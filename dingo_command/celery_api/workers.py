
from datetime import datetime
import json
import os
import subprocess
import time
from typing import Dict, Optional
from dingo_command.api.model.cluster import ClusterObject
from dingo_command.api.model.instance import InstanceCreateObject
from dingo_command.celery_api.ansible import run_playbook
from dingo_command.celery_api.util import update_task_state
from dingo_command.services.cluster import TaskService
from dingo_command.db.models.cluster.models import Cluster,Taskinfo
from dingo_command.db.models.node.models import NodeInfo
from dingo_command.db.models.instance.models import Instance
from pydantic import BaseModel, Field
import openstack
from requests import Session
from dingo_command.celery_api.celery_app import celery_app
from dingo_command.celery_api import CONF
from dingo_command.db.engines.mysql import get_engine, get_session
from dingo_command.db.models.cluster.sql import ClusterSQL, TaskSQL

from dingo_command.db.models.node.sql import NodeSQL
from dingo_command.db.models.instance.sql import InstanceSQL
from dingo_command.api.model.instance import OpenStackConfigObject

from jinja2 import Environment, FileSystemLoader

BASE_DIR = os.getcwd()
TERRAFORM_DIR = os.path.join(BASE_DIR, "dingo_command", "templates", "terraform")
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
    private_key_path: Optional[str] = Field(None, description="私钥路径")
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
            cluster.private_key_path = os.path.join(cluster_dir, "id_rsa")
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
        
        key_file_path = os.path.join(WORK_DIR, "ansible-deploy", "inventory",str(cluster.id), "id_rsa")
        with open(key_file_path, 'r') as key_file:
            private_key_content = key_file.read()
        query_params = {}
        query_params["id"] = cluster.id
        count, data = ClusterSQL.list_cluster(query_params)
        if count > 0:
            db_cluster = data[0]
            host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory",cluster.id, "hosts")
             # Give execute permissions to the host file
            os.chmod(host_file, 0o755) 
            network_id,bus_network_id, subnet_id,bussubnet_id = get_networks(cluster, task_info, host_file)
            db_cluster.admin_network_id = network_id
            db_cluster.admin_subnet_id = subnet_id
            db_cluster.bus_network_id = bus_network_id
            db_cluster.bus_subnet_id = bussubnet_id
            db_cluster.private_key = private_key_content
            ClusterSQL.update_cluster(db_cluster)
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
def create_cluster(self, cluster_tf:ClusterTFVarsObject,cluster_dict:ClusterObject, instance_bm_list):
    try:
        task_id = self.request.id.__str__()
        print(f"Task ID: {task_id}")
        cluster_tfvars = ClusterTFVarsObject(**cluster_tf)
        cluster = ClusterObject(**cluster_dict)
        
        instance_list = json.loads(instance_bm_list)
        instructure_task = Taskinfo(task_id=task_id, cluster_id=cluster_tf["id"], state="progress", start_time=datetime.fromtimestamp(datetime.now().timestamp()),msg=TaskService.TaskMessage.instructure_create.name)
        TaskSQL.insert(instructure_task)
        
        terraform_result = create_infrastructure(cluster_tfvars,instructure_task, cluster.region_name)
        
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
                        db_instance.ip_address = v.get("ip")
                        db_instance.floating_ip = v.get("public_ipv4")
        query_params = {}
        query_params["id"] = cluster_tf["id"]
        count,db_clusters = ClusterSQL.list_cluster(query_params)
        db_cluster = db_clusters[0]
        db_cluster.status = 'success'
        db_cluster.status_msg = ""
        ClusterSQL.update_cluster(db_cluster)
    except Exception as e:
        # 发生错误时更新集群状态为"失败"
        query_params = {}
        query_params["id"] = cluster_tf["id"]
        count,db_clusters = ClusterSQL.list_cluster(query_params)
        db_cluster = db_clusters[0]
        db_cluster.status = 'failed'
        db_cluster.status_msg = str(e.__str__())
        ClusterSQL.update_cluster(db_cluster)
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
        key_file_path = os.path.join(WORK_DIR, "ansible-deploy", "inventory",str(cluster.id), "id_rsa")
        with open(key_file_path, 'r') as key_file:
            private_key_content = key_file.read()
        
        
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

    
def get_cluster_kubeconfig(cluster:ClusterTFVarsObject, lb_ip,master_ip, float_ip):
    """获取集群的kubeconfig配置"""

    print(f"lb_ip: {lb_ip}, master_ip: {master_ip}, float_ip: {float_ip}")
    try:

        kubeconfig = ""
        # SSH连接到master节点获取kubeconfig
        if cluster.password != "":
            
            result = subprocess.run(
                [
                    "ssh",
                    f"{cluster.ssh_user}@{float_ip}",
                    "sudo cat /etc/kubernetes/admin.conf"
                ],
                capture_output=True,
                text=True,
                check=True
            )
            kubeconfig = result.stdout
        else:
            key_file_path = os.path.join(WORK_DIR, "ansible-deploy", "inventory",str(cluster.id), "id_rsa")
            result = subprocess.run(
                [
                    "ssh",
                    "-i", key_file_path,  # SSH私钥路径
                    f"{cluster.ssh_user}@{float_ip}",
                    "sudo cat /etc/kubernetes/admin.conf"
                ],
                capture_output=True,
                text=True,
                check=True
            )
            kubeconfig = result.stdout
        
        # 替换server地址为外部IP
        ip = "127.0.0.1"
        if lb_ip != "":
            ip = lb_ip
        elif master_ip != "":
            ip = master_ip
        
        kubeconfig = kubeconfig.replace(
            "server: https://127.0.0.1:6443",
            f"server: https://{ip}:6443"
        )
            
        return kubeconfig
        
    except subprocess.CalledProcessError as e:
        print(f"Error getting kubeconfig: {e}")
        return None

