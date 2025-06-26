from datetime import datetime
import json
import random
import ipaddress
import base64
import os
import re
import subprocess
import time
import copy
from typing import Dict, Optional, List
from dingo_command.api.model.cluster import ClusterObject
from dingo_command.api.model.instance import InstanceCreateObject
from dingo_command.celery_api.ansible import run_playbook
from dingo_command.celery_api.util import update_task_state
from dingo_command.services.cluster import TaskService
from dingo_command.db.models.cluster.models import Cluster, Taskinfo
from dingo_command.db.models.node.models import NodeInfo
from dingo_command.db.models.instance.models import Instance
from pydantic import BaseModel, Field
from openstack import connection
from requests import Session
from keystoneauth1.identity import v3
from keystoneauth1.session import Session as KeySession
from dingo_command.celery_api.celery_app import celery_app
from dingo_command.celery_api import CONF
from dingo_command.db.engines.mysql import get_engine, get_session
from dingo_command.db.models.cluster.sql import ClusterSQL, TaskSQL
from dingo_command.common import CONF as CommonConf
from dingo_command.common.nova_client import NovaClient
from dingo_command.common import neutron
from dingo_command.common.cinder_client import CinderClient
from celery.exceptions import SoftTimeLimitExceeded

from dingo_command.db.models.node.sql import NodeSQL
from dingo_command.db.models.instance.sql import InstanceSQL
from dingo_command.api.model.instance import OpenStackConfigObject

from jinja2 import Environment, FileSystemLoader

BASE_DIR = os.getcwd()
TERRAFORM_DIR = os.path.join(BASE_DIR, "dingo_command", "templates", "terraform")
ANSIBLE_DIR = os.path.join(BASE_DIR, "templates", "ansible-deploy")
WORK_DIR = CONF.DEFAULT.cluster_work_dir
HARBOR_URL = CONF.DEFAULT.harbor_url
FILESERVER_URL = CONF.DEFAULT.fileserver_url
UBUNTU_REPO = CONF.DEFAULT.ubuntu_repo

TIMEOUT = 600
SERVER_TIMEOUT = 1200
NOVA_AUTH_URL = CommonConf.nova.auth_url
SSH_KEY_NAME = "instance_key"
INSTANCE_NET_NAME = "instance_network"
INSTANCE_ROUTER_NAME = "instance_router"
INSTANCE_SUBNET_NAME = "instance_subnet"
TASK_TIMEOUT = CONF.DEFAULT.task_timeout
SOFT_TASK_TIMEOUT = CONF.DEFAULT.soft_task_timeout
PUSHGATEWAY_URL = CONF.DEFAULT.pushgateway_url

runtime_task_name = "Check container-engine status"
etcd_task_name = "Check etcd cluster status"
control_plane_task_name = "Check control plane status"
work_node_task_name = "Check k8s nodes status"

# scale_swap = "Disable swap"
# scale_stop_kubelet = "Stop kubelet"
scale_install_crictl = "Install crictl"
scale_download_images = "Download | Download files / images"
scale_get_token = "Set kubeadm_token to generated token"
scale_install_calico = "Calico install"

remove_from_cluster = "Remove member from cluster"
remove_cri_pods = "Reset | stop all cri pods"
remove_iptables = "Clear IPVS virtual server table"
remove_file_dirs = "Reset | delete some files and directories"

class PortForwards(BaseModel):
    internal_port: Optional[int] = Field(None, description="转发的内部端口")
    external_port: Optional[int] = Field(None, description="转发的外部端口")
    protocol: Optional[str] = Field(None, description="协议")


class NodeGroup(BaseModel):
    az: Optional[str] = Field(None, description="可用域")
    flavor: Optional[str] = Field(None, description="规格")
    floating_ip: Optional[bool] = Field(None, description="浮动ip")
    etcd: Optional[bool] = Field(None, description="是否是etcd节点")
    image_id: Optional[str] = Field(None, description="镜像id")
    port_forwards: Optional[List[PortForwards]] = Field(None, description="端口转发配置")
    use_local_disk: Optional[bool] = Field(None, description="实例id")
    volume_type: Optional[str] = Field(None, description="卷类型")
    volume_size: Optional[int] = Field(None, description="卷大小")

class ClusterTFVarsObject(BaseModel):
    id: Optional[str] = Field(None, description="集群id")
    cluster_name: Optional[str] = Field(None, description="集群id")
    image_uuid: Optional[str] = Field(None, description="用户id")
    nodes: Optional[Dict[str, NodeGroup]] = Field(None, description="集群状态")
    admin_subnet_id: Optional[str] = Field(None, description="管理子网id")
    bus_network_id: Optional[str] = Field(None, description="业务网络id")
    admin_network_id: Optional[str] = Field(None, description="管理网id")
    bus_subnet_id: Optional[str] = Field(None, description="业务子网id")
    ssh_user: Optional[str] = Field(None, description="用户名")
    password: Optional[str] = Field(None, description="密码")
    floatingip_pool: Optional[str] = Field(None, description="浮动ip池")
    public_floatingip_pool: Optional[str] = Field(None, description="公网浮动ip池") 
    external_subnetids: Optional[list[str]] = Field(None, description="公网浮动ip池") 
    public_subnetids: Optional[list[str]] = Field(None, description="公网浮动ip池") 
    subnet_cidr: Optional[str] = Field(None, description="运行时类型")
    use_existing_network: Optional[bool] = Field(None, description="是否使用已有网络")
    external_net: Optional[str] = Field(None, description="外部网络id")
    group_vars_path: Optional[str] = Field(None, description="集群变量路径")
    number_of_etcd: Optional[int] = Field(0, description="ETCD节点数量")
    number_of_k8s_masters: Optional[int] = Field(0, description="K8s master节点数量")
    number_of_k8s_masters_no_etcd: Optional[int] = Field(0, description="不带ETCD的K8s master节点数量")
    number_of_k8s_masters_no_floating_ip: Optional[int] = Field(0, description="无浮动IP的K8s master节点数量")
    number_of_k8s_masters_no_floating_ip_no_etcd: Optional[int] = Field(0,
                                                                        description="无浮动IP且不带ETCD的K8s master节点数量")
    number_of_k8s_nodes: Optional[int] = Field(0, description="K8s worker节点数量")
    number_of_k8s_nodes_no_floating_ip: Optional[int] = Field(0, description="无浮动IP的K8s worker节点数量")
    k8s_master_loadbalancer_enabled: Optional[bool] = Field(False, description="是否启用负载均衡器")
    private_key_path: Optional[str] = Field(None, description="私钥路径")
    public_key_path: Optional[str] = Field(None, description="公钥路径")
    tenant_id: Optional[str] = Field(None, description="租户id")
    auth_url: Optional[str] = Field(None, description="鉴权url")
    token: Optional[str] = Field(None, description="token")
    forward_float_ip_id: Optional[str] = Field("", description="集群浮动ip的id")
    port_forwards: Optional[list[PortForwards]] = Field(None, description="端口转发配置")
    image_master: Optional[str] = Field(None, description="master节点的镜像")
    router_id: Optional[str] = Field(None, description="路由id")
    bastion_floatip_id: Optional[str] = Field(None, description="堡垒机浮动ip的id")
    bastion_fips: Optional[list[str]] = Field(None, description="堡垒机浮动ip的地址")
    etcd_volume_type: Optional[str] = Field(None, description="堡垒机浮动ip的地址")
    pushgateway_url: Optional[str] = Field("", description="Prometheus Pushgateway的URL")

def replace_ansi_with_single_newline(text):
    ansi_pattern = re.compile(r'\x1b\[[\d;]*[a-zA-Z]')
    text_with_newlines = ansi_pattern.sub('\n', text)
    consecutive_newline_pattern = re.compile(r'\n{2,}')
    cleaned_text = consecutive_newline_pattern.sub('\n', text_with_newlines)
    return cleaned_text

def get_node_info(node_list):
    cpu_int_total = 0
    gpu_int_total = 0
    mem_int_total = 0
    for node in node_list:
        if node.get("cpu"):
            cpu_int = node.get("cpu")
            cpu_int_total += cpu_int
        if node.get("gpu"):
            gpu_int = node.get("gpu")
            gpu_int_total += gpu_int
        if node.get("mem"):
            mem_int = node.get("mem")
            mem_int_total += mem_int
    return cpu_int_total, gpu_int_total, mem_int_total

def set_instance_status(cluster, node_list, node_type=None):
    cluster_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", cluster.id)
    host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", cluster.id, "hosts")
    os.chmod(host_file, 0o755)
    res = subprocess.run(["python3", host_file, "--root", cluster_dir, "--list"], capture_output=True, text=True)
    hosts_data = json.loads(res.stdout)
    session = get_session()
    nova_client = NovaClient()
    with session.begin():
        for node in node_list:
            db_instance = session.get(node_type, node.get("id"))
            for k, v in hosts_data["_meta"]["hostvars"].items():
                # 需要添加节点的ip地址等信息
                if db_instance.name == k:
                    db_instance.server_id = v.get("id")
                    server = nova_client.nova_get_server_detail(v.get("id"))
                    if server.get("status") == "ERROR":
                        db_instance.status = "error"
                        db_instance.status_msg = server.get("fault").get("details")
                    elif server.get("status") == "ACTIVE":
                        db_instance.status = "running"
                    else:
                        db_instance.status = server.get("status")

def state_remove(node_list):
    for node in node_list:
        try:
            subprocess.run(
                ["terraform", "state", "rm", f"module.compute.openstack_compute_instance_v2.nodes[\"{node}\"]"],
                capture_output=True,
                text=True,
                check=True
            )
            subprocess.run(
                ["terraform", "state", "rm", f"module.compute.openstack_networking_port_v2.nodes_port[\"{node}\"]"],
                capture_output=True,
                text=True,
                check=True
            )
        except Exception as e:
            if "No matching objects found" in str(e):
                continue
    print(f"rm nodes from terraform state successfully")

