
# 大屏的shovel类, 启动的时候自动add shovel，先删除，再add
# 每个mq的pod都需要shovel
import requests
from oslo_config import cfg

# 多region情况下大屏的shovel的名称
MQ_MANAGE_PORT = "15672"
MQ_SHOVEL_ADD_URL = "/api/parameters/shovel/%2F/"
SHOVEL_NAME_PREFIX = "big_screen_sync_shovel_"
SHOVEL_QUEUE = "multi_region_big_screen_queue"
# 默认文件配置
CONF = cfg.CONF
# 环境的vip
VIP = CONF.DEFAULT.vip
MY_IP = CONF.DEFAULT.my_ip
TRANSPORT_URL = CONF.DEFAULT.transport_url
CENTER_TRANSPORT_URL = CONF.DEFAULT.center_transport_url
CENTER_REGION_FLAG = CONF.DEFAULT.center_region_flag
# print(VIP)
# print(MY_IP)
# print(TRANSPORT_URL)
# print(CENTER_TRANSPORT_URL)

class BigScreenShovelService:

    @classmethod
    def add_shovel(self):
        # 中心region不需要创建铲子，现在是从普通region铲消息到中心region
        if CENTER_REGION_FLAG:
            print("current region is center region, no need to add shovel")
            return
        # 当前环境的mq管理地址RabbitMQ 管理 API 的 URL 和认证信息
        shovel_url = "http://" + MY_IP + ":" + MQ_MANAGE_PORT + MQ_SHOVEL_ADD_URL + SHOVEL_NAME_PREFIX +  MY_IP
        print("shovel_url: " + shovel_url)
        # 处理mq读取用户命和密码
        if TRANSPORT_URL is None:
            print("rabbit mq transport_url is empty ")
            return
        # mq的处理后的地址
        transport_url = TRANSPORT_URL.replace("rabbit:", "").replace("//", "")
        center_transport_url = CENTER_TRANSPORT_URL.replace("rabbit:", "").replace("//", "")
        # 多节点环境
        transport_url_array = transport_url.split(',')
        center_transport_url_array = center_transport_url.split(',')
        # 空
        if transport_url_array is None or len(transport_url_array) <= 0:
            print("rabbit mq transport url array is empty ")
            return
        # 空
        if center_transport_url_array is None or len(center_transport_url_array) <= 0:
            print("center region rabbit mq transport url array is empty ")
            return
        user_name = None
        password = None
        src_mq_url = None
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
                "src-queue": SHOVEL_QUEUE,
                "dest-uri": dest_mq_url_array,
                "dest-queue": SHOVEL_QUEUE,
                "ack-mode": "on-confirm",
                "reconnect-delay": 5
            }
            # 一次创建多个
            # "value": {
            #     "src-uri": ["amqp://user:password@source-node1:5672", "amqp://user:password@source-node2:5672"],
            #     "src-queue": "source_queue",
            #     "dest-uri": ["amqp://user:password@destination-node1:5672", "amqp://user:password@destination-node2:5672"],
            #     "dest-exchange": "destination_exchange",
            #     "ack-mode": "on-confirm",
            #     "reconnect-delay": 5
            # }
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

    # 自动创建shovel
    @classmethod
    def auto_add_shovel(self):
        # 启动的时候自动创建shovel
        pass

if __name__=="__main__":
    BigScreenShovelService().add_shovel()