# 数据表对应的model对象

from __future__ import annotations

from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# 外部消息
class ExternalMessage(Base):
    __tablename__ = "ops_external_message"

    id = Column(String(length=128), primary_key= True, nullable=False, index=True, unique=False)
    message_type = Column(String(length=128), nullable=True)
    region_name = Column(String(length=128), nullable=True)
    az_name = Column(String(length=128), nullable=True)
    message_status = Column(String(length=40), nullable=True)
    message_data = Column(Text)
    message_description = Column(Text)
    create_date = Column(DateTime, nullable=True)
    update_date = Column(DateTime, nullable=True)

