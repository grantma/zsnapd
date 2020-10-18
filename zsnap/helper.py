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
Provides basic helper functionality
"""

import re
import sys
from subprocess import Popen, PIPE

from magcode.core.globals_ import debug_extreme
from magcode.core.globals_ import log_debug
from magcode.core.globals_ import log_info
from magcode.core.globals_ import log_error


class Helper(object):
    """
    Contains generic helper functionality
    """

    @staticmethod
    def run_command(command, cwd, endpoint='', log_command=False, filter_error=''):
        """
        Executes a command, returning the output. If the command fails, it raises
        """
        if endpoint == '':
            command = command
        else:
            command = "{0} '{1}'".format(endpoint, command)
        if log_command:
            log_debug("Executing command: '{0}'".format(command))
        elif debug_extreme():
            log_debug("Executing command: '{0}'".format(command))
        pattern = re.compile(r'[^\n\t@ a-zA-Z0-9_\\.:/\-]+')
        process = Popen(command, shell=True, cwd=cwd, stdout=PIPE, stderr=PIPE)
        out, err = process.communicate()
        # Clean up output
        if (sys.version_info.major >= 3):
            out = out.decode(encoding='utf-8')
            err = err.decode(encoding='utf-8')
        err = err.strip()
        return_code = process.poll()
        if return_code != 0:
            if (not filter_error or err.find(filter_error) == -1):
               raise RuntimeError('{0} failed with return value {1} and error message: {2}'.format(command, return_code, err))
        return re.sub(pattern, '', out)

