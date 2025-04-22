
from apscheduler.schedulers.background import BackgroundScheduler

from common.ironic_client import ironic_client
from utils import datetime as datatime_util
from datetime import datetime

relation_scheduler = BackgroundScheduler()

def start():
    relation_scheduler.add_job(fetch_relation_info, 'interval', seconds=300, next_run_time=datetime.now())
    relation_scheduler.start()

def fetch_relation_info():
    # 读取所有裸机数据、读取所有资产数据，对比数据根据ip进行比对，相同的ip则建立关联关系
    print(f"同步资源与资产的关联关系开始时间: {datatime_util.get_now_time_in_timestamp_format()}")
    try:
        # 1、读取裸金属列表
        node_response = ironic_client.ironic_list_nodes()
        print(f"裸金属列表数据: {node_response}")
    except Exception as e:
        print(f"同步资源与资产关系失败: {e}")
    print(f"同步资源与资产的关联关系结束时间: {datatime_util.get_now_time_in_timestamp_format()}")
