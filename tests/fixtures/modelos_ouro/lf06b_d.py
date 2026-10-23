"""Ouro do LF06B, parte D — os fechos do ato e da abertura da matrícula (`ri_web`).

`fecho_do_ato` e `fecho_da_abertura` moram DENTRO de `ri_web.registrar_rotas`
(são usados pela ficha), e por isso não se importam. Mas não pegam nada da
rota — só o que é do módulo (`re`, `date`, `data_por_extenso`) —, e o ouro os
alcança pelo objeto de código guardado na função de fora: a MESMA função, sem
rota nem banco, na árvore de antes e na de depois.

Contexto de teste: «FULANO DE EXEMPLO», «Cidade Exemplo». Nenhum dado real.
"""
from __future__ import annotations

import types


def _de_dentro_das_rotas(nome: str):
    """A função `nome` de dentro de `ri_web.registrar_rotas`, montada com os
    globais do módulo. Os padrões dos argumentos (todos `None`) moram no
    objeto da função, e não no código: repõem-se aqui."""
    import ri_web
    for k in ri_web.registrar_rotas.__code__.co_consts:
        if isinstance(k, types.CodeType) and k.co_name == nome:
            assert not k.co_freevars, f"{nome} passou a depender da rota: {k.co_freevars}"
            f = types.FunctionType(k, ri_web.__dict__, nome)
            obrigatorios = 4
            f.__defaults__ = (None,) * (k.co_argcount - obrigatorios)
            nomeados = k.co_varnames[k.co_argcount:k.co_argcount + k.co_kwonlyargcount]
            f.__kwdefaults__ = {n: None for n in nomeados}
            return f
    raise LookupError(nome)


def chamadas() -> dict:
    ato = lambda **k: _de_dentro_das_rotas("fecho_do_ato")(  # noqa: E731
        "Cidade Exemplo", "MA", **k)
    abertura = lambda **k: _de_dentro_das_rotas("fecho_da_abertura")(  # noqa: E731
        "Cidade Exemplo", "MA", **k)
    f: dict = {
        "fecho_do_ato(com titulo, O)": lambda: ato(
            data_iso="2026-10-19", teor="R-1 TEOR DE EXEMPLO.", nome="FULANO DE EXEMPLO",
            titulo="Oficial Registrador", tratamento="O"),
        "fecho_do_ato(com titulo, A)": lambda: ato(
            data_iso="2026-03-01", teor="AV-2 TEOR DE EXEMPLO.", nome="MARIA DE EXEMPLO",
            titulo="Tabeliã Registradora Substituta", tratamento="A"),
        "fecho_do_ato(sem tratamento)": lambda: ato(
            data_iso="2026-10-19", teor="", nome="FULANO DE EXEMPLO", titulo="Escrevente"),
        "fecho_do_ato(sem titulo)": lambda: ato(
            data_iso="2026-12-31", teor=None, nome="FULANO DE EXEMPLO"),
        "fecho_do_ato(teor ja diz dou fe)": lambda: ato(
            data_iso="2026-10-19", teor="R-1 TEOR. Dou fé. FULANO.", nome="FULANO DE EXEMPLO",
            titulo="Oficial"),
        "fecho_do_ato(sem nome)": lambda: ato(data_iso="2026-10-19", teor="R-1"),
        "fecho_do_ato(sem data)": lambda: ato(data_iso=None, teor="R-1", nome="FULANO"),
        "fecho_do_ato(data torta)": lambda: ato(data_iso="19/10/2026", teor="R-1",
                                                nome="FULANO"),
        "fecho_do_ato(caracteres de html)": lambda: ato(
            data_iso="2026-10-19", teor="", nome="FULANO <&> DE EXEMPLO",
            titulo="Oficial & Registrador"),
    }
    for tipo in ("ESTRUTURADA", "ACERVO", None):
        for teor in ("Teor de exemplo. Dou fé. ________ FULANO.", "Teor de exemplo.", None):
            f[f"fecho_da_abertura({tipo}, {teor!r}, com nome e titulo)"] = (
                lambda t=tipo, te=teor: abertura(
                    data_iso="2026-10-19", teor=te, nome="FULANO DE EXEMPLO",
                    titulo="Escrevente Autorizado", tratamento="O", tipo_ficha=t))
    f["fecho_da_abertura(sem nome)"] = lambda: abertura(
        data_iso="2026-10-19", teor="Teor.", tipo_ficha="ESTRUTURADA")
    f["fecho_da_abertura(sem titulo)"] = lambda: abertura(
        data_iso="2026-10-19", teor="Teor.", nome="FULANO DE EXEMPLO",
        tipo_ficha="ESTRUTURADA")
    f["fecho_da_abertura(sem data)"] = lambda: abertura(
        data_iso=None, teor="Teor.", nome="FULANO DE EXEMPLO", titulo="Oficial",
        tipo_ficha="ESTRUTURADA")
    f["fecho_da_abertura(data torta)"] = lambda: abertura(
        data_iso="ontem", teor="Teor.", nome="FULANO DE EXEMPLO", titulo="Oficial",
        tipo_ficha="ESTRUTURADA")
    return f
