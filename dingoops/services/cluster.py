# 资产的service层
from enum import Enum
import json
import logging
import os
import shutil
import uuid
from io import BytesIO

import pandas as pd
from datetime import datetime

from ansible_collections.inspur.sm.plugins.modules.media_instance_info import Instance
from openpyxl.reader.excel import load_workbook
from openpyxl.styles import Border, Side
from typing_extensions import assert_type

from dingoops.celery_api.celery_app import celery_app

from dingoops.db.models.cluster.sql import ClusterSQL,TaskSQL
from dingoops.db.models.node.sql import NodeSQL
from dingoops.db.models.instance.sql import InstanceSQL
from math import ceil
from oslo_log import log

from dingoops.api.model.cluster import ClusterTFVarsObject, NodeGroup, ClusterObject, KubeClusterObject
from dingoops.api.model.instance import InstanceConfigObject

from dingoops.db.models.cluster.models import Cluster as ClusterDB
from dingoops.db.models.node.models import NodeInfo as NodeDB
from dingoops.db.models.instance.models import Instance as InstanceDB
from dingoops.common import neutron

from dingoops.services.custom_exception import Fail
from dingoops.services.system import SystemService



LOG = log.getLogger(__name__)


# 定义边框样式
thin_border = Border(
    left=Side(border_style="thin", color="000000"),  # 左边框
    right=Side(border_style="thin", color="000000"),  # 右边框
    top=Side(border_style="thin", color="000000"),  # 上边框
    bottom=Side(border_style="thin", color="000000")  # 下边框
)

system_service = SystemService()

