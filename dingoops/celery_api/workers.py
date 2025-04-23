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
from dingoops.celery_api.ansible import run_playbook
from dingoops.celery_api.util import update_task_state
from dingoops.db.models.cluster.models import Cluster,Taskinfo
from dingoops.db.models.node.models import NodeInfo
from pydantic import BaseModel, Field
from fastapi import Path
from pathlib import Path as PathLib
from requests import Session
from dingoops.celery_api.celery_app import celery_app
from dingoops.celery_api import CONF
from dingoops.db.engines.mysql import get_engine, get_session
from dingoops.db.models.cluster.sql import ClusterSQL, TaskSQL
from dingoops.db.models.node.sql import NodeSQL
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


class NodeGroup(BaseModel):
    az: Optional[str] = Field(None, description="可用域")
    flavor: Optional[str] = Field(None, description="规格")
    floating_ip: Optional[bool] = Field(None, description="浮动ip")
    etcd: Optional[bool] = Field(None, description="是否是etcd节点")

class ClusterTFVarsObject(BaseModel):
    id: Optional[str] = Field(None, description="项目id")
    cluster_name: Optional[str] = Field(None, description="集群名称")   
    image: Optional[str] = Field(None, description="用户id")
    k8s_masters: Optional[Dict[str, NodeGroup]] = Field(None, description="集群标签")
    k8s_nodes: Optional[Dict[str, NodeGroup]] = Field(None, description="集群状态")
    admin_subnet_id: Optional[str] = Field(None, description="管理子网id")
    bus_network_id: Optional[str] = Field(None, description="业务网络id")
    admin_network_id: Optional[str] = Field(None, description="管理网id")
    bus_subnet_id: Optional[str] = Field(None, description="业务子网id")
    floatingip_pool: Optional[str] = Field(None, description="节点配置")
    subnet_cidr: Optional[str] = Field(None, description="运行时类型")
    use_existing_network: Optional[bool] = Field(None, description="是否使用已有网络")
    external_net: Optional[str] = Field(None, description="外部网络id")
    group_vars_path:  Optional[str] = Field(None, description="集群变量路径")
    number_of_etcd: Optional[int] = Field(None, description="ETCD节点数量")
    number_of_k8s_masters: Optional[int] = Field(None, description="K8s master节点数量")
    number_of_k8s_masters_no_etcd: Optional[int] = Field(None, description="不带ETCD的K8s master节点数量")
    number_of_k8s_masters_no_floating_ip: Optional[int] = Field(None, description="无浮动IP的K8s master节点数量")
    number_of_k8s_masters_no_floating_ip_no_etcd: Optional[int] = Field(None, description="无浮动IP且不带ETCD的K8s master节点数量")
    number_of_k8s_nodes: Optional[int] = Field(None, description="K8s worker节点数量")
    number_of_k8s_nodes_no_floating_ip: Optional[int] = Field(None, description="无浮动IP的K8s worker节点数量")
    ssh_user: Optional[str] = Field(None, description="用户名")
    password: Optional[str] = Field(None, description="密码")
    k8s_master_loadbalancer_enabled: Optional[bool] = Field(None, description="是否启用负载均衡器")
    
    
def create_infrastructure(cluster:ClusterTFVarsObject, task_info:Taskinfo):
    """使用Terraform创建基础设施"""
    try:
        
        # 将templat下的terraform目录复制到WORK_DIR/cluster.id目录下
        cluster_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id))
        dd = subprocess.run(["cp", "-LRpf", os.path.join(WORK_DIR, "ansible-deploy", "inventory","sample-inventory"), str(cluster_dir)], capture_output=True)

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
        
        cluster.group_vars_path = os.path.join(cluster_dir, "group_vars")
   
        tfvars_str = json.dumps(cluster, default=lambda o: o.__dict__, indent=2)
        with open("output.tfvars.json", "w") as f:
            f.write(tfvars_str)
       
        # 执行terraform apply
        # os.environ['OS_CLOUD']=cluster.region_name
        os.environ['OS_CLOUD']="dingzhi"
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

