import json

import time
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from oslo_log import log

from dingo_command.db.models.chart.sql import AppSQL
from dingo_command.db.models.cluster.sql import ClusterSQL

LOG = log.getLogger(__name__)

scheduler = BackgroundScheduler()
blocking_scheduler = BlockingScheduler()
# 启动完成后执行
run_time_10s = datetime.now() + timedelta(seconds=10)  # 任务将在10秒后执行
run_time_30s = datetime.now() + timedelta(seconds=30)  # 任务将在30秒后执行


def start():
    # 添加检查集群状态的定时任务，每180秒执行一次
    scheduler.add_job(check_app_status, 'interval', seconds=300, next_run_time=datetime.now())
    scheduler.start()


def check_app_status():
    """
    定期检查k8s集群状态并更新数据库
    """
    try:
        LOG.info(f"Starting check app status at {time.strftime('%Y-%m-%d %H:%M:%S')}")

        # 获取所有状态为 creating、running 或 error 的集群
        query_params = {}
        count, apps = AppSQL.list_apps(query_params, page_size=-1)
        for app in apps:
            # 1、先获取cluster_id，然后获取kube_config文件
            cluster_id = app.cluster_id
            query_params = {}
            query_params["id"] = cluster_id
            count, clusters = ClusterSQL.list_cluster(query_params, 1, -1, sort_keys=None, sort_dirs=None)
            kube_config = json.loads(clusters[0].kube_info).get("kube_config")
            # 2、拿到kube_config文件后，通过helm list获取真实存在的app的名称
            # 3、比对app的名称和数据库中的app名称是否存在，如果数据库中存在但是helm list中不存在，说明app已经被删除，需要重新安装下这个app
            pass

    except Exception as e:
        LOG.error(f"Error in app_status: {str(e)}")