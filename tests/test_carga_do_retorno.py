"""
O RETORNO A CRA NAO PODIA SER GERADO PARA NENHUM TITULO DO ACERVO.

COMO APARECEU — e nao foi por teste
    Todo o modulo do Protesto passava em teste de mesa. O ENSAIO CONTRA A
    PRODUCAO, em 01/09/2026, mostrou o que os testes nao podiam mostrar:

        pendentes() ................. 1.211 atos que a CRA nao sabe
        deles, SEM protocolo ........ 1.211
        apresentantes_pendentes() ... UM grupo, com codigo VAZIO
        atos de INTIMACAO ........... zero em 1.366 titulos

    Sao tres buracos da carga, e eles se somam num efeito so: **nenhum retorno
    sai**. O sistema ja recusava, com a mensagem certa — «estao sem numero de
    protocolo, e ele e o que volta na posicao 448 do arquivo. Os titulos
    vindos do acervo antigo podem estar assim» —, e ninguem tinha medido que a
    recusa alcanca TODOS.

    O CLAUDE.md diz «o protocolo e o apresentante nao se guardavam, e o
    retorno cobrou os dois». Aquele conserto foi no caminho do titulo NOVO;
    a carga ficou como estava.

ONDE O DADO ESTAVA, o tempo todo
    protocolo ............. tbAvisoProtesto.strCB ......... 1.369 de 1.370
    codigo do apresentante  tbSDT.Campo02, por intProtocolo  1.357
    nome .................. tbSDT.Campo04 .................. 1.360
    intimacao por edital .. tbEdital.dtmpublicacao ......... 1.115 titulos
    intimacao em maos ..... tbBoletoApto.dtmEntregaConfirmada .. 61
    motivo ................ tbBoletoControleNEntrega + tbMotivoNEntrega

O QUE O ENSAIO DEU, DEPOIS DA PASSADA
    protocolos 1.365 · apresentantes 1.357 · intimacoes 1.176
    (EDITAL 1.115, PESSOAL 61) · sem intimacao no acervo 190
    retorno: 1.211 pendentes, **zero sem protocolo**, **58 apresentantes**

O QUE ESTES TESTES GUARDAM
      - os tres vem juntos, porque servem ao mesmo arquivo;
      - a ligacao e `origem_chave`, e nao o protocolo (que e o que falta) nem
        a `origem` (que diz de onde o TITULO veio, nao a fonte da carga);
      - `strCB = '0'` NAO vira protocolo: e campo em branco preenchido com
        zero;
      - **nao se inventa intimacao**: sem edital e sem entrega, o ato nao
        entra;
      - o motivo so acompanha o EDITAL;
      - e a passada e REPETIVEL — ela olha o que falta.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import acervo_carga as AC
import protesto_retorno as PR
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

AGORA = "2026-09-01T10:00:00"


def acervo() -> sqlite3.Connection:
    """O acervo mínimo, com as colunas que esta passada lê de verdade."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE tbAvisoProtesto (intChave REAL, strCB TEXT,
                                      intProtocolo REAL);
        CREATE TABLE tbSDT (intChave REAL, intProtocolo REAL,
                            Campo02 TEXT, Campo04 TEXT);
        CREATE TABLE tbEdital (strcb_ap TEXT, dtmpublicacao TEXT);
        CREATE TABLE tbBoletoApto (strCB_AP TEXT, dtmEntregaConfirmada TEXT);
        CREATE TABLE tbBoletoControleNEntrega (
            strCB_AP TEXT, dtmEntrega TEXT,
            intCodigoMotivoNaoEntrega INTEGER, bitEntregue INTEGER);
        -- O catalogo medido: 13 motivos, e `strMotivo` — nao `strDescricao`,
        -- que foi o nome que eu inventei e que a execucao corrigiu.
        CREATE TABLE tbMotivoNEntrega (intCodigo INTEGER, strMotivo TEXT);
        INSERT INTO tbMotivoNEntrega VALUES
            (1,'Mudou-se'), (2,'Endereço não encontrado'),
            (3,'Recusou-se a receber'), (5,'Ausente');
    """)
    return con


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def titulo(con, *, chave=7, numero="84713/1", origem="CRA") -> int:
    cur = con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
               valor_centavos, saldo_centavos, situacao, origem,
               origem_chave, criado_em)
           VALUES ('DMI',?,'00200000991',148278,148278,'APONTADO',?,?,?)""",
        (numero, origem, f"tbAvisoProtesto:{chave}.0", AGORA))
    return int(cur.lastrowid)


