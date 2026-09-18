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
    jefferson.leite,jefferson@resiliencecloud.com.br,Jefferson,Leite,resilience-admins

XLSX: mesma estrutura de colunas, na primeira aba.

Obrigatórias: username, email, role. Opcionais: firstName, lastName.

## Variáveis de ambiente

| Variável                 | Descrição                     | Exemplo                                              |
|--------------------------|-------------------------------|------------------------------------------------------|
| `KEYCLOAK_URL`           | URL base do Keycloak          | `http://localhost:8080`                              |
| `KEYCLOAK_ADMIN_USER`    | Usuário admin do realm master | `admin`                                              |
| `KEYCLOAK_ADMIN_PASS`    | Senha do admin                | `********`                                           |
| `KEYCLOAK_REALM`         | Realm a ser provisionado      | `resilience`                                         |
| `KEYCLOAK_CLIENT_ID`     | Client ID (ex: Backstage)     | `backstage`                                          |
| `KEYCLOAK_CLIENT_SECRET` | Client secret (confidential)  | `********`                                           |
| `KEYCLOAK_REDIRECT_URI`  | Redirect URI do client        | `http://localhost:3000/api/auth/oidc/handler/frame`  |
| `KEYCLOAK_WEB_ORIGIN`    | Web origin do client          | `http://localhost:3000`                              |
| `KEYCLOAK_TEMP_PASSWORD` | Senha temporária dos usuários | `Mudar@123`                                          |

## Uso

### 1. Port-forward do Keycloak (pré-requisito)

O Keycloak **não tem Ingress** — é acessível apenas de dentro do cluster. Para rodar
o provisioner a partir da sua máquina, exponha o Service localmente:

    kubectl -n keycloak port-forward svc/keycloak 8080:80

Deixe esse terminal aberto e use outro para os próximos passos.

### 2. Exportar as variáveis

    export KEYCLOAK_URL="http://localhost:8080"
    export KEYCLOAK_ADMIN_USER="admin"
    export KEYCLOAK_ADMIN_PASS="$(kubectl -n keycloak get secret keycloak-admin \
      -o jsonpath='{.data.admin-password}' | base64 -d)"
    export KEYCLOAK_REALM="resilience"
    export KEYCLOAK_CLIENT_ID="backstage"
    export KEYCLOAK_CLIENT_SECRET="$(openssl rand -hex 32)"
    export KEYCLOAK_REDIRECT_URI="http://localhost:3000/api/auth/oidc/handler/frame"
    export KEYCLOAK_WEB_ORIGIN="http://localhost:3000"
    export KEYCLOAK_TEMP_PASSWORD="Mudar@123"

> ⚠️ O Secret chama-se **`keycloak-admin`** (chave `admin-password`).
> Não existe Secret chamado `keycloak` — um comando com esse nome falha.

> 💡 Guarde o `KEYCLOAK_CLIENT_SECRET` gerado: ele será usado pelo Backstage.
> Note que ele **muda** a cada execução do `openssl rand` — guarde o valor que
> foi realmente aplicado.

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
