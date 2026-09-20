"""
Testes da carga de preços (`carregar_precos.py`).

O ALVO PRINCIPAL AQUI É O PORTÃO
================================
A regra que decide se a base é tocada é a parte mais séria do projeto: ela
existe para impedir que um preço errado entre com cara de número certo. Se essa
regra só pudesse ser exercitada com PostgreSQL de pé e rede disponível, na
prática ela não seria testada — e a primeira vez que rodasse de verdade seria no
dia em que algo deu errado.

Por isso `avaliar_portao` é **função pura**: recebe dado, devolve recusas. Os
quatro casos (publicação sem data, família que sumiu, preço que sumiu, valor
divergente) são testados aqui, sem banco.

O que NÃO dá para testar sem banco é a gravação em si — essa vive no
`make carga-seca`, que fala com o PostgreSQL de verdade. E a decisão de projeto
é essa mesma: erro de regra pega no teste, erro de fiação pega na carga a seco.
"""

from __future__ import annotations

import re

import carregar_precos as carga


# ---------------------------------------------------------------------------
# O portão
# ---------------------------------------------------------------------------
def test_portao_aprova_quando_esta_tudo_em_ordem():
    assert carga.avaliar_portao([], set(), {}, {}) == []


def test_portao_recusa_publicacao_sem_data():
    """
    Preço sem data de publicação é preço que não se sabe DE QUANDO é — e o
    projeto inteiro se apoia em poder dizer a data de cada número.
    """
    recusas = carga.avaliar_portao(["lambda"], set(), {}, {})
    assert len(recusas) == 1
    assert "sem data de publicação" in recusas[0]
    assert "lambda" in recusas[0]


def test_portao_recusa_ratecode_vigente_que_sumiu_do_mapa():
    """
    Dimensão que já está na base e não veio nesta carga: o silêncio deixaria
    preço velho no ar como se fosse atual.
    """
    recusas = carga.avaliar_portao([], {"AAA.1.2", "BBB.3.4"}, {}, {})
    assert len(recusas) == 1
    assert "desapareceram do mapa" in recusas[0]
    assert "2 rateCode" in recusas[0]
    # O exemplo ajuda quem lê o log a investigar sem abrir o banco.
    assert "AAA.1.2" in recusas[0]


def test_portao_recusa_ratecode_com_preco_diferente_entre_mapas():
    """
    O MESMO rateCode com preço diferente em DOIS MAPAS da própria oficial. Este
    caso não estava previsto quando a carga foi escrita — ele apareceu porque a
    oficial publica o mesmo rateCode em mais de um mapa (`redshift` e
    `redshift-storage` dividem os mesmos 140). Se os dois discordarem, escolher
    um é adivinhar.
    """
    conflitantes = {
        "ZZQXJMTMJJG6F4RP.JRTCKXETXF.6YS6EN2CT7": {
            "preco": ["0.0000002000", "0.0000003000"],
            "mapas": ["redshift", "redshift-storage"],
        }
    }
    recusas = carga.avaliar_portao([], set(), conflitantes, {})
    assert len(recusas) == 1
    assert "preço diferente entre mapas" in recusas[0]
    assert "redshift" in recusas[0] and "0.0000003000" in recusas[0]


def test_portao_recusa_valor_divergente_entre_as_duas_fontes():
    """
    MESMO rateCode com preço diferente na oficial e no Price List: as duas
    fontes discordam. Gravar escolhendo uma delas seria adivinhar — e
    adivinhação com cara de número certo é exatamente o que o projeto combate.
    """
    divergentes = {
        "aWSLambda": [
            {"rate_code": "ZZQXJMTMJJG6F4RP.JRTCKXETXF.6YS6EN2CT7",
             "oficial": "0.0000002000", "price_list": "0.0000003000"}
        ]
    }
    recusas = carga.avaliar_portao([], set(), {}, divergentes)
    assert len(recusas) == 1
    assert "VALOR diferente" in recusas[0]
    assert "aWSLambda" in recusas[0]
    assert "0.0000002000" in recusas[0] and "0.0000003000" in recusas[0]


def test_portao_junta_todas_as_recusas_em_vez_de_parar_na_primeira():
    """
    O relatório precisa vir completo: quem for corrigir tem de ver tudo de uma
    vez, e não descobrir um problema novo a cada tentativa.
    """
    recusas = carga.avaliar_portao(
        ["lambda"],
        {"AAA.1.2"},
        {"BBB.3.4": {"preco": ["1", "2"], "mapas": ["redshift", "redshift-storage"]}},
        {"aWSLambda": [{"rate_code": "X.Y.Z", "oficial": "1", "price_list": "2"}]},
    )
    assert len(recusas) == 4


