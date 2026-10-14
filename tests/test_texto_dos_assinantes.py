# -*- coding: utf-8 -*-
"""Assinantes do fecho vêm das partes qualificadas no formulário."""
import notas_teor as NT
from ri_modelos_atos import preencher as preencher_modelo


def test_texto_dos_assinantes_nome_e_condicao():
    partes = [
        {"nome": "Sonia Maria", "qualificacao": "Divorcianda", "testemunha": 0},
        {"nome": "Egnaldo Feitosa", "qualificacao": "Divorciando", "testemunha": 0},
        {"nome": "Pedro Testemunha", "qualificacao": "", "testemunha": 1},
    ]
    texto = NT.texto_dos_assinantes(partes)
    assert texto == (
        "SONIA MARIA, Divorcianda; EGNALDO FEITOSA, Divorciando; "
        "PEDRO TESTEMUNHA, Testemunha"
    )


def test_texto_dos_assinantes_sem_partes_fica_vazio():
    assert NT.texto_dos_assinantes([]) == ""


def test_preencher_fecho_com_chave_dos_assinantes():
    corpo = (
        "Nada mais. Assinam o ato "
        "[ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé."
    )
    partes = [
        {"nome": "Ana", "qualificacao": "Outorgante", "testemunha": 0},
        {"nome": "Beto", "qualificacao": "Outorgado", "testemunha": 0},
    ]
    valores = {NT.CHAVE_ASSINANTES: NT.texto_dos_assinantes(partes)}
    saida = preencher_modelo({"corpo": corpo}, valores)
    assert "[ASSINANTES" not in saida
    assert "ANA, Outorgante; BETO, Outorgado" in saida
