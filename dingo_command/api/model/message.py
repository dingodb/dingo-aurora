from typing import Optional, List, Any, Dict

from pydantic import BaseModel, Field

# 上报数据查询对象信息
class MessageQueryApiModel(BaseModel):
    sql: str = Field(None, description="查询语句")
