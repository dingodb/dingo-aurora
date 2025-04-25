# dingoops的nova的client
import requests
import json

from common import CONF

# 配置nova信息
NOVA_AUTH_URL = CONF.nova.auth_url
NOVA_AUTH_TYPE = CONF.nova.auth_type
NOVA_PROJECT_NAME = CONF.nova.project_name
NOVA_PROJECT_DOMAIN = CONF.nova.project_domain
NOVA_USER_NAME = CONF.nova.user_name
NOVA_USER_DOMAIN = CONF.nova.user_domain
NOVA_PASSWORD = CONF.nova.password
NOVA_REGION_NAME = CONF.nova.region_name


class NovaClient:

    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.service_catalog = []

        # 认证并初始化session
        self.authenticate()

    def authenticate(self):
        """获取认证Token和服务目录"""
        auth_data = {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": NOVA_USER_NAME,
                            "password": NOVA_PASSWORD,
                            "domain": {"name": NOVA_USER_DOMAIN}
                        }
                    }
                },
                "scope": {
                    "project": {
                        "name": NOVA_PROJECT_NAME,
                        "domain": {"name": NOVA_PROJECT_DOMAIN}
                    }
                }
            }
        }

        headers = {'Content-Type': 'application/json'}
        response = requests.post(f"{NOVA_AUTH_URL}/v3/auth/tokens", data=json.dumps(auth_data), headers=headers)
        if response.status_code != 201:
            print(f"nova获取token失败: {response.text}")
        else:
            self.token = response.headers['X-Subject-Token']
            self.service_catalog = response.json()['token']['catalog']
            self.session.headers.update({'X-Auth-Token': self.token})
            self.session.headers.update({'X-OpenStack-Nova-API-Version': "latest" })


    def get_service_endpoint(self, service_type, interface='public', region='RegionOne'):
        """根据服务类型获取Endpoint"""
        for service in self.service_catalog:
            if service['type'] == service_type:
                for endpoint in service['endpoints']:
                    if endpoint['interface'] == interface and endpoint['region'] == region:
                        return endpoint['url']
        raise Exception(f"未找到服务: {service_type}")

    # 添加Nova服务调用
    def nova_list_servers(self):
        endpoint = self.get_service_endpoint('compute')
        response = self.session.get(f"{endpoint}/servers")
        if response.status_code != 200:
            raise Exception(f"nova请求失败: {response.text}")
        return response.json()['servers']

    # 虚拟机详情
    def nova_get_server_detail(self, server_id):
        endpoint = self.get_service_endpoint('compute')
        response = self.session.get(f"{endpoint}/servers/"+ server_id)
        if response.status_code != 200:
            raise Exception(f"nova请求失败: {response.text}")
        return response.json()['server']

# 声明nova的client
nova_client = NovaClient()