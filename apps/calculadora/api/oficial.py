"""Cliente das fontes públicas da calculadora de custo da AWS.

Três fontes, todas públicas e SEM credencial (verificadas em 2026-09-20 —
evidências em `docs/calculadora/01-plano.md` §1):

1. Catálogo        — manifest com os 440 serviços e a URL da definição de cada um
2. Mapa de preço   — o mapa que a PRÓPRIA calculadora da AWS consome
3. Bulk Price List — o preço oficial da AWS

── POR QUE ISTO EXISTE ────────────────────────────────────────────────────────
O mapa da calculadora da AWS é indexado por `rateCode`, que é a MESMA chave do
Bulk Price List (`SKU.oferta.versão`). Isso permite conferir preço a preço, sem
navegador e sem interpretação: bate ou não bate.

É esse join que sustenta a afirmação de que nenhum número sai sem procedência.
Se um dia divergir, o relatório aponta o `rateCode` exato.

── ARMADILHAS JÁ CONHECIDAS (custaram tempo) ──────────────────────────────────
• O mapa de preço NÃO está no CloudFront do manifest: está em `calculator.aws`.
  Pedir no host errado devolve 403, que parece "não existe" mas é host errado.
• A resposta vem em gzip mesmo sem pedirmos. Descomprimir antes de ler.
• `regions` do manifest pode vir VAZIO em serviço ativo (o Lambda vem). Não serve
  para filtrar serviço por região.
• O manifest NÃO declara categoria nem dependência. A hierarquia está em
  `templates` (pai aponta os filhos) e a faceta `hasDataTransfer`.
• A família do mapa (`kms`, `eks`) NÃO é o offerCode do Price List
  (`awskms`, `AmazonEKS`). O casamento é por busca + confirmação por interseção
  de `rateCode` — nunca por chute.
"""

import gzip
import hashlib
import json
import os
import urllib.error
import urllib.request
from decimal import Decimal

MANIFEST_URL = "https://d1qsjq9pzbk1k6.cloudfront.net/manifest/en_US.json"
PRICING_BASE = "https://pricing.us-east-1.amazonaws.com"
MAPA_BASE = "https://calculator.aws/"

CABECALHOS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://calculator.aws/",
    "Origin": "https://calculator.aws",
}

CACHE_PADRAO = "/tmp/calculadora-cache"

# O rótulo que a oficial usa não é o código do Price List. Começamos pela região
# que já provamos; as 37 da oficial entram como arquivo de dados na F1b.
REGIAO_PADRAO = {"rotulo_oficial": "US East (N. Virginia)", "codigo_price_list": "us-east-1"}

# ── correspondência família → offerCode (DADO, não heurística) ────────────────
# Não é dedutível por nome: 'datatransfer-calc' → AWSDataTransfer,
# 'rds-mysql-ondemand' → AmazonRDS, 'queueservice' → AWSQueueService.
# Cada linha de `dados/correspondencia.json` foi confirmada por INTERSEÇÃO de
# rateCode com o mapa oficial — nunca por semelhança de nome.
ARQUIVO_CORRESPONDENCIA = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "dados", "correspondencia.json"
)

_correspondencia = None


def correspondencia():
    """Carrega (uma vez) a tabela família → oferta e as ofertas companheiras."""
    global _correspondencia
    if _correspondencia is None:
        with open(os.path.abspath(ARQUIVO_CORRESPONDENCIA), encoding="utf-8") as arquivo:
            _correspondencia = json.load(arquivo)
    return _correspondencia


def ofertas_da_familia(familia):
    """As ofertas do Price List que publicam os preços desta família."""
    entrada = (correspondencia().get("familias") or {}).get(familia) or {}
    oferta = entrada.get("oferta")
    return [oferta] if oferta else []


def ofertas_companheiras():
    """Ofertas que aparecem DENTRO de mapas alheios (transferência, sobretudo)."""
    return correspondencia().get("ofertas_companheiras") or []


# ── rede ─────────────────────────────────────────────────────────────────────

def baixar(url, cache_dir=CACHE_PADRAO, timeout=240, usar_cache=True):
    """Baixa uma URL tratando gzip. Guarda em disco para não repetir download.

    O cache é por hash da URL: o mapa do EKS tem 4,2 MB e é baixado a cada
    conferência, o que seria desperdício puro.
    """
    if usar_cache:
        os.makedirs(cache_dir, exist_ok=True)
        chave = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        caminho = os.path.join(cache_dir, chave)
        if os.path.exists(caminho):
            with open(caminho, "rb") as f:
                return f.read()

    pedido = urllib.request.Request(url, headers=CABECALHOS)
    with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
        bruto = resposta.read()

    if bruto[:2] == b"\x1f\x8b":
        bruto = gzip.decompress(bruto)

    if usar_cache:
        with open(caminho, "wb") as f:
            f.write(bruto)
    return bruto


def baixar_json(url, **kwargs):
    return json.loads(baixar(url, **kwargs))


