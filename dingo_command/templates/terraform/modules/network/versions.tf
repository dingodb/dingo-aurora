terraform {
  required_providers {
    openstack = {
      source = "dingo.com/terraform-provider-openstack/openstack"
    }
  }
  required_version = ">= 0.12.26"
}
