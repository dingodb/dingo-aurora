
data "openstack_images_image_v2" "vm_image" {
  count = var.image_uuid == "" ? 1 : 0
  most_recent = true
  name = var.image
}


data "openstack_images_image_v2" "image_master" {
  count = var.image_master_uuid == "" ?  1 : 0
  name = var.image_master
}

data "cloudinit_config" "masters-cloudinit" {
  for_each = var.masters
  part {
    content_type =  "text/cloud-config"
    content = templatefile("${path.module}/templates/cloudinit-master.yaml.tmpl", {
      extra_partitions = [],
      netplan_critical_dhcp_interface = "",
      ssh_user = var.ssh_user,
      password = var.password,
      pushgateway_url = var.pushgateway_url,
      pushgateway_user = var.pushgateway_user,
      pushgateway_pass = var.pushgateway_pass,
      etcd_volume_type = var.etcd_volume_type,
      cluster_id = var.cluster_id
    })
  }
}

data "openstack_networking_network_v2" "admin_network" {
  network_id = var.admin_network_id
}

#data "openstack_networking_network_v2" "bus_network" {
#  network_id = var.bus_network_id
#}

resource "random_integer" "master_port" {
  min   = 0
  max   = 40000
}
resource "random_string" "secgroup_suffix" {
  length  = 4
  special = false
  upper   = true
  lower   = true
  numeric = true
}
# create key pair
resource "openstack_compute_keypair_v2" "key_pair" {
  count      = (var.public_key_path != null && var.public_key_path != "") ? 1 : 0
  name       = "${var.cluster_name}-${random_string.secgroup_suffix.result}"
  public_key = var.public_key_path != "" ? chomp(file(var.public_key_path)) : ""
}

# Check if flavor exists
#data "openstack_compute_flavor_v2" "k8s_control" {
  #name = "k8s_control"  # 替换为你的 Flavor 名称

#  flavor_id = var.flavor_k8s_master
#}

resource "openstack_networking_secgroup_v2" "secgroup" {
  name        = "${var.cluster_name}-${random_string.secgroup_suffix.result}"
  description = "cluster default security group"
  tenant_id = var.tenant_id
}

# 入站规则 - 允许所有端口和协议
resource "openstack_networking_secgroup_rule_v2" "allow_all_ingress" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 0
  port_range_max    = 0
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = openstack_networking_secgroup_v2.secgroup.id
}

resource "openstack_networking_secgroup_rule_v2" "allow_all_ingress_udp" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "udp"
  port_range_min    = 0
  port_range_max    = 0
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = openstack_networking_secgroup_v2.secgroup.id
}

resource "openstack_networking_secgroup_rule_v2" "allow_all_ingress_icmp" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "icmp"
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = openstack_networking_secgroup_v2.secgroup.id
}

# 出站规则 - 允许所有端口和协议
resource "openstack_networking_secgroup_rule_v2" "allow_all_egress" {
  direction         = "egress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 0
  port_range_max    = 0
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = openstack_networking_secgroup_v2.secgroup.id
}

resource "openstack_networking_secgroup_rule_v2" "allow_all_egress_udp" {
  direction         = "egress"
  ethertype         = "IPv4"
  protocol          = "udp"
  port_range_min    = 0
  port_range_max    = 0
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = openstack_networking_secgroup_v2.secgroup.id
}

