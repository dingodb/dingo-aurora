# 数据表对应的model对象

from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Text, Boolean, text, Integer
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class AiK8sConfigs(Base):
    __tablename__ = "ops_ai_k8s_configs"

    id = Column(String(length=128), primary_key= True, nullable=False, index=True, unique=True)
    k8s_id = Column(String(length=128), nullable=True, index=True, unique=True)
    k8s_type = Column(String(length=128), nullable=True)
    public_ip = Column(String(length=128), nullable=True)
    metallb_ip = Column(String(length=128), nullable=True)
    dns_suffix = Column(String(length=128), nullable=True)
    kubeconfig_path = Column(String(length=255), nullable=True)
    kubeconfig_context_name = Column(String(length=128), nullable=True)
    kubeconfig = Column(Text, nullable=False)
    harbor_address = Column(String(length=128), nullable=True)
    harbor_username = Column(String(length=128), nullable=True)
    harbor_password = Column(String(length=128), nullable=True)
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
    instance_region_id = Column(String(length=128), nullable=True)
    instance_k8s_id = Column(String(length=128), nullable=True)
    instance_user_id = Column(String(length=128), nullable=True)
    is_manager = Column(Boolean, nullable=True)
    instance_tenant_id = Column(String(length=128), nullable=True)
    instance_image = Column(String(length=128), nullable=True)
    stop_time = Column(DateTime, nullable=True)
    auto_delete_time = Column(DateTime, nullable=True)
    instance_config = Column(Text, nullable=True)
    instance_volumes = Column(Text, nullable=True)
    instance_envs = Column(Text, nullable=True)
    ssh_root_password = Column(String(length=255), nullable=True)
    product_code = Column(String(length=255), nullable=True)
    instance_description = Column(Text, nullable=True)
    # data_set = Column(Text)
    instance_start_time = Column(DateTime, nullable=True)
    create_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    update_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))
    error_msg = Column(Text, nullable=True)

class AiK8sNodeResourceInfo(Base):
    __tablename__ = "ops_ai_k8s_node_resource"

    id = Column(String(length=128), nullable=False, primary_key=True, unique=True)
    k8s_id = Column(String(length=128), nullable=True, index=True, unique=True)
    node_name = Column(String(length=128), nullable=True)
    node_ip = Column(String(length=128), nullable=True)
    less_gpu_pod_total = Column(Integer, nullable=True, server_default='20')
    less_gpu_pod_count = Column(Integer, nullable=True, server_default='0')
    gpu_pod_count = Column(Integer, nullable=True, server_default='0')
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
    __tablename__ = "ops_account_vip_info"

    id = Column(String(length=128), primary_key=True, nullable=False, index=True, unique=True)
    account = Column(String(length=128), nullable=True, comment="账户账号")
    vip = Column(String(length=128), nullable=True, comment="VIP")
    metallb_ip = Column(String(length=128), nullable=True)
    create_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间")
    update_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="更新时间")

class AiInstancePortsInfo(Base):
    __tablename__ = "ops_ai_instance_ports_info"

    id = Column(String(length=128), primary_key=True, nullable=False, index=True, unique=True)
    instance_id = Column(String(length=128), nullable=True, comment="容器实例的id")
    instance_svc_port = Column(Integer, nullable=True, comment="容器实例的服务的port")
    instance_svc_target_port = Column(Integer, nullable=True, comment="容器实例的服务的target port")
    create_time = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间")
    update_time = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="更新时间")

class AiInstanceGpuCardInfo(Base):
    __tablename__ = "ops_ai_instance_gpu_card_info"

    id = Column(String(length=128), primary_key=True, nullable=False, index=True, unique=True)
    gpu_model_display = Column(String(length=255), nullable=True, comment="页面展示GPU卡型号")
    gpu_node_label = Column(String(length=255), nullable=True, comment="Node上GPU卡标签")
    gpu_key = Column(String(length=255), nullable=True, comment="Pod可使用的GPU key值")
    update_time = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="更新时间")
