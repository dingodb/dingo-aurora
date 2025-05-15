# 数据表对应的model对象

from __future__ import annotations

from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# 节点对象
class NodeInfo(Base):
    __tablename__ = "ops_node_info"

    id = Column(String(length=128), primary_key= True, nullable=False, index=True, unique=False)
    cluster_id = Column(String(length=128), nullable=False)
    cluster_name = Column(String(length=128), nullable=False)
    project_id = Column(String(length=128), nullable=True)
    name = Column(String(length=128), nullable=True)
    openstack_id = Column(String(length=128), nullable=True)
    server_id = Column(String(length=128), nullable=True)
    instance_id = Column(String(length=128), nullable=True)
    admin_address = Column(String(length=128), default=0, nullable= False)
    bus_address = Column(String(length=128), default=0, nullable= False)
    floating_ip = Column(String(length=128), default=0, nullable= True)
    role = Column(String(length=128), default=0, nullable= False)
    node_type = Column(String(length=128), default=0, nullable= False)
    region = Column(String(length=128), default=0, nullable= False)
    image = Column(String(length=128), default=0, nullable= False)
    status = Column(String(length=128), default=0, nullable= False)
    flavor_id = Column(String(length=128), default=0, nullable= True)
    security_group = Column(String(length=128), default=0, nullable= True)
    private_key = Column(Text, nullable=True)
    auth_type = Column(String(length=128), default=0, nullable= True)
    user = Column(String(length=128), default=0, nullable= False)
    password = Column(String(length=128), default=0, nullable= False)
    create_time = Column(DateTime, nullable=True)
    update_time = Column(DateTime, nullable=True)
    description = Column(String(length=255), nullable=True)
    extra = Column(Text, nullable=True)
