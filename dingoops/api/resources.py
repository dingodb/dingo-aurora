# 资源的api接口
from fastapi import APIRouter, HTTPException, Query

from services.custom_exception import Fail
from services.resources import ResourcesService

router = APIRouter()
resources_service = ResourcesService()

@router.get("/resources/management_list", summary="查询资源与资产管理列表", description="查询所有VPC下资源与资产管理列表")
async def resource_asset_management_list(
        page: int = Query(1, description="页码"),
        page_size: int = Query(10, description="页数量大小"),
        sort_keys: str = Query(None, description="排序字段"),
        sort_dirs: str = Query(None, description="排序方式"),):
    try:
        # 声明查询条件的dict
        query_params = {}

        # 查询资源与资产管理列表数据
        return resources_service.resource_asset_management_list(query_params, page, page_size, sort_keys, sort_dirs)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        raise HTTPException(status_code=400, detail="resource asset management list error")

@router.get("/resources/statistic_list", summary="查询VPC资源统计列表", description="各种各种条件查询VPC资源统计列表")
async def vpc_resource_statistic_list():
    try:
        # 查询资源统计概览相关数据
        return resources_service.vpc_resource_statistic_list()
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        raise (HTTPException(status_code=400, detail="vpc resource statistic list error"))

@router.get("/resources/{vpcId}/detail", summary="VPC资源详情列表", description="查询VPC下资源的详情列表")
async def resource_detail_list(vpcId:str):
    try:
        # 查询资源统计概览相关数据
        return resources_service.resource_detail_list(vpcId)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        raise HTTPException(status_code=400, detail="resource detail list error")

@router.get("/resources/statistics_overview", summary="查询资源统计概览视图数据", description="组装资源统计概览视图数据")
async def fetch_resource_statistic_overview_data():
    try:
        # 查询资源统计概览相关数据
        return resources_service.fetch_resource_statistic_overview_data()
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        raise HTTPException(status_code=400, detail="fetch resource statistic overview error")
