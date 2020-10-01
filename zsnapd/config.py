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
Processes and reads in configuration
"""

import os
import os.path
import sys
import re
import errno
import time
import configparser
from subprocess import SubprocessError

from magcode.core.globals_ import *
from magcode.core.utility import MagCodeConfigError
from magcode.core.utility import get_numeric_setting

from zsnapd.globals_ import CLEANER_REGEX
from zsnapd.globals_ import DEFAULT_BUFFER_SIZE
from zsnapd.globals_ import TRIGGER_FILENAME
from zsnapd.zfs import ZFS

TEMPLATE_KEY = r'{template}'
TRIGGER_STR = r'trigger'
TMP_STRVAL_REGEX = r'(' + TRIGGER_STR + '|' + TEMPLATE_KEY + r')'
TMP_HR_REGEX = r'([0-1]*\d|2[0-3])'
TMP_HRMIN_REGEX = TMP_HR_REGEX + r':([0-5]\d)'
TM_STRVAL_REGEX = r'^' + TMP_STRVAL_REGEX + r'$'
TM_HRMIN_REGEX = r'^' + TMP_HRMIN_REGEX + r'$'
TMP_RANGE_REGEX = TMP_HRMIN_REGEX + r'\s*-\s*' + TMP_HRMIN_REGEX + r'(\s*/\s*(' + TMP_HRMIN_REGEX + r'|' + TMP_HR_REGEX + r')){0,1}'
TM_RANGE_REGEX = r'^' + TMP_RANGE_REGEX + r'$'
TMP_HRMINSTRVAL_REGEX = r'(' + TMP_STRVAL_REGEX + r'|' + TMP_HRMIN_REGEX + r')'
TM_HRMINSTRVAL_REGEX = r'^' + TMP_HRMINSTRVAL_REGEX + r'$'
TMP_HRMINRANGESTRVAL_REGEX = r'(' + TMP_STRVAL_REGEX + r'|' + TMP_HRMIN_REGEX + r'|' + TMP_RANGE_REGEX + r')'
TM_HRMINRANGESTRVAL_REGEX = r'^' + TMP_HRMINRANGESTRVAL_REGEX + r'$'
TMP_HRMINCOMMA_REGEX = r'(' + TMP_HRMIN_REGEX + r'\s*,\s*){1,}' + TMP_HRMIN_REGEX
TM_HRMINCOMMA_REGEX  = r'^' + TMP_HRMINCOMMA_REGEX + r'$'
TMP_HRMINRANGESTRVALCOMMA_REGEX = r'(' + TMP_HRMINRANGESTRVAL_REGEX + r'\s*,\s*){1,}' + TMP_HRMINRANGESTRVAL_REGEX
TM_HRMINRANGESTRVALCOMMA_REGEX  = r'^' + TMP_HRMINRANGESTRVALCOMMA_REGEX + r'$'

ds_name_syntax = r'^[-_:.a-zA-Z0-9][-_:./a-zA-Z0-9]*$'
ds_name_reserved_regex = r'^(log|DEFAULT|(c[0-9]|log/|mirror|raidz|raidz1|raidz2|raidz3|spare).*)$'
template_name_syntax = r'^[a-zA-Z0-9][-_:.a-zA-Z0-9]*$'
BOOLEAN_REGEX = r'^([tT]rue|[fF]alse|[oO]n|[oO]ff|0|1)$'
PATH_REGEX = r'[-_./ ~a-zA-Z0-9]+'
MOUNTPOINT_REGEX = r'^(None|legacy|/|/' + PATH_REGEX + r')$'
SHELLCMD_REGEX = r'^[-_./~a-zA-Z0-9 	:@|=$"' + r"'" + r']+$'
SHELLFORMAT_REGEX = r'^[-_./~a-zA-Z0-9 	:@|{}]+$'
NETCMD_REGEX = r'^[-_./~a-zA-Z0-9 	:@|]*$'
HOST_REGEX = r'^[0-9a-zA-Z\[][-_.:a-zA-Z0-9\]]*$'
PORT_REGEX = r'^[0-9]{1,5}$'
USER_REGEX = r'^[a-zA-Z][-_.a-zA-Z0-9]*$'
BUFFER_SIZE_REGEX = r'[0-9]{1,12}[kMG]'
ds_syntax_dict = {'snapshot': BOOLEAN_REGEX,
        'replicate': BOOLEAN_REGEX,
        'time': None,
        'mountpoint': MOUNTPOINT_REGEX,
        'do_trigger': BOOLEAN_REGEX,
        'preexec': SHELLCMD_REGEX,
        'postexec': SHELLCMD_REGEX,
        'log_commands': BOOLEAN_REGEX,
        'replicate_all': BOOLEAN_REGEX,
        'all_snapshots': BOOLEAN_REGEX,
        'replicate_append_basename': BOOLEAN_REGEX,
        'replicate_append_fullname': BOOLEAN_REGEX,
        'replicate_full_clone': BOOLEAN_REGEX,
        'replicate_receive_save': BOOLEAN_REGEX,
        'replicate_receive_no_mountpoint': BOOLEAN_REGEX,
        'replicate_receive_mountpoint': MOUNTPOINT_REGEX,
        'replicate_receive_umount': BOOLEAN_REGEX,
        'replicate_send_compression': BOOLEAN_REGEX,
        'replicate_send_properties': BOOLEAN_REGEX,
        'replicate_send_raw': BOOLEAN_REGEX,
        'replicate_postexec': SHELLCMD_REGEX,
        'replicate_target': ds_name_syntax,
        'replicate_source': ds_name_syntax,
        'replicate_endpoint': NETCMD_REGEX,
        'replicate_endpoint_host': HOST_REGEX,
        'replicate_endpoint_port': PORT_REGEX,
        'replicate_endpoint_command': SHELLFORMAT_REGEX,
        'replicate2_append_fullname': BOOLEAN_REGEX,
        'replicate2_append_basename': BOOLEAN_REGEX,
        'replicate2_full_clone': BOOLEAN_REGEX,
        'replicate2_receive_save': BOOLEAN_REGEX,
        'replicate2_receive_no_mountpoint': BOOLEAN_REGEX,
        'replicate2_receive_mountpoint': MOUNTPOINT_REGEX,
        'replicate2_receive_umount': BOOLEAN_REGEX,
        'replicate2_send_compression': BOOLEAN_REGEX,
        'replicate2_send_properties': BOOLEAN_REGEX,
        'replicate2_send_raw': BOOLEAN_REGEX,
        'replicate2_target': ds_name_syntax,
        'replicate2_endpoint': NETCMD_REGEX,
        'replicate2_endpoint_host': HOST_REGEX,
        'replicate2_endpoint_port': PORT_REGEX,
        'replicate2_endpoint_command': SHELLFORMAT_REGEX,
        'buffer_size': BUFFER_SIZE_REGEX,
        'compression': PATH_REGEX,
        'compression2': PATH_REGEX,
        'schema': CLEANER_REGEX,
        'local_schema': CLEANER_REGEX,
        'remote_schema': CLEANER_REGEX,
        'remote2_schema': CLEANER_REGEX,
        'clean_all': BOOLEAN_REGEX,
        'local_clean_all': BOOLEAN_REGEX,
        'remote_clean_all': BOOLEAN_REGEX,
        'remote2_clean_all': BOOLEAN_REGEX,
        'template': template_name_syntax,
        }
DEFAULT_ENDPOINT_PORT = 22
DEFAULT_ENDPOINT_CMD = 'ssh -p {port} {host}'
DATE_SPEC = '%Y%m%d '
ZFS_MOUNTPOINT_NONE = ('legacy', 'none')


def _check_time_syntax(section_name, item, time_spec, checking_template=False):
    """
    Function called to check time spec syntax
    """
    if (',' in time_spec):
        if (re.match(TM_HRMINRANGESTRVALCOMMA_REGEX, time_spec) is None):
            log_error("[{0}] {1} - value '{2}' invalid. Must be of form 'HH:MM, HH:MM, HH:MM-HH:MM/[HH:MM|HH|H], {3}, {4}, ...'."
                    .format(section_name, item, time_spec, TEMPLATE_KEY, TRIGGER_STR))
            return False
    else:
        if (re.match(TM_HRMINRANGESTRVAL_REGEX, time_spec) is None):
            log_error("[{0}] {1} - value '{2}' invalid. Must be of form 'HH:MM', 'HH:MM-HH:MM/[HH:MM|HH|H]', '{3}' or '{4}'."
                    .format(section_name, item, time_spec, TEMPLATE_KEY, TRIGGER_STR))
            return False
    if time_spec.find(TEMPLATE_KEY) != -1:
        if checking_template:
            log_error("[{0}] {1} - value '{2}' invalid. Templates can't have '{3}' as part of the time specifier."
                    .format(section_name, item, time_spec, TEMPLATE_KEY))
            return False
        else:
            lfind = time_spec.find(TEMPLATE_KEY)
            rfind = time_spec.rfind(TEMPLATE_KEY)
            if lfind != rfind:
                log_error("[{0}] {1} - value '{2}' invalid. More than one '{3}' found.".format(section_name, item, time_spec, TEMPLATE_KEY))
                return False
    return True

ds_syntax_dict['time'] = _check_time_syntax

class MeterTime(object):
    """
    Manages the passing of time on a daily cycle, and the parsing of 
    time strings for that cycle
    """

    def __init__(self, dataset='', time_spec='', mountpoint=''):
        """
        Initialise class
        """
        hysteresis_time = int(get_numeric_setting('startup_hysteresis_time', float))
        self.prev_secs = int(time.time()) - hysteresis_time
        self.dataset = dataset
        self.mountpoint = mountpoint
        self.time_spec = time_spec
        self.date = self._midnight_date()
        # Do this before calling _parse_timespec(), as that routine sets it!
        self.trigger_flag = False
        self.time_list = self._parse_timespec(self.time_spec) if self.time_spec else []

    def __repr__(self):
        return '{0}'.format(self.time_spec)

    def __iter__(self):
        yield from self.time_list

    def __call__(self, time_spec, section_name, item):
        return (self._parse_timespec(time_spec, section_name, item, syntax_check=True))

    def _midnight_date(self):
        date = time.strftime(DATE_SPEC, time.localtime())
        return(int(time.mktime(time.strptime(date + '00:00', DATE_SPEC + '%H:%M'))))

    def _parse_timespec(self, time_spec, section_name=None, item=None, syntax_check=False):
        """
        Parse a time spec
        """
        def parse_hrmin(time_spec):
            return(int(time.mktime(time.strptime(date + time_spec, DATE_SPEC + '%H:%M'))))

        def parse_range(time_spec):
            tm_list = []
            parse = time_spec.split('-')
            if ('/' in parse[1]):
                parse = [parse[0]] + parse[1].split('/')
            parse = [ts.strip() for ts in parse]
            tm_start = parse_hrmin(parse[0])
            tm_stop = parse_hrmin(parse[1])
            if (tm_stop < tm_start):
                if (section_name and item):
                    log_error("[{0}] {1} - '{2}' - '{3}' before '{4}', should be after."
                            .format(section_name, item, time_spec, parse[1], parse[0]))
                parse_flag = False
                return([])
            if (len(parse) > 2):
                int_parse = parse[2]
                if ( ':' in int_parse):
                    int_parse = int_parse.split(':')
                    tm_int = int(int_parse[0]) * 3600 + int(int_parse[1]) * 60
                else:
                    tm_int = int(int_parse) * 3600
            else:
                tm_int = 3600
            tm_next = tm_start
            while (tm_next < tm_stop):
                tm_list.append(tm_next)
                tm_next += tm_int
            tm_list.append(tm_stop)
            return(tm_list)

        def parse_spec(time_spec):
            if (time_spec == TRIGGER_STR):
                self.trigger_flag = True
                if syntax_check:
                    return[1,]
                return([])
            if (time_spec == TEMPLATE_KEY):
                if syntax_check:
                    return([1,])
                return([])
            if re.match(TM_HRMIN_REGEX, time_spec):
                return ([parse_hrmin(time_spec)])
            if re.match(TM_RANGE_REGEX, time_spec):
                return(parse_range(time_spec))
            raise Exception('Parsing time specs, should not have got here!')

        parse_flag = True
        date = time.strftime(DATE_SPEC, time.localtime())
        time_list = []
        spec_list = time_spec.split(',')
        spec_list = [ts.strip() for ts in spec_list]
        for ts in spec_list:
            time_list = time_list + parse_spec(ts)
        time_list.sort()
        if parse_flag:
            return(time_list)
        else:
            return([])

    def is_trigger(self):
        return self.trigger_flag

    def do_run(self, now):
        """
        Check if time has passed for a dataset, or for a .trigger file
        """
        # Reinitialise time_list
        now_date = self._midnight_date()
        if (now_date > self.date):
            # Now a new day, reinitialise time_list
            self.date = now_date
            self.time_list = self._parse_timespec(self.time_spec) if self.time_spec else []
        # Trigger file
        if self.is_trigger():
            # We wait until we find a trigger file in the filesystem
            trigger_filename = '{0}/{1}'.format(self.mountpoint, TRIGGER_FILENAME)
            if os.path.exists(trigger_filename):
                log_info("[{0}] - trigger file '{1}' found".format(self.dataset, trigger_filename))
                os.remove(trigger_filename)
                self.prev_secs = now
                return True
        # Check for Time passed
        prev_secs = self.prev_secs
        for inst in self.time_list:
            if ( prev_secs < inst <= now):
                log_info('[{0}] - time passed has passed'.format(self.dataset))
                self.prev_secs = now
                return True
        self.prev_secs = now
        return False

class Config(object):
    @staticmethod
    def _check_section_syntax(section, section_name, checking_template=False):
        result = True
        for item in section.keys():
            try:
                value_syntax = ds_syntax_dict[item]
            except KeyError as ex:
                log_error("[{0}] - item '{1}' is not a valid dataset keyword.".format(section_name, item))
                result = False
                continue
            if (not ds_syntax_dict[item]):
                continue
            value = section[item]
            if type(ds_syntax_dict[item]) == type(_check_time_syntax):
                if not ds_syntax_dict[item](section_name, item, value, checking_template):
                    result = False
                continue
            if (not re.match(ds_syntax_dict[item], value)):
                log_error("[{0}] {1} - value '{2}' invalid. Must match regex '{3}'.".format(section_name, item, value, ds_syntax_dict[item]))
                result = False
            if item in ('replicate_source', 'replicate_target'):
                if re.match(ds_name_reserved_regex, value):
                    log_error("[{0}] {1} - value '{2}' invalid. Must not start with a ZFS reserved keyword.".format(section_name, item, value))
                    result = False
        return result
    
    @staticmethod
    def _check_template_syntax(template_config):
        """
        Checks the syntax of the template file
        """
        result = True
        # Check syntax of DEFAULT section
        if not Config._check_section_syntax(template_config.defaults(), 'DEFAULT'):
            result = False
        for template in template_config.sections():
            # Check name syntax of each dataset group
            if not re.match(template_name_syntax, template):
                log_error("Template name '{0}' is invalid.".format(template))
                result = False
            # Check syntax of each dataset group 
            if not Config._check_section_syntax(template_config[template], template,
                    checking_template=True):
                result = False
        return result

    @staticmethod
    def _check_dataset_syntax (ds_config):
        """
        Checks the dataset syntax of read in items
        """
        result = True
        for dataset in ds_config.sections():
            if (not re.match(ds_name_syntax, dataset)
                    or re.match(ds_name_reserved_regex, dataset)):
                log_error("Dataset name '{0}' is invalid.".format(dataset))
                result = False
            if not Config._check_section_syntax(ds_config[dataset], dataset):
                result = False
            if (ds_config.has_option(dataset, 'replicate_endpoint_host') or ds_config.has_option(dataset, 'replicate_endpoint')):
                if (not ds_config.has_option(dataset, 'replicate_target') and not ds_config.has_option('replicate_source')):
                    log_error("Dataset '{0}' is configured for replication but no replicate_source or replicate_target is specified.".format(dataset))
                    result = False
        return result

    @staticmethod
    def read_ds_config():
        """
        Read dataset configuration
        """
        def read_config(filename, dirname=None, default_dict=None):
            file_ = open(filename)
            config = configparser.ConfigParser()
            if default_dict:
                config.read_dict(default_dict)
            config.read_file(file_)
            if dirname:
                for root, dirs, files in os.walk(dirname):
                    file_list = [os.path.join(root, name) for name in files]
                config.read(file_list)
            file_.close()
            return config

        def check_ds_config_clash(setting_name1, setting_name2, fallback1=False, fallback2=False):
            nonlocal invalid_config
            try:
                setting1 =  ds_config.get(dataset, setting_name1)
                setting1_set = True
            except configparser.NoOptionError:
                setting1 = fallback1
                setting1_set = False
            try:
                setting2 = ds_config.get(dataset, setting_name2)
                setting2_set = True
            except configparser.NoOptionError:
                setting2 = fallback2
                setting2_set = False
            if ((setting1_set and setting1) and (setting2_set and setting2)):
                log_error("[{0}] - '{1}' and '{2}' can't be set at the same time.".format(dataset, setting_name1, setting_name2))
                invalid_config = True
            return (setting1, setting2)

        ds_settings = {}
        ds_dict = {}
        template_dict = {}
        try:
            template_filename = settings['template_config_file']
            template_dirname = settings['template_config_dir']
            template_config = read_config(template_filename, template_dirname)
            if not Config._check_template_syntax(template_config):
                raise MagCodeConfigError("Invalid dataset syntax in config file/dir '{0}' or '{1}'"
                        .format(template_filename, template_dirname))

            def get_sect_dict(config, section):
                res_dict = {}
                for item in config[section]:
                    if item in ('snapshot', ):
                        res_dict[item] = config.getboolean(section, item)
                    else:
                        res_dict[item] = config.get(section, item)
                return res_dict

            template_dict = {template_section:get_sect_dict(template_config, template_section) for template_section in template_config.sections()}
            
            ds_filename = settings['dataset_config_file']
            ds_dirname = settings['dataset_config_dir']
            ds_config = read_config(ds_filename, ds_dirname)
            invalid_config = not bool(Config._check_dataset_syntax(ds_config))
            if invalid_config:
                raise MagCodeConfigError("Invalid dataset syntax in config file/dir '{0}' or '{1}'"
                        .format(ds_filename, ds_dirname))

            # Assemble default ds_dict
            ds_dict = {}
            for ds in ds_config.sections():
                ds_template = ds_config.get(ds, 'template', fallback=None)
                if (ds_template and ds_template in template_dict):
                    ds_dict[ds] = template_dict.get(ds_template, None)

            # Destroy ds_config and re read it
            del ds_config
            ds_config = read_config(ds_filename, ds_dirname, ds_dict)
            datasets = ZFS.get_datasets()
            for dataset in ds_config.sections():
                # Calculate mountpoint
                zfs_mountpoint = None
                if dataset in datasets:
                    zfs_mountpoint = settings['zfs_proc_mounts'].get(dataset, None)
                    zfs_mountpoint = zfs_mountpoint if zfs_mountpoint not in ZFS_MOUNTPOINT_NONE else None
                mountpoint = ds_config.get(dataset, 'mountpoint', fallback=zfs_mountpoint)
                # Work out time_spec
                time_spec = ds_config.get(dataset, 'time')
                if time_spec.find(TEMPLATE_KEY) != -1:
                    try:
                        time_spec = time_spec.replace(TEMPLATE_KEY, ds_dict[dataset]['time'])
                    except KeyError:
                        log_error("[{0}] - template section or template time setting does not exist.".format(dataset))
                        invalid_config = True
                        continue
                test_time = MeterTime()
                if not test_time(time_spec, dataset, 'time'):
                    del test_time
                    invalid_config = True
                    continue
                del test_time

                # Deal with deprecated settings
                old_setting_repl_all = ds_config.getboolean(dataset, 'replicate_all', fallback=True)
                ds_settings[dataset] = {'mountpoint': mountpoint,
                                     'time': MeterTime(dataset, time_spec, mountpoint),
                                     'all_snapshots': ds_config.getboolean(dataset, 'all_snapshots',
                                         fallback=old_setting_repl_all),
                                     'snapshot': ds_config.getboolean(dataset, 'snapshot'),
                                     'do_trigger': ds_config.getboolean(dataset, 'do_trigger', fallback=False),
                                     'replicate': None,
                                     'replicate2': None,
                                     'schema': ds_config.get(dataset, 'schema'),
                                     'local_schema': ds_config.get(dataset, 'local_schema', fallback=None),
                                     'remote_schema': ds_config.get(dataset, 'remote_schema', fallback=None),
                                     'remote2_schema': ds_config.get(dataset, 'remote2_schema', fallback=None),
                                     'clean_all': ds_config.get(dataset, 'clean_all', fallback=False),
                                     'local_clean_all': ds_config.get(dataset, 'local_clean_all', fallback=None),
                                     'remote_clean_all': ds_config.get(dataset, 'remote_clean_all', fallback=None),
                                     'remote2_clean_all': ds_config.get(dataset, 'remote2_clean_all', fallback=None),
                                     'preexec': ds_config.get(dataset, 'preexec', fallback=None),
                                     'postexec': ds_config.get(dataset, 'postexec', fallback=None),
                                     'replicate_postexec': ds_config.get(dataset, 'replicate_postexec', fallback=None),
                                     'log_commands': ds_config.getboolean(dataset, 'log_commands', fallback=False)}
                if (ds_settings[dataset]['local_schema'] is None):
                    ds_settings[dataset]['local_schema'] = ds_settings[dataset]['schema']
                if (ds_settings[dataset]['local_clean_all'] is None):
                    ds_settings[dataset]['local_clean_all'] = ds_settings[dataset]['clean_all']
                if (ds_settings[dataset]['remote_clean_all'] is None):
                    ds_settings[dataset]['remote_clean_all'] = ds_settings[dataset]['clean_all']
                if (ds_settings[dataset]['remote2_clean_all'] is None):
                    ds_settings[dataset]['remote2_clean_all'] = ds_settings[dataset]['clean_all']
                if ((ds_config.has_option(dataset, 'replicate_endpoint_host') or ds_config.has_option(dataset, 'replicate_endpoint'))
                        and (ds_config.has_option(dataset, 'replicate_target') or ds_config.has_option(dataset, 'replicate_source'))):
                    host = ds_config.get(dataset, 'replicate_endpoint_host', fallback='')
                    port = ds_config.get(dataset, 'replicate_endpoint_port', fallback=DEFAULT_ENDPOINT_PORT)
                    if ds_config.has_option(dataset, 'replicate_endpoint_host'):
                        command = ds_config.get(dataset, 'replicate_endpoint_command', fallback=DEFAULT_ENDPOINT_CMD)
                        if host:
                            endpoint = command.format(port=port, host=host)
                        else:
                            endpoint = ''
                    else:
                        endpoint = ds_config.get(dataset, 'replicate_endpoint')
                    full_clone = ds_config.getboolean(dataset, 'replicate_full_clone', fallback=False)
                    send_properties = ds_config.getboolean(dataset, 'replicate_send_properties', fallback=False)
                    append_basename, append_fullname = check_ds_config_clash('replicate_append_basename', 'replicate_append_fullname')
                    receive_no_mountpoint, receive_mountpoint = check_ds_config_clash('replicate_receive_no_mountpoint', 'replicate_receive_mountpoint', 
                                                                        fallback1=(full_clone or send_properties), fallback2='')
                    if (receive_no_mountpoint and receive_mountpoint):
                        # Setting a receive_mountpoint overrides a full_clone receive_no_mountpoint
                        receive_no_mountpoint = False

                    append_name = ''
                    if (append_fullname and dataset.find('/') != -1):
                        append_name = dataset[dataset.find('/'):]
                    if (append_basename and dataset.rfind('/') != -1):
                        append_name = dataset[dataset.rfind('/'):]
                    receive_mountpoint = str(receive_mountpoint) + append_name
                    target = ds_config.get(dataset, 'replicate_target', fallback=None)
                    if target:
                        target += append_name

                    ds_settings[dataset]['replicate'] = {'endpoint': endpoint,
                                                      'target': target,
                                                      'source': ds_config.get(dataset, 'replicate_source', fallback=None),
                                                      'all_snapshots': ds_config.getboolean(dataset, 'all_snapshots',
                                                            fallback=old_setting_repl_all),
                                                      'compression': ds_config.get(dataset, 'compression', fallback=None),
                                                      'full_clone': full_clone,
                                                      'receive_save': ds_config.getboolean(dataset, 'replicate_receive_save', fallback=False),
                                                      'receive_no_mountpoint': receive_no_mountpoint,
                                                      'receive_mountpoint': receive_mountpoint,
                                                      'receive_umount': ds_config.getboolean(dataset, 'replicate_receive_umount',
                                                          fallback=(full_clone or send_properties)),
                                                      'send_compression': ds_config.getboolean(dataset, 'replicate_send_compression', fallback=False),
                                                      'send_properties': send_properties,
                                                      'send_raw': ds_config.getboolean(dataset, 'replicate_send_raw', fallback=False),
                                                      'buffer_size': ds_config.get(dataset, 'buffer_size', fallback=DEFAULT_BUFFER_SIZE),
                                                      'log_commands': ds_config.getboolean(dataset, 'log_commands', fallback=False),
                                                      'endpoint_host': host,
                                                      'endpoint_port': port}

                if ((ds_config.has_option(dataset, 'replicate2_endpoint_host') or ds_config.has_option(dataset, 'replicate2_endpoint'))
                        and (ds_config.has_option(dataset, 'replicate2_target'))):
                    host = ds_config.get(dataset, 'replicate2_endpoint_host', fallback='')
                    port = ds_config.get(dataset, 'replicate2_endpoint_port', fallback=DEFAULT_ENDPOINT_PORT)
                    if ds_config.has_option(dataset, 'replicate2_endpoint_host'):
                        command = ds_config.get(dataset, 'replicate2_endpoint_command', fallback=ds_config.get(dataset, 'replicate_endpoint_command', fallback=DEFAULT_ENDPOINT_CMD))
                        if host:
                            endpoint = command.format(port=port, host=host)
                        else:
                            endpoint = ''
                    else:
                        endpoint = ds_config.get(dataset, 'replicate2_endpoint')
                    full_clone = ds_config.getboolean(dataset, 'replicate2_full_clone', fallback=False)
                    send_properties = ds_config.getboolean(dataset, 'replicate2_send_properties', fallback=False)
                    append_basename, append_fullname = check_ds_config_clash('replicate2_append_basename', 'replicate2_append_fullname')
                    receive_no_mountpoint, receive_mountpoint = check_ds_config_clash('replicate2_receive_no_mountpoint', 'replicate2_receive_mountpoint', 
                                                                        fallback1=(full_clone or send_properties), fallback2='')
                    if (receive_no_mountpoint and receive_mountpoint):
                        # Setting a receive_mountpoint overrides a full_clone receive_no_mountpoint
                        receive_no_mountpoint = False

                    append_name = ''
                    if (append_fullname and dataset.find('/') != -1):
                        append_name = dataset[dataset.find('/'):]
                    if (append_basename and dataset.rfind('/') != -1):
                        append_name = dataset[dataset.rfind('/'):]
                    receive_mountpoint = str(receive_mountpoint) + append_name
                    target = ds_config.get(dataset, 'replicate2_target', fallback=None)
                    if target:
                        target += append_name

                    ds_settings[dataset]['replicate2'] = {'endpoint': endpoint,
                                                      'target': target,
                                                      'source': None,
                                                      'all_snapshots': ds_config.getboolean(dataset, 'all_snapshots',
                                                            fallback=old_setting_repl_all),
                                                      'compression': ds_config.get(dataset, 'compression2', fallback=None),
                                                      'full_clone': full_clone,
                                                      'append_basename': ds_config.get(dataset, 'replicate2_append_basename', fallback=False),
                                                      'append_fullname': ds_config.get(dataset, 'replicate2_append_fullname', fallback=False),
                                                      'receive_save': ds_config.getboolean(dataset, 'replicate2_receive_save', fallback=False),
                                                      'receive_no_mountpoint': receive_no_mountpoint,
                                                      'receive_mountpoint': receive_mountpoint,
                                                      'receive_umount': ds_config.getboolean(dataset, 'replicate2_receive_umount',
                                                          fallback=(full_clone or send_properties)),
                                                      'send_compression': ds_config.getboolean(dataset, 'replicate2_send_compression', fallback=False),
                                                      'send_properties': send_properties,
                                                      'send_raw': ds_config.getboolean(dataset, 'replicate2_send_raw', fallback=False),
                                                      'buffer_size': ds_config.get(dataset, 'buffer2_size', fallback=DEFAULT_BUFFER_SIZE),
                                                      'log_commands': ds_config.getboolean(dataset, 'log_commands', fallback=False),
                                                      'endpoint_host': host,
                                                      'endpoint_port': port}

            if invalid_config:
                raise MagCodeConfigError("Invalid dataset syntax in config file/dir '{0}', '{1}', '{2}', or '{3}'"
                        .format(template_filename, template_dirname, ds_filename, ds_dirname))
       
        # Handle file opening and read errors
        except (IOError,OSError) as e:
            log_error('Exception while parsing configuration file: {0}'.format(str(e)))
            if (e.errno == errno.EPERM or e.errno == errno.EACCES):
                systemd_exit(os.EX_NOPERM, SDEX_NOPERM)
            else:
                systemd_exit(os.EX_IOERR, SDEX_GENERIC)

        # Handle all configuration file parsing errors
        except configparser.Error as e:
            log_error('Exception while parsing configuration file: {0}'.format(str(e)))
            systemd_exit(os.EX_CONFIG, SDEX_CONFIG)
        
        except MagCodeConfigError as e:
            log_error(str(e))
            systemd_exit(os.EX_CONFIG, SDEX_CONFIG)

        # Handle errors running zfs list -pH etc
        except (RuntimeError, SubprocessError) as e:
            log_error(str(e))
            systemd_exit(os.EX_SOFTWARE, SDEX_GENERIC)

        return ds_settings


