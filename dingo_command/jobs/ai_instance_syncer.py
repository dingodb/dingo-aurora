import json

from apscheduler.schedulers.background import BackgroundScheduler

from dingo_command.common.Enum.AIInstanceEnumUtils import K8sStatus, AiInstanceStatus
from dingo_command.common.k8s_common_operate import K8sCommonOperate
from dingo_command.common.common import dingo_print
from dingo_command.db.models.ai_instance.sql import AiInstanceSQL
from dingo_command.services.redis_connection import RedisLock, redis_connection
from dingo_command.utils.constant import CCI_NAMESPACE_PREFIX,  DEV_TOOL_JUPYTER, SAVE_TO_IMAGE_CCI_PREFIX, CCI_SYNC_K8S_NODE_REDIS_KEY
from dingo_command.utils.k8s_client import get_k8s_core_client, get_k8s_app_client
from dingo_command.services.ai_instance import AiInstanceService, harbor_service
from dingo_command.utils import datetime as datatime_util
from datetime import datetime, timedelta

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
                dingo_print(f"auto stop failed for {inst.id}: {e}")
        # 自动删除
        to_delete = AiInstanceSQL.list_instances_to_auto_delete(now)
        for inst in to_delete:
            try:
                ai_instance_service.delete_ai_instance_by_id(inst.id)
            except Exception as e:
                dingo_print(f"auto delete failed for {inst.id}: {e}")
    except Exception as e:
        dingo_print(f"auto_actions_tick error: {e}")

# 将任务注册到 scheduler（与 fetch_ai_instance_info 同步周期一样或独立间隔）
def start():
    ai_instance_scheduler.add_job(fetch_ai_instance_info, 'interval', seconds=300, next_run_time=datetime.now(), misfire_grace_time=150, coalesce=True, max_instances=1)
    # ai_instance_scheduler.add_job(fetch_ai_instance_info_4operate, 'interval', seconds=5, next_run_time=datetime.now(), misfire_grace_time=150,coalesce=True, max_instances=1)
    # ai_instance_scheduler.add_job(auto_actions_tick, 'interval', seconds=60*30, next_run_time=datetime.now())
    ai_instance_scheduler.start()

def fetch_ai_instance_info_4operate():
    try:
        # 从redis查看最近10s内是否存在key
        operator_flag = redis_connection.get_redis_by_key(CCI_SYNC_K8S_NODE_REDIS_KEY)
        # 没有key 啥都不做
        if not operator_flag:
            return
        # 同步
        fetch_ai_instance_info()
    except Exception as e:
        dingo_print(e)

def fetch_ai_instance_info():
    fetch_start_time = datatime_util.get_now_time()
    dingo_print(f"fetch_ai_instance_info start: {fetch_start_time}")

    with RedisLock(redis_connection.redis_master_connection, "dingo_command_ai_instance_lock", expire_time=120) as lock:
        if lock:
            start_time = datatime_util.get_now_time()
            dingo_print(f"fetch_ai_instance_info start_with_lock: {datatime_util.get_now_time()}, fetch_start_time: {fetch_start_time}")

            try:
                # 查询所有容器实例
                k8s_kubeconfig_configs_db = AiInstanceSQL.list_k8s_configs()
                if not k8s_kubeconfig_configs_db:
                    dingo_print("ai k8s kubeconfig configs is temp, fetch_start_time: {fetch_start_time}")
                    return

                for k8s_kubeconfig_db in k8s_kubeconfig_configs_db:
                    if not k8s_kubeconfig_db.k8s_id:
                        dingo_print("k8s cluster id empty, fetch_start_time: {fetch_start_time}")
                        continue

                    dingo_print(f"doing k8s cluster {k8s_kubeconfig_db.k8s_id} ai instance info, fetch_start_time: {fetch_start_time}")
                    try:
                        # 获取client
                        core_k8s_client = get_k8s_core_client(k8s_kubeconfig_db.k8s_id)
                        app_k8s_client = get_k8s_app_client(k8s_kubeconfig_db.k8s_id)
                        networking_k8s_client = get_k8s_app_client(k8s_kubeconfig_db.k8s_id)
                    except Exception as e:
                        dingo_print(f"get k8s[{k8s_kubeconfig_db.k8s_id}] client failed: {e}, fetch_start_time: {fetch_start_time}")
                        continue

                    # 同步处理单个K8s集群
                    sync_single_k8s_cluster(
                        k8s_id=k8s_kubeconfig_db.k8s_id,
                        core_client=core_k8s_client,
                        apps_client=app_k8s_client,
                        networking_client=networking_k8s_client
                    )

                    dingo_print(f"done k8s cluster {k8s_kubeconfig_db.k8s_id} ai instance info, fetch_start_time: {fetch_start_time}")
                dingo_print(f"fetch_ai_instance_info all k8s cluster done, fetch_start_time: {fetch_start_time}")
            except Exception as e:
                dingo_print(f"sync ai instance info error: {e}")
            finally:
                end_time = datatime_util.get_now_time()
                dingo_print(f"sync ai instance info end: {datatime_util.get_now_time()}, used time: {(end_time - start_time).total_seconds()}s")
        else:
            dingo_print(f"{datatime_util.get_now_time()} get dingo_command_ai_instance_lock redis lock failed, fetch_start_time: {fetch_start_time}, another progress is running")
    
    dingo_print(f"fetch_ai_instance_info end: {datatime_util.get_now_time()}, fetch_start_time: {fetch_start_time}, used time: {(datatime_util.get_now_time() - fetch_start_time).total_seconds()}s")


