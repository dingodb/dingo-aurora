output "k8s_master_ips" {
  value = [for m in openstack_compute_instance_v2.masters : m]
}