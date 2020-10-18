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
Provides functionality for cleaning up old ZFS snapshots
"""

import re
import time
from datetime import datetime
from collections import OrderedDict

from magcode.core.globals_ import log_info
from magcode.core.globals_ import log_debug
from magcode.core.globals_ import log_error

from zsnap.zfs import ZFS
from zsnap.globals_ import CLEANER_REGEX
from zsnap.globals_ import SNAPSHOTNAME_REGEX

class Cleaner(object):
    """
    Cleaner class, containing all methods for cleaning up ZFS snapshots
    """

    logger = None  # The manager will fill this object

    @staticmethod
    def clean(dataset, snapshots, schema, endpoint='', local_dataset='', all_snapshots=False, return_no_keep=True, log_command=False):
        local_dataset = local_dataset if local_dataset else dataset
        now = time.localtime()
        midnight = time.mktime(time.strptime('{0}-{1}-{2}'.format(now.tm_year, now.tm_mon, now.tm_mday) , '%Y-%m-%d'))

        # Parsing schema
        match = re.match(CLEANER_REGEX, schema)
        if not match:
            log_info('[{0}] - Got invalid schema for dataset {0}: {1}'.format(local_dataset, dataset, schema))
            return
        matchinfo = match.groupdict()
        settings = {}
        for key in list(matchinfo.keys()):
            settings[key] = int(matchinfo[key] if matchinfo[key] is not None else 0)
        settings['keep'] = settings.get('keep', 0) 
        base_time = midnight - settings['keep']*86400

        # Loading snapshots
        snapshot_list = []
        for snapshot in snapshots:
            snapshotname = snapshots[snapshot]['name']
            if (not all_snapshots and re.match(SNAPSHOTNAME_REGEX, snapshotname) is None):
                # If required, only clean zsnapd snapshots
                continue
            held = False
            if ZFS.is_held(dataset, snapshotname, endpoint, log_command=log_command):
                log_debug('[{0}]   - Keeping {1}@{2} - held snapshot'
                        .format(local_dataset, dataset, snapshotname))
                held = True
            snapshot_ctime = snapshots[snapshot]['creation']
            snapshot_age = (base_time - snapshot_ctime)/3600
            snapshot_age = int(snapshot_age) if snapshot_age >= 0 else -1
            snapshot_list.append({'name': snapshotname,
                                  'handle': snapshot,
                                  'time': datetime.fromtimestamp(snapshot_ctime),
                                  'age': snapshot_age,
                                  'held': held})

        buckets = {}
        counter = -1
        for i in range(settings['hours']):
            counter += 1
            buckets[counter] = []
        for i in range(settings['days']):
            counter += (1 * 24)
            buckets[counter] = []
        for i in range(settings['weeks']):
            counter += (7 * 24)
            buckets[counter] = []
        for i in range(settings['months']):
            counter += (30 * 24)
            buckets[counter] = []
        for i in range(settings['years']):
            counter += (30 * 12 * 24)
            buckets[counter] = []

        will_delete = False
        end_of_life_snapshots = []
        kept_flag = False
        for snapshot in snapshot_list:
            if snapshot['age'] <= 0:
                log_debug('[{0}]   - Ignoring and keeping {1}@{2} - too fresh'
                        .format(local_dataset, dataset, snapshot['name']))
                kept_flag = True
                continue
            possible_keys = []
            for key in buckets:
                if snapshot['age'] <= key:
                    possible_keys.append(key)
            if possible_keys:
                buckets[min(possible_keys)].append(snapshot)
            else:
                will_delete = True
                end_of_life_snapshots.append(snapshot)

        # Return from procedure if no scripts found to keep
        if (return_no_keep and not kept_flag):
            return

        to_delete = {}
        to_keep = {}
        for key in buckets:
            oldest = None
            if len(buckets[key]) == 1:
                oldest = buckets[key][0]
            else:
                for snapshot in buckets[key]:
                    if oldest is None:
                        oldest = snapshot
                    elif snapshot['age'] > oldest['age']:
                        oldest = snapshot
                    else:
                        will_delete = True
                        to_delete[key] = to_delete.get(key, []) + [snapshot]
            to_keep[key] = oldest
            to_delete[key] = to_delete.get(key, [])

        if will_delete is True:
            log_info('[{0}] - Cleaning {1}'.format(local_dataset, dataset))

        keys = list(to_delete.keys())
        keys.sort()
        for key in keys:
            for snapshot in to_delete[key]:
                if snapshot['held']:
                    log_info('[{0}] -   Skipping held {1}@{2}'.format(local_dataset, dataset, snapshot['name']))
                    continue
                log_info('[{0}] -   Destroying {1}@{2}'.format(local_dataset, dataset, snapshot['name']))
                ZFS.destroy(dataset, snapshot['name'], endpoint, log_command=log_command)
                snapshots.pop(snapshot['handle'])
        for snapshot in end_of_life_snapshots:
            if snapshot['held']:
                log_info('[{0}] -   Skipping held {1}@{2}'.format(local_dataset, dataset, snapshot['name']))
                continue
            log_info('[{0}] -   Destroying {1}@{2}'.format(local_dataset, dataset, snapshot['name']))
            ZFS.destroy(dataset, snapshot['name'], endpoint, log_command=log_command)
            snapshots.pop(snapshot['handle'])

        if will_delete is True:
            log_info('[{0}] - Cleaning {1} complete'.format(local_dataset, dataset))
