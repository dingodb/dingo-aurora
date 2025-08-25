import copy
import uuid

from apscheduler.schedulers.background import BackgroundScheduler

from dingo_command.common.k8s_common_operate import K8sCommonOperate
from dingo_command.db.models.ai_instance.sql import AiInstanceSQL
from dingo_command.utils.k8s_client import get_k8s_core_client
from dingo_command.db.models.ai_instance.models import AiK8sNodeResourceInfo
from dingo_command.services.ai_instance import AiInstanceService
from datetime import datetime
from oslo_log import log

relation_scheduler = BackgroundScheduler()
ai_instance_service = AiInstanceService()
k8s_common_operate = K8sCommonOperate()

LOG = log.getLogger(__name__)

def start():
    relation_scheduler.add_job(fetch_ai_k8s_node_resource, 'interval', seconds=60*10, next_run_time=datetime.now())
    relation_scheduler.start()


def fetch_ai_k8s_node_resource():
    start_time = datetime.now()
    print(f"同步k8s node resource开始时间: {start_time}")
    try:
        # 查询所有k8s集群配置
        k8s_configs = AiInstanceSQL.list_k8s_kubeconfig_configs()
        if not k8s_configs:
            LOG.info("ai k8s kubeconfig configs is temp")
            return

        for k8s_kubeconfig_db in k8s_configs:
            if not k8s_kubeconfig_db.k8s_id:
                print(f"k8s 集群[{k8s_kubeconfig_db.k8s_name}], k8s type:{k8s_kubeconfig_db.k8s_type} id empty")
                continue

            print(f"处理K8s集群: ID={k8s_kubeconfig_db.k8s_id}, Name={k8s_kubeconfig_db.k8s_name}, Type={k8s_kubeconfig_db.k8s_type}")
            try:
                # 获取client
                core_k8s_client = get_k8s_core_client(k8s_kubeconfig_db.k8s_id)
            except Exception as e:
                LOG.error(f"获取k8s[{k8s_kubeconfig_db.k8s_id}_{k8s_configs.k8s_name}] client失败: {e}")
                continue

            k8s_nodes = k8s_common_operate.list_node(core_k8s_client).items
            if not k8s_nodes:
                LOG.error(f"k8s[{k8s_kubeconfig_db.k8s_id}_{k8s_configs.k8s_name}] node is empty, 删除其下数据")
                AiInstanceSQL.delete_k8s_node_resource_by_k8s_id(k8s_kubeconfig_db.k8s_id)
                continue

            # 处理节点资源
            process_node_resources(k8s_kubeconfig_db, k8s_nodes)

    except Exception as e:
        LOG.error(f"同步k8s node resource失败: {e}")
    finally:
        end_time = datetime.now()
        LOG.error(f"同步k8s node resource结束时间: {end_time}, 耗时：{(end_time - start_time).total_seconds()}秒")

def process_node_resources(k8s_kubeconfig_db, k8s_node):
    """处理节点资源信息"""
    node_resources = []

    # 1. 收集节点资源信息
    for node in k8s_node:
        node_name = node.metadata.name
        LOG.info(f"Processing node: {node_name}")

        allocatable = node.status.allocatable
        if not allocatable:
            LOG.warning(f"Node {node_name} has no allocatable resources")
            continue

        print(f"wwww----0-allocatable:{allocatable}")
        print(f"wwww----0-cpu:{allocatable.get('cpu', '0')}")
        # 构建资源字典
        single_node_resource = {
            'node_name': node_name,
            'standard_resources': {
                'cpu': allocatable.get('cpu', '0'),
                'memory': convert_memory_to_mb(allocatable.get('memory', '0Ki')),
                'ephemeral_storage': convert_storage_to_gb(allocatable.get('ephemeral_storage', '0'))
            },
            'extended_resources': {}
        }

        # 处理扩展资源（主要关注GPU）
        for key in dir(allocatable):
            print(f"wwww----0-----key:{key}")
            if key.startswith('_') or key in ['cpu', 'memory', 'ephemeral_storage', 'pods', 'hugepages_1gi', 'hugepages_2mi']:
                continue

            value = allocatable.get(key)
            if 'gpu' in key.lower():
                single_node_resource['extended_resources'][key] = value

        node_resources.append(single_node_resource)

    if not node_resources:
        LOG.error(f"No valid node resources found for cluster {k8s_kubeconfig_db.k8s_id}")
        return

    # 2. 保存或更新资源信息
    for resource in node_resources:
        process_single_node_resource(k8s_kubeconfig_db.k8s_id, resource)


def process_single_node_resource(k8s_id, resource):
    """处理单个节点的资源信息"""
    node_name = resource['node_name']
    existing = AiInstanceSQL.get_k8s_node_resource_by_k8s_id_and_node_name(k8s_id, node_name)

    # 准备基础数据
    ai_k8s_node_resource_db = AiK8sNodeResourceInfo(
        k8s_id=k8s_id,
        node_name=node_name,
        cpu_total=resource['standard_resources']['cpu'],
        memory_total=resource['standard_resources']['memory'],
        storage_total=resource['standard_resources']['ephemeral_storage']
    )

    # 处理GPU资源
    ext_resources = resource.get('extended_resources', {})
    print(f"=========ext_resources:{ext_resources}, items:{ext_resources.items()}")
    for gpu_key, gpu_count in ext_resources.items():
        ai_k8s_node_resource_db.gpu_model= gpu_key
        ai_k8s_node_resource_db.gpu_total= gpu_count
        break  # 只处理第一个GPU资源（通常一个节点只有一种GPU）

    # 创建或更新记录
    if existing:
        print(f"======existing:{existing}")
        # ai_k8s_node_resource_db_co = copy.deepcopy(ai_k8s_node_resource_db)
        ai_k8s_node_resource_db.id = existing.id
        LOG.info(f"Updating resource for node {node_name}:{ai_k8s_node_resource_db}")
        AiInstanceSQL.update_k8s_node_resource(ai_k8s_node_resource_db)
    else:
        ai_k8s_node_resource_db.id = uuid.uuid4().hex
        LOG.info(f"Creating new resource for node {node_name}:{ai_k8s_node_resource_db}")
        AiInstanceSQL.save_k8s_node_resource(ai_k8s_node_resource_db)

# 单位转换函数
def convert_memory_to_mb(memory_str):
    """将内存字符串转换为 MB"""
    if memory_str.endswith('Ki'):
        return int(memory_str[:-2]) // 1024
    elif memory_str.endswith('Mi'):
        return int(memory_str[:-2])
    elif memory_str.endswith('Gi'):
        return int(memory_str[:-2]) * 1024
    return int(memory_str) // (1024 * 1024)  # 默认假设为字节

def convert_storage_to_gb(storage_str):
    """将存储字符串转换为 GB"""
    if storage_str.endswith('Ki'):
        return int(storage_str[:-2]) // (1024 * 1024)
    return int(storage_str) // (1024 * 1024 * 1024)  # 默认假设为字节