"""
Globals file for zsnapd
"""

from magcode.core.globals_ import settings

# Constants for use in program
CLEANER_REGEX = r'^((?P<keep>[0-9]+)k){0,1}((?P<hours>[0-9]+)h){0,1}(?P<days>[0-9]+)d(?P<weeks>[0-9]+)w(?P<months>[0-9]+)m(?P<years>[0-9]+)y$'
SNAPSHOTNAME_REGEX = r'^(\d{4})(1[0-2]|0[1-9])(0[1-9]|[1-2]\d|3[0-1])(([0-1]\d|2[0-3])([0-5]\d)){0,1}$'
SNAPSHOTNAME_FMTSPEC = '%Y%m%d%H%M'
TRIGGER_FILENAME = '.trigger'
DEFAULT_BUFFER_SIZE = '512M'

# settings for where files are
settings['config_dir'] = '/etc/zsnapd'
settings['log_dir'] = '/var/log/zsnapd'
settings['run_dir'] = '/run'
settings['config_file'] = settings['config_dir'] + '/' + 'process.conf'
# Zsnapd only uses one daemon
settings['pid_file'] = settings['run_dir'] + '/' + 'zsnapd.pid'
#settings['log_file'] = settings['log_dir'] \
#        + '/' + settings['process_name'] + '.log'
settings['log_file'] = ''
settings['panic_log'] = settings['log_dir'] \
        + '/' + settings['process_name'] + '-panic.log'
settings['syslog_facility'] = ''

# zsnapd.py
# Dataset config file
settings['dataset_config_file'] = settings['config_dir'] \
        + '/' + 'dataset.conf'
settings['dataset_config_dir'] = settings['config_dir'] \
        + '/' + 'dataset.conf.d'
# Template config file
settings['template_config_file'] = settings['config_dir'] \
        + '/' + 'template.conf'
settings['template_config_dir'] = settings['config_dir'] \
        + '/' + 'template.conf.d'
# Print debug mark
settings['debug_mark'] = False
# Number of seconds we wait while looping in main loop...
settings['sleep_time'] = 300 # seconds
settings['debug_sleep_time'] = 15 # seconds
settings['startup_hysteresis_time'] = 15 # seconds
settings['connect_retry_wait'] = 3 # seconds

settings['zfs_proc_not_mounts'] = ('/var/lib/lxd/devices',)
def read_proc_mounts():
    zfs_mnts = {}
    try:
        for mnt in open('/proc/self/mounts'):
            mnt = mnt.split(' ')
            if (len(mnt) < 3):
                continue
            if (mnt[2] != 'zfs'):
                continue
            if zfs_mnts.get(mnt[0], None):
                continue
            if (mnt[1].startswith(settings['zfs_proc_not_mounts'])):
                continue
            zfs_mnts[mnt[0]] = mnt[1]
    except:
        pass
    return zfs_mnts
settings['zfs_proc_mounts'] = read_proc_mounts()
 
