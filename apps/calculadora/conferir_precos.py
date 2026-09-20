#!/usr/bin/env python3
"""F1 — Conferência de preço: mapa da calculadora oficial x Bulk Price List.

Confere, serviço a serviço do escopo, se cada `rateCode` do mapa que a
calculadora da AWS consome existe e tem o MESMO preço no Bulk Price List — a
fonte que a nossa calculadora usa.

Uso:
    python3 conferir_precos.py                    # escopo inteiro
    python3 conferir_precos.py --servico awsEks   # um serviço
    python3 conferir_precos.py --filhos 0         # não descer em filhos de pai
    python3 conferir_precos.py --detalhe          # mostra divergências e ausentes

Saída: relatório no terminal. Código de saída 1 se houver divergência, ausência
ou falha — serve de portão em teste automatizado.

── POR QUE ASSIM ───────────────────────────────────────────────────────────────
O mapa oficial e o Bulk Price List são indexados pelo mesmo `rateCode`, então a
conferência é um join de dicionário. Quando bate, não é "parece certo": é o mesmo
número, identificado pelo mesmo código, da mesma publicação.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api import oficial

AQUI = os.path.dirname(os.path.abspath(__file__))


def carregar_escopo():
    with open(os.path.join(AQUI, "dados", "escopo.json"), encoding="utf-8") as arquivo:
        return json.load(arquivo)


def raizes_do_escopo(escopo):
    """Códigos de serviço do escopo, na ordem da tabela, sem repetir."""
    vistos = []
    for linha in escopo["linhas"]:
        for codigo in linha.get("raizes") or []:
            if codigo not in vistos:
                vistos.append(codigo)
    return vistos


def imprimir(relatorio, detalhe=False):
    status = relatorio["status"]
    marca = {"VERIFICADO": "OK ", "FILHO_NECESSARIO": "PAI", "DIVERGENTE": "DIV",
             "SEM_MAPA": "SEM", "SEM_OFERTA": "SEM", "FALHA": "ERR"}.get(status, "?  ")
    extra = f"iguais={relatorio['iguais']}"
    if relatorio["diferentes"]:
        extra += f" diferentes={len(relatorio['diferentes'])}"
    if relatorio["ausentes"]:
        extra += f" ausentes={len(relatorio['ausentes'])}"
    ofertas = relatorio.get("ofertas_indexadas") or []
    # 1 oferta é o caso simples; várias significa que o mapa traz dimensão de fora.
    rotulo_ofertas = ofertas[0] if len(ofertas) == 1 else f"{len(ofertas)} ofertas"
    if relatorio.get("mapas_sem_regiao"):
        extra += f" sem_regiao={relatorio['mapas_sem_regiao']}"
    print(f"  [{marca}] {relatorio['service_code']:<40} {extra:<40} "
          f"oferta={rotulo_ofertas:<20} pub={relatorio.get('publicacao_mapa') or '-'}")
    if detalhe and len(ofertas) > 1:
        print(f"          índice: {', '.join(ofertas)}")
    if relatorio.get("motivo") and status not in ("VERIFICADO",):
        print(f"          motivo: {relatorio['motivo']}")
    if detalhe:
        for d in relatorio["diferentes"][:5]:
            print(f"          DIFERE {d['rate_code']}  oficial={d['oficial']}  price_list={d['price_list']}")
        for a in relatorio["ausentes"][:5]:
            print(f"          AUSENTE {a}")


def conferir_com_filhos(catalogo, codigo, regiao, cache_dir, max_filhos, detalhe):
    """Confere um serviço; se for pai (sem preço próprio), desce nos filhos.

    O pai declarar os filhos em `templates` é o único mapa de dependência que o
    manifest oferece — e é por isso que ele é usado aqui em vez de uma lista
    escrita à mão.
    """
    relatorio = oficial.conferir(catalogo, codigo, regiao, cache_dir)
    imprimir(relatorio, detalhe)
    # Serviço que NÃO é pai e está divergente também é pendência. Sem isto o
    # portão do CLI não portava nada: só pai era avaliado, e o exit code saía 0
    # com divergência na tela.
    ruins = [] if relatorio["status"] in ("VERIFICADO", "FILHO_NECESSARIO") else [relatorio]
    if relatorio["status"] != "FILHO_NECESSARIO" or max_filhos <= 0:
        return [relatorio], ruins

    entrada = catalogo.get(codigo) or {}
    filhos = (entrada.get("templates") or [])[:max_filhos]
    resultados = []
    for filho in filhos:
        r = oficial.conferir(catalogo, filho, regiao, cache_dir)
        imprimir(r, detalhe)
        resultados.append(r)
    total = [relatorio] + resultados
    return resultados, [r for r in total if r["status"] not in ("VERIFICADO", "FILHO_NECESSARIO")]


def main():
    parser = argparse.ArgumentParser(description="Confere preço: calculadora oficial x Bulk Price List")
    parser.add_argument("--servico", help="conferir só este serviceCode")
    parser.add_argument("--filhos", type=int, default=3,
                        help="quantos filhos conferir por serviço pai (default 3; 0 = nenhum)")
    parser.add_argument("--detalhe", action="store_true", help="mostra divergências e ausentes")
    parser.add_argument("--cache", default=oficial.CACHE_PADRAO)
    args = parser.parse_args()

    escopo = carregar_escopo()
    regiao = escopo["regiao_de_verificacao"]
    regiao_para_cliente = {"rotulo_oficial": regiao["rotulo_oficial"],
                           "codigo_price_list": regiao["codigo_price_list"]}

    print("=== F1 · CONFERÊNCIA DE PREÇO ===")
    print(f"  região: {regiao['rotulo_oficial']}  ({regiao['codigo_price_list']})")
    print(f"  fonte A: mapa da calculadora da AWS (calculator.aws)")
    print(f"  fonte B: Bulk Price List (pricing.us-east-1.amazonaws.com)")
    print()

    catalogo = oficial.manifesto(args.cache)
    print(f"  catálogo: {len(catalogo)} serviços")
    print()

    codigos = [args.servico] if args.servico else raizes_do_escopo(escopo)

    todos = []
    ruins = []
    for codigo in codigos:
        try:
            resultados, pendencias = conferir_com_filhos(
                catalogo, codigo, regiao_para_cliente, args.cache, args.filhos, args.detalhe)
            todos.extend(resultados)
            ruins.extend(pendencias)
        except Exception as erro:  # rede instável não pode derrubar a conferência inteira
            print(f"  [ERR] {codigo:<40} exceção: {str(erro)[:70]}")
            ruins.append({"service_code": codigo, "status": "FALHA", "iguais": 0,
                          "diferentes": [], "ausentes": [], "oferta": None})

    verificados = [r for r in todos if r["status"] == "VERIFICADO"]
    pais = [r for r in todos if r["status"] == "FILHO_NECESSARIO"]
    iguais = sum(r["iguais"] for r in todos)
    diferentes = sum(len(r["diferentes"]) for r in todos)
    ausentes = sum(len(r["ausentes"]) for r in todos)

    print()
    print("=== RESUMO ===")
    print(f"  serviços conferidos ....... {len(todos)}")
    print(f"  VERIFICADOS ............... {len(verificados)}")
    print(f"  pais (preço nos filhos) ... {len(pais)}")
    print(f"  rateCodes iguais .......... {iguais}")
    print(f"  rateCodes diferentes ...... {diferentes}")
    print(f"  rateCodes ausentes ........ {ausentes}")
    print(f"  pendências ................ {len(ruins)}")
    print()
    print("  Nota: 'ausentes' = não encontrado nas ofertas indexadas, não 'não existe'.")
    print("  Famílias com mapa sem eixo de região são contadas como sem_regiao, não como falha.")

    if ruins:
        print()
        print("  PENDÊNCIAS:")
        for r in ruins:
            print(f"    {r['service_code']}  ({r['status']})")
        return 1

    print()
    print("  Nenhuma divergência. Cada preço do escopo tem o mesmo rateCode,")
    print("  com o mesmo valor, na mesma publicação das duas fontes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
