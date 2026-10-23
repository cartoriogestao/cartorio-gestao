"""
O revisor da procuração — ordem do oficial em 13/10/2026: «coloque revisor de
procuracao pelo sonnet, obrigando que todos campos do ato sejam preenchidos no
sistema, para nao ocorrer esse problema de novo».

O PROBLEMA QUE A PEDIU: a procuração 791 (livro 28, fl. 47) foi lavrada com o
procurador só no termo impresso. O texto guardado ficou com o colchete do
modelo e o quadro «Partes», sem o procurador — e a CENSEC recusou.

São duas coisas, e elas não se confundem:
    - a TRAVA é regra fixa (`notas_web._travas_da_procuracao`): sem outorgante,
      sem outorgado, com cadastro incompleto ou com parte que não aparece no
      texto, a procuração não lavra — e isso não depende da IA responder;
    - o REVISOR é o Sonnet (`revisao_previa.modelo_e_instrucao`), com instrução
      própria, que lê o texto contra o cadastro inteiro das partes.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import revisao_previa as RV  # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def serventia(cg_casa):
    app = cg_casa["app"]
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    bancada = {"app": app, "cliente": c, "banco": cg_casa["banco"],
               "db": cg_casa["db"], "dados": cg_casa["dados"]}
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(bancada):
        yield bancada


def _sql(banco, comando, args=()):
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    cur = con.execute(comando, args)
    linhas = [dict(r) for r in cur.fetchall()]
    con.commit()
    con.close()
    return linhas


def _abrir(s, tipo="PROCURACAO") -> int:
    html = s["cliente"].get("/notas/atos/novo").get_data(as_text=True)
    s["cliente"].post("/notas/atos/novo",
                      data={"csrf_token": _token(html), "tipo": tipo,
                            "interessado": "MARIA DAS DORES"},
                      follow_redirects=True)
    aid = int(_sql(s["banco"], "SELECT MAX(id) id FROM nt_atos")[0]["id"])
    if tipo == "ESCRITURA":
        _sql(s["banco"], "UPDATE nt_atos SET valor_transacao=0, natureza_censec=14 WHERE id=?",
             (aid,))
    return aid


def _parte(banco, aid, nome, qualificacao, completa=True):
    # Completa, desde o LD07 (21/10/2026), tem também o documento de
    # identidade e a união estável que o CNN art. 111 pôs na qualificação.
    campos = ("12345678909", "brasileira", "solteira", "lavradora",
              "Rua Grande, 10, Cidade Exemplo/MA", "1234567 SSP/MA",
              "NAO") if completa else (None,) * 7
    _sql(banco, """INSERT INTO nt_ato_partes(ato_id, nome, nome_norm, qualificacao,
                       documento, nacionalidade, estado_civil, profissao, endereco,
                       identidade, uniao_estavel, tipo_pessoa, testemunha, ordem,
                       criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,'F',0,1,'2026-10-13T00:00:00')""",
         (aid, nome, nome.lower(), qualificacao, *campos))


def _postar(s, aid, **dados) -> str:
    html = s["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    dados.setdefault("csrf_token", _token(html))
    if dados.get("acao") == "lancar":
        dados.setdefault("codigo_tj", "13.2")
        dados.setdefault("paginas", "2")
    return s["cliente"].post(f"/notas/atos/{aid}", data=dados,
                             follow_redirects=True).get_data(as_text=True)


def _situacao(s, aid):
    return _sql(s["banco"], "SELECT situacao FROM nt_atos WHERE id=?", (aid,))[0]["situacao"]


# ------------------------------------------------------------- a trava fixa

def test_procuracao_sem_procurador_no_quadro_nao_lavra(serventia):
    """O caso da 791: o procurador só no papel, e não no sistema."""
    aid = _abrir(serventia)
    _parte(serventia["banco"], aid, "PEDRO EXEMPLO DOS SANTOS", "OUTORGANTE")
    _postar(serventia, aid, acao="teor",
            teor="<p>PEDRO EXEMPLO DOS SANTOS nomeia e constitui seu procurador "
                 "JOSE DA SILVA, a quem confere poderes</p>")
    html = _postar(serventia, aid, acao="lancar")
    assert _situacao(serventia, aid) == "EM_LAVRATURA"
    assert "NÃO lançado" in html and "sem OUTORGADO" in html


def test_cadastro_incompleto_da_parte_nao_lavra(serventia):
    aid = _abrir(serventia)
    _parte(serventia["banco"], aid, "PEDRO EXEMPLO DOS SANTOS", "OUTORGANTE")
    _parte(serventia["banco"], aid, "JOSE DA SILVA", "OUTORGADO", completa=False)
    _postar(serventia, aid, acao="teor",
            teor="<p>PEDRO EXEMPLO DOS SANTOS nomeia e constitui seu procurador "
                 "JOSE DA SILVA, a quem confere poderes</p>")
    html = _postar(serventia, aid, acao="lancar")
    assert _situacao(serventia, aid) == "EM_LAVRATURA"
    assert "cadastro incompleto" in html and "JOSE DA SILVA" in html


def test_parte_do_quadro_que_nao_esta_no_texto_nao_lavra(serventia):
    aid = _abrir(serventia)
    _parte(serventia["banco"], aid, "PEDRO EXEMPLO DOS SANTOS", "OUTORGANTE")
    _parte(serventia["banco"], aid, "JOSE DA SILVA", "OUTORGADO")
    _postar(serventia, aid, acao="teor",
            teor="<p>PEDRO EXEMPLO DOS SANTOS nomeia e constitui seu procurador "
                 "FULANO DE TAL, a quem confere poderes</p>")
    html = _postar(serventia, aid, acao="lancar")
    assert _situacao(serventia, aid) == "EM_LAVRATURA"
    assert "não aparece no texto" in html


def test_procuracao_completa_nao_bate_na_trava_da_procuracao(serventia):
    aid = _abrir(serventia)
    _parte(serventia["banco"], aid, "PEDRO EXEMPLO DOS SANTOS", "OUTORGANTE")
    _parte(serventia["banco"], aid, "José da Silva", "OUTORGADO")
    _postar(serventia, aid, acao="teor",
            teor="<p>PEDRO EXEMPLO DOS SANTOS nomeia e constitui seu procurador "
                 "JOSÉ DA SILVA, a quem confere poderes</p>")
    html = _postar(serventia, aid, acao="lancar")
    for frase in ("sem OUTORGANTE", "sem OUTORGADO", "cadastro incompleto",
                  "não aparece no texto"):
        assert frase not in html


def test_a_trava_da_procuracao_nao_alcanca_a_escritura(serventia):
    """A ordem foi para a procuração; a escritura tem as travas dela."""
    aid = _abrir(serventia, "ESCRITURA")
    _parte(serventia["banco"], aid, "PEDRO EXEMPLO DOS SANTOS", "OUTORGANTE",
           completa=False)
    _postar(serventia, aid, acao="teor", teor="<p>teor completo do ato</p>")
    html = _postar(serventia, aid, acao="lancar")
    assert "sem OUTORGADO" not in html and "cadastro incompleto" not in html


# ------------------------------------------------------------- o revisor Sonnet

@pytest.fixture()
def con(cg_casa):
    c = sqlite3.connect(cg_casa["banco"])
    RV.init_schema(c)
    yield c
    c.close()


def _ato_de_notas(con, tipo):
    aid = con.execute("""INSERT INTO nt_atos(tipo, data, situacao, criado_em)
                         VALUES (?, '2026-10-13', 'EM_LAVRATURA', '2026-10-13T00:00:00')""",
                      (tipo,)).lastrowid
    con.commit()
    return aid


def test_procuracao_e_lida_pelo_sonnet_e_escritura_pelo_opus(con):
    proc = _ato_de_notas(con, "PROCURACAO")
    prev = _ato_de_notas(con, "PROCURACAO_PREVIDENCIARIA")
    escr = _ato_de_notas(con, "ESCRITURA")
    assert RV.modelo_e_instrucao(con, "NOTAS", proc) == (
        RV.MODELO_DA_PROCURACAO, RV.INSTRUCAO_DA_PROCURACAO)
    assert RV.modelo_e_instrucao(con, "NOTAS", prev)[0] == "claude-sonnet-5-5"
    assert RV.modelo_e_instrucao(con, "NOTAS", escr) == (RV.MODELO, RV.INSTRUCAO)
    # o número do RI não é ato de notas, mesmo que coincida com um
    assert RV.modelo_e_instrucao(con, "RI", proc) == (RV.MODELO, RV.INSTRUCAO)


def test_a_leitura_da_procuracao_sai_pelo_sonnet_com_a_instrucao_dela(con, cg_casa):
    aid = _ato_de_notas(con, "PROCURACAO")
    _parte(cg_casa["banco"], aid, "PEDRO EXEMPLO DOS SANTOS", "OUTORGANTE")
    dossie = RV.dossie_notas(con, aid)
    rid, _ = RV.pedir(con, "NOTAS", aid, "h1", dossie, usuario="BEATRIZ")
    con.commit()
    vistos = {}

    def ia(pasta, *, provedor, sistema, conversa, ferramentas, modelo, maximo_de_saida, **_registro):
        vistos.update(modelo=modelo, sistema=sistema)
        return {"texto": '{"achados": [], "parecer": "ok"}', "modelo": None,
                "entrada": 10, "saida": 5}

    RV.executar(Path(cg_casa["banco"]), Path("."), rid, conversar=ia)
    assert vistos["modelo"] == "claude-sonnet-5-5"
    assert vistos["sistema"] == RV.INSTRUCAO_DA_PROCURACAO
    linha = con.execute("SELECT situacao, modelo FROM rv_revisoes WHERE id=?",
                        (rid,)).fetchone()
    assert linha == ("PRONTA", "claude-sonnet-5-5")


def test_o_dossie_leva_o_cadastro_inteiro_das_partes(con, cg_casa):
    aid = _ato_de_notas(con, "PROCURACAO")
    _parte(cg_casa["banco"], aid, "PEDRO EXEMPLO DOS SANTOS", "OUTORGANTE")
    _parte(cg_casa["banco"], aid, "JOSE DA SILVA", "OUTORGADO", completa=False)
    dossie = RV.dossie_notas(con, aid)
    assert "brasileira" in dossie and "lavradora" in dossie and "Rua Grande" in dossie
    # o que falta não some: aparece marcado, para o revisor apontar
    assert "profissão ?" in dossie and "endereço ?" in dossie


def test_procuracao_com_a_fileira_de_x_do_modelo_nao_lavra(serventia):
    """O caso da 802 (14/10/2026): o veículo ficou «XXXXXXXXXXXXXXXXXXX»."""
    aid = _abrir(serventia)
    _parte(serventia["banco"], aid, "PEDRO EXEMPLO DOS SANTOS", "OUTORGANTE")
    _parte(serventia["banco"], aid, "JOSE DA SILVA", "OUTORGADO")
    _postar(serventia, aid, acao="teor",
            teor="<p>PEDRO EXEMPLO DOS SANTOS nomeia e constitui seu procurador "
                 "JOSE DA SILVA, a quem confere poderes para vender o veículo : "
                 "XXXXXXXXXXXXXXXXXXX</p>")
    html = _postar(serventia, aid, acao="lancar")
    assert _situacao(serventia, aid) == "EM_LAVRATURA"
    assert "XXXXXXXXXXXXXXXXXXX" in html and "campo em branco" in html