# ── catálogo ─────────────────────────────────────────────────────────────────

def manifesto(cache_dir=CACHE_PADRAO):
    """Todos os serviços que a calculadora da AWS sabe precificar (440)."""
    dados = baixar_json(MANIFEST_URL, cache_dir=cache_dir)
    return {s.get("serviceCode"): s for s in dados["awsServices"]}


def definicao_do_servico(catalogo, service_code, cache_dir=CACHE_PADRAO):
    """A definição de um serviço — é ela que descreve o formulário e os preços."""
    entrada = catalogo.get(service_code)
    if not entrada:
        raise KeyError(f"serviço {service_code!r} não está no catálogo")
    return baixar_json(entrada["serviceDefinitionLocation"], cache_dir=cache_dir), entrada


def mapas_de_preco(definicao, moeda="USD"):
    """Os mapas de preço que a definição declara.

    Um serviço pode ter MAIS DE UM (o Route 53 tem `route53` e
    `route53regionalchina`). Devolver lista, nunca "o mapa".
    """
    mapas = []
    for md in definicao.get("mappingDefinitions") or []:
        caminho = md.get("mappingDefinitionURL") or ""
        if "meteredUnitMaps" not in caminho:
            continue
        relativo = caminho.replace("[currency]", moeda)
        url = relativo if relativo.startswith("http") else MAPA_BASE + relativo
        mapas.append({"familia": md.get("mappingDefinitionName"), "url": url})
    return mapas


# ── preços ───────────────────────────────────────────────────────────────────

def indice_ofertas(cache_dir=CACHE_PADRAO):
    """As ~271 ofertas do Price List, para casar família -> offerCode."""
    return list(baixar_json(f"{PRICING_BASE}/offers/v1.0/aws/index.json", cache_dir=cache_dir)["offers"].keys())


def ratecodes_do_price_list(offer_code, regiao_codigo, cache_dir=CACHE_PADRAO):
    """rateCode -> preço, direto do Bulk Price List (a nossa fonte)."""
    indice = baixar_json(f"{PRICING_BASE}/offers/v1.0/aws/{offer_code}/current/region_index.json",
                         cache_dir=cache_dir)
    regiao = (indice.get("regions") or {}).get(regiao_codigo)
    if not regiao:
        return {}, None
    url = regiao["currentVersionUrl"]
    if not url.startswith("http"):
        url = PRICING_BASE + url
    arquivo = baixar_json(url, cache_dir=cache_dir)

    precos = {}
    for termos in (arquivo.get("terms", {}).get("OnDemand", {}) or {}).values():
        for oferta in termos.values():
            for rate_code, dimensao in (oferta.get("priceDimensions") or {}).items():
                valor = (dimensao.get("pricePerUnit") or {}).get("USD")
                if valor is not None:
                    precos[rate_code] = Decimal(str(valor))
    return precos, arquivo.get("publicationDate")


def itens_da_estrutura(mapa, rotulo_regiao):
    """Os itens da região, a partir de um mapa JÁ lido.

    Separado de `itens_do_mapa` para a carga poder aproveitar os bytes que já
    baixou (e calcular o hash do conteúdo exato) sem reabrir o arquivo. A
    navegação do JSON mora aqui, num lugar só.
    """
    entrada = (mapa.get("regions") or {}).get(rotulo_regiao)
    if not entrada:
        return []
    return [item for item in entrada.values() if isinstance(item, dict) and item.get("rateCode")]


def itens_do_mapa(url_mapa, rotulo_regiao, cache_dir=CACHE_PADRAO):
    """Os itens CRUS do mapa na região, sem recortar nada.

    Devolve (itens, mapa). Lista vazia quando a região não está no mapa — e isso
    NÃO é erro: os mapas terminados em `-calc` vêm com `regions` vazio, porque
    são de outro formato, sem eixo de região.
    """
    mapa = baixar_json(url_mapa, cache_dir=cache_dir)
    return itens_da_estrutura(mapa, rotulo_regiao), mapa


def ratecodes_do_mapa(url_mapa, rotulo_regiao, cache_dir=CACHE_PADRAO):
    """rateCode -> preço, do mapa que a calculadora da AWS consome."""
    itens, mapa = itens_do_mapa(url_mapa, rotulo_regiao, cache_dir)
    return {item["rateCode"]: Decimal(str(item.get("price"))) for item in itens}, mapa


# `escolher_oferta` foi REMOVIDA. Casar família→oferta por heurística de nome
# escolheu a oferta errada no Aurora: 'maior interseção' elegeu o AmazonS3 com 267
# coincidências, em vez do AmazonRDS. O erro não apareceu como falha — apareceu
# como 267 acertos e 337 ausências. Hoje a correspondência vem de
# `dados/correspondencia.json`, e o índice soma TODAS as ofertas do serviço mais
# as companheiras, porque um mapa pode conter dimensão publicada em outra oferta.


# ── conferência ──────────────────────────────────────────────────────────────

