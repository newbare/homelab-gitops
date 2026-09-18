# Trust anchor interno — 3 opções (e por que escolhemos a Opção B)

> **Caso concreto que motivou este documento:** Etapa 11 — o backend do Backstage
> (namespace `backstage`) precisa chamar `https://keycloak.local` para completar o
> fluxo OIDC. O certificado apresentado por `keycloak.local` é auto-assinado, e o
> Node.js recusa a conexão.
>
> Ver também: [`README.md`](README.md) (visão geral de certificados do repo).

---

## 1. O problema em uma frase

O Kubernetes **não permite** que um Pod monte um `Secret` ou `ConfigMap` de outro
namespace. Então, para o Pod do Backstage (ns `backstage`) confiar no certificado
servido em `keycloak.local` (cujo `Secret` está no ns `keycloak`), esse certificado
precisa ser **materializado dentro do namespace `backstage`**.

*Como* materializar — e o que acontece quando o certificado muda — é o assunto
deste documento.

---

## 2. Reproduzindo o problema

### 2.1 O certificado é auto-assinado

```bash
echo | openssl s_client -connect keycloak.local:443 -servername keycloak.local 2>/dev/null \
  | openssl x509 -noout -text \
  | grep -E 'Basic Constraints|Not After' -A 1
```

Saída obtida:

```
            X509v3 Basic Constraints: critical
                CA:FALSE
            Not After : Dec 17 16:54:18 2026 GMT
```

Três leituras:

| Linha | Significado |
|---|---|
| `-servername` | obrigatório (SNI). Sem ele o nginx devolve o certificado *default* (`fake`) e o resultado é enganoso |
| `CA:FALSE` | não é uma autoridade certificadora — é uma folha auto-assinada |
| `Not After: Dec 17 2026` | **validade de 90 dias** (default do cert-manager). Guarde essa data |

> ⚠️ `openssl x509 -subject -issuer` **não serve** para certificados do cert-manager:
> ambos os campos voltam vazios (a identidade fica nos SANs). Use `-text`.

### 2.2 O Node recusa a conexão

```bash
node -e "fetch('https://keycloak.local/realms/resilience/.well-known/openid-configuration')
  .then(r => console.log('HTTP', r.status))
  .catch(e => console.log('FALHOU:', e.cause?.code ?? e.message))"
```

Saída obtida:

```
FALHOU: DEPTH_ZERO_SELF_SIGNED_CERT
```

É **esse** erro que o backend do Backstage produziria ao tentar autenticar.

### 2.3 O controle negativo (o passo que valida o teste)

Um teste só é útil se puder falhar. O experimento a seguir prova que
`NODE_EXTRA_CA_CERTS` resolve — e é o mesmo mecanismo que usaremos no cluster:

```bash
# exporta o certificado servido
echo | openssl s_client -connect keycloak.local:443 -servername keycloak.local 2>/dev/null \
  | openssl x509 -outform PEM > /tmp/keycloak-ca.crt

# sem CA -> FALHA (controle)
node -e "fetch('https://keycloak.local/realms/resilience/.well-known/openid-configuration')
  .then(r => console.log('SEM CA -> HTTP', r.status))
  .catch(e => console.log('SEM CA -> FALHOU:', e.cause?.code ?? e.message))"

# com CA -> deve funcionar
NODE_EXTRA_CA_CERTS=/tmp/keycloak-ca.crt node -e "fetch('https://keycloak.local/realms/resilience/.well-known/openid-configuration')
  .then(r => console.log('COM CA -> HTTP', r.status))
  .catch(e => console.log('COM CA -> FALHOU:', e.cause?.code ?? e.message))"
```

Saídas obtidas:

```
SEM CA  -> FALHOU: DEPTH_ZERO_SELF_SIGNED_CERT
COM CA  -> HTTP 200
```

**Fato verificado:** o Node **aceita** um certificado auto-assinado com
`CA:FALSE` como âncora de confiança via `NODE_EXTRA_CA_CERTS`. A teoria de que
seria obrigatório ter `CA:TRUE` está **errada**. Isso importa: sem esse teste,
haveria uma reforma desnecessária na arquitetura de certificados.

---

## 3. A pista falsa: "90 dias é curto demais"

A tentação imediata, ao ver `Not After: Dec 17 2026`, é concluir:

> "90 dias é pouco. Vamos aumentar a validade e resolver o problema."

