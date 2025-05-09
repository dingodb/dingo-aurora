# 接收消息的api接口定义类
from fastapi import APIRouter, HTTPException
from oslo_log import log

from dingoops.services.custom_exception import Fail
from dingoops.services.message import MessageService

LOG = log.getLogger(__name__)

router = APIRouter()
message_service = MessageService()

@router.post("/messages/external", summary="发送外部的消息数据", description="接收外部的消息数据")
async def create_external_message(message: dict):
    # 创建消息
    try:
        # 接收到的数据
        LOG.info("接收到的数据: %s", message)
        result = message_service.create_external_message(message)
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="create external message error")