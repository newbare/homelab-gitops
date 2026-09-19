# `generate-catalog.py` — usuários do catálogo do Backstage

Gera o ConfigMap `backstage-catalog-users`, que materializa no catálogo do
Backstage um `Group` por role e um `User` por pessoa.

---

## O fluxo, de ponta a ponta

```
   ┌────────────────────────────────────────────────────────────────────┐
   │  FORA DO GIT — infrastructure/keycloak/scripts/data/users.csv      │
   │  (regra `data/users.csv` no .gitignore)                            │
   │                                                                    │
   │   username,email,firstName,lastName,role                           │
   │   fulano.silva,fulano@dominio,Fulano,Silva,role-x                  │
   └───────────────────────────────┬────────────────────────────────────┘
                                   │
                 UMA fonte ────────┴─────── dois consumidores
                                   │
        ┌──────────────────────────┴──────────────────────────┐
        │                                                     │
        ▼                                                     ▼
 ┌────────────────────┐                       ┌─────────────────────────┐
 │ Keycloak           │                       │ generate-catalog.py     │
 │ provisioner Python │                       │ Python, stdlib, sem venv│
 │ → Admin API        │                       │ → YAML no stdout        │
 └─────────┬──────────┘                       └────────────┬────────────┘
           │                                             │
           │                                             │ pipe
           ▼                                             ▼
 ┌────────────────────┐                       ┌─────────────────────────┐
 │ realm resilience   │                       │ kubectl apply -f -      │
 │ 4 users, 3 roles   │                       │ (nada escrito no disco) │
 └─────────┬──────────┘                       └────────────┬────────────┘
           │                                             ▼
           │                             ┌──────────────────────────────┐
           │                             │ ConfigMap                    │
           │                             │ backstage-catalog-users      │
           │                             │  users.yaml = 3 Group+4 User │
           │                             └───────────────┬──────────────┘
           │                                             │ volume
           │                                             ▼
           │                              /etc/backstage-catalog/users.yaml
           │                                             │
           │  login OIDC                                 │
           ▼                                             ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │  Backstage                                                          │
 │   1. usuário clica "Entrar com Keycloak"                            │
 │   2. Keycloak devolve o e-mail no token                             │
 │   3. resolver:  profile.email.split('@')[0]  →  "fulano"            │
 │   4. acha  user:default/fulano  no catálogo  →  entra               │
 └─────────────────────────────────────────────────────────────────────┘
```

O resumo em quatro decisões — cada uma detalhada na sua seção:

| Decisão | Por quê | Seção |
|---|---|---|
| **Uma fonte, dois consumidores** | duas listas podiam divergir — o usuário existir no Keycloak e não conseguir logar | §2 |
| **Gerador em vez de manifesto** | o que se versiona é o *programa*; o dado entra só na execução | §1, §4 |
| **Pipe em vez de arquivo temporário** | o YAML com dado pessoal **nunca toca o disco** | §3 |
| **Derivação verificada na fonte** | o nome da entidade é a parte local do e-mail, e tem formato obrigatório | §4, §5.2 |

⚠️ O preço está na §7: este é o **único passo do fluxo que não é puramente
GitOps**, e é uma escolha consciente.

---

## 1. Por que este script existe

O Backstage precisa de entidades `User` e `Group` no catálogo por dois motivos:

**(a) O login depende disso.** O resolver de sign-in configurado
(`emailLocalPartMatchingUserEntityName`) resolve a identidade procurando a
entidade `User` cujo `metadata.name` é a **parte local do e-mail**. O código real
(`@backstage/plugin-auth-node/dist/sign-in/commonSignInResolvers.cjs.js`) é:

```js
const [localPart] = profile.email.split("@");
...
return ctx.signInWithCatalogUser({ entityRef: { name: localPart } }, {...});
```

Sem a entidade, ele lança `NotFoundError` e **o login falha**.

**(b) Ownership e RBAC.** Entidades de `Component` apontam para `owner`, e
`owner` referencia `User`/`Group`. Os grupos abaixo ainda **não concedem
permissão nenhuma** — política de permissões é assunto da fase de RBAC.

---

## 2. Por que os usuários NÃO estão no Git

Este repositório é **público**. Nome e e-mail de pessoas são dados pessoais, e
dado pessoal não se versiona — nem em manifesto, nem "só como exemplo".

A fonte de verdade é o **mesmo `users.csv`** que já provisiona os usuários no
Keycloak, e esse arquivo é ignorado pelo Git:

```console
$ git check-ignore -v infrastructure/keycloak/scripts/data/users.csv
infrastructure/keycloak/scripts/.gitignore:4:data/users.csv   infrastructure/...
```

A consequência conceitual é a separação de camadas:

| camada | o que é | onde vive | como é aplicado |
|---|---|---|---|
| **infraestrutura** | estado desejado | Git (versionado) | ArgoCD, declarativo |
| **usuários** | dados | `users.csv` (fora do Git) | provisionado, imperativo |

Ou seja: **um `User` no catálogo é dado provisionado, não infraestrutura
versionada.** É exatamente o mesmo tratamento que já se dá aos usuários do
Keycloak.

---

## 3. Uso

Ver o que seria aplicado (não altera nada):

```bash
python3 infrastructure/backstage/scripts/generate-catalog.py
```

Aplicar no cluster (idempotente):

```bash
python3 infrastructure/backstage/scripts/generate-catalog.py | kubectl apply -f -
```

Usar outro CSV:

```bash
python3 infrastructure/backstage/scripts/generate-catalog.py --users caminho/usuarios.csv
```

O diagnóstico (`N usuários, M grupos`) vai para **stderr** e o YAML para
**stdout**, justamente para a canalização acima funcionar sem poluir o
manifesto.

### Por que uma pipe e não um arquivo temporário

`kubectl apply -f -` lê o manifesto do stdin. Assim o YAML com dados pessoais
**nunca é escrito no disco**: não há arquivo a esquecer de ignorar, nem resíduo
em `/tmp`, nem chance de um `git add .` acidental.

O script usa **somente a biblioteca padrão do Python 3** — sem venv, sem
`pip install`, sem `requirements.txt`. Roda com o `python3` do sistema.

---

## 4. De onde vem cada campo (verificado na fonte, não presumido)

O CSV de origem tem as colunas `username,email,firstName,lastName,role`. O
`username` **não** é usado: o Backstage resolve pelo e-mail.

| campo do catálogo | derivado de | regra |
|---|---|---|
| `User.metadata.name` | `email` | parte antes do `@` — é o que o resolver usa |
| `User.spec.profile.displayName` | `firstName` + `lastName` | concatenados |
| `User.spec.profile.email` | `email` | direto |
| `User.spec.memberOf` | `role` | um elemento |
| `Group.metadata.name` | `role` | um grupo por role distinta |

Exemplo com `users.example.csv` (dados fictícios):

```
username,email,firstName,lastName,role
fulano.silva,fulano@example.com,Fulano,Silva,resilience-devs
beltrano.souza,beltrano@example.com,Beltrano,Souza,resilience-viewers
```

produz:

```yaml
data:
  users.yaml: |
    apiVersion: backstage.io/v1alpha1
    kind: Group
    metadata:
      name: "resilience-devs"
      description: "Grupo derivado da role resilience-devs no Keycloak"
    spec:
      type: team
      children: []
    ---
    apiVersion: backstage.io/v1alpha1
    kind: User
    metadata:
      name: "fulano"
    spec:
      profile:
        displayName: "Fulano Silva"
        email: "fulano@example.com"
      memberOf: ["resilience-devs"]
```

Repare: o `username` (`fulano.silva`) **não** vira nome de entidade — quem vira
é a parte local do e-mail (`fulano`).

---

## 5. Duas lições de schema que este script passou a validar

### 5.1 `spec.memberOf` é obrigatório

O schema de `kind: User` do Backstage **exige** `spec.memberOf`. Uma versão
anterior deste catálogo saiu com quatro `User` sem esse campo, e o catálogo
rejeitou todos:

```
Processor BuiltinKindsEntityProcessor threw an error while validating the
entity user:default/<nome>; caused by TypeError: /spec must have required
property 'memberOf' - missingProperty: memberOf
```

**O sintoma era invisível em qualquer `kubectl get`.** As entidades simplesmente
não entravam no catálogo, e o login falhava mais tarde com `NotFoundError` —
parecendo problema de resolver ou de client secret. Foi `kubectl logs | grep -i
error` que revelou.

Hoje o script **falha antes**, com mensagem explícita, se uma linha do CSV vier
sem `role`.

### 5.2 O nome da entidade tem formato obrigatório

O nome não é livre. A validação vem de
`@backstage/catalog-model/dist/validation/KubernetesValidatorFunctions.cjs.js`:

