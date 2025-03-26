
from typing import Dict, Optional, List

from pydantic import BaseModel, Field
from api.model.base import DingoopsObject


class NetworkConfigObject(BaseModel):
    network_id: Optional[str] = Field(None, description="网络id")
    cni: Optional[str] = Field(None, description="集群标签")
    pod_cidr: Optional[str] = Field(None, description="集群状态原因")
    network_id: Optional[str] = Field(None, description="网络id")
    admin_subnet_id: Optional[str] = Field(None, description="管理网id")
    bus_subnet_id: Optional[str] = Field(None, description="业务子网id")
    admin_network_id: Optional[str] = Field(None, description="管理网络id")
    bus_network_id: Optional[str] = Field(None, description="业务网络id")
    vip: Optional[str] = Field(None, description="管理网访问地址")
    floating_ip: Optional[bool] = Field(None, description="是否启用浮动ip")
    service_cidr: Optional[str] = Field(None, description="服务网段")
    router_id: Optional[str] = Field(None, description="虚拟路由id")
    
class NodeConfigObject(BaseModel):
    count: Optional[int] = Field(None, description="项目id")
    image: Optional[str] = Field(None, description="用户id")
    flavor_id: Optional[str] = Field(None, description="节点规格")
    role: Optional[str] = Field(None, description="节点角色")
    type: Optional[str] = Field(None, description="节点类型vm/metal")
    security_group: Optional[str] = Field(None, description="安全组名称")
    
class NodeGroup(BaseModel):
    az: Optional[str] = Field(None, description="可用域")
    flavor: Optional[str] = Field(None, description="规格")
    floating_ip: Optional[str] = Field(None, description="浮动ip")
    etcd: Optional[str] = Field(None, description="是否是etcd节点")
    
class ClusterObject(DingoopsObject):
    project_id: Optional[str] = Field(None, description="项目id")
    user_id: Optional[str] = Field(None, description="用户id")
    labels: Optional[str] = Field(None, description="集群标签")
    region_name: Optional[str] = Field(None, description="region名称")
    network_config: Optional[NetworkConfigObject] = Field(None, description="网络配置")
    node_config: Optional[List[NodeConfigObject]] = Field(None, description="节点配置")
    runtime: Optional[str] = Field(None, description="运行时类型")
    type: Optional[str] = Field(None, description="集群类型")
    
    version: Optional[str] = Field(None, description="k8s版本")
    kube_config: Optional[str] = Field(None, description="cni插件")

class NodeObject(DingoopsObject):
    project_id: Optional[str] = Field(None, description="项目id")
    user_id: Optional[str] = Field(None, description="用户id")
    keypair: Optional[str] = Field(None, description="密钥对")
    flavor_id: Optional[str] = Field(None, description="规格id")
    cluster_id: Optional[str] = Field(None, description="集群标签")
    image_id: Optional[str] = Field(None, description="集群状态")
    admin_address: Optional[str] = Field(None, description="集群状态")
    business_address: Optional[str] = Field(None, description="集群状态")
    openstack_id: Optional[str] = Field(None, description="集群状态原因")
    region_name: Optional[str] = Field(None, description="region名称")
    role: Optional[str] = Field(None, description="网络id")
    operation_system: Optional[str] = Field(None, description="子网id")
    node_type: Optional[str] = Field(None, description="管理网访问地址")
    status: Optional[str] = Field(None, description="业务网nodeport暴露地址")
    status_msg: Optional[str] = Field(None, description="节点状态信息")
    kube_config: Optional[str] = Field(None, description="cni插件")

class NodeStatusObject(BaseModel):
    id: Optional[str] = Field(None, description="密钥对")
    cpu_usage: Optional[str] = Field(None, description="cpu使用")
    mem_usage: Optional[str] = Field(None, description="内存使用")
    disk_usage: Optional[str] = Field(None, description="存储使用")
    status: Optional[str] = Field(None, description="集群状态")
    status_msg: Optional[str] = Field(None, description="集群状态信息")
    update_time: Optional[str] = Field(None, description="更新时间")                
   
class ClusterTFVarsObject(BaseModel):
    id: Optional[str] = Field(None, description="集群id")
    cluster_name: Optional[str] = Field(None, description="集群id")
    image: Optional[str] = Field(None, description="用户id")
    k8s_masters: Optional[Dict[str, NodeGroup]] = Field(None, description="集群标签")
    k8s_nodes: Optional[Dict[str, NodeGroup]] = Field(None, description="集群状态")
    admin_subnet_id: Optional[str] = Field(None, description="管理子网id")
    bus_network_id: Optional[str] = Field(None, description="业务网络id")
    admin_network_id: Optional[str] = Field(None, description="管理网id")
    bus_subnet_id: Optional[str] = Field(None, description="业务子网id")
    floatingip_pool: Optional[bool] = Field(None, description="节点配置")
    subnet_cidr: Optional[str] = Field(None, description="运行时类型")
    use_existing_network: Optional[str] = Field(None, description="是否使用已有网络")
    external_net: Optional[str] = Field(None, description="外部网络id")