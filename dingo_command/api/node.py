from fastapi import Query, Header, Depends
from dingo_command.api.model.cluster import ScaleNodeObject

from dingo_command.services.cluster import ClusterService
from dingo_command.services.node import NodeService
from dingo_command.services.custom_exception import Fail
from fastapi import APIRouter, HTTPException

router = APIRouter()
node_service = NodeService()

async def get_token(x_auth_token: str = Header(None, alias="X-Auth-Token")):
    if x_auth_token is None:
        raise HTTPException(status_code=401, detail="X-Auth-Token header is missing")
    return x_auth_token

@router.get("/node/list", summary="k8s集群节点列表", description="k8s集群节点列表")
async def list_nodes(cluster_id: str = Query(None, description="集群id"),
                     cluster_name: str = Query(None, description="集群名称"),
                     type: str = Query(None, description="节点类型"),
                     status: str = Query(None, description="status状态"),
                     page: int = Query(1, description="页码"),
                     page_size: int = Query(10, description="页数量大小"),
                     sort_keys: str = Query(None, description="排序字段"),
                     sort_dirs: str = Query(None, description="排序方式"), ):
    try:
        # 声明查询条件的dict
        query_params = {}
        # 查询条件组装
        if cluster_name:
            query_params['cluster_name'] = cluster_name
        if type:
            query_params['type'] = type
        if status:
            query_params['status'] = status
        # 查询条件组装
        if cluster_id:
            query_params['cluster_id'] = cluster_id
        if type:
            query_params['type'] = type
        result = node_service.list_nodes(query_params, page, page_size, sort_keys, sort_dirs)
        return result
    except Exception as e:
        return None


@router.get("/node/{node_id}", summary="获取k8s集群节点详情", description="获取k8s集群节点详情")
async def get_node(node_id: str):
    try:
        # 获取某个节点的信息
        result = node_service.get_node(node_id)
        # 操作日志
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="get cluster error")


@router.post("/node", summary="扩容节点", description="扩容节点")
async def create_node(cluster: ScaleNodeObject, token: str = Depends(get_token)):
    # 先检查下是否有正在处于扩容的状态，如果是就直接返回
    cluster_service = ClusterService()
    cluster_info = cluster_service.get_cluster(cluster.id)
    if not cluster_info:
        raise HTTPException(status_code=400, detail="the cluster does not exist, please check")
    if cluster_info.status == "creating":
        raise HTTPException(status_code=400, detail="the cluster is creating, please wait")
    if cluster_info.status == "scaling":
        raise HTTPException(status_code=400, detail="the cluster is scaling, please wait")
    try:
        # 创建节点（扩容节点）
        result = node_service.create_node(cluster_info, cluster, token)
        return {"data": result}
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="scale node error")


@router.delete("/node/{node_id}", summary="缩容节点", description="缩容节点")
async def delete_node(node_id: str):
    data = node_service.get_node(node_id)
    if data.get("data") is not None:
        node = data.get("data")
        # 先检查下是否有正在处于缩容的状态，如果是就直接返回
        cluster_service = ClusterService()
        result = cluster_service.get_cluster(node.cluster_id)
        if not result:
            raise HTTPException(status_code=400, detail="the cluster does not exist, please check")
        if result.status == "creating":
            raise HTTPException(status_code=400, detail="the cluster is creating, please wait")
        try:
            # 缩容某些节点
            result = node_service.delete_node(node)
            if result is not None:
                return {"data": result}
        except Fail as e:
            raise HTTPException(status_code=400, detail=e.error_message)
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=400, detail="delete node error")
    else:
        raise HTTPException(status_code=400, detail="can not find the node, please check")
