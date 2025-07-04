# 阿里云的dingodb的服务
from dingo_command.services import CONF
from dingo_command.utils.mysql import MySqlUtils

# 阿里云的配置信息
ALIYUN_DINGODB_HOST = CONF.aliyun_dingodb.host
ALIYUN_DINGODB_PORT = CONF.aliyun_dingodb.port
ALIYUN_DINGODB_USER = CONF.aliyun_dingodb.user
ALIYUN_DINGODB_READ_USER = CONF.aliyun_dingodb.read_user
ALIYUN_DINGODB_PASSWORD = CONF.aliyun_dingodb.password
ALIYUN_DINGODB_READ_PASSWORD = CONF.aliyun_dingodb.read_password
ALIYUN_DINGODB_REPORT_DATABASE = CONF.aliyun_dingodb.report_database

class AliyunDingoDB:
    """
    阿里云的dingodb的服务
    """
    aliyun_dingodb = None

    # 初始化方法
    def __new__(cls, *args, **kwargs):
        # 是None
        if not cls.aliyun_dingodb:
            try:
                # 声明一个对象
                cls.aliyun_dingodb = MySqlUtils(
                    ALIYUN_DINGODB_HOST,
                    ALIYUN_DINGODB_PORT,
                    ALIYUN_DINGODB_USER,
                    ALIYUN_DINGODB_PASSWORD,
                    ALIYUN_DINGODB_REPORT_DATABASE
                )
            except Exception as e:
                import traceback
                traceback.print_exc()
        # 返回client
        return cls.aliyun_dingodb

# 初始化aliyun的dingodb
aliyun_dingodb_utils = AliyunDingoDB()

# 只读
class AliyunDingoDB_READ:
    """
    阿里云的dingodb的服务
    """
    aliyun_dingodb = None

    # 初始化方法
    def __new__(cls, *args, **kwargs):
        # 是None
        if not cls.aliyun_dingodb:
            try:
                # 声明一个对象
                cls.aliyun_dingodb = MySqlUtils(
                    ALIYUN_DINGODB_HOST,
                    ALIYUN_DINGODB_PORT,
                    ALIYUN_DINGODB_READ_USER,
                    ALIYUN_DINGODB_READ_PASSWORD,
                    ALIYUN_DINGODB_REPORT_DATABASE
                )
            except Exception as e:
                import traceback
                traceback.print_exc()
        # 返回client
        return cls.aliyun_dingodb

# 初始化aliyun的dingodb
aliyun_dingodb_read_utils = AliyunDingoDB_READ()