def delete_vm_instance(conn, instance_list):
    # 在这里使用openstack的api接口，直接删除vm或bm
    server_list = []
    for instance in instance_list:
        server = conn.compute.find_server(instance.get("server_id"))
        conn.compute.delete_server(server)
        conn.compute.wait_for_delete(server, wait=TIMEOUT)
        server_list.append(instance.get("id"))
    return server_list

def create_vm_instance(conn, instance_info: InstanceCreateObject, instance_list):
    # 在这里使用openstack的api接口，直接创建vm
    server_list = []
    for ins in instance_list:
        server = conn.create_server(
            name=ins.get("name"),
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
            name=ins.get("name"),
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
def create_k8s_cluster(self, cluster_tf_dict, cluster_dict, node_list, instance_list, scale=False):

    try:
        task_id = self.request.id.__str__()
        print(f"Task ID: {task_id}")
        cluster_tfvars = ClusterTFVarsObject(**cluster_tf_dict)
        cluster = ClusterObject(**cluster_dict)
        node_list = json.loads(node_list)
        instance_list = json.loads(instance_list)
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

        if cluster_tfvars.password != "":
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
        master_node_name = cluster_tfvars.cluster_name+"-k8s-master-1"
        master_ip = hosts_data["_meta"]["hostvars"][master_node_name]["ip"]
        float_ip = hosts_data["_meta"]["hostvars"][master_node_name]["access_ip_v4"]

        # 2. 使用Ansible部署K8s集群
        cluster.id = cluster_tf_dict["id"]

        if scale:
            ansible_result = scale_kubernetes(cluster)
        else:
            ansible_result = deploy_kubernetes(cluster,lb_ip,task_id)
        if not ansible_result:
            raise Exception("Ansible kubernetes deployment failed")
        #阻塞线程，直到ansible_client.get_playbook_result()返回结果
        # 获取集群的kube_config
        kube_config = get_cluster_kubeconfig(cluster,lb_ip,master_ip,float_ip)
        # 更新集群状态为running
        count, db_cluster = ClusterSQL.list_cluster(cluster_dict["id"])
        db_cluster.kube_config = kube_config
        db_cluster.status = 'error'
        db_cluster.error_message = str(e.__str__())
        ClusterSQL.update_cluster(db_cluster)

        # 更新集群node的状态为running
        session = get_session()
        with session.begin():
            for node in node_list:
                db_node = session.get(NodeInfo, node.get("id"))
                for k,v in hosts_data["_meta"]["hostvars"].items():
                    if db_node.name == k:
                        db_node.server_id = v.get("id")
                        db_node.status = "running"
                        db_node.admin_address = v.get("ip")
                        db_node.floating_ip = v.get("public_ipv4")
                        for instance in instance_list:
                            if db_node.name == instance.name:
                                db_node.instance_id = instance.id
                                break

        # 更新集群instance的状态为running

        with session.begin():
            for instance in instance_list:
                db_instance = session.get(Instance, instance.get("id"))
                for k,v in hosts_data["_meta"]["hostvars"].items():
                    # 需要添加节点的ip地址等信息
                    if  db_instance.name == k:
                        db_instance.server_id = v.get("id")
                        db_instance.status = "running"
                        db_instance.ip_address = v.get("ip")
                        db_instance.floating_ip = v.get("public_ipv4")

        # 更新数据库的状态为success
        task_info.end_time = time.time()
        task_info.state = "success"
        task_info.detail = ""
        update_task_state(task_info)
    except Exception as e:
        # 发生错误时更新集群状态为"失败"
          # 发生错误时更新集群状态为failed
        count, db_clusters = ClusterSQL.list_cluster(cluster_dict["id"])
        c = db_clusters[0]
        c.state = 'error'
        c.error_message = str(e.__str__())
        ClusterSQL.update_cluster(c)
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
    hosts_data = json.loads(hosts)
        # 从_meta.hostvars中获取master节点的IP
    master_node_name = cluster_tfvars.cluster_name+"-k8s-master-1"
    master_ip = hosts_data["_meta"]["hostvars"][master_node_name]["access_ip_v4"]
    lb_ip = hosts_data["_meta"]["hostvars"][master_node_name]["lb_ip"]
    return master_ip,lb_ip

def get_networks(cluster_tfvars, task_info, host_file):
    res = subprocess.run(["python3", host_file, "--list"], capture_output=True, text=True)
    if res.returncode != 0:
            #更新数据库的状态为failed
        task_info.end_time = datetime.fromtimestamp(datetime.now().timestamp())
        task_info.state = "failed"
        task_info.detail = str(res.stderr)
        update_task_state(task_info)
        raise Exception("Error generating Ansible inventory")
    hosts = res.stdout
    hosts_data = json.loads(hosts)
        # 从_meta.hostvars中获取master节点的IP
    master_node_name = cluster_tfvars.cluster_name+"-k8s-master-1"
    bus_network_id = ""
    network_id = hosts_data["_meta"]["hostvars"][master_node_name]["network"][0]['uuid']
    if  hosts_data["_meta"]["hostvars"][master_node_name]["network"].__len__() > 1:       
        bus_network_id = hosts_data["_meta"]["hostvars"][master_node_name]["network"][1]['uuid']
    subnet_id = hosts_data["_meta"]["hostvars"][master_node_name]["subnet_id"]
    bussubnet_id = hosts_data["_meta"]["hostvars"][master_node_name]["bussubnet_id"]
    return network_id,bus_network_id, subnet_id,bussubnet_id


@celery_app.task(bind=True)
def delete_cluster(self, cluster_id, region_name):
    #进入到terraform目录
    cluster_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", cluster_id)
    terraform_dir = os.path.join(cluster_dir, "terraform")
    print(f"Terraform dir: {terraform_dir}")
    print(f"Terraform dir: {region_name}")
    
    os.chdir(terraform_dir)
    # 删除集群
    os.environ['OS_CLOUD']=region_name
    res = subprocess.run(["terraform", "destroy", "-auto-approve","-var-file=output.tfvars.json"], capture_output=True)
    if res.returncode != 0:
        # 发生错误时更新任务状态为"失败"

        print(f"Terraform error: {res.stderr}")
        count, db_clusters = ClusterSQL.list_cluster(cluster_id)
        c = db_clusters[0]
        c.state = 'delete_error'
        c.error_message = "delete cluster error"
        ClusterSQL.update_cluster(c)
        return False
    else:
        # 更新任务状态为"成功"
        count, db_clusters = ClusterSQL.list_cluster(cluster_id)
        c = db_clusters[0]
        c.state = 'deleted'
        c.error_message = ""
        ClusterSQL.update_cluster(c)
        print("Terraform destroy succeeded")
    
@celery_app.task(bind=True)
def delete_node(self, cluster_id, node_list, instance_list_db, extravars):
    try:
        # 1、在这里先找到cluster的文件夹，找到对应的目录，先通过发来的node_list组合成extravars的变量，再执行remove-node.yaml
        ansible_dir = os.path.join(WORK_DIR, "ansible-deploy")
        os.chdir(ansible_dir)
        host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id), "hosts")
        playbook_file = os.path.join(WORK_DIR, "ansible-deploy", "remove-node.yml")
        run_playbook(playbook_file, host_file, ansible_dir, extravars)
        node_list = json.loads(node_list)
        instance_list = json.loads(instance_list_db)

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
            # 根据 node.id 删除节点
            for node in node_list:
                node = session.get(NodeSQL, node.get("id"))  # 假设 NodeSQL 是 ORM 模型类
                if node:
                    session.delete(node)

            # 根据 instance.id 删除实例
            for instance in instance_list:
                instance = session.get(InstanceSQL, instance.get("id"))  # 假设 InstanceSQL 是 ORM 模型类
                instance.status = "running"
                instance.cluster_id = ""
                instance.cluster_name = ""

    except subprocess.CalledProcessError as e:
        print(f"Ansible error: {e}")
        return False

@celery_app.task(bind=True)
def create_instance(self, instance, instance_list):
    try:
        instance = InstanceCreateObject(**instance)
        instance_list = json.loads(instance_list)
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
                        if instance.get("name") == server.name:
                            with session.begin():
                                db_instance = session.get(Instance, instance.get("id"))
                                db_instance.server_id = server.id
                                db_instance.status = server.status
                                db_instance.ip_address = server.interface_ip
                    server_id_active.append(server_id)
            time.sleep(5)
    except Exception as e:
        print(f"create instance error: {e}")
        raise ValueError(e)

@celery_app.task(bind=True)
def delete_instance(self, openstack_info, instance_list):
    try:
        instance_list = json.loads(instance_list)
        openstack_info = OpenStackConfigObject(**openstack_info)
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
        with session.begin():
            for server in server_list:
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