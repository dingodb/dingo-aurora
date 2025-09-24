import json
import pika
from dingo_command.common.common import dingo_print
from dingo_command.services.bigscreens import BigScreensService
from dingo_command.services.bigscreenshovel import SHOVEL_QUEUE, MY_IP, CENTER_REGION_FLAG, TRANSPORT_URL


# 大屏的service
bigScreensService = BigScreensService()

class BigScreenSyncService:

    @classmethod
    def handle_big_screen_message(cls, body):
        # 在这里处理大屏幕消息
        dingo_print(f"Handling big screen message: {body}")
        # 转换json对象
        big_screen_message = None
        try:
            big_screen_message = json.loads(body)
        except Exception as e:
            import traceback
            traceback.print_exc()
        # 判空
        if big_screen_message is None:
            dingo_print("big_screen_message is none, no need to handle")
            return None
        # 存入数据库
        metrics_dict = big_screen_message["metrics_dict"] if "metrics_dict" in big_screen_message else None
        specify_region = big_screen_message["region_name"] if "region_name" in big_screen_message else None
        # 判空
        if metrics_dict is None or specify_region is None:
            dingo_print("metrics_dict is none, no need to save db. region_name is none, no need to save db")
            return None
        # 存入数据库
        bigScreensService.batch_upgrade_metrics_data_by_region(metrics_dict, specify_region)
        dingo_print("metrics_dict save db successfully.")

    @classmethod
    def callback(cls, ch, method, properties, body):
        dingo_print(f"Received {body}")
        cls.handle_big_screen_message(body)

    @classmethod
    def connect_mq_queue(cls):
        # 目前只有中心region才需要连接队列，因为目前是从普通region铲消息到中心region
        if CENTER_REGION_FLAG is False:
            dingo_print("current region is not center region, no need to connect mq shovel queue")
            return
        # 连接到当前节点的RabbitMQ的服务器
        username, password = cls.get_mq_name_password()
        credentials = pika.PlainCredentials(username, password)
        parameters = pika.ConnectionParameters(MY_IP, 5672, '/', credentials)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        # 声明队列
        channel.queue_declare(queue=SHOVEL_QUEUE, durable=True)
        # 订阅队列并设置回调函数
        channel.basic_consume(queue=SHOVEL_QUEUE, on_message_callback=cls.callback, auto_ack=True)
        dingo_print('Waiting for messages.')
        channel.start_consuming()

    @classmethod
    def get_mq_name_password(cls):
        user_name = None
        password = None
        transport_url = TRANSPORT_URL.replace("rabbit:", "").replace("//", "")
        # 多节点环境
        transport_url_array = transport_url.split(',')
        # 空
        if transport_url_array is None or len(transport_url_array) <= 0:
            dingo_print("rabbit mq transport url array is empty ")
            return
        # 遍历
        for temp_url in transport_url_array:
        # 当前节点的mq信息
            if MY_IP in temp_url:
                # 分割获取用户名和密码
                temp_url_array = temp_url.split('@')
                # 非空
                if temp_url_array:
                    name_and_password = temp_url_array[0].split(':')
                    if name_and_password:
                        user_name = name_and_password[0]
                        password = name_and_password[1]
                break
        # 返回数据
        return user_name, password

    @classmethod
    def send_mq_message(cls, message):
        # 中心region的话，不需要发送mq消息
        if CENTER_REGION_FLAG is True:
            dingo_print("current region is center region, no need to send mq message")
            return
        try:
            # 连接到当前节点的RabbitMQ的服务器，连接到队列然后发送消息
            username, password = cls.get_mq_name_password()
            credentials = pika.PlainCredentials(username, password)
            parameters = pika.ConnectionParameters(MY_IP, 5672, '/', credentials)
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            # 声明队列
            channel.queue_declare(queue=SHOVEL_QUEUE, durable=True)
            # 发送消息
            channel.basic_publish(
                exchange='',
                routing_key=SHOVEL_QUEUE,
                body=message,
                properties=pika.BasicProperties(
                    delivery_mode=2,
                )
            )
            dingo_print("send mq message success")
            dingo_print(f"message: {message}")
            # 关闭连接
            connection.close()
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None