# Jaeger - Versão

## Importante

O Istio 1.31 instala por padrão o **Jaeger 2.x**, que tem uma UI incompatível
com o `istioctl dashboard jaeger` e com a maioria dos tutoriais.

Para usar a UI clássica, foi feito downgrade para o **Jaeger 1.x** (compatível
com Istio 1.30):

```bash
kubectl delete -f samples/addons/jaeger.yaml
kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.30/samples/addons/jaeger.yaml
