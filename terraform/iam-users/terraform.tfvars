environment = "dev"

aws_region     = "us-east-1"
aws_account_id = "000000000000"
floci_endpoint = "http://192.168.99.5:4566"

project_name = "resilience-cloud"
bucket_name  = "resilience-cloud-users"

identity_store_id = "d-9067f2a3c1"
sso_instance_arn  = "arn:aws:sso:::instance/ssoins-7223b02a5d9f7c8e"

lambda_runtime     = "python3.12"
lambda_handler     = "handler.lambda_handler"
lambda_timeout     = 60
lambda_memory_size = 256
