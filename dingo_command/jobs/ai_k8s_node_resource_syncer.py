import json
import uuid

from apscheduler.schedulers.background import BackgroundScheduler

from dingo_command.common.Enum.AIInstanceEnumUtils import AiInstanceStatus
from dingo_command.common.k8s_common_operate import K8sCommonOperate
from dingo_command.db.models.ai_instance.sql import AiInstanceSQL
from dingo_command.utils.k8s_client import get_k8s_core_client
from dingo_command.db.models.ai_instance.models import AiK8sNodeResourceInfo
from dingo_command.services.ai_instance import AiInstanceService
from datetime import datetime
from oslo_log import log

node_resource_scheduler = BackgroundScheduler()
ai_instance_service = AiInstanceService()
k8s_common_operate = K8sCommonOperate()

LOG = log.getLogger(__name__)

def start():
    node_resource_scheduler.add_job(fetch_ai_k8s_node_resource, 'interval', seconds=60, next_run_time=datetime.now(),  misfire_grace_time=300,coalesce=True, max_instances=1)
    node_resource_scheduler.start()

def fetch_ai_k8s_node_resource():
    start_time = datetime.now()
    print(f"sync k8s node resource start time: {start_time}")
    try:
        # 查询所有k8s集群配置
        k8s_configs = AiInstanceSQL.list_k8s_kubeconfig_configs()
        if not k8s_configs:
            LOG.info("ai k8s kubeconfig configs is temp")
            return

        for k8s_kubeconfig_db in k8s_configs:
            if not k8s_kubeconfig_db.k8s_id:
                print(f"k8s cluster [{k8s_kubeconfig_db.k8s_name}], k8s type:{k8s_kubeconfig_db.k8s_type} id empty")
                continue

            print(f"handle K8s cluster: ID={k8s_kubeconfig_db.k8s_id}, Name={k8s_kubeconfig_db.k8s_name}, Type={k8s_kubeconfig_db.k8s_type}")
            try:
                # 获取client
                core_client  = get_k8s_core_client(k8s_kubeconfig_db.k8s_id)
                k8s_nodes = k8s_common_operate.list_node(core_client).items
                if not k8s_nodes:
                    LOG.info(f"k8s cluster {k8s_kubeconfig_db.k8s_id} no available node, clear old data")
                    AiInstanceSQL.delete_k8s_node_resource_by_k8s_id(k8s_kubeconfig_db.k8s_id)
                    continue

                k8s_node_map = {node.metadata.name: node for node in k8s_nodes}

                # 获取数据库中记录的节点
                db_node_map = {node.node_name: node for node in
                            AiInstanceSQL.get_k8s_node_resource_by_k8s_id(k8s_kubeconfig_db.k8s_id)}

                # 处理节点删除场景
                handle_removed_nodes(k8s_kubeconfig_db.k8s_id, set(db_node_map.keys()) - set(k8s_node_map.keys()))

                for k8s_node in k8s_nodes:
                    # 同步单个node资源
                    sync_node_and_pod_resources(
                        k8s_kubeconfig_db.k8s_id,
                        k8s_node,
                        core_client
                    )

            except Exception as e:
                LOG.error(f"get k8s[{k8s_kubeconfig_db.k8s_id}_{k8s_kubeconfig_db.k8s_name}] client fail: {e}")
                continue

    except Exception as e:
        LOG.error(f"sync k8s node resource fail: {e}")
    finally:
        end_time = datetime.now()
        LOG.error(f"sync k8s node resource end time: {end_time}, time-consuming：{(end_time - start_time).total_seconds()}s")

def handle_removed_nodes(k8s_id, removed_node_names):
    """处理被删除的节点"""
    for node_name in removed_node_names:
        try:
            # 检查节点上是否还有关联的AI实例
            instances = AiInstanceSQL.get_instances_by_k8s_and_node(k8s_id, node_name)
            if instances:
                LOG.warning(f"node [{node_name}] deleted, {len(instances)}AI instances remain associated, flagged as abnormal status.")
                for instance in instances:
                    update_data = {
                        'instance_real_status': None,
                        'instance_status': AiInstanceStatus.ERROR,
                        'error_msg': f"Associated K8s node [{node_name}] deleted"

                    }
                    # 更新POD状态
                    AiInstanceSQL.update_specific_fields_instance(
                        instance,
                        **update_data
                    )

            # 删除节点资源记录
            AiInstanceSQL.delete_k8s_node_resource(k8s_id, node_name)
            LOG.info(f"Cleared resource records of deleted node [{node_name}]")

        except Exception as e:
            LOG.error(f"hande delete node [{node_name}] fail: {str(e)}", exc_info=True)

def sync_node_and_pod_resources(k8s_id, k8s_node, core_client):
    """
    同步单个节点的资源和POD使用量
    """
    if not sync_node_resource_total(k8s_id, k8s_node, core_client):
        LOG.error(f"k8s [{k8s_id}] node  {k8s_node.metadata.name} resource total sync fail")
        return

    if not sync_pod_resource_usage(k8s_id, k8s_node.metadata.name, core_client):
        LOG.error(f"k8s [{k8s_id}] node {k8s_node.metadata.name} POD resource used sync fail")
        return

    LOG.info(f"k8s [{k8s_id}] node {k8s_node.metadata.name} resource sync end")


