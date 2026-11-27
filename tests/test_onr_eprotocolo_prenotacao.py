# -*- coding: utf-8 -*-
"""A prenotação com um clique do título do e-Protocolo do ONR (RI013, P2a, 25/11/2026).

O QUE ESTES TESTES GUARDAM
    **A ficha se preenche** do pedido (fictício) que a P1 gravou: apresentante,
    natureza, matrícula ligada ao acervo ou o aviso de que não existe, partes,
    valor, protocolo do ONR, IDContrato e anexos.
    **A ordem da remessa é obrigatória** entre os eletrônicos (CNN 326), e a rota
    confere de novo ao gravar. **Pular sem motivo é recusado.**
    **O vínculo se grava**: o pedido guarda a prenotação, quem e quando; a
    prenotação guarda a origem «e-Protocolo ONR» e o IDContrato.
    **Nenhuma chamada sai para a rede**, e **o caminho do balcão continua igual**.
"""
from __future__ import annotations

import json
import re
import socket
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import onr_eprotocolo as EP                                        # noqa: E402
import onr_eprotocolo_prenotacao as EPP                            # noqa: E402
import onr_wsoficio as W                                           # noqa: E402
from bd_nativo import banco                                        # noqa: E402
from test_onr_eprotocolo import ANEXOS, _con, _ficha, _item, _soap  # noqa: E402

AGORA = "2026-11-25T09:00:00"


def _semear(con, contratos, *, matriculas=None):
    """Os pedidos como a leitura da P1 os grava: lista, ficha e anexos. Sem rede.

    `contratos` é [(id_contrato, data_da_remessa)]; devolve {id_contrato: pedido_id}."""
    EPP.init_schema(con)
    ids = {}
    for i, (contrato, remessa) in enumerate(contratos):
        lista = _soap("ListPedidosAC", "<RETORNO>true</RETORNO><QtdePaginas>1</QtdePaginas>"
                      f"<Pedidos>{_item(contrato, f'EP-{contrato}', 1, remessa)}</Pedidos>")
        item = EP.itens_da_lista(lista)[0][0]
        agora = f"2026-11-2{i % 5}T08:00:0{i % 10}"
        pid = EP.guardar_da_lista(con, W.PRODUCAO, item, agora)["pedido_id"]
        mats = (matriculas or {}).get(contrato, ("1.234", "999999"))
        EP.guardar_ficha(con, pid, EP.resultado_cru(
            _soap("GetPedidoAC_V8", _ficha(contrato, f"EP-{contrato}", remessa=remessa,
                                           matriculas=mats)), "GetPedidoAC_V8"), agora)
        EP.guardar_anexos(con, pid, _soap("ListAnexosAC", ANEXOS), agora)
        ids[contrato] = pid
    return ids


# ------------------------------------------------------------------ a ficha

def test_a_ficha_se_preenche_do_pedido_ficticio():
    con = _con()
    pid = _semear(con, [(701, "2026-11-20")])[701]
    p = EPP.conferir(con, pid)
    f = EPP.ficha_para_prenotar(con, p)
    c = f["campos"]
    assert c["apresentante"] == "JOAO APRESENTANTE"
    assert c["apresentante_documento"] == "00000000191"
    assert c["natureza_titulo"] == "Registro / averbação — Escritura pública"
    assert c["matricula_numero"] == "1234"                      # normalizado: «1.234»
    assert "IDContrato 701" in c["objeto"] and "EP-701" in c["objeto"]
    assert "FULANA COMPRADORA (compradores)" in c["objeto"]
    assert "escritura.pdf" in c["documento_descricao"]
    assert "e-Protocolo ONR" in c["anotacao"] and "701" in c["anotacao"]
    assert f["id_contrato"] == 701 and f["protocolo"] == "EP-701"
    assert f["valor"] == "150.00" and f["cobranca"] == "Integral"
    assert [x["nome"] for x in f["partes"]] == ["FULANA COMPRADORA", "BELTRANO VENDEDOR"]
    assert [a["nome"] for a in f["anexos"]] == ["escritura.pdf"]
    # A matrícula que existe se liga a `ri_matriculas` (a sem complemento); a
    # que não existe vira aviso.
    assert [im["matricula_id"] for im in f["imoveis"]] == [77, None]
    assert any(a["tipo"] == "MATRICULA_FORA_DO_ACERVO" and "999999" in a["texto"]
               for a in f["alertas"])


