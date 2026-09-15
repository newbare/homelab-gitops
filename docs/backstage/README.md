# Backstage — Homelab MK8s

Backstage é o portal de developer do homelab MK8s. Ele centraliza
catálogo de serviços, templates de scaffolder, documentação técnica,
e (futuramente) observabilidade do cluster.

## 🌐 Acesso

- **URL:** https://backstage.local
- **Auth:** guest (por enquanto — Fase 8 planeja OAuth GitHub)
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
| Auth real | ❌ Guest apenas |
| CSP (Random Joke) | ⚠️ Pendente |

## 📌 Regras do projeto

Este projeto segue **GitOps declarativo**:

1. **Toda mudança é feita no Git** (nada de `kubectl apply` manual)
2. **ArgoCD sincroniza automaticamente** (auto-sync + self-heal ativos)
3. **Imagens são imutáveis** (v1, v2, v3... — nunca `latest`)
4. **Decisões são documentadas** (ADRs em `03-decisoes.md`)
5. **Exceções são registradas** no `04-runbook.md`