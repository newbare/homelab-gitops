# Contexto — Backstage no Homelab MK8s

## 🎯 Motivação

Eu já conhecia o Backstage de outros ambientes, mas **nunca tinha
implementado do zero**. O objetivo da Fase 7 foi:

1. **Aprender na prática** como o Backstage funciona por dentro
2. **Ter um portal funcional** para o homelab MK8s
3. **Documentar a jornada** para replicar em outros projetos
4. **Melhorar skills** em Kubernetes, GitOps, Helm e Backstage

A Fase 7 começou em **14/09/2026 às 11:00** e durou **13 horas**.

## 🖥️ Ambiente

| Item | Valor |
|---|---|
| **Máquina de trabalho** | MacBook Intel  (2020) |
| **Servidor** | Linux (MicroK8s) AMD 16 RAM 750 Storage |
| **OS MicroK8s** | MicroK8s v1.35.6 revision 9072 |
| **Cluster** | MicroK8s single-node |
| **Ingress** | NGINX Ingress Controller |
| **TLS** | cert-manager + selfsigned-issuer |
| **GitOps** | ArgoCD v3.5.2 |

## 🛠️ Stack técnica

| Componente | Versão |
|---|---|
| **Backstage** | 1.54.0 |
| **Helm chart Backstage** | 2.10.1 |
| **kubectl (client)** | v1.35.8 |
| **kubectl (server)** | v1.35.6 |
| **Kustomize** | v5.7.1 |
| **Node.js** | v24.21.0 |
| **Yarn** | 1.22.22 |
| **Docker** | 29.7.2 |

## 📦 Repositórios

| Repo | Visibilidade | URL |
|---|---|---|
| **GitOps** | Público | https://github.com/newbare/homelab-gitops |
| **Imagem Docker** | Público | https://hub.docker.com/r/newbare/homelab-backstage |

### Tags de imagem publicadas

| Tag | Descrição |
|---|---|
| v2 | (histórico) |
| v3 | Adiciona notificationsPlugin |
| v4 | Corrige import (default export) |
| v5 | Registra searchPlugin + homePlugin + scaffolderPlugin |
| v6 | Registra PageBlueprint `/home` (depois removida) |
| v7 | Home na raiz + widgets (atual) |

## 🏗️ Estado ANTES da Fase 7

O homelab já tinha:

- ✅ MicroK8s rodando
- ✅ ArgoCD configurado (com auto-sync)
- ✅ NGINX Ingress Controller
- ✅ cert-manager (selfsigned-issuer)
- ✅ PostgreSQL interno (via Helm chart do Backstage)
- ❌ Backstage ainda **não** funcional (múltiplos erros)

## 🎯 Estado DEPOIS da Fase 7

- ✅ Backstage rodando na v7
- ✅ Home customizada (widgets: Getting Started, Toolkit, World Clock, Starred, etc.)
- ✅ Todos os plugins registrados (search, notifications, scaffolder)
- ✅ ConfigMap gerado corretamente pelo Helm
- ⚠️ CSP do Random Joke pendente
- ⚠️ Auth ainda em guest

## 📐 Decisões de design (resumo)

| Decisão | Escolha | Alternativa descartada |
|---|---|---|
| Imagem | Customizada (`newbare/homelab-backstage`) | Oficial `spotify/backstage` |
| Tag | Imutável (`v7`, `v6`, ...) | `latest` |
| Root page | Home (`page:home`) | Catalog (`page:catalog`) |
| Fonte de config | `appConfig` do Helm values | `app-config.yaml` do bundle |
| Auth | Guest | OAuth GitHub |
| GitOps | Auto-sync + self-heal | Sync manual |

## 🔗 Ver também

- [`01-arquitetura.md`](./01-arquitetura.md) — como os componentes se conectam
- [`02-jornada-fase-7.md`](./02-jornada-fase-7.md) — o que aconteceu na Fase 7
- [`03-decisoes.md`](./03-decisoes.md) — ADRs detalhadas