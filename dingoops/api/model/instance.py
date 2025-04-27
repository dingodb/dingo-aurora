from typing import Dict, Optional, List

from pydantic import BaseModel, Field
from dingoops.api.model.base import DingoopsObject


class InstanceConfigObject(DingoopsObject):
    cluster_id: Optional[str] = Field(None, description="集群id")
    cluster_name: Optional[str] = Field(None, description="集群id")
    project_id: Optional[str] = Field(None, description="租户id")
    server_id: Optional[str] = Field(None, description="server的id")
    openstack_id: Optional[str] = Field(None, description="openstack的id")
    ip_address: Optional[str] = Field(None, description="server的ip")
    operation_system: Optional[str] = Field(None, description="server的os")
    floating_ip: Optional[str] = Field(None, description="server的fip")
    node_type: Optional[str] = Field(None, description="server的type")
    region: Optional[str] = Field(None, description="server的region")
    status: Optional[str] = Field(None, description="server的status")
    user: Optional[str] = Field(None, description="openstack的用户")
    password: Optional[str] = Field(None, description="openstack的用户的密码")
    cpu: Optional[str] = Field(None, description="server的cpu")
    gpu: Optional[str] = Field(None, description="server的gpu")
    mem: Optional[str] = Field(None, description="server的mem")
    disk: Optional[str] = Field(None, description="server的disk")

class InstanceRemoveObject(BaseModel):
    cluster_id: Optional[str] = Field(None, description="集群id")
    instance_list: Optional[List[InstanceConfigObject]] = Field(None, description="instance列表")