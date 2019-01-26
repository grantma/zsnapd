"""
Globals file for zsnapd
"""

from magcode.core.globals_ import settings

# settings for where files are
settings['config_dir'] = '/etc/zsnapd'
settings['log_dir'] = '/var/log/zsnapd'
settings['run_dir'] = '/run'
settings['config_file'] = settings['config_dir'] + '/' + 'zsnapd-rcmd.conf'

#settings['log_file'] = settings['log_dir'] \
#        + '/' + settings['process_name'] + '.log'
settings['log_file'] = ''
settings['syslog_facility'] = ''

# Defaults for zsnapd-rcmd
settings['rshell'] = '/bin/rbash'
settings['rshell_path'] = '/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin'
settings['regex_error_on_^'] = True
settings['regex_error_on_.*'] = True
settings['regex_error_on_$'] = True
settings['regex_comp_prog'] = ''
settings['regex_compress'] = ''
settings['regex_decompress'] = ''
settings['regex_dataset'] = ''
settings['regex_snapshot'] = ''
settings['regex_incr_delta'] = ''
settings['regex_mbuffer_common'] = ''
settings['regex_mbuffer_push'] = ''
settings['regex_mbuffer_pull'] = ''
settings['regex_grep_filter_dataset'] = ''
settings['rcmd_zfs_get_snapshots'] = ''
settings['rcmd_zfs_get_datasets'] = ''
settings['rcmd_zfs_snapshot'] = ''
settings['rcmd_zfs_replicate_push'] = ''
settings['rcmd_zfs_replicate_pull'] = ''
settings['rcmd_zfs_is_held'] = ''
settings['rcmd_zfs_hold'] = ''
settings['rcmd_zfs_release'] = ''
settings['rcmd_zfs_get_size'] = ''
settings['rcmd_zfs_destroy'] = ''
settings['rcmd_preexec'] = ''
settings['rcmd_postexec'] = ''
settings['rcmd_replicate_postexec'] = ''

