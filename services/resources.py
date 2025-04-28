# 资源的service层
from math import ceil
from zoneinfo import available_timezones

from db.models.asset_resoure_relation.sql import AssetResourceRelationSQL

class ResourcesService:

    @classmethod
    def vpc_resource_statistic_list(self, query_params, page, page_size, sort_keys, sort_dirs):
        # 资源按vpc_id分组： 根据裸金属和裸金属对应的虚拟机所属的租户进行分组
        # VPC名称、资源类型、资源数量、资产数量
        # 业务逻辑
        try:
            # 按照条件从数据库中查询数据
            count, vpc_statistic_data = AssetResourceRelationSQL.vpc_resource_statistic(query_params, page, page_size, sort_keys, sort_dirs)
            asset_statistic_data = AssetResourceRelationSQL.asset_statistic()
            # 数据处理
            # 遍历
            ret = []
            for r in vpc_statistic_data:
                # 填充数据
                temp = {}
                if r.resource_project_id:
                    temp["resource_project_id"] = r.resource_project_id
                    temp["resource_project_name"] = r.resource_project_name
                    temp["resource_count"] = r.resource_count
                    if not asset_statistic_data:
                        temp["asset_count"] = 0
                    for asset_statistic in asset_statistic_data:
                        if asset_statistic.resource_project_id == r.resource_project_id:
                            temp["asset_count"] = asset_statistic.asset_count
                            break
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

            # 资源状态
            resource_status_info_ret = []
            resource_status_info_data = AssetResourceRelationSQL.get_all_resource_status_info()
            available_resource_count = 0
            if resource_status_info_data:
                for resource_status_info in resource_status_info_data:
                    resource_status_info_temp = {}
                    resource_status_info_temp['resource_id'] = resource_status_info.resource_id
                    resource_status_info_temp['resource_name'] = resource_status_info.resource_name
                    resource_status_info_temp['resource_status'] = resource_status_info.resource_status
                    # 追加数据
                    resource_status_info_ret.append(resource_status_info_temp)
                    # if resource_status_info.resource_status == "available":
                    if resource_status_info.resource_status == "active":
                        available_resource_count += 1
            result['resource_status_info'] = resource_status_info_ret

            # 可用节点数目
            result['available_resource_count'] = available_resource_count

            # 资源使用情况：
            # 资产分配的情况

            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None