resource "openstack_networking_secgroup_rule_v2" "allow_all_egress_icmp" {
  direction         = "egress"
  ethertype         = "IPv4"
  protocol          = "icmp"
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = openstack_networking_secgroup_v2.secgroup.id
}
locals {

# Image uuid
  image_to_use_node = var.image_uuid != "" ? var.image_uuid : data.openstack_images_image_v2.vm_image[0].id
  image_to_use_master = var.image_master_uuid != "" ? var.image_master_uuid : data.openstack_images_image_v2.image_master[0].id
  master_flavor = var.flavor_k8s_master
  nodes_settings = {
    for name, node in var.nodes :
      name => {
        "key_pair"       = length(openstack_compute_keypair_v2.key_pair) > 0 ? openstack_compute_keypair_v2.key_pair[0].name : "",
        "password"       = var.password,
        "use_local_disk" = node.use_local_disk,
        "image_id"       = node.image_id != null ? node.image_id : local.image_to_use_node,
        "volume_size"    = node.volume_size,
        "volume_type"    = node.volume_type,
        "data_volumes"   = node.data_volumes != null ? node.data_volumes : [],
        #"admin_network_id"   = node.network_id != null ? node.network_id : (var.use_existing_network ? data.openstack_networking_network_v2.admin_network[0].id : var.admin_network_id)
        #"bus_network_id"     = node.network_id != null ? node.network_id : (var.use_existing_network && var.bus_network_id != "" ? data.openstack_networking_network_v2.bus_network[0].id : var.bus_network_id)
        #"server_group"   = node.server_group != null ? node.server_group : openstack_compute_servergroup_v2.secgroup[0].id
      }
  }

  masters_settings = {
    for name, node in var.masters :
      name => {
        "key_pair"       = length(openstack_compute_keypair_v2.key_pair) > 0 ? openstack_compute_keypair_v2.key_pair[0].name : "",
        "password"       = var.password,
        "use_local_disk" = node.use_local_disk,
        "image_id"       = node.image_id != null ? node.image_id : local.image_to_use_master,
        "volume_size"    = node.root_volume_size_in_gb != null ? node.root_volume_size_in_gb : var.master_root_volume_size_in_gb,
        "volume_type"    = node.volume_type != null ? node.volume_type : var.master_volume_type,
        #"admin_network_id"     = node.network_id != null ? node.network_id : (var.use_existing_network  && var.admin_network_id != "" ? data.openstack_networking_network_v2.admin_network[0].id : var.admin_network_id)
        #"bus_network_id"     = node.network_id != null ? node.network_id : (var.use_existing_network && var.bus_network_id != "" ? data.openstack_networking_network_v2.bus_network[0].id : var.bus_network_id)
        #"server_group"   = node.server_group != null ? node.server_group : openstack_compute_servergroup_v2.secgroup[0].id
      }
  }
}

