# 数据表对应的model对象

from __future__ import annotations

from dingo_command.db.engines.mysql import get_session
from dingo_command.db.models.ai_instance.models import AiK8sKubeConfigConfigs

class AiInstanceSQL:

    @classmethod
    def get_ai_k8s_kubeconfig_configs(cls, k8s_id):
        session = get_session()
        with session.begin():
            return session.query(AiK8sKubeConfigConfigs).filter(AiK8sKubeConfigConfigs.k8s_cluster_id == k8s_id).first()

    @classmethod
    def create_ai_k8s_kubeconfig_configs(cls, kubeconfig_configs):
        session = get_session()
        with session.begin():
            session.add(kubeconfig_configs)