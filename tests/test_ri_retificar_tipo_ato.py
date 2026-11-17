"""
Retificar o tipo (R <-> AV) de um ato do RI ja lavrado.

O CASO QUE ORIGINOU (17/11/2026)
    Uma averbacao de retificacao foi lavrada direto na ficha, sem minuta, com
    o «Tipo de ato» no padrao — Registro (R). O teor dizia «AV-03», o selo era
    de averbacao, e a ficha mostrava «R-03». O tipo entra no hash do ato, e o
    hash encadeia os posteriores; nao havia tela para corrigir.

O QUE ESTES TESTES EXIGEM
    - a troca muda so o tipo: numero, teor e selo ficam;
    - a cadeia de hash deste ato e dos posteriores e refeita e volta a
      conferir (`verifica_cadeia`), e os anteriores nao mudam;
    - motivo obrigatorio; ato cancelado, de acervo ou com cadeia ja
      divergente e recusado sem alterar nada;
    - pela tela: so ADMIN; a auditoria guarda tipos, rotulos, hashes e motivo.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import ri_correcoes as RC                                         # noqa: E402
from ri_schema import hash_ato, init_ri_schema, verifica_cadeia   # noqa: E402

AGORA = "2026-11-17T11:00:00"
MOTIVO = "Lavrado como Registro por engano; teor e selo são de averbação"


# ------------------------------------------------------------ modulo


@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.execute("PRAGMA foreign_keys=ON")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    init_ri_schema(c)
    yield c
    c.close()


def matricula(con, numero="4100"):
    cur = con.execute(
        """INSERT INTO ri_matriculas
           (numero, complemento, livro, livro_norm, tipo_ficha, situacao, conferido,
            origem, criado_em, teor_formato)
           VALUES (?,'','2','2','ESTRUTURADA','ATIVA',1,'MANUAL',?,'texto')""",
        (str(numero), AGORA))
    return int(cur.lastrowid)


def ato(con, mid, tipo, numero, teor, *, selo=None, cancelado=0, acervo=0,
        origem="MANUAL", matricula_numero="4100"):
    anterior = con.execute("""SELECT hash_ato FROM ri_atos WHERE matricula_id=?
                              ORDER BY id DESC LIMIT 1""", (mid,)).fetchone()
    ha = anterior["hash_ato"] if anterior else None
    h = hash_ato(matricula_numero, tipo, numero, "2026-11-17", teor, ha)
    cur = con.execute(
        """INSERT INTO ri_atos
           (matricula_id, tipo, numero, data_ato, teor, teor_formato, cancelado,
            acervo, origem, selo_texto, hash_ato, hash_anterior, lavrado_em)
           VALUES (?,?,?,'2026-11-17',?,'texto',?,?,?,?,?,?,?)""",
        (mid, tipo, numero, teor, cancelado, acervo, origem, selo, h, ha, AGORA))
    return int(cur.lastrowid)


def linhas(con, mid):
    return [dict(r) for r in con.execute(
        """SELECT id, tipo, numero, data_ato, teor, selo_texto, hash_ato, hash_anterior
           FROM ri_atos WHERE matricula_id=? ORDER BY id""", (mid,)).fetchall()]


def cadeia(con, mid, numero="4100"):
    return [r | {"matricula_numero": numero} for r in linhas(con, mid)]


def caso_r03_que_e_av03(con):
    """R-01 e AV-02 antes; o «R-03» que e AV-03; o AV-04 encadeado nele."""
    mid = matricula(con)
    a1 = ato(con, mid, "R", 1, "R-01/4.100 COMPRA E VENDA")
    a2 = ato(con, mid, "AV", 2, "AV-02/4.100 CADASTRO")
    a3 = ato(con, mid, "R", 3, "AV-03/4.100 RETIFICAÇÃO E COMPLEMENTAÇÃO",
             selo="AVTESTE0000000000000000000001")
    a4 = ato(con, mid, "AV", 4, "AV-04/4.100 GEORREFERENCIAMENTO",
             selo="AVTESTE0000000000000000000002")
    return mid, (a1, a2, a3, a4)


def test_r03_vira_av03_e_a_cadeia_volta_a_conferir(con):
    mid, (a1, a2, a3, a4) = caso_r03_que_e_av03(con)
    antes = {r["id"]: r for r in linhas(con, mid)}

    saida = RC.retificar_tipo_do_ato(con, a3, "AV", motivo=MOTIVO, agora=AGORA,
                                     usuario="tabeliao")

    depois = {r["id"]: r for r in linhas(con, mid)}
    assert depois[a3]["tipo"] == "AV" and depois[a3]["numero"] == 3
    assert depois[a3]["teor"] == antes[a3]["teor"], "o teor nao muda"
    assert depois[a3]["selo_texto"] == antes[a3]["selo_texto"], "o selo nao muda"
    # os anteriores ficam como estavam
    for i in (a1, a2):
        assert depois[i]["hash_ato"] == antes[i]["hash_ato"]
    # este e o posterior mudam, e o posterior aponta para o hash novo
    assert depois[a3]["hash_ato"] != antes[a3]["hash_ato"]
    assert depois[a4]["hash_ato"] != antes[a4]["hash_ato"]
    assert depois[a3]["hash_anterior"] == depois[a2]["hash_ato"]
    assert depois[a4]["hash_anterior"] == depois[a3]["hash_ato"]
    assert verifica_cadeia(cadeia(con, mid)) == []

    assert saida["rotulo_antigo"] == "R-03" and saida["rotulo_novo"] == "AV-03"
    assert saida["tipo_antigo"] == "R" and saida["tipo_novo"] == "AV"
    assert saida["teor_confere"] is True
    assert [x["id"] for x in saida["atos"]] == [a3, a4]
    assert saida["atos"][0]["hash_antigo"] == antes[a3]["hash_ato"]
    assert saida["atos"][0]["hash_novo"] == depois[a3]["hash_ato"]


def test_sem_retificar_a_cadeia_com_o_tipo_trocado_nao_conferiria(con):
    """Prova de que o recalculo e necessario: so trocar a coluna quebra a cadeia."""
    mid, (_a1, _a2, a3, _a4) = caso_r03_que_e_av03(con)
    con.execute("UPDATE ri_atos SET tipo='AV' WHERE id=?", (a3,))
    assert verifica_cadeia(cadeia(con, mid)), "trocar so a coluna deixa o hash divergente"


def test_volta_de_av_para_r_tambem(con):
    mid = matricula(con)
    a1 = ato(con, mid, "AV", 1, "R-01/4.100 COMPRA E VENDA")
    RC.retificar_tipo_do_ato(con, a1, "R", motivo=MOTIVO, agora=AGORA)
    assert linhas(con, mid)[0]["tipo"] == "R"
    assert verifica_cadeia(cadeia(con, mid)) == []


@pytest.mark.parametrize("motivo", ["", "   ", "curto"])
def test_motivo_obrigatorio(con, motivo):
    mid, (_a1, _a2, a3, _a4) = caso_r03_que_e_av03(con)
    antes = linhas(con, mid)
    with pytest.raises(RC.CorrecaoError, match="motivo"):
        RC.retificar_tipo_do_ato(con, a3, "AV", motivo=motivo, agora=AGORA)
    assert linhas(con, mid) == antes


def test_tipo_invalido_e_mesmo_tipo_sao_recusados(con):
    mid, (_a1, _a2, a3, _a4) = caso_r03_que_e_av03(con)
    with pytest.raises(RC.CorrecaoError, match="Registro .R. ou Averba"):
        RC.retificar_tipo_do_ato(con, a3, "X", motivo=MOTIVO, agora=AGORA)
    with pytest.raises(RC.CorrecaoError, match="já é R-03"):
        RC.retificar_tipo_do_ato(con, a3, "R", motivo=MOTIVO, agora=AGORA)


def test_ato_cancelado_e_recusado(con):
    mid = matricula(con)
    a1 = ato(con, mid, "R", 1, "AV-01 TEXTO", cancelado=1)
    with pytest.raises(RC.CorrecaoError, match="cancelado"):
        RC.retificar_tipo_do_ato(con, a1, "AV", motivo=MOTIVO, agora=AGORA)
    assert linhas(con, mid)[0]["tipo"] == "R"


def test_ato_do_acervo_e_recusado(con):
    mid = matricula(con)
    a1 = ato(con, mid, "R", 1, "AV-01 TEXTO", acervo=1, origem="EOFICIO")
    with pytest.raises(RC.CorrecaoError, match="acervo"):
        RC.retificar_tipo_do_ato(con, a1, "AV", motivo=MOTIVO, agora=AGORA)
    assert linhas(con, mid)[0]["tipo"] == "R"


def test_ato_inexistente_ou_expurgado_e_recusado(con):
    with pytest.raises(RC.CorrecaoError, match="não existe"):
        RC.retificar_tipo_do_ato(con, 999999, "AV", motivo=MOTIVO, agora=AGORA)


def test_cadeia_ja_divergente_e_recusada_sem_mexer(con):
    """Refazer a cadeia por cima de uma divergencia a esconderia."""
    mid, (_a1, a2, a3, _a4) = caso_r03_que_e_av03(con)
    con.execute("UPDATE ri_atos SET teor='AV-02 TEXTO ALTERADO DEPOIS' WHERE id=?", (a2,))
    antes = linhas(con, mid)
    with pytest.raises(RC.CorrecaoError, match="divergente"):
        RC.retificar_tipo_do_ato(con, a3, "AV", motivo=MOTIVO, agora=AGORA)
    assert linhas(con, mid) == antes


def test_numero_ja_ocupado_pelo_tipo_novo_e_recusado(con):
    """O UNIQUE(matricula, tipo, numero) seria a falha crua; a recusa vem antes."""
    mid = matricula(con)
    ato(con, mid, "AV", 1, "AV-01 TEXTO")
    a2 = ato(con, mid, "R", 1, "R-01 TEXTO")
    with pytest.raises(RC.CorrecaoError, match="Já existe AV-01"):
        RC.retificar_tipo_do_ato(con, a2, "AV", motivo=MOTIVO, agora=AGORA)


def test_aviso_quando_o_teor_diz_outro_tipo(con):
    mid = matricula(con)
    a1 = ato(con, mid, "R", 1, "R-01/4.100 COMPRA E VENDA")
    saida = RC.retificar_tipo_do_ato(con, a1, "AV", motivo=MOTIVO, agora=AGORA)
    assert saida["teor_confere"] is False and saida["teor_comeca_com"] == "R"


@pytest.mark.parametrize("teor,tipo", [
    ("AV-03/4.100 — RETIFICAÇÃO", "AV"),
    ("  av - 3 texto", "AV"),
    ("<p><strong>R-01</strong>/4.100 COMPRA</p>", "R"),
    ("R.5 texto", "R"),
    ("AVERBAÇÃO sem rótulo", None),
    ("Protocolo nº 11.626", None),
    ("", None),
])
def test_tipo_escrito_no_teor(teor, tipo):
    assert RC.tipo_escrito_no_teor(teor) == tipo


# ------------------------------------------------------------ tela


SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(cg_casa):
        yield cg_casa


def _cliente(casa, usuario, papel):
    casa["db"].create_user(usuario, f"{usuario.upper()} EXEMPLO", SENHA, papel)
    c = casa["app"].test_client()
    c.post("/login", data={"username": usuario, "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def _banco(casa):
    c = sqlite3.connect(casa["banco"])
    c.row_factory = sqlite3.Row
    return c


def _semear(casa):
    """Matricula do intervalo do sistema com R-01, «R-02» (que e AV) e AV-03."""
    c = _banco(casa)
    cur = c.execute(
        """INSERT INTO ri_matriculas
           (numero, complemento, livro, livro_norm, tipo_ficha, situacao, conferido,
            origem, criado_em, teor_formato)
           VALUES ('4100','','2','2','ESTRUTURADA','ATIVA',1,'MANUAL',?,'texto')""",
        (AGORA,))
    mid = int(cur.lastrowid)
    ids = []
    anterior = None
    for tipo, numero, teor in (("R", 1, "R-01/4.100 COMPRA E VENDA"),
                               ("R", 2, "AV-02/4.100 RETIFICAÇÃO"),
                               ("AV", 3, "AV-03/4.100 GEORREFERENCIAMENTO")):
        h = hash_ato("4100", tipo, numero, "2026-11-17", teor, anterior)
        cur = c.execute(
            """INSERT INTO ri_atos
               (matricula_id, tipo, numero, data_ato, teor, teor_formato, cancelado,
                acervo, origem, selo_texto, hash_ato, hash_anterior, lavrado_em)
               VALUES (?,?,?,'2026-11-17',?,'texto',0,0,'MANUAL',?,?,?,?)""",
            (mid, tipo, numero, teor, f"SELOTESTE{numero}", h, anterior, AGORA))
        ids.append(int(cur.lastrowid))
        anterior = h
    c.commit()
    c.close()
    return mid, ids


def _postar(cliente, mid, ato_id, dados):
    html = cliente.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    dados = dict(dados) | {"csrf_token": _token(html)}
    return cliente.post(f"/registro-imoveis/atos/{ato_id}/retificar-tipo", data=dados,
                        follow_redirects=False)


def test_tela_admin_retifica_e_audita(casa):
    mid, (a1, a2, a3) = _semear(casa)
    admin = _cliente(casa, "tabeliao", "ADMIN")
    html = admin.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert f"/registro-imoveis/atos/{a2}/retificar-tipo" in html, "o ADMIN ve o botao"

    r = _postar(admin, mid, a2, {"novo_tipo": "AV", "motivo": MOTIVO})
    assert r.status_code in (302, 303)
    html = admin.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "R-02 passou a ser AV-02" in html
    assert "Hash divergente" not in html

    c = _banco(casa)
    tipo = c.execute("SELECT tipo FROM ri_atos WHERE id=?", (a2,)).fetchone()["tipo"]
    evento = c.execute("""SELECT details FROM audit_logs
                          WHERE action='RI_ATO_TIPO_RETIFICADO'""").fetchone()
    c.close()
    assert tipo == "AV"
    det = json.loads(evento["details"])
    assert det["tipo_antigo"] == "R" and det["tipo_novo"] == "AV"
    assert det["rotulo_antigo"] == "R-02" and det["rotulo_novo"] == "AV-02"
    assert det["motivo"] == MOTIVO and det["usuario"] == "tabeliao"
    assert [x["id"] for x in det["atos"]] == [a2, a3]
    assert all(x["hash_antigo"] and x["hash_novo"] for x in det["atos"])


@pytest.mark.parametrize("papel", ["MANAGER", "USER"])
def test_tela_nega_quem_nao_e_admin(casa, papel):
    mid, (_a1, a2, _a3) = _semear(casa)
    cliente = _cliente(casa, f"pessoa{papel.lower()}", papel)
    html = cliente.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "retificar-tipo" not in html, "o botao so aparece para ADMIN"
    r = _postar(cliente, mid, a2, {"novo_tipo": "AV", "motivo": MOTIVO})
    assert r.status_code == 403
    c = _banco(casa)
    assert c.execute("SELECT tipo FROM ri_atos WHERE id=?", (a2,)).fetchone()["tipo"] == "R"
    c.close()


def test_tela_sem_motivo_nao_muda_nada(casa):
    mid, (_a1, a2, _a3) = _semear(casa)
    admin = _cliente(casa, "tabeliao", "ADMIN")
    _postar(admin, mid, a2, {"novo_tipo": "AV", "motivo": ""})
    html = admin.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "motivo da retificação" in html
    c = _banco(casa)
    assert c.execute("SELECT tipo FROM ri_atos WHERE id=?", (a2,)).fetchone()["tipo"] == "R"
    assert c.execute("""SELECT COUNT(*) n FROM audit_logs
                        WHERE action='RI_ATO_TIPO_RETIFICADO'""").fetchone()["n"] == 0
    c.close()


def test_formulario_de_lavrar_avisa_tipo_trocado(casa):
    mid, _ids = _semear(casa)
    admin = _cliente(casa, "tabeliao", "ADMIN")
    html = admin.get(f"/registro-imoveis/{mid}?lavrar=1").get_data(as_text=True)
    assert "form-lavrar-ato" in html
    assert "O texto começa com" in html, "o aviso do tipo x texto acompanha o formulario"
