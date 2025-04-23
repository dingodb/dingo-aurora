data "openstack_images_image_v2" "vm_image" {
  count = var.image_uuid == "" ? 1 : 0
  most_recent = true
  name = var.image
}

data "openstack_images_image_v2" "gfs_image" {
  count = var.image_gfs_uuid == "" ? var.image_uuid == "" ? 1 : 0 : 0
  most_recent = true
  name = var.image_gfs == "" ? var.image : var.image_gfs
}

data "openstack_images_image_v2" "image_master" {
  count = var.image_master_uuid == "" ? var.image_uuid == "" ? 1 : 0 : 0
  name = var.image_master == "" ? var.image : var.image_master
}

data "cloudinit_config" "cloudinit" {
  part {
    content_type =  "text/cloud-config"
    content = templatefile("${path.module}/templates/cloudinit.yaml.tmpl", {
      extra_partitions = [],
      netplan_critical_dhcp_interface = "",
      ssh_user = var.ssh_user
      password = var.password
    })
  }
}

data "openstack_networking_network_v2" "k8s_admin_network" {
  count = var.use_existing_network != null ? 1 : 0
  network_id  = var.admin_network_id
}

data "openstack_networking_network_v2" "bus_k8s_network" {
  count = var.use_existing_network && var.bus_network_id != "" ? 1 : 0
  network_id  = var.bus_network_id
}

# resource "openstack_compute_keypair_v2" "k8s" {
#   name       = "kubernetes-${var.cluster_name}"
#   public_key = chomp(file(var.public_key_path))
# }

locals {

# Image uuid
  image_to_use_node = var.image_uuid != "" ? var.image_uuid : data.openstack_images_image_v2.vm_image[0].id
# Image_gfs uuid
  image_to_use_gfs = var.image_gfs_uuid != "" ? var.image_gfs_uuid : var.image_uuid != "" ? var.image_uuid : data.openstack_images_image_v2.gfs_image[0].id
# image_master uuidimage_gfs_uuid
  image_to_use_master = var.image_master_uuid != "" ? var.image_master_uuid : var.image_uuid != "" ? var.image_uuid : data.openstack_images_image_v2.image_master[0].id
  k8s_nodes_settings = {
    for name, node in var.k8s_nodes :
      name => {
        "key_pair"       = var.key_pair,
        "password"       = var.password,
        "use_local_disk" = (node.root_volume_size_in_gb != null ? node.root_volume_size_in_gb : var.node_root_volume_size_in_gb) == 0,
        "image_id"       = node.image_id != null ? node.image_id : local.image_to_use_node,
        "volume_size"    = node.root_volume_size_in_gb != null ? node.root_volume_size_in_gb : var.node_root_volume_size_in_gb,
        "volume_type"    = node.volume_type != null ? node.volume_type : var.node_volume_type,
        "admin_network_id"     = node.network_id != null ? node.network_id : (var.use_existing_network ? data.openstack_networking_network_v2.k8s_admin_network[0].id : var.admin_network_id)
        "bus_network_id"     = node.network_id != null ? node.network_id : (var.use_existing_network && var.bus_network_id != "" ? data.openstack_networking_network_v2.bus_k8s_network[0].id : var.bus_network_id)
        #"server_group"   = node.server_group != null ? [openstack_compute_servergroup_v2.k8s_node_additional[node.server_group].id] : (var.node_server_group_policy != ""  ? [openstack_compute_servergroup_v2.k8s_node[0].id] : [])
      }
  }

  k8s_masters_settings = {
    for name, node in var.k8s_masters :
      name => {
        "key_pair"       = var.key_pair,
        "password"       = var.password,
        "use_local_disk" = (node.root_volume_size_in_gb != null ? node.root_volume_size_in_gb : var.master_root_volume_size_in_gb) == 0,
        "image_id"       = node.image_id != null ? node.image_id : local.image_to_use_master,
        "volume_size"    = node.root_volume_size_in_gb != null ? node.root_volume_size_in_gb : var.master_root_volume_size_in_gb,
        "volume_type"    = node.volume_type != null ? node.volume_type : var.master_volume_type,
        "admin_network_id"     = node.network_id != null ? node.network_id : (var.use_existing_network ? data.openstack_networking_network_v2.k8s_admin_network[0].id : var.admin_network_id)
        "bus_network_id"     = node.network_id != null ? node.network_id : (var.use_existing_network && var.bus_network_id != "" ? data.openstack_networking_network_v2.bus_k8s_network[0].id : var.bus_network_id)
      }
  }
}
locals {
  # Only process segments if using existing network and bus_network_id is provided
  segments_list = var.use_existing_network && var.bus_network_id != "" ? [for s in data.openstack_networking_network_v2.bus_k8s_network[0].segments : s] : []
  # Get first segment (if exists)
  first_segment = length(local.segments_list) > 0 ? local.segments_list[0] : null
  # Provide default values to prevent null
  segmentation_id = local.first_segment != null ? local.first_segment.segmentation_id : "1000"
  network_type = local.first_segment != null ? local.first_segment.network_type : "vlan"
}

