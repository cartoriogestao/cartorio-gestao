# -*- coding: utf-8 -*-
"""Blueprint Flask do motor de fidelidade — Etapa 2a/2b.

Rotas (contrato aprovado):
  POST /modelos/api/previa
  GET  /modelos/api/campos?area=&tipo=
  GET  /modelos/api/trechos-bloqueados?area=&tipo=

Como plugar (ainda NÃO aplicar em app.py nesta etapa — Editor/teste cart
pediram aviso):

    import modelos_motor_web
    app.register_blueprint(modelos_motor_web.modelos_motor_api)
    # ou, no padrão da casa:
    # modelos_motor_web.registrar_rotas(app, db, login_required, roles_required, audit)

Sem selo, sem numeração, sem gravação nas prévias.

2c: `conteudo` NÃO SALVO (texto do termo ou ODT base64 do molde) substitui o
persistido pelo mesmo pipeline da emissão; resposta com `arquivo_base64`
(+ alias `pdf_base64`) e `mime`. Com `login_required` passado a
`registrar_rotas` (padrão do app.py), as 3 rotas exigem login e respondem
401 em JSON (não redirecionam para a tela de login).

2b: `POST /modelos/api/previa` com `template_id` `RC_TERMO_*` (ou
`area: "TERMO"`) devolve a prévia do TERMO (mesmo contrato + `texto` e
`correcoes`). Com `assento_id`, lê o assento (SELECT) e corrige o teor só na
prévia; `escrevente`/`funcao` opcionais (senão vale a regra viva da casa);
`estilo_data` opcional (`extenso` [padrão] | `so_extenso` | `mes_numerado`;
`padrao`/`casa` = `extenso`).
"""
from __future__ import annotations

from functools import wraps

from flask import Blueprint, current_app, jsonify, request

import modelos_motor as MOTOR
import serventia as SERV

modelos_motor_api = Blueprint("modelos_motor_api", __name__)


def _sv_do_app():
    """Lê cadastro da casa — nunca hardcode de CNS/endereço aqui."""
    db = current_app.extensions.get("db")
    if db is not None and hasattr(db, "get_settings"):
        return SERV.dados(db.get_settings)
    get_settings = current_app.extensions.get("get_settings")
    if callable(get_settings):
        return SERV.dados(get_settings)
    return SERV.dados({})


def _carregar_contexto_termo(dados: dict, sv: dict, corpo: str | None = None):
    """Termo de um assento real (só leitura). None se não houver id/banco."""
    db = current_app.extensions.get("db")
    assento_id = dados.get("assento_id")
    if db is None or not assento_id:
        return None
    try:
        con = db.connect()
    except Exception:  # noqa: BLE001
        return None
    try:
        return MOTOR.contexto_termo_de_assento(
            con, int(assento_id), sv=sv,
            escrevente=str(dados.get("escrevente") or ""),
            funcao=str(dados.get("funcao") or dados.get("funcao_do_escrevente") or ""),
            estilo_data=dados.get("estilo_data") or None,
            remontar=bool(dados.get("remontar")), corpo=corpo)
    except LookupError:
        return None
    finally:
        try:
            con.close()
        except Exception:  # noqa: BLE001
            pass


def _carregar_contexto_de_ids(dados: dict, sv: dict):
    """Se `dados` trouxer assento_id/certidao_id, monta do banco (só leitura)."""
    db = current_app.extensions.get("db")
    if db is None:
        return None, None
    assento_id = dados.get("assento_id")
    certidao_id = dados.get("certidao_id")
    if not assento_id and not certidao_id:
        return None, None
    try:
        con = db.connect()
    except Exception:  # noqa: BLE001
        return None, None
    try:
        certidao = {}
        if certidao_id:
            import rc_certidao as RCE
            row = RCE.ler(con, int(certidao_id))
            if row:
                certidao = dict(row)
                assento_id = assento_id or certidao.get("assento_id")
        if not assento_id:
            return None, None
        ctx = MOTOR.contexto_de_assento(
            con, assento_id=int(assento_id), certidao=certidao, sv=sv)
        return ctx, certidao
    finally:
        try:
            con.close()
        except Exception:  # noqa: BLE001
            pass


