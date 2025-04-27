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

from openpyxl.reader.excel import load_workbook
from openpyxl.styles import Border, Side
from typing_extensions import assert_type

from dingoops.celery_api.celery_app import celery_app

from dingoops.db.models.cluster.sql import ClusterSQL,TaskSQL
from dingoops.db.models.node.sql import NodeSQL
from math import ceil
from oslo_log import log
from dingoops.api.model.cluster import ClusterTFVarsObject, NodeGroup, ClusterObject, KubeClusterObject
from dingoops.db.models.cluster.models import Cluster as ClusterDB
from dingoops.db.models.node.models import NodeInfo as NodeDB
from dingoops.utils import neutron

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
    def generate_k8s_nodes(self, cluster:ClusterObject, k8s_nodes):
        index = 1
        for idx, node in enumerate(cluster.node_config):
            if node.role == "worker" and node.type == "vm":
                for i in range(node.count):
                    k8s_nodes[f"node-{int(i) + 1}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False
                    )
                    i=i+1
            if node.role == "worker" and node.type == "baremental":
                for i in range(node.count):
                    k8s_nodes[f"node-{int(index) + 1}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False
                    )
                    i=i+1
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
            nodes = {}
            self.generate_k8s_nodes(cluster, nodes)
            lb_enbale = False
            if cluster.kube_info.number_master>1:
                lb_enbale = cluster.kube_info.loadbalancer_enabled
           
            # 创建terraform变量
            tfvars = ClusterTFVarsObject(
                id = cluster_info_db.id,
                cluster_name=cluster.name,
                image=cluster.node_config[0].image,
                nodes=nodes,
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
        except Exception as e:
            import traceback
            traceback.print_exc()
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

    def convert_nodeinfo_todb(self, cluster:ClusterObject):
        nodeinfo_list = []

        if not cluster or not hasattr(cluster, 'node_config') or not cluster.node_config:
            return nodeinfo_list

        # 遍历 node_config 并转换为 Nodeinfo 对象
        for node_conf in cluster.node_config:
            node_db = NodeDB()
            node_db.id = str(uuid.uuid4())
            node_db.node_type = node_conf.type
            node_db.cluster_id = cluster.id
            node_db.cluster_name = cluster.name
            node_db.region = cluster.region_name
            node_db.role = node_conf.role
            node_db.user = node_conf.user
            node_db.password = node_conf.password
            node_db.private_key = node_conf.private_key
            #node_db.openstack_id = node_conf.openstack_id
            node_db.status = "creating"

            # 节点的ip地址，创建虚拟机的时候不知道，只能等到后面从集群中获取ip地址，node的名字如何匹配，节点的状态是not ready还是ready？
            node_db.admin_address = ""
            node_db.name = ""
            node_db.bus_address = ""

            # Create a clean dictionary with only serializable fields
            node_dict = {
                'id': node_db.id,
                'node_type': node_db.node_type,
                'cluster_id': node_db.cluster_id,
                'cluster_name': node_db.cluster_name,
                'region': node_db.region,
                'role': node_db.role,
                'user': node_db.user,
                'password': node_db.password,
                'private_key': node_db.private_key,
                'openstack_id': node_db.openstack_id,
                'status': node_db.status,
                'admin_address': node_db.admin_address,
                'name': node_db.name,
                'bus_address': node_db.bus_address
            }
            nodeinfo_list.append(node_dict)
        return nodeinfo_list

        
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


