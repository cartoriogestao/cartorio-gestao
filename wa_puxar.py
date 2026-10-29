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
from pathlib import Path
import urllib.error
import urllib.request
from typing import Any, Callable

import serventia as SERV
import wa_balcao as WA
import wa_schema as SCH

TIMEOUT_PUXAR = 8

_LOG = logging.getLogger(__name__)


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


# BUSCAR E APLICAR SÃO DOIS PASSOS (26/10/2026). A rota punha o GET da
# caixa-postal — oito segundos de prazo — dentro de `db.transaction()`, com a
# trava de escrita da casa presa enquanto a VPS respondia. Agora a rota lê a
# configuração, busca FORA da transação e só então abre a transação curta que
# aplica. O antigo `puxar_pendentes`, que fazia os dois juntos, saiu: deixá-lo
# seria deixar pronta a porta para a rede voltar a ficar dentro da transação.


def buscar_pendentes(con: Any, http_get: Callable | None = None) -> dict:
    """Lê a configuração em `con` e FALA COM A REDE. Não grava nada.

    Devolve {"ok": True, "itens": [...]} ou {"ok": False, "motivo": ...}."""
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
    return {"ok": True, "itens": _itens(bruto)}


def aplicar_itens(con: Any, itens: list, *, serventia: Any = None,
                  agora: str | None = None) -> dict:
    """Aplica na fila o que a caixa-postal devolveu. ESCREVE; não fala com a rede."""
    if serventia is None:
        serventia = SERV.PADRAO
    aplicadas = 0
    repetidas = 0
    entregas = 0
    ids: list[Any] = []
    for item in itens or []:
        corpo, eid = _desembrulhar(item)
        r = WA.aplicar_entrada(con, corpo, serventia=serventia, agora=agora)
        aplicadas += int(r.get("criadas") or 0)
        repetidas += int(r.get("repetidas") or 0)
        entregas += int(r.get("entregas") or 0)
        if _id_confirmavel(eid):
            ids.append(eid)
    return {"ok": True, "aplicadas": aplicadas, "repetidas": repetidas,
            "entregas": entregas, "ids": ids}


def confirmar(con: Any, ids: list[Any] | None, http_post: Callable | None = None) -> None:
    """O TERCEIRO PASSO (envelope e confirmação, 27/10/2026): POST
    `<caixa_url>/ack` com os ids do que `aplicar_itens` gravou. FALA COM A REDE
    e não grava nada — quem chama confirma DEPOIS da transação que aplicou, e
    fora dela, como a busca. Falha aqui não desfaz a puxada: só avisa (o item
    volta na próxima busca e é contado como repetido). Lê a configuração em
    `con`: o segredo não passa pelo resultado que a rodada imprime."""
    if not ids:
        return
    url = WA.ler_config(con, SCH.CHAVE_CAIXA_URL)
    if not url or not str(url).strip().lower().startswith("https://"):
        return
    segredo = WA.ler_config(con, SCH.CHAVE_CAIXA_SEGREDO)
    fn = http_post or _http_post
    try:
        status, _bruto = fn(str(url).rstrip("/") + "/ack", segredo, {"ids": list(ids)})
    except Exception:                                   # noqa: BLE001 — só avisa
        _LOG.warning("caixa-postal: ack falhou")
        return
    if status < 200 or status >= 300:
        _LOG.warning("caixa-postal: ack falhou (HTTP %s)", status)


# ------------------------------------------------------------------ a central da automação


def rodar_automacao(ctx) -> dict:
    """O processo WHATSAPP_CAIXA_POSTAL: a mesma volta do vigia do servidor
    (`wa_vigia.um_ciclo`) — busca, aplica e confirma; baixa os arquivos; roda
    o atendente com IA; manda o aviso de fora do horário; resolve as paradas.
    ESCREVE (a fila do balcão).

    27/10/2026, na configuração da VPS: a busca só acontecia no botão. 29/10:
    o atendente com IA não rodava em lugar nenhum sozinho — só no clique —, e
    os arquivos dos clientes nunca eram baixados. Desde então a automação é a
    RESERVA do vigia: as duas podem rodar juntas sem dobrar nada (ver
    `wa_vigia`)."""
    import automacao_processos as PROC
    import automacao_schema as ASCH
    import wa_vigia as VIGIA
    pasta = Path(ctx.db.db_path).parent
    r = VIGIA.um_ciclo(ctx.db, pasta_dados=pasta,
                       pasta_arquivos=VIGIA.pasta_de_arquivos(ctx.db, pasta),
                       agora=ctx.agora.isoformat(timespec="seconds"), encerrar=True)
    if r.get("caixa"):
        return PROC.resultado(ASCH.AVISO, f"Caixa-postal não lida: {r['caixa']}.")
    texto = (f"{r['aplicadas']} mensagem(ns) nova(s) na fila do balcão, "
             f"{r['repetidas']} repetida(s); {r['arquivos']} arquivo(s) baixado(s); "
             f"{r['ia']} conversa(s) com a IA; {r['avisos']} aviso(s) de fora do horário.")
    if r["erros"]:
        return PROC.resultado(ASCH.AVISO, texto + " Falhou: " + ", ".join(r["erros"]) + ".")
    return PROC.resultado(ASCH.OK, texto)


def busca_automatica_ligada(con: Any) -> bool:
    """O processo WHATSAPP_CAIXA_POSTAL está ligado? Ligado, ele busca de 2 em 2
    minutos, e a tela não precisa do botão de atualizar; desligado (ou sem a
    automação nesta instalação), o botão é o único jeito de trazer mensagem."""
    try:
        import automacao as AU
        p = AU.por_codigo(con, CATALOGO[0]["codigo"])
    except Exception:                                   # noqa: BLE001
        return False
    return bool(p and int(p.get("ativo") or 0) == 1)


CATALOGO = (
    {"codigo": "WHATSAPP_CAIXA_POSTAL", "nome": "WhatsApp — buscar na caixa-postal",
     "setor": "GESTAO", "funcao": f"wa_puxar.{rodar_automacao.__name__}", "timeout_s": 120,
     "agenda": {"dias": [0, 1, 2, 3, 4, 5, 6], "intervalo_min": 2,
                "janela": ["06:00", "22:00"]},
     "descricao": "De 2 em 2 minutos: a reserva do vigia do servidor (que busca de "
                  "20 em 20 segundos). Traz da caixa-postal da VPS as mensagens que o "
                  "WhatsApp entregou, baixa os arquivos, roda o atendente com IA e o "
                  "aviso de fora do horário."},
)

