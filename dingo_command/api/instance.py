from fastapi import Query, Header, Depends
from fastapi import APIRouter, HTTPException
from dingo_command.api.model.instance import InstanceCreateObject, OpenStackConfigObject
from dingo_command.api.model.cluster import ScaleNodeObject, NodeRemoveObject
from dingo_command.services.cluster import ClusterService
from dingo_command.services.instance import InstanceService
from dingo_command.services.custom_exception import Fail
from dingo_command.db.engines.mysql import get_session
from dingo_command.db.models.instance.models import Instance

router = APIRouter()
instance_service = InstanceService()


async def get_token(x_auth_token: str = Header(None, alias="X-Auth-Token")):
    if x_auth_token is None:
        raise HTTPException(status_code=401, detail="X-Auth-Token header is missing")
    return x_auth_token


@router.get("/instance/list", summary="instance列表", description="instance列表")
async def list_instances(cluster_id: str = Query(None, description="集群id"),
                         cluster_name: str = Query(None, description="集群名称"),
                         type: str = Query(None, description="instance类型"),
                         name: str = Query(None, description="instance名称"),
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
        if name:
            query_params['name'] = name
        if type:
            query_params['type'] = type
        if status:
            query_params['status'] = status
        if cluster_id:
            query_params['cluster_id'] = cluster_id
        result = instance_service.list_instances(query_params, page, page_size, sort_keys, sort_dirs)
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="list instances error")


@router.get("/instance/{instance_id}", summary="获取instance详情", description="获取instance详情")
async def get_instance(instance_id: str):
    try:
        # 获取某个节点的信息
        result = instance_service.get_instance(instance_id)
        # 操作日志
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="get instance error")


@router.post("/instance", summary="创建instance", description="创建instance")
async def create_instance(instance: InstanceCreateObject, token: str = Depends(get_token)):
    try:
        # 创建instance，创建openstack种的虚拟机或者裸金属服务器，如果属于某个cluster就写入cluster_id
        if not instance.openstack_info.token:
            instance.openstack_info.token = token
        result = instance_service.create_instance(instance)
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="create instance error")


@router.delete("/instance/{instance_id}", summary="删除instance", description="删除instance")
async def delete_instance(instance_id: str, token: str = Depends(get_token)):
    try:
        # 获取某个节点的信息
        instance = instance_service.get_instance(instance_id)
        if not instance.get("data"):
            return {"data": None}
        if not instance.get("data").server_id:
            session = get_session()
            with session.begin():
                db_instance = session.get(Instance, instance_id)
                session.delete(db_instance)
            return {"data": "success"}
        if instance.get("data").status == "deleting":
            raise HTTPException(status_code=400, detail="the instance is deleting, please wait")
        # 删除某些instance，删除这个server，并在数据路中删除这个instance的数据信息
        openstack_info = OpenStackConfigObject()
        openstack_info.token = token
        openstack_info.project_id = instance.get("data").project_id
        result = instance_service.delete_instance(openstack_info, instance.get("data"))
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="delete instance error")


@router.post("/baremetal", summary="扩容baremetal集群", description="扩容baremetal集群")
async def create_baremetal(baremetal: ScaleNodeObject, token: str = Depends(get_token)):
    # 先检查下是否有正在处于扩容的状态，如果是就直接返回
    cluster_service = ClusterService()
    cluster_info = cluster_service.get_cluster(baremetal.id)
    if not cluster_info:
        raise HTTPException(status_code=400, detail="the cluster does not exist, please check")
    if cluster_info.status == "creating":
        raise HTTPException(status_code=400, detail="the cluster is creating, please wait")
    if cluster_info.status == "scaling":
        raise HTTPException(status_code=400, detail="the cluster is scaling, please wait")
    if cluster_info.status == "deleting":
        raise HTTPException(status_code=400, detail="the cluster is deleting, please wait")
    if cluster_info.status == "removing":
        raise HTTPException(status_code=400, detail="the cluster is removing, please wait")
    try:
        # 创建instance，创建openstack种的虚拟机或者裸金属服务器，如果属于某个cluster就写入cluster_id
        result = instance_service.create_baremetal(cluster_info, baremetal, token)
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="create instance error")


@router.post("/baremetal/remove", summary="缩容baremetal", description="缩容baremetal")
async def delete_node(node_info: NodeRemoveObject, token: str = Depends(get_token)):
    try:
        # 先检查下是否有正在处于缩容的状态，如果是就直接返回
        cluster_service = ClusterService()
        result = cluster_service.get_cluster(node_info.cluster_id)
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

        # 缩容某些节点
        node_list = []
        for id in node_info.node_list:
            node = instance_service.get_instance(id)
            if not node.get("data"):
                continue
            node_list.append(node.get("data"))
        if not node_list:
            raise HTTPException(status_code=400, detail="there are no nodes, please check")
        result = instance_service.delete_baremetal(node_info.cluster_id, result.name, node_list, token)
        if result is not None:
            return {"data": result}
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="remove node error")