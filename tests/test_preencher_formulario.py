"""Preencher o formulario do ato novo a partir do arquivo — #31, 2ª metade.

O oficial escolheu a **opcao 1** em 30/08/2026: o mesmo padrao de importacao,
jogando os dados na tela em vez de gravar direto.

O QUE ESTES TESTES GUARDAM

    **Que preencher NAO grava.** Importar traz acervo — o registro entra no
    livro com o numero que ja tinha. Preencher leva os dados para a tela de
    lavrar um ato NOVO, que vai tomar numero, ocupar folha, selar e cobrar. Sao
    dois caminhos, e confundi-los faria nascer ato com numero de outra casa.

    **Que e um registro de cada vez.** Um arquivo com trinta preencheria a tela
    com o primeiro e calaria os vinte e nove — e quem mandou acharia que os
    trinta entraram.

    **Que o que nao tem campo na tela e DITO.** A tela do assento nao pergunta
    tudo o que a tabela guarda; descartar em silencio faria o escrevente assinar
    achando que aquele dado esta la.

    **Que o preenchimento e consumido de uma vez.** Se ficasse na sessao, o
    formulario do proximo cliente abriria com os dados do anterior — e alguem
    lavraria assento com o nome de outra pessoa.

    **Que o campo da tela e MEDIDO do proprio modelo**, e nao escrito numa
    lista: escrita, ela envelheceria no dia em que a tela ganhasse um campo, e o
    preenchimento passaria a calar justamente o campo novo.
"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import importar_padrao as IMP                                    # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return achado.group(1) if achado else ""


@pytest.fixture(scope="module")
def casa(tmp_path_factory):
    from app import create_app
    from database import Database

    dados = tmp_path_factory.mktemp("dados")
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco).create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA,
                                "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"c": c, "banco": banco, "app": app}


def _arquivo(registros, especie="RCPN_ASSENTO") -> str:
    return json.dumps({"formato": IMP.FORMATO, "versao": IMP.VERSAO,
                       "especie": especie,
                       "de_onde_veio": "Serventia vizinha",
                       "registros": registros}, ensure_ascii=False)


def _preencher(casa, arquivo: str):
    tela = casa["c"].get("/importar-padrao").get_data(as_text=True)
    return casa["c"].post(
        "/importar-padrao/preencher",
        data={"csrf_token": _token(tela), "texto": arquivo},
        follow_redirects=True)


UM_ASSENTO = [{"chave": "V-1955-12", "serie": "RC_A", "especie": "NASCIMENTO",
               "nome": "MARIA DAS DORES SOUSA", "data_fato": "2026-08-01",
               "cor_raca": "PARDA"}]


# ------------------------------------------------------- o caminho inteiro


def test_o_formulario_do_assento_vem_preenchido(casa):
    html = _preencher(casa, _arquivo(UM_ASSENTO)).get_data(as_text=True)
    assert 'value="MARIA DAS DORES SOUSA"' in html, \
        "o nome não chegou ao formulário"
    assert 'value="2026-08-01"' in html


def test_a_tela_avisa_que_veio_de_arquivo_e_manda_conferir(casa):
    """**Quem assina é o escrevente**, e o arquivo não decidiu nada."""
    html = _preencher(casa, _arquivo(UM_ASSENTO)).get_data(as_text=True)
    assert "veio preenchida a partir de um arquivo" in html
    assert "V-1955-12" in html, "o registro de origem tem de ficar à vista"
    assert "Confira campo por campo antes de lavrar" in html


def test_preencher_nao_grava_nada(casa):
    """**Importar traz acervo; preencher adianta a digitação.**"""
    import sqlite3

    _preencher(casa, _arquivo(UM_ASSENTO))
    con = sqlite3.connect(casa["banco"])
    n = con.execute("SELECT COUNT(*) FROM rc_assentos").fetchone()[0]
    con.close()
    assert n == 0, "preencher gravou um assento — e ele não pode gravar"


def test_o_que_a_tela_nao_pergunta_e_dito(casa):
    """A `serie` não tem campo na tela — quem manda nela é a espécie.

    Descartá-la em silêncio faria quem preparou o arquivo achar que ela foi
    considerada.
    """
    html = _preencher(casa, _arquivo(UM_ASSENTO)).get_data(as_text=True)
    assert "esta tela não pergunta" in html
    assert "serie" in html


def test_o_preenchimento_e_consumido_de_uma_vez(casa):
    """**Se ficasse na sessão, o próximo cliente abriria com os dados do
    anterior** — e alguém lavraria assento com o nome de outra pessoa."""
    _preencher(casa, _arquivo(UM_ASSENTO))
    de_novo = casa["c"].get("/rcpn/assento/novo").get_data(as_text=True)
    assert "MARIA DAS DORES SOUSA" not in de_novo, \
        "o formulário abriu de novo com os dados do cliente anterior"


def test_a_matricula_do_ri_tambem_se_preenche(casa):
    html = _preencher(casa, _arquivo(
        [{"chave": "V-315", "numero": "315", "logradouro": "RUA DAS FLORES",
          "bairro": "CENTRO", "area_valor": "360"}],
        especie="RI_MATRICULA")).get_data(as_text=True)
    assert 'value="RUA DAS FLORES"' in html
    assert 'value="360"' in html


# ------------------------------------------------------- o que se recusa


def test_arquivo_com_varios_registros_e_recusado(casa):
    """**Um ato de cada vez**: com trinta, a tela ficaria com o primeiro e os
    outros sumiriam sem ninguém ver."""
    r = _preencher(casa, _arquivo(
        [dict(UM_ASSENTO[0]), dict(UM_ASSENTO[0], chave="V-2")]))
    html = r.get_data(as_text=True)
    assert "um ato de cada vez" in html
    assert "use a importação" in html


def test_registro_ruim_nao_preenche_e_diz_por_que(casa):
    r = _preencher(casa, _arquivo(
        [{"chave": "V-9", "serie": "RC_A", "especie": "NASCIMENTO",
          "nome": "FULANO", "campo_que_nao_existe": "x"}]))
    assert "campo_que_nao_existe" in r.get_data(as_text=True)


# ------------------------------------------------------- os guardas


def test_os_campos_da_tela_sao_medidos_do_proprio_modelo():
    """Escrita numa lista, ela envelheceria no dia em que a tela mudasse."""
    do_assento = IMP.campos_da_tela("atrib_rcpn_novo.html")
    assert "nome" in do_assento and "data_fato" in do_assento
    assert "serie" not in do_assento, "a série não é perguntada, e não deve ser"
    da_matricula = IMP.campos_da_tela("ri_nova.html")
    assert "logradouro" in da_matricula and "area_valor" in da_matricula


def test_o_aviso_e_uma_macro_e_nao_duas_copias():
    """A regra de `_fraude.html`: duas cópias divergem no primeiro conserto."""
    telas = RAIZ / "templates"
    assert (telas / "_veio_de_arquivo.html").is_file()
    for tela in ("atrib_rcpn_novo.html", "ri_nova.html"):
        html = (telas / tela).read_text(encoding="utf-8")
        assert "_veio_de_arquivo.html" in html, f"{tela} não importa a macro"


def test_o_dado_da_pessoa_nao_viaja_no_endereco(casa):
    """**Nome e data de nascimento numa `query string`** ficam no histórico do
    navegador do balcão e no registro do servidor."""
    r = casa["c"].post(
        "/importar-padrao/preencher",
        data={"csrf_token": _token(casa["c"].get("/importar-padrao").get_data(
            as_text=True)), "texto": _arquivo(UM_ASSENTO)},
        follow_redirects=False)
    assert r.status_code in (301, 302, 303)
    assert "MARIA" not in r.headers.get("Location", ""), \
        "o nome do cliente foi parar no endereço"


def test_a_matricula_nova_repopula_o_que_foi_digitado(casa):
    """**Isto era um defeito que já existia**: até 30/08/2026 `ri_nova.html`
    não tinha um único `value` vindo do formulário — se a lavratura falhasse
    por qualquer motivo, o operador perdia tudo o que tinha digitado."""
    html = (RAIZ / "templates" / "ri_nova.html").read_text(encoding="utf-8")
    for campo in ("logradouro", "bairro", "cep", "area_valor",
                  "descricao_perimetro", "teor"):
        assert f"form.get('{campo}'" in html, \
            f"o campo «{campo}» não volta preenchido depois de um erro"
