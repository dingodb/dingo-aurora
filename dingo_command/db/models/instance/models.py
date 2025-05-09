# 数据表对应的model对象

from __future__ import annotations

from sqlalchemy import Column, String, DateTime, Integer
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# 节点对象
class Instance(Base):
    __tablename__ = "ops_instance_info"

    id = Column(String(length=128), primary_key= True, nullable=False, index=True, unique=False)
    cluster_id = Column(String(length=128), nullable=True)
    cluster_name = Column(String(length=128), nullable=True)
    project_id = Column(String(length=128), nullable=False)
    server_id = Column(String(length=128), nullable=False)
    name = Column(String(length=128), nullable=True)
    openstack_id = Column(String(length=128), nullable=True)
    ip_address = Column(String(length=128), default=0, nullable= False)
    operation_system = Column(String(length=128), default=0, nullable= False)
    floating_ip = Column(String(length=128), default=0, nullable= True)
    security_group = Column(String(length=128), default=0, nullable= True)
    flavor_id = Column(String(length=128), default=0, nullable= True)
    image_id = Column(String(length=128), default=0, nullable= True)
    network_id = Column(String(length=128), default=0, nullable= True)
    subnet_id = Column(String(length=128), default=0, nullable= True)
    sshkey_name = Column(String(length=128), default=0, nullable= True)
    node_type = Column(String(length=128), default=0, nullable= False)
    region = Column(String(length=128), default=0, nullable= False)
    status = Column(String(length=128), default=0, nullable= False)
    user = Column(String(length=128), default=0, nullable= False)
    password = Column(String(length=128), default=0, nullable= False)
    cpu = Column(Integer, nullable=True)
    gpu = Column(Integer, nullable=True)
    mem = Column(Integer, nullable=True)
    disk = Column(Integer, nullable=True)
    create_time = Column(DateTime, nullable=True)
    update_time = Column(DateTime, nullable=True)
    description = Column(String(length=255), nullable=True)
    extra = Column(String(length=255), nullable=True)