resource "openstack_networking_port_v2" "k8s_admin_master_port" {
  count                 = var.number_of_k8s_masters
  name                  = "${var.cluster_name}-k8s-master-admin-${count.index + 1}"
  network_id            = var.use_existing_network ? data.openstack_networking_network_v2.k8s_admin_network[0].id : var.admin_network_id
  admin_state_up        = "true"
  dynamic "fixed_ip" {
    for_each = var.private_subnet_id == "" ? [] : [true]
    content {
      subnet_id = var.private_subnet_id
    }
  }

  lifecycle {
    ignore_changes = [ allowed_address_pairs ]
  }

  depends_on = [
    var.network_router_id
  ]
}

resource "openstack_networking_port_v2" "k8s_business_master_port" {
  count                 = var.number_of_k8s_masters
  name                  = "${var.cluster_name}-k8s-master-${count.index + 1}"
  network_id            = var.use_existing_network ? data.openstack_networking_network_v2.bus_k8s_network[0].id : var.bus_network_id
  admin_state_up        = "true"
  port_security_enabled = false
  #no_fixed_ip           = true

  lifecycle {
    ignore_changes = [ allowed_address_pairs ]
  }

  depends_on = [
    var.network_router_id
  ]
}

resource "openstack_networking_trunk_v2" "trunk_master" {
  name           = "${var.cluster_name}-${count.index + 1}"
  count          = var.number_of_k8s_masters
  admin_state_up = "true"
  port_id        = element(openstack_networking_port_v2.k8s_business_master_port.*.id, count.index)

}

resource "openstack_compute_instance_v2" "k8s_master" {
  name              = "${var.cluster_name}-k8s-master-${count.index + 1}"
  count             = var.number_of_k8s_masters
  availability_zone = element(var.az_list, count.index)
  image_id          = var.master_root_volume_size_in_gb == 0 ? local.image_to_use_master : null
  flavor_id         = var.flavor_k8s_master
  key_pair          = var.key_pair
  user_data         = data.cloudinit_config.cloudinit.rendered

  dynamic "block_device" {
    for_each = var.master_root_volume_size_in_gb > 0 ? [local.image_to_use_master] : []
    content {
      uuid                  = local.image_to_use_master
      source_type           = "image"
      volume_size           = var.master_root_volume_size_in_gb
      volume_type           = var.master_volume_type
      boot_index            = 0
      destination_type      = "volume"
      delete_on_termination = true
    }
  }
  network {
    port = element(openstack_networking_port_v2.k8s_admin_master_port.*.id, count.index)
  }
  network {
    port = element(openstack_networking_port_v2.k8s_business_master_port.*.id, count.index)
  }

  metadata = {
    ssh_user         = var.ssh_user
    kubespray_groups = "etcd,kube_control_plane,${var.supplementary_master_groups},k8s_cluster"
    depends_on       = var.network_router_id
    use_access_ip    = var.use_access_ip
  }
  depends_on = [
    openstack_networking_trunk_v2.trunk_masters
  ]
  provisioner "local-exec" {
    command = "sed -e s/USER/${var.ssh_user}/ -e s/BASTION_ADDRESS/${element(concat(var.bastion_fips, var.k8s_master_fips), 0)}/ ${path.module}/ansible_bastion_template.txt > ${var.group_vars_path}/no_floating.yml"
  }
}
## 配置k8snode节点相关
resource "openstack_networking_port_v2" "k8s_admin_node_port" {
  count                 = var.number_of_k8s_nodes
  name                  = "${var.cluster_name}-k8s-node-${count.index + 1}"
  network_id            = var.use_existing_network ? data.openstack_networking_network_v2.k8s_admin_network[0].id : var.admin_network_id
  admin_state_up        = "true"
  dynamic "fixed_ip" {
    for_each = var.private_subnet_id == "" ? [] : [true]
    content {
      subnet_id = var.private_subnet_id
    }
  }

  lifecycle {
    ignore_changes = [ allowed_address_pairs ]
  }

  depends_on = [
    var.network_router_id
  ]
}

