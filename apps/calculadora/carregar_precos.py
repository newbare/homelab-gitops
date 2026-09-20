#!/usr/bin/env python3
"""
Carga dos preços oficiais da AWS no PostgreSQL — fase F2 do plano.

Por que existe separado do `buscar_precos.py`
============================================
Os dois baixam preço oficial, e é de propósito que sejam dois:

  `buscar_precos.py`  ->  snapshot JSON  ->  a aplicação que existe HOJE
      Consultas CURADAS (o preço do m3.large, o do gp3…), conjunto fechado de
      itens, e o resultado é o arquivo que o dashboard serve.

  `carregar_precos.py`  ->  PostgreSQL  ->  o motor AGNÓSTICO (F2 em diante)
      Carrega o mapa INTEIRO de cada serviço — 10 mil rateCodes, não 10 itens —
      para que qualquer serviço do catálogo possa ser precificado depois sem
      código novo. É a diferença entre "a vitrine" e "o motor".

O QUE ESTE ARQUIVO SE RECUSA A FAZER
====================================
1. **Não apaga preço.** A carga nova marca os anteriores como histórico
   (`vigente = false`). É o que permite responder depois "por que o mês passado
   deu outro número?" — e é a lição do `orig`/`latest` do ISU-HPC.

2. **Não grava se a fonte se contradizer.** Antes de tocar na base, confere
   `rateCode` por `rateCode` contra o mapa da própria calculadora da AWS (a
   fase F1). Divergência de VALOR recusa a carga inteira: base intacta, preço
   antigo (que era íntegro) continua valendo, e o `carga_log` registra a
   recusa.

3. **Não confunde ausência com erro.** 86 rateCodes do Redshift existem no mapa
   da calculadora e não no Bulk Price List — medido em F1, e IRREDUTÍVEL: nenhuma
   outra oferta os contém. Ausência vira AVISO registrado; só preço que JÁ
   ESTAVA na base e sumiu do mapa é que recusa a carga.

4. **Não trata mapa sem região como falha.** Os mapas terminados em `-calc` vêm
   com `regions` VAZIO: são de outro formato, sem eixo de região. Contados à
   parte, nunca como erro.

Uso
===
    python3 carregar_precos.py --dry-run          # confere tudo, não grava
    python3 carregar_precos.py                    # carga completa do escopo
    python3 carregar_precos.py --sem-conferir     # sem o portão do F1 (rápido)
    python3 carregar_precos.py --servico aWSLambda  # só um serviço

Credenciais vêm do ambiente (`PGHOST`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`) —
nenhuma senha mora no código. Ver `api/pg.py`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "api"))

import oficial  # noqa: E402  (o módulo que fala com as fontes da AWS)
import pg  # noqa: E402  (o cliente PostgreSQL em biblioteca padrão)

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------
SQL_REGIAO = """
INSERT INTO regiao (codigo, rotulo, disponivel, visto_em)
VALUES ($1, $2, TRUE, now())
ON CONFLICT (codigo) DO UPDATE SET rotulo = EXCLUDED.rotulo, disponivel = TRUE, visto_em = now()
"""

SQL_MAPA = """
INSERT INTO mapa_preco (familia, offer_code, publicacao_em, moeda, url_origem, hash_conteudo, carregado_por)
VALUES ($1, $2, $3::timestamptz, 'USD', $4, $5, $6)
ON CONFLICT (hash_conteudo) DO UPDATE SET familia = EXCLUDED.familia
RETURNING id
"""

# Histórico: o preço anterior NÃO é apagado, só deixa de ser o vigente.
#
# ⚠️ A demolição é por RATECODE (contra uma tabela temporária com os que vão
# entrar) e NÃO por família. Motivo, medido na primeira carga de verdade: o mesmo
# rateCode pode ser declarado por MAIS DE UM mapa (`redshift` e `redshift-storage`
# publicam os mesmos 140), e a linha vigente dele está ligada a UM mapa só. Com a
# demolição por família, o rateCode cujo mapa de origem não viesse nesta carga
# continuaria vigente — e o INSERT do novo estouraria o índice único parcial com
# um erro cru de chave duplicada, no meio da transação.
SQL_HISTORICO = """
UPDATE preco SET vigente = FALSE
WHERE vigente AND regiao_codigo = $1
  AND rate_code IN (SELECT rate_code FROM _precos_novos)
