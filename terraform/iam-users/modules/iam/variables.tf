variable "project_name" {
  description = "Nome do projeto (para tags e naming)"
  type        = string
}

variable "environment" {
  description = "Ambiente (dev, uat, prd)"
  type        = string
}

variable "bucket_arn" {
  description = "ARN do bucket S3 (para permissões de leitura)"
  type        = string
}