def conferir(catalogo, service_code, regiao=None, cache_dir=CACHE_PADRAO):
    """Confere um serviço: mapa oficial x Bulk Price List, por `rateCode`.

    Devolve um relatório. Nunca levanta exceção por divergência — divergência é
    resultado, não erro.
    """
    regiao = regiao or REGIAO_PADRAO
    relatorio = {
        "service_code": service_code,
        "nome": None, "sub_tipo": None,
        "definicao_versao": None,
        "mapas": [], "oferta": None,
        "publicacao_mapa": None, "publicacao_price_list": None,
        "iguais": 0, "diferentes": [], "ausentes": [],
        "motivo": None, "status": "FALHA",
    }

    try:
        definicao, entrada = definicao_do_servico(catalogo, service_code, cache_dir)
    except (KeyError, urllib.error.HTTPError, urllib.error.URLError) as erro:
        relatorio["motivo"] = f"definição indisponível: {erro}"
        return relatorio

    relatorio["nome"] = entrada.get("name")
    relatorio["sub_tipo"] = entrada.get("subType")
    relatorio["definicao_versao"] = definicao.get("version")

    mapas = mapas_de_preco(definicao)
    relatorio["mapas"] = [m["familia"] for m in mapas]

    if not mapas:
        # Pai (subServiceSelector) não tem preço próprio: quem precifica são os
        # filhos, que estão em `templates`. Isto NÃO é falha.
        filhos = entrada.get("templates") or []
        relatorio["status"] = "FILHO_NECESSARIO"
        relatorio["motivo"] = f"sem mappingDefinitions; filhos declarados: {len(filhos)}"
        return relatorio

    oficial_total = {}
    familias_com_regiao = []
    mapas_sem_regiao = 0
    for mapa in mapas:
        try:
            precos, meta = ratecodes_do_mapa(mapa["url"], regiao["rotulo_oficial"], cache_dir)
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as erro:
            relatorio["motivo"] = f"mapa {mapa['familia']} indisponível: {erro}"
            continue
        if not precos:
            # Família sem eixo de região: os mapas "-calc" vêm com `regions` VAZIO.
            # Não é falha nem falta de região — é outro formato de mapa, com preço
            # resolvido por combinação de campos em vez de por região. O Route 53
            # também cai aqui às vezes: ele declara dois mapas e o da China não tem
            # us-east-1. Por isso a família vem do mapa que TEM a região.
            mapas_sem_regiao += 1
            continue
        oficial_total.update(precos)
        familias_com_regiao.append(mapa["familia"])
        relatorio["publicacao_mapa"] = (meta.get("manifest") or {}).get("hawkFilePublicationDate")

    relatorio["mapas_sem_regiao"] = mapas_sem_regiao

    if not oficial_total:
        relatorio["status"] = "SEM_MAPA"
        relatorio["motivo"] = relatorio["motivo"] or f"nenhum mapa tem {regiao['rotulo_oficial']}"
        return relatorio

    # O índice NÃO é uma oferta só. Um mapa de serviço costuma carregar dimensões
    # publicadas em OUTRA oferta: o mapa do SQS e o do Kinesis Video trazem 155
    # rateCodes com a data de publicação do AWSDataTransfer, e o do Redshift traz
    # preço de S3. Então indexamos todas as ofertas das famílias DESTE serviço mais
    # as companheiras — e a ausência passa a ser ausência no índice, não "ausência
    # no Price List", que seria afirmação forte demais.
    ofertas = []
    for familia in familias_com_regiao:
        for oferta in ofertas_da_familia(familia):
            if oferta not in ofertas:
                ofertas.append(oferta)
    for companheira in ofertas_companheiras():
        if companheira not in ofertas:
            ofertas.append(companheira)

    precos_nossos = {}
    publicacoes = set()
    for oferta in ofertas:
        try:
            precos, publicacao = ratecodes_do_price_list(oferta, regiao["codigo_price_list"], cache_dir)
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
            continue
        precos_nossos.update(precos)
        if publicacao:
            publicacoes.add(publicacao)

    relatorio["ofertas_indexadas"] = ofertas
    relatorio["oferta"] = ",".join(ofertas)
    relatorio["publicacao_price_list"] = ",".join(sorted(publicacoes)) or None

    if not precos_nossos:
        relatorio["status"] = "SEM_OFERTA"
        relatorio["motivo"] = f"nenhuma oferta indexada tem preço em {regiao['codigo_price_list']}"
        return relatorio

    for rate_code, preco_oficial in oficial_total.items():
        nosso = precos_nossos.get(rate_code)
        if nosso is None:
            relatorio["ausentes"].append(rate_code)
        elif nosso == preco_oficial:
            relatorio["iguais"] += 1
        else:
            relatorio["diferentes"].append({"rate_code": rate_code,
                                            "oficial": str(preco_oficial),
                                            "price_list": str(nosso)})

    relatorio["status"] = "DIVERGENTE" if (relatorio["diferentes"] or relatorio["ausentes"]) else "VERIFICADO"
    return relatorio
