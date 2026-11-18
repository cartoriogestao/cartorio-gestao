"""Forma de pagamento PG_ONR — «PG feito pela ONR».

Decisão da oficial da casa em 18/11/2026: entra no saldo e
como receita, igual ao PIX; não entra em espécie; vale no Protocolo Geral, no
Caixa e nos Depósitos; carnê-leão conta como receita normal.

Em 18/11/2026 o mesmo código e rótulo passam a valer no Livro de Pagamentos
do protesto (select da ficha, validação, gravação e peça do livro).
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest
from jinja2 import Template

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

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

AGORA = "2026-09-20T10:00:00"
ROTULO = "PG feito pela ONR"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "endereco_completo": "Rua Grande, 1, Centro",
      "serventia_telefone": "(99) 0000-0000",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}


def test_formas_pagamento_tem_pg_onr():
    assert CX.FORMAS_PAGAMENTO["PG_ONR"] == ROTULO


def test_resumo_caixa_pg_onr_entra_no_saldo_e_nao_em_especie():
    resumo = CX.resumo_caixa([
        {"sentido": "ENTRADA", "valor": "100,00", "forma_pagamento": "PG_ONR"},
        {"sentido": "ENTRADA", "valor": "50,00", "forma_pagamento": "DINHEIRO"},
    ], saldo_inicial=0)
    assert resumo["entradas"] == 15000
    assert resumo["saldo"] == 15000
    assert resumo["por_forma"]["PG_ONR"] == 10000
    assert resumo["em_especie"] == 5000


def test_fechamento_automatico_trata_pg_onr_como_eletronica(cg_casa):
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
               VALUES (%s,'2026-11-15','RECEBIMENTO','ENTRADA','PG_ONR',
                       '10,00','2026-11-15T10:00:00')""",
            (cid,))
        caixa = banco(con).um("SELECT * FROM cx_caixas WHERE id=%s", (cid,))
        _resumo, precisa_contar = CA._medir(con, caixa)
    assert precisa_contar is False
    assert "PG_ONR" in CA.FORMAS_ELETRONICAS


def test_pg_onr_nao_e_pagamento_por_fora():
    cfg = {"cobranca_ligada": "1", "cobranca_banco": "PARCELA"}
    assert CB.conferir_pagamento_por_fora(
        "PG_ONR", cfg, afirmo=False, afirmacao="", ciencia=False) is None
    assert "PG_ONR" in CB.FORMAS_DE_DENTRO


def test_gestor_financeiro_nomeia_pg_onr(cg_casa):
    caminho = cg_casa["banco"]
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    con.execute(
        """INSERT INTO cx_lancamentos (data, natureza, sentido, forma_pagamento,
               descricao, valor, criado_em, estornado)
           VALUES ('2026-09-20', 'RECEBIMENTO', 'ENTRADA', 'PG_ONR',
                   'CERTIDÃO', '80,00', ?, 0)""", (AGORA,))
    con.commit()
    r = GF.apurar_mes(con, 2026, 9)
    con.close()
    assert r["entrou"][ROTULO] == pytest.approx(80.0)


def test_telas_oferecem_a_opcao_pg_onr():
    for nome in ("_cobrar.html", "atrib_protesto_ficha.html"):
        html = (RAIZ / "templates" / nome).read_text(encoding="utf-8-sig")
        assert 'value="PG_ONR"' in html, nome
        assert ROTULO in html, nome
    fonte = (RAIZ / "templates" / "caixa_protocolo.html").read_text(encoding="utf-8-sig")
    assert "FORMAS.items()" in fonte
    renderizado = Template(
        '{% for cod, rotulo in FORMAS.items() %}'
        '<option value="{{ cod }}">{{ rotulo }}</option>{% endfor %}'
    ).render(FORMAS=CX.FORMAS_PAGAMENTO)
    assert 'value="PG_ONR"' in renderizado
    assert ROTULO in renderizado


def test_livro_de_pagamentos_tem_pg_onr():
    assert PT.FORMAS_DE_PAGAMENTO["PG_ONR"] == ROTULO
    peca = (RAIZ / "modelos_padrao" / "protesto" / "PT_LIVRO_PAGAMENTOS.txt"
            ).read_text(encoding="utf-8-sig")
    assert f"PG_ONR = {ROTULO}" in peca
    assert PECAS.vocabulario(None, "PT_LIVRO_PAGAMENTOS")["PG_ONR"] == ROTULO


def test_ficha_do_protesto_oferece_pg_onr_no_select_do_livro():
    """O 2º select (ato PAGAMENTO / Livro de Pagamentos), não o do emolumento."""
    html = (RAIZ / "templates" / "atrib_protesto_ficha.html").read_text(
        encoding="utf-8-sig")
    trecho = re.search(
        r"\{%\s*for k, rotulo in \(\((.*?)\)\)\s*%\}.*?O Livro de Pagamentos exige",
        html, flags=re.S)
    assert trecho, "select do Livro de Pagamentos não achado"
    opcoes = trecho.group(1)
    assert "'PG_ONR'" in opcoes or '"PG_ONR"' in opcoes
    assert ROTULO in opcoes


def test_lancar_pagamento_pg_onr_grava_e_aparece_no_livro(s):
    import json

    tid = titulo_apontado(s)
    con = _con(s)
    with con:
        PT.lancar_intimacao(con, tid, modo="PESSOAL", agora="2026-10-10T10:00:00")
        PT.lancar_pagamento(
            con, tid, sv=SV, agora="2026-10-14T10:00:00", data_extenso="x",
            valor_pago="1.310,45", emolumentos="82,64",
            forma_pagamento="PG_ONR",
            forma_identificacao="comprovante ONR ficticio 1")
    assert PT.titulo(con, tid)["situacao"] == "PAGO"
    atos = [a for a in PT.atos_do(con, tid) if a["tipo"] == "PAGAMENTO"]
    assert atos
    detalhe = json.loads(atos[-1]["detalhe_json"] or "{}")
    assert detalhe["forma_pagamento"] == "PG_ONR"
    linhas = PLIV.livro_de_pagamentos(con, de="2026-10-01", ate="2026-10-31")
    assert len(linhas) == 1
    assert ROTULO in linhas[0]["ocorrencias"]
    assert "comprovante ONR ficticio 1" in linhas[0]["ocorrencias"]
    con.close()


def test_carne_leao_pg_onr_conta_como_receita(cg_casa):
    db = cg_casa["db"]
    with db.transaction() as con:
        CL.cadastrar_tabela(
            con, vigencia_inicio="2026-01-01", descricao="Fictícia PG_ONR",
            fonte="Tabela fictícia do teste",
            faixas_texto="1.000,00; 0; 0\n2.000,00; 10; 100,00\n; 20; 300,00",
            por="mario", agora="2026-10-26T10:00:00")
        banco(con).escrever(
            """INSERT INTO cx_lancamentos (data, natureza, sentido, forma_pagamento,
                   descricao, valor, emolumentos, criado_em, estornado)
               VALUES ('2026-09-12', 'RECEBIMENTO', 'ENTRADA', 'PG_ONR',
                       'Certidão ONR', '112,00', '100,00',
                       '2026-09-12T10:00:00', 0)""")
    with db.connect() as con:
        a = CL.apurar(con, "2026-09")
    assert a["caixa"] == 10000
