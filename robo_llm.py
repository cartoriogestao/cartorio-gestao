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

import ia_uso as USO
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


def _pedir(provedor: str, api_key: str, system: str, user: str, *,
           timeout: float) -> dict[str, Any]:
    """A chamada em si, sem o registro: texto, tokens e modelo."""
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
    uso = parsed.get("usage") or {}
    return {"texto": out, "modelo": str(parsed.get("model") or modelo),
            "entrada": int(uso.get("input_tokens") or uso.get("prompt_tokens") or 0),
            "saida": int(uso.get("output_tokens") or uso.get("completion_tokens") or 0)}


def _motivo(erro: BaseException) -> tuple[str, str]:
    """O resultado e o resumo de forma fixa da falha, para o `ia_uso`.

    Nunca a mensagem: a do provedor pode trazer de volta o que subiu.
    """
    if isinstance(erro, urllib.error.HTTPError):
        return (USO.RECUSADO if 400 <= erro.code < 500 and erro.code != 429
                else USO.ERRO), f"HTTP {erro.code}"
    if isinstance(erro, ValueError) and not isinstance(erro, json.JSONDecodeError):
        return USO.RECUSADO, ("sem chave" if "api_key" in str(erro)
                              else "provedor desconhecido")
    if isinstance(erro, (TimeoutError, urllib.error.URLError, OSError)):
        return USO.ERRO, ("sem resposta no prazo" if "timed out" in str(erro).lower()
                          else "sem rede")
    if isinstance(erro, json.JSONDecodeError):
        return USO.ERRO, "resposta ilegível"
    if isinstance(erro, RuntimeError):
        return USO.ERRO, "resposta vazia"
    return USO.ERRO, type(erro).__name__


def _pedido_nao_saiu(erro: BaseException) -> bool:
    """O pedido falhou ANTES de sair? Só aí a vaga da cota volta (26/10/2026).

    - recusa antes da rede (provedor desconhecido, chave vazia): não saiu;
    - `URLError` é o que o `urllib` levanta quando a CONEXÃO ou o ENVIO falham
      (ele embrulha só o `request`, e não a leitura da resposta): não saiu —
      salvo se a razão for prazo esgotado, que conta como enviado;
    - `HTTPError` (o provedor respondeu), prazo esgotado na leitura, resposta
      ilegível ou vazia: saiu, e a vaga fica gasta.
    """
    if isinstance(erro, urllib.error.HTTPError):
        return False
    if isinstance(erro, ValueError) and not isinstance(erro, json.JSONDecodeError):
        return True
    if isinstance(erro, urllib.error.URLError):
        razao = erro.reason
        if isinstance(razao, TimeoutError) or "timed out" in str(razao).lower():
            return False
        return True
    return False


def chamar_provedor(
    provedor: str,
    api_key: str,
    system: str,
    user: str,
    *,
    timeout: float = 30.0,
    pasta_de_dados: Any = None,
    modulo: str = "",
    finalidade: str = "",
    usuario: str = "",
    atribuicao: str = "",
    referencia: str = "",
    mascarado: bool | None = None,
) -> str:
    """Chamada HTTP unica. Sem SDK. Testes devem mockar esta funcao.

    Grok/GPT/DeepSeek: JSON estilo OpenAI chat completions.
    Claude: Messages API (x-api-key + anthropic-version).

    CADA CHAMADA FICA REGISTRADA (LF01): é um dos dois transportes de IA do
    sistema, e grava em `ia_uso` como `agente_provedores.conversar` — quando,
    de onde, para quê, quem, provedor, modelo, tokens e como terminou, e
    NUNCA o texto. Sem `pasta_de_dados` o registro vai para o log do sistema
    (não há banco onde gravar), e a chamada segue igual.
    """
    registro = {"modulo": modulo, "finalidade": finalidade, "usuario": usuario,
                "atribuicao": atribuicao, "referencia": referencia,
                "mascarado": mascarado,
                "provedor": (provedor or "").strip().lower(),
                "modelo": MODELOS_PADRAO.get((provedor or "").strip().lower(), "")}
    # A COTA DO DIA SE RESERVA ANTES DA REDE (26/10/2026, achado transversal
    # 3 da revisão de segurança) — a mesma regra de `agente_provedores.
    # conversar`. Teto atingido ou cota que não pôde ser conferida: nada sobe,
    # e o registro diz por quê. A vaga só volta se o pedido NÃO SAIU.
    try:
        reserva = USO.reservar(pasta_de_dados, finalidade)
    except USO.TetoAtingido as teto:
        USO.registrar(pasta_de_dados, **registro, resultado=USO.RECUSADO,
                      erro=("cota indisponível"
                            if isinstance(teto, USO.ReservaIndisponivel)
                            else "teto do dia"))
        raise
    try:
        lida = _pedir(provedor, api_key, system, user, timeout=timeout)
    except Exception as erro:
        resultado, motivo = _motivo(erro)
        if _pedido_nao_saiu(erro):
            USO.devolver(pasta_de_dados, reserva)
        else:
            USO.consumida_sem_resposta(reserva, motivo)
        USO.registrar(pasta_de_dados, **registro, resultado=resultado, erro=motivo)
        raise
    registro["modelo"] = lida["modelo"] or registro["modelo"]
    USO.registrar(pasta_de_dados, **registro, resultado=USO.OK,
                  tokens_entrada=lida["entrada"], tokens_saida=lida["saida"])
    return lida["texto"]


def rascunhar(
    robo: dict[str, Any] | Any,
    pedido: str,
    exemplos: list[dict[str, Any]] | None = None,
    *,
    api_key: str | None = None,
    chamar: Callable[..., str] | None = None,
    **registro: Any,
) -> dict[str, str]:
    """Gera rascunho. Retorna {texto, modo, aviso}.

    Sem chave → local. Com chave → chamar_provedor (ou `chamar` injetado).
    Falha de rede/API → local com aviso. Nunca levanta a chave.

    `registro` são os dados do uso de IA que `chamar_provedor` grava
    (`pasta_de_dados`, `modulo`, `finalidade`, `usuario`, `referencia`...).
    O modo local não fala com provedor nenhum, e por isso não registra.
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
        texto = fn(provedor, key, system, user, **registro)
        return {
            "texto": texto,
            "modo": SCH.MODO_API,
            "aviso": "",
        }
    except USO.TetoAtingido as teto:
        # O TETO DO DIA NÃO É FALHA DA API: a tela diz a frase dele, e não
        # «falha na API (TetoAtingido)». Nada subiu.
        return {
            "texto": rascunho_local(prompt, user, ex_list),
            "modo": SCH.MODO_LOCAL,
            "aviso": str(teto),
        }
    except Exception as exc:  # noqa: BLE001 — cai no local com aviso
        return {
            "texto": rascunho_local(prompt, user, ex_list),
            "modo": SCH.MODO_LOCAL,
            "aviso": f"{AVISO_FALHA_API} ({type(exc).__name__})",
        }
