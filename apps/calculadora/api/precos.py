#!/usr/bin/env python3
"""
Núcleo do cálculo — compartilhado entre a CLI e o servidor da aplicação.

A regra desta calculadora é simples e vale escrever: NENHUM preço mora aqui.
Os preços vêm de `dados/prices.json`, que é o snapshot da lista oficial da AWS
com a `publicationDate` que a própria AWS publica. Este arquivo só sabe fazer
conta — e é por isso que ele pode ser auditado sem discutir se 0,192 está certo.

As duas únicas decisões que este arquivo toma, e que precisam ficar explícitas:

1. GB-Mo é PRO-RATEADO por hora (730 h/mês).
   A AWS cobra disco e storage por GB-segundo na prática; o preço publicado é
   por GB-mês. Pagar um mês inteiro por uma semana de laboratório inflaria o
   número em ~4x. 730 h é a convenção de mês usada pela própria AWS.

2. Cada unidade tem um fator de conversão, e unidade desconhecida NÃO é
   ignorada: vira erro. Unidade nova sem tratamento silencioso é como um
   número errado entra num dashboard e ninguém percebe.

Só biblioteca padrão — de propósito. O mesmo módulo roda na CLI do host de
operação e dentro do container, sem `pip install` em lugar nenhum.
"""

from __future__ import annotations

import json
from pathlib import Path

HORAS_POR_MES = 730

# Unidades que a lista oficial usa nas linhas que consumimos, e o que cada uma
# significa para o cálculo. `GB-Mo` recebe tratamento especial (pro-rata).
UNIDADES = {
    "hrs": "hora (a quantidade já está em horas)",
    "gb-mo": "GB-mês — pro-rateado por hora",
    "gb": "GB (transferência)",
    "requests": "requisição",
    "count": "contagem",
}


class ErroDeCalculo(RuntimeError):
    """Erro de dados ou de premissa — nunca de aritmética."""


class ErroDeEntrada(ErroDeCalculo):
    """
    Erro causado pelo PEDIDO, não pelo dado — parâmetro fora de faixa, tipo
    errado, escolha que não existe no catálogo.

    Existe separado porque a resposta HTTP certa é diferente: pedido inválido é
    400; dado quebrado no snapshot é 500. Sem essa distinção, o servidor devolve
    500 para "você digitou letra no campo de horas", e quem consome a API passa a
    investigar o servidor em vez do próprio pedido.
    """


def carregar_json(caminho: str | Path) -> dict:
    caminho = Path(caminho)
    if not caminho.exists():
        raise ErroDeCalculo(f"arquivo não encontrado: {caminho}")
    return json.loads(caminho.read_text(encoding="utf-8"))


def fator_da_unidade(unidade: str, horas: float) -> float:
    """
    Fator multiplicativo da unidade para a janela pedida.

    `Hrs` e `Requests` já vêm na unidade da janela (168 h, N requisições).
    `GB-Mo` precisa ser pro-rateado, senão a janela de uma semana paga um mês.
    """
    chave = (unidade or "").strip().lower()
    if chave not in UNIDADES:
        raise ErroDeCalculo(
            f"unidade não tratada: {unidade!r}. Trate explicitamente em UNIDADES "
            "antes de usar — unidade ignorada em silêncio vira número errado."
        )
    if chave == "gb-mo":
        return horas / HORAS_POR_MES
    return 1.0


