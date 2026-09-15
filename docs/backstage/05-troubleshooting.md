# Troubleshooting — Backstage no Homelab MK8s

Guia de resolução de problemas conhecidos. Cada entrada segue o formato:

- **Sintoma** — o que você vê
- **Causa** — o que está acontecendo
- **Solução** — passo a passo
- **Prevenção** — como evitar
- **Referência** — links pra ADRs, runbook, etc.

**Como usar:** procure pelo sintoma (mensagem de erro, comportamento
inesperado) e siga a solução.

---

## Índice rápido

| # | Sintoma | Severidade |
|---|---|---|
| 1 | `NotImplementedError` do `plugin.notifications.service` | 🟡 Média |
| 2 | `plugin.search.queryservice` não registrado | 🟡 Média |
| 3 | `Routable extension not discovered` (home) | 🔴 Alta |
| 4 | `--force cannot be used with --server-side` | 🟡 Média |
| 5 | CSP bloqueia `official-joke-api.appspot.com` | 🟢 Baixa |
| 6 | ConfigMap não atualiza após sync | 🔴 Alta |
| 7 | `ImagePullBackOff` | 🔴 Alta |
| 8 | `CrashLoopBackOff` | 🔴 Alta |
| 9 | Home não aparece na raiz (404) | 🔴 Alta |
| 10 | YAML inválido (indentação, chaves duplicadas) | 🟡 Média |

---

## 1. `NotImplementedError` do `plugin.notifications.service`

### Sintoma

No browser, ao abrir o Backstage:

```
NotImplementedError: The API 'plugin.notifications.service' has not been
implemented yet.
```

### Causa

O `Sidebar.tsx` (ou outro componente) usa `NotificationsSidebarItem`, que
depende do plugin de notificações. Mas o **plugin não está registrado** no
`App.tsx`.

O Backstage usa o **frontend system novo** (`/alpha`), onde cada plugin
precisa ser **explicitamente registrado** em `plugins.ts`.

### Solução

**Passo 1:** Adicione o `notificationsPlugin` em
`apps/backstage/packages/app/src/plugins.ts`:

```typescript
export { default as notificationsPlugin } from '@backstage/plugin-notifications/alpha';
```

**Passo 2:** Confirme que o `App.tsx` inclui o `plugins.ts`:

```typescript
// apps/backstage/packages/app/src/App.tsx
import * as plugins from './plugins';

export default createApp({
  features: [catalogPlugin, ...Object.values(plugins), navModule, homeModule],
});
```

