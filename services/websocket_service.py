# websocket的服务类
import json

from fastapi import WebSocket
import asyncio

from db.models.bigscreen.sql import BigscreenSQL
from jobs import CONF
from utils.constant import websocket_data_type

# 当前region名称
region_name = CONF.DEFAULT.region_name

class ConnectionManager:
    # 初始化websocket连接管理
    def __init__(self):
        self.active_connections = {}
        self.lock = asyncio.Lock()

    # 连接指定类型的websocket
    async def connect(self, websocket_type: str, websocket: WebSocket):
        # 判断类型
        if websocket_type not in websocket_data_type:
            print(f"websocket_type:{websocket_type} not allowed")
            return None
        # 建立连接
        await websocket.accept()
        # 更新连接组
        async with self.lock:
            # 获取当前类型的所有连接
            connections = self.active_connections.get(websocket_type)
            # 判空
            if connections is None:
                connections = set()
            # 加入最新的数据
            connections.add(websocket)
            # 更新对应类型
            self.active_connections[websocket_type] = connections

    # 删除指定类型的websocket
    async def disconnect(self, websocket_type: str, websocket: WebSocket):
        # 判断类型
        if websocket_type not in websocket_data_type:
            print(f"websocket_type:{websocket_type} not allowed")
            return None
        async with self.lock:
            # 判断是否存在对应的类型
            if websocket_type in self.active_connections:
                # 获取当前类型的所有连接
                connections = self.active_connections.get(websocket_type)
                # 判断当前websocket在
                if websocket in connections:
                    connections.remove(websocket)
                    # 更新对应类型
                    self.active_connections[websocket_type] = connections
                else:
                    print(f"websocket_type:{websocket_type} connections not exists")
            else:
                print(f"websocket_type:{websocket_type} not exists")

    # 像当前类型的所有连接广播消息
    async def broadcast(self, websocket_type: str, message: str):
        # 判断类型
        if websocket_type not in websocket_data_type or message is None:
            print(f"websocket_type:{websocket_type} not allowed or message is empty")
            return None
        async with self.lock:
            # 判断是否存在对应的类型
            if websocket_type in self.active_connections:
                # 获取当前类型的所有连接
                connections = self.active_connections.get(websocket_type)
                # 遍历
                for connection in connections:
                    # 发送消息
                    await connection.send_text(message)

# websocket的连接管理类
manager = ConnectionManager()



class WebSocketService:

    # 大屏最新的时间
    big_screen_last_time = None

    async def broadcast_message(self, websocket_type: str):
        # 循环
        while True:
            # 定义发送的message
            message = None
            # 给当前类型的websocket连接广播消息
            if websocket_type == "big_screen":
                # 查询当前region的数据
                big_screen_metric = BigscreenSQL.get_bigscreen_by_region(region_name)
                # 非空
                if big_screen_metric:
                    # 第一次时间或者时间不一致
                    if WebSocketService.big_screen_last_time is None or WebSocketService.big_screen_last_time != big_screen_metric.last_modified:
                        # 消息通知需要刷新
                        message = json.dumps({"refresh_flag": True})
                    # 时间赋值最新时间
                    WebSocketService.big_screen_last_time = big_screen_metric.last_modified
            # 发送
            if message:
                await manager.broadcast(websocket_type, message)
            # 休息时间5s
            await asyncio.sleep(5)
