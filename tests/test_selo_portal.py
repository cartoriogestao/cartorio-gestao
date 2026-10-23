# -*- coding: utf-8 -*-
"""O que a casa deve ao Portal do Selo — LG07, 19/10/2026.

    «Selo cancelado/inutilizado: o oficial comunica à mão e pede o
     cancelamento de TODOS.» · «no portal do selo é preciso enviar o
     comprovante da gratuidade PARA CADA SELO»

Nenhum dado de pessoa real: números de selo com o CNS genérico (000000) e
nomes de exemplo. Não há rede: o Portal não tem API no código, e o módulo
só monta a lista, o ofício e o pacote.
"""
from __future__ import annotations

import csv
import io
import re
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402
from conftest import cg_login  # noqa: E402

import gratuidade_comprovante as GC  # noqa: E402
import selo_portal as SP  # noqa: E402
from bd_nativo import banco  # noqa: E402
from selador_config import init_selador_schema  # noqa: E402

TELAS = Path(__file__).resolve().parents[1] / "templates"
ISENTO = ("Poder Judiciário – TJMA. Selo: {n}, 15/10/2026 10:00:00, Ato: 14.4.1, "
          "Total R$ 0,00 Selo Isento, Consulte em https://selo.tjma.jus.br")
PAGO = "Poder Judiciário – TJMA. Selo: {n}, Total R$ 53,58"
ESCREVENTE = "BEATRIZ EXEMPLO DE SOUZA"


def _selo(con, numero, *, texto=ISENTO, obtido_em="2026-10-15T10:00:00", obtido_por=ESCREVENTE,
          cancelado_em=None, motivo=None) -> int:
    return int(banco(con).escrever(
        "INSERT INTO sd_selos (numero, texto, atribuicao, obtido_em, obtido_por, cancelado_em, "
        "motivo_cancelamento, ambiente) VALUES (%s, %s, 'RCPN', %s, %s, %s, %s, 'PRODUCAO') "
        "RETURNING id",
        (numero, texto.format(n=numero), obtido_em, obtido_por, cancelado_em, motivo))[0]["id"])


def _pdf(texto: str, paginas: int = 1) -> bytes:
    fitz = SP._pymupdf()
    doc = fitz.open()
    for _ in range(paginas):
        doc.new_page().insert_text((72, 72), texto)
    return doc.tobytes()


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), "white").save(buf, format="PNG")
    return buf.getvalue()


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


@pytest.fixture
def db(cg_casa):
    return cg_casa["db"]


# ------------------------------------------------------- o cancelamento


def test_o_cancelado_nao_comunicado_vira_aviso_e_so_sai_quando_o_oficio_e_comunicado(db):
    with db.transaction() as con:
        _selo(con, "AVERBA000000CANC0000000001", texto=PAGO, cancelado_em="2026-10-19T09:00:00",
              motivo="Ato refeito por erro de digitação")
        _selo(con, "AVERBA000000CANC0000000002", texto=PAGO)  # não cancelado
        _selo(con, "AVERBA000000CANC0000000003", texto=PAGO, cancelado_em="2026-09-01 10:00:00",
              motivo="Cancelado antes do aviso existir")
        assert SP.nao_comunicados(con)["n"] == 1   # o de setembro é anterior ao «desde»
        novo = SP.gerar_oficio(con, inicio="2026-10-19", fim="2026-10-19", agora="t", usuario="x")
        assert SP.nao_comunicados(con)["n"] == 1   # gerar o papel não é comunicar
        SP.marcar_comunicado(con, novo, agora="2026-10-19T15:00:00", protocolo="MALOTE 123")
        assert SP.nao_comunicados(con) == {"n": 0, "mais_antigo": ""}


