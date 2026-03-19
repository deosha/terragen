terraform {
  required_version = "~&gt; 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~&gt; 5.40"
    }

    archive = {
      source  = "hashicorp/archive"
      version = "~&gt; 2.4"
    }
  }
}
