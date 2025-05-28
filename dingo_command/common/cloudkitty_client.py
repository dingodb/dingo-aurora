import json

import requests
from dingo_command.common import CONF


# 配置nova信息
CLOUDKITTY_AUTH_URL = CONF.cloudkitty.auth_url
CLOUDKITTY_AUTH_TYPE = CONF.cloudkitty.auth_type
CLOUDKITTY_PROJECT_NAME = CONF.cloudkitty.project_name
CLOUDKITTY_PROJECT_DOMAIN = CONF.cloudkitty.project_domain
CLOUDKITTY_USER_NAME = CONF.cloudkitty.user_name
CLOUDKITTY_USER_DOMAIN = CONF.cloudkitty.user_domain
CLOUDKITTY_PASSWORD = CONF.cloudkitty.password
CLOUDKITTY_REGION_NAME = CONF.cloudkitty.region_name

class CloudKittyClient:
    def __init__(self, token=None):

        self.session = requests.Session()
        self.token = token

        # 认证并初始化session
        self.authenticate()

    def authenticate(self):
        """获取认证Token和服务目录"""
        if not self.token:
            auth_data = {
                "auth": {
                    "identity": {
                        "methods": ["password"],
                        "password": {
                            "user": {
                                "name": CLOUDKITTY_USER_NAME,
                                "password": CLOUDKITTY_PASSWORD,
                                "domain": {"name": CLOUDKITTY_USER_DOMAIN}
                            }
                        }
                    },
                    "scope": {
                        "project": {
                            "name": CLOUDKITTY_PROJECT_NAME,
                            "domain": {"name": CLOUDKITTY_PROJECT_DOMAIN}
                        }
                    }
                }
            }

            headers = {'Content-Type': 'application/json'}
            try:
                response = requests.post(f"{CLOUDKITTY_AUTH_URL}/v3/auth/tokens", data=json.dumps(auth_data), headers=headers)
                if response.status_code != 201:
                    print(f"cloudkitty获取token失败: {response.text}")
                else:
                    self.token = response.headers['X-Subject-Token']
                    self.service_catalog = response.json()['token']['catalog']
                    self.session.headers.update({'X-Auth-Token': self.token})
                    self.session.headers.update({'X-OpenStack-CloudKitty-API-Version': "latest"})
            except Exception as e:
                print(f"cloudkitty[{CLOUDKITTY_AUTH_URL}] 获取token报错：{e}")
        else:
            headers = {'X-Auth-Token': self.token, 'X-Subject-Token': self.token}
            response = requests.get(f"{CLOUDKITTY_AUTH_URL}/v3/auth/tokens", headers=headers)
            if response.status_code != 200:
                print(f"cloudkitty获取token失败: {response.text}")
            else:
                # self.token = response.headers['X-Subject-Token']
                self.service_catalog = response.json()['token']['catalog']
                self.session.headers.update({'X-Auth-Token': self.token})
                self.session.headers.update({'X-OpenStack-CloudKitty-API-Version': "latest"})

    def get_service_endpoint(self, service_type, interface='public', region='RegionOne'):
        """根据服务类型获取Endpoint"""
        for service in self.service_catalog:
            if service['type'] == service_type:
                for endpoint in service['endpoints']:
                    if endpoint['interface'] == interface and endpoint['region'] == region:
                        return endpoint['url']
        raise Exception(f"未找到服务: {service_type}")


    # 添加Nova服务调用
    def get_storage_dataframes(self, filters=None):
        endpoint = self.get_service_endpoint('rating')
        response = self.session.get(f"{endpoint}/v1/storage/dataframes", params=filters)
        if response.status_code != 200:
            raise Exception(f"cloudkitty[{endpoint}]请求失败: {response.text}")
        print(f"{endpoint}/v1/storage/dataframes 返回数据大小: {len(response.json()['dataframes'])}")
        return response.json()['dataframes']