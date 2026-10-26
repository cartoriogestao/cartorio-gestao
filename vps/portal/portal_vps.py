#!/usr/bin/env python3
"""O PORTAL DO CLIENTE — a parte que mora na VPS.

    «portal do cliente para acompanhar o pedido e baixar o recibo», no VPS do
     WhatsApp, com «código no recibo». O oficial, 26/10/2026.

O QUE ESTE PROGRAMA FAZ, E SÓ ISTO
    1. Recebe do servidor da serventia, por `POST <prefixo>/api/retratos` com o
       token no cabeçalho, o retrato mínimo de cada protocolo (número, HASH do
       código, situação, previsão, última movimentação, atribuição, recibo em
       PDF) e o guarda num SQLite local.
    2. Serve a página pública: o cliente digita número + código e vê a
       situação; baixa o COMPROVANTE DE ACOMPANHAMENTO em PDF (e o recibo,
       se um dia o oficial o liberar — de fábrica ele não sobe).

O COMPROVANTE DE ACOMPANHAMENTO (decisão do oficial em 26/10/2026: «PDF que
o cliente baixa: informações essenciais de interesse do cliente»)
    É desenhado AQUI, na hora do download (`comprovante_pdf`), só com os
    campos da lista fechada: número, código MASCARADO (só os dois últimos
    caracteres — o código inteiro é a senha da consulta, e o PDF baixado vai
    parar em pasta, e-mail e impressora), data de entrada, atribuição, serviço
    pedido, situação com a data, prazo previsto, exigências pendentes, se está
    pronto para retirar e o contato da serventia (`PORTAL_CONTATO`). Não leva
    CPF/CNPJ, nome de pagador ou de parte, valor, nem observação interna: o
    servidor manda o texto já limpo, e esta ponta RECUSA o lote em que o
    serviço ou a exigência tragam cara de CPF/CNPJ ou de valor.

    Ele NÃO alcança o servidor da serventia — quem fala é o servidor, de
    saída. E não sabe o código de ninguém: guarda só o hash (PBKDF2 com sal e
    200 mil voltas), que é o que se confere a cada consulta.

POR QUE SQLITE, E NÃO O MYSQL QUE JÁ ESTÁ NA VPS
    São alguns milhares de linhas e uma escrita a cada quinze minutos; o SQLite
    vem com o Python e não pede driver, usuário de banco nem senha a mais. E o
    portal fica ISOLADO do que mais roda na VPS: um MySQL compartilhado é um
    lugar onde outro programa da máquina (ou um erro de permissão dele) lê os
    recibos dos clientes. O arquivo mora numa pasta só do usuário do serviço.

SEM DEPENDÊNCIA NENHUMA FORA DA BIBLIOTECA PADRÃO (Python 3.10+). Atende em
127.0.0.1, atrás do Apache (ou nginx), que faz o HTTPS. Ver `LEIA-ME.md`.

AS TRÊS GUARDAS DA PÁGINA PÚBLICA
    - A MESMA RESPOSTA para «número que não existe» e «código errado», com o
      mesmo trabalho de hash nos dois: quem tenta adivinhar não aprende quais
      números existem.
    - LIMITE DE ERROS POR IP E POR NÚMERO. O número é sequencial e se adivinha;
      o código (8 caracteres de 32, 40 bits) não — desde que não se possa tentar
      à vontade. Passou do limite, o número fica travado até a janela acabar,
      inclusive para o código certo.
    - Nada de código na URL: número e código vão no corpo do formulário (POST),
      que não fica no histórico do navegador nem no log do Apache.
"""
from __future__ import annotations

import base64
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
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

# ----------------------------------------------------------- os números

ALFABETO = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
TAMANHO_DO_CODIGO = 8
ITERACOES_MAXIMAS = 2_000_000

#: Erros aceitos por IP numa janela curta, e por NÚMERO numa janela longa.
ERROS_POR_IP = 10
JANELA_IP = 15 * 60
ERROS_POR_NUMERO = 10
JANELA_NUMERO = 24 * 3600

#: Quanto tempo o retrato fica sem o servidor mandar nada antes de sair.
DIAS_SEM_NOTICIA = 180
CORPO_MAXIMO_API = 25 * 1024 * 1024
CORPO_MAXIMO_FORM = 2048
RETRATOS_POR_CHAMADA = 100
RECIBOS_POR_PROTOCOLO = 5
PDF_MAXIMO = 3 * 1024 * 1024

#: Quantas conferências de hash ao mesmo tempo. Cada uma custa ~0,1 s de CPU;
#: sem teto, uma enxurrada de pedidos de IPs diferentes pararia a VPS.
_HASHES_AO_MESMO_TEMPO = threading.BoundedSemaphore(4)

