# Fase 2 — Plano: popular o catálogo do Backstage

> **Fase:** 2 de 3 (Pesquisa → **Plano** → Implementação)
> **Data:** 2026-09-19 · **Base de pesquisa:** [`12-pesquisa-catalogo.md`](./12-pesquisa-catalogo.md)
> **Status:** proposta. **Nada aqui está aplicado.** A implementação (Fase 3) só
> começa depois da sua aprovação.

---

## 1. Objetivo e não-objetivos

**Objetivo:** colocar no catálogo as entidades que **já existem** no laboratório,
sem inventar software. Fonte natural: as 21 Applications do ArgoCD, que já
representam os projetos reais.

**Não-objetivos desta fase:**

- Não instalar o plugin do ArgoCD (é visualização, e é uma fase própria).
- Não configurar TechDocs — só anotar as entidades que já têm `mkdocs.yml` e `docs/`.
- Não criar templates de scaffolder.
- Não ingerir entidades do GitHub automaticamente (descoberta é fase própria).

---

## 2. Pré-requisitos descobertos na pesquisa

| # | Pré-requisito | Estado | Impacto se faltar |
|---|---|---|---|
| 1 | `Domain` **não** está no `rules.allow` atual | ⚠️ ausente | Entidade `Domain` é **descartada em silêncio** |
| 2 | `spec.owner` é obrigatório em `Component`, `System`, `Resource`, `Domain`, `API` | ✅ resolvido | Grupos existentes: `resilience-admins`, `resilience-devs`, `resilience-viewers` (todos `type: team`, sem `parent`) |
| 3 | `apps/backstage/catalog-info.yaml` ocupa o nome `backstage` (e é o exemplo) | ⚠️ conflito | Nome duplicado: *"one will be processed and all others will be skipped"* |
| 4 | `apps/bookinfo/catalog-info.yaml` existe e nenhuma location o lê | pronto | Basta apontar |
| 5 | Plugin do ArgoCD não instalado → `argocd/app-name` hoje é inerte | aceito | A aba não aparece; **não bloqueia** o catálogo |

**Ação exigida pelo item 2:** ✅ resolvida. Os `Group` existentes são
`resilience-admins`, `resilience-devs` e `resilience-viewers` — todos `type: team`,
hierarquia plana (nenhum tem `parent`). Fonte: ConfigMap `backstage-catalog-users`,
extraindo **apenas** os nomes de `Group` (os `User` não foram lidos).

**`owner` definido para toda a infra: `resilience-admins`.**

---

## 3. Modelo proposto

Baseado nas definições oficiais (pesquisa §3). O campo `spec.type` é **livre** — a
taxonomia abaixo é escolha nossa, não imposição do Backstage.

### 3.1 Árvore

```text
Domain      homelab
  ├─ System  plataforma-gitops      → argocd, backstage
  ├─ System  identidade             → keycloak
  ├─ System  malha-de-servico       → istio, kiali
  ├─ System  observabilidade        → prometheus, grafana, jaeger
  └─ System  rede-e-seguranca       → metallb, cert-manager, trust-manager, metrics-server
Resource    postgresql              (pertence a identidade — guarda Keycloak + Backstage)
```

### 3.2 Componentes, por Application do ArgoCD

| ArgoCD Application | Kind | `spec.type` sugerido | Observação |
|---|---|---|---|
| `backstage` | Component | `website` | portal |
| `keycloak` | Component | `service` | IdP |
| `istio-base`, `istiod`, `istio-gateway` | Component | `service` | **3 apps → 1 componente?** ver decisão D3 |
| `kiali` | Component | `service` | observabilidade da malha |
| `kiali-operator` | — | — | operator: subcomponente? ver D3 |
| `jaeger` | Component | `service` | tracing |
| `jaeger-operator` | — | — | idem D3 |
| `kube-prometheus-stack` | Component | `service` | métricas + Grafana |
| `metallb` | Component | `service` | LB |
| `cert-manager`, `trust-manager` | Component | `service` | PKI |
| `metrics-server` | Component | `service` | métricas de recurso |
| `bookinfo` | Component | `service` | demo (entidade já existe no repo) |
| `backstage-certificate`, `backstage-ingress`, `cert-manager-ca`, `namespaces` | — | — | **não são componentes** — são manifesto de recurso. Ver D4 |
| `postgresql` | **Resource** | `database` | infraestrutura, não software |

### 3.3 `lifecycle`

