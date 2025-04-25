# dingoops的裸机的client
# self.region_name = region_name
import requests
import json

from common import CONF

# 配置ironic信息
IRONIC_AUTH_URL = CONF.ironic.auth_url
IRONIC_AUTH_TYPE = CONF.ironic.auth_type
IRONIC_PROJECT_NAME = CONF.ironic.project_name
IRONIC_PROJECT_DOMAIN = CONF.ironic.project_domain
IRONIC_USER_NAME = CONF.ironic.user_name
IRONIC_USER_DOMAIN = CONF.ironic.user_domain
IRONIC_PASSWORD = CONF.ironic.password
IRONIC_REGION_NAME = CONF.ironic.region_name


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
                            "name": IRONIC_USER_NAME,
                            "password": IRONIC_PASSWORD,
                            "domain": {"name": IRONIC_USER_DOMAIN}
                        }
                    }
                },
                "scope": {
                    "project": {
                        "name": IRONIC_PROJECT_NAME,
                        "domain": {"name": IRONIC_PROJECT_DOMAIN}
                    }
                }
            }
        }

        headers = {'Content-Type': 'application/json'}
        response = requests.post(f"{IRONIC_AUTH_URL}/v3/auth/tokens", data=json.dumps(auth_data), headers=headers)
        if response.status_code != 201:
            print(f"ironic获取token失败: {response.text}")
        else:
            self.token = response.headers['X-Subject-Token']
            self.service_catalog = response.json()['token']['catalog']
            self.session.headers.update({'X-Auth-Token': self.token})
            self.session.headers.update({'X-OpenStack-Ironic-API-Version': "latest" })


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
            raise Exception(f"ironic请求失败: {response.text}")
        return response.json()['nodes']

    def keystone_get_user_by_id(self, user_id):
        """获取Ironic节点列表"""
        endpoint = self.get_service_endpoint('identity')
        response = self.session.get(f"{endpoint}/v3/users/"+user_id)
        if response.status_code != 200:
            raise Exception(f"user请求失败: {response.text}")
        return response.json()['user']

    def keystone_get_project_by_id(self, project_id):
        """获取Ironic节点列表"""
        endpoint = self.get_service_endpoint('identity')
        response = self.session.get(f"{endpoint}/v3/projects/"+project_id)
        if response.status_code != 200:
            raise Exception(f"project请求失败: {response.text}")
        return response.json()['project']

# 声明裸金属的client
ironic_client = IronicClient()