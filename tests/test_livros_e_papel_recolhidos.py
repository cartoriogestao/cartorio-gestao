"""Livros e termos, e folhas de segurança, no layout novo: o que espera vem aberto, e o resto fica recolhido.

Estes testes montam o molde de verdade sobre uma moldura vazia, e por isso não dependem de banco. O layout antigo
continua com a forma de sempre, e as duas molduras mandam os mesmos campos.
"""
from __future__ import annotations

import re
from pathlib import Path

import jinja2
import pytest

RAIZ = Path(__file__).resolve().parents[1]


def _montar(molde: str, **contexto) -> str:
    env = jinja2.Environment(autoescape=True, loader=jinja2.ChoiceLoader([
        jinja2.DictLoader({"base.html": "{% block content %}{% endblock %}", "_serventia.html": ""}),
        jinja2.FileSystemLoader(str(RAIZ / "templates"))]))
    return env.get_template(molde).render(url_for=lambda rota, **_: f"/{rota}", csrf_token="t", **contexto)


def _campos(html: str) -> list[str]:
    return sorted(re.findall(r'<(?:input|select|textarea)\b[^>]*\bname="([^"]+)"', html))


def _quadro(html: str, ident: str) -> str:
    m = re.search(rf'<details class="panel cg-quadro" id="{ident}"[^>]*>', html)
    assert m, f"o quadro {ident} sumiu"
    return m.group(0)


def _papel(novo=True, procurada="", busca="", pagina=1, acabou=False, papel="ADMIN"):
    return _montar(
        "rcpn_papel.html", layout_novo=novo, user={"role": papel},
        quadro={"acabou": acabou, "acabando": False, "em_branco": 10, "usadas": 2, "inutilizadas": 1, "piso": 5,
                "proxima": "7225136"},
        caixas=[{"id": 1, "recebida_em": "2026-10-01", "fornecedor": "F", "serie": "HA", "codigo_de": 1, "codigo_ate": 9,
                 "quantas": 9, "restam": 3, "nota_fiscal": ""}],
        inutilizadas=[{"codigo": "1", "inutilizada_em": "", "inutilizada_por": "", "inutilizada_motivo": "borrada"}],
        procurada=procurada, folha=None, caminho=[],
        pagina_usadas={"total": 2, "busca": busca, "pagina": pagina, "paginas": 3}, usadas=[])


def _livros(novo=True, sem_livro=True, papel="ADMIN"):
    linha = {"atribuicao": 1, "nome": "Livro de Exemplo", "serie": "EX", "diario": False, "livro_id": None if sem_livro else 7,
             "livro_numero": 1, "dia": None, "folha_livre": 1, "folhas": 200, "proximo_numero": 1, "livros": 1, "atos": 0}
    outra = {**linha, "atribuicao": 2, "serie": "EY", "livro_id": 8}
    return _montar(
        "nucleo_livros.html", layout_novo=novo, user={"role": papel}, atrasados={}, series={"EX": {"nome": "Exemplo"}},
        atribuicoes={1: {"nome": "Notas"}, 2: {"nome": "Registro Civil"}}, linhas=[linha, outra],
        exigencias={"EX": ["Termo de abertura"]}, fechados=[])


@pytest.mark.parametrize("montar", [_papel, _livros])
def test_as_duas_molduras_mandam_os_mesmos_campos(montar):
    assert _campos(montar(novo=True)) == _campos(montar(novo=False))


@pytest.mark.parametrize("montar", [_papel, _livros])
def test_o_layout_antigo_nao_tem_quadro_nem_script(montar):
    html = montar(novo=False)
    assert "cg-quadro" not in html and "<script" not in html


def test_a_folha_estragou_vem_aberta_e_o_resto_recolhido():
    html = _papel()
    assert " open" in _quadro(html, "papel-estragou")
    for ident in ("papel-caixa", "papel-caixas", "papel-inutilizadas", "caminho", "usadas", "papel-como"):
        assert " open" not in _quadro(html, ident), ident


def test_sem_folha_em_branco_a_caixa_abre_sozinha():
    assert " open" in _quadro(_papel(acabou=True), "papel-caixa")


def test_procurar_e_buscar_voltam_com_o_quadro_aberto():
    assert " open" in _quadro(_papel(procurada="7225136"), "caminho")
    assert " open" in _quadro(_papel(busca="Ana Exemplo"), "usadas")
    assert " open" in _quadro(_papel(pagina=2), "usadas")


def test_o_balcao_nao_ve_o_quadro_da_caixa():
    assert 'id="papel-caixa"' not in _papel(papel="USER")


def test_o_titulo_das_caixas_diz_quantas_restam():
    assert "restam 3 folha(s)" in _papel()


def test_a_atribuicao_com_serie_sem_livro_abre_sozinha():
    html = _livros()
    assert " open" in _quadro(html, "livros-1") and "1 sem livro aberto" in html
    assert " open" not in _quadro(html, "livros-2") and "todas com livro aberto" in html


def test_com_todos_os_livros_abertos_nenhum_quadro_vem_aberto():
    html = _livros(sem_livro=False)
    assert " open" not in _quadro(html, "livros-1") and " open" not in _quadro(html, "livros-2")


def test_o_macro_e_o_mesmo_das_outras_telas():
    fonte = (RAIZ / "templates" / "_quadros_recolhidos.html").read_text(encoding="utf-8")
    assert 'document.addEventListener("invalid"' in fonte
