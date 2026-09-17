module "s3" {
  source = "./modules/s3"

  bucket_name  = var.bucket_name
  project_name = var.project_name
  environment  = var.environment
}

module "iam" {
  source = "./modules/iam"

  project_name = var.project_name
  environment  = var.environment
  bucket_arn   = module.s3.bucket_arn
}

module "lambda" {
  source = "./modules/lambda"

  project_name       = var.project_name
  environment        = var.environment
  lambda_runtime     = var.lambda_runtime
  lambda_handler     = var.lambda_handler
  lambda_timeout     = var.lambda_timeout
  lambda_memory_size = var.lambda_memory_size

  bucket_name     = module.s3.bucket_name
  bucket_arn      = module.s3.bucket_arn
  lambda_role_arn = module.iam.lambda_role_arn

  identity_store_id = var.identity_store_id
  sso_instance_arn  = var.sso_instance_arn
}

module "sso" {
  source = "./modules/sso"

  identity_store_id = var.identity_store_id
  sso_instance_arn  = var.sso_instance_arn
  environment       = var.environment
}
