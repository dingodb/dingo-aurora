import os
import tempfile
from typing import List
from fastapi import Query
from fastapi.responses import FileResponse
from dingo_command.api.model.cluster import ClusterObject, NodeConfigObject
from dingo_command.common.nova_client import NovaClient
from dingo_command.services.cluster import ClusterService,TaskService, master_flvaor
from dingo_command.services.custom_exception import Fail
from fastapi import APIRouter, HTTPException, Depends, Header

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
async def create_cluster(cluster_object:ClusterObject, token: str = Depends(get_token)):
    try:
        NovaClient(token)
        if cluster_object.type == "kubernetes":
            master_config = {}
            master_config["count"] = cluster_object.kube_info.number_master
            master_config["role"] = "master"
            master_config["type"] = "vm"
            master_config["flavor_id"] = master_flvaor
            cluster_object.node_config.append(NodeConfigObject(**master_config))
        cluster_id = cluster_service.create_cluster(cluster_object,token)
        # 操作日志
        #SystemService.create_system_log(OperateLogApiModel(operate_type="create", resource_type="flow", resource_id=cluster_id, resource_name=cluster_object.name, operate_flag=True))
        return cluster_id
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except  HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
    
@router.get("/cluster/list", summary="k8s集群列表", description="k8s集群列表")
async def list_cluster(id:str = Query(None, description="集群id"),
        name:str = Query(None, description="集群名称"),
        status:str = Query(None, description="集群状态"),
        project_id: str = Query(None, description="项目id"),
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
        if project_id:
            query_params['project_id'] = project_id
        if type:
            query_params['type'] = type
        if id:
            query_params['id'] = id
        if status:
            query_params['status'] = status

        result = cluster_service.list_clusters(query_params, page,page_size, sort_keys,sort_dirs)
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
        private_key = cluster_service.get_key_file(cluster_id, instance_id)
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

@router.get("/cluster/progress/param", summary="创建k8s集群进度", description="创建k8s集群进度")
async def get_cluster_progress(type:str):
    try:
        # 集群信息存入数据库
        result =task_service.get_tasks_param(type)
        # 操作日志
        #SystemService.create_system_log(OperateLogApiModel(operate_type="create", resource_type="flow", resource_id=result, resource_name=cluster_object.name, operate_flag=True))
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="get cluster progress param error")

@router.get("/cluster/progress", summary="创建k8s集群进度", description="创建k8s集群进度")
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
        raise HTTPException(status_code=400, detail=f"get cluster progress error {str(e)}")

@router.get("/cluster/delete/progress", summary="创建k8s集群进度", description="创建k8s集群进度")
async def get_cluster_progress(cluster_id:str):
    try:
        # 集群信息存入数据库
        result =task_service.get_delete_tasks(cluster_id)
        # 操作日志
        #SystemService.create_system_log(OperateLogApiModel(operate_type="create", resource_type="flow", resource_id=result, resource_name=cluster_object.name, operate_flag=True))
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"get delete cluster progress error {str(e)}")
    
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
async def get_cluster(cluster_id:str):
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
        raise HTTPException(status_code=400, detail=f"get cluster error {str(e)}")

@router.delete("/cluster/{cluster_id}", summary="删除k8s集群", description="删除k8s集群")
async def delete_cluster(cluster_id:str, token: str = Depends(get_token)):
    try:
        NovaClient(token)
        # 集群信息存入数据库
        result = cluster_service.get_cluster(cluster_id)
        if not result:
            raise HTTPException(status_code=400, detail="the cluster does not exist, please check")
        if result.status == "creating":
            raise HTTPException(status_code=400, detail="the cluster is creating, please wait")
        if result.status == "deleting":
            raise HTTPException(status_code=400, detail="the cluster is deleting, please wait")
        if result.status == "scaling":
            raise HTTPException(status_code=400, detail="the cluster is scaling, please wait")
        if result.status == "removing":
            raise HTTPException(status_code=400, detail="the cluster is removing, please wait")
        result = cluster_service.delete_cluster(cluster_id, token)
        # 操作日志
        #SystemService.create_system_log(OperateLogApiModel(operate_type="create", resource_type="flow", resource_id=result, resource_name=cluster_object.name, operate_flag=True))
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except  HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"delete cluster error {str(e)}")
    
    
@router.post("/cluster/{cluster_id}/node", summary="增加已有节点", description="增加已有节点")
async def add_node(cluster_id:str, server_ids: List[str], token: str = Depends(get_token)):
    try:
            
        # 集群信息存入数据库
        result = cluster_service.get_cluster(cluster_id)

        if not result:
            raise HTTPException(status_code=400, detail="the cluster does not exist, please check")
        if result.status == "creating":
            raise HTTPException(status_code=400, detail="the cluster is creating, please wait")
        if result.status == "deleting":
            raise HTTPException(status_code=400, detail="the cluster is deleting, please wait")
        if result.status == "scaling":
            raise HTTPException(status_code=400, detail="the cluster is scaling, please wait")
        if result.status == "removing":
            raise HTTPException(status_code=400, detail="the cluster is removing, please wait")
        
        # 通过server_ids查询虚拟机信息
        server_details = []
        for server_id in server_ids:
            try:
                nova_client = NovaClient()
                server_detail = nova_client.nova_get_server_detail(server_id)
                #根据server_detail对应的网络信息，是否与集群的网络信息匹配
                if not server_detail:
                    raise HTTPException(status_code=400, detail=f"Server {server_id} not found")
                if not server_detail.get("addresses"):
                    raise HTTPException(status_code=400, detail=f"Server {server_id} has no networks")
                # 检查网络是否匹配
                # 获取第一个网络的地址信息
                first_network = list(server_detail["addresses"].keys())
                if not any(net == result.network_config.admin_network_name for net in first_network):
                    raise HTTPException(status_code=400, detail=f"Server {server_id} network does not match the cluster network")
                server_details.append(server_detail)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to get server {server_id} details: {str(e)}")
        
        # 调用添加节点的服务方法
        result = cluster_service.add_existing_nodes_to_cluster(cluster_id, server_details, token)
        
        return result
        
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except  HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"add node error {str(e)}")