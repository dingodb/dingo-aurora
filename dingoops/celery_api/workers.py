
import copy
from asyncio import sleep
from datetime import datetime
import json
import logging
import os
import subprocess
import time
from typing import Any, Dict, Optional
from celery import Celery
from dingoops.api.model.cluster import ClusterObject
from dingoops.api.model.instance import InstanceConfigObject, InstanceCreateObject
from dingoops.celery_api.ansible import run_playbook,CustomCallback
from dingoops.celery_api.util import update_task_state
from dingoops.services.cluster import TaskService
from dingoops.db.models.cluster.models import Cluster,Taskinfo
from dingoops.db.models.node.models import NodeInfo
from dingoops.db.models.instance.models import Instance
from pydantic import BaseModel, Field
import openstack
from fastapi import Path
from pathlib import Path as PathLib
from requests import Session
from dingoops.celery_api.celery_app import celery_app
from dingoops.celery_api import CONF
from dingoops.db.engines.mysql import get_engine, get_session
from dingoops.db.models.cluster.sql import ClusterSQL, TaskSQL

from dingoops.db.models.node.sql import NodeSQL
from dingoops.db.models.instance.sql import InstanceSQL
from ansible.executor.playbook_executor import PlaybookExecutor

# 用于导入资产文件
from ansible.inventory.manager import InventoryManager
from celery import current_task   
import yaml        
from jinja2 import Environment, FileSystemLoader

BASE_DIR = os.getcwd()
TERRAFORM_DIR = os.path.join(BASE_DIR, "dingoops", "templates", "terraform")
ANSIBLE_DIR = os.path.join(BASE_DIR, "templates", "ansible-deploy")
WORK_DIR = CONF.DEFAULT.cluster_work_dir
TIMEOUT = 600

etcd_task_name = "Check etcd cluster status"
control_plane_task_name = "Check control plane status"
work_node_task_name = "Check k8s nodes status"


class NodeGroup(BaseModel):
    az: Optional[str] = Field(None, description="可用域")
    flavor: Optional[str] = Field(None, description="规格")
    floating_ip: Optional[bool] = Field(None, description="浮动ip")
    etcd: Optional[bool] = Field(None, description="是否是etcd节点")

class ClusterTFVarsObject(BaseModel):
    id: Optional[str] = Field(None, description="集群id")
    cluster_name: Optional[str] = Field(None, description="集群id")
    image: Optional[str] = Field(None, description="用户id")
    nodes: Optional[Dict[str, NodeGroup]] = Field(None, description="集群状态")
    admin_subnet_id: Optional[str] = Field(None, description="管理子网id")
    bus_network_id: Optional[str] = Field(None, description="业务网络id")
    admin_network_id: Optional[str] = Field(None, description="管理网id")
    bus_subnet_id: Optional[str] = Field(None, description="业务子网id")
    ssh_user: Optional[str] = Field(None, description="用户名")
    password: Optional[str] = Field(None, description="密码")
    floatingip_pool: Optional[str] = Field(None, description="浮动ip池")
    subnet_cidr: Optional[str] = Field(None, description="运行时类型")
    use_existing_network: Optional[bool] = Field(None, description="是否使用已有网络")
    external_net: Optional[str] = Field(None, description="外部网络id")
    group_vars_path:  Optional[str] = Field(None, description="集群变量路径")
    number_of_etcd: Optional[int] = Field(0, description="ETCD节点数量")
    number_of_k8s_masters: Optional[int] = Field(0, description="K8s master节点数量")
    number_of_k8s_masters_no_etcd: Optional[int] = Field(0, description="不带ETCD的K8s master节点数量")
    number_of_k8s_masters_no_floating_ip: Optional[int] = Field(0, description="无浮动IP的K8s master节点数量")
    number_of_k8s_masters_no_floating_ip_no_etcd: Optional[int] = Field(0, description="无浮动IP且不带ETCD的K8s master节点数量")
    number_of_k8s_nodes: Optional[int] = Field(0, description="K8s worker节点数量")
    number_of_k8s_nodes_no_floating_ip: Optional[int] = Field(0, description="无浮动IP的K8s worker节点数量")
    k8s_master_loadbalancer_enabled: Optional[bool] = Field(False, description="是否启用负载均衡器")
    public_key_path: Optional[str] = Field(None, description="公钥路径")
    
