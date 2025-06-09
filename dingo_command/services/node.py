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
from dingo_command.api.model.cluster import ClusterTFVarsObject, NodeGroup, ClusterObject, ScaleNodeObject, PortForwards
from dingo_command.db.models.cluster.models import Cluster as ClusterDB
from dingo_command.db.models.node.models import NodeInfo as NodeDB
from dingo_command.db.models.instance.models import Instance as InstanceDB
from dingo_command.common import neutron
from dingo_command.services.cluster import ClusterService
from dingo_command.db.engines.mysql import get_engine, get_session

from dingo_command.services.custom_exception import Fail
from dingo_command.services.system import SystemService
from dingo_command.common.nova_client import NovaClient
from dingo_command.services import CONF

LOG = log.getLogger(__name__)
WORK_DIR = CONF.DEFAULT.cluster_work_dir
auth_url = CONF.DEFAULT.auth_url
image_master = CONF.DEFAULT.k8s_master_image
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

    def update_nodes_todb(self, node_list):
        node_info_list = []
        for node in node_list:
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
                "cpu": node.cpu,
                "gpu": node.gpu,
                "mem": node.mem,
                "disk": node.disk,
                "node_type": node.node_type,
                "auth_type": node.auth_type,
                "region_name": node.region,
                "user": node.user,
                "password": node.password,
            }
            node_info_list.append(node_dict)
        instance_list_json = json.dumps(node_info_list)
        return node_list, instance_list_json

    def update_instances_todb(self, node_list):
        session = get_session()
        instance_info_list = []
        instance_db_list = []
        for node in node_list:
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
            instance_db_list.append(db_instance)
            instance_info_list.append(instance_dict)
        instance_list_json = json.dumps(instance_info_list)
        return instance_db_list, instance_list_json

    def generate_random_port(self):
        """从 20000 到 40000 范围内随机生成一个端口号"""
        import random
        return random.randint(20000, 40000)

    def generate_k8s_nodes(self, cluster_info, cluster, k8s_nodes, scale_nodes, forward_rules, forward_float_ip_id):
        node_db_list, instance_db_list = [], []
        max_key = max(k8s_nodes, key=lambda k: int(k.split('-')[-1]))
        node_index = int(max_key.split('-')[-1]) + 1
        nova_client = NovaClient()
        for idx, node in enumerate(cluster.node_config):
            if node.role == "worker" and node.type == "vm":
                cpu, gpu, mem, disk = self.get_flavor_info(nova_client, node.flavor_id)
                operation_system = self.get_image_info(nova_client, node.image)
                for i in range(node.count):
                    forward_rules_new = []
                    if forward_rules:
                        for index, port_forward in enumerate(forward_rules):
                            cluster_new = {}
                            cluster_new["external_port"] = self.generate_random_port()
                            cluster_new["internal_port"] = port_forward.get("internal_port")
                            cluster_new["protocol"] = port_forward.get("protocol")
                            forward_rules_new.append(cluster_new)
                    k8s_nodes[f"node-{int(node_index)}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False,
                        image_id=node.image,
                        port_forwards=[PortForwards(**forward) for forward in forward_rules_new],
                        use_local_disk=node.use_local_disk,
                        volume_size=node.volume_size,
                        volume_type=node.volume_type
                    )
                    scale_nodes.append(f"{cluster_info.name}-node-{int(node_index)}")
                    instance_db = InstanceDB()
                    instance_db.id = str(uuid.uuid4())
                    instance_db.node_type = node.type
                    instance_db.cluster_id = cluster.id
                    instance_db.cluster_name = cluster_info.name
                    instance_db.region = cluster_info.region_name
                    instance_db.user = node.user
                    instance_db.password = node.password
                    instance_db.security_group = node.security_group
                    instance_db.flavor_id = node.flavor_id
                    instance_db.status = "creating"
                    instance_db.floating_forward_ip = forward_float_ip_id
                    instance_db.ip_forward_rule = forward_rules_new
                    instance_db.status_msg = ""
                    instance_db.project_id = ""
                    instance_db.server_id = ""
                    instance_db.openstack_id = ""
                    instance_db.operation_system = operation_system
                    instance_db.cpu = cpu
                    instance_db.gpu = gpu
                    instance_db.mem = mem
                    instance_db.disk = disk
                    instance_db.ip_address = ""
                    instance_db.name = cluster_info.name + f"-node-{int(node_index)}"
                    instance_db.floating_ip = ""
                    instance_db.create_time = datetime.now()
                    instance_db_list.append(instance_db)

                    node_db = NodeDB()
                    node_db.id = str(uuid.uuid4())
                    node_db.node_type = node.type
                    node_db.cluster_id = cluster.id
                    node_db.cluster_name = cluster_info.name
                    node_db.region = cluster_info.region_name
                    node_db.role = node.role
                    node_db.user = node.user
                    node_db.password = node.password
                    node_db.image = node.image
                    node_db.instance_id = instance_db.id
                    node_db.operation_system = operation_system
                    node_db.cpu = cpu
                    node_db.gpu = gpu
                    node_db.mem = mem
                    node_db.disk = disk
                    node_db.project_id = cluster_info.project_id
                    node_db.auth_type = node.auth_type
                    node_db.security_group = node.security_group
                    node_db.flavor_id = node.flavor_id
                    node_db.status = "creating"
                    node_db.floating_forward_ip = forward_float_ip_id
                    node_db.ip_forward_rule = forward_rules_new
                    node_db.status_msg = ""
                    node_db.admin_address = ""
                    node_db.name = cluster_info.name + f"-node-{int(node_index)}"
                    node_db.bus_address = ""
                    node_db.create_time = datetime.now()
                    node_db_list.append(node_db)
                    node_index = node_index + 1
            if node.role == "worker" and node.type == "baremental":
                cpu, gpu, mem, disk = self.get_flavor_info(nova_client, node.flavor_id)
                operation_system = self.get_image_info(nova_client, node.image)
                for i in range(node.count):
                    forward_rules_new = []
                    if forward_rules:
                        for index, port_forward in enumerate(forward_rules):
                            cluster_new = {}
                            cluster_new["external_port"] = self.generate_random_port()
                            cluster_new["internal_port"] = port_forward.get("internal_port")
                            cluster_new["protocol"] = port_forward.get("protocol")
                            forward_rules_new.append(cluster_new)
                    k8s_nodes[f"node-{int(node_index)}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False,
                        image_id=node.image,
                        port_forwards=[PortForwards(**forward) for forward in forward_rules_new]
                    )
                    scale_nodes.append(f"{cluster_info.name}-node-{int(node_index)}")
                    instance_db = InstanceDB()
                    instance_db.id = str(uuid.uuid4())
                    instance_db.node_type = node.type
                    instance_db.cluster_id = cluster.id
                    instance_db.cluster_name = cluster_info.name
                    instance_db.region = cluster_info.region_name
                    instance_db.user = node.user
                    instance_db.password = node.password
                    instance_db.security_group = node.security_group
                    instance_db.flavor_id = node.flavor_id
                    instance_db.status = "creating"
                    instance_db.floating_forward_ip = forward_float_ip_id
                    instance_db.ip_forward_rule = forward_rules_new
                    instance_db.status_msg = ""
                    instance_db.project_id = ""
                    instance_db.server_id = ""
                    instance_db.openstack_id = ""
                    instance_db.operation_system = operation_system
                    instance_db.cpu = cpu
                    instance_db.gpu = gpu
                    instance_db.mem = mem
                    instance_db.disk = disk
                    instance_db.ip_address = ""
                    instance_db.name = cluster_info.name + f"-node-{int(node_index)}"
                    instance_db.floating_ip = ""
                    instance_db.create_time = datetime.now()
                    instance_db_list.append(instance_db)

                    node_db = NodeDB()
                    node_db.id = str(uuid.uuid4())
                    node_db.node_type = node.type
                    node_db.cluster_id = cluster.id
                    node_db.cluster_name = cluster_info.name
                    node_db.region = cluster_info.region_name
                    node_db.role = node.role
                    node_db.user = node.user
                    node_db.password = node.password
                    node_db.image = node.image
                    node_db.instance_id = instance_db.id
                    node_db.project_id = cluster_info.project_id
                    node_db.auth_type = node.auth_type
                    node_db.security_group = node.security_group
                    node_db.flavor_id = node.flavor_id
                    node_db.status = "creating"
                    node_db.floating_forward_ip = forward_float_ip_id
                    node_db.ip_forward_rule = forward_rules_new
                    node_db.status_msg = ""
                    node_db.admin_address = ""
                    node_db.name = cluster_info.name + f"-node-{int(node_index)}"
                    node_db.bus_address = ""
                    node_db.create_time = datetime.now()
                    node_db_list.append(node_db)
                    node_index = node_index + 1

        node_list_dict = []
        for node in node_db_list:
            # Create a serializable dictionary from the NodeDB object
            node_dict = {
                "id": node.id,
                "node_type": node.node_type,
                "cluster_id": node.cluster_id,
                "cluster_name": node.cluster_name,
                "region": node.region,
                "role": node.role,
                "user": node.user,
                "cpu": node.cpu,
                "gpu": node.gpu,
                "mem": node.mem,
                "disk": node.disk,
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
        for instance in instance_db_list:
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

        instance_list_json = json.dumps(instance_list_dict)
        node_list_json = json.dumps(node_list_dict)
        NodeSQL.create_node_list(node_db_list)
        InstanceSQL.create_instance_list(instance_db_list)
        return node_list_json, instance_list_json

    def get_floatip_pools(self, neutron_api, external_net):
        floatingip_pool = ""
        public_floatingip_pool=""
        external_net_id = ""
        external_subnetids = []
        public_subnetids = []
        for net in external_net:
            for subnet_id in net["subnets"]:
                subnet = neutron_api.get_subnet_by_id(subnet_id)
                import ipaddress
                if ipaddress.ip_network(subnet["cidr"]).is_private:
                    if floatingip_pool=="":
                        floatingip_pool=net["name"]
                        external_net_id = net["id"]
                    external_subnetids.append(subnet_id)
                elif not ipaddress.ip_network(subnet["cidr"]).is_private:
                    if public_floatingip_pool=="":
                        public_floatingip_pool=net["name"]
                    public_subnetids = public_subnetids.append(subnet_id)
        if public_floatingip_pool == "":
            public_floatingip_pool = floatingip_pool
        if not public_subnetids:
            public_subnetids = external_subnetids
        return floatingip_pool,public_floatingip_pool,public_subnetids,external_subnetids,external_net_id

    def create_node(self, cluster_info, cluster: ScaleNodeObject, token):
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

            output_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id),
                                       "terraform", "output.tfvars.json")
            with open(output_file) as f:
                content = json.loads(f.read())

            cluster_info_db = self.convert_clusterinfo_todb(cluster_info.id, cluster_info.name)
            ClusterSQL.update_cluster(cluster_info_db)
            k8s_nodes = content["nodes"]
            scale_nodes = []
            subnet_cidr = content.get("subnet_cidr")
            forward_float_ip_id = content.get("forward_float_ip_id")
            lb_enbale = content.get("k8s_master_loadbalancer_enabled")
            number_of_k8s_masters_no_floating_ip = content.get("number_of_k8s_masters_no_floating_ip")
            neutron_api = neutron.API()  # 创建API类的实例
            external_net = neutron_api.list_external_networks()
            (floatingip_pool, public_floatingip_pool, public_subnetids,
             external_subnetids, external_net_id) = self.get_floatip_pools(neutron_api, external_net)
            forward_rules = []
            for k, v in k8s_nodes.items():
                if v.get("port_forwards"):
                    forward_rules = v.get("port_forwards")
                    break
            node_list, instance_list = self.generate_k8s_nodes(cluster_info, cluster, k8s_nodes,
                                                               scale_nodes, forward_rules, forward_float_ip_id)
            # 创建terraform变量
            tfvars = ClusterTFVarsObject(
                id=cluster.id,
                cluster_name=cluster_info.name,
                image_uuid=cluster.node_config[0].image,
                nodes=k8s_nodes,
                subnet_cidr=subnet_cidr,
                floatingip_pool=floatingip_pool,
                public_floatingip_pool=public_floatingip_pool,
                public_subnetids=public_subnetids,
                external_subnetids=external_subnetids,
                external_net=external_net_id,
                use_existing_network=False,
                ssh_user=cluster.node_config[0].user,
                k8s_master_loadbalancer_enabled=lb_enbale,
                number_of_k8s_masters=1,
                number_of_k8s_masters_no_floating_ip=number_of_k8s_masters_no_floating_ip,
                token=token,
                auth_url=auth_url,
                tenant_id=cluster_info.project_id,
                forward_float_ip_id=forward_float_ip_id,
                image_master=image_master,
            )
            if cluster.node_config[0].auth_type == "password":
                tfvars.password = cluster.node_config[0].password
            elif cluster.node_config[0].auth_type == "keypair":
                tfvars.password = ""
            else:
                tfvars.password = ""
            # 调用celery_app项目下的work.py中的create_cluster方法
            result = celery_app.send_task("dingo_command.celery_api.workers.create_k8s_cluster",
                                          args=[tfvars.dict(), cluster_info.dict(), node_list, instance_list,
                                                ",".join(scale_nodes), scale])
            return result.id
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def delete_node(self, cluster_id, cluster_name, node_list):
        # 详情
        try:
            extravars = {}
            node_name_list = []
            for node in node_list:
                node_name_list.append(node.name)
            extravars["node"] = ",".join(node_name_list)

            # 写入集群的状态为正在缩容的状态，防止其他缩容的动作重复执行
            cluster_info_db = self.update_clusterinfo_todb(cluster_id, cluster_name)
            ClusterSQL.update_cluster(cluster_info_db)
            # 写入节点的状态为正在deleting的状态
            node_db_list, node_dict = self.update_nodes_todb(node_list)
            NodeSQL.update_node_list(node_db_list)
            # 写入instance的状态为正在deleting的状态
            instance_db_list, instance_dict = self.update_instances_todb(node_list)
            InstanceSQL.update_instance_list(instance_db_list)

            # 调用celery_app项目下的work.py中的delete_cluster方法
            result = celery_app.send_task("dingo_command.celery_api.workers.delete_node",
                                          args=[cluster_id, cluster_name, node_dict, instance_dict, extravars])
            return result.id
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def convert_nodeinfo_todb(self, cluster_info, cluster: ScaleNodeObject, k8s_scale_nodes):
        node_db_list, instance_db_list = [], []
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
            instance_db.cluster_id = cluster_info.id
            instance_db.cluster_name = cluster_info.name
            instance_db.project_id = cluster_info.project_id
            instance_db.server_id = ""
            instance_db.operation_system = ""
            instance_db.cpu = 0
            instance_db.gpu = 0
            instance_db.mem = 0
            instance_db.disk = 0
            instance_db.region = cluster_info.region_name
            instance_db.user = worker_usr
            instance_db.password = worker_password
            instance_db.image_id = worker_image
            instance_db.openstack_id = worker_openstack_id
            instance_db.security_group = worker_security_group
            instance_db.flavor_id = worker_flavor_id
            instance_db.status = "creating"
            instance_db.ip_address = ""
            instance_db.name = cluster_info.name + "-" + worker_node
            instance_db.floating_ip = ""
            instance_db.create_time = datetime.now()
            instance_db_list.append(instance_db)

            node_db = NodeDB()
            node_db.id = str(uuid.uuid4())
            node_db.node_type = worker_type
            node_db.cluster_id = cluster.id
            node_db.cluster_name = cluster_info.name
            node_db.region = cluster_info.region_name
            node_db.project_id = cluster_info.project_id
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
            node_db.name = cluster_info.name + "-" + worker_node
            node_db.bus_address = ""
            node_db.create_time = datetime.now()
            node_db_list.append(node_db)

        node_list_dict = []
        for node in node_db_list:
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
        for instance in instance_db_list:
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
        return node_db_list, node_list_json, instance_db_list, instance_list_json

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

    def get_flavor_info(self, nova_client, flavor_id):
        flavor = nova_client.nova_get_flavor(flavor_id)
        cpu = 0
        gpu = 0
        mem = 0
        disk = 0
        if flavor is not None:
            cpu = flavor['vcpus']
            mem = flavor['ram']
            disk = flavor['disk']
            if "extra_specs" in flavor and "pci_passthrough:alias" in flavor["extra_specs"]:
                pci_alias = flavor['extra_specs']['pci_passthrough:alias']
                if ':' in pci_alias:
                    gpu = pci_alias.split(':')[1]
        return int(cpu), int(gpu), int(mem), int(disk)

    def get_image_info(self, nova_client, image_id):
        operation_system = ""
        image = nova_client.glance_get_image(image_id)
        if image is not None:
            if image.get("os_version"):
                operation_system = image.get("os_version")
            elif image.get("os_distro"):
                operation_system = image.get("os_distro")
            else:
                operation_system = image.get("name")
        return operation_system

