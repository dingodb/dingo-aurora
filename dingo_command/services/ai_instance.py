# ai实例的service层
import json
import random
import string
import uuid
from datetime import datetime

import yaml
from math import ceil

from kubernetes.client import V1PersistentVolumeClaim, V1ObjectMeta, V1PersistentVolumeClaimSpec, \
    V1ResourceRequirements, V1PodTemplateSpec, V1StatefulSet, V1LabelSelector, V1Container, V1VolumeMount, V1Volume, \
    V1ConfigMapVolumeSource, V1EnvVar, V1PodSpec, V1StatefulSetSpec, V1LifecycleHandler, V1ExecAction, V1Lifecycle, \
    V1ContainerPort, V1Toleration, V1EmptyDirVolumeSource
from oslo_log import log

from dingo_command.api.model.aiinstance import StorageObj
from dingo_command.common.k8s_common_operate import K8sCommonOperate
from dingo_command.db.models.ai_instance.models import AiInstanceInfo, AiK8sKubeConfigConfigs
from dingo_command.db.models.ai_instance.sql import AiInstanceSQL
from dingo_command.utils.constant import NAMESPACE_PREFIX, AI_INSTANCE_SYSTEM_MOUNT_PATH_DEFAULT, SYSTEM_DISK_NAME_DEFAULT, \
    RESOURCE_TYPE, AI_INSTANCE, AI_INSTANCE_PVC_MOUNT_PATH_DEFAULT, AI_INSTANCE_CM_MOUNT_PATH_DEFAULT, SYSTEM_DISK_SIZE_DEFAULT
from dingo_command.utils.k8s_client import get_k8s_core_client, get_k8s_app_client
from dingo_command.services.custom_exception import Fail

LOG = log.getLogger(__name__)

k8s_common_operate = K8sCommonOperate()

