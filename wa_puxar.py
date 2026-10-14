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
import sqlite3
import urllib.error
import urllib.request
from typing import Any, Callable

import serventia as SERV
import wa_balcao as WA
import wa_schema as SCH

TIMEOUT_PUXAR = 8


def _http_get(url: str, segredo: str, timeout: float = TIMEOUT_PUXAR) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    if segredo:
        req.add_header("Authorization", f"Bearer {segredo}")
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


def puxar_pendentes(con: sqlite3.Connection, *,
                    http_get: Callable | None = None,
                    serventia: Any = None,
                    agora: str | None = None) -> dict:
    """Busca pendentes na caixa-postal e aplica na fila. Sem rede se mockado."""
    url = WA.ler_config(con, SCH.CHAVE_CAIXA_URL)
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
    for item in _itens(bruto):
        r = WA.aplicar_entrada(con, item, serventia=serventia, agora=agora)
        aplicadas += int(r.get("criadas") or 0)
        repetidas += int(r.get("repetidas") or 0)
    return {"ok": True, "aplicadas": aplicadas, "repetidas": repetidas}
