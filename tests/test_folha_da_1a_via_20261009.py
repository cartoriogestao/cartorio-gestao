# -*- coding: utf-8 -*-
"""A folha da 1a via e a folha do registro - 09/10/2026 (FOLHA_DA_1A_VIA_20261009).

    Pedido da escrevente Elisa, relatado pelo Robo Certidao Nascimento: no
    1o registro de nascimento/obito a lavratura dava baixa numa folha (que ia
    ao TJMA no `papelMoeda` do selo) e a emissao da 1a via pedia OUTRA folha
    EM BRANCO, imprimia nela e nao dava baixa em nada. 16 casos desde 09/09.

POR QUE NAO SE ADIA O `papelMoeda` (caminho A)
    A documentacao oficial do selador (selador-doc, 2017) tem 181 servicos,
    todos `POST /selo/...` de gerar selo, mais `POST /auth`. Nao ha servico
    para informar ou retificar papel depois, e `papelMoeda` e REQUIRED em
    `DadosSeloNascimento`/`DadosSeloObito`/`DadosSeloNatimorto`. Entao vale a
    folha escolhida (sem pre-selecao) na conferencia, e a 1a via sai nela.

O QUE ESTES TESTES GUARDAM
    - a folha que vai ao TJMA (corpo do pedido ao selador de bancada) e a
      folha baixada em `pp_folhas` e a folha mostrada/amarrada na 1a via;
    - a 1a via nao pede outro selo, nao baixa folha de novo (sem baixa dupla)
      e recusa folha diferente da do registro;
    - nao sobra folha EM BRANCO que foi impressa;
    - a conferencia nao pre-seleciona folha;
    - robo lavra "Pendente de selo", sem baixar folha, e o botao Selar do
      registro responde 403 para ele.
"""
from __future__ import annotations

import glob
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import papel_seguranca as PP                                     # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-10-09T10:00:00"
FOLHAS = ("9100001", "9100002", "9100003")


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def _login(c, user):
    html = c.get("/login").get_data(as_text=True)
    c.post("/login", data={"username": user, "password": SENHA,
                           "csrf_token": _token(html)}, follow_redirects=True)
    return c


@pytest.fixture()
def casa(tmp_path):
    from app import create_app
    from database import Database
    from selador_de_bancada import ligar_o_selador

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    db = Database(banco)
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    # ROBO NAO ADMINISTRA (A6, 22/10/2026): a conta de robo so pode ser USER ou
    # AUDITOR. Lavrar e do USER, e e isso que estes testes medem.
    db.create_user("robo_teste", "Robo de Testes", SENHA, "USER", eh_robo=1)
    con = sqlite3.connect(banco)
    with con:
        PP.receber_remessa(con, fornecedor="ARPENBRASIL", serie="IA",
                           codigo_de=FOLHAS[0], codigo_ate=FOLHAS[-1],
                           agora=AGORA, nota_fiscal="NF TESTE", usuario="MARIO")
    con.close()
    bancada = {"app": app, "banco": banco, "dados": dados, "db": db}
    with ligar_o_selador(bancada) as aparelho:
        bancada["aparelho"] = aparelho
        bancada["humano"] = _login(app.test_client(), "mario")
        yield bancada


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _minimo(especie):
    if especie == "NASCIMENTO":
        return {"pessoa_nome": "CRIANCA TESTE FOLHA", "pessoa_sexo": "M",
                "data_fato": "2026-10-01",
                "local_fato_nome": "Hospital Municipal",
                "ibge_local": "1",    # relato #130: o SIRC exige
                "filiacao1_nome": "MARIA TESTE", "filiacao2_nome": "IGNORADO",
                "declarante_nome": "MARIA TESTE",
                "paternidade_tipo": "NEGATIVO"}   # pai ignorado: termo (23/10/2026)
    return {"pessoa_nome": "FALECIDO TESTE FOLHA", "data_fato": "2026-10-01",
            "local_fato_nome": "Hospital Municipal", "numero_do": "98765",
            "filiacao1_nome": "IGNORADO", "filiacao2_nome": "IGNORADO",
            "declarante_nome": "FULANO",
            "obito_possui_bens": "NAO"}   # relato #130: a CRC exige


SLUG = {"NASCIMENTO": "nascimento", "OBITO": "obito"}
CAMINHO = {"NASCIMENTO": "/selo/civil/nascimento", "OBITO": "/selo/civil/obito"}


