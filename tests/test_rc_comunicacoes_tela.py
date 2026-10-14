"""As telas das comunicações mensais de óbito.

POR QUE ESTE ARQUIVO EXISTE SEPARADO
    `test_rc_comunicacoes.py` prova que o **módulo** filtra, monta e congela.
    Este prova que a **tela chama o módulo** — e são coisas diferentes.

    **É o defeito que mais se repetiu neste projeto**, oito vezes: função de
    domínio pronta e testada que nenhuma tela chamava.
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

import rc_comunicacoes as CM                                     # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-01T09:00"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.set_settings({"serventia_titular": "MARIO EXEMPLO DOS SANTOS"})
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _liso(t: str) -> str:
    return " ".join((t or "").split())


def _obito(casa, nome, sexo, nasc, *, numero=1, data_ato="2026-07-15"):
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em)
               VALUES ('RC_C','OBITO',?,?,?,?,'ATIVO','SISTEMA',?)""",
            (numero, nome, data_ato, data_ato, AGORA))
        con.execute(
            """INSERT INTO rc_pessoas (assento_id, papel, nome, nome_norm,
                   sexo, data_nascimento, criado_em) VALUES (?,?,?,?,?,?,?)""",
            (int(cur.lastrowid), "FALECIDO", nome, nome.lower(), sexo, nasc,
             AGORA))


def _abrir(casa, url):
    r = casa["cliente"].get(url)
    assert r.status_code == 200, f"{url} não abriu ({r.status_code})"
    return _liso(r.get_data(as_text=True))


def _abrir_mes(casa, competencia="2026-07"):
    html = casa["cliente"].get("/rcpn/comunicacoes").get_data(as_text=True)
    return casa["cliente"].post(
        "/rcpn/comunicacoes/abrir",
        data={"csrf_token": _token(html), "competencia": competencia},
        follow_redirects=True)


# ------------------------------------------------ a tela explica a obrigação


def test_a_tela_lista_os_cinco_destinos_com_o_artigo(casa):
    html = _abrir(casa, "/rcpn/comunicacoes")
    for d in CM.DESTINOS:
        assert d["nome"] in html, f"{d['chave']} não aparece"
        assert d["artigo"] in html
    assert "5º dia útil" in html


def test_a_tela_diz_que_a_omissao_responsabiliza(casa):
    """É o § 2º, e quem lê a tela precisa saber o que está em jogo."""
    html = _abrir(casa, "/rcpn/comunicacoes")
    assert "responsabilização" in html


def test_a_tela_manda_abrir_o_mes_vazio_tambem(casa):
    html = _abrir(casa, "/rcpn/comunicacoes")
    assert "mês sem óbito nenhum" in html
    assert "inexistência de movimento" in html


# ------------------------------------------------ abrir e ver


def test_a_tela_abre_as_cinco_com_o_prazo_calculado(casa):
    """O PRAZO VEM DE QUEM CONTA DIA ÚTIL, e não de dentro do módulo — que é
    por isso que ele se calcula na rota."""
    _abrir_mes(casa, "2026-07")
    con = _con(casa)
    linhas = [dict(r) for r in con.execute(
        "SELECT * FROM rc_comunicacoes WHERE competencia='2026-07'")]
    assert len(linhas) == 5
    prazos = {x["prazo_ate"] for x in linhas}
    assert prazos != {None}, "o prazo não foi calculado"
    # o 5º dia útil de agosto/2026 cai em agosto
    assert all((p or "").startswith("2026-08") for p in prazos), prazos


def test_abrir_duas_vezes_avisa_em_vez_de_duplicar(casa):
    _abrir_mes(casa, "2026-07")
    r = _abrir_mes(casa, "2026-07")
    assert "já estavam abertas" in _liso(r.get_data(as_text=True))
    con = _con(casa)
    assert int(con.execute(
        "SELECT COUNT(*) FROM rc_comunicacoes").fetchone()[0]) == 5