def create_infrastructure(cluster:ClusterTFVarsObject, task_info:Taskinfo, region_name:str = "regionOne"):
    """使用Terraform创建基础设施"""
    try:
        
        # 将templat下的terraform目录复制到WORK_DIR/cluster.id目录下
        cluster_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id))
        subprocess.run(["cp", "-LRpf", os.path.join(WORK_DIR, "ansible-deploy", "inventory","sample-inventory"), str(cluster_dir)], capture_output=True)

        subprocess.run(["cp", "-r", str(TERRAFORM_DIR), str(cluster_dir)], capture_output=True)
        os.chdir(os.path.join(cluster_dir, "terraform"))
        # 初始化terraform
        os.environ['https_proxy']="172.20.3.88:1088"
        os.environ['CURRENT_CLUSTER_DIR']=cluster_dir
        res = subprocess.run(["terraform", "init"], capture_output=True)
        if res.returncode != 0:
            # 发生错误时更新任务状态为"失败"
            task_info.end_time =datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "failed"
            task_info.detail = res.stderr
            update_task_state(task_info)
            print(f"Terraform error: {res.stderr}")
            return False
        
        if cluster.password == "":
            res = subprocess.run(["ssh-keygen", "-t", "rsa", "-b", "4096", "-C", "", "-f", os.path.join(str(cluster_dir), "id_rsa"), "-N", ""], capture_output=True)
            if res.returncode != 0:
            # 发生错误时更新任务状态为"失败"
                task_info.end_time =datetime.fromtimestamp(datetime.now().timestamp())
                task_info.state = "failed"
                task_info.detail = res.stderr
                update_task_state(task_info)
                print(f"Terraform error: {res.stderr}")
                return False
            cluster.public_key_path = os.path.join(cluster_dir, "id_rsa.pub")
        
        
        cluster.group_vars_path = os.path.join(cluster_dir, "group_vars")          
        tfvars_str = json.dumps(cluster, default=lambda o: o.__dict__, indent=2)
        with open("output.tfvars.json", "w") as f:
            f.write(tfvars_str)
       
        # 执行terraform apply
        # os.environ['OS_CLOUD']=cluster.region_name
        os.environ['OS_CLOUD']=region_name
        res = subprocess.run([
            "terraform",
            "apply",
            "-auto-approve",
            "-var-file=output.tfvars.json"
        ], capture_output=True, text=True) 
        
        if res.returncode != 0:
            # 发生错误时更新任务状态为"失败"
            task_info.end_time =datetime.fromtimestamp(datetime.now().timestamp())
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
def create_cluster(self, cluster_tf:ClusterTFVarsObject,cluster:ClusterObject):
    try:
        task_id = self.request.id.__str__()
        instructure_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress", start_time=datetime.fromtimestamp(datetime.now().timestamp()),msg=TaskService.TaskMessage.instructure_create.name)
        TaskSQL.insert(instructure_task)
        cluster_tfvars = ClusterTFVarsObject(**cluster_tf)
        cluster_dict = ClusterTFVarsObject(**cluster)
        terraform_result = create_infrastructure(cluster_tfvars,instructure_task, cluster.region_name)
        
        if not terraform_result:
            raise Exception("Terraform infrastructure creation failed")
        instructure_task.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        instructure_task.state = "success"
        instructure_task.detail = TaskService.TaskDetail.instructure_create.value
        update_task_state(instructure_task)
        print("Terraform apply succeeded")
        db_cluster = ClusterSQL.list_cluster(cluster_dict["id"])
        db_cluster.status = 'failed'
        db_cluster.error_message = str(e.__str__())
        ClusterSQL.update_cluster(cluster_dict["id"])
    except Exception as e:
        # 发生错误时更新集群状态为"失败"
        db_cluster = ClusterSQL.list_cluster(cluster_dict["id"])[0]
        db_cluster.status = 'failed'
        db_cluster.error_message = str(e.__str__())
        ClusterSQL.update_cluster(cluster_dict["id"])
        raise
        
        
    


