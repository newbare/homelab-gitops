# Keycloak — Identity Provider do homelab

Keycloak é o **provedor de identidade (IDP)** do laboratório. Centraliza
autenticação e autorização dos apps da stack via **OIDC**, começando pelo Backstage.

> **Por que existe:** a Fase 9 (Floci + Terraform + Lambda) criou usuários
> (IAM + SSO) a partir de uma planilha. O Keycloak é a peça que transforma esses
> mesmos usuários em identidade real dos apps internos, fechando o ciclo
> `users.csv` → Keycloak → Backstage.

---

## Como é implantado

A Application `keycloak` vive neste diretório ([`app.yaml`](./app.yaml)) e é
gerenciada pelo ArgoCD.

| Item | Valor |
|---|---|
| Chart | `bitnami/keycloak` **24.4.0** |
| Repositório do chart | `https://charts.bitnami.com/bitnami` (upstream) |
| Imagem | `bitnamilegacy/keycloak:26.0.7-debian-12-r0` |
| Namespace | `keycloak` |
| `sync-wave` | `8` |
| Sync policy | automated + `prune` + `selfHeal` |
| Sync options | `CreateNamespace=true`, `ServerSideApply=true` |

### ⚠️ Padrão de Application: chart upstream com values inline

Diferente do MetalLB e do PostgreSQL, esta Application **não aponta para um `path`
do repositório GitOps** — o `PATH` dela aparece vazio no ArgoCD:

    NAME       PATH     CHART      TARGET   SYNC     HEALTH
    keycloak   <none>   keycloak   24.4.0   Synced   Healthy

O motivo é que a `source` referencia o **repositório Helm do Bitnami** e traz os
`values` **embutidos no próprio manifesto** da Application:

    source:
      repoURL: https://charts.bitnami.com/bitnami
      chart: keycloak
      targetRevision: 24.4.0
      helm:
        values: |
          ...

Ou seja: o que está versionado no Git é **a Application + os values** — não os
manifestos renderizados. Isso é intencional, pois fixa a versão do chart
(`targetRevision`) e mantém os values auditáveis.

> 💡 **Consequência prática:** o ArgoCD renderiza o chart (equivalente a um
> `helm template`) e aplica com `kubectl`. Ele **não cria um release Helm**.
> Por isso `helm list -n keycloak` retorna **vazio** — e isso **não é problema**.
> Não existem `helm upgrade` nem `helm rollback` aqui: o ciclo de vida é do ArgoCD.

### ⚠️ Mudou este `app.yaml`? Um `git push` NÃO basta

Esta é a pegadinha número um deste componente.

O ArgoCD sincroniza o **chart do Bitnami** com os valores que estão **dentro do objeto
Application no cluster**. Ele **não observa** o arquivo `infrastructure/keycloak/app.yaml`
do repositório — quem coloca esse arquivo no cluster é um `kubectl apply`.

    editar app.yaml → git commit/push      →  NADA acontece
    kubectl apply -f infrastructure/keycloak/app.yaml  →  aí sim

**Como desconfiar que você caiu nisso:** numa Application baseada em chart, o
`status.sync.revision` é a **versão do chart**, não um commit:

    kubectl -n argocd get application keycloak \
      -o jsonpath='{.status.sync.revision}{"\n"}'
    # 24.4.0

E `Synced` quer dizer *"igual ao que o ArgoCD observou"* — **não** *"igual ao GitHub agora"*.
Um `Synced` verde pode estar desatualizado.

**Conferir se o objeto no cluster tem os valores novos:**

    kubectl -n argocd get application keycloak \
      -o jsonpath='{.spec.source.helm.values}' | grep -A 9 'ingress:'
    # se aparecer "enabled: false", o cluster está com a versão antiga

**Aplicar:**

    kubectl apply -f infrastructure/keycloak/app.yaml
    # esperado: application.argoproj.io/keycloak configured

Depois do `apply`, o ArgoCD detecta a mudança de values e sincroniza sozinho.

> 📌 Vale para **todas** as Applications baseadas em `chart` (`keycloak`, `istio`,
> `backstage`, `kube-prometheus-stack`...). As baseadas em `path` do Git (como
> `postgresql` e `metallb`) **são** atualizadas pelo próprio commit.
>
> **Backlog:** um "App of Apps" — uma Application que gerencia `infrastructure/` —
> elimina essa exceção e faz o `git push` bastar para tudo.

---

## Recursos criados

| Recurso | Nome | Detalhe |
|---|---|---|
| StatefulSet | `keycloak` | 1 réplica (pod `keycloak-0`) |
| Service | `keycloak` | ClusterIP, porta **80** |
| Service | `keycloak-headless` | ClusterIP `None`, porta 8080 |
| Secret | `keycloak-admin` | chave `admin-password` |
| Secret | `keycloak-postgresql` | chave `password` |

- **Recursos do container:** requests `512Mi` / `250m`, limits `1Gi` / `1000m`
- **Config:** `production: true`, `proxy: edge`, métricas desabilitadas

> ⚠️ Nenhum dos dois Secrets está versionado no Git — este diretório contém apenas
> `app.yaml`, este `README.md` e `scripts/`. Eles precisam existir **antes** do
> primeiro sync, senão os pods ficam presos em `CreateContainerConfigError`.

