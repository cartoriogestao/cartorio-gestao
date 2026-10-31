"""A importação do E-Ofício terminou, e a tela não a oferece mais.

Decisão do oficial em 17/10/2026: o acervo do E-Ofício já entrou nesta
serventia, e os botões, links e itens de menu que disparavam a importação
saem. **Os importadores ficam** — módulos, rotas e testes —, como exemplo
para quem for trazer o acervo de outro sistema
(`docs/COMO_FAZER_UM_IMPORTADOR.md`). A tela de importação continua aberta
pelo endereço, para o administrador.

O QUE ESTES TESTES GUARDAM
    - o menu (`base.html`) e as telas que tinham o botão não levam a
      nenhuma rota de importar do E-Ofício — nem por link, nem por formulário;
    - essas telas não mostram «E-Ofício» ao usuário: o que sobrou citando o
      sistema passou a dizer «sistema antigo»;
    - as rotas de importar continuam existindo, e as telas abrem pelo
      endereço para o ADMIN.

Renderiza como ADMIN, que é quem via todos os botões.
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

SENHA = "Senha#12345"

# As rotas que importam do E-Ofício. Ficam no sistema; só saem da tela.
ROTAS_DE_IMPORTAR = (
    "notas_importar",
    "notas_assinaturas",
    "protesto_importar_eoficio",
    "atribuicoes_importar",
    "caixa_importar",
    "rcpn_importar_acervo",
    "livro3_importar_acervo",
    "ri_importar",
    "protesto_cenprot_xml_apresentantes_do_acervo",
    "cnib_credencial_do_acervo",
)

# As que abrem por GET — a tela de importação que ficou só pelo endereço.
TELAS_DE_IMPORTAR = (
    "/notas/importar",
    "/notas/assinaturas",
    "/protesto/importar-eoficio",
    "/atribuicoes/importar",
    "/caixa/importar",
    "/rcpn/importar-acervo",
    "/livro3/importar-do-acervo",
    "/registro-imoveis/importar",
)

# O menu e as telas onde havia botão de importar do E-Ofício. Nelas o nome
# do E-Ofício também não aparece mais.
TELAS = (
    "/",                                  # o menu (base.html)
    "/notas",                             # notas_painel
    "/notas/cartoes",                     # notas_cartoes
    "/caixa/emolumentos",                 # caixa_emolumentos
    "/protesto/cenprot-xml",              # protesto_cenprot_xml
    "/registro-imoveis/cnib/central",     # cnib_central
    "/selador",                           # selador_config
)

# Telas que só linkavam para a carga — o link sai; o texto delas é medido
# à parte, quando o caso pede.
TELAS_QUE_LINKAVAM = (
    "/livro3",
    "/registro-imoveis/importacoes",
    "/protesto/cenprot",
    "/protesto/titulos",
    "/nucleo/numeracao",
    "/implantacao",
    "/importar-padrao",
)

# O nome inteiro: sem a letra antes, «correcoes-de-oficio» (o endereço do menu)
# casava pelo «e-oficio» do meio e reprovava toda tela.
NOME = re.compile(r"(?<![a-z])e-of[ií]cio", re.I)


@pytest.fixture()
def casa(cg_casa):
    """ADMIN logado, protesto ligado e o acervo do E-Ofício no lugar.

    **O ACERVO NO LUGAR É O PIOR CASO**: o botão do CNIB e o do selador só
    apareciam quando o `acervo_eoficio.sqlite3` estava na pasta de dados. Sem
    o arquivo, a tela passaria sem botão por outro motivo. Ele é um SQLite
    de verdade, com a tabela que a tela do CNIB lê (vazia)."""
    from conftest import cg_login

    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA,
                              "ADMIN")
    cg_casa["db"].set_settings({"modulo_protesto_ligado": "1"})
    cg_login(cg_casa["c"], "mario", SENHA)
    pastas = {Path(cg_casa["app"].config["DATA_DIR"]),
              Path(cg_casa["db"].db_path).parent}
    criados = []
    for pasta in pastas:
        acervo = pasta / "acervo_eoficio.sqlite3"
        if not acervo.exists():
            with closing(sqlite3.connect(acervo)) as con:
                con.execute("CREATE TABLE tbCNIB_Registro (DATAPEDIDO TEXT)")
                con.commit()
            criados.append(acervo)
    try:
        yield cg_casa
    finally:
        for acervo in criados:
            acervo.unlink(missing_ok=True)


def _abrir(casa, caminho: str) -> str:
    r = casa["c"].get(caminho, follow_redirects=True)
    assert r.status_code == 200, f"{caminho} devolveu {r.status_code}"
    return r.get_data(as_text=True)


def _caminhos_de_importar(casa) -> set[str]:
    from flask import url_for

    with casa["app"].test_request_context():
        return {url_for(e) for e in ROTAS_DE_IMPORTAR}


def _destinos(html: str) -> set[str]:
    """Para onde a tela leva: todo href e todo action, sem a query."""
    return {m.group(2).split("?")[0].split("#")[0]
            for m in re.finditer(r'\b(href|action|formaction)="([^"]*)"', html)}


def _visivel(html: str) -> str:
    """O que chega ao usuário: sem script, estilo e comentário de HTML.
    Atributo fica — `title` e `placeholder` também são lidos."""
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.S | re.I)
    return re.sub(r"<!--.*?-->", " ", html, flags=re.S)


def _com_tabela_de_emolumentos(casa) -> None:
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute("INSERT INTO cx_vigencias (codigo, descricao, vigente) "
                    "VALUES (2026, 'Tabela de teste', 1)")
    con.close()


# ------------------------------------------------------------- o que saiu


@pytest.mark.parametrize("caminho", TELAS + TELAS_QUE_LINKAVAM)
def test_a_tela_nao_leva_a_importar_do_eoficio(casa, caminho):
    html = _abrir(casa, caminho)
    sobrou = _destinos(html) & _caminhos_de_importar(casa)
    assert not sobrou, f"{caminho} ainda leva a importar do E-Ofício: {sobrou}"


def test_a_tabela_de_emolumentos_carregada_nao_oferece_importar(casa):
    """Eram dois botões: um na tabela vazia, outro em «Atualizar a tabela»."""
    _com_tabela_de_emolumentos(casa)
    html = _abrir(casa, "/caixa/emolumentos")
    assert "vigência atual" in html, "a tabela de teste não entrou"
    assert 'value="importar"' not in html
    assert "Atualizar a tabela" not in html


def test_a_tabela_de_emolumentos_vazia_nao_oferece_importar(casa):
    html = _abrir(casa, "/caixa/emolumentos")
    assert "ainda não foi importada" in html
    assert 'value="importar"' not in html


def test_o_selador_nao_oferece_trazer_a_configuracao(casa):
    html = _abrir(casa, "/selador")
    assert 'value="importar"' not in html
    assert "tbSeladorConfiguracao" not in html


def test_o_cnib_nao_oferece_trazer_o_par_do_acervo(casa):
    html = _abrir(casa, "/registro-imoveis/cnib/central")
    assert "Trazer o par" not in html


def test_as_importacoes_do_ri_nao_completam_o_tipo_pelo_eoficio(casa):
    """O botão relia o matriculas.jsonl da exportação do E-Ofício."""
    html = _abrir(casa, "/registro-imoveis/importacoes")
    assert 'value="tipo_imovel"' not in html


# ---------------------------------------------- o nome do sistema também


@pytest.mark.parametrize("caminho", TELAS)
def test_a_tela_nao_mostra_o_nome_do_eoficio(casa, caminho):
    html = _visivel(_abrir(casa, caminho))
    achados = sorted({html[max(0, m.start() - 60):m.end() + 20].strip()
                      for m in NOME.finditer(html)})
    assert not achados, (
        f"{caminho} ainda mostra o E-Ofício ao usuário:\n" + "\n".join(achados))


def test_a_tabela_de_emolumentos_carregada_nao_mostra_o_nome(casa):
    _com_tabela_de_emolumentos(casa)
    assert not NOME.search(_visivel(_abrir(casa, "/caixa/emolumentos")))


def test_o_que_ficou_no_menu_diz_sistema_antigo(casa):
    html = _abrir(casa, "/")
    assert "Documentos avulsos (modelos do sistema antigo)" in html


def test_as_telas_que_linkavam_nao_dizem_mais_trazer_do_eoficio(casa):
    for caminho in TELAS_QUE_LINKAVAM:
        html = _visivel(_abrir(casa, caminho))
        assert "Trazer o acervo do E-Ofício" not in html, caminho
        assert "Trazer das atribuições" not in html, caminho


# ----------------------------------------------- mas o importador fica


def test_as_rotas_de_importar_continuam_no_sistema(casa):
    existentes = {r.endpoint for r in casa["app"].url_map.iter_rules()}
    faltam = [e for e in ROTAS_DE_IMPORTAR if e not in existentes]
    assert not faltam, f"rota de importar apagada: {faltam}"


@pytest.mark.parametrize("caminho", TELAS_DE_IMPORTAR)
def test_a_tela_de_importar_abre_pelo_endereco(casa, caminho):
    """Sem link, mas viva: o administrador chega pelo endereço."""
    _abrir(casa, caminho)
