"""As telas da retificação, restauração e suprimento do Registro Civil.

POR QUE SEPARADO
    `test_retificacao_rcpn.py` prova que o **módulo** recusa decidir sem a CRC e
    abre as duas comunicações do art. 353. Este prova que a **tela chama o
    módulo** — décimo segundo caso, neste projeto, em que essa diferença
    importou. Foi um teste de tela que achou a chave estrangeira do usucapião,
    a `normalizar_nome` copiada, e os dois `request.form` desta semana.
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

import retificacao_rcpn as RR                                    # noqa: E402

SENHA = "Senha#12345"
FUNDAMENTO = ("o erro é evidente na comparação com a certidão apresentada e "
              "não exige indagação, na forma do art. 352, I")


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _liso(t: str) -> str:
    return " ".join((t or "").split())


def _abrir(casa, url):
    r = casa["cliente"].get(url)
    assert r.status_code == 200, f"{url} não abriu ({r.status_code})"
    return _liso(r.get_data(as_text=True))


def _post(casa, url, campos):
    html = casa["cliente"].get(url).get_data(as_text=True)
    dados = {"csrf_token": _token(html)}
    dados.update(campos)
    return casa["cliente"].post(url, data=dados, follow_redirects=True)


def _novo(casa, **extra):
    campos = {"instituto": "RETIFICACAO", "forma": "ESCRITO",
              "requerente_nome": "MARIA DAS DORES",
              "o_que_se_pede": "corrigir o nome da genitora",
              "assento_descricao": "Livro A-24, fl. 166, termo 19552"}
    campos.update(extra)
    r = _post(casa, "/rcpn/retificacoes/nova", campos)
    return r, _liso(r.get_data(as_text=True))


def _id_do_unico(casa):
    return int(_con(casa).execute(
        "SELECT id FROM rr_processos ORDER BY id DESC LIMIT 1").fetchone()[0])


# ------------------------------------------------ a lista explica


def test_a_lista_separa_os_tres_institutos(casa):
    """Juntá-los num «corrigir assento» faria escolher o caminho errado."""
    html = _abrir(casa, "/rcpn/retificacoes")
    for palavra in ("Retificação", "Restauração", "Suprimento"):
        assert palavra in html


def test_a_lista_diz_que_a_crc_e_condicao_de_validade(casa):
    html = _abrir(casa, "/rcpn/retificacoes")
    assert "art. 348, § 2º" in html
    assert "condição de validade" in html
    assert "não é aviso, é recusa" in html


def test_a_lista_avisa_das_duas_recusas_erradas_do_balcao(casa):
    """O pedido pode ser verbal, e mandado de outra comarca não precisa de
    «cumpra-se» daqui."""
    html = _abrir(casa, "/rcpn/retificacoes")
    assert "art. 348, § 1º, III" in html
    assert "cumpra-se" in html
    assert "procurador" in html


def test_a_lista_diz_de_quando_o_prazo_conta(casa):
    html = _abrir(casa, "/rcpn/retificacoes")
    assert "10 dias úteis" in html
    assert "devidamente instruído" in html


# ------------------------------------------------ abrir


def test_abrir_um_processo(casa):
    _novo(casa)
    html = _abrir(casa, f"/rcpn/retificacoes/{_id_do_unico(casa)}")
    assert "MARIA DAS DORES" in html
    assert "corrigir o nome da genitora" in html
    assert "Ainda não instruído" in html


def test_o_verbal_sem_termo_volta_avisando(casa):
    """Erro de regra não é HTTP 500."""
    _, saida = _novo(casa, forma="VERBAL")
    assert "reduzido a termo" in saida


def test_o_verbal_com_termo_mostra_o_termo(casa):
    _novo(casa, forma="VERBAL",
          termo_verbal="Compareceu MARIA e declarou que o nome está grafado "
                       "MARIA e o certo é MARIA JOSÉ.")
    html = _abrir(casa, f"/rcpn/retificacoes/{_id_do_unico(casa)}")
    assert "Termo do pedido verbal" in html
    assert "o certo é MARIA JOSÉ" in html


def test_o_suprimento_entra_sem_assento(casa):
    _novo(casa, instituto="SUPRIMENTO", assento_descricao="")
    assert _con(casa).execute(
        "SELECT COUNT(*) FROM rr_processos").fetchone()[0] == 1


def test_a_retificacao_sem_assento_volta_avisando(casa):
    _, saida = _novo(casa, assento_descricao="")
    assert "de que assento" in saida


def test_a_recusa_volta_com_o_que_foi_digitado(casa):
    """A recusa redirecionava para a tela em branco (31/10/2026)."""
    _, saida = _novo(casa, forma="VERBAL", instituto="SUPRIMENTO", requerente_documento="00000000191",
                     assinado_por="procurador", assento_descricao="Livro A-24, fl. 1")
    assert "reduzido a termo" in saida
    for trecho in ('value="SUPRIMENTO" checked', 'value="VERBAL" checked', 'value="MARIA DAS DORES"', 'value="00000000191"',
                   ">corrigir o nome da genitora</textarea>", 'value="Livro A-24, fl. 1"'):
        assert trecho in saida, trecho
    assert 'value="RETIFICACAO" checked' not in saida
    assert _con(casa).execute("SELECT COUNT(*) FROM rr_processos").fetchone()[0] == 0


# ------------------------------------------------ o rito, na tela


def test_a_tela_diz_o_que_fazer_agora(casa):
    """Num rito de dias, «e agora?» é a pergunta que mais se repete."""
    _novo(casa)
    html = _abrir(casa, f"/rcpn/retificacoes/{_id_do_unico(casa)}")
    assert "O que fazer agora" in html
    assert "instruído" in html
    assert "CRC" in html


def test_instruir_pela_tela_faz_o_prazo_correr(casa):
    _novo(casa)
    pid = _id_do_unico(casa)
    r = _post(casa, f"/rcpn/retificacoes/{pid}", {"acao": "instruir"})
    html = _liso(r.get_data(as_text=True))
    assert "Prazo até" in html
    assert "Ainda não instruído" not in html


def test_a_tela_recusa_decidir_sem_a_crc(casa):
    """**É CONDIÇÃO DE VALIDADE DA DECISÃO**, e a tela avisa antes do botão e o
    módulo recusa depois dele."""
    _novo(casa)
    pid = _id_do_unico(casa)
    _post(casa, f"/rcpn/retificacoes/{pid}", {"acao": "instruir"})
    html = _abrir(casa, f"/rcpn/retificacoes/{pid}")
    assert "Ainda não dá para decidir" in html
    r = _post(casa, f"/rcpn/retificacoes/{pid}",
              {"acao": "decidir", "decisao": "DEFERIDO",
               "fundamento": FUNDAMENTO})
    assert "consulta obrigatória à CRC" in _liso(r.get_data(as_text=True))


def test_registrar_a_consulta_pela_tela(casa):
    _novo(casa)
    pid = _id_do_unico(casa)
    r = _post(casa, f"/rcpn/retificacoes/{pid}",
              {"acao": "crc", "o_que_se_procurou": "nome e filiação",
               "resultado": "nenhuma duplicidade", "protocolo": "CRC/9988"})
    html = _liso(r.get_data(as_text=True))
    assert "nenhuma duplicidade" in html
    assert "CRC/9988" in html


def test_a_duplicidade_aparece_com_o_art_365(casa):
    """O art. 365 manda comunicar imediatamente ao juiz corregedor, com bloqueio
    cautelar do registro mais recente."""
    _novo(casa)
    pid = _id_do_unico(casa)
    r = _post(casa, f"/rcpn/retificacoes/{pid}",
              {"acao": "crc", "o_que_se_procurou": "nome",
               "resultado": "há assento da mesma pessoa em Imperatriz",
               "achou_duplicidade": "on"})
    html = _liso(r.get_data(as_text=True))
    assert "duplicidade" in html
    assert "art. 365" in html


def test_a_tela_diz_que_nao_consulta_a_crc(casa):
    """Um botão que dissesse «consultado» sem consultar responderia, e
    responderia errado."""
    _novo(casa)
    html = _abrir(casa, f"/rcpn/retificacoes/{_id_do_unico(casa)}")
    assert "não consulta a CRC" in html


# ------------------------------------------------ decidir, pela tela


def _ate_a_decisao(casa):
    _novo(casa)
    pid = _id_do_unico(casa)
    _post(casa, f"/rcpn/retificacoes/{pid}", {"acao": "instruir"})
    _post(casa, f"/rcpn/retificacoes/{pid}",
          {"acao": "crc", "o_que_se_procurou": "nome e filiação",
           "resultado": "nenhuma duplicidade"})
    return pid


def test_decidir_sem_fundamento_volta_avisando(casa):
    pid = _ate_a_decisao(casa)
    r = _post(casa, f"/rcpn/retificacoes/{pid}",
              {"acao": "decidir", "decisao": "DEFERIDO", "fundamento": "sim"})
    assert "fundamentada" in _liso(r.get_data(as_text=True))


def test_deferir_pela_tela(casa):
    pid = _ate_a_decisao(casa)
    r = _post(casa, f"/rcpn/retificacoes/{pid}",
              {"acao": "decidir", "decisao": "DEFERIDO",
               "fundamento": FUNDAMENTO})
    html = _liso(r.get_data(as_text=True))
    assert "Decisão: deferido" in html
    assert "Amarrar o ato" in html
    # O TEXTO VEM PARTIDO PELO `<strong>` do filtro `forte`, que transforma a
    # marcacao da norma em negrito de verdade em vez de mostrar asteriscos ao
    # operador. Por isso se conferem as duas metades, e nao a frase colada.
    assert "o livro <strong>corrente em uso na serventia</strong>" in html


def test_marcar_erro_da_serventia_sem_fundamento_volta_avisando(casa):
    """A marca gera gratuidade, duas comunicações e uma cobrança contra uma
    pessoa nomeada."""
    pid = _ate_a_decisao(casa)
    r = _post(casa, f"/rcpn/retificacoes/{pid}",
              {"acao": "decidir", "decisao": "DEFERIDO",
               "fundamento": FUNDAMENTO, "erro_da_serventia": "on",
               "erro_fundamento": "foi nosso"})
    assert "delegatário titular da época" in _liso(r.get_data(as_text=True))


def test_erro_da_serventia_abre_as_duas_comunicacoes_na_tela(casa):
    """Comunicar só a um deixaria o ressarcimento pela metade."""
    pid = _ate_a_decisao(casa)
    r = _post(casa, f"/rcpn/retificacoes/{pid}",
              {"acao": "decidir", "decisao": "DEFERIDO",
               "fundamento": FUNDAMENTO, "erro_da_serventia": "on",
               "erro_fundamento": "erro de digitação desta serventia no ato "
                                  "originário, conferido no livro de papel"})
    html = _liso(r.get_data(as_text=True))
    assert "Comunicações do art. 353" in html
    assert "FERC" in html and "FERJ" in html
    assert "São dois fundos, e não um" in html


def test_registrar_a_comunicacao_pela_tela(casa):
    pid = _ate_a_decisao(casa)
    _post(casa, f"/rcpn/retificacoes/{pid}",
          {"acao": "decidir", "decisao": "DEFERIDO", "fundamento": FUNDAMENTO,
           "erro_da_serventia": "on",
           "erro_fundamento": "erro de digitação desta serventia, conferido"})
    r = _post(casa, f"/rcpn/retificacoes/{pid}",
              {"acao": "comunicar", "fundo": "FERC", "teor": "Ofício ao FERC",
               "canal": "malote", "protocolo": "2026/77"})
    html = _liso(r.get_data(as_text=True))
    assert "enviada por malote" in html
    assert "2026/77" in html


# ------------------------------------------------ o ato


def test_amarrar_ato_que_nao_existe_volta_avisando(casa):
    """Sem a conferência batia na chave estrangeira e virava HTTP 500 no fim de
    um processo de dias — o defeito que o teste de tela do usucapião pegou."""
    pid = _ate_a_decisao(casa)
    _post(casa, f"/rcpn/retificacoes/{pid}",
          {"acao": "decidir", "decisao": "DEFERIDO", "fundamento": FUNDAMENTO})
    r = _post(casa, f"/rcpn/retificacoes/{pid}",
              {"acao": "ato", "ato_id": "9999"})
    assert "Esse ato não existe" in _liso(r.get_data(as_text=True))


def test_amarrar_o_ato_conclui_e_sai_da_lista(casa):
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',1,'MARIA','2026-01-15','2026-01-10',
                       'ATIVO','SISTEMA','2026-08-20T09:00')""")
        aid = int(cur.lastrowid)
        cur = con.execute(
            """INSERT INTO rc_atos (assento_id, tipo, data_ato, criado_em)
               VALUES (?,'RETIFICACAO','2026-08-25','2026-08-25T09:00')""",
            (aid,))
        ato_id = int(cur.lastrowid)
    pid = _ate_a_decisao(casa)
    _post(casa, f"/rcpn/retificacoes/{pid}",
          {"acao": "decidir", "decisao": "DEFERIDO", "fundamento": FUNDAMENTO})
    _post(casa, f"/rcpn/retificacoes/{pid}",
          {"acao": "ato", "ato_id": str(ato_id)})
    assert "MARIA DAS DORES" not in _abrir(casa, "/rcpn/retificacoes")


