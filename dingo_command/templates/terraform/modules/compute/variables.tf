variable "cluster_name" {}
variable "cluster_id" {}

variable "az_list" {
  type = list(string)
}

variable "az_list_node" {
  type = list(string)
}

variable "number_of_k8s_masters" {}

variable "number_of_k8s_masters_no_etcd" {}

variable "number_of_etcd" {}

variable "number_of_k8s_masters_no_floating_ip" {}

variable "number_of_k8s_masters_no_floating_ip_no_etcd" {}

variable "number_of_nodes" {}

variable "number_of_nodes_no_floating_ip" {}

variable "number_of_bastions" {}

variable "number_of_gfs_nodes_no_floating_ip" {}

variable "bastion_root_volume_size_in_gb" {}

variable "etcd_root_volume_size_in_gb" {}

variable "master_root_volume_size_in_gb" {}

variable "node_root_volume_size_in_gb" {}

variable "gfs_root_volume_size_in_gb" {}

variable "gfs_volume_size_in_gb" {}

variable "master_volume_type" {}

variable "node_volume_type" {}
variable "public_key_path" {}
variable "private_key_path" {}

variable "image" {}

variable "image_gfs" {}

variable "ssh_user" {}

variable "ssh_user_gfs" {}

variable "flavor_k8s_master" {}

variable "flavor_k8s_node" {}

variable "flavor_etcd" {}

variable "flavor_gfs_node" {}

variable "admin_network_name" {}

variable "bus_network_name" {}


variable "flavor_bastion" {}

variable "admin_network_id" {
  default = ""
}
variable "bus_network_id" {
  default = ""
}
variable "use_existing_network" {
  type = bool
}

variable "network_router_id" {
  default = ""
}

variable "k8s_master_fips" {
  type = list
}

variable "k8s_master_no_etcd_fips" {
  type = list
}

variable "node_fips" {
  type = list
}

variable "k8s_masters_fips" {
  type = map(object({
    address = string
  }))
}

variable "nodes_fips" {
  type = map(object({
    address = string
  }))
}

variable "bastion_fips" {
  type = list
}

variable "bastion_fip_ids" {
  type = list
}


variable "bastion_allowed_remote_ips" {
  type = list
}

variable "bastion_allowed_remote_ipv6_ips" {
  type = list
}

variable "master_allowed_remote_ips" {
  type = list
}

variable "master_allowed_remote_ipv6_ips" {
  type = list
}

variable "k8s_allowed_remote_ips" {
  type = list
}

variable "k8s_allowed_remote_ips_ipv6" {
  type = list
}

variable "k8s_allowed_egress_ips" {
  type = list
}

variable "k8s_allowed_egress_ipv6_ips" {
  type = list
}

variable "k8s_masters" {
  type = map(object({
    az                     = string
    flavor                 = string
    etcd                   = bool
    floating_ip            = bool
    reserved_floating_ip   = optional(string)
    image_id               = optional(string)
    root_volume_size_in_gb = optional(number)
    volume_type            = optional(string)
    network_id             = optional(string)
    cloudinit              = optional(string)
  }))
}

variable "nodes" {
  type = map(object({
    az                     = string
    flavor                 = string
    floating_ip            = bool
    use_local_disk         = bool
    volume_type            = string
    volume_size            = number
    port_forwards          = optional(list(object({
    external_port = number
    internal_port = number
    protocol = string
  })))

    reserved_floating_ip   = optional(string)
    extra_groups           = optional(string)
    image_id               = optional(string)
    root_volume_size_in_gb = optional(number)
    network_id             = optional(string)
    additional_server_groups = optional(list(string))
    server_group           = optional(string)
    cloudinit              = optional(object({
      extra_partitions = optional(list(object({
        volume_path     = string
        partition_path  = string
        partition_start = string
        partition_end   = string
        mount_path      = string
      })), [])
      netplan_critical_dhcp_interface = optional(string, "")
    }))
  }))
}



variable "additional_server_groups" {
  type = map(object({
    policy = string
  }))
}

variable "supplementary_master_groups" {
  default = ""
}

variable "supplementary_node_groups" {
  default = ""
}

variable "master_allowed_ports" {
  type = list
}

variable "master_allowed_ports_ipv6" {
  type = list
}

variable "worker_allowed_ports" {
  type = list
}

variable "worker_allowed_ports_ipv6" {
  type = list
}

variable "bastion_allowed_ports" {
  type = list
}

variable "bastion_allowed_ports_ipv6" {
  type = list
}

variable "use_access_ip" {}

variable "master_server_group_policy" {
  type = string
}

variable "node_server_group_policy" {
  type = string
}

variable "etcd_server_group_policy" {
  type = string
}

variable "extra_sec_groups" {
  type = bool
}

variable "extra_sec_groups_name" {
  type = string
}

variable "image_uuid" {
  type = string
}

variable "image_gfs_uuid" {
  type = string
}

variable "image_master" {
  type = string
}

variable "image_master_uuid" {
  type = string
}

variable "group_vars_path" {
  type = string
}

variable "port_security_enabled" {
  type = bool
}

variable "force_null_port_security" {
  type = bool
}

variable "private_subnet_id" {
  type = string
}

variable "key_pair" {
  type = string
}

variable "password" {
  type = string
}

variable "token" {
  type    = string
  default = ""
}
variable "auth_url" {
  type    = string
  default = ""
}
variable "tenant_id" {
  type    = string
  default = ""
}

variable "forward_float_ip_id" {}
variable "etcd_volume_type" {}

variable "pushgateway_url" {}

variable "pushgateway_user" {}
variable "pushgateway_pass" {}