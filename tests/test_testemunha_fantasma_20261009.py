# -*- coding: utf-8 -*-
"""A testemunha fantasma - 09/10/2026 (TESTEMUNHA_FANTASMA_20261009).

    Nos assentos 8371 (rascunho 22) e 8373 (rascunho 23) a lavratura do
    nascimento criou em `rc_pessoas` uma TESTEMUNHA com o nome do proprio
    registrado, sem nenhum campo testemunha_* preenchido. A linha foi apagada
    a mao. Em producao ha mais 11 assentos com a mesma linha (9 nascimentos e
    2 obitos, desde 09/09/2026).

A CAUSA, EM DOIS PASSOS
    1. `_pessoa_do_assento.html`: o <select name="testemunha_documento_tipo">
       nao tem opcao vazia. O NAVEGADOR manda «CPF» em toda gaveta - inclusive
       a da testemunha que ninguem abriu.
    2. `_pessoas_do_formulario` contava esse «CPF» como gaveta preenchida, e
       `rc_assento.registrar_pessoa` completava o nome que faltava com o nome
       DO ASSENTO (o do registrado) - reserva pensada so para o titular.

    O rascunho nao e a causa: ele so preenche a tela. Por isso estes testes
    enviam o formulario COMO O NAVEGADOR ENVIA (todo campo da tela, com o
    valor que o <select> mostra), passando pela conferencia, a partir de um
    rascunho - e e esse o caminho que reproduzia o defeito.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import papel_seguranca as PP                                     # noqa: E402
import rascunho_de_tela as RASC                                  # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-10-09T10:00:00"
FOLHAS = ("9200001", "9200002", "9200003", "9200004")
SLUG = {"NASCIMENTO": "nascimento", "OBITO": "obito", "CASAMENTO": "casamento"}


# ------------------------------------------- o navegador, em miniatura
class _Formularios(HTMLParser):
    """Le os <form> da pagina e monta o que o navegador enviaria."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms: list[dict] = []
        self._f = None
        self._sel = None
        self._ta = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self._f = {"attrs": a, "campos": [], "botoes": []}
            self.forms.append(self._f)
            return
        if self._f is None:
            return
        if tag == "input":
            tipo = (a.get("type") or "text").lower()
            nome = a.get("name")
            if not nome or "disabled" in a:
                return
            if tipo in ("checkbox", "radio"):
                if "checked" in a:
                    self._f["campos"].append([nome, a.get("value", "on")])
            elif tipo in ("submit", "button", "image", "reset", "file"):
                if tipo == "submit":
                    self._f["botoes"].append((nome, a.get("value", "")))
            else:
                self._f["campos"].append([nome, a.get("value", "")])
        elif tag == "button":
            if a.get("name") and (a.get("type") or "submit") == "submit":
                self._f["botoes"].append((a["name"], a.get("value", "")))
        elif tag == "select" and a.get("name") and "disabled" not in a:
            self._sel = {"nome": a["name"], "primeira": None, "marcada": None}
        elif tag == "option" and self._sel is not None:
            v = a.get("value")
            self._sel["_atual"] = v
            if self._sel["primeira"] is None:
                self._sel["primeira"] = v
            if "selected" in a:
                self._sel["marcada"] = v
        elif tag == "textarea" and a.get("name"):
            self._ta = [a["name"], ""]

    def handle_data(self, data):
        if self._ta is not None:
            self._ta[1] += data
        if self._sel is not None and self._sel.get("_atual") is None \
                and self._sel.get("primeira") is None:
            pass

    def handle_endtag(self, tag):
        if tag == "select" and self._sel is not None:
            v = self._sel["marcada"] if self._sel["marcada"] is not None \
                else self._sel["primeira"]
            if v is not None:
                self._f["campos"].append([self._sel["nome"], v])
            self._sel = None
        elif tag == "textarea" and self._ta is not None:
            self._f["campos"].append([self._ta[0], self._ta[1].lstrip("\n")])
            self._ta = None
        elif tag == "form":
            self._f = None


def _como_o_navegador(html: str, botao: tuple[str, str], **trocar) -> dict:
    """O que o navegador manda ao clicar `botao` no form que o tem."""
    p = _Formularios()
    p.feed(html)
    for f in p.forms:
        if botao in f["botoes"]:
            dados: dict = {}
            for nome, valor in f["campos"]:
                dados.setdefault(nome, valor)   # 1o valor, como o Flask le
            dados.update(trocar)
            dados[botao[0]] = botao[1]
            return dados
    raise AssertionError(f"nenhum formulario com o botao {botao}")


