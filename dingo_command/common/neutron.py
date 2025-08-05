"""
获取neutron的client，查询所有的外部网络列表
"""

from typing import Dict, List, Any

from neutronclient.v2_0 import client as neutron_client
from keystoneauth1 import loading
from keystoneauth1 import session
from dingo_command.common import CONF

class API:
    
    def get_neutron_client(self, conf) -> neutron_client.Client:
        """
        获取Neutron客户端
        
        参数:
            auth_url: Keystone认证URL
            user_name: 用户名
            password: 密码
            project_name: 项目名称
            project_domain_name: 项目域名称，默认为'Default'
            user_domain_name: 用户域名称，默认为'Default'
            region_name: 区域名称
        
        返回:
            neutron_client.Client: Neutron客户端实例
        """
        # 优先使用传入的参数，否则从环境变量获取
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
        

    def list_router(self, name: str, tenant_id: str,neutron_client: neutron_client.Client = None, **kwargs)-> Dict[str, Any]:
        if neutron_client is None:
            neutron_client = self.get_neutron_client(CONF)
        
        try:
            # 构建查询参数
            search_opts = {}
            if name:
                search_opts['name'] = name
            if tenant_id:
                search_opts['tenant_id'] = tenant_id
            
            # 添加其他查询参数
            search_opts.update(kwargs)
            
            # 查询路由器
            routers = neutron_client.list_routers(**search_opts)
            return routers.get('routers', [])
            
        except Exception as e:
            # 处理查询失败的情况
            print(f"查询路由器失败: {str(e)}")
            return []

    def get_router_by_name(self, name: str, tenant_id: str, neutron_client: neutron_client.Client = None, **kwargs) -> Dict[str, Any]:
        """
        根据路由器名称查询单个路由器信息
        
        参数:
            name: 路由器名称
            neutron_client: Neutron客户端实例，如果未提供则自动创建
            **kwargs: 传递给get_neutron_client的参数
        
        返回:
            Dict[str, Any]: 路由器信息，如果路由器不存在则返回空字典
        """
        routers = self.list_router(name=name,tenant_id=tenant_id, neutron_client=neutron_client, **kwargs)
        
        if routers:
            return routers[0]  # 返回第一个匹配的路由器
        else:
            return {}
    def get_floatingip_by_tags(self, tags: List[str], neutron_client: neutron_client.Client = None, **kwargs) -> List[Dict[str, Any]]:
        """
        根据 tags 查询符合条件的浮动IP列表
        
        参数:
            tags: 标签列表
            neutron_client: Neutron客户端实例，如果未提供则自动创建
            **kwargs: 其他查询参数
        
        返回:
            List[Dict[str, Any]]: 符合条件的浮动IP列表
        """
        if neutron_client is None:
            neutron_client = self.get_neutron_client(CONF)
        
        try:
            # 构建查询参数
            search_opts = {}
            if tags:
                search_opts['tags'] = tags
            
            # 添加其他查询参数
            search_opts.update(kwargs)
            
            # 查询浮动IP
            floatingips = neutron_client.list_floatingips(**search_opts)
            return floatingips.get('floatingips', [])
            
        except Exception as e:
            # 处理查询失败的情况
            print(f"查询浮动IP失败: {str(e)}")
            return [] 
        
    def get_first_floatingip_id_by_tags(self, tags: List[str], neutron_client: neutron_client.Client = None, **kwargs) -> str:
        """
        根据 tags 查询第一个符合条件的浮动IP的ID
        
        参数:
            tags: 标签列表
            neutron_client: Neutron客户端实例，如果未提供则自动创建
            **kwargs: 其他查询参数
        
        返回:
            str: 第一个符合条件的浮动IP的ID，如果没有找到则返回空字符串
        """
        floatingips = self.get_floatingip_by_tags(tags, neutron_client, **kwargs)
        
        if floatingips:
            return floatingips[0]['id'], floatingips[0]['floating_ip_address']
        else:
            return "", ""