def sync_single_k8s_cluster(k8s_id: str, core_client, apps_client, networking_client):
    """同步单个K8s集群中的StatefulSet资源"""
    try:
        # 1. 获取数据库中的记录
        db_instances = AiInstanceSQL.list_ai_instance_info_by_k8s_id(k8s_id)
        if not db_instances:
            return

        # 2. 按namespace分组处理
        tenant_id_list = [instance.instance_tenant_id for instance in db_instances if instance.instance_tenant_id]
        dingo_print(f"fetch_ai_instance_info k8s {k8s_id} need handle namespace size: {len(tenant_id_list)}")

        # 3. 逐个namespace处理
        for tenant_id in tenant_id_list:
            try:
                process_namespace_resources(
                    tenant_id=tenant_id,
                    core_client=core_client,
                    apps_client=apps_client,
                    networking_client=networking_client
                )
            except Exception as e:
                dingo_print(f"{datatime_util.get_now_time()} handle namespace {CCI_NAMESPACE_PREFIX+tenant_id} failed: {str(e)}")

    except Exception as e:
        dingo_print(f"{datatime_util.get_now_time()} sync K8s {k8s_id} resource failed: {str(e)}")


def process_namespace_resources(tenant_id: str, core_client, apps_client, networking_client):
    """处理单个namespace下的资源"""
    dingo_print(f"fetch_ai_instance_info start sync namespace {CCI_NAMESPACE_PREFIX + tenant_id} resource")
    namespace = CCI_NAMESPACE_PREFIX + tenant_id
    dingo_print(f"fetch_ai_instance_info {datatime_util.get_now_time()} start handle namespace: {namespace}")

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

    instances = AiInstanceSQL.get_ai_instance_info_by_tenant_id(tenant_id)
    db_instance_map = {inst.instance_real_name: inst for inst in instances}
    dingo_print(f"{datatime_util.get_now_time()} sts_map size: {len(sts_map)}, pod_map size: {len(pod_map)}, db_instance_map size: {len(db_instance_map)}")

    # 3. 处理孤儿资源: K8s中存在但数据库不存在的资源
    dingo_print(f"fetch_ai_instance_info {datatime_util.get_now_time()} start handle orphan resources in namespace: {namespace}")
    handle_orphan_resources(
        sts_names=sts_map.keys(),
        svc_names=svc_map.keys(),
        db_instance_map=db_instance_map,
        namespace=namespace,
        core_client=core_client,
        apps_client=apps_client,
        networking_client=networking_client
    )

    # 4. 处理缺失资源: 数据库中存在但K8s中不存在的记录
    dingo_print(f"fetch_ai_instance_info {datatime_util.get_now_time()} start handle missing resources in namespace: {namespace}")
    handle_missing_resources(
        apps_client,
        sts_names=sts_map.keys(),
        db_instances=instances
    )

    # 5. 更新状态同步的记录
    dingo_print(f"fetch_ai_instance_info {datatime_util.get_now_time()} start sync instance info in namespace: {namespace}")
    sync_instance_info(
        sts_map=sts_map,
        pod_map=pod_map,
        db_instance_map=db_instance_map,
        core_client=core_client,
        apps_client=apps_client,
        networking_client=networking_client
    )

