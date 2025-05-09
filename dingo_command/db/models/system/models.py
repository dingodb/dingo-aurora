# 数据表对应的model对象

from __future__ import annotations

from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# 操作日志对象
class OperateLog(Base):
    __tablename__ = "ops_operate_log"

    id = Column(String(length=128), primary_key= True, nullable=False, index=True, unique=False)
    log_date = Column(DateTime)
    user_id = Column(String(length=128), nullable=True)
    user_name = Column(String(length=128), nullable=True)
    ip = Column(String(length=128), nullable=True)
    operate_type = Column(String(length=128), nullable=True)
    resource_type = Column(String(length=128), nullable=True)
    resource_type_name = Column(String(length=128), nullable=True)
    resource_id = Column(String(length=128), nullable=True)
    resource_name = Column(String(length=128), nullable=True)
    operate_flag = Column(Boolean, nullable=True, default=False)
    description = Column(String(length=255), nullable=True)
