"""Aceite pelo portal fica comprovado sem fingir resposta da API nem reenviar."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

import afirmacoes_expressas as AFX
import protesto_retorno as PRE
import protesto_retorno_manual as M
from bd_nativo import banco

AGORA = "2026-11-15T12:00:00"
NOTA = "Conferi no portal da CRA que este arquivo foi aceito integralmente."
PDF = b"%PDF-1.4\ncomprovante ficticio"


@pytest.fixture
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("conferente", "Operador Exemplo", "Senha#12345", "USER")
    db.set_settings({"modulo_protesto_ligado": "1"})
    return cg_casa


def _arquivo(db, tipo="SDTBFORTP", *, ato=True, cancelado=0):
    with db.transaction() as con:
        bd = banco(con)
        rid = bd.escrever("""INSERT INTO pt_retornos(tipo,apresentante_codigo,dia,
                nome_arquivo,conteudo,hash_arquivo,titulos,gerado_em)
            VALUES (%s,'001','2026-11-15','R0011511.261','ensaio','hash',1,%s) RETURNING id""",
            (tipo, AGORA))[0]["id"]
        if ato:
            tid = bd.escrever("""INSERT INTO pt_titulos(numero_titulo,especie,
                    valor_centavos,saldo_centavos,situacao,origem,criado_em)
                VALUES ('EXEMPLO','DMI',100,100,'PROTESTADO','CRA',%s) RETURNING id""", (AGORA,))[0]["id"]
            bd.escrever("""INSERT INTO pt_atos(titulo_id,tipo,data_ato,origem,
                    criado_em,retorno_id,cancelado)
                VALUES (%s,'PROTESTO',%s,'CRA',%s,%s,%s)""", (tid, AGORA, AGORA, rid, cancelado))
    return rid


def _registrar(db, rid, pasta, **kw):
    args = {"nome": "aceite.pdf", "conteudo": PDF, "pasta_de_arquivos": pasta,
            "agora": AGORA, "usuario": "conferente", "usuario_id": None,
            "afirmo": True, "afirmacao": NOTA}
    args.update(kw)
    with db.transaction() as con:
        return M.registrar(con, rid, **args)


@pytest.mark.parametrize("tipo", ["SDTBFORTP", "SDTBFOAND", "SDTBFOCRT"])
def test_guarda_prova_autoria_e_canal_sem_marcar_o_par(casa, tmp_path, tipo):
    db = casa["db"]
    rid = _arquivo(db, tipo, ato=tipo != "SDTBFOCRT")
    par = _arquivo(db)
    with db.transaction() as con:
        banco(con).escrever("UPDATE pt_retornos SET par_id=%s WHERE id=%s", (par, rid))
    r = _registrar(db, rid, tmp_path)
    with db.connect() as con:
        linha = PRE.retorno(con, rid)
        assert linha["cra_enviado_em"] == AGORA
        assert linha["cra_enviado_por"] == "conferente"
        dados = M.dados_do_envio(linha)
        assert dados["anexo_id"] == r["anexo_id"] and dados["afirmacao"].endswith(NOTA)
        anexo = banco(con).um("SELECT * FROM attachments WHERE id=%s", (r["anexo_id"],))
        assert anexo["entity_type"] == M.ENTIDADE
        assert Path(anexo["stored_path"]).read_bytes() == PDF
        assert PRE.retorno(con, par)["cra_enviado_em"] is None
    with pytest.raises(M.EnvioManualError, match="já tem envio"):
        _registrar(db, rid, tmp_path)


@pytest.mark.parametrize("kw", [{"afirmo": False}, {"afirmacao": "sim"}, {"robo": True}])
def test_declaracao_e_de_quem_conferiu(casa, tmp_path, kw):
    rid = _arquivo(casa["db"])
    with pytest.raises(AFX.AfirmacaoError):
        _registrar(casa["db"], rid, tmp_path, **kw)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("conteudo,nome", [(b"", "vazio.pdf"), (b"nao e pdf", "falso.pdf"), (PDF, "prova.exe")])
def test_recusa_comprovante_invalido(casa, tmp_path, conteudo, nome):
    rid = _arquivo(casa["db"])
    with pytest.raises(M.EnvioManualError, match="PDF"):
        _registrar(casa["db"], rid, tmp_path, conteudo=conteudo, nome=nome)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("ato,cancelado", [(False, 0), (True, 1)])
def test_arquivo_sem_atos_ou_com_ato_desfeito_nao_vira_informado(casa, tmp_path, ato, cancelado):
    rid = _arquivo(casa["db"], ato=ato, cancelado=cancelado)
    with pytest.raises(M.EnvioManualError, match="devolvidos"):
        _registrar(casa["db"], rid, tmp_path)


def test_recusa_anterior_fica_no_historico_do_novo_aceite(casa, tmp_path):
    db = casa["db"]
    rid = _arquivo(db)
    with db.transaction() as con:
        banco(con).escrever("UPDATE pt_retornos SET cra_recusado_em=%s,cra_recusa_codigo='2161' WHERE id=%s", (AGORA, rid))
    _registrar(db, rid, tmp_path)
    with db.connect() as con:
        linha = PRE.retorno(con, rid)
        assert linha["cra_recusado_em"] is None
        assert json.loads(linha["cra_envio_resumo"])["recusa_anterior"]["codigo"] == "2161"


def _token(client, rota="/login"):
    import re
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', client.get(rota).get_data(as_text=True)).group(1)


def test_escrevente_registra_no_fluxo_autenticado_e_com_auditoria(casa):
    db = casa["db"]
    rid = _arquivo(db)
    c = casa["app"].test_client()
    c.post("/login", data={"username": "conferente", "password": "Senha#12345", "csrf_token": _token(c)})
    resposta = c.post(f"/protesto/retornos/{rid}/comprovante-portal", data={
        "csrf_token": _token(c, "/protesto/retornos"), "afirmo": "1", "afirmacao": NOTA,
        "comprovante": (io.BytesIO(PDF), "aceite.pdf")}, follow_redirects=True)
    assert resposta.status_code == 200
    assert "aceite no portal registrado" in resposta.get_data(as_text=True)
    with db.connect() as con:
        registro = banco(con).um("SELECT * FROM audit_logs WHERE action='PROTESTO_CRA_ACEITE_PORTAL' AND entity_id=%s", (rid,))
        assert registro["username_snapshot"] == "conferente"


def test_rota_anonima_nao_registra_aceite(casa):
    rid = _arquivo(casa["db"])
    c = casa["app"].test_client()
    c.post(f"/protesto/retornos/{rid}/comprovante-portal", data={"afirmo": "1", "afirmacao": NOTA})
    with casa["db"].connect() as con:
        assert PRE.retorno(con, rid)["cra_enviado_em"] is None
