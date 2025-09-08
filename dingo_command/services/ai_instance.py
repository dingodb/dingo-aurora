# ai实例的service层
import asyncio
import copy
import json
import random
import string
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from keystoneclient import client
from math import ceil
from kubernetes.client import V1PersistentVolumeClaim, V1ObjectMeta, V1PersistentVolumeClaimSpec, \
    V1ResourceRequirements, V1PodTemplateSpec, V1StatefulSet, V1LabelSelector, V1Container, V1VolumeMount, V1Volume, \
    V1ConfigMapVolumeSource, V1EnvVar, V1PodSpec, V1StatefulSetSpec, V1LifecycleHandler, V1ExecAction, V1Lifecycle, \
    V1ContainerPort, V1Toleration, V1EmptyDirVolumeSource, V1Affinity, V1PodAffinity, V1WeightedPodAffinityTerm, \
    V1PodAffinityTerm
from kubernetes import client
from kubernetes.stream import stream
from oslo_log import log

from dingo_command.api.model.aiinstance import StorageObj, AddPortModel
from dingo_command.common.Enum.AIInstanceEnumUtils import AiInstanceStatus, K8sStatus
from dingo_command.common.k8s_common_operate import K8sCommonOperate
from dingo_command.db.models.ai_instance.models import AiInstanceInfo, AccountInfo
from dingo_command.db.models.ai_instance.sql import AiInstanceSQL
from dingo_command.services.redis_connection import redis_connection, RedisLock
from dingo_command.utils.constant import NAMESPACE_PREFIX, AI_INSTANCE_SYSTEM_MOUNT_PATH_DEFAULT, \
    SYSTEM_DISK_NAME_DEFAULT, RESOURCE_TYPE_KEY, PRODUCT_TYPE_CCI, AI_INSTANCE_PVC_MOUNT_PATH_DEFAULT, \
    APP_LABEL, AI_INSTANCE_CM_MOUNT_PATH_SSHKEY, AI_INSTANCE_CM_MOUNT_PATH_SSHKEY_SUB_PATH, \
    CONFIGMAP_PREFIX, DEV_TOOL_JUPYTER, SAVE_TO_IMAGE_CCI_SUFFIX, GPU_CARD_MAPPING, SYSTEM_DISK_SIZE_DEFAULT, \
    GPU_POD_LABEL_KEY, GPU_POD_LABEL_VALUE, STOP_SAVE_IMAGE_PREFIX
from dingo_command.utils.k8s_client import get_k8s_core_client, get_k8s_app_client, get_k8s_networking_client
from dingo_command.services.custom_exception import Fail

LOG = log.getLogger(__name__)

k8s_common_operate = K8sCommonOperate()

# 全局线程池
task_executor = ThreadPoolExecutor(max_workers=4)

