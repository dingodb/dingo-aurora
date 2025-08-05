
from dingo_command.common.keystone_client import KeystoneClient
from dingo_command.common.neutron import API as NeutronAPI
from dingo_command.common import CONF

PROJECT_NAME = "dingo-command"
NETWORK_NAME = "dingo-command-shared-net"
NETWORK_CIDR = "172.254.0.0/16"



def init_openstack_project_and_network():
    # 初始化项目
    keystone = KeystoneClient()
    project = keystone.get_project_by_name(PROJECT_NAME)
    if not project:
        project = keystone.create_project(PROJECT_NAME, "default")
    project_id = project.id

    # 初始化网络
    neutron_api = NeutronAPI()
    neutron = neutron_api.get_neutron_client(CONF)
    # 查询网络是否存在
    networks = neutron.list_networks(name=NETWORK_NAME).get('networks', [])
    if not networks:
        # 创建网络
        network = neutron.create_network({
            "network": {
                "name": NETWORK_NAME,
                "project_id": project_id,
                "shared": True
            }
        })
        network_id = network["network"]["id"]
        # 创建子网
        subnet = neutron.create_subnet({
            "subnet": {
                "name": f"{NETWORK_NAME}-subnet",
                "network_id": network_id,
                "ip_version": 4,
                "cidr": NETWORK_CIDR,
                "project_id": project_id
            }
        })
# 初始化时自动调用
init_openstack_project_and_network()