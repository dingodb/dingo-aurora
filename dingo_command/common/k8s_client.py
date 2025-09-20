import os
from kubernetes import client, config, dynamic
from kubernetes.client.rest import ApiException
from typing import List, Dict, Any, Optional, Union
import logging
from dingo_command.common.k8s.resource import ResourceClientFactory

logger = logging.getLogger(__name__)

class K8sClient:
    """
    一个统一的 Kubernetes API 客户端，支持查询、创建内置资源和自定义资源。
    内部主要使用 dynamic_client 实现通用操作。
    """ 
    def __init__(self, kubeconfig_path: Optional[str] = None, kubeconfig_content: Optional[str] = None, netns: Optional[str] = None):
        """
        初始化 Kubernetes 客户端。

        Args:
            kubeconfig_path (str, optional): 指定 kubeconfig 文件的路径。
                                             如果为 None，则按以下顺序尝试加载：
                                             1. 默认 kubeconfig 文件路径 (~/.kube/config)
                                             2. 集群内配置 (In-cluster config)
        """
        self._load_kubernetes_config(kubeconfig_path, kubeconfig_content, netns)
        self._dynamic_client = dynamic.DynamicClient(client.ApiClient())
        self._core_v1_api = client.CoreV1Api()
        self._apps_v1_api = client.AppsV1Api()
        print("Kubernetes 客户端初始化成功。")

    def _load_kubernetes_config(self, kubeconfig_path: Optional[str], kubeconfig_content: Optional[str] = None, netns: Optional[str] = None):
        """内部方法：加载 Kubernetes 配置。"""
        try:
            if kubeconfig_path:
                config.load_kube_config(config_file=kubeconfig_path)
            elif kubeconfig_content:
                # 如果提供了 kubeconfig 内容，则从内容加载
                import yaml
                kubeconfig_dict = yaml.safe_load(kubeconfig_content)
                config.load_kube_config_from_dict(kubeconfig_dict)
            else:
                config.load_kube_config() # 尝试从默认路径加载
        except config.config_exception.ConfigException as e_kubeconfig:
            print(f"无法从 kubeconfig 文件加载配置: {e_kubeconfig}")
            try:
                config.load_incluster_config() # 尝试从集群内服务账户加载
                print("已成功从集群内配置加载。")
            except config.config_exception.ConfigException as e_incluster:
                raise ConnectionError(
                    f"无法加载 Kubernetes 配置。请检查 kubeconfig 或集群内配置。\n"
                    f"Kubeconfig 错误: {e_kubeconfig}\n"
                    f"集群内配置错误: {e_incluster}"
                ) from e_incluster
        except Exception as e:
            raise ConnectionError(f"加载 Kubernetes 配置时发生未知错误: {e}") from e

    def _filter_none_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """过滤掉字典中值为 None 的键值对，用于传递给 Kubernetes API 方法。"""
        return {k: v for k, v in params.items() if v is not None}

    def _get_k8s_server_version(self) -> str:
        """获取 Kubernetes 集群的版本信息。"""
        try:
            version_api = client.VersionApi()
            version_info = version_api.get_code()
            # 返回主版本号，如 "1.25", "1.26" 等
            return f"{version_info.major}.{version_info.minor}"
        except Exception as e:
            print(f"获取 Kubernetes 版本信息失败: {e}")
            # 默认假设为较新版本
            return "1.25"

    def _infer_kind_from_resource_type(self, resource_type: str) -> str:
        """
        根据资源类型（复数形式）推断对应的 Kind（单数形式）。
        
        Args:
            resource_type (str): 资源类型的复数形式，如 "pods", "deployments" 等
            
        Returns:
            str: 推断出的 Kind
        """
        # 常见的复数到单数的映射
        resource_kind_mapping = {
            # Core API resources
            'pods': 'Pod',
            'services': 'Service',
            'configmaps': 'ConfigMap',
            'secrets': 'Secret',
            'serviceaccounts': 'ServiceAccount',
            'events': 'Event',
            'nodes': 'Node',
            'persistentvolumes': 'PersistentVolume',
            'persistentvolumeclaims': 'PersistentVolumeClaim',
            'namespaces': 'Namespace',
            'endpoints': 'Endpoints',
            'limitranges': 'LimitRange',
            'resourcequotas': 'ResourceQuota',
            'replicationcontrollers': 'ReplicationController',
            'bindings': 'Binding',
            'componentstatuses': 'ComponentStatus',
            
            # Apps API resources
            'deployments': 'Deployment',
            'replicasets': 'ReplicaSet',
            'daemonsets': 'DaemonSet',
            'statefulsets': 'StatefulSet',
            
            # Networking API resources
            'ingresses': 'Ingress',
            'networkpolicies': 'NetworkPolicy',
            'ingressclasses': 'IngressClass',
            
            # RBAC API resources
            'roles': 'Role',
            'rolebindings': 'RoleBinding',
            'clusterroles': 'ClusterRole',
            'clusterrolebindings': 'ClusterRoleBinding',
            
            # Batch API resources
            'jobs': 'Job',
            'cronjobs': 'CronJob',
            
            # Autoscaling API resources
            'horizontalpodautoscalers': 'HorizontalPodAutoscaler',
            
            # Policy API resources
            'poddisruptionbudgets': 'PodDisruptionBudget',
            'podsecuritypolicies': 'PodSecurityPolicy',
            
            # Storage API resources
            'storageclasses': 'StorageClass',
            'volumeattachments': 'VolumeAttachment',
            'csinodes': 'CSINode',
            'csidrivers': 'CSIDriver',
            'csistoragecapacities': 'CSIStorageCapacity',
            
            # Node API resources
            'runtimeclasses': 'RuntimeClass',
            
            # API extensions resources
            'customresourcedefinitions': 'CustomResourceDefinition',
            
            # Admission registration resources
            'mutatingwebhookconfigurations': 'MutatingWebhookConfiguration',
            'validatingwebhookconfigurations': 'ValidatingWebhookConfiguration',
            
            # Certificates API resources
            'certificatesigningrequests': 'CertificateSigningRequest',
            
            # Coordination API resources
            'leases': 'Lease',
            
            # Discovery API resources
            'endpointslices': 'EndpointSlice',
        }
        
        # 先查找直接映射
        if resource_type.lower() in resource_kind_mapping:
            return resource_kind_mapping[resource_type.lower()]
        
        # 如果没有直接映射，尝试通过 dynamic client 发现
        try:
            for api_resource in self._dynamic_client.resources.search(name=resource_type):
                return api_resource.kind
        except Exception:
            pass
        
        # 如果还是找不到，使用简单的规则转换
        # 去掉末尾的 's'，然后首字母大写
        if resource_type.endswith('s') and len(resource_type) > 1:
            kind = resource_type[:-1].capitalize()
            # 处理一些特殊情况
            if kind.endswith('ie'):
                kind = kind[:-2] + 'y'  # policies -> policy -> Policy
            elif kind.endswith('sse'):
                kind = kind[:-1]  # classes -> classe -> class -> Class
            return kind
        else:
            # 如果没有找到合适的映射，返回原始资源类型的大写形式
            return resource_type.capitalize()
        
    def _infer_api_version(self, resource_type: str) -> str:
        """
        根据资源类型和 Kubernetes 版本推断 API 版本。
        
        Args:
            resource_type (str): 资源类型的复数形式，如 "pods", "deployments" 等
            
        Returns:
            str: 推断出的 API 版本
        """
        # 获取集群版本
        k8s_version = self._get_k8s_server_version()
        major, minor = map(int, k8s_version.split('.'))
        
        # 核心 API 组 (v1)
        core_v1_resources = [
            'pods', 'services', 'configmaps', 'secrets', 'serviceaccounts', 
            'events', 'nodes', 'persistentvolumes', 'persistentvolumeclaims',
            'namespaces', 'endpoints', 'limitranges', 'resourcequotas',
            'replicationcontrollers', 'bindings', 'componentstatuses'
        ]
        
        # apps API 组
        apps_v1_resources = [
            'deployments', 'replicasets', 'daemonsets', 'statefulsets'
        ]
        
        # networking API 组
        networking_resources = {
            'ingresses': 'networking.k8s.io/v1' if (major > 1 or (major == 1 and minor >= 19)) else 'extensions/v1beta1',
            'networkpolicies': 'networking.k8s.io/v1',
            'ingressclasses': 'networking.k8s.io/v1'
        }
        
        # apiextensions API 组
        apiextensions_resources = {
            'customresourcedefinitions': 'apiextensions.k8s.io/v1' if (major > 1 or (major == 1 and minor >= 16)) else 'apiextensions.k8s.io/v1beta1'
        }
        
        # rbac API 组
        rbac_resources = [
            'roles', 'rolebindings', 'clusterroles', 'clusterrolebindings'
        ]
        
        # batch API 组
        batch_resources = {
            'jobs': 'batch/v1',
            'cronjobs': 'batch/v1' if (major > 1 or (major == 1 and minor >= 21)) else 'batch/v1beta1'
        }
        
        # autoscaling API 组
        autoscaling_resources = {
            'horizontalpodautoscalers': 'autoscaling/v2' if (major > 1 or (major == 1 and minor >= 23)) else 'autoscaling/v1'
        }
        
        # policy API 组
        policy_resources = {
            'poddisruptionbudgets': 'policy/v1' if (major > 1 or (major == 1 and minor >= 21)) else 'policy/v1beta1',
            'podsecuritypolicies': 'policy/v1beta1'  # 在 k8s 1.25+ 中已移除
        }
        
        # storage API 组
        storage_resources = [
            'storageclasses', 'volumeattachments', 'csinodes', 'csidrivers', 'csistoragecapacities'
        ]
        
        # node API 组
        node_resources = [
            'runtimeclasses'
        ]
        
        # metrics API 组
        metrics_resources = [
            'nodes', 'pods'  # 这些在 metrics.k8s.io 中也存在
        ]
        
        # 判断资源类型并返回相应的 API 版本
        if resource_type in core_v1_resources:
            return "v1"
        elif resource_type in apps_v1_resources:
            return "apps/v1"
        elif resource_type in networking_resources:
            return networking_resources[resource_type]
        elif resource_type in apiextensions_resources:
            return apiextensions_resources[resource_type]
        elif resource_type in rbac_resources:
            return "rbac.authorization.k8s.io/v1"
        elif resource_type in batch_resources:
            return batch_resources[resource_type]
        elif resource_type in autoscaling_resources:
            return autoscaling_resources[resource_type]
        elif resource_type in policy_resources:
            return policy_resources[resource_type]
        elif resource_type in storage_resources:
            return "storage.k8s.io/v1"
        elif resource_type in node_resources:
            return "node.k8s.io/v1"
        # 特殊情况：admission API 组
        elif resource_type in ['mutatingwebhookconfigurations', 'validatingwebhookconfigurations']:
            return "admissionregistration.k8s.io/v1"
        # 特殊情况：certificates API 组
        elif resource_type in ['certificatesigningrequests']:
            return "certificates.k8s.io/v1"
        # 特殊情况：coordination API 组
        elif resource_type in ['leases']:
            return "coordination.k8s.io/v1"
        # 特殊情况：discovery API 组
        elif resource_type in ['endpointslices']:
            return "discovery.k8s.io/v1"
        # 特殊情况：metrics API 组
        elif resource_type.startswith('metrics.k8s.io/'):
            return "metrics.k8s.io/v1beta1"
        else:
            # 对于未知的资源类型，尝试使用 dynamic client 的发现功能
            try:
                # 尝试通过 API 发现找到资源
                for api_resource in self._dynamic_client.resources.search(kind=self._infer_kind_from_resource_type(resource_type)):
                    return api_resource.group_version
                # 如果没有找到，抛出错误
                raise ValueError(f"无法推断资源 '{resource_type}' 的 API 版本，请明确提供 'api_version' 参数。")
            except Exception:
                raise ValueError(f"无法推断资源 '{resource_type}' 的 API 版本，请明确提供 'api_version' 参数。")

    def _sort_resources(self, items: List[Dict[str, Any]], sort_by: str, sort_order: str) -> List[Dict[str, Any]]:
        """
        对资源列表进行排序。

        Args:
            items (List[Dict[str, Any]]): 资源对象列表
            sort_by (str): 排序字段，支持嵌套字段如 "metadata.name"
            sort_order (str): 排序顺序，"asc" 或 "desc"

        Returns:
            List[Dict[str, Any]]: 排序后的资源列表
        """
        def get_nested_value(obj: Dict[str, Any], path: str):
            """获取嵌套字段的值"""
            try:
                keys = path.split('.')
                value = obj
                for key in keys:
                    if key == "create_time":
                        key = "creationTimestamp"
                    if key in ("status", "creationTimestamp", "labels", "name"):
                        if isinstance(value, dict):
                            if key == "status":
                                value = value.get("status").get("phase")
                                continue
                            value = value.get("metadata").get(key)
                    elif isinstance(value, dict):
                        value = value.get(key)
                    else:
                        return None
                return value
            except (KeyError, TypeError, AttributeError):
                return None

        def sort_key(item: Dict[str, Any]):
            """排序键函数"""
            value = get_nested_value(item, sort_by)
            # 处理不同类型的值
            if value is None:
                return ""
            elif isinstance(value, str):
                return value.lower()  # 字符串不区分大小写排序
            elif isinstance(value, (int, float)):
                return value
            elif isinstance(value, dict) and 'seconds' in value:
                # 处理时间戳对象 (如 creationTimestamp)
                return value.get('seconds', 0)
            else:
                return str(value).lower()

        try:
            reverse = sort_order.lower() == 'descend'
            return sorted(items, key=sort_key, reverse=reverse)
        except Exception as e:
            print(f"排序时发生错误: {e}")
            return items

    def _get_nested_field_value(self, obj: Dict[str, Any], field_path: str) -> Any:
        """
        获取嵌套字段的值，支持数组索引。

        Args:
            obj (Dict[str, Any]): 对象
            field_path (str): 字段路径，如 "metadata.name" 或 "spec.containers[0].image"

        Returns:
            Any: 字段值，如果不存在则返回 None
        """
        try:
            parts = field_path.split('.')
            current = obj.to_dict() if hasattr(obj, 'to_dict') else obj

            for part in parts:
                if '[' in part and ']' in part:
                    # 处理数组索引，如 containers[0]
                    field_name = part.split('[')[0]
                    index_str = part.split('[')[1].rstrip(']')
                    
                    if field_name:
                        current = current.get(field_name)
                    
                    if current and isinstance(current, list):
                        try:
                            index = int(index_str)
                            current = current[index] if 0 <= index < len(current) else None
                        except (ValueError, IndexError):
                            return None
                else:
                    if isinstance(current, dict):
                        current = current.get(part)
                    else:
                        return None

            return current
        except (KeyError, TypeError, AttributeError):
            return None

    def _get_resource(
        self,
        resource_type: str,
        api_version: Optional[str] = None,
        namespace: Optional[str] = None,
        label_selector: Optional[str] = None,
        field_selector: Optional[str] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        通用方法，用于查询 Kubernetes 资源（简化版本，保持向后兼容）。

        Args:
            resource_type (str): 资源类型的复数形式，如 "pods", "deployments" 等
            api_version (str, optional): API 版本，如果不提供则自动推断
            namespace (str, optional): 命名空间，如果不提供则查询所有命名空间
            label_selector (str, optional): 标签选择器，如 "app=nginx"
            field_selector (str, optional): 字段选择器，如 "status.phase=Running"

        Returns:
            Optional[List[Dict[str, Any]]]: 资源对象列表，如果查询失败则返回 None
        """
        try:
            if not api_version:
                api_version = self._infer_api_version(resource_type)

            resource_client = self._dynamic_client.resources.get(api_version=api_version, kind=self._infer_kind_from_resource_type(resource_type))

            # 构建查询参数
            params = {
                'label_selector': label_selector,
                'field_selector': field_selector
            }

            # 执行查询
            if namespace:
                resource_list = resource_client.get(namespace=namespace, **self._filter_none_params(params))
            else:
                resource_list = resource_client.get(**self._filter_none_params(params))

            # 获取资源列表
            items = resource_list.items if hasattr(resource_list, 'items') else []
            
            # 转换为字典格式
            items_dict = [item.to_dict() if hasattr(item, 'to_dict') else item for item in items]

            return items_dict

        except ApiException as e:
            print(f"查询 Kubernetes 资源 '{resource_type}' (API Version: {api_version}) 时发生 API 错误: {e}")
            return None
        except ValueError as e:
            print(f"参数错误: {e}")
            return None
        except Exception as e:
            print(f"查询 Kubernetes 资源 '{resource_type}' (API Version: {api_version}) 时发生未知错误: {e}")
            return None
        
    def get_resource(
        self,
        resource_type: str,
        name: str,
        api_version: Optional[str] = None,
        namespace: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        通过名称获取单个 Kubernetes 资源的详情。

        Args:
            resource_type (str): 资源类型的复数形式，如 "pods", "deployments" 等
            name (str): 资源名称
            api_version (str, optional): API 版本，如果不提供则自动推断
            namespace (str, optional): 命名空间，对于命名空间级别的资源必须提供

        Returns:
            Optional[Dict[str, Any]]: 资源对象详情，如果获取失败则返回 None
        """
        try:
            if not api_version:
                api_version = self._infer_api_version(resource_type)

            resource_client = self._dynamic_client.resources.get(api_version=api_version, kind=self._infer_kind_from_resource_type(resource_type))

            # 检查资源是否为命名空间级别
            if resource_client.namespaced and not namespace:
                raise ValueError(f"资源 '{resource_type}' 是命名空间级别的，必须提供命名空间参数")

            # 执行查询 - 获取单个资源
            if resource_client.namespaced:
                resource_obj = resource_client.get(name=name, namespace=namespace)
            else:
                resource_obj = resource_client.get(name=name)

            # 转换为字典格式
            if hasattr(resource_obj, 'to_dict'):
                return resource_obj.to_dict()
            else:
                return dict(resource_obj)

        except ApiException as e:
            if e.status == 404:
                print(f"资源 '{resource_type}/{name}' 在命名空间 '{namespace}' 中不存在")
            else:
                print(f"查询 Kubernetes 资源 '{resource_type}/{name}' (API Version: {api_version}) 时发生 API 错误: {e.status} - {e.reason}")
            return None
        except ValueError as e:
            print(f"参数错误: {e}")
            return None
        except Exception as e:
            print(f"查询 Kubernetes 资源 '{resource_type}/{name}' (API Version: {api_version}) 时发生未知错误: {e}")
            return None
        
    def _filter_by_key_value(self, items: List[Dict[str, Any]], key: str, value: str) -> List[Dict[str, Any]]:
        """
        根据键值对过滤资源列表。
        
        Args:
            items: 资源列表
            key: 搜索键，如 "name", "status", "label.app" 等
            value: 搜索值
            
        Returns:
            过滤后的资源列表
        """
        filtered_items = []
        
        for item in items:
            match_found = False
            
            if key.lower().startswith('name'):
                # name 相关的搜索使用默认匹配
                name_value = self._get_nested_field_value(item, 'metadata.name')
                if name_value and value.lower() in str(name_value).lower():
                    match_found = True
            elif key.lower().startswith('label.'):
                # 标签搜索，如 label.app=nginx
                label_key = key[6:]  # 去掉 "label." 前缀
                labels = self._get_nested_field_value(item, 'metadata.labels')
                if labels and isinstance(labels, dict):
                    label_value = labels.get(label_key)
                    if label_value and str(label_value).lower() == value.lower():
                        match_found = True
            elif key.lower() == 'status':
                # 状态搜索，根据资源类型处理
                status_value = self._get_resource_status(item)
                if status_value and value.lower() in str(status_value).lower():
                    match_found = True
            elif key.lower() == 'phase':
                # Pod 阶段搜索
                phase_value = self._get_nested_field_value(item, 'status.phase')
                if phase_value and str(phase_value).lower() == value.lower():
                    match_found = True
            elif key.lower() == 'ready':
                # 就绪状态搜索
                ready_status = self._get_resource_ready_status(item)
                if ready_status is not None and str(ready_status).lower() == value.lower():
                    match_found = True
            elif key.lower() == 'image':
                # 镜像搜索（适用于 Pod、Deployment 等）
                if self._resource_contains_image(item, value):
                    match_found = True
            else:
                # 通用字段搜索
                field_value = self._get_nested_field_value(item, key)
                if field_value and value.lower() in str(field_value).lower():
                    match_found = True
            
            if match_found:
                filtered_items.append(item)
        
        return filtered_items

    def _paginate_items(self, items: List[Dict[str, Any]], page: int, page_size: int) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        对资源列表进行分页处理。
        
        Args:
            items: 资源列表
            page: 页码，从1开始
            page_size: 每页大小
            
        Returns:
            tuple: (分页后的资源列表, 分页元数据)
        """
        # 确保 page 和 page_size 为整数
        page = int(page)
        page_size = int(page_size)

        total_count = len(items)
        total_pages = (total_count + page_size - 1) // page_size if page_size > 0 else 1
        
        # 确保页码有效
        if page < 1:
            page = 1
        elif page > total_pages and total_pages > 0:
            page = total_pages
        
        # 计算起始和结束索引
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        
        # 获取当前页的数据
        paginated_items = items[start_index:end_index]
        
        # 构建分页元数据
        pagination_metadata = {
            'current_page': page,
            'page_size': page_size,
            'total_count': total_count,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None,
            'start_index': start_index + 1 if paginated_items else 0,
            'end_index': start_index + len(paginated_items)
        }
        
        return paginated_items, pagination_metadata

    def _convert_k8s_object_to_dict(self, obj: Any) -> Dict[str, Any]:
        """
        将 K8s 对象安全地转换为字典格式，确保包含 apiVersion 和 kind。
        
        Args:
            obj: K8s 对象
            resource_type: 资源类型
            api_version: API 版本
            
        Returns:
            字典格式的对象，确保包含 apiVersion 和 kind
        """
        # 首先尝试转换为字典
        if hasattr(obj, 'to_dict'):
            try:
                result = obj.to_dict()
            except Exception as e:
                print(f"使用 to_dict() 转换失败: {e}")
                result = dict(obj) if hasattr(obj, '__dict__') else {}
        elif isinstance(obj, dict):
            result = dict(obj)
        elif hasattr(obj, '__dict__'):
            result = dict(obj.__dict__)
        else:
            result = {'value': str(obj)}
        
        # 确保包含 apiVersion
        if 'apiVersion' not in result or not result.get('apiVersion'):
            result['apiVersion'] = obj.get('apiVersion', 'v1')  # 默认值为 v1
        if 'kind' not in result or not result.get('kind'):
            result['kind'] = obj.get('kind', 'Pod')  # 默认值为 Pod
        return result

    def list_resource(
            self,
            resource_type: str,
            api_version: Optional[str] = None,
            namespace: Optional[str] = None,
            label_selector: Optional[str] = None,
            field_selector: Optional[str] = None,
            limit: Optional[int] = None,
            page: int = 1,
            page_size: int = 10,
            continue_token: Optional[str] = None,
            sort_by: Optional[str] = None,
            sort_order: str = "asc",
            search_terms: Optional[List[str]] = None,
        ) -> Dict[str, Any]:
        #根据资源类型组织不同的filter
        
        try:
            if not api_version:
                api_version = self._infer_api_version(resource_type)

                resource_client = self._dynamic_client.resources.get(api_version=api_version, kind=self._infer_kind_from_resource_type(resource_type))

                # 构建查询参数
                params = {
                    'label_selector': label_selector,
                    'field_selector': field_selector,
                    'limit': limit,
                    '_continue': continue_token
                }

                # 执行查询
                if namespace:
                    resource_list = resource_client.get(namespace=namespace, **self._filter_none_params(params))
                else:
                    resource_list = resource_client.get(**self._filter_none_params(params))

            # 获取资源列表
            items = resource_list.items if hasattr(resource_list, 'items') else []

            # 转换为字典格式
            items_dict = []
            for item in items:
                items_dict.append(self._convert_k8s_object_to_dict(item))
            # 创建资源工厂
            factory = ResourceClientFactory(self)
            items_dict = factory.list(items_dict, resource_type = resource_type, namespace=namespace, label_selector=label_selector, field_selector=field_selector, filters=search_terms)
           # 应用多个自定义过滤器
            if search_terms:
                tmp_items_dict = []
                for term in search_terms:
                    if '=' in term:
                        key, value = term.split('=', 1)
                        if key == "name":
                            for item in items_dict:
                                if value.lower() in item.get('metadata', {}).get('name', '').lower():
                                    tmp_items_dict.append(item)
                            items_dict = tmp_items_dict

            # 应用排序
            if sort_by:
                items_dict = self._sort_resources(items_dict, sort_by, sort_order)
            # 应用客户端分页
            paginated_items, pagination_metadata = self._paginate_items(items_dict, page, page_size)

            # 构建K8s原生元数据
            k8s_metadata = {
                'continue': getattr(resource_list.metadata, 'continue', None) if hasattr(resource_list, 'metadata') else None,
                'remainingItemCount': getattr(resource_list.metadata, 'remainingItemCount', None) if hasattr(resource_list, 'metadata') else None,
                'resourceVersion': getattr(resource_list.metadata, 'resourceVersion', None) if hasattr(resource_list, 'metadata') else None
            }
            # 构建完整响应
            result = {
                'items': paginated_items,
                'pagination': pagination_metadata,
                'k8s_metadata': k8s_metadata,
                'total_count_before_pagination': len(items_dict),  # 过滤和排序后但分页前的总数
                'total_count_from_server': len(items)  # 从服务器获取的原始总数
            }

            return result

        except ApiException as e:
            print(f"查询 Kubernetes 资源 '{resource_type}' (API Version: {api_version}) 时发生 API 错误: {e}")
            return {
                'items': [],
                'metadata': {'error': str(e)},
                'total_count': 0
            }
        except ValueError as e:
            print(f"参数错误: {e}")
            return {
                'items': [],
                'metadata': {'error': str(e)},
                'total_count': 0
            }
        except Exception as e:
            print(f"查询 Kubernetes 资源 '{resource_type}' (API Version: {api_version}) 时发生未知错误: {e}")
            return {
                'items': [],
                'metadata': {'error': str(e)},
                    'total_count': 0
                }

    def create_resource(
        self,
        resource_body: Dict[str, Any],
        resource_type: str, # 这是资源的 plural 名称
        api_version: Optional[str] = None, # 优先使用 body 中的 apiVersion，其次用此参数
        namespace: Optional[str] = None # 优先使用 body 中的 metadata.namespace，其次用此参数
    ) -> Optional[Dict[str, Any]]:
        """
        通用方法，用于创建 Kubernetes 资源。

        Args:
            resource_body (Dict[str, Any]): 要创建的资源的完整 JSON/字典表示。
                                             必须包含 'apiVersion', 'kind', 'metadata' 等。
            resource_type (str): 资源的复数形式名称 (plural name)，例如 "pods", "deployments"。
                                 用于 dynamic_client 获取资源客户端。
            api_version (str, optional): 资源的 API 版本，例如 "v1", "apps/v1"。
                                         如果 resource_body 中没有 'apiVersion'，则使用此参数。
            namespace (str, optional): 资源的命名空间。如果 resource_body 中没有 metadata.namespace，则使用此参数。
                                      如果资源是集群级别的 (cluster-scoped)，则忽略此参数。

        Returns:
            Optional[Dict[str, Any]]: 成功创建的资源对象 (字典形式)，如果创建失败则为 None。
        """
        # 确定 apiVersion 和 kind (resource_type)
        resolved_api_version = resource_body.get('apiVersion') or api_version
        
        # 如果仍然没有 API 版本，尝试推断
        if not resolved_api_version:
            try:
                resolved_api_version = self._infer_api_version(resource_type)
            except ValueError:
                raise ValueError("创建资源时必须提供 'apiVersion'，请确保其在请求体中或作为参数提供，或者确保 resource_type 是可识别的标准资源类型。")
        
        resolved_kind = resource_body.get('kind', '').lower()
        try:
            # 获取 dynamic client resource
            # 获取 resource 对象
            resource = self._dynamic_client.resources.get(api_version=resolved_api_version, kind=self._infer_kind_from_resource_type(resource_type))
        
            #resource_client = self._dynamic_client.resources.get(api_version=resolved_api_version, kind=resource_type)
            res = self._dynamic_client.create(resource, body = resource_body, namespace=namespace)
            # 确定命名空间
            # resolved_namespace = resource_body.get('metadata', {}).get('namespace') or namespace

            # # 检查资源是否为命名空间级别
            # # 这是一个简化的判断，更准确的判断需要查询 API Resource List
            # # 但对于常见的资源，我们可以根据其 type 来大致判断
            # is_namespaced = resource_client.namespaced

            # if is_namespaced and not resolved_namespace:
            #     raise ValueError(f"资源 '{resource_type}' 是命名空间级别的，但未提供命名空间。")

            # if is_namespaced:
            #     created_resource = resource_client.create(body=resource_body, namespace=resolved_namespace)
            # else:
            #     created_resource = resource_client.create(body=resource_body)

            return res.to_dict() # dynamic_client 返回的对象可以转为 dict
        except ApiException as e:
            print(f"创建 Kubernetes 资源 '{resource_type}' (API Version: {resolved_api_version}) 时发生 API 错误: {e.status} - {e.reason}")
            # 尝试解析更多错误详情
            try:
                error_detail = e.body.decode('utf-8') if isinstance(e.body, bytes) else e.body
                print(f"错误详情: {error_detail}")
            except Exception:
                pass
            raise e # 重新抛出 ApiException，让 FastAPI 捕获并转换为 HTTPException
        except ValueError as e:
            print(f"参数错误: {e}")
            raise e
        except Exception as e:
            print(f"创建 Kubernetes 资源 '{resource_type}' 时发生未知错误: {e}")
            raise e

    def get_supported_api_versions(self) -> Dict[str, List[str]]:
        """
        获取集群支持的所有 API 版本和资源类型。
        
        Returns:
            Dict[str, List[str]]: 字典，键为 API 版本，值为该版本支持的资源类型列表
        """
        try:
            api_versions = {}
            
            # 获取所有 API 资源
            for api_resource in self._dynamic_client.resources:
                group_version = api_resource.group_version
                resource_name = api_resource.name
                
                if group_version not in api_versions:
                    api_versions[group_version] = []
                api_versions[group_version].append(resource_name)
            
            return api_versions
        except Exception as e:
            print(f"获取支持的 API 版本时发生错误: {e}")
            return {}

    def find_resource_api_version(self, resource_type: str) -> Optional[str]:
        """
        通过搜索集群 API 来查找资源的正确 API 版本。
        
        Args:
            resource_type (str): 资源类型
            
        Returns:
            Optional[str]: 找到的 API 版本，如果没找到则返回 None
        """
        try:
            # 搜索匹配的资源
            for api_resource in self._dynamic_client.resources.search(kind=self._infer_kind_from_resource_type(resource_type)):
                return api_resource.group_version
            return None
        except Exception as e:
            print(f"搜索资源 '{resource_type}' 的 API 版本时发生错误: {e}")
            return None

    def validate_resource_and_api_version(self, resource_type: str, api_version: str) -> bool:
        """
        验证指定的资源类型和 API 版本组合是否在集群中可用。
        
        Args:
            resource_type (str): 资源类型
            api_version (str): API 版本
            
        Returns:
            bool: 如果组合有效则返回 True，否则返回 False
        """
        try:
            # 尝试获取资源客户端
            self._dynamic_client.resources.get(api_version=api_version, kind=self._infer_kind_from_resource_type(resource_type))
            return True
        except Exception:
            return False

    def get_resource_info(self, resource_type: str, api_version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        获取资源的详细信息，包括是否为命名空间级别、支持的操作等。
        
        Args:
            resource_type (str): 资源类型
            api_version (str, optional): API 版本，如果不提供则尝试推断
            
        Returns:
            Optional[Dict[str, Any]]: 资源信息字典，如果获取失败则返回 None
        """
        try:
            if not api_version:
                api_version = self._infer_api_version(resource_type)
            
            resource_client = self._dynamic_client.resources.get(api_version=api_version, kind=self._infer_kind_from_resource_type(resource_type))
            
            return {
                "name": resource_client.name,
                "singularName": resource_client.singular_name,
                "kind": resource_client.kind,
                "apiVersion": resource_client.group_version,
                "namespaced": resource_client.namespaced,
                "verbs": getattr(resource_client, 'verbs', []),
                "shortNames": getattr(resource_client, 'short_names', []),
                "categories": getattr(resource_client, 'categories', [])
            }
        except Exception as e:
            print(f"获取资源 '{resource_type}' 信息时发生错误: {e}")
            return None
        
    def delete_resource(
        self,
        resource_type: str,
        name: Optional[str] = None,
        api_version: Optional[str] = None,
        namespace: Optional[str] = None,
        propagation_policy: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        通用方法，用于删除 Kubernetes 资源。支持删除单个资源或批量删除。

        Args:
            resource_type (str): 资源的复数形式名称，例如 "pods", "deployments"
            name (str, optional): 资源名称。如果提供，则删除指定的单个资源；
                                如果不提供，则根据选择器批量删除
            api_version (str, optional): 资源的 API 版本，例如 "v1", "apps/v1"。
                                        如果不提供则自动推断
            namespace (str, optional): 资源的命名空间。对于命名空间级别的资源必须提供
            propagation_policy (str, optional): 删除传播策略，可选值：
                                            - "Orphan": 孤立子资源
                                            - "Background": 后台删除子资源
                                            - "Foreground": 前台删除子资源
            dry_run (bool): 是否为试运行模式，默认 False

        Returns:
            Dict[str, Any]: 删除操作的结果，包含删除的资源列表和状态信息
        """
        try:
            if not api_version:
                api_version = self._infer_api_version(resource_type)

            resource_client = self._dynamic_client.resources.get(api_version=api_version, kind=self._infer_kind_from_resource_type(resource_type))

            # 检查资源是否为命名空间级别
            if resource_client.namespaced and not namespace:
                raise ValueError(f"资源 '{resource_type}' 是命名空间级别的，必须提供命名空间参数")

            # 构建删除选项
            delete_options = {}
            if propagation_policy:
                delete_options['propagation_policy'] = propagation_policy
            if dry_run:
                delete_options['dry_run'] = ['All']

            deleted_resources = []
            
            if name:
                # 删除单个资源
                try:
                    if resource_client.namespaced:
                        result = resource_client.delete(
                            name=name,
                            namespace=namespace,
                            **delete_options
                        )
                    else:
                        result = resource_client.delete(
                            name=name,
                            **delete_options
                        )
                    
                    deleted_resources.append({
                        'name': name,
                        'namespace': namespace if resource_client.namespaced else None,
                        'status': 'deleted',
                        'result': result.to_dict() if hasattr(result, 'to_dict') else str(result)
                    })
                    
                except ApiException as e:
                    if e.status == 404:
                        return {
                            'success': False,
                            'error': f"资源 '{resource_type}/{name}' 在命名空间 '{namespace}' 中不存在",
                            'deleted_resources': [],
                            'failed_resources': [{
                                'name': name,
                                'namespace': namespace if resource_client.namespaced else None,
                                'error': 'NotFound'
                            }]
                        }
                    else:
                        raise e
            else:
                # 如果没有提供 name，则返回错误，因为批量删除需要其他参数
                raise ValueError("删除资源时必须提供 name 参数")

            # 构建响应
            success = len(deleted_resources) > 0
            result = {
                'success': success,
                'deleted_count': len(deleted_resources),
                'deleted_resources': deleted_resources,
                'operation': 'dry_run' if dry_run else 'delete'
            }

            return result

        except ApiException as e:
            print(f"删除 Kubernetes 资源 '{resource_type}' (API Version: {api_version}) 时发生 API 错误: {e}")
            return {
                'success': False,
                'error': f"API 错误: {e.status} - {e.reason}",
                'deleted_resources': []
            }
        except ValueError as e:
            print(f"参数错误: {e}")
            return {
                'success': False,
                'error': f"参数错误: {str(e)}",
                'deleted_resources': []
            }
        except Exception as e:
            print(f"删除 Kubernetes 资源 '{resource_type}' (API Version: {api_version}) 时发生未知错误: {e}")
            return {
                'success': False,
                'error': f"未知错误: {str(e)}",
                'deleted_resources': []
            }

    def delete_resource_by_name(
        self,
        resource_type: str,
        name: str,
        api_version: Optional[str] = None,
        namespace: Optional[str] = None,
        propagation_policy: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        删除指定名称的单个资源的便捷方法。

        Args:
            resource_type (str): 资源的复数形式名称，例如 "pods", "deployments"
            name (str): 资源名称
            api_version (str, optional): 资源的 API 版本
            namespace (str, optional): 资源的命名空间
            propagation_policy (str, optional): 删除传播策略
            dry_run (bool): 是否为试运行模式

        Returns:
            Dict[str, Any]: 删除操作的结果
        """
        return self.delete_resource(
            resource_type=resource_type,
            name=name,
            api_version=api_version,
            namespace=namespace,
            propagation_policy=propagation_policy,
            dry_run=dry_run
        )

    def update_resource(
        self,
        resource_body: Dict[str, Any],
        resource_type: str, # 这是资源的 plural 名称
        api_version: Optional[str] = None, # 优先使用 body 中的 apiVersion，其次用此参数
        namespace: Optional[str] = None, # 优先使用 body 中的 metadata.namespace，其次用此参数
        name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        通用方法，用于创建 Kubernetes 资源。

        Args:
            resource_body (Dict[str, Any]): 要创建的资源的完整 JSON/字典表示。
                                             必须包含 'apiVersion', 'kind', 'metadata' 等。
            resource_type (str): 资源的复数形式名称 (plural name)，例如 "pods", "deployments"。
                                 用于 dynamic_client 获取资源客户端。
            api_version (str, optional): 资源的 API 版本，例如 "v1", "apps/v1"。
                                         如果 resource_body 中没有 'apiVersion'，则使用此参数。
            namespace (str, optional): 资源的命名空间。如果 resource_body 中没有 metadata.namespace，则使用此参数。
                                      如果资源是集群级别的 (cluster-scoped)，则忽略此参数。

        Returns:
            Optional[Dict[str, Any]]: 成功创建的资源对象 (字典形式)，如果创建失败则为 None。
        """
        if not resource_body:
            raise ValueError("更新资源时必须提供有效的 resource_body 字典。")
        if resource_body.get('metadata', {}).get('name') is None:
            raise ValueError("更新资源时必须提供 'metadata.name' 字段。")
        if resource_body.get('metadata', {}).get('name') != name:
            raise ValueError("更新资源时提供的 'metadata.name' 必须与参数 name 相同。")
        # 确定 apiVersion 和 kind (resource_type)
        resolved_api_version = resource_body.get('apiVersion') or api_version
        
        # 如果仍然没有 API 版本，尝试推断
        if not resolved_api_version:
            try:
                resolved_api_version = self._infer_api_version(resource_type)
            except ValueError:
                raise ValueError("创建资源时必须提供 'apiVersion'，请确保其在请求体中或作为参数提供，或者确保 resource_type 是可识别的标准资源类型。")
        
        resolved_kind = resource_body.get('kind', '').lower()
        try:
            # 获取 dynamic client resource
            # 获取 resource 对象
            resource = self._dynamic_client.resources.get(api_version=resolved_api_version, kind=self._infer_kind_from_resource_type(resource_type))
        
            #resource_client = self._dynamic_client.resources.get(api_version=resolved_api_version, kind=resource_type)
            res = self._dynamic_client.replace(resource, body = resource_body, namespace=namespace)
            # 确定命名空间
            # resolved_namespace = resource_body.get('metadata', {}).get('namespace') or namespace

            # # 检查资源是否为命名空间级别
            # # 这是一个简化的判断，更准确的判断需要查询 API Resource List
            # # 但对于常见的资源，我们可以根据其 type 来大致判断
            # is_namespaced = resource_client.namespaced

            # if is_namespaced and not resolved_namespace:
            #     raise ValueError(f"资源 '{resource_type}' 是命名空间级别的，但未提供命名空间。")

            # if is_namespaced:
            #     created_resource = resource_client.create(body=resource_body, namespace=resolved_namespace)
            # else:
            #     created_resource = resource_client.create(body=resource_body)

            return res.to_dict() # dynamic_client 返回的对象可以转为 dict
        except ApiException as e:
            print(f"创建 Kubernetes 资源 '{resource_type}' (API Version: {resolved_api_version}) 时发生 API 错误: {e.status} - {e.reason}")
            # 尝试解析更多错误详情
            try:

                error_detail = e.body.decode('utf-8') if isinstance(e.body, bytes) else e.body
                print(f"错误详情: {error_detail}")
            except Exception:
                pass
            raise e # 重新抛出 ApiException，让 FastAPI 捕获并转换为 HTTPException
        except ValueError as e:
            print(f"参数错误: {e}")
            raise e
        except Exception as e:
            print(f"创建 Kubernetes 资源 '{resource_type}' 时发生未知错误: {e}")
            raise e