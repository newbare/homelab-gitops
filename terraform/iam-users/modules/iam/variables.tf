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

variable "techdocs_bucket_arn" {
  description = "ARN do bucket S3 do TechDocs (publicado e lido pelo Backstage)"
  type        = string
}

# Das 5 ações que a doc do Backstage lista, `s3:ListBucket` é a ÚNICA no nível do
# bucket — as outras 4 são no nível do objeto. Por isso esta variável lista
# apenas as 4; a quinta é fixa no recurso do bucket, no main.tf.
variable "techdocs_publisher_object_actions" {
  description = "Ações S3 de objeto do publisher do TechDocs (mínimo documentado)"
  type        = list(string)
  default = [
    "s3:GetObject",
    "s3:PutObject",
    "s3:DeleteObject",
    "s3:DeleteObjectVersion",
  ]
}
