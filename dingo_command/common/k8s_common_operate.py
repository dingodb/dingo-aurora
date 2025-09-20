import base64
import textwrap
import time
from typing import Dict
import json

from kubernetes.client import V1StatefulSet, ApiException, V1Ingress, V1ObjectMeta, V1IngressSpec, \
    V1IngressRule, V1HTTPIngressRuleValue, V1HTTPIngressPath, V1IngressBackend, V1IngressServiceBackend, \
    V1ServiceBackendPort, V1ServicePort, V1Service, V1ServiceSpec
from kubernetes import client
from oslo_log import log

from dingo_command.utils.constant import RESOURCE_TYPE_KEY, PRODUCT_TYPE_CCI, DEV_TOOL_JUPYTER, INGRESS_SIGN, \
    CCI_SHARE_METALLB

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

    def create_cci_metallb_service(self, core_v1: client.CoreV1Api(), namespace: str, service_name: str, cci_service_ip: str, is_account: bool, available_ports_map):
        """
        创建带有特定注解的MetalLB Service
        """
        try:
            # 定义Service端口
            ports = [
                V1ServicePort(name="ssh", protocol="TCP", port=available_ports_map['22'], target_port=22),  # 第一个端口映射
                V1ServicePort(name="port-9001", protocol="TCP", port=available_ports_map['9001'], target_port=9001),  # 第二个端口映射
                V1ServicePort(name="port-9002", protocol="TCP", port=available_ports_map['9002'], target_port=9002)  # 第三个端口映射
            ]

            if is_account:
                metallb_share = namespace
            else:
                metallb_share = CCI_SHARE_METALLB

            # 定义Service的metadata，包含名称、命名空间、标签和关键的MetalLB注解
            metadata = V1ObjectMeta(
                name=service_name,
                namespace=namespace,
                labels={RESOURCE_TYPE_KEY: PRODUCT_TYPE_CCI},

                annotations={
                    "metallb.universe.tf/allow-shared-ip": metallb_share,  # 共享IP的标识
                    "metallb.universe.tf/loadBalancerIPs": cci_service_ip  # 指定的固定IP
                }
            )

            # 定义Service的spec
            spec = V1ServiceSpec(
                type="LoadBalancer",  # 类型为LoadBalancer，由MetalLB提供实现
                allocate_load_balancer_node_ports=False,
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

    def create_jupyter_configmap(self, core_v1: client.CoreV1Api, namespace, configmap_name, nb_prefix, nb_init_password):
        """
        创建 Jupyter Notebook 配置的 ConfigMap

        参数:
            namespace (str): Kubernetes 命名空间
            configmap_name (str): ConfigMap 名称
            jupyter_config_content (str): Jupyter Notebook 配置文件内容
        """
        try:
            # 定义ConfigMap数据
            configmap_data = {
                "NB_INIT_PASSWORD": nb_init_password,  # 使用传入的变量值
                "NOTEBOOK_ENABLE_PROXY": "False",
                "PIP_SOURCE": "nexus",
                "CONDA_SOURCE": "tsinghua",
                "APT_SOURCE": "nexus",
                "NB_PREFIX": nb_prefix
            }

            # 创建ConfigMap对象
            configmap = client.V1ConfigMap(
                api_version="v1",
                kind="ConfigMap",
                metadata=client.V1ObjectMeta(
                    name=configmap_name,
                    namespace=namespace
                ),
                data=configmap_data
            )

            # 创建 ConfigMap
            api_response = core_v1.create_namespaced_config_map(
                namespace=namespace,
                body=configmap
            )
            LOG.info(f"ConfigMap '{configmap_name}' 创建成功. API 响应: {api_response.metadata.name}")
            return api_response

        except Exception as e:
            LOG.error(f"创建 ConfigMap[{namespace}/{configmap_name}]时发生异常: {e}")
            raise e

    def create_configmap(self, core_v1: client.CoreV1Api, namespace, configmap_name, nb_prefix):
        """
        创建 Jupyter Notebook 配置的 ConfigMap

        参数:
            namespace (str): Kubernetes 命名空间
            configmap_name (str): ConfigMap 名称
            jupyter_config_content (str): Jupyter Notebook 配置文件内容
        """
        try:
            # Jupyter 配置内容
            jupyter_config_content = textwrap.dedent(f"""\
                c = get_config()
                c.ServerApp.token = ''
                c.ServerApp.password = ''
                c.ServerApp.disable_check_xsrf = True
                c.ServerApp.allow_origin = '*'
                c.ServerApp.allow_remote_access = True
                c.ServerApp.base_url = '{nb_prefix}'
                c.ServerApp.trust_xheaders = True
                c.ServerApp.allow_root = True
                """)

            # 定义 ConfigMap 主体
            configmap_manifest = {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {
                    "name": configmap_name,
                    "namespace": namespace
                },
                "data": {
                    "jupyter_notebook_config.py": jupyter_config_content  # 配置数据
                }
            }

            # 创建 ConfigMap
            api_response = core_v1.create_namespaced_config_map(
                namespace=namespace,
                body=configmap_manifest
            )
            LOG.info(f"ConfigMap '{configmap_name}' 创建成功. API 响应: {api_response.metadata.name}")
            return api_response

        except ApiException as e:
            LOG.error(f"创建 ConfigMap 时发生异常: {e}")
            raise e

    def delete_configmap(self, core_v1: client.CoreV1Api, namespace, configmap_name):
        """
        删除指定的 ConfigMap
        参数:
            namespace (str): Kubernetes 命名空间
            configmap_name (str): 要删除的 ConfigMap 名称
        """
        try:
            # propagation_policy='Background'：Kubernetes 在删除对象后立即返回，并在后台进行垃圾回收
            # grace_period_seconds=0：尽可能缩短优雅删除期限（对 ConfigMap 可能影响不大，但表明意图）
            delete_options = client.V1DeleteOptions(
                propagation_policy='Background',
                grace_period_seconds=0
            )
            api_response = core_v1.delete_namespaced_config_map(
                name=configmap_name,
                namespace=namespace,
                body=delete_options
            )
            LOG.info(f"ConfigMap '{configmap_name}' 删除请求已发送. 状态: {api_response.status}")
            return api_response

        except ApiException as e:
            if e.status == 404:
                LOG.warning(f"ConfigMap '{configmap_name}' 在命名空间 '{namespace}' 中不存在")
            else:
                LOG.error(f"删除 ConfigMap {configmap_name} 时发生异常: {e}")
            raise e

    def create_cci_ingress_rule(self, networking_v1: client.NetworkingV1Api, namespace: str, service_name: str, host_domain: str, nb_prefix: str):
        """创建Ingress Service"""
        # 定义变量
        ingress_name = f"{service_name}-{INGRESS_SIGN}"
        user_cci_pod_service_name = service_name + "-" + DEV_TOOL_JUPYTER  # 替换为实际 jupter Service 名称

        # 创建 Ingress 对象
        ingress = V1Ingress(
            api_version="networking.k8s.io/v1",
            kind="Ingress",
            metadata=V1ObjectMeta(
                name=ingress_name,
                namespace=namespace,
                annotations={
                    # "nginx.ingress.kubernetes.io/rewrite-target": "/$1",
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
                        host=host_domain,
                        http=V1HTTPIngressRuleValue(
                            paths=[
                                V1HTTPIngressPath(
                                    path=nb_prefix,
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



    def read_sts_info(self, app_v1: client.AppsV1Api, name: str, namespace: str):
        """
        查询单个 sts 的基础信息

        :param app_v1: AppsV1Api 客户端实例
        :param name: Pod 名称
        :param namespace: 命名空间，默认为 default
        :return: V1StatefulSet 对象，查询失败返回 e
        """
        try:
            return app_v1.read_namespaced_stateful_set(name, namespace)
        except Exception as e:
            print(f"查询 Pod {namespace}/{name} 失败: {e}")
            raise e


    def replace_statefulset(self, apps_v1: client.AppsV1Api, real_name, namespace_name, modified_sts_data):
        """
        替换 StatefulSet：删除旧的并创建新的，确保旧资源完全清理后再创建。

        参数:
            apps_v1: apps client。
            core_v1: core client (用于检查Pod)。
            real_name: StatefulSet 的名称。
            namespace_name: 命名空间。
            modified_sts_data: 修改后的 V1StatefulSet 对象。
        """
        try:
            # 1. 删除 StatefulSet (采用默认的级联删除策略，会删除Pod)
            delete_options = client.V1DeleteOptions(grace_period_seconds=0)
            apps_v1.delete_namespaced_stateful_set(
                name=real_name,
                namespace=namespace_name,
                body=delete_options
            )
            print(f"StatefulSet '{namespace_name}/{real_name}' 删除命令已发出.")

            # 2. 等待 StatefulSet 资源完全删除
            if not self.wait_for_sts_deletion(apps_v1, real_name, namespace_name, timeout=120):
                print(f"警告: 等待 StatefulSet '{real_name}' 删除超时，但仍尝试继续操作。")

            # 3. 创建新的 StatefulSet
            created_sts = apps_v1.create_namespaced_stateful_set(
                namespace=namespace_name,
                body=modified_sts_data
            )
            print(f"StatefulSet '{namespace_name}/{real_name}' 已重新创建.")
            return created_sts

        except Exception as e:
            print(f"替换 StatefulSet {namespace_name}/{real_name} 时发生错误: {e}")
            import traceback
            traceback.print_exc()
            raise e

    def wait_for_sts_deletion(self, apps_v1, sts_name, namespace, timeout=120, interval=1):
        """
        等待指定的 StatefulSet 被完全删除。

        参数:
            apps_v1: apps client。
            sts_name: StatefulSet 名称。
            namespace: 命名空间。
            timeout: 总等待超时时间（秒）。
            interval: 检查间隔（秒）。

        返回:
            bool: True 表示删除成功，False 表示超时。
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                apps_v1.read_namespaced_stateful_set(name=sts_name, namespace=namespace)
                # 如果read操作没抛异常，说明STS还存在
                time.sleep(interval)
            except ApiException as e:
                if e.status == 404:  # Not Found
                    print(f"StatefulSet '{namespace}/{sts_name}' 已确认删除。")
                    return True
                else:
                    # 其他API错误，可能需要根据情况处理
                    raise
            except Exception as e:
                print(f"检查 StatefulSet 删除状态时发生未知错误: {e}")
                time.sleep(interval)
        print(f"等待 StatefulSet '{namespace}/{sts_name}' 删除超时 (超时时间: {timeout} 秒)。")
        return False

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

    def list_svc_by_label(self, core_v1: client.CoreV1Api, namespace="",
                          label_selector="", limit=2000, timeout_seconds=60):
        """
        根据标签选择器列出Service，支持分页查询所有命名空间或指定命名空间

        :param core_v1: CoreV1Api 客户端实例
        :param namespace: 命名空间，为空字符串时查询所有命名空间
        :param label_selector: 标签选择器，例如 "app=my-app,environment=prod"
        :param limit: 每页返回的结果数量限制
        :param timeout_seconds: 查询超时时间
        :return: 匹配的Service列表
        :raises: RuntimeError 当查询失败时
        """
        all_svcs = []
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
                        resp = core_v1.list_namespaced_service(
                            namespace=namespace,
                            **kwargs
                        )
                    else:
                        # 分页查询所有命名空间
                        resp = core_v1.list_service_for_all_namespaces(
                            **kwargs
                        )
                except ApiException as ex:
                    raise RuntimeError(f"Failed to query Services: {str(ex)}") from ex

                all_svcs.extend(resp.items)

                # 检查是否还有更多数据
                continue_token = resp.metadata._continue
                if not continue_token:
                    break

        except Exception as e:
            print(f"list_svc_by_label failed: {e}")
            raise e

        return all_svcs

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
            print(f"已删除 StatefulSet: {namespace}/{real_sts_name}")
        except ApiException as e:
            if e.status == 404:
                print(f"StatefulSet 不存在 (StatefulSet: {namespace}/{real_sts_name})")
                return
            else:
                print(f"删除{namespace}/{real_sts_name}失败: {e.reason}")
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
            print(f"已删除 Service: {namespace}/{service_name}")
            return True

        except ApiException as e:
            import traceback
            traceback.print_exc()
            if e.status == 404:
                print(f"Service {namespace}/{service_name}不存在: {service_name}")
                return
            else:
                print(f"删除 {namespace}/{service_name}失败: {e.reason}")
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
                name=f"{ingress_name}-{INGRESS_SIGN}",
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

    def list_node(self, core_v1: client.CoreV1Api, label_selector="kubernetes.io/role=node"):
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

    def read_node(self, core_v1: client.CoreV1Api, node_name: str):
        """
        读取指定名称的节点信息

        :param core_v1: CoreV1Api客户端实例
        :param node_name: 要查询的节点名称
        :return: Node对象
        :raises: Exception 当Kubernetes API调用失败时
        """
        try:
            node = core_v1.read_node(name=node_name)
            return node
        except ApiException as e:
            error_msg = f"read node {node_name} fail: {e.reason} (status: {e.status})"
            print(error_msg)
            raise Exception(error_msg) from e

    def create_ns_configmap(self, core_v1: client.CoreV1Api, namespace_name: str, configmap_name: str, ai_instance_db,
                            configmap_data: Dict[str, str]):
        """
        创建 ConfigMap
        :param core_v1: CoreV1Api 客户端实例
        :param namespace_name: 命名空间名称
        :param configmap_name: ConfigMap 名称
        """
        from dingo_command.services.sshkey import KeyService
        # 如何把这些key_content数据组合起来
        query_params = {}
        query_params['user_id'] = ai_instance_db.instance_user_id
        query_params['tenant_id'] = ai_instance_db.instance_tenant_id
        data = KeyService().list_keys(query_params, 1, -1, None, None)
        key_content_list = []
        configmap_data = configmap_data
        if data.get("data"):
            for key in data.get("data"):
                key_content_list.append(key.key_content)
            key_content_list = list(set(key_content_list))

        if ai_instance_db.is_manager:
            if key_content_list:
                configmap_data = {
                    "authorized_keys": "\n".join(key_content_list)
                }
        else:
            # 把所有的tenant_id为同一个的key_content都租户起来
            query_params = {}
            query_params['tenant_id'] = ai_instance_db.instance_tenant_id
            query_params['is_manager'] = True
            data = KeyService().list_keys(query_params, 1, -1, None, None)
            key_content_tmp_list = []
            if data.get("data"):
                for key in data.get("data"):
                    key_content_tmp_list.append(key.key_content)
                key_content_total_list = list(set(key_content_tmp_list + key_content_list))
                configmap_data = {
                    "authorized_keys": "\n".join(key_content_total_list)
                }
            else:
                if key_content_list:
                    configmap_data = {
                        "authorized_keys": "\n".join(key_content_list)
                    }
        try:
            # 如果有就修改
            configmap = core_v1.read_namespaced_config_map(configmap_name, namespace_name)
            configmap.data["authorized_keys"] = configmap_data["authorized_keys"]
            core_v1.patch_namespaced_config_map(
                name=configmap_name,
                namespace=namespace_name,
                body=configmap
            )
        except ApiException as e:
            if e.status == 404:
                # ConfigMap 不存在，创建新的
                LOG.info("ConfigMap %s not found in namespace %s. Creating new one.", configmap_name, namespace_name)
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
                    LOG.info("Successfully created new ConfigMap %s with the SSH public key.", configmap_name)
                except ApiException as e:
                    raise e
            else:
                # 其他 API 错误
                import traceback
                traceback.print_exc()
                raise e

    def create_docker_registry_secret(self, core_v1: client.CoreV1Api, namespace, secret_name, docker_server, docker_username,
                                      docker_password, docker_email=None):
        """
        创建 Docker Registry 类型的 Secret
        """
        # 构造认证字符串并编码
        auth_str = f"{docker_username}:{docker_password}"
        auth_b64 = base64.b64encode(auth_str.encode()).decode()

        # 构造 Docker Config JSON 对象并编码
        docker_config_json = {
            "auths": {
                docker_server: {
                    "username": docker_username,
                    "password": docker_password,
                    "auth": auth_b64
                }
            }
        }
        docker_config_json_b64 = base64.b64encode(str(docker_config_json).replace("'", '"').encode()).decode()

        # 定义 Secret 对象
        secret = client.V1Secret(
            metadata=client.V1ObjectMeta(name=secret_name, namespace=namespace),
            type="kubernetes.io/dockerconfigjson",
            data={".dockerconfigjson": docker_config_json_b64}
        )

        try:
            # 在指定命名空间中创建 Secret
            core_v1.create_namespaced_secret(namespace=namespace, body=secret)
            print(f"Secret '{secret_name}' created successfully in namespace '{namespace}'.")
        except ApiException as e:
            if e.status == 409:  # 如果 Secret 已存在，则更新它
                print(f"Secret '{secret_name}' already exists in namespace '{namespace}'. Updating it.")
                core_v1.replace_namespaced_secret(name=secret_name, namespace=namespace, body=secret)
                print(f"Secret '{secret_name}' updated successfully in namespace '{namespace}'.")
            else:
                print(f"Failed to create/update secret '{secret_name}': {e}")
                raise

    def patch_default_service_account(self, core_v1: client.CoreV1Api, namespace, secret_name):
        """
        为指定命名空间的默认 ServiceAccount 添加 imagePullSecrets
        """
        try:
            # 获取当前的默认 ServiceAccount
            sa = core_v1.read_namespaced_service_account(name="default", namespace=namespace)
            # 确保 image_pull_secrets 属性是一个列表
            if sa.image_pull_secrets is None:
                sa.image_pull_secrets = []

            # 检查要添加的 secret 是否已存在，避免重复添加
            existing_secrets = [ips.name for ips in sa.image_pull_secrets]
            if secret_name not in existing_secrets:
                # 添加新的 imagePullSecret
                sa.image_pull_secrets.append(client.V1LocalObjectReference(name=secret_name))
                # 更新 ServiceAccount
                core_v1.replace_namespaced_service_account(name="default", namespace=namespace, body=sa)
                print(
                    f"Successfully added secret '{secret_name}' to default ServiceAccount in namespace '{namespace}'.")
            else:
                print(
                    f"Secret '{secret_name}' already exists in imagePullSecrets of default ServiceAccount in namespace '{namespace}'.")
        except ApiException as e:
            print(f"Failed to patch default ServiceAccount in namespace '{namespace}': {e}")
            if e.status == 404:
                print(f"Default ServiceAccount in namespace '{namespace}' not ready yet")
                # 构造 image_pull_secrets
                image_pull_secrets = [client.V1LocalObjectReference(name=secret_name)]

                # 构造 ServiceAccount 对象
                body = client.V1ServiceAccount(
                    metadata=client.V1ObjectMeta(name=secret_name),
                    image_pull_secrets=image_pull_secrets
                )

                try:
                    # 创建 ServiceAccount
                    api_response = core_v1.create_namespaced_service_account(
                        namespace=namespace,
                        body=body
                    )
                    print(f"ServiceAccount {secret_name} 创建成功")
                    return api_response
                except ApiException as e:
                    print(f"创建 ServiceAccount 时发生异常: {e}")
                    if e.status == 409:
                        print(f"Default ServiceAccount in namespace '{namespace}' ready yet")
                    raise
            else:
                print(f"Failed to patch default ServiceAccount in namespace '{namespace}': {e}")
                raise
