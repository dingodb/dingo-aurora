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

async def create_harbor_repo(repo_name=util.repo_global_name, url=harbor_url, username=harbor_user,
                             password=harbor_passwd):
    """
    创建Harbor仓库
    :param repo_name: 仓库名称
    """
    # 创建全局harbor的仓库，如果已经存在就不创建，如果不存在才会创建
    try:
        query_params = {}
        query_params['name'] = repo_name
        query_params['cluster_id'] = util.repo_global_cluster_id
        data = ChartService().list_repos(query_params, 1, -1, None, None)
        if data.get("total") > 0:
            # 是否要添加当repo的url修改了，重新创建harbor的仓库的charts包
            if (data.get("data")[0].url != url and data.get("data")[0].status == util.repo_status_success or
                    data.get("data")[0].status == util.repo_status_failed):
                repo_info_db = data.get("data")[0]
                repo_info_db.url = url
                repo_info_db.username = username
                repo_info_db.password = password
                repo_info_db.create_time = datetime.now()
                repo_info_db.status = "creating"
                RepoSQL.update_repo(repo_info_db)
                service = ChartService()
                # 删除原来的repo的所有chart
                data = service.get_repo_from_name(repo_info_db.id)
                if data.get("data"):
                    service.delete_charts_repo_id(data.get("data"))
                # 添加新的repo的所有chart
                await service.handle_oci_repo(repo_info_db)
            return
        repo_info_db = RepoDB()
        repo_info_db.id = 1
        repo_info_db.name = repo_name
        repo_info_db.url = url
        repo_info_db.username = username
        repo_info_db.password = password
        repo_info_db.type = "oci"
        repo_info_db.is_global = True
        repo_info_db.cluster_id = util.repo_global_cluster_id
        repo_info_db.create_time = datetime.now()
        repo_info_db.description = "global repo with harbor"
        repo_info_db.status = "creating"
        RepoSQL.create_repo(repo_info_db)
        await ChartService().handle_oci_repo(repo_info_db)
    except asyncio.TimeoutError as e:
        Log.error("Harbor API请求超时，请检查网络或Harbor服务状态")
        raise e
    except Exception as e:
        import traceback
        traceback.print_exc()
        Log.error("add global repo with harbor failed, reason %s" % str(e))
        raise e

def create_tag_info():
    # 创建指定的tag信息，如果已经存在就不创建，如果不存在才会创建
    query_params = {}
    count, data = TagSQL.list_tags(query_params, page=1, page_size=-1)
    for tag_id, tag_dict_info in util.tag_data.items():
        back = False
        for tag in data:
            if (tag.id == tag_id and tag.name == tag_dict_info.get("name") and
                    tag.chinese_name == tag_dict_info.get("chinese_name")):
                back = True
                break
            elif (tag.id == tag_id and tag.name!= tag_dict_info.get("name") or tag.id == tag_id and
                  tag.chinese_name!= tag_dict_info.get("chinese_name")):
                back = True
                tag_info = TagDB()
                tag_info.id = tag_id
                tag_info.name = tag_dict_info.get("name")
                tag_info.chinese_name = tag_dict_info.get("chinese_name")
                TagSQL.update_tag(tag_info)
                break
        if back:
            continue
        tag_info = TagDB()
        tag_info.id = tag_id
        tag_info.name = tag_dict_info.get("name")
        tag_info.chinese_name = tag_dict_info.get("chinese_name")
        TagSQL.create_tag(tag_info)

def run_sync_repo():
    # 同步repo的信息，如果repo的状态是creating，就会去同步repo的信息，如果repo的状态是可用的，就不会去同步repo的信息
    # 应该单起一个线程去完成这个任务
    query_params = {}
    pass

def is_valid_url(url):
    try:
        result = urlparse(url)
        # 必须包含协议和网络位置，且协议需为http/https
        return all([result.scheme in ['http', 'https'], result.netloc])
    except Exception:
        return False


