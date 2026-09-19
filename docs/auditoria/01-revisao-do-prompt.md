# Revisão do Prompt de Auditoria — v1.0 → v1.1

> **Avaliado:** [`00-prompt-avaliacao-maturidade.md`](./00-prompt-avaliacao-maturidade.md) v1.0
> **Data:** 2026-09-19 · **Método:** confronto do prompt com o estado real do repo
> (não com a intenção declarada nele)

## Veredito curto

O prompt é **bom em ambição e fraco em aterrissagem**. Ele descreve a arquitetura
errada em dois pontos, exige métricas que manifesto nenhum contém, e contém uma
**contradição estrutural** que faz a auditoria ser incapaz de responder parte das
próprias perguntas. Corrigido, ele serve; como está, ele produz falso negativo.

---

## 🔴 1. Contradição estrutural: o repo não tem o que a regra manda ler

A **Regra de Saída nº 1** diz: *"Apenas avalie com base nos arquivos YAML,
documentações e código do repositório. Não pressuponha funcionalidades não
declaradas."*

**O problema:** a maior parte dos workloads deste repo é **Helm-chart-based**.
O ArgoCD não aplica manifesto nosso para Backstage, Keycloak, Istio, Kiali,
Jaeger, Prometheus, MetalLB, Cert-Manager — ele aponta para um **chart de
terceiro** e passa `values`. Foi verificado:

```
$ kubectl -n argocd get application backstage -o jsonpath='{.spec.source.repoURL}'
https://backstage.github.io/charts
```

**Consequência:** perguntas como *"os Pods têm `livenessProbe`?"*,
*"executam como não-root?"* ou *"quais são os `requests`/`limits`?"* **não têm
resposta nos arquivos do repo** quando o valor vem do default do chart. O
auditor obediente vai responder **"não há"** — e estar errado.

Evidência do falso negativo, medida nos manifestos do repo:

| Verificação | Achado nos YAML do repo |
|---|---|
| `livenessProbe`/`readinessProbe`/`startupProbe` | 2 arquivos (`postgresql/statefulset.yaml`, `keycloak/app.yaml`) |
| `resources:` | 5 arquivos |
| `image:` | 1 (`postgres:17-alpine`) |

Se o auditor concluir *"só 2 de 15 workloads têm probe"*, ele auditou a pobreza
do repositório, não a pobreza da plataforma.

**Correção (v1.1):** ampliar a fonte de evidência, sem abrir mão do rigor:

> Além dos arquivos do repositório, é permitido usar como evidência o **estado
> derivado declarativamente**: `helm template <chart> -f values.yaml`,
> `argocd app manifests <app>` e `kubectl get <recurso> -o yaml` no cluster.
> Toda conclusão deve declarar a **origem da evidência**
> (`repo`, `chart-default`, `cluster-live`) — porque a correção vai em lugares
> diferentes. Onde a evidência for chart-default, **não invente** que está no repo.

---

## 🔴 2. O prompt viola a própria regra de não pressupor

Ele afirma coisas que não existem no repositório:

- **Namespaces.** O prompt cita `default`, `app`, `observability`, `keycloak`.
  O que os manifestos realmente declaram (`namespace:` em `infrastructure/**`):

  ```
  19 argocd · 5 observability · 5 backstage · 4 postgresql · 4 kiali-operator
   4 cert-manager · 3 istio-system · 2 monitoring · 2 metallb-system
   1 kube-system · 1 keycloak · 1 ingress-nginx · 1 default
  ```

  `app` **não aparece** — porque nunca existiu. Ele veio do **nome do arquivo**:
  `infrastructure/namespaces/app.yaml` não é um namespace, é a `Application`
  `namespaces` (o único `Namespace` que aquele diretório declara é o `default`).
  Como o prompt usa essa lista para julgar "isolamento adequado", a pergunta já
  nasce enviesada.

