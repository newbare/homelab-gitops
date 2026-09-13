# ArgoCD — GitOps

## Instalação
- Chart: argo/argo-cd v10.9.0 (app v3.5.2)
- Namespace: argocd
- Instalado via Helm
- server.insecure=true (TLS terminado no Ingress NGINX)

## Configurações
- URL externa: https://argocd.local
- Ingress: backend-protocol HTTP, porta 80
- Acesso: admin / (senha definida)

## Application gerenciada
- `metallb` → infrastructure/metallb
  - sync-policy: automated
  - auto-prune: true
  - self-heal: true
  - revision: main

## Validação
    argocd app list
    argocd app get metallb
    curl -k https://argocd.local

## Comandos úteis
    kubectl -n argocd port-forward svc/argocd-server 8080:80
    argocd login argocd.local --insecure --grpc-web