@modelos_motor_api.post("/modelos/api/previa")
def api_previa():
    body = request.get_json(silent=True) or {}
    area = str(body.get("area") or "RCPN")
    template_id = str(body.get("template_id") or body.get("template") or "")
    dados = body.get("dados") if isinstance(body.get("dados"), dict) else {}
    # ids de ato podem vir no topo ou dentro de dados
    for k in ("assento_id", "certidao_id", "escrevente", "funcao",
              "estilo_data", "remontar"):
        if body.get(k) is not None and k not in dados:
            dados[k] = body.get(k)
    papel = str(body.get("papel") or "A4")
    formato = str(body.get("formato") or "html")
    conteudo = body.get("conteudo")
    versao = body.get("versao")  # informativo: a prévia nunca grava versão
    _ = versao

    sv = _sv_do_app()
    if MOTOR.eh_template_termo(template_id, area):
        corpo = None
        if conteudo:
            import modelos_motor_termo as TERMO
            corpo = TERMO.rascunho_do_termo(
                conteudo, area=area, template_id=template_id)["corpo"]
        ctx_termo = _carregar_contexto_termo(dados, sv, corpo=corpo)
        resp = MOTOR.resposta_previa(
            area=area, template_id=template_id,
            dados=dados if ctx_termo is None else None,
            contexto=ctx_termo, sv=sv, papel=papel, formato=formato,
            conteudo=conteudo, corpo_termo=corpo)
        code = 200 if not resp.get("erros") else 422
        if any(e.get("codigo") == "FORMATO_INVALIDO" for e in resp.get("erros") or []):
            code = 400
        return jsonify(resp), code
    contexto, certidao = _carregar_contexto_de_ids(dados, sv)
    molde_bytes = None if conteudo else _molde_publicado(template_id, contexto)
    resp = MOTOR.resposta_previa(
        area=area,
        template_id=template_id,
        dados=dados if contexto is None else None,
        contexto=contexto,
        certidao=certidao,
        sv=sv,
        papel=papel,
        formato=formato,
        conteudo=conteudo,
        molde_bytes=molde_bytes,
    )
    code = 200 if not resp.get("erros") else 422
    # erros de formato inválido etc. — ainda devolve corpo do contrato
    if any(e.get("codigo") == "FORMATO_INVALIDO" for e in resp.get("erros") or []):
        code = 400
    return jsonify(resp), code


def _molde_publicado(template_id: str, contexto: dict | None):
    """Hook 2c: molde publicado do Editor, só com a flag ligada (padrão: não)."""
    import modelos_motor_versao as VERSAO
    if not VERSAO.USAR_CONTEUDO_PUBLICADO_EDITOR:
        return None
    db = current_app.extensions.get("db")
    chave = str(template_id or (contexto or {}).get("template_id") or "").upper()
    if db is None or not chave.startswith("RC_MOLDE_"):
        return None
    try:
        con = db.connect()
    except Exception:  # noqa: BLE001
        return None
    try:
        blob, _origem = VERSAO.molde_da_certidao(con, chave)
        return blob
    finally:
        try:
            con.close()
        except Exception:  # noqa: BLE001
            pass


@modelos_motor_api.get("/modelos/api/campos")
def api_campos():
    area = request.args.get("area") or ""
    tipo = request.args.get("tipo") or ""
    return jsonify(MOTOR.campos(area=area, tipo=tipo))


@modelos_motor_api.get("/modelos/api/trechos-bloqueados")
def api_trechos_bloqueados():
    area = request.args.get("area") or ""
    tipo = request.args.get("tipo") or ""
    return jsonify(MOTOR.trechos_bloqueados(area=area, tipo=tipo))


ENDPOINTS_API = (
    "modelos_motor_api.api_previa",
    "modelos_motor_api.api_campos",
    "modelos_motor_api.api_trechos_bloqueados",
)
# 2c: com login_required do app, as APIs exigem sessão (401 JSON).
EXIGIR_LOGIN_NAS_APIS = True


def _api_com_login(view, login_required):
    """Envolve a view com o `login_required` da casa; o redirect para a tela
    de login vira 401 JSON (cliente da API não segue HTML)."""
    guardada = login_required(view)

    @wraps(view)
    def protegida(*args, **kwargs):
        r = guardada(*args, **kwargs)
        codigo = getattr(r, "status_code", None)
        if codigo in (301, 302, 303, 307, 308):
            return jsonify({
                "html": None, "arquivo_base64": None, "pdf_base64": None,
                "avisos": [], "placeholders_usados": [],
                "placeholders_desconhecidos": [],
                "erros": [{"linha": 0, "coluna": 0, "codigo": "LOGIN_NECESSARIO",
                           "msg": "Entre no sistema para usar a prévia."}],
            }), 401
        return r
    protegida._motor_login = True  # noqa: SLF001 — marca para não envolver 2x
    return protegida


def registrar_rotas(app, db=None, login_required=None, roles_required=None,
                    audit=None, fmt_date=None, **_kwargs):
    """Padrão da casa: registra o blueprint no app já construído.

    2c: se `login_required` vier (app.py passa), as 3 rotas exigem login
    (401 JSON sem sessão). Sem ele (testes com Flask mínimo) ficam abertas.
    Não liga emissão nem selo.
    """
    if db is not None:
        app.extensions.setdefault("db", db)
    if "modelos_motor_api" not in app.blueprints:
        app.register_blueprint(modelos_motor_api)
    if EXIGIR_LOGIN_NAS_APIS and callable(login_required):
        for ep in ENDPOINTS_API:
            view = app.view_functions.get(ep)
            if view is not None and not getattr(view, "_motor_login", False):
                app.view_functions[ep] = _api_com_login(view, login_required)
    return modelos_motor_api
