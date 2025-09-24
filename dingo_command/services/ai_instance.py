# ai实例的service层
import copy
import json
import random
import re
import string
import time
import uuid
from datetime import datetime
from func_timeout import func_timeout, FunctionTimedOut
from functools import wraps, partial

from tenacity import retry, stop_after_attempt, retry_if_exception, wait_fixed
from keystoneclient import client
from math import ceil
from kubernetes.client import V1PersistentVolumeClaim, V1ObjectMeta, V1PersistentVolumeClaimSpec, \
    V1ResourceRequirements, V1PodTemplateSpec, V1StatefulSet, V1LabelSelector, V1Container, V1VolumeMount, V1Volume, \
    V1ConfigMapVolumeSource, V1EnvVar, V1PodSpec, V1StatefulSetSpec, V1ContainerPort, V1Toleration, V1Affinity, \
    V1PodAffinity, \
    V1WeightedPodAffinityTerm, V1PodAffinityTerm, V1LabelSelectorRequirement, V1HostPathVolumeSource, V1SecurityContext
from kubernetes import client
from kubernetes.stream import stream

from dingo_command.api.model.aiinstance import AddPortModel
from dingo_command.common.common import dingo_print
from dingo_command.common.Enum.AIInstanceEnumUtils import AiInstanceStatus, K8sStatus
from dingo_command.common.k8s_common_operate import K8sCommonOperate
from dingo_command.db.models.ai_instance.models import AiInstanceInfo, AccountInfo, AiInstancePortsInfo
from dingo_command.db.models.ai_instance.sql import AiInstanceSQL
from dingo_command.db.models.system.sql import SystemSQL
from dingo_command.services.harbor import HarborService
from dingo_command.services.redis_connection import redis_connection, RedisLock
from dingo_command.utils.constant import CCI_NAMESPACE_PREFIX, RESOURCE_TYPE_KEY, PRODUCT_TYPE_CCI, \
    AI_INSTANCE_PVC_MOUNT_PATH_DEFAULT, \
    APP_LABEL, AI_INSTANCE_CM_MOUNT_PATH_SSHKEY, AI_INSTANCE_CM_MOUNT_PATH_SSHKEY_SUB_PATH, CONFIGMAP_PREFIX, \
    DEV_TOOL_JUPYTER, \
    SAVE_TO_IMAGE_CCI_PREFIX, GPU_POD_LABEL_KEY, GPU_POD_LABEL_VALUE, CCI_STS_PREFIX, CCI_STS_POD_SUFFIX, INGRESS_SIGN, \
    HYPHEN_SIGN, POINT_SIGN, JUPYTER_INIT_MOUNT_NAME, JUPYTER_INIT_MOUNT_PATH, HARBOR_PULL_IMAGE_SUFFIX, \
    CPU_OVER_COMMIT, MIN_CPU_REQUEST, CPU_POD_SLOT_KEY, CCI_SYNC_K8S_NODE_REDIS_KEY, CCI_TIME_OUT_DEFAULT
from dingo_command.utils.customer_thread_pool import queuedThreadPool
from dingo_command.utils.k8s_client import get_k8s_core_client, get_k8s_app_client, get_k8s_networking_client
from dingo_command.services.custom_exception import Fail

k8s_common_operate = K8sCommonOperate()
harbor_service = HarborService()

def _create_retry_decorator():
    """创建支持智能重试判断的装饰器工厂"""

    def is_retryable_error(exception):
        """
        判断传入的异常是否可重试。
        根据你的业务场景和常见的Kubernetes操作错误进行扩充。
        """
        error_message = str(exception).lower()

        # 匹配不可重试的错误（永久性故障）
        non_retryable_keywords = [
            'no such container',  # 容器不存在
            'no such file or directory',  # 文件或目录不存在
            'permission denied',  # 权限不足
            'invalid reference format',  # 镜像名称等引用格式无效
            'syntax error',  # 语法错误
            'quota exceeded',  # 资源配额不足
            'out of memory',  # 内存不足（如果是任务本身需求超出节点容量，重试可能无效）
            # 'resource already exists'  # 资源已存在（如重复创建）
        ]

        for keyword in non_retryable_keywords:
            if keyword in error_message:
                return False  # 不可重试

        # 默认情况（如网络超时、临时不可用等）视为可重试
        return True

    def decorator(func):
        @retry(
            stop=stop_after_attempt(3), # 设置最大尝试次数为2（原始调用1次 + 重试2次）
            wait=wait_fixed(1),   # 重试前等待1秒（可根据需要调整间隔）
            retry=retry_if_exception(is_retryable_error),  # 只重试可重试的异常
            # before_sleep=before_sleep_log(LOG, log.WARNING),  # 重试前打印日志
            reraise=True  # 重试耗尽后抛出原始异常
        )
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator


