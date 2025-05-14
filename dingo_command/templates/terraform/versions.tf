terraform {
  required_providers {
    openstack = {
      source  = "dingo.com/terraform-provider-openstack/openstack"
      version = "1.54.1"
    }
    cloudinit = {
      source  = "dingo.com/hashicorp/cloudinit"
      version = "2.3.7"
    }
  }
  required_version = ">= 1.3.0"
}
