import json
import time
import os
import shutil
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from oslo_log import log

from dingo_command.db.models.chart.sql import AppSQL, RepoSQL
from dingo_command.db.models.cluster.sql import ClusterSQL
from dingo_command.services.chart import ChartService
from dingo_command.api.model.chart import CreateRepoObject, CreateAppObject
from dingo_command.utils.helm import util


LOG = log.getLogger(__name__)
config_dir = "/tmp/kube_config_dir"
scheduler = BackgroundScheduler()
scheduler_async = AsyncIOScheduler()

blocking_scheduler = BlockingScheduler()
# 启动完成后执行
run_time_10s = datetime.now() + timedelta(seconds=10)  # 任务将在10秒后执行
run_time_30s = datetime.now() + timedelta(seconds=30)  # 任务将在30秒后执行
chart_service = ChartService()


def start():
    # 添加检查集群状态的定时任务，每180秒执行一次
    scheduler.add_job(check_app_status, 'interval', seconds=300)
    scheduler.add_job(check_cluster_status, 'interval', seconds=3600)
    scheduler.start()
    scheduler_async.add_job(check_sync_status,'cron', hour=0, minute=0)
    scheduler_async.start()


def check_app_status():
    """
    定期检查k8s集群状态并更新数据库
    """
    try:
        LOG.info(f"Starting check app status at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        os.makedirs(config_dir, exist_ok=True)
        # 先获取所有repo的cluster_id
        query_params = {}
        count, repos = RepoSQL.list_repos(query_params, page_size=-1)
        cluster_id_list = []
        for repo in repos:
            if repo.is_global:
                continue
            cluster_id = repo.cluster_id
            if cluster_id not in cluster_id_list:
                query_params = {}
                query_params["id"] = cluster_id
                count, clusters = ClusterSQL.list_cluster(query_params, 1, -1, sort_keys=None, sort_dirs=None)
                if count < 1:
                    continue
                else:
                    cluster_id_list.append(cluster_id)
        # 遍历cluster_id_list
        for cluster_id in cluster_id_list:
            # 1、先获取cluster_id，然后获取kube_config文件
            query_params = {}
            query_params["cluster_id"] = cluster_id
            count, apps = AppSQL.list_apps(query_params, page_size=-1)
            if count < 1:
                continue
            query_params = {}
            query_params["id"] = cluster_id
            count, clusters = ClusterSQL.list_cluster(query_params, 1, -1, sort_keys=None, sort_dirs=None)
            if count < 1:
                continue
            # 1、先获取cluster_id，然后获取kube_config文件
            kube_config = json.loads(clusters[0].kube_info).get("kube_config")
            if not kube_config:
                continue
            config_file = os.path.join(config_dir, f"{cluster_id}_kube_config")
            with open(config_file, "w") as f:
                f.write(kube_config)

            # 2、拿到kube_config文件后，通过helm list获取真实存在的app的名称
            content = chart_service.get_helm_list(config_file)
            content_list = json.loads(content)
            for app in apps:
                flag = False
                # 看看数据库中的app是否存在，如果存在，但是helm list中不存在，说明app已经被删除，需要重新安装下这个app
                # 3、比对app的名称和数据库中的app名称是否存在，如果数据库中存在但是helm list中不存在，说明app已经被删除，
                # 需要重新安装下这个app
                for content in content_list:
                    if (app.status == util.app_status_success and app.name == content.get("name") and
                            app.namespace == content.get("namespace")):
                        flag = True
                        break
                if not flag:
                    # 重新安装app
                    create_data = CreateAppObject(
                        id=str(app.id),
                        name=app.name,
                        namespace=app.namespace,
                        chart_id=str(app.chart_id),
                        cluster_id=app.cluster_id,
                        values=json.loads(app.values),
                        chart_version=app.version,
                        description=app.description,
                    )
                    chart_service.install_app(create_data, update=True)
        shutil.rmtree(config_dir)
        LOG.info(f"Finished check app status at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        LOG.error(f"Error in app_status: {str(e)}")


def check_cluster_status():
    """
    定期检查k8s集群状态并更新数据库
    """
    try:
        LOG.info(f"Starting check cluster status at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        # 1、先获取cluster的状态，如果已经删除那就把所有的关于此cluster的repo都删除
        query_params = {}
        count, repos = RepoSQL.list_repos(query_params, page_size=-1)
        remove_repo_list = []
        remove_app_list = []
        remove_cluster_list = []
        cluster_id_list = []
        if len(repos) == 1:
            if repos[0].except_cluster:
                repo = repos[0]
                repo.except_cluster = None
                RepoSQL.update_repo(repo)
                return
        for repo in repos:
            if repo.is_global:
                continue
            cluster_id = repo.cluster_id
            if cluster_id not in cluster_id_list:
                query_params = {}
                query_params["id"] = cluster_id
                count, clusters = ClusterSQL.list_cluster(query_params, 1, -1, sort_keys=None, sort_dirs=None)
                if count < 1:
                    remove_cluster_list.append(cluster_id)
                    remove_repo_list.append(repo)
                    continue
                else:
                    cluster_id_list.append(cluster_id)
        # 2、把所有的关于该集群的app都删除，清理干净
        query_params = {}
        count, apps = AppSQL.list_apps(query_params, page_size=-1)
        cluster_id_list = []
        for app in apps:
            # 1、先获取cluster_id，然后获取kube_config文件
            cluster_id = app.cluster_id
            if cluster_id not in cluster_id_list:
                query_params = {}
                query_params["id"] = cluster_id
                count, clusters = ClusterSQL.list_cluster(query_params, 1, -1, sort_keys=None, sort_dirs=None)
                if count < 1:
                    remove_cluster_list.append(cluster_id)
                    remove_app_list.append(app)
                    continue
                else:
                    cluster_id_list.append(cluster_id)
        RepoSQL.delete_repo_list(remove_repo_list)
        AppSQL.delete_app_list(remove_app_list)
        # 3、把全局的repo里面从except_cluster里面把cluster_id给剔除出去
        real_remove_cluster_list = list(set(remove_cluster_list))
        query_params = {}
        query_params["is_global"] = True
        count, repos = RepoSQL.list_repos(query_params, page_size=-1)
        if count < 1:
            return
        repo = repos[0]
        if not repo.except_cluster:
            return
        except_cluster = json.loads(repo.except_cluster)
        for cluster_id in real_remove_cluster_list:
            if cluster_id in except_cluster:
                except_cluster.remove(cluster_id)
        repo.except_cluster = json.dumps(except_cluster)
        RepoSQL.update_repo(repo)
        LOG.info(f"Finished check cluster_status at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        LOG.error(f"Error in cluster_status: {str(e)}")


async def check_sync_status():
    """
    定期检查k8s集群状态并更新数据库
    """
    try:
        LOG.info(f"Starting check harbor sync status at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        # 1、定时同步harbor的repo
        # 同步repo的charts
        repo_id = "1"
        data = chart_service.get_repo_from_id(repo_id, display=True)
        if not data.get("data"):
            raise ValueError("repo not found")
        repo_data = data.get("data")
        # 先删除原来的repo的charts应用
        data = chart_service.get_repo_from_name(repo_id)
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
        await chart_service.create_repo(repo_data_info, update=True, status="syncing")
        LOG.info(f"Finished check harbor sync status at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        LOG.error(f"Error in check_sync_status: {str(e)}")