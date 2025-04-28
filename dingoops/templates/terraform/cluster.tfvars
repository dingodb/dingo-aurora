# your Kubernetes cluster name here
cluster_name = "d-cluster"

# list of availability zones available in your OpenStack cluster
az_list = ["nova"]

# SSH key to use for access to nodesdn
public_key_path = "~/.ssh/id_rsa.pub"

# image to use for bastion, masters, standalone etcd instances, and nodes
image = "ubuntu-2204-dsy"

# user on the node (ex. core on Container Linux, ubuntu on Ubuntu, etc.)
ssh_user = "ubuntu"

# 0|1 bastion nodes
number_of_bastions = 0

#flavor_bastion = "1"

# standalone etcds
number_of_etcd = 0

# masters
number_of_k8s_masters = 1

number_of_k8s_masters_no_etcd = 0

number_of_k8s_masters_no_floating_ip = 0

number_of_k8s_masters_no_floating_ip_no_etcd = 0

flavor_k8s_master = "1"

k8s_masters = {
  #"master-1" = {
  #  "az"          = "nova"
  #  "flavor"      = "1"
  #  "floating_ip" = true
  #  "etcd" = true
  #}
}

group_vars_path="/root/dsy/kubespray/inventory/dsy-cluster/group_vars"
# nodes
number_of_k8s_nodes = 1

number_of_k8s_nodes_no_floating_ip = 0

flavor_k8s_node = "1"

# GlusterFS
# either 0 or more than one
#number_of_gfs_nodes_no_floating_ip = 0
#gfs_volume_size_in_gb = 150
# Container Linux does not support GlusterFS
#image_gfs = "<image name>"
# May be different from other nodes
#ssh_user_gfs = "ubuntu"
#flavor_gfs_node = "<UUID>"

# networking
admin_network_id = "AIDC2-vlan4056-2"
bus_network_id = "mall-share-net-vlan-4058"
# Use a existing network with the name of network_name. Set to false to create a network with name of network_name.
use_existing_network = true

subnet_cidr = "192.168.10.0/24"

floatingip_pool = "physnet2"

bastion_allowed_remote_ips = ["0.0.0.0/0"]

# Force port security to be null. Some cloud providers do not allow to set port security.
# force_null_port_security = false
external_net = "a88e60f1-6bd1-4846-8b96-cbd309c1ebd4"

k8s_nodes = {
  #"node-1" = {
  #  "az"     = "nova"
  #  "flavor" = "1"
  #  "floating_ip" = false
  #}
}

router_id = "33e1fd4f-c277-4e6a-8b48-ab637f7bcce6"
admin_subnet_id = "c8b2c4df-7745-4028-acbd-333bc450a5be"
bus_subnet_id = "438b7357-6a9a-4d93-993d-f73ce2a5d803"