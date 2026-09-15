# Referências — Backstage no Homelab MK8s

Links úteis, documentação oficial, issues relevantes, e materiais que
ajudaram na implementação da Fase 7.

---

## 📚 Documentação oficial

### Backstage

| Recurso | URL |
|---|---|
| **Site oficial** | https://backstage.io |
| **Documentação** | https://backstage.io/docs |
| **Getting Started** | https://backstage.io/docs/getting-started |
| **GitHub (repo)** | https://github.com/backstage/backstage |
| **Changelog** | https://github.com/backstage/backstage/releases |
| **Blog** | https://backstage.io/blog |

### Frontend System (novo `/alpha`)

| Recurso | URL |
|---|---|
| **Frontend System (visão geral)** | https://backstage.io/docs/frontend-system |
| **Building plugins** | https://backstage.io/docs/frontend-system/building-plugins |
| **Extension blueprints** | https://backstage.io/docs/frontend-system/architecture/extension-blueprints |
| **Migrating to new frontend system** | https://backstage.io/docs/frontend-system/migrating |

**⚠️ Importante:** a API do novo frontend system (`/alpha`) é **relativamente nova** e mudou bastante entre versões. Sempre confira a doc da **versão exata** que você está usando.

### Helm Chart

| Recurso | URL |
|---|---|
| **Backstage Charts** | https://github.com/backstage/charts |
| **Artifact Hub** | https://artifacthub.io/packages/helm/backstage/backstage |
| **Values de referência** | https://github.com/backstage/charts/blob/main/charts/backstage/values.yaml |

### Configuração

| Recurso | URL |
|---|---|
| **app-config.yaml** | https://backstage.io/docs/conf/ |
| **Defining config** | https://backstage.io/docs/conf/defining |
| **Reading config** | https://backstage.io/docs/conf/reading |
| **Writing config schema** | https://backstage.io/docs/conf/writing |

---

## 🧩 Plugins usados

### Plugins registrados na Fase 7

