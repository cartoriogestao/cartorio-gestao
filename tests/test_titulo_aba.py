from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import titulo_aba as TITULO


@pytest.fixture(autouse=True)
def _limpar_cache():
    TITULO._nomes_do_menu.cache_clear()
    yield
    TITULO._nomes_do_menu.cache_clear()


def test_titulos_rcpj_rtd_respeitam_atribuicao_na_aba():
    t_rtd = TITULO.sugerir("rcpj_rtd_titulos", atribuicao="4", modulo_nome="RCPJ e RTD")
    assert t_rtd.startswith("RTD")
    assert "RCPJ" not in t_rtd
    t_rcpj = TITULO.sugerir("rcpj_rtd_titulos", atribuicao="3", modulo_nome="RCPJ e RTD")
    assert t_rcpj.startswith("RCPJ")
    assert "RTD" not in t_rcpj


def test_certidoes_compartilhadas_levam_a_atribuicao():
    t = TITULO.sugerir(
        "atribuicoes_certidoes",
        atribuicao="LIVRO3",
        modulo_nome="RCPJ e RTD",
    )
    assert "Certid" in t
    assert "Livro 3" in t


def test_tela_do_menu_ganha_modulo_quando_faz_sentido():
    t = TITULO.sugerir("protesto_painel", modulo_nome="Protesto")
    assert "Roteiro" in t or "roteiro" in t.lower()
    assert "Protesto" in t

@pytest.mark.parametrize(
    "endpoint,modulo_nome,needles",
    [
        ("notas_painel", "Notas", ("Tabelionato", "Notas")),
        ("notas_reconhecimento", "Notas", ("Reconhecer", "Notas")),
        ("notas_autenticacao", "Notas", ("Autenticar", "Notas")),
        ("ri_matriculas", "Registro de Imóveis", ("Matrícula", "Registro")),
        ("ri_protocolo", "Registro de Imóveis", ("Protocolo", "Registro")),
        # «Tarefas e pendências», «Expedientes / Malote» e «Expedientes
        # prontos para encerrar» SAÍRAM DO MENU em 12/10/2026, por ordem do
        # oficial: viraram a lista única de Processos (templates/base.html,
        # grupo «Processos e malote»). A aba agora se mede nela — 14/10/2026.
        ("processos_lista", "Malote", ("Processos", "Malote")),
        ("caixa_protocolos", "Administrativo", ("Protocolo", "Administrativo")),
        ("inspections", "Malote", ("Inspe", "Malote")),
        ("nucleo_livros", "Livros e acervo", ("termos", "Livros")),
        ("nucleo_encerramento_diario", "Livros e acervo", ("Encerramento", "Livros")),
        ("atribuicoes_importar", "Livros e acervo", ("E-Ofício", "Livros")),
        ("importar_padrao_tela", "Livros e acervo", ("Importar", "Livros")),
    ],
)
def test_telas_de_alto_trafego(endpoint, modulo_nome, needles):
    t = TITULO.sugerir(endpoint, modulo_nome=modulo_nome)
    assert t
    low = t.lower()
    for part in needles:
        assert part.lower() in low
