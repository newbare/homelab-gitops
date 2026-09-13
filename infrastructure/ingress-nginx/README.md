# NGINX Ingress Controller

## Instalação

- Chart: ingress-nginx/ingress-nginx v4.15.1 (app v1.15.1)
- Namespace: ingress-nginx
- Instalado via Helm (não via add-on ingress do MicroK8s)

## Comando de instalação

    helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
    helm repo update
    helm install ingress-nginx ingress-nginx/ingress-nginx \
      --namespace ingress-nginx \
      --create-namespace \
      --version 4.15.1 \
      --set controller.service.type=LoadBalancer

## Integração com MetalLB

O --set controller.service.type=LoadBalancer faz o Service do controller
receber um EXTERNAL-IP do MetalLB (faixa 192.168.99.200-250).
Atualmente: 192.168.99.200.

## Validação

    kubectl -n ingress-nginx get pods
    kubectl -n ingress-nginx get svc
    kubectl get ingressclass

## Teste

    kubectl create deployment web-test --image=nginx:alpine
    kubectl expose deployment web-test --port=80
    # aplicar Ingress com host web-test.local
    curl --resolve web-test.local:80:192.168.99.200 http://web-test.local
