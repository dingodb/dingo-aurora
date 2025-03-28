# websocket的api接口
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from services.custom_exception import Fail
from services.websocket_service import WebSocketService, websocket_connection_manager
from utils.constant import websocket_data_type

router = APIRouter()

# websocket的服务类
websocket_service = WebSocketService()

# 所有的websocket的连接的统一入口
@router.websocket("/ws/{websocket_type}")
async def websocket_endpoint(websocket: WebSocket, websocket_type: str):
    # 类型为空或者类型不合法
    if websocket_type is None or websocket_type not in websocket_data_type:
        raise Fail("websocket_type is not valid", error_message="websocket类型不合法")
    # 建立连接处理数据并推送数据到前端
    try:
        # 服务器接受客户端的WebSocket连接请求。
        await websocket_connection_manager.connect(websocket_type, websocket)
        # # 订阅指定类型redis的频道
        await websocket_service.subscribe_redis_channel_ws(websocket_type, websocket)
    # 客户端断开连接，捕获WebSocketDisconnect异常
    except WebSocketDisconnect:
        websocket_connection_manager.disconnect(websocket_type, websocket)
        return None
    except Fail as e:
        websocket_connection_manager.disconnect(websocket_type, websocket)
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        websocket_connection_manager.disconnect(websocket_type, websocket)
        raise HTTPException(status_code=400, detail="websocket连接失败")

# websocket的测试接口，向大屏订阅发送个测试消息
@router.post("/websocket/test/{websocket_type}", summary="测试操作类websocket的消息", description="测试操作websocket的消息")
async def send_websocket_message(websocket_type: str):
    try:
        # 发送测试消息
        websocket_service.send_test_message(websocket_type)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="发送大屏评到测试消息失败")