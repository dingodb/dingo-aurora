# 数据表对应的model对象

from __future__ import annotations

from sqlalchemy import JSON, Column, MetaData, String, Table, Text, DateTime, Integer, Boolean
from sqlalchemy.orm import declarative_base

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


