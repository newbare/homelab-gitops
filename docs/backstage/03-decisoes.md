# Decisões Arquiteturais — Backstage no Homelab MK8s

Registro das decisões importantes tomadas durante a Fase 7.
Formato: ADR enxuto (Status, Data, Contexto, Decisão, Consequências,
Alternativas).

---

## ADR-001: Imagem customizada em vez de chart oficial puro

**Status:** Aceita
**Data:** 2026-09-14

### Contexto

O Backstage foi inicialmente instalado usando o **chart oficial**
(`backstage.github.io/charts`, versão `2.10.1`) com a **imagem oficial**
(`spotify/backstage`). Ao tentar customizar arquivos `.ts` (`plugins.ts`,
`homeModule.tsx`, `App.tsx`) e rebuildar a imagem, percebeu-se que **o chart
sobrescrevia** as customizações, aplicando uma config default.

### Investigação

Pesquisa na comunidade Backstage revelou que **customização é o padrão em
ambientes de produção**. Empresas rodam imagens próprias, geradas a partir
do código-fonte, e usam o chart oficial apenas como **scaffolding** do
Deployment — não como fonte de verdade da aplicação.

### Decisão

**Deletar tudo e voltar ao marco zero**, adotando:

1. **Imagem customizada** — `newbare/homelab-backstage`, buildada localmente
   com `yarn build:backend` + `docker build` + `docker push`
2. **`values.yaml` explícito** no `Application` do ArgoCD, com `appConfig`
   controlando toda a configuração de runtime
3. **Tags imutáveis** (`v3`, `v4`, `v5`, `v6`, `v7`) em vez de `latest`

### Consequências

**Positivas:**

- **Controle total** sobre o bundle da aplicação
- Customizações **persistem** entre deploys
- **Padrão de produção** (o que a comunidade faz)
- Rastreabilidade por tag imutável
- Rollback fácil (`v7` → `v6` → `v5`)

**Negativas:**

- **Retrabalho:** horas perdidas tentando fazer o chart oficial aceitar
  customizações
- **Manutenção extra:** agora é preciso rebuildar a imagem a cada mudança
  de código
- **Pipeline manual:** sem CI/CD, o build é local (`yarn` + `docker`)

### Alternativas consideradas

1. **Usar chart oficial sem customização** — descartada: perde a home
   customizada, plugins específicos, e identidade visual
2. **Fork do chart oficial** — descartada: overhead de manutenção de fork
3. **Usar chart + patches via `kustomize`** — descartada: complexidade
   adicional sem ganho real

---

## ADR-002: Home como raiz (`page:home` com `path: /`)

**Status:** Aceita
**Data:** 2026-09-14

### Contexto

O Backstage tem, por padrão, o **Catalog** como página raiz (`/`). A home
customizada (com widgets) fica em `/home`. Para um portal de developer, faz
mais sentido a **home** ser o ponto de entrada.

### Decisão

Configurar `page:home` com `path: /` no `app.extensions` do `appConfig`:

```yaml
app:
  extensions:
    - page:home:
        config:
          path: /
          defaultConfig:
            - component: HomePageSearchBar
              ...
```

O Catalog **permanece acessível em `/catalog`** (path default).

### Consequências

**Positivas:**

- Home com widgets é o **ponto de entrada** natural
- Catalog continua acessível na sidebar
- Padrão alinhado com portais de developer modernos

**Negativas:**

- Usuários acostumados com `/catalog` como raiz precisam se adaptar
- Precisa garantir que `/home` **também** funcione (por compatibilidade)

### Alternativas consideradas

1. **Catalog como raiz** — descartada: home com widgets é mais útil como
   landing page
2. **Redirect `/` → `/home` no Ingress** — descartada: Backstage é SPA, o
   redirect acontece no cliente (React Router), não no servidor
3. **Home em `/home` e Catalog em `/`** — descartada: home perde o papel de
   landing page

---

