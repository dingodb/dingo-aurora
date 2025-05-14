import uuid
import json

from apscheduler.schedulers.background import BackgroundScheduler

from dingo_command.common.ironic_client import ironic_client
from dingo_command.common.nova_client import nova_client
from dingo_command.db.models.asset_resoure_relation.models import AssetResourceRelationInfo
from dingo_command.db.models.asset_resoure_relation.sql import AssetResourceRelationSQL
from dingo_command.db.models.asset.sql import AssetSQL
from dingo_command.services.assets import AssetsService
from dingo_command.services.bigscreens import BigScreensService
from dingo_command.services.resources import ResourcesService
from dingo_command.utils import datetime as datatime_util
from datetime import datetime, timedelta

relation_scheduler = BackgroundScheduler()
assert_service = AssetsService()
resource_service = ResourcesService()

def start():
    relation_scheduler.add_job(fetch_relation_info, 'interval', seconds=300, next_run_time=datetime.now())
    relation_scheduler.add_job(fetch_resource_metrics_info, 'interval', seconds=300, next_run_time=datetime.now() + timedelta(seconds=30))
    relation_scheduler.start()

def fetch_relation_info():
    # 读取所有裸机数据、读取所有资产数据，对比数据根据ip进行比对，相同的ip则建立关联关系
    print(f"同步资源与资产的关联关系开始时间: {datatime_util.get_now_time_in_timestamp_format()}")
    try:
        # 1、读取裸金属列表
        node_list = ironic_client.ironic_list_nodes()
        print(f"裸金属列表数据: {node_list}")
        # 2、读取所有的资产数据
        asset_list = get_all_asset_list()
        print(f"资产数据数目：{len(asset_list)}, 裸机节点数目：{len(node_list)}")
        # 3、查询所有虚拟机
        # server_list = nova_client.nova_list_servers()
        # print(f"虚拟机列表数据: {server_list}")
        # 数据判空
        if not node_list or not asset_list :
            print("裸金属列表数据或资产列表数据为空")
            return
        # 4、数据遍历，对比裸金属与资产数据
        asset_resource_relation_list = []
        resource_id_list = []
        for temp_node in node_list:
            print(f"裸金属数据:{temp_node}")
            # uuid是裸金属的id  instance_uuid是对应的虚拟机的id
            resource_id_list.append(temp_node.get('uuid'))
            #print(f"裸金属列表数据:{temp_node.get('uuid')}")
            server_detail = None
            if temp_node.get('instance_uuid'):
                try:
                    server_detail = nova_client.nova_get_server_detail(temp_node.get('instance_uuid'))
                    print(f"虚拟机详情数据: {server_detail}")
                except Exception as e:
                    print(f"虚拟机[{temp_node.get('instance_uuid')}]详情数据失败: {e}")
            # 裸金属的ipmi的ip地址
            ipmi_address = temp_node.get('driver_info').get('ipmi_address') if temp_node.get('driver_info') else None
            # 与裸机对应的资产的id
            asset_id = None
            # 遍历资产查找与裸机ipmi的IP能对应的数据
            for temp_asset in asset_list:
                # 资产的ip地址
                asset_ips = get_asset_ip(temp_asset)
                if asset_ips and ipmi_address and ipmi_address in asset_ips:
                    # ipmi的ip地址与资产的ip地址相同
                    asset_id = temp_asset.get('asset_id')
                    break
            # 组装数据
            temp_relation = init_asset_resource_relation(temp_node, asset_id, server_detail)
            # 追加资源的用户和项目名称
            attach_user_and_project(temp_relation)
            # 加入到列表中
            asset_resource_relation_list.append(temp_relation)
        # 保存数据
        if asset_resource_relation_list:
            for temp_relation in asset_resource_relation_list:
                # 查询数据库中的数据
                db_relation = AssetResourceRelationSQL.get_asset_resource_relation_by_resource_id(temp_relation.resource_id)
                # 如果数据库中没有数据，则插入数据
                if not db_relation:
                    # 数据插入
                    AssetResourceRelationSQL.create_asset_resource_relation(temp_relation)
                else:
                    # 数据更新
                    update_asset_resource_relation(db_relation, temp_relation)
        # 删除掉已经不存在的资源数据
        # 读取所有裸机关联关系数据
        asset_resource_relation_list = AssetResourceRelationSQL.get_all_asset_resource_relation()
        if asset_resource_relation_list:
            # 读取所有裸机的id
            for temp_db_relation in asset_resource_relation_list:
                # 数据不在资源列表中
                if temp_db_relation.resource_id not in resource_id_list:
                    # 数据删除
                    AssetResourceRelationSQL.delete_asset_resource_relation_by_resource_id(temp_db_relation.resource_id)

        # 处理资产表中未关联资源的数据的标识状态
        handle_asset_table_relation_resource_flag()
    except Exception as e:
        print(f"同步资源与资产关系失败: {e}")
    print(f"同步资源与资产的关联关系结束时间: {datatime_util.get_now_time_in_timestamp_format()}")

