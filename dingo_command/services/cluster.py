# 资产的service层
import copy

from enum import Enum
import json
import os
import random
import uuid
from datetime import datetime

from openpyxl.styles import Border, Side
from fastapi import HTTPException

from dingo_command.celery_api.celery_app import celery_app
from dingo_command.services.node import NodeService
from dingo_command.services.instance import InstanceService
from dingo_command.db.models.cluster.sql import ClusterSQL,TaskSQL,ParamSQL
from dingo_command.db.models.node.sql import NodeSQL
from dingo_command.db.models.instance.sql import InstanceSQL
from math import ceil
from oslo_log import log

from dingo_command.api.model.cluster import ClusterTFVarsObject, NodeGroup, ClusterObject, KubeClusterObject, NetworkConfigObject,NodeConfigObject

from dingo_command.db.models.cluster.models import Cluster as ClusterDB
from dingo_command.db.models.node.models import NodeInfo as NodeDB
from dingo_command.db.models.instance.models import Instance as InstanceDB
from dingo_command.common import neutron
from dingo_command.common.nova_client import NovaClient
from dingo_command.services.custom_exception import Fail
from dingo_command.services.system import SystemService
from dingo_command.services import CONF
from dingo_command.db.engines.mysql import get_session


LOG = log.getLogger(__name__)


# 定义边框样式
thin_border = Border(
    left=Side(border_style="thin", color="000000"),  # 左边框
    right=Side(border_style="thin", color="000000"),  # 右边框
    top=Side(border_style="thin", color="000000"),  # 上边框
    bottom=Side(border_style="thin", color="000000")  # 下边框
)
auth_url = CONF.DEFAULT.auth_url
WORK_DIR = CONF.DEFAULT.cluster_work_dir
master_image = CONF.DEFAULT.k8s_master_image
master_flvaor = CONF.DEFAULT.k8s_master_flavor
system_service = SystemService()

