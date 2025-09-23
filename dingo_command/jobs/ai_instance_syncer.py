import json

from apscheduler.schedulers.background import BackgroundScheduler

from dingo_command.common.Enum.AIInstanceEnumUtils import K8sStatus, AiInstanceStatus
from dingo_command.common.k8s_common_operate import K8sCommonOperate
from dingo_command.db.models.ai_instance.sql import AiInstanceSQL
from dingo_command.services.redis_connection import RedisLock, redis_connection
from dingo_command.utils.constant import CCI_NAMESPACE_PREFIX,  DEV_TOOL_JUPYTER, SAVE_TO_IMAGE_CCI_PREFIX
from dingo_command.utils.k8s_client import get_k8s_core_client, get_k8s_app_client
from dingo_command.services.ai_instance import AiInstanceService, harbor_service
from dingo_command.utils import datetime as datatime_util
from datetime import datetime

ai_instance_scheduler = BackgroundScheduler()
ai_instance_service = AiInstanceService()
k8s_common_operate = K8sCommonOperate()


def auto_actions_tick():
    now = datetime.now()
    try:
        # 自动关机
        to_stop = AiInstanceSQL.list_instances_to_auto_stop(now)
        for inst in to_stop:
            try:
                ai_instance_service.stop_ai_instance_by_id(inst.id)
            except Exception as e:
                print(f"auto stop failed for {inst.id}: {e}")
        # 自动删除
        to_delete = AiInstanceSQL.list_instances_to_auto_delete(now)
        for inst in to_delete:
            try:
                ai_instance_service.delete_ai_instance_by_id(inst.id)
            except Exception as e:
                print(f"auto delete failed for {inst.id}: {e}")
    except Exception as e:
        print(f"auto_actions_tick error: {e}")

# 将任务注册到 scheduler（与 fetch_ai_instance_info 同步周期一样或独立间隔）
def start():
    ai_instance_scheduler.add_job(fetch_ai_instance_info, 'interval', seconds=300, next_run_time=datetime.now(), misfire_grace_time=150,coalesce=True, max_instances=1)
    # ai_instance_scheduler.add_job(auto_actions_tick, 'interval', seconds=60*30, next_run_time=datetime.now())
    ai_instance_scheduler.start()


def fetch_ai_instance_info():
    with RedisLock(redis_connection.redis_connection, "dingo_command_ai_instance_lock", expire_time=120) as lock:
        if lock:
            start_time = datatime_util.get_now_time()
            print(f"同步容器实例开始时间: {start_time}")
            try:
                # 查询所有容器实例
                k8s_kubeconfig_configs_db = AiInstanceSQL.list_k8s_configs()
                if not k8s_kubeconfig_configs_db:
                    print("ai k8s kubeconfig configs is temp")
                    return

                for k8s_kubeconfig_db in k8s_kubeconfig_configs_db:
                    if not k8s_kubeconfig_db.k8s_id:
                        print(f"k8s cluster id empty")
                        continue

                    print(f"处理K8s集群: ID={k8s_kubeconfig_db.k8s_id}, Type={k8s_kubeconfig_db.k8s_type}")
                    try:
                        # 获取client
                        core_k8s_client = get_k8s_core_client(k8s_kubeconfig_db.k8s_id)
                        app_k8s_client = get_k8s_app_client(k8s_kubeconfig_db.k8s_id)
                        networking_k8s_client = get_k8s_app_client(k8s_kubeconfig_db.k8s_id)
                    except Exception as e:
                        print(f"获取k8s[{k8s_kubeconfig_db.k8s_id}] client失败: {e}")
                        continue

                    # 同步处理单个K8s集群
                    sync_single_k8s_cluster(
                        k8s_id=k8s_kubeconfig_db.k8s_id,
                        core_client=core_k8s_client,
                        apps_client=app_k8s_client,
                        networking_client=networking_k8s_client
                    )
            except Exception as e:
                print(f"同步容器实例失败: {e}")
            finally:
                end_time = datatime_util.get_now_time()
                print(f"同步容器实例结束时间: {datatime_util.get_now_time()}, 耗时：{(end_time - start_time).total_seconds()}秒")
        else:
            print("get dingo_command_ai_instance_lock redis lock failed")


def sync_single_k8s_cluster(k8s_id: str, core_client, apps_client, networking_client):
    """同步单个K8s集群中的StatefulSet资源"""
    try:
        # 1. 获取数据库中的记录
        db_instances = AiInstanceSQL.list_ai_instance_info_by_k8s_id(k8s_id)
        if not db_instances:
            return

        # 2. 按namespace分组处理
        namespace_instance_map = {}
        for instance in db_instances:
            namespace = CCI_NAMESPACE_PREFIX + instance.instance_tenant_id
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
                    apps_client=apps_client,
                    networking_client=networking_client
                )
            except Exception as e:
                print(f"处理namespace[{namespace}]失败: {str(e)}")

    except Exception as e:
        print(f"同步K8s集群[{k8s_id}]资源失败: {str(e)}")