def deploy_kubernetes(cluster:ClusterObject,lb_ip:str, task_id:str = None):
    """使用Ansible部署K8s集群"""
    etcd_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress", start_time=datetime.fromtimestamp(datetime.now().timestamp()),msg=TaskService.TaskMessage.etcd_deploy.name)
    control_plane_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress", start_time=datetime.fromtimestamp(datetime.now().timestamp()),msg=TaskService.TaskMessage.controler_deploy.name)
    worker_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress", start_time=datetime.fromtimestamp(datetime.now().timestamp()),msg=TaskService.TaskMessage.worker_deploy.name)
    component_task = Taskinfo(task_id=task_id, cluster_id=cluster.id, state="progress", start_time=datetime.fromtimestamp(datetime.now().timestamp()),msg=TaskService.TaskMessage.component_deploy.name)

    try:
        # #替换
        # # 定义上下文字典，包含所有要替换的变量值
        context = {
            'kube_version': cluster.kube_info.version,
            'kube_network_plugin': cluster.kube_info.cni,
            'service_cidr': cluster.kube_info.service_cidr,
            "kube_vip_address": lb_ip,
            "kube_proxy_mode": cluster.kube_info.kube_proxy_mode,
        }
        # 修正模板文件路径
        template_file = "k8s-cluster.yml.j2"
        template_dir = os.path.join(BASE_DIR, "dingoops", "templates")
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
         # 确保目标目录存在
        target_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "group_vars", "k8s_cluster")
        os.makedirs(target_dir, exist_ok=True)
        
        # 写入渲染后的内容
        cluster_file = os.path.join(target_dir, "k8s-cluster.yml")
        # 将渲染后的内容写入新文件，使用 UTF-8 编码确保兼容性
        with open(cluster_file, 'w', encoding='utf-8') as f:
            f.write(rendered)
        
        # 将templates下的ansible-deploy目录复制到WORK_DIR/cluster.id目录下
        task_info = etcd_task
        TaskSQL.insert(etcd_task)
        ansible_dir = os.path.join(WORK_DIR, "ansible-deploy")
        os.chdir(ansible_dir)
        host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "hosts")
        playbook_file  = os.path.join(WORK_DIR, "ansible-deploy", "cluster.yml")
        thread,runner = run_playbook(playbook_file, host_file, ansible_dir)
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
                        
                    #将结果输出到文件中
                    with open("ansible_debug.log", "a") as log_file:
                        log_file.write(f"Task: {task_name}, Status: {task_status}, host:  {host}\n")
            time.sleep(0.01)
            continue
        print("out: {}".format(runner.stdout.read()))
        print("err: {}".format(runner.stderr.read()))
        print(runner.stdout)
        thread.join()
        # 检查最终状态
        if runner.rc != 0:
            # 更新数据库的状态为failed
            task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "failed"
            task_info.detail = event['event_data'].get('res').get('msg')
            update_task_state(task_info)
            raise Exception(f"Playbook execution failed: {runner.rc}")

        task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        task_info.state = "success"
        task_info.detail = TaskService.TaskDetail.component_deploy.value
        update_task_state(task_info)
    
    except subprocess.CalledProcessError as e:
        print(f"Ansible error: {e}")
        return False


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


def scale_kubernetes(cluster: ClusterObject):
    """使用Ansible扩容K8s集群"""
    try:
        ansible_dir = os.path.join(WORK_DIR, "ansible-deploy")
        os.chdir(ansible_dir)
        host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "hosts")
        playbook_file = os.path.join(WORK_DIR, "ansible-deploy", "scale.yml")
        run_playbook(playbook_file, host_file, ansible_dir)

    except subprocess.CalledProcessError as e:
        print(f"Ansible error: {e}")
        return False

    
def get_cluster_kubeconfig(cluster, lb_ip):
    """获取集群的kubeconfig配置"""
    try:
        # 切换到terraform工作目录
        os.chdir(TERRAFORM_DIR)
        
        # 获取master节点IP
        result = subprocess.run(
            ["terraform", "output", "master_ip"],
            capture_output=True,
            text=True,
            check=True
        )
        master_ip = result.stdout.strip()
        
        # SSH连接到master节点获取kubeconfig
        result = subprocess.run(
            [
                "ssh",
                "-i", f"{TERRAFORM_DIR}/ssh_key",  # SSH私钥路径
                f"ubuntu@{master_ip}",
                "sudo cat /etc/kubernetes/admin.conf"
            ],
            capture_output=True,
            text=True,
            check=True
        )
        
        kubeconfig = result.stdout
        
        # 替换server地址为外部IP
        kubeconfig = kubeconfig.replace(
            "server: https://127.0.0.1:6443",
            f"server: https://{lb_ip}:6443"
        )
        get_engine()
        # 保存kubeconfig到数据库
        with Session(get_engine()) as session:
            db_cluster = session.get(Cluster, cluster.id)
            db_cluster.kube_config = kubeconfig
            session.commit()
            
        return kubeconfig
        
    except subprocess.CalledProcessError as e:
        print(f"Error getting kubeconfig: {e}")
        return None

