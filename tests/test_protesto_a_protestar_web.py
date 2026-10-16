"""
Testes das TELAS do «a protestar» — o passo da tarde do roteiro.

POR QUE ELES EXISTEM SEPARADOS DOS DE DOMINIO
    Buraco de tela nao aparece em teste de dominio, e este passo era um buraco
    de tela inteiro: `esperando_protesto` nao existia, e o titulo intimado
    ficava esperando alguem lembrar dele na lista geral.

O QUE ESTES TESTES GUARDAM, E QUE O TESTE DE DOMINIO NAO ALCANCA
      - LAVRA SO OS MARCADOS. Um botao que protestasse a lista inteira faria
        um clique valer por vinte atos que nao se desfazem;
      - NADA MARCADO NAO PROTESTA NADA — e avisa, em vez de calar;
      - UM QUE FALHA NAO DERRUBA OS OUTROS: cada titulo na sua transacao;
      - o LOTE NAO SELA E NAO COBRA, e a tela DIZ isso — vinte selos sao vinte
        chamadas ao aparelho, e segura-las poria a casa no `busy_timeout`;
      - a tela manda o `csrf_token` (dez formularios da casa nao mandavam, e o
        balcao levou «bad request error» em 27/08/2026);
      - a tela DIZ que o prazo nao e calculado por este sistema.
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
AGORA = "2026-08-31T15:00:00"


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
    # O PROTESTO ESTA DESLIGADO DE FABRICA desde 01/09/2026 — ordem do
    # oficial. Estes testes exercitam as TELAS dele, e por isso o LIGAM
    # aqui, de proposito e a vista: eles provam que o modulo funciona
    # quando ele voltar, que e o que «fica para um futuro» quer dizer.
    cg_casa['db'].set_settings({"modulo_protesto_ligado": "1"})
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


def intimado(s, *, numero="84713/1", nome="MARIA SANTOS",
             data="2026-08-20") -> int:
    """Um título intimado e sem movimentação, gravado direto no banco.

    Passar pela tela de apontar e intimar poria a montagem do cenário à mercê
    de outras duas telas — e o que se testa aqui é a do protesto.
    """
    con = _con(s)
    with con:
        cur = con.execute(
            """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
                   valor_centavos, saldo_centavos, situacao, protocolo,
                   origem, criado_em, motivo_protesto)
               VALUES ('DMI',?,'00200000991',148278,148278,'INTIMADO',
                       '2608310001','CRA',?,'1')""", (numero, AGORA))
        tid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO pt_devedores(titulo_id, nome, documento_tipo,
                   documento_numero) VALUES (?,?,'CPF','04785512388')""",
            (tid, nome))
        con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
                   origem, criado_em)
               VALUES (?,'APONTAMENTO','2026-08-18','{}','MANUAL',?)""",
            (tid, AGORA))
        con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
                   origem, criado_em)
               VALUES (?,'INTIMACAO',?,'{"modo": "EDITAL"}','MANUAL',?)""",
            (tid, data, AGORA))
    con.close()
    return tid


def lavrar(s, ids):
    tela = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    return s["c"].post("/protesto/a-protestar/lavrar",
                       data={"csrf_token": _token(tela),
                             "titulo_id": [str(x) for x in ids]},
                       follow_redirects=True)


def atos(s, titulo_id, tipo="PROTESTO") -> int:
    con = _con(s)
    n = con.execute("SELECT COUNT(*) FROM pt_atos WHERE titulo_id=? AND tipo=?",
                    (titulo_id, tipo)).fetchone()[0]
    con.close()
    return int(n)


# ------------------------------------------------------------- a lista


def test_a_tela_abre_e_mostra_o_intimado(s):
    intimado(s)
    html = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    assert "84713/1" in html
    assert "MARIA SANTOS" in html


def test_a_tela_diz_que_o_prazo_NAO_e_calculado(s):
    """Decisão do oficial de 24/08/2026, e ela precisa estar escrita onde a
    decisão é tomada — não só num comentário do código."""
    intimado(s)
    html = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    assert "não é calculado" in html
    assert "tríduo" in html


def test_a_tela_manda_o_csrf_token(s):
    """Dez formulários da casa não mandavam, e o balcão levou «bad request
    error» ao clicar. Teste de rota não pega: ele monta o POST com o token
    na mão."""
    intimado(s)
    html = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    assert 'name="csrf_token"' in html


def test_lista_vazia_nao_parece_defeito(s):
    """Lista vazia que só mostra nada faz o operador achar que quebrou."""
    html = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    assert "Nenhum título intimado" in html


def test_a_tela_esta_no_menu(s):
    html = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    assert "/protesto/a-protestar" in html


# ------------------------------------------------------------ o lavrar


def test_lavra_SO_o_marcado(s):
    """MARCADOS, E NÃO TODOS. Entre «listar» e «gerar» está a decisão, e
    protesto não se desfaz."""
    vai = intimado(s, numero="vai")
    fica = intimado(s, numero="fica")
    lavrar(s, [vai])
    assert atos(s, vai) == 1
    assert atos(s, fica) == 0


