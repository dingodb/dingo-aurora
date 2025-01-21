from oslo_config import cfg
import os

# 读取config的信息
CONF = cfg.CONF

# 配置目录
CONF( default_config_files = ['/etc/dingoops/dingoops.conf'])

# 数据库
bigscreen_group = cfg.OptGroup(name='bigscreen', title='bigscreen')

bigscreen_opts = [
    cfg.StrOpt('prometheus_query_url', default='http://172.20.53.200:80/api/v1/', help='prmetheus query url'),
    cfg.IntOpt('metrics_fetch_interval', default=300, help='metrics fetch interval'),
    cfg.IntOpt('metrics_expiration_time', default=600, help='metrics expiration time'),
    cfg.StrOpt('memcached_address', default='10.220.56.19:11211', help='memcached address'),
    cfg.StrOpt('memcached_key_prefix', default='bigscreen_metrics_', help='memcached bigscreen key prefix')
]

CONF.register_group(bigscreen_group)
CONF.register_opts(bigscreen_opts, bigscreen_group)

