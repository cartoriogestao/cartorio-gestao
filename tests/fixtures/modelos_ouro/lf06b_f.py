"""Ouro do LF06B, parte F — o título e o fecho da certidão do Livro 3 em ODT, e o
critério «pelo bairro» da negativa de imóvel.

`atribuicoes_web._papel_da_certidao_do_livro3` monta o papel dentro da rota,
com banco e selo; o texto do título e do fecho, porém, sai de um TRECHO de
instruções da função que só usa a linha da certidão e os dados da serventia.
Esta parte acha esse trecho na fonte da árvore que estiver no `sys.path` — do
`titulo = …` até `corpo_odf = html_para_odf(titulo)`, e do `emitida = …` até
`corpo_odf += html_para_odf(fecho)` — e o executa com uma certidão de teste. Na
árvore de antes ele é a f-string; na de depois, a leitura pela base. O texto já
lido pela rota (`_modelos`) entra como o padrão da base.

O critério «pelo bairro» é uma atribuição só, na rota da negativa
(`ri_web.ri_emitir_certidao_negativa`), e vai pela mesma régua da parte E.

Contexto de teste: «FULANO DE EXEMPLO», hash de exemplo. Nenhum dado real.
"""
from __future__ import annotations

import ast
import datetime
import html
import importlib
from pathlib import Path

CHAVES_DO_LIVRO3 = ("RI_LIVRO3_CERTIDAO_TITULO", "RI_LIVRO3_CERTIDAO_CANCELADA",
                    "RI_LIVRO3_CERTIDAO_FECHO")


def _funcao(modulo: str, nome: str):
    mod = importlib.import_module(modulo)
    arvore = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    achadas = [n for n in ast.walk(arvore)
               if isinstance(n, ast.FunctionDef) and n.name == nome]
    assert len(achadas) == 1, (modulo, nome, len(achadas))
    return mod, achadas[0]


def _com_ri_frases(locais: dict) -> dict:
    try:
        import ri_frases                    # só existe na árvore de depois
    except ImportError:
        return locais
    return {"ri_frases": ri_frases,
            "_modelos": ri_frases.ler(None, *CHAVES_DO_LIVRO3), **locais}


def _trecho(modulo: str, funcao: str, de: str, ate: str, locais: dict, devolve: str):
    """Executa as instruções de `funcao` que vão da que começa por `de` até a
    que começa por `ate` (exclusive), e devolve a variável `devolve`."""
    mod, fn = _funcao(modulo, funcao)
    corpo = [ast.unparse(s) for s in fn.body]
    i = [k for k, s in enumerate(corpo) if s.startswith(de)]
    j = [k for k, s in enumerate(corpo) if s.startswith(ate)]
    assert len(i) == 1 and len(j) == 1 and i[0] < j[0], (funcao, de, ate, i, j)
    codigo = compile(ast.Module(body=fn.body[i[0]:j[0]], type_ignores=[]),
                     f"{modulo}.{funcao}", "exec")
    ambiente = {**vars(mod), **_com_ri_frases(locais)}
    exec(codigo, ambiente)                                    # noqa: S102
    return ambiente[devolve]


def _bairro(bairro: str, modo: str = "IMOVEL") -> dict:
    """A atribuição de `ids["criterio_rotulo"]` com «bairro», na rota da negativa."""
    mod, fn = _funcao("ri_web", "ri_emitir_certidao_negativa")
    achadas = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
               and ast.unparse(n.targets[0]) == "ids['criterio_rotulo']"
               and "bairro" in ast.unparse(n.value)]
    assert len(achadas) == 1, len(achadas)
    codigo = compile(ast.Expression(achadas[0].value), "ri_web.negativa", "eval")
    return eval(codigo, dict(vars(mod)),                     # noqa: S307
                _com_ri_frases({"bairro": bairro, "_c_frases": None}))


def chamadas() -> dict:
    sv = {"ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
          "serventia_titular": "FULANO DE EXEMPLO", "serventia_titulo": "Oficial"}
    base = {"numero": 7, "ano": 2026, "cancelada": 0, "motivo_cancelamento": None,
            "emitida_em": "2026-10-19T09:30:00", "validade_ate": "2026-11-18",
            "emitida_por_nome": "MARIA DE EXEMPLO",
            "emitida_por_funcao": "Escrevente Autorizada",
            "finalidade": "Instruir processo hipotético", "registro_id": 1,
            "hash_certidao": "0" * 64}
    linhas = {
        "completa": base,
        "sem finalidade nem validade": {**base, "finalidade": "", "validade_ate": None},
        "quem pela serventia": {**base, "emitida_por_nome": None, "emitida_por_funcao": None},
        "sem quem nem funcao": {**base, "emitida_por_nome": None, "emitida_por_funcao": None},
        "html no texto": {**base, "finalidade": "Uso <&> de exemplo",
                          "emitida_por_nome": "FULANO <&> DE EXEMPLO"},
        "data torta": {**base, "emitida_em": "19/10/2026"},
        "cancelada": {**base, "cancelada": 1, "motivo_cancelamento": "Erro <&> de exemplo"},
    }
    f: dict = {}
    for nome, linha in linhas.items():
        s = dict(sv) if nome != "sem quem nem funcao" else {"ri_cidade": "", "ri_uf": ""}
        locais = {"linha": linha, "s": s, "_esc": html.escape, "_date": datetime.date}
        f[f"_papel_da_certidao_do_livro3(titulo, {nome})"] = (
            lambda lo=locais: _trecho("atribuicoes_web", "_papel_da_certidao_do_livro3",
                                      "titulo = ", "corpo_odf = html_para_odf(titulo)",
                                      lo, "titulo"))
        f[f"_papel_da_certidao_do_livro3(fecho, {nome})"] = (
            lambda lo=locais: _trecho("atribuicoes_web", "_papel_da_certidao_do_livro3",
                                      "emitida = ", "corpo_odf += html_para_odf(fecho)",
                                      lo, "fecho"))
    for bairro in ("Centro", "Bairro <&> de Exemplo"):
        f[f"ri_emitir_certidao_negativa(pelo bairro, {bairro})"] = (
            lambda b=bairro: _bairro(b))
    return f
