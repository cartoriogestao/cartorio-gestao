"""RELATO #53 — a lista de atos da tabela enquanto se digita.

A frase do oficial, de 11/09/2026:

    «Itens da tabela ao procurar o ato poderiam ser listados automaticamente —
     para procurar um item para acrescentar da tabela no protocolo precisa
     clicar em pesquisar, daí recarrega a página e vai lá pra cima, fazendo
     perder tempo.»

SÃO DUAS QUEIXAS NUMA, e as duas se resolvem do mesmo jeito: o clique que
recarrega e a rolagem que se perde. Agora a lista sai enquanto se digita, e a
página não sai do lugar.

O QUE ESTES TESTES PROVAM, E A ORDEM IMPORTA:

1. a tela pede a lista sozinha — o campo, o endereço e o lugar onde desenhar;
2. **a lista do fragmento é a MESMA da página** — as duas saem da mesma macro.
   Duas montagens divergiriam no primeiro conserto, e o operador veria uma
   coisa ao digitar e outra ao clicar;
3. o caminho sem JavaScript continua de pé (o formulário GET, com o resultado
   desenhado na própria página);
4. a rota do fragmento **não grava nada** — é a mesma consulta de sempre;
5. a lista vazia diz que está vazia: numa busca que responde enquanto se digita,
   a lista que some pode ser «não achei» ou «o pedido falhou», e as duas pedem
   providências diferentes de quem está no balcão;
6. sem termo, não se devolve a tabela inteira (1.317 atos);
7. o limite é um só, para os dois caminhos.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

OPERADOR = "MARIO EXEMPLO DOS SANTOS"

SERVICOS = ((716, "16.24.4", "Certidões de inteiro teor, ônus e ações reais", "100,73"),
            (758, "13.18", "Por folha acrescida além da primeira, mais", "10,68"),
            (444, "13.17.2", "Reconhecimento de firma por semelhança", "11,96"))


# ------------------------------------------------------------- ferramentas

def _protocolo_e_tabela(banco) -> int:
    """Um protocolo e a tabela do tribunal, com o preço do dia."""
    import emolumentos as EMOL

    con = sqlite3.connect(str(banco))
    try:
        cur = con.execute(
            """INSERT INTO cx_protocolos (numero, data_abertura, interessado,
                                          situacao, criado_em)
               VALUES ('2026.09.901', ?, 'CONSTRUTORA ALFA LTDA', 'ABERTO', ?)""",
            (date.today().isoformat(), "2026-09-15T09:00:00"))
        protocolo_id = int(cur.lastrowid)
        con.execute(
            """INSERT INTO cx_vigencias (codigo, descricao, vigente, servicos,
                                         faixas, importado_em)
               VALUES (10022, 'Vigência de ensaio', 1, 0, 0, '2026-09-15')""")
        for codigo, codigo_tj, descricao, total in SERVICOS:
            con.execute(
                """INSERT INTO cx_servicos (codigo, codigo_tj, descricao,
                                            descricao_norm, ativo)
                   VALUES (?,?,?,?,1)""",
                (codigo, codigo_tj, descricao, EMOL._norm(descricao)))
            con.execute(
                """INSERT INTO cx_servico_valores (servico, vigencia,
                                                   emolumentos, total)
                   VALUES (?, 10022, ?, ?)""",
                (codigo, total, total))
        con.commit()
        return protocolo_id
    finally:
        con.close()


def _linhas_da_lista(html: str) -> int:
    """Quantos atos a lista tem — um campo `servico` por linha.

    O contador olha o campo `servico`, e não o botão «acrescentar»: a tela do
    protocolo tem outro botão com esse mesmo nome (o «acrescentar pela faixa»),
    e contar o botão contaria a tela em vez da lista.
    """
    return html.count('name="servico"')


# ------------------------------------------------------------------ a tela

def test_a_tela_pede_a_lista_sozinha(cg_casa_logada):
    """O campo, o endereço e o lugar de desenhar: sem os três, o script não
    sabe o que fazer."""
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo_e_tabela(banco)
    html = cg_casa_logada["c"].get(
        f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True)

    assert "data-busca-ato" in html, "o campo não se identifica para o script"
    assert f'/caixa/protocolos/{protocolo_id}/atos-da-tabela' in html, \
        "a tela não diz onde pedir a lista"
    assert 'data-atos-da-tabela' in html, "a tela não diz onde desenhar a lista"
    assert "busca_ato.js" in html, "o script da busca não é carregado"


def test_o_recado_so_aparece_com_o_script(cg_casa_logada):
    """«A lista aparece enquanto você digita» é promessa: quem está sem
    JavaScript precisa clicar, e a frase escondida não mente para ele."""
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo_e_tabela(banco)
    html = cg_casa_logada["c"].get(
        f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True)

    assert "data-busca-ato-recado" in html
    trecho = html[html.index("data-busca-ato-recado"):][:220]
    assert "hidden" in trecho, \
        "o recado nasce à vista: sem JavaScript ele promete o que não acontece"


# ------------------------------------------------- o fragmento e a mesma lista

def test_o_fragmento_e_a_mesma_lista_da_pagina(cg_casa_logada):
    """**O guarda que separa «a mesma lista» de «uma parecida».**

    A página, aberta com `?busca_ato=`, e o fragmento, pedido com `?busca=`,
    têm de trazer os MESMOS atos — os dois saem da macro `_atos_da_tabela.html`.
    """
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo_e_tabela(banco)
    c = cg_casa_logada["c"]

    pagina = c.get(f"/caixa/protocolos/{protocolo_id}?busca_ato=firma") \
        .get_data(as_text=True)
    fragmento = c.get(f"/caixa/protocolos/{protocolo_id}/atos-da-tabela"
                      "?busca=firma").get_data(as_text=True)

    assert _linhas_da_lista(pagina) == 1, "a página não achou a firma"
    assert _linhas_da_lista(fragmento) == 1, "o fragmento não achou a firma"
    assert "Reconhecimento de firma por semelhança" in pagina
    assert "Reconhecimento de firma por semelhança" in fragmento
    # O fragmento é só a lista: se viesse a página em volta, o script injetaria
    # um documento dentro do outro.
    assert "<html" not in fragmento.lower()
    assert "Meus dados" not in fragmento


def test_a_busca_por_codigo_do_tj_tambem_vale(cg_casa_logada):
    """É a outra metade do pedido: o balcão procura pelo código que está na
    tabela do tribunal."""
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo_e_tabela(banco)
    fragmento = cg_casa_logada["c"].get(
        f"/caixa/protocolos/{protocolo_id}/atos-da-tabela?busca=16.24.4"
    ).get_data(as_text=True)
    assert "Certidões de inteiro teor" in fragmento
    assert _linhas_da_lista(fragmento) == 1


def test_o_preco_vem_da_tabela_do_dia(cg_casa_logada):
    """O item entra pelo valor da tabela — quem procura precisa vê-lo antes de
    acrescentar."""
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo_e_tabela(banco)
    fragmento = cg_casa_logada["c"].get(
        f"/caixa/protocolos/{protocolo_id}/atos-da-tabela?busca=acrescida"
    ).get_data(as_text=True)
    assert "10,68" in fragmento, "a lista não mostra o total do dia"


def test_a_lista_vazia_diz_que_esta_vazia(cg_casa_logada):
    """Lista que some sem dizer nada, numa busca que responde enquanto se
    digita, se confunde com pedido que falhou."""
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo_e_tabela(banco)
    fragmento = cg_casa_logada["c"].get(
        f"/caixa/protocolos/{protocolo_id}/atos-da-tabela?busca=zzzzzz"
    ).get_data(as_text=True)
    assert "Nenhum ato" in fragmento
    assert _linhas_da_lista(fragmento) == 0


def test_sem_termo_nao_devolve_a_tabela_inteira(cg_casa_logada):
    """A tabela do tribunal tem 1.317 atos: abrir a tela não é pedir todos."""
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo_e_tabela(banco)
    fragmento = cg_casa_logada["c"].get(
        f"/caixa/protocolos/{protocolo_id}/atos-da-tabela"
    ).get_data(as_text=True)
    assert _linhas_da_lista(fragmento) == 0
    assert "Nenhum ato" not in fragmento, "sem busca não há o que lamentar"


# ------------------------------------------------------------- as duas guardas

def test_o_limite_e_um_so_para_os_dois_caminhos():
    """O número escrito duas vezes faria um caminho mostrar trinta e o outro
    sessenta no dia em que alguém mexesse num só."""
    codigo = (RAIZ / "caixa_web.py").read_text(encoding="utf-8")
    assert codigo.count("LIMITE_DA_BUSCA_DE_ATOS") >= 2
    assert "limite=30" not in codigo, \
        "voltou um limite escrito à mão fora da constante"
    # OS DOIS CAMINHOS PASSAM PELA MESMA CONSULTA.
    assert codigo.count("_atos_da_tabela(db, busca)") == 2, \
        "um dos caminhos deixou de usar a consulta comum"


def test_a_rota_do_fragmento_nao_grava():
    """SÓ LÊ. A mesma consulta da tela, sem escrever nada — e sem abrir
    transação de escrita, que numa tela de leitura põe a casa no busy_timeout.
    """
    codigo = (RAIZ / "caixa_web.py").read_text(encoding="utf-8")
    inicio = codigo.index("def caixa_protocolo_atos_da_tabela")
    fim = codigo.index("def _quem_esta_no_balcao")
    bloco = codigo[inicio:fim]
    for proibido in ("INSERT", "UPDATE", "DELETE", "db.transaction"):
        assert proibido not in bloco, \
            f"a rota da busca automática passou a escrever: {proibido}"


def test_protocolo_inexistente_e_404_e_nao_lista(cg_casa_logada):
    """Id trocado na barra não pode devolver a tabela do tribunal sobre um
    protocolo que não existe."""
    r = cg_casa_logada["c"].get("/caixa/protocolos/999999/atos-da-tabela"
                                "?busca=firma")
    assert r.status_code == 404
