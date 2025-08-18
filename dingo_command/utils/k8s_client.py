# k8s的client
import json
import os
from typing import Optional

from kubernetes import client, config

from dingo_command.db.models.ai_instance.models import AiK8sKubeConfigConfigs
from dingo_command.db.models.ai_instance.sql import AiInstanceSQL
import yaml

from dingo_command.utils.constant import KUBECONFIG_DIR_DEFAULT
from typing import Type, TypeVar, Any
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 类型变量用于泛型
T = TypeVar('T')


def get_k8s_client(k8s_id: str,client_type: Type[T], **kwargs: Any) -> T:
    """
    通用 Kubernetes 客户端获取函数

    Args:
        k8s_id: Kubernetes 集群 ID
        client_type: 要获取的客户端类 (如 CoreV1Api, AppsV1Api 等)
        **kwargs: 传递给客户端构造函数的额外参数

    Returns:
        指定类型的 Kubernetes 客户端实例
    """

    # 1. 获取数据库配置
    kubeconfig_configs_db = AiInstanceSQL.get_k8s_kubeconfig_info_by_k8s_id(k8s_id)
    if not kubeconfig_configs_db:
        error_msg = f"by {k8s_id} 无法获取 kubeconfig 配置信息"
        logger.error(error_msg)
        raise ValueError(error_msg)

    _validate_kubeconfig_config(kubeconfig_configs_db, k8s_id)

    # 2. 确定 kubeconfig 文件路径和上下文名称
    config_file = _resolve_kubeconfig_path(kubeconfig_configs_db)
    context_name = _resolve_context_name(kubeconfig_configs_db)

    # 3. 加载配置
    try:
        config.load_kube_config(
            config_file=config_file,
            context=context_name  # None 时自动使用 current-context
        )
        print(f"loaded kubeconfig: config_file={config_file}, context={context_name or 'current-context'}")
    except Exception as e:
        error_msg = f"load kubeconfig fail: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e

    # 4. 创建并返回请求的客户端
    try:
        # 检查是否是有效的客户端类型
        if not hasattr(client, client_type.__name__):
            error_msg = f"invalid Kubernetes client: {client_type.__name__}"
            logger.error(error_msg)
            raise TypeError(error_msg)

        # 实例化客户端
        api_client = client_type(**kwargs)
        logger.debug(f"success create {client_type.__name__} client")
        return api_client

    except Exception as e:
        error_msg = f"create {client_type.__name__} client fail: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


# 常用客户端的便捷方法
def get_k8s_core_client(k8s_id: str) -> client.CoreV1Api:
    """获取 CoreV1Api 客户端"""
    return get_k8s_client(k8s_id, client.CoreV1Api)


def get_k8s_app_client(k8s_id: str) -> client.AppsV1Api:
    """获取 AppsV1Api 客户端"""
    return get_k8s_client(k8s_id, client.AppsV1Api)


def _validate_kubeconfig_config(config_info: AiK8sKubeConfigConfigs, k8s_id: str) -> None:
    """验证配置合法性"""
    if not config_info:
        raise ValueError(f"{k8s_id} kubeconfig configs配置为空")
    if not config_info.kubeconfig_path and not config_info.kubeconfig:
        raise ValueError(f"必须提供{k8s_id} kubeconfig_path或kubeconfig内容")