def delete_vm_instance(conn, instance_list):
    # 在这里使用openstack的api接口，直接删除vm或bm
    server_list = []
    for instance in instance_list:
        server = conn.compute.find_server(instance.id)
        conn.compute.delete_server(server)
        conn.compute.wait_for_delete(server, wait=TIMEOUT)
        server_list.append(server.id)
    return server_list

def create_vm_instance(conn, instance_info: InstanceCreateObject, instance_list):
    # 在这里使用openstack的api接口，直接创建vm
    server_list = []
    for ins in instance_list:
        server = conn.create_server(
            name=ins.name,
            image=instance_info.image_id,
            flavor=instance_info.flavor_id,
            network=instance_info.network_id,
            key_name=instance_info.sshkey_name,
            wait=False
        )
        server_list.append(server.id)
    return server_list

def create_bm_instance(conn, instance_info: InstanceCreateObject, instance_list):
    # 在这里使用openstack的api接口，直接创建bm
    server_list = []
    for ins in instance_list:
        server = conn.create_server(
            name=ins.name,
            image=instance_info.image_id,
            flavor=instance_info.flavor_id,
            network=instance_info.network_id,
            key_name=instance_info.sshkey_name,
            config_drive=True,
            meta={
                "baremetal": "true",
                "capabilities": "boot_option:local"
            },
            wait=False
        )
        server_list.append(server.id)
    return server_list
    