**Passo 3:** Rebuild + push (ver [runbook seção 2](./04-runbook.md#2-atualizar-a-imagem-do-backstage)):

```bash
cd ~/mk8s/homelab-gitops/apps/backstage
rm -rf packages/app/dist packages/backend/dist
yarn build:backend
docker build -t newbare/homelab-backstage:vN -f packages/backend/Dockerfile .
docker push newbare/homelab-backstage:vN
```

**Passo 4:** Atualizar o `app.yaml`, aplicar, sincronizar e reiniciar.

### Prevenção

Sempre que adicionar um componente que usa um plugin novo (notifications,
search, scaffolder, etc.), **registre o plugin** em `plugins.ts`.

### Referência

- [ADR-001: Imagem customizada](./03-decisoes.md#adr-001-imagem-customizada-em-vez-de-chart-oficial-puro)
- [Runbook seção 13: Adicionar ou remover plugin](./04-runbook.md#13-adicionar-ou-remover-plugin)

---

## 2. `plugin.search.queryservice` não registrado

### Sintoma

No browser:

```
NotImplementedError: The API 'plugin.search.queryservice' has not been
implemented yet.
```

### Causa

O `SidebarSearchModal` (usado no `Sidebar.tsx`) depende da API
`plugin.search.queryservice`, mas o `searchPlugin` **não está registrado**
no `plugins.ts`.

Mesmo problema do erro 1, mas pra outro plugin.

### Solução

**Passo 1:** Adicione o `searchPlugin` em `plugins.ts`:

```typescript
export { default as notificationsPlugin } from '@backstage/plugin-notifications/alpha';
export { default as searchPlugin } from '@backstage/plugin-search/alpha';
```

**Passo 2:** Rebuild + push (ver [runbook seção 2](./04-runbook.md#2-atualizar-a-imagem-do-backstage)).

**Passo 3:** Atualizar o `app.yaml`, aplicar, sincronizar e reiniciar.

### Prevenção

Mesma do erro 1: sempre registrar plugins.

### Referência

- [Runbook seção 13: Adicionar ou remover plugin](./04-runbook.md#13-adicionar-ou-remover-plugin)

---

## 3. `Routable extension not discovered` (home)

### Sintoma

No browser, ao abrir a home:

```
Routable extension component with mount point routeRef{type=absolute,id=home}
was not discovered in the app element tree. Routable extension components
may not be rendered by other components and must be directly available as
an element within the App provider component.
```

### Causa

Você registrou uma `PageBlueprint` no `homeModule.tsx` que renderiza o
`HomepageCompositionRoot`.

O problema: o `HomepageCompositionRoot` **já é** uma routable extension
(registra a rota `/home`). Ao envolvê-la numa `PageBlueprint` (que
**também** registra rota), o sistema **não consegue descobri-la** — ela
deixa de ser "elemento direto da árvore de rotas".

### Solução

**Remova a `PageBlueprint`** do `homeModule.tsx`. Deixe só o widget:

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

O **`homePlugin`** (do `/alpha`) já registra a rota `/home` sozinho.

Depois: rebuild + push + sync + restart.

### Prevenção

**Não misture `PageBlueprint` com `HomepageCompositionRoot`.** Se o plugin
já registra a rota, não registre de novo.

### Referência

- [ADR-003: `homeModule` só com widget](./03-decisoes.md#adr-003-homemodule-só-com-widget-sem-pageblueprint)

---

## 4. `--force cannot be used with --server-side`

### Sintoma

Ao rodar:

```bash
argocd app sync backstage --force
```

Retorna:

```
error validating options: --force cannot be used with --server-side
```

### Causa

O `Application` do ArgoCD tem `ServerSideApply=true` no `syncOptions`. A
flag `--force` é **incompatível** com `--server-side` (o ArgoCD recusa
combinar as duas).

### Solução

Use `--replace` em vez de `--force`:

```bash
argocd app sync backstage --replace
```

### Prevenção

Lembre-se: **`--force` não é compatível com `--server-side`**.

| Flag | Quando usar |
|---|---|
| `--replace` | Padrão neste projeto (com ServerSideApply) |
| `--force` | Só se `ServerSideApply=false` |

### Referência

- [ADR-007: `--replace` vs `--force`](./03-decisoes.md#adr-007-argocd-app-sync---replace-em-vez-de---force)
- [Runbook seção 2.2 passo 8](./04-runbook.md#passo-8-sincronizar-o-argocd)

---

## 5. CSP bloqueia `official-joke-api.appspot.com`

### Sintoma

No browser, no widget "Random Joke":

```
Failed to fetch
Refused to connect because it violates the document's Content Security Policy.
"default-src 'self'"
```

### Causa

O widget `HomePageRandomJoke` faz chamadas HTTP pra
`https://official-joke-api.appspot.com`. O CSP (Content Security Policy)
padrão do Backstage tem `default-src 'self'`, que **bloqueia** chamadas
externas.

### Solução

**Passo 1:** Edite o `app.yaml` e adicione `csp.connect-src` em
`backend`:

```yaml
backend:
  baseUrl: https://backstage.local
  listen:
    port: 7007
  cors:
    origin: https://backstage.local
  csp:
    connect-src:
      - "'self'"
      - "https:"
```

**Passo 2:** Aplicar + sync + restart (ver [runbook seção 11](./04-runbook.md#11-resolver-o-csp-do-random-joke)).

**Passo 3:** Hard refresh no browser (`Cmd+Shift+R`).

### Prevenção

Sempre que um widget ou plugin precisar chamar API externa, adicione a URL
em `csp.connect-src`.

### Referência

- [Runbook seção 11: Resolver o CSP do Random Joke](./04-runbook.md#11-resolver-o-csp-do-random-joke)
- [ADR-010: Widgets customizados](./03-decisoes.md#adr-010-apenas-toolkit-e-world-clock-como-widgets-customizados)

---

## 6. ConfigMap não atualiza após sync

### Sintoma

Você editou o `infrastructure/backstage/app.yaml`, fez `git push`, rodou
`argocd app sync`, mas o ConfigMap continua com o conteúdo antigo:

```bash
kubectl -n backstage get configmap backstage-app-config -o yaml
# ⚠️ Não tem `page:home`, `packages: all`, etc.
```

O `resourceVersion` do ConfigMap **não muda**.

### Causa

Há **duas camadas** no GitOps:

1. **Git** — o `app.yaml` versionado no repositório
2. **Cluster** — o `Application` que o ArgoCD lê de verdade

O ArgoCD **não lê** o `app.yaml` do Git. Ele lê o `Application` que está
**no cluster** (criado por `kubectl apply`). Se você só fez `git push`, o
`Application` no cluster **continua com os values antigos**.

### Solução

**Passo 1:** Aplicar o `app.yaml` no cluster:

```bash
cd ~/mk8s/homelab-gitops
kubectl apply -f infrastructure/backstage/app.yaml
```

**Passo 2:** Verificar que o `Application` no cluster tem o novo values:

```bash
kubectl -n argocd get application backstage -o yaml | grep -A5 "page:home"
```

**Passo 3:** Forçar o ArgoCD a regenerar o ConfigMap:

```bash
argocd app sync backstage --replace
```

**Passo 4:** Verificar o ConfigMap:

```bash
kubectl -n backstage get configmap backstage-app-config -o yaml | head -60
```

**Passo 5:** Se ainda não atualizar, deletar o ConfigMap manualmente:

```bash
kubectl -n backstage delete configmap backstage-app-config
argocd app sync backstage --replace
```

### Prevenção

**Sempre que editar o `app.yaml`:**

1. `git push`
2. `kubectl apply -f infrastructure/backstage/app.yaml`
3. `argocd app sync backstage --replace`
4. `kubectl -n backstage rollout restart deployment backstage`

**O `git push` sozinho não basta.**

### Referência

- [ADR-004: `appConfig` é a fonte da verdade](./03-decisoes.md#adr-004-appconfig-no-helm-values-é-a-fonte-da-verdade-no-cluster)
- [Runbook seção 15: Atualizar o Application do ArgoCD](./04-runbook.md#15-atualizar-o-application-do-argocd)

---

## 7. `ImagePullBackOff`

### Sintoma

```bash
kubectl -n backstage get pods
```

Mostra:

```
NAME                         READY   STATUS             RESTARTS   AGE
backstage-xxxxxxxxxx-xxxxx   0/1     ImagePullBackOff   0          2m
```

### Causa

O Kubernetes não consegue puxar a imagem do Docker Hub. Possíveis causas:

1. **Tag não existe** (`v8` não foi publicado)
2. **Nome da imagem errado** no `app.yaml`
3. **Sem acesso ao Docker Hub** (rede)
4. **Rate limit** do Docker Hub (se muitas pulls sem login)

### Solução

**Passo 1:** Ver qual imagem o pod está tentando puxar:

```bash
kubectl -n backstage describe pod <nome-do-pod> | grep -A5 "Events"
```

**Passo 2:** Confirmar que a tag existe no Docker Hub:

```bash
# Lista tags disponíveis
curl -s https://hub.docker.com/v2/repositories/newbare/homelab-backstage/tags | jq '.results[].name'
```

**Passo 3:** Verificar o `app.yaml`:

```bash
grep -A3 "image:" ~/mk8s/homelab-gitops/infrastructure/backstage/app.yaml
```

Deve mostrar:

```yaml
image:
  registry: docker.io
  repository: newbare/homelab-backstage
  tag: vN
```

**Passo 4:** Se a tag estiver errada, corrija o `app.yaml`, faça
`kubectl apply` + `argocd sync` + `rollout restart`.

**Passo 5:** Se for rate limit, faça login no Docker Hub:

```bash
docker login
```

### Prevenção

- Sempre que buildar uma nova imagem, **verifique que o push foi
  bem-sucedido** (o digest aparece no output)
- Use tags imutáveis (`vN`) e nunca `latest`
- Evite rebuilds desnecessários (rate limit)

### Referência

- [ADR-005: Tags imutáveis](./03-decisoes.md#adr-005-tags-imutáveis-v7-em-vez-de-latest)
- [Runbook seção 2: Atualizar a imagem](./04-runbook.md#2-atualizar-a-imagem-do-backstage)

---

## 8. `CrashLoopBackOff`

### Sintoma

```bash
kubectl -n backstage get pods
```

Mostra:

```
NAME                         READY   STATUS             RESTARTS   AGE
backstage-xxxxxxxxxx-xxxxx   0/1     CrashLoopBackOff   5          5m
```

O pod sobe e cai repetidamente.

### Causa

O container está **quebrando na inicialização**. Possíveis causas:

1. **Config inválida** (YAML malformado no ConfigMap)
2. **Erro de conexão** com PostgreSQL
3. **Plugin mal registrado** (import quebrado)
4. **Falta de variável de ambiente** (ex: `GITHUB_TOKEN` ausente)
5. **Dependência faltando** no bundle

### Solução

**Passo 1:** Ver os logs do container que quebrou:

```bash
# Logs do container atual
kubectl -n backstage logs deployment/backstage --tail=100

# Logs do container ANTERIOR (antes de crashar)
kubectl -n backstage logs deployment/backstage --previous --tail=100
```

**Passo 2:** Procurar por `ERROR` ou stack trace:

```bash
kubectl -n backstage logs deployment/backstage --previous | grep -iE "error|exception|fatal"
```

**Passo 3:** Dependendo do erro:

| Erro | Solução |
|---|---|
| `Error: Cannot find module 'X'` | Rebuild da imagem (dependência faltando) |
| `ECONNREFUSED 5432` | Verificar se PostgreSQL está rodando |
| `YAMLException: bad indentation` | Corrigir o `app.yaml` |
| `GITHUB_TOKEN not defined` | Criar o Secret |
| `Unknown plugin X` | Registrar plugin em `plugins.ts` |

**Passo 4:** Corrigir a causa, rebuild + push + sync + restart.

### Prevenção

- Sempre rodar `yarn build:backend` **localmente** antes de buildar a imagem
- Testar a config YAML antes de aplicar (`kubectl apply --dry-run=client`)
- Verificar logs **após cada deploy**

### Referência

- [Runbook seção 4: Ver logs detalhados](./04-runbook.md#4-ver-logs-detalhados)
- [Runbook seção 14.1: Pod em CrashLoopBackOff](./04-runbook.md#141-pod-em-crashloopbackoff)

---

## 9. Home não aparece na raiz (404)

### Sintoma

No browser:

- `https://backstage.local/home` → funciona ✅
- `https://backstage.local/` → `ERROR 404: PAGE NOT FOUND` ❌

### Causa

O `appConfig` não tem `page:home` com `path: /`. Sem isso, o Backstage não
sabe que a home deve estar na raiz — só em `/home` (rota default do
plugin).

Pode ser porque:

1. O `app.yaml` não foi atualizado
2. O `Application` no cluster não foi atualizado (falta `kubectl apply`)
3. O ConfigMap não foi regenerado (falta `argocd sync --replace`)
4. O pod não foi reiniciado

### Solução

**Passo 1:** Verificar o ConfigMap:

```bash
kubectl -n backstage get configmap backstage-app-config -o yaml | grep -A5 "page:home"
```

**Esperado:**

```yaml
- page:home:
    config:
      defaultConfig:
      # ...
      path: /
```

**Se NÃO aparecer:** o ConfigMap está desatualizado. Siga o passo a passo
do [erro 6 (ConfigMap não atualiza)](#6-configmap-não-atualiza-após-sync).

**Se aparecer, mas o browser ainda dá 404:** o pod não recarregou o
ConfigMap. Reinicie:

```bash
kubectl -n backstage rollout restart deployment backstage
kubectl -n backstage get pods -w
```

**Passo 2:** Hard refresh no browser (`Cmd+Shift+R`).

### Prevenção

Ao mudar a config de rota (`page:home`, `page:catalog`, etc.), **sempre**
confirme os 4 passos:

1. `git push`
2. `kubectl apply -f infrastructure/backstage/app.yaml`
3. `argocd app sync backstage --replace`
4. `kubectl -n backstage rollout restart deployment backstage`

### Referência

- [ADR-002: Home como raiz](./03-decisoes.md#adr-002-home-como-raiz-pagehome-com-path-)
- [Runbook seção 15: Atualizar o Application do ArgoCD](./04-runbook.md#15-atualizar-o-application-do-argocd)

---

## 10. YAML inválido (indentação, chaves duplicadas)

### Sintoma

Ao rodar:

```bash
kubectl apply -f infrastructure/backstage/app.yaml --dry-run=client
```

Retorna:

```
error: error validating "infrastructure/backstage/app.yaml": 
error validating data: [apiVersion not set, kind not set]
```

Ou:

```
error: yaml: line X: did not find expected key
```

Ou o `argocd sync` falha com erro de parse.

### Causa

O YAML tem erro de:

1. **Indentação** (usou tab em vez de espaço, ou indentou errado)
2. **Chave duplicada** (YAML não aceita duas chaves com o mesmo nome)
3. **Estrutura quebrada** (faltou `:` em algum lugar)
4. **Bloco `values:` mal formatado** (o conteúdo interno é uma string, não
   YAML estruturado)

### Solução

**Passo 1:** Validar o YAML antes de commitar:

```bash
# Opção 1: kubectl (mais confiável pro k8s)
kubectl apply --dry-run=client -f infrastructure/backstage/app.yaml

# Opção 2: yamllint (estilo + sintaxe)
yamllint infrastructure/backstage/app.yaml

# Opção 3: Ruby (rápido)
ruby -ryaml -e "YAML.load_file('infrastructure/backstage/app.yaml'); puts 'OK'"
```

**Passo 2:** Se o erro for `apiVersion not set, kind not set`, o arquivo
provavelmente **perdeu a estrutura de `Application`** (alguém colou
conteúdo de outro arquivo).

Confira o topo:

```bash
head -5 infrastructure/backstage/app.yaml
```

**Esperado:**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: backstage
  namespace: argocd
```

**Se aparecer `app:` na primeira linha:** está errado. Restaure o
`Application` (ver [ADR-004](./03-decisoes.md#adr-004-appconfig-no-helm-values-é-a-fonte-da-verdade-no-cluster)).

**Passo 3:** Se for **chave duplicada** (YAML não aceita), procure:

```bash
grep -n "page:home\|page:catalog" infrastructure/backstage/app.yaml
```

Se `page:home` aparecer 2x, é isso. Remova a duplicata (mantenha só uma,
com todos os campos juntos: `path` + `defaultConfig`).

**Passo 4:** Se for **tab em vez de espaço**:

```bash
grep -P '\t' infrastructure/backstage/app.yaml
```

Se aparecer algo, substitua tabs por 2 espaços.

### Prevenção

- **Nunca** usar tabs em YAML — só espaços
- **Sempre** validar com `kubectl apply --dry-run=client` antes de commitar
- **Nunca** ter chaves duplicadas no mesmo nível
- Ao mover blocos (ex: o `## Resumo das decisões`), **cuidar da ordem**
  (colocar no lugar certo, não no meio)

### Referência

- [Runbook seção 15: Atualizar o Application](./04-runbook.md#15-atualizar-o-application-do-argocd)

---

## 📌 Resumo por severidade

| Severidade | Erros | Ação |
|---|---|---|
| 🔴 **Alta** | 3, 6, 7, 8, 9 | Bloqueiam uso. Resolver **agora**. |
| 🟡 **Média** | 1, 2, 4, 10 | Funcionalidade parcial. Resolver logo. |
| 🟢 **Baixa** | 5 | Polish. Pode esperar. |

## 🔗 Ver também

- [`00-contexto.md`](./00-contexto.md) — motivação e stack
- [`01-arquitetura.md`](./01-arquitetura.md) — componentes e fluxo
- [`02-jornada-fase-7.md`](./02-jornada-fase-7.md) — cronológico
- [`03-decisoes.md`](./03-decisoes.md) — ADRs
- [`04-runbook.md`](./04-runbook.md) — operações comuns
