# 数据表对应的model对象

from __future__ import annotations

from db.engines.mysql import get_session
from db.models.asset_resoure_relation.models import AssetResourceRelationInfo


class AssetReSourceRelationSQL:

    @classmethod
    def list_asset_basic_info(cls, query_params, page=1, page_size=10, field=None, dir="ascend"):
        # 获取session
        session = get_session()
        with session.begin():
            query = session.query(AssetResourceRelationInfo)
            # 数据库查询参数
            if 'resource_name' in query_params and query_params['resource_name']:
                query = query.filter(AssetResourceRelationInfo.resource_name.like('%' + query_params['resource_name'] + '%'))
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
    def create_asset_resource_relation(cls, asset_resource_relation):
        session = get_session()
        with session.begin():
            session.add(asset_resource_relation)


    @classmethod
    def delete_asset_resource_relation(cls, relation_id):
        session = get_session()
        with session.begin():
            session.query(AssetResourceRelationInfo).filter(AssetResourceRelationInfo.id == relation_id).delete()

    @classmethod
    def update_asset_resource_relation(cls, asset_resource_relation):
        session = get_session()
        with session.begin():
            session.merge(asset_resource_relation)