def test_nada_marcado_nao_protesta_nada_E_AVISA(s):
    """Calar faria o operador achar que protestou. A lista não protesta
    sozinha."""
    tid = intimado(s)
    resposta = lavrar(s, [])
    assert atos(s, tid) == 0
    assert "não protesta sozinha" in resposta.get_data(as_text=True)


def test_o_protestado_SAI_da_lista(s):
    """É a prova de que a consulta e o ato falam da mesma coisa: o protesto é
    ato posterior à intimação, e por isso o título deixa de esperar.

    E A AUSÊNCIA SE PROVA PELO LINK DA LINHA, e não pelo número solto: eu
    havia escrito `assert "84713/1" not in html` e o teste ficou vermelho com
    o conserto funcionando — **a janela da ajuda, que existe em toda tela,
    escreve esse mesmo número no exemplo do campo** («do título 84713/1,
    marquei pagamento e cliquei em lançar»). É a quinta vez neste projeto que
    procurar palavra solta num HTML inteiro dá resposta errada, e a segunda
    em que quem a dá é a janela da ajuda.
    """
    tid = intimado(s)
    antes = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    assert f'href="/protesto/{tid}"' in antes
    lavrar(s, [tid])
    depois = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    assert f'href="/protesto/{tid}"' not in depois


def test_um_que_falha_NAO_derruba_os_outros(s):
    """Cada título na sua transação. Protesto lavrado é protesto lavrado, e
    desfazer os bons por causa de um ruim seria pior.

    O ruim aqui é um `titulo_id` que não existe — o caso do formulário que
    volta com a lista velha depois de outro escrevente ter mexido.
    """
    bom = intimado(s, numero="bom")
    resposta = lavrar(s, [bom, 999999])
    assert atos(s, bom) == 1
    assert "999999" in resposta.get_data(as_text=True)


def test_o_lote_NAO_sela_e_NAO_cobra(s):
    """Vinte selos são vinte chamadas de rede de 20 s: segurá-las aqui poria
    todo o balcão no `busy_timeout`. Eles aparecem nas telas do outro lado, e
    a mensagem manda passar por elas."""
    tid = intimado(s)
    resposta = lavrar(s, [tid])
    con = _con(s)
    linha = con.execute(
        "SELECT selo, lancamento_id FROM pt_atos WHERE titulo_id=? AND "
        "tipo='PROTESTO'", (tid,)).fetchone()
    con.close()
    assert linha["selo"] is None
    assert linha["lancamento_id"] is None
    assert "sem selo" in resposta.get_data(as_text=True).lower()


def test_o_protesto_toma_numero_e_lugar_no_livro(s):
    """CADA UM É UM ATO PRÓPRIO. O que se junta é o trabalho de clicar, e não
    o ato: ele tem número de ordem e lugar no livro como qualquer outro."""
    tid = intimado(s)
    lavrar(s, [tid])
    con = _con(s)
    linha = con.execute(
        "SELECT numero_ordem, livro_id, folha FROM pt_atos WHERE titulo_id=? "
        "AND tipo='PROTESTO'", (tid,)).fetchone()
    con.close()
    assert linha["numero_ordem"]
    assert linha["livro_id"]
    assert linha["folha"]


def test_dois_marcados_saem_com_numeros_DIFERENTES(s):
    """O número de ordem é o do livro, e livro não repete número — é a trava
    mais importante do sistema, e o lote é justamente onde ela seria posta à
    prova."""
    a = intimado(s, numero="a")
    b = intimado(s, numero="b")
    lavrar(s, [a, b])
    con = _con(s)
    numeros = [r[0] for r in con.execute(
        "SELECT numero_ordem FROM pt_atos WHERE tipo='PROTESTO' "
        "ORDER BY numero_ordem")]
    con.close()
    assert len(numeros) == 2
    assert numeros[0] != numeros[1]


def test_o_lote_deixa_rastro_na_auditoria(s):
    """Vinte atos graves num clique precisam aparecer no rastro um a um, e
    marcados como de lote — numa correição a pergunta é como aquele protesto
    foi lavrado."""
    tid = intimado(s)
    lavrar(s, [tid])
    con = _con(s)
    linhas = con.execute(
        "SELECT * FROM audit_logs WHERE action='PROTESTO_LAVRADO'").fetchall()
    con.close()
    assert len(linhas) == 1
    assert "em_lote" in (linhas[0]["details"] or "")


def test_titulo_id_que_nao_e_numero_e_descartado(s):
    """O `getlist` traz o que vier no formulário. Texto vira `int()` que
    estoura, e estouro aqui seria HTTP 500 em cima de uma lista de protestos.
    """
    tid = intimado(s)
    tela = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    resposta = s["c"].post("/protesto/a-protestar/lavrar",
                           data={"csrf_token": _token(tela),
                                 "titulo_id": ["", "abc", str(tid)]},
                           follow_redirects=True)
    assert resposta.status_code == 200
    assert atos(s, tid) == 1


