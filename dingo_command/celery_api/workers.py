from datetime import datetime
import json
import base64
import os
import subprocess
import time
import copy
from typing import Dict, Optional
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
SERVER_TIMEOUT = 600
NOVA_AUTH_URL = CommonConf.nova.auth_url
SSH_KEY_NAME = "instance_key"
INSTANCE_NET_NAME = "instance_network"
INSTANCE_SUBNET_NAME = "instance_subnet"

etcd_task_name = "Check etcd cluster status"
control_plane_task_name = "Check control plane status"
work_node_task_name = "Check k8s nodes status"


class Port_forwards(BaseModel):
    internal_port: Optional[int] = Field(None, description="转发的内部端口")
    external_port: Optional[int] = Field(None, description="转发的外部端口")
    protocol: Optional[str] = Field(None, description="协议")


class NodeGroup(BaseModel):
    az: Optional[str] = Field(None, description="可用域")
    flavor: Optional[str] = Field(None, description="规格")
    floating_ip: Optional[bool] = Field(None, description="浮动ip")
    etcd: Optional[bool] = Field(None, description="是否是etcd节点")
    image_id: Optional[str] = Field(None, description="镜像id")
    port_forwards: Optional[List[Port_forwards]] = Field(None, description="端口转发配置")


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
    port_forwards: Optional[list[Port_forwards]] = Field(None, description="端口转发配置")
    image_master: Optional[str] = Field(None, description="master节点的镜像")
    
def create_infrastructure(cluster:ClusterTFVarsObject, task_info:Taskinfo, region_name:str = "regionOne"):
    """使用Terraform创建基础设施"""
    try:

        # 将templat下的terraform目录复制到WORK_DIR/cluster.id目录下
        cluster_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id))
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
                     "-N", ""], capture_output=True)
                if res.returncode != 0:
                    # 发生错误时更新任务状态为"失败"
                    task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                    task_info.state = "failed"
                    task_info.detail = res.stderr
                    update_task_state(task_info)
                    print(f"ssh-keygen error: {res.stderr}")
                    return False
                cluster.private_key_path = os.path.join(cluster_dir, "id_rsa")
                cluster.public_key_path = os.path.join(cluster_dir, "id_rsa.pub")

        cluster.group_vars_path = os.path.join(cluster_dir, "group_vars")
        tfvars_str = json.dumps(cluster, default=lambda o: o.__dict__, indent=2)
        with open("output.tfvars.json", "w") as f:
            f.write(tfvars_str)
            
        os.environ['CURRENT_CLUSTER_DIR']=cluster_dir
        res = subprocess.run(["terraform", "init"], capture_output=True)
        if res.returncode != 0:
            # 发生错误时更新任务状态为"失败"
            task_info.end_time =datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "failed"
            task_info.detail = res.stderr
            update_task_state(task_info)
            print(f"Terraform init error: {res.stderr}")
            return False
       
        # 执行terraform apply
        # os.environ['OS_CLOUD']=cluster.region_name
        #os.environ['OS_CLOUD']=region_name 
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
            task_info.detail = res.stderr
            update_task_state(task_info)
            print(f"Terraform apply error: {res.stderr}")
            return False
        key_file_path = os.path.join(WORK_DIR, "ansible-deploy", "inventory",str(cluster.id), "id_rsa")
        private_key_content = ""
        if os.path.exists(key_file_path):
            with open(key_file_path, 'r') as key_file:
                private_key_content = key_file.read()
        query_params = {}
        query_params["id"] = cluster.id
        count, data = ClusterSQL.list_cluster(query_params)
        if count > 0:
            db_cluster = data[0]
            host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", cluster.id, "hosts")
            # Give execute permissions to the host file
            os.chmod(host_file, 0o755)
            network_id, bus_network_id, subnet_id, bussubnet_id = get_networks(cluster, task_info, host_file)
            db_cluster.admin_network_id = network_id
            db_cluster.admin_subnet_id = subnet_id
            db_cluster.bus_network_id = bus_network_id
            db_cluster.bus_subnet_id = bussubnet_id
            db_cluster.private_key = private_key_content
            #db_cluster.status = "running"
            ClusterSQL.update_cluster(db_cluster)
        if res.returncode != 0:
            # 发生错误时更新任务状态为"失败"
            task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "failed"
            task_info.detail = res.stderr
            update_task_state(task_info)
            print(f"Terraform error: {res.stderr}")
            return False
        else:
            # 更新任务状态为"成功"
            task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "success"
            task_info.detail = res.stdout
            update_task_state(task_info)
            print("Terraform apply succeeded")
        return res

    except subprocess.CalledProcessError as e:
        # 发生错误时更新任务状态为"失败"
        task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        task_info.state = "failed"
        task_info.detail = str(e)
        update_task_state(task_info)
        print(f"Terraform error: {e}")
        return False


