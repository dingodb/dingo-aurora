from pymemcache.client.base import Client
from apscheduler.schedulers.background import BackgroundScheduler
from services.bigscreens import BigScreensService
from jobs import CONF

scheduler = BackgroundScheduler()

def start():
    scheduler.add_job(fetch_bigscreen_metrics, 'interval', seconds=CONF.bigscreen.metrics_fetch_interval)
    scheduler.start()

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

