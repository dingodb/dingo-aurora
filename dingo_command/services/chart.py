import json
import logging
import os
import shutil
import uuid
from io import BytesIO
from urllib.parse import urlparse
from typing import Union
from datetime import datetime
from math import ceil
from openpyxl.styles import Border, Side

from oslo_log import log
from dingo_command.api.model.chart import CreateRepoObject, CreateAppObject
from dingo_command.db.models.chart.models import RepoInfo as RepoDB
from dingo_command.db.models.chart.sql import RepoSQL, AppSQL, ChartSQL, TagSQL

from dingo_command.services.system import SystemService
from dingo_command.services import CONF
from dingo_command.utils.helm import util
from dingo_command.services.custom_exception import Fail

LOG = log.getLogger(__name__)
WORK_DIR = CONF.DEFAULT.cluster_work_dir
auth_url = CONF.DEFAULT.auth_url
image_master = CONF.DEFAULT.k8s_master_image
harbor_url = CONF.DEFAULT.chart_harbor_url
harbor_user = CONF.DEFAULT.chart_harbor_user
harbor_passwd = CONF.DEFAULT.chart_harbor_passwd


# 定义边框样式
thin_border = Border(
    left=Side(border_style="thin", color="000000"),  # 左边框
    right=Side(border_style="thin", color="000000"),  # 右边框
    top=Side(border_style="thin", color="000000"),  # 上边框
    bottom=Side(border_style="thin", color="000000")  # 下边框
)

system_service = SystemService()

def create_harbor_repo(repo_name="my_harbor", url=harbor_url, username=harbor_user, password=harbor_passwd):
    """
    创建Harbor仓库
    :param repo_name: 仓库名称
    """
    pass

def is_valid_url(url):
    try:
        result = urlparse(url)
        # 必须包含协议和网络位置，且协议需为http/https
        return all([result.scheme in ['http', 'https'], result.netloc])
    except Exception:
        return False


class ChartService:

    def list_repos(self, query_params, page, page_size, sort_keys, sort_dirs):
        try:
            # 按照条件从数据库中查询数据
            count, data = RepoSQL.list_repos(query_params, page, page_size, sort_keys, sort_dirs)

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

    def get_repo_from_id(self,repo_id ):
        query_params = {}
        query_params['id'] = repo_id
        data = self.list_repos(query_params, 1, -1, None, None)
        if data.get("total") > 0:
            return {"data": data.get("data")[0]}
        else:
            return {"data": None}

    def check_repo_args(self, repo: CreateRepoObject):
        if repo.type not in (util.repo_type_http, util.repo_type_oci):
            raise ValueError("the type of repo only http or oci")
        if repo.type == util.repo_type_http:
            if not is_valid_url(repo.url):
                raise ValueError("the repo url is not in standard http or https format, please check")
        if repo.type == util.repo_type_oci:
            if not is_valid_url(repo.url):
                raise ValueError("the harbor url is not in standard http or https format with oci type, please check")
        if not repo.cluster_id:
            raise ValueError("the cluster id is empty, please check")
        if repo.is_global is None:
            raise ValueError("the is_global is empty, please check")
        query_params = {}
        query_params["name"] = repo.name
        query_params["cluster_id"] = repo.cluster_id
        res = self.list_repos(query_params, 1, -1, None, None)
        if res.get("total") > 0:
            for r in res.get("data"):
                if r.name == repo.name and r.cluster_id == repo.cluster_id:
                    # 如果查询结果不为空，说明仓库名称已存在+
                    raise Fail(error_code=405, error_message="Repo name already exists")

    def convert_repo_db(self, repo: CreateRepoObject):
        cluster_info_db = RepoDB()
        cluster_info_db.name = repo.name
        cluster_info_db.is_global = repo.is_global
        cluster_info_db.type = repo.type
        cluster_info_db.description = repo.description
        cluster_info_db.url = repo.url
        cluster_info_db.username = repo.username
        cluster_info_db.password = repo.password
        cluster_info_db.cluster_id = repo.cluster_id
        cluster_info_db.status = "creating"
        cluster_info_db.create_time = datetime.now()
        return cluster_info_db

    def delete_repo_id(self, repo: RepoDB):
        try:
            # 删除repo数据库表中的数据
            RepoSQL.delete_repo(repo)
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def create_repo(self, repo: CreateRepoObject):
        cluster_info_db = self.convert_repo_db(repo)
        RepoSQL.create_repo(cluster_info_db)
        print(cluster_info_db.id)
        if repo.type == util.repo_type_http:
            if repo.url.startswith("http"):
                # 处理http的repo
                pass
            else:
                # 处理https的repo
                pass
        else:
            if repo.url.startswith("https"):
                # 处理带密码的harbor的repo
                if repo.username and repo.password:
                    print(100, repo.username, repo.password)
                else:
                    pass
            else:
                # 处理带密码的harbor的repo
                if repo.username and repo.password:
                    print(200, repo.username, repo.password)
                else:
                    pass
        # 需不需要执行命令add repo并等待返回结果，需要考虑下（不需要执行这个命令）
        # oci的仓库是不能helm repo add添加命令的
