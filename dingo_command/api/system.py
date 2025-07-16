# 日志等系统相关的接口
from fastapi import APIRouter, Query, HTTPException

from dingo_command.api.model.system import OperateLogApiModel
from dingo_command.services.system import SystemService

router = APIRouter()
system_service = SystemService()

@router.get("/system/logs", summary="获取系统操作日志列表数据")
async def get_system_logs(
        resource_id: str = Query(None, description="资源id"),
        user_id: str = Query(None, description="操作人id"),
        operate_type: str = Query(None, description="操作类型"),
        page: int = Query(1, description="页码"),
        page_size: int = Query(10, description="页数量大小"),
        sort_keys:str = Query("log_date", description="排序字段"),
        sort_dirs:str = Query("descend", description="排序方式"),):
    # 创建资产类型
    try:
        # 查询条件
        query_params = {}
        if resource_id:
            query_params["resource_id"] =resource_id
        if user_id:
            query_params["user_id"] =user_id
        if operate_type:
            query_params["operate_type"] =operate_type
        # 查询
        return system_service.list_system_logs(query_params, page, page_size, sort_keys, sort_dirs)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="system log query error")

@router.post("/system/logs", summary="创建系统操作日志数据")
async def create_system_log(system_log:OperateLogApiModel):
    # 创建资产类型
    try:
        return system_service.create_system_log(system_log)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="system log create error")

@router.get("/system/time_range", summary="根据类型查询系统时间范围")
async def get_system_time_range(time_type: str = Query(None, description="时间类型. current_month:当月；one_hour_ago：最近一小时；one_day_ago：最近一天；one_week_ago：最近7天；month30_ago：最近30天"),):
    try:
        return system_service.get_system_time_range(time_type)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="get system time range error")

@router.get("/system/current_time", summary="获取系统当前时间")
async def get_system_current_time():
    try:
        return system_service.get_system_current_time()
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="get system current time error")

@router.get("/system/support_config", summary="获取系统支持配置")
async def get_system_support_config():
    try:
        return system_service.get_system_support_config()
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="get system support config error")