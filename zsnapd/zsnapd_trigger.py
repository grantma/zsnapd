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

# A bit of nice stuff to set up ps output as much as we can...
try:
    from setproctitle import getproctitle
    setproctitle_support = True
except ImportError:
    setproctitle_support = False

from magcode.core.process import Process
from magcode.core.process import BooleanCmdLineArg
from magcode.core.globals_ import *
# import this to set up config file settings etc
import zsnapd.globals_
from zsnapd.manager import Manager
from zsnapd.config import Config

USAGE_MESSAGE = "Usage: %s [-hrv] [-c config_file] [mnt-point-or-dataset, mnt-point-or-dataset, ...]"
COMMAND_DESCRIPTION = "ZFS Snap Daemon trigger utility"


class ReachableCmdLineArg(BooleanCmdLineArg):
    """
    Process reachable endpoint flag
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self,
                            short_arg='r',
                            long_arg='reachable',
                            help_text="Test if replication endpoint can be TCP connected to",
                            settings_key = 'reachable_arg',
                            settings_default_value = False,
                            settings_set_value = True)

class DoTriggerCmdLineArg(BooleanCmdLineArg):
    """
    Process do_trigger trigger candidate flag
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self,
                            short_arg='t',
                            long_arg='do-trigger',
                            help_text="Create do_trigger flagged triggers for datasets",
                            settings_key = 'do_trigger_arg',
                            settings_default_value = False,
                            settings_set_value = True)

class ZsnapdTriggerProcess(Process):

    def __init__(self, *args, **kwargs):
        """
        Clean up command line argument list
        """
        super().__init__(usage_message=USAGE_MESSAGE,
            command_description=COMMAND_DESCRIPTION, *args, **kwargs)
        self.cmdline_arg_list.append(DoTriggerCmdLineArg())
        self.cmdline_arg_list.append(ReachableCmdLineArg())

    def parse_argv_left(self, argv_left):
        """
        Handle any arguments left after processing all switches
        """
        self.argv_left = []
        if (len(argv_left) != 0):
            self.argv_left = argv_left

    def main_process(self):
        """
        zsnapd-trigger main process
        """
        self.check_if_root()
        # Read configuration
        ds_settings = Config.read_ds_config()
        # Process triggers
        if not(Manager.touch_trigger(ds_settings, 
            settings['reachable_arg'], settings['do_trigger_arg'], *self.argv_left)):
            sys.exit(os.EX_CONFIG)
        sys.exit(os.EX_OK)
   
