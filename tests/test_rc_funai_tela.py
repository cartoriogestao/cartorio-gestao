"""As telas da FUNAI e o painel das comunicações.

POR QUE SEPARADO
    `test_rc_funai.py` prova que o **módulo** lista, monta e registra. Este prova
    que a **tela chama o módulo** — décimo primeiro caso, neste projeto, em que
    essa diferença importa. Foi um teste de tela que achou a `normalizar_nome`
    copiada, e outro que achou a chave estrangeira do usucapião.
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
AGORA = "2026-08-20T09:00"


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
    db.set_settings({"serventia_cns": "000000",
                     "serventia_nome": "SERVENTIA DE CIDADE EXEMPLO"})
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
    """O HTML sem as quebras de linha do Jinja.

    JÁ ERRAMOS ISSO QUATRO VEZES: o modelo quebra a frase no meio e o `in` falha
    numa comparação que está certa.
    """
    return " ".join((t or "").split())


def _nascimento(casa, *, nome="CAMILO KRIKATI", cor="Indigena", numero=1,
                data_ato="2026-08-05"):
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em, cor_raca)
               VALUES ('RC_A','NASCIMENTO',?,?,?,?,'ATIVO','SISTEMA',?,?)""",
            (numero, nome, data_ato, data_ato, AGORA, cor))
        return int(cur.lastrowid)


def _abrir(casa, url):
    r = casa["cliente"].get(url)
    assert r.status_code == 200, f"{url} não abriu ({r.status_code})"
    return _liso(r.get_data(as_text=True))


# ------------------------------------------------ o painel


def test_o_painel_abre_e_mostra_os_nove_destinos(casa):
    html = _abrir(casa, "/rcpn/comunicacoes-painel")
    assert "6 obrigações, 9 destinos" in html


def test_o_painel_poe_o_sirc_na_frente(casa):
    """A ordem é a do aperto: um dia útil vem antes de trimestral, e não na ordem
    em que os módulos foram escritos."""
    html = _abrir(casa, "/rcpn/comunicacoes-painel")
    # COMPARA-SE PELO TEXTO DA LINHA, e nao pela sigla: «IBGE» tambem aparece no
    # MENU, muito antes da tabela, e a primeira versao deste teste comparava a
    # posicao no menu achando que comparava a ordem do painel.
    assert html.index("SIRC / INSS") < html.index("o mapa trimestral")


def test_o_painel_marca_a_junta_militar_como_fora_do_codigo(casa):
    """Ela é da Lei 4.375/1964, e por isso quase se perdeu: quem lê só o Código
    de Normas não a encontra."""
    html = _abrir(casa, "/rcpn/comunicacoes-painel")
    assert "não está no Código de Normas" in html


def test_o_painel_diz_o_prazo_do_ibge_e_o_trimestre_que_ele_entrega(casa):
    """O dia 8 de outubro entrega julho, agosto e setembro. E o IBGE é o único
    destino com multa em dinheiro."""
    html = _abrir(casa, "/rcpn/comunicacoes-painel")
    assert "dia 8 de janeiro, abril, julho e outubro" in html
    assert "vence em" in html
    assert "trimestre de" in html
    assert "multa de 1 a 5 salários mínimos" in html


def test_o_painel_mostra_o_prazo_do_ibge_com_a_contagem(casa):
    """O buraco que esta tela declarava foi fechado em 30/08/2026: o sistema
    passou a guardar o que foi entregue ao IBGE. **Buraco fechado que continua
    declarado é o carimbo que mente outra vez.**"""
    html = _abrir(casa, "/rcpn/comunicacoes-painel")
    assert "não registra o que já foi enviado" not in html
    assert "vence em" in html


def test_o_painel_conta_o_que_espera(casa):
    _nascimento(casa)
    html = _abrir(casa, "/rcpn/comunicacoes-painel")
    assert "Comunicação à FUNAI" in html or "FUNAI" in html


def test_o_painel_leva_a_tela_de_cada_uma(casa):
    html = _abrir(casa, "/rcpn/comunicacoes-painel")
    assert "/rcpn/sirc" in html
    assert "/rcpn/funai" in html
    assert "/rcpn/crc" in html


def test_o_painel_esta_no_menu(casa):
    assert "O que comunicar hoje" in _abrir(casa, "/rcpn/comunicacoes-painel")


