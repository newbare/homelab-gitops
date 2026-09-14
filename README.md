
| Serviço | URL | Credenciais | Backend |
|---------|-----|-------------|---------|
| ArgoCD | https://argocd.local | `admin` / (definida) | NGINX Ingress → argocd-server:80 |
| Kiali | http://kiali.local/kiali/ | anonymous | NGINX Ingress → kiali:20001 |
| Jaeger | http://jaeger.local | — | NGINX Ingress → jaeger-query:16686 |
| Grafana | http://grafana.local | `admin` / `admin` | NGINX Ingress → kube-prometheus-stack-grafana:80 |
| Bookinfo | http://bookinfo.local/productpage | — | Istio Gateway → productpage:9080 |

> ⚠️ O ArgoCD usa HTTPS (certificado self-signed). O navegador vai avisar.

---

## 🔀 sync-waves (ordem de sincronização)

| Wave | Application | O que faz |
|------|-------------|-----------|
| -2 | metrics-server | Métricas para HPA |
| -1 | namespaces | Labels (istio-injection) |
| 0 | istio-base | CRDs do Istio |
| 1 | istiod | Control plane |
| 2 | istio-gateway | Ingress Gateway |
| 3 | bookinfo | Aplicação de demonstração |
| 4 | kube-prometheus-stack, cert-manager | Métricas + certificados |
| 5 | kiali-operator, jaeger-operator | Operadores |
| 6 | kiali, jaeger | CRs (instâncias) |

---

## 🎯 Fases de Implementação

| Fase | O que foi feito | Documentação |
|------|-----------------|--------------|
| 1 | MicroK8s 1.35.6 + dns + hostpath-storage + rbac | (este README) |
| 2 | MetalLB 0.16.1 via Helm + IPAddressPool + L2Advertisement | `infrastructure/metallb/README.md` |
| 3 | NGINX Ingress Controller 4.15.1 via Helm | `infrastructure/ingress-nginx/README.md` |
| 4 | ArgoCD v3.5.2 via Helm + Ingress + Application metallb | `infrastructure/argocd/README.md` |
| 5 | Istio 1.30.4 (base + istiod + gateway) + Bookinfo + sidecar injection | `infrastructure/istio/README.md` |
| 6 | Observabilidade: Prometheus, Grafana, Kiali, Jaeger, metrics-server, cert-manager | `infrastructure/observability/README.md` |

---

## 🧠 Lições Aprendidas

### 1. MetalLB + ARP (Fase 2)

**Sintoma:** serviços `LoadBalancer` recebiam EXTERNAL-IP, mas o tráfego não
chegava, ou outros dispositivos da rede perdiam conectividade.

**Causa raiz:** o MetalLB em modo L2 responde ARP pelos IPs do pool em **todas**
as interfaces do host. O servidor tem múltiplas interfaces:
- `enp3s0` (LAN, 192.168.99.5)
- `vxlan.calico` (10.1.56.0/32)
- `docker0` / `veth*` (se Docker/Podman estiver ativo)

Respostas ARP na interface errada causam conflito de IP na rede.

**Solução:** especificar `interfaces: [enp3s0]` no `L2Advertisement`.

**Diagnóstico:** `ip -4 addr show | grep -E "^[0-9]+:|inet "`

### 2. Istio gateway chart não aceita `image` (Fase 5)

**Sintoma:** `helm template` falha com `additional properties 'image' not allowed`.

**Causa raiz:** o chart `istio/gateway` 1.30.x tem `additionalProperties: false`
no schema. A chave `image` não existe no `values.yaml`.

**Solução:** não especificar `image`. A imagem do `istio-proxy` é injetada pelo
webhook do `istiod` em runtime.

### 3. Pod do gateway com imagem "auto" (Fase 5)

**Sintoma:** pod `istio-ingress` preso em `ImagePullBackOff` puxando imagem `"auto"`.

