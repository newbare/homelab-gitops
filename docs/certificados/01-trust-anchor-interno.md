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
| 1 | Ainda existe **um passo manual**: extrair a CA e commitá-la num arquivo do repo. Material **gerado pelo cluster** acaba versionado como dado — o valor não é derivável do Git. Ver seção 10 |
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
  extraEnvVars:
    - name: NODE_EXTRA_CA_CERTS
      value: /etc/homelab-ca/ca.crt
  extraVolumes:
    - name: homelab-ca          # nome do VOLUME: livre, escolhido por nós
      configMap:
        name: homelab-ca        # nome do CONFIGMAP: tem de ser o nome do Bundle
  extraVolumeMounts:
    - name: homelab-ca
      mountPath: /etc/homelab-ca
      readOnly: true
```

Os dois `homelab-ca` acima são coincidência de nome, não obrigação: o trust-manager
nomeia o `ConfigMap` que cria com o **nome do `Bundle`**. O nome do volume é livre.
Manter os dois iguais é só para leitura.

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

## 7. Como validar

### 7.1 A CA (uma vez, logo após criá-la)

O bloco mais importante depois de criar a CA: provar que ela **é** uma CA, e não
apenas mais um certificado auto-assinado.

```bash
kubectl -n cert-manager get secret homelab-ca \
  -o jsonpath='{.data.tls\.crt}' | base64 -d > /tmp/homelab-ca.crt

echo '--- identidade e datas ---'
openssl x509 -in /tmp/homelab-ca.crt -noout -subject -issuer -dates

echo
echo '--- e uma CA? ---'
openssl x509 -in /tmp/homelab-ca.crt -noout -text | grep -A 1 'Basic Constraints'

echo
echo '--- Key Usage ---'
openssl x509 -in /tmp/homelab-ca.crt -noout -text | grep -A 2 'X509v3 Key Usage'

echo
echo '--- ela valida a si mesma? ---'
openssl verify -CAfile /tmp/homelab-ca.crt /tmp/homelab-ca.crt
```

**Saída real obtida (2026-09-18):**

```
--- identidade e datas ---
subject=CN=homelab-ca
issuer=CN=homelab-ca
notBefore=Sep 18 19:18:59 2026 GMT
notAfter=Sep 15 19:18:59 2036 GMT

--- e uma CA? ---
            X509v3 Basic Constraints: critical
                CA:TRUE

--- Key Usage ---
            X509v3 Key Usage: critical
                Digital Signature, Key Encipherment, Certificate Sign

--- ela valida a si mesma? ---
/tmp/homelab-ca.crt: OK
```

Por que **quatro** verificações, e não uma só:

| Bloco | Pergunta que responde | Se falhar |
|---|---|---|
| identidade e datas | é uma identidade própria, com vida longa? | a cópia vai expirar e o login quebra sozinho |
| Basic Constraints | é `CA:TRUE`? | é só mais uma folha auto-assinada — o problema original |
| Key Usage | tem `Certificate Sign`? | a CA existe, mas **não pode assinar** folhas |
| `openssl verify` | forma cadeia válida? | a raiz está malformada |

O terceiro bloco é o mais fácil de esquecer: `CA:TRUE` **sem** `Certificate Sign`
é uma CA que existe no papel e falha na prática.

> 📌 Note que aqui o `subject` vem **preenchido** (`CN=homelab-ca`), enquanto nos
> certificados folha do cert-manager ele vinha **vazio**. Não é inconsistência:
> numa CA o CN vai para o `Subject` porque não há SAN a preencher. O mesmo
> comando dá resultados diferentes porque os tipos de certificado são diferentes.

> 🔧 Refinamento possível: o `Key Usage` saiu com `Key Encipherment` e sem
> `CRL Sign`. Uma CA estritamente correta costuma ter apenas
> `Certificate Sign` + `CRL Sign`.

### 7.2 A folha de `keycloak.local`

Depois de trocar a annotation para `homelab-ca-issuer`, a prova definitiva de que
funcionou não é ler a annotation — é a **cadeia**:

```bash
# extrai a folha que o ingress está servindo
kubectl -n keycloak get secret keycloak.local-tls \
  -o jsonpath='{.data.tls\.crt}' | base64 -d > /tmp/keycloak-leaf.crt

