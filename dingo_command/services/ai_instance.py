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
    V1ContainerPort, V1Toleration, V1EmptyDirVolumeSource
from kubernetes import client
from oslo_log import log

from dingo_command.api.model.aiinstance import StorageObj
from dingo_command.common.Enum.AIInstanceEnumUtils import AiInstanceStatus, K8sStatus
from dingo_command.common.k8s_common_operate import K8sCommonOperate
from dingo_command.db.models.ai_instance.models import AiInstanceInfo, AccountInfo
from dingo_command.db.models.ai_instance.sql import AiInstanceSQL
from dingo_command.utils.constant import NAMESPACE_PREFIX, AI_INSTANCE_SYSTEM_MOUNT_PATH_DEFAULT, \
    SYSTEM_DISK_NAME_DEFAULT, RESOURCE_TYPE, AI_INSTANCE, AI_INSTANCE_PVC_MOUNT_PATH_DEFAULT, AI_INSTANCE_CM_MOUNT_PATH_DEFAULT, \
    SYSTEM_DISK_SIZE_DEFAULT, APP_LABEL
from dingo_command.utils.k8s_client import get_k8s_core_client, get_k8s_app_client
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
            namespace_name = NAMESPACE_PREFIX + ai_instance_info_db.instance_root_account_id
            real_name = ai_instance_info_db.instance_real_name or ai_instance_info_db.instance_name

            try:
                k8s_common_operate.delete_service_by_name(core_k8s_client, real_name, namespace_name)
            except Exception as e:
                LOG.error(f"删除Service失败, name={real_name}, ns={namespace_name}, err={e}")

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
        return {"data": "success", "uuid": id}

    # ================= 账户相关 =================
    def create_ai_account(self, account: str, is_vip: bool = False):
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
                is_vip=bool(is_vip)
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

    def update_ai_account_by_id(self, id: str, account: str = None, is_vip: bool = None):
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
            if is_vip is not None:
                existed.is_vip = bool(is_vip)

            AiInstanceSQL.update_account_info(existed)
            return {"data": "success", "uuid": id}
        except Fail:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def sava_ai_instance_to_image(self, id, request):
        try:
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            if not ai_instance_info_db:
                raise Fail(f"ai instance[{id}] is not found", error_message=f" 容器实例[{id}找不到]")

            repo_name = request.repo_name
            image_label = request.image_label
            # harbor_username = request.harbor_username
            # harbor_password = request.harbor_password

            if not repo_name:
                raise Fail(f"image repository name for saving the ai instance to image - [{id}] - is empty.", error_message=f"容器实例[{id}]保存镜像到的镜像库名称为空")

            if not image_label:
                raise Fail(f"image label for saving the ai instance to image - [{id}] - is empty.",
                           error_message=f"容器实例[{id}]保存的镜像的标签为空")

            # if not harbor_username or not harbor_password:
            #     raise Fail(f"harbor username or password is empty",
            #                error_message=f"harbor username or password is empty")

            core_k8s_client = get_k8s_core_client(ai_instance_info_db.instance_k8s_id)

            # 执行函数
            # self.process_large_volume_and_build(
            #     core_k8s_client,
            #     pod_name=ai_instance_info_db.instance_real_name + "-0",
            #     namespace=NAMESPACE_PREFIX + ai_instance_info_db.instance_root_account_id,
            #     source_path=AI_INSTANCE_SYSTEM_MOUNT_PATH_DEFAULT,
            #     harbor_repo=repo_name,
            #     new_tag=image_label
            # )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return e


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
        temp["uuid"] = r.id
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
            toleration_gpus = []
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
                    toleration_gpus.append(toleration)

                elif "amd" in ai_instance.instance_config.gpu_model.lower():
                    resource_limits['amd.com/gpu'] = str(ai_instance.instance_config.gpu_count)
                else:
                    LOG.erorr(f"ai instance[{ai_instance.name}] instance_config gpu model[{ai_instance.instance_config.gpu_model}] is unknown")

            results = []
            if ai_instance.instance_config.replica_count == 1:
                # 校验namespace是否存在，不存在则创建
                namespace_name = self.handling_and_create_namespace_info(ai_instance, core_k8s_client)
                # 组装statefulset pod数据
                ai_instance_info_db_rel = self.assemble_create_sts_pod_to_save(
                                                             ai_instance, ai_instance_info_db, app_k8s_client,
                                                             core_k8s_client, ai_instance.instance_envs,
                                                             namespace_name,resource_limits, node_selector_gpu,
                                                             toleration_gpus)
                # 启动异步任务（不等待）
                self._start_async_check_task(
                    core_k8s_client,
                    ai_instance_info_db.instance_k8s_id,
                    ai_instance_info_db_rel.id,
                    f"{ai_instance_info_db_rel.instance_real_name}-0",
                    NAMESPACE_PREFIX + ai_instance_info_db_rel.instance_root_account_id
                )
                results.append(self.assemble_ai_instance_return_result(ai_instance_info_db_rel))
                return results
            else:
                # 校验namespace是否存在，不存在则创建
                namespace_name = self.handling_and_create_namespace_info(ai_instance, core_k8s_client)
                for i in range(ai_instance.instance_config.replica_count):
                    ai_instance_info_db_copy = copy.deepcopy(ai_instance_info_db)
                    # 组装statefulset pod数据
                    ai_instance_info_db_rel = self.assemble_create_sts_pod_to_save(
                                                                 ai_instance, ai_instance_info_db_copy, app_k8s_client,
                                                                 core_k8s_client, ai_instance.instance_envs,
                                                                 namespace_name,resource_limits, node_selector_gpu,
                                                                 toleration_gpus)
                    # 启动异步任务（不等待）
                    self._start_async_check_task(
                        core_k8s_client,
                        ai_instance_info_db.instance_k8s_id,
                        ai_instance_info_db_rel.id,
                        f"{ai_instance_info_db_rel.instance_real_name}-0",
                        NAMESPACE_PREFIX + ai_instance_info_db_rel.instance_root_account_id
                    )
                    results.append(self.assemble_ai_instance_return_result(ai_instance_info_db_rel))
            # 返回数据
            return results
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def assemble_create_sts_pod_to_save(self, ai_instance, ai_instance_info_db, app_k8s_client, core_k8s_client,
                                        env_vars, namespace_name, resource_limits, node_selector_gpu, toleration_gpus):
        # 名称后面加上五位随机小写字母和数字组合字符串
        bottom_name = ai_instance.name + "-" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
        ai_instance_info_db.instance_real_name = bottom_name

        # 创建Service(StatefulSet需要)
        k8s_common_operate.create_ai_instance_sts_service(core_k8s_client, namespace_name, bottom_name)

        system_limit_disk = ai_instance.instance_config.system_disk_size
        if not system_limit_disk:
            system_limit_disk = SYSTEM_DISK_SIZE_DEFAULT
        else:
            system_limit_disk += "Gi"

        resource_limits['ephemeral-storage'] = system_limit_disk

        # 组装StatefulSet Pod 数据
        stateful_set_pod_data = self.assemble_sts_pod_info(
            sts_name=bottom_name,
            service_name=bottom_name,
            image=ai_instance.image,
            env_vars=env_vars,
            resource_limits=resource_limits,
            volumes=ai_instance.volumes,
            order_id=ai_instance.order_id,
            user_id=ai_instance.user_id,
            node_selector_gpu=node_selector_gpu,
            toleration_gpus=toleration_gpus,
            system_disk=system_limit_disk
        )
        ai_instance_info_db.id = uuid.uuid4().hex
        # 提前保存数据到数据库
        AiInstanceSQL.save_ai_instance_info(ai_instance_info_db)

        # 创建StatefulSet Pod
        create_namespaced_sts_info = k8s_common_operate.create_sts_pod(app_k8s_client, namespace_name,stateful_set_pod_data)

        # 组装statefulset uid、creationTimestamp
        ai_instance_info_db.instance_create_time = create_namespaced_sts_info.metadata.creation_timestamp
        # 更新数据
        AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)
        return ai_instance_info_db

    def start_ai_instance_by_id(self, id):
        try:
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            if not ai_instance_info_db:
                raise Fail(f"ai instance[{id}] is not found", error_message=f"容器实例[{id}找不到]")
            
            # 检查实例状态，只有 stopped 状态的实例才能开机
            if ai_instance_info_db.instance_status != AiInstanceStatus.STOPPED:
                raise Fail(f"ai instance[{id}] status is {ai_instance_info_db.instance_status}, cannot start",
                          error_message=f" 容器实例[{id}]状态为{ai_instance_info_db.instance_status}，无法开机")

            # 获取k8s客户端
            app_k8s_client = get_k8s_app_client(ai_instance_info_db.instance_k8s_id)

            # 命名空间名称与实例名
            namespace_name = NAMESPACE_PREFIX + ai_instance_info_db.instance_root_account_id
            real_name = ai_instance_info_db.instance_real_name

            # 直接 Patch StatefulSet 副本为 1（开机）
            body = {"spec": {"replicas": 1}}
            try:
                app_k8s_client.patch_namespaced_stateful_set(
                    name=real_name,
                    namespace=namespace_name,
                    body=body,
                    _preload_content=False
                )
            except Exception as e:
                LOG.error(f"开机失败, 实例ID: {id}, 错误: {e}")
                raise e

            # 标记为 RUNNING
            ai_instance_info_db.instance_status = AiInstanceStatus.RUNNING
            ai_instance_info_db.instance_real_status = K8sStatus.RUNNING
            AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)
            return {"id": id, "status": ai_instance_info_db.instance_status}
        except Fail:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def stop_ai_instance_by_id(self, id):
        try:
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            if not ai_instance_info_db:
                raise Fail(f"ai instance[{id}] is not found", error_message=f" 容器实例[{id}找不到]")

            # 命名空间名称与实例名
            namespace_name = NAMESPACE_PREFIX + ai_instance_info_db.instance_root_account_id
            real_name = ai_instance_info_db.instance_real_name

            # 获取k8s客户端
            app_k8s_client = get_k8s_app_client(ai_instance_info_db.instance_k8s_id)

            # 在关机前尝试保存镜像
            # try:
            #     LOG.info(f"开始保存实例 {id} 的镜像")
            #
            #     # 构建默认的保存镜像请求
            #     from dingo_command.api.model.aiinstance import AiInstanceSavaImageApiModel
            #
            #     # 使用默认配置保存镜像（可以根据需要调整）
            #     default_save_request = AiInstanceSavaImageApiModel(
            #         repo_name="dingo-aurora",  # 默认仓库名
            #         image_label=f"instance-{id}",  # 使用实例ID作为标签
            #         harbor_username="admin",  # 默认用户名
            #         harbor_password="Harbor12345"  # 默认密码，实际应该从配置读取
            #     )
            #
            #     # 调用现有的保存镜像方法
            #     save_result = self.sava_ai_instance_to_image(id, default_save_request)
            #     LOG.info(f"实例 {id} 镜像保存完成: {save_result}")
            #
            # except Exception as e:
            #     LOG.error(f"保存镜像失败，实例ID: {id}, 错误: {e}")
            # 镜像保存失败不影响关机流程

            # 直接 Patch StatefulSet 副本为 0（关机）
            body = {"spec": {"replicas": 0}}
            try:
                app_k8s_client.patch_namespaced_stateful_set(
                    name=real_name,
                    namespace=namespace_name,
                    body=body,
                    _preload_content=False
                )
            except Exception as e:
                LOG.error(f"关机失败，实例ID: {id}, 错误: {e}")
                raise e
            # 标记为 STOPPED
            ai_instance_info_db.instance_status = AiInstanceStatus.STOPPED
            ai_instance_info_db.instance_real_status = ""
            ai_instance_info_db.stop_time = datetime.now()
            AiInstanceSQL.update_ai_instance_info(ai_instance_info_db)

            return {"id": id, "status": ai_instance_info_db.instance_status}
        except Fail:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

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

    def assemble_sts_pod_info(self, sts_name: str, service_name: str, image: str,
                              env_vars: list, resource_limits: dict, volumes: StorageObj,
                              order_id: str, user_id: str, node_selector_gpu: dict, toleration_gpus: list, system_disk: str = "30Gi") -> V1StatefulSet:
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
                    size_limit=system_disk
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
                    APP_LABEL: sts_name,
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
                tolerations=toleration_gpus
            )
        )

        # 5. 构建StatefulSet
        sts_info = V1StatefulSet(
            metadata=V1ObjectMeta(name=sts_name,
                                  labels={RESOURCE_TYPE: AI_INSTANCE}),
            spec=V1StatefulSetSpec(
                replicas=1,
                selector=V1LabelSelector(match_labels={APP_LABEL: sts_name,
                                                       RESOURCE_TYPE: AI_INSTANCE}),
                service_name=service_name,
                template=template,
                volume_claim_templates=[pvc_template] if pvc_template else None
            )
        )

        return sts_info

    def convert_ai_instance_info_db(self, ai_instance):
        ai_instance_info_db = AiInstanceInfo(instance_name=ai_instance.name,
                                             instance_status="READY",
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

    async def check_pod_status_node_name_and_update_db(self,
                                                       core_k8s_client,
                                                       k8s_id: str,
                                                       id: str,
                                                       pod_name: str,
                                                       namespace: str,
                                                       timeout: int = 300
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
                        self.update_pod_status_and_node_name_in_db(id, pod_real_status, pod_located_node_name)
                        print(f"Pod {pod_name} 状态/node name更新为: {pod_real_status}_{pod_located_node_name}")

                    # 如果 Pod 处于 Running 状态，退出循环
                    if pod_real_status == "Running":
                        print(f"Pod {pod_name} 已正常运行, node name:{current_node_name}")
                        node_name = pod.spec.node_name
                        node_resource_db = AiInstanceSQL.get_instances_by_k8s_and_node(k8s_id, node_name)
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

                                AiInstanceSQL.update_k8s_node_resource(node_resource_db)
                                LOG.error(f"k8s[{k8s_id}] node[{node_name}] resource update success")
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
                    # 检查是否为 NotFound 错误
                    if "Not Found" in str(e):
                        print(f"Pod {pod_name} 不存在，直接结束")
                        return  # 直接结束整个函数

                    await asyncio.sleep(3)

            # 5. 检查是否超时
            if (datetime.now() - start_time).total_seconds() >= timeout:
                print(f"Pod {pod_name} 状态检查超时(5分钟)")
                # self.update_pod_status_and_node_name_in_db(id, pod_real_status, pod_located_node_name)

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

    def create_port_by_id(self, id: str, port: int):
        try:
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            if not ai_instance_info_db:
                raise Fail(f"ai instance[{id}] is not found", error_message=f" 容器实例[{id}找不到]")

            core_k8s_client = get_k8s_core_client(ai_instance_info_db.instance_k8s_id)
            namespace_name = NAMESPACE_PREFIX + ai_instance_info_db.instance_root_account_id
            service_name = ai_instance_info_db.instance_real_name or ai_instance_info_db.instance_name

            # NodePort 占用校验（以 node_port=port 的策略暴露）
            if k8s_common_operate.is_node_port_in_use(core_k8s_client, int(port)):
                raise Fail(f"nodePort {port} already in use", error_message=f"节点端口 {port} 已被占用")

            # 读取 Service 并追加端口
            svc = core_k8s_client.read_namespaced_service(name=service_name, namespace=namespace_name)
            if not svc or not svc.spec:
                raise Fail("service invalid", error_message="Service 无效")

            existing_ports = svc.spec.ports or []
            for p in existing_ports:
                if int(p.port) == int(port) or getattr(p, 'node_port', None) == int(port):
                    return {"data": "success", "port": port}  # 幂等

            new_port = client.V1ServicePort(port=int(port), target_port=int(port))
            # 设为固定 nodePort
            if not svc.spec.type:
                svc.spec.type = "NodePort"
            if svc.spec.type != "NodePort":
                svc.spec.type = "NodePort"
            new_port.node_port = int(port)

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
            namespace_name = NAMESPACE_PREFIX + ai_instance_info_db.instance_root_account_id
            service_name = ai_instance_info_db.instance_real_name or ai_instance_info_db.instance_name

            svc = core_k8s_client.read_namespaced_service(name=service_name, namespace=namespace_name)
            if not svc or not svc.spec:
                raise Fail("service invalid", error_message="Service 无效")

            old_len = len(svc.spec.ports or [])
            svc.spec.ports = [p for p in (svc.spec.ports or []) if int(p.port) != int(port) and getattr(p, 'node_port', None) != int(port)]
            if len(svc.spec.ports or []) == old_len:
                return {"data": "success", "port": port}  # 幂等

            core_k8s_client.patch_namespaced_service(name=service_name, namespace=namespace_name, body=svc)
            return {"data": "success", "port": port}
        except Fail:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def list_port_by_id(self, id: str):
        try:
            ai_instance_info_db = AiInstanceSQL.get_ai_instance_info_by_id(id)
            if not ai_instance_info_db:
                raise Fail(f"ai instance[{id}] is not found", error_message=f" 容器实例[{id}找不到]")

            core_k8s_client = get_k8s_core_client(ai_instance_info_db.instance_k8s_id)
            namespace_name = NAMESPACE_PREFIX + ai_instance_info_db.instance_root_account_id
            service_name = ai_instance_info_db.instance_real_name or ai_instance_info_db.instance_name

            svc = core_k8s_client.read_namespaced_service(name=service_name, namespace=namespace_name)
            if not svc or not svc.spec:
                return {"data": []}

            ports = []
            for p in (svc.spec.ports or []):
                ports.append({
                    "port": int(p.port) if p.port is not None else None,
                    "targetPort": int(p.target_port) if isinstance(p.target_port, int) else p.target_port,
                    "nodePort": int(p.node_port) if getattr(p, 'node_port', None) is not None else None,
                    "protocol": p.protocol
                })
            return {"data": ports}
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
            namespace_name = NAMESPACE_PREFIX + ai_instance_info_db.instance_root_account_id
            service_name = ai_instance_info_db.instance_real_name or ai_instance_info_db.instance_name

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

    def _start_async_check_task(self, core_k8s_client, k8s_id, pod_id, pod_name, namespace):
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
                        pod_id,
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
                'gpu_model': None if not node_resource_db.gpu_model else node_resource_db.gpu_model.split("/", 1)[-1],
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
