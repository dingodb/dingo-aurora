# 消息的service层
import uuid
import json
import pika

from oslo_log import log
from oslo_config import cfg
from datetime import datetime

from dingoops.db.models.message.models import ExternalMessage
from dingoops.db.models.message.sql import MessageSQL
from dingoops.services.custom_exception import Fail
from dingoops.services.rabbitmqconfig import RabbitMqConfigService
from dingoops.utils.constant import RABBITMQ_EXTERNAL_MESSAGE_QUEUE

LOG = log.getLogger(__name__)

rabbitmq_config_service = RabbitMqConfigService()

CONF = cfg.CONF
MY_IP = CONF.DEFAULT.my_ip
TRANSPORT_URL = CONF.DEFAULT.transport_url
CENTER_TRANSPORT_URL = CONF.DEFAULT.center_transport_url
CENTER_REGION_FLAG = CONF.DEFAULT.center_region_flag


class MessageService:

    def create_external_message(self, message):
        try:
            # 判空
            if not message:
                raise Fail("message not exists", error_message="报送JSON数据对象不能是空")
            # 处理数据
            message_db = self.convert_external_message_db(message)
            # 转化对象
            if not message_db or not message_db.message_type or not message_db.message_data:
                raise Fail("message param not exists", error_message="报送JSON数据对象参数不完整")
            # 创建
            MessageSQL.create_external_message(message_db)
            # 返回
            return message_db.id
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e


    # 转换前端的json对象
    def convert_external_message_db(self, message):
        # 判空
        if not message:
            return None
        # 声明空的信息对象
        message_db = ExternalMessage(
            id=uuid.uuid4().hex,
            message_status="READY",
            create_date = datetime.fromtimestamp(datetime.now().timestamp()), # 当前时间
        )
        # 处理数据
        if "region" in message:
            message_db.region_name = message["region"]
        if "message_type" in message:
            message_db.message_type = message["message_type"]
        if "message_data" in message:
            message_db.message_data = json.dumps(message["message_data"]) if message["message_data"] else None # 转化为json字符串
        # 返回
        return message_db

    def callback(self, ch, method, properties, body):
        print(f"Received {body}")
        # 停止消费 判断是否消费了指定的数量
        # ch.stop_consuming()
        self.handle_big_screen_message(body)

    # 连接消息队列，消费数据
    def connect_mq_queue(self):
        # 目前只有中心region才需要连接队列，因为目前是从普通region铲消息到中心region
        if CENTER_REGION_FLAG is False:
            print("current region is not center region, no need to connect mq shovel queue")
            return
        # 连接到当前节点的RabbitMQ的服务器
        username, password, _ = rabbitmq_config_service.get_current_mq_config_info()
        credentials = pika.PlainCredentials(username, password)
        parameters = pika.ConnectionParameters(MY_IP, 5672, '/', credentials)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        # 声明队列
        channel.queue_declare(queue=RABBITMQ_EXTERNAL_MESSAGE_QUEUE, durable=True)
        # 订阅队列并设置回调函数
        channel.basic_consume(queue=RABBITMQ_EXTERNAL_MESSAGE_QUEUE, on_message_callback=self.callback, auto_ack=True)
        print('Waiting for external json messages.')
        channel.start_consuming()

