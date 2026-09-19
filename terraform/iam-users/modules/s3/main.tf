# ============================================
# Buckets S3 — declarados em um único lugar
# ============================================
# A CHAVE do mapa `bucket_configs` (terraform.tfvars) é o nome do bucket.
# Adicionar bucket = adicionar uma entrada no tfvars; o resto do módulo não muda.
# Cada bucket carrega as próprias regras (versionamento e ciclo de vida).
resource "aws_s3_bucket" "this" {
  for_each = var.bucket_configs

  bucket = each.key

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Module      = "s3"
  }
}

# Versionamento — o status vem da configuração de cada bucket
resource "aws_s3_bucket_versioning" "this" {
  for_each = var.bucket_configs

  bucket = aws_s3_bucket.this[each.key].id

  versioning_configuration {
    status = each.value.versioning_status
  }
}

# Criptografia em repouso — o algoritmo vem da configuração de cada bucket
resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = var.bucket_configs

  bucket = aws_s3_bucket.this[each.key].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = each.value.sse_algorithm
    }
  }
}

# ============================================
# Ciclo de vida — uma regra por bucket
# ============================================
# Só é criado para buckets que declaram ao menos uma ação: o provider rejeita
# `rule` sem transição e sem expiração.
# `transition` e `expiration` são opcionais por bucket — bucket sem
# `expiration_days` NÃO expira objeto nenhum.
resource "aws_s3_bucket_lifecycle_configuration" "this" {
  for_each = {
    for name, cfg in var.bucket_configs : name => cfg
    if cfg.transition_days != null || cfg.expiration_days != null
  }

  bucket = aws_s3_bucket.this[each.key].id

  rule {
    id     = "lifecycle-${each.key}"
    status = "Enabled"

    # `filter` vazio = regra vale para todos os objetos do bucket.
    # Obrigatório no provider v5 (sem ele, vira erro em versão futura).
    filter {}

    dynamic "transition" {
      for_each = each.value.transition_days == null || each.value.storage_class == null ? [] : [each.value.transition_days]
      content {
        days          = transition.value
        storage_class = each.value.storage_class
      }
    }

    dynamic "expiration" {
      for_each = each.value.expiration_days == null ? [] : [each.value.expiration_days]
      content {
        days = expiration.value
      }
    }
  }
}

# ============================================
# Migração de endereço — sem destruir/recriar
# ============================================
# Contexto histórico: o state ficou com a chave = finalidade ("users"/"techdocs")
# porque a chave passou a ser o NOME do bucket. Estes blocos moveram o endereço
# no state em vez de destruir/recriar, e já foram aplicados.
#
# Mantidos comentados por decisão de 2026-09-19, apenas como contexto histórico.
# O Floci é efêmero e o state é local, então não há uso operacional previsto.
# A deleção fica ELEITA PARA O FUTURO caso deixem de ser necessários: o rationale
# também vive no commit dc1f080, então remover não apaga o porquê.
# moved {
#   from = aws_s3_bucket.this["users"]
#   to   = aws_s3_bucket.this["resilience-cloud-users"]
# }

# moved {
#   from = aws_s3_bucket.this["techdocs"]
#   to   = aws_s3_bucket.this["resilience-techdocs"]
# }

# moved {
#   from = aws_s3_bucket_versioning.this["users"]
#   to   = aws_s3_bucket_versioning.this["resilience-cloud-users"]
# }

# moved {
#   from = aws_s3_bucket_versioning.this["techdocs"]
#   to   = aws_s3_bucket_versioning.this["resilience-techdocs"]
# }

# moved {
#   from = aws_s3_bucket_server_side_encryption_configuration.this["users"]
#   to   = aws_s3_bucket_server_side_encryption_configuration.this["resilience-cloud-users"]
# }

# moved {
#   from = aws_s3_bucket_server_side_encryption_configuration.this["techdocs"]
#   to   = aws_s3_bucket_server_side_encryption_configuration.this["resilience-techdocs"]
# }