# 初始化资源与资产关联关系
def init_asset_resource_relation(temp_node, asset_id, server_detail):
    # 初始化然后返回
    return AssetResourceRelationInfo(
        id=uuid.uuid4().hex,
        resource_id=temp_node.get('uuid'),
        asset_id=asset_id,
        resource_type='baremetal',
        resource_name=temp_node.get('instance_info').get('display_name') if temp_node.get('instance_info') else None,
        resource_status=temp_node.get('provision_state'),
        resource_ip=temp_node.get('driver_info').get('ipmi_address') if temp_node.get('driver_info') else None,
        resource_user_id=server_detail.get('user_id') if server_detail else None,
        resource_project_id=server_detail.get('tenant_id') if server_detail else None,
        create_date=datetime.fromtimestamp(datetime.now().timestamp()),
    )

# 更新资产资源关系
def update_asset_resource_relation(db_relation, temp_relation):
    # 数据更新
    db_relation.asset_id = temp_relation.asset_id
    db_relation.resource_name = temp_relation.resource_name
    db_relation.resource_status = temp_relation.resource_status
    db_relation.resource_ip = temp_relation.resource_ip
    db_relation.resource_user_id = temp_relation.resource_user_id
    db_relation.resource_user_name = temp_relation.resource_user_name
    db_relation.resource_project_id = temp_relation.resource_project_id
    db_relation.resource_project_name = temp_relation.resource_project_name
    db_relation.update_date = datetime.fromtimestamp(datetime.now().timestamp())
    AssetResourceRelationSQL.update_asset_resource_relation(db_relation)

# 追加资源的用户和项目名称
def attach_user_and_project(temp_relation):
    # 追加资源的用户和项目名称
    if temp_relation.resource_user_id:
        user = ironic_client.keystone_get_user_by_id(temp_relation.resource_user_id)
        if user:
            temp_relation.resource_user_name = user.get('name')
    if temp_relation.resource_project_id:
        project = ironic_client.keystone_get_project_by_id(temp_relation.resource_project_id)
        if project:
            temp_relation.resource_project_name = project.get('name')

# 查询所有的资产列表
def get_all_asset_list():
    # 定义查询参数
    query_params = {}
    page = 1
    page_size = 1000
    # 定义返回列表
    asset_list = []
    # 查询
    try:
        # 查询一次
        asset_result = assert_service.list_assets(query_params, page, page_size, None, None)
        # 非空
        if asset_result and asset_result.get('data'):
            # 读取资产列表
            asset_list = asset_result.get('data')
            # 判断是否还有数据
            while len(asset_result.get('data')) == page_size:
                # 查询下一页
                page += 1
                asset_result = assert_service.list_assets(query_params, page, page_size, None, None)
                # 非空
                if asset_result and asset_result.get('data'):
                    asset_list.extend(asset_result.get('data'))
    except Exception as e:
        print(f"查询资产列表失败: {e}")
    # 返回资产列表
    return asset_list

# 获取资产数据的ip字段
def get_asset_ip(asset):
    # 定义扩展字段
    extra_json = {}
    try:
        # ip在扩展字段中
        if asset['extra']:
            extra_json = json.loads(asset['extra'])
        # 获取ip地址
        return extra_json["ip"] if extra_json and "ip" in extra_json else None
    except Exception as e:
        print(f"解析资产扩展字段失败: {e}")

