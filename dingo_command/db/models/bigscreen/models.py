# 数据表对应的model对象

from __future__ import annotations

from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# 大屏指标配置信息对象
class BigscreenMetricsConfig(Base):
    __tablename__ = "ops_bigscreen_metrics_configs"

    id = Column(String(length=128), primary_key=True, nullable=False, index=True, unique=False)
    name = Column(String(length=128), nullable=False, index=True, unique=True)
    query = Column(String(length=511), nullable=False)
    description = Column(String(length=255), nullable=True)
    sub_class = Column(String(length=128), nullable=True)
    unit = Column(String(length=32), nullable=True)
    extra = Column(Text)
    metrics = relationship("BigscreenMetrics", back_populates="config", cascade="all, delete-orphan")

class BigscreenMetrics(Base):
    __tablename__ = "ops_bigscreen_metrics"

    id = Column(String(length=128), primary_key=True, nullable=False, index=True, unique=False)

    name = Column(String, ForeignKey("ops_bigscreen_metrics_configs.name"), nullable=False)
    data = Column(Text, nullable=True)

    region = Column(String(length=128), nullable=True)
    last_modified = Column(DateTime, nullable=True)

    config = relationship("BigscreenMetricsConfig", back_populates="metrics")

