# Fase 1 — Pesquisa: o modelo de catálogo do Backstage

> **Fase:** 1 de 3 (Pesquisa → Plano → Implementação)
> **Data:** 2026-09-19 · **Base:** Backstage 1.54.0
> **Natureza deste documento:** pesquisa. **Não** contém proposta, decisão nem YAML
> a aplicar. Onde não consegui confirmar, está escrito que não confirmei.

---

## 1. Por que este documento existe

Uma tentativa anterior desta feature começou pelo "como implementar" — e errou a
premissa central (supôs que o catálogo se alimentava do ArgoCD). O custo foi
retrabalho. A ordem correta é: **documentar como funciona → planejar → implementar**.

Este documento é a Fase 1.

---

## 2. Fontes consultadas

| Fonte | Link | O que respondeu |
|---|---|---|
| Backstage — System Model | <https://backstage.io/docs/features/software-catalog/system-model> | O que são Component, API, Resource, System, Domain, User, Group, Location, Type |
| Backstage — Descriptor Format | <https://backstage.io/docs/features/software-catalog/descriptor-format> | Campos obrigatórios/opcionais por kind; envelope; metadata; relations; substitutions |
| Backstage — Catalog Configuration | <https://backstage.io/docs/features/software-catalog/configuration> | Como entidade entra no catálogo; `locations`; `rules`; providers; órfãos; intervalos |
| Backstage — GitHub Discovery | <https://backstage.io/docs/integrations/github/discovery> | Provider de descoberta; instalação do módulo; opções; escopo de token |
| Este repositório | `infrastructure/backstage/app.yaml`, `apps/*/catalog-info.yaml`, `packages/backend/*` | O que já existe aqui |

Versões usadas como referência de código: **Backstage 1.54.0**, chart `backstage`
**2.10.1**, `@backstage/plugin-catalog-backend` **^3.9.0**.

---

## 3. O que é o catálogo

Fonte: System Model. O catálogo modela software em **três entidades centrais**:

| Kind | Definição (doc oficial) |
|---|---|
| **Component** | "a piece of software" — serviço de backend, site, biblioteca, pipeline de dados |
| **API** | "the boundaries between different components" — implementada por componentes, precisa de formato legível por máquina (OpenAPI, AsyncAPI, GraphQL, gRPC) |
| **Resource** | "the infrastructure a component needs to operate at runtime, like BigTable databases, Pub/Sub topics, S3 buckets or CDNs" |

Mais duas **organizacionais**:

| Kind | Definição |
|---|---|
| **User** | "a person, such as an employee, a contractor, or similar" |
| **Group** | "an organizational entity, such as for example a team, a business unit, or a loose collection of people" |

E duas **opcionais** de agrupamento (chamadas na doc de *ecosystem modeling*):

| Kind | Definição | Detalhe relevante |
|---|---|---|
| **System** | "a collection of resources and components that exposes one or several public APIs" | *"Typically, a system will consist of at most a handful of components"* |
| **Domain** | "groups a collection of systems that share terminology, domain models, business purpose, or documentation, i.e. form a bounded context" | pode aninhar (`subdomainOf`) |

Duas entidades de apoio:

| Kind | Definição | Detalhe relevante |
|---|---|---|
| **Location** | "a marker that references other places to look for catalog data" | É o que aponta para outros arquivos |
| **Type** | `spec.type` | *"The type field in the system has no set meaning. It is up to the user to assign their own types"* — é **campo livre**, não enum fechado |

> ⚠️ A própria página do System Model ressalva: *"some of the concepts are not yet
> supported in Backstage"*. Nem tudo que está descrito ali é implementado.

---

## 4. Como uma entidade entra no catálogo

Fonte: Catalog Configuration.

### 4.1 Mecanismos

| Mecanismo | Como | Custo / observação |
|---|---|---|
| **Location estática** (`type: url`) | `catalog.locations` aponta para uma URL | Processado pelo `UrlReaderProcessor`, que **precisa de uma integration** configurada para aquele host |
| **Location estática** (`type: file`) | `catalog.locations` aponta para arquivo local | A doc é explícita: *"You should only use this for local development, test setups, and example data, not for production data"* |
| **Entity provider** (ex.: GitHub) | `catalog.providers.<provider>` + módulo no backend | Descobre sozinho; precisa do pacote instalado |
| **Custom processor** | Código no backend | Para ingerir de sistemas existentes |
| **catalog-import** (UI) | Registrar pela interface | Grava uma Location; desabilitável com `catalog.readonly: true` |

