# 定义系统公共功能的api的model对象
from typing import Optional
from pydantic import BaseModel, Field

# 资产购买合同信息
class OperateLogApiModel(BaseModel):
    id: Optional[str] = Field(None, description="日志的id")
    log_date: Optional[int] = Field(None, description="日志操作时间")
    user_id: Optional[str] = Field(None, description="用户id")
    user_name: Optional[str] = Field(None, description="用户名称")
    ip: Optional[str] = Field(None, description="操作ip")
    operate_type: Optional[str] = Field(None, description="操作类型")
    resource_type: Optional[str] = Field(None, description="操作资源类型")
    resource_type_name: Optional[str] = Field(None, description="操作资源类型中文名称")
    resource_id: Optional[str] = Field(None, description="操作资源id")
    resource_name: Optional[str] = Field(None, description="操作资源名称")
    operate_flag: Optional[bool] = Field(None, description="操作成功失败标识")
    description: Optional[str] = Field(None, description="合同的描述信息")