**Essa conclusão está errada** — e entender por quê é mais importante do que
qualquer comando deste documento.

### 3.1 O que o Let's Encrypt faz

A Let's Encrypt é a maior CA do mundo e emite certificados de **90 dias**. Não é
uma limitação temporária: é uma escolha de projeto.

Do FAQ oficial (letsencrypt.org/docs/faq):

> **"Our default certificates are valid for 90 days."**
>
> **"There is no way to adjust these lifetimes, there are no exceptions. We
> recommend renewing 90 day certificates every 60 days."**
>
> "Subscribers can opt in to short-lived certificates which are valid for six
> days."

E do artigo *Why ninety-day lifetimes for certificates?* (Josh Aas, ISRG, 2015):

> "Ninety days is nothing new on the Web. According to Firefox Telemetry, **29% of
> TLS transactions use ninety-day certificates. That's more than any other
> lifetime.**"
>
> "From our perspective, there are two primary advantages to such short
> certificate lifetimes:
> **1. They limit damage from key compromise and mis-issuance.**
> **2. They encourage automation, which is absolutely essential for ease-of-use.**"
>
> "Once issuance and renewal are automated, shorter lifetimes won't be any less
> convenient than longer ones."
>
> "Once automated renewal tools are widely deployed and working well, we may
> consider even shorter lifetimes."

E eles de fato encurtaram: desde fevereiro de 2025 a Let's Encrypt emite
certificados de **6 dias** para quem adere.

### 3.2 Por que 90 dias funciona em produção

Ambientes produtivos sérios — bancos, e-commerces, SaaS — rodam com certificados
de 90 dias (ou menos) **sem drama**. O motivo é a separação em duas camadas:

| Camada | Validade | Muda? |
|---|---|---|
| **Raiz** (ISRG Root X1, já embutida em Windows/macOS/Linux/Android/iOS) | medida em **décadas** | praticamente nunca |
| **Folha** (o certificado do seu site) | **90 dias** | rotaciona automaticamente, a cada ~60 dias |

O cliente valida a folha **contra uma raiz que ele já conhece**. Quando a folha
rotaciona, ninguém precisa ser avisado: a validação continua passando, porque a
âncora de confiança não mudou.

Ninguém copia o certificado do `example.com` para dentro da aplicação de
`other.example.com`. A confiança é **herdada da raiz**, e a rotação é
**automatizada pelo protocolo ACME**.

### 3.3 A lição

> **O problema nunca foram os 90 dias. O problema é COPIAR um artefato que rotaciona.**

Se o certificado muda a cada 90 dias e alguém copiou ele para outro lugar, existe
uma data — conhecida e futura — em que a cópia fica velha e algo quebra
*silenciosamente*, sem ninguém ter tocado em nada.

A falha é do **acoplamento** (cópia de algo volátil), não do **prazo**.

### 3.4 O que a nossa arquitetura faz de diferente

O `ClusterIssuer` deste cluster é:

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: selfsigned-issuer
spec:
  selfSigned: {}
```

O `selfSigned` do cert-manager gera, para cada `Certificate`, um certificado
**independente e auto-assinado**. Ou seja:

```
Let's Encrypt:   raiz estável (décadas)  +  folha rotativa (90 dias)   ->  ✅ confiança estável
Nosso cluster:   folha rotativa (90 dias) QUE É a própria raiz          ->  ❌ cada rotação troca a âncora
```

É por isso que 90 dias é inofensivo lá e problemático aqui: **aqui não existe uma
camada estável**. Cada renovação troca aquilo em que se confia.

As três opções a seguir são, todas, formas diferentes de resolver esse
desacoplamento.

---

## 4. As três opções

Todas partem do mesmo ponto: o certificado (ou a raiz) precisa existir **dentro do
namespace `backstage`**, e o processo Node precisa saber onde encontrá-lo.

O mecanismo de confiança é sempre o mesmo — variável de ambiente `NODE_EXTRA_CA_CERTS`
apontando para um arquivo PEM montado de um `ConfigMap`:

```yaml
backstage:
  extraEnvVars:
    - name: NODE_EXTRA_CA_CERTS
      value: /etc/keycloak-ca/ca.crt
  extraVolumes:
    - name: keycloak-ca
      configMap:
        name: keycloak-ca        # nome varia conforme a opção
  extraVolumeMounts:
    - name: keycloak-ca
      mountPath: /etc/keycloak-ca
      readOnly: true