def _lavrar(casa, cliente, especie, folha):
    rota = f"/rcpn/novo/{SLUG[especie]}"
    html = cliente.get(rota).get_data(as_text=True)
    dados = {"csrf_token": _token(html), "especie": especie, "acao": "lavrar",
             "folha_seguranca": folha, "nome": _minimo(especie)["pessoa_nome"]}
    dados.update(_minimo(especie))
    r = cliente.post(rota, data=dados, follow_redirects=True)
    con = _con(casa)
    aid = con.execute("SELECT MAX(id) FROM rc_assentos").fetchone()[0]
    ato = con.execute(
        "SELECT * FROM rc_atos WHERE assento_id=? AND tipo='REGISTRO'",
        (aid,)).fetchone()
    con.close()
    return int(aid), dict(ato), r.get_data(as_text=True)


def _papel_no_tjma(casa, especie):
    corpos = [json.loads(p["corpo"]) for p in casa["aparelho"].pedidos
              if p["caminho"].endswith(CAMINHO[especie]) and p["corpo"]]
    assert corpos, f"nenhum pedido ao selador em {CAMINHO[especie]}"
    return [c.get("papelMoeda", {}).get("codigo") for c in corpos]


def _pedidos_de_selo(casa):
    return [p for p in casa["aparelho"].pedidos if "/selo/" in p["caminho"]]


def _emitir(casa, cliente, aid, **extra):
    html = cliente.get(f"/rcpn/{aid}").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "tipo_certidao": "resumo",
             "requerente": "O PROPRIO", "finalidade": "TESTE"}
    dados.update(extra)
    return cliente.post(f"/rcpn/{aid}/certidao", data=dados,
                        follow_redirects=True)


def _folhas(casa):
    con = _con(casa)
    linhas = {r["codigo"]: dict(r) for r in con.execute(
        "SELECT * FROM pp_folhas")}
    con.close()
    return linhas


# --------------------------------------------------------- o caminho feliz


@pytest.mark.parametrize("especie", ["NASCIMENTO", "OBITO"])
def test_a_folha_do_tjma_e_a_baixada_e_a_da_1a_via(casa, especie):
    c = casa["humano"]
    # escolhe a do MEIO, e nao a menor - prova que vale a escolha
    aid, ato, html = _lavrar(casa, c, especie, FOLHAS[1])
    assert (ato["selo"] or "").strip(), html[:800]

    # 1) a folha que foi ao TJMA
    assert _papel_no_tjma(casa, especie) == [FOLHAS[1]]
    # 2) a folha baixada
    f = _folhas(casa)
    assert f[FOLHAS[1]]["situacao"] == "USADA"
    assert f[FOLHAS[1]]["tabela"] == "rc_atos"
    assert int(f[FOLHAS[1]]["ato_id"]) == int(ato["id"])
    assert f[FOLHAS[1]]["selo"] == ato["selo"]
    assert f[FOLHAS[0]]["situacao"] == "EM BRANCO"

    # 3) a folha mostrada na 1a via: travada, sem lista de EM BRANCO
    ficha = c.get(f"/rcpn/{aid}").get_data(as_text=True)
    assert 'id="folha_da_1a_via"' in ficha
    assert re.search(r'id="folha_da_1a_via"', ficha)
    assert re.search(r'<input type="hidden" name="folha_seguranca" value="%s">'
                     % FOLHAS[1], ficha)
    assert 'id="folha_seguranca_select"' not in ficha

    antes = len(_pedidos_de_selo(casa))
    r = _emitir(casa, c, aid, folha_seguranca=FOLHAS[1])
    texto = r.get_data(as_text=True)
    con = _con(casa)
    certs = [dict(x) for x in con.execute(
        "SELECT * FROM rc_certidoes WHERE assento_id=?", (aid,))]
    folha_cert = PP.folha_da_certidao(con, certs[0]["id"]) if certs else None
    movs = [dict(x) for x in con.execute(
        "SELECT * FROM pp_movimentos WHERE codigo=? ORDER BY id", (FOLHAS[1],))]
    con.close()
    assert len(certs) == 1, texto[:1500]
    assert certs[0]["cancelada_em"] is None, certs[0]
    assert certs[0]["selo"] == ato["selo"], "1a via usa o selo do registro"
    assert len(_pedidos_de_selo(casa)) == antes, "1a via nao pede selo novo"
    assert folha_cert == FOLHAS[1], "a certidao ficou com a folha do registro"

    # 4) sem baixa dupla e sem folha impressa que ficou EM BRANCO
    f = _folhas(casa)
    assert sum(1 for x in f.values() if x["situacao"] == "USADA") == 1
    assert f[FOLHAS[1]]["tabela"] == "rc_atos", "a baixa nao foi refeita"
    assert [m["situacao_nova"] for m in movs] == ["USADA", "USADA"]
    assert [m["tabela"] for m in movs] == ["rc_atos", "rc_certidoes"]
    impressas_em_branco = [x for x in f.values()
                           if x["situacao"] == "EM BRANCO"
                           and x["codigo"] == folha_cert]
    assert not impressas_em_branco


