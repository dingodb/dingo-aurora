from oslo_config import cfg

# 读取config的信息
CONF = cfg.CONF

# 配置目录
CONF(args=[], default_config_files = ['/etc/dingoops/dingoops.conf'])

# 默认配置
default_group = cfg.OptGroup(name='DEFAULT', title='default conf data')
default_opts = [
    cfg.StrOpt('vip', default=None, help='the openstack vip'),
    cfg.StrOpt('my_ip', default=None, help='the openstack host ip'),
    cfg.StrOpt('transport_url', default=None, help='the openstack rabbit mq url'),
    cfg.StrOpt('center_transport_url', default=None, help='the region one openstack rabbit mq url'),
    cfg.BoolOpt('center_region_flag', default=False, help='the region is center region'),
    cfg.StrOpt('region_name', default=None, help='the openstack region name')
]

# redis数据
redis_group = cfg.OptGroup(name='redis', title='redis conf data')
redis_opts = [
    cfg.StrOpt('redis_ip', default=None, help='the redis ip'),
    cfg.IntOpt('redis_port', default=None, help='the redis port'),
    cfg.StrOpt('redis_password', default=None, help='the redis password'),
]

# 注册默认配置
CONF.register_group(default_group)
CONF.register_opts(default_opts, default_group)
# 注册redis配置
CONF.register_group(redis_group)
CONF.register_opts(redis_opts, redis_group)

