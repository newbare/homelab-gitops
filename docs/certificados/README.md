# Certificados TLS no homelab

Como os certificados são **gerados**, **instalados** e **diagnosticados** neste
laboratório. Cada comando vem com o porquê e a saída esperada.

**Última atualização:** 2026-09-18

---

## 🧩 Como funciona

Quem emite os certificados é o **cert-manager**, a partir de um `ClusterIssuer`:

```
infrastructure/cert-manager/cluster-issuer.yaml
```

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: selfsigned-issuer
spec:
  selfSigned: {}
```

> **`ClusterIssuer`** = emissor de escopo de cluster (vale para todos os namespaces).
> Um `Issuer` (sem "Cluster") valeria só no namespace dele.

O fluxo completo:

```
Certificate (ou annotation no Ingress)
        ↓
cert-manager emite o certificado
        ↓
grava num Secret do tipo kubernetes.io/tls
        ↓
o Ingress referencia esse Secret no bloco tls:
        ↓
o NGINX Ingress usa o certificado para terminar o HTTPS
```

---

## 📐 Os dois padrões usados neste repositório

### Padrão A — `Certificate` explícito

O manifesto do certificado fica no Git, e uma Application própria o aplica.

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: backstage-tls
  namespace: backstage
spec:
  secretName: backstage-tls
  issuerRef:
    name: selfsigned-issuer
    kind: ClusterIssuer
  dnsNames:
    - backstage.local
```

Exemplo real: [`infrastructure/backstage/certificate.yaml`](../../infrastructure/backstage/certificate.yaml),
aplicado pela Application `backstage-certificate`.

**Use este padrão** quando os manifestos são seus (Ingress escrito à mão).

### Padrão B — annotation no Ingress (chart gera o Ingress)

Quando um chart Helm cria o Ingress, não dá para escrever um `Certificate` junto —
mas o cert-manager consegue criá-lo **a partir do próprio Ingress**.

```yaml
ingress:
  enabled: true
  hostname: keycloak.local
  tls: true
  annotations:
    cert-manager.io/cluster-issuer: selfsigned-issuer
```

É o caso do Keycloak. O cert-manager (via *ingress-shim*) vê a annotation e o bloco
`tls:` do Ingress, cria o `Certificate` e popula o Secret.

> ⚠️ **Pegadinha do chart Bitnami:** o bloco `tls:` **só é gerado** se `tls: true`
> **E** existir uma destas três coisas: a annotation do cert-manager, `selfSigned: true`,
> ou `secrets` preenchido. Só `tls: true` **não basta** — e o Ingress sai sem TLS,
> silenciosamente.
>
> Confirmado no template do chart 24.4.0 (`templates/ingress.yaml`):
>
> ```
> {{- if or (and .Values.ingress.tls (or (include "common.ingress.certManagerRequest" ...) .Values.ingress.selfSigned .Values.ingress.secrets)) ... }}
> ```

### O nome do Secret

Nos dois padrões, o nome sai do **hostname** (com o chart, é o template que decide):

| Host | Secret de TLS |
|---|---|
| `backstage.local` | `backstage-tls` |
| `keycloak.local` | `keycloak.local-tls` |
| `argocd.local` | `argocd-tls` |

**Não adivinhe o nome** — confirme com o comando da seção de diagnóstico.

---

## ⚠️ Por que o navegador diz "Não seguro"

O `selfSigned` do cert-manager **não é uma CA**. Ele gera um certificado
**autoassinado e independente para cada `Certificate`**.

Consequência prática:

```
Certificate backstage-tls      → certificado A (autoassinado)
Certificate keycloak.local-tls → certificado B (autoassinado, SEM relação com A)

confiar em A  →  não faz B deixar de avisar
```

Foi por isso que, ao abrir `https://keycloak.local`, o aviso apareceu mesmo que o
Backstage já não avisasse.

### Como confirmar (verificado em 2026-09-18)

