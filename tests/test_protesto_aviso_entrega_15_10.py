"""A entrega do aviso, o comprovante, e o caminho Resolve → edital — 15/10/2026.

Pedido do oficial: «lugar de upload das intimações dos títulos entregues e
botão para avisar que não pode ser entregue (seja por ser fora da zona de
entrega ou por negativa em receber), possibilitando mandar para intimação pela
Resolve e, não rolando pela Resolve, por edital». A rede é simulada.
"""
from __future__ import annotations

import io
import json

import centrais_cred as CRED
from test_protesto_aviso_web import (_con, _token, aviso_id, emitir,  # noqa: F401
                                     registrar, s, titulo_apontado)

PDF = b"%PDF-1.4\n% comprovante de teste\n%%EOF\n"
CHAVE = "21999990141243301260417"


def _com_chave(s, tid: int) -> None:
    con = _con(s)
    with con:
        con.execute("UPDATE pt_titulos SET chave_cenprot=? WHERE id=?",
                    (CHAVE, tid))


def _na_resolve(s, tid: int, estado: str) -> None:
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO rs_intimacoes(titulo_id, ambiente, lote_id,
                   intimacao_id, identificador, teor, resumo, enviada_em,
                   estado, estado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (tid, CRED.PRODUCAO, "L1", "I1", f"P{tid}-1", "{}", "",
             "2026-10-15T09:00:00", estado, "2026-10-15T10:00:00"))


def _nao_entregue(s, motivo="14"):
    tid = titulo_apontado(s)
    emitir(s, tid)
    aid = aviso_id(s)
    registrar(s, aid, entregue="0", motivo=motivo)
    return tid, aid


def _edital(s, aid, **extra):
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    dados = {"csrf_token": _token(tela)}
    dados.update(extra)
    return s["c"].post(f"/protesto/avisos/{aid}/edital", data=dados,
                       follow_redirects=True).get_data(as_text=True)


# ------------------------------------------------------------ os dois botões