# 读取资源的监控数据项数据
def fetch_resource_metrics_info():
    # 读取资源的监控数据项数据
    print(f"读取资源的监控数据项数据开始: {datatime_util.get_now_time_in_timestamp_format()}")
    try:
        # 读取所有资源需要的指标配置项
        resource_metrics_config_list = AssetResourceRelationSQL.get_all_resource_metrics_config()
        # 空
        if not resource_metrics_config_list:
            print("资源的监控数据项配置数据为空，不需要采集资源的监控指标数据")
            return
        # 读取所有裸机关联关系数据
        asset_resource_relation_list = AssetResourceRelationSQL.get_all_asset_resource_relation()
        # 非空
        resource_id_list = []
        if asset_resource_relation_list:
            for temp_relation in asset_resource_relation_list:
                # 资源的名称作为查询监控项的入参，如果None则不需要查询，直接进入下次循环
                if not temp_relation.resource_name:
                    continue
                # 通过config的metrics查询资源的使用率信息
                print(f"当前的资源：{temp_relation.resource_id}")
                resource_id_list.append(temp_relation.resource_id)
                # 资源的监控数据项
                temp_resource_metrics_dict = {}
                # 遍历监控指标项
                for temp_config in resource_metrics_config_list:
                    # 读取配置项的查询query字符串，写入参数，组装promql
                    data = {"host_name": temp_relation.resource_name}
                    promql = temp_config.query.format(**data)
                    print(f"查询promql语句是{promql}")
                    metrics_json = BigScreensService.fetch_metrics_with_promql(promql)
                    # if temp_config.name == "gpu_count":
                    #     metrics_json = {"status":"success","data":{"resultType":"vector","result":[{"metric":{},"value":[1747031802.721,"8"]}],"analysis":{}}}
                    # elif temp_config.name == "cpu_usage":
                    #     metrics_json = {"status":"success","data":{"resultType":"vector","result":[{"metric":{"instance":"10.201.49.1:9100"},"value":[1747031746.604,"1.6218749999663329"]}],"analysis":{}}}
                    # elif temp_config.name == "memory_usage":
                    #     metrics_json = {"status":"success","data":{"resultType":"vector","result":[{"metric":{"hostname":"hd03-gpu2-0001","ib_addr":"192.168.1.1","instance":"10.201.49.1:9100","job":"consul","node_role":"k8s","region":"hd-03"},"value":[1747031684.197,"27.14990270986004"]}],"analysis":{}}}
                    # elif temp_config.name == "gpu_power":
                    #     metrics_json = {"status":"success","data":{"resultType":"vector","result":[{"metric":{"hostname":"hd03-gpu2-0001","ib_addr":"192.168.1.1","instance":"10.201.49.1:9100","job":"consul","node_role":"k8s","region":"hd-03"},"value":[1747031684.197,"27.14990270986004"]}],"analysis":{}}}
                    print(f"监控项：{temp_config.name}数据:{metrics_json}")
                    metrics_value = handle_metrics_json(metrics_json)
                    temp_resource_metrics_dict[temp_config.name] = metrics_value
                # 存入数据库
                resource_service.update_resource_metrics(temp_relation.resource_id, temp_resource_metrics_dict)

            # 删除资源metrics中资源已经不存在的数据
            print(f"资源ID列表：{resource_id_list}")
            if not resource_id_list:
                AssetResourceRelationSQL.delete_all_resource_metrics()
            else:
                AssetResourceRelationSQL.delete_resource_metrics_outside_resource_id_list(resource_id_list)
        else: # 资源与资产关联表为空，则删除资源metrics表中所有数据
            print("资源与资产关联表为空，删除资源metrics表中所有数据")
            AssetResourceRelationSQL.delete_all_resource_metrics()

        # 读取每一个资源的监控数据信息
        print(f"读取资源的监控数据项数据开始: {datatime_util.get_now_time_in_timestamp_format()}")
    except Exception as e:
        print(f"读取资源的监控数据项失败: {e}")


# 处理prometheus的返回数据
def handle_metrics_json(metrics_json):
    try:
        # 数据不为空
        if metrics_json:
            # 数据的状态为success
            if metrics_json['status'] == 'success':
                # 数据对象
                json_data = metrics_json['data']
                # 数据结果
                json_data_result = json_data['result']
                # 读取数据结果中的value数值
                if json_data_result:
                    # "value":[1747031802.721,"8"], 其中第一个数据1747031802.721为时间戳，第二个数据"8"为需要的数据
                    return json_data_result[0]['value'][1]
    except Exception as e:
        print(f"解析监控数据项失败: {e}")
    # 返回None
    return None


def handle_asset_table_relation_resource_flag():
    relation_resources = AssetResourceRelationSQL.get_asset_id_not_empty_list()
    asset_id_list_in_relation_resource = None
    if relation_resources is not None:
        asset_id_list_in_relation_resource = [getattr(r, "asset_id") for r in relation_resources]

    print(f"资源关联资产表中资产ID集合: {asset_id_list_in_relation_resource}")
    if asset_id_list_in_relation_resource is None:
        # 修改所有资产关联资源标识为True的数据为false
        set_all_asset_relation_resource_flag_to_false()
    else:
        for asset_id_in_relation_resource in asset_id_list_in_relation_resource:
            # 设置资源关联资产标识为True
            set_single_asset_relation_resource_flag_to_true(asset_id_in_relation_resource)

        # 设置资源关联资产外的资产关联标识为true->false
        not_relation_resource_asset_info = AssetSQL.get_all_asset_basic_info_with_relation_resource_excluding_ids(
            asset_id_list_in_relation_resource)
        if not_relation_resource_asset_info is not None:
            for asset_info_db in not_relation_resource_asset_info:
                asset_info_db.asset_relation_resource_flag = False
                AssetSQL.update_asset(asset_info_db, None, None, None, None, None, None, None,
                                      None)

def set_all_asset_relation_resource_flag_to_false():
    asset_basic_info_with_relation_resource = AssetSQL.get_all_asset_basic_info_with_relation_resource()
    if asset_basic_info_with_relation_resource is not None:
        for asset_basic_info in asset_basic_info_with_relation_resource:
            asset_basic_info.asset_relation_resource_flag = False
            AssetSQL.update_asset(asset_basic_info, None, None, None, None, None, None, None,
                                  None)

def set_single_asset_relation_resource_flag_to_true(asset_id):
    if asset_id is not None:
        asset_basic_info = AssetSQL.get_asset_basic_info_by_id(asset_id)
        if asset_basic_info is not None and asset_basic_info.asset_relation_resource_flag is False:
            asset_basic_info.asset_relation_resource_flag = True
            AssetSQL.update_asset(asset_basic_info, None, None, None, None, None, None, None, None)
