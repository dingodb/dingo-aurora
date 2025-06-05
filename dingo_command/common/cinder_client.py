# dingo-command的裸机的client
# self.region_name = region_name
import requests
import json

from dingo_command.common import CONF

# 配置cinder信息
CINDER_AUTH_URL = CONF.cinder.auth_url
CINDER_AUTH_TYPE = CONF.cinder.auth_type
CINDER_PROJECT_NAME = CONF.cinder.project_name
CINDER_PROJECT_DOMAIN = CONF.cinder.project_domain
CINDER_USER_NAME = CONF.cinder.user_name
CINDER_USER_DOMAIN = CONF.cinder.user_domain
CINDER_PASSWORD = CONF.cinder.password
CINDER_REGION_NAME = CONF.cinder.region_name


class CinderClient:

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
                            "name": CINDER_USER_NAME,
                            "password": CINDER_PASSWORD,
                            "domain": {"name": CINDER_USER_DOMAIN}
                        }
                    }
                },
                "scope": {
                    "project": {
                        "name": CINDER_PROJECT_NAME,
                        "domain": {"name": CINDER_PROJECT_DOMAIN}
                    }
                }
            }
        }

        headers = {'Content-Type': 'application/json'}
        try:
            response = requests.post(f"{CINDER_AUTH_URL}/v3/auth/tokens", data=json.dumps(auth_data), headers=headers)
            if response.status_code != 201:
                print(f"cinder[{CINDER_AUTH_URL}] 获取token失败: {response.text}")
            else:
                self.token = response.headers['X-Subject-Token']
                self.service_catalog = response.json()['token']['catalog']
                self.session.headers.update({'X-Auth-Token': self.token})
                self.session.headers.update({'X-OpenStack-Ironic-API-Version': "latest" })
        except Exception as e:
            print(f"cinder[{CINDER_AUTH_URL}] 获取token报错：{e}")


    def get_service_endpoint(self, service_type, interface='public', region='RegionOne'):
        """根据服务类型获取Endpoint"""
        for service in self.service_catalog:
            if service['type'] == service_type:
                for endpoint in service['endpoints']:
                    if endpoint['interface'] == interface and endpoint['region'] == region:
                        return endpoint['url']
        raise Exception(f"未找到服务: {service_type}")

    def list_volum_type(self):
        """获取Ironic节点列表"""
        endpoint = self.get_service_endpoint('volumev3')
        response = self.session.get(f"{endpoint}/types")
        if response.status_code == 200:
            volume_types = response.json().get('volume_types', [])
            res = ""
            for vt in volume_types:
                print(f"- Name: {vt['name']}, ID: {vt['id']}, Description: {vt.get('description', 'N/A')}")
                if "lvm-cluster" in vt['name']:
                    res = vt['name']
            return res
        else:
            return ""