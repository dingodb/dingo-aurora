provider "openstack" {
  token    = var.token
  auth_url =  var.auth_url
  tenant_id = var.tenant_id
}

module "network" {
  source = "./modules/network"
  number_subnet         = var.number_subnet
  external_net          = var.external_net
  admin_network_name    = var.admin_network_name
  bus_network_name      = var.bus_network_name
  subnet_cidr           = var.subnet_cidr 
  cluster_name          = var.cluster_name
  dns_nameservers       = var.dns_nameservers
  network_dns_domain    = var.network_dns_domain
  use_neutron           = var.use_neutron
  port_security_enabled = var.port_security_enabled
  router_id             = var.router_id
  admin_subnet_id       = var.admin_subnet_id
  bus_subnet_id         = var.bus_subnet_id
  use_existing_network  = var.use_existing_network
  token = var.token
  auth_url = var.auth_url
  tenant_id = var.tenant_id
}

module "ips" {
  source = "./modules/ips"

  number_of_k8s_masters         = var.number_of_k8s_masters
  number_of_k8s_masters_no_etcd = var.number_of_k8s_masters_no_etcd
  number_of_nodes               = var.number_of_nodes
  floatingip_pool               = var.floatingip_pool
  external_subnetids            = var.external_subnetids
  number_of_bastions            = var.number_of_bastions
  external_net                  = var.external_net
  admin_network_name            = var.admin_network_name
  admin_network_id              = var.admin_network_id
  router_id                     = module.network.router_id
  nodes                         = var.nodes
  k8s_masters                   = var.k8s_masters
  k8s_master_fips               = var.k8s_master_fips
  bastion_fips                  = var.bastion_fips
  router_internal_port_id       = module.network.router_internal_port_id
  token = var.token
  auth_url = var.auth_url
  tenant_id = var.tenant_id
  bastion_floatip_id =  var.bastion_floatip_id

}

module "compute" {
  source = "./modules/compute"

  cluster_name                                 = var.cluster_name
  az_list                                      = var.az_list
  az_list_node                                 = var.az_list_node
  number_of_k8s_masters                        = var.number_of_k8s_masters
  number_of_k8s_masters_no_etcd                = var.number_of_k8s_masters_no_etcd
  number_of_etcd                               = var.number_of_etcd
  number_of_k8s_masters_no_floating_ip         = var.number_of_k8s_masters_no_floating_ip
  number_of_k8s_masters_no_floating_ip_no_etcd = var.number_of_k8s_masters_no_floating_ip_no_etcd
  number_of_nodes                              = var.number_of_nodes
  number_of_bastions                           = var.number_of_bastions
  number_of_nodes_no_floating_ip               = var.number_of_nodes_no_floating_ip
  number_of_gfs_nodes_no_floating_ip           = var.number_of_gfs_nodes_no_floating_ip
  k8s_masters                                  = var.k8s_masters
  nodes                                        = var.nodes
  bastion_root_volume_size_in_gb               = var.bastion_root_volume_size_in_gb
  etcd_root_volume_size_in_gb                  = var.etcd_root_volume_size_in_gb
  master_root_volume_size_in_gb                = var.master_root_volume_size_in_gb
  node_root_volume_size_in_gb                  = var.node_root_volume_size_in_gb
  gfs_root_volume_size_in_gb                   = var.gfs_root_volume_size_in_gb
  gfs_volume_size_in_gb                        = var.gfs_volume_size_in_gb
  master_volume_type                           = var.master_volume_type
  node_volume_type                             = var.node_volume_type
  public_key_path                              = var.public_key_path
  private_key_path                             = var.private_key_path
  image                                        = var.image
  image_uuid                                   = var.image_uuid
  image_gfs                                    = var.image_gfs
  image_master                                 = var.image_master
  image_master_uuid                            = var.image_master_uuid
  image_gfs_uuid                               = var.image_gfs_uuid
  ssh_user                                     = var.ssh_user
  ssh_user_gfs                                 = var.ssh_user_gfs
  flavor_k8s_master                            = var.flavor_k8s_master
  flavor_k8s_node                              = var.flavor_k8s_node
  flavor_etcd                                  = var.flavor_etcd
  flavor_gfs_node                              = var.flavor_gfs_node
  bus_network_name                             = var.bus_network_name
  admin_network_name                           = var.admin_network_name

