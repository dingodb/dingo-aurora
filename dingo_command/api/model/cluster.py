
from typing import Dict, Optional, List
from sqlalchemy import  DateTime

from pydantic import BaseModel, Field
from dingo_command.api.model.base import DingoopsObject
from dingo_command.api.model.chart import AppChartObject
    
class NetworkConfigObject(BaseModel):
    admin_subnet_id: Optional[str] = Field(None, description="管理网id")
    admin_network_name: Optional[str] = Field(None, description="管理网络id")
    bus_subnet_id: Optional[str] = Field(None, description="业务子网id")
    bus_network_name: Optional[str] = Field(None, description="管理网络名称")
    admin_cidr: Optional[str] = Field(None, description="管理网cidr")
    bus_cidr: Optional[str] = Field(None, description="业务网cidr")
    admin_network_id: Optional[str] = Field(None, description="管理网络id")
    bus_network_id: Optional[str] = Field(None, description="业务网络id")
    vip: Optional[str] = Field(None, description="管理网访问地址")
    floating_ip: Optional[bool] = Field(None, description="是否启用浮动ip")
    kube_lb_address: Optional[str] = Field(None, description="kube_lb_address地址")


class PortForwards(BaseModel):
    internal_port: Optional[int] = Field(None, description="转发的内部端口")
    external_port: Optional[int] = Field(None, description="转发的外部端口")
    protocol: Optional[str] = Field(None, description="协议")


class NodeConfigObject(BaseModel):
    count: Optional[int] = Field(None, description="项目id")
    image: Optional[str] = Field(None, description="用户id")
    flavor_id: Optional[str] = Field(None, description="节点规格")
    key_id: Optional[str] = Field(None, description="node在openstack中的id")
    #private_key: Optional[str] = Field(None, description="node在openstack中的id")
    user: Optional[str] = Field("root", description="node在openstack中的id")
    password: Optional[str] = Field(None, description="node在openstack中的id")
    auth_type: Optional[str] = Field(None, description="鉴权方式")
    role: Optional[str] = Field(None, description="节点角色")
    type: Optional[str] = Field(None, description="节点类型vm/metal")
    security_group: Optional[str] = Field(None, description="安全组名称")
    status: Optional[str] = Field(None, description="状态")
    instance_id: Optional[str] = Field(None, description="实例id")
    use_local_disk: Optional[bool] = Field(False, description="实例id")
    volume_type: Optional[str] = Field("", description="卷类型")
    volume_size: Optional[int] = Field(0, description="卷大小")
    
class NodeGroup(BaseModel):
    az: Optional[str] = Field(None, description="可用域")
    flavor: Optional[str] = Field(None, description="规格")
    floating_ip: Optional[bool] = Field(None, description="浮动ip")
    etcd: Optional[bool] = Field(None, description="是否是etcd节点")
    image_id: Optional[str] = Field(None, description="镜像id")
    port_forwards: Optional[List[PortForwards]] = Field(None, description="端口转发配置")
    use_local_disk: Optional[bool] = Field(None, description="实例id")
    volume_type: Optional[str] = Field(None, description="卷类型")
    volume_size: Optional[int] = Field(None, description="卷大小")

class KubeClusterObject(BaseModel):
    kube_lb_address: Optional[str] = Field(None, description="负载均衡器的浮动ip")
    kube_proxy_mode: Optional[str] = Field(None, description="kube proxy模式")
    loadbalancer_enabled: Optional[bool] = Field(False, description="是否启用负载均衡器")
    
    runtime: Optional[str] = Field(None, description="运行时类型")
    version: Optional[str] = Field("v1.32.0", description="k8s版本")
    kube_config: Optional[str] = Field(None, description="cni插件")
    service_cidr: Optional[str] = Field(None, description="服务网段")
    cni: Optional[str] = Field(None, description="cni")
    pod_cidr: Optional[str] = Field(None, description="pod的cidr")
    number_master: Optional[int] = Field(0, description="master节点数量")
        