def handle_orphan_resources(sts_names, svc_names, db_instance_map, namespace, core_client, apps_client, networking_client):
    db_instance_names = db_instance_map.keys()
    """处理K8s中存在但数据库不存在的资源"""
    orphans = set(sts_names) - set(db_instance_names)
    # cci的ns中多余的svc
    orphans_svcs = filter_svc_names(svc_names, db_instance_names)
    dingo_print(f"fetch_ai_instance_info {datatime_util.get_now_time()}======handle_orphan_resources======orphans:{orphans}")
    for name in orphans:
        ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_real_name(name)
        if ai_instance_info_db:
            dingo_print(f"fetch_ai_instance_info {datatime_util.get_now_time()} cleanup orphan resource ai instance in k8s, and exist in db: {namespace}/{name}. no delete")
            continue

        dingo_print(f"fetch_ai_instance_info {datatime_util.get_now_time()} cleanup orphan resource ai instance in k8s, but not exist in db: {namespace}/{name}")

        cleanup_cci_resources(apps_client, core_client, networking_client, name, namespace)

        # 清理关机镜像
        ai_instance_db = AiInstanceSQL.get_ai_instance_info_by_real_name(name)
        try:
           # 删除镜像库中保存的关机镜像
           k8s_configs_db = AiInstanceSQL.get_k8s_configs_info_by_k8s_id(ai_instance_db.instance_k8s_id)
           harbor_address = k8s_configs_db.harbor_address
           image_name = SAVE_TO_IMAGE_CCI_PREFIX + ai_instance_db.id
           project_name = ai_instance_service.extract_project_and_image_name(harbor_address)
           harbor_service.delete_custom_projects_images(project_name, image_name)
           dingo_print(f"fetch_ai_instance_info {datatime_util.get_now_time()} delete ai instance {ai_instance_db.id} stop-image project_image:{project_name}/{image_name} succeed")
        except Exception as e:
             dingo_print(f"fetch_ai_instance_info {datatime_util.get_now_time()} delete ai instance {ai_instance_db.id} stop-image {project_name}/{image_name} failed: {e}")

        try:
            # 删除 jupyter configMap
            k8s_common_operate.delete_configmap(core_client, namespace, ai_instance_db.instance_real_name)
            dingo_print(f"fetch_ai_instance_info {datatime_util.get_now_time()} delete ai instance {ai_instance_db.id} jupyter configMap {namespace}/{ai_instance_db.instance_real_name} succeed")
        except Exception as e:
            dingo_print(f"fetch_ai_instance_info {datatime_util.get_now_time()} delete jupyter configMap {namespace}/{ai_instance_db.instance_real_name} 失败: {str(e)}")

        # 删除metallb的默认端口
        AiInstanceSQL.delete_ai_instance_ports_info_by_instance_id(ai_instance_db.id)
        dingo_print(f"fetch_ai_instance_info {datatime_util.get_now_time()} delete ai instance {ai_instance_db.id} ports succeed")

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
            dingo_print(f"{datatime_util.get_now_time()} delete default svc {namespace}/{svc_name} failed: {e}")

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

    # 过滤条件: 服务名不以任何 db_prefixes 中的前缀开头（不区分大小写）
    filtered_svcs = {
        svc for svc in svc_set
        if not any(svc.lower().startswith(prefix) for prefix in db_prefixes)
    }

    return filtered_svcs

