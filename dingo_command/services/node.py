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

from dingo_command.celery_api.celery_app import celery_app
from dingo_command.db.models.cluster.sql import ClusterSQL
from dingo_command.db.models.node.sql import NodeSQL
from dingo_command.db.models.instance.sql import InstanceSQL
from math import ceil
from oslo_log import log
from dingo_command.api.model.cluster import ClusterTFVarsObject, NodeGroup, ClusterObject
from dingo_command.db.models.cluster.models import Cluster as ClusterDB
from dingo_command.db.models.node.models import NodeInfo as NodeDB
from dingo_command.db.models.instance.models import Instance as InstanceDB
from dingo_command.common import neutron
from dingo_command.services.cluster import ClusterService
from dingo_command.db.engines.mysql import get_engine, get_session

from dingo_command.services.custom_exception import Fail
from dingo_command.services.system import SystemService

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
                return {"data": None}
            # 返回第一条数据
            return {"data": res.get("data")[0]}
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def convert_clusterinfo_todb(self, cluster_id, cluster_name):
        session = get_session()
        db_cluster = session.get(ClusterDB, (cluster_id, cluster_name))
        db_cluster.status = "scaling"
        db_cluster.update_time = datetime.now()
        return db_cluster

    def update_clusterinfo_todb(self, cluster_id, cluster_name):
        session = get_session()
        db_cluster = session.get(ClusterDB, (cluster_id, cluster_name))
        db_cluster.status = "removing"
        db_cluster.update_time = datetime.now()
        return db_cluster

    def update_nodes_todb(self, node):
        node.status = "deleting"
        node.update_time = datetime.now()
        node_dict = {
            "id": node.id,
            "name": node.name,
            "cluster_id": node.cluster_id,
            "cluster_name": node.cluster_name,
            "instance_id": node.instance_id,
            "server_id": node.server_id,
            "admin_address": node.admin_address,
            "role": node.role,
            "node_type": node.node_type,
            "auth_type": node.auth_type,
            "user": node.user,
            "password": node.password,
        }
        return node, node_dict

    def update_instances_todb(self, node):
        session = get_session()
        print("333333 node.instance_id is:", node.instance_id)
        db_instance = session.get(InstanceDB, node.instance_id)
        db_instance.status = "deleting"
        db_instance.update_time = datetime.now()
        instance_dict = {
            "id": db_instance.id,
            "name": db_instance.name,
            "cluster_id": db_instance.cluster_id,
            "cluster_name": db_instance.cluster_name,
            "server_id": db_instance.server_id,
            "ip_address": db_instance.ip_address,
            "node_type": db_instance.node_type,
            "region": db_instance.region,
            "user": db_instance.user,
            "password": db_instance.password,
        }
        return db_instance, instance_dict

    def generate_k8s_nodes(self, cluster, k8s_nodes, k8s_scale_nodes):
        node_index = len(k8s_nodes) + 1
        for idx, node in enumerate(cluster.node_config):
            if node.role == "worker" and node.type == "vm":
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
            if node.role == "worker" and node.type == "baremental":
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
        node_db_list, node_list, instance_db_list, instance_list = self.convert_nodeinfo_todb(cluster, k8s_scale_nodes)
        NodeSQL.create_node_list(node_db_list)
        # 保存instance信息到数据库
        # instance_db_list, instance_list = self.convert_instance_todb(cluster, k8s_scale_nodes)
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
            # cluster_service = ClusterService()
            # clust_dbinfo = cluster_service.get_cluster(cluster.id)

            output_file = os.path.join(BASE_DIR, "dingo_command", "ansible-deploy", "inventory", str(cluster.id),
                                       "terraform", "output.tfvars.json")
            with open(output_file) as f:
                content = json.loads(f.read())

            neutron_api = neutron.API()  # 创建API类的实例
            external_net = neutron_api.list_external_networks()

            lb_enbale = False
            if cluster.kube_info.number_master > 1:
                lb_enbale = cluster.kube_info.loadbalancer_enabled

            cluster_info_db = self.convert_clusterinfo_todb(cluster.id, cluster.name)
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
            result = celery_app.send_task("dingo_command.celery_api.workers.create_k8s_cluster",
                                          args=[tfvars.dict(), cluster.dict(), node_list, instance_list, scale])
            return result.id
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def delete_node(self, node):
        if not node:
            return None
        # 详情
        try:
            cluster_id = node.cluster_id
            cluster_name = node.cluster_name
            extravars = {}
            extravars["node"] = node.name
            if node.role == "master":
                raise ValueError("node’s role is not master")

            # 写入集群的状态为正在缩容的状态，防止其他缩容的动作重复执行
            cluster_info_db = self.update_clusterinfo_todb(cluster_id, cluster_name)
            ClusterSQL.update_cluster(cluster_info_db)
            # 写入节点的状态为正在deleting的状态
            node_info_db, node_dict = self.update_nodes_todb(node)
            NodeSQL.update_node(node_info_db)
            # 写入instance的状态为正在deleting的状态
            instance_info_db, instance_dict = self.update_instances_todb(node)
            InstanceSQL.update_instance(instance_info_db)

            # 调用celery_app项目下的work.py中的delete_cluster方法
            result = celery_app.send_task("dingo_command.celery_api.workers.delete_node",
                                          args=[cluster_id, cluster_name, node_dict, instance_dict, extravars])
            return result.id
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def convert_nodeinfo_todb(self, cluster: ClusterObject, k8s_scale_nodes):
        nodeinfo_list = []
        instance_list = []

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
                worker_auth_type = node_conf.auth_type
                worker_security_group = node_conf.security_group
                worker_flavor_id = node_conf.flavor_id

        for worker_node in k8s_scale_nodes:
            instance_db = InstanceDB()
            instance_db.id = str(uuid.uuid4())
            instance_db.node_type = worker_type
            instance_db.cluster_id = cluster.id
            instance_db.cluster_name = cluster.name
            instance_db.project_id = cluster.project_id
            instance_db.server_id = ""
            instance_db.operation_system = ""
            instance_db.cpu = 0
            instance_db.gpu = 0
            instance_db.mem = 0
            instance_db.disk = 0
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

            node_db = NodeDB()
            node_db.id = str(uuid.uuid4())
            node_db.node_type = worker_type
            node_db.cluster_id = cluster.id
            node_db.cluster_name = cluster.name
            node_db.region = cluster.region_name
            node_db.role = "worker"
            node_db.user = worker_usr
            node_db.instance_id = instance_db.id
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
        # Convert the list of dictionaries to a JSON string
        node_list_json = json.dumps(node_list_dict)
        return nodeinfo_list, node_list_json, instance_list, instance_list_json

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
            instance_db.cpu = 0
            instance_db.gpu = 0
            instance_db.mem = 0
            instance_db.disk = 0
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
