variable "bucket_configs" {
  description = "Buckets S3 do stack: a chave é o nome do bucket, o valor são as regras"
  type = map(object({
    versioning_status = string
    sse_algorithm     = string
    transition_days   = optional(number)
    storage_class     = optional(string)
    expiration_days   = optional(number)
  }))

  # `Disabled` não é valor inválido, mas o provider RECUSA atualizar um bucket
  # existente de 'Enabled' para 'Disabled'. Para desligar versionamento use
  # 'Suspended'. Aqui isso vira erro de plan, não de apply.
  validation {
    condition = alltrue([
      for cfg in var.bucket_configs : contains(["Enabled", "Suspended"], cfg.versioning_status)
    ])
    error_message = "versioning_status aceita apenas 'Enabled' ou 'Suspended'. 'Disabled' não pode ser aplicado a bucket existente."
  }
}

variable "project_name" {
  description = "Nome do projeto (para tags)"
  type        = string
}

variable "environment" {
  description = "Ambiente (dev, uat, prd)"
  type        = string
}
