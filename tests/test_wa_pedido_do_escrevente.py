"""O pedido que a IA do WhatsApp encaminha (15/11/2026): dono, cobrança, protocolo e anexos.

- quem responde pelo balcão geral recebe a tarefa sem setor (`wa_ferramentas`);
- o pedido parado é cobrado uma vez, no expediente (`wa_cobranca`);
- o escrevente liga o pedido ao protocolo do Caixa, e a IA passa a ver a situação;
- o arquivo da conversa vai, em cópia, à tarefa ou ao protocolo (`wa_anexos`).

Nada aqui fala com a Meta nem com provedor de verdade.
"""
from __future__ import annotations

import hashlib
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ), str(RAIZ / "tests")]

import wa_anexos as ANEXOS  # noqa: E402
import wa_atendente as AT  # noqa: E402
import wa_cobranca as COBRANCA  # noqa: E402
import wa_escrevente as WE  # noqa: E402
import wa_ferramentas as FERR  # noqa: E402
import wa_horario as HORARIO  # noqa: E402
import wa_pedido as PEDIDO  # noqa: E402
import wa_schema as SCH  # noqa: E402
from bd_nativo import banco  # noqa: E402
from test_wa_atendente import (AGORA, SENHA, Graph, _cfg, _entrada, _entrar,  # noqa: E402,F401
                               _sem_rede, _token, _um, casa)
from test_wa_escrevente_conversa import Roteiro, _ligar, _pedir  # noqa: E402

PDF = b"%PDF-1.4\n" + b"x" * 200


def _usuario(db, login, nome, papel="USER"):
    return int(db.create_user(login, nome, SENHA, papel))


def _pedido(db, casa, texto="quero uma certidão", servico="certidao_civil", meta="wamid.p1"):
    cid = _entrada(db, texto, meta_id=meta)
    AT.rodada(db, agora=AGORA, pasta_de_dados=casa["pasta"], http_post=Graph(),
              conversar=Roteiro(_pedir(servico, "Quer o serviço."), "Encaminhado."))
    return cid, _um(db, "SELECT * FROM wa_pedido WHERE conversa_id=%s", (cid,))


def _protocolo(db, numero="2026.11.7"):
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO cx_protocolos (numero, data_abertura, situacao, atribuicao, criado_em)
               VALUES (%s, '2026-10-20', 'ABERTO', 'RI', '2026-10-20T09:00:00')""", (numero,))
    return _um(db, "SELECT id FROM cx_protocolos WHERE numero=%s", (numero,))["id"]


def _arquivo(db, cid, pasta, dados=PDF, nome="escritura.pdf", mime="application/pdf"):
    caminho = Path(pasta) / "whatsapp-teste" / (hashlib.sha256(dados).hexdigest() + ".pdf")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(dados)
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO wa_mensagem (conversa_id, direcao, texto, criado_em, meta_id, tipo,
                   arquivo_nome, arquivo_caminho, arquivo_mime, arquivo_bytes, arquivo_sha256,
                   ia_situacao)
               VALUES (%s, 'in', '', %s, %s, 'document', %s, %s, %s, %s, %s, 'respondida')""",
            (cid, AGORA, f"wamid.arq-{nome}", nome, str(caminho), mime, len(dados),
             hashlib.sha256(dados).hexdigest()))
    return _um(db, "SELECT id FROM wa_mensagem WHERE meta_id=%s", (f"wamid.arq-{nome}",))["id"], caminho


# ---------------------------------------------------------------- o dono do balcão


def test_quem_responde_pelo_balcao_recebe_a_tarefa_sem_setor(casa):
    db = casa["db"]
    _ligar(db)
    dono = _usuario(db, "beatriz", "BEATRIZ EXEMPLO")
    with db.transaction() as con:
        sem = FERR.responsavel_do_setor(con, "ATENDIMENTO")
        AT.gravar_configuracao(con, {"ia_ligada": "1", "ia_escrevente": "1",
                                     "provedor": "claude", "dono_do_balcao": str(dono)},
                               por="MARIO", agora=AGORA)
        com = FERR.responsavel_do_setor(con, "ATENDIMENTO")
    assert sem == {} and com == {"user_id": dono, "nome": "BEATRIZ"}
    _cid, pedido = _pedido(db, casa, "tenho uma dúvida", servico="orientacao")
    tarefa = _um(db, "SELECT assigned_user_id FROM tasks WHERE source_ref=%s",
                 (f"wa_pedido:{pedido['id']}",))
    assert tarefa["assigned_user_id"] == dono


def test_sem_dono_do_balcao_a_tela_avisa_e_dono_inativo_e_recusado(casa):
    db = casa["db"]
    _ligar(db)
    form = {"ia_ligada": "1", "ia_escrevente": "1", "provedor": "claude", "dono_do_balcao": ""}
    with db.transaction() as con:
        avisos = AT.gravar_configuracao(con, form, por="MARIO", agora=AGORA)
    assert any("balcão geral" in a for a in avisos)
    try:
        with db.transaction() as con:
            AT.gravar_configuracao(con, {**form, "dono_do_balcao": "999999"},
                                   por="MARIO", agora=AGORA)
        assert False, "aceitou pessoa que não existe"
    except AT.AtendenteErro as erro:
        assert "pessoa ativa" in str(erro)


