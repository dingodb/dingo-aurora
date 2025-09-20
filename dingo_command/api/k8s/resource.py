import json
import ctypes
import os
import re
import traceback
from fastapi import FastAPI, Depends, HTTPException, Query, Path
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Header
from kubernetes.dynamic import DynamicClient
from pydantic import BaseModel
# from models import K8sResourceQueryParams #, PodResponse, DeploymentResponse, GenericResourceResponse
from dingo_command.common import k8s_client
from dingo_command.common.k8s_client import K8sClient  # Adjust the import path as needed
from dingo_command.services.cluster import ClusterService
router = APIRouter()
not_delete_ns = ("default", "kube-node-lease", "kube-public", "kube-system")

class CreateResourceRequest(BaseModel):
    cluster_id: str = "default"
    project_id: str
    user_id: str
    template: Dict[str, Any]

class ResourceResponse(BaseModel):
    name: str
    namespace: Optional[str]
    creation_time: str
    details: Dict[str, Any]

class ListResourcesResponse(BaseModel):
    total: int
    resources: List[ResourceResponse]

libc = ctypes.CDLL("libc.so.6")

def set_netns(netns_name):
    """
    将当前线程切换到指定的网络命名空间。
    libc.setns() 系统调用需要文件描述符和命名空间标识。
    """
    netns_path = f"/run/netns/{netns_name}"
    if not os.path.exists(netns_path):
        #raise FileNotFoundError(f"网络命名空间 {netns_name} 不存在于 {netns_path}")
        print(f"网络命名空间 {netns_name} 不存在于 {netns_path}")
        return
    current_ns_fd = os.open("/proc/self/ns/net", os.O_RDONLY)
    fd = os.open(netns_path, os.O_RDONLY)
    try:
        if libc.setns(fd, 0) == -1:
            raise OSError("setns 系统调用失败")
        print(f"已切换到网络命名空间: {netns_name}")
        # 返回一个恢复函数
        def restore_ns():
            if libc.setns(current_ns_fd, 0) == -1:
                raise OSError("恢复原始网络命名空间失败")
            print("已恢复到原始网络命名空间")
            os.close(current_ns_fd)
        
        return restore_ns
    finally:
        os.close(fd)
def get_cluster_info(cluster_id: str):
        # 1. 通过cluster_id查询集群信息
    cluster_service = ClusterService()
    cluster = cluster_service.get_cluster(cluster_id)
    
    if not cluster:
        print("Cluster not found:", cluster_id)
        raise HTTPException(status_code=404, detail=f"集群 {cluster_id} 不存在")
    
    if cluster.status != "running":
        print("Cluster is not running:", cluster_id)
        raise HTTPException(status_code=400, detail=f"集群 {cluster_id} 状态不是运行中，当前状态: {cluster.status}")
    
    # 2. 获取kubeconfig内容
    # 假设kubeconfig存储在cluster.kubeconfig字段中

    if not hasattr(cluster.kube_info, 'kube_config') or not cluster.kube_info:
        print("kube_config is None:", cluster_id)
        raise HTTPException(status_code=400, detail=f"集群 {cluster_id} 的kubeconfig不存在")
    return cluster.kube_info.kube_config, "qdhcp-" + str(cluster.network_config.admin_network_id)

def get_k8s_client_by_cluster(kube_config: str) -> K8sClient:
    """根据cluster_id获取对应的kubeconfig，然后获取kubeclient"""
    print("get_k8s_client_by_cluster:", kube_config)
    try:
        # 4. 使用kubeconfig内容创建K8sClient
        k8s_client = K8sClient(kubeconfig_content=kube_config)

        return k8s_client
            
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取K8s客户端失败: {str(e)}")
    
def get_k8s_client() -> K8sClient:
    """依赖注入 K8sClient 实例."""
    try:
        # 实际部署时，kubeconfig_path 可以通过环境变量或配置管理
        return K8sClient(kubeconfig_path=None) # 例如，None 意味着尝试默认路径或集群内
    except ConnectionError as e:
        raise HTTPException(status_code=500, detail=f"无法连接到 Kubernetes 集群: {e}")

# 创建安全机制
# Get token from X-Auth-Token header
async def get_token(x_auth_token: str = Header(None, alias="X-Auth-Token")):
    if x_auth_token is None:
        raise HTTPException(status_code=401, detail="X-Auth-Token header is missing")
    return x_auth_token

## Kubernetes 资源查询接口

### 1. 通用资源查询接口

