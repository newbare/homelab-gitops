### Etapa 4 — Debug home/scaffolder (60 min)

**Sintoma:** após registrar o `searchPlugin`, apareceram erros similares para
os plugins **home** e **scaffolder**.

```
plugin.home.service não registrado
plugin.scaffolder.service não registrado
```

**Investigação:**

- Verificar se `@backstage/plugin-home` e `@backstage/plugin-scaffolder`
  tinham `/alpha`
- Testar se o problema era o mesmo do search (registro no `plugins.ts`)
- **Confirmar que o `Sidebar.tsx` usava `nav.take('page:home')` e
  `nav.take('page:scaffolder')`** — ou seja, dependia dos plugins registrados

**Solução:** adicionar ao `plugins.ts`:

```typescript
export { default as homePlugin } from '@backstage/plugin-home/alpha';
export { default as scaffolderPlugin } from '@backstage/plugin-scaffolder/alpha';
```

**Resultado:** erros sumiram, mas **apareceu um novo erro mais crítico**.

### Etapa 5 — Debug `Routable extension` (45 min)

**Sintoma:** após registrar home + scaffolder, o Backstage **quebrou** com:

```
Routable extension component with mount point routeRef{type=absolute,id=home}
was not discovered in the app element tree. Routable extension components
may not be rendered by other components and must be directly available as
an element within the App provider component.
```

**Tradução do erro:** o `HomepageCompositionRoot` é uma **routable extension**
(registra uma rota). Quando colocada dentro de uma `PageBlueprint` no
`homeModule.tsx`, o sistema **não consegue descobri-la** na árvore de rotas.

**Investigação:**

- Ler a doc do frontend system novo (`/alpha`)
- Entender a diferença entre `PageBlueprint` (define rota) e
  `HomepageCompositionRoot` (renderiza home)
- Perceber que **o `homePlugin` já registra a rota `/home` sozinho**

**Tentativa que não funcionou:** manter a `PageBlueprint` e tentar
"envolver" o `HomepageCompositionRoot` de outra forma.

**Solução:** **remover a `PageBlueprint` duplicada** do `homeModule.tsx` e
deixar só o widget:

```typescript
// apps/backstage/packages/app/src/modules/home/homeModule.tsx
import { createFrontendModule } from '@backstage/frontend-plugin-api';
import { HomePageWidgetBlueprint } from '@backstage/plugin-home-react/alpha';
import { MarkdownContent } from '@backstage/core-components';

const gettingStartedWidget = HomePageWidgetBlueprint.make({
  name: 'getting-started',
  params: {
    name: 'GettingStarted',
    title: 'Getting Started',
    // ...
  },
});

export const homeModule = createFrontendModule({
  pluginId: 'home',
  extensions: [gettingStartedWidget],  // sem PageBlueprint
});
```

**Resultado:** `/home` passou a funcionar! Mas a **raiz `/` ainda dava 404**.

### Etapa 6 — Descoberta do ConfigMap (90 min) ⬅️ o mais caro

**Sintoma:** `/home` funcionava, mas `/` (raiz) dava `ERROR 404: PAGE NOT FOUND`.

**Investigação inicial (errônea):**

- Tentar registrar `page:home` no `app-config.yaml` do repo
- Tentar várias combinações no `plugins.ts`
- Rebuildar imagem múltiplas vezes (v5, v6, v7)

**Nada funcionava.** O `curl` retornava 200, mas o browser mostrava 404.
**Por quê?** Porque o Backstage é uma **SPA (Single Page Application)** — o
servidor sempre responde 200 com o HTML, e **o React Router decide o que
renderizar no cliente**. Um 200 do servidor **não significa que a rota
funciona**.

**Descoberta crítica:** ao rodar

```bash
kubectl -n backstage get configmap backstage-app-config -o yaml
```

o conteúdo **não tinha** `app.extensions`, `page:home`, nem `defaultConfig`.
O ConfigMap **nunca tinha sido atualizado** com as mudanças do `app.yaml`.

**Por quê?**

O Backstage **não lê o `app-config.yaml` empacotado na imagem** no cluster.
Ele lê o ConfigMap `backstage-app-config`, gerado pelo **Helm chart** a partir
do `spec.source.helm.values` do **`Application` do ArgoCD**.

