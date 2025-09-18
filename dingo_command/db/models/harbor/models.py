# 数据表对应的model对象

from __future__ import annotations

from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# 集群对象
class TenantHarborRelation(Base):
    __tablename__ = "ops_tenant_harbor_relation_info"

    id = Column(String(length=128), primary_key= True, nullable=False, index=True, unique=False)
    harbor_name = Column(String(length=128), nullable=True)
    harbor_password = Column(String(length=128), nullable=True)
    tenant_id = Column(String(length=128), nullable=True)
    create_time = Column(DateTime, nullable=True)
    update_time = Column(DateTime, nullable=True)
    description = Column(String(length=255), nullable=True)
