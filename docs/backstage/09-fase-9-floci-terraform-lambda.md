```markdown
# Jornada — Fase 9 (Floci + Terraform + Lambda Serverless)

Documentação da Fase 9 — provisionamento de **infraestrutura AWS local emulada**
com **Floci** + **Terraform CAF** + **Lambda serverless** disparada por
**S3 Event Notification**, criando usuários IAM + SSO a partir de uma
planilha XLSX.

## 🎯 Objetivo

1. Subir o **Floci** (AWS local emulado) no Ubuntu
2. Provisionar infra com **Terraform** (padrão CAF)
3. Lambda que **lê XLSX do S3** e cria:
   - IAM users/groups
   - SSO users/groups (Identity Store)
   - catalog-info.yaml (Backstage-ready)
4. **S3 Event Notification** dispara a Lambda automaticamente

## 📅 Timeline

- **Início:** 16/09/2026, noite
- **Duração:** ~5h
- **Fases:** Investigação → Floci → Terraform → Lambda → Testes

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│  1. Terraform (MacBook)                                     │
│     - Cria S3 bucket                                        │
│     - Cria IAM Role + Lambda + S3 Event                     │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Upload users.xlsx (S3 / UI Floci)                       │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  3. S3 Event Notification → Lambda                          │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Lambda roda (Python 3.12):                              │
│     - Lê XLSX do S3                                         │
│     - Cria IAM users/groups                                 │
│     - Cria SSO users/groups                                 │
│     - Gera catalog-info.yaml                                │
│     - Upload do YAML no S3                                  │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  5. (Futuro) Backstage importa catalog-info.yaml            │
└─────────────────────────────────────────────────────────────┘
```

## 🔍 Decisão: Floci vs LocalStack vs Keycloak

| Critério | Floci | LocalStack | Keycloak |
|---|---|---|---|
| **Free** | ✅ MIT | ⚠️ Token desde 2026 | ✅ |
| **Startup** | 24ms | 3.3s | ~10s |
| **Memória** | 13 MiB | 143 MiB | ~500 MiB |
| **Serviços** | 119 | 70 | SSO apenas |
| **CPU** | ⚠️ AVX2 (binário) | ✅ | ✅ |

**Decisão:** **Floci via Docker** (multi-arch, roda em qualquer CPU).

**Contexto:** o CPU do servidor é um **AMD A10-7860K (2016)** que **não tem AVX2/BMI2**. O binário nativo do Floci crashou. **Docker resolveu.**

## 🚧 Becos sem saída

### 1. Binário nativo do Floci (AVX2)

**O que tentamos:** instalar o `floci-cli` via `curl | sh`.

**O que deu errado:**

```
The current machine does not support all of the following CPU features 
that are required by the image: [CX8, CMOV, ..., AVX2, BMI1, BMI2, FMA, F16C].
```

**Solução:** usar **`floci/floci` via Docker** (multi-arch).

### 2. Docker Hub via IPv6

**O que tentamos:** `docker pull`.

**O que deu errado:** timeout em `[2600:1f18:...]` (IPv6 sem rota).

**Solução:** `/etc/docker/daemon.json` com `ipv6: false` + DNS público.

### 3. Storage sem persistência

**O que tentamos:** `FLOCI_STORAGE=persistent` (errado).

**O que deu errado:** a variável correta é `FLOCI_STORAGE_MODE=hybrid`.

**Solução:** usar `hybrid` (leitura em memória + flush async pro disco).

### 4. Lambda sem rede compartilhada

**O que tentamos:** só `docker run` com `-p 4566:4566`.

**O que deu errado:** a Lambda **não conseguia** se comunicar com o Floci.

**Solução:** criar `floci-network` + `FLOCI_HOSTNAME=floci` + `FLOCI_SERVICES_LAMBDA_DOCKER_NETWORK=floci-network`.

### 5. `pip install` global no macOS

**O que tentamos:** `pip install --user openpyxl`.