def test_ficha_ainda_nao_lida_nao_se_prenota():
    con = _con()
    EPP.init_schema(con)
    lista = _soap("ListPedidosAC", "<RETORNO>true</RETORNO><QtdePaginas>1</QtdePaginas>"
                  f"<Pedidos>{_item(800, 'EP-800', 1, '2026-11-20')}</Pedidos>")
    pid = EP.guardar_da_lista(con, W.PRODUCAO, EP.itens_da_lista(lista)[0][0], AGORA)["pedido_id"]
    with pytest.raises(EPP.PrenotacaoEletronicaError, match="ficha deste título ainda não veio"):
        EPP.conferir(con, pid)


# ------------------------------------------------------------------ a ordem e o pulo

def test_a_ordem_da_remessa_e_obrigatoria():
    con = _con()
    ids = _semear(con, [(711, "2026-11-21"), (712, "2026-11-20"), (713, "2026-11-22")])
    assert [p["id_contrato"] for p in EPP.esperando(con, W.PRODUCAO)] == [712, 711, 713]
    assert EPP.conferir(con, ids[712])["a_frente"] == []
    with pytest.raises(EPP.PrenotacaoEletronicaError, match="ordem da remessa") as erro:
        EPP.conferir(con, ids[711])
    assert "EP-712" in str(erro.value) and "Nada foi prenotado" in str(erro.value)
    with pytest.raises(EPP.PrenotacaoEletronicaError, match="2 título"):
        EPP.conferir(con, ids[713])


def test_pular_sem_motivo_e_recusado_e_o_pulo_vale_so_para_aquele_titulo():
    con = _con()
    ids = _semear(con, [(721, "2026-11-20"), (722, "2026-11-21"), (723, "2026-11-22")])
    for motivo in ("", "   ", "curto"):
        with pytest.raises(EPP.PrenotacaoEletronicaError, match="escreva o motivo"):
            EPP.registrar_pulo(con, ids[722], motivo, quem_id=None, quem_nome="ANA", agora=AGORA)
    assert banco(con).valor("SELECT COUNT(*) FROM onr_ep_pulos") == 0
    with pytest.raises(EPP.PrenotacaoEletronicaError, match="já é o primeiro"):
        EPP.registrar_pulo(con, ids[721], "motivo comprido o bastante", quem_id=None,
                           quem_nome="ANA", agora=AGORA)
    pulo = EPP.registrar_pulo(con, ids[722], "  apresentante pediu urgência   por escrito ",
                              quem_id=None, quem_nome="ANA", agora=AGORA)
    assert pulo["pulados"] == [ids[721]] and pulo["motivo"] == "apresentante pediu urgência por escrito"
    # Com o pulo, o 722 passa; o pulo do 722 não serve ao 723.
    assert EPP.conferir(con, ids[722], pulo_id=pulo["pulo_id"])["pulo"]["id"] == pulo["pulo_id"]
    with pytest.raises(EPP.PrenotacaoEletronicaError, match="ordem da remessa"):
        EPP.conferir(con, ids[723], pulo_id=pulo["pulo_id"])
    with pytest.raises(EPP.PrenotacaoEletronicaError, match="ordem da remessa"):
        EPP.conferir(con, ids[722], pulo_id="não é número")


# ------------------------------------------------------------------ o vínculo

