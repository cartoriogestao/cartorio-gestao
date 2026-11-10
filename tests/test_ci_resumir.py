"""O comentário de falha da CI (ci/suite/resumir.py): agrupa pela causa, sem IA."""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ci" / "suite"))

import resumir as R  # noqa: E402

SEMENTE = "AssertionError: a semente da gestão falhou em 1 parte(s):\n  Traceback ..."


def _junit(casos: list[tuple[str, str, str]]) -> str:
    corpo = "".join(
        f'<testcase classname="tests.{arq}" name="{nome}"><{marca} message="{msg}">detalhe</{marca}></testcase>'
        for arq, nome, (marca, msg) in ((a, n, m) for a, n, m in casos))
    return f'<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite>{corpo}</testsuite></testsuites>'


def test_as_294_quedas_de_uma_causa_so_viram_um_grupo(tmp_path):
    casos = [("test_layout_fichas_notas", f"t{i}", ("error", SEMENTE.split("\n")[0])) for i in range(294)]
    casos += [("test_funcao_sem_tela", "t", ("failure", "AssertionError: estas funções não têm caminho"))]
    (tmp_path / "junit.xml").write_text(_junit(casos), encoding="utf-8")
    (tmp_path / "situacao.txt").write_text("codigo=1 295 failed", encoding="utf-8")
    texto = R.comentario(tmp_path)
    assert "**295 teste(s) caíram, por 2 causa(s) distinta(s):**" in texto
    assert "**294×** `ERRO: AssertionError: a semente da gestão falhou em <n> parte(s):`" in texto
    assert "e mais 291" in texto
    assert texto.index("294×") < texto.index("1×")


def test_numeros_diferentes_na_mesma_frase_sao_a_mesma_causa():
    assert R.assinatura("['/rcpj-rtd/2: estoura 139 px (página 1)']") == \
        R.assinatura("['/rcpj-rtd/2: estoura 14 px (página 1)']")
    assert R.assinatura("assert 1050 == 1000") != R.assinatura("assert troco == 1000")


def test_caminho_temporario_e_hex_nao_separam_grupos():
    a = R.assinatura("AcaoBloqueada: '/var/folders/yc/abc/T/cg_pdf_x1' em 0x7f00aa")
    b = R.assinatura("AcaoBloqueada: '/private/var/folders/zz/T/cg_pdf_y2' em 0x7f00bb")
    assert a == b


def test_xml_com_doctype_ou_entidade_e_recusado(tmp_path):
    malicioso = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]>'
                 '<testsuites><testsuite><testcase classname="c" name="n"><failure message="&a;"/>'
                 '</testcase></testsuite></testsuites>')
    (tmp_path / "junit.xml").write_text(malicioso, encoding="utf-8")
    assert R.falhas_do_junit(tmp_path / "junit.xml") == []


def test_xml_quebrado_ou_ausente_nao_derruba(tmp_path):
    assert R.falhas_do_junit(tmp_path / "junit.xml") == []
    (tmp_path / "junit.xml").write_text("<testsuites><testcase", encoding="utf-8")
    assert R.falhas_do_junit(tmp_path / "junit.xml") == []
    texto = R.comentario(tmp_path)
    assert "a falha foi da infraestrutura" in texto


def test_o_texto_do_pr_nao_fecha_o_bloco_de_codigo(tmp_path):
    (tmp_path / "suite.log").write_text("E       ``` fim do bloco\nE       </sub><b>x</b>\n", encoding="utf-8")
    texto = R.comentario(tmp_path)
    assert texto.count("```") == 2  # só a abertura e o fechamento do próprio comentário


def test_sem_rede_nem_ia():
    fonte = (RAIZ / "ci" / "suite" / "resumir.py").read_text(encoding="utf-8")
    assert "urllib" not in fonte and "11434" not in fonte and "ollama" not in fonte.lower()
