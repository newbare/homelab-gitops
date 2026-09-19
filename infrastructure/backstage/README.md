# Backstage — infraestrutura

Manifestos que colocam o Backstage no cluster. Documentação da aplicação em
[`../../docs/backstage/`](../../docs/backstage/).

---

## 📁 O que tem aqui

| Arquivo | O que é | Aplicado por |
|---|---|---|
| `app.yaml` | **Application principal** (chart `backstage` 2.10.1) | `kubectl apply` |
| `certificate.yaml` + `certificate-app.yaml` | `Certificate` TLS de `backstage.local` | Application `backstage-certificate` |
| `ingress.yaml` + `ingress-app.yaml` | Ingress próprio | Application `backstage-ingress` |
| `scripts/` | gerador do `ConfigMap` de usuários do catálogo | **manual** — ver [`scripts/README.md`](scripts/README.md) |

> ⚠️ **Dois recursos que o Pod usa NÃO têm manifesto neste diretório.** Não é
> esquecimento:
>
> | Recurso | De onde vem | Por quê assim |
> |---|---|---|
> | `ConfigMap homelab-ca` | **trust-manager** (`infrastructure/trust-manager/`) | é valor gerado pelo cluster; versioná-lo quebraria num bootstrap do zero |
> | `ConfigMap backstage-catalog-users` | **provisionado** por `scripts/generate-catalog.py` | são dados pessoais (nome e e-mail); o repo é público |
>
> O primeiro é reconciliado por um controller — `git push` basta. O segundo
> depende de um comando. A justificativa completa do segundo, e o trade-off, em
> [`scripts/README.md`](scripts/README.md).

---

## ⚠️ As três pegadinhas deste diretório

### 1. `git push` NÃO basta para o `app.yaml`

A Application principal é **baseada em chart** (`source.chart`). O ArgoCD **não**
lê esse arquivo do Git — ele lê o **objeto Application que existe no cluster**.

Mudou o `app.yaml` no repo? Além do commit:

```bash
kubectl apply -f infrastructure/backstage/app.yaml
```

> Consequência útil: `argocd app get backstage` mostrar `Synced` significa
> *"igual ao que o ArgoCD observou"* — **não** "igual ao GitHub agora".

### 2. Tudo dentro de `values: |` é uma string

O `appConfig` e os values do Helm estão embutidos como bloco literal. Um erro de
indentação lá dentro **não** é pego por `kubectl apply --dry-run`. Valide à parte:

```bash
ruby -ryaml -e '
v = YAML.load(YAML.load_file("infrastructure/backstage/app.yaml")["spec"]["source"]["helm"]["values"])
puts v["backstage"]["image"]["tag"]
'
```

### 3. O config do repo **não** é o config que roda

O chart sobrescreve o `CMD` do Dockerfile:

```
args: ["--config","/app/app-config-from-configmap.yaml"]
```

Ou seja: `app-config.yaml` e `app-config.production.yaml` **da imagem nunca são
lidos**. O único config ativo é o `ConfigMap` gerado do `appConfig` do `app.yaml`.

**Confirme o que está valendo de verdade:**

```bash
kubectl -n backstage get configmap backstage-app-config \
  -o jsonpath='{.data.app-config\.yaml}'
```

Foi exatamente esse detalhe que fez a Fase 11 levar mais tempo: durante um bom
tempo editamos um `catalog.locations` que nunca chegava ao processo.

---

## 🔌 O que o Pod precisa

| Recurso | Tipo | Para quê |
|---|---|---|
| `backstage-github-token` | Secret | integração GitHub |
| `backstage-postgresql` | Secret | senha do banco |
| `backstage-keycloak` | Secret | `KEYCLOAK_CLIENT_SECRET` (OIDC) |
| `backstage-auth-session` | Secret | `AUTH_SESSION_SECRET` (`auth.session.secret`) |
| `homelab-ca` | ConfigMap | a CA interna, via `NODE_EXTRA_CA_CERTS`. Criado pelo **trust-manager** em todos os namespaces |
| `backstage-catalog-users` | ConfigMap | os `User`/`Group` do catálogo. **Provisionado**, não versionado |