def test_a_1a_via_recusa_folha_diferente_da_do_registro(casa):
    c = casa["humano"]
    aid, ato, _ = _lavrar(casa, c, "NASCIMENTO", FOLHAS[0])
    r = _emitir(casa, c, aid, folha_seguranca=FOLHAS[2])
    texto = r.get_data(as_text=True)
    con = _con(casa)
    n = con.execute("SELECT COUNT(*) FROM rc_certidoes WHERE assento_id=?",
                    (aid,)).fetchone()[0]
    con.close()
    assert n == 0, "com folha trocada a 1a via nao sai"
    assert FOLHAS[0] in texto and "TJMA" in texto
    assert _folhas(casa)[FOLHAS[2]]["situacao"] == "EM BRANCO"


def test_emitir_duas_vezes_nao_baixa_a_folha_duas_vezes(casa):
    """A 2a emissao ja e 2a via: exige folha EM BRANCO propria (a do registro
    e recusada como usada) - nunca reaproveita a folha do registro."""
    c = casa["humano"]
    aid, ato, _ = _lavrar(casa, c, "NASCIMENTO", FOLHAS[0])
    _emitir(casa, c, aid, folha_seguranca=FOLHAS[0])
    _emitir(casa, c, aid, folha_seguranca=FOLHAS[0])
    con = _con(casa)
    ativas = con.execute(
        "SELECT COUNT(*) FROM rc_certidoes WHERE assento_id=? "
        "AND cancelada_em IS NULL", (aid,)).fetchone()[0]
    usada = con.execute(
        "SELECT COUNT(*) FROM pp_movimentos WHERE codigo=? "
        "AND situacao_anterior='EM BRANCO'", (FOLHAS[0],)).fetchone()[0]
    con.close()
    assert ativas == 1
    assert usada == 1, "a folha do registro so tem UMA baixa"


def test_1a_via_de_registro_sem_folha_baixa_a_escolhida(casa):
    """Registro com selo e sem folha no estoque (lavrado antes do controle):
    a folha escolhida EM BRANCO e baixada na propria 1a via - antes era o
    `pass` que deixava a folha impressa EM BRANCO no sistema."""
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos(serie, especie, numero, matricula, nome,
                   data_ato, data_fato, dados_json, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',19553,
                       '000000015520261000112700103859 0','SEM FOLHA DA SILVA',
                       '2026-10-01','2026-09-30','{"strSexo": "Masculino"}',
                       'ATIVO','MANUAL',?)""", (AGORA,))
        aid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO rc_atos(assento_id, tipo, folha, numero_ordem, rotulo,
                   data_ato, selo, origem, criado_em)
               VALUES (?,'REGISTRO',154,19553,'154','2026-10-01',
                       'REGNAS000000SEMFOLHA0001','MANUAL',?)""", (aid, AGORA))
        for papel, quem, ordem in (("PAI", "JOSE TESTE", 1),
                                   ("MAE", "MARIA TESTE", 2)):
            con.execute(
                """INSERT INTO rc_pessoas(assento_id, papel, nome, ordem, origem,
                       criado_em) VALUES (?,?,?,?,'MANUAL',?)""",
                (aid, papel, quem, ordem, AGORA))
    con.close()
    c = casa["humano"]
    ficha = c.get(f"/rcpn/{aid}").get_data(as_text=True)
    assert 'id="folha_seguranca_select"' in ficha, "sem folha no registro, escolhe"
    antes = len(_pedidos_de_selo(casa))
    r = _emitir(casa, c, aid, folha_seguranca=FOLHAS[2])
    con = _con(casa)
    cert = con.execute("SELECT * FROM rc_certidoes WHERE assento_id=?",
                       (aid,)).fetchone()
    assert cert is not None, r.get_data(as_text=True)[:1500]
    folha_cert = PP.folha_da_certidao(con, cert["id"])
    con.close()
    f = _folhas(casa)[FOLHAS[2]]
    assert f["situacao"] == "USADA" and f["tabela"] == "rc_certidoes"
    assert folha_cert == FOLHAS[2]
    assert cert["selo"] == "REGNAS000000SEMFOLHA0001"
    assert len(_pedidos_de_selo(casa)) == antes


