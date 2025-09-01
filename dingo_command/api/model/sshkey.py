from typing import Dict, Optional, List, Union, Any
from pydantic import BaseModel, Field


# 定义递归类型支持任意嵌套结构
ValueType = Union[
    str, int, float, bool, None,
    List[Any],
    Dict[str, Any]
]


class CreateRepoObject(BaseModel):
    name: Optional[str] = Field(None, description="sshkey的name")
    owner: Optional[str] = Field(None, description="sshkey的owner")
    user_id: Optional[str] = Field(None, description="sshkey的user_id")
    account_id: Optional[str] = Field(None, description="sshkey的account_id")
    key: Optional[str] = Field(None, description="sshkey的内容")
    description: Optional[str] = Field(None, description="repo仓库的描述")