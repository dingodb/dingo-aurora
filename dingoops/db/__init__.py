from oslo_config import cfg
import os

# 读取config的信息
CONF = cfg.CONF

# 配置目录
CONF(args=[], default_config_files = ['/etc/dingoops/dingoops.conf'])

# 数据库
database_group = cfg.OptGroup(name='database', title='database')

database_opts = [
    cfg.StrOpt('connection', default='mysql+pymysql://root:HworLIIDvmTRsPfQauNskuJF8PcoTuULfu3dEHFg@10.220.56.254:3306/dingoops?charset=utf8mb3', help='the mysql url'),
]

CONF.register_group(database_group)
CONF.register_opts(database_opts, database_group)