resource "openstack_networking_port_v2" "k8s_business_node_port" {
  count                 = var.number_of_k8s_nodes
  name                  = "${var.cluster_name}-k8s-node-${count.index + 1}"
  network_id            = var.use_existing_network ? data.openstack_networking_network_v2.bus_k8s_network[0].id : var.bus_network_id
  admin_state_up        = "true"
  port_security_enabled = false
  #no_fixed_ip           = true

  lifecycle {
    ignore_changes = [ allowed_address_pairs ]
  }

  depends_on = [
    var.network_router_id
  ]
}

resource "openstack_networking_trunk_v2" "trunk_node" {
  name           = "${var.cluster_name}-${count.index + 1}"
  count          = var.number_of_k8s_nodes
  admin_state_up = "true"
  port_id        = element(openstack_networking_port_v2.k8s_business_node_port.*.id, count.index)

}

resource "openstack_compute_instance_v2" "k8s_node" {
  name              = "${var.cluster_name}-k8s-node-${count.index + 1}"
  count             = var.number_of_k8s_nodes
  availability_zone = element(var.az_list_node, count.index)
  image_id          = var.node_root_volume_size_in_gb == 0 ? local.image_to_use_node : null
  flavor_id         = var.flavor_k8s_node
  key_pair          =var.key_pair
  user_data         = data.cloudinit_config.cloudinit.rendered

  dynamic "block_device" {
    for_each = var.node_root_volume_size_in_gb > 0 ? [local.image_to_use_node] : []
    content {
      uuid                  = local.image_to_use_node
      source_type           = "image"
      volume_size           = var.node_root_volume_size_in_gb
      volume_type           = var.node_volume_type
      boot_index            = 0
      destination_type      = "volume"
      delete_on_termination = true
    }
  }

  network {
    port = element(openstack_networking_port_v2.k8s_admin_node_port.*.id, count.index)
  }

  network {
    port = element(openstack_networking_port_v2.k8s_business_node_port.*.id, count.index)
  }

  metadata = {
    ssh_user         = var.ssh_user
    kubespray_groups = "kube_node,k8s_cluster,${var.supplementary_node_groups}"
    depends_on       = var.network_router_id
    use_access_ip    = var.use_access_ip
  }
  depends_on = [
    openstack_networking_trunk_v2.trunk_nodes
  ]
  provisioner "local-exec" {
    command = "sed -e s/USER/${var.ssh_user}/ -e s/BASTION_ADDRESS/${element(concat(var.bastion_fips, var.k8s_node_fips), 0)}/ ${path.module}/ansible_bastion_template.txt > ${var.group_vars_path}/no_floating.yml"
  }
}

resource "openstack_networking_port_v2" "k8s_nodes_port" {
  for_each              = var.number_of_k8s_nodes == 0 && var.number_of_k8s_nodes_no_floating_ip == 0 ? var.k8s_nodes : {}
  name                  = "${var.cluster_name}-k8s-node-${each.key}"
  network_id            = local.k8s_nodes_settings[each.key].admin_network_id
  admin_state_up        = "true"
  #port_security_enabled = var.force_null_port_security ? null : var.port_security_enabled
  #security_group_ids    = var.port_security_enabled ? local.worker_sec_groups : null
  #no_security_groups    = var.port_security_enabled ? null : false
  dynamic "fixed_ip" {
    for_each = var.private_subnet_id == "" ? [] : [true]
    content {
      subnet_id = var.private_subnet_id
    }
  }

  lifecycle {
    ignore_changes = [ allowed_address_pairs ]
  }

  depends_on = [
    var.network_router_id
  ]
}