```

O que muda entre A, B e C é **de onde vem o conteúdo** desse `ConfigMap` e
**quem o mantém atualizado**.

---

### 4.1 Opção A — cópia manual do certificado corrente

**Ideia:** copiar o certificado de hoje para um `ConfigMap` no ns `backstage`.

**Comandos:**

```bash
# 1. extrai o certificado servido por keycloak.local
kubectl get secret keycloak.local-tls -n keycloak \
  -o jsonpath='{.data.tls\.crt}' \
  | base64 -d > /tmp/keycloak-ca.crt

# 2. confere que veio um PEM válido
openssl x509 -in /tmp/keycloak-ca.crt -noout -subject -dates

# 3. cria o ConfigMap no namespace onde o Pod roda
kubectl create configmap keycloak-ca -n backstage \
  --from-file=ca.crt=/tmp/keycloak-ca.crt
```

Depois, aplicar no `app.yaml` do Backstage o bloco `extraVolumes` /
`extraVolumeMounts` / `extraEnvVars` mostrado acima.

> `tls.crt` é garantido: o tipo `kubernetes.io/tls` **exige** as chaves `tls.crt`
> e `tls.key`. `ca.crt` é adicional e opcional.

**Vantagens:** é o caminho mais curto; funciona imediatamente (mecanismo já
provado na seção 2.3).

**Problemas:**

| # | Problema |
|---|---|
| 1 | **Quebra sozinho em ~60 dias.** O cert-manager renova ~30 dias antes do vencimento. Quando isso acontece, a cópia fica velha e a autenticação falha sem nenhuma mudança ter sido feita |
| 2 | A falha é **silenciosa e diferida** — o pior tipo. Diagnóstico caro, porque o erro aparece como falha genérica de login |
| 3 | Cria uma cópia **imperativa**, fora do Git. Num repo GitOps, vira estado não versionado |
| 4 | Nada avisa quando vai quebrar |

**Quando usar:** como passo **temporário e consciente**, para validar rápido que o
resto do fluxo funciona. Com a data de vencimento anotada e um item de backlog
registrado. Nunca como estado final.

---

### 4.2 Opção B — CA interna estável ⭐ **(a escolha deste projeto)**

**Ideia:** criar uma **CA própria** (auto-assinada, com `isCA: true`), usá-la para
assinar o certificado de `keycloak.local`, e copiar apenas **a CA** — que é estável.

Isso reproduz, dentro do cluster, exatamente o que a Let's Encrypt faz no mundo
público: raiz estável + folha rotativa.

**Arquivo:** `infrastructure/cert-manager/ca.yaml`

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: homelab-ca
  namespace: cert-manager
spec:
  isCA: true                                  # <- isto é o que cria uma CA
  commonName: homelab-ca
  secretName: homelab-ca
  duration: 87600h                            # 10 anos
  renewBefore: 8760h                          # renova 1 ano antes
  privateKey:
    algorithm: ECDSA
    size: 256
  issuerRef:
    name: selfsigned-issuer                   # o ClusterIssuer que já existe
    kind: ClusterIssuer
    group: cert-manager.io
---
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: homelab-ca-issuer
spec:
  ca:
    secretName: homelab-ca                    # resolvido no ns `cert-manager`
```

> O `ClusterIssuer` do tipo `ca` procura o `secretName` no **cluster resource
> namespace** (por default, `cert-manager`). Por isso a `Certificate` da CA é
> criada lá.

**Comandos:**

```bash
# 1. cria a CA e o ClusterIssuer
kubectl apply -f infrastructure/cert-manager/ca.yaml

# 2. confere que a CA foi emitida
kubectl get clusterissuer
kubectl -n cert-manager get secret homelab-ca

# 3. confere que a CA realmente é uma CA
kubectl -n cert-manager get secret homelab-ca \
  -o jsonpath='{.data.tls\.crt}' | base64 -d \
  | openssl x509 -noout -text | grep -A 1 'Basic Constraints'
# esperado: CA:TRUE
```

**Trocar o emissor do Keycloak** — em `infrastructure/keycloak/app.yaml`, uma linha:

```yaml
        ingress:
          annotations:
            cert-manager.io/cluster-issuer: homelab-ca-issuer   # era selfsigned-issuer
```

