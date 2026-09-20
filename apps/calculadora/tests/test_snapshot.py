"""
Testes do CONTRATO DO DADO — o snapshot commitado e o BOM declarado.

Estes são os testes que pegam o erro que nenhum teste de aritmética pega:
preço que entrou sem procedência, catálogo que encolheu, BOM que aponta para
chave que não existe mais.

Não são testes sobre a AWS: são sobre a coerência entre dois arquivos que
viajam juntos no repositório.
"""

from __future__ import annotations

import re
from datetime import datetime

import pytest

# Preços conferidos na coleta de referência (2026-09-19, us-east-1).
# ⚠️ Se um destes quebrar, a pergunta NÃO é "ajustar o teste": é "por que o
# preço mudou?". Preço tabelado da AWS não muda sem aviso e sem motivo.
PRECOS_CONHECIDOS = [
    ("ipv4.publico.em_uso", "0.005"),
    ("s3.standard", "0.023"),
    ("s3.requisicoes.tier1", "0.000005"),
    ("s3.requisicoes.tier2", "0.0000004"),
    ("ecr.armazenamento", "0.10"),
    ("ebs.gp3", "0.08"),
    ("transferencia.internet", "0.09"),
]


def test_snapshot_tem_data_de_geracao(snapshot_real):
    gerado = snapshot_real["gerado_em"]
    # Tem de ser ISO-8601 terminando em Z: é o carimbo que o painel mostra.
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", gerado), gerado
    datetime.fromisoformat(gerado.replace("Z", "+00:00"))


def test_snapshot_registra_a_procedencia_de_cada_servico(snapshot_real):
    servicos = snapshot_real["fonte"]["servicos"]
    assert servicos, "snapshot sem procedência não pode ser commitado"
    for nome, info in servicos.items():
        assert info.get("publicationDate"), f"{nome} sem publicationDate"
        assert info.get("url_csv", "").startswith("https://pricing."), f"{nome} sem URL oficial"
        assert info.get("linhas_varridas", 0) > 0, f"{nome} sem linhas varridas"


def test_snapshot_nao_tem_problemas(snapshot_real):
    # Coleta com problema é coleta que não fecha. Se isto quebrar, o filtro de
    # alguma consulta deixou de casar (ou passou a casar demais).
    assert snapshot_real["problemas"] == [], snapshot_real["problemas"]


def test_snapshot_descobriu_regioes(snapshot_real):
    regioes = snapshot_real["regioes_disponiveis"]
    assert len(regioes) >= 100, f"só {len(regioes)} regiões: a descoberta regrediu?"
    assert snapshot_real["regiao"] in regioes


def test_snapshot_descobriu_servicos(snapshot_real):
    servicos = snapshot_real["servicos_disponiveis"]
    assert len(servicos) >= 250, f"só {len(servicos)} serviços no índice raiz"
    assert "AmazonEC2" in servicos


def test_snapshot_tem_catalogo_de_instancias(snapshot_real):
    catalogo = snapshot_real["catalogo_ec2"]
    assert len(catalogo) >= 500, f"só {len(catalogo)} modelos: catálogo suspeito"
    amostra = catalogo["m6i.xlarge"]
    assert amostra["unidade"] == "Hrs"
    assert amostra["vcpu"] == "4"
    assert amostra["memoria"] == "16 GiB"
    assert float(amostra["preco"]) > 0


def test_localidade_foi_descoberta_do_arquivo(snapshot_real):
    # Nada de "US East (N. Virginia)" escrito no código: vem do arquivo.
    assert snapshot_real["localidade"].startswith("US East")
    assert snapshot_real["regiao"] in snapshot_real["fonte"]["servicos"]["AmazonEC2"]["url_csv"]


@pytest.mark.parametrize("chave,esperado", PRECOS_CONHECIDOS)
def test_preco_conhecido(snapshot_real, chave, esperado):
    item = snapshot_real["itens"][chave]
    assert float(item["preco"]) == pytest.approx(float(esperado))
    assert item["unidade"]
    assert item["tipo_uso"], f"{chave} sem usageType: não dá para auditar"


def test_todo_item_precificado_tem_sku(snapshot_real):
    for chave, item in snapshot_real["itens"].items():
        assert item.get("sku"), f"{chave} sem SKU"
        assert item.get("tipo_uso"), f"{chave} sem usageType"


# ---------------------------------------------------------------------------
# BOM x snapshot — o teste de deriva
# ---------------------------------------------------------------------------
def test_todo_preco_ref_do_bom_existe(bom_real, snapshot_real):
    disponiveis = set(snapshot_real["itens"]) | {"catalogo_ec2"}
    faltando = [
        item["id"] for item in bom_real["itens"] if item.get("preco_ref") not in disponiveis
    ]
    assert faltando == [], f"BOM aponta para preço inexistente: {faltando}"


def test_todo_modelo_padrao_do_bom_existe_no_catalogo(bom_real, snapshot_real):
    catalogo = snapshot_real["catalogo_ec2"]
    for item in bom_real["itens"]:
        if item.get("preco_ref") == "catalogo_ec2":
            assert item.get("padrao") in catalogo, (
                f"{item['id']}: padrão {item.get('padrao')!r} não está no catálogo"
            )


def test_bom_tem_justificativa_em_toda_linha(bom_real):
    # O "por_que" é o que separa BOM de planilha: quem lê sabe por que a linha
    # existe, e não só quanto custa.
    sem_motivo = [item["id"] for item in bom_real["itens"] if not item.get("por_que")]
    assert sem_motivo == [], f"linha sem justificativa: {sem_motivo}"


def test_bom_declara_janela_de_uma_semana(bom_real):
    assert bom_real["horas_padrao"] == 168


def test_bom_tem_premissas_declaradas(bom_real):
    assert len(bom_real["premissas"]) >= 4


def test_toda_linha_do_bom_tem_grupo_valido(bom_real):
    validos = {"computacao", "armazenamento", "rede", "operacao", "outros"}
    invalidos = [i["id"] for i in bom_real["itens"] if i["grupo"] not in validos]
    assert invalidos == [], f"grupo inválido em: {invalidos}"


def test_nenhuma_lacuna_no_bom_contra_o_snapshot(bom_real, snapshot_real):
    from precos import calcular

    resultado = calcular(bom_real, snapshot_real)
    assert resultado["lacunas"] == [], (
        "o BOM tem linha sem preço — lacuna declarada é aceitável, mas aqui ela "
        f"não deveria existir: {resultado['lacunas']}"
    )
    assert resultado["total"] > 0
