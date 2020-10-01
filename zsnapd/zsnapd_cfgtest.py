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
from magcode.core.globals_ import *
# import this to set up config file settings etc
import zsnapd.globals_
from zsnapd.manager import Manager
from zsnapd.config import Config

USAGE_MESSAGE = "Usage: %s [-hv] [-c config_file]"
COMMAND_DESCRIPTION = "ZFS Snap Managment Daemon configuration tester"


class ZsnapdCfgtestProcess(Process):

    def __init__(self, *args, **kwargs):
        """
        Clean up command line argument list
        """
        super().__init__(usage_message=USAGE_MESSAGE,
            command_description=COMMAND_DESCRIPTION, *args, **kwargs)

    def main_process(self):
        """
        zsnapd-cfgtest main process
        """
        # Test configuration
        ds_settings = Config.read_ds_config()
        sys.exit(os.EX_OK)
   