def test_o_oficio_leva_todos_os_cancelados_do_periodo_e_nenhum_selo_vai_em_dois_oficios(db):
    with db.transaction() as con:
        a = _selo(con, "AVERBA000000CANC0000000011", texto=PAGO, cancelado_em="2026-10-19T09:00:00")
        b = _selo(con, "AVERBA000000CANC0000000012", texto=PAGO, cancelado_em="2026-09-01 10:00:00")
        primeiro = SP.gerar_oficio(con, inicio="2026-09-01", fim="2026-10-19", agora="t")
        assert [i["id"] for i in SP.remessa(con, primeiro)["itens"]] == [b, a]
        with pytest.raises(SP.PortalError, match="falta pedir"):
            SP.gerar_oficio(con, inicio="2026-09-01", fim="2026-10-19", agora="t")
        c = _selo(con, "AVERBA000000CANC0000000013", texto=PAGO, cancelado_em="2026-10-19T11:00:00")
        segundo = SP.gerar_oficio(con, inicio="2026-09-01", fim="2026-10-19", agora="t")
        assert [i["id"] for i in SP.remessa(con, segundo)["itens"]] == [c]


def test_o_ultimo_dia_do_periodo_entra_nos_dois_formatos_de_data_do_razao(db):
    with db.transaction() as con:
        _selo(con, "AVERBA000000CANC0000000021", texto=PAGO, cancelado_em="2026-10-21 14:21:03")
        _selo(con, "AVERBA000000CANC0000000022", texto=PAGO, cancelado_em="2026-10-21T09:00:00")
        _selo(con, "AVERBA000000CANC0000000023", texto=PAGO, cancelado_em="2026-10-22T00:00:00")
        numeros = [s["numero"] for s in SP.cancelados(con, inicio="2026-10-21", fim="2026-10-21")]
    assert numeros == ["AVERBA000000CANC0000000021", "AVERBA000000CANC0000000022"]


def test_o_rascunho_se_descarta_e_o_comunicado_nao_se_desfaz_nem_se_marca_duas_vezes(db):
    with db.transaction() as con:
        _selo(con, "AVERBA000000CANC0000000031", texto=PAGO, cancelado_em="2026-10-19T09:00:00")
        rascunho = SP.gerar_oficio(con, inicio="2026-10-19", fim="2026-10-19", agora="t")
        assert SP.descartar(con, rascunho) == SP.CANCELAMENTO
        assert [s["pedido"] for s in SP.cancelados(con, inicio="2026-10-19", fim="2026-10-19")] \
            == ["NAO_PEDIDO"]
        novo = SP.gerar_oficio(con, inicio="2026-10-19", fim="2026-10-19", agora="t")
        SP.marcar_comunicado(con, novo, agora="t2")
        with pytest.raises(SP.PortalError, match="já foi marcada"):
            SP.marcar_comunicado(con, novo, agora="t3")
        with pytest.raises(SP.PortalError, match="não se desfaz"):
            SP.descartar(con, novo)
        assert [s["pedido"] for s in SP.cancelados(con, inicio="2026-10-19", fim="2026-10-19")] \
            == ["COMUNICADO"]


def test_periodo_sem_data_ou_invertido_e_recusado_com_frase(db):
    with db.connect() as con:
        with pytest.raises(SP.PortalError, match="duas datas"):
            SP.cancelados(con, inicio="", fim="2026-10-19")
        with pytest.raises(SP.PortalError, match="depois do fim"):
            SP.cancelados(con, inicio="2026-10-20", fim="2026-10-19")


# --------------------------------------------------- a gratuidade


