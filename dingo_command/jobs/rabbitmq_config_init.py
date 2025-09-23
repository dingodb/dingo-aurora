# rabbitmq的配置任务，自动创建shovel和queue

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import time

from dingo_command.services.message import MessageService
from dingo_command.services.rabbitmqconfig import RabbitMqConfigService

# mq的任务调度器
rabbitmq_scheduler = BackgroundScheduler()
# 启动完成后执行
run_time_10s = datetime.now() + timedelta(seconds=10)  # 任务将在10秒后执行
run_time_30s = datetime.now() + timedelta(seconds=30)  # 任务将在30秒后执行

# 连接rabbitmq的配置
rabbitmq_config_service = RabbitMqConfigService()
message_service = MessageService()

def start():
    rabbitmq_scheduler.add_job(auto_set_shovel, 'date', run_date=run_time_10s)
    rabbitmq_scheduler.add_job(auto_connect_message_queue, 'date', run_date=run_time_30s)
    # 任务体的锁的时间就是60s 任务的频率改成60s就可以
    rabbitmq_scheduler.add_job(auto_send_message_to_dingodb, 'interval', seconds=60, next_run_time=datetime.now())
    # rabbitmq_scheduler.add_job(check_rabbitmq_shovel_status, 'interval', seconds=60*5, next_run_time=datetime.now())
    rabbitmq_scheduler.start()

def auto_set_shovel():
    print(f"Starting add rabbitmq shovel at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    rabbitmq_config_service.add_shovel()

def auto_connect_message_queue():
    print(f"Starting connect message mq queue at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    # 连接数据报送的queue进行消费
    message_service.connect_mq_queue()

def auto_send_message_to_dingodb():
    print(f"Starting send message to aliyun dingodb at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    # 连接数据报送的queue进行消费
    message_service.send_message_to_dingodb()

def check_rabbitmq_shovel_status():
    print(f"Starting check rabbitmq shovel status at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    # 检查rabbitmq shovel status
    message_service.check_rabbitmq_shovel_status()
