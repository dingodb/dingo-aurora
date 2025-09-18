from typing import Dict, Optional, List, Union, Any
from pydantic import BaseModel, Field


# 定义递归类型支持任意嵌套结构
ValueType = Union[
    str, int, float, bool, None,
    List[Any],
    Dict[str, Any]
]


class CreateKeyObject(BaseModel):
    name: Optional[str] = Field(None, description="sshkey的name")
    user_id: Optional[str] = Field(None, description="用户id")
    is_manager: Optional[bool] = Field(None, description="是否是主账号")
    user_name: Optional[str] = Field(None, description="用户名称")
    tenant_id: Optional[str] = Field(None, description="租户id")
    key_content: Optional[str] = Field(None, description="sshkey的内容")
    description: Optional[str] = Field(None, description="sshkey的描述")