class ClusterObject(DingoopsObject):
    name: str = Field(..., description="集群名称")
    project_id:str = Field(None, description="项目id")
    user_id: Optional[str] = Field(None, description="用户id")
    labels: Optional[str] = Field(None, description="集群标签")
    region_name: str = Field(None, description="region名称")
    network_config: Optional[NetworkConfigObject] = Field(None, description="网络配置")
    node_config: Optional[List[NodeConfigObject]] = Field(None, description="节点配置")
    type: str = Field(None, description="集群类型")
    security_group: Optional[str] = Field(None, description="安全组名称")
    kube_info: Optional[KubeClusterObject] = Field(None, description="k8s信息")
    status: Optional[str] = Field(None, description="集群状态")
    cpu: Optional[int] = Field(0, description="cpu数量")
    mem: Optional[int] = Field(0, description="mem数量")
    gpu: Optional[int] = Field(0, description="cpu数量")
    gpu_mem: Optional[int] = Field(0, description="gpu_mem数量")
    node_count: Optional[int] = Field(0, description="节点数量")
    status_msg: Optional[str] = Field(None, description="集群状态信息")
    private_key: Optional[str] = Field(None, description="集群私钥")
    extra: Optional[str] = Field(None, description="extra信息")
    forward_float_ip_id: Optional[str] = Field(None, description="集群浮动ip的id")
    forward_float_ip: Optional[str] = Field(None, description="集群浮动ip")
    port_forwards: Optional[List[PortForwards]] = Field(None, description="端口转发配置")
    charts: Optional[List[AppChartObject]] = Field(None, description="应用图表配置")


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
    server_id: Optional[str] = Field(None, description="server的id")
    instance_id: Optional[str] = Field(None, description="instance的id")
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
    image_uuid: Optional[str] = Field(None, description="用户id")
    nodes: Optional[Dict[str, NodeGroup]] = Field(None, description="集群状态")
    admin_subnet_id: Optional[str] = Field(None, description="管理子网id")
    bus_network_id: Optional[str] = Field(None, description="业务网络id")
    admin_network_id: Optional[str] = Field(None, description="管理网id")
    bus_subnet_id: Optional[str] = Field(None, description="业务子网id")
    ssh_user: Optional[str] = Field(None, description="用户名")
    password: Optional[str] = Field(None, description="密码")
    floatingip_pool: Optional[str] = Field(None, description="浮动ip池")
    public_floatingip_pool: Optional[str] = Field(None, description="公网浮动ip池") 
    external_subnetids: Optional[List[str]] = Field(None, description="公网浮动ip池") 
    public_subnetids: Optional[List[str]] = Field(None, description="公网浮动ip池") 
    subnet_cidr: Optional[str] = Field(None, description="运行时类型")
    use_existing_network: Optional[bool] = Field(None, description="是否使用已有网络")
    external_net: Optional[str] = Field(None, description="外部网络id")
    group_vars_path:  Optional[str] = Field(None, description="集群变量路径")

    number_of_etcd: Optional[int] = Field(0, description="ETCD节点数量")
    number_of_k8s_masters: Optional[int] = Field(0, description="K8s master节点数量")
    number_of_k8s_masters_no_etcd: Optional[int] = Field(0, description="不带ETCD的K8s master节点数量")
    number_of_k8s_masters_no_floating_ip: Optional[int] = Field(0, description="无浮动IP的K8s master节点数量")
    number_of_k8s_masters_no_floating_ip_no_etcd: Optional[int] = Field(0, description="无浮动IP且不带ETCD的K8s master节点数量")
    number_of_k8s_nodes: Optional[int] = Field(0, description="K8s worker节点数量")
    number_of_k8s_nodes_no_floating_ip: Optional[int] = Field(0, description="无浮动IP的K8s worker节点数量")
    k8s_master_loadbalancer_enabled: Optional[bool] = Field(False, description="是否启用负载均衡器")
    public_key_path: Optional[str] = Field(None, description="公钥路径")
    tenant_id: Optional[str] = Field(None, description="租户id")
    auth_url: Optional[str] = Field(None, description="鉴权url")
    token: Optional[str] = Field(None, description="token")
    forward_float_ip_id: Optional[str] = Field("", description="集群浮动ip的id")
    image_master: Optional[str] = Field(None, description="master节点的镜像")
    router_id: Optional[str] = Field(None, description="路由id")
    bastion_floatip_id: Optional[str] = Field(None, description="堡垒机浮动ip的id")
    pushgateway_url: Optional[str] = Field("", description="Prometheus Pushgateway的URL")

class NodeRemoveObject(BaseModel):
    cluster_id: Optional[str] = Field(None, description="集群id")
    node_list: Optional[List[str]] = Field(None, description="缩容节点列表")

class ScaleNodeObject(BaseModel):
    id: Optional[str] = Field(None, description="集群名称")
    node_config: Optional[List[NodeConfigObject]] = Field(None, description="节点配置")