```js
static isValidObjectName(value) {
  return typeof value === "string" && value.length >= 1 && value.length <= 63
    && /^([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9]$/.test(value);
}
```

Como o nome é derivado do e-mail, um endereço com sufixo `+`
(`fulano+teste@dominio`) produziria `fulano+teste` — **inválido**. O script
detecta e aborta com explicação, em vez de deixar o catálogo rejeitar em silêncio:

```console
$ python3 infrastructure/backstage/scripts/generate-catalog.py --users /tmp/bad-users.csv
ERRO: o e-mail 'fulano+teste@example.com' gera o nome de entidade 'fulano+teste',
que o Backstage REJEITA.
       O nome precisa casar com /^([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9]$/ e
       ter 1 a 63 caracteres.
       Causa provável: o endereço tem sufixo `+` ou a parte local começa/termina
       com '-'.
```

---

## 6. Ordem de provisionamento

O volume `catalog-users` do Deployment é **obrigatório** (`optional` não está
definido). Logo, se o ConfigMap não existir, o Pod **não sobe**.

Não é suposição — foi verificado com um Pod de teste montando um ConfigMap
inexistente:

```console
$ kubectl -n backstage get pod probe-missing-cm
NAME               READY   STATUS              RESTARTS   AGE
probe-missing-cm   0/1     ContainerCreating   0          1s

$ kubectl -n backstage describe pod probe-missing-cm | sed -n '/Events:/,$p'
Events:
  Type     Reason       Age   From               Message
  ----     ------       ----  ----               ------
  Warning  FailedMount  0s    kubelet            MountVolume.SetUp failed for
           volume "x" : configmap "nao-existe-mesmo" not found
```

O Pod fica preso em `ContainerCreating` indefinidamente.

**Isso é intencional e preferível.** Um Pod que não sobe aponta o problema na
hora. A alternativa (`optional: true`) faria o Backstage subir normalmente e
**falhar só no login**, de forma silenciosa e difícil de rastrear.

Portanto, em cluster novo:

> **provisione os usuários antes de tentar logar.**

O Keycloak e o próprio Backstage sobem normalmente; o que não funciona sem este
passo é o login de pessoas.

---

## 7. O trade-off: este é o único passo que não é puramente GitOps

Vale ser explícito, porque contraria o princípio de "um botão que implanta toda
a infraestrutura".

Os dados pessoais vêm de uma fonte fora do Git, então um cluster novo precisa de
**um comando a mais** além do ArgoCD. As três saídas possíveis:

| opção | como funciona | custo |
|---|---|---|
| **A — gerar do CSV** *(escolhida)* | script lê `users.csv` (fora do Git) e aplica | um comando manual a mais no bootstrap |
| **B — criptografar no Git** | `sops`/`sealed-secrets`: o YAML fica no repositório **cifrado**, e um controlador decifra no cluster | exige controlador/plugin + gerência de chave; ainda assim há um artefato versionado |
| **C — dispensar o catálogo** | `dangerouslyAllowSignInWithoutUserInCatalog: true` no resolver — login funciona sem entidade | perde-se `User`/`Group` no catálogo, portanto ownership e RBAC |

Sobre a **opção C**: a flag existe de fato. Na mesma fonte do resolver:

```js
dangerousEntityRefFallback: options?.dangerouslyAllowSignInWithoutUserInCatalog
  ? { entityRef: { name: localPart } } : void 0
```

Ela faria o login funcionar sem o catálogo — mas o nome começa com
"dangerously" por um motivo: não haveria entidade para atribuir `owner` nem para
a política de permissões consultar. Foi descartada, e a opção A é a que mantém
as entidades no catálogo sem colocar dado pessoal no Git.

A opção B continua disponível como evolução, caso o objetivo passe a ser
"bootstrap 100% declarativo, sem passo manual".

---

## 8. O que este script NÃO faz

- **Não** cria usuários no Keycloak — isso é o provisioner em
  `infrastructure/keycloak/scripts/`.
- **Não** define permissões. Os `Group` existem para satisfazer o schema e
  espelhar as roles do Keycloak; a política de permissões é da fase de RBAC.
- **Não** é aplicado pelo ArgoCD, por definição (é o ponto da seção 7).

Uma consequência a observar: como o Keycloak e este catálogo leem **o mesmo
CSV**, não há duas listas para manter em sincronia — era uma fonte de bug
conhecida (usuário existir no Keycloak e não conseguir logar no Backstage).