class ChartService:

    def list_repos(self, query_params, page, page_size, sort_keys, sort_dirs, display=False):
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

    def list_charts(self, query_params, page, page_size, sort_keys, sort_dirs):
        try:
            # 按照条件从数据库中查询数据
            query_tmp_params = {}
            query_tmp_params['cluster_id'] = "all"
            count, data = RepoSQL.list_repos(query_tmp_params, 1, -1, None, None)
            tmp_list = []
            if count > 0:
                repo = data[0]
                if repo.except_cluster:
                    tmp_list = json.loads(repo.except_cluster)
            count, data = ChartSQL.list_charts(query_params, page, page_size, sort_keys, sort_dirs)
            chart_tmp_list = []
            if "cluster_id" in query_params and query_params["cluster_id"]:
                for chart in data:
                    if chart.cluster_id == "all":
                        chart.cluster_id = query_params["cluster_id"]
                        if query_params["cluster_id"] in tmp_list:
                            chart.status = "unavailable"
                    chart_tmp_list.append(chart)
            if chart_tmp_list:
                data = chart_tmp_list
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

    def list_tags(self, query_params, page, page_size, sort_keys, sort_dirs):
        try:
            # 按照条件从数据库中查询数据
            count, data = TagSQL.list_tags(query_params, page, page_size, sort_keys, sort_dirs)

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

    def list_apps(self, query_params, page, page_size, sort_keys, sort_dirs):
        try:
            # 按照条件从数据库中查询数据
            count, data = AppSQL.list_apps(query_params, page, page_size, sort_keys, sort_dirs)

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

    def get_repo_from_id(self, repo_id, cluster_id=None, display=False):
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

    def change_repo_data(self, repo_info_db):
        RepoSQL.update_repo(repo_info_db)

    def get_repo_from_name(self, repo_id):
        query_params = {}
        query_params['repo_id'] = repo_id
        data = self.list_charts(query_params, 1, -1, None, None)
        if data.get("total") > 0:
            return {"data": data.get("data")}
        else:
            return {"data": None}

    async def get_harbor_project(self, harbor_url, harbor_user, harbor_passwd):
        parsed_url = urlparse(harbor_url)
        harbor_api_url = f"{parsed_url.scheme}://{parsed_url.netloc}/api/v2.0"
        project_name = parsed_url.path.strip("/").split("/")[-1]

        client = HarborAsyncClient(
            url=harbor_api_url,
            username=harbor_user,
            secret=harbor_passwd
        )

        try:
            # 设置 3 秒超时
            project = await asyncio.wait_for(
                client.project_exists(project_name=project_name),
                timeout=util.time_out
            )
            if not project:
                raise ValueError(f"{project_name} project not found")

        except asyncio.TimeoutError:
            raise TimeoutError(f"访问 Harbor API 超时（3秒）: {harbor_api_url}")
        except Exception as e:
            raise RuntimeError(f"请求失败: {str(e)}")

    async def check_repo_args(self, repo: CreateRepoObject):
        if repo.type not in (util.repo_type_http, util.repo_type_oci):
            raise ValueError("the type of repo only http or oci")
        if repo.type == util.repo_type_http:
            if not is_valid_url(repo.url):
                raise ValueError("the repo url is not in standard http or https format, please check")
            if not self.handle_http_repo(repo.url, repo.username, repo.password):
                raise ValueError(f"add repo failed, {repo.url} is not a valid http or https repo, please check")
        if repo.type == util.repo_type_oci:
            if not is_valid_url(repo.url):
                raise ValueError("the harbor url is not in standard http or https format with oci type, please check")
            await self.get_harbor_project(repo.url, repo.username, repo.password)
        if not repo.cluster_id:
            raise ValueError("the cluster id is empty, please check")
        # if repo.is_global is None:
        #     raise ValueError("the is_global is empty, please check")
        query_params = {}
        # query_params["name"] = repo.name
        query_params["cluster_id"] = repo.cluster_id
        res = self.list_repos(query_params, 1, -1, None, None)
        if res.get("total") > 0:
            for r in res.get("data"):
                if r.name == repo.name and r.cluster_id == repo.cluster_id:
                    # 如果查询结果不为空，说明仓库名称已存在+
                    raise ValueError("Repo name already exists")
                # if r.url == repo.url and r.cluster_id == repo.cluster_id:
                #     # 如果查询结果不为空，说明仓库地址已存在
                #     raise ValueError(f"The same repo url already exists, repo name is {r.name}")

    def convert_repo_db(self, repo: CreateRepoObject, status="creating"):
        repo_info_db = RepoDB()
        if repo.id:
            repo_info_db.id = repo.id
        repo_info_db.name = repo.name
        repo_info_db.is_global = repo.is_global or False
        repo_info_db.type = repo.type
        repo_info_db.description = repo.description
        repo_info_db.url = repo.url
        repo_info_db.username = repo.username
        repo_info_db.password = repo.password
        repo_info_db.cluster_id = repo.cluster_id
        repo_info_db.status = status
        return repo_info_db

    def convert_db_harbor(self, chart_name, artifact_info, repo_info_db, prefix_name):
        chart_info_db = ChartDB()
        chart_info_db.name = chart_name
        chart_info_db.prefix_name = prefix_name
        chart_info_db.description = artifact_info.get("description", "")
        chart_info_db.version = json.dumps(artifact_info.get("version"))
        chart_info_db.deprecated = artifact_info.get("deprecated")
        chart_info_db.icon = artifact_info.get("icon")

        chart_info_db.repo_id = repo_info_db.id
        chart_info_db.cluster_id = repo_info_db.cluster_id
        chart_info_db.type = util.repo_type_oci
        chart_info_db.latest_version = artifact_info.get("latest_version")
        chart_info_db.repo_name = repo_info_db.name
        chart_info_db.create_time = artifact_info.get("create_time")
        chart_info_db.status = util.chart_status_success
        if artifact_info.get("label"):
            chart_info_db.tag_id = util.tag_id_data.get(artifact_info.get("label"), 13)
            chart_info_db.tag_name = artifact_info.get("label")
        if not chart_info_db.tag_name:
            self.get_chart_db_info(chart_name, artifact_info, chart_info_db)
        return chart_info_db

    def get_chart_db_info(self, chart_name, version, chart_info_db):
        if "infrastructure" in chart_name.lower():
            chart_info_db.tag_name = "Infrastructure"
            chart_info_db.tag_id = 1
        elif "monitor" in chart_name.lower() or "grafana" in chart_name.lower():
            chart_info_db.tag_name = "Monitor"
            chart_info_db.tag_id = 2
        elif "fluent" in chart_name.lower() or "log" in chart_name.lower():
            chart_info_db.tag_name = "Log"
            chart_info_db.tag_id = 3
        elif "etcd" in chart_name.lower() or "minio" in chart_name.lower():
            chart_info_db.tag_name = "Storage"
            chart_info_db.tag_id = 4
        elif "rabbitmq" in chart_name.lower() or "kafka" in chart_name.lower() or "zookeeper" in chart_name.lower() or \
                "memcached" in chart_name.lower() or "redis" in chart_name.lower() or "aerospike" in chart_name.lower():
            chart_info_db.tag_name = "Middleware"
            chart_info_db.tag_id = 5
        elif "jenkins" in chart_name.lower() or "gitlab" in chart_name.lower() or "concourse" in chart_name.lower() or \
                "artifactory" in chart_name.lower() or "sonarqube" in chart_name.lower():
            chart_info_db.tag_name = "Development Tools"
            chart_info_db.tag_id = 6
        elif "wordpress" in chart_name.lower() or "drupal" in chart_name.lower() or "ghost" in chart_name.lower() or \
                "redmine" in chart_name.lower() or "odoo" in chart_name.lower():
            chart_info_db.tag_name = "Web Application"
            chart_info_db.tag_id = 7
        elif "mysql" in chart_name.lower() or "postgresql" in chart_name.lower() or "mongodb" in chart_name.lower():
            chart_info_db.tag_name = "Database"
            chart_info_db.tag_id = 8
        elif "vault" in chart_name.lower() or "cert-manager" in chart_name.lower() or \
                "anchore-engine" in chart_name.lower() or "kube-lego" in chart_name.lower() or \
                "security" in chart_name.lower():
            chart_info_db.tag_name = "Security Tools"
            chart_info_db.tag_id = 9
        elif "hadoop" in chart_name.lower() or "spark" in chart_name.lower() or "zeppelin" in chart_name.lower():
            chart_info_db.tag_name = "Big Data"
            chart_info_db.tag_id = 10
        elif "AI" in chart_name or "dask-distributed" in chart_name.lower() or "gpu" in chart_name.lower() or \
                "tensorflow" in chart_name.lower() or "pytorch" in chart_name.lower() or \
                "openai" in chart_name.lower() or "llm" in chart_name.lower() or "chatgpt" in chart_name.lower() or \
                "chatbot" in chart_name.lower() or "cuda" in chart_name.lower():
            chart_info_db.tag_name = "AI Tools"
            chart_info_db.tag_id = 11
        elif "ingress" in chart_name.lower() or "load" in chart_name.lower() and "balancer" in chart_name.lower() or \
                "network" in chart_name.lower() or "istio" in chart_name.lower() or \
                "service-mesh" in chart_name.lower() or "envoy" in chart_name.lower():
            chart_info_db.tag_name = "Network Service"
            chart_info_db.tag_id = 12

        if not chart_info_db.tag_name and version.get("keywords"):
            for key in version.get("keywords"):
                if "big" in key.lower() and "data" in key.lower():
                    chart_info_db.tag_name = "Big Data"
                    chart_info_db.tag_id = 10
                    break
                elif "infrastructure" in key.lower():
                    chart_info_db.tag_name = "Infrastructure"
                    chart_info_db.tag_id = 1
                    break
                elif "monitor" in key.lower() or "prometheus" in key.lower() or "grafana" in key.lower() :
                    chart_info_db.tag_name = "Monitor"
                    chart_info_db.tag_id = 2
                    break
                elif "fluent" in key.lower() or "log" in key.lower():
                    chart_info_db.tag_name = "Log"
                    chart_info_db.tag_id = 3
                    break
                elif "etcd" in key.lower() or "minio" in key.lower():
                    chart_info_db.tag_name = "Storage"
                    chart_info_db.tag_id = 4
                    break
                elif "rabbitmq" in key.lower() or "kafka" in key.lower() or "zookeeper" in key.lower() or \
                        "memcached" in key.lower() or "redis" in key.lower() or "aerospike" in key.lower():
                    chart_info_db.tag_name = "Middleware"
                    chart_info_db.tag_id = 5
                    break
                elif "jenkins" in key.lower() or "gitlab" in key.lower() or "concourse" in key.lower() or \
                        "artifactory" in key.lower() or "sonarqube" in key.lower():
                    chart_info_db.tag_name = "Development Tools"
                    chart_info_db.tag_id = 6
                    break
                elif "wordpress" in key.lower() or "drupal" in key.lower() or "ghost" in key.lower() or \
                        "redmine" in key.lower() or "odoo" in key.lower():
                    chart_info_db.tag_name = "Web Application"
                    chart_info_db.tag_id = 7
                    break
                elif "mysql" in key.lower() or "postgresql" in key.lower() or "mongodb" in key.lower():
                    chart_info_db.tag_name = "Database"
                    chart_info_db.tag_id = 8
                    break
                elif "vault" in key.lower() or "cert-manager" in key.lower() or \
                        "anchore-engine" in key.lower() or "kube-lego" in key.lower() or \
                        "security" in key.lower():
                    chart_info_db.tag_name = "Security Tools"
                    chart_info_db.tag_id = 9
                    break
                elif "AI" in key or "dask-distributed" in key.lower() or "gpu" in key.lower() or "tensorflow" in \
                      key.lower() or "pytorch" in key.lower() or "openai" in key.lower() or "llm" in key.lower() \
                      or "chatgpt" in key.lower() or "chatbot" in key.lower() or "cuda" in key.lower():
                    chart_info_db.tag_name = "AI Tools"
                    chart_info_db.tag_id = 11
                    break
                elif "ingress" in key.lower() or "load" in key.lower() and "balancer" in key.lower() or \
                        "network" in key.lower() or "istio" in key.lower() or \
                        "service-mesh" in key.lower() or "envoy" in key.lower():
                    chart_info_db.tag_name = "Network Service"
                    chart_info_db.tag_id = 12
                    break

        if not chart_info_db.tag_name:
            chart_info_db.tag_name = "Others"
            chart_info_db.tag_id = 13

    def convert_chart_db(self, chart_name, version, repo: RepoDB):
        chart_info_db = ChartDB()
        chart_info_db.name = chart_name
        chart_info_db.description = version.get("description")
        chart_info_db.repo_id = repo.id
        chart_info_db.cluster_id = repo.cluster_id
        chart_info_db.type = util.repo_type_http
        chart_info_db.repo_name = repo.name
        chart_info_db.version = json.dumps(version.get("version"))
        chart_info_db.latest_version = version.get("latest_version")
        chart_info_db.deprecated = version.get("deprecated")
        chart_info_db.icon = version.get("icon")
        chart_info_db.create_time = version.get("create_time")
        chart_info_db.status = util.chart_status_success
        self.get_chart_db_info(chart_name, version, chart_info_db)
        return chart_info_db

    def delete_repo_id(self, repo: RepoDB):
        try:
            # 删除repo数据库表中的数据
            RepoSQL.delete_repo(repo)
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def delete_charts_repo_id(self, chart_list):
        try:
            ChartSQL.delete_chart_list(chart_list)
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def update_charts_status(self, chart_list):
        try:
            ChartSQL.update_chart_list(chart_list)
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def update_repo_status(self, repo, cluster_id=None, stop=False):
        try:
            if (repo.id == 1 or repo.id == "1") and cluster_id:
                if repo.except_cluster:
                    list_a = json.loads(repo.except_cluster)
                    if cluster_id in list_a:
                        if not stop:
                            list_a.remove(cluster_id)
                    else:
                        list_a.append(cluster_id)
                else:
                    list_a = [cluster_id]
                repo.except_cluster = json.dumps(list_a)

            RepoSQL.update_repo(repo)
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def handle_http_repo(self, url, username=None, password=None):
        try:
            # 构造 index.yaml 的完整 URL
            index_url = url + "/index.yaml"
            if not username or not password:
                response = requests.get(index_url, timeout=util.time_out)
            else:
                response = requests.get(index_url, auth=HTTPBasicAuth(username, password), timeout=util.time_out)
            if not response.ok:
                return False
            return True
        except Exception as e:
            raise ValueError(f"get url /index.yaml error with {str(e)}")

    def handle_http_repo_content(self, url, username=None, password=None):
        try:
            # 构造 index.yaml 的完整 URL
            index_url = url + "/index.yaml"
            if not username or not password:
                response = requests.get(index_url, timeout=util.time_out)
            else:
                response = requests.get(index_url, auth=HTTPBasicAuth(username, password), timeout=util.time_out)
            if response.ok:
                return response.text
            raise ValueError(f"Unable to access the content in index.yaml, index.yaml is empty, please check")
        except Exception as e:
            raise ValueError(f"Unable to access the content in index.yaml, reason {str(e)}")

    async def handle_oci_repo(self, repo_info_db: RepoDB):
        try:
            parsed_url = urlparse(repo_info_db.url)
            harbor_api_url = f"{parsed_url.scheme}://{parsed_url.netloc}/api/v2.0"
            harbor_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            project_name = parsed_url.path.strip("/").split("/")[-1]
            client = HarborAsyncClient(
                url=harbor_api_url,
                username=repo_info_db.username,
                secret=repo_info_db.password
            )

            try_times = 0
            e_object = None
            while try_times < util.try_times:
                try:
                    repositories = await asyncio.wait_for(
                        client.get_repositories(project_name=project_name), timeout=util.repo_time_out
                    )
                    artifact_tasks = []
                    for repository in repositories:
                        # 为每个项目创建异步任务
                        task = asyncio.create_task(
                            asyncio.wait_for(
                                client.get_artifacts(project_name=project_name,
                                                     repository_name=repository.name.split(f"{project_name}/")[1],
                                                     with_label=True), timeout=util.repo_time_out)
                        )
                        artifact_tasks.append(task)

                    chart_list = []
                    await asyncio.gather(*artifact_tasks, return_exceptions=True)
                    for artifact in artifact_tasks:
                        if artifact.result()[0].type != "CHART":
                            continue
                        dict_version = {}
                        versions = artifact.result()
                        # chartname = versions[0].repository_name.split(f"{project_name}/")[-1]
                        parts = versions[0].repository_name.split('/')
                        chartname = parts[-1]  # 末尾字段
                        prefix_name = '/'.join(parts[parts.index(project_name) + 1: -1])
                        dict_info = versions[0].extra_attrs.model_dump()
                        dict_version["description"] = dict_info.get("description")
                        dict_version["icon"] = dict_info.get("icon")
                        if isinstance(versions[0].push_time, datetime):
                            dict_version["create_time"] = versions[0].push_time.isoformat()
                        else:
                            dict_version["create_time"] = versions[0].push_time
                        dict_version["latest_version"] = dict_info.get("version")
                        dict_version["deprecated"] = dict_info.get("deprecated") or False
                        if versions[0].labels:
                            dict_version["label"] = versions[0].labels[0].name
                        if dict_info.get("keywords"):
                            dict_version["keywords"] = dict_info.get("keywords")
                        dict_version["version"] = dict()
                        for artifact_info in artifact.result()[:util.chart_nubmer]:
                            if artifact_info.type != "CHART":
                                continue
                            dict_info = {}
                            dict_tmp_info = artifact_info.addition_links.model_dump()
                            dict_chart_info = artifact_info.extra_attrs.model_dump()
                            dict_info["create_time"] = dict_version["create_time"]
                            dict_info["readme_url"] = harbor_url + dict_tmp_info.get("readme.md").get("href")
                            dict_info["values_url"] = harbor_url + dict_tmp_info.get("values.yaml").get("href")
                            dict_version["version"][dict_chart_info.get("version")] = dict_info

                        chart_info_db = self.convert_db_harbor(chartname, dict_version, repo_info_db, prefix_name)
                        chart_list.append(chart_info_db)
                    ChartSQL.create_chart_list(chart_list)
                    repo_info_db.status = util.repo_status_success
                    repo_info_db.status_msg = ""
                    RepoSQL.update_repo(repo_info_db)
                    break
                except asyncio.TimeoutError as e:
                    e_object = e
                    Log.error("Harbor API请求超时，请检查网络或Harbor服务状态")
                    try_times += 1
                except HTTPStatusError as e:
                    e_object = e
                    Log.error(f"Harbor API请求失败: {e}")
                    try_times += 1
                except Exception as e:
                    e_object = e
                    Log.error(f"other failed: {e}")
                    try_times += 1
            if try_times >= util.try_times:
                raise ValueError(f"{str(e_object)}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            Log.error("add global repo with harbor failed, reason %s" % str(e))
            raise e

    async def create_repo(self, repo: CreateRepoObject, update=False, status="creating"):
        repo_info_db = self.convert_repo_db(repo, status)
        if not update:
            repo_info_db.create_time = datetime.now()
            RepoSQL.create_repo(repo_info_db)
        else:
            repo_info_db.update_time = datetime.now()
            RepoSQL.update_repo(repo_info_db)
        if not update:
            Log.info("add repo started, repo id %s, name %s, url %s" % (repo_info_db.id,  repo.name, repo.url))
        elif status == "updating":
            Log.info("update repo started, repo id %s, name %s, url %s" % (repo_info_db.id,  repo.name, repo.url))
        else:
            Log.info("sync repo started, repo id %s, name %s, url %s" % (repo_info_db.id,  repo.name, repo.url))
        try:
            chart_list = []
            if repo.type == util.repo_type_http:
                # 处理http的repo
                # 1、处理index.yaml里面的内容
                content = self.handle_http_repo_content(repo.url, repo.username, repo.password)
                index_data = yaml.load(content, Loader=CLoader)
                if not index_data.get("entries") or not index_data.get("apiVersion") or not index_data.get("generated"):
                    Log.error("the content in index.yaml is empty, please check")
                    raise ValueError(f"the content in index.yaml is empty, please check")
                for chart_name, versions in index_data["entries"].items():
                    if len(versions) > util.chart_nubmer:
                        index_data["entries"][chart_name] = versions[:util.chart_nubmer]
                for chart_name, versions in index_data["entries"].items():
                    dict_version = {}
                    dict_version["description"] = versions[0].get("description")
                    dict_version["icon"] = versions[0].get("icon")
                    dict_version["create_time"] = versions[0].get("created")
                    dict_version["latest_version"] = versions[0].get("version")
                    dict_version["deprecated"] = versions[0].get("deprecated") or False
                    dict_version["version"] = dict()
                    for version in versions:
                        dict_info = {}
                        if isinstance(version.get("created"), datetime):
                            dict_info["create_time"] = version.get("created").isoformat()
                        else:
                            dict_info["create_time"] = version.get("created")
                        dict_info["urls"] = version.get("urls")
                        dict_info["deprecated"] = version.get("deprecated", False)
                        dict_version["version"][version.get("version")] = dict_info
                    chart_info_db = self.convert_chart_db(chart_name, dict_version, repo_info_db)
                    chart_list.append(chart_info_db)
                ChartSQL.create_chart_list(chart_list)
                repo_info_db.status = util.repo_status_success
                repo_info_db.status_msg = ""
                RepoSQL.update_repo(repo_info_db)
            else:
                # 处理oci类型的repo仓库，并添加repo的chart到数据库中
                await self.handle_oci_repo(repo_info_db)
            if not update:
                Log.info("add repo success, repo id %s, name %s, url %s" % (repo_info_db.id, repo.name, repo.url))
            elif status == "updating":
                Log.info("update repo success, repo id %s, name %s, url %s" % (repo_info_db.id, repo.name, repo.url))
            else:
                Log.info("sync repo success, repo id %s, name %s, url %s" % (repo_info_db.id, repo.name, repo.url))
        except Exception as e:
            import traceback
            traceback.print_exc()
            repo_info_db.status = "failed"
            repo_info_db.status_msg = str(e)
            RepoSQL.update_repo(repo_info_db)
            Log.error("add or update or sync repo failed, reason %s" % str(e))
            raise e

    async def create_repo_list(self, repo_list: List[CreateRepoObject], update=False, status="creating"):
        for repo in repo_list:
            await self.create_repo(repo, update, status)

    def get_chart(self, chart_id):
        # 声明查询条件的dict
        query_params = {}
        # 查询条件组装
        if chart_id:
            query_params['id'] = chart_id
        # 显示repo列表的逻辑
        data = self.list_charts(query_params, 1, -1, None, None)
        if data.get("total") > 0:
            chart_data = data.get("data")[0]
            chart_metadata = ChartMetadataObject(
                name=chart_data.name,
                description=chart_data.description,
                icon=chart_data.icon,
                repo=chart_data.repo_name,
                version=chart_data.latest_version
            )
            list_chart_version = []
            dict_chart_version = json.loads(chart_data.version)
            query_params = {}
            query_params['id'] = chart_data.repo_id
            repo_data = self.list_repos(query_params, 1, -1, None, None, display=True)
            username = repo_data.get("data")[0].username
            password = repo_data.get("data")[0].password
            if chart_data.type == "http":
                # 处理http类型的chart应用展示
                chart_url = ""
                for version, create_time_info in dict_chart_version.items():
                    if version == chart_data.latest_version:
                        chart_url = create_time_info.get("urls")[0]
                    chart_version_info = ChartVersionObject(
                        version=version,
                        created=create_time_info.get("create_time")
                    )
                    list_chart_version.append(chart_version_info)
                readme_content, values_dict = self.get_chart_details(chart_data.name, chart_url, username, password,
                                                                     chart_data.latest_version)
                if not readme_content or not values_dict:
                    raise ValueError(f"get chart {chart_data.name} failed, please check")
            else:
                # 处理oci类型的chart应用展示
                chart_readme_url = ""
                chart_values_url = ""
                for version, create_time_info in dict_chart_version.items():
                    if version == chart_data.latest_version:
                        chart_readme_url = create_time_info.get("readme_url")
                        chart_values_url = create_time_info.get("values_url")
                    chart_version_info = ChartVersionObject(
                        version=version,
                        created=create_time_info.get("create_time")
                    )
                    list_chart_version.append(chart_version_info)
                readme_content, values_dict = self.get_chart_oci_details(chart_readme_url, chart_values_url,
                                                                         username, password)
                if not readme_content or not values_dict:
                    raise ValueError(f"get oci chart {chart_data.name} failed, please check")

            chart_object = ChartObject(
                metadata=chart_metadata,
                readme=readme_content,
                values=values_dict
            )
            chart_data = ResponseChartObject(
                versions=list_chart_version,
                chart=chart_object,
            )
            success =True
        else:
            chart_data = ResponseChartObject(
                versions=None,
                chart=None,
            )
            success = False
        return {"data": chart_data, "success": success}

    def handle_docker_io_data(self, chart_name, chart_url, version, username=None, password=None):
        chart_readme = ""
        chart_data = {}
        chart_tmp_url = chart_url.replace("oci://", "").split("/", 1)
        repo_cahrt = ""
        if len(chart_tmp_url) >= 2:
            if len(chart_tmp_url[1].split(":")) >= 2:
                repo_cahrt = chart_tmp_url[1].split(":")[0]
            else:
                repo_cahrt = chart_tmp_url[1]
        url = f"https://{chart_tmp_url[0]}/v2/{repo_cahrt}/manifests/{version}"
        # 获取访问 Token
        auth_url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo_cahrt}:pull"
        if username and password:
            token = requests.get(auth_url, auth=HTTPBasicAuth(username, password), timeout=util.time_out).json().get("token")
        else:
            token = requests.get(auth_url, timeout=util.time_out).json().get("token")
        # 请求 Manifest
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.oci.image.manifest.v1+json"}
        response = requests.get(url, headers=headers, timeout=util.time_out)
        response.raise_for_status()
        manifest = response.json()
        for layer in manifest.get("layers", []):
            if layer.get("annotations", {}).get("org.opencontainers.image.title", "").endswith(".tgz"):
                digest = layer["digest"]
                break
        else:
            raise ValueError("chart blob not found")
        blob_url = f"https://{chart_tmp_url[0]}/v2/{repo_cahrt}/blobs/{digest}"
        response = requests.get(blob_url, headers={"Authorization": f"Bearer {token}"}, stream=True,
                                timeout=util.time_out)
        response.raise_for_status()
        import tarfile
        from io import BytesIO
        with tarfile.open(fileobj=BytesIO(response.content), mode="r:gz") as tar:
            # 提取 chart.yaml
            for name in tar.getnames():
                # 提取 values.yaml
                if name == f"{chart_name}/values.yaml":
                    with tar.extractfile(name) as f:
                        chart_data = yaml.safe_load(f.read())

                if name == f"{chart_name}/README.md":
                    with tar.extractfile(name) as f:
                        chart_readme = f.read().decode("utf-8")
        return chart_readme, chart_data

    def get_chart_details(self, chart_name, chart_url, username, password, version):
        """ 下载并解析 Chart 包中的详细配置 """
        try:
            if chart_url.startswith("oci://"):
                return self.handle_docker_io_data(chart_name, chart_url, version, username, password)
            if username and password:
                response = requests.get(chart_url, auth=HTTPBasicAuth(username, password), timeout=util.time_out)
            else:
                response = requests.get(chart_url, timeout=util.time_out)
            response.raise_for_status()
            chart_yaml = chart_name + "/Chart.yaml"
            values_yaml = chart_name + "/values.yaml"
            import tarfile
            from io import BytesIO
            chart_readme = ""
            chart_data = None
            with tarfile.open(fileobj=BytesIO(response.content)) as tar:
                for name in tar.getnames():
                    if chart_yaml == name:
                        chart_file = tar.extractfile(name)
                        chart_readme = chart_file.read()
                    if values_yaml == name:
                        chart_file = tar.extractfile(name)
                        chart_data = json.dumps(yaml.safe_load(chart_file))
            return chart_readme, chart_data
        except Exception as e:
            raise e

    # def get_chart_oci_details(self, chart_readme_url, chart_values_url, username, password):
    #     """ 下载并解析 Chart 包中的详细配置 """
    #     try:
    #         if username and password:
    #             response = requests.get(chart_readme_url, auth=HTTPBasicAuth(username, password), timeout=util.time_out)
    #         else:
    #             response = requests.get(chart_readme_url, timeout=util.time_out)
    #         response.raise_for_status()
    #         chart_readme = response.text
    #         if username and password:
    #             response = requests.get(chart_values_url, auth=HTTPBasicAuth(username, password), timeout=util.time_out)
    #         else:
    #             response = requests.get(chart_values_url, timeout=util.time_out)
    #         response.raise_for_status()
    #         index_data = yaml.load(response.text, Loader=CLoader)
    #         return chart_readme, index_data
    #     except Exception as e:
    #         raise e

    def get_chart_oci_details(self, chart_readme_url, chart_values_url, username, password):
        """ 并发下载并解析 Chart 包中的详细配置 """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        def fetch_url(url):
            """ 内部函数：发送HTTP请求 """
            try:
                auth = HTTPBasicAuth(username, password) if username and password else None
                response = requests.get(url, auth=auth, timeout=util.time_out)
                response.raise_for_status()
                return url, response.text
            except Exception as e:
                raise RuntimeError(f"请求失败 {url}: {str(e)}")

        try:
            # 准备要并发的URL列表
            urls = [chart_readme_url, chart_values_url]

            # 使用线程池并发执行请求
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {executor.submit(fetch_url, url): url for url in urls}

                results = {}
                for future in as_completed(futures):
                    url, content = future.result()
                    results[url] = content

            # 提取并处理结果
            chart_readme = results[chart_readme_url]
            values_content = results[chart_values_url]
            index_data = json.dumps(yaml.safe_load(values_content))

            return chart_readme, index_data

        except Exception as e:
            raise RuntimeError(f"获取Chart详情失败: {str(e)}")

    def get_chart_version(self, chart_id, chart_version):
        # 声明查询条件的dict
        query_params = {}
        # 查询条件组装
        if chart_id:
            query_params['id'] = chart_id
        # 显示repo列表的逻辑
        data = self.list_charts(query_params, 1, -1, None, None)
        if data.get("total") > 0:
            chart_data = data.get("data")[0]
            chart_metadata = ChartMetadataObject(
                name=chart_data.name,
                description=chart_data.description,
                icon=chart_data.icon,
                repo=chart_data.repo_name,
                version=chart_version
            )
            dict_chart_version = json.loads(chart_data.version)
            query_params = {}
            query_params['id'] = chart_data.repo_id
            repo_data = self.list_repos(query_params, 1, -1, None, None, display=True)
            username = repo_data.get("data")[0].username
            password = repo_data.get("data")[0].password
            if chart_data.type == "http":
                # 处理http类型的chart应用展示
                chart_url = ""
                for version, create_time_info in dict_chart_version.items():
                    if version == chart_version:
                        chart_url = create_time_info.get("urls")[0]
                readme_content, values_dict = self.get_chart_details(chart_data.name, chart_url, username, password,
                                                                     chart_version)
                if not readme_content or not values_dict:
                    raise ValueError(f"get chart {chart_data.name} failed, please check")
            else:
                # 处理oci类型的chart应用展示
                chart_readme_url = ""
                chart_values_url = ""
                for version, create_time_info in dict_chart_version.items():
                    if version == chart_version:
                        chart_readme_url = create_time_info.get("readme_url")
                        chart_values_url = create_time_info.get("values_url")
                if not chart_readme_url or not chart_values_url:
                    raise ValueError(f"get oci chart {chart_data.name} content failed, please check")
                readme_content, values_dict = self.get_chart_oci_details(chart_readme_url, chart_values_url,
                                                                         username, password)
                if not readme_content or not values_dict:
                    raise ValueError(f"get oci chart {chart_data.name} failed, please check")

            chart_object = ChartObject(
                metadata=chart_metadata,
                readme=readme_content,
                values=values_dict
            )
            success = True
        else:
            chart_object = ChartObject(
                metadata=None,
                readme=None,
                values=None
            )
            success = False
        return {"data": chart_object, "success": success}

    def get_chart_version_info(self, chart_id):
        query_params = {}
        # 查询条件组装
        if chart_id:
            query_params['id'] = chart_id
        # 显示repo列表的逻辑
        data = self.list_charts(query_params, 1, -1, None, None)
        if data.get("total") > 0:
            chart_data = data.get("data")[0]
            return chart_data
        else:
            raise ValueError("chart not found")

    def get_app_data_info(self, chart_data, chart_version):
        repo_id = chart_data.repo_id
        repo_data = self.get_repo_from_id(repo_id, display=True).get("data")
        repo_url = ""
        if repo_data:
            repo_url = repo_data.url
            result = urlparse(repo_url)
            repo_url = repo_url.split(result.scheme + "://")[1]
        dict_chart_version = json.loads(chart_data.version)
        if dict_chart_version.get(chart_version):
            if chart_data.type == util.repo_type_http:
                remote_url = dict_chart_version.get(chart_version).get("urls")
                if remote_url:
                    remote_url = remote_url[0]
                else:
                    raise ValueError("chart url not found")
                if remote_url.startswith("oci://"):
                    prefix, tag = remote_url.rsplit(":", 1)
                    remote_url = prefix
            else:
                if chart_data.prefix_name:
                    remote_url = "oci://" + repo_url + "/" + chart_data.prefix_name +  "/" + chart_data.name
                else:
                    remote_url = "oci://" + repo_url + "/" + chart_data.name
            return chart_data.type, repo_url, remote_url, repo_data.username, repo_data.password
        else:
            raise ValueError("chart version not found")

    def get_kubeconfig(self, cluster_id):
        res_cluster = ClusterService().get_cluster(cluster_id)
        helm_cache_dir = os.path.join(WORK_DIR, "ansible-deploy/inventory/", cluster_id, util.helm_cache)
        print("helm_cache_dir is:", helm_cache_dir)
        os.makedirs(helm_cache_dir, exist_ok=True)
        kube_config = os.path.join(WORK_DIR, "ansible-deploy/inventory/", cluster_id, "kube_config")
        with open(kube_config, "w") as f :
            f.write(yaml.dump(json.loads(res_cluster.kube_info.kube_config)))
        return kube_config, helm_cache_dir

    def convert_app_db(self, create_data: ChartDB, create_info: CreateAppObject, update=False):
        app_db = AppDB()
        if update:
            app_db.id = create_info.id
            app_db.status = util.app_status_update
            app_db.version = create_info.chart_version
            app_db.update_time = datetime.now()
            return app_db
        else:
            app_db.status = util.app_status_create
            app_db.create_time = datetime.now()
        app_db.name = create_info.name
        app_db.cluster_id = create_info.cluster_id
        app_db.chart_id = create_data.id
        app_db.repo_id = create_data.repo_id
        app_db.version = create_info.chart_version
        app_db.values = json.dumps(create_info.values)
        app_db.namespace = create_info.namespace
        app_db.description = create_info.description
        app_db.repo_name = create_data.repo_name
        app_db.type = create_data.type
        app_db.tag_id = create_data.tag_id
        app_db.tag_name = create_data.tag_name
        return app_db

    def login_registry(self, repo_url, username, password, config):
        try:
            cmd_list = [
                "helm",
                "registry",
                "login", repo_url,
                "--username", username,
                "--password", password,
                "--registry-config", config
            ]
            Log.info("helm cmd: %s" % " ".join(cmd_list))
            result = subprocess.run(cmd_list, capture_output=True, text=True)
            if result.returncode != 0:
                raise ValueError(result.stderr)
        except Exception as e:
            raise e

    def run_helm_upgrade(self, release_name, remote_url, version, config, helm_cache_dir, kube_config, values,
                         namespace, username=None, password=None):
        """执行 Helm 升级/安装操作"""
        values_yaml = str(uuid.uuid4()) + ".yaml"
        value_yaml = os.path.join(helm_cache_dir, values_yaml)
        with open(value_yaml, "w", encoding="utf-8") as f:
            yaml.dump(values, f, allow_unicode=True)
        # 定义 Helm 命令参数
        if username and password:
            helm_command = [
                "helm",
                "upgrade",
                release_name,
                remote_url,
                "--version", version,
                "--history-max", "10",
                "--install",
                "--timeout", "5m",
                "--registry-config", config,
                "--repository-cache", helm_cache_dir,
                "--kubeconfig", kube_config,
                "--username", username,
                "--password", password,
                "-f", value_yaml
            ]
        else:
            helm_command = [
                "helm",
                "upgrade",
                release_name,
                remote_url,
                "--version", version,
                "--history-max", "10",
                "--install",
                "--timeout", "5m",
                "--registry-config", config,
                "--repository-cache", helm_cache_dir,
                "--kubeconfig", kube_config,
                "--namespace", namespace,
                "-f", value_yaml
            ]
        Log.info("helm cmd: %s" % " ".join(helm_command))
        try:
            # 执行命令并捕获输出
            result = subprocess.run(
                helm_command,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                raise ValueError(result.stderr)
        except Exception as e:
            raise e

    def install_chart_app(self, app_type, repo_url, remote_url, name, version, values, kube_config, helm_cache_dir,
                          username, password, namespace):
        # 根据type类型判断下如何处理，如果是http的如何处理？
        # 如果是oci的如何处理？需要仔细的处理清楚
        # 还有带不带--plain-http也需要考虑进去
        try:
            config = os.path.join(helm_cache_dir, util.registry_config)
            if app_type == util.repo_type_http:
                self.run_helm_upgrade(name, remote_url, version, config, helm_cache_dir, kube_config, values, namespace
                                      , username, password)
            else:
                # 1、先要login登录harbor上才行
                self.login_registry(repo_url, username, password, config)
                # 2、执行命令
                self.run_helm_upgrade(name, remote_url, version, config, helm_cache_dir, kube_config, values, namespace)
            # 清除安装产生的缓存文件
            shutil.rmtree(helm_cache_dir)
        except Exception as e:
            shutil.rmtree(helm_cache_dir)
            raise e

    def install_app(self, create_data: CreateAppObject, update=False):
        """ 下载并解析 Chart 包中的详细配置 """
        # 0、写入数据库中
        chart_info = self.get_chart_version_info(create_data.chart_id)
        app_info_db = self.convert_app_db(chart_info, create_data, update=update)
        if update:
            AppSQL.update_app(app_info_db)
        else:
            AppSQL.create_app(app_info_db)
        try:
            # 1、先获取cluster_id的信息，拿到kube-config文件
            kube_config, helm_cache_dir = self.get_kubeconfig(create_data.cluster_id)
            # 2、根据chart_id和chart_version信息来指定安装，根据类型区分https和http，http类型的也有可能是oci的url的chart包
            app_type, repo_url, remote_url, username, password = self.get_app_data_info(chart_info,
                                                                                        create_data.chart_version)
            # 3、如何使用helm的sdk实现安装应用, 创建cache目录，执行命令时添加这个cache目录执行
            self.install_chart_app(app_type, repo_url, remote_url, create_data.name, create_data.chart_version,
                                   create_data.values, kube_config, helm_cache_dir, username, password,
                                   create_data.namespace)
            # 4、如何写入app的状态以及values的信息
            app_info_db.status = util.app_status_success
            app_info_db.status_msg = ""
            app_info_db.values = json.dumps(create_data.values)
            AppSQL.update_app(app_info_db)
        except Exception as e:
            # 写入failed的状态
            app_info_db.status = util.app_status_failed
            app_info_db.status_msg = str(e)
            AppSQL.update_app(app_info_db)
            # 清理缓存文件，删除目录等等操作
            if update:
                Log.error(f"update app error: {str(e)}")
                raise ValueError(f"update app error: {str(e)}")
            else:
                Log.error(f"install app error: {str(e)}")
                raise ValueError(f"install app error: {str(e)}")

    def uninstall_chart_app(self, name, kube_config, namespace):
        helm_command = [
            "helm",
            "uninstall",
            name,
            "--kubeconfig", kube_config,
            "--namespace", namespace
        ]

        try:
            # 执行命令并捕获输出
            result = subprocess.run(
                helm_command,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                raise ValueError(result.stderr)
        except Exception as e:
            raise e

    def delete_app(self, app_data: AppDB):
        app_data.status = util.app_status_delete
        AppSQL.update_app(app_data)
        try:
            kube_config, helm_cache_dir = self.get_kubeconfig(app_data.cluster_id)
            # 2、根据chart_id和chart_version信息来指定安装，根据类型区分https和http，http类型的也有可能是oci的url的chart包
            self.uninstall_chart_app(app_data.name, kube_config, app_data.namespace)
            AppSQL.delete_app(app_data)
        except Exception as e:
            # 写入failed的状态
            app_data.status = util.app_status_failed
            app_data.status_msg = str(e)
            AppSQL.update_app(app_data)
            raise ValueError(f"uninstall app error: {str(e)}")

    def get_info_cmd(self, kube_config, namespace, name):
        helm_command = [
            "helm",
            "status",
            name,
            "--kubeconfig", kube_config,
            "--namespace", namespace,
            "--show-resources", "-o", "json"
        ]
        # 执行命令并捕获输出
        result = subprocess.run(
            helm_command,
            capture_output=True,
            text=True
        )
        if result.returncode!= 0:
            raise ValueError(result.stderr)
        else:
            return result.stdout

    def get_app_detail(self, app_data: AppDB):
        try:
            query_params = {}
            query_params['id'] = app_data.chart_id
            # 显示repo列表的逻辑
            data = self.list_charts(query_params, 1, -1, None, None)
            if data.get("total") > 0:
                chart_data = data.get("data")[0]
                # 0、要获取kube_config文件， 执行对应的命令获取下面的资源
                kube_config, helm_cache_dir = self.get_kubeconfig(app_data.cluster_id)
                content = self.get_info_cmd(kube_config, app_data.namespace, app_data.name)
                dict_content = json.loads(content)
                resourc_obj_list = []
                # 1、获取chart信息
                app_obj = AppChartObject(
                    name=chart_data.name,
                    description=chart_data.description,
                    repo_name=chart_data.repo_name,
                    icon=chart_data.icon
                )

                if dict_content.get("info") and dict_content.get("info").get("resources"):
                    for k, v in dict_content.get("info").get("resources").items():
                        if "related" in k:
                            continue
                        if len(v) > 0:
                            for vv in v:
                                if vv.get("status") and vv.get("status").get("phase"):
                                    if vv.get("status").get("phase") in ("Running", "Succeeded"):
                                        vv["status"]["phase"] = util.resource_status_active
                                    elif vv.get("status").get("phase").lower() == "failed":
                                        vv["status"]["phase"] = util.resource_status_failed
                                    elif vv.get("status").get("phase").lower() == "unknown":
                                        vv["status"]["phase"] = util.resource_status_unknown
                                    else:
                                        vv["status"]["phase"] = util.resource_status_pend
                                    resourc_obj = ResourcesObject(
                                        name=vv.get("metadata").get("name"),
                                        namespace=vv.get("metadata").get("namespace"),
                                        kind=vv.get("kind"),
                                        status=vv.get("status").get("phase")
                                    )
                                    resourc_obj_list.append(resourc_obj)
                                    continue

                                if vv.get("status") and vv.get("status") and not vv.get("status").get("phase"):
                                    if vv.get("status").get("availableReplicas") and vv.get("status").get(
                                            "availableReplicas") and vv.get("status").get("replicas"):
                                        if vv.get("status").get("replicas") == vv.get("status").get(
                                                "readyReplicas") == vv.get("status").get("availableReplicas"):
                                            resourc_obj = ResourcesObject(
                                                name=vv.get("metadata").get("name"),
                                                namespace=vv.get("metadata").get("namespace"),
                                                kind=vv.get("kind"),
                                                status=util.resource_status_active
                                            )
                                            resourc_obj_list.append(resourc_obj)
                                            continue
                                        else:
                                            resourc_obj = ResourcesObject(
                                                name=vv.get("metadata").get("name"),
                                                namespace=vv.get("metadata").get("namespace"),
                                                kind=vv.get("kind"),
                                                status=util.resource_status_pend
                                            )
                                            resourc_obj_list.append(resourc_obj)
                                            continue
                                    elif vv.get("status").get("unavailableReplicas"):
                                        resourc_obj = ResourcesObject(
                                            name=vv.get("metadata").get("name"),
                                            namespace=vv.get("metadata").get("namespace"),
                                            kind=vv.get("kind"),
                                            status=util.resource_status_failed
                                        )
                                        resourc_obj_list.append(resourc_obj)
                                        continue
                                    elif "service" in k.lower() and vv.get("spec").get("type") == "LoadBalancer":
                                        if not vv.get("status").get("loadBalancer"):
                                            resourc_obj = ResourcesObject(
                                                name=vv.get("metadata").get("name"),
                                                namespace=vv.get("metadata").get("namespace"),
                                                kind=vv.get("kind"),
                                                status=util.resource_status_pend
                                            )
                                            resourc_obj_list.append(resourc_obj)
                                            continue
                                        else:
                                            resourc_obj = ResourcesObject(
                                                name=vv.get("metadata").get("name"),
                                                namespace=vv.get("metadata").get("namespace"),
                                                kind=vv.get("kind"),
                                                status=util.resource_status_active
                                            )
                                            resourc_obj_list.append(resourc_obj)
                                            continue
                                    elif "service" in k.lower() and vv.get("spec").get("type") != "LoadBalancer":
                                        resourc_obj = ResourcesObject(
                                            name=vv.get("metadata").get("name"),
                                            namespace=vv.get("metadata").get("namespace"),
                                            kind=vv.get("kind"),
                                            status=util.resource_status_active
                                        )
                                        resourc_obj_list.append(resourc_obj)
                                        continue
                                    elif "statefulset" in k.lower() and vv.get("status"):
                                        if vv.get("status").get("replicas") == vv.get("status").get(
                                                "readyReplicas") == vv.get("status").get("availableReplicas"):
                                            resourc_obj = ResourcesObject(
                                                name=vv.get("metadata").get("name"),
                                                namespace=vv.get("metadata").get("namespace"),
                                                kind=vv.get("kind"),
                                                status=util.resource_status_active
                                            )
                                            resourc_obj_list.append(resourc_obj)
                                            continue
                                        else:
                                            resourc_obj = ResourcesObject(
                                                name=vv.get("metadata").get("name"),
                                                namespace=vv.get("metadata").get("namespace"),
                                                kind=vv.get("kind"),
                                                status=util.resource_status_pend
                                            )
                                            resourc_obj_list.append(resourc_obj)
                                            continue
                                    elif "daemonset" in k.lower() and vv.get("status"):
                                        if vv.get("status").get("numberReady") == vv.get("status").get(
                                                "desiredNumberScheduled") == vv.get("status").get(
                                                "currentNumberScheduled"):
                                            resourc_obj = ResourcesObject(
                                                name=vv.get("metadata").get("name"),
                                                namespace=vv.get("metadata").get("namespace"),
                                                kind=vv.get("kind"),
                                                status=util.resource_status_active
                                            )
                                            resourc_obj_list.append(resourc_obj)
                                            continue
                                        else:
                                            resourc_obj = ResourcesObject(
                                                name=vv.get("metadata").get("name"),
                                                namespace=vv.get("metadata").get("namespace"),
                                                kind=vv.get("kind"),
                                                status=util.resource_status_pend
                                            )
                                            resourc_obj_list.append(resourc_obj)
                                            continue

                                if vv.get("metadata") and not vv.get("status"):
                                    resourc_obj = ResourcesObject(
                                        name=vv.get("metadata").get("name"),
                                        namespace=vv.get("metadata").get("namespace"),
                                        kind=vv.get("kind"),
                                        status=util.resource_status_active
                                    )
                                    resourc_obj_list.append(resourc_obj)
                                    continue
                                resourc_obj = ResourcesObject(
                                    name=vv.get("metadata").get("name"),
                                    namespace=vv.get("metadata").get("namespace"),
                                    kind=vv.get("kind"),
                                    status=util.resource_status_unknown
                                )
                                resourc_obj_list.append(resourc_obj)

                    # 3、把上述的资源信息和chart信息组装成一个对象返回
                    response_obj = ResponseAppObject(
                        resources=resourc_obj_list,
                        values=app_data.values,
                        chart_info=app_obj
                    )
                else:
                    response_obj = ResponseAppObject(
                        resources=None,
                        values=app_data.values,
                        chart_info=app_obj
                    )
                return response_obj
            else:
                raise ValueError("chart not found")

        except Exception as e:
            raise ValueError(f"get app detail error: {str(e)}")

    def get_helm_list(self, kube_config):
        helm_command = [
            "helm",
            "list",
            "--kubeconfig", kube_config,
            "-A",
            "-o", "json"
        ]
        # 执行命令并捕获输出
        result = subprocess.run(
            helm_command,
            capture_output=True,
            text=True
        )
        if result.returncode!= 0:
            raise ValueError(result.stderr)

        return result.stdout