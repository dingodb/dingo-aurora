# rabbit的shovel类, 启动的时候自动add shovel，先删除，再add
# 每个mq的pod都需要shovel
import requests
from oslo_config import cfg

from dingo_command.utils.constant import MQ_MANAGE_PORT, MQ_SHOVEL_ADD_URL, RABBITMQ_SHOVEL_QUEUE

# 默认文件配置
CONF = cfg.CONF
MY_IP = CONF.DEFAULT.my_ip
TRANSPORT_URL = CONF.DEFAULT.transport_url
CENTER_TRANSPORT_URL = CONF.DEFAULT.center_transport_url
CENTER_REGION_FLAG = CONF.DEFAULT.center_region_flag

class RabbitMqConfigService:

    def get_convert_mq_url(self):
        try:
            # 转换mq的原始的地址
            transport_url = TRANSPORT_URL.replace("rabbit:", "").replace("//", "")
            center_transport_url = CENTER_TRANSPORT_URL.replace("rabbit:", "").replace("//", "")
            return transport_url, center_transport_url
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None

    def get_convert_mq_url_array(self):
        try:
            # 转换地址为array
            transport_url, center_transport_url = self.get_convert_mq_url()
            return transport_url.split(','), center_transport_url.split(',')
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None

    def add_shovel(self):
        # 开启rabbitmq创建逻辑
        try:
            # 中心region不需要创建铲子，现在是从普通region铲消息到中心region
            if CENTER_REGION_FLAG:
                print("current region is center region, no need to add shovel")
                return
            # 没有shovel配置
            if not RABBITMQ_SHOVEL_QUEUE:
                print("rabbit shovel queue is empty")
                return
            # mq的transport_url是空
            if not TRANSPORT_URL or not CENTER_TRANSPORT_URL:
                print("rabbit mq transport_url or center_transport_url is empty ")
                return
            # 解析mq的url
            transport_url_array, center_transport_url_array = self.get_convert_mq_url_array()
            # 空
            if transport_url_array is None or len(transport_url_array) <= 0:
                print("rabbit mq transport url array is empty ")
                return
            # 空
            if center_transport_url_array is None or len(center_transport_url_array) <= 0:
                print("center region rabbit mq transport url array is empty ")
                return
            # 读取当前的mq的用户名、密码、mq的url
            user_name, password, src_mq_url = self.get_current_mq_config_info()
            # 判空
            if not user_name or not password or not src_mq_url:
                print("rabbit mq user name or password or src_mq_url is empty ")
                return
            # 遍历需要创建的shovel的队列
            for shovel_name, queue_name in RABBITMQ_SHOVEL_QUEUE.items():
                # 当前环境的mq管理地址RabbitMQ 管理 API 的 URL 和认证信息
                shovel_url = "http://" + MY_IP + ":" + MQ_MANAGE_PORT + MQ_SHOVEL_ADD_URL + shovel_name + "_" +  MY_IP
                print("shovel_url: " + shovel_url)
                # 遍历中心region的mq的url
                dest_mq_url_array = []
                for temp_url in center_transport_url_array:
                    dest_mq_url_array.append("amqp://" + temp_url)
                # 默认用户名和密码
                auth = (user_name, password)
                # Shovel 配置
                shovel_config = {
                    "value": {
                        "src-uri": "amqp://" + src_mq_url,
                        "src-queue": queue_name,
                        "dest-uri": dest_mq_url_array,
                        "dest-queue": queue_name,
                        "ack-mode": "on-confirm",
                        "reconnect-delay": 5
                    }
                }
                # 创建前删除掉原来的shovel
                delete_response = requests.delete(shovel_url, auth=auth)
                print(f"Shovel Deleted,状态码：{delete_response.status_code}, 响应内容：{delete_response.text} ")
                # 发送 HTTP 请求创建 Shovel
                response = requests.put(shovel_url, auth=auth, json=shovel_config)
                # 检查响应状态
                if response.status_code == 201:
                    print("Shovel 创建成功！")
                else:
                    print(f"Shovel 创建失败，状态码：{response.status_code}, 响应内容：{response.text}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            return

    # 获取当前的mq的的用户名、密码、mq的url
    def get_current_mq_config_info(self):
        # 声明配置参数
        user_name = None
        password = None
        src_mq_url = None
        # 解析mq的url
        transport_url_array, _ = self.get_convert_mq_url_array()
        # 判空
        if transport_url_array is None or len(transport_url_array) <= 0:
            print("rabbit mq transport url array is empty ")
            return None
        # 遍历
        for temp_url in transport_url_array:
            # 当前节点的mq信息
            if MY_IP in temp_url:
                # 当前节点的mq的url
                src_mq_url = temp_url
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
        return user_name, password, src_mq_url
