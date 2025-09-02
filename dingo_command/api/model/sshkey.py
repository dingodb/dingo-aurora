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
    project_id: Optional[str] = Field(None, description="租户id")
    project_name: Optional[str] = Field(None, description="租户名称")
    user_id: Optional[str] = Field(None, description="用户id")
    user_name: Optional[str] = Field(None, description="用户名称")
    root_account_id: Optional[str] = Field(None, description="主账号ID")
    root_account_name: Optional[str] = Field(None, description="主账号名称")
    owner: Optional[str] = Field(None, description="sshkey的owner")
    k8s_id: Optional[str] = Field(None, description="sshkey的k8s_id")
    is_admin: Optional[bool] = Field(None, description="是否是主账户")
    key_content: Optional[str] = Field(None, description="sshkey的内容")
    description: Optional[str] = Field(None, description="sshkey的描述")