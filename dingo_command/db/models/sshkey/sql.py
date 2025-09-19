from __future__ import annotations

from dingo_command.db.engines.mysql import get_session
from dingo_command.db.models.sshkey.models import KeyInfo
from dingo_command.utils.helm.util import ChartLOG as Log
from sqlalchemy import delete

key_dir_dic = {"create_time": KeyInfo.create_time, "name": KeyInfo.name, "status": KeyInfo.status}


class KeySQL:

    @classmethod
    def list_keys(cls, query_params, page=1, page_size=10, sort_keys=None, sort_dirs="ascend"):
        # 获取session
        session = get_session()
        with session.begin():
            # 根据query_params查询数据
            query = session.query(KeyInfo)

            # 数据库查询参数
            if "id" in query_params and query_params["id"]:
                query = query.filter(KeyInfo.id == query_params["id"])
            if "name" in query_params and query_params["name"]:
                query = query.filter(KeyInfo.name.like(f"%{query_params['name']}%"))
            if "full_name" in query_params and query_params["full_name"]:
                query = query.filter(KeyInfo.name == query_params["full_name"])
            if "status" in query_params and query_params["status"]:
                query = query.filter(KeyInfo.status == query_params["status"])
            if "tenant_id" in query_params and query_params["tenant_id"]:
                query = query.filter(KeyInfo.tenant_id == query_params["tenant_id"])
            if "user_id" in query_params and query_params["user_id"]:
                query = query.filter(KeyInfo.user_id == query_params["user_id"])
            if "is_manager" in query_params and query_params["is_manager"]:
                query = query.filter(KeyInfo.is_manager == query_params["is_manager"])
            if "user_name" in query_params and query_params["user_name"]:
                query = query.filter(KeyInfo.user_name.like(f"%{query_params['user_name']}%"))
            # 总数
            count = query.count()
            # 排序
            if sort_keys is not None and sort_keys in key_dir_dic:
                if sort_dirs == "ascend" or sort_dirs is None:
                    query = query.order_by(key_dir_dic[sort_keys].asc())
                elif sort_dirs == "descend":
                    query = query.order_by(key_dir_dic[sort_keys].desc())
            else:
                query = query.order_by(KeyInfo.name.desc())
            # 分页条件
            page_size = int(page_size)
            page_num = int(page)
            # 查询所有数据
            if page_size == -1:
                return count, query.all()
            # 页数计算
            start = (page_num - 1) * page_size
            query = query.limit(page_size).offset(start)
            key_list = query.all()
            # 返回
            return count, key_list

    @classmethod
    def create_key(cls, key):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.add(key)

    @classmethod
    def create_key_list(cls, key_list):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        try:
            with session.begin():
                session.bulk_save_objects(key_list)
        except Exception as e:
            Log.error("create_chart_list failed, error: %s" % str(e))
            session.rollback()
            raise

    @classmethod
    def update_key(cls, key):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.merge(key)

    @classmethod
    def update_key_list(cls, key_list):
        session = get_session()
        try:
            with session.begin():
                # 使用bulk_save_objects替代循环merge
                session.bulk_save_objects(key_list, update_changed_only=True)
        except Exception as e:
            Log.error("update_key_list failed, error: %s" % str(e))
            session.rollback()
            raise

    @classmethod
    def delete_key_list(cls, key_list):
        session = get_session()
        try:
            key_ids = [key.id for key in key_list]
            if not key_ids:
                return

            # 直接执行原生批量删除
            stmt = delete(KeyInfo).where(KeyInfo.id.in_(key_ids))
            with session.begin():
                session.execute(stmt)
        except Exception as e:
            session.rollback()
            Log.error(f"原生SQL删除失败: {str(e)}")
            raise
        finally:
            session.close()

    @classmethod
    def delete_key(cls, key):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.delete(key)