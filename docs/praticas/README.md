# Práticas de trabalho — Git, CLI e verificação

> Este documento reúne os **padrões que usamos neste repositório**, com os
> comandos exatos e o motivo de cada um. Não é uma lista de "boas práticas
> genéricas": cada item existe porque **algo quebrou** ou porque evitou que
> quebrasse.
>
> Origem: sessão de 2026-09-18 (Fase 11 — login OIDC).

---

## 1. Git

### 1.1 Mensagens multi-linha com `-F` e heredoc

**Use isto** para qualquer mensagem com mais de uma linha:

```bash
git commit -F - <<'MSG_EOF'
feat(backstage): login OIDC via Keycloak no frontend e backend

Registra o provider OIDC no backend e cria o auth module do frontend,
substituindo a tela de login guest por uma com botão do Keycloak.

- backend: instala e registra @backstage/plugin-auth-backend-module-oidc-provider
- frontend: modules/auth com keycloakAuthApiRef (id auth.keycloak)

O provider.id passado a OAuth2.create precisa ser oidc — é o nome que o
backend registra; Keycloak é apenas o rótulo exibido.

Ref: https://backstage.io/docs/auth/oidc/
MSG_EOF
```

**Por que não `-m`:**

| Tentativa | Problema |
|---|---|
| `git commit -m 'texto com Let's Encrypt'` | o apóstrofo **fecha** a aspa simples e o shell quebra o comando |
| `-m 'linha 1' -m 'linha 2' -m 'linha 3'` | funciona, mas fica ilegível e não preserva parágrafos |
| `-F -` com heredoc `'MSG_EOF'` | ✅ aceita acentos, apóstrofos, backticks e parágrafos |

O delimitador **entre aspas simples** (`'MSG_EOF'`) é essencial: impede o shell
de expandir `$`, crases e variáveis dentro da mensagem.

### 1.2 Commits atômicos por assunto

Separe **código**, **documentação** e **infraestrutura**:

```
9f4e481  feat(backstage): login OIDC via Keycloak no frontend e backend
5960b51  docs(certificados): 3 opções de trust anchor interno
33bf07d  feat(cert-manager): CA interna homelab-ca e ClusterIssuer do tipo ca
```

**Por quê:** permite `git revert` isolado. Reverter o código não deve derrubar a
CA; reverter a documentação não deve mexer em infraestrutura.

### 1.3 `git status -sb` antes de commitar

```bash
git status -sb
```

Mostra a branch e os arquivos pendentes em uma linha cada. É a verificação que
pega o arquivo esquecido (`ca-app.yaml`) **antes** do commit, não depois.

---

## 2. Verificação de YAML (três camadas)

O caso mais perigoso são os `app.yaml` deste repo: eles são **Applications do
ArgoCD com os values do Helm embutidos como string**:

```yaml
spec:
  source:
    helm:
      values: |
        backstage:
          image:
            tag: v20
```

Para quem lê de fora, tudo dentro de `values: |` é **uma string**. Um erro de
indentação lá dentro passa por todos os validadores normais — só aparece quando o
ArgoCD for renderizar.

### Camada 1 — sintaxe e campos

```bash
kubectl apply --dry-run=client -f infrastructure/backstage/app.yaml
```

Valida YAML bem formado e nomes de campo. Rápido (~1s). **Não** valida schema de
CRD nem o YAML embutido.

### Camada 2 — schema real e webhook

```bash
kubectl apply --dry-run=server -f infrastructure/backstage/app.yaml
```

O `--dry-run=server` valida contra o **CRD real** e passa pelos **webhooks de
admissão** (ex.: o cert-manager valida o spec do `Certificate`). Nada é
persistido.

> A saída deve conter `(dry run)` em todas as linhas. Se aparecer algo **sem**
> `(dry run)`, algo foi aplicado de verdade — pare e verifique.

### Camada 3 — o YAML **embutido**

```bash
ruby -ryaml -e '
v = YAML.load(YAML.load_file("infrastructure/backstage/app.yaml")["spec"]["source"]["helm"]["values"])
puts "tag ......... #{v["backstage"]["image"]["tag"]}"
puts "providers ... #{v["backstage"]["appConfig"]["auth"]["providers"].keys}"
puts "resources ... #{v["keycloak"] rescue nil}"
'
```

Extrai a string de `values:`, parseia como YAML e imprime os pontos alterados.
**É a única camada que pega erro de indentação dentro do bloco.**

**Por que `ruby -ryaml`:** a biblioteca YAML (`psych`) é **stdlib** no macOS — não
precisa instalar nada. `python3` exigiria `PyYAML`, que normalmente não vem.

---

## 3. Verificação de comportamento

### 3.1 Controle negativo

**Todo teste precisa poder falhar.** Antes de concluir que um mecanismo funciona,
teste o caso que **deve** falhar:

```bash
# controle: SEM a CA -> DEVE falhar
node -e "fetch('https://keycloak.local/...').then(...).catch(...)"
#   -> FALHOU: DEPTH_ZERO_SELF_SIGNED_CERT

# experimento: COM a CA -> deve passar
NODE_EXTRA_CA_CERTS=/tmp/homelab-ca.crt node -e "fetch(...)"
#   -> HTTP 200
```

Se o controle **passasse**, o teste não estaria medindo nada e a conclusão seria
falsa.

#### 3.1.1 O controle que parece válido e não é

Um jeito de escrever esse controle que **não funciona** — e foi o que eu usei
primeiro, dentro do Pod:

```bash
# ❌ NÃO É CONTROLE VÁLIDO
kubectl -n backstage exec deploy/backstage -- node -e "
  process.env.NODE_EXTRA_CA_CERTS='';
  fetch('https://keycloak.local/...')..."
#   -> HTTP 200     (igual ao caso positivo: não prova nada)
```

A variável foi limpa **depois** que o processo já tinha subido. O Node lê
`NODE_EXTRA_CA_CERTS` **uma única vez, na inicialização**, e carrega o bundle no
trust store — limpar depois não desfaz a confiança já carregada.

O controle válido faz o processo **nascer** sem a variável:

```bash
# ✅ CONTROLE VÁLIDO
kubectl -n backstage exec deploy/backstage -- \
  env -u NODE_EXTRA_CA_CERTS node -e "fetch('https://keycloak.local/...')..."
#   -> como esperado, falhou: UNABLE_TO_VERIFY_LEAF_SIGNATURE
```

**Regra:** o controle tem de diferir do experimento **exatamente naquilo que se
quer testar**. Alterar o estado de um processo em execução mede outra coisa.

> O mesmo vale para qualquer valor consumido no boot: variável de ambiente
> (`NODE_OPTIONS`, `TZ`), arquivo lido uma vez, conexão aberta no start. Se o
> valor é lido na inicialização, o teste tem de ser em um **processo novo**.

### 3.2 Testar em vez de deduzir

Nesta sessão, uma hipótese tecnicamente plausível (`precisa ser CA:TRUE para
servir de âncora`) foi **refutada** por um teste de 2 segundos. Ler especificação
X.509 não substitui executar.

**Regra:** quando a resposta determina uma decisão de arquitetura, **teste**.

### 3.3 Verificar o que importa, não o que é fácil

Exemplo real: `kubectl get certificate` mostrava `READY: True` com `AGE: 150m`
**depois** de uma reemissão. O `AGE` é a idade do **objeto**, não do certificado
— o cert-manager atualiza o `Secret` no lugar.

A pergunta era "o certificado mudou?", e a resposta só veio da **cadeia**:

```bash
openssl verify -CAfile CA.crt folha.crt
```

Sinais que parecem provar e não provam: annotation no recurso, `READY: True`,
`AGE`. Prefira o que **responde à pergunta feita**.

### 3.4 A saída real, não o resumo

Ao documentar um comando, registre a **saída obtida** — não um "esperado"
hipotético. Foi assim que erros como o `memberOf` ficaram visíveis e
documentáveis.

---

## 4. `kubectl` — padrões úteis

### 4.1 Listar só as CHAVES de um Secret

```bash
kubectl -n backstage get secret backstage-keycloak \
  -o go-template='{{range $k,$v := .data}}{{$k}}{{"\n"}}{{end}}'
```

Itera o mapa `.data` e imprime **apenas os nomes** das chaves. Nunca expõe
valores — diferente de `-o yaml`, que mostra tudo em base64.

### 4.2 Criar segredo sem imprimir o valor

```bash
kubectl -n backstage create secret generic backstage-auth-session \
  --from-literal=AUTH_SESSION_SECRET="$(openssl rand -hex 32)" \
  --dry-run=client -o yaml | kubectl apply -f -
```

Gera e aplica **sem** o valor passar pela tela, pelo histórico do shell ou por
argumento de linha de comando (onde apareceria em `ps` para outros usuários).

> ⚠️ Rodar de novo **rotaciona** o valor. É para rodar uma vez.

### 4.3 Esperar um rollout de forma explícita

```bash
kubectl -n backstage rollout status deploy/backstage --timeout=300s
```

Bloqueia até concluir e reporta. Melhor que consultar `get pods` repetidamente:
uma espera declarativa em vez de polling manual.

### 4.4 Ler o ConfigMap ativo, não o arquivo do repo

```bash
kubectl -n backstage get configmap backstage-app-config \
  -o jsonpath='{.data.app-config\.yaml}'
```

Neste repo isso **não** é redundante: o chart do Backstage sobrescreve o `CMD` e
só carrega o ConfigMap gerado do `appConfig`. O que está no repo **não** é
necessariamente o que o processo lê.