---

## Acesso

O Keycloak é exposto pelo **Ingress do próprio chart** (nginx + TLS via cert-manager):

| | |
|---|---|
| **URL** | `https://keycloak.local` |
| **Console admin** | `https://keycloak.local/admin` |
| **Realms** | `master` (onde vive o admin) · `resilience` (onde vivem os usuários) |

O nome precisa resolver no seu Mac — uma linha no `/etc/hosts`:

    192.168.99.200  keycloak.local

Para conferir:

    grep keycloak.local /etc/hosts
    # esperado: 192.168.99.200  keycloak.local

> ⚠️ **O navegador vai avisar "Não seguro".** O certificado é autoassinado
> (`ClusterIssuer selfsigned-issuer`), então nenhuma máquina confia nele por padrão.
> É esperado no laboratório. Como resolver está em
> [`docs/certificados/`](../../docs/certificados/).

> 💡 **Não é mais necessário `kubectl port-forward`.** Antes o Keycloak não tinha
> Ingress, e o túnel caía sozinho com frequência (`lost connection to pod`). Hoje o
> acesso é direto pelo hostname. Este é o motivo pelo qual `hostnameStrict: true`
> está ativo: ele fixa a URL pública que o Keycloak anuncia no discovery OIDC.

### Leitura da senha do admin

    kubectl -n keycloak get secret keycloak-admin \
      -o jsonpath='{.data.admin-password}' | base64 -d

> ⚠️ O Secret chama-se **`keycloak-admin`**. Não existe Secret chamado `keycloak`.

---

## Banco de dados

O Keycloak **não** sobe banco próprio. Ele usa o **PostgreSQL compartilhado** —
regra de ouro do projeto: um Postgres único para toda a stack, com
database + user por aplicação.

| Item | Valor |
|---|---|
| Host | `postgresql.postgresql.svc.cluster.local` |
| Porta | `5432` |
| Database | `keycloak` |
| User | `keycloak` |
| Secret da senha | `keycloak-postgresql` (chave `password`) |
| Postgres do chart | **desabilitado** (`postgresql.enabled: false`) |

---

## Provisionamento de usuários

O provisionamento em massa (realm, client, roles e usuários) fica em
[`scripts/`](./scripts/README.md), que tem **README próprio**: formato do CSV/XLSX,
variáveis de ambiente, alvos do `Makefile` e considerações de segurança.

Resumo: `make dry-run` para simular, `make run` para aplicar.

> 📌 Este documento cobre **o componente Keycloak**. Para provisionamento, consulte
> o README do script — evita ter a mesma informação em dois lugares (fontes únicas).

---

## Troubleshooting

### 1. Pod reinicia com `exitCode: 1` — falha de DNS na partida

**Sintoma:** `kubectl -n keycloak get pod` mostra vários `RESTARTS`.

**Diagnóstico** (o container atual é um processo novo, então o erro **não** está no
log dele — é preciso ler o do anterior):

    kubectl -n keycloak logs keycloak-0 --previous --tail=40

**Log típico:**

    Trying to connect to PostgreSQL server postgresql.postgresql.svc.cluster.local...
    cannot resolve host "postgresql.postgresql.svc.cluster.local":
      lookup postgresql.postgresql.svc.cluster.local: Temporary failure in name resolution
    ERROR ==> Unable to connect to host postgresql.postgresql.svc.cluster.local

**Causa raiz:** falha **transitória** de resolução DNS (CoreDNS indisponível no
instante em que o container subiu). O container tenta por cerca de 50 segundos,
desiste e sai com `exitCode: 1`; o reinício seguinte normalmente conecta.

**Distinção que importa:**

| Mensagem | Significado |
|---|---|
| `Temporary failure in name resolution` | Infraestrutura — o DNS não respondeu a tempo |
| `no such host` | Configuração — o nome não existe (Service errado) |

Aqui é o **primeiro** caso: o nome do Service está correto.

**Impacto no provisionamento:** se o pod reiniciar durante um `make run`, o script
pode receber erro de conexão. Ele tem retry (5 tentativas com backoff exponencial),
então deve sobreviver — mas se aparecer erro de conexão no provisioner, **a primeira
coisa a verificar é se o Keycloak reiniciou**.

**Verificação do estado de terminação:**

    kubectl -n keycloak get pod keycloak-0 \
      -o go-template='{{range .status.containerStatuses}}restarts: {{.restartCount}}
    lastState: {{.lastState}}
    {{end}}'

> 🕵️ Investigação em aberto (não bloqueante): por que o CoreDNS fica
> momentaneamente indisponível. Possíveis causas: pressão de recursos no nó,
> restart do próprio CoreDNS, ou timing de partida.

---

## Referências

- [`scripts/README.md`](./scripts/README.md) — provisioner de usuários
- [`app.yaml`](./app.yaml) — manifesto da Application
- [`docs/00-visao-geral.md`](../../docs/00-visao-geral.md) — visão geral do projeto
- [`infrastructure/postgresql/`](../postgresql/) — PostgreSQL compartilhado
