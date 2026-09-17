variable "environment" {
  type = string
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_account_id" {
  type    = string
  default = "000000000000"
}

variable "floci_endpoint" {
  type = string
}

variable "project_name" {
  type = string
}

variable "bucket_name" {
  type = string
}

variable "identity_store_id" {
  type = string
}

variable "sso_instance_arn" {
  type = string
}

variable "lambda_runtime" {
  type    = string
  default = "python3.12"
}

variable "lambda_handler" {
  type    = string
  default = "handler.lambda_handler"
}

variable "lambda_timeout" {
  type    = number
  default = 60
}

variable "lambda_memory_size" {
  type    = number
  default = 256
}
