# 监控类的对象
from typing import Optional
from pydantic import BaseModel, Field

# 资源统计概览
class ResourceStatisticOverviewApiModel(BaseModel):
    resource_total_count: Optional[int] = Field(None, description="资源总数")
    vpc_count: Optional[int] = Field(None, description="分配的VPC总数")
    unassigned_asset_count: Optional[int] = Field(None, description="未分配的资产数量")
    failure_asset_count: Optional[int] = Field(None, description="故障的资产数量")
    asset_utilization_rate: Optional[float] = Field(None, description="资产使用率")
    # remaining_cpu_utilization_rate: Optional[float] = Field(None, description="CPU资源剩余占比")
    # share_dedicated_node_utilization_rate: Optional[float] = Field(None, description="共享及独占节点利用率")

# VPC资源统计列表
class ResourceStatisticModel(BaseModel):
    resource_vpc_id: Optional[str] = Field(None, description="VPC ID")
    resource_vpc_name: Optional[str] = Field(None, description="VPC名称")
    # resource_id: Optional[str] = Field(None, description="资源ID")
    # resource_type: Optional[str] = Field(None, description="资源类型")
    resource_count: Optional[int] = Field(None, description="资源数量")
    asset_count: Optional[int] = Field(None, description="资产数量")

# VPC资源详情列表
class ResourceDetailModel(BaseModel):
    resource_id: Optional[str] = Field(None, description="资源ID")
    resource_name: Optional[str] = Field(None, description="资源名称")
    resource_status: Optional[str] = Field(None, description="资源状态")
    asset_name: Optional[str] = Field(None, description="资产名称")
    asset_status: Optional[str] = Field(None, description="资产状态")
    resource_user_id: Optional[str] = Field(None, description="资源所属用户ID")
    resource_user_name: Optional[str] = Field(None, description="资源所属用户名称")
    resource_project_id: Optional[str] = Field(None, description="资源所属project的ID")
    resource_project_name: Optional[str] = Field(None, description="资源所属project的名称")
    resource_gpu_count: Optional[int] = Field(None, description="资源GPU卡数目")
    resource_gpu_utilization_rate: Optional[int] = Field(None, description="资源GPU功率")
    resource_cpu_utilization_rate: Optional[str] = Field(None, description="资源CPU使用率")
    resource_memory_utilization_rate: Optional[str] = Field(None, description="资源内存使用率")

# 资源与资产管理列表
class ResourceAssetManagementModel(BaseModel):
    resource_id: Optional[str] = Field(None, description="资源ID")
    resource_name: Optional[str] = Field(None, description="资源名称")
    resource_status: Optional[str] = Field(None, description="资源状态")
    asset_id: Optional[str] = Field(None, description="资产ID")
    asset_name: Optional[str] = Field(None, description="资产名称")
    asset_status: Optional[str] = Field(None, description="资产状态")
    resource_user_id: Optional[str] = Field(None, description="资源所属用户ID")
    resource_user_name: Optional[str] = Field(None, description="资源所属用户名称")
    resource_project_id: Optional[str] = Field(None, description="资源所属project的ID")
    resource_project_name: Optional[str] = Field(None, description="资源所属project的名称")
    # resource_vpc_id: Optional[str] = Field(None, description="资源所属VPC ID")
    # resource_vpc_name: Optional[str] = Field(None, description="资源所属VPC名称")
    resource_order_id: Optional[str] = Field(None, description="资源所属订单ID")
    resource_order_name: Optional[str] = Field(None, description="资源所属订单名称")
    resource_lease_start_time: Optional[int] = Field(None, description="资源租赁开始时间")
    resource_lease_end_time: Optional[int] = Field(None, description="资源租赁结束时间")
