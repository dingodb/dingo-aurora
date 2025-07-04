# 接收消息的api接口定义类
import json

from math import ceil

from fastapi import APIRouter, HTTPException, Query, Request
from oslo_log import log

from dingo_command.api.model.message import MessageQueryApiModel
from dingo_command.services.custom_exception import Fail
from dingo_command.services.message import MessageService

LOG = log.getLogger(__name__)

router = APIRouter()
message_service = MessageService()

@router.post("/messages/external", summary="发送外部的消息数据", description="接收外部的消息数据")
async def create_external_message(message: dict):
    # 创建消息
    try:
        # 接收到的数据
        LOG.info("接收到的数据: %s", message)
        result = message_service.send_message_to_queue(message)
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="create external message error")


@router.get("/messages/external/{message_type}", summary="查询消息报送后的消息数据", description="查询消息报送后的消息数据")
async def list_external_message_data(
        message_type: str,
        request: Request,
        page: int = Query(1, description="页码"),
        page_size: int = Query(10, description="页数量大小"),
        sort_keys:str = Query(None, description="排序字段"),
        sort_dirs:str = Query("asc", description="排序方式"),):
    # 创建消息
    try:
        # 接收到的数据
        LOG.info("查询的数据类型: %s", message_type)
        # 读取request中的请求参数，删掉固定参数
        query_params = dict(request.query_params) if hasattr(request, 'query_params') else {}
        query_params.pop("page", None)
        query_params.pop("page_size", None)
        query_params.pop("sort_keys", None)
        query_params.pop("sort_dirs", None)
        # 查询阿里云的dingodb数据库
        count_number = message_service.count_messages_from_dingodb(message_type, query_params)
        data_list = message_service.list_messages_from_dingodb(message_type, query_params, page, page_size, sort_keys, sort_dirs)
        # 定义数据
        result = {}
        # 页数相关信息
        if page and page_size:
            result['currentPage'] = page
            result['pageSize'] = page_size
            result['totalPages'] = ceil(count_number / int(page_size))
        result['total'] = count_number
        result['data'] = data_list
        # 返回数据
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="query message error")

@router.post("/messages/external/statistics", summary="查询消息报送后的消息数据的统计结果", description="查询消息报送后的消息数据的统计结果")
async def list_external_message_statistics(message:MessageQueryApiModel):
    # 通过sql查询消息统计结果
    try:
        # 接收到的数据
        LOG.info("查询的报送数据的统计结果")
        # 查询阿里云的dingodb数据库
        data_list = message_service.list_messages_from_dingodb_by_sql(message.sql)
        # 定义数据
        result = {}
        # 页数相关信息
        result['data'] = data_list
        # 返回数据
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="query message error")