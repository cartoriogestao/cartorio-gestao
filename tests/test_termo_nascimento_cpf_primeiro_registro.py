"""Termo de NASCIMENTO: CPF do registrado e «primeiro registro» DENTRO do teor.

Pedido do oficial, 09/10/2026: «ADICIONAR O CPF SEM AVERBACAO E O PRIMEIRO
REGISTRO». Vale para o termo que se lavra daqui para a frente; teor ja gravado
nao muda, e o acervo nao ganha frase que o papel assinado nao tem.
"""
from __future__ import annotations

import rc_modelos_do_livro as LIVRO
from test_rc_folha_tela import casa, _con, _abrir, _nascimento  # noqa: F401

SV = {"ri_cidade": "Cidade Exemplo", "ri_uf": "MA", "estado": "Maranhão"}


def _assento(**extra):
    a = {"id": 1, "especie": "NASCIMENTO", "origem": "MANUAL", "nome": "MARIA TESTE",
         "data_ato": "2026-10-09", "data_fato": "2026-10-06",
         "naturalidade_declarada": "Imperatriz/MA", "cpf_registrado": "00000004855"}
    a.update(extra)
    return a


def _pessoas(sexo="F"):
    return [{"papel": "REGISTRADO", "nome": "MARIA TESTE", "sexo": sexo},
            {"papel": "DECLARANTE", "nome": "JOAO TESTE"},
            {"papel": "MAE", "nome": "ANA TESTE", "sexo": "F"}]


def _montar(assento, pessoas):
    return LIVRO.montar_do_assento(assento, pessoas, sv=SV, escrevente="Fulana",
                                   funcao_do_escrevente="Escrevente Autorizada")["texto"]


def test_catalogo_e_formulario_batem():
    assert LIVRO.conferir("NASCIMENTO") == []


def test_cpf_presente_entra_no_teor_com_primeiro_registro():
    t = _montar(_assento(), _pessoas("F"))
    assert ("Trata-se de primeiro registro. Inscrita no CPF n.º 000.000.048-55. "
            "Lido e achado conforme") in t
    t = _montar(_assento(), _pessoas("M"))
    assert "Inscrito no CPF n.º 000.000.048-55." in t


def test_cpf_ausente_nao_deixa_traco_nem_frase():
    t = _montar(_assento(cpf_registrado=""), _pessoas())
    assert "CPF" not in t
    assert "Trata-se de primeiro registro. Lido e achado conforme" in t
    assert "____________ Lido" not in t


def test_acervo_e_natimorto_nao_ganham_primeiro_registro():
    for extra in ({"origem": "EOFICIO"}, {"origem": "ACERVO"}, {"especie": "NATIMORTO"}):
        assert "primeiro registro" not in _montar(_assento(**extra), _pessoas())


def test_teor_digitado_ganha_as_frases_uma_vez_so():
    digitado = ("A naturalidade declarada é de Imperatriz/MA, local do nascimento. "
                "Lido e achado conforme, o(a) declarante assina. Eu, Fulana, dou fé.")
    novo = LIVRO.completar_teor_nascimento(digitado, cpf="000.000.048-55", sexo="F")
    assert ("local do nascimento. Trata-se de primeiro registro. Inscrita no CPF "
            "n.º 000.000.048-55. Lido e achado conforme") in novo
    assert LIVRO.completar_teor_nascimento(novo, cpf="00000004855", sexo="F") == novo
    so_primeiro = LIVRO.completar_teor_nascimento(digitado, cpf="", sexo="F")
    assert "Trata-se de primeiro registro. Lido" in so_primeiro and "CPF" not in so_primeiro
    sem_ancora = "Texto proprio sem o fecho da casa."
    assert LIVRO.completar_teor_nascimento(sem_ancora, cpf="00000004855") == sem_ancora


def test_teor_ja_gravado_nao_muda_na_folha(casa):
    gravado = ("Teor congelado de teste. Lido e achado conforme, o(a) declarante "
               "assina. Eu, Fulana, dou fé e assino.")
    aid = _nascimento(casa, teor=gravado, cpf_registrado="00000004855")
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert "Teor congelado de teste." in html
    assert "primeiro registro" not in html
    assert "000.000.048-55" not in html