# a CA interna valida essa folha?
openssl verify -CAfile /tmp/homelab-ca.crt /tmp/keycloak-leaf.crt
```

Esperado: `/tmp/keycloak-leaf.crt: OK`.

**Antes** da troca, esse mesmo comando retornava:

```
error 18 at 0 depth lookup: self-signed certificate
```

— que é exatamente o problema descrito na seção 2. Ou seja: o comando é o mesmo,
e a mudança de resultado é a prova.

#### ⚠️ Três sinais que PARECEM provar, mas não provam

Este é o ponto mais fácil de errar de todo o documento. Depois de trocar a
annotation, os três comandos abaixo **parecem** confirmar sucesso — e **nenhum**
deles confirma:

| Sinal | O que ele realmente prova |
|---|---|
| `kubectl get ingress` mostrando `homelab-ca-issuer` | que a **annotation** mudou. Nada sobre o certificado |
| `kubectl get certificate` com `READY: True` | que existe um certificado válido. Nada sobre **qual issuer** o gerou |
| `AGE` do objeto `Certificate` | **o mais enganoso** — ver abaixo |

**O caso do `AGE`.** Ele é a idade do **objeto** `Certificate`, **não** do
certificado emitido. Ao reemitir, o cert-manager **atualiza o `Secret` no lugar**;
o objeto `Certificate` não é recriado. Logo:

```
NAME                 READY   SECRET               AGE
keycloak.local-tls   True    keycloak.local-tls   150m
```

`READY: True` com `AGE: 150m` pode significar duas coisas **opostas**:

- ✅ o certificado **foi** reemitido agora; o objeto é que é antigo
- ❌ a annotation mudou, mas o cert-manager **ainda não reemitiu**

Os dois estados produzem **exatamente a mesma saída**. A idade do objeto não
distingue um do outro. Confiar nela é confiar em um sinal que não responde à
pergunta feita.

#### O que prova de verdade

| Verificação | O que prova |
|---|---|
| `openssl verify -CAfile <CA> <folha>` → `OK` | a folha foi **assinada por essa CA** — a cadeia fecha |
| `notBefore` recente na folha **servida** | o nginx está entregando o certificado **novo**, e não um antigo em cache |

```bash
# a data de emissão do certificado que o servidor entrega AGORA
echo | openssl s_client -connect keycloak.local:443 -servername keycloak.local 2>/dev/null \
  | openssl x509 -noout -dates
```

Se o `notBefore` for de hoje (e não da data em que o Ingress foi criado), a
reemissão realmente chegou ao servidor.

### 7.3 O Pod do Backstage

```bash
# 1. o Pod subiu e está montando o arquivo?
kubectl -n backstage exec deploy/backstage -- ls -l /etc/homelab-ca/

# 2. a variável de ambiente está no processo?
kubectl -n backstage exec deploy/backstage -- printenv NODE_EXTRA_CA_CERTS

# 3. o backend consegue falar com o Keycloak?
kubectl -n backstage exec deploy/backstage -- node -e "
  fetch('https://keycloak.local/realms/resilience/.well-known/openid-configuration')
    .then(r => console.log('HTTP', r.status))
    .catch(e => console.log('FALHOU:', e.cause?.code ?? e.message))"
```

Esperado: `HTTP 200`.

#### 7.3.1 O controle negativo que NÃO funciona

O jeito intuitivo de provar que é a CA montada que sustenta a confiança seria
limpar a variável em runtime:

```bash
# ❌ NÃO É UM CONTROLE VÁLIDO
kubectl -n backstage exec deploy/backstage -- node -e "
  process.env.NODE_EXTRA_CA_CERTS='';
  fetch('https://keycloak.local/realms/resilience/.well-known/openid-configuration')
    .then(r => console.log('INESPERADO: HTTP', r.status))..."
```

Resultado observado: `HTTP 200` — **igual ao caso positivo. Não prova nada.**

Motivo: o Node lê `NODE_EXTRA_CA_CERTS` **uma única vez, na inicialização do
processo**, e carrega o bundle no trust store. Alterar a variável depois não
desfaz a confiança que já foi carregada.

O controle válido remove a variável do **processo filho**, para que ele **nasça**
sem ela:

```bash
# ✅ CONTROLE NEGATIVO VÁLIDO
kubectl -n backstage exec deploy/backstage -- \
  env -u NODE_EXTRA_CA_CERTS node -e "
    fetch('https://keycloak.local/realms/resilience/.well-known/openid-configuration')
      .then(r => console.log('INESPERADO: HTTP', r.status))
      .catch(e => console.log('como esperado, falhou:', e.cause?.code ?? e.message))"