class ClusterService:

    def get_az_value(self, node_type):
        """根据节点类型返回az值"""
        return "nova" if node_type == "vm" else ""
    def generate_k8s_nodes(self, cluster:ClusterObject, k8s_masters,k8s_nodes):
        node_index = 1
        master_index = 1
        for idx, node in enumerate(cluster.node_config):
            if node.role == "master" and node.type == "vm":
                for i in range(node.count):
                    k8s_masters[f"master-{int(master_index) + 1}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=True,
                        etcd=False
                    )
                    master_index=master_index+1
            if node.role == "worker" and node.type == "vm":
                for i in range(node.count):
                    k8s_nodes[f"node-{int(node_index) + 1}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False
                    )
                    node_index=node_index+1
            if node.role == "worker" and node.type == "baremental":
                for i in range(node.count):
                    k8s_nodes[f"node-{int(node_index) + 1}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False
                    )
                    node_index=node_index+1
    # 查询资产列表
    def list_clusters(self, query_params, page, page_size, sort_keys, sort_dirs):
        # 业务逻辑
        try:
            # 按照条件从数据库中查询数据
            count, data = ClusterSQL.list_cluster(query_params, page, page_size, sort_keys, sort_dirs)
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
        
    
    def get_cluster(self, cluster_id):
        if not cluster_id:
            return None
        # 详情
        try:
            # 根据id查询
            query_params = {}
            query_params["id"] = cluster_id
            res = self.list_clusters(query_params, 1, 10, None, None)

            # 将cluster转为ClusterObject对象
            if not res.get("data"):
                return None
            cluster = res.get("data")[0]
            # Convert the parsed JSON to a KubeClusterObject
            kube_info = KubeClusterObject(**json.loads(cluster.kube_info))
            # 将cluster转为ClusterObject对象
            cluster = ClusterObject(
                id=cluster.id,
                name=cluster.name,
                project_id=cluster.project_id,
                user_id=cluster.user_id,
                labels=cluster.labels,
                status=cluster.status,
                region_name=cluster.region_name,
                type=cluster.type,
                kube_info=kube_info,
                create_time=cluster.create_time,
                update_time=cluster.update_time,
                description=cluster.description,
                extra=cluster.extra
            )
            if cluster.admin_network_id != "null":
                cluster.admin_network_id = json.loads(cluster.admin_network_id)
            if cluster.admin_subnet_id != "null":   
                cluster.admin_subnet_id = json.loads(cluster.admin_subnet_id)
            if cluster.bus_network_id != "null":
                cluster.bus_network_id = json.loads(cluster.bus_network_id)
            if cluster.bus_subnet_id != "null":
                cluster.bus_subnet_id = json.loads(cluster.bus_subnet_id)

            # 空
            if not res or not res.get("data"):
                return None
            # 返回第一条数据
            return cluster
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def check_cluster_param(self, cluster: ClusterObject):
        # 判断名称是否重复、判断是否有空值、判断是否有重复的节点配置
        
        return True
    
    
    def create_cluster(self, cluster: ClusterObject):
        # 数据校验 todo
        if  not self.check_cluster_param(cluster):
            raise Fail("参数校验失败")
        try:
            cluster_info_db = self.convert_clusterinfo_todb(cluster)
            # 保存对象到数据库
            res = ClusterSQL.create_cluster(cluster_info_db)
             # 保存node信息到数据库
            node_list = self.convert_nodeinfo_todb(cluster)
            #res = NodeSQL.create_nodes(node_list)
            #查询openstack相关接口，返回需要的信息
            neutron_api = neutron.API()  # 创建API类的实例
            external_net = neutron_api.list_external_networks()

            lb_enbale = False
            if cluster.kube_info.number_master>1:
                lb_enbale = cluster.kube_info.loadbalancer_enabled
           

            #组装cluster信息为ClusterTFVarsObject格式
            k8s_masters = {}
            k8s_nodes = {}
            self.generate_k8s_nodes(cluster, k8s_masters, k8s_nodes)
            # 保存node信息到数据库
            node_list = self.convert_nodeinfo_todb(cluster, k8s_masters, k8s_nodes)
            NodeSQL.create_node_list(node_list)
            # 保存instance信息到数据库
            instance_list = self.convert_instance_todb(cluster, k8s_masters, k8s_nodes)
            InstanceSQL.create_instance_list(instance_list)

            # 创建terraform变量
            tfvars = ClusterTFVarsObject(
                id = cluster_info_db.id,
                cluster_name=cluster.name,
                image=cluster.node_config[0].image,
                nodes=k8s_nodes,
                floatingip_pool=external_net[0]['name'],
                subnet_cidr=cluster.kube_info.pod_cidr,
                external_net=external_net[0]['id'],
                use_existing_network=False,
                password=cluster.node_config[0].password,
                ssh_user=cluster.node_config[0].user,
                k8s_master_loadbalancer_enabled=lb_enbale,
                number_of_k8s_masters = cluster.kube_info.number_master
                )

            #组装cluster信息为ClusterTFVarsObject格式
        # 根据
            if cluster.type == "none":
                result = celery_app.send_task("dingoops.celery_api.workers.create_cluster",
                                          args=[tfvars.dict(), cluster.dict(), node_list ])
            elif cluster.type == "kubernetes":
                print(tfvars.dict())
                print(cluster.dict())
                result = celery_app.send_task("dingoops.celery_api.workers.create_k8s_cluster",
                                          args=[tfvars.dict(), cluster.dict(), node_list ])
            elif cluster.type == "slurm":
                pass
            else:
                pass

        except Fail as e:
            raise e

        # 成功返回资产id
        return cluster_info_db.id
    

    def delete_cluster(self, cluster_id):
        if not cluster_id:
            return None
        # 详情
        try:
            # 更新集群状态为删除中
            
            # 根据id查询
            query_params = {}
            query_params["id"] = cluster_id
            res = self.list_clusters(query_params, 1, 10, None, None)
            # 空
            if not res or not res.get("data"):
                return None
            # 返回第一条数据
            cluster = res.get("data")[0]
            cluster.status = "deleting"
            # 保存对象到数据库
            res = ClusterSQL.update_cluster(cluster)
            # 调用celery_app项目下的work.py中的delete_cluster方法
            result = celery_app.send_task("dingoops.celery_api.workers.delete_cluster", args=[cluster_id])
            if result.get():
                # 删除成功，更新数据库状态
                cluster.status = "deleted"
                res = ClusterSQL.update_cluster(cluster)
            else:
                # 删除失败，更新数据库状态
                cluster.status = "delete_failed"
                res = ClusterSQL.update_cluster(cluster)
            return res.get("data")[0]
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e
    
    def convert_clusterinfo_todb(self, cluster:ClusterObject):
        cluster_info_db = ClusterDB()

        cluster_info_db.id = str(uuid.uuid4())
        cluster_info_db.name = cluster.name
        cluster_info_db.project_id = cluster.project_id
        cluster_info_db.user_id = cluster.user_id
        cluster_info_db.labels = json.dumps(cluster.labels)
        cluster_info_db.status = "creating"
        cluster_info_db.region_name = cluster.region_name

        cluster_info_db.type = cluster.type
        cluster_info_db.create_time = datetime.now()
        cluster_info_db.update_time = datetime.now()
        cluster_info_db.description = cluster.description
        cluster_info_db.extra = cluster.extra
        # 将kube_info转换为字符串
        if cluster.kube_info:
            cluster_info_db.kube_info = json.dumps(cluster.kube_info.dict())
        else:
            cluster_info_db.kube_info = None
        # 计算集群中的cpu、mem、gpu、gpu_mem
        for idx, node in enumerate(cluster.node_config):
            if node.role == "worker" and node.type == "vm":
                pass
                #查询flavor信息
            elif node.role == "worker" and node.type == "baremental":
                #查询flavor信息
                pass

        return cluster_info_db

    def convert_nodeinfo_todb(self, cluster:ClusterObject, k8s_masters, k8s_nodes):
        nodeinfo_list = []

        if not cluster or not hasattr(cluster, 'node_config') or not cluster.node_config:
            return nodeinfo_list

        master_type, worker_type = "vm", "vm"
        master_usr, worker_usr, master_password, worker_password = "", "", "", ""
        master_private_key, worker_private_key, master_image, worker_image = "", "", "", ""
        master_flavor_id, worker_flavor_id, master_openstack_id, worker_openstack_id = "", "", "", ""
        master_auth_type, worker_auth_type, master_security_group, worker_security_group = "", "", "", ""
        for config in cluster.node_config:
            if config.role == "master":
                master_type = config.type
                master_usr = config.user
                master_password = config.password
                master_image = config.image
                master_private_key = config.private_key
                master_auth_type = config.auth_type
                master_openstack_id = config.openstack_id
                master_security_group = config.security_group
                master_flavor_id = config.flavor_id
            if config.role == "worker":
                worker_type = config.type
                worker_usr = config.user
                worker_password = config.password
                worker_image = config.image
                worker_private_key = config.private_key
                worker_auth_type = config.auth_type
                worker_openstack_id = config.openstack_id
                worker_security_group = config.security_group
                worker_flavor_id = config.flavor_id

        # 遍历 node_config 并转换为 Nodeinfo 对象
        for master_node in k8s_masters:
            node_db = NodeDB()
            node_db.id = str(uuid.uuid4())
            node_db.node_type = master_type
            node_db.cluster_id = cluster.id
            node_db.cluster_name = cluster.name
            node_db.region = cluster.region_name
            node_db.role = "master"
            node_db.user = master_usr
            node_db.password = master_password
            node_db.image = master_image
            node_db.private_key = master_private_key
            node_db.openstack_id = master_openstack_id
            node_db.auth_type = master_auth_type
            node_db.security_group = master_security_group
            node_db.flavor_id = master_flavor_id
            node_db.status = "creating"
            node_db.admin_address = ""
            node_db.name = cluster.name + "-k8s-" + master_node
            node_db.bus_address = ""
            node_db.create_time = datetime.now()
            nodeinfo_list.append(node_db)
        for worker_node in k8s_nodes:
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
        
            # Create a clean dictionary with only serializable fields
            
        return nodeinfo_list


    def convert_instance_todb(self, cluster:ClusterObject, k8s_masters, k8s_nodes):
        instance_list = []

        if not cluster or not hasattr(cluster, 'node_config') or not cluster.node_config:
            return instance_list

        master_type, worker_type = "vm", "vm"
        master_usr, worker_usr, master_password, worker_password = "", "", "", ""
        mmaster_image, worker_image = "", ""
        master_flavor_id, worker_flavor_id, master_openstack_id, worker_openstack_id = "", "", "", ""
        master_security_group, worker_security_group = "", ""
        for config in cluster.node_config:
            if config.role == "master":
                master_type = config.type
                master_usr = config.user
                master_password = config.password
                master_image = config.image
                master_openstack_id = config.openstack_id
                master_security_group = config.security_group
                master_flavor_id = config.flavor_id
            if config.role == "worker":
                worker_type = config.type
                worker_usr = config.user
                worker_password = config.password
                worker_image = config.image
                worker_openstack_id = config.openstack_id
                worker_security_group = config.security_group
                worker_flavor_id = config.flavor_id

        # 遍历 node_config 并转换为 Nodeinfo 对象
        for master_node in k8s_masters:
            instance_db = InstanceDB()
            instance_db.id = str(uuid.uuid4())
            instance_db.node_type = master_type
            instance_db.cluster_id = cluster.id
            instance_db.cluster_name = cluster.name
            instance_db.region = cluster.region_name
            instance_db.user = master_usr
            instance_db.password = master_password
            instance_db.image = master_image
            instance_db.openstack_id = master_openstack_id
            instance_db.security_group = master_security_group
            instance_db.flavor_id = master_flavor_id
            instance_db.status = "creating"
            instance_db.ip_address = ""
            instance_db.name = cluster.name + "-k8s-" + master_node
            instance_db.floating_ip = ""
            instance_db.create_time = datetime.now()
            instance_list.append(instance_db)

        for worker_node in k8s_nodes:
            instance_db = InstanceDB()
            instance_db.id = str(uuid.uuid4())
            instance_db.node_type = worker_type
            instance_db.cluster_id = cluster.id
            instance_db.cluster_name = cluster.name
            instance_db.region = cluster.region_name
            instance_db.user = worker_usr
            instance_db.password = worker_password
            instance_db.image = worker_image
            instance_db.openstack_id = worker_openstack_id
            instance_db.security_group = worker_security_group
            instance_db.flavor_id = worker_flavor_id
            instance_db.status = "creating"
            instance_db.ip_address = ""
            instance_db.name = cluster.name + "-k8s-" + worker_node
            instance_db.floating_ip = ""
            instance_db.create_time = datetime.now()
            instance_list.append(instance_db)
        return instance_list

        
class TaskService:
    

    class TaskMessage(Enum):
        instructure_check = "参数校验"
        instructure_create = "创建基础设施"
        pre_install = "安装前准备"
        etcd_deploy = "安装etcd"
        controler_deploy = "配置kubernetes控制面"
        worker_deploy = "配置kubernetes工作节点"
        component_deploy = "安装组件"
        
    
    class TaskDetail(Enum):
        instructure_check = "instructure check passed"
        instructure_create = "instructure create success"
        pre_install = "install prepare success"
        etcd_deploy = "etcd deploy success"
        controler_deploy = "control plane deploy success"
        worker_deploy = "worker node deploy success"
        component_deploy = "component deploy success"
        
    def get_tasks(self, cluster_id):
        if not cluster_id:
            return None
        # 详情
        try:
            # 根据id查询
            query_params = {}
            query_params["cluster_id"] = cluster_id
            res = TaskSQL.list(query_params, None, None)
            # 空
            if not res :
                return None
            # 返回第一条数据
            return res
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e