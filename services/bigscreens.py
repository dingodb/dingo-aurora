# 大屏的service层
import json
import urllib

import requests
from pymemcache.client.base import Client
from jobs import CONF

from db.models.bigscreen.models import BigscreenMetricsConfig
from db.models.bigscreen.sql import BigscreenSQL
from utils import datetime

prometheus_query_url = CONF.bigscreen.prometheus_query_url

class BigScreensService:
    @classmethod
    def list_bigscreen_metrics_configs(self):
        return BigscreenSQL.get_bigscreen_metrics_configs()

    @classmethod
    def get_bigscreen_metrics(self, name):
        memcached_client = Client((CONF.bigscreen.memcached_address), timeout=1)
        try:
            memcached_metrics = memcached_client.get(f'{CONF.bigscreen.memcached_key_prefix}{name}')
            print(f"memcached_metrics: {name} -> {memcached_metrics.decode()}")
            if memcached_metrics:
                print("fetch data from cache")
                return memcached_metrics.decode()
        except Exception as e:
            print("fetch data from database")

        bigscreen_metrics_config = BigscreenSQL.get_bigscreen_metrics_config_by_name(name)
        if bigscreen_metrics_config:
            query = bigscreen_metrics_config.query
        else:
            return None
        # 通过get请求读取实时监控数据 指标项的查询语句 + / 需要转义
        request_url = prometheus_query_url + "query?query=" + urllib.parse.quote(query)
        response = requests.get(request_url)
        return self.__handle_response(response)

    # 解析接口返回的数据
    @classmethod
    def __handle_response(self, response):
        try:
            json_response = response.json()
            if json_response:
                if json_response['status'] == 'success':
                    json_data = json_response['data']
                    json_data_result = json_data['result']
                    print(f"json_data_result：{json_data_result}")
                    if json_data_result == []:
                        return 0
                    return json_data_result[0]['value'][1]
        except Exception as e:
            raise e

    @classmethod
    def fetch_metrics_with_promql(self, promql, query_range=False, start_time=None, end_time=None, step=None):
        if query_range:
            request_url = prometheus_query_url + "query_range?query=" + urllib.parse.quote(promql)
            start_time = datetime.change_to_utc_time_and_format(start_time)
            request_url = request_url + "&start=" + start_time
            if end_time:
                end_time = datetime.change_to_utc_time_and_format(end_time)
            else:
                end_time = datetime.get_now_time_in_timestamp_format()
            request_url = request_url + "&end=" + end_time
            if step:
                request_url = request_url + "&step=" + step
        else:
            request_url = prometheus_query_url + "query?query=" + urllib.parse.quote(promql)

        print(f"bigscreen_prom_request_url: {request_url}")
        response = requests.get(request_url)
        return response.json()