**O que deu errado:** PEP 668 (externally-managed-environment).

**Solução:** `python3 -m venv /tmp/venv-X`.

## 🎓 Insights principais

### 1. Floci é o "LocalStack killer"

- **24ms startup** vs 3.3s
- **13 MiB** vs 143 MiB
- **119 serviços** vs 70
- **MIT forever** vs token obrigatório

### 2. Docker é a salvação em CPUs antigas

GraalVM Native Image **exige AVX2**. Docker **não exige**.

### 3. Terraform CAF é o padrão de mercado

```
raiz/               → main.tf, providers.tf, variables.tf, outputs.tf
modules/            → s3/, iam/, lambda/, sso/
env/{dev,uat,prd}/  → state isolado por ambiente
```

### 4. S3 Event → Lambda funciona no Floci

**Formato do evento idêntico à AWS real:**

```json
{
  "Records": [{
    "eventSource": "aws:s3",
    "eventName": "ObjectCreated:Put",
    "s3": {
      "bucket": {"name": "..."},
      "object": {"key": "..."}
    }
  }]
}
```

### 5. Lambda Python com deps via ZIP

`data "archive_file"` **não instala deps**. Precisa `build.sh` manual.

### 6. Idempotência é essencial

A Lambda pode rodar **múltiplas vezes** (retries do S3). Precisa `try/except EntityAlreadyExistsException`.

## 📌 Resultado final

| Recurso | Criado |
|---|---|
| S3 bucket | `resilience-cloud-users` |
| IAM Role | `resilience-cloud-dev-lambda-role` |
| Lambda | `resilience-cloud-dev-process-users` |
| S3 Event Notification | `.xlsx` → Lambda |
| IAM Users | `jefferson.leite`, `maria.silva`, `joao.santos`, `ana.costa` |
| IAM Groups | `resilience-admins`, `resilience-devs`, `resilience-viewers` |
| SSO Users | 4 no Identity Store |
| catalog-info.yaml | 4 arquivos no S3 |

## 📊 Estatísticas

| Métrica | Valor |
|---|---|
| **Duração** | ~5h |
| **Arquivos no PR** | 25 |
| **Linhas** | ~874 |
| **Commits** | 6 |
| **Becos sem saída** | 5 |
| **Insights** | 6 |

## 🔗 Ver também

- [`02-jornada-fase-7.md`](./02-jornada-fase-7.md)
- [`07-fase-8-polish.md`](./07-fase-8-polish.md)
- [`03-decisoes.md`](./03-decisoes.md)
- [Floci](https://floci.io)
- [CAF Landing Zone](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/)
```

---

## ▶️ Passo 4 — Verificar

```bash
cd ~/mk8s/homelab-gitops

wc -l docs/backstage/09-fase-9-floci-terraform-lambda.md
grep -c "^## " docs/backstage/09-fase-9-floci-terraform-lambda.md
head -10 docs/backstage/09-fase-9-floci-terraform-lambda.md
```

**Esperado:**

- `wc -l`: ~240 linhas
- `grep -c "^## "`: ~10 seções
- `head`: começa com `# Jornada — Fase 9...`

## ▶️ Passo 5 — Commit + push

```bash
cd ~/mk8s/homelab-gitops

git add docs/backstage/09-fase-9-floci-terraform-lambda.md
git commit -m "docs(backstage): adiciona jornada da Fase 9 (Floci + Terraform + Lambda)"
git push origin main
```

## ▶️ Passo 6 — Verificar no GitHub

```
https://github.com/newbare/homelab-gitops/blob/main/docs/backstage/09-fase-9-floci-terraform-lambda.md
```

## 🎯 Ação agora

**Roda os Passos 1-4** (verificar estado + criar com `vim` + validar) e me manda:

```bash
cd ~/mk8s/homelab-gitops
git branch --show-current
git status
wc -l docs/backstage/09-fase-9-floci-terraform-lambda.md
```