```

Resultado observado:

```
como esperado, falhou: UNABLE_TO_VERIFY_LEAF_SIGNATURE
```

É o contraste entre os dois quadros que sustenta a afirmação "esta CA é a origem
da confiança" — e não, por exemplo, um certificado já embutido na imagem.

#### 7.3.2 Impressão digital igual, arquivo diferente

Ao conferir a CA distribuída pelo trust-manager contra o `Secret` de origem:

| | bytes | impressão digital SHA-256 |
|---|---|---|
| `Secret homelab-ca` (`tls.crt`) | 554 | `F9:B1:EE:...:EF:A3` |
| `ConfigMap homelab-ca` (`ca.crt`) | 553 | `F9:B1:EE:...:EF:A3` |

As impressões digitais são **idênticas** e os tamanhos **diferem em 1 byte**. O
`diff` mostra por quê:

```
10c10
< -----END CERTIFICATE-----
---
> -----END CERTIFICATE-----
\ No newline at end of file
```

O trust-manager normaliza o PEM e **remove o `\n` final**. Consequência prática:
comparar arquivos por hash (`shasum`) acusa diferença onde **não há diferença
criptográfica**. Para comparar identidade de certificado, use impressão digital —
não hash de arquivo:

```bash
# ✅ compara IDENTIDADE
kubectl -n cert-manager get secret homelab-ca -o jsonpath='{.data.tls\.crt}' \
  | base64 -d | openssl x509 -noout -fingerprint -sha256

kubectl -n backstage get configmap homelab-ca -o jsonpath='{.data.ca\.crt}' \
  | openssl x509 -noout -fingerprint -sha256
```

---

## 8. Armadilhas e diagnóstico

| Sintoma | Causa provável |
|---|---|
| `DEPTH_ZERO_SELF_SIGNED_CERT` | o `NODE_EXTRA_CA_CERTS` não chegou ao processo, ou o arquivo montado está vazio |
| `UNABLE_TO_VERIFY_LEAF_SIGNATURE` | foi montado o certificado **folha** errado (ex.: de outro host) |
| Funcionava e parou **sozinho** | rotação do certificado. Sintoma clássico da Opção A |
| `mountPath` certo mas `ls` vazio | `ConfigMap` montado não existe, ou o nome do `ConfigMap` no `extraVolumes` não é o nome do `Bundle` |
| `ConfigMap homelab-ca` não aparece em algum namespace | trust-manager não está rodando, ou o `Bundle` não sincronizou — ver os comandos abaixo |
| Erro só depois de recriar o Pod | algum recurso foi criado **imperativamente** e não está no Git. Hoje isso se aplica a `backstage-catalog-users`, não mais à CA |
| `READY: True` com `AGE` antigo e a cadeia **não** fecha | **falso positivo** — `AGE` é do objeto, não do certificado; o cert-manager ainda não reemitiu (ver 7.2) |
| `openssl verify` dá `error 18` depois de trocar o issuer | a folha no Secret ainda é a antiga, ou o `.crt` em `/tmp` está desatualizado |
| `shasum` do `Secret` difere do `ConfigMap` | esperado: o trust-manager remove o `\n` final. Compare por impressão digital (ver 7.3.2) |

Comandos de investigação:

```bash
# --- os recursos de confiança ---
kubectl get bundle
kubectl -n cert-manager get pods                                    # trust-manager Running?
kubectl get configmap -A --field-selector metadata.name=homelab-ca  # chegou em todos os ns?
kubectl get bundle homelab-ca \
  -o jsonpath='{range .status.conditions[*]}{.type}={.status}  {.message}{"\n"}{end}'

