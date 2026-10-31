"""Da lista de selos se entra no ato — of-0118.

A ARMADILHA QUE ESTE TESTE GUARDA
    Em tabela filha, `sd_selos.ato_id` é do ATO, e não da ficha. Montar o link
    com ele abre a ficha de OUTRO registro, e ninguém desconfia de uma ficha que
    abre. Por isso todo id de ato aqui é diferente do id da ficha, e a tabela
    de endereços abaixo está escrita à mão, e não lida de `DESTINO_DO_ATO`.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest
from flask import url_for

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modulos as MOD                                            # noqa: E402
import modulos_ligados as MODLIG                                 # noqa: E402
import selos_emitidos as SEM                                     # noqa: E402

SENHA = "Senha#12345"
ID_DO_ATO = 910001

# tabela: (endereço de {ficha}, tabela do pai ou None se a ficha é a própria
# linha, coluna do pai)
ESPERADO = {
    "nt_atos": ("/notas/atos/{}", None, None),
    "ri_matriculas": ("/registro-imoveis/{}", None, None),
    "ri_protocolos": ("/registro-imoveis/protocolo/{}", None, None),
    "rc_assentos": ("/rcpn/{}", None, None),
    "hc_habilitacoes": ("/rcpn/habilitacoes/{}", None, None),
    "rc_certidoes": ("/rcpn/certidoes/{}", None, None),
    "pt_certidoes": ("/protesto/certidoes/{}", None, None),
    "nt_certidoes": ("/notas/certidoes/{}", None, None),
    "at_certidoes": ("/atribuicoes/certidoes/{}", None, None),
    "nt_reconhecimentos": ("/notas/reconhecimento/{}", None, None),
    "nt_sinais_reconhecimentos": ("/notas/sinais/reconhecimento/{}", None, None),
    "nt_cartoes": ("/notas/cartoes/{}", None, None),
    "ri_atos": ("/registro-imoveis/{}", "ri_matriculas", "matricula_id"),
    "ri_certidoes": ("/registro-imoveis/{}", "ri_matriculas", "matricula_id"),
    "rc_atos": ("/rcpn/{}", "rc_assentos", "assento_id"),
    "pt_atos": ("/protesto/{}", "pt_titulos", "titulo_id"),
    "rg_atos": ("/rcpj-rtd/{}", "rg_registros", "registro_id"),
    "ra_atos": ("/livro3/{}", "ra_registros", "registro_id"),
}


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _entrar(app, bd, usuario: str, papel: str):
    bd.create_user(usuario, "MARIO EXEMPLO DOS SANTOS", SENHA, papel)
    c = app.test_client()
    c.post("/login",
           data={"username": usuario, "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


@pytest.fixture()
def s(cg_casa):
    app, bd = cg_casa["app"], cg_casa["db"]
    return {"app": app, "db": bd, "banco": cg_casa["banco"],
            "c": _entrar(app, bd, "tabeliao", "ADMIN")}


def _colunas_obrigatorias(con, tabela: str) -> list[tuple[str, str]]:
    return [(r[0], r[1]) for r in con.execute(
        """SELECT column_name, data_type FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = ?
              AND is_nullable = 'NO' AND column_default IS NULL
              AND is_identity = 'NO'""", (tabela,)).fetchall()]


def _linha(con, tabela: str, id_: int, **valores) -> int:
    """Uma linha mínima de `tabela`, com o id pedido. O teste só precisa dos
    ids e dos pais: o resto é o que o banco exige."""
    campos = {"id": id_, **valores}
    for coluna, tipo in _colunas_obrigatorias(con, tabela):
        if coluna not in campos:
            campos[coluna] = (id_ if tipo in ("integer", "bigint", "smallint")
                              else 0 if tipo in ("numeric", "real",
                                                 "double precision")
                              else "2026-10-31")
    marcas = ",".join("?" for _ in campos)
    con.execute(f"INSERT INTO {tabela} ({','.join(campos)}) VALUES ({marcas})",
                list(campos.values()))
    return id_


def _selo(con, numero: str, tabela, ato_id, usado_em=None) -> None:
    con.execute(
        """INSERT INTO sd_selos (numero, atribuicao, caminho, tabela, ato_id,
                                 obtido_em, obtido_por, usado_em)
           VALUES (?,'NOTAS','/selo/notas/x',?,?,'2026-10-31 10:00:00','BEATRIZ',?)""",
        (numero, tabela, ato_id, usado_em))


@pytest.fixture()
def con(s):
    c = sqlite3.connect(s["banco"])
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _tela(c) -> str:
    return " ".join(c.get("/selos").get_data(as_text=True).split())


def _ato_e_ficha(con, tabela: str) -> tuple[int, int]:
    """Grava o ato e, se for filha, o pai. Devolve (id do ato, id da ficha)."""
    _, pai, coluna = ESPERADO[tabela]
    if pai is None:
        # Estas têm chave estrangeira, mas a ficha é a própria linha.
        apoio = {"nt_sinais_reconhecimentos": ("nt_sinais_publicos", "sinal_id"),
                 "rc_certidoes": ("rc_assentos", "assento_id")}.get(tabela)
        extra = ({apoio[1]: _linha(con, apoio[0], 910888)} if apoio else {})
        return _linha(con, tabela, ID_DO_ATO, **extra), ID_DO_ATO
    ficha = _linha(con, pai, 910777)
    _linha(con, tabela, ID_DO_ATO, **{coluna: ficha})
    return ID_DO_ATO, ficha


# ------------------------------------------------------------ cada tabela


def test_a_lista_daqui_e_a_do_codigo():
    assert set(ESPERADO) == set(SEM.DESTINO_DO_ATO)


@pytest.mark.parametrize("tabela", sorted(ESPERADO))
def test_cada_tabela_leva_a_tela_certa(s, con, tabela):
    ato_id, ficha = _ato_e_ficha(con, tabela)
    _selo(con, "SELOTESTE0001", tabela, ato_id)
    con.commit()

    html = _tela(s["c"])

    endereco = ESPERADO[tabela][0].format(ficha)
    assert (f'<a href="{endereco}">{tabela} nº {ato_id}</a>') in html


@pytest.mark.parametrize("tabela", [t for t, e in ESPERADO.items() if e[1]])
def test_a_filha_nunca_usa_o_id_do_ato_no_link(s, con, tabela):
    ato_id, ficha = _ato_e_ficha(con, tabela)
    assert ato_id != ficha
    _selo(con, "SELOTESTE0002", tabela, ato_id)
    con.commit()

    assert f'href="{ESPERADO[tabela][0].format(ato_id)}"' not in _tela(s["c"])


def test_toda_tela_da_lista_existe(s):
    with s["app"].test_request_context("/"):
        for tabela, (tela, parametro, _) in SEM.DESTINO_DO_ATO.items():
            assert url_for(tela, **{parametro: 1}), tabela


# ----------------------------------------------------- o que fica sem link


def test_pai_vazio_fica_sem_link_e_com_o_texto(s, con):
    _linha(con, "ri_certidoes", ID_DO_ATO)      # matricula_id é opcional aqui
    _selo(con, "SELOTESTE0003", "ri_certidoes", ID_DO_ATO)
    con.commit()

    html = _tela(s["c"])

    assert f"ri_certidoes nº {ID_DO_ATO}" in html
    assert f">ri_certidoes nº {ID_DO_ATO}</a>" not in html


def test_tabela_fora_da_lista_fica_sem_link_e_com_o_texto(s, con):
    _selo(con, "SELOTESTE0004", "ap_apostilas", ID_DO_ATO)
    con.commit()

    html = _tela(s["c"])

    assert f"ap_apostilas nº {ID_DO_ATO}" in html
    assert f">ap_apostilas nº {ID_DO_ATO}</a>" not in html


def test_ato_que_nao_existe_mais_fica_sem_link(s, con):
    _selo(con, "SELOTESTE0005", "nt_atos", ID_DO_ATO)
    con.commit()

    html = _tela(s["c"])

    assert f"nt_atos nº {ID_DO_ATO}" in html
    assert f">nt_atos nº {ID_DO_ATO}</a>" not in html


def test_selo_so_com_usado_em_fica_sem_link(s, con):
    _selo(con, "SELOTESTE0006", None, None, usado_em="2026-01-01")
    con.commit()

    html = _tela(s["c"])

    assert "SELOTESTE0006" in html
    linha = html.split("SELOTESTE0006")[1].split("</tr>")[0]
    assert "<a href" not in linha


# ----------------------------------------------------------- quem recebe


def test_auditor_recebe_o_link_quando_a_rota_o_admite(s, con):
    _ato_e_ficha(con, "nt_atos")
    _selo(con, "SELOTESTE0007", "nt_atos", ID_DO_ATO)
    con.commit()
    auditor = _entrar(s["app"], s["db"], "auditora", "AUDITOR")

    assert f'<a href="/notas/atos/{ID_DO_ATO}">' in _tela(auditor)


def test_auditor_nao_recebe_link_de_rota_em_que_o_papel_nao_entra(
        s, con, monkeypatch):
    """Nenhuma tela da lista barra o AUDITOR hoje, e por isso a rota é fechada
    aqui. `pode_entrar` sozinha daria o link: ela não olha os papéis da rota."""
    _ato_e_ficha(con, "nt_atos")
    _selo(con, "SELOTESTE0008", "nt_atos", ID_DO_ATO)
    con.commit()
    auditor = _entrar(s["app"], s["db"], "auditora", "AUDITOR")
    monkeypatch.setattr(s["app"].view_functions["notas_ato"],
                        "papeis_exigidos", ("ADMIN", "MANAGER"))
    assert MODLIG.pode_entrar(s["db"].get_setting,
                              MOD.modulo_da_tela("notas_ato"), "AUDITOR", None)

    html = _tela(auditor)

    assert f"nt_atos nº {ID_DO_ATO}" in html
    assert f">nt_atos nº {ID_DO_ATO}</a>" not in html
    assert f'<a href="/notas/atos/{ID_DO_ATO}">' in _tela(s["c"])


def test_quem_o_modulo_barra_nao_recebe_o_link(s, con, monkeypatch):
    _ato_e_ficha(con, "nt_atos")
    _selo(con, "SELOTESTE0009", "nt_atos", ID_DO_ATO)
    con.commit()
    original = MODLIG.pode_entrar
    barrado = MOD.modulo_da_tela("notas_ato")
    assert barrado != MOD.modulo_da_tela("selos_emitidos_lista")
    monkeypatch.setattr(
        MODLIG, "pode_entrar",
        lambda get, modulo, papel=None, funcao=None: (
            modulo != barrado and original(get, modulo, papel, funcao)))

    html = _tela(s["c"])

    assert f"nt_atos nº {ID_DO_ATO}" in html
    assert f">nt_atos nº {ID_DO_ATO}</a>" not in html


# --------------------------------------------------------------- os layouts


@pytest.mark.parametrize("layout", ["novo", "antigo"])
def test_a_tela_abre_com_o_link_nos_dois_layouts(s, con, layout):
    _ato_e_ficha(con, "nt_atos")
    _selo(con, "SELOTESTE0010", "nt_atos", ID_DO_ATO)
    con.commit()
    pagina = s["c"].get("/selos").get_data(as_text=True)
    s["c"].post("/preferencias/layout",
                data={"layout": layout, "next": "/selos",
                      "csrf_token": _token(pagina)})

    resposta = s["c"].get("/selos")

    assert resposta.status_code == 200
    assert (f'<a href="/notas/atos/{ID_DO_ATO}">nt_atos nº {ID_DO_ATO}</a>'
            in resposta.get_data(as_text=True))
