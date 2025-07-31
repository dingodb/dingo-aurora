# 定义ai容器相关的model对象
from typing import Optional, List, Any, Dict

from pydantic import BaseModel, Field


# 容器实例信息
class AiInstanceApiModel(BaseModel):
    ai_instance_id: Optional[str] = Field(None, description="容器实例的id")
    ai_instance_name: Optional[str] = Field(None, description="容器实例的名称")
    description: Optional[str] = Field(None, description="描述信息")
