# Relatório de Auditoria — homelab-gitops

> **Prompt aplicado:** [`00-prompt-avaliacao-maturidade.md`](./00-prompt-avaliacao-maturidade.md) **v1.1**
> **Avaliação anterior do prompt:** [`01-revisao-do-prompt.md`](./01-revisao-do-prompt.md)
> **Data:** 2026-09-19 · **Método:** evidência de `repo`, `chart-default` e `cluster-live`

---

## 1. Executive Summary

**Nota global: 4,8 / 10** — abaixo da meta declarada de 70%.

A plataforma tem **operação madura e segurança imatura**. O que existe é bem feito:
21 Applications no ArgoCD com `selfHeal` em 19, esquema de `sync-wave` ordenado de
`-2` a `8`, versões de chart pinadas, nenhum segredo no Git, TLS interno com CA
própria distribuída por trust-manager, documentação por fase com runbook. Isso é
gitops de verdade, não `kubectl apply` fantasiado.

O que falta é **controle**, não intenção: **nenhum** namespace tem Pod Security
Admission, **nenhuma** NetworkPolicy foi escrita por nós (as 8 existentes vieram
de chart), o Istio está instalado mas **sem `PeerAuthentication`** — logo mTLS em
`PERMISSIVE` — e **não existe backup de nada**. Três PVCs em `microk8s-hostpath`
guardam o PostgreSQL (catálogo do Backstage + usuários do Keycloak), o Grafana e o
Prometheus. Se o nó morrer, **o catálogo e os acessos vão junto**.

O gargalo não é conhecimento arquitetural — os `sync-wave` provam que há. É
**enforcement**: quase tudo está declarado como boa prática, raramente como
impossibilidade de errar.

---

## 2. Scorecard por Pilar

Rubrica aplicada: `0–2 inexistente · 3–4 declarado mas não aplicado · 5–6 aplicado sem verificação · 7–8 verificado e documentado · 9–10 verificado, automatizado e testado contra falha`

| Pilar | Nota | Rubrica | Evidência principal |
|---|:--:|---|---|
| 🔄 **GitOps & Automação** | **8** | verificado e documentado | 21 Applications; `automated` em **19/21**; `sync-wave` de `-2` a `8`; `prune:false` deliberado em `namespaces` e `cert-manager-ca` |
| 🏛️ **CCoE & Governança (CAF)** | **6** | aplicado sem verificação | `docs/` por fase + runbooks; naming por labels de chart; **mas** fonte de verdade dupla de namespaces e política de upgrade inexistente |
| 🛡️ **DevSecOps & OWASP** | **4** | declarado mas não aplicado | TLS interno OK; **PSA ausente em 15/15 ns**; **0 NetworkPolicy autoral**; **mTLS `PERMISSIVE`** |
| 📈 **SRE & Resiliência (WAF/DORA)** | **3** | declarado mas não aplicado | probes parciais; **0 backup**; sem RPO/RTO declarado; DORA não mensurável |
| 💰 **Eficiência de Recursos** | **3** | declarado mas não aplicado | `limits=0` em ~90% dos workloads; sem `LimitRange`/`ResourceQuota` |

**Média simples: (8 + 6 + 4 + 3 + 3) / 5 = 4,8**

---

## 3. Achados Principais

### ✅ Pontos fortes (com evidência)

1. **Automação GitOps real.** `automated: {"prune":true,"selfHeal":true}` em 19 das
   21 Applications. As duas exceções são **deliberadas e corretas**: `namespaces`
   (`prune:false` — não deixar o ArgoCD apagar namespaces) e `cert-manager-ca`
   (`prune:false` — proteger a CA raiz). *Origem: `cluster-live`.*
2. **`sync-wave` sistemático e ordenado** — o achado mais forte do repositório:

   | wave | componentes |
   |:--:|---|
   | `-2` | metrics-server |
   | `-1` | namespaces |
   | `0` / `1` / `2` | istio-base / istiod / gateway |
   | `4` | cert-manager, kube-prometheus-stack |
   | `5` | kiali-operator, jaeger-operator, trust-manager |
   | `6` | CA interna, jaeger, kiali, CRs |
   | `7` | backstage, certificado do backstage |
   | `8` | keycloak, ingress do backstage |

   *Origem: `repo` — 20 ocorrências em `infrastructure/**`.*
