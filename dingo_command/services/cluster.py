# 资产的service层
from enum import Enum
import json
import uuid
from datetime import datetime

from openpyxl.styles import Border, Side

from dingo_command.celery_api.celery_app import celery_app

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
from dingo_command.common.nova_client import NovaClient, nova_client
from dingo_command.services.custom_exception import Fail
from dingo_command.services.system import SystemService



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
        # 在这里要判断cluster的类型是不是k8s的类型，如果是才需要生成k8s_masters和k8s_nodes
        if cluster.type != "kubernetes":
            return [], []
        node_db_list, instance_db_list = [], []
        node_index = 1
        master_index = 1
        for idx, node in enumerate(cluster.node_config):
            if node.role == "master" and node.type == "vm":
                cpu, gpu, mem, disk = self.get_flavor_info(node.flavor_id)
                operation_system = self.get_image_info(node.image)
                for i in range(node.count):
                    k8s_masters[f"master-{int(master_index)}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=True,
                        etcd=True
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
                    instance_db.project_id = ""
                    instance_db.server_id = ""
                    instance_db.openstack_id = ""
                    instance_db.operation_system = operation_system
                    instance_db.cpu = cpu
                    instance_db.gpu = gpu
                    instance_db.mem = mem
                    instance_db.disk = disk
                    instance_db.ip_address = ""
                    instance_db.name = cluster.name + f"master-{int(master_index)}"
                    instance_db.floating_ip = ""
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
                    node_db.private_key = node.private_key
                    node_db.project_id = cluster.project_id
                    node_db.auth_type = node.auth_type
                    node_db.security_group = node.security_group
                    node_db.flavor_id = node.flavor_id
                    node_db.status = "creating"
                    node_db.admin_address = ""
                    node_db.name = cluster.name + f"-master-{int(master_index)}"
                    node_db.bus_address = ""
                    node_db.create_time = datetime.now()
                    node_db_list.append(node_db)
                    master_index=master_index+1
            if node.role == "worker" and node.type == "vm":
                cpu, gpu, mem, disk = self.get_flavor_info(node.flavor_id)
                operation_system = self.get_image_info(node.image)
                for i in range(node.count):
                    k8s_nodes[f"node-{int(node_index)}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False
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
                    instance_db.floating_ip = ""
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
                    node_db.private_key = node.private_key
                    node_db.project_id = cluster.project_id
                    node_db.auth_type = node.auth_type
                    node_db.security_group = node.security_group
                    node_db.flavor_id = node.flavor_id
                    node_db.status = "creating"
                    node_db.admin_address = ""
                    node_db.name = cluster.name + f"-node-{int(node_index)}"
                    node_db.bus_address = ""
                    node_db.create_time = datetime.now()
                    node_db_list.append(node_db)
                    node_index=node_index+1
            if node.role == "worker" and node.type == "baremental":
                cpu, gpu, mem, disk = self.get_flavor_info(node.flavor_id)
                operation_system = self.get_image_info(node.image)
                for i in range(node.count):
                    k8s_nodes[f"node-{int(node_index)}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False
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
                    instance_db.floating_ip = ""
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
                    node_db.private_key = node.private_key
                    node_db.project_id = cluster.project_id
                    node_db.auth_type = node.auth_type
                    node_db.security_group = node.security_group
                    node_db.flavor_id = node.flavor_id
                    node_db.status = "creating"
                    node_db.admin_address = ""
                    node_db.name = cluster.name + f"-node-{int(node_index)}"
                    node_db.bus_address = ""
                    node_db.create_time = datetime.now()
                    node_db_list.append(node_db)
                    node_index=node_index+1
        # 保存node信息到数据库
        NodeSQL.create_node_list(node_db_list)
        InstanceSQL.create_instance_list(instance_db_list)
        node_list_dict = []
        instance_list_dict = []
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
            network_config = NetworkConfigObject()
            # 将cluster转为ClusterObject对象
            res_cluster = ClusterObject(
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
                gpu=cluster.gpu,
                cpu=cluster.cpu,
                mem=cluster.mem,
                gpu_mem = cluster.gpu_mem,
                network_config=network_config,
                extra=cluster.extra
            )
            #查询网络信息
            neutron_api = neutron.API()  # 创建API类的实例
            if cluster.admin_network_id != "null":
                admin_network = neutron_api.get_network_by_id(cluster.admin_network_id)
                res_cluster.network_config.admin_network_name = admin_network.get("name")
            if cluster.admin_subnet_id != "null":   
                admin_subnet = neutron_api.get_subnet_by_id(cluster.admin_subnet_id)
                res_cluster.network_config.admin_cidr = admin_subnet.get("cidr")
            if cluster.bus_network_id != "null":
                bus_network = neutron_api.get_network_by_id(cluster.bus_network_id)
                res_cluster.network_config.bus_network_name = bus_network.get("name")
            if cluster.bus_subnet_id != "null":   
                bus_subnet = neutron_api.get_subnet_by_id(cluster.bus_subnet_id)
                res_cluster.network_config.bus_cidr = bus_subnet.get("cidr")
            # 空
            # 查询节点信息
            node_query_params = {"cluster_id": cluster_id}
            node_res = NodeSQL.list_nodes(node_query_params, 1, -1, None, None)
            nodeinfos = []
            if node_res and node_res[0] > 0:
                for n in node_res:
                    node_info = NodeConfigObject()
                    node_info.auth_type = n.auth_type
                    node_info.status = n.status
                    node_info.instance_id = n.instance_id   
                
            if not res or not res.get("data"):
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
        query_params["name"] = cluster.name
        query_params["project_id"] = cluster.project_id
        res = self.list_clusters(query_params, 1, -1, None, None)
        if res.get("total") > 0:
            raise Fail("集群名称已存在")
        return True

    def create_cluster(self, cluster: ClusterObject):
        # 数据校验 todo
        self.check_cluster_param(cluster)
        try:
            cluster_info_db = self.convert_clusterinfo_todb(cluster)
            res = ClusterSQL.create_cluster(cluster_info_db)

            neutron_api = neutron.API()  # 创建API类的实例
            external_net = neutron_api.list_external_networks()

            lb_enbale = False
            if cluster.kube_info.number_master>1 and cluster.type == "kubernetes":
                lb_enbale = cluster.kube_info.loadbalancer_enabled
           

            #组装cluster信息为ClusterTFVarsObject格式
            cluster.id = cluster_info_db.id
            k8s_masters = {}
            k8s_nodes = {}
            node_list, instance_list = self.generate_k8s_nodes(cluster, k8s_masters, k8s_nodes)

            # 保存instance信息到数据库
            instance_db_list, instance_bm_list = self.convert_instance_todb(cluster, k8s_nodes)
            InstanceSQL.create_instance_list(instance_db_list)
            # 创建terraform变量
            
            tfvars = ClusterTFVarsObject(
                id = cluster_info_db.id,
                cluster_name=cluster.name,
                image=cluster.node_config[0].image,
                nodes=k8s_nodes,
                subnet_cidr="192.168.10.0/24",
                floatingip_pool=external_net[0]['name'],
                external_net=external_net[0]['id'],
                use_existing_network=False,
                ssh_user=cluster.node_config[0].user,
                k8s_master_loadbalancer_enabled=lb_enbale,
                number_of_k8s_masters = cluster.kube_info.number_master
                )
            if cluster.node_config[0].auth_type == "password":
                tfvars.password = cluster.node_config[0].password
            elif cluster.node_config[0].auth_type == "keypair":
                tfvars.password = ""
            #组装cluster信息为ClusterTFVarsObject格式
            if cluster.type == "baremental":
                tfvars.number_of_k8s_masters = 0
                result = celery_app.send_task("dingo_command.celery_api.workers.create_cluster",
                                          args=[tfvars.dict(), cluster.dict(), instance_bm_list ])
            elif cluster.type == "kubernetes":
                print(tfvars.dict())
                print(cluster.dict())
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
                instance_list_db = []
                for instance in instances:
                    instance.status = "deleting"
                    instance.update_time = datetime.now()
                    instance_list_db.append(instance)
                InstanceSQL.update_instance_list(instance_list_db)
            result = celery_app.send_task("dingo_command.celery_api.workers.delete_cluster", args=[cluster_id, region])
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
            if node.role == "worker" and node.type == "vm":
                flavor = nova_client.nova_get_flavor(node.flavor_id)
                if flavor is not None:
                    cpu_total += flavor['vcpus']
                    mem_total += flavor['ram']
                    if "extra_specs" in flavor and "pci_passthrough:alias" in flavor["extra_specs"]:
                        pci_alias = flavor['extra_specs']['pci_passthrough:alias']
                        if ':' in pci_alias:
                            gpu_value = pci_alias.split(':')[1].strip("'")
                            gpu_total += int(gpu_value)
                    #gpu_mem_total += flavor['extra_specs']['gpu_mem']
                #查询flavor信息
            elif node.role == "worker" and node.type == "baremental":
                flavor = nova_client.nova_get_flavor(node.flavor_id)
                cpu_total += flavor['vcpus']
                mem_total += flavor['ram']
                if "extra_specs" in flavor and "resources:GPU" in flavor["extra_specs"]:
                    gpu_value = int(flavor["extra_specs"])
                    gpu_total += int(gpu_value)
        cluster_info_db.gpu = gpu_total
        cluster_info_db.cpu = cpu_total
        cluster_info_db.mem = mem_total
        #gpu_mem_total = gpu_mem_total

        return cluster_info_db

    def convert_instance_todb(self, cluster:ClusterObject, k8s_nodes):
        if cluster.type != "baremental":
            return [], []
        instance_db_list = []
        node_index = 1
        for idx, node in enumerate(cluster.node_config):
            if node.role == "worker" and node.type == "vm":
                for i in range(node.count):
                    k8s_nodes[f"node-{int(node_index)}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False
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
                    instance_db.ip_address = ""
                    instance_db.name = cluster.name + f"node-{int(node_index)}"
                    instance_db.floating_ip = ""
                    instance_db.create_time = datetime.now()
                    instance_db_list.append(instance_db)
                    node_index = node_index + 1
            if node.role == "worker" and node.type == "baremental":
                for i in range(node.count):
                    k8s_nodes[f"node-{int(node_index)}"] = NodeGroup(
                        az=self.get_az_value(node.type),
                        flavor=node.flavor_id,
                        floating_ip=False,
                        etcd=False
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
                    instance_db.ip_address = ""
                    instance_db.name = cluster.name + f"node-{int(node_index)}"
                    instance_db.floating_ip = ""
                    instance_db.create_time = datetime.now()
                    instance_db_list.append(instance_db)
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
        image = nova_client.glance_get_image(image_id)
        if image is not None:
            if image.get("os_version"):
                operation_system = image.get("os_version")
            elif image.get("os_distro"):
                operation_system = image.get("os_distro")
            else:
                operation_system = image.get("name")
        return operation_system


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