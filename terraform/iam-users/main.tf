module "s3" {
  source = "./modules/s3"

  bucket_configs = var.bucket_configs
  project_name   = var.project_name
  environment    = var.environment
}

module "iam" {
  source = "./modules/iam"

  project_name = var.project_name
  environment  = var.environment
  bucket_arn   = module.s3.bucket_arns["resilience-cloud-users"]
}

module "lambda" {
  source = "./modules/lambda"

  project_name       = var.project_name
  environment        = var.environment
  lambda_runtime     = var.lambda_runtime
  lambda_handler     = var.lambda_handler
  lambda_timeout     = var.lambda_timeout
  lambda_memory_size = var.lambda_memory_size

  bucket_name     = module.s3.bucket_names["resilience-cloud-users"]
  bucket_arn      = module.s3.bucket_arns["resilience-cloud-users"]
  lambda_role_arn = module.iam.lambda_role_arn

  # Descobertos pelo módulo sso (data source), NÃO declarados no tfvars
  identity_store_id = module.sso.identity_store_id
  sso_instance_arn  = module.sso.sso_instance_arn
}

module "sso" {
  source = "./modules/sso"

  environment = var.environment
}
