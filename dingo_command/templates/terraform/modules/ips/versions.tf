terraform {
  required_providers {
    null = {
      source = "dingo.com/hashicorp/null"
    }
    openstack = {
      source = "dingo.com/terraform-provider-openstack/openstack"
    }
  }
  required_version = ">= 0.12.26"
}
