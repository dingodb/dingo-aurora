# 资产的service层
import json
import logging
import os
import shutil
import uuid
from io import BytesIO

import pandas as pd
from datetime import datetime

from openpyxl.reader.excel import load_workbook
from openpyxl.styles import Border, Side
from typing_extensions import assert_type

from dingoops.celery_api.celery_app import celery_app
from dingoops.db.models.cluster.sql import ClusterSQL
from dingoops.db.models.node.sql import NodeSQL
from dingoops.db.models.instance.sql import InstanceSQL
from math import ceil
from oslo_log import log
from dingoops.api.model.cluster import ClusterTFVarsObject, NodeGroup, ClusterObject
from dingoops.api.model.instance import InstanceConfigObject, InstanceCreateObject
from dingoops.api.model.base import BaseResponse, ErrorResponse, ErrorDetail
from dingoops.db.models.cluster.models import Cluster as ClusterDB
from dingoops.db.models.node.models import NodeInfo as NodeDB
from dingoops.db.models.instance.models import Instance as InstanceDB
from dingoops.utils import neutron
from dingoops.services.cluster import ClusterService

from dingoops.services.custom_exception import Fail
from dingoops.services.system import SystemService



LOG = log.getLogger(__name__)
BASE_DIR = os.getcwd()

# 定义边框样式
thin_border = Border(
    left=Side(border_style="thin", color="000000"),  # 左边框
    right=Side(border_style="thin", color="000000"),  # 右边框
    top=Side(border_style="thin", color="000000"),  # 上边框
    bottom=Side(border_style="thin", color="000000")  # 下边框
)

