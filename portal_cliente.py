"""O PORTAL DO CLIENTE — o servidor EMPURRA para a VPS o retrato mínimo de cada
protocolo com código de acompanhamento.

    «portal do cliente para acompanhar o pedido e baixar o recibo», no mesmo
     VPS do WhatsApp («já temos um VPS»), com «código no recibo».
     O oficial, 26/10/2026.

A REGRA DE ARQUITETURA QUE ESTE MÓDULO NÃO FURA
    O servidor da serventia NÃO fica na internet (`wa_schema.py`,
    `docs/SEGURANCA_REDE.md`). É o desenho da caixa-postal do WhatsApp
    (`wa_puxar.py`) pelo outro lado: lá a VPS guarda o que chega e o servidor
    PUXA; aqui o servidor EMPURRA o que o cliente pode ver. Nos dois, a conexão
    é sempre de SAÍDA, em HTTPS, com um token que mora no cofre (`portal.cred`),
    e nunca no banco. A VPS não alcança o servidor, e não guarda nada que o
    servidor não lhe mandou.

O QUE SOBE, E O QUE NÃO SOBE
    Sobe, por protocolo: o número, o HASH do código (nunca o código), a
    situação em linguagem simples, a previsão, a última movimentação, a
    atribuição — o mesmo dicionário de `acompanhamento_cliente.retrato` — e o
    recibo em PDF quando houver. NÃO sobe: nome, CPF, telefone, valor por ato,
    assunto, teor. O PROTESTO não sobe nada (sigilo; não ganha código). E o
    recibo do REGISTRO CIVIL não sobe (`SEM_RECIBO_NO_PORTAL`): a
    discriminação diria qual ato foi pedido — uma averbação de reconhecimento de
    paternidade, por exemplo —, e isso não é dado para ficar numa máquina fora
    da casa. É decisão para o oficial confirmar (ver o PR).

    O RECIBO EM PDF LEVA O QUE O PAPEL LEVA: o nome do pagador, o documento
    mascarado e os valores. É o papel que o próprio cliente já tem, e só sai
    para quem digita número e código — mas é dado pessoal numa VPS, e por isso
    a caixa de configuração diz isso com todas as letras.

QUANDO SOBE, E QUANDO SAI DE LÁ
    Sobe só o que mudou: a impressão digital do retrato (`portal_marca`) fica
    gravada, e o mesmo retrato não sobe de novo. O protocolo encerrado fica no
    portal `DIAS_DEPOIS_DE_ENCERRADO` dias e então a VPS recebe a ordem de
    apagá-lo; o aberto, `DIAS_DO_ABERTO` dias desde a abertura. A VPS também
    apaga sozinha o que passou de `expira_em`, para o dia em que o servidor
    parar de mandar.

QUEM CHAMA
    O botão «Enviar agora» da tela do portal (`caixa_web`) e a linha de comando
    deste módulo, para a tarefa do Agendador (a cada 15 minutos, instalada pela
    TI — `vps/portal/LEIA-ME.md`). Nada sobe com o interruptor
    desligado, e ele nasce DESLIGADO: a VPS ainda não está instalada.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import sys
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

import acompanhamento_cliente as ACOMP
from bd_nativo import banco

LOG = logging.getLogger("cartorio.portal")

CHAVE_URL = "portal_cliente_url"
CHAVE_ENVIO = "portal_cliente_envio"
CHAVE_ULTIMO = "portal_cliente_ultimo_envio"
CHAVE_TOKEN = "token_da_vps"
LIGADO = "LIGADO"
DESLIGADO = "DESLIGADO"

#: Quanto tempo o protocolo fica consultável depois de encerrado (entregue ou
#: cancelado) — o tempo de o cliente baixar o recibo de novo, e não mais.
DIAS_DEPOIS_DE_ENCERRADO = 90
#: O teto do protocolo que nunca se encerra (a casa tem milhares em PAGO que
#: ninguém fechou): um ano depois da abertura ele sai do portal.
DIAS_DO_ABERTO = 365
#: Retratos por chamada. Com PDF de recibo, cada um pesa dezenas de KB.
LOTE = 20
TIMEOUT = 30
#: A marca de quem já saiu do portal: não se recalcula a cada rodada.
REMOVIDO = "REMOVIDO"
#: Atribuições em que o protocolo sobe sem o recibo. Ver o cabeçalho.
SEM_RECIBO_NO_PORTAL = frozenset({"RCPN"})
#: Recibos por protocolo que sobem — o atendimento normal tem um.
RECIBOS_POR_PROTOCOLO = 5
CAMINHO_DA_API = "/api/retratos"


class PortalError(ValueError):
    """Erro de regra, com a frase pronta para o balcão."""


# ============================================================ configuração


def _setting(con, chave: str, padrao: str = "") -> str:
    linha = banco(con).um("SELECT value FROM settings WHERE key = %s", (chave,))
    return str(linha["value"]) if linha and linha["value"] is not None else padrao


def _gravar_setting(con, chave: str, valor: str) -> None:
    banco(con).escrever(
        """INSERT INTO settings(key, value) VALUES (%s, %s)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
        (chave, str(valor)))