@router.post("/k8s/namespace/{namespace}/{resource_type}", summary="创建资源", description="创建资源")
async def create_resources(
    resource: CreateResourceRequest,
    namespace: str = Path(..., description="Kubernetes 命名空间"),
    resource_type: str = Path(..., description="Kubernetes 资源类型"),
    token: str = Depends(get_token),
):
    #根据cluster_id获取对应的kubeconfig，然后获取kubeclient

    """
    根据提供的参数查询 Kubernetes 资源。
    """
    restore_ns = None
    try:
        kube_config, netns = get_cluster_info(resource.cluster_id)
        
        if netns:
            restore_ns = set_netns(netns)
        k8sclient = get_k8s_client_by_cluster(kube_config)
        resources = k8sclient.create_resource(
            resource_body=resource.template,
            resource_type=resource_type,
            namespace=namespace,
            
        )
    except Exception as e:
        traceback.print_exc()
        response_body = getattr(getattr(e, 'response', None), 'body', str(e))
        match = re.search(r"HTTP response body: b?['\"]?(.*?)[\"']?\\n", response_body, re.DOTALL)
        if match:
            body_str = match.group(1)
            # 处理转义字符
            body_str = body_str.encode('utf-8').decode('unicode_escape')
            # 解析 JSON
            body_json = json.loads(body_str)
            raise HTTPException(status_code=500, detail=f"{body_json}")
        raise HTTPException(status_code=500, detail=f"{response_body}")
    finally:
        if restore_ns:
            restore_ns()
    return JSONResponse(content=jsonable_encoder(resources)) # 确保复杂对象可以被序列化



@router.post("/k8s/{resource_type}", summary="创建资源", description="创建资源")
async def create_resources(
    resource: CreateResourceRequest,
    resource_type: str = Path(..., description="Kubernetes 资源类型"),
    token: str = Depends(get_token),
):
    #根据cluster_id获取对应的kubeconfig，然后获取kubeclient

    """
    根据提供的参数查询 Kubernetes 资源。
    """
    restore_ns = None
    try:
        kube_config, netns = get_cluster_info(resource.cluster_id)
        
        if netns:
            restore_ns = set_netns(netns)
        k8sclient = get_k8s_client_by_cluster(kube_config)
        resources = k8sclient.create_resource(
            resource_body=resource.template,
            resource_type=resource_type
            
        )
    except Exception as e:
        traceback.print_exc()
        response_body = getattr(getattr(e, 'response', None), 'body', str(e))
        match = re.search(r"HTTP response body: b?['\"]?(.*?)[\"']?\\n", response_body, re.DOTALL)
        if match:
            body_str = match.group(1)
            # 处理转义字符
            body_str = body_str.encode('utf-8').decode('unicode_escape')
            # 解析 JSON
            body_json = json.loads(body_str)
            raise HTTPException(status_code=500, detail=f"{body_json}")
        raise HTTPException(status_code=500, detail=f"{response_body}")
    finally:
        if restore_ns:
            restore_ns()
    return JSONResponse(content=jsonable_encoder(resources)) # 确保复杂对象可以被序列化

@router.get("/k8s/{resource}/list", summary="查询资源列表", description="查询资源列表")
async def list_resources(
    cluster_id:str = Query(None, description="集群id"),
    namespace:str = Query(None, description="集群id"),
    resource: str = Path(..., description="Kubernetes 资源类型"),
    label_selector: str = Query(None, description="标签选择器"),
    search_terms: str = Query(None, description="搜索关键词，多个关键词用逗号分隔"),
    name: str = Query(None, description="搜索关键词"),
    page: str = Query(None, description="页码"),
    page_size: str = Query(None, description="每页大小"),
    sort_keys: str = Query(None, description="排序字段"),
    sort_dirs: str = Query(None, description="排序顺序"),
    token: str = Depends(get_token),
):
    #根据cluster_id获取对应的kubeconfig，然后获取kubeclient

    """
    根据提供的参数查询 Kubernetes 资源。
    """
    restore_ns = None
    try:
        kube_config, netns = get_cluster_info(cluster_id)
        
        if netns:
            restore_ns = set_netns(netns)
        k8sclient = get_k8s_client_by_cluster(kube_config)
        #将search_terms按照逗号分开
        search_terms_list = search_terms.split(",") if search_terms else []
        search_terms_list = ["name=" + name] + search_terms_list if name else search_terms_list
        resources = k8sclient.list_resource(
            resource_type=resource,
            namespace=namespace,
            search_terms=search_terms_list,
            label_selector=label_selector,
            page=int(page),
            page_size=int(page_size),
            sort_by=sort_keys,
            sort_order=sort_dirs
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"查询资源 '{resource}' 失败。")
    finally:
        if restore_ns:
            restore_ns()
    #将resources转为json返回
    return resources