### 4.2 Comportamentos que surpreendem

Levantados na doc, e que valem para qualquer decisão futura:

1. **Location estática não se remove pela API.** *"The locations added through
   static configuration cannot be removed through the catalog locations API."*
   Só edita o config.
2. **Erro não interrompe o processamento.** *"Errors do not cause processing to
   abort"* — erro de sintaxe em `catalog-info.yaml` é **logado**, não falha ruidosamente.
3. **Nome duplicado: um sobrevive, o resto é descartado.**
   *"When multiple `catalog-info.yaml` files with the same `metadata.name` property
   are discovered, one will be processed and all others will be skipped."*
4. **`catalog.rules` SUBSTITUI o default, não complementa.** *"if the `catalog.rules`
   key is present it will replace the default value"*. O default permite apenas
   `Component`, `API`, `Location`.
5. **Órfão é removido por padrão.** Se a location sai, a entidade sai — a menos que
   se configure `catalog.orphanStrategy: keep`.
6. **Intervalo de processamento** é ~45 min por padrão; a doc avisa que valor baixo
   demais *"risks exhausting rate limits on external systems"*.

### 4.3 O provider do GitHub — requisitos

Fonte: GitHub Discovery.

- **Não vem instalado.** É preciso `@backstage/plugin-catalog-backend-module-github`
  **e** registrá-lo: `backend.add(import('@backstage/plugin-catalog-backend-module-github'))`.
- Config fica em `catalog.providers.github.<providerId>`, com `organization`
  (ou `app`) obrigatório, `catalogPath`, `filters`, `schedule`.
- **Incompatibilidade importante:** `validateLocationsExist: true` **não pode ser
  combinado com wildcard** em `catalogPath` — *"this option cannot be used in
  conjunction with wildcards"*. É uma escolha: validar **ou** varrer recursivamente.
- Token: PAT precisa de escopo **`repo`** (mínimo) para ler componentes.
- A doc é clara sobre quando vale a pena: é *"the preferred method for ingesting
  entities into the catalog"*, mas **custa requisições de API** (limite de 5.000/h).

---

## 5. O formato do descritor

Fonte: Descriptor Format.

### 5.1 Envelope

```text
apiVersion   [obrigatório]  ex.: backstage.io/v1alpha1
kind         [obrigatório]  ex.: Component
metadata     [obrigatório]
spec         [varia por kind]
relations    [SAÍDA — não se escreve este campo no YAML]
status       [SAÍDA — não se escreve este campo no YAML]
```

**Nome do arquivo:** a doc *recomenda* `catalog-info.yaml`
(*"we recommend that you name them catalog-info.yaml"*) — recomendação, não exigência.

### 5.2 `metadata` — campos com semântica reservada

| Campo | Status | Regra |
|---|---|---|
| `name` | obrigatório | único por kind dentro do namespace; case-insensitive; `[a-zA-Z0-9]` separado por `[-_.]`; ≤63 chars |
| `namespace` | opcional | default é `default`; referência entre namespaces usa `<namespace>/<name>` |
| `uid` | **saída** | gerado pelo banco, **não é estável** — a doc diz para não usar como referência externa |
| `title` | opcional | só exibição; referências continuam usando `name` |
| `description` | opcional | texto curto |
| `labels` | opcional | par chave/valor estilo Kubernetes; prefixo `backstage.io/` **reservado** |
| `annotations` | opcional | valor sempre string; prefixo `backstage.io/` **reservado** |
| `tags` | opcional | lista de strings; `[a-z0-9:+#]` separado por `-`; ≤63 |
| `links` | opcional | `url` (obrigatório), `title`, `icon`, `type` |

### 5.3 Relações — derivadas, não escritas

A doc é explícita: *"Entity descriptor YAML files are not supposed to contain this
field."* Os processadores **deduzem** as relações a partir do `spec` e do entorno, e
o resultado vira a **fonte autoritativa** para plugins.

Mapa `campo do spec` → `relação` (e a reversa):

