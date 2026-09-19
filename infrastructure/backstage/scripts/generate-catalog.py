#!/usr/bin/env python3
"""
Gera o ConfigMap `backstage-catalog-users` para o catálogo do Backstage.

===============================================================================
POR QUE ISTO EXISTE
===============================================================================
O Backstage precisa de entidades `User` e `Group` no catálogo para:

  1. o resolver de sign-in do OIDC encontrar o usuário. O resolver configurado
     (`emailLocalPartMatchingUserEntityName`) faz, literalmente:

         const [localPart] = profile.email.split("@");
         return ctx.signInWithCatalogUser({ entityRef: { name: localPart } });

     ou seja, o `metadata.name` da entidade `User` É a parte local do e-mail.
     Sem a entidade, o login falha com NotFoundError.

  2. ownership e RBAC funcionarem (assunto da fase de permissões).

===============================================================================
POR QUE GERADO E NÃO VERSIONADO
===============================================================================
Este repositório é PÚBLICO. Nome e e-mail de pessoas são dados pessoais e não
podem entrar em arquivo versionado.

A fonte de verdade é o MESMO `users.csv` que já provisiona os usuários no
Keycloak — e esse arquivo é ignorado pelo Git (ver
`infrastructure/keycloak/scripts/.gitignore`, regra `data/users.csv`).

Logo, os usuários são DADOS PROVISIONADOS, não INFRAESTRUTURA VERSIONADA:

    infraestrutura = estado    (ArgoCD, versionado, declarativo)
    usuários       = dados     (users.csv, fora do Git, provisionado)

O manifesto é GERADO no momento do provisionamento e vai direto para o cluster.

===============================================================================
USO
===============================================================================
Ver o YAML que seria aplicado (não altera nada):

    python3 infrastructure/backstage/scripts/generate-catalog.py

Usar outro CSV:

    python3 infrastructure/backstage/scripts/generate-catalog.py --users caminho/usuarios.csv

Aplicar no cluster (idempotente):

    python3 infrastructure/backstage/scripts/generate-catalog.py \\
      | kubectl apply -f -

===============================================================================
POR QUE UMA PIPE E NÃO UM ARQUIVO TEMPORÁRIO
===============================================================================
`kubectl apply -f -` lê o manifesto do stdin. Assim o YAML com dados pessoais
NUNCA é escrito no disco: não há arquivo a esquecer de ignorar, nem resíduo em
/tmp, nem chance de um `git add .` acidental.

===============================================================================
DEPENDÊNCIAS
===============================================================================
Somente a biblioteca padrão do Python 3 — de propósito. Não exige venv, pip,
nem `requirements.txt`; roda com o `python3` do sistema.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

# Nome do ConfigMap e chave dentro dele. Precisam casar com o que o
# `infrastructure/backstage/app.yaml` monta em /etc/backstage-catalog/ e aponta
# em `appConfig.catalog.locations[].target`.
CONFIGMAP_NAME = "backstage-catalog-users"
CONFIGMAP_NAMESPACE = "backstage"
CONFIGMAP_KEY = "users.yaml"

# Caminho padrão: a MESMA fonte que provisiona o Keycloak.
#   __file__ = infrastructure/backstage/scripts/generate-catalog.py
#   parents[0] = scripts | parents[1] = backstage | parents[2] = infrastructure
DEFAULT_USERS_CSV = (
    Path(__file__).resolve().parents[2] / "keycloak" / "scripts" / "data" / "users.csv"
)

# Colunas obrigatórias no CSV.
REQUIRED_COLUMNS = ("email", "firstName", "lastName", "role")

# ---------------------------------------------------------------------------
# Validação de nome de entidade — copiada da fonte, NÃO inventada.
#
# `@backstage/catalog-model/dist/validation/KubernetesValidatorFunctions.cjs.js`:
#
#     static isValidObjectName(value) {
#       return typeof value === "string" && value.length >= 1
#         && value.length <= 63
#         && /^([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9]$/.test(value);
#     }
#
# Como o nome da entidade é derivado do e-mail, um endereço com `+` (por
# exemplo `fulano+teste@dominio`) produziria um nome INVÁLIDO e a entidade
# seria rejeitada pelo catálogo. Melhor falhar aqui, com mensagem clara, do que
# descobrir em log de Pod.
# ---------------------------------------------------------------------------
ENTITY_NAME_RE = re.compile(r"^([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9]$")


def yaml_quote(value: str) -> str:
    """Aspas duplas YAML, com escape de `\\` e `"`."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def entity_name_for(email: str) -> str:
    """Deriva o `metadata.name` da entidade a partir do e-mail.

    Espelha EXATAMENTE o que o resolver do Backstage faz — a parte local:

        profile.email.split("@")[0]
    """
    return email.split("@", 1)[0].strip()


