"""Encerrar o protocolo do balcão — o atendimento que não virou ato.

O DÉBITO, que estava no `CLAUDE.md` desde agosto: **«encerrar protocolo»**.

O QUE SE MEDIU EM 28/08/2026, ANTES DE CONSTRUIR
    São **640 protocolos abertos**, todos de 2026 e **todos vindos do
    E-Ofício**: 250 do Registro de Imóveis, 226 do Registro Civil, 101 de
    firmas, 30 das Notas, 30 do Protesto, 3 do RTD.

    E **nenhum deles tem um único item**, nem valor, nem nada quitado — são
    atendimentos que começaram e nunca viraram serviço: «orçamento registro
    TÍTULO DE DOMÍNIO», «CERTIDÃO», «2ª VIA NASCIMENTO».

O DEFEITO ERA O CONTRÁRIO DO DE COSTUME
    Neste projeto a forma repetida é «função pronta que nenhuma tela chama».
    Aqui é o inverso: a situação terminal estava declarada em **três** lugares
    — o comentário do esquema, o rótulo de `SITUACOES`, e até uma guarda em
    `_atualizar_situacao` que evita sobrescrevê-la — e **nenhuma rota
    conseguia produzi-la**. Havia uma trava esperando um estado que nada
    criava.
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

import caixa_protocolo as CXP

SENHA = "Senha#12345"


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


def _protocolo(con, *, numero="2026.08.146", assunto="orçamento de certidão",
               situacao="ABERTO", itens=()):
    cur = con.execute(
        """INSERT INTO cx_protocolos (numero, data_abertura, atribuicao,
               interessado, assunto, situacao, origem, criado_em)
           VALUES (?, '2026-08-12', 'RI', 'FULANO DE TAL', ?, ?, 'MANUAL',
                   '2026-08-12T09:00')""", (numero, assunto, situacao))
    pid = int(cur.lastrowid)
    for codigo, quitado in itens:
        # a coluna e `codigo_ato`, e nao `codigo_tj` — o codigo do TJ mora em
        # `cx_servicos`, e aqui fica o do ato
        con.execute(
            """INSERT INTO cx_protocolo_atos (protocolo_id, codigo_ato,
                   descricao, quantidade, quitado, origem)
               VALUES (?,?, 'um ato', 1, ?, 'MANUAL')""",
            (pid, codigo, quitado))
    return pid


# ------------------------------------------- o que o encerramento faz


def test_encerrar_grava_a_situacao_o_motivo_e_quem_fez(casa):
    con = _con(casa)
    with con:
        pid = _protocolo(con)
        CXP.encerrar(con, pid, situacao=CXP.CANCELADO,
                     motivo="era só orçamento; o cliente não voltou",
                     quem="mario", agora="2026-08-28T15:00")
    r = _con(casa).execute("SELECT * FROM cx_protocolos WHERE id=?",
                           (pid,)).fetchone()
    assert r["situacao"] == "CANCELADO"
    assert r["finalizado"] == 1
    assert r["data_finalizacao"] == "2026-08-28T15:00"
    assert "não voltou" in r["encerramento_motivo"]
    assert r["encerrado_por"] == "mario"


def test_as_duas_palavras_dizem_coisas_diferentes():
    """`ENTREGUE` é o atendimento resolvido; `CANCELADO` é o que não virou
    serviço. Juntar as duas num «encerrado» faria a lista de um mês não
    distinguir o trabalho feito do trabalho que não houve."""
    assert set(CXP.ENCERRAMENTOS) == {"ENTREGUE", "CANCELADO"}
    assert "resolvido" in CXP.ENCERRAMENTOS["ENTREGUE"]
    assert "não virou serviço" in CXP.ENCERRAMENTOS["CANCELADO"]


def test_o_vocabulario_e_o_que_a_casa_ja_tinha():
    """As duas palavras já estavam no comentário do esquema e no rótulo da
    tela desde sempre. Inventar uma terceira seria criar vocabulário novo
    tendo o antigo à mão — e ele já está em tela."""
    esquema = (RAIZ / "caixa_schema.py").read_text(encoding="utf-8")
    assert "ABERTO | ENTREGUE | CANCELADO" in esquema
    import caixa_web
    assert "ENTREGUE" in caixa_web.SITUACOES
    assert "CANCELADO" in caixa_web.SITUACOES


# ------------------------------------------- as três recusas


def test_protocolo_com_item_quitado_nao_se_encerra(casa):
    """Esse dinheiro já entrou no caixa. Encerrar aqui faria o serviço sumir da
    lista e o valor ficar — e a conferência do dia fecharia sem saber por quê.
    O caminho é o estorno, que deixa rastro."""
    con = _con(casa)
    with con:
        pid = _protocolo(con, situacao="A_PAGAR",
                         itens=(("13.18", 1), ("14.5.1", 0)))
    with pytest.raises(CXP.ProtocoloError) as e:
        with _con(casa) as c:
            CXP.encerrar(c, pid, situacao=CXP.CANCELADO,
                         motivo="o cliente desistiu do serviço todo",
                         quem="mario", agora="2026-08-28T15:00")
    assert "estorne" in str(e.value).lower()
    assert _con(casa).execute(
        "SELECT situacao FROM cx_protocolos WHERE id=?",
        (pid,)).fetchone()["situacao"] == "A_PAGAR"


def test_encerrar_exige_motivo_escrito(casa):
    """«Dispensar é decisão do oficial; ignorar não é.» Numa correição a
    pergunta é exatamente por que aquele atendimento não virou ato."""
    con = _con(casa)
    with con:
        pid = _protocolo(con)
    for vazio in ("", "   ", "ok"):
        with pytest.raises(CXP.ProtocoloError) as e:
            with _con(casa) as c:
                CXP.encerrar(c, pid, situacao=CXP.CANCELADO, motivo=vazio,
                             quem="mario", agora="2026-08-28T15:00")
        assert "Escreva por que" in str(e.value)


def test_encerrado_nao_se_encerra_de_novo(casa):
    """O segundo clique trocaria o motivo e a data do primeiro, e o rastro
    passaria a contar outra história."""
    con = _con(casa)
    with con:
        pid = _protocolo(con)
        CXP.encerrar(con, pid, situacao=CXP.CANCELADO,
                     motivo="era só orçamento; o cliente não voltou",
                     quem="mario", agora="2026-08-28T15:00")
    with pytest.raises(CXP.ProtocoloError) as e:
        with _con(casa) as c:
            CXP.encerrar(c, pid, situacao=CXP.ENTREGUE,
                         motivo="na verdade foi entregue por outro caminho",
                         quem="mario", agora="2026-08-28T16:00")
    assert "reabra primeiro" in str(e.value)


def test_encerramento_fora_do_catalogo_e_recusado(casa):
    con = _con(casa)
    with con:
        pid = _protocolo(con)
    with pytest.raises(CXP.ProtocoloError) as e:
        with _con(casa) as c:
            CXP.encerrar(c, pid, situacao="ARQUIVADO",
                         motivo="um motivo suficientemente longo",
                         quem="mario", agora="2026-08-28T15:00")
    assert "não é um jeito de encerrar" in str(e.value)


# ------------------------------------------- reabrir


def test_reabrir_recalcula_a_situacao_dos_itens_e_nao_a_deixa_escolher(casa):
    """Deixar quem reabre escolher permitiria devolver como PAGO um protocolo
    que ninguém pagou. A situação vem dos itens, que é a regra da casa."""
    con = _con(casa)
    with con:
        pid = _protocolo(con, itens=(("13.18", 0),))
        CXP.encerrar(con, pid, situacao=CXP.CANCELADO,
                     motivo="o cliente desistiu antes de pagar",
                     quem="mario", agora="2026-08-28T15:00")
        CXP.reabrir(con, pid, motivo="o cliente voltou no dia seguinte",
                    quem="mario", agora="2026-08-29T09:00")
    r = _con(casa).execute("SELECT * FROM cx_protocolos WHERE id=?",
                           (pid,)).fetchone()
    assert r["situacao"] == "A_PAGAR"        # tem item, nenhum quitado
    assert r["finalizado"] == 0
    assert r["data_finalizacao"] is None


def test_o_motivo_do_encerramento_fica_gravado_depois_de_reabrir(casa):
    """Apagá-lo faria o rastro dizer que aquele encerramento nunca existiu —
    e engano se conserta à vista, não se esconde."""
    con = _con(casa)
    with con:
        pid = _protocolo(con)
        CXP.encerrar(con, pid, situacao=CXP.CANCELADO,
                     motivo="era só orçamento; o cliente não voltou",
                     quem="mario", agora="2026-08-28T15:00")
        CXP.reabrir(con, pid, motivo="ele voltou e quer fazer",
                    quem="mario", agora="2026-08-29T09:00")
    guardado = _con(casa).execute(
        "SELECT encerramento_motivo m FROM cx_protocolos WHERE id=?",
        (pid,)).fetchone()["m"]
    assert "era só orçamento" in guardado          # o primeiro continua lá
    assert "reaberto" in guardado and "voltou e quer fazer" in guardado


def test_reabrir_o_que_nao_esta_encerrado_e_recusado(casa):
    con = _con(casa)
    with con:
        pid = _protocolo(con)
    with pytest.raises(CXP.ProtocoloError) as e:
        with _con(casa) as c:
            CXP.reabrir(c, pid, motivo="um motivo suficientemente longo",
                        quem="mario", agora="2026-08-29T09:00")
    assert "não está encerrado" in str(e.value)


# ------------------------------------------- a lista dos parados


def test_a_lista_traz_so_os_abertos_sem_item(casa):
    con = _con(casa)
    with con:
        _protocolo(con, numero="A", situacao="ABERTO")
        _protocolo(con, numero="B", situacao="A_PAGAR", itens=(("13.18", 0),))
        _protocolo(con, numero="C", situacao="ABERTO", itens=(("13.18", 0),))
    parados = CXP.abertos_sem_item(_con(casa))
    assert [p["numero"] for p in parados] == ["A"]
    assert CXP.quantos_abertos_sem_item(_con(casa)) == 1


def test_a_lista_diz_quantos_ficaram_de_fora(casa):
    """Lista cortada que não diz que cortou faz quem a lê achar que acabou —
    «varredor que deixa de achar passa calado»."""
    con = _con(casa)
    with con:
        for i in range(5):
            _protocolo(con, numero=f"2026.08.{i}")
    html = casa["cliente"].get(
        "/caixa/protocolos-parados").get_data(as_text=True)
    assert "5" in html
    assert CXP.abertos_sem_item(_con(casa), limite=2).__len__() == 2
    assert CXP.quantos_abertos_sem_item(_con(casa)) == 5


# ------------------------------------------- a tela


def test_a_ficha_oferece_encerrar_quando_nao_ha_dinheiro(casa):
    con = _con(casa)
    with con:
        pid = _protocolo(con)
    html = casa["cliente"].get(
        f"/caixa/protocolos/{pid}").get_data(as_text=True)
    assert 'value="encerrar"' in html
    assert "não virou serviço" in html


def test_a_ficha_nao_oferece_encerrar_quando_ha_item_quitado(casa):
    """A tela não oferece por educação; o domínio recusa por dever — e há
    teste para os dois lados."""
    con = _con(casa)
    with con:
        pid = _protocolo(con, situacao="A_PAGAR", itens=(("13.18", 1),))
    # o espaço se normaliza: o HTML quebra linha onde quiser, e um teste que
    # falha por causa de uma quebra de linha da tela não prova nada
    html = casa["cliente"].get(
        f"/caixa/protocolos/{pid}").get_data(as_text=True)
    assert 'value="encerrar"' not in html
    assert "estorne o lançamento" in " ".join(html.split()).lower()


def test_a_tela_encerra_e_a_recusa_chega_ao_balcao(casa):
    con = _con(casa)
    with con:
        pid = _protocolo(con)
    html = casa["cliente"].get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    # sem motivo, a tela recusa e diz o que escrever
    r = casa["cliente"].post(f"/caixa/protocolos/{pid}", data={
        "csrf_token": _token(html), "acao": "encerrar",
        "encerramento": "CANCELADO", "motivo": ""}, follow_redirects=True)
    assert "Escreva por que" in r.get_data(as_text=True)
    # com motivo, encerra
    r = casa["cliente"].post(f"/caixa/protocolos/{pid}", data={
        "csrf_token": _token(html), "acao": "encerrar",
        "encerramento": "CANCELADO",
        "motivo": "era só orçamento; o cliente não voltou"},
        follow_redirects=True)
    assert "encerrado como cancelado" in r.get_data(as_text=True)
    assert _con(casa).execute(
        "SELECT situacao FROM cx_protocolos WHERE id=?",
        (pid,)).fetchone()["situacao"] == "CANCELADO"


def test_quem_encerrou_sai_da_sessao_e_nao_de_um_campo(casa):
    """Campo que o operador tem de preencher para o rastro ficar bom é campo
    que fica vazio."""
    con = _con(casa)
    with con:
        pid = _protocolo(con)
    html = casa["cliente"].get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    casa["cliente"].post(f"/caixa/protocolos/{pid}", data={
        "csrf_token": _token(html), "acao": "encerrar",
        "encerramento": "ENTREGUE",
        "motivo": "resolvido no balcão sem custas"}, follow_redirects=True)
    assert _con(casa).execute(
        "SELECT encerrado_por FROM cx_protocolos WHERE id=?",
        (pid,)).fetchone()["encerrado_por"] == "mario"


def test_o_encerramento_fica_na_auditoria(casa):
    con = _con(casa)
    with con:
        pid = _protocolo(con)
    html = casa["cliente"].get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    casa["cliente"].post(f"/caixa/protocolos/{pid}", data={
        "csrf_token": _token(html), "acao": "encerrar",
        "encerramento": "CANCELADO",
        "motivo": "era só orçamento; o cliente não voltou"},
        follow_redirects=True)
    assert _con(casa).execute(
        "SELECT COUNT(*) c FROM audit_logs WHERE action='PROTOCOLO_ENCERRAR'"
    ).fetchone()["c"] == 1


# ------------------------------------------- a conta mora num lugar só


def test_a_situacao_pelos_itens_e_a_mesma_conta_das_duas_telas():
    """Duas versões da conta que decide se um protocolo está pago é como elas
    divergem — e a divergência apareceria no dia em que uma fosse corrigida."""
    codigo = (RAIZ / "caixa_protocolo.py").read_text(encoding="utf-8")
    assert "def situacao_pelos_itens" in codigo
    web = (RAIZ / "caixa_web.py").read_text(encoding="utf-8")
    # a rota não reescreve a regra: ela chama o domínio
    assert "CXP.encerrar(" in web and "CXP.reabrir(" in web
    assert "UPDATE cx_protocolos\n              SET situacao" not in web


# ======================================================== o problema #90
#
#     «ESTOU TENTANDO GERAR UM ORÇAMENTO PORÉM O SISTEMA NÃO ESTÁ RESPONDENDO
#      AOS MEUS COMANDOS ...... VERIFICAR POR FAVOR»
#                       — Beatriz, 21/09/2026 às 14h39, protocolo 2026.09.46
#
# **O SISTEMA RESPONDIA: ELE É QUE NÃO DIZIA NADA.** Medido na auditoria do dia:
# às 14h34 ela emitiu o orçamento do protocolo 21183 (`ORCAMENTO_EMITIDO`, total
# 165,60); às 14h37 abriu o 21394, novo, **sem um único item**; às 14h39 relatou.
# No protocolo sem itens o botão não existia — o `{% if atos %}` o escondia — e
# quem acabou de usá-lo dois minutos antes procura, não acha, e conclui que a
# tela travou.


def test_protocolo_sem_itens_diz_por_que_nao_ha_orcamento(casa):
    """ESCONDER SEM DIZER POR QUÊ É O DEFEITO — é a régua que esta casa já
    tinha escrita: *lista vazia que só mostra nada faz o operador achar que
    quebrou*."""
    con = _con(casa)
    with con:
        pid = _protocolo(con, numero="2026.09.90")
    tela = casa["cliente"].get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    assert "Sem itens não há o que orçar" in tela
    assert 'href="#acrescentar-item"' in tela, (
        "o aviso aponta ONDE se resolve, e não só que não dá")
    assert 'id="acrescentar-item"' in tela, (
        "a âncora tem de existir, senão o link não leva a lugar nenhum")
    assert f"/caixa/protocolos/{pid}/orcamento" not in tela, (
        "sem itens o botão não sai — a rota recusaria, e oferecer o que "
        "recusa é o outro lado do mesmo defeito")


def test_com_item_o_botao_do_orcamento_volta_sozinho(casa):
    con = _con(casa)
    with con:
        pid = _protocolo(con, numero="2026.09.91", itens=(("16.24.4", 0),))
    tela = casa["cliente"].get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    assert f"/caixa/protocolos/{pid}/orcamento" in tela
    assert "Sem itens não há o que orçar" not in tela


def test_a_rota_continua_recusando_o_orcamento_sem_itens(casa):
    """A tela explica; **quem recusa é a rota**, porque é ela que faz. Duas
    guardas no mesmo lugar não: uma educa, a outra impede."""
    con = _con(casa)
    with con:
        pid = _protocolo(con, numero="2026.09.92")
    r = casa["cliente"].get(f"/caixa/protocolos/{pid}/orcamento",
                            follow_redirects=True)
    assert r.status_code == 200
    assert "não tem itens para orçar" in r.get_data(as_text=True)