> ⚠️ **Um nome errado aqui não degrada — derruba.** Secret ausente em
> `extraEnvVarsSecrets` → `CreateContainerConfigError`. ConfigMap ausente em
> `extraVolumes` → `ContainerCreating` eterno. **Confira antes de aplicar.**

---

## 🌐 Rede

O Pod precisa alcançar `https://keycloak.local`. O discovery OIDC devolve URLs
**públicas**, e o provider do Backstage aceita **só `metadataUrl`** — não há como
apontar endpoints internos.

Como o Pod não vê o `/etc/hosts` do Mac, o mapeamento é explícito:

```yaml
hostAliases:
  - ip: 10.152.183.36        # ClusterIP do svc ingress-nginx-controller
    hostnames:
      - keycloak.local
```

Confirme o ClusterIP atual antes de mudar:

```bash
kubectl -n ingress-nginx get svc ingress-nginx-controller -o jsonpath='{.spec.clusterIP}{"\n"}'
```

E o TLS é resolvido com a CA interna montada + `NODE_EXTRA_CA_CERTS`. O racional
completo está em
[`../../docs/certificados/01-trust-anchor-interno.md`](../../docs/certificados/01-trust-anchor-interno.md).

---

## 🚀 Atualizar a imagem

O `Dockerfile` é **single-stage** e **não compila**: exige os artefatos prontos.

```bash
cd apps/backstage

yarn tsc                    # validação rápida de tipos
yarn build:backend          # gera skeleton.tar.gz + bundle.tar.gz

cd ../..

DOCKER_BUILDKIT=1 docker build \
  -t newbare/homelab-backstage:vNN \
  -f packages/backend/Dockerfile .
#                       ^ contexto = apps/backstage (raiz do monorepo Yarn)

docker push newbare/homelab-backstage:vNN
```

Depois: `tag: vNN` no `app.yaml` + `kubectl apply`.

**Antes de buildar, confirme que a sua mudança entra no bundle** — especialmente
mudanças de **frontend**:

```bash
grep -rl 'Entrar com Keycloak' apps/backstage/packages/app/dist/static/
```

> "O build não deu erro" **não** prova que o seu código entrou: ele prova que o
> que estava lá compilou. Uma mudança de frontend removida por tree-shaking passa
> pelo build sem reclamar.

---

## 🔍 Diagnóstico

```bash
# a Application está sincronizada?
kubectl -n argocd get application backstage \
  -o jsonpath='sync={.status.sync.status} health={.status.health.status}{"\n"}'

# o Pod está pronto e com quantos restarts?
kubectl -n backstage get pods

# a config ativa é a esperada?
kubectl -n backstage get configmap backstage-app-config \
  -o jsonpath='{.data.app-config\.yaml}' | grep -A 3 'oidc:'

# o provider OIDC foi registrado?
kubectl -n backstage logs deploy/backstage | grep 'Configuring auth provider'

# o Pod fala com o Keycloak?
kubectl -n backstage exec deploy/backstage -- node -e \
  "fetch('https://keycloak.local/realms/resilience/.well-known/openid-configuration').then(r => console.log('HTTP', r.status)).catch(e => console.log('FALHOU:', e.cause?.code ?? e.message))"
```

### Erros conhecidos

| Sintoma | Causa provável |
|---|---|
| `Login failed, popup was closed` | o popup do OAuth recebeu erro e fechou. Veja o que apareceu **nele** |
| `OPError: expected 200 OK, got: 503` | o Keycloak está reiniciando. Ver `infrastructure/keycloak/README.md` |
| Provider OIDC não aparece nos logs | `YAML` inválido dentro de `values: \|`, ou `prompt`/`metadataUrl` ausente |
| `Sign-in failed, user not found` | não existe `User` no catálogo com aquele nome de entidade |
| Entidades não entram no catálogo | **leia os logs do catálogo** — ele valida e reporta; não aparece em nenhum `get` |
| `CreateContainerConfigError` | um `Secret` referenciado não existe |
| Pod preso em `ContainerCreating` | um `ConfigMap` referenciado não existe |
