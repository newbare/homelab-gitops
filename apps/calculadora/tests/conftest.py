"""
Configuração dos testes.

`sys.path` recebe `api/` para os testes importarem os módulos pelo MESMO nome
que eles têm em produção (`precos`, `servidor`). Assim o teste exercita o
código que roda no Pod — e não uma cópia que envelhece ao lado.

Duas famílias de dado, de propósito separadas:

  - `snapshot_falso` / `bom_falso`: construídos à mão, com número redondo. É o
    que permite testar ARITMÉTICA sem depender do mercado da AWS. Um teste de
    conta que quebra porque o preço do m6i.xlarge mudou não é teste de conta,
    é aforição sobre a AWS.
  - `snapshot_real` / `bom_real`: os arquivos do repositório. Servem para
    testar o CONTRATO do dado (procedência, catálogo, coerência com o BOM).
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent.parent
# Dois caminhos, porque ha dois lugares de modulo: `api/` (precos, servidor, pg,
# oficial) e a raiz do app (buscar_precos, carregar_precos, calcular). O teste
# importa pelo MESMO nome que roda em producao.
sys.path.insert(0, str(BASE / "api"))
sys.path.insert(0, str(BASE))

DADOS = BASE / "dados"


# --------------------------------------------------------------------------
# Dado real (commitado)
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def bom_real() -> dict:
    return json.loads((DADOS / "bom.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def snapshot_real() -> dict:
    return json.loads((DADOS / "prices.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Dado sintético (números redondos)
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def snapshot_falso() -> dict:
    return {
        "gerado_em": "2026-09-19T00:00:00Z",
        "regiao": "us-east-1",
        "localidade": "US East (N. Virginia)",
        "itens": {
            "ebs.gp3": {"preco": "0.08", "unidade": "GB-Mo", "tipo_uso": "gp3", "sku": "SKU-DISCO", "descricao": "gp3"},
            "transferencia.internet": {"preco": "0.10", "unidade": "GB", "tipo_uso": "DataTransfer-Out-Bytes", "sku": "SKU-EGRESS", "descricao": "egress"},
        },
        "catalogo_ec2": {
            "m6i.xlarge": {"preco": "0.20", "unidade": "Hrs", "vcpu": "4", "memoria": "16 GiB", "familia": "General purpose", "sku": "SKU-A"},
            "t3.micro": {"preco": "0.01", "unidade": "Hrs", "vcpu": "2", "memoria": "1 GiB", "familia": "General purpose", "sku": "SKU-B"},
        },
        "fonte": {"servicos": {}},
    }


@pytest.fixture(scope="session")
def bom_falso() -> dict:
    return {
        "nome": "BOM de teste",
        "regiao": "us-east-1",
        "horas_padrao": 100,
        "premissas": ["premissa de teste"],
        "itens": [
            {
                "id": "node",
                "descricao": "node do teste",
                "preco_ref": "catalogo_ec2",
                "padrao": "m6i.xlarge",
                "quantidade": "janela",
                "unidade_conta": "Hrs",
                "grupo": "computacao",
                "por_que": "porque sim",
            },
            {
                "id": "disco",
                "descricao": "disco do teste",
                "preco_ref": "ebs.gp3",
                "quantidade": 500,
                "unidade_conta": "GB-Mo",
                "grupo": "armazenamento",
                "por_que": "porque sim",
            },
            {
                "id": "egress",
                "descricao": "saída do teste",
                "preco_ref": "transferencia.internet",
                "quantidade": 30,
                "unidade_conta": "GB",
                "grupo": "rede",
                "por_que": "porque sim",
            },
            {
                "id": "sem-preco",
                "descricao": "linha sem preço no snapshot",
                "preco_ref": "nao.existe.no.snapshot",
                "quantidade": 7,
                "unidade_conta": "Hrs",
                "grupo": "rede",
                "por_que": "existe para provar que lacuna não é descartada",
            },
        ],
    }


# --------------------------------------------------------------------------
# Servidor de verdade
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def base_url() -> str:
    """
    Sobe o servidor REAL em porta efêmera e devolve a URL base.

    Porta 0 = o SO escolhe uma livre, então o teste não colide com nada que
    esteja rodando na máquina. Fala HTTP de verdade: o que passa aqui passou
    pelo mesmo caminho que o Ingress vai usar.
    """
    from servidor import criar_servidor

    servidor = criar_servidor(BASE / "web", DADOS, porta=0, endereco="127.0.0.1", assets=BASE / "assets")
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{servidor.server_port}"
    finally:
        servidor.shutdown()
        servidor.server_close()