def sync_node_resource_total(k8s_id, k8s_node, core_client):
    """
    同步节点资源总量到数据库
    :param k8s_id: K8s集群ID
    :param k8s_node: k8s node数据
    :param core_client: K8s客户端
    :return: 是否同步成功
    """
    try:
        allocatable = k8s_node.status.allocatable
        if not allocatable:
            LOG.warning(f"Node {k8s_node.metadata.name} has no allocatable resources")
            return False

        # 构建资源字典
        node_resource  = {
            'node_name': k8s_node.metadata.name,
            'standard_resources': {
                'cpu': ai_instance_service.convert_cpu_to_core(allocatable.get('cpu', '0')),
                'memory': ai_instance_service.convert_memory_to_gb(allocatable.get('memory', '0Ki')),
                'ephemeral_storage': ai_instance_service.convert_storage_to_gb(allocatable.get('ephemeral-storage', '0'))
            },
            'extended_resources': {}
        }

        # 处理扩展资源（主要关注GPU）
        for key in dir(allocatable):
            if key.startswith('_') or key in ['cpu', 'memory', 'ephemeral-storage', 'pods', 'hugepages-1gi', 'hugepages-2mi']:
                continue

            value = allocatable.get(key)
            if 'gpu' in key.lower():
                node_resource['extended_resources'][key] = value

            # 保存或更新到数据库
            process_node_total_resource(k8s_id, node_resource, core_client)
            return True
    except Exception as e:
        LOG.error(f"sync node {k8s_node.metadata.name} resource total failed: {str(e)}")
        return False


def sync_pod_resource_usage(k8s_id, node_name, core_client):
    """
    同步POD资源使用量到数据库
    :param k8s_id: K8s集群ID
    :param node_name: 节点名称
    :param core_client: K8s客户端
    :return: 是否同步成功
    """
    try:
        # 获取节点上所有POD
        pods = k8s_common_operate.list_pods_by_label_and_node(core_v1=core_client, node_name=node_name)

        # 初始化资源使用总量
        total_usage = {
            'cpu': 0,
            'memory': 0,
            'ephemeral-storage': 0,
            'gpu': 0,
            'gpu_pod_count': 0
        }
        gpu_model = None

        # 汇总所有POD的资源使用量
        for pod in pods:
            for container in pod.spec.containers:
                # CPU
                if container.resources.limits and 'cpu' in container.resources.limits:
                    total_usage['cpu'] += float(ai_instance_service.convert_cpu_to_core(
                        container.resources.limits['cpu'])
                    )

                # 内存
                if container.resources.limits and 'memory' in container.resources.limits:
                    total_usage['memory'] += float(ai_instance_service.convert_memory_to_gb(
                        container.resources.limits['memory'])
                    )

                # GPU
                if container.resources.limits:
                    for key, value in container.resources.limits.items():
                        if 'gpu' in key.lower():
                            total_usage['gpu'] += int(value)
                            gpu_model = key
                            total_usage['gpu_pod_count'] += total_usage['gpu_pod_count']



            # 存储
            for volume in pod.spec.volumes:
                if volume.name == "system-disk" and hasattr(volume, "empty_dir"):
                    empty_dir = volume.empty_dir
                    if hasattr(empty_dir, "size_limit"):
                        total_usage['ephemeral-storage'] += float(ai_instance_service.convert_storage_to_gb(empty_dir.size_limit))

        # 更新数据库中的已使用量
        node_resource_db = AiInstanceSQL.get_k8s_node_resource_by_k8s_id_and_node_name(k8s_id, node_name)
        if node_resource_db:
            node_resource_db.less_gpu_pod_count = len(pods) - total_usage['gpu_pod_count']
            node_resource_db.cpu_used = str(total_usage['cpu'])
            node_resource_db.memory_used = str(total_usage['memory'])
            node_resource_db.storage_used = str(total_usage['ephemeral-storage'])
            if gpu_model and gpu_model in node_resource_db.gpu_model:
                node_resource_db.gpu_used = str(total_usage['gpu'])

            AiInstanceSQL.update_k8s_node_resource(node_resource_db)
            return True

        LOG.error(f"Not found {k8s_id}/{node_name} resource data")
        return False

    except Exception as e:
        LOG.error(f"sync POD used resource failed: {str(e)}")
        return False