@router.get("/k8s/namespace/{namespace}/{resource}/{name}", summary="查询资源", description="查询资源")
async def get_resources(
    cluster_id:str = Query(None, description="集群id"),
    name: str = Path(..., description="Kubernetes 资源名称"),
    namespace: str = Path(..., description="Kubernetes 资源名称"),
    resource: str = Path(..., description="Kubernetes 资源类型"),
    token: str = Depends(get_token),
):
    #根据cluster_id获取对应的kubeconfig，然后获取kubeclient

    """
    根据提供的参数查询 Kubernetes 资源。
    """
    restore_ns = None
    try:
        kube_config, netns = get_cluster_info(cluster_id)
       
        if netns:
            restore_ns = set_netns(netns)
        k8sclient = get_k8s_client_by_cluster(kube_config)
        resources = k8sclient.get_resource(
            resource_type=resource,
            name=name,
            api_version=None,
            namespace=namespace
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"查询资源 '{resource}' 失败。")
    finally:
        if restore_ns:
            restore_ns()
    return JSONResponse(content=jsonable_encoder(resources)) # 确保复杂对象可以被序列化

@router.get("/k8s/{resource}/{name}?cluster_id=xxxx", summary="获取资源", description="获取资源")
async def get_resources(
    cluster_id:str = Query(None, description="集群id"),
    name: str = Path(..., description="Kubernetes 资源名称"),
    resource: str = Path(..., description="Kubernetes 资源类型"),
    token: str = Depends(get_token),
):
    #根据cluster_id获取对应的kubeconfig，然后获取kubeclient

    """
    根据提供的参数查询 Kubernetes 资源。
    """
    restore_ns = None
    try:
        kube_config, netns = get_cluster_info(cluster_id)
        
        if netns:
            restore_ns = set_netns(netns)
        k8sclient = get_k8s_client_by_cluster(kube_config)

        resources = k8sclient.create_resource(
            resource_type=resource,
            name=name,
            api_version=None
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"查询资源 '{resource}' 失败。")
    finally:
        if restore_ns:
            restore_ns()
    return JSONResponse(content=jsonable_encoder(resources)) # 确保复杂对象可以被序列化


@router.delete("/k8s/{resource}/{name}", summary="查询资源", description="查询资源")
async def delete_resources(
    cluster_id:str = Query(None, description="集群id"),
    name: str = Path(..., description="Kubernetes 资源名称"),
    resource: str = Path(..., description="Kubernetes 资源类型"),
    token: str = Depends(get_token),
):
    #根据cluster_id获取对应的kubeconfig，然后获取kubeclient

    """
    根据提供的参数查询 Kubernetes 资源。
    """
    restore_ns = None
    try:
        kube_config, netns = get_cluster_info(cluster_id)
        
        if netns:
            restore_ns = set_netns(netns)
        if resource == "namespaces" and name in not_delete_ns:
            raise HTTPException(status_code=403, detail="The namespace resources automatically created by the k8s cluster "
                                                        "cannot be deleted")
        k8sclient = get_k8s_client_by_cluster(kube_config)
        resources = k8sclient.delete_resource(
            resource_type=resource,
            name=name,
            api_version=None
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"查询资源 '{resource}' 失败。")
    finally:
        if restore_ns:
            restore_ns()
    return JSONResponse(content=jsonable_encoder(resources)) # 确保复杂对象可以被序列化

@router.delete("/k8s/namespace/{namespace}/{resource}/{name}", summary="查询资源", description="查询资源")
async def delete_resources(
    cluster_id:str = Query(None, description="集群id"),
    name: str = Path(..., description="Kubernetes 资源名称"),
    namespace: str = Path(..., description="Kubernetes 资源名称"),
    resource: str = Path(..., description="Kubernetes 资源类型"),
    token: str = Depends(get_token),
):
    #根据cluster_id获取对应的kubeconfig，然后获取kubeclient

    """
    根据提供的参数查询 Kubernetes 资源。
    """
    try:
        kube_config, netns = get_cluster_info(cluster_id)
        restore_ns = None
        
        if resource == "namespaces" and name in not_delete_ns:
            raise HTTPException(status_code=403, detail="The namespace resources automatically created by the k8s cluster "
                                                        "cannot be deleted")
        if netns:
            restore_ns = set_netns(netns)
        k8sclient = get_k8s_client_by_cluster(kube_config)
        resources = k8sclient.delete_resource(
            resource_type=resource,
            name=name,
            api_version=None,
            namespace=namespace
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"delete dresource '{resource}' error")
    finally:
        if restore_ns:
            restore_ns()
    return JSONResponse(content=jsonable_encoder(resources)) # 确保复杂对象可以被序列化


