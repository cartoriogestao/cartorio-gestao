"""A filiação em dois campos (mãe e pai) e o nascimento, em toda parte.

Decisão do oficial, 03/11/2026 (ensaio de atos das Notas, item 15): o RCTO pedia a data de nascimento
e o nome da mãe do testador, e só a ficha de firma os tinha. A prática pela tela está em
`test_ensaio_de_atos_notas`. Os nomes são fictícios.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import notas_partes as NP  # noqa: E402
import notas_teor as NT  # noqa: E402

PARTE = {"nome": "MARIO EXEMPLO DOS SANTOS", "qualificacao": "OUTORGANTE", "tipo_pessoa": "F",
         "nacionalidade": "brasileiro", "estado_civil": "solteiro", "profissao": "comerciante",
         "documento": "00000000191", "uniao_estavel": "NAO", "endereco": "Rua Exemplo, 10"}


def test_sem_documento_a_qualificacao_diz_o_pai_e_a_mae():
    texto = NT.qualificar({**PARTE, "filiacao_pai": "JOSE EXEMPLO DOS SANTOS",
                           "filiacao_mae": "MARIA EXEMPLO DOS SANTOS"})
    assert "filho(a) de JOSE EXEMPLO DOS SANTOS e MARIA EXEMPLO DOS SANTOS" in texto
    assert "[DOCUMENTO DE IDENTIDADE OU FILIAÇÃO]" not in texto


def test_so_a_mae_tambem_e_filiacao():
    texto = NT.qualificar({**PARTE, "filiacao_mae": "MARIA EXEMPLO DOS SANTOS"})
    assert "filho(a) de MARIA EXEMPLO DOS SANTOS" in texto
    assert NT.pendencias_da_qualificacao([{**PARTE, "filiacao_mae": "MARIA"}]) == []


def test_a_filiacao_de_texto_livre_gravada_antes_continua_valendo():
    texto = NT.qualificar({**PARTE, "filiacao": "JOSE E MARIA"})
    assert "filho(a) de JOSE E MARIA" in texto


def test_o_que_se_digita_vence_o_cartao_e_a_data_invalida_fica_de_fora():
    cartao = {"filiacao_mae": "MARIA DO CARTAO", "filiacao_pai": "JOSE DO CARTAO", "nascimento_data": "1960-05-10"}
    f = NP.filiacao_e_nascimento({"filiacao_mae": " maria  digitada ", "nascimento_data": "10/05/1960"}, cartao)
    assert f == {"filiacao_mae": "MARIA DIGITADA", "filiacao_pai": "JOSE DO CARTAO",
                 "nascimento_data": "1960-05-10"}
    assert NP.filiacao_e_nascimento({"nascimento_data": "10/05/1960"})["nascimento_data"] is None


def test_o_cartao_passa_a_mae_o_pai_e_o_nascimento():
    d = NP.dados_para_parte({"nome": "MARIO", "mae": "MARIA EXEMPLO", "pai": "JOSE EXEMPLO",
                             "nascimento": "1960-05-10"})
    assert (d["filiacao_mae"], d["filiacao_pai"], d["nascimento_data"]) == ("MARIA EXEMPLO", "JOSE EXEMPLO",
                                                                         "1960-05-10")
