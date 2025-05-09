# 数据表对应的model对象

from __future__ import annotations

from dingo_command.db.engines.mysql import get_session
from dingo_command.db.models.instance.models import Instance

instance_dir_dic= {"create_time":Instance.create_time, "name":Instance.name,"status":Instance.status,
                  "region_name":Instance.region}

class InstanceSQL:

    @classmethod
    def list_instances(cls, query_params, page=1, page_size=10, sort_keys=None, sort_dirs="ascend"):
        # 获取session
        session = get_session()
        with session.begin():
            # 根据query_params查询数据
            query = session.query(Instance)
            # 查询语句

            # 数据库查询参数
            if "id" in query_params and query_params["id"]:
                query = query.filter(Instance.id == query_params["id"])
            if "cluster_name" in query_params and query_params["cluster_name"]:
                query = query.filter(Instance.cluster_name.like('%' + query_params["cluster_name"] + '%'))
            if "cluster_id" in query_params and query_params["cluster_id"]:
                query = query.filter(Instance.cluster_id == query_params["cluster_id"])
            # 总数
            count = query.count()
            # 排序
            if sort_keys is not None and sort_keys in instance_dir_dic:
                if sort_dirs == "ascend" or sort_dirs is None :
                    query = query.order_by(instance_dir_dic[sort_keys].asc())
                elif sort_dirs == "descend":
                    query = query.order_by(instance_dir_dic[sort_keys].desc())
            else:
                query = query.order_by(Instance.create_time.desc())
            # 分页条件
            page_size = int(page_size)
            page_num = int(page)
            # 查询所有数据
            if page_size == -1:
                return count, query.all()
            # 页数计算
            start = (page_num - 1) * page_size
            query = query.limit(page_size).offset(start)
            node_list = query.all()
            # 返回
            return count, node_list

    @classmethod
    def create_instance(cls, instance):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.add(instance)

    @classmethod
    def create_instance_list(cls, instance_list):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        for instance in instance_list:
            cls.create_instance(instance)

    @classmethod
    def update_instance(cls, instance):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.merge(instance)

    @classmethod
    def update_instance_list(cls, instance_list):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        for instance in instance_list:
            cls.update_instance(instance)

    @classmethod
    def delete_instance_list(cls, instance_list):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        for instance in instance_list:
            cls.delete_instance(instance)

    @classmethod
    def delete_instance(cls, instance):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.delete(instance)