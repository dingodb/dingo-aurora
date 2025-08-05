from typing import Union
import asyncio
from datetime import datetime
from fastapi import Query, Header, Depends
from fastapi import APIRouter, HTTPException, BackgroundTasks
from dingo_command.api.model.cluster import ScaleNodeObject, NodeRemoveObject
from dingo_command.api.model.chart import CreateRepoObject, CreateAppObject
from dingo_command.services.cluster import ClusterService, TaskService
from dingo_command.services.chart import ChartService, create_harbor_repo, create_tag_info, run_sync_repo
from dingo_command.services.custom_exception import Fail
from dingo_command.common.nova_client import NovaClient
from dingo_command.utils.helm.util import ChartLOG as Log

router = APIRouter()
chart_service = ChartService()

async def init():
    """
    初始化函数，用于初始化一些全局变量
    :return:
    """
    await create_harbor_repo()
    create_tag_info()
    # 是否再起一个线程来执行同步repo的任务，感觉放到定时任务里更好点，但是这样可以保证每次启动的时候都能同步repo
    # 要仔细考虑考虑
    run_sync_repo()

asyncio.run(init())

@router.post("/repo", summary="helm的repo仓库", description="创建helm的repo仓库")
async def create_repo(repo: CreateRepoObject, background_tasks: BackgroundTasks):
    try:
        # 1、判断参数是否合法
        await chart_service.check_repo_args(repo)
        Log.info("add repo, repo info %s" % repo)
        # 2、异步处理创建repo仓库的逻辑
        background_tasks.add_task(chart_service.create_repo, repo, update=False)
        return {"success": True, "message": "create repo started, please wait"}
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        Log.error(f"create repo error: {str(e)}")
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
        return chart_service.list_repos(query_params, page, page_size, sort_keys, sort_dirs, display=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"list repos error: {str(e)}")


@router.put("/repo/{repo_id}", summary="更新repo的仓库配置", description="更新repo的仓库配置")
async def update_repo(repo_id: Union[str, int], repo_data: CreateRepoObject, background_tasks: BackgroundTasks):
    try:
        # 更新repo仓库的配置
        # 先从数据库中看看有没有repo_id这个数据，如果没有直接返回404
        Log.info("update repo, repo id %s" % repo_id)
        query_params = {}
        query_params["id"] = repo_id
        data = chart_service.list_repos(query_params, 1, -1, None, None)
        if data.get("total") == 0:
            raise HTTPException(status_code=404, detail="repo not found")

        repo = data.get("data")[0]
        if repo.url == repo_data.url and repo.name == repo_data.name and repo.type == repo_data.type  and \
                repo.username == repo_data.username and repo.password == repo_data.password and \
                repo.description == repo_data.description:
            return {"success": False, "message": "repo value is not change"}
        elif repo.url == repo_data.url and repo.name == repo_data.name and repo.type == repo_data.type and \
                repo.username == repo_data.username and repo.password == repo_data.password and \
                repo.description != repo_data.description:
            # 更新下描述
            repo.description = repo_data.description
            repo.update_time = datetime.now()
            chart_service.change_repo_data(repo)
            return {"success": True, "message": "update repo success"}
        # 如果url改变了，那么需要删除原来的repo的charts应用，然后再添加新的repo的charts应用
        # 先删除原来的repo的charts应用
        chart_data = chart_service.get_repo_from_name(repo.id)
        if chart_data.get("data"):
            chart_service.delete_charts_repo_id(chart_data.get("data"))
        # 再添加新的repo的charts应用
        repo_data.id = repo.id
        repo_data.cluster_id = repo.cluster_id
        background_tasks.add_task(chart_service.create_repo, repo_data, update=True)
        # 1、先判断repo的url是否改变了，如果改变了就需要把原来的repo的charts应用全部删除，然后再添加新的repo的charts应用
        # 2、如果相同就不需要更换charts应用，只需要修改repo的配置即可，repo_id是不需要修改的
        # 3、如果不相同就需要删除原来的repo的charts应用，然后再添加新的repo的charts应用
        return {"success": True, "message": "update repo started, please wait"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"update repo error: {str(e)}")

@router.get("/repo/{repo_id}", summary="获取某个repo的仓库信息", description="获取某个repo的仓库信息")
async def get_repo(repo_id: Union[str, int], cluster_id: str = Query(None, description="集群id")):
    try:
        # 获取指定repo仓库的配置
        if cluster_id:
            return chart_service.get_repo_from_id(repo_id, cluster_id)
        else:
            return chart_service.get_repo_from_id(repo_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"get repo error: {str(e)}")

@router.delete("/repo/{repo_id}", summary="删除某个repo的仓库", description="删除某个repo的仓库")
async def delete_repo(repo_id: Union[str, int], cluster_id: str = Query(None, description="集群id")):
    try:
        # 删除某个repo
        if repo_id == 1 or repo_id == "1":
            raise HTTPException(status_code=400, detail="can not delete global repo")
        if cluster_id:
            data = chart_service.get_repo_from_id(repo_id, cluster_id)
        else:
            data = chart_service.get_repo_from_id(repo_id)
        if data.get("data"):
            chart_service.delete_repo_id(data.get("data"))
        return {"success": True, "message": "delete repo success"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"delete repo error: {str(e)}")

# @router.delete("/chart/{repo_id}", summary="删除某个repo的charts", description="删除某个repo的charts")
# async def delete_repo(repo_id: Union[str, int]):
#     try:
#         # 删除某个repo的所有charts
#         data = chart_service.get_repo_from_name(repo_id)
#         if data.get("data"):
#             chart_service.delete_charts_repo_id(data.get("data"))
#         return {"success": True, "message": "delete charts success"}
#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         raise HTTPException(status_code=400, detail=f"delete repo error: {str(e)}")

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
async def get_repo_charts(cluster_id: str = Query(None, description="集群id"),
                     repo_id: str = Query(None, description="集群id"),
                     repo_name: str = Query(None, description="集群id"),
                     tag_id: int = Query(None, description="tag的id"),
                     tag_name: str = Query(None, description="tag的name"),
                     type: str = Query(None, description="类型"),
                     page: int = Query(1, description="页码"),
                     page_size: int = Query(10, description="页数量大小"),
                     sort_dirs:str = Query(None, description="排序方式"),
                     sort_keys: str = Query(None, description="排序字段")):
    try:
        # 显示charts列表
        # 声明查询条件的dict
        query_params = {}
        # 查询条件组装
        if cluster_id:
            query_params['cluster_id'] = cluster_id
        if repo_id:
            query_params['repo_id'] = repo_id
        if repo_name:
            query_params['repo_name'] = repo_name
        if tag_id:
            query_params['tag_id'] = tag_id
        if tag_name:
            query_params['tag_name'] = tag_name
        if type:
            query_params['type'] = type
        # 显示repo列表的逻辑
        return chart_service.list_charts(query_params, page, page_size, sort_keys, sort_dirs)
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