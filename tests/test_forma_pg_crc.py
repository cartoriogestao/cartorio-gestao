"""Forma de pagamento PG_CRC — «PG feito pela CRC».

Pedido da operadora, para lançar no caixa os pedidos feitos e pagos pela CRC.
Decisão do oficial em 23/11/2026: a forma segue em tudo o molde do PG_ONR
(`test_forma_pg_onr.py`), caso a caso: entra no saldo e como receita, não entra
em espécie, vale no Protocolo Geral, no Caixa, nos Depósitos e no Livro de
Pagamentos do protesto, e o carnê-leão a conta como receita normal.

O CASO QUE O PG_ONR NÃO TEM: a cobertura `ato_selado.FORMA_CENTRAL_CRC` é do
selo da certidão eletrônica do RCPN (item 14.5.7) e NÃO é forma de pagamento.
A certidão continua saindo pelo caminho dela, e o protocolo pago com PG_CRC
cobre o selo só pela trava normal, como qualquer item pago.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest
from jinja2 import Template

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS  # noqa: E402
import caixa_automacao as CA  # noqa: E402
import caixa_schema as CX  # noqa: E402
import carne_leao as CL  # noqa: E402
import cobranca as CB  # noqa: E402
import gestor_financeiro as GF  # noqa: E402
import protesto as PT  # noqa: E402
import protesto_livros as PLIV  # noqa: E402
import protesto_pecas as PECAS  # noqa: E402
from bd_nativo import banco  # noqa: E402
from test_protesto_aviso_web import (  # noqa: E402, F401
    _con, s, titulo_apontado,
)
import test_certidao_eletronica_crc_selo as CRC  # noqa: E402
import test_rc_certidao_web as RC  # noqa: E402
import test_selo_e_caixa as SC  # noqa: E402
from selador_de_bancada import ligar_o_selador  # noqa: E402
from test_selo_e_caixa import _fechar_as_conexoes, aparelho  # noqa: E402, F401

AGORA = "2026-09-20T10:00:00"
ROTULO = "PG feito pela CRC"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "endereco_completo": "Rua Grande, 1, Centro",
      "serventia_telefone": "(99) 0000-0000",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}


def test_formas_pagamento_tem_pg_crc():
    assert CX.FORMAS_PAGAMENTO["PG_CRC"] == ROTULO


def test_resumo_caixa_pg_crc_entra_no_saldo_e_nao_em_especie():
    resumo = CX.resumo_caixa([
        {"sentido": "ENTRADA", "valor": "100,00", "forma_pagamento": "PG_CRC"},
        {"sentido": "ENTRADA", "valor": "50,00", "forma_pagamento": "DINHEIRO"},
    ], saldo_inicial=0)
    assert resumo["entradas"] == 15000
    assert resumo["saldo"] == 15000
    assert resumo["por_forma"]["PG_CRC"] == 10000
    assert resumo["em_especie"] == 5000


def test_fechamento_automatico_trata_pg_crc_como_eletronica(cg_casa):
    db = cg_casa["db"]
    with db.transaction() as con:
        cid = banco(con).escrever(
            """INSERT INTO cx_caixas
               (data,operador_nome,saldo_inicial,aberto_em,situacao)
               VALUES ('2026-11-15',%s,'0','2026-11-15T09:00:00','ABERTO')
               RETURNING id""",
            (CB.OPERADOR_DO_CAIXA_BANCARIO,))[0]["id"]
        banco(con).escrever(
            """INSERT INTO cx_lancamentos
               (caixa_id,data,natureza,sentido,forma_pagamento,valor,criado_em)
               VALUES (%s,'2026-11-15','RECEBIMENTO','ENTRADA','PG_CRC',
                       '10,00','2026-11-15T10:00:00')""",
            (cid,))
        caixa = banco(con).um("SELECT * FROM cx_caixas WHERE id=%s", (cid,))
        _resumo, precisa_contar = CA._medir(con, caixa)
    assert precisa_contar is False
    assert "PG_CRC" in CA.FORMAS_ELETRONICAS


def test_pg_crc_nao_e_pagamento_por_fora():
    cfg = {"cobranca_ligada": "1", "cobranca_banco": "PARCELA"}
    assert CB.conferir_pagamento_por_fora(
        "PG_CRC", cfg, afirmo=False, afirmacao="", ciencia=False) is None
    assert "PG_CRC" in CB.FORMAS_DE_DENTRO


def test_gestor_financeiro_nomeia_pg_crc(cg_casa):
    caminho = cg_casa["banco"]
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    con.execute(
        """INSERT INTO cx_lancamentos (data, natureza, sentido, forma_pagamento,
               descricao, valor, criado_em, estornado)
           VALUES ('2026-09-20', 'RECEBIMENTO', 'ENTRADA', 'PG_CRC',
                   'CERTIDÃO', '80,00', ?, 0)""", (AGORA,))
    con.commit()
    r = GF.apurar_mes(con, 2026, 9)
    con.close()
    assert r["entrou"][ROTULO] == pytest.approx(80.0)


def test_telas_oferecem_a_opcao_pg_crc():
    for nome in ("_cobrar.html", "atrib_protesto_ficha.html"):
        html = (RAIZ / "templates" / nome).read_text(encoding="utf-8-sig")
        assert 'value="PG_CRC"' in html, nome
        assert ROTULO in html, nome
    fonte = (RAIZ / "templates" / "caixa_protocolo.html").read_text(encoding="utf-8-sig")
    assert "FORMAS.items()" in fonte
    renderizado = Template(
        '{% for cod, rotulo in FORMAS.items() %}'
        '<option value="{{ cod }}">{{ rotulo }}</option>{% endfor %}'
    ).render(FORMAS=CX.FORMAS_PAGAMENTO)
    assert 'value="PG_CRC"' in renderizado
    assert ROTULO in renderizado


def test_livro_de_pagamentos_tem_pg_crc():
    assert PT.FORMAS_DE_PAGAMENTO["PG_CRC"] == ROTULO
    peca = (RAIZ / "modelos_padrao" / "protesto" / "PT_LIVRO_PAGAMENTOS.txt"
            ).read_text(encoding="utf-8-sig")
    assert f"PG_CRC = {ROTULO}" in peca
    assert PECAS.vocabulario(None, "PT_LIVRO_PAGAMENTOS")["PG_CRC"] == ROTULO


def test_ficha_do_protesto_oferece_pg_crc_no_select_do_livro():
    """O 2º select (ato PAGAMENTO / Livro de Pagamentos), não o do emolumento."""
    html = (RAIZ / "templates" / "atrib_protesto_ficha.html").read_text(
        encoding="utf-8-sig")
    trecho = re.search(
        r"\{%\s*for k, rotulo in \(\((.*?)\)\)\s*%\}.*?O Livro de Pagamentos exige",
        html, flags=re.S)
    assert trecho, "select do Livro de Pagamentos não achado"
    opcoes = trecho.group(1)
    assert "'PG_CRC'" in opcoes or '"PG_CRC"' in opcoes
    assert ROTULO in opcoes


def test_lancar_pagamento_pg_crc_grava_e_aparece_no_livro(s):
    tid = titulo_apontado(s)
    con = _con(s)
    with con:
        PT.lancar_intimacao(con, tid, modo="PESSOAL", agora="2026-10-10T10:00:00")
        PT.lancar_pagamento(
            con, tid, sv=SV, agora="2026-10-14T10:00:00", data_extenso="x",
            valor_pago="1.310,45", emolumentos="82,64",
            forma_pagamento="PG_CRC",
            forma_identificacao="comprovante CRC ficticio 1")
    assert PT.titulo(con, tid)["situacao"] == "PAGO"
    atos = [a for a in PT.atos_do(con, tid) if a["tipo"] == "PAGAMENTO"]
    assert atos
    detalhe = json.loads(atos[-1]["detalhe_json"] or "{}")
    assert detalhe["forma_pagamento"] == "PG_CRC"
    linhas = PLIV.livro_de_pagamentos(con, de="2026-10-01", ate="2026-10-31")
    assert len(linhas) == 1
    assert ROTULO in linhas[0]["ocorrencias"]
    assert "comprovante CRC ficticio 1" in linhas[0]["ocorrencias"]
    con.close()


def test_carne_leao_pg_crc_conta_como_receita(cg_casa):
    db = cg_casa["db"]
    with db.transaction() as con:
        CL.cadastrar_tabela(
            con, vigencia_inicio="2026-01-01", descricao="Fictícia PG_CRC",
            fonte="Tabela fictícia do teste",
            faixas_texto="1.000,00; 0; 0\n2.000,00; 10; 100,00\n; 20; 300,00",
            por="mario", agora="2026-10-26T10:00:00")
        banco(con).escrever(
            """INSERT INTO cx_lancamentos (data, natureza, sentido, forma_pagamento,
                   descricao, valor, emolumentos, criado_em, estornado)
               VALUES ('2026-09-12', 'RECEBIMENTO', 'ENTRADA', 'PG_CRC',
                       'Certidão CRC', '112,00', '100,00',
                       '2026-09-12T10:00:00', 0)""")
    with db.connect() as con:
        a = CL.apurar(con, "2026-09")
    assert a["caixa"] == 10000


# ------------------------------------------------- a cobertura CENTRAL_CRC


def _caixa_aberto(con) -> int:
    novo = banco(con).escrever(
        """INSERT INTO cx_caixas (data, operador_nome, saldo_inicial, aberto_em, situacao)
           VALUES ('2026-10-19', 'CAIXA DE TESTE', '0', %s, 'ABERTO')
           RETURNING id""", (SC.AGORA,))
    con.commit()
    return int(novo[0]["id"])


def test_central_crc_nao_e_forma_de_pagamento():
    assert AS.FORMA_CENTRAL_CRC == "CENTRAL_CRC"
    assert AS.FORMA_CENTRAL_CRC in AS.FORMAS_QUE_COBREM
    assert AS.FORMA_CENTRAL_CRC not in CX.FORMAS_PAGAMENTO
    assert "PG_CRC" not in AS.FORMAS_QUE_COBREM


def test_certidao_eletronica_14_5_7_segue_pelo_caminho_dela(cg_casa):
    """Sem protocolo pago e sem lançamento: quem cobre é a CENTRAL_CRC."""
    with ligar_o_selador(cg_casa, protocolo_pago=False) as selador:
        sessao = RC._sessao(cg_casa)
        assento = RC._semear(sessao)
        CRC._emitir_selo_crc(sessao, assento, requerente="BEATRIZ EXEMPLO")
        selos = [p for p in selador.pedidos if p["caminho"].startswith("/selo/")]
    assert len(selos) == 1
    assert selos[0]["caminho"] == AS.CAMINHO_CERTIDAO_ELETRONICA_CRC
    assert json.loads(selos[0]["corpo"])["codigoAto"] == AS.CODIGO_CERTIDAO_ELETRONICA_CRC
    con = RC._con(sessao)
    certidao = con.execute(
        "SELECT * FROM rc_certidoes ORDER BY id DESC LIMIT 1").fetchone()
    cobertura = con.execute(
        "SELECT forma FROM cx_selo_coberturas WHERE tabela='rc_certidoes' AND ato_id=?",
        (certidao["id"],)).fetchone()
    com_a_forma = con.execute(
        "SELECT COUNT(*) FROM cx_lancamentos WHERE forma_pagamento='PG_CRC'").fetchone()[0]
    con.close()
    assert certidao["selo"] and not certidao["cancelada_em"]
    assert cobertura["forma"] == AS.FORMA_CENTRAL_CRC
    assert com_a_forma == 0


def test_protocolo_pago_com_pg_crc_cobre_o_selo_so_pela_trava_normal(aparelho):
    con = SC._casa()
    protocolo = SC._protocolo(con)
    item = SC._item(con, protocolo["protocolo_id"])
    SC._ligar(con, item)
    CX.cobrar_item_do_protocolo(
        con, item, caixa_id=_caixa_aberto(con), agora=SC.AGORA,
        hoje=SC.AGORA[:10], hora=SC.AGORA[11:16], forma_pagamento="PG_CRC")
    con.commit()
    assert SC._selar(con)["selado"] is True
    assert len(aparelho) == 1
    forma = banco(con).valor("SELECT forma FROM cx_selo_coberturas WHERE ato_id = 1")
    assert forma == AS.FORMA_ITEM_PAGO


def test_lancamento_pg_crc_sem_item_pago_nao_libera_o_selo(aparelho):
    """A forma não abre a trava: o item ligado ao ato continua em aberto."""
    con = SC._casa()
    protocolo = SC._protocolo(con)
    SC._ligar(con, SC._item(con, protocolo["protocolo_id"]))
    banco(con).escrever(
        """INSERT INTO cx_lancamentos (caixa_id, protocolo_id, data, natureza, sentido,
               forma_pagamento, descricao, valor, criado_em)
           VALUES (%s, %s, '2026-10-19', 'RECEBIMENTO', 'ENTRADA', 'PG_CRC',
                   'Pedido CRC', '80,00', %s)""",
        (_caixa_aberto(con), protocolo["protocolo_id"], SC.AGORA))
    con.commit()
    assert SC._selar(con)["selado"] is False
    assert aparelho == []
    assert banco(con).valor(
        "SELECT COUNT(*) FROM cx_selo_coberturas WHERE situacao = 'CONFIRMADA'") == 0
