from oslo_config import cfg


# 读取config的信息
CONF = cfg.CONF

# 配置目录
CONF(args=[], default_config_files = ['/etc/dingo-command/dingo-command.conf'])

default_group = cfg.OptGroup(name='DEFAULT', title='default conf data')

default_opts = [
    cfg.StrOpt('vip', default=None, help='the openstack vip'),
    cfg.StrOpt('my_ip', default=None, help='the openstack host ip'),
    cfg.StrOpt('transport_url', default=None, help='the openstack rabbit mq url'),
    cfg.StrOpt('center_transport_url', default=None, help='the region one openstack rabbit mq url'),
    cfg.BoolOpt('center_region_flag', default=False, help='the region is center region'),
    cfg.StrOpt('region_name', default=None, help='the openstack region name'),
    cfg.StrOpt('cluster_work_dir', default='/var/lib/dingo-command', help='the openstack region name'),
    cfg.StrOpt('auth_url', default=None, help='the openstack region name'),
    cfg.StrOpt('k8s_master_image', default=None, help='the master image id'),
    cfg.StrOpt('k8s_master_flavor', default=None, help='the master flavor name'),
    cfg.StrOpt('chart_harbor_url', default=None, help='the url of harbor registry'),
    cfg.StrOpt('chart_harbor_user', default=None, help='the user of harbor registry'),
    cfg.StrOpt('chart_harbor_passwd', default=None, help='the passwd of harbor registry')
]

# redis数据
redis_group = cfg.OptGroup(name='redis', title='redis conf data')
redis_opts = [
    cfg.StrOpt('redis_ip', default=None, help='the redis ip'),
    cfg.IntOpt('redis_port', default=None, help='the redis port'),
    cfg.StrOpt('redis_password', default=None, help='the redis password'),
]

# aliyun的dingodb数据
aliyun_dingodb_group = cfg.OptGroup(name='aliyun_dingodb', title='aliyun dingodb conf data')
aliyun_dingodb_opts = [
    cfg.StrOpt('host', default=None, help='the aliyun dingodb host'),
    cfg.IntOpt('port', default=9921, help='the aliyun dingodb port'),
    cfg.StrOpt('user', default=None, help='the aliyun dingodb user'),
    cfg.StrOpt('read_user', default=None, help='the aliyun dingodb read user'),
    cfg.StrOpt('password', default=None, help='the aliyun dingodb password'),
    cfg.StrOpt('read_password', default=None, help='the aliyun dingodb read user password'),
    cfg.StrOpt('report_database', default=None, help='the aliyun dingodb report database'),
]

# 注册默认配置
CONF.register_group(default_group)
CONF.register_opts(default_opts, default_group)
# 注册redis配置
CONF.register_group(redis_group)
CONF.register_opts(redis_opts, redis_group)
# 注册aliyun的dingodb配置
CONF.register_group(aliyun_dingodb_group)
CONF.register_opts(aliyun_dingodb_opts, aliyun_dingodb_group)

# redis数据

# neutron_opts = [
#     cfg.StrOpt('metadata_proxy_shared_secret', default=None, help='the redis ip'),
#     cfg.IntOpt('service_metadata_proxy', default=None, help='the redis port'),
#     cfg.StrOpt('auth_url', default=None, help='the redis password'),
#     cfg.StrOpt('auth_type', default=None, help='the redis password'),
#     cfg.StrOpt('project_domain_name', default=None, help='the redis password'),
#     cfg.StrOpt('project_name', default=None, help='the redis password'),
#     cfg.StrOpt('username', default=None, help='the redis password'),
#     cfg.StrOpt('password', default=None, help='the redis password'),
#     cfg.StrOpt('region_name', default=None, help='the redis password'),
#     cfg.StrOpt('valid_interfaces', default=None, help='the redis password'),
#     cfg.StrOpt('cafile', default=None, help='the redis password')
# ]


# 注册默认配置
CONF.register_group(default_group)
CONF.register_opts(default_opts, default_group)
# 注册redis配置
CONF.register_group(redis_group)
CONF.register_opts(redis_opts, redis_group)


neutron_group = cfg.OptGroup(name='neutron', title='neutron conf data')

