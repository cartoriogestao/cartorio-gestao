"""A CERTIDÃO ELETRÔNICA DE UM REGISTRO DESTA CASA — sem pedido da Central.

    «precisamos colocar o botao de emissao do json (ver documentacao, acho que
     selado já) para emitir certidao pela CRC»    — o oficial, 10/09/2026

O QUE SE MEDIU ANTES DE CONSTRUIR
    `rc_pedidos.emitir` recebe `pedido_id: int | None = None` **desde que
    nasceu**, e `rc_certidoes_eletronicas.pedido_id` aceita NULO: a certidão
    eletrônica de um registro desta casa sempre foi possível. O que havia era
    **um botão só, na ficha de um pedido que veio da Central**
    (`templates/rcpn_pedido.html`) — de modo que emitir pela CRC dependia de
    alguém do outro lado pedir primeiro, e quem chega ao balcão pedindo
    certidão eletrônica não passa por aquela fila.

    É o defeito que mais se repetiu neste projeto **pelo lado do rascunho de
    tela**: não «função sem chamador», mas peça que UMA tela chama e as outras
    não — e nenhum varredor o vê, porque a função tem chamador.

O «ACHO QUE SELADO JÁ» DELE
    O sistema **não compra** selo por aqui (esta casa nunca selou certidão
    eletrônica). O que ele faz é trazer preenchido o selo que o **ato de
    registro** já tem, para não obrigar a digitar um número que o banco
    conhece — editável, e vazio quando não há.
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

import rc_pedidos as PED

SENHA = "Senha#12345"
SELO_DO_REGISTRO = "BRCXXX00000037Z7UYDS1EOW8G07"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["c"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _assento(casa, *, com_selo: bool = True, com_matricula: bool = True) -> int:
    con = _con(casa)
    matricula = "000000015520261000421660001234 45" if com_matricula else ""
    with con:
        con.execute(
            """INSERT INTO rc_assentos(serie, especie, numero, matricula, nome,
                   data_ato, data_fato, dados_json, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',19552,?,'MARIA EDUARDA SANTANA',
                       '2026-09-01','2026-08-28','{}','ATIVO','SISTEMA',
                       '2026-09-10T09:00:00')""", (matricula,))
        aid = con.execute("SELECT id FROM rc_assentos").fetchone()["id"]
        con.execute(
            """INSERT INTO rc_atos(assento_id, tipo, folha, numero_ordem,
                   rotulo, data_ato, selo, origem, criado_em)
               VALUES (?,'REGISTRO',166,19552,'166','2026-09-01',?,'SISTEMA',
                       '2026-09-10T09:00:00')""",
            (aid, SELO_DO_REGISTRO if com_selo else None))
        for papel, quem, ordem in (("PAI", "MANOEL SANTANA", 1),
                                   ("MAE", "JOSEFA SANTANA", 2)):
            con.execute(
                """INSERT INTO rc_pessoas(assento_id, papel, nome, ordem,
                       origem, criado_em)
                   VALUES (?,?,?,?,'SISTEMA','2026-09-10T09:00:00')""",
                (aid, papel, quem, ordem))
    con.close()
    return aid


def _tela(casa, assento_id: int) -> str:
    r = casa["c"].get(f"/rcpn/{assento_id}/certidao-eletronica")
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


# ----------------------------------------------------------- o botão


def test_a_ficha_do_assento_oferece_a_certidao_eletronica(casa):
    """**O BOTÃO VEM PARA ONDE O ESCREVENTE ESTÁ.** Sem esta linha o caminho
    existe e ninguém o alcança — que era o relato."""
    aid = _assento(casa)
    html = casa["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
    assert f"/rcpn/{aid}/certidao-eletronica" in html
    assert "Certidão eletrônica na CRC" in html


def test_a_ficha_diz_que_e_outra_coisa_que_o_papel(casa):
    """Dois botões de «certidão» na mesma tela, sem uma palavra que os separe,
    é o relato #12 («duas portas para a mesma sala») ao contrário: portas
    diferentes que parecem a mesma."""
    aid = _assento(casa)
    html = casa["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
    assert "não gasta folha" in html


# ------------------------------------------------------ a conferência


def test_a_tela_confere_sem_mandar_nada(casa):
    """**CONFERIR E CRIAR SÃO DOIS BOTÕES.** Abrir a conferência não pode
    criar certidão nenhuma na Central."""
    aid = _assento(casa)
    _tela(casa, aid)
    _tela(casa, aid)
    con = _con(casa)
    assert con.execute(
        "SELECT COUNT(*) c FROM rc_certidoes_eletronicas").fetchone()["c"] == 0
    con.close()


def test_o_selo_do_registro_vem_preenchido(casa):
    """O «acho que selado já» dele: o número que o banco conhece não se
    digita de novo."""
    aid = _assento(casa)
    assert SELO_DO_REGISTRO in _tela(casa, aid)


def test_registro_sem_selo_deixa_o_campo_vazio_em_vez_de_inventar(casa):
    """Campo vazio não afirma nada; selo inventado afirma — e o sistema
    **não compra** selo por este caminho."""
    aid = _assento(casa, com_selo=False)
    html = _tela(casa, aid)
    assert SELO_DO_REGISTRO not in html
    assert 'name="selo" value=""' in html


def test_sem_matricula_a_tela_impede_e_diz_por_que(casa):
    """A matrícula de 32 dígitos é por onde a Central identifica o registro.
    A recusa é aqui, e não na hora do envio."""
    aid = _assento(casa, com_matricula=False)
    html = _tela(casa, aid)
    assert "matrícula" in html.lower()
    assert "Criar na Central" not in html, (
        "a tela ofereceu criar com impedimento na frente")


def test_sem_credencial_a_tela_diz_onde_o_token_mora(casa):
    """**FILA VAZIA / TELA MUDA DIZ POR QUÊ** — a lição da tela de
    assinaturas, que custou três respostas. Sem token nada sobe, e o operador
    tem de saber que é isso, e não que o sistema quebrou."""
    aid = _assento(casa)
    html = _tela(casa, aid)
    assert "IdRC" in html
    assert "Criar na Central" not in html


def test_assento_que_nao_existe_avisa_em_vez_de_estourar(casa):
    """Erro de regra não é HTTP 500."""
    r = casa["c"].get("/rcpn/98765/certidao-eletronica", follow_redirects=True)
    assert r.status_code == 200
    assert "não existe" in r.get_data(as_text=True)


# --------------------------------------------------------- o envio


def test_criar_sem_credencial_volta_com_a_frase_e_nao_grava(casa):
    """A rota que grava tem de recusar sozinha — **a tela só oferece; quem
    recusa é o domínio** —, e a recusa volta como aviso, não como erro."""
    aid = _assento(casa)
    html = _tela(casa, aid)
    r = casa["c"].post(
        f"/rcpn/{aid}/certidao-eletronica/criar",
        data={"csrf_token": _token(html), "tipo_registro": "nascimento"},
        follow_redirects=True)
    assert r.status_code == 200
    con = _con(casa)
    assert con.execute(
        "SELECT COUNT(*) c FROM rc_certidoes_eletronicas").fetchone()["c"] == 0
    con.close()


def test_o_dominio_aceita_emitir_SEM_pedido_da_central():
    """**A MEDIÇÃO QUE DECIDIU NÃO CONSTRUIR DOMÍNIO NOVO.**

    `emitir` já nasceu com `pedido_id` opcional, e é isso que torna a tela
    nova uma TELA, e não um segundo caminho de envio. Um segundo caminho
    divergiria do primeiro no primeiro conserto, e o que a Central recebesse
    deixaria de ser o que a tela conferiu.
    """
    import inspect
    p = inspect.signature(PED.emitir).parameters["pedido_id"]
    assert p.default is None, (
        "se `pedido_id` virar obrigatório, a certidão eletrônica da casa "
        "deixa de existir — e a tela nova passa a mentir")


def test_a_certidao_da_casa_se_distingue_da_que_veio_de_pedido(casa):
    """`pedido_id` NULO quer dizer «esta casa emitiu», e a tela mostra isso:
    sem essa coluna, quem confere depois não sabe se a certidão saiu de um
    pedido da Central ou do balcão."""
    con = _con(casa)
    colunas = {r["name"] for r in
               con.execute("PRAGMA table_info(rc_certidoes_eletronicas)")}
    con.close()
    assert "pedido_id" in colunas
