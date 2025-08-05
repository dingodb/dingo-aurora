from typing import Union
from fastapi import Query, Header, Depends
from fastapi import APIRouter, HTTPException, BackgroundTasks
from dingo_command.api.model.cluster import ScaleNodeObject, NodeRemoveObject
from dingo_command.api.model.chart import CreateRepoObject, CreateAppObject
from dingo_command.services.cluster import ClusterService, TaskService
from dingo_command.services.chart import ChartService, create_harbor_repo
from dingo_command.services.custom_exception import Fail
from dingo_command.common.nova_client import NovaClient
from dingo_command.utils.helm import util

router = APIRouter()
chart_service = ChartService()


# 先判断我们的全局harbor是否存在，不存在就创建
create_harbor_repo()

@router.post("/repo", summary="helm的repo仓库", description="创建helm的repo仓库")
async def create_repo(repo: CreateRepoObject, background_tasks: BackgroundTasks):
    try:
        # 1、判断参数是否合法
        chart_service.check_repo_args(repo)
        # 2、判断http和https是否是合法的url以及oci是否是合法的url
        # 2、添加创建repo的逻辑
        # repo的name是唯一的，不能相同
        background_tasks.add_task(chart_service.create_repo, repo)
        return {"status": "create repo started, please wait"}
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"create repo error: {str(e)}")


@router.get("/repo/list", summary="helm的repo仓库列表", description="显示helm的repo仓库列表")
async def list_repos(cluster_id: str = Query(None, description="集群id"),
                     status: str = Query(None, description="status状态"),
                     name: str = Query(None, description="名称"),
                     is_global: bool = Query(None, description="名称"),
                     id: str = Query(None, description="id"),
                     page: int = Query(1, description="页码"),
                     page_size: int = Query(10, description="页数量大小"),
                     sort_dirs:str = Query(None, description="排序方式"),
                     sort_keys: str = Query(None, description="排序字段")):
    try:
        # 声明查询条件的dict
        query_params = {}
        # 查询条件组装
        if name:
            query_params['name'] = name
        if is_global is not None:
            query_params['is_global'] = is_global
        if status:
            query_params['status'] = status
        if id:
            query_params['id'] = id
        if status:
            query_params['status'] = status
        if cluster_id:
            query_params['cluster_id'] = cluster_id
        # 显示repo列表的逻辑
        return chart_service.list_repos(query_params, page, page_size, sort_keys, sort_dirs)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"list repos error: {str(e)}")


@router.put("/repo/{repo_id}", summary="更新repo的仓库配置", description="更新repo的仓库配置")
async def update_repo(repo_id: Union[str, int], repo_data: CreateRepoObject):
    try:
        # 更新repo仓库的配置
        # 1、先判断repo的url是否改变了，如果改变了就需要把原来的repo的charts应用全部删除，然后再添加新的repo的charts应用
        # 2、如果相同就不需要更换charts应用，只需要修改repo的配置即可，repo_id是不需要修改的
        # 3、如果不相同就需要删除原来的repo的charts应用，然后再添加新的repo的charts应用
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"update repo error: {str(e)}")

@router.get("/repo/{repo_id}", summary="获取某个repo的仓库信息", description="获取某个repo的仓库信息")
async def get_repo(repo_id: Union[str, int]):
    try:
        # 获取指定repo仓库的配置
        return chart_service.get_repo_from_id(repo_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"get repo error: {str(e)}")

@router.delete("/repo/{repo_id}", summary="删除某个repo的仓库", description="删除某个repo的仓库")
async def delete_repo(repo_id: Union[str, int]):
    try:
        # 删除某个repo
        data = chart_service.get_repo_from_id(repo_id)
        if data.get("data"):
            chart_service.delete_repo_id(data.get("data"))
            # 还要删除所有repo_id的charts应用
            # TODO
        return {"success": True, "message": "delete repo success"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"delete repo error: {str(e)}")


@router.get("/repo/sync/{repo_id}", summary="同步某个repo的charts包", description="同步某个repo的charts包")
async def sync_repo(repo_id: Union[str, int]):
    try:
        # 同步repo的charts
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"sync repo error: {str(e)}")


@router.get("/charts/list", summary="显示所有的charts信息", description="显示所有的charts信息")
async def get_repo_charts(repo: Union[str, int], cluster_id: str = Query(None, description="集群id"),
                     page: int = Query(1, description="页码"),
                     page_size: int = Query(10, description="页数量大小"),
                     sort_keys: str = Query(None, description="排序字段")):
    try:
        # 显示charts列表
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"get charts error: {str(e)}")


@router.get("/app/list", summary="显示所有的已安装应用信息", description="显示所有的已安装应用信息")
async def get_apps(cluster_id: str = Query(None, description="集群id"),
                     page: int = Query(1, description="页码"),
                     page_size: int = Query(10, description="页数量大小"),
                     sort_keys: str = Query(None, description="排序字段")):
    try:
        # 显示已安装应用列表
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"get apps error: {str(e)}")


@router.put("/app/update/{app_name}", summary="已安装的应用的编辑或升级", description="已安装的应用的编辑或升级")
async def put_app(app_name: str, update_data: CreateAppObject):
    try:
        # 编辑或更新已安装应用
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"update app error: {str(e)}")


@router.get("/charts/{chart_id}", summary="获取某个chart的详情", description="获取某个chart的详情")
async def get_chart(chart_id: Union[str, int]):
    try:
        # 获取某个chart的详情
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"get chart error: {str(e)}")


@router.delete("/app/{app_name}", summary="删除某个已安装的应用", description="删除某个已安装的应用")
async def get_apps(app_name: str, cluster_id: str):
    try:
        # 删除某个已安装的应用
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"delete app error: {str(e)}")


@router.post("/charts/install", summary="安装某个应用", description="安装某个应用")
async def get_apps(create_data: CreateAppObject):
    try:
        # 安装某个应用
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"create app error: {str(e)}")