| Campo escrito no `spec` | Gera relação | Reversa | Alvo |
|---|---|---|---|
| `owner` | `ownedBy` | `ownerOf` | Group (default) ou User |
| `system` | `partOf` | `hasPart` | System |
| `subcomponentOf` | `partOf` | `hasPart` | Component |
| `providesApis` | `providesApi` | `apiProvidedBy` | API |
| `consumesApis` | `consumesApi` | `apiConsumedBy` | API |
| `dependsOn` | `dependsOn` | `dependencyOf` | Component ou Resource |
| `dependencyOf` | `dependencyOf` | `dependsOn` | Component ou Resource |
| `domain` | `partOf` | `hasPart` | Domain |
| `subdomainOf` | `partOf` | `hasPart` | Domain |
| `parent` | `childOf` | `parentOf` | Group |
| `children` | `parentOf` | `childOf` | Group |
| `members` | `hasMember` | `memberOf` | User |
| `memberOf` | `memberOf` | `hasMember` | Group |

### 5.4 Campos obrigatórios por kind

| Kind | apiVersion | Obrigatórios | Opcionais notáveis |
|---|---|---|---|
| `Component` | `v1alpha1` | `spec.type`, `spec.lifecycle`, `spec.owner` | `system`, `subcomponentOf`, `providesApis`, `consumesApis`, `dependsOn`, `dependencyOf` |
| `API` | `v1alpha1` | `spec.type`, `spec.lifecycle`, `spec.owner`, `spec.definition` | `system` |
| `Resource` | `v1alpha1` | `spec.owner`, `spec.type` | `system`, `dependsOn`, `dependencyOf` |
| `System` | `v1alpha1` | `spec.owner` | `domain`, `type` |
| `Domain` | `v1alpha1` | `spec.owner` | `subdomainOf`, `type` |
| `Group` | `v1alpha1` | `spec.type`, `spec.children` (pode ser vazio) | `profile`, `parent`, `members` |
| `User` | `v1alpha1` | `spec.memberOf` (pode ser vazio) | `profile` |
| `Location` | `v1alpha1` | `spec` (mínimo `{}`) | `type`, `target`, `targets`, `presence` |
| `Template` | `v1beta2` | — | — |

Valores *well-known* (não são enum fechado — a doc aceita qualquer valor, e
recomenda que a organização defina sua taxonomia):

- `Component.spec.type`: `service`, `website`, `library`
- `Component.spec.lifecycle`: `experimental`, `production`, `deprecated`
- `API.spec.type`: `openapi`, `asyncapi`, `graphql`, `grpc`
- `Resource.spec.type`: `database`, `s3-bucket`, `kubernetes-cluster`
- `Group.spec.type`: `team`, `business-unit`, `product-area`, `root`
- `System.spec.type`: `product`, `service`, `feature-set`
- `Domain.spec.type`: `product-area`, `product-group`, `bundle`

### 5.5 Substitutions

`$text`, `$json`, `$yaml` embutem conteúdo de outro arquivo (absoluto ou relativo ao
`catalog-info.yaml`). Para alvos **fora** das integrations conhecidas, é preciso
liberar em `backend.reading.allow`.

Além disso, módulos acrescentam placeholders próprios:
`@backstage/plugin-catalog-backend-module-openapi` habilita `$openapi` e `$asyncapi`,
que resolvem os `$ref` do spec.

---

## 6. GitHub × ArgoCD — a premissa que estava errada

**O que ficou documentado:** a entrada de entidades no catálogo é feita por
**location** ou **provider**, ambos lendo de **sistema de versionamento**
(Git) ou de arquivo. **Não existe** mecanismo de ingestão do catálogo que leia do
ArgoCD.

**O que existe no nosso repo:** `apps/bookinfo/catalog-info.yaml` traz a anotação
`argocd/app-name: bookinfo`. Anotação é campo de `metadata` destinado a
*"reference into external systems"* — ou seja, é um **ponteiro para um plugin de
visualização**, não uma fonte de catálogo.

**Correção da premissa:** o catálogo é alimentado pelo **Git**; o ArgoCD aparece como
**view**, via plugin que consome a anotação.

### 6.1 O plugin do ArgoCD — identificado

O README em `backstage/backstage/blob/master/plugins/argocd/` **dá 404 porque o
plugin não está mais lá**. Ele foi movido para o repositório de plugins da
comunidade. Entrada oficial no índice de plugins do Backstage
(`microsite/data/plugins/argocd.yaml`):