"""

# Os rateCodes que JÁ estavam vigentes nesta região. É contra este conjunto que o
# portão pergunta "alguma dimensão que já usávamos desapareceu do mapa?" — e a
# pergunta é feita pelo rateCode, não pela família, porque o rateCode é a
# identidade da dimensão.
SQL_RATECODES_VIGENTES = """
SELECT rate_code FROM preco WHERE vigente AND regiao_codigo = $1
"""

# Tabela temporária com os rateCodes desta carga: é ela que permite demolir o
# vigente por lista, num comando só, sem montar array em texto. `ON COMMIT DROP`
# porque só existe durante a transação da carga.
SQL_CRIAR_TEMP_NOVOS = """
CREATE TEMPORARY TABLE _precos_novos (rate_code TEXT PRIMARY KEY) ON COMMIT DROP
"""

SQL_HASHES_CARREGADOS = "SELECT hash_conteudo FROM mapa_preco"

SQL_CARGA_LOG = """
INSERT INTO carga_log (concluido_em, duracao_ms, resultado, regiao_codigo, publicacoes, mapas,
                       precos_novos, precos_historico, verificadas, divergentes, ausentes,
                       mensagem, executado_por)
VALUES (now(), $1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10, $11, $12)
RETURNING id
"""

COLUNAS_SERVICO = ("service_code", "nome", "descricao", "sub_tipo", "is_active",
                   "definition_url", "parent_service_code")

COLUNAS_PRECO = ("mapa_preco_id", "rate_code", "sku", "regiao_codigo", "preco",
                 "unidade", "descricao", "familia_produto", "atributos", "vigente")


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------
def agora_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_de(bruto: bytes) -> str:
    return hashlib.sha256(bruto).hexdigest()


def sku_do_ratecode(rate_code: str) -> str | None:
    """
    O `rateCode` tem a forma `SKU.oferta.versão` (ex.:
    `ZZQXJMTMJJG6F4RP.JRTCKXETXF.6YS6EN2CT7`), confirmado em 10.150 comparações
    na F1. O SKU é a primeira parte — derivar daqui evita uma coluna a mais na
    fonte e uma junção a mais na leitura.
    """
    partes = (rate_code or "").split(".")
    return partes[0] if len(partes) >= 2 else None


def tamanho_remoto(url: str, timeout: float = 20.0) -> int | None:
    """
    Tamanho do arquivo pela resposta do `HEAD`, ANTES de baixar.

    Existe por causa de um caso concreto: o arquivo do EC2 em us-east-1 tem
    120.658 rateCodes e centenas de MB. Baixar e depois reclamar não serve —
    a memória já foi. Com o tamanho antes, a decisão de pular é tomada antes do
    download. Devolve None quando o servidor não informa (aí a decisão é tomada
    depois, sobre os bytes já em memória).
    """
    pedido = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
            bruto = resposta.headers.get("Content-Length")
            return int(bruto) if bruto else None
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, OSError):
        return None


def enriquecer_com_price_list(familias: set[str], regiao_codigo: str, limite_mb: float,
                              cache_dir: str) -> tuple[dict[str, dict], list[str]]:
    """
    Unidade e descrição de cada rateCode, do Bulk Price List.

    Por que isto é necessário: o mapa da calculadora traz `rateCode` e `price`,
    e nada mais. **A unidade não está lá** — e sem unidade não se sabe que
    `Hrs` multiplica por hora e `GB-Mo` precisa ser pro-rateado. A unidade vem
    daqui, casada pelo MESMO `rateCode`.

    O limite de tamanho é explícito e o que foi pulado é REPORTADO: preferir
    unidade ausente (visível) a travar a carga inteira por causa de um arquivo
    gigante (invisível).
    """
    detalhes: dict[str, dict] = {}
    pulados: list[str] = []
    for familia in sorted(familias):
        ofertas = oficial.ofertas_da_familia(familia)
        if not ofertas:
            continue
        oferta = ofertas[0]
        indice = f"{oficial.PRICING_BASE}/offers/v1.0/aws/{oferta}/current/region_index.json"
        try:
            dados = oficial.baixar_json(indice, cache_dir=cache_dir)
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
            pulados.append(f"{familia} ({oferta}): índices indisponíveis")
            continue
        entrada = (dados.get("regions") or {}).get(regiao_codigo)
        if not entrada:
            pulados.append(f"{familia} ({oferta}): sem {regiao_codigo}")
            continue
        url = entrada["currentVersionUrl"]
        if not url.startswith("http"):
            url = oficial.PRICING_BASE + url

        tamanho = tamanho_remoto(url)
        if tamanho is not None and tamanho > limite_mb * 1024 * 1024:
            pulados.append(
                f"{familia} ({oferta}): {tamanho / 1048576:.0f} MB acima do limite de {limite_mb:.0f} MB"
            )
            continue

        try:
            bruto = oficial.baixar(url, cache_dir=cache_dir)
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as erro:
            pulados.append(f"{familia} ({oferta}): {type(erro).__name__}")
            continue
        if len(bruto) > limite_mb * 1024 * 1024:
            pulados.append(f"{familia} ({oferta}): {len(bruto) / 1048576:.0f} MB acima do limite")
            continue
        try:
            arquivo = json.loads(bruto)
        except ValueError:
            pulados.append(f"{familia} ({oferta}): JSON ilegível")
            continue

        for termos in (arquivo.get("terms", {}).get("OnDemand", {}) or {}).values():
            for oferta_termo in termos.values():
                for rate_code, dimensao in (oferta_termo.get("priceDimensions") or {}).items():
                    detalhes[rate_code] = {
                        "unidade": dimensao.get("unit"),
                        "descricao": dimensao.get("description"),
                    }
    return detalhes, pulados


def inserir_em_lotes(con, tabela: str, colunas: tuple[str, ...], linhas: list[tuple],
                     lote: int = 500) -> int:
    """
    INSERT de várias linhas por comando.

    Inserir uma a uma custaria uma ida e volta de rede por linha — 10 mil
    linhas seriam 10 mil idas e voltas. Com lote, são 20 comandos. O limite do
    protocolo é 65.535 parâmetros por comando, e o lote padrão de 500 linhas
    com 10 colunas usa 5.000 — folga larga.
    """
    total = 0
    for inicio in range(0, len(linhas), lote):
        pedaco = linhas[inicio : inicio + lote]
        marcadores = []
        parametros: list = []
        n = 0
        for linha in pedaco:
            celulas = []
            for valor in linha:
                n += 1
                celulas.append(f"${n}")
                parametros.append(valor)
            marcadores.append("(" + ", ".join(celulas) + ")")
        sql = f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES " + ", ".join(marcadores)
        con.comando(sql, parametros)
        total += len(pedaco)
    return total


def linhas_de_servico(catalogo: dict) -> list[tuple]:
    """
    Uma linha por serviço do manifest (440), com o PAI resolvido.

    O manifest não diz quem é filho de quem: quem diz é o pai, declarando os
    filhos em `templates`. Então a hierarquia é INVERTIDA aqui, em vez de ser
    escrita à mão numa tabela de exceções que envelhece.
    """
    pai_de: dict[str, str] = {}
    for codigo, entrada in catalogo.items():
        for filho in entrada.get("templates") or []:
            pai_de.setdefault(filho, codigo)
    return [
        (
            entrada.get("serviceCode"),
            entrada.get("name"),
            entrada.get("description"),
            entrada.get("subType"),
            bool(entrada.get("isActive")),
            entrada.get("serviceDefinitionLocation"),
            pai_de.get(entrada.get("serviceCode")),
        )
        for entrada in catalogo.values()
    ]


def servicos_do_escopo(catalogo: dict, escopo: dict, so_um: str | None) -> list[str]:
    """
    Os serviços a varrer: as raízes do escopo MAIS os filhos que elas declaram.

    Os filhos entram porque é neles que está o preço — o pai
    (`subServiceSelector`) quase sempre não tem preço próprio, só a lista de
    quem precifica.

    Filho declarado que não existe no catálogo é IGNORADO: não há definição para
    buscar, e tentar só produziria erro de rede disfarçado de erro de dado.
    """
    if so_um:
        return [so_um]
    codigos: list[str] = []
    for linha in escopo["linhas"]:
        for codigo in linha.get("raizes") or []:
            if codigo not in codigos:
                codigos.append(codigo)
            for filho in (catalogo.get(codigo) or {}).get("templates") or []:
                if filho in catalogo and filho not in codigos:
                    codigos.append(filho)
    return codigos


# ---------------------------------------------------------------------------
# carga
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Carrega os preços oficiais da AWS no PostgreSQL (F2)")
    parser.add_argument("--dry-run", action="store_true", help="confere tudo e não grava nada")
    parser.add_argument("--sem-conferir", action="store_true",
                        help="pula o portão do F1 (conferência rateCode contra a calculadora oficial)")
    parser.add_argument("--servico", default=None, help="limita a um serviceCode")
    parser.add_argument("--regiao-codigo", default=None, help="código do Price List (us-east-1)")
    parser.add_argument("--regiao-rotulo", default=None, help="rótulo do mapa (US East (N. Virginia))")
    parser.add_argument("--cache", default=oficial.CACHE_PADRAO)
    parser.add_argument("--enriquecer", action="store_true",
                        help="busca unidade e descrição de cada rateCode no Bulk Price List")
    parser.add_argument("--limite-mb", type=float, default=80.0,
                        help="tamanho máximo de arquivo do Price List para enriquecer (MB)")
    parser.add_argument("--por", default=os.environ.get("USER") or "desconhecido",
                        help="quem executou (vai para carga_log.executado_por)")
    parser.add_argument("--json", action="store_true", help="resumo em JSON, para script")
    parser.add_argument("--aplicar-schema", action="store_true",
                        help="aplica sql/001-schema.sql e encerra (idempotente)")
    parser.add_argument("--conferir-carga", action="store_true",
                        help="mostra o que está na base e encerra (sem baixar nada)")
    args = parser.parse_args()

    # Dois modos de operação que não carregam preço: criar a estrutura e
    # CONFERIR o que foi carregado. Existem para o `make` ter um comando por
    # passo — e para o schema não depender de um `psql` instalado na máquina,
    # que é justamente o que o cliente em biblioteca padrão evita.
    if args.aplicar_schema or args.conferir_carga:
        return _modo_banco(args)

    inicio = time.time()
    escopo = json.loads((BASE / "dados" / "escopo.json").read_text(encoding="utf-8"))
    regiao_padrao = escopo["regiao_de_verificacao"]
    rotulo = args.regiao_rotulo or regiao_padrao["rotulo_oficial"]
    codigo = args.regiao_codigo or regiao_padrao["codigo_price_list"]

    resumo: dict = {
        "iniciado_em": agora_iso(), "regiao": codigo, "resultado": "erro",
        "mapas": 0, "mapas_sem_regiao": 0, "precos": 0, "precos_historico": 0,
        "verificadas": 0, "divergentes": 0, "ausentes": 0,
        "recusas": [], "avisos": [], "publicacoes": {},
    }

    def falar(*partes) -> None:
        if not args.json:
            print(*partes, file=sys.stderr)

    # ── 1. fontes ────────────────────────────────────────────────────────────
    falar("=== F2 · CARGA DE PREÇOS NO POSTGRESQL ===")
    falar(f"  região: {rotulo}  ({codigo})")
    falar("  fonte:  mapa da calculadora oficial (calculator.aws)")

    catalogo = oficial.manifesto(args.cache)
    servicos = servicos_do_escopo(catalogo, escopo, args.servico)
    falar(f"  catálogo: {len(catalogo)} serviços · escopo: {len(servicos)} nós")

    # ── 2. coleta dos mapas ──────────────────────────────────────────────────
    # Deduplicado por HASH: serviços diferentes declaram a MESMA família (o
    # `cloudwatch` aparece no RDS e no EC2). Sem deduplicar, o mesmo preço
    # entraria duas vezes e a contagem não fecharia com o mapa.
    por_hash: dict[str, dict] = {}
    sem_regiao: list[str] = []
    indisponiveis: list[str] = []

    for nome_servico in servicos:
        try:
            definicao, _ = oficial.definicao_do_servico(catalogo, nome_servico, args.cache)
        except (KeyError, urllib.error.HTTPError, urllib.error.URLError, ValueError) as erro:
            indisponiveis.append(f"{nome_servico}: {type(erro).__name__}")
            continue
        for mapa in oficial.mapas_de_preco(definicao):
            try:
                bruto = oficial.baixar(mapa["url"], cache_dir=args.cache)
            except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as erro:
                indisponiveis.append(f"{mapa['familia']}: {type(erro).__name__}")
                continue
            try:
                conteudo = json.loads(bruto)
            except ValueError:
                indisponiveis.append(f"{mapa['familia']}: JSON ilegível")
                continue
            itens = oficial.itens_da_estrutura(conteudo, rotulo)
            if not itens:
                if mapa["familia"] not in sem_regiao:
                    sem_regiao.append(mapa["familia"])
                continue
            chave = sha256_de(bruto)
            registro = por_hash.setdefault(chave, {
                "familia": mapa["familia"],
                "url": mapa["url"],
                "publicacao": (conteudo.get("manifest") or {}).get("hawkFilePublicationDate"),
                "itens": itens,
                "servicos": [],
            })
            if nome_servico not in registro["servicos"]:
                registro["servicos"].append(nome_servico)

    if indisponiveis:
        resumo["avisos"].extend(indisponiveis[:10])
        falar(f"  ⚠ {len(indisponiveis)} mapa(s)/definição(ões) indisponíveis")

    # ── 3. publicações: data legível em toda publicação ────────────────
    # A decisão de RECUSAR por causa disto é do portão (`avaliar_portao`), e não
    # aqui: aqui só se levanta o dado. Regra de decisão misturada com coleta de
    # dado é regra que não se consegue testar sem rede e sem banco.
    sem_data = [r["familia"] for r in por_hash.values() if not r["publicacao"]]

    resumo["mapas"] = len(por_hash)
    resumo["mapas_sem_regiao"] = len(sem_regiao)
    resumo["precos"] = sum(len(r["itens"]) for r in por_hash.values())
    resumo["publicacoes"] = {r["familia"]: r["publicacao"] for r in por_hash.values()}

    falar(f"  mapas com preço nesta região: {resumo['mapas']} "
          f"({resumo['precos']} rateCodes)")
    falar(f"  mapas sem eixo de região: {resumo['mapas_sem_regiao']} (formato `-calc`, não é falha)")

    # ── 4. conexão ───────────────────────────────────────────────────────────
    try:
        con = pg.Conexao.de_ambiente().conectar()
    except (pg.ErroPostgres, OSError, ValueError) as erro:
        falar(f"✖ banco inacessível: {erro}")
        resumo["recusas"].append(f"banco inacessível: {erro}")
        if args.json:
            print(json.dumps(resumo, ensure_ascii=False, indent=2))
        return 2
    falar(f"  banco: PostgreSQL {con.versao()} · {con.banco}@{con.host}")

    # Guarda de estrutura: sem as tabelas, a carga falharia no meio da transação
    # com um `42P01` cru — erro correto e inútil. Aqui o erro diz o que fazer.
    try:
        existe = con.consultar(
            "SELECT count(*)::text FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN ('preco', 'mapa_preco', 'carga_log')"
        ).primeira
    except pg.ErroPostgres as erro:
        falar(f"✖ não consegui conferir a estrutura: {erro}")
        return 2
    if not existe or existe[0] != "3":
        falar("✖ o schema não está aplicado neste banco.")
        falar(f"  aplicado: {existe[0] if existe else 0} de 3 tabelas esperadas")
        falar("  rode: make schema")
        return 2

    try:
        return _carregar(con, args, resumo, inicio, rotulo, codigo, catalogo,
                         por_hash, sem_data, falar)
    finally:
        con.fechar()


def avaliar_portao(publicacoes_sem_data, ratecodes_sumidos, ratecodes_conflitantes,
                   divergencias_por_servico) -> list[str]:
    """
    O veredito do portão, como FUNÇÃO PURA.

    Separada da carga de propósito: esta é a regra que decide se a base é
    tocada. Regra que só se testa com banco de verdade é regra que quase nunca
    é testada — aqui ela recebe dado e devolve a lista de recusas, e o teste
    cobre os quatro casos (data ilegível, família que sumiu, preço que sumiu,
    valor divergente) sem rede e sem PostgreSQL.

    As quatro recusas, e por que cada uma é recusa:
      - publicação sem data legível: não se sabe DE QUANDO é o preço que entrou;
      - rateCode vigente que desapareceu do mapa: a dimensão que já usamos
        deixou de ser publicada;
      - MESMO rateCode com preço diferente em DOIS MAPAS da própria oficial: as
        publicações discordam, e escolher uma seria adivinhar;
      - MESMO rateCode com valor diferente entre as duas fontes oficiais (mapa da
        calculadora × Bulk Price List): as duas discordam.
    """
    recusas: list[str] = []
    if publicacoes_sem_data:
        recusas.append("mapas sem data de publicação: " + ", ".join(sorted(publicacoes_sem_data)[:10]))
    if ratecodes_sumidos:
        recusas.append(
            f"{len(ratecodes_sumidos)} rateCode(s) que estavam vigentes desapareceram do mapa "
            f"(ex.: {', '.join(sorted(ratecodes_sumidos)[:3])})"
        )
    for rate_code, conflito in sorted(ratecodes_conflitantes.items()):
        recusas.append(
            f"{rate_code}: preço diferente entre mapas da oficial "
            f"({conflito['mapas'][0]}={conflito['preco'][0]} × "
            f"{conflito['mapas'][1]}={conflito['preco'][1]})"
        )
    for nome_servico, divergentes in sorted(divergencias_por_servico.items()):
        exemplo = divergentes[0]
        recusas.append(
            f"{nome_servico}: {len(divergentes)} rateCode(s) com VALOR diferente "
            f"(ex.: {exemplo['rate_code']} oficial={exemplo['oficial']} "
            f"price_list={exemplo['price_list']})"
        )
    return recusas


def _modo_banco(args) -> int:
    """`--aplicar-schema` e `--conferir-carga`: os dois passos que não baixam preço."""
    try:
        con = pg.Conexao.de_ambiente().conectar()
    except (pg.ErroPostgres, OSError, ValueError) as erro:
        print(f"✖ banco inacessível: {erro}", file=sys.stderr)
        return 2
    try:
        if args.aplicar_schema:
            caminho = BASE / "sql" / "001-schema.sql"
            print(f"aplicando {caminho.name} em {con.banco}@{con.host} (PostgreSQL {con.versao()})")
            # Protocolo SIMPLES: o arquivo tem dezenas de comandos, e o
            # protocolo estendido aceita um por `Parse`. É por isso que o
            # cliente tem os dois caminhos.
            con.executar_simples(caminho.read_text(encoding="utf-8"))
            tabelas = con.consultar(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
            print(f"estrutura aplicada — {len(tabelas)} objetos em public:")
            for nome in tabelas.linhas:
                print(f"  {nome[0]}")
            return 0

        # --conferir-carga
        try:
            total = con.consultar("SELECT count(*)::text FROM preco WHERE vigente").primeira
        except pg.ErroPostgres as erro:
            if erro.codigo == "42P01":
                print("✖ a tabela `preco` não existe neste banco. Rode: make schema", file=sys.stderr)
                return 2
            raise
        print("=== O QUE ESTÁ NA BASE (vigente) ===")
        print(f"  preços vigentes: {total[0] if total else 0}")
        por_familia = con.consultar(
            "SELECT m.familia, count(*)::text, max(m.publicacao_em)::text "
            "FROM preco p JOIN mapa_preco m ON m.id = p.mapa_preco_id "
            "WHERE p.vigente GROUP BY m.familia ORDER BY m.familia"
        )
        for familia, quantos, publicacao in por_familia.linhas:
            print(f"    {familia:<40} {quantos:>6}  pub={publicacao}")
        historico = con.consultar("SELECT count(*)::text FROM preco WHERE NOT vigente").primeira
        print(f"  preços históricos (nunca apagados): {historico[0] if historico else 0}")

        print()
        print("=== ÚLTIMAS CARGAS ===")
        cargas = con.consultar(
            "SELECT iniciado_em::text, resultado, mapas::text, precos_novos::text, "
            "verificadas::text, divergentes::text, ausentes::text, executado_por "
            "FROM carga_log ORDER BY iniciado_em DESC LIMIT 5"
        )
        for linha in cargas.linhas:
            inicio, resultado, mapas, novos, verif, div, aus, quem = linha
            print(f"  {inicio}  {resultado:<12} mapas={mapas} novos={novos} "
                  f"conferidos={verif} divergentes={div} ausentes={aus} por={quem}")
        return 0
    finally:
        con.fechar()


def _carregar(con, args, resumo: dict, inicio: float, rotulo: str, codigo: str,
              catalogo: dict, por_hash: dict, sem_data: list[str], falar) -> int:
    # ── 5. novidade: algum hash já está na base? ─────────────────────────────
    conhecidos = {linha[0] for linha in con.consultar(SQL_HASHES_CARREGADOS).linhas}
    novos = {chave: r for chave, r in por_hash.items() if chave not in conhecidos}

    if not novos:
        # Nada a fazer — e isso é RESULTADO, não falha. O `carga_log` registra a
        # tentativa para que "sem novidade" seja auditável e não pareça que o
        # botão não funcionou.
        resumo["resultado"] = "sem_novidade"
        resumo["duracao_ms"] = int((time.time() - inicio) * 1000)
        falar("  nada novo: todos os mapas desta região já estão carregados")
        _registrar_log(con, resumo, codigo, args.por,
                       "todos os mapas já estavam carregados por hash de conteúdo")
        _resumir(resumo, args, falar)
        return 0

    falar(f"  mapas novos: {len(novos)} de {len(por_hash)}")

    # ── 6. enriquecimento (unidade/descrição) ────────────────────────────────
    detalhes: dict[str, dict] = {}
    if args.enriquecer:
        familiares = {r["familia"] for r in novos.values()}
        detalhes, pulados = enriquecer_com_price_list(familiares, codigo, args.limite_mb, args.cache)
        falar(f"  unidades/descrições obtidas para {len(detalhes)} rateCodes")
        for pulado in pulados:
            falar(f"    ⚠ não enriquecido: {pulado}")
            resumo["avisos"].append(f"enriquecimento pulado — {pulado}")

    # ── 7. portão: preço que JÁ ESTAVA na base e sumiu do mapa ───────────────
    # Só faz sentido na carga COMPLETA: com `--servico`, as outras famílias não
    # são carregadas e a comparação acusaria desaparecimento que não houve.
    # ── 7. levanta o dado que o portão precisa ─────────────────────────
    # Nada é DECIDIDO aqui: aqui se COLETA. Quem decide é `avaliar_portao`, que
    # é função pura e por isso testável sem rede e sem banco.
    # ⚠️ UM rateCode PODE SER DECLARADO POR MAIS DE UM MAPA — medido na primeira
    # carga de verdade, e não deduzido: `redshift` e `redshift-storage` publicam
    # os MESMOS 140 rateCodes, e o `cloudwatch` aparece no mapa do RDS e no do
    # EC2. O rateCode é a identidade da dimensão, então o PREÇO é um só; o que
    # muda é quem o declara.
    #
    # A primeira versão gravava uma linha por (mapa, rateCode) e o índice único
    # parcial recusou a segunda — e o índice está certo: ele existe justamente
    # para não existirem dois vigentes do mesmo rateCode. O erro era meu.
    consolidado: dict[str, dict] = {}
    conflitantes: dict[str, dict] = {}
    for chave, registro in novos.items():
        for item in registro["itens"]:
            rate_code = item["rateCode"]
            preco = item.get("price")
            atual = consolidado.get(rate_code)
            if atual is None:
                consolidado[rate_code] = {
                    "preco": preco,
                    "familia": registro["familia"],
                    "familias": [registro["familia"]],
                    "mapa_chave": chave,
                    "item": item,
                }
                continue
            if registro["familia"] not in atual["familias"]:
                atual["familias"].append(registro["familia"])
            if str(atual["preco"]) != str(preco):
                conflitantes.setdefault(rate_code, {
                    "preco": [str(atual["preco"]), str(preco)],
                    "mapas": [atual["familia"], registro["familia"]],
                })

    resumo["precos_unicos"] = len(consolidado)

    # O que já estava vigente nesta região, para o portão perguntar se alguma
    # dimensão que já usávamos desapareceu do mapa.
    ratecodes_sumidos = (
        {linha[0] for linha in con.consultar(SQL_RATECODES_VIGENTES, [codigo]).linhas}
        - set(consolidado)
    )

    # ── 8. portão: conferência F1 (rateCode contra a calculadora oficial) ────
    divergencias: dict[str, list[dict]] = {}
    if not args.sem_conferir:
        falar("  conferindo rateCode contra a calculadora oficial...")
        for nome_servico in sorted({s for r in novos.values() for s in r["servicos"]}):
            try:
                relatorio = oficial.conferir(catalogo, nome_servico,
                                            {"rotulo_oficial": rotulo, "codigo_price_list": codigo},
                                            args.cache)
            except Exception as erro:  # noqa: BLE001 — rede instável não derruba a carga
                resumo["avisos"].append(f"conferência de {nome_servico} falhou: {type(erro).__name__}")
                continue
            resumo["verificadas"] += relatorio.get("iguais", 0)
            resumo["ausentes"] += len(relatorio.get("ausentes") or [])
            if relatorio.get("diferentes"):
                divergencias[nome_servico] = relatorio["diferentes"]
        resumo["divergentes"] = sum(len(v) for v in divergencias.values())
        falar(f"  conferidos: {resumo['verificadas']} iguais · {resumo['divergentes']} divergentes · "
              f"{resumo['ausentes']} ausentes no Price List (medido na F1: ausência não é erro)")

    # ── 9. veredito do portão ────────────────────────────────────────────────
    resumo["recusas"] = avaliar_portao(sem_data, ratecodes_sumidos,
                                      conflitantes, divergencias)
    if resumo["recusas"]:
        resumo["resultado"] = "recusado"
        resumo["duracao_ms"] = int((time.time() - inicio) * 1000)
        falar("")
        falar("  ✖ CARGA RECUSADA — a base NÃO foi tocada, o preço antigo (íntegro) continua valendo:")
        for recusa in resumo["recusas"]:
            falar(f"      {recusa}")
        if args.dry_run:
            falar("      (dry-run: a recusa também não foi registrada)")
        else:
            _registrar_log(con, resumo, codigo, args.por, "; ".join(resumo["recusas"])[:2000])
        _resumir(resumo, args, falar)
        return 1

    if args.dry_run:
        resumo["resultado"] = "dry_run"
        resumo["duracao_ms"] = int((time.time() - inicio) * 1000)
        falar("")
        falar("  dry-run: nada foi gravado (nem o log)")
        _resumir(resumo, args, falar)
        return 0

    # ── 10. gravação: UMA transação ────────────────────────────────────
    falar("  gravando...")
    gravados = 0
    historico = 0
    with con.transacao():
        con.comando(SQL_REGIAO, [codigo, rotulo])
        inserir_em_lotes(con, "servico", COLUNAS_SERVICO, linhas_de_servico(catalogo))

        ids_por_chave: dict[str, int] = {}
        for chave, registro in sorted(novos.items(), key=lambda kv: kv[1]["familia"]):
            familia = registro["familia"]
            ofertas = oficial.ofertas_da_familia(familia)
            linha = con.consultar(SQL_MAPA, [
                familia, ofertas[0] if ofertas else None, registro["publicacao"],
                registro["url"], chave, args.por,
            ]).primeira
            if not linha:
                raise pg.ErroPostgres({"S": "ERRO", "C": "XX000",
                                       "M": f"mapa {familia} não devolveu id"})
            ids_por_chave[chave] = int(linha[0])

        # 1. Os rateCodes desta carga vão para uma tabela TEMPORÁRIA...
        con.comando(SQL_CRIAR_TEMP_NOVOS)
        inserir_em_lotes(con, "_precos_novos", ("rate_code",),
                         [(rate_code,) for rate_code in consolidado])

        # 2. ...para o vigente anterior virar histórico num comando só, ANTES do
        # INSERT. A ordem importa: o índice único parcial não admite dois vigentes
        # do mesmo rateCode, então o antigo tem de sair de cena primeiro. A
        # etiqueta ("UPDATE 1185") diz quantos viraram histórico — contar pelo
        # retorno do banco, e não por estimativa nossa.
        etiqueta = con.comando(SQL_HISTORICO, [codigo])
        if etiqueta.startswith("UPDATE"):
            historico = int(etiqueta.split()[-1])

        linhas = []
        for rate_code, dados in consolidado.items():
            extra = {k: v for k, v in dados["item"].items() if k not in ("rateCode", "price")}
            # Quais mapas declaram este rateCode. É o que preserva a informação
            # de que `redshift` e `redshift-storage` publicam o mesmo preço.
            extra["mapas"] = dados["familias"]
            detalhe = detalhes.get(rate_code) or {}
            linhas.append((
                ids_por_chave[dados["mapa_chave"]],
                rate_code,
                sku_do_ratecode(rate_code),
                codigo,
                dados["preco"],
                detalhe.get("unidade"),
                detalhe.get("descricao"),
                dados["familia"],
                json.dumps(extra, ensure_ascii=False),
                True,
            ))
        gravados = inserir_em_lotes(con, "preco", COLUNAS_PRECO, linhas)

    resumo["precos_novos"] = gravados
    resumo["precos_historico"] = historico
    resumo["resultado"] = "ok"
    resumo["duracao_ms"] = int((time.time() - inicio) * 1000)
    falar(f"  gravados: {gravados} preços em {len(novos)} mapas")
    _registrar_log(con, resumo, codigo, args.por, None)
    _resumir(resumo, args, falar)
    return 0


def _registrar_log(con, resumo: dict, codigo: str, por: str, mensagem: str | None) -> None:
    """
    Grava o `carga_log`. Fora da transação principal de propósito: o log precisa
    sobreviver à recusa, e uma recusa não tem transação para reverter.
    """
    con.comando(SQL_CARGA_LOG, [
        resumo.get("duracao_ms"), resumo["resultado"], codigo,
        json.dumps(resumo.get("publicacoes") or {}, ensure_ascii=False),
        resumo.get("mapas", 0), resumo.get("precos_novos", 0), resumo.get("precos_historico", 0),
        resumo.get("verificadas", 0), resumo.get("divergentes", 0), resumo.get("ausentes", 0),
        mensagem, por,
    ])


def _resumir(resumo: dict, args, falar) -> None:
    if args.json:
        print(json.dumps(resumo, ensure_ascii=False, indent=2))
        return
    falar("")
    falar("=== RESUMO ===")
    falar(f"  resultado ................. {resumo['resultado']}")
    falar(f"  mapas carregados .......... {resumo['mapas']}")
    falar(f"  mapas sem eixo de região .. {resumo['mapas_sem_regiao']}")
    falar(f"  rateCodes únicos .......... {resumo.get('precos_unicos', 0)}"
          "  (um rateCode pode estar em mais de um mapa)")
    # `resumo.get`: no dry-run nada é gravado, então a chave não existe — e
    # estourar KeyError ao IMPRIMIR o resumo seria perder o resultado por causa
    # do relatório dele.
    falar(f"  preços gravados ........... {resumo.get('precos_novos', 0)}")
    falar(f"  virados histórico ......... {resumo.get('precos_historico', 0)}")
    # A contagem da conferência é POR SERVIÇO: o mesmo mapa (o `cloudwatch`, por
    # exemplo) é declarado por vários serviços, então o mesmo rateCode entra mais
    # de uma vez. Quem quiser o número sem repetição olha os rateCodes dos mapas.
    falar(f"  rateCodes conferidos ...... {resumo['verificadas']}  (por serviço, com repetição)")
    falar(f"  divergências de valor ..... {resumo['divergentes']}")
    falar(f"  ausentes no Price List .... {resumo['ausentes']}  (por serviço)")
    falar(f"  duração ................... {resumo.get('duracao_ms', 0)} ms")


if __name__ == "__main__":
    raise SystemExit(main())