@celery_app.task(bind=True)
def create_k8s_cluster(self, cluster_tf_dict, cluster_dict, node_list, scale=False):

    try:
        task_id = self.request.id.__str__()
        #task_id = "da"
        print(f"Task ID: {task_id}")
        cluster_tfvars = ClusterTFVarsObject(**cluster_tf_dict)
        cluster = ClusterObject(**cluster_dict)
        # 1. 使用Terraform创建基础设施
         # 将task_info存入数据库
        task_info = Taskinfo(task_id=task_id, cluster_id=cluster_tf_dict["id"], state="progress", start_time=datetime.fromtimestamp(datetime.now().timestamp()),msg=TaskService.TaskMessage.instructure_create.name)
        TaskSQL.insert(task_info)

        terraform_result = create_infrastructure(cluster_tfvars,task_info, cluster.region_name)
        if not terraform_result:
            raise Exception("Terraform infrastructure creation failed")
        # 打印日志
        print("Terraform infrastructure creation succeeded")
        # 根据生成inventory
        # 复制script下面的host文件到WORK_DIR/cluster.id目录下
        #执行python3 host --list，将生成的内容转换为yaml格式写入到inventory/inventory.yaml文件中
         # 将task_info存入数据库
        task_info = Taskinfo(task_id=task_id, cluster_id=cluster_tf_dict["id"], state="progress", start_time=datetime.fromtimestamp(datetime.now().timestamp()),msg=TaskService.TaskMessage.pre_install.name)
        TaskSQL.insert(task_info)

        host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory",cluster_tf_dict["id"], "hosts")
        # Give execute permissions to the host file
        os.chmod(host_file, 0o755)  # rwxr-xr-x permission

        # 执行ansible命令验证是否能够连接到所有节点
        res = subprocess.run([
            "ansible",
            "-i", host_file,
            "-m", "ping",
            "all"
        ], capture_output=True)   
        master_ip, lb_ip = get_ips(cluster_tfvars, task_info, host_file)
        result = subprocess.run("", shell=True, capture_output=True)
        
        if cluster_tfvars.password == "":
            cmd = f'ssh-keygen -f "/root/.ssh/known_hosts" -R "{master_ip}" && sshpass -p "{cluster_tfvars.password}" ssh-copy-id -o StrictHostKeyChecking=no {cluster_tfvars.ssh_user}@{master_ip}'
            result = subprocess.run(cmd, shell=True, capture_output=True)
            if result.returncode != 0:
                task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
                task_info.state = "failed"
                task_info.detail = str(result.stderr)
                update_task_state(task_info)
                raise Exception("Ansible kubernetes deployment failed")

        task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        task_info.state = "success"
        task_info.detail = str(res.stdout)
        update_task_state(task_info)

        res = subprocess.run(["python3", host_file, "--list"], capture_output=True, text=True)
        if res.returncode != 0:
            #更新数据库的状态为failed
            task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "failed"
            task_info.detail = str(res.stderr)
            update_task_state(task_info)
            raise Exception("Error generating Ansible inventory")
        hosts = res.stdout
        # todo 添加节点时，需要将节点信息写入到inventory/inventory.yaml文件中
        # 如果是密码登录与master节点1做免密
        hosts_data = json.loads(hosts)
        # 从_meta.hostvars中获取master节点的IP
        master_node_name = cluster_tfvars.cluster_name+"-k8s-master1"
        master_ip = hosts_data["_meta"]["hostvars"][master_node_name]["access_ip_v4"]
        cmd = f'sshpass -p "{cluster_tfvars.password}" ssh-copy-id -o StrictHostKeyChecking=no {cluster_tfvars.ssh_user}@{master_ip}'
        result = subprocess.run(cmd, shell=True, capture_output=True)
        if result.returncode != 0:
            task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
            task_info.state = "failed"
            task_info.detail = str(result.stderr)
            update_task_state(task_info)
            raise Exception("Ansible kubernetes deployment failed")

        # 2. 使用Ansible部署K8s集群
        cluster.id = cluster_tf_dict["id"]

        if scale:
            ansible_result = scale_kubernetes(cluster)
        else:
            ansible_result = deploy_kubernetes(cluster,lb_ip,task_id)

        #阻塞线程，直到ansible_client.get_playbook_result()返回结果

        if not ansible_result:
            # 更新数据库的状态为failed
            task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp()), # 当前时间
            task_info.state = "failed"
            task_info.detail = ""
            update_task_state(task_info)
            raise Exception("Ansible kubernetes deployment failed")
        # 获取集群的kube_config
        kube_config = get_cluster_kubeconfig(cluster)
        # 更新集群状态为running
        with Session(get_engine()) as session:
            db_cluster = session.get(cluster, cluster.id)
            db_cluster.status = 'running'
            db_cluster.kube_config = kube_config
            session.commit()

        # 更新集群node的状态为running
        # session = get_session()
        # for node in node_list:
        #     with session.begin():
        #         db_node = session.get(NodeInfo, node.id)
        #         for k,v in hosts_data["_meta"]["hostvars"].items():
        #             if db_node.name == k:
        #                 db_node.server_id = v.get("id")
        #                 db_node.status = "running"
        #                 db_node.admin_address = v.get("ip")
        #                 db_node.floating_ip = v.get("public_ipv4")
        #                 for instance in instance_list:
        #                     if db_node.name == instance.name:
        #                         db_node.instance_id = instance.id
        #                         break

        # 更新集群instance的状态为running
        # session = get_session()
        # for instance in instance_list:
        #     with session.begin():
        #         db_instance = session.get(Instance, instance.id)
        #         for k,v in hosts_data["_meta"]["hostvars"].items():
        #             # 需要添加节点的ip地址等信息
        #             if  db_instance.name == k:
        #                 db_instance.server_id = v.get("id")
        #                 db_instance.status = "running"
        #                 db_instance.ip_address = v.get("ip")
        #                 db_instance.floating_ip = v.get("public_ipv4")

        # 更新数据库的状态为success
        task_info.end_time = time.time()
        task_info.state = "success"
        task_info.detail = ""
        update_task_state(task_info)
    except Exception as e:
        # 发生错误时更新集群状态为"失败"
          # 发生错误时更新集群状态为failed
        db_cluster = ClusterSQL.list_cluster(cluster_dict["id"])
        db_cluster.status = 'failed'
        db_cluster.error_message = str(e.__str__())
        ClusterSQL.update_cluster(cluster_dict["id"])
        raise

def get_ips(cluster_tfvars, task_info, host_file):
    res = subprocess.run(["python3", host_file, "--list"], capture_output=True, text=True)
    if res.returncode != 0:
            #更新数据库的状态为failed
        task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        task_info.state = "failed"
        task_info.detail = str(res.stderr)
        update_task_state(task_info)
        raise Exception("Error generating Ansible inventory")
    hosts = res.stdout
        # todo 添加节点时，需要将节点信息写入到inventory/inventory.yaml文件中
        # 如果是密码登录与master节点1做免密
    hosts_data = json.loads(hosts)
        # 从_meta.hostvars中获取master节点的IP
    master_node_name = cluster_tfvars.cluster_name+"-k8s-master-1"
    master_ip = hosts_data["_meta"]["hostvars"][master_node_name]["access_ip_v4"]
    lb_ip = hosts_data["_meta"]["hostvars"][master_node_name]["lb_ip"]
    return master_ip,lb_ip


