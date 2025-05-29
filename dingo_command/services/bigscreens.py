# 大屏的service层
import json
import urllib
import uuid

import requests
from pymemcache.client.base import Client
from dingo_command.jobs import CONF

from dingo_command.db.models.bigscreen.models import BigscreenMetrics
from dingo_command.db.models.bigscreen.sql import BigscreenSQL
from dingo_command.utils import datetime

prometheus_query_url = CONF.bigscreen.prometheus_query_url
region_name = CONF.DEFAULT.region_name
nightingale_base_url = CONF.bigscreen.nightingale_base_url
nightingale_username = CONF.bigscreen.nightingale_username
nightingale_password = CONF.bigscreen.nightingale_password
sequence_list = CONF.bigscreen.sequence_list  # 序列值指标

class BigScreensService:
    @classmethod
    def list_bigscreen_metrics_configs(self):
        return BigscreenSQL.get_bigscreen_metrics_configs()

    @classmethod
    def get_bigscreen_metrics(self, name, region, sync=False):
        # 通过 n9e 获取数据
        if name in ['alert_count', 'gpu_fallen_count']:
            return self.fetch_n9e_metrics(name)

        # 通过 prometheus 同步数据
        if sync:
            bigscreen_metrics_config = BigscreenSQL.get_bigscreen_metrics_config_by_name(name)
            if bigscreen_metrics_config:
                query = bigscreen_metrics_config.query
            else:
                return None
            # 通过get请求读取实时监控数据 指标项的查询语句 + / 需要转义
            request_url = prometheus_query_url + "query?query=" + urllib.parse.quote(query)
            if name in sequence_list:
                sequence = True
            else:
                sequence = False
            response = requests.get(request_url)
            return self.__handle_response(response,sequence)

        # 通过 memcached 和 mysql 获取数据
        memcached_client = Client((CONF.bigscreen.memcached_address), timeout=1)
        try:
            memcached_metrics = memcached_client.get(f'{CONF.bigscreen.memcached_key_prefix}{name}')
            print(f"memcached_metrics: {name} -> {memcached_metrics.decode()}")
            if memcached_metrics:
                print("fetch data from cache")
                if name in sequence:
                    return list(memcached_metrics.decode())
                return memcached_metrics.decode()
        except Exception as e:
            print("fetch data from cache failed")

        if region == None:
            region = region_name
        bigscreen_metrics = BigscreenSQL.get_bigscreen_metrics_by_name_and_region(name, region)
        if bigscreen_metrics:
            print("fetch data from db")
            return json.loads(bigscreen_metrics.data)
        else:
            return None

    # 解析接口返回的数据
    @classmethod
    def __handle_response(self, response,sequence=False):
        try:
            json_response = response.json()
            if json_response:
                if json_response['status'] == 'success':
                    json_data = json_response['data']
                    json_data_result = json_data['result']
                    if not json_data_result:
                        return 0
                    if not sequence:
                        return json_data_result[0]['value'][1]
                    else:
                        return  [{**result, **result.get('metric', {})} if isinstance(result.get('metric', {}), dict) else result  for result in json_data_result]
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

    @classmethod
    def batch_upgrade_metrics_data(self, metrics_dict):
        for name, data in metrics_dict.items():
            metrics = BigscreenSQL.get_bigscreen_metrics_by_name_and_region(name, region_name)
            if metrics:
                metrics.data = data
                metrics.last_modified = datetime.get_now_time()
                if isinstance(data, list):
                    metrics.data = json.dumps(data)
                BigscreenSQL.update_bigscreen_metrics(metrics)
            else:
                metrics = BigscreenMetrics(
                    id = uuid.uuid4().hex,
                    name = name,
                    data = data,
                    region = region_name,
                    last_modified = datetime.get_now_time()
                )
                if isinstance(data, list):
                    metrics.data = json.dumps(data)
                BigscreenSQL.create_bigscreen_metrics(metrics)


    @classmethod
    def batch_upgrade_metrics_data_by_region(self, metrics_dict, specify_region):
        # 遍历
        for name, data in metrics_dict.items():
            metrics = BigscreenSQL.get_bigscreen_metrics_by_name_and_region(name, specify_region)
            if metrics:
                metrics.data = data
                metrics.last_modified = datetime.get_now_time()
                BigscreenSQL.update_bigscreen_metrics(metrics)
            else:
                metrics = BigscreenMetrics(
                    id = uuid.uuid4().hex,
                    name = name,
                    data = data,
                    region = specify_region,
                    last_modified = datetime.get_now_time()
                )
                BigscreenSQL.create_bigscreen_metrics(metrics)

    @classmethod
    def fetch_n9e_metrics(self, name):
        access_token = self.login_n9e()
        if access_token:
            headers = {
                "Authorization": f"Bearer {access_token}"
            }
            if name == 'alert_count':
                url = nightingale_base_url + "/api/n9e/alert-cur-events/list"
                response = requests.get(url, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    return data['dat']['total']
                else:
                    print(f"获取告警数失败: {response}")
            if name == 'gpu_fallen_count':
                url = nightingale_base_url + "/api/n9e/alert-cur-events/list"
                params = {"query": "掉卡"}
                response = requests.get(url, headers=headers, params=params)

                if response.status_code == 200:
                    data = response.json()
                    return data['dat']['total']
                else:
                    print(f"获取掉卡数失败: {response}")

    @classmethod
    def login_n9e(self):
        login_url = nightingale_base_url + "/api/n9e/auth/login"
        login_payload = {
            "username": nightingale_username,
            "password": nightingale_password
        }
        login_response = requests.post(login_url, json=login_payload)

        if login_response.status_code == 200:
            login_data = login_response.json()
            access_token = login_data["dat"]["access_token"]
            return access_token
        else:
            print(f"夜莺登录失败: {login_response}")
            return None

