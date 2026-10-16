"""Documentos para qualificação no Protocolo Geral — relato #135, 15/10/2026.

A FRASE DO RELATO, aberto da tarefa 386 pela escrevente do RI e das Notas:

    «CRIAR NO PROTOCOLO GERAL OU EM NOTAS ABA DE ANEXAR DOCUMENTOS PARA FIM
     DE QUALIFICAÇÃO»

A tarefa 386 é um parecer de qualificação da prenotação 11.573, e os papéis
dela moravam numa pasta compartilhada, fora do sistema. Estes testes guardam:
o arquivo entra pela tela do protocolo (PDF/JPG/PNG, até 25 MB, com tipo),
sai com motivo e sem apagar, e aparece no ato que se liga ao protocolo — nas
Notas e na prenotação do RI.
"""
from __future__ import annotations

import io
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import protocolo_documentos as PDOC

PDF = b"%PDF-1.4\n%fake\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _protocolo(casa, numero="2026.10.90", atribuicao="NOTAS", situacao="ABERTO",
               ri_protocolo_id=None):
    con = _con(casa)
    cur = con.execute(
        """INSERT INTO cx_protocolos (numero, data_abertura, atribuicao,
               interessado, assunto, situacao, origem, criado_em, ri_protocolo_id)
           VALUES (?, '2026-10-15', ?, 'FULANO DE TAL', 'ESCRITURA', ?,
                   'MANUAL', '2026-10-15T09:00', ?)""",
        (numero, atribuicao, situacao, ri_protocolo_id))
    con.commit()
    pid = int(cur.lastrowid)
    con.close()
    return pid


def _ato_de_notas(casa, situacao="EM_LAVRATURA"):
    con = _con(casa)
    cur = con.execute(
        "INSERT INTO nt_atos (tipo, situacao, origem, data, criado_em) "
        "VALUES ('ESCRITURA', ?, 'MANUAL', '2026-10-15', '2026-10-15T09:00')",
        (situacao,))
    con.commit()
    aid = int(cur.lastrowid)
    con.close()
    return aid


def _anexar(casa, pid, arquivos, tipo="CERTIDAO", descricao="certidão de casamento"):
    c = casa["c"]
    tok = _token(c.get(f"/caixa/protocolos/{pid}").get_data(as_text=True))
    dados = {"csrf_token": tok, "tipo": tipo, "descricao": descricao,
             "documento": [(io.BytesIO(conteudo), nome) for nome, conteudo in arquivos]}
    return c.post(f"/caixa/protocolos/{pid}/documentos", data=dados,
                  content_type="multipart/form-data", follow_redirects=True)


def _linhas(casa, pid):
    con = _con(casa)
    try:
        return [dict(r) for r in con.execute(
            "SELECT * FROM attachments WHERE entity_type='PROTOCOLO' AND entity_id=? "
            "ORDER BY id", (pid,))]
    finally:
        con.close()


# ------------------------------------------------------------ o esquema


def test_as_colunas_novas_existem_e_a_migracao_e_idempotente(cg_casa_logada):
    con = _con(cg_casa_logada)
    try:
        PDOC.init_protocolo_documentos_schema(con)   # segunda vez: não estoura
        colunas = {r[1] for r in con.execute("PRAGMA table_info(attachments)")}
    finally:
        con.close()
    assert {"documento_tipo", "retirado_em", "retirado_por",
            "retirado_motivo"} <= colunas


# ------------------------------------------------------------ o arquivo


def test_so_entra_pdf_jpg_e_png_de_verdade():
    assert PDOC.conferir_arquivo("rg.pdf", PDF[:16], len(PDF)) == ".pdf"
    assert PDOC.conferir_arquivo("rg.PNG", PNG[:16], len(PNG)) == ".png"
    with pytest.raises(PDOC.DocumentoError, match="não é PDF"):
        PDOC.conferir_arquivo("planilha.xlsx", b"PK\x03\x04", 100)
    # Extensão de PDF com conteúdo de outra coisa: a extensão não prova nada.
    with pytest.raises(PDOC.DocumentoError, match="o conteúdo não é PDF"):
        PDOC.conferir_arquivo("rg.pdf", b"MZ\x90\x00", 100)