def test_a_tela_do_texto_mostra_quem_fica_de_fora(casa):
    """Lista que só mostra quem entra deixa quem confere sem saber se faltou
    alguém."""
    _obito(casa, "CRIANCA X", "F", "2018-03-01", numero=1)
    _obito(casa, "JULIO CEZAR", "M", "2004-02-10", numero=2)
    _abrir_mes(casa, "2026-07")
    con = _con(casa)
    cid = int(con.execute(
        "SELECT id FROM rc_comunicacoes WHERE destino='ELEITORAL'"
    ).fetchone()[0])
    html = _abrir(casa, f"/rcpn/comunicacoes/{cid}")
    assert "JULIO CEZAR" in html
    assert "Ficam de fora" in html
    assert "CRIANCA X" in html


def test_ver_o_texto_nao_grava(casa):
    _obito(casa, "A", "M", "1990-01-01")
    _abrir_mes(casa, "2026-07")
    con = _con(casa)
    cid = int(con.execute("SELECT id FROM rc_comunicacoes LIMIT 1"
                          ).fetchone()[0])
    _abrir(casa, f"/rcpn/comunicacoes/{cid}")
    teor = con.execute("SELECT teor FROM rc_comunicacoes WHERE id=?",
                       (cid,)).fetchone()["teor"]
    assert not (teor or "").strip()


# ------------------------------------------------ registrar o envio


def _registrar(casa, cid, **extra):
    html = casa["cliente"].get(
        f"/rcpn/comunicacoes/{cid}").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "acao": "ENVIADA",
             "canal": "OFICIO", "protocolo": "OF-2026-0099",
             "quando": "2026-08-05"}
    dados.update(extra)
    return casa["cliente"].post(f"/rcpn/comunicacoes/{cid}/resolver",
                                data=dados, follow_redirects=True)


def test_a_tela_registra_o_envio_e_congela_o_teor(casa):
    _obito(casa, "MARIA DAS DORES", "F", "1956-01-05")
    _abrir_mes(casa, "2026-07")
    con = _con(casa)
    cid = int(con.execute(
        "SELECT id FROM rc_comunicacoes WHERE destino='RECEITA'"
    ).fetchone()[0])
    _registrar(casa, cid)
    linha = con.execute("SELECT * FROM rc_comunicacoes WHERE id=?",
                        (cid,)).fetchone()
    assert linha["situacao"] == CM.ENVIADA
    assert "MARIA DAS DORES" in linha["teor"]
    assert linha["protocolo"] == "OF-2026-0099"
    assert len(linha["hash_teor"]) == 64


def test_a_rota_recusa_envio_sem_protocolo(casa):
    """MANDADO DIRETO PARA A ROTA: quem recusa é o domínio."""
    _abrir_mes(casa, "2026-07")
    con = _con(casa)
    cid = int(con.execute("SELECT id FROM rc_comunicacoes LIMIT 1"
                          ).fetchone()[0])
    r = _registrar(casa, cid, protocolo="")
    assert "art. 226, § 2º" in _liso(r.get_data(as_text=True))


def test_enviada_a_tela_mostra_o_teor_congelado(casa):
    _obito(casa, "A", "M", "1990-01-01")
    _abrir_mes(casa, "2026-07")
    con = _con(casa)
    cid = int(con.execute("SELECT id FROM rc_comunicacoes LIMIT 1"
                          ).fetchone()[0])
    _registrar(casa, cid)
    html = _abrir(casa, f"/rcpn/comunicacoes/{cid}")
    assert "congelado" in html
    assert "OF-2026-0099" in html
    assert "Registrar o envio" not in html


# ------------------------------------------------ o atraso na tela


def test_a_tela_mostra_os_meses_com_obito_e_sem_comunicacao(casa):
    """É a lista que diz o tamanho do que está em aberto."""
    _obito(casa, "A", "M", "1990-01-01", numero=1, data_ato="2026-04-10")
    _obito(casa, "B", "F", "1990-01-01", numero=2, data_ato="2026-07-10")
    html = _abrir(casa, "/rcpn/comunicacoes")
    assert "2026-04" in html
    assert "2026-07" in html
    assert "sem as cinco comunicações" in html
    _abrir_mes(casa, "2026-04")
    depois = _abrir(casa, "/rcpn/comunicacoes")
    assert "2026-07" in depois


def test_a_lista_esta_no_menu(casa):
    html = _abrir(casa, "/rcpn/comunicacoes")
    assert "Comunicações mensais" in html
