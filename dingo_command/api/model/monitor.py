# 监控类的对象
from typing import Optional
from pydantic import BaseModel, Field

# 监控url的配置对象
class MonitorUrlConfigApiModel(BaseModel):
    id: Optional[str] = Field(None, description="配置的id")
    name: Optional[str] = Field(None, description="配置的名称")
    url: Optional[str] = Field(None, description="配置的url")
    url_catalog: Optional[str] = Field(None, description="配置的类型")
    url_type: Optional[str] = Field(None, description="配置的url类型")
    user_id: Optional[str] = Field(None, description="用户id")
    user_account: Optional[str] = Field(None, description="用户名称")
    description: Optional[str] = Field(None, description="描述信息")