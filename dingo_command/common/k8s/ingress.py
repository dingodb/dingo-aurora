import logging
from typing import Dict, List, Optional, Any, Union
from kubernetes.client.rest import ApiException


logger = logging.getLogger(__name__)

class IngressClient:
    def __init__(self, k8s_client):

        self._k8s_client = k8s_client
    
    def list(
        self, 
        items: List[Dict[str, Any]],
        labels: Dict[str, str], 
        filters: Optional[List[str]] = None,
        namespace: Optional[str] = None,
        match_all: bool = True
    ) -> List[Dict[str, Any]]:
       
        try:

            matched_services = []
            # 处理 filters 参数，查找关联的工作负载并获取其标签
            workload_types = ["deployments", "statefulsets", "daemonsets"]
            workload_labels = {}
            
            if filters:
                for filter_str in filters:
                    if "=" in filter_str:
                        key, value = filter_str.split("=", 1)
                        if key in workload_types:
                            matched_services = self._k8s_client.list_resource("services", namespace=namespace, label_selector=labels, field_selector=None, search_terms=filters)
                            
            matched_ingresses = []
            for ingress in items:
                # 检查ingress是否关联到匹配的service
                for service in matched_services:
                    service_name = service.get('metadata', {}).get('name')
                    if not service_name:
                        continue
                    
                    # 检查ingress是否关联到此service
                    is_associated = False
                    rules = ingress.get('spec', {}).get('rules', [])
                    
                    for rule in rules:
                        http_paths = rule.get('http', {}).get('paths', [])
                        for path in http_paths:
                            backend = path.get('backend', {})
                            
                            # 处理旧版API格式 (serviceName直接在backend中)
                            if 'serviceName' in backend and backend.get('serviceName') == service_name:
                                is_associated = True
                                break
                            
                            # 处理新版API格式 (service.name在backend.service中)
                            if 'service' in backend and backend.get('service', {}).get('name') == service_name:
                                is_associated = True
                                break
                        
                        if is_associated:
                            break
                    
                    if is_associated:
                        matched_ingresses.append(ingress)
                        break
            return matched_ingresses

        except ApiException as e:
            logger.error(f"获取 Service 列表失败: {e}")
            raise
        except Exception as e:
            logger.error(f"获取 Service 列表时发生错误: {e}")
            raise
    