@celery_app.task(bind=True)
def delete_cluster(self, cluster_id):
    #进入到terraform目录
    cluster_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", cluster_id)
    terraform_dir = os.path.join(cluster_dir, "terraform")
    os.chdir(terraform_dir)
    # 删除集群
    os.environ['OS_CLOUD']="shangdi"
    res = subprocess.run(["terraform", "destroy", "-auto-approve","-var-file=output.tfvars.json"], capture_output=True)
    if res.returncode != 0:
        # 发生错误时更新任务状态为"失败"

        print(f"Terraform error: {res.stderr}")
        return False
    else:
        # 更新任务状态为"成功"

        print("Terraform destroy succeeded")
    pass
    
@celery_app.task(bind=True)
def delete_node(self, cluster_id, node_list, instance_list_db, extravars):
    try:
        # 1、在这里先找到cluster的文件夹，找到对应的目录，先通过发来的node_list组合成extravars的变量，再执行remove-node.yaml
        ansible_dir = os.path.join(WORK_DIR, "ansible-deploy")
        os.chdir(ansible_dir)
        host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id), "hosts")
        playbook_file = os.path.join(WORK_DIR, "ansible-deploy", "remove-node.yml")
        run_playbook(playbook_file, host_file, ansible_dir, extravars)

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
            db_cluster = session.get(Cluster, cluster_id)
            db_cluster.status = 'running'
        NodeSQL.delete_node_list(node_list)
        InstanceSQL.delete_instance_list(instance_list_db)

    except subprocess.CalledProcessError as e:
        print(f"Ansible error: {e}")
        return False

@celery_app.task(bind=True)
def create_instance(self, instance: InstanceCreateObject, instance_list):
    try:
        # 1、拿到openstack的信息，就可以执行创建instance的流程，需要分别处理类型是vm还是裸金属的
        conn = openstack.connect(
            auth_url=instance.openstack_info.openstack_auth_url,
            project_name=instance.openstack_info.project_name,
            username=instance.openstack_info.openstack_username,
            password=instance.openstack_info.openstack_password,
            user_domain_name=instance.openstack_info.user_domain_name,
            project_domain_name=instance.openstack_info.project_domain_name,
            region_name=instance.openstack_info.region
        )
        if instance.node_type == "vm":
            server_id_list = create_vm_instance(conn, instance, instance_list)
        else:
            server_id_list = create_bm_instance(conn, instance, instance_list)

        # 2、判断server的状态，如果都成功就将instance的信息写入数据库中的表中
        server_id_active = []
        session = get_session()
        while len(server_id_active) < len(server_id_list):
            for server_id in server_id_list:
                if server_id in server_id_active:
                    continue
                server = conn.get_server(server_id)
                if server.status == "ACTIVE":
                    # 写入数据库中
                    for instance in instance_list:
                        if instance.name == server.name:
                            with session.begin():
                                db_instance = session.get(Instance, instance.id)
                                db_instance.server_id = server.id
                                db_instance.status = server.status
                                db_instance.ip_address = server.private_v4
                                db_instance.floating_ip = server.public_v4
                    server_id_active.append(server_id)
            time.sleep(5)
    except Exception as e:
        print(f"create instance error: {e}")
        raise ValueError(e)

@celery_app.task(bind=True)
def delete_instance(self, openstack_info, instance_list):
    try:
        # 1、拿到openstack的信息，就可以执行删除instance的流程，需要分别处理类型是vm还是裸金属的
        conn = openstack.connect(
            auth_url=openstack_info.openstack_auth_url,
            project_name=openstack_info.project_name,
            username=openstack_info.openstack_username,
            password=openstack_info.openstack_password,
            user_domain_name=openstack_info.user_domain_name,
            project_domain_name=openstack_info.project_domain_name,
            region_name=openstack_info.region
        )
        # 2、将instance的信息在数据库中的表中删除
        server_list = delete_vm_instance(conn, instance_list)
        session = get_session()
        for server in server_list:
            with session.begin():
                db_instance = session.get(Instance, server)
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