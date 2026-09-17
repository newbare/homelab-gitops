variable "project_name" {
  description = "Nome do projeto"
  type        = string
}

variable "environment" {
  description = "Ambiente"
  type        = string
}

variable "lambda_runtime" {
  description = "Runtime da Lambda"
  type        = string
}

variable "lambda_handler" {
  description = "Handler da Lambda"
  type        = string
}

variable "lambda_timeout" {
  description = "Timeout em segundos"
  type        = number
}

variable "lambda_memory_size" {
  description = "Memória em MB"
  type        = number
}

variable "bucket_name" {
  description = "Nome do bucket S3"
  type        = string
}

variable "bucket_arn" {
  description = "ARN do bucket S3"
  type        = string
}

variable "lambda_role_arn" {
  description = "ARN da IAM Role da Lambda"
  type        = string
}

variable "identity_store_id" {
  description = "ID do Identity Store"
  type        = string
}

variable "sso_instance_arn" {
  description = "ARN da instância SSO"
  type        = string
}
