# ============================================
# Data Source — DESCOBRE a instância do Identity Center
# ============================================
# O ARN da instância e o Identity Store ID mudam quando se troca de conta ou
# região (em AWS real). Por isso são descobertos aqui, e não declarados no
# tfvars — dado que a API fornece não é configuração.
data "aws_ssoadmin_instances" "this" {}

# O Floci já cria a instância SSO automaticamente.
locals {
  identity_store_id = tolist(data.aws_ssoadmin_instances.this.identity_store_ids)[0]
  sso_instance_arn  = tolist(data.aws_ssoadmin_instances.this.arns)[0]
}
