# 数据表对应的model对象

from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class AiK8sKubeConfigConfigs(Base):
    __tablename__ = "ops_ai_k8s_kubeconfig_configs"

    id = Column(String(length=128), primary_key= True, nullable=False, index=True, unique=False)
    k8s_cluster_id = Column(String(length=128), nullable=True)
    kubeconfig_path = Column(String(length=255), nullable=True)
    kubeconfig_context_name = Column(String(length=128), nullable=True)
    kubeconfig = Column(Text, nullable=False)
    create_time = Column(DateTime, nullable=True)
    update_time = Column(DateTime, nullable=True)
