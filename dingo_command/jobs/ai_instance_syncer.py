import json

from apscheduler.schedulers.background import BackgroundScheduler

from dingo_command.common.k8s_common_operate import K8sCommonOperate
from dingo_command.db.models.ai_instance.sql import AiInstanceSQL
from dingo_command.utils.constant import NAMESPACE_PREFIX
from dingo_command.utils.k8s_client import get_k8s_core_client, get_k8s_app_client
from dingo_command.services.ai_instance import AiInstanceService
from dingo_command.utils import datetime as datatime_util
from datetime import datetime
from oslo_log import log

ai_instance_scheduler = BackgroundScheduler()
ai_instance_service = AiInstanceService()
k8s_common_operate = K8sCommonOperate()

LOG = log.getLogger(__name__)

def auto_actions_tick():
    now = datetime.now()
    try:
        # 自动关机
        to_stop = AiInstanceSQL.list_instances_to_auto_stop(now)
        for inst in to_stop:
            try:
                ai_instance_service.close_ai_instance_by_id(inst.id)
            except Exception as e:
                LOG.error(f"auto stop failed for {inst.id}: {e}")
        # 自动删除
        to_delete = AiInstanceSQL.list_instances_to_auto_delete(now)
        for inst in to_delete:
            try:
                ai_instance_service.delete_ai_instance_by_id(inst.id)
            except Exception as e:
                LOG.error(f"auto delete failed for {inst.id}: {e}")
    except Exception as e:
        LOG.error(f"auto_actions_tick error: {e}")

# 将任务注册到 scheduler（与 fetch_ai_instance_info 同步周期一样或独立间隔）
def start():
    ai_instance_scheduler.add_job(fetch_ai_instance_info, 'interval', seconds=60*10, next_run_time=datetime.now())
    # ai_instance_scheduler.add_job(auto_actions_tick, 'interval', seconds=60*30, next_run_time=datetime.now())
    ai_instance_scheduler.start()


def fetch_ai_instance_info():
    start_time = datatime_util.get_now_time()
    print(f"同步容器实例开始时间: {start_time}")
    try:
        # 查询所有容器实例
        k8s_kubeconfig_configs_db = AiInstanceSQL.list_k8s_kubeconfig_configs()
        if not k8s_kubeconfig_configs_db:
            LOG.info("ai k8s kubeconfig configs is temp")
            return

        for k8s_kubeconfig_db in k8s_kubeconfig_configs_db:
            if not k8s_kubeconfig_db.k8s_id:
                print(f"k8s 集群[{k8s_kubeconfig_db.k8s_name}], k8s type:{k8s_kubeconfig_db.k8s_type} id empty")
                continue

            print(f"处理K8s集群: ID={k8s_kubeconfig_db.k8s_id}, Name={k8s_kubeconfig_db.k8s_name}, Type={k8s_kubeconfig_db.k8s_type}")
            try:
                # 获取client
                core_k8s_client = get_k8s_core_client(k8s_kubeconfig_db.k8s_id)
                app_k8s_client = get_k8s_app_client(k8s_kubeconfig_db.k8s_id)
            except Exception as e:
                LOG.error(f"获取k8s[{k8s_kubeconfig_db.k8s_id}_{k8s_kubeconfig_configs_db.k8s_name}] client失败: {e}")
                continue

            # 同步处理单个K8s集群
            sync_single_k8s_cluster(
                k8s_id=k8s_kubeconfig_db.k8s_id,
                core_client=core_k8s_client,
                apps_client=app_k8s_client
            )
    except Exception as e:
        LOG.error(f"同步容器实例失败: {e}")
    finally:
        end_time = datatime_util.get_now_time()
        LOG.error(f"同步容器实例结束时间: {datatime_util.get_now_time()}, 耗时：{(end_time - start_time).total_seconds()}秒")


def sync_single_k8s_cluster(k8s_id: str, core_client, apps_client):
    """同步单个K8s集群中的StatefulSet资源"""
    try:
        # 1. 获取数据库中的记录
        db_instances = AiInstanceSQL.list_ai_instance_info_by_k8s_id(k8s_id)
        if not db_instances:
            return

        # 2. 按namespace分组处理
        namespace_instance_map = {}
        for instance in db_instances:
            namespace = NAMESPACE_PREFIX + instance.instance_root_account_id
            if namespace not in namespace_instance_map:
                namespace_instance_map[namespace] = []
            namespace_instance_map[namespace].append(instance)

        # 3. 逐个namespace处理
        for namespace, instances in namespace_instance_map.items():
            try:
                process_namespace_resources(
                    namespace=namespace,
                    instances=instances,
                    core_client=core_client,
                    apps_client=apps_client
                )
            except Exception as e:
                LOG.error(f"处理namespace[{namespace}]失败: {str(e)}", exc_info=True)

    except Exception as e:
        LOG.error(f"同步K8s集群[{k8s_id}]资源失败: {str(e)}", exc_info=True)