@router.delete("/k8s/{resource}/{name}", summary="delete dresource '{resource}' error")
async def delete_resources(
    cluster_id:str = Query(None, description="集群id"),
    name: str = Path(..., description="Kubernetes 资源名称"),
    resource: str = Path(..., description="Kubernetes 资源类型"),
    token: str = Depends(get_token),
):
    #根据cluster_id获取对应的kubeconfig，然后获取kubeclient

    """
    根据提供的参数查询 Kubernetes 资源。
    """
    restore_ns = None
    try:
        kube_config, netns = get_cluster_info(cluster_id)
        
        if resource == "namespaces" and name in not_delete_ns:
            raise HTTPException(status_code=403, detail="The namespace resources automatically created by the k8s cluster "
                                                        "cannot be deleted")
        if netns:
            restore_ns = set_netns(netns)
        k8sclient = get_k8s_client_by_cluster(kube_config)
        resources = k8sclient.delete_resource(
            resource_type=resource,
            name=name,
            api_version=None
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"delete dresource '{resource}' error")
    finally:
        if restore_ns:
            restore_ns()
    return JSONResponse(content=jsonable_encoder(resources)) # 确保复杂对象可以被序列化

@router.put("/k8s/{resource_type}/{name}", summary="更新资源", description="更新资源")
async def update_resources(
    resource: CreateResourceRequest,
    resource_type: str = Path(..., description="Kubernetes 资源名称"),
    name: str = Path(..., description="Kubernetes 资源名称"),
    token: str = Depends(get_token),
):
    #根据cluster_id获取对应的kubeconfig，然后获取kubeclient

    """
    根据提供的参数查询 Kubernetes 资源。
    """
    restore_ns = None
    try:
        kube_config, netns = get_cluster_info(resource.cluster_id)
    
        if netns:
            restore_ns = set_netns(netns)
        k8sclient = get_k8s_client_by_cluster(kube_config)
        resources = k8sclient.update_resource(
            resource_body=resource.template,
            resource_type=resource_type,
            name=name
        )
    except Exception as e:
        traceback.print_exc()
        response_body = getattr(getattr(e, 'response', None), 'body', str(e))
        match = re.search(r"HTTP response body: b?['\"]?(.*?)[\"']?\\n", response_body, re.DOTALL)
        if match:
            body_str = match.group(1)
            # 处理转义字符
            body_str = body_str.encode('utf-8').decode('unicode_escape')
            # 解析 JSON
            body_json = json.loads(body_str)
            raise HTTPException(status_code=500, detail=f"{body_json}")
        raise HTTPException(status_code=500, detail=f"{response_body}")
    finally:
        if restore_ns:
            restore_ns()
    return JSONResponse(content=jsonable_encoder(resources)) # 确保复杂对象可以被序列化

@router.put("/k8s/namespace/{namespace}/{resource_type}/{name}", summary="更新资源", description="更新资源")
async def update_resources(

    resource: CreateResourceRequest,
    namespace: str = Path(..., description="Kubernetes 命名空间"),
    resource_type: str = Path(..., description="Kubernetes 资源类型"),
    name: str = Path(..., description="Kubernetes 资源名称"),
    token: str = Depends(get_token),
):
    #根据cluster_id获取对应的kubeconfig，然后获取kubeclient

    """
    根据提供的参数查询 Kubernetes 资源。
    """
    restore_ns = None
    try:
        kube_config, netns = get_cluster_info(resource.cluster_id)
        
        if netns:
            restore_ns = set_netns(netns)
        k8sclient = get_k8s_client_by_cluster(kube_config)
        resources = k8sclient.update_resource(
            resource_body=resource.template,
            resource_type=resource_type,
            namespace=namespace,
            name=name
        )
    except Exception as e:
        traceback.print_exc()
        response_body = getattr(getattr(e, 'response', None), 'body', str(e))
        match = re.search(r"HTTP response body: b?['\"]?(.*?)[\"']?\\n", response_body, re.DOTALL)
        if match:
            body_str = match.group(1)
            # 处理转义字符
            body_str = body_str.encode('utf-8').decode('unicode_escape')
            # 解析 JSON
            body_json = json.loads(body_str)
            raise HTTPException(status_code=500, detail=f"{body_json}")
        raise HTTPException(status_code=500, detail=f"{response_body}")
    finally:
        if restore_ns:
            restore_ns()
    return JSONResponse(content=jsonable_encoder(resources)) # 确保复杂对象可以被序列化