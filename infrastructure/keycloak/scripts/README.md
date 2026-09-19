# Keycloak Provisioner

Automação de provisionamento em massa no Keycloak: realms, clients, roles e usuários.

Lê a regra de negócio de um arquivo CSV ou XLSX e aplica no Keycloak de forma
idempotente (cria se não existir, atualiza se existir), com retry, paralelismo
controlado e dry-run.

## Estrutura

    scripts/
    ├── .venv/                 # venv local (gitignored)
    ├── .gitignore
    ├── Makefile
    ├── README.md
    ├── requirements.txt
    ├── data/
    │   ├── users.csv          # real (gitignored)
    │   └── users.example.csv  # exemplo versionado
    ├── src/
    │   ├── __init__.py
    │   ├── config.py
    │   ├── keycloak_client.py
    │   ├── provisioner.py
    │   └── cli.py
    └── tests/
        └── test_provisioner.py

## Formato do arquivo de usuários

CSV:

    username,email,firstName,lastName,role
    fulano.silva,fulano@example.com,Fulano,Silva,resilience-devs

XLSX: mesma estrutura de colunas, na primeira aba.

> ⚠️ O exemplo acima (e o arquivo `data/users.example.csv`) usa dados
> **fictícios**. Os dados reais ficam em `data/users.csv`, que é ignorado pelo
> Git — este repositório é público, e nome/e-mail de pessoa é dado pessoal.

Obrigatórias: username, email, role. Opcionais: firstName, lastName.

## Variáveis de ambiente

| Variável                 | Descrição                     | Exemplo                                              |
|--------------------------|-------------------------------|------------------------------------------------------|
| `KEYCLOAK_URL`           | URL base do Keycloak          | `https://keycloak.local`                             |
| `KEYCLOAK_ADMIN_USER`    | Usuário admin do realm master | `admin`                                              |
| `KEYCLOAK_ADMIN_PASS`    | Senha do admin                | `********`                                           |
| `KEYCLOAK_REALM`         | Realm a ser provisionado      | `resilience`                                         |
| `KEYCLOAK_CLIENT_ID`     | Client ID (ex: Backstage)     | `backstage`                                          |
| `KEYCLOAK_CLIENT_SECRET` | Client secret (confidential)  | `********`                                           |
| `KEYCLOAK_REDIRECT_URI`  | Redirect URI do client        | `https://backstage.local/api/auth/oidc/handler/frame` |
| `KEYCLOAK_WEB_ORIGIN`    | Web origin do client          | `https://backstage.local`                            |
| `REQUESTS_CA_BUNDLE`     | CA que assinou o TLS do Keycloak | `/tmp/homelab-ca.crt`                    |
| `KEYCLOAK_TEMP_PASSWORD` | Senha temporária dos usuários | `Mudar@123`                                          |

## Uso

### 1. Pré-requisitos

**a) O nome do Keycloak precisa resolver no seu Mac** (linha no `/etc/hosts`):

    grep keycloak.local /etc/hosts
    # esperado: 192.168.99.200  keycloak.local

> 💡 **Não é mais preciso `kubectl port-forward`.** O Keycloak tem Ingress em
> `https://keycloak.local`. Antes o túnel era obrigatório e caía com frequência
> (`lost connection to pod`), interrompendo o provisionamento no meio.

**b) O TLS é assinado pela CA interna do homelab — aponte o Python para ela.**

O provisioner usa a biblioteca `requests`, que **valida** o certificado por padrão.
O `keycloak.local` é emitido pelo `ClusterIssuer` **`homelab-ca-issuer`** (mudou na
Fase 11 — antes era `selfsigned-issuer`). A âncora de confiança, portanto, é a CA
`homelab-ca`, que vive no ns `cert-manager`:

    kubectl -n cert-manager get secret homelab-ca \
      -o jsonpath='{.data.tls\.crt}' | base64 -d > /tmp/homelab-ca.crt

    export REQUESTS_CA_BUNDLE=/tmp/homelab-ca.crt