resource "openstack_networking_floatingip_associate_v2" "k8s_master" {
  count                 = var.number_of_k8s_masters
  floating_ip           = var.k8s_master_fips[count.index]
  port_id               = element(openstack_networking_port_v2.k8s_admin_master_port.*.id, count.index)
}

# resource "openstack_networking_floatingip_associate_v2" "k8s_masters" {
#   for_each              = var.number_of_k8s_masters == 0 && var.number_of_k8s_masters_no_etcd == 0 && var.number_of_k8s_masters_no_floating_ip == 0 && var.number_of_k8s_masters_no_floating_ip_no_etcd == 0 ? { for key, value in var.k8s_masters : key => value if value.floating_ip } : {}
#   floating_ip           = var.k8s_masters_fips[each.key].address
#   port_id               = openstack_networking_port_v2.k8s_masters_port[each.key].id
# }


resource "openstack_networking_floatingip_associate_v2" "k8s_node" {
  count                 = var.node_root_volume_size_in_gb == 0 ? var.number_of_k8s_nodes : 0
  floating_ip           = var.k8s_node_fips[count.index]
  port_id               = element(openstack_networking_port_v2.k8s_admin_node_port.*.id, count.index)
}

# resource "openstack_networking_floatingip_associate_v2" "k8s_nodes" {
#   for_each              = var.number_of_k8s_nodes == 0 && var.number_of_k8s_nodes_no_floating_ip == 0 ? { for key, value in var.k8s_nodes : key => value if value.floating_ip } : {}
#   floating_ip           = var.k8s_nodes_fips[each.key].address
#   port_id               = openstack_networking_port_v2.k8s_nodes_port[each.key].id
# }


resource "openstack_networking_port_v2" "k8s_masters_admin_port" {
  for_each              = var.number_of_k8s_masters == 0 && var.number_of_k8s_masters_no_etcd == 0 && var.number_of_k8s_masters_no_floating_ip == 0 && var.number_of_k8s_masters_no_floating_ip_no_etcd == 0 ? var.k8s_masters : {}
  name                  = "${var.cluster_name}-k8s-${each.key}"
  network_id            = local.k8s_masters_settings[each.key].admin_network_id
  admin_state_up        = "true"
  dynamic "fixed_ip" {
    for_each = var.private_subnet_id == "" ? [] : [true]
    content {
      subnet_id = var.private_subnet_id
    }
  }

  lifecycle {
    ignore_changes = [ allowed_address_pairs ]
  }

  depends_on = [
    var.network_router_id
  ]
}
resource "openstack_networking_port_v2" "k8s_masters_bus_port" {
  for_each              = var.bus_network_id != "" && var.number_of_k8s_masters == 0 && var.number_of_k8s_masters_no_etcd == 0 && var.number_of_k8s_masters_no_floating_ip == 0 && var.number_of_k8s_masters_no_floating_ip_no_etcd == 0 ? var.k8s_masters : {}
  name                  = "${var.cluster_name}-k8s-${each.key}"
  network_id            = local.k8s_masters_settings[each.key].bus_network_id
  admin_state_up        = "true"
  dynamic "fixed_ip" {
    for_each = var.private_subnet_id == "" ? [] : [true]
    content {
      subnet_id = var.private_subnet_id
    }
  }

  lifecycle {
    ignore_changes = [ allowed_address_pairs ]
  }

  depends_on = [
    var.network_router_id
  ]
}

resource "openstack_networking_trunk_v2" "trunk_masters" {
  for_each       = var.bus_network_id != "" && var.number_of_k8s_masters == 0 && var.number_of_k8s_masters_no_etcd == 0 && var.number_of_k8s_masters_no_floating_ip == 0 && var.number_of_k8s_masters_no_floating_ip_no_etcd == 0 ? var.k8s_masters : {}
  name           = "${var.cluster_name}-k8s-${each.key}"
  admin_state_up = "true"
  port_id        = openstack_networking_port_v2.k8s_masters_admin_port[each.key].id
  sub_port {
    port_id           = openstack_networking_port_v2.k8s_masters_bus_port[each.key].id
    segmentation_id   = local.segmentation_id
    segmentation_type = local.network_type
  }
}