def validate_entity_name(name: str, email: str) -> None:
    if not (1 <= len(name) <= 63) or not ENTITY_NAME_RE.match(name):
        raise SystemExit(
            f"ERRO: o e-mail {email!r} gera o nome de entidade {name!r}, que o "
            f"Backstage REJEITA.\n"
            f"       O nome precisa casar com "
            f"/^([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9]$/ e ter 1 a 63 "
            f"caracteres.\n"
            f"       Causa provável: o endereço tem sufixo `+` ou a parte local "
            f"começa/termina com '-'.\n"
            f"       O Backstage deriva o nome da parte local do e-mail, então a "
            f"correção é no próprio endereço."
        )


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(
            f"ERRO: CSV não encontrado: {path}\n"
            f"       Sem a fonte de dados não há como gerar o catálogo."
        )

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        raise SystemExit(f"ERRO: CSV vazio: {path}")

    missing = [col for col in REQUIRED_COLUMNS if col not in rows[0]]
    if missing:
        raise SystemExit(
            f"ERRO: o CSV {path} não tem as colunas obrigatórias: "
            f"{', '.join(missing)}\n"
            f"       Colunas encontradas: {', '.join(rows[0].keys())}"
        )

    return rows


def build_entities(rows: list[dict]) -> tuple[list[str], list[str], list[str]]:
    """Devolve (grupos, usuários, nomes-de-role) já ordenados e validados."""
    users: list[tuple[str, str, str, str]] = []  # (nome, displayName, email, role)
    seen_names: dict[str, str] = {}

    for index, row in enumerate(rows, start=2):  # linha 1 é o cabeçalho
        email = (row.get("email") or "").strip()
        first = (row.get("firstName") or "").strip()
        last = (row.get("lastName") or "").strip()
        role = (row.get("role") or "").strip()

        if not email:
            raise SystemExit(f"ERRO: linha {index} do CSV está sem `email`.")
        if not role:
            raise SystemExit(
                f"ERRO: linha {index} ({email}) está sem `role`.\n"
                f"       O schema de `kind: User` do Backstage EXIGE "
                f"`spec.memberOf`, e a role é a origem desse campo."
            )

        name = entity_name_for(email)
        validate_entity_name(name, email)

        if name in seen_names:
            raise SystemExit(
                f"ERRO: {email} e {seen_names[name]} geram o MESMO nome de "
                f"entidade {name!r}.\n"
                f"       O resolver do Backstage resolve por esse nome, então "
                f"dois usuários com a mesma parte local são ambíguos."
            )
        seen_names[name] = email

        display = " ".join(part for part in (first, last) if part) or name
        users.append((name, display, email, role))

    users.sort(key=lambda item: item[0])
    roles = sorted({role for *_, role in users})
    return roles, users, roles


def render_group(role: str) -> str:
    return (
        "apiVersion: backstage.io/v1alpha1\n"
        "kind: Group\n"
        "metadata:\n"
        f"  name: {yaml_quote(role)}\n"
        f"  description: {yaml_quote(f'Grupo derivado da role {role} no Keycloak')}\n"
        "spec:\n"
        "  type: team\n"
        "  children: []\n"
    )


def render_user(name: str, display: str, email: str, role: str) -> str:
    return (
        "apiVersion: backstage.io/v1alpha1\n"
        "kind: User\n"
        "metadata:\n"
        f"  name: {yaml_quote(name)}\n"
        "spec:\n"
        "  profile:\n"
        f"    displayName: {yaml_quote(display)}\n"
        f"    email: {yaml_quote(email)}\n"
        f"  memberOf: [{yaml_quote(role)}]\n"
    )


def render_configmap(roles: list[str], users: list[tuple], users_csv: Path) -> str:
    inner = "\n---\n".join(
        [render_group(role).rstrip("\n") for role in roles]
        + [render_user(*user).rstrip("\n") for user in users]
    )

    # Indenta o YAML interno para dentro do block scalar `data.users.yaml: |`.
    indented = "\n".join(f"    {line}" if line else "" for line in inner.split("\n"))

    return (
        "# GERADO AUTOMATICAMENTE — NÃO EDITE À MÃO.\n"
        "#\n"
        "# Origem: infrastructure/backstage/scripts/generate-catalog.py\n"
        f"# Fonte : {users_csv}\n"
        "#\n"
        "# Este arquivo NÃO é versionado. Ele contém dados pessoais (nome e e-mail)\n"
        "# e é gerado no momento do provisionamento, direto para o cluster.\n"
        "# Ver infrastructure/backstage/scripts/README.md para a justificativa.\n"
        "apiVersion: v1\n"
        "kind: ConfigMap\n"
        "metadata:\n"
        f"  name: {CONFIGMAP_NAME}\n"
        f"  namespace: {CONFIGMAP_NAMESPACE}\n"
        "  labels:\n"
        "    app.kubernetes.io/component: catalog-users\n"
        "    app.kubernetes.io/managed-by: generate-catalog-py\n"
        "data:\n"
        f"  {CONFIGMAP_KEY}: |\n"
        f"{indented}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Gera o ConfigMap com os usuários do catálogo do Backstage a partir "
            "do CSV que também provisiona o Keycloak."
        )
    )
    parser.add_argument(
        "--users",
        type=Path,
        default=DEFAULT_USERS_CSV,
        help=f"CSV de usuários (default: {DEFAULT_USERS_CSV})",
    )
    args = parser.parse_args()

    rows = load_rows(args.users)
    roles, users, _ = build_entities(rows)

    # Diagnóstico SEMPRE em stderr, para não corromper o YAML que vai no stdout
    # e é canalizado para `kubectl apply -f -`.
    print(
        f"Fonte: {args.users}\n"
        f"  {len(users)} usuários, {len(roles)} grupos: {', '.join(roles)}",
        file=sys.stderr,
    )

    sys.stdout.write(render_configmap(roles, users, args.users))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