| Plugin | Versão | Doc | GitHub |
|---|---|---|---|
| `@backstage/plugin-notifications` | (bundled) | [docs](https://backstage.io/docs/notifications/) | [github](https://github.com/backstage/backstage/tree/master/plugins/notifications) |
| `@backstage/plugin-search` | (bundled) | [docs](https://backstage.io/docs/features/search/) | [github](https://github.com/backstage/backstage/tree/master/plugins/search) |
| `@backstage/plugin-home` | (bundled) | [docs](https://backstage.io/docs/getting-started/homepage) | [github](https://github.com/backstage/backstage/tree/master/plugins/home) |
| `@backstage/plugin-home-react` | (bundled) | [docs](https://backstage.io/docs/getting-started/homepage) | [github](https://github.com/backstage/backstage/tree/master/plugins/home-react) |
| `@backstage/plugin-scaffolder` | (bundled) | [docs](https://backstage.io/docs/features/software-templates/) | [github](https://github.com/backstage/backstage/tree/master/plugins/scaffolder) |
| `@backstage/plugin-catalog` | (bundled) | [docs](https://backstage.io/docs/features/software-catalog/) | [github](https://github.com/backstage/backstage/tree/master/plugins/catalog) |

### Plugins planejados (Fase 8+)

| Plugin | Para quê |
|---|---|
| `@backstage/plugin-kubernetes` | Ver pods/deployments do cluster |
| `@backstage/plugin-github-actions` | Ver builds do GitHub Actions |
| `@backstage/plugin-techdocs` | Documentação técnica integrada |
| `@backstage/plugin-org` | Ver estrutura organizacional |
| `@backstage/plugin-api-docs` | Ver APIs (OpenAPI, GraphQL, gRPC) |
| `@backstage/plugin-grafana` | Dashboards de observabilidade |
| `@backstage/plugin-argo-cd` | Status dos apps ArgoCD |

---

## 🛠️ Ferramentas auxiliares

### Kubernetes / GitOps

| Ferramenta | URL | Uso |
|---|---|---|
| **kubectl** | https://kubernetes.io/docs/reference/kubectl/ | CLI do Kubernetes |
| **ArgoCD** | https://argo-cd.readthedocs.io/ | GitOps |
| **Helm** | https://helm.sh/docs/ | Gerenciador de pacotes |
| **Kustomize** | https://kustomize.io/ | Customização de YAML |
| **k9s** | https://k9scli.io/ | TUI pra Kubernetes |

### Desenvolvimento

| Ferramenta | URL | Uso |
|---|---|---|
| **Node.js** | https://nodejs.org/ | Runtime (v24.21.0) |
| **Yarn 1** | https://classic.yarnpkg.com/ | Gerenciador de pacotes (v1.22.22) |
| **Docker** | https://docs.docker.com/ | Build/push de imagens |
| **yamllint** | https://yamllint.readthedocs.io/ | Validação de YAML |

### Rede / Infra

| Ferramenta | URL | Uso |
|---|---|---|
| **MicroK8s** | https://microk8s.io/docs | Cluster Kubernetes |
| **MetalLB** | https://metallb.universe.tf/ | LoadBalancer bare-metal |
| **NGINX Ingress** | https://kubernetes.github.io/ingress-nginx/ | Ingress Controller |
| **cert-manager** | https://cert-manager.io/docs/ | Certificados TLS |
| **cert-manager selfsigned** | https://cert-manager.io/docs/configuration/selfsigned/ | Issuer auto-assinado |

---

## 💡 Conceitos-chave (referência rápida)

### GitOps de duas camadas

**Conceito:** no Backstage, o GitOps tem **duas camadas**:

1. **Git** — o `app.yaml` versionado no repositório
2. **Cluster** — o `Application` que o ArgoCD lê de verdade

**Implicação:** `git push` sozinho **não basta**. Precisa de
`kubectl apply -f infrastructure/backstage/app.yaml` pra propagar o novo
`Application` no cluster.

**Referência:** [ADR-004](./03-decisoes.md#adr-004-appconfig-no-helm-values-é-a-fonte-da-verdade-no-cluster)

### ConfigMap como fonte da verdade

**Conceito:** o pod **não lê** o `app-config.yaml` empacotado na imagem.
Ele lê o ConfigMap `/app/app-config-from-configmap.yaml`, gerado pelo
Helm.

**Implicação:** editar o `apps/backstage/app-config.yaml` **não muda** o
cluster. O que vale é o `appConfig` no `app.yaml` do Helm.

**Referência:** [ADR-004](./03-decisoes.md#adr-004-appconfig-no-helm-values-é-a-fonte-da-verdade-no-cluster)

### Imagens imutáveis

**Conceito:** usar tags únicas por build (`v3`, `v4`, `v7`) em vez de
`latest`.

**Implicação:** rollback fácil, rastreabilidade, cache de camadas.

**Referência:** [ADR-005](./03-decisoes.md#adr-005-tags-imutáveis-v7-em-vez-de-latest)

### Frontend System novo (`/alpha`)

**Conceito:** o Backstage está migrando do sistema antigo pro novo. O novo
usa **extension blueprints** (`PageBlueprint`, `HomePageWidgetBlueprint`,
etc.).

**Implicação:** plugins novos têm import `@backstage/plugin-X/alpha`.
Plugins antigos ainda funcionam (com import legado).

**Cuidado:** não misture `PageBlueprint` com extensões que **já registram
rota** (como `HomepageCompositionRoot`).

**Referência:** [ADR-003](./03-decisoes.md#adr-003-homemodule-só-com-widget-sem-pageblueprint)

---

## 🐛 Issues relevantes no GitHub

### Notifications plugin

- [#14867 — Add notifications plugin](https://github.com/backstage/backstage/issues/14867)
- [#22345 — Notifications: `alpha` export](https://github.com/backstage/backstage/pull/22345)

### Search plugin

- [#14173 — Search: novo frontend system](https://github.com/backstage/backstage/issues/14173)
- [#21793 — `plugin.search.queryservice` errors](https://github.com/backstage/backstage/issues/21793)

### Home plugin

- [#21124 — HomepageCompositionRoot with PageBlueprint](https://github.com/backstage/backstage/issues/21124)
- [#22567 — Home widget blueprints](https://github.com/backstage/backstage/issues/22567)

### Helm chart

- [#430 — Values de referência do chart](https://github.com/backstage/charts/issues/430)
- [#512 — Suporte a `appConfig` no chart](https://github.com/backstage/charts/issues/512)

### ArgoCD + ServerSideApply

- [#8400 — `--force` incompatível com `--server-side`](https://github.com/argoproj/argo-cd/issues/8400)

**⚠️ Nota:** os números podem estar desatualizados. Sempre busque no GitHub
pelo título.

---

## 📖 Leituras recomendadas

### Backstage

| Título | URL |
|---|---|
| **Backstage: The Missing Manual** | https://backstage.io/docs/getting-started/ |
| **Software Catalog 101** | https://backstage.io/docs/features/software-catalog/ |
| **Scaffolder templates** | https://backstage.io/docs/features/software-templates/ |
| **TechDocs** | https://backstage.io/docs/features/techdocs/ |
| **Permissions framework** | https://backstage.io/docs/permissions/ |

### GitOps

| Título | URL |
|---|---|
| **ArgoCD Docs** | https://argo-cd.readthedocs.io/ |
| **GitOps Principles** | https://opengitops.dev/ |
| **ArgoCD Best Practices** | https://argo-cd.readthedocs.io/en/stable/user-guide/best_practices/ |

### Kubernetes

| Título | URL |
|---|---|
| **Kubernetes Docs** | https://kubernetes.io/docs/ |
| **MicroK8s Docs** | https://microk8s.io/docs |
| **MetalLB Concepts** | https://metallb.universe.tf/concepts/ |

### Blogs e artigos

| Título | Autor | URL |
|---|---|---|
| **Building a developer portal with Backstage** | Vários | https://backstage.io/blog |
| **Migrating to the new frontend system** | Backstage team | https://backstage.io/docs/frontend-system/migrating |
| **Setting up MetalLB on MicroK8s** | Vários | https://microk8s.io/docs/addon-metallb |

---

## 🔗 Repositórios deste projeto

| Repo | Descrição | URL |
|---|---|---|
| **homelab-gitops** | GitOps (este repo) | https://github.com/newbare/homelab-gitops |
| **homelab-backstage** | Imagem customizada | https://hub.docker.com/r/newbare/homelab-backstage |
| **Backstage upstream** | Código-fonte do Backstage | https://github.com/backstage/backstage |
| **Backstage charts** | Helm chart oficial | https://github.com/backstage/charts |

### Arquivos-chave deste repo

| Arquivo | Descrição |
|---|---|
| `infrastructure/backstage/app.yaml` | `Application` do ArgoCD (fonte de verdade) |
| `infrastructure/backstage/ingress.yaml` | Ingress NGINX |
| `infrastructure/backstage/certificate.yaml` | Certificate cert-manager |
| `infrastructure/metallb/ipaddresspool.yaml` | Pool de IPs do MetalLB |
| `apps/backstage/` | Código-fonte do Backstage (customizado) |
| `apps/backstage/packages/app/src/plugins.ts` | Registro de plugins |
| `apps/backstage/packages/app/src/modules/home/homeModule.tsx` | Módulo da home |
| `apps/backstage/packages/app/src/modules/nav/Sidebar.tsx` | Sidebar |
| `docs/backstage/` | Esta documentação |

---

## 📝 Convenções deste projeto

### Commits

Formato: `<tipo>(<escopo>): <descrição>`

| Tipo | Uso |
|---|---|
| `feat` | Nova funcionalidade |
| `fix` | Correção de bug |
| `docs` | Documentação |
| `chore` | Manutenção (deps, config) |
| `refactor` | Refatoração |
| `test` | Testes |
| `revert` | Reverter commit |

**Exemplos:**

- `feat(backstage): adiciona plugin kubernetes`
- `fix(backstage): corrige CSP do Random Joke`
- `docs(backstage): adiciona troubleshooting`
- `chore(backstage): atualiza imagem para v8`

### Branches

| Padrão | Uso |
|---|---|
| `main` | Produção (protegida) |
| `docs/*` | Documentação |
| `feat/*` | Features |
| `fix/*` | Correções |
| `chore/*` | Manutenção |

### Tags de imagem

| Padrão | Uso |
|---|---|
| `vN` | Versão imutável (N incrementa) |
| `latest` | ❌ Nunca usar |

---

## 🤝 Como contribuir

1. Crie uma branch a partir de `main`:
   ```bash
   git checkout -b feat/minha-feature
   ```

2. Faça as mudanças, commit:
   ```bash
   git add .
   git commit -m "feat(backstage): descrição"
   ```

3. Push + PR:
   ```bash
   git push -u origin feat/minha-feature
   ```

4. Aguarde review (ou, se for o dono do repo, faça merge).

---

## 📅 Histórico de mudanças

| Data | Fase | Descrição |
|---|---|---|
| 2026-09-13 | Setup | MicroK8s + MetalLB + ArgoCD |
| 2026-09-14 | Fase 7 | Backstage customizado (v7) |
| 2026-09-15 | Fase 7 (docs) | Documentação retroativa |
| (próxima) | Fase 8 | A definir |

---

## 🔗 Ver também

- [`00-contexto.md`](./00-contexto.md) — motivação e stack
- [`01-arquitetura.md`](./01-arquitetura.md) — componentes e fluxo
- [`02-jornada-fase-7.md`](./02-jornada-fase-7.md) — cronológico
- [`03-decisoes.md`](./03-decisoes.md) — ADRs
- [`04-runbook.md`](./04-runbook.md) — operações comuns
- [`05-troubleshooting.md`](./05-troubleshooting.md) — erros conhecidos