**Causa raiz:** o webhook do `istiod` não conseguiu injetar a imagem na criação
do pod (istiod ainda não estava pronto).

**Solução:** `kubectl -n istio-system delete pod -l app=istio-ingress`.
O pod recriado recebe a imagem correta.

### 4. Webhooks do Istio OutOfSync eterno (Fase 5)

**Sintoma:** Applications `istio-base`, `istiod`, `istio-gateway` sempre `OutOfSync`.

**Causa raiz:** o `istiod` modifica o `caBundle` e o `failurePolicy` dos webhooks
em runtime.

**Solução:** `ignoreDifferences` nas Applications para
`ValidatingWebhookConfiguration` e `MutatingWebhookConfiguration`.

### 5. HPA Degraded sem metrics-server (Fase 6)

**Sintoma:** `istiod` e `istio-gateway` apareciam como `Degraded` no ArgoCD.

**Causa raiz:** o HPA não conseguia ler métricas porque o `metrics-server` não
estava instalado. A API `pods.metrics.k8s.io` não existia.

**Solução:** instalar o `metrics-server` via ArgoCD com
`--kubelet-insecure-tls` (MicroK8s usa certificados self-signed nos kubelets).

### 6. jaeger-operator requer cert-manager (Fase 6)

**Sintoma:** `jaeger-operator` falhava com
`cert-manager.io/Certificate not found`.

**Causa raiz:** o chart 2.57.0 cria um `Certificate` e um `Issuer` do cert-manager
para o webhook. Sem cert-manager instalado, os CRDs não existem.

**Solução:** instalar o `cert-manager` via ArgoCD **antes** do `jaeger-operator`.

### 7. jaeger-operator requer RBAC extra (Fase 6)

**Sintoma:** pods do Jaeger não subiam. Log do operator:
`cannot list resource "ingressclasses" in API group "networking.k8s.io"`.

**Causa raiz:** o ClusterRole padrão do chart não inclui permissão para listar
`IngressClass` (escopo de cluster).

**Solução:** criar `ClusterRole` + `ClusterRoleBinding` adicionais
(`infrastructure/observability/jaeger-operator-rbac.yaml`).

### 8. Kiali CR: campos obsoletos (Fase 6)

**Sintoma:** `strict decoding error: unknown field "spec.deployment.ingress_enabled",
unknown field "spec.installation_namespace"`.

**Causa raiz:** esses campos foram removidos no Kiali 2.31.0.

**Solução:**
- `installation_namespace` → o namespace vem do `metadata.namespace`.
- `deployment.ingress_enabled` → usar Ingress separado (NGINX).

### 9. Jaeger CR OutOfSync eterno (Fase 6)

**Sintoma:** Application `jaeger` sempre `OutOfSync`.

**Causa raiz:** o `jaeger-operator` modifica o CR em runtime (adiciona defaults
no `/spec` e `status`).

**Solução:** `ignoreDifferences` na Application para `/spec` e `/status`, com
`RespectIgnoreDifferences=true` no `syncPolicy`.

### 10. GitOps de verdade

**Padrão:** tudo é commitado no Git. O cluster converge para o estado declarado.
O `kubectl apply` direto vira exceção (só para as Applications iniciais).

**Exemplo:** o teste de self-heal do MetalLB — delete o `IPAddressPool` e o
ArgoCD recria automaticamente em segundos.

---

## 🛠️ Comandos Úteis

```bash
# Estado geral
kubectl -n argocd get applications
kubectl get pods -A
kubectl top nodes
kubectl top pods -A

# ArgoCD CLI
argocd login argocd.local --insecure --grpc-web
argocd app list
argocd app get <app>
argocd app sync <app> --force

# Forçar rollout do Istio gateway
kubectl -n istio-system delete pod -l app=istio-ingress

# Gerar tráfego no Bookinfo
for i in {1..20}; do
  curl -s -H "Host: bookinfo.local" http://192.168.99.201/productpage > /dev/null
  sleep 1
done