@celery_app.task(bind=True)
def create_cluster(self, cluster_tf: ClusterTFVarsObject, cluster_dict: ClusterObject, instance_bm_list):
    try:
        task_id = self.request.id.__str__()
        cluster_id = cluster_tf["id"]
        print(f"Task ID: {task_id}, Cluster ID: {cluster_id}")
        cluster_tfvars = ClusterTFVarsObject(**cluster_tf)
        cluster = ClusterObject(**cluster_dict)

        instance_list = json.loads(instance_bm_list)
        instructure_task = Taskinfo(task_id=task_id, cluster_id=cluster_tf["id"], state="progress",
                                    start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                    msg=TaskService.TaskMessage.instructure_create.name)
        TaskSQL.insert(instructure_task)

        terraform_result = create_infrastructure(cluster_tfvars, instructure_task, cluster.region_name)

        if not terraform_result:
            raise Exception("Terraform infrastructure creation failed")
        instructure_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        instructure_task.state = "success"
        instructure_task.detail = TaskService.TaskDetail.instructure_create.value
        update_task_state(instructure_task)
        print("Terraform apply succeeded")

        host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", cluster_tfvars.id, "hosts")
        res = subprocess.run(["python3", host_file, "--list"], capture_output=True, text=True)
        if res.returncode != 0:
            # 更新数据库的状态为failed
            instructure_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
            instructure_task.state = "failed"
            instructure_task.detail = str(res.stderr)
            update_task_state(instructure_task)
            raise Exception("Error generating Ansible inventory")
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
                        if v.get("public_ipv4") != v.get("ip"):
                            db_instance.floating_ip = v.get("public_ipv4")
        query_params = {}
        query_params["id"] = cluster_tf["id"]
        count, db_clusters = ClusterSQL.list_cluster(query_params)
        db_cluster = db_clusters[0]
        db_cluster.status = 'running'
        db_cluster.status_msg = ""
        ClusterSQL.update_cluster(db_cluster)
    except Exception as e:
        # 发生错误时更新集群状态为"失败"
        query_params = {}
        query_params["id"] = cluster_tf["id"]
        count, db_clusters = ClusterSQL.list_cluster(query_params)
        db_cluster = db_clusters[0]
        db_cluster.status = 'error'
        db_cluster.status_msg = str(e.__str__())
        ClusterSQL.update_cluster(db_cluster)
        raise