**E o `Application` do ArgoCD** (que vive no cluster, em `argocd/backstage`)
**não lê o `app.yaml` do Git automaticamente**. Ele só é atualizado via
`kubectl apply -f infrastructure/backstage/app.yaml`.

**Traduzindo:** havia **3 camadas** entre o que você editava no Git e o que o
pod lia:

```
Git (app.yaml)  →  Application (cluster)  →  ConfigMap  →  Pod
   ↑                      ↑                      ↑           ↑
 editar               kubectl apply          argocd sync   restart
```

**Solução final:**

1. Editar `infrastructure/backstage/app.yaml` com o `app.extensions` correto
2. **`kubectl apply -f infrastructure/backstage/app.yaml`** (propaga pro
   `Application` no cluster)
3. **`argocd app sync backstage --replace`** (regenera o ConfigMap — sem
   `--force`, que conflita com `--server-side`)
4. **`kubectl rollout restart deployment backstage`** (recria o pod)

**Resultado:** o ConfigMap foi regenerado com:

```yaml
app:
  extensions:
  - page:home:
      config:
        path: /
        defaultConfig:
        - component: HomePageSearchBar
          ...
  - home-page-widget:home/toolkit:
      ...
  - home-page-widget:home/world-clock:
      ...
  packages: all
```

**E a home finalmente renderizou na raiz `/`!** 🎉

### Etapa 7 — CSP + polish (60 min)

**Sintoma:** a home funcionava, mas o widget **Random Joke** mostrava erro
`Failed to fetch`.

**Causa:** Content Security Policy (CSP) bloqueava chamadas para
`https://official-joke-api.appspot.com`:

```
Refused to connect because it violates the document's Content Security Policy.
"default-src 'self'"
```

**Solução (pendente, não aplicada ainda):** adicionar
`backend.csp.connect-src` no `app.yaml`:

```yaml
backend:
  csp:
    connect-src:
      - "'self'"
      - "https:"
```

**Status:** **pendente**. É um ajuste de polish, não bloqueia o uso.

## 🚧 Becos sem saída (o que NÃO funcionou)

### 1. Usar o chart oficial do Backstage sem customização

**O que tentamos:** instalar o chart oficial e usar a imagem oficial
(`spotify/backstage`) sem build próprio.

**O que deu errado:** o chart oficial **sobrescrevia** os ajustes feitos em
arquivos `.ts` (`plugins.ts`, `homeModule.tsx`, `App.tsx`). Mesmo após rebuild
da imagem, o chart aplicava uma config default que **ignorava** as
customizações.

**Solução:** **imagem customizada** (`newbare/homelab-backstage`) +
`values.yaml` com `appConfig` explícito, sobrescrevendo o chart.

### 2. Editar `.ts` sem rebuildar a imagem

**O que tentamos:** editar `plugins.ts` / `homeModule.tsx` e esperar que o pod
pegasse as mudanças.

**O que deu errado:** o pod roda a **imagem Docker** (bundle compilado). Editar
o fonte não muda nada até você rodar:

```bash
yarn build:backend
docker build -t newbare/homelab-backstage:vN -f packages/backend/Dockerfile .
docker push newbare/homelab-backstage:vN
```

### 3. Registrar `page:home` só no `app-config.yaml` do repo

**O que tentamos:** editar `apps/backstage/app-config.yaml` e rebuildar.

**O que deu errado:** o pod **não lê** esse arquivo no cluster — ele lê o
ConfigMap gerado pelo Helm. Editar o `app-config.yaml` do repo **não tem
efeito**.

### 4. Tentar `--force` com `--server-side`

**O que tentamos:** `argocd app sync backstage --force` pra forçar atualização
do ConfigMap.

**O que deu errado:**

```
error validating options: --force cannot be used with --server-side
```

**Solução:** usar `--replace` em vez de `--force`:

```bash
argocd app sync backstage --replace
```

### 5. Tentar redirect de `/` via Ingress

**O que tentamos:** adicionar annotations no Ingress pra redirecionar `/` para
`/home`.

**O que deu errado:** o Backstage é uma SPA — o redirecionamento no servidor
não resolve, porque **o roteamento é do cliente (React Router)**. Um 302 do
servidor ainda mostraria a home vazia.

**Solução:** registrar `page:home` com `path: /` no `app.extensions` do
`appConfig`. Aí o próprio Backstage decide que a home é a raiz.

## 🎓 7 insights principais

### 1. Editar `.ts` não afeta o pod

