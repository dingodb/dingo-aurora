# 资产的service层
from datetime import datetime
import uuid
from math import ceil
from oslo_log import log

from dingoops.db.models.monitor.models import MonitorUrlConfig
from dingoops.db.models.monitor.sql import MonitorSQL
from dingoops.services.custom_exception import Fail

LOG = log.getLogger(__name__)

class MonitorService:

    # 查询资产列表
    def list_monitor_urls(self, query_params, page, page_size, sort_keys, sort_dirs):
        # 业务逻辑
        try:
            # 按照条件从数据库中查询数据
            count, data = MonitorSQL.list_monitor_url_config_page(query_params, page, page_size, sort_keys, sort_dirs)
            # 数据处理
            ret = []
            # 遍历
            for r in data:
                # 填充数据
                temp = {}
                temp["id"] = r.id
                temp["name"] = r.name
                temp["url"] = r.url
                temp["url_catalog"] = r.url_catalog
                temp["url_type"] = r.url_type
                temp["user_id"] = r.user_id
                temp["user_account"] = r.user_account
                temp["description"] = r.description
                ret.append(temp)
            # 返回数据
            res = {}
            # 页数相关信息
            if page and page_size:
                res['currentPage'] = page
                res['pageSize'] = page_size
                res['totalPages'] = ceil(count / int(page_size))
            res['total'] = count
            res['data'] = ret
            return res
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    # 创建监控url类型
    def create_monitor_url_config(self, monitor_url_config):
        # 业务逻辑
        try:
            # 业务校验 对象非空，数据线填充
            # 判空
            if monitor_url_config is None or monitor_url_config.name is None:
                raise Exception("monitor config name is empty", error_message = "url配置信息名称是空")
            # 重名
            monitor_url_db = MonitorSQL.get_monitor_url_by_name(monitor_url_config.name)
            if monitor_url_db:
                raise Exception("monitor config name already exists", error_message = "url配置信息名称已经存在")
            # 数据对象转换
            monitor_url_db = self.convert_monitor_url_info_db(monitor_url_config)
            # 数据入库
            MonitorSQL.create_monitor_url_config(monitor_url_db)
            # 返回
            return monitor_url_db.id
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    # api的model对象转换数据库对象
    def convert_monitor_url_info_db(self, api_model):
        # 判空
        if api_model is None:
            return None
        # 数据转化为db对象
        monitor_url_db = MonitorUrlConfig(
            id=uuid.uuid4().hex,
            name=api_model.name,
            url=api_model.url,
            url_catalog=api_model.url_catalog,
            url_type=api_model.url_type,
            user_id=api_model.user_id,
            user_account=api_model.user_account,
            create_date=datetime.fromtimestamp(datetime.now().timestamp()), # 当前时间
            description=api_model.description,
        )
        # 返回数据
        return monitor_url_db

    # 删除监控url配置信息
    def delete_monitor_url_config_by_id(self, config_id):
        # 业务校验
        if config_id is None or len(config_id) <= 0:
            return None
        # 删除
        try:
            MonitorSQL.delete_monitor_url_by_id(config_id)
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e
        # 成功id
        return config_id

    # 根据id修改监控url配置
    def update_monitor_url_config_by_id(self, config_id, monitor_url_config):
        # 业务校验
        if config_id is None or monitor_url_config is None:
            return None
        try:
            # 配置信息
            config_db = MonitorSQL.get_monitor_url_by_id(config_id)
            # 判空
            if config_db is None:
                raise Fail("monitor url config not exists", error_message="监控URL配置信息不存在")
            # 判断重名
            if monitor_url_config.name and monitor_url_config.name != config_db.name:
                monitor_url_db = MonitorSQL.get_monitor_url_by_name(monitor_url_config.name)
                if monitor_url_db:
                    raise Exception("monitor config name already exists", error_message = "url配置信息名称已经存在")
            # 填充需要修改的数据
            config_db = self.reset_monitor_url_info_db(config_db, monitor_url_config)
            # 保存对象
            MonitorSQL.update_monitor_url_config(config_db)
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e
        # 成功返回id
        return config_id

    # api的model对象转换数据库对象
    def reset_monitor_url_info_db(self, db_model, api_model):
        # 判空
        if api_model is None:
            return db_model
        # 数据转化为db对象
        if api_model.name:
            db_model.name = api_model.name
        if api_model.url:
            db_model.url = api_model.url
        if api_model.url_catalog:
            db_model.url_catalog = api_model.url_catalog
        if api_model.url_type:
            db_model.url_type = api_model.url_type
        if api_model.user_id:
            db_model.user_id = api_model.user_id
        if api_model.user_account:
            db_model.user_account = api_model.user_account
        if api_model.description:
            db_model.description = api_model.description
        # 返回数据
        return db_model