## ADR-003: `homeModule` só com widget (sem `PageBlueprint`)

**Status:** Aceita
**Data:** 2026-09-14

### Contexto

Ao tentar registrar a rota `/home` no `homeModule.tsx`, foi adicionada uma
`PageBlueprint` que renderizava o `HomepageCompositionRoot`. Isso causou o
erro:

```
Routable extension component with mount point routeRef{type=absolute,id=home}
was not discovered in the app element tree.
```

### Causa

O `HomepageCompositionRoot` é uma **routable extension** (registra uma rota).
Ao envolvê-la numa `PageBlueprint` (que **também** registra rota), o sistema
não consegue descobri-la — ela deixa de ser "elemento direto da árvore de
rotas".

### Decisão

**Remover a `PageBlueprint`** do `homeModule.tsx` e deixar só o widget:

```typescript
export const homeModule = createFrontendModule({
  pluginId: 'home',
  extensions: [gettingStartedWidget],  // sem PageBlueprint
});
```

O **`homePlugin`** (do `/alpha`) já registra a rota `/home` sozinho. O
`homeModule` só precisa **adicionar widgets** ao home.

### Consequências

**Positivas:**

- Erro resolvido
- `/home` funciona
- Código mais simples e alinhado com a arquitetura do frontend system novo

**Negativas:**

- Nenhuma identificada

### Alternativas consideradas

1. **Manter `PageBlueprint` e tentar envolver `HomepageCompositionRoot` de
   outra forma** — descartada: conflito arquitetural, não é o uso pretendido
2. **Não usar `homePlugin`** — descartada: perderia widgets prontos (starred,
   toolkit, etc.)

---

## ADR-004: `appConfig` no Helm values é a fonte da verdade no cluster

**Status:** Aceita
**Data:** 2026-09-14

### Contexto

Durante 90 min, editou-se o `apps/backstage/app-config.yaml` (no repo) e
rebuildou-se a imagem múltiplas vezes, esperando que a config fosse aplicada.
**Nada mudava no cluster.**

Investigação revelou que o pod **não lê** o `app-config.yaml` empacotado na
imagem. Ele lê:

```
/app/app-config-from-configmap.yaml
```

Gerado pelo **Helm chart** a partir do `spec.source.helm.values` do
`Application` do ArgoCD.

### Decisão

Adotar o **`appConfig` no Helm values** como **fonte da verdade** para
configuração de runtime no cluster. O `apps/backstage/app-config.yaml` do
repo é usado **apenas** para desenvolvimento local (`yarn dev`).

**Mantê-los em sincronia** quando possível, mas saber que:

| Arquivo | Onde vive | Lido por |
|---|---|---|
| `apps/backstage/app-config.yaml` | Bundle Docker | `yarn dev` (local) |
| `appConfig` no `app.yaml` (Helm values) | ConfigMap | Pod no cluster |

### Consequências

**Positivas:**

- **Clareza:** sabe-se exatamente qual arquivo controla o quê
- **Config sem rebuild:** mudar `appConfig` não exige rebuildar imagem
- **GitOps:** config versionada no `app.yaml`

**Negativas:**

- **Duplicação:** config vive em dois lugares (bundle + ConfigMap)
- **Risco de divergência:** se editar só um dos dois, ficam diferentes
- **Curva de aprendizado:** não é óbvio pra quem vem de outras stacks

### Alternativas consideradas

1. **Usar só o `app-config.yaml` do repo** — descartada: impossível no
   cluster (o ConfigMap sobrescreve)
2. **Usar só o `appConfig` do Helm values** — descartada: `yarn dev`
   precisa do `app-config.yaml` local
3. **Montar o `app-config.yaml` como volume** — descartada: o chart oficial
   já faz isso via ConfigMap

---

## ADR-005: Tags imutáveis (`v7` em vez de `latest`)

**Status:** Aceita
**Data:** 2026-09-14

### Contexto

