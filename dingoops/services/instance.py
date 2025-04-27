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
from dingoops.api.model.instance import InstanceConfigObject
from dingoops.db.models.cluster.models import Cluster as ClusterDB
from dingoops.db.models.node.models import NodeInfo as NodeDB
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

system_service = SystemService()

class InstanceService:

    def get_az_value(self, node_type):
        """根据节点类型返回az值"""
        return "nova" if node_type == "vm" else ""

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
                return None
            # 返回第一条数据
            return res.get("data")[0]
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def convert_clusterinfo_todb(self, cluster:ClusterObject):
        cluster_info_db = ClusterDB()
        cluster_info_db.id = cluster.id
        cluster_info_db.status = "scaling"
        cluster_info_db.update_time = datetime.now()
        for node_conf in cluster.node_config:
            if node_conf.role == "worker":
                cluster_info_db.worker_count += node_conf.count
        return cluster_info_db

    def update_clusterinfo_todb(self, cluster_id, node_list):
        cluster_info_db = ClusterDB()
        cluster_info_db.id = cluster_id
        cluster_info_db.status = "removing"
        cluster_info_db.update_time = datetime.now()
        cluster_info_db.worker_count -= len(node_list)
        return cluster_info_db
    
    def update_nodes_todb(self, node_list):
        node_list_db = []
        for node in node_list:
            node_info_db = NodeDB()
            node_info_db.id = node.id
            node_info_db.status = "deleting"
            node_info_db.update_time = datetime.now()
            node_list_db.append(node_info_db)
        return node_list_db

    def generate_k8s_nodes(self, cluster, k8s_nodes, k8s_scale_nodes):
        node_count = k8s_nodes.count()
        for idx, node in enumerate(cluster.node_config):
            if node.get("role") == "worker":
                for i in range(node.count):
                    k8s_nodes[f"node-{node_count + i +1}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False
                    )
                    k8s_scale_nodes[f"node-{node_count + i +1}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False
                    )

    def create_instance(self, instance: InstanceConfigObject):
        # 在这里使用openstack的api接口，直接创建vm或者裸金属，根据type类型决定是创建vm还是裸金属，走不同的流程
        # 创建instance，创建openstack种的虚拟机或者裸金属服务器，如果属于某个cluster就写入cluster_id
        # 数据校验 todo
        try:
            # 获取openstack的参数，传入到create_instance的方法中，由这create_instance创建vm或者裸金属
            # 调用celery_app项目下的work.py中的create_instance方法
            result = celery_app.send_task("dingoops.celery_api.workers.create_instance", args=[])
            return result
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
            cluster_id = instance_list_info.cluter_id
            instance_list = instance_list_info.instance_list
            # 具体要操作的步骤，删除openstack中的server，删除数据库中instance表里面的该instance的数据

            # 调用celery_app项目下的work.py中的delete_instance方法
            result = celery_app.send_task("dingoops.celery_api.workers.delete_instance", args=[])
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def convert_nodeinfo_todb(self, cluster:ClusterObject, k8s_scale_nodes):
        nodeinfo_list = []

        if not cluster or not hasattr(cluster, 'node_config') or not cluster.node_config:
            return nodeinfo_list

        worker_type = "vm", "vm"
        worker_usr, worker_password = "", ""
        worker_private_key, worker_image = "", ""
        worker_flavor_id, worker_openstack_id = "", ""
        worker_auth_type, worker_security_group = "", ""

        # 遍历 node_config 并转换为 Nodeinfo 对象
        for node_conf in cluster.node_config:
            if node_conf.role == "worker":
                worker_type = node_conf.type
                worker_usr = node_conf.user
                worker_password = node_conf.password
                worker_image = node_conf.image
                worker_private_key = node_conf.private_key
                worker_auth_type = node_conf.auth_type
                worker_openstack_id = node_conf.openstack_id
                worker_security_group = node_conf.security_group
                worker_flavor_id = node_conf.flavor_id

        for worker_node in k8s_scale_nodes:
            node_db = NodeDB()
            node_db.id = str(uuid.uuid4())
            node_db.node_type = worker_type
            node_db.cluster_id = cluster.id
            node_db.cluster_name = cluster.name
            node_db.region = cluster.region_name
            node_db.role = "worker"
            node_db.user = worker_usr
            node_db.password = worker_password
            node_db.image = worker_image
            node_db.private_key = worker_private_key
            node_db.openstack_id = worker_openstack_id
            node_db.auth_type = worker_auth_type
            node_db.security_group = worker_security_group
            node_db.flavor_id = worker_flavor_id
            node_db.status = "creating"
            node_db.admin_address = ""
            node_db.name = cluster.name + "-k8s-" + worker_node
            node_db.bus_address = ""
            node_db.create_time = datetime.now()
            nodeinfo_list.append(node_db)
        return nodeinfo_list