class ClusterService:

    def get_az_value(self, node_type):
        """根据节点类型返回az值"""
        return "nova" if node_type == "vm" else ""

    def generate_k8s_nodes(self, cluster: ClusterObject, k8s_masters, k8s_nodes):
        forward_float_ip_id = ""
        if cluster.forward_float_ip_id:
            forward_float_ip_id = cluster.forward_float_ip_id
        # 在这里要判断cluster的类型是不是k8s的类型，如果是才需要生成k8s_masters和k8s_nodes
        if cluster.type != "kubernetes":
            return [], []
        node_db_list, instance_db_list = [], []
        node_index = 1
        master_index = 1
        cluster_new = copy.deepcopy(cluster)
        (master_cpu, master_gpu, master_mem, master_disk,
         master_flavor_id) = self.get_master_flavor_info(master_flvaor)
        master_operation_system, master_image_id = self.get_master_image_info(master_image)
        worker_node = []
        for idx, node in enumerate(cluster.node_config):
            if node.role == "master" and node.type == "vm":
                for i in range(node.count):
                    k8s_masters[f"master-{int(master_index)}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=master_flavor_id,
                        floating_ip=True,
                        etcd=True,
                        image_id=master_image_id
                    )
                    instance_db = InstanceDB()
                    instance_db.id = str(uuid.uuid4())
                    instance_db.node_type = node.type
                    instance_db.cluster_id = cluster.id
                    instance_db.cluster_name = cluster.name
                    instance_db.region = cluster.region_name
                    instance_db.user = node.user
                    instance_db.password = node.password
                    instance_db.security_group = cluster.name
                    instance_db.flavor_id = master_flavor_id
                    instance_db.image_id = master_image_id
                    instance_db.status = "creating"
                    instance_db.status_msg = ""
                    instance_db.floating_forward_ip = ""
                    instance_db.ip_forward_rule = []
                    instance_db.project_id = ""
                    instance_db.server_id = ""
                    instance_db.openstack_id = ""
                    instance_db.operation_system = master_operation_system
                    instance_db.cpu = master_cpu
                    instance_db.gpu = master_gpu
                    instance_db.mem = master_mem
                    instance_db.disk = master_disk
                    instance_db.ip_address = ""
                    instance_db.name = cluster.name + f"-k8s-master-{int(master_index)}"
                    instance_db.create_time = datetime.now()
                    instance_db_list.append(instance_db)

                    node_db = NodeDB()
                    node_db.id = str(uuid.uuid4())
                    node_db.node_type = node.type
                    node_db.cluster_id = cluster.id
                    node_db.cluster_name = cluster.name
                    node_db.region = cluster.region_name
                    node_db.role = node.role
                    node_db.user = node.user
                    node_db.password = node.password
                    node_db.image = master_image_id
                    node_db.instance_id = instance_db.id
                    node_db.project_id = cluster.project_id
                    node_db.auth_type = node.auth_type
                    node_db.security_group = cluster.name
                    node_db.flavor_id = master_flavor_id
                    node_db.operation_system = master_operation_system
                    node_db.cpu = master_cpu
                    node_db.gpu = master_gpu
                    node_db.mem = master_mem
                    node_db.disk = master_disk
                    node_db.status = "creating"
                    node_db.floating_forward_ip = ""
                    node_db.ip_forward_rule = []
                    node_db.status_msg = ""
                    node_db.admin_address = ""
                    node_db.name = cluster.name + f"-k8s-master-{int(master_index)}"
                    node_db.bus_address = ""
                    node_db.create_time = datetime.now()
                    node_db_list.append(node_db)
                    master_index=master_index+1
            if node.role == "worker" and node.type == "vm":
                cpu, gpu, mem, disk = self.get_flavor_info(node.flavor_id)
                operation_system = self.get_image_info(node.image)
                for i in range(node.count):
                    # 设置端口转发的外部端口
                    if cluster.port_forwards is not None:
                        for index, port_forward in enumerate(cluster.port_forwards):
                            if not port_forward.external_port or port_forward.external_port == "":
                                cluster_new.port_forwards[index].external_port = self.generate_random_port()
                                cluster_new.port_forwards[index].internal_port = port_forward.internal_port
                                cluster_new.port_forwards[index].protocol = port_forward.protocol
                    k8s_nodes[f"node-{int(node_index)}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False,
                        image_id=node.image,
                        port_forwards=cluster_new.port_forwards,
                        use_local_disk = node.use_local_disk,
                        volume_size=node.volume_size,
                        volume_type=node.volume_type
                    )
                    instance_db = InstanceDB()
                    instance_db.id = str(uuid.uuid4())
                    instance_db.node_type = node.type
                    instance_db.cluster_id = cluster.id
                    instance_db.cluster_name = cluster.name
                    instance_db.region = cluster.region_name
                    instance_db.user = node.user
                    instance_db.password = node.password
                    instance_db.security_group = node.security_group
                    instance_db.flavor_id = node.flavor_id
                    instance_db.status = "creating"
                    instance_db.floating_forward_ip = forward_float_ip_id
                    instance_db.ip_forward_rule = cluster_new.dict().get("port_forwards")
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
                    instance_db.name = cluster.name + f"-node-{int(node_index)}"
                    instance_db.floating_ip = cluster.forward_float_ip
                    instance_db.create_time = datetime.now()
                    instance_db_list.append(instance_db)

                    node_db = NodeDB()
                    node_db.id = str(uuid.uuid4())
                    node_db.node_type = node.type
                    node_db.cluster_id = cluster.id
                    node_db.cluster_name = cluster.name
                    node_db.region = cluster.region_name
                    node_db.role = node.role
                    node_db.user = node.user
                    node_db.password = node.password
                    node_db.image = node.image
                    node_db.instance_id = instance_db.id
                    node_db.project_id = cluster.project_id
                    node_db.auth_type = node.auth_type
                    node_db.security_group = node.security_group
                    node_db.flavor_id = node.flavor_id
                    node_db.operation_system = operation_system
                    node_db.cpu = cpu
                    node_db.gpu = gpu
                    node_db.mem = mem
                    node_db.disk = disk
                    node_db.status = "creating"
                    node_db.floating_forward_ip = forward_float_ip_id
                    node_db.floating_ip = cluster.forward_float_ip
                    node_db.ip_forward_rule = cluster_new.dict().get("port_forwards")
                    node_db.status_msg = ""
                    node_db.admin_address = ""
                    node_db.name = cluster.name + f"-node-{int(node_index)}"
                    node_db.bus_address = ""
                    node_db.create_time = datetime.now()
                    node_db_list.append(node_db)
                    cluster_new = copy.deepcopy(cluster)
                    node_index=node_index+1
                    worker_node.append(node)
            if node.role == "worker" and node.type == "baremetal":
                cpu, gpu, mem, disk = self.get_flavor_info(node.flavor_id)
                operation_system = self.get_image_info(node.image)
                for i in range(node.count):
                    # 设置端口转发的外部端口
                    if cluster.port_forwards is not None:
                        for index, port_forward in enumerate(cluster.port_forwards):
                            if not port_forward.external_port or port_forward.external_port == "":
                                cluster_new.port_forwards[index].external_port = self.generate_random_port()
                                cluster_new.port_forwards[index].internal_port = port_forward.internal_port
                                cluster_new.port_forwards[index].protocol = port_forward.protocol
                    k8s_nodes[f"node-{int(node_index)}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False,
                        image_id=node.image,
                        port_forwards=cluster_new.port_forwards
                    )
                    instance_db = InstanceDB()
                    instance_db.id = str(uuid.uuid4())
                    instance_db.node_type = node.type
                    instance_db.cluster_id = cluster.id
                    instance_db.cluster_name = cluster.name
                    instance_db.region = cluster.region_name
                    instance_db.user = node.user
                    instance_db.password = node.password
                    instance_db.security_group = node.security_group
                    instance_db.flavor_id = node.flavor_id
                    instance_db.status = "creating"
                    instance_db.floating_forward_ip = forward_float_ip_id
                    instance_db.ip_forward_rule = cluster_new.dict().get("port_forwards")
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
                    instance_db.name = cluster.name + f"-node-{int(node_index)}"
                    instance_db.floating_ip = cluster.forward_float_ip
                    instance_db.create_time = datetime.now()
                    instance_db_list.append(instance_db)

                    node_db = NodeDB()
                    node_db.id = str(uuid.uuid4())
                    node_db.node_type = node.type
                    node_db.cluster_id = cluster.id
                    node_db.cluster_name = cluster.name
                    node_db.region = cluster.region_name
                    node_db.role = node.role
                    node_db.user = node.user
                    node_db.password = node.password
                    node_db.image = node.image
                    node_db.instance_id = instance_db.id
                    node_db.project_id = cluster.project_id
                    node_db.auth_type = node.auth_type
                    node_db.security_group = node.security_group
                    node_db.flavor_id = node.flavor_id
                    node_db.operation_system = operation_system
                    node_db.cpu = cpu
                    node_db.gpu = gpu
                    node_db.mem = mem
                    node_db.disk = disk
                    node_db.status = "creating"
                    node_db.floating_forward_ip = forward_float_ip_id
                    node_db.floating_ip = cluster.forward_float_ip
                    node_db.ip_forward_rule = cluster_new.dict().get("port_forwards")
                    node_db.status_msg = ""
                    node_db.admin_address = ""
                    node_db.name = cluster.name + f"-node-{int(node_index)}"
                    node_db.bus_address = ""
                    node_db.create_time = datetime.now()
                    node_db_list.append(node_db)
                    cluster_new = copy.deepcopy(cluster)
                    node_index=node_index+1
                    worker_node.append(node)
        cluster.node_config = worker_node
        # 保存node信息到数据库
        NodeSQL.create_node_list(node_db_list)
        InstanceSQL.create_instance_list(instance_db_list)
        node_list_dict = []
        instance_list_dict = []
        for node in node_db_list:
            # Create a serializable dictionary from the NodeDB object
            node_dict = {
                "id": node.id,
                "image_id": node.image,
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
        node_list_json = json.dumps(node_list_dict)
        instance_list_json = json.dumps(instance_list_dict)
        return node_list_json, instance_list_json

    # 查询资产列表
    def list_clusters(self, query_params, page, page_size, sort_keys, sort_dirs):
        # 业务逻辑
        try:
            # 按照条件从数据库中查询数据
            count, data = ClusterSQL.list_cluster(query_params, page, page_size, sort_keys, sort_dirs)

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
            result = self.list_clusters(query_params, 1, 10, None, None)
            query_params = {}
            query_params["cluster_id"] = cluster_id
            res = NodeService().list_nodes(query_params, 1, 10, None, None)
            forward_float_ip = ""
            if len(res.get("data")) > 0:
                forward_float_ip = res.get("data")[0].floating_ip
            else:
                res = InstanceService().list_instances(query_params, 1, 10, None, None)
                if len(res.get("data")) > 0:
                    forward_float_ip = res.get("data")[0].floating_ip
            # 将cluster转为ClusterObject对象
            if not result.get("data"):
                return None
            cluster = result.get("data")[0]
            # Convert the parsed JSON to a KubeClusterObject
            kube_info = KubeClusterObject(**json.loads(cluster.kube_info))
            network_config = NetworkConfigObject()
            # 将cluster转为ClusterObject对象
            res_cluster = ClusterObject(
                id=cluster.id,
                name=cluster.name,
                project_id=cluster.project_id,
                user_id=cluster.user_id,
                labels=cluster.labels,
                status=cluster.status,
                status_msg= cluster.status_msg,
                region_name=cluster.region_name,
                type=cluster.type,
                kube_info=kube_info,
                created_at=cluster.create_time.timestamp() * 1000,
                updated_at=cluster.update_time.timestamp() * 1000,
                description=cluster.description,
                gpu=cluster.gpu,
                cpu=cluster.cpu,
                mem=cluster.mem,
                forward_float_ip=forward_float_ip,
                gpu_mem = cluster.gpu_mem,
                network_config=network_config,
                extra=cluster.extra,
                private_key=cluster.private_key
            )
            #查询网络信息
            res_cluster.network_config.kube_lb_address = kube_info.kube_lb_address
            if cluster.admin_network_id and cluster.admin_network_id != "":
                res_cluster.network_config.admin_network_name = cluster.admin_network_name
            if cluster.admin_subnet_id and cluster.admin_subnet_id!= "":
                res_cluster.network_config.admin_cidr = cluster.admin_network_cidr
            if cluster.bus_network_id and cluster.bus_network_id != "":
                res_cluster.network_config.bus_network_name = cluster.bus_network_name
            if cluster.bus_subnet_id and cluster.bus_subnet_id != "":
                res_cluster.network_config.bus_cidr = cluster.bus_network_cidr
            # 空
            # 查询节点信息
            node_query_params = {"cluster_id": cluster_id}
            nodeinfos = []
            if cluster.type == "baremetal":
                count, node_res = InstanceSQL.list_instances(node_query_params, 1, -1, None, None)
            else:
                count, node_res = NodeSQL.list_nodes(node_query_params, 1, -1, None, None)
            if count > 0:
                for n in node_res:
                    node_info = NodeConfigObject()
                    node_info.status = n.status
                    node_info.instance_id = n.id
                    nodeinfos.append(node_info) 
            res_cluster.node_config = nodeinfos
            res_cluster.node_count = count
            
            # 查询
            if not result or not result.get("data"):
                return None
            # 返回第一条数据
            return res_cluster
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def check_cluster_param(self, cluster: ClusterObject):
        # 判断名称是否重复、判断是否有空值、判断是否有重复的节点配置
        query_params = {}
        query_params["exact_name"] = cluster.name
        query_params["project_id"] = cluster.project_id
        res = self.list_clusters(query_params, 1, -1, None, None)
        if res.get("total") > 0:
            for c in res.get("data"):
                if c.status != "deleted":
                    # 如果查询结果不为空，说明集群名称已存在+
                    raise Fail(error_code=405, error_message="Cluster name already exists")
        if cluster.type not in ("kubernetes", "baremetal"):
            raise Fail(error_code=405, error_message="Cluster type must be kubernetes or baremetal")
        if not cluster.node_config:
            raise Fail(error_code=405, error_message="Cluster node_config parameter cannot be empty")
        else:
            if len(cluster.node_config) == 1 and cluster.type == "kubernetes":
                raise Fail(error_code=405, error_message="The number of nodes in the cluster cannot be less than 1.")
            for node_info in cluster.node_config:
                if node_info.role == "master":
                    continue
                if not node_info.image:
                    raise Fail(error_code=405, error_message="The image parameter of cluster node cannot be empty")
                if not node_info.flavor_id:
                    raise Fail(error_code=405, error_message="The flavor parameter of cluster node cannot be empty")
        if cluster.port_forwards:
            for port_info in cluster.port_forwards:
                if not port_info.internal_port:
                    raise Fail(error_code=405, error_message="The internal port parameter of node port "
                                                             "forwarding rule cannot be null.")
                if not port_info.protocol:
                    raise Fail(error_code=405, error_message="The protocol for node port forwarding rules "
                                                             "must be tcp or udp")
        return True
    
    def generate_random_cidr(self):
        import random
        
        # 第一部分固定为 10
        first_octet = 10
        
        # 第二部分范围从 100 到 130
        second_octet = random.randint(100, 130)
        
        # 第三部分范围从 0 到 255
        third_octet = random.randint(0, 255)
        
        # 第四部分固定为 0，因为是 /24 网段
        fourth_octet = 0
        
        # 生成 CIDR 字符串
        cidr = f"{first_octet}.{second_octet}.{third_octet}.{fourth_octet}/24"
        
        return cidr
    
    def generate_random_port(self):
        """从 20000 到 40000 范围内随机生成一个端口号"""
        import random
        return random.randint(20000, 40000)

    def create_cluster(self, cluster: ClusterObject, token):
        # 验证token
        # 数据校验 todo
        self.check_cluster_param(cluster)
        try:
            neutron_api = neutron.API()  # 创建API类的实例
            external_net = neutron_api.list_external_networks()

            lb_enbale = False
            if cluster.type == "kubernetes":
                lb_enbale = cluster.kube_info.loadbalancer_enabled

           
            cluster_info_db = self.convert_clusterinfo_todb(cluster)
            cluster.id = cluster_info_db.id
            k8s_masters = {}
            k8s_nodes = {}
            node_list, instance_list = self.generate_k8s_nodes(cluster, k8s_masters, k8s_nodes)

            # 保存instance信息到数据库
            instance_db_list, instance_bm_list = self.convert_instance_todb(cluster, k8s_nodes)
            InstanceSQL.create_instance_list(instance_db_list)
            # 生成一个随机的私有cidr
            subnet_cidr = self.generate_random_cidr()
            #获取浮动ip池
            floatingip_pool,public_floatingip_pool,public_subnetids,external_subnetids,external_net_id= self.get_floatip_pools(neutron_api, external_net)
            
            res = ClusterSQL.create_cluster(cluster_info_db)
            #设置端口转发的外部端口 
            # if cluster.port_forwards != None:
            #     for p in cluster.port_forwards:
            #         if p.external_port == None or p.external_port == "":
            #             p.external_port = self.generate_random_port()
            if not cluster.forward_float_ip_id:
                cluster.forward_float_ip_id = ""
            use_existing_network = False
            if cluster.network_config.admin_network_id == "":
                use_existing_network = True
            tfvars = ClusterTFVarsObject(
                id = cluster_info_db.id,
                cluster_name=cluster.name,
                image_uuid=cluster.node_config[0].image,
                nodes=k8s_nodes,
                subnet_cidr=subnet_cidr,
                floatingip_pool=floatingip_pool,
                public_floatingip_pool=public_floatingip_pool,
                public_subnetids=public_subnetids,
                external_subnetids=external_subnetids,
                external_net=external_net_id,
                use_existing_network=use_existing_network,
                ssh_user=cluster.node_config[0].user,
                k8s_master_loadbalancer_enabled=lb_enbale,
                number_of_k8s_masters = 1,
                number_of_k8s_masters_no_floating_ip = cluster.kube_info.number_master - 1,
                token = token,
                auth_url = auth_url,
                tenant_id=cluster.project_id,
                forward_float_ip_id = cluster.forward_float_ip_id,
                image_master = master_image
                )
            if cluster.node_config[0].auth_type == "password":
                tfvars.password = cluster.node_config[0].password
            elif cluster.node_config[0].auth_type == "keypair":
                tfvars.password = ""
            #组装cluster信息为ClusterTFVarsObject格式
            if cluster.type == "baremetal":
                tfvars.number_of_k8s_masters = 0
                tfvars.number_of_k8s_masters_no_floating_ip = 0
                result = celery_app.send_task("dingo_command.celery_api.workers.create_cluster",
                                          args=[tfvars.dict(), cluster.dict(), instance_bm_list ])
            elif cluster.type == "kubernetes":
                result = celery_app.send_task("dingo_command.celery_api.workers.create_k8s_cluster",
                                          args=[tfvars.dict(), cluster.dict(), node_list, instance_list ])
            elif cluster.type == "slurm":
                pass
            else:
                pass

            # 成功返回资产id
            return cluster_info_db
            
        except Fail as e:
            
            raise e

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

    def delete_cluster(self, cluster_id,token):
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
            cluster_info = res.get("data")[0]
            if cluster_info.status == "creating":
                raise HTTPException(status_code=400, detail="the cluster is creating, please wait")
            if cluster_info.status == "scaling":
                raise HTTPException(status_code=400, detail="the cluster is scaling, please wait")
            if cluster_info.status == "deleting":
                raise HTTPException(status_code=400, detail="the cluster is deleting, please wait")
            if cluster_info.status == "removing":
                raise HTTPException(status_code=400, detail="the cluster is removing, please wait")
            # 返回第一条数据
            cluster = res.get("data")[0]
            cluster.status = "deleting"
            # 保存对象到数据库
            res = ClusterSQL.update_cluster(cluster)
            region = cluster.region_name
            # 调用celery_app项目下的work.py中的delete_cluster方法
            # 更新node表和instance表中的状态为删除中
            node_query_params = {"cluster_id": cluster_id}
            node_res = NodeSQL.list_nodes(node_query_params, 1, -1, None, None)
            if node_res and node_res[0] > 0:
                nodes = node_res[1]
                node_list_db = []
                for node in nodes:
                    node.status = "deleting"
                    node.update_time = datetime.now()
                    node_list_db.append(node)
                NodeSQL.update_node_list(node_list_db)
                
            instance_query_params = {"cluster_id": cluster_id}
            instance_res = InstanceSQL.list_instances(instance_query_params, 1, -1, None, None)
            if instance_res and instance_res[0] > 0:
                instances = instance_res[1]
                session = get_session()
                with session.begin():
                    for instance in instances:
                        instance.status = "deleting"
                        instance.update_time = datetime.now()
            result = celery_app.send_task("dingo_command.celery_api.workers.delete_cluster", args=[cluster_id, token])
            # if result.get():
            #     # 删除成功，更新数据库状态
            #     cluster.status = "deleted"'
            #     res = ClusterSQL.update_cluster(cluster)
            # else:
            #     # 删除失败，更新数据库状态
            #     cluster.status = "delete_failed"
            #     res = ClusterSQL.update_cluster(cluster)
            return cluster
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e
    
    def add_existing_nodes_to_cluster(self, cluster_id: str, server_details: list, token: str):
        """将已有的服务器节点添加到K8s集群中"""
        try:
            # 1. 验证集群状态
            cluster = self.get_cluster(cluster_id)
            if not cluster:
                raise Fail("集群不存在")
            
            if cluster.status != "running":
                raise Fail(f"集群状态为{cluster.status}，无法添加节点")
            
            # 2. 更新集群状态为scaling
            query_params = {"id": cluster_id}
            res = self.list_clusters(query_params, 1, 10, None, None)
            if not res or not res.get("data"):
                raise Fail("集群不存在")
            
            cluster_db = res.get("data")[0]
            cluster_db.status = "scaling"
            ClusterSQL.update_cluster(cluster_db)
            #增加已有节点到node表
            node_db_list = []
            for server in server_details:
                node_db = NodeDB()
                node_db.id = str(uuid.uuid4())
                node_db.node_type = "vm"
                node_db.cluster_id = cluster_id
                node_db.cluster_name = cluster.name
                node_db.region = cluster.region_name
                node_db.role = "worker"
                node_db.image = server.image.id
                node_db.status = "running"
                #node_db.name = server.get("name", "")
                node_db.create_time = datetime.now()
                
                # 赋值其他字段，确保只传递对象，不传dict
                # 例如：node_db.user = server.get("user", "")
                #      node_db.cpu = server.get("cpu", 0)
                #      node_db.mem = server.get("mem", 0)
                #      node_db.disk = server.get("disk", 0)
                #      node_db.password = server.get("password", "")
                #      node_db.private_key = server.get("private_key", "")
                #      node_db.auth_type = server.get("auth_type", "")
                #      node_db.security_group = server.get("security_group", "")
                # 获取flavor信息
                if hasattr(server, "flavor") and server.flavor:
                    node_db.flavor_id = getattr(server.flavor, "id", "")
                    node_db.cpu = getattr(server.flavor, "vcpus", 0)
                    node_db.mem = getattr(server.flavor, "ram", 0)
                    node_db.disk = getattr(server.flavor, "disk", 0)
                else:
                    node_db.flavor_id = server.get("flavor_id", "")
                # 从 server.addresses 获取第一个 map 的 value 中的 addr
                admin_address = ""
                if hasattr(server, "addresses") and server.addresses:
                    # server.addresses 是一个 dict，取第一个 key 的 value
                    first_key = next(iter(server.addresses), None)
                    if first_key:
                        addr_list = server.addresses[first_key]
                        if isinstance(addr_list, list) and addr_list:
                            admin_address = addr_list[0].get("addr", "")
                node_db.admin_address = admin_address
                node_db_list.append(node_db)
                node_db.security_group = server.get("security_group", "")
            NodeSQL.create_node_list(node_db_list)  

            # 3. 调用Celery任务异步处理
            result = celery_app.send_task(
                "dingo_command.celery_api.workers.add_existing_nodes", 
                args=[cluster_id, server_details]
            )
            
            return {
                "task_id": result.id,
                "cluster_id": cluster_id,
                "message": "添加节点任务已提交",
                "server_count": len(server_details)
            }
            
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
        nova_client = NovaClient()
        cpu_total = 0
        mem_total = 0
        gpu_total = 0
        gpu_mem_total = 0
        for idx, node in enumerate(cluster.node_config):
            # 在这里添加master节点的cpu、mem等信息
            if node.role == "master" and node.type == "vm":
                cpu, gpu, mem, disk, flavor_id = self.get_master_flavor_info(node.flavor_id)
                cpu_total += cpu * node.count
                mem_total += mem * node.count
                gpu_total += gpu * node.count
            if node.role == "worker" and node.type == "vm":
                flavor = nova_client.nova_get_flavor(node.flavor_id)
                if flavor is not None:
                    cpu_total = cpu_total + flavor['vcpus'] * node.count
                    mem_total = mem_total + flavor['ram'] * node.count
                    if "extra_specs" in flavor and "pci_passthrough:alias" in flavor["extra_specs"]:
                        pci_alias = flavor['extra_specs']['pci_passthrough:alias']
                        if ':' in pci_alias:
                            gpu_value = pci_alias.split(':')[1].strip("'")
                            gpu_total = gpu_total + int(gpu_value) *  node.count
                    #gpu_mem_total += flavor['extra_specs']['gpu_mem']
                #查询flavor信息
            elif node.role == "worker" and node.type == "baremetal":
                flavor = nova_client.nova_get_flavor(node.flavor_id)
                cpu_total = cpu_total + flavor['vcpus'] * node.count
                mem_total = mem_total + flavor['ram'] * node.count
                if "extra_specs" in flavor and "resources:GPU" in flavor["extra_specs"]:
                    gpu_value = int(flavor["extra_specs"])
                    gpu_total = gpu_total + int(gpu_value) *  node.count
        cluster_info_db.gpu = gpu_total
        cluster_info_db.cpu = cpu_total
        cluster_info_db.mem = mem_total
        #gpu_mem_total = gpu_mem_total

        return cluster_info_db

    def convert_instance_todb(self, cluster:ClusterObject, k8s_nodes):
        forward_float_ip_id = ""
        if cluster.forward_float_ip_id:
            forward_float_ip_id = cluster.forward_float_ip_id
        if cluster.type != "baremetal":
            return [], []
        instance_db_list = []
        node_index = 1
        cluster_new = copy.deepcopy(cluster)
        for idx, node in enumerate(cluster.node_config):
            if node.role == "worker" and node.type == "vm":
                cpu, gpu, mem, disk = self.get_flavor_info(node.flavor_id)
                operation_system = self.get_image_info(node.image)
                for i in range(node.count):
                    if cluster.port_forwards is not None:
                        for index, port_forward in enumerate(cluster.port_forwards):
                            if not port_forward.external_port or port_forward.external_port == "":
                                cluster_new.port_forwards[index].external_port = self.generate_random_port()
                                cluster_new.port_forwards[index].internal_port = port_forward.internal_port
                                cluster_new.port_forwards[index].protocol = port_forward.protocol
                    k8s_nodes[f"node-{int(node_index)}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False,
                        image_id=node.image,
                        port_forwards=cluster_new.port_forwards,
                        use_local_disk = node.use_local_disk,
                        volume_size=node.volume_size,
                        volume_type=node.volume_type
                    )
                    instance_db = InstanceDB()
                    instance_db.id = str(uuid.uuid4())
                    instance_db.node_type = node.type
                    instance_db.cluster_id = cluster.id
                    instance_db.cluster_name = cluster.name
                    instance_db.region = cluster.region_name
                    instance_db.user = node.user
                    instance_db.password = node.password
                    instance_db.security_group = node.security_group
                    instance_db.flavor_id = node.flavor_id
                    instance_db.operation_system = operation_system
                    instance_db.server_id = ""
                    instance_db.cpu = cpu
                    instance_db.gpu = gpu
                    instance_db.mem = mem
                    instance_db.disk = disk
                    instance_db.status = "creating"
                    instance_db.floating_forward_ip = forward_float_ip_id
                    instance_db.ip_forward_rule = cluster_new.dict().get("port_forwards")
                    instance_db.ip_address = ""
                    instance_db.name = cluster.name + f"-node-{int(node_index)}"
                    instance_db.floating_ip = cluster.forward_float_ip
                    instance_db.create_time = datetime.now()
                    instance_db_list.append(instance_db)
                    cluster_new = copy.deepcopy(cluster)
                    node_index = node_index + 1
            if node.role == "worker" and node.type == "baremetal":
                cpu, gpu, mem, disk = self.get_flavor_info(node.flavor_id)
                operation_system = self.get_image_info(node.image)
                for i in range(node.count):
                    if cluster.port_forwards is not None:
                        for index, port_forward in enumerate(cluster.port_forwards):
                            if not port_forward.external_port or port_forward.external_port == "":
                                cluster_new.port_forwards[index].external_port = self.generate_random_port()
                                cluster_new.port_forwards[index].internal_port = port_forward.internal_port
                                cluster_new.port_forwards[index].protocol = port_forward.protocol
                    k8s_nodes[f"node-{int(node_index)}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        image_id=node.image,
                        etcd=False,
                        port_forwards=cluster_new.port_forwards
                    )
                    instance_db = InstanceDB()
                    instance_db.id = str(uuid.uuid4())
                    instance_db.node_type = node.type
                    instance_db.cluster_id = cluster.id
                    instance_db.cluster_name = cluster.name
                    instance_db.region = cluster.region_name
                    instance_db.user = node.user
                    instance_db.password = node.password
                    instance_db.security_group = node.security_group
                    instance_db.flavor_id = node.flavor_id
                    instance_db.operation_system = operation_system
                    instance_db.cpu = cpu
                    instance_db.gpu = gpu
                    instance_db.mem = mem
                    instance_db.disk = disk
                    instance_db.server_id = ""
                    instance_db.status = "creating"
                    instance_db.floating_forward_ip = forward_float_ip_id
                    instance_db.ip_forward_rule = cluster_new.dict().get("port_forwards")
                    instance_db.ip_address = ""
                    instance_db.name = cluster.name + f"-node-{int(node_index)}"
                    instance_db.floating_ip = cluster.forward_float_ip
                    instance_db.create_time = datetime.now()
                    instance_db_list.append(instance_db)
                    cluster_new = copy.deepcopy(cluster)
                    node_index = node_index + 1

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
        return instance_db_list, instance_list_json

    def get_create_params(self):
        res = ParamSQL.list()
        return res[1]

    def get_flavor_info(self, flavor_id):
        nova_client = NovaClient()
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

    def get_image_info(self, image_id):
        operation_system = ""
        nova_client = NovaClient()
        image = nova_client.glance_get_image(image_id)
        if image is not None:
            if image.get("os_version"):
                operation_system = image.get("os_version")
            elif image.get("os_distro"):
                operation_system = image.get("os_distro")
            else:
                operation_system = image.get("name")
        return operation_system

    def get_key_file(self, cluster_id:str, instance_id:str):
        # 根据id查询集群
        if  instance_id is not None and not cluster_id:
            # 如果传入了instance_id，则根据instance_id查询集群
            instance_query_params = {}
            instance_query_params["id"] = instance_id
            instance_res = InstanceSQL.list_instances(instance_query_params, 1, 10, None, None)
            # 空
            if not instance_res or instance_res[0]==0:
                return None
            # 返回第一条数据
            instance = instance_res[1]
            if instance[0].private_key is not None and instance[0].private_key != "":
                return instance[0].private_key
            cluster_id = instance.cluster_id
        if cluster_id == "" or not cluster_id:
            return None
        query_params = {}
        query_params["id"] = cluster_id
        res = self.list_clusters(query_params, 1, 10, None, None)
        # 如果集群不存在
        if not res or not res.get("data"):
            return None
            
        # 获取集群信息
        cluster = res.get("data")[0]
        private_key = cluster.private_key
        # 检查是否有私钥
        if not cluster.private_key:
            # 如果数据库没有保存私钥，尝试从文件系统获取
            key_file_path = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id), "id_rsa")
            if os.path.exists(key_file_path):
                with open(key_file_path, "r") as f:
                    private_key = f.read()
            else:
                raise Fail("找不到集群对应的私钥文件")
        return private_key

    def get_master_flavor_info(self, master_flavor_name):
        nova_client = NovaClient()
        flavor = nova_client.nova_get_flavor(master_flavor_name)
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
        return int(cpu), int(gpu), int(mem), int(disk), flavor.get("id")

    def get_master_image_info(self, master_image_name):
        operation_system = ""
        nova_client = NovaClient()
        image = nova_client.glance_get_image(master_image_name)
        if image:
            if image.get("os_version"):
                operation_system = image.get("os_version")
            elif image.get("os_distro"):
                operation_system = image.get("os_distro")
            else:
                operation_system = image.get("name")
        return operation_system, image.get("id")