def _resolve_kubeconfig_path(config_info: AiK8sKubeConfigConfigs) -> str:
    """
    解析kubeconfig文件路径（优先检查已有文件，否则动态生成）

    Returns:
        str: 最终使用的kubeconfig文件绝对路径
    """
    # 情况1: 配置中指定的文件已存在
    if config_info.kubeconfig_path and os.path.exists(config_info.kubeconfig_path):
        logger.debug(f"文件已存在：{config_info.kubeconfig_path}")
        return config_info.kubeconfig_path

    # 情况2: 需要从内容生成文件
    if not config_info.kubeconfig:
        raise FileNotFoundError("无有效的kubeconfig文件或内容")

    # 确保目录存在
    os.makedirs(KUBECONFIG_DIR_DEFAULT, mode=0o755, exist_ok=True)

    # 生成文件名格式: kubeconfig_{k8s_id}
    kubeconfig_file_name = f"kubeconfig_{config_info.k8s_id}"
    config_file = os.path.join(KUBECONFIG_DIR_DEFAULT, kubeconfig_file_name)

    logger.debug(f"config_file：{config_file}")
    if os.path.exists(config_file):
        logger.info(f"文件[{config_file}]已存在不再重复生成")
        return config_file

    # 确保输入是字典格式
    if isinstance(config_info.kubeconfig, str):
        try:
            # 尝试解析字符串形式的JSON
            config_data = json.loads(config_info.kubeconfig)
        except json.JSONDecodeError:
            # 如果已经是YAML格式则直接使用
            config_data = yaml.safe_load(config_info.kubeconfig)
    else:
        # 如果已经是YAML格式则直接使用
        config_data = yaml.safe_load(config_info.kubeconfig)

    # 验证基本结构
    if not all(key in config_data for key in ['apiVersion', 'kind', 'clusters']):
        raise ValueError("无效的kubeconfig格式")

    # 写入文件
    with open(config_file, 'w') as f:
        yaml.dump(
            config_data,
            f,
            indent=2,  # 标准2空格缩进
            default_flow_style=False  # 保持多行格式
        )

    return config_file


def _resolve_context_name(config_info: AiK8sKubeConfigConfigs) -> Optional[str]:
    """解析上下文名称（显式指定 > 自动解析）"""
    # 优先级1: 直接指定的上下文
    if config_info.kubeconfig_context_name:
        return config_info.kubeconfig_context_name

    # 优先级2: 从kubeconfig内容解析admin上下文
    if config_info.kubeconfig:
        contexts = _parse_contexts(config_info.kubeconfig)
        return contexts[0] if contexts else None
    else:
        # 返回None（将使用current-context）
        return None


def _parse_contexts(kubeconfig_content: str) -> list[str]:
    """解析包含-admin的上下文（按名称排序）"""
    try:
        config_data = yaml.safe_load(kubeconfig_content)
        return sorted(
            ctx["name"]
            for ctx in config_data.get("contexts", [])
            if "-admin" in ctx.get("context", {}).get("user", "").lower()
        )
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse kubeconfig: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error parsing contexts: {str(e)}")
        return []


