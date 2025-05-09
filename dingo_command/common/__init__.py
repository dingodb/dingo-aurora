from oslo_config import cfg
from dingo_command.common.common import register_ksa_opts

# 读取config的信息
CONF = cfg.CONF

# 配置目录
CONF(args=[], default_config_files = ['/etc/dingo-command/dingo-command.conf'])

# ironic的配置信息
ironic_group = cfg.OptGroup(name='ironic', title='ironic conf data')
ironic_opts = [
    cfg.StrOpt( 'auth_url', default='http://10.220.56.254:5000', help='auth url'),
    cfg.StrOpt( 'auth_type', default="password", help='auth type'),
    cfg.StrOpt( 'project_domain', default="default", help='project domain'),
    cfg.StrOpt( 'user_domain', default='default', help='user domain'),
    cfg.StrOpt( 'project_name', default='service', help='project name'),
    cfg.StrOpt( 'user_name', default='ironic', help='user name'),
    cfg.StrOpt( 'password', default='dKF6StAnNfzTQjXVX3MIGWSRi0JagLxAKZDK6zLk', help='password'),
    cfg.StrOpt( 'region_name', default='RegionOne', help='region name'),
]
# 注册ironic配置
CONF.register_group(ironic_group)
CONF.register_opts(ironic_opts, ironic_group)

# nova的配置信息
nova_group = cfg.OptGroup(name='nova', title='nova conf data')
nova_opts = [
    cfg.StrOpt( 'auth_url', default='http://10.220.56.254:5000', help='auth url'),
    cfg.StrOpt( 'auth_type', default="password", help='auth type'),
    cfg.StrOpt( 'project_domain', default="default", help='project domain'),
    cfg.StrOpt( 'user_domain', default='default', help='user domain'),
    cfg.StrOpt( 'project_name', default='service', help='project name'),
    cfg.StrOpt( 'user_name', default='nova', help='user name'),
    cfg.StrOpt( 'password', default='XModTf5fcvUw7aAr3CUBBVdO38WQS15QQwNqVjGJ', help='password'),
    cfg.StrOpt( 'region_name', default='RegionOne', help='region name'),
]
# 注册nova配置
CONF.register_group(nova_group)
CONF.register_opts(nova_opts, nova_group)

# 注册neutron配置
neutron_group = cfg.OptGroup(name='neutron', title='neutron conf data')
CONF.register_group(neutron_group)
register_ksa_opts(CONF, neutron_group, "network")
