import pika

from services.bigscreenshovel import SHOVEL_QUEUE, MY_IP, CENTER_REGION_FLAG, TRANSPORT_URL


class BigScreenSyncService:

    @classmethod
    def handle_big_screen_message(cls, body):
        # 在这里处理大屏幕消息
        print(f"Handling big screen message: {body}")

    @classmethod
    def callback(cls, ch, method, properties, body):
        print(f"Received {body}")
        cls.handle_big_screen_message(body)

    @classmethod
    def connect_mq_queue(cls):
        # 目前只有中心region才需要连接队列，因为目前是从普通region铲消息到中心region
        if CENTER_REGION_FLAG is False:
            print("current region is center region, no need to add shovel")
            return
        # 连接到当前节点的RabbitMQ的服务器
        username, password = cls.get_mq_name_password()
        credentials = pika.PlainCredentials(username, password)
        parameters = pika.ConnectionParameters(MY_IP, 5672, '/', credentials)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        # 声明队列
        channel.queue_declare(queue=SHOVEL_QUEUE)
        # 订阅队列并设置回调函数
        channel.basic_consume(queue=SHOVEL_QUEUE, on_message_callback=cls.callback, auto_ack=True)
        print('Waiting for messages.')
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
            print("rabbit mq transport url array is empty ")
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