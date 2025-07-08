# 消息的service层
import re
import uuid
import json
from enum import Enum

from oslo_log import log
from oslo_config import cfg
from datetime import datetime

from dingo_command.db.models.message.models import ExternalMessage
from dingo_command.db.models.message.sql import MessageSQL
from dingo_command.services.aliyundingodb import aliyun_dingodb_utils, aliyun_dingodb_read_utils
from dingo_command.services.custom_exception import Fail
from dingo_command.services.rabbitmqconfig import RabbitMqConfigService
from dingo_command.services.redis_connection import redis_connection, RedisLock
from dingo_command.utils.constant import RABBITMQ_EXTERNAL_MESSAGE_QUEUE, MESSAGE_TYPE_TABLE

LOG = log.getLogger(__name__)

rabbitmq_config_service = RabbitMqConfigService()

CONF = cfg.CONF
MY_IP = CONF.DEFAULT.my_ip
TRANSPORT_URL = CONF.DEFAULT.transport_url
CENTER_TRANSPORT_URL = CONF.DEFAULT.center_transport_url
CENTER_REGION_FLAG = CONF.DEFAULT.center_region_flag

# 消息状态的枚举
class MessageStatusEnum(Enum):
    READY = "READY"  # 准备中
    ERROR = "ERROR"  # 错误


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

    # 批量更新外部消息的状态为ERROR
    def update_external_many_message_4error(self, message_ids, error_description):
        try:
            # 判空
            if not message_ids:
                raise Fail("message id not exists", error_message="报送的消息是未知id")
            # 更新错误消息
            MessageSQL.update_external_message_4error(message_ids, error_description)
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
            # 获取redis的锁，自动释放时间是60s
            with RedisLock(redis_connection.redis_connection, "dingo_command_report_message_lock", expire_time=60) as lock:
                if lock:
                    print("get dingo_command_report_message_lock redis lock success")
                    # 遍历message_type_table 按照类型进行插入数据
                    for message_type_key, message_dingo_table in MESSAGE_TYPE_TABLE.items():
                        # 检查当前类型的数据是否存在ERROR状态的数据，如果存在ERROR状态数据则需要告警，并且不再报送数据
                        error_status_number = MessageSQL.get_external_message_number_by_status(message_type_key, MessageStatusEnum.ERROR)
                        if error_status_number > 0:
                            print(f"message type {message_type_key} has error status message, please check it")
                            continue
                        # 每次读取1000条
                        query_params = {"message_type":message_type_key}
                        # 按照创建时间顺序排序
                        _, message_list = MessageSQL.list_external_message(query_params, 1, 1000, "create_date", "ascend")
                        # 判空 进入下一种类型
                        if not message_list:
                            print(f"{message_type_key} message type no message to send")
                            continue
                        # 报送的数据结构可能是变化的，兼容不同的结构，生产不同的插入语句,不同的插入语句对应不同的数据内容
                        insert_dingodb_sql_value_map = {}
                        insert_dingodb_sql_message_id_map = {}
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
                            # 加入到map中
                            insert_dingodb_sql_value_map = self.add_sql_and_values_to_map(insert_dingodb_sql_value_map, insert_dingodb_sql, insert_dingodb_values)
                            insert_dingodb_sql_message_id_map = self.add_sql_and_id_to_map(insert_dingodb_sql_message_id_map, insert_dingodb_sql, temp_message.id)
                        # 批量多个数据
                        self.insert_many_message_to_dingodb(insert_dingodb_sql_value_map, insert_dingodb_sql_message_id_map)
                else:
                    print("get dingo_command_report_message_lock redis lock failed")
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e


    # 执行sql与数据分组键值对
    def add_sql_and_values_to_map(self, insert_dingodb_sql_map, insert_dingodb_sql, insert_dingodb_values):
        # 判空
        if not insert_dingodb_sql_map:
            insert_dingodb_sql_map = {}
        # 判断当前sql是否存在，如果存在则直接添加值
        if insert_dingodb_sql in insert_dingodb_sql_map:
            insert_dingodb_sql_map[insert_dingodb_sql].append(insert_dingodb_values)
        else:
            insert_dingodb_sql_map[insert_dingodb_sql] = [insert_dingodb_values]
        # 返回数据
        return insert_dingodb_sql_map


    # 执行sql与消息id键值对
    def add_sql_and_id_to_map(self, insert_dingodb_message_id_map, insert_dingodb_sql, message_id):
        # 判空
        if not insert_dingodb_message_id_map:
            insert_dingodb_message_id_map = {}
        # 判断当前sql是否存在，如果存在则直接添加值
        if insert_dingodb_sql in insert_dingodb_message_id_map:
            insert_dingodb_message_id_map[insert_dingodb_sql].append(message_id)
        else:
            insert_dingodb_message_id_map[insert_dingodb_sql] = [message_id]
        # 返回数据
        return insert_dingodb_message_id_map


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


    # 处理多条message数据
    def insert_many_message_to_dingodb(self, insert_dingodb_sql_value_map, insert_dingodb_sql_message_id_map)  :
        # 判空
        if not insert_dingodb_sql_value_map or not insert_dingodb_sql_message_id_map:
            print("no message to insert to dingodb")
            return
        # 当前处理的message_id
        message_ids = None
        # 执行
        try:
            # 遍历sql语句，执行插入操作
            for insert_dingodb_sql, insert_dingodb_values in insert_dingodb_sql_value_map.items():
                # 当前处理的id
                message_ids = insert_dingodb_sql_message_id_map[insert_dingodb_sql]
                # 执行插入多条
                self.insert_many_into_dingodb(insert_dingodb_sql, insert_dingodb_values)
                # 成功之后删除掉当前数据
                MessageSQL.delete_external_message_by_ids(message_ids)
                # 成功记录成功的操作日志
                print(f"success insert message to dingodb: {message_ids}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            # 记录错误日志信息
            self.update_external_many_message_4error(message_ids, traceback.format_exc())


    # 处理1条message数据
    def insert_one_message_to_dingodb(self, temp_message, insert_dingodb_sql, insert_dingodb_values):
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


    # 执行插入dingodb的sql语句
    def insert_many_into_dingodb(self, insert_dingodb_sql, insert_dingodb_values):
        # 执行sql
        try:
            # 执行插入语句
            aliyun_dingodb_utils.insert_many(insert_dingodb_sql, insert_dingodb_values)
            print(f"success execute sql: {insert_dingodb_sql}")
            print(f"success insert message to dingodb: {insert_dingodb_values}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def list_messages_from_dingodb(self, message_type, query_conditions, page, page_size, sort_keys, sort_dirs):
        try:
            # 判空
            if not message_type:
                raise Fail("message type is empty", error_message="消息类型不能为空")
            # 未知消息类型
            if message_type not in MESSAGE_TYPE_TABLE:
                raise Fail("message type not exists", error_message="消息类型不存在")
            # 获取数据
            return aliyun_dingodb_utils.list_messages(MESSAGE_TYPE_TABLE[message_type], query_conditions, page, page_size, sort_keys, sort_dirs)
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def count_messages_from_dingodb(self, message_type, query_conditions):
        try:
            # 判空
            if not message_type:
                raise Fail("message type is empty", error_message="消息类型不能为空")
            # 未知消息类型
            if message_type not in MESSAGE_TYPE_TABLE:
                raise Fail("message type not exists", error_message="消息类型不存在")
            # 获取数据
            return aliyun_dingodb_utils.count_messages(MESSAGE_TYPE_TABLE[message_type], query_conditions)
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def list_messages_from_dingodb_by_sql(self, sql):
        try:
            # 判空
            if not sql:
                raise Fail("sql is empty", error_message="数据库查询语句不能为空")
            # sql注入检测
            self.validate_sql(sql)
            # 获取数据
            return aliyun_dingodb_read_utils.list_messages_by_sql(sql)
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    # 进行sql检测
    def validate_sql(self, sql: str):
        # 只允许SELECT查询
        if not re.match(r'^SELECT\s.+', sql, re.IGNORECASE):
            raise Fail("sql is only select", error_message="数据库查询语句只允许查询操作")
        # 禁止危险关键词
        forbidden_keywords = ['DROP ', 'DELETE ', 'UPDATE ', 'INSERT ', 'ALTER ']
        for keyword in forbidden_keywords:
            if keyword in sql.upper():
                raise Fail("sql is only select", error_message="数据库查询语句只允许查询操作")
