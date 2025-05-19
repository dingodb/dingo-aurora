variable "cluster_name" {}

variable "subnet_id" {}

variable "k8s_master_ips" {}

variable "k8s_master_loadbalancer_enabled" {}

variable "k8s_master_loadbalancer_listener_port" {}

variable "k8s_master_loadbalancer_server_port" {}

variable "k8s_master_loadbalancer_public_ip" {}
variable "token" {
  type    = string
  default = ""
}
variable "auth_url" {
  type    = string
  default = ""
}
variable "tenant_id" {
}

variable "public_floatingip_pool" {}
variable "public_subnetids" {}