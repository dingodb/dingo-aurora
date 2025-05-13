# 消息的service层
import uuid
import json
import pika

from oslo_log import log
from oslo_config import cfg
from datetime import datetime

from dingo_command.db.models.message.models import ExternalMessage
from dingo_command.db.models.message.sql import MessageSQL
from dingo_command.services.aliyundingodb import aliyun_dingodb_utils
from dingo_command.services.custom_exception import Fail
from dingo_command.services.rabbitmqconfig import RabbitMqConfigService
from dingo_command.utils.constant import RABBITMQ_EXTERNAL_MESSAGE_QUEUE, MESSAGE_TYPE_TABLE
from dingo_command.utils.mysql import MySqlUtils

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

    def update_external_message_4error(self, message_db, error_description):
        try:
            # 判空
            if not message_db:
                raise Fail("message not exists", error_message="报送JSON数据对象不能是空")
            # 设置
            message_db.message_status = "ERROR"
            message_db.message_description = error_description
            message_db.update_date = datetime.fromtimestamp(datetime.now().timestamp()) # 当前时间
            # 创建
            MessageSQL.update_external_message(message_db)
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
        if "az" in message:
            message_db.az_name = message["az"]
        if "message_type" in message:
            message_db.message_type = message["message_type"]
        if "message_data" in message:
            message_db.message_data = json.dumps(message["message_data"]) if message["message_data"] else None # 转化为json字符串
        # 返回
        return message_db

    def callback(self, ch, method, properties, body):
        print(f"Received queue: {RABBITMQ_EXTERNAL_MESSAGE_QUEUE}, message: {body}")
        # 停止消费 判断是否消费了指定的数量
        # ch.stop_consuming()
        # 转换json对象
        message_json = None
        try:
            message_json = json.loads(body)
        except Exception as e:
            import traceback
            traceback.print_exc()
        if not message_json:
            print(f"message is not valid: {body}")
            return
        self.create_external_message(message_json)

    # 连接消息队列，消费数据
    def connect_mq_queue(self):
        # 目前只有中心region才需要连接队列，因为目前是从普通region铲消息到中心region
        if CENTER_REGION_FLAG is False:
            print("current region is not center region, no need to connect mq shovel queue")
            return
        # 消费报送数据的消息
        rabbitmq_config_service.consume_queue_message(RABBITMQ_EXTERNAL_MESSAGE_QUEUE, self.callback)

    # 发送数据到rabbitmq的队列中
    def send_message_to_queue(self, message):
        try:
            # 判空
            if not message:
                raise Fail("message not exists", error_message="报送JSON数据对象不能是空")
            # 处理数据
            message_db = self.convert_external_message_db(message)
            # 转化对象
            if not message_db or not message_db.message_type or not message_db.message_data or not message_db.region_name:
                raise Fail("message param not exists", error_message="报送JSON数据对象参数不完整")
            # 发送message
            rabbitmq_config_service.publish_message_to_queue(RABBITMQ_EXTERNAL_MESSAGE_QUEUE, json.dumps(message))
            print("current region is not center region, no need to connect mq shovel queue")
            # 返回成功标志
            return "SUCCESS"
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e


    # 发送数据到阿里云的dingodb
    def send_message_to_dingodb(self):
        # 目前只有中心region才需要发送数据到dingodb
        if CENTER_REGION_FLAG is False:
            print("current region is not center region, no need to send message to dingodb")
            return
        try:
            # 遍历message_type_table 按照类型进行插入数据
            for message_type_key, message_dingo_table in MESSAGE_TYPE_TABLE.items():
                # 每次读取1000条
                query_params = {"message_type":message_type_key}
                _, message_list = MessageSQL.list_external_message(query_params, 1, 1000, None, None)
                # 判空 进入下一种类型
                if not message_list:
                    print(f"{message_type_key} message type no message to send")
                    continue
                # 遍历消息列表
                for temp_message in message_list:
                    # 判断message是否合规
                    if not temp_message.message_data:
                        print(f"message is not valid: {temp_message}")
                        continue
                    # message_data转化为json对象
                    message_data_json = self.load_message_data_json(temp_message)
                    # 判空
                    if not message_data_json:
                        print(f"message_data_json is not valid: {temp_message}")
                        continue
                    # 组装sql
                    insert_dingodb_sql = self.create_dingodb_insert_sql(message_data_json, message_dingo_table)
                    insert_dingodb_values = tuple(message_data_json.values())
                    # 执行sql
                    try:
                        self.insert_one_into_dingodb(insert_dingodb_sql, insert_dingodb_values)
                        # 成功之后删除掉当前数据
                        MessageSQL.delete_external_message(temp_message.id)
                        # 成功记录成功的操作日志
                        print(f"success insert message to dingodb: {temp_message}")
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        # 记录错误日志信息
                        self.update_external_message_4error(temp_message, traceback.format_exc())
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def load_message_data_json(self,message_db):
        try:
        # 处理数据
            message_data_json = json.loads(message_db.message_data)
            return message_data_json
        except Exception as e:
            import traceback
            traceback.print_exc()

    # 组装dingodb的插入sql语句
    def create_dingodb_insert_sql(self, message_data_json, message_dingo_table):
        # 生成字段名和占位符
        fields = ", ".join(message_data_json.keys())
        placeholders = ", ".join(["%s"] * len(message_data_json))
        # 生成sql语句
        dingodb_sql_template = f"INSERT INTO {message_dingo_table} ({fields}) VALUES ({placeholders})"
        # 返回组装语句
        return dingodb_sql_template

    # 执行插入dingodb的sql语句
    def insert_one_into_dingodb(self, insert_dingodb_sql, insert_dingodb_values):
        # 执行sql
        try:
            # 执行插入语句
            aliyun_dingodb_utils.insert_one(insert_dingodb_sql, insert_dingodb_values)
            print(f"success execute sql: {insert_dingodb_sql}")
            print(f"success insert message to dingodb: {insert_dingodb_values}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e