def create_infrastructure(cluster:ClusterTFVarsObject, task_info:Taskinfo, scale=False, node_list=None,
                          node_type=None, instance_list=None):
    """使用Terraform创建基础设施"""
    try:
        cluster_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id))
        if not scale:
            # 将templat下的terraform目录复制到WORK_DIR/cluster.id目录下
            subprocess.run(["cp", "-LRpf", os.path.join(WORK_DIR, "ansible-deploy", "inventory", "sample-inventory"),
                        str(cluster_dir)], capture_output=True)
            subprocess.run(["cp", "-r", str(TERRAFORM_DIR), str(cluster_dir)], capture_output=True)
        os.chdir(os.path.join(cluster_dir, "terraform"))
        # 初始化terraform
        #os.environ['https_proxy']="10.220.70.88:1088"
        if cluster.password == "":
            if os.path.exists(os.path.join(cluster_dir, "id_rsa")) \
                    and os.path.exists(os.path.join(cluster_dir, "id_rsa.pub")):
                cluster.private_key_path = os.path.join(cluster_dir, "id_rsa")
                cluster.public_key_path = os.path.join(cluster_dir, "id_rsa.pub")
            else:
                res = subprocess.run(
                    ["ssh-keygen", "-t", "rsa", "-b", "4096", "-C", "", "-f", os.path.join(str(cluster_dir), "id_rsa"),
                     "-N", ""], capture_output=True, text=True)
                if res.returncode != 0:
                    # 发生错误时更新任务状态为"失败"
                    task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                    task_info.state = "failed"
                    task_info.detail = res.stderr
                    update_task_state(task_info)
                    print(f"ssh-keygen error: {res.stderr}")
                    return False, res.stderr
                cluster.private_key_path = os.path.join(cluster_dir, "id_rsa")
                cluster.public_key_path = os.path.join(cluster_dir, "id_rsa.pub")
        neutron_api = neutron.API()  # 创建API类的实例
        router = neutron_api.get_router_by_name(CONF.DEFAULT.cluster_router_name, cluster.tenant_id)
        if router is not None:
            cluster.router_id = router.get("id", "")
        else:
            cluster.router_id = ""
        fip_id, fip_address = neutron_api.get_first_floatingip_id_by_tags(
            tags=["bastion_fip"],
            tenant_id=cluster.tenant_id
        )
        cluster.bastion_floatip_id = fip_id
        cluster.bastion_fips = [fip_address]
        if fip_address == "": 
            cluster.bastion_fips = []
        

        cluster.group_vars_path = os.path.join(cluster_dir, "group_vars")
        tfvars_str = json.dumps(cluster, default=lambda o: o.__dict__, indent=2)
        
        with open("output.tfvars.json", "w") as f:
            f.write(tfvars_str)
            
        os.environ['CURRENT_CLUSTER_DIR']=cluster_dir
        res = subprocess.run(["terraform", "init"], capture_output=True, text=True)
        if res.returncode != 0:
            # 发生错误时更新任务状态为"失败"
            task_info.end_time =datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "failed"
            task_info.detail = res.stderr
            update_task_state(task_info)
            print(f"Terraform init error: {res.stderr}")
            return False, replace_ansi_with_single_newline(res.stderr)
       
        # 执行terraform apply
        # os.environ['OS_CLOUD']=cluster.region_name
        #os.environ['OS_CLOUD']=region_name
        #判断是否存在名为cluster-router的路由

        res = subprocess.run([
            "terraform",
            "apply",
            "-auto-approve",
            "-var-file=output.tfvars.json",
            "-lock=false"
        ], capture_output=True, text=True) 
        if res.returncode != 0:
            # 发生错误时更新任务状态为"失败"
            task_info.end_time =datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "failed"
            task_info.detail = "deploy base infrastructure failed, reason: " + res.stderr
            update_task_state(task_info)
            print(f"Terraform apply error: {res.stderr}")
            set_instance_status(cluster, node_list, node_type=node_type)
            if node_type == NodeInfo and instance_list:
                set_instance_status(cluster, instance_list, node_type=Instance)
            return False, replace_ansi_with_single_newline(res.stderr)
        key_file_path = os.path.join(WORK_DIR, "ansible-deploy", "inventory",str(cluster.id), "id_rsa")
        private_key_content = ""
        if os.path.exists(key_file_path):
            with open(key_file_path, 'r') as key_file:
                private_key_content = key_file.read()
        query_params = {}
        query_params["id"] = cluster.id
        count, data = ClusterSQL.list_cluster(query_params)
        if count > 0 and not scale:
            db_cluster = data[0]
            host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", cluster.id, "hosts")
            # Give execute permissions to the host file
            os.chmod(host_file, 0o755)
            (network_id, network_name, bus_network_id, bus_network_name,
             subnet_id, bussubnet_id) = get_networks(cluster, task_info, host_file, cluster_dir)
            db_cluster.admin_network_id = network_id
            db_cluster.admin_subnet_id = subnet_id
            db_cluster.bus_network_id = bus_network_id
            db_cluster.bus_subnet_id = bussubnet_id
            db_cluster.private_key = private_key_content
            db_cluster.admin_network_name = network_name
            db_cluster.admin_network_cidr = cluster.subnet_cidr
            db_cluster.bus_network_name = bus_network_name
            if bussubnet_id != "":
                neutron_api = neutron.API()
                bus_subnet = neutron_api.get_subnet_by_id(bussubnet_id)
                db_cluster.bus_network_cidr = bus_subnet.get("cidr")
            #db_cluster.status = "running"
            ClusterSQL.update_cluster(db_cluster)

        # 更新任务状态为"成功"
        task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        task_info.state = "success"
        task_info.detail = "base infrastructure created successfully"
        update_task_state(task_info)
        print("Terraform apply succeeded")
        return True, ""

    except subprocess.CalledProcessError as e:
        # 发生错误时更新任务状态为"失败"
        task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        task_info.state = "failed"
        task_info.detail = str(e)
        update_task_state(task_info)
        print(f"Terraform error: {e}")
        return False, str(e)


@celery_app.task(bind=True, time_limit=TASK_TIMEOUT, soft_time_limit=SOFT_TASK_TIMEOUT)
def create_cluster(self, cluster_tf, cluster_dict, instance_bm_list, scale=False):
    try:
        task_id = str(self.request.id)
        if scale:
            update_task_info(task_id, cluster_dict.get("id"), cluster_dict.get("name"))
        cluster_id = cluster_tf["id"]
        print(f"tf: {cluster_tf}, cluster_dict: {cluster_dict}")
        print(f"Task ID: {task_id}, Cluster ID: {cluster_id}")
        cluster_tfvars = ClusterTFVarsObject(**cluster_tf)
        cluster = ClusterObject(**cluster_dict)

        instance_list = json.loads(instance_bm_list)
        if not scale:
            instructure_task = Taskinfo(task_id=task_id, cluster_id=cluster_tf["id"], state="progress",
                                        start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                        msg=TaskService.TaskMessage.instructure_create.name)
            TaskSQL.insert(instructure_task)
        else:
            instructure_task = Taskinfo(task_id=task_id, cluster_id=cluster_tf["id"], state="progress",
                                        start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                        msg=TaskService.TaskScaleBaremetalMessage.scale_instructure.name)
            TaskSQL.insert(instructure_task)
        terraform_result = create_infrastructure(cluster_tfvars, instructure_task,
                                                 scale=scale, node_list=instance_list, node_type=Instance)
        if not terraform_result[0]:
            raise Exception(f"Terraform infrastructure creation failed, reason: {terraform_result[1]}")

        cluster_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", cluster_tfvars.id)
        host_file = os.path.join(cluster_dir, "hosts")
        res = subprocess.run(["python3", host_file, "--root", cluster_dir, "--list"], capture_output=True, text=True)
        if res.returncode != 0:
            # 更新数据库的状态为failed
            instructure_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
            instructure_task.state = "failed"
            instructure_task.detail = str(res.stderr)
            update_task_state(instructure_task)
            raise Exception(f"Error generating Ansible inventory: {str(res.stderr)}")

        instructure_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        instructure_task.state = "success"
        instructure_task.detail = TaskService.TaskDetail.instructure_create.value
        update_task_state(instructure_task)
        print("Terraform apply succeeded")

        hosts = res.stdout
        # todo 添加节点时，需要将节点信息写入到inventory/inventory.yaml文件中
        # 如果是密码登录与master节点1做免密
        hosts_data = json.loads(hosts)
        terraform_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "terraform")
        output_file = os.path.join(terraform_dir, "output.tfvars.json")
        with open (output_file) as f:
            content = json.loads(f.read())
        session = get_session()
        # 更新集群instance的状态为running
        with session.begin():
            for instance in instance_list:
                db_instance = session.get(Instance, instance.get("id"))
                for k, v in hosts_data["_meta"]["hostvars"].items():
                    # 需要添加节点的ip地址等信息
                    if db_instance.name == k:
                        db_instance.server_id = v.get("id")
                        db_instance.status = "running"
                        db_instance.cidr = content.get("subnet_cidr")
                        db_instance.ip_address = v.get("ip")
                        db_instance.security_group = cluster.name
        query_params = {}
        query_params["id"] = cluster_tf["id"]
        count, db_clusters = ClusterSQL.list_cluster(query_params)
        db_cluster = db_clusters[0]
        db_cluster.status = 'running'
        if scale:
            cpu_total, gpu_total, mem_total = get_node_info(instance_list)
            db_cluster.cpu += cpu_total
            db_cluster.gpu += gpu_total
            db_cluster.mem += mem_total
        db_cluster.status_msg = ""
        ClusterSQL.update_cluster(db_cluster)
    except SoftTimeLimitExceeded:
        query_params = {}
        query_params["id"] = cluster_dict["id"]
        count, db_clusters = ClusterSQL.list_cluster(query_params)
        c = db_clusters[0]
        if scale:
            c.status = 'scale_error'
            c.status_msg = "The scale cluster task has timed out."
        else:
            c.status = 'error'
            c.status_msg = "The create_cluster task has timed out."
        ClusterSQL.update_cluster(c)
        raise
    except Exception as e:
        # 发生错误时更新集群状态为"失败"
        query_params = {}
        query_params["id"] = cluster_tf["id"]
        count, db_clusters = ClusterSQL.list_cluster(query_params)
        db_cluster = db_clusters[0]
        if scale:
            db_cluster.status = 'scale_error'
        else:
            db_cluster.status = 'error'
        db_cluster.status_msg = replace_ansi_with_single_newline(str(e))
        ClusterSQL.update_cluster(db_cluster)
        raise

