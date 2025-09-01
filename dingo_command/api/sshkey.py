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

@router.post("/sshkey", summary="创建sshkey", description="创建sshkey")
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


@router.get("/sshkey/list", summary="helm的repo仓库列表", description="显示helm的repo仓库列表")
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


@router.delete("/sshkey/{sshkey_id}", summary="删除某个repo的仓库", description="删除某个repo的仓库")
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