"""Abrir protocolo não nasce como RI, e a firma vê o que ficou de fora.

O formulário de abrir protocolo trazia a atribuição já marcada com RI, a
primeira opção. O reconhecimento de firma só aceita FIRMAS, NOTAS ou
atribuição em branco: o protocolo pago no 13.17.2, até o que estava em
atendimento, sumia da lista «Protocolo que paga o selo» e da cobertura
sem dizer por quê.

O que estes testes protegem:
    - a tela não marca RI sozinha, e o servidor recusa abrir sem escolha;
    - RI, RCPN, RTD, RCPJ, Protesto, Notas e Firmas continuam abrindo quando
      a pessoa escolhe;
    - o protocolo em atendimento que ficou de fora aparece com o motivo e
      sem botão de escolher;
    - a lista vazia do reconhecimento diz os códigos 13.17.2, 13.17.3 e
      13.17.4.
"""
from __future__ import annotations

import re
from datetime import date

import caixa_protocolo as CXP
from bd_nativo import banco


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe o csrf_token"
    return achado.group(1)


def _n_protocolos(db) -> int:
    with db.connect() as con:
        return int(banco(con).valor("SELECT count(*) FROM cx_protocolos"))


def test_o_formulario_nao_marca_ri_e_sem_escolha_nao_abre(cg_casa_logada):
    casa = cg_casa_logada
    c = casa["c"]
    html = c.get("/caixa/protocolos").get_data(as_text=True)
    formulario = html.split("Abrir protocolo", 1)[1].split("</form>", 1)[0]
    select = formulario.split('name="atribuicao"', 1)[1].split("</select>", 1)[0]
    assert "required" in formulario.split('name="atribuicao"', 1)[0][-80:] or \
        "required" in select[:40] or 'name="atribuicao" required' in formulario
    assert '<option value="">escolha a atribuição</option>' in select
    assert "selected" not in select
    antes = _n_protocolos(casa["db"])
    recusa = c.post("/caixa/protocolos", data={
        "csrf_token": _token(html), "acao": "novo",
        "interessado": "CLIENTE DE EXEMPLO", "telefone": "(99) 90000-0000",
        "atribuicao": "",
    }, follow_redirects=True).get_data(as_text=True)
    assert "Escolha a atribuição" in recusa
    assert _n_protocolos(casa["db"]) == antes


def test_as_atribuicoes_do_balcao_abrem_quando_a_pessoa_escolhe(cg_casa_logada):
    casa = cg_casa_logada
    c, db = casa["c"], casa["db"]
    for atrib in ("RI", "RCPN", "RTD", "RCPJ", "PROTESTO", "NOTAS", "FIRMAS"):
        html = c.get("/caixa/protocolos").get_data(as_text=True)
        r = c.post("/caixa/protocolos", data={
            "csrf_token": _token(html), "acao": "novo",
            "interessado": "CLIENTE DE EXEMPLO", "telefone": "(99) 90000-0000",
            "atribuicao": atrib,
        }, follow_redirects=False)
        assert r.status_code == 302, atrib
        with db.connect() as con:
            gravada = banco(con).valor(
                "SELECT atribuicao FROM cx_protocolos ORDER BY id DESC LIMIT 1")
        assert gravada == atrib


def test_a_firma_mostra_o_protocolo_de_ri_com_o_motivo_e_os_codigos(cg_casa_logada):
    casa = cg_casa_logada
    c, db = casa["c"], casa["db"]
    hoje = date.today().isoformat()
    with db.transaction() as con:
        pid = int(banco(con).escrever(
            """INSERT INTO cx_protocolos
               (numero, data_abertura, atribuicao, interessado, situacao, criado_em)
               VALUES (%s,%s,'RI',%s,'ABERTO',%s) RETURNING id""",
            ("2099.10.77", hoje, "CLIENTE DE EXEMPLO", hoje + "T10:00:00"))[0]["id"])
        banco(con).escrever(
            """INSERT INTO cx_protocolo_atos
               (protocolo_id, descricao, codigo_ato, quantidade, valor_total, quitado)
               VALUES (%s,%s,'13.17.2',1,'10,00',1)""",
            (pid, "Reconhecimento de firma"))
        CXP.atender(con, usuario="MARIO EXEMPLO DOS SANTOS",
                    protocolo="2099.10.77", agora=hoje + "T10:00:00")
        banco(con).escrever(
            """INSERT INTO nt_cartoes (nome, nome_norm, criado_em)
               VALUES (%s,%s,%s)""",
            ("CLIENTE DE EXEMPLO", "cliente de exemplo", hoje + "T10:00:00"))
    # A lista do selo mora no formulário que só abre depois de achar o cartão.
    tela = c.get("/notas/reconhecimento", query_string={"busca": "CLIENTE"}
                 ).get_data(as_text=True)
    assert "Este ato pede:" in tela
    for codigo in ("13.17.2", "13.17.3", "13.17.4"):
        assert codigo in tela
    assert "2099.10.77" in tela
    assert "atribuição incompatível" in tela
    assert "não dá para escolher" in tela
    assert f'name="protocolo_selo" value="{pid}"' not in tela

    cobertura = c.get("/selo/cobertura", query_string={
        "tabela": "nt_reconhecimentos", "pedido": "13.*:1",
    }).get_data(as_text=True)
    assert "item do grupo 13" in cobertura
    assert "2099.10.77" in cobertura
    assert "atribuição incompatível" in cobertura
    assert "não dá para escolher" in cobertura
    assert f'name="protocolo_selo" value="{pid}"' not in cobertura
