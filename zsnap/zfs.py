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
Provides basic ZFS functionality
"""

import time
import re
from collections import OrderedDict

from magcode.core.globals_ import log_debug
from magcode.core.globals_ import log_info
from magcode.core.globals_ import log_error
from magcode.core.globals_ import debug_verbose

from zsnap.globals_ import SNAPSHOTNAME_REGEX
from zsnap.globals_ import SNAPSHOTNAME_FMTSPEC
from zsnap.globals_ import DEFAULT_BUFFER_SIZE
from zsnap.helper import Helper


class ZFS(object):
    """
    Contains generic ZFS functionality
    """

    @staticmethod
    def get_snapshots(dataset='', endpoint='', all_snapshots=True, log_command=False):
        """
        Retreives a list of snapshots
        """

        if endpoint == '':
            command = 'zfs list -pH -s creation -o name,creation -t snapshot{0}{1} || true'
        else:
            command = '{0} \'zfs list -pH -s creation -o name,creation -t snapshot{1} || true\''
        if dataset == '':
            dataset_filter = ''
        else:
            dataset_filter = ' | grep ^{0}@'.format(dataset)
        output = Helper.run_command(command.format(endpoint, dataset_filter), '/', log_command=log_command)
        snapshots = {}
        for line in filter(len, output.split('\n')):
            parts = list(filter(len, line.split('\t')))
            datasetname = parts[0].split('@')[0]
            creation = int(parts[1])
            snapshot = time.strftime(SNAPSHOTNAME_FMTSPEC, time.localtime(creation))
            snapshotname = parts[0].split('@')[1]
            if (not all_snapshots and re.match(SNAPSHOTNAME_REGEX, snapshotname) is None):
                # If required, only read in zsnapd snapshots
                continue
            if datasetname not in snapshots:
                snapshots[datasetname] = OrderedDict()
            snapshots[datasetname].update({snapshot:{'name': snapshotname, 'creation': creation}})
        return snapshots

    @staticmethod
    def get_snapshots2(dataset, endpoint='', all_snapshots=True, log_command=False):
        """
        Retreives a list of snapshots from a dataset
        """
        command = 'zfs list -pH -s creation -o name,creation -t snapshot {1} || true'
        if endpoint:
            command = '{0} \'' + command + '\''
        output = Helper.run_command(command.format(endpoint, dataset), '/', log_command=log_command)
        snapshots = OrderedDict()
        for line in filter(len, output.split('\n')):
            parts = list(filter(len, line.split('\t')))
            creation = int(parts[1])
            snapshot = time.strftime(SNAPSHOTNAME_FMTSPEC, time.localtime(creation))
            snapshotname = parts[0].split('@')[1]
            if (not all_snapshots and re.match(SNAPSHOTNAME_REGEX, snapshotname) is None):
                # If required, only read in zsnapd snapshots
                continue
            snapshots[snapshot] = {'name': snapshotname, 'creation': creation}
        return snapshots

    @staticmethod
    def get_datasets(endpoint='', log_command=False):
        """
        Retreives all datasets
        """
        if endpoint == '':
            command = 'zfs list -pH -o name,mountpoint'
        else:
            command = "{0} 'zfs list -pH -o name,mountpoint'"
        output = Helper.run_command(command.format(endpoint), '/', log_command=log_command)
        datasets = {}
        for line in filter(len, output.split('\n')):
            parts = list(filter(len, line.split('\t')))
            datasets[parts[0]] = {'name': parts[0], 'mountpoint': parts[1]}
        return datasets

    @staticmethod
    def snapshot(dataset, name, endpoint='', log_command=False):
        """
        Takes a snapshot
        """
        if endpoint == '':
            command = 'zfs snapshot {0}@{1}'.format(dataset, name)
        else:
            command = "{0} 'zfs snapshot {1}@{2}'".format(endpoint, dataset, name)
        Helper.run_command(command, '/', log_command=log_command)

    @staticmethod
    def abort_interrupted_receive(dataset, endpoint='', log_command=False, no_save=False):
        """
        Abort an interrupted receive
        """
        filter_error = 'does not have any resumable receive state to abort' if no_save else ''
        if endpoint == '':
            command = 'zfs receive -A {0}'.format(dataset)
        else:
            command = "{0} 'zfs receive -A {1}'".format(endpoint, dataset)
        Helper.run_command(command, '/', log_command=log_command, filter_error=filter_error)

    @staticmethod
    def get_receive_resume_token(dataset, endpoint='', log_command=False):
        """
        Retreives a resume token
        """
        if endpoint == '':
            command = 'zfs get receive_resume_token -pHo value {0} || true'.format(dataset)
        else:
            command = "{0} 'zfs get receive_resume_token -pHo value {1} || true'".format(endpoint, dataset)
        output = Helper.run_command(command, '/', log_command=log_command)
        receive_resume_token = ''
        for line in filter(len, output.split('\n')):
            receive_resume_token = line
        return receive_resume_token if receive_resume_token != '-' else ''

    @staticmethod
    def replicate(dataset, base_snapshot, last_snapshot, target, endpoint='', receive_resume_token='', direction='push',
            buffer_size=DEFAULT_BUFFER_SIZE, compression=None, receive_mountpoint='',
            full_clone=False, all_snapshots=True, send_compression=False,
            send_properties=False, send_raw=False, receive_no_mountpoint=False, receive_umount=False, receive_save=False, log_command=False):
        """
        Replicates a dataset towards a given endpoint/target (push)
        Replicates a dataset from a given endpoint to a local target (pull)
        """

        delta = ''
        if base_snapshot is not None:
            if (not full_clone and not all_snapshots):
                delta = '-i {0}@{1} '.format(dataset, base_snapshot)
            else:
                delta = '-I {0}@{1} '.format(dataset, base_snapshot)

        send_args = ''
        if send_compression:
            send_args += 'Lec'
        if send_raw:
            send_args += 'w'
        if not receive_resume_token:
            if send_properties:
                send_args += 'p'
            if full_clone:
                send_args += 'R'
        if send_args:
            send_args = '-' + send_args
            send_args += ' '

        receive_args = ''
        if receive_save:
            receive_args = 's'
        if receive_umount:
            receive_args += 'u'
        if receive_args:
            receive_args = '-' + receive_args
            receive_args += ' '
        if receive_no_mountpoint:
            receive_args += '-x mountpoint '
        if receive_mountpoint:
            receive_args += '-o "mountpoint={0}" '.format(receive_mountpoint)

        if compression is not None:
            compress = '| {0} -c'.format(compression)
            decompress = '| {0} -cd'.format(compression)
        else:
            compress = ''
            decompress = ''

        if debug_verbose():
            # Log these commands if verbose debug
            log_command = True

        # Work out zfs send command
        if receive_resume_token:
            zfs_send_cmd = 'zfs send {0}-t ' + receive_resume_token
        else:
            zfs_send_cmd = 'zfs send {0}{1}{2}@{3}'

        if endpoint == '':
            # We're replicating to a local target
            command = zfs_send_cmd + ' | zfs receive {4}-F {5}'
            command = command.format(send_args, delta, dataset, last_snapshot, receive_args, target)
            Helper.run_command(command, '/', log_command=log_command)
        else:
            if direction == 'push':
                # We're replicating to a remote server
                command = zfs_send_cmd + ' {4} | mbuffer -q -v 0 -s 128k -m {5} | {6} \'mbuffer -q -v 0 -s 128k -m {5} {7} | zfs receive {8}-F {9}\''
                command = command.format(send_args, delta, dataset, last_snapshot, compress, buffer_size, endpoint, decompress, receive_args, target)
                Helper.run_command(command, '/', log_command=log_command)
            elif direction == 'pull':
                # We're pulling from a remote server
                command = '{5} \'' + zfs_send_cmd + ' {4} | mbuffer -q -v 0 -s 128k -m {6}\' | mbuffer -q -v 0 -s 128k -m {6} {7} | zfs receive {8}-F {9}'
                command = command.format(send_args, delta, dataset, last_snapshot, compress, endpoint, buffer_size, decompress, receive_args, target)
                Helper.run_command(command, '/', log_command=log_command)

    @staticmethod
    def holds(target, endpoint='', log_command=False):
        command = 'zfs list -H -r -d 1 -t snapshot -o name {1} | xargs -d "\\n" zfs holds -H'
        if endpoint != '':
            command = '{0} \'' + command + '\''
        command = command.format(endpoint, target)
        output = Helper.run_command(command, '/', log_command=log_command)
        holds = []
        for line in filter(len, output.split('\n')):
            parts = list(filter(len, line.split('\t')))
            if parts[1] != 'zsm':
                continue
            snapshotname = parts[0].split('@')[1]
            holds.append(snapshotname)
        holds.sort()
        return holds

    @staticmethod
    def is_held(target, snapshot, endpoint='', log_command=False):
        if endpoint == '':
            command = 'zfs holds {0}@{1}'.format(target, snapshot)
            return 'zsm' in Helper.run_command(command, '/', log_command=log_command)
        command = '{0} \'zfs holds {1}@{2}\''.format(endpoint, target, snapshot)
        return 'zsm' in Helper.run_command(command, '/', log_command=log_command)

    @staticmethod
    def hold(target, snapshot, endpoint='', log_command=False, may_exist=False):
        filter_error = 'tag already exists' if may_exist else ''
        if endpoint == '':
            command = 'zfs hold zsm {0}@{1}'.format(target, snapshot)
            Helper.run_command(command, '/', log_command=log_command, filter_error=filter_error)
        else:
            command = '{0} \'zfs hold zsm {1}@{2}\''.format(endpoint, target, snapshot)
            Helper.run_command(command, '/', log_command=log_command, filter_error=filter_error)

    @staticmethod
    def release(target, snapshot, endpoint='', log_command=False):
        if endpoint == '':
            command = 'zfs release zsm {0}@{1} || true'.format(target, snapshot)
            Helper.run_command(command, '/', log_command=log_command)
        else:
            command = '{0} \'zfs release zsm {1}@{2} || true\''.format(endpoint, target, snapshot)
            Helper.run_command(command, '/', log_command=log_command)

    @staticmethod
    def get_size(dataset, base_snapshot, last_snapshot, endpoint='', receive_resume_token='',
            buffer_size=DEFAULT_BUFFER_SIZE, compression=None, receive_mountpoint='',
            full_clone=False, all_snapshots=True,
            receive_no_mountpoint=False, receive_umount=False, receive_save=False,
            send_compression=False, send_properties=False, send_raw=False,
            log_command=False):
        """
        Executes a dry-run zfs send to calculate the size of the delta.
        """
        delta = ''
        if base_snapshot is not None:
            if (not full_clone and not all_snapshots):
                delta = '-i {0}@{1} '.format(dataset, base_snapshot)
            else:
                delta = '-I {0}@{1} '.format(dataset, base_snapshot)

        send_args = ''
        if send_compression:
            send_args += 'Lec'
        if send_raw:
            send_args += 'w'
        if not receive_resume_token:
            if send_properties:
                send_args += 'p'
            if full_clone:
                send_args += 'R'
        if send_args:
            send_args = '-' + send_args
            send_args += ' '

        # Work out zfs send command
        if receive_resume_token:
            zfs_send_cmd = 'zfs send -nv {0}-t ' + receive_resume_token
        else:
            zfs_send_cmd = 'zfs send -nv {0}{1}{2}@{3}'

        if endpoint == '':
            command = zfs_send_cmd
        else:
            command = '{4} \'' + zfs_send_cmd + '\''
        command = command.format(send_args, delta, dataset, last_snapshot, endpoint)
        command = '{0} 2>&1 | grep \'estimated size is\''.format(command)
        output = Helper.run_command(command, '/', log_command=log_command)
        size = output.strip().split(' ')[-1]
        if size[-1].isdigit():
            return '{0}B'.format(size)
        return '{0}iB'.format(size)

    @staticmethod
    def destroy(dataset, snapshot, endpoint='', log_command=False):
        """
        Destroyes a dataset
        """
        if endpoint == '':
            command = 'zfs destroy {0}@{1}'.format(dataset, snapshot)
        else:
            command = "{0} 'zfs destroy {1}@{2}'".format(endpoint, dataset, snapshot)
        Helper.run_command(command, '/', log_command=log_command)