def _token(con) -> str:
    import cofre_cred as COFRE
    return COFRE.ler_segredo(con, COFRE.PORTAL, CHAVE_TOKEN)


def endereco_valido(url: Any) -> str:
    """O endereço público do portal, conferido. Só calcula.

    HTTPS sempre: o token vai no cabeçalho, e em `http://` qualquer máquina no
    caminho o leria — a regra que `wa_puxar` aprendeu em 22/10/2026 (M11).
    """
    texto = str(url or "").strip().rstrip("/")
    if not texto:
        return ""
    partes = urlsplit(texto)
    if partes.scheme != "https" or not partes.netloc:
        raise PortalError("O endereço do portal tem de começar com https:// — o "
                          "token iria em claro pela rede.")
    if partes.query or partes.fragment or "@" in partes.netloc:
        raise PortalError("O endereço do portal não leva «?», «#» nem usuário: "
                          "escreva só https://servidor/caminho.")
    return texto


def configuracao(con) -> dict:
    """O que a tela mostra. SÓ LÊ — nunca devolve o token."""
    try:
        ultimo = json.loads(_setting(con, CHAVE_ULTIMO) or "{}")
    except ValueError:
        ultimo = {}
    bd = banco(con)
    return {
        "url": _setting(con, CHAVE_URL),
        "ligado": _setting(con, CHAVE_ENVIO, DESLIGADO).upper() == LIGADO,
        "tem_token": bool(_token_ou_vazio(con)),
        "ultimo": ultimo,
        "com_codigo": int(bd.valor(
            "SELECT count(*) FROM cx_protocolos WHERE acompanhamento_hash IS NOT NULL")
            or 0),
        "no_portal": int(bd.valor(
            """SELECT count(*) FROM cx_protocolos
                WHERE portal_marca IS NOT NULL AND portal_marca <> %s""",
            (REMOVIDO,)) or 0),
    }


def _token_ou_vazio(con) -> str:
    try:
        return _token(con)
    except Exception:                                   # noqa: BLE001
        return ""


def gravar_configuracao(con, *, url: Any, ligado: bool,
                        token: str | None = None,
                        apagar_token: bool = False) -> None:
    """Grava o endereço e o interruptor no banco, e o token no cofre. ESCREVE.

    Token vazio não mexe no que está gravado (a tela não mostra o token, e o
    campo em branco quer dizer «não alterar»).
    """
    import cofre_cred as COFRE
    endereco = endereco_valido(url)
    if ligado and not endereco:
        raise PortalError("Para ligar o envio, informe o endereço do portal.")
    _gravar_setting(con, CHAVE_URL, endereco)
    _gravar_setting(con, CHAVE_ENVIO, LIGADO if ligado else DESLIGADO)
    if apagar_token:
        COFRE.gravar_segredo(con, COFRE.PORTAL, CHAVE_TOKEN, "")
    elif str(token or "").strip():
        limpo = str(token).strip()
        if len(limpo) < 32:
            raise PortalError("O token da VPS tem de ter pelo menos 32 caracteres "
                              "(é a senha da porta da VPS). Gere um longo e "
                              "aleatório, e grave o mesmo na VPS.")
        COFRE.gravar_segredo(con, COFRE.PORTAL, CHAVE_TOKEN, limpo)


