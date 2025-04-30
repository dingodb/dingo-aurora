from typing import Dict, Optional, List
from pydantic import BaseModel, Field
from dingoops.api.model.base import DingoopsObject
from dingoops.api.model.cluster import NetworkConfigObject

class OpenStackConfigObject(BaseModel):
    openstack_auth_url: Optional[str] = Field(None, description="openstack的url")
    project_id: Optional[str] = Field(None, description="openstack的id")
    project_name: Optional[str] = Field(None, description="openstack的租户")
    openstack_username: Optional[str] = Field(None, description="openstack的用户")
    openstack_password: Optional[str] = Field(None, description="openstack的用户密码")
    user_domain_name: Optional[str] = Field(None, description="openstack用户的域")
    project_domain_name: Optional[str] = Field(None, description="openstack租户的域")
    region: Optional[str] = Field(None, description="region信息")

class InstanceConfigObject(DingoopsObject):
    cluster_id: Optional[str] = Field(None, description="集群id")
    cluster_name: Optional[str] = Field(None, description="集群id")
    project_id: Optional[str] = Field(None, description="租户id")
    server_id: Optional[str] = Field(None, description="server的id")
    openstack_id: Optional[str] = Field(None, description="openstack的id")
    flavor_id: Optional[str] = Field(None, description="flavor的id")
    image_id: Optional[str] = Field(None, description="image的id")
    network_id: Optional[NetworkConfigObject] = Field(None, description="network信息")
    node_type: Optional[str] = Field(None, description="server的type")
    ip_address: Optional[str] = Field(None, description="server的ip")
    operation_system: Optional[str] = Field(None, description="server的os")
    floating_ip: Optional[str] = Field(None, description="server的fip")
    region: Optional[str] = Field(None, description="server的region")
    status: Optional[str] = Field(None, description="server的status")
    user: Optional[str] = Field(None, description="openstack的用户")
    password: Optional[str] = Field(None, description="openstack的用户的密码")
    cpu: Optional[str] = Field(None, description="server的cpu")
    gpu: Optional[str] = Field(None, description="server的gpu")
    mem: Optional[str] = Field(None, description="server的mem")
    disk: Optional[str] = Field(None, description="server的disk")

class InstanceRemoveObject(BaseModel):
    openstack_info: Optional[OpenStackConfigObject] = Field(None, description="openstack中的信息")
    instance_list: Optional[List[InstanceConfigObject]] = Field(None, description="instance列表")

class InstanceCreateObject(BaseModel):
    cluster_id: Optional[str] = Field(None, description="集群id")
    cluster_name: Optional[str] = Field(None, description="集群id")
    name: Optional[str] = Field(None, description="instance的名字")
    numbers: Optional[int] = Field(0, description="instance的数量")
    node_type: Optional[str] = Field(None, description="server的type")
    flavor_id: Optional[str] = Field(None, description="flavor的id")
    image_id: Optional[str] = Field(None, description="image的id")
    network_id: Optional[str] = Field(None, description="network信息")
    sshkey_name: Optional[str] = Field(None, description="sshkey_name信息")
    security_group: Optional[str] = Field(None, description="security_group信息")
    openstack_info: Optional[OpenStackConfigObject] = Field(None, description="openstack中的信息")