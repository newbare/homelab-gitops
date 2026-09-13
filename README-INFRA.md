# README-INFRA.md — Homelab Kubernetes

Documentação do laboratório de estudos de **Kubernetes, GitOps, DevOps e DevSecOps**.

Este documento registra **o roteiro seguido**, **cada decisão técnica** e **o estado atual** do lab.

---

## 🖥️ Hardware do servidor

| Componente | Especificação |
| :--- | :--- |
| **Processador** | AMD A10-7860K (3.60 GHz) |
| **Memória RAM** | 16 GB DDR3 1600 MHz |
| **SSD** | 120 GB (sistema operacional) |
| **HD** | 500 GB (armazenamento de volumes Kubernetes) |
| **Placa-mãe** | A68HM-K |
| **Fonte** | Knup 500W |
| **Gabinete** | C3 Tech |

**Nome do host:** `resilience-System-Product`
**IP do servidor:** `192.168.99.5`
**Rede local:** `192.168.99.0/24`
**Roteador:** `192.168.99.1`

---

## 📚 Roteiro de estudos

O lab foi construído seguindo esta trilha:

1. **Kubernetes** — base do lab (MicroK8s)
2. **GitOps** — ArgoCD + repositório Git
3. **Service Mesh** — Istio
4. **Observabilidade** — Kiali, Jaeger, Grafana, Prometheus, Loki
5. **DevOps** — Helm, CI/CD
6. **DevSecOps** — Trivy, Falco, Kyverno (próximos passos)

---

## ✅ Checklist de implementação

### 🐧 Sistema Operacional

- [x] Instalação do **Ubuntu Server** (versão 24.04 LTS ou superior)
- [x] Configuração de **SSH** (acesso remoto do Mac)
- [x] Ajuste de **hostname** para `resilience-System-Product`
- [x] Configuração de **IP fixo** ou DHCP reservado (`192.168.99.5`)

### 💾 Armazenamento

- [x] Particionamento do **HD de 500 GB** com `ext4`
- [x] Label do volume: **`k8s-data`**
- [x] Ponto de montagem: **`/mnt/k8s-data`**
- [x] Configuração no `/etc/fstab` com **UUID** e opções `defaults,nofail,noatime`
- [x] Permissões ajustadas para o usuário `jefferson`

### ☸️ Kubernetes (MicroK8s)

- [x] Instalação via Snap: `microk8s --classic --channel=1.32/stable`
- [x] Adição do usuário `jefferson` ao grupo `microk8s`
- [x] Instalação do `util-linux-extra` (para o comando `newgrp`)
- [x] Verificação do cluster: `microk8s status --wait-ready`
- [x] **Upgrade do cluster** de 1.30 → 1.32 (para compatibilidade com Istio 1.31)

#### Add-ons habilitados

- [x] `dns` (CoreDNS)
- [x] `rbac`
- [x] `hostpath-storage` (StorageClass padrão)
- [x] `metrics-server`
- [x] `metallb` (faixa `192.168.99.200-250`, 51 IPs)
- [x] `ingress` (NGINX Ingress Controller)
- [x] `helm` / `helm3`

### 🍎 Acesso remoto do Mac

- [x] Instalação do `kubectl` no Mac
- [x] Cópia do kubeconfig do MicroK8s para o Mac (`~/.kube/microk8s-config`)
- [x] Ajuste do IP no kubeconfig (`192.168.99.5:16443`)
- [x] Configuração do `KUBECONFIG` com múltiplos contextos (kind + microk8s)
- [x] Alias `mkssh` para comandos administrativos via SSH
- [x] Alias `k` para `kubectl`

### 📦 Helm

- [x] Instalação do Helm **via binário oficial** (Homebrew apresentou problemas no Mac Intel)
- [x] Verificação: `helm version` → v3.16.4
- [x] Repositório do ArgoCD adicionado: `helm repo add argo`

### 🚀 ArgoCD (GitOps)

- [x] Instalação via **Helm** no namespace `argocd`
- [x] Ajuste do modo `server.insecure=true` (SSL terminado no Ingress)
- [x] Exposição via Ingress NGINX: `argocd.local`
- [x] Senha inicial obtida do secret `argocd-initial-admin-secret`
- [x] Secret inicial **deletado** após login
- [x] Repositório GitOps criado: `newbare/homelab-gitops`

### 📦 App de exemplo: podinfo

- [x] Estrutura de pastas: `apps/podinfo/`
- [x] Manifests: `deployment.yaml`, `service.yaml`, `ingress.yaml`
- [x] Application no ArgoCD apontando para o repo
- [x] **Primeiro deploy GitOps** (reconciliação automática)
- [x] Teste de **escala via Git** (alteração de `replicas` → ArgoCD sincronizou)

### 🕸️ Istio (Service Mesh)

- [x] Instalação do `istioctl` **via binário oficial** (v1.31.0)
- [x] Precheck: `istioctl x precheck` → OK (requer Kubernetes 1.32+)
- [x] Instalação do Istio com `profile=demo`
- [x] Label `istio-injection=enabled` no namespace `default`
- [x] Sidecar injection validado (pods `2/2`)
- [x] Exposição do podinfo via **Istio Gateway** + **VirtualService**
- [x] Hostname: `podinfo-istio.local` → IP `192.168.99.200`

### 📊 Observabilidade

- [x] Addons de exemplo do Istio instalados (`samples/addons/`)
- [x] **Kiali** — exposto via Ingress: `kiali.local`
- [x] **Grafana** — exposto via Ingress: `grafana.local`
- [x] **Jaeger** — **downgrade para Jaeger 1.x** (compatibilidade com `istioctl dashboard`)
- [x] **Prometheus** — coletando métricas
- [x] **Loki** — coletando logs

