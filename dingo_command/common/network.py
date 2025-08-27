import re
from dingo_command.common.neutron import API as NeutronAPI
from dingo_command.common.nova_client import NovaClient
from dingo_command.common import CONF
import subprocess

def get_controller_nodes():
    #获取openstack的所有主节点
    control_nodes = CONF.DEFAULT.controller_nodes
    if not control_nodes:
        raise Exception("No control nodes configured in the dingo-command configuration.")
    control_nodes = control_nodes.split(',')
    
    return control_nodes 

def get_network_ports(port_name):
    neutron_api = NeutronAPI()
    neutron = neutron_api.get_neutron_client(CONF)
    networks = neutron.list_networks(name="dingo-command-shared-net")
    network_id = networks.get('networks', [])[0].get('id')
    if not networks:
        raise Exception(f"Network dingo-command-share-net not found")
    # 根据port_name查询端口
    ports = neutron.list_ports(name=port_name, network_id=network_id).get('ports', [])
    # 如果没有找到端口，返回None            
    if not ports:
        return None, network_id
    return ports[0], network_id


def generate_ovs_command(port):
    iface = port['name']
    mac = port['mac_address']
    iface_id = port['id']
    ip_addr = port['fixed_ips'][0]['ip_address']
    # 这里假设/24，实际应根据子网信息获取
    # 检查设备是否已存在
    
    cmd = (
        f"ovs-vsctl --db=unix:/run/openvswitch/db.sock --may-exist add-port br-int {iface} "
        f"-- set Interface {iface} type=internal "
        f"-- set Interface {iface} external-ids:iface-status=active "
        f"-- set Interface {iface} external-ids:attached-mac={mac} "
        f"-- set Interface {iface} external-ids:iface-id={iface_id} && "
        f"ip link set dev {iface} address {mac} && "
        f"ip addr add {ip_addr}/16 dev {iface} && "
        f"ip link set {iface} up"
    )
    return cmd

def assign_ports_to_ovs(port, node_ip, password = ""):
    #ssh到node_ip上执行命令cmd命令
    # 读取controller_pass文件获取密码
    # with open('/etc/dingo/controller_pass', 'r') as f:
    #     password = f.read().strip()
    # 使用sshpass通过ssh连接到节点并执行命令
    iface = port['name']
    check_cmd = f"sshpass -p {password} ssh -o StrictHostKeyChecking=no root@{node_ip} 'ip link show {iface}'"
    check_result = subprocess.run(check_cmd, shell=True, capture_output=True)
    if check_result.returncode == 0:
        # 设备已存在，不再执行后续步骤
        return
    ssh_cmd = generate_ovs_command(port)
    if ssh_cmd == "":
        return
    cmd = f"sshpass -p {password} ssh -o StrictHostKeyChecking=no root@{node_ip} '{ssh_cmd}'"
    res = subprocess.run(cmd, shell=True, check=True)
    if res.returncode != 0:
        print(f"在节点 {node_ip} 上执行命令失败: {res.stderr}")
        return
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
    subnet_info = subnets[0]
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
            network_cidr = subnet_info['cidr']
            # 获取已分配的IP地址
            used_ips = set()
            existing_ports = neutron.list_ports(network_id=network_id).get('ports', [])
            for p in existing_ports:
                for ip_info in p.get('fixed_ips', []):
                    used_ips.add(ip_info['ip_address'])
            # 获取子网的所有可用IP
            import ipaddress
            subnet_ips = list(ipaddress.ip_network(network_cidr).hosts())
            assigned_ip = None
            for ip in subnet_ips:
                ip_str = str(ip)
                if ip_str not in used_ips:
                    assigned_ip = ip_str
                    break
            if not assigned_ip:
                raise Exception("No available IP addresses in subnet for router interface.")
            port_body = {
                'port': {
                    'network_id': subnet_info['network_id'],
                    'fixed_ips': [{'subnet_id': subnet_id, 'ip_address': assigned_ip}],
                    'device_owner': 'network:router_interface'
                }
            }
            port = neutron.create_port(port_body)
            port_id = port['port']['id']
            print(f"为路由器 {router['name']} ({router['id']}) 分配 IP 地址 {assigned_ip}")
            neutron.add_interface_router(router['id'], body={'port_id': port_id})
         #获取添加到路由器上的port的ip
            ports = neutron.list_ports(device_id=router['id'], network_id=network_id).get('ports', [])
            for port in ports:
                print(f"路由器{router['name']} ({router['id']}) 上的端口 {port['name']} ({port['id']}) 的IP地址为 {port['fixed_ips'][0]['ip_address']}")
            print(f"已将子网{subnet_id}连接到路由器{router['name']} ({router['id']})")
            port_ip = assigned_ip
        else:
            print(f"路由器{router['name']} ({router['id']}) 已连接该网络")
            port_ip = ports[0]['fixed_ips'][0]['ip_address']
    #返回vpc子网的cidr
    return subnets[0]['cidr'],port_ip

def init_cluster_network(project_id:str, subnet_id:str):
    # 初始化网络配置
    # 读取password文件获取密码
    password = CONF.DEFAULT.controller_password
    
    controller_nodes = get_controller_nodes()
    cidr, port_ip = connect_network_to_vpc(project_id)
    index = 1
    # 根据subnet_id获取网络的cidr
    neutron_api = NeutronAPI()
    neutron = neutron_api.get_neutron_client(CONF)
    subnet = neutron.show_subnet(subnet_id).get('subnet', {})
    cidr = subnet.get('cidr', cidr)
    print(f"VPC子网的CIDR为 {cidr}")
    for node in controller_nodes:
        print(f"正在为控制节点 {node} 初始化网络配置...")
        #创建port
        port,network_id = get_network_ports("dingo-port-" + str(index))

        if not port:
            print(f"控制节点 {node} 没有找到相关网络端口，尝试创建...")
            # 如果没有端口，可能需要创建一个新的端口
            neutron_api = NeutronAPI()
            neutron = neutron_api.get_neutron_client(CONF)
            network_id = neutron.list_networks(name="dingo-command-shared-net").get('networks', [])[0]['id']
            port = neutron.create_port({
                "port": {
                    "network_id": network_id,
                    "name": "dingo-port-" + str(index),
                    "admin_state_up": True
                }
            })

            # 将端口分配到 OVS
        assign_ports_to_ovs(port, node, password)
        print(f"控制节点 {node}  的网络端口已分配到 OVS")
        cmd = f"route add -net {cidr} gw {port_ip}"
        ssh_cmd = f"sshpass -p {password} ssh -o StrictHostKeyChecking=no root@{node} '{cmd}'"
        
        try:
            res = subprocess.run(ssh_cmd, shell=True, check=True, capture_output=True, text=True)
            if res.returncode == 0:
                print(f"在节点 {node} 上执行命令成功: {res.stdout}")
            else:
                print(f"在节点 {node} 上执行命令失败: {res.stderr}")
        except subprocess.CalledProcessError as e:
            print(f"在节点 {node} 上执行命令失败: {e.stderr}")
            print(f"请检查密码是否正确、root用户是否允许SSH登录、目标主机{node}是否可达。")
        index += 1

    print("网络初始化完成，dingo-command-shared-net 已连接到 VPC 路由上。")
