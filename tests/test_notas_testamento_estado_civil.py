"""O estado civil do testamento público vem da parte TESTADOR.

Ensaio de atos das Notas, 03/11/2026 (docs/ensaio_de_atos/relatorio_notas.md, item 4): a escolha da
minuta começava em «solteiro», e o testador casado declarava «ser solteiro». CC art. 215, § 1º, III,
e art. 1.864, I. A prática pela tela está em `test_ensaio_de_atos_notas`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import notas_teor as NT  # noqa: E402

CASADO = {"nome": "MARIO EXEMPLO DOS SANTOS", "qualificacao": "TESTADOR", "estado_civil": "casado",
          "conjuge": "JOANA EXEMPLO DOS SANTOS", "regime_bens": "comunhão parcial de bens"}


def _tela(**mais) -> dict:
    return {"op_estado_civil_do_testador": "solteiro", **mais}


def test_o_casado_e_casado_com_o_conjuge_e_o_regime_e_o_balcao_e_avisado():
    valores = _tela()
    avisos = NT.estado_civil_do_testador(valores, [CASADO])
    assert valores["op_estado_civil_do_testador"] == "casado"
    assert valores["se_se_casado_ou_convivente"] == "1"
    assert valores["op_conjuge_ou_convivente"] == "cônjuge"
    assert valores["nome_e_qualificacao_do_conjuge_ou_convivente"] == "JOANA EXEMPLO DOS SANTOS"
    assert valores["regime_de_bens"] == "comunhão parcial de bens"
    assert avisos and "vale o da parte" in avisos[0]


def test_o_que_o_escrevente_digitou_do_conjuge_fica():
    valores = _tela(op_estado_civil_do_testador="casado",
                    nome_e_qualificacao_do_conjuge_ou_convivente="JOANA, brasileira, professora")
    assert NT.estado_civil_do_testador(valores, [CASADO]) == []
    assert valores["nome_e_qualificacao_do_conjuge_ou_convivente"] == "JOANA, brasileira, professora"


def test_a_viuva_e_viuvo_na_escolha_da_minuta_e_a_clausula_do_casado_sai():
    valores = _tela(se_se_casado_ou_convivente="1")
    NT.estado_civil_do_testador(valores, [{"qualificacao": "TESTADORA", "estado_civil": "viúva"}])
    assert valores["op_estado_civil_do_testador"] == "viúvo"
    assert valores["se_se_casado_ou_convivente"] == ""


def test_o_solteiro_em_uniao_estavel_e_convivente():
    valores = _tela()
    NT.estado_civil_do_testador(valores, [{"qualificacao": "TESTADOR", "estado_civil": "solteiro",
                                           "uniao_estavel": "SIM"}])
    assert valores["op_estado_civil_do_testador"] == "convivente em união estável"
    assert valores["op_conjuge_ou_convivente"] == "convivente"


def test_sem_testador_ou_sem_a_escolha_nada_muda():
    valores = _tela()
    assert NT.estado_civil_do_testador(valores, [{"qualificacao": "TESTEMUNHA", "estado_civil": "casado",
                                                  "testemunha": 1}]) == []
    assert valores == _tela()
    outra = {"op_forma_de_pagamento": "PIX"}
    assert NT.estado_civil_do_testador(outra, [CASADO]) == [] and outra == {"op_forma_de_pagamento": "PIX"}
