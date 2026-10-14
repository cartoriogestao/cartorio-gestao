"""O razão dos selos, pesquisável — relato #33 do oficial.

    «preciso que seja possivel pesquisar os selo emitidos por data,
     especialidade, usuario.»

O TESTE QUE MAIS VALE AQUI É O DA DATA
    `sd_selos.obtido_em` guarda **dois formatos** — medido na produção:
    `2020-03-19 14:21:03` em **26.130** linhas (o que a carga trouxe) e
    `2026-09-01T14:17:06` em **5** (o `isoformat()` deste sistema).

    **`BETWEEN inicio AND fim` perde o último dia inteiro**, nos dois: qualquer
    hora é maior que a data nua. Ensaiado contra a produção — pedindo «até
    01/09/2026», o filtro com o `z` acha **1** selo e o `BETWEEN` cru acha
    **0**.
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

import selos_emitidos as SEM                                     # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco, "db": bd}


def _con(s):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _selo(s, numero: str, *, obtido_em: str, obtido_por: str = "BEATRIZ",
          atribuicao: str = "NOTAS", caminho: str = "/selo/notas/x",
          ato_id: int | None = 1, tabela: str | None = "nt_atos",
          cancelado_em: str | None = None) -> None:
    con = sqlite3.connect(s["banco"])
    con.execute(
        """INSERT INTO sd_selos (numero, caminho, atribuicao, tabela, ato_id,
                                 obtido_em, obtido_por, cancelado_em)
           VALUES (?,?,?,?,?,?,?,?)""",
        (numero, caminho, atribuicao, tabela, ato_id, obtido_em, obtido_por,
         cancelado_em))
    con.commit()
    con.close()


def test_etiquetas_encontram_so_selos_externos_do_rtdpj(s):
    _selo(s, "REGTER000000EXTERNO00000001", obtido_em="2026-09-10 09:00:00",
          atribuicao="RTDPJ", caminho="/selo/rtdpj/atos-em-geral",
          ato_id=None, tabela=None)
    _selo(s, "REGTER000000INTERNO00000002", obtido_em="2026-09-10 09:01:00",
          atribuicao="RTDPJ", caminho="/selo/rtdpj/atos-em-geral")
    _selo(s, "AUTENT000000NOTAS0000000003", obtido_em="2026-09-10 09:02:00",
          atribuicao="NOTAS", caminho="/selo/notas/x", ato_id=None, tabela=None)
    con = _con(s)
    achados = SEM.procurar_externos_rtdpj(con)
    con.close()
    assert [x["numero"] for x in achados] == ["REGTER000000EXTERNO00000001"]


def test_etiqueta_externa_recusa_cancelado_e_selo_de_ato_interno(s):
    _selo(s, "REGTER000000CANCELADO000001", obtido_em="2026-09-10 09:00:00",
          atribuicao="RTDPJ", ato_id=None, tabela=None,
          cancelado_em="2026-09-10T10:00:00")
    _selo(s, "REGTER000000INTERNO00000002", obtido_em="2026-09-10 09:01:00",
          atribuicao="RTDPJ")
    con = _con(s)
    with pytest.raises(SEM.SeloEmitidoError, match="cancelado"):
        SEM.externos_rtdpj_para_etiqueta(con, ["REGTER000000CANCELADO000001"])
    with pytest.raises(SEM.SeloEmitidoError, match="ligado a um ato"):
        SEM.externos_rtdpj_para_etiqueta(con, ["REGTER000000INTERNO00000002"])
    con.close()


# ============================================ a data


def test_O_ULTIMO_DIA_ENTRA_INTEIRO_nos_dois_formatos(s):
    """**O teste que mais vale deste arquivo.**

    A coluna tem `2020-03-19 14:21:03` (26.130 linhas) e
    `2026-09-01T14:17:06` (5). Pedir «até 01/09» com `BETWEEN` cru devolve
    ZERO daquele dia, nos dois formatos — porque qualquer hora é maior que a
    data nua.
    """
    _selo(s, "COM-ESPACO", obtido_em="2026-09-01 14:21:03")
    _selo(s, "COM-T", obtido_em="2026-09-01T14:17:06")
    _selo(s, "DEPOIS", obtido_em="2026-09-02 08:00:00")

    with _con(s) as con:
        r = SEM.procurar(con, inicio="2026-09-01", fim="2026-09-01")
        # o que o BETWEEN cru daria, para o teste PROVAR a diferença
        cru = con.execute(
            "SELECT COUNT(*) FROM sd_selos WHERE obtido_em BETWEEN ? AND ?",
            ("2026-09-01", "2026-09-01")).fetchone()[0]

    assert {x["numero"] for x in r["linhas"]} == {"COM-ESPACO", "COM-T"}
    assert cru == 0, "o BETWEEN cru perde o dia inteiro — é por isso que há o z"


def test_a_data_de_inicio_tambem_pega_o_dia_todo(s):
    _selo(s, "NO-DIA", obtido_em="2026-09-01 00:00:01")
    _selo(s, "ANTES", obtido_em="2026-08-31 23:59:59")
    with _con(s) as con:
        r = SEM.procurar(con, inicio="2026-09-01")
    assert [x["numero"] for x in r["linhas"]] == ["NO-DIA"]


# ============================================ os três campos do relato


def test_pesquisa_por_USUARIO_e_ele_se_chama_obtido_por(s):
    """`sd_selos` não tem coluna `usuario` — tem `obtido_por`. Foi o nome
    errado que me fez procurar e não achar."""
    _selo(s, "A", obtido_em="2026-09-01 10:00:00", obtido_por="BEATRIZ")
    _selo(s, "B", obtido_em="2026-09-01 10:00:00", obtido_por="GISELE")
    with _con(s) as con:
        r = SEM.procurar(con, quem="GISELE")
    assert [x["numero"] for x in r["linhas"]] == ["B"]


def test_pesquisa_por_ESPECIALIDADE_pela_atribuicao_e_pelo_caminho(s):
    _selo(s, "N", obtido_em="2026-09-01 10:00:00", atribuicao="NOTAS",
          caminho="/selo/notas/reconhecimento-firma")
    _selo(s, "I", obtido_em="2026-09-01 10:00:00", atribuicao="IMOVEL",
          caminho="/selo/imovel/certidao")
    with _con(s) as con:
        assert [x["numero"] for x in
                SEM.procurar(con, atribuicao="IMOVEL")["linhas"]] == ["I"]
        assert [x["numero"] for x in SEM.procurar(
            con, caminho="/selo/notas/reconhecimento-firma")["linhas"]] == ["N"]


def test_pesquisa_pelo_NUMERO_do_selo_por_pedaco(s):
    """Quem tem o selo na mão digita um pedaço — o código tem 28 caracteres."""
    _selo(s, "RECFIR000000PLAPKNVMA4SRV055", obtido_em="2026-09-01 10:00:00")
    _selo(s, "AUTENT000000NQWWFKVCRAMA9G29", obtido_em="2026-09-01 10:00:00")
    with _con(s) as con:
        r = SEM.procurar(con, numero="PLAPKN")
    assert len(r["linhas"]) == 1
    assert r["linhas"][0]["numero"].startswith("RECFIR")


# ============================================ as situações


def test_ORFAO_e_o_selo_COMPRADO_e_nao_usado(s):
    """São 9.060 no razão desta casa, e eles custaram dinheiro."""
    _selo(s, "USADO", obtido_em="2026-09-01 10:00:00", ato_id=7)
    _selo(s, "ORFAO", obtido_em="2026-09-01 10:00:00", ato_id=None, tabela=None)
    _selo(s, "CANC", obtido_em="2026-09-01 10:00:00", ato_id=None, tabela=None,
          cancelado_em="2026-09-02")
    with _con(s) as con:
        assert [x["numero"] for x in
                SEM.procurar(con, situacao="ORFAO")["linhas"]] == ["ORFAO"], (
            "cancelado não é órfão — quem cancelou já sabe")
        assert [x["numero"] for x in
                SEM.procurar(con, situacao="USADO")["linhas"]] == ["USADO"]
        assert [x["numero"] for x in
                SEM.procurar(con, situacao="CANCELADO")["linhas"]] == ["CANC"]


def test_situacao_desconhecida_RECUSA_em_vez_de_devolver_tudo(s):
    """Filtro que a tela ignora é pior que filtro que recusa: quem pediu «só
    os cancelados» leria a lista inteira achando que são todos cancelados."""
    _selo(s, "A", obtido_em="2026-09-01 10:00:00")
    with _con(s) as con:
        with pytest.raises(SEM.SeloEmitidoError) as erro:
            SEM.procurar(con, situacao="INVENTADA")
    assert "INVENTADA" in str(erro.value)


# ============================================ os números


def test_O_RESUMO_ACOMPANHA_O_FILTRO(s):
    """**Número que não acompanha o filtro é o carimbo que mente**: quem pede
    «da Gisele» e lê o total do razão conclui a coisa errada."""
    _selo(s, "A", obtido_em="2026-09-01 10:00:00", obtido_por="BEATRIZ")
    _selo(s, "B", obtido_em="2026-09-01 10:00:00", obtido_por="GISELE")
    _selo(s, "C", obtido_em="2026-09-01 10:00:00", obtido_por="GISELE",
          ato_id=None, tabela=None)
    with _con(s) as con:
        assert SEM.resumo(con)["total"] == 3
        r = SEM.resumo(con, quem="GISELE")
    assert r["total"] == 2 and r["usados"] == 1 and r["orfaos"] == 1


def test_as_opcoes_sao_MEDIDAS_e_nao_escritas(s):
    """Lista escrita à mão noutro arquivo envelhece na tarde em que se
    escreve — e o operador procura por um valor que a tela não oferece."""
    _selo(s, "A", obtido_em="2026-09-01 10:00:00", atribuicao="NOTAS",
          obtido_por="BEATRIZ", caminho="/selo/notas/x")
    _selo(s, "B", obtido_em="2026-09-01 10:00:00", atribuicao="PROTESTO",
          obtido_por="GISELE", caminho="/selo/protesto/y")
    with _con(s) as con:
        o = SEM.opcoes(con)
    assert o["atribuicoes"] == ["NOTAS", "PROTESTO"]
    assert o["usuarios"] == ["BEATRIZ", "GISELE"]
    assert o["caminhos"] == ["/selo/notas/x", "/selo/protesto/y"]


def test_a_pagina_tem_TETO(s):
    """O razão tem 26.135 linhas: sem teto a tela pediria o razão inteiro ao
    navegador do balcão."""
    for i in range(12):
        _selo(s, f"S{i:02}", obtido_em=f"2026-09-01 10:{i:02}:00")
    with _con(s) as con:
        r = SEM.procurar(con, por_pagina=5, pagina=2)
    assert len(r["linhas"]) == 5 and r["total"] == 12 and r["paginas"] == 3
    with _con(s) as con:
        assert SEM.procurar(con, por_pagina=99999)["por_pagina"] == (
            SEM.POR_PAGINA_MAXIMO)


# ============================================ o módulo e a tela


def test_este_modulo_SO_LE(s):
    """O razão é o que responde «este selo já foi usado?». Uma função que
    escrevesse aqui abriria um segundo caminho para o mesmo fato."""
    fonte = (RAIZ / "selos_emitidos.py").read_text(encoding="utf-8")
    import ast
    arvore = ast.parse(fonte)
    docs = set()
    for n in ast.walk(arvore):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                          ast.AsyncFunctionDef)) and n.body:
            pr = n.body[0]
            if (isinstance(pr, ast.Expr) and isinstance(pr.value, ast.Constant)
                    and isinstance(pr.value.value, str)):
                docs.add(id(pr.value))
    for n in ast.walk(arvore):
        if (isinstance(n, ast.Constant) and isinstance(n.value, str)
                and id(n) not in docs):
            alto = n.value.upper()
            for proibido in ("INSERT ", "UPDATE ", "DELETE "):
                assert proibido not in alto, (
                    f"este módulo não grava: achei {proibido!r}")


def test_a_rota_existe_E_A_TELA_MOSTRA_os_tres_filtros(s):
    _selo(s, "RECFIR0000000WK0H8VXAZS05W56", obtido_em="2026-09-01 10:00:00")
    regras = {r.rule for r in s["app"].url_map.iter_rules()}
    assert "/selos" in regras

    html = " ".join(s["c"].get("/selos").get_data(as_text=True).split())
    for campo in ('name="inicio"', 'name="fim"', 'name="atribuicao"',
                  'name="quem"', 'name="caminho"', 'name="situacao"',
                  'name="numero"'):
        assert campo in html, f"a tela não oferece {campo}"
    assert "RECFIR0000000WK0H8VXAZS05W56" in html


def test_a_tela_DIZ_QUE_NAO_E_a_de_selos_do_RI(s):
    """«Duas portas para a mesma sala» é o relato #12, e a saída não foi
    apagar uma: foi cada uma dizer a que veio."""
    html = " ".join(s["c"].get("/selos").get_data(as_text=True).split())
    assert "razão dos selos" in html
    assert "Registro de Imóveis" in html
    assert url_do_ri(s) in html


def url_do_ri(s) -> str:
    with s["app"].test_request_context():
        from flask import url_for
        return url_for("ri_selos")


def test_lista_vazia_DIZ_o_que_significa(s):
    """Lista vazia que só mostra nada faz o operador achar que quebrou."""
    html = " ".join(s["c"].get("/selos?quem=NINGUEM").get_data(as_text=True).split())
    assert "não quer dizer que não há selos" in html


# ============================================ a consolidação de 15/09/2026


def test_o_relatorio_antigo_ainda_responde_e_TRADUZ_os_filtros(s):
    """**`/relatorios/selos` continua respondendo — era a metade que o oficial
    perguntou em 15/09/2026: «o relatório dos últimos selos gerados ainda vai
    existir?»**

    Quem tem o endereço nos favoritos não encontra porta fechada; e ele
    **traduz os nomes dos filtros**, porque os de lá eram `de`, `ate` e
    `usuario`, e os de cá são `inicio`, `fim` e `quem`. Redirecionar sem
    traduzir abriria a tela **sem filtro nenhum**, e quem voltasse pelo
    favorito concluiria que a busca quebrou.
    """
    r = s["c"].get("/relatorios/selos?de=2026-09-01&ate=2026-09-02&usuario=BEATRIZ"
                   "&atribuicao=NOTAS&tipo=RECFIR&numero=000000&situacao=USADO"
                   "&agrupar=dia")
    assert r.status_code == 302, "o endereço antigo deixou de responder"
    destino = r.headers["Location"]
    assert "/selos" in destino
    for par, valor in (("inicio", "2026-09-01"), ("fim", "2026-09-02"),
                       ("quem", "BEATRIZ"), ("atribuicao", "NOTAS"),
                       ("tipo", "RECFIR"), ("numero", "000000"),
                       ("situacao", "USADO"), ("agrupar", "dia")):
        assert f"{par}={valor}" in destino, (
            f"o filtro {par} não foi traduzido — o favorito abriria sem ele")


def test_o_que_o_relatorio_antigo_tinha_esta_na_tela_que_ficou(s):
    """Sobrou **uma** tela, e ela tem de ter o que a outra tinha.

    As duas discordavam em **7.762 selos** sobre o que é «não usado», e a lista
    de lá perdia o último dia de todo período. O que se faz aqui é impedir a
    outra metade do estrago: juntar e **esquecer** um pedaço da antiga no
    caminho — que é o defeito de quem consolida olhando só para o que fica.
    """
    _selo(s, "RECFIR0000000WK0H8VXAZS05W56", obtido_em="2026-09-01 10:00:00")
    html = " ".join(s["c"].get("/selos").get_data(as_text=True).split())
    # o tipo do ato e o agrupamento eram só do relatório antigo
    assert 'name="tipo"' in html, "o filtro do tipo do ato não veio"
    assert 'name="agrupar"' in html, "o agrupamento não veio"
    # o quadro de números, com as quatro contagens dele
    for rotulo in ("Usados num ato", "não usados", "Cancelados",
                   "Do primeiro ao último"):
        assert rotulo in html, f"o quadro perdeu a linha {rotulo!r}"
    # e a frase que diz o que a tela NÃO faz
    assert "só lê" in html, (
        "a tela deixou de dizer que só lê — quem a abrisse procuraria onde "
        "emitir selo")


def test_um_rotulo_so_no_menu_para_o_razao_dos_selos(s):
    """Havia **duas** entradas «Selos emitidos» no menu, apontando para telas
    com réguas diferentes — e nenhum teste dizia nada, porque o validador do
    menu desistia calado do caso «mesmo rótulo, endereços diferentes».

    Sobrou uma. E o validador passou a exigir **declaração com motivo** para
    rótulo repetido: se este voltar, ele volta declarado — ou não volta.
    """
    pagina = s["c"].get("/").get_data(as_text=True)
    nav = pagina[pagina.find("<nav>"):pagina.find("</nav>")]
    assert nav.lower().count("selos emitidos") == 1, (
        "o rótulo «Selos emitidos» voltou a aparecer mais de uma vez no menu")
