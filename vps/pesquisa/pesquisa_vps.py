#!/usr/bin/env python3
"""A PESQUISA DE SATISFAÇÃO — a parte que mora na VPS, ao lado do portal do cliente.

    «aceito a proposta, faça o PR curto» — o oficial, 26/10/2026.

O QUE ESTE PROGRAMA FAZ, E SÓ ISTO
    1. Recebe do servidor da serventia, por `POST <prefixo>/api/convites` com
       o token no cabeçalho, a CHAVE de cada convite (o sha256 do código que
       vai no link), a atribuição, o dia do convite e até quando ele vale.
    2. Serve a página pública `<prefixo>/r/<código>`: a nota de 1 a 5 e um
       comentário opcional. Uma resposta por convite.
    3. Entrega as respostas ao servidor, que as PUXA (`GET <prefixo>/api/
       respostas`) e confirma o que gravou (`POST <prefixo>/api/respostas/
       confirmar`) — e então elas saem daqui.

    Ele NÃO alcança o servidor da serventia: quem fala é o servidor, de saída
    — o mesmo desenho do portal do cliente (`vps/portal/`) e da caixa-postal
    do WhatsApp. E NÃO guarda dado de pessoa: nem nome, nem e-mail, nem
    telefone, nem número de protocolo, nem atendente. Só a chave, a
    atribuição, as datas e a resposta. Nem o código: guarda o hash dele, e o
    código só existe no link do e-mail.

AS GUARDAS DA PÁGINA PÚBLICA
    - A MESMA RESPOSTA para «convite que não existe» e «convite vencido»:
      quem tenta adivinhar não aprende nada. (O código tem 160 bits; tentar
      não leva a lugar nenhum, e mesmo assim há limite de erros por IP.)
    - UMA RESPOSTA POR CONVITE, e a trava mora no banco (chave primária).
    - O comentário entra como texto puro e sai escapado; a página não tem
      script nenhum (a política de conteúdo proíbe).
    - Sem a hora: a resposta guarda o DIA, como a pesquisa da casa — dia mais
      hora mais atribuição ajudariam a achar quem respondeu.

SEM DEPENDÊNCIA NENHUMA FORA DA BIBLIOTECA PADRÃO (Python 3.10+). Atende em
127.0.0.1, atrás do Apache (ou nginx), que faz o HTTPS. Ver `LEIA-ME.md`.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import sqlite3
import sys
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

# ----------------------------------------------------------- os números

#: O código do link: 32 caracteres do base32 (A-Z e 2-7) — 160 bits.
RE_CODIGO = re.compile(r"^[A-Z2-7]{32}$")
RE_CHAVE = re.compile(r"^[0-9a-f]{64}$")
RE_DATA = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
RE_ATRIBUICAO = re.compile(r"^[A-Za-z0-9_ ./-]{0,20}$")

NOTAS = {1: "Muito ruim", 2: "Ruim", 3: "Regular", 4: "Bom", 5: "Ótimo"}
LIMITE_DO_COMENTARIO = 1000
CONVITES_POR_CHAMADA = 200
RESPOSTAS_POR_ENTREGA = 500
CORPO_MAXIMO_API = 1024 * 1024
CORPO_MAXIMO_FORM = 8 * 1024

#: Convite que não existe, por IP, numa janela curta.
ERROS_POR_IP = 20
JANELA_IP = 15 * 60

MENSAGEM_NAO_ACHEI = ("Este convite não foi encontrado ou já venceu. Se você foi atendido "
                      "recentemente, pode avaliar no próprio cartório.")
MENSAGEM_JA = "Este convite já foi respondido. Obrigado!"
MENSAGEM_MUITAS = "Muitas tentativas seguidas. Tente de novo mais tarde."

NOMES_DAS_ATRIBUICOES = {
    "RI": "Registro de Imóveis", "RCPN": "Registro Civil", "NOTAS": "Tabelionato de Notas",
    "RTD": "Títulos e Documentos", "RCPJ": "Pessoas Jurídicas", "RTDPJ": "Títulos e Documentos",
}


class Recusa(ValueError):
    """O que o servidor mandou e não se guarda — com a razão."""


def normalizar_codigo(texto) -> str:
    return re.sub(r"[\s\-.]", "", str(texto or "")).upper()


def chave_do_codigo(codigo) -> str:
    """O mesmo cálculo de `satisfacao_envio.chave_na_vps`, byte a byte."""
    return hashlib.sha256(normalizar_codigo(codigo).encode("ascii", "replace")).hexdigest()


# ----------------------------------------------------------- o banco

ESQUEMA = """
CREATE TABLE IF NOT EXISTS convites (
    chave TEXT PRIMARY KEY,
    atribuicao TEXT NOT NULL DEFAULT '',
    dia TEXT NOT NULL,
    expira_em TEXT NOT NULL,
    recebido_em TEXT NOT NULL,
    respondido_em TEXT
);
CREATE TABLE IF NOT EXISTS respostas (
    chave TEXT PRIMARY KEY,
    nota INTEGER NOT NULL CHECK (nota BETWEEN 1 AND 5),
    comentario TEXT NOT NULL DEFAULT '',
    dia TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tentativas (
    chave TEXT PRIMARY KEY,
    inicio REAL NOT NULL,
    erros INTEGER NOT NULL
);
"""


class Pesquisa:
    """O estado da pesquisa: o banco, o token e a configuração."""

    def __init__(self, banco: str, token: str, *, prefixo: str = "/pesquisa",
                 exigir_https: bool = True, serventia: str = ""):
        if len(token or "") < 32:
            raise SystemExit("O token da pesquisa tem de ter pelo menos 32 caracteres.")
        self.banco = banco
        self.token = token
        self.prefixo = "/" + prefixo.strip("/") if prefixo.strip("/") else ""
        self.exigir_https = exigir_https
        self.serventia = serventia
        self._trava = threading.Lock()
        self._limpo_em = 0.0
        with self._con() as con:
            con.executescript(ESQUEMA)

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.banco, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    # -- a limpeza: convite vencido sai, com a resposta que o servidor não buscou
    def limpar(self, hoje: date | None = None) -> None:
        hoje_txt = (hoje or date.today()).isoformat()
        with self._trava, self._con() as con:
            velhos = [r["chave"] for r in con.execute(
                "SELECT chave FROM convites WHERE expira_em < ?", (hoje_txt,))]
            for chave in velhos:
                con.execute("DELETE FROM respostas WHERE chave = ?", (chave,))
                con.execute("DELETE FROM convites WHERE chave = ?", (chave,))
            con.execute("DELETE FROM tentativas WHERE inicio < ?", (time.time() - JANELA_IP,))
        self._limpo_em = time.time()

    def _limpar_de_vez_em_quando(self) -> None:
        if time.time() - self._limpo_em > 3600:
            self.limpar()

    # -- a trava de tentativas
    def _travado(self, chave: str) -> bool:
        with self._con() as con:
            linha = con.execute("SELECT inicio, erros FROM tentativas WHERE chave = ?",
                                (chave,)).fetchone()
        return bool(linha) and time.time() - linha["inicio"] <= JANELA_IP \
            and linha["erros"] >= ERROS_POR_IP

    def _anotar_erro(self, chave: str) -> None:
        agora = time.time()
        with self._trava, self._con() as con:
            linha = con.execute("SELECT inicio, erros FROM tentativas WHERE chave = ?",
                                (chave,)).fetchone()
            if not linha or agora - linha["inicio"] > JANELA_IP:
                con.execute("INSERT OR REPLACE INTO tentativas VALUES (?, ?, 1)", (chave, agora))
            else:
                con.execute("UPDATE tentativas SET erros = erros + 1 WHERE chave = ?", (chave,))

    # -- a página
    def convite(self, codigo: str, ip: str, hoje: date | None = None) -> tuple[str, dict | None]:
        """("ok", convite) | ("ja", None) | ("nao_achei", None) | ("muitas", None)."""
        self._limpar_de_vez_em_quando()
        if self._travado(f"ip:{ip}"):
            return "muitas", None
        codigo = normalizar_codigo(codigo)
        linha = None
        if RE_CODIGO.match(codigo):
            with self._con() as con:
                linha = con.execute("SELECT * FROM convites WHERE chave = ?",
                                    (chave_do_codigo(codigo),)).fetchone()
        hoje_txt = (hoje or date.today()).isoformat()
        if not linha or linha["expira_em"] < hoje_txt:
            self._anotar_erro(f"ip:{ip}")
            return "nao_achei", None
        if linha["respondido_em"]:
            return "ja", None
        return "ok", dict(linha)

    def responder(self, codigo: str, nota, comentario, ip: str,
                  hoje: date | None = None) -> str:
        """"ok" | "ja" | "nao_achei" | "muitas" | "nota". Grava uma vez só."""
        estado, convite = self.convite(codigo, ip, hoje)
        if estado != "ok":
            return estado
        try:
            n = int(str(nota).strip())
        except (TypeError, ValueError):
            return "nota"
        if n not in NOTAS:
            return "nota"
        texto = str(comentario or "").replace("\x00", "").strip()[:LIMITE_DO_COMENTARIO]
        dia = (hoje or date.today()).isoformat()
        with self._trava, self._con() as con:
            # A trava da segunda resposta mora no banco: a chave primária, e a
            # marca no convite na mesma transação.
            try:
                con.execute("INSERT INTO respostas (chave, nota, comentario, dia) "
                            "VALUES (?, ?, ?, ?)", (convite["chave"], n, texto, dia))
            except sqlite3.IntegrityError:
                return "ja"
            con.execute("UPDATE convites SET respondido_em = ? WHERE chave = ?",
                        (dia, convite["chave"]))
        return "ok"

    # -- o que o servidor manda
    def receber(self, corpo: bytes, hoje: date | None = None) -> dict:
        """Grava o lote inteiro ou nada. Levanta `Recusa`."""
        try:
            dados = json.loads(corpo.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as erro:
            raise Recusa("o corpo não é JSON em UTF-8") from erro
        convites = dados.get("convites") if isinstance(dados, dict) else None
        if not isinstance(convites, list) or len(convites) > CONVITES_POR_CHAMADA:
            raise Recusa(f"esperava 'convites' com até {CONVITES_POR_CHAMADA} itens")
        limpos = [self._conferir(c) for c in convites]
        agora = (hoje or date.today()).isoformat()
        gravados = removidos = 0
        with self._trava, self._con() as con:
            for c in limpos:
                if c.get("remover"):
                    con.execute("DELETE FROM respostas WHERE chave = ?", (c["chave"],))
                    con.execute("DELETE FROM convites WHERE chave = ?", (c["chave"],))
                    removidos += 1
                    continue
                # O convite que volta NÃO perde a marca de respondido: mandar de
                # novo não reabre a pesquisa.
                con.execute(
                    """INSERT INTO convites (chave, atribuicao, dia, expira_em, recebido_em)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(chave) DO UPDATE SET atribuicao = excluded.atribuicao,
                           dia = excluded.dia, expira_em = excluded.expira_em""",
                    (c["chave"], c["atribuicao"], c["dia"], c["expira_em"], agora))
                gravados += 1
        return {"ok": True, "gravados": gravados, "removidos": removidos}

    @staticmethod
    def _conferir(c) -> dict:
        if not isinstance(c, dict):
            raise Recusa("convite que não é objeto")
        chave = c.get("chave")
        if not isinstance(chave, str) or not RE_CHAVE.match(chave):
            raise Recusa("chave fora do formato (sha256 em hexadecimal)")
        if c.get("remover") is True:
            if set(c) - {"chave", "remover"}:
                raise Recusa("a ordem de remover leva só a chave")
            return {"chave": chave, "remover": True}
        # A LISTA É FECHADA: campo que não está aqui recusa o lote — é o que
        # impede o servidor de mandar, por engano, um nome ou um e-mail.
        sobra = set(c) - {"chave", "atribuicao", "dia", "expira_em"}
        if sobra:
            raise Recusa(f"campos que a pesquisa não guarda: {sorted(sobra)}")
        atribuicao = c.get("atribuicao") or ""
        if not isinstance(atribuicao, str) or not RE_ATRIBUICAO.match(atribuicao):
            raise Recusa("atribuição fora do formato")
        for campo in ("dia", "expira_em"):
            valor = c.get(campo)
            if not isinstance(valor, str) or not RE_DATA.match(valor):
                raise Recusa(f"{campo} fora do formato AAAA-MM-DD")
        return {"chave": chave, "atribuicao": atribuicao, "dia": c["dia"],
                "expira_em": c["expira_em"]}

    def respostas(self) -> list[dict]:
        """O que o servidor ainda não confirmou. Só lê."""
        with self._con() as con:
            return [dict(r) for r in con.execute(
                "SELECT chave, nota, comentario, dia FROM respostas ORDER BY dia, chave "
                "LIMIT ?", (RESPOSTAS_POR_ENTREGA,))]

    def confirmar(self, corpo: bytes) -> dict:
        """O servidor gravou: a resposta sai daqui. O convite fica, respondido,
        até vencer — o link continua dizendo «já respondido»."""
        try:
            dados = json.loads(corpo.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as erro:
            raise Recusa("o corpo não é JSON em UTF-8") from erro
        chaves = dados.get("chaves") if isinstance(dados, dict) else None
        if not isinstance(chaves, list) or len(chaves) > RESPOSTAS_POR_ENTREGA \
                or not all(isinstance(k, str) and RE_CHAVE.match(k) for k in chaves):
            raise Recusa(f"esperava 'chaves' (sha256) com até {RESPOSTAS_POR_ENTREGA} itens")
        apagadas = 0
        with self._trava, self._con() as con:
            for k in chaves:
                apagadas += con.execute("DELETE FROM respostas WHERE chave = ?", (k,)).rowcount
        return {"ok": True, "apagadas": apagadas}

    def contar(self) -> dict:
        with self._con() as con:
            return {"convites": int(con.execute("SELECT count(*) FROM convites").fetchone()[0]),
                    "respostas": int(con.execute("SELECT count(*) FROM respostas").fetchone()[0])}


# ----------------------------------------------------------- as páginas

ESTILO = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;
background:#f4f5f7;color:#1d2330}
main{max-width:520px;margin:0 auto;padding:24px 16px}
h1{font-size:1.4rem;margin:0 0 4px}.sub{color:#5a6372;margin:0 0 20px}
.cartao{background:#fff;border-radius:10px;padding:20px;box-shadow:0 1px 3px #0002}
fieldset{border:0;padding:0;margin:0}legend{font-weight:600;margin-bottom:8px}
.notas label{display:block;padding:10px;border:1px solid #c5cad3;border-radius:8px;margin:6px 0}
textarea{width:100%;box-sizing:border-box;padding:10px;font-size:1rem;min-height:90px;
border:1px solid #c5cad3;border-radius:8px}
button{margin-top:16px;width:100%;padding:12px;font-size:1.05rem;border:0;
border-radius:8px;background:#1f5fa8;color:#fff;cursor:pointer}
.aviso{background:#fff4e5;border-left:4px solid #e08a00;padding:12px;margin-bottom:16px}
.rodape{color:#5a6372;font-size:.85rem;margin-top:20px}
"""


def _pagina(pesquisa: Pesquisa, corpo: str) -> bytes:
    titulo = "Pesquisa de satisfação"
    sub = html.escape(pesquisa.serventia) if pesquisa.serventia else ""
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{titulo}</title><style>{ESTILO}</style></head>
<body><main><h1>{titulo}</h1><p class="sub">{sub}</p>{corpo}
<p class="rodape">A resposta é anônima: esta página não pede nem guarda o seu nome,
e-mail ou telefone.</p></main></body></html>""".encode("utf-8")


def _aviso(pesquisa: Pesquisa, texto: str) -> bytes:
    return _pagina(pesquisa, f'<div class="aviso">{html.escape(texto)}</div>')


def _formulario(pesquisa: Pesquisa, codigo: str, convite: dict, erro: str = "") -> bytes:
    caixa = f'<div class="aviso">{html.escape(erro)}</div>' if erro else ""
    area = NOMES_DAS_ATRIBUICOES.get(str(convite.get("atribuicao") or "").upper(), "")
    sobre = f" ({html.escape(area)})" if area else ""
    opcoes = "".join(
        f'<label><input type="radio" name="nota" value="{n}" required> {n} — {html.escape(t)}'
        f'</label>' for n, t in sorted(NOTAS.items(), reverse=True))
    return _pagina(pesquisa, f"""{caixa}<form class="cartao" method="post"
action="{pesquisa.prefixo}/r/{html.escape(codigo)}" autocomplete="off">
<fieldset class="notas"><legend>Como foi o seu atendimento{sobre}?</legend>{opcoes}</fieldset>
<label for="comentario"><strong>Quer comentar?</strong> (opcional)</label>
<textarea id="comentario" name="comentario" maxlength="{LIMITE_DO_COMENTARIO}"></textarea>
<button type="submit">Enviar a avaliação</button>
<p class="rodape">Não escreva CPF, telefone nem outros dados pessoais no comentário.</p>
</form>""")


# ----------------------------------------------------------- o HTTP

class Atendente(BaseHTTPRequestHandler):
    pesquisa: Pesquisa = None  # type: ignore[assignment]
    server_version = "pesquisa"
    sys_version = ""

    # Sem log de corpo nem de cabeçalho; e o caminho, que leva o código, não
    # se escreve inteiro.
    def log_message(self, formato, *args):  # noqa: D401
        linha = formato % args
        linha = re.sub(r"/r/[A-Za-z0-9]+", "/r/<codigo>", linha)
        sys.stderr.write("%s %s\n" % (self.log_date_time_string(), linha))

    def _ip(self) -> str:
        par = self.client_address[0]
        encaminhado = self.headers.get("X-Forwarded-For", "")
        if par in ("127.0.0.1", "::1") and encaminhado:
            # O Apache ACRESCENTA o IP de quem chegou no fim; o começo se falsifica.
            return encaminhado.split(",")[-1].strip()[:64]
        return par

    def _cabecalhos(self, tipo: str, tamanho: int, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(tamanho))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        # O código está no endereço: ele não vai, como referência, a site nenhum.
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; "
                         "form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        if self.pesquisa.exigir_https:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        self.end_headers()

    def _html(self, corpo: bytes, status: int = 200) -> None:
        self._cabecalhos("text/html; charset=utf-8", len(corpo), status)
        self.wfile.write(corpo)

    def _json(self, dados: dict, status: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self._cabecalhos("application/json; charset=utf-8", len(corpo), status)
        self.wfile.write(corpo)

    def _https_ok(self) -> bool:
        if not self.pesquisa.exigir_https:
            return True
        if self.headers.get("X-Forwarded-Proto", "").lower() == "https":
            return True
        self._html(b"Use https.", 403)
        return False

    def _caminho(self) -> str | None:
        alvo = self.path.split("?", 1)[0]
        prefixo = self.pesquisa.prefixo
        if prefixo and not (alvo == prefixo or alvo.startswith(prefixo + "/")):
            return None
        return alvo[len(prefixo):] or "/"

    def _ler(self, maximo: int) -> bytes | None:
        try:
            tamanho = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if tamanho < 0 or tamanho > maximo:
            return None
        return self.rfile.read(tamanho)

    def _autorizado(self) -> bool:
        dado = self.headers.get("Authorization", "")
        esperado = "Bearer " + self.pesquisa.token
        return hmac.compare_digest(dado.encode("utf-8"), esperado.encode("utf-8"))

    def _estado_na_tela(self, estado: str) -> None:
        if estado == "muitas":
            return self._html(_aviso(self.pesquisa, MENSAGEM_MUITAS), 429)
        if estado == "ja":
            return self._html(_aviso(self.pesquisa, MENSAGEM_JA))
        return self._html(_aviso(self.pesquisa, MENSAGEM_NAO_ACHEI), 404)

    def do_GET(self):  # noqa: N802
        if not self._https_ok():
            return None
        caminho = self._caminho()
        if caminho in ("/api/saude", "/api/respostas"):
            if not self._autorizado():
                return self._json({"ok": False, "motivo": "token"}, 401)
            if caminho == "/api/saude":
                return self._json({"ok": True, **self.pesquisa.contar()})
            return self._json({"ok": True, "respostas": self.pesquisa.respostas()})
        if caminho and caminho.startswith("/r/"):
            codigo = caminho[3:]
            estado, convite = self.pesquisa.convite(codigo, self._ip())
            if estado != "ok":
                return self._estado_na_tela(estado)
            return self._html(_formulario(self.pesquisa, normalizar_codigo(codigo), convite))
        return self._html(b"Nada aqui.", 404)

    def do_POST(self):  # noqa: N802
        if not self._https_ok():
            return None
        caminho = self._caminho()
        if caminho in ("/api/convites", "/api/respostas/confirmar"):
            if not self._autorizado():
                return self._json({"ok": False, "motivo": "token"}, 401)
            corpo = self._ler(CORPO_MAXIMO_API)
            if corpo is None:
                return self._json({"ok": False, "motivo": "corpo grande demais"}, 413)
            try:
                if caminho == "/api/convites":
                    return self._json(self.pesquisa.receber(corpo))
                return self._json(self.pesquisa.confirmar(corpo))
            except Recusa as erro:
                return self._json({"ok": False, "motivo": str(erro)}, 400)
        if caminho and caminho.startswith("/r/"):
            codigo = caminho[3:]
            corpo = self._ler(CORPO_MAXIMO_FORM)
            if corpo is None:
                return self._html(_aviso(self.pesquisa, "Comentário grande demais."), 413)
            campos = {k: v[0] for k, v in parse_qs(
                corpo.decode("utf-8", "replace"), max_num_fields=5).items()}
            estado = self.pesquisa.responder(codigo, campos.get("nota"),
                                             campos.get("comentario", ""), self._ip())
            if estado == "nota":
                _e, convite = self.pesquisa.convite(codigo, self._ip())
                if convite:
                    return self._html(_formulario(self.pesquisa, normalizar_codigo(codigo),
                                                  convite, "Escolha uma nota de 1 a 5."), 400)
                return self._estado_na_tela("nao_achei")
            if estado != "ok":
                return self._estado_na_tela(estado)
            return self._html(_pagina(self.pesquisa, '<div class="cartao"><p><strong>Obrigado!'
                                      '</strong> A sua avaliação foi registrada.</p></div>'))
        return self._html(b"Nada aqui.", 404)


def servir(pesquisa: Pesquisa, endereco: str = "127.0.0.1",
           porta: int = 8782) -> ThreadingHTTPServer:
    classe = type("AtendenteDaPesquisa", (Atendente,), {"pesquisa": pesquisa})
    return ThreadingHTTPServer((endereco, porta), classe)


def _token_do_ambiente() -> str:
    # O CONTEÚDO é o mesmo token do portal (o servidor da casa usa o do
    # `portal.cred` para os dois serviços da mesma VPS); o ARQUIVO é deste
    # serviço, legível só pelo usuário dele. Ver LEIA-ME.md.
    arquivo = os.environ.get("PESQUISA_TOKEN_ARQUIVO", "/etc/cartorio-pesquisa/token")
    try:
        return open(arquivo, encoding="utf-8").read().strip()
    except OSError:
        raise SystemExit(f"Não li o token em {arquivo}. Ver LEIA-ME.md.")


def main() -> int:
    pesquisa = Pesquisa(
        os.environ.get("PESQUISA_BANCO", "/var/lib/cartorio-pesquisa/pesquisa.sqlite3"),
        _token_do_ambiente(),
        prefixo=os.environ.get("PESQUISA_PREFIXO", "/pesquisa"),
        exigir_https=os.environ.get("PESQUISA_EXIGIR_HTTPS", "1") != "0",
        serventia=os.environ.get("PESQUISA_SERVENTIA", ""))
    endereco = os.environ.get("PESQUISA_ENDERECO", "127.0.0.1")
    porta = int(os.environ.get("PESQUISA_PORTA", "8782"))
    servidor = servir(pesquisa, endereco, porta)
    sys.stderr.write(f"pesquisa de satisfação em http://{endereco}:{porta}{pesquisa.prefixo}/\n")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