def deploy_kubernetes(cluster: ClusterObject, lb_ip: str, task_id: str = None):
    """使用Ansible部署K8s集群"""
    runtime_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress",
                         start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                         msg=TaskService.TaskMessage.runtime_prepair.name)
    etcd_task = Taskinfo()
    control_plane_task = Taskinfo()
    worker_task = Taskinfo()
    component_task = Taskinfo()
    try:
        # #替换
        # # 定义上下文字典，包含所有要替换的变量值
        template_file = "offline.yml.j2"
        context = {
            'harbor_url': HARBOR_URL,
            'fileserver_url': FILESERVER_URL,
            'ubuntu_repo': UBUNTU_REPO
        }
        target_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "group_vars", "all")
        os.makedirs(target_dir, exist_ok=True)
        cluster_file = os.path.join(target_dir, "offline.yml")
        render_templatefile(template_file, cluster_file, context)
        
        template_file = "k8s-cluster.yml.j2"
        context = {
            'kube_version': cluster.kube_info.version,
            'kube_network_plugin': cluster.kube_info.cni,
            'service_cidr': cluster.kube_info.service_cidr,
            "kube_vip_address": lb_ip,
            "kube_proxy_mode": cluster.kube_info.kube_proxy_mode,
            "container_manager": cluster.kube_info.runtime,
        }
        target_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "group_vars", "k8s_cluster")
        os.makedirs(target_dir, exist_ok=True)
        cluster_file = os.path.join(target_dir, "k8s-cluster.yml")
        render_templatefile(template_file, cluster_file, context)

        # 将templates下的ansible-deploy目录复制到WORK_DIR/cluster.id目录下
        runtime_task.start_time = datetime.fromtimestamp(datetime.now().timestamp())
        task_info = runtime_task
        TaskSQL.insert(runtime_task)
        ansible_dir = os.path.join(WORK_DIR, "ansible-deploy")
        os.chdir(ansible_dir)
        host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id))
        playbook_file = os.path.join(WORK_DIR, "ansible-deploy", "cluster.yml")
        key_file_path = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "id_rsa")
        private_key_content = None
        if os.path.exists(key_file_path):
            with open(key_file_path, 'r') as key_file:
                private_key_content = key_file.read()
        
        print(f"start deploy kubernetes cluster: {str(cluster.id)}")
        thread, runner = run_playbook(playbook_file, host_file, ansible_dir, ssh_key=private_key_content)
        # 处理并打印事件日志
        runtime_bool = False
        etcd_bool = False
        controller_bool = False
        worker_bool = False
        while runner.status not in ['canceled', 'successful', 'timeout', 'failed']:
            # 处理事件日志
            for event in runner.events:
                # 检查事件是否包含 task 信息
                if 'event_data' in event and 'task' in event['event_data']:
                    task_name = event['event_data'].get('task')
                    host =  event['event_data'].get('host')
                    task_status = event['event'].split('_')[-1]  # 例如 runner_on_ok -> ok
                    # 处理 etcd 任务的特殊逻辑
                    # print(f"任务 {task_name} 在主机 {host} 上 Status: {event['event']}")
                    if task_name == runtime_task_name and host is not None:
                        if not runtime_bool:
                            runtime_bool = True
                            runtime_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                            runtime_task.state = "success"
                            runtime_task.detail = TaskService.TaskDetail.runtime_prepair.value
                            update_task_state(runtime_task)
                            # 写入下一个任务
                            etcd_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress",
                                                 start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                                 msg=TaskService.TaskMessage.etcd_deploy.name)
                            TaskSQL.insert(etcd_task)
                            task_info = etcd_task
                    if task_name == etcd_task_name and host is not None:
                        if not etcd_bool:
                            etcd_bool = True
                            etcd_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                            etcd_task.state = "success"
                            etcd_task.detail = TaskService.TaskDetail.etcd_deploy.value
                            update_task_state(etcd_task)
                            # 写入下一个任务
                            control_plane_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress",
                                                          start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                                          msg=TaskService.TaskMessage.controller_deploy.name)
                            TaskSQL.insert(control_plane_task)
                            task_info = control_plane_task
                    if task_name == control_plane_task_name and host is not None:
                        if not controller_bool:
                            controller_bool = True
                            control_plane_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                            control_plane_task.state = "success"
                            control_plane_task.detail = TaskService.TaskDetail.controller_deploy.value
                            update_task_state(control_plane_task)
                            # 写入下一个任务
                            worker_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress",
                                                   start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                                   msg=TaskService.TaskMessage.worker_deploy.name)
                            TaskSQL.insert(worker_task)
                            task_info = worker_task
                    if task_name == work_node_task_name and host is not None and task_status != "failed":
                        if not worker_bool:
                            worker_bool = True
                            worker_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                            worker_task.state = "success"
                            worker_task.detail = TaskService.TaskDetail.worker_deploy.value
                            update_task_state(worker_task)
                            component_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress",
                                                      start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                                      msg=TaskService.TaskMessage.component_deploy.name)
                            TaskSQL.insert(component_task)
                            task_info = component_task
            #time.sleep(0.01)
            continue
        log_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "ansible_debug.log")
        with open(log_file, "a") as log_file:
            log_file.write(format(runner.stdout.read()))
        thread.join()
        # 检查最终状态
        if runner.rc != 0:
            # 更新数据库的状态为failed
            task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "failed"
            task_info.detail = "ansible deploy kubernetes error"
            update_task_state(task_info)
            raise Exception("Deploy kubernetes failed, please check log")

        component_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        component_task.state = "success"
        component_task.detail = TaskService.TaskDetail.component_deploy.value
        update_task_state(component_task)
        return True, ""
    
    except Exception as e:
        print(f"Ansible error: {e}")
        return False, str(e)

def render_templatefile(template_file, cluster_file, context):
   
        # 修正模板文件路径
    #template_file = "k8s-cluster.yml.j2"
    template_dir = os.path.join(BASE_DIR, "dingo_command", "templates")
    template_path = os.path.join(template_dir, template_file)

        # 确保模板文件存在
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"模板文件不存在: {template_path}")

        # 创建Jinja2环境 - 使用相对路径而不是绝对路径
    env = Environment(
            loader=FileSystemLoader(template_dir),
            variable_start_string='${',
            variable_end_string='}'
        )

        # 获取模板并渲染
    template = env.get_template(template_file)  # 只使用文件名而不是完整路径
    rendered = template.render(**context)

        # 将渲染后的内容写入新文件，使用 UTF-8 编码确保兼容性
    with open(cluster_file, 'w', encoding='utf-8') as f:
        f.write(rendered)


def update_ansible_status(task_info, event, task_name, host, task_status):
    if task_name == work_node_task_name and host is not None:
        # 处理 etcd 任务的特殊逻辑
        print(f"任务 {task_name} 在主机 {host} 上 Status: {event['event']}")
        if task_status != "failed":
            # 处理 etcd 任务失败的逻辑
            print(f"etcd 任务失败: {task_name} 在主机 {host} 上")
            # 处理任务成功的逻辑
            print(f"任务失败: {task_name} 在主机 {host} 上")
            # 更新数据库的状态为failed
            task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "success"
            task_info.detail = event['event_data'].get('res').get('msg')
            update_task_state(task_info)


def scale_kubernetes(cluster: ClusterObject, scale_nodes, task_id):
    """使用Ansible扩容K8s集群"""
    try:
        runtime_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress",
                                start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                msg=TaskService.TaskScaleNodeMessage.scale_runtime_prepair.name)
        etcd_task = Taskinfo()
        control_plane_task = Taskinfo()
        worker_task = Taskinfo()
        component_task = Taskinfo()
        task_info = runtime_task
        TaskSQL.insert(runtime_task)
        ansible_dir = os.path.join(WORK_DIR, "ansible-deploy")
        os.chdir(ansible_dir)
        host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id))
        playbook_file = os.path.join(WORK_DIR, "ansible-deploy", "scale.yml")
        key_file_path = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "id_rsa")
        if os.path.exists(key_file_path):
            with open(key_file_path, 'r') as key_file:
                private_key_content = key_file.read()
        else:
            private_key_content = None

        thread, runner = run_playbook(playbook_file, host_file, ansible_dir,
                                      ssh_key=private_key_content, limit=scale_nodes)
        # 处理并打印事件日志
        runtime_bool = False
        etcd_bool = False
        controller_bool = False
        worker_bool = False
        while runner.status not in ['canceled', 'successful', 'timeout', 'failed']:
            for event in runner.events:
                # 检查事件是否包含 task 信息
                if 'event_data' in event and 'task' in event['event_data']:
                    task_name = event['event_data'].get('task')
                    host = event['event_data'].get('host')
                    task_status = event['event'].split('_')[-1]  # 例如 runner_on_ok -> ok
                    # print(f"任务 {task_name} 在主机 {host} 上 Status: {event['event']}")
                    # print(f"task_name is: {task_name}")
                    if task_name == scale_download_images and host is not None:
                        if not runtime_bool:
                            runtime_bool = True
                            runtime_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                            runtime_task.state = "success"
                            runtime_task.detail = TaskService.TaskDetail.scale_runtime_prepair.value
                            update_task_state(runtime_task)
                            # 写入下一个任务
                            etcd_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress",
                                                 start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                                 msg=TaskService.TaskScaleNodeMessage.scale_check_file.name)
                            TaskSQL.insert(etcd_task)
                            task_info = etcd_task
                    if task_name == scale_get_token and host is not None:
                        if not etcd_bool:
                            etcd_bool = True
                            etcd_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                            etcd_task.state = "success"
                            etcd_task.detail = TaskService.TaskDetail.scale_install_file.value
                            update_task_state(etcd_task)
                            # 写入下一个任务
                            control_plane_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress",
                                                          start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                                          msg=TaskService.TaskScaleNodeMessage.scale_check_image.name)
                            TaskSQL.insert(control_plane_task)
                            task_info = control_plane_task
                    if task_name == scale_install_calico and host is not None and task_status != "failed":
                        if not controller_bool:
                            controller_bool = True
                            control_plane_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                            control_plane_task.state = "success"
                            control_plane_task.detail = TaskService.TaskDetail.scale_download_images.value
                            update_task_state(control_plane_task)
                            # 写入下一个任务
                            worker_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress",
                                                   start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                                   msg=TaskService.TaskScaleNodeMessage.scale_join_cluster.name)
                            TaskSQL.insert(worker_task)
                            task_info = worker_task
                    # if task_name == scale_install_calico and host is not None and task_status != "failed":
                    #     if not worker_bool:
                    #         worker_bool = True
                    #         worker_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                    #         worker_task.state = "success"
                    #         worker_task.detail = TaskService.TaskDetail.scale_join_cluster.value
                    #         update_task_state(worker_task)
                    #         component_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress",
                    #                                   start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                    #                                   msg=TaskService.TaskScaleNodeMessage.scale_install_calico.name)
                    #         TaskSQL.insert(component_task)
                    #         task_info = component_task
            time.sleep(0.01)
            continue
        log_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "ansible_scale.log")
        with open(log_file, "a") as log_file:
            log_file.write(format(runner.stdout.read()))
        thread.join()
        if runner.rc != 0:
            # 更新数据库的状态为failed
            task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "failed"
            task_info.detail = "ansible deploy kubernetes error"
            update_task_state(task_info)
            raise Exception("Deploy kubernetes with sacle node failed, please check log")
        # 这里component_task为None就报错
        worker_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        worker_task.state = "success"
        worker_task.detail = TaskService.TaskDetail.scale_join_cluster.value
        update_task_state(worker_task)
        return True, ""
    except Exception as e:
        print(f"Ansible error: {e}")
        return False, str(e)


