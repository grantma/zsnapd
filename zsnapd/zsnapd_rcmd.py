#!/usr/bin/env python3
# Copyright (c) 2018 Matthew Grant <matt@mattgrant.net.nz>
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

import os
import sys
import re

# A bit of nice stuff to set up ps output as much as we can...
try:
    from setproctitle import getproctitle
    setproctitle_support = True
except ImportError:
    setproctitle_support = False

from magcode.core.logging import setup_logging
from magcode.core.logging import reconfigure_logging
from magcode.core.logging import setup_syslog_logging
from magcode.core.logging import setup_file_logging
from magcode.core.logging import remove_daemon_stderr_logging
from magcode.core.process import BooleanCmdLineArg
from magcode.core.process import Process
from magcode.core.globals_ import *
# import this to set up config file settings etc
import zsnapd.globals_rcmd

USAGE_MESSAGE = "Usage: %s [-htv] [-c config_file]"
COMMAND_DESCRIPTION = "ZFS Snap Daemon remote command shell for sshd"


class TestingCmdLineArg(BooleanCmdLineArg):
    """
    Process testing command Line setting
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self,
                            short_arg='t',
                            long_arg='testing',
                            help_text="Test mode - exit without execing command",
                            settings_key = 'testing_arg',
                            settings_default_value = False,
                            settings_set_value = True)

class ZsnapdRCmdProcess(Process):

    def __init__(self, *args, **kwargs):
        """
        Clean up command line argument list
        """
        super().__init__(usage_message=USAGE_MESSAGE,
            command_description=COMMAND_DESCRIPTION, *args, **kwargs)
        self.cmdline_arg_list.append(TestingCmdLineArg())

    def main_process(self):
        """
        zsnapd-rcmd main process
        """
        # Configure extra logging abilities
        reconfigure_logging()
        setup_syslog_logging()
        setup_file_logging()
        remove_daemon_stderr_logging()

        # Load configuration
        rshell = settings['rshell']
        allowed_cmd_regex_dict = {
                'rcmd_zfs_get_snapshots': settings['rcmd_zfs_get_snapshots'],
                'rcmd_zfs_get_snapshots2': settings['rcmd_zfs_get_snapshots2'],
                'rcmd_zfs_get_datasets': settings['rcmd_zfs_get_datasets'],
                'rcmd_zfs_snapshot': settings['rcmd_zfs_snapshot'],
                'rcmd_zfs_replicate_push': settings['rcmd_zfs_replicate_push'],
                'rcmd_zfs_replicate_pull': settings['rcmd_zfs_replicate_pull'],
                'rcmd_zfs_replicate_pull2': settings['rcmd_zfs_replicate_pull2'],
                'rcmd_zfs_holds': settings['rcmd_zfs_holds'],
                'rcmd_zfs_is_held': settings['rcmd_zfs_is_held'],
                'rcmd_zfs_hold': settings['rcmd_zfs_hold'],
                'rcmd_zfs_release': settings['rcmd_zfs_release'],
                'rcmd_zfs_get_size': settings['rcmd_zfs_get_size'],
                'rcmd_zfs_get_size2': settings['rcmd_zfs_get_size2'],
                'rcmd_zfs_destroy': settings['rcmd_zfs_destroy'],
                'rcmd_zfs_recieve_abort': settings['rcmd_zfs_receive_abort'],
                'rcmd_zfs_get_receive_resume_token': settings['rcmd_zfs_get_receive_resume_token'],
                'rcmd_preexec': settings['rcmd_preexec'],
                'rcmd_postexec': settings['rcmd_postexec'],
                'rcmd_replicate_postexec': settings['rcmd_replicate_postexec'],
                'rcmd_aux0': settings['rcmd_aux0'],
                'rcmd_aux1': settings['rcmd_aux1'],
                'rcmd_aux2': settings['rcmd_aux2'],
                'rcmd_aux3': settings['rcmd_aux3'],
                'rcmd_aux4': settings['rcmd_aux4'],
                'rcmd_aux5': settings['rcmd_aux5'],
                'rcmd_aux6': settings['rcmd_aux6'],
                'rcmd_aux7': settings['rcmd_aux7'],
                'rcmd_aux8': settings['rcmd_aux8'],
                'rcmd_aux9': settings['rcmd_aux9'],
                }
        regex_error_flag = False
        for key in allowed_cmd_regex_dict:
            regex = allowed_cmd_regex_dict[key]
            if not regex:
                # Skip blank settings
                continue
            if (settings['regex_error_on_^'] and regex[0] != '^'):
                regex_error_flag = True
                log_error("SECURITY - {0} regex '{1}' does not begin with '^'".format(key, regex) )
            if (settings['regex_error_on_.*'] and regex.find('.*') >= 0):
                regex_error_flag = True
                log_error("SECURITY - {0} regex '{1}' contains '.*'".format(key, regex) )
            if (settings['regex_error_on_$'] and regex[-1] != '$'):
                regex_error_flag = True
                log_error("SECURITY - {0} regex '{1}' does not end with '$'".format(key, regex) )

        if regex_error_flag:
            log_error('Exiting and not processing because of bad regex(es)!')
            print('SECURITY - command rejected', file=sys.stderr)
            sys.exit(os.EX_NOPERM)

        # Process command
        try:
            orig_cmd = os.environ["SSH_ORIGINAL_COMMAND"]
            log_debug("SSH_ORIGINAL_COMMAND is: '{0}'".format(orig_cmd))
        except KeyError:
            log_error('SSH_ORIGINAL_COMMAND - environment variable not found.')
            print('SECURITY - command rejected', file=sys.stderr)
            sys.exit(os.EX_NOPERM)
        allowed = False
        for regex in allowed_cmd_regex_dict.values():
            if not regex:
                # Skip blank settings
                continue
            match = re.match(regex, orig_cmd)
            if match:
                log_debug("     MATCH: regex: '{0}'".format(regex))
                allowed = True
                break
            if debug_verbose():
                log_debug("   nomatch: regex: '{0}'".format(regex))
        if not allowed:
            log_error("Command rejected: '{0}'".format(orig_cmd))
            print('SECURITY - command rejected', file=sys.stderr)
            sys.exit(os.EX_NOPERM)

        log_info("Command accepted: '{0}'".format(orig_cmd))
        # Execute command using rshell
        argv = [rshell, '-c']
        argv.append(orig_cmd)
        env = { 'PATH': settings['rshell_path'], }
        log_debug("Execing os.execve(argv[0]={0}, argv={1}, env={2})".format(argv[0], argv, env))
        if settings['testing_arg']:
            sys.exit(os.EX_OK)
        os.execve(argv[0], argv, env)

