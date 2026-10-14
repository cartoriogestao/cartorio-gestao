"""O painel mostra OS ATOS em andamento — relato #29 do oficial.

    «no painel, deveriam aparecer apenas expedientes pendentes (...) o painel
     deve focar nos atos em andamento e tarefas pendentes, tudo em ordem de
     relevancia»

O QUE SE MEDIU ANTES DE MEXER
    **A primeira metade do pedido ja estava feita**, e dizer o contrario seria
    consertar o que nao esta quebrado: `dashboard()` ja pedia
    `list_tasks("ABERTAS")` e `list_expedientes(only_open=True)`, e as duas
    consultas ja ordenavam por prioridade e por prazo.

    **A metade que faltava era «atos».** Tarefa e expediente sao o que a casa
    anota; a escritura em lavratura, a prenotacao sem ato, o usucapiao e a
    habilitacao sao o que a casa FAZ — e nenhum deles aparecia na primeira tela.
    `inacabados` ja os media, so que numa tela que se abre de proposito, e o
    painel e a que se abre sozinha.

E UM DEFEITO QUE ISSO DESENTERROU
    A fonte do protocolo do balcao contava **21.348 atendimentos em aberto,
    21.342 deles do E-Oficio** — porque `PAGO` e `A_PAGAR` nao sao situacoes
    terminais e o botao de encerrar so nasceu em 28/08/2026. Levado ao painel
    como estava, ele anunciaria vinte e um mil pendencias na primeira tela da
    casa. O conserto esta em `inacabados.py`, e o guarda em
    `test_o_acervo_nao_vira_atraso.py`.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return achado.group(1) if achado else ""


@pytest.fixture(scope="module")
def casa(tmp_path_factory):
    from app import create_app
    from database import Database

    dados = tmp_path_factory.mktemp("dados")
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco).create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA,
                                "ADMIN")

    con = sqlite3.connect(banco)
    # UM ATENDIMENTO DO E-OFICIO, parado ha anos — o que NAO pode aparecer.
    con.execute(
        "INSERT INTO cx_protocolos (numero, interessado, data_abertura, "
        "situacao, origem, criado_em) VALUES (?,?,?,?,?,?)",
        ("2019.01.001", "GENTE DE OUTRO TEMPO", "2019-03-04", "PAGO",
         "EOFICIO", "2019-03-04T09:00"))
    # UM DA CASA, tambem parado — o que TEM de aparecer, e em primeiro lugar.
    con.execute(
        "INSERT INTO cx_protocolos (numero, interessado, data_abertura, "
        "situacao, origem, criado_em) VALUES (?,?,?,?,?,?)",
        ("2026.01.010", "QUEM ESPERA DESDE JANEIRO", "2026-01-06", "A_PAGAR",
         "MANUAL", "2026-01-06T09:00"))
    con.commit()
    con.close()

    c = app.test_client()
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"c": c, "banco": banco}


def _painel(casa) -> str:
    return casa["c"].get("/").get_data(as_text=True)


def test_o_painel_tem_a_secao_dos_atos(casa):
    """Sem ela o painel responde metade da pergunta do oficial."""
    html = _painel(casa)
    assert "Atos em andamento" in html


def test_o_atendimento_da_casa_aparece_no_painel(casa):
    """Ele esta parado desde janeiro, e e trabalho de verdade."""
    html = _painel(casa)
    assert "Atendimento do balc" in html, "a fonte do protocolo sumiu do painel"


def test_o_acervo_nao_aparece_no_painel(casa):
    """**O caso que ia para a primeira tela da casa.**

    Sao 21.342 atendimentos do E-Oficio, todos «em aberto» porque ninguem os
    marcou como entregues — o botao de encerrar so nasceu em 28/08/2026. Um
    painel que os contasse anunciaria vinte e um mil pendencias, e lista que o
    balcao nao tem como zerar e lista que ninguem abre duas vezes.
    """
    import inacabados as INAC

    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    achados = INAC.lista(con, hoje="2026-08-30", chave="BALCAO_PROTOCOLO")
    con.close()
    assert [x["rotulo"] for x in achados] == ["QUEM ESPERA DESDE JANEIRO"]


def test_o_painel_leva_a_lista_inteira(casa):
    """Numero no painel sem caminho para o detalhe faz quem o le procurar."""
    html = _painel(casa)
    assert "/inacabados" in html


def test_os_processos_vem_antes_dos_atos(casa):
    """13/10/2026 — o contrato virou: era «atos antes das tarefas» (relato #29).

    O oficial: «deixando como prioridade o campo de tarefas, ocupando todo
    espaço horizontal (...) atos em andamento também ao final».
    """
    html = _painel(casa)
    assert html.index("Processos em aberto") < html.index("Atos em andamento"), \
        "os atos ficaram na frente dos processos"
    assert "Expedientes em andamento" not in html


def test_a_medicao_que_falha_nao_vira_zero(casa):
    """**ZERO MEDIDO E ZERO POR ENGANO SAO A MESMA TELA E COISAS DIFERENTES.**

    Um `except` que devolvesse lista vazia faria a primeira tela da casa dizer
    «nada em andamento» no dia em que a medicao quebrasse — e ninguem repara em
    item que deixou de aparecer.
    """
    codigo = (RAIZ / "app.py").read_text(encoding="utf-8")
    trecho = codigo[codigo.index("andamento, andamento_erro"):]
    trecho = trecho[:trecho.index("return render_template")]
    assert "andamento_erro = f" in trecho, \
        "a falha da medição não está sendo guardada para aparecer na tela"
    tela = (RAIZ / "templates" / "dashboard.html").read_text(encoding="utf-8")
    assert "andamento_erro" in tela, "a tela não mostra a falha da medição"
