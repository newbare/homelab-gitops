"""
Testes da CONTA — aritmética pura, com snapshot sintético.

Nenhum teste aqui depende do preço real da AWS. Se um deles quebrar porque o
m6i.xlarge subiu, o teste estaria medindo o mercado, não o código.
"""

from __future__ import annotations

import pytest

from precos import (
    HORAS_POR_MES,
    ErroDeCalculo,
    ErroDeEntrada,
    calcular,
    fator_da_unidade,
    projecao_mensal,
)

LOCAL = pytest.approx


# ---------------------------------------------------------------------------
# Fator de unidade
# ---------------------------------------------------------------------------
def test_horas_nao_tem_fator():
    assert fator_da_unidade("Hrs", 168) == 1.0


def test_requisicoes_nao_tem_fator():
    assert fator_da_unidade("Requests", 168) == 1.0


def test_gb_nao_tem_fator():
    assert fator_da_unidade("GB", 168) == 1.0


def test_gb_mo_pro_rateia_por_hora():
    # A AWS cobra disco por GB-segundo e publica por GB-mês. Pagar mês cheio
    # por uma semana inflaria o número em ~4,3x.
    assert fator_da_unidade("GB-Mo", 168) == LOCAL(168 / HORAS_POR_MES)


def test_gb_mo_em_um_mes_nao_pro_rateia():
    assert fator_da_unidade("GB-Mo", HORAS_POR_MES) == LOCAL(1.0)


def test_unidade_desconhecida_levanta():
    # Unidade nova com tratamento implícito é como um número errado entra sem
    # ninguém perceber. Tem de falhar alto.
    with pytest.raises(ErroDeCalculo, match="unidade não tratada"):
        fator_da_unidade("TB-Mo", 168)


def test_unidade_vazia_levanta():
    with pytest.raises(ErroDeCalculo):
        fator_da_unidade("", 168)


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------
def test_total_e_a_soma_dos_subtotais(bom_falso, snapshot_falso):
    resultado = calcular(bom_falso, snapshot_falso)
    assert resultado["total"] == LOCAL(sum(i["subtotal"] for i in resultado["itens"]))


def test_horas_padrao_vem_do_bom(bom_falso, snapshot_falso):
    assert calcular(bom_falso, snapshot_falso)["horas"] == 100


def test_horas_pedidas_sobrescrevem_o_padrao(bom_falso, snapshot_falso):
    assert calcular(bom_falso, snapshot_falso, horas=24)["horas"] == 24


def test_preco_por_hora_multiplica_direto(bom_falso, snapshot_falso):
    resultado = calcular(bom_falso, snapshot_falso)
    node = next(i for i in resultado["itens"] if i["id"] == "node")
    assert node["subtotal"] == LOCAL(100 * 0.20)
    assert node["fator"] == 1.0


def test_gb_mo_e_pro_rateado_no_subtotal(bom_falso, snapshot_falso):
    resultado = calcular(bom_falso, snapshot_falso)
    disco = next(i for i in resultado["itens"] if i["id"] == "disco")
    esperado = 500 * (100 / HORAS_POR_MES) * 0.08
    assert disco["subtotal"] == LOCAL(esperado)
    assert disco["quantidade_efetiva"] == LOCAL(500 * (100 / HORAS_POR_MES))


def test_gb_multiplica_direto(bom_falso, snapshot_falso):
    resultado = calcular(bom_falso, snapshot_falso)
    egress = next(i for i in resultado["itens"] if i["id"] == "egress")
    assert egress["subtotal"] == LOCAL(30 * 0.10)


def test_total_por_hora_e_por_dia(bom_falso, snapshot_falso):
    resultado = calcular(bom_falso, snapshot_falso)
    assert resultado["total_por_hora"] == LOCAL(resultado["total"] / 100)
    assert resultado["total_por_dia"] == LOCAL(resultado["total"] / (100 / 24))


def test_por_grupo_soma_o_total(bom_falso, snapshot_falso):
    resultado = calcular(bom_falso, snapshot_falso)
    assert sum(resultado["por_grupo"].values()) == LOCAL(resultado["total"])


def test_itens_vem_ordenados_do_maior_para_o_menor(bom_falso, snapshot_falso):
    subtotais = [i["subtotal"] for i in calcular(bom_falso, snapshot_falso)["itens"]]
    assert subtotais == sorted(subtotais, reverse=True)


def test_linha_sem_preco_nao_some_e_vira_lacuna(bom_falso, snapshot_falso):
    resultado = calcular(bom_falso, snapshot_falso)
    sem_preco = next(i for i in resultado["itens"] if i["id"] == "sem-preco")
    assert sem_preco["sem_preco"] is True
    assert sem_preco["subtotal"] == 0.0
    assert "motivo" in sem_preco
    # Continua aparecendo na lista: lacuna silenciosa é o que se quer evitar.
    assert [l["id"] for l in resultado["lacunas"]] == ["sem-preco"]


