"""QUEM PRATICA O ATO NO RI — relato #65 do oficial, 15/09/2026.

    «tirar a opcao de escolher ato praticado por, atos novos sao sempre
     praticados pelo delegatario ou escrevente atual do sistema»

O QUE ISTO CONSERTA
    A ficha tinha um `<select name="delegatario_id">` com a lista de
    delegatarios, e quem estava no balcao escolhia — por ato — por quem o ato
    saia assinado. Medido na producao em 15/09/2026: dos 1.246 atos do RI,
    **1.242 estavam com `lavrado_nome` vazio** e 4 traziam o nome (os quatro
    de 18/08, pela BEATRIZ). A lista era a mesma em todo ato, e quem ja
    lavrou nao escolhe por quem assina: o nome sai embaixo da assinatura de
    quem responde pelo ato (Lei 8.935/94, arts. 20 e 21).

DE ONDE VEM AGORA
    Do cadastro de quem esta LOGADO (`users`), pela regra que o Tabelionato de
    Notas ja usa ha tempos (`lavrado_nome or usuario_nome()` e
    `lavrado_titulo or usuario_funcao()`). A funcao que a tabela Usuarios
    avisa quando falta e a mesma que sai no fecho.

E O QUE FICA
    `ri_delegatarios` FICA, e continua respondendo pelo TIMBRE
    (`titulo_registrador`, `titulo_substituta`) e pelos atos antigos. O que
    saiu foi o campo de ESCOLHA — e com ele o `delegatario_id` do formulario,
    que era o unico lugar onde alguem podia dizer que o ato era de outro.

O QUE ESTES TESTES PROTEGEM
    1. O nome e a funcao saem de quem esta logado, e ficam gravados NO ATO.
    2. O artigo («O»/«A») sai da funcao, e o fecho o usa.
    3. O ato congelado nao muda quando o cadastro de quem assinou muda.
    4. A tela nao oferece mais escolha, e nao ha para onde escolher.
    5. Os TRES caminhos que lavram ato gravam quem praticou — o ato comum, o
       cancelamento e o encerramento. Um deles sem o nome faria o fecho
       reaparecer vazio so num deles.
"""
from __future__ import annotations

import re
import sqlite3
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"

TEOR = ("AV-02/3.201 - RETIFICACAO DE AREA, conforme o titulo apresentado e a "
        "planta que instrui o pedido.")