class TaskService:
    
    class TaskMessage(Enum):
        #instructure_check = "参数校验"
        instructure_create = "创建基础设施"
        pre_install = "安装前准备"
        runtime_prepair = "运行时准备"
        etcd_deploy = "安装etcd"
        controller_deploy = "配置kubernetes控制面"
        worker_deploy = "配置kubernetes工作节点"
        component_deploy = "安装组件"

    class TaskBaremetalMessage(Enum):
        instructure_create = "创建基础设施"

    class TaskScaleBaremetalMessage(Enum):
        scale_instructure = "扩容基础设施"

    class TaskScaleNodeMessage(Enum):
        scale_instructure = "扩容基础设施"
        scale_pre_install = "扩容前准备"
        scale_runtime_prepair = "运行时准备"
        scale_check_file = "检查二进制文件"
        scale_check_image = "检查镜像"
        scale_join_cluster = "加入集群"
        # scale_install_calico = "安装calico"
        # scale_calico_check = "检查calico安装是否完成"

    class TaskRemoveBaremetalMessage(Enum):
        remove_instructure = "缩容基础设施"

    class TaskRemoveNodeMessage(Enum):
        # remove_instructure_create = "缩容缩容基础设施"
        remove_pre_install = "缩容前准备"
        remove_from_cluster = "从集群中移除"
        remove_cri_pods = "清理节点的pod"
        remove_iptables = "清理iptables或者ipvs"
        remove_file_dirs = "清理文件和目录"

    class TaskDeleteMessage(Enum):
        delete_instructure = "删除基础设施"

    class TaskDetail(Enum):
        #instructure_check = "instructure check passed"
        instructure_create = "instructure create success"
        pre_install = "install prepare success"
        runtime_prepair = "runtime prepare success"
        etcd_deploy = "etcd deploy success"
        controller_deploy = "control plane deploy success"
        worker_deploy = "worker node deploy success"
        component_deploy = "component deploy success"

        scale_instructure = "instructure create success"
        scale_pre_install = "install prepare success"
        scale_runtime_prepair = "runtime prepare success"
        scale_install_file = "install file success"
        scale_download_images = "download images success"
        scale_join_cluster = "join cluster success"
        scale_install_calico = "install calico cni"

        remove_pre_install = "remove prepare success"
        remove_from_cluster = "remove member from cluster success"
        remove_cri_pods = "remove pods from node success"
        remove_iptables = "clear iptables or ipvs success"
        remove_file_dirs = "delete some files and directories success"

    def get_tasks_param(self, type):
        tasks_with_title = []
        if type == "baremetal":
            task_dict = {
                'msg': TaskService.TaskMessage.instructure_check.name,
                'state': "waiting",
                'detail': getattr(task, 'detail', None),
                'start_time': None,
                'end_time': None,
                # 根据task名称匹配TaskMessage枚举值添加中文标题
                'title': TaskService.TaskMessage.instructure_check.value
            }
            tasks_with_title.append(task_dict)
            task_dict2 = {
                'msg': TaskService.TaskMessage.instructure_create.name,
                'state': "waiting",
                'detail': getattr(task, 'detail', None),
                'start_time': None,
                'end_time': None,
                # 根据task名称匹配TaskMessage枚举值添加中文标题
                'title': TaskService.TaskMessage.instructure_create.value
            }
            tasks_with_title.append(task_dict2)

        else:

            for task in TaskService.TaskMessage:
                task_dict = {
                    'msg': task.name,
                    'state': "waiting",
                    'detail': getattr(task, 'detail', None),
                    'start_time': None,
                    'end_time': None,
                    # 根据task名称匹配TaskMessage枚举值添加中文标题
                    'title': task.value
                }
                tasks_with_title.append(task_dict)
        return tasks_with_title

    def handle_task(self, tasks, task_service, tasks_with_title, task_id=None):
        inprogress = False
        for task in task_service:
            for t in tasks:
                if task_id and t.task_id != task_id:
                    continue
                inprogress = False
                if t.msg == task.name:
                    task_dict = {
                        'task_id': getattr(t, 'task_id', None),
                        'msg': getattr(t, 'msg', None),
                        'cluster_id': getattr(t, 'cluster_id', None),
                        'state': getattr(t, 'state', None),
                        'detail': getattr(t, 'detail', None),
                        'start_time': getattr(t, 'start_time', None),
                        'end_time': getattr(t, 'end_time', None),
                        # 根据task名称匹配TaskMessage枚举值添加中文标题
                        'title': task_service[t.msg].value if hasattr(task_service, t.msg) else t.msg
                    }
                    tasks_with_title.append(task_dict)
                    inprogress = True
                    break
            if inprogress:
                continue
            task_dict = {
                'msg': task.name,
                'state': "waiting",
                'detail': getattr(task, 'detail', None),
                'start_time': None,
                'end_time': None,
                # 根据task名称匹配TaskMessage枚举值添加中文标题
                'title': task.value
            }
            tasks_with_title.append(task_dict)
        return tasks_with_title
        
    def get_tasks(self, cluster_id):
        if not cluster_id:
            return None
        # 详情
        try:
            # 根据id查询
            query_params = {}
            query_params["cluster_id"] = cluster_id
            res = TaskSQL.list(query_params, None, None)
            cluster = ClusterService().get_cluster(cluster_id)
            # 空
            if not res or not cluster:
                return None
            # 返回第一条数据
            tasks_with_title = []
            tasks = res[1]
            if cluster.type == "baremetal":
                tasks_with_title = self.handle_task(tasks, TaskService.TaskBaremetalMessage, tasks_with_title)
            elif cluster.type == "kubernetes":
                tasks_with_title = self.handle_task(tasks, TaskService.TaskMessage, tasks_with_title)
            else:
                pass
            return tasks_with_title
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def get_scale_tasks(self, cluster_id):
        if not cluster_id:
            return None
        # 详情
        try:
            # 根据id查询
            query_params = {}
            query_params["cluster_id"] = cluster_id
            res = TaskSQL.list(query_params, None, None)
            cluster = ClusterService().get_cluster(cluster_id)
            # 空
            if not res or not cluster:
                return None
            # 返回第一条数据
            task_id = None
            if cluster.extra:
                task_dict = json.loads(cluster.extra)
                if task_dict.get("task_id"):
                    task_id = task_dict.get("task_id")

            tasks_with_title = []
            tasks = res[1]
            if cluster.type == "baremetal":
                tasks_with_title = self.handle_task(tasks, TaskService.TaskScaleBaremetalMessage,
                                                    tasks_with_title, task_id)
            elif cluster.type == "kubernetes":
                tasks_with_title = self.handle_task(tasks, TaskService.TaskScaleNodeMessage, tasks_with_title, task_id)
            else:
                pass
            return tasks_with_title
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def get_remove_tasks(self, cluster_id):
        if not cluster_id:
            return None
        # 详情
        try:
            # 根据id查询
            query_params = {}
            query_params["cluster_id"] = cluster_id
            res = TaskSQL.list(query_params, None, None)
            cluster = ClusterService().get_cluster(cluster_id)
            # 空
            if not res or not cluster:
                return None
            # 返回第一条数据
            task_id = None
            if cluster.extra:
                task_dict = json.loads(cluster.extra)
                if task_dict.get("task_id"):
                    task_id = task_dict.get("task_id")

            tasks_with_title = []
            tasks = res[1]
            if cluster.type == "baremetal":
                tasks_with_title = self.handle_task(tasks, TaskService.TaskRemoveBaremetalMessage,
                                                    tasks_with_title, task_id)
            elif cluster.type == "kubernetes":
                tasks_with_title = self.handle_task(tasks, TaskService.TaskRemoveNodeMessage, tasks_with_title, task_id)
            else:
                pass
            return tasks_with_title
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def get_delete_tasks(self, cluster_id):
        if not cluster_id:
            return None
        # 详情
        try:
            # 根据id查询
            query_params = {}
            query_params["cluster_id"] = cluster_id
            res = TaskSQL.list(query_params, None, None)
            # 空
            if not res:
                return None
            # 返回第一条数据
            tasks_with_title = []
            tasks = res[1]
            tasks_with_title = self.handle_task(tasks, TaskService.TaskDeleteMessage, tasks_with_title)
            return tasks_with_title
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e