class AiInstanceService:

    def delete_ai_instance_by_id(self, id):
        ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
        if not ai_instance_info_db:
            raise Fail(f"ai instance[{id}] is not found", error_message=f" 容器实例[{id}找不到]")
        # 更新状态为删除中
        ai_instance_info_db.instance_status="DELETING"
        AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)

        # 优先尝试删除 K8s 资源（Service、StatefulSet）
        try:
            core_k8s_client = get_k8s_core_client(ai_instance_info_db.instance_k8s_id)
            app_k8s_client = get_k8s_app_client(ai_instance_info_db.instance_k8s_id)
            networking_k8s_client = get_k8s_networking_client(ai_instance_info_db.instance_k8s_id)
            namespace_name = NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id
            real_name = ai_instance_info_db.instance_real_name or ai_instance_info_db.instance_name

            try:
                k8s_common_operate.delete_service_by_name(core_k8s_client, real_name, namespace_name)
            except Exception as e:
                LOG.error(f"删除Service失败, name={real_name}, ns={namespace_name}, err={e}")

            try:
                k8s_common_operate.delete_service_by_name(core_k8s_client, real_name + "-" + DEV_TOOL_JUPYTER, namespace_name)
            except Exception as e:
                LOG.error(f"删除 jupyter Service失败, name={real_name}, ns={namespace_name}, err={e}")

            try:
                # 删除 ingress rule
                k8s_common_operate.delete_namespaced_ingress(networking_k8s_client, real_name, namespace_name)
            except Exception as e:
                LOG.error(f"删除ingress资源[{namespace_name}/{real_name}-jupyter]失败: {str(e)}")

            # TODO: 删除关机保存镜像
            
            try:
                k8s_common_operate.delete_sts_by_name(app_k8s_client, real_name, namespace_name)
            except Exception as e:
                LOG.error(f"删除StatefulSet失败, name={real_name}, ns={namespace_name}, err={e}")
                raise e
        except Exception as e:
            LOG.error(f"获取 K8s 客户端失败或删除资源异常: {e}")
            raise e

        # 删除数据库记录
        AiInstanceSQL.delete_ai_instance_info_by_id(id)

        # 移除pod在ops_ai_k8s_node_resource表中的资源占用
        node_resource_db = AiInstanceSQL.get_k8s_node_resource_by_k8s_id_and_node_name(ai_instance_info_db.instance_k8s_id, ai_instance_info_db.instance_node_name)
        if node_resource_db and ai_instance_info_db.instance_config:
            instance_config_dict = json.loads(ai_instance_info_db.instance_config)
            self.update_node_resources(node_resource_db, instance_config_dict, "release")
        return {"data": "success", "uuid": id}

    # ================= 账户相关 =================
    def create_ai_account(self, account: str, vip: str):
        try:
            if not account or not str(account).strip():
                raise Fail("account is empty", error_message="账户账号不能为空")

            # 校验是否已存在
            existed = AiInstanceSQL.get_account_info_by_account(account)
            if existed:
                raise Fail("account already exist", error_message="账户已存在")

            new_id = uuid.uuid4().hex
            account_db = AccountInfo(
                id=new_id,
                account=str(account).strip(),
                vip=str(vip)
            )
            AiInstanceSQL.save_account_info(account_db)
            return {"data": "success", "uuid": new_id}
        except Fail:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def delete_ai_account_by_id(self, id: str):
        try:
            if not id:
                raise Fail("id is empty", error_message="账户ID不能为空")

            existed = AiInstanceSQL.get_account_info_by_id(id)
            if not existed:
                raise Fail(f"account[{id}] is not found", error_message=f"账户[{id}]不存在")

            AiInstanceSQL.delete_account_info_by_id(id)
            return {"data": "success", "uuid": id}
        except Fail:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def update_ai_account_by_id(self, id: str, account: str = None, vip: str = None):
        try:
            if not id:
                raise Fail("id is empty", error_message="账户ID不能为空")

            existed = AiInstanceSQL.get_account_info_by_id(id)
            if not existed:
                raise Fail(f"account[{id}] is not found", error_message=f"账户[{id}]不存在")

            if account is not None:
                account = str(account).strip()
                if not account:
                    raise Fail("account is empty", error_message="账户账号不能为空")
                # 检查同名唯一
                conflict = AiInstanceSQL.get_account_info_by_account_excluding_id(account, id)
                if conflict:
                    raise Fail("account already exist", error_message="账户已存在")
                existed.account = account
            if vip:
                existed.vip = str(vip)

            AiInstanceSQL.update_account_info(existed)
            return {"data": "success", "uuid": id}
        except Fail:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def sava_ai_instance_to_image(self, id, image_registry, image_name, image_tag):
        """
        异步保存AI实例为镜像（立即返回，实际操作在后台执行）
        """
        try:
            with RedisLock(redis_connection.redis_connection, f"ai-instance-image-{id}", expire_time=3600) as lock:
                if lock:
                    # 参数验证和基本信息获取
                    ai_instance_info_db = self._validate_and_get_instance_info(id, image_registry, image_name, image_tag)

                    # 获取harbor信息
                    _, harbor_username, harbor_password  = self.get_harbor_info(ai_instance_info_db.instance_k8s_id)

                    # 获取k8s客户端和Pod信息
                    core_k8s_client, sts_pod_info = self._get_k8s_sts_pod_info(ai_instance_info_db)

                    # 获取nerdctl-api Pod信息
                    nerdctl_api_pod = self._get_nerdctl_api_pod(core_k8s_client, sts_pod_info['node_name'])

                    # 立即返回响应，后续操作异步执行
                    asyncio.create_task(
                        self._async_save_operation(
                            id, core_k8s_client, nerdctl_api_pod,
                            sts_pod_info['container_id'], image_registry, harbor_username, harbor_password,
                            image_name, image_tag
                        )
                    )
                    return {
                        "status": "accepted",
                        "message": "容器实例保存操作已开始异步执行",
                        "instance_id": id,
                        "image_name": f"{image_name}:{image_tag}"
                    }

                else:
                    print(f"未获取到锁{id}")
                    raise Fail(f"Ai instance [{id}] is saving, not allow to operation")

        except Exception as e:
            # 记录日志并重新抛出异常
            print(f"Failed to start save operation for instance {id}: {str(e)}")
            raise Fail(f"Failed to start save operation: {str(e)}")

    def sava_ai_instance_to_image_process_status(self, id):
        """
        异步保存AI实例为镜像（立即返回，实际操作在后台执行）
        """
        try:
            redis_key = id + SAVE_TO_IMAGE_CCI_SUFFIX
            value = redis_connection.get_redis_by_key(redis_key)
            if value:
                return {
                    "instance_id": id,
                    "process_status": "Saving",
                    "image": value
                }

        except Exception as e:
            print(f"Failed to start save operation for instance {id}: {str(e)}")
            raise Fail(f"Failed to query save cci to image operation: {str(e)}")

    def get_harbor_info(self, k8s_id):
        k8s_configs = AiInstanceSQL.get_k8s_configs_info_by_k8s_id(k8s_id)
        if not k8s_configs:
            raise Fail(f"ai instance[{id}] k8s kube configs is not found", error_message=f"容器实例[{id} k8s配置找不到]")
        return  k8s_configs.harbor_address,  k8s_configs.harbor_username,  k8s_configs.harbor_password

    def _validate_and_get_instance_info(self, id, image_registry, image_name, image_tag):
        """验证参数并获取实例信息"""
        ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
        if not ai_instance_info_db:
            raise Fail(f"ai instance[{id}] is not found", error_message=f"容器实例[{id}找不到]")

        if ai_instance_info_db.instance_status != "RUNNING":
            raise Fail(f"only ai instance[{id}] status is not RUNNING, can to operate", error_message=f"容器实例[{id}仅RUNNING状态支持操作]")

        if not image_registry:
            raise Fail(
                f"image name for saving the ai instance to image - [{id}] - is empty.",
                error_message=f"容器实例[{id}]保存的Harbor仓库地址为空"
            )

        if not image_name:
            raise Fail(
                f"image name for saving the ai instance to image - [{id}] - is empty.",
                error_message=f"容器实例[{id}]保存的镜像的名称为空"
            )

        if not image_tag:
            raise Fail(
                f"image tag for saving the ai instance to image - [{id}] - is empty.",
                error_message=f"容器实例[{id}]保存的镜像的标签为空"
            )

        return ai_instance_info_db

    def _get_k8s_sts_pod_info(self, ai_instance_info_db):
        """获取K8s Pod信息"""
        core_k8s_client = get_k8s_core_client(ai_instance_info_db.instance_k8s_id)

        pod = k8s_common_operate.get_pod_info(
            core_k8s_client,
            ai_instance_info_db.instance_real_name + "-0",
            NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id
        )

        container_id = pod.status.container_statuses[0].container_id
        clean_container_id = container_id.split('//')[-1]

        return core_k8s_client, {
            'container_id': clean_container_id,
            'node_name': pod.spec.node_name
        }


    def _get_nerdctl_api_pod(self, core_k8s_client, node_name):
        """获取nerdctl-api Pod"""
        nerdctl_api_pod = k8s_common_operate.list_pods_by_label_and_node(
            core_v1=core_k8s_client,
            label_selector="name=nerdctl-api",
            node_name=node_name
        )

        if not nerdctl_api_pod:
            raise Fail(
                f"Fail to save ai instance as image, can not exec command.",
                error_message=f"保存容器实例为镜像失败,无法执行保存命令"
            )

        return {
            'name': nerdctl_api_pod[0].metadata.name,
            'namespace': nerdctl_api_pod[0].metadata.namespace
        }

    async def _async_save_operation(self, id, core_k8s_client, nerdctl_api_pod,
                                    clean_container_id, harbor_address, harbor_username, harbor_password, image_name, image_tag):
        """
        实际的异步保存操作（受分布式锁保护）
        """

        # 存入redis，镜像推送完成标识
        redis_key = id + SAVE_TO_IMAGE_CCI_SUFFIX
        try:
            redis_connection.set_redis_by_key_with_expire(redis_key, f"{image_name}:{image_tag}", 3600)

            # 1. Harbor登录
            await self._harbor_login(core_k8s_client, nerdctl_api_pod, harbor_address, harbor_username, harbor_password)

            # 2. Commit操作
            image = f"{harbor_address}/{image_name}:{image_tag}"
            await self._commit_container(
                core_k8s_client, nerdctl_api_pod, clean_container_id, image
            )

            # 3. Push操作
            await self._push_image(core_k8s_client, nerdctl_api_pod, image)
            print(f"容器实例[{id}]推送镜像[{image_name}]完成")
        except Exception as e:
            print(f"Async save operation failed for instance {id}: {str(e)}")
        finally:
            redis_connection.delete_redis_key(redis_key)

    async def _execute_k8s_command(self, core_k8s_client, pod_name, namespace, command):
        """异步执行K8s命令的辅助函数"""
        loop = asyncio.get_event_loop()

        def _sync_execute():
            resp = stream(
                core_k8s_client.connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                container=None,
                command=command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
                _preload_content=False
            )

            # 读取输出
            output = []
            while resp.is_open():
                resp.update(timeout=1)
                if resp.peek_stdout():
                    stdout = resp.read_stdout()
                    output.append(f"STDOUT: {stdout}")
                if resp.peek_stderr():
                    stderr = resp.read_stderr()
                    output.append(f"STDERR: {stderr}")

            resp.close()
            return resp.returncode, "\n".join(output)

        return await loop.run_in_executor(None, _sync_execute)

    async def _harbor_login(self, core_k8s_client, nerdctl_api_pod, harbor_address, harbor_username, harbor_password):
        """Harbor登录"""
        harbor_login_command = [
            'nerdctl', 'login',
            '-u', harbor_username,
            '-p', harbor_password,
            harbor_address,
            '--insecure-registry'
        ]

        returncode, output = await self._execute_k8s_command(
            core_k8s_client, nerdctl_api_pod['name'], nerdctl_api_pod['namespace'], harbor_login_command
        )

        if returncode != 0:
            raise Exception(f"Harbor login failed: {output}")

    async def _commit_container(self, core_k8s_client, nerdctl_api_pod, clean_container_id, image_name):
        """执行commit操作"""
        commit_command = [
            'nerdctl', 'commit', clean_container_id, image_name,
            '--pause=false', '--namespace', 'k8s.io', '--insecure-registry'
        ]

        returncode, output = await self._execute_k8s_command(
            core_k8s_client, nerdctl_api_pod['name'], nerdctl_api_pod['namespace'], commit_command
        )

        if returncode != 0:
            raise Exception(f"Commit failed: {output}")

    async def _push_image(self, core_k8s_client, nerdctl_api_pod, image_name):
        """执行push操作"""
        push_command = [
            'nerdctl', 'push', image_name,
            '--namespace', 'k8s.io', '--insecure-registry'
        ]

        returncode, output = await self._execute_k8s_command(
            core_k8s_client, nerdctl_api_pod['name'], nerdctl_api_pod['namespace'], push_command
        )

        if returncode != 0:
            raise Exception(f"Push failed: {output}")

    def get_ai_instance_info_by_id(self, id):
        ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
        if not ai_instance_info_db:
            raise Fail(f"ai instance[{id}] is not found", error_message=f" 容器实例[{id}找不到]")
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
        temp["id"] = r.id
        temp["instance_name"] = r.instance_name
        temp['instance_real_name'] = r.instance_real_name
        temp['pod_name'] = r.instance_real_name + "-0"
        temp["instance_status"] = r.instance_status
        temp["instance_k8s_id"] = r.instance_k8s_id
        temp["instance_user_id"] = r.instance_user_id
        temp["instance_tenant_id"] = r.instance_tenant_id
        if r.instance_tenant_id: 
            temp["namespace"] = "ns-" + r.instance_tenant_id
        temp["instance_image"] = r.instance_image
        temp["stop_time"] = r.stop_time
        temp["auto_delete_time"] = r.auto_delete_time
        if r.instance_config:
            temp["instance_config"] = json.loads(r.instance_config)
        if r.instance_volumes:
            temp["volumes"] = json.loads(r.instance_volumes)
        if r.instance_envs:
            temp["instance_envs"] = json.loads(r.instance_envs)
        temp["instance_start_time"] = r.instance_start_time
        return temp

    def create_ai_instance(self, ai_instance):
        try:
            # 参数校验
            self._validate_ai_instance_parameters(ai_instance)
            # 初始化客户端
            self._initialize_clients(ai_instance.k8s_id)
            # 准备命名空间
            namespace_name = self._prepare_namespace(ai_instance)
            # 转换数据结构
            ai_instance_db = self._convert_to_db_model(ai_instance)

            if ai_instance.instance_config.replica_count == 1:
                # 单副本场景
                return self._create_single_instance(ai_instance, ai_instance_db, namespace_name)
            else:
                # 多副本场景
                return self._create_multiple_instances(ai_instance, ai_instance_db, namespace_name)
        except Exception as e:
            LOG.error(f"Failed to create AI instance: {str(e)}")
            import traceback
            traceback.print_exc()
            raise e

    def _validate_ai_instance_parameters(self, ai_instance):
        """校验CCI参数"""
        if not ai_instance:
            raise Fail("ai instance is empty", error_message="容器实例信息为空")
        if not ai_instance.k8s_id:
            raise Fail("k8s id is empty", error_message="k8s集群ID为空")
        if not ai_instance.name:
            raise Fail("ai instance name is empty", error_message="容器实例名称为空")
        if not ai_instance.tenant_id:
            raise Fail("ai instance root account is empty", error_message="容器实例所属租户ID为空")
        if not ai_instance.user_id:
            raise Fail("ai instance user_id is empty", error_message="容器实例所属用户ID为空")
        if ai_instance.instance_config.replica_count <= 0:
            raise Fail("ai instance replica count must be greater than or equal to 1",
                       error_message="容器实例副本个数必须大于等于1")

    def _initialize_clients(self, k8s_id):
        """初始化K8s客户端"""
        self.core_k8s_client = get_k8s_core_client(k8s_id)
        self.app_k8s_client = get_k8s_app_client(k8s_id)
        self.networking_k8s_client = get_k8s_networking_client(k8s_id)

    def _prepare_namespace(self, ai_instance):
        """准备命名空间"""
        namespace_name = NAMESPACE_PREFIX + ai_instance.tenant_id

        if not k8s_common_operate.check_ai_instance_ns_exists(self.core_k8s_client, namespace_name):
            k8s_common_operate.create_ai_instance_ns(self.core_k8s_client, namespace_name)
            LOG.info(f"Created namespace: {namespace_name}")

        return namespace_name

    def _convert_to_db_model(self, ai_instance) -> AiInstanceInfo:
        ai_instance_info_db = AiInstanceInfo(
            instance_name=ai_instance.name,
            instance_status="READY",  # 默认状态，表示准备创建
            instance_k8s_id=ai_instance.k8s_id,
            instance_user_id=ai_instance.user_id,
            instance_tenant_id=ai_instance.tenant_id,
            instance_image=ai_instance.image,
            stop_time=datetime.fromtimestamp(ai_instance.stop_time) if ai_instance.stop_time else None,
            auto_delete_time=datetime.fromtimestamp(ai_instance.auto_delete_time) if ai_instance.auto_delete_time else None,
            instance_config=json.dumps(ai_instance.instance_config.dict()) if ai_instance.instance_config else None,
            instance_volumes=json.dumps(ai_instance.volumes.dict()) if ai_instance.volumes else None,
            instance_envs=json.dumps(ai_instance.instance_envs) if ai_instance.instance_envs else None,
            instance_description=ai_instance.description
        )
        return ai_instance_info_db

    def _create_single_instance(self, ai_instance, ai_instance_db, namespace_name):
        """创建单个实例"""
        resource_config = self._prepare_resource_config(ai_instance.instance_config)
        instance_result = self._assemble_and_create_instance(
            ai_instance, ai_instance_db, namespace_name, resource_config
        )
        # 后台检查pod状态
        self._start_async_check_task(
            self.core_k8s_client,
            ai_instance_db.instance_k8s_id,
            instance_result.id,
            f"{instance_result.instance_real_name}-0",
            NAMESPACE_PREFIX + ai_instance_db.instance_tenant_id
        )

        return [self.assemble_ai_instance_return_result(instance_result)]

    def _create_multiple_instances(self, ai_instance, ai_instance_db, namespace_name):
        """创建多个实例副本"""
        resource_config = self._prepare_resource_config(ai_instance.instance_config)
        results = []

        for i in range(ai_instance.instance_config.replica_count):
            instance_copy = copy.deepcopy(ai_instance_db)
            instance_result = self._assemble_and_create_instance(
                ai_instance, instance_copy, namespace_name, resource_config
            )

            self._start_async_check_task(
                self.core_k8s_client,
                ai_instance_db.instance_k8s_id,
                instance_result.id,
                f"{instance_result.instance_real_name}-0",
                NAMESPACE_PREFIX + ai_instance_db.instance_tenant_id
            )

            results.append(self.assemble_ai_instance_return_result(instance_result))

        return results

    def _prepare_resource_config(self, instance_config):
        """准备资源限制配置"""
        resource_limits = {
            'cpu': int(instance_config.compute_cpu),
            'memory': instance_config.compute_memory + "Gi",
            'ephemeral-storage': SYSTEM_DISK_SIZE_DEFAULT
        }

        node_selector_gpu = {}
        toleration_gpus = []

        if instance_config.gpu_model:
            gpu_card_info = GPU_CARD_MAPPING.get(instance_config.gpu_model)
            if not gpu_card_info:
                raise Fail(f"GPU card mapping not found for model: {instance_config.gpu_model}")
            resource_limits[gpu_card_info['gpu_code']] = instance_config.gpu_count
            node_selector_gpu['nvidia.com/gpu.product'] = gpu_card_info['original_name']
            # 容忍度
            toleration_gpus.append(V1Toleration(
                key=gpu_card_info['original_name'],
                operator="Exists",
                effect="NoSchedule"
            ))

        return {
            'resource_limits': resource_limits,
            'node_selector_gpu': node_selector_gpu,
            'toleration_gpus': toleration_gpus
        }

    def _assemble_and_create_instance(self, ai_instance, ai_instance_db, namespace_name, resource_config):
        """组装并创建实例"""
        # 设置实例ID
        ai_instance_db.id = ai_instance.instance_id or uuid.uuid4().hex
        # 设置实例k8s上真实名称
        ai_instance_db.instance_real_name = ai_instance.name + "-" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))

        # 创建K8s资源
        self._create_cci_k8s_resources(ai_instance, ai_instance_db, namespace_name, resource_config)

        return ai_instance_db

    def _create_cci_k8s_resources(self, ai_instance, ai_instance_db, namespace_name, resource_config):
        """创建K8s相关资源"""
        # 获取服务IP
        service_ip = self._get_service_ip(ai_instance_db)

        # 1、创建jupter的service服务，包括默认端口8888
        k8s_common_operate.create_cci_jupter_service(
            self.core_k8s_client, namespace_name, ai_instance_db.instance_real_name
        )

        # 2、创建metallb的服务，包括默认端口22、9001、9002
        k8s_common_operate.create_cci_metallb_service(
            self.core_k8s_client, namespace_name, ai_instance_db.instance_real_name, service_ip
        )

        # 3、创建ingress 规则，端口是8888
        k8s_common_operate.create_cci_ingress_rule(
            self.networking_k8s_client, ai_instance_db.id, namespace_name,
            ai_instance_db.instance_real_name, ai_instance_db.instance_k8s_id, ai_instance.region_id
        )

        # 4、创建sshkey的configmap（如果有就跳过，没有就创建）
        configmap_name = CONFIGMAP_PREFIX + ai_instance.user_id
        k8s_common_operate.create_ns_configmap(
            self.core_k8s_client, namespace_name, configmap_name, {"authorized_keys": ""}
        )

        # 5、创建StatefulSet
        sts_data = self._assemble_sts_data(ai_instance, ai_instance_db, namespace_name, resource_config)
        k8s_common_operate.create_sts_pod(self.app_k8s_client, namespace_name, sts_data)

        # 保存数据库信息
        AiInstanceSQL.update_ai_instance_info(ai_instance_db)

    def _get_service_ip(self, ai_instance_db):
        """获取服务IP地址"""
        account_vip_db = AiInstanceSQL.get_account_info_by_account(ai_instance_db.instance_tenant_id)
        if account_vip_db:
            return account_vip_db.vip

        k8s_configs_db = AiInstanceSQL.get_k8s_configs_info_by_k8s_id(ai_instance_db.instance_k8s_id)
        return k8s_configs_db.public_ip

    def _assemble_sts_data(self, ai_instance, ai_instance_db, namespace_name, resource_config):
        """
        组装创建StatefulSet所需的数据对象。

        Args:
            ai_instance: 前端传入的AI实例参数对象，包含镜像、配置等信息。
            ai_instance_db: 已转换为数据库模型的AI实例信息。
            namespace_name: 目标命名空间名称。
            resource_config: 资源限制配置字典，包含resource_limits, node_selector_gpu, toleration_gpus。

        Returns:
            V1StatefulSet: 组装好的Kubernetes StatefulSet对象。
        """
        # 解包资源配置
        resource_limits = resource_config['resource_limits']
        node_selector_gpu = resource_config['node_selector_gpu']
        toleration_gpus = resource_config['toleration_gpus']

        # 环境变量处理
        env_vars_dict = json.loads(ai_instance_db.instance_envs) if ai_instance_db.instance_envs else {}
        # 处理环境变量
        env_vars_dict['NB_PREFIX'] = f"/{ai_instance_db.id}/notebook/jupyter/{namespace_name}/{ai_instance_db.instance_real_name}-0"
        if "JUPYTER_TOKEN" not in env_vars_dict.keys():
            env_vars_dict['JUPYTER_TOKEN'] = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        env_list = [
            V1EnvVar(name=key, value=str(value))
            for key, value in env_vars_dict.items()
        ]


        # 准备Volume和VolumeMount
        volume_mounts = []
        pod_volumes = []
        # volume_mounts = [
        #     V1VolumeMount(name=SYSTEM_DISK_NAME_DEFAULT, mount_path=AI_INSTANCE_SYSTEM_MOUNT_PATH_DEFAULT)
        # ]
        #
        # pod_volumes = [
        #     V1Volume(
        #         name=SYSTEM_DISK_NAME_DEFAULT,
        #         empty_dir=V1EmptyDirVolumeSource(
        #             size_limit=resource_limits.get('ephemeral-storage', '50Gi')  # 从资源限制中获取或使用默认值
        #         )
        #     )
        # ]

        # 处理PVC (从ai_instance.volumes中获取信息)
        pvc_template = None
        if ai_instance.volumes and ai_instance.volumes.pvc_name and ai_instance.volumes.pvc_size:
            volume_mounts.append(
                V1VolumeMount(name=ai_instance.volumes.pvc_name, mount_path=AI_INSTANCE_PVC_MOUNT_PATH_DEFAULT)
            )
            pvc_template = V1PersistentVolumeClaim(
                metadata=V1ObjectMeta(name=ai_instance.volumes.pvc_name),
                spec=V1PersistentVolumeClaimSpec(
                    access_modes=["ReadWriteOnce"],
                    resources=V1ResourceRequirements(
                        requests={"storage": f"{ai_instance.volumes.pvc_size}Gi"}
                    )
                )
            )

        # 添加SSH公钥的ConfigMap (固定逻辑)
        configmap_name_ssh = CONFIGMAP_PREFIX + ai_instance.user_id
        volume_mounts.append(
            V1VolumeMount(name=configmap_name_ssh, mount_path=AI_INSTANCE_CM_MOUNT_PATH_SSHKEY,
                          sub_path=AI_INSTANCE_CM_MOUNT_PATH_SSHKEY_SUB_PATH)
        )
        pod_volumes.append(
            V1Volume(
                name=configmap_name_ssh,
                config_map=V1ConfigMapVolumeSource(name=configmap_name_ssh)
            )
        )

        affinity = {}
        if node_selector_gpu:
            # 定义 Pod 的亲和性配置
            affinity = V1Affinity(
                pod_affinity=V1PodAffinity(
                    preferred_during_scheduling_ignored_during_execution=[
                        V1WeightedPodAffinityTerm(
                            weight=100,
                            pod_affinity_term=V1PodAffinityTerm(
                                label_selector=V1LabelSelector(
                                    match_expressions=[
                                        client.V1LabelSelectorRequirement(
                                            key=GPU_POD_LABEL_KEY,
                                            operator="In",
                                            values=[GPU_POD_LABEL_VALUE]
                                        )
                                    ]
                                ),
                                namespace_selector={},  # 空字典表示选择所有命名空间
                                topology_key="kubernetes.io/hostname"
                            )
                        )
                    ]
                )
            )

        # USERNAME = "root"
        # PASSWORD = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        # 定义容器
        container = V1Container(
            name=ai_instance_db.instance_real_name,  # 使用实例的真实名称
            image=ai_instance.image,
            image_pull_policy="Always",
            env=env_list,
            ports=[V1ContainerPort(container_port=22), V1ContainerPort(container_port=8888), V1ContainerPort(container_port=9001), V1ContainerPort(container_port=9002)],  # 固定端口
            resources=V1ResourceRequirements(
                requests=resource_limits,
                limits=resource_limits
            ),
            volume_mounts=volume_mounts,
            # lifecycle=V1Lifecycle(
            #     post_start=V1LifecycleHandler(
            #         _exec=V1ExecAction(
            #             command=[
            #                 "/bin/sh",
            #                 "-c",
            #                 f"mkdir -p {AI_INSTANCE_SYSTEM_MOUNT_PATH_DEFAULT} && chmod 755 {AI_INSTANCE_SYSTEM_MOUNT_PATH_DEFAULT}"
            #             ]
            #         )
            #     )
            # )

            # lifecycle=client.V1Lifecycle(
            #     post_start=client.V1LifecycleHandler(
            #         _exec=client.V1ExecAction(
            #             command=[
            #                 "/bin/bash", "-c",
            #                 f"""
            #                 useradd -m -s /bin/bash -u 1000 root
            #                 echo root:${PASSWORD} | chpasswd
            #                 """
            #             ]
            #         )
            #     )
            # ),
            # security_context=client.V1SecurityContext(run_as_user=0, run_as_group=0)
        )


        pod_template_labels = {
                    RESOURCE_TYPE_KEY: PRODUCT_TYPE_CCI,
                    APP_LABEL: ai_instance_db.instance_real_name,
                    "dc.com/tenant.instance-id": ai_instance_db.id,
                    "dc.com/tenant.app": "CCI",
                    "dc.com/product.item": "CCI",
                    "dc.com/tenant.source": "user",
                    "dc.com/tenant.user-id": ai_instance.user_id,
                    # "dc.com/params.productType":  ai_instance.instance_config if ai_instance.instance_config else "",
                    "dc.com/params.cciId": ai_instance_db.id,
                    "dc.com/params.regionId": ai_instance.region_id,
                    "dc.com/params.zoneId": ai_instance.k8s_id,
                }
        if any(key.startswith('nvidia.com/') for key in resource_limits):
            pod_template_labels[GPU_POD_LABEL_KEY] = GPU_POD_LABEL_VALUE

        # 定义Pod模板
        template = V1PodTemplateSpec(
            metadata=V1ObjectMeta(
                labels=pod_template_labels
            ),
            spec=V1PodSpec(
                containers=[container],
                volumes=pod_volumes,
                node_selector=node_selector_gpu,  # 使用传入的GPU节点选择器
                tolerations=toleration_gpus,  # 使用传入的GPU容忍度
                affinity=affinity
            )
        )

        # 构建StatefulSet
        sts_data = V1StatefulSet(
            metadata=V1ObjectMeta(
                name=ai_instance_db.instance_real_name,
                namespace=namespace_name,  # 指定命名空间
                labels={RESOURCE_TYPE_KEY: PRODUCT_TYPE_CCI}
            ),
            spec=V1StatefulSetSpec(
                replicas=1,  # StatefulSet副本数，通常为1，由外层控制多实例
                selector=V1LabelSelector(
                    match_labels={
                        APP_LABEL: ai_instance_db.instance_real_name,
                        RESOURCE_TYPE_KEY: PRODUCT_TYPE_CCI
                    }
                ),
                service_name=ai_instance_db.instance_real_name,  # 关联的Service名称
                template=template,
                volume_claim_templates=[pvc_template] if pvc_template else None  # PVC模板，如果有的话
            )
        )

        return sts_data

    def start_ai_instance_by_id(self, id, request):
        try:
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            if not ai_instance_info_db:
                raise Fail(f"ai instance[{id}] is not found", error_message=f"容器实例[{id}找不到]")

            # 检查实例状态，只有 stopped 状态的实例才能开机
            if ai_instance_info_db.instance_status != AiInstanceStatus.STOPPED.name:
                raise Fail(f"ai instance[{id}] status is {ai_instance_info_db.instance_status}, cannot start",
                          error_message=f" 容器实例[{id}]状态为{ai_instance_info_db.instance_status}，无法开机")
            # 更新开机时间和开机中状态
            ai_instance_info_db.instance_start_time = datetime.fromtimestamp(datetime.now().timestamp())
            ai_instance_info_db.instance_status = AiInstanceStatus.STARTING.name
            ai_instance_info_db.instance_real_status = K8sStatus.PENDING.value
            AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)

            # 获取k8s客户端
            app_k8s_client = get_k8s_app_client(ai_instance_info_db.instance_k8s_id)
            core_k8s_client = get_k8s_core_client(ai_instance_info_db.instance_k8s_id)

            # 命名空间名称与实例名
            namespace_name = NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id
            real_name = ai_instance_info_db.instance_real_name
            if request and request.image:
                image_name = request.image
            else:
                harbor_address, harbor_username, harbor_password = self.get_harbor_info(ai_instance_info_db.instance_k8s_id)
                image_name = harbor_address + "/" + STOP_SAVE_IMAGE_PREFIX + id + ":latest"
            # 直接 Patch StatefulSet 副本为 1（开机）
            body = {
                "spec": {
                    "replicas": 1,  # 修改副本数
                    "template": {
                        "spec": {
                            "containers": [  # 这是一个列表，需要指定容器标识
                                {
                                    "name": real_name,  # 关键：通过名称标识要修改的容器
                                    "image": image_name  # 然后更新它的镜像
                                }
                            ]
                        }
                    }
                }
            }
            try:
                app_k8s_client.patch_namespaced_stateful_set(
                    name=real_name,
                    namespace=namespace_name,
                    body=body,
                    _preload_content=False
                )
            except Exception as e:
                LOG.error(f"开机失败, 实例ID: {id}, 错误: {e}")
                ai_instance_info_db.instance_start_time = None
                ai_instance_info_db.instance_status = AiInstanceStatus.STOPPED.name
                ai_instance_info_db.instance_real_status = None
                AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)
                raise e

            # 后台检查pod状态
            self._start_async_check_task(
                core_k8s_client,
                ai_instance_info_db.instance_k8s_id,
                ai_instance_info_db.id,
                f"{ai_instance_info_db.instance_real_name}-0",
                NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id
            )
            return {"id": id, "status": ai_instance_info_db.instance_status}
        except Exception as e:
            import traceback
            traceback.print_exc()
            # 回滚数据
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            ai_instance_info_db.instance_start_time = None
            ai_instance_info_db.instance_status = AiInstanceStatus.STOPPED.name
            ai_instance_info_db.instance_real_status = None
            AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)
            raise e



    def stop_ai_instance_by_id(self, id):
        try:
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            if not ai_instance_info_db:
                raise Fail(f"ai instance[{id}] is not found", error_message=f" 容器实例[{id}找不到]")

            # 异步保存镜像
            asyncio.create_task(
                self.sava_ai_instance_to_image_backup(id)
            )

            # 标记为 STOPPED
            ai_instance_info_db.instance_status = AiInstanceStatus.STOPPING.name
            AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)

            return {"id": id, "status": AiInstanceStatus.STOPPING.name}
        except Fail:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    async def sava_ai_instance_to_image_backup(self, id, image_tag = "latest"):
        """
        异步保存AI实例为镜像（立即返回，实际操作在后台执行）
        """
        try:
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            if ai_instance_info_db:
                image_name = STOP_SAVE_IMAGE_PREFIX + id
                harbor_address, harbor_username, harbor_password  = self.get_harbor_info(ai_instance_info_db.instance_k8s_id)
                core_k8s_client, sts_pod_info = self._get_k8s_sts_pod_info(ai_instance_info_db)
                nerdctl_api_pod = self._get_nerdctl_api_pod(core_k8s_client, sts_pod_info['node_name'])

                await self._async_save_operation(
                    id, core_k8s_client, nerdctl_api_pod,
                    sts_pod_info['container_id'], harbor_address, harbor_username, harbor_password,
                    image_name, image_tag
                )

                app_client = get_k8s_app_client(ai_instance_info_db.instance_k8s_id)
                body = {"spec": {"replicas": 0}}
                try:
                    app_client.patch_namespaced_stateful_set(
                        name=ai_instance_info_db.instance_real_name,
                        namespace=NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id,
                        body=body,
                        _preload_content=False
                    )
                except Exception as e:
                    LOG.error(f"关机失败，实例ID: {id}, 错误: {e}")
                    ai_instance_info_db.instance_status = AiInstanceStatus.RUNNING.name
                    ai_instance_info_db.instance_real_status = K8sStatus.RUNNING.value
                    AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)
                    raise e

                # 标记为 STOPPED
                ai_instance_info_db.instance_status = AiInstanceStatus.STOPPED.name
                ai_instance_info_db.instance_real_status = None
                ai_instance_info_db.stop_time = datetime.now()
                AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)

                # 释放pod 所在节点node资源
                node_resource_db = AiInstanceSQL.get_k8s_node_resource_by_k8s_id_and_node_name(
                    ai_instance_info_db.instance_k8s_id, ai_instance_info_db.instance_node_name)
                if node_resource_db and ai_instance_info_db.instance_config:
                    instance_config_dict = json.loads(ai_instance_info_db.instance_config)
                    self.update_node_resources(node_resource_db, instance_config_dict, "release")

        except Exception as e:
            print(f"Failed to start save operation for instance {id}: {str(e)}")
            raise Fail(f"Failed to start save operation: {str(e)}")

    def set_auto_close_instance_by_id(self, id: str, auto_close_time: str, auto_close: bool):
        try:
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            if not ai_instance_info_db:
                raise Fail(f"ai instance[{id}] is not found", error_message=f" 容器实例[{id}找不到]")

            if auto_close:
                if not auto_close_time:
                    raise Fail("auto close time is empty", error_message="定时关机时间为空")
                try:
                    # 手动解析时间字符串
                    parsed_time = datetime.fromisoformat(auto_close_time)
                    ai_instance_info_db.stop_time = parsed_time
                except ValueError:
                    raise Fail("invalid time format", error_message="时间格式无效，请使用 YYYY-MM-DDTHH:MM:SS 格式")
            else:
                ai_instance_info_db.stop_time = None

            AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)
            return self.assemble_ai_instance_return_result(ai_instance_info_db)
        except Fail:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def set_auto_delete_instance_by_id(self, id: str, auto_delete_time: str, auto_delete: bool):
        try:
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            if not ai_instance_info_db:
                raise Fail(f"ai instance[{id}] is not found", error_message=f" 容器实例[{id}找不到]")

            if auto_delete:
                if not auto_delete_time:
                    raise Fail("auto delete time is empty", error_message="定时删除时间为空")
                try:
                    # 手动解析时间字符串
                    parsed_time = datetime.strptime(auto_delete_time, "%Y-%m-%d %H:%M:%S")
                    ai_instance_info_db.auto_delete_time = parsed_time
                except ValueError:
                    raise Fail("invalid time format", error_message="时间格式无效，请使用 YYYY-MM-DD HH:MM:SS 格式")
            else:
                ai_instance_info_db.auto_delete_time = None

            AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)
            return self.assemble_ai_instance_return_result(ai_instance_info_db)
        except Fail:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e


    async def check_pod_status_node_name_and_update_db(self,
                                                       core_k8s_client,
                                                       k8s_id: str,
                                                       instance_id: str,
                                                       pod_name: str,
                                                       namespace: str,
                                                       timeout: int = 360
                                                       ):
        """
        异步检查 Pod 状态并更新数据库

        :param core_k8s_client: k8s core v1 client
        :param pod_name: 要检查的 Pod 名称
        :param namespace: Pod 所在的命名空间
        :param timeout: 超时时间(秒)，默认5分钟(300秒)
        """
        try:
            start_time = datetime.now()
            pod_real_status = None
            pod_located_node_name = None

            while (datetime.now() - start_time).total_seconds() < timeout:
                try:
                    # 查询 Pod 状态
                    pod = k8s_common_operate.get_pod_info(core_k8s_client, pod_name, namespace)

                    current_real_status = pod.status.phase
                    current_node_name = pod.spec.node_name

                    # 如果状态发生变化，更新数据库
                    if current_real_status != pod_real_status or current_node_name != pod_located_node_name:
                        pod_real_status = current_real_status
                        pod_located_node_name = current_node_name
                        self.update_pod_status_and_node_name_in_db(instance_id, pod_real_status, pod_located_node_name)
                        print(f"Pod {pod_name} 状态/node name更新为: {pod_real_status}_{pod_located_node_name}")

                    # 如果 Pod 处于 Running 状态，退出循环
                    if pod_real_status == "Running":
                        print(f"Pod {pod_name} 已正常运行, node name:{current_node_name}")
                        node_name = pod.spec.node_name
                        node_resource_db = AiInstanceSQL.get_k8s_node_resource_by_k8s_id_and_node_name(k8s_id, node_name)
                        if node_resource_db:
                            try:
                                # 更新资源使用量
                                limit_resources = pod.spec.containers[0].resources.limits
                                # 转换并累加CPU使用量
                                new_cpu_used  = self.convert_cpu_to_core(limit_resources.get('cpu', '0'))
                                if node_resource_db.cpu_used:
                                    # 使用float来处理小数
                                    total_cpu = float(node_resource_db.cpu_used) + float(new_cpu_used)
                                    node_resource_db.cpu_used = str(total_cpu)
                                else:
                                    node_resource_db.cpu_used = new_cpu_used

                                # 转换并累加内存使用量
                                new_memory_used = self.convert_memory_to_gb(limit_resources.get('memory', '0'))
                                if node_resource_db.memory_used:
                                    # 使用float来处理小数
                                    total_memory = float(node_resource_db.memory_used) + float(new_memory_used)
                                    node_resource_db.memory_used = str(total_memory)
                                else:
                                    node_resource_db.memory_used = new_memory_used

                                # 累加存储使用量
                                new_storage_used = self.convert_storage_to_gb(limit_resources.get('ephemeral-storage', '0'))
                                if node_resource_db.storage_used:
                                    # 使用float来处理小数
                                    total_storage = float(node_resource_db.storage_used) + float(new_storage_used)
                                    node_resource_db.storage_used = str(total_storage)
                                else:
                                    node_resource_db.storage_used = new_storage_used

                                # 处理GPU使用卡数
                                instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(instance_id)
                                compute_resource_dict = json.loads(instance_info_db.instance_config) if instance_info_db else {}
                                if ('gpu_model' in compute_resource_dict and 'gpu_count' in compute_resource_dict and
                                        compute_resource_dict['gpu_model'] and node_resource_db.gpu_model):
                                    if node_resource_db.gpu_used:
                                        total_gpu = int(node_resource_db.gpu_used) + int(compute_resource_dict['gpu_count'])
                                        node_resource_db.gpu_used = str(total_gpu)
                                    else:
                                        node_resource_db.gpu_used = int(compute_resource_dict['gpu_count'])

                                    node_resource_db.gpu_pod_count += 1
                                else:
                                    node_resource_db.less_gpu_pod_count += 1

                                AiInstanceSQL.update_k8s_node_resource(node_resource_db)
                                LOG.info(f"k8s[{k8s_id}] node[{node_name}] resource update success")
                            except Exception as e:
                                LOG.error(f"save k8s node resource fail:{e}")
                                import traceback
                                traceback.print_exc()
                        else:
                            LOG.error(f"Not found k8s[{k8s_id}] node[{node_name}] resource info, can not to update used resource")

                        # 明确退出函数
                        return

                    # 等待3秒后再次检查
                    await asyncio.sleep(3)

                except Exception as e:
                    import traceback
                    traceback.print_exc()

                    await asyncio.sleep(3)

            # 5. 检查是否超时
            if (datetime.now() - start_time).total_seconds() >= timeout:
                print(f"Pod {pod_name} 状态检查超时(6分钟)")
                self.update_pod_status_and_node_name_in_db(instance_id, K8sStatus.ERROR.value, pod_located_node_name)

        except Exception as e:
            print(f"检查Pod状态时发生未预期错误: {e}")
            import traceback
            traceback.print_exc()
            return

    def update_pod_status_and_node_name_in_db(self, id : str, k8s_status: str, node_name: str):
        """
        更新数据库中的 Pod 状态

        :param id: 容器实例ID
        :param k8s_status: 状态值
        :param node_name: 节点名称
        """
        try:
            ai_instance_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            ai_instance_db.instance_real_status = k8s_status
            ai_instance_db.instance_status = self.map_k8s_to_db_status(k8s_status, ai_instance_db.instance_status)
            ai_instance_db.instance_node_name = node_name
            print(f"异步更新容器实例[{ai_instance_db.instance_real_name}] instance_status：{ai_instance_db.instance_status}, node name:{ai_instance_db.instance_node_name}")
            AiInstanceSQL.update_ai_instance_info(ai_instance_db)
        except Exception as e:
            print(f"更新容器实例[{id}]数据库失败: {e}")

    @staticmethod
    def map_k8s_to_db_status(k8s_status: str, original_status: str):
        """
        将K8s状态映射为数据库状态(使用枚举)

        :param k8s_status: Kubernetes Pod状态字符串
        :param original_status: 原始数据库状态字符串
        :return: 映射后的数据库状态枚举
        """

        # 状态转换规则字典
        status_rules = {
            AiInstanceStatus.READY: {
                K8sStatus.PENDING: AiInstanceStatus.READY,
                K8sStatus.RUNNING: AiInstanceStatus.RUNNING
            },
            AiInstanceStatus.STOPPING: {
                K8sStatus.STOPPED: AiInstanceStatus.STOPPED,
                K8sStatus.RUNNING: AiInstanceStatus.RUNNING
            },
            AiInstanceStatus.STARTING: {
                K8sStatus.PENDING: AiInstanceStatus.STARTING,
                K8sStatus.RUNNING: AiInstanceStatus.RUNNING
            },
            AiInstanceStatus.DELETING: {
                K8sStatus.STOPPED: AiInstanceStatus.STOPPED,
                K8sStatus.RUNNING: AiInstanceStatus.RUNNING
            },
            # 公共规则适用于 RUNNING, ERROR, STOPPED
            None: {
                K8sStatus.STOPPED: AiInstanceStatus.STOPPED,
                K8sStatus.RUNNING: AiInstanceStatus.RUNNING
            }
        }

        # 转换为枚举类型
        k8s_enum = K8sStatus.from_string(k8s_status)
        original_enum = AiInstanceStatus.from_string(original_status)

        # 获取适用的转换规则
        rules = status_rules.get(original_enum, status_rules[None])

        # 应用转换规则或返回错误状态
        result_status = rules.get(k8s_enum, AiInstanceStatus.ERROR)

        return result_status.value

    def add_node_port_by_id(self, id: str, model: AddPortModel):
        try:
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            if not ai_instance_info_db:
                raise Fail(f"ai instance[{id}] is not found", error_message=f" 容器实例[{id}找不到]")

            core_k8s_client = get_k8s_core_client(ai_instance_info_db.instance_k8s_id)
            namespace_name = NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id
            service_name = ai_instance_info_db.instance_real_name

            port = int(model.port)
            target_port = int(model.target_port) if hasattr(model, 'target_port') and model.target_port is not None else 8888
            node_port = int(model.node_port) if getattr(model, 'node_port', None) is not None else None
            protocol = getattr(model, 'protocol', None) or 'TCP'

            # NodePort 占用校验（以 node_port=port 的策略暴露）
            if k8s_common_operate.is_port_in_use(core_k8s_client, port):
                raise Fail(f"port {port} already in use", error_message=f"节点端口 {port} 已被占用")

            # 读取 Service 并追加端口
            svc = core_k8s_client.read_namespaced_service(name=service_name, namespace=namespace_name)
            if not svc or not svc.spec:
                raise Fail("service invalid", error_message="Service 无效")

            existing_ports = svc.spec.ports or []
            new_port = client.V1ServicePort(port=port, target_port=target_port, protocol=protocol)

            # 必须为每个端口设置唯一 name 字段
            new_port.name = f"port-{port}"

            # 设为固定 nodePort
            if not svc.spec.type:
                svc.spec.type = "NodePort"
            if svc.spec.type != "NodePort":
                svc.spec.type = "NodePort"
            new_port.node_port = node_port

            existing_ports.append(new_port)
            svc.spec.ports = existing_ports

            core_k8s_client.patch_namespaced_service(name=service_name, namespace=namespace_name, body=svc)
            return {"data": "success", "port": port}
        except Fail:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def delete_port_by_id(self, id: str, port: int):
        try:
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            if not ai_instance_info_db:
                raise Fail(f"ai instance[{id}] is not found", error_message=f" 容器实例[{id}找不到]")

            core_k8s_client = get_k8s_core_client(ai_instance_info_db.instance_k8s_id)
            namespace_name = NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id
            service_name = ai_instance_info_db.instance_real_name

            svc = core_k8s_client.read_namespaced_service(name=service_name, namespace=namespace_name)
            if not svc or not svc.spec:
                raise Fail("service invalid", error_message="Service 无效")

            old_ports = svc.spec.ports or []
            # 新增：如果端口为空或只有一个，不允许删除
            if not old_ports or len(old_ports) <= 1:
                raise Fail("can not delete port: service must have at least one port", error_message="Service 至少需要保留一个端口，无法删除")

            # 查找目标端口的 index
            target_index = None
            for idx, p in enumerate(old_ports):
                if int(getattr(p, 'port', -1)) == int(port):
                    target_index = idx
                    break
            if target_index is None:
                raise Fail("port not found", error_message=f"未找到指定端口: {port}")

            # 用 json patch 删除指定 index 的端口
            patch_operations = [
                {
                    "op": "remove",
                    "path": f"/spec/ports/{target_index}"
                }
            ]
            core_k8s_client.patch_namespaced_service(name=service_name, namespace=namespace_name, body=patch_operations)
            return {"data": "success", "port": port}
        except Fail:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def list_port_by_id(self, id: str, page, page_size):
        try:
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            if not ai_instance_info_db:
                raise Fail(f"ai instance[{id}] is not found", error_message=f" 容器实例[{id}找不到]")

            core_k8s_client = get_k8s_core_client(ai_instance_info_db.instance_k8s_id)
            namespace_name = NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id
            service_name = ai_instance_info_db.instance_real_name or ai_instance_info_db.instance_name

            svc = core_k8s_client.read_namespaced_service(name=service_name, namespace=namespace_name)
            if not svc or not svc.spec:
                return {"status": "success", "data": []}

            k8s_config = AiInstanceSQL.get_k8s_configs_info_by_k8s_id(ai_instance_info_db.instance_k8s_id)
            ports = []
            for p in (svc.spec.ports or []):
                ports.append({
                    "port": int(p.port) if p.port is not None else None,
                    "targetPort": int(p.target_port) if isinstance(p.target_port, int) else p.target_port,
                    "nodePort": int(p.node_port) if getattr(p, 'node_port', None) is not None else None,
                    "protocol": p.protocol,
                    "ip": k8s_config.public_ip if k8s_config else None,
                })

            return {
                "status": "success",
                "data": ports
            }
        except Fail:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def get_jupyter_urls_by_id(self, id: str, service_port: int = 8888, target_port: int = 8888):
        try:
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            if not ai_instance_info_db:
                raise Fail(f"ai instance[{id}] is not found", error_message=f" 容器实例[{id}找不到]")

            core_k8s_client = get_k8s_core_client(ai_instance_info_db.instance_k8s_id)
            namespace_name = NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id
            service_name = ai_instance_info_db.instance_real_name

            # 确保 Service 暴露了 jupyter 端口，如没有则自动新增，并让 k8s 自动分配 nodePort
            svc = core_k8s_client.read_namespaced_service(name=service_name, namespace=namespace_name)
            if not svc or not svc.spec:
                raise Fail("service invalid", error_message="Service 无效")

            node_port_assigned = None
            if svc.spec.ports:
                for p in svc.spec.ports:
                    # 匹配到 8888 的 service_port 或 target_port
                    if (int(p.port or 0) == int(service_port)) or (isinstance(p.target_port, int) and int(p.target_port) == int(target_port)):
                        node_port_assigned = getattr(p, 'node_port', None)
                        if node_port_assigned:
                            node_port_assigned = int(node_port_assigned)
                        break

            # 若未找到，新增一个端口项（不设置 nodePort，交给 k8s 自动分配）
            if node_port_assigned is None:
                new_port = client.V1ServicePort(port=int(service_port), target_port=int(target_port))
                if not svc.spec.type:
                    svc.spec.type = "NodePort"
                if svc.spec.type != "NodePort":
                    svc.spec.type = "NodePort"
                ports = svc.spec.ports or []
                # 避免重复
                for p in ports:
                    if int(p.port or 0) == int(service_port):
                        new_port = None
                        break
                if new_port is not None:
                    ports.append(new_port)
                    svc.spec.ports = ports
                    core_k8s_client.patch_namespaced_service(name=service_name, namespace=namespace_name, body=svc)
                    # 重新获取以拿到自动分配的 nodePort
                    svc = core_k8s_client.read_namespaced_service(name=service_name, namespace=namespace_name)
                    for p in (svc.spec.ports or []):
                        if int(p.port or 0) == int(service_port):
                            node_port_assigned = getattr(p, 'node_port', None)
                            if node_port_assigned:
                                node_port_assigned = int(node_port_assigned)
                            break

            if not node_port_assigned:
                raise Fail("nodePort not assigned", error_message="节点端口尚未分配，请稍后重试")

            # 获取节点 IP 列表
            urls = []
            nodes = k8s_common_operate.list_node(core_k8s_client)
            for n in getattr(nodes, 'items', []) or []:
                addresses = getattr(n.status, 'addresses', []) or []
                node_ip = None
                    # 优先 ExternalIP，其次 InternalIP
                for addr in addresses:
                    if addr.type == 'ExternalIP' and addr.address:
                        node_ip = addr.address
                        break
                if not node_ip:
                    for addr in addresses:
                        if addr.type == 'InternalIP' and addr.address:
                            node_ip = addr.address
                            break
                if node_ip:
                    urls.append(f"http://{node_ip}:{node_port_assigned}")

            return {"data": {"nodePort": node_port_assigned, "urls": urls}}
        except Fail:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def _start_async_check_task(self, core_k8s_client, k8s_id, instance_id, pod_name, namespace):
        """启动后台检查任务"""
        def _run_task():
            loop = None
            try:
                # 创建新的事件循环（每个线程独立）
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # 执行检查任务
                loop.run_until_complete(
                    self._safe_check_pod_status_and_node_name(
                        core_k8s_client,
                        k8s_id,
                        instance_id,
                        pod_name,
                        namespace
                    )
                )
            except Exception as e:
                LOG.error(f"Background task failed: {str(e)}", exc_info=True)
            finally:
                if loop:
                    loop.close()

        # 使用线程池提交任务
        task_executor.submit(_run_task)

    async def _safe_check_pod_status_and_node_name(self, *args):
        """受保护的检查任务"""
        try:
            await self.check_pod_status_node_name_and_update_db(*args)
        except Exception as e:
            LOG.error(f"Pod status check failed: {str(e)}", exc_info=True)

    def convert_cpu_to_core(self, cpu_str):
        """将CPU字符串转换为 核"""
        if cpu_str.endswith('m'):
            return str(float(cpu_str[:-1]) / 1000)
        return cpu_str

    # 单位转换函数
    def convert_memory_to_gb(self, memory_str):
        """将内存字符串转换为 GB"""
        if memory_str.endswith('Ki'):
            return str(float(memory_str[:-2]) / (1024 * 1024))
        elif memory_str.endswith('Mi'):
            return str(float(memory_str[:-2]) / 1024)
        elif memory_str.endswith('Gi'):
            return str(memory_str[:-2])
        return str(float(memory_str) / (1024 * 1024 * 1024))  # 默认假设为字节

    def convert_storage_to_gb(self, storage_str):
        """将存储字符串转换为 GB"""
        if storage_str.endswith('Ki'):
            return str(float(storage_str[:-2]) / (1024 * 1024))
        elif storage_str.endswith('Mi'):
            return str(float(storage_str[:-2]) / 1024)
        elif storage_str.endswith('Gi'):
            return str(storage_str[:-2])
        return str(float(storage_str) / (1024 * 1024 * 1024) ) # 默认假设为字节

