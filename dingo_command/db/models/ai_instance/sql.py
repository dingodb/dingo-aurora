# 数据表对应的model对象

from __future__ import annotations
from dingo_command.db.engines.mysql import get_session
from dingo_command.db.models.ai_instance.models import AiK8sKubeConfigConfigs, AiInstanceInfo, AiK8sNodeResourceInfo, AccountInfo

# 容器实例排序字段字典
ai_instance_dir_dic= {"instance_name":AiInstanceInfo.instance_name}


class AiInstanceSQL:

    @classmethod
    def save_ai_instance_info(cls, ai_instance_db):
        session = get_session()
        with session.begin():
            session.add(ai_instance_db)

    @classmethod
    def update_ai_instance_info(cls, ai_instance_db):
        session = get_session()
        with (session.begin()):
            session.merge(ai_instance_db)

    @classmethod
    def update_specific_fields_instance(cls, ai_instance_db, **update_data):
        """
        更新AI实例信息（支持部分更新）

        :param ai_instance_db: 要更新的AI实例ORM对象
        :param update_data: 需要更新的字段字典（可选）
        :return: 更新后的实例对象
        """
        session = get_session()
        with session.begin():
            # 如果有更新数据，先应用到对象
            if update_data:
                for key, value in update_data.items():
                    if hasattr(ai_instance_db, key):
                        setattr(ai_instance_db, key, value)

            # 使用merge确保数据一致性（会返回新对象）
            merged_instance = session.merge(ai_instance_db)
            return merged_instance

    @classmethod
    def delete_ai_instance_info_by_id(cls, id):
        session = get_session()
        with session.begin():
            session.query(AiInstanceInfo) \
                .filter(AiInstanceInfo.id == id).delete()


    @classmethod
    def delete_ai_instance_info_by_k8s_id(cls, k8s_id):
        session = get_session()
        with session.begin():
            count = session.query(AiInstanceInfo) \
                .filter(AiInstanceInfo.instance_k8s_id == k8s_id).delete()
            return count

    @classmethod
    def get_instances_by_k8s_and_node(cls, k8s_id, node_name):
        session = get_session()
        with (session.begin()):
            return session.query(AiInstanceInfo).\
                filter(AiInstanceInfo.instance_k8s_id == k8s_id). \
                filter(AiInstanceInfo.instance_node_name == node_name).first()

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
            query = session.query(AiInstanceInfo.id.label("id"),
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
            if "uuid" in query_params and query_params["uuid"]:
                query = query.filter(AiInstanceInfo.id == query_params["uuid"])
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

    # ================= 以下为 node resource 相关 =======================
    @classmethod
    def get_k8s_node_resource_by_k8s_id(cls, k8s_id):
        session = get_session()
        with session.begin():
            return session.query(AiK8sNodeResourceInfo).filter(AiK8sNodeResourceInfo.k8s_id == k8s_id).all()

    @classmethod
    def get_k8s_node_resource_by_k8s_id_and_node_name(cls, k8s_id, node_name):
        session = get_session()
        with session.begin():
            return session.query(AiK8sNodeResourceInfo).filter(AiK8sNodeResourceInfo.k8s_id == k8s_id, AiK8sNodeResourceInfo.node_name == node_name).first()

    @classmethod
    def delete_k8s_node_resource_by_k8s_id(cls, k8s_id):
        session = get_session()
        with session.begin():
            return session.query(AiK8sNodeResourceInfo).filter(AiK8sNodeResourceInfo.k8s_id == k8s_id).delete()

    @classmethod
    def delete_k8s_node_resource(cls, k8s_id, node_name):
        session = get_session()
        with session.begin():
            return session.query(AiK8sNodeResourceInfo). \
                filter(AiK8sNodeResourceInfo.k8s_id == k8s_id). \
                filter(AiK8sNodeResourceInfo.node_name == node_name).delete()

    @classmethod
    def save_k8s_node_resource(cls, k8s_node_resource_db):
        session = get_session()
        with session.begin():
            session.add(k8s_node_resource_db)

    @classmethod
    def update_k8s_node_resource(cls, k8s_node_resource_db):
        session = get_session()
        with (session.begin()):
            session.merge(k8s_node_resource_db)

    @classmethod
    def list_instances_to_auto_stop(cls, now_time):
        session = get_session()
        with session.begin():
            return session.query(AiInstanceInfo) \
                .filter(AiInstanceInfo.stop_time.isnot(None)) \
                .filter(AiInstanceInfo.stop_time <= now_time) \
                .all()

    @classmethod
    def list_instances_to_auto_delete(cls, now_time):
        session = get_session()
        with session.begin():
            return session.query(AiInstanceInfo) \
                .filter(AiInstanceInfo.auto_delete_time.isnot(None)) \
                .filter(AiInstanceInfo.auto_delete_time <= now_time) \
                .all()

    # ================= 以下为 account 相关 =======================
    @classmethod
    def save_account_info(cls, account_db):
        session = get_session()
        with session.begin():
            session.add(account_db)

    @classmethod
    def update_account_info(cls, account_db):
        session = get_session()
        with session.begin():
            session.merge(account_db)

    @classmethod
    def delete_account_info_by_id(cls, id):
        session = get_session()
        with session.begin():
            session.query(AccountInfo).filter(AccountInfo.id == id).delete()

    @classmethod
    def get_account_info_by_account(cls, account):
        session = get_session()
        with session.begin():
            return session.query(AccountInfo).filter(AccountInfo.account == account).first()

    @classmethod
    def get_account_info_by_id(cls, id):
        session = get_session()
        with session.begin():
            return session.query(AccountInfo).filter(AccountInfo.id == id).first()

    @classmethod
    def get_account_info_by_account_excluding_id(cls, account, exclude_id):
        session = get_session()
        with session.begin():
            return session.query(AccountInfo).filter(AccountInfo.account == account, AccountInfo.id != exclude_id).first()
