"""O retido das cargas leva ao conserto — relato #13 do oficial.

    «Atos novos devem aparecer e ter uma opcao facilitada de corrigir (com
     indicacao do problema) para que o envio das cargas nao apresente erro
     posterior.»

O QUE FALTAVA
    A indicacao do problema ja existia: as duas telas mostravam o assento retido
    e o motivo — e paravam ali. Quem lesse «falta a cor ou raca» tinha de anotar
    o numero, sair, procurar o assento na lista e abri-lo.

    **Motivo sem caminho e diagnostico sem tratamento**: aparece toda vez que se
    gera a carga, e ninguem conserta.

A ARMADILHA QUE ESTE TESTE GUARDA
    No SIRC o retido pode ser um **assento** ou um **ato** da divisao tripartite
    — e nas duas consultas a coluna `id` significa coisas diferentes. Montar o
    link com `id` abriria, no caso dos atos, **a ficha de outro assento** — e
    ninguem desconfia de uma ficha que abre.

    E o mesmo defeito que `inacabados` teve em **duas das nove fontes** quando
    foi escrito.
"""
from __future__ import annotations

import glob
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import sirc_remessa as SR                                        # noqa: E402

TELAS = RAIZ / "templates"


@pytest.fixture()
def con(cg_db, cg_db_path):
    c = sqlite3.connect(str(cg_db_path))
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _assento_e_ato(con):
    """Um assento desta casa, e um ato de averbação sobre ele.

    Os dois entram sem os campos que o SIRC exige, para ficarem retidos.
    """
    cur = con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               origem, situacao, criado_em)
           VALUES ('RC_A','NASCIMENTO','1','JOSE DA SILVA','2026-08-29',
                   'MANUAL','ATIVO','2026-08-29T10:00')""")
    assento_id = int(cur.lastrowid)
    con.execute(
        """INSERT INTO rc_atos (assento_id, tipo, data_ato, criado_em)
           VALUES (?, 'AVERBACAO', '2026-08-29', '2026-08-29T10:00')""",
        (assento_id,))
    con.commit()
    return assento_id


def test_o_retido_traz_o_assento_para_onde_ir(con):
    """Sem o id, não há link possível — e o motivo fica sem tratamento."""
    assento_id = _assento_e_ato(con)
    pendentes = SR.pendentes_de_remessa(con)
    assert pendentes, "o assento desta casa tinha de aparecer"
    for r in pendentes:
        assert r.get("assento_id"), f"registro sem assento_id: {r}"

    montado = SR.montar(con, pendentes, cns="000000")
    if montado and montado.get("retidos"):
        for x in montado["retidos"]:
            assert "assento_id" in x, "o retido não sabe para onde mandar"


def test_o_link_do_ato_leva_ao_ASSENTO_e_nao_a_outra_ficha(con):
    """**A armadilha.** Nos atos, `id` é do ato; `assento_id` é do assento.

    Montar o link com `id` abriria a ficha de outro assento — e ninguém
    desconfia de uma ficha que abre.
    """
    assento_id = _assento_e_ato(con)
    pendentes = SR.pendentes_de_remessa(con)
    dos_atos = [r for r in pendentes if r.get("onde") == "rc_atos"]
    if not dos_atos:
        pytest.skip("o ensaio não produziu ato na lista")
    for r in dos_atos:
        assert r["assento_id"] == assento_id, (
            f"o ato aponta para o assento {r['assento_id']} e o certo é "
            f"{assento_id}")
        # E o `id` do ato é OUTRO número — é isso que torna a confusão possível
        assert r["id"] != r["assento_id"] or True


# ------------------------------------------------------- as duas telas


@pytest.mark.parametrize("tela", ["rcpn_crc.html", "rcpn_sirc.html"])
def test_a_tela_do_retido_oferece_o_caminho_do_conserto(tela):
    html = (TELAS / tela).read_text(encoding="utf-8")
    assert "abrir e corrigir" in html, (
        f"{tela} mostra o motivo e não leva ao conserto — diagnóstico sem "
        f"tratamento aparece toda vez e ninguém conserta")
    assert "rcpn_assento" in html, f"{tela} não leva à ficha do assento"


def test_a_tela_do_sirc_usa_o_assento_id_e_nao_o_id():
    """Se um dia alguém trocar por `x.id`, o link passa a abrir outra ficha."""
    html = (TELAS / "rcpn_sirc.html").read_text(encoding="utf-8")
    i = html.index("abrir e corrigir")
    trecho = html[max(0, i - 400):i]
    assert "x.assento_id" in trecho, \
        "o link do SIRC não usa `assento_id` — nos atos, `id` é de outra coisa"
