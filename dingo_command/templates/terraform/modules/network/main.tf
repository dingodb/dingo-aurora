data "openstack_networking_router_v2" "cluster" {
  name      = "cluster-router"
  tenant_id = var.tenant_id
  count     = var.use_neutron == 1 && var.router_id != null && var.router_id != "" ? 1 : 0
}
resource "openstack_networking_router_v2" "cluster" {
  name                = "cluster-router"
  count               = length(data.openstack_networking_router_v2.cluster) == 0 ? 1 : 0
  admin_state_up      = "true"
  external_network_id = var.external_net
}

resource "openstack_networking_network_v2" "cluster" {
  name                  = var.cluster_name
  count                 = var.use_existing_network && var.admin_network_id != "" ? 0 : 1
  dns_domain            = var.network_dns_domain != null ? var.network_dns_domain : null
  admin_state_up        = "true"
  #port_security_enabled = var.port_security_enabled
  #segments {
  #  network_type    = "vlan"
  #  physical_network = "physnet1"
  #}
}


resource "openstack_networking_network_v2" "bus_cluster" {
  name                  = var.cluster_name
  count                 = var.use_existing_network ? 0 : (var.bus_network_id != null && var.bus_network_id != "") ? 1 : 0
  dns_domain            = var.network_dns_domain != null ? var.network_dns_domain : null
  admin_state_up        = "true"
  #port_security_enabled = var.port_security_enabled
  #segments {
  #  network_type    = "vlan"
  #  physical_network = "physnet1"
  #}
}

resource "openstack_networking_subnet_v2" "cluster" {
  name            = "${var.cluster_name}-internal-network"
  count           =  var.use_existing_network && var.bus_network_id != "" ? 0 : var.use_neutron
  network_id      = openstack_networking_network_v2.cluster[count.index].id
  cidr            = var.subnet_cidr
  ip_version      = 4
  dns_nameservers = var.dns_nameservers
}

resource "openstack_networking_subnet_v2" "bussiness" {
  name            = "${var.cluster_name}-bus-network"
  count           = var.use_neutron == 1 && var.number_subnet > 1 ? var.number_subnet : 0
  network_id      = openstack_networking_network_v2.cluster[count.index].id
  cidr            = var.subnet_cidr
  ip_version      = 4
  dns_nameservers = var.dns_nameservers
}


// 获取路由器信息用于检查external_fixed_ip
locals {
  router_id = var.router_id != null && var.router_id != "" ? var.router_id : (
    length(data.openstack_networking_router_v2.cluster) > 0 ?
    data.openstack_networking_router_v2.cluster[0].id :
    openstack_networking_router_v2.cluster[0].id
  )
}

// 如果subnet不在路由器的external_fixed_ip中，则将其绑定到路由器
resource "openstack_networking_router_interface_v2" "cluster_interface" {
  count     = var.use_existing_network && !var.attached_router && var.admin_subnet_id != null && var.admin_subnet_id != "" ? 1 : 0
  router_id = local.router_id
  subnet_id = var.admin_subnet_id
}

resource "openstack_networking_router_interface_v2" "cluster_interface_n" {
  count     = var.use_existing_network ? 0 : 1
  router_id = local.router_id
  subnet_id = resource.openstack_networking_subnet_v2.cluster[0].id
}