  #bus_network_id                               = module.network.bus_network_id
  network_router_id                            = module.network.router_id
  admin_network_id                             = module.network.admin_network_id
  flavor_bastion                               = var.flavor_bastion
  k8s_master_fips                              = module.ips.k8s_master_fips
  k8s_master_no_etcd_fips                      = module.ips.k8s_master_no_etcd_fips
  k8s_masters_fips                             = module.ips.k8s_masters_fips
  node_fips                                    = module.ips.node_fips
  nodes_fips                                   = module.ips.nodes_fips
  bastion_fips                                 = module.ips.bastion_fips
  bastion_fip_ids                              = module.ips.bastion_fip_ids
  bastion_allowed_remote_ips                   = var.bastion_allowed_remote_ips
  bastion_allowed_remote_ipv6_ips              = var.bastion_allowed_remote_ipv6_ips
  master_allowed_remote_ips                    = var.master_allowed_remote_ips
  master_allowed_remote_ipv6_ips               = var.master_allowed_remote_ipv6_ips
  k8s_allowed_remote_ips                       = var.k8s_allowed_remote_ips
  k8s_allowed_remote_ips_ipv6                  = var.k8s_allowed_remote_ips_ipv6
  k8s_allowed_egress_ips                       = var.k8s_allowed_egress_ips
  k8s_allowed_egress_ipv6_ips                  = var.k8s_allowed_egress_ipv6_ips
  supplementary_master_groups                  = var.supplementary_master_groups
  supplementary_node_groups                    = var.supplementary_node_groups
  master_allowed_ports                         = var.master_allowed_ports
  master_allowed_ports_ipv6                    = var.master_allowed_ports_ipv6
  worker_allowed_ports                         = var.worker_allowed_ports
  worker_allowed_ports_ipv6                    = var.worker_allowed_ports_ipv6
  bastion_allowed_ports                        = var.bastion_allowed_ports
  bastion_allowed_ports_ipv6                   = var.bastion_allowed_ports_ipv6
  use_access_ip                                = var.use_access_ip
  master_server_group_policy                   = var.master_server_group_policy
  node_server_group_policy                     = var.node_server_group_policy
  etcd_server_group_policy                     = var.etcd_server_group_policy
  extra_sec_groups                             = var.extra_sec_groups
  extra_sec_groups_name                        = var.extra_sec_groups_name
  group_vars_path                              = var.group_vars_path
  port_security_enabled                        = var.port_security_enabled
  force_null_port_security                     = var.force_null_port_security
  use_existing_network                         = var.use_existing_network
  private_subnet_id                            = module.network.admin_subnet_id
  additional_server_groups                     = var.additional_server_groups
  depends_on = [
    module.network.subnet_id
  ]
  key_pair                                     = var.key_pair
  password                                     = var.password
  forward_float_ip_id                          = var.forward_float_ip_id
  token = var.token
  auth_url = var.auth_url
  tenant_id = var.tenant_id
  etcd_volume_type = var.etcd_volume_type
}

module "loadbalancer" {
  source = "./modules/loadbalancer"

  cluster_name                          = var.cluster_name
  subnet_id                             = module.network.admin_subnet_id
  public_floatingip_pool                = var.public_floatingip_pool
  public_subnetids                      = var.public_subnetids
  k8s_master_ips                        = module.compute.k8s_master_ips
  k8s_master_loadbalancer_enabled       = var.k8s_master_loadbalancer_enabled
  k8s_master_loadbalancer_listener_port = var.k8s_master_loadbalancer_listener_port
  k8s_master_loadbalancer_server_port   = var.k8s_master_loadbalancer_server_port
  k8s_master_loadbalancer_public_ip     = var.k8s_master_loadbalancer_public_ip
  token = var.token
  auth_url = var.auth_url
  tenant_id = var.tenant_id
  depends_on = [
    module.compute.k8s_master
  ]
}


output "private_subnet_id" {
  value = module.network.admin_subnet_id
}

output "floating_network_id" {
  value = var.external_net
}

output "router_id" {
  value = module.network.router_id
}

output "k8s_master_fips" {
  value = var.number_of_k8s_masters + var.number_of_k8s_masters_no_etcd > 0 ? concat(module.ips.k8s_master_fips, module.ips.k8s_master_no_etcd_fips) : [for key, value in module.ips.k8s_masters_fips : value.address]
}

output "node_fips" {
  value = var.number_of_nodes > 0 ? module.ips.node_fips : [for key, value in module.ips.nodes_fips : value.address]
}

output "bastion_fips" {
  value = module.ips.bastion_fips
}
