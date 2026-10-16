"""Camada ÚNICA do Cartório Gestão para falar com o serviço A3 local.

Módulos de negócio (Notas, RI, CCN…) NÃO falam com o token. Só chamam daqui:
  listar_certificados()
  assinar_pdf(pdf, pin, thumbprint=None)
  status_do_servico()

Timeout curto. Falha → AssinarComA3Error com frase de balcão.
Nunca carrega DLL PKCS#11 neste processo (nem no Flask).
PIN só via argumento da função / tela — nunca .cred, banco, log ou argv.
Sem chamada a e-Notariado/CCN neste marco (A3-0/A3-1).
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Any

HOST = "127.0.0.1"
PORTA = 8766
PRAZO_SEGUNDOS = 8.0
PRAZO_ASSINAR_SEGUNDOS = 50.0
URL_BASE = f"http://{HOST}:{PORTA}"


class AssinarComA3Error(ValueError):
    """Erro de regra / serviço, com mensagem pronta para o balcão."""


def _url(caminho: str) -> str:
    return f"{URL_BASE}{caminho}"


def _get(caminho: str, *, prazo: float = PRAZO_SEGUNDOS) -> dict[str, Any]:
    req = urllib.request.Request(_url(caminho), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=prazo) as resp:
            corpo = resp.read().decode("utf-8")
            return json.loads(corpo)
    except urllib.error.HTTPError as exc:
        detalhe = _ler_erro_http(exc)
        raise AssinarComA3Error(detalhe) from None
    except urllib.error.URLError:
        raise AssinarComA3Error(
            "o serviço local de assinatura A3 não está no ar "
            f"(esperado em {URL_BASE}). No servidor de sandbox, rode: "
            "py -3 a3_servico_local.py") from None
    except TimeoutError:
        raise AssinarComA3Error(
            "o serviço A3 demorou demais para responder — tente de novo") from None
    except json.JSONDecodeError:
        raise AssinarComA3Error(
            "o serviço A3 devolveu resposta inválida") from None


def _post_json(caminho: str, corpo: dict[str, Any], *,
               prazo: float) -> dict[str, Any]:
    bruto = json.dumps(corpo).encode("utf-8")
    req = urllib.request.Request(
        _url(caminho), data=bruto, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=prazo) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detalhe = _ler_erro_http(exc)
        raise AssinarComA3Error(detalhe) from None
    except urllib.error.URLError:
        raise AssinarComA3Error(
            "o serviço local de assinatura A3 não está no ar "
            f"(esperado em {URL_BASE}). No servidor de sandbox, rode: "
            "py -3 a3_servico_local.py") from None
    except TimeoutError:
        raise AssinarComA3Error(
            "a assinatura A3 demorou demais — confira o token e o PIN") from None
    except json.JSONDecodeError:
        raise AssinarComA3Error(
            "o serviço A3 devolveu resposta inválida") from None


def _ler_erro_http(exc: urllib.error.HTTPError) -> str:
    try:
        corpo = json.loads(exc.read().decode("utf-8"))
        return str(corpo.get("erro") or f"serviço A3 respondeu HTTP {exc.code}")
    except Exception:
        return f"serviço A3 respondeu HTTP {exc.code}"


def status_do_servico() -> dict[str, Any]:
    """GET /saude. Devolve dict com ok/driver; ou levanta AssinarComA3Error."""
    dados = _get("/saude")
    if not dados.get("ok"):
        raise AssinarComA3Error(
            dados.get("erro") or "serviço A3 respondeu sem ok")
    return dados


def servico_no_ar() -> bool:
    """True se GET /saude ok; False se o serviço não responde (nunca estoura)."""
    try:
        status_do_servico()
        return True
    except AssinarComA3Error:
        return False


def listar_certificados() -> list[dict[str, str]]:
    """Lista certificados do token via serviço local. Pode ser lista vazia."""
    dados = _get("/certificados", prazo=PRAZO_ASSINAR_SEGUNDOS)
    if not dados.get("ok", True) and dados.get("erro"):
        raise AssinarComA3Error(str(dados["erro"]))
    lista = dados.get("certificados") or []
    return list(lista)


def assinar_pdf(pdf: bytes, pin: str, *,
                thumbprint: str | None = None) -> dict[str, Any]:
    """Assina PDF pelo serviço local. PIN só neste argumento (efêmero).

    Devolve dict com cms_b64 (se montado), assinatura_b64, certificado_b64,
    subject, thumbprint, formato, mecanismo.
    """
    if not pin:
        raise AssinarComA3Error(
            "digite o PIN do certificado antes de assinar — ele não fica "
            "guardado em lugar nenhum, e é pedido a cada assinatura")
    if not pdf:
        raise AssinarComA3Error("PDF vazio — nada para assinar")

    corpo: dict[str, Any] = {
        "pdf_b64": base64.b64encode(pdf).decode("ascii"),
        "pin": pin,
    }
    if thumbprint:
        corpo["thumbprint"] = thumbprint

    dados = _post_json("/assinar/pdf", corpo, prazo=PRAZO_ASSINAR_SEGUNDOS)
    # Não reter pin
    corpo["pin"] = ""
    if not dados.get("ok", True):
        raise AssinarComA3Error(
            str(dados.get("erro") or "assinatura A3 recusada"))
    return dados


# ACRÉSCIMO DE 15/10/2026 (sessão do protesto): a assinatura pelo repositório
# do Windows, a rota `/assinar/pdf-windows` do serviço local. Sem PIN aqui: a
# janela do próprio token o pede ao titular, e por isso o prazo é longo.
PRAZO_ASSINAR_PELO_WINDOWS_SEGUNDOS = 200.0


def assinar_pdf_pelo_windows(pdf: bytes, *,
                             thumbprint: str | None = None) -> dict[str, Any]:
    """Assina o PDF pelo Windows, no serviço local. Devolve `cms_b64` etc."""
    if not pdf:
        raise AssinarComA3Error("PDF vazio — nada para assinar")
    corpo: dict[str, Any] = {"pdf_b64": base64.b64encode(pdf).decode("ascii")}
    if thumbprint:
        corpo["thumbprint"] = thumbprint
    dados = _post_json("/assinar/pdf-windows", corpo,
                       prazo=PRAZO_ASSINAR_PELO_WINDOWS_SEGUNDOS)
    if not dados.get("ok", True):
        raise AssinarComA3Error(
            str(dados.get("erro") or "assinatura pelo Windows recusada"))
    return dados
