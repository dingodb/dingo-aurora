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
from math import ceil
from oslo_log import log
from dingoops.api.model.cluster import ClusterTFVarsObject, NodeGroup, ClusterObject
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

    def create_node(self, cluster: ClusterObject):
        # 在这里执行创建集群的那个流程，先创建vm虚拟机，然后添加到本k8s集群里面
        # 数据校验 todo
        try:
            cluster_info_db = self.convert_clusterinfo_todb(cluster)
            # 校验是否存在同名数据库

            # 保存对象到数据库
            res = ClusterSQL.create_cluster(cluster_info_db)
            # 保存节点信息到数据库
            # cluster_id = AssetSQL.create_cluster(cluster_info_db)
            # 调用celery_app项目下的work.py中的create_cluster方法
            # 查询openstack相关接口，返回需要的信息
            neutron_api = neutron.API()  # 创建API类的实例
            external_net = neutron_api.list_external_networks()
            # 组装cluster信息为ClusterTFVarsObject格式
            k8s_masters = {}
            k8s_nodes = {}
            self.generate_k8s_nodes(cluster, k8s_masters, k8s_nodes)
            # 保存node信息到数据库
            node_list = self.convert_nodeinfo_todb(cluster)
            res = NodeSQL.create_nodes(node_list)
            # 创建terraform变量
            tfvars = ClusterTFVarsObject(
                id=cluster_info_db.id,
                cluster_name=cluster.name,
                image=cluster.node_config[0].image,
                k8s_masters=k8s_masters,
                k8s_nodes=k8s_nodes,
                admin_subnet_id=cluster.network_config.admin_subnet_id,
                bus_subnet_id=cluster.network_config.admin_subnet_id,
                admin_network_id=cluster.network_config.admin_subnet_id,
                bus_network_id=cluster.network_config.bus_network_id,
                floatingip_pool="physnet2",
                subnet_cidr=cluster.network_config.pod_cidr,
                external_net=external_net[0]['id'],
                use_existing_network=True,
                group_vars_path="group_vars",
                password=cluster.node_config[0].password
            )
            # 调用celery_app项目下的work.py中的create_cluster方法
            result = celery_app.send_task("dingoops.celery_api.workers.scale_k8s_node",
                                          args=[tfvars.dict(), cluster.dict()])
            logging.info(result.get())
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e
        # 成功返回资产id
        return cluster_id

    def delete_node(self, node_id):
        if not node_id:
            return None
        # 详情
        try:
            # 更新集群状态为删除中

            # 根据id查询
            query_params = {}
            query_params["id"] = node_id
            res = self.list_nodes(query_params, 1, 10, None, None)
            # 空
            if not res or not res.get("data"):
                return None
            # 返回第一条数据
            node = res.get("data")[0]
            node.status = "deleting"
            # 保存对象到数据库
            res = ClusterSQL.update_cluster(node)
            # 调用celery_app项目下的work.py中的delete_cluster方法
            result = celery_app.send_task("dingoops.celery_api.workers.delete_cluster", args=[node_id])
            if result.get():
                # 删除成功，更新数据库状态
                node.status = "deleted"
                res = ClusterSQL.update_cluster(node)
            else:
                # 删除失败，更新数据库状态
                node.status = "delete_failed"
                res = ClusterSQL.update_cluster(node)
            return res.get("data")[0]
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def convert_nodeinfo_todb(self, cluster:ClusterObject):
        nodeinfo_list = []

        if not cluster or not hasattr(cluster, 'node_config') or not cluster.node_config:
            return nodeinfo_list

        # 遍历 node_config 并转换为 Nodeinfo 对象
        for node_conf in cluster.node_config:
            node_db = NodeDB()
            node_db.node_type = node_conf.type
            node_db.cluster_id = cluster.id
            node_db.cluster_name = cluster.name
            node_db.region_name = cluster.region_name
            node_db.role = node_conf.role
            node_db.user = node_conf.user
            node_db.password = node_conf.password
            node_db.private_key = node_conf.private_key
            node_db.openstack_id = node_conf.openstack_id

            # 节点的ip地址，创建虚拟机的时候不知道，只能等到后面从集群中获取ip地址，node的名字如何匹配，节点的状态是not ready还是ready？
            node_db.admin_address = ""
            node_db.name = ""
            node_db.status = ""
            node_db.bus_address = ""

            nodeinfo_list.append(node_db)
        return nodeinfo_list
