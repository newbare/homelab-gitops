"""
Testes do cliente PostgreSQL em biblioteca padrão (`api/pg.py`).

POR QUE ESTES TESTES NÃO PRECISAM DE BANCO
=========================================
O que pode dar errado neste cliente está em três lugares, e nenhum deles é o
PostgreSQL:

  1. a CONTA do SCRAM (PBKDF2, HMAC, XOR da prova) — verificável contra o vetor
     de teste do RFC 7677, que é um resultado conhecido e externo a nós;
  2. a CODIFICAÇÃO das mensagens (tipo + tamanho + carga) — verificável byte a
     byte contra um soquete falso;
  3. a LEITURA das respostas (DataRow, ErrorResponse) — verificável com bytes
     construídos à mão.

Um teste que só passa com o banco de pé é um teste que quase nunca roda. O que
realmente exige servidor é a integração — e essa vive no `make carga-seca`, que
fala com o PostgreSQL de verdade.

O teste contra o banco real já provou: autenticação SCRAM contra PostgreSQL
17.11, consulta com parâmetro, erro 42P01 capturado, ROLLBACK limpando transação
e a conexão seguindo utilizável depois do erro.
"""

from __future__ import annotations

import struct

import pytest

import pg


# ---------------------------------------------------------------------------
# 1. A conta do SCRAM, contra o vetor do RFC 7677
# ---------------------------------------------------------------------------
def test_scram_bate_com_o_vetor_do_rfc_7677():
    """
    O vetor do RFC 7677 (seção 3), que é um resultado EXTERNO:

        usuário: user      senha: pencil
        nonce do cliente:  rOprNGfwEbeRWgbNEkqO
        servidor: r=rOprNGfwEbeRWgbNEkqO%hvYDpWUa2RaTCAfuxFIlj)hNlF$k0,
                  s=W22ZaJ0SNY7soEsUEjb6gQ==,i=4096
        cliente-final esperado:
                  c=biws,r=rOprNGfwEbeRWgbNEkqO%hvYDpWUa2RaTCAfuxFIlj)hNlF$k0,
                  p=dHzbZapWIk4jUhN+Ute9ytag9zjfMHgsqmmiz7AndVQ=
        servidor-final: v=6rriTRBi23WpRR/wtup+mMhUZUn/dB5nLTJRsjl95G4=

    Sem este teste, o SCRAM seria conferido contra ele mesmo: qualquer erro de
    conta passaria, porque os dois lados errariam igual. Foi por isso que o nonce
    virou parâmetro injetável.
    """
    nonce = "rOprNGfwEbeRWgbNEkqO"
    servidor_primeira = (
        "r=rOprNGfwEbeRWgbNEkqO%hvYDpWUa2RaTCAfuxFIlj)hNlF$k0,"
        "s=W22ZaJ0SNY7soEsUEjb6gQ==,i=4096"
    )
    scram = pg._Scram("user", "pencil", nonce=nonce)

    # O cliente-primeiro do RFC leva `n=user` — é este texto que entra na conta
    # da prova. Com ele vazio, o vetor não conferiria (e não valeria como teste).
    assert scram.cliente_primeira().decode() == f"n,,n=user,r={nonce}"

    cliente_final = scram.cliente_final(servidor_primeira).decode()
    assert cliente_final == (
        "c=biws,r=rOprNGfwEbeRWgbNEkqO%hvYDpWUa2RaTCAfuxFIlj)hNlF$k0,"
        "p=dHzbZapWIk4jUhN+Ute9ytag9zjfMHgsqmmiz7AndVQ="
    )

    # E a assinatura do servidor também é conferida, sem levantar.
    scram.conferir_servidor_final(
        "v=6rriTRBi23WpRR/wtup+mMhUZUn/dB5nLTJRsjl95G4="
    )


