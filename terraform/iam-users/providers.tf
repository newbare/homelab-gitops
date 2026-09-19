terraform {
  # `moved` blocks exigem >= 1.1; `optional()` em object exige >= 1.3
  required_version = ">= 1.3"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # Credenciais NUNCA no código: o provider lê AWS_ACCESS_KEY_ID /
  # AWS_SECRET_ACCESS_KEY do ambiente (as mesmas que o aws CLI usa).

  # Flags do ambiente — default `false` (comportamento seguro em AWS real).
  skip_credentials_validation = var.skip_credentials_validation
  skip_metadata_api_check     = var.skip_metadata_api_check
  skip_requesting_account_id  = var.skip_requesting_account_id
  s3_use_path_style           = var.s3_use_path_style

  endpoints {
    s3            = var.floci_endpoint
    iam           = var.floci_endpoint
    lambda        = var.floci_endpoint
    ssoadmin      = var.floci_endpoint
    identitystore = var.floci_endpoint
    logs          = var.floci_endpoint
  }
}
