# dingo-command的裸机的client
# self.region_name = region_name
import uuid
from datetime import datetime, timedelta
from oslo_utils import timeutils
from functools import wraps
import requests

from dingo_command.common import CONF

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
    _singleton_instance = None
    TOKEN_EXPIRY_THRESHOLD = timedelta(minutes=15)

    def __new__(cls):
        if not cls._singleton_instance or not cls._is_token_valid():
            cls._singleton_instance = super().__new__(cls)
            cls._singleton_instance._init_client()
            print("generate New Ironic instance client")
        return cls._singleton_instance

    def _init_client(self):
        self._session = requests.Session()
        self._current_token = None
        self._token_expiry = None
        self._service_catalog = []
        self._singleton_instance_uuid = uuid.uuid4()
        self._acquire_new_token()

    @classmethod
    def _is_token_valid(cls):
        if not cls._singleton_instance:
            return False

        instance = cls._singleton_instance
        if not instance._current_token:
            print(f"ironic client single instance id: {instance._singleton_instance_uuid}, token[{instance._current_token}]无效，token过期阈值：{cls.TOKEN_EXPIRY_THRESHOLD}")
            return False

        remaining_time = instance._token_expiry - timeutils.utcnow()
        if remaining_time < cls.TOKEN_EXPIRY_THRESHOLD:
            print(f"ironic client single instance id: {instance._singleton_instance_uuid}, token[{instance._current_token}]剩余时间：{remaining_time}, token过期阈值：{cls.TOKEN_EXPIRY_THRESHOLD}， 当前token是否有效：{remaining_time > cls.TOKEN_EXPIRY_THRESHOLD}")
        return remaining_time > cls.TOKEN_EXPIRY_THRESHOLD

    def _acquire_new_token(self):
        """获取认证Token和服务目录"""
        auth_request = {
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
        try:
            response = requests.post(
                f"{IRONIC_AUTH_URL}/v3/auth/tokens",
                json=auth_request,
                headers=headers
            )
            if response.status_code != 201:
                print(f"ironic[{IRONIC_AUTH_URL}] 获取token失败: {response.text}")
            else:
                self._current_token = response.headers['X-Subject-Token']
                token_data = response.json()['token']
                self._service_catalog = token_data['catalog']
                self._token_expiry = datetime.strptime(
                    token_data['expires_at'], '%Y-%m-%dT%H:%M:%S.%fZ'
                )

                self._session.headers.update({
                    'X-Auth-Token': self._current_token,
                    'X-OpenStack-Ironic-API-Version': 'latest'
                })
        except Exception as e:
            print(f"ironic[{IRONIC_AUTH_URL}] 获取token报错：{e}")

    def _require_valid_token(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if not self._is_token_valid():
                self._acquire_new_token()
            return func(self, *args, **kwargs)

        return wrapper

    def get_service_endpoint(self, service_type, interface='public', region='RegionOne'):
        """根据服务类型获取Endpoint"""
        for service in self._service_catalog:
            if service['type'] == service_type:
                for endpoint in service['endpoints']:
                    if endpoint['interface'] == interface and endpoint['region'] == region:
                        return endpoint['url']
        raise Exception(f"未找到服务: {service_type}")

    @_require_valid_token
    def ironic_list_nodes(self):
        """获取Ironic节点列表"""
        endpoint = self.get_service_endpoint('baremetal')
        response = self._session.get(f"{endpoint}/v1/nodes/detail")
        if response.status_code != 200:
            raise Exception(f"ironic请求失败: {response.text}")
        return response.json()['nodes']

    @_require_valid_token
    def ironic_node_info_by_id(self, node_id):
        """获取Ironic指定节点信息"""
        endpoint = self.get_service_endpoint('baremetal')
        response = self._session.get(f"{endpoint}/v1/nodes/{node_id}")
        if response.status_code != 200:
            raise Exception(f"ironic查询指定node[{node_id}]请求{endpoint}失败: {response.text}")
        print(response.json())
        return response.json()

    @_require_valid_token
    def keystone_get_user_by_id(self, user_id):
        """获取指定用户信息"""
        endpoint = self.get_service_endpoint('identity')
        response = self._session.get(f"{endpoint}/v3/users/"+user_id)
        if response.status_code != 200:
            raise Exception(f"user请求失败: {response.text}")
        return response.json()['user']

    @_require_valid_token
    def keystone_get_project_by_id(self, project_id):
        """获取指定项目信息"""
        endpoint = self.get_service_endpoint('identity')
        response = self._session.get(f"{endpoint}/v3/projects/"+project_id)
        if response.status_code != 200:
            raise Exception(f"project请求失败: {response.text}")
        return response.json()['project']