def test_o_teto_e_o_da_casa_25_mb():
    assert PDOC.LIMITE_POR_ARQUIVO == 25 * 1024 * 1024
    with pytest.raises(PDOC.DocumentoError, match="25 MB"):
        PDOC.conferir_arquivo("grande.pdf", PDF[:16], 26 * 1024 * 1024)


# ------------------------------------------------------------ a tela do protocolo


def test_a_tela_do_protocolo_tem_a_aba_de_documentos(cg_casa_logada):
    pid = _protocolo(cg_casa_logada)
    html = cg_casa_logada["c"].get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    assert 'id="documentos-qualificacao"' in html
    assert "Documentos para qualificação" in html
    assert "Procuração anterior" in html          # o tipo é escolha


def test_anexar_varios_de_uma_vez_com_tipo_quem_e_quando(cg_casa_logada):
    casa = cg_casa_logada
    pid = _protocolo(casa)
    r = _anexar(casa, pid, [("certidao.pdf", PDF), ("rg.png", PNG)])
    assert r.status_code == 200
    linhas = _linhas(casa, pid)
    assert len(linhas) == 2
    assert {x["documento_tipo"] for x in linhas} == {"CERTIDAO"}
    assert all(x["uploaded_by"] for x in linhas)
    # O arquivo mora na pasta que o backup varre, e não fora dela.
    for x in linhas:
        caminho = Path(x["stored_path"])
        assert caminho.exists()
        assert "protocolo" in caminho.parts and "qualificacao" in caminho.parts
    html = r.get_data(as_text=True)
    assert "certidao.pdf" in html and "MARIO EXEMPLO DOS SANTOS" in html
    con = _con(casa)
    try:
        aud = con.execute("SELECT COUNT(*) FROM audit_logs WHERE action="
                          "'PROTOCOLO_DOCUMENTO_ANEXADO' AND entity_id=?",
                          (pid,)).fetchone()[0]
    finally:
        con.close()
    assert aud == 1


def test_um_arquivo_ruim_no_lote_nao_deixa_os_bons_pela_metade(cg_casa_logada):
    casa = cg_casa_logada
    pid = _protocolo(casa)
    r = _anexar(casa, pid, [("bom.pdf", PDF), ("ruim.pdf", b"MZ\x90\x00 nada")])
    assert "o conteúdo não é PDF" in r.get_data(as_text=True)
    assert _linhas(casa, pid) == []


def test_outro_documento_exige_descricao(cg_casa_logada):
    casa = cg_casa_logada
    pid = _protocolo(casa)
    r = _anexar(casa, pid, [("x.pdf", PDF)], tipo="OUTRO", descricao="")
    assert "escreva na descrição" in r.get_data(as_text=True)
    assert _linhas(casa, pid) == []


def test_protocolo_encerrado_nao_recebe_papel(cg_casa_logada):
    casa = cg_casa_logada
    pid = _protocolo(casa, situacao="CANCELADO")
    r = _anexar(casa, pid, [("x.pdf", PDF)])
    assert "está encerrado" in r.get_data(as_text=True)
    assert _linhas(casa, pid) == []


# ------------------------------------------------------------ retirar sem apagar


def test_retirar_exige_motivo_e_nao_apaga_nada(cg_casa_logada):
    casa = cg_casa_logada
    pid = _protocolo(casa)
    _anexar(casa, pid, [("trocado.pdf", PDF)])
    anexo = _linhas(casa, pid)[0]
    c = casa["c"]
    tok = _token(c.get(f"/caixa/protocolos/{pid}").get_data(as_text=True))
    url = f"/caixa/protocolos/{pid}/documentos/{anexo['id']}/retirar"

    r = c.post(url, data={"csrf_token": tok, "motivo": "erro"}, follow_redirects=True)
    assert "pelo menos dez letras" in r.get_data(as_text=True)
    assert _linhas(casa, pid)[0]["retirado_em"] is None

    r = c.post(url, data={"csrf_token": tok,
                          "motivo": "documento de outro cliente"},
               follow_redirects=True)
    html = r.get_data(as_text=True)
    linha = _linhas(casa, pid)[0]                 # a linha continua no banco
    assert linha["retirado_em"] and linha["retirado_motivo"] == "documento de outro cliente"
    assert linha["retirado_por"] == "MARIO EXEMPLO DOS SANTOS"
    assert Path(linha["stored_path"]).exists()    # e o arquivo no disco
    assert "Retirados (1)" in html and "documento de outro cliente" in html
    con = _con(casa)
    try:
        assert PDOC.documentos(con, pid)["ativos"] == []
        aud = con.execute("SELECT COUNT(*) FROM audit_logs WHERE action="
                          "'PROTOCOLO_DOCUMENTO_RETIRADO'").fetchone()[0]
    finally:
        con.close()
    assert aud == 1


