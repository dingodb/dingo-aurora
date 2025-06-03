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
    total: Optional[str] = Field(None, description="总计")
    flavor: Optional[List[FlavorObject]] = Field(None, description="描述信息")