if __name__ == '__main__':
    kubeconfig_str = """
    {
      "apiVersion": "v1",
      "clusters": [
        {
          "cluster": {
            "certificate-authority-data": "LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSURCVENDQWUyZ0F3SUJBZ0lJT2puMW5zOTVydW93RFFZSktvWklodmNOQVFFTEJRQXdGVEVUTUJFR0ExVUUKQXhNS2EzVmlaWEp1WlhSbGN6QWVGdzB5TlRBM01Ea3dOREk0TlROYUZ3MHpOVEEzTURjd05ETXpOVE5hTUJVeApFekFSQmdOVkJBTVRDbXQxWW1WeWJtVjBaWE13Z2dFaU1BMEdDU3FHU0liM0RRRUJBUVVBQTRJQkR3QXdnZ0VLCkFvSUJBUURMcTNuSlZWRFBYQTJHNTlkT2xGazRObytZSmdoeW0wRVJaUjFCMEQ2cVoxRnNxMUs0NFJQR2tGTkkKZ21EUTlVV29mOENIRldmWno1aGlITEZMSnY0LzBLNGdkcjByRlczenlvUDJiRFJERDRlVnBMb3hHbXF4RXZKUgorK0F3ZGFicUp6bmY2bVVNK1VtekFWSFEzWFR2NENTbk9YK293eGg5VUdFYjFLV05iclNQcEY0Q2hQR2Rwd0tBCjVZNkkxMXhBN0RkOUp6Nnc5KzB0b0pBbHZuaTEydVF4eVAvUkZ4STU4aytsTUdVRDlZQXRHUHRKbWRnRGtDZkQKb2diTnByWFlDb2xEdmg3VGZIb0hZTGNkTEJCaFRtdmx6NTZOYzJkZE9mVm5sekNYMFh0TEtlSDBjYlBlVlI3VQoweVRWZE40bE9VVmRhamlEZ1huWmxCVm1FR09CQWdNQkFBR2pXVEJYTUE0R0ExVWREd0VCL3dRRUF3SUNwREFQCkJnTlZIUk1CQWY4RUJUQURBUUgvTUIwR0ExVWREZ1FXQkJTVGFreFZITDJhVlBLd1QvMDVzZ0orRXBLRm9qQVYKQmdOVkhSRUVEakFNZ2dwcmRXSmxjbTVsZEdWek1BMEdDU3FHU0liM0RRRUJDd1VBQTRJQkFRQnA1M3ZuSTA2bgpHcjFKTkpTYW92Tk1PWnFFaUVqWkYzdDh2a1c3TUNLcnRITEVCMUtBRHdjV3BzenZ2Q3pqTytVWW5OZE9GOWxiCjF4NFZyYlpaemlzTW9MdEtYVW9rVmd4aWlMK1NwYmxOSlBnQVJibnJPU0oxR2g1Y1pUZ0hySTQ2UXU0V0oxYXoKdHJvbXphQ1IwZThrQXE2c2RTbE9ReklJcm1QZnNLcG53V2ZRK2VhTkk2cisxeTh2WGpURmNHMDUxbXVKenlwawpiRWN0cUNETC92TDRoeW9aak5vWTRhZHhkdUgwTSt0bGZvSVNNOTYyNHFpTTJPNWh6R01GdGNaVE5uSlhKV1dUCkI4UU5qZGI2MXRHQklhNVpRUVpYSzY2VUFDblByM2xpcFp1VHhhRmhEMEFaUTF3Mkpvd3VlaGFwb1o3cXNqcSsKSDlUblZmTlZCUGJJCi0tLS0tRU5EIENFUlRJRklDQVRFLS0tLS0K",
            "server": "https://10.220.50.158:6443"
          },
          "name": "cluster.local"
        }
      ],
      "contexts": [
        {
          "context": {
            "cluster": "cluster.local",
            "user": "kubernetes-admin"
          },
          "name": "kubernetes-admin@cluster.local"
        }
      ],
      "current-context": "kubernetes-admin@cluster.local",
      "kind": "Config",
      "preferences": {},
      "users": [
        {
          "name": "kubernetes-admin",
          "user": {
            "client-certificate-data": "LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSURJVENDQWdtZ0F3SUJBZ0lJSmthb24weUtRLzh3RFFZSktvWklodmNOQVFFTEJRQXdGVEVUTUJFR0ExVUUKQXhNS2EzVmlaWEp1WlhSbGN6QWVGdzB5TlRBM01Ea3dOREk0TlROYUZ3MHlOakEzTURrd05ETXpOVFJhTURReApGekFWQmdOVkJBb1REbk41YzNSbGJUcHRZWE4wWlhKek1Sa3dGd1lEVlFRREV4QnJkV0psY201bGRHVnpMV0ZrCmJXbHVNSUlCSWpBTkJna3Foa2lHOXcwQkFRRUZBQU9DQVE4QU1JSUJDZ0tDQVFFQTRFblppVmdKMjY5VHdveEoKVUdkTTltOWoxSlFQVTFJK0MzTGY3UHE3djMxTXBCUXhIeldIcWFZK29sN1NHTmtrQ1QwSDZpeDYzQ1hHVGlVRQpGcUdYRVFBczJhN2ZSZWRKVkpBNXp0K2l0eDBUenByZ09lMDJGSnQ5WWdVejQ3ak92UXNNOFpOUUNoVkZJTkMwCnlibjR1WlJ1OEp1TjFuM1VCNHpaaDNaY3V0YkQyWmV6T2dnWXZHVjZZeTZ4VVF5OTFEZVdnZG1Mam4yb3BDbGkKcnVtZTZad0pZRkloY3BqV0g5N2xqQ3hQbG9ZUHIxTmE0NlhNbmh3VXRpalQ2Z0VnQjZVTEdPNmZ1bVhuZ0xPYgp1R3pFZitiR0ZFejg5bllxUDZmTE9jV01SeXN3dXh6cVBnQUhGY2IxUWM4bmRWT0ZOMWJhaGJvUjlBYXpOVnFjCjdNb1V1d0lEQVFBQm8xWXdWREFPQmdOVkhROEJBZjhFQkFNQ0JhQXdFd1lEVlIwbEJBd3dDZ1lJS3dZQkJRVUgKQXdJd0RBWURWUjBUQVFIL0JBSXdBREFmQmdOVkhTTUVHREFXZ0JTVGFreFZITDJhVlBLd1QvMDVzZ0orRXBLRgpvakFOQmdrcWhraUc5dzBCQVFzRkFBT0NBUUVBTjRKZk9zSzBMeURXMzIySTFuZmh0R3ZhWnM0ZGZ6aTR1SGJPCldGOFhUVmVpNkZWQ3N6WklmWVNvSE14NUJ4M1R0NnZMMWdGaGljY3I1ZXdjV3dXR3orUUJ3ckpxZjJ6aUJvQTkKMy8zSGxUVlA2RmpvR3dlTmhjWlZSc1FRQ3VCb0tRSXl5bHlwMGJ3Rk1uOHpUYWJQcGRFdmQzN0l4QUltME1POApOdWtiL3ZLcFVYbDFJZVNzWGhvMVBMRjhhaU1idi9ZWlFGbEVUbUJVSDVraW4zNkxGZGNCcU9RU0JTWGdBTjd0CmdrTzVRTUVJM0pmQUZ3VHNkR1hGZGRJa2FKNjRuY2UxbVZucGNYcnFCZ1p6K2NESitpNGVHVk1OK3J5ckNBLysKTmE1T1lYc3h3Q0RhTEJTVi9tZVNNWms2SVBXK0hEUmhiazRiTDFrRGtOTURoUHlsNkE9PQotLS0tLUVORCBDRVJUSUZJQ0FURS0tLS0tCg==",
            "client-key-data": "LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlFcEFJQkFBS0NBUUVBNEVuWmlWZ0oyNjlUd294SlVHZE05bTlqMUpRUFUxSStDM0xmN1BxN3YzMU1wQlF4Ckh6V0hxYVkrb2w3U0dOa2tDVDBINml4NjNDWEdUaVVFRnFHWEVRQXMyYTdmUmVkSlZKQTV6dCtpdHgwVHpwcmcKT2UwMkZKdDlZZ1V6NDdqT3ZRc004Wk5RQ2hWRklOQzB5Ym40dVpSdThKdU4xbjNVQjR6WmgzWmN1dGJEMlplegpPZ2dZdkdWNll5NnhVUXk5MURlV2dkbUxqbjJvcENsaXJ1bWU2WndKWUZJaGNwaldIOTdsakN4UGxvWVByMU5hCjQ2WE1uaHdVdGlqVDZnRWdCNlVMR082ZnVtWG5nTE9idUd6RWYrYkdGRXo4OW5ZcVA2ZkxPY1dNUnlzd3V4enEKUGdBSEZjYjFRYzhuZFZPRk4xYmFoYm9SOUFhek5WcWM3TW9VdXdJREFRQUJBb0lCQUdGOCtBY1FzMGcvendKegpBN0xsRTdqUjlleUNacDdxMG5rYmQyV0VIbk0vUFQ3Y1gvV1d5TjdlbWI3dHhCaDAyWXNDY2h4Qk5TM1haWGkxCjhpNzhFYk9jQmVLZ2RmL21aaU5SaFM3OFdiZUo5Z0FKcFlqSUtJZVFobEZDdmFrdnZQekNmdC9LRGpJenlKWlkKNFJ3RnI2ektiZVk3VnMxeVorVFlQZno1WDVqOXpBaitVYno4THNSKzFkNzl6ZkFxRzlGbFhZa0gvOHEzb1Q5aApkTmNXMjgvQWpmeTNFem85YmQyMWVOYnhUV0ZVY2lNZDVzalQ2S0wxbEV2eElsVjlOUDVvbmJUbU81VmgrMzlMCjEzOURmaHJKMGUxWjJPYkpVaEJjQm5TRkJ0WnpEUVRiSG1KOHQvMVhxdFpxbTRlV1UvZUVIaTBZdlpLNHAwdE0KL2Vrb2JFRUNnWUVBNHVYVzh0UGxFSDMxRDhrMGszbStYZm5MVDVEb21EMC9EeUxXNzZWd1FQOHBoVzZtZ3pVdApTSzJ4V3RDcWw3aGtndlA2WlI1VmtqMW5xQytlRjNXVjd6Njc2NDg4ZzVzNGp4REFxdFNqbVk2dVZpOE4vaVY1CmM5c1NpV1JLRXN1REppdGh4a0l6d2luMzJ3WW9rV0MyK1dzM3lOZ1dqakEzVnFZMWRkdG1XUEVDZ1lFQS9RNVYKT2Q4c09CRGhGeXMrWS9UMllBbVRUc1l2bE9CN2cxRUZNanljc2ZTZC93am1vRjN5V3Nrb3BleEpRb0x2RVBmMApZVDlHNTR3RkFjUU5ubE0rU2E2UWpDenZEZkduVHE4ZFdoU0ZqbU54dXgrQVFYbXJNYVJIK3hEL2YxamcwemljCmJpV1RzNXBXVEtGdzVqQVBCbHlYOGZyS3NRSjI1UWpBdllyeGFHc0NnWUFINTIvTWQ3czBEdDg1bEkzRFVXdGoKUks5amJ5M2JGODhaak9JbDZRSjNFU3gySEh1cWVIRENabUtXUWt5ZkNtcGQ4WGZZaSt6NU1qQnBPSGR1WThjOApWVmdnaFpYYkU4NHRsYXpRaHFYSVZLTVlGMzJLUyszbUxreUFBc0ZkMUQ4V1ZrNktwSVcvRHMwMmtRbGF2eDdBCm80Nkc3WmdqamVSdm5VeWhkV29rVVFLQmdRRHA4VlV5OGpIa0J4N0FsNWJQTzhpRlVuVGZqM0t2bExRNjJ5ME4KbTJGVlZ3cTFtdG56Q2NjaXpQTUtLWjQwb2UwM1o3T0NMOGh5Q1UwYnE4N1hQcWZINEZ6N2FoTDZkaHd4THN6WQoyVDM3Tzg0SnF2NmNDVW9OMDQxRCt4dm85QmFzenBvM2JmL1ZPMnBxMzVrTEJRVHU0YTBLNU1wN3lBWjRpSlgrCjVMTjJ6d0tCZ1FDcWRjekJWc2QvS01RczE3VkZJbXhvbCtFeGs3WHg2YzlGSWpuYklPK2NLeGw3YkszTkR5bUQKak51YVBadDEzQ3JpZnNDRnhkUUxwSDR5Um5aUmtNV1AxcWgzWGMwejhHUTgvaXpnM2EvcFBEVlZlK3FST1J4OApwTThhZXI5eWRZc1VyUVBDQ3BkTW55NmZkSXhUa0NYVnRZb0ZyVkpNUEhGc2VMcURsRENDa0E9PQotLS0tLUVORCBSU0EgUFJJVkFURSBLRVktLS0tLQo="
          }
        }
      ]
    }
      """