def process_namespace_resources(namespace: str, instances: list, core_client, apps_client, networking_client):
    """处理单个namespace下的资源"""
    print(f"开始处理namespace: {namespace}")

    # 1. 获取K8s中的资源
    sts_list = k8s_common_operate.list_sts_by_label(
        apps_client,
        namespace=namespace
    )
    pod_list = k8s_common_operate.list_pods_by_label_and_node(
        core_client,
        namespace=namespace
    )
    svc_list = k8s_common_operate.list_svc_by_label(
        core_client,
        namespace=namespace
    )

    # 2. 构建资源映射
    sts_map = {sts.metadata.name: sts for sts in sts_list}
    pod_map = {pod.metadata.name: pod for pod in pod_list}
    svc_map = {svc.metadata.name: svc for svc in svc_list}
    db_instance_map = {inst.instance_real_name: inst for inst in instances}
    print(f"---------sts_map:{sts_map.keys()}, pod_map:{pod_map.keys()}, db_instance_map:{db_instance_map.keys()}")

    # 3. 处理孤儿资源: K8s中存在但数据库不存在的资源
    handle_orphan_resources(
        sts_names=sts_map.keys(),
        svc_names = svc_map.keys(),
        db_instance_map=db_instance_map,
        namespace=namespace,
        core_client=core_client,
        apps_client=apps_client,
        networking_client=networking_client
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


def handle_orphan_resources(sts_names, svc_names, db_instance_map, namespace, core_client, apps_client, networking_client):
    db_instance_names = db_instance_map.keys()
    """处理K8s中存在但数据库不存在的资源"""
    orphans = set(sts_names) - set(db_instance_names)
    # cci的ns中多余的svc
    orphans_svcs = filter_svc_names(svc_names, db_instance_names)
    print(f"======handle_orphan_resources======orphans:{orphans}")
    for name in orphans:
        print(f"清理孤儿资源: {namespace}/{name}")
        cleanup_cci_resources(apps_client, core_client, networking_client, name, namespace)
        # 清理关机镜像
        ai_instance_db = AiInstanceSQL.get_ai_instance_info_by_real_name(name)

        try:
           # 删除镜像库中保存的关机镜像
           k8s_configs_db = AiInstanceSQL.get_k8s_configs_info_by_k8s_id(ai_instance_db.instance_k8s_id)
           harbor_address = k8s_configs_db.harbor_address
           image_name = SAVE_TO_IMAGE_CCI_PREFIX + ai_instance_db.id
           project_name = ai_instance_service.extract_project_and_image_name(harbor_address)
           print(f"ai instance [{ai_instance_db.id}] project_name:{project_name}, image_name:{image_name}")
           harbor_service.delete_custom_projects_images(project_name, image_name)
        except Exception as e:
             print(f"删除容器实例[{ai_instance_db.id}]的关机镜像失败: {e}")

        try:
            # 删除 jupyter configMap
            k8s_common_operate.delete_configmap(core_client, namespace, ai_instance_db.instance_real_name)
        except Exception as e:
            print(f"删除jupyter configMap资源[{namespace}/{ai_instance_db.instance_real_name}]失败: {str(e)}")

        # 删除metallb的默认端口
        AiInstanceSQL.delete_ai_instance_ports_info_by_instance_id(ai_instance_db.id)

    # 遍历删除多余的svc （出现过sts删除了，但是svc未删除的情况）
    for svc_name in orphans_svcs:
        try:
            # 删除
            k8s_common_operate.delete_service_by_name(
                core_client,
                service_name=svc_name,
                namespace=namespace
            )
        except Exception as e:
            print(f"删除 default svc资源[{namespace}/{svc_name}]失败: {str(e)}")


def filter_svc_names(svc_names, db_instance_names):
    """
    过滤掉以 db_instance_names 开头的服务名称，并去重

    :param svc_names: 原始服务名称列表（可能包含重复项）
    :param db_instance_names: 需要排除的数据库实例名前缀列表
    :return: 去重后的过滤结果集合
    """
    # 将输入列表转为集合去重
    svc_set = set(svc_names)

    # 生成需要排除的数据库服务名前缀集合（统一小写处理）
    db_prefixes = {name.lower() for name in db_instance_names}

    # 过滤条件：服务名不以任何 db_prefixes 中的前缀开头（不区分大小写）
    filtered_svcs = {
        svc for svc in svc_set
        if not any(svc.lower().startswith(prefix) for prefix in db_prefixes)
    }

    return filtered_svcs

def cleanup_cci_resources(apps_client, core_client, networking_client, name, namespace):
    try:
        # 删除StatefulSet
        print(f"删除底层k8s的sts资源: namespace = {namespace}, name = {name}")
        k8s_common_operate.delete_sts_by_name(
            apps_client,
            real_sts_name=name,
            namespace=namespace
        )
    except Exception as e:
        print(f"删除sts资源[{namespace}/{name}]失败: {str(e)}")

    try:
        # 删除default Service
        k8s_common_operate.delete_service_by_name(
            core_client,
            service_name=name,
            namespace=namespace
        )
    except Exception as e:
        print(f"删除 default svc资源[{namespace}/{name}]失败: {str(e)}")

    try:
        # 删除 jupyter Service
        k8s_common_operate.delete_service_by_name(
            core_client,
            service_name=name + "-" + DEV_TOOL_JUPYTER,
            namespace=namespace
        )
    except Exception as e:
        print(f"删除 jupyter svc资源[{namespace}/{name}]失败: {str(e)}")

    try:
        # 删除 ingress rule
        k8s_common_operate.delete_namespaced_ingress(
            networking_client,
            ingress_name=name,
            namespace=namespace
        )
    except Exception as e:
        print(f"删除ingress资源[{namespace}/{name}]失败: {str(e)}")


def handle_missing_resources(sts_names, db_instances):
    """处理数据库中存在但K8s中不存在的记录"""
    sts_name_set = set(sts_names)
    for instance in db_instances:
        if instance.instance_real_name not in sts_name_set:
            print(f"删除数据库中不存在的实例记录: {instance.instance_real_name}")
            try:
                print(f"删除db的instance资源: id = {instance.id}, name = {instance.instance_name}, real_name = {instance.instance_real_name}")
                # 清理实例
                AiInstanceSQL.delete_ai_instance_info_by_id(instance.id)
                # 清理端口数据
                AiInstanceSQL.delete_ai_instance_ports_info_by_instance_id(instance.id)
            except Exception as e:
                print(f"删除数据库记录失败[{instance.id}]: {str(e)}")


def sync_instance_info(sts_map, pod_map, db_instance_map):
    """同步实例状态、image、env等信息"""
    for real_name, instance_db in db_instance_map.items():
        if real_name not in sts_map:
            continue

        sts = sts_map[real_name]
        pod = pod_map.get(f"{real_name}-0")  # StatefulSet Pod命名规则

        # 处理副本数为0的情况 关机状态
        if sts and sts.spec.replicas == 0:
            print(f"Sts[{real_name}]副本数为0，检查Pod[{real_name}-0]是否存在")
            # 如果副本数为0，但Pod不存在，说明是关机状态，更新状态为STOPPED
            if not pod:
                print(f"Not Found Pod[{real_name}-0], Sts[{real_name}]副本数为0，更新状态为STOPPED")
                ai_instance_db = AiInstanceSQL.get_ai_instance_info_by_real_name(real_name)
                if ai_instance_db:
                    if (ai_instance_db.instance_status == AiInstanceStatus.READY.name
                            or ai_instance_db.instance_status == AiInstanceStatus.RUNNING.name
                            or ai_instance_db.instance_status == AiInstanceStatus.ERROR.name):
                        print(
                            f"Not Found Pod[{real_name}-0], ai instance {ai_instance_db.id} change instance_status:{ai_instance_db.instance_status} to error")
                        ai_instance_db.instance_status = AiInstanceStatus.ERROR.name
                        ai_instance_db.instance_real_status = K8sStatus.ERROR.value
                        ai_instance_db.error_msg = "k8s not exist this pod"
                        AiInstanceSQL.update_ai_instance_info(ai_instance_db)
                        ai_instance_service.set_k8s_sts_replica_by_instance_id(instance_db.id, 0)
                    else:
                        print(
                            f"Not Found Pod[{real_name}-0], ai instance {ai_instance_db.id} change instance_status:{ai_instance_db.instance_status} to stopped")
                        ai_instance_db.instance_status = AiInstanceStatus.STOPPED.name
                        ai_instance_db.instance_real_status = None
                        AiInstanceSQL.update_ai_instance_info(ai_instance_db)
            else:
                # 关机过程中，Pod还存在
                print(f"Sts[{real_name}]副本数为0，但Pod[{real_name}-0]存在，关机过程中，不更新状态")
            continue

        print(f"Sts[{real_name}]副本数不为0，进行别的状态处理")
        # 确定实例状态
        k8s_status, error_msg = ai_instance_service.get_pod_final_status(pod)
        # k8s_image = extract_image_info(sts)
        # 环境变量、错误信息等
        pod_details = extract_pod_details(pod)
        instance_status = AiInstanceService.map_k8s_to_db_status(k8s_status, instance_db.instance_status)
        print(f"ai instance [{real_name}] k8s_status: {k8s_status}, instance_status: {instance_status}, error_msg: {error_msg}")

        # 更新数据库记录
        try:
            # 准备更新数据
            update_data = {
                'instance_real_status': k8s_status,
                'instance_status': instance_status,
                # 'instance_image': k8s_image,
                'instance_node_name': pod.spec.node_name
            }

            if pod_details:
                update_data['instance_envs'] = pod_details.get('instance_envs')
                update_data['error_msg'] = pod_details.get('error_msg')

            # 更新数据库
            AiInstanceSQL.update_specific_fields_instance(instance_db, **update_data)
            if instance_status.upper() == "ERROR":
                print(f"update ai instance [{real_name}]: {update_data['instance_status']}")
                # 修改副本数
                ai_instance_service.set_k8s_sts_replica_by_instance_id(instance_db.id, 0)
        except Exception as e:
            print(f"update ai instance failed[{real_name}]: {str(e)}")

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