def process_namespace_resources(namespace: str, instances: list, core_client, apps_client):
    """处理单个namespace下的资源"""
    LOG.info(f"开始处理namespace: {namespace}")

    # 1. 获取K8s中的资源
    sts_list = k8s_common_operate.list_sts_by_label(
        apps_client,
        namespace=namespace,
        label_selector="resource-type=ai-instance"
    )
    pod_list = k8s_common_operate.list_pods_by_label_and_node(
        core_client,
        namespace=namespace,
        label_selector="resource-type=ai-instance"
    )

    # 2. 构建资源映射
    sts_map = {sts.metadata.name: sts for sts in sts_list}
    pod_map = {pod.metadata.name: pod for pod in pod_list}
    db_instance_map = {inst.instance_real_name: inst for inst in instances}
    LOG.info(f"---------sts_map:{sts_map.keys()}, pod_map:{pod_map.keys()}, db_instance_map:{db_instance_map.keys()}")

    # 3. 处理孤儿资源: K8s中存在但数据库不存在的资源
    handle_orphan_resources(
        sts_names=sts_map.keys(),
        db_instance_names=db_instance_map.keys(),
        namespace=namespace,
        core_client=core_client,
        apps_client=apps_client
    )

    # 4. 处理缺失资源: 数据库中存在但K8s中不存在的记录
    handle_missing_resources(
        sts_names=sts_map.keys(),
        db_instances=instances
    )

    # 5. 更新状态同步的记录
    sync_instance_info(
        sts_map=sts_map,
        pod_map=pod_map,
        db_instance_map=db_instance_map
    )


def handle_orphan_resources(sts_names, db_instance_names, namespace, core_client, apps_client):
    """处理K8s中存在但数据库不存在的资源"""
    orphans = set(sts_names) - set(db_instance_names)
    LOG.info(f"======handle_orphan_resources======orphans:{orphans}")
    for name in orphans:
        LOG.info(f"清理孤儿资源: {namespace}/{name}")
        try:
            # 删除StatefulSet
            k8s_common_operate.delete_sts_by_name(
                apps_client,
                real_sts_name=name,
                namespace=namespace
            )
        except Exception as e:
            LOG.error(f"删除sts资源[{namespace}/{name}]失败: {str(e)}")

        try:
            # 删除Service
            k8s_common_operate.delete_service_by_name(
                core_client,
                service_name=name,
                namespace=namespace
            )
        except Exception as e:
            LOG.error(f"删除svc资源[{namespace}/{name}]失败: {str(e)}")


def handle_missing_resources(sts_names, db_instances):
    """处理数据库中存在但K8s中不存在的记录"""
    sts_name_set = set(sts_names)
    for instance in db_instances:
        if instance.instance_real_name not in sts_name_set:
            LOG.info(f"删除数据库中不存在的实例记录: {instance.instance_real_name}")
            try:
                AiInstanceSQL.delete_ai_instance_info_by_id(instance.id)
            except Exception as e:
                LOG.error(f"删除数据库记录失败[{instance.id}]: {str(e)}")


def sync_instance_info(sts_map, pod_map, db_instance_map):
    """同步实例状态、image、env等信息"""
    for real_name, instance_db in db_instance_map.items():
        if real_name not in sts_map:
            continue

        sts = sts_map[real_name]
        pod = pod_map.get(f"{real_name}-0")  # StatefulSet Pod命名规则

        if not pod:
            LOG.warning(f"Not Found Pod[{real_name}-0], skip sync")
            continue

        # 确定实例状态
        k8s_status = determine_instance_real_status(sts, pod)
        # 实例使用镜像
        k8s_image = extract_image_info(sts)
        # 环境变量、错误信息等
        pod_details = extract_pod_details(pod)

        # 更新数据库记录
        try:
            # 准备更新数据
            update_data = {
                'instance_real_status': k8s_status,
                'instance_status': AiInstanceService.map_k8s_to_db_status(k8s_status, instance_db.instance_status),
                'instance_image': k8s_image,
                'instance_node_name': pod.spec.node_name
            }

            if pod_details:
                update_data['instance_envs'] = pod_details.get('instance_envs')
                update_data['error_msg'] = pod_details.get('error_msg')

            # 更新数据库
            AiInstanceSQL.update_specific_fields_instance(instance_db, **update_data)
            LOG.info(f"更新实例[{real_name}]信息: {update_data['instance_status']}")
        except Exception as e:
            LOG.error(f"更新实例状态失败[{real_name}]: {str(e)}")

def extract_pod_details(pod):
    """从Pod中提取详细信息"""
    if not pod:
        return None

    details = {}

    # 1. 提取环境变量
    env_vars = {}
    for container in pod.spec.containers:
        if container.env:
            for env in container.env:
                env_vars[env.name] = env.value if env.value else None

    if env_vars:
        details['instance_envs'] = json.dumps(env_vars)  # 序列化为JSON字符串

    # 2. 提取错误信息（从status.conditions）
    error_msgs = []
    for condition in pod.status.conditions or []:
        if condition.status != 'True' and condition.message:
            error_msgs.append(f"{condition.type}: {condition.message}")

    if error_msgs:
        details['error_msg'] = '; '.join(error_msgs)

    return details if details else None


def extract_image_info(sts):
    """从StatefulSet中提取镜像信息"""
    if not sts or not sts.spec.template.spec.containers:
        return None

    # 获取主容器镜像（通常第一个容器是主容器）
    primary_container = sts.spec.template.spec.containers[0]
    return primary_container.image

def determine_instance_real_status(sts, pod):
    """根据K8s资源确定实例状态"""
    if not pod:
        return "STOPPED"

    if sts.status.replicas == 0:
        return "STOPPED"

    return pod.status.phase
