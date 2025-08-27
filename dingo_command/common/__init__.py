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

# cloudkitty的配置信息
cloudkitty_group = cfg.OptGroup(name='cloudkitty', title='cloudkitty conf data')
cloudkitty_opts = [
    cfg.StrOpt( 'auth_url', default='http://10.220.58.246:5000', help='auth url'),
    cfg.StrOpt( 'auth_type', default="password", help='auth type'),
    cfg.StrOpt( 'project_domain', default="default", help='project domain'),
    cfg.StrOpt( 'user_domain', default='default', help='user domain'),
    cfg.StrOpt( 'project_name', default='service', help='project name'),
    cfg.StrOpt( 'user_name', default='cloudkitty', help='user name'),
    cfg.StrOpt( 'password', default='LRnxEqGtZqtBC2zmwDwg9510x1sGnMPB4eOOQa0w', help='password'),
    cfg.StrOpt( 'region_name', default='RegionOne', help='region name'),
]
# 注册cloudkitty配置
CONF.register_group(cloudkitty_group)
CONF.register_opts(cloudkitty_opts, cloudkitty_group)

# cinder的配置信息
cinder_group = cfg.OptGroup(name='cinder', title='cinder conf data')
cinder_opts = [
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
CONF.register_group(cinder_group)
CONF.register_opts(cinder_opts, cinder_group)

# keystone的配置信息
keystone_group = cfg.OptGroup(name='keystone', title='keystone conf data')
keystone_opts = [
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
CONF.register_group(keystone_group)
CONF.register_opts(keystone_opts, keystone_group)

default_group = cfg.OptGroup(name='DEFAULT', title='default conf data')

default_opts = [
    cfg.StrOpt('controller_nodes', default=None, help='the openstack controller nodes'),
    cfg.StrOpt('my_ip', default=None, help='the openstack host ip'),
    cfg.StrOpt('transport_url', default=None, help='the openstack rabbit mq url'),
    cfg.StrOpt('center_transport_url', default=None, help='the region one openstack rabbit mq url'),
    cfg.BoolOpt('center_region_flag', default=False, help='the region is center region'),
    cfg.StrOpt('region_name', default=None, help='the openstack region name'),
    cfg.StrOpt('cluster_work_dir', default='/var/lib/dingo-command', help='the openstack region name'),
    cfg.StrOpt('auth_url', default=None, help='the openstack region name'),
    cfg.StrOpt('k8s_master_image', default=None, help='the master image id'),
    cfg.StrOpt('k8s_master_flavor', default=None, help='the master flavor name'),
    cfg.StrOpt('controller_password', default=None, help='the master flavor name')
]
CONF.register_group(default_group)
CONF.register_opts(default_opts, default_group)

# Harbor的配置信息
harbor_group = cfg.OptGroup(name="harbor", title="harbor conf data")
harbor_opts = [
    cfg.StrOpt(
        "base_url",
        default="https://harbor.test-03.zetyun.cn:443",
        help="harbor base url",
    ),
    cfg.StrOpt(
        "robot_username", default="robot$dingo_command", help="harbor robot username"
    ),
    cfg.StrOpt(
        "robot_token",
        default="S5Uqg5FSxoQlnoMt7JKiBIQsJ9US5wCI",
        help="harbor robot token",
    ),
    cfg.BoolOpt("verify_ssl", default=False, help="whether to verify ssl certificate"),
]
# 注册harbor配置
CONF.register_group(harbor_group)
CONF.register_opts(harbor_opts, harbor_group)

# 注册neutron配置
neutron_group = cfg.OptGroup(name='neutron', title='neutron conf data')
CONF.register_group(neutron_group)
register_ksa_opts(CONF, neutron_group, "network")