- **Imagens Bitnami.** ~~Não há nenhuma referência a Bitnami em
  `infrastructure/`.~~ ⚠️ **CORREÇÃO (verificada depois):** o **Keycloak** roda a
  partir de `https://charts.bitnami.com/bitnami` rev `24.4.0`. Bitnami **está** na
  arquitetura — só não está nos arquivos de `infrastructure/`, e sim no
  `spec.source.repoURL` da Application. O prompt estava **certo** ao citá-la.
  Este item é o **quarto erro** meu do dia no mesmo padrão: concluir por ausência
  no que eu inspecionei. Fonte certa: `kubectl -n argocd get applications`.

**Correção real:** trocar exemplos afirmativos por perguntas abertas, ou removê-los.
Exemplo afirmativo no prompt faz o auditor **confirmar** em vez de **verificar** —
foi exatamente o que aconteceu comigo aqui.

---

## 🟡 3. DORA não é auditável por manifesto

DF, LTC, CFR e MTTR/TTRS exigem **telemetria temporal**: histórico de commits,
tags de release, janelas de incidente, execuções de pipeline. Nada disso está em
YAML. Com a Regra nº 1 como está, o auditor não pode responder — e vai chutar.

**Correção:** declarar explicitamente a fonte permitida e o critério de
indisponibilidade:

> Para DORA, use **proxy mensurável a partir do Git**: intervalo entre commit e
> merge (lead time), contagem de commits em `main` por semana (deploy frequency),
> reversões e `git revert` (CFR). Se o dado não existir, responda
> **"não mensurável com a evidência disponível"** — nunca estime.

---

## 🟡 4. Eixos ausentes — buracos maiores que os presentes

O prompt cobre bem CAF/WAF/12-Factor/OWASP/DORA, mas omite o que mais dói:

| Eixo ausente | Por que importa aqui |
|---|---|
| **Backup & DR** | PostgreSQL e Keycloak são stateful. Onde está o backup de PVC? Existe restore testado? (WAF Reliability) |
| **NetworkPolicy** | O prompt fala de "isolamento entre namespaces" mas não pergunta se **existe** `NetworkPolicy`. Sem ela, o isolamento é nominal, não real. |
| **Admission control / PSA** | Pergunta *"os Pods rodam como não-root?"* mas não *"o que impede um Pod de rodar como root?"*. Diagnóstico ≠ enforcement. Sem Kyverno/Gatekeeper/PSA, a resposta é "nada impede". |
| **Secrets no GitOps** | Factor III pergunta se segredo está fora do Git, mas não qual o mecanismo (SOPS, Sealed Secrets, External Secrets). É a lacuna clássica de GitOps. |
| **Supply chain** | Tags pinadas são o mínimo. Falta: scan de CVE, SBOM, assinatura (cosign), imagem base distroless. |
| **RBAC de cluster** | O eixo de IAM está todo em Keycloak/SSO. Falta RBAC nativo: ServiceAccounts, `ClusterRoleBinding` amplo, `automountServiceAccountToken`. |
| **Política de upgrade** | Versão de k8s e dos charts: pinada? Existe caminho de upgrade? Drift de versão vs. documentação? |

**FinOps, num homelab de nó único, é quase vazio** — não há fatura. Vale
reenquadrar o pilar como **"Eficiência de Recursos"**: dimensionamento correto no
nó compartilhado, ausência de `requests` inflados, desperdício de réplica. Do
contrário o pilar vira ritual e derruba a média sem motivo.

---

## 🟡 5. Sem escopo declarado, todo gap vira falha

O prompt não diz **qual é a meta**. Um homelab de estudo não deve ser medido como
landing zone de banco. Sem isso:

- a nota global fica arbitrária,
- o relatório vira lista de culpa e não de prioridades,
- e execuções diferentes não são comparáveis.

**Correção:** declarar no topo, e deixar explícito no relatório:

> **Escopo:** laboratório individual, nó único, sem SLA e sem fatura de nuvem.
> **Meta declarada:** `<ex: 70% de aderência em segurança e GitOps>`.
> Lacunas fora do escopo declarado são registradas como **"fora de escopo"**,
> não como falha.

---

