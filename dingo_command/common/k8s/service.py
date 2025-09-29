import logging
from typing import Dict, List, Optional, Any, Union
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)

class ServiceClient:
    def __init__(self, k8s_client):
        """
        初始化 Service 客户端
        
        Args:
            k8s_client: K8sClient 实例
        """
        self._k8s_client = k8s_client
    
    def list(
        self, 
        items: List[Dict[str, Any]],
        labels: Dict[str, str], 
        filters: Optional[List[str]] = None,
        namespace: Optional[str] = None,
        match_all: bool = True
    ) -> List[Dict[str, Any]]:
        """
        根据工作负载的 labels 筛选 Service 资源列表
        
        Args:
            labels: 工作负载的标签字典，如 {"app": "nginx", "tier": "frontend"}
            namespace: 命名空间名称，如果为 None 则查询所有命名空间
            match_all: 是否需要匹配所有标签，True 表示所有标签都匹配才返回，
                      False 表示匹配任一标签即返回
        
        Returns:
            匹配的 Service 资源列表
        """
        try:

            matched_services = []
            # 处理 filters 参数，查找关联的工作负载并获取其标签
            workload_types = ["deployments", "statefulsets", "daemonsets"]
            workload_labels = {}
            if filters is None or len(filters) == 0:
                return items

            for filter_str in filters:
                if "=" in filter_str:
                    key, value = filter_str.split("=", 1)
                    if key in workload_types:
                        # 查询指定的工作负载
                        try:
                            workload = self._k8s_client.get_resource(
                                resource_type=key,
                                name=value,
                                namespace=namespace
                            )
                            
                            if workload:
                                # 获取工作负载的标签
                                pod_template_labels = workload.get('spec', {}).get('template', {}).get('metadata', {}).get('labels', {})
                                if pod_template_labels:
                                    # 合并标签
                                    workload_labels.update(pod_template_labels)
                                    logger.info(f"找到工作负载 {key}/{value} 的标签: {pod_template_labels}")
                        except Exception as e:
                            logger.warning(f"获取工作负载 {key}/{value} 时出错: {e}")
            
            # 如果通过 filters 找到了工作负载标签，将其与传入的 labels 合并
            if workload_labels:
                if labels:
                    # 合并两个标签字典
                    merged_labels = {**labels, **workload_labels}
                else:
                    merged_labels = workload_labels
                
                labels = merged_labels
            
            # 如果没有标签，返回所有项目
            if not labels:
                return []

            for service in items:
                # 获取 Service 的 selector
                selector = service.get('spec', {}).get('selector', {})
                
                if not selector:
                    continue
                
                # 检查 selector 是否匹配提供的 labels
                if match_all:
                    # 所有标签都必须匹配
                    match = all(selector.get(key) == value for key, value in labels.items())
                else:
                    # 匹配任一标签
                    match = any(selector.get(key) == value for key, value in labels.items() if key in selector)
                
                if match:
                    matched_services.append(service)
            
            return matched_services
            
        except ApiException as e:
            logger.error(f"获取 Service 列表失败: {e}")
            raise
        except Exception as e:
            logger.error(f"获取 Service 列表时发生错误: {e}")
            raise
    
    def get_services_for_workload(
        self, 
        workload_type: str,
        workload_name: str,
        namespace: str
    ) -> List[Dict[str, Any]]:
        """
        根据工作负载类型和名称获取关联的 Service 列表
        
        Args:
            workload_type: 工作负载类型，如 "deployment", "statefulset", "daemonset"
            workload_name: 工作负载名称
            namespace: 命名空间名称
            
        Returns:
            与工作负载关联的 Service 资源列表
        """
        try:
            # 获取工作负载
            workload = self._k8s_client.get_namespaced_resource(
                workload_type, 
                workload_name, 
                namespace
            )
            
            if not workload:
                return []
            
            # 获取工作负载的标签
            labels = workload.get('metadata', {}).get('labels', {})
            
            if not labels:
                return []
                
            # 根据标签查找 Service
            return self.list_services_by_workload_labels(labels, namespace)
            
        except ApiException as e:
            logger.error(f"获取工作负载 {workload_type}/{workload_name} 关联的 Service 列表失败: {e}")
            raise
        except Exception as e:
            logger.error(f"获取工作负载关联的 Service 列表时发生错误: {e}")
            raise
    
    def check_service_points_to_workload(
        self,
        service_name: str,
        workload_type: str,
        workload_name: str,
        namespace: str
    ) -> bool:
        """
        检查指定 Service 是否指向特定的工作负载
        
        Args:
            service_name: Service 名称
            workload_type: 工作负载类型，如 "deployment", "statefulset"
            workload_name: 工作负载名称
            namespace: 命名空间
            
        Returns:
            如果 Service 指向该工作负载，则返回 True，否则返回 False
        """
        try:
            # 获取工作负载
            workload = self._k8s_client.get_namespaced_resource(
                workload_type, 
                workload_name, 
                namespace
            )
            
            if not workload:
                return False
                
            # 获取工作负载的标签
            workload_labels = workload.get('metadata', {}).get('labels', {})
            
            if not workload_labels:
                return False
                
            # 获取 Service
            service = self._k8s_client.get_namespaced_resource(
                "services", 
                service_name, 
                namespace
            )
            
            if not service:
                return False
                
            # 获取 Service 的选择器
            service_selector = service.get('spec', {}).get('selector', {})
            
            if not service_selector:
                return False
                
            # 检查 Service 选择器是否匹配工作负载的标签
            for key, value in service_selector.items():
                if workload_labels.get(key) != value:
                    return False
                    
            return True
            
        except ApiException as e:
            logger.error(f"检查 Service {service_name} 是否指向工作负载 {workload_type}/{workload_name} 失败: {e}")
            return False
        except Exception as e:
            logger.error(f"检查 Service 和工作负载关联时发生错误: {e}")
            return False