```bash
cd /tmp

kubectl -n backstage get secret backstage-tls \
  -o jsonpath='{.data.tls\.crt}' | base64 -d > backstage.crt

kubectl -n keycloak get secret keycloak.local-tls \
  -o jsonpath='{.data.tls\.crt}' | base64 -d > keycloak.crt

echo '=== 1) Cada um valida a si mesmo? ==='
openssl verify -CAfile backstage.crt backstage.crt
openssl verify -CAfile keycloak.crt keycloak.crt

echo
echo '=== 2) O cert do Backstage valida o do Keycloak? ==='
openssl verify -CAfile backstage.crt keycloak.crt

echo
echo '=== 3) Impressoes digitais ==='
openssl x509 -in backstage.crt -noout -fingerprint -sha256
openssl x509 -in keycloak.crt  -noout -fingerprint -sha256
```

**Saída real observada:**

```
=== 1) Cada um valida a si mesmo? ===
backstage.crt: OK
keycloak.crt: OK

=== 2) O cert do Backstage valida o do Keycloak? ===
error 18 at 0 depth lookup: self-signed certificate
error keycloak.crt: verification failed

=== 3) Impressoes digitais ===
sha256 Fingerprint=5F:BE:A6:4C:...:E3      (backstage)
sha256 Fingerprint=64:38:54:AB:...:E8      (keycloak)
```

**A leitura:** a seção **2** é a prova. Se o certificado do Backstage **não** valida o do
Keycloak, eles **não compartilham raiz de confiança** — cada um é sua própria autoridade.
É por isso que confiar num não elimina o aviso do outro.

> ⚠️ **Não use `openssl x509 -subject -issuer` para esta pergunta.** O cert-manager gera
> certificados com `subject` **vazio** (a identidade vai nos SANs, como os navegadores
> modernos exigem) — e, sendo autoassinado, o `issuer` também vem vazio. Os dois campos
> vazios **não provam nada**. Foi um comando que *parecia* certo mas não respondia à
> pergunta. Registro aqui porque é uma armadilha fácil de cair de novo.

> `base64 -d` é necessário porque o Kubernetes guarda dados de Secret codificados em base64.

---

## 🚀 Como publicar um serviço novo com TLS

### Se o Ingress é seu (Padrão A)

**1. Criar o `Certificate`** em `infrastructure/<app>/certificate.yaml`:

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: meuservico-tls
  namespace: meuservico
spec:
  secretName: meuservico-tls
  issuerRef:
    name: selfsigned-issuer
    kind: ClusterIssuer
  dnsNames:
    - meuservico.local
```

**2. Referenciar no Ingress:**

```yaml
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - meuservico.local
      secretName: meuservico-tls
  rules:
    - host: meuservico.local
      ...
```

**3. Criar a Application** que aplica esse arquivo (como `backstage-certificate`).

**4. Adicionar o host no `/etc/hosts` do Mac** (precisa de `sudo` — rode você):

```bash
echo "192.168.99.200  meuservico.local" | sudo tee -a /etc/hosts
```

> **Por que `tee` e não `>>`?** Com `sudo echo ... >> arquivo`, quem abre o arquivo é o
> seu shell (sem privilégio) e dá `Permission denied`. Com `sudo tee -a`, quem escreve
> é o `tee`, já como root.

### Se o Ingress vem de um chart (Padrão B)

Acrescente aos values:

```yaml
ingress:
  enabled: true
  ingressClassName: nginx
  hostname: meuservico.local
  tls: true
  annotations:
    cert-manager.io/cluster-issuer: selfsigned-issuer