def test_documento_de_outro_protocolo_nao_se_retira_por_este(cg_casa_logada):
    casa = cg_casa_logada
    p1 = _protocolo(casa, numero="2026.10.91")
    p2 = _protocolo(casa, numero="2026.10.92")
    _anexar(casa, p1, [("a.pdf", PDF)])
    anexo = _linhas(casa, p1)[0]
    con = _con(casa)
    try:
        with pytest.raises(PDOC.DocumentoError, match="não é deste protocolo"):
            PDOC.retirar(con, p2, anexo["id"], motivo="motivo bem escrito",
                         por="beatriz", agora="2026-10-15T10:00")
    finally:
        con.close()


def test_o_auditor_ve_e_nao_anexa(cg_casa_logada):
    casa = cg_casa_logada
    pid = _protocolo(casa)
    casa["db"].create_user("carla", "CARLA EXEMPLO", "Senha#12345", "AUDITOR")
    c = casa["app"].test_client()
    html = c.get("/login").get_data(as_text=True)
    c.post("/login", data={"username": "carla", "password": "Senha#12345",
                           "csrf_token": _token(html)}, follow_redirects=True)
    tela = c.get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    assert "Documentos para qualificação" in tela
    assert 'name="documento"' not in tela
    r = c.post(f"/caixa/protocolos/{pid}/documentos",
               data={"csrf_token": _token(tela), "tipo": "CERTIDAO",
                     "documento": [(io.BytesIO(PDF), "x.pdf")]},
               content_type="multipart/form-data")
    assert r.status_code in (302, 403)
    assert _linhas(casa, pid) == []


# ------------------------------------------------------------ o ato das Notas