### 📖 App de exemplo: Bookinfo

- [x] Deploy dos 4 microsserviços (`productpage`, `details`, `reviews`, `ratings`)
- [x] **3 versões do `reviews`** (v1, v2, v3) para testes de canary
- [x] Sidecars injetados (`2/2 Running`)
- [x] Gateway + VirtualService do Bookinfo configurados
- [x] Acesso via `http://bookinfo.local/productpage` ✅

---

## 📂 Estrutura do repositório GitOps

homelab-gitops/
├── apps/
│ └── podinfo/
│ ├── deployment.yaml
│ ├── service.yaml
│ ├── ingress.yaml
│ └── istio/
│ ├── gateway.yaml
│ └── virtualservice.yaml
├── infrastructure/
│ ├── istio/
│ │ └── jaeger-version.md
│ └── observability/
│ ├── grafana-ingress.yaml
│ ├── jaeger-ingress.yaml
│ └── kiali-ingress.yaml
├── .gitignore
└── README.md


---

## 🎯 Decisões técnicas importantes

| Decisão | Motivo |
| :--- | :--- |
| **MicroK8s em vez de K3s** | Add-ons prontos (Istio, MetalLB, Ingress), menor fricção para estudos |
| **Ubuntu Server** | Maior comunidade, compatibilidade com tutoriais |
| **MetalLB com 51 IPs** | Folga para múltiplos gateways, sem risco de esgotamento |
| **Ingress NGINX + Istio Gateway coexistindo** | Comparar as duas abordagens na prática |
| **Jaeger 1.x em vez de 2.x** | Compatibilidade com `istioctl dashboard jaeger` |
| **Helm via binário oficial** | Homebrew no Mac Intel tem limitações crescentes |
| **Repo GitOps separado do istioctl** | O diretório `istio-1.31.0/` não pertence ao repo (adicionado ao `.gitignore`) |

---

## 🔗 Endereços acessíveis do Mac

| Serviço | URL | Onde roda |
| :--- | :--- | :--- |
| ArgoCD | `http://argocd.local` | Ingress NGINX (`192.168.99.5`) |
| podinfo (Ingress) | `http://podinfo.local` | Ingress NGINX (`192.168.99.5`) |
| podinfo (Istio) | `http://podinfo-istio.local` | Istio Gateway (`192.168.99.200`) |
| Kiali | `http://kiali.local` | Ingress NGINX (`192.168.99.5`) |
| Grafana | `http://grafana.local` | Ingress NGINX (`192.168.99.5`) |
| Jaeger | `http://localhost:16686` | `istioctl dashboard jaeger` (port-forward) |
| Bookinfo | `http://bookinfo.local/productpage` | Istio Gateway (`192.168.99.200`) |

---

## 🚧 Próximos passos

### Curto prazo (Istio)

- [ ] **Traffic shifting** — canary `reviews` v1/v3 (90/10, 50/50)
- [ ] **Fault injection** — aborto HTTP 500, delay de 7s
- [ ] **mTLS estrito** — `PeerAuthentication` no namespace
- [ ] **Authorization policies** — restringir quem fala com quem
- [ ] **Circuit breaking** — resiliência entre serviços

### Médio prazo (DevOps)

- [ ] **CI/CD** — GitHub Actions para build e push de imagens
- [ ] **ArgoCD Image Updater** — atualização automática de tags
- [ ] **App of Apps** — um `Application` que gerencia outros
- [ ] **Kustomize** — sobreposição de ambientes (dev/prod)

### Longo prazo (DevSecOps)

- [ ] **Trivy** — scan de imagens (CI e cluster)
- [ ] **Falco** — runtime security
- [ ] **Kyverno** ou **OPA Gatekeeper** — políticas de admissão
- [ ] **Sealed Secrets** — secrets criptografados no Git
- [ ] **Network Policies** — segmentação de rede

---

## 📝 Notas e aprendizados

### Sobre MicroK8s

- O `microk8s enable` precisa de um **TTY interativo** para o `sudo` — use `ssh -t` ou sessão interativa.
- O add-on `rbac` pode falhar com `No callback tokens file`, mas o RBAC **já funciona por padrão** — valide com `kubectl auth can-i`.
- O `hostpath-storage` cria volumes em `/var/snap/microk8s/common/default-storage/` (no SSD). Para mover ao HD, é preciso configuração adicional.

### Sobre o Istio

- O Istio 1.31 **requer Kubernetes 1.32+**. Se seu cluster estiver em 1.30, faça upgrade do MicroK8s (`snap refresh`).
- O `profile=demo` instala `istiod`, `istio-ingressgateway` e `istio-egressgateway`.
- O **Istio Gateway** usa um IP dedicado do MetalLB (`192.168.99.200`), separado do Ingress NGINX (`192.168.99.5`).
- O **Jaeger 2.x** tem UI incompatível com `istioctl dashboard`. Fazer downgrade para 1.x (branch `release-1.30` do Istio).

### Sobre GitOps

- Deletar pods **não é** uma divergência de estado para o ArgoCD — o ReplicaSet recria automaticamente.
- O ArgoCD **intervém** quando há divergência entre Git e cluster (ex: `replicas` alteradas no Git).
- Use `automatic` sync policy com **Prune** e **Self Heal** para reconciliação contínua.

---

**Última atualização:** Setembro/2026


