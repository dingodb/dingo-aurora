# 定义ai容器相关的model对象
from typing import Optional
from pydantic import BaseModel, Field


class InstanceConfigObj(BaseModel):
    instance_replica_num: Optional[int] = Field(None, description="实例副本个数")
    instance_cpu: Optional[int] = Field(None, description="实例CPU")
    instance_memory: Optional[int] = Field(None, description="实例内存")

class InstanceEnvsObj(BaseModel):
    name: Optional[str] = Field(None, description="环境变量名称")
    value: Optional[str] = Field(None, description="环境变量value")

class VolumeObj(BaseModel):
    pass

# 容器实例信息
class AiInstanceApiModel(BaseModel):
    project_id: Optional[str] = Field(None, description="租户id")
    user_id: Optional[str] = Field(None, description="用户id")
    k8s_id: Optional[str] = Field(None, description="K8S id")
    name: Optional[str] = Field(None, description="实例名称")
    stop_time: Optional[str] = Field(None, description="实例自动关机时间")
    auto_delete_time: Optional[str] = Field(None, description="实例自动删除时间")
    instance_config: Optional[InstanceConfigObj] = Field(None, description="实例的配置（个数、cpu、内存、存储等）")
    instance_envs: Optional[list[InstanceEnvsObj]] = Field(None, description="实例的环境变量")
    image_type: Optional[str] = Field(None, description="实例的镜像库")
    image: Optional[str] = Field(None, description="实例的镜像")
    volumes: Optional[VolumeObj] = Field(None, description="实例的卷配置（卷类型、大小、挂载点）")
