import json

from apscheduler.schedulers.blocking import BlockingScheduler
from pymemcache.client.base import Client
from apscheduler.schedulers.background import BackgroundScheduler
from dingoops.services.bigscreens import BigScreensService, region_name
from dingoops.services.bigscreenshovel import BigScreenShovelService
from dingoops.jobs import CONF
from datetime import datetime, timedelta
import time
import os
import tempfile
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from dingoops.services.syn_bigscreens import BigScreenSyncService
from dingoops.services.websocket_service import websocket_service
from dingoops.db.models.cluster.sql import ClusterSQL
from dingoops.db.models.node.sql import NodeSQL
from dingoops.db.models.instance.sql import InstanceSQL
from oslo_log import log


LOG = log.getLogger(__name__)

scheduler = BackgroundScheduler()
blocking_scheduler = BlockingScheduler()
# 启动完成后执行
run_time_10s = datetime.now() + timedelta(seconds=10)  # 任务将在10秒后执行
run_time_30s = datetime.now() + timedelta(seconds=30)  # 任务将在30秒后执行

def start():
    #scheduler.add_job(fetch_bigscreen_metrics, 'interval', seconds=5, next_run_time=datetime.now())
    # 添加检查集群状态的定时任务，每60秒执行一次
    scheduler.add_job(check_k8s_cluster_status, 'interval', seconds=60, next_run_time=datetime.now())
    scheduler.start()

def check_cluster_status():
    """
    定期检查k8s集群状态并更新数据库
    """
    try:
        LOG.info(f"Starting check k8s cluster status at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 获取所有状态为 creating、running 或 error 的集群
        query_params = {}
        #query_params["status_in"] = ["creating", "running", "error"]
        clusters = ClusterSQL.list_cluster(query_params)
        
        for cluster in clusters:
            try:
                # 检查实例状态
                instance_query = {"cluster_id": cluster.id}
                instances = InstanceSQL.list_instances(instance_query)
                # 检查集群类型是否为 kubernetes
                if cluster.type != "kubernetes":
                    continue
                else:
                    # 检查API服务器状态
                    api_server_status = False
                    if hasattr(cluster, 'kubeconfig') and cluster.kubeconfig:
                        api_server_status = check_api_server_status(cluster.kubeconfig)
                # 检查节点状态
                node_query = {"cluster_id": cluster.id}
                nodes = NodeSQL.list_node_direct(node_query)
                
                # 检查实例状态
                instance_query = {"cluster_id": cluster.id}
                instances = InstanceSQL.list_instance_direct(instance_query)
                
                # 计算节点和实例状态
                node_statuses = [node.status for node in nodes if node]
                instance_statuses = [instance.status for instance in instances if instance]
                
                
                
                # 确定集群的新状态
                new_status = determine_cluster_status(node_statuses, instance_statuses, cluster.status)
                
                # 如果状态发生变化，更新集群状态
                if new_status != cluster.status:
                    LOG.info(f"Updating cluster {cluster.id} status from {cluster.status} to {new_status}")
                    cluster.status = new_status
                    ClusterSQL.update_cluster(cluster)
                    
                    # 这里可以添加通知或其他后续处理逻辑
                    
            except Exception as e:
                LOG.error(f"Error checking status for cluster {cluster.id}: {str(e)}")
                
    except Exception as e:
        LOG.error(f"Error in check_k8s_cluster_status: {str(e)}")
        
def check_api_server_status(kubeconfig_content):
    """
    通过kubeconfig检查Kubernetes API服务器状态
    
    :param kubeconfig_content: kubeconfig文件内容
    :return: True表示API服务器正常运行，False表示无法连接或异常
    """
    if not kubeconfig_content:
        return False
        
    try:
        # 创建临时kubeconfig文件
        with tempfile.NamedTemporaryFile(delete=False) as temp:
            temp_path = temp.name
            temp.write(kubeconfig_content.encode())
        
        # 加载kubeconfig并初始化客户端
        config.load_kube_config(config_file=temp_path)
        v1 = client.CoreV1Api()
        
        # 尝试获取节点列表以测试连接
        v1.list_node(_request_timeout=10)
        
        # 清理临时文件
        os.unlink(temp_path)
        return True
    except ApiException as e:
        LOG.error(f"API服务器连接错误: {e}")
        return False
    except Exception as e:
        LOG.error(f"检查API服务器时发生错误: {e}")
        return False
    
def determine_cluster_status(node_statuses, instance_statuses, current_status):
    """
    根据节点和实例的状态确定集群的状态
    
    参数:
    node_statuses (list): 节点状态列表
    instance_statuses (list): 实例状态列表
    current_status (str): 当前集群状态
    
    返回:
    str: 确定的集群状态
    """
    # 如果没有节点或实例，保持当前状态
    if not node_statuses and not instance_statuses:
        return current_status
        
    # 如果有任何失败状态
    if 'error' in node_statuses or 'error' in instance_statuses or 'failed' in node_statuses or 'failed' in instance_statuses:
        return 'error'
        
    # 如果全部都是运行状态
    if all(status == 'running' for status in node_statuses) and all(status == 'running' for status in instance_statuses):
        return 'running'
        
    # 如果有创建中的状态
    if 'creating' in node_statuses or 'creating' in instance_statuses:
        return 'creating'
        
    # 如果有删除中的状态
    if 'deleting' in node_statuses or 'deleting' in instance_statuses:
        return 'deleting'
    
    # 默认保持当前状态
    return current_status
