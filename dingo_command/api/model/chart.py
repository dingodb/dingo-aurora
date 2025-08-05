from typing import Dict, Optional, List, Union, Any
from pydantic import BaseModel, Field


# 定义递归类型支持任意嵌套结构
ValueType = Union[
    str, int, float, bool, None,
    List[Any],
    Dict[str, Any]
]


class CreateRepoObject(BaseModel):
    url: Optional[str] = Field(None, description="repo的url")
    id: Optional[str] = Field(None, description="repo的id")
    name: Optional[str] = Field(None, description="repo的name")
    type: Optional[str] = Field(None, description="repo的类型")
    cluster_id: Optional[str] = Field(None, description="k8s集群的id")
    description: Optional[str] = Field(None, description="repo仓库的描述")
    is_global: Optional[bool] = Field(None, description="repo仓库是否是全局配置")
    username: Optional[str] = Field(None, description="repo的凭证用户名")
    password: Optional[str] = Field(None, description="repo的凭证密码")
    
    
class CreateChartObject(BaseModel):
    urls: Optional[str] = Field(None, description="chart的url")
    name: Optional[str] = Field(None, description="chart的name")
    type: Optional[str] = Field(None, description="chart的类型")
    cluster_id: Optional[str] = Field(None, description="k8s集群的id")
    description: Optional[str] = Field(None, description="chart仓库的描述")
    repo_id: Optional[int] = Field(None, description="chart仓库的id")
    repo_name: Optional[str] = Field(None, description="chart仓库的name")
    tag_id: Optional[int] = Field(None, description="chart仓库的id")
    tag_name: Optional[str] = Field(None, description="chart仓库的name")
    create_time: Optional[str] = Field(None, description="chart的凭证用户名")
    version: Optional[str] = Field(None, description="chart的凭证密码")
    deprecated: Optional[bool] = Field(None, description="repo仓库是否是全局配置")


class CreateAppObject(BaseModel):
    name: Optional[str] = Field(None, description="创建应用的名称")
    chart_name: Optional[str] = Field(None, description="chartname的name")
    repo: Optional[str] = Field(None, description="repo的名字")
    cluster_id: Optional[str] = Field(None, description="k8s集群的id")
    chart_version: Optional[str] = Field(None, description="chart的version")
    namespace: Optional[str] = Field(None, description="namespace的名称")
    values: Optional[Dict[str, ValueType]] = Field(None, description="values.yaml里面的值")


class ChartObject(BaseModel):
    name: Optional[str] = Field(None, description="chart的名称")
    icon: Optional[str] = Field(None, description="chart的图标")
    repo: Optional[str] = Field(None, description="repo的名字")
    description: Optional[str] = Field(None, description="chart的describe信息")


class ResponseChartObject(BaseModel):
    items: Optional[Dict[str, ChartObject]] = Field(None, description="chart的数据")
    total: Optional[int] = Field(None, description="chart的total数")


# CreateAppObject.model_rebuild()