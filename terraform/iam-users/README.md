# IAM Users — Provisionamento via Terraform + Lambda

Provisiona **usuários IAM** e **usuários SSO (Identity Center)** no **Floci**
(AWS local emulado) a partir de uma planilha **XLSX**, usando uma **Lambda**
disparada por **S3 Event Notification**.

## 🔑 Credenciais — não ficam no código

O provider AWS **não** declara `access_key`/`secret_key`. Ele lê do ambiente:

```bash
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
```

⚠️ Sem elas o `terraform plan` falha com `No valid credential sources found`.
São as mesmas variáveis que o `aws` CLI usa.

## ⚙️ Flags do provider — por ambiente

O default é `false` de propósito (comportamento correto/seguro em AWS real).
O `terraform.tfvars` do Floci sobrescreve para `true`:

| Flag | Floci (tfvars) | AWS real (default) |
|---|---|---|
| `skip_credentials_validation` | `true` | `false` |
| `skip_metadata_api_check` | `true` | `false` |
| `skip_requesting_account_id` | `true` | `false` |
| `s3_use_path_style` | `true` | `false` |

Virar a chave para AWS real = parar de sobrescrever no tfvars. Nada de código.

## 🧭 Decisões estruturais (e fontes)

| Decisão | Por quê | Fonte |
|---|---|---|
| Buckets em `map(object)` com a **chave = nome do bucket** | um único lugar cria todos; cada bucket carrega as próprias regras | [for_each](https://developer.hashicorp.com/terraform/language/meta-arguments/for_each) |
| `optional()` nos campos de ciclo de vida | bucket sem `expiration_days` não expira objeto nenhum; tornar o campo obrigatório obrigaria a inventar um número | [optional attributes](https://developer.hashicorp.com/terraform/language/expressions/type-constraints#optional-object-type-attributes) |
| Blocos `moved` ao mudar o endereço de um recurso | move o endereço no state em vez de destruir/recriar o bucket | [refactoring](https://developer.hashicorp.com/terraform/language/modules/develop/refactoring) |
| `filter {}` na regra de lifecycle | no provider v5 a `rule` exige `filter` ou `prefix`; sem isso vira erro em versão futura | [s3_bucket_lifecycle_configuration](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_lifecycle_configuration) |
| Credenciais no ambiente, nunca no código | o provider lê `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | [provider aws](https://registry.terraform.io/providers/hashicorp/aws/latest/docs) |
| SSO derivado de `data.aws_ssoadmin_instances` | ARN da instância e Identity Store ID mudam com conta/região: são **dado descoberto**, não configuração | [aws_ssoadmin_instances](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/ssoadmin_instances) |

Regra geral adotada: **dado que a API fornece** (ARN, ID) → deriva do provider;
**dado que você configura** (nome de bucket, role, flags) → `terraform.tfvars`.

### ⚠️ Armadilha verificada — `versioning_status`

`"Disabled"` não é valor inválido: é **atualização proibida**. O provider recusa

```
Error: versioning_configuration.status cannot be updated from 'Enabled' to 'Disabled'
```

Para desligar o versionamento de um bucket existente use `"Suspended"` (verificado:
`0 to add, 1 to change, 0 to destroy`). Por isso o `validation` em
`modules/s3/variables.tf` recusa `"Disabled"` já no plan.

Buckets com status **diferentes** entre si funcionam normalmente — cada instância
do `for_each` carrega o próprio status.

## 🏗️ Arquitetura