A imagem `newbare/homelab-backstage` começou com tag `latest`. Isso
dificultava:

- Saber **qual versão** está rodando no cluster
- Fazer **rollback** pra versão anterior
- **Rastrear** qual mudança introduziu um bug

### Decisão

Adotar **tags imutáveis** (`v2`, `v3`, `v4`, `v5`, `v6`, `v7`), uma por
mudança significativa. Nunca usar `latest`.

### Consequências

**Positivas:**

- **Rastreabilidade:** `kubectl get pod` mostra a tag exata
- **Rollback:** `v7` → `v6` é só mudar no `app.yaml` + sync
- **Cache Docker:** camadas são reaproveitadas entre versões
- **Histórico:** cada tag tem um commit correspondente

**Negativas:**

- **Manutenção:** precisa lembrar de incrementar a tag a cada build
- **Espaço:** múltiplas imagens no Docker Hub (mitigado por camadas
  compartilhadas)

### Alternativas consideradas

1. **`latest` sempre** — descartada: impossível rastrear versão
2. **Hash do commit (`git-sha`)** — descartada: menos legível
3. **Semver (`1.0.0`, `1.0.1`)** — descartada: overkill pra homelab

---

## ADR-006: Secret separado para token GitHub

**Status:** Aceita
**Data:** 2026-09-14

### Contexto

A integração com GitHub exige um **Personal Access Token (PAT)**. O token
**não pode** ir em plaintext no `app.yaml` (repo público).

### Decisão

Armazenar o token em um **Secret separado** (`backstage-github-token`),
referenciado no `app.yaml` via `extraEnvVarsSecrets`:

```yaml
backstage:
  extraEnvVarsSecrets:
    - backstage-github-token
```

E usar no `appConfig` via variável de ambiente:

```yaml
integrations:
  github:
    - host: github.com
      token: ${GITHUB_TOKEN}   # expandido em runtime
```

### Consequências

**Positivas:**

- Token **nunca** vai pro Git
- **Rotação** sem rebuildar imagem
- Secret **separado** do Helm chart (pode ser gerenciado por outra ferramenta,
  ex: External Secrets Operator, Vault, etc.)
- Boa prática alinhada com 12-factor app

**Negativas:**

- **Passo extra** de setup (criar o Secret manualmente)
- Se o Secret for deletado, o pod perde integração GitHub

### Alternativas consideradas

1. **Token em plaintext no `app.yaml`** — descartada: repo público, risco
   de vazamento
2. **Token em `values.yaml` do Helm** — descartada: mesma coisa, vai pro Git
3. **Token em ConfigMap** — descartada: ConfigMaps não são seguros pra
   segredos (ficam em plaintext no etcd)

---

## ADR-007: `argocd app sync --replace` em vez de `--force`

**Status:** Aceita
**Data:** 2026-09-15

### Contexto

Ao tentar forçar o ArgoCD a regenerar o ConfigMap, usou-se:

```bash
argocd app sync backstage --force
```

Isso falhou com:

```
error validating options: --force cannot be used with --server-side
```

O `Application` usa `ServerSideApply=true` no `syncOptions`. O `--force`
é incompatível.

### Decisão

Usar `--replace` em vez de `--force`:

```bash
argocd app sync backstage --replace
```

### Diferença entre as flags

| Flag | O que faz |
|---|---|
| `--force` | Força **delete + recreate** de recursos (agressivo) |
| `--replace` | Substitui recursos via **kubectl replace** (mais suave) |
| `--server-side` | Usa **Server-Side Apply** (default neste projeto) |

`--force` e `--server-side` são mutuamente exclusivos. Como o projeto usa
Server-Side Apply, `--replace` é o caminho.

### Consequências

**Positivas:**

- Sync funciona
- ConfigMap regenerado corretamente
- Mantém o `ServerSideApply` (mais moderno que Client-Side)

**Negativas:**

- `--replace` é **menos agressivo** que `--force` — em alguns casos pode
  não resolver, e aí a solução é **deletar o recurso manualmente** antes do
  sync