def test_a_fila_diz_por_selo_gratuito_o_que_falta_para_o_portal(db, tmp_path):
    with db.transaction() as con:
        um = _selo(con, "AVERBA000000GRAT0000000001")
        dois = _selo(con, "AVERBA000000GRAT0000000002")
        tres = _selo(con, "AVERBA000000GRAT0000000003")
        _selo(con, "AVERBA000000GRAT0000000004", texto=PAGO)                       # pago
        _selo(con, "AVERBA000000GRAT0000000005", cancelado_em="2026-10-16T10:00:00")  # cancelado
        SP.guardar_peca(con, um, peca="COMPROVANTE", tipo_comprovante="DECLARACAO_POBREZA",
                        nome_arquivo="declaracao.pdf", conteudo=_pdf("comprovante"),
                        pasta=tmp_path, usuario_id=None, agora="t")
        SP.guardar_peca(con, dois, peca="AMBOS", tipo_comprovante="DECISAO_JUDICIAL",
                        nome_arquivo="tudo.pdf", conteudo=_pdf("os dois"), pasta=tmp_path,
                        usuario_id=None, agora="t")
        fila = {s["id"]: s["situacao"] for s in SP.gratuitos(con)}
        assert fila == {um: "FALTA_CERTIDAO", dois: "PRONTO", tres: "FALTAM_OS_DOIS"}
        SP.guardar_peca(con, um, peca="CERTIDAO", nome_arquivo="certidao.pdf",
                        conteudo=_pdf("certidão"), pasta=tmp_path, usuario_id=None, agora="t")
        assert [s["id"] for s in SP.gratuitos(con, situacao="FALTANDO")] == [tres]
        assert [s["id"] for s in SP.gratuitos(con, situacao="PRONTO")] == [um, dois]


def test_a_certidao_sozinha_nao_apaga_o_aviso_do_escrevente_e_o_comprovante_apaga(db, tmp_path):
    with db.transaction() as con:
        selo = _selo(con, "AVERBA000000GRAT0000000011")
        SP.guardar_peca(con, selo, peca="CERTIDAO", nome_arquivo="certidao.pdf",
                        conteudo=_pdf("certidão"), pasta=tmp_path, usuario_id=None, agora="t")
        assert [p["id"] for p in GC.pendentes(con, nome=ESCREVENTE)] == [selo]
        SP.guardar_peca(con, selo, peca="COMPROVANTE", tipo_comprovante="DECLARACAO_POBREZA",
                        nome_arquivo="declaracao.pdf", conteudo=_pdf("comprovante"),
                        pasta=tmp_path, usuario_id=None, agora="t")
        assert GC.pendentes(con, nome=ESCREVENTE) == []


def test_o_comprovante_guardado_antes_desta_versao_conta_e_pode_ser_marcado_com_os_dois(db, tmp_path):
    with db.transaction() as con:
        selo = _selo(con, "AVERBA000000GRAT0000000021")
        aid = GC.guardar(con, selo, nome_arquivo="antigo.pdf", conteudo=_pdf("antigo"),
                         pasta=tmp_path, usuario_id=None, agora="t")
        assert [s["situacao"] for s in SP.gratuitos(con)] == ["FALTA_CERTIDAO"]
        with pytest.raises(SP.PortalError, match="entrou como comprovante"):
            SP.classificar(con, aid, peca="CERTIDAO", agora="t")
        assert SP.classificar(con, aid, peca="AMBOS", tipo_comprovante="OUTRO", agora="t") == selo
        assert [s["situacao"] for s in SP.gratuitos(con)] == ["PRONTO"]


def test_selo_pago_tipo_faltando_e_arquivo_estranho_sao_recusados(db, tmp_path):
    with db.transaction() as con:
        pago = _selo(con, "AVERBA000000GRAT0000000031", texto=PAGO)
        isento = _selo(con, "AVERBA000000GRAT0000000032")
        with pytest.raises(SP.PortalError, match="não é de ato gratuito"):
            SP.guardar_peca(con, pago, peca="CERTIDAO", nome_arquivo="c.pdf", conteudo=b"%PDF",
                            pasta=tmp_path, usuario_id=None, agora="t")
        with pytest.raises(SP.PortalError, match="tipo do comprovante"):
            SP.guardar_peca(con, isento, peca="COMPROVANTE", nome_arquivo="c.pdf",
                            conteudo=b"%PDF", pasta=tmp_path, usuario_id=None, agora="t")
        with pytest.raises(SP.PortalError, match="PDF ou imagem"):
            SP.guardar_peca(con, isento, peca="CERTIDAO", nome_arquivo="c.exe", conteudo=b"x",
                            pasta=tmp_path, usuario_id=None, agora="t")