def test_a_tela_tem_os_dois_botoes_e_os_motivos_do_pedido_primeiro(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    html = s["c"].get("/protesto/avisos").get_data(as_text=True)
    assert "Entregue — lavrar a intimação" in html
    assert "Não pôde ser entregue" in html
    i_zona = html.index("Fora da zona de entrega")
    i_recusa = html.index("Recusou-se a receber")
    i_ausente = html.index(">Ausente<")
    assert i_zona < i_recusa < i_ausente


def test_fora_da_zona_nao_intima_e_vai_ao_proximo_passo(s):
    tid, aid = _nao_entregue(s, motivo="14")
    con = _con(s)
    assert tuple(con.execute("SELECT situacao, motivo FROM pt_avisos WHERE id=?",
                       (aid,)).fetchone()) == ("NAO_ENTREGUE", 14)
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "APONTADO"
    html = s["c"].get("/protesto/avisos").get_data(as_text=True)
    assert "Resolve, e depois edital" in html


# --------------------------------------------- o caminho Resolve → edital


def test_sem_chave_a_resolve_nao_serve_e_o_edital_sai_direto(s):
    tid, aid = _nao_entregue(s)
    html = _edital(s, aid)
    assert "intimação por edital foi lavrada" in html
    detalhe = json.loads(_con(s).execute(
        "SELECT detalhe_json FROM pt_atos WHERE titulo_id=? AND tipo="
        "'INTIMACAO'", (tid,)).fetchone()[0])
    assert "Intimação Digital: não se aplica" in detalhe["comprovante"]


def test_com_chave_e_sem_tentar_a_resolve_o_edital_pede_o_motivo(s):
    tid, aid = _nao_entregue(s, motivo="3")
    _com_chave(s, tid)
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    assert "Intimar pela Resolve" in tela
    html = _edital(s, aid)
    assert "escreva o motivo" in html
    assert _con(s).execute("SELECT COUNT(*) FROM pt_editais").fetchone()[0] == 0

    html = _edital(s, aid, justificativa="devedor sem e-mail nem telefone")
    assert "intimação por edital foi lavrada" in html
    detalhe = json.loads(_con(s).execute(
        "SELECT detalhe_json FROM pt_atos WHERE titulo_id=? AND tipo="
        "'INTIMACAO'", (tid,)).fetchone()[0])
    assert "não tentada; motivo: devedor sem e-mail" in detalhe["comprovante"]


def test_resolve_em_curso_o_edital_espera_ou_vai_com_motivo(s):
    tid, aid = _nao_entregue(s)
    _com_chave(s, tid)
    _na_resolve(s, tid, "ENVIADO")
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    assert "foi enviada em 15/10/2026" in tela
    assert "Intimar pela Resolve" not in tela
    assert "escreva o motivo" in _edital(s, aid)


def test_resolve_que_nao_deu_libera_o_edital(s):
    tid, aid = _nao_entregue(s)
    _com_chave(s, tid)
    _na_resolve(s, tid, "SEM_RESPOSTA")
    assert "intimação por edital foi lavrada" in _edital(s, aid)


def test_resolve_confirmada_lavra_a_digital_e_recusa_o_edital(s):
    tid, aid = _nao_entregue(s)
    _com_chave(s, tid)
    _na_resolve(s, tid, "INTIMADO")
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    assert "Lavrar a intimação digital" in tela
    assert "o edital não cabe" in _edital(s, aid, justificativa="x" * 20)

    html = s["c"].post(f"/protesto/avisos/{aid}/digital",
                       data={"csrf_token": _token(tela)},
                       follow_redirects=True).get_data(as_text=True)
    assert "Intimação digital lavrada" in html
    con = _con(s)
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "INTIMADO"
    detalhe = json.loads(con.execute(
        "SELECT detalhe_json FROM pt_atos WHERE titulo_id=? AND tipo="
        "'INTIMACAO'", (tid,)).fetchone()[0])
    assert detalhe["digital"] is True and detalhe["modo"] == "PESSOAL"
    assert "921, § 6º, II" in detalhe["comprovante"]
    # o título intimado sai da lista do edital
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    assert "Lavrar a intimação digital" not in tela


def test_sem_confirmacao_a_digital_nao_se_lavra(s):
    tid, aid = _nao_entregue(s)
    _com_chave(s, tid)
    _na_resolve(s, tid, "ENVIADO")
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    html = s["c"].post(f"/protesto/avisos/{aid}/digital",
                       data={"csrf_token": _token(tela)},
                       follow_redirects=True).get_data(as_text=True)
    assert "ainda não confirmou" in html
    assert _con(s).execute("SELECT situacao FROM pt_titulos WHERE id=?",
                           (tid,)).fetchone()[0] == "APONTADO"


def test_o_botao_da_resolve_manda_o_titulo_do_aviso(s, monkeypatch):
    import resolve_intimacao as RS
    tid, aid = _nao_entregue(s)
    _com_chave(s, tid)
    pedidos = []

    def falso(db, ids, **k):
        pedidos.append(list(ids))
        return {"mandadas": 1, "gravadas": 1, "lote_id": "L9"}
    monkeypatch.setattr(RS, "enviar", falso)
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    html = s["c"].post(f"/protesto/avisos/{aid}/resolve",
                       data={"csrf_token": _token(tela)},
                       follow_redirects=True).get_data(as_text=True)
    assert pedidos == [[tid]]
    assert "Intimação Digital enviada" in html and "L9" in html


# ------------------------------------------------------------ o comprovante


def _entrega_com_arquivo(s, aid, nome, conteudo):
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    return s["c"].post(
        f"/protesto/avisos/{aid}/entrega",
        data={"csrf_token": _token(tela), "entregue": "1",
              "recebido_por": "JOSÉ DA SILVA",
              "comprovante": (io.BytesIO(conteudo), nome)},
        content_type="multipart/form-data",
        follow_redirects=True).get_data(as_text=True)


def test_entrega_com_comprovante_anexa_ao_aviso(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    aid = aviso_id(s)
    html = _entrega_com_arquivo(s, aid, "intimacao.pdf", PDF)
    assert "O comprovante ficou anexado" in html
    anexo = _con(s).execute(
        "SELECT * FROM attachments WHERE entity_type='PT_AVISO' "
        "AND entity_id=?", (aid,)).fetchone()
    assert anexo is not None and anexo["original_name"] == "intimacao.pdf"
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    assert f"/arquivo/{anexo['id']}/ver" in tela


def test_comprovante_que_nao_e_pdf_desfaz_a_entrega(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    aid = aviso_id(s)
    html = _entrega_com_arquivo(s, aid, "falso.pdf", b"MZ isto nao e pdf")
    assert "diz ser .pdf e não é" in html
    con = _con(s)
    assert con.execute("SELECT situacao FROM pt_avisos WHERE id=?",
                       (aid,)).fetchone()[0] == "EMITIDO"
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "APONTADO"


def test_o_comprovante_pode_vir_depois_e_nao_se_repete(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    aid = aviso_id(s)
    registrar(s, aid, entregue="1", recebido_por="JOSÉ DA SILVA")
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    assert "falta o comprovante" in tela

    def anexar():
        t = s["c"].get("/protesto/avisos").get_data(as_text=True)
        return s["c"].post(
            f"/protesto/avisos/{aid}/comprovante",
            data={"csrf_token": _token(t),
                  "comprovante": (io.BytesIO(PDF), "ar.pdf")},
            content_type="multipart/form-data",
            follow_redirects=True).get_data(as_text=True)

    assert "Comprovante anexado" in anexar()
    assert "já está anexado" in anexar()
    assert _con(s).execute(
        "SELECT COUNT(*) FROM attachments WHERE entity_type='PT_AVISO'"
    ).fetchone()[0] == 1


def test_aviso_sem_desfecho_nao_recebe_comprovante(s):
    """O comprovante é da entrega OU da tentativa (15/10/2026) — o aviso que
    nem teve desfecho registrado não recebe."""
    tid = titulo_apontado(s)
    emitir(s, tid)
    aid = aviso_id(s)
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    html = s["c"].post(
        f"/protesto/avisos/{aid}/comprovante",
        data={"csrf_token": _token(tela),
              "comprovante": (io.BytesIO(PDF), "ar.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True).get_data(as_text=True)
    assert "registre o desfecho do aviso primeiro" in html