### Alternativas consideradas

1. **Remover `ServerSideApply=true`** — descartada: perde os benefícios
   (melhor detecção de drift, ownership explícito)
2. **Usar `--force` e desabilitar `ServerSideApply` temporariamente** —
   descartada: gambiarra, quebra outros recursos

---

## ADR-008: Yarn 1 em vez de Yarn 4

**Status:** Aceita
**Data:** 2026-09-14

### Contexto

O Yarn tem duas versões principais em uso:

- **Yarn 1** (também chamado `yarn-classic`) — v1.x, estável, legado
- **Yarn 4** (também chamado `yarn-berry`) — v2+, moderno, PnP, ESM-first

O Backstage **1.54.0** foi scaffoldado com **Yarn 1.22.22** por padrão.
Ao tentar migrar pra Yarn 4, surgiram incompatibilidades.

### Decisão

**Manter Yarn 1.22.22** para o projeto Backstage. Não migrar pra Yarn 4
durante a Fase 7.

### Consequências

**Positivas:**

- **Compatibilidade garantida** com o scaffold do Backstage 1.54.0
- `yarn.lock` funciona sem ajustes
- Plugins e dependências do Backstage testados com Yarn 1
- Sem surpresas de PnP ou ESM

**Negativas:**

- **Yarn 1 está em modo de manutenção** (sem features novas)
- Performance inferior ao Yarn 4 em projetos grandes
- Algumas ferramentas modernas assumem Yarn 4+

### Alternativas consideradas

1. **Migrar pra Yarn 4** — descartada: risco de quebrar o build do Backstage
   sem ganho real no escopo do homelab
2. **Migrar pra pnpm** — descartada: mudaria o lockfile e exigiria
   revalidação completa
3. **Usar npm** — descartada: o Backstage é Yarn-first, mudar quebraria o
   `backstage-cli`

### Observação futura

Quando o Backstage oficialmente migrar pra Yarn 4 (ou quando o projeto
crescer muito), reavaliar. Por enquanto, **Yarn 1 é o caminho de menor
resistência**.

---

## ADR-009: PostgreSQL interno (bitnamilegacy) em vez de externo

**Status:** Aceita
**Data:** 2026-09-14

### Contexto

O Backstage precisa de um banco **PostgreSQL** (por padrão, suporta também
SQLite em dev). Existem duas opções no chart oficial:

1. **PostgreSQL interno** — StatefulSet dentro do namespace `backstage`,
   gerenciado pelo próprio Helm chart
2. **PostgreSQL externo** — banco provisionado à parte (Cloud SQL, RDS,
   outro cluster, etc.)

O homelab **não tem** um PostgreSQL externo provisionado.

### Decisão

Usar o **PostgreSQL interno** do chart oficial, com a imagem
**`bitnamilegacy/postgresql:15.4.0-debian-11-r10`**.

A escolha da imagem `bitnamilegacy` foi necessária porque a Bitnami
**descontinuou as imagens públicas** — as novas versões exigem registro.
A tag `bitnamilegacy` mantém as imagens antigas acessíveis.

### Consequências

**Positivas:**

- **Setup automático:** o chart cria StatefulSet + Service + Secret + PVC
- **Sem dependência externa:** tudo roda no cluster
- **Persistência:** PVC mantém os dados entre restarts
- **Backup fácil:** `kubectl exec` + `pg_dump`, ou snapshot do PVC
- **Custo zero:** nada extra pra provisionar

**Negativas:**

- **Acoplamento:** deletar o `Application` pode deletar o StatefulSet
  (a menos que o PVC seja protegido)
- **Sem HA:** single-node, sem replicação
- **Manutenção manual:** atualizar versão do PostgreSQL exige plano
- **Imagem legada:** `bitnamilegacy` é um workaround, não solução definitiva

### Alternativas consideradas

