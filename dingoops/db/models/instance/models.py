# 数据表对应的model对象

from __future__ import annotations

from sqlalchemy import JSON, Column, MetaData, String, Table, Text, DateTime, Integer, Boolean
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
    openstack_id = Column(String(length=128), nullable=False)
    ip_address = Column(String(length=128), default=0, nullable= False)
    operation_system = Column(String(length=128), default=0, nullable= False)
    floating_ip = Column(String(length=128), default=0, nullable= True)
    security_group = Column(String(length=128), default=0, nullable= True)
    flavor_id = Column(String(length=128), default=0, nullable= True)
    node_type = Column(String(length=128), default=0, nullable= False)
    region = Column(String(length=128), default=0, nullable= False)
    status = Column(String(length=128), default=0, nullable= False)
    user = Column(String(length=128), default=0, nullable= False)
    password = Column(String(length=128), default=0, nullable= False)
    cpu = Column(String(length=128), default=0, nullable= False)
    gpu = Column(String(length=128), default=0, nullable= False)
    mem = Column(String(length=128), default=0, nullable= False)
    disk = Column(String(length=128), default=0, nullable= False)
    create_time = Column(DateTime, nullable=True)
    update_time = Column(DateTime, nullable=True)
    description = Column(String(length=255), nullable=True)
    extra = Column(String(length=255), nullable=True)
