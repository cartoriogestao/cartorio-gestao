"""O retorno do 900001/2 recusado três vezes pela CRA — 21/10/2026.

O QUE SE MEDIU
    1ª e 2ª recusa: código 2154, «APRESENTANTE: TAB - SEQUENCIAL REMESSA:
    000001 / 000077 NÃO FOI ENCONTRADO NA CRA». O título veio pela Gestão de
    Pedidos da CENPROT (pedido 9000002), e a remessa nunca passou pela CRA. O
    pagamento entrou na CENPROT pelo XML «D», aceito no mesmo dia.

    E no caminho apareceu o outro defeito: o retorno levava o NOME do
    apresentante nas posições 005/019, onde o E-Ofício punha
    `tbSDT.Campo03` — medido no RTAB0608.261 que ele gerou para o mesmo título.

O QUE ESTES TESTES GUARDAM
    - título que veio da CENPROT não entra no retorno à CRA, e a recusa diz
      para onde ele vai;
    - a carga traz `Campo03` para `cra_identificacao`, e é ele que sai no
      retorno;
    - sem a identificação, o retorno continua levando o que havia antes.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import acervo_carga as AC
import protesto_arquivo as PA
import protesto_retorno as PR
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

AGORA = "2026-10-21T10:00:00"


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def pago(con, *, origem: str, protocolo: str, nosso: str,
         identificacao: str | None = None, chave: int = 1) -> int:
    cur = con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
               valor_centavos, saldo_centavos, situacao, origem, origem_chave,
               protocolo, apresentante_codigo, apresentante_nome,
               cra_identificacao, criado_em)
           VALUES ('DMI',?,?,23000,23000,'PAGO',?,?,?,'TAB',
                   'MARIO EXEMPLO COMERCIO',?,?)""",
        (nosso, nosso, origem, f"tbAvisoProtesto:{chave}.0", protocolo,
         identificacao, AGORA))
    tid = int(cur.lastrowid)
    for tipo, quando in (("APONTAMENTO", "2026-08-06"), ("PAGAMENTO", "2026-08-11")):
        con.execute("""INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
                           origem, criado_em) VALUES (?,?,?,'{}','EOFICIO',?)""",
                    (tid, tipo, quando, AGORA))
    return tid


def test_titulo_da_cenprot_nao_vai_no_retorno_a_cra_e_a_recusa_diz_onde_vai():
    con = banco()
    pago(con, origem="CENPROT", protocolo="2608060001", nosso="900001/2")
    assert PR.pendentes(con, apresentante_codigo="TAB") == []
    assert PR.pendentes_da_cenprot(con, apresentante_codigo="TAB") == 1
    with pytest.raises(PR.RetornoError) as e:
        PR.montar(con, apresentante_codigo="TAB", dia="2026-10-21")
    assert "XML do CENPROT" in str(e.value)


def test_o_titulo_da_cra_continua_no_retorno_com_a_identificacao_da_central():
    con = banco()
    pago(con, origem="CRA", protocolo="2608060002", nosso="900001/3",
         identificacao="000000009000002")
    pago(con, origem="CENPROT", protocolo="2608060001", nosso="900001/2", chave=2)
    feito = PR.montar(con, apresentante_codigo="TAB", dia="2026-10-21")
    titulos = PA.ler(feito["conteudo"]).titulos
    assert [t["nosso_numero"] for t in titulos] == ["900001/3"]
    assert titulos[0]["identificacao_do_apresentante"] == "000000009000002"


def test_sem_a_identificacao_o_retorno_leva_o_que_havia_antes():
    con = banco()
    pago(con, origem="CRA", protocolo="2608060002", nosso="900001/3")
    titulos = PA.ler(PR.montar(con, apresentante_codigo="TAB",
                               dia="2026-10-21")["conteudo"]).titulos
    assert titulos[0]["identificacao_do_apresentante"] == "MARIO EXEMPLO C"


def test_a_carga_traz_o_campo03_e_e_repetivel():
    con = banco()
    tid = pago(con, origem="CRA", protocolo="2608060002", nosso="900001/3")
    ac = conexao_de_teste()
    ac.executescript("""
        CREATE TABLE tbSDT (intChave REAL, intProtocolo REAL, Campo02 TEXT,
                            Campo03 TEXT, Campo04 TEXT);
        INSERT INTO tbSDT VALUES (1, 2608060002, 'TAB', '000000009000002',
                                  'MARIO EXEMPLO COMERCIO');
    """)
    assert AC._identificacao_na_central(con, ac, carga=AC.Carga("pt_titulos")) == 1
    assert con.execute("SELECT cra_identificacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "000000009000002"
    assert AC._identificacao_na_central(con, ac, carga=AC.Carga("pt_titulos")) == 0


def test_acervo_sem_campo03_nao_estoura():
    con = banco()
    pago(con, origem="CRA", protocolo="2608060002", nosso="900001/3")
    ac = conexao_de_teste()
    ac.execute("CREATE TABLE tbSDT (intChave REAL, intProtocolo REAL, Campo02 TEXT)")
    assert AC._identificacao_na_central(con, ac, carga=AC.Carga("pt_titulos")) == 0