```bash
# o ingress-shim percebe a mudança de issuerRef e reemite o certificado
kubectl apply -f infrastructure/keycloak/app.yaml

# acompanha a reemissão
kubectl -n keycloak get certificate
kubectl -n keycloak get secret keycloak.local-tls -o jsonpath='{.data.tls\.crt}' \
  | base64 -d | openssl x509 -noout -issuer -text | grep -A 1 'Basic Constraints'
```

**Materializar a CA no namespace `backstage`** — agora com um artefato **estável**,
que pode ser versionado no Git:

```bash
# extrai a CA (válida 10 anos)
kubectl -n cert-manager get secret homelab-ca \
  -o jsonpath='{.data.tls\.crt}' | base64 -d > /tmp/homelab-ca.crt

openssl x509 -in /tmp/homelab-ca.crt -noout -dates
```

E commitar como manifesto em `infrastructure/backstage/keycloak-ca.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: keycloak-ca
  namespace: backstage
data:
  ca.crt: |
    -----BEGIN CERTIFICATE-----
    ...conteúdo de /tmp/homelab-ca.crt...
    -----END CERTIFICATE-----
```

No `app.yaml` do Backstage, o mesmo bloco `extraVolumes` / `extraVolumeMounts` /
`extraEnvVars` da seção 4.

**Vantagens:**

| # | Vantagem |
|---|---|
| 1 | **Resolve a causa raiz:** existe agora uma camada estável de confiança |
| 2 | A cópia no `backstage` não precisa ser atualizada na prática (CA válida 10 anos) |
| 3 | O `ConfigMap` pode ser **commitado no Git** → revisável no PR, versionado |
| 4 | **Blast radius mínimo:** só o `keycloak.local` muda de emissor. Os outros hosts (argocd, backstage, kiali, jaeger, grafana) seguem no `selfsigned-issuer` |
| 5 | Bônus: importando a CA no Keychain do macOS **uma vez**, os avisos do browser somem para `keycloak.local` |
| 6 | Fecha um item de backlog já registrado no `README.md` desta pasta |

**Problemas:**

| # | Problema |
|---|---|
| 1 | Ainda existe **um passo manual** (extrair a CA e commitar o `ConfigMap`) — porém uma vez a cada ~10 anos, não a cada 90 dias |
| 2 | Num bootstrap do zero, a CA precisa existir antes do `ConfigMap` poder ser preenchido (chicken-and-egg, resolvido por ordem de sync-wave) |
| 3 | Quem confia na CA passa a confiar em **tudo** que ela assinar. A chave privada da CA é agora material sensível e deve ficar só no cluster |

---

### 4.3 Opção C — trust-manager (distribuição automática)

**Ideia:** instalar o **trust-manager** (projeto irmão do cert-manager, da Jetstack)
e declarar um `Bundle`. Ele distribui o bundle para `ConfigMap`s em **todos os
namespaces** do cluster, e **ressincroniza sozinho** quando a origem muda.

É a única das três opções que **elimina completamente o passo manual**.

**Comandos:**

```bash
# instalação (teste fora do ArgoCD)
helm upgrade trust-manager oci://quay.io/jetstack/charts/trust-manager \
  --install \
  --namespace cert-manager \
  --wait
```

> ⚠️ Neste repo, instalações são feitas via **ArgoCD Application**, como os outros
> componentes em `infrastructure/`. Criar `infrastructure/trust-manager/app.yaml`
> seguindo o padrão das demais.

**O recurso `Bundle`:**

```yaml
apiVersion: trust.cert-manager.io/v1alpha1
kind: Bundle
metadata:
  name: homelab-ca
spec:
  sources:
    - secret:
        name: homelab-ca        # lido do ns `cert-manager` (trust namespace)
        key: tls.crt
  target:
    configMap:
      key: ca.crt
```

O que acontece:

- O `Bundle` é **cluster-scoped**.
- O `target` gera um `ConfigMap` cujo **nome é igual ao do Bundle** (`homelab-ca`),
  com a chave `ca.crt`.
- Com `namespaceSelector` vazio, o `ConfigMap` é sincronizado em **todos os
  namespaces** — inclusive `backstage`.
- Se a origem mudar, o `ConfigMap` em todos os namespaces é atualizado sozinho.

No `app.yaml` do Backstage, o volume passa a apontar para esse `ConfigMap`
(nenhuma extração manual, nenhum `kubectl create configmap`):