def passar(con, ac) -> dict:
    return AC._o_que_o_retorno_precisa(con, ac, carga=AC.Carga("pt_titulos"),
                                       agora=AGORA)


def do_titulo(con, tid, campo):
    return con.execute(f"SELECT {campo} FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0]


# ------------------------------------------------- os três vêm juntos


def test_traz_protocolo_apresentante_e_intimacao():
    con, ac = banco(), acervo()
    tid = titulo(con)
    ac.execute("INSERT INTO tbAvisoProtesto VALUES (7,'2608310001',2608310001)")
    ac.execute("INSERT INTO tbSDT VALUES (1,2608310001,'1LV','EQUATORIAL')")
    ac.execute("INSERT INTO tbEdital VALUES ('2608310001','2026-08-20 00:00:00')")
    ac.execute("""INSERT INTO tbBoletoControleNEntrega
                  VALUES ('2608310001','2026-08-15 00:00:00',5,0)""")

    feito = passar(con, ac)
    assert feito == {"protocolo": 1, "apresentante": 1, "intimacao": 1,
                     "sem_intimacao": 0}
    assert do_titulo(con, tid, "protocolo") == "2608310001"
    assert do_titulo(con, tid, "apresentante_codigo") == "1LV"
    assert do_titulo(con, tid, "apresentante_nome") == "EQUATORIAL"

    ato = con.execute("SELECT * FROM pt_atos WHERE tipo='INTIMACAO'").fetchone()
    detalhe = json.loads(ato["detalhe_json"])
    assert ato["data_ato"] == "2026-08-20"
    assert detalhe["modo"] == "EDITAL"
    assert detalhe["motivo"] == "Ausente"


def test_a_ligacao_e_origem_chave_e_nao_o_protocolo():
    """FOI O MEU PRIMEIRO ERRO nesta passada: procurei por `origem = 'EOFICIO'`
    e por protocolo preenchido, e achei ZERO — porque `origem` guarda de onde o
    TÍTULO veio (CRA, CENPROT, MANUAL) e o protocolo é justamente o que falta.
    """
    con, ac = banco(), acervo()
    # os três origens que a produção tem, e nenhuma delas é 'EOFICIO'
    for i, o in enumerate(("CRA", "CENPROT", "MANUAL"), start=1):
        titulo(con, chave=i, numero=f"{i}/1", origem=o)
        ac.execute("INSERT INTO tbAvisoProtesto VALUES (?,?,?)",
                   (float(i), f"260831000{i}", float(f"260831000{i}")))
    assert passar(con, ac)["protocolo"] == 3


# ------------------------------------------- o que NÃO se traz


def test_strCB_igual_a_ZERO_nao_vira_protocolo():
    """«0» não é protocolo: é campo em branco preenchido com zero. O acervo
    real tem um assim."""
    con, ac = banco(), acervo()
    tid = titulo(con)
    ac.execute("INSERT INTO tbAvisoProtesto VALUES (7,'0',NULL)")
    assert passar(con, ac)["protocolo"] == 0
    assert not (do_titulo(con, tid, "protocolo") or "")


def test_NAO_se_inventa_intimacao():
    """Sem edital publicado e sem entrega confirmada, o ato não entra. São 194
    assim no acervo, e 8 deles protestados — buraco do próprio E-Ofício, e
    melhor visível como tal do que preenchido por suposição."""
    con, ac = banco(), acervo()
    titulo(con)
    ac.execute("INSERT INTO tbAvisoProtesto VALUES (7,'2608310001',2608310001)")
    feito = passar(con, ac)
    assert feito["intimacao"] == 0
    assert feito["sem_intimacao"] == 1
    assert con.execute(
        "SELECT COUNT(*) FROM pt_atos WHERE tipo='INTIMACAO'").fetchone()[0] == 0


def test_entrega_confirmada_sem_edital_e_intimacao_PESSOAL():
    con, ac = banco(), acervo()
    titulo(con)
    ac.execute("INSERT INTO tbAvisoProtesto VALUES (7,'2608310001',2608310001)")
    ac.execute("""INSERT INTO tbBoletoApto
                  VALUES ('2608310001','2026-08-18 00:00:00')""")
    passar(con, ac)
    ato = con.execute("SELECT * FROM pt_atos WHERE tipo='INTIMACAO'").fetchone()
    assert json.loads(ato["detalhe_json"])["modo"] == "PESSOAL"
    assert ato["data_ato"] == "2026-08-18"


def test_o_motivo_so_acompanha_o_EDITAL():
    """Ele explica por que a entrega falhou — e numa intimação em mãos ela não
    falhou."""
    con, ac = banco(), acervo()
    titulo(con)
    ac.execute("INSERT INTO tbAvisoProtesto VALUES (7,'2608310001',2608310001)")
    ac.execute("""INSERT INTO tbBoletoApto
                  VALUES ('2608310001','2026-08-18 00:00:00')""")
    ac.execute("""INSERT INTO tbBoletoControleNEntrega
                  VALUES ('2608310001','2026-08-15 00:00:00',5,0)""")
    passar(con, ac)
    ato = con.execute("SELECT * FROM pt_atos WHERE tipo='INTIMACAO'").fetchone()
    assert "motivo" not in json.loads(ato["detalhe_json"])


def test_a_ULTIMA_publicacao_e_a_que_conta():
    """O aviso não é um por título — 1.618 para 1.361 —, e reemitir é rotina."""
    con, ac = banco(), acervo()
    titulo(con)
    ac.execute("INSERT INTO tbAvisoProtesto VALUES (7,'2608310001',2608310001)")
    ac.execute("INSERT INTO tbEdital VALUES ('2608310001','2026-08-10 00:00:00')")
    ac.execute("INSERT INTO tbEdital VALUES ('2608310001','2026-08-28 00:00:00')")
    passar(con, ac)
    assert con.execute(
        "SELECT data_ato FROM pt_atos WHERE tipo='INTIMACAO'").fetchone()[0] \
        == "2026-08-28"


# -------------------------------------------------- e é repetível


def test_a_passada_roda_DUAS_VEZES_sem_duplicar():
    """Ela olha o que FALTA — é a mesma forma das outras passadas da casa, e
    a razão é que quem rodou a carga antes tem os títulos gravados: numa
    segunda rodada eles voltam como `repetidos`, e nada chegaria neles."""
    con, ac = banco(), acervo()
    titulo(con)
    ac.execute("INSERT INTO tbAvisoProtesto VALUES (7,'2608310001',2608310001)")
    ac.execute("INSERT INTO tbSDT VALUES (1,2608310001,'1LV','EQUATORIAL')")
    ac.execute("INSERT INTO tbEdital VALUES ('2608310001','2026-08-20 00:00:00')")

    primeira = passar(con, ac)
    segunda = passar(con, ac)
    assert primeira["intimacao"] == 1
    assert segunda == {"protocolo": 0, "apresentante": 0, "intimacao": 0,
                       "sem_intimacao": 0}
    assert con.execute(
        "SELECT COUNT(*) FROM pt_atos WHERE tipo='INTIMACAO'").fetchone()[0] == 1


# --------------------------------- e o efeito: o retorno passa a sair


def test_o_RETORNO_deixa_de_ser_impossivel():
    """**É o teste que resume tudo.** Antes da passada, `pendentes()` devolve
    atos todos sem protocolo e o agrupamento por apresentante devolve um grupo
    de código vazio — e `montar` recusa. Depois, cada ato tem protocolo e cada
    apresentante tem código.
    """
    con, ac = banco(), acervo()
    tid = titulo(con)
    con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, origem, criado_em)
           VALUES (?,'PROTESTO','2026-08-25','EOFICIO',?)""", (tid, AGORA))
    ac.execute("INSERT INTO tbAvisoProtesto VALUES (7,'2608310001',2608310001)")
    ac.execute("INSERT INTO tbSDT VALUES (1,2608310001,'1LV','EQUATORIAL')")
    ac.execute("INSERT INTO tbEdital VALUES ('2608310001','2026-08-20 00:00:00')")

    antes = PR.pendentes(con)
    assert antes and all(not (a["protocolo"] or "").strip() for a in antes)
    assert [g["apresentante_codigo"] for g in PR.apresentantes_pendentes(con)] \
        == [""]

    passar(con, ac)

    depois = PR.pendentes(con)
    assert depois and all((a["protocolo"] or "").strip() for a in depois)
    assert [g["apresentante_codigo"] for g in PR.apresentantes_pendentes(con)] \
        == ["1LV"]