### 4.5 Verificar o SPEC resultante, não só o rollout

Quando quem aplica a mudança é um **controller** (ArgoCD, operator), o
`kubectl apply` não muda nada de imediato — e `rollout status` pode devolver
sucesso **do estado antigo**:

```bash
kubectl apply -f infrastructure/backstage/app.yaml    # edita a Application
kubectl -n backstage rollout status deploy/backstage  # ✅ "successfully rolled out"
                                                      #    ...do Deployment ANTIGO
```

`rollout status` responde *"a revisão atual terminou?"*, não *"a mudança chegou?"*.
A verificação que responde à pergunta certa olha o **spec**:

```bash
kubectl -n backstage get deploy backstage \
  -o jsonpath='{range .spec.template.spec.volumes[*]}{.name}{"  "}{end}{"\n"}'
```

Se o valor esperado não estiver lá, o sync ainda não aconteceu — **não é falha**.

Para forçar o sync, em vez de esperar o ciclo do controller:

```bash
kubectl -n argocd patch application backstage --type merge -p '{"operation":{"sync":{}}}'
```

### 4.6 "Tudo reiniciou junto" ≠ "as aplicações quebraram"

Caso real: a conexão com a API passou a ser **recusada** em `…:16443` e, quando
voltou, vários pods exibiam `restartCount` novo. Parecia pane geral.

Dois sinais identificam **restart do runtime/kubelet** em vez de crash:

| Sinal | Por quê |
|---|---|
| `restartCount > 0` com `lastState` **vazio** | o status do container foi truncado junto com o runtime. Crash de verdade deixa `lastState.terminated.reason` |
| `startedAt` de pods **não relacionados** no mesmo minuto | aplicações não combinam horário de restart entre si |

O teste decisivo é comparar o horário de partida de pods de namespaces
diferentes:

```bash
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"/"}{.metadata.name}{"  "}{.status.containerStatuses[*].state.running.startedAt}{"\n"}{end}'
```

Se `coredns`, `calico`, `metallb` e `argocd` reiniciaram todos dentro de ~1
minuto, a causa é o runtime — nenhuma aplicação derruba as outras.

Para **descartar** pressão de recursos como causa:

```bash
kubectl get node <no> -o jsonpath='{range .status.conditions[*]}{.type}={.status}{"\n"}{end}'
kubectl get events -A --field-selector reason=Evicted
```

**Depois de um restart assim, revalide o que depende de estado** — login,
certificados, sessões. O cluster pode estar saudável e algo ter ficado
inconsistente.

---

## 5. `openssl`

### 5.1 `-servername` é obrigatório

```bash
echo | openssl s_client -connect host:443 -servername host 2>/dev/null \
  | openssl x509 -noout -text
```

Sem `-servername` (SNI), o servidor devolve o certificado **default** — e a
resposta é enganosa. Num cluster com vários hosts no mesmo Ingress, isso dá
falso resultado.

### 5.2 `-subject -issuer` não serve para cert-manager

```bash
# ❌ não responde
openssl x509 -in cert.crt -noout -subject -issuer
```

Certificados do cert-manager têm `subject` **vazio** (a identidade vai nos SANs,
como os navegadores modernos exigem). Para uma **folha**, o `issuer` também vem
vazio.

```bash
# ✅ responde
openssl x509 -in cert.crt -noout -text | grep -A 1 'Basic Constraints'
openssl verify -CAfile CA.crt folha.crt
```

> Curiosidade útil: numa **CA** o `subject` **vem preenchido** (`CN=homelab-ca`),
> porque não há SAN a preencher. O mesmo comando dá resultados diferentes porque
> são **tipos** de certificado diferentes.

### 5.3 Hash de arquivo ≠ impressão digital

Dois PEM do **mesmo** certificado podem ter hashes diferentes. Caso real: a CA no
`Secret` de origem contra a mesma CA no `ConfigMap` distribuído pelo trust-manager.

```console
$ kubectl -n cert-manager get secret homelab-ca -o jsonpath='{.data.tls\.crt}' \
  | base64 -d | shasum -a 256
fd4c50543c15d2b1d9926a2df11823a0d4f83643d23ef4750ff21ffce93bebb0

$ kubectl -n backstage get configmap homelab-ca -o jsonpath='{.data.ca\.crt}' \
  | shasum -a 256
3939c68270183205eb412f37faaefd1d329b52f64f8f5f3dc3b5cdf9f6c22de4
```

Hashes diferentes — e são o **mesmo certificado**. O trust-manager normaliza o
PEM e remove o `\n` final (554 bytes contra 553). O `diff` escancara:

```
10c10
< -----END CERTIFICATE-----
---
> -----END CERTIFICATE-----
\ No newline at end of file
```

