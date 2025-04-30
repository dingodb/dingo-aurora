# 资源的service层
import uuid

from math import ceil

from dingoops.db.models.asset_resoure_relation.models import ResourceMetrics
from dingoops.db.models.asset_resoure_relation.sql import AssetResourceRelationSQL
from dingoops.utils import datetime

class ResourcesService:

    @classmethod
    def vpc_resource_statistic_list(self, query_params, page, page_size, sort_keys, sort_dirs):
        # 资源按vpc_id分组： 根据裸金属和裸金属对应的虚拟机所属的租户进行分组
        # VPC名称、资源类型、资源数量、资产数量
        # 业务逻辑
        try:
            # 按照条件从数据库中查询数据
            count, data = AssetResourceRelationSQL.vpc_resource_statistic_list(query_params, page, page_size, sort_keys, sort_dirs)
            # 数据处理
            # 遍历
            ret = []
            for r in data:
                # 填充数据
                temp = {}
                if r.resource_project_id:
                    temp["resource_project_id"] = r.resource_project_id
                    temp["resource_project_name"] = r.resource_project_name
                    temp["resource_count"] = r.resource_count
                    temp["asset_count"] = r.asset_count
                    # 追加数据
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

    @classmethod
    def resource_detail_list(self, resource_project_id, query_params, page, page_size, sort_keys, sort_dirs):
        # 业务逻辑
        try:
            # 按照条件从数据库中查询数据
            count, data = AssetResourceRelationSQL.resource_detail_list(resource_project_id, query_params, page, page_size, sort_keys, sort_dirs)
            # 数据处理
            # 遍历
            ret = []
            for r in data:
                temp = {}
                temp["resource_id"] = r.resource_id
                temp["resource_name"] = r.resource_name
                temp["resource_status"] = r.resource_status
                temp["asset_id"] = None if r.asset_id is None else r.asset_id
                temp["asset_name"] = None if r.asset_name is None else r.asset_name
                temp["asset_status"] = None if r.asset_status is None else r.asset_status
                temp["resource_user_id"] = r.resource_user_id
                temp["resource_user_name"] = r.resource_user_name
                temp["resource_project_id"] = r.resource_project_id
                temp["resource_project_name"] = r.resource_project_name
                # TODO：待处理数据字段: 资源GPU卡数、资源GPU功率、资源CPU使用率、资源内存使用率
                temp["resource_gpu_cards_count"] = None
                temp["resource_gpu_utilization_rate"] = None
                temp["resource_cpu_utilization_rate"] = None
                temp["resource_memory_utilization_rate"] = None
                # 追加数据
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

    @classmethod
    def fetch_resource_statistic_overview_data(self):
        try:
            result = {}
            # 资源数目
            resource_total_count = AssetResourceRelationSQL.get_all_asset_resource_relation_count()
            result['resource_total_count'] = resource_total_count
            # 项目数目
            project_count = AssetResourceRelationSQL.get_resource_project_not_empty_count()
            result['project_count'] = project_count

            # 资源的资产ID为空数目，即为未分配节点数目
            unassigned_asset_count = AssetResourceRelationSQL.get_asset_id_empty_resource_count()
            result['unassigned_asset_count'] = unassigned_asset_count

            # 故障节点数目：即为资源关联的资产中，资产状态为故障的数目
            failure_asset_count = AssetResourceRelationSQL.get_resource_relation_asset_failure_count()
            result['failure_asset_count'] = failure_asset_count

            # 资源状态
            resource_status_info_ret = []
            resource_status_info_data = AssetResourceRelationSQL.get_all_resource_status_info()
            if resource_status_info_data:
                for resource_status_info in resource_status_info_data:
                    resource_status_info_temp = {}
                    resource_status_info_temp['resource_id'] = resource_status_info.resource_id
                    resource_status_info_temp['resource_name'] = resource_status_info.resource_name
                    resource_status_info_temp['resource_status'] = resource_status_info.resource_status
                    # 追加数据
                    resource_status_info_ret.append(resource_status_info_temp)

            result['resource_status_info'] = resource_status_info_ret

            # 资源使用情况：
            # 资产分配的情况

            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None

    # 保存资源监控指标项数据
    def update_resource_metrics(self, resource_id, resource_metrics_dict):
        # 空
        if not resource_id or not resource_metrics_dict:
            return None
        # 遍历
        for name, metrics_value in resource_metrics_dict.items():
            # 查询指标名称对应的数据
            db_resource_metrics = AssetResourceRelationSQL.get_resource_metrics_by_resource_id_and_name(resource_id, name)
            # 判空
            if not db_resource_metrics:
                temp_resource_metrics = ResourceMetrics(
                    id = uuid.uuid4().hex,
                    resource_id = resource_id,
                    name = name,
                    data = metrics_value,
                    region = None,
                    last_modified = datetime.get_now_time()
                )
                # 插入数据
                AssetResourceRelationSQL.create_resource_metrics(temp_resource_metrics)
            else:
                # 更新数据
                db_resource_metrics.data = metrics_value
                db_resource_metrics.last_modified = datetime.get_now_time()
                AssetResourceRelationSQL.update_resource_metrics(db_resource_metrics)

    # 查询某个资源的监控指标项数据
    def get_resource_metrics_by_resource_id(self, resource_id):
        # 查询数据
        db_resource_metrics = AssetResourceRelationSQL.get_resource_metrics_by_resource_id(resource_id)
        # 返回
        return db_resource_metrics