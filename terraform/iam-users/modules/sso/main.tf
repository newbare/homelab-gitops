# ============================================
# Data Sources — valida Identity Store
# ============================================
data "aws_ssoadmin_instances" "this" {}

# NOTA: O Floci já cria a instância SSO automaticamente.
# Este módulo apenas valida que ela existe e expõe o ID.

locals {
  identity_store_id = var.identity_store_id
  sso_instance_arn  = var.sso_instance_arn
}
