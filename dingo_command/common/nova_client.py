# dingo-command的nova的client
import requests
import json
from fastapi import HTTPException
from dingo_command.common import CONF

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

    def __init__(self, token=None):
        self.session = requests.Session()
        self.token = token
        self.service_catalog = []

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
        else:
            headers = {'X-Auth-Token': self.token, 'X-Subject-Token': self.token}
            response = requests.get(f"{NOVA_AUTH_URL}/v3/auth/tokens", headers=headers)
            if response.status_code == 200:
                self.service_catalog = response.json()['token']['catalog']
                self.session.headers.update({'X-Auth-Token': self.token})
                self.session.headers.update({'X-OpenStack-Nova-API-Version': "latest"})
            elif response.status_code == 401:
                raise HTTPException(status_code=401, detail="The request you have made requires authentication.")
            else:
                print(f"nova获取token失败: {response.text}")

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
            raise Exception(f"nova详情请求失败: {response.text}")
        return response.json()['server']

    # 根据id查询规格
    def nova_get_flavor(self, flavor_id):
        endpoint = self.get_service_endpoint('compute')
        response = self.session.get(f"{endpoint}/flavors/"+ flavor_id)
        if response.status_code != 200:
            raise Exception(f"nova规格请求失败: {response.text}")
        return response.json()['flavor']

    # 根据name查询规格
    def nova_get_flavor_by_name(self, flavor_name):
        endpoint = self.get_service_endpoint('compute')
        response = self.session.get(f"{endpoint}/flavors/detail")
        if response.status_code != 200:
            raise Exception(f"获取规格列表失败: {response.text}")
        flavors = response.json()['flavors']
        matched_flavors = [f for f in flavors if f['name'] == flavor_name]

        if not matched_flavors:
            raise ValueError(f"未找到名称为 '{flavor_name}' 的规格")

        return matched_flavors[0]

    # 根据image_id查询规格
    def glance_get_image(self, image_id):
        endpoint = self.get_service_endpoint('image')
        response = self.session.get(f"{endpoint}/v2/images/"+ image_id)
        if response.status_code != 200:
            raise Exception(f"nova规格请求失败: {response.text}")
        return response.json()

    # 根据image_name查询规格
    def get_image(self, image_name):
        endpoint = self.get_service_endpoint('image')
        params = {'name': image_name}
        response = self.session.get(f"{endpoint}/v2/images", params=params)
        if response.status_code != 200:
            raise Exception(f"nova规格请求失败: {response.text}")
        return response.json()['images'][0]

    def nova_create_server(self, name, image_id, flavor_id, network_id, security_groups=None, user_data=None,
                           key_name=None, metadata=None, config_drive=False):
        """
        创建虚拟机
        :param name: 虚拟机名称（需唯一）
        :param image_id: 镜像ID（通过glance_get_image验证）
        :param flavor_id: 规格ID（通过nova_get_flavor验证）
        :param network_id: 网络ID
        :param security_groups: 可选安全组列表（如['default']）
        :return: 虚拟机创建响应数据
        """
        # 1. 参数预验证
        # self.glance_get_image(image_id)
        # self.nova_get_flavor(flavor_id)
        # 2. 构造请求体
        request_body = {
            "server": {
                "name": name,
                "imageRef": image_id,
                "flavorRef": flavor_id,
                "networks": [{"uuid": network_id}]
            }
        }
        if security_groups:
            request_body["server"]["security_groups"] = [
                {"name": sg} for sg in security_groups
            ]
        if user_data:
            request_body["server"]["user_data"] = user_data
        if key_name:
            request_body["server"]["key_name"] = key_name
        if metadata:
            request_body["server"]["metadata"] = metadata
        if config_drive:
            request_body["server"]["config_drive"] = config_drive
        # 3. 获取Nova服务端点
        endpoint = self.get_service_endpoint('compute')

        # 4. 发送创建请求
        response = self.session.post(
            f"{endpoint}/servers",
            json=request_body,
            headers={'Content-Type': 'application/json'}
        )

        # 5. 处理响应
        if response.status_code != 202:
            raise Exception(f"创建失败[HTTP {response.status_code}]: {response.text}")
        return response.json()['server']

