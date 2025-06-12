# 资源的service层
import json
import uuid

from math import ceil

from dingo_command.db.models.asset_resoure_relation.models import ResourceMetrics
from dingo_command.db.models.asset_resoure_relation.sql import AssetResourceRelationSQL
from dingo_command.utils import datetime

class ResourcesService:

    @classmethod
    def project_resource_statistic_list(self, query_params, page, page_size, sort_keys, sort_dirs):
        # 资源按vpc_id分组： 根据裸金属和裸金属对应的虚拟机所属的租户进行分组
        # VPC名称、资源类型、资源数量、资产数量
        # 业务逻辑
        try:
            # 按照条件从数据库中查询数据
            count, data = AssetResourceRelationSQL.project_resource_statistic_list(query_params, page, page_size, sort_keys, sort_dirs)
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

                # prometheus metrics数据：资源GPU卡数、资源GPU功率、资源CPU使用率、资源内存使用率
                resource_metrics_info = self.get_resource_metrics_by_resource_id(self, r.resource_id)
                temp["resource_metrics_info"] = resource_metrics_info
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
            project_count = AssetResourceRelationSQL.get_project_resource_project_not_empty_count()
            result['project_count'] = project_count

            # 资源的资产ID为空以及资源的资产ID不为空且未创建实例数目，即为未分配节点数目
            unassigned_asset_count = AssetResourceRelationSQL.get_unassigned_asset_count()
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
                    resource_status_info_temp['resource_project_id'] = resource_status_info.resource_project_id
                    resource_status_info_temp['resource_project_name'] = resource_status_info.resource_project_name
                    resource_status_info_temp['resource_id'] = resource_status_info.resource_id
                    if resource_status_info.resource_name is None:
                        resource_status_info_temp['resource_name'] = resource_status_info.node_name
                    else:
                        resource_status_info_temp['resource_name'] = resource_status_info.resource_name
                    if resource_status_info.resource_status == "active":
                        resource_status_info_temp['resource_status'] = resource_status_info.resource_status
                    else:
                        resource_status_info_temp['resource_status'] = "inactive"
                    # 追加数据
                    resource_status_info_ret.append(resource_status_info_temp)

            result['resource_status_info'] = resource_status_info_ret
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None

    # 保存资源监控指标项数据
    def update_resource_metrics(self, resource_id, resource_metrics_dict):
        # 资源不为空，metrics数据为空
        if resource_id is not None and not resource_metrics_dict:
            print(f"当前资源[{resource_id}]在prometheus中的metric数据为空，删除数据中的该资源数据")
            AssetResourceRelationSQL.delete_resource_metrics_by_resource_id(resource_id)
            return None
        elif not resource_id or not resource_metrics_dict: # 空
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
        temp = {"resource_gpu_count": "-",
                "resource_gpu_power": "-",
                "resource_cpu_usage": "-",
                "resource_memory_usage": "-"}
        # 查询数据
        db_resource_metrics = AssetResourceRelationSQL.get_resource_metrics_by_resource_id(resource_id)
        #print(db_resource_metrics)
        if not db_resource_metrics:
            return temp

        for resource_metric in db_resource_metrics:
            # GPU卡数
            if resource_metric.name == 'gpu_count' and resource_metric.data is not None:
                temp["resource_gpu_count"] = resource_metric.data
            # 资源GPU平均功率
            if resource_metric.name == 'gpu_power' and resource_metric.data is not None:
                temp["resource_gpu_power"] = "{:.2f}".format(float(str(resource_metric.data)))
            # CPU使用率
            if resource_metric.name == 'cpu_usage' and resource_metric.data is not None:
                temp["resource_cpu_usage"] = "{:.2f}".format(float(str(resource_metric.data)))
            # 内存使用率
            if resource_metric.name == 'memory_usage' and resource_metric.data is not None:
                temp["resource_memory_usage"] = "{:.2f}".format(float(str(resource_metric.data)))

        # 返回
        return temp