def test_o_vinculo_se_grava_uma_vez_e_a_leitura_do_onr_nao_o_desfaz():
    con = _con()
    ids = _semear(con, [(731, "2026-11-20"), (732, "2026-11-21")])
    bd = banco(con)
    bd.escrever("INSERT INTO ri_protocolos(id, numero, data_prenotacao, situacao) "
                "VALUES (5001, 9001, '2026-11-25', 'ABERTO')")
    EPP.vincular(con, ids[731], 5001, quem_id=None, quem_nome="ANA EXEMPLO", agora=AGORA)
    row = bd.um("SELECT * FROM onr_ep_pedidos WHERE id=%s", (ids[731],))
    assert (row["prenotacao_id"], row["prenotado_por_nome"], row["prenotado_em"],
            row["situacao"]) == (5001, "ANA EXEMPLO", AGORA, "EM_ANDAMENTO")
    # O segundo escrevente que chega atrasado é recusado — e a exceção desfaz a
    # transação da prenotação dele.
    with pytest.raises(EPP.PrenotacaoEletronicaError, match="outra pessoa"):
        EPP.vincular(con, ids[731], 5002, quem_id=None, quem_nome="BIA", agora=AGORA)
    # A fila anda: o 732 é a vez.
    assert [p["id"] for p in EPP.esperando(con, W.PRODUCAO)] == [ids[732]]
    assert EPP.conferir(con, ids[732])["a_frente"] == []
    # O ONR ainda diz «Em aberto» (a P2a não avisa): mudar de status lá não
    # devolve o título à fila daqui.
    lista = _soap("ListPedidosAC", "<RETORNO>true</RETORNO><QtdePaginas>1</QtdePaginas>"
                  f"<Pedidos>{_item(731, 'EP-731', 9, '2026-11-20')}</Pedidos>")
    EP.guardar_da_lista(con, W.PRODUCAO, EP.itens_da_lista(lista)[0][0], AGORA)
    assert bd.valor("SELECT situacao FROM onr_ep_pedidos WHERE id=%s", (ids[731],)) == "EM_ANDAMENTO"
    # A prenotação ligada não é contraditório do próprio título.
    bd.escrever("UPDATE ri_protocolos SET matricula_numero='1234' WHERE id=5001")
    p = EP.pedido(con, ids[731])
    assert not [a for a in EP.alertas(con, p) if a["tipo"] == "CONTRADITORIO_PRENOTACAO"]


# ------------------------------------------------------------------ as telas

def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _q(db, sql, args=()):
    with db.connect() as con:
        return banco(con).um(sql, args)


def _semear_na_casa(db, contratos, **kw):
    with db.transaction() as con:
        return _semear(con, contratos, **kw)


@pytest.fixture()
def sem_rede(monkeypatch):
    """Qualquer tentativa de sair para a rede fica anotada e falha."""
    tentativas = []

    def barra(nome):
        def _f(*a, **k):
            tentativas.append((nome, a[:2]))
            raise AssertionError(f"chamada de rede inesperada: {nome}")
        return _f

    import centrais_http
    monkeypatch.setattr(centrais_http, "requisitar", barra("centrais_http.requisitar"))
    monkeypatch.setattr(W, "_transporte_da_casa", barra("onr_wsoficio._transporte_da_casa"))
    monkeypatch.setattr(EP, "ler", barra("onr_eprotocolo.ler"))
    monkeypatch.setattr(socket, "create_connection", barra("socket.create_connection"))
    monkeypatch.setattr(socket.socket, "connect", barra("socket.connect"))
    return tentativas


def _dados(**extra):
    d = {"livro_destino": "2", "telefone": "(99) 98888-7777", "apresentante": "JOAO APRESENTANTE",
         "natureza_titulo": "Registro / averbação", "objeto": "título eletrônico"}
    d.update(extra)
    return d