# ------------------------------------ a desistência vem antes do protesto


def test_a_tela_manda_conferir_as_DESISTENCIAS_antes(s):
    """O roteiro do oficial manda conferir desistência TRÊS VEZES POR DIA, e
    protestar título de que o credor desistiu é o erro que menos se desfaz
    nesta atribuição.

    O aviso mora NA TELA, e não só na ordem do menu: quem chega aqui por link,
    por favorito ou pela volta de um lote não passa pelo menu.
    """
    intimado(s)
    html = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    assert "desistências do dia" in html
    assert 'href="/protesto/desistencias"' in html


def test_no_MENU_a_desistencia_vem_antes_do_a_protestar(s):
    """A ORDEM DENTRO DO MÓDULO É A DO DIA, e a do roteiro dele é esta nos
    DOIS turnos: «MEIO DIA: 2) verificação de desistências» e «TARDE: 1)
    verificar desistências; 2) gerar protesto».

    Estava invertida quando a tela nasceu — item novo entra onde é cômodo
    escrever, e não onde é cômodo achar.
    """
    html = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    menu = html[:html.index("</nav>")] if "</nav>" in html else html
    desistencias = menu.index('/protesto/desistencias')
    a_protestar = menu.index('/protesto/a-protestar')
    assert desistencias < a_protestar


# ---------------------------------- a sustação judicial, na tela


def sustar(s, titulo_id, *, juizo="1ª Vara Cível de Cidade Exemplo/MA",
           processo="0800123-45.2026.8.10.0100", recebido_em=""):
    tela = s["c"].get(f"/protesto/{titulo_id}").get_data(as_text=True)
    return s["c"].post(f"/protesto/{titulo_id}/lancar",
                       data={"csrf_token": _token(tela), "ato": "SUSTACAO",
                             "juizo": juizo, "processo": processo,
                             "recebido_em": recebido_em},
                       follow_redirects=True)


def test_o_SUSTADO_sai_da_lista_e_o_lote_nao_o_protesta(s):
    """Lei 9.492/1997, art. 17: ordem judicial que impede o protesto.

    Este é o teste que mais importa desta tela. Ela lavra **em lote** — e sem
    a sustação registrada ofereceria, no meio dos outros, um título que o juiz
    mandou parar. Um clique, e o ato está lavrado.

    E ele manda o `titulo_id` **direto para a rota**, sem passar pela lista:
    a tela esconde por educação, o domínio recusa por dever, e é o domínio que
    este teste põe à prova.
    """
    tid = intimado(s)
    sustar(s, tid)
    html = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    assert f'href="/protesto/{tid}"' not in html.split("Sustados por ordem")[0]
    resposta = lavrar(s, [tid])
    assert atos(s, tid) == 0
    assert "SUSTADO por ordem judicial" in resposta.get_data(as_text=True)


def test_a_tela_MOSTRA_os_sustados_porque_eles_somem_de_todo_o_resto(s):
    """Título à disposição do Juízo que ninguém enxerga é título esquecido —
    `pt_titulos` continua dizendo INTIMADO, e a fila não o traz."""
    tid = intimado(s)
    sustar(s, tid)
    html = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    assert "Sustados por ordem judicial" in html
    assert "0800123-45.2026.8.10.0100" in html


def test_o_REVOGADO_aparece_no_ALTO_com_o_prazo_de_um_dia_util(s):
    """Art. 17, § 2º. É o único título do Protesto com prazo de um dia útil
    escrito na lei — e ele vem **antes** da lista comum, porque embaixo
    ficaria abaixo de trinta linhas sem pressa."""
    tid = intimado(s)
    sustar(s, tid)
    tela = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    s["c"].post(f"/protesto/{tid}/lancar",
                data={"csrf_token": _token(tela), "ato": "REVOGACAO_SUSTACAO",
                      "recebido_em": "2026-08-31"}, follow_redirects=True)
    html = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    assert "primeiro dia útil" in html
    # e o bloco da revogação vem ANTES do da lista comum
    assert html.index("Sustação revogada") < html.index(
        "Títulos intimados e sem movimentação")


def test_a_ficha_DIZ_por_que_o_botao_do_protesto_sumiu(s):
    """Esconder o botão sem dizer por quê faria o escrevente achar que o
    sistema quebrou — e o motivo aqui é ordem judicial, que ele precisa saber
    para explicar ao cliente."""
    tid = intimado(s)
    sustar(s, tid)
    html = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "PROTESTO SUSTADO POR ORDEM JUDICIAL" in html
    assert "1ª Vara Cível de Cidade Exemplo/MA" in html
    assert "art. 17" in html


def test_sem_juizo_a_tela_recusa_registrar_a_ordem(s):
    tid = intimado(s)
    resposta = sustar(s, tid, juizo="")
    assert "juízo e o número do processo" in resposta.get_data(as_text=True)
    assert atos(s, tid, "SUSTACAO") == 0