# --- o que o Pod está usando ---
kubectl -n backstage describe deploy backstage | grep -A 5 -i 'mount\|environment'
kubectl -n backstage logs deploy/backstage | grep -i 'certificate\|self.signed\|oidc'
```

### 8.1 "Tudo reiniciou ao mesmo tempo" ≠ "as aplicações quebraram"

Um caso que apareceu em 2026-09-18 e que vale saber distinguir: durante uma pausa,
**todos os pods do cluster** reiniciaram na mesma janela de ~1 minuto —
`coredns`, `calico`, `metallb`, `argocd` (7 pods), `prometheus`, `grafana`,
`jaeger`, `keycloak`, `backstage` — e, junto, a conexão com a API passou a ser
recusada em `192.168.99.5:16443`.

Isso **não** é falha de nenhuma aplicação. Reinício simultâneo de `coredns` e
`calico` não pode ser causado por uma aplicação: é **restart do runtime/kubelet**
(o MicroK8s foi reiniciado — muito provavelmente a VM foi suspensa junto com o Mac).

Duas assinaturas que identificam esse cenário:

| Assinatura | Por quê |
|---|---|
| `restartCount > 0` com `lastState` **vazio** | o status do container foi truncado junto com o runtime; um crash real deixaria `lastState.terminated.reason` |
| `startedAt` de **pods diferentes** concentrados no mesmo minuto | aplicações não combinam horário de restart entre si |

Como separar os dois casos:

```bash
# motivo real de um restart (útil quando é crash de verdade)
kubectl -n <ns> get pod <pod> \
  -o jsonpath='{range .status.containerStatuses[*]}{.lastState.terminated.reason} exit={.lastState.terminated.exitCode}{"\n"}{end}'

# houve pressão de recursos? (descarta OOM como causa)
kubectl get node <no> -o jsonpath='{range .status.conditions[*]}{.type}={.status}{"\n"}{end}'
kubectl get events -A --field-selector reason=Evicted
```

No caso ocorrido, o diagnóstico fechou com: nó `Ready=True`, sem `MemoryPressure`,
**zero** eventos `Evicted`, **zero** pods fora de `Running`. Ou seja, o cluster
estava saudável — houve restart do runtime, e nada mais. Depois de um restart
assim, **revalide** os recursos que dependem de estado (login OIDC, certificados).

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

## 10. Status: a refatoração B + C foi executada (2026-09-18)

> Esta seção era **"limitação conhecida + refatoração planejada"**. Agora é o
> registro do que foi feito.

### 10.1 A limitação que motivou a refatoração

A Opção B resolveu *"a raiz rotaciona"*, mas **não** resolveu *"alguém precisa
copiar"*. Ela apenas esticou o intervalo: de 90 dias para 10 anos.

Isso apareceu concretamente em `infrastructure/backstage/keycloak-ca.yaml`, onde
o certificado da CA estava **escrito dentro de um arquivo do Git**:

```yaml
data:
  ca.crt: |
    -----BEGIN CERTIFICATE-----
    MIIBbTCCARSgAwIBAgIUDdOuR3wbTTT+zzYbJSSXsz0RfaowCgYIKoZIzj0EAwIw
    ...
```

Por que isso era um cheiro, mesmo sendo material público:

| Problema | Detalhe |
|---|---|
| **O valor não é derivável do repo** | foi *gerado pelo cluster*. Quem clonar não reproduz o arquivo sem um cluster rodando |
| **Duplica a fonte da verdade** | a origem é o Secret `homelab-ca`; o repo passava a ter uma segunda cópia, que podia divergir |
| **Continua sendo sincronização manual** | a **natureza** do problema era a mesma da Opção A — só a frequência mudou |

Com um agravante que só ficou claro depois: o arquivo era um **manifesto `.yaml`
contendo um certificado**, num repositório cujo `.gitignore` já excluía `*.crt`,
`*.key` e `*.pem`. A política existia — o formato do arquivo apenas a contornava.

### A refatoração planejada: B + C

A Opção B **não será descartada** — ela é o **pré-requisito** da C.

A documentação do trust-manager alerta que apontar um `Bundle` **direto** para um
Secret do cert-manager faz a nova raiz substituir a antiga **imediatamente** na
rotação, destrustando certificados ainda em uso. A recomendação oficial é apontar
para uma **raiz estável** — exatamente o que a Opção B criou.

Além disso, o `Bundle` lê fontes `secret`/`configMap` do **namespace do
trust-manager** (`cert-manager`), e a CA já mora lá. A restrição vira encaixe.

A arquitetura final separa as duas responsabilidades:

| Camada | Quem resolve |
|---|---|
| raiz **estável** | Opção B (`Certificate homelab-ca`, 10 anos) |
| **distribuição** automática | Opção C (`Bundle` do trust-manager) |

Resultado: **nenhum hardcode, nenhuma cópia manual.**

### 10.2 O que foi feito

| # | Passo | Arquivo / objeto |
|---|---|---|
| 1 | Application do trust-manager no ArgoCD (ns `cert-manager`) | `infrastructure/trust-manager/app.yaml` |
| 2 | `Bundle` apontando para o Secret `homelab-ca` | bloco final de `infrastructure/cert-manager/ca.yaml` |
| 3 | `keycloak-ca.yaml` e `keycloak-ca-app.yaml` **apagados** | — |
| 4 | `extraVolumes` do Backstage apontando para `homelab-ca` | `infrastructure/backstage/app.yaml` |
| 5 | `ConfigMap keycloak-ca` órfão removido do cluster | `kubectl -n backstage delete configmap keycloak-ca` |

Evidências coletadas:

```console
$ kubectl get bundle homelab-ca
NAME         CONFIGMAP TARGET   SECRET TARGET   SYNCED   AGE
homelab-ca   ca.crt                                       1s