#     kubeconfig_str = """
# apiVersion: v1
# clusters:
# - cluster:
#     certificate-authority-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSURCVENDQWUyZ0F3SUJBZ0lJT2puMW5zOTVydW93RFFZSktvWklodmNOQVFFTEJRQXdGVEVUTUJFR0ExVUUKQXhNS2EzVmlaWEp1WlhSbGN6QWVGdzB5TlRBM01Ea3dOREk0TlROYUZ3MHpOVEEzTURjd05ETXpOVE5hTUJVeApFekFSQmdOVkJBTVRDbXQxWW1WeWJtVjBaWE13Z2dFaU1BMEdDU3FHU0liM0RRRUJBUVVBQTRJQkR3QXdnZ0VLCkFvSUJBUURMcTNuSlZWRFBYQTJHNTlkT2xGazRObytZSmdoeW0wRVJaUjFCMEQ2cVoxRnNxMUs0NFJQR2tGTkkKZ21EUTlVV29mOENIRldmWno1aGlITEZMSnY0LzBLNGdkcjByRlczenlvUDJiRFJERDRlVnBMb3hHbXF4RXZKUgorK0F3ZGFicUp6bmY2bVVNK1VtekFWSFEzWFR2NENTbk9YK293eGg5VUdFYjFLV05iclNQcEY0Q2hQR2Rwd0tBCjVZNkkxMXhBN0RkOUp6Nnc5KzB0b0pBbHZuaTEydVF4eVAvUkZ4STU4aytsTUdVRDlZQXRHUHRKbWRnRGtDZkQKb2diTnByWFlDb2xEdmg3VGZIb0hZTGNkTEJCaFRtdmx6NTZOYzJkZE9mVm5sekNYMFh0TEtlSDBjYlBlVlI3VQoweVRWZE40bE9VVmRhamlEZ1huWmxCVm1FR09CQWdNQkFBR2pXVEJYTUE0R0ExVWREd0VCL3dRRUF3SUNwREFQCkJnTlZIUk1CQWY4RUJUQURBUUgvTUIwR0ExVWREZ1FXQkJTVGFreFZITDJhVlBLd1QvMDVzZ0orRXBLRm9qQVYKQmdOVkhSRUVEakFNZ2dwcmRXSmxjbTVsZEdWek1BMEdDU3FHU0liM0RRRUJDd1VBQTRJQkFRQnA1M3ZuSTA2bgpHcjFKTkpTYW92Tk1PWnFFaUVqWkYzdDh2a1c3TUNLcnRITEVCMUtBRHdjV3BzenZ2Q3pqTytVWW5OZE9GOWxiCjF4NFZyYlpaemlzTW9MdEtYVW9rVmd4aWlMK1NwYmxOSlBnQVJibnJPU0oxR2g1Y1pUZ0hySTQ2UXU0V0oxYXoKdHJvbXphQ1IwZThrQXE2c2RTbE9ReklJcm1QZnNLcG53V2ZRK2VhTkk2cisxeTh2WGpURmNHMDUxbXVKenlwawpiRWN0cUNETC92TDRoeW9aak5vWTRhZHhkdUgwTSt0bGZvSVNNOTYyNHFpTTJPNWh6R01GdGNaVE5uSlhKV1dUCkI4UU5qZGI2MXRHQklhNVpRUVpYSzY2VUFDblByM2xpcFp1VHhhRmhEMEFaUTF3Mkpvd3VlaGFwb1o3cXNqcSsKSDlUblZmTlZCUGJJCi0tLS0tRU5EIENFUlRJRklDQVRFLS0tLS0K
#     server: https://10.220.50.158:6443
#   name: cluster.local
# contexts:
# - context:
#     cluster: cluster.local
#     user: kubernetes-admin
#   name: kubernetes-admin@cluster.local
# current-context: kubernetes-admin@cluster.local
# kind: Config
# preferences: {}
# users:
# - name: kubernetes-admin
#   user:
#     client-certificate-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSURJVENDQWdtZ0F3SUJBZ0lJSmthb24weUtRLzh3RFFZSktvWklodmNOQVFFTEJRQXdGVEVUTUJFR0ExVUUKQXhNS2EzVmlaWEp1WlhSbGN6QWVGdzB5TlRBM01Ea3dOREk0TlROYUZ3MHlOakEzTURrd05ETXpOVFJhTURReApGekFWQmdOVkJBb1REbk41YzNSbGJUcHRZWE4wWlhKek1Sa3dGd1lEVlFRREV4QnJkV0psY201bGRHVnpMV0ZrCmJXbHVNSUlCSWpBTkJna3Foa2lHOXcwQkFRRUZBQU9DQVE4QU1JSUJDZ0tDQVFFQTRFblppVmdKMjY5VHdveEoKVUdkTTltOWoxSlFQVTFJK0MzTGY3UHE3djMxTXBCUXhIeldIcWFZK29sN1NHTmtrQ1QwSDZpeDYzQ1hHVGlVRQpGcUdYRVFBczJhN2ZSZWRKVkpBNXp0K2l0eDBUenByZ09lMDJGSnQ5WWdVejQ3ak92UXNNOFpOUUNoVkZJTkMwCnlibjR1WlJ1OEp1TjFuM1VCNHpaaDNaY3V0YkQyWmV6T2dnWXZHVjZZeTZ4VVF5OTFEZVdnZG1Mam4yb3BDbGkKcnVtZTZad0pZRkloY3BqV0g5N2xqQ3hQbG9ZUHIxTmE0NlhNbmh3VXRpalQ2Z0VnQjZVTEdPNmZ1bVhuZ0xPYgp1R3pFZitiR0ZFejg5bllxUDZmTE9jV01SeXN3dXh6cVBnQUhGY2IxUWM4bmRWT0ZOMWJhaGJvUjlBYXpOVnFjCjdNb1V1d0lEQVFBQm8xWXdWREFPQmdOVkhROEJBZjhFQkFNQ0JhQXdFd1lEVlIwbEJBd3dDZ1lJS3dZQkJRVUgKQXdJd0RBWURWUjBUQVFIL0JBSXdBREFmQmdOVkhTTUVHREFXZ0JTVGFreFZITDJhVlBLd1QvMDVzZ0orRXBLRgpvakFOQmdrcWhraUc5dzBCQVFzRkFBT0NBUUVBTjRKZk9zSzBMeURXMzIySTFuZmh0R3ZhWnM0ZGZ6aTR1SGJPCldGOFhUVmVpNkZWQ3N6WklmWVNvSE14NUJ4M1R0NnZMMWdGaGljY3I1ZXdjV3dXR3orUUJ3ckpxZjJ6aUJvQTkKMy8zSGxUVlA2RmpvR3dlTmhjWlZSc1FRQ3VCb0tRSXl5bHlwMGJ3Rk1uOHpUYWJQcGRFdmQzN0l4QUltME1POApOdWtiL3ZLcFVYbDFJZVNzWGhvMVBMRjhhaU1idi9ZWlFGbEVUbUJVSDVraW4zNkxGZGNCcU9RU0JTWGdBTjd0CmdrTzVRTUVJM0pmQUZ3VHNkR1hGZGRJa2FKNjRuY2UxbVZucGNYcnFCZ1p6K2NESitpNGVHVk1OK3J5ckNBLysKTmE1T1lYc3h3Q0RhTEJTVi9tZVNNWms2SVBXK0hEUmhiazRiTDFrRGtOTURoUHlsNkE9PQotLS0tLUVORCBDRVJUSUZJQ0FURS0tLS0tCg==
#     client-key-data: LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlFcEFJQkFBS0NBUUVBNEVuWmlWZ0oyNjlUd294SlVHZE05bTlqMUpRUFUxSStDM0xmN1BxN3YzMU1wQlF4Ckh6V0hxYVkrb2w3U0dOa2tDVDBINml4NjNDWEdUaVVFRnFHWEVRQXMyYTdmUmVkSlZKQTV6dCtpdHgwVHpwcmcKT2UwMkZKdDlZZ1V6NDdqT3ZRc004Wk5RQ2hWRklOQzB5Ym40dVpSdThKdU4xbjNVQjR6WmgzWmN1dGJEMlplegpPZ2dZdkdWNll5NnhVUXk5MURlV2dkbUxqbjJvcENsaXJ1bWU2WndKWUZJaGNwaldIOTdsakN4UGxvWVByMU5hCjQ2WE1uaHdVdGlqVDZnRWdCNlVMR082ZnVtWG5nTE9idUd6RWYrYkdGRXo4OW5ZcVA2ZkxPY1dNUnlzd3V4enEKUGdBSEZjYjFRYzhuZFZPRk4xYmFoYm9SOUFhek5WcWM3TW9VdXdJREFRQUJBb0lCQUdGOCtBY1FzMGcvendKegpBN0xsRTdqUjlleUNacDdxMG5rYmQyV0VIbk0vUFQ3Y1gvV1d5TjdlbWI3dHhCaDAyWXNDY2h4Qk5TM1haWGkxCjhpNzhFYk9jQmVLZ2RmL21aaU5SaFM3OFdiZUo5Z0FKcFlqSUtJZVFobEZDdmFrdnZQekNmdC9LRGpJenlKWlkKNFJ3RnI2ektiZVk3VnMxeVorVFlQZno1WDVqOXpBaitVYno4THNSKzFkNzl6ZkFxRzlGbFhZa0gvOHEzb1Q5aApkTmNXMjgvQWpmeTNFem85YmQyMWVOYnhUV0ZVY2lNZDVzalQ2S0wxbEV2eElsVjlOUDVvbmJUbU81VmgrMzlMCjEzOURmaHJKMGUxWjJPYkpVaEJjQm5TRkJ0WnpEUVRiSG1KOHQvMVhxdFpxbTRlV1UvZUVIaTBZdlpLNHAwdE0KL2Vrb2JFRUNnWUVBNHVYVzh0UGxFSDMxRDhrMGszbStYZm5MVDVEb21EMC9EeUxXNzZWd1FQOHBoVzZtZ3pVdApTSzJ4V3RDcWw3aGtndlA2WlI1VmtqMW5xQytlRjNXVjd6Njc2NDg4ZzVzNGp4REFxdFNqbVk2dVZpOE4vaVY1CmM5c1NpV1JLRXN1REppdGh4a0l6d2luMzJ3WW9rV0MyK1dzM3lOZ1dqakEzVnFZMWRkdG1XUEVDZ1lFQS9RNVYKT2Q4c09CRGhGeXMrWS9UMllBbVRUc1l2bE9CN2cxRUZNanljc2ZTZC93am1vRjN5V3Nrb3BleEpRb0x2RVBmMApZVDlHNTR3RkFjUU5ubE0rU2E2UWpDenZEZkduVHE4ZFdoU0ZqbU54dXgrQVFYbXJNYVJIK3hEL2YxamcwemljCmJpV1RzNXBXVEtGdzVqQVBCbHlYOGZyS3NRSjI1UWpBdllyeGFHc0NnWUFINTIvTWQ3czBEdDg1bEkzRFVXdGoKUks5amJ5M2JGODhaak9JbDZRSjNFU3gySEh1cWVIRENabUtXUWt5ZkNtcGQ4WGZZaSt6NU1qQnBPSGR1WThjOApWVmdnaFpYYkU4NHRsYXpRaHFYSVZLTVlGMzJLUyszbUxreUFBc0ZkMUQ4V1ZrNktwSVcvRHMwMmtRbGF2eDdBCm80Nkc3WmdqamVSdm5VeWhkV29rVVFLQmdRRHA4VlV5OGpIa0J4N0FsNWJQTzhpRlVuVGZqM0t2bExRNjJ5ME4KbTJGVlZ3cTFtdG56Q2NjaXpQTUtLWjQwb2UwM1o3T0NMOGh5Q1UwYnE4N1hQcWZINEZ6N2FoTDZkaHd4THN6WQoyVDM3Tzg0SnF2NmNDVW9OMDQxRCt4dm85QmFzenBvM2JmL1ZPMnBxMzVrTEJRVHU0YTBLNU1wN3lBWjRpSlgrCjVMTjJ6d0tCZ1FDcWRjekJWc2QvS01RczE3VkZJbXhvbCtFeGs3WHg2YzlGSWpuYklPK2NLeGw3YkszTkR5bUQKak51YVBadDEzQ3JpZnNDRnhkUUxwSDR5Um5aUmtNV1AxcWgzWGMwejhHUTgvaXpnM2EvcFBEVlZlK3FST1J4OApwTThhZXI5eWRZc1VyUVBDQ3BkTW55NmZkSXhUa0NYVnRZb0ZyVkpNUEhGc2VMcURsRENDa0E9PQotLS0tLUVORCBSU0EgUFJJVkFURSBLRVktLS0tLQo=
#     """
#     ai_k8s_kubeconfig = AiK8sKubeConfigConfigs(id=uuid.uuid4().__str__(), k8s_cluster_id='test_k8s_158', kubeconfig=kubeconfig_str)
#     AiInstanceSQL.create_ai_k8s_kubeconfig_configs(ai_k8s_kubeconfig)
#     core_k8s_client = get_k8s_client('test_wwb-2', client.CoreV1Api)
    core_k8s_client = get_k8s_client('test-cluster-1', client.CoreV1Api)
#     core_k8s_client = get_k8s_client('test_wwb-2', client.CoreV1Api)
    print("======0=====")
    try:
        node = core_k8s_client.list_node()
        print(node)
    except Exception as e:
        print(f"list_node 查询出错：{e}")
    print("======1=====")
