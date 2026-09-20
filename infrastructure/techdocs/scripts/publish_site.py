#!/usr/bin/env python3
"""
Publica um site JÁ GERADO no bucket que o Backstage lê (TechDocs).

===============================================================================
POR QUE ISTO EXISTE
===============================================================================
O caminho normal de publicação é o CronJob `techdocs-builder` (ver
`infrastructure/techdocs/templates/cronjob.yaml`): ele clona o repositório,
roda `mkdocs build` e sincroniza no bucket, sozinho, a cada 30 minutos.

Este script faz o MESMO último passo, mas a partir da sua máquina:

  1. para reproduzir o pipeline na mão e entender cada etapa;
  2. para publicar um site gerado localmente sem esperar o ciclo do cron
     (útil quando se está iterando no `mkdocs.yml` ou no próprio script);
  3. para inspecionar o que o bucket receberia, sem publicar (`--dry-run`).

Ele NÃO substitui o CronJob e não é pré-requisito de nada em produção. É
ferramenta de bancada — e ferramenta de bancada que roda à mão precisa ser
declarada também, senão vira procedimento tribal.

===============================================================================
POR QUE PYTHON, E NÃO `aws s3 sync` NA CONSOLE
===============================================================================
`aws s3 sync --endpoint-url ...` funciona e foi o que eu usei primeiro. O
problema não é funcionar: é que um comando digitado no terminal **não fica**.
Ele não está no repositório, não tem `--help`, não diz o que faz, e na próxima
vez alguém reinventa (ou erra) o caminho.

Aqui a decisão de projeto está no código: qual endpoint, qual caminho no
bucket, o que é "arquivo que mudou", o que acontece com o que sumiu do site.

===============================================================================
POR QUE boto3, E NÃO ASSINATURA SigV4 NA MÃO
===============================================================================
Assinar as requisições com a biblioteca padrão é possível (o algoritmo SigV4 é
público), mas seriam ~80 linhas de criptografia para reimplementar o que o SDK
já faz — e o erro de assinatura é silencioso e chato de depurar.

O SDK da AWS é o cliente oficial: é o que o Backstage usa para LER o bucket e
o que a CLI oficial do TechDocs usa para PUBLICAR. Usar o mesmo cliente aqui
mantém um só comportamento.

===============================================================================
POR QUE COMPARAR MD5 E NÃO SÓ O TAMANHO
===============================================================================
O CronJob usa `aws s3 sync --size-only`, uma aproximação: se um arquivo mudar
de conteúdo **sem mudar de tamanho** (raro, mas possível), ele não sobe.

Aqui a comparação é exata: o MD5 local contra o `ETag` do objeto remoto — que,
para objeto sem multipart, é o próprio MD5. Assim o script é uma referência de
comportamento correto para comparar com a aproximação do cron.

===============================================================================
⚠️  QUAL TOOLCHAIN GEROU O SITE? (evita ping-pong no bucket)
===============================================================================
O build CANÔNICO é o do CronJob, que usa a imagem `spotify/techdocs:1.2.9`
(pinada — ADR-005). Ela carrega as próprias versões de mkdocs e techdocs-core.

Se você gerar o site com OUTRA versão (por exemplo, um venv local com um
`mkdocs-techdocs-core` mais novo), o HTML e os assets saem diferentes — inclusive
os nomes de arquivo, que carregam hash de conteúdo. Publicar isso cria uma
briga: este script escreve uma versão, o CronJob escreve a outra 30 minutos
depois, e o bucket fica oscilando.

Medido em 2026-09-19, comparando um build local (techdocs-core 1.7.1) com o do
cron (imagem 1.2.9): **21 arquivos com conteúdo diferente e 4 assets órfãos**.

Portanto: para publicar, gere o site com a MESMA imagem do cron. Use este script
para reproduzir e conferir o caminho de publicação — não para competir com ele.

===============================================================================
USO
===============================================================================
Ver o plano, sem publicar nada:

    python3 infrastructure/techdocs/scripts/publish_site.py \\
      --site-dir /tmp/tfdocs-site --dry-run

Publicar:

    export AWS_ACCESS_KEY_ID=test
    export AWS_SECRET_ACCESS_KEY=test
    python3 infrastructure/techdocs/scripts/publish_site.py \\
      --site-dir /tmp/tfdocs-site

Forçar o reenvio de tudo (ignora a comparação de MD5):

    python3 infrastructure/techdocs/scripts/publish_site.py \\
      --site-dir /tmp/tfdocs-site --force

===============================================================================
DEPENDÊNCIAS
===============================================================================
`boto3` (ver `requirements.txt` ao lado). Precisa de venv — diferente do
`generate-catalog.py`, que é stdlib puro porque só gera YAML. Aqui há rede,
TLS e assinatura de requisição envolvidas; biblioteca padrão não é a ferramenta
certa.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import Any

try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError, ClientError
except ModuleNotFoundError:
    sys.exit(
        "ERRO: boto3 não encontrado.\n\n"
        "Crie o venv e instale as dependências:\n"
        "  python3 -m venv infrastructure/techdocs/scripts/.venv\n"
        "  infrastructure/techdocs/scripts/.venv/bin/pip install -r "
        "infrastructure/techdocs/scripts/requirements.txt\n"
    )

# Valores padrão do laboratório. Não são segredo: são topologia (o Floci vive
# na LAN, no servidor). As CREDENCIAIS, sim, vêm sempre do ambiente.
DEFAULT_ENDPOINT = os.environ.get("FLOCI_ENDPOINT", "http://192.168.99.5:4566")
DEFAULT_BUCKET = "resilience-techdocs"
DEFAULT_ENTITY = "default/component/documentacao-resilience"
DEFAULT_REGION = "us-east-1"


def md5_of(path: Path) -> str:
    """MD5 do arquivo, em hexadecimal — para comparar com o ETag do objeto."""
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_client(endpoint: str, region: str) -> Any:
    """Cliente S3 apontado para o Floci, com path-style.

    `path-style` é obrigatório: o Floci é uma API S3-compatível que recebe o
    bucket no CAMINHO (`endpoint/bucket/chave`), e não no subdomínio
    (`bucket.endpoint/chave`), que é o estilo virtual-hosted da AWS.
    """
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        config=Config(
            s3={"addressing_style": "path"},
            retries={"max_attempts": 5, "mode": "standard"},
        ),
    )


def remote_objects(client: Any, bucket: str, prefix: str) -> dict[str, dict[str, Any]]:
    """Mapa chave -> metadados do objeto, para tudo abaixo do prefixo."""
    found: dict[str, dict[str, Any]] = {}
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            found[obj["Key"]] = obj
    return found


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publica um site gerado no bucket de TechDocs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--site-dir",
        type=Path,
        required=True,
        help="diretório com o site já gerado (o `site/` do mkdocs)",
    )
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument(
        "--entity",
        default=DEFAULT_ENTITY,
        help="entity triplet (namespace/kind/name), em minúsculas — é o caminho no bucket",
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument(
        "--force",
        action="store_true",
        help="reenvia tudo, sem comparar MD5 com o objeto remoto",
    )
    parser.add_argument(
        "--keep-stale",
        action="store_true",
        help="não apaga do bucket o que não existe mais no site local",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="mostra o que seria feito e não altera nada",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    site_dir: Path = args.site_dir
    if not site_dir.is_dir():
        sys.exit(f"ERRO: {site_dir} não é um diretório.")
    if not (site_dir / "index.html").is_file():
        sys.exit(
            f"ERRO: {site_dir}/index.html não existe.\n"
            "Um site de TechDocs precisa de index.html na raiz — sem ele o\n"
            "leitor do Backstage mostra spinner eterno (ver README em\n"
            "infrastructure/techdocs/artefatos/payload-de-teste/)."
        )

    if not os.environ.get("AWS_ACCESS_KEY_ID") or not os.environ.get(
        "AWS_SECRET_ACCESS_KEY"
    ):
        sys.exit(
            "ERRO: credenciais ausentes no ambiente.\n"
            "  export AWS_ACCESS_KEY_ID=test\n"
            "  export AWS_SECRET_ACCESS_KEY=test\n"
            "(os valores do emulador; credencial nunca fica no código)"
        )

    prefix = f"{args.entity}/"
    local_files = sorted(p for p in site_dir.rglob("*") if p.is_file())

    print(f"endpoint : {args.endpoint}")
    print(f"bucket   : {args.bucket}")
    print(f"prefixo  : {prefix}")
    print(f"arquivos : {len(local_files)} locais")
    if args.dry_run:
        print("modo     : --dry-run (nada será alterado)")
    print()

    client = build_client(args.endpoint, args.region)

    try:
        remote = remote_objects(client, args.bucket, prefix)
    except (BotoCoreError, ClientError) as exc:
        sys.exit(f"ERRO ao listar o bucket {args.bucket}: {exc}")

    print(f"remotos  : {len(remote)} objetos sob o prefixo")
    print()

    enviados: list[str] = []
    ignorados: list[str] = []
    remotos_vistos: set[str] = set()

    for path in local_files:
        key = f"{prefix}{path.relative_to(site_dir).as_posix()}"
        remotos_vistos.add(key)
        etag = (remote.get(key) or {}).get("ETag", "").strip('"')
        local_md5 = md5_of(path)

        if not args.force and etag == local_md5:
            ignorados.append(key)
            continue

        motivo = "novo" if key not in remote else (
            "forçado" if args.force else "conteúdo diferente"
        )
        print(f"  enviar   {key}  ({motivo})")
        enviados.append(key)
        if not args.dry_run:
            client.upload_file(
                str(path),
                args.bucket,
                key,
                ExtraArgs={"ContentType": guess_content_type(path)},
            )

    obsoletos = sorted(set(remote) - remotos_vistos)
    if obsoletos and not args.keep_stale:
        for key in obsoletos:
            print(f"  apagar   {key}  (não existe mais no site)")
        if not args.dry_run:
            client.delete_objects(
                Bucket=args.bucket,
                Delete={"Objects": [{"Key": k} for k in obsoletos]},
            )

    print()
    print(f"enviados : {len(enviados)}")
    print(f"idênticos: {len(ignorados)}")
    print(f"apagados : {len(obsoletos) if not args.keep_stale else 0}")
    if args.dry_run:
        print("\n(--dry-run: nada foi alterado)")

    return 0


def guess_content_type(path: Path) -> str:
    """Content-Type pelo sufixo. O iframe do TechDocs precisa de text/html."""
    return {
        ".html": "text/html",
        ".css": "text/css",
        ".js": "application/javascript",
        ".json": "application/json",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".ico": "image/x-icon",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".map": "application/json",
        ".xml": "application/xml",
        ".gz": "application/gzip",
    }.get(path.suffix.lower(), "application/octet-stream")


if __name__ == "__main__":
    raise SystemExit(main())