def test_o_clique_leva_a_prenotacao_de_balcao_preenchida_e_grava_o_vinculo(cg_casa_logada, sem_rede):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    ids = _semear_na_casa(db, [(741, "2026-11-20"), (742, "2026-11-21")],
                          matriculas={741: ("424242",), 742: ("515151",)})
    fila = c.get("/ri/onr/eprotocolo").get_data(as_text=True)
    assert f'href="/registro-imoveis/protocolo?onr_ep={ids[741]}"' in fila
    assert f"?onr_ep={ids[742]}" not in fila, "só o mais antigo fica liberado"
    assert "Pular a ordem" in fila and "2 título(s) esperando prenotação" in fila

    tela = c.get(f"/registro-imoveis/protocolo?onr_ep={ids[741]}").get_data(as_text=True)
    for trecho in (f'name="onr_ep_pedido_id" value="{ids[741]}"', 'value="JOAO APRESENTANTE"',
                   'value="00000000191"', 'value="424242"', "IDContrato <strong>741</strong>",
                   "EP-741", "escritura.pdf", "FULANA COMPRADORA", "150.00",
                   "não existe neste sistema"):
        assert trecho in tela, trecho

    antes = _q(db, "SELECT COUNT(*) AS n FROM ri_protocolos")["n"]
    r = c.post(f"/registro-imoveis/protocolo?onr_ep={ids[741]}",
               data=_dados(csrf_token=_token(tela), onr_ep_pedido_id=str(ids[741]),
                           matricula_numero="424242"),
               follow_redirects=True).get_data(as_text=True)
    assert "ligado a esta prenotação" in r and "SetPrenotacaoAC" in r and "não enviado" in r
    assert _q(db, "SELECT COUNT(*) AS n FROM ri_protocolos")["n"] == antes + 1
    ped = _q(db, "SELECT * FROM onr_ep_pedidos WHERE id=%s", (ids[741],))
    pren = _q(db, "SELECT * FROM ri_protocolos WHERE id=%s", (ped["prenotacao_id"],))
    mario = _q(db, "SELECT id FROM users WHERE username='mario'")["id"]
    assert ped["situacao"] == "EM_ANDAMENTO" and ped["prenotado_por"] == mario and ped["prenotado_em"]
    assert (pren["origem"], pren["origem_chave"]) == (EPP.ORIGEM, "741")
    assert pren["matricula_numero"] == "424242" and pren["situacao"] == "ABERTO"
    log = _q(db, "SELECT details FROM audit_logs WHERE action='ONR_EPROTOCOLO_PRENOTADO' "
                 "AND entity_id=%s", (ids[741],))
    assert json.loads(log["details"])["protocolo_id"] == pren["id"]
    # O título já prenotado não se prenota de novo, nem pela URL velha.
    de_novo = c.post(f"/registro-imoveis/protocolo?onr_ep={ids[741]}",
                     data=_dados(csrf_token=_token(tela), onr_ep_pedido_id=str(ids[741])),
                     follow_redirects=True).get_data(as_text=True)
    assert "já foi prenotado" in de_novo
    assert _q(db, "SELECT COUNT(*) AS n FROM ri_protocolos")["n"] == antes + 1
    assert sem_rede == []


def test_fora_da_ordem_e_recusado_e_pular_pede_motivo(cg_casa_logada, sem_rede):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    ids = _semear_na_casa(db, [(751, "2026-11-20"), (752, "2026-11-21")])
    tela = c.get("/ri/onr/eprotocolo").get_data(as_text=True)
    tok = _token(tela)
    antes = _q(db, "SELECT COUNT(*) AS n FROM ri_protocolos")["n"]
    # O POST direto, sem pulo, não passa: a rota confere a ordem ao gravar.
    r = c.post("/registro-imoveis/protocolo",
               data=_dados(csrf_token=tok, onr_ep_pedido_id=str(ids[752])),
               follow_redirects=True).get_data(as_text=True)
    assert "ordem da remessa" in r and "Nada foi prenotado" in r
    assert "onr_ep_pedido_id" not in r, "a recusa volta à ficha, e não ao formulário sem o vínculo"
    assert _q(db, "SELECT COUNT(*) AS n FROM ri_protocolos")["n"] == antes, "nenhum número se gasta"
    # O link direto para o segundo também volta à ficha.
    r = c.get(f"/registro-imoveis/protocolo?onr_ep={ids[752]}")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/ri/onr/eprotocolo/{ids[752]}")
    # Pular sem motivo: recusado, e nada se grava.
    r = c.post(f"/ri/onr/eprotocolo/{ids[752]}/pular", data={"csrf_token": tok, "motivo": " "},
               follow_redirects=True).get_data(as_text=True)
    assert "escreva o motivo" in r
    assert _q(db, "SELECT COUNT(*) AS n FROM onr_ep_pulos")["n"] == 0
    # Com motivo: vai para a auditoria e leva à prenotação de balcão preenchida.
    r = c.post(f"/ri/onr/eprotocolo/{ids[752]}/pular",
               data={"csrf_token": tok, "motivo": "ordem do oficial, título com prazo judicial"})
    assert r.status_code == 302 and f"onr_ep={ids[752]}" in r.headers["Location"]
    pulo = _q(db, "SELECT * FROM onr_ep_pulos WHERE pedido_id=%s", (ids[752],))
    log = _q(db, "SELECT details FROM audit_logs WHERE action='ONR_EPROTOCOLO_FORA_DA_ORDEM'")
    assert json.loads(log["details"])["motivo"] == "ordem do oficial, título com prazo judicial"
    assert json.loads(log["details"])["pulados"] == [ids[751]]
    tela = c.get(r.headers["Location"]).get_data(as_text=True)
    assert f'name="onr_ep_pulo_id" value="{pulo["id"]}"' in tela and "ordem do oficial" in tela
    r = c.post(r.headers["Location"],
               data=_dados(csrf_token=tok, onr_ep_pedido_id=str(ids[752]),
                           onr_ep_pulo_id=str(pulo["id"])),
               follow_redirects=True).get_data(as_text=True)
    assert "ligado a esta prenotação" in r
    ped = _q(db, "SELECT * FROM onr_ep_pedidos WHERE id=%s", (ids[752],))
    assert ped["pulo_id"] == pulo["id"] and ped["prenotacao_id"]
    assert _q(db, "SELECT protocolo_id FROM onr_ep_pulos WHERE id=%s",
              (pulo["id"],))["protocolo_id"] == ped["prenotacao_id"]
    assert sem_rede == []