# ============================================================ o retrato


def _dia(valor: Any) -> date | None:
    try:
        return date.fromisoformat(str(valor or "")[:10])
    except ValueError:
        return None


def expira_em(protocolo: Mapping, hoje: date) -> date:
    """Até quando o protocolo fica no portal. Só calcula."""
    if str(protocolo.get("situacao") or "").upper() in ("ENTREGUE", "CANCELADO"):
        base = _dia(protocolo.get("data_finalizacao")) or hoje
        return base + timedelta(days=DIAS_DEPOIS_DE_ENCERRADO)
    base = _dia(protocolo.get("data_abertura")) or hoje
    return base + timedelta(days=DIAS_DO_ABERTO)


def _recibos(con, protocolo: Mapping) -> list[dict]:
    if str(protocolo.get("atribuicao") or "").upper() in SEM_RECIBO_NO_PORTAL:
        return []
    return [dict(r) for r in banco(con).ler(
        """SELECT * FROM cx_recibos
            WHERE protocolo_id = %s AND coalesce(cancelado, 0) = 0
            ORDER BY id DESC LIMIT %s""",
        (int(protocolo["id"]), RECIBOS_POR_PROTOCOLO))]


def retrato_para_a_vps(con, protocolo: Mapping, *, hoje: date) -> dict:
    """O pacote de um protocolo, SEM os PDFs — é sobre ele que a marca se tira.
    Só lê."""
    base = ACOMP.retrato(con, protocolo, hoje=hoje.isoformat())
    return {
        **base,
        "codigo_hash": protocolo["acompanhamento_hash"],
        "expira_em": expira_em(protocolo, hoje).isoformat(),
        "recibos": [{"nome": f"recibo-{r['numero']}-{r['ano']}.pdf",
                     "conferencia": str(r.get("hash_recibo") or "")[:16]}
                    for r in _recibos(con, protocolo)],
    }