# ------------------------------------------------------------- a casa
def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


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
    db.create_user("elisa", "ELISA TESTE", SENHA, "ADMIN")
    con = sqlite3.connect(banco)
    with con:
        PP.receber_remessa(con, fornecedor="ARPENBRASIL", serie="IA",
                           codigo_de=FOLHAS[0], codigo_ate=FOLHAS[-1],
                           agora=AGORA, nota_fiscal="NF TESTE", usuario="T")
        RASC.init_rascunho_schema(con)
    con.close()
    bancada = {"app": app, "banco": banco, "dados": dados, "db": db}
    with ligar_o_selador(bancada):
        c = app.test_client()
        html = c.get("/login").get_data(as_text=True)
        c.post("/login", data={"username": "elisa", "password": SENHA,
                               "csrf_token": _token(html)},
               follow_redirects=True)
        bancada["c"] = c
        yield bancada


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


# O rascunho 22 de producao, com nomes trocados: 66 chaves, NENHUMA de
# testemunha a nao ser o tipo de documento que a tela gravou.
def _rascunho_nascimento() -> dict:
    d = {"especie": "NASCIMENTO", "data_fato": "2026-10-06",
         "cor_raca": "PARDA", "hora_fato": "01:03",
         "local_fato_nome": "Maternidade de Teste",
         "local_fato_endereco": "Rua Teste, Centro, Imperatriz/MA",
         "naturalidade_declarada": "Imperatriz/MA", "ibge_local": "1",
         "ibge_gemeo": "1", "dnv": "30-00000000-1",
         "pessoa_nome": "JOSE FANTASMA DE TESTE", "pessoa_sexo": "M",
         "pessoa_data_nascimento": "2026-10-06",
         "pessoa_nacionalidade": "brasileiro",
         "pessoa_naturalidade_cidade": "Imperatriz",
         "pessoa_naturalidade_uf": "MA",
         "prog1f1_nome": "AVO MATERNA TESTE", "prog2f1_nome": "AVO MATERNO TESTE",
         "prog1f2_nome": "AVO PATERNA TESTE", "prog2f2_nome": "AVO PATERNO TESTE",
         "testemunha_documento_tipo": "CPF"}
    for pref, nome, sexo, nasc in (("filiacao1", "MAE DE TESTE", "F", "2001-08-11"),
                                   ("filiacao2", "PAI DE TESTE", "M", "1996-02-08"),
                                   ("declarante", "PAI DE TESTE", "M", "1996-02-08")):
        d.update({f"{pref}_nome": nome, f"{pref}_sexo": sexo,
                  f"{pref}_data_nascimento": nasc,
                  f"{pref}_estado_civil": "solteiro(a)",
                  f"{pref}_profissao": "lavrador(a)",
                  f"{pref}_documento_tipo": "CPF",
                  f"{pref}_documento_numero": "",
                  f"{pref}_nacionalidade": "brasileira",
                  f"{pref}_naturalidade_cidade": "Cidade Exemplo",
                  f"{pref}_naturalidade_uf": "MA"})
    return d


def _rascunho_obito() -> dict:
    return {"especie": "OBITO", "data_fato": "2026-10-05",
            "hora_fato": "10:00", "local_fato_nome": "Hospital de Teste",
            "local_fato_endereco": "Rua Teste, Cidade Exemplo/MA",
            "numero_do": "98765432", "causa_morte": "causa de teste",
            "atestante": "MEDICO DE TESTE", "local_sepultamento": "Cemiterio",
            "pessoa_nome": "MARIA FANTASMA DE TESTE", "pessoa_sexo": "F",
            "pessoa_data_nascimento": "1950-01-01",
            "filiacao1_nome": "IGNORADO", "filiacao2_nome": "IGNORADO",
            "declarante_nome": "FILHO DECLARANTE TESTE",
            "declarante_documento_tipo": "CPF"}


def _salvar_rascunho(casa, dados) -> int:
    con = _con(casa)
    with con:
        r = RASC.salvar(con, tela="rcpn_assento_novo",
                        titulo=f"{dados['especie']} - teste fantasma",
                        dados=dados, agora=AGORA, por="ELISA TESTE")
    con.close()
    return int(r["id"])