def test_ausencia_no_price_list_NAO_recusa():
    """
    Ausência é caso medido, e não erro: os rateCodes que existem no mapa da
    calculadora e não no Bulk Price List são IRREDUTÍVEIS (nenhuma outra oferta
    os contém) — 142 deles, medidos na carga do escopo inteiro. Por isso
    `avaliar_portao` nem recebe ausências: elas vão para o log como aviso, e não
    como recusa.
    """
    import inspect

    parametros = list(inspect.signature(carga.avaliar_portao).parameters)
    assert "ausentes" not in parametros
    assert parametros == [
        "publicacoes_sem_data", "ratecodes_sumidos",
        "ratecodes_conflitantes", "divergencias_por_servico",
    ]


# ---------------------------------------------------------------------------
# Derivados do rateCode
# ---------------------------------------------------------------------------
def test_sku_sai_do_proprio_ratecode():
    """`rateCode` é `SKU.oferta.versão` — a primeira parte é o SKU."""
    assert carga.sku_do_ratecode("ZZQXJMTMJJG6F4RP.JRTCKXETXF.6YS6EN2CT7") == "ZZQXJMTMJJG6F4RP"
    assert carga.sku_do_ratecode("AAA.1.2") == "AAA"


def test_sku_de_ratecode_inesperado_nao_inventa_valor():
    # Sem os pontos não há SKU a extrair. Devolver None é melhor do que devolver
    # o texto inteiro fingindo que é SKU.
    assert carga.sku_do_ratecode("sem-pontos") is None
    assert carga.sku_do_ratecode("") is None


def test_hash_de_conteudo_distingue_virgula_de_ponto():
    assert carga.sha256_de(b"abc") != carga.sha256_de(b"abd")
    assert carga.sha256_de(b"abc") == carga.sha256_de(b"abc")
    assert len(carga.sha256_de(b"abc")) == 64


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------
CATALOGO_FALSO = {
    "amazonDynamoDb": {
        "serviceCode": "amazonDynamoDb",
        "name": "DynamoDB",
        "description": "...",
        "subType": "subServiceSelector",
        "isActive": True,
        "serviceDefinitionLocation": "https://exemplo/dynamodb.json",
        "templates": ["dynamoDbOnDemand", "dynamoDbProvisioned"],
    },
    "dynamoDbOnDemand": {
        "serviceCode": "dynamoDbOnDemand",
        "name": "DynamoDB on-demand",
        "subType": "subService",
        "isActive": True,
        "serviceDefinitionLocation": "https://exemplo/dynamodb-ondemand.json",
    },
    "dynamoDbProvisioned": {
        "serviceCode": "dynamoDbProvisioned",
        "name": "DynamoDB provisionado",
        "subType": "subService",
        "isActive": True,
        "serviceDefinitionLocation": "https://exemplo/dynamodb-provisioned.json",
    },
    "aLambda": {
        "serviceCode": "aWSLambda",
        "name": "Lambda",
        "subType": "subService",
        "isActive": True,
        "serviceDefinitionLocation": "https://exemplo/lambda.json",
    },
}


def test_pai_e_resolvido_invertendo_os_templates():
    """
    O manifest não diz quem é filho de quem: quem diz é o PAI, listando os
    filhos em `templates`. A hierarquia é invertida, e não escrita à mão numa
    tabela que envelhece.
    """
    linhas = carga.linhas_de_servico(CATALOGO_FALSO)
    por_codigo = {linha[0]: linha for linha in linhas}

    assert por_codigo["dynamoDbOnDemand"][6] == "amazonDynamoDb"
    assert por_codigo["amazonDynamoDb"][6] is None, "quem não é filho não tem pai"
    assert por_codigo["aWSLambda"][6] is None


def test_servico_sem_descricao_nao_quebra():
    linhas = carga.linhas_de_servico(CATALOGO_FALSO)
    por_codigo = {linha[0]: linha for linha in linhas}
    assert por_codigo["dynamoDbOnDemand"][2] is None


ESCOPO_FALSO = {"linhas": [{"raizes": ["amazonDynamoDb"]}, {"raizes": ["aLambda", "amazonDynamoDb"]}]}


def test_escopo_traz_as_raizes_E_os_filhos_que_elas_declaram():
    """
    Os filhos entram porque é neles que está o preço: o pai quase sempre só
    declara quem precifica. Sem descer nos filhos, a carga não acharia preço
    nenhum no DynamoDB.
    """
    servicos = carga.servicos_do_escopo(CATALOGO_FALSO, ESCOPO_FALSO, None)
    assert servicos == ["amazonDynamoDb", "dynamoDbOnDemand", "dynamoDbProvisioned", "aLambda"]


def test_escopo_nao_repete_servico_que_aparece_em_duas_linhas():
    servicos = carga.servicos_do_escopo(CATALOGO_FALSO, ESCOPO_FALSO, None)
    assert len(servicos) == len(set(servicos))