def marca(pacote: Mapping) -> str:
    """A impressão digital do retrato. Só calcula."""
    texto = json.dumps(pacote, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def a_enviar(con, *, hoje: date) -> list[dict]:
    """O que mudou desde o último envio. SÓ LÊ.

    Cada item: `{"id", "numero", "pacote", "marca", "remover"}`. Remover é a
    ordem de a VPS apagar: o protocolo passou da data, ou deixou de ter
    acompanhamento (virou protesto, por exemplo).
    """
    saida = []
    for linha in banco(con).ler(
            """SELECT * FROM cx_protocolos
                WHERE acompanhamento_hash IS NOT NULL
                  AND coalesce(portal_marca, '') <> %s
                ORDER BY id""", (REMOVIDO,)):
        p = dict(linha)
        if not ACOMP.elegivel(p) or expira_em(p, hoje) < hoje:
            # Já subiu: a VPS recebe a ordem de apagar. Nunca subiu: só se
            # marca, sem rede (`pacote` None).
            saida.append({"id": int(p["id"]), "numero": p["numero"],
                          "pacote": ({"numero": p["numero"], "remover": True}
                                     if p.get("portal_marca") else None),
                          "marca": REMOVIDO, "remover": True})
            continue
        pacote = retrato_para_a_vps(con, p, hoje=hoje)
        m = marca(pacote)
        if m != p.get("portal_marca"):
            saida.append({"id": int(p["id"]), "numero": p["numero"],
                          "pacote": pacote, "marca": m, "remover": False})
    return saida


# ============================================================ o PDF do recibo


def pdf_do_recibo(con, recibo: Mapping, settings: Mapping) -> bytes:
    """O recibo em PDF, como o papel sai — SEM o código de acompanhamento.

    O código não vai no PDF que sobe: na VPS ele estaria em claro, que é
    justamente o que o hash existe para evitar. Levanta `PdfError` quando o
    LibreOffice não converte; quem chama decide o que fazer.
    """
    import caixa_web
    import impressao_pdf
    from ri_odt import gerar_odt, html_para_odf
    data = _dia(recibo.get("data_emissao"))
    html = caixa_web.html_do_recibo(
        con, recibo, settings=settings,
        emitido_por="Segunda via eletrônica, para consulta — sem assinatura",
        funcao="", data_extenso=data.strftime("%d/%m/%Y") if data else "",
        agora=datetime.now().strftime("%d/%m/%Y %H:%M"), acompanhamento=None)
    odt = gerar_odt(html_para_odf(html),
                    titulo=f"Recibo {recibo['numero']}/{recibo['ano']}")
    return impressao_pdf.pdf_de_odt(
        odt, nome=f"recibo-{recibo['numero']}-{recibo['ano']}",
        get_setting=lambda chave, padrao="": settings.get(chave, padrao))


def _com_os_pdfs(con, item: dict, atribuicao: Any, settings: Mapping,
                 gerar_pdf: Callable) -> tuple[dict, bool]:
    """O pacote com os PDFs dentro, e se ficou completo."""
    pacote = dict(item["pacote"])
    completo = True
    linhas = {f"recibo-{r['numero']}-{r['ano']}.pdf": r
              for r in _recibos(con, {"id": item["id"], "atribuicao": atribuicao})}
    recibos = []
    for r in pacote.get("recibos") or []:
        linha = linhas.get(r["nome"])
        try:
            conteudo = gerar_pdf(con, linha, settings) if linha else None
        except Exception as erro:                       # noqa: BLE001
            LOG.warning("recibo %s não virou PDF para o portal: %s", r["nome"], erro)
            conteudo = None
        if not conteudo:
            completo = False
            continue
        recibos.append({**r, "sha256": hashlib.sha256(conteudo).hexdigest(),
                        "pdf": base64.b64encode(conteudo).decode("ascii")})
    pacote["recibos"] = recibos
    return pacote, completo


# ============================================================ o envio


def _http_post(url: str, token: str, corpo: bytes,
               timeout: float = TIMEOUT) -> tuple[int, str]:
    req = urllib.request.Request(url, data=corpo, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read(65536).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return int(e.code), e.read(4096).decode("utf-8", "replace")
    except Exception as e:                              # noqa: BLE001
        return 0, str(e)


def _settings(con) -> dict:
    return {r["key"]: r["value"] for r in banco(con).ler("SELECT key, value FROM settings")}


def enviar(db, *, hoje: date | None = None, http_post: Callable | None = None,
           gerar_pdf: Callable | None = None) -> dict:
    """Empurra para a VPS o que mudou. ESCREVE (as marcas e o resumo).

    `db` tem `connect()` e `transaction()` (o `Database` da casa, ou a porta da
    linha de comando). A REDE FICA FORA DA TRANSAÇÃO: lê-se numa conexão, manda-
    se, e só então se grava a marca, numa transação curta — trinta segundos de
    rede segurando a escrita da casa poriam o balcão inteiro esperando.
    """
    hoje = hoje or date.today()
    post = http_post or _http_post
    gerar = gerar_pdf or pdf_do_recibo
    resumo = {"em": datetime.now().isoformat(timespec="seconds"), "ok": False,
              "enviados": 0, "removidos": 0, "incompletos": 0, "motivo": ""}
    with db.connect() as con:
        cfg_url = _setting(con, CHAVE_URL)
        ligado = _setting(con, CHAVE_ENVIO, DESLIGADO).upper() == LIGADO
        token = _token_ou_vazio(con)
        settings = _settings(con)
        itens = a_enviar(con, hoje=hoje)
        atribuicoes = {int(r["id"]): r["atribuicao"] for r in banco(con).ler(
            "SELECT id, atribuicao FROM cx_protocolos WHERE id = ANY(%s)",
            ([i["id"] for i in itens] or [0],))}
    try:
        url = endereco_valido(cfg_url)
    except PortalError as erro:
        url, resumo["motivo"] = "", str(erro)
    if not ligado:
        resumo["motivo"] = "envio ao portal desligado nas configurações"
    elif not url and not resumo["motivo"]:
        resumo["motivo"] = "endereço do portal em branco"
    elif not token:
        resumo["motivo"] = "token da VPS não gravado"
    if resumo["motivo"]:
        _registrar(db, resumo)
        return resumo

    # O que nunca subiu e já não deve subir: só a marca, sem rede.
    so_marcar = [i for i in itens if i["pacote"] is None]
    if so_marcar:
        _marcar(db, [(i["id"], REMOVIDO) for i in so_marcar])
    fila = [i for i in itens if i["pacote"] is not None]
    for inicio in range(0, len(fila), LOTE):
        lote = fila[inicio:inicio + LOTE]
        pacotes, marcas = [], []
        with db.connect() as con:
            for item in lote:
                if item["remover"]:
                    pacotes.append(item["pacote"])
                    marcas.append((item["id"], REMOVIDO))
                    continue
                pacote, completo = _com_os_pdfs(
                    con, item, atribuicoes.get(item["id"]), settings, gerar)
                pacotes.append(pacote)
                # Incompleto (o LibreOffice não converteu): a marca grava com
                # o sufixo, e a próxima rodada tenta de novo.
                marcas.append((item["id"], item["marca"] if completo
                               else item["marca"] + ":incompleto"))
                resumo["incompletos"] += 0 if completo else 1
        corpo = json.dumps({"retratos": pacotes}, ensure_ascii=False).encode("utf-8")
        status, resposta = post(url + CAMINHO_DA_API, token, corpo)
        if not 200 <= status < 300:
            resumo["motivo"] = f"a VPS respondeu HTTP {status}: {resposta[:200]}"
            _registrar(db, resumo)
            return resumo
        _marcar(db, marcas)
        resumo["removidos"] += sum(1 for _, m in marcas if m == REMOVIDO)
        resumo["enviados"] += sum(1 for _, m in marcas if m != REMOVIDO)
    resumo["ok"] = True
    _registrar(db, resumo)
    return resumo


def _marcar(db, marcas: list[tuple[int, str]]) -> None:
    agora = datetime.now().isoformat(timespec="seconds")
    with db.transaction() as con:
        bd = banco(con)
        for pid, m in marcas:
            bd.escrever("""UPDATE cx_protocolos SET portal_marca = %s,
                                  portal_enviado_em = %s WHERE id = %s""",
                        (m, agora, int(pid)))


def _registrar(db, resumo: dict) -> None:
    with db.transaction() as con:
        _gravar_setting(con, CHAVE_ULTIMO, json.dumps(resumo, ensure_ascii=False))


# ============================================================ linha de comando


class _Porta:
    """O `connect()`/`transaction()` do `Database`, sobre uma conexão só — a do
    Agendador, que roda fora do sistema."""

    def __init__(self, con):
        self._con = con

    @contextmanager
    def connect(self):
        yield self._con

    @contextmanager
    def transaction(self):
        try:
            yield self._con
            self._con.commit()
        except BaseException:
            self._con.rollback()
            raise


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Empurra para a VPS o retrato dos protocolos com código de "
                    "acompanhamento (portal do cliente).")
    p.add_argument("--banco", required=True, help="o banco da casa")
    a = p.parse_args(argv)
    import banco_pg
    # PELA PORTA (`banco_pg.conectar`), como a rodada do gestor: o Agendador
    # roda fora do sistema, e o acesso nativo recusa o sqlite3 cru.
    con = banco_pg.conectar(a.banco, timeout=60)
    try:
        resumo = enviar(_Porta(con))
    finally:
        con.close()
    print(json.dumps(resumo, ensure_ascii=False))
    return 0 if resumo.get("ok") or "desligado" in resumo.get("motivo", "") else 1


if __name__ == "__main__":
    sys.exit(main())
