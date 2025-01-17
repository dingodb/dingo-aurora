# 监控接口配置
from fastapi import APIRouter, Query
from oslo_log import log

from services.monitor import MonitorService

# 日志
LOG = log.getLogger(__name__)
# 路由
router = APIRouter()
monitor_service = MonitorService()

@router.get("/monitor/urls", summary="查询监控url接口配置列表", description="根据各种条件查询监控url接口配置列表")
async def list_monitor_urls(
        name:str = Query(None, description="名称"),
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
        # 查询成功
        result = monitor_service.list_monitor_urls(query_params, page, page_size, sort_keys, sort_dirs)
        return result
    except Exception as e:
        return None
