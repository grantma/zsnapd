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

from zsnap.zfs import ZFS
from zsnap.clean import Cleaner
from zsnap.helper import Helper
from zsnap.globals_ import SNAPSHOTNAME_FMTSPEC
from zsnap.globals_ import SNAPSHOTNAME_REGEX
from zsnap.globals_ import TRIGGER_FILENAME

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

    def test_unconnected(self, replicate_param, local_dataset=''):
        """
        Check that endpoint is unconnected
        """
        self.local_dataset = local_dataset
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
    def touch_trigger(ds_settings, test_reachable, do_trigger, *args):
        """
        Runs around creating .trigger files for datasets with time = trigger
        """
        result = True
        datasets = ZFS.get_datasets()
        ds_candidates = [ds.rstrip('/') for ds in args if ds[0] != '/']
        mnt_candidates = [m.rstrip('/') for m in args if m[0] == '/']
        do_trigger_candidates = [ds for ds in ds_settings if ds_settings[ds]['do_trigger']]
        trigger_mnts_dict = {ds_settings[ds]['mountpoint']:ds for ds in ds_settings if ds_settings[ds]['time'].is_trigger()}
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
        # If no candidates given on comman line, process all those with do_trigger set
        if (do_trigger and not ds_candidates):
            ds_candidates = do_trigger_candidates
        # If do_trigger, only process those datasets with do_trigger set
        elif (do_trigger and ds_candidates):
            for ds in ds_candidates:
                if (settings['verbose'] and not ds_settings[ds]['do_trigger']):
                    log_info("Dataset '{0}' 'do_trigger' not set - skipping.".format(ds))
            ds_candidates = [ ds for ds in ds_candidates if ds_settings[ds]['do_trigger']]
        if (not len(ds_candidates)):
            log_error("No datasets configured for triggers or given on command line.")
            sys.exit(os.EX_NOINPUT)
        # Check ds_candidates for is_trigger and mnt point
        for ds in ds_candidates:
            if (not ds_settings[ds]['time'].is_trigger() and settings['verbose']):
                log_info("Dataset '{0}' is not configured for triggers - skipping.".format(ds))
            if (not ds_settings[ds]['mountpoint'] and settings['verbose']):
                log_info("Dataset '{0}' does not have a mountpoint configured - skipping.".format(ds))

        is_connected = IsConnected()
        for dataset in datasets:
            if dataset in ds_settings:
                if (len(ds_candidates) and dataset not in ds_candidates):
                    continue
                try:
                    dataset_settings = ds_settings[dataset]

                    take_snapshot = dataset_settings['snapshot'] is True
                    replicate = dataset_settings['replicate'] is not None
                    clean = bool(dataset_settings['schema'])

                    if take_snapshot is True or replicate is True or clean is True:
                        if dataset_settings['time'].is_trigger() and dataset_settings['mountpoint']:
                            # Check endpoint for trigger is connected
                            if test_reachable and is_connected.test_unconnected(dataset_settings['replicate']):
                                continue
                            # Trigger file testing and creation
                            trigger_filename = '{0}/{1}'.format(dataset_settings['mountpoint'], TRIGGER_FILENAME)
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
    def new_hold(dataset, snap_name, endpoint='', log_command=False):
        result = PROC_EXECUTED
        holds = ZFS.holds(dataset, endpoint=endpoint, log_command=log_command)
        ZFS.hold(dataset, snap_name, endpoint=endpoint, log_command=log_command, may_exist=True)
        if snap_name in holds:
            holds.remove(snap_name)
        for hold in holds:
            ZFS.release(dataset, hold, endpoint=endpoint, log_command=log_command)
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
        dst_host = gethostname().split('.')[0] if not push else replicate_settings['endpoint_host']
        local_dataset = src_dataset if push else dst_dataset
        full_clone = replicate_settings['full_clone']
        receive_save = replicate_settings['receive_save']
        receive_no_mountpoint = replicate_settings['receive_no_mountpoint']
        receive_mountpoint = replicate_settings['receive_mountpoint']
        receive_umount = replicate_settings['receive_umount']
        send_compression = replicate_settings['send_compression']
        send_properties = replicate_settings['send_properties']
        send_raw = replicate_settings['send_raw']
        all_snapshots = replicate_settings['all_snapshots']
        buffer_size = replicate_settings['buffer_size']
        compression = replicate_settings['compression']
        log_command = replicate_settings['log_commands']
        extra_args = {'full_clone': full_clone, 'all_snapshots': all_snapshots,
                'receive_no_mountpoint': receive_no_mountpoint, 'receive_umount': receive_umount,
                'receive_save': receive_save, 'receive_mountpoint': receive_mountpoint,
                'send_compression': send_compression, 'send_properties': send_properties,
                'buffer_size': buffer_size, 'compression': compression, 'send_raw': send_raw,
                'log_command': log_command }
        # Get any receive_resume_tokens
        receive_resume_token = ''
        if push:
            receive_resume_token = ZFS.get_receive_resume_token(dst_dataset, endpoint=dst_endpoint, log_command=log_command)
        else:
            receive_resume_token = ZFS.get_receive_resume_token(src_dataset, endpoint=src_endpoint, log_command=log_command)
        if receive_resume_token:
            log_info('[{0}] - Resuming replicating [{1}]:{2} to [{3}]:{4}'.format(local_dataset, src_host, src_dataset, dst_host, dst_dataset))
            size = ZFS.get_size(src_dataset, None, None, src_endpoint, receive_resume_token, **extra_args)
            log_info('[{0}] -   {1}@??? > {1}@??? ({2})'.format(local_dataset, src_dataset, size))
            ZFS.replicate(src_dataset, None, None, dst_dataset, replicate_settings['endpoint'],
                    receive_resume_token, direction=replicate_dirN, **extra_args)
            # Recalculate dst data sets
            if push:
                dst_endpoint = replicate_settings['endpoint']
            else:
                dst_endpoint = ''
            new_dst_snapshots = ZFS.get_snapshots2(dst_dataset, dst_endpoint, log_command=log_command,
                    all_snapshots=all_snapshots)
            snapshot = list(new_dst_snapshots)[-1]
            snap_name = new_dst_snapshots[snapshot]['name']
            Manager.new_hold(src_dataset, snap_name, endpoint=src_endpoint, log_command=log_command)
            Manager.new_hold(dst_dataset, snap_name, endpoint=dst_endpoint, log_command=log_command)
            dst_snapshots.clear()
            dst_snapshots.update(new_dst_snapshots)
            log_info('[{0}] - Resumed replicatiion [{1}]:{2} to [{3}]:{4} complete'.format(local_dataset, src_host, src_dataset, dst_host, dst_dataset))
            result= PROC_CHANGED
            return result

        log_info('[{0}] - Replicating [{1}]:{2} to [{3}]:{4}'.format(local_dataset, src_host, src_dataset, dst_host, dst_dataset))
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
                Manager.new_hold(src_dataset, snap_name, endpoint=src_endpoint, log_command=log_command)
                Manager.new_hold(dst_dataset, snap_name, endpoint=dst_endpoint, log_command=log_command)
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
                    Manager.new_hold(src_dataset, snap_name, endpoint=src_endpoint, log_command=log_command)
                    Manager.new_hold(dst_dataset, snap_name, endpoint=dst_endpoint, log_command=log_command)
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
                    direction=replicate_dirN, **extra_args)
            Manager.new_hold(src_dataset, snap_name, endpoint=src_endpoint, log_command=log_command)
            ZFS.hold(dst_dataset, snap_name, endpoint=dst_endpoint, log_command=log_command)
            if full_clone:
                for snapshot in src_snapshots:
                    dst_snapshots.update({snapshot:src_snapshots[snapshot]})
            else:
                dst_snapshots.update({snapshot:src_snapshots[snapshot]})
            result = PROC_CHANGED
        log_info('[{0}] - Replicating [{1}]:{2} to [{3}]:{4} complete'.format(local_dataset, src_host, src_dataset, dst_host, dst_dataset))
        return result

    @staticmethod
    def run(ds_settings, sleep_time):
        """
        Executes a single run where certain datasets might or might not be snapshotted
        """

        snapshots = ZFS.get_snapshots()
        datasets = ZFS.get_datasets()
        is_connected = IsConnected()
        for dataset in datasets:
            if dataset not in ds_settings:
                continue

            # Evaluate per dataset to make closer to actual snapshot time
            # Can wander due to large volume transfers and replications
            now = int(time.time())
            this_time = time.strftime(SNAPSHOTNAME_FMTSPEC, time.localtime(now))

            try:
                dataset_settings = ds_settings[dataset]
                take_snapshot = dataset_settings['snapshot'] is True
                replicate = dataset_settings['replicate'] is not None
                replicate2 = dataset_settings['replicate2'] is not None
                clean = bool(dataset_settings['schema'])

                # Decide whether we need to handle this dataset
                if not take_snapshot and not replicate and not replicate2 and not clean:
                    continue

                replicate_settings = dataset_settings['replicate']
                replicate2_settings = dataset_settings['replicate2']
                full_clone = replicate_settings['full_clone'] if replicate else False
                full_clone2 = replicate2_settings['full_clone'] if replicate2 else False
                log_command = dataset_settings['log_commands']
                local_snapshots = snapshots.get(dataset, OrderedDict())
                # Manage what snapshots we operate on - everything or zsnapd only
                if (not dataset_settings['all_snapshots'] and not full_clone):
                    for snapshot in local_snapshots:
                        snapshotname = local_snapshots[snapshot]['name']
                        if (re.match(SNAPSHOTNAME_REGEX, snapshotname)):
                            continue
                        local_snapshots.pop(snapshot)

                meter_time = dataset_settings['time']
                if not meter_time.do_run(now):
                    continue

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
                    result = PROC_FAILURE
                    result2 = PROC_FAILURE
                    if (replicate is True):
                        # If network replicating, check connectivity here
                        test_unconnected = is_connected.test_unconnected(replicate_settings, local_dataset=dataset)
                        if test_unconnected:
                            log_info("[{0}] - Skipping as '{1}:{2}' unreachable"
                                    .format(dataset, replicate_settings['endpoint_host'], replicate_settings['endpoint_port']))
                            continue

                        remote_dataset = replicate_settings['target']
                        remote_snapshots = ZFS.get_snapshots2(remote_dataset, replicate_settings['endpoint'], log_command=log_command,
                                all_snapshots=dataset_settings['all_snapshots'])
                        result = Manager.replicate(dataset, local_snapshots, remote_dataset, remote_snapshots, replicate_settings)
                        # Clean snapshots remotely if one has been taken - only kept snapshots will allow aging
                        if (dataset_settings['remote_schema']):
                            Cleaner.clean(remote_dataset, remote_snapshots, dataset_settings['remote_schema'], log_command=log_command,
                                    all_snapshots=dataset_settings['remote_clean_all'])
                    if (replicate2 is True):
                        # If network replicating, check connectivity here
                        test_unconnected = is_connected.test_unconnected(replicate2_settings, local_dataset=dataset)
                        if test_unconnected:
                            log_info("[{0}] - Skipping as '{1}:{2}' unreachable"
                                    .format(dataset, replicate2_settings['endpoint_host'], replicate2_settings['endpoint_port']))
                            continue

                        remote_dataset = replicate2_settings['target']
                        remote_snapshots = ZFS.get_snapshots2(remote_dataset, replicate2_settings['endpoint'], log_command=log_command,
                                all_snapshots=dataset_settings['all_snapshots'])
                        result2 = Manager.replicate(dataset, local_snapshots, remote_dataset, remote_snapshots, replicate2_settings)
                        # Clean snapshots remotely if one has been taken - only kept snapshots will allow aging
                        if (dataset_settings['remote2_schema']):
                            Cleaner.clean(remote_dataset, remote_snapshots, dataset_settings['remote2_schema'], log_command=log_command,
                                    all_snapshots=dataset_settings['remote2_clean_all'])
                    # Post execution command
                    if ((result or result2) and dataset_settings['replicate_postexec'] is not None):
                        Helper.run_command(dataset_settings['replicate_postexec'], '/', log_command=log_command)
                else:
                    # Pull logic for remote site
                    # Replicating, if required
                    # If network replicating, check connectivity here
                    test_unconnected = is_connected.test_unconnected(replicate_settings, local_dataset=dataset)
                    if test_unconnected:
                        log_warn("[{$0}] - Skipping as '{1}:{2}' unreachable"
                                .format(dataset, replicate_settings['endpoint_host'], replicate_settings['endpoint_port']))
                        continue
                    
                    remote_dataset = replicate_settings['target'] if push else replicate_settings['source']
                    remote_datasets = ZFS.get_datasets(replicate_settings['endpoint'], remote_dataset, log_command=log_command)
                    if remote_dataset not in remote_datasets:
                        log_error("[{0}] - remote dataset '{1}' does not exist".format(dataset, remote_dataset))
                        continue
                    remote_snapshots = ZFS.get_snapshots2(remote_dataset, replicate_settings['endpoint'], log_command=log_command,
                            all_snapshots=dataset_settings['all_snapshots'])
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

