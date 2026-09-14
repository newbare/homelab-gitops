# Backstage — Developer Portal

## Instalação
- Chart: backstage/backstage v2.10.0
- Namespace: backstage
- Instalado via ArgoCD (Application `backstage`, sync-wave 7)

## Dependências
- PostgreSQL (criado pelo próprio chart como dependência)
- Ingress NGINX (Fase 3)

## Configuração
- appConfig.app.title: "Homelab Developer Portal"
- appConfig.app.baseUrl: http://backstage.local
- appConfig.backend.baseUrl: http://backstage.local
- appConfig.backend.listen.port: 7007

## Acesso
- URL: http://backstage.local
- Backend: porta 7007
- PostgreSQL: porta 5432 (ClusterIP interno)

## Ingress
- infrastructure/backstage/ingress.yaml
- backend-protocol: HTTP
- proxy-body-size: 0 (sem limite, para o scaffolder)
- proxy-read/send-timeout: 600s

## Lições aprendidas

### appConfig deve estar no nível raiz
O chart `backstage/backstage` espera `appConfig` no nível raiz do `values`,
NÃO aninhado sob `backstage:`. A estrutura correta é:

    appConfig:
      app:
        baseUrl: http://backstage.local
      backend:
        baseUrl: http://backstage.local

### Erro "Missing required config value at 'app.baseUrl'"
Sintoma: pod em CrashLoopBackOff com `Missing required config value at 'app.baseUrl'`.
Causa: `appConfig` aninhado incorretamente sob `backstage:`.
Solução: mover `appConfig` para o nível raiz do values.

### Warnings cosméticos
- `backend.baseUrl is set to a localhost URL` — o chart injeta localhost
  por padrão em algum lugar. O Backstage funciona mesmo assim.
- `file /examples/entities.yaml does not exist` — o catálogo de exemplo
  não está na imagem.
- `Failed to initialize kubernetes backend` — falta config do plugin K8s.