def process_node_total_resource(k8s_id, node_resource, core_client):
    """处理单个节点的资源信息"""
    node_name = node_resource['node_name']
    existing = AiInstanceSQL.get_k8s_node_resource_by_k8s_id_and_node_name(k8s_id, node_name)

    # 处理GPU资源
    gpu_model = None
    gpu_total = None
    ext_resources = node_resource.get('extended_resources', {})
    for gpu_key, gpu_count in ext_resources.items():
        gpu_model= gpu_key
        gpu_total= gpu_count
        break  # 只处理第一个GPU资源（通常一个节点只有一种GPU）

    # 创建或更新记录
    if existing:
        existing.cpu_total = node_resource['standard_resources']['cpu']
        existing.memory_total = node_resource['standard_resources']['memory']
        existing.storage_total = node_resource['standard_resources']['ephemeral_storage']
        existing.gpu_model = gpu_model
        existing.gpu_total = gpu_total
        LOG.info(f"Updating resource for node {node_name}")
        AiInstanceSQL.update_k8s_node_resource(existing)
    else:
        ai_k8s_node_resource_db = AiK8sNodeResourceInfo(
            k8s_id=k8s_id,
            node_name=node_name,
            cpu_total=node_resource['standard_resources']['cpu'],
            memory_total=node_resource['standard_resources']['memory'],
            storage_total=node_resource['standard_resources']['ephemeral_storage'],
            gpu_model=gpu_model,
            gpu_total=gpu_total
        )
        ai_k8s_node_resource_db.id = uuid.uuid4().hex
        LOG.info(f"Creating new resource for node {node_name}")
        AiInstanceSQL.save_k8s_node_resource(ai_k8s_node_resource_db)

def handle_node_migration(instance_db, old_node_name, new_node_name):
    """
    处理节点迁移的资源管理
    :return: 是否成功处理资源迁移
    """
    try:
        compute_resource_dict = json.loads(instance_db.instance_config)
        k8s_id = instance_db.instance_k8s_id

        # 1. 释放原节点资源
        if old_node_name:
            original_node_resource_db = AiInstanceSQL.get_k8s_node_resource_by_k8s_id_and_node_name(
                k8s_id, old_node_name
            )
            if original_node_resource_db:
                if update_node_resources(original_node_resource_db, compute_resource_dict, 'release'):
                    LOG.info(f"释放原节点[{k8s_id}_{old_node_name}]资源成功")
                else:
                    LOG.error(f"释放原节点[{k8s_id}_{old_node_name}]资源失败")
                    return False
            else:
                LOG.warning(f"未找到原节点[{k8s_id}_{old_node_name}]资源记录")

        # 2. 分配新节点资源
        if new_node_name:
            new_node_resource_db = AiInstanceSQL.get_k8s_node_resource_by_k8s_id_and_node_name(
                k8s_id, new_node_name
            )
            if new_node_resource_db:
                if update_node_resources(new_node_resource_db, compute_resource_dict, 'allocate'):
                    LOG.info(f"分配新节点[{k8s_id}_{new_node_name}]资源成功")
                    return True
                else:
                    LOG.error(f"分配新节点[{k8s_id}_{new_node_name}]资源失败")
                    return False
            else:
                LOG.error(f"未找到新节点[{k8s_id}_{new_node_name}]资源记录")
                return False

        return True

    except Exception as e:
        LOG.error(f"处理节点迁移失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def update_node_resources(node_resource_db, compute_resource_dict , operation='release'):
    """
    更新节点资源（分配或释放）
    :param node_resource_db: 节点资源数据库对象
    :param compute_resource_dict : 计算资源配置字典
    :param operation: 'allocate' 分配资源, 'release' 释放资源
    :return: 是否成功更新资源
    """
    try:
        operation_factor = 1 if operation == 'allocate' else -1
        print(f"============compute_resource_dict :{compute_resource_dict }")
        # 处理GPU资源（需要型号匹配）
        if ('gpu_model' in compute_resource_dict  and
                'gpu_count' in compute_resource_dict  and
                compute_resource_dict['gpu_model'] and
                node_resource_db.gpu_model and
                compute_resource_dict['gpu_model'] in node_resource_db.gpu_model):
            current_gpu = safe_float(node_resource_db.gpu_used or '0')
            resource_gpu = safe_float(compute_resource_dict['gpu_count'])
            node_resource_db.gpu_used = str(max(0, current_gpu + operation_factor * resource_gpu))

        # 处理CPU资源
        if 'compute_cpu' in compute_resource_dict :
            current_cpu = safe_float(node_resource_db.cpu_used or '0')
            resource_cpu = safe_float(compute_resource_dict['compute_cpu'])
            node_resource_db.cpu_used = str(max(0, current_cpu + operation_factor * resource_cpu))

        # 处理内存资源
        if 'compute_memory' in compute_resource_dict :
            current_memory = safe_float(node_resource_db.memory_used or '0')
            resource_memory = safe_float(compute_resource_dict['compute_memory'])
            node_resource_db.memory_used = str(max(0, current_memory + operation_factor * resource_memory))

        # 处理系统磁盘资源
        if 'system_disk_size' in compute_resource_dict :
            current_disk = safe_float(node_resource_db.storage_used or '0')
            resource_disk = safe_float(compute_resource_dict['system_disk_size'])
            node_resource_db.storage_used = str(max(0, current_disk + operation_factor * resource_disk))

        # 更新数据库
        AiInstanceSQL.update_k8s_node_resource(node_resource_db)
        return True

    except Exception as e:
        LOG.error(f"{operation}节点资源失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def safe_float(value, default=0.0):
    """安全转换为float类型"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default