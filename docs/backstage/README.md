# Backstage — Homelab MK8s

Backstage é o portal de developer do homelab MK8s. Ele centraliza
catálogo de serviços, templates de scaffolder, documentação técnica,
e (futuramente) observabilidade do cluster.

## 🌐 Acesso

- **URL:** https://backstage.local
- **Auth:** **OIDC via Keycloak** (realm `resilience`) — desde a Fase 11
- **Ingress:** NGINX, com TLS self-signed (`backstage-tls`)

## 🗂️ Estrutura da documentação

| Documento | Conteúdo |
|---|---|
| [`00-contexto.md`](./00-contexto.md) | Motivação, stack, ambiente |
| [`01-arquitetura.md`](./01-arquitetura.md) | Diagrama, componentes, fluxo |
| [`02-jornada-fase-7.md`](./02-jornada-fase-7.md) | Cronológico da Fase 7 |
| [`03-decisoes.md`](./03-decisoes.md) | ADRs (decisões arquiteturais) |
| [`04-runbook.md`](./04-runbook.md) | Operações comuns |
| [`05-troubleshooting.md`](./05-troubleshooting.md) | Erros conhecidos e soluções |
| [`06-referencias.md`](./06-referencias.md) | Links úteis |
| [`07-fase-8-polish.md`](./07-fase-8-polish.md) | Jornada da Fase 8 (polish visual) |
| [`09-fase-9-floci-terraform-lambda.md`](./09-fase-9-floci-terraform-lambda.md) | Jornada da Fase 9 |
| [`10-fase-11-backstage-oidc.md`](./10-fase-11-backstage-oidc.md) | **Jornada da Fase 11 — login OIDC via Keycloak** |

### Documentos relacionados (fora desta pasta)

| Documento | Conteúdo |
|---|---|
| [`../certificados/01-trust-anchor-interno.md`](../certificados/01-trust-anchor-interno.md) | A CA interna e por que folha rotativa não se copia |
| [`../praticas/README.md`](../praticas/README.md) | Práticas de Git/CLI e verificação usadas no repo |
| [`../../infrastructure/backstage/README.md`](../../infrastructure/backstage/README.md) | Os manifestos e as pegadinhas do chart |

## 🔗 Repositórios

| Repo | URL |
|---|---|
| GitOps (este) | https://github.com/newbare/homelab-gitops |
| Imagem Docker | https://hub.docker.com/r/newbare/homelab-backstage |
| Backstage upstream | https://github.com/backstage/backstage |
| Helm chart | https://github.com/backstage/charts |

## 🚦 Status atual

| Componente | Status |
|---|---|
| Backstage rodando | ✅ |
| Home customizada na raiz (`/`) | ✅ |
| Search | ✅ |
| Catalog | ✅ |
| Scaffolder | ✅ |
| Notifications | ✅ |
| TechDocs | ⚠️ Configurado, sem docs |
| Kubernetes plugin | ❌ Não configurado |
| **Auth real (OIDC Keycloak)** | ✅ Fase 11 |
| Permissões/RBAC por grupo | ❌ Grupos existem, sem permissões |
| CSP (Random Joke) | ⚠️ Pendente |

## 📌 Regras do projeto

Este projeto segue **GitOps declarativo**:

1. **Toda mudança é feita no Git.**
   **Exceção obrigatória:** Applications **baseadas em chart** (`source.chart`)
   não são lidas do Git pelo ArgoCD — o objeto `Application` vive no cluster.
   Para essas, o commit **precisa** ser seguido de
   `kubectl apply -f infrastructure/<app>/app.yaml`.
   Ver [`../../infrastructure/backstage/README.md`](../../infrastructure/backstage/README.md).
2. **ArgoCD sincroniza automaticamente** (auto-sync + self-heal ativos)
3. **Imagens são imutáveis** (v1, v2, v3... — nunca `latest`)
4. **Decisões são documentadas** (ADRs em `03-decisoes.md`)
5. **Exceções são registradas** no `04-runbook.md`