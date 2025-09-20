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
    id: Optional[str] = Field(None, description="app的id")
    name: Optional[str] = Field(None, description="创建应用的名称")
    chart_id: Optional[str] = Field(None, description="chart的id")
    # repo_id: Optional[str] = Field(None, description="repo的id")
    cluster_id: Optional[str] = Field(None, description="k8s集群的id")
    chart_version: Optional[str] = Field(None, description="chart的version")
    namespace: Optional[str] = Field(None, description="namespace的名称")
    values: Optional[Dict[str, ValueType]] = Field(None, description="values.yaml里面的值")
    description: Optional[str] = Field(None, description="description信息")


class ChartVersionObject(BaseModel):
    version: Optional[str] = Field(None, description="chart的版本号")
    created: Optional[str] = Field(None, description="chart的创建时间")


class ChartMetadataObject(BaseModel):
    name: Optional[str] = Field(None, description="chart的名称")
    description: Optional[str] = Field(None, description="chart的describe信息")
    icon: Optional[str] = Field(None, description="chart的图标")
    repo: Optional[str] = Field(None, description="repo的名字")
    version: Optional[str] = Field(None, description="chart的版本号")


class ChartObject(BaseModel):
    metadata: Optional[ChartMetadataObject] = Field(None, description="chart的名称")
    readme: Optional[str] = Field(None, description="chart的图标")
    values: Optional[str] = Field(None, description="values.yaml里面的值")


class ResponseChartObject(BaseModel):
    versions: Optional[List[ChartVersionObject]] = Field(None, description="chart的数据")
    chart: Optional[ChartObject] = Field(None, description="chart的详情")


class ResourcesObject(BaseModel):
    name: Optional[str] = Field(None, description="resource的名称")
    kind: Optional[str] = Field(None, description="resource的类型")
    status: Optional[str] = Field(None, description="status状态")
    namespace: Optional[str] = Field(None, description="resource的名称空间")
    yaml: Optional[str] = Field(None, description="resource的yaml")


class AppChartObject(BaseModel):
    name: Optional[str] = Field(None, description="chart的名称")
    description: Optional[str] = Field(None, description="chart的describe信息")
    icon: Optional[str] = Field(None, description="chart的图标")
    repo_name: Optional[str] = Field(None, description="repo的名字")
    namespace: Optional[str] = Field(None, description="命名空间")
    app_name: Optional[str] = Field(None, description="app的名字")
    update_time: Optional[str] = Field(None, description="更新时间")
    chart_version: Optional[str] = Field(None, description="chart的版本")
    app_version: Optional[str] = Field(None, description="app的版本")


class ResponseAppObject(BaseModel):
    resources: Optional[List[ResourcesObject]] = Field(None, description="resources数据")
    values: Optional[str] = Field(None, description="values.yaml里面的值")
    chart_info: Optional[AppChartObject] = Field(None, description="chart的详情")


class ChartInfoObject(BaseModel):
    id: Optional[int] = Field(None, description="chart的id")
    name: Optional[str] = Field(None, description="chart的名称")
    prefix_name: Optional[str] = Field(None, description="prefix_name")
    cluster_id: Optional[str] = Field(None, description="集群的名称")
    repo_id: Optional[int] = Field(None, description="repo的id")
    icon: Optional[str] = Field(None, description="icon")
    description: Optional[str] = Field(None, description="chart的描述")
    repo_name: Optional[str] = Field(None, description="repo的名称")
    type: Optional[str] = Field(None, description="chart的类型")
    tag_id: Optional[int] = Field(None, description="chart的tag_id")
    tag_name: Optional[str] = Field(None, description="chart的tag名称")
    status: Optional[str] = Field(None, description="chart的状态")
    create_time: Optional[str] = Field(None, description="chart的创建的时间")
    version: Optional[str] = Field(None, description="chart的版本")
    latest_version: Optional[str] = Field(None, description="chart的最新版本")
    deprecated: Optional[bool] = Field(None, description="chart是否是老版本")
    need_install: Optional[bool] = Field(None, description="chart是否是必须安装的")
    chart_content: Optional[str] = Field(None, description="chart的content信息")
    values_content: Optional[str] = Field(None, description="chart的名values信息")
    readme_content: Optional[str] = Field(None, description="chart的readme内容")
    extra: Optional[str] = Field(None, description="预留参数")


class ListChartInfoObject(BaseModel):
    currentPage: Optional[int] = Field(None, description="当前页码")
    pageSize: Optional[int] = Field(None, description="每页条数")
    total: Optional[int] = Field(None, description="总条数")
    totalPages: Optional[int] = Field(None, description="总页数")
    data: Optional[List[ChartInfoObject]] = Field(None, description="数据")

# CreateAppObject.model_rebuild()