import uuid
import json

from apscheduler.schedulers.background import BackgroundScheduler

from common.ironic_client import ironic_client
from common.nova_client import nova_client
from db.models.asset_resoure_relation.models import AssetResourceRelationInfo
from db.models.asset_resoure_relation.sql import AssetResourceRelationSQL
from services.assets import AssetsService
from services.bigscreens import BigScreensService
from utils import datetime as datatime_util
from datetime import datetime, timedelta

relation_scheduler = BackgroundScheduler()
assert_service = AssetsService()

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
                    print(f"获取虚拟机详情失败：{e}")
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
        user = None
        try:
            user = ironic_client.keystone_get_user_by_id(temp_relation.resource_user_id)
        except Exception as e:
            print(f"获取资源[{temp_relation.resource_name}]的用户[{temp_relation.resource_user_id}]名称报错：{e}")
        if user:
            temp_relation.resource_user_name = user.get('name')
    if temp_relation.resource_project_id:
        project = None
        try:
            project = ironic_client.keystone_get_project_by_id(temp_relation.resource_project_id)
        except Exception as e:
            print(f"获取资源[{temp_relation.resource_name}]的项目[{temp_relation.resource_project_id}]名称报错：{e}")
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
        # 读取所有裸机关联关系数据
        asset_resource_relation_list = AssetResourceRelationSQL.get_all_asset_resource_relation()
        # 非空
        if asset_resource_relation_list:
            for temp_relation in asset_resource_relation_list:
                # 通过config的metrics查询资源的使用率信息
                print(f"当前的资源是{temp_relation.resource_id}")
                # 读取裸机的监控数据
                promql = "DCGM_FI_DEV_MEM_CLOCK{Hostname=\"k8s-demo-gpu-11-80\"}"
                metrics = BigScreensService.fetch_metrics_with_promql(promql)
                print(f"裸机的的测试监控数据: {metrics}")
        # 读取每一个资源的监控数据信息
        print(f"读取资源的监控数据项数据开始: {datatime_util.get_now_time_in_timestamp_format()}")
    except Exception as e:
        print(f"读取资源的监控数据项失败: {e}")