# NGINX Ingress Controller

## Instalação
- Chart: ingress-nginx/ingress-nginx v4.15.1 (app v1.15.1)
- Namespace: ingress-nginx
- Instalado via Helm (Fase 3)

## Configuração adicional

### Snippets habilitados

Para permitir o uso de `configuration-snippet` (necessário para o Backstage),
foi necessário editar o ConfigMap `ingress-nginx-controller`.

O manifesto `configmap-patch.yaml` contém as chaves necessárias:

    data:
      allow-snippet-annotations: "true"
      annotations-risk-level: "Critical"

Aplicar com:

    kubectl apply -f infrastructure/ingress-nginx/configmap-patch.yaml

### Por que?

O NGINX Ingress Controller bloqueia snippets por padrão (a partir da v1.9.3)
por questões de segurança. A anotação `configuration-snippet` é classificada
como risco Critical, então é preciso elevar o nível de risco permitido.

### Aviso

Habilitar snippets permite injeção de configuração arbitrária no NGINX.
Para um laboratório é aceitável; em produção, evite e prefira rebuildar a
imagem com a URL correta.

## Integração com MetalLB
O Service do controller recebe EXTERNAL-IP do MetalLB (faixa 192.168.99.200-250).
Atualmente: 192.168.99.200.