def test_scram_recusa_nonce_de_servidor_desconhecido():
    """O nonce do servidor TEM de começar com o do cliente (RFC 5802)."""
    scram = pg._Scram("user", "pencil", nonce="cliente-nao-esta-aqui")
    with pytest.raises(pg.ErroDeProtocolo, match="nonce"):
        scram.cliente_final("r=outro-nonce-qualquer,s=W22ZaJ0SNY7soEsUEjb6gQ==,i=4096")


def test_scram_recusa_assinatura_de_servidor_falsa():
    """
    A prova do servidor é o que impede um intermediário de dizer "autenticado".
    """
    nonce = "rOprNGfwEbeRWgbNEkqO"
    scram = pg._Scram("user", "pencil", nonce=nonce)
    scram.cliente_final(
        "r=rOprNGfwEbeRWgbNEkqO%hvYDpWUa2RaTCAfuxFIlj)hNlF$k0,"
        "s=W22ZaJ0SNY7soEsUEjb6gQ==,i=4096"
    )
    with pytest.raises(pg.ErroDeProtocolo, match="assinatura"):
        scram.conferir_servidor_final("v=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")


def test_scram_reconhece_recusa_do_servidor():
    scram = pg._Scram("user", "pencil")
    with pytest.raises(pg.ErroDeProtocolo, match="recusou"):
        scram.conferir_servidor_final("e=invalid-proof")


def test_scram_sem_dados_do_servidor_e_erro_de_protocolo():
    scram = pg._Scram("user", "pencil")
    with pytest.raises(pg.ErroDeProtocolo, match="não mandou"):
        scram.cliente_final("r=abc")


# ---------------------------------------------------------------------------
# 2. Conversão de parâmetro
# ---------------------------------------------------------------------------
def test_booleano_vira_true_false_e_nao_1_0():
    """
    `bool` tem de ser testado ANTES de `int`: em Python, `True` É um int, e o
    JSONB deste schema espera `true` e não `1`.
    """
    assert pg._literal(True) == b"true"
    assert pg._literal(False) == b"false"


def test_dicionario_e_lista_viram_json():
    assert pg._literal({"a": 1}).decode() == '{"a": 1}'
    assert pg._literal([1, 2]).decode() == "[1, 2]"


def test_nulo_nao_vira_texto_nulo():
    # O NULL do protocolo é comprimento -1, e não a string vazia: quem monta a
    # mensagem decide isso. Aqui o valor tem de continuar "vazio", não "None".
    assert pg._literal(None) == b""


def test_numero_e_texto():
    assert pg._literal(42) == b"42"
    assert pg._literal("abc") == b"abc"


# ---------------------------------------------------------------------------
# 3. Quadro das mensagens (tipo + tamanho + carga)
# ---------------------------------------------------------------------------
class SoqueteFalso:
    """Guarda o que foi enviado, para conferir o quadro byte a byte."""

    def __init__(self):
        self.enviado = bytearray()

    def sendall(self, dados: bytes) -> None:
        self.enviado.extend(dados)


def test_mensagem_tem_tipo_e_tamanho_incluindo_o_proprio_tamanho():
    con = pg.Conexao()
    con.soquete = SoqueteFalso()
    con._enviar(b"Q", b"select 1\0")

    enviado = bytes(con.soquete.enviado)
    assert enviado[:1] == b"Q"
    (tamanho,) = struct.unpack("!I", enviado[1:5])
    assert tamanho == len(b"select 1\0") + 4
    assert enviado[5:] == b"select 1\0"


