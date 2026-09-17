variable "bucket_name" {
  description = "Nome do bucket S3"
  type        = string
}

variable "project_name" {
  description = "Nome do projeto (para tags)"
  type        = string
}

variable "environment" {
  description = "Ambiente (dev, uat, prd)"
  type        = string
}
