#!/usr/bin/env python3
"""
CLI da calculadora — a mesma conta que o dashboard faz, no terminal.

Existe por dois motivos:
  1. número em documento precisa ser reproduzível sem abrir navegador;
  2. a CLI é a forma de conferir o que o dashboard mostra, e não o contrário.

Usa o MESMO módulo (`api/precos.py`) que o servidor, de propósito: duas
implementações da mesma conta é como dois números diferentes nascem.

    python3 calcular.py
    python3 calcular.py --horas 24
    python3 calcular.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "api"))

from precos import calcular, carregar_json, projecao_mensal  # noqa: E402

MOEDA = "US$"


def brl(valor: float) -> str:
    """Formata milhar com ponto e decimal com vírgula — leitura em pt-BR."""
    return f"{valor:,.4f}".replace(",", "@").replace(".", ",").replace("@", ".")


def num(valor: float) -> str:
    """
    Quantidade em pt-BR, sem decimal supérfluo.

    Existe separado do formatador de dinheiro porque a versão anterior fazia
    um `.replace(',', '.')` na LINHA INTEIRA — o que convertia também as
    vírgulas do português dentro da descrição. A tabela saía assim:

        EC2 do node único — roda Istio. Backstage. Keycloak. Pos...

    Formatar o NÚMERO é diferente de reformatar o texto. Misturar os dois
    estragou a descrição de cada linha.
    """
    if abs(valor - round(valor)) < 1e-9:
        return f"{int(round(valor)):,}".replace(",", ".")
    return f"{valor:,.4f}".replace(",", "@").replace(".", ",").replace("@", ".")


def linha_tabela(item: dict) -> str:
    descricao = item["descricao"]
    if len(descricao) > 54:
        descricao = descricao[:53] + "…"
    if item["sem_preco"]:
        return (
            f"  {descricao:<54} {num(item['quantidade']):>12} {item['unidade_conta']:<9} "
            f"{'—':>14} {'não precificado':>16}"
        )
    return (
        f"  {descricao:<54} {num(item['quantidade_efetiva']):>12} {item['unidade_oficial']:<9} "
        f"{brl(item['preco_unitario']):>14} {brl(item['subtotal']):>16}"
    )


def imprimir(resultado: dict) -> None:
    bom = resultado["bom"]
    print()
    print(f"  {bom['nome']}")
    print(f"  Região: {bom['regiao']} ({bom['localidade']})   Janela: {resultado['horas']:.0f} h")
    fontes = resultado["procedencia"].get("servicos", {})
    datas = ", ".join(f"{s} {v.get('publicationDate', '?')}" for s, v in sorted(fontes.items()))
    print(f"  Fonte dos preços (lista oficial AWS): {datas}")
    print(f"  Snapshot gerado em: {resultado['gerado_em']}")
    print()
    print(f"  {'ITEM':<54} {'QUANTIDADE':>12} {'UNIDADE':<9} {'PREÇO UNIT.':>14} {'SUBTOTAL':>16}")
    print(f"  {'-' * 54} {'-' * 12} {'-' * 9} {'-' * 14} {'-' * 16}")

    grupo_atual = None
    for item in resultado["itens"]:
        if item["grupo"] != grupo_atual:
            grupo_atual = item["grupo"]
            print(f"\n  [{grupo_atual.upper()}]")
        print(linha_tabela(item))

    print()
    print(f"  {'-' * 110}")
    print(f"  TOTAL em {resultado['horas']:.0f} h .............. {MOEDA} {brl(resultado['total'])}")
    print(f"  por hora .................... {MOEDA} {brl(resultado['total_por_hora'])}")
    print(f"  por dia ..................... {MOEDA} {brl(resultado['total_por_dia'])}")
    mes = resultado["mes"]
    print(f"  projeção 730 h (1 mês) ...... {MOEDA} {brl(mes['total'])}")

    print("\n  Por grupo (na janela):")
    for grupo, valor in resultado["por_grupo"].items():
        fatia = 100 * valor / resultado["total"] if resultado["total"] else 0
        print(f"    {grupo:<16} {MOEDA} {brl(valor):>10}   {fatia:5.1f}%")

    if resultado["lacunas"]:
        print("\n  LACUNAS DECLARADAS (linha existe, preço não):")
        for lacuna in resultado["lacunas"]:
            print(f"    - {lacuna['id']}: {lacuna['motivo']}")

    print("\n  Premissas:")
    for premissa in resultado["premissas"]:
        print(f"    - {premissa[:110]}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculadora Resilience — custo do laboratório em AWS")
    parser.add_argument("--horas", type=float, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    bom = carregar_json(BASE / "dados" / "bom.json")
    snapshot = carregar_json(BASE / "dados" / "prices.json")
    resultado = calcular(bom, snapshot, horas=args.horas)
    resultado["mes"] = projecao_mensal(bom, snapshot)
    resultado["bom"] = {k: bom.get(k) for k in ("nome", "regiao", "localidade", "janela")}

    if args.json:
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
    else:
        imprimir(resultado)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
