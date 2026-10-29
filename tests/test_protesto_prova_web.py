"""A PROVA DA INTIMAÇÃO PELAS TELAS — a ficha do título e o lote «A protestar».

Ordem do oficial, 29/10/2026: as telas mostram, título a título, se a prova
está completa, o que falta e o campo da afirmação (recolhido, com a frase de
alerta). No lote, o título sem prova não se lavra — a não ser com a
afirmação expressa DAQUELE título —, e a afirmação vai à auditoria como
`AFIRMACAO_EXPRESSA`, com a regra, o texto e o que faltava.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_protesto_a_protestar_web import (MOTIVO, _con, _token, atos,  # noqa: E402,F401
                                           intimado, lavrar, s)

AFIRMACAO = ("o envio do arquivo do edital foi feito no portal da CENPROT e o "
             "comprovante será juntado hoje à tarde")


def _auditoria(s, acao: str) -> list:
    con = _con(s)
    linhas = con.execute("SELECT * FROM audit_logs WHERE action=? ORDER BY id",
                         (acao,)).fetchall()
    con.close()
    return linhas


def test_a_lista_diz_o_que_falta_e_oferece_a_afirmacao_recolhida(s):
    sem = intimado(s, numero="sem/1", provado=False)
    com = intimado(s, numero="com/1")
    html = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    assert "Sem a prova da intimação, o título marcado não se lavra" in html
    assert "Falta a prova da intimação" in html
    assert "não tem edital publicado no sistema" in html
    assert "Prova da intimação completa" in html
    # a afirmação é do título sem prova, e só dele
    assert f'name="afirmo_{sem}"' in html and f'name="afirmacao_{sem}"' in html
    assert f'name="afirmo_{com}"' not in html
    assert "Afirmo, sob minha responsabilidade, que" in html
    assert '<details class="afirmacao-expressa"' in html          # recolhida


def test_no_lote_o_titulo_sem_prova_nao_se_lavra_e_o_provado_sim(s):
    sem = intimado(s, numero="sem/1", provado=False)
    com = intimado(s, numero="com/1")
    resposta = lavrar(s, [sem, com]).get_data(as_text=True)
    assert atos(s, com) == 1
    assert atos(s, sem) == 0
    assert "Não se protesta sem a prova da intimação" in resposta
    assert _auditoria(s, "AFIRMACAO_EXPRESSA") == []


def test_no_lote_so_a_caixa_sem_o_texto_nao_afirma_nada(s):
    sem = intimado(s, numero="sem/1", provado=False)
    tela = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    s["c"].post("/protesto/a-protestar/lavrar",
                data={"csrf_token": _token(tela), "titulo_id": [str(sem)],
                      f"motivo_atraso_{sem}": MOTIVO, f"afirmo_{sem}": "1",
                      f"afirmacao_{sem}": "confere"},
                follow_redirects=True)
    assert atos(s, sem) == 0


def test_no_lote_a_afirmacao_do_titulo_lavra_e_fica_na_auditoria(s):
    sem = intimado(s, numero="sem/1", provado=False)
    outro = intimado(s, numero="outro/1", provado=False)
    tela = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    s["c"].post("/protesto/a-protestar/lavrar",
                data={"csrf_token": _token(tela),
                      "titulo_id": [str(sem), str(outro)],
                      f"motivo_atraso_{sem}": MOTIVO,
                      f"motivo_atraso_{outro}": MOTIVO,
                      # A AFIRMAÇÃO É POR TÍTULO: a de um não vale pelo outro
                      f"afirmo_{sem}": "1", f"afirmacao_{sem}": AFIRMACAO},
                follow_redirects=True)
    assert atos(s, sem) == 1
    assert atos(s, outro) == 0

    [linha] = _auditoria(s, "AFIRMACAO_EXPRESSA")
    assert linha["entity_type"] == "pt_atos"
    detalhe = json.loads(linha["details"])
    assert detalhe["regra"] == "PROTESTO_SEM_PROVA_DA_INTIMACAO"
    assert detalhe["afirmacao"].startswith("Afirmo, sob minha responsabilidade, que")
    assert AFIRMACAO in detalhe["afirmacao"]
    assert "não tem edital publicado" in detalhe["o_que_faltava"]

    con = _con(s)
    no_ato = json.loads(con.execute(
        "SELECT detalhe_json FROM pt_atos WHERE titulo_id=? AND tipo='PROTESTO'",
        (sem,)).fetchone()[0])
    con.close()
    assert no_ato["afirmacao_expressa"]["afirmacao"] == detalhe["afirmacao"]


def test_a_ficha_mostra_a_prova_e_a_ficha_recusa_sem_afirmacao(s):
    tid = intimado(s, provado=False)
    html = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "Falta a prova da intimação" in html
    assert 'name="afirmo"' in html and 'name="afirmacao"' in html
    resposta = s["c"].post(
        f"/protesto/{tid}/lancar",
        data={"csrf_token": _token(html), "ato": "PROTESTO",
              "motivo_atraso": MOTIVO},
        follow_redirects=True).get_data(as_text=True)
    assert "Não se protesta sem a prova da intimação" in resposta
    assert atos(s, tid) == 0


def test_a_tela_dos_avisos_lista_os_intimados_sem_prova(s):
    """A pendência que o roteiro lê aparece onde a prova se junta."""
    sem = intimado(s, numero="sem/1", provado=False)
    intimado(s, numero="com/1")
    html = s["c"].get("/protesto/avisos").get_data(as_text=True)
    assert "Intimados sem a prova da intimação" in html
    assert f"/protesto/{sem}" in html and "sem/1" in html
    assert "com/1" not in html.split('id="sem-prova"', 1)[1].split("</section>", 1)[0]


def test_a_ficha_do_titulo_provado_nao_oferece_afirmacao(s):
    tid = intimado(s)
    html = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "Prova da intimação completa" in html
    assert 'name="afirmo"' not in html