# --------------------------------------------------------- a conferencia


def test_a_conferencia_nao_pre_seleciona_a_folha(casa):
    c = casa["humano"]
    rota = "/rcpn/novo/nascimento"
    html = c.get(rota).get_data(as_text=True)
    dados = {"csrf_token": _token(html), "especie": "NASCIMENTO",
             "acao": "conferir"}
    dados.update(_minimo("NASCIMENTO"))
    conf = c.post(rota, data=dados).get_data(as_text=True)
    assert 'name="folha_seguranca"' in conf
    for codigo in FOLHAS:
        assert not re.search(r'<option value="%s"[^>]*selected' % codigo, conf), (
            f"a folha {codigo} veio pre-selecionada na conferencia")
    assert "TJMA" in conf


# --------------------------------------------------------- o robo


def test_robo_lavra_pendente_sem_folha_e_selar_e_403(casa):
    app = casa["app"]
    robo = _login(app.test_client(), "robo_teste")
    antes = len(_pedidos_de_selo(casa))
    aid, ato, html = _lavrar(casa, robo, "NASCIMENTO", FOLHAS[0])
    assert not (ato["selo"] or "").strip(), "robo nunca sela"
    assert len(_pedidos_de_selo(casa)) == antes, "robo nao chama o selador"
    assert _folhas(casa)[FOLHAS[0]]["situacao"] == "EM BRANCO", (
        "sem selo a folha nao se gasta")

    ficha = robo.get(f"/rcpn/{aid}").get_data(as_text=True)
    r = robo.post(f"/rcpn/ato/{ato['id']}/selar",
                  data={"csrf_token": _token(ficha),
                        "folha_seguranca": FOLHAS[0]})
    assert r.status_code == 403
    assert len(_pedidos_de_selo(casa)) == antes
    assert _folhas(casa)[FOLHAS[0]]["situacao"] == "EM BRANCO"

    # o escrevente humano sela, escolhendo a folha que tem na mao
    c = casa["humano"]
    ficha = c.get(f"/rcpn/{aid}").get_data(as_text=True)
    assert "Selar registro" in ficha
    r = c.post(f"/rcpn/ato/{ato['id']}/selar",
               data={"csrf_token": _token(ficha), "folha_seguranca": FOLHAS[2]},
               follow_redirects=True)
    con = _con(casa)
    selo = con.execute("SELECT selo FROM rc_atos WHERE id=?",
                       (ato["id"],)).fetchone()["selo"]
    con.close()
    assert (selo or "").strip(), r.get_data(as_text=True)[:1500]
    assert _papel_no_tjma(casa, "NASCIMENTO") == [FOLHAS[2]]
    f = _folhas(casa)
    assert f[FOLHAS[2]]["situacao"] == "USADA"
    assert f[FOLHAS[0]]["situacao"] == "EM BRANCO"
    ficha = c.get(f"/rcpn/{aid}").get_data(as_text=True)
    assert re.search(r'<input type="hidden" name="folha_seguranca" value="%s">'
                     % FOLHAS[2], ficha)


def test_selar_sem_folha_e_recusado(casa):
    app = casa["app"]
    robo = _login(app.test_client(), "robo_teste")
    aid, ato, _ = _lavrar(casa, robo, "OBITO", FOLHAS[0])
    c = casa["humano"]
    ficha = c.get(f"/rcpn/{aid}").get_data(as_text=True)
    antes = len(_pedidos_de_selo(casa))
    c.post(f"/rcpn/ato/{ato['id']}/selar",
           data={"csrf_token": _token(ficha)}, follow_redirects=True)
    assert len(_pedidos_de_selo(casa)) == antes
    con = _con(casa)
    selo = con.execute("SELECT selo FROM rc_atos WHERE id=?",
                       (ato["id"],)).fetchone()["selo"]
    con.close()
    assert not (selo or "").strip()