# ========== 以下为 k8s node resoource相关接口 ==================================
    def get_k8s_node_resource_statistics(self, k8s_id):
        if not k8s_id:
            raise Fail("k8s id is empty", error_message="K8s ID为空")
        node_resource_list_db = AiInstanceSQL.get_k8s_node_resource_by_k8s_id(k8s_id)
        if not node_resource_list_db:
            LOG.error("")
            return None

        node_resources = []
        for node_resource_db in node_resource_list_db:

            # 转换基础数据
            gpu_total = self.safe_convert(node_resource_db.gpu_total, int)
            gpu_used = self.safe_convert(node_resource_db.gpu_used, int)
            cpu_total = self.safe_convert(node_resource_db.cpu_total)
            cpu_used = self.safe_convert(node_resource_db.cpu_used)
            memory_total = self.safe_convert(node_resource_db.memory_total)
            memory_used = self.safe_convert(node_resource_db.memory_used)
            storage_total = self.safe_convert(node_resource_db.storage_total)
            storage_used = self.safe_convert(node_resource_db.storage_used)

            # 局部函数：处理剩余量
            def calc_remaining(total, used):
                if total is None:
                    return None
                used_val = used if used is not None else 0
                return round(float(total) - float(used_val), 2) if isinstance(total, (int, float)) else total - used_val

            # 构建结果字典
            node_stats = {
                'node_name': node_resource_db.node_name,
                'less_gpu_pod_count': node_resource_db.less_gpu_pod_count,
                'gpu_model': None if not node_resource_db.gpu_model else self.find_key_by_gpu_code(node_resource_db.gpu_model),
                # GPU资源（整数）
                'gpu_total': int(gpu_total) if gpu_total else 0,
                'gpu_used': int(gpu_used) if gpu_used else 0,
                'gpu_remaining': calc_remaining(gpu_total, gpu_used) if gpu_total else 0,
                # CPU资源（浮点数）
                'cpu_total': round(cpu_total, 2),
                'cpu_used': round(cpu_used, 2) if cpu_used else 0,
                'cpu_remaining': calc_remaining(cpu_total, cpu_used),
                # 内存资源（浮点数）
                'memory_total': round(memory_total, 2),
                'memory_used': round(memory_used, 2) if memory_used else 0,
                'memory_remaining': calc_remaining(memory_total, memory_used),
                # 存储资源（浮点数）
                'storage_total': round(storage_total,2),
                'storage_used': round(storage_used, 2) if storage_used else 0,
                'storage_remaining': calc_remaining(storage_total, storage_used)
            }
            node_resources.append(node_stats)

        # 返回所有node资源
        return  node_resources

    def find_key_by_gpu_code(self, gpu_code_value):
        reverse_mapping = {details["gpu_code"]: key for key, details in GPU_CARD_MAPPING.items()}
        return reverse_mapping.get(gpu_code_value)

    """计算单个节点的资源统计"""
    def safe_convert(self, value, convert_type=float):
        """安全转换字符串到数值，失败时返回None"""
        if value is None or str(value).strip() == "":
            return None
        try:
            # 处理带特殊符号的字符串（如"1,024"）
            cleaned_value = str(value).replace(',', '').replace('%', '').strip()
            return convert_type(cleaned_value)
        except (ValueError, TypeError) as e:
            LOG.error(f"Convert failed: {value} to {convert_type.__name__}, error: {str(e)}")
            return None

    def update_node_resources(self, node_resource_db, compute_resource_dict, operation='release'):
        """
        更新节点资源（分配或释放）
        :param node_resource_db: 节点资源数据库对象
        :param compute_resource_dict : 计算资源配置字典
        :param operation: 'allocate' 分配资源, 'release' 释放资源
        :return: 是否成功更新资源
        """
        try:
            operation_factor = 1 if operation == 'allocate' else -1
            print(f"============compute_resource_dict :{compute_resource_dict}")
            # 处理GPU资源（需要型号匹配）
            if ('gpu_model' in compute_resource_dict and 'gpu_count' in compute_resource_dict and
                    compute_resource_dict['gpu_model'] and node_resource_db.gpu_model):
                current_node_gpu = self.safe_float(node_resource_db.gpu_used or '0')
                pod_resource_gpu = self.safe_float(compute_resource_dict['gpu_count'])
                node_resource_db.gpu_used = str(max(0, current_node_gpu + operation_factor * pod_resource_gpu))

            # 处理CPU资源
            if 'compute_cpu' in compute_resource_dict:
                current_node_cpu = self.safe_float(node_resource_db.cpu_used or '0')
                pod_resource_cpu = self.safe_float(compute_resource_dict['compute_cpu'])
                node_resource_db.cpu_used = str(max(0, current_node_cpu + operation_factor * pod_resource_cpu))

            # 处理内存资源
            if 'compute_memory' in compute_resource_dict:
                current_node_memory = self.safe_float(node_resource_db.memory_used or '0')
                pod_resource_memory = self.safe_float(compute_resource_dict['compute_memory'])
                node_resource_db.memory_used = str(max(0, current_node_memory + operation_factor * pod_resource_memory))

            # 处理系统磁盘资源
            if 'system_disk_size' in compute_resource_dict:
                current_node_disk = self.safe_float(node_resource_db.storage_used or '0')
                pod_resource_disk = self.safe_float(compute_resource_dict['system_disk_size'])
                node_resource_db.storage_used = str(max(0, current_node_disk + operation_factor * pod_resource_disk))

            # 更新数据库
            AiInstanceSQL.update_k8s_node_resource(node_resource_db)
            return True

        except Exception as e:
            LOG.error(f"{operation}节点资源失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def safe_float(self, value, default=0.0):
        """安全转换为float类型"""
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def ai_instance_web_ssh(self, instance_id: str):
        ai_instance_db = AiInstanceSQL.get_ai_instance_info_by_id(instance_id)
        if not ai_instance_db:
            raise Fail(f"ai instance[{id}] is not found", error_message=f" 容器实例[{id}找不到]")

        try:
            core_client = get_k8s_core_client(ai_instance_db.instance_k8s_id)
            # 创建k8s exec连接
            exec_command = [
                '/bin/sh',
                '-c',
                'TERM=xterm-256color; export TERM; [ -x /bin/bash ] && ([ -x /usr/bin/script ] && /usr/bin/script -q -c "/bin/bash" /dev/null || exec /bin/bash) || exec /bin/sh'
            ]
            resp = stream(
                core_client.connect_get_namespaced_pod_exec,
                name=ai_instance_db.instance_real_name+"-0",
                namespace=NAMESPACE_PREFIX + ai_instance_db.instance_tenant_id,
                container=None,
                command=exec_command,
                stderr=True, stdin=True,
                stdout=True, tty=True,
                _preload_content=False
            )
            return resp
        except Exception as e:
            LOG.error(f"ai_instance_web_ssh instance_id:{instance_id} fail")
            import traceback
            traceback.print_exc()
            raise e