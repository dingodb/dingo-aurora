# 日志等系统相关的接口
from fastapi import APIRouter, Query, HTTPException

from api.model.system import OperateLogApiModel
from services.bigscreens import BigScreensService
from services.system import SystemService

router = APIRouter()
system_service = SystemService()

@router.get("/system/logs", summary="获取系统操作日志列表数据")
async def get_system_logs(
        resource_id: str = Query(None, description="资源id"),
        page: int = Query(1, description="页码"),
        page_size: int = Query(10, description="页数量大小"),
        sort_keys:str = Query(None, description="排序字段"),
        sort_dirs:str = Query(None, description="排序方式"),):
    # 创建资产类型
    try:
        return system_service.list_system_logs(resource_id, page, page_size, sort_keys, sort_dirs)
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