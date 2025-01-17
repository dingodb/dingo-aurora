# 资产的service层
from db.models.asset.sql import AssetSQL
from math import ceil
from oslo_log import log

from db.models.monitor.sql import MonitorSQL

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
