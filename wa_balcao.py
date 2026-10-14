"""Dominio do Balcao WhatsApp — classificar, rascunhar, gravar entrada, enviar.

A ROTA SO LIGA OS FIOS. O webhook local (teste ou reenvio da caixa-postal)
chama `aplicar_entrada`. A tela le o que ja esta no SQLite.

Envio a Cloud API e so no botao do escrevente. Autoenvio continua desligado.
Nunca logar access_token, app_secret nem caixa_segredo.

Idempotencia: a mesma `meta_id` nao cria segunda mensagem.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Callable
from unicodedata import normalize

import serventia as SERV
import wa_schema as WA
import wa_textos as TEXTOS

DIR_IN = "in"
DIR_OUT = "out"
DIR_RASCUNHO = "rascunho"

_ISO = "%Y-%m-%dT%H:%M:%S"
GRAPH_VER = "v21.0"
TIMEOUT_ENVIO = 8


class EnvioErro(Exception):
    """A Graph recusou ou nao respondeu. Nao inventa envio."""


def agora_iso() -> str:
    return datetime.now().replace(microsecond=0).strftime(_ISO)


def _sem_acento(texto: str) -> str:
    n = normalize("NFD", texto or "")
    return "".join(c for c in n if not (0x300 <= ord(c) <= 0x36F)).lower()


def classificar(texto: str) -> str:
    """Etiqueta por palavra-chave em portugues. Sem modelo pago."""
    t = _sem_acento(texto)
    if not t.strip():
        return "outros"
    if any(p in t for p in ("protesto", "titulo", "edital")):
        return "protesto"
    if any(p in t for p in (
        "certidao", "certidoes", "nascimento", "casamento", "obito",
    )):
        return "certidao"
    if any(p in t for p in ("firma", "reconhecer", "reconhecimento")):
        return "firma"
    if "preciso levar" in t or "documentos" in t or "documento" in t:
        return "documentos"
    if any(p in t for p in ("horario", "abre", "fecha", "expediente", "funcionamento")):
        return "horario"
    if any(p in t for p in ("endereco", "onde fica", "onde voc", "localizacao")):
        return "endereco"
    return "outros"


def rascunhar(texto: str, etiqueta: str | None, serventia: Any = None) -> str:
    """Rascunho curto no tom de cartorio. Nao envia. Nao inventa horario."""
    et = (etiqueta or "outros").strip().lower() or "outros"
    if et not in TEXTOS.POR_ETIQUETA:
        et = "outros"
    fn = TEXTOS.POR_ETIQUETA[et]
    return fn(serventia)


def ler_config(con: sqlite3.Connection, chave: str) -> str:
    linha = con.execute(
        "SELECT valor FROM wa_config WHERE chave=?", (chave,)
    ).fetchone()
    if not linha:
        return ""
    if isinstance(linha, sqlite3.Row):
        return (linha["valor"] or "").strip()
    return (linha[0] or "").strip()


def gravar_config(con: sqlite3.Connection, chave: str, valor: str) -> None:
    con.execute(
        "INSERT INTO wa_config(chave, valor) VALUES (?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
        (chave, valor or ""),
    )


def verify_token_salvo(con: sqlite3.Connection) -> str:
    """O token que o GET do webhook confere. Vazio vira o de desenvolvimento."""
    t = ler_config(con, WA.CHAVE_VERIFY)
    return t or WA.VERIFY_TOKEN_DEV


def mascarar_segredo(valor: str) -> str:
    """Mostra so os ultimos 4. Nunca o token inteiro."""
    t = (valor or "").strip()
    if not t:
        return ""
    if len(t) <= 4:
        return "****"
    return "••••" + t[-4:]


def pode_enviar_meta(con: sqlite3.Connection) -> bool:
    return bool(ler_config(con, WA.CHAVE_TOKEN) and ler_config(con, WA.CHAVE_PHONE))


def config_para_tela(con: sqlite3.Connection) -> dict:
    token = ler_config(con, WA.CHAVE_TOKEN)
    secret = ler_config(con, WA.CHAVE_APP_SECRET)
    caixa_seg = ler_config(con, WA.CHAVE_CAIXA_SEGREDO)
    return {
        "verify_token": ler_config(con, WA.CHAVE_VERIFY),
        "phone_number_id": ler_config(con, WA.CHAVE_PHONE),
        "access_token_mascarado": mascarar_segredo(token),
        "tem_access_token": bool(token),
        "app_secret_mascarado": mascarar_segredo(secret),
        "tem_app_secret": bool(secret),
        "caixa_url": ler_config(con, WA.CHAVE_CAIXA_URL),
        "caixa_segredo_mascarado": mascarar_segredo(caixa_seg),
        "tem_caixa_segredo": bool(caixa_seg),
        "pode_enviar": pode_enviar_meta(con),
        "caixa_url_documentada": WA.CAIXA_URL_DOCUMENTADA,
        "webhook_publico": WA.WEBHOOK_PUBLICO_DOCUMENTADO,
    }


def gravar_tela_config(con: sqlite3.Connection, form: dict) -> None:
    """Grava o que a tela mandou. Campo de segredo vazio = nao altera."""
    gravar_config(con, WA.CHAVE_VERIFY,
                  (form.get("verify_token") or "").strip())
    gravar_config(con, WA.CHAVE_PHONE,
                  (form.get("phone_number_id") or "").strip())
    token = (form.get("access_token") or "").strip()
    if token:
        gravar_config(con, WA.CHAVE_TOKEN, token)
    secret = (form.get("app_secret") or "").strip()
    if secret:
        gravar_config(con, WA.CHAVE_APP_SECRET, secret)
    gravar_config(con, WA.CHAVE_CAIXA_URL,
                  (form.get("caixa_url") or "").strip())
    caixa_seg = (form.get("caixa_segredo") or "").strip()
    if caixa_seg:
        gravar_config(con, WA.CHAVE_CAIXA_SEGREDO, caixa_seg)


def assinatura_hub(app_secret: str, corpo: bytes, header: str) -> bool:
    """X-Hub-Signature-256 da Meta: sha256=<hex do HMAC do corpo cru>."""
    if not (app_secret or "").strip() or corpo is None:
        return False
    h = (header or "").strip()
    prefixo = "sha256="
    if not h.lower().startswith(prefixo):
        return False
    recebido = h.split("=", 1)[1].strip()
    esperado = hmac.new(
        app_secret.encode("utf-8"), corpo, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(esperado.lower(), recebido.lower())
def post_de_teste_liberado(con: sqlite3.Connection, header_teste: str = "") -> bool:
    """POST local de desenvolvimento: header X-Wa-Test: 1 e sem app_secret.

    Com app_secret gravado, so entra quem trouxer HMAC valido (reenvio da
    caixa-postal no host XMPP, ou teste que assina o corpo). O tunel no
    SERVIDOR do Cartorio Gestao e proibido: este endpoint nao deve ser
    publico.
    """
    if ler_config(con, WA.CHAVE_APP_SECRET):
        return False
    return str(header_teste or "").strip() == "1"


def post_permitido(con: sqlite3.Connection, header_teste: str = "",
                   corpo: bytes = b"", signature_header: str = "") -> bool:
    """Este POST entra na fila?

    - Com `app_secret` gravado: exige HMAC SHA256 `X-Hub-Signature-256` valido.
    - Sem secret: so `X-Wa-Test: 1`. Nao abre o webhook para o mundo.
    Producao inbound nao chega direto neste Flask: chega na caixa-postal
    (host XMPP) e o Cartorio Gestao puxa.
    """
    secret = ler_config(con, WA.CHAVE_APP_SECRET)
    if secret:
        return assinatura_hub(secret, corpo or b"", signature_header)
    return post_de_teste_liberado(con, header_teste)


def _texto_da_mensagem(msg: dict) -> str:
    if not isinstance(msg, dict):
        return ""
    texto = msg.get("text")
    if isinstance(texto, dict):
        return str(texto.get("body") or "").strip()
    if isinstance(texto, str):
        return texto.strip()
    for k in ("body", "texto", "message"):
        if msg.get(k):
            return str(msg.get(k)).strip()
    return ""


def _mensagens_do_payload(payload: Any) -> list[tuple[dict, dict]]:
    """Aceita o envelope da Meta e um JSON curto de teste."""
    saida: list[tuple[dict, dict]] = []
    if not isinstance(payload, dict):
        return saida
    if payload.get("entry"):
        for entry in payload.get("entry") or []:
            if not isinstance(entry, dict):
                continue
            for change in entry.get("changes") or []:
                if not isinstance(change, dict):
                    continue
                value = change.get("value") or {}
                nomes = {}
                for c in value.get("contacts") or []:
                    if not isinstance(c, dict):
                        continue
                    nomes[str(c.get("wa_id") or "")] = (
                        (c.get("profile") or {}).get("name") or ""
                    )
                for m in value.get("messages") or []:
                    if isinstance(m, dict):
                        saida.append((m, nomes))
        return saida
    if payload.get("messages"):
        for m in payload.get("messages") or []:
            if isinstance(m, dict):
                saida.append((m, {}))
        return saida
    if payload.get("from") or payload.get("wa_id") or payload.get("text"):
        saida.append((payload, {}))
    return saida


def _ja_tem_meta(con: sqlite3.Connection, meta_id: str) -> bool:
    if not meta_id:
        return False
    linha = con.execute(
        "SELECT id FROM wa_mensagem WHERE meta_id=?", (meta_id,)
    ).fetchone()
    return bool(linha)


def _conversa_por_wa(con: sqlite3.Connection, wa_id: str) -> sqlite3.Row | None:
    return con.execute(
        "SELECT * FROM wa_conversa WHERE wa_id=?", (wa_id,)
    ).fetchone()


def aplicar_entrada(con: sqlite3.Connection, payload_meta: Any,
                    serventia: Any = None, agora: str | None = None) -> dict:
    """Grava conversa+mensagem, classifica e rascunha. Idempotente por meta_id.

    Nao envia nada a Meta. auto_ok permanece 0.
    """
    quando = agora or agora_iso()
    if serventia is None:
        serventia = SERV.PADRAO
    criadas = 0
    repetidas = 0
    ids: list[int] = []
    for msg, nomes in _mensagens_do_payload(payload_meta):
        meta_id = str(msg.get("id") or msg.get("meta_id") or "").strip()
        if meta_id and _ja_tem_meta(con, meta_id):
            repetidas += 1
            continue
        wa_id = str(msg.get("from") or msg.get("wa_id") or "").strip()
        if not wa_id:
            continue
        texto = _texto_da_mensagem(msg)
        nome = str(nomes.get(wa_id) or msg.get("nome") or "").strip()
        etiqueta = classificar(texto)
        rascunho = rascunhar(texto, etiqueta, serventia)
        bruto = json.dumps(msg, ensure_ascii=False)
        existente = _conversa_por_wa(con, wa_id)
        if existente:
            cid = int(existente["id"] if isinstance(existente, sqlite3.Row)
                      else existente[0])
            con.execute(
                """UPDATE wa_conversa
                      SET nome=COALESCE(NULLIF(?, ''), nome),
                          etiqueta=?, rascunho=?, status=?,
                          auto_ok=0, atualizado_em=?
                    WHERE id=?""",
                (nome, etiqueta, rascunho, WA.ABERTA, quando, cid),
            )
        else:
            cur = con.execute(
                """INSERT INTO wa_conversa
                       (wa_id, nome, etiqueta, status, rascunho,
                        auto_ok, atualizado_em)
                   VALUES (?, ?, ?, ?, ?, 0, ?)""",
                (wa_id, nome, etiqueta, WA.ABERTA, rascunho, quando),
            )
            cid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO wa_mensagem
                   (conversa_id, direcao, texto, bruto_json, criado_em, meta_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (cid, DIR_IN, texto, bruto, quando, meta_id or None),
        )
        criadas += 1
        ids.append(cid)
    return {"criadas": criadas, "repetidas": repetidas, "conversa_ids": ids}


def listar_conversas(con: sqlite3.Connection) -> list[dict]:
    linhas = con.execute(
        """SELECT c.id, c.wa_id, c.nome, c.etiqueta, c.status, c.rascunho,
                  c.auto_ok, c.atualizado_em,
                  (SELECT m.texto FROM wa_mensagem m
                    WHERE m.conversa_id=c.id
                    ORDER BY m.id DESC LIMIT 1) AS ultimo_texto
             FROM wa_conversa c
            ORDER BY c.atualizado_em DESC, c.id DESC"""
    ).fetchall()
    return [dict(r) for r in linhas]


def conversa(con: sqlite3.Connection, conversa_id: int) -> dict | None:
    row = con.execute(
        "SELECT * FROM wa_conversa WHERE id=?", (int(conversa_id),)
    ).fetchone()
    if not row:
        return None
    msgs = con.execute(
        """SELECT * FROM wa_mensagem
            WHERE conversa_id=?
            ORDER BY id ASC""",
        (int(conversa_id),),
    ).fetchall()
    d = dict(row)
    d["mensagens"] = [dict(m) for m in msgs]
    return d


def salvar_rascunho(con: sqlite3.Connection, conversa_id: int, texto: str,
                    agora: str | None = None) -> None:
    quando = agora or agora_iso()
    con.execute(
        """UPDATE wa_conversa
              SET rascunho=?, atualizado_em=?
            WHERE id=?""",
        (texto, quando, int(conversa_id)),
    )


def resolver(con: sqlite3.Connection, conversa_id: int,
             agora: str | None = None) -> None:
    quando = agora or agora_iso()
    con.execute(
        """UPDATE wa_conversa
              SET status=?, atualizado_em=?
            WHERE id=?""",
        (WA.RESOLVIDA, quando, int(conversa_id)),
    )


def _id_da_graph(bruto: str) -> str:
    try:
        d = json.loads(bruto or "{}")
    except json.JSONDecodeError:
        return ""
    msgs = d.get("messages") or []
    if msgs and isinstance(msgs[0], dict):
        return str(msgs[0].get("id") or "").strip()
    return ""


def _mensagem_erro_graph(bruto: str, status: int) -> str:
    try:
        d = json.loads(bruto or "{}")
        err = d.get("error") or {}
        msg = err.get("message") or err.get("error_user_msg")
        if msg:
            return f"A Graph recusou ({status}): {msg}"
    except json.JSONDecodeError:
        pass
    trecho = (bruto or "").strip().replace("\n", " ")[:180]
    return f"A Graph recusou ({status}). {trecho}".strip()


def _http_post_json(url: str, corpo: dict, headers: dict,
                    timeout: float = TIMEOUT_ENVIO) -> tuple[int, str]:
    """POST JSON. Isolado para o teste mockar urllib. Nao loga cabecalho."""
    data = json.dumps(corpo).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        corpo_e = e.read().decode("utf-8", errors="replace")
        return int(e.code), corpo_e
    except Exception as e:
        raise EnvioErro(
            f"Nao consegui falar com a Graph: {e}. Nada foi enviado."
        ) from e


def enviar_rascunho(con: sqlite3.Connection, conversa_id: int,
                    agora: str | None = None,
                    http_post: Callable | None = None) -> dict:
    """POST na Graph Cloud API. So o rascunho conferido. Nao autoenvia."""
    d = conversa(con, conversa_id)
    if not d:
        raise EnvioErro("Conversa nao encontrada.")
    texto = (d.get("rascunho") or "").strip()
    if not texto:
        raise EnvioErro("Nao ha rascunho para enviar.")
    token = ler_config(con, WA.CHAVE_TOKEN)
    phone = ler_config(con, WA.CHAVE_PHONE)
    if not token or not phone:
        raise EnvioErro("Falta access_token ou phone_number_id na configuracao.")
    url = f"https://graph.facebook.com/{GRAPH_VER}/{phone}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": d["wa_id"],
        "type": "text",
        "text": {"body": texto},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    fn = http_post or _http_post_json
    status, bruto = fn(url, payload, headers)
    if status < 200 or status >= 300:
        raise EnvioErro(_mensagem_erro_graph(bruto, status))
    meta_id = _id_da_graph(bruto) or None
    quando = agora or agora_iso()
    con.execute(
        """INSERT INTO wa_mensagem
               (conversa_id, direcao, texto, bruto_json, criado_em, meta_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (int(conversa_id), DIR_OUT, texto, None, quando, meta_id),
    )
    con.execute(
        """UPDATE wa_conversa
              SET status=?, atualizado_em=?
            WHERE id=?""",
        (WA.AGUARDANDO, quando, int(conversa_id)),
    )
    return {"ok": True, "meta_id": meta_id}