def deploy_kubernetes(cluster: ClusterObject, lb_ip: str, task_id: str = None):
    """使用Ansible部署K8s集群"""
    etcd_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress",
                         start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                         msg=TaskService.TaskMessage.etcd_deploy.name)
    control_plane_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress",
                                  start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                                  msg=TaskService.TaskMessage.controler_deploy.name)
    worker_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress",
                           start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                           msg=TaskService.TaskMessage.worker_deploy.name)
    component_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress",
                              start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                              msg=TaskService.TaskMessage.component_deploy.name)

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
        }
        target_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "group_vars", "k8s_cluster")
        os.makedirs(target_dir, exist_ok=True)
        cluster_file = os.path.join(target_dir, "k8s-cluster.yml")
        render_templatefile(template_file, cluster_file, context)

        # 将templates下的ansible-deploy目录复制到WORK_DIR/cluster.id目录下
        task_info = etcd_task
        TaskSQL.insert(etcd_task)
        ansible_dir = os.path.join(WORK_DIR, "ansible-deploy")
        os.chdir(ansible_dir)
        host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "hosts")
        playbook_file = os.path.join(WORK_DIR, "ansible-deploy", "cluster.yml")
        key_file_path = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "id_rsa")
        private_key_content = None
        if os.path.exists(key_file_path):
            with open(key_file_path, 'r') as key_file:
                private_key_content = key_file.read()
        
        print(f"start deploy kubernetes cluster: {ansible_dir}")
        thread,runner = run_playbook(playbook_file, host_file, ansible_dir, ssh_key=private_key_content)
        # 处理并打印事件日志
        while runner.status not in ['canceled', 'successful', 'timeout', 'failed']:
            # 处理事件日志
            for event in runner.events:
                # 检查事件是否包含 task 信息
                if 'event_data' in event and 'task' in event['event_data']:
                    task_name = event['event_data'].get('task')
                    host =  event['event_data'].get('host')
                    task_status = event['event'].split('_')[-1]  # 例如 runner_on_ok -> ok
                     # 处理 etcd 任务的特殊逻辑
                    print(f"任务 {task_name} 在主机 {host} 上 Status: {event['event']}")
                    
                    if task_name == etcd_task_name and host != None:    
                        task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                        task_info.state = "success"
                        task_info.detail = TaskService.TaskDetail.etcd_deploy.value
                        update_task_state(task_info)                  
                        # 写入下一个任务
                        task_info = control_plane_task
                        TaskSQL.insert(control_plane_task)
                    if task_name == control_plane_task_name and host != None: 
                        task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                        task_info.state = "success"
                        task_info.detail = TaskService.TaskDetail.controler_deploy.value
                        update_task_state(task_info)   
                        # 写入下一个任务
                        task_info = worker_task
                        TaskSQL.insert(worker_task)
                    if task_name == work_node_task_name and host != None and task_status != "failed":
                        task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                        task_info.state = "success"
                        task_info.detail = TaskService.TaskDetail.worker_deploy.value
                        update_task_state(task_info)   
                        task_info = component_task
                        TaskSQL.insert(component_task)
                    
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
            raise Exception(f"Playbook execution failed: {runner.rc}")

        task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        task_info.state = "success"
        task_info.detail = TaskService.TaskDetail.component_deploy.value
        update_task_state(task_info)
        return True
    
    except subprocess.CalledProcessError as e:
        print(f"Ansible error: {e}")
        return False

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
    if task_name == work_node_task_name and host != None:
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


def scale_kubernetes(cluster: ClusterObject, scale_nodes):
    """使用Ansible扩容K8s集群"""
    try_count = 5
    count = 0
    while count < try_count:
        try:
            ansible_dir = os.path.join(WORK_DIR, "ansible-deploy")
            os.chdir(ansible_dir)
            host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "hosts")
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
            while runner.status not in ['canceled', 'successful', 'timeout', 'failed']:
                for event in runner.events:
                    # 检查事件是否包含 task 信息
                    if 'event_data' in event and 'task' in event['event_data']:
                        task_name = event['event_data'].get('task')
                        host = event['event_data'].get('host')
                        task_status = event['event'].split('_')[-1]  # 例如 runner_on_ok -> ok
                        print(f"任务 {task_name} 在主机 {host} 上 Status: {event['event']}")
                        # 将结果输出到文件中
                        with open("ansible_debug.log", "a") as log_file:
                            log_file.write(f"Task: {task_name}, Status: {task_status}, host:  {host}\n")
                time.sleep(0.01)
                continue
            log_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "ansible_scale.log")
            with open(log_file, "a") as log_file:
                log_file.write(format(runner.stdout.read()))
            thread.join()
            if runner.rc != 0:
                # 更新数据库的状态为failed
                print("{}".format(runner.stderr.read()))
                count += 1
                continue
            print("out: {}".format(runner.stdout.read()))
            print("err: {}".format(runner.stderr.read()))
            return True
        except subprocess.CalledProcessError as e:
            count += 1
            print(f"Ansible error: {e}")
            continue
    return False


