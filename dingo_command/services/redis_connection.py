# redis连接工具 用于连接redis数据库 读取和写入数据
import redis
import uuid
import time

from dingo_command.services import CONF

# redis的配置信息
REDIS_HOST = CONF.redis.redis_ip
REDIS_PORT = CONF.redis.redis_port
REDIS_PASSWORD = CONF.redis.redis_password

# Redis连接工具
class RedisConnection:

    # 创建redis连接
    redis_connection = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, db=0, decode_responses=True)

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

    def set_redis_by_key_with_expire(self, redis_key: str, redis_value, expire_seconds=None):
        """
        向Redis中写入键值对，支持设置秒级超时时间

        Args:
            redis_key: Redis键名
            redis_value: 要存储的值
            expire_seconds: 超时时间（秒），默认为None表示不过期

        Returns:
            bool: 设置成功返回True，否则返回False
        """
        if not redis_key:
            return False

        try:
            if expire_seconds is not None:
                # 使用setex命令同时设置值和过期时间[6,7](@ref)
                return self.redis_connection.setex(redis_key, expire_seconds, redis_value)
            else:
                # 不使用过期时间
                return self.redis_connection.set(redis_key, redis_value)
        except Exception as e:
            print(f"Redis set operation failed: {e}")
            return False

    def delete_redis_key(self, redis_key: str) -> bool:
        """
        删除Redis中指定的key

        Args:
            redis_key: 要删除的Redis键名

        Returns:
            bool: 成功删除返回True (即使key不存在也会返回True)，
                  如果遇到异常则返回False
        """
        if not redis_key:
            return False

        try:
            result = self.redis_connection.delete(redis_key)
            return True
        except Exception as e:
            print(f"Redis delete operation failed: {e}")
            return False

# 声明redis的连接工具
redis_connection = RedisConnection()

class RedisLock:

    def __init__(self, redis_client, lock_name, expire_time=30, retry_interval=0.1, auto_renew=False):
        """
        :param redis_client: Redis 连接实例
        :param lock_name: 分布式锁名称（全局唯一）
        :param expire_time: 锁自动过期时间（秒）
        :param retry_interval: 获取锁失败后的重试间隔（秒）
        :param auto_renew: 是否启用自动续期（针对长任务）
        """
        self.client = redis_client
        self.lock_name = lock_name
        self.expire_time = expire_time
        self.retry_interval = retry_interval
        self.auto_renew = auto_renew
        self.identifier = str(uuid.uuid4())  # 唯一标识符防止误删:ml-citation{ref="7" data="citationList"}
        self._renew_thread = None

    def acquire(self, timeout=10):
        """
        获取锁（支持超时等待）
        :param timeout: 最长等待时间（秒）
        :return: 是否成功获取锁
        """
        end_time = time.time() + timeout
        while time.time() < end_time:
            # 原子操作：SET key value NX EX
            if self.client.set(self.lock_name, self.identifier, nx=True, ex=self.expire_time):
                if self.auto_renew:
                    self._start_renew_thread()
                return True
            time.sleep(self.retry_interval)
        return False

    def release(self):
        """
        释放锁（Lua 脚本保证原子性）
        """
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """
        result = self.client.eval(lua_script, 1, self.lock_name, self.identifier)
        if self.auto_renew and self._renew_thread:
            self._stop_renew_thread()
        return bool(result)

    def _start_renew_thread(self):
        """启动后台线程自动续期"""
        import threading
        self._renew_thread = threading.Thread(target=self._renew_lock, daemon=True)
        self._renew_thread.start()

    def _stop_renew_thread(self):
        """停止续期线程"""
        self._renew_thread = None

    def _renew_lock(self):
        """锁续期逻辑"""
        while getattr(self._renew_thread, "do_run", True):
            time.sleep(self.expire_time // 3)
            if self.client.get(self.lock_name) == self.identifier:
                self.client.expire(self.lock_name, self.expire_time)

    def __enter__(self):
        if self.acquire():
            return self
        raise TimeoutError("获取锁超时")

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()