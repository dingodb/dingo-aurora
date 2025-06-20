import json
import uuid
from datetime import datetime, timedelta
from oslo_utils import timeutils
from functools import wraps

import requests
from dingo_command.common import CONF


# 配置cloudkitty信息
CLOUDKITTY_AUTH_URL = CONF.cloudkitty.auth_url
CLOUDKITTY_AUTH_TYPE = CONF.cloudkitty.auth_type
CLOUDKITTY_PROJECT_NAME = CONF.cloudkitty.project_name
CLOUDKITTY_PROJECT_DOMAIN = CONF.cloudkitty.project_domain
CLOUDKITTY_USER_NAME = CONF.cloudkitty.user_name
CLOUDKITTY_USER_DOMAIN = CONF.cloudkitty.user_domain
CLOUDKITTY_PASSWORD = CONF.cloudkitty.password
CLOUDKITTY_REGION_NAME = CONF.cloudkitty.region_name

class CloudKittyClient:
    _singleton_instance = None
    TOKEN_EXPIRY_THRESHOLD = timedelta(minutes=15)

    def __new__(cls):
        if not cls._singleton_instance or not cls._is_token_valid():
            cls._singleton_instance = super().__new__(cls)
            cls._singleton_instance._init_client()
            print("generate New CloudKitty instance client")
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
            print(f"cloudkitty client single instance id: {instance._singleton_instance_uuid}, token[{instance._current_token}]无效，token过期阈值：{cls.TOKEN_EXPIRY_THRESHOLD}")
            return False

        remaining_time = instance._token_expiry - timeutils.utcnow()
        if remaining_time < cls.TOKEN_EXPIRY_THRESHOLD:
            print(f"cloudkitty client single instance id: {instance._singleton_instance_uuid}, token[{instance._current_token}]剩余时间：{remaining_time}, token过期阈值：{cls.TOKEN_EXPIRY_THRESHOLD}， 当前token是否有效：{remaining_time > cls.TOKEN_EXPIRY_THRESHOLD}")
        return remaining_time > cls.TOKEN_EXPIRY_THRESHOLD

    def _acquire_new_token(self):
        """获取认证Token和服务目录"""
        auth_request = {
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
            response = requests.post(f"{CLOUDKITTY_AUTH_URL}/v3/auth/tokens", data=json.dumps(auth_request), headers=headers)
            if response.status_code != 201:
                print(f"cloudkitty[{CLOUDKITTY_AUTH_URL}] 获取token失败: {response.text}")
            else:
                self._current_token = response.headers['X-Subject-Token']
                token_data = response.json()['token']
                self._service_catalog = token_data['catalog']
                self._token_expiry = datetime.strptime(
                    token_data['expires_at'], '%Y-%m-%dT%H:%M:%S.%fZ'
                )

                self._session.headers.update({
                    'X-Auth-Token': self._current_token,
                    'X-OpenStack-CloudKitty-API-Version': 'latest'
                })
        except Exception as e:
            print(f"cloudkitty[{CLOUDKITTY_AUTH_URL}] 获取token报错：{e}")


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
    def get_storage_dataframes(self, filters=None):
        endpoint = self.get_service_endpoint('rating')
        response = self._session.get(f"{endpoint}/v1/storage/dataframes", params=filters)
        if response.status_code != 200:
            raise Exception(f"cloudkitty[{endpoint}/v1/storage/dataframes]请求失败: {response.text}")
        print(f"{endpoint}/v1/storage/dataframes 返回数据大小: {len(response.json()['dataframes'])}")
        return response.json()['dataframes']

    # 添加cloudkitty服务编辑服务映射
    @_require_valid_token
    def modify_rating_module_config_hashmap_mappings(self, mapping_id, mapping):
        endpoint = self.get_service_endpoint('rating')
        headers = {'Content-Type': 'application/json'}
        response = self._session.put(f"{endpoint}/v1/rating/module_config/hashmap/mappings/{mapping_id}", data=mapping.json(), headers=headers)
        if response.status_code != 200:
            print(f"cloudkitty[{endpoint}/v1/rating/module_config/hashmap/mappings/{mapping_id}] status_code:{response.status_code}, 请求失败: {response.text}")
            raise Exception(f"{response.text}")
        return response.json()

    @_require_valid_token
    def modify_rating_module_config_hashmap_thresholdings(self, threshold_id, thresholding):
        endpoint = self.get_service_endpoint('rating')
        headers = {'Content-Type': 'application/json'}
        response = self._session.put(f"{endpoint}/v1/rating/module_config/hashmap/thresholds/{threshold_id}", data=thresholding.json(), headers=headers)
        if response.status_code != 200:
            print(f"cloudkitty[{endpoint}/v1/rating/module_config/hashmap/thresholds/{mapping_id}] status_code:{response.status_code}, 请求失败: {response.text}")
            raise Exception(f"{response.text}")
        return response.json()

    @_require_valid_token
    def edit_rating_module_modules(self, module_id, modules):
        endpoint = self.get_service_endpoint('rating')
        # 转换键名
        output_data = {k.replace('_', '-') if k == "hot_config" else k: v for k, v in modules}
        response = self._session.put(f"{endpoint}/v1/rating/modules/{module_id}", data=json.dumps(output_data), headers={'Content-Type': 'application/json'})
        if response.status_code != 200:
            print(f"cloudkitty[{endpoint}/v1/rating/modules/{module_id}] status_code:{response.status_code}, 请求失败: {response.text}")
            raise Exception(f"{response.text}")
        return response.json()