```yaml
npmPackageName: '@backstage-community/plugin-argocd'
authorUrl: https://redhat.com
category: CI/CD
description: Visualizes Argo CD application state and deployment lifecycle for catalog entities.
status: active
```

**A palavra é *"Visualizes"*.** É plugin de **visualização**, exatamente como você
apontou — não é fonte de catálogo. Há também um backend: `@backstage-community/plugin-argocd-backend`.

**Pré-requisito declarado:** exige os plugins de Kubernetes (frontend e backend)
instalados. No nosso caso o `plugin-kubernetes-backend` **já está** no backend.

**Anotações** (a segunda é a que existe no nosso `bookinfo`):

| Anotação | Função |
|---|---|
| `argocd/app-name: '<app>'` | busca **uma** aplicação |
| `argocd/app-selector: 'label.key=label.value'` | busca **várias** |
| `argocd/project-name` | projeto da Application |
| `argocd/app-namespace` | namespace da Application |
| `argocd/instance-name` | qual instância do ArgoCD |

> ⚠️ A doc avisa: *"You should not add both the annotations in the same catalog,
> adding both annotations will result in error in the plugin."* — `app-name` e
> `app-selector` são **mutuamente exclusivos**.

**O que renderiza:** abas *Deployment Lifecycle* e *Deployment Summary*, registradas
automaticamente para entidades que tenham as anotações (frontend system novo).
E — relevante — *"The Argo CD entity tabs are only shown to users authorized for
the `argocd.view.read` permission."*

**Estado no nosso repo:** os pacotes **não estão instalados**. Logo, o
`argocd/app-name` do `bookinfo` é hoje **inerte**: aponta para um plugin que não existe.

---

## 6.5 TechDocs — o que uma entidade precisa

Fonte: <https://backstage.io/docs/features/techdocs/creating-and-publishing> e
<https://backstage.io/docs/features/techdocs/configuration>

**Artefatos exigidos, na raiz do repositório do componente:**

```text
your-great-component/
  docs/
    index.md          # no mínimo isto
  catalog-info.yaml     # com backstage.io/techdocs-ref: dir:.
  mkdocs.yml
```

- `mkdocs.yml` — `site_name`, `nav`, `plugins` (o `techdocs-core` é injetado
automaticamente se faltar)
- A anotação `backstage.io/techdocs-ref: dir:.` é o gatilho
- Renomear a pasta `docs` é permitido, configurável no `mkdocs.yml`
- Syslink precisa resolver dentro da própria árvore, **ou o build é rejeitado**
- Documentação avulsa: um `Component` com `spec.type: documentation`

**Configuração — e é aqui que o nosso repo está no default de dev:**

| Chave | Valores | Observação oficial |
|---|---|---|
| `techdocs.builder` | `local` ou `external` | `local` = o backend gera e publica ao abrir a página ("Basic"); `external` = CI/CD gera, o backend só lê ("**Recommended**") |
| `techdocs.generator.runIn` | `docker` ou `local` | ⚠️ *"You want to change this to 'local' if you are running Backstage using your own custom Docker setup and want to avoid running into **Docker in Docker** situation"* |
| `techdocs.publisher.type` | `local`, `googleGcs`, `awsS3`, `azureBlobStorage` | `local` = diretório `static` na raiz do backend |

**Achado que conecta com o nosso laboratório:** o publisher `awsS3` tem a opção
`s3ForcePathStyle`, descrita na doc como: *"This allows providers like **LocalStack**,
Minio and Wasabi (and possibly others) to be used to host tech docs"*. Como o Floci
é drop-in do LocalStack, existe caminho documentado para publicar TechDocs em S3
do Floci — com `endpoint` + `s3ForcePathStyle: true`.

**Nosso estado atual:** `builder: local`, `generator.runIn: docker`,
`publisher.type: local`. Ou seja: o par `docker` + `local` que a doc trata como
configuração de desenvolvimento, rodando dentro de um Pod.

---

## 7. O que já existe neste repositório

Fatos verificados, sem interpretação:

| Onde | O que tem |
|---|---|
| `infrastructure/backstage/app.yaml` → `appConfig.catalog.rules` | `allow: [Component, System, API, Resource, Location, User, Group, Template]` — **sem `Domain`** |
| `infrastructure/backstage/app.yaml` → `appConfig.catalog.locations` | uma única location: `type: file` → `/etc/backstage-catalog/users.yaml` |
| `infrastructure/backstage/app.yaml` → `appConfig.integrations.github` | `host: github.com`, `token: ${GITHUB_TOKEN}` |
| Pod `backstage` → `envFrom` | `secret/backstage-github-token`, entre outros |
| `packages/backend/package.json` | `plugin-catalog-backend` ^3.9.0, `-module-logs`, `-module-scaffolder-entity-model` |
| `packages/backend/src/index.ts` | `backend.add` de catalog-backend, module-logs, module-scaffolder-entity-model — **nada de github** |
| `apps/bookinfo/catalog-info.yaml` | `Component` real, com `backstage.io/techdocs-ref` e `argocd/app-name` |
| `apps/backstage/catalog-info.yaml` | ainda o exemplo do `create-app` (`owner: john@example.com`, `lifecycle: experimental`) |
| `apps/backstage/app-config.yaml` e `app-config.production.yaml` | locations apontam para `examples/*`. ⚠️ **Correção — são arquivos de DEV LOCAL**, não do Pod. O processo roda com `--config /app/app-config-from-configmap.yaml` |
| ConfigMap `backstage-app-config` (o que o Pod **realmente** lê) | **uma única** location: `type: file` → `/etc/backstage-catalog/users.yaml`. Sem provider, sem location de repo, sem `examples/*` |
| `infrastructure/backstage/scripts/generate-catalog.py` | gera o ConfigMap de Users/Groups a partir do `users.csv`, aplicado **fora** do Git (motivo documentado no `scripts/README.md`) |

### Deduções diretas (fatos, não opinião)

- O `users.yaml` é uma location `type: file` — e a doc desaconselha `file` para
  produção.
- `apps/bookinfo/catalog-info.yaml` existe e **não é referenciado por nenhuma
  location** — nenhum mecanismo atual o lê.
- `apps/backstage/catalog-info.yaml` define `metadata.name: backstage`. Como nome
  duplicado faz *"one will be processed and all others will be skipped"*, isso é
  relevante para qualquer entidade futura com o mesmo nome.
- A lista de `rules` exclui `Domain` — qualquer entidade desse kind seria rejeitada.

---

## 8. Lacunas desta pesquisa

### Fechadas

1. ✅ **Plugin do ArgoCD** — identificado: `@backstage-community/plugin-argocd`
   (+ `-backend`), da Red Hat, categoria CI/CD, status *active*. É de
   **visualização**, exige os plugins de Kubernetes e a permissão `argocd.view.read`.
   A anotação `argocd/app-name` é dele. Ver §6.1.
2. ✅ **TechDocs** — artefatos, anotação e todas as opções de `builder`,
   `generator.runIn` e `publisher`. Ver §6.5.
3. ✅ **Implicação do nosso `appConfig` de TechDocs** — `runIn: docker` + `publisher: local`
   é a configuração que a doc associa a desenvolvimento; a própria doc recomenda
   `local` para evitar Docker-in-Docker. Ver §6.5.

### Ainda abertas

4. **Páginas de referência não abertas:** `well-known-relations` e
   `well-known-annotations`. O mapa de relações do §5.3 veio do *descriptor format*,
   que é suficiente para o plano, mas a lista canônica de anotações não foi lida.
5. **Permissão** — existe `@backstage/plugin-permission-backend` com
   `allow-all-policy` no nosso backend. O plugin do ArgoCD declara que as abas
   dependem da permissão `argocd.view.read`. **Não pesquisei** como uma
   `allow-all-policy` se comporta diante de uma permissão nomeada de plugin — pode
   liberar ou pode não reconhecer.
6. **Nomes dos `Group` existentes** — o `users.yaml` é gerado do `users.csv` e
   aplicado fora do Git. Como `spec.owner` é **obrigatório** em `Component`,
   `System`, `Resource`, `Domain` e `API`, e o owner precisa **existir** no
   catálogo, é pré-requisito do plano saber os nomes. Não inspecionei (contém
   dado pessoal).

---

## 9. Próximo passo

Fase 2 — **Plano**: propor o modelo de entidades (quais kinds, quais nomes, quais
relações, como entram no catálogo e a custo de quê), com as decisões em aberto
explícitas. Só depois da aprovação, Fase 3 — implementação.
