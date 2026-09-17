variable "identity_store_id" {
  description = "ID do Identity Store"
  type        = string
}

variable "sso_instance_arn" {
  description = "ARN da instância SSO"
  type        = string
}

variable "environment" {
  description = "Ambiente"
  type        = string
}