def get_cluster_kubeconfig(cluster: ClusterTFVarsObject, lb_ip, master_ip, float_ip):
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
        if lb_ip != None and lb_ip != "":
            ip = lb_ip
        elif master_ip != None and master_ip != "":
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

def create_subnet_id(conn, network, subnet_name=INSTANCE_SUBNET_NAME):
    existing_subnet = conn.network.find_subnet(subnet_name)
    if not existing_subnet:
        conn.network.create_subnet(
            name=subnet_name,
            network_id=network.id,
            ip_version=4,
            cidr="10.0.0.0/16",
            gateway_ip="10.0.0.1",
            allocation_pools=[{"start": "10.0.1.2", "end": "10.0.255.254"}],
            dns_nameservers=["8.8.8.8", "114.114.114.114"],
            enable_dhcp=True
        )


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
                                                key_name=instance_info.sshkey_name, config_drive=True, metadata=meta_data)
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

@celery_app.task(bind=True)
def create_k8s_cluster(self, cluster_tf_dict, cluster_dict, node_list, instance_list, scale_nodes=None, scale=False):
    try:
        task_id = self.request.id.__str__()
        print(f"Task ID: {task_id}")
        cluster_tfvars = ClusterTFVarsObject(**cluster_tf_dict)
        cluster = ClusterObject(**cluster_dict)
        node_list = json.loads(node_list)
        instance_list = json.loads(instance_list)
        # 将task_info存入数据库
        task_info = Taskinfo(task_id=task_id, cluster_id=cluster_tf_dict["id"], state="progress",
                             start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                             msg=TaskService.TaskMessage.instructure_create.name)
        TaskSQL.insert(task_info)

        terraform_result = create_infrastructure(cluster_tfvars, task_info, cluster.region_name)

        if not terraform_result:
            raise Exception("Terraform infrastructure creation failed")
        # 打印日志
        print("Terraform infrastructure creation succeeded")

        # 根据生成inventory
        # 复制script下面的host文件到WORK_DIR/cluster.id目录下
        # 执行python3 host --list，将生成的内容转换为yaml格式写入到inventory/inventory.yaml文件中
        # 将task_info存入数据库
        task_info = Taskinfo(task_id=task_id, cluster_id=cluster_tf_dict["id"], state="progress",
                             start_time=datetime.fromtimestamp(datetime.now().timestamp()),
                             msg=TaskService.TaskMessage.pre_install.name)
        TaskSQL.insert(task_info)

        host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", cluster_tf_dict["id"], "hosts")
        # Give execute permissions to the host file
        os.chmod(host_file, 0o755)  # rwxr-xr-x permission

        print(f"config ssh no pass {task_id}")
        master_ip, lb_ip, hosts_data = get_ips(cluster_tfvars, task_info, host_file)
        # ensure /root/.ssh/known_hosts exists
        if os.path.exists("/root/.ssh/known_hosts"):
            for i in range(1, cluster_tfvars.number_of_k8s_masters + 1):
                print(f"delete host from know_hosts  {task_id}")
                master_node_name = f"{cluster_tfvars.cluster_name}-k8s-master-{i}"
                tmp_ip = hosts_data["_meta"]["hostvars"][master_node_name]["access_ip_v4"]
                cmd = f'ssh-keygen -f "/root/.ssh/known_hosts" -R "{tmp_ip}"'
                result = subprocess.run(cmd, shell=True, capture_output=True)
                if result.returncode != 0:
                    task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                    task_info.state = "failed"
                    task_info.detail = str(result.stderr)
                    update_task_state(task_info)
                    raise Exception("Ansible kubernetes deployment failed, configure ssh-keygen error")
        if cluster_tfvars.password != "":
            cmd = f'sshpass -p "{cluster_tfvars.password}" ssh-copy-id -o StrictHostKeyChecking=no {cluster_tfvars.ssh_user}@{master_ip}'
            result = subprocess.run(cmd, shell=True, capture_output=True)
            if result.returncode != 0:
                task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                task_info.state = "failed"
                task_info.detail = str(result.stderr)
                update_task_state(task_info)
                raise Exception("Ansible kubernetes deployment failed, configure sshpass error")

        # 执行ansible命令验证是否能够连接到所有节点
        print(f"check all node status {task_id}")
        ansible_dir = os.path.join(WORK_DIR, "ansible-deploy")
        os.chdir(ansible_dir)
        key_file_path = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "id_rsa")
        # 添加重试逻辑
        start_time = time.time()
        max_retry_time = 600  # 10分钟超时
        retry_interval = 5    # 5秒重试间隔
        connection_success = False

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
                        if v.get("public_ipv4") != v.get("ip"):
                            db_node.floating_ip = v.get("public_ipv4")
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
                        if v.get("public_ipv4") != v.get("ip"):
                            db_instance.floating_ip = v.get("public_ipv4")
                        break

        res = subprocess.run(["python3", host_file, "--list"], capture_output=True, text=True)
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
        master_ip = hosts_data["_meta"]["hostvars"][master_node_name]["ip"]
        float_ip = hosts_data["_meta"]["hostvars"][master_node_name]["access_ip_v4"]
        
        task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        task_info.state = "success"
        task_info.detail = TaskService.TaskDetail.pre_install.value
        update_task_state(task_info)
        # 2. 使用Ansible部署K8s集群
        cluster.id = cluster_tf_dict["id"]
        if scale:
            ansible_result = scale_kubernetes(cluster, scale_nodes)
        else:
            ansible_result = deploy_kubernetes(cluster, lb_ip, task_id)
        if not ansible_result:
            raise Exception("Ansible kubernetes deployment failed")
        # 阻塞线程，直到ansible_client.get_playbook_result()返回结果
        # 获取集群的kube_config
        kube_config = get_cluster_kubeconfig(cluster_tfvars,lb_ip,master_ip,float_ip)
        # 更新集群状态为running
        count, db_cluster = ClusterSQL.list_cluster(cluster_dict["id"])
        c = db_cluster[0]
        kube_info = json.loads(c.kube_info)
        kube_info["kube_config"] = kube_config
        c.kube_info = json.dumps(kube_info)
        c.status = 'running'
        c.error_message = ""
        ClusterSQL.update_cluster(c)

        # 更新数据库的状态为success
        task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        task_info.state = "success"
        task_info.detail = ""
        update_task_state(task_info)
    except Exception as e:
        # 发生错误时更新集群状态为"失败"
        print(f"deploy k8s cluster error")
        count, db_clusters = ClusterSQL.list_cluster(cluster_dict["id"])
        c = db_clusters[0]
        c.status = 'error'
        c.status_msg = str(e.__str__())
        ClusterSQL.update_cluster(c)
        raise