def get_cluster_kubeconfig(cluster: ClusterTFVarsObject, lb_ip, master_ip, float_ip,ssh_port):
    """获取集群的kubeconfig配置"""

    print(f"lb_ip: {lb_ip}, master_ip: {master_ip}, float_ip: {float_ip}")
    try:
        kubeconfig = ""
        # SSH连接到master节点获取kubeconfig
        if cluster.password != "":
            result = subprocess.run(
                [
                    "ssh",
                    "-o", "StrictHostKeyChecking=no",
                    "-p", str(ssh_port),
                    f"{cluster.ssh_user}@{float_ip}",
                    "sudo cat /etc/kubernetes/admin.conf"
                ],
                capture_output=True,
                text=True,
                check=True
            )
            kubeconfig = result.stdout
        else:
            key_file_path = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "id_rsa")
            result = subprocess.run(
                [
                    "ssh",
                    "-o", "StrictHostKeyChecking=no",
                    "-i", key_file_path,  # SSH私钥路径
                    "-p", str(ssh_port),
                    f"{cluster.ssh_user}@{float_ip}",
                    "sudo cat /etc/kubernetes/admin.conf"
                    ""
                ],
                capture_output=True,
                text=True,
                check=True
            )
            kubeconfig = result.stdout

        # 替换server地址为外部IP
        ip = "127.0.0.1"
        if lb_ip is not None and lb_ip != "":
            ip = lb_ip
        elif master_ip is not None and master_ip != "":
            ip = master_ip

        kubeconfig = kubeconfig.replace(
            "server: https://127.0.0.1:6443",
            f"server: https://{ip}:6443"
        )
        return kubeconfig

    except subprocess.CalledProcessError as e:
        print(f"Error getting kubeconfig: {e}")
        return None


def delete_vm_instance(conn, instance):
    try:
        # 在这里使用openstack的api接口，直接删除vm或bm
        server = conn.compute.find_server(instance.get("server_id"))
        if server:
            conn.compute.delete_server(server)
            conn.compute.wait_for_delete(server, wait=TIMEOUT)
        return instance.get("id")
    except Exception as e:
        session = get_session()
        with session.begin():
            db_instance = session.get(Instance, instance.get("id"))
            db_instance.status = "error"
            db_instance.status_msg = str(e)
        raise ValueError(e)


def get_user_data(user, password):
    user_data = f"""Content-Type: multipart/mixed; boundary="===============2309984059743762475=="
MIME-Version: 1.0

--===============2309984059743762475==
Content-Type: text/cloud-config; charset="us-ascii"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Content-Disposition: attachment; filename="ssh-pwauth-script.txt"

#cloud-config
disable_root: false
ssh_pwauth: true

--===============2309984059743762475==
Content-Type: text/x-shellscript; charset="us-ascii"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Content-Disposition: attachment; filename="passwd-script.txt"

#!/bin/sh
echo '{user}:{password}' | chpasswd

--===============2309984059743762475==--"""
    return base64.b64encode(user_data.encode("utf-8")).decode()


def create_ssh_keypair(conn, key_name=SSH_KEY_NAME):
    # 检查密钥对是否已存在
    existing_keypair = conn.compute.find_keypair(key_name)
    if not existing_keypair:
        # 未找到密钥时触发创建流程
        keypair = conn.compute.create_keypair(name=key_name)

        # 保存私钥到本地文件（权限自动设置为 600）
        with open(f"{key_name}.pem", "w") as f:
            f.write(keypair.private_key)
            import os
            os.chmod(f"{key_name}.pem", 0o600)
        with open(f"{key_name}.pem", "r") as f:
            content = f.read()

        return keypair.name, content
    else:
        with open(f"{key_name}.pem", "r") as f:
            content = f.read()
        return existing_keypair.name, content


def create_network_id(conn, network_name=INSTANCE_NET_NAME):
    existing_network = conn.network.find_network(network_name)
    if not existing_network:
        network = conn.network.create_network(
            name=network_name,
            is_router_external=False,  # 内部网络
            shared=False                # 仅限当前项目使用
        )
        return network
    else:
        return existing_network


def create_router_id(conn, external_net_id, subnet_id, router_name=INSTANCE_ROUTER_NAME):
    existing_router = conn.network.find_router(router_name)
    if not existing_router:
        router = conn.network.create_router(
            name=router_name,
            **{"external_gateway_info": {"network_id": external_net_id}},
        )
        router.add_interface(conn.network, subnet_id=subnet_id)


def get_subnet_info():
    # 生成随机CIDR（格式：10.x.x.0/16）
    cidr = f"10.{random.randint(150, 200)}.0.0/16"
    # 解析CIDR并获取网络对象
    network = ipaddress.ip_network(cidr, strict=False)
    # 计算第一个可用IP（网络地址+1）
    first_ip = network.network_address + 1
    second_ip = network.network_address + 2
    last_ip = network.broadcast_address - 1
    return cidr, str(first_ip), str(second_ip), str(last_ip)


def create_subnet_id(conn, network, subnet_name=INSTANCE_SUBNET_NAME):
    existing_subnet = conn.network.find_subnet(subnet_name)
    if not existing_subnet:
        cidr, first_ip, second_ip, last_ip = get_subnet_info()
        subnet = conn.network.create_subnet(
            name=subnet_name,
            network_id=network.id,
            ip_version=4,
            cidr=cidr,
            gateway_ip=first_ip,
            allocation_pools=[{"start": second_ip, "end": last_ip}],
            dns_nameservers=["114.114.114.114", "8.8.8.8"],
            enable_dhcp=True
        )
        return subnet
    else:
        return existing_subnet


def create_vm_instance(conn, instance_info: InstanceCreateObject, instance_list):
    server_list = []
    # 在这里使用openstack的api接口，直接创建vm
    nclient = NovaClient(token=instance_info.openstack_info.token)
    if instance_info.user and instance_info.password:
        user_data = get_user_data(instance_info.user, instance_info.password)
        for ins in instance_list:
            # server = conn.create_server(
            #     name=ins.get("name"),
            #     image=instance_info.image_id,
            #     flavor=instance_info.flavor_id,
            #     network=instance_info.network_id,
            #     userdata=user_data,
            #     security_groups=instance_info.security_group,
            #     wait=False
            # )
            server = nclient.nova_create_server(ins.get("name"), instance_info.image_id, instance_info.flavor_id,
                                                instance_info.network_id, user_data=user_data)
            server_list.append(server.get("id"))
    else:
        for ins in instance_list:
            # server = conn.create_server(
            #     name=ins.get("name"),
            #     image=instance_info.image_id,
            #     flavor=instance_info.flavor_id,
            #     network=instance_info.network_id,
            #     key_name=instance_info.sshkey_name,
            #     security_groups=instance_info.security_group,
            #     wait=False
            # )
            server = nclient.nova_create_server(ins.get("name"), instance_info.image_id,
                                                instance_info.flavor_id, instance_info.network_id,
                                                key_name=instance_info.sshkey_name)
            server_list.append(server.get("id"))
    return server_list


def create_bm_instance(conn, instance_info: InstanceCreateObject, instance_list):
    server_list = []
    nclient = NovaClient(token=instance_info.openstack_info.token)
    meta_data = {
        "baremetal": "true",
        "capabilities": "boot_option:local"
    }
    # 在这里使用openstack的api接口，直接创建vm
    if instance_info.user and instance_info.password:
        # 在这里使用openstack的api接口，直接创建bm
        user_data = get_user_data(instance_info.user, instance_info.password)
        for ins in instance_list:
            # server = conn.create_server(
            #     name=ins.get("name"),
            #     image=instance_info.image_id,
            #     flavor=instance_info.flavor_id,
            #     network=instance_info.network_id,
            #     userdata=user_data,
            #     security_groups=instance_info.security_group,
            #     config_drive=True,
            #     meta={
            #         "baremetal": "true",
            #         "capabilities": "boot_option:local"
            #     },
            #     wait=False
            # )
            server = nclient.nova_create_server(ins.get("name"), instance_info.image_id,
                                                instance_info.flavor_id, instance_info.network_id,
                                                user_data=user_data, config_drive=True, metadata=meta_data)
            server_list.append(server.get("id"))
    else:
        for ins in instance_list:
            # server = conn.create_server(
            #     name=ins.get("name"),
            #     image=instance_info.image_id,
            #     flavor=instance_info.flavor_id,
            #     network=instance_info.network_id,
            #     key_name=instance_info.sshkey_name,
            #     security_groups=instance_info.security_group,
            #     config_drive=True,
            #     meta={
            #         "baremetal": "true",
            #         "capabilities": "boot_option:local"
            #     },
            #     wait=False
            # )
            server = nclient.nova_create_server(ins.get("name"), instance_info.image_id,
                                                instance_info.flavor_id, instance_info.network_id,
                                                key_name=instance_info.sshkey_name, config_drive=True,
                                                metadata=meta_data)
            server_list.append(server.get("id"))
    return server_list

def check_nodes_connectivity(host_file, key_file_path):
    """检查所有节点的连通性并返回详细结果"""
    res={}
    if key_file_path != "":   
        res = subprocess.run([
            "ansible",
            "-i", host_file,
            "-m", "ping",
            "all",
            "--ssh-common-args=\"-o StrictHostKeyChecking=no\"",
            "--private-key", key_file_path,
            "-o", # 使用简单输出格式
        ], capture_output=True, text=True)
    else:
        res = subprocess.run([
            "ansible",
            "-i", host_file,
            "-m", "ping",
            "all",
            "-o", # 使用简单输出格式
        ], capture_output=True, text=True)
    
    # 初始化结果
    result = {
        "success": res.returncode == 0,
        "all_nodes_reachable": True,
        "unreachable_nodes": [],
        "output": res.stdout,
        "error": res.stderr
    }
    
    for line in res.stdout.splitlines() + res.stderr.splitlines():
        if "UNREACHABLE!" in line or "FAILED!" in line:
            node_name = line.split()[0].rstrip(":")
            result["unreachable_nodes"].append(node_name)
            result["all_nodes_reachable"] = False
    
    return result