```yaml
backstage:
  extraVolumes:
    - name: keycloak-ca
      configMap:
        name: homelab-ca
```

```bash
# confere o estado do bundle
kubectl get bundle
kubectl get configmap homelab-ca -n backstage -o "jsonpath={.data['ca\.crt']}" | openssl x509 -noout -subject
```

**Restrição importante:** as fontes `secret` e `configMap` de um `Bundle` só são
lidas do **namespace do trust-manager** (por default, `cert-manager`). Um
`Secret` no ns `keycloak` **não** pode ser fonte direta. Isso torna a Opção C um
complemento natural da Opção B (a CA já mora em `cert-manager`).

**Vantagens:**

| # | Vantagem |
|---|---|
| 1 | **Zero passos manuais.** Nenhuma cópia, nunca |
| 2 | Lida com rotação de **qualquer** origem, automaticamente |
| 3 | Resolve o problema para **todo o cluster**, não só para o Backstage |
| 4 | É a solução desenhada pelo próprio ecossistema cert-manager para este problema |

**Problemas:**

| # | Problema |
|---|---|
| 1 | **Mais um operador** rodando no cluster (mais superfície de atualização e monitoração) |
| 2 | Um componente que, com bug ou indisponibilidade, afeta a confiança TLS de vários workloads |
| 3 | A própria doc do trust-manager alerta: apontar um `Bundle` **direto** para um `Secret` rotativo do cert-manager faz a **nova raiz substituir a antiga imediatamente**, podendo destrustar certificados ainda em uso. A recomendação oficial é justamente **copiar a raiz estável** para uma fonte dedicada e atualizá-la sob controle |

> 💡 Esse último ponto é notável: a documentação oficial do cert-manager
> **recomenda intencionalmente fazer uma cópia** da raiz. O que ela condena é
> copiar algo **volátil**. Isso valida o raciocínio da seção 3.3.

---

## 5. Comparação

| Critério | A — cópia manual | **B — CA estável** ⭐ | C — trust-manager |
|---|---|---|---|
| Funciona hoje | ✅ | ✅ | ✅ |
| Sobrevive à rotação de 90 dias | ❌ quebra em ~60 dias | ✅ (a CA não rotaciona) | ✅ (ressincroniza) |
| Passos manuais recorrentes | a cada ~60 dias | ~1 a cada 10 anos | nenhum |
| Versionável no Git | ❌ imperativo | ✅ | ✅ |
| Componentes novos no cluster | 0 | 0 | **1 operador** |
| Blast radius | baixo | **muito baixo** (só `keycloak.local`) | todo o cluster |
| Esforço inicial | ~5 min | ~20 min | ~40 min |
| Risco de falha silenciosa futura | **alto** | muito baixo | muito baixo |
| Fecha item de backlog do repo | ❌ | ✅ | ✅ |

---

## 6. Por que escolhemos a Opção B

Cinco razões, em ordem de peso:

1. **Elimina a falha silenciosa e diferida.** A Opção A cria um problema com data
   marcada para acontecer, sem nenhum sintoma até o dia em que quebra. Trocar isso
   por um artefato estável é a diferença entre "não precisa pensar" e "precisa
   lembrar".

2. **Custo desprezível.** São 2 recursos novos (`Certificate` + `ClusterIssuer`),
   uma linha alterada no `app.yaml` do Keycloak e um `ConfigMap`. ~20 minutos.

3. **Blast radius mínimo.** Diferente de migrar tudo para uma CA nova, apenas
   `keycloak.local` troca de emissor. Nenhum outro host do lab é afetado, e não há
   risco de destrustar certificados em uso durante a transição.

