import json
import time

from kubernetes.client import V1StatefulSet, ApiException
from kubernetes import client
from oslo_log import log

from dingo_command.utils.constant import RESOURCE_TYPE, AI_INSTANCE

LOG = log.getLogger(__name__)

class K8sCommonOperate:

    def create_ai_instance_ns(self, core_v1: client.CoreV1Api, namespace_name: str = "default"):
        try:
            # 1. 定义命名空间对象
            namespace = client.V1Namespace(
                metadata=client.V1ObjectMeta(
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

    def create_ai_instance_sts_service(self, core_v1: client.CoreV1Api, namespace: str, service_name: str):
        """创建NodePort Service"""
        service = client.V1Service(
            metadata=client.V1ObjectMeta(name=service_name,
                                         labels={RESOURCE_TYPE: AI_INSTANCE}),
            spec=client.V1ServiceSpec(
                selector={"app": service_name,
                          RESOURCE_TYPE: AI_INSTANCE},  # 定义标签
                ports=[
                    client.V1ServicePort(
                        name="jupyter",
                        port=8888,
                        target_port=8888,
                        protocol="TCP"
                    ),
                    client.V1ServicePort(
                        name="ssh",
                        port=22,
                        target_port=22,
                        protocol="TCP"
                    )
                ],  # 定义port、target_port端口号
                # cluster_ip="",  # Headless Service
                type="NodePort",  # svc类型为NodePort
            )
        )

        try:
            create_namespaced_service_thread = core_v1.create_namespaced_service(
                namespace=namespace,
                body=service,
                async_req=True
            )
            create_namespaced_service = create_namespaced_service_thread.get()
            print(f"success get service {create_namespaced_service.metadata.name}")
            return create_namespaced_service.metadata.uid
        except client.exceptions.ApiException as e:
            if e.status == 409:
                print(f"Service {service_name} already exists")
            else:
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
        except ApiException as e:
            print(f"查询 Pod {namespace}/{name} 失败: {e.reason} (状态码: {e.status})")
            raise e.reason

    def list_pods_by_label_and_node(self, core_v1: client.CoreV1Api,
                                    namespace=None,
                                    label_selector="resource-type=ai-instance",
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
                          label_selector="resource-type=ai-instance", limit=2000, timeout_seconds=60):
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

    def list_node(self, core_v1: client.CoreV1Api):
        """
       查询所有node基础信息

       :param core_v1: CoreV1Api 客户端实例
       :return: 对象，查询失败返回 e
       """
        try:
            return core_v1.list_node()
        except ApiException as e:
            print(f"查询Node失败: {e.reason} (状态码: {e.status})")
            raise e.reason