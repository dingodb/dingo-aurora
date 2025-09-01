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
    owner: Optional[str] = Field(None, description="sshkey的owner")
    k8s_id: Optional[str] = Field(None, description="sshkey的k8s_id")
    user_id: Optional[str] = Field(None, description="sshkey的user_id")
    user_name: Optional[str] = Field(None, description="sshkey的user_name")
    account_id: Optional[str] = Field(None, description="sshkey的account_id")
    is_admin: Optional[str] = Field(None, description="是否是主账户")
    key_content: Optional[str] = Field(None, description="sshkey的内容")
    description: Optional[str] = Field(None, description="sshkey的描述")