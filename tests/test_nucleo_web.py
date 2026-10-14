"""
Testes das telas do nucleo — livros, termos, inutilizacoes e encerramentos.

O QUE ELES CONFEREM
    Que existe TELA para o que o dominio ja sabia fazer. Ate 25/08/2026
    `escrituracao.py` — 41 KB, os 24 livros — nao tinha uma unica rota: abrir
    livro, encerrar livro, inutilizar folha e encerrar o dia eram funcoes
    prontas e testadas que ninguem chamava.

    E que a tela NAO REPETE A REGRA DO DOMINIO: quem recusa o segundo livro
    aberto, a folha escriturada, o livro ja encerrado e o dia repetido e
    `escrituracao`, com frase de balcao. Ha teste que manda o pedido direto
    para a rota, sem passar pelo botao, so para ver o dominio recusar.
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
AGORA = "2026-08-25T09:00:00"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _sessao(cg_casa, papel: str = "ADMIN"):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, papel)
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco}


@pytest.fixture()
def s(cg_casa):
    return _sessao(cg_casa)


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _post(s, rota: str, origem: str | None = None, **campos) -> str:
    """POST com o csrf que a tela de origem entregou."""
    c = s["c"]
    token = _token(c.get(origem or "/nucleo/livros").get_data(as_text=True))
    return c.post(rota, data={"csrf_token": token, **campos},
                  follow_redirects=True).get_data(as_text=True)


def _abrir(s, serie: str = "RC_A", **campos) -> int:
    """Abre um livro pela tela e devolve o id dele."""
    _post(s, "/nucleo/livros/abrir", serie=serie, **campos)
    con = _con(s)
    livro_id = con.execute(
        "SELECT id FROM nu_livros WHERE serie=? ORDER BY id DESC LIMIT 1",
        (serie,)).fetchone()["id"]
    con.close()
    return int(livro_id)


# ------------------------------------------------------------- o panorama


def test_o_panorama_lista_as_series_das_seis_atribuicoes(s):
    html = s["c"].get("/nucleo/livros").get_data(as_text=True)
    assert "Livro de Apontamento" in html
    assert "Livro A — Registro de Nascimento" in html
    assert "Livro B do Registro de Títulos e Documentos" in html
    assert "Livro de Escrituras" in html          # Notas, atribuição 1


def test_o_panorama_diz_quando_nao_ha_livro_aberto(s):
    html = s["c"].get("/nucleo/livros").get_data(as_text=True)
    assert "nenhum aberto" in html


def test_o_menu_leva_aos_livros_e_ao_encerramento_diario(s):
    html = s["c"].get("/nucleo/livros").get_data(as_text=True)
    assert "Livros e termos" in html
    assert "Encerramento diário" in html


# --------------------------------------------------------- abrir o livro


def test_abrir_livro_grava_o_termo_de_abertura(s):
    # O TERMO NAO E FORMALIDADE: e o que diz o que o livro e, quantas folhas
    # tem e onde comeca. E o primeiro papel que a inspecao pede.
    livro_id = _abrir(s, "RC_A")
    linha = _con(s).execute("SELECT * FROM nu_livros WHERE id=?",
                            (livro_id,)).fetchone()
    assert linha["numero"] == "1"                 # o primeiro da série
    assert "TERMO DE ABERTURA" in linha["termo_abertura"]
    assert "Livro A — Registro de Nascimento" in linha["termo_abertura"]
    assert "CNS 000000" in linha["termo_abertura"]
    assert int(linha["encerrado"]) == 0


def test_o_numero_do_livro_nao_se_digita_e_anda_sozinho(s):
    # Digitar o numero abriria a porta para dois Livros 3 na mesma serie.
    primeiro = _abrir(s, "RC_A")
    _post(s, f"/nucleo/livros/{primeiro}/encerrar",
          origem=f"/nucleo/livros/{primeiro}", motivo="livro esgotado")
    segundo = _abrir(s, "RC_A", numero="99")      # o campo nem existe na tela
    numeros = [r["numero"] for r in _con(s).execute(
        "SELECT numero FROM nu_livros WHERE serie='RC_A' ORDER BY id")]
    assert numeros == ["1", "2"]
    assert segundo != primeiro


def test_nao_se_abre_um_segundo_livro_aberto_na_mesma_serie(s):
    # Quem recusa e o dominio: dois livros abertos na mesma serie fazem o
    # mesmo numero de ordem sair em dois lugares.
    _abrir(s, "RC_A")
    html = _post(s, "/nucleo/livros/abrir", serie="RC_A")
    assert "Encerre-o antes" in html
    assert _con(s).execute(
        "SELECT COUNT(*) FROM nu_livros WHERE serie='RC_A'").fetchone()[0] == 1


def test_livro_diario_exige_o_dia(s):
    html = _post(s, "/nucleo/livros/abrir", serie="PT_PROTOCOLO")
    assert "informe o dia" in html
    assert _con(s).execute("SELECT COUNT(*) FROM nu_livros").fetchone()[0] == 0


def test_livro_diario_abre_com_o_dia_e_convive_com_o_de_outro_dia(s):
    # O livro da vez de uma serie diaria e o DO DIA: o protocolo de ontem esta
    # encerrado, e lancar nele seria antedatar.
    _abrir(s, "PT_PROTOCOLO", dia="2026-08-24")
    _abrir(s, "PT_PROTOCOLO", dia="2026-08-25")
    dias = [r["dia"] for r in _con(s).execute(
        "SELECT dia FROM nu_livros WHERE serie='PT_PROTOCOLO' ORDER BY dia")]
    assert dias == ["2026-08-24", "2026-08-25"]


def test_serie_desconhecida_e_recusada_com_frase_de_balcao(s):
    html = _post(s, "/nucleo/livros/abrir", serie="NAO_EXISTE")
    assert "não existe" in html.lower()


def test_auditoria_ve_os_livros_mas_nao_abre(cg_casa):
    sessao = _sessao(cg_casa, papel="AUDITOR")
    c = sessao["c"]
    pagina = c.get("/nucleo/livros")
    assert pagina.status_code == 200
    # Com o csrf da própria tela — sem ele o 400 chegaria antes do 403, e o
    # teste diria "recusou" sem ter provado por qual motivo.
    token = _token(pagina.get_data(as_text=True))
    resposta = c.post("/nucleo/livros/abrir",
                      data={"csrf_token": token, "serie": "RC_A"})
    assert resposta.status_code == 403
    assert _con(sessao).execute(
        "SELECT COUNT(*) FROM nu_livros").fetchone()[0] == 0


# ---------------------------------------------------------- a ficha


def test_a_ficha_do_livro_traz_o_termo_e_a_conferencia(s):
    livro_id = _abrir(s, "RC_A")
    html = s["c"].get(f"/nucleo/livros/{livro_id}").get_data(as_text=True)
    assert "TERMO DE ABERTURA" in html
    assert "nada a apontar" in html               # livro novo está em ordem
    assert "Nenhum ato neste livro ainda" in html


def test_ficha_de_livro_que_nao_existe_avisa_e_volta(s):
    r = s["c"].get("/nucleo/livros/9999", follow_redirects=True)
    assert r.status_code == 200
    assert "não encontrado" in r.get_data(as_text=True)


def test_a_conferencia_aponta_a_folha_em_branco_no_meio(s):
    # `conferir_livro` e a inspecao antes da inspecao: folha em branco no meio
    # do livro, sem termo de inutilizacao, e o que ela procura.
    livro_id = _abrir(s, "RC_A")
    con = _con(s)
    with con:
        for folha, ordem in ((1, 1), (3, 2)):     # a folha 2 fica em branco
            con.execute(
                """INSERT INTO nu_lugares(livro_id, serie, folha, verso, ordem,
                       rotulo, inicio, paginas, numero_ordem, tabela,
                       referencia, ocupado_em)
                   VALUES (?,'RC_A',?,0,1,?,1,1,?,'rc_atos',?,?)""",
                (livro_id, folha, str(folha), ordem, ordem, AGORA))
    con.close()
    html = s["c"].get(f"/nucleo/livros/{livro_id}").get_data(as_text=True)
    assert "folha(s) em branco no meio do livro" in html


# ------------------------------------------------------- inutilizar


def test_inutilizar_folha_em_branco_grava_o_termo(s):
    livro_id = _abrir(s, "RC_A")
    html = _post(s, f"/nucleo/livros/{livro_id}/inutilizar",
                 origem=f"/nucleo/livros/{livro_id}",
                 rotulo="7", motivo="folha danificada na impressão")
    assert "inutilizada" in html
    linha = _con(s).execute(
        "SELECT * FROM nu_inutilizacoes WHERE livro_id=?", (livro_id,)).fetchone()
    assert linha["rotulo"] == "7"
    assert linha["motivo"] == "folha danificada na impressão"
    assert linha["teor"].startswith("FOLHA INUTILIZADA.")
    assert "nada nela podendo ser lançado" in linha["teor"]


def test_motivo_curto_de_inutilizacao_e_recusado(s):
    # O motivo sai impresso no termo, e e o que a inspecao le.
    livro_id = _abrir(s, "RC_A")
    html = _post(s, f"/nucleo/livros/{livro_id}/inutilizar",
                 origem=f"/nucleo/livros/{livro_id}", rotulo="7", motivo="erro")
    assert "dez letras" in html
    assert _con(s).execute(
        "SELECT COUNT(*) FROM nu_inutilizacoes").fetchone()[0] == 0


def test_folha_escriturada_nao_se_inutiliza(s):
    # A face escriturada nao se inutiliza: o ato nela e que se cancela. Sao
    # coisas diferentes, e confundi-las apaga ato bom.
    livro_id = _abrir(s, "RC_A")
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO nu_lugares(livro_id, serie, folha, verso, ordem,
                   rotulo, inicio, paginas, numero_ordem, tabela, referencia,
                   ocupado_em)
               VALUES (?,'RC_A',5,0,1,'5',1,1,1,'rc_atos',1,?)""",
            (livro_id, AGORA))
    con.close()
    html = _post(s, f"/nucleo/livros/{livro_id}/inutilizar",
                 origem=f"/nucleo/livros/{livro_id}", rotulo="5",
                 motivo="quero apagar este ato")
    assert "está escriturada" in html
    assert _con(s).execute(
        "SELECT COUNT(*) FROM nu_inutilizacoes").fetchone()[0] == 0


