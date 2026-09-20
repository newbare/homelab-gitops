#!/usr/bin/env python3
"""
Coleta os preços OFICIAIS da AWS e escreve um snapshot compacto.

Por que este arquivo existe
===========================
A calculadora precisa de preço, e preço digitado de memória envelhece sem
avisar. Aqui o número vem da fonte oficial da AWS, e o snapshot sai carimbado
com a `publicationDate` que a PRÓPRIA AWS publica — então cada valor no
dashboard tem procedência e data sem ninguém digitar nada.

Qual fonte, e por que esta
==========================
Existem três superfícies de preço na AWS. Medidas em 2026-09-19:

  1. Bulk Price List  pricing.us-east-1.amazonaws.com/offers/v1.0/aws/...
     -> PÚBLICA, SEM CREDENCIAL. É a que usamos.
     -> Custo: o arquivo do EC2/us-east-1 em CSV tem 288,8 MB.
        (o JSON tem 459 MB; gzip NÃO é oferecido pelo servidor)

  2. Price List Query API  api.pricing.us-east-1.amazonaws.com
     -> oficial, filtra no servidor (resposta pequena), mas EXIGE SigV4:
        sem credencial devolve `MissingAuthenticationTokenException`.
     -> é o modo "preciso", para quando houver conta AWS de verdade.

  3. calculator.aws
     -> instrumento oficial de estimativa, sem API pública documentada.

Por que 288,8 MB não é problema
===============================
Porque isso NÃO roda a cada leitura. Este script é o passo RARO:

    buscar_precos.py  ->  dados/prices.json  ->  a calculadora (instantânea)

O snapshot fica versionado no Git. A aplicação serve o snapshot; ela nunca
baixa os 288,8 MB. E o refresh roda no host do Terraform, com Python e venv,
que é onde a operação de AWS já vive — não na máquina de quem está olhando o
dashboard.

Uso
===
    python3 buscar_precos.py                       # todos os serviços
    python3 buscar_precos.py --servicos AmazonECR  # só um (é instantâneo)
    python3 buscar_precos.py --dump /tmp/cand.json # inspecionar candidatos

O `--dump` existe porque o CSV tem dezenas de colunas e os nomes variam entre
famílias de produto. Quando uma consulta não casa, o dump mostra o que o
arquivo REALMENTE contém — em vez de adivinhar de novo.

Só biblioteca padrão: nenhum `pip install`, nem aqui, nem no host.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws"
RAIZ_OFERTAS = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/index.json"
REGIAO_PADRAO = "us-east-1"  # só o padrão do CLI; a lista inteira vem da fonte

# Filtro canônico de instância sob demanda: é o conjunto que identifica
# "On Demand Linux <tipo> Instance" (tenancy compartilhada, sem software pré
# instalado, capacidade usada). Vale para o CATÁLOGO inteiro, então serve para
# qualquer tipo de máquina — não é uma lista de modelos, é um critério.
FILTRO_INSTANCIA = {
    "unit": "Hrs",
    "operating system": "Linux",
    "tenancy": "Shared",
    "pre installed sw": "NA",
    "capacitystatus": "Used",
    "license model": "No License required",
}

# ---------------------------------------------------------------------------
# CONSULTAS — o que interessa precificar
# ---------------------------------------------------------------------------
# Cada consulta tem:
#   id        -> a chave que o BOM vai referenciar em dados/bom.json
#   familia   -> `Product Family` no arquivo (Compute Instance, Storage, ...)
#   ancora    -> atributo(s) que identificam sozinhos, usados para o modo LOOSE
#                (o dump). Com a âncora errada o dump ainda traz o material.
#   igual     -> filtro exato. Todas as condições precisam casar.
#
# Os nomes de coluna são comparados de forma NORMALIZADA (minúsculas, sem
# espaço/barra/hífen), então `Pre Installed S/W` casa com `preinstalledsw`.
# ⚠️ LIÇÃO DO PRIMEIRO TESTE (2026-09-19): filtrar por `Product Family` NÃO
# funciona. No arquivo do S3, 282 das 366 linhas têm essa coluna VAZIA, e o
# filtro por família descarta justamente as linhas de armazenamento. A chave
# confiável é o `usageType`, que é identificador de máquina e vem sempre
# preenchido — foi lendo o arquivo real (e não a documentação) que isso
# apareceu.
CONSULTAS: dict[str, list[dict]] = {
    "AmazonEC2": [
        {
            "id": "ec2.m6i.xlarge",
            "descricao": "EC2 m6i.xlarge — 4 vCPU / 16 GiB, Linux, tenancy Shared, on-demand",
            "familia": "Compute Instance",
            "ancora": {"instance type": "m6i.xlarge"},
            "igual": {
                "unit": "Hrs",
                "operating system": "Linux",
                "tenancy": "Shared",
                "pre installed sw": "NA",
                "capacitystatus": "Used",
                "license model": "No License required",
            },
        },
        {
            "id": "ec2.t3.xlarge",
            "descricao": "EC2 t3.xlarge — 4 vCPU / 16 GiB (burstable), Linux, on-demand",
            "familia": "Compute Instance",
            "ancora": {"instance type": "t3.xlarge"},
            "igual": {
                "unit": "Hrs",
                "operating system": "Linux",
                "tenancy": "Shared",
                "pre installed sw": "NA",
                "capacitystatus": "Used",
                "license model": "No License required",
            },
        },
        {
            "id": "ec2.t3.micro",
            "descricao": "EC2 t3.micro — 2 vCPU / 1 GiB, Linux (host do Terraform)",
            "familia": "Compute Instance",
            "ancora": {"instance type": "t3.micro"},
            "igual": {
                "unit": "Hrs",
                "operating system": "Linux",
                "tenancy": "Shared",
                "pre installed sw": "NA",
                "capacitystatus": "Used",
                "license model": "No License required",
            },
        },
        {
            "id": "ebs.gp3",
            "descricao": "EBS gp3 — volume SSD de uso geral",
            "ancora": {"volume api name": "gp3"},
            "igual": {"volume api name": "gp3", "unit": "GB-Mo"},
        },
        {
            # ⚠️ O IPv4 PÚBLICO NÃO ESTÁ NESTE ARQUIVO. A varredura das
            # famílias reais do arquivo do EC2 devolveu: Compute Instance,
            # Compute Instance (bare metal), Dedicated Host, Data Transfer,
            # Storage, NAT Gateway, Load Balancer... e NENHUMA família de IP.
            # Três tentativas falharam aqui — primeiro por igualdade em
            # `Product Family: IP Address`, depois por substring em
            # `usageType` — até o diagnóstico de famílias mostrar que o dado
            # não existe no arquivo.
            #
            # A cobrança horária do endereço mora no offer do **AmazonVPC**.
            # Ver a consulta `ipv4.publico.em_uso` naquele serviço.
            "id": "ec2.ipv4-estava-no-arquivo-errado",
            "desativada": True,
        },
        {
            # ⚠️ A FAMÍLIA "Data Transfer" DESTE ARQUIVO É SÓ INTER-REGIÃO.
            # O dump trouxe as 34 linhas e nenhuma é internet: são
            # `USE1-USW1-AWS-Out-Bytes` (US$ 0,02/GB entre regiões),
            # `DataTransfer-Regional-Bytes` (intra-região) e afins.
            #
            # O filtro frouxo (`~outbytes`) casou 20 linhas e o `escolher`
            # pegou a MENOR — US$ 0,02 — enquanto as 19 descartadas ficavam
            # invisíveis. Foi o aviso de "candidatos descartados" que denunciou
            # o problema. Sem ele, o painel mostraria 4,5x menos que a
            # realidade, com cara de número certo.
            #
            # A saída para internet mora no offer `AWSDataTransfer`.
            "id": "transferencia.ec2-inter-regiao",
            "desativada": True,
        },
    ],
    "AmazonS3": [
        {
            # S3 Standard: a linha do primeiro escalão é identificada pelo
            # usageType + `StartingRange == 0`. Sem o range, casam também as
            # faixas de 450 TB em diante (0.022 e 0.021), que não são Standard.
            "id": "s3.standard",
            "descricao": "S3 Standard — armazenamento (primeiros 50 TB/mês)",
            "ancora": {"usage type": "TimedStorage-ByteHrs"},
            "igual": {
                "usage type": "TimedStorage-ByteHrs",
                "unit": "GB-Mo",
                "starting range": "0",
            },
        },
        {
            "id": "s3.requisicoes.tier1",
            "descricao": "S3 — requisições Tier1 (PUT, COPY, POST, LIST)",
            "ancora": {"usage type": "Requests-Tier1"},
            "igual": {"usage type": "Requests-Tier1", "unit": "Requests"},
        },
        {
            "id": "s3.requisicoes.tier2",
            "descricao": "S3 — requisições Tier2 (GET e demais)",
            "ancora": {"usage type": "Requests-Tier2"},
            "igual": {"usage type": "Requests-Tier2", "unit": "Requests"},
        },
    ],
    "AmazonECR": [
        {
            # Mesmo usageType do S3, POR ISSO a consulta é escopada por serviço.
            "id": "ecr.armazenamento",
            "descricao": "ECR — armazenamento de imagem privada",
            "ancora": {"usage type": "TimedStorage-ByteHrs"},
            "igual": {"usage type": "TimedStorage-ByteHrs", "unit": "GB-Mo"},
        },
    ],
    "AmazonVPC": [
        {
            # A cobrança horária do IPv4 público em uso vive AQUI, no offer do
            # VPC — não no do EC2. Ver o comentário em `AmazonEC2` acima.
            # Confirmado no dado: US$ 0,005/h.
            "id": "ipv4.publico.em_uso",
            "descricao": "Endereço IPv4 público em uso (cobrado por hora desde 2024-02)",
            "ancora": {"usage type": "~ipv4"},
            "igual": {"usage type": "~inuseaddress", "unit": "Hrs"},
        },
    ],
    "AWSDataTransfer": [
        {
            # Offer separado, só de transferência. É aqui que está a SAÍDA PARA
            # INTERNET — que não aparece no arquivo do EC2 (lá só há
            # inter-região) nem no do VPC.
            #
            # Filtro EXATO, e não substring: `~datatransfer-out-bytes` também
            # casava `Global-DataTransfer-Out-Bytes` (US$ 0,00) — verificado no
            # dump. E `StartingRange: 0` fixa o PRIMEIRO ESCALÃO (US$ 0,09/GB),
            # sem o qual casam também 0,085, 0,07 e 0,05.
            "id": "transferencia.internet",
            "descricao": "Transferência de dados para a internet (saída)",
            "ancora": {"usage type": "~datatransfer-out-bytes"},
            "igual": {
                "usage type": "DataTransfer-Out-Bytes",
                "unit": "GB",
                "starting range": "0",
            },
        },
    ],
}

# Serviços pequenos o bastante para o snapshot guardar TODAS as linhas da
# família, sem filtro. Serve para o dashboard oferecer escolha (ex.: classe do
# S3) sem nova coleta.
SERVICOS_PEQUENOS = {"AmazonS3", "AmazonECR"}


def norm(texto: str | None) -> str:
    """Normaliza nome de coluna ou valor para comparação tolerante."""
    return re.sub(r"[^a-z0-9]", "", (texto or "").lower())


def colunas(linha: dict) -> dict[str, str]:
    """Indexa a linha por nome de coluna normalizado."""
    return {norm(k): (v or "").strip() for k, v in linha.items() if k}


def valor(linha_norm: dict[str, str], chave: str) -> str:
    return linha_norm.get(norm(chave), "")


def casa(linha_norm: dict[str, str], condicoes: dict[str, str]) -> bool:
    """
    Todas as condições precisam casar. Comparação normalizada no VALOR também,
    porque o arquivo escreve `No License required` e `No License Required`
    conforme o serviço.

    Valor esperado começando com `~` é SUBSTRING. Existe porque nem sempre o
    identificador exato é conhecido de antemão, e adivinhar gera falha muda —
    foi assim que o IPv4 foi finalmente encontrado, depois de DUAS tentativas
    por igualdade (`Product Family: IP Address` casou zero linhas):

        {"usage type": "~ipv4", "usage type": "~inuseaddress"}
            -> USE1-PublicIPv4:InUseAddress

    A substring ignora o prefixo de região (`USE1-`), que muda por região e não
    deveria estar escrito à mão em consulta nenhuma.
    """
    for chave, esperado in condicoes.items():
        atual = valor(linha_norm, chave)
        if esperado.startswith("~"):
            if norm(esperado[1:]) not in norm(atual):
                return False
        elif norm(atual) != norm(esperado):
            return False
    return True


def ler_regiao(servico: str, regiao: str) -> dict:
    """
    Lê o `region_index.json` do serviço: é pequeno e é o PONTO DE ENTRADA
    oficial. Dele saem a `publicationDate`, a URL do arquivo da região E a
    LISTA DE TODAS AS REGIÕES que aquele serviço tem — é esse array que
    alimenta o seletor da aplicação, em vez de uma lista escrita à mão.

    ⚠️ PEGADINHA CONFIRMADA (2026-09-19): o `currentVersionUrl` vem ABSOLUTO,
    já começando com `/offers/v1.0/aws/...`. Concatenar com a `BASE` duplica o
    caminho e o servidor devolve 404:

        .../offers/v1.0/aws/offers/v1.0/aws/AmazonS3/20260918174747/us-east-1/

    Por isso o teste é sobre a barra inicial: caminho absoluto troca só o host,
    caminho relativo é o único caso em que se prefixa a base.
    """
    url = f"{BASE}/{servico}/current/region_index.json"
    with urllib.request.urlopen(url, timeout=60) as resp:
        indice = json.load(resp)
    regioes = sorted((indice.get("regions") or {}).keys())
    regiao_info = (indice.get("regions") or {}).get(regiao) or {}
    if not regiao_info:
        raise SystemExit(
            f"{servico}: região {regiao} não está no region_index "
            f"({len(regioes)} regiões disponíveis para este serviço)"
        )

    caminho = regiao_info["currentVersionUrl"]
    if caminho.startswith("/"):
        arquivo_json = "https://pricing.us-east-1.amazonaws.com" + caminho
    else:
        arquivo_json = f"{BASE}/{caminho}"

    return {
        "publicationDate": indice.get("publicationDate"),
        "version": regiao_info.get("version") or indice.get("version"),
        "csv": arquivo_json.replace(".json", ".csv"),
        "regioes_disponiveis": regioes,
    }


def varrer(
    servico: str,
    url_csv: str,
    consultas: list[dict],
    dump: list,
    catalogo: dict,
    progresso: bool = True,
):
    """
    Baixa e filtra em UMA passada, em streaming.

    Streaming é o ponto: o arquivo do EC2 tem 288,8 MB. `csv.DictReader` sobre
    o corpo da resposta consome linha a linha, então a memória fica baixa mesmo
    com o arquivo grande — ler tudo para depois filtrar não caberia tranquilo.

    ⚠️ O ARQUIVO TEM PREÂMBULO (confirmado lendo o arquivo real em 2026-09-19):

        "FormatVersion","v1.0"
        "Disclaimer","This pricing list is for informational purposes..."
        "Publication Date","2026-09-18T17:47:47Z"
        "Version","20260918174747"
        "OfferCode","AmazonS3"
        "SKU","OfferTermCode",...      <- o cabeçalho de verdade começa aqui

    Entregar isso ao `csv.DictReader` sem tratamento lê LIXO: a primeira linha
    vira cabeçalho e o resultado sai vazio — foi exatamente o que aconteceu no
    primeiro teste, com zero itens e nenhum erro.

    E o preâmbulo é útil: o `Publication Date` está ali. A data de procedência
    passa a vir do MESMO arquivo que foi lido, e não de uma segunda consulta.

    Devolve (achados, linhas_lidas, preambulo).
    """
    achados: dict[str, list[dict]] = {c["id"]: [] for c in consultas if not c.get("desativada")}
    ancoras: dict[str, list[dict]] = {c["id"]: [] for c in consultas}
    solto = servico in SERVICOS_PEQUENOS
    total_linhas = 0
    inicio = time.time()
    preambulo: dict[str, str] = {}
    # Diagnóstico que já pagou por si: quando uma consulta casa zero, a
    # primeira pergunta é "este arquivo tem o que eu procuro?". Contar as
    # famílias responde isso sem uma segunda passada de 288 MB — foi assim que
    # se descobriu que o IPv4 não mora no offer do EC2.
    familias: dict[str, int] = {}
    locais: dict[str, int] = {}

    req = urllib.request.Request(url_csv, headers={"User-Agent": "homelab-gitops/calculadora"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        corpo = io.TextIOWrapper(resp, encoding="utf-8-sig", newline="")
        cabecalho = None
        for linha in corpo:
            campos = next(csv.reader([linha]), [])
            if campos and norm(campos[0]) == "sku":
                cabecalho = campos
                break
            if len(campos) >= 2:
                preambulo[campos[0].strip()] = campos[1].strip()
        if not cabecalho:
            raise SystemExit(f"{servico}: cabeçalho (linha começando com SKU) não encontrado em {url_csv}")

        # `fieldnames` passado à mão: o cabeçalho já foi consumido acima, e
        # assim o corpo segue sendo lido em streaming, linha a linha.
        leitor = csv.DictReader(corpo, fieldnames=cabecalho)
        for linha in leitor:
            total_linhas += 1
            if progresso and total_linhas % 100000 == 0:
                print(
                    f"    ... {total_linhas:,} linhas lidas "
                    f"({time.time() - inicio:.0f}s)".replace(",", "."),
                    file=sys.stderr,
                )
            ln = colunas(linha)
            # SEM filtro de `Location`: o arquivo JÁ É o da região pedida —
            # quem garante isso é o `region_index`, que entrega a URL da região.
            # Filtrar por nome de localidade era redundante E obrigava a
            # escrever "US East (N. Virginia)" à mão no código: dado chapado,
            # exatamente o que não se quer. A contagem abaixo existe para o
            # nome da localidade ser DESCOBERTO do arquivo, não digitado.
            local = valor(ln, "location")
            if local:
                locais[local] = locais.get(local, 0) + 1
            familia_da_linha = valor(ln, "product family") or "(sem família)"
            familias[familia_da_linha] = familias.get(familia_da_linha, 0) + 1

            # CATÁLOGO DE INSTÂNCIAS — o "array com todos os modelos de EC2".
            # Sai do próprio arquivo, e não de uma lista minha: qualquer modelo
            # que a AWS publique naquela região entra aqui sozinho.
            if servico == "AmazonEC2" and norm(valor(ln, "product family")) == norm("Compute Instance"):
                if norm(valor(ln, "term type")) == "ondemand" and casa(ln, FILTRO_INSTANCIA):
                    tipo = valor(ln, "instance type")
                    if tipo and tipo not in catalogo:
                        catalogo[tipo] = {
                            "preco": valor(ln, "priceperunit"),
                            "unidade": valor(ln, "unit"),
                            "vcpu": valor(ln, "vcpu"),
                            "memoria": valor(ln, "memory"),
                            "familia": valor(ln, "instance family"),
                            "sku": valor(ln, "sku"),
                        }

            for consulta in consultas:
                if consulta.get("desativada"):
                    continue
                cid = consulta["id"]
                familia = consulta.get("familia")
                # Família só é filtrada quando a consulta DECLARA uma — e a
                # coluna vazia não conta como igual, senão as 282 linhas sem
                # família do arquivo do S3 passariam por engano.
                if familia and norm(valor(ln, "product family")) != norm(familia):
                    continue
                if consulta["ancora"] and not casa(ln, consulta["ancora"]):
                    continue
                if len(ancoras[cid]) < 400:
                    ancoras[cid].append(_resumo(ln))
                if solto and len(ancoras[cid]) >= 400:
                    continue
                # Só on-demand interessa: em janela de 7 dias não há Reserved
                # nem Savings Plan (ambos exigem compromisso).
                if norm(valor(ln, "term type")) != "ondemand":
                    continue
                if casa(ln, consulta["igual"]):
                    achados[cid].append(_resumo(ln))

    for consulta in consultas:
        cid = consulta["id"]
        dump.append(
            {
                "id": cid,
                "servico": servico,
                "descricao": consulta.get("descricao", ""),
                "casou": len(achados.get(cid, [])),
                "selecionados": achados.get(cid, [])[:6],
                "candidatos_ancora": ancoras.get(cid, [])[:120],
            }
        )
    return achados, total_linhas, preambulo, familias, locais, catalogo


def _resumo(ln: dict[str, str]) -> dict:
    """Recorta as colunas que importam para o snapshot — não a linha inteira."""
    return {
        "sku": valor(ln, "sku"),
        "preco": valor(ln, "priceperunit"),
        "unidade": valor(ln, "unit"),
        "moeda": valor(ln, "currency"),
        "efetivo_em": valor(ln, "effectivedate"),
        "termo": valor(ln, "termtype"),
        "descricao": valor(ln, "pricedescription"),
        "tipo_uso": valor(ln, "usagetype"),
        "operacao": valor(ln, "operation"),
        "familia": valor(ln, "product family"),
        "instance_type": valor(ln, "instance type"),
        "vcpu": valor(ln, "vcpu"),
        "memoria": valor(ln, "memory"),
        "so": valor(ln, "operating system"),
        "tenancy": valor(ln, "tenancy"),
        "capacidade": valor(ln, "capacitystatus"),
        "volume_api": valor(ln, "volume api name"),
        "classe_storage": valor(ln, "storage class"),
        "grupo": valor(ln, "group"),
        "de": valor(ln, "from location"),
        "para": valor(ln, "to location"),
        "tipo_transferencia": valor(ln, "transfer type"),
    }


def escolher(consulta: dict, candidatos: list[dict]) -> dict | None:
    """
    Exige UM ÚNICO candidato. Casando mais de um, NÃO escolhe — devolve None.

    Motivo, aprendido de TRÊS erros em sequência nesta sessão (2026-09-19):
    a versão anterior desempatava pelo MENOR preço. Deu errado nas três:

      1. egress no arquivo do EC2 -> pegou US$ 0,02/GB (inter-região) em vez da
         saída internet, que nem está naquele arquivo;
      2. o IP virou lacuna por outro motivo, mas o padrão se repetia;
      3. egress no AWSDataTransfer -> pegou US$ 0,00/GB de uma variante
         `Global-*`, com 4 candidatos descartados, porque `min` escolhe o
         ESCALÃO mais barato e o filtro por substring também casou a global.

    O erro de fundo não é o filtro: é desempatar por preço. Filtro frouxo com
    desempate por preço é como um painel de custo passa a mentir com cara de
    número certo. Preço AUSENTE é visível e alguém corrige; preço ERRADO não
    chama ninguém.

    Por isso a ambiguidade agora falha alto: o chamador transforma o None em
    problema declarado, com o número de candidatos, e a linha vai para
    `lacunas` em vez de entrar no total.
    """
    validos = [c for c in candidatos if c.get("preco")]
    if len(validos) == 1:
        return validos[0]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Coleta preços oficiais da AWS em snapshot")
    parser.add_argument("--servicos", default=",".join(CONSULTAS), help="serviços separados por vírgula")
    parser.add_argument(
        "--regiao",
        default=REGIAO_PADRAO,
        help="região a precificar; a lista completa de regiões vem da fonte, não do código",
    )
    parser.add_argument("--dump", default=None, help="grava os candidatos crus para inspeção")
    parser.add_argument(
        "--saida",
        default=str(Path(__file__).resolve().parent / "dados" / "prices.json"),
    )
    args = parser.parse_args()

    servicos = [s.strip() for s in args.servicos.split(",") if s.strip()]
    regiao = args.regiao
    itens: dict[str, dict] = {}
    fontes: dict[str, dict] = {}
    dump: list[dict] = []
    problemas: list[str] = []
    avisos: list[str] = []
    catalogo: dict[str, dict] = {}
    locais: dict[str, int] = {}
    regioes: list[str] = []

    # O array de SERVIÇOS vem do índice raiz da lista oficial — não de uma
    # lista minha. É o que permite o seletor da aplicação mostrar tudo o que a
    # AWS publica preço, sem eu manter catálogo.
    catalogo_servicos: dict[str, str] = {}
    try:
        with urllib.request.urlopen(RAIZ_OFERTAS, timeout=60) as resp:
            raiz = json.load(resp)
        catalogo_servicos = {
            codigo: (info or {}).get("offerCode", codigo)
            for codigo, info in (raiz.get("offers") or {}).items()
        }
        print(f"índice raiz: {len(catalogo_servicos)} serviços publicados")
    except Exception as erro:  # noqa: BLE001 — aviso, não fatal: o snapshot ainda presta
        avisos.append(f"índice raiz de serviços indisponível: {erro}")

    for servico in servicos:
        consultas = CONSULTAS.get(servico)
        if not consultas:
            raise SystemExit(f"serviço desconhecido em CONSULTAS: {servico}")
        print(f"[{servico}] descobrindo o arquivo da região...", file=sys.stderr)
        info = ler_regiao(servico, regiao)
        if not regioes:
            regioes = info["regioes_disponiveis"]
        print(
            f"[{servico}] publicationDate={info['publicationDate']}  "
            f"regioes={len(info['regioes_disponiveis'])}  "
            f"versao={info['version']}\n[{servico}] lendo {info['csv']}",
            file=sys.stderr,
        )
        achados, linhas, preambulo, familias, locais_do_arquivo, catalogo = varrer(
            servico, info["csv"], consultas, dump, catalogo
        )
        locais.update(locais_do_arquivo)
        for consulta in consultas:
            if consulta.get("desativada"):
                continue
            cid = consulta["id"]
            escolhido = escolher(consulta, achados[cid])
            if not escolhido:
                quantos = len(achados[cid])
                if quantos > 1:
                    # Ambiguidade: o filtro precisa ficar exato. A mensagem diz
                    # o que fazer (ver o --dump) em vez de só reclamar.
                    problemas.append(
                        f"{cid}: {quantos} candidatos casaram — filtro precisa ser exato; "
                        "ver o --dump e fixar por usageType + StartingRange"
                    )
                else:
                    problemas.append(f"{cid}: nenhuma linha casou (serviço {servico})")
                continue
            itens[cid] = {
                "descricao": consulta["descricao"],
                "servico": servico,
                **escolhido,
            }
        fontes[servico] = {
            "publicationDate": preambulo.get("Publication Date") or info["publicationDate"],
            "version": preambulo.get("Version") or info["version"],
            "offerCode": preambulo.get("OfferCode") or servico,
            "url_csv": info["csv"],
            "linhas_varridas": linhas,
            "regioes_disponiveis": len(info["regioes_disponiveis"]),
            "familias_no_arquivo": dict(sorted(familias.items(), key=lambda kv: -kv[1])),
        }

    # O nome da LOCALIDADE sai do arquivo (a localidade que mais aparece entre
    # as linhas lidas), em vez de estar escrito no código.
    localidade = max(locais, key=locais.get) if locais else ""

    snapshot = {
        "gerado_em": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "regiao": regiao,
        "localidade": localidade,
        # Arrays DESCOBERTOS da fonte oficial. É daqui que os seletores da
        # aplicação se alimentam — e não de listas escritas no código.
        "regioes_disponiveis": regioes,
        "servicos_disponiveis": catalogo_servicos,
        "catalogo_ec2": dict(sorted(catalogo.items())),
        "premissa": (
            "Preços on-demand, Linux, tenancy Shared. Em janela de 7 dias não se "
            "aplicam Reserved Instance nem Savings Plans: ambos exigem compromisso "
            "de 1 a 3 anos, então on-demand é a única resposta honesta."
        ),
        "escopo": (
            "O catálogo de instâncias e os preços valem para UMA região por coleta. "
            "O array de regiões lista todas as que o serviço tem, mas só é possível "
            "PRECIFICAR a região que foi coletada — oferecer as outras sem dado seria "
            "mostrar número inventado."
        ),
        "fonte": {
            "descricao": "AWS Bulk Price List (público, sem credencial)",
            "base": BASE,
            "endpoint_api_filtrada": "api.pricing.us-east-1.amazonaws.com",
            "observacao_api_filtrada": (
                "Exige SigV4. Sem credencial devolve MissingAuthenticationTokenException. "
                "É o modo 'preciso', para quando houver conta AWS real."
            ),
            "servicos": fontes,
        },
        "itens": itens,
        "problemas": problemas,
        "avisos": avisos,
    }

    destino = Path(args.saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nsnapshot: {destino}  ({destino.stat().st_size} bytes, {len(itens)} itens)", file=sys.stderr)
    for cid, item in itens.items():
        print(f"  {cid:22s} {item['moeda']} {item['preco']:>10s} / {item['unidade']}", file=sys.stderr)
    for p in problemas:
        print(f"  ✖ {p}", file=sys.stderr)
    for a in avisos:
        print(f"  ⚠ {a}", file=sys.stderr)

    if args.dump:
        Path(args.dump).write_text(json.dumps(dump, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"dump de candidatos: {args.dump}", file=sys.stderr)

    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
