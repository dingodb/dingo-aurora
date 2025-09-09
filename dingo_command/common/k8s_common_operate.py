from typing import Dict
import json
import time

from kubernetes.client import V1StatefulSet, ApiException, V1Ingress, V1ObjectMeta, V1IngressSpec, V1IngressTLS, \
    V1IngressRule, V1HTTPIngressRuleValue, V1HTTPIngressPath, V1IngressBackend, V1IngressServiceBackend, \
    V1ServiceBackendPort, V1ServicePort, V1Service, V1ServiceSpec
from kubernetes import client
from oslo_log import log

from dingo_command.utils.constant import RESOURCE_TYPE_KEY, PRODUCT_TYPE_CCI, DEV_TOOL_JUPYTER

LOG = log.getLogger(__name__)

class K8sCommonOperate:

    def create_ai_instance_ns(self, core_v1: client.CoreV1Api, namespace_name: str = "default"):
        try:
            # 1. 定义命名空间对象
            namespace = client.V1Namespace(
                metadata=client.V1ObjectMeta(
                    labels= {
                        "dc.com/osm.jspolicy.verify":  "false" # 不再校验GPU类型,之前针对vks的
                    },
                    name=namespace_name,
                )
            )

            # 2. 创建命名空间
            core_v1.create_namespace(body=namespace)
            print(f"namespace {namespace_name} create success")
        except Exception as e:
            print(f"namespace {namespace_name} create failed")
            import traceback
            traceback.print_exc()
            raise e

    def check_ai_instance_ns_exists(self, core_v1: client.CoreV1Api, namespace_name: str) -> bool:
        """
        检查命名空间是否已存在

        Args:
            core_v1: CoreV1Api 客户端实例
            namespace_name: 要检查的命名空间名称

        Returns:
            bool: 是否存在
        """
        try:
            core_v1.read_namespace(name=namespace_name)
            return True
        except client.exceptions.ApiException as e:
            import traceback
            traceback.print_exc()
            if e.status == 404:
                return False
            else:
                raise e

    def create_sts_pod(self, app_v1: client.AppsV1Api, namespace_name: str, stateful_set_pod_data: V1StatefulSet, async_req = True):
        create_namespaced_stateful_set_pod_thread = None
        try:
            # 创建StatefulSet Pod
            create_namespaced_stateful_set_pod_thread = app_v1.create_namespaced_stateful_set(
                namespace=namespace_name,
                body=stateful_set_pod_data,
                async_req=async_req
            )
        except Exception as e:
            LOG.info(f"create statefulset pod failed, namespace_name: {namespace_name}, stateful_set_pod_data: {json.dumps(stateful_set_pod_data)}")
            import traceback
            traceback.print_exc()
            raise e
        if create_namespaced_stateful_set_pod_thread is None:
            return None
        return create_namespaced_stateful_set_pod_thread.get()

    def create_cci_jupter_service(self, core_v1: client.CoreV1Api(), namespace: str, service_name: str):
        """创建ClusterIP Service"""
        service = client.V1Service(
            metadata=client.V1ObjectMeta(name=service_name + "-" + DEV_TOOL_JUPYTER,
                                         labels={RESOURCE_TYPE_KEY: PRODUCT_TYPE_CCI}),
            spec=client.V1ServiceSpec(
                selector={"app": service_name,
                          RESOURCE_TYPE_KEY: PRODUCT_TYPE_CCI},  # 定义标签
                ports=[
                    client.V1ServicePort(
                        name=DEV_TOOL_JUPYTER,
                        port=8888,
                        target_port=8888,
                        protocol="TCP"
                    )
                ],  # 定义port、target_port端口号
                type="ClusterIP",
            )
        )

        try:
            create_namespaced_service_thread = core_v1.create_namespaced_service(
                namespace=namespace,
                body=service,
                async_req=True
            )
            create_namespaced_service = create_namespaced_service_thread.get()
            print(f"success create jupter service {create_namespaced_service.metadata.name}")
            return create_namespaced_service.metadata.uid
        except client.exceptions.ApiException as e:
            print(f"Jupter service {service_name}  cerate failed:{e}")
            import traceback
            traceback.print_exc()
            raise e

    def create_cci_metallb_service(self, core_v1: client.CoreV1Api(), namespace: str, service_name: str, cci_service_ip: str):
        """
        创建带有特定注解的MetalLB Service
        """
        try:
            # 定义Service端口
            ports = [
                V1ServicePort(name="ssh", protocol="TCP", port=22, target_port=22),  # 第一个端口映射
                V1ServicePort(name="port-9001", protocol="TCP", port=9001, target_port=9001),  # 第二个端口映射
                V1ServicePort(name="port-9002", protocol="TCP", port=9002, target_port=9002)  # 第三个端口映射
            ]

            # 定义Service的metadata，包含名称、命名空间、标签和关键的MetalLB注解
            metadata = V1ObjectMeta(
                name=service_name,
                namespace=namespace,
                labels={RESOURCE_TYPE_KEY: PRODUCT_TYPE_CCI},

                annotations={
                    "metallb.universe.tf/allow-shared-ip": service_name,  # 共享IP的标识
                    "metallb.universe.tf/loadBalancerIPs": cci_service_ip  # 指定的固定IP
                }
            )

            # 定义Service的spec
            spec = V1ServiceSpec(
                type="LoadBalancer",  # 类型为LoadBalancer，由MetalLB提供实现
                ports=ports,
                selector={
                    "app": service_name,
                    RESOURCE_TYPE_KEY: PRODUCT_TYPE_CCI
                },  # 定义标签  # 选择器，指向拥有此标签的Pod
            )

            # 构建Service对象
            service = V1Service(api_version="v1", kind="Service", metadata=metadata, spec=spec)
            # 创建Service
            create_namespaced_service_thread = core_v1.create_namespaced_service(
                namespace=namespace,
                body=service,
                async_req=True
            )
            create_namespaced_service = create_namespaced_service_thread.get()
            print(f"success create metallb service {create_namespaced_service.metadata.name}")
            return create_namespaced_service.metadata.uid
        except ApiException as e:
            print(f"创建Metallb Service时发生Kubernetes API异常: {e}")
            print(f"异常详情: {e.body}")
        except Exception as e:
            print(f"创建Service时发生系统异常: {e}")

    def create_cci_ingress_rule(self, networking_v1: client.NetworkingV1Api, instance_id: str, namespace: str, service_name: str, k8s_id: str, region_id: str):
        """创建Ingress Service"""
        # 定义变量
        ingress_name = f"cci-{service_name}-ingress"
        user_cci_pod_service_name = service_name + "-" + DEV_TOOL_JUPYTER  # 替换为实际 jupter Service 名称
        if not region_id:  # 替换为实际 region_id, 云上会传过来
            region_id = "default"
        zone_id = k8s_id  # 替换为实际 zone_id
        cci_pod_name = service_name + '-0'  # 替换为实际 Pod 名称

        # 构建 Ingress 主机名和路径
        host = f"{region_id}-{zone_id}.alayanew.com"
        path = f"/{instance_id}/notebook/jupyter/{namespace}/{cci_pod_name}"

        # 创建 Ingress 对象
        ingress = V1Ingress(
            api_version="networking.k8s.io/v1",
            kind="Ingress",
            metadata=V1ObjectMeta(
                name=ingress_name,
                namespace=namespace,
                annotations={
                    "nginx.ingress.kubernetes.io/rewrite-target": "/$1",
                    "nginx.ingress.kubernetes.io/ssl-redirect": "true",
                    "nginx.ingress.kubernetes.io/websocket-services": service_name + "-" + DEV_TOOL_JUPYTER,
                    "nginx.ingress.kubernetes.io/proxy-read-timeout": "3600",
                    "nginx.ingress.kubernetes.io/proxy-send-timeout": "3600",
                },
            ),
            spec=V1IngressSpec(
                ingress_class_name="nginx",
                rules=[
                    V1IngressRule(
                        host=host,
                        http=V1HTTPIngressRuleValue(
                            paths=[
                                V1HTTPIngressPath(
                                    path=path,
                                    path_type="Prefix",
                                    backend=V1IngressBackend(
                                        service=V1IngressServiceBackend(
                                            name=user_cci_pod_service_name,
                                            port=V1ServiceBackendPort(number=8888),
                                        )
                                    ),
                                )
                            ]
                        ),
                    )
                ],
            ),
        )

        # 创建 Ingress
        try:
            api_response = networking_v1.create_namespaced_ingress(
                namespace=namespace,
                body=ingress,
            )
            print(f"Ingress created successfully: {api_response.metadata.name}")
        except Exception as e:
            print(f"Error creating Ingress: {e}")
            import traceback
            traceback.print_exc()
            raise e

    def is_node_port_in_use(self, core_v1: client.CoreV1Api, node_port: int) -> bool:
        """检查某个 NodePort 是否在整个集群范围内已被占用"""
        try:
            services = core_v1.list_service_for_all_namespaces()
            for svc in services.items:
                if not svc.spec or not svc.spec.ports:
                    continue
                for p in svc.spec.ports:
                    if getattr(p, 'node_port', None) == node_port:
                        return True
            return False
        except Exception as e:
            import traceback
            traceback.print_exc()
            # 如果检查失败，为安全起见视为已占用，避免冲突
            return True

    def is_port_in_use(self, core_v1: client.CoreV1Api, port: int) -> bool:
        """检查某个 Service Port 是否在整个集群范围内已被占用"""
        try:
            services = core_v1.list_service_for_all_namespaces()
            for svc in services.items:
                if not svc.spec or not svc.spec.ports:
                    continue
                for p in svc.spec.ports:
                    if getattr(p, 'port', None) == port:
                        return True
            return False
        except Exception as e:
            import traceback
            traceback.print_exc()
            # 如果检查失败，为安全起见视为已占用，避免冲突
            return True

    def get_pod_info(self, core_v1: client.CoreV1Api, name: str, namespace: str):
        """
        查询单个 Pod 的基础信息

        :param core_v1: CoreV1Api 客户端实例
        :param name: Pod 名称
        :param namespace: 命名空间，默认为 default
        :return: V1Pod 对象，查询失败返回 e
        """
        try:
            return core_v1.read_namespaced_pod(name, namespace)
        except Exception as e:
            print(f"查询 Pod {namespace}/{name} 失败: {e}")
            raise e

    def list_pods_by_label_and_node(self, core_v1: client.CoreV1Api,
                                    namespace=None,
                                    label_selector=f"{RESOURCE_TYPE_KEY}={PRODUCT_TYPE_CCI}",
                                    node_name=None,  # 新增：节点名称参数
                                    limit=2000,
                                    timeout_seconds=60):
        all_pods = []
        continue_token = None
        try:
            while True:
                # 构造查询参数
                kwargs = {
                    "label_selector": label_selector,
                    "limit": limit,
                    "_continue": continue_token,
                    "timeout_seconds": timeout_seconds
                }

                if node_name:
                    kwargs["field_selector"] = f"spec.nodeName={node_name}"

                try:
                    if namespace:
                        # 分页查询指定命名空间
                        resp = core_v1.list_namespaced_pod(
                            namespace=namespace,
                            **kwargs
                        )
                    else:
                        # 分页查询所有命名空间
                        resp = core_v1.list_pod_for_all_namespaces(
                            **kwargs
                        )
                except Exception as ex:
                    raise RuntimeError(f"Failed to query pod: {str(ex)}") from ex

                all_pods.extend(resp.items)

                # 检查是否还有更多数据
                continue_token = resp.metadata._continue
                if not continue_token:
                    break
        except Exception as e:
            print(f"list_namespaced_stateful_set failed:{e}")
            raise e

        return all_pods

    def list_sts_by_label(self, app_v1: client.AppsV1Api, namespace="",
                          label_selector=f"{RESOURCE_TYPE_KEY}={PRODUCT_TYPE_CCI}", limit=2000, timeout_seconds=60):
        all_sts = []
        continue_token = None
        try:
            while True:
                # 构造查询参数
                kwargs = {
                    "label_selector": label_selector,
                    "limit": limit,
                    "_continue": continue_token,
                    "timeout_seconds": timeout_seconds
                }
                try:
                    if namespace:
                        # 分页查询指定命名空间
                        resp = app_v1.list_namespaced_stateful_set(
                            namespace=namespace,
                            **kwargs
                        )
                    else:
                        # 分页查询所有命名空间
                        resp = app_v1.list_stateful_set_for_all_namespaces(
                            **kwargs
                        )
                except Exception as ex:
                    raise RuntimeError(f"Failed to query StatefulSets: {str(ex)}") from ex

                all_sts.extend(resp.items)

                # 检查是否还有更多数据
                continue_token = resp.metadata._continue
                if not continue_token:
                    break
        except Exception as e:
            print(f"list_namespaced_stateful_set failed:{e}")
            raise e
        return all_sts

    def delete_sts_by_name(self,
            apps_v1: client.AppsV1Api,
            real_sts_name: str,
            namespace: str = None,
            grace_period_seconds: int = 0,
            propagation_policy: str = 'Foreground'  # 可选：'Orphan'/'Background'
    ):
        """
        根据 name 精确删除 StatefulSet

        Args:
            apps_v1: AppsV1Api 实例
            real_sts_name: StatefulSet 的 name
            namespace: 命名空间
            grace_period_seconds: 优雅删除等待时间（0表示立即删除）
            propagation_policy: 级联删除策略
        """
        try:
            # 执行删除
            apps_v1.delete_namespaced_stateful_set(
                name=real_sts_name,
                namespace=namespace,
                grace_period_seconds=grace_period_seconds,
                propagation_policy=propagation_policy,
                body=client.V1DeleteOptions()
            )
            print(f"已删除 StatefulSet: {real_sts_name}")
        except ApiException as e:
            if e.status == 404:
                print(f"StatefulSet 不存在 (StatefulSet: {real_sts_name})")
                return
            else:
                print(f"删除失败: {e.reason}")
            return False

    def delete_service_by_name(self,
            core_v1: client.CoreV1Api,
            service_name: str,
            namespace: str = None,
            grace_period_seconds: int = 0):
        """
        根据名称删除 Service

        Args:
            core_v1: CoreV1Api 实例
            service_name: Service 名称
            namespace: 命名空间
            grace_period_seconds: 优雅删除等待时间
        """
        try:
            core_v1.delete_namespaced_service(
                name=service_name,
                namespace=namespace,
                grace_period_seconds=grace_period_seconds,
                body=client.V1DeleteOptions()
            )
            print(f"已删除 Service: {service_name}")
            return True

        except ApiException as e:
            import traceback
            traceback.print_exc()
            if e.status == 404:
                print(f"Service 不存在: {service_name}")
                return
            else:
                print(f"删除失败: {e.reason}")
            raise e

    def delete_namespaced_ingress(self, networking_v1: client.NetworkingV1Api, ingress_name: str, namespace: str):
        """
        删除指定命名空间中的指定Ingress资源

        Args:
            ingress_name (str): 要删除的Ingress资源的名称
            namespace (str): Ingress资源所在的命名空间。
        """
        try:
            # 删除Ingress
            api_response = networking_v1.delete_namespaced_ingress(
                name=f"cci-{ingress_name}-ingress",
                namespace=namespace,
                body=client.V1DeleteOptions(  # 可选删除参数
                    propagation_policy='Foreground',  # 删除策略：'Foreground', 'Background', 'Orphan'
                    grace_period_seconds=0  # 宽限期秒数，0表示立即删除
                )
            )
            print(f"Ingress '{ingress_name}' in namespace '{namespace}' deleted successfully. API Response status: {api_response.status}")
        except Exception as e:
            print(f"Exception when calling NetworkingV1Api->delete_namespaced_ingress {ingress_name}: {e}")
            raise e

    def list_node(self, core_v1: client.CoreV1Api, label_selector="kubernetes.io/role"):
        """
       查询所有node基础信息

       :param core_v1: CoreV1Api 客户端实例
       :return: 对象，查询失败返回 e
       """
        try:
            kwargs = {
                "label_selector": label_selector
            }
            return core_v1.list_node(**kwargs).items
        except ApiException as e:
            print(f"查询Node失败: {e.reason} (状态码: {e.status})")
            raise e.reason

    def create_ns_configmap(self, core_v1: client.CoreV1Api, namespace_name: str, configmap_name: str,
                            configmap_data: Dict[str, str]):
        """
        创建 ConfigMap
        :param core_v1: CoreV1Api 客户端实例
        :param namespace_name: 命名空间名称
        :param configmap_name: ConfigMap 名称
        """
        try:
            core_v1.read_namespaced_config_map(configmap_name, namespace_name)
        except ApiException as e:
            if e.status == 404:
                # ConfigMap 不存在，创建新的
                LOG.info(f"ConfigMap '{configmap_name}' not found in namespace '{namespace_name}'. Creating new one.")

                # 创建新的 ConfigMap 对象
                new_configmap = client.V1ConfigMap(
                    api_version="v1",
                    kind="ConfigMap",
                    metadata=client.V1ObjectMeta(
                        name=configmap_name,
                        namespace=namespace_name
                    ),
                    data=configmap_data
                )
                try:
                    # 创建 ConfigMap
                    core_v1.create_namespaced_config_map(
                        namespace=namespace_name,
                        body=new_configmap
                    )
                    LOG.info(f"Successfully created new ConfigMap '{configmap_name}' with the SSH public key.")
                except ApiException as e:
                    raise e
            else:
                # 其他 API 错误
                raise e