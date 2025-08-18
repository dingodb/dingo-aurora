# 数据表对应的model对象

from __future__ import annotations

from sqlalchemy.testing import not_in

from dingo_command.db.engines.mysql import get_session
from dingo_command.db.models.ai_instance.models import AiK8sKubeConfigConfigs, AiInstanceInfo
from dingo_command.utils.constant import STOP_STATUS

# 容器实例排序字段字典
ai_instance_dir_dic= {"instance_name":AiInstanceInfo.instance_name}


class AiInstanceSQL:

    @classmethod
    def save_ai_instance_info(cls, ai_instance_db):
        session = get_session()
        with session.begin():
            session.add(ai_instance_db)
            # 立即刷新以获取生成的ID
            session.flush()

            # 返回实例ID（假设主键字段为id）
            return ai_instance_db.id
    @classmethod
    def update_ai_instance_info(cls, ai_instance_db):
        session = get_session()
        with session.begin():
            session.merge(ai_instance_db)

    @classmethod
    def delete_ai_instance_info_not_stopped(cls, k8s_id):
        session = get_session()
        with session.begin():
            count = session.query(AiInstanceInfo) \
                .filter(AiInstanceInfo.instance_k8s_id == k8s_id,AiInstanceInfo.instance_status.notin_(STOP_STATUS)
            ).delete(synchronize_session=False)

            print(f"Deleted {count} non-stopped AI instances for k8s_id: {k8s_id}")
            return count

    @classmethod
    def delete_ai_instance_info_by_instance_id(cls, instance_id):
        session = get_session()
        with session.begin():
            session.query(AiInstanceInfo) \
                .filter(AiInstanceInfo.instance_id == instance_id).delete(synchronize_session=False)


    @classmethod
    def delete_ai_instance_info_by_k8s_id(cls, k8s_id):
        session = get_session()
        with session.begin():
            count = session.query(AiInstanceInfo) \
                .filter(AiInstanceInfo.instance_k8s_id == k8s_id).delete(synchronize_session=False)

            print(f"Deleted {count} non-stopped AI instances for k8s_id: {k8s_id}")
            return count

    @classmethod
    def get_ai_instance_info_by_instance_id(cls, instance_id):
        session = get_session()
        with (session.begin()):
            return session.query(AiInstanceInfo).filter(AiInstanceInfo.instance_id == instance_id).first()

    @classmethod
    def get_ai_instance_info_by_instance_name(cls, instance_name):
        session = get_session()
        with (session.begin()):
            return session.query(AiInstanceInfo).filter(AiInstanceInfo.instance_name == instance_name).first()

    @classmethod
    def get_ai_instance_info_by_id(cls, id):
        session = get_session()
        with (session.begin()):
            return session.query(AiInstanceInfo).filter(AiInstanceInfo.id == id).first()

    @classmethod
    def list_ai_instance_info_by_k8s_id(cls, k8s_id):
        session = get_session()
        with session.begin():
            return session.query(AiInstanceInfo).filter(AiInstanceInfo.instance_k8s_id == k8s_id).all()

    @classmethod
    def list_ai_instance_info(cls, query_params, page=1, page_size=10, sort_keys=None, sort_dirs="ascend"):
        # 获取session
        session = get_session()
        with session.begin():
            # 查询语句
            query = session.query(AiInstanceInfo.instance_id.label("instance_id"),
                                  AiInstanceInfo.instance_name.label("instance_name"),
                                  AiInstanceInfo.instance_real_name.label("instance_real_name"),
                                  AiInstanceInfo.instance_status.label("instance_status"),
                                  AiInstanceInfo.instance_k8s_type.label("instance_k8s_type"),
                                  AiInstanceInfo.instance_k8s_id.label("instance_k8s_id"),
                                  AiInstanceInfo.instance_k8s_name.label("instance_k8s_name"),
                                  AiInstanceInfo.instance_project_id.label("instance_project_id"),
                                  AiInstanceInfo.instance_project_name.label("instance_project_name"),
                                  AiInstanceInfo.instance_user_id.label("instance_user_id"),
                                  AiInstanceInfo.instance_user_name.label("instance_user_name"),
                                  AiInstanceInfo.instance_root_account_id.label("instance_root_account_id"),
                                  AiInstanceInfo.instance_root_account_name.label("instance_root_account_name"),
                                  AiInstanceInfo.dev_tool.label("dev_tool"),
                                  AiInstanceInfo.instance_image.label("instance_image"),
                                  AiInstanceInfo.image_type.label("image_type"),
                                  AiInstanceInfo.stop_time.label("stop_time"),
                                  AiInstanceInfo.auto_delete_time.label("auto_delete_time"),
                                  AiInstanceInfo.instance_config.label("instance_config"),
                                  AiInstanceInfo.instance_volumes.label("instance_volumes"),
                                  AiInstanceInfo.instance_envs.label("instance_envs"),
                                  AiInstanceInfo.instance_create_time.label("instance_create_time"))

            # 数据库查询参数
            if "instance_name" in query_params and query_params["instance_name"]:
                query = query.filter(AiInstanceInfo.instance_name.like('%' + str(query_params["instance_name"]) + '%'))
            if "instance_id" in query_params and query_params["instance_id"]:
                query = query.filter(AiInstanceInfo.instance_id == query_params["instance_id"])
            if "instance_status" in query_params and query_params["instance_status"]:
                # 状态拆分
                instance_status_arr = query_params["instance_status"].split(",")
                query = query.filter(AiInstanceInfo.instance_status.in_(instance_status_arr))

            # 总数
            count = query.count()
            # 排序
            if sort_keys is not None and sort_keys in ai_instance_dir_dic:
                if sort_dirs == "ascend" or sort_dirs is None:
                    query = query.order_by(ai_instance_dir_dic[sort_keys].asc())
                elif sort_dirs == "descend":
                    query = query.order_by(ai_instance_dir_dic[sort_keys].desc())
            else:
                query = query.order_by(AiInstanceInfo.instance_create_time.desc())
            # 分页条件
            page_size = int(page_size)
            page_num = int(page)
            # 查询所有数据
            if page_size == -1:
                return count, query.all()
            # 页数计算
            start = (page_num - 1) * page_size
            query = query.limit(page_size).offset(start)
            ai_instance_info_list = query.all()
            # 返回
            return count, ai_instance_info_list
    # ================= 以下为 kubeconfig 相关 =======================
    @classmethod
    def get_k8s_kubeconfig_info_by_k8s_id(cls, k8s_id):
        session = get_session()
        with session.begin():
            return session.query(AiK8sKubeConfigConfigs).filter(AiK8sKubeConfigConfigs.k8s_id == k8s_id).first()

    @classmethod
    def list_k8s_kubeconfig_configs(cls):
        session = get_session()
        with session.begin():
            return session.query(AiK8sKubeConfigConfigs).all()
