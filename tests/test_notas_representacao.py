"""Quem comparece por outra parte vem na qualificação dela, com o instrumento.

Decisão do oficial, 03/11/2026 (ensaio de atos das Notas, item 2; CN-MA art. 798, VI e VII): «…, neste
ato representado por FULANO, conforme procuração lavrada no livro X, folha Y, do …», na qualificação
do representado. A prática pela tela está em `test_ensaio_de_atos_notas`. Os nomes são fictícios.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import notas_teor as NT  # noqa: E402

BASE = {"tipo_pessoa": "F", "nacionalidade": "brasileiro", "estado_civil": "solteiro",
        "profissao": "comerciante", "documento": "00000000191", "identidade": "1234567 SSP/MA",
        "uniao_estavel": "NAO", "endereco": "Rua Exemplo, 10"}
VENDEDOR = {**BASE, "id": 1, "nome": "MARIO EXEMPLO DOS SANTOS", "qualificacao": "VENDEDOR"}
COMPRADORA = {**BASE, "id": 2, "nome": "BEATRIZ EXEMPLO DE SOUZA", "qualificacao": "COMPRADORA"}
PROCURACAO = "procuração lavrada no livro 10, folha 20, do Tabelionato de Notas de Cidade Exemplo"


def _procurador(**mais) -> dict:
    return {**BASE, "id": 3, "nome": "CARLOS EXEMPLO PROCURADOR", "qualificacao": "PROCURADOR",
            "representa_parte_id": 1, "representa_instrumento": PROCURACAO, **mais}


def test_o_procurador_vem_na_qualificacao_do_vendedor_com_a_procuracao():
    outorgantes, outorgados = NT.partes_por_lado([VENDEDOR, COMPRADORA, _procurador()],
                                                 tipo_ato="ESCRITURA")
    assert ", neste ato representado(a) por <b>CARLOS EXEMPLO PROCURADOR</b>" in outorgantes
    assert outorgantes.endswith("conforme " + PROCURACAO)
    assert outorgantes.count("CARLOS") == 1 and "CARLOS" not in outorgados
    assert "[" not in outorgantes.split("CARLOS")[1]


def test_sem_o_instrumento_ele_fica_marcado():
    outorgantes, _ = NT.partes_por_lado([VENDEDOR, COMPRADORA, _procurador(representa_instrumento="")],
                                        tipo_ato="ESCRITURA")
    assert "[INSTRUMENTO DA REPRESENTAÇÃO" in outorgantes


def test_sem_dizer_quem_representa_ele_continua_marcado_fora_dos_lados():
    outorgantes, _ = NT.partes_por_lado([VENDEDOR, COMPRADORA, _procurador(representa_parte_id=None)],
                                        tipo_ato="ESCRITURA")
    assert "DIGA JUNTO DE QUEM REPRESENTA" in outorgantes and "neste ato" not in outorgantes


def test_a_assistente_assiste():
    mae = {**BASE, "id": 3, "nome": "JOANA EXEMPLO DOS SANTOS", "qualificacao": "ASSISTENTE",
           "representa_parte_id": 2, "representa_instrumento": "certidão de nascimento lavrada no livro A-1"}
    _, outorgados = NT.partes_por_lado([VENDEDOR, COMPRADORA, mae], tipo_ato="ESCRITURA")
    assert ", neste ato assistido(a) por <b>JOANA EXEMPLO DOS SANTOS</b>" in outorgados


def test_quem_assina_a_rogo_nao_representa_e_nao_pede_instrumento():
    rogo = {**BASE, "id": 3, "nome": "PAULO EXEMPLO TESTEMUNHA", "qualificacao": "ASSINA A ROGO",
            "representa_parte_id": 1}
    outorgantes, _ = NT.partes_por_lado([VENDEDOR, COMPRADORA, rogo], tipo_ato="ESCRITURA")
    assert "assinando a seu rogo <b>PAULO EXEMPLO TESTEMUNHA</b>" in outorgantes
    assert "representado" not in outorgantes and "[INSTRUMENTO" not in outorgantes


def test_parte_de_outro_ato_ou_ela_mesma_nao_conta():
    assert NT.representantes_por_parte([VENDEDOR, _procurador(representa_parte_id=99)]) == {}
    assert NT.representantes_por_parte([_procurador(id=1, representa_parte_id=1)]) == {}
