#!/usr/bin/env python3
"""
Cliente PostgreSQL em BIBLIOTECA PADRÃO — sem `pip install`, de propósito.

Por que não usar `psycopg`
=========================
Porque a aplicação inteira roda em imagem OFICIAL do Python + arquivos vindos de
ConfigMap: sem build, sem registry, sem Dockerfile. Foi assim que o
`api/servidor.py` pôde existir sem framework, e trocar isso por um driver
externo obrigaria a construir imagem própria — mudança de arquitetura para
atender o banco, quando o banco é que deve caber na arquitetura.

O que ficou de fora, conscientemente
====================================
- pool de conexões (a carga é operação rara; o servidor abre o que precisar)
- resultado em formato BINÁRIO (texto é o formato que o `psql` usa por padrão e
  o que dá para ler num log sem decodificar nada)
- tipos: o resultado vem como TEXTO e quem chama converte. `NUMERIC(20,10)`
  virando float em silêncio seria perda de precisão em preço — converter no
  ponto de uso é onde a decisão fica visível
- COPY (a carga daqui é de milhares de linhas, não de milhões)

O protocolo, resumido
=====================
  1. mensagem de STARTUP: versão 3.0 + pares chave/valor (`user`, `database`)
  2. o servidor responde `R` (autenticação) até `AuthenticationOk`
     -> código 5  = MD5 (senha + salt)
     -> código 10 = SASL: escolhemos SCRAM-SHA-256, ver `_scram`
  3. `S` (ParameterStatus), `K` (BackendKeyData), `Z` (ReadyForQuery)
  4. consultas pelo protocolo ESTENDIDO (`P`arse, `B`ind, `D`escribe, `E`xecute,
     `S`ync) — com parâmetro de verdade, e não SQL montado por concatenação
  5. para DDL com VÁRIOS comandos, o protocolo SIMPLES (`Q`), que aceita mais de
     um comando por mensagem. O estendido aceita UM por Parse

⚠️ SCRAM com canal: o servidor oferece `SCRAM-SHA-256` e `SCRAM-SHA-256-PLUS`.
Escolhemos a variante SEM canal (`-PLUS` exige TLS e channel binding). É por isso
que o `gs2-header` abaixo é `n,,` — "não suporto channel binding".
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import socket
import ssl as modulo_ssl
import struct
from contextlib import contextmanager

PROTOCOLO = 196608  # 3.0 -> (3 << 16) | 0


class ErroPostgres(RuntimeError):
    """Erro devolvido pelo SERVIDOR (`ErrorResponse`), não erro de rede."""

    def __init__(self, campos: dict[str, str]):
        self.campos = campos
        self.severidade = campos.get("S", "ERRO")
        self.codigo = campos.get("C", "")
        self.mensagem = campos.get("M", "erro sem mensagem do servidor")
        detalhe = campos.get("D")
        dica = campos.get("H")
        texto = f"[{self.codigo}] {self.mensagem}"
        if detalhe:
            texto += f" | detalhe: {detalhe}"
        if dica:
            texto += f" | dica: {dica}"
        super().__init__(texto)


class ErroDeProtocolo(RuntimeError):
    """O servidor mandou algo que este cliente não sabe interpretar."""


# ---------------------------------------------------------------------------
# SCRAM-SHA-256 (RFC 5802 / 7677)
# ---------------------------------------------------------------------------
def _hmac(chave: bytes, dados: bytes) -> bytes:
    return hmac.new(chave, dados, hashlib.sha256).digest()


def _pbkdf2(senha: bytes, salt: bytes, iteracoes: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", senha, salt, iteracoes)


class _Scram:
    """
    Máquina de estados do SCRAM-SHA-256, separada da rede de propósito: assim a
    conta criptográfica pode ser testada sozinha, sem servidor no meio.
    """

    def __init__(self, usuario: str, senha: str, nonce: str | None = None):
        self.usuario = usuario
        self.senha = senha.encode("utf-8")
        # O nonce é injetável para o teste poder reproduzir o vetor do RFC 7677
        # e conferir a conta criptográfica contra um resultado CONHECIDO, e não
        # só contra ele mesmo. Em produção ele é sempre aleatório — nonce
        # previsível destrói a garantia de frescor do SCRAM.
        self.nonce_cliente = nonce or base64.b64encode(secrets.token_bytes(18)).decode("ascii")
        # `n=` vai com o nome de usuário de verdade, escapado como o RFC 5802
        # manda (`=` -> `=3D`, `,` -> `=2C`).
        #
        # O PostgreSQL IGNORA este campo — ele usa o usuário do STARTUP —, e por
        # isso mandar vazio também funcionaria. Mas foi mandando vazio que a
        # conferência contra o vetor do RFC 7677 deixou de valer: o vetor foi
        # calculado com `n=user`, e o texto do cliente entra na conta da prova.
        # Com o campo vazio, o teste comparava a minha conta com ela mesma — e
        # um erro de fórmula passaria nos dois lados. Com o nome certo, o vetor
        # volta a ser resultado EXTERNO.
        self.usuario_sasl = usuario.replace("=", "=3D").replace(",", "=2C")
        self.primeira_sem_prova = f"n={self.usuario_sasl},r={self.nonce_cliente}"
        self.gs2 = "n,,"
        self.servidor_primeira = ""
        self.prova = ""
        self._auth_message = b""
        self._salted = b""

    def cliente_primeira(self) -> bytes:
        """`SASLInitialResponse`: mecanismo + tamanho + texto."""
        return (self.gs2 + self.primeira_sem_prova).encode("utf-8")

    def cliente_final(self, servidor_primeira: str) -> bytes:
        """Consome `r=`, `s=`, `i=` do servidor e produz `c=,r=,p=`."""
        self.servidor_primeira = servidor_primeira
        partes = dict(
            item.split("=", 1) for item in servidor_primeira.split(",") if "=" in item
        )
        for exigido in ("r", "s", "i"):
            if exigido not in partes:
                raise ErroDeProtocolo(f"SCRAM: servidor não mandou {exigido!r}: {servidor_primeira!r}")
        nonce_servidor = partes["r"]
        if not nonce_servidor.startswith(self.nonce_cliente):
            # Sem esta checagem, um servidor (ou um proxy no caminho) poderia
            # escolher o nonce inteiro e o SCRAM perderia a garantia de frescor.
            raise ErroDeProtocolo("SCRAM: o nonce do servidor não começa com o do cliente")
        salt = base64.b64decode(partes["s"])
        iteracoes = int(partes["i"])

        self._salted = _pbkdf2(self.senha, salt, iteracoes)
        chave_cliente = _hmac(self._salted, b"Client Key")
        chave_guardada = hashlib.sha256(chave_cliente).digest()
        sem_prova = f"c={base64.b64encode(self.gs2.encode()).decode()},r={nonce_servidor}"
        self._auth_message = (
            f"{self.primeira_sem_prova},{self.servidor_primeira},{sem_prova}".encode("utf-8")
        )
        assinatura = _hmac(chave_guardada, self._auth_message)
        prova = bytes(a ^ b for a, b in zip(chave_cliente, assinatura))
        self.prova = base64.b64encode(prova).decode("ascii")
        return f"{sem_prova},p={self.prova}".encode("utf-8")

    def conferir_servidor_final(self, servidor_final: str) -> None:
        """
        Confere `v=` — a prova de que o servidor CONHECE a senha.

        Sem isto, o cliente autentica o servidor por nada: um intermediário
        poderia responder AuthenticationOk e a aplicação gravaria dado em quem
        não é o banco.
        """
        partes = dict(item.split("=", 1) for item in servidor_final.split(",") if "=" in item)
        if "v" not in partes:
            if partes.get("e"):
                raise ErroDeProtocolo(f"SCRAM: servidor recusou: {partes['e']}")
            raise ErroDeProtocolo(f"SCRAM: servidor não mandou a assinatura final: {servidor_final!r}")
        esperado = _hmac(_hmac(self._salted, b"Server Key"), self._auth_message)
        recebido = base64.b64decode(partes["v"])
        if not hmac.compare_digest(esperado, recebido):
            raise ErroDeProtocolo("SCRAM: a assinatura do servidor não confere")


# ---------------------------------------------------------------------------
# Conexão
# ---------------------------------------------------------------------------
def _literal(valor) -> bytes:
    """Converte um parâmetro Python no texto que o protocolo leva."""
    if isinstance(valor, bool):
        # `bool` ANTES de `int`: em Python, True É um int, e sem esta ordem o
        # booleano viraria '1'/'0' — que o Postgres aceita para BOOLEAN, mas o
        # JSONB abaixo esperaria outra coisa.
        return b"true" if valor else b"false"
    if isinstance(valor, (int, float)):
        return str(valor).encode("utf-8")
    if isinstance(valor, (dict, list)):
        # Conveniência para as colunas JSONB deste schema: o chamador passa a
        # estrutura e não precisa lembrar de serializar.
        return json.dumps(valor, ensure_ascii=False).encode("utf-8")
    if valor is None:
        return b""
    return str(valor).encode("utf-8")


class Resultado:
    """Um conjunto de resultados: colunas + linhas + etiqueta do comando."""

    def __init__(self, colunas: list[str], linhas: list[list[str | None]], etiqueta: str):
        self.colunas = colunas
        self.linhas = linhas
        self.etiqueta = etiqueta

    def __len__(self) -> int:
        return len(self.linhas)

    def __iter__(self):
        """Itera as LINHAS, não as colunas.

        Existe porque `len(resultado)` já funcionava e `for linha in resultado`
        não — e a assimetria produzia o pior tipo de erro: a chamada parecia
        certa e estourava em tempo de execução com "não é iterável". Aconteceu na
        primeira execução real do `--aplicar-schema`.
        """
        return iter(self.linhas)

    @property
    def primeira(self) -> list[str | None] | None:
        return self.linhas[0] if self.linhas else None

    def dicionarios(self) -> list[dict]:
        return [dict(zip(self.colunas, linha)) for linha in self.linhas]


class Conexao:
    def __init__(
        self,
        host: str = "127.0.0.1",
        porta: int = 5432,
        usuario: str = "postgres",
        senha: str = "",
        banco: str = "postgres",
        timeout: float = 30.0,
        modo_ssl: str = "prefer",
        application_name: str = "calculadora-resilience",
    ):
        self.host = host
        self.porta = porta
        self.usuario = usuario
        self.senha = senha
        self.banco = banco
        self.timeout = timeout
        self.modo_ssl = modo_ssl
        self.application_name = application_name
        self.soquete: socket.socket | None = None
        self.parametros: dict[str, str] = {}
        self.avisos: list[dict[str, str]] = []
        self.backend_pid: int | None = None
        self._buffer = bytearray()
        self._em_transacao = False
        self.tls = False

    # ------------------------------------------------------------ de fábrica
    @classmethod
    def de_ambiente(cls, **trocar) -> "Conexao":
        """
        Monta a conexão a partir de variáveis de ambiente.

        As chaves seguem o nome que o próprio Postgres usa (`PGHOST`, `PGUSER`…),
        para não inventar vocabulário novo. É assim que o Deployment passa as
        credenciais, sem nenhuma delas no código.
        """
        campos = {
            "host": os.environ.get("PGHOST") or os.environ.get("POSTGRES_HOST") or "127.0.0.1",
            "porta": int(os.environ.get("PGPORT") or os.environ.get("POSTGRES_PORT") or 5432),
            "usuario": os.environ.get("PGUSER") or os.environ.get("POSTGRES_USER") or "postgres",
            "senha": os.environ.get("PGPASSWORD") or os.environ.get("POSTGRES_PASSWORD") or "",
            "banco": os.environ.get("PGDATABASE") or os.environ.get("POSTGRES_DB") or "postgres",
            "modo_ssl": os.environ.get("PGSSLMODE", "prefer"),
        }
        campos.update({k: v for k, v in trocar.items() if v is not None})
        return cls(**campos)

    # ------------------------------------------------------------------ rede
    def _ler_exato(self, quantos: int) -> bytes:
        while len(self._buffer) < quantos:
            pedaco = self.soquete.recv(65536)  # type: ignore[union-attr]
            if not pedaco:
                raise ErroDeProtocolo("a conexão foi fechada pelo servidor no meio de uma mensagem")
            self._buffer.extend(pedaco)
        dados = bytes(self._buffer[:quantos])
        del self._buffer[:quantos]
        return dados

    def _enviar(self, tipo: bytes, carga: bytes) -> None:
        self.soquete.sendall(tipo + struct.pack("!I", len(carga) + 4) + carga)  # type: ignore[union-attr]

    def _receber(self) -> tuple[bytes, bytes]:
        tipo = self._ler_exato(1)
        (tamanho,) = struct.unpack("!I", self._ler_exato(4))
        return tipo, self._ler_exato(tamanho - 4)

    def _negociar_ssl(self) -> None:
        """
        Pede TLS quando o modo não é `disable`.

        `SSLMODE=prefer` (padrão do psql) CONTINUA sem TLS quando o servidor
        recusa — é o caso do Postgres do laboratório. `require` falha, para quem
        precisa de garantia não receber silêncio.
        """
        if self.modo_ssl == "disable":
            return
        self.soquete.sendall(struct.pack("!II", 8, 80877103))  # SSLRequest
        resposta = self._ler_exato(1)
        if resposta == b"S":
            contexto = modulo_ssl.create_default_context()
            self.soquete = contexto.wrap_socket(self.soquete, server_hostname=self.host)
            self.tls = True
            return
        if self.modo_ssl == "require":
            raise ErroDeProtocolo("sslmode=require, mas o servidor recusou TLS")

    def conectar(self) -> "Conexao":
        self.soquete = socket.create_connection((self.host, self.porta), timeout=self.timeout)
        self.soquete.settimeout(self.timeout)
        try:
            self._negociar_ssl()
        except Exception:
            self.soquete.close()
            raise

        carga = struct.pack("!I", PROTOCOLO)
        for chave, valor in (
            ("user", self.usuario),
            ("database", self.banco),
            ("client_encoding", "UTF8"),
            ("application_name", self.application_name),
        ):
            carga += chave.encode("utf-8") + b"\0" + str(valor).encode("utf-8") + b"\0"
        carga += b"\0"
        self.soquete.sendall(struct.pack("!I", len(carga) + 4) + carga)

        self._autenticar()
        return self

    def _autenticar(self) -> None:
        scram: _Scram | None = None
        while True:
            tipo, carga = self._receber()
            if tipo == b"R":
                (codigo,) = struct.unpack("!I", carga[:4])
                dados = carga[4:]
                if codigo == 0:
                    continue
                if codigo == 3:
                    raise ErroDeProtocolo("o servidor pediu senha em texto claro; SCRAM deve ser usado")
                if codigo == 5:
                    salt = dados[:4]
                    dentro = hashlib.md5((self.senha + self.usuario).encode("utf-8")).hexdigest()
                    fora = hashlib.md5(dentro.encode("ascii") + salt).hexdigest()
                    self._enviar(b"p", b"md5" + fora.encode("ascii") + b"\0")
                    continue
                if codigo == 10:
                    mecanismos = [m.decode("utf-8") for m in dados.split(b"\0") if m]
                    if "SCRAM-SHA-256" not in mecanismos:
                        raise ErroDeProtocolo(
                            f"o servidor só oferece {mecanismos}; este cliente fala SCRAM-SHA-256"
                        )
                    scram = _Scram(self.usuario, self.senha)
                    primeira = scram.cliente_primeira()
                    self._enviar(
                        b"p",
                        b"SCRAM-SHA-256\0" + struct.pack("!I", len(primeira)) + primeira,
                    )
                    continue
                if codigo == 11:
                    if scram is None:
                        raise ErroDeProtocolo("SASLContinue sem SASL ter começado")
                    self._enviar(b"p", scram.cliente_final(dados.decode("utf-8")))
                    continue
                if codigo == 12:
                    if scram is None:
                        raise ErroDeProtocolo("SASLFinal sem SASL ter começado")
                    scram.conferir_servidor_final(dados.decode("utf-8"))
                    continue
                raise ErroDeProtocolo(f"pedido de autenticação não tratado: código {codigo}")
            if tipo == b"E":
                raise self._erro(carga)
            if tipo == b"S":
                chave, _, valor = carga.decode("utf-8").partition("\0")
                self.parametros[chave] = valor.rstrip("\0")
                continue
            if tipo == b"K":
                self.backend_pid = struct.unpack("!I", carga[:4])[0]
                continue
            if tipo == b"N":
                self.avisos.append(self._campos(carga))
                continue
            if tipo == b"Z":
                return
            raise ErroDeProtocolo(f"mensagem inesperada durante a autenticação: {tipo!r}")

    # -------------------------------------------------------------- leitura
    @staticmethod
    def _campos(carga: bytes) -> dict[str, str]:
        """`ErrorResponse`/`NoticeResponse`: par (código de 1 byte, texto\\0)."""
        campos: dict[str, str] = {}
        posicao = 0
        while posicao < len(carga) and carga[posicao] != 0:
            codigo = chr(carga[posicao])
            fim = carga.index(b"\0", posicao + 1)
            campos[codigo] = carga[posicao + 1 : fim].decode("utf-8", "replace")
            posicao = fim + 1
        return campos

    def _erro(self, carga: bytes) -> ErroPostgres:
        return ErroPostgres(self._campos(carga))

    # ------------------------------------------------------------- comandos
    def executar_simples(self, sql: str) -> list[Resultado]:
        """
        Protocolo SIMPLES: aceita VÁRIOS comandos numa mensagem.

        É o caminho do DDL (o arquivo de schema tem dezenas de `CREATE TABLE`).
        O protocolo estendido recusa mais de um comando por `Parse` — não é
        limitação deste cliente, é do protocolo.
        """
        self._enviar(b"Q", sql.encode("utf-8") + b"\0")
        return self._ler_resultados()

    def consultar(self, sql: str, parametros: list | tuple | None = None) -> Resultado:
        """SELECT pelo protocolo ESTENDIDO, com parâmetro separado do SQL."""
        resultados = self._executar_estendido(sql, parametros)
        if not resultados:
            return Resultado([], [], "SELECT 0")
        return resultados[-1]

    def comando(self, sql: str, parametros: list | tuple | None = None) -> str:
        """INSERT/UPDATE/DDL de um comando só. Devolve a etiqueta ('INSERT 0 1')."""
        resultados = self._executar_estendido(sql, parametros)
        return resultados[-1].etiqueta if resultados else ""

    def _executar_estendido(self, sql: str, parametros: list | tuple | None) -> list[Resultado]:
        valores = list(parametros or [])
        # Nomes vazios: sem cache de prepared statement do lado do servidor —
        # statement nomeado sobrevive à consulta e este cliente não o reusa.
        carga_parse = b"\0" + sql.encode("utf-8") + b"\0" + struct.pack("!H", len(valores))
        carga_parse += b"".join(struct.pack("!I", 0) for _ in valores)
        self._enviar(b"P", carga_parse)

        carga_bind = b"\0\0" + struct.pack("!H", 1) + struct.pack("!H", 0)  # 1 formato: texto
        carga_bind += struct.pack("!H", len(valores))
        for valor in valores:
            if valor is None:
                carga_bind += struct.pack("!i", -1)
            else:
                dado = _literal(valor)
                carga_bind += struct.pack("!I", len(dado)) + dado
        carga_bind += struct.pack("!H", 1) + struct.pack("!H", 0)  # resultado em texto
        self._enviar(b"B", carga_bind)

        self._enviar(b"D", b"P\0")
        self._enviar(b"E", b"\0" + struct.pack("!I", 0))
        self._enviar(b"S", b"")
        return self._ler_resultados()

    def _ler_resultados(self) -> list[Resultado]:
        """
        Lê até `ReadyForQuery`, juntando `RowDescription` + `DataRow`.

        ⚠️ ERRO SÓ É LEVANTADO NO FIM, DEPOIS DO `ReadyForQuery` —
        e isso não é estilo, é correção. A primeira versão levantava assim que
        via o `ErrorResponse`, deixando o `ReadyForQuery` que o servidor manda
        logo depois dentro do soquete. A conexão ficava DESINCRONIZADA: a
        leitura seguinte devolvia a mensagem atrasada em vez da resposta, e o
        sintoma era "consulta sem linhas", num lugar do código sem relação
        nenhuma com o erro original. Foi o teste contra o banco real que pegou:
        depois de um `42P01` (tabela inexistente), o ROLLBACK seguinte parecia
        não ter feito nada.

        Regra: em erro, o que já foi lido é DESCARTADO e a exceção sai depois de
        a conexão voltar ao estado limpo — pronta para o próximo comando.
        """
        resultados: list[Resultado] = []
        colunas: list[str] = []
        linhas: list[list[str | None]] = []
        etiqueta = ""
        erro: ErroPostgres | None = None
        while True:
            tipo, carga = self._receber()
            if tipo == b"T":
                quantas = struct.unpack("!H", carga[:2])[0]
                posicao = 2
                nomes = []
                for _ in range(quantas):
                    fim = carga.index(b"\0", posicao)
                    nomes.append(carga[posicao:fim].decode("utf-8"))
                    posicao = fim + 1 + 4 + 2 + 4 + 2 + 4 + 2
                colunas = nomes
                linhas = []
                continue
            if tipo == b"D":
                quantas = struct.unpack("!H", carga[:2])[0]
                posicao = 2
                linha: list[str | None] = []
                for _ in range(quantas):
                    (tamanho,) = struct.unpack("!i", carga[posicao : posicao + 4])
                    posicao += 4
                    if tamanho == -1:
                        linha.append(None)
                    else:
                        linha.append(carga[posicao : posicao + tamanho].decode("utf-8"))
                        posicao += tamanho
                linhas.append(linha)
                continue
            if tipo == b"C":
                etiqueta = carga[:-1].decode("utf-8")
                resultados.append(Resultado(colunas, linhas, etiqueta))
                colunas, linhas = [], []
                continue
            if tipo == b"E":
                # O PRIMEIRO erro é o que vale: os seguintes são consequência.
                if erro is None:
                    erro = self._erro(carga)
                continue
            if tipo == b"N":
                self.avisos.append(self._campos(carga))
                continue
            if tipo == b"Z":
                (estado,) = struct.unpack("c", carga[:1])
                self._em_transacao = estado != b"I"
                if erro is not None:
                    raise erro
                return resultados
            if tipo in (b"1", b"2", b"3", b"n", b"s", b"t", b"S", b"A"):
                # ParseComplete, BindComplete, CloseComplete, NoData,
                # PortalSuspended, ParameterDescription, ParameterStatus,
                # NotificationResponse: nada a guardar nesta altura.
                continue
            raise ErroDeProtocolo(f"mensagem não tratada: {tipo!r}")

    # ----------------------------------------------------------- transação
    @contextmanager
    def transacao(self):
        """
        Bloco transacional: sai com COMMIT, ou com ROLLBACK se der erro.

        Existe porque a regra do projeto é "nada é gravado parcialmente": uma
        carga que falha no meio não pode deixar preço pela metade na base.
        """
        if self._em_transacao:
            raise ErroPostgres({"S": "ERRO", "C": "25001", "M": "já existe transação aberta"})
        self.comando("BEGIN")
        try:
            yield self
        except BaseException:
            try:
                self.comando("ROLLBACK")
            except Exception:  # noqa: BLE001 — a falha original é a que importa
                pass
            raise
        self.comando("COMMIT")

    def versao(self) -> str:
        linha = self.consultar("SHOW server_version").primeira
        return linha[0] if linha else "?"

    def fechar(self) -> None:
        if self.soquete is None:
            return
        try:
            self._enviar(b"X", b"")
        except Exception:  # noqa: BLE001 — fechar não pode levantar
            pass
        try:
            self.soquete.close()
        finally:
            self.soquete = None

    def __enter__(self) -> "Conexao":
        return self.conectar()

    def __exit__(self, *_erro) -> None:
        self.fechar()
