from __future__ import annotations
from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.mysql import LONGTEXT

Base = declarative_base()


# repo对象
class KeyInfo(Base):
    __tablename__ = "ops_sshkey_info"

    id = Column(String(length=256), primary_key= True, nullable=False, index=True, unique=True)
    name = Column(String(length=256), nullable=False)
    tenant_id = Column(String(length=256), nullable=True)
    description = Column(String(length=256), nullable=True)
    create_time = Column(DateTime, nullable= True)
    update_time = Column(DateTime, nullable= True)
    status = Column(String(length=256), nullable= True)
    status_msg = Column(LONGTEXT, nullable=True)
    key_content = Column(LONGTEXT, nullable=True)
    user_id = Column(String(length=256), nullable= True)
    user_name = Column(String(length=256), nullable= True)
    namespace = Column(String(length=256), nullable= True)
    configmap_name = Column(String(length=256), nullable= True)
    extra = Column(LONGTEXT, nullable=True)