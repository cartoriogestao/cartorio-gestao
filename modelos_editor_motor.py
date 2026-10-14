"""Cliente único do motor de prévia (contrato Fidelidade).

Ordem de resolução:
  1) motor real in-process (`import modelos_motor`) — preferido;
  2) HTTP `POST/GET /modelos/api/*` se `app_url` for passado;
  3) fallback local (`modelos_previa.resposta_previa`) com selo
     "prévia aproximada — motor fiel ainda não disponível".

Trocar só este arquivo quando o contrato do motor mudar.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

AVISO_FALLBACK = "prévia aproximada — motor fiel ainda não disponível"


class MotorIndisponivel(Exception):
    """Motor ausente (404/import) — caller deve usar fallback."""


def normalizar_arquivo_resposta(resp: dict) -> dict:
    """Garante `arquivo_base64` (2c) com fallback para o alias `pdf_base64`."""
    if not isinstance(resp, dict):
        return resp
    out = dict(resp)
    arq = out.get("arquivo_base64") or out.get("pdf_base64")
    out["arquivo_base64"] = arq
    out["pdf_base64"] = arq  # alias compatível
    return out


def marcar_bloqueados(area: str, template_id: str, conteudo,
                      *, avisos: list | None = None):
    """Insere `{{#bloqueado id}}` via motor. Fallback: conteúdo intacto + aviso.

    Não grava nada. Para ODT/bytes o motor devolve intacto.
    """
    if avisos is None:
        avisos = []
    if not motor_disponivel():
        avisos.append(
            "marcar_bloqueados: motor ausente — conteúdo sem marcação nova")
        return conteudo, avisos
    try:
        import modelos_motor as MOTOR
        return MOTOR.marcar_bloqueados(area, template_id, conteudo), avisos
    except Exception as err:  # noqa: BLE001
        avisos.append(f"marcar_bloqueados falhou: {err}")
        return conteudo, avisos


def motor_disponivel() -> bool:
    """True se o pacote `modelos_motor*` do Robô Fidelidade estiver importável."""
    try:
        import modelos_motor  # noqa: F401
        return True
    except ImportError:
        return False


def _base_url(app_url: str | None = None) -> str:
    return (app_url or "").rstrip("/")


def _http_json(method: str, url: str, body: dict | None = None,
               timeout: float = 8.0) -> tuple[dict | list, int]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            codigo = getattr(resp, "status", 200) or 200
            try:
                return (json.loads(raw) if raw else {}), int(codigo)
            except json.JSONDecodeError:
                return {"ok": False, "erro": "resposta não-JSON do motor"}, int(codigo)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            raise MotorIndisponivel("404") from err
        raw = err.read().decode("utf-8", errors="replace") if err.fp else ""
        try:
            return (json.loads(raw) if raw else {"ok": False, "erro": str(err)}), err.code
        except json.JSONDecodeError:
            return {"ok": False, "erro": str(err)}, err.code
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as err:
        raise MotorIndisponivel(str(err)) from err


def previa_via_motor_modulo(payload: dict, *, sv: dict | None = None,
                            con=None) -> dict:
    """Chama `modelos_motor.resposta_previa` in-process (contrato real)."""
    import modelos_motor as MOTOR
    conteudo = payload.get("conteudo")
    # Motor 2a espera str|None; se vier dict de partes, serializa aviso
    if isinstance(conteudo, dict):
        # junta partes texto se houver; senão passa None
        partes_txt = [str(v) for v in conteudo.values() if isinstance(v, str) and v.strip()]
        conteudo_arg = "\n\n".join(partes_txt) if partes_txt else None
    else:
        conteudo_arg = conteudo
    resp = MOTOR.resposta_previa(
        area=str(payload.get("area") or "RCPN"),
        template_id=str(payload.get("template_id") or ""),
        dados=payload.get("dados") if isinstance(payload.get("dados"), dict) else {},
        sv=sv,
        papel=str(payload.get("papel") or "a4"),
        formato=str(payload.get("formato") or "html"),
        conteudo=conteudo_arg,
    )
    if isinstance(resp, dict):
        resp = dict(resp)
        resp.setdefault("aproximada", False)
        resp["fonte"] = "motor"
        resp = normalizar_arquivo_resposta(resp)
    return resp


def previa_via_motor_http(payload: dict, *, app_url: str) -> dict:
    """POST /modelos/api/previa — contrato HTTP fechado."""
    url = f"{_base_url(app_url)}/modelos/api/previa"
    corpo, _codigo = _http_json("POST", url, payload)
    if isinstance(corpo, dict):
        corpo = dict(corpo)
        corpo["fonte"] = "motor_http"
        corpo.setdefault("aproximada", False)
        return normalizar_arquivo_resposta(corpo)
    return {"ok": False, "erro": "resposta inesperada", "fonte": "motor_http"}


def campos_via_motor_modulo(*, area: str, tipo: str) -> list[dict]:
    import modelos_motor as MOTOR
    out = MOTOR.campos(area=area, tipo=tipo)
    return list(out) if out is not None else []


def campos_via_motor_http(*, area: str, tipo: str, app_url: str) -> list[dict]:
    q = urllib.parse.urlencode({"area": area, "tipo": tipo})
    url = f"{_base_url(app_url)}/modelos/api/campos?{q}"
    corpo, _ = _http_json("GET", url)
    if isinstance(corpo, list):
        return corpo
    if isinstance(corpo, dict):
        return list(corpo.get("campos") or [])
    return []


def trechos_via_motor_modulo(*, area: str, tipo: str) -> list[dict]:
    import modelos_motor as MOTOR
    out = MOTOR.trechos_bloqueados(area=area, tipo=tipo)
    return list(out) if out is not None else []


def trechos_via_motor_http(*, area: str, tipo: str, app_url: str) -> list[dict]:
    q = urllib.parse.urlencode({"area": area, "tipo": tipo})
    url = f"{_base_url(app_url)}/modelos/api/trechos-bloqueados?{q}"
    corpo, _ = _http_json("GET", url)
    if isinstance(corpo, list):
        return corpo
    if isinstance(corpo, dict):
        return list(corpo.get("trechos") or [])
    return []


# ------------------------------------------------------------------ fallback

def _campos_fallback_local(area: str, tipo: str) -> list[dict]:
    """Vocabulário já existente — só leitura. Sem inventar motor."""
    tipo = (tipo or "").strip().upper()
    itens: list[dict] = []

    from modelos_editor_serventia import ALIAS_SERVENTIA
    for alias in ALIAS_SERVENTIA:
        itens.append({
            "nome": f"serventia.{alias}",
            "rotulo": f"{{{{serventia.{alias}}}}}",
            "tipo": "serventia",
            "obrigatorio": False,
            "exemplo": "",
            "grupo": "Serventia",
        })

    if tipo.startswith("RC_MOLDE_"):
        try:
            import modelos_moldes as MOLDES
            especie = MOLDES.POR_CHAVE.get(tipo, {}).get("especie", "")
            mat = MOLDES.MATRICULA_DA_ESPECIE.get(especie, "")
            if mat:
                itens.append({
                    "nome": mat.lstrip("@"),
                    "rotulo": mat,
                    "tipo": "odt",
                    "obrigatorio": True,
                    "exemplo": "",
                    "grupo": "Molde ODT",
                })
            try:
                import rc_certidao_odt as ODT
                for nome in sorted(ODT.valores({}, {}, {})):
                    itens.append({
                        "nome": nome.lstrip("@"),
                        "rotulo": nome if str(nome).startswith("@") else f"@{nome}",
                        "tipo": "odt",
                        "obrigatorio": False,
                        "exemplo": "",
                        "grupo": "Molde ODT",
                    })
            except Exception:
                pass
        except Exception:
            pass
        return itens

    if tipo.startswith("RC_"):
        try:
            import modelos_elementos as ELEM
            import modelos_da_casa as CASA
            try:
                texto = CASA.padrao_de(tipo)
            except Exception:
                texto = ""
            for m in ELEM.legenda_do_ato(tipo, texto):
                itens.append({
                    "nome": m.get("nome") or m.get("codigo", ""),
                    "rotulo": m.get("rotulo") or m.get("codigo", ""),
                    "tipo": "texto",
                    "obrigatorio": False,
                    "exemplo": "",
                    "grupo": "Campos do ato",
                    "codigo": m.get("codigo", ""),
                })
        except Exception:
            pass
    return itens


def _bloqueados_fallback_local(area: str, tipo: str) -> tuple[list[dict], list[str]]:
    return [], ["lista de trechos bloqueados vazia — motor ainda não disponível"]


def previa_fallback_local(con, ato: str, form) -> dict:
    """Chama modelos_previa.resposta_previa sem modificá-la."""
    import modelos_previa as PREVIA
    corpo, codigo = PREVIA.resposta_previa(con, ato, form)
    if not isinstance(corpo, dict):
        corpo = {"ok": False, "erro": "prévia inválida"}
    avisos = list(corpo.get("avisos") or [])
    if AVISO_FALLBACK not in avisos:
        avisos.append(AVISO_FALLBACK)
    corpo["avisos"] = avisos
    corpo["aproximada"] = True
    corpo["fonte"] = "fallback"
    corpo.setdefault("paginas", 1)
    corpo.setdefault("erros", [])
    corpo.setdefault("placeholders_usados", [])
    corpo.setdefault("placeholders_desconhecidos", [])
    if corpo.get("ok") and "html" in corpo:
        html = corpo["html"] or ""
        selo = (
            '<div style="position:sticky;top:0;z-index:9;background:#fff3cd;'
            'color:#7a5b00;font:12px/1.4 sans-serif;padding:8px 12px;'
            'border-bottom:1px solid #e0c36a;text-align:center">'
            f"{AVISO_FALLBACK}</div>"
        )
        if "<body" in html.lower():
            import re
            corpo["html"] = re.sub(
                r"(?i)<body([^>]*)>",
                lambda m: f"<body{m.group(1)}>{selo}",
                html, count=1)
        else:
            corpo["html"] = selo + html
    corpo["_http"] = codigo
    return corpo


def previa(con, *, area: str, template_id: str, conteudo: dict | str | None = None,
           dados: dict | None = None, assento_id: Any = None,
           papel: str = "a4", formato: str = "html",
           versao: Any = None, app_url: str | None = None,
           form_fallback: dict | None = None,
           sv: dict | None = None) -> dict:
    """Prévia: motor real → HTTP → fallback local."""
    payload = {
        "area": area,
        "template_id": template_id,
        "versao": versao,
        "conteudo": conteudo,
        "dados": dict(dados or {}),
        "assento_id": assento_id,
        "papel": papel if str(papel).lower() in ("a4", "seguranca") else "a4",
        "formato": formato if str(formato).lower() in ("html", "pdf", "odt") else "html",
    }
    if assento_id is not None and "assento_id" not in payload["dados"]:
        payload["dados"]["assento_id"] = assento_id

    # 1) motor real in-process
    if motor_disponivel():
        try:
            return normalizar_arquivo_resposta(
                previa_via_motor_modulo(payload, sv=sv, con=con))
        except Exception as err:  # noqa: BLE001
            # Se o motor quebrou, ainda tenta HTTP/fallback
            motor_erro = str(err)
        else:
            motor_erro = None
    else:
        motor_erro = None

    # 2) HTTP
    if app_url:
        try:
            return normalizar_arquivo_resposta(
                previa_via_motor_http(payload, app_url=app_url))
        except MotorIndisponivel:
            pass

    # 3) fallback
    form = dict(form_fallback or {})
    if conteudo and isinstance(conteudo, dict):
        for parte, texto in conteudo.items():
            form[f"parte_{str(parte).lower()}"] = texto if isinstance(texto, str) else ""
    form["_papel_editor"] = payload["papel"]
    resp = previa_fallback_local(con, template_id, form)
    if motor_erro:
        resp.setdefault("avisos", []).append(f"motor real falhou: {motor_erro}")
    return normalizar_arquivo_resposta(resp)


def campos(*, area: str, tipo: str, app_url: str | None = None) -> dict:
    if motor_disponivel():
        try:
            return {
                "campos": campos_via_motor_modulo(area=area, tipo=tipo),
                "avisos": [],
                "fonte": "motor",
            }
        except Exception as err:  # noqa: BLE001
            avisos_extra = [f"motor real falhou: {err}"]
        else:
            avisos_extra = []
    else:
        avisos_extra = []

    if app_url:
        try:
            return {
                "campos": campos_via_motor_http(area=area, tipo=tipo, app_url=app_url),
                "avisos": [],
                "fonte": "motor_http",
            }
        except MotorIndisponivel:
            pass

    return {
        "campos": _campos_fallback_local(area, tipo),
        "avisos": (avisos_extra or []) + [
            "campos do vocabulário local — motor ainda não disponível"],
        "fonte": "fallback",
    }


def trechos_bloqueados(*, area: str, tipo: str,
                       app_url: str | None = None) -> dict:
    if motor_disponivel():
        try:
            return {
                "trechos": trechos_via_motor_modulo(area=area, tipo=tipo),
                "avisos": [],
                "fonte": "motor",
            }
        except Exception:
            pass

    if app_url:
        try:
            return {
                "trechos": trechos_via_motor_http(
                    area=area, tipo=tipo, app_url=app_url),
                "avisos": [],
                "fonte": "motor_http",
            }
        except MotorIndisponivel:
            pass

    lista, avisos = _bloqueados_fallback_local(area, tipo)
    return {"trechos": lista, "avisos": avisos, "fonte": "fallback"}