# def wait_for_ansible_result(task_id: str, timeout: int = 3600, interval: int = 5) -> Optional[Dict[str, Any]]:

#     start_time = time.time()
#     logging.info(f"等待Ansible任务 {task_id} 完成...")
    
#     while True:
#         # 检查是否超时
#         if time.time() - start_time > timeout:
#             logging.error(f"等待Ansible任务 {task_id} 结果超时")
#             return None
        
#         try:
#             # 获取任务结果
#             result = ansible_client.get_playbook_result(task_id)
            
#             # 检查任务是否完成且成功
#             if result and result.get('status') == 'SUCCESS':
#                 logging.info(f"Ansible任务 {task_id} 执行成功")
#                 return result
#             elif result and result.get('status') in ['FAILED', 'ERROR']:
#                 logging.error(f"Ansible任务 {task_id} 执行失败: {result}")
#                 return None
                
#             # 任务仍在运行，继续等待
#             logging.debug(f"Ansible任务 {task_id} 仍在执行中，继续等待...")
            
#         except Exception as e:
#             logging.warning(f"获取Ansible任务 {task_id} 结果时出错: {str(e)}，将继续尝试")
        
#         # 等待一段时间再次检查
#         time.sleep(interval)

def deploy_kubernetes(cluster:ClusterObject):
    """使用Ansible部署K8s集群"""
    try:
        # #替换
        # # 定义上下文字典，包含所有要替换的变量值
        context = {
            'kube_version': cluster.version,
            'kube_network_plugin': cluster.network_config.cni,
            'service_cidr': cluster.network_config.service_cidr,
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
        ansible_dir = os.path.join(WORK_DIR, "ansible-deploy")
        os.chdir(ansible_dir)
        host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster.id), "hosts")
        playbook_file  = os.path.join(WORK_DIR, "ansible-deploy", "cluster.yml")
        run_playbook(playbook_file, host_file, ansible_dir)
        
    except subprocess.CalledProcessError as e:
        print(f"Ansible error: {e}")
        return False


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
    
def get_cluster_kubeconfig(cluster):
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
            f"server: https://{master_ip}:6443"
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
    
