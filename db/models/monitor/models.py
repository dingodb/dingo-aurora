# 数据表对应的model对象

from __future__ import annotations

from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# 资产对象
class MonitorUrlConfig(Base):
    __tablename__ = "ops_monitor_url_config_info"

    id = Column(String(length=128), primary_key= True, nullable=False, index=True, unique=False)
    name = Column(String(length=128), nullable=True)
    url = Column(String(length=128), nullable=True)
    url_catalog = Column(String(length=40), nullable=True)
    url_type = Column(String(length=40), nullable=True)
    user_id = Column(String(length=128), nullable=True)
    user_account = Column(String(length=128), nullable=True)
    create_date = Column(DateTime, nullable=True)
    description = Column(String(length=255), nullable=True)
