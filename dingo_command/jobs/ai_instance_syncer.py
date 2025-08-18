import json
import uuid

from apscheduler.schedulers.background import BackgroundScheduler

from dingo_command.common.k8s_common_operate import K8sCommonOperate
from dingo_command.db.models.ai_instance.sql import AiInstanceSQL
from dingo_command.utils.k8s_client import get_k8s_core_client, get_k8s_app_client
from dingo_command.db.models.ai_instance.models import AiInstanceInfo
from dingo_command.services.ai_instance import AiInstanceService
from dingo_command.utils import datetime as datatime_util
from datetime import datetime
from oslo_log import log

relation_scheduler = BackgroundScheduler()
ai_instance_service = AiInstanceService()
k8s_common_operate = K8sCommonOperate()

LOG = log.getLogger(__name__)

def start():
    relation_scheduler.add_job(fetch_ai_instance_info, 'interval', seconds=30, next_run_time=datetime.now())
    relation_scheduler.start()


def fetch_ai_instance_info():
    start_time = datatime_util.get_now_time_in_timestamp_format()
    LOG.info(f"同步容器实例开始时间: {start_time}")
    try:
        # 查询所有容器实例
        k8s_kubeconfig_configs_db = AiInstanceSQL.list_k8s_kubeconfig_configs()
        if k8s_kubeconfig_configs_db is None:
            LOG.info("ai k8s kubeconfig configs is temp")
            return
        for k8s_kubeconfig_db in k8s_kubeconfig_configs_db:
            if k8s_kubeconfig_db.k8s_id is None:
                print(f"k8s 集群[{k8s_kubeconfig_db.k8s_name}], k8s type:{k8s_kubeconfig_db.k8s_type} id empty")
                continue

            try:
                # 获取client
                core_k8s_client = get_k8s_core_client(k8s_kubeconfig_db.k8s_id)
                app_k8s_client = get_k8s_app_client(k8s_kubeconfig_db.k8s_id)
            except Exception as e:
                LOG.error(f"获取k8s[{k8s_kubeconfig_db.k8s_id}_{k8s_kubeconfig_configs_db.k8s_name}] client失败: {e}")
                continue

            all_sts_in_k8s = k8s_common_operate.list_sts_by_label(app_k8s_client)
            if not all_sts_in_k8s:
                #TODO: 删除数据库中该集群下的容器实例数据
                # AiInstanceSQL.delete_ai_instance_info_by_k8s_id(k8s_kubeconfig_db.k8s_id)
                continue

            all_instance_in_k8s_db = AiInstanceSQL.list_ai_instance_info_by_k8s_id({k8s_kubeconfig_db.k8s_id})
            if not all_instance_in_k8s_db:
                #TODO: 删除该集群下的所有容器实例service、名命名空间、sts
                pass

            list_instance_real_name_db = [instance_db.instance_real_name for instance_db in all_instance_in_k8s_db]
            for sts in all_sts_in_k8s:
                if sts.metadata.name in list_instance_real_name_db:
                    #TODO: 更新容器实例状态等字段信息
                    ai_instance_db = AiInstanceSQL.get_ai_instance_info_by_instance_name(sts.metadata.name)
                    ai_instance_db.instance_real_status = sts.status.phase if sts.status.phase else "creating"
                    if ai_instance_db.instance_real_status == "running":
                        ai_instance_db.instance_status = "running"
                    elif ai_instance_db.instance_real_status in ("ImagePullBackOff", "ErrImagePull", "CrashLoopBackOff", "Error", "CreateContainerError",):
                        ai_instance_db.instance_status = "failed"
                    AiInstanceSQL.update_ai_instance_info(ai_instance_db)
                    continue
                else:
                    # k8s存在，而dingo-command 未保存sts数据，则从k8s上删除该数据
                    try:
                        k8s_common_operate.delete_sts_by_name(app_k8s_client, sts.metadata.name)
                    except Exception as e:
                        LOG.error(f"删除sts[{sts.metadata.name}]失败: {e}")
                        continue

            list_sts_name_in_k8s = [sts_in_k8s.metadata.name for sts_in_k8s in all_sts_in_k8s]
            for instance_db in all_instance_in_k8s_db:
                if instance_db.instance_name not in list_sts_name_in_k8s:
                    # dingo-command中容器实例不在k8s上，则从dingo-command数据库中删除该数据
                    AiInstanceSQL.delete_ai_instance_info_by_instance_id(instance_db.instance_id)
                    LOG.info(f"ai instance name[{instance_db.instance_name} + ' , real name: ' + {instance_db.instance_real_name}] deleted from dingo-command, duo to not exist in k8s")
                else:
                    continue

    except Exception as e:
        LOG.error(f"同步容器实例失败: {e}")
    LOG.error(f"同步容器实例结束时间: {datatime_util.get_now_time_in_timestamp_format()}, 耗时：{datatime_util.get_now_time_in_timestamp_format()-start_time}秒")


def convert_ai_instance_info_db(self, ai_instance):
    ai_instance_info_db = AiInstanceInfo(id=uuid.uuid4().hex,
                                         instance_name=ai_instance.name,
                                         # instance_status="creating",
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
                                         stop_time=ai_instance.stop_time,
                                         auto_delete_time=ai_instance.auto_delete_time,
                                         instance_config=json.dumps(
                                             ai_instance.instance_config.dict()) if ai_instance.instance_config else None,
                                         instance_volumes=json.dumps(
                                             ai_instance.volumes.dict()) if ai_instance.volumes else None,
                                         instance_envs=json.dumps(
                                             ai_instance.instance_envs) if ai_instance.instance_envs else None,
                                         instance_description=ai_instance.description
                                         )
    return ai_instance_info_db
