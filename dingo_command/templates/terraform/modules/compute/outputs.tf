output "k8s_master_ips" {
  value = concat(
    values(openstack_compute_instance_v2.k8s-master),
    values(openstack_compute_instance_v2.k8s-master-no-floatip)
  )
}