FUNCAO_DO_OFICIAL = "Tabelião e Oficial de Registro"
FUNCAO_DA_BALCAO = "Escrevente Autorizada"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def _entrar(app, usuario: str):
    c = app.test_client()
    c.post("/login",
           data={"username": usuario, "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("balcao", "QUEM ATENDE", SENHA, "MANAGER")
    con = sqlite3.connect(cg_casa["banco"])
    with con:
        con.execute("UPDATE users SET funcao=? WHERE username='jean'",
                    (FUNCAO_DO_OFICIAL,))
        con.execute("UPDATE users SET funcao=? WHERE username='balcao'",
                    (FUNCAO_DA_BALCAO,))
    con.close()
    return {**cg_casa, "cliente": _entrar(cg_casa["app"], "jean")}


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _ficha(con, numero="3201"):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, criado_em)
           VALUES (?, '2R', '2R', 'ATIVO', 'ACERVO', '2026-09-15T08:00')""",
        (numero,))
    return int(cur.lastrowid)


def _lavrar(casa, mid, *, numero=2, teor=TEOR, cliente=None):
    """Lavra o ato pela TELA, como o balcao faz — e nao pelo dominio.

    `lavrar_sem_selo` vai marcado porque no ensaio nao ha selador: sem a
    marca, o ato entra na cadeia e sai cancelado (regra de 15/09), e estes
    testes, que sao de QUEM ASSINA, ficariam medindo o selo.
    """
    c = cliente or casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    return c.post(f"/registro-imoveis/{mid}/atos",
                  data={"csrf_token": _token(html), "tipo": "AV",
                        "numero": numero, "data_ato": "2026-09-15",
                        "teor": teor, "_removido_lavrar_sem_selo": "0",
                        # A NATUREZA E EXIGIDA ANTES DE O ATO NASCER —
                        # 15/09/2026, pedido do oficial: «se deu problema
                        # no selo deve voltar e permitir retificar o erro».
                        # Sem ela a rota recusa, e o ato nao chega a
                        # existir; estes testes lavram o minimo e por isso
                        # ficaram vermelhos naquela data.
                        "natureza_titulo": "Cancelamento de hipoteca"},
                  follow_redirects=True)


def _ato(con, mid, numero=2):
    linha = con.execute(
        "SELECT * FROM ri_atos WHERE matricula_id=? AND numero=?",
        (mid, numero)).fetchone()
    return dict(linha) if linha else None


# ------------------------------------------------------- de quem esta logado


def test_o_nome_e_a_funcao_saem_do_cadastro_de_quem_esta_logado(casa):
    con = _con(casa)
    with con:
        mid = _ficha(con)
    con.close()

    _lavrar(casa, mid)

    con = _con(casa)
    ato = _ato(con, mid)
    con.close()
    assert ato, "o ato nao foi lavrado"
    assert ato["lavrado_nome"] == "MARIO EXEMPLO DOS SANTOS", (
        "quem assina e quem esta logado — e nao uma escolha da tela")
    assert ato["lavrado_titulo"] == FUNCAO_DO_OFICIAL
    assert ato["lavrado_tratamento"] == "O", (
        "«Tabelião e Oficial de Registro» pede artigo O")


def test_quem_atende_lavra_e_sai_com_o_proprio_nome(casa):
    """A guarda e da tela, e nao do papel: o balcao continua lavrando ato."""
    balcao = _entrar(casa["app"], "balcao")
    con = _con(casa)
    with con:
        mid = _ficha(con, numero="3202")
    con.close()

    _lavrar(casa, mid, cliente=balcao)

    con = _con(casa)
    ato = _ato(con, mid)
    con.close()
    assert ato["lavrado_nome"] == "QUEM ATENDE"
    assert ato["lavrado_titulo"] == FUNCAO_DA_BALCAO
    assert ato["lavrado_tratamento"] == "A", (
        "«Escrevente Autorizada» pede artigo A — e o fecho imprime «A ...»")


def test_o_nome_assinado_vai_no_papel_da_ficha(casa):
    """O fecho sai no PAPEL, e não na tela da ficha.

    MEDIDO AO ESCREVER ESTE TESTE: `ri_ficha.html` não imprime o fecho — o teor
    que ela mostra é o do livro. Quem o imprime é o `.odt` da ficha (onde ele
    entra no fim do teor) e a certidão. O teste anterior deste arquivo afirmava
    «Dou fé» na tela e **reprovava**: a regra estava certa, o lugar da prova
    é que não. Teste que procura a prova onde ela nunca esteve acusa quem está
    certo.
    """
    con = _con(casa)
    with con:
        mid = _ficha(con, numero="3203")
    con.close()
    _lavrar(casa, mid)

    r = casa["cliente"].get(f"/registro-imoveis/{mid}/ficha.odt?formato=odt")
    assert r.status_code == 200 and r.data[:2] == b"PK", "o .odt da ficha tem de sair"
    with zipfile.ZipFile(BytesIO(r.data)) as z:
        papel = z.read("content.xml").decode("utf-8")
    assert "Dou fé" in papel, "o fecho do ato não chegou ao papel"
    assert "MARIO EXEMPLO DOS SANTOS" in papel, (
        "o fecho do ato tem de trazer o nome de quem o praticou")
    assert FUNCAO_DO_OFICIAL in papel


# ----------------------------------------------------------------- congelado


def test_o_ato_nao_muda_quando_o_cadastro_de_quem_assinou_muda(casa):
    """O ato diz o que dizia no dia: se a funcao de quem assinou mudar amanha,
    este ato continua mostrando a de hoje — ele nao se remonta."""
    con = _con(casa)
    with con:
        mid = _ficha(con, numero="3204")
    con.close()
    _lavrar(casa, mid)

    con = _con(casa)
    with con:
        con.execute("UPDATE users SET funcao='Substituta' WHERE username='jean'")
    ato = _ato(con, mid)
    con.close()
    assert ato["lavrado_titulo"] == FUNCAO_DO_OFICIAL
    assert ato["lavrado_tratamento"] == "O", (
        "o artigo tambem congela: o ato nao se remonta depois de assinado")


# -------------------------------------------------- a tela nao oferece escolha


def test_a_ficha_nao_oferece_escolher_quem_pratica(casa):
    con = _con(casa)
    with con:
        mid = _ficha(con, numero="3205")
    con.close()
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert 'name="delegatario_id"' not in html, (
        "relato #65: o campo de escolha saiu")
    assert "Quem pratica este ato" in html, (
        "saiu o campo, mas a tela tem de DIZER por quem o ato vai sair")
    assert "MARIO EXEMPLO DOS SANTOS" in html


def test_nao_ha_campo_de_escolha_em_tela_nenhuma():
    """Varredura: o campo saiu da ficha e nao pode reaparecer noutra tela."""
    telas = list((RAIZ / "templates").glob("*.html"))
    assert len(telas) > 50, "o varredor perdeu a pasta das telas"
    culpadas = [t.name for t in telas
                if 'name="delegatario_id"' in t.read_text(encoding="utf-8")]
    assert not culpadas, (
        f"estas telas ainda oferecem escolher quem pratica o ato: {culpadas}")


def test_o_modulo_nao_le_mais_quem_pratica_do_formulario():
    """Nao basta tirar o campo: se a rota continuar LENDO `delegatario_id`,
    basta um formulario forjado para o ato sair em nome de outro."""
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    assert "delegatario_id" not in codigo, (
        "`ri_web.py` ainda le/devolve `delegatario_id`; o relato #65 manda "
        "que os atos novos sejam sempre de quem esta no sistema")


# ------------------------------------------------- os tres caminhos que lavram


def test_todo_caminho_que_lavra_ato_grava_quem_praticou():
    """Hoje sao tres: o ato comum, o cancelamento e o encerramento.

    Um deles sem as colunas faria o fecho sair vazio — e so naquele caminho,
    que e como um defeito desses passa despercebido.
    """
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    inserts = re.findall(r"INSERT INTO ri_atos\s*\((.*?)\)\s*VALUES",
                         codigo, re.S)
    assert len(inserts) == 3, (
        f"{len(inserts)} caminhos inserem em `ri_atos`; se um novo nasceu, "
        f"ele precisa gravar quem praticou o ato")
    for colunas in inserts:
        assert "lavrado_nome" in colunas and "lavrado_titulo" in colunas, (
            "todo caminho que lavra ato tem de congelar quem o praticou")


def test_o_cancelamento_grava_quem_praticou(casa):
    con = _con(casa)
    with con:
        mid = _ficha(con, numero="3206")
    con.close()
    _lavrar(casa, mid)
    con = _con(casa)
    ato_id = _ato(con, mid)["id"]
    con.close()

    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    casa["cliente"].post(
        f"/registro-imoveis/atos/{ato_id}/cancelar",
        data={"csrf_token": _token(html), "motivo": "erro material na area",
              "data_ato": "2026-09-15"}, follow_redirects=True)

    con = _con(casa)
    cancelamento = _ato(con, mid, numero=3)
    original = _ato(con, mid)
    con.close()
    assert cancelamento and "CANCELAMENTO DO ATO" in cancelamento["teor"]
    assert cancelamento["lavrado_nome"] == "MARIO EXEMPLO DOS SANTOS", (
        "a averbacao de cancelamento tambem e ato — e tambem se assina")
    assert cancelamento["lavrado_tratamento"] == "O"
    # E O CANCELAMENTO TEM DE TERMINAR: era aqui que a rota morria com
    # `NameError`, a transacao voltava atras e a ficha continuava dizendo que o
    # ato valia. Sem esta linha o teste provaria so metade do caminho.
    assert original["cancelado"] == 1, "o ato cancelado tem de ficar marcado"


def test_o_encerramento_pelo_botao_grava_quem_praticou(casa):
    con = _con(casa)
    with con:
        mid = _ficha(con, numero="3207")
    con.close()
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    casa["cliente"].post(f"/registro-imoveis/{mid}/encerrar",
                         data={"csrf_token": _token(html),
                               "motivo": "unificacao das fichas",
                               "destino": "4019"}, follow_redirects=True)

    con = _con(casa)
    ato = _ato(con, mid, numero=1)
    con.close()
    assert ato and "ENCERRAMENTO DESTA MATR" in ato["teor"]
    assert ato["lavrado_nome"] == "MARIO EXEMPLO DOS SANTOS"
    assert ato["lavrado_titulo"] == FUNCAO_DO_OFICIAL
