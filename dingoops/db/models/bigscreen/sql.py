# 数据表对应的model对象

from __future__ import annotations

from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from typing_extensions import assert_type

from dingoops.db.engines.mysql import get_session
from dingoops.db.models.bigscreen.models import BigscreenMetricsConfig, BigscreenMetrics

from datetime import datetime
from enum import Enum

#链接数据库，可以使用配置文件进行定义
# engine = create_engine("mysql+pymysql://root:HworLIIDvmTRsPfQauNskuJF8PcoTuULfu3dEHFg@10.220.56.254:3306/dingoops?charset=utf8mb3", echo=True)

class BigscreenSQL:
    # 数据库操作添加
    @classmethod
    def create_bigscreen_metrics_config(cls, bigscreen_metrics_config_info):
        session = get_session()
        with session.begin():
            session.add(bigscreen_metrics_config_info)

    @classmethod
    def update_bigscreen_metrics_config(cls, bigscreen_metrics_config_info):
        session = get_session()
        with session.begin():
            session.merge(bigscreen_metrics_config_info)

    @classmethod
    def delete_bigscreen_metrics_config(cls, bigscreen_metrics_config_id):
        session = get_session()
        with session.begin():
            session.query(BigscreenMetricsConfig).filter(BigscreenMetricsConfig.id == bigscreen_metrics_config_id).delete()

    @classmethod
    def get_bigscreen_metrics_config_by_id(cls, bigscreen_metrics_config_id):
        session = get_session()
        with session.begin():
            return session.query(BigscreenMetricsConfig).filter(BigscreenMetricsConfig.id == bigscreen_metrics_config_id).first()
 
    @classmethod
    def get_bigscreen_metrics_config_by_name(cls, bigscreen_metrics_config_name):
        session = get_session()
        with session.begin():
            return session.query(BigscreenMetricsConfig).filter(BigscreenMetricsConfig.name == bigscreen_metrics_config_name).first()

    @classmethod
    def get_bigscreen_metrics_configs(cls):
        session = get_session()
        with session.begin():
            return session.query(BigscreenMetricsConfig).all()

    @classmethod
    def get_bigscreen_metrics_config_by_sub_class(cls, bigscreen_metrics_config_sub_class):
        session = get_session()
        with session.begin():
            return session.query(BigscreenMetricsConfig).filter(BigscreenMetricsConfig.sub_class == bigscreen_metrics_config_sub_class)

    @classmethod
    def create_bigscreen_metrics(cls, bigscreen_metrics_info):
        session = get_session()
        with session.begin():
            session.add(bigscreen_metrics_info)

    @classmethod
    def get_bigscreen_metrics_by_name(cls, bigscreen_metrics_name):
        session = get_session()
        with session.begin():
            return session.query(BigscreenMetrics).filter(BigscreenMetrics.name == bigscreen_metrics_name).first()

    @classmethod
    def get_bigscreen_metrics_by_name_and_region(cls, bigscreen_metrics_name, bigscreen_metrics_region):
        session = get_session()
        with session.begin():
            return session.query(BigscreenMetrics).filter(
                BigscreenMetrics.name == bigscreen_metrics_name,
                BigscreenMetrics.region == bigscreen_metrics_region
            ).first()

    @classmethod
    def update_bigscreen_metrics(cls, bigscreen_metrics_info):
        session = get_session()
        with session.begin():
            session.merge(bigscreen_metrics_info)

    @classmethod
    def update_bigscreen_metrics_data_by_name(cls, name, data):
        session = get_session()
        with session.begin():
            metrics = cls.get_bigscreen_metrics_by_name(name)
            metrics.data = data
            metrics.last_modified = datetime.fromtimestamp(datetime.now().timestamp())
            session.merge(metrics)

    @classmethod
    def delete_bigscreen_metrics(cls, bigscreen_metrics_id):
        session = get_session()
        with session.begin():
            session.query(BigscreenMetrics).filter(BigscreenMetrics.id == bigscreen_metrics_id).delete()

    @classmethod
    def get_bigscreen_metrics_by_id(cls, bigscreen_metrics_id):
        session = get_session()
        with session.begin():
            return session.query(BigscreenMetrics).filter(BigscreenMetrics.id == bigscreen_metrics_id).first()

    @classmethod
    def get_bigscreen_metrics(cls):
        session = get_session()
        with session.begin():
            return session.query(BigscreenMetrics).all()

    @classmethod
    def get_bigscreen_by_region(cls, bigscreen_metrics_region):
        session = get_session()
        with session.begin():
            return session.query(BigscreenMetrics).filter(BigscreenMetrics.region == bigscreen_metrics_region).first()