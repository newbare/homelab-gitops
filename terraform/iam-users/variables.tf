variable "environment" {
  type = string
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "floci_endpoint" {
  type = string
}

# Flags do provider. Default `false` = comportamento correto/seguro em AWS real;
# o tfvars do Floci sobrescreve para `true`.
variable "skip_credentials_validation" {
  type    = bool
  default = false
}

variable "skip_metadata_api_check" {
  type    = bool
  default = false
}

variable "skip_requesting_account_id" {
  type    = bool
  default = false
}

variable "s3_use_path_style" {
  type    = bool
  default = false
}

variable "project_name" {
  type = string
}

variable "bucket_configs" {
  type = map(object({
    versioning_status = string
    sse_algorithm     = string
    transition_days   = optional(number)
    storage_class     = optional(string)
    expiration_days   = optional(number)
  }))
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