class AiInstanceService:

    def delete_ai_instance_by_instance_id(self, instance_id):
        return None

    def get_ai_instance_info_by_instance_id(self, instance_id):
        ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_instance_id(instance_id)
        if not ai_instance_info_db:
            raise Fail(f"ai instance[{instance_id}] is not found", error_message=f" 容器实例[{instance_id}找不到]")
        return self.assemble_ai_instance_return_result(ai_instance_info_db)

    def list_ai_instance_info(self, query_params, page, page_size, sort_keys, sort_dirs):
        # 业务逻辑
        try:
            # 按照条件从数据库中查询数据
            count, data = AiInstanceSQL.list_ai_instance_info(query_params, page, page_size, sort_keys, sort_dirs)
            # 数据处理
            ret = []
            # 遍历
            for r in data:
                # 填充数据
                temp = self.assemble_ai_instance_return_result(r)
                # 添加数据
                ret.append(temp)

            # 返回数据
            res = {}
            # 页数相关信息
            if page and page_size:
                res['currentPage'] = page
                res['pageSize'] = page_size
                res['totalPages'] = ceil(count / int(page_size))
            res['total'] = count
            res['data'] = ret
            return res
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None

    def assemble_ai_instance_return_result(self, r):
        temp = {}
        temp["instance_id"] = r.instance_id
        temp["instance_name"] = r.instance_name
        temp['instance_real_name'] = r.instance_real_name
        temp["instance_status"] = r.instance_status
        temp["instance_k8s_type"] = r.instance_k8s_type
        temp["instance_k8s_id"] = r.instance_k8s_id
        temp["instance_k8s_name"] = r.instance_k8s_name
        temp["instance_project_id"] = r.instance_project_id
        temp["instance_project_name"] = r.instance_project_name
        temp["instance_user_id"] = r.instance_user_id
        temp["instance_user_name"] = r.instance_user_name
        temp["instance_root_account_id"] = r.instance_root_account_id
        temp["instance_root_account_name"] = r.instance_root_account_name
        temp["dev_tool"] = r.dev_tool
        temp["instance_image"] = r.instance_image
        temp["image_type"] = r.image_type
        temp["stop_time"] = r.stop_time
        temp["auto_delete_time"] = r.auto_delete_time
        if r.instance_config:
            temp["instance_config"] = json.loads(r.instance_config)
        if r.instance_volumes:
            temp["volumes"] = json.loads(r.instance_volumes)
        if r.instance_envs:
            temp["instance_envs"] = json.loads(r.instance_envs)
        temp["instance_create_time"] = r.instance_create_time
        return temp

    def create_ai_instance(self, ai_instance):
        try:
            print(f"=====start create ai instance====")
            # 转化为数据库参数
            ai_instance_info_db = self.convert_ai_instance_info_db(ai_instance)
            # 校验容器实例参数
            self.check_ai_instance_parameter(ai_instance)

           # 获取k8s客户端
            core_k8s_client = get_k8s_core_client(ai_instance.k8s_id)
            app_k8s_client = get_k8s_app_client(ai_instance.k8s_id)

            # 容器实例名称
            ai_instance_info_db.instance_name = ai_instance.name

            # CPU、内存、GPU相关的资源限制
            resource_limits = {}
            node_selector_gpu = {}
            tolerations_gpu = []
            resource_limits['cpu'] = str(ai_instance.instance_config.compute_cpu)
            resource_limits['memory'] = ai_instance.instance_config.compute_memory + "Gi"
            if ai_instance.instance_config.gpu_model:
                if "nvidia" in ai_instance.instance_config.gpu_model.lower():
                    resource_limits['nvidia.com/gpu'] = str(ai_instance.instance_config.gpu_count)
                    # resource_limits['nvidia.com/gpu.memory'] = str(ai_instance.instance_config.gpu_memory)
                    node_selector_gpu['nvidia.com/gpu.product'] = ai_instance.instance_config.gpu_model
                    node_selector_gpu['nvidia.com/gpu.count'] = str(ai_instance.instance_config.gpu_count)

                    toleration = V1Toleration(
                            key="nvidia.com/gpu",
                            operator="Exists",
                            effect="NoSchedule"
                        )
                    tolerations_gpu.append(toleration)

                elif "amd" in ai_instance.instance_config.gpu_model.lower():
                    resource_limits['amd.com/gpu'] = str(ai_instance.instance_config.gpu_count)
                else:
                    LOG.erorr(f"ai instance[{ai_instance.name}] instance_config gpu model[{ai_instance.instance_config.gpu_model}] is unknown")

            results = []
            if ai_instance.instance_config.replica_count == 1:
                # 校验namespace是否存在，不存在则创建
                namespace_name = self.handling_and_create_namespace_info(ai_instance, core_k8s_client)
                # 组装statefulset pod数据
                ai_instance_info_db_rel = self.assemble_create_statefulset_pod_to_save(
                                                             ai_instance, ai_instance_info_db, app_k8s_client,
                                                             core_k8s_client, ai_instance.instance_envs,
                                                             namespace_name,resource_limits, node_selector_gpu,
                                                             tolerations_gpu)
                results.append(self.assemble_ai_instance_return_result(ai_instance_info_db_rel))
            else:
                # 校验namespace是否存在，不存在则创建
                namespace_name = self.handling_and_create_namespace_info(ai_instance, core_k8s_client)
                for i in range(ai_instance.instance_config.replica_count):
                    # 组装statefulset pod数据
                    ai_instance_info_db_rel = self.assemble_create_statefulset_pod_to_save(
                                                                 ai_instance, ai_instance_info_db, app_k8s_client,
                                                                 core_k8s_client, ai_instance.instance_envs,
                                                                 namespace_name,resource_limits, node_selector_gpu,
                                                                 tolerations_gpu)
                    results.append(self.assemble_ai_instance_return_result(ai_instance_info_db_rel))
            # 返回数据
            return results
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def assemble_create_statefulset_pod_to_save(self, ai_instance, ai_instance_info_db, app_k8s_client, core_k8s_client,
                                                env_vars, namespace_name, resource_limits, node_selector_gpu, tolerations_gpu):
        # 名称后面加上五位随机小写字母和数字组合字符串
        bottom_name = ai_instance.name + "-" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
        ai_instance_info_db.instance_real_name = bottom_name
        # 创建Service(StatefulSet需要)
        k8s_common_operate.create_ai_instance_sts_service(core_k8s_client, namespace_name, bottom_name)

        # 组装StatefulSet Pod 数据
        stateful_set_pod_data = self.assemble_statefulset_pod_info(
            sts_name=bottom_name,
            service_name=bottom_name,
            image=ai_instance.image,
            env_vars=env_vars,
            resource_limits=resource_limits,
            volumes=ai_instance.volumes,
            order_id=ai_instance.order_id,
            user_id=ai_instance.user_id,
            node_selector_gpu=node_selector_gpu,
            tolerations_gpu=tolerations_gpu

        )
        # 提前保存数据到数据库
        ai_instance_info_db_id = AiInstanceSQL.save_ai_instance_info(ai_instance_info_db)

        # 创建StatefulSet Pod
        create_namespaced_stateful_set_info = k8s_common_operate.create_sts_pod(
            app_k8s_client, namespace_name,stateful_set_pod_data)

        # 组装statefulset uid、creationTimestamp
        ai_instance_info_db_new = AiInstanceSQL.get_ai_instance_info_by_id(ai_instance_info_db_id)
        ai_instance_info_db_new.instance_id = create_namespaced_stateful_set_info.metadata.uid
        ai_instance_info_db_new.instance_create_time = create_namespaced_stateful_set_info.metadata.creation_timestamp
        # 更新数据
        AiInstanceSQL.update_ai_instance_info(ai_instance_info_db_new)
        return ai_instance_info_db_new

    def check_ai_instance_parameter(self, ai_instance):
        if not ai_instance:
            raise Fail("ai instance is empty", error_message=" 容器实例信息为空")
        if not ai_instance.k8s_id:
            raise Fail("k8s id is empty", error_message=" k8s集群ID为空")
        if not ai_instance.name:
            raise Fail("ai instance name is empty", error_message=" 容器实例名称为空")
        if not ai_instance.root_account_id:
            raise Fail("ai instance root account is empty", error_message=" 容器实例所属用户主账号为空")
        if not ai_instance.user_id:
            raise Fail("ai instance user_id is empty", error_message=" 容器实例所属用户ID为空")
        if ai_instance.instance_config.replica_count <= 0:
            raise Fail("ai instance replica count must be greater than or equal to 1",
                       error_message=" 容器实例副本个数必须大于等于1")

    # 处理和创建命名空间，包括设置使用哪个参数创建命令空间、校验命令空间、创建命令空间
    def handling_and_create_namespace_info(self, ai_instance, core_k8s_client):
        namespace_name = None
        if ai_instance.root_account_id:  # 是否主账号标识，为主账号
            namespace_name = NAMESPACE_PREFIX + ai_instance.root_account_id

        if not namespace_name:
            raise Fail("param error, can not to create namespace",
                       error_message="参数错误，无法创建namespace")

        #  判断命名空间是否存在
        if k8s_common_operate.check_ai_instance_ns_exists(core_k8s_client, namespace_name):
            print(f"namespace {namespace_name} already exists, not need to create")
        else:
            # 创建namespace
            k8s_common_operate.create_ai_instance_ns(core_k8s_client, namespace_name)
            print(f"=====create_namespace[{namespace_name}] end====")
        return namespace_name

    def assemble_statefulset_pod_info(self, sts_name: str, service_name: str, image: str,
                                      env_vars: list, resource_limits: dict, volumes: StorageObj,
                                      order_id: str, user_id: str, node_selector_gpu: dict, tolerations_gpu: list) -> V1StatefulSet:
        """构建StatefulSet对象"""
        # 1. 环境变量处理
        env_list = [
            V1EnvVar(name=key, value=str(value))
            for key, value in (env_vars or {}).items()
        ]

        # 2. 准备Volume和VolumeMount
        volume_mounts = [
            V1VolumeMount(name=SYSTEM_DISK_NAME_DEFAULT, mount_path=AI_INSTANCE_SYSTEM_MOUNT_PATH_DEFAULT)
        ]

        pod_volumes = [
            V1Volume(
                name=SYSTEM_DISK_NAME_DEFAULT,
                empty_dir=V1EmptyDirVolumeSource(
                    size_limit=SYSTEM_DISK_SIZE_DEFAULT
                )
            )
        ]

        # 处理PVC
        pvc_template = None
        if volumes and volumes.pvc_name and volumes.pvc_size:
            volume_mounts.append(
                V1VolumeMount(name=volumes.pvc_name, mount_path=AI_INSTANCE_PVC_MOUNT_PATH_DEFAULT)
            )
            pvc_template = V1PersistentVolumeClaim(
                metadata=V1ObjectMeta(name=volumes.pvc_name),
                spec=V1PersistentVolumeClaimSpec(
                    access_modes=["ReadWriteOnce"],
                    resources=V1ResourceRequirements(
                        requests={"storage": f"{volumes.pvc_size}Gi"}
                    )
                )
            )

        # 处理ConfigMap
        if volumes and volumes.configmap_name:
            volume_mounts.append(
                V1VolumeMount(name=volumes.configmap_name, mount_path=AI_INSTANCE_CM_MOUNT_PATH_DEFAULT)
            )
            pod_volumes.append(
                V1Volume(
                    name=volumes.configmap_name,
                    config_map=V1ConfigMapVolumeSource(name=volumes.configmap_name)
                )
            )

        # 3. 定义容器
        container = V1Container(
            name=sts_name,
            image=image,
            env=env_list,
            ports=[V1ContainerPort(container_port=22)],
            resources=V1ResourceRequirements(
                requests=resource_limits,
                limits=resource_limits
            ),
            volume_mounts=volume_mounts,  # 正确挂载
            lifecycle=V1Lifecycle(
                post_start=V1LifecycleHandler(
                    _exec=V1ExecAction(
                        command=["chmod", "755", AI_INSTANCE_SYSTEM_MOUNT_PATH_DEFAULT]
                    )
                )
            )
        )

        # 4. 定义Pod模板
        template = V1PodTemplateSpec(
            metadata=V1ObjectMeta(
                labels={
                    RESOURCE_TYPE: AI_INSTANCE,
                    "app": sts_name,
                    "dc.com/tenant.instance-id": order_id,
                    "dc.com/tenant.app": "",
                    "dc.com/tenant.source": "user",
                    "dc.com/tenant.user-id": user_id,
                }
            ),
            spec=V1PodSpec(
                containers=[container],
                volumes=pod_volumes,  # 直接传递Volume列表,
                node_selector=node_selector_gpu,
                tolerations=tolerations_gpu
            )
        )

        # 5. 构建StatefulSet
        sts_info = V1StatefulSet(
            metadata=V1ObjectMeta(name=sts_name),
            spec=V1StatefulSetSpec(
                replicas=1,
                selector=V1LabelSelector(match_labels={"app": sts_name,
                                                       RESOURCE_TYPE: AI_INSTANCE}),
                service_name=service_name,
                template=template,
                volume_claim_templates=[pvc_template] if pvc_template else None
            )
        )

        return sts_info

    def convert_ai_instance_info_db(self, ai_instance):
        ai_instance_info_db = AiInstanceInfo(id=uuid.uuid4().hex,
                                             instance_name=ai_instance.name,
                                             instance_status="creating",
                                             instance_k8s_type=ai_instance.k8s_type,
                                             instance_k8s_id=ai_instance.k8s_id,
                                             instance_k8s_name=ai_instance.k8s_name,
                                             instance_project_id=ai_instance.project_id,
                                             instance_project_name=ai_instance.project_name,
                                             instance_user_id=ai_instance.user_id,
                                             instance_user_name=ai_instance.user_name,
                                             instance_root_account_id=ai_instance.root_account_id,
                                             instance_root_account_name=ai_instance.root_account_name,
                                             # dev_tool=ai_instance.dev_tool,
                                             instance_image=ai_instance.image,
                                             image_type=ai_instance.image_type,
                                             stop_time=datetime.fromtimestamp(ai_instance.stop_time) if ai_instance.stop_time else None,
                                             auto_delete_time=datetime.fromtimestamp(ai_instance.auto_delete_time) if ai_instance.auto_delete_time else None,
                                             instance_config= json.dumps(ai_instance.instance_config.dict()) if ai_instance.instance_config  else None,
                                             instance_volumes= json.dumps(ai_instance.volumes.dict()) if ai_instance.volumes  else None,
                                             instance_envs= json.dumps(ai_instance.instance_envs) if ai_instance.instance_envs else None,
                                             instance_description= ai_instance.description
                                             )
        return ai_instance_info_db