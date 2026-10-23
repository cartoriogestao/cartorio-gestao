"""
O PASSO DA TARDE: «gerar protesto, sem movimentacao, calcular, listar, gerar».

Do CHECK LIST PROTESTO que o oficial pos na pasta. Era o unico passo do roteiro
diario sem tela nenhuma — o titulo intimado ficava esperando alguem lembrar
dele, um a um, na lista geral.

O QUE ESTES TESTES GUARDAM
      - «SEM MOVIMENTACAO» e SEM ATO POSTERIOR, e nao so a situacao `INTIMADO`:
        a consulta olha o `id` do ato, que e a ordem em que foram lavrados;
      - o PRAZO NAO SE CALCULA — decisao do oficial de 24/08/2026. A lista
        conta os dias e nao julga o trideo;
      - `dias_desde_a_intimacao` devolve **None** quando falta data, e nao
        zero: zero diria «foi intimado hoje», que e afirmacao;
      - a lista NAO PROTESTA SOZINHA — quem escolhe e o oficial, titulo a
        titulo.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import protesto as PT
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

AGORA = "2026-08-31T15:00:00"
HOJE = "2026-08-31"


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def titulo(con, *, numero="84713/1") -> int:
    cur = con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
               valor_centavos, saldo_centavos, situacao, protocolo, origem,
               criado_em)
           VALUES ('DMI',?,'00200000991',148278,148278,'APONTADO',
                   '2608310001','CRA',?)""", (numero, AGORA))
    tid = int(cur.lastrowid)
    con.execute(
        """INSERT INTO pt_devedores(titulo_id, nome, documento_tipo,
               documento_numero) VALUES (?,'MARIA SANTOS','CPF','04785512388')""",
        (tid,))
    return tid


def ato(con, titulo_id, tipo, *, data="2026-08-20", detalhe="{}"):
    # `detalhe_json` e NOT NULL DEFAULT '{}': passar None atropela o padrao do
    # banco e estoura. O DEFAULT so vale quando a coluna fica FORA do INSERT.
    con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
               origem, criado_em) VALUES (?,?,?,?, 'MANUAL', ?)""",
        (titulo_id, tipo, data, detalhe, AGORA))


def intimado(con, titulo_id, *, data="2026-08-20", modo="PESSOAL"):
    ato(con, titulo_id, "APONTAMENTO", data="2026-08-18")
    ato(con, titulo_id, "INTIMACAO", data=data,
        detalhe=json.dumps({"modo": modo}))
    con.execute("UPDATE pt_titulos SET situacao='INTIMADO' WHERE id=?",
                (titulo_id,))


# ------------------------------------------------------- o que entra


def test_o_intimado_sem_ato_posterior_entra():
    con = banco()
    tid = titulo(con)
    intimado(con, tid)
    lista = PT.esperando_protesto(con, hoje=HOJE)
    assert [x["id"] for x in lista] == [tid]
    assert lista[0]["data_da_intimacao"] == "2026-08-20"


def test_o_que_nunca_foi_intimado_nao_entra():
    con = banco()
    tid = titulo(con)
    ato(con, tid, "APONTAMENTO")
    assert PT.esperando_protesto(con, hoje=HOJE) == []


def test_ato_POSTERIOR_a_intimacao_tira_da_lista():
    """SEM MOVIMENTACAO E SEM ATO POSTERIOR, e nao so a situacao `INTIMADO`.

    Um pagamento lançado hoje muda a situacao — mas o que a lista pergunta e se
    ENTROU ALGUM ATO depois da intimacao, olhando o `id`, que e a ordem em que
    eles foram lavrados. Perguntar so pela situacao deixaria passar o titulo
    cujo ato posterior nao mudou o estado.
    """
    con = banco()
    tid = titulo(con)
    intimado(con, tid)
    assert len(PT.esperando_protesto(con, hoje=HOJE)) == 1
    ato(con, tid, "PAGAMENTO", data="2026-08-25")
    # A situacao continua INTIMADO de proposito, para isolar o que se testa.
    assert PT.esperando_protesto(con, hoje=HOJE) == []


def test_o_devedor_vem_junto():
    """Quem le a lista decide sobre PESSOAS, e nao sobre numeros de titulo."""
    con = banco()
    tid = titulo(con)
    intimado(con, tid)
    lista = PT.esperando_protesto(con, hoje=HOJE)
    assert lista[0]["devedores"][0]["nome"] == "MARIA SANTOS"


def test_o_modo_da_intimacao_sai_do_detalhe():
    """Ele mora no `detalhe_json`, e nao em coluna. Saber se foi pessoal ou por
    edital importa: o edital e a rotina desta casa."""
    con = banco()
    tid = titulo(con)
    intimado(con, tid, modo="EDITAL")
    assert PT.esperando_protesto(con, hoje=HOJE)[0]["modo_da_intimacao"] == "EDITAL"


# ---------------------------------------------- o prazo nao se calcula


def test_a_lista_CONTA_os_dias_e_nao_julga_o_prazo():
    """Decisao do oficial em 24/08/2026: nenhuma funcao de Protesto calcula
    prazo. `dias_desde_a_intimacao` e contagem — quem diz se o trideo venceu e
    quem assina."""
    con = banco()
    tid = titulo(con)
    intimado(con, tid, data="2026-08-20")
    assert PT.esperando_protesto(con, hoje=HOJE)[0]["dias_desde_a_intimacao"] == 11


def test_o_modulo_nao_ganhou_funcao_que_decida_prazo():
    """Se alguem escrever `venceu_o_prazo` ou `pode_protestar`, isto fica
    vermelho — seria o sistema decidindo sobre o ato mais grave da atribuicao."""
    proibidas = [n for n in dir(PT) if not n.startswith("_")
                 and any(p in n.lower() for p in
                         ("venceu", "trideo", "pode_protestar",
                          "prazo_vencido"))]
    assert proibidas == []


def test_sem_data_a_contagem_e_None_e_nao_zero():
    """Zero diria «foi intimado hoje», que e afirmacao. Nao saber e outra
    coisa, e a tela mostra um traco."""
    con = banco()
    tid = titulo(con)
    ato(con, tid, "INTIMACAO", data="")
    con.execute("UPDATE pt_titulos SET situacao='INTIMADO' WHERE id=?", (tid,))
    assert PT.esperando_protesto(con, hoje=HOJE)[0]["dias_desde_a_intimacao"] is None


def test_a_intimacao_MAIS_NOVA_e_a_que_conta():
    """O aviso nao e um por titulo — 1.618 avisos para 1.361 titulos —, e
    reemitir e rotina. Quem conta e a ultima intimacao."""
    con = banco()
    tid = titulo(con)
    intimado(con, tid, data="2026-08-10")
    ato(con, tid, "INTIMACAO", data="2026-08-28", detalhe='{"modo": "EDITAL"}')
    lista = PT.esperando_protesto(con, hoje=HOJE)
    assert lista[0]["data_da_intimacao"] == "2026-08-28"
    assert lista[0]["dias_desde_a_intimacao"] == 3


def test_a_ordem_e_a_da_intimacao_mais_antiga():
    """Quem esperou mais aparece primeiro — e a fila do dia e essa."""
    con = banco()
    novo = titulo(con, numero="novo")
    velho = titulo(con, numero="velho")
    intimado(con, novo, data="2026-08-28")
    intimado(con, velho, data="2026-08-10")
    assert [x["id"] for x in PT.esperando_protesto(con, hoje=HOJE)] == [velho, novo]