1. **PostgreSQL externo no mesmo cluster** (namespace `databases`) —
   descartada: adiciona complexidade sem ganho no escopo atual
2. **PostgreSQL gerenciado** (Neon, Supabase, etc.) — descartada: dependência
   de internet, latência, custo
3. **SQLite** — descartada: o chart oficial é PostgreSQL-first; SQLite perde
   features (search full-text, etc.)
4. **PostgreSQL em VM separada** — descartada: overkill pra homelab

### Observação futura

Se o cluster crescer (múltiplos apps precisando de PostgreSQL), considerar:

- **CloudNativePG Operator** — gerenciamento declarativo de PostgreSQL
- **PostgreSQL compartilhado** em namespace `databases`
- **Migração pra imagem oficial** (se a Bitnami reabrir ou se usar
  `bitnami/postgresql` com registro)

---

## ADR-010: Apenas `toolkit` e `world-clock` como widgets customizados

**Status:** Aceita
**Data:** 2026-09-14

### Contexto

O Backstage oferece **muitos widgets prontos** para a home. O
`defaultConfig` aceita uma lista de componentes. A questão: **quais widgets
usar**?

Alguns disponíveis:

- `HomePageSearchBar` — barra de busca
- `GettingStarted` — widget customizado (Markdown)
- `HomePageStarredEntities` — entidades favoritas
- `HomePageRandomJoke` — piada aleatória (API externa)
- `HomePageToolkit` — links rápidos
- `HomePageWorldClock` — relógios mundiais
- `HomePageMostVisited` — mais visitados
- `HomePageRecentlyVisited` — visitados recentemente
- `HomePageTopVisited` — top visitados
- `HomePageCompanyLogo` — logo customizado
- `HomePageMarkdown` — Markdown genérico

### Decisão

Usar **todos os widgets do scaffold** (Getting Started, Search Bar, Starred,
Random Joke, Toolkit, World Clock, Most Visited, Recently Visited), mas
configurar **explicitamente** apenas:

1. **`home-page-widget:home/toolkit`** — com links (Docs, GitHub,
   Contributing, Plugins Directory, Submit New Issue)
2. **`home-page-widget:home/world-clock`** — com timezones (NYC, UTC, STO,
   TYO)

Os outros widgets usam **defaults** (sem `config` extra).

### Consequências

**Positivas:**

- **Home útil** desde o primeiro acesso
- **Toolkit customizado** com links do projeto
- **World Clock** com timezones relevantes (Brasil + locais que você
  trabalha)
- **Zero código** para os widgets padrão

**Negativas:**

- **Random Joke** depende de API externa (`official-joke-api.appspot.com`),
  que é bloqueada por CSP → erro visível na home
- **Most Visited** e **Recently Visited** mostram aviso de "tracking não
  habilitado" (precisa de `api:home/visits: true`)
- **Starred Entities** fica vazia se o usuário não favoritar nada
- Muitos widgets = **mais ruído visual** para quem só quer o essencial

### Alternativas consideradas

1. **Só `GettingStarted`** — descartada: home muito vazia
2. **Todos os widgets + Random Joke removido** — descartada: melhor resolver
   o CSP do que remover (Random Joke é divertido)
3. **Widgets customizados no código** (`.tsx`) — descartada: overkill, os
   prontos atendem

### Observação futura

- **Habilitar Visit Tracking** (`api:home/visits: true` e
  `app-root-element:home/visit-listener: true`) pra popular Most/Recently
  Visited
- **Resolver o CSP** do Random Joke (`backend.csp.connect-src`)
- **Adicionar logo customizado** com `HomePageCompanyLogo`
- **Remover widgets que não fazem sentido** depois de um tempo de uso

---

## ADR-011: MetalLB como LoadBalancer interno

**Status:** Aceita
**Data:** 2026-09-13

### Contexto

O MicroK8s **não tem LoadBalancer nativo**. Por padrão, Services do tipo
`LoadBalancer` ficam com IP `<pending>` — sem acesso externo.

