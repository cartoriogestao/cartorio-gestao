"""Puxar inbound da caixa-postal (host XMPP), sem expor o SERVIDOR.

A Meta NÃO chama o Flask do Cartorio Gestao em producao. Worker minimo
na VPS Hostinger (127.0.0.1 atras do Apache de equipetextual.com.br)
recebe `/whatsapp/webhook` e guarda JSON; este modulo PUXA `/pendentes`.
URL documentada: https://equipetextual.com.br/pendentes
(alternativa de path: /wa-caixa). Nao usar srv750938.hstgr.cloud (sem TLS).
Nao instalar tunel no Windows. Deploy SSH do worker: o oficial ainda nao pediu.

Nao instala nada no Windows do cartorio. Nao abre a porta 8765.
Nos testes, `http_get` e mockado: nao bate na rede de verdade.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import urllib.error
import urllib.request
from typing import Any, Callable

import serventia as SERV
import wa_balcao as WA
import wa_schema as SCH

_LOG = logging.getLogger(__name__)

TIMEOUT_PUXAR = 8


def _marcar_segredo(req: urllib.request.Request, segredo: str) -> None:
    """A caixa exige os dois; só o Bearer já respondeu 401."""
    if not segredo:
        return
    req.add_header("Authorization", f"Bearer {segredo}")
    req.add_header("X-Caixa-Segredo", segredo)


def _http_get(url: str, segredo: str, timeout: float = TIMEOUT_PUXAR) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    _marcar_segredo(req, segredo)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return int(e.code), e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, str(e)


def _http_post(url: str, segredo: str, corpo: dict,
               timeout: float = TIMEOUT_PUXAR) -> tuple[int, str]:
    data = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    _marcar_segredo(req, segredo)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return int(e.code), e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, str(e)


def _itens(bruto: str) -> list[Any]:
    try:
        d = json.loads(bruto or "[]")
    except json.JSONDecodeError:
        return []
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        for k in ("pendentes", "items", "entry", "payloads"):
            v = d.get(k)
            if isinstance(v, list):
                return v
        if d.get("object") or d.get("entry") or d.get("messages"):
            return [d]
    return []


def _desembrulhar(item: Any) -> tuple[Any, Any]:
    """Envelope `{id, payload}` vira o webhook; o formato antigo passa inteiro."""
    if isinstance(item, dict) and "payload" in item:
        return item["payload"], item.get("id")
    return item, None


def _id_confirmavel(eid: Any) -> bool:
    if eid is None:
        return False
    if isinstance(eid, str) and not eid.strip():
        return False
    return True


def _confirmar(caixa_url: str, segredo: str, ids: list[Any],
               http_post: Callable | None = None) -> None:
    """POST `<caixa_url>/ack`. Falha aqui não desfaz a puxada: só avisa."""
    if not ids:
        return
    url = str(caixa_url).rstrip("/") + "/ack"
    fn = http_post or _http_post
    try:
        status, _bruto = fn(url, segredo, {"ids": list(ids)})
    except Exception:
        _LOG.warning("caixa-postal: ack falhou")
        return
    if status < 200 or status >= 300:
        _LOG.warning("caixa-postal: ack falhou (HTTP %s)", status)


def puxar_pendentes(con: sqlite3.Connection, *,
                    http_get: Callable | None = None,
                    http_post: Callable | None = None,
                    serventia: Any = None,
                    agora: str | None = None) -> dict:
    """Busca pendentes na caixa-postal e aplica na fila. Sem rede se mockado."""
    url = WA.ler_config(con, SCH.CHAVE_CAIXA_URL)
    # O SEGREDO SÓ VIAJA EM HTTPS (revisão de segurança de 22/10/2026, M11):
    # o `Bearer` ia para a URL que o ADMIN gravasse, inclusive `http://`, e
    # qualquer máquina no caminho o leria.
    if url and not str(url).strip().lower().startswith("https://"):
        return {"ok": False, "motivo": "caixa_url sem https: o segredo iria em "
                                       "claro pela rede — corrija nas configurações",
                "aplicadas": 0, "ignoradas": 0, "erros": []}
    if not url:
        return {"ok": False, "motivo": "caixa_url vazia", "aplicadas": 0,
                "repetidas": 0}
    segredo = WA.ler_config(con, SCH.CHAVE_CAIXA_SEGREDO)
    fn = http_get or _http_get
    status, bruto = fn(url, segredo)
    if status < 200 or status >= 300:
        return {"ok": False, "motivo": f"caixa HTTP {status}",
                "aplicadas": 0, "repetidas": 0}
    if serventia is None:
        serventia = SERV.PADRAO
    aplicadas = 0
    repetidas = 0
    ids: list[Any] = []
    for item in _itens(bruto):
        corpo, eid = _desembrulhar(item)
        r = WA.aplicar_entrada(con, corpo, serventia=serventia, agora=agora)
        aplicadas += int(r.get("criadas") or 0)
        repetidas += int(r.get("repetidas") or 0)
        if _id_confirmavel(eid):
            ids.append(eid)
    _confirmar(url, segredo, ids, http_post=http_post)
    return {"ok": True, "aplicadas": aplicadas, "repetidas": repetidas}
