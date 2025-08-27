import unittest
from unittest.mock import patch, MagicMock
from dingo_command.celery_api.workers import create_cluster, delete_cluster,create_k8s_cluster,add_existing_nodes 
from dingo_command.common.nova_client import NovaClient

class TestCreateCluster(unittest.TestCase):
  def setUp(self):
    # Setup test data
    # self.cluster_tf_dict = {
    #   'id': 'fsdfds410-1a8f-4862-a646-32d8845612f4',
    #   'cluster_name': 'dsy3',
    #   'image': 'ubuntu-2204-dsy',
    #   'k8s_masters': {'master1': {'flavor': '1', 'etcd': True, 'floating_ip': True,'user': 'root', 'password': 'daz3502'}},
    #   'k8s_nodes': {'worker1': {'flavor': '1','floating_ip': False,'etcd': False,'user': 'root', 'password': 'daz3502'}, 'worker2': {'flavor': '1','floating_ip': True,'etcd': False,'user': 'root', 'password': 'daz3502'}},
    #   'admin_subnet_id': 'c8b2c4df-7745-4028-acbd-333bc450a5be',
    #   'admin_network_id': '4700f790-0a34-4ca2-a53d-f1438568f8ff',
    #   'bus_network_id': 'f0f21356-858d-4c1e-b58b-71238bc3c23c',
    #   'bus_subnet_id': '438b7357-6a9a-4d93-993d-f73ce2a5d803',
    #   'auth_type': 'key', 
    #   'ssh_user': 'root', 
    #   'password': 'daz3502',
    #   'use_existing_network': True,
    #   'external_net': 'a88e60f1-6bd1-4846-8b96-cbd309c1ebd4',
    #   'floatingip_pool': 'physnet2',
    #   "loadbalancer_enabled": True,
    #   "number_of_etcd": 0,

    #   "number_of_k8s_masters": 0,

    #   "number_of_k8s_masters_no_etcd": 0,

    #   "number_of_k8s_masters_no_floating_ip": 0,

    #   "number_of_k8s_masters_no_floating_ip_no_etcd": 0,
    #   "number_of_k8s_nodes": 0,

    #   "number_of_k8s_nodes_no_floating_ip": 0
    # }
    
    # self.cluster_dict = {
    # "name": "dsy1",
    # "description": "dedadasdasd",
    # "region_name": "regionOne",
    # "network_config": {
    #     "cni": "calico",
    #     "pod_cidr": "10.0.0.0/24",
    #     "admin_subnet_id": "c8b2c4df-7745-4028-acbd-333bc450a5be",
    #     "bus_subnet_id": "438b7357-6a9a-4d93-993d-f73ce2a5d803",
    #     "admin_network_id": "4700f790-0a34-4ca2-a53d-f1438568f8ff",
    #     "bus_network_id": "f0f21356-858d-4c1e-b58b-71238bc3c23c",
    #     "service_cidr": "10.233.0.0/18"
    # },
    # "node_config": [
    #     {
    #         "count": 1,
    #         "image": "ubuntu-2204-dsy",
    #         "flavor_id": "1",
    #         "password": "daz3502",
    #         "auth_type": "password",
    #         "role": "master",
    #         "type": "vm"
    #     },
    #     {
    #         "count": 2,
    #         "image": "ubuntu-2204-dsy",
    #         "flavor_id": "1",
    #         "user": "root",
    #         "password": "daz3502",
    #         "auth_type": "pass",
    #         "role": "worker",
    #         "type": "vm"
    #     }
    # ],
    # "runtime": "containerd",
    # "type": "1",
    # "version": "v1.32.0",
    # "cni": "calico"
    # }
    # self.cluster_tf_dict = {
    #   'id': 'b4eaf586-8d4f-4dfa-8e9f-bc1129007033',
    #   'cluster_name': 'dsy5',
    #   'image': 'ubuntu2204-dsy',
    #   'k8s_masters': {'master1': {'flavor': 'a0ee8641-fcb0-486e-9251-db9a4cf81225', 'etcd': True, 'floating_ip': True,'user': 'root', 'password': 'daz3502'}},
    #   'k8s_nodes': {'worker1': {'flavor': 'a0ee8641-fcb0-486e-9251-db9a4cf81225','floating_ip': False,'etcd': False,'user': 'root', 'password': 'daz3502'}, 'worker2': {'flavor': 'a0ee8641-fcb0-486e-9251-db9a4cf81225','floating_ip': False,'etcd': False,'user': 'root', 'password': 'daz3502'}},
    #   'admin_subnet_id': 'a5d2a291-429f-4e8c-8665-3cbaaa643b70',
    #   'admin_network_id': 'a87fca1a-d0fe-42fe-99c9-15e396ab8539',
    #   'bus_network_id': '',
    #   'bus_subnet_id': '',
    #   'auth_type': 'key', 
    #   'ssh_user': 'root', 
    #   'password': 'daz3502',
    #   'use_existing_network': True,
    #   'external_net': 'd3e17b8a-80d3-4375-9148-615a50240005',
    #   'floatingip_pool': 'physnet1-vlan806',
    #   "k8s_master_loadbalancer_enabled": True,
    #   "number_of_etcd": 0,

    #   "number_of_k8s_masters": 0,

    #   "number_of_k8s_masters_no_etcd": 0,

    #   "number_of_k8s_masters_no_floating_ip": 0,

    #   "number_of_k8s_masters_no_floating_ip_no_etcd": 0,
    #   "number_of_k8s_nodes": 0,

    #   "number_of_k8s_nodes_no_floating_ip": 0
    # }
    
    # self.cluster_dict = {
    # "name": "dsy5",
    # "description": "dedadasdasd",
    # "region_name": "regionOne",
    # "network_config": {
    #     "cni": "calico",
    #     "pod_cidr": "10.0.0.0/24",
    #     "admin_subnet_id": "a0ee8641-fcb0-486e-9251-db9a4cf81225",
    #     "bus_subnet_id": "",
    #     "admin_network_id": "a0ee8641-fcb0-486e-9251-db9a4cf81225",
    #     "bus_network_id": "",
    #     "service_cidr": "10.233.0.0/18",
    #     "kube_proxy_mode":"ipvs"
    # },
    # "node_config": [
    #     {
    #         "count": 1,
    #         "image": "ubuntu2204-dsy",
    #         "flavor_id": "a0ee8641-fcb0-486e-9251-db9a4cf81225",
    #         "password": "daz3502",
    #         "auth_type": "password",
    #         "role": "master",
    #         "type": "vm"
    #     },
    #     {
    #         "count": 2,
    #         "image": "ubuntu2204-dsy",
    #         "flavor_id": "a0ee8641-fcb0-486e-9251-db9a4cf81225",
    #         "user": "root",
    #         "password": "daz3502",
    #         "auth_type": "pass",
    #         "role": "worker",
    #         "type": "vm"
    #     }
    # ],
    # "runtime": "containerd",
    # "type": "1",
    # "version": "v1.32.0",
    # "cni": "calico"
    # }
    self.cluster_tf_dict = {'id': '8457c2cd-2f2b-402d-a14f-69440e46b57a', 'cluster_name': 'dsy-131', 'image_uuid': '86f35962-2b4d-4d2f-9f63-a54eeb9dae97', 'nodes': {'node-1': {'az': 'nova', 'flavor': 'e320244e-66d3-45ac-9e07-52fe7e8b2ba8', 'floating_ip': False, 'etcd': False, 'image_id': '86f35962-2b4d-4d2f-9f63-a54eeb9dae97', 'port_forwards': [], 'use_local_disk': False, 'volume_type': '', 'volume_size': 0}}, 'admin_subnet_id': None, 'bus_network_id': None, 'admin_network_id': None, 'bus_subnet_id': None, 'ssh_user': 'ubuntu', 'password': '123456Aa?', 'floatingip_pool': 'physnet2', 'public_floatingip_pool': 'physnet1', 'external_subnetids': ['0da829d8-e8b5-4738-8a49-aa0aa0ba9728', 'ee6f9ba6-f420-41c4-8162-bf5b41bc43dc', '78608c52-0e59-4c4b-b113-64b41fc79a2d'], 'public_subnetids': ['0da829d8-e8b5-4738-8a49-aa0aa0ba9728', 'ee6f9ba6-f420-41c4-8162-bf5b41bc43dc', '78608c52-0e59-4c4b-b113-64b41fc79a2d'], 'subnet_cidr': '10.106.39.0/24', 'use_existing_network': False, 'external_net': 'a88e60f1-6bd1-4846-8b96-cbd309c1ebd4', 'group_vars_path': None, 'number_of_etcd': 0, 'number_of_k8s_masters': 1, 'number_of_k8s_masters_no_etcd': 0, 'number_of_k8s_masters_no_floating_ip': 0, 'number_of_k8s_masters_no_floating_ip_no_etcd': 0, 'number_of_k8s_nodes': 0, 'number_of_k8s_nodes_no_floating_ip': 0, 'k8s_master_loadbalancer_enabled': False, 'public_key_path': None, 'tenant_id': '2ef792461415449796e25ab9c438ca6f', 'auth_url': 'http://10.220.58.248:5000', 'token': 'gAAAAABopWlCLkZ1XfVF57Ng1WaUPm0EoiqQ1n-33f0KD-OZO8fBTzi5pVZhy6RT7j7GuLhZ4CF2HvOgw3SZMmGmk9RQZFnWP4o7z7DUUAoF8gPzxzUNMkH4hYrzARooMyMj_cYyXby5YeMCCGvDWV_xoUFD6q7tFuKjfidk2oHZOofRfjty8gxaqbuDfARBZ3NDKTk1RGRH', 'forward_float_ip_id': '', 'image_master': '86f35962-2b4d-4d2f-9f63-a54eeb9dae97', 'router_id': None, 'bastion_floatip_id': None, 'pushgateway_url': ''}
    self.cluster_dict = {'id': '8457c2cd-2f2b-402d-a14f-69440e46b57a', 'name': 'dsy-131', 'description': None, 'extra': None, 'created_at': None, 'updated_at': None, 'project_id': '2ef792461415449796e25ab9c438ca6f', 'user_id': 'ef81a343e6ce472e8d81a71954ed047a', 'labels': None, 'region_name': 'RegionOne', 'network_config': None, 'node_config': [{'count': 1, 'image': '86f35962-2b4d-4d2f-9f63-a54eeb9dae97', 'flavor_id': 'e320244e-66d3-45ac-9e07-52fe7e8b2ba8', 'key_id': None, 'user': 'ubuntu', 'password': '123456Aa?', 'auth_type': 'password', 'role': 'worker', 'type': 'vm', 'security_group': None, 'status': None, 'instance_id': None, 'use_local_disk': False, 'volume_type': '', 'volume_size': 0}], 'type': 'kubernetes', 'security_group': None, 'kube_info': {'kube_lb_address': None, 'kube_proxy_mode': 'ipvs', 'loadbalancer_enabled': False, 'runtime': 'containerd', 'version': 'v1.31.5', 'kube_config': None, 'service_cidr': '192.168.0.0/24', 'cni': 'calico', 'pod_cidr': None, 'number_master': 1}, 'status': None, 'cpu': 0, 'mem': 0, 'gpu': 0, 'gpu_mem': 0, 'node_count': 0, 'status_msg': None, 'private_key': None, 'forward_float_ip_id': '', 'forward_float_ip': '', 'port_forwards': []}
  def test_create_cluster_success(self):

    #调用celery_app项目下的work.py中的create_cluster方法
    # Test execution
    create_k8s_cluster(self.cluster_tf_dict, self.cluster_dict, [], [])

  def test_add_exist_node(self):
     # 通过server_ids查询虚拟机信息
    token = "gAAAAABokvuoZiKGvAMkOIz1UKV1W7a5XzEoqx2Zi_RqBao7m9x3hzaAhPSG35kiL3HbNGG3mjGsxPJkk3Dz49PBMlg2d6jBNJpcb_hm6AguNCcjn6B7BajfjGYD3b2oiroluAIuVxt62_rO-loiynCbmt37LwDe6pfjyfxe_Qru2hr5Dbbn7S1D7VbKph3qii1-sFdHDZWy"
    nova_client = NovaClient(token)
    server_details = []
    for server_id in ["b6ca55e7-812f-481c-8dda-5ad7253a2a8f"]:

      server_detail = nova_client.nova_get_server_detail(server_id)
      # 检查网络是否匹配

      server_details.append(server_detail)

    add_existing_nodes("9582f04f-0e53-4a46-accc-2a6126279ac8",server_details)
  
  def test_delete_cluster_success(self):
    #调用celery_app项目下的work.py中的create_cluster方法
    # Test execution
    delete_cluster("fsdfds410-1a8f-4862-a646-32d8845612f4")
  @patch('celery_api.workers.current_task')
  @patch('celery_api.workers.create_infrastructure')
  @patch('celery_api.workers.deploy_kubernetes')
  @patch('celery_api.workers.subprocess.run')
  @patch('celery_api.workers.Session')
  def test_create_cluster_terraform_failure(self, mock_session, mock_run, mock_deploy_k8s, 
                       mock_create_infra, mock_current_task):
    # Setup mocks to simulate Terraform failure
    mock_current_task.id = "task-123"
    mock_create_infra.return_value = False
    
    # Test execution and verify exception
    with self.assertRaises(Exception) as context:
      create_cluster(self.cluster_tf_dict, self.cluster_dict)
    
    self.assertIn("Terraform infrastructure creation failed", str(context.exception))
    mock_create_infra.assert_called_once()
    mock_deploy_k8s.assert_not_called()

  @patch('celery_api.workers.current_task')
  @patch('celery_api.workers.create_infrastructure')
  @patch('celery_api.workers.deploy_kubernetes')
  @patch('celery_api.workers.subprocess.run')
  @patch('celery_api.workers.Session')
  def test_create_cluster_inventory_generation_failure(self, mock_session, mock_run, mock_deploy_k8s, 
                             mock_create_infra, mock_current_task):
    # Setup mocks
    mock_current_task.id = "task-123"
    mock_create_infra.return_value = True
    
    # Mock inventory generation failure
    mock_run.side_effect = [
      MagicMock(returncode=0),  # cp command succeeds
      MagicMock(returncode=1)   # host --list command fails
    ]
    
    # Test execution and verify exception
    with self.assertRaises(Exception) as context:
      create_cluster(self.cluster_tf_dict, self.cluster_dict)
    
    self.assertIn("Error generating Ansible inventory", str(context.exception))
    mock_create_infra.assert_called_once()
    mock_deploy_k8s.assert_not_called()

  @patch('celery_api.workers.current_task')
  @patch('celery_api.workers.create_infrastructure')
  @patch('celery_api.workers.deploy_kubernetes')
  @patch('celery_api.workers.time.sleep')
  @patch('celery_api.workers.subprocess.run')
  @patch('celery_api.workers.Session')
  def test_create_cluster_connectivity_failure(self, mock_session, mock_run, mock_sleep, 
                         mock_deploy_k8s, mock_create_infra, mock_current_task):
    # Setup mocks
    mock_current_task.id = "task-123"
    mock_create_infra.return_value = True
    
    # Create mock returns for all subprocess.run calls
    # First two calls succeed (cp and inventory generation)
    # Then we have 13 failed ansible ping attempts (initial + 12 retries)
    mock_returns = [
      MagicMock(returncode=0),  # cp command succeeds
      MagicMock(returncode=0),  # host --list command succeeds
    ]
    for _ in range(13):  # All ping attempts fail
      mock_returns.append(MagicMock(returncode=1))
      
    mock_run.side_effect = mock_returns
    
    # Test execution and verify exception
    with self.assertRaises(Exception) as context:
      create_cluster(self.cluster_tf_dict, self.cluster_dict)
    
    self.assertIn("Failed to connect to all nodes", str(context.exception))
    mock_create_infra.assert_called_once()
    mock_deploy_k8s.assert_not_called()
    # Verify sleep was called for retries
    self.assertGreaterEqual(mock_sleep.call_count, 12)

  @patch('celery_api.workers.current_task')
  @patch('celery_api.workers.create_infrastructure')
  @patch('celery_api.workers.deploy_kubernetes')
  @patch('celery_api.workers.get_cluster_kubeconfig')
  @patch('celery_api.workers.subprocess.run')
  @patch('celery_api.workers.Session')
  def test_create_cluster_kubernetes_deployment_failure(self, mock_session, mock_run, mock_get_kubeconfig, 
                            mock_deploy_k8s, mock_create_infra, mock_current_task):
    # Setup mocks
    mock_current_task.id = "task-123"
    mock_create_infra.return_value = True
    mock_deploy_k8s.return_value = False
    
    # Mock successful subprocess calls for ping
    mock_run.return_value = MagicMock(returncode=0, stdout="inventory_content")
    
    # Test execution and verify exception
    with self.assertRaises(Exception) as context:
      create_cluster(self.cluster_tf_dict, self.cluster_dict)
    
    self.assertIn("Ansible kubernetes deployment failed", str(context.exception))
    mock_create_infra.assert_called_once()
    mock_deploy_k8s.assert_called_once()
    mock_get_kubeconfig.assert_not_called()

  @patch('celery_api.workers.current_task')
  @patch('celery_api.workers.create_infrastructure')
  @patch('celery_api.workers.deploy_kubernetes')
  @patch('celery_api.workers.get_cluster_kubeconfig')
  @patch('celery_api.workers.subprocess.run')
  @patch('celery_api.workers.Session')
  @patch('celery_api.workers.time')
  def test_create_cluster_timeout(self, mock_time, mock_session, mock_run, mock_get_kubeconfig, 
                  mock_deploy_k8s, mock_create_infra, mock_current_task):
    # Setup mocks
    mock_current_task.id = "task-123"
    mock_create_infra.return_value = True
    
    # Mock time to simulate timeout
    mock_time.time.side_effect = [0, 1800 + 1]  # Start time and then time after timeout
    
    # Set up run to return failure for ping
    mock_run.side_effect = [
      MagicMock(returncode=0),  # cp command succeeds
      MagicMock(returncode=0),  # host --list command succeeds
      MagicMock(returncode=1)   # ansible ping fails
    ]
    
    # Test execution and verify timeout exception
    with self.assertRaises(Exception) as context:
      create_cluster(self.cluster_tf_dict, self.cluster_dict)
    
    self.assertIn("Operation timed out", str(context.exception))
    mock_create_infra.assert_called_once()
