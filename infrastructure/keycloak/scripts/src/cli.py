import argparse
import logging
import sys
from pathlib import Path

from . import config
from .keycloak_client import KeycloakClient
from .provisioner import load_users, run


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def main():
    setup_logging()
    log = logging.getLogger("provisioner")

    parser = argparse.ArgumentParser(description="Provisiona usuários em massa no Keycloak.")
    parser.add_argument("--users", required=True, help="Caminho para o CSV/XLSX de usuários.")
    parser.add_argument("--workers", type=int, default=8, help="Threads paralelas (default: 8).")
    parser.add_argument("--dry-run", action="store_true", help="Só simula, não altera nada.")
    args = parser.parse_args()

    path = Path(args.users)
    if not path.exists():
        log.error(f"Arquivo não encontrado: {path}")
        sys.exit(1)

    cfg = config.load()
    log.info(f"Keycloak: {cfg['url']}")
    log.info(f"Realm:    {cfg['realm']}")

    log.info(f"Lendo usuários de {path}...")
    users = load_users(path)
    log.info(f"{len(users)} usuários carregados.")

    client = KeycloakClient(cfg)
    stats = run(client, users, workers=args.workers, dry_run=args.dry_run)

    log.info(
        f"Resumo: {stats['created']} criados, "
        f"{stats['updated']} atualizados, {stats['errors']} erros."
    )


if __name__ == "__main__":
    main()
