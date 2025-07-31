# k8s的client

from kubernetes import client, config


def get_k8s_client(config_file: str, context: str):
    """检测"""
    if not config_file or not context:
        raise ValueError(f"Invalid param config_file: {config_file}, context: {context}")
    """加载配置"""
    config.load_kube_config(
        config_file=config_file,
        context=context,
    )
    """返回api"""
    return client.CoreV1Api()
