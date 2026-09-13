# Homelab GitOps



### 🔍 Análise das Versões Disponíveis

| Canal | Versão K8s | Data | Comentário |
|-------|-----------|------|------------|
| `latest/stable` | **1.36.2** | 2026-06-24 | ✅ Mais recente, EOL em ~2027 |
| `1.35/stable` | 1.35.6 | 2026-07-02 | ✅ Boa opção, EOL longo |
| `1.34/stable` | 1.34.9 | 2026-06-17 | ⚠️ EOL em out/2026 |
| `1.33/stable` | 1.33.13 | 2026-07-01 | ⚠️ Já em EOL |

**Recomendação:** Usar **`1.35/stable` (v1.35.6)**.

Por quê?

- O `latest/stable` (1.36.2) é muito recente e pode ter incompatibilidades com Helm charts que ainda não foram atualizados (Istio, MetalLB, ArgoCD).
- O `1.35/stable` é maduro, tem suporte até ~2027 e é **totalmente compatível** com as versões mais recentes do Istio 1.30, ArgoCD v3.5, MetalLB 0.16.1 e NGINX Ingress LTS.
- Fixar o canal (`--channel=1.35/stable`) evita que um `snap refresh` futuro quebre seu laboratório.

### 🚀 Fase 1: Instalação do MicroK8s

**1. Instalar fixando o canal 1.35/stable:**

```bash
sudo snap install microk8s --classic --channel=1.35/stable
```

**2. Adicionar seu usuário ao grupo microk8s e ajustar permissões:**

```bash
sudo usermod -a -G microk8s $USER
sudo chown -f -R $USER ~/.kube
```

**3. Aplicar o novo grupo (ou faça logout/login depois):**

```bash
newgrp microk8s
```

> Se o `newgrp` abrir um subshell, tudo bem — você pode continuar nele. Se preferir, feche a sessão SSH e reconecte.

**4. Aguardar o cluster ficar pronto:**

```bash
microk8s status --wait-ready
```

Isso pode levar de 1 a 3 minutos na primeira execução.

**5. Verificar a versão instalada:**

```bash
microk8s version
```

Deve retornar algo como `MicroK8s v1.35.6 revision 9072`.

### 🔌 Fase 1 (continuação): Habilitar Apenas os Add-ons Essenciais

Conforme o roteiro, **não** habilitaremos `metallb`, `ingress` nem `istio` — esses serão instalados manualmente via Helm.

```bash
microk8s enable dns
microk8s enable hostpath-storage
microk8s enable rbac
```

**Aguarde cada um terminar** antes de rodar o próximo. O `dns` (CoreDNS) demora um pouco mais.

**Verificação:**

```bash
microk8s status
```

Você deve ver `dns: enabled`, `hostpath-storage: enabled`, `rbac: enabled`, e **`metallb: disabled`**, **`ingress: disabled`**, **`istio: disabled`**.

### 📄 Fase 1 (final): Preparar o kubeconfig para o Mac

**1. No servidor, gerar o kubeconfig:**

```bash
microk8s config > ~/microk8s-config.yaml
```

**2. Descobrir o IP correto do servidor na rede:**

```bash
ip -4 addr show | grep inet
```

Confirme que é o `192.168.99.5`. Se for, ótimo.

**3. Ajustar o `server:` no kubeconfig gerado.**

O MicroK8s gera o kubeconfig apontando para o IP da interface interna (geralmente `127.0.0.1` ou o IP da bridge). Você precisa trocar para o IP da LAN:

```bash
sed -i 's|server: https://.*:16443|server: https://192.168.99.5:16443|' ~/microk8s-config.yaml
```

Confirme com:

```bash
grep server ~/microk8s-config.yaml
```

Deve mostrar `server: https://192.168.99.5:16443`.

**4. Copiar o arquivo para o Mac.**

No **Mac**, execute:

```bash
mkdir -p ~/.kube
scp jefferson@192.168.99.5:~/microk8s-config.yaml ~/.kube/config
chmod 600 ~/.kube/config
```

> Ajuste o usuário `jefferson` se for diferente.

**5. (Ainda no Mac) Instalar o `kubectl` com versão compatível.**

Como o cluster é 1.35, instale o kubectl 1.35:

```bash
brew install kubectl@1.35
```

> Se essa formula não existir, instale via download direto:
> ```bash
> curl -LO "https://dl.k8s.io/release/v1.35.6/bin/darwin/amd64/kubectl"
> chmod +x kubectl
> sudo mv kubectl /usr/local/bin/kubectl
> ```
> (Use `darwin/arm64` se seu Mac for Apple Silicon.)

**6. Testar a conexão do Mac ao cluster:**

```bash
kubectl get nodes
kubectl get pods -A
```

Se retornar o nó `resilience-system-product` como `Ready` e os pods do `kube-system` rodando, **Fase 1 concluída com sucesso**. 🎉

### ⚠️ Ponto de Atenção: IP do Servidor

Antes de rodar o `sed`, **confirme** que o IP do servidor é mesmo `192.168.99.5`. Se o servidor tiver múltiplas interfaces (ex: uma bridge do Docker/Podman, uma VM, etc.), o `microk8s config` pode gerar um IP errado. Rode:

```bash
hostname -I
```

E identifique qual é o IP da sua LAN.

### ▶️ Próximo Passo

Rode os comandos acima em ordem e me envie a saída dos pontos: 

1. `microk8s version`
2. `microk8s status`
3. `grep server ~/microk8s-config.yaml`
4. (no Mac) `kubectl get nodes`

Com isso validado, partimos para a **Fase 2: MetalLB via Helm** — e aí reinstalamos o `helm` no Mac também.

Quer que eu já prepare o roteiro da Fase 2 enquanto você executa a Fase 1?
