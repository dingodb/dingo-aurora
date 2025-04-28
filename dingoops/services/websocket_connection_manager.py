# websocket的连接管理器
from fastapi import WebSocket
import asyncio

from dingoops.utils.constant import websocket_data_type

# 单例模式的websocket连接管理器
class WebSocketConnectionManager:

    _instance = None

    # 单例模式
    def __new__(cls, *args, **kwargs):
        # 是none
        if not cls._instance:
            cls._instance = super(WebSocketConnectionManager, cls).__new__(cls)
        # 返回
        return cls._instance

    # 初始化websocket连接管理
    def __init__(self):
        self.active_connections = {}
        self.lock = asyncio.Lock()

    # 连接指定类型的websocket
    async def connect(self, websocket_type: str, websocket: WebSocket):
        # 连接
        print(f"start connect websocket: {websocket_type}")
        # 判断类型
        if websocket_type not in websocket_data_type:
            print(f"websocket_type:{websocket_type} not allowed")
            return None
        # 建立连接
        await websocket.accept()
        # 更新连接组
        async with self.lock:
            # 定义默认连接
            connections = None
            # 检测当前类型是否存在
            if websocket_type not in self.active_connections:
                print(f"websocket_type:{websocket_type} not in websocket type connections")
            else:
                # 当前类型的所有的连接
                connections = self.active_connections[websocket_type]
            # 判空
            if connections is None:
                connections = set()
            # 加入最新的数据
            connections.add(websocket)
            # 更新连接
            self.active_connections[websocket_type] = connections
            print(f"websocket_type_connections: {self.active_connections}")

    # 删除指定类型的websocket
    async def disconnect(self, websocket_type: str, websocket: WebSocket):
        # 解除连接
        print(f"disconnect websocket: {websocket_type}")
        # 判断类型
        if websocket_type not in websocket_data_type:
            print(f"websocket_type:{websocket_type} not allowed")
            return None
        async with self.lock:
            # 检测当前类型是否存在
            if websocket_type not in self.active_connections:
                print(f"websocket_type:{websocket_type} connection not in websocket type connections")
                return None
            # 当前类型的所有的连接
            connections = self.active_connections[websocket_type]
            # 判断是否存在对应的类型
            if not connections:
                print(f"websocket connections is empty")
                return None
            # 判断当前websocket在
            if websocket in connections:
                connections.remove(websocket)
            # 更新连接
            self.active_connections[websocket_type] = connections

    # 像当前类型的所有连接广播消息
    async def broadcast(self, websocket_type: str, message):
        # 判断类型
        if websocket_type not in websocket_data_type or message is None:
            print(f"websocket_type:{websocket_type} not allowed or message is empty")
            return None
        async with self.lock:
            # 判断websocket_type是否存在
            if websocket_type not in self.active_connections:
                print(f"websocket type :{websocket_type} connection not in websocket type connections")
                return None
            # 当前类型的所有的连接
            connections = self.active_connections[websocket_type]
            # 判断是否存在对应的类型
            if not connections:
                print(f"websocket connections is empty")
                return None
            # 遍历
            for connection in connections:
                # 发送消息
                await connection.send_text(message)

    # 像当前类型的所有连接广播消息
    async def broadcast_websocket(self, websocket_type: str, websocket: WebSocket, message):
        # 判断类型
        if websocket_type not in websocket_data_type or message is None:
            print(f"websocket_type:{websocket_type} not allowed or message is empty")
            return None
        async with self.lock:
            # 判断websocket_type是否存在
            if websocket_type not in self.active_connections:
                print(f"websocket type :{websocket_type} connection not in websocket type connections")
                return None
            # 当前类型的所有的连接
            connections = self.active_connections[websocket_type]
            # 判断是否存在对应的类型
            if not connections:
                print(f"websocket connections is empty")
                return None
            # 遍历
            for connection in connections:
                # 发送消息
                if connection == websocket:
                    await connection.send_text(message)

# websocket连接管理
websocket_connection_manager = WebSocketConnectionManager()