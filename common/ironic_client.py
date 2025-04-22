# dingoops的裸机的client
# self.region_name = region_name
import requests
import json

from common import CONF

# 配置ironic信息
AUTH_URL = CONF.ironic.auth_url
AUTH_TYPE = CONF.ironic.auth_type
PROJECT_NAME = CONF.ironic.project_name
PROJECT_DOMAIN = CONF.ironic.project_domain
USER_NAME = CONF.ironic.user_name
USER_DOMAIN = CONF.ironic.user_domain
PASSWORD = CONF.ironic.password
REGION_NAME = CONF.ironic.region_name


class IronicClient:

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
                            "name": USER_NAME,
                            "password": PASSWORD,
                            "domain": {"name": USER_DOMAIN}
                        }
                    }
                },
                "scope": {
                    "project": {
                        "name": PROJECT_NAME,
                        "domain": {"name": PROJECT_DOMAIN}
                    }
                }
            }
        }

        headers = {'Content-Type': 'application/json'}
        response = requests.post(f"{AUTH_URL}/v3/auth/tokens", data=json.dumps(auth_data), headers=headers)
        if response.status_code != 201:
            raise Exception(f"认证失败: {response.text}")

        self.token = response.headers['X-Subject-Token']
        self.service_catalog = response.json()['token']['catalog']
        self.session.headers.update({'X-Auth-Token': self.token})


    def get_service_endpoint(self, service_type, interface='public', region='RegionOne'):
        """根据服务类型获取Endpoint"""
        for service in self.service_catalog:
            if service['type'] == service_type:
                for endpoint in service['endpoints']:
                    if endpoint['interface'] == interface and endpoint['region'] == region:
                        return endpoint['url']
        raise Exception(f"未找到服务: {service_type}")

    def ironic_list_nodes(self):
        """获取Ironic节点列表"""
        endpoint = self.get_service_endpoint('baremetal')
        response = self.session.get(f"{endpoint}/v1/nodes/detail")
        if response.status_code != 200:
            raise Exception(f"请求失败: {response.text}")
        return response.json()['nodes']

    def users_list(self):
        """获取Ironic节点列表"""
        endpoint = self.get_service_endpoint('identity')
        response = self.session.get(f"{endpoint}/v3/users")
        if response.status_code != 200:
            raise Exception(f"请求失败: {response.text}")
        return response.json()['users']

    # 示例：添加Nova服务调用
    def nova_list_servers(self):
        endpoint = self.get_service_endpoint('compute')
        response = self.session.get(f"{endpoint}/servers")
        return response.json()

# 声明裸金属的client
ironic_client = IronicClient()