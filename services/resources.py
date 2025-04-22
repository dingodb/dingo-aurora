# 资源的service层
from math import ceil

from api.model.resources import ResourceAssetManagementModel
from db.models.asset_resoure_relation.sql import AssetReSourceRelationSQL


class ResourcesService:
    @classmethod
    def resource_asset_management_list(self, query_params, page, page_size, sort_keys, sort_dirs):
        # 业务逻辑
        try:
            # 按照条件从数据库中查询数据
            count, data = AssetReSourceRelationSQL.list_asset_resource_relation_info(query_params, page, page_size, sort_keys, sort_dirs)
            # 数据处理
            ret = []
            # 遍历
            for r in data:
                # 填充数据
                temp = self.convert_resource_asset_management_model_data_structure(r)
                ret.append(temp)

            # 返回数据
            return self.convert_result_data_structure(count, page, page_size, ret)
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

    def convert_result_data_structure(cls, count, page, page_size, ret):
        res = {}
        # 页数相关信息
        if page and page_size:
            res['currentPage'] = page
            res['pageSize'] = page_size
            res['totalPages'] = ceil(count / int(page_size))
        res['total'] = count
        res['data'] = ret
        return res

    def convert_resource_asset_management_model_data_structure(cls, r):
        temp = {}
        temp[ResourceAssetManagementModel.resource_id] = r.resource_id
        temp[ResourceAssetManagementModel.resource_name] = r.resource_name
        temp[ResourceAssetManagementModel.resource_status] = r.resource_status
        temp[ResourceAssetManagementModel.asset_id] = r.asset_id
        temp[ResourceAssetManagementModel.asset_name] = r.asset_name
        temp[ResourceAssetManagementModel.asset_status] = r.asset_status
        temp[ResourceAssetManagementModel.resource_user_id] = r.resource_user_id
        temp[ResourceAssetManagementModel.resource_user_name] = r.resource_user_name
        temp[ResourceAssetManagementModel.resource_project_id] = r.resource_project_id
        temp[ResourceAssetManagementModel.resource_project_name] = r.resource_project_name
        # temp[ResourceAssetManagementModel.resource_vpc_id] = r.resource_vpc_id
        # temp[ResourceAssetManagementModel.resource_vpc_name] = r.resource_vpc_name
        temp[ResourceAssetManagementModel.resource_order_id] = r.resource_order_id
        temp[ResourceAssetManagementModel.resource_order_name] = r.resource_order_name
        temp[ResourceAssetManagementModel.resource_lease_start_time] = r.resource_lease_start_time
        temp[ResourceAssetManagementModel.resource_lease_end_time] = r.resource_lease_end_time

        return temp