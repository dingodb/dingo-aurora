"""
获取neutron的client，查询所有的外部网络列表
"""

from typing import Dict, List, Any

from neutronclient.v2_0 import client as neutron_client
from keystoneauth1 import loading
from keystoneauth1 import session
from dingo_command.services import CONF

class API:
    
    def get_neutron_client(self, conf) -> neutron_client.Client:
        """
        获取Neutron客户端
        
        参数:
            auth_url: Keystone认证URL
            username: 用户名
            password: 密码
            project_name: 项目名称
            project_domain_name: 项目域名称，默认为'Default'
            user_domain_name: 用户域名称，默认为'Default'
            region_name: 区域名称
        
        返回:
            neutron_client.Client: Neutron客户端实例
        """
        # 优先使用传入的参数，否则从环境变量获取
        sss = conf["neutron"]
        nb = conf["neutron"].auth_section
        region_name = conf.neutron.region_name

        auth_plugin = loading.load_auth_from_conf_options(conf,
                                        'neutron')
        # 创建session
        sess = session.Session(auth=auth_plugin)
        
        # 创建neutron客户端
        neutron = neutron_client.Client(session=sess, region_name=region_name)
        
        return neutron

    def list_external_networks(self, neutron_client: neutron_client.Client = None, **kwargs) -> List[Dict[str, Any]]:
        """
        获取所有的外部网络列表
        
        参数:
            neutron_client: Neutron客户端实例，如果未提供则自动创建
            **kwargs: 传递给get_neutron_client的参数
        
        返回:
            List[Dict[str, Any]]: 外部网络列表
        """
        if neutron_client is None:
            neutron_client = self.get_neutron_client(CONF)
        
        # 查询所有外部网络
        networks = neutron_client.list_networks(**{'router:external': True})
        
        return networks.get('networks', [])
    def get_network_by_id(self, network_id: str, neutron_client: neutron_client.Client = None, **kwargs) -> Dict[str, Any]:
        """
        根据网络ID查询网络信息
        
        参数:
            network_id: 网络ID
            neutron_client: Neutron客户端实例，如果未提供则自动创建
            **kwargs: 传递给get_neutron_client的参数
        
        返回:
            Dict[str, Any]: 网络信息，如果网络不存在则返回空字典
        """
        if neutron_client is None:
            neutron_client = self.get_neutron_client(CONF)
        
        try:
            # 根据ID查询网络
            network = neutron_client.show_network(network_id)
            return network.get('network', {})
        except Exception as e:
            # 处理网络不存在或其他错误的情况
            print(f"获取网络信息失败: {str(e)}")
            return {}
    def get_subnet_by_id(self, subnet_id: str, neutron_client: neutron_client.Client = None, **kwargs) -> Dict[str, Any]:
        """
        根据子网ID查询子网信息
        
        参数:
            subnet_id: 子网ID
            neutron_client: Neutron客户端实例，如果未提供则自动创建
            **kwargs: 传递给get_neutron_client的参数
        
        返回:
            Dict[str, Any]: 子网信息，如果子网不存在则返回空字典
        """
        if neutron_client is None:
            neutron_client = self.get_neutron_client(CONF)
        
        try:
            # 根据ID查询子网
            subnet = neutron_client.show_subnet(subnet_id)
            return subnet.get('subnet', {})
        except Exception as e:
            # 处理子网不存在或其他错误的情况
            print(f"获取子网信息失败: {str(e)}")
            return {}

