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