def test_o_ato_das_notas_ligado_ao_protocolo_ve_os_documentos(cg_casa_logada):
    casa = cg_casa_logada
    pid = _protocolo(casa, numero="2026.10.93")
    _anexar(casa, pid, [("procuracao_anterior.pdf", PDF)], tipo="PROCURACAO",
            descricao="procuração da vendedora")
    aid = _ato_de_notas(casa)
    c = casa["c"]
    tela = c.get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert "sem protocolo ligado" in tela
    r = c.post(f"/notas/atos/{aid}/protocolo-geral",
               data={"csrf_token": _token(tela), "acao": "vincular",
                     "numero": "2026.10.93"}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "procuracao_anterior.pdf" in html and "2026.10.93" in html

    # A função que o outro agente usa para contar folhas: anexos do ato E do
    # protocolo, cada um com o caminho do arquivo.
    con = _con(casa)
    try:
        tudo = PDOC.anexos_do_ato_de_notas(con, aid)
    finally:
        con.close()
    assert tudo["protocolo"]["numero"] == "2026.10.93"
    assert tudo["do_ato"] == []
    assert [d["original_name"] for d in tudo["do_protocolo"]] == ["procuracao_anterior.pdf"]
    assert Path(tudo["do_protocolo"][0]["stored_path"]).exists()


def test_protocolo_de_qualquer_atribuicao_se_liga_ao_ato(cg_casa_logada):
    """Decisão do oficial, 15/10/2026: o ato das Notas se liga a protocolo de
    QUALQUER atribuição (o cliente pode ter protocolado no RI e lavrar aqui).
    O que continua recusado é o número que não existe."""
    casa = cg_casa_logada
    _protocolo(casa, numero="2026.10.94", atribuicao="RI")
    aid = _ato_de_notas(casa)
    con = _con(casa)
    try:
        with pytest.raises(PDOC.DocumentoError, match="Não há protocolo"):
            PDOC.vincular_ato_de_notas(con, aid, "1999.01.01")
        p = PDOC.vincular_ato_de_notas(con, aid, "2026.10.94")
        con.commit()
        assert p["atribuicao"] == "RI"
        assert con.execute("SELECT protocolo_id FROM nt_atos WHERE id=?",
                           (aid,)).fetchone()[0] == p["id"]
    finally:
        con.close()
    # A tela diz de que atribuição é o protocolo ligado.
    html = casa["c"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert "2026.10.94" in html and "(RI" in html


def test_a_trava_da_lavratura_vale_para_qualquer_atribuicao(cg_casa_logada):
    casa = cg_casa_logada
    _protocolo(casa, numero="2026.10.97", atribuicao="RCPN")
    aid = _ato_de_notas(casa, situacao="LAVRADO")
    con = _con(casa)
    try:
        with pytest.raises(PDOC.DocumentoError, match="já foi lançado"):
            PDOC.vincular_ato_de_notas(con, aid, "2026.10.97")
    finally:
        con.close()


def test_ato_ja_lancado_nao_troca_de_protocolo(cg_casa_logada):
    casa = cg_casa_logada
    _protocolo(casa, numero="2026.10.95")
    aid = _ato_de_notas(casa, situacao="LAVRADO")
    con = _con(casa)
    try:
        with pytest.raises(PDOC.DocumentoError, match="já foi lançado"):
            PDOC.vincular_ato_de_notas(con, aid, "2026.10.95")
    finally:
        con.close()


# ------------------------------------------------------------ a prenotação do RI


def test_a_prenotacao_ve_os_documentos_do_protocolo_geral_vinculado(cg_casa_logada):
    """O caso da tarefa 386: prenotação de escritura, papéis no protocolo."""
    casa = cg_casa_logada
    con = _con(casa)
    cur = con.execute(
        """INSERT INTO ri_protocolos (numero, livro, data_prenotacao,
               apresentante, situacao, criado_em)
           VALUES (11573, '1A', '2026-10-15', 'FULANO DE TAL', 'ABERTO',
                   '2026-10-15T09:00')""")
    con.commit()
    rid = int(cur.lastrowid)
    con.close()
    pid = _protocolo(casa, numero="2026.10.96", atribuicao="RI", ri_protocolo_id=rid)
    _anexar(casa, pid, [("matricula.pdf", PDF)], tipo="MATRICULA",
            descricao="matrícula atualizada")
    html = casa["c"].get(f"/registro-imoveis/protocolo/{rid}").get_data(as_text=True)
    assert "Documentos para qualificação do protocolo geral" in html
    assert "matricula.pdf" in html


# ------------------------------------------------------------ a tela de lavrar do RI


def _matricula_e_prenotacao(casa, *, numero_prenotacao=11574, ato_id=None):
    con = _con(casa)
    mid = int(con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, criado_em)
           VALUES ('4010', '2', '2', 'ATIVA', 'ESTRUTURADA', '2026-10-15T09:00')"""
    ).lastrowid)
    rid = int(con.execute(
        """INSERT INTO ri_protocolos (numero, livro, data_prenotacao,
               apresentante, situacao, ato_id, criado_em)
           VALUES (?, '1A', '2026-10-15', 'FULANO DE TAL', 'ABERTO', ?,
                   '2026-10-15T09:00')""", (numero_prenotacao, ato_id)).lastrowid)
    con.commit()
    con.close()
    return mid, rid


def test_a_tela_de_lavrar_da_matricula_mostra_os_documentos_do_protocolo(cg_casa_logada):
    """Decisão do oficial, 15/10/2026: quem lavra na ficha da matrícula vê o que
    o cliente entregou no Protocolo Geral ligado à prenotação escolhida."""
    casa = cg_casa_logada
    mid, rid = _matricula_e_prenotacao(casa)
    pid = _protocolo(casa, numero="2026.10.98", atribuicao="RI", ri_protocolo_id=rid)
    _anexar(casa, pid, [("formal_de_partilha.pdf", PDF)], tipo="TITULO",
            descricao="formal de partilha")
    c = casa["c"]
    com = c.get(f"/registro-imoveis/{mid}?lavrar=1&prenotacao_id={rid}").get_data(as_text=True)
    assert 'id="documentos-qualificacao-lavrar"' in com
    assert "formal_de_partilha.pdf" in com and "2026.10.98" in com
    # Sem prenotação escolhida, o bloco não aparece — o relato #85 tirou da
    # ficha a lista das prenotações abertas, por ser ruído.
    sem = c.get(f"/registro-imoveis/{mid}?lavrar=1").get_data(as_text=True)
    assert "formal_de_partilha.pdf" not in sem


def test_o_documento_retirado_nao_aparece_para_quem_lavra(cg_casa_logada):
    casa = cg_casa_logada
    _, rid = _matricula_e_prenotacao(casa, numero_prenotacao=11575)
    pid = _protocolo(casa, numero="2026.10.99", atribuicao="RI", ri_protocolo_id=rid)
    _anexar(casa, pid, [("errado.pdf", PDF)])
    anexo = _linhas(casa, pid)[0]
    con = _con(casa)
    try:
        PDOC.retirar(con, pid, anexo["id"], motivo="documento de outro cliente",
                     por="beatriz", agora="2026-10-15T11:00")
        con.commit()
        assert PDOC.da_prenotacao(con, rid)["ativos"] == []
    finally:
        con.close()


def test_documentos_para_lavrar_traz_o_protocolo_geral_em_chave_propria(cg_casa_logada):
    """O ato já lavrado da ficha enxerga, pela prenotação dele, também o que o
    cliente entregou no balcão — sem misturar com o título da prenotação."""
    import ri_documentos as RDOC
    from ri_schema import hash_ato
    casa = cg_casa_logada
    con = _con(casa)
    mid = int(con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, criado_em)
           VALUES ('4011', '2', '2', 'ATIVA', 'ESTRUTURADA', '2026-10-15T09:00')"""
    ).lastrowid)
    aid = int(con.execute(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor,
               teor_formato, cancelado, acervo, origem, hash_ato, lavrado_em)
           VALUES (?, 'R', 1, '2026-10-15', 'x', 'texto', 0, 0, 'MANUAL', ?,
                   '2026-10-15T09:00')""",
        (mid, hash_ato("4011", "R", 1, "2026-10-15", "x", None))).lastrowid)
    rid = int(con.execute(
        """INSERT INTO ri_protocolos (numero, livro, data_prenotacao,
               apresentante, situacao, ato_id, criado_em)
           VALUES (11576, '1A', '2026-10-15', 'FULANO DE TAL', 'REGISTRADO', ?,
                   '2026-10-15T09:00')""", (aid,)).lastrowid)
    con.commit()
    con.close()
    pid = _protocolo(casa, numero="2026.10.100", atribuicao="RI", ri_protocolo_id=rid)
    _anexar(casa, pid, [("rg.pdf", PDF)], tipo="IDENTIDADE", descricao="RG do herdeiro")
    con = _con(casa)
    try:
        visao = RDOC.documentos_para_lavrar(con, aid)
    finally:
        con.close()
    assert visao["documentos"] == []                       # o título da prenotação
    assert [d["original_name"] for d in visao["do_protocolo_geral"]] == ["rg.pdf"]


# ------------------------------------------------------------ a pasta do processo


def test_a_pasta_do_processo_lista_ativos_e_retirados_a_parte(cg_casa_logada):
    import processo_pasta as PASTA
    casa = cg_casa_logada
    pid = _protocolo(casa, numero="2026.10.101")
    _anexar(casa, pid, [("fica.pdf", PDF), ("sai.pdf", PDF)], tipo="CERTIDAO")
    sai = [x for x in _linhas(casa, pid) if x["original_name"] == "sai.pdf"][0]
    con = _con(casa)
    try:
        PDOC.retirar(con, pid, sai["id"], motivo="digitalizado de cabeça para baixo",
                     por="beatriz", agora="2026-10-15T11:00")
        tid = int(con.execute(
            "INSERT INTO tasks (source_type, title, sector, priority, status, due_days, "
            "start_date, due_date, created_at, updated_at) VALUES ('MANUAL', "
            "'Qualificar escritura', 'Notas', 'MEDIA', 'ABERTA', 2, '2026-10-15', "
            "'2026-10-17', '2026-10-15T09:00', '2026-10-15T09:00')").lastrowid)
        PASTA.vincular(con, tid, "cx_protocolos", "2026.10.101",
                       agora="2026-10-15T11:00", por=None)
        con.commit()
        ativos = [d["nome"] for d in PASTA.documentos(con, tid)]
        retirados = PASTA.documentos_retirados(con, tid)
    finally:
        con.close()
    assert ativos == ["fica.pdf"]
    assert [d["nome"] for d in retirados] == ["sai.pdf"]
    assert retirados[0]["retirado_motivo"] == "digitalizado de cabeça para baixo"
    html = casa["c"].get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "fica.pdf" in html
    assert "Retirados (1)" in html and "digitalizado de cabeça para baixo" in html
