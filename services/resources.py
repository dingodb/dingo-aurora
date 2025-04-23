# 资源的service层
from math import ceil

from db.models.asset_resoure_relation.sql import AssetResourceRelationSQL

class ResourcesService:
    @classmethod
    def resource_asset_management_list(self, query_params, page, page_size, sort_keys, sort_dirs):
        # 业务逻辑
        try:
            # 按照条件从数据库中查询数据
            count, data = AssetResourceRelationSQL.list_asset_resource_relation_info(query_params, page, page_size, sort_keys, sort_dirs)
            # 数据处理
            ret = []
            # 遍历
            for r in data:
                # 填充数据
                temp = {}
                temp["resource_id"] = r.resource_id
                temp["resource_name"] = r.resource_name
                temp["resource_status"] = r.resource_status
                temp["asset_id"] = r.asset_id
                temp["asset_name"] = None if r.asset_name is None else r.asset_name
                temp["asset_status"] = None if r.asset_status is None else r.asset_status
                temp["resource_user_id"] = r.resource_user_id
                temp["resource_user_name"] = r.resource_user_name
                temp["resource_project_id"] = r.resource_project_id
                temp["resource_project_name"] = r.resource_project_name
                # temp["resource_order_number"] = None if r.resource_order_number is None else r.resource_order_number
                temp["resource_lease_start_time"] = None if r.resource_lease_start_time is None else r.resource_lease_start_time
                temp["resource_lease_end_time"] = None if r.resource_lease_end_time is None else r.resource_lease_end_time
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
    def vpc_resource_statistic_list(self):
        # 资源按vpc_id分组： 根据裸金属和裸金属对应的虚拟机所属的租户进行分组
        # VPC名称、资源类型、资源数量、资产数量

        return

    @classmethod
    def resource_detail_list(self, vpcId):
        # 资源按vpc_id分组： 根据裸金属和裸金属对应的虚拟机所属的租户进行分组
        # VPC名称、资源类型、资源数量、资产数量

        return

    @classmethod
    def fetch_resource_statistic_overview_data(self):
        # 调用ops_asset_resource_relation_info表
        # 资源数量: 查询裸金属列表数目+裸金属对应的虚拟机数目

        # 资源状态: 裸金属或裸金属对应的虚拟机的状态

        # 资源使用情况：

        # 资产分配的情况

        # vpc统计情况：统计裸金属列表和裸金属对应的虚拟机所属的租户个数

        return

