"""O advogado assiste e não é parte; o «DOS ADVOGADOS» é montado dele, com a OAB.

Decisão do oficial, 03/11/2026 (ensaio de atos das Notas, item 5). A prática pela tela está em
`test_ensaio_de_atos_notas`. Os nomes são fictícios.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import notas_teor as NT  # noqa: E402

BASE = {"tipo_pessoa": "F", "nacionalidade": "brasileiro", "estado_civil": "solteiro",
        "profissao": "advogado", "documento": "00000000191", "identidade": "1234567 SSP/MA",
        "uniao_estavel": "NAO", "endereco": "Rua Exemplo, 10"}
HERDEIRA = {**BASE, "id": 1, "nome": "ANA EXEMPLO HERDEIRA", "qualificacao": "HERDEIRA"}
ADVOGADO = {**BASE, "id": 2, "nome": "CARLOS EXEMPLO ADVOGADO", "qualificacao": "ADVOGADO",
            "oab_numero": "00000", "oab_uf": "ma"}


def test_o_advogado_fica_fora_das_partes_e_vem_no_paragrafo_dele():
    ctx = NT.contexto_jinja_partes([HERDEIRA, ADVOGADO])
    assert "CARLOS" not in ctx["outorgantes"] and "CARLOS" not in ctx["outorgados"]
    assert ctx["advogados"].startswith("<b>CARLOS EXEMPLO ADVOGADO</b>")
    assert ctx["advogados"].endswith(", inscrito(a) na OAB/MA sob o nº 00000")


def test_sem_a_oab_ela_fica_marcada():
    ctx = NT.contexto_jinja_partes([HERDEIRA, {**ADVOGADO, "oab_numero": ""}])
    assert "[INSCRIÇÃO NA OAB" in ctx["advogados"]


def test_sem_advogado_o_paragrafo_pede_um():
    assert NT.contexto_jinja_partes([HERDEIRA])["advogados"].startswith("[ADVOGADO")


def test_a_advogada_tambem():
    assert NT.lado_da_parte({"qualificacao": "Advogada"}) == NT.ADVOGADO
