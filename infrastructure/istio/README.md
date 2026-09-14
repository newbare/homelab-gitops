# Istio — Service Mesh

## Estratégia
100% GitOps via ArgoCD. Nenhum helm install manual.

## Charts (via ArgoCD Applications)
- istio/base    1.30.4 → CRDs (namespace istio-system)
- istio/istiod  1.30.4 → Control plane
- istio/gateway 1.30.4 → Ingress Gateway (EXTERNAL-IP 192.168.99.201 via MetalLB)

## sync-waves
- istio-base:    wave 0
- istiod:        wave 1
- istio-gateway: wave 2

## Lições aprendidas

### 1. Chart gateway 1.30.x não aceita `image` no values
O schema do chart (`additionalProperties: false`) rejeita a chave `image`.
A imagem do `istio-proxy` é injetada pelo webhook do `istiod` em runtime.

### 2. Pod do gateway com imagem "auto" (ErrImagePull)
Sintoma: pod `istio-ingress` preso em `ImagePullBackOff` puxando imagem "auto".
Causa: webhook do istiod não conseguiu injetar a imagem na criação do pod
(istiod ainda não estava pronto).
Solução: `kubectl -n istio-system delete pod -l app=istio-ingress`
O pod recriado recebe a imagem correta do webhook.

### 3. Webhooks OutOfSync eterno
O istiod modifica o caBundle/failurePolicy dos webhooks em runtime.
Solução: ignoreDifferences nas Applications (base, istiod, gateway).