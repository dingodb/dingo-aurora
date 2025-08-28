# 定义ai容器相关的model对象
from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field


class InstanceConfigObj(BaseModel):
    replica_count: Optional[int] = Field(None, description="实例副本个数")
    compute_model: Optional[str] = Field(None, description="计算资源型号")
    compute_cpu: Optional[str] = Field(None, description="计算资源CPU")
    compute_memory: Optional[str] = Field(None, description="计算资源内存")
    gpu_memory: Optional[str] = Field(None, description="GPU显存")
    gpu_model: Optional[str] = Field(None, description="GPU型号")
    gpu_count: Optional[int] = Field(None, description="GPU卡数")
    system_disk_size: Optional[str] = Field(None, description="系统盘大小(默认单位Gib)")

class StorageObj(BaseModel):
    configmap_name: Optional[str] = Field(None, description="configmap名称")
    configmap_path: Optional[str] = Field(None, description="configmap挂载路径")
    pvc_name: Optional[str] = Field(None, description="pvc名称")
    pvc_size: Optional[str] = Field(None, description="pvc大小（默认单位为Gib）")

# class DataSetObj(BaseModel):
#     name: Optional[str] = Field(None, description="数据集名称")
#     mount_path: Optional[str] = Field(None, description="挂载地址")

# 容器实例信息
class AiInstanceApiModel(BaseModel):
    project_id: Optional[str] = Field(None, description="租户id")
    project_name: Optional[str] = Field(None, description="租户名称")
    user_id: Optional[str] = Field(None, description="用户id")
    user_name: Optional[str] = Field(None, description="用户id")
    root_account_id: Optional[str] = Field(None, description="主账号ID")
    root_account_name: Optional[str] = Field(None, description="主账号ID")
    order_id: Optional[str] = Field(None, description="订单ID")
    k8s_id: Optional[str] = Field(None, description="K8S id")
    k8s_type: Optional[str] = Field(None, description="K8S类型")
    k8s_name: Optional[str] = Field(None, description="K8S名称")
    name: Optional[str] = Field(None, description="实例名称")
    stop_time: Optional[int] = Field(None, description="实例自动关机时间")
    auto_delete_time: Optional[int] = Field(None, description="实例自动释放时间")
    instance_config: Optional[InstanceConfigObj] = Field(None, description="实例的计算资源配置（个数、cpu、内存、存储等）")
    instance_envs: Optional[Dict[str, str]] = Field(None, description="实例的环境变量")
    image_type: Optional[str] = Field(None, description="实例的镜像库")
    image: Optional[str] = Field(None, description="实例的镜像")
    volumes: Optional[StorageObj] = Field(None, description="实例的卷配置（卷类型、大小、挂载点）")
    description: Optional[str] = Field(None, description="实例的卷配置（卷类型、大小、挂载点）")
    # data_set: Optional[DataSetObj] = Field(None, description="数据集信息")

class AiInstanceSavaImageApiModel(BaseModel):
    repo_name: Optional[str] = Field(None, description="仓库名称")
    image_label: Optional[str] = Field(None, description="镜像标签")
    # harbor_username: Optional[str] = Field(None, description="harbor名称")
    # harbor_password: Optional[str] = Field(None, description="harbor密码")

# k8s kubeconfig配置
class K8skubeconfigApiModel(BaseModel):
    k8s_id: Optional[str] = Field(None, description="k8s集群ID")
    k8s_name: Optional[str] = Field(None, description="k8s集群名称")
    k8s_type: Optional[str] = Field(None, description="k8s集群类型")
    kubeconfig_path: Optional[str] = Field(None, description="k8s kubeconfig配置文件存放路径")
    kubeconfig_context_name: Optional[str] = Field(None, description="k8s kubeconfig 使用用户")
    kubeconfig: Optional[Any] = Field(None, description="k8s kubeconfig配置文件内容")

# 定时关机请求模型
class AutoCloseRequest(BaseModel):
    auto_close_time: str = Field(..., description="定时关机时间，格式：YYYY-MM-DD HH:MM:SS")
    auto_close: bool = Field(..., description="是否启用定时关机")

# 定时删除请求模型
class AutoDeleteRequest(BaseModel):
    auto_delete_time: str = Field(..., description="定时删除时间，格式：YYYY-MM-DD HH:MM:SS")
    auto_delete: bool = Field(..., description="是否启用定时删除")

# 账户创建请求
class AccountCreateRequest(BaseModel):
    account: str = Field(..., description="账户账号")
    is_vip: bool = Field(False, description="是否为VIP账户")

class AccountUpdateRequest(BaseModel):
    account: Optional[str] = Field(None, description="账户账号")
    is_vip: Optional[bool] = Field(None, description="是否为VIP账户")

# 开机请求参数
class StartInstanceModel(BaseModel):
    image_type: Optional[str] = Field(None, description="镜像仓库")
    image: Optional[str] = Field(None, description="镜像名称")
