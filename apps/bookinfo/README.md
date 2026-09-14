# Bookinfo — Aplicação de demonstração do Istio

## Estrutura
- 6 microservices: productpage, details, ratings, reviews-v1, reviews-v2, reviews-v3
- Todos com sidecar Istio injetado (2/2 Running)
- Namespace: default (label istio-injection=enabled via GitOps)

## Exposição
- Gateway: bookinfo-gateway (selector: istio=ingressgateway)
- VirtualService: bookinfo (host: bookinfo.local)
- EXTERNAL-IP: 192.168.99.201 (Istio Gateway via MetalLB)

## Acesso
    curl -H "Host: bookinfo.local" http://192.168.99.201/productpage
    # ou no navegador (com /etc/hosts apontando bookinfo.local para 192.168.99.201)

## GitOps
- Application: bookinfo (sync-wave 3, automated, prune, selfHeal)
- path: apps/bookinfo
- destination: default