Todas as entidades rodam em produção de laboratório. Sugestão: `production`
para tudo, exceto `bookinfo` → `experimental` (é demo). A doc define os três
valores bem-conhecidos: `experimental`, `production`, `deprecated`.

---

## 4. Como as entidades entram no catálogo

Duas opções, ambas já descritas na pesquisa (§4).

### Opção B — locations estáticas · **recomendada para o primeiro incremento**

| | |
|---|---|
| **O que muda** | `appConfig.catalog.locations` + arquivos `catalog-info.yaml` |
| **Custo** | zero código, zero build de imagem |
| **Publicação** | commit → ConfigMap → o chart já reinicia o Pod (checksum) |
| **Limite** | atualização só quando commitamos; um `target` por arquivo |

### Opção A — descoberta automática pelo GitHub

| | |
|---|---|
| **O que muda** | `yarn add @backstage/plugin-catalog-backend-module-github` + `backend.add(...)` + `catalog.providers.github` |
| **Custo** | alteração de código + **rebuild da imagem** |
| **Ganha** | acha `catalog-info.yaml` de **qualquer** repo da org, sozinho |
| **Cuidado** | `validateLocationsExist: true` é **incompatível com wildcard**; PAT precisa de escopo `repo`; consome rate limit |

**Recomendação:** fazer **B** primeiro. Ele valida o modelo de entidades e o
desenho das relações a custo quase zero. Se o modelo se provar bom, **A** entra
depois como fase própria — e aí o custo do build é justificado por algo já
validado.

---

## 5. Sequência de execução (3 incrementos)

Cada incremento é independente e verificável. Se o primeiro não se provar,
os outros dois não acontecem.

**Incremento 1 — ligar o fio que já existe (1 arquivo).**
Adicionar `apps/bookinfo/catalog-info.yaml` como location. É o menor passo
possível, usa entidade que **já está escrita** no repo, e prova que o mecanismo de
location funciona. Verificação: a entidade aparece no catálogo.

**Incremento 2 — modelo completo (1-2 arquivos + config).**
Criar `catalog/catalog-info.yaml` com `System`s, `Component`s e o `Resource`;
adicionar ao `rules.allow` o kind que faltar; registrar a location. Verificação:
o grafo aparece — sistemas com seus componentes, `owner` resolvido.

**Incremento 3 — substituir o exemplo.**
Trocar `apps/backstage/catalog-info.yaml` (hoje `owner: john@example.com`) pela
entidade real, resolvendo a colisão de nome `backstage`.

---

## 6. Critério de pronto

- [ ] `bookinfo` visível no catálogo (Incremento 1)
- [ ] Os `System`s e seus `Component`s visíveis, com relações formadas
- [ ] `postgresql` aparece como `Resource`, não como serviço
- [ ] Nenhuma entidade com `owner` inexistente
- [ ] Nenhum nome duplicado
- [ ] `apps/backstage/catalog-info.yaml` deixou de ser o exemplo do `create-app`
- [ ] Nenhum erro de política nos logs (`plugin-catalog-backend-module-logs` já está ativo)

---

## 7. Decisões

| # | Decisão | Resolução | Quem decidiu |
|---|---|---|---|
| **D1** | Incluir `Domain`? | ✅ **Sim.** Exige acrescentar `Domain` ao `rules.allow` — senão a entidade é descartada em silêncio | Jefferson |
| **D2** | Usar `System`? | ✅ **Sim**, ~5 sistemas. É a camada que dá sentido ao grafo | recomendação |
| **D3** | Operator × CR | ✅ **Fundir.** 1 `Component` por produto; o operator vira `subcomponentOf` | delegado ao agente |
| **D4** | Applications que não são software (`backstage-ingress`, `namespaces`, `cert-manager-ca`, `backstage-certificate`) | ✅ **Ignorar** nesta fase — não são software nem infraestrutura nomeável | recomendação |
| **D5** | Nome do `Domain` | ✅ **`resilience`** | Jefferson |
| **D6** | Onde ficam os arquivos | ✅ **Um arquivo central**: `catalog/catalog-info.yaml` | Jefferson |

### Racional de D3 (a decisão delegada)

`kiali` e `kiali-operator` são **Applications separadas** porque o *deploy* é
separado. Mas não são dois produtos: o operator é o mecanismo, o CR é a instância.
O mesmo vale para `jaeger` + `jaeger-operator`.

**O ArgoCD agrupa por como instala. O catálogo deve agrupar por o que é.** As duas
visões não precisam coincidir — e a anotação `argocd/app-name` continua ligando
cada `Component` à sua Application.