def get_ips(cluster_tfvars, task_info, host_file):
    res = subprocess.run(["python3", host_file, "--list"], capture_output=True, text=True)
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
    master_ip = hosts_data["_meta"]["hostvars"][master_node_name]["access_ip_v4"]
    lb_ip = hosts_data["_meta"]["hostvars"][master_node_name]["lb_ip"]
    return master_ip, lb_ip, hosts_data


def get_networks(cluster_tfvars, task_info, host_file):
    res = subprocess.run(["python3", host_file, "--list"], capture_output=True, text=True)
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
    network_id = hosts_data["_meta"]["hostvars"][node_name]["network"][0]['uuid']
    if hosts_data["_meta"]["hostvars"][node_name]["network"].__len__() > 1:
        bus_network_id = hosts_data["_meta"]["hostvars"][node_name]["network"][1]['uuid']
    subnet_id = hosts_data["_meta"]["hostvars"][node_name]["subnet_id"]
    bussubnet_id = hosts_data["_meta"]["hostvars"][node_name]["bussubnet_id"]
    return network_id, bus_network_id, subnet_id, bussubnet_id

def load_tfvars_to_object(tfvars_path):
    """
    从 output.tfvars.json 文件加载内容并转换为 ClusterTFVarsObject 对象
    
    Args:
        tfvars_path: output.tfvars.json 文件路径
        
    Returns:
        ClusterTFVarsObject 对象
    """
    import json
    from dingo_command.celery_api.workers import ClusterTFVarsObject
    
    # 读取 tfvars 文件
    with open(tfvars_path, 'r') as f:
        tfvars_data = json.load(f)
    
    # 将 JSON 数据直接传递给 Pydantic 模型构造函数
    # Pydantic 会自动处理数据类型转换和验证
    cluster_tfvars = ClusterTFVarsObject(**tfvars_data)
    
    return cluster_tfvars