def _lavrar_do_rascunho(casa, dados, folha):
    """Abre o rascunho, confere e lavra - clicando como o balcao clica."""
    c = casa["c"]
    rid = _salvar_rascunho(casa, dados)
    slug = SLUG[dados["especie"]]
    html = c.get(f"/rcpn/novo/{slug}?rascunho_id={rid}",
                 follow_redirects=True).get_data(as_text=True)
    assert dados["pessoa_nome"] in html, "o rascunho nao preencheu a tela"
    envio = _como_o_navegador(html, ("acao", "conferir"))
    # o defeito nasce aqui: o <select> sem opcao vazia manda CPF
    assert envio.get("testemunha_documento_tipo") == "CPF"
    if not dados.get("testemunha_nome"):
        assert not envio.get("testemunha_nome")
    conf = c.post(f"/rcpn/novo/{slug}", data=envio,
                  follow_redirects=True).get_data(as_text=True)
    envio2 = _como_o_navegador(conf, ("acao", "lavrar"),
                               folha_seguranca=folha)
    r = c.post(f"/rcpn/novo/{slug}", data=envio2, follow_redirects=True)
    con = _con(casa)
    aid = con.execute("SELECT MAX(id) FROM rc_assentos").fetchone()[0]
    assert aid, "nao lavrou: " + re.sub(r"\s+", " ", r.get_data(as_text=True))[:600]
    pessoas = [dict(p) for p in con.execute(
        "SELECT * FROM rc_pessoas WHERE assento_id=? ORDER BY id", (aid,))]
    con.close()
    return int(aid), pessoas


@pytest.mark.parametrize("especie", ["NASCIMENTO", "OBITO"])
def test_lavrar_do_rascunho_nao_cria_testemunha_com_o_nome_do_registrado(
        casa, especie):
    dados = _rascunho_nascimento() if especie == "NASCIMENTO" else _rascunho_obito()
    aid, pessoas = _lavrar_do_rascunho(casa, dados, FOLHAS[1])
    titular = dados["pessoa_nome"]
    papeis = [p["papel"] for p in pessoas]
    assert "TESTEMUNHA" not in papeis, (
        f"testemunha fantasma no assento {aid}: "
        f"{[(p['papel'], p['nome']) for p in pessoas]}")
    # ninguem alem do titular leva o nome do registrado/falecido
    com_o_nome = [p["papel"] for p in pessoas if p["nome"] == titular]
    assert com_o_nome == [("REGISTRADO" if especie == "NASCIMENTO" else "FALECIDO")]
    # e o resto continua entrando
    assert "DECLARANTE" in papeis


def test_testemunha_digitada_continua_entrando(casa):
    dados = _rascunho_nascimento()
    dados.update({"testemunha_nome": "TESTEMUNHA DE VERDADE",
                  "testemunha_documento_numero": "000.000.044-21"})
    aid, pessoas = _lavrar_do_rascunho(casa, dados, FOLHAS[2])
    t = [p for p in pessoas if p["papel"] == "TESTEMUNHA"]
    assert [p["nome"] for p in t] == ["TESTEMUNHA DE VERDADE"]
    assert t[0]["documento_tipo"] == "CPF"


def test_registrar_pessoa_nao_empresta_o_nome_do_assento_a_outro_papel(casa):
    """A segunda trava, no modulo: so o titular herda o nome do assento."""
    import rc_assento as RC
    con = _con(casa)
    with con:
        aid = con.execute(
            "INSERT INTO rc_assentos(serie, especie, nome, data_ato, situacao,"
            " origem, criado_em) VALUES ('RC_A','NASCIMENTO','FULANO TITULAR',"
            "?, 'ATIVO','MANUAL',?)", (AGORA, AGORA)).lastrowid
        # o titular sem nome continua herdando (comportamento de antes)
        RC.registrar_pessoa(con, aid, papel="REGISTRADO", agora=AGORA, sexo="M")
        for papel in ("TESTEMUNHA", "DECLARANTE", "PAI"):
            with pytest.raises(RC.RcError, match="sem nome"):
                RC.registrar_pessoa(con, aid, papel=papel, agora=AGORA,
                                    documento_tipo="CPF")
    nomes = [tuple(r) for r in con.execute(
        "SELECT papel, nome FROM rc_pessoas WHERE assento_id=?", (aid,))]
    con.close()
    assert nomes == [("REGISTRADO", "FULANO TITULAR")]


def test_casamento_obito_natimorto_tem_o_mesmo_select(casa):
    """O <select> sem opcao vazia esta em toda gaveta de pessoa (macro
    unica) - a correcao no servidor vale para todas as especies."""
    for slug in ("casamento", "obito", "natimorto"):
        html = casa["c"].get(f"/rcpn/novo/{slug}",
                             follow_redirects=True).get_data(as_text=True)
        envio = _como_o_navegador(html, ("acao", "conferir"))
        assert envio.get("testemunha_documento_tipo") == "CPF", slug
