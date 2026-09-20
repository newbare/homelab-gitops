#!/usr/bin/env python3
"""
Servidor da Calculadora Resilience — biblioteca padrão apenas.

Por que SEM framework (nem FastAPI, nem Flask)
==============================================
Porque o que se ganharia com framework aqui é conveniência de autor, e o que
se perde é maior: um `pip install` a mais para manter, um lockfile para
versionar, e a necessidade de construir imagem própria. Com `http.server` o app
é: imagem OFICIAL do Python + arquivos vindos de ConfigMap. Sem build, sem
registry, sem imagem para envelhecer.

Isso é limitação consciente, não descuido. O que este servidor NÃO faz, e que
exigiria trocar de ferramenta: concorrência de verdade sob carga, TLS próprio,
autenticação, timeout por requisição, métricas. Ele serve um painel interno de
leitura, com o conteúdo vindo de arquivo local — é o que cabe.

Cuidados que estão implementados, porque são os que importam de fato:
  - só GET (o app não muda nada);
  - defesa contra path traversal no estático (`realpath` + confinamento);
  - whitelist de extensões servidas, em vez de "qualquer arquivo da pasta";
  - `Cache-Control: no-store` na API: preço cacheado no browser é preço velho;
  - releitura do snapshot quando o arquivo muda (ConfigMap atualizado).

Uso:
    python3 servidor.py --web ../web --dados ../dados --porta 8080
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import posixpath
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from precos import ErroDeCalculo, ErroDeEntrada, calcular, carregar_json, projecao_mensal  # noqa: E402

EXTENSOES_PERMITIDAS = {".html", ".js", ".css", ".png", ".svg", ".ico", ".json", ".webmanifest", ".woff2"}

WEB = Path(__file__).resolve().parent.parent / "web"
DADOS = Path(__file__).resolve().parent.parent / "dados"
# Opcional: no cluster NÃO existe (o binaryData chega montado em /app/web).
ASSETS: Path | None = Path(__file__).resolve().parent.parent / "assets"
CACHE: dict[str, tuple[float, dict]] = {}


def ler_atualizado(caminho: Path) -> dict:
    """
    Lê o JSON e revalida pelo mtime.

    Existe porque o ConfigMap montado no Pod é atualizado pelo kubelet: sem
    isto, um preço novo exigiria reiniciar o Pod para aparecer.
    """
    chave = str(caminho)
    mtime = caminho.stat().st_mtime
    if chave not in CACHE or CACHE[chave][0] != mtime:
        CACHE[chave] = (mtime, carregar_json(caminho))
    return CACHE[chave][1]


class Handler(BaseHTTPRequestHandler):
    server_version = "calculadora-resilience"
    protocol_version = "HTTP/1.1"

    # Padrão de classe: o valor do GET é definido por requisição, mas quem NUNCA
    # passa pelo GET (POST, por exemplo) precisa de um valor válido. Sem isto,
    # qualquer POST derrubava o handler com AttributeError — bug encontrado pelo
    # teste `test_metodo_post_e_recusado`.
    _cacheavel = False

    # ------------------------------------------------------------------ saída
    def _responder(self, codigo: int, corpo: bytes, tipo: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if self._cacheavel:
            self.send_header("Cache-Control", "public, max-age=60")
        else:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _json(self, dados: dict, codigo: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8")
        self._responder(codigo, corpo, "application/json; charset=utf-8")

    def _erro(self, codigo: int, mensagem: str) -> None:
        self._json({"erro": mensagem, "codigo": codigo}, codigo)

    # ----------------------------------------------------------------- entradas
    def do_GET(self) -> None:  # noqa: N802 (nome exigido por BaseHTTPRequestHandler)
        self._cacheavel = False
        partes = urlparse(self.path)
        rota = partes.path
        query = parse_qs(partes.query)

        try:
            if rota in ("/healthz", "/api/estado"):
                return self._json({"ok": True, "servico": "calculadora-resilience"})
            if rota == "/api/openapi.json":
                return self._openapi()
            if rota == "/api/docs":
                return self._estatico("/docs.html")
            if rota == "/api/precos":
                return self._json(self._dados()["prices"])
            if rota == "/api/bom":
                return self._json(self._dados()["bom"])
            if rota == "/api/regioes":
                snap = self._dados()["prices"]
                return self._json(
                    {
                        "coletada": snap.get("regiao"),
                        "localidade": snap.get("localidade"),
                        "total": len(snap.get("regioes_disponiveis", [])),
                        "regioes": snap.get("regioes_disponiveis", []),
                        "observacao": snap.get("escopo", ""),
                    }
                )
            if rota == "/api/servicos":
                servicos = self._dados()["prices"].get("servicos_disponiveis", {})
                return self._json(
                    {
                        "total": len(servicos),
                        "servicos": [{"codigo": k, "nome": v} for k, v in sorted(servicos.items())],
                        "observacao": "Todos os serviços publicados no índice raiz da lista oficial.",
                    }
                )
            if rota == "/api/catalogo":
                return self._catalogo(parse_qs(partes.query))
            if rota == "/api/calcular":
                return self._json(self._calcular(query))
            if rota == "/api/fonte":
                snap = self._dados()["prices"]
                return self._json(
                    {
                        "fonte": snap.get("fonte", {}),
                        "gerado_em": snap.get("gerado_em"),
                        "regiao": snap.get("regiao"),
                        "problemas": snap.get("problemas", []),
                        "avisos": snap.get("avisos", []),
                    }
                )
            if rota.startswith("/api/"):
                return self._erro(404, f"rota de API desconhecida: {rota}")
            return self._estatico(("/" if rota == "/" else rota))
        except ErroDeEntrada as erro:
            # Pedido inválido é 400 — o problema é do cliente, não do servidor.
            return self._erro(400, str(erro))
        except ErroDeCalculo as erro:
            return self._erro(500, str(erro))
        except FileNotFoundError:
            return self._erro(404, "arquivo não encontrado")
        except Exception as erro:  # noqa: BLE001 — servidor pequeno: erro vira resposta, não stack trace ao cliente
            print(f"[erro] {type(erro).__name__}: {erro}", file=sys.stderr)
            return self._erro(500, "erro interno")

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        self._erro(405, "somente GET: esta aplicação não altera nada")

    # ------------------------------------------------------------------ interno
    def _openapi(self) -> None:
        """Serve a especificação OpenAPI escrita à mão (api/openapi.json).

        Ela mora em `api/` — junto do código, e não do conteúdo web — porque é
        o CONTRATO da API: é o artefato de desenho, no espírito de API first.
        """
        caminho = Path(__file__).resolve().parent / "openapi.json"
        self._cacheavel = True
        self._responder(200, caminho.read_bytes(), "application/json; charset=utf-8")

    def _catalogo(self, query: dict) -> None:
        """Catálogo de modelos EC2 descoberto do arquivo oficial da região."""
        catalogo = self._dados()["prices"].get("catalogo_ec2", {})
        busca = (query.get("busca", [""])[0] or "").strip().lower()
        familia = (query.get("familia", [""])[0] or "").strip().lower()
        try:
            limite = min(int(query.get("limite", ["200"])[0]), 1500)
        except ValueError:
            raise ErroDeEntrada("parâmetro `limite` precisa ser numérico") from None

        itens = []
        for tipo, dados in sorted(catalogo.items()):
            if busca and busca not in tipo.lower():
                continue
            if familia and familia not in (dados.get("familia", "").lower()):
                continue
            itens.append({"tipo": tipo, **dados})
        self._json(
            {
                "total_no_catalogo": len(catalogo),
                "total_filtrado": len(itens),
                "regiao": self._dados()["prices"].get("regiao"),
                "modelos": itens[:limite],
            }
        )

    def _dados(self) -> dict:
        return {
            "prices": ler_atualizado(DADOS / "prices.json"),
            "bom": ler_atualizado(DADOS / "bom.json"),
        }

    def _calcular(self, query: dict) -> dict:
        """
        Calcula o custo para a janela pedida.

        QUALQUER parâmetro cujo nome seja o `id` de um item do BOM é tratado
        como ESCOLHA daquele item — é assim que o seletor de modelo funciona
        sem o servidor saber o nome de nenhum modelo:

            /api/calcular?horas=168&node-principal=t3.large&host-terraform=t3.small

        O servidor não tem lista de modelos: quem tem é o catálogo, que veio do
        arquivo oficial da AWS.
        """
        dados = self._dados()
        bom, snap = dados["bom"], dados["prices"]
        try:
            horas = float(query.get("horas", [bom.get("horas_padrao", 168)])[0])
        except ValueError:
            raise ErroDeEntrada("parâmetro `horas` precisa ser numérico") from None
        if horas <= 0 or horas > 8760:
            raise ErroDeEntrada("`horas` fora de faixa aceitável (1 a 8760)")

        ids_do_bom = {item["id"] for item in bom.get("itens", [])}
        selecao = {
            chave: valores[0]
            for chave, valores in query.items()
            if chave in ids_do_bom and valores and valores[0]
        }

        resultado = calcular(bom, snap, horas=horas, selecao=selecao)
        resultado["mes"] = projecao_mensal(bom, snap, selecao=selecao)
        resultado["bom"] = {
            "nome": bom.get("nome"),
            "regiao": bom.get("regiao"),
            "localidade": bom.get("localidade"),
            "janela": bom.get("janela"),
        }
        return resultado

    def _estatico(self, rota: str) -> None:
        """
        Serve um arquivo do diretório web, com os assets como segundo root.

        O confinamento é por `realpath`: resolve symlink e `..` ANTES de
        comparar com a raiz. Comparar a string da rota não basta — `%2e%2e%2f`
        passa pela comparação e resolve depois.

        Por que DOIS roots: no cluster o `binaryData` do ConfigMap é montado no
        MESMO diretório do conteúdo web, então o logo está em `/app/web`. No
        ambiente local os binários vivem em `assets/` (é de lá que o Helm os
        lê), e sem o segundo root o logo simplesmente não aparecia — diferença
        entre dev e produção que o teste do PNG pegou.
        """
        relativo = unquote(rota).lstrip("/")
        extensao_aceita = False
        for raiz in filter(None, (WEB, ASSETS)):
            raiz_resolvida = raiz.resolve()
            candidato = (raiz_resolvida / relativo).resolve()
            if raiz_resolvida != candidato and raiz_resolvida not in candidato.parents:
                continue  # fora desta raiz: tenta a próxima, e não vaza nada
            if candidato.is_dir():
                candidato = candidato / "index.html"
            if candidato.suffix.lower() not in EXTENSOES_PERMITIDAS:
                continue
            extensao_aceita = True
            if not candidato.is_file():
                continue
            tipo = mimetypes.guess_type(str(candidato))[0] or "application/octet-stream"
            if tipo.startswith("text/") or tipo in ("application/javascript", "application/json"):
                tipo += "; charset=utf-8"
            self._cacheavel = True
            self._responder(200, candidato.read_bytes(), tipo)
            return

        # 403 quando a EXTENSÃO não é servível (não é "não achei": é "não
        # sirvo"); 404 quando a extensão era aceitável e o arquivo não existe.
        self._erro(404 if extensao_aceita else 403, f"não servível: /{relativo}")

    def log_message(self, formato: str, *args) -> None:
        print(f"[http] {self.address_string()} {formato % args}", file=sys.stderr)


def criar_servidor(
    web: str | Path,
    dados: str | Path,
    porta: int = 8080,
    endereco: str = "0.0.0.0",
    assets: str | Path | None = None,
):
    """
    Monta o servidor e devolve o objeto (sem `serve_forever`).

    Existe para o servidor ser TESTÁVEL: o teste sobe isto na porta 0 (porta
    livre escolhida pelo SO), conversa por HTTP de verdade e derruba no fim.
    Com tudo dentro do `main`, a única forma de testar seria abrir subprocesso —
    e aí o teste deixa de ser unitário sem ganhar nada.
    """
    global WEB, DADOS, ASSETS
    WEB = Path(posixpath.normpath(str(web))).resolve()
    DADOS = Path(posixpath.normpath(str(dados))).resolve()
    ASSETS = Path(posixpath.normpath(str(assets))).resolve() if assets else None
    for pasta in (WEB, DADOS):
        if not pasta.is_dir():
            raise FileNotFoundError(f"diretório inexistente: {pasta}")
    return ThreadingHTTPServer((endereco, porta), Handler)


def main() -> int:
    parser = argparse.ArgumentParser(description="Servidor da Calculadora Resilience")
    parser.add_argument("--web", default=str(Path(__file__).resolve().parent.parent / "web"))
    parser.add_argument("--dados", default=str(Path(__file__).resolve().parent.parent / "dados"))
    parser.add_argument(
        "--assets",
        default=str(Path(__file__).resolve().parent.parent / "assets"),
        help="segundo root de estáticos; no cluster não existe, porque o binaryData chega montado em /app/web",
    )
    parser.add_argument("--porta", type=int, default=8080)
    parser.add_argument("--endereco", default="0.0.0.0")
    args = parser.parse_args()

    # `posixpath` importado para deixar claro que a rota é tratada como caminho
    # POSIX, e não como caminho da máquina que roda o servidor.
    try:
        servidor_http = criar_servidor(args.web, args.dados, args.porta, args.endereco, args.assets)
    except FileNotFoundError as erro:
        print(erro, file=sys.stderr)
        return 2

    for esperado in ("prices.json", "bom.json"):
        if not (DADOS / esperado).exists():
            print(f"aviso: {DADOS / esperado} não existe — a API vai responder erro", file=sys.stderr)

    print(f"web={WEB}\ndados={DADOS}\nhttp://{args.endereco}:{servidor_http.server_port}", file=sys.stderr)
    servidor_http.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
