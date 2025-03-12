# redis的频道服务
import redis

from services import CONF
from utils.constant import websocket_channels

# redis的配置信息
REDIS_HOST = CONF.redis.redis_ip
REDIS_PORT = CONF.redis.redis_port
REDIS_PASSWORD = CONF.redis.redis_password

# redis的client单例类
class RedisClientInstance:
    # redis的客户端
    redis_client = None

    # 初始化方法
    def __new__(cls, *args, **kwargs):
        # 是none
        if not cls.redis_client:
            try:
                # 连接redis客户端
                cls.redis_client = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True)
            except Exception as e:
                import traceback
                traceback.print_exc()
        # 返回
        return cls.redis_client

# redis的频道的client
redis_client_instance = RedisClientInstance()

# redis的频道管理service服务
class RedisChannelService:

    # 初始化redis的频道信息
    def __init__(self):
        try:
            # redis的连接
            publisher = redis_client_instance.pubsub()
            publisher.subscribe(websocket_channels)
            print(f"subscribe redis channel: {websocket_channels}")
        except Exception as e:
            import traceback
            traceback.print_exc()

    # 向某个channel发布消息
    def publish_channel_message(self, channel, message):
        # 发布消息
        try:
            # 判断channel是否存在
            if channel in websocket_channels:
                redis_client_instance.publish(channel, message)
            else:
                print(f"channel not exist: {channel}")
        except Exception as e:
            import traceback
            traceback.print_exc()

# redis的频道服务
redis_channel_service = RedisChannelService()