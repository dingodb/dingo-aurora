import uuid
import json

from apscheduler.schedulers.background import BackgroundScheduler

from common.ironic_client import ironic_client
from common.nova_client import nova_client
from db.models.asset_resoure_relation.models import AssetResourceRelationInfo
from db.models.asset_resoure_relation.sql import AssetResourceRelationSQL
from services.assets import AssetsService
from utils import datetime as datatime_util
from datetime import datetime

relation_scheduler = BackgroundScheduler()
assert_service = AssetsService()

def start():
    relation_scheduler.add_job(fetch_relation_info, 'interval', seconds=300, next_run_time=datetime.now())
    relation_scheduler.start()

def fetch_relation_info():
    # 读取所有裸机数据、读取所有资产数据，对比数据根据ip进行比对，相同的ip则建立关联关系
    print(f"同步资源与资产的关联关系开始时间: {datatime_util.get_now_time_in_timestamp_format()}")
    try:
        # 1、读取裸金属列表
        node_list = ironic_client.ironic_list_nodes()
        print(f"裸金属列表数据: {node_list}")
        # 2、读取所有的资产数据
        query_params = {}
        asset_result = assert_service.list_assets(query_params, 1, 1000, None, None)
        print(f"资产列表数据: {asset_result}")
        # 3、查询所有虚拟机
        # server_list = nova_client.nova_list_servers()
        # print(f"虚拟机列表数据: {server_list}")
        # 数据判空
        if not node_list or not asset_result or not asset_result.get('data'):
            print("裸金属列表数据或资产列表数据为空")
            return
        # 4、数据遍历，对比裸金属与资产数据
        asset_resource_relation_list = []
        for temp_node in node_list:
            print(f"裸金属数据:{temp_node}")
            # uuid是裸金属的id  instance_uuid是对应的虚拟机的id
            #print(f"裸金属列表数据:{temp_node.get('uuid')}")
            server_detail = None
            if temp_node.get('instance_uuid'):
                server_detail = nova_client.nova_get_server_detail(temp_node.get('instance_uuid'))
                print(f"虚拟机详情数据: {server_detail}")
            # 裸金属的ipmi的ip地址
            ipmi_address = temp_node.get('driver_info').get('ipmi_address') if temp_node.get('driver_info') else None
            # 与裸机对应的资产的id
            asset_id = None
            # 遍历资产查找与裸机ipmi的IP能对应的数据
            for temp_asset in asset_result.get('data'):
                # 资产的ip地址
                # 定义扩展字段
                extra_json = {}
                try:
                    if temp_asset['extra']:
                        extra_json = json.loads(temp_asset['extra'])
                except Exception as e:
                    print(f"解析资产扩展字段失败: {e}")
                asset_ips = extra_json["ip"] if extra_json and "ip" in extra_json else None
                if asset_ips:
                    # 资产的ip地址可能是多个ip地址，使用逗号分隔
                    asset_ip_array = asset_ips.split(',')
                    # 非空
                    if asset_ip_array:
                        for temp_asset_ip in asset_ip_array:
                            if temp_asset_ip == ipmi_address:
                                asset_id = temp_asset.get('asset_id')
                                break
            # 组装数据
            temp_relation = AssetResourceRelationInfo(
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
            if temp_relation.resource_user_id:
                user = ironic_client.keystone_get_user_by_id(temp_relation.resource_user_id)
                if user:
                    temp_relation.resource_user_name = user.get('name')
            if temp_relation.resource_project_id:
                project = ironic_client.keystone_get_project_by_id(temp_relation.resource_project_id)
                if project:
                    temp_relation.resource_project_name = project.get('name')
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
    except Exception as e:
        print(f"同步资源与资产关系失败: {e}")
    print(f"同步资源与资产的关联关系结束时间: {datatime_util.get_now_time_in_timestamp_format()}")