@celery_app.task(bind=True)
def delete_cluster(self, cluster_id, region_name, token):
    # 进入到terraform目录
    cluster_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", cluster_id)
    terraform_dir = os.path.join(cluster_dir, "terraform")
    print(f"Terraform dir: {terraform_dir}")
    print(f"Terraform dir: {region_name}")

    os.chdir(terraform_dir)
    # 删除集群
    #os.environ['OS_CLOUD'] = region_name
    if not os.path.exists(cluster_dir):
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
        return True
    res = subprocess.run(["terraform", "destroy", "-auto-approve", "-var-file=output.tfvars.json"], capture_output=True)
    # 获取 tfvars 文件路径
    tfvars_path = os.path.join(WORK_DIR, "ansible-deploy", "inventory", cluster_id, "terraform", "output.tfvars.json")

    # 加载为 ClusterTFVarsObject 对象
    cluster_tfvars = load_tfvars_to_object(tfvars_path)
    cluster_tfvars.token = token
    tfvars_str = json.dumps(cluster_tfvars, default=lambda o: o.__dict__, indent=2)
    with open("output.tfvars.json", "w") as f:
        f.write(tfvars_str)
    if res.returncode != 0:
        # 发生错误时更新任务状态为"失败"

        print(f"Terraform error: {res.stderr}")
        query_params = {}
        query_params["id"] = cluster_id
        count, db_clusters = ClusterSQL.list_cluster(query_params)
        c = db_clusters[0]
        c.status = 'delete_error'
        c.status_msg = "delete cluster error"
        ClusterSQL.update_cluster(c)
        return False
    else:
        
        # 更新任务状态为"成功"
        query_params = {}
        query_params["id"] = cluster_id
        count, db_clusters = ClusterSQL.list_cluster(query_params)
        c = db_clusters[0]
        c.status = 'deleted'
        c.status_msg = ""
        ClusterSQL.update_cluster(c)
        print("Terraform destroy succeeded")


