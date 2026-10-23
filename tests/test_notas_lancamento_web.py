"""
O lancamento do ato no livro, pelas telas.

POR QUE TESTE DE ROTA, E NAO SO DE MODULO
    A regra de numeracao esta em `notas_livro.py` e tem teste proprio. O que
    ESTES testes protegem e o caminho que o escrevente percorre: abrir o ato,
    escrever o teor, lancar. Foi ai que estavam os defeitos que motivaram a
    mudanca — a folha digitada a mao, e o "Guardar o teor" que apagava a folha
    quando o campo vinha vazio.

    O modulo de notas nao tinha teste de rota nenhum. Agora tem.
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
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def serventia(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")

    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    bancada = {"app": app, "cliente": c, "banco": banco,
               "db": cg_casa["db"], "dados": dados}
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(bancada):
        yield bancada


def tela(s, caminho: str) -> str:
    return s["cliente"].get(caminho).get_data(as_text=True)


def ato_no_banco(s, ato_id: int) -> dict:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    linha = con.execute("SELECT * FROM nt_atos WHERE id=?", (ato_id,)).fetchone()
    con.close()
    return dict(linha)


def abrir_ato(s, tipo="ESCRITURA") -> int:
    html = tela(s, "/notas/atos/novo")
    s["cliente"].post("/notas/atos/novo",
                      data={"csrf_token": _token(html), "tipo": tipo,
                            "interessado": "MARIA DAS DORES"},
                      follow_redirects=True)
    con = sqlite3.connect(s["banco"])
    ato_id = con.execute("SELECT MAX(id) FROM nt_atos").fetchone()[0]
    con.close()
    return int(ato_id)


def acao(s, ato_id: int, **dados):
    html = tela(s, f"/notas/atos/{ato_id}")
    dados.setdefault("csrf_token", _token(html))
    if dados.get("acao") == "lancar":
        dados.setdefault("codigo_tj", "13.2")
        # A trava da CENSEC (09/10/2026) — ver `notas_pronto_para_a_censec`.
        from notas_pronto_para_a_censec import preparar
        preparar(s["banco"], ato_id)
    return s["cliente"].post(f"/notas/atos/{ato_id}", data=dados,
                             follow_redirects=True)


# ------------------------------------------------------------- abertura

def test_o_ato_nasce_em_lavratura_sem_livro_nem_folha(serventia):
    a = ato_no_banco(serventia, abrir_ato(serventia))
    assert a["situacao"] == "EM_LAVRATURA"
    assert a["livro_id"] is None and a["folha"] is None and a["termo"] is None


def test_a_tela_de_abrir_nao_pede_mais_folha(serventia):
    html = tela(serventia, "/notas/atos/novo")
    assert 'name="folha"' not in html
    assert 'name="livro_id"' not in html


def test_a_tela_mostra_para_onde_o_ato_vai_antes_de_abrir(serventia):
    html = tela(serventia, "/notas/atos/novo")
    assert "Para onde cada ato vai" in html
    assert "Escrituras" in html


# ------------------------------------------------------------- teor

def test_guardar_o_teor_nao_apaga_mais_a_folha(serventia):
    """O defeito que motivou tudo isto.

    Antes, `UPDATE nt_atos SET teor=?, folha=?, ...` rodava com o campo Folha
    do formulario. Corrigir uma virgula no teor apagava a folha do ato.
    """
    ato_id = abrir_ato(serventia)
    acao(serventia, ato_id, acao="teor", teor="<p>primeira versao</p>")
    acao(serventia, ato_id, acao="lancar", paginas=2)
    antes = ato_no_banco(serventia, ato_id)
    assert antes["folha"] == "1" and antes["termo"] == 1

    # Agora corrige o teor, sem mandar folha nenhuma — como o formulario faz.
    acao(serventia, ato_id, acao="teor", teor="<p>segunda versao, sem virgula</p>")
    depois = ato_no_banco(serventia, ato_id)
    assert depois["folha"] == "1"
    assert depois["folha_final"] == antes["folha_final"]
    assert depois["termo"] == 1
    # E O TEOR DO ATO LANÇADO FICA COMO FOI PARA O LIVRO (LX12, LS02 M10): o
    # formulário não o regrava mais — corrigir ato lançado é retificação.
    assert "primeira versao" in depois["teor"]


def test_a_tela_do_teor_nao_tem_mais_campo_de_folha(serventia):
    ato_id = abrir_ato(serventia)
    html = tela(serventia, f"/notas/atos/{ato_id}")
    assert 'name="folha_final"' not in html
    # 07/10/2026, ordem do oficial: as páginas não se perguntam mais — o
    # sistema mede no termo ao lançar. O campo só volta quando a medição falha.
    assert 'name="paginas"' not in html
    html = tela(serventia, f"/notas/atos/{ato_id}?paginas_a_mao=1")
    assert 'name="paginas"' in html


# ------------------------------------------------------------- lancamento

def test_o_lancamento_atribui_livro_folha_e_termo(serventia):
    ato_id = abrir_ato(serventia)
    acao(serventia, ato_id, acao="teor", teor="<p>teor do ato</p>")
    resposta = acao(serventia, ato_id, acao="lancar", paginas=4)
    html = resposta.get_data(as_text=True)
    assert "Lançado no livro 1, folha 1 a 2v, termo nº 1" in html

    a = ato_no_banco(serventia, ato_id)
    assert a["situacao"] == "LAVRADO"
    assert (a["livro"], a["folha"], a["folha_final"]) == ("1", "1", "2v")
    assert (a["termo"], a["folhas"], a["paginas"]) == (1, 2, 4)
    assert a["lancado_por"] == "MARIO EXEMPLO DOS SANTOS"


def test_o_primeiro_lancamento_abre_o_livro_com_termo_de_abertura(serventia):
    ato_id = abrir_ato(serventia)
    acao(serventia, ato_id, acao="teor", teor="<p>x</p>")
    acao(serventia, ato_id, acao="lancar", paginas=2)
    con = sqlite3.connect(serventia["banco"])
    con.row_factory = sqlite3.Row
    livro = con.execute("SELECT * FROM nt_livros").fetchone()
    con.close()
    assert livro["numero"] == "1" and livro["automatico"] == 1
    assert "TERMO DE ABERTURA" in livro["termo_abertura"]
    assert "000000" in livro["termo_abertura"]


def test_o_aviso_do_verso_a_inutilizar_aparece_na_tela(serventia):
    ato_id = abrir_ato(serventia)
    acao(serventia, ato_id, acao="teor", teor="<p>x</p>")
    html = acao(serventia, ato_id, acao="lancar", paginas=3).get_data(as_text=True)
    # 07/10/2026: o verso não se inutiliza mais à parte — ele sai no fim do
    # Termo do livro, e o recado diz isso.
    assert "verso" in html and "inutilizado" in html.lower()
    assert "Termo do livro" in html
    assert "795" in html                       # o fundamento vai no recado


def test_dois_atos_nao_pegam_a_mesma_folha_pela_tela(serventia):
    folhas = []
    for _ in range(3):
        ato_id = abrir_ato(serventia)
        acao(serventia, ato_id, acao="teor", teor="<p>x</p>")
        acao(serventia, ato_id, acao="lancar", paginas=2)
        folhas.append(ato_no_banco(serventia, ato_id)["folha"])
    assert folhas == ["1", "2", "3"]


def test_o_ato_lancado_nao_se_relanca_pela_tela(serventia):
    ato_id = abrir_ato(serventia)
    acao(serventia, ato_id, acao="teor", teor="<p>x</p>")
    acao(serventia, ato_id, acao="lancar", paginas=2)
    html = acao(serventia, ato_id, acao="lancar", paginas=2).get_data(as_text=True)
    assert "já está lançado" in html
    assert ato_no_banco(serventia, ato_id)["folha"] == "1"


def test_a_tela_do_ato_lancado_mostra_livro_folha_e_termo(serventia):
    ato_id = abrir_ato(serventia)
    acao(serventia, ato_id, acao="teor", teor="<p>x</p>")
    acao(serventia, ato_id, acao="lancar", paginas=2)
    html = tela(serventia, f"/notas/atos/{ato_id}")
    assert "termo nº 1" in html
    assert "Livro, folha e termo" in html
    assert 'name="paginas"' not in html        # nao se lanca duas vezes


def test_o_lancamento_fica_na_auditoria(serventia):
    ato_id = abrir_ato(serventia)
    acao(serventia, ato_id, acao="teor", teor="<p>x</p>")
    acao(serventia, ato_id, acao="lancar", paginas=2)
    con = sqlite3.connect(serventia["banco"])
    con.row_factory = sqlite3.Row
    linha = con.execute("""SELECT * FROM audit_logs WHERE action='NT_ATO_LANCADO'
                           ORDER BY id DESC LIMIT 1""").fetchone()
    con.close()
    assert linha is not None
    assert '"folha": "1"' in linha["details"]
    assert '"termo": 1' in linha["details"]


def test_nao_se_marca_lavrado_a_mao_sem_lancar(serventia):
    ato_id = abrir_ato(serventia)
    html = acao(serventia, ato_id, acao="situacao", situacao="LAVRADO",
                motivo="").get_data(as_text=True)
    assert "ainda não foi lançado no livro" in html
    assert ato_no_banco(serventia, ato_id)["situacao"] == "EM_LAVRATURA"


def test_ato_em_lavratura_nao_entra_na_remessa(serventia):
    """A separacao da CENSEC filtra por LAVRADO. Rascunho fica de fora."""
    from datetime import date

    import notas_censec as NC
    abrir_ato(serventia)
    hoje = date.today()
    con = sqlite3.connect(serventia["banco"])
    con.row_factory = sqlite3.Row
    resultado = NC.separar(con, "CEP", hoje.year, hoje.month,
                           1 if hoje.day <= 15 else 2)
    con.close()
    assert resultado["aptos"] == [] and resultado["impedidos"] == []


# ------------------------------------------------------------- livros

def test_a_tela_de_livros_mostra_a_folha_de_verdade(serventia):
    """Antes dizia sempre "1 de 200", mesmo com o livro na folha 139."""
    for _ in range(3):
        ato_id = abrir_ato(serventia)
        acao(serventia, ato_id, acao="teor", teor="<p>x</p>")
        acao(serventia, ato_id, acao="lancar", paginas=2)
    html = tela(serventia, "/notas/livros")
    assert "3 de 200" in html                  # tres folhas usadas


def test_a_conferencia_do_livro_responde_sem_reclamar(serventia):
    ato_id = abrir_ato(serventia)
    acao(serventia, ato_id, acao="teor", teor="<p>x</p>")
    acao(serventia, ato_id, acao="lancar", paginas=2)
    con = sqlite3.connect(serventia["banco"])
    lid = con.execute("SELECT id FROM nt_livros").fetchone()[0]
    con.close()
    html = tela(serventia, f"/notas/livros/{lid}/conferir")
    resposta = serventia["cliente"].get(f"/notas/livros/{lid}/conferir",
                                        follow_redirects=True)
    assert "numeração seguida" in resposta.get_data(as_text=True)
    assert html is not None


def test_o_termo_de_abertura_sai_em_odt(serventia):
    ato_id = abrir_ato(serventia)
    acao(serventia, ato_id, acao="teor", teor="<p>x</p>")
    acao(serventia, ato_id, acao="lancar", paginas=2)
    con = sqlite3.connect(serventia["banco"])
    lid = con.execute("SELECT id FROM nt_livros").fetchone()[0]
    con.close()
    resposta = serventia["cliente"].get(f"/notas/livros/{lid}/termo/abertura")
    assert resposta.status_code == 200
    assert resposta.mimetype == "application/vnd.oasis.opendocument.text"
    assert resposta.data[:2] == b"PK"          # e um .odt de verdade


def test_abrir_livro_sem_numero_pega_o_proximo_da_serie(serventia):
    html = tela(serventia, "/notas/livros")
    serventia["cliente"].post("/notas/livros",
                              data={"csrf_token": _token(html), "acao": "abrir",
                                    "tipo": "PROCURACAO", "numero": "",
                                    "folhas": "200"},
                              follow_redirects=True)
    con = sqlite3.connect(serventia["banco"])
    con.row_factory = sqlite3.Row
    livro = con.execute("SELECT * FROM nt_livros WHERE tipo='PROCURACAO'").fetchone()
    con.close()
    assert livro["numero"] == "1"
    assert "TERMO DE ABERTURA" in livro["termo_abertura"]


# ------------------------------------------------------------- o acervo, pela tela
#
# A revisão adversarial de 17/08/2026 mostrou que a tela CONVIDAVA a estragar
# o acervo: como o ato de 2011 não tem `termo`, o cabeçalho dizia "em
# lavratura", o painel caía no ramo do rascunho, e o botão "Lançar no livro"
# aparecia. Um clique reescrevia a folha 139.

def ato_do_acervo(s, situacao="LAVRADO", livro="27", folha="139",
                  numero_ordem=100, tipo="ESCRITURA") -> int:
    con = sqlite3.connect(s["banco"])
    cur = con.execute(
        """INSERT INTO nt_atos(tipo, data, livro, folha, folha_final,
                               numero_ordem, situacao, teor, criado_em)
           VALUES (?, '2011-05-04', ?, ?, ?, ?, ?, '<p>teor antigo</p>',
                   '2026-08-17T09:00:00')""",
        (tipo, livro, folha, folha, numero_ordem, situacao))
    con.commit()
    ato_id = int(cur.lastrowid)
    con.close()
    return ato_id


def test_a_tela_nao_oferece_lancar_para_ato_do_acervo(serventia):
    ato_id = ato_do_acervo(serventia)
    html = tela(serventia, f"/notas/atos/{ato_id}")
    assert "em lavratura" not in html
    assert 'value="lancar"' not in html
    assert "livro 27, folha 139" in html


def test_lancar_ato_do_acervo_pela_tela_e_recusado(serventia):
    ato_id = ato_do_acervo(serventia)
    html = acao(serventia, ato_id, acao="lancar", paginas=4).get_data(as_text=True)
    assert "já está lançado" in html
    a = ato_no_banco(serventia, ato_id)
    assert (a["livro"], a["folha"], a["numero_ordem"]) == ("27", "139", 100)


def test_procuracao_revogada_do_acervo_nao_volta_a_valer(serventia):
    ato_id = ato_do_acervo(serventia, situacao="REVOGADO", folha="88",
                           numero_ordem=77, tipo="PROCURACAO")
    acao(serventia, ato_id, acao="lancar", paginas=2)
    a = ato_no_banco(serventia, ato_id)
    assert a["situacao"] == "REVOGADO" and a["folha"] == "88"


def test_traslado_de_ato_em_lavratura_e_recusado(serventia):
    ato_id = abrir_ato(serventia)
    acao(serventia, ato_id, acao="teor", teor="<p>teor pronto</p>")
    html = tela(serventia, f"/notas/atos/{ato_id}")
    assert "Traslado (.odt)" not in html          # o botão nem aparece
    assert "Termo do livro (.odt)" not in html
    resposta = serventia["cliente"].get(f"/notas/atos/{ato_id}/traslado",
                                        follow_redirects=True)
    corpo = resposta.get_data(as_text=True)
    assert "ainda não foi lançado no livro" in corpo
    assert resposta.mimetype == "text/html"      # não saiu .odt nenhum
    resp_termo = serventia["cliente"].get(
        f"/notas/atos/{ato_id}/termo-livro", follow_redirects=True)
    corpo_t = resp_termo.get_data(as_text=True)
    assert "ainda não foi lançado no livro" in corpo_t
    assert resp_termo.mimetype == "text/html"


# ------------------------------------------------------------- perfil de auditoria

@pytest.fixture()
def auditor(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    d = cg_casa['db']
    d.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    d.create_user("corregedor", "CORREGEDORIA", SENHA, "AUDITOR")

    def entrar(quem):
        c = app.test_client()
        c.post("/login",
               data={"username": quem, "password": SENHA,
                     "csrf_token": _token(c.get("/login").get_data(as_text=True))},
               follow_redirects=True)
        return c
    return {"app": app, "banco": banco, "cliente": entrar("tabeliao"),
            "fiscal": entrar("corregedor")}


def test_o_auditor_ve_mas_nao_lanca(auditor):
    ato_id = abrir_ato(auditor)
    acao(auditor, ato_id, acao="teor", teor="<p>x</p>")

    fiscal = auditor["fiscal"]
    html = fiscal.get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    assert html                                   # ele enxerga a tela
    resposta = fiscal.post(f"/notas/atos/{ato_id}",
                           data={"csrf_token": _token(html), "acao": "lancar",
                                 "paginas": "2"}, follow_redirects=True)
    assert "não pratica ato" in resposta.get_data(as_text=True)
    assert ato_no_banco(auditor, ato_id)["termo"] is None


def test_as_telas_de_leitura_nao_mexem_nos_livros_nem_na_numeracao(auditor):
    """GET é leitura — pelo menos no que diz respeito ao tabelionato.

    A primeira versão desta rodada abria `db.transaction()` no GET para
    reconciliar `folha_atual` e semear o contador de termos. Transação no GET
    é BEGIN IMMEDIATE: com outro balcão lavrando, a tela ficava dez segundos
    no busy_timeout e devolvia 500 — numa página que ninguém pediu para
    escrever. E o AUDITOR, perfil de leitura, gravava ao abri-la.

    RESSALVA HONESTA: este teste olha `nt_livros`, `nt_termos` e `nt_atos`, e
    não o banco inteiro. O `before_request` do `app.py` chama
    `ensure_recurring_tasks` e `ensure_overdue_escalations` em TODA
    requisição, e as duas abrem transação de escrita — defeito anterior a
    esta rodada, que vale para o sistema todo e está anotado na revisão.
    """
    ato_id = abrir_ato(auditor)
    acao(auditor, ato_id, acao="teor", teor="<p>x</p>")
    acao(auditor, ato_id, acao="lancar", paginas=2)

    def retrato():
        con = sqlite3.connect(auditor["banco"])
        con.row_factory = sqlite3.Row
        estado = tuple(
            [dict(r) for r in con.execute(f"SELECT * FROM {tabela} ORDER BY 1")]
            for tabela in ("nt_livros", "nt_termos", "nt_atos"))
        con.close()
        return estado

    antes = retrato()
    # `/notas/atos/novo` é 403 para o AUDITOR pelo `roles_required` — abrir ato
    # não é trabalho de correição. As demais ele vê.
    assert auditor["fiscal"].get("/notas/atos/novo").status_code == 403
    for quem, caminhos in (
            ("cliente", ("/notas/livros", "/notas/atos/novo",
                         f"/notas/atos/{ato_id}", "/notas")),
            ("fiscal", ("/notas/livros", f"/notas/atos/{ato_id}", "/notas"))):
        for caminho in caminhos:
            assert auditor[quem].get(caminho).status_code == 200, (quem, caminho)
    assert retrato() == antes


def test_conferir_o_livro_tambem_nao_mexe_em_nada(auditor):
    ato_id = abrir_ato(auditor)
    acao(auditor, ato_id, acao="teor", teor="<p>x</p>")
    acao(auditor, ato_id, acao="lancar", paginas=2)
    con = sqlite3.connect(auditor["banco"])
    lid = con.execute("SELECT id FROM nt_livros").fetchone()[0]
    antes = con.execute("SELECT folha_atual FROM nt_livros WHERE id=?",
                        (lid,)).fetchone()[0]
    con.close()

    auditor["fiscal"].get(f"/notas/livros/{lid}/conferir", follow_redirects=True)

    con = sqlite3.connect(auditor["banco"])
    depois = con.execute("SELECT folha_atual FROM nt_livros WHERE id=?",
                         (lid,)).fetchone()[0]
    con.close()
    assert depois == antes


def test_o_auditor_nao_abre_nem_encerra_livro(auditor):
    fiscal = auditor["fiscal"]
    html = fiscal.get("/notas/livros").get_data(as_text=True)
    resposta = fiscal.post("/notas/livros",
                           data={"csrf_token": _token(html), "acao": "abrir",
                                 "tipo": "ATA", "folhas": "200"},
                           follow_redirects=True)
    assert "não abre nem encerra livro" in resposta.get_data(as_text=True)
    con = sqlite3.connect(auditor["banco"])
    quantos = con.execute("SELECT COUNT(*) FROM nt_livros WHERE tipo='ATA'").fetchone()[0]
    con.close()
    assert quantos == 0


# ------------------------------------------------------------- borda no formulário

def test_paginas_invalidas_nao_derrubam_a_tela(serventia):
    ato_id = abrir_ato(serventia)
    acao(serventia, ato_id, acao="teor", teor="<p>x</p>")
    for ruim in ("0", "-3", "abc", "9999999"):
        resposta = acao(serventia, ato_id, acao="lancar", paginas=ruim)
        assert resposta.status_code == 200, ruim
        assert ato_no_banco(serventia, ato_id)["termo"] is None, ruim


def test_livro_com_folhas_absurdas_nao_derruba_a_tela(serventia):
    html = tela(serventia, "/notas/livros")
    resposta = serventia["cliente"].post(
        "/notas/livros", data={"csrf_token": _token(html), "acao": "abrir",
                               "tipo": "ATA", "folhas": "10000000"},
        follow_redirects=True)
    assert resposta.status_code == 200
    assert "plausível" in resposta.get_data(as_text=True)
