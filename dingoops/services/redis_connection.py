# redis连接工具 用于连接redis数据库 读取和写入数据
import redis

from dingoops.services import CONF

# redis的配置信息
REDIS_HOST = CONF.redis.redis_ip
REDIS_PORT = CONF.redis.redis_port
REDIS_PASSWORD = CONF.redis.redis_password

# Redis连接工具
class RedisConnection:

    # 创建redis连接
    redis_connection = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, db=0)

    # 从redis中读取
    def get_redis_by_key(self, redis_key:str):
        # 判空
        if not redis_key:
            return None
        # 判断redis存在当前key
        if self.redis_connection.exists(redis_key):
            # 返回数据
            return self.redis_connection.get(redis_key)

    # 向redis中写入
    def set_redis_by_key(self, redis_key:str, redis_value):
        # 判空
        if not redis_key:
            return None
        # 更新数据为空
        if not redis_key:
            return None
        # 返回数据
        return self.redis_connection.set(redis_key, redis_value)

# 声明redis的连接工具
redis_connection = RedisConnection()