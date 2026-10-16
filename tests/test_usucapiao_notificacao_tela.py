"""A tela de expedir notificacao no usucapiao — relatos #30 e #21.

O QUE ELA GUARDA

    **Que a tela oferece so as quatro formas da norma**, e na ordem. Um campo
    livre ali deixaria a serventia notificar por um meio que o Codigo nao preve
    — e a notificacao seria nula sem ninguem perceber.

    **Que o prazo nao e campo livre.** Ele sai da regra do destinatario: prazo
    digitado errado para menos produz anuencia por silencio de quem ainda podia
    impugnar.

    **Que o papel sai com o teor GUARDADO.** Remonta-lo traria o processo como
    esta hoje, e nao como estava quando o papel saiu.

    **Que o manual esta a um clique de quem vai expedir.** Manual que mora so na
    documentacao e manual que ninguem abre no balcao.
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
    achado = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return achado.group(1) if achado else ""


@pytest.fixture(scope="module")
def casa(tmp_path_factory):
    from app import create_app
    from database import Database

    dados = tmp_path_factory.mktemp("dados")
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco).create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA,
                                "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)

    import usucapiao as US
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    pid = US.autuar(con, numero="7", modalidade="ORDINARIA",
                    agora="2026-08-30T09:00",
                    requerente_nome="JOÃO BATISTA DE SOUSA",
                    imovel_descricao="Terreno urbano de 12m por 30m",
                    imovel_municipio="Cidade Exemplo", usuario="mario")
    con.commit()
    con.close()
    return {"c": c, "banco": banco, "pid": pid}


def _ficha(casa) -> str:
    return casa["c"].get(f"/usucapiao/{casa['pid']}").get_data(as_text=True)


def _expedir(casa, **troca):
    dados = {"csrf_token": _token(_ficha(casa)),
             "destinatario": "MARIA DAS DORES SOUSA",
             "destinatario_papel": "Confrontante ao norte",
             "endereco": "Rua do Comércio, 45, Cidade Exemplo/MA",
             "forma": "PESSOAL", "prazo_chave": "CONFRONTANTE",
             "tentativa": "1"}
    dados.update(troca)
    return casa["c"].post(f"/usucapiao/{casa['pid']}/notificar", data=dados,
                          follow_redirects=True)


# ------------------------------------------------------- o formulário


def test_a_ficha_oferece_expedir_notificacao(casa):
    html = _ficha(casa)
    assert "Expedir notificação" in html
    assert "/notificar" in html


def _formulario_da_notificacao(casa) -> str:
    """So o formulario de expedir notificacao, e nao a pagina inteira.

    **A pagina tem OUTRO seletor com «EDITAL» dentro** — o de tipo de
    movimento, que lista os tipos existentes. Procurar na pagina toda comparava
    posicoes de formularios diferentes, e o teste reprovava a ordem estando ela
    certa.

    > **Decima primeira vez neste projeto que se procura no lugar largo
    > demais** — e a terceira so nesta tarde. O alvo precisa ser recortado
    > antes de se procurar dentro dele.
    """
    html = _ficha(casa)
    i = html.index("/notificar")
    return html[i:html.index("</form>", i)]


def test_a_tela_oferece_so_as_quatro_formas_da_norma(casa):
    """**Campo livre ali deixaria notificar por meio que o Código não prevê.**"""
    import us_notificacao as UN

    form = _formulario_da_notificacao(casa)
    for f in UN.ORDEM_DAS_FORMAS:
        assert f'value="{f}"' in form, f"faltou a forma {f}"
    assert form.index('value="PESSOAL"') < form.index('value="EDITAL"'), \
        "o edital tem de vir por último — a ordem é da norma"


def test_a_tela_diz_que_o_edital_e_o_ultimo(casa):
    html = _ficha(casa)
    assert "frustradas as anteriores" in html


def test_o_prazo_nao_e_campo_livre(casa):
    """**Prazo errado para menos produz anuência por silêncio.**"""
    import us_notificacao as UN

    html = _ficha(casa)
    for p in UN.PRAZOS:
        assert f'value="{p["chave"]}"' in html
    assert "sai da norma" in html


def test_a_tela_mostra_onde_notificar_com_o_artigo(casa):
    """Os três endereços possíveis, para quem preenche não ter de procurar."""
    html = _ficha(casa)
    assert "endereço indicado pelo requerente" in html
    assert "598" in html


def test_o_manual_esta_a_um_clique(casa):
    """**Manual que mora só na documentação é manual que ninguém abre.**"""
    assert "/usucapiao/notificacao/manual" in _ficha(casa)


def test_os_tres_oficios_dos_entes_ficam_acessiveis_para_imprimir(casa):
    """Relato #88: a tela dizia que gerou, mas não oferecia os papéis."""
    html = _ficha(casa)
    resposta = casa["c"].post(
        f"/usucapiao/{casa['pid']}/ciencia-aos-entes",
        data={"csrf_token": _token(html)}, follow_redirects=True)
    pagina = resposta.get_data(as_text=True)
    assert resposta.status_code == 200
    assert "Abrir para imprimir" in pagina

    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    oficios = con.execute(
        """SELECT id, destinatario, teor_expedido FROM us_movimentos
             WHERE processo_id=? AND tipo='CIENCIA' ORDER BY id""",
        (casa["pid"],)).fetchall()
    con.close()
    assert len(oficios) == 3
    for oficio in oficios:
        endereco = (f"/usucapiao/{casa['pid']}/notificacao/"
                    f"{oficio['id']}")
        assert endereco in pagina
        papel = casa["c"].get(endereco)
        assert papel.status_code == 200
        texto = papel.get_data(as_text=True)
        assert oficio["destinatario"] in texto
        assert oficio["teor_expedido"] in texto