def test_prenotacao_de_balcao_aberta_na_mesma_matricula_e_destacada(cg_casa_logada, sem_rede):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    tok = _token(c.get("/registro-imoveis/protocolo").get_data(as_text=True))
    c.post("/registro-imoveis/protocolo",
           data=_dados(csrf_token=tok, apresentante="MARIA DE EXEMPLO", matricula_numero="616161"),
           follow_redirects=True)
    ids = _semear_na_casa(db, [(761, "2026-11-20")], matriculas={761: ("616161",)})
    tela = c.get(f"/registro-imoveis/protocolo?onr_ep={ids[761]}").get_data(as_text=True)
    assert "<strong>Contraditório:</strong>" in tela and "mesma matrícula" in tela
    assert sem_rede == []


def test_o_caminho_do_balcao_continua_igual(cg_casa_logada, sem_rede):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    ids = _semear_na_casa(db, [(771, "2026-11-20")])
    tela = c.get("/registro-imoveis/protocolo").get_data(as_text=True)
    assert "onr_ep_pedido_id" not in tela and "e-Protocolo do ONR" not in tela
    r = c.post("/registro-imoveis/protocolo",
               data=_dados(csrf_token=_token(tela), apresentante="MARIA DE EXEMPLO",
                           matricula_numero="717171"),
               follow_redirects=True).get_data(as_text=True)
    assert "prenotado em" in r and "e-Protocolo" not in r.split("prenotado em", 1)[1][:400]
    pren = _q(db, "SELECT * FROM ri_protocolos WHERE apresentante='MARIA DE EXEMPLO'")
    assert (pren["origem"], pren["origem_chave"]) == ("MANUAL", None)
    assert _q(db, "SELECT situacao, prenotacao_id FROM onr_ep_pedidos WHERE id=%s",
              (ids[771],)) == {"situacao": "A_PRENOTAR", "prenotacao_id": None}
    log = _q(db, "SELECT details FROM audit_logs WHERE action='RI_PRENOTACAO' ORDER BY id DESC LIMIT 1")
    assert "origem" not in json.loads(log["details"])
    assert sem_rede == []


def test_o_auditor_ve_a_fila_mas_nao_tem_o_botao(cg_casa):
    from conftest import cg_login
    db = cg_casa["db"]
    db.create_user("aud", "Auditor de Exemplo", "Senha#12345", "AUDITOR")
    ids = _semear_na_casa(db, [(781, "2026-11-20"), (782, "2026-11-21")])
    c = cg_casa["c"]
    cg_login(c, "aud", "Senha#12345")
    tela = c.get("/ri/onr/eprotocolo").get_data(as_text=True)
    assert "EP-781" in tela and "?onr_ep=" not in tela and "/pular" not in tela
    assert c.post(f"/ri/onr/eprotocolo/{ids[782]}/pular",
                  data={"motivo": "qualquer motivo comprido"}).status_code in (302, 400, 403)
    with db.connect() as con:
        assert banco(con).valor("SELECT COUNT(*) FROM onr_ep_pulos") == 0
