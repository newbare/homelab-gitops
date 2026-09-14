# Observabilidade

## Componentes instalados (todos via GitOps/ArgoCD)

| Componente | Chart | Versão | Namespace |
|------------|-------|--------|-----------|
| kube-prometheus-stack | prometheus-community | 91.2.1 | monitoring |
| metrics-server | metrics-server | 3.14.0 | kube-system |
| cert-manager | jetstack | v1.21.2 | cert-manager |
| kiali-operator | kiali | 2.31.0 | kiali-operator |
| jaeger-operator | jaegertracing | 2.57.0 | observability |

## CRs gerenciados via ArgoCD

| CR | Application | sync-wave |
|----|-------------|-----------|
| Kiali | kiali | 6 |
| Jaeger | jaeger | 6 |

## Ingresses

| Host | Backend | Namespace |
|------|---------|-----------|
| kiali.local | kiali:20001 | kiali-operator |
| jaeger.local | jaeger-query:16686 | observability |
| grafana.local | kube-prometheus-stack-grafana:80 | monitoring |

## Decisão: Jaeger 1.x via operator

- **Motivo:** integração nativa com Kiali 2.31, UI clássica, Istio 1.30 envia traces nativamente.
- **Alternativa:** Jaeger 2.x (chart direto) — UI nova, baseada em OpenTelemetry, suporte parcial no Kiali.

## Lições aprendidas

### 1. jaeger-operator requer cert-manager
O chart 2.57.0 cria `Certificate` e `Issuer` do cert-manager para o webhook.
Sem cert-manager, o sync falha com "cert-manager.io/Certificate not found".

### 2. jaeger-operator requer RBAC extra para IngressClass
Erro: `cannot list resource "ingressclasses"`.
Solução: ClusterRole + ClusterRoleBinding adicionais.

### 3. Kiali CR: campos obsoletos
- `spec.installation_namespace` → removido (namespace vem do metadata)
- `spec.deployment.ingress_enabled` → removido (usar Ingress separado)

### 4. Jaeger CR OutOfSync eterno
O operator modifica o CR em runtime. Solução: `ignoreDifferences` na Application.