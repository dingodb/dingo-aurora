# 数据表对应的model对象

from __future__ import annotations

from sqlalchemy import func, asc, desc, or_, and_

from dingo_command.db.engines.mysql import get_session
from dingo_command.db.models.asset.models import AssetBasicInfo
from dingo_command.db.models.asset_resoure_relation.models import AssetResourceRelationInfo, ResourceMetricsConfig, \
    ResourceMetrics

# 资源详情列表排序字段字典
resource_detail_list_dir_dic= {"resource_name":AssetResourceRelationInfo.resource_name, "resource_status":AssetResourceRelationInfo.resource_status,"asset_name":AssetBasicInfo.name,
                               "asset_status":AssetBasicInfo.asset_status, "resource_user_name":AssetResourceRelationInfo.resource_user_name, "resource_project_name": AssetResourceRelationInfo.resource_project_name,}

class AssetResourceRelationSQL:

    @classmethod
    def project_resource_statistic_list(cls, query_params, page=1, page_size=10, sort_keys=None, sort_dirs="ascend"):
        # 获取session
        session = get_session()
        with session.begin():
            query = session.query(AssetResourceRelationInfo.resource_project_id.label("resource_project_id"),
                                  AssetResourceRelationInfo.resource_project_name.label("resource_project_name"),
                                  func.count(AssetResourceRelationInfo.resource_id).label("resource_count"),
                                  func.count(AssetResourceRelationInfo.asset_id).label("asset_count")
                                  )
            # 查询
            query = query.filter(AssetResourceRelationInfo.resource_project_id.isnot(None)).group_by(AssetResourceRelationInfo.resource_project_id)
            # 数据库查询参数
            if 'resource_project_name' in query_params and query_params['resource_project_name']:
                query = query.filter(AssetResourceRelationInfo.resource_project_name.like('%' + query_params['resource_project_name'] + '%'))
            # 总数
            count = query.count()
            # 排序
            if sort_keys is not None:
                if sort_keys  == "resource_project_name":
                    if sort_dirs == "ascend" or sort_dirs is None:
                        query = query.order_by(AssetResourceRelationInfo.resource_project_name.asc())
                    elif sort_dirs == "descend":
                        query = query.order_by(AssetResourceRelationInfo.resource_project_name.desc())
                elif sort_keys  == "resource_count":
                    if sort_dirs == "ascend" or sort_dirs is None:
                        query = query.order_by(asc("resource_count"))
                    elif sort_dirs == "descend":
                        query = query.order_by(desc("resource_count"))
                elif sort_keys == "asset_count":
                    if sort_dirs == "ascend" or sort_dirs is None:
                        query = query.order_by(asc("asset_count"))
                    elif sort_dirs == "descend":
                        query = query.order_by(desc("asset_count"))
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
            query = query.outerjoin(AssetBasicInfo, AssetBasicInfo.id == AssetResourceRelationInfo.asset_id). \
                outerjoin(ResourceMetrics, ResourceMetrics.resource_id == AssetResourceRelationInfo.resource_id).group_by(AssetResourceRelationInfo.resource_id)
            if 'resource_name' in query_params and query_params['resource_name']:
                query = query.filter(AssetResourceRelationInfo.resource_name.like('%' + query_params['resource_name'] + '%'))
            if 'resource_status' in query_params and query_params['resource_status']:
                # 状态拆分
                resource_status_arr = query_params["resource_status"].split(",")
                query = query.filter(AssetResourceRelationInfo.resource_status.in_(resource_status_arr))
            if 'asset_name' in query_params and query_params['asset_name']:
                query = query.filter(AssetBasicInfo.name.like('%' + query_params['asset_name'] + '%'))
            if 'asset_status' in query_params and query_params['asset_status']:
                # 状态拆分
                asset_status_arr = query_params["asset_status"].split(",")
                query = query.filter(AssetBasicInfo.asset_status.in_(asset_status_arr))
            if 'resource_user_name' in query_params and query_params['resource_user_name']:
                query = query.filter(AssetResourceRelationInfo.resource_user_name.like('%' + query_params['resource_user_name'] + '%'))
            if 'resource_project_name' in query_params and query_params['resource_project_name']:
                query = query.filter(AssetResourceRelationInfo.resource_project_name.like('%' + query_params['resource_project_name'] + '%'))
            # 查询
            if resource_project_id is not None:
                query = query.filter(AssetResourceRelationInfo.resource_project_id == resource_project_id, AssetResourceRelationInfo.resource_project_id.isnot(None))
            else:
                query = query.filter(AssetResourceRelationInfo.resource_project_id.isnot(None))

            # 总数
            count = query.count()
            # 排序
            if sort_keys is not None:
                if sort_keys in resource_detail_list_dir_dic:
                    if sort_dirs == "ascend" or sort_dirs is None:
                        query = query.order_by(resource_detail_list_dir_dic[sort_keys].asc())
                    elif sort_dirs == "descend":
                        query = query.order_by(resource_detail_list_dir_dic[sort_keys].desc())
                else:
                    from sqlalchemy import case, null
                    metric_name = sort_keys.replace("resource_", "")

                    # 构建case表达式处理空值
                    order_expr = case(
                (ResourceMetrics.name == metric_name, ResourceMetrics.data),
                        else_=0  # 默认值为0，可根据业务需求调整
                    )
                    if sort_dirs == "ascend" or sort_dirs is None:
                        query = query.order_by(order_expr.asc())
                    elif sort_dirs == "descend":
                        query = query.order_by(order_expr.desc())
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
    def delete_all_asset_resource_relation_data(cls):
        session = get_session()
        with session.begin():
            return session.query(AssetResourceRelationInfo).delete()

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
    def get_project_resource_project_not_empty_count(cls):
        session = get_session()
        with ((session.begin())):
            return session.query(AssetResourceRelationInfo). \
                filter(AssetResourceRelationInfo.resource_project_id.isnot(None)). \
                group_by(AssetResourceRelationInfo.resource_project_id).count()

    @classmethod
    def get_all_resource_status_info(cls):
        session = get_session()
        with session.begin():
            return session.query(AssetResourceRelationInfo.resource_project_id,
                                 AssetResourceRelationInfo.resource_project_name,
                                 AssetResourceRelationInfo.resource_id,
                                 AssetResourceRelationInfo.resource_name,
                                 AssetResourceRelationInfo.resource_status,
                                 AssetResourceRelationInfo.node_name).all()

    @classmethod
    def get_unassigned_asset_count(cls):
        session = get_session()
        with session.begin():
            return session.query(AssetResourceRelationInfo). \
                filter(
                or_(
                    AssetResourceRelationInfo.asset_id.is_(None),
                    and_(
                        AssetResourceRelationInfo.asset_id.isnot(None),
                        AssetResourceRelationInfo.resource_name.is_(None)
                    )
                )
            ).count()

    @classmethod
    def get_asset_id_not_empty_list(cls):
        session = get_session()
        with session.begin():
            return session.query(AssetResourceRelationInfo). \
                filter(AssetResourceRelationInfo.asset_id.isnot(None)).all()

    @classmethod
    def get_resource_relation_asset_failure_count(cls):
        session = get_session()
        with session.begin():
            query = session.query(AssetResourceRelationInfo). \
                        outerjoin(AssetBasicInfo, AssetBasicInfo.id == AssetResourceRelationInfo.asset_id). \
                        filter(AssetResourceRelationInfo.asset_id.isnot(None)). \
                        filter(AssetBasicInfo.asset_status == "3")
            return query.count()


    @classmethod
    def get_all_resource_metrics_config(cls):
        session = get_session()
        with session.begin():
            return session.query(ResourceMetricsConfig).all()

    @classmethod
    def update_resource_metrics(cls, resource_metrics):
        session = get_session()
        with session.begin():
            session.merge(resource_metrics)

    @classmethod
    def create_resource_metrics(cls, resource_metrics):
        session = get_session()
        with session.begin():
            session.add(resource_metrics)

    @classmethod
    def get_resource_metrics_by_resource_id(cls, resource_id):
        session = get_session()
        with session.begin():
            return session.query(ResourceMetrics).filter(ResourceMetrics.resource_id == resource_id).all()

    @classmethod
    def get_resource_metrics_by_resource_id_and_name(cls, resource_id, name):
        session = get_session()
        with session.begin():
            return session.query(ResourceMetrics).filter(ResourceMetrics.resource_id == resource_id, ResourceMetrics.name == name).first()

    @classmethod
    def delete_resource_metrics_by_resource_id(cls, resource_id):
        session = get_session()
        with session.begin():
            return session.query(ResourceMetrics).filter(ResourceMetrics.resource_id == resource_id).delete()

    @classmethod
    def delete_resource_metrics_outside_resource_id_list(cls, resource_id_list):
        session = get_session()
        with session.begin():
            return session.query(ResourceMetrics).filter(ResourceMetrics.resource_id.not_in(resource_id_list)).delete()

    @classmethod
    def delete_all_resource_metrics(cls):
        session = get_session()
        with session.begin():
            return session.query(ResourceMetrics).delete()

