# 数据表对应的model对象

from __future__ import annotations

from sqlalchemy import JSON, Column, MetaData, String, Table, Text, DateTime, Integer, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# 资产资源关联信息对象
class AssetResourceRelationInfo(Base):
    __tablename__ = "ops_assets_resources_relations_info"

    id = Column(String(length=128), primary_key= True, nullable=False, index=True, unique=False)
    asset_id = Column(String(length=128), nullable=True)
    resource_id = Column(String(length=128), nullable=True)
    resource_type = Column(String(length=128), nullable=True)
    resource_name = Column(String(length=128), nullable=True)
    resource_status = Column(String(length=128), nullable=True)
    resource_project_id = Column(String(length=128), nullable=True)
    resource_project_name = Column(String(length=128), nullable=True)
    resource_user_id = Column(String(length=128), nullable=True)
    resource_user_name = Column(String(length=128), nullable=True)
    resource_ip = Column(String(length=256), nullable=True)
    resource_description = Column(String(length=255), nullable=True)
    resource_extra = Column(Text)
    create_date = Column(DateTime, nullable=True)
    update_date = Column(DateTime, nullable=True)


# 资源指标配置信息对象
class ResourceMetricsConfig(Base):
    __tablename__ = "ops_resource_metrics_configs"

    id = Column(String(length=128), primary_key=True, nullable=False, index=True, unique=False)
    name = Column(String(length=128), nullable=False, index=True, unique=True)
    query = Column(String(length=512), nullable=False)
    description = Column(String(length=255), nullable=True)
    sub_class = Column(String(length=128), nullable=True)
    unit = Column(String(length=32), nullable=True)
    extra = Column(Text)
    metrics = relationship("ResourceMetrics", back_populates="config", cascade="all, delete-orphan")

class ResourceMetrics(Base):
    __tablename__ = "ops_resource_metrics"

    id = Column(String(length=128), primary_key=True, nullable=False, index=True, unique=False)
    resource_id = Column(String(length=128), nullable=False)
    name = Column(String, ForeignKey("ops_resource_metrics_configs.name"), nullable=False)
    data = Column(Text, nullable=True)
    region = Column(String(length=128), nullable=True)
    last_modified = Column(DateTime, nullable=True)
    config = relationship("ResourceMetricsConfig", back_populates="metrics")
