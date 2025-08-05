from __future__ import annotations
from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# repo对象
class RepoInfo(Base):
    __tablename__ = "ops_chart_repo_info"

    id = Column(Integer, primary_key= True, nullable=False, index=True, unique=False)
    name = Column(String(length=128), nullable=False)
    is_global = Column(Boolean, nullable=False)
    type = Column(String(length=128), nullable=True)
    description = Column(String(length=256), nullable=True)
    url = Column(String(length=256), nullable=True)
    username = Column(String(length=256), nullable=True)
    password = Column(String(length=256), nullable= True)
    create_time = Column(DateTime, nullable= True)
    update_time = Column(DateTime, nullable= True)
    status = Column(String(length=128), nullable= True)
    cluster_id = Column(String(length=256), nullable= True)
    extra = Column(Text, nullable=True)

    charts = relationship(
        "ChartInfo",
        back_populates="repo",
        cascade="all, delete-orphan",
        passive_deletes=True
    )


# chart对象
class ChartInfo(Base):
    __tablename__ = "ops_chart_info"

    id = Column(Integer, primary_key= True, nullable=False, index=True, unique=False)
    name = Column(String(length=128), nullable=False)
    cluster_id = Column(String(length=256), nullable=False)
    repo_id = Column(Integer, ForeignKey("ops_chart_repo_info.id", ondelete="CASCADE"), nullable=False)
    icon = Column(String(length=256), nullable=True)
    description = Column(String(length=256), nullable=True)
    repo_name = Column(String(length=128), nullable=True)
    type = Column(String(length=128), nullable=True)
    tag_name = Column(Integer, nullable=True)
    index_content = Column(Text, nullable=True)
    chart_content = Column(Text, nullable=True)
    extra = Column(Text, nullable=True)

    repo = relationship("RepoInfo", back_populates="charts")  # 双向关联


# app对象
class AppInfo(Base):
    __tablename__ = "ops_chart_app_info"

    id = Column(Integer, primary_key=True, nullable=False, index=True, unique=False)
    name = Column(String(length=128), nullable=False)
    cluster_id = Column(String(length=256), nullable=False)
    repo_id = Column(Integer, nullable=True)
    status = Column(String(length=128), nullable=True)
    namespace = Column(String(length=128), nullable=True)
    description = Column(String(length=256), nullable=True)
    repo_name = Column(String(length=128), nullable=True)
    create_time = Column(DateTime, nullable=True)
    update_time = Column(DateTime, nullable=True)
    type = Column(String(length=128), nullable=True)
    tag_name = Column(Integer, nullable=True)
    extra = Column(Text, nullable=True)


# tag对象
class TagInfo(Base):
    __tablename__ = "ops_chart_tag_info"

    id = Column(Integer, primary_key= True, nullable=False, index=True, unique=False)
    name = Column(String(length=128), nullable=False)
    type = Column(String(length=128), nullable=False)
    extra = Column(Text, nullable=True)