def test_folha_fora_do_livro_e_recusada_dizendo_a_faixa(s):
    livro_id = _abrir(s, "RC_A", folhas="10")
    html = _post(s, f"/nucleo/livros/{livro_id}/inutilizar",
                 origem=f"/nucleo/livros/{livro_id}", rotulo="88",
                 motivo="folha que não existe neste livro")
    assert "está fora do Livro" in html


# --------------------------------------------------------- encerrar


def test_encerrar_o_livro_grava_o_termo_com_o_que_ficou_em_branco(s):
    livro_id = _abrir(s, "RC_A", folhas="10")
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO nu_lugares(livro_id, serie, folha, verso, ordem,
                   rotulo, inicio, paginas, numero_ordem, tabela, referencia,
                   ocupado_em)
               VALUES (?,'RC_A',1,0,1,'1',1,1,1,'rc_atos',1,?)""",
            (livro_id, AGORA))
    con.close()
    html = _post(s, f"/nucleo/livros/{livro_id}/encerrar",
                 origem=f"/nucleo/livros/{livro_id}",
                 motivo="mudança de série")
    assert "encerrado" in html
    linha = _con(s).execute("SELECT * FROM nu_livros WHERE id=?",
                            (livro_id,)).fetchone()
    assert int(linha["encerrado"]) == 1
    assert "TERMO DE ENCERRAMENTO" in linha["termo_encerramento"]
    assert "INUTILIZADAS" in linha["termo_encerramento"]
    assert linha["motivo_encerramento"] == "mudança de série"


def test_livro_encerrado_nao_encerra_de_novo(s):
    livro_id = _abrir(s, "RC_A")
    _post(s, f"/nucleo/livros/{livro_id}/encerrar",
          origem=f"/nucleo/livros/{livro_id}")
    html = _post(s, f"/nucleo/livros/{livro_id}/encerrar",
                 origem=f"/nucleo/livros/{livro_id}")
    assert "já está encerrado" in html


def test_a_ficha_de_livro_encerrado_nao_oferece_inutilizar_nem_encerrar(s):
    livro_id = _abrir(s, "RC_A")
    _post(s, f"/nucleo/livros/{livro_id}/encerrar",
          origem=f"/nucleo/livros/{livro_id}")
    html = s["c"].get(f"/nucleo/livros/{livro_id}").get_data(as_text=True)
    assert "Inutilizar, com termo" not in html
    assert "Encerrar o livro" not in html


# ------------------------------------------------------------ os termos


def test_o_termo_sai_em_odt_para_colar_no_livro_de_papel(s):
    # Termo que so existe dentro do banco nao serve: o livro fisico e que
    # precisa dele na primeira e na ultima folha.
    livro_id = _abrir(s, "RC_A")
    r = s["c"].get(f"/nucleo/livros/{livro_id}/termo/abertura")
    assert r.status_code == 200
    assert "opendocument" in r.headers["Content-Type"]
    assert "termo-abertura-rc_a-livro-1.odt" in r.headers["Content-Disposition"]
    assert r.data[:2] == b"PK"                    # é um .odt de verdade


def test_termo_que_ainda_nao_existe_avisa_em_vez_de_baixar_vazio(s):
    livro_id = _abrir(s, "RC_A")
    html = s["c"].get(f"/nucleo/livros/{livro_id}/termo/encerramento",
                      follow_redirects=True).get_data(as_text=True)
    assert "ainda não tem termo de encerramento" in html


def test_termo_de_nome_inventado_da_404(s):
    livro_id = _abrir(s, "RC_A")
    assert s["c"].get(f"/nucleo/livros/{livro_id}/termo/qualquer").status_code == 404


# ------------------------------------------------- encerramento diário


def test_a_tela_do_encerramento_diario_lista_os_tres_protocolos(s):
    html = s["c"].get("/nucleo/encerramento-diario").get_data(as_text=True)
    assert "Livro de Protocolo do Protesto" in html
    assert "Livro de Protocolo do RCPJ" in html
    assert "Livro de Protocolo do RTD" in html


def test_dia_sem_movimento_tambem_se_encerra_e_o_termo_diz_isso(s):
    # E o que distingue dia PARADO de dia NAO ESCRITURADO — e e a diferenca
    # que a inspecao procura.
    html = _post(s, "/nucleo/encerramento-diario",
                 origem="/nucleo/encerramento-diario",
                 serie="PT_PROTOCOLO", dia="2026-08-25")
    assert "sem movimento" in html
    linha = _con(s).execute(
        "SELECT * FROM nu_encerramentos_diarios WHERE dia='2026-08-25'").fetchone()
    assert linha["quantidade"] == 0
    assert "Não houve movimento neste dia." in linha["teor"]
    assert linha["encerrado_por"] == "MARIO EXEMPLO DOS SANTOS"


def test_o_mesmo_dia_nao_se_encerra_duas_vezes(s):
    _post(s, "/nucleo/encerramento-diario", origem="/nucleo/encerramento-diario",
          serie="PT_PROTOCOLO", dia="2026-08-25")
    html = _post(s, "/nucleo/encerramento-diario",
                 origem="/nucleo/encerramento-diario",
                 serie="PT_PROTOCOLO", dia="2026-08-25")
    assert "já foi encerrado" in html
    assert _con(s).execute(
        "SELECT COUNT(*) FROM nu_encerramentos_diarios").fetchone()[0] == 1


def test_serie_que_nao_e_diaria_nao_encerra_o_dia(s):
    # Quem recusa e o dominio: o Livro A encerra quando enche, nao no fim do
    # dia. A tela nem oferece — mas se o pedido chegar assim, ele recusa.
    html = _post(s, "/nucleo/encerramento-diario",
                 origem="/nucleo/encerramento-diario",
                 serie="RC_A", dia="2026-08-25")
    assert "não é livro diário" in html


def test_o_dia_encerrado_fecha_tambem_o_livro_daquele_dia(s):
    livro_id = _abrir(s, "PT_PROTOCOLO", dia="2026-08-25")
    _post(s, "/nucleo/encerramento-diario", origem="/nucleo/encerramento-diario",
          serie="PT_PROTOCOLO", dia="2026-08-25")
    linha = _con(s).execute("SELECT * FROM nu_livros WHERE id=?",
                            (livro_id,)).fetchone()
    assert int(linha["encerrado"]) == 1
    assert linha["motivo_encerramento"] == "encerramento diário"


def test_o_dia_com_movimento_e_sem_termo_aparece_como_atrasado(s):
    # Nao basta encerrar hoje: tem de dar para provar que nao ficou dia aberto
    # atras. E a tela que a inspecao pede.
    _abrir(s, "PT_PROTOCOLO", dia="2026-08-20")
    html = s["c"].get("/nucleo/encerramento-diario").get_data(as_text=True)
    assert "2026-08-20" in html
    # e o panorama dos livros avisa também
    assert "sem termo de encerramento" in \
        s["c"].get("/nucleo/livros").get_data(as_text=True)


def test_auditoria_nao_encerra_o_dia(cg_casa):
    sessao = _sessao(cg_casa, papel="AUDITOR")
    html = _post(sessao, "/nucleo/encerramento-diario",
                 origem="/nucleo/encerramento-diario",
                 serie="PT_PROTOCOLO", dia="2026-08-25")
    assert "auditoria não encerra" in html
    assert _con(sessao).execute(
        "SELECT COUNT(*) FROM nu_encerramentos_diarios").fetchone()[0] == 0


# ------------------------------------------------- a numeração dos livros
#
# Esta tela faltava, e sem ela o passo 5 do roteiro nao tinha onde acontecer:
# a carga semeia sete series do acervo e declara duas que o acervo NAO SABE
# informar. Informa-las e decisao de quem le o livro fisico — e sem informar,
# o primeiro ato de cada uma nasce com o numero 1 sobre acervo que ja passou
# disso.


def test_a_tela_de_numeracao_lista_os_livros_do_nucleo(s):
    html = s["c"].get("/nucleo/numeracao").get_data(as_text=True)
    assert "Livro de Apontamento" in html
    assert "Livro de Registro de Protestos" in html
    assert "Livro A — Registro de Nascimento" in html


def test_a_tela_de_numeracao_diz_quais_series_esperam_o_oficial(s):
    html = s["c"].get("/nucleo/numeracao").get_data(as_text=True)
    assert "nenhuma coluna com o número de ordem" in html      # PT_PROTESTO
    assert "antes de lavrar o primeiro pagamento" in html      # PT_PAGAMENTO


def test_a_numeracao_e_de_admin_ou_gerente(cg_casa):
    sessao = _sessao(cg_casa, papel="USER")
    assert sessao["c"].get("/nucleo/numeracao").status_code == 403


def test_abrir_a_numeracao_nao_consome_numero(s):
    # GET QUE CONSOME CONTADOR fica preso no `busy_timeout` enquanto outro
    # balcao lavra, e devolve 500 na cara do escrevente. Tela de leitura le.
    s["c"].get("/nucleo/numeracao")
    assert _con(s).execute(
        "SELECT COUNT(*) FROM nu_numeracao").fetchone()[0] == 0


def test_informar_o_proximo_numero_grava_com_quem_informou_e_por_que(s):
    html = _post(s, "/nucleo/numeracao", origem="/nucleo/numeracao",
                 serie="PT_PROTESTO", proximo="318",
                 motivo="lido no Livro 9, fl. 187")
    assert "passa a ser 318" in html
    linha = _con(s).execute(
        "SELECT * FROM nu_numeracao WHERE serie='PT_PROTESTO'").fetchone()
    assert linha["proximo"] == 318
    assert linha["fixado_por"] == "MARIO EXEMPLO DOS SANTOS"
    assert linha["observacao"] == "lido no Livro 9, fl. 187"


def test_a_numeracao_recusa_numero_que_repetiria_ordem_ja_usada(s):
    # Quem recusa e `escrituracao.fixar_numeracao`, e nao a rota: numero igual
    # ou menor que o maior JA USADO repetiria numero de ordem — o defeito de
    # 18/08/2026, a matricula 4011 aberta depois de a 4013 existir.
    livro_id = _abrir(s, "RC_A")
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO nu_lugares(livro_id, serie, folha, verso, ordem,
                   rotulo, inicio, paginas, numero_ordem, tabela, referencia,
                   ocupado_em)
               VALUES (?,'RC_A',1,0,1,'1',1,1,19552,'rc_atos',1,?)""",
            (livro_id, AGORA))
    con.close()
    html = _post(s, "/nucleo/numeracao", origem="/nucleo/numeracao",
                 serie="RC_A", proximo="1000", motivo="tentativa de repetir")
    assert "repetiria número de ordem" in html
    assert "19552" in html                        # e diz qual é o maior


def test_serie_de_numeracao_diaria_nao_tem_contador_a_corrigir(s):
    html = _post(s, "/nucleo/numeracao", origem="/nucleo/numeracao",
                 serie="PT_PROTOCOLO", proximo="5", motivo="x")
    assert "numeração diária" in html


def test_o_menu_leva_a_numeracao_dos_livros(s):
    assert "Numeração dos livros" in \
        s["c"].get("/nucleo/livros").get_data(as_text=True)
