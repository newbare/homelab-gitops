output "s3_bucket_name" {
  value = module.s3.bucket_names["resilience-cloud-users"]
}

output "s3_bucket_arn" {
  value = module.s3.bucket_arns["resilience-cloud-users"]
}

output "techdocs_bucket_name" {
  value = module.s3.bucket_names["resilience-techdocs"]
}

output "techdocs_bucket_arn" {
  value = module.s3.bucket_arns["resilience-techdocs"]
}

output "lambda_function_name" {
  value = module.lambda.function_name
}

output "lambda_function_arn" {
  value = module.lambda.function_arn
}

output "lambda_role_arn" {
  value = module.iam.lambda_role_arn
}

output "identity_store_id" {
  value = module.sso.identity_store_id
}