4. **Resolve o problema na camada certa.** Reproduz a arquitetura que a indústria
   usa (raiz estável + folha rotativa) em vez de contornar o sintoma aumentando o
   prazo — que, além de não resolver, contraria a direção em que o setor caminha
   (a Let's Encrypt já emite certificados de 6 dias).

5. **Abre o caminho para a Opção C.** Com a CA em `cert-manager`, adotar
   trust-manager depois é trivial: basta um `Bundle`. O trabalho da Opção B não é
   descartado, é a fundação da C.

### O que **não** escolhemos, e por quê

- **Aumentar a validade do certificado para "resolver" o problema.** Não resolve:
  o certificado continua sendo folha *e* raiz, e a próxima rotação (agora em 5
  anos) ainda quebraria a cópia. Seria trocar uma falha frequente por uma falha
  rara — e mais difícil ainda de diagnosticar, porque ninguém lembra de algo
  configurado 5 anos atrás.
- **Desligar a verificação TLS** (`NODE_TLS_REJECT_UNAUTHORIZED=0`). Rejeitado por
  princípio: desabilita a validação **globalmente** no processo, não só para o
  Keycloak. Num projeto de estudo de DevSecOps, é exatamente o antipadrão a não
  praticar.
- **A Opção C agora.** É a mais completa, mas introduz um operador e amplia o
  blast radius para todo o cluster. Fica como evolução natural (seção 10), não
  como pré-requisito.

---

## 7. Como validar que funcionou

```bash
# 1. o Pod subiu e está montando o arquivo?
kubectl -n backstage exec deploy/backstage -- ls -l /etc/keycloak-ca/

# 2. a variável de ambiente está no processo?
kubectl -n backstage exec deploy/backstage -- printenv NODE_EXTRA_CA_CERTS

# 3. o backend consegue falar com o Keycloak?
kubectl -n backstage exec deploy/backstage -- node -e "
  fetch('https://keycloak.local/realms/resilience/.well-known/openid-configuration')
    .then(r => console.log('HTTP', r.status))
    .catch(e => console.log('FALHOU:', e.cause?.code ?? e.message))"
```

Esperado: `HTTP 200`.

E, do lado do cluster, o certificado de `keycloak.local` deve agora ser emitido
pela CA interna:

```bash
kubectl -n keycloak get secret keycloak.local-tls -o jsonpath='{.data.tls\.crt}' \
  | base64 -d | openssl x509 -noout -text | grep -A 2 'Authority Key Identifier'
```

---

## 8. Armadilhas e diagnóstico

| Sintoma | Causa provável |
|---|---|
| `DEPTH_ZERO_SELF_SIGNED_CERT` | o `NODE_EXTRA_CA_CERTS` não chegou ao processo, ou o arquivo montado está vazio |
| `UNABLE_TO_VERIFY_LEAF_SIGNATURE` | foi montado o certificado **folha** errado (ex.: de outro host) |
| Funcionava e parou **sozinho** | rotação do certificado. Sintoma clássico da Opção A |
| `mountPath` certo mas `ls` vazio | `ConfigMap` criado no namespace errado — precisa estar no ns `backstage` |
| Erro só depois de recriar o Pod | o `ConfigMap` foi criado imperativamente e não está no Git |

Comandos de investigação:

```bash
kubectl -n backstage get configmap
kubectl -n backstage describe deploy backstage | grep -A 5 -i 'mount\|environment'
kubectl -n backstage logs deploy/backstage | grep -i 'certificate\|self.signed\|oidc'
```

**Datas para ter no radar** (sintoma = login OIDC parando de funcionar sem
nenhuma mudança no repo):

```bash
kubectl -n keycloak get certificate -o wide
kubectl -n cert-manager get certificate homelab-ca -o wide
```

---

## 9. Referências

- [Why ninety-day lifetimes for certificates?](https://letsencrypt.org/2015/11/09/why-90-days) — Josh Aas, ISRG
- [Let's Encrypt — FAQ](https://letsencrypt.org/docs/faq/) — vida útil, renovação, short-lived certs
- [cert-manager — SelfSigned issuer](https://cert-manager.io/docs/configuration/selfsigned/)
- [cert-manager — CA issuer](https://cert-manager.io/docs/configuration/ca/)
- [trust-manager](https://cert-manager.io/docs/trust/trust-manager/) — `Bundle`, trust namespace, guia "Preparing for Production"
- [Kubernetes — Adding entries to a Pod's /etc/hosts](https://kubernetes.io/docs/concepts/services-networking/add-entries-to-pod-etc-hosts-with-host-aliases/)

---

## 10. Backlog — quando migrar para a Opção C

Adotar trust-manager quando **qualquer** destes for verdadeiro:

- outro workload (além do Backstage) precisar confiar em certificados internos;
- o lab passar a rodar uma CA interna de verdade para múltiplos serviços;
- a manutenção do `ConfigMap` da CA começar a incomodar.

A migração é incremental: o `Bundle` aponta para a **mesma** `Secret` `homelab-ca`
criada na Opção B, e o Backstage só troca o nome do `ConfigMap` referenciado no
volume. Nada do trabalho da Opção B é descartado.