def test_lacuna_nao_entra_no_total(bom_falso, snapshot_falso):
    resultado = calcular(bom_falso, snapshot_falso)
    # 20 (node) + 5,47945205 (disco) + 3 (egress) — e nada do item sem preço.
    assert resultado["total"] == LOCAL(20 + 500 * (100 / HORAS_POR_MES) * 0.08 + 3)


# ---------------------------------------------------------------------------
# Seleção de modelo (o seletor da tela)
# ---------------------------------------------------------------------------
def test_selecao_troca_o_modelo_do_catalogo(bom_falso, snapshot_falso):
    resultado = calcular(bom_falso, snapshot_falso, selecao={"node": "t3.micro"})
    node = next(i for i in resultado["itens"] if i["id"] == "node")
    assert node["modelo"] == "t3.micro"
    assert node["subtotal"] == LOCAL(100 * 0.01)
    assert resultado["selecao"] == {"node": "t3.micro"}


def test_sem_selecao_usa_o_padrao_do_bom(bom_falso, snapshot_falso):
    node = next(i for i in calcular(bom_falso, snapshot_falso)["itens"] if i["id"] == "node")
    assert node["modelo"] == "m6i.xlarge"


def test_modelo_inexistente_no_catalogo_e_erro_de_entrada(bom_falso, snapshot_falso):
    # Erro de ENTRADA (400), não erro de dado (500): o pedido é que está errado.
    with pytest.raises(ErroDeEntrada, match="não existe no catálogo"):
        calcular(bom_falso, snapshot_falso, selecao={"node": "gpu-enorme.24xlarge"})


def test_modelos_disponiveis_reflete_o_catalogo(bom_falso, snapshot_falso):
    assert calcular(bom_falso, snapshot_falso)["modelos_disponiveis"] == 2


# ---------------------------------------------------------------------------
# Projeção mensal
# ---------------------------------------------------------------------------
def test_projecao_mensal_usa_730_horas(bom_falso, snapshot_falso):
    mes = projecao_mensal(bom_falso, snapshot_falso)
    assert mes["horas"] == HORAS_POR_MES
    node = next(i for i in mes["itens"] if i["id"] == "node")
    assert node["subtotal"] == LOCAL(HORAS_POR_MES * 0.20)


def test_projecao_mensal_nao_pro_rateia_o_disco(bom_falso, snapshot_falso):
    mes = projecao_mensal(bom_falso, snapshot_falso)
    disco = next(i for i in mes["itens"] if i["id"] == "disco")
    # Em 730 h o fator de GB-Mo é exatamente 1: 500 GB × US$ 0,08.
    assert disco["subtotal"] == LOCAL(500 * 0.08)


def test_projecao_mensal_respeita_a_selecao(bom_falso, snapshot_falso):
    mes = projecao_mensal(bom_falso, snapshot_falso, selecao={"node": "t3.micro"})
    node = next(i for i in mes["itens"] if i["id"] == "node")
    assert node["subtotal"] == LOCAL(HORAS_POR_MES * 0.01)


# ---------------------------------------------------------------------------
# Quantidade que segue a janela ("janela")
# ---------------------------------------------------------------------------
def test_item_segue_janela_escala_com_as_horas(bom_falso, snapshot_falso):
    # O node é `"quantidade": "janela"`: a quantidade É a janela pedida. Sem
    # isto, projetar um mês manteria as 168 h do BOM e a MAIOR linha do custo
    # sairia ~4x mais barata — o bug que os testes pegaram na primeira rodada.
    node = next(i for i in calcular(bom_falso, snapshot_falso, horas=24)["itens"] if i["id"] == "node")
    assert node["quantidade"] == 24
    assert node["subtotal"] == LOCAL(24 * 0.20)
    assert node["segue_janela"] is True


def test_item_que_nao_segue_janela_nao_escala(bom_falso, snapshot_falso):
    # O disco é quantidade DECLARADA (500 GB): muda a janela, o volume não.
    # Ele só é pro-rateado no fator de GB-Mo.
    disco = next(i for i in calcular(bom_falso, snapshot_falso, horas=24)["itens"] if i["id"] == "disco")
    assert disco["quantidade"] == 500
    assert disco["segue_janela"] is False
    assert disco["subtotal"] == LOCAL(500 * (24 / HORAS_POR_MES) * 0.08)


def test_projecao_mensal_custa_mais_que_a_semana(bom_falso, snapshot_falso):
    semana = calcular(bom_falso, snapshot_falso, horas=168)
    mes = projecao_mensal(bom_falso, snapshot_falso)
    # A razão NÃO é 730/168 = 4,35 porque parte das linhas não segue a janela —
    # é justamente essa mistura que o teste protege.
    assert 3.0 < mes["total"] / semana["total"] < 4.35


def test_quantidade_estranha_levanta_erro(bom_falso, snapshot_falso):
    bom_ruim = {
        "horas_padrao": 100,
        "itens": [dict(bom_falso["itens"][0], quantidade="meia-janela")],
    }
    with pytest.raises(ErroDeCalculo, match="quantidade inválida"):
        calcular(bom_ruim, snapshot_falso)
