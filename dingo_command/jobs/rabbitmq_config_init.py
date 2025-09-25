# rabbitmq的配置任务，自动创建shovel和queue

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import time

from dingo_command.common.common import dingo_print
from dingo_command.services.message import MessageService
from dingo_command.services.rabbitmqconfig import RabbitMqConfigService
from dingo_command.services.redis_connection import RedisLock, redis_connection

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
    dingo_print(f"Starting add rabbitmq shovel at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    # 通过redis拿锁，保证服务启动的时候只一个服务才能够拿到锁去管理报送数据的shovel
    try:
        # 只允许dingo_command连接到redis是master的节点拿到锁去
        with RedisLock(redis_connection.redis_connection, "dingo_command_dingodb_message_shovel_lock", expire_time=300) as lock:
            if lock:
                dingo_print(f"add dingodb message shovel info after get redis lock")
                rabbitmq_config_service.add_shovel()
                dingo_print(f"add dingodb message shovel info successfully")
            else:
                dingo_print(f"get redis lock failed")
    except Exception as e:
        dingo_print(e)
        dingo_print(f"can not add dingodb message shovel at {time.strftime('%Y-%m-%d %H:%M:%S')}")

def auto_connect_message_queue():
    dingo_print(f"Starting connect message mq queue at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    # 连接数据报送的queue进行消费
    message_service.connect_mq_queue()

def auto_send_message_to_dingodb():
    dingo_print(f"Starting send message to aliyun dingodb at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    # 连接数据报送的queue进行消费
    message_service.send_message_to_dingodb()

def check_rabbitmq_shovel_status():
    dingo_print(f"Starting check rabbitmq shovel status at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    # 检查rabbitmq shovel status
    message_service.check_rabbitmq_shovel_status()
