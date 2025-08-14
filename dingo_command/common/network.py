from dingo_command.common.neutron import API as NeutronAPI
from dingo_command.common.nova_client import NovaClient
from dingo_command.common import CONF
import subprocess

def get_controller_nodes():
    #获取openstack的所有主节点
    control_nodes = CONF.default.controller_nodes
    if not control_nodes:
        raise Exception("No control nodes configured in the dingo-command configuration.")
    control_nodes = control_nodes.split(',')
    
    return control_nodes 

def get_network_ports(network_name):
    neutron_api = NeutronAPI()
    neutron = neutron_api.get_neutron_client(CONF)
    networks = neutron.list_networks(name=network_name).get('networks', [])
    if not networks:
        raise Exception(f"Network {network_name} not found")
    network_id = networks[0]['id']
    ports = neutron.list_ports(network_id=network_id).get('ports', [])
    if not ports:
        return None
    return ports[0]

def assign_ports_to_ovs(port, node_ip):
    #ssh到node_ip上执行命令cmd命令

    iface = port['name']
    mac = port['mac_address']
    iface_id = port['id']
    ip_addr = port['fixed_ips'][0]['ip_address']
    # 这里假设/24，实际应根据子网信息获取
    cmd = (
        f"ovs-vsctl --may-exist add-port br-int {iface} "
        f"-- set Interface {iface} type=internal "
        f"-- set Interface {iface} external-ids:iface-status=active "
        f"-- set Interface {iface} external-ids:attached-mac={mac} "
        f"-- set Interface {iface} external-ids:iface-id={iface_id} && "
        f"ip link set dev {iface} address {mac} && "
        f"ip addr add {ip_addr}/24 dev {iface} && "
        f"ip link set {iface} up"
    )
    subprocess.run(cmd, shell=True, check=True)




def connect_network_to_vpc(project_id:str):
    """
    将 dingo-command-shared-net 网络连接到用户 project 的路由上
    """
    neutron_api = NeutronAPI()
    neutron = neutron_api.get_neutron_client(CONF)
    # 获取 dingo-command-shared-net 网络
    networks = neutron.list_networks(name="dingo-command-shared-net").get('networks', [])
    if not networks:
        raise Exception("dingo-command-shared-net 网络不存在")
    network_id = networks[0]['id']
    # 获取该网络的子网
    subnets = neutron.list_subnets(network_id=network_id).get('subnets', [])
    if not subnets:
        raise Exception("dingo-command-shared-net 没有子网")
    subnet_id = subnets[0]['id']
    # 获取名为cluster-router的路由器,根据project过滤
    port_ip = ""
    routers = neutron.list_routers(project_id=project_id).get('routers', [])
    for router in routers:
        if router['name'] != 'cluster-router':
            continue
        # 检查是否已连接
        ports = neutron.list_ports(device_id=router['id'], network_id=network_id).get('ports', [])
        if not ports:
            # 添加接口到路由器
            neutron.add_interface_router(router['id'], {'subnet_id': subnet_id})
            #获取添加到路由器上的port的ip
            ports = neutron.list_ports(device_id=router['id'], network_id=network_id).get('ports', [])
            for port in ports:
                print(f"路由器{router['name']} ({router['id']}) 上的端口 {port['name']} ({port['id']}) 的IP地址为 {port['fixed_ips'][0]['ip_address']}")
            print(f"已将子网{subnet_id}连接到路由器{router['name']} ({router['id']})")
        else:
            print(f"路由器{router['name']} ({router['id']}) 已连接该网络")
        port_ip = ports[0]['fixed_ips'][0]['ip_address']
    #返回vpc子网的cidr
    return subnets[0]['cidr'],port_ip

def init_cluster_network(project_id:str, subnet_id:str):
    # 初始化网络配置
    controller_nodes = get_controller_nodes()
    cidr, port_ip = connect_network_to_vpc(project_id)
    index = 1
    # 根据subnet_id获取网络的cidr
    subnet = neutron_api.get_subnet_by_id(subnet_id)
    cidr = subnet.get('cidr', cidr)
    print(f"VPC子网的CIDR为 {cidr}")
    for node in controller_nodes:
        print(f"正在初始化控制节点 {node['name']} 的网络配置...")
        #创建port
        port = get_network_ports("dingo-port-" + index)

        if not port:
            print(f"控制节点 {node['name']} 没有找到相关网络端口，尝试创建...")
            # 如果没有端口，可能需要创建一个新的端口
            neutron_api = NeutronAPI()
            neutron = neutron_api.get_neutron_client(CONF)
            network_id = neutron.list_networks(name="dingo-command-shared-net").get('networks', [])[0]['id']
            port = neutron.create_port({
                "port": {
                    "network_id": network_id,
                    "name": "dingo-port-" + index,
                    "admin_state_up": True
                }
            })

        # 将端口分配到 OVS
        assign_ports_to_ovs(port, node)
        print(f"控制节点 {node['name']} 的网络端口已分配到 OVS")
        cmd = f"ip route add {node['name']} {cidr} via {port_ip} dev dingo-port-{node['name']}"
        subprocess.run(cmd, shell=True, check=True)
    
    print("网络初始化完成，dingo-command-shared-net 已连接到 VPC 路由上。")

