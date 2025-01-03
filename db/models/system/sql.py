# 数据表对应的model对象

from __future__ import annotations
from db.engines.mysql import get_session
from db.models.system.models import OperateLog


class SystemSQL:

    @classmethod
    def list_operate_log(cls, resource_id=None, page=1, page_size=10, field=None, dir="ASC"):
        session = get_session()
        with session.begin():
            query = session.query(OperateLog)
            # 数据库查询参数
            if resource_id is not None:
                query = query.filter(OperateLog.resource_id == resource_id)
            # 总数
            count = query.count()
            # 分页条件
            page_size = int(page_size)
            page_num = int(page)
            # 查询所有数据
            if page_size == -1:
                return count, query.all()
            # 页数计算
            start = (page_num - 1) * page_size
            query = query.limit(page_size).offset(start)
            assert_list = query.all()
            # 返回
            return count, assert_list

    @classmethod
    def create_operate_log(cls, operate_log_info):
        session = get_session()
        with session.begin():
            session.add(operate_log_info)
