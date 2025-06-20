from typing import Optional, List
from pydantic import BaseModel, Field

class FlavorObject(BaseModel):
    begin: Optional[str] = Field(None, description="开始时间")
    end: Optional[str] = Field(None, description="结束时间")
    tenant_id: Optional[str] = Field(None, description="租户ID")
    flavor_name: Optional[str] = Field(None, description="Flavor名称")
    res_type: Optional[str] = Field(None, description="服务类型")
    rate: Optional[str] = Field(None, description="费率")

class CloudKittyRatingSummaryDetail(BaseModel):
    service: Optional[str] = Field(None, description="服务类型")
    tenant_id: Optional[str] = Field(None, description="项目ID")
    tenant_name: Optional[str] = Field(None, description="项目名称")
    end: Optional[str] = Field(None, description="结束时间")
    end_time: Optional[str] = Field(None, description="结束时间")
    start_time: Optional[str] = Field(None, description="开始时间")
    total: Optional[str] = Field(None, description="总计")
    flavor: Optional[List[FlavorObject]] = Field(None, description="描述信息")
    cpuTotal: Optional[float] = Field(None, description="CPU总计")
    gpuTotal: Optional[float] = Field(None, description="GPU总计")

class RatingModuleConfigHashMapMapping(BaseModel):
    mapping_id: Optional[str] = Field(None, description="映射ID")
    cost: Optional[str] = Field(None, description="费用")
    type: Optional[str] = Field(None, description="类型")
    group_id: Optional[str] = Field(None, description="组ID")
    tenant_id: Optional[str] = Field(None, description="项目ID")
    value: Optional[str] = Field(None, description="值")
    field_id: Optional[str] = Field(None, description="字段ID")
    service_id: Optional[str] = Field(None, description="服务ID")

class RatingModuleConfigHashMapThreshold(BaseModel):
    threshold_id: Optional[str] = Field(None, description="阈值ID")
    cost: Optional[str] = Field(None, description="费用")
    type: Optional[str] = Field(None, description="类型")
    group_id: Optional[str] = Field(None, description="组ID")
    tenant_id: Optional[str] = Field(None, description="项目ID")
    field_id: Optional[str] = Field(None, description="字段ID")
    service_id: Optional[str] = Field(None, description="服务ID")
    level: Optional[str] = Field(None, description="级别")

class RatingModules(BaseModel):
    module_id: Optional[str] = Field(None, description="模型ID")
    description: Optional[str] = Field(None, description="描述")
    enabled: Optional[bool] = Field(None, description="是否启用")
    hot_config: Optional[bool] = Field(None, description="是否可配置", alias="hot-config")
    priority: Optional[int] = Field(None, description="优先级")