def test_servico_escolhido_a_mao_ignora_o_escopo():
    assert carga.servicos_do_escopo(CATALOGO_FALSO, ESCOPO_FALSO, "aWSLambda") == ["aWSLambda"]


def test_filho_declarado_que_nao_esta_no_catalogo_e_ignorado():
    """
    `templates` pode citar código que não existe no manifest. Varrer o que não
    existe só geraria erro de rede disfarçado de erro de dado.
    """
    catalogo = dict(CATALOGO_FALSO)
    catalogo["amazonDynamoDb"] = dict(catalogo["amazonDynamoDb"])
    catalogo["amazonDynamoDb"]["templates"] = ["naoExiste"]
    servicos = carga.servicos_do_escopo(catalogo, {"linhas": [{"raizes": ["amazonDynamoDb"]}]}, None)
    assert servicos == ["amazonDynamoDb"]


# ---------------------------------------------------------------------------
# Inserção em lote
# ---------------------------------------------------------------------------
class ConexaoFalsa:
    def __init__(self):
        self.comandos: list[tuple[str, list]] = []

    def comando(self, sql: str, parametros=None) -> str:
        self.comandos.append((sql, list(parametros or [])))
        return f"INSERT 0 {len(parametros or [])}"


def test_lote_monta_um_comando_so_para_varias_linhas():
    """
    Uma ida e volta de rede por linha seriam 10 mil idas e voltas. O lote é o
    que faz a carga terminar em segundos, e não em minutos.
    """
    con = ConexaoFalsa()
    linhas = [(1, "a"), (2, "b"), (3, "c")]
    total = carga.inserir_em_lotes(con, "t", ("x", "y"), linhas, lote=500)

    assert total == 3
    assert len(con.comandos) == 1
    sql, parametros = con.comandos[0]
    assert sql == "INSERT INTO t (x, y) VALUES ($1, $2), ($3, $4), ($5, $6)"
    assert parametros == [1, "a", 2, "b", 3, "c"]


def test_lote_quebra_em_varios_comandos_quando_passa_do_tamanho():
    con = ConexaoFalsa()
    linhas = [(i, f"v{i}") for i in range(1, 8)]
    total = carga.inserir_em_lotes(con, "t", ("x", "y"), linhas, lote=3)

    assert total == 7
    assert [len(p) // 2 for _, p in con.comandos] == [3, 3, 1], "3 + 3 + 1 linhas"
    # A numeração dos marcadores RECOMEÇA em cada comando: $1 acumulado entre
    # comandos faria o Postgres recusar por parâmetro ausente.
    for sql, parametros in con.comandos:
        marcadores = [int(m) for m in re.findall(r"\$(\d+)", sql)]
        assert marcadores == list(range(1, len(parametros) + 1))


def test_lote_vazio_nao_emite_comando():
    con = ConexaoFalsa()
    assert carga.inserir_em_lotes(con, "t", ("x",), []) == 0
    assert con.comandos == []


# ---------------------------------------------------------------------------
# Histórico de carga
# ---------------------------------------------------------------------------
def test_log_de_carga_recebe_as_contagens_na_ordem_certa():
    """
    O `carga_log` é o que permite responder depois "o que aquela carga fez?".
    Se um número entrar na coluna errada, o log passa a mentir em silêncio — e
    um log que mente é pior do que log nenhum.
    """
    con = ConexaoFalsa()
    resumo = {
        "duracao_ms": 1234,
        "resultado": "ok",
        "publicacoes": {"lambda": "2026-09-11T12:46:01Z"},
        "mapas": 40,
        "precos_novos": 10150,
        "precos_historico": 7,
        "verificadas": 10150,
        "divergentes": 0,
        "ausentes": 86,
    }
    carga._registrar_log(con, resumo, "us-east-1", "jefera", None)

    sql, parametros = con.comandos[0]
    assert "INSERT INTO carga_log" in sql
    # A ordem segue as colunas de SQL_CARGA_LOG.
    assert parametros[0] == 1234
    assert parametros[1] == "ok"
    assert parametros[2] == "us-east-1"
    assert "lambda" in parametros[3]
    assert parametros[4] == 40, "mapas"
    assert parametros[5] == 10150, "precos_novos"
    assert parametros[6] == 7, "precos_historico"
    assert parametros[7] == 10150, "verificadas"
    assert parametros[8] == 0, "divergentes"
    assert parametros[9] == 86, "ausentes"
    assert parametros[11] == "jefera"


def test_log_de_recusa_guarda_o_motivo():
    con = ConexaoFalsa()
    resumo = {"resultado": "recusado", "duracao_ms": 10, "recusas": ["x"]}
    carga._registrar_log(con, resumo, "us-east-1", "jefera", "2 rateCodes divergentes")
    assert con.comandos[0][1][1] == "recusado"
    assert con.comandos[0][1][10] == "2 rateCodes divergentes"