resource "openstack_compute_instance_v2" "k8s_masters" {
  for_each          = var.number_of_k8s_masters == 0 && var.number_of_k8s_masters_no_etcd == 0 && var.number_of_k8s_masters_no_floating_ip == 0 && var.number_of_k8s_masters_no_floating_ip_no_etcd == 0 ? var.k8s_masters : {}
  name              = "${var.cluster_name}-k8s-${each.key}"
  availability_zone = each.value.az
  image_id          = local.k8s_masters_settings[each.key].use_local_disk ? local.k8s_masters_settings[each.key].image_id : null
  flavor_id         = each.value.flavor
  key_pair          = var.key_pair
  user_data         = each.value.cloudinit != null ? templatefile("${path.module}/templates/cloudinit.yaml.tmpl", {
    extra_partitions = each.value.cloudinit.extra_partitions,
    netplan_critical_dhcp_interface = each.value.cloudinit.netplan_critical_dhcp_interface,
  }) : data.cloudinit_config.cloudinit.rendered
  dynamic "block_device" {
    for_each = !local.k8s_masters_settings[each.key].use_local_disk ? [local.k8s_masters_settings[each.key].image_id] : []
    content {
      uuid                  = block_device.value
      source_type           = "image"
      volume_size           = local.k8s_masters_settings[each.key].volume_size
      volume_type           = local.k8s_masters_settings[each.key].volume_type
      boot_index            = 0
      destination_type      = "volume"
      delete_on_termination = true
    }
  }

  network {
    port = openstack_networking_port_v2.k8s_masters_admin_port[each.key].id
  }
  metadata = {
    ssh_user         = var.ssh_user
    password         = var.password
    kubespray_groups = "%{if each.value.etcd == true}etcd,%{endif}kube_control_plane,${var.supplementary_master_groups},k8s_cluster%{if each.value.floating_ip == false},no_floating%{endif}"
    depends_on       = var.network_router_id
    use_access_ip    = var.use_access_ip
  }
  depends_on = [
    openstack_networking_trunk_v2.trunk_masters
  ]
  provisioner "local-exec" {
    command = "%{if each.value.floating_ip} %{if var.password == ""}sed -e s/USER/${var.ssh_user}/ -e s/BASTION_ADDRESS/${element([for key, value in var.k8s_masters_fips : value.address], 0)}/ ${path.module}/ansible_bastion_template.txt > ${var.group_vars_path}/no_floating.yml  %{else} sed -e s/PASSWORD/${var.password}/ -e s/USER/${var.ssh_user}/ -e s/BASTION_ADDRESS/${element([for key, value in var.k8s_masters_fips : value.address], 0)}/ ${path.module}/ansible_bastion_template_pass.txt > ${var.group_vars_path}/no_floating.yml%{endif}%{else}true%{endif}"  
  }
}


resource "openstack_networking_port_v2" "k8s_nodes_admin_port" {
  for_each              = var.number_of_k8s_nodes == 0 && var.number_of_k8s_nodes_no_floating_ip == 0 ? var.k8s_nodes : {}
  name                  = "${var.cluster_name}-k8s-${each.key}"
  network_id            = local.k8s_nodes_settings[each.key].admin_network_id
  admin_state_up        = "true"
  dynamic "fixed_ip" {
    for_each = var.private_subnet_id == "" ? [] : [true]
    content {
      subnet_id = var.private_subnet_id
    }
  }

  lifecycle {
    ignore_changes = [ allowed_address_pairs ]
  }

  depends_on = [
    var.network_router_id
  ]
}
resource "openstack_networking_port_v2" "k8s_nodes_bus_port" {
  for_each              = var.bus_network_id != "" && var.number_of_k8s_nodes == 0 && var.number_of_k8s_nodes_no_floating_ip == 0 ? var.k8s_nodes : {}
  name                  = "${var.cluster_name}-k8s-${each.key}"
  network_id            = local.k8s_nodes_settings[each.key].bus_network_id
  admin_state_up        = "true"
  dynamic "fixed_ip" {
    for_each = var.private_subnet_id == "" ? [] : [true]
    content {
      subnet_id = var.private_subnet_id
    }
  }

  lifecycle {
    ignore_changes = [ allowed_address_pairs ]
  }

  depends_on = [
    var.network_router_id
  ]
}