## 🟢 6. Rubrica de nota não definida

Cinco pilares de 0 a 10, sem âncora: o que é 3? o que é 7? Sem rubrica, a nota
varia entre execuções e não serve como linha de base — que é justamente o valor
de repetir a auditoria.

**Correção:** fixar âncora por faixa, ao menos grosseira:
`0–2 inexistente · 3–4 declarado mas não aplicado · 5–6 aplicado sem verificação ·
7–8 verificado e documentado · 9–10 verificado, automatizado e testado contra falha`.

E exigir que toda nota venha com **evidência + arquivo**, no formato
`nota | evidência | origem (repo/chart-default/cluster-live) | arquivo`.

---

## 🟢 7. Ajustes de forma

- **Matriz de risco:** falta o veredito **"não implementado"** — hoje só há
  🔴/🟡/🟢, que classificam *correção*, não *estado*. Sem isso, "não existe" e
  "existe mal feito" ficam indistinguíveis.
- **YAML de exemplo:** exigir **caminho do arquivo** e se o fix vai no repo ou
  em override de `values` do chart. Fix no lugar errado vira manifest morto.
- **Regra nº 1** deveria terminar com: *"se a evidência não permitir a conclusão,
  declare 'não mensurável', não presuma"*. O prompt já pede para não pressupor,
  mas não oferece a saída honrosa quando o dado não existe.

---

## Texto de substituição sugerido (v1.1)

Aplicando o que é consenso (1, 2, 3, 5 e o ajuste de FinOps), os blocos abaixo
substituem os correspondentes na v1.0:

**Regra de Saída nº 1 (nova):**
> **Fatos & Evidências.** Avalie com base em: (a) arquivos do repositório,
> (b) **estado derivado declarativamente** (`helm template` com os `values` do
> repo, `argocd app manifests`, `kubectl get -o yaml`), (c) histórico Git para
> métricas DORA. Toda conclusão deve citar a **origem da evidência** e o
> **arquivo ou comando**. Quando o dado não existir, escreva
> **"não mensurável com a evidência disponível"**. Nunca presuma.

**Escopo (novo, no topo):**
> **Escopo da avaliação:** laboratório individual, cluster de nó único,
> sem SLA formal e sem fatura de nuvem. **Meta:** `<definir>`.
> Lacunas fora do escopo são marcadas como *fora de escopo*, não como falha.

**Eixo 5 — DORA (revisado):**
> Mensure com proxy a partir do Git (commit→merge, commits em `main`/semana,
> reversões). Onde não houver dado, declare não mensurável.

**Eixo 2 — FinOps (revisado):**
> Renomear para **Eficiência de Recursos**: dimensionamento em nó compartilhado,
> ausência de `requests` inflados, réplicas desnecessárias. Não avaliar custo
> de nuvem — não existe.

**Novos eixos (adicionar):**
> **6. Resiliência de Dados:** backup de PVC/etcd, restore testado, RPO/RTO.
> **7. Enforcement vs. Declaração:** existe mecanismo que **impeça** o
> anti-padrão (PSA, Kyverno/Gatekeeper, NetworkPolicy default-deny), ou apenas
> boa intenção nos manifestos?
> **8. Supply Chain:** scan de CVE, SBOM, assinatura, imagem base mínima.
> **9. RBAC nativo:** ServiceAccounts, alcance de `ClusterRoleBinding`,
> `automountServiceAccountToken`.
> **10. Ciclo de vida:** versões pinadas, política de upgrade, drift
> documentação vs. cluster.

**Formato do relatório (acrescentar ao item 4):**
> Cada linha da matriz: `item | estado (implementado / parcial / ausente) |
> risco | evidência + origem | ação | arquivo-alvo`.

---

## Ordem de execução recomendada

1. Aplicar a v1.1 (regra de evidência + escopo + rubrica) — sem isso a auditoria
   mede o repo, não a plataforma.
2. Só então rodar. Rodar a v1.0 produziria um relatório confiante e errado nos
   pilares de Segurança e SRE, que são os que mais importam.