def remove_bastion_fip_from_state(cluster_dir):
    """
    检查并从 Terraform state 中移除 bastion_fip 资源
    
    参数:
        cluster_dir: 集群目录路径
    
    返回:
        bool: 操作是否成功
    """
    terraform_dir = os.path.join(cluster_dir, "terraform")
    os.chdir(terraform_dir)
    
    try:
        # 执行 terraform state list 获取所有资源
        result = subprocess.run(
            ["terraform", "state", "list"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        
        state_resources = result.stdout.strip().split('\n')
        target_resource = "module.ips.openstack_networking_floatingip_v2.bastion_fip[0]"
        
        # 检查目标资源是否存在
        if target_resource in state_resources:
            print(f"找到资源 {target_resource}，正在从 state 中移除...")
            
            # 执行 terraform state rm 移除资源
            remove_result = subprocess.run(
                ["terraform", "state", "rm", target_resource],
                capture_output=True,
                text=True,
                check=True
            )
            
            print(f"rm bastion_fip from terraform state ")
            return True

        elif "module.network.openstack_networking_router_v2.cluster[0]" in state_resources:
            # 执行 terraform state rm 移除资源
            remove_result = subprocess.run(
                ["terraform", "state", "rm", "module.network.openstack_networking_router_v2.cluster[0]"],
                capture_output=True,
                text=True,
                check=True
            )
            print(f"rm cluster_router from terraform state ")
            return True
        else:
            print(f"resource {target_resource} not exist in state ")
            return True
            
    except subprocess.CalledProcessError as e:
        print(f"操作失败: {e.stderr}")
        return False

def update_task_info(task_id, cluster_id, cluster_name, node_count=None):
    session = get_session()
    with session.begin():
        db_cluster = session.get(Cluster, (cluster_id, cluster_name))
        if not db_cluster.extra:
            extra_dict = {}
        else:
            extra_dict = json.loads(db_cluster.extra)
        extra_dict["task_id"] = task_id
        if node_count:
            extra_dict["node_count"] = int(extra_dict.get("node_count", 0)) + int(node_count)
        db_cluster.extra = json.dumps(extra_dict)

def update_cluster_node_count(node_count, db_cluster):
    if not db_cluster.extra:
        extra_dict = {}
    else:
        extra_dict = json.loads(db_cluster.extra)
    extra_dict["node_count"] = int(extra_dict.get("node_count", 0)) + int(node_count)
    db_cluster.extra = json.dumps(extra_dict)

@celery_app.task(bind=True,time_limit=TASK_TIMEOUT, soft_time_limit=SOFT_TASK_TIMEOUT)
def create_k8s_cluster(self, cluster_tf_dict, cluster_dict, node_list, instance_list, scale_nodes=None, scale=False):
    try:
        task_id = self.request.id.__str__()
        if scale:
            update_task_info(task_id, cluster_dict.get("id"), cluster_dict.get("name"), len(scale_nodes.split(",")))
        print(f"tf: {cluster_tf_dict},cluster_dict: {cluster_dict}")
        print(f"Task ID: {task_id}")
        cluster_tfvars = ClusterTFVarsObject(**cluster_tf_dict)
        cluster = ClusterObject(**cluster_dict)
        node_list = json.loads(node_list)
        instance_list = json.loads(instance_list)
        if not scale:
            # 将task_info存入数据库
            task_info = Taskinfo(task_id=task_id, cluster_id=cluster_tf_dict["id"], state="progress",
                                 start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                 msg=TaskService.TaskMessage.instructure_create.name)
            TaskSQL.insert(task_info)
        else:
            task_info = Taskinfo(task_id=task_id, cluster_id=cluster_tf_dict["id"], state="progress",
                                 start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                 msg=TaskService.TaskScaleNodeMessage.scale_instructure.name)
            TaskSQL.insert(task_info)

        cinder_client = CinderClient()
        volume_type = cinder_client.list_volum_type()
        cluster_tfvars.etcd_volume_type = volume_type
        cluster_tfvars.pushgateway_url = PUSHGATEWAY_URL
        terraform_result = create_infrastructure(cluster_tfvars, task_info, scale=scale,
                                                 node_list=node_list, node_type=NodeInfo, instance_list=instance_list)

        if not terraform_result[0]:
            raise Exception(f"Terraform infrastructure creation failed, reason: {terraform_result[1]}")
        # 打印日志
        print("Terraform infrastructure creation succeeded")
        # 将bastion_ip从terraform state中去除
        # 从 terraform state 中移除 bastion_fip 资源
        cluster_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", cluster_tf_dict["id"])
        remove_bastion_fip_from_state(cluster_dir)

        # 根据生成inventory
        # 复制script下面的host文件到WORK_DIR/cluster.id目录下
        # 执行python3 host --list，将生成的内容转换为yaml格式写入到inventory/inventory.yaml文件中
        if not scale:
            # 将task_info存入数据库
            task_info = Taskinfo(task_id=task_id, cluster_id=cluster_tf_dict["id"], state="progress",
                                 start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                 msg=TaskService.TaskMessage.pre_install.name)
            TaskSQL.insert(task_info)
        else:
            task_info = Taskinfo(task_id=task_id, cluster_id=cluster_tf_dict["id"], state="progress",
                                 start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                 msg=TaskService.TaskScaleNodeMessage.scale_pre_install.name)
            TaskSQL.insert(task_info)
        # Give execute permissions to the host file
        host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", cluster_tf_dict["id"], "hosts")
        os.chmod(host_file, 0o755)  # rwxr-xr-x permission
        master_ip, lb_ip, hosts_data = get_ips(cluster_tfvars, task_info, host_file, cluster_dir, scale)
        # ensure /root/.ssh/known_hosts exists
        if os.path.exists("/root/.ssh/known_hosts"):
            for i in range(1, cluster_tfvars.number_of_k8s_masters + 1):
                print(f"delete host from know_hosts  {task_id}")
                master_node_name = f"{cluster_tfvars.cluster_name}-k8s-master-{i}"
                tmp_ip = hosts_data["_meta"]["hostvars"][master_node_name]["ansible_host"]
                cmd = f'ssh-keygen -f "/root/.ssh/known_hosts" -R "{tmp_ip}"'
                result = subprocess.run(cmd, shell=True, capture_output=True)
                if result.returncode != 0:
                    task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                    task_info.state = "failed"
                    task_info.detail = "Ansible kubernetes deployment failed, configure ssh-keygen error"
                    update_task_state(task_info)
                    raise Exception("Ansible kubernetes deployment failed, configure ssh-keygen error")
        if cluster_tfvars.password != "":
            master_node_name = f"{cluster_tfvars.cluster_name}-k8s-master-1"
            ssh_port = hosts_data["_meta"]["hostvars"][master_node_name].get("ansible_port", 22)
            cmd = (f'sshpass -p "{cluster_tfvars.password}" ssh-copy-id -o StrictHostKeyChecking=no -p {ssh_port} '
                   f'{cluster_tfvars.ssh_user}@{master_ip}')
            retry_count = 0
            max_retries = 30
            while retry_count < max_retries:
                result = subprocess.run(cmd, shell=True, capture_output=True)
                if result.returncode == 0:
                    break
                else:
                    retry_count += 1
                    if retry_count < max_retries:
                        print(f"sshpass failed, retry {retry_count}/{max_retries} after 5s...")
                        time.sleep(5)
            if result.returncode != 0:
                task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                task_info.state = "failed"
                task_info.detail = "Ansible kubernetes deployment failed, configure sshpass error"
                update_task_state(task_info)
                print(f"sshpass failed after {max_retries} retries: {result.stderr}")
                raise Exception("Ansible kubernetes deployment failed, configure sshpass error")

        # 执行ansible命令验证是否能够连接到所有节点
        print(f"check all node status {task_id}")
        ansible_dir = os.path.join(WORK_DIR, "ansible-deploy")
        os.chdir(ansible_dir)
        key_file_path = ""
        if cluster_tfvars.password == "":
            key_file_path = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "id_rsa")
        # 添加重试逻辑
        start_time = time.time()
        max_retry_time = 600  # 10分钟超时
        retry_interval = 5    # 5秒重试间隔
        connection_success = False

        output_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory",
                                   str(cluster.id), "terraform", "output.tfvars.json")
        with open(output_file) as f:
            content = json.loads(f.read())
        # 更新集群node的状态为running
        session = get_session()
        with session.begin():
            for node in node_list:
                db_node = session.get(NodeInfo, node.get("id"))
                for k, v in hosts_data["_meta"]["hostvars"].items():
                    if db_node.name == k:
                        db_node.server_id = v.get("id")
                        db_node.status = "running"
                        db_node.cidr = content.get("subnet_cidr")
                        db_node.security_group = cluster.name
                        db_node.admin_address = v.get("ip")
                        break

        # 更新集群instance的状态为running
        with session.begin():
            for instance in instance_list:
                db_instance = session.get(Instance, instance.get("id"))
                for k, v in hosts_data["_meta"]["hostvars"].items():
                    # 需要添加节点的ip地址等信息
                    if db_instance.name == k:
                        db_instance.server_id = v.get("id")
                        db_instance.status = "running"
                        db_instance.cidr = content.get("subnet_cidr")
                        db_instance.security_group = cluster.name
                        db_instance.ip_address = v.get("ip")
                        break

        while not connection_success and (time.time() - start_time) < max_retry_time:
            nodes_result = check_nodes_connectivity(host_file, key_file_path)
            
            if nodes_result["all_nodes_reachable"]:
                connection_success = True
                print(f"all node connect sussess {task_id}")    
                break
            else:
                unreachable_nodes = ", ".join(nodes_result["unreachable_nodes"])
                print(f"some node can not connect: {unreachable_nodes}，{retry_interval}s after retry...")
                # 记录日志，显示哪些节点不可达
                with open(os.path.join(WORK_DIR, "ansible-deploy", "inventory", cluster_tf_dict["id"], "connection_check.log"), "a") as log_file:
                    log_file.write(f"{datetime.now()}: unreachable nodes: {unreachable_nodes}\n")
                    log_file.write(f"错误输出: {nodes_result['error']}\n\n")
                
                time.sleep(retry_interval)

        # 如果超时后仍然无法连接所有节点，则抛出错误
        if not connection_success:
            error_msg = f"{int(time.time() - start_time)}s retry node can not connect: {', '.join(nodes_result['unreachable_nodes'])}"
            task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "failed"
            task_info.detail = error_msg
            update_task_state(task_info)
            raise Exception(error_msg)

        res = subprocess.run(["python3", host_file, "--root",cluster_dir,"--list"], capture_output=True, text=True)
        if res.returncode != 0:
            # 更新数据库的状态为failed
            task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "failed"
            task_info.detail = str(res.stderr)
            update_task_state(task_info)
            raise Exception(f"Error generating Ansible inventory: {str(res.stderr)}")
        hosts = res.stdout
        hosts_data = json.loads(hosts)
        # 从_meta.hostvars中获取master节点的IP
        master_node_name = cluster_tfvars.cluster_name + "-k8s-master-1"
        master_ip = hosts_data["_meta"]["hostvars"][master_node_name]["ip"]
        float_ip = hosts_data["_meta"]["hostvars"][master_node_name]["ansible_host"]
        ssh_port = hosts_data["_meta"]["hostvars"][master_node_name].get("ansible_port", 22)
        task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        task_info.state = "success"
        task_info.detail = TaskService.TaskDetail.pre_install.value
        update_task_state(task_info)

        # 2. 使用Ansible部署K8s集群
        cluster.id = cluster_tf_dict["id"]
        if scale:
            ansible_result = scale_kubernetes(cluster, scale_nodes, task_id)
        else:
            ansible_result = deploy_kubernetes(cluster, lb_ip, task_id)
        if not ansible_result[0]:
            raise Exception(f"Ansible kubernetes deployment failed: {ansible_result[1]}")
        # 阻塞线程，直到ansible_client.get_playbook_result()返回结果
        # 获取集群的kube_config
        kube_config = get_cluster_kubeconfig(cluster_tfvars,lb_ip,master_ip,float_ip,ssh_port)
        # 更新集群状态为running
        query_params = {}
        query_params["id"] = cluster_dict["id"]
        count, db_clusters = ClusterSQL.list_cluster(query_params)
        c = db_clusters[0]
        kube_info = json.loads(c.kube_info)
        kube_info["kube_config"] = kube_config
        kube_info["kube_lb_address"] = lb_ip
        c.kube_info = json.dumps(kube_info)
        c.status = 'running'
        if scale:
            cpu_total, gpu_total, mem_total = get_node_info(node_list)
            c.cpu += cpu_total
            c.gpu += gpu_total
            c.mem += mem_total
        else:
            update_cluster_node_count(len([node for node in node_list if node.get("role") != "master"]), c)
        c.status_msg = ""
        ClusterSQL.update_cluster(c)

    except SoftTimeLimitExceeded:
        query_params = {}
        query_params["id"] = cluster_dict["id"]
        count, db_clusters = ClusterSQL.list_cluster(query_params)
        c = db_clusters[0]
        if scale:
            c.status = 'scale_error'
            c.status_msg = "The scale k8s_cluster task has timed out."
        else:
            c.status = 'error'
            c.status_msg = "The create_k8s_cluster task has timed out."
        ClusterSQL.update_cluster(c)
        raise
    except Exception as e:
        # 发生错误时更新集群状态为"失败"
        print(f"deploy k8s cluster error")
        query_params = {}
        query_params["id"] = cluster_dict["id"]
        count, db_clusters = ClusterSQL.list_cluster(query_params)
        c = db_clusters[0]
        if scale:
            c.status = 'scale_error'
        else:
            c.status = 'error'
        c.status_msg = replace_ansi_with_single_newline(str(e))
        ClusterSQL.update_cluster(c)
        raise


