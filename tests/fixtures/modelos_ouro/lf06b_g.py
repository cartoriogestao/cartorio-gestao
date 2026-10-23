"""Ouro do LF06B, parte G — a parte fixa das minutas de ato (`ri_web`).

`_contexto_modelo` (o preenchimento do modelo na ficha) e `ri_aplicar_modelo`
(o teor sugerido na lavratura) montam, cada um com a sua cópia, a frase do
protocolo e a do imóvel que entram nas minutas de `ri_modelos_atos`. As duas
moram dentro das rotas e leem o banco; a EXPRESSÃO de cada frase, não.

Esta parte acha, na fonte da árvore que estiver no `sys.path`, a expressão de
`protocolo_frase` e de `area_frase` em cada função — o valor no dicionário (a
árvore de antes) ou a atribuição à variável de mesmo nome (a de depois) — e a
avalia com uma matrícula e uma prenotação de teste. Nenhum dado real.
"""
from __future__ import annotations

import ast
from pathlib import Path


def _expressao(funcao: str, nome: str):
    import ri_web
    arvore = ast.parse(Path(ri_web.__file__).read_text(encoding="utf-8"))
    fn = [n for n in ast.walk(arvore) if isinstance(n, ast.FunctionDef) and n.name == funcao]
    assert len(fn) == 1, (funcao, len(fn))
    achadas = []
    for no in ast.walk(fn[0]):
        if (isinstance(no, ast.Assign) and len(no.targets) == 1
                and isinstance(no.targets[0], ast.Name) and no.targets[0].id == nome):
            achadas.append(no.value)
        elif isinstance(no, ast.Dict):
            for k, v in zip(no.keys, no.values):
                if (isinstance(k, ast.Constant) and k.value == nome
                        and not isinstance(v, ast.Name)):
                    achadas.append(v)
    assert len(achadas) == 1, (funcao, nome, len(achadas))
    return ri_web, compile(ast.Expression(achadas[0]), f"ri_web.{funcao}", "eval")


def _avaliar(funcao: str, nome: str, locais: dict):
    mod, codigo = _expressao(funcao, nome)
    try:
        import ri_frases                    # só existe na árvore de depois
        locais = {"ri_frases": ri_frases, **locais}
    except ImportError:
        pass
    return eval(codigo, dict(vars(mod)), locais)              # noqa: S307


def _data(d):
    return "/".join(reversed(str(d)[:10].split("-"))) if d else ""


def chamadas() -> dict:
    matriculas = {
        "com logradouro e area": {"logradouro": "Rua de Exemplo, 100", "area_valor": "360,00",
                                  "area_unidade": "m²"},
        "area sem unidade": {"logradouro": "Lote de Exemplo", "area_valor": "2,5",
                             "area_unidade": None},
        "sem area": {"logradouro": "Rua de Exemplo, 100", "area_valor": None,
                     "area_unidade": "m²"},
        "sem logradouro": {"logradouro": "", "area_valor": None, "area_unidade": None},
    }
    protocolos = {"aberta": {"numero": 11546, "data_prenotacao": "2026-09-23"},
                  "sem prenotacao": None}
    f: dict = {}
    for funcao in ("_contexto_modelo", "ri_aplicar_modelo"):
        for nome, m in matriculas.items():
            f[f"{funcao}(area_frase, {nome})"] = (
                lambda fn=funcao, mm=m: _avaliar(fn, "area_frase", {
                    "m": mm, "_c_frases": None}))
        for nome, p in protocolos.items():
            f[f"{funcao}(protocolo_frase, {nome})"] = (
                lambda fn=funcao, pp=p: _avaliar(fn, "protocolo_frase", {
                    "protocolo": pp, "fmt_date": _data, "_c_frases": None}))
    return f
