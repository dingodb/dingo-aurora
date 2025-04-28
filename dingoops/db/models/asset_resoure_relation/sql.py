# 数据表对应的model对象

from __future__ import annotations

from sqlalchemy import func, distinct

from db.engines.mysql import get_session
from db.models.asset.models import AssetBasicInfo, AssetCustomersInfo
from db.models.asset_resoure_relation.models import AssetResourceRelationInfo

# 资源详情列表排序字段字典
resource_detail_list_dir_dic= {"resource_name":AssetResourceRelationInfo.resource_name, "resource_status":AssetResourceRelationInfo.resource_status,"asset_name":AssetBasicInfo.name,
                               "asset_status":AssetBasicInfo.asset_status, "resource_user_name":AssetResourceRelationInfo.resource_user_name, "resource_project_name": AssetResourceRelationInfo.resource_project_name,}

class AssetResourceRelationSQL:

    @classmethod
    def vpc_resource_statistic_list(cls, query_params, page=1, page_size=10, sort_keys=None, sort_dirs="ascend"):
        # 获取session
        session = get_session()
        with session.begin():
            query = session.query(AssetResourceRelationInfo.resource_project_id.label("resource_project_id"),
                                  AssetResourceRelationInfo.resource_project_name.label("resource_project_name"),
                                  func.count(AssetResourceRelationInfo.resource_id).label("resource_count"),
                                  func.count(AssetResourceRelationInfo.asset_id).label("asset_count")
                                  )
            # 查询
            query = query.filter(AssetResourceRelationInfo.resource_project_id.isnot(None))
            # 数据库查询参数
            if 'resource_project_name' in query_params and query_params['resource_project_name']:
                query = query.filter(AssetResourceRelationInfo.resource_project_name.like('%' + query_params['resource_project_name'] + '%'))
            # 总数
            count = query.count()
            # 排序
            if sort_keys is not None and sort_keys  == "resource_project_name":
                if sort_dirs == "ascend" or sort_dirs is None:
                    query = query.order_by(AssetResourceRelationInfo.resource_project_name.asc())
                elif sort_dirs == "descend":
                    query = query.order_by(AssetResourceRelationInfo.resource_project_name.desc())
            else:
                query = query.order_by(AssetResourceRelationInfo.create_date.desc())
            # 分页条件
            page_size = int(page_size)
            page_num = int(page)
            # 查询所有数据
            if page_size == -1:
                return count, query.all()
            # 页数计算
            start = (page_num - 1) * page_size
            query = query.limit(page_size).offset(start)
            resource_asset_list = query.all()
            # 返回
            return count, resource_asset_list

    @classmethod
    def resource_detail_list(cls, resource_project_id, query_params, page=1, page_size=10, sort_keys=None, sort_dirs="ascend"):
        # 获取session
        session = get_session()
        with session.begin():
            query = session.query(AssetResourceRelationInfo.resource_id.label("resource_id"),
                                  AssetResourceRelationInfo.resource_name.label("resource_name"),
                                  AssetResourceRelationInfo.resource_status.label("resource_status"),
                                  AssetResourceRelationInfo.asset_id.label("asset_id"),
                                  AssetBasicInfo.name.label("asset_name"),
                                  AssetBasicInfo.asset_status.label("asset_status"),
                                  AssetResourceRelationInfo.resource_user_id.label("resource_user_id"),
                                  AssetResourceRelationInfo.resource_user_name.label("resource_user_name"),
                                  AssetResourceRelationInfo.resource_project_id.label("resource_project_id"),
                                  AssetResourceRelationInfo.resource_project_name.label("resource_project_name"),
                                  )
            # 外连接
            query = query.outerjoin(AssetBasicInfo, AssetBasicInfo.id == AssetResourceRelationInfo.asset_id)
            if 'resource_name' in query_params and query_params['resource_name']:
                query = query.filter(AssetResourceRelationInfo.resource_name.like('%' + query_params['resource_name'] + '%'))
            if 'resource_status' in query_params and query_params['resource_status']:
                query = query.filter(AssetResourceRelationInfo.resource_status == query_params['resource_status'])
            if 'asset_name' in query_params and query_params['asset_name']:
                query = query.filter(AssetBasicInfo.name.like('%' + query_params['asset_name'] + '%'))
            if 'asset_status' in query_params and query_params['asset_status']:
                query = query.filter(AssetBasicInfo.asset_status == query_params['asset_status'])
            if 'resource_user_name' in query_params and query_params['resource_user_name']:
                query = query.filter(AssetResourceRelationInfo.resource_user_name.like('%' + query_params['resource_user_name'] + '%'))
            if 'resource_project_name' in query_params and query_params['resource_project_name']:
                query = query.filter(AssetResourceRelationInfo.resource_project_name.like('%' + query_params['resource_project_name'] + '%'))
            # 查询
            query = query.filter(AssetResourceRelationInfo.resource_project_id == resource_project_id, AssetResourceRelationInfo.resource_project_id.isnot(None))

            # 总数
            count = query.count()
            # 排序
            if sort_keys is not None and sort_keys in resource_detail_list_dir_dic:
                if sort_dirs == "ascend" or sort_dirs is None:
                    query = query.order_by(resource_detail_list_dir_dic[sort_keys].asc())
                elif sort_dirs == "descend":
                    query = query.order_by(resource_detail_list_dir_dic[sort_keys].desc())
            else:
                query = query.order_by(AssetResourceRelationInfo.create_date.desc())
            # 分页条件
            page_size = int(page_size)
            page_num = int(page)
            # 查询所有数据
            if page_size == -1:
                return count, query.all()
            # 页数计算
            start = (page_num - 1) * page_size
            query = query.limit(page_size).offset(start)
            resource_asset_detail_list = query.all()
            # 返回
            return count, resource_asset_detail_list

    @classmethod
    def create_asset_resource_relation(cls, asset_resource_relation):
        session = get_session()
        with session.begin():
            session.add(asset_resource_relation)

    @classmethod
    def delete_asset_resource_relation_by_relation_id(cls, relation_id):
        session = get_session()
        with session.begin():
            session.query(AssetResourceRelationInfo).filter(AssetResourceRelationInfo.id == relation_id).delete()

    @classmethod
    def delete_asset_resource_relation_by_resource_id(cls, resource_id):
        session = get_session()
        with session.begin():
            session.query(AssetResourceRelationInfo).filter(
                AssetResourceRelationInfo.resource_id == resource_id).delete()

    @classmethod
    def update_asset_resource_relation(cls, asset_resource_relation):
        session = get_session()
        with session.begin():
            session.merge(asset_resource_relation)

    @classmethod
    def get_asset_resource_relation_by_resource_id(cls, resource_id):
        session = get_session()
        with session.begin():
            return session.query(AssetResourceRelationInfo).filter(
                AssetResourceRelationInfo.resource_id == resource_id).first()

    @classmethod
    def get_all_asset_resource_relation(cls):
        session = get_session()
        with session.begin():
            return session.query(AssetResourceRelationInfo).all()

    @classmethod
    def get_all_asset_resource_relation_count(cls):
        session = get_session()
        with session.begin():
            return session.query(AssetResourceRelationInfo).count()

    @classmethod
    def get_resource_project_not_empty_count(cls):
        session = get_session()
        with ((session.begin())):
            return session.query(distinct(AssetResourceRelationInfo.resource_project_id.isnot(None))).count()

    @classmethod
    def get_all_resource_status_info(cls):
        session = get_session()
        with session.begin():
            return session.query(AssetResourceRelationInfo.resource_id, AssetResourceRelationInfo.resource_name, AssetResourceRelationInfo.resource_status).all()