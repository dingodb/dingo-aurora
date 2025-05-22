import os
import subprocess
from oslo_config import cfg
from dingo_command.common.common import register_ksa_opts
# 读取config的信息
CONF = cfg.CONF

# 配置目录
CONF(args=[], default_config_files = ['/etc/dingo-command/dingo-command.conf'])

# 默认数据
default_group = cfg.OptGroup(name='DEFAULT', title='default conf data')

default_opts = [
    cfg.StrOpt('vip', default=None, help='the openstack vip'),
    cfg.StrOpt('my_ip', default=None, help='the openstack host ip'),
    cfg.StrOpt('transport_url', default=None, help='the openstack rabbit mq url'),
    cfg.StrOpt('center_transport_url', default=None, help='the region one openstack rabbit mq url'),
    cfg.BoolOpt('center_region_flag', default=False, help='the region is center region'),
    cfg.StrOpt('region_name', default=None, help='the openstack region name'),
    cfg.StrOpt('cluster_work_dir', default='/var/lib/dingo-command', help='the openstack region name'),
    cfg.StrOpt('harbor_url', default=None, help='harbor url'),
    cfg.StrOpt('fileserver_url', default=None, help='fileserver url'),
]

CONF.register_group(default_group)
CONF.register_opts(default_opts, default_group)

# redis数据
redis_group = cfg.OptGroup(name='redis', title='redis conf data')
redis_opts = [
    cfg.StrOpt('redis_ip', default=None, help='the redis ip'),
    cfg.IntOpt('redis_port', default=None, help='the redis port'),
    cfg.StrOpt('redis_password', default=None, help='the redis password'),
    cfg.StrOpt('sentinel_url', default=None, help='the redis sentinel'),
]

# 注册默认配置
CONF.register_group(default_group)
CONF.register_opts(default_opts, default_group)
# 注册redis配置
CONF.register_group(redis_group)
CONF.register_opts(redis_opts, redis_group)

# redis数据
neutron_group = cfg.OptGroup(name='neutron', title='neutron conf data')
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
# 注册redis配置
CONF.register_group(neutron_group)
register_ksa_opts(CONF, neutron_group, "network")


# 注册默认配置
CONF.register_group(default_group)
CONF.register_opts(default_opts, default_group)
# 注册redis配置
CONF.register_group(redis_group)
CONF.register_opts(redis_opts, redis_group)

#复制ansible-deploy目录到WORK_DIR目录下
ansible_dir = os.path.join(os.getcwd(), "dingo_command","templates","ansible-deploy")
WORK_DIR = CONF.DEFAULT.cluster_work_dir
aaa = subprocess.run(["cp", "-LRpf", ansible_dir, WORK_DIR], capture_output=True)
# print(aaa.stdout)
