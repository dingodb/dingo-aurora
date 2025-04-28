import json

from apscheduler.schedulers.blocking import BlockingScheduler
from pymemcache.client.base import Client
from apscheduler.schedulers.background import BackgroundScheduler
from dingoops.services.bigscreens import BigScreensService
from dingoops.services.bigscreenshovel import BigScreenShovelService
from dingoops.jobs import CONF
from datetime import datetime, timedelta
import time

from dingoops.services.syn_bigscreens import BigScreenSyncService
from dingoops.services.websocket_service import websocket_service


scheduler = BackgroundScheduler()
blocking_scheduler = BlockingScheduler()
# 启动完成后执行
run_time_10s = datetime.now() + timedelta(seconds=10)  # 任务将在10秒后执行
run_time_30s = datetime.now() + timedelta(seconds=30)  # 任务将在30秒后执行

def start():
    scheduler.add_job(fetch_bigscreen_metrics, 'interval', seconds=CONF.bigscreen.metrics_fetch_interval, next_run_time=datetime.now())
    scheduler.add_job(auto_add_shovel, 'date', run_date=run_time_10s)
    scheduler.add_job(auto_connect_queue, 'date', run_date=run_time_30s)
    scheduler.start()

def auto_add_shovel():
    print(f"Starting add shovel at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    BigScreenShovelService.add_shovel()

def auto_connect_queue():
    print(f"Starting connect big screen mq queue at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    BigScreenSyncService.connect_mq_queue()

def fetch_bigscreen_metrics():
    metrics = BigScreensService.list_bigscreen_metrics_configs()
    memcached_client = Client((CONF.bigscreen.memcached_address))
    metrics_dict = {}
    metrics_dict_with_prefix = {}
    print(f'client: {memcached_client}')
    for metric in metrics:
        metric_name = metric.name
        metric_value = BigScreensService.get_bigscreen_metrics(metric_name, None, sync=True)
        metrics_dict[metric_name] = metric_value
        metrics_dict_with_prefix[f'{CONF.bigscreen.memcached_key_prefix}{metric_name}'] = metric_value
    try:
        # metrics 写入缓存
        memcached_client.set_many(metrics_dict_with_prefix, expire=CONF.bigscreen.metrics_expiration_time)

        # metrics 写入数据库
        BigScreensService.batch_upgrade_metrics_data(metrics_dict)

        # 发送mq消息，往中心region发送一份数据
        BigScreenSyncService.send_mq_message(json.dumps({"region_name":region_name, "metrics_dict":metrics_dict}))
        # 发送websocket更新消息
        websocket_service.send_websocket_message('big_screen', json.dumps({"refresh_flag": True}))
    except Exception as e:
        print(f"缓存写入失败: {e}")

