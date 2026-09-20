"""
Testes da BORDA HTTP.

Sobem o servidor de verdade em porta efêmera e conversam por HTTP. O que passa
aqui passou pelo mesmo caminho que o Ingress usa depois — inclusive o
confinamento de caminho e o mapa de códigos de erro.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest

BASE_WEB = Path(__file__).resolve().parent.parent / "web"

# Rotas implementadas. `/api/estado` é ALIAS de `/healthz`, mantida por
# compatibilidade e omitida da spec de propósito: duas entradas para a mesma
# coisa na documentação ensina dúvida. A exceção fica registrada no teste, em
# vez de escondida.
ROTAS_IMPLEMENTADAS = [
    "/healthz",
    "/api/precos",
    "/api/bom",
    "/api/calcular",
    "/api/fonte",
    "/api/regioes",
    "/api/servicos",
    "/api/catalogo",
    "/api/docs",
    "/api/openapi.json",
]
ALIAS_NAO_DOCUMENTADO = {"/api/estado"}


def pedir(url: str, metodo: str = "GET"):
    """Faz a requisição e devolve (codigo, cabecalhos, corpo) — sem levantar em 4xx/5xx."""
    requisicao = urllib.request.Request(url, method=metodo)
    try:
        with urllib.request.urlopen(requisicao, timeout=15) as resposta:
            return resposta.status, dict(resposta.headers), resposta.read()
    except urllib.error.HTTPError as erro:
        return erro.code, dict(erro.headers), erro.read()


def json_de(url: str):
    codigo, _, corpo = pedir(url)
    return codigo, json.loads(corpo)


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rota", ["/healthz", "/api/estado"])
def test_sonda_de_saude(base_url, rota):
    codigo, dados = json_de(base_url + rota)
    assert codigo == 200
    assert dados["ok"] is True


def test_openapi_json_e_valido(base_url):
    codigo, spec = json_de(base_url + "/api/openapi.json")
    assert codigo == 200
    assert spec["openapi"].startswith("3.1")
    assert spec["info"]["title"]
    assert spec["paths"]


def test_toda_rota_da_spec_existe_de_verdade(base_url):
    """A especificação não pode descrever rota que não responde."""
    _, spec = json_de(base_url + "/api/openapi.json")
    for rota in spec["paths"]:
        codigo, _, _ = pedir(base_url + rota)
        assert codigo != 404, f"{rota} está na spec mas a API respondeu 404"


def test_toda_rota_implementada_esta_na_spec(base_url):
    """E o contrário também: rota nova sem entrar na spec é dívida invisível."""
    _, spec = json_de(base_url + "/api/openapi.json")
    faltando = [r for r in ROTAS_IMPLEMENTADAS if r not in spec["paths"]]
    assert faltando == []
    for rota in ALIAS_NAO_DOCUMENTADO:
        assert rota not in spec["paths"], f"{rota} é alias e não deveria estar documentada"


def test_api_docs_serve_a_tela(base_url):
    codigo, cabecalhos, corpo = pedir(base_url + "/api/docs")
    assert codigo == 200
    assert "text/html" in cabecalhos["Content-Type"]
    assert b"OpenAPI" in corpo


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------
def test_calcular_com_padrao(base_url):
    codigo, dados = json_de(base_url + "/api/calcular?horas=168")
    assert codigo == 200
    assert dados["horas"] == 168
    assert dados["total"] > 0
    assert dados["lacunas"] == []
    assert dados["mes"]["horas"] == 730


def test_calcular_por_hora_e_por_dia_batem(base_url):
    _, dados = json_de(base_url + "/api/calcular?horas=168")
    assert dados["total_por_dia"] == pytest.approx(dados["total"] / 7)
    assert dados["total_por_hora"] == pytest.approx(dados["total"] / 168)


def test_horas_nao_numerico_e_400(base_url):
    codigo, dados = json_de(base_url + "/api/calcular?horas=abc")
    assert codigo == 400
    assert "precisa ser numérico" in dados["erro"]


@pytest.mark.parametrize("horas", ["0", "-5", "99999"])
def test_horas_fora_de_faixa_e_400(base_url, horas):
    codigo, _ = json_de(f"{base_url}/api/calcular?horas={horas}")
    assert codigo == 400


def test_modelo_do_catalogo_muda_o_preco(base_url):
    _, catalogo = json_de(base_url + "/api/catalogo?busca=m6i.xlarge")
    modelo = catalogo["modelos"][0]
    preco = float(modelo["preco"])

    _, dados = json_de(base_url + "/api/calcular?horas=168&node-principal=m6i.xlarge")
    node = next(i for i in dados["itens"] if i["id"] == "node-principal")
    assert node["modelo"] == "m6i.xlarge"
    assert node["subtotal"] == pytest.approx(preco * 168)
    assert dados["selecao"] == {"node-principal": "m6i.xlarge"}


def test_modelo_inexistente_e_400_e_nao_numero_errado(base_url):
    codigo, dados = json_de(base_url + "/api/calcular?node-principal=gpu-que-nao-existe")
    assert codigo == 400
    assert "não existe no catálogo" in dados["erro"]


def test_selecao_de_dois_itens_ao_mesmo_tempo(base_url):
    _, dados = json_de(base_url + "/api/calcular?node-principal=t3.micro&host-terraform=t3.micro")
    assert dados["selecao"] == {
        "node-principal": "t3.micro",
        "host-terraform": "t3.micro",
    }


def test_parametro_desconhecido_e_ignorado_sem_quebrar(base_url):
    # Parâmetro que não é id do BOM não vira erro: ele simplesmente não é uma
    # escolha. O contrato é "id de item = escolha", e nada além disso.
    codigo, dados = json_de(base_url + "/api/calcular?qualquer-coisa=1")
    assert codigo == 200
    assert dados["selecao"] == {}


# ---------------------------------------------------------------------------
# Descoberta
# ---------------------------------------------------------------------------
def test_regioes(base_url):
    codigo, dados = json_de(base_url + "/api/regioes")
    assert codigo == 200
    assert dados["coletada"] == "us-east-1"
    assert dados["total"] >= 100
    assert dados["coletada"] in dados["regioes"]
    assert dados["observacao"]


def test_servicos(base_url):
    codigo, dados = json_de(base_url + "/api/servicos")
    assert codigo == 200
    assert dados["total"] >= 250
    codigos = {s["codigo"] for s in dados["servicos"]}
    assert {"AmazonEC2", "AmazonS3", "AmazonVPC"} <= codigos


def test_catalogo_sem_filtro(base_url):
    codigo, dados = json_de(base_url + "/api/catalogo")
    assert codigo == 200
    assert dados["total_no_catalogo"] >= 500
    assert len(dados["modelos"]) <= 200  # limite padrão


def test_catalogo_com_busca(base_url):
    _, dados = json_de(base_url + "/api/catalogo?busca=m6i.xlarge")
    assert dados["total_filtrado"] == 1
    assert dados["modelos"][0]["tipo"] == "m6i.xlarge"


def test_catalogo_limite_invalido_e_400(base_url):
    codigo, _ = json_de(base_url + "/api/catalogo?limite=abc")
    assert codigo == 400


def test_bom_e_precos_refletem_o_repositorio(base_url):
    _, bom = json_de(base_url + "/api/bom")
    _, precos = json_de(base_url + "/api/precos")
    assert bom["horas_padrao"] == 168
    assert precos["regiao"] == "us-east-1"
    assert precos["catalogo_ec2"]


def test_fonte_sem_problemas(base_url):
    codigo, dados = json_de(base_url + "/api/fonte")
    assert codigo == 200
    assert dados["problemas"] == []
    assert dados["fonte"]["servicos"]


# ---------------------------------------------------------------------------
# Estático
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "rota,tipo",
    [
        ("/", "text/html"),
        ("/styles.css", "text/css"),
        ("/app.js", "javascript"),
        ("/logo-resilience-full.png", "image/png"),
    ],
)
def test_estaticos_tem_tipo_certo(base_url, rota, tipo):
    codigo, cabecalhos, corpo = pedir(base_url + rota)
    assert codigo == 200
    assert tipo in cabecalhos["Content-Type"]
    assert corpo


def test_png_chega_inteiro(base_url):
    # A marca vem de ConfigMap em base64; se o round-trip quebrar, o logo some.
    _, cabecalhos, corpo = pedir(base_url + "/logo-resilience-full.png")
    assert corpo[:8] == b"\x89PNG\r\n\x1a\n", "o arquivo servido não é um PNG válido"


# ---------------------------------------------------------------------------
# Logos da stack — o deslize que só apareceria no palco
# ---------------------------------------------------------------------------
def logos_referenciados() -> set[str]:
    """Nomes de logo citados no app.js (os itens com `tec: '...'`)."""
    fonte = (BASE_WEB / "app.js").read_text(encoding="utf-8")
    return set(re.findall(r"tec: '([a-z0-9]+)'", fonte))


def test_todo_logo_referenciado_existe():
    """
    Um `tec:` com typo vira imagem quebrada — e imagem quebrada aparece na
    APRESENTAÇÃO, não no desenvolvimento. Este teste troca a surpresa de lugar.
    """
    faltando = sorted(t for t in logos_referenciados() if not (BASE_WEB / f"tec-{t}.svg").exists())
    assert faltando == [], f"logos citados no app.js que não existem: {faltando}"


def test_nenhum_logo_versionado_sobrando():
    """
    O caminho contrário: logo baixado e não usado é peso morto dentro do
    ConfigMap e do chart. Este teste pegou dois na primeira execução.
    """
    versionados = {p.stem.removeprefix("tec-") for p in BASE_WEB.glob("tec-*.svg")}
    sobrando = sorted(versionados - logos_referenciados())
    assert sobrando == [], (
        f"logos versionados que ninguém usa: {sobrando} — remova o arquivo ou cite no app.js"
    )


def test_todo_logo_versionado_e_servido(base_url):
    """Cada arquivo de logo precisa sair pela HTTP como SVG de verdade."""
    logos = sorted(p.name for p in BASE_WEB.glob("tec-*.svg"))
    assert logos, "nenhum tec-*.svg encontrado em web/"
    for nome in logos:
        codigo, cabecalhos, corpo = pedir(f"{base_url}/{nome}")
        assert codigo == 200, f"{nome} não foi servido"
        assert "svg" in cabecalhos["Content-Type"]
        assert b"<svg" in corpo[:400], f"{nome} não parece ser SVG"


# ---------------------------------------------------------------------------
# Segurança da borda
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "rota",
    [
        "/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "/..%2f..%2fdados%2fprices.json",
        "/%2e%2e%2fapi%2fprecos.py",
    ],
)
def test_path_traversal_e_bloqueado(base_url, rota):
    codigo, _, _ = pedir(base_url + rota)
    assert codigo in (403, 404), f"{rota} devolveu {codigo}: vazou do diretório web"


@pytest.mark.parametrize("rota", ["/segredo.py", "/backup.bak", "/.env"])
def test_extensao_nao_servida_e_recusada(base_url, rota):
    codigo, _, _ = pedir(base_url + rota)
    assert codigo == 403


def test_metodo_post_e_recusado(base_url):
    codigo, _, corpo = pedir(base_url + "/api/calcular", metodo="POST")
    assert codigo == 405
    assert "somente GET" in json.loads(corpo)["erro"]


def test_rota_de_api_desconhecida_e_404(base_url):
    codigo, _ = json_de(base_url + "/api/nao-existe")
    assert codigo == 404
