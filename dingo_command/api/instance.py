from fastapi import Query
from dingo_command.api.model.instance import InstanceRemoveObject, InstanceCreateObject

from dingo_command.services.instance import InstanceService
from dingo_command.services.custom_exception import Fail
from fastapi import APIRouter, HTTPException
    
router = APIRouter()
instance_service = InstanceService()

@router.get("/instance/list", summary="instance列表", description="instance列表")
async def list_instances(cluster_id:str = Query(None, description="集群id"),
        cluster_name:str = Query(None, description="集群名称"),
        type:str = Query(None, description="instance类型"),
        page: int = Query(1, description="页码"),
        page_size: int = Query(10, description="页数量大小"),
        sort_keys:str = Query(None, description="排序字段"),
        sort_dirs:str = Query(None, description="排序方式"),):
    try:
         # 声明查询条件的dict
        query_params = {}
        # 查询条件组装
        if cluster_name:
            query_params['cluster_name'] = cluster_name
        if type:
            query_params['type'] = type
        if cluster_id:
            query_params['cluster_id'] = cluster_id
        result = instance_service.list_instances(query_params, page,page_size, sort_keys, sort_dirs)
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="list instances error")

@router.get("/instance/{instance_id}", summary="获取instance详情", description="获取instance详情")
async def get_instance(instance_id:str):
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
async def create_instance(instance: InstanceCreateObject):
    try:
        # 创建instance，创建openstack种的虚拟机或者裸金属服务器，如果属于某个cluster就写入cluster_id
        result = instance_service.create_instance(instance)
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="create instance error")

@router.delete("/instance", summary="删除instance", description="删除instance")
async def delete_instance(instance_list_info: InstanceRemoveObject):
    try:
        # 删除某些instance，删除这个server，并在数据路中删除这个instance的数据信息
        result = instance_service.delete_instance(instance_list_info)
        return result
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="delete instance error")