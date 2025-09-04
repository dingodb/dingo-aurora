from typing import Union
import asyncio
from datetime import datetime
import json
from fastapi import Query
from fastapi import APIRouter, HTTPException, BackgroundTasks
from dingo_command.api.model.sshkey import CreateKeyObject
from dingo_command.services.sshkey import KeyService
from dingo_command.db.models.sshkey.sql import KeySQL
from dingo_command.utils.helm.util import SshLOG as Log


router = APIRouter()
key_service = KeyService()


@router.post("/sshkey", summary="创建sshkey", description="创建sshkey")
async def create_key(key: CreateKeyObject):
    try:
        Log.info("add key, key info %s" % key)
        return key_service.create_key(key)
    except Exception as e:
        import traceback
        traceback.print_exc()
        Log.error(f"create key error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"create key error: {str(e)}")


@router.get("/sshkey/list", summary="helm的repo仓库列表", description="显示helm的repo仓库列表")
async def list_keys(status: str = Query(None, description="status状态"),
                     name: str = Query(None, description="名称"),
                     id: str = Query(None, description="id"),
                     account_id: str = Query(None, description="account_id"),
                     user_id: str = Query(None, description="user_id"),
                     user_name: str = Query(None, description="user_name"),
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
        if id:
            query_params['id'] = id
        if status:
            query_params['status'] = status
        if account_id:
            query_params['account_id'] = account_id
        if user_id:
            query_params['user_id'] = user_id
        if user_name:
            query_params['user_name'] = user_name
        # 显示repo列表的逻辑
        data = key_service.list_keys(query_params, page, page_size, sort_keys, sort_dirs)
        return data
    except Exception as e:
        import traceback
        traceback.print_exc()
        Log.error(f"list keys error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"list keys error: {str(e)}")


@router.delete("/sshkey/{sshkey_id}", summary="删除某个repo的仓库", description="删除某个repo的仓库")
async def delete_key(sshkey_id: str):
    try:
        # 删除某个key以及它的数据信息
        Log.info("delete key, sshkey_id info %s" % sshkey_id)
        return key_service.delete_key(sshkey_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        Log.error(f"delete key error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"delete key error: {str(e)}")


@router.get("/sshkey/{sshkey_id}", summary="获取某个repo的仓库", description="删除某个repo的仓库")
async def get_key(sshkey_id: str):
    try:
        # 删除某个key以及它的数据信息
        Log.info("get key, sshkey_id info %s" % sshkey_id)
        # 声明查询条件的dict
        query_params = {}
        # 查询条件组装
        if sshkey_id:
            query_params['id'] = sshkey_id
        # 显示repo列表的逻辑
        data = key_service.list_keys(query_params, 1, -1, None, None)
        if not data.get("data"):
            raise HTTPException(status_code=404, detail=f"get key error: key not exist")
        return data.get("data")[0]
    except Exception as e:
        import traceback
        traceback.print_exc()
        Log.error(f"get key error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"get key error: {str(e)}")