"""A planilha que sai da casa não leva fórmula — revisão de segurança, 26/10/2026.

Achado transversal 2: o CSV saía por `csv.writer` cru, e campo que começa com
`=`, `+`, `-` ou `@` a planilha lê como fórmula. Agora todo CSV passa por
`csv_seguro`: tudo entre aspas (`QUOTE_ALL`) e apóstrofo na frente do texto
perigoso.

O VARREDOR é `test_nenhum_csv_nasce_fora_do_helper`: `csv.writer` ou
`csv.DictWriter` cru em qualquer módulo do sistema fica vermelho aqui, e toda
rota que entrega `text/csv` tem de passar pelo helper — o CSV de amanhã nasce
neutralizado ou não nasce.
"""
from __future__ import annotations

import ast
import csv
import io
import sys
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import csv_seguro as CSVS                        # noqa: E402


# ----------------------------------------------------------- a neutralização


@pytest.mark.parametrize("perigoso", [
    '=HIPERLINK("http://exemplo.invalid";"clique")', "=1+1", "+5*2", "-2+3",
    "@SOMA(A1:A2)", "\t=1+1", "\r=1+1", "-", "=", "@mario",
])
def test_o_texto_que_vira_formula_ganha_apostrofo(perigoso):
    assert CSVS.neutralizar(perigoso) == "'" + perigoso


@pytest.mark.parametrize("numero", ["-5", "-3,50", "+12.5", "42", "-0.25"])
def test_o_texto_que_e_so_numero_continua_numero(numero):
    """`-5` não roda fórmula; virar texto estragaria a soma da coluna."""
    assert CSVS.neutralizar(numero) == numero


@pytest.mark.parametrize("valor,esperado", [
    (-5, "-5"), (3.5, "3.5"), (Decimal("-1.20"), "-1.20"), (0, "0"), (None, ""),
    (True, "True"), ("MARIO EXEMPLO", "MARIO EXEMPLO"), ("", ""),
])
def test_os_demais_valores(valor, esperado):
    assert CSVS.neutralizar(valor) == esperado


def test_o_csv_sai_todo_entre_aspas_e_relido_volta_igual_menos_o_apostrofo():
    texto = CSVS.gerar(["nome", "obs"], [["MARIO; EXEMPLO", '=1+1'],
                                         ['diz "oi"', -7]])
    assert texto.splitlines()[0] == '"nome";"obs"'
    linhas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    assert linhas == [["nome", "obs"], ["MARIO; EXEMPLO", "'=1+1"],
                      ['diz "oi"', "-7"]]


def test_o_escritor_de_dicionario_neutraliza_e_recusa_coluna_estranha():
    saida = io.StringIO()
    w = CSVS.escritor_de_dicionario(saida, ["a", "b"])
    w.writeheader()
    w.writerow({"a": "@x", "b": None})
    assert saida.getvalue().splitlines() == ['"a";"b"', '"\'@x";""']
    with pytest.raises(ValueError):
        w.writerow({"a": 1, "c": 2})


def test_a_resposta_leva_o_bom_e_o_nome(cg_app):
    with cg_app.test_request_context():
        r = CSVS.resposta("tarefas.csv", ["ID"], [["=1"]])
    assert r.mimetype == "text/csv"
    assert r.get_data(as_text=True).startswith("﻿" + '"ID"')
    assert "'=1" in r.get_data(as_text=True)
    assert 'filename="tarefas.csv"' in r.headers["Content-Disposition"]


# ------------------------------------------------------------------ o varredor

#: Telas que entregam `text/csv` montado noutro módulo — o módulo que monta é
#: quem tem de passar pelo helper.
QUEM_MONTA = {"selo_portal_web.py": "selo_portal.py",
              "produtividade_web.py": "produtividade.py"}


def _fontes() -> list[Path]:
    return sorted([*RAIZ.glob("*.py"), *RAIZ.glob("tools/*.py")])


def _chama_csv_cru(arvore: ast.AST) -> list[int]:
    linhas = []
    for no in ast.walk(arvore):
        if (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                and no.func.attr in ("writer", "DictWriter")
                and isinstance(no.func.value, ast.Name) and no.func.value.id == "csv"):
            linhas.append(no.lineno)
    return linhas


def test_nenhum_csv_nasce_fora_do_helper():
    problemas = []
    for p in _fontes():
        if p.name == "csv_seguro.py":
            continue
        texto = p.read_text(encoding="utf-8")
        for linha in _chama_csv_cru(ast.parse(texto)):
            problemas.append(f"{p.name}:{linha}: csv.writer/DictWriter cru — use csv_seguro")
        if "text/csv" in texto:
            quem = RAIZ / QUEM_MONTA.get(p.name, p.name)
            if "csv_seguro" not in quem.read_text(encoding="utf-8"):
                problemas.append(f"{p.name}: entrega text/csv sem passar por csv_seguro "
                                 f"(conferido em {quem.name})")
    assert problemas == [], "\n".join(problemas)


def test_o_varredor_pega_o_csv_cru():
    """O teste do teste."""
    fonte = "import csv\ndef f(s):\n    return csv.writer(s, delimiter=';')\n"
    assert _chama_csv_cru(ast.parse(fonte)) == [3]