# ---------------------------------------------------------------- a cobrança


def test_o_relogio_so_corre_no_expediente():
    regra = HORARIO.ler("seg-sex 08:00-14:00")
    sexta = datetime(2026, 11, 13, 13, 30)          # sexta, meia hora antes de fechar
    segunda = datetime(2026, 11, 16, 8, 30)         # segunda, meia hora depois de abrir
    assert COBRANCA.minutos_uteis(regra, sexta, segunda) == 60
    assert COBRANCA.minutos_uteis(None, sexta, segunda) == (segunda - sexta).seconds // 60 + 2 * 24 * 60
    assert COBRANCA.espera_em_palavras(45) == "45 min"
    assert COBRANCA.espera_em_palavras(130) == "2 h de expediente"


def test_o_pedido_parado_e_cobrado_uma_vez_e_a_ia_ve_a_espera(casa):
    db = casa["db"]
    _ligar(db, **{SCH.CHAVE_PRAZO_MINUTOS: "30"})
    cid, pedido = _pedido(db, casa)
    tarefa_ref = f"wa_pedido:{pedido['id']}"
    assert COBRANCA.cobrar(db, agora="2026-10-26T10:20:00") == 0        # dentro do prazo
    depois = "2026-10-26T11:30:00"
    assert COBRANCA.cobrar(db, agora=depois) == 1
    assert COBRANCA.cobrar(db, agora="2026-10-26T15:00:00") == 0        # uma vez só
    tarefa = _um(db, "SELECT id, priority FROM tasks WHERE source_ref=%s", (tarefa_ref,))
    assert tarefa["priority"] == "ALTA"
    nota = _um(db, "SELECT note FROM task_history WHERE task_id=%s AND action='NOTA' "
                   "ORDER BY id DESC LIMIT 1", (tarefa["id"],))["note"]
    assert "sem atendimento há" in nota
    assert _um(db, "SELECT cobrado_em FROM wa_pedido WHERE id=%s",
               (pedido["id"],))["cobrado_em"] == depois
    # a IA lê há quanto tempo o pedido espera, e que já foi cobrado
    conversa = dict(_um(db, "SELECT * FROM wa_conversa WHERE id=%s", (cid,)))
    estado = WE.estado(db, conversa, agora=depois, rotina={}, arquivos=0)
    assert "aguardando o escrevente há 1 h de expediente — já cobrado da equipe" in estado


def test_nao_se_cobra_o_que_alguem_ja_pegou(casa):
    db = casa["db"]
    _ligar(db)
    cid, pedido = _pedido(db, casa)
    with db.transaction() as con:
        banco(con).escrever("INSERT INTO wa_mensagem (conversa_id, direcao, texto, criado_em, "
                            "autor, tipo) VALUES (%s, 'out', 'Oi, aqui é a Ana.', %s, "
                            "'ANA EXEMPLO', 'text')", (cid, "2026-10-26T10:10:00"))
    assert COBRANCA.cobrar(db, agora="2026-10-26T12:00:00") == 0
    _cid2, outro = _pedido(db, casa, "quero uma procuração", "procuracao", meta="wamid.p2")
    with db.transaction() as con:
        banco(con).escrever("UPDATE tasks SET status='EM_ANDAMENTO' WHERE source_ref=%s",
                            (f"wa_pedido:{outro['id']}",))
    assert COBRANCA.cobrar(db, agora="2026-10-26T12:00:00") == 0


# ---------------------------------------------------------------- o protocolo


def test_o_pedido_ligado_ao_protocolo_mostra_a_situacao_a_ia(casa, monkeypatch):
    db = casa["db"]
    _ligar(db)
    cid, pedido = _pedido(db, casa)
    _protocolo(db, "2026.11.7")
    with db.transaction() as con:
        try:
            PEDIDO.vincular_protocolo(con, pedido["id"], "9999.99.9", por="ANA", quando=AGORA)
            assert False, "ligou a protocolo que não existe"
        except PEDIDO.PedidoErro as erro:
            assert "Não há protocolo" in str(erro)
    with db.transaction() as con:
        r = PEDIDO.vincular_protocolo(con, pedido["id"], "2026.11.7", por="ANA", quando=AGORA)
    assert r["numero"] == "2026.11.7"
    monkeypatch.setattr(WE, "retrato_do_protocolo", lambda con, numero, hoje: {
        "numero": numero, "situacao_publica": "Em atendimento", "atribuicao": "Registro de Imóveis"})
    conversa = dict(_um(db, "SELECT * FROM wa_conversa WHERE id=%s", (cid,)))
    estado = WE.estado(db, conversa, agora=AGORA, rotina={}, arquivos=0)
    assert "Protocolo do Caixa ligado pelo escrevente a este pedido" in estado
    assert "situação «Em atendimento»" in estado
    # o de protesto (ou ilegível) não mostra situação
    monkeypatch.setattr(WE, "retrato_do_protocolo", lambda con, numero, hoje: None)
    estado = WE.estado(db, conversa, agora=AGORA, rotina={}, arquivos=0)
    assert "não se informa por aqui" in estado and "Em atendimento" not in estado


