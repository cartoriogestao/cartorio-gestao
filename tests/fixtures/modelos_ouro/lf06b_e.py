"""Ouro do LF06B, parte E — frases montadas DENTRO das rotas do `ri_web`.

O comprovante de prenotação, o encerramento e o cancelamento lavrados direto
e a validade da certidão reprográfica montavam a frase numa f-string no meio
da rota, junto do banco e da sessão. A rota inteira não se chama sem o app; a
EXPRESSÃO que monta o texto, sim.

Por isso esta parte acha, na FONTE do `ri_web.py` da árvore que estiver no
`sys.path` (a de antes, no gerador; a de depois, no teste), a atribuição que
monta a frase — `teor = …` em `ri_cancelar_ato`, `corpo += …` com «VALIDADE»
em `ri_emitir_certidao`… — e a avalia com os mesmos valores de teste. Na
árvore de antes ela é a f-string; na de depois, a leitura pela base
(`ri_frases`). É a mesma chamada nas duas, e a saída tem de ser a mesma.

A conexão da rota vai como `None` (o padrão da base) e o texto já lido vai
como na rota. Contexto de teste, sem dado real de pessoa.
"""
from __future__ import annotations

import ast
from pathlib import Path


def _avaliar(funcao: str, alvo: str, marca: str, locais: dict):
    """Avalia a expressão de `alvo = …` (ou `alvo += …`) dentro de `funcao`
    que contém `marca`. `+=` devolve só o que se acrescenta."""
    import ri_web
    arvore = ast.parse(Path(ri_web.__file__).read_text(encoding="utf-8"))
    achadas = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and no.name == funcao:
            for sub in ast.walk(no):
                if isinstance(sub, ast.Assign) and len(sub.targets) == 1:
                    destino = sub.targets[0]
                elif isinstance(sub, ast.AugAssign):
                    destino = sub.target
                else:
                    continue
                if (isinstance(destino, ast.Name) and destino.id == alvo
                        and marca in ast.unparse(sub.value)):
                    achadas.append(sub.value)
    assert len(achadas) == 1, f"{funcao}: {len(achadas)} expressões de «{alvo}» com «{marca}»"
    try:
        import ri_frases                    # só existe na árvore de depois
        locais = {"ri_frases": ri_frases, **locais}
    except ImportError:
        pass
    codigo = compile(ast.Expression(achadas[0]), f"ri_web.{funcao}", "eval")
    return eval(codigo, dict(vars(ri_web)), locais)          # noqa: S307


def _lido(chave: str):
    """O texto já lido pela rota (na árvore de depois): o padrão da base."""
    try:
        import ri_frases
    except ImportError:
        return None
    return ri_frases.texto(chave)


def _data(d):
    return "/".join(reversed(str(d)[:10].split("-"))) if d else ""


def chamadas() -> dict:
    f: dict = {}
    for motivo, destino in (("Unificação com a matrícula de exemplo", ""),
                            ("Desmembramento de exemplo", "4901 e 4902"),
                            ("Motivo com <&> de exemplo", "4903")):
        f[f"ri_encerrar_matricula(teor, {motivo!r}, {destino!r})"] = (
            lambda m=motivo, d=destino: _avaliar(
                "ri_encerrar_matricula", "teor", "ENCERRAMENTO", {
                    "motivo": m, "destino": d, "_c_frases": None}))
    for rotulo, motivo in (("R-01/4901", "Requerimento de exemplo, de 19/10/2026"),
                           ("AV-12/4.901", "Ordem judicial de exemplo")):
        f[f"ri_cancelar_ato(teor, {rotulo})"] = (
            lambda r=rotulo, m=motivo: _avaliar(
                "ri_cancelar_ato", "teor", "CANCELAMENTO", {
                    "rotulo": r, "motivo": m, "_c_frases": None}))
    for hoje in ("19 de outubro de 2026", "1º de março de 2026"):
        f[f"ri_emitir_certidao(validade, {hoje})"] = (
            lambda h=hoje: _avaliar(
                "ri_emitir_certidao", "corpo", "VALIDADE", {
                    "_hoje_ext": h, "_c_frases": None}))
    prenotacoes = (
        {"prazo_suspenso_desde": "2026-10-01", "prazo_suspenso_motivo": "DUVIDA"},
        {"prazo_suspenso_desde": "2026-09-15", "prazo_suspenso_motivo": "MOTIVO_DE_EXEMPLO"},
    )
    for limite in ("30/10/2026", ""):
        for p in prenotacoes:
            f[f"ri_prenotacao_comprovante(limite, {limite!r}, {p['prazo_suspenso_motivo']})"] = (
                lambda li=limite, pr=p: _avaliar(
                    "ri_prenotacao_comprovante", "limite", "suspens", {
                        "limite": li, "p": pr, "fmt_date": _data,
                        "_modelo_suspenso": _lido("RI_PRENOTACAO_PRAZO_SUSPENSO")}))
    return f