def test_o_pacote_traz_um_pdf_por_selo_com_o_numero_no_nome_e_a_lista_sem_o_escrevente(db, tmp_path):
    with db.transaction() as con:
        um = _selo(con, "AVERBA000000GRAT0000000041")
        dois = _selo(con, "AVERBA000000GRAT0000000042")
        falta = _selo(con, "AVERBA000000GRAT0000000043")
        SP.guardar_peca(con, um, peca="COMPROVANTE", tipo_comprovante="DECLARACAO_POBREZA",
                        nome_arquivo="declaracao.pdf", conteudo=_pdf("comprovante", 2),
                        pasta=tmp_path, usuario_id=None, agora="t")
        SP.guardar_peca(con, um, peca="CERTIDAO", nome_arquivo="certidao.png", conteudo=_png(),
                        pasta=tmp_path, usuario_id=None, agora="t")
        SP.guardar_peca(con, dois, peca="AMBOS", tipo_comprovante="GRATUIDADE_LEGAL",
                        nome_arquivo="tudo.pdf", conteudo=_pdf("os dois"), pasta=tmp_path,
                        usuario_id=None, agora="t")
        novo = SP.gerar_pacote(con, inicio="2026-10-13", fim="2026-10-19", agora="t")
        assert [i["id"] for i in SP.remessa(con, novo)["itens"]] == [um, dois]
        assert [s["id"] for s in SP.gratuitos(con, situacao="FALTANDO")] == [falta]
        corpo = SP.montar_pacote(con, novo)
    zf = zipfile.ZipFile(io.BytesIO(corpo))
    assert sorted(zf.namelist()) == ["AVERBA000000GRAT0000000041.pdf",
                                     "AVERBA000000GRAT0000000042.pdf", "lista.csv"]
    fitz = SP._pymupdf()
    assert fitz.open(stream=zf.read("AVERBA000000GRAT0000000041.pdf"), filetype="pdf").page_count == 3
    lista = zf.read("lista.csv").decode("utf-8-sig")
    linhas = list(csv.reader(io.StringIO(lista), delimiter=";"))
    assert [l[0] for l in linhas[1:]] == ["AVERBA000000GRAT0000000041", "AVERBA000000GRAT0000000042"]
    assert "Declaração de pobreza" in lista and ESCREVENTE.lower() not in lista.lower()


def test_arquivo_que_nao_abre_recusa_o_pacote_dizendo_qual_e(db, tmp_path):
    with db.transaction() as con:
        selo = _selo(con, "AVERBA000000GRAT0000000051")
        SP.guardar_peca(con, selo, peca="AMBOS", tipo_comprovante="OUTRO",
                        nome_arquivo="quebrado.pdf", conteudo=b"isto nao e pdf",
                        pasta=tmp_path, usuario_id=None, agora="t")
        novo = SP.gerar_pacote(con, inicio="2026-10-13", fim="2026-10-19", agora="t")
        with pytest.raises(SP.PortalError, match="quebrado.pdf"):
            SP.montar_pacote(con, novo)


def test_o_pacote_vazio_e_recusado_e_o_selo_no_pacote_nao_volta_a_fila_de_prontos(db, tmp_path):
    with db.transaction() as con:
        with pytest.raises(SP.PortalError, match="Nenhum selo gratuito"):
            SP.gerar_pacote(con, inicio="2026-10-13", fim="2026-10-19", agora="t")
        selo = _selo(con, "AVERBA000000GRAT0000000061")
        SP.guardar_peca(con, selo, peca="AMBOS", tipo_comprovante="OUTRO", nome_arquivo="t.pdf",
                        conteudo=_pdf("x"), pasta=tmp_path, usuario_id=None, agora="t")
        novo = SP.gerar_pacote(con, inicio="2026-10-13", fim="2026-10-19", agora="t")
        assert [s["situacao"] for s in SP.gratuitos(con)] == ["NO_PACOTE"]
        SP.marcar_comunicado(con, novo, agora="t2", protocolo="PORTAL 9")
        assert [s["situacao"] for s in SP.gratuitos(con)] == ["ENVIADO"]


# ------------------------------------------------------------- o esquema


