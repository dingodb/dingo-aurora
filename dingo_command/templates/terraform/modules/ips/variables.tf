variable "number_of_k8s_masters" {}

variable "number_of_k8s_masters_no_etcd" {}

variable "number_of_nodes" {}

variable "floatingip_pool" {}

variable "number_of_bastions" {}

variable "external_net" {}

variable "admin_network_name" {}

variable "admin_network_id" {}

variable "router_id" {
  default = ""
}

variable "k8s_masters" {}

variable "nodes" {}

variable "k8s_master_fips" {}

variable "bastion_fips" {}

variable "router_internal_port_id" {}
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
variable "external_subnetids" {}