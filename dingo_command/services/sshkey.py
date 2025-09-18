import uuid
from datetime import datetime
from math import ceil
from kubernetes.client.exceptions import ApiException
from kubernetes import client
from dingo_command.db.models.sshkey.sql import KeySQL
from dingo_command.db.models.sshkey.models import KeyInfo
from dingo_command.api.model.sshkey import CreateKeyObject
from dingo_command.utils.helm import util
from dingo_command.utils.helm.util import SshLOG as Log
from dingo_command.utils.k8s_client import get_k8s_core_client
from dingo_command.utils.constant import CONFIGMAP_PREFIX, CCI_NAMESPACE_PREFIX
from dingo_command.db.models.ai_instance.sql import AiInstanceSQL
from sshpubkeys import SSHKey


class KeyService:

    def list_keys(self, query_params, page, page_size, sort_keys, sort_dirs,):
        try:
            # 按照条件从数据库中查询数据
            count, data = KeySQL.list_keys(query_params, page, page_size, sort_keys, sort_dirs)
            res = {}
            # 页数相关信息
            if page and page_size:
                res['currentPage'] = page
                res['pageSize'] = page_size
                res['totalPages'] = ceil(count / int(page_size))
            res['total'] = count
            res['data'] = data
            return res
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def delete_key(self, key_id):
        # 根据key的id删除具体的key
        query_params = {}
        query_params['id'] = key_id
        data = self.list_keys(query_params, 1, -1, None, None)
        if data.get("total") > 0:
            key_info = data.get("data")[0]
            if key_info.status == util.key_status_delete:
                raise ValueError("key is deleting, please wait")
            if key_info.status == util.key_status_create:
                raise ValueError("key is creating, please wait")
            try:
                KeySQL.delete_key(key_info)
                # 执行删除的操作
                return {"success": True, "message": "delete key success"}
            except Exception as e:
                raise ValueError(f"delete key error: {str(e)}")
        else:
            raise ValueError("key not found")

    def create_key(self, create_key_object: CreateKeyObject):
        # 创建key
        name = create_key_object.name
        user_id = create_key_object.user_id
        user_name = create_key_object.user_name
        tenant_id = create_key_object.tenant_id
        key_content = create_key_object.key_content
        description = create_key_object.description or ""
        is_manager = create_key_object.is_manager or False
        if not user_id:
            raise ValueError("user_id not found")
        if not user_name:
            raise ValueError("user_name not found")
        if not tenant_id:
            raise ValueError("tenant_id not found")
        if not key_content:
            raise ValueError("key_content not found")
        if not name:
            raise ValueError("name not found")
        # 创建 SSHKey 对象，并启用严格模式以提高验证强度
        key = SSHKey(key_content, strict_mode=True)
        try:
            # 尝试解析和验证公钥
            key.parse()
        except Exception as e:
            raise ValueError(f"ssh key format error: {str(e)}")
        query_params = {}
        query_params['name'] = name
        query_params['user_id'] = user_id
        query_params['tenant_id'] = tenant_id
        data = self.list_keys(query_params, 1, -1, None, None)
        if data.get("total") > 0:
            raise ValueError("key name already exists")
        namespace = CCI_NAMESPACE_PREFIX + tenant_id
        configmap_name = CONFIGMAP_PREFIX + user_id
        key_info = KeyInfo(
            id=str(uuid.uuid4()),
            name=name,
            user_id=user_id,
            user_name=user_name,
            tenant_id=tenant_id,
            key_content=key_content,
            description=description,
            status=util.key_status_success,
            create_time=datetime.now(),
            namespace=namespace,
            configmap_name=configmap_name,
            is_manager=is_manager
        )
        try:
            KeySQL.create_key(key_info)
            return {"success": True, "message": "create key success"}
        except Exception as e:
            raise ValueError(f"create ssh-key error: {str(e)}")