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
from dingoops.db.models.cluster.models import Cluster as ClusterDB
from dingoops.db.models.node.models import NodeInfo as NodeDB
from dingoops.db.models.instance.models import Instance as InstanceDB
from dingoops.common import neutron
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


class NodeService:

    def get_az_value(self, node_type):
        """根据节点类型返回az值"""
        return "nova" if node_type == "vm" else ""

    # 查询资产列表
    @classmethod
    def list_nodes(cls, query_params, page, page_size, sort_keys, sort_dirs):
        # 业务逻辑
        try:
            # 按照条件从数据库中查询数据
            count, data = NodeSQL.list_nodes(query_params, page, page_size, sort_keys, sort_dirs)
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

    def get_node(self, node_id):
        if not node_id:
            return None
        # 详情
        try:
            # 根据id查询
            query_params = {}
            query_params["id"] = node_id
            res = self.list_nodes(query_params, 1, 10, None, None)
            # 空
            if not res or not res.get("data"):
                return None
            # 返回第一条数据
            return res.get("data")[0]
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def convert_clusterinfo_todb(self, cluster: ClusterObject):
        cluster_info_db = ClusterDB()
        cluster_info_db.id = cluster.id
        cluster_info_db.status = "scaling"
        cluster_info_db.update_time = datetime.now()
        return cluster_info_db

    def update_clusterinfo_todb(self, cluster_id, node_list):
        cluster_info_db = ClusterDB()
        cluster_info_db.id = cluster_id
        cluster_info_db.status = "removing"
        cluster_info_db.update_time = datetime.now()
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

    def update_instances_todb(self, node_list):
        instance_list_db = []
        for node in node_list:
            instance_info_db = InstanceDB()
            instance_info_db.id = node.instance_id
            instance_info_db.status = "deleting"
            instance_info_db.update_time = datetime.now()
            instance_list_db.append(instance_info_db)
        instance_list_dict = []
        for instance in instance_list_db:
            # Create a serializable dictionary from the instanceDB object
            instance_dict = {
                "id": instance.id,
            }
            instance_list_dict.append(instance_dict)

        # Convert the list of dictionaries to a JSON string
        instance_list_json = json.dumps(instance_list_dict)
        return instance_list_db, instance_list_json

    def generate_k8s_nodes(self, cluster, k8s_nodes, k8s_scale_nodes):
        node_count = len(k8s_nodes)
        node_index = len(k8s_nodes) + 1
        for idx, node in enumerate(cluster.node_config):
            if node.get("role") == "worker" and node.type == "vm":
                for i in range(node.count):
                    k8s_nodes[f"node-{node_index}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False
                    )
                    k8s_scale_nodes[f"node-{node_index}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False
                    )
                    node_index += 1
            if node.get("role") == "worker" and node.type == "baremental":
                for i in range(node.count):
                    k8s_nodes[f"node-{node_index}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False
                    )
                    k8s_scale_nodes[f"node-{node_index}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False
                    )
                    node_index += 1

        # 保存node信息到数据库
        node_db_list, node_list = self.convert_nodeinfo_todb(cluster, k8s_scale_nodes)
        NodeSQL.create_node_list(node_db_list)
        # 保存instance信息到数据库
        instance_db_list, instance_list = self.convert_instance_todb(cluster, k8s_scale_nodes)
        InstanceSQL.create_instance_list(instance_db_list)
        return node_list, instance_list

    def create_node(self, cluster: ClusterObject):
        # 在这里执行创建集群的那个流程，先创建vm虚拟机，然后添加到本k8s集群里面
        # 数据校验 todo
        try:
            scale = True
            for conf in cluster.node_config:
                if conf.role == "master":
                    raise ValueError("The expanded node cannot be the master node.")
            # 从集群数据库里获取这个集群的集群信息，然后拼接出一个扩容的信息，或者从output.tfvars.json信息里获取
            cluster_service = ClusterService()
            clust_dbinfo = cluster_service.get_cluster(cluster.id)

            output_file = os.path.join(BASE_DIR, "dingoops", "ansible-deploy", "inventory", str(cluster.id),
                                       "terraform", "output.tfvars.json")
            with open(output_file) as f:
                content = json.loads(f.read())

            neutron_api = neutron.API()  # 创建API类的实例
            external_net = neutron_api.list_external_networks()

            lb_enbale = False
            if cluster.kube_info.number_master > 1:
                lb_enbale = cluster.kube_info.loadbalancer_enabled

            cluster_info_db = self.convert_clusterinfo_todb(cluster)
            ClusterSQL.update_cluster(cluster_info_db)
            k8s_nodes = content["nodes"]
            k8s_scale_nodes = {}
            node_list, instance_list = self.generate_k8s_nodes(cluster, k8s_nodes, k8s_scale_nodes)

            # 创建terraform变量
            tfvars = ClusterTFVarsObject(
                id=cluster.id,
                cluster_name=cluster.name,
                image=cluster.node_config[0].image,
                nodes=k8s_nodes,
                subnet_cidr="192.168.10.0/24",
                floatingip_pool=external_net[0]['name'],
                external_net=external_net[0]['id'],
                use_existing_network=False,
                ssh_user=cluster.node_config[0].user,
                k8s_master_loadbalancer_enabled=lb_enbale,
                number_of_k8s_masters=cluster.kube_info.number_master
            )
            if cluster.node_config[0].auth_type == "password":
                tfvars.password = cluster.node_config[0].password
            elif cluster.node_config[0].auth_type == "keypair":
                tfvars.password = ""
            # 调用celery_app项目下的work.py中的create_cluster方法
            result = celery_app.send_task("dingoops.celery_api.workers.create_k8s_cluster",
                                          args=[tfvars.dict(), cluster.dict(), node_list, instance_list, scale])
            return result
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def delete_node(self, node_list_info):
        if not node_list_info:
            return None
        # 详情
        try:
            cluster_id = node_list_info.cluter_id
            node_list = node_list_info.node_list
            extravars = {}
            for node in node_list:
                extravars[node.name] = node.admin_address
                if node.role == "master":
                    raise ValueError("node’s role is not master")

            # 写入集群的状态为正在缩容的状态，防止其他缩容的动作重复执行
            cluster_info_db = self.update_clusterinfo_todb(cluster_id, node_list)
            ClusterSQL.update_cluster(cluster_info_db)
            # 写入节点的状态为正在deleting的状态
            nodes_info_db = self.update_nodes_todb(node_list)
            NodeSQL.update_node_list(nodes_info_db)
            # 写入instance的状态为正在deleting的状态
            instance_list_db, instance_list = self.update_instances_todb(node_list)
            InstanceSQL.update_instance_list(instance_list_db)

            # 调用celery_app项目下的work.py中的delete_cluster方法
            result = celery_app.send_task("dingoops.celery_api.workers.delete_node",
                                          args=[cluster_id, node_list.dict(), instance_list, extravars])
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def convert_nodeinfo_todb(self, cluster: ClusterObject, k8s_scale_nodes):
        nodeinfo_list = []

        if not cluster or not hasattr(cluster, 'node_config') or not cluster.node_config:
            return [], []

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
            node_db.auth_type = worker_auth_type
            node_db.security_group = worker_security_group
            node_db.flavor_id = worker_flavor_id
            node_db.status = "creating"
            node_db.admin_address = ""
            node_db.name = cluster.name + "-" + worker_node
            node_db.bus_address = ""
            node_db.create_time = datetime.now()
            nodeinfo_list.append(node_db)
        node_list_dict = []
        for node in nodeinfo_list:
            # Create a serializable dictionary from the NodeDB object
            node_dict = {
                "id": node.id,
                "node_type": node.node_type,
                "cluster_id": node.cluster_id,
                "cluster_name": node.cluster_name,
                "region": node.region,
                "role": node.role,
                "user": node.user,
                "password": node.password,
                "image": node.image,
                "private_key": node.private_key,
                "auth_type": node.auth_type,
                "security_group": node.security_group,
                "flavor_id": node.flavor_id,
                "status": node.status,
                "admin_address": node.admin_address,
                "name": node.name,
                "bus_address": node.bus_address,
                "create_time": node.create_time.isoformat() if node.create_time else None
            }
            node_list_dict.append(node_dict)
        # Convert the list of dictionaries to a JSON string
        node_list_json = json.dumps(node_list_dict)
        return nodeinfo_list, node_list_json

    def convert_instance_todb(self, cluster: ClusterObject, k8s_nodes):
        instance_list = []

        if not cluster or not hasattr(cluster, 'node_config') or not cluster.node_config:
            return [], []

        master_type, worker_type = "vm", "vm"
        master_usr, worker_usr, master_password, worker_password = "", "", "", ""
        mmaster_image, worker_image = "", ""
        master_flavor_id, worker_flavor_id, master_openstack_id, worker_openstack_id = "", "", "", ""
        master_security_group, worker_security_group = "", ""
        for config in cluster.node_config:
            if config.role == "worker":
                worker_type = config.type
                worker_usr = config.user
                worker_password = config.password
                worker_image = config.image
                worker_security_group = config.security_group
                worker_flavor_id = config.flavor_id

        # 遍历 node_config 并转换为 Instance 对象
        for worker_node in k8s_nodes:
            instance_db = InstanceDB()
            instance_db.id = str(uuid.uuid4())
            instance_db.node_type = worker_type
            instance_db.cluster_id = cluster.id
            instance_db.cluster_name = cluster.name
            instance_db.project_id = cluster.project_id
            instance_db.server_id = ""
            instance_db.operation_system = ""
            instance_db.cpu = ""
            instance_db.gpu = ""
            instance_db.mem = ""
            instance_db.disk = ""
            instance_db.region = cluster.region_name
            instance_db.user = worker_usr
            instance_db.password = worker_password
            instance_db.image_id = worker_image
            instance_db.openstack_id = worker_openstack_id
            instance_db.security_group = worker_security_group
            instance_db.flavor_id = worker_flavor_id
            instance_db.status = "creating"
            instance_db.ip_address = ""
            instance_db.name = cluster.name + "-" + worker_node
            instance_db.floating_ip = ""
            instance_db.create_time = datetime.now()
            instance_list.append(instance_db)

        instance_list_dict = []
        for instance in instance_list:
            # Create a serializable dictionary from the instanceDB object
            instance_dict = {
                "id": instance.id,
                "instance_type": instance.node_type,
                "cluster_id": instance.cluster_id,
                "cluster_name": instance.cluster_name,
                "region": instance.region,
                "user": instance.user,
                "password": instance.password,
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
        return instance_list, instance_list_json
