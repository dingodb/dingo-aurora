# 资源的api接口
from fastapi import APIRouter, HTTPException, Query

from dingo_command.services.custom_exception import Fail
from dingo_command.services.resources import ResourcesService

router = APIRouter()
resources_service = ResourcesService()

@router.get("/resources/statistic_list", summary="查询所有租户下资源统计列表", description="根据各种条件查询所有租户下资源统计列表")
async def project_resource_statistic_list(page: int = Query(1, description="页码"),
        page_size: int = Query(10, description="页数量大小"),
        sort_keys: str = Query(None, description="排序字段"),
        sort_dirs: str = Query(None, description="排序方式"),
        resource_project_name: str = Query(None, description="租户的名称"),):
    try:
        # 声明查询条件的dict
        query_params = {}
        if resource_project_name:
            query_params['resource_project_name'] = resource_project_name
        # 查询资源统计概览相关数据
        return resources_service.vpc_resource_statistic_list(query_params, page, page_size, sort_keys, sort_dirs)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        raise (HTTPException(status_code=400, detail="vpc resource statistic list error"))

@router.get("/resources/resource_detail_list", summary="租户下资源详情列表", description="查询指定租户或所有租户下资源详情列表")
async def resource_detail_list(resource_project_id: str = Query(None, description="租户ID. 其值为空时，查询所有租户下的资源"),
                               page: int = Query(1, description="页码"),
                               page_size: int = Query(10, description="页数量大小"),
                               sort_keys: str = Query(None, description="排序字段"),
                               sort_dirs: str = Query(None, description="排序方式"),
                               resource_name: str = Query(None, description="资源名称"),
                               resource_status: str = Query(None, description="资源状态"),
                               asset_name: str = Query(None, description="资产名称"),
                               asset_status: str = Query(None, description="资产状态"),
                               resource_user_name: str = Query(None, description="所属用户名称"),
                               resource_project_name: str = Query(None, description="所属租户名称"),):
    try:
        # 声明查询条件的dict
        query_params = {}
        if resource_name:
            query_params['resource_name'] = resource_name
        if resource_status:
            query_params['resource_status'] = resource_status
        if asset_name:
            query_params['asset_name'] = asset_name
        if asset_status:
            query_params['asset_status'] = asset_status
        if resource_user_name:
            query_params['resource_user_name'] = resource_user_name
        if resource_project_name:
            query_params['resource_project_name'] = resource_project_name
        # 查询资源统计概览相关数据
        return resources_service.resource_detail_list(resource_project_id, query_params, page, page_size, sort_keys, sort_dirs)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        raise HTTPException(status_code=400, detail="resource detail list error")

@router.get("/resources/statistics_overview", summary="查询租户资源统计概览视图数据", description="组装租户资源统计概览视图数据")
async def fetch_resource_statistic_overview_data():
    try:
        # 查询资源统计概览相关数据
        return resources_service.fetch_resource_statistic_overview_data()
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        raise HTTPException(status_code=400, detail="fetch resource statistic overview error")