def get_ips(cluster_tfvars, task_info, host_file, cluster_dir, scale):
    res = subprocess.run(["python3", host_file, "--root", cluster_dir, "--list"], capture_output=True, text=True)
    if res.returncode != 0:
        # 更新数据库的状态为failed
        task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        task_info.state = "failed"
        task_info.detail = str(res.stderr)
        update_task_state(task_info)
        raise Exception("Error generating Ansible inventory")
    hosts = res.stdout
    hosts_data = json.loads(hosts)
    # 从_meta.hostvars中获取master节点的IP
    master_node_name = cluster_tfvars.cluster_name + "-k8s-master-1"
    master_ip = hosts_data["_meta"]["hostvars"][master_node_name]["ansible_host"]
    lb_ip = hosts_data["_meta"]["hostvars"][master_node_name]["lb_ip"]
    return master_ip, lb_ip, hosts_data


def get_networks(cluster_tfvars, task_info, host_file, cluster_dir):
    res = subprocess.run(["python3", host_file,  "--root", cluster_dir,"--list"], capture_output=True, text=True)
    if res.returncode != 0:
        # 更新数据库的状态为failed
        task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        task_info.state = "failed"
        task_info.detail = str(res.stderr)
        update_task_state(task_info)
        raise Exception("Error generating Ansible inventory")
    hosts = res.stdout
    hosts_data = json.loads(hosts)
    # 从_meta.hostvars中获取master节点的IP
    node_name = cluster_tfvars.cluster_name + "-k8s-master-1"
    if cluster_tfvars.number_of_k8s_masters == 0:
        node_name = cluster_tfvars.cluster_name + "-node-1"
    
    bus_network_id = ""
    bus_network_name = ""
    network_id = hosts_data["_meta"]["hostvars"][node_name]["network"][0]['uuid']
    network_name = hosts_data["_meta"]["hostvars"][node_name]["network"][0]['name']
    if len(hosts_data["_meta"]["hostvars"][node_name]["network"]) > 1:
        bus_network_id = hosts_data["_meta"]["hostvars"][node_name]["network"][1]['uuid']
        bus_network_name = hosts_data["_meta"]["hostvars"][node_name]["network"][1]['name']
    subnet_id = hosts_data["_meta"]["hostvars"][node_name]["subnet_id"]
    bussubnet_id = hosts_data["_meta"]["hostvars"][node_name]["bussubnet_id"]
    return network_id, network_name, bus_network_id, bus_network_name, subnet_id, bussubnet_id

def load_tfvars_to_object(tfvars_path):
    """
    从 output.tfvars.json 文件加载内容并转换为 ClusterTFVarsObject 对象
    
    Args:
        tfvars_path: output.tfvars.json 文件路径
        
    Returns:
        ClusterTFVarsObject 对象
    """
    # 读取 tfvars 文件
    with open(tfvars_path, 'r') as f:
        tfvars_data = json.load(f)
    
    # 将 JSON 数据直接传递给 Pydantic 模型构造函数
    # Pydantic 会自动处理数据类型转换和验证
    cluster_tfvars = ClusterTFVarsObject(**tfvars_data)
    
    return cluster_tfvars


def update_cluster_status(cluster_id):
    # 更新任务状态为"成功"
    query_params = {}
    query_params["id"] = cluster_id
    count, db_clusters = ClusterSQL.list_cluster(query_params)
    c = db_clusters[0]
    c.status = 'deleted'
    c.status_msg = ""
    ClusterSQL.update_cluster(c)
    print("Terraform destroy succeeded")
    # delete instance
    # 1. 查询与该集群关联的所有实例
    query_params = {"cluster_id": cluster_id}
    count, instances = InstanceSQL.list_instances(query_params, 1, -1, None, None)
    session = get_session()
    with session.begin():
        for instance in instances:
            db_instance = session.get(Instance, instance.id)
            session.delete(db_instance)
    # 1. 查询与该集群关联的所有实例
    query_params = {"cluster_id": cluster_id}
    count, nodes = NodeSQL.list_nodes(query_params, 1, -1, None, None)
    with session.begin():
        for n in nodes:
            db_node = session.get(NodeInfo, n.id)
            session.delete(db_node)