# ---------------------------------------------------------------- os anexos


def test_o_arquivo_vai_em_copia_a_tarefa_e_ao_protocolo(casa, tmp_path):
    db = casa["db"]
    _ligar(db)
    ana = _usuario(db, "ana", "ANA EXEMPLO")
    cid, pedido = _pedido(db, casa)
    mid, original = _arquivo(db, cid, tmp_path)
    raiz = tmp_path / "arquivos"
    r = ANEXOS.anexar(db, mid, pedido["id"], destino="tarefa", usuario_id=ana, raiz=raiz,
                      agora=AGORA)
    anexo = _um(db, "SELECT * FROM attachments WHERE id=%s", (r["anexo_id"],))
    assert anexo["entity_type"] == "TASK" and anexo["original_name"] == "escritura.pdf"
    assert Path(anexo["stored_path"]).read_bytes() == PDF
    assert Path(anexo["stored_path"]) != original
    Path(anexo["stored_path"]).unlink()                 # apagar a cópia não toca o original
    assert original.read_bytes() == PDF
    # ao protocolo, só depois de ligado
    try:
        ANEXOS.anexar(db, mid, pedido["id"], destino="protocolo", usuario_id=ana, raiz=raiz,
                      agora=AGORA)
        assert False, "anexou sem protocolo ligado"
    except ANEXOS.AnexoErro as erro:
        assert "Ligue o pedido" in str(erro)
    pid = _protocolo(db)
    with db.transaction() as con:
        PEDIDO.vincular_protocolo(con, pedido["id"], "2026.11.7", por="ANA", quando=AGORA)
    r = ANEXOS.anexar(db, mid, pedido["id"], destino="protocolo", usuario_id=ana, raiz=raiz,
                      agora=AGORA)
    anexo = _um(db, "SELECT * FROM attachments WHERE id=%s", (r["anexo_id"],))
    assert (anexo["entity_type"], anexo["entity_id"]) == ("PROTOCOLO", pid)
    assert "qualificacao" in anexo["stored_path"]


def test_o_protocolo_recusa_o_que_nao_e_pdf_nem_imagem(casa, tmp_path):
    db = casa["db"]
    _ligar(db)
    ana = _usuario(db, "ana", "ANA EXEMPLO")
    cid, pedido = _pedido(db, casa)
    _protocolo(db)
    with db.transaction() as con:
        PEDIDO.vincular_protocolo(con, pedido["id"], "2026.11.7", por="ANA", quando=AGORA)
    mid, _ = _arquivo(db, cid, tmp_path, dados=b"MZ\x90\x00 executavel", nome="nota.pdf")
    try:
        ANEXOS.anexar(db, mid, pedido["id"], destino="protocolo", usuario_id=ana,
                      raiz=tmp_path / "arquivos", agora=AGORA)
        assert False, "aceitou um executável com nome de PDF"
    except ANEXOS.AnexoErro as erro:
        assert "não é PDF" in str(erro)
    assert not list((tmp_path / "arquivos").rglob("nota*.pdf"))


def test_a_tela_liga_o_protocolo_e_anexa_e_o_auditor_nao(casa, tmp_path):
    db, app = casa["db"], casa["app"]
    _ligar(db)
    _usuario(db, "beatriz", "BEATRIZ EXEMPLO")
    _usuario(db, "auditor", "AUDITOR EXEMPLO", "AUDITOR")
    cid, pedido = _pedido(db, casa)
    mid, _ = _arquivo(db, cid, tmp_path)
    _protocolo(db)
    beatriz = _entrar(app, "beatriz")
    tela = beatriz.get(f"/whatsapp/{cid}").get_data(as_text=True)
    assert "data-wa-pedido-protocolo" in tela and "data-wa-anexar" in tela
    r = beatriz.post(f"/whatsapp/pedido/{pedido['id']}/protocolo",
                     data={"csrf_token": _token(tela), "numero": "2026.11.7", "volta": str(cid)})
    assert r.status_code in (302, 303)
    assert _um(db, "SELECT protocolo_id FROM wa_pedido WHERE id=%s",
               (pedido["id"],))["protocolo_id"]
    r = beatriz.post(f"/whatsapp/midia/{mid}/anexar",
                     data={"csrf_token": _token(tela), "pedido_id": str(pedido["id"]),
                           "destino": "tarefa", "volta": str(cid)})
    assert r.status_code in (302, 303)
    assert _um(db, "SELECT count(*) AS n FROM attachments WHERE entity_type='TASK'")["n"] == 1
    auditor = _entrar(app, "auditor")
    tela = auditor.get(f"/whatsapp/{cid}").get_data(as_text=True)
    r = auditor.post(f"/whatsapp/midia/{mid}/anexar",
                     data={"csrf_token": _token(tela), "pedido_id": str(pedido["id"]),
                           "destino": "tarefa"})
    assert r.status_code == 403
