from typing import Union
import asyncio
from datetime import datetime
import json
from fastapi import Query
from fastapi import APIRouter, HTTPException, BackgroundTasks
from dingo_command.api.model.chart import CreateRepoObject, CreateAppObject
from dingo_command.services.chart import ChartService, create_harbor_repo, create_tag_info
from dingo_command.db.models.chart.sql import RepoSQL, AppSQL, ChartSQL, TagSQL
from dingo_command.utils.helm.util import ChartLOG as Log
from dingo_command.utils.helm import util

router = APIRouter()
chart_service = ChartService()

async def init():
    """
    初始化函数，用于初始化一些全局变量
    :return:
    """
    await create_harbor_repo()
    create_tag_info()

asyncio.run(init())

@router.post("/repo", summary="helm的repo仓库（异步）", description="创建helm的repo仓库（异步）")
async def create_repo(repo: CreateRepoObject, background_tasks: BackgroundTasks):
    try:
        # 1、判断参数是否合法
        await chart_service.check_repo_args(repo)
        Log.info("add repo, repo info %s" % repo)
        # 2、异步处理创建repo仓库的逻辑
        background_tasks.add_task(chart_service.create_repo, repo, update=False, status="creating")
        return {"success": True, "message": "create repo started, please wait"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        Log.error(f"create repo error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"create repo error: {str(e)}")


@router.get("/repo/list", summary="helm的repo仓库列表", description="显示helm的repo仓库列表")
async def list_repos(background_tasks: BackgroundTasks, cluster_id: str = Query(None, description="集群id"),
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
        if id:
            query_params['id'] = id
        if status:
            query_params['status'] = status
        if cluster_id:
            query_params['cluster_id'] = cluster_id
        # 显示repo列表的逻辑
        data = chart_service.list_repos(query_params, page, page_size, sort_keys, sort_dirs, display=True)
        current_time = datetime.now()
        repo_list = []
        for repo in data.get("data"):
            if repo.id == 1 or repo.id == "1" or repo.status != "creating":
                continue
            if (current_time - repo.create_time).total_seconds() < util.repo_update_time_out:
                continue
            repo_data_info = CreateRepoObject(
                id=str(repo.id),
                name=repo.name,
                type=repo.type,
                url=repo.url,
                username=repo.username,
                password=repo.password,
                description=repo.description,
                cluster_id=repo.cluster_id,
                is_global=repo.is_global
            )
            repo_list.append(repo_data_info)
        if len(repo_list) > 0:
            background_tasks.add_task(chart_service.create_repo_list, repo_list, update=True, status="updating")
        data1 = chart_service.list_repos(query_params, page, page_size, sort_keys, sort_dirs)
        return data1
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"list repos error: {str(e)}")


@router.put("/repo/{repo_id}", summary="更新repo的仓库配置（异步）", description="更新repo的仓库配置（异步）")
async def update_repo(repo_id: Union[str, int], repo_data: CreateRepoObject, background_tasks: BackgroundTasks):
    try:
        # 更新repo仓库的配置
        # 先从数据库中看看有没有repo_id这个数据，如果没有直接返回404
        Log.info("update repo, repo id %s" % repo_id)
        query_params = {}
        query_params["id"] = repo_id
        data = chart_service.list_repos(query_params, 1, -1, None, None)
        if data.get("total") == 0:
            raise ValueError("repo not found")

        repo = data.get("data")[0]
        if repo.status == util.repo_status_create:
            raise ValueError("repo is creating, please wait")
        if repo.status == util.repo_status_update:
            raise ValueError("repo is updating, please wait")
        if repo.status == util.repo_status_sync:
            raise ValueError("repo is syncing, please wait")
        if repo.status == util.repo_status_delete:
            raise ValueError("repo is deleting, please wait")
        if repo.id == 1 or repo.id == "1":
            raise ValueError("can not update global repo")
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
        background_tasks.add_task(chart_service.create_repo, repo_data, update=True, status="updating")
        # 1、先判断repo的url是否改变了，如果改变了就需要把原来的repo的charts应用全部删除，然后再添加新的repo的charts应用
        # 2、如果相同就不需要更换charts应用，只需要修改repo的配置即可，repo_id是不需要修改的
        # 3、如果不相同就需要删除原来的repo的charts应用，然后再添加新的repo的charts应用
        return {"success": True, "message": "update repo started, please wait"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        Log.error(f"update repo failed, reason: {str(e)}")
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
            raise ValueError("can not delete global repo")
        if cluster_id:
            data = chart_service.get_repo_from_id(repo_id, cluster_id)
        else:
            data = chart_service.get_repo_from_id(repo_id)
        if data.get("data"):
            repo = data.get("data")
            if repo.status == util.repo_status_create:
                raise ValueError("repo is creating, please wait")
            if repo.status == util.repo_status_update:
                raise ValueError("repo is updating, please wait")
            if repo.status == util.repo_status_sync:
                raise ValueError("repo is syncing, please wait")
            if repo.status == util.repo_status_delete:
                raise ValueError("repo is deleting, please wait")
            repo.status = util.repo_status_delete
            RepoSQL.update_repo(repo)
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
async def sync_repo(repo_id: Union[str, int], background_tasks: BackgroundTasks):
    try:
        # 同步repo的charts
        data = chart_service.get_repo_from_id(repo_id, display=True)
        if not data.get("data"):
            raise ValueError("repo not found")
        repo_data = data.get("data")
        # 先删除原来的repo的charts应用
        data = chart_service.get_repo_from_name(repo_id)
        repo = data.get("data")[0]
        if repo.status == util.repo_status_create:
            raise ValueError("repo is creating, please wait")
        if repo.status == util.repo_status_update:
            raise ValueError("repo is updating, please wait")
        if repo.status == util.repo_status_sync:
            raise ValueError("repo is syncing, please wait")
        if data.get("data"):
            chart_service.delete_charts_repo_id(data.get("data"))
        # 再添加新的repo的charts应用
        repo_data_info = CreateRepoObject(
            id=repo_id,
            name=repo_data.name,
            type=repo_data.type,
            url=repo_data.url,
            username=repo_data.username,
            password=repo_data.password,
            description=repo_data.description,
            cluster_id=repo_data.cluster_id,
            is_global=repo_data.is_global
        )
        background_tasks.add_task(chart_service.create_repo, repo_data_info, update=True, status="syncing")
        return {"success": True, "message": "sync repo started, please wait"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"sync repo error: {str(e)}")

@router.get("/repo/stop/{repo_id}", summary="停用某个repo", description="停用某个repo")
async def stop_repo(repo_id: Union[str, int], cluster_id: str = Query(None, description="集群id")):
    try:
        # 同步repo的charts
        if (repo_id == 1 or repo_id == "1") and not cluster_id:
            raise ValueError("cluster_id must be provided when stop global repo")
        data = chart_service.get_repo_from_id(repo_id, display=True)
        if not data.get("data"):
            raise ValueError("repo not found")
        repo_data = data.get("data")
        if repo_data.status != util.repo_status_success:
            raise ValueError("repo is not ready for stop, only available repo can be stop")
        if repo_id == 1 or repo_id == "1":
            repo_data.status = util.repo_status_success
        else:
            repo_data.status = util.repo_status_stop
        chart_service.update_repo_status(repo_data, cluster_id=cluster_id, stop=True)
        data = chart_service.get_repo_from_name(repo_id)
        if data.get("data"):
            chart_list = data.get("data")
            if repo_id == 1 or repo_id == "1":
                for chart in chart_list:
                    chart.status = util.chart_status_success
            else:
                for chart in chart_list:
                    chart.status = util.chart_status_stop
            chart_service.update_charts_status(chart_list)
        return {"success": True, "message": "stop repo success"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"stop repo failed: {str(e)}")

@router.get("/repo/start/{repo_id}", summary="启用某个repo", description="启用某个repo")
async def start_repo(repo_id: Union[str, int], cluster_id: str = Query(None, description="集群id")):
    try:
        # 同步repo的charts
        if (repo_id == 1 or repo_id == "1") and not cluster_id:
            raise ValueError("cluster_id must be provided when start global repo")
        data = chart_service.get_repo_from_id(repo_id, display=True)
        if not data.get("data"):
            raise ValueError("repo not found")
        repo_data = data.get("data")
        if not (repo_id == 1 or repo_id == "1") and repo_data.status != util.repo_status_stop:
            raise ValueError("repo is not ready for start, only unavailable repo can be start")
        repo_data.status = util.repo_status_success
        chart_service.update_repo_status(repo_data, cluster_id=cluster_id)
        data = chart_service.get_repo_from_name(repo_id)
        if data.get("data"):
            chart_list = data.get("data")
            for chart in chart_list:
                chart.status = util.chart_status_success
            chart_service.update_charts_status(chart_list)
        return {"success": True, "message": "start repo success"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"start repo failed: {str(e)}")

@router.get("/charts/list", summary="显示所有的charts信息", description="显示所有的charts信息")
async def get_repo_charts(cluster_id: str = Query(None, description="集群id"),
                     repo_id: str = Query(None, description="集群id"),
                     repo_name: str = Query(None, description="集群id"),
                     tag_id: int = Query(None, description="tag的id"),
                     tag_name: str = Query(None, description="tag的name"),
                     status: str = Query(None, description="status状态"),
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
        if status:
            query_params['status'] = status
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

@router.get("/tag/list", summary="显示所有的tag信息", description="显示所有的tag信息")
async def get_tags(name: str = Query(None, description="名称"),
                     id: str = Query(None, description="id"),
                     chinese_name: str = Query(None, description="id"),
                     page: int = Query(1, description="页码"),
                     page_size: int = Query(10, description="页数量大小"),
                     sort_dirs:str = Query(None, description="排序方式"),
                     sort_keys: str = Query(None, description="排序字段")):
    try:
        # 显示某个tag信息
        # 声明查询条件的dict
        query_params = {}
        # 查询条件组装
        if name:
            query_params['name'] = name
        if id:
            query_params['id'] = id
        if chinese_name:
            query_params['chinese_name'] = chinese_name
        # 返回tags列表
        return chart_service.list_tags(query_params, page, page_size, sort_keys, sort_dirs)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"get tags error: {str(e)}")

@router.get("/tag/{tag_id}", summary="显示某个tag信息", description="显示某个tag信息")
async def get_tags(tag_id: Union[str, int]):
    try:
        query_params = {}
        query_params['id'] = tag_id
        data = chart_service.list_tags(query_params, 1, -1, None, None)
        if data.get("total") > 0:
            return {"data": data.get("data")[0]}
        else:
            return {"data": None}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"get tag detail error: {str(e)}")

@router.get("/app/list", summary="显示所有的已安装应用信息", description="显示所有的已安装应用信息")
async def get_apps(app_id: str = Query(None, description="集群id"),
                     app_name: str = Query(None, description="集群id"),
                     cluster_id: str = Query(None, description="集群id"),
                     chart_id: str = Query(None, description="集群id"),
                     repo_id: str = Query(None, description="集群id"),
                     repo_name: str = Query(None, description="集群id"),
                     namespace: int = Query(None, description="tag的id"),
                     tag_name: str = Query(None, description="tag的name"),
                     tag_id: str = Query(None, description="tag的name"),
                     status: str = Query(None, description="status状态"),
                     type: str = Query(None, description="类型"),
                     page: int = Query(1, description="页码"),
                     page_size: int = Query(10, description="页数量大小"),
                     sort_dirs:str = Query(None, description="排序方式"),
                     sort_keys: str = Query(None, description="排序字段")):
    try:
        # 显示已安装应用列表
        # list时得看下真实的状态是否已经被删除了，这个要怎么看得研究下
        # 得返回所有app对应chart的version和values信息，这个必须的（这个是不是可以让前端去取chart_id的信息来获取，version和values）
        query_params = {}
        # 查询条件组装
        if app_id:
            query_params['id'] = app_id
        if app_name:
            query_params['name'] = app_name
        if cluster_id:
            query_params['cluster_id'] = cluster_id
        if status:
            query_params['status'] = status
        if repo_name:
            query_params['repo_name'] = repo_name
        if tag_id:
            query_params['tag_id'] = tag_id
        if tag_name:
            query_params['tag_name'] = tag_name
        if type:
            query_params['type'] = type
        if chart_id:
            query_params['chart_id'] = chart_id
        if repo_id:
            query_params['repo_id'] = repo_id
        if namespace:
            query_params['namespace'] = namespace
        if type:
            query_params['type'] = type
        # 显示repo列表的逻辑
        return chart_service.list_apps(query_params, page, page_size, sort_keys, sort_dirs)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"get apps error: {str(e)}")

@router.get("/app/{app_id}", summary="显示某个已安装应用信息", description="显示某个已安装应用信息")
async def get_apps(app_id: Union[str, int]):
    try:
        # 显示选中的已安装应用，具体哪些信息要展示
        query_params = {}
        query_params["id"] = app_id
        data = chart_service.list_apps(query_params, 1, -1, None, None)
        if data.get("total") == 0:
            raise ValueError("app not found")

        app_data = data.get("data")[0]
        return chart_service.get_app_detail(app_data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"get apps error: {str(e)}")

@router.put("/app/update/{app_id}", summary="已安装的应用的编辑或升级（异步）", description="已安装的应用的编辑或升级（异步）")
async def put_app(app_id: Union[str, int], update_data: CreateAppObject, background_tasks: BackgroundTasks):
    try:
        # 编辑或更新已安装应用
        # 获取app的id，然后添加到update_data
        Log.info(f"update app, app_id %s" % app_id)
        query_params = {}
        query_params["id"] = app_id
        data = chart_service.list_apps(query_params, 1, -1, None, None)
        if data.get("total") == 0:
            raise ValueError("app not found")

        app_data = data.get("data")[0]
        if app_data.status == util.app_status_create:
            raise ValueError("app is creating, please wait")
        if app_data.status == util.app_status_update:
            raise ValueError("app is updating, please wait")
        if app_data.status == util.app_status_delete:
            raise ValueError("app is deleting, please wait")
        update_data.id = app_data.id
        update_data.name = app_data.name
        update_data.cluster_id = app_data.cluster_id
        update_data.chart_id = app_data.chart_id
        update_data.namespace = app_data.namespace
        background_tasks.add_task(chart_service.install_app, update_data, update=True)
        return {"success": True, "message": "updata app started, please wait"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        Log.error(f"update app failed, reason: {str(e)}")
        raise HTTPException(status_code=400, detail=f"update app error: {str(e)}")


@router.get("/charts/{chart_id}", summary="获取某个chart的详情", description="获取某个chart的详情")
async def get_chart(chart_id: Union[str, int]):
    try:
        # 获取某个chart的详情
        return chart_service.get_chart(chart_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"get chart error: {str(e)}")

@router.get("/charts/detail/{chart_id}", summary="获取某个版本的chart的详情", description="获取某个版本的chart的详情")
async def get_chart_version(chart_id: Union[str, int], version: str = Query(None, description="版本号")):
    try:
        # 获取某个chart的详情a
        return chart_service.get_chart_version(chart_id, version)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"get chart detail with version error: {str(e)}")

@router.delete("/app/{app_id}", summary="删除某个已安装的应用（异步）", description="删除某个已安装的应用（异步）")
async def get_apps(app_id: Union[str, int], background_tasks: BackgroundTasks):
    try:
        # 删除某个已安装的应用
        Log.info("delete app, app_id %s" % app_id)
        query_params = {}
        query_params["id"] = app_id
        data = chart_service.list_apps(query_params, 1, -1, None, None)
        if data.get("total") == 0:
            raise ValueError("app not found")

        app_data = data.get("data")[0]
        if app_data.status == util.app_status_create:
            raise ValueError("app is creating, please wait")
        if app_data.status == util.app_status_update:
            raise ValueError("app is updating, please wait")
        if app_data.status == util.app_status_delete:
            raise ValueError("app is deleting, please wait")
        background_tasks.add_task(chart_service.delete_app, app_data)
        return {"success": True, "message": "delete app started, please wait"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        Log.error(f"delete app failed, reason: {str(e)}")
        raise HTTPException(status_code=400, detail=f"delete app error: {str(e)}")


@router.post("/charts/install", summary="安装某个应用（异步）", description="安装某个应用（异步）")
async def get_apps(create_data: CreateAppObject, background_tasks: BackgroundTasks):
    try:
        Log.info(f"install app {create_data.name}, data info {create_data}")
        query_params = {}
        query_params["cluster_id"] = create_data.cluster_id
        data = chart_service.list_apps(query_params, 1, -1, None, None)
        if data.get("total") != 0:
            for app_data in data.get("data"):
                if app_data.name == create_data.name and app_data.namespace == create_data.namespace:
                    raise ValueError("app name already exists")

        background_tasks.add_task(chart_service.install_app, create_data, update=False)
        return {"success": True, "message": "install app started, please wait"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        Log.error(f"install app {create_data.name} failed, reason: {str(e)}")
        raise HTTPException(status_code=400, detail=f"install app error: {str(e)}")


@router.get("/helm/list", summary="安装某个应用（异步）", description="安装某个应用（异步）")
async def get_test(kube_config_path: str = Query(None, description="kube_config路径")):
    try:
        content = chart_service.get_helm_list(kube_config_path)
        content_list = json.loads(content)
        return {"data": content_list}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"helm list error: {str(e)}")