class AiInstanceService:

    def delete_ai_instance_by_id(self, id):
        ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
        if not ai_instance_info_db:
            dingo_print("ai instance[{id}] is not found")
            return
        # 更新状态为删除中
        ai_instance_info_db.instance_status="DELETING"
        AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)
        # 优先尝试删除 K8s 资源（Service、StatefulSet）
        try:
            core_k8s_client = get_k8s_core_client(ai_instance_info_db.instance_k8s_id)
            app_k8s_client = get_k8s_app_client(ai_instance_info_db.instance_k8s_id)
            networking_k8s_client = get_k8s_networking_client(ai_instance_info_db.instance_k8s_id)
            namespace_name = CCI_NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id
            real_name = ai_instance_info_db.instance_real_name or ai_instance_info_db.instance_name

            try:
                k8s_common_operate.delete_service_by_name(core_k8s_client, real_name, namespace_name)
            except Exception as e:
                dingo_print(f"删除Service失败, name={real_name}, ns={namespace_name}, err={e}")

            try:
                k8s_common_operate.delete_service_by_name(core_k8s_client, real_name + "-" + DEV_TOOL_JUPYTER, namespace_name)
            except Exception as e:
                dingo_print(f"删除 jupyter Service失败, name={real_name}, ns={namespace_name}, err={e}")

            try:
                # 删除 ingress rule
                k8s_common_operate.delete_namespaced_ingress(networking_k8s_client, real_name, namespace_name)
            except Exception as e:
                dingo_print(f"删除ingress资源[{namespace_name}/{real_name}-jupyter]失败: {str(e)}")

            try:
                # 删除 jupyter configMap
                k8s_common_operate.delete_configmap(core_k8s_client, namespace_name, real_name)
            except Exception as e:
                dingo_print(f"删除jupyter configMap资源[{namespace_name}/{real_name}]失败: {str(e)}")

            try:
                # 删除镜像库中保存的关机镜像
                k8s_configs_db = AiInstanceSQL.get_k8s_configs_info_by_k8s_id(ai_instance_info_db.instance_k8s_id)
                harbor_address = k8s_configs_db.harbor_address
                image_name = SAVE_TO_IMAGE_CCI_PREFIX + ai_instance_info_db.id
                project_name = self.extract_project_and_image_name(harbor_address)
                delete_project_repository_response = harbor_service.delete_custom_projects_images(project_name, image_name)
                dingo_print(f"ai instance [{id}] project_name:{project_name}, image_name:{image_name}, delete_project_repository_response:{delete_project_repository_response}")
            except Exception as e:
                dingo_print(f"删除容器实例[{id}]的关机镜像失败: {e}")

            # 删除metallb的默认端口
            AiInstanceSQL.delete_ai_instance_ports_info_by_instance_id(id)

            try:
                k8s_common_operate.delete_sts_by_name(app_k8s_client, real_name, namespace_name)
            except Exception as e:
                dingo_print(f"删除StatefulSet失败, name={real_name}, ns={namespace_name}, err={e}")
                raise e
        except Exception as e:
            dingo_print(f"获取 K8s 客户端失败或删除资源异常: {e}")
            import traceback
            traceback.print_exc()
            raise e
        finally:
            self.get_or_set_update_k8s_node_resource_redis()

        # 删除数据库记录
        AiInstanceSQL.delete_ai_instance_info_by_id(id)
        return {"data": "success", "uuid": id}

    # ================= 账户相关 =================
    def create_ai_account(self, account: str, vip: str, metallb_ip: str):
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
                vip=str(vip),
                metallb_ip=str(metallb_ip)
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

    def update_ai_account_by_id(self, id: str, account: str = None, vip: str = None, metallb_ip: str = None):
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
            if metallb_ip:
                existed.metallb_ip = str(metallb_ip)

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
            with RedisLock(redis_connection.redis_master_connection, f"ai-instance-image-{id}", expire_time=CCI_TIME_OUT_DEFAULT) as lock:
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
                    queuedThreadPool.submit(partial(self.async_save_cci_to_image,
                                                    id, core_k8s_client, nerdctl_api_pod,
                                                    sts_pod_info['container_id'], image_registry, harbor_username, harbor_password, image_name, image_tag
                                                    ))

                    return {
                        "status": "accepted",
                        "message": "容器实例保存操作已开始异步执行",
                        "instance_id": id,
                        "image_name": f"{image_name}:{image_tag}"
                    }

                else:
                    dingo_print(f"未获取到锁{id}")
                    raise Fail(f"Ai instance [{id}] is saving, not allow to operation")

        except Exception as e:
            # 记录日志并重新抛出异常
            dingo_print(f"Failed to start save operation for instance {id}: {str(e)}")
            raise Fail(f"Failed to start save operation: {str(e)}")


    def stop_save_cci_to_image_task(self, id):
        """启动后台检查任务"""
        try:
            start_time = datetime.now()
            while True:
                try:
                    # 使用 func_timeout 来执行方法，设置单次执行超时时间为15秒
                    func_timeout(CCI_TIME_OUT_DEFAULT, self.stop_cci_to_save_image, args=(id,))
                except FunctionTimedOut:
                    dingo_print(f"stop_cci_to_save_image single execution timed out after {CCI_TIME_OUT_DEFAULT} seconds!")
                    # 可以选择跳出循环或进行其他处理
                    break
                except Exception as e:
                    # 处理其他可能的异常
                    dingo_print(f"stop_cci_to_save_image ai instance {id} execution occurred an error occurred: {e}")
                    break

                # 方法执行完后，立即检查总耗时（包括方法执行时间和之前所有循环的耗时）
                current_total_seconds = (datetime.now() - start_time).total_seconds()
                if current_total_seconds >= CCI_TIME_OUT_DEFAULT:
                    error_msg = f"stop save cci to image exec timeout {CCI_TIME_OUT_DEFAULT}"
                    raise Exception(error_msg)  # 建议使用具体的异常类型，而非 raise error_msg

                # 如果还没超时，则等待5秒
                time.sleep(5)

        except Exception as e:
            dingo_print(
                f"{time.strftime('%Y-%m-%d %H:%M:%S')} Background task stop_save_cci_to_image_task failed or timeout for instance {id}: {str(e)}")
            try:
                ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
                if ai_instance_info_db:
                    ai_instance_info_db.instance_status = AiInstanceStatus.ERROR.name
                    ai_instance_info_db.instance_real_status = K8sStatus.ERROR.value
                    ai_instance_info_db.error_msg = str(e)
                    AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)
                    # 副本数改成0
                    self.set_k8s_sts_replica_by_instance_id(id, 0)
            except Exception as inner_e:
                dingo_print(f"Error during exception handling for instance {id}: {inner_e}")
        finally:
            self.get_or_set_update_k8s_node_resource_redis()
            dingo_print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} Task for instance {id} has finished (success, timeout, or error), thread should be released.")


    def sava_ai_instance_to_image_process_status(self, id):
        """
        异步保存AI实例为镜像（立即返回，实际操作在后台执行）
        """
        try:
            redis_key = SAVE_TO_IMAGE_CCI_PREFIX + id
            value = redis_connection.get_redis_by_key(redis_key)
            if value:
                return {
                    "instance_id": id,
                    "process_status": "Saving",
                    "image": value
                }

        except Exception as e:
            dingo_print(f"Failed to start save operation for instance {id}: {str(e)}")
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
            ai_instance_info_db.instance_real_name + CCI_STS_POD_SUFFIX,
            CCI_NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id
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

    def async_save_cci_to_image(self, id, core_k8s_client, nerdctl_api_pod,
                                      clean_container_id, harbor_address, harbor_username, harbor_password, image_name, image_tag):
        """
        实际的异步保存操作（受分布式锁保护）
        """

        # 存入redis，镜像推送完成标识
        redis_key = SAVE_TO_IMAGE_CCI_PREFIX + id
        try:
            redis_connection.set_redis_by_key_with_expire(redis_key, f"{image_name}:{image_tag}", CCI_TIME_OUT_DEFAULT)

            # 1. Harbor登录
            self._harbor_login(core_k8s_client, nerdctl_api_pod, harbor_address, harbor_username, harbor_password)

            # 2. Commit操作
            image = f"{harbor_address}/{image_name}:{image_tag}"
            dingo_print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ai instance[{id}] commit image container ID: {clean_container_id}, image_tag: [{image_name}:{image_tag}] start")
            self._commit_container(
                core_k8s_client, nerdctl_api_pod, clean_container_id, image
            )
            dingo_print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ai instance[{id}] commit image container ID: {clean_container_id}, image_tag: [{image_name}:{image_tag}] finished, start push image")

            # 3. Push操作
            self._push_image(core_k8s_client, nerdctl_api_pod, image)
            # 判断是否完成标识
            redis_connection.set_redis_by_key_with_expire(redis_key + "_flag", "true", 10)
            dingo_print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ai instance[{id}] push image container ID: {clean_container_id}, image_tag: [{image_name}:{image_tag}] finished")
        except Exception as e:
            dingo_print(f"Async save operation failed for instance {id}: {str(e)}")
            raise e
        finally:
            redis_connection.delete_redis_key(redis_key)
            self.get_or_set_update_k8s_node_resource_redis()

    def _execute_k8s_command(self, core_k8s_client, pod_name, namespace, command):
        """异步执行K8s命令的辅助函数"""
        resp = None
        try:
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
        except Exception as  e:
            dingo_print(f"exec k8s pod {namespace}/{pod_name}  command {command} failed: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if resp is not None:
                resp.close() #


    def _harbor_login(self, core_k8s_client, nerdctl_api_pod, harbor_address, harbor_username, harbor_password):
        """Harbor登录"""
        harbor_login_command = [
            'nerdctl', 'login',
            '-u', harbor_username,
            '-p', harbor_password,
            harbor_address,
            '--insecure-registry'
        ]

        returncode, output = self._execute_k8s_command(
            core_k8s_client, nerdctl_api_pod['name'], nerdctl_api_pod['namespace'], harbor_login_command
        )

        if returncode != 0:
            dingo_print(f"Harbor login returncode:{returncode}, failed: {output}")
            raise Exception(f"Harbor login returncode:{returncode}, failed: {output}")

    @_create_retry_decorator()  # 应用装饰器工厂
    def _commit_container(self, core_k8s_client, nerdctl_api_pod, clean_container_id, image_name):
        """执行commit操作"""
        commit_command = [
            'nerdctl', 'commit', clean_container_id, image_name,
            '--pause=true', '--namespace', 'k8s.io', '--insecure-registry', '--compression=zstd'
        ]
        dingo_print(f"commit_command: {commit_command}")
        returncode, output = self._execute_k8s_command(
            core_k8s_client, nerdctl_api_pod['name'], nerdctl_api_pod['namespace'], commit_command
        )

        if returncode != 0:
            error_msg = f"Container id {clean_container_id} Commit returncode:{returncode}, failed: {output}"
            dingo_print(error_msg)
            # WARN[0000] Image lacks label "nerdctl/platform", assuming the platform to be "linux/amd64"
            if "nerdctl/platform" in output:
                return output
            raise Exception(error_msg)
            # 成功则返回输出
        return output

    @_create_retry_decorator()
    def _push_image(self, core_k8s_client, nerdctl_api_pod, image_name):
        """执行push操作"""
        push_command = [
            'nerdctl', 'push', image_name,
            '--namespace', 'k8s.io', '--insecure-registry'
        ]
        dingo_print(f"push_command: {push_command}")
        returncode, output = self._execute_k8s_command(
            core_k8s_client, nerdctl_api_pod['name'], nerdctl_api_pod['namespace'], push_command
        )

        if returncode != 0:
            error_msg = f"Image {image_name} Push returncode:{returncode}, failed: {output}"
            dingo_print(error_msg)
            raise Exception(error_msg)

        return  output

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
        temp['pod_name'] = r.instance_real_name + CCI_STS_POD_SUFFIX
        temp["instance_status"] = r.instance_status
        temp["instance_region_id"] = r.instance_region_id
        temp["instance_k8s_id"] = r.instance_k8s_id
        temp["instance_user_id"] = r.instance_user_id
        temp["instance_tenant_id"] = r.instance_tenant_id
        if r.instance_tenant_id: 
            temp["namespace"] = CCI_NAMESPACE_PREFIX + r.instance_tenant_id
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
        temp["instance_start_time"] = r.instance_start_time
        temp["instance_description"] = r.instance_description
        temp["ssh_root_password"] = r.ssh_root_password
        temp["product_code"] = r.product_code
        return temp

    def create_ai_instance(self, ai_instance):
        try:
            # 参数校验
            self._validate_ai_instance_parameters(ai_instance)
            # 初始化客户端
            self._initialize_clients(ai_instance.k8s_id)
            # 准备命名空间
            namespace_name = self._prepare_namespace(ai_instance)
            # 镜像全路径。格式：  域名/项目/镜像名+tag
            image_pull = ai_instance.image
            harbor_address = image_pull.split("/")[0]
            dingo_print(f"create_ai_instance harbor_address:{harbor_address}")
            k8s_configs_db = AiInstanceSQL.get_k8s_configs_info_by_k8s_id(ai_instance.k8s_id)
            # 创建私有镜像默认拉取秘钥
            k8s_common_operate.create_docker_registry_secret(self.core_k8s_client, namespace_name, namespace_name + HARBOR_PULL_IMAGE_SUFFIX,
                                                             harbor_address, k8s_configs_db.harbor_username, k8s_configs_db.harbor_password)
            # 设置默认服务账号的harbor 秘钥
            k8s_common_operate.patch_default_service_account(self.core_k8s_client, namespace_name, namespace_name + HARBOR_PULL_IMAGE_SUFFIX)
            # 转换数据结构
            ai_instance_db = self._convert_to_db_model(ai_instance)

            if ai_instance.instance_config.replica_count == 1:
                # 单副本场景
                return self._create_single_instance(ai_instance, ai_instance_db, namespace_name)
            else:
                # 多副本场景
                return self._create_multiple_instances(ai_instance, ai_instance_db, namespace_name)
        except Exception as e:
            dingo_print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} Failed to create AI instance: {e}")
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
        namespace_name = CCI_NAMESPACE_PREFIX + ai_instance.tenant_id

        if not k8s_common_operate.check_ai_instance_ns_exists(self.core_k8s_client, namespace_name):
            k8s_common_operate.create_ai_instance_ns(self.core_k8s_client, namespace_name)
            dingo_print(f"Created namespace: {namespace_name}")

        return namespace_name

    def _convert_to_db_model(self, ai_instance) -> AiInstanceInfo:
        ai_instance_info_db = AiInstanceInfo(
            instance_name=ai_instance.name,
            instance_status="READY",  # 默认状态，表示准备创建
            product_code=ai_instance.product_code,
            instance_region_id=ai_instance.region_id,
            instance_k8s_id=ai_instance.k8s_id,
            instance_user_id=ai_instance.user_id,
            is_manager=ai_instance.is_manager,
            instance_tenant_id=ai_instance.tenant_id,
            instance_image=ai_instance.image,
            stop_time=datetime.fromtimestamp(ai_instance.stop_time) if ai_instance.stop_time else None,
            auto_delete_time=datetime.fromtimestamp(ai_instance.auto_delete_time) if ai_instance.auto_delete_time else None,
            instance_config=json.dumps(ai_instance.instance_config.dict()) if ai_instance.instance_config else None,
            instance_volumes=json.dumps(ai_instance.volumes.dict()) if ai_instance.volumes else None,
            instance_envs=json.dumps(ai_instance.instance_envs) if ai_instance.instance_envs else None,
            instance_description=ai_instance.description,
            ssh_root_password=''.join(random.choices(string.ascii_letters + string.digits, k=10))
        )
        return ai_instance_info_db

    def _create_single_instance(self, ai_instance, ai_instance_db, namespace_name):
        """创建单个实例"""
        resource_config = self._prepare_resource_config(ai_instance.instance_config)

        # 设置实例ID
        ai_instance_db.id = ai_instance.instance_id or uuid.uuid4().hex
        # 设置实例k8s上真实名称
        ai_instance_db.instance_real_name = CCI_STS_PREFIX + ai_instance_db.id
        # 保存数据库信息
        AiInstanceSQL.save_ai_instance_info(ai_instance_db)

        # 启异步任务执行创建k8s资源及检查pod状态, 提交任务时使用这个包装函数
        queuedThreadPool.submit(partial(self.create_check_pod_status_node_name_and_update_db, ai_instance, ai_instance_db, namespace_name, resource_config))

        return [self.assemble_ai_instance_return_result(ai_instance_db)]

    def _create_multiple_instances(self, ai_instance, ai_instance_db, namespace_name):
        """创建多个实例副本"""
        resource_config = self._prepare_resource_config(ai_instance.instance_config)
        results = []

        for i in range(ai_instance.instance_config.replica_count):
            instance_copy = copy.deepcopy(ai_instance_db)
            instance_result = self._assemble_and_create_instance(
                ai_instance, instance_copy, namespace_name, resource_config
            )

            # self._start_async_check_task(
            #     self.core_k8s_client,
            #     ai_instance_db.instance_k8s_id,
            #     instance_result.id,
            #     f"{instance_result.instance_real_name}{CCI_STS_POD_SUFFIX}",
            #     CCI_NAMESPACE_PREFIX + ai_instance_db.instance_tenant_id
            # )

            results.append(self.assemble_ai_instance_return_result(instance_result))

        return results

    def _prepare_resource_config(self, instance_config):
        resource_limits = []
        resource_requests = []
        node_selector_gpu = {}
        toleration_gpus = []

        if instance_config.gpu_model:
            gpu_card_info = AiInstanceSQL.get_gpu_card_info_by_gpu_model_display(instance_config.gpu_model)
            if not gpu_card_info:
                raise Fail(f"GPU card mapping not found for model: {instance_config.gpu_model}")

            resource_limits = {'cpu': int(instance_config.compute_cpu), 'memory': instance_config.compute_memory + "Gi",
                               gpu_card_info.gpu_key: instance_config.gpu_count, 'ephemeral-storage': f"{int(instance_config.system_disk_size) * 1024 + 100}Mi"}
            # 定义资源requests
            resource_requests = {'cpu': int(instance_config.compute_cpu), 'memory': instance_config.compute_memory + "Gi",
                               gpu_card_info.gpu_key: instance_config.gpu_count, 'ephemeral-storage': "1024Mi"}
            # node_selector_gpu['nvidia.com/gpu.product'] = gpu_card_info.gpu_node_label
            # 容忍度
            # toleration_gpus.append(V1Toleration(
            #     key=gpu_card_info.gpu_node_label,
            #     operator="Exists",
            #     effect="NoSchedule"
            # ))
        elif instance_config.compute_cpu:
            # 定义资源requests
            resource_requests = {'cpu': self.safe_divide(instance_config.compute_cpu),
                                 'memory': instance_config.compute_memory + "Gi",
                                 'ephemeral-storage': "1024Mi"}
            resource_limits= {CPU_POD_SLOT_KEY: int(instance_config.compute_cpu),
                              "cpu": int(instance_config.compute_cpu),
                              'memory': instance_config.compute_memory + "Gi",
                              'ephemeral-storage': f"{int(instance_config.system_disk_size) * 1024 + 100}Mi"}

        return {
            'resource_limits': resource_limits,
            'resource_requests': resource_requests,
            'node_selector_gpu': node_selector_gpu,
            'toleration_gpus': toleration_gpus,
            "system_disk_size": instance_config.system_disk_size
        }

    def _assemble_and_create_instance(self, ai_instance, ai_instance_db, namespace_name, resource_config):
        """组装并创建实例"""
        # 设置实例ID
        ai_instance_db.id = ai_instance.instance_id or uuid.uuid4().hex
        # 设置实例k8s上真实名称
        ai_instance_db.instance_real_name = CCI_STS_PREFIX + ai_instance_db.id

        # 创建K8s资源
        self._create_cci_k8s_resources(ai_instance, ai_instance_db, namespace_name, resource_config)

        return ai_instance_db

    def _create_cci_k8s_resources(self, ai_instance, ai_instance_db, namespace_name, resource_config):
        """创建K8s相关资源"""
        # 获取服务IP
        service_ip, dns_suffix, is_account = self._get_service_ip(ai_instance_db)

        # 规则： host: ingress-${zone_id}.${region_id}.alayanew.com # 这里的region_id和zone_id对应的就是下一步的值，每一个cci实例的ingress都是这个值
        # 生产环境域名后缀： alayanew.com； 测试环境：zetyun.cn
        host_domain = f"{INGRESS_SIGN}{HYPHEN_SIGN}{ai_instance_db.instance_k8s_id}{POINT_SIGN}{ai_instance_db.instance_region_id}{POINT_SIGN}{dns_suffix}"
        # 这个path对应的就是注入到pod的环境变量中的path. 规则： /notebook/jupyter/{region_id}/{zone_id}/{instance_id{user_namespace}/{cci_pod_name}  # HTTPS 路径
        nb_prefix = f"/notebook/jupyter/{ai_instance_db.instance_region_id}/{ai_instance_db.instance_k8s_id}/{ai_instance_db.id}/{namespace_name}/{ai_instance_db.instance_real_name}{CCI_STS_POD_SUFFIX}"

        # 1、创建sshkey的configmap（如果有就跳过，没有就创建）
        configmap_name = CONFIGMAP_PREFIX + ai_instance.user_id
        k8s_common_operate.create_ns_configmap(
            self.core_k8s_client, namespace_name, configmap_name, ai_instance_db, {"authorized_keys": ""}
        )

        self._wait_for_resource(self.core_k8s_client, self.app_k8s_client, self.networking_k8s_client, namespace_name, configmap_name, client.V1ConfigMap)

        # 2、挂载jupyter config
        k8s_common_operate.create_jupyter_configmap(self.core_k8s_client, namespace_name,
                                                    ai_instance_db.instance_real_name, nb_prefix, ai_instance_db.ssh_root_password)
        self._wait_for_resource(self.core_k8s_client, self.app_k8s_client, self.networking_k8s_client, namespace_name, ai_instance_db.instance_real_name, client.V1ConfigMap)

        # 3、创建jupter的service服务，包括默认端口8888
        k8s_common_operate.create_cci_jupter_service(
            self.core_k8s_client, namespace_name, ai_instance_db.instance_real_name
        )
        self._wait_for_resource(self.core_k8s_client, self.app_k8s_client, self.networking_k8s_client,
                                namespace_name, ai_instance_db.instance_real_name  + "-" + DEV_TOOL_JUPYTER, client.V1Service)

        # 端口：22、9001、9002 port需实时获取,防止冲突
        available_ports, available_ports_map = self.find_ai_instance_available_ports(instance_id=ai_instance_db.id, is_add=False, )
        if len(available_ports) < 3:
            dingo_print(f"Not enough available ports or ai instance {ai_instance_db.id} not get redis lock")
            raise Fail(f"Not enough available ports or ai instance {ai_instance_db.id} not get redis lock ", error_message="无足够可用端口")
        dingo_print(f"ai instance [{ai_instance_db.id}] available_ports:{available_ports}")

        try:
            # 4、创建metallb的服务，包括默认端口22、9001、9002
            k8s_common_operate.create_cci_metallb_service(
                self.core_k8s_client, namespace_name, ai_instance_db.instance_real_name, service_ip, is_account, available_ports_map
            )
            self._wait_for_resource(self.core_k8s_client, self.app_k8s_client, self.networking_k8s_client,
                                    namespace_name, ai_instance_db.instance_real_name, client.V1Service)

        except Exception as e:
            dingo_print(f"create cci pod fail:{e}")
            import traceback
            traceback.print_exc()
            AiInstanceSQL.delete_ai_instance_ports_info_by_instance_id(ai_instance_db.id)
            raise e

        # 5、创建ingress 规则，端口是8888
        k8s_common_operate.create_cci_ingress_rule(
            self.networking_k8s_client, namespace_name, ai_instance_db.instance_real_name,
            host_domain, nb_prefix
        )
        self._wait_for_resource(self.core_k8s_client, self.app_k8s_client, self.networking_k8s_client,
                                namespace_name, f"{ai_instance_db.instance_real_name}-{INGRESS_SIGN}", client.V1Ingress)

        # 6、创建StatefulSet
        sts_data = self._assemble_sts_data(ai_instance, ai_instance_db, namespace_name, resource_config, nb_prefix)
        k8s_common_operate.create_sts_pod(self.app_k8s_client, namespace_name, sts_data)


    def _wait_for_resource(self, core_v1_client, app_v1_client, networking_v1_client, namespace, name, resource_type, timeout=60):
        """等待资源就绪"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                if resource_type == client.V1ConfigMap:
                    core_v1_client.read_namespaced_config_map(name, namespace)
                    return
                elif resource_type == client.V1Service:
                    svc = core_v1_client.read_namespaced_service(name, namespace)
                    if svc.spec.cluster_ip:  # 检查 Service 已分配 ClusterIP
                        return
                elif resource_type == client.V1StatefulSet:
                    sts = app_v1_client.read_namespaced_stateful_set(name, namespace)
                    if sts.status.ready_replicas == sts.spec.replicas:
                        return
                elif resource_type == client.V1Ingress:
                    networking_v1_client.read_namespaced_ingress(name, namespace)
                    return
            except Exception as e:
                time.sleep(2)
                dingo_print(f"{namespace}/{name} resource_type:{resource_type} fail: {e}")
        raise TimeoutError(f"Resource {name} not ready in {timeout}s")


    def find_ai_instance_available_ports(self,instance_id, start_port=30001, end_port=65535, count=3, is_add: bool=False, target_port: int=None):
        """查找从start_port开始的最小count个可用端口"""
        with RedisLock(redis_connection.redis_master_connection, lock_name=f"cci-metallb-port") as lock:
            if lock:
                available_ports = []
                current_port = start_port
                ai_instance_ports_db = AiInstanceSQL.list_ai_instance_ports_info()
                ports_db = [ports.instance_svc_port for ports in ai_instance_ports_db] if ai_instance_ports_db else []
                while current_port <= end_port and len(available_ports) < count:
                    if current_port not in ports_db:
                        available_ports.append(current_port)
                    current_port += 1

                if not available_ports:
                    dingo_print("ai instance {instance_id} available port is empty")
                    raise Fail(f"ai instance {instance_id} available port is empty")
                available_ports_map = {}
                if is_add == False:
                    available_ports_map = {
                        "22": available_ports[0] if len(available_ports) > 0 else None,
                        "9001": available_ports[1] if len(available_ports) > 1 else None,
                        "9002": available_ports[2] if len(available_ports) > 2 else None,
                    }

                    # 22、9001、9002默认端口的metallb配置
                    ports = []
                    for port_key, port_value in available_ports_map.items():
                        port = AiInstancePortsInfo(
                            id=uuid.uuid4().hex,
                            instance_id=instance_id,
                            instance_svc_target_port=int(port_key),
                            instance_svc_port=port_value
                        )
                        ports.append(port)
                    AiInstanceSQL.save_ai_instance_ports_info(ports)
                else:
                    port = AiInstancePortsInfo(
                        id=uuid.uuid4().hex,
                        instance_id=instance_id,
                        instance_svc_target_port=int(target_port),
                        instance_svc_port=available_ports[0]
                    )
                    AiInstanceSQL.save_ai_instance_ports_info([port])

                return available_ports, available_ports_map


    def _get_service_ip(self, ai_instance_db):
        """获取服务IP地址"""
        k8s_configs_db = AiInstanceSQL.get_k8s_configs_info_by_k8s_id(ai_instance_db.instance_k8s_id)
        # 是否为大客户
        is_account = False
        account_vip_db = AiInstanceSQL.get_account_info_by_account(ai_instance_db.instance_tenant_id)
        if account_vip_db:
            is_account = True
            return account_vip_db.vip, k8s_configs_db.dns_suffix, is_account

        return k8s_configs_db.metallb_ip, k8s_configs_db.dns_suffix, is_account

    def _assemble_sts_data(self, ai_instance, ai_instance_db, namespace_name, resource_config, nb_prefix):
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
        resource_requests = resource_config['resource_requests']
        node_selector_gpu = resource_config['node_selector_gpu']
        toleration_gpus = resource_config['toleration_gpus']

        # 环境变量处理
        env_vars_dict = json.loads(ai_instance_db.instance_envs) if ai_instance_db.instance_envs else {}
        env_vars_dict['NB_PREFIX'] = nb_prefix
        if "JUPYTER_TOKEN" not in env_vars_dict.keys():
            env_vars_dict['JUPYTER_TOKEN'] = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        env_list = [
            V1EnvVar(name=key, value=str(value))
            for key, value in env_vars_dict.items()
        ]


        # 准备Volume和VolumeMount
        volume_mounts = [
            V1VolumeMount(
                name=JUPYTER_INIT_MOUNT_NAME,  # 卷名称，需与下面定义的卷匹配
                mount_path=JUPYTER_INIT_MOUNT_PATH,  # 容器内的挂载路径
                read_only = True # 将此挂载设置为只读
            )
        ]
        pod_volumes = [
            V1Volume(
                name=JUPYTER_INIT_MOUNT_NAME,
                host_path= V1HostPathVolumeSource(
                    path="/" + JUPYTER_INIT_MOUNT_NAME,  # 宿主机上的路径
                    type="DirectoryOrCreate"  # 类型：如果目录不存在则创建
                )
            )
        ]

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

        pod_security_context = V1SecurityContext(
            run_as_user=0, # 指定容器内的进程以 root 用户（UID 0）的身份运行。
            run_as_group=0 # 指定容器内的进程以 root 用户组（GID 0）的身份运行
        )
        container_security_context = V1SecurityContext(
            run_as_user=0, # 指定容器内的进程以 root 用户（GID 0）的身份运行
            run_as_group=0 # 指定容器内的进程以 root 用户组（GID 0）的身份运行
        )

        # 定义容器
        container = V1Container(
            name=ai_instance_db.instance_real_name,  # 使用实例的真实名称
            image=ai_instance.image,
            # image_pull_policy="Always",
            security_context=container_security_context,
            env=env_list,
            env_from=[
                client.V1EnvFromSource(
                    config_map_ref=client.V1ConfigMapEnvSource(
                        name=ai_instance_db.instance_real_name
                    )
                )
            ],
            ports=[V1ContainerPort(container_port=22), V1ContainerPort(container_port=8888), V1ContainerPort(container_port=9001), V1ContainerPort(container_port=9002)],  # 固定端口
            resources=V1ResourceRequirements(
                requests=resource_requests,
                limits=resource_limits
            ),
            volume_mounts=volume_mounts,
            command=["/anc-init/script/anc-init"],
        )

        # 亲和性
        # affinity = self.create_affinity(node_selector_gpu)
        # pod标签
        pod_template_labels = self.build_pod_template_labels(ai_instance_db, ai_instance_db.product_code, resource_limits)

        # 定义Pod模板
        template = V1PodTemplateSpec(
            metadata=V1ObjectMeta(
                labels=pod_template_labels,
                annotations={"dc.com/quota.xfs.size": f"{ai_instance.instance_config.system_disk_size}g"}
            ),
            spec=V1PodSpec(
                # node_name=self.choose_k8s_node(ai_instance_db.instance_k8s_id,
                #                                int(ai_instance.instance_config.compute_cpu),
                #                                int(ai_instance.instance_config.compute_memory),
                #                                int(ai_instance.instance_config.system_disk_size),
                #                                self.find_gpu_key_by_display(ai_instance.instance_config.gpu_model),
                #                                ai_instance.instance_config.gpu_count),
                scheduler_name = "volcano",
                containers=[container],
                termination_grace_period_seconds = 5,
                security_context=pod_security_context,
                volumes=pod_volumes,
                # node_selector=node_selector_gpu,  # 使用传入的GPU节点选择器
                # tolerations=toleration_gpus,  # 使用传入的GPU容忍度
                # affinity=affinity
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

            ai_instance_info_db = self.get_and_validate_instance(id)

            # 更新开机时间和开机中状态
            ai_instance_info_db.instance_start_time = datetime.fromtimestamp(datetime.now().timestamp())
            ai_instance_info_db.instance_status = AiInstanceStatus.STARTING.name
            ai_instance_info_db.instance_real_status = K8sStatus.PENDING.value
            AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)

            # 获取k8s客户端
            app_k8s_client = get_k8s_app_client(ai_instance_info_db.instance_k8s_id)
            core_k8s_client = get_k8s_core_client(ai_instance_info_db.instance_k8s_id)

            # 命名空间名称与实例名
            namespace_name = CCI_NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id
            real_name = ai_instance_info_db.instance_real_name

            # 获取最新的configmap的信息
            configmap_name = CONFIGMAP_PREFIX + ai_instance_info_db.instance_user_id
            k8s_common_operate.create_ns_configmap(
                core_k8s_client, namespace_name, configmap_name, ai_instance_info_db,
                {"authorized_keys": ""}
            )

            # 原sts 数据
            existing_sts = k8s_common_operate.read_sts_info(app_k8s_client, real_name, namespace_name)

            if request and request.instance_config:
                resource_config = self._prepare_resource_config(request.instance_config)
            else:
                resource_config = self._prepare_resource_config(json.loads(ai_instance_info_db.instance_config))

            image_name_temp = SAVE_TO_IMAGE_CCI_PREFIX + id
            if request and request.image:
                image_name = request.image
            else:
                project_name = None
                harbor_address, harbor_username, harbor_password = self.get_harbor_info(
                    ai_instance_info_db.instance_k8s_id)
                if harbor_address.endswith('/'):
                    image_name = harbor_address + image_name_temp + ":latest"
                    project_name = harbor_address.rstrip('/').split('/')[-1]
                else:
                    image_name = harbor_address + "/" + image_name_temp + ":latest"
                    project_name = harbor_address.split('/')[-1]

                # 判断是否有保存的镜像存在，不存在用初始镜像
                if not self._check_image_exists(core_k8s_client, image_name_temp, project_name):
                    image_name = ai_instance_info_db.instance_image

            dingo_print(f"Start ai instance id: [{id}] image_name: {image_name}")

            updated_sts = self.build_updated_sts(
                existing_sts, resource_config, image_name, ai_instance_info_db, request
            )

            # 开机操作
            k8s_common_operate.replace_statefulset(app_k8s_client, real_name, namespace_name, updated_sts)

            # 设置下发参数
            if request and request.product_code:
                ai_instance_info_db.product_code = request.product_code
            if request and request.instance_config:
                ai_instance_info_db.instance_config = json.dumps(request.instance_config.dict())
            ai_instance_info_db.instance_image = image_name
            ai_instance_info_db.error_msg = None
            AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)


            # 启异步任务检查pod状态, 提交任务时使用这个包装函数
            queuedThreadPool.submit(
                partial(self.start_cci_check_pod_status_node_name_and_update_db,  core_k8s_client,
                                                       ai_instance_info_db.id,
                                                       f"{ai_instance_info_db.instance_real_name}-0",
                                                       CCI_NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id))
            return {"id": id, "status": ai_instance_info_db.instance_status}
        except Exception as e:
            import traceback
            traceback.print_exc()
            # 回滚数据
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            ai_instance_info_db.instance_start_time = None
            ai_instance_info_db.instance_status = AiInstanceStatus.STOPPED.name
            ai_instance_info_db.instance_real_status = None
            ai_instance_info_db.error_msg = e
            AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)
            raise e

    def _check_image_exists(self, core_k8s_client, image_name, project_name):
        """检查镜像是否存在"""
        try:
            result = harbor_service.get_custom_projects_images(project_name)
            if result["status"]:
                images = result["data"]
                for image in images:
                    if image['repository_name'] == image_name:
                        for tag in image['tags_list']:
                            if tag['tag_name'] == "latest":
                                dingo_print(f"镜像 {image_name}:latest 存在")
                                return True
            else:
                dingo_print(f"获取镜像列表失败: {result['message']}")
                return False

            return False
        except Exception as e:
            dingo_print(f"Error checking image existence: {str(e)}")
            return False

    def get_and_validate_instance(self, instance_id):
        ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(instance_id)
        if not ai_instance_info_db:
            raise Fail(f"ai instance[{instance_id}] is not found", error_message=f"容器实例[{instance_id}找不到]")

        # 检查实例状态，只有 stopped 状态的实例才能开机
        if ai_instance_info_db.instance_status != AiInstanceStatus.STOPPED.name and ai_instance_info_db.instance_status != AiInstanceStatus.ERROR.name:
            raise Fail(f"ai instance[{instance_id}] status is {ai_instance_info_db.instance_status}, cannot start",
                       error_message=f" 容器实例[{instance_id}]状态为{ai_instance_info_db.instance_status}，无法开机")

        return ai_instance_info_db

    def build_updated_sts(self, existing_sts, resource_config, image_name, ai_instance_info_db, request):
        """构建需要更新的StatefulSet配置"""
        # 提取资源配置
        resource_limits = resource_config.get('resource_limits', {})
        resource_requests = resource_config.get('resource_requests', {})
        node_selector_gpu = resource_config.get('node_selector_gpu', {})
        toleration_gpus = resource_config.get('toleration_gpus', [])
        system_disk_size = resource_config.get('system_disk_size', 50)

        # 创建亲和性配置
        # affinity = self.create_affinity(node_selector_gpu)

        # 构建Pod模板标签
        pod_template_labels = self.build_pod_template_labels(ai_instance_info_db, request.product_code if request and request.product_code else ai_instance_info_db.product_code, resource_limits)

        # 更新existing_sts的各个字段
        existing_sts.metadata.resource_version = None
        existing_sts.spec.replicas = 1
        existing_sts.spec.template.metadata = V1ObjectMeta(labels=pod_template_labels, annotations = {"dc.com/quota.xfs.size": f"{system_disk_size}g"})
        existing_sts.spec.template.spec.containers[0].name = ai_instance_info_db.instance_real_name
        existing_sts.spec.template.spec.containers[0].image = image_name
        existing_sts.spec.template.spec.containers[0].image_pull_policy = "Always"
        if resource_limits:
            existing_sts.spec.template.spec.containers[0].resources = V1ResourceRequirements(
                requests=resource_requests,
                limits=resource_limits
            )

        return existing_sts

    def build_pod_template_labels(self, ai_instance_info_db, product_code, resource_limits):
        """构建Pod模板的标签"""
        labels = {
            RESOURCE_TYPE_KEY: PRODUCT_TYPE_CCI,
            APP_LABEL: ai_instance_info_db.instance_real_name,
            "dc.com/tenant.instance-id": ai_instance_info_db.id,
            "dc.com/tenant.app": "CCI",
            "dc.com/product.item": "CCI",
            "dc.com/tenant.source": "user",
            "dc.com/params.userId": ai_instance_info_db.instance_user_id,
            "dc.com/params.cciId": ai_instance_info_db.id,
            "dc.com/params.regionId": ai_instance_info_db.instance_region_id,
            "dc.com/params.zoneId": ai_instance_info_db.instance_k8s_id,
        }
        # 添加产品代码（如果存在）
        if product_code:
            labels["dc.com/params.productCode"] = product_code
        # # 检查是否为GPU实例并添加相应标签
        # if any(key.startswith('nvidia.com/') for key in resource_limits):
        #     labels[GPU_POD_LABEL_KEY] = GPU_POD_LABEL_VALUE

        return labels

    def create_affinity(self, node_selector_gpu):
        """创建亲和性配置"""
        if not node_selector_gpu:
            return None

        return V1Affinity(
            pod_affinity=V1PodAffinity(
                preferred_during_scheduling_ignored_during_execution=[
                    V1WeightedPodAffinityTerm(
                        weight=100,
                        pod_affinity_term=V1PodAffinityTerm(
                            label_selector=V1LabelSelector(
                                match_expressions=[
                                    V1LabelSelectorRequirement(
                                        key=GPU_POD_LABEL_KEY,
                                        operator="In",
                                        values=[GPU_POD_LABEL_VALUE]
                                    )
                                ]
                            ),
                            namespace_selector=None,
                            topology_key="kubernetes.io/hostname"
                        )
                    )
                ]
            )
        )

    def stop_ai_instance_by_id(self, id):
        try:
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            if not ai_instance_info_db:
                raise Fail(f"ai instance[{id}] is not found", error_message=f" 容器实例[{id}找不到]")
            dingo_print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} start to stop ai instance[{id}]")

            # 异步保存镜像
            queuedThreadPool.submit(partial(self.stop_save_cci_to_image_task, id))

            return {"id": id, "status": AiInstanceStatus.STOPPING.name}
        except Fail:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def force_stop_ai_instance_by_id(self, id):
        try:
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            if not ai_instance_info_db:
                raise Fail(f"ai instance[{id}] is not found", error_message=f" 容器实例[{id}找不到]")
            dingo_print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} start to stop ai instance[{id}]")

            # 标记为 STOPPED
            ai_instance_info_db.instance_status = AiInstanceStatus.STOPPING.name
            ai_instance_info_db.instance_real_status = None
            AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)

            app_client = get_k8s_app_client(ai_instance_info_db.instance_k8s_id)
            body = {"spec": {"replicas": 0}}
            try:
                app_client.patch_namespaced_stateful_set(
                    name=ai_instance_info_db.instance_real_name,
                    namespace=CCI_NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id,
                    body=body,
                    _preload_content=False
                )
            except Exception as e:
                dingo_print(f"关机失败，实例ID: {id}, 错误: {e}")
                ai_instance_info_db.instance_status = AiInstanceStatus.ERROR.name
                ai_instance_info_db.instance_real_status = K8sStatus.ERROR.value
                ai_instance_info_db.error_msg = str(e)
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

            return {"id": id, "status": AiInstanceStatus.STOPPING.name}
        except Fail:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e
        finally:
            self.get_or_set_update_k8s_node_resource_redis()

    def stop_cci_to_save_image(self, id, image_tag ="latest"):
        """
        异步保存AI实例为镜像（立即返回，实际操作在后台执行）
        """
        try:
            dingo_print(f"start time {time.strftime('%Y-%m-%d %H:%M:%S')} stop cci {id}")
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            if ai_instance_info_db:
                # 标记为 STOPPED
                ai_instance_info_db.instance_status = AiInstanceStatus.STOPPING.name
                ai_instance_info_db.instance_real_status = None
                AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)

                image_name = SAVE_TO_IMAGE_CCI_PREFIX + id
                harbor_address, harbor_username, harbor_password  = self.get_harbor_info(ai_instance_info_db.instance_k8s_id)
                core_k8s_client, sts_pod_info = self._get_k8s_sts_pod_info(ai_instance_info_db)
                nerdctl_api_pod = self._get_nerdctl_api_pod(core_k8s_client, sts_pod_info['node_name'])
                # 异步保存关机镜像
                self.async_save_cci_to_image(
                    id, core_k8s_client, nerdctl_api_pod,
                    sts_pod_info['container_id'], harbor_address, harbor_username, harbor_password,
                    image_name, image_tag
                )

                commit_push_image_flag = redis_connection.get_redis_by_key(SAVE_TO_IMAGE_CCI_PREFIX + id + "_flag")
                dingo_print(f"ai instance[{id}] push image flag: {commit_push_image_flag}")
                if commit_push_image_flag != "true":
                    error_msg =  f"{time.strftime('%Y-%m-%d %H:%M:%S')} ai instance[{id}] commit or push image image_tag: [{image_name}:{image_tag}] failed"
                    dingo_print(error_msg)
                    raise error_msg


                app_client = get_k8s_app_client(ai_instance_info_db.instance_k8s_id)
                body = {"spec": {"replicas": 0}}
                try:
                    app_client.patch_namespaced_stateful_set(
                        name=ai_instance_info_db.instance_real_name,
                        namespace=CCI_NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id,
                        body=body,
                        _preload_content=False
                    )
                except Exception as e:
                    error_msg = (f"stop k8s cci pod failed, id [{id}] : {e}")
                    dingo_print(error_msg)
                    raise error_msg

                # 标记为 STOPPED
                ai_instance_info_db.instance_status = AiInstanceStatus.STOPPED.name
                ai_instance_info_db.instance_real_status = None
                ai_instance_info_db.stop_time = datetime.now()
                AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)

        except Exception as e:
            # 副本数改成0
            self.set_k8s_sts_replica_by_instance_id(id, 0)

            dingo_print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} stop cci {id} to save image fail:{e}")
            import  traceback
            traceback.print_exc()
            raise e
        finally:
            self.get_or_set_update_k8s_node_resource_redis()


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

    def start_cci_check_pod_status_node_name_and_update_db(self,
                                                       core_k8s_client,
                                                       instance_id: str,
                                                       pod_name: str,
                                                       namespace: str,
                                                       timeout: int = CCI_TIME_OUT_DEFAULT
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

                    current_real_status, error_msg = self.get_pod_final_status(pod)
                    current_node_name = pod.spec.node_name

                    # 如果状态发生变化，更新数据库
                    if current_real_status != pod_real_status or current_node_name != pod_located_node_name:
                        pod_real_status = current_real_status
                        pod_located_node_name = current_node_name
                        self.update_pod_status_and_node_name_in_db(instance_id, pod_real_status, pod_located_node_name, error_msg)
                        dingo_print(f"Pod {pod_name} status/node name change to: {pod_real_status}_{pod_located_node_name}")
                        if current_real_status in ["Error", "CrashLoopBackOff", "ImagePullBackOff", "CreateContainerError",
                                                   "CreateContainerConfigError", "OOMKilled", "ContainerCannotRun", "Completed", "Failed"]:
                            dingo_print(f"change Pod {pod_name} sts replica to 0")
                            # 副本数改成0
                            self.set_k8s_sts_replica_by_instance_id(instance_id, 0)

                            self.get_or_set_update_k8s_node_resource_redis()
                            return


                    # 如果 Pod 处于 Running 状态，退出循环
                    if pod_real_status == "Running":
                        dingo_print(f"Pod {pod_name} 已正常运行, node name:{current_node_name}")
                        self.get_or_set_update_k8s_node_resource_redis()

                        # 明确退出函数
                        return


                    # 等待3秒后再次检查
                    time.sleep(5)

                except Exception as e:
                    import traceback
                    traceback.print_exc()

                    time.sleep(5)

            # 5. 检查是否超时
            if (datetime.now() - start_time).total_seconds() >= timeout:
                dingo_print(f"Pod {pod_name} 状态检查超时(5分钟)")

                self.update_pod_status_and_node_name_in_db(instance_id, K8sStatus.ERROR.value, pod_located_node_name, "cci pod change to running timeout")

                # 副本数改成0
                self.set_k8s_sts_replica_by_instance_id(instance_id, 0)

                self.get_or_set_update_k8s_node_resource_redis()
                return

        except Exception as e:
            dingo_print(f"检查Pod状态时发生未预期错误: {e}")
            self.get_or_set_update_k8s_node_resource_redis()
            import traceback
            traceback.print_exc()
            return


    def create_check_pod_status_node_name_and_update_db(self, ai_instance, ai_instance_db, namespace_name, resource_config, timeout: int = CCI_TIME_OUT_DEFAULT):
        """
        异步检查 Pod 状态并更新数据库

        :param core_k8s_client: k8s core v1 client
        :param pod_name: 要检查的 Pod 名称
        :param namespace: Pod 所在的命名空间
        :param timeout: 超时时间(秒)，默认5分钟(300秒)
        """
        try:

            pod_real_status = None
            pod_located_node_name = None
            pod_name = ai_instance_db.instance_real_name + "-0"
            namespace = CCI_NAMESPACE_PREFIX + ai_instance_db.instance_tenant_id
            start_time = datetime.now()

            # 创建K8s资源
            self._create_cci_k8s_resources(ai_instance, ai_instance_db, namespace_name, resource_config)

            while (datetime.now() - start_time).total_seconds() < timeout:
                try:
                    # 查询 Pod 状态
                    pod = k8s_common_operate.get_pod_info(self.core_k8s_client, pod_name, namespace)

                    current_real_status, error_msg = self.get_pod_final_status(pod)
                    current_node_name = pod.spec.node_name

                    # 如果状态发生变化，更新数据库
                    if current_real_status != pod_real_status or current_node_name != pod_located_node_name:
                        pod_real_status = current_real_status
                        pod_located_node_name = current_node_name
                        self.update_pod_status_and_node_name_in_db(ai_instance_db.id, pod_real_status, pod_located_node_name, error_msg)
                        dingo_print(f"Pod {pod_name} status/node name change to: {pod_real_status}_{pod_located_node_name}")
                        if current_real_status in ["Error", "CrashLoopBackOff", "ImagePullBackOff", "CreateContainerError",
                                                   "CreateContainerConfigError", "OOMKilled", "ContainerCannotRun", "Completed", "Failed"]:
                            dingo_print(f"change Pod {pod_name} sts replica to 0")
                            # 副本数改成0
                            self.set_k8s_sts_replica_by_instance_id(ai_instance_db.id, 0)

                            self.get_or_set_update_k8s_node_resource_redis()
                            return


                    # 如果 Pod 处于 Running 状态，退出循环
                    if pod_real_status == "Running":
                        dingo_print(f"Pod {pod_name} 已正常运行, node name:{current_node_name}")
                        self.get_or_set_update_k8s_node_resource_redis()

                        # 明确退出函数
                        return


                    # 等待3秒后再次检查
                    time.sleep(5)

                except Exception as e:
                    import traceback
                    traceback.print_exc()

                    time.sleep(5)

            # 5. 检查是否超时
            if (datetime.now() - start_time).total_seconds() >= timeout:
                dingo_print(f"Pod {pod_name} 状态检查超时(5分钟)")

                self.update_pod_status_and_node_name_in_db(ai_instance_db.id, K8sStatus.ERROR.value, pod_located_node_name, "cci pod change to running timeout")

                # 副本数改成0
                self.set_k8s_sts_replica_by_instance_id(ai_instance_db.id, 0)

                self.get_or_set_update_k8s_node_resource_redis()

        except Exception as e:
            dingo_print(f"检查Pod {ai_instance_db.id} 状态时发生未预期错误: {e}")
            self.get_or_set_update_k8s_node_resource_redis()
            import traceback
            traceback.print_exc()
            return

    def handle_cci_node_resource_info(self, instance_id, k8s_id, node_name):
        node_resource_db = AiInstanceSQL.get_k8s_node_resource_by_k8s_id_and_node_name(k8s_id, node_name)
        if node_resource_db:
            try:
                # 处理GPU使用卡数
                instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(instance_id)
                compute_resource_dict = json.loads(instance_info_db.instance_config) if instance_info_db else {}
                # 更新资源使用量

                #  转换并累加CPU使用量
                if node_resource_db.cpu_used:
                    # 使用float来处理小数
                    total_cpu = float(node_resource_db.cpu_used) + float(compute_resource_dict['compute_cpu'])
                    node_resource_db.cpu_used = str(total_cpu)
                else:
                    node_resource_db.cpu_used = float(compute_resource_dict['compute_cpu'])

                # 处理slot
                node_resource_db.cpu_slot_used = str((float(
                    node_resource_db.cpu_slot_used) if node_resource_db.cpu_slot_used else 0) + float(
                    compute_resource_dict['compute_cpu']))

                # 转换并累加内存使用量
                if node_resource_db.memory_used:
                    # 使用float来处理小数
                    total_memory = float(node_resource_db.memory_used) + float(compute_resource_dict['compute_memory'])
                    node_resource_db.memory_used = str(total_memory)
                else:
                    node_resource_db.memory_used = float(compute_resource_dict['compute_memory'])

                # 累加存储使用量
                if node_resource_db.storage_used:
                    # 使用float来处理小数
                    total_storage = float(node_resource_db.storage_used) + float(compute_resource_dict['system_disk_size'])
                    node_resource_db.storage_used = str(total_storage)
                else:
                    node_resource_db.storage_used = float(compute_resource_dict['system_disk_size'])

                # 处理GPU使用卡数
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
                dingo_print(f"k8s[{k8s_id}] node[{node_name}] resource update success")
            except Exception as e:
                dingo_print(f"save k8s node resource fail:{e}")
                import traceback
                traceback.print_exc()
        else:
            dingo_print(f"Not found k8s[{k8s_id}] node[{node_name}] resource info, can not to update used resource")

    def update_pod_status_and_node_name_in_db(self, id : str, k8s_status: str, node_name: str, error_msg: str = None):
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
            ai_instance_db.error_msg = error_msg
            dingo_print(f"异步更新容器实例[{ai_instance_db.instance_real_name}] instance_status：{ai_instance_db.instance_status}, node name:{ai_instance_db.instance_node_name}")
            AiInstanceSQL.update_ai_instance_info(ai_instance_db)
        except Exception as e:
            dingo_print(f"更新容器实例[{id}]数据库失败: {e}")

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
                # 关机中的状态，不允许装换状态到运行中，说明在保存镜像，底层是RUNNING，ANC要保持STOPPING
                K8sStatus.RUNNING: AiInstanceStatus.STOPPING
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
            namespace_name = CCI_NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id
            service_name = ai_instance_info_db.instance_real_name

            # port = int(model.port)
            target_port = int(model.target_port) if hasattr(model,
                                                            'target_port') and model.target_port is not None else 8888
            # node_port = int(model.node_port) if getattr(model, 'node_port', None) is not None else None
            protocol = getattr(model, 'protocol', None) or 'TCP'

            # 查询一个未被占用的port
            available_port, _ = self.find_ai_instance_available_ports(instance_id=id, count=1, is_add=True, target_port=target_port)
            port=available_port[0]
            try:
                # 读取 Service 并追加端口
                svc = core_k8s_client.read_namespaced_service(name=service_name, namespace=namespace_name)
                if not svc or not svc.spec:
                    raise Fail("service invalid", error_message="Service 无效")

                existing_ports = svc.spec.ports or []
                new_port = client.V1ServicePort(port=port, target_port=target_port, protocol=protocol)

                # 必须为每个端口设置唯一 name 字段
                new_port.name = f"port-{target_port}"
                existing_ports.append(new_port)
                svc.spec.ports = existing_ports

                core_k8s_client.patch_namespaced_service(name=service_name, namespace=namespace_name, body=svc)
            except Exception as e:
                dingo_print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ai instance {id} add port {target_port} fail: {e}")
                AiInstanceSQL.delete_ports_info_by_instance_id_target_port(id, target_port)
                import traceback
                traceback.print_exc()
                raise e

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
            namespace_name = CCI_NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id
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
                if int(getattr(p, 'target_port', -1)) == int(port):
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
            # 删数据库表数据
            AiInstanceSQL.delete_ports_info_by_instance_id_target_port(id, port)
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
            namespace_name = CCI_NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id
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
            namespace_name = CCI_NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id
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

    def get_ssh_info_by_id(self, id: str):
        try:
            # id空
            if not id:
                raise Fail("ai instance id can not be empty")
            # 查库
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            # 空
            if not ai_instance_info_db:
                raise Fail(f"ai instance[{id}] is not found", error_message=f"容器实例[{id}找不到]")
            # 连接k8s
            core_k8s_client = get_k8s_core_client(ai_instance_info_db.instance_k8s_id)
            namespace_name = CCI_NAMESPACE_PREFIX + ai_instance_info_db.instance_tenant_id
            service_name = ai_instance_info_db.instance_real_name

            # 查询 Service 暴露 22 端口
            svc = core_k8s_client.read_namespaced_service(name=service_name, namespace=namespace_name)
            # 无效service
            if not svc or not svc.spec or not svc.spec.ports:
                raise Fail("service invalid", error_message="Service 无效")
            # 匹配 Service 的 22 端口
            node_port_assigned = None
            for p in svc.spec.ports:
                # 匹配到 22 的端口
                if (int(p.target_port) == 22):
                    node_port_assigned = getattr(p, 'port', None)
                    break
            # 查询实例对应的vip
            vip, _, _ = self._get_service_ip(ai_instance_info_db)
            # 组装返回参数
            if not vip or not ai_instance_info_db.ssh_root_password or not node_port_assigned:
                raise Fail("ssh service invalid", error_message="SSH Service 无效")
            return {"data": {"password": ai_instance_info_db.ssh_root_password, "target_port": 22, "url": f"ssh root@{vip} -p {node_port_assigned}"}}
        except Fail:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    #
    # async def create_safe_check_pod_status_and_node_name(self, *args):
    #     """受保护的检查任务"""
    #     try:
    #         await self.create_check_pod_status_node_name_and_update_db(*args)
    #     except Exception as e:
    #         dingo_print(f"Pod status check failed: {e}")
    #         import traceback
    #         traceback.print_exc()

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
                if total is None:
                    return None

                    # 处理used为None或非数值的情况，默认为0
                used_val = float(used) if used is not None else 0.0
                total_val = float(total)

                # 计算剩余量，并确保结果不小于0
                remaining = total_val - used_val
                return round(max(0.0, remaining), 2)

            # 构建结果字典
            node_stats = {
                'node_name': node_resource_db.node_name,
                'less_gpu_pod_total': node_resource_db.less_gpu_pod_total,
                'less_gpu_pod_count': node_resource_db.less_gpu_pod_count,
                'cpu_slot_total': int(node_resource_db.cpu_slot_total) if node_resource_db.cpu_slot_total else 0,
                'cpu_slot_used': int(node_resource_db.cpu_slot_used) if node_resource_db.cpu_slot_used else 0,
                'gpu_model': None if not node_resource_db.gpu_model else self.find_gpu_display_by_key(node_resource_db.gpu_model),
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

    def find_gpu_display_by_key(self, gpu_key):
        gpu_card_info = AiInstanceSQL.get_gpu_card_info_by_gpu_key(gpu_key)
        return gpu_card_info.gpu_model_display if gpu_card_info else None

    def find_gpu_key_by_display(self, gpu_display):
        gpu_card_info = AiInstanceSQL.get_gpu_card_info_by_gpu_model_display(gpu_display)
        return gpu_card_info.gpu_key if gpu_card_info else None

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
            dingo_print(f"Convert failed: {value} to {convert_type.__name__}, error: {str(e)}")
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
            dingo_print(f"============compute_resource_dict :{compute_resource_dict}")
            # 处理GPU资源（需要型号匹配）
            less_gpu_pod = True
            if ('gpu_model' in compute_resource_dict and 'gpu_count' in compute_resource_dict and
                    compute_resource_dict['gpu_model'] and node_resource_db.gpu_model):
                current_node_gpu = self.safe_float(node_resource_db.gpu_used or '0')
                current_node_gpu_pod_count = self.safe_float(node_resource_db.gpu_pod_count or '0')
                pod_resource_gpu = self.safe_float(compute_resource_dict['gpu_count'])
                node_resource_db.gpu_used = str(max(0, current_node_gpu + operation_factor * pod_resource_gpu))
                node_resource_db.gpu_pod_count = str(max(0, current_node_gpu_pod_count + operation_factor * 1))
                less_gpu_pod = False

            # 处理CPU资源
            if 'compute_cpu' in compute_resource_dict:
                current_node_cpu = self.safe_float(node_resource_db.cpu_used or '0')
                pod_resource_cpu = self.safe_float(compute_resource_dict['compute_cpu'])
                node_resource_db.cpu_used = str(max(0, current_node_cpu + operation_factor * pod_resource_cpu))
                if less_gpu_pod:
                    current_node_less_gpu_pod_count = self.safe_float(node_resource_db.less_gpu_pod_count or '0')
                    node_resource_db.less_gpu_pod_count = str(max(0, current_node_less_gpu_pod_count + operation_factor * 1))

                node_resource_db.cpu_slot_used = str(max(0, float(node_resource_db.cpu_slot_used) if node_resource_db.cpu_slot_used else 0)
                                                     + operation_factor + float(compute_resource_dict['compute_cpu']))


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
            dingo_print(f"{operation}节点资源失败: {str(e)}")
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
                name=ai_instance_db.instance_real_name + CCI_STS_POD_SUFFIX,
                namespace=CCI_NAMESPACE_PREFIX + ai_instance_db.instance_tenant_id,
                container=None,
                command=exec_command,
                stderr=True, stdin=True,
                stdout=True, tty=True,
                _preload_content=False
            )
            return resp
        except Exception as e:
            dingo_print(f"ai_instance_web_ssh instance_id:{instance_id} fail")
            import traceback
            traceback.print_exc()
            raise e

    def extract_project_and_image_name(self, harbor_address):
        """
        根据Harbor仓库地址提取出项目名。

        参数:
            harbor_address (str): Harbor仓库地址，例如 'xxx/anc-public/'
        返回:
            tuple: 包含 (project_name, image_name)
                  例如 ('anc-public', 'stop_save_image-88a81cc88e9348bea4091663d1513e15')
        """
        # 1. 从 harbor_address 中提取命名空间 (如 'anc-public')
        # 移除末尾的斜杠（如果存在），然后按 '/' 分割，取最后一部分
        if harbor_address.endswith('/'):
            harbor_address = harbor_address.rstrip('/')
        parts = harbor_address.split('/')
        project_name = parts[-1] if parts else ""  # 获取最后一部分作为命名空间

        return project_name

    def set_k8s_sts_replica_by_instance_id(self, instance_id: str, replica: int):
        # 空
        if not instance_id:
            return
        # 查库
        instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(instance_id)
        # 空
        if not instance_info_db:
            return
        # 连接k8s，设置副本数0
        try:
            app_client = get_k8s_app_client(instance_info_db.instance_k8s_id)
            body = {"spec": {"replicas": replica}}
            app_client.patch_namespaced_stateful_set(
                name=instance_info_db.instance_real_name,
                namespace=CCI_NAMESPACE_PREFIX + instance_info_db.instance_tenant_id,
                body=body,
                _preload_content=False
            )
        except Exception as e:
            dingo_print(f"实例设置副本数{replica}失败，实例ID: {id}, 错误: {e}")

    def get_pod_final_status(self, pod) -> str:
        """
        获取 Pod 的最终状态和详细信息，规则：
        - 容器有错误状态 → 返回错误状态和详情
        - 容器有 Running 状态 → 返回 Running 和详情
        - 其他情况 → 返回 Pod 原生相位（如 Pending）和详情

        Returns:
            tuple: (status_str, detail_message)
        """
        try:
            container_statuses = pod.status.container_statuses or []
            pod_phase = pod.status.phase or "Error"

            # 1. 检查是否有容器处于错误状态
            for container_status in container_statuses:
                state = container_status.state
                container_name = container_status.name

                # 处理 Waiting 状态
                if state.waiting:
                    reason = state.waiting.reason
                    message = state.waiting.message or ""
                    if reason in ["Error", "CrashLoopBackOff", "ImagePullBackOff", "CreateContainerError", "CreateContainerConfigError"]:
                        detail_msg = f"Container '{container_name}' waiting: {reason}"
                        if message:
                            detail_msg += f" - {message}"
                        return str(reason), detail_msg

                # 处理 Terminated 状态
                if state.terminated:
                    reason = state.terminated.reason
                    exit_code = state.terminated.exit_code
                    message = state.terminated.message or ""

                    if reason in ["Error", "OOMKilled", "ContainerCannotRun", "Completed"]:
                        detail_msg = f"Container '{container_name}' terminated: {reason} (exit code: {exit_code})"
                        if message:
                            detail_msg += f" - {message}"
                        return str(reason), detail_msg

                    # 处理信号终止的情况 (128 + signal number)
                    # if exit_code >= 128:
                    #     signal_num = exit_code - 128
                    #     detail_msg = f"Container '{container_name}' killed by signal {signal_num} (exit code: {exit_code})"
                    #     if message:
                    #         detail_msg += f" - {message}"
                    #     return f"Signal{signal_num}", detail_msg

            # 2. 检查是否有容器处于 Running 状态
            running_containers = []
            for container_status in container_statuses:
                if container_status.state and container_status.state.running:
                    running_containers.append(container_status.name)

            if running_containers:
                containers_str = ", ".join(running_containers)
                return "Running", f"Containers running: {containers_str}"

            # 3. 检查就绪状态
            ready_containers = []
            not_ready_containers = []
            for container_status in container_statuses:
                if container_status.ready:
                    ready_containers.append(container_status.name)
                else:
                    not_ready_containers.append(container_status.name)

            # if ready_containers and not_ready_containers:
            #     detail_msg = f"Mixed readiness: ready={ready_containers}, not-ready={not_ready_containers}"
            #     return "NotReady", detail_msg

            # 4. 无错误且无 Running 容器，返回 Pod 原生相位
            phase_detail = f"Pod phase: {pod_phase}"
            if pod.status.message:
                phase_detail += f" - {pod.status.message}"
            if pod.status.reason:
                phase_detail += f" (reason: {pod.status.reason})"

            return pod_phase, phase_detail

        except Exception as e:
            return "Error", f"Failed to get pod status: {str(e)}"

    # 选择可用节点 参数传输的是当前规格的cpu（核）、内存（G）、存储（G）、gpuModel（）gpu（个）
    def choose_k8s_node(self, k8s_id: str, cpu: int, memory: int, disk: int = 50, gpu_model=None, gpu: int = 1):
        # 判断空
        if not k8s_id or not cpu or not memory:
            dingo_print(f"指定的k8s{k8s_id},cpu：{cpu},memory：{memory},disk：{disk}")
            return None
        # 查询当前所有可用节点
        node_list = []
        try:
            # 查询当前k8s的所有可用节点
            node_list = self.get_k8s_node_resource_statistics(k8s_id)
            # node_list.append(node_resource_list_db)
        except Exception as e:
            dingo_print(f"查询不到可用节点, 错误: {e}")
        # 空
        if not node_list:
            return None
        # 如果是gpu规格对应的节点
        if gpu_model:
            return self.choose_gpu_falvor_node(self.filter_node_list_by_gpu_model(node_list, gpu_model), gpu)
        else:
            return self.choose_no_gpu_flavor_node(node_list, cpu, memory, disk)
        # 针对gpu规格查询可用节点 是根据节点的gpu剩余卡数，找剩余卡数满足gpu且剩余卡数是最小的节点
        # 遍历节点配置计算节点按照当前模式匹配的
        # 规则判断
        # 无卡 固定的2核4G pod已使用两数量最大的node
        # 有卡 找gpu使用量最大的满足条件的node
        return None

    def choose_no_gpu_flavor_node(self, node_list, cpu: int, memory: int, disk: int):
        # 判空
        if not node_list or cpu <= 0 or memory <= 0 or disk <= 0:
            return None
        # 可用节点列表
        available_nodes = []
        # 遍历
        for node in node_list:
            # # 检查节点是否有所需属性
            # if not all(hasattr(node, attr) for attr in
            #            ['node_name', 'cpu_total', 'cpu_used', 'gpu_model', 'gpu_used', 'memory_total',
            #             'memory_used', 'storage_total', 'storage_used']):
            #     continue
            gpu_1_cpu = 0
            gpu_1_memory = 0
            if node['gpu_model']:
                config = SystemSQL.get_system_support_config_by_config_key("cci_" + self.find_gpu_key_by_display(node['gpu_model']))
                if config:
                    gpu_1_cpu, gpu_1_memory = self.parse_gpu_model(str(config.config_value))
            # 计算实际可用资源（扣除 GPU 占用的部分）
            available_cpu = node['cpu_total'] - node['cpu_used'] - node['gpu_used'] * gpu_1_cpu
            available_memory = node['memory_total'] - node['memory_used'] - node['gpu_used'] * gpu_1_memory
            available_disk = node['storage_total'] - node['storage_used'] - node['gpu_used'] * 50
            # 检查是否满足需求
            if available_cpu >= cpu and available_memory >= memory and available_disk >= disk:
                available_nodes.append((node, available_cpu))
        # 没有可用节点
        if not available_nodes:
            return None
        # 选择剩余 CPU 最小的节点（负载最均衡）
        chosen_node = min(available_nodes, key=lambda x: x[1])[0]
        dingo_print(f"wwb chosen_node:{chosen_node}")
        # 返回选择好的节点
        return chosen_node['node_name']

    """
    选择一个 GPU 节点，其剩余 GPU 资源（gpu_total - gpu_used）最小，但仍能满足请求的 gpu 数量。
    """
    def choose_gpu_falvor_node(self, node_list: list, gpu: int):
        # 空
        if not node_list or not gpu:
            return None
        # 筛选出满足 gpu_total - gpu_used >= gpu 的节点
        available_nodes = [
            node for node in node_list
            if hasattr(node, "gpu_total") and hasattr(node, "gpu_used")
               and (node.gpu_total - node.gpu_used) >= gpu
        ]
        if not available_nodes:
            return None
        # 找出剩余 GPU 最小的节点
        chosen_node = min(
            available_nodes,
            key=lambda node: node.gpu_total - node.gpu_used
        )
        # 返回选择的节点名称
        return chosen_node.node_name if hasattr(chosen_node, "node_name") else None

    """
    过滤匹配的GPU卡的节点。
    """
    def filter_node_list_by_gpu_model(self, node_resource_list_db, gpu_model):
        # 空
        if not gpu_model or not node_resource_list_db:
            return None
        # 筛选出 gpu_mode 匹配的节点
        filtered_nodes = [
            node for node in node_resource_list_db
            if hasattr(node, "gpu_model") and node.gpu_model == gpu_model
        ]
        # 返回
        return filtered_nodes if filtered_nodes else None

    """
    从 8C16G 这类格式中提取 CPU 和内存占用值
    """
    def parse_gpu_model(self, gpu_cpu_memory: str) -> tuple:
        pattern = r"^(\d+)C(\d+)G$"  # 匹配数字C数字G的格式
        match = re.match(pattern, gpu_cpu_memory)
        if match:
            return int(match.group(1)), int(match.group(2))
        return 0, 0  # 默认不占用额外资源


    def safe_divide(self, cpu_str, divisor=CPU_OVER_COMMIT):
        try:
            # 转换为数字
            cpu_num = float(cpu_str)
            # 除超分倍数
            result = cpu_num / divisor
            # 最小返回0.5 保留两位小数
            return max(MIN_CPU_REQUEST, round(result, 2))
        except Exception as e:
            dingo_print(e)
            return MIN_CPU_REQUEST  # 默认安全值

    def get_or_set_update_k8s_node_resource_redis(self):
        operator_flag = redis_connection.get_redis_by_key(CCI_SYNC_K8S_NODE_REDIS_KEY)
        if not operator_flag:
            dingo_print("set ai instance k8s node resource key expire time  to 10s")
            redis_connection.set_redis_by_key_with_expire(CCI_SYNC_K8S_NODE_REDIS_KEY, "true", 10)

    def test_thread_pool(self):
        for i in range(1, 1001):
            # 测试线程池
            queuedThreadPool.submit(partial(print, f"Hello World Number {i}"))
