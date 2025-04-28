# websocket的服务类
import json
import asyncio

from fastapi import WebSocket

from dingoops.db.models.bigscreen.sql import BigscreenSQL
from dingoops.jobs import CONF
from dingoops.services.custom_exception import Fail
from dingoops.services.redis_channel import redis_channel_service, redis_client_instance
from dingoops.services.websocket_connection_manager import websocket_connection_manager
from dingoops.utils.constant import websocket_data_type, websocket_type_channels

# 当前region名称
REGION_NAME = CONF.DEFAULT.region_name


class WebSocketService:

    # 大屏最新的时间
    big_screen_last_time = None

    # 直接发送消息到前端当前类型的所有websocket，适合redis订阅模式
    async def broadcast_redis_message(self, websocket_type: str, message):
        # 类型为空或者类型不合法
        if websocket_type is None or websocket_type not in websocket_data_type:
            print("websocket_type is not valid")
            return None
        # 消息空
        if not message:
            print("message is none")
            return None
        # 发送
        await websocket_connection_manager.broadcast(websocket_type, "message")


    # 直接发送消息到前端某个websocket，适合redis订阅模式
    async def broadcast_redis_message_4ws(self, websocket_type: str, websocket: WebSocket, message):
        # 类型为空或者类型不合法
        if websocket_type is None or websocket_type not in websocket_data_type:
            print("websocket_type is not valid")
            return None
        # 消息空
        if not message:
            print("message is none")
            return None
        # 消息
        print(f"redis channel message info: {message}")
        # 发送
        await websocket_connection_manager.broadcast_websocket(websocket_type, websocket, message['data'])

    # 发送redis的频道消息 适合操作类触发的websocket消息
    def send_test_message(self, websocket_type:str):
        try:
            redis_channel_service.publish_channel_message(websocket_type_channels[websocket_type], json.dumps({"refresh_flag": True}))
            print("send redis channel message success")
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise Fail("send redis channel message fail", error_message="发送redis频道测试消息失败")

    # 处理redis的频道消息 适合操作类触发的websocket消息
    async def subscribe_redis_channel_ws(self, websocket_type:str, websocket: WebSocket):
        try:
            # 类型为空或者类型不合法
            if websocket_type is None or websocket_type not in websocket_data_type or websocket_type not in websocket_type_channels:
                raise Fail("websocket_type is not valid", error_message="websocket类型不合法")
            # 开始处理频道消息
            print(f"subscribe redis channel by websocket_type: {websocket_type}")
            # redis订阅频道
            publisher = redis_client_instance.pubsub()
            publisher.subscribe(websocket_type_channels[websocket_type])
            # 循环
            while True:
                # 读取消息
                message = publisher.get_message(ignore_subscribe_messages=True, timeout=1)
                # 非空
                if message:
                    await self.broadcast_redis_message_4ws(websocket_type, websocket, message)
                # 休息
                await asyncio.sleep(5)
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise Fail("subscribe redis channel fail", error_message="订阅redis频道失败")

    # 处理redis的频道消息 适合操作类触发的websocket消息
    async def subscribe_redis_channel(self, websocket_type:str):
        try:
            # 类型为空或者类型不合法
            if websocket_type is None or websocket_type not in websocket_data_type or websocket_type not in websocket_type_channels:
                raise Fail("websocket_type is not valid", error_message="websocket类型不合法")
            # 开始处理频道消息
            print(f"subscribe redis channel by websocket_type: {websocket_type}")
            # redis订阅频道
            publisher = redis_client_instance.pubsub()
            publisher.subscribe(websocket_type_channels[websocket_type])
            # 循环
            while True:
                # 读取消息
                message = publisher.get_message(ignore_subscribe_messages=True, timeout=1)
                # 非空
                if message:
                    await self.broadcast_redis_message(websocket_type, message)
                # 休息
                await asyncio.sleep(5)
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise Fail("subscribe redis channel fail", error_message="订阅redis频道失败")

    # 根据redis的频道查询对应的websocket的类型
    def get_websocket_type_by_channel(self, channel):
        # 空
        if not channel:
            print(f"channel is none")
            return None
        # 查找channel对应的类型
        for temp_websocket_type, temp_channel in websocket_type_channels.items():
            if channel == temp_channel:
                return temp_websocket_type
        # 返回空
        return None

    # 返回最新的大屏的websocket消息
    def get_big_screen_websocket_message(self):
        # 定义message
        message = None
        # 查询当前region的数据
        big_screen_metric = BigscreenSQL.get_bigscreen_by_region(REGION_NAME)
        # 非空
        if big_screen_metric:
            # 第一次时间或者时间不一致
            if WebSocketService.big_screen_last_time is None or WebSocketService.big_screen_last_time != big_screen_metric.last_modified:
                # 消息通知需要刷新
                message = json.dumps({"refresh_flag": True})
            # 时间赋值最新时间
            WebSocketService.big_screen_last_time = big_screen_metric.last_modified
        # 返回
        return message

    # 根据类型发送redis的频道消息 适合操作类触发的websocket消息
    def send_websocket_message(self, websocket_type:str, message):
        try:
            redis_channel_service.publish_channel_message(websocket_type_channels[websocket_type], message)
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise Fail("send redis channel message fail", error_message="发送redis频道消息失败")

# 声明websocket的service
websocket_service = WebSocketService()