def test_o_esquema_e_idempotente_e_devolve_o_indice_a_tabela_que_ja_existe():
    con = conexao_de_teste()
    try:
        bd = banco(con)
        bd.escrever("CREATE TABLE IF NOT EXISTS attachments (id bigint GENERATED BY DEFAULT AS "
                    "IDENTITY PRIMARY KEY, entity_type TEXT, entity_id bigint)")
        init_selador_schema(con)
        SP.init_selo_portal_schema(con)
        bd.escrever("DROP INDEX ix_sd_portal_itens_remessa")
        SP.init_selo_portal_schema(con)
        assert bd.tem_tabela("ix_sd_portal_itens_remessa")
        assert bd.tem_tabela("sd_gratuidade_pecas")
    finally:
        con.close()


@pytest.mark.parametrize("tela", ["selo_cancelamentos.html", "selo_gratuidades_portal.html",
                                  "selo_portal_remessa.html"])
def test_as_telas_do_portal_do_selo_mandam_o_token_em_todo_formulario(tela):
    html = (TELAS / tela).read_text(encoding="utf-8")
    corpos = re.findall(r"<form\b[^>]*method=\"post\"[^>]*>(.*?)</form>", html, re.S | re.I)
    assert corpos, f"{tela} deixou de ter formulário"
    assert all('name="csrf_token"' in c for c in corpos), f"{tela} esqueceu o token"


# --------------------------------------------------------------- as telas


def _acoes(db) -> list[str]:
    with db.connect() as con:
        return [r["action"] for r in banco(con).ler("SELECT action FROM audit_logs ORDER BY id")]


