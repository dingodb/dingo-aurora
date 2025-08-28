# 数据表对应的model对象

from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Text, Boolean, text, Integer
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class AiK8sKubeConfigConfigs(Base):
    __tablename__ = "ops_ai_k8s_kubeconfig_configs"

    id = Column(String(length=128), primary_key= True, nullable=False, index=True, unique=True)
    k8s_id = Column(String(length=128), nullable=True, index=True, unique=True)
    k8s_name = Column(String(length=128), nullable=True)
    k8s_type = Column(String(length=128), nullable=True)
    kubeconfig_path = Column(String(length=255), nullable=True)
    kubeconfig_context_name = Column(String(length=128), nullable=True)
    kubeconfig = Column(Text, nullable=False)
    create_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    update_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))

class AiInstanceInfo(Base):
    __tablename__ = "ops_ai_instance_info"

    id = Column(String(length=128), nullable=False, primary_key=True, unique=True)
    instance_name = Column(String(length=128), nullable=True)
    instance_real_name = Column(String(length=128), nullable=True)
    instance_node_name = Column(String(length=128), nullable=True)
    instance_status = Column(String(length=128), nullable=True)
    instance_real_status = Column(String(length=128), nullable=True)
    instance_k8s_type = Column(String(length=128), nullable=True)
    instance_k8s_id = Column(String(length=128), nullable=True)
    instance_k8s_name = Column(String(length=128), nullable=True)
    instance_project_id = Column(String(length=128), nullable=True)
    instance_project_name = Column(String(length=128), nullable=True)
    instance_user_id = Column(String(length=128), nullable=True)
    instance_user_name = Column(String(length=128), nullable=True)
    instance_root_account_id = Column(String(length=128), nullable=True)
    instance_root_account_name = Column(String(length=128), nullable=True)
    instance_image = Column(String(length=128), nullable=True)
    image_type = Column(String(length=128), nullable=True)
    stop_time = Column(DateTime, nullable=True)
    auto_delete_time = Column(DateTime, nullable=True)
    instance_config = Column(Text, nullable=True)
    instance_volumes = Column(Text, nullable=True)
    instance_envs = Column(Text, nullable=True)
    instance_description = Column(Text, nullable=True)
    # data_set = Column(Text)
    instance_create_time = Column(DateTime, nullable=True)
    create_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    update_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))
    error_msg = Column(Text, nullable=True)

class AiK8sNodeResourceInfo(Base):
    __tablename__ = "ops_ai_k8s_node_resource"

    id = Column(String(length=128), nullable=False, primary_key=True, unique=True)
    k8s_id = Column(String(length=128), nullable=True, index=True, unique=True)
    node_name = Column(String(length=128), nullable=True)
    less_gpu_pod_count = Column(Integer, nullable=True, default=0)
    gpu_model = Column(String, nullable=True)
    gpu_total = Column(String, nullable=True)
    gpu_used = Column(String, nullable=True)
    cpu_total = Column(String, nullable=True)
    cpu_used = Column(String, nullable=True)
    memory_total = Column(String, nullable=True)
    memory_used = Column(String, nullable=True)
    storage_total = Column(String, nullable=True)
    storage_used = Column(String, nullable=True)
    update_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))

class AccountInfo(Base):
    __tablename__ = "ops_account_info"

    id = Column(String(length=128), primary_key=True, nullable=False, index=True, unique=True)
    account = Column(String(length=128), nullable=False, index=True, unique=True, comment="账户账号")
    is_vip = Column(Boolean, nullable=False, default=False, comment="是否是VIP账户")
    create_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间")
    update_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="更新时间")
