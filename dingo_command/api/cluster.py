import os
import tempfile
from fastapi import BackgroundTasks, Query
from fastapi.responses import FileResponse
from dingo_command.api.model.cluster import ClusterObject

from dingo_command.services.cluster import ClusterService,TaskService
from dingo_command.services.custom_exception import Fail
from fastapi import APIRouter, HTTPException, Depends,Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    
router = APIRouter()
cluster_service = ClusterService()
task_service = TaskService()

# 创建安全机制
# Get token from X-Auth-Token header
async def get_token(x_auth_token: str = Header(None, alias="X-Auth-Token")):
    if x_auth_token is None:
        raise HTTPException(status_code=401, detail="X-Auth-Token header is missing")
    return x_auth_token

@router.post("/cluster", summary="创建k8s集群", description="创建k8s集群")
async def create_cluster(cluster_object:ClusterObject,token: str = Depends(get_token)):
    try:
        
        cluster_id = cluster_service.create_cluster(cluster_object,token)
        # 操作日志
        #SystemService.create_system_log(OperateLogApiModel(operate_type="create", resource_type="flow", resource_id=cluster_id, resource_name=cluster_object.name, operate_flag=True))
        return cluster_id
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="cluster create error")
    
@router.get("/cluster/list", summary="k8s集群列表", description="k8s集群列表")
async def list_cluster(id:str = Query(None, description="集群id"),
        name:str = Query(None, description="集群名称"),
        type:str = Query(None, description="集群类型"),
        page: int = Query(1, description="页码"),
        page_size: int = Query(10, description="页数量大小"),
        sort_keys:str = Query(None, description="排序字段"),
        sort_dirs:str = Query(None, description="排序方式"),):
    try:
         # 声明查询条件的dict
        query_params = {}
        # 查询条件组装
        if name:
            query_params['name'] = name
        if type:
            query_params['type'] = type
        query_params = {}
        # 查询条件组装
        if id:
            query_params['id'] = id
        if name:
            query_params['name'] = name
        if type:
            query_params['type'] = type
        result = ClusterService.list_clusters(id, query_params, page,page_size, sort_keys,sort_dirs)
        return result
    except Exception as e:
        return None
    
@router.get("/cluster/key", summary="下载key文件", description="下载key文件")
async def get_cluster_private_key(cluster_id:str = Query(None, description="集群id"),
                            instance_id:str = Query(None, description="集群id")):
    """获取集群的私钥内容"""
    if not cluster_id and not instance_id:
        return None
    try:
        # 根据id查询集群
        cs=ClusterService()
        private_key = cs.get_key_file(cluster_id, instance_id)
        if private_key is None:
            raise HTTPException(status_code=400, detail="Key not found")
        filename = "id_rsa.pem"
        fd, temp_path = tempfile.mkstemp()
        with os.fdopen(fd, 'w') as tmp:
            tmp.write(private_key)
            os.chmod(temp_path, 0o600)
       
        # 返回文件响应
        return FileResponse(
            path=temp_path,
            filename=filename,
            media_type="application/octet-stream",
            #background=BackgroundTasks([lambda: os.unlink(temp_path)])  # 请求完成后删除临时文件
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise e
    
@router.get("/progress", summary="创建k8s集群进度", description="创建k8s集群进度")
async def get_cluster_progress(cluster_id:str):
    try:
        # 集群信息存入数据库
        result =task_service.get_tasks(cluster_id)
        # 操作日志
        #SystemService.create_system_log(OperateLogApiModel(operate_type="create", resource_type="flow", resource_id=result, resource_name=cluster_object.name, operate_flag=True))
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="get cluster error")
    
@router.get("/cluster/params", summary="获取k8s集群参数", description="获取k8s集群参数")
async def list_params():
    try:
        # 集群信息存入数据库
        result =cluster_service.get_create_params()
        # 操作日志
        #SystemService.create_system_log(OperateLogApiModel(operate_type="create", resource_type="flow", resource_id=result, resource_name=cluster_object.name, operate_flag=True))
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="get cluster param error")
    
@router.get("/cluster/{cluster_id}", summary="获取k8s集群详情", description="获取k8s集群详情")
async def get_cluster(cluster_id:str, token: str = Depends(get_token)):
    try:
        # 集群信息存入数据库
        result = cluster_service.get_cluster(cluster_id)
        # 操作日志
        #SystemService.create_system_log(OperateLogApiModel(operate_type="create", resource_type="flow", resource_id=result, resource_name=cluster_object.name, operate_flag=True))
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="get cluster error")

@router.delete("/cluster/{cluster_id}", summary="删除k8s集群", description="删除k8s集群")
async def delete_cluster(cluster_id:str, token: str = Depends(get_token)):
    try:
        # 集群信息存入数据库
        result = cluster_service.delete_cluster(cluster_id, token)
        # 操作日志
        #SystemService.create_system_log(OperateLogApiModel(operate_type="create", resource_type="flow", resource_id=result, resource_name=cluster_object.name, operate_flag=True))
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="get cluster error")