def test_o_painel_nao_grava_nada(casa):
    aid = _nascimento(casa)
    antes = dict(_con(casa).execute(
        "SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone())
    _abrir(casa, "/rcpn/comunicacoes-painel")
    depois = dict(_con(casa).execute(
        "SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone())
    assert antes == depois


# ------------------------------------------------ a lista da FUNAI


def test_a_tela_da_funai_diz_que_o_prazo_e_imediatamente(casa):
    html = _abrir(casa, "/rcpn/funai")
    assert "art. 253" in html
    assert "imediatamente" in html


def test_a_tela_diz_que_o_numero_vermelho_e_da_casa(casa):
    """A norma não dá número. Afirmar que ela dá seria pôr na tela uma regra que
    o Código não tem."""
    _nascimento(casa)
    html = _abrir(casa, "/rcpn/funai")
    assert "Esse número é da casa, e não da norma" in html


def test_a_tela_lista_o_indigena_e_nao_os_outros(casa):
    _nascimento(casa, nome="CAMILO KRIKATI", cor="Indigena", numero=1)
    _nascimento(casa, nome="MARIA DAS DORES", cor="Parda", numero=2)
    html = _abrir(casa, "/rcpn/funai")
    assert "CAMILO KRIKATI" in html
    assert "MARIA DAS DORES" not in html


def test_a_tela_vazia_diz_de_onde_vem_a_lista(casa):
    """Lista vazia que só mostra nada faz o operador achar que quebrou — e aqui
    ela pode estar vazia porque o campo não foi preenchido, o que é diferente de
    não ter havido nenhum."""
    html = _abrir(casa, "/rcpn/funai")
    assert "Nenhum nascimento esperando" in html
    assert "em branco em 178 dos 193" in html


# ------------------------------------------------ o ofício


def test_o_oficio_abre_com_o_artigo_e_o_nome(casa):
    aid = _nascimento(casa, nome="CECILIA VASCO DOURADO PEIXOTO")
    html = _abrir(casa, f"/rcpn/funai/{aid}")
    assert "CECILIA VASCO DOURADO PEIXOTO" in html
    assert "registro administrativo" in html
    assert "000000" in html


def test_o_oficio_pede_a_etnia_em_vez_de_deduzir(casa):
    """A ETNIA NÃO SE TIRA DO SOBRENOME — o § 1º permite, não obriga."""
    aid = _nascimento(casa, nome="ISAAC KRIKATI")
    html = _abrir(casa, f"/rcpn/funai/{aid}")
    assert "Falta preencher" in html
    assert "não deduzidas do sobrenome" in html
    assert "[COMPLETAR: a etnia" in html


def test_o_oficio_aceita_a_etnia_digitada(casa):
    aid = _nascimento(casa, nome="ISAAC KRIKATI")
    html = _abrir(casa, f"/rcpn/funai/{aid}?etnia=Krikati&aldeia=S%C3%A3o+Jos%C3%A9")
    assert "Falta preencher" not in html
    assert "Krikati" in html
    assert "São José" in html


def test_assento_que_nao_e_indigena_volta_avisando(casa):
    """Erro de regra não é HTTP 500."""
    aid = _nascimento(casa, nome="MARIA", cor="Parda")
    r = casa["cliente"].get(f"/rcpn/funai/{aid}", follow_redirects=True)
    assert "corrija a cor/raça" in _liso(r.get_data(as_text=True))


# ------------------------------------------------ a saída do aviso


def test_registrar_que_saiu_tira_da_lista(casa):
    """AVISO SEM SAÍDA É AVISO QUE FICA PARA SEMPRE."""
    aid = _nascimento(casa, nome="CAMILO KRIKATI")
    html = casa["cliente"].get(f"/rcpn/funai/{aid}").get_data(as_text=True)
    r = casa["cliente"].post(
        f"/rcpn/funai/{aid}",
        data={"csrf_token": _token(html), "acao": "enviei",
              "canal": "malote", "etnia": "Krikati", "aldeia": "São José"},
        follow_redirects=True)
    saida = _liso(r.get_data(as_text=True))
    assert "Nenhum nascimento esperando" in saida
    assert "comunicada por malote" in saida


def test_o_teor_que_ficou_gravado_e_o_que_a_tela_mostrou(casa):
    """O teor congela — remontá-lo depois faria o que se mostra numa correição
    discordar do que foi enviado."""
    aid = _nascimento(casa, nome="CAMILO KRIKATI")
    html = casa["cliente"].get(
        f"/rcpn/funai/{aid}?etnia=Krikati&aldeia=Aldeia+Nova"
    ).get_data(as_text=True)
    casa["cliente"].post(
        f"/rcpn/funai/{aid}",
        data={"csrf_token": _token(html), "acao": "enviei",
              "etnia": "Krikati", "aldeia": "Aldeia Nova"},
        follow_redirects=True)
    linha = dict(_con(casa).execute(
        "SELECT * FROM rc_funai WHERE assento_id=?", (aid,)).fetchone())
    assert "Krikati" in linha["teor"]
    assert "Aldeia Nova" in linha["teor"]
    assert linha["etnia"] == "Krikati"
    assert len(linha["hash_teor"]) == 64


def test_dispensar_sem_motivo_volta_avisando(casa):
    aid = _nascimento(casa, nome="CAMILO KRIKATI")
    html = casa["cliente"].get(f"/rcpn/funai/{aid}").get_data(as_text=True)
    r = casa["cliente"].post(
        f"/rcpn/funai/{aid}",
        data={"csrf_token": _token(html), "acao": "dispensar", "motivo": "não"},
        follow_redirects=True)
    assert "Escreva por que" in _liso(r.get_data(as_text=True))


def test_dispensar_com_motivo_guarda_o_que_se_escreveu(casa):
    aid = _nascimento(casa, nome="CAMILO KRIKATI")
    html = casa["cliente"].get(f"/rcpn/funai/{aid}").get_data(as_text=True)
    r = casa["cliente"].post(
        f"/rcpn/funai/{aid}",
        data={"csrf_token": _token(html), "acao": "dispensar",
              "motivo": "a cor foi digitada por engano, conferido no livro"},
        follow_redirects=True)
    saida = _liso(r.get_data(as_text=True))
    assert "digitada por engano" in saida
    assert "Nenhum nascimento esperando" in saida


def test_so_ver_o_oficio_nao_grava_nada(casa):
    """Grava-se quando o operador age, nunca ao mostrar — a regra do rastro das
    fraudes, que abre a ficha duas vezes e confere que nada foi gravado."""
    aid = _nascimento(casa, nome="CAMILO KRIKATI")
    _abrir(casa, f"/rcpn/funai/{aid}")
    _abrir(casa, f"/rcpn/funai/{aid}")
    assert _con(casa).execute(
        "SELECT COUNT(*) FROM rc_funai").fetchone()[0] == 0
