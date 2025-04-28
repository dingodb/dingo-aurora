"""
获取neutron的client，查询所有的外部网络列表
"""

import os
from typing import Dict, List, Optional, Any

from neutronclient.v2_0 import client as neutron_client
from keystoneauth1 import loading
from keystoneauth1 import session
from dingoops.services import CONF

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