RE_NUMERO = re.compile(r"^[0-9]{4}\.[0-9]{2}\.[0-9]{1,7}$")
RE_HASH = re.compile(r"^pbkdf2_sha256\$[0-9]{1,7}\$[0-9a-f]{32}\$[0-9a-f]{64}$")
RE_DATA = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
RE_MOMENTO = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}([T ][0-9]{2}:[0-9]{2})?$")
RE_RECIBO = re.compile(r"^recibo-[0-9]{1,9}-[0-9]{4}\.pdf$")

#: O comprovante de acompanhamento (26/10/2026). Os tetos são os de
#: `acompanhamento_cliente` (EXIGENCIAS_NO_COMPROVANTE, TAMANHO_DA_EXIGENCIA,
#: TAMANHO_DO_SERVICO), e as duas pontas têm de concordar.
EXIGENCIAS_MAXIMAS = 10
TAMANHO_DA_EXIGENCIA = 400
TAMANHO_DO_SERVICO = 200
#: A segunda tranca: texto do comprovante com cara de documento ou de valor
#: recusa o lote (o servidor já mascara — isto pega o servidor que errar).
RE_DOCUMENTO = re.compile(r"(?<!\d)(?:\d{3}\.?\d{3}\.?\d{3}-?\d{2}|"
                          r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?!\d)")
RE_VALOR = re.compile(r"R\$\s*\d|(?<![\d.,])\d{1,3}(?:\.\d{3})*,\d{2}(?![\d,])")

MENSAGEM_NAO_CONFERE = ("Número do protocolo ou código não conferem. Confira no "
                        "recibo ou no protocolo de recepção e tente de novo.")
MENSAGEM_MUITAS = ("Muitas tentativas sem acerto. Por segurança, a consulta deste "
                   "protocolo (ou deste acesso) ficou suspensa por algumas horas. "
                   "Se precisar antes, fale com o cartório.")


class Recusa(ValueError):
    """O que o servidor mandou e não se guarda — com a razão."""


# ----------------------------------------------------------- o código

def normalizar_codigo(texto) -> str:
    return re.sub(r"[\s\-\.]", "", str(texto or "")).upper()


def confere(codigo, gravado) -> bool:
    """O mesmo formato de `acompanhamento_cliente.hash_do_codigo`, byte a byte."""
    try:
        prefixo, voltas, sal, esperado = str(gravado or "").split("$")
        voltas_n = int(voltas)
        if prefixo != "pbkdf2_sha256" or not 1 <= voltas_n <= ITERACOES_MAXIMAS:
            return False
        with _HASHES_AO_MESMO_TEMPO:
            calculado = hashlib.pbkdf2_hmac(
                "sha256", normalizar_codigo(codigo).encode("ascii", "replace"),
                bytes.fromhex(sal), voltas_n).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculado, esperado)


def _hash_de_mentira() -> str:
    # Um hash fixo e válido, para gastar o mesmo tempo quando não há o que
    # conferir. Gerado uma vez: o tempo é o que importa, não o valor.
    sal = "00" * 16
    feito = hashlib.pbkdf2_hmac("sha256", b"22222222", bytes.fromhex(sal), 200_000).hex()
    return f"pbkdf2_sha256$200000${sal}${feito}"


# ----------------------------------------------------------- o banco

ESQUEMA = """
CREATE TABLE IF NOT EXISTS retratos (
    numero TEXT PRIMARY KEY,
    codigo_hash TEXT NOT NULL,
    situacao TEXT NOT NULL,
    previsao TEXT,
    atualizado_em TEXT,
    atribuicao TEXT,
    expira_em TEXT NOT NULL,
    recebido_em TEXT NOT NULL,
    entrada TEXT,
    servico TEXT,
    exigencias TEXT,
    pronto INTEGER
);
CREATE TABLE IF NOT EXISTS recibos (
    numero TEXT NOT NULL,
    nome TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    pdf BLOB NOT NULL,
    PRIMARY KEY (numero, nome)
);
CREATE TABLE IF NOT EXISTS tentativas (
    chave TEXT PRIMARY KEY,
    inicio REAL NOT NULL,
    erros INTEGER NOT NULL
);
"""
COLUNAS_DO_COMPROVANTE = (("entrada", "TEXT"), ("servico", "TEXT"),
                          ("exigencias", "TEXT"), ("pronto", "INTEGER"))