def calcular(bom: dict, snapshot: dict, horas: float | None = None, selecao: dict | None = None) -> dict:
    """
    Cruza o BOM declarado com o snapshot de preços e devolve o detalhamento.

    `selecao` permite trocar, em tempo de execução, o que o BOM traz como
    padrão — é o que faz o seletor de modelo da aplicação funcionar sem que a
    lista de modelos esteja escrita em lugar nenhum: a chave é resolvida no
    `catalogo_ec2`, que saiu do arquivo oficial da AWS.

    Item do BOM cujo preço não existe no snapshot NÃO é descartado: entra com
    `sem_preco: true`. Lacuna visível é melhor que lacuna silenciosa — o painel
    mostra 'não precificado' em vez de fingir que a linha não existe.
    """
    horas = float(horas if horas is not None else bom.get("horas_padrao", 168))
    itens_preco = snapshot.get("itens", {})
    catalogo = snapshot.get("catalogo_ec2", {})
    selecao = selecao or {}
    detalhe: list[dict] = []

    for item in bom.get("itens", []):
        ref = item.get("preco_ref")

        # QUANTIDADE: número, ou a palavra "janela".
        #
        # `"janela"` significa "a quantidade É a janela pedida" — é como uma
        # linha "fica ligada o tempo todo" se declara. Sem isto, a projeção de
        # um mês manteria as 168 h do BOM e a MAIOR linha do custo sairia ~4x
        # mais barata. Foi o primeiro bug que os testes pegaram, e ele não
        # aparecia em nenhuma leitura do código: só na conta de 730 h.
        quantidade_declarada = item.get("quantidade")
        segue_janela = isinstance(quantidade_declarada, str)
        if segue_janela:
            if quantidade_declarada != "janela":
                raise ErroDeCalculo(
                    f"quantidade inválida em {item['id']!r}: {quantidade_declarada!r} "
                    "(use um número ou a palavra 'janela')"
                )
            quantidade = horas
        else:
            quantidade = float(quantidade_declarada)

        linha = {
            "id": item["id"],
            "descricao": item["descricao"],
            "grupo": item.get("grupo", "outros"),
            "quantidade": quantidade,
            "segue_janela": segue_janela,
            "unidade_conta": item["unidade_conta"],
            "preco_ref": ref,
            "opcional": bool(item.get("opcional")),
            "por_que": item.get("por_que", ""),
        }

        if ref == "catalogo_ec2":
            # O preço vem do CATÁLOGO descoberto (1.249 modelos em us-east-1).
            escolhido = selecao.get(item["id"]) or item.get("padrao")
            if escolhido not in catalogo:
                raise ErroDeEntrada(
                    f"modelo {escolhido!r} não existe no catálogo da região "
                    f"{snapshot.get('regiao')!r}"
                )
            do_catalogo = catalogo[escolhido]
            preco_bruto = {
                "preco": do_catalogo["preco"],
                "unidade": do_catalogo["unidade"],
                "tipo_uso": f"catálogo EC2 · {do_catalogo.get('vcpu')} vCPU / {do_catalogo.get('memoria')}",
                "sku": do_catalogo.get("sku", ""),
                "descricao": f"EC2 {escolhido} — {do_catalogo.get('familia', '')}",
            }
            linha["modelo"] = escolhido
        else:
            preco_bruto = itens_preco.get(ref)

        if not preco_bruto:
            linha.update(
                {
                    "sem_preco": True,
                    "motivo": f"o snapshot não tem preço para {ref!r}",
                    "subtotal": 0.0,
                }
            )
            detalhe.append(linha)
            continue

        preco = float(preco_bruto["preco"])
        unidade_oficial = preco_bruto["unidade"]
        fator = fator_da_unidade(unidade_oficial, horas)
        quantidade_efetiva = quantidade * fator
        linha.update(
            {
                "sem_preco": False,
                "preco_unitario": preco,
                "unidade_oficial": unidade_oficial,
                "fator": fator,
                "quantidade_efetiva": quantidade_efetiva,
                "subtotal": quantidade_efetiva * preco,
                "tipo_uso": preco_bruto.get("tipo_uso", ""),
                "sku": preco_bruto.get("sku", ""),
                "preco_descricao": preco_bruto.get("descricao", ""),
            }
        )
        detalhe.append(linha)

    total = sum(l["subtotal"] for l in detalhe)
    por_grupo: dict[str, float] = {}
    for linha in detalhe:
        por_grupo[linha["grupo"]] = por_grupo.get(linha["grupo"], 0.0) + linha["subtotal"]

    sem_preco = [l for l in detalhe if l["sem_preco"]]

    return {
        "horas": horas,
        "regiao": snapshot.get("regiao"),
        "localidade": snapshot.get("localidade"),
        "total": total,
        "total_por_hora": total / horas if horas else 0.0,
        "total_por_dia": total / (horas / 24) if horas else 0.0,
        "por_grupo": dict(sorted(por_grupo.items(), key=lambda kv: -kv[1])),
        "itens": sorted(detalhe, key=lambda l: -l["subtotal"]),
        "lacunas": [{"id": l["id"], "descricao": l["descricao"], "motivo": l["motivo"]} for l in sem_preco],
        "selecao": selecao,
        "modelos_disponiveis": len(catalogo),
        "procedencia": snapshot.get("fonte", {}),
        "gerado_em": snapshot.get("gerado_em"),
        "premissas": bom.get("premissas", []),
    }


def projecao_mensal(bom: dict, snapshot: dict, selecao: dict | None = None) -> dict:
    """
    Mesmo BOM, janela de um mês (730 h).

    Existe para responder a pergunta que sempre vem depois do número semanal:
    'e se eu deixar isso ligado?'. A resposta é ~4,3x, e mostrar isso é mais
    honesto do que deixar o número da semana ser confundido com operação real.
    """
    return calcular(bom, snapshot, horas=float(HORAS_POR_MES), selecao=selecao)
