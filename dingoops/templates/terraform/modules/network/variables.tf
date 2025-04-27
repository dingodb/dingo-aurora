variable "external_net" {}

variable "admin_network_name" {}

variable "bus_network_name" {}

variable "network_dns_domain" {}

variable "cluster_name" {}
variable "number_subnet" {}

variable "dns_nameservers" {
  type = list
}

variable "port_security_enabled" {
  type = bool
}

variable "subnet_cidr" {}

variable "use_neutron" {}

variable "router_id" {}
variable "admin_subnet_id" {}
variable "bus_subnet_id" {}
variable "use_existing_network" {
  description = "Whether to use an existing network instead of creating a new one"
  type        = bool
  default     = false
}