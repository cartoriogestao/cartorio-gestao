"""Rascunho por provedor (Grok/GPT/Claude/DeepSeek) ou modo local.

Fatia 1: sem SDK pesado. Interface clara `chamar_provedor` com urllib.
Nos testes a rede e SEMPRE mock. Sem chave → modo local (eco prompt+pedido).
Se a chamada falhar, cai no local com aviso. Nunca loga API key.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

import robo_schema as SCH

# URLs documentadas (chat completions / messages).
URLS = {
    "grok": "https://api.x.ai/v1/chat/completions",
    "gpt": "https://api.openai.com/v1/chat/completions",
    "claude": "https://api.anthropic.com/v1/messages",
    "deepseek": "https://api.deepseek.com/chat/completions",
}

MODELOS_PADRAO = {
    "grok": "grok-2-latest",
    "gpt": "gpt-4o-mini",
    "claude": "claude-3-5-haiku-latest",
    "deepseek": "deepseek-chat",
}

AVISO_SEM_CHAVE = "sem chave — modo local"
AVISO_FALHA_API = "falha na API — modo local"


def provedores() -> tuple[str, ...]:
    return SCH.PROVEDORES


def _montar_system(prompt: str, exemplos: list[dict[str, Any]] | None) -> str:
    partes = [(prompt or "").strip() or "Voce redige rascunhos de ato cartorario."]
    if exemplos:
        partes.append("Exemplos (entrada → saida esperada):")
        for i, ex in enumerate(exemplos, 1):
            ent = (ex.get("entrada") or "").strip()
            sai = (ex.get("saida_esperada") or "").strip()
            peso = ex.get("peso") or 1
            partes.append(f"{i}. [peso {peso}]\nENTRADA: {ent}\nSAIDA: {sai}")
    partes.append(
        "Responda so o rascunho. Nao grave em livro. Nao envie WhatsApp."
    )
    return "\n\n".join(partes)


def rascunho_local(prompt: str, pedido: str,
                   exemplos: list[dict[str, Any]] | None = None) -> str:
    """Eco do prompt + pedido (+ exemplos). Sem rede."""
    linhas = [
        "[rascunho local]",
        "",
        "PROMPT:",
        (prompt or "").strip() or "(vazio)",
        "",
        "PEDIDO:",
        (pedido or "").strip() or "(vazio)",
    ]
    if exemplos:
        linhas.append("")
        linhas.append("EXEMPLOS:")
        for ex in exemplos:
            linhas.append(
                f"- {((ex.get('entrada') or '')[:80])} → "
                f"{((ex.get('saida_esperada') or '')[:80])}"
            )
    return "\n".join(linhas)


def chamar_provedor(
    provedor: str,
    api_key: str,
    system: str,
    user: str,
    *,
    timeout: float = 30.0,
) -> str:
    """Chamada HTTP unica. Sem SDK. Testes devem mockar esta funcao.

    Grok/GPT/DeepSeek: JSON estilo OpenAI chat completions.
    Claude: Messages API (x-api-key + anthropic-version).
    """
    prov = (provedor or "").strip().lower()
    if prov not in URLS:
        raise ValueError(f"provedor desconhecido: {provedor!r}")
    key = (api_key or "").strip()
    if not key:
        raise ValueError("api_key vazia")

    url = URLS[prov]
    modelo = MODELOS_PADRAO[prov]

    if prov == "claude":
        corpo = {
            "model": modelo,
            "max_tokens": 2048,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        }
    else:
        corpo = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        }

    data = json.dumps(corpo).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        bruto = resp.read().decode("utf-8", errors="replace")
    parsed = json.loads(bruto)

    if prov == "claude":
        blocos = parsed.get("content") or []
        textos = [
            b.get("text", "") for b in blocos
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        out = "\n".join(t for t in textos if t).strip()
    else:
        choices = parsed.get("choices") or []
        if not choices:
            raise RuntimeError("resposta sem choices")
        msg = (choices[0].get("message") or {})
        out = (msg.get("content") or "").strip()
    if not out:
        raise RuntimeError("resposta vazia do provedor")
    return out


def rascunhar(
    robo: dict[str, Any] | Any,
    pedido: str,
    exemplos: list[dict[str, Any]] | None = None,
    *,
    api_key: str | None = None,
    chamar: Callable[..., str] | None = None,
) -> dict[str, str]:
    """Gera rascunho. Retorna {texto, modo, aviso}.

    Sem chave → local. Com chave → chamar_provedor (ou `chamar` injetado).
    Falha de rede/API → local com aviso. Nunca levanta a chave.
    """
    if hasattr(robo, "keys"):
        prompt = robo["prompt"] or ""
        provedor = (robo["provedor"] or "grok").strip().lower()
    else:
        prompt = (robo.get("prompt") or "")
        provedor = (robo.get("provedor") or "grok").strip().lower()

    ex_list = list(exemplos or [])
    key = (api_key or "").strip()
    system = _montar_system(prompt, ex_list)
    user = (pedido or "").strip()

    if not key:
        return {
            "texto": rascunho_local(prompt, user, ex_list),
            "modo": SCH.MODO_LOCAL,
            "aviso": AVISO_SEM_CHAVE,
        }

    fn = chamar or chamar_provedor
    try:
        texto = fn(provedor, key, system, user)
        return {
            "texto": texto,
            "modo": SCH.MODO_API,
            "aviso": "",
        }
    except Exception as exc:  # noqa: BLE001 — cai no local com aviso
        return {
            "texto": rascunho_local(prompt, user, ex_list),
            "modo": SCH.MODO_LOCAL,
            "aviso": f"{AVISO_FALHA_API} ({type(exc).__name__})",
        }