@celery_app.task(bind=True)
def delete_cluster(self, cluster_id, token):
    try:
        task_id = str(self.request.id)
        task_info = Taskinfo(task_id=task_id, cluster_id=cluster_id, state="progress",
                             start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                             msg=TaskService.TaskDeleteMessage.delete_instructure.name)
        TaskSQL.insert(task_info)
        cluster_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", cluster_id)
        terraform_dir = os.path.join(cluster_dir, "terraform")
        # 进入到terraform目录、
        if not os.path.exists(cluster_dir) or not os.path.exists(terraform_dir):
            print(f"集群目录不存在: {cluster_dir}")
            # 更新集群状态为已删除，因为目录不存在意味着可能已被删除或从未创建成功
            query_params = {}
            query_params["id"] = cluster_id
            count, db_clusters = ClusterSQL.list_cluster(query_params)
            if count > 0:
                c = db_clusters[0]
                c.status = 'deleted'
                c.status_msg = ""
                ClusterSQL.update_cluster(c)
            query_params = {"cluster_id": cluster_id}
            count, instances = InstanceSQL.list_instances(query_params, 1, -1, None, None)
            for instance in instances:
                session = get_session()
                with session.begin():
                    db_instance = session.get(Instance, instance.id)
                    session.delete(db_instance)

            # 1. 查询与该集群关联的所有实例
            query_params = {"cluster_id": cluster_id}
            count, nodes = NodeSQL.list_nodes(query_params, 1, -1, None, None)
            for n in nodes:
                session = get_session()
                with session.begin():
                    db_node = session.get(NodeInfo, n.id)
                    session.delete(db_node)
            task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "success"
            task_info.detail = "delete cluster successfully"
            update_task_state(task_info)
            return True

        terraform_dir = os.path.join(cluster_dir, "terraform")
        print(f"Terraform dir: {terraform_dir}")

        os.chdir(terraform_dir)
        # 加载为 ClusterTFVarsObject 对象
        
        tfvars_path = os.path.join(WORK_DIR, "ansible-deploy", "inventory", cluster_id, "terraform", "output.tfvars.json")
        cluster_tfvars = load_tfvars_to_object(tfvars_path)
        cluster_tfvars.token = token
        tfvars_str = json.dumps(cluster_tfvars, default=lambda o: o.__dict__, indent=2)
        with open("output.tfvars.json", "w") as f:
            f.write(tfvars_str)
        # 获取 tfvars 文件路径
        res = subprocess.run(["terraform", "init"], capture_output=True, text=True)
        if res.returncode != 0:
            # 发生错误时更新任务状态为"失败"
            print(f"Terraform error: {res.stderr}")
            task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "failed"
            task_info.detail = f"delete cluster, reason: {replace_ansi_with_single_newline(res.stderr)}"
            update_task_state(task_info)
            raise Exception("delete cluster Error terraform init exception: {}".format(res.stderr))

        env = os.environ.copy()
        env["TF_LOG"] = "DEBUG"
        resource_inuse = False
        # 创建子进程并实时捕获输出
        process = subprocess.Popen(
            ["terraform", "destroy", "-auto-approve", "-var-file=output.tfvars.json", "-lock=false"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env
        )
        # 实时读取输出流
        try:
            for line in process.stdout:
                if "type" in line and "SecurityGroupInUse" in line:
                    resource_inuse = True
                    print("type with SecurityGroupInUse")
                    process.terminate()
                    break
                if "type" in line and "SubnetInUse" in line:
                    resource_inuse = True
                    print("type with SubnetInUse")
                    process.terminate()
                    break
                if "type" in line and "NetworkInUse" in line:
                    resource_inuse = True
                    print("type with NetworkInUse")
                    process.terminate()
                    break
        finally:
            # 确保回收资源
            process.wait(timeout=60)
            if process.returncode is None:
                process.kill()
            print(f"进程已终止，退出码: {process.returncode}")
        if process.returncode != 0:
            # 发生错误时更新任务状态为"失败"
            if resource_inuse:
                update_cluster_status(cluster_id)
                task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                task_info.state = "success"
                task_info.detail = "delete cluster successfully"
                update_task_state(task_info)
                return True
            else:
                print(f"Terraform error: {process.stderr}")
                task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                task_info.state = "failed"
                task_info.detail = f"delete cluster, reason: {replace_ansi_with_single_newline(process.stderr)}"
                update_task_state(task_info)
                # 在这里判断具体的日志输出信息，如果出现删除安全组超时就判断为删除成功
                raise Exception("delete cluster Error terraform destroy exception: {}".format(process.stderr))
        else:
            task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "success"
            task_info.detail = "delete cluster successfully"
            update_task_state(task_info)
            update_cluster_status(cluster_id)
            return True
    except Exception as e:
        query_params = {}
        query_params["id"] = cluster_id
        count, db_clusters = ClusterSQL.list_cluster(query_params)
        c = db_clusters[0]
        c.status = 'delete_error'
        c.status_msg = f"delete cluster error: {replace_ansi_with_single_newline(str(e))}"
        ClusterSQL.update_cluster(c)
        return False
                

@celery_app.task(bind=True)
def delete_node(self, cluster_id, cluster_name, node_list, instance_list, extravars):
    try:
        task_id = str(self.request.id)
        update_task_info(task_id, cluster_id, cluster_name)
        runtime_task = Taskinfo(task_id=task_id, cluster_id=cluster_id, state="progress",
                                start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                msg=TaskService.TaskRemoveNodeMessage.remove_pre_install.name)
        TaskSQL.insert(runtime_task)
        task_info = runtime_task
        etcd_task = Taskinfo()
        control_plane_task = Taskinfo()
        worker_task = Taskinfo()
        component_task = Taskinfo()
        node_list = json.loads(node_list)
        instance_list = json.loads(instance_list)
        extravars["skip_confirmation"] = "true"
        cluster_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id))
        os.environ['CURRENT_CLUSTER_DIR'] = cluster_dir
        # os.environ['OS_CLOUD'] = node.get("region_name")
        # 1、在这里先找到cluster的文件夹，找到对应的目录，先通过发来的node_list组合成extravars的变量，再执行remove-node.yaml
        ansible_dir = os.path.join(WORK_DIR, "ansible-deploy")
        os.chdir(ansible_dir)
        host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id))
        playbook_file = os.path.join(WORK_DIR, "ansible-deploy", "remove-node.yml")
        key_file_path = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id), "id_rsa")
        private_key_content = ""
        if os.path.exists(key_file_path):
            with open(key_file_path, 'r') as key_file:
                private_key_content = key_file.read()
        thread, runner = run_playbook(playbook_file, host_file, ansible_dir,
                                      ssh_key=private_key_content, extravars=extravars)
        # 处理并打印事件日志
        runtime_bool = False
        etcd_bool = False
        controller_bool = False
        worker_bool = False
        while runner.status not in ['canceled', 'successful', 'timeout', 'failed']:
            for event in runner.events:
                # 检查事件是否包含 task 信息
                if 'event_data' in event and 'task' in event['event_data']:
                    task_name = event['event_data'].get('task')
                    host = event['event_data'].get('host')
                    task_status = event['event'].split('_')[-1]  # 例如 runner_on_ok -> ok
                    #print(f"任务 {task_name} 在主机 {host} 上 Status: {event['event']}")
                    if task_name == remove_from_cluster and host is not None:
                        if not runtime_bool:
                            runtime_bool = True
                            runtime_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                            runtime_task.state = "success"
                            runtime_task.detail = TaskService.TaskDetail.remove_pre_install.value
                            update_task_state(runtime_task)
                            # 写入下一个任务
                            etcd_task = Taskinfo(task_id=task_id, cluster_id=cluster_id, state="progress",
                                                 start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                                 msg=TaskService.TaskRemoveNodeMessage.remove_from_cluster.name)
                            TaskSQL.insert(etcd_task)
                            task_info = etcd_task
                    if task_name == remove_cri_pods and host is not None:
                        if not etcd_bool:
                            etcd_bool = True
                            etcd_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                            etcd_task.state = "success"
                            etcd_task.detail = TaskService.TaskDetail.remove_from_cluster.value
                            update_task_state(etcd_task)
                            # 写入下一个任务
                            control_plane_task = Taskinfo(task_id=task_id, cluster_id=cluster_id, state="progress",
                                                          start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                                          msg=TaskService.TaskRemoveNodeMessage.remove_cri_pods.name)
                            TaskSQL.insert(control_plane_task)
                            task_info = control_plane_task
                    if task_name == remove_iptables and host is not None:
                        if not controller_bool:
                            controller_bool = True
                            control_plane_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                            control_plane_task.state = "success"
                            control_plane_task.detail = TaskService.TaskDetail.remove_cri_pods.value
                            update_task_state(control_plane_task)
                            # 写入下一个任务
                            worker_task = Taskinfo(task_id=task_id, cluster_id=cluster_id, state="progress",
                                                   start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                                   msg=TaskService.TaskRemoveNodeMessage.remove_iptables.name)
                            TaskSQL.insert(worker_task)
                            task_info = worker_task
                    if task_name == remove_file_dirs and host is not None and task_status != "failed":
                        if not worker_bool:
                            worker_bool = True
                            worker_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                            worker_task.state = "success"
                            worker_task.detail = TaskService.TaskDetail.remove_iptables.value
                            update_task_state(worker_task)
                            component_task = Taskinfo(task_id=task_id, cluster_id=cluster_id, state="progress",
                                                      start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                                      msg=TaskService.TaskRemoveNodeMessage.remove_file_dirs.name)
                            TaskSQL.insert(component_task)
                            task_info = component_task

            time.sleep(0.01)
            continue
        log_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id), "ansible_remove.log")
        with open(log_file, "a") as log_file:
            log_file.write(format(runner.stdout.read()))
        thread.join()
        if runner.rc != 0:
            # print("{}".format(runner.stdout.read()))
            task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "failed"
            task_info.detail = "Ansible remove node failed, please check log"
            update_task_state(task_info)
            raise Exception(f"Ansible remove node failed, please check log")

        # # 2、执行完删除k8s这些节点之后，再执行terraform销毁这些节点（这里是单独修改output.json文件还是需要通过之前生成的output.json文件生成）
        # 在这里添加需要排除重新创建的虚拟机，从output文件里面取得nodes再和数据库里面的nodes做比较，数据里面没有的就在state删除
        remove_node_list = extravars.get("node").split(",")
        remove_list = []
        for remove_node in remove_node_list:
            remove_list.append(remove_node.split(cluster_name + "-")[1])
        terraform_dir = os.path.join(cluster_dir, "terraform")
        os.chdir(terraform_dir)
        state_remove(remove_list)
        with open("output.tfvars.json") as f:
            content = json.loads(f.read())
            content_new = copy.deepcopy(content)
            for node in content["nodes"]:
                if node in remove_list:
                    del content_new["nodes"][node]
        with open("output.tfvars.json", "w") as f:
            json.dump(content_new, f, indent=4)

        # output_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id),
        #                            "terraform", "output.tfvars.json")
        # with open(output_file) as f:
        #     content = json.loads(f.read())
        #     content_new = copy.deepcopy(content)
        #     for node in content["k8s_nodes"]:
        #         if node in extravars.keys():
        #             del content_new["k8s_nodes"][node]
        # with open(output_file, "w") as f:
        #     json.dump(content_new, f, indent=4)
        #
        # # 执行terraform apply
        # cluster_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id))
        # os.environ['CURRENT_CLUSTER_DIR'] = cluster_dir
        # terraform_dir = os.path.join(cluster_dir, "terraform")
        # os.chdir(terraform_dir)
        # # os.environ['OS_CLOUD']=cluster.region_name
        # os.environ['OS_CLOUD'] = "dingzhi"
        # res = subprocess.run([
        #     "terraform",
        #     "apply",
        #     "-auto-approve",
        #     "-var-file=output.tfvars.json"
        # ], capture_output=True, text=True)

        # 3、然后需要更新node节点的数据库的信息和集群的数据库信息
        # 更新集群cluster的状态为running，删除缩容节点的数据库信息
        component_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        component_task.state = "success"
        component_task.detail = TaskService.TaskDetail.remove_file_dirs.value
        update_task_state(task_info)
        session = get_session()
        with session.begin():
            for node in node_list:
                # 根据 node.id 删除节点
                node = session.get(NodeInfo, node.get("id"))
                if node:
                    session.delete(node)
            for instance in instance_list:
                # 根据 instance.id 更新实例
                instance = session.get(Instance, instance.get("id"))
                instance.status = "running"
                instance.cluster_id = ""
                instance.cluster_name = ""
        with session.begin():
            db_cluster = session.get(Cluster, (cluster_id, cluster_name))
            cpu_total, gpu_total, mem_total = get_node_info(node_list)
            db_cluster.cpu -= cpu_total
            db_cluster.gpu -= gpu_total
            db_cluster.mem -= mem_total
            query_params = {"cluster_id": cluster_id}
            count, nodes = NodeSQL.list_nodes(query_params, 1, -1, None, None)
            for node in nodes:
                if node.status != "running":
                    return
            db_cluster.status = 'running'
            db_cluster.status_msg = ''
    except Exception as e:
        print(f"Ansible error: {e}")
        session = get_session()
        with session.begin():
            db_cluster = session.get(Cluster, (cluster_id, cluster_name))
            db_cluster.status = 'remove_error'
            db_cluster.status_msg = f"Ansible remove node error: {str(e)}"

