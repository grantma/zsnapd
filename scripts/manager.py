#!/usr/bin/python3
# Copyright (c) 2014-2017 Kenneth Henderick <kenneth@ketronic.be>
# Copyright (c) 2019 Matthew Grant <matt@mattgrant.net.nz>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""
Provides the overall functionality
"""

import time
import os
import re
from collections import OrderedDict
from socket import gethostname

from magcode.core.globals_ import *
from magcode.core.utility import connect_test_address
from magcode.core.utility import get_numeric_setting

from scripts.zfs import ZFS
from scripts.clean import Cleaner
from scripts.helper import Helper
from scripts.config import MeterTime
from scripts.globals_ import SNAPSHOTNAME_FMTSPEC
from scripts.globals_ import SNAPSHOTNAME_REGEX

PROC_FAILURE = 0
PROC_EXECUTED = 1
PROC_CHANGED = 2

class IsConnected(object):
    """
    Test object class for caching endpoint connectivity and testing for it as well
    """
    def __init__(self):
        self.unconnected_list = []
        self.connected_list = []

    def _test_connected(self, host, port):
        connect_retry_wait = get_numeric_setting('connect_retry_wait', float)
        exc_msg = ''
        for t in range(3):
            try:
                # Transform any hostname to an IP address
                connect_test_address(host, port)
                break
            except(IOError, OSError) as exc:
                exc_msg = str(exc)
                time.sleep(connect_retry_wait)
                continue
        else:
            if self.local_dataset:
                log_info("[{0}] - Can't reach endpoint '{1}:{2}' - {3}"
                        .format(self.local_dataset, host, port, exc_msg))
            else:
                log_error("Can't reach endpoint '{0}:{1}' - {2}".format(host, port, exc_msg))
            return False
        return True

    def test_unconnected(self, dataset_settings, local_dataset=''):
        """
        Check that endpoint is unconnected
        """
        self.local_dataset = local_dataset
        replicate_param = dataset_settings['replicate']
        if (replicate_param and replicate_param['endpoint_host']):
            host = replicate_param['endpoint_host']
            port = replicate_param['endpoint_port']
            if ((host, port) in self.unconnected_list):
                return(True)
            if ((host, port) not in self.connected_list):
                if self._test_connected(host, port):
                    self.connected_list.append((host, port))
                    # Go and write trigger
                else:
                    self.unconnected_list.append((host, port))
                    return(True)
        return(False)

class Manager(object):
    """
    Manages the ZFS snapshotting process
    """

    @staticmethod
    def touch_trigger(ds_settings, test_reachable, *args):
        """
        Runs around creating .trigger files for datasets with time = trigger
        """
        result = True
        datasets = ZFS.get_datasets()
        ds_candidates = [ds.rstrip('/') for ds in args if ds[0] != '/']
        mnt_candidates = [m.rstrip('/') for m in args if m[0] == '/']
        trigger_mnts_dict = {ds_settings[ds]['mountpoint']:ds for ds in ds_settings if ds_settings[ds]['time'] == 'trigger'}
        if len(ds_candidates):
            for candidate in ds_candidates:
                if candidate not in datasets:
                    log_error("Dataset '{0}' does not exist.".format(candidate))
                    sys.exit(os.EX_DATAERR)
                if candidate not in ds_settings:
                    log_error("Dataset '{0}' is not configured fo zsnapd.".format(candidate))
                    sys.exit(os.EX_DATAERR)
        if len(mnt_candidates):
            for candidate in mnt_candidates:
                if candidate not in trigger_mnts_dict:
                    log_error("Trigger mount '{0}' not configured for zsnapd".format(candidate))
                    sys.exit(os.EX_DATAERR)
                if trigger_mnts_dict[candidate] not in datasets:
                    log_error("Dataset '{0}' for trigger mount {1} does not exist.".format(candidate, trigger_mnts_dict[candidate]))
                    sys.exit(os.EX_DATAERR)
                ds_candidates.append(trigger_mnts_dict[candidate])

        is_connected = IsConnected()
        for dataset in datasets:
            if dataset in ds_settings:
                if (len(ds_candidates) and dataset not in ds_candidates):
                    continue
                try:
                    dataset_settings = ds_settings[dataset]

                    take_snapshot = dataset_settings['snapshot'] is True
                    replicate = dataset_settings['replicate'] is not None

                    if take_snapshot is True or replicate is True:
                        if dataset_settings['time'] == 'trigger':
                            # Check endpoint for trigger is connected
                            if test_reachable and is_connected.test_unconnected(dataset_settings):
                                continue
                            # Trigger file testing and creation
                            trigger_filename = '{0}/.trigger'.format(dataset_settings['mountpoint'])
                            if os.path.exists(trigger_filename):
                                continue
                            if (not os.path.isdir(dataset_settings['mountpoint'])):
                                log_error("Directory '{0}' does not exist.".format(dataset_settings['mountpoint']))
                                result = False
                                continue
                            trigger_file = open(trigger_filename, 'wt')
                            trigger_file.close()
                except Exception as ex:
                    log_error('Exception: {0}'.format(str(ex)))
        del is_connected
        return result

    @staticmethod
    def snapshot(dataset, snapshots, now, local_dataset='', endpoint='', log_command=False):
        local_dataset = dataset if not local_dataset else local_dataset
        result = PROC_EXECUTED
        this_time = time.strftime(SNAPSHOTNAME_FMTSPEC, time.localtime(now))
        # Take this_time's snapshotzfs
        log_info('[{0}] - Taking snapshot {1}@{2}'.format(local_dataset, dataset, this_time))
        try:
            ZFS.snapshot(dataset, this_time, endpoint=endpoint, log_command=log_command)
        except Exception as ex:
            # if snapshot fails move onto next one
            log_error('[{0}] -   Exception: {1}'.format(local_dataset, str(ex)))
            return PROC_FAILURE
        else:
            snapshots.update({this_time:{'name': this_time, 'creation': now}})
            log_info('[{0}] - Taking snapshot {1}@{2} complete'.format(local_dataset, dataset, this_time))
            result = PROC_CHANGED
        return result

    @staticmethod
    def replicate(src_dataset, src_snapshots, dst_dataset, dst_snapshots, replicate_settings):
        result = PROC_EXECUTED
        push = replicate_settings['target'] is not None
        replicate_dirN = 'push' if push else 'pull'
        src_endpoint = '' if push else replicate_settings['endpoint']
        dst_endpoint = replicate_settings['endpoint'] if push else ''
        src_host = gethostname().split('.')[0] if push else replicate_settings['endpoint_host']
        local_dataset = src_dataset if push else dst_dataset
        full_clone = replicate_settings['full_clone']
        send_compression = replicate_settings['send_compression']
        send_properties = replicate_settings['send_properties']
        all_snapshots = replicate_settings['all_snapshots']
        buffer_size = replicate_settings['buffer_size']
        compression = replicate_settings['compression']
        log_command = replicate_settings['log_commands']
        extra_args = {'full_clone': full_clone, 'all_snapshots': all_snapshots,
                'send_compression': send_compression, 'send_properties': send_properties,
                'buffer_size': buffer_size, 'compression': compression,
                'log_command': log_command }
        log_info('[{0}] - Replicating [{1}]:{2}'.format(local_dataset, src_host, src_dataset))
        last_common_snapshot = None
        index_last_common_snapshot = None
        # Search for the last src snapshot that is available in dst
        for snapshot in src_snapshots:
            if snapshot in dst_snapshots:
                last_common_snapshot = snapshot
                index_last_common_snapshot = list(src_snapshots).index(snapshot)
        if last_common_snapshot is not None:  # There's a common snapshot
            snaps_to_send = list(src_snapshots)[index_last_common_snapshot:]
            # Remove first element as it is already at other end
            snaps_to_send.pop(0)
            previous_snapshot = last_common_snapshot
            if full_clone or all_snapshots:
                prevsnap_name = src_snapshots[previous_snapshot]['name']
                snapshot = list(src_snapshots)[-1]
                snap_name = src_snapshots[snapshot]['name']
                # There is a snapshot on this host that is not yet on the other side.
                size = ZFS.get_size(src_dataset, prevsnap_name, snap_name, endpoint=src_endpoint, **extra_args)
                log_info('[{0}] -   {1}@{2} > {1}@{3} ({4})'.format(local_dataset, src_dataset, prevsnap_name, snap_name, size))
                ZFS.replicate(src_dataset, prevsnap_name, snap_name, dst_dataset, replicate_settings['endpoint'],
                        direction=replicate_dirN, **extra_args)
                ZFS.hold(src_dataset, snap_name, endpoint=src_endpoint, log_command=log_command)
                ZFS.hold(dst_dataset, snap_name, endpoint=dst_endpoint, log_command=log_command)
                ZFS.release(src_dataset, prevsnap_name, endpoint=src_endpoint, log_command=log_command)
                ZFS.release(dst_dataset, prevsnap_name, endpoint=dst_endpoint, log_command=log_command)
                for snapshot in snaps_to_send:
                    dst_snapshots.update({snapshot:src_snapshots[snapshot]})
                result = PROC_CHANGED
            else:
                for snapshot in snaps_to_send:
                    prevsnap_name = src_snapshots[previous_snapshot]['name']
                    snap_name = src_snapshots[snapshot]['name']
                    # There is a snapshot on this host that is not yet on the other side.
                    size = ZFS.get_size(src_dataset, prevsnap_name, snap_name, endpoint=src_endpoint, **extra_args)
                    log_info('[{0}] -   {1}@{2} > {1}@{3} ({4})'.format(local_dataset, src_dataset, prevsnap_name, snap_name, size))
                    ZFS.replicate(src_dataset, prevsnap_name, snap_name, dst_dataset, replicate_settings['endpoint'],
                            direction=replicate_dirN, **extra_args)
                    ZFS.hold(src_dataset, snap_name, endpoint=src_endpoint, log_command=log_command)
                    ZFS.hold(dst_dataset, snap_name, endpoint=dst_endpoint, log_command=log_command)
                    ZFS.release(src_dataset, prevsnap_name, endpoint=src_endpoint, log_command=log_command)
                    ZFS.release(dst_dataset, prevsnap_name, endpoint=dst_endpoint, log_command=log_command)
                    previous_snapshot = snapshot
                    dst_snapshots.update({snapshot:src_snapshots[snapshot]})
                    result = PROC_CHANGED
        elif len(src_snapshots) > 0:
            # No remote snapshot, full replication
            snapshot = list(src_snapshots)[-1]
            snap_name = src_snapshots[snapshot]['name']
            size = ZFS.get_size(src_dataset, None, snap_name, endpoint=src_endpoint, **extra_args)
            log_info('  {0}@         > {0}@{1} ({2})'.format(src_dataset, snap_name, size))
            ZFS.replicate(src_dataset, None, snap_name, dst_dataset, replicate_settings['endpoint'],
                    direction=replicate_dirN, compression=replicate_settings['compression'], **extra_args)
            ZFS.hold(src_dataset, snap_name, endpoint=src_endpoint, log_command=log_command)
            ZFS.hold(dst_dataset, snap_name, endpoint=dst_endpoint, log_command=log_command)
            if full_clone:
                for snapshot in src_snapshosts:
                    dst_snapshots.update({snapshot:src_snapshots[snapshot]})
            else:
                dst_snapshots.update({snapshot:src_snapshots[snapshot]})
            result = PROC_CHANGED
        log_info('[{0}] - Replicating [{1}]:{2} complete'.format(local_dataset, src_host, src_dataset))
        return result

    @staticmethod
    def run(ds_settings, sleep_time):
        """
        Executes a single run where certain datasets might or might not be snapshotted
        """

        meter_time = MeterTime(sleep_time)
        now = int(time.time())
        this_time = time.strftime(SNAPSHOTNAME_FMTSPEC, time.localtime(now))

        snapshots = ZFS.get_snapshots()
        datasets = ZFS.get_datasets()
        is_connected = IsConnected()
        for dataset in datasets:
            if dataset not in ds_settings:
                continue
            try:
                dataset_settings = ds_settings[dataset]
                log_command = dataset_settings['log_commands']
                local_snapshots = snapshots.get(dataset, OrderedDict())
                # Manage what snapshots we operate on - everything or zsnapd only
                if not dataset_settings['all_snapshots']:
                    for snapshot in local_snapshots:
                        snapshotname = local_snapshots[snapshot]['name']
                        if (re.match(SNAPSHOTNAME_REGEX, snapshotname)):
                            continue
                        local_snapshots.pop(snapshot)

                take_snapshot = dataset_settings['snapshot'] is True
                replicate = dataset_settings['replicate'] is not None

                # Decide whether we need to handle this dataset
                if not take_snapshot and not replicate:
                    continue
                if dataset_settings['time'] == 'trigger':
                    # We wait until we find a trigger file in the filesystem
                    trigger_filename = '{0}/.trigger'.format(dataset_settings['mountpoint'])
                    if os.path.exists(trigger_filename):
                        log_info('[{0}] - Trigger found on {1}'.format(dataset, dataset))
                        os.remove(trigger_filename)
                    else:
                        continue
                else:
                    if not meter_time.has_time_passed(dataset_settings['time'], now):
                        continue
                    log_info('[{0}] - Time passed for {1}'.format(dataset, dataset))

                replicate_settings = dataset_settings['replicate']
                push = replicate_settings['target'] is not None if replicate else True
                if push:
                    # Pre exectution command
                    if dataset_settings['preexec'] is not None:
                        Helper.run_command(dataset_settings['preexec'], '/', log_command=log_command)

                    result = PROC_FAILURE
                    if (take_snapshot is True and this_time not in local_snapshots):
                        result = Manager.snapshot(dataset, local_snapshots, now, log_command=log_command)
                    # Clean snapshots if one has been taken - clean will not execute
                    # if no snapshot taken
                    Cleaner.clean(dataset, local_snapshots, dataset_settings['schema'], log_command=log_command,
                            all_snapshots=dataset_settings['clean_all'])
                    # Execute postexec command
                    if result and dataset_settings['postexec'] is not None:
                            Helper.run_command(dataset_settings['postexec'], '/', log_command=log_command)

                    # Replicating, if required
                    # If network replicating, check connectivity here
                    test_unconnected = is_connected.test_unconnected(dataset_settings, local_dataset=dataset)
                    if test_unconnected:
                        log_info("[{0}] - Skipping as '{1}:{2}' unreachable"
                                .format(dataset, replicate_settings['endpoint_host'], replicate_settings['endpoint_port']))
                        continue

                    if (replicate is True):
                        remote_dataset = replicate_settings['target']
                        remote_snapshots = ZFS.get_snapshots(remote_dataset, replicate_settings['endpoint'], log_command=log_command,
                                all_snapshots=dataset_settings['all_snapshots'])
                        remote_snapshots = remote_snapshots.get(remote_dataset, OrderedDict())
                        result = Manager.replicate(dataset, local_snapshots, remote_dataset, remote_snapshots, replicate_settings)
                        # Clean snapshots remotely if one has been taken - only kept snapshots will allow aging
                        if (dataset_settings['remote_schema']):
                            Cleaner.clean(remote_dataset, remote_snapshots, dataset_settings['remote_schema'], log_command=log_command,
                                    all_snapshots=dataset_settings['remote_clean_all'])
                        # Post execution command
                        if (result and dataset_settings['replicate_postexec'] is not None):
                            Helper.run_command(dataset_settings['replicate_postexec'], '/', log_command=log_command)
                else:
                    # Pull logic for remote site
                    # Replicating, if required
                    # If network replicating, check connectivity here
                    test_unconnected = is_connected.test_unconnected(dataset_settings, local_dataset=dataset)
                    if test_unconnected:
                        log_warn("[{$0}] - Skipping as '{1}:{2}' unreachable"
                                .format(dataset, replicate_settings['endpoint_host'], replicate_settings['endpoint_port']))
                        continue
                    
                    remote_dataset = replicate_settings['target'] if push else replicate_settings['source']
                    remote_datasets = ZFS.get_datasets(replicate_settings['endpoint'], log_command=log_command)
                    remote_snapshots = ZFS.get_snapshots(remote_dataset, replicate_settings['endpoint'], log_command=log_command,
                            all_snapshots=dataset_settings['all_snapshots'])
                    if remote_dataset not in remote_datasets:
                        log_error("[{0}] - remote dataset '{1}' does not exist".format(dataset, remote_dataset))
                        continue
                    remote_snapshots = remote_snapshots.get(remote_dataset, OrderedDict())
                    endpoint = replicate_settings['endpoint']
                    if (take_snapshot is True and this_time not in remote_snapshots):
                        # Only execute everything here if needed

                        # Remote Pre exectution command
                        if dataset_settings['preexec'] is not None:
                            Helper.run_command(dataset_settings['preexec'], '/', endpoint=endpoint, log_command=log_command)

                        # Take remote snapshot
                        result = PROC_FAILURE
                        result = Manager.snapshot(remote_dataset, remote_snapshots, now, endpoint=endpoint, local_dataset=dataset, log_command=log_command)
                        # Clean remote snapshots if one has been taken - only kept snapshots will aging to happen
                        Cleaner.clean(remote_dataset, remote_snapshots, dataset_settings['schema'], log_command=log_command,
                                endpoint=endpoint, local_dataset=dataset, all_snapshots=dataset_settings['clean_all'])
                        # Execute remote postexec command
                        if result and dataset_settings['postexec'] is not None:
                                Helper.run_command(dataset_settings['postexec'], '/', endpoint=endpoint, log_command=log_command)

                    if (replicate is True):
                        result = PROC_FAILURE
                        result = Manager.replicate(remote_dataset, remote_snapshots, dataset, local_snapshots, replicate_settings)
                        # Clean snapshots locally if one has been taken - only kept snapshots will allow aging
                        #if not replicate_settings['full_clone']:
                        Cleaner.clean(dataset, local_snapshots, dataset_settings['local_schema'], log_command=log_command,
                                all_snapshots=dataset_settings['local_clean_all'])
                        # Post execution command
                        if (result and dataset_settings['replicate_postexec'] is not None):
                            Helper.run_command(dataset_settings['replicate_postexec'], '/', endpoint=endpoint, log_command=log_command)

            except Exception as ex:
                log_error('[{0}] - Exception: {1}'.format(dataset, str(ex)))

        # Clean up
        del is_connected