class InstanceService:

    # 查询资产列表
    @classmethod
    def list_instances(cls, query_params, page, page_size, sort_keys, sort_dirs):
        # 业务逻辑
        try:
            # 按照条件从数据库中查询数据
            count, data = InstanceSQL.list_instances(query_params, page, page_size, sort_keys, sort_dirs)
            # 返回数据
            res = {}
            # 页数相关信息
            if page and page_size:
                res['currentPage'] = page
                res['pageSize'] = page_size
                res['totalPages'] = ceil(count / int(page_size))
            res['total'] = count
            res['data'] = data
            return res
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None

    def get_instance(self, instance_id):
        if not instance_id:
            return None
        # 详情
        try:
            # 根据id查询
            query_params = {}
            query_params["id"] = instance_id
            res = self.list_instances(query_params, 1, 10, None, None)
            # 空
            if not res or not res.get("data"):
                return BaseResponse(data=None)
            # 返回第一条数据
            return BaseResponse(data=res.get("data")[0])
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def create_instance(self, instance: InstanceCreateObject):
        # 在这里使用openstack的api接口，直接创建vm或者裸金属，根据type类型决定是创建vm还是裸金属，走不同的流程
        # 创建instance，创建openstack种的虚拟机或者裸金属服务器，如果属于某个cluster就写入cluster_id
        # 数据校验 todo
        try:
            number = instance.numbers
            if number == 0:
                return ErrorResponse(code=400, status="fail", message="number parameter is 0, no instance is created",
                                     error=ErrorDetail(type="ValidationError"))
            # 写入instance信息到数据库中
            instance_info_db_list, instance_list = self.convert_instance_todb(instance)
            InstanceSQL.create_instance_list(instance_info_db_list)
            # 获取openstack的参数，传入到create_instance的方法中，由这create_instance创建vm或者裸金属
            # 调用celery_app项目下的work.py中的create_instance方法
            result = celery_app.send_task("dingoops.celery_api.workers.create_instance",
                                          args=[instance.dict(), instance_list])
            return BaseResponse(data=result.id)
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def delete_instance(self, instance_list_info):
        if not instance_list_info:
            return None
        # 详情
        try:
            openstack_info = instance_list_info.openstack_info
            instance_list = instance_list_info.instance_list
            # 具体要操作的步骤，删除openstack中的server，删除数据库中instance表里面的该instance的数据
            instance_list_db, instance_list_json = self.update_instance_todb(instance_list)
            InstanceSQL.update_instance_list(instance_list_db)
            # 调用celery_app项目下的work.py中的delete_instance方法
            result = celery_app.send_task("dingoops.celery_api.workers.delete_instance",
                                          args=[openstack_info.dict(), instance_list_json])
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def convert_instance_todb(self, instance_info):
        instance_info_db_list = []
        if instance_info.numbers == 1:
            instance_info_db = InstanceDB()
            instance_info_db.id = str(uuid.uuid4())
            instance_info_db.name = instance_info.name
            instance_info_db.status = "creating"
            instance_info_db.server_id = ""
            instance_info_db.openstack_id = ""
            instance_info_db.ip_address = ""
            instance_info_db.operation_system = ""
            instance_info_db.user = instance_info.user
            instance_info_db.password = instance_info.password
            instance_info_db.cpu = ""
            instance_info_db.gpu = ""
            instance_info_db.mem = ""
            instance_info_db.disk = ""
            instance_info_db.node_type = instance_info.node_type
            instance_info_db.flavor_id = instance_info.flavor_id
            instance_info_db.image_id = instance_info.image_id
            instance_info_db.network_id = instance_info.network_id
            instance_info_db.subnet_id = instance_info.subnet_id
            instance_info_db.cluster_id = instance_info.cluster_id
            instance_info_db.cluster_name = instance_info.cluster_name
            instance_info_db.project_id = instance_info.openstack_info.project_id
            instance_info_db.sshkey_name = instance_info.sshkey_name
            instance_info_db.security_group = instance_info.security_group
            instance_info_db.region = instance_info.openstack_info.region
            instance_info_db_list.append(instance_info_db)
        else:
            for i in range(1, int(instance_info.numbers) + 1):
                instance_info_db = InstanceDB()
                instance_info_db.id = str(uuid.uuid4())
                instance_info_db.name = instance_info.name + "-" + str(i)
                instance_info_db.status = "creating"
                instance_info_db.server_id = ""
                instance_info_db.openstack_id = ""
                instance_info_db.ip_address = ""
                instance_info_db.operation_system = ""
                instance_info_db.user = instance_info.user
                instance_info_db.password = instance_info.password
                instance_info_db.cpu = ""
                instance_info_db.gpu = ""
                instance_info_db.mem = ""
                instance_info_db.disk = ""
                instance_info_db.node_type = instance_info.node_type
                instance_info_db.flavor_id = instance_info.flavor_id
                instance_info_db.image_id = instance_info.image_id
                instance_info_db.network_id = instance_info.network_id
                instance_info_db.subnet_id = instance_info.subnet_id
                instance_info_db.cluster_id = instance_info.cluster_id
                instance_info_db.cluster_name = instance_info.cluster_name
                instance_info_db.project_id = instance_info.openstack_info.project_id
                instance_info_db.sshkey_name = instance_info.sshkey_name
                instance_info_db.security_group = instance_info.security_group
                instance_info_db.region = instance_info.openstack_info.region
                instance_info_db_list.append(instance_info_db)

        instance_list_dict = []
        for instance in instance_info_db_list:
            # Create a serializable dictionary from the instanceDB object
            instance_dict = {
                "id": instance.id,
                "instance_type": instance.node_type,
                "cluster_id": instance.cluster_id,
                "cluster_name": instance.cluster_name,
                "region": instance.region,
                "image_id": instance.image_id,
                "project_id": instance.project_id,
                "security_group": instance.security_group,
                "flavor_id": instance.flavor_id,
                "status": instance.status,
                "name": instance.name,
                "create_time": instance.create_time.isoformat() if instance.create_time else None
            }
            instance_list_dict.append(instance_dict)

        # Convert the list of dictionaries to a JSON string
        instance_list_json = json.dumps(instance_list_dict)
        return instance_info_db_list, instance_list_json
    
    def update_instance_todb(self, instance_list):
        instance_list_db = []
        for instance in instance_list:
            instance_info_db = InstanceDB()
            instance_info_db.id = instance.id
            instance_info_db.status = "deleting"
            instance_info_db.update_time = datetime.now()
            instance_list_db.append(instance_info_db)
        instance_list_dict = []
        for instance in instance_list_db:
            # Create a serializable dictionary from the instanceDB object
            instance_dict = {
                "id": instance.id,
                "status": instance.status,
                "update_time": instance.update_time
            }
            instance_list_dict.append(instance_dict)

        # Convert the list of dictionaries to a JSON string
        instance_list_json = json.dumps(instance_list_dict)
        return instance_list_db, instance_list_json