resource "openstack_networking_port_v2" "masters_port" {
  for_each              = var.masters
  name                  = "${var.cluster_name}-master-${each.key}"
  network_id            = data.openstack_networking_network_v2.admin_network.id
  admin_state_up        = "true"
  security_group_ids    = [openstack_networking_secgroup_v2.secgroup.id]
  #port_security_enabled = var.force_null_port_security ? null : var.port_security_enabled
  #no_security_groups    = var.port_security_enabled ? null : false
  # 添加可用地址对配置
  allowed_address_pairs {
    ip_address = var.pod_cidr
  }
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

resource "openstack_compute_instance_v2" "masters" {
  for_each          = var.masters
  name              = "${var.cluster_name}-${each.key}"
  availability_zone = each.value.az
  config_drive      = true             # 启用 config_drive
  image_id          = local.masters_settings[each.key].image_id
  flavor_id         = each.value.flavor
  key_pair          = length(openstack_compute_keypair_v2.key_pair) > 0 ? openstack_compute_keypair_v2.key_pair[0].name : ""
  user_data         = data.cloudinit_config.masters-cloudinit[each.key].rendered
  # Master 节点启动盘配置
  # 注意：此配置已被注释，master 节点使用 flavor 默认磁盘启动
  # dynamic "block_device" {
  #   for_each = local.masters_settings[each.key].use_local_disk == true ? [local.masters_settings[each.key].image_id] : []
  #   content {
  #     uuid                  = block_device.value
  #     source_type           = "image"
  #     volume_size           = local.masters_settings[each.key].volume_size
  #     volume_type           = local.masters_settings[each.key].volume_type
  #     boot_index            = 0
  #     destination_type      = "volume"
  #     delete_on_termination = true
  #   }
  # }
  tags = ["kubernetes control"]
  security_groups        = [openstack_networking_secgroup_v2.secgroup.name]
  network {
    port = openstack_networking_port_v2.masters_port[each.key].id
  }
  metadata = {
    ssh_user         = var.ssh_user
    password         = var.password
    kubespray_groups = "etcd,kube_control_plane,${var.supplementary_master_groups},cluster"
    depends_on       = var.network_router_id
    use_access_ip    = var.use_access_ip
  }
  depends_on = [
    openstack_networking_secgroup_v2.secgroup
  ]
}


###############################################worker node################################################
###############################################worker node################################################
resource "openstack_networking_port_v2" "nodes_port" {
  for_each              = var.number_of_nodes == 0 && var.number_of_nodes_no_floating_ip == 0 ? var.nodes : {}
  name                  = "${var.cluster_name}-node-${each.key}"
  network_id            = data.openstack_networking_network_v2.admin_network.id
  admin_state_up        = "true"
  security_group_ids    = [openstack_networking_secgroup_v2.secgroup.id]
  #port_security_enabled = var.force_null_port_security ? null : var.port_security_enabled
  #no_security_groups    = var.port_security_enabled ? null : false
  allowed_address_pairs {
    ip_address = var.pod_cidr
  }
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

#resource "openstack_networking_floatingip_associate_v2" "master" {
#  count                 = var.number_of_k8s_masters
#  floating_ip           = var.k8s_master_fips[count.index]
#  port_id               = element(openstack_networking_port_v2.admin_master_port.*.id, count.index)
#}

#resource "openstack_networking_floatingip_associate_v2" "master" {
#  count                 = var.number_of_k8s_masters
#  floating_ip           = var.k8s_master_fips[0]
#  port_id               = element(openstack_networking_port_v2.admin_master_port.*.id, 0)
#}

# resource "openstack_networking_floatingip_associate_v2" "masters" {
#   for_each              = var.number_of_k8s_masters == 0 && var.number_of_k8s_masters_no_etcd == 0 && var.number_of_k8s_masters_no_floating_ip == 0 && var.number_of_k8s_masters_no_floating_ip_no_etcd == 0 ? { for key, value in var.masters : key => value if value.floating_ip } : {}
#   floating_ip           = var.masters_fips[each.key].address
#   port_id               = openstack_networking_port_v2.masters_port[each.key].id
# }

# resource "openstack_networking_floatingip_associate_v2" "nodes" {
#   for_each              = var.number_of_nodes == 0 && var.number_of_nodes_no_floating_ip == 0 ? { for key, value in var.nodes : key => value if value.floating_ip } : {}
#   floating_ip           = var.nodes_fips[each.key].address
#   port_id               = openstack_networking_port_v2.nodes_port[each.key].id
# }

# resource "openstack_networking_trunk_v2" "trunk_nodes" {
#   for_each       =  var.bus_network_id != "" && var.number_of_nodes == 0 && var.number_of_nodes_no_floating_ip == 0 ? var.nodes : {}
#   name           = "${var.cluster_name}-k8s-${each.key}"
#   admin_state_up = "true"
#   port_id        = openstack_networking_port_v2.nodes_admin_port[each.key].id
#   sub_port {
#     port_id           = openstack_networking_port_v2.nodes_bus_port[each.key].id
#     segmentation_id   = local.segmentation_id
#     segmentation_type = local.network_type
#   }
# }

data "cloudinit_config" "nodes_cloudinit" {
  for_each = var.number_of_nodes == 0 && var.number_of_nodes_no_floating_ip == 0 ? var.nodes : {}
  
  part {
    content_type = "text/cloud-config"
    content = templatefile("${path.module}/templates/cloudinit.yaml.tmpl", {
      extra_partitions = [],
      netplan_critical_dhcp_interface = "",
      ssh_user = var.ssh_user,
      password = var.password,
      pushgateway_url = var.pushgateway_url,
      pushgateway_user = var.pushgateway_user,
      pushgateway_pass = var.pushgateway_pass,
      cluster_id = var.cluster_id,
      az = each.value.az
    })
  }
}

resource "openstack_compute_instance_v2" "nodes" {
  for_each          = var.number_of_nodes == 0 && var.number_of_nodes_no_floating_ip == 0 ? var.nodes : {}
  name              = "${var.cluster_name}-${each.key}"
  availability_zone = each.value.az
  config_drive      = true             # 启用 config_drive
  image_id          = local.nodes_settings[each.key].use_local_disk == true ? local.nodes_settings[each.key].image_id : null
  flavor_id         = each.value.flavor
  key_pair          = length(openstack_compute_keypair_v2.key_pair) > 0 ? openstack_compute_keypair_v2.key_pair[0].name : ""
  user_data         = data.cloudinit_config.nodes_cloudinit[each.key].rendered
  # 启动盘
  dynamic "block_device" {
    for_each = local.nodes_settings[each.key].use_local_disk == false ? [local.nodes_settings[each.key].image_id] : []
    content {
      uuid                  = block_device.value
      source_type           = "image"
      volume_size           = local.nodes_settings[each.key].volume_size
      volume_type           = local.nodes_settings[each.key].volume_type
      boot_index            = 0
      destination_type      = "volume"
      delete_on_termination = true
    }
  }
  
  # 数据盘
  dynamic "block_device" {
    for_each = local.nodes_settings[each.key].data_volumes
    content {
      source_type           = "blank"
      destination_type      = "volume"
      volume_size           = block_device.value.volume_size
      volume_type           = block_device.value.volume_type
      boot_index            = local.nodes_settings[each.key].use_local_disk == true ? block_device.key : block_device.key + 1
      delete_on_termination = true
    }
  }

  tags = var.number_of_k8s_masters == 0 ? ["worker node"] : ["kubernetes worker node"]
  security_groups        = [openstack_networking_secgroup_v2.secgroup.name]
  network {
    port = openstack_networking_port_v2.nodes_port[each.key].id
  }
  metadata = {
    ssh_user         = var.ssh_user
    password         = var.password
    kubespray_groups = "kube_node,cluster"
    depends_on       = var.network_router_id
    use_access_ip    = var.use_access_ip
  }
  depends_on = [
    openstack_networking_secgroup_v2.secgroup
  ]
}

#resource "openstack_networking_portforwarding_v2" "pf_1" {
#  for_each         = var.number_of_nodes == 0 && var.number_of_nodes_no_floating_ip == 0  var.forward_float_ip_id != ""? var.nodes : {}
#  floatingip_id    = var.forward_float_ip_id
#  external_port    = var.forward_out_port
#  internal_port    = var.forward_in_port
#  internal_port_id = openstack_networking_port_v2.nodes_port[each.key].id
#  protocol         = "tcp"
#  depends_on = [
#    openstack_compute_instance_v2.nodes
#  ]
#}
locals {
  # 检查是否满足执行端口转发的条件
  should_create_port_forwarding = (
    var.number_of_nodes == 0 && 
    var.number_of_nodes_no_floating_ip == 0 && 
    var.forward_float_ip_id != null &&
    var.forward_float_ip_id != ""
  )
  
  # 创建所有节点的所有端口转发的映射
  port_forwarding_mappings = flatten([
    for node_key, node in var.nodes : [
      # 判断节点是否有 port_forwards 配置
      for port_mapping in (node.port_forwards != null ? node.port_forwards : []) : {
        node_key      = node_key             # 节点标识
        mapping_key   = "${node_key}-${port_mapping.internal_port}"  # 创建唯一键
        external_port = port_mapping.external_port                   # 外部端口
        internal_port = port_mapping.internal_port                   # 内部端口
        protocol      = port_mapping.protocol                        # 协议
        internal_ip   = openstack_compute_instance_v2.nodes[node_key].network[0].fixed_ip_v4  # 内部IP
      }
    ]
  ])
  
  # 转换为 for_each 所需的 map 格式
  port_forwarding_map = {
    for mapping in local.port_forwarding_mappings : 
      mapping.mapping_key => mapping
    if var.forward_float_ip_id != "" && var.forward_float_ip_id != null
  }
}
resource "openstack_networking_portforwarding_v2" "pf_multi" {
  for_each = local.port_forwarding_map

  floatingip_id    = var.forward_float_ip_id
  external_port    = each.value.external_port
  internal_port    = each.value.internal_port
  internal_port_id = openstack_networking_port_v2.nodes_port[each.value.node_key].id
  protocol         = each.value.protocol
  internal_ip_address = each.value.internal_ip
  depends_on = [
    openstack_compute_instance_v2.nodes
  ]
}