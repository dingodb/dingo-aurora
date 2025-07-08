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


@router.get("/messages/external/{message_type}", summary="查询消息报送后的消息数据",
            description="查询消息报送后的消息数据。"
                        "支持根据特定规则多种条件过滤，字段与运算符之间以两个下划线连接（__）. 运算符支持：ge(大于等于)、le(小于等于)、gt(大于)、lt(小于)、in(包含于)、like(模糊匹配)、ne(不等于)。 \n"
                         "举例： data_time__ge=2025-05-01 00:00:00&data_time__le=2025-05-31 23:59:59&status__in=1,2,3&name__like=Datacanvas%&namespace__ne=vcluster-vcxjze2ols23")
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
        # 解析查询条件
        query_params = dict(request.query_params) if hasattr(request, 'query_params') else {}
        query_conditions = parse_query_conditions(query_params)

        # 查询阿里云的dingodb数据库
        count_number = message_service.count_messages_from_dingodb(message_type, query_conditions)
        data_list = message_service.list_messages_from_dingodb(message_type, query_conditions, page, page_size, sort_keys, sort_dirs)
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

def parse_query_conditions(query_params):
    """解析查询参数为结构化条件"""
    conditions = {}
    # 删掉固定参数
    exclude_params = ["page", "page_size", "sort_keys", "sort_dirs"]

    for key, value in query_params.items():
        if key in exclude_params:
            continue

        # 处理运算符 (field__op=value)
        if "__" in key:
            field, op = key.split("__", 1)
            # 验证运算符有效性
            if op not in ["gt", "ge", "lt", "le", "like", "in", "ne"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"不支持的运算符: {op}. 可用运算符: gt,ge,lt,le,like,in,ne"
                )
            conditions.setdefault(field, []).append({
                "operator": op,
                "value": value
            })
        else:
            # 默认等于查询
            conditions.setdefault(key, []).append({
                "operator": "eq",
                "value": value
            })

    return conditions

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