# websocket的api接口
import asyncio

from fastapi import APIRouter
from starlette.websockets import WebSocket, WebSocketDisconnect

from services.websocket_service import manager, WebSocketService
from utils.constant import websocket_data_type

router = APIRouter()

websocketService = WebSocketService()

@router.websocket("/ws/{websocket_type}")
async def websocket_endpoint(websocket: WebSocket, websocket_type: str):
    # 数据类型为空或者不是指定类型
    if websocket_type is None or websocket_type not in websocket_data_type:
        return None
    # 建立连接处理数据并推送数据到前端
    try:
        # 服务器接受客户端的WebSocket连接请求。
        await manager.connect(websocket_type, websocket)
        # 发送数据
        await websocketService.broadcast_message(websocket_type)
    # 客户端断开连接，捕获WebSocketDisconnect异常
    except WebSocketDisconnect:
        print("websocket disconnect")
        manager.disconnect(websocket_type, websocket)
        return None
    except Exception as e:
        import traceback
        traceback.print_exc()
        manager.disconnect(websocket_type, websocket)
        return None