# ------------------------------------------------------- expedir


def test_expedir_leva_ao_papel_pronto_para_imprimir(casa):
    html = _expedir(casa).get_data(as_text=True)
    assert "Notificação expedida" in html
    assert "MARIA DAS DORES SOUSA" in html
    assert "USUCAPIÃO EXTRAJUDICIAL" in html
    assert "RECIBO" in html, "o recibo tem de sair no mesmo papel"


def test_o_papel_diz_que_o_que_prova_e_o_comprovante(casa):
    """A linha no sistema não prova notificação nenhuma."""
    html = _expedir(casa, destinatario="ANTONIO PEREIRA").get_data(as_text=True)
    assert "comprovante que volta assinado" in html


def test_sem_endereco_a_tela_recusa_e_nao_grava(casa):
    """Movimento sem papel que o sustente é uma linha dizendo que a serventia
    notificou alguém sem ter notificado."""
    con = sqlite3.connect(casa["banco"])
    antes = con.execute("SELECT COUNT(*) FROM us_movimentos").fetchone()[0]
    con.close()

    html = _expedir(casa, endereco="", destinatario="JOSE DA SILVA"
                    ).get_data(as_text=True)
    assert "Endereço" in html

    con = sqlite3.connect(casa["banco"])
    depois = con.execute("SELECT COUNT(*) FROM us_movimentos").fetchone()[0]
    con.close()
    assert depois == antes


def test_o_papel_sai_do_teor_guardado_e_nao_remontado(casa):
    """**O que o notificado leu é o de então.**

    Depois de expedir, muda-se a descrição do imóvel no processo — e o papel
    tem de continuar mostrando a de antes.
    """
    _expedir(casa, destinatario="CARLOS ANDRADE")
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    mid = con.execute(
        "SELECT id FROM us_movimentos WHERE destinatario='CARLOS ANDRADE'"
    ).fetchone()["id"]
    con.execute("UPDATE us_processos SET imovel_descricao=? WHERE id=?",
                ("OUTRA COISA COMPLETAMENTE DIFERENTE", casa["pid"]))
    con.commit()
    con.close()

    html = casa["c"].get(
        f"/usucapiao/{casa['pid']}/notificacao/{mid}").get_data(as_text=True)
    assert "Terreno urbano de 12m por 30m" in html
    assert "OUTRA COISA COMPLETAMENTE DIFERENTE" not in html


# ------------------------------------------------------- o manual


def test_o_manual_abre_e_traz_o_passo_a_passo(casa):
    html = casa["c"].get("/usucapiao/notificacao/manual").get_data(as_text=True)
    assert "Como efetuar a notificação" in html
    assert "754" in html, "a remissão que autoriza a regra tem de estar à vista"
    assert "ATA NOTARIAL" in html.upper()


def test_o_manual_marca_a_procedencia_de_cada_prazo(casa):
    """**«Lido» e «citado» são coisas diferentes**, e o prazo do titular tabular
    vem da lei que não foi lida dentro da casa."""
    html = casa["c"].get("/usucapiao/notificacao/manual").get_data(as_text=True)
    assert "lido" in html and "citado" in html
    assert "não foi lido aqui dentro" in html


def test_o_manual_nao_mostra_asterisco_de_norma(casa):
    """A marcação `**` do código vira negrito na tela — filtro `|forte`."""
    html = casa["c"].get("/usucapiao/notificacao/manual").get_data(as_text=True)
    assert "**" not in html, "a marcação da norma vazou para a tela"


def test_a_tela_diz_o_que_ja_se_tentou_e_qual_e_a_proxima_forma(casa):
    """**Sem isso, quem expede a segunda notificacao repete a mesma forma ou
    pula direto para o edital** — que custa, demora, e sem a frustracao
    registrada e nulo.

    O caso: MARIA ja foi notificada pessoalmente nos testes acima; a proxima
    forma da norma e o RTD.
    """
    html = _ficha(casa)
    assert "o que já se tentou" in html
    assert "MARIA DAS DORES SOUSA" in html
    i = html.index("o que já se tentou")
    quadro = html[i:i + 3000]
    assert "PESSOAL" in quadro
    assert "RTD" in quadro, "a próxima forma da norma não foi sugerida"
