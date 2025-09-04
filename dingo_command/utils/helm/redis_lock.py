import redis
from redis.sentinel import Sentinel
import uuid
import threading
import time
import re
from typing import Optional
from dingo_command.utils.helm.util import ChartLOG as Log



class RedisSentinelDistributedLock:
    """
    基于 Redis Sentinel 的分布式锁实现
    """

    def __init__(self, sentinel_url: str, master_name: str, password: Optional[str] = None,
                 lock_key: str = "distributed_lock", expire_time: int = 30):
        """
        初始化分布式锁

        :param sentinel_url: Sentinel URL 字符串，多个节点用分号分隔
        :param master_name: Sentinel 监控的主节点名称
        :param password: Redis 密码（可选，如果为None则从URL中提取）
        :param lock_key: 锁的键名
        :param expire_time: 锁的默认过期时间（秒）
        """
        self.sentinel_url = sentinel_url
        self.master_name = master_name
        # 如果未提供密码，则从URL中提取
        self.password = password or self._extract_password_from_url(sentinel_url)
        self.lock_key = lock_key
        self.expire_time = expire_time

        self.lock_value = str(uuid.uuid4())  # 唯一标识，确保只能释放自己加的锁
        self.is_locked = False
        self._watchdog_thread = None
        self._watchdog_stop_event = threading.Event()

        # 初始化 Redis Sentinel 连接
        self.sentinel, self.redis_client = self._init_redis_sentinel()

    def _extract_password_from_url(self, sentinel_url: str) -> str:
        """
        从 Sentinel URL 中提取密码

        :param sentinel_url: Sentinel URL 字符串
        :return: 提取到的密码
        """
        try:
            # 使用正则表达式从URL中提取密码
            # 匹配模式: sentinel://:password@host:port
            pattern = r'sentinel://:([^@]+)@'
            match = re.search(pattern, sentinel_url)
            if match:
                return match.group(1)
            else:
                raise ValueError("无法从Sentinel URL中提取密码，请检查URL格式或显式提供password参数")
        except Exception as e:
            Log.error(f"提取密码时发生错误: {str(e)}")
            raise

    def _init_redis_sentinel(self):
        """
        初始化 Redis Sentinel 连接
        """
        # 解析 Sentinel URLs
        sentinel_nodes = []
        for url in self.sentinel_url.split(';'):
            if url.startswith('sentinel://'):
                # 提取主机和端口
                clean_url = url.replace('sentinel://', '')
                if '@' in clean_url:
                    # 处理带密码的情况
                    auth_part, host_part = clean_url.split('@', 1)
                    host, port_str = host_part.split(':', 1)
                    port = int(port_str)
                    sentinel_nodes.append((host, port))

        if not sentinel_nodes:
            raise ValueError("No valid Sentinel nodes found in the URL")

        try:
            # 创建 Sentinel 连接
            sentinel = Sentinel(
                sentinel_nodes,
                socket_timeout=5,
                password=self.password,
                decode_responses=True
            )

            # 获取主节点客户端
            redis_client = sentinel.master_for(
                self.master_name,
                socket_timeout=5,
                password=self.password,
                decode_responses=True
            )

            # 测试连接
            redis_client.ping()
            # Log.info("Successfully connected to Redis Sentinel")

            return sentinel, redis_client

        except Exception as e:
            Log.error(f"Failed to connect to Redis Sentinel: {str(e)}")
            raise

    def acquire(self, retry_times: int = 3, retry_interval: float = 0.5) -> bool:
        """
        获取分布式锁

        :param retry_times: 重试次数
        :param retry_interval: 重试间隔（秒）
        :return: True if acquired, False otherwise
        """
        for attempt in range(retry_times):
            try:
                # 使用 SET 命令的 NX 和 PX 参数实现原子操作
                result = self.redis_client.set(
                    self.lock_key,
                    self.lock_value,
                    nx=True,
                    px=self.expire_time * 1000  # 转换为毫秒
                )

                if result:
                    self.is_locked = True
                    Log.info(f"Lock acquired for key: {self.lock_key}")
                    self._start_watchdog()  # 启动看门狗线程自动续期
                    return True
                else:
                    # Log.debug(f"Failed to acquire lock on attempt {attempt + 1}. Retrying...")
                    time.sleep(retry_interval)

            except redis.RedisError as e:
                # Log.error(f"Error acquiring lock: {e}")
                time.sleep(retry_interval)

        # Log.warning(f"Failed to acquire lock after {retry_times} attempts.")
        return False

    def release(self) -> bool:
        """
        释放分布式锁。使用Lua脚本保证原子性，确保只有锁的持有者才能释放。
        """
        if not self.is_locked:
            return True

        self._stop_watchdog()  # 停止看门狗线程

        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        try:
            result = self.redis_client.eval(lua_script, 1, self.lock_key, self.lock_value)
            if result == 1:
                self.is_locked = False
                Log.info(f"Lock released for key: {self.lock_key}")
                return True
            else:
                Log.warning("Lock release failed: lock value mismatch or lock does not exist.")
                return False
        except redis.RedisError as e:
            Log.error(f"Error releasing lock: {e}")
            return False

    def _start_watchdog(self):
        """启动看门狗线程，用于自动续期"""
        if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
            return

        self._watchdog_stop_event.clear()

        def watchdog_task():
            while not self._watchdog_stop_event.is_set():
                try:
                    time.sleep(self.expire_time / 3)  # 在过期时间的 1/3 时续期
                    if self._watchdog_stop_event.is_set():
                        break

                    # 续期前再次检查锁是否仍属于自己
                    current_value = self.redis_client.get(self.lock_key)
                    if current_value and current_value == self.lock_value:
                        self.redis_client.pexpire(self.lock_key, self.expire_time * 1000)
                        Log.debug(f"Lock renewed for key: {self.lock_key}")
                    else:
                        Log.warning("Watchdog: lock value mismatch, stopping renewal.")
                        self._watchdog_stop_event.set()
                        self.is_locked = False
                        break
                except redis.RedisError as e:
                    Log.error(f"Watchdog error: {e}")
                    break
                except Exception as e:
                    Log.error(f"Unexpected watchdog error: {e}")
                    break

        self._watchdog_thread = threading.Thread(target=watchdog_task, daemon=True)
        self._watchdog_thread.start()

    def _stop_watchdog(self):
        """停止看门狗线程"""
        self._watchdog_stop_event.set()
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=2.0)
            self._watchdog_thread = None

    def __enter__(self):
        """支持 with 语句"""
        if self.acquire():
            return self
        else:
            raise Exception("Could not acquire lock")

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持 with 语句"""
        self.release()

    def __del__(self):
        """析构函数中尝试释放锁"""
        if self.is_locked:
            self.release()