**Regra:** para comparar **identidade** de certificado, use **impressão digital**;
`shasum` compara *bytes*, não *significado*.

```bash
# ✅ compara IDENTIDADE
openssl x509 -noout -fingerprint -sha256 < arquivo.crt

# ⚠️ compara BYTES — pode acusar diferença onde não há diferença criptográfica
shasum -a 256 arquivo.crt
```

### 5.4 No macOS, `curl` NÃO serve para testar confiança TLS

O `curl` que vem no macOS é compilado com **SecureTransport** e valida contra o
**Keychain** — não contra o que se passa em `--cacert`:

```console
$ curl -V | head -1
curl 8.7.1 (x86_64-apple-darwin25.0) libcurl/8.7.1 (SecureTransport) LibreSSL/3.3.6 …
                                              ^^^^^^^^^^^^^^^
```

Prova — o controle que **deveria** falhar, e não falha:

```console
$ curl --cacert /tmp/nao-tem-relacao.crt -s -o /dev/null -w 'HTTP %{http_code}\n' \
    https://keycloak.local/realms/resilience/.well-known/openid-configuration
HTTP 200
```

Um certificado **sem relação alguma** com o servidor, usado como CA bundle, e
ainda assim `HTTP 200`: o `--cacert` foi **ignorado**.

Consequência: num teste com `curl` no macOS, um "passou" **não** significa que o
cluster confia em quem você pensa. Pode estar passando pelo Keychain da sua
máquina — inclusive porque a CA do laboratório pode estar **importada ali**.

O mesmo teste com o `ssl` do Python, que **honra** o `cafile`:

```python
import ssl, urllib.request
ctx = ssl.create_default_context(cafile="/tmp/homelab-ca.crt")
urllib.request.urlopen("https://keycloak.local/…", context=ctx)
```

```console
/tmp/nao-tem-relacao.crt -> FALHOU: unable to get local issuer certificate
/tmp/leaf.crt            -> HTTP 200
/tmp/homelab-ca.crt      -> HTTP 200
```

Aqui o controle negativo **falha como deve** — e é isso que dá valor ao `HTTP 200`
dos outros dois.

> **Sem controle que deva falhar, "passou" não prova nada.** Se o controle passar,
> o teste está medindo outra coisa (neste caso: o Keychain do Mac, não a âncora
> de confiança do cluster).

---

## 6. YAML — armadilhas

### 6.1 Chave duplicada não dá erro

```yaml
resources:
  requests: { cpu: 200m }

# ... 40 linhas depois ...

resources:
  requests: { cpu: 250m }   # <- esta VENCE
```

YAML permite chaves duplicadas: **a última vence, silenciosamente**. Aconteceu
neste repo ao adicionar `resources` ao `app.yaml` do Keycloak sem ler o arquivo
inteiro.

**Prevenção:** antes de inserir um bloco, **leia o arquivo todo** e confirme que
a chave não existe:

```bash
grep -c '^        resources:' infrastructure/keycloak/app.yaml   # esperado: 1
```

### 6.2 Antes de sobrescrever um arquivo **untracked**

Compare a **cobertura de conteúdo**, não só a estrutura. Estrutura responde "um
é subconjunto do outro?"; cobertura responde "**perco informação?**". Fazer a
segunda pergunta **antes** de escrever.

---

## 7. Expressões de fluxo lógico

Quando o conflito é branco-e-preto, deixe explícito:

$$ \text{Bloqueia} \;\equiv\; \text{HTTP } 000 \;\wedge\; \text{\texttt{curl -k} também falha} $$

```bash
curl -k -s -o /dev/null -w '%{http_code}\n' https://host/   # testa DISPONIBILIDADE
curl    -s -o /dev/null -w '%{http_code}\n' https://host/   # testa CONFIANÇA TLS
```

Sem o `-k`, um erro de certificado aparece como `000` — e pode ser confundido com
o serviço fora do ar. São **duas perguntas diferentes**:
*está no ar?* e *eu confio nele?*

> ⚠️ **No macOS, a segunda linha testa o Keychain da sua máquina, não o cluster.**
> O `curl` de lá usa SecureTransport e **ignora** `--cacert`. Para confiança TLS,
> use o `ssl` do Python — ver seção 5.4.

---

## 8. Disciplina de alteração

1. **Ler antes de editar** — o arquivo inteiro, não o trecho.
2. **Validar antes de aplicar** — as três camadas da seção 2.
3. **Aplicar uma coisa por vez** — e verificar o efeito.
4. **Um passo que muda comportamento merece pré-voo**: confirme que todos os
   recursos referenciados existem (um nome errado em `Secret`/`ConfigMap` não
   degrada — **derruba** o Pod).
5. **Documentar comando + porquê + saída esperada** — não basta entregar
   funcionando.
