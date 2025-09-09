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
from dingo_command.utils.constant import CONFIGMAP_PREFIX, NAMESPACE_PREFIX
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
        # 把这个key从configmap中删除
        # 再把其他的key的内容更新到configmap中（将所有的这个用户的sshkey的内容都写入指定ns指定name的configmap里面）
        query_params = {}
        query_params['id'] = key_id
        data = self.list_keys(query_params, 1, -1, None, None)
        if data.get("total") > 0:
            key_info = data.get("data")[0]
            if key_info.status == util.key_status_delete:
                raise ValueError("key is deleting, please wait")
            if key_info.status == util.key_status_create:
                raise ValueError("key is creating, please wait")
            key_info.status = util.key_status_delete
            KeySQL.update_key(key_info)
            namespace = key_info.namespace
            configmap_name = key_info.configmap_name
            key_content = key_info.key_content
            k8s_configs = AiInstanceSQL.list_k8s_configs()
            if not k8s_configs:
                raise ValueError("k8s configs not found")
            for k8s_config in k8s_configs:
                k8s_id = k8s_config.k8s_id
                try:
                    core_k8s_client = get_k8s_core_client(k8s_id)
                    # 2. 获取现有的 ConfigMap
                    configmap = core_k8s_client.read_namespaced_config_map(name=configmap_name, namespace=namespace)
                    # 3. 获取当前的 authorized_keys 内容
                    current_keys = configmap.data.get("authorized_keys", "")
                    if not current_keys:
                        Log.info("No authorized_keys found in ConfigMap.")
                        continue
                    # 4. 将内容分割成单独的公钥行
                    key_lines = current_keys.split('\n')
                    # 5. 查找并移除指定的公钥（只移除第一个完全匹配的）
                    key_found = False
                    new_key_lines = []
                    for line in key_lines:
                        if not key_found and line.strip() == key_content.strip():
                            key_found = True
                            Log.info(f"Found and removing specified public key: {line.strip()}")
                        else:
                            new_key_lines.append(line)

                    # 检查是否实际找到了公钥
                    if not key_found:
                        Log.info("Specified public key not found in ConfigMap.")
                        continue
                    # 6. 将剩余的公钥重新组合成字符串
                    new_keys_content = '\n'.join(new_key_lines)
                    # 确保以换行符结尾（如果还有内容）
                    if new_keys_content and not new_keys_content.endswith('\n'):
                        new_keys_content += '\n'
                    # 7. 更新 ConfigMap 数据
                    configmap.data["authorized_keys"] = new_keys_content
                    # 8. 应用更新到集群
                    core_k8s_client.patch_namespaced_config_map(
                        name=configmap_name,
                        namespace=namespace,
                        body=configmap
                    )
                except ApiException as e:
                    if e.status == 404:
                        Log.error(f"ConfigMap '{configmap_name}' not found in namespace '{namespace}'.")
                        KeySQL.delete_key(key_info)
                        # 执行删除的操作
                        return {"success": True, "message": f"ConfigMap '{configmap_name}' not found in namespace"
                                                            f" '{namespace}'."}
                    else:
                        Log.error(f"Failed to access ConfigMap: {e}")
                        raise e
                except Exception as e:
                    Log.error(f"Unexpected error occurred: {e}")
                    raise e
            KeySQL.delete_key(key_info)
            Log.info(f"Successfully removed SSH public key from ConfigMap.")
            # 执行删除的操作
            return {"success": True, "message": "delete key success"}
        else:
            raise ValueError("key not found")

    def create_key(self, create_key_object: CreateKeyObject):
        # 创建key
        # 问题：kube_config文件从哪获取，从文博的数据库里获取？
        # 具体步骤：1、接收前端发来的请求，获取一些参数
        # 2、校验参数是否合法，哪些参数要校验，哪些参数不需要校验
        name = create_key_object.name
        user_id = create_key_object.user_id
        tenant_id = create_key_object.tenant_id
        key_content = create_key_object.key_content
        description = create_key_object.description or ""
        if not user_id:
            raise ValueError("user_id not found")
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
        # 从数据库表里面获取k8s_id信息，用来获取kubeconfig信息
        k8s_configs = AiInstanceSQL.list_k8s_configs()
        if not k8s_configs:
            raise ValueError("k8s configs not found")
        # 3、调用数据库接口，存入数据库中
        namespace = NAMESPACE_PREFIX + tenant_id
        configmap_name = CONFIGMAP_PREFIX + user_id
        key_info = KeyInfo(
            id=str(uuid.uuid4()),
            name=name,
            user_id=user_id,
            tenant_id=tenant_id,
            key_content=key_content,
            description=description,
            status=util.key_status_create,
            create_time=datetime.now(),
            namespace=namespace,
            configmap_name=configmap_name
        )
        KeySQL.create_key(key_info)
        for k8s_config in k8s_configs:
            k8s_id = k8s_config.k8s_id
            # 2、根据k8s_id获取k8s的client
            core_k8s_client = get_k8s_core_client(k8s_id)

            try:
                # 首先检查命名空间是否存在，如果不存在则创建
                try:
                    # 尝试获取命名空间
                    core_k8s_client.read_namespace(namespace)
                except ApiException as e:
                    if e.status == 404:
                        # 命名空间不存在，创建新的命名空间
                        Log.info(f"Namespace '{namespace}' not found. Creating new namespace.")

                        # 创建命名空间对象
                        namespace_metadata = client.V1ObjectMeta(name=namespace)
                        namespace_body = client.V1Namespace(metadata=namespace_metadata)

                        # 创建命名空间
                        core_k8s_client.create_namespace(body=namespace_body)
                        Log.info(f"Namespace '{namespace}' created successfully.")
                    else:
                        # 其他 API 错误
                        key_info.status = util.key_status_failed
                        key_info.status_msg = str(e)
                        KeySQL.update_key(key_info)
                        Log.error(f"Failed to access namespace: {e}")
                        raise e

                # 4、把这个key的内容添加到configmap中（将所有的这个用户的sshkey的内容都写入指定ns指定name的configmap里面）
                try:
                    configmap = core_k8s_client.read_namespaced_config_map(configmap_name, namespace)
                    current_keys = configmap.data.get("authorized_keys", "")
                    if current_keys and not current_keys.endswith("\n"):
                        current_keys += "\n"
                    current_keys += key_content + "\n"
                    configmap.data["authorized_keys"] = current_keys
                    core_k8s_client.patch_namespaced_config_map(
                        name=configmap_name,
                        namespace=namespace,
                        body=configmap
                    )
                except ApiException as e:
                    if e.status == 404:
                        # ConfigMap 不存在，创建新的
                        Log.info(f"ConfigMap '{configmap_name}' not found in namespace '{namespace}'. Creating new one.")

                        # 创建新的 ConfigMap 对象
                        new_configmap = client.V1ConfigMap(
                            api_version="v1",
                            kind="ConfigMap",
                            metadata=client.V1ObjectMeta(
                                name=configmap_name,
                                namespace=namespace
                            ),
                            data={
                                "authorized_keys": key_content + "\n"
                            }
                        )

                        # 创建 ConfigMap
                        core_k8s_client.create_namespaced_config_map(
                            namespace=namespace,
                            body=new_configmap
                        )
                        key_info.status = util.key_status_success
                        KeySQL.update_key(key_info)
                        Log.info(f"Successfully created new ConfigMap '{configmap_name}' with the SSH public key.")
                        continue
                    else:
                        # 其他 API 错误
                        key_info.status = util.key_status_failed
                        key_info.status_msg = str(e)
                        KeySQL.update_key(key_info)
                        Log.error(f"Failed to access ConfigMap: {e}")
                        raise e
                # 5、返回结果
                key_info.status = util.key_status_success
                KeySQL.update_key(key_info)
                Log.info(f"create key success, key info {key_info}")
            except Exception as e:
                key_info.status = util.key_status_failed
                key_info.status_msg = str(e)
                KeySQL.update_key(key_info)
                Log.error(f"Error in create_key: {str(e)}")
                raise e
        return {"success": True, "message": "create key success"}