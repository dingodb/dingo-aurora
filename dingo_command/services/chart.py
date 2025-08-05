import json
import logging
import os
import shutil
import uuid
from io import BytesIO
import requests
from urllib.parse import urlparse
from requests.auth import HTTPBasicAuth
from typing import Union
from datetime import datetime
from math import ceil
from openpyxl.styles import Border, Side
from yaml import CLoader
import yaml
from harborapi import HarborAsyncClient
import asyncio
from urllib.parse import urlparse

from oslo_log import log
from dingo_command.api.model.chart import CreateRepoObject, CreateAppObject, CreateChartObject
from dingo_command.db.models.chart.models import RepoInfo as RepoDB
from dingo_command.db.models.chart.models import ChartInfo as ChartDB
from dingo_command.db.models.chart.models import AppInfo as AppDB
from dingo_command.db.models.chart.models import TagInfo as TagDB
from dingo_command.db.models.chart.sql import RepoSQL, AppSQL, ChartSQL, TagSQL

from dingo_command.services.system import SystemService
from dingo_command.services import CONF
from dingo_command.utils.helm import util
from dingo_command.services.custom_exception import Fail
from dingo_command.utils.helm.util import ChartLOG as Log

WORK_DIR = CONF.DEFAULT.cluster_work_dir
auth_url = CONF.DEFAULT.auth_url
image_master = CONF.DEFAULT.k8s_master_image
harbor_url = CONF.DEFAULT.chart_harbor_url
harbor_user = CONF.DEFAULT.chart_harbor_user
harbor_passwd = CONF.DEFAULT.chart_harbor_passwd
index_yaml = "index.yaml"


# 定义边框样式
thin_border = Border(
    left=Side(border_style="thin", color="000000"),  # 左边框
    right=Side(border_style="thin", color="000000"),  # 右边框
    top=Side(border_style="thin", color="000000"),  # 上边框
    bottom=Side(border_style="thin", color="000000")  # 下边框
)

system_service = SystemService()

async def create_harbor_repo(repo_name=util.repo_global_name, url=harbor_url, username=harbor_user, password=harbor_passwd):
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
            if data.get("data")[0].url != url or data.get("data")[0].status == "creating":
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

        service = ChartService()
        await service.handle_oci_repo(repo_info_db)
    except asyncio.TimeoutError:
        Log.error("Harbor API请求超时，请检查网络或Harbor服务状态")
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
            if count > 0 and not display:
                for repo in data:
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
            count, data = ChartSQL.list_charts(query_params, page, page_size, sort_keys, sort_dirs)

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

    def get_repo_from_id(self, repo_id, cluster_id=None):
        query_params = {}
        query_params['id'] = repo_id
        if cluster_id:
            query_params['cluster_id'] = cluster_id
        data = self.list_repos(query_params, 1, -1, None, None)
        if data.get("total") > 0:
            return {"data": data.get("data")[0]}
        else:
            return {"data": None}

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
                    raise Fail(error_code=405, error_message="Repo name already exists")
                if r.url == repo.url and r.cluster_id == repo.cluster_id:
                    # 如果查询结果不为空，说明仓库地址已存在
                    raise Fail(error_code=405, error_message=f"The same repo url already exists, repo name is {r.name}")

    def convert_repo_db(self, repo: CreateRepoObject):
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
        repo_info_db.status = "creating"
        return repo_info_db

    def convert_db_harbor(self, chart_name, artifact_info, repo_info_db, harbor_url):
        chart_info_db = ChartDB()
        chart_info_db.name = chart_name
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

            # 设置3秒超时
            repositories = await asyncio.wait_for(
                client.get_repositories(project_name=project_name), timeout=util.time_out
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

            # 第三步：并发执行所有制品获取任务
            chart_list = []
            await asyncio.gather(*artifact_tasks, return_exceptions=True)
            for artifact in artifact_tasks:
                if artifact.result()[0].type != "CHART":
                    continue
                dict_version = {}
                versions = artifact.result()
                chartname = versions[0].repository_name.split(f"{project_name}/")[-1]
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

                chart_info_db = self.convert_db_harbor(chartname, dict_version, repo_info_db, harbor_url)
                chart_list.append(chart_info_db)
            ChartSQL.create_chart_list(chart_list)
            repo_info_db.status = util.repo_status_success
            RepoSQL.update_repo(repo_info_db)
        except asyncio.TimeoutError:
            Log.error("Harbor API请求超时，请检查网络或Harbor服务状态")
        except Exception as e:
            import traceback
            traceback.print_exc()
            Log.error("add global repo with harbor failed, reason %s" % str(e))
            raise e

    async def create_repo(self, repo: CreateRepoObject, update=False):
        try:
            repo_info_db = self.convert_repo_db(repo)
            if not update:
                repo_info_db.create_time = datetime.now()
                RepoSQL.create_repo(repo_info_db)
            else:
                repo_info_db.update_time = datetime.now()
                RepoSQL.update_repo(repo_info_db)
            Log.info("add or update repo started, repo id %s, name %s, url %s" % (repo_info_db.id,  repo.name, repo.url))
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
                RepoSQL.update_repo(repo_info_db)
            else:
                # 处理oci类型的repo仓库，并添加repo的chart到数据库中
                await self.handle_oci_repo(repo_info_db)
            Log.info("add or update repo success, repo id %s, name %s, url %s" % (repo_info_db.id, repo.name, repo.url))
        except Exception as e:
            import traceback
            traceback.print_exc()
            query_params = {}
            query_params['name'] = repo.name
            query_params['cluster_id'] = repo.cluster_id
            data = self.list_repos(query_params, 1, -1, None, None, display=True)
            if data.get("total") > 0:
                if data.get("data")[0].status != "failed":
                    data.get("data")[0].status = "failed"
                    data.get("data")[0].status_msg = str(e)
                    RepoSQL.update_repo(data.get("data")[0])
            Log.error("add or update repo failed, reason %s" % str(e))
            raise e