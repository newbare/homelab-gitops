environment = "dev"

aws_region     = "us-east-1"
floci_endpoint = "http://192.168.99.5:4566"

# Só o ambiente emulado precisa destes flags (o default é `false`)
skip_credentials_validation = true
skip_metadata_api_check     = true
skip_requesting_account_id  = true
s3_use_path_style           = true

project_name = "resilience-cloud"

bucket_configs = {
  "resilience-cloud-users" = {
    versioning_status = "Enabled"
    sse_algorithm     = "AES256"
    transition_days   = 90
    storage_class     = "STANDARD_IA"
  }

  "resilience-techdocs" = {
    versioning_status = "Enabled"
    sse_algorithm     = "AES256"
    transition_days   = 30
    storage_class     = "ONEZONE_IA"
  }
}

# Dados do Identity Center NÃO ficam aqui: são descobertos pelo data source
# aws_ssoadmin_instances (modules/sso).

lambda_runtime     = "python3.12"
lambda_handler     = "handler.lambda_handler"
lambda_timeout     = 60
lambda_memory_size = 256
