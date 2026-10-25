"""Pontes para montar corpo de certidao RI (Livro 2) fora do request HTTP."""
from __future__ import annotations
from typing import Any, Callable

from bd_nativo import banco

_contexto_ficha: Callable[..., dict] | None = None
_corpo_certidao: Callable[..., str] | None = None
_app = None
_data_dir = None


def registrar(*, contexto_ficha, corpo_certidao) -> None:
    global _contexto_ficha, _corpo_certidao
    _contexto_ficha = contexto_ficha
    _corpo_certidao = corpo_certidao


def pronto() -> bool:
    return _contexto_ficha is not None and _corpo_certidao is not None


def garantir_registrado(data_dir) -> None:
    global _app, _data_dir
    _data_dir = str(data_dir)
    if pronto() and _app is not None:
        return
    from app import create_app
    _app = create_app({"TESTING": True, "DATA_DIR": _data_dir, "WTF_CSRF_ENABLED": False})


def montar_corpo(matricula_id: int, tipo: str, *, certidao_numero: int | None = None, data_dir=None) -> str:
    if data_dir is not None:
        garantir_registrado(data_dir)
    if not pronto() or _app is None:
        raise RuntimeError("Emissao RI ainda nao registrou contexto/corpo.")
    with _app.test_request_context():
        ctx = _contexto_ficha(int(matricula_id), para_odt=False)
        if certidao_numero is not None:
            ctx = dict(ctx, certidao_numero=int(certidao_numero))
        return _corpo_certidao(str(tipo).strip().upper(), ctx)


def previa_no_app_vivo(matricula_id: int, tipo: str) -> str:
    """O corpo que a certidão teria HOJE, montado no servidor vivo — para a
    tela de aprovação do pedido do ONR (25/10/2026). NÃO numera, não grava,
    não sela: é a mesma montagem da emissão (`corpo_certidao` sobre o
    `contexto_ficha`), dentro da requisição que já está em curso. Fora de uma
    requisição, recusa (não abre app novo)."""
    from flask import has_request_context
    if not pronto() or not has_request_context():
        raise RuntimeError("A prévia da certidão só se monta dentro do servidor vivo.")
    ctx = _contexto_ficha(int(matricula_id), para_odt=False)
    return _corpo_certidao(str(tipo).strip().upper(), ctx)


def painel_do_onus_no_app_vivo(matricula_id: int, data_dir) -> dict:
    """O quadro da decisão do ônus (`ri_onus_ia.painel`) para a aprovação do
    pedido do ONR — com os MESMOS ônus vigentes e proprietários que a emissão
    confere (`contexto_ficha`). Só LÊ; recusa fora do servidor vivo."""
    from pathlib import Path

    from flask import current_app, has_request_context

    import ri_onus_ia as RONIA
    if not pronto() or not has_request_context():
        raise RuntimeError("O quadro do ônus só se monta dentro do servidor vivo.")
    ctx = _contexto_ficha(int(matricula_id), para_odt=False)
    with current_app.extensions["db"].connect() as con:
        return RONIA.painel(con, int(matricula_id), ctx.get("onus") or [], Path(data_dir),
                            proprietarios_cadastro=ctx.get("proprietarios") or [])


def teor_precisa_remontar_modelo(corpo: str | None) -> bool:
    if not corpo or len(corpo) < 200:
        return True
    if "Certidao de ensaio" in corpo or "Certid\u00e3o de ensaio" in corpo:
        return True
    if "ensaio-acervo-v220" in corpo and "CERTID" not in corpo.upper():
        return True
    if "SANDBOX ENSAIO RI CERTIDAO" in corpo:
        return True
    return False


def remontar_corpo_gravado(con, certidao_id: int, *, data_dir, agora: str) -> dict[str, Any]:
    from ri_schema import hash_certidao
    garantir_registrado(data_dir)
    row = banco(con).um("SELECT * FROM ri_certidoes WHERE id=%s", (int(certidao_id),))
    if not row:
        raise ValueError("Certidao nao encontrada.")
    linha = dict(row)
    if str(linha.get("fonte_corpo") or "TEXTO").upper() != "TEXTO":
        return {"certidao_id": int(certidao_id), "atualizado": False, "motivo": "digitalizacao"}
    tipo = str(linha["tipo"])
    # A CERTIDÃO DE ÔNUS ESCOLHIDA NO BALCÃO NÃO SE REMONTA (13/10/2026): o que
    # ela transcreve foi escolhido por quem a emitiu, e remontar pela ficha
    # trocaria a escolha pelo padrão do sistema.
    if tipo.upper() == "ONUS" and str(linha.get("onus_escolhido_por") or "") == "BALCAO":
        return {"certidao_id": int(certidao_id), "atualizado": False,
                "motivo": "onus escolhido no balcao"}
    # A DOMINIAL E A VINTENÁRIA TAMBÉM NÃO (14/10/2026): as matrículas de
    # origem e os anos foram escolhidos no balcão e só ficaram no corpo —
    # remontar pela ficha trocaria a escolha pelo padrão (20 anos; a origem
    # seguida pelo registro anterior), e a 394/2026 perderia a 2548.
    if tipo.upper() in ("DOMINIAL", "VINTENARIA"):
        return {"certidao_id": int(certidao_id), "atualizado": False,
                "motivo": "cadeia escolhida no balcao"}
    matricula_id = int(linha["matricula_id"])
    numero = int(linha["numero"])
    ano = int(linha["ano"])
    matricula_numero = str(linha["matricula_numero"] or "")
    corpo = montar_corpo(matricula_id, tipo, certidao_numero=numero, data_dir=data_dir)
    data_emissao = str(linha["data_emissao"] or agora[:10])
    h = hash_certidao(numero, ano, tipo, matricula_numero, corpo, data_emissao)
    banco(con).escrever("UPDATE ri_certidoes SET corpo=%s, hash_certidao=%s WHERE id=%s",
                        (corpo, h, int(certidao_id)))
    return {"certidao_id": int(certidao_id), "atualizado": True, "corpo_len": len(corpo)}
