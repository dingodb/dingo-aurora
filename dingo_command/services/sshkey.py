import time
import json
import os
import uuid
import subprocess
import requests
import shutil
from requests.auth import HTTPBasicAuth
from datetime import datetime
from math import ceil
from yaml import CLoader
import yaml
from harborapi import HarborAsyncClient
import asyncio
from urllib.parse import urlparse
from typing import List
from httpx import HTTPStatusError
from dingo_command.db.models.sshkey.sql import KeySQL
from dingo_command.services import CONF
from dingo_command.utils.helm import util
from dingo_command.utils.helm.util import ChartLOG as Log

WORK_DIR = CONF.DEFAULT.cluster_work_dir
auth_url = CONF.DEFAULT.auth_url
image_master = CONF.DEFAULT.k8s_master_image
harbor_url = CONF.DEFAULT.chart_harbor_url
harbor_user = CONF.DEFAULT.chart_harbor_user
harbor_passwd = CONF.DEFAULT.chart_harbor_passwd
index_yaml = "index.yaml"


class KeyService:

    def list_keys(self, query_params, page, page_size, sort_keys, sort_dirs,):
        try:
            # 按照条件从数据库中查询数据
            count, data = KeySQL.list_keys(query_params, page, page_size, sort_keys, sort_dirs)
            res = {}
            # 页数相关信息
            if page and page_size:
                res['currentPage'] = page
                res['pageSize'] = page_size
                res['totalPages'] = ceil(count / int(page_size))
            res['total'] = count
            res['data'] = data
            return res
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def delete_key(self, key_id):
        # 根据key的id删除具体的key
        # 把这个key从configmap中删除
        query_params = {}
        query_params['id'] = key_id
        data = self.list_keys(query_params, 1, -1, None, None)
        if data.get("total") > 0:
            # 执行删除的操作
            return {"data": data.get("data")[0]}
        else:
            raise ValueError("key not found")

    def create_key(self, create_key_object):
        # 创建key
        # 具体步骤：1、接收前端发来的请求
        # 2、校验参数是否合法
        # 3、调用数据库接口
        # 4、把这个key的内容添加到configmap中
        # 5、返回结果
        pass