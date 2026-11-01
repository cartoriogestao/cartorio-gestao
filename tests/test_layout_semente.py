"""A casa de ensaio alcança toda rota com número no endereço.

O QUE DEFENDE
    Varredura que não abre a ficha passa sem tê-la visto. Aqui: toda rota de leitura com número
    tem semente, ou está em `SEM_SEMENTE` com o motivo; e o que a semente anotou abre de verdade.

`CG_LAYOUT_AREAS=ri` olha só uma área, e é como se trabalha numa semente.
"""
from __future__ import annotations

import pytest

from layout_casa import area_da_regra, areas_pedidas, casa, sem_semente  # noqa: F401
import layout_ensaio as E

pytestmark = pytest.mark.lento


def test_a_casa_nao_depende_da_hora_em_que_roda(casa):  # noqa: F811
    """O aviso de fechar o caixa cobre a tela, e a casa fica com o caixa aberto: de tarde, nada se clicava."""
    import caixa_aviso as CA
    assert CA.fim_do_expediente(casa.db.get_setting(CA.CHAVE_FIM, CA.FIM_PADRAO)) == (23, 59)


def test_toda_rota_com_numero_tem_semente(casa):  # noqa: F811
    semeadas = {endpoint for endpoint, _ in casa.paginas}
    fora = sem_semente()
    areas = areas_pedidas()
    faltam = sorted(f"{r.rule}  ({r.endpoint})" for r in E.regras_de_leitura(casa.app)
                    if r.arguments and area_da_regra(r.rule) in areas
                    and r.endpoint not in semeadas and r.endpoint not in fora)
    assert not faltam, ("rota com número sem semente: anote com `casa.pagina` na semente da área, ou ponha em "
                        f"`SEM_SEMENTE` com o motivo ({len(faltam)}):\n  " + "\n  ".join(faltam))


def test_nao_ha_motivo_para_rota_que_tem_semente_nem_para_rota_que_nao_existe(casa):  # noqa: F811
    semeadas = {endpoint for endpoint, _ in casa.paginas}
    existem = {r.endpoint for r in E.regras_de_leitura(casa.app)}
    fora = sem_semente()
    assert not sorted(set(fora) & semeadas), "está em SEM_SEMENTE e tem semente"
    assert not sorted(set(fora) - existem), "está em SEM_SEMENTE e a rota não existe"


def test_o_que_a_semente_anotou_abre(casa):  # noqa: F811
    """404 aqui é semente que não achou a linha: a varredura passaria sem ver a tela."""
    c = casa.cliente("ADMIN", "novo")
    ruins = []
    for endpoint, endereco in casa.paginas:
        if area_da_regra(endereco) not in areas_pedidas():
            continue
        r = c.get(endereco)
        if r.mimetype != "text/event-stream":
            r.get_data()
        if r.status_code in (404, 500) or (r.status_code == 302 and "/login" in r.headers.get("Location", "")):
            ruins.append(f"{endereco} ({endpoint}): {r.status_code} {r.headers.get('Location', '')}")
    assert not ruins, "a semente não abre:\n  " + "\n  ".join(ruins)