class Portal:
    """O estado do portal: o banco, o token e a configuração."""

    def __init__(self, banco: str, token: str, *, prefixo: str = "/portal",
                 exigir_https: bool = True, serventia: str = "",
                 contato: str = ""):
        if len(token or "") < 32:
            raise SystemExit("O token do portal tem de ter pelo menos 32 caracteres.")
        self.banco = banco
        self.token = token
        self.prefixo = "/" + prefixo.strip("/") if prefixo.strip("/") else ""
        self.exigir_https = exigir_https
        self.serventia = serventia
        self.contato = contato
        self._trava = threading.Lock()
        self._limpo_em = 0.0
        self._mentira = _hash_de_mentira()
        with self._con() as con:
            con.executescript(ESQUEMA)
            # As colunas do comprovante (26/10/2026) num banco que já existia.
            tem = {r["name"] for r in con.execute("PRAGMA table_info(retratos)")}
            for coluna, tipo in COLUNAS_DO_COMPROVANTE:
                if coluna not in tem:
                    con.execute(f"ALTER TABLE retratos ADD COLUMN {coluna} {tipo}")

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.banco, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    # -- a limpeza
    def limpar(self, agora: float | None = None) -> None:
        agora = agora if agora is not None else time.time()
        hoje = date.today().isoformat()
        limite = (datetime.now() - timedelta(days=DIAS_SEM_NOTICIA)).isoformat()
        with self._trava, self._con() as con:
            velhos = [r["numero"] for r in con.execute(
                "SELECT numero FROM retratos WHERE expira_em < ? OR recebido_em < ?",
                (hoje, limite))]
            for n in velhos:
                con.execute("DELETE FROM recibos WHERE numero = ?", (n,))
                con.execute("DELETE FROM retratos WHERE numero = ?", (n,))
            con.execute("DELETE FROM tentativas WHERE inicio < ?",
                        (agora - max(JANELA_IP, JANELA_NUMERO),))
        self._limpo_em = agora

    def _limpar_de_vez_em_quando(self) -> None:
        if time.time() - self._limpo_em > 3600:
            self.limpar()

    # -- a trava de tentativas
    def _travado(self, chave: str, limite: int, janela: int) -> bool:
        with self._con() as con:
            linha = con.execute("SELECT inicio, erros FROM tentativas WHERE chave = ?",
                                (chave,)).fetchone()
        return bool(linha) and time.time() - linha["inicio"] <= janela \
            and linha["erros"] >= limite

    def _anotar_erro(self, chave: str, janela: int) -> None:
        agora = time.time()
        with self._trava, self._con() as con:
            linha = con.execute("SELECT inicio, erros FROM tentativas WHERE chave = ?",
                                (chave,)).fetchone()
            if not linha or agora - linha["inicio"] > janela:
                con.execute("INSERT OR REPLACE INTO tentativas VALUES (?, ?, 1)",
                            (chave, agora))
            else:
                con.execute("UPDATE tentativas SET erros = erros + 1 WHERE chave = ?",
                            (chave,))

    # -- a consulta
    def consultar(self, numero: str, codigo: str, ip: str) -> tuple[str, dict | None]:
        """("ok", retrato) | ("nao_confere", None) | ("muitas", None)."""
        self._limpar_de_vez_em_quando()
        numero = str(numero or "").strip()[:40]
        chave_ip, chave_num = f"ip:{ip}", f"num:{numero}"
        if self._travado(chave_ip, ERROS_POR_IP, JANELA_IP) or \
                self._travado(chave_num, ERROS_POR_NUMERO, JANELA_NUMERO):
            return "muitas", None
        retrato = None
        if RE_NUMERO.match(numero):
            with self._con() as con:
                linha = con.execute("SELECT * FROM retratos WHERE numero = ?",
                                    (numero,)).fetchone()
            retrato = dict(linha) if linha else None
        gravado = retrato["codigo_hash"] if retrato else self._mentira
        acertou = confere(codigo, gravado) and retrato is not None
        if not acertou:
            self._anotar_erro(chave_ip, JANELA_IP)
            self._anotar_erro(chave_num, JANELA_NUMERO)
            return "nao_confere", None
        with self._con() as con:
            retrato["recibos"] = [r["nome"] for r in con.execute(
                "SELECT nome FROM recibos WHERE numero = ? ORDER BY nome", (numero,))]
        try:
            exigencias = json.loads(retrato.get("exigencias") or "[]")
        except ValueError:
            exigencias = []
        retrato["exigencias"] = [str(e) for e in exigencias] if isinstance(exigencias, list) else []
        return "ok", retrato

    def recibo(self, numero: str, nome: str) -> bytes | None:
        with self._con() as con:
            linha = con.execute("SELECT pdf FROM recibos WHERE numero = ? AND nome = ?",
                                (numero, nome)).fetchone()
        return bytes(linha["pdf"]) if linha else None

    # -- o que o servidor manda
    def receber(self, corpo: bytes) -> dict:
        """Grava o lote inteiro ou nada. Levanta `Recusa`."""
        try:
            dados = json.loads(corpo.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as erro:
            raise Recusa("o corpo não é JSON em UTF-8") from erro
        retratos = dados.get("retratos") if isinstance(dados, dict) else None
        if not isinstance(retratos, list) or len(retratos) > RETRATOS_POR_CHAMADA:
            raise Recusa(f"esperava 'retratos' com até {RETRATOS_POR_CHAMADA} itens")
        limpos = [self._conferir(r) for r in retratos]
        agora = datetime.now().isoformat(timespec="seconds")
        gravados = removidos = 0
        with self._trava, self._con() as con:
            for r in limpos:
                con.execute("DELETE FROM recibos WHERE numero = ?", (r["numero"],))
                if r.get("remover"):
                    con.execute("DELETE FROM retratos WHERE numero = ?", (r["numero"],))
                    removidos += 1
                    continue
                con.execute(
                    """INSERT OR REPLACE INTO retratos
                       (numero, codigo_hash, situacao, previsao, atualizado_em,
                        atribuicao, expira_em, recebido_em,
                        entrada, servico, exigencias, pronto)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (r["numero"], r["codigo_hash"], r["situacao_publica"],
                     r["previsao"], r["atualizado_em"], r["atribuicao"],
                     r["expira_em"], agora, r["entrada"], r["servico"],
                     json.dumps(r["exigencias"], ensure_ascii=False),
                     None if r["pronto"] is None else int(r["pronto"])))
                for rec in r["recibos"]:
                    con.execute("INSERT INTO recibos VALUES (?,?,?,?)",
                                (r["numero"], rec["nome"], rec["sha256"], rec["pdf"]))
                gravados += 1
        self.limpar()
        return {"ok": True, "gravados": gravados, "removidos": removidos}

    @staticmethod
    def _texto(valor, maximo: int, obrigatorio: bool = False) -> str | None:
        if valor is None or valor == "":
            if obrigatorio:
                raise Recusa("campo obrigatório em branco")
            return None
        if not isinstance(valor, str) or len(valor) > maximo or "<" in valor:
            raise Recusa(f"texto inválido: {str(valor)[:40]!r}")
        return valor

    def _conferir(self, r) -> dict:
        if not isinstance(r, dict):
            raise Recusa("retrato que não é objeto")
        numero = r.get("numero")
        if not isinstance(numero, str) or not RE_NUMERO.match(numero):
            raise Recusa(f"número de protocolo inválido: {str(numero)[:40]!r}")
        if r.get("remover") is True:
            return {"numero": numero, "remover": True}
        # A LISTA É FECHADA: campo que não está aqui não se guarda, e campo
        # desconhecido recusa o lote — é o que impede o servidor de mandar, por
        # engano, um nome ou um CPF que a página mostraria.
        permitidos = {"numero", "codigo_hash", "situacao_publica", "previsao",
                      "atualizado_em", "atribuicao", "expira_em", "recibos",
                      # o comprovante de acompanhamento (26/10/2026)
                      "entrada", "servico", "exigencias", "pronto"}
        sobra = set(r) - permitidos
        if sobra:
            raise Recusa(f"campos que o portal não guarda: {sorted(sobra)}")
        codigo_hash = r.get("codigo_hash")
        if not isinstance(codigo_hash, str) or not RE_HASH.match(codigo_hash):
            raise Recusa(f"{numero}: hash do código fora do formato")
        previsao = self._texto(r.get("previsao"), 10)
        if previsao and not RE_DATA.match(previsao):
            raise Recusa(f"{numero}: previsão fora do formato AAAA-MM-DD")
        atualizado = self._texto(r.get("atualizado_em"), 16)
        if atualizado and not RE_MOMENTO.match(atualizado):
            raise Recusa(f"{numero}: atualizado_em fora do formato")
        expira = self._texto(r.get("expira_em"), 10, obrigatorio=True)
        if not RE_DATA.match(expira):
            raise Recusa(f"{numero}: expira_em fora do formato")
        recibos = []
        lista = r.get("recibos") or []
        if not isinstance(lista, list) or len(lista) > RECIBOS_POR_PROTOCOLO:
            raise Recusa(f"{numero}: recibos demais")
        for rec in lista:
            if not isinstance(rec, dict) or not RE_RECIBO.match(str(rec.get("nome"))):
                raise Recusa(f"{numero}: nome de recibo inválido")
            try:
                pdf = base64.b64decode(str(rec.get("pdf") or ""), validate=True)
            except ValueError as erro:
                raise Recusa(f"{numero}: PDF que não é base64") from erro
            if len(pdf) > PDF_MAXIMO or not pdf.startswith(b"%PDF-"):
                raise Recusa(f"{numero}: o recibo não é um PDF (ou é grande demais)")
            if hashlib.sha256(pdf).hexdigest() != rec.get("sha256"):
                raise Recusa(f"{numero}: o PDF chegou diferente do que saiu")
            recibos.append({"nome": rec["nome"], "sha256": rec["sha256"], "pdf": pdf})
        # -- o comprovante (26/10/2026): tudo opcional, para o servidor antigo
        entrada = self._texto(r.get("entrada"), 10)
        if entrada and not RE_DATA.match(entrada):
            raise Recusa(f"{numero}: entrada fora do formato AAAA-MM-DD")
        servico = self._texto(r.get("servico"), TAMANHO_DO_SERVICO)
        lista_ex = r.get("exigencias") or []
        if not isinstance(lista_ex, list) or len(lista_ex) > EXIGENCIAS_MAXIMAS:
            raise Recusa(f"{numero}: exigências demais (até {EXIGENCIAS_MAXIMAS})")
        exigencias = [self._texto(e, TAMANHO_DA_EXIGENCIA, obrigatorio=True)
                      for e in lista_ex]
        pronto = r.get("pronto")
        if pronto is not None and not isinstance(pronto, bool):
            raise Recusa(f"{numero}: «pronto» tem de ser verdadeiro ou falso")
        for texto in [servico or ""] + exigencias:
            if RE_DOCUMENTO.search(texto) or RE_VALOR.search(texto):
                raise Recusa(f"{numero}: texto do comprovante com cara de CPF/CNPJ "
                             "ou de valor — o comprovante não leva isso")
        return {"numero": numero, "codigo_hash": codigo_hash,
                "situacao_publica": self._texto(r.get("situacao_publica"), 60,
                                                obrigatorio=True),
                "previsao": previsao, "atualizado_em": atualizado,
                "atribuicao": self._texto(r.get("atribuicao"), 60),
                "expira_em": expira, "recibos": recibos,
                "entrada": entrada, "servico": servico, "exigencias": exigencias,
                "pronto": pronto}

    def contar(self) -> int:
        with self._con() as con:
            return int(con.execute("SELECT count(*) FROM retratos").fetchone()[0])


# ----------------------------------------------------------- as páginas

ESTILO = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;
background:#f4f5f7;color:#1d2330}
main{max-width:520px;margin:0 auto;padding:24px 16px}
h1{font-size:1.4rem;margin:0 0 4px}.sub{color:#5a6372;margin:0 0 20px}
.cartao{background:#fff;border-radius:10px;padding:20px;box-shadow:0 1px 3px #0002}
label{display:block;font-weight:600;margin:12px 0 4px}
input{width:100%;box-sizing:border-box;padding:12px;font-size:1.1rem;
border:1px solid #c5cad3;border-radius:8px}
button{margin-top:16px;width:100%;padding:12px;font-size:1.05rem;border:0;
border-radius:8px;background:#1f5fa8;color:#fff;cursor:pointer}
.aviso{background:#fff4e5;border-left:4px solid #e08a00;padding:12px;margin-bottom:16px}
.situacao{font-size:1.5rem;font-weight:700;margin:4px 0 16px}
dl{display:grid;grid-template-columns:auto 1fr;gap:6px 12px;margin:0}
dt{color:#5a6372}dd{margin:0}.rodape{color:#5a6372;font-size:.85rem;margin-top:20px}
"""


def _pagina(portal: Portal, corpo: str) -> bytes:
    titulo = "Acompanhe o seu pedido"
    sub = html.escape(portal.serventia) if portal.serventia else ""
    contato = (f'<p class="rodape">{html.escape(portal.contato)}</p>'
               if portal.contato else "")
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{titulo}</title><style>{ESTILO}</style></head>
<body><main><h1>{titulo}</h1><p class="sub">{sub}</p>{corpo}{contato}
<p class="rodape">Esta página mostra só a situação do pedido. Os dados pessoais
ficam no cartório.</p></main></body></html>""".encode("utf-8")


def _formulario(portal: Portal, aviso: str = "", numero: str = "") -> bytes:
    caixa = f'<div class="aviso">{html.escape(aviso)}</div>' if aviso else ""
    return _pagina(portal, f"""{caixa}<form class="cartao" method="post"
action="{portal.prefixo}/consultar" autocomplete="off">
<label for="numero">Número do protocolo</label>
<input id="numero" name="numero" inputmode="decimal" maxlength="20"
 placeholder="2026.10.57" value="{html.escape(numero)}" required>
<label for="codigo">Código de acompanhamento</label>
<input id="codigo" name="codigo" maxlength="12" placeholder="ABCD-EFGH"
 autocapitalize="characters" spellcheck="false" required>
<button type="submit">Consultar</button>
<p class="rodape">O número e o código estão no recibo e no protocolo de recepção.</p>
</form>""")


def _data(valor) -> str:
    try:
        texto = str(valor or "")
        d = datetime.fromisoformat(texto.replace(" ", "T"))
        return d.strftime("%d/%m/%Y %H:%M") if "T" in texto or " " in texto \
            else d.strftime("%d/%m/%Y")
    except ValueError:
        return "—"


def codigo_mascarado(codigo) -> str:
    """O código como sai no comprovante: só os dois últimos caracteres. O
    código inteiro é a senha da consulta, e o PDF baixado circula."""
    c = normalizar_codigo(codigo)
    fim = c[-2:] if len(c) == TAMANHO_DO_CODIGO and all(x in ALFABETO for x in c) else "••"
    return "••••-••" + fim


def _pronto(r: dict) -> bool:
    if r.get("pronto") is not None:
        return bool(r["pronto"])
    return str(r.get("situacao") or "") == "pronto para retirar"


def _linhas_do_comprovante(portal: Portal, r: dict, codigo: str) -> list[tuple[int, bool, str]]:
    """(corpo, negrito, texto) de cada linha. A LISTA É FECHADA: só os campos do
    retrato e a configuração da página — nada de fora entra no PDF."""
    linhas: list[tuple[int, bool, str]] = [(15, True, "COMPROVANTE DE ACOMPANHAMENTO")]
    if portal.serventia:
        linhas.append((11, False, portal.serventia))
    linhas.append((10, False, ""))
    situacao = str(r.get("situacao") or "")
    desde = _data(r["atualizado_em"]) if r.get("atualizado_em") else ""
    campos = [
        ("Protocolo", r["numero"]),
        ("Código de acompanhamento", f"{codigo_mascarado(codigo)} (só os dois últimos "
                                     "caracteres: o código inteiro é a senha da consulta)"),
        ("Data de entrada", _data(r["entrada"]) if r.get("entrada") else "não informada"),
        ("Atribuição", r.get("atribuicao") or "—"),
        ("Serviço pedido", r.get("servico") or "conforme o protocolo no cartório"),
        ("Situação atual", situacao + (f" (última movimentação em {desde})" if desde else "")),
        ("Prazo previsto", _data(r["previsao"]) if r.get("previsao") else "não informado"),
        ("Pronto para retirar", "Sim" if _pronto(r) else "Ainda não"),
    ]
    for rotulo, valor in campos:
        linhas.append((10, False, f"{rotulo}: {valor}"))
    linhas.append((10, False, ""))
    linhas.append((10, True, "Exigências pendentes (o que falta o cliente trazer):"))
    exigencias = r.get("exigencias") or []
    if exigencias:
        linhas += [(10, False, f"{i}. {e}") for i, e in enumerate(exigencias, 1)]
    elif situacao == "aguardando documento/exigência":
        linhas.append((10, False, "Há exigência pendente — procure o cartório para saber o "
                                  "que falta."))
    else:
        linhas.append((10, False, "Nenhuma."))
    linhas.append((10, False, ""))
    linhas.append((10, False, "Contato da serventia: "
                   + (portal.contato or "procure o cartório pessoalmente.")))
    linhas.append((10, False, ""))
    linhas.append((8, False, "Emitido em " + datetime.now().strftime("%d/%m/%Y %H:%M")
                   + " pelo portal do cliente. Este comprovante não é recibo nem certidão "
                   "e não leva dados pessoais nem valores; os dados completos ficam no "
                   "cartório."))
    return linhas


def _quebrar(texto: str, largura: int) -> list[str]:
    palavras, saida, atual = texto.split(" "), [], ""
    for p in palavras:
        while len(p) > largura:
            if atual:
                saida.append(atual)
                atual = ""
            saida.append(p[:largura])
            p = p[largura:]
        if atual and len(atual) + 1 + len(p) > largura:
            saida.append(atual)
            atual = p
        else:
            atual = f"{atual} {p}" if atual else p
    saida.append(atual)
    return saida


def _pdf_texto(texto: str) -> bytes:
    bruto = texto.encode("cp1252", "replace")
    return bruto.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def comprovante_pdf(portal: Portal, r: dict, codigo: str) -> bytes:
    """O comprovante de acompanhamento em PDF, desenhado aqui, só com a
    biblioteca padrão (A4, Helvetica, WinAnsi). O texto vai SEM compressão —
    é o que deixa o teste ler o PDF e provar o que ele não leva."""
    largura_pagina, altura_pagina, margem = 595, 842, 50
    paginas: list[list[bytes]] = [[]]
    y = altura_pagina - margem
    for corpo, negrito, texto in _linhas_do_comprovante(portal, r, codigo):
        por_linha = max(20, int((largura_pagina - 2 * margem) / (corpo * 0.52)))
        for pedaco in (_quebrar(texto, por_linha) if texto else [""]):
            altura = corpo * 1.45
            if y - altura < margem:
                paginas.append([])
                y = altura_pagina - margem
            y -= altura
            if pedaco:
                fonte = b"/F2" if negrito else b"/F1"
                paginas[-1].append(b"BT " + fonte + b" %d Tf %d %d Td (" % (corpo, margem, int(y))
                                   + _pdf_texto(pedaco) + b") Tj ET")
    objetos: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",                                                    # as páginas, abaixo
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        b"/Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
        b"/Encoding /WinAnsiEncoding >>",
    ]
    filhos = []
    for conteudo in paginas:
        fluxo = b"\n".join(conteudo)
        objetos.append(b"<< /Length %d >>\nstream\n" % len(fluxo) + fluxo + b"\nendstream")
        n_conteudo = len(objetos)
        objetos.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
                       b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                       b"/Contents %d 0 R >>" % (largura_pagina, altura_pagina, n_conteudo))
        filhos.append(len(objetos))
    objetos[1] = (b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % f for f in filhos)
                  + b"] /Count %d >>" % len(filhos))
    saida = bytearray(b"%PDF-1.4\n")
    posicoes = []
    for i, obj in enumerate(objetos, 1):
        posicoes.append(len(saida))
        saida += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(saida)
    saida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    for p in posicoes:
        saida += b"%010d 00000 n \n" % p
    saida += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
              % (len(objetos) + 1, xref))
    return bytes(saida)


def _resultado(portal: Portal, r: dict, codigo: str) -> bytes:
    linhas = [("Protocolo", r["numero"])]
    if r.get("entrada"):
        linhas.append(("Entrada", _data(r["entrada"])))
    if r.get("atribuicao"):
        linhas.append(("Atribuição", r["atribuicao"]))
    if r.get("servico"):
        linhas.append(("Serviço", r["servico"]))
    if r.get("previsao"):
        linhas.append(("Previsão", _data(r["previsao"])))
    if r.get("atualizado_em"):
        linhas.append(("Última movimentação", _data(r["atualizado_em"])))
    linhas.append(("Pronto para retirar", "Sim" if _pronto(r) else "Ainda não"))
    for i, e in enumerate(r.get("exigencias") or [], 1):
        linhas.append((f"Exigência {i}", e))
    dl = "".join(f"<dt>{html.escape(a)}</dt><dd>{html.escape(str(b))}</dd>"
                 for a, b in linhas)
    comprovante = f"""<form method="post" action="{portal.prefixo}/comprovante">
<input type="hidden" name="numero" value="{html.escape(r['numero'])}">
<input type="hidden" name="codigo" value="{html.escape(normalizar_codigo(codigo))}">
<button type="submit">Baixar o comprovante de acompanhamento (PDF)</button></form>"""
    recibos = "".join(f"""<form method="post" action="{portal.prefixo}/recibo">
<input type="hidden" name="numero" value="{html.escape(r['numero'])}">
<input type="hidden" name="codigo" value="{html.escape(normalizar_codigo(codigo))}">
<input type="hidden" name="nome" value="{html.escape(nome)}">
<button type="submit">Baixar o recibo ({html.escape(nome)})</button></form>"""
                      for nome in r.get("recibos") or [])
    return _pagina(portal, f"""<div class="cartao">
<div>Situação do pedido</div><div class="situacao">{html.escape(r['situacao'])}</div>
<dl>{dl}</dl>{comprovante}{recibos}</div>
<p class="rodape"><a href="{portal.prefixo}/">Consultar outro protocolo</a></p>""")


# ----------------------------------------------------------- o HTTP

class Atendente(BaseHTTPRequestHandler):
    portal: Portal = None  # type: ignore[assignment]
    server_version = "portal"
    sys_version = ""

    # Sem log de corpo nem de cabeçalho: o log do Apache já diz quem veio.
    def log_message(self, formato, *args):  # noqa: D401
        sys.stderr.write("%s %s\n" % (self.log_date_time_string(), formato % args))

    def _ip(self) -> str:
        par = self.client_address[0]
        encaminhado = self.headers.get("X-Forwarded-For", "")
        if par in ("127.0.0.1", "::1") and encaminhado:
            # O Apache ACRESCENTA o IP de quem chegou no fim; o começo da lista
            # vem de quem chamou e se falsifica.
            return encaminhado.split(",")[-1].strip()[:64]
        return par

    def _cabecalhos(self, tipo: str, tamanho: int, status: int = 200,
                    extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(tamanho))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; "
                         "form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        if self.portal.exigir_https:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _html(self, corpo: bytes, status: int = 200) -> None:
        self._cabecalhos("text/html; charset=utf-8", len(corpo), status)
        self.wfile.write(corpo)

    def _json(self, dados: dict, status: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self._cabecalhos("application/json; charset=utf-8", len(corpo), status)
        self.wfile.write(corpo)

    def _https_ok(self) -> bool:
        if not self.portal.exigir_https:
            return True
        if self.headers.get("X-Forwarded-Proto", "").lower() == "https":
            return True
        self._html(b"Use https.", 403)
        return False

    def _caminho(self) -> str | None:
        alvo = self.path.split("?", 1)[0]
        prefixo = self.portal.prefixo
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
        esperado = "Bearer " + self.portal.token
        return hmac.compare_digest(dado.encode("utf-8"), esperado.encode("utf-8"))

    def do_GET(self):  # noqa: N802
        if not self._https_ok():
            return
        caminho = self._caminho()
        if caminho in ("/", ""):
            return self._html(_formulario(self.portal))
        if caminho == "/api/saude":
            if not self._autorizado():
                return self._json({"ok": False}, 401)
            return self._json({"ok": True, "retratos": self.portal.contar()})
        return self._html(b"Nada aqui.", 404)

    def do_POST(self):  # noqa: N802
        if not self._https_ok():
            return
        caminho = self._caminho()
        if caminho == "/api/retratos":
            if not self._autorizado():
                return self._json({"ok": False, "motivo": "token"}, 401)
            corpo = self._ler(CORPO_MAXIMO_API)
            if corpo is None:
                return self._json({"ok": False, "motivo": "corpo grande demais"}, 413)
            try:
                return self._json(self.portal.receber(corpo))
            except Recusa as erro:
                return self._json({"ok": False, "motivo": str(erro)}, 400)
        if caminho in ("/consultar", "/recibo", "/comprovante"):
            corpo = self._ler(CORPO_MAXIMO_FORM)
            if corpo is None:
                return self._html(_formulario(self.portal, MENSAGEM_NAO_CONFERE), 400)
            campos = {k: v[0] for k, v in parse_qs(
                corpo.decode("utf-8", "replace"), max_num_fields=5).items()}
            numero = campos.get("numero", "")
            estado, retrato = self.portal.consultar(numero, campos.get("codigo", ""),
                                                    self._ip())
            if estado == "muitas":
                return self._html(_formulario(self.portal, MENSAGEM_MUITAS), 429)
            if estado != "ok":
                return self._html(_formulario(self.portal, MENSAGEM_NAO_CONFERE,
                                              numero=numero[:20]))
            if caminho == "/consultar":
                return self._html(_resultado(self.portal, retrato, campos.get("codigo")))
            if caminho == "/comprovante":
                pdf = comprovante_pdf(self.portal, retrato, campos.get("codigo", ""))
                nome = "comprovante-" + retrato["numero"].replace(".", "-") + ".pdf"
                self._cabecalhos("application/pdf", len(pdf), extra={
                    "Content-Disposition": f'attachment; filename="{nome}"'})
                self.wfile.write(pdf)
                return None
            nome = campos.get("nome", "")
            pdf = self.portal.recibo(retrato["numero"], nome) \
                if nome in (retrato.get("recibos") or []) else None
            if not pdf:
                return self._html(b"Recibo n\xc3\xa3o encontrado.", 404)
            self._cabecalhos("application/pdf", len(pdf), extra={
                "Content-Disposition": f'attachment; filename="{nome}"'})
            self.wfile.write(pdf)
            return None
        return self._html(b"Nada aqui.", 404)


def servir(portal: Portal, endereco: str = "127.0.0.1", porta: int = 8781) -> ThreadingHTTPServer:
    classe = type("AtendenteDoPortal", (Atendente,), {"portal": portal})
    return ThreadingHTTPServer((endereco, porta), classe)


def _token_do_ambiente() -> str:
    arquivo = os.environ.get("PORTAL_TOKEN_ARQUIVO", "/etc/cartorio-portal/token")
    try:
        return open(arquivo, encoding="utf-8").read().strip()
    except OSError:
        raise SystemExit(f"Não li o token em {arquivo}. Ver LEIA-ME.md.")


def main() -> int:
    portal = Portal(
        os.environ.get("PORTAL_BANCO", "/var/lib/cartorio-portal/portal.sqlite3"),
        _token_do_ambiente(),
        prefixo=os.environ.get("PORTAL_PREFIXO", "/portal"),
        exigir_https=os.environ.get("PORTAL_EXIGIR_HTTPS", "1") != "0",
        serventia=os.environ.get("PORTAL_SERVENTIA", ""),
        contato=os.environ.get("PORTAL_CONTATO", ""))
    endereco = os.environ.get("PORTAL_ENDERECO", "127.0.0.1")
    porta = int(os.environ.get("PORTAL_PORTA", "8781"))
    servidor = servir(portal, endereco, porta)
    sys.stderr.write(f"portal do cliente em http://{endereco}:{porta}{portal.prefixo}/\n")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
