# 资产的service层
import json
import os
import uuid

from datetime import datetime

from openpyxl.styles import Border, Side

from dingo_command.celery_api.celery_app import celery_app
from dingo_command.db.models.instance.sql import InstanceSQL
from math import ceil
from oslo_log import log
from dingo_command.api.model.instance import InstanceCreateObject, OpenStackConfigObject
from dingo_command.api.model.cluster import ClusterTFVarsObject, NodeGroup, ScaleNodeObject, NodeRemoveObject
from dingo_command.api.model.base import BaseResponse, ErrorResponse, ErrorDetail
from dingo_command.db.models.instance.models import Instance as InstanceDB
from dingo_command.db.models.cluster.models import Cluster as ClusterDB
from dingo_command.db.models.cluster.sql import ClusterSQL
from dingo_command.db.engines.mysql import get_engine, get_session
from dingo_command.common import neutron

from dingo_command.services.custom_exception import Fail
from dingo_command.common.nova_client import nova_client

from dingo_command.services import CONF

WORK_DIR = CONF.DEFAULT.cluster_work_dir
auth_url = CONF.DEFAULT.auth_url
image_master = CONF.DEFAULT.k8s_master_image
LOG = log.getLogger(__name__)
BASE_DIR = os.getcwd()

# 定义边框样式
thin_border = Border(
    left=Side(border_style="thin", color="000000"),  # 左边框
    right=Side(border_style="thin", color="000000"),  # 右边框
    top=Side(border_style="thin", color="000000"),  # 上边框
    bottom=Side(border_style="thin", color="000000")  # 下边框
)


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
                return {"data": None}
            # 返回第一条数据
            return {"data": res.get("data")[0]}
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def create_instance(self, instance: InstanceCreateObject):
        # 在这里使用openstack的api接口，直接创建vm或者裸金属，根据type类型决定是创建vm还是裸金属，走不同的流程
        # 创建instance，创建openstack种的虚拟机或者裸金属服务器，如果属于某个cluster就写入cluster_id
        # 数据校验 todo
        try:
            number = instance.numbers
            if number == 0:
                return ErrorResponse(code=400, status="fail", message="number parameter is 0, no instance is created",
                                     error=ErrorDetail(type="ValidationError"))
            neutron_api = neutron.API()  # 创建API类的实例
            external_net = neutron_api.list_external_networks()
            (floatingip_pool, public_floatingip_pool, public_subnetids,
             external_subnetids, external_net_id) = self.get_floatip_pools(neutron_api, external_net)
            # 写入instance信息到数据库中
            instance_info_db_list, instance_list = self.convert_instance_todb(instance)
            InstanceSQL.create_instance_list(instance_info_db_list)
            # 获取openstack的参数，传入到create_instance的方法中，由这create_instance创建vm或者裸金属
            # 调用celery_app项目下的work.py中的create_instance方法
            result = celery_app.send_task("dingo_command.celery_api.workers.create_instance",
                                          args=[instance.dict(), instance_list, external_net_id])
            return BaseResponse(data=result.id)
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def delete_instance(self, opensatck_info: OpenStackConfigObject, instance):
        # 详情
        try:
            # 具体要操作的步骤，删除openstack中的server，删除数据库中instance表里面的该instance的数据
            instance_db, instance_dict = self.update_instance_todb(instance)
            InstanceSQL.update_instance(instance_db)
            # 调用celery_app项目下的work.py中的delete_instance方法
            result = celery_app.send_task("dingo_command.celery_api.workers.delete_instance",
                                          args=[opensatck_info.dict(), instance_dict])
            return BaseResponse(data=result.id)
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

    def generate_random_port(self):
        """从 20000 到 40000 范围内随机生成一个端口号"""
        import random
        return random.randint(20000, 40000)

    def generate_k8s_nodes(self, cluster_info, cluster, k8s_nodes, forward_rules, forward_float_ip_id):
        node_db_list, instance_db_list = [], []
        max_key = max(k8s_nodes, key=lambda k: int(k.split('-')[-1]))
        node_index = int(max_key.split('-')[-1]) + 1
        for idx, node in enumerate(cluster.node_config):
            if node.role == "worker" and node.type == "vm":
                cpu, gpu, mem, disk = self.get_flavor_info(node.flavor_id)
                operation_system = self.get_image_info(node.image)
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
                        port_forwards=forward_rules_new
                    )
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
                    node_index = node_index + 1
            if node.role == "worker" and node.type == "baremental":
                cpu, gpu, mem, disk = self.get_flavor_info(node.flavor_id)
                operation_system = self.get_image_info(node.image)
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
                        port_forwards=forward_rules_new
                    )
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

        instance_list_json = json.dumps(instance_list_dict)
        InstanceSQL.create_instance_list(instance_db_list)
        return instance_list_json

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
        if public_subnetids == []:
            public_subnetids = external_subnetids
        return floatingip_pool,public_floatingip_pool,public_subnetids,external_subnetids,external_net_id

    def create_baremetal(self, cluster_info, cluster: ScaleNodeObject, token):
        # 扩容baremetal集群的节点
        # 创建instance，创建openstack种的虚拟机或者裸金属服务器
        # 数据校验 todo
        try:
            for conf in cluster.node_config:
                if conf.role == "master":
                    raise ValueError("The expanded node cannot be the master node.")
            # 从集群数据库里获取这个集群的集群信息，然后拼接出一个扩容的信息，或者从output.tfvars.json信息里获取
            # cluster_service = ClusterService()
            # clust_dbinfo = cluster_service.get_cluster(cluster.id)

            output_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "terraform",
                                       "output.tfvars.json")
            with open(output_file) as f:
                content = json.loads(f.read())

            cluster_info_db = self.convert_clusterinfo_todb(cluster_info.id, cluster_info.name)
            ClusterSQL.update_cluster(cluster_info_db)
            k8s_nodes = content["nodes"]
            subnet_cidr = content.get("subnet_cidr")
            forward_float_ip_id = content.get("forward_float_ip_id")
            neutron_api = neutron.API()  # 创建API类的实例
            external_net = neutron_api.list_external_networks()
            (floatingip_pool, public_floatingip_pool, public_subnetids,
             external_subnetids, external_net_id) = self.get_floatip_pools(neutron_api, external_net)
            forward_rules = []
            for k, v in k8s_nodes.items():
                if v.get("port_forwards"):
                    forward_rules = v.get("port_forwards")
                    break
            instance_list = self.generate_k8s_nodes(cluster_info, cluster, k8s_nodes,
                                                    forward_rules, forward_float_ip_id)

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
            # 调用celery_app项目下的work.py中的create_cluster方法
            result = celery_app.send_task("dingo_command.celery_api.workers.create_cluster",
                                          args=[tfvars.dict(), cluster_info.dict(), instance_list])
            return result.id
        except Fail as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def delete_baremetal(self, cluster_id, cluster_name, node_list, token):
        # 详情
        try:
            # 写入集群的状态为正在缩容的状态，防止其他缩容的动作重复执行
            cluster_info_db = self.update_clusterinfo_todb(cluster_id, cluster_name)
            ClusterSQL.update_cluster(cluster_info_db)
            # 写入节点的状态为正在deleting的状态
            # 写入instance的状态为正在deleting的状态
            instance_db_list, instance_dict = self.update_instances_todb(node_list)
            InstanceSQL.update_instance_list(instance_db_list)

            # 调用celery_app项目下的work.py中的delete_cluster方法
            result = celery_app.send_task("dingo_command.celery_api.workers.delete_baremetal",
                                          args=[cluster_id, cluster_name, instance_dict, token])
            return result.id
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def convert_instance_todb(self, instance_info):
        instance_info_db_list = []
        flavor = nova_client.nova_get_flavor(instance_info.flavor_id)
        operation_system = ""
        image = nova_client.glance_get_image(instance_info.image_id)
        if image is not None:
            if image.get("os_version"):
                operation_system = image.get("os_version")
            elif image.get("os_distro"):
                operation_system = image.get("os_distro")
            else:
                operation_system = image.get("name")
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
        user, password, network_id, cluster_id, cluster_name, sshkey_name = "", "", "", "", "", ""
        if instance_info.user:
            user = instance_info.user
        if instance_info.password:
            password = instance_info.password
        if instance_info.network_id:
            network_id = instance_info.network_id
        if instance_info.cluster_id:
            cluster_id = instance_info.cluster_id
        if instance_info.cluster_name:
            cluster_name = instance_info.cluster_name
        if instance_info.sshkey_name:
            sshkey_name = instance_info.sshkey_name
        if instance_info.security_group:
            security_group = instance_info.security_group
        else:
            security_group = "default"
        if instance_info.numbers == 1:
            instance_info_db = InstanceDB()
            instance_info_db.id = str(uuid.uuid4())
            instance_info_db.name = instance_info.name
            instance_info_db.status = "creating"
            instance_info_db.status_msg = ""
            instance_info_db.server_id = ""
            instance_info_db.openstack_id = ""
            instance_info_db.ip_address = ""
            instance_info_db.operation_system = operation_system
            instance_info_db.user = user
            instance_info_db.password = password
            instance_info_db.cpu = int(cpu)
            instance_info_db.gpu = int(gpu)
            instance_info_db.mem = int(mem)
            instance_info_db.disk = int(disk)
            instance_info_db.node_type = instance_info.node_type
            instance_info_db.flavor_id = instance_info.flavor_id
            instance_info_db.image_id = instance_info.image_id
            instance_info_db.network_id = network_id
            instance_info_db.create_time = datetime.now()
            instance_info_db.cluster_id = cluster_id
            instance_info_db.cluster_name = cluster_name
            instance_info_db.project_id = instance_info.openstack_info.project_id
            instance_info_db.sshkey_name = sshkey_name
            instance_info_db.security_group = security_group
            instance_info_db.region = instance_info.openstack_info.region
            instance_info_db_list.append(instance_info_db)
        else:
            for i in range(1, int(instance_info.numbers) + 1):
                instance_info_db = InstanceDB()
                instance_info_db.id = str(uuid.uuid4())
                instance_info_db.name = instance_info.name + "-" + str(i)
                instance_info_db.status = "creating"
                instance_info_db.status_msg = ""
                instance_info_db.server_id = ""
                instance_info_db.openstack_id = ""
                instance_info_db.ip_address = ""
                instance_info_db.operation_system = operation_system
                instance_info_db.user = user
                instance_info_db.password = password
                instance_info_db.cpu = int(cpu)
                instance_info_db.gpu = int(gpu)
                instance_info_db.mem = int(mem)
                instance_info_db.disk = int(disk)
                instance_info_db.node_type = instance_info.node_type
                instance_info_db.flavor_id = instance_info.flavor_id
                instance_info_db.image_id = instance_info.image_id
                instance_info_db.network_id = network_id
                instance_info_db.create_time = datetime.now()
                instance_info_db.cluster_id = cluster_id
                instance_info_db.cluster_name = cluster_name
                instance_info_db.project_id = instance_info.openstack_info.project_id
                instance_info_db.sshkey_name = sshkey_name
                instance_info_db.security_group = security_group
                instance_info_db.region = instance_info.openstack_info.region
                instance_info_db_list.append(instance_info_db)

        instance_list_dict = []
        for instance in instance_info_db_list:
            # Create a serializable dictionary from the instanceDB object
            instance_dict = {
                "id": instance.id,
                "instance_type": instance.node_type,
                "cluster_id": instance.cluster_id,
                "cluster_name": instance.cluster_name,
                "region": instance.region,
                "image_id": instance.image_id,
                "network_id": instance.network_id,
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
        return instance_info_db_list, instance_list_json

    def update_instance_todb(self, instance):
        instance_info_db = InstanceDB()
        instance_info_db.id = instance.id
        instance_info_db.status = "deleting"
        instance_info_db.server_id = instance.server_id
        instance_info_db.update_time = datetime.now()
        # Create a serializable dictionary from the instanceDB object
        instance_dict = {
            "id": instance.id,
            "status": instance.status,
            "server_id": instance.server_id,
            "update_time": instance.update_time.isoformat() if instance.update_time else None
        }
        return instance_info_db, instance_dict

    def update_clusterinfo_todb(self, cluster_id, cluster_name):
        session = get_session()
        db_cluster = session.get(ClusterDB, (cluster_id, cluster_name))
        db_cluster.status = "removing"
        db_cluster.update_time = datetime.now()
        return db_cluster

    def update_instances_todb(self, node_list):
        session = get_session()
        instance_info_list = []
        instance_db_list = []
        for node in node_list:
            db_instance = session.get(InstanceDB, node.id)
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