O pod roda um **bundle compilado** dentro da imagem Docker. Editar o fonte
**não muda nada** até você:

```bash
yarn build:backend          # compila o bundle
docker build -t ...:vN .    # empacota na imagem
docker push ...:vN          # publica
```

### 2. Pré-requisitos do ambiente

Versões **compatíveis** de Yarn e Node são essenciais:

- Node.js v24.21.0
- Yarn 1.22.22 (não Yarn 4 — o Backstage 1.54 usa Yarn 1)

Ferramentas auxiliares:

- `yamllint` pra validar YAML (estilo)
- `kubectl` pra inspecionar o cluster
- `argocd` CLI pra gerenciar sync

### 3. Acompanhar pods via CLI + ArgoCD

Não basta olhar o browser. Durante a Fase 7, foi essencial acompanhar:

```bash
kubectl -n backstage get pods -w          # ver subida/queda
kubectl -n backstage logs deployment/backstage --tail=100   # logs
argocd app get backstage                  # status do sync
```

O browser mostra o **sintoma**; o CLI mostra a **causa**.

### 4. O ConfigMap é a fonte da verdade no cluster

**Não é** o `app-config.yaml` do repo. O pod lê:

```
/app/app-config-from-configmap.yaml
```

Gerado pelo Helm chart a partir do `spec.source.helm.values` do `Application`.

**Editar o `apps/backstage/app-config.yaml` do repo NÃO tem efeito no cluster.**

### 5. O GitOps tem duas camadas

```
Git (app.yaml)  →  Application (cluster)  →  ConfigMap  →  Pod
   ↑                      ↑                      ↑           ↑
 editar               kubectl apply          argocd sync   restart
```

- **Camada 1 — Git:** o `app.yaml` versionado no repositório
- **Camada 2 — Cluster:** o `Application` que o ArgoCD lê de verdade

**Editar no Git sem `kubectl apply` NÃO propaga** — o `Application` no cluster
continua com os values antigos.

### 6. Documentar é o que transforma erro em lição

Cada erro da Fase 7 virou:

- **ADR** em `03-decisoes.md`
- **Troubleshooting** em `05-troubleshooting.md`
- **Runbook** em `04-runbook.md`

Sem documentação, o conhecimento se perde. Com documentação, **a próxima
pessoa (ou você no futuro) não repete os mesmos erros**.

### 7. Credenciais vivem em Secret, referenciado por `extraEnvVarsSecrets`

Nunca hardcode tokens no `app.yaml`. O padrão é:

1. **Criar Secret** no cluster:

   ```bash
   kubectl -n backstage create secret generic backstage-github-token \
     --from-literal=GITHUB_TOKEN=<seu-token>
   ```

2. **Referenciar no `app.yaml`**:

   ```yaml
   backstage:
     extraEnvVarsSecrets:
       - backstage-github-token
   ```

3. **Usar no `appConfig`**:

   ```yaml
   integrations:
     github:
       - host: github.com
         token: ${GITHUB_TOKEN}   # expandido em runtime
   ```

**Vantagens:**

- Token **nunca** vai pro Git
- Rotação **sem** rebuildar imagem
- Secret **separado** do Helm chart

## 📌 Resultado final da Fase 7

| Item | Antes | Depois |
|---|---|---|
| Backstage carrega | ⚠️ Parcial | ✅ Completo |
| Plugins registrados | ❌ Nenhum | ✅ 4 (notifications, search, home, scaffolder) |
| Home na raiz `/` | ❌ 404 | ✅ Renderiza |
| Widgets | ❌ | ✅ 8 widgets |
| Imagem | v3 | v7 |
| Chart Helm | 2.10.1 | 2.10.1 |
| GitOps | Parcial | ✅ Declarativo |
| Documentação | ❌ | ✅ (esta doc) |
| CSP (Random Joke) | ❌ | ⚠️ Pendente |
| Auth | Guest | Guest (Fase 8) |

## 🔗 Ver também

- [`00-contexto.md`](./00-contexto.md) — motivação e stack
- [`01-arquitetura.md`](./01-arquitetura.md) — componentes e fluxo
- [`03-decisoes.md`](./03-decisoes.md) — ADRs detalhadas
- [`04-runbook.md`](./04-runbook.md) — operações comuns
- [`05-troubleshooting.md`](./05-troubleshooting.md) — erros e soluções