from apscheduler.schedulers.blocking import BlockingScheduler
from pymemcache.client.base import Client
from apscheduler.schedulers.background import BackgroundScheduler
from services.bigscreens import BigScreensService
from services.bigscreenshovel import BigScreenShovelService
from jobs import CONF
from datetime import datetime, timedelta
import time

from services.syn_bigscreens import BigScreenSyncService

scheduler = BackgroundScheduler()
blocking_scheduler = BlockingScheduler()
# 启动完成后执行
run_time_10s = datetime.now() + timedelta(seconds=10)  # 任务将在10秒后执行
run_time_30s = datetime.now() + timedelta(seconds=30)  # 任务将在30秒后执行

def start():
    scheduler.add_job(fetch_bigscreen_metrics, 'interval', seconds=CONF.bigscreen.metrics_fetch_interval)
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
    print(f'client: {memcached_client}')
    for metric in metrics:
        metric_name = metric.name
        metric_value = BigScreensService.get_bigscreen_metrics(metric_name)
        metrics_dict[f'{CONF.bigscreen.memcached_key_prefix}{metric_name}'] = metric_value
    try:
        print(metrics_dict)
        memcached_client.set_many(metrics_dict, expire=CONF.bigscreen.metrics_expiration_time)
    except Exception as e:
        print(f"缓存写入失败: {e}")