def test_o_gestor_ve_o_aviso_gera_o_oficio_marca_comunicado_e_tudo_fica_no_rastro(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    with db.transaction() as con:
        _selo(con, "AVERBA000000TELA0000000001", texto=PAGO, cancelado_em="2026-10-19T09:00:00",
              motivo="Ato refeito por erro de digitação")
    html = c.get("/selos/cancelamentos?inicio=2026-10-19&fim=2026-10-19").get_data(as_text=True)
    assert "1 selo(s) cancelado(s) ainda não comunicado(s) ao TJMA" in html
    assert "AVERBA000000TELA0000000001" in html and "Não pedido" in html
    r = c.post("/selos/cancelamentos/oficio", data={"csrf_token": _token(html),
               "inicio": "2026-10-19", "fim": "2026-10-19"})
    assert r.status_code == 302 and "/selos/portal/remessa/" in r.headers["Location"]
    oficio = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "Pedido de cancelamento de selos" in oficio and "Ato refeito por erro" in oficio
    assert "arts. 134 e 135" in oficio
    remessa_id = int(r.headers["Location"].rstrip("/").split("/")[-1])
    lista = c.get(f"/selos/portal/remessa/{remessa_id}/lista.csv")
    assert lista.status_code == 200 and b"AVERBA000000TELA0000000001" in lista.data
    c.post(f"/selos/portal/remessa/{remessa_id}/comunicado",
           data={"csrf_token": _token(oficio), "protocolo": "MALOTE 77"})
    depois = c.get("/selos/cancelamentos?inicio=2026-10-19&fim=2026-10-19").get_data(as_text=True)
    assert "ainda não comunicado(s) ao TJMA" not in depois and "Comunicado em" in depois
    acoes = _acoes(db)
    assert "SELO_CANCELAMENTO_OFICIO_GERADO" in acoes and "SELO_PORTAL_REMESSA_COMUNICADA" in acoes


def test_post_sem_token_e_recusado(cg_casa_logada):
    c = cg_casa_logada["c"]
    r = c.post("/selos/cancelamentos/oficio", data={"inicio": "2026-10-19", "fim": "2026-10-19"})
    assert r.status_code == 400


def test_as_telas_so_leem_nenhum_get_grava_rastro_nem_remessa(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    with db.transaction() as con:
        _selo(con, "AVERBA000000TELA0000000011", texto=PAGO, cancelado_em="2026-10-19T09:00:00")
        _selo(con, "AVERBA000000TELA0000000012")
    antes = _acoes(db)
    assert c.get("/selos/cancelamentos").status_code == 200
    assert c.get("/selos/gratuidades-portal").status_code == 200
    assert c.get("/selos/gratuidades-portal?situacao=TODAS").status_code == 200
    assert _acoes(db) == antes
    with db.connect() as con:
        assert banco(con).valor("SELECT count(*) FROM sd_portal_remessas") == 0


def test_o_pacote_se_baixa_por_post_e_fica_no_rastro(cg_casa_logada, tmp_path):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    with db.transaction() as con:
        selo = _selo(con, "AVERBA000000TELA0000000021")
    fila = c.get("/selos/gratuidades-portal").get_data(as_text=True)
    assert "AVERBA000000TELA0000000021" in fila and "Falta o comprovante e a certidão" in fila
    r = c.post(f"/selos/gratuidades-portal/{selo}/peca",
               data={"csrf_token": _token(fila), "peca": "AMBOS", "tipo": "DECLARACAO_POBREZA",
                     "arquivo": (io.BytesIO(_pdf("os dois")), "tudo.pdf")},
               content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "1 arquivo(s) guardado(s)" in r
    r = c.post("/selos/gratuidades-portal/pacote", data={"csrf_token": _token(r),
               "inicio": "2026-10-13", "fim": "2026-10-19"})
    assert r.status_code == 302
    pagina = c.get(r.headers["Location"]).get_data(as_text=True)
    remessa_id = int(r.headers["Location"].rstrip("/").split("/")[-1])
    assert c.get(f"/selos/portal/remessa/{remessa_id}/pacote").status_code == 405
    z = c.post(f"/selos/portal/remessa/{remessa_id}/pacote", data={"csrf_token": _token(pagina)})
    assert z.status_code == 200 and z.mimetype == "application/zip"
    assert zipfile.ZipFile(io.BytesIO(z.data)).namelist()[0] == "AVERBA000000TELA0000000021.pdf"
    acoes = _acoes(db)
    assert {"SELO_GRATUIDADE_PECA_GUARDADA", "SELO_GRATUIDADE_PACOTE_GERADO",
            "SELO_GRATUIDADE_PACOTE_BAIXADO"} <= set(acoes)


def test_o_escrevente_ve_so_os_selos_dele_guarda_a_certidao_e_nao_gera_oficio_nem_pacote(cg_casa):
    c, db = cg_casa["c"], cg_casa["db"]
    db.create_user("beatriz", ESCREVENTE, "Senha#12345", "USER")
    with db.transaction() as con:
        meu = _selo(con, "AVERBA000000TELA0000000031")
        _selo(con, "AVERBA000000TELA0000000032", obtido_por="CARLA EXEMPLO LIMA")
        _selo(con, "AVERBA000000TELA0000000033", texto=PAGO, cancelado_em="2026-10-19T09:00:00")
    cg_login(c, "beatriz", "Senha#12345")
    fila = c.get("/selos/gratuidades-portal").get_data(as_text=True)
    assert "AVERBA000000TELA0000000031" in fila and "AVERBA000000TELA0000000032" not in fila
    assert "ainda não comunicado(s) ao TJMA" not in fila   # o aviso é do gestor
    tok = _token(fila)
    r = c.post(f"/selos/gratuidades-portal/{meu}/peca",
               data={"csrf_token": tok, "peca": "CERTIDAO",
                     "arquivo": (io.BytesIO(_pdf("certidão")), "certidao.pdf")},
               content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "1 arquivo(s) guardado(s)" in r
    assert c.get("/selos/cancelamentos").status_code == 403
    assert c.post("/selos/cancelamentos/oficio", data={"csrf_token": tok, "inicio": "2026-10-19",
                  "fim": "2026-10-19"}).status_code == 403
    assert c.post("/selos/gratuidades-portal/pacote", data={"csrf_token": tok, "inicio": "2026-10-13",
                  "fim": "2026-10-19"}).status_code == 403