# ------------------------------------------------ o resto


def test_acao_desconhecida_volta_avisando(casa):
    _novo(casa)
    pid = _id_do_unico(casa)
    r = _post(casa, f"/rcpn/retificacoes/{pid}", {"acao": "apagar_tudo"})
    assert "Não conheço essa ação" in _liso(r.get_data(as_text=True))


def test_processo_que_nao_existe_volta_avisando(casa):
    r = casa["cliente"].get("/rcpn/retificacoes/9999", follow_redirects=True)
    assert "Esse processo não existe" in _liso(r.get_data(as_text=True))


def test_so_abrir_a_ficha_nao_grava_nada(casa):
    """Grava-se quando o operador age, nunca ao mostrar."""
    _novo(casa)
    pid = _id_do_unico(casa)
    antes = _con(casa).execute(
        "SELECT COUNT(*) FROM rr_andamento").fetchone()[0]
    _abrir(casa, f"/rcpn/retificacoes/{pid}")
    _abrir(casa, f"/rcpn/retificacoes/{pid}")
    assert _con(casa).execute(
        "SELECT COUNT(*) FROM rr_andamento").fetchone()[0] == antes


def test_esta_no_menu(casa):
    assert "Retificação e suprimento" in _abrir(casa, "/rcpn/retificacoes")