@celery_app.task(bind=True)
def create_cluster(self, cluster_tf_dict, cluster_dict, node_list, scale=False):
    try:
        #task_id = self.request.id.__str__()
        task_id = "da"
        print(f"Task ID: {task_id}")
        cluster_tfvars = ClusterTFVarsObject(**cluster_tf_dict)
        cluster = ClusterObject(**cluster_dict)
        # 1. 使用Terraform创建基础设施
         # 将task_info存入数据库
        task_info = Taskinfo(task_id=task_id, cluster_id=cluster_tf_dict["id"], state="progress", start_time=datetime.fromtimestamp(datetime.now().timestamp()),msg="instructure_base")
        TaskSQL.insert(task_info)
        terraform_result = create_infrastructure(cluster_tfvars,task_info)
        
        if not terraform_result:
            raise Exception("Terraform infrastructure creation failed")
        # 打印日志
        print("Terraform infrastructure creation succeeded")
        # 根据生成inventory
        # 复制script下面的host文件到WORK_DIR/cluster.id目录下
        #执行python3 host --list，将生成的内容转换为yaml格式写入到inventory/inventory.yaml文件中
         # 将task_info存入数据库
        task_info = Taskinfo(task_id=task_id, cluster_id=cluster_tf_dict["id"], state="progress", start_time=datetime.fromtimestamp(datetime.now().timestamp()),msg="instructure_chack")
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
        if res.returncode != 0:
            # Keep trying to connect to all nodes until successful
            max_attempts = 12  # Try for up to 1 minute (12 * 5 seconds)
            attempt = 1
            start_time = time.time()
            timeout = 1800  # 30 minutes in seconds
            while True:
                if time.time() - start_time > timeout:
                    raise Exception("Operation timed out after 30 minutes. Terminating execution.")
                print(f"Attempting to connect to all nodes with Ansible (attempt {attempt}/{max_attempts})...")
                res = subprocess.run([
                    "ansible",
                    "-i", "inventory/hosts",
                    "-m", "ping",
                    "all"
                ], capture_output=True)
                
                if res.returncode == 0:
                    print("Successfully connected to all nodes")
                    break
                
                attempt += 1
                if attempt > max_attempts:
                    raise Exception(f"Failed to connect to all nodes with Ansible ping after {max_attempts} attempts")
                
                print(f"Connection attempt failed. Waiting 5 seconds before retrying...")
                time.sleep(5)
                # Add timeout check - terminate after 30 minutes
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
        task_info = Taskinfo(task_id=task_id, cluster_id=cluster_tf_dict["id"], state="progress", start_time=datetime.fromtimestamp(datetime.now().timestamp()), msg="k8s_deploy")
        update_task_state(task_info)
        cluster.id = cluster_tf_dict["id"]
        if scale:
            ansible_result = scale_kubernetes(cluster)
        else:
            ansible_result = deploy_kubernetes(cluster)
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
        session = get_session()
        with session.begin():
            for node in node_list:
                db_node = session.get(NodeInfo, node.id)
                for k,v in hosts_data["_meta"]["hostvars"].items():
                    # 需要添加节点的ip地址等信息
                    if  db_node.name == k:
                        db_node.status = "running"
                        db_node.admin_address = v.get("ip")
                        db_node.floating_ip = v.get("public_ipv4")

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
def delete_node(self, cluster_id, node_list, extravars):
    try:
        # 1、在这里先找到cluster的文件夹，找到对应的目录，先通过发来的node_list组合成extravars的变量，再执行remove-node.yaml
        ansible_dir = os.path.join(WORK_DIR, "ansible-deploy")
        os.chdir(ansible_dir)
        host_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id), "hosts")
        playbook_file = os.path.join(WORK_DIR, "ansible-deploy", "remove-node.yml")
        run_playbook(playbook_file, host_file, ansible_dir, extravars)

        # 2、执行完删除k8s这些节点之后，再执行terraform销毁这些节点（这里是单独修改output.json文件还是需要通过之前生成的output.json文件生成）
        output_file = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id),
                                   "terraform", "output.tfvars.json")
        with open(output_file) as f:
            content = json.loads(f.read())
            content_new = copy.deepcopy(content)
            for node in content["k8s_nodes"]:
                if node in extravars.keys():
                    del content_new["k8s_nodes"][node]
        with open(output_file, "w") as f:
            json.dump(content_new, f, indent=4)

        # 执行terraform apply
        cluster_dir = os.path.join(WORK_DIR, "ansible-deploy", "inventory", str(cluster_id))
        os.environ['CURRENT_CLUSTER_DIR'] = cluster_dir
        terraform_dir = os.path.join(cluster_dir, "terraform")
        os.chdir(terraform_dir)
        # os.environ['OS_CLOUD']=cluster.region_name
        os.environ['OS_CLOUD'] = "dingzhi"
        res = subprocess.run([
            "terraform",
            "apply",
            "-auto-approve",
            "-var-file=output.tfvars.json"
        ], capture_output=True, text=True)

        # 3、然后需要更新node节点的数据库的信息和集群的数据库信息
        # 更新集群cluster的状态为running，删除缩容节点的数据库信息
        session = get_session()
        with session.begin():
            db_cluster = session.get(Cluster, cluster_id)
            db_cluster.status = 'running'
        NodeSQL.delete_node_list(node_list)

    except subprocess.CalledProcessError as e:
        print(f"Ansible error: {e}")
        return False

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