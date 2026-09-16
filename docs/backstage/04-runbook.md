# Runbook — Backstage no Homelab MK8s

Guia operacional para o Backstage. Cobre tarefas do dia a dia:
verificar saúde, atualizar imagem, reverter, gerenciar credenciais,
habilitar features.

**Filosofia:** GitOps declarativo. Toda mudança permanente vai pelo Git
(`git push` → ArgoCD sync). `kubectl` é usado para **inspeção e debug**,
não para mudanças de estado.

**Exceções:** quando o `Application` do ArgoCD precisa ser atualizado, usa-se
`kubectl apply -f infrastructure/backstage/app.yaml` **uma vez** (porque o
Application vive no cluster, não no Git). Isso está documentado na seção
[Atualizar o Application do ArgoCD](#atualizar-o-application-do-argocd).

---

## 1. Verificar saúde do Backstage

### 1.1 Ver se o pod está rodando

```bash
kubectl -n backstage get pods
```

**Output esperado:**

```
NAME                         READY   STATUS    RESTARTS   AGE
backstage-6c966d9594-ttkcx   1/1     Running   0          5m
backstage-postgresql-0       1/1     Running   0          5m
```

**Interpretação:**

| Campo | O que significa |
|---|---|
| `READY 1/1` | Container pronto e respondendo |
| `STATUS Running` | Pod está ativo |
| `RESTARTS 0` | Sem reinícios inesperados |
| `AGE 5m` | Rodando há 5 minutos (após último deploy) |

**Se estiver diferente:**

- `0/1` → pod não passou no readiness probe
- `Pending` → sem recursos ou PVC não bound
- `ImagePullBackOff` → imagem não encontrada no registry
- `CrashLoopBackOff` → app quebrando na inicialização (ver logs)

### 1.2 Ver a imagem que está rodando

```bash
kubectl -n backstage get pod -o jsonpath='{.items[*].spec.containers[*].image}'; echo
```

**Output esperado:**

```
docker.io/newbare/homelab-backstage:v7 docker.io/bitnamilegacy/postgresql:15.4.0-debian-11-r10
```

**Interpretação:**

- A primeira imagem é o Backstage (tag `v7`)
- A segunda é o PostgreSQL (versão fixa `15.4.0`)

**Se aparecer `latest` ou uma tag antiga:** o `app.yaml` precisa ser
atualizado e sincronizado.

### 1.3 Ver os logs

```bash
kubectl -n backstage logs deployment/backstage --tail=50
```

**Output esperado (trecho):**

```
{"level":"info","message":"Plugin initialization complete, newly initialized: 'catalog', 'notifications', 'scaffolder', 'app'","service":"backstage","type":"initialization"}
{"level":"info","message":"Serving static app content from /app/packages/app/dist","plugin":"app","service":"backstage"}
{"contentLength":15,"date":"...","message":"GET /.backstage/health/v1/readiness HTTP/1.1\" 200 15","method":"GET","status":200,"type":"incomingRequest","url":"/.backstage/health/v1/readiness"}
```

**Interpretação:**

- `Plugin initialization complete` → app subiu OK
- `Serving static app content` → frontend está sendo servido
- `GET /.backstage/health/v1/readiness 200` → health check passando

**Se aparecer `ERROR` ou `Failed`:** ver seção [Troubleshooting](./05-troubleshooting.md).

### 1.4 Ver status do ArgoCD

```bash
argocd app get backstage
```

**Output esperado:**

```
Name:               argocd/backstage
Project:            default
Server:             https://kubernetes.default.svc
Namespace:          backstage
URL:                https://argocd.local/applications/backstage
Source:
- Repo:             https://backstage.github.io/charts
  Target:           2.10.1
Sync Status:        Synced to 2.10.1
Health Status:      Healthy
```

**Interpretação:**

| Campo | Esperado |
|---|---|
| `Sync Status` | `Synced to 2.10.1` |
| `Health Status` | `Healthy` |

**Se `OutOfSync` ou `Degraded`:** ver [Troubleshooting](./05-troubleshooting.md).

### 1.5 Ver se o ConfigMap tem a config certa

```bash
kubectl -n backstage get configmap backstage-app-config -o yaml | grep -A3 "page:home\|packages"
```

**Output esperado:**

```
      packages: all
    app:
      baseUrl: https://backstage.local
      extensions:
      - page:home:
          config:
            defaultConfig:
```

**Se o ConfigMap não tiver `page:home` ou `packages: all`:** o
`app.yaml` não foi propagado. Ver seção
[Atualizar o Application do ArgoCD](#atualizar-o-application-do-argocd).

### 1.6 Ver o certificado TLS

```bash
kubectl -n backstage get certificate
```

**Output esperado:**

```
NAME             READY   SECRET           AGE
backstage-tls    True    backstage-tls    2h
```

**Se `READY False`:** ver logs do cert-manager.

### 1.7 Testar do browser

```bash
# Testa a raiz (deve retornar 200)
curl -k -s -o /dev/null -w "%{http_code}\n" https://backstage.local

# Testa /home (deve retornar 200)
curl -k -s -o /dev/null -w "%{http_code}\n" https://backstage.local/home

# Testa /catalog (deve retornar 200)
curl -k -s -o /dev/null -w "%{http_code}\n" https://backstage.local/catalog
```

**Output esperado:** `200` em todos.

**⚠️ Atenção:** o Backstage é uma **SPA (Single Page Application)**. O
servidor sempre retorna `200` com o HTML, e o **React Router decide o que
renderizar no cliente**. Um `200` do servidor **não significa** que a rota
funciona. Sempre confirme no browser.

---

## 2. Atualizar a imagem do Backstage

Esta é a operação mais comum. Sempre que você muda código (`.ts`, `.tsx`,
`package.json`, etc.), precisa **rebuildar a imagem** e **publicar**.

### 2.1 Fluxo completo (resumo)

```
Código-fonte → yarn build:backend → docker build → docker push
   → editar app.yaml (nova tag) → kubectl apply → argocd sync
   → rollout restart
```

### 2.2 Passo a passo

#### Passo 1: Editar o código

```bash
cd ~/mk8s/homelab-gitops/apps/backstage
# editar o que precisar (ex: plugins.ts, homeModule.tsx)
```

#### Passo 2: Limpar builds antigos

```bash
rm -rf packages/app/dist packages/backend/dist dist-types
```

**Por quê:** garante que o build é do zero, sem cache de versões anteriores.

#### Passo 3: Buildar o bundle

```bash
yarn install
yarn build:backend
```

**Output esperado (final):**

```
Moving backend into dist workspace
Moving app into dist workspace
```

**Tempo:** ~5-10 min.

**Se der erro de TypeScript:** pare e corrija antes de seguir. Não faça
Docker com build quebrado.

#### Passo 4: Buildar a imagem Docker

```bash
docker build -t newbare/homelab-backstage:vN -f packages/backend/Dockerfile .
```

Substitua `vN` pela nova versão (ex: `v8`).

**Output esperado (final):**

```
 => => writing image sha256:...
 => => naming to docker.io/newbare/homelab-backstage:vN
```

**Se der erro `lstat packages: no such file or directory`:** você está na
pasta errada. Confirme com `pwd` (deve estar em `apps/backstage`).

#### Passo 5: Publicar no Docker Hub

```bash
docker push newbare/homelab-backstage:vN
```

**Output esperado (final):**

```
vN: digest: sha256:... size: 3673
```

#### Passo 6: Atualizar o `app.yaml`

```bash
cd ~/mk8s/homelab-gitops
nano infrastructure/backstage/app.yaml
```

Mude a linha:

```yaml
tag: v7        →     tag: vN
```

#### Passo 7: Aplicar o `app.yaml` no cluster

```bash
kubectl apply -f infrastructure/backstage/app.yaml
```

**Output esperado:**

```
application.argoproj.io/backstage configured
```

**Por que este passo:** o `Application` do ArgoCD vive **no cluster**, não
no Git. O `kubectl apply` propaga o novo values do arquivo pro cluster.

#### Passo 8: Sincronizar o ArgoCD

```bash
argocd login argocd.local --insecure --grpc-web
argocd app sync backstage --replace
```

**Output esperado:**

```
Operation:          Sync
Phase:              Succeeded
Message:            successfully synced (all tasks run)
```

**⚠️ Use `--replace`, não `--force`.** O `--force` conflita com
`--server-side` (configurado no `syncOptions`).

#### Passo 9: Reiniciar o pod

```bash
kubectl -n backstage rollout restart deployment backstage
kubectl -n backstage get pods -w
```

**Output esperado:**

```
backstage-6c966d9594-ttkcx   0/1   Pending       0     0s
backstage-6c966d9594-ttkcx   0/1   ContainerCreating   0     0s
backstage-6c966d9594-ttkcx   0/1   Running       0     5s
backstage-6c966d9594-ttkcx   1/1   Running       0     15s
```

**Ctrl+C** quando o pod ficar `1/1 Running`.

#### Passo 10: Verificar

```bash
kubectl -n backstage get pod -o jsonpath='{.items[*].spec.containers[*].image}'; echo
```

**Output esperado:** `newbare/homelab-backstage:vN`.

#### Passo 11: Commit

```bash
git add infrastructure/backstage/app.yaml
git commit -m "chore(backstage): atualiza imagem para vN"
git push
```

### 2.3 Tempo total

| Etapa | Tempo |
|---|---|
| Editar código | variável |
| `yarn build:backend` | ~5-10 min |
| `docker build` | ~30s-1 min |
| `docker push` | ~30s |
| `kubectl apply` | 1s |
| `argocd sync` | ~5s |
| `rollout restart` | ~15-30s |
| **Total** | **~10-15 min** |

---

## 3. Reverter pra versão anterior

Se uma nova versão introduziu bug, reverter é rápido.

### Passo 1: Identificar a versão anterior

```bash
git log --oneline infrastructure/backstage/app.yaml | head -10
```

**Output esperado:**

```
a1b2c3d chore(backstage): atualiza imagem para v7
b2c3d4e chore(backstage): atualiza imagem para v6
c3d4e5f chore(backstage): atualiza imagem para v5
...
```

### Passo 2: Editar o `app.yaml` pra tag anterior

```bash
cd ~/mk8s/homelab-gitops
nano infrastructure/backstage/app.yaml
```

Mude:

```yaml
tag: v7     →     tag: v6
```

### Passo 3: Aplicar + sincronizar + restart

```bash
kubectl apply -f infrastructure/backstage/app.yaml
argocd app sync backstage --replace
kubectl -n backstage rollout restart deployment backstage
kubectl -n backstage get pods -w
```

### Passo 4: Commit

```bash
git add infrastructure/backstage/app.yaml
git commit -m "revert(backstage): volta para v6 (bug em v7)"
git push
```

**Alternativa:** se a mudança foi só no `app.yaml` e já está no Git, você
pode fazer:

```bash
git revert <commit-que-introduziu-o-bug>
git push
kubectl apply -f infrastructure/backstage/app.yaml
argocd app sync backstage --replace
```

---

## 4. Ver logs detalhados

### 4.1 Logs em tempo real

```bash
kubectl -n backstage logs deployment/backstage -f
```

**Ctrl+C** pra sair.

### 4.2 Filtrar por nível

```bash
# Só erros
kubectl -n backstage logs deployment/backstage | grep '"level":"error"'

# Só warnings
kubectl -n backstage logs deployment/backstage | grep '"level":"warn"'

# Só um plugin específico
kubectl -n backstage logs deployment/backstage | grep '"plugin":"catalog"'
```

### 4.3 Logs de um pod específico (se houver múltiplos)

```bash
kubectl -n backstage get pods
kubectl -n backstage logs <nome-do-pod>
```

### 4.4 Logs de um container específico (se o pod tem sidecar)

```bash
kubectl -n backstage logs <nome-do-pod> -c backstage
```

---

## 5. Acessar o pod (debug)

### 5.1 Shell interativo

```bash
kubectl -n backstage exec -it deployment/backstage -- sh
```

**Dentro do pod, você pode verificar:**

```bash
# Ver o app-config carregado
cat /app/app-config-from-configmap.yaml

# Ver variáveis de ambiente
env | grep GITHUB

# Ver se o bundle existe
ls /app/packages/app/dist

# Testar conectividade com PostgreSQL
nc -zv backstage-postgresql 5432
```

**Sair:** `exit`.

### 5.2 Rodar um comando único

```bash
kubectl -n backstage exec deployment/backstage -- cat /app/app-config-from-configmap.yaml
```

---

## 16. Acessar o Backstage de outra máquina

### 16.1 Como funciona

O Backstage roda no cluster MicroK8s (servidor Linux), mas é acessado do
MacBook via `https://backstage.local`. Pra isso funcionar:

1. O **Ingress NGINX** escuta no IP do host MicroK8s (via MetalLB)
2. O **`/etc/hosts`** do MacBook mapeia `backstage.local` pro IP do host
3. O browser acessa `https://backstage.local`, que resolve pro IP, que
   chega no Ingress, que roteia pro Backstage

**Diagrama do fluxo:**

```
MacBook                       Servidor Linux (MicroK8s)
   │                                │
   │ 1. DNS lookup                  │
   │    /etc/hosts → 192.168.99.x   │
   │                                │
   │ 2. HTTPS request               │
   │    https://backstage.local     │
   ├───────────────────────────────►│
   │                                │
   │                          3. MetalLB
   │                          (IP 192.168.99.200-250)
   │                                │
   │                          4. Ingress NGINX
   │                          (porta 443)
   │                                │
   │                          5. Service backstage:80
   │                                │
   │                          6. Pod Backstage
   │                                │
   │ 7. HTML + JS                  │
   │◄───────────────────────────────┤
```

### 16.2 Descobrir o IP do host MicroK8s

**No servidor Linux** (onde o MicroK8s roda):

```bash
ip a
```

**Output esperado (trecho):**

```
2: enp1s0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP group default qlen 1000
    link/ether xx:xx:xx:xx:xx:xx brd ff:ff:ff:ff:ff:ff
    inet 192.168.99.200/24 brd 192.168.99.255 scope global dynamic enp1s0
       valid_lft 86394sec preferred_lft 86394sec
```

**O IP é o que está em `inet`** (no exemplo: `192.168.99.200`).

**⚠️ Importante:** se o IP for atribuído por **DHCP**, ele pode mudar. Ver
seção [16.5 Fixar o IP do host](#165-fixar-o-ip-do-host-recomendado).

**Alternativa (mostra só o IP):**

```bash
hostname -I | awk '{print $1}'
```

**Output esperado:**

```
192.168.99.200
```

**⚠️ Nota:** o IP do host MicroK8s (`192.168.99.200`) **coincide** com o
início do range do MetalLB (`192.168.99.200-192.168.99.250`). Isso é
intencional: o MetalLB usa IPs da mesma rede, mas **fora do range DHCP**
do modem (que vai até `192.168.99.199`).

### 16.3 Configurar `/etc/hosts` no MacBook

**No MacBook:**

```bash
sudo nano /etc/hosts
```

**Adicione a linha:**

```
192.168.99.200   backstage.local
```

**Salve** (`Ctrl+O`, Enter, `Ctrl+X`).

**Verifique:**

```bash
cat /etc/hosts | grep backstage
```

**Output esperado:**

```
192.168.99.200   backstage.local
```

**Teste a resolução:**

```bash
ping -c 2 backstage.local
```

**Output esperado:**

```
PING backstage.local (192.168.99.200): 56 data bytes
64 bytes from 192.168.99.200: icmp_seq=0 ttl=64 time=2.345 ms
64 bytes from 192.168.99.200: icmp_seq=1 ttl=64 time=2.123 ms
```

### 16.4 Testar o acesso

**No MacBook:**

```bash
curl -k -s -o /dev/null -w "%{http_code}\n" https://backstage.local
```

**Output esperado:** `200`.

**No browser:** abre `https://backstage.local`. O certificado é
**self-signed**, então o browser vai mostrar aviso. Clique em
**"Avançado" → "Continuar mesmo assim"**.

**No Chrome/Safari (macOS), pra evitar o aviso toda vez:**

1. Abre `https://backstage.local` no Chrome
2. Clica em **"Not secure"** na barra de endereço
3. **"Certificate is not valid"** → **"Continue to backstage.local (unsafe)"**
4. Ou: importa o certificado no Keychain (ver seção 16.6)

### 16.5 Fixar o IP do host (recomendado)

O IP do host MicroK8s foi atribuído por **DHCP** (`192.168.99.200`). Se
o modem reiniciar, o IP pode mudar — e aí o `/etc/hosts` do MacBook fica
desatualizado.

**Solução 1 — Reserva DHCP no modem** (recomendado)

1. Acessa o painel do modem (geralmente `http://192.168.99.1`)
2. Procura por **"DHCP Reservation"** ou **"Static Lease"**
3. Adiciona o MAC address do servidor Linux + IP `192.168.99.200`
4. Salva

**Vantagens:** zero configuração no servidor, o modem sempre dá o mesmo IP.

**Solução 2 — IP estático no servidor Linux**

Edita o `/etc/netplan/00-installer-config.yaml`:

```yaml
network:
  ethernets:
    enp1s0:
      dhcp4: no
      addresses:
        - 192.168.99.200/24
      routes:
        - to: default
          via: 192.168.99.1
      nameservers:
        addresses: [8.8.8.8, 1.1.1.1]
  version: 2
```

Aplica:

```bash
sudo netplan apply
```

**Vantagens:** controle total.
**Desvantagens:** se o modem mudar de faixa, o servidor perde conectividade.

**⚠️ Escolha uma das duas.** A **Solução 1** é mais simples e recomendada
pra homelab.

### 16.6 Importar o certificado no Keychain (opcional)

Pra evitar o aviso de "não seguro" no browser:

**No MacBook:**

```bash
# Exporta o certificado
kubectl -n backstage get secret backstage-tls -o jsonpath='{.data.tls\.crt}' | base64 -d > /tmp/backstage-tls.crt

# Abre no Keychain
open /tmp/backstage-tls.crt
```

**No Keychain Access:**

1. Procura `backstage.local`
2. Duplo clique → expande **"Trust"**
3. Muda **"When using this certificate"** pra **"Always Trust"**
4. Fecha (vai pedir senha)

**Verifica:**

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://backstage.local
```

Sem `-k` (não precisa mais).

### 16.7 Como funciona o MetalLB

O MicroK8s **não tem LoadBalancer nativo**. Por padrão, Services do tipo
`LoadBalancer` ficam em `<pending>` (sem IP externo).

O **MetalLB** resolve isso: ele atribui IPs da rede local aos Services
`LoadBalancer`, como se fossem IPs "externos" (mas na verdade são IPs da
LAN).

**Configuração do MetalLB:**

Arquivo: `infrastructure/metallb/ipaddresspool.yaml`

```yaml
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: lab-pool
  namespace: metallb-system
spec:
  addresses:
    - 192.168.99.200-192.168.99.250
```

**Range:** `192.168.99.200` a `192.168.99.250` = **51 IPs**.

**Por que esse range:**

- O modem DHCP serve `192.168.99.1` a `192.168.99.199`
- O MetalLB usa `192.168.99.200` a `192.168.99.250`
- **Não há sobreposição** — evita conflito de IP

**Verificar o range atual:**

```bash
kubectl get ipaddresspool -n metallb-system lab-pool -o yaml
```

**Output esperado:**

```yaml
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: lab-pool
  namespace: metallb-system
spec:
  addresses:
  - 192.168.99.200-192.168.99.250
```

**Ver os IPs atribuídos:**

```bash
kubectl get svc -A | grep LoadBalancer
```

**Output esperado (trecho):**

```
ingress-nginx   ingress-nginx-controller   LoadBalancer   10.152.183.x   192.168.99.200   80:31xxx/TCP,443:32xxx/TCP
```

**O IP `192.168.99.200`** é o do Ingress NGINX, atribuído pelo MetalLB.
É esse IP que vai no `/etc/hosts` do MacBook.

---

## 📄 Bloco 2 — Adicionar no `03-decisoes.md` (ADR-011)

Cola **antes** do `## 📌 Resumo das decisões`:

````markdown
## ADR-011: MetalLB como LoadBalancer interno

**Status:** Aceita
**Data:** 2026-09-13

### Contexto

O MicroK8s **não tem LoadBalancer nativo**. Por padrão, Services do tipo
`LoadBalancer` ficam com IP `<pending>` — sem acesso externo.

No homelab, o Ingress NGINX precisa de um IP "externo" pra ser acessível
do MacBook.

### Decisão

Usar **MetalLB** com o seguinte pool de IPs:

```yaml
# infrastructure/metallb/ipaddresspool.yaml
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: lab-pool
  namespace: metallb-system
spec:
  addresses:
    - 192.168.99.200-192.168.99.250
```

**Range:** `192.168.99.200` a `192.168.99.250` = **51 IPs**.

**Por que esse range específico:**

- O modem DHCP serve `192.168.99.1` a `192.168.99.199`
- O MetalLB usa `192.168.99.200` a `192.168.99.250`
- **Sem sobreposição** — evita conflito de IP

### Consequências

**Positivas:**

- **Ingress acessível** de qualquer máquina da LAN
- **IPs estáveis** dentro do cluster (o MetalLB gerencia)
- **Sem cloud** — tudo local
- **Fácil de expandir:** adicionar mais IPs é só editar o range
- **Padrão de mercado:** MetalLB é o LoadBalancer mais usado em clusters
  bare-metal

**Negativas:**

- **Acoplamento com a rede local:** se a rede mudar (ex: mudar de
  `192.168.99.0/24` pra outra faixa), o MetalLB precisa ser reconfigurado
- **DHCP do host pode conflitar:** o IP do host MicroK8s é atribuído por
  DHCP (não fixo). Se o modem mudar, o `/etc/hosts` do MacBook precisa ser
  atualizado
- **Range fixo:** 51 IPs é suficiente pro homelab, mas limitado se o
  cluster crescer muito

### Alternativas consideradas

1. **NodePort** — descartada: portas altas (30000-32767), feio
2. **`kubectl port-forward`** — descartada: manual, não persiste
3. **Ingress sem LoadBalancer** — descartada: Ingress precisa de IP externo
4. **Cloud LoadBalancer** — descartada: não há cloud no homelab
5. **MetalLB com range maior** — descartada: 51 IPs é suficiente
6. **Traefik como LoadBalancer** — descartada: MetalLB é mais simples

### Observação futura

- **Fixar o IP do host MicroK8s** (reserva DHCP no modem ou IP estático no
  servidor Linux) — ver seção 16.5 do [runbook](./04-runbook.md)
- **Considerar IPv6** se a rede suportar
- **Automatizar o `/etc/hosts`** (via Ansible ou script)

---

## 17. Customizar o tema do Backstage UI (BUI)

O Backstage 1.54 tem **2 sistemas de UI** (MUI + BUI). Esta seção cobre o
**BUI** (componentes `bui-*`). Para MUI, ver `themeModule.tsx`.

### 17.1 Identificar se o componente é BUI

**No browser (F12 → Elements):** se a classe começa com `bui-`, é BUI.

**Exemplos:**

- `bui-ButtonLink` (botões primários)
- `bui-HeaderTitle` (títulos de header)
- `bui-Card` (cards)

### 17.2 Onde customizar

**Arquivo:** `apps/backstage/packages/app/src/resilience-theme.css`

**Estrutura:**

```css
/* 1. Variáveis (tema light) */
[data-theme-mode='light'] {
  --bui-bg-app: #f7fafc;
  --bui-bg-solid: #FF9900;          /* Botões primários */
  --bui-fg-solid: #ffffff;
  --bui-fg-primary: #1a202c;
  --bui-fg-secondary: #4a5568;
  --bui-border-1: #e2e8f0;
  --bui-border-2: #cbd5e0;
}

/* 2. Ataque direto ao componente (garantia extra) */
.bui-ButtonLink[data-variant='primary'] {
  background-color: #FF9900 !important;
  color: #ffffff !important;
}
```

### 17.3 Variáveis mais usadas

| Variável | Uso |
|---|---|
| `--bui-bg-app` | Fundo geral do app |
| `--bui-bg-solid` | **Botões primários** |
| `--bui-fg-solid` | Texto sobre fundo sólido |
| `--bui-fg-primary` | Texto principal |
| `--bui-fg-secondary` | Texto secundário |
| `--bui-border-1` | Bordas sutis |
| `--bui-border-2` | Bordas principais |

**Lista completa:** https://backstage.io/docs/conf/user-interface/

### 17.4 Como testar

**1. Editar o CSS.**

**2. Rebuild:**

```bash
cd ~/mk8s/homelab-gitops/apps/backstage
rm -rf packages/app/dist packages/backend/dist
yarn build:backend
docker build -t newbare/homelab-backstage:vN -f packages/backend/Dockerfile .
docker push newbare/homelab-backstage:vN
```

**3. Atualizar `app.yaml`** (`tag: vN`).

**4. Aplicar + sync + restart:**

```bash
cd ~/mk8s/homelab-gitops
kubectl apply -f infrastructure/backstage/app.yaml
argocd app sync backstage --replace
kubectl -n backstage rollout restart deployment backstage
```

**5. Hard refresh** no browser (`Cmd+Shift+R`).

**6. Verificar no DevTools:**

```javascript
console.log('--bui-bg-solid:', getComputedStyle(document.documentElement).getPropertyValue('--bui-bg-solid'));
// Esperado: #FF9900
```

### 17.5 Troubleshooting

**Se o BUI não muda:**

1. **Confirma que está dentro de `[data-theme-mode='light']`** (não `:root`)
2. **Confirma que a var correta** está sendo usada (ex: `--bui-bg-solid` pra botões)
3. **Usa `!important`** no ataque direto
4. **Verifica se o cache do browser** não está atrapalhando (hard refresh)

### 17.6 Ver também

- [ADR-012](./03-decisoes.md#adr-012-backstage-tem-2-sistemas-de-ui-mui--bui)
- [Doc oficial](https://backstage.io/docs/conf/user-interface/)
- [Fase 8 — Jornada](./07-fase-8-polish.md)