Resultado: 4 componentes onde havia 6 (`istio`, `kiali`, `jaeger`, `prometheus`).

### Racional de D2 (argumentável — não é boa prática)

**Classificação honesta:** a doc marca `System` e `Domain` como conceitos
**opcionais** de categorização. Logo isto **não** é um mandato de melhores práticas
— é julgamento, e a base é esta passagem:

> *"A large catalogue of components, APIs and resources can be **highly granular and
> hard to understand as a whole**. It might thus be convenient to further categorize
> these entities using the following **(optional)** concepts"* — System Model

**Contra-argumento, registrado:** a definição de `System` diz que ele *"exposes one or
several public APIs"*. Nossos componentes de infraestrutura não expõem API de produto
— então há rigor de definição sendo flexibilizado.

**O que decide:** a preferência declarada de Jefferson — *"minha opinião é documentar
tudo na Backstage"*. Por esse critério o `System` entra: custa 5 entidades e é o que
gera a relação `partOf`, que é o que a página **Grafo do catálogo** desenha.

**Natureza da decisão:** escolha do adotante sobre conceito opcional. **Não** é
exigência do framework.

### Racional de D4 (ancorado na doc)

Diferente de D2, esta tem base na definição oficial:

> `Resource` — *"the infrastructure a component needs to operate at runtime, like
> BigTable databases, Pub/Sub topics, S3 buckets or CDNs"*

`namespaces`, `backstage-ingress`, `cert-manager-ca` e `backstage-certificate` **não
são isso** — são manifestos de orquestração (criam namespace, configuram rota,
emitem certificado). Não são software (`Component`) nem infraestrutura nomeável
(`Resource`). Ficam fora, e o motivo é a definição, não preferência.

**Nota:** se um dia entrar um bucket S3 do Floci ou um banco novo, esse **é** um
`Resource` pela mesma definição — e aí entra.

---

## 8. Riscos conhecidos

| Risco | Probabilidade | Mitigação |
|---|---|---|
| `owner` inexistente invalida as entidades | **alta** — não confirmamos os nomes | Confirmar os `Group` **antes** do Incremento 2 |
| Nome `backstage` duplicado descarta uma entidade em silêncio | alta | Incremento 3 resolve; conferir os logs |
| `Domain` descartado por não estar no `rules` | certa, se D1 = (a) não for feito | Editar `rules.allow` junto |
| Erro em `catalog-info.yaml` **não** interrompe o processamento — só loga | média | Ler os logs do `catalog-backend-module-logs` após cada incremento |
| Location estática não se remove pela API | baixa | Sabido: só se remove editando o config |

---

## 9. O que este plano **não** decide

- Instalar o plugin do ArgoCD (`@backstage-community/plugin-argocd`) — fase própria.
- Configurar TechDocs (`runIn: docker` → `local`, publisher) — fase própria, e
  depende de decidir se a publicação vai para `local` ou para o S3 do Floci.
- Descoberta automática pelo GitHub (Opção A) — fase própria, com rebuild.

### 9.1 Autorização — fase própria, e não é catálogo

Requisito levantado por Jefferson: *"somente o grupo de admins pode ver documentos de infra"*.

**Isso não é modelagem de catálogo — é autorização.** Misturar as duas faz as duas
saírem mal. Fica registrado como fase separada, com o estado atual documentado:

| Item | Estado hoje |
|---|---|
| Policy de permissão | `@backstage/plugin-permission-backend-module-allow-all-policy` — **todo mundo vê tudo** |
| Grupos disponíveis para a regra | `resilience-admins`, `resilience-devs`, `resilience-viewers` |
| Dependência cruzada | O plugin do ArgoCD declara que as abas dependem da permissão `argocd.view.read`; a interação com `allow-all` está **aberta** na pesquisa (§8.5) |

**Por que não é filtro de tela:** o catálogo tem API. Esconder na interface sem
restringir a API é esconder o botão, não a porta.

**Consequência para a F1:** o `owner` das entidades de infra é `resilience-admins`,
o que já prepara o terreno — mas **a F1 não implementa a restrição**.

---

## 10. Próximo passo

✅ D1 a D6 resolvidos e os nomes de `Group` obtidos.

Falta apenas a sua confirmação em **D2** e **D4**, que segui por recomendação
(§7). Confirmado isso, Fase 3 — implementação, começando pelo Incremento 1.
