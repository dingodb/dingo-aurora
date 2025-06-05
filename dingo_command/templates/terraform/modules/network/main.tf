data "openstack_networking_router_v2" "cluster" {
  name      = "cluster-router"
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
  count                 = var.use_neutron
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
  count           = var.use_neutron
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

resource "openstack_networking_router_interface_v2" "cluster" {
  count     = var.use_neutron
  router_id = "%{if length(data.openstack_networking_router_v2.cluster) == 0}${openstack_networking_router_v2.cluster[count.index].id}%{else}${data.openstack_networking_router_v2.cluster[count.index].id}%{endif}"
  subnet_id = openstack_networking_subnet_v2.cluster[count.index].id
}