No homelab, o Ingress NGINX precisa de um IP "externo" pra ser acessível
do MacBook.

### Decisão

Usar **MetalLB** com o seguinte pool de IPs:

```yaml
# infrastructure/metallb/ipaddresspool.yaml
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: lab-pool
  namespace: metallb-system
spec:
  addresses:
    - 192.168.99.200-192.168.99.250
```

**Range:** `192.168.99.200` a `192.168.99.250` = **51 IPs**.

**Por que esse range específico:**

- O modem DHCP serve `192.168.99.1` a `192.168.99.199`
- O MetalLB usa `192.168.99.200` a `192.168.99.250`
- **Sem sobreposição** — evita conflito de IP

### Consequências

**Positivas:**

- **Ingress acessível** de qualquer máquina da LAN
- **IPs estáveis** dentro do cluster (o MetalLB gerencia)
- **Sem cloud** — tudo local
- **Fácil de expandir:** adicionar mais IPs é só editar o range
- **Padrão de mercado:** MetalLB é o LoadBalancer mais usado em clusters
  bare-metal

**Negativas:**

- **Acoplamento com a rede local:** se a rede mudar (ex: mudar de
  `192.168.99.0/24` pra outra faixa), o MetalLB precisa ser reconfigurado
- **DHCP do host pode conflitar:** o IP do host MicroK8s é atribuído por
  DHCP (não fixo). Se o modem mudar, o `/etc/hosts` do MacBook precisa ser
  atualizado
- **Range fixo:** 51 IPs é suficiente pro homelab, mas limitado se o
  cluster crescer muito

### Alternativas consideradas

1. **NodePort** — descartada: portas altas (30000-32767), feio
2. **`kubectl port-forward`** — descartada: manual, não persiste
3. **Ingress sem LoadBalancer** — descartada: Ingress precisa de IP externo
4. **Cloud LoadBalancer** — descartada: não há cloud no homelab
5. **MetalLB com range maior** — descartada: 51 IPs é suficiente
6. **Traefik como LoadBalancer** — descartada: MetalLB é mais simples

### Observação futura

- **Fixar o IP do host MicroK8s** (reserva DHCP no modem ou IP estático no
  servidor Linux) — ver seção 16.5 do [runbook](./04-runbook.md)
- **Considerar IPv6** se a rede suportar
- **Automatizar o `/etc/hosts`** (via Ansible ou script)

## 📌 Resumo das decisões

| ADR | Decisão | Impacto |
|---|---|---|
| 001 | Imagem customizada vs chart oficial puro | 🔴 Alto (retrabalho, mas controle total) |
| 002 | Home como raiz (`page:home path:/`) | 🟡 Médio (UX) |
| 003 | `homeModule` só com widget | 🟡 Médio (corrige erro) |
| 004 | `appConfig` do Helm é a fonte da verdade | 🔴 Alto (evita 90 min de debug) |
| 005 | Tags imutáveis (`v7`) | 🟢 Baixo (boa prática) |
| 006 | Secret separado pra token | 🟡 Médio (segurança) |
| 007 | `--replace` vs `--force` | 🟢 Baixo (corrige erro) |
| 008 | Yarn 1 em vez de Yarn 4 | 🟡 Médio (compatibilidade) |
| 009 | PostgreSQL interno (bitnamilegacy) | 🟡 Médio (custo/complexidade) |
| 010 | Apenas `toolkit` e `world-clock` customizados | 🟢 Baixo (polish) |
| 011 | MetalLB como LoadBalancer interno | 🟡 Médio (rede local) |

## 🔗 Ver também

- [`00-contexto.md`](./00-contexto.md) — motivação e stack
- [`01-arquitetura.md`](./01-arquitetura.md) — componentes e fluxo
- [`02-jornada-fase-7.md`](./02-jornada-fase-7.md) — cronológico
- [`04-runbook.md`](./04-runbook.md) — operações comuns