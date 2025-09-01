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
from openpyxl.styles import Border, Side
from yaml import CLoader
import yaml
from harborapi import HarborAsyncClient
import asyncio
from urllib.parse import urlparse
from typing import List
from httpx import HTTPStatusError
from dingo_command.api.model.chart import (CreateRepoObject, CreateAppObject, ChartObject, ChartVersionObject,
                                           ChartMetadataObject, ResponseChartObject, ResourcesObject, AppChartObject,
                                           ResponseAppObject)
from dingo_command.db.models.chart.models import RepoInfo as RepoDB
from dingo_command.db.models.chart.models import ChartInfo as ChartDB
from dingo_command.db.models.chart.models import AppInfo as AppDB
from dingo_command.db.models.chart.models import TagInfo as TagDB
from dingo_command.db.models.chart.sql import RepoSQL, AppSQL, ChartSQL, TagSQL
from dingo_command.services.cluster import ClusterService

from dingo_command.services.system import SystemService
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

    def list_keys(self, query_params, page, page_size, sort_keys, sort_dirs, display=False):
        try:
            # 按照条件从数据库中查询数据
            count, data = RepoSQL.list_repos(query_params, page, page_size, sort_keys, sort_dirs)
            repo_tmp_list = []
            if "cluster_id" in query_params and query_params["cluster_id"]:
                for repo in data:
                    if repo.cluster_id == "all":
                        repo.cluster_id = query_params["cluster_id"]
                        if repo.except_cluster:
                            tmp_list = json.loads(repo.except_cluster)
                            if query_params["cluster_id"] in tmp_list:
                                repo.status = "unavailable"
                    repo_tmp_list.append(repo)
            if repo_tmp_list:
                data = repo_tmp_list
            if count > 0 and not display:
                for repo in data:
                    if repo.id == 1 or repo.id == "1":
                        repo.username = "xxxxxxxxxxxxxx"
                        repo.password = "xxxxxxxxxxxxxx"
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

    def delete_key(self, repo_id, cluster_id=None, display=False):
        # 根据key的id删除具体的key
        # 把这个key从configmap中删除
        query_params = {}
        query_params['id'] = repo_id
        if cluster_id:
            query_params['cluster_id'] = cluster_id
        if display:
            data = self.list_repos(query_params, 1, -1, None, None, display=True)
        else:
            data = self.list_repos(query_params, 1, -1, None, None)
        if data.get("total") > 0:
            return {"data": data.get("data")[0]}
        else:
            raise ValueError("repo not found")

    def create_key(self, create_key_object):
        # 创建key
        # 具体步骤：1、接收前端发来的请求
        # 2、校验参数是否合法
        # 3、调用数据库接口
        # 4、把这个key的内容添加到configmap中
        # 5、返回结果
        pass