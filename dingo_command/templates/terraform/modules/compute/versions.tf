terraform {
  required_providers {
    openstack = {
      source  = "dingo.com/terraform-provider-openstack/openstack"
    }
    cloudinit = {
      source  = "dingo.com/hashicorp/cloudinit"
    }
    random = {
      source = "dingo.com/hashicorp/random"
    }
  }
  required_version = ">= 1.3.0"
}