@celery_app.task(bind=True)
def delete_baremetal(self, cluster_id, cluster_name, instance_list, token):
    try:
        task_id = str(self.request.id)
        update_task_info(task_id, cluster_id, cluster_name)
        task_info = Taskinfo(task_id=task_id, cluster_id=cluster_id, state="progress",
                             start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                             msg=TaskService.TaskRemoveBaremetalMessage.remove_instructure.name)
        TaskSQL.insert(task_info)
        instance_list = json.loads(instance_list)
        # 执行terraform销毁这些节点（这里需要通过之前生成的output.json文件生成）
        output_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id),
                                   "terraform", "output.tfvars.json")
        node_name_list = []
        for instance in instance_list:
            node_name_list.append(instance.get("name")[len(cluster_name) + 1:])
        with open(output_file) as f:
            content = json.loads(f.read())
            content_new = copy.deepcopy(content)
            for node in content["nodes"]:
                if node in node_name_list:
                    del content_new["nodes"][node]
        content_new["token"] = token
        with open(output_file, "w") as f:
            json.dump(content_new, f, indent=4)

        # 执行terraform apply
        cluster_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id))
        os.environ['CURRENT_CLUSTER_DIR'] = cluster_dir
        terraform_dir = os.path.join(cluster_dir, "terraform")
        os.chdir(terraform_dir)
        res = subprocess.run([
            "terraform",
            "apply",
            "-auto-approve",
            "-var-file=output.tfvars.json"
        ], capture_output=True, text=True)
        session = get_session()
        if res.returncode != 0:
            # 发生错误时更新集群务状态为"失败"
            print(f"Terraform error: {res.stderr}")
            task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "failed"
            task_info.detail = f"remove node failed, reason: {replace_ansi_with_single_newline(res.stderr)}"
            update_task_state(task_info)
            with session.begin():
                db_cluster = session.get(Cluster, (cluster_id, cluster_name))
                db_cluster.status = 'error'
                error_msg = replace_ansi_with_single_newline(res.stderr)
                db_cluster.status_msg = f"delete baremetal error: {error_msg}"
            return False
        task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        task_info.state = "success"
        task_info.detail = "remove node successfully"
        update_task_state(task_info)
        with session.begin():
            for node in instance_list:
                # 根据 node.id 删除节点
                node = session.get(Instance, node.get("id"))
                if node:
                    session.delete(node)
        with session.begin():
            db_cluster = session.get(Cluster, (cluster_id, cluster_name))
            cpu_total, gpu_total, mem_total = get_node_info(instance_list)
            db_cluster.cpu -= cpu_total
            db_cluster.gpu -= gpu_total
            db_cluster.mem -= mem_total
            query_params = {"cluster_id": cluster_id}
            count, instances = InstanceSQL.list_instances(query_params, 1, -1, None, None)
            for ins in instances:
                if ins.status != "running":
                    return False
            db_cluster.status = 'running'
            db_cluster.status_msg = ''
            return True

    except Exception as e:
        print(f"Ansible error: {e}")
        session = get_session()
        with session.begin():
            db_cluster = session.get(Cluster, (cluster_id, cluster_name))
            db_cluster.status = 'remove_error'
            error_msg = replace_ansi_with_single_newline(str(e))
            db_cluster.status_msg = f"delete baremetal error: {error_msg}"
        return False

@celery_app.task(bind=True)
def create_instance(self, instance, instance_list, external_net_id):
    try:
        instance = InstanceCreateObject(**instance)
        instance_list = json.loads(instance_list)
        # 1、拿到openstack的信息，就可以执行创建instance的流程，需要分别处理类型是vm还是裸金属的
        # conn = connection.Connection(
        #     auth_url=instance.openstack_info.openstack_auth_url,
        #     project_name=instance.openstack_info.project_name,
        #     username=instance.openstack_info.openstack_username,
        #     password=instance.openstack_info.openstack_password,
        #     user_domain_name=instance.openstack_info.user_domain_name,
        #     project_domain_name=instance.openstack_info.project_domain_name,
        #     region_name=instance.openstack_info.region
        # )
        auth = v3.Token(
            auth_url = NOVA_AUTH_URL,
            token = instance.openstack_info.token,
            project_id = instance.openstack_info.project_id  # 项目ID
        )

        session = KeySession(auth=auth)
        conn = connection.Connection(
            session = session
        )
        cidr = ""
        if not instance.network_id:
            # 创建network_id
            network = create_network_id(conn)
            subnet = create_subnet_id(conn, network)
            cidr = subnet.cidr
            instance.network_id = network.id
            create_router_id(conn, external_net_id, subnet.id)
        content = ""
        if not instance.sshkey_name:
            # 创建sshkey_name
            ssh_key, content = create_ssh_keypair(conn)
            instance.sshkey_name = ssh_key
        if not instance.security_group:
            # 创建security_group
            instance.security_group = "default"
        if instance.node_type == "vm":
            server_id_list = create_vm_instance(conn, instance, instance_list)
        else:
            server_id_list = create_bm_instance(conn, instance, instance_list)

        # 2、判断server的状态，如果都成功就将instance的信息写入数据库中的表中
        server_id_active = []
        server_id_error = []
        session = get_session()
        start_time = time.time()
        handle_time = 0
        while len(server_id_active) < len(server_id_list) and handle_time < SERVER_TIMEOUT:
            for server_id in server_id_list:
                if server_id in server_id_active or server_id in server_id_error:
                    continue
                server = conn.get_server(server_id)
                if server.status == "ACTIVE":
                    # 写入数据库中
                    for ins in instance_list:
                        if ins.get("name") == server.name:
                            with session.begin():
                                db_instance = session.get(Instance, ins.get("id"))
                                for k, v in server.addresses.items():
                                    for i in v:
                                        if i.get("OS-EXT-IPS:type") == "floating":
                                            db_instance.floating_ip = i.get("addr")
                                        if i.get("OS-EXT-IPS:type") == "fixed":
                                            db_instance.ip_address = i.get("addr")
                                db_instance.server_id = server.id
                                db_instance.private_key = content
                                db_instance.status = "running"
                                db_instance.cidr = cidr
                    server_id_active.append(server_id)
                elif server.status == "ERROR":
                    for ins in instance_list:
                        if ins.get("name") == server.name:
                            with session.begin():
                                db_instance = session.get(Instance, ins.get("id"))
                                db_instance.status = "error"
                                db_instance.status_msg = server.fault.get("details")
                    server_id_error.append(server_id)
                    if server_id_error == server_id_list:
                        break
            time.sleep(3)
            handle_time = time.time() - start_time
            if handle_time > SERVER_TIMEOUT:
                print("Execution time exceeds 20 minutes with check server's status")
        difference = list(set(server_id_list) - set(server_id_active))
        if difference:
            with session.begin():
                for server_id in difference:
                    server = conn.get_server(server_id)
                    for ins in instance_list:
                        if ins.get("name") == server.name:
                            db_instance = session.get(Instance, ins.get("id"))
                            db_instance.server_id = server.id
                            db_instance.status = "error"
                            db_instance.status_msg = server.fault.get("details")

        success_server = []
        handle_time = 0
        start_time = time.time()
        if instance.forward_float_ip_id and instance.port_forwards:
            while len(success_server) < len(server_id_list) and handle_time < SERVER_TIMEOUT:
                for server_id in server_id_list:
                    if server_id in success_server:
                        continue
                    server = conn.get_server(server_id)
                    ports = list(conn.network.ports(device_id=server.id))
                    internal_ip = ports[0].fixed_ips[0]["ip_address"]
                    internal_port_id = ports[0].id
                    try:
                        list_dict_forward = []
                        for port_forward in instance.port_forwards:
                            dict_forward = {}
                            random_port = random.randint(10000, 50000)
                            conn.network.create_port_forwarding(
                                floatingip_id=instance.forward_float_ip_id,
                                internal_port_id=internal_port_id,
                                internal_ip_address=internal_ip,
                                internal_port=port_forward.internal_port,
                                external_port=random_port,
                                protocol=port_forward.protocol,
                                description=f"{server.name} use forward rule",
                            )
                            dict_forward["dict_forward"] = port_forward.internal_port
                            dict_forward["protocol"] = port_forward.protocol
                            dict_forward["external_port"] = random_port
                            list_dict_forward.append(dict_forward)
                        with session.begin():
                            for instance in instance_list:
                                if instance.get("name") == server.name:
                                    db_instance = session.get(Instance, instance.get("id"))
                                    db_instance.ip_forward_rule = list_dict_forward
                                    db_instance.floating_forward_ip = instance.forward_float_ip_id
                        success_server.append(server_id)
                    except Exception as e:
                        if "port collision with the internal_port_range" in str(e):
                            continue
                        raise ValueError(e)
                time.sleep(3)
                handle_time = time.time() - start_time
                if handle_time > SERVER_TIMEOUT:
                    print("Execution time exceeds 20 minutes with create port forward rule")
    except Exception as e:
        print(f"create instance error: {e}")
        raise ValueError(e)


@celery_app.task(bind=True)
def delete_instance(self, openstack_info, instance):
    try:
        openstack_info = OpenStackConfigObject(**openstack_info)
        # 1、拿到openstack的信息，就可以执行删除instance的流程，需要分别处理类型是vm还是裸金属的
        # conn = openstack.connect(
        #     auth_url=openstack_info.openstack_auth_url,
        #     project_name=openstack_info.project_name,
        #     username=openstack_info.openstack_username,
        #     password=openstack_info.openstack_password,
        #     user_domain_name=openstack_info.user_domain_name,
        #     project_domain_name=openstack_info.project_domain_name,
        #     region_name=openstack_info.region
        # )
        auth = v3.Token(
            auth_url=NOVA_AUTH_URL,
            token=openstack_info.token,
            project_id=openstack_info.project_id
        )

        session = KeySession(auth=auth)
        conn = connection.Connection(
            session=session
        )
        # 2、将instance的信息在数据库中的表中删除
        instance_id = delete_vm_instance(conn, instance)
        session = get_session()
        with session.begin():
            db_instance = session.get(Instance, instance_id)
            session.delete(db_instance)
    except subprocess.CalledProcessError as e:
        print(f"delete instance error: {e}")
        raise ValueError(e)


@celery_app.task(bind=True)
def install_component(cluster_id, node_name):
    with Session(get_engine()) as session:
        # cluster = session.get(Cluster, cluster_id)
        # if not cluster:
        #     raise ValueError(f"Cluster with ID {cluster_id} does not exist")
        # node = Node(cluster_id=cluster_id, name=node_name)
        # session.add(node)
        # session.commit()
        # return node.id
        pass
