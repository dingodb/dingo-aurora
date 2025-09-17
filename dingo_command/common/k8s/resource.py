import logging
from typing import Dict, Any, Optional, Union, Type, List

# 导入各种资源客户端
try:
    from .pod import PodClient
except ImportError:
    PodClient = None

try:
    from .deployment import DeploymentClient
except ImportError:
    DeploymentClient = None

try:
    from .service import ServiceClient
except ImportError:
    ServiceClient = None

try:
    from .statefulset import StatefulSetClient
except ImportError:
    StatefulSetClient = None

try:
    from .configmap import ConfigMapClient
except ImportError:
    ConfigMapClient = None

try:
    from .secret import SecretClient
except ImportError:
    SecretClient = None

try:
    from .ingress import IngressClient
except ImportError:
    IngressClient = None

try:
    from .job import JobClient
except ImportError:
    JobClient = None

try:
    from .cronjob import CronJobClient
except ImportError:
    CronJobClient = None

try:
    from .daemonset import DaemonSetClient
except ImportError:
    DaemonSetClient = None

logger = logging.getLogger(__name__)


class ResourceClientFactory:
    """
    资源客户端工厂，根据不同的资源类型返回相应的客户端实例
    """
    
    def __init__(self, k8s_client):
        """
        初始化资源客户端工厂
        
        Args:
            k8s_client: K8sClient 实例
        """
        self._k8s_client = k8s_client
        self._client_classes = {
            "pods": PodClient,
            "deployments": DeploymentClient,
            "services": ServiceClient,
            "statefulsets": StatefulSetClient,
            "configmaps": ConfigMapClient,
            "secrets": SecretClient,
            "ingresses": IngressClient,
            "jobs": JobClient,
            "cronjobs": CronJobClient,
            "daemonsets": DaemonSetClient,
        }
        # 实例缓存
        self._client_instances = {}
    
    def get_client(self, resource_type: str) -> Optional[Any]:
        """
        获取指定资源类型的客户端实例
        
        Args:
            resource_type: 资源类型，如 "pods", "deployments", "services" 等
            
        Returns:
            资源类型对应的客户端实例，如果不支持该资源类型，则返回 None
        """
        
        # 检查缓存
        if resource_type in self._client_instances:
            return self._client_instances[resource_type]
        
        # 获取客户端类
        client_class = self._client_classes.get(resource_type)
        if client_class is None:
            logger.warning(f"不支持的资源类型: {resource_type}")
            return None
        
        # 创建客户端实例
        try:
            client_instance = client_class(self._k8s_client)
            self._client_instances[resource_type] = client_instance
            return client_instance
        except Exception as e:
            logger.error(f"创建 {resource_type} 客户端实例失败: {e}")
            return None

    def supports_resource(self, resource_type: str) -> bool:
        """
        检查是否支持指定的资源类型
        
        Args:
            resource_type: 资源类型名称
            
        Returns:
            如果支持该资源类型，返回 True；否则返回 False
        """
        # 标准化资源类型名称
        resource_type = resource_type.lower()
        if resource_type.endswith('y'):
            resource_type = resource_type[:-1] + 'ies'
        elif not resource_type.endswith('s'):
            resource_type = resource_type + 's'
            
        return resource_type in self._client_classes and self._client_classes[resource_type] is not None

    def register_client(self, resource_type: str, client_class: Type) -> None:
        """
        注册自定义资源客户端
        
        Args:
            resource_type: 资源类型名称
            client_class: 客户端类
        """
        # 标准化资源类型名称
        resource_type = resource_type.lower()
        if resource_type.endswith('y'):
            resource_type = resource_type[:-1] + 'ies'
        elif not resource_type.endswith('s'):
            resource_type = resource_type + 's'
            
        self._client_classes[resource_type] = client_class
        # 清除缓存
        if resource_type in self._client_instances:
            del self._client_instances[resource_type]
            
    def get_supported_resource_types(self) -> list:
        """
        获取所有支持的资源类型列表
        
        Returns:
            支持的资源类型名称列表
        """
        return [resource_type for resource_type, client_class in self._client_classes.items() 
                if client_class is not None]

    def list(
        self, 
        items: List[Dict[str, Any]],
        resource_type: str, 
        labels: Optional[Dict[str, str]] = None,
        filters: Optional[str] = None,
        namespace: Optional[str] = None,
        match_all: bool = True,
        **kwargs
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        
        # 如果没有标签筛选，直接返回结果
        if labels is None and filters is None:
            return items
        resource_list = items
        # 获取对应的资源客户端
        client = self.get_client(resource_type)

        try:
            resource_list = client.list(
                items=items,
                labels=labels,
                filters=filters,
                namespace=namespace,
                match_all=match_all
            )
            return resource_list
        except Exception as e:
            logger.error(f"调用 {resource_type} 客户端的 list 方法失败: {e}")
            # 失败时返回原始结果
            return resource_list