3. **Versões pinadas, nenhum `:latest`.** Charts em `2.10.1`, `v1.19.0`, `1.30.4`,
   `24.4.0`, `91.2.1`, `2.31.0`, `3.14.0`, `v0.25.0`; imagem própria
   `newbare/homelab-backstage:v27`; `postgres:17-alpine`. *Origem: `cluster-live` + `repo`.*
4. **Nenhum segredo no Git.** Zero `kind: Secret` em `infrastructure/**`.
   *Origem: `repo`.*
5. **TLS interno com evolução consciente.** Commit `125e424` ("trust-manager
   distribui a CA e substitui a **cópia manual**") troca procedimento imperativo
   por distribuição declarativa. *Origem: `repo` (histórico).*
6. **Documentação de nível acima da média** para um laboratório: jornadas por fase,
   `04-runbook.md`, `05-troubleshooting.md`, decisões registradas.
7. **RBAC sem excesso.** Existe **1** binding `cluster-admin` — o padrão do
   Kubernetes, com subject `system:masters`. Nenhuma concessão custom.
   *Origem: `cluster-live`.*
8. **Kubernetes v1.35.6** — versão atual. *Origem: `cluster-live`.*

### ⚠️ Lacunas (com estado declarado)

1. **mTLS não aplicado.** Istio instalado, mas `kubectl get peerauthentication -A`
   → **"No resources found"**. Sem `PeerAuthentication`, o modo é `PERMISSIVE`:
   tráfego em texto claro entre pods é aceito. Além disso, o único namespace com
   `istio-injection: enabled` declarado no repo é o `default` — onde roda o
   **bookinfo** (demo), não os serviços reais. **Estado: ausente.**
2. **Pod Security Admission: ausente em 15/15 namespaces.** Nenhum label
   `pod-security.kubernetes.io/enforce`. Nada impede um Pod de rodar como root,
   com `privileged` ou com filesystem gravável. **Estado: ausente.**
3. **NetworkPolicy: 8 existentes, 0 autorais.** Todas vêm de chart (6 do ArgoCD,
   1 do Keycloak, 1 do Kiali). **Nenhum `default-deny`.** O "isolamento entre
   namespaces" citado no prompt é **nominal, não real**. **Estado: parcial.**
4. **Backup e DR: inexistentes.** 3 PVCs, todas em `microk8s-hostpath` (nó único,
   `RWO`): `postgresql` 10Gi, `prometheus` 10Gi, `grafana` 5Gi. Sem
   `VolumeSnapshot`, sem Velero, sem `pg_dump` agendado, **sem restore testado**,
   **sem RPO/RTO declarado**. *Origem: `cluster-live`.* **Estado: ausente.**
5. **`resources.limits` em ~90% dos workloads = 0.** Sem `LimitRange` nem
   `ResourceQuota`, o nó único não tem proteção contra vizinho barulhento.
   **Estado: ausente.**
6. **Fonte de verdade dupla para namespaces.** `infrastructure/namespaces/` declara
   **apenas** o namespace `default`. Os outros 11 (`backstage`, `monitoring`,
   `postgresql`, `keycloak`, `observability`, `argocd`, `cert-manager`,
   `metallb-system`, `istio-system`, `kiali-operator`, `ingress-nginx`) existem por
   efeito colateral de `CreateNamespace=true` nas Applications. Não há um lugar
   onde se leia "quais namespaces existem". **Estado: parcial.**
7. **Dependência mais crítica ordenada por acidente.** `infrastructure/postgresql/app.yaml`
   **não tem `sync-wave`**; o Keycloak está em `8`. Funciona porque a ausência
   resulta em `0` — mas o banco não está declarado antes de quem depende dele.
   É literalmente o cenário de CFR citado no prompt. **Estado: parcial.**
8. **Segredos: fora do Git, mas não reproduzíveis.** Não há `kind: Secret`
   (bom), porém **nenhum mecanismo declarativo** — sem SOPS, sem Sealed Secrets,
   sem External Secrets. Segredos são criados à mão (ex.: `keycloak-admin`).
   Rebuild do cluster **não** traz os segredos de volta. **Estado: parcial.**
9. **Probes incompletos.** Sem `liveness`/`readiness`: `argocd-applicationset-controller`,
   `argocd-dex-server`, `argocd-notifications-controller`, `trust-manager`
   (live=0), `jaeger-operator`, `hostpath-provisioner` e o **`istio-ingress`
   (live=0 / ready=0)**. *Origem: `cluster-live`.* **Estado: parcial.**
10. **`securityContext` não declarado nos nossos manifests.** `runAsNonRoot`
    aparece como `true` em cert-manager, Grafana, MetalLB, ArgoCD Redis,
    kube-state-metrics, node-exporter e Prometheus — mas isso é **`chart-default`**,
    não mérito do repo. Em `postgresql`, `keycloak`, `backstage`, `jaeger` e
    `istio` não há `securityContext`. **Estado: parcial.**
11. **Supply chain no mínimo.** Tags por versão, mas **sem digest** (`@sha256`),
    sem scan de CVE, sem SBOM, sem assinatura. **Estado: ausente.**
12. **DORA não mensurável com a amostra disponível.** Histórico de `main` cobre
    **2 semanas ISO**: W37 = 29 commits, W38 = 107 commits. Reversões = **2**
    (`21d4822`, `bca9082`, ambas rotuladas "reverter", Fase 7). CFR proxy ≈ 1,5% —
    mas **n pequeno demais para conclusão**. Lead time: **não mensurável** (sem
    timestamps de PR/merge por commit). **Estado: não mensurável.**

---

## 4. Matriz de Riscos e Recomendações

Formato: `item | estado | risco | evidência (origem) | ação | arquivo-alvo`

| # | Item | Estado | Risco | Evidência (origem) | Ação | Arquivo-alvo |
|---|---|---|---|---|---|---|
| 1 | Backup do PostgreSQL | **ausente** | 🔴 | 3 PVC em `microk8s-hostpath`, sem snapshot *(cluster-live)* | CronJob `pg_dump` + PVC de backup + **restore testado** | `infrastructure/postgresql/backup-cronjob.yaml` |
| 2 | Pod Security Admission | **ausente** | 🔴 | 15/15 ns sem label `pod-security.kubernetes.io/*` *(cluster-live)* | `enforce: baseline` nos ns de app | `infrastructure/namespaces/*` |
| 3 | mTLS do Istio | **ausente** | 🟡 | `get peerauthentication -A` vazio *(cluster-live)* | `PeerAuthentication` + ampliar injeção de sidecar | `infrastructure/istio/peerauthentication.yaml` |
| 4 | NetworkPolicy `default-deny` | **ausente** | 🟡 | 8 netpol, todas de chart; 0 autorais *(cluster-live)* | `default-deny` por namespace + liberação explícita | `infrastructure/<ns>/networkpolicy.yaml` |
| 5 | `limits`/`requests` | **ausente** | 🟡 | `limits=0` em ~90% dos workloads *(cluster-live)* | `LimitRange` + `ResourceQuota`; depois `resources` por app | `infrastructure/<ns>/limitrange.yaml` |
| 6 | Ordering do banco | **parcial** | 🟡 | `postgresql/app.yaml` sem `sync-wave`; keycloak em `8` *(repo)* | `sync-wave: "-1"` no postgresql | `infrastructure/postgresql/app.yaml` |
| 7 | Fonte de verdade de namespaces | **parcial** | 🟡 | só `default` declarado; 11 por `CreateNamespace=true` *(repo + cluster-live)* | declarar todos em `infrastructure/namespaces/` | `infrastructure/namespaces/` |
| 8 | Secrets declarativos | **parcial** | 🟡 | 0 `kind: Secret`; 0 SOPS/SealedSecrets/ESO *(repo)* | Sealed Secrets ou External Secrets | `infrastructure/secrets/` |
| 9 | Probes faltantes | **parcial** | 🟡 | 7 workloads sem probe; `istio-ingress` live=0/ready=0 *(cluster-live)* | habilitar via `values` | `infrastructure/<app>/app.yaml` (override) |
| 10 | Supply chain | **ausente** | 🟢 | sem digest, sem SBOM, sem scan *(repo)* | pinar por digest + Trivy no CI | `.github/workflows/` |
| 11 | `securityContext` | **parcial** | 🟢 | `nao-declarado` em postgresql/keycloak/backstage/jaeger/istio *(cluster-live)* | `runAsNonRoot` + `readOnlyRootFilesystem` (avaliar caso a caso) | `infrastructure/<app>/app.yaml` |
| 12 | Política de upgrade | **ausente** | 🟢 | charts pinados, sem política escrita *(repo)* | seção de upgrade no runbook | `docs/**/04-runbook.md` |

> ⚠️ **Nota de origem que muda a correção:** 12 das 21 Applications são **charts
> externos** (backstage, cert-manager, istio ×3, keycloak/bitnami, jaeger-operator,
> kiali-operator, kube-prometheus-stack, metrics-server, trust-manager). Nesses
> casos, o fix **não vai no repo** — vai como override em `values` na Application.
> Escrever `livenessProbe` em YAML nosso para um chart externo é manifest morto.

### YAMLs de exemplo

**1. Backup do PostgreSQL** — *a única ação que resolve risco irreversível.*
⚠️ Confirmar o nome/chave do Secret antes de aplicar.

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgresql-backup
  namespace: postgresql
  annotations:
    argocd.argoproj.io/sync-wave: "5"
spec:
  schedule: "0 3 * * *"          # 03:00 diário
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: pg-dump
              image: postgres:17-alpine
              env:
                - name: PGPASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: <SECRET-DO-POSTGRESQL>   # CONFIRMAR
                      key: postgres-password         # CONFIRMAR
              command: ["/bin/sh", "-c"]
              args:
                - pg_dump -h postgresql -U postgres -Fc app > /backup/app-$(date +%Y%m%d).dump
              volumeMounts:
                - { name: backup, mountPath: /backup }
          volumes:
            - name: backup
              persistentVolumeClaim: { claimName: postgresql-backup }
```

**2. Pod Security Admission + `default-deny` + `LimitRange`** (exemplo: `backstage`).
PSA em `baseline` (não `restricted`) porque `restricted` exige
`readOnlyRootFilesystem`, e nenhum workload nosso declara isso — subir direto para
`restricted` derruba o cluster.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: backstage
  labels:
    pod-security.kubernetes.io/enforce: baseline    # bloqueia
    pod-security.kubernetes.io/audit: restricted    # só audita o degrau acima
    pod-security.kubernetes.io/warn: restricted
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: backstage
spec:
  podSelector: {}
  policyTypes: [Ingress]
---
apiVersion: v1
kind: LimitRange
metadata:
  name: defaults
  namespace: backstage
spec:
  limits:
    - type: Container
      defaultRequest: { cpu: 100m, memory: 128Mi }
      default:        { cpu: 500m, memory: 512Mi }
```

**3. mTLS `STRICT`** — ⚠️ **não aplicar antes de ampliar a injeção de sidecar.**
Com sidecar só no `default`, `STRICT` mesh-wide quebra o tráfego dos workloads sem
sidecar. A ordem correta é: (a) injetar sidecar nos namespaces reais,
(b) validar com tráfego real, (c) só então `STRICT`.

```yaml
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: default
  namespace: istio-system
spec:
  mtls:
    mode: STRICT
```

**4. `sync-wave` do PostgreSQL** — 1 linha, fecha o CFR do próprio prompt.

```yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "-1"   # banco antes de quem consome
```

---

## 5. Roteiro de Evolução (3 passos)

**Passo 1 — Parar a sangria (hoje).**
Backup do PostgreSQL + restore testado. É o único item que **não se recupera
depois**: os outros são dívida, este é perda. Sem ele, tudo o mais é cosmético.

**Passo 2 — Trocar intenção por controle (esta semana).**
PSA `baseline` nos namespaces de aplicação, `default-deny` de NetworkPolicy e
`LimitRange`. São declarações curtas e mudam a natureza do ambiente: deixam de
existir "boas práticas que ninguém segue" e passam a existir **bloqueios**.

**Passo 3 — Tornar o ambiente reconstruível (próximas duas semanas).**
Seqüência: `sync-wave` no postgresql → mecanismo de segredo declarativo
(Sealed Secrets/ESO) → fonte única de namespaces → mTLS em `STRICT` **depois** de
ampliar a injeção. Ao fim, o cluster deve nascer do zero a partir do repo.

---

## 6. Limites desta Avaliação

O que **não** foi possível medir, e por quê:

- **DORA completo.** Só 2 semanas de histórico em `main`; sem timestamps de
  PR/merge por commit, **lead time não é mensurável**. CFR é proxy grosseiro.
- **Comportamento sob falha.** Volumes, latência e limites reais exigiriam carga.
  O que existe aqui é configuração declarada, não comportamento verificado.
- **`values` efetivos dos charts externos.** As notas de segurança dos 12 charts
  derivam do default do chart; não abri os `values` de cada um linha a linha.
- **Escopo excluído por decisão:** custo de nuvem (não existe), SLA (não existe),
  multi-nó/HA (topologia é nó único). Lacunas aqui são **fora de escopo**, não falha.
- **Nota é ponto no tempo.** Sem a rubrica, repetir a auditoria não geraria
  linha de base — com ela, esta é a linha zero.