def test_bind_monta_parametro_como_texto_e_nulo_como_menos_um():
    """
    O `Bind` é onde o parâmetro de verdade entra, e a sequência das mensagens
    importa: Parse (`P`) -> Bind (`B`) -> Describe (`D`) -> Execute (`E`) ->
    Sync (`S`). Um erro aqui seria silencioso: o banco receberia OUTRO valor, e
    não um erro.
    """
    con = pg.Conexao()
    con.soquete = SoqueteFalso()
    con._ler_resultados = lambda: []  # type: ignore[assignment]  # sem servidor: não há o que ler

    con._executar_estendido("select $1, $2", ["abc", None])

    # Percorre o fluxo de mensagens como o servidor faria: tipo + tamanho + carga.
    enviado = bytes(con.soquete.enviado)
    mensagens: list[tuple[bytes, bytes]] = []
    posicao = 0
    while posicao < len(enviado):
        tipo = enviado[posicao : posicao + 1]
        (tamanho,) = struct.unpack("!I", enviado[posicao + 1 : posicao + 5])
        mensagens.append((tipo, enviado[posicao + 5 : posicao + 1 + tamanho]))
        posicao += 1 + tamanho

    assert [tipo for tipo, _ in mensagens] == [b"P", b"B", b"D", b"E", b"S"]

    carga_bind = dict(mensagens).get(b"B")
    assert carga_bind is not None
    assert carga_bind.startswith(b"\0\0"), "portal e statement sem nome (sem cache no servidor)"
    assert b"abc" in carga_bind, "o texto do parâmetro tem de ir no Bind"
    assert struct.pack("!i", -1) in carga_bind, "NULL é comprimento -1, e não string vazia"

    # Parse leva a SQL e a contagem de parâmetros — 2 marcadores, tipos inferidos.
    carga_parse = dict(mensagens)[b"P"]
    assert b"select $1, $2\0" in carga_parse
    assert carga_parse.endswith(struct.pack("!H", 2) + struct.pack("!I", 0) * 2)


# ---------------------------------------------------------------------------
# 4. Leitura das respostas
# ---------------------------------------------------------------------------
def test_campos_de_erro_sao_lidos_ate_o_terminador():
    carga = b"SERROR\0C42P01\0Mrelation does not exist\0Hveja o schema\0\0"
    campos = pg.Conexao._campos(carga)
    assert campos["S"] == "ERROR"
    assert campos["C"] == "42P01"
    assert campos["M"] == "relation does not exist"
    assert campos["H"] == "veja o schema"


def test_excecao_de_erro_mostra_codigo_e_dica():
    erro = pg.ErroPostgres({"S": "ERROR", "C": "42P01", "M": "não existe", "H": "confira"})
    assert erro.codigo == "42P01"
    assert "42P01" in str(erro)
    assert "confira" in str(erro)


def test_resultado_vira_dicionario():
    resultado = pg.Resultado(["a", "b"], [["1", "2"], ["3", None]], "SELECT 2")
    assert len(resultado) == 2
    assert resultado.dicionarios() == [{"a": "1", "b": "2"}, {"a": "3", "b": None}]
    assert resultado.primeira == ["1", "2"]


# ---------------------------------------------------------------------------
# 5. Configuração por ambiente
# ---------------------------------------------------------------------------
def test_conexao_vem_do_ambiente(monkeypatch):
    monkeypatch.setenv("PGHOST", "banco.interno")
    monkeypatch.setenv("PGPORT", "6000")
    monkeypatch.setenv("PGUSER", "calculadora")
    monkeypatch.setenv("PGPASSWORD", "segredo")
    monkeypatch.setenv("PGDATABASE", "calculadora")

    con = pg.Conexao.de_ambiente()
    assert (con.host, con.porta, con.usuario, con.banco) == (
        "banco.interno", 6000, "calculadora", "calculadora",
    )
    assert con.senha == "segredo"


def test_argumento_explicito_vence_o_ambiente(monkeypatch):
    monkeypatch.setenv("PGHOST", "banco.interno")
    con = pg.Conexao.de_ambiente(host="127.0.0.1")
    assert con.host == "127.0.0.1"


def test_transacao_aninhada_e_recusada():
    """
    Transação dentro de transação não é suportada de propósito: sem savepoint, o
    aninhamento daria a impressão de isolamento que não existe.
    """
    con = pg.Conexao()
    con._em_transacao = True
    with pytest.raises(pg.ErroPostgres, match="transação aberta"):
        with con.transacao():
            pass
