# Istio — Service Mesh

## Estratégia
100% GitOps via ArgoCD. Nenhum `helm install` manual.

## Charts instalados (via ArgoCD Applications)
- istio/base   1.30.4 → CRDs (namespace istio-system)
- istio/istiod 1.30.4 → Control plane
- istio/gateway 1.30.4 → Ingress Gateway (EXTERNAL-IP via MetalLB)

## Ordem de sincronização (sync-waves)
- istio-base:   wave 0
- istiod:       wave 1
- istio-gateway: wave 2

## Modo
Sidecar tradicional (não Ambient).

## Validação
    kubectl -n istio-system get pods
    kubectl -n istio-system get svc
    kubectl -n argocd get applications