def cleanup_cci_resources(apps_client, core_client, networking_client, name, namespace):
    try:
        # 删除StatefulSet
        dingo_print(f"{datatime_util.get_now_time()} delete k8s sts: namespace = {namespace}, name = {name}")
        k8s_common_operate.delete_sts_by_name(
            apps_client,
            real_sts_name=name,
            namespace=namespace
        )
    except Exception as e:
        dingo_print(f"delete sts {namespace}/{name} failed: {str(e)}")

    try:
        # 删除default Service
        k8s_common_operate.delete_service_by_name(
            core_client,
            service_name=name,
            namespace=namespace
        )
    except Exception as e:
        dingo_print(f"delete default svc {namespace}/{name} failed: {str(e)}")

    try:
        # 删除 jupyter Service
        k8s_common_operate.delete_service_by_name(
            core_client,
            service_name=name + "-" + DEV_TOOL_JUPYTER,
            namespace=namespace
        )
    except Exception as e:
        dingo_print(f"{datatime_util.get_now_time()} delete jupyter svc {namespace}/{name} failed: {str(e)}")

    try:
        # 删除 ingress rule
        k8s_common_operate.delete_namespaced_ingress(
            networking_client,
            ingress_name=name,
            namespace=namespace
        )
    except Exception as e:
        dingo_print(f"{datatime_util.get_now_time()} delete ingress rule {namespace}/{name} failed: {str(e)}")

def handle_missing_resources(apps_client, sts_names, db_instances):
    """处理数据库中存在但K8s中不存在的记录"""
    sts_name_set = set(sts_names)
    for instance in db_instances:
        if instance.instance_real_name not in sts_name_set:
            try:
                k8s_common_operate.read_sts_info(apps_client, instance.instance_real_name, CCI_NAMESPACE_PREFIX + instance.instance_tenant_id)
                dingo_print(f"{datatime_util.get_now_time()} ai instance {instance.id} exist in db. no delete k8s resource")
                continue
            except Exception as e:
                dingo_print(f"{datatime_util.get_now_time()} sts {instance.instance_real_name} not found in k8s:{e}")

            # 当前时间
            current_time = datetime.now()
            # cci实例的最新操作时间
            cci_latest_operator_time = instance.create_time
            if instance.instance_start_time:
                cci_latest_operator_time = instance.instance_start_time
            # 最新操作时间与当前时间的差值
            operator_time_difference = current_time - cci_latest_operator_time
            # 差值在一小时之内的不允许清理
            if operator_time_difference <= timedelta(hours=1):
                # if is instance.instance_status in [AiInstanceStatus.DELETING.name], do delete ai instance in db
                if instance.instance_status in [AiInstanceStatus.DELETING.name]:
                    dingo_print(f"{datatime_util.get_now_time()} ai instance {instance.id} in deleting status, delete it in db")
                else:
                    dingo_print(f"{datatime_util.get_now_time()} current instance in 1 hour cannot be delete, id:{instance.id}, instance_status:{instance.instance_status} ")
                    continue

            try:
                # 清理实例
                AiInstanceSQL.delete_ai_instance_info_by_id(instance.id)
                # 清理端口数据
                AiInstanceSQL.delete_ai_instance_ports_info_by_instance_id(instance.id)
                dingo_print(f"fetch_ai_instance_info {datatime_util.get_now_time()} delete db not exist ai instance and ports: id = {instance.id}, name = {instance.instance_name}, real_name = {instance.instance_real_name} succeed ")
            except Exception as e:
                dingo_print(f"fetch_ai_instance_info {datatime_util.get_now_time()} delete db not exist instance id {instance.id}: {e}")