$ kubectl get bundle homelab-ca -o jsonpath='{.status.conditions[0].message}'
Successfully synced Bundle to all namespaces

# o ConfigMap derivado existe em TODOS os namespaces:
$ kubectl get configmap -A --field-selector metadata.name=homelab-ca | wc -l
16        # 1 cabeçalho + 15 namespaces

# impressão digital da CA distribuída == impressão digital da origem:
$ kubectl -n backstage get configmap homelab-ca -o jsonpath='{.data.ca\.crt}' \
  | openssl x509 -noout -subject -fingerprint -sha256
subject=CN=homelab-ca
sha256 Fingerprint=F9:B1:EE:DD:2F:8F:6D:E2:FF:AA:CF:5F:AD:A1:47:F0:8B:B2:44:00:36:BE:D6:1D:D9:C7:9B:80:27:24:EF:A3
```

E a prova de que o Pod passou a consumir essa CA — ver seções 7.3 e 7.3.1.

### 10.3 O que surpreendeu (e vale para a próxima vez)

**1. O `ConfigMap` é criado em TODOS os namespaces, por padrão.**
Com `namespaceSelector` vazio, o `Bundle` distribui para o cluster inteiro — não
só para `backstage`. São 15 namespaces aqui, incluindo `kube-system`. É o
comportamento desejado (qualquer Pod pode confiar na CA interna), mas tem duas
consequências: (a) existe um `ConfigMap` chamado `homelab-ca` em cada namespace,
então um nome de ConfigMap igual em outra aplicação colidiria; (b) uma mudança de
default do `namespaceSelector` numa versão futura do trust-manager alteraria isso
de uma vez — é um dos motivos de a versão estar **fixada** em `v0.25.0`.

**2. A ordem importa em dois níveis, e um deles estava invertido.**
O `Bundle` é um CRD que **vem do próprio trust-manager**: sem o CRD instalado, o
manifesto é recusado. E o trust-manager **depende do cert-manager** — ele usa um
`Certificate` do cert-manager para o TLS do seu webhook (confirmado:
`kubectl -n cert-manager get certificate` mostra `trust-manager`).

A ordem correta é, portanto:

```
cert-manager  ->  trust-manager  ->  Bundle (homelab-ca)
```

Mas as `sync-wave` estavam em `trust-manager: 3` e `cert-manager: 4` — invertidas.
Hoje isso é **inofensivo**, porque sem um "app of apps" as waves são apenas
documentais (o próprio `ca-app.yaml` já registra isso). Numa implantação de
cluster do zero, com app of apps, seria um erro real. As waves foram corrigidas
para refletir a dependência.

**3. `trust-manager` normaliza o PEM e remove o `\n` final.**
O arquivo distribuído tem 553 bytes contra 554 da origem. Comparar por `shasum`
acusa divergência onde não há diferença criptográfica — a comparação correta é por
impressão digital (detalhes e comandos na seção 7.3.2).

### 10.4 O que ficou pendente

| Pendência | Por quê |
|---|---|
| **Aplicar a Application `cert-manager-ca`** | o `ca-app.yaml` existe no repo mas **nunca foi aplicado** — a CA, o `ClusterIssuer` e o `Bundle` foram criados por `kubectl apply` direto. Como o `ca-app.yaml` aponta para `targetRevision: main`, ele só funciona **depois do merge** (mesma convenção de `backstage-certificate` e `backstage-ingress`) |
| **App of Apps** | é o que faz as `sync-wave` saírem do papel. Sem ele, o "botão único" continua sendo uma sequência manual de `kubectl apply` |
| **Migrar os outros hosts** | `backstage.local`, `argocd.local`, `kiali`, `jaeger` e `grafana` seguem no `selfsigned-issuer`. Passando para `homelab-ca-issuer`, os avisos de browser somem com **uma** CA importada no Keychain em vez de várias |

Nada disso invalida o que já foi feito: os passos são aditivos, não uma
reescrita.