@celery_app.task(bind=True)
def delete_node(self, cluster_id, cluster_name, node_list, instance_list, extravars):
    try:
        node_list = json.loads(node_list)
        instance_list = json.loads(instance_list)
        extravars["skip_confirmation"] = "true"
        cluster_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id))
        os.environ['CURRENT_CLUSTER_DIR'] = cluster_dir
        # os.environ['OS_CLOUD'] = node.get("region_name")
        # 1、在这里先找到cluster的文件夹，找到对应的目录，先通过发来的node_list组合成extravars的变量，再执行remove-node.yaml
        ansible_dir = os.path.join(WORK_DIR, "ansible-deploy")
        os.chdir(ansible_dir)
        host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id), "hosts")
        playbook_file = os.path.join(WORK_DIR, "ansible-deploy", "remove-node.yml")
        key_file_path = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id), "id_rsa")
        private_key_content = ""
        if os.path.exists(key_file_path):
            with open(key_file_path, 'r') as key_file:
                private_key_content = key_file.read()
        thread, runner = run_playbook(playbook_file, host_file, ansible_dir,
                                      ssh_key=private_key_content, extravars=extravars)
        # 处理并打印事件日志
        while runner.status not in ['canceled', 'successful', 'timeout', 'failed']:
            for event in runner.events:
                # 检查事件是否包含 task 信息
                if 'event_data' in event and 'task' in event['event_data']:
                    task_name = event['event_data'].get('task')
                    host = event['event_data'].get('host')
                    task_status = event['event'].split('_')[-1]  # 例如 runner_on_ok -> ok
                    print(f"任务 {task_name} 在主机 {host} 上 Status: {event['event']}")
                    # 将结果输出到文件中
                    with open("ansible_debug.log", "a") as log_file:
                        log_file.write(f"Task: {task_name}, Status: {task_status}, host:  {host}\n")
            time.sleep(0.01)
            continue
        log_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id), "ansible_remove.log")
        with open(log_file, "a") as log_file:
            log_file.write(format(runner.stdout.read()))
        thread.join()
        if runner.rc != 0:
            print("{}".format(runner.stderr.read()))
            raise Exception("Ansible remove node failed")
        print("out: {}".format(runner.stdout.read()))
        print("err: {}".format(runner.stderr.read()))

        # # 2、执行完删除k8s这些节点之后，再执行terraform销毁这些节点（这里是单独修改output.json文件还是需要通过之前生成的output.json文件生成）
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
        session = get_session()
        with session.begin():
            db_cluster = session.get(Cluster, (cluster_id, cluster_name))
            db_cluster.status = 'running'
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

    except subprocess.CalledProcessError as e:
        print(f"Ansible error: {e}")
        return False

@celery_app.task(bind=True)
def delete_baremetal(self, cluster_id, cluster_name, instance_list, token):
    try:
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
        with session.begin():
            db_cluster = session.get(Cluster, (cluster_id, cluster_name))
            db_cluster.status = 'running'
            for node in instance_list:
                # 根据 node.id 删除节点
                node = session.get(Instance, node.get("id"))
                if node:
                    session.delete(node)

    except subprocess.CalledProcessError as e:
        print(f"Ansible error: {e}")
        return False

@celery_app.task(bind=True)
def create_instance(self, instance, instance_list):
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
        if not instance.network_id:
            # 创建network_id
            network = create_network_id(conn)
            create_subnet_id(conn, network)
            instance.network_id = network.id
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
                if server_id in server_id_active:
                    continue
                server = conn.get_server(server_id)
                if server.status == "ACTIVE":
                    # 写入数据库中
                    for instance in instance_list:
                        if instance.get("name") == server.name:
                            with session.begin():
                                db_instance = session.get(Instance, instance.get("id"))
                                for k, v in server.addresses.items():
                                    for i in v:
                                        if i.get("OS-EXT-IPS:type") == "floating":
                                            db_instance.floating_ip = i.get("addr")
                                        if i.get("OS-EXT-IPS:type") == "fixed":
                                            db_instance.ip_address = i.get("addr")
                                db_instance.server_id = server.id
                                db_instance.private_key = content
                                db_instance.status = "running"
                                db_instance.security_group = "default"
                                db_instance.cidr = "10.0.0.0/16"
                    server_id_active.append(server_id)
                elif server.status == "ERROR":
                    server_id_error.append(server_id)
                    if server_id_error == server_id_list:
                        break
            time.sleep(5)
            handle_time = time.time() - start_time
        difference = list(set(server_id_list) - set(server_id_active))
        if difference:
            with session.begin():
                for server_id in difference:
                    server = conn.get_server(server_id)
                    for instance in instance_list:
                        if instance.get("name") == server.name:
                            db_instance = session.get(Instance, instance.get("id"))
                            db_instance.server_id = server.id
                            db_instance.status = "error"
                            db_instance.status_msg = server.fault.get("details")
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
