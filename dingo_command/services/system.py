# 系统相关的公共功能service
import uuid
from datetime import datetime
from math import ceil

from oslo_log import log

from dingo_command.db.models.system.models import OperateLog
from dingo_command.db.models.system.sql import SystemSQL
from dingo_command.utils.datetime import get_system_time_range, get_system_current_time

LOG = log.getLogger(__name__)


class SystemService:

    def list_system_logs(self, query_params, page, page_size, sort_keys, sort_dirs):
        # 业务逻辑
        try:
            # 查询数据库
            count, data = SystemSQL.list_operate_log(query_params, page, page_size, sort_keys, sort_dirs)
            # 数据处理
            ret = []
            # 遍历
            for r in data:
                temp = {}
                temp["id"] = r.id
                temp["log_date"] = None if r.log_date is None else r.log_date.timestamp() * 1000
                temp["user_id"] = r.user_id
                temp["user_name"] = r.user_name
                temp["ip"] = r.ip
                temp["operate_type"] = r.operate_type
                temp["resource_type"] = r.resource_type
                temp["resource_type_name"] = r.resource_type_name
                temp["resource_id"] = r.resource_id
                temp["resource_name"] = r.resource_name
                temp["operate_flag"] = r.operate_flag
                temp["description"] = r.description
                # 加入列表
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
            return None

    def create_system_log(self, system_log):
        # 空
        if system_log is None:
            return None
        # 日志id
        log_id = None
        # 保存
        try:
            # 数据判空
            system_log_info_db = self.convert_system_log_info_db(system_log)
            log_id = system_log_info_db.id
            # 保存日志
            SystemSQL.create_operate_log(system_log_info_db)
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e
        # 成功返回资产id
        return log_id


    # 日志创建时基础对象数据转换
    def convert_system_log_info_db(self, system_log):
        # 数据转化为db对象
        system_log_info_db = OperateLog(
            id=uuid.uuid4().hex,
            log_date=datetime.fromtimestamp(datetime.now().timestamp()),
            user_id=system_log.user_id,
            user_name=system_log.user_name,
            ip=system_log.ip,
            operate_type=system_log.operate_type,
            resource_type=system_log.resource_type,
            resource_type_name=system_log.resource_type_name,
            resource_id=system_log.resource_id,
            resource_name=system_log.resource_name,
            operate_flag=system_log.operate_flag,
            description=system_log.description,
        )
        # 返回数据
        return system_log_info_db

    def get_system_time_range(self, time_type):
        try:
            begin, end = get_system_time_range(time_type)
            result = {}
            result['begin'] = begin
            result['end'] = end
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def get_system_current_time(self):
        try:
            return get_system_current_time()
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e