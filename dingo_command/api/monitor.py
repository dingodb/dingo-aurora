# 监控接口配置
from fastapi import APIRouter, Query, HTTPException
from oslo_log import log

from dingo_command.api.model.monitor import MonitorUrlConfigApiModel
from dingo_command.services.custom_exception import Fail
from dingo_command.services.monitor import MonitorService

# 日志
LOG = log.getLogger(__name__)
# 路由
router = APIRouter()
monitor_service = MonitorService()

@router.get("/monitor/urls", summary="查询监控url接口配置列表", description="根据各种条件查询监控url接口配置列表")
async def list_monitor_urls(
        name:str = Query(None, description="名称"),
        url_catalog:str = Query(None, description="分类"),
        url_type:str = Query(None, description="url类型"),
        url:str = Query(None, description="url"),
        page: int = Query(1, description="页码"),
        page_size: int = Query(10, description="页数量大小"),
        sort_keys:str = Query(None, description="排序字段"),
        sort_dirs:str = Query(None, description="排序方式"),):
    # 接收查询参数
    # 返回数据接口
    try:
        # 声明查询条件的dict
        query_params = {}
        if name:
            query_params['name'] = name
        if url_catalog:
            query_params['url_catalog'] = url_catalog
        if url_type:
            query_params['url_type'] = url_type
        if url:
            query_params['url'] = url
        # 查询成功
        result = monitor_service.list_monitor_urls(query_params, page, page_size, sort_keys, sort_dirs)
        return result
    except Exception as e:
        return None

@router.post("/monitor/urls", summary="创建监控url配置信息数据")
async def create_monitor_url(monitor_url_config:MonitorUrlConfigApiModel):
    # 创建资产类型
    try:
        return monitor_service.create_monitor_url_config(monitor_url_config)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="create monitor url config info error")

@router.delete("/monitor/urls/{id}", summary="删除监控url配置信息", description="根据id删除监控url配置信息")
async def delete_monitor_url_by_id(id:str):
    # 删除监控配置信息
    try:
        # 删除成功
        result = monitor_service.delete_monitor_url_config_by_id(id)
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="delete monitor url config error")

@router.put("/monitor/urls/{id}", summary="修改监控url配置信息", description="根据id修改监控url配置信息")
async def delete_monitor_url_by_id(id:str, monitor_url_config:MonitorUrlConfigApiModel):
    # 删除监控配置信息
    try:
        # 删除成功
        result = monitor_service.update_monitor_url_config_by_id(id, monitor_url_config)
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="delete monitor url config error")