resource "openstack_networking_trunk_v2" "trunk_nodes" {
  for_each       =  var.bus_network_id != "" && var.number_of_k8s_nodes == 0 && var.number_of_k8s_nodes_no_floating_ip == 0 ? var.k8s_nodes : {}
  name           = "${var.cluster_name}-k8s-${each.key}"
  admin_state_up = "true"
  port_id        = openstack_networking_port_v2.k8s_nodes_admin_port[each.key].id
  sub_port {
    port_id           = openstack_networking_port_v2.k8s_nodes_bus_port[each.key].id
    segmentation_id   = local.segmentation_id
    segmentation_type = local.network_type
  }
}

resource "openstack_compute_instance_v2" "k8s_nodes" {
  for_each          = var.number_of_k8s_nodes == 0 && var.number_of_k8s_nodes_no_floating_ip == 0 ? var.k8s_nodes : {}
  name              = "${var.cluster_name}-k8s-${each.key}"
  availability_zone = each.value.az
  image_id          = local.k8s_nodes_settings[each.key].use_local_disk ? local.k8s_nodes_settings[each.key].image_id : null
  flavor_id         = each.value.flavor
  key_pair          = var.key_pair
  user_data         = each.value.cloudinit != null ? templatefile("${path.module}/templates/cloudinit.yaml.tmpl", {
    extra_partitions = each.value.cloudinit.extra_partitions,
    netplan_critical_dhcp_interface = each.value.cloudinit.netplan_critical_dhcp_interface,
  }) : data.cloudinit_config.cloudinit.rendered
  dynamic "block_device" {
    for_each = !local.k8s_nodes_settings[each.key].use_local_disk ? [local.k8s_nodes_settings[each.key].image_id] : []
    content {
      uuid                  = block_device.value
      source_type           = "image"
      volume_size           = local.k8s_nodes_settings[each.key].volume_size
      volume_type           = local.k8s_nodes_settings[each.key].volume_type
      boot_index            = 0
      destination_type      = "volume"
      delete_on_termination = true
    }
  }

  network {
    port = openstack_networking_port_v2.k8s_nodes_admin_port[each.key].id
  }
  metadata = {
    ssh_user         = var.ssh_user
    password         = var.password
    kubespray_groups = "kube_node,k8s_cluster,%{if !each.value.floating_ip}no_floating,%{endif}${var.supplementary_node_groups}${each.value.extra_groups != null ? ",${each.value.extra_groups}" : ""}"
    depends_on       = var.network_router_id
    use_access_ip    = var.use_access_ip
  }
  depends_on = [
    openstack_networking_trunk_v2.trunk_nodes
  ]
  provisioner "local-exec" {
    command = "%{if each.value.floating_ip} %{if var.password == ""}sed -e s/USER/${var.ssh_user}/ -e s/BASTION_ADDRESS/${element([for key, value in var.k8s_masters_fips : value.address], 0)}/ ${path.module}/ansible_bastion_template.txt > ${var.group_vars_path}/no_floating.yml  %{else} sed -e s/PASSWORD/${var.password}/ -e s/USER/${var.ssh_user}/ -e s/BASTION_ADDRESS/${element([for key, value in var.k8s_masters_fips : value.address], 0)}/ ${path.module}/ansible_bastion_template_pass.txt > ${var.group_vars_path}/no_floating.yml%{endif}%{else}true%{endif}"
  }
}
resource "openstack_networking_floatingip_associate_v2" "k8s_masters" {
  for_each              = var.number_of_k8s_masters == 0 && var.number_of_k8s_masters_no_etcd == 0 && var.number_of_k8s_masters_no_floating_ip == 0 && var.number_of_k8s_masters_no_floating_ip_no_etcd == 0 ? { for key, value in var.k8s_masters : key => value if value.floating_ip } : {}
  floating_ip           = var.k8s_masters_fips[each.key].address
  port_id               = openstack_networking_port_v2.k8s_masters_admin_port[each.key].id
}


resource "openstack_networking_floatingip_associate_v2" "k8s_nodes" {
  for_each              = var.number_of_k8s_nodes == 0 && var.number_of_k8s_nodes_no_floating_ip == 0 ? { for key, value in var.k8s_nodes : key => value if value.floating_ip } : {}
  floating_ip           = var.k8s_nodes_fips[each.key].address
  port_id               = openstack_networking_port_v2.k8s_nodes_admin_port[each.key].id
}