def sync_instance_info(sts_map, pod_map, db_instance_map,  core_client, apps_client, networking_client):
    """同步实例状态、image、env等信息"""
    dingo_print(f"fetch_ai_instance_info {datatime_util.get_now_time()}======sync_instance_info======db_instance_map size:{len(db_instance_map)}")

    for real_name, instance_db in db_instance_map.items():
        if real_name not in sts_map:
            continue

        sts = sts_map[real_name]
        pod = pod_map.get(f"{real_name}-0")  # StatefulSet Pod Naming Rule

        # if sts is not exists, this senario is not processed in this function, because we have processed in handle_missing_resources function
        if not sts:
            dingo_print(f"Not Found Sts[{real_name}], instance_status:{instance_db.instance_status}, not process in this function")
            continue

        # statefulset replicas 0
        if sts and sts.spec.replicas == 0:
            dingo_print(f"Sts[{real_name}]replicas == 0, check Pod[{real_name}-0] if exist")
            if not pod:
                dingo_print(f"Not Found Pod[{real_name}-0], Sts[{real_name}] replicas 0, check instance status, prev is {instance_db.instance_status}, will get latest db info to decide") 

                ai_instance_db = AiInstanceSQL.get_ai_instance_info_by_real_name(real_name)
                if ai_instance_db:
                    dingo_print(f"Not Found Pod[{real_name}-0], ai instance {ai_instance_db.id} found by real_name:{real_name}, check instance_status:{ai_instance_db.instance_status}")
                    # if instance_status is ERROR, do nothing
                    if(ai_instance_db.instance_status == AiInstanceStatus.ERROR.name):
                        dingo_print(f"Not Found Pod[{real_name}-0], ai instance {ai_instance_db.id} in ERROR status, no update status")
                        continue

                    # if instance_status is DELETING, do nothing
                    elif(ai_instance_db.instance_status == AiInstanceStatus.DELETING.name):
                        dingo_print(f"Not Found Pod[{real_name}-0], ai instance {ai_instance_db.id} in DELETING status, no update status")
                        continue
                    
                    # if instance_status is STOPPING, update to STOPPED
                    elif(ai_instance_db.instance_status == AiInstanceStatus.STOPPING.name):
                        dingo_print(f"Not Found Pod[{real_name}-0], ai instance {ai_instance_db.id} in STOPPING status, change to STOPPED, start_update_db")
                        ai_instance_db.instance_status = AiInstanceStatus.STOPPED.name
                        ai_instance_db.instance_real_status = None
                        AiInstanceSQL.update_ai_instance_info(ai_instance_db)
                        continue

                    # if instance_status is STOPPED, do nothing
                    elif(ai_instance_db.instance_status == AiInstanceStatus.STOPPED.name):
                        dingo_print(f"Not Found Pod[{real_name}-0], ai instance {ai_instance_db.id} in STOPPED status, no update status")
                        continue

                    # if instance_status is STARTING, do nothing
                    elif(ai_instance_db.instance_status == AiInstanceStatus.STARTING.name):
                        dingo_print(f"Not Found Pod[{real_name}-0], ai instance {ai_instance_db.id} in STARTING status, no update status")
                        continue

                    # if instance_status is READY or RUNNING, and pod not exist, change to STOPPED if last update_time > 3min, else do nothing
                    elif (ai_instance_db.instance_status == AiInstanceStatus.READY.name
                            or ai_instance_db.instance_status == AiInstanceStatus.RUNNING.name):
                        dingo_print(f"Not Found Pod[{real_name}-0], ai instance {ai_instance_db.id} check instance_status:{ai_instance_db.instance_status}")

                        # get time difference between now and ai_instance_db.update_time
                        time_difference = datetime.now() - ai_instance_db.update_time
                        # if time_difference <= timedelta(minutes=3), do nothing
                        if time_difference > timedelta(minutes=3):
                            dingo_print(f"Not Found Pod[{real_name}-0], ai instance {ai_instance_db.id} change instance_status:{ai_instance_db.instance_status} to STOPPED, time_diff:{time_difference}, update_time: {ai_instance_db.update_time}")
                            ai_instance_db.instance_status = AiInstanceStatus.STOPPED.name
                            ai_instance_db.instance_real_status = K8sStatus.STOPPED.value
                            ai_instance_db.error_msg = "k8s not exist this pod more 3min"
                            AiInstanceSQL.update_ai_instance_info(ai_instance_db)
                            ai_instance_service.set_k8s_sts_replica_by_instance_id(instance_db.id, 0)
                    else:
                        # other status, may not happen, because we have checked all status before, just change to STOPPED
                        dingo_print(f"Not Found Pod[{real_name}-0], ai instance {ai_instance_db.id} in other status:{ai_instance_db.instance_status}, change to STOPPED, start_update_db")
                        ai_instance_db.instance_status = AiInstanceStatus.STOPPED.name
                        ai_instance_db.instance_real_status = None
                        AiInstanceSQL.update_ai_instance_info(ai_instance_db)
                        continue
                else:
                    dingo_print(f"Not Found Pod[{real_name}-0], but not found ai instance by real_name:{real_name}, no update status")
                    continue
            else:
                # sts replicas 0, but pod exist, in stopping process, no update status
                dingo_print(f"Sts[{real_name}]replicas 0, but Pod[{real_name}-0] exist, maybe in stopping process, it's k8s process, no update status")
            continue

        # statefulset replicas 1
        if sts and sts.spec.replicas == 1:
            dingo_print(f"Sts[{real_name}] replicas not 0, replicas is {sts.spec.replicas}, check Pod[{real_name}-0] if exist")

            # pod not exist, instance status in starting or stopped, no update status
            # if not pod and (instance_db.instance_status.lower() == AiInstanceStatus.STARTING.name.lower() or instance_db.instance_status.lower() == AiInstanceStatus.STOPPED.name.lower()):
            #     dingo_print(f"Sts[{real_name}]replicas 1, but Pod[{real_name}-0] not exist, instance status in starting or stopped, no update status")
            #     continue
            # pod not exist, it's the issue of k8s, do not update status, wait next sync
            if not pod:
                dingo_print(f"Sts[{real_name}]replicas 1, but Pod[{real_name}-0] not exist, it's the issue of k8s, do not update status, wait next sync")
                continue

            # pod exist, check and update status
            else:
                dingo_print(f"Sts[{real_name}]replicas 1, Pod[{real_name}-0] exist, check and update status")

                # get k8s_status, error_msg
                k8s_status, error_msg = ai_instance_service.get_pod_final_status(pod)
                # k8s_image = extract_image_info(sts)
                pod_details = extract_pod_details(pod)
                instance_status = AiInstanceService.map_k8s_to_db_status(k8s_status, instance_db.instance_status)
                dingo_print(f"ai instance [{real_name}] k8s_status: {k8s_status}, instance_status: {instance_status}, error_msg: {error_msg}")

                # if instance_db.instance_status != instance_status, we need to check if instance_db.update_time is within 2 minutes, else we do not update it
                if instance_db.instance_status != instance_status:
                    # 重新获取最新的数据库记录以确保数据一致性
                    ai_instance_db = AiInstanceSQL.get_ai_instance_info_by_real_name(real_name)
                    if not ai_instance_db:
                        dingo_print(f"not found ai instance by real_name:{real_name}")
                        continue
                    
                    dingo_print(f"ai instance {ai_instance_db.id} check ai_instance_db.instance_status:{ai_instance_db.instance_status}, calc instance_status:{instance_status}")
                    
                    # 检查状态是否真的需要更新（使用最新的数据库记录）
                    if ai_instance_db.instance_status != instance_status:
                        dingo_print(f"ai instance {ai_instance_db.id} will calc change instance_status:{ai_instance_db.instance_status} to {instance_status}")
                        
                        # if ai_instance_db.instance_status is STOPPING, do not update status, wait next sync
                        if ai_instance_db.instance_status == AiInstanceStatus.STOPPING.name:
                            dingo_print(f"ai instance {ai_instance_db.id} in stopping status, no update status, wait next sync")
                            continue

                        # if ai_instance_db.instance_status is DELETING, do not update status, wait next sync
                        if ai_instance_db.instance_status == AiInstanceStatus.DELETING.name:
                            dingo_print(f"ai instance {ai_instance_db.id} in deleting status, no update status, wait next sync")

                            # check if update_time > 5min, if true, delete cci resources and then delete db record
                            if ai_instance_db.update_time and (datetime.now() - ai_instance_db.update_time) > timedelta(minutes=5):
                                dingo_print(f"ai instance {ai_instance_db.id} in deleting status, and update_time > 5min, delete cci resources and then delete db record")
                                try:
                                    cleanup_cci_resources(apps_client, core_client, networking_client, real_name, CCI_NAMESPACE_PREFIX + ai_instance_db.instance_tenant_id)
                                except Exception as e:
                                    dingo_print(f"cleanup cci resources for ai instance {ai_instance_db.id} failed: {e}")

                                try:
                                    AiInstanceSQL.delete_ai_instance_info_by_id(ai_instance_db.id)
                                    AiInstanceSQL.delete_ai_instance_ports_info_by_instance_id(ai_instance_db.id)
                                    dingo_print(f"delete ai instance {ai_instance_db.id} in deleting status db record succeed")
                                except Exception as e:
                                    dingo_print(f"delete ai instance {ai_instance_db.id} in deleting status db record failed: {e}")
                            continue
                        
                        # if ai_instance_db.instance_status is ERROR, do not update status, wait next sync
                        if ai_instance_db.instance_status == AiInstanceStatus.ERROR.name:
                            dingo_print(f"ai instance {ai_instance_db.id} in error status, no update status, wait next sync")
                            continue

                        # if ai_instance_db.instance_status is STOPPED, do not update status to other status except STARTING
                        if ai_instance_db.instance_status == AiInstanceStatus.STOPPED.name and instance_status != AiInstanceStatus.STARTING.name:
                            dingo_print(f"ai instance {ai_instance_db.id} in stopped status, no update status to {instance_status}, wait next sync")
                            continue
                        
                        # 检查更新时间是否存在，避免 None 异常
                        if ai_instance_db.update_time is None:
                            dingo_print(f"ai instance {ai_instance_db.id} update_time is None, allow update")
                        else:
                            # 最新操作时间与当前时间的差值
                            time_difference = datetime.now() - ai_instance_db.update_time
                            # 差值在3min之内的不允许更新
                            if time_difference <= timedelta(minutes=3):
                                dingo_print(f"ai instance {ai_instance_db.id} change instance_status:{ai_instance_db.instance_status} to {instance_status}, time_diff:{time_difference}, update_time: {ai_instance_db.update_time}, <= 3min, no update")
                                continue
                            else:
                                dingo_print(f"ai instance {ai_instance_db.id} change instance_status:{ai_instance_db.instance_status} to {instance_status}, time_diff:{time_difference}, update_time: {ai_instance_db.update_time}, > 3min, update")
                    else:
                        dingo_print(f"ai instance {ai_instance_db.id} instance_status:{ai_instance_db.instance_status} no change, will update other info")
                    
                    # 使用最新的数据库记录
                    instance_db = ai_instance_db
                    dingo_print(f"ai instance [{real_name}] final decide instance_status: {instance_status}, use latest db info to update")

                # 更新数据库记录
                try:
                    # 准备更新数据，处理可能的空值
                    update_data = {
                        'instance_real_status': k8s_status,
                        'instance_status': instance_status,
                        # 'instance_image': k8s_image,
                        'instance_node_name': pod.spec.node_name if pod and pod.spec and pod.spec.node_name else None
                    }

                    if pod_details:
                        update_data['instance_envs'] = pod_details.get('instance_envs')
                        update_data['error_msg'] = pod_details.get('error_msg')

                    dingo_print(f"ai instance [{real_name}] k8s_status: {k8s_status}, old_instance_status: {instance_db.instance_status}, new_instance_status: {instance_status}, error_msg: {error_msg}, start_update_db")
                    # 更新数据库
                    AiInstanceSQL.update_specific_fields_instance(instance_db, **update_data)

                    if instance_status.upper() == "ERROR":
                        # 修改副本数
                        dingo_print(f"ai instance [{real_name}] in error status, change sts replicas to 0")
                        ai_instance_service.set_k8s_sts_replica_by_instance_id(instance_db.id, 0)
                except Exception as e:
                    dingo_print(f"update ai instance failed[{real_name}]: {str(e)}")

    dingo_print(f"fetch_ai_instance_info {datatime_util.get_now_time()}======sync_instance_info======all done")

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

# def determine_instance_real_status(sts, pod):
#     """根据K8s资源确定实例状态"""
#     if not pod:
#         return "STOPPED"
#
#     if sts.status.replicas == 0:
#         return "STOPPED"
#
#     return pod.status.phase