```

E **valide o render antes de aplicar** (ver seção de diagnóstico).

> ⚠️ Se a Application for **baseada em chart**, o `git push` **não** aplica a mudança —
> é preciso `kubectl apply -f infrastructure/<app>/app.yaml`. Ver
> [`infrastructure/keycloak/README.md`](../../infrastructure/keycloak/README.md).

---

## 🔍 Diagnóstico

### Conferir se o certificado foi emitido

```bash
kubectl -n <namespace> get certificate
```

Saída esperada:

```
NAME                 READY   SECRET               AGE
keycloak.local-tls   True    keycloak.local-tls   2m16s
```

**`READY: True`** = emitido. Se aparecer `False`, o cert-manager não conseguiu emitir —
veja os eventos:

```bash
kubectl -n <namespace> describe certificate <nome>
```

### Conferir o Ingress

```bash
kubectl -n <namespace> get ingress
```

Saída esperada:

```
NAME       CLASS   HOSTS            ADDRESS          PORTS     AGE
keycloak   nginx   keycloak.local   192.168.99.200   80, 443   2m16s
```

`ADDRESS` preenchido = o NGINX Ingress assumiu o recurso.

### Conferir o Secret de TLS

```bash
kubectl -n <namespace> get secrets | grep tls
```

Esperado: um Secret do tipo `kubernetes.io/tls`, com **3 chaves**
(`tls.crt`, `tls.key`, `ca.crt`).

### Testar o HTTPS de fora

```bash
curl -k -s -o /dev/null -w 'HTTP %{http_code}\n' https://<host>/
```

O `-k` é necessário porque o certificado é autoassinado. `HTTP 200` = funcionando.

### Tabela de sintomas

| Sintoma | Causa provável | Verificar |
|---|---|---|
| Ingress sem bloco `tls:` | falta a annotation do cert-manager (Padrão B) | o template do chart / o `app.yaml` aplicado |
| `Certificate` não aparece | o cert-manager não viu o Ingress ou o Certificate | `kubectl get certificate -A` |
| `READY: False` | erro na emissão | `describe certificate` |
| Navegador: "Não seguro" | autoassinado — **esperado** | seção acima |
| `HTTP 000` no `curl` | nome não resolve, ou Ingress sem ADDRESS | `grep <host> /etc/hosts` |
| `SSLError: certificate verify failed` (Python) | `requests` validando cert autoassinado | exportar `REQUESTS_CA_BUNDLE` |
| Mudou o `app.yaml` e nada aconteceu | Application baseada em chart | `kubectl apply -f infrastructure/<app>/app.yaml` |

### Validar antes de aplicar (Padrão B)

```bash
helm template <release> <chart> --version <versao> \
  -f /tmp/valores.yaml \
  | sed -n '/^kind: Ingress/,/^---/p'
```

Renderiza localmente, **sem tocar no cluster**. Se o bloco `tls:` não aparecer aqui,
não vai aparecer no cluster tampouco.

---

## 🔐 Remover o aviso do navegador (opcional)

### Opção 1 — confiar no certificado, um por um

Serve para uso pessoal, mas **cada certificado novo exige repetir o processo** — por
causa do `selfSigned` independente.

```bash
kubectl -n <namespace> get secret <host>-tls \
  -o jsonpath='{.data.tls\.crt}' | base64 -d > /tmp/<host>.crt

sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain /tmp/<host>.crt
```

> `sudo` = **você executa**, no seu terminal. Nunca passe senha por chat.

### Opção 2 — ter uma CA própria (melhor caminho)

Cria-se **uma** autoridade certificadora no cluster e ela passa a assinar todos os
certificados. Aí basta confiar **uma vez** na CA, e todos os serviços param de avisar.

O caminho seria:

1. Criar um `ClusterIssuer` autoassinado "de bootstrap"
2. Emitir um `Certificate` de CA (`isCA: true`) → vira um Secret com a chave da CA
3. Criar um `ClusterIssuer` do tipo `ca`, apontando para esse Secret
4. Trocar os demais `issuerRef` para o novo Issuer
5. Confiar na CA no Keychain do Mac (uma vez)

> 📌 **Não implementado ainda.** Fica como melhoria do laboratório — e elimina os
> avisos de todos os serviços de uma vez, em vez de um a um.

---

## 🔗 Referências

- [cert-manager — SelfSigned Issuer](https://cert-manager.io/docs/configuration/selfsigned/)
- [cert-manager — CA Issuer](https://cert-manager.io/docs/configuration/ca/)
- [cert-manager — Annotated Ingress (ingress-shim)](https://cert-manager.io/docs/usage/ingress/)
- [NGINX Ingress — TLS](https://kubernetes.github.io/ingress-nginx/user-guide/tls/)
- [`infrastructure/cert-manager/cluster-issuer.yaml`](../../infrastructure/cert-manager/cluster-issuer.yaml)
- [`infrastructure/backstage/certificate.yaml`](../../infrastructure/backstage/certificate.yaml)
