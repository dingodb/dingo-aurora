locals {
  k8s_masters_reserved_fips = {
    for key, value in var.k8s_masters : key => {
      address = value.reserved_floating_ip
    } if value.floating_ip && (lookup(value, "reserved_floating_ip", "") != "")
  }
  k8s_masters_create_fips = {
    for key, value in openstack_networking_floatingip_v2.k8s_masters : key => {
      address = value.address
    }
  }
  nodes_reserved_fips = {
    for key, value in var.nodes : key => {
      address = value.reserved_floating_ip
    } if value.floating_ip && (lookup(value, "reserved_floating_ip", "") != "")
  }
  nodes_create_fips = {
    for key, value in openstack_networking_floatingip_v2.nodes : key => {
      address = value.address
    }
  }
  bastion_ips = var.bastion_floatip_id != "" && length(var.bastion_fips) > 0 ?  var.bastion_fips : openstack_networking_floatingip_v2.bastion_fip.*.address
}

# If k8s_master_fips is already defined as input, keep the same value since new FIPs have not been created.
output "k8s_master_fips" {
  value = length(var.bastion_fips) > 0 ? var.bastion_fips : local.bastion_ips
}

output "k8s_masters_fips" {
  value = merge(local.k8s_masters_create_fips, local.k8s_masters_reserved_fips)
}

# If k8s_master_fips is already defined as input, keep the same value since new FIPs have not been created.
output "k8s_master_no_etcd_fips" {
  value = length(var.bastion_fips) > 0 ? var.bastion_fips : openstack_networking_floatingip_v2.bastion[*].address
}

output "node_fips" {
  value = openstack_networking_floatingip_v2.k8s_node[*].address
}

output "nodes_fips" {
  value = merge(local.nodes_create_fips, local.nodes_reserved_fips)
}

output "bastion_fips" {
  value = local.bastion_ips
}

output "bastion_fip_ids" {
  value = var.bastion_floatip_id != "" ? [var.bastion_floatip_id] : openstack_networking_floatingip_v2.bastion_fip.*.id
}