> ⚠️ **Sem essa variável o erro será de SSL, não de credencial.** Se aparecer
> `SSLError: certificate verify failed`, é isto — não é senha errada nem script quebrado.

> ⚠️ **Extraia a CA, não o certificado folha.** Extrair `keycloak.local-tls` (a
> folha) *também* funciona — mas por **fixação exata**, não por validação de
> cadeia: o servidor apresenta exatamente aquele certificado, e ele está no trust
> store. A diferença aparece na **renovação**: a folha troca a cada ~90 dias e a
> cópia fixada fica velha, quebrando sem ninguém ter mexido em nada. A CA vale 10
> anos. Verificado: com a folha e com a CA, `HTTP 200`; com um certificado sem
> relação, `CERTIFICATE_VERIFY_FAILED`.
>
> Detalhes sobre certificados no laboratório: [`docs/certificados/`](../../../docs/certificados/).

### 2. Exportar as variáveis

    export KEYCLOAK_URL="https://keycloak.local"
    export KEYCLOAK_ADMIN_USER="admin"
    export KEYCLOAK_ADMIN_PASS="$(kubectl -n keycloak get secret keycloak-admin \
      -o jsonpath='{.data.admin-password}' | base64 -d)"
    export KEYCLOAK_REALM="resilience"
    export KEYCLOAK_CLIENT_ID="backstage"
    export KEYCLOAK_CLIENT_SECRET="$(openssl rand -hex 32)"
    export KEYCLOAK_REDIRECT_URI="https://backstage.local/api/auth/oidc/handler/frame"
    export KEYCLOAK_WEB_ORIGIN="https://backstage.local"
    export KEYCLOAK_TEMP_PASSWORD="Mudar@123"

> ⚠️ O Secret chama-se **`keycloak-admin`** (chave `admin-password`).
> Não existe Secret chamado `keycloak` — um comando com esse nome falha.

> ⚠️ **O `KEYCLOAK_CLIENT_SECRET` gerado aqui precisa chegar ao Keycloak** (é o que o
> `make run` faz, via `ensure_client`). Ele **muda** a cada `openssl rand` — grave-o
> no Secret do Backstage logo depois (ver seção Segurança).

> ⚠️ O `KEYCLOAK_REDIRECT_URI` precisa bater com o `baseUrl` real do Backstage.
> Hoje é `https://backstage.local`. Um valor de `localhost:3000` (padrão de
> desenvolvimento) **quebra** o login do Backstage.

### 3. Rodar

    cd scripts

    make dry-run                          # simula, sem alterar nada
    make run                              # aplica de verdade
    make run USERS=data/users.xlsx        # sobrescreve o arquivo (CSV/XLSX)
    make test                             # roda os testes
    make clean                            # destrói o venv

## Comportamento

- **Idempotente:** rodar várias vezes não duplica nada.
- **Paralelo:** usa `ThreadPoolExecutor` (default: 8 workers).
- **Retry:** 5 tentativas com backoff exponencial em 429/5xx/timeout.
- **Dry-run:** mostra o que seria feito sem tocar no Keycloak.
- **Roles dinâmicas:** as roles são extraídas do próprio CSV/XLSX.
- **Senha temporária:** usuários criados recebem senha temporária, que deve ser
  trocada no primeiro login.

## Segurança

- Nunca commitar data/users.csv nem data/users.xlsx (gitignored).
- Nunca commitar o KEYCLOAK_CLIENT_SECRET real.
- Para o Backstage consumir o secret:

      kubectl -n backstage create secret generic backstage-keycloak \
        --from-literal=KEYCLOAK_CLIENT_SECRET="$KEYCLOAK_CLIENT_SECRET"

## Próximos passos

- [ ] Remover usuários que saíram do CSV (comparação com o Keycloak).
- [ ] Ler direto de Google Sheets.
- [ ] Empacotar como imagem e rodar como `Job`/`CronJob` no Kubernetes.
- [ ] Exportar métricas (criados/atualizados/erros) para Prometheus.
