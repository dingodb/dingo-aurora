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
from math import ceil
from oslo_log import log
from dingoops.api.model.cluster import ClusterTFVarsObject, NodeGroup, ClusterObject
from dingoops.db.models.cluster.models import Cluster as ClusterDB
from dingoops.db.models.cluster.models import Nodeinfo as NodeDB
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
    def generate_k8s_nodes(self, cluster:ClusterObject, k8s_masters, k8s_nodes):
        for idx, node in enumerate(cluster.node_config):
            if node.role== "master":
                for i in range(node.count):
                    if i == 0:
                        float_ip_bool = True
                    else:
                        float_ip_bool = False
                    if i < 3:
                        etcd_bool = True
                    else:
                        etcd_bool = False
                    k8s_masters[f"master-{int(i) + 1}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=float_ip_bool,
                        etcd=etcd_bool
                    )
            if node.role == "worker":
                for i in range(node.count):
                    k8s_nodes[f"node-{int(i) + 1}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False
                    )
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
            # 空
            if not res or not res.get("data"):
                return None
            # 返回第一条数据
            return res.get("data")[0]
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e


    def create_cluster(self, cluster: ClusterObject):
        # 数据校验 todo
        try:
            cluster_info_db = self.convert_clusterinfo_todb(cluster)
            # 校验是否存在同名数据库
            
            # 保存对象到数据库
            res = ClusterSQL.create_cluster(cluster_info_db)
            # 保存节点信息到数据库
            # cluster_id = AssetSQL.create_cluster(cluster_info_db)
            # 调用celery_app项目下的work.py中的create_cluster方法
            #查询openstack相关接口，返回需要的信息
            neutron_api = neutron.API()  # 创建API类的实例
            external_net = neutron_api.list_external_networks()
            #组装cluster信息为ClusterTFVarsObject格式
            k8s_masters = {}
            k8s_nodes = {}
            self.generate_k8s_nodes(cluster, k8s_masters, k8s_nodes)
             # 保存node信息到数据库
            node_list = self.convert_clusterinfo_todb(cluster)
            res = ClusterSQL.create_cluster(cluster_info_db)
            # 创建terraform变量
            tfvars = ClusterTFVarsObject(
                id = cluster_info_db.id,
                cluster_name=cluster.name,
                image=cluster.node_config[0].image,
                k8s_masters=k8s_masters,
                k8s_nodes=k8s_nodes,
                admin_subnet_id=cluster.network_config.admin_subnet_id,
                bus_subnet_id=cluster.network_config.bus_subnet_id,
                admin_network_id=cluster.network_config.admin_network_id,
                bus_network_id=cluster.network_config.bus_network_id,
                floatingip_pool=external_net[0]['name'],
                subnet_cidr=cluster.network_config.pod_cidr,
                external_net=external_net[0]['id'],
                use_existing_network=True,
                group_vars_path="group_vars",
                password=cluster.node_config[0].password,
                ssh_user=cluster.node_config[0].user,
                k8s_master_loadbalancer_enabled=cluster.network_config.loadbalancer_enabled
                )
                #调用celery_app项目下的work.py中的create_cluster方法
            result = celery_app.send_task("dingoops.celery_api.workers.create_cluster", args=[tfvars.dict(),cluster.dict()])
            #logging.info(result.get())
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
        cluster_info_db.master_count = 0
        cluster_info_db.worker_count = 0
        cluster_info_db.id = str(uuid.uuid4())
        cluster_info_db.name = cluster.name
        cluster_info_db.project_id = cluster.project_id
        cluster_info_db.user_id = cluster.user_id
        cluster_info_db.labels = json.dumps(cluster.labels)
        cluster_info_db.status = "creating"
        cluster_info_db.region_name = cluster.region_name
        cluster_info_db.admin_network_id = cluster.network_config.admin_network_id
        cluster_info_db.admin_subnet_id = cluster.network_config.admin_subnet_id
        cluster_info_db.bus_network_id = cluster.network_config.bus_network_id
        cluster_info_db.bus_subnet_id = cluster.network_config.bus_subnet_id
        cluster_info_db.runtime = cluster.runtime
        cluster_info_db.type = "k8s"
        cluster_info_db.service_cidr = cluster.network_config.service_cidr
        cluster_info_db.bus_address = ""
        cluster_info_db.api_address = ""
        cluster_info_db.cni = cluster.network_config.cni
        cluster_info_db.version = cluster.version
        cluster_info_db.worker_count = 0
        cluster_info_db.version = cluster.version
        cluster_info_db.kube_config = ""
        cluster_info_db.create_time = datetime.now()
        cluster_info_db.update_time = datetime.now()
        cluster_info_db.description = cluster.description
        cluster_info_db.extra = cluster.extra
        for node_conf in cluster.node_config:
            if node_conf.role == "master":
                cluster_info_db.master_count += node_conf.count
            if node_conf.role == "worker":
                cluster_info_db.worker_count += node_conf.count
        return cluster_info_db
    def convert_nodeinfo_todb(self, cluster:ClusterObject):
        nodeinfo_list = []
    
        if not cluster or not hasattr(cluster, 'node_config') or not cluster.node_config:
            return nodeinfo_list
        
        # 遍历 node_config 并转换为 Nodeinfo 对象
        for node_conf in cluster.node_config:
            nodeinfo = NodeDB(**node_conf)
            nodeinfo_list.append(nodeinfo)
        
        return nodeinfo_list
        node_info_db.node_type = ""
        return cluster_info_db
        
class TaskService:
    

    class TaskMessage(Enum):
        instructure_check = "参数校验"
        instructure_create = "创建基础设施"
        pre_install = "安装前准备"
        etcd_deploy = "安装etcd"
        controler_deploy = "配置kubernetes控制面"
        worker_deploy = "配置kubernetes工作节点"
        component_deploy = "安装组件"
    
    
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