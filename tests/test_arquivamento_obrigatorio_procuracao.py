"""O selo de arquivamento (13.30) obrigatório na procuração, no substabelecimento
e na revogação — e as folhas contadas dos anexos e confirmadas.

    «colocar o selo de arquivamento como obrigatorio pra ir junto com a
     procuracao»                       — o oficial, 15/10/2026

No mesmo dia: a regra vale também para o substabelecimento e a revogação, e a
quantidade de folhas é a do documento anexado, pendente de confirmação do
escrevente. O mecanismo é o que já existia como OPCIONAL na lavratura; o que
estes testes guardam é que, nos três tipos, ele deixou de ser escolha — e que
a escritura continua com o opcional de antes.
"""
from __future__ import annotations

import io
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import notas_arquivamento as NARQ  # noqa: E402

SENHA = "Senha#12345"
TIPOS = ("PROCURACAO", "SUBSTABELECIMENTO", "REVOGACAO",
         "PROCURACAO_PREVIDENCIARIA", "RENUNCIA")


# ------------------------------------------------------------ ajudantes


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _pdf(paginas: int) -> bytes:
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(paginas):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("carla", "CARLA EXEMPLO LIMA", SENHA, "USER")
    db.set_settings({"ri_cidade": "Cidade Exemplo", "ri_uf": "MA"})
    c = cg_casa["app"].test_client()
    c.post("/login", data={"username": "carla", "password": SENHA,
                           "csrf_token": _token(
                               c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {**cg_casa, "cliente": c}


def _ato(casa, tipo: str) -> int:
    con = sqlite3.connect(casa["banco"])
    with con:
        cur = con.execute(
            """INSERT INTO nt_atos (tipo, serie, data, hora, situacao,
                   natureza, interessado, teor, teor_formato, lavrado_nome,
                   origem, criado_em)
               VALUES (?, 'LIVRO', '2026-10-15', '10:00', 'EM_LAVRATURA',
                       'OUTRA', 'MARIO EXEMPLO', ?, 'html',
                       'CARLA EXEMPLO LIMA', 'MANUAL',
                       '2026-10-15T10:00:00')""",
            (tipo, "<p>MARIO EXEMPLO nomeia e constitui sua procuradora "
                   "BEATRIZ EXEMPLO, a quem confere poderes.</p>"))
        aid = int(cur.lastrowid)
        # As duas pontas com o cadastro inteiro: a trava da procuração
        # (13/10/2026) recusa outorgante ou outorgado incompletos, e o que
        # estes testes medem é o arquivamento, que vem depois dela.
        for ordem, (nome, qualif, doc) in enumerate((
                ("MARIO EXEMPLO", "OUTORGANTE", "00000000191"),
                ("BEATRIZ EXEMPLO", "OUTORGADO", "00000000272")), start=1):
            con.execute(
                """INSERT INTO nt_ato_partes (ato_id, nome, nome_norm,
                       qualificacao, documento, nacionalidade, estado_civil,
                       profissao, endereco, tipo_pessoa, testemunha, ordem,
                       criado_em)
                   VALUES (?,?,?,?,?,'brasileira','solteira','lavradora',
                           'Rua Grande, 10, Cidade Exemplo/MA','F',0,?,
                           '2026-10-15T10:00:00')""",
                (aid, nome, nome.lower(), qualif, doc, ordem))
    con.close()
    return aid


def _tela(casa, ato_id) -> str:
    return casa["cliente"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)


def _postar(casa, ato_id, **dados) -> str:
    if dados.get("acao") == "lancar":
        from notas_pronto_para_a_censec import preparar
        preparar(casa["banco"], ato_id)
    return casa["cliente"].post(
        f"/notas/atos/{ato_id}",
        data={"csrf_token": _token(_tela(casa, ato_id)), **dados},
        follow_redirects=True).get_data(as_text=True)


def _anexar(casa, ato_id, nome: str, conteudo: bytes) -> None:
    casa["cliente"].post(
        f"/notas/atos/{ato_id}/anexos",
        data={"csrf_token": _token(_tela(casa, ato_id)),
              "descricao": "Documento arquivado",
              "arquivo": (io.BytesIO(conteudo), nome)},
        content_type="multipart/form-data", follow_redirects=True)


def _linha(casa, ato_id):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM nt_atos WHERE id=?", (ato_id,)).fetchone()
    con.close()
    return r


def _selos(casa, ato_id) -> list[str]:
    con = sqlite3.connect(casa["banco"])
    caminhos = [r[0] for r in con.execute(
        "SELECT caminho FROM sd_selos WHERE tabela='nt_atos' AND ato_id=? "
        "ORDER BY id", (ato_id,))]
    con.close()
    return caminhos


# ------------------------------------------------------------ a regra, pura


def test_os_cinco_sao_obrigados_e_a_escritura_nao():
    for tipo in TIPOS:
        assert NARQ.arquivamento_obrigatorio(tipo)
    for tipo in ("ESCRITURA", "ATA", "ATA_USUCAPIAO", "TESTAMENTO"):
        assert not NARQ.arquivamento_obrigatorio(tipo)


@pytest.mark.parametrize("tipo", ("SUBSTABELECIMENTO", "REVOGACAO",
                                  "PROCURACAO_PREVIDENCIARIA", "RENUNCIA"))
def test_substabelecimento_e_revogacao_selam_pelo_caminho_da_procuracao(
        casa, tipo):
    """Decisão do oficial, 15/10/2026: o mesmo caminho da procuração — e,
    no mesmo dia, também a previdenciária e a renúncia."""
    import ato_selado as AS
    assert (AS.caminho_do_ato_de_livro_das_notas(
        tipo, especie_procuracao="SIMPLES")
        == "/selo/notas/procuracao/simples")
    html = _tela(casa, _ato(casa, tipo))
    assert "Qual procuração é esta?" in html
    assert "13.9.3" in html


@pytest.mark.parametrize("bruto,esperado", [
    ("3", 3), ("1", 1), ("0", 0), ("-2", 0), ("2.5", 0), ("", 0),
    (None, 0), ("abc", 0), (4, 4), (0, 0)])
def test_folhas_so_inteiro_maior_que_zero(bruto, esperado):
    assert NARQ.folhas_validas(bruto) == esperado


# ------------------------------------------------------------ a contagem


@pytest.mark.parametrize("tipo", TIPOS)
def test_a_sugestao_sai_da_contagem_dos_anexos(casa, tipo):
    """PDF conta as páginas, imagem conta uma — e a tela diz de onde veio."""
    aid = _ato(casa, tipo)
    _anexar(casa, aid, "rg.pdf", _pdf(2))
    _anexar(casa, aid, "comprovante.jpg", b"\xff\xd8\xff\xe0 imagem")
    html = _tela(casa, aid)
    assert "3 folhas: rg.pdf (2) + comprovante.jpg (1)" in html
    assert "Pendente de confirmação" in html
    assert re.search(r'name="folhas_arquivamento"[^>]*value="3"', html)


def test_o_pdf_contado_nao_fica_travado(casa, tmp_path):
    """HOTFIX-2026-10-06-01: o PDF aberto trava no Windows; contar fecha."""
    p = tmp_path / "doc.pdf"
    p.write_bytes(_pdf(4))
    assert NARQ.folhas_do_arquivo("doc.pdf", p) == 4
    p.unlink()                       # estouraria em WinError 32 se travado
    assert not p.exists()


def test_os_anexos_do_protocolo_geral_tambem_contam(casa, tmp_path):
    """Os de qualificação do Protocolo Geral (relato #135) entram na soma, e a
    parcela diz de onde veio e de que tipo é — na dúvida conta-se tudo, e o
    escrevente corrige na confirmação."""
    import protocolo_documentos as PDOC
    aid = _ato(casa, "PROCURACAO")
    _anexar(casa, aid, "rg.pdf", _pdf(2))
    doc = tmp_path / "certidao.pdf"
    doc.write_bytes(_pdf(3))
    con = sqlite3.connect(casa["banco"])
    with con:
        PDOC.init_protocolo_documentos_schema(con)
        pid = con.execute(
            "INSERT INTO cx_protocolos (numero, data_abertura, atribuicao, "
            "criado_em) VALUES ('2026.10.5', '2026-10-15', 'NOTAS', "
            "'2026-10-15T10:00:00')").lastrowid
        con.execute("UPDATE nt_atos SET protocolo_id=? WHERE id=?", (pid, aid))
        con.execute(
            """INSERT INTO attachments (entity_type, entity_id, original_name,
                   stored_name, stored_path, sha256, size_bytes, uploaded_at,
                   documento_tipo)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (PDOC.ENTIDADE, pid, "certidao.pdf", "certidao.pdf", str(doc),
             "0" * 64, 10, "2026-10-15T10:00:00", "CERTIDAO"))
    con.close()
    html = _tela(casa, aid)
    assert ("5 folhas: rg.pdf (2) + certidao.pdf (3, protocolo 2026.10.5, "
            "Certidão") in html


def test_arquivo_que_nao_se_conta_e_dito_e_nao_vira_zero(casa):
    aid = _ato(casa, "PROCURACAO")
    _anexar(casa, aid, "rg.pdf", _pdf(1))
    _anexar(casa, aid, "nota.docx", b"PK\x03\x04 nada")
    html = _tela(casa, aid)
    assert "1 folha: rg.pdf (1)" in html
    assert "não contado(s): nota.docx" in html


# ------------------------------------------------------------ as recusas


@pytest.mark.parametrize("tipo", TIPOS)
def test_sem_anexo_a_selagem_e_recusada(casa, tipo):
    aid = _ato(casa, tipo)
    html = _tela(casa, aid)
    assert "Anexe o documento arquivado" in html
    html = _postar(casa, aid, acao="lancar", paginas="2", codigo_tj="13.9.3",
                   especie_procuracao="PODERES_ESPECIFICOS",
                   gerar_arquivamento="1", folhas_arquivamento="5")
    r = _linha(casa, aid)
    assert not (r["livro"] or "").strip(), "não podia ocupar o livro"
    assert "NÃO lançado" in html and "anexe o documento arquivado" in html
    # e a confirmação também recusa sem anexo
    html = _postar(casa, aid, acao="confirmar_arquivamento",
                   folhas_arquivamento="5")
    assert "anexe o documento arquivado" in html
    assert not _linha(casa, aid)["arquivamento_confirmado_em"]


@pytest.mark.parametrize("tipo", TIPOS)
def test_sem_confirmacao_a_selagem_e_recusada(casa, tipo):
    """O número do formulário não vale: só o confirmado na ficha."""
    aid = _ato(casa, tipo)
    _anexar(casa, aid, "rg.pdf", _pdf(2))
    html = _tela(casa, aid)
    assert re.search(r'<button class="primary" name="acao" value="lancar"\s+'
                     r'disabled title="Confirme as folhas', html), \
        "a tela tinha de travar o lançamento"
    html = _postar(casa, aid, acao="lancar", paginas="2", codigo_tj="13.9.3",
                   especie_procuracao="PODERES_ESPECIFICOS",
                   gerar_arquivamento="1", folhas_arquivamento="2")
    r = _linha(casa, aid)
    assert not (r["livro"] or "").strip()
    assert "NÃO lançado" in html and "confirme a quantidade" in html


@pytest.mark.parametrize("tipo", TIPOS)
def test_desmarcar_a_caixa_nao_dispensa(casa, tipo):
    """Formulário mandado sem `gerar_arquivamento` continua obrigado."""
    aid = _ato(casa, tipo)
    html = _postar(casa, aid, acao="lancar", paginas="2", codigo_tj="13.9.3",
                   especie_procuracao="PODERES_ESPECIFICOS")
    assert not (_linha(casa, aid)["livro"] or "").strip()
    assert "obrigatório" in html


@pytest.mark.parametrize("tipo", TIPOS)
def test_a_tela_mostra_a_caixa_marcada_e_travada(casa, tipo):
    aid = _ato(casa, tipo)
    html = _tela(casa, aid)
    assert '<input type="hidden" name="gerar_arquivamento" value="1">' in html
    assert '<input type="checkbox" checked disabled>' in html


def test_a_escritura_continua_com_o_opcional(casa):
    aid = _ato(casa, "ESCRITURA")
    html = _tela(casa, aid)
    assert 'id="gerar_arquivamento_nt"' in html
    assert '<input type="hidden" name="gerar_arquivamento" value="1">' not in html


# ------------------------------------------------------------ a confirmação


@pytest.mark.parametrize("tipo", TIPOS)
def test_o_numero_corrigido_e_respeitado_e_fica_o_rastro(casa, tipo):
    aid = _ato(casa, tipo)
    _anexar(casa, aid, "rg.pdf", _pdf(2))
    html = _postar(casa, aid, acao="confirmar_arquivamento",
                   folhas_arquivamento="7")
    assert "corrigido por você" in html
    r = _linha(casa, aid)
    assert r["folhas_arquivamento"] == 7
    assert r["arquivamento_folhas_sugeridas"] == 2
    assert r["arquivamento_origem_sugestao"] == "2 folhas: rg.pdf (2)"
    assert r["arquivamento_confirmado_por"] == "CARLA EXEMPLO LIMA"
    assert (r["arquivamento_confirmado_em"] or "").strip()
    con = sqlite3.connect(casa["banco"])
    n = con.execute("SELECT COUNT(*) FROM audit_logs WHERE action="
                    "'NT_ATO_ARQUIVAMENTO_CONFIRMADO'").fetchone()[0]
    con.close()
    assert n == 1


def test_confirmacao_invalida_e_recusada(casa):
    aid = _ato(casa, "PROCURACAO")
    _anexar(casa, aid, "rg.pdf", _pdf(2))
    html = _postar(casa, aid, acao="confirmar_arquivamento",
                   folhas_arquivamento="0")
    assert "número inteiro, 1 ou mais" in html
    assert not _linha(casa, aid)["arquivamento_confirmado_em"]


def test_anexo_novo_depois_da_confirmacao_pede_confirmar_de_novo(casa):
    aid = _ato(casa, "PROCURACAO")
    _anexar(casa, aid, "rg.pdf", _pdf(2))
    _postar(casa, aid, acao="confirmar_arquivamento", folhas_arquivamento="2")
    _anexar(casa, aid, "cpf.png", b"\x89PNG imagem")
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    ato = con.execute("SELECT * FROM nt_atos WHERE id=?", (aid,)).fetchone()
    with pytest.raises(NARQ.ArquivamentoError, match="anexos mudaram"):
        NARQ.exigir_para_selar(con, ato)
    con.close()
    assert "confirme de novo" in _tela(casa, aid)


# ------------------------------------------------------------ o caminho inteiro


def test_procuracao_confirmada_sela_os_dois_com_o_numero_confirmado(casa):
    """O selo do ato e o 13.30 saem juntos, e a quantidade é a corrigida."""
    from selador_de_bancada import ligar_o_selador
    aid = _ato(casa, "PROCURACAO")
    _anexar(casa, aid, "rg.pdf", _pdf(2))
    _anexar(casa, aid, "comprovante.jpg", b"\xff\xd8\xff\xe0 imagem")
    _postar(casa, aid, acao="confirmar_arquivamento", folhas_arquivamento="4")
    with ligar_o_selador(casa) as aparelho:
        html = _postar(casa, aid, acao="lancar", paginas="2",
                       codigo_tj="13.9.3",
                       especie_procuracao="PODERES_ESPECIFICOS",
                       # o formulário dizer outro número não muda nada
                       folhas_arquivamento="99")
        pedidos = [p for p in aparelho.pedidos
                   if p["caminho"].endswith("/selo/notas/atos-em-geral")]
    r = _linha(casa, aid)
    assert (r["selo"] or "").strip(), html[:0]
    assert (r["selo_arquivamento"] or "").strip(), "faltou o selo 13.30"
    assert r["folhas_arquivamento"] == 4
    assert r["situacao"] == "LAVRADO"
    assert _selos(casa, aid) == ["/selo/notas/procuracao/poderes-especificos",
                                 "/selo/notas/atos-em-geral"]
    assert len(pedidos) == 1, "um pedido só, com a quantidade"
    corpo = json.loads(pedidos[0]["corpo"])
    assert corpo["ato"]["codigo"] == "13.30"
    assert corpo["quantidade"] == 4


def test_arquivamento_recusado_suspende_a_procuracao(casa, monkeypatch):
    """O do ato sai, o 13.30 não: a procuração não fica LAVRADA, e o botão
    «Selar arquivamento» a conclui com o número confirmado."""
    from selador_de_bancada import ligar_o_selador
    import ato_selado as AS
    aid = _ato(casa, "PROCURACAO")
    _anexar(casa, aid, "rg.pdf", _pdf(3))
    _postar(casa, aid, acao="confirmar_arquivamento", folhas_arquivamento="3")
    original = AS.envelope_do_arquivamento_do_ri

    def _recusa(**_k):
        raise AS.AtoError("arquivamento recusado na bancada")

    with ligar_o_selador(casa):
        monkeypatch.setattr(AS, "envelope_do_arquivamento_do_ri", _recusa)
        html = _postar(casa, aid, acao="lancar", paginas="2",
                       codigo_tj="13.9.3",
                       especie_procuracao="PODERES_ESPECIFICOS")
        r = _linha(casa, aid)
        assert (r["selo"] or "").strip()
        assert not (r["selo_arquivamento"] or "").strip()
        assert r["situacao"] == "SUSPENSO_SELO"
        assert "NÃO concluído" in html and "arquivamento recusado" in html

        monkeypatch.setattr(AS, "envelope_do_arquivamento_do_ri", original)
        tela = _tela(casa, aid)
        casa["cliente"].post(f"/notas/atos/{aid}/selar-arquivamento",
                             data={"csrf_token": _token(tela)},
                             follow_redirects=True)
    r = _linha(casa, aid)
    assert (r["selo_arquivamento"] or "").strip()
    assert r["folhas_arquivamento"] == 3
    assert r["situacao"] == "LAVRADO"


def test_selar_arquivamento_depois_recusa_sem_confirmacao(casa):
    """A rota de «Selar arquivamento» também confere, no servidor."""
    aid = _ato(casa, "PROCURACAO")
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute("UPDATE nt_atos SET selo='PROCUR000000TESTE0000000001', "
                    "situacao='LAVRADO', livro='1', folha='1' WHERE id=?",
                    (aid,))
    con.close()
    _anexar(casa, aid, "rg.pdf", _pdf(2))
    html = casa["cliente"].post(
        f"/notas/atos/{aid}/selar-arquivamento",
        data={"csrf_token": _token(_tela(casa, aid)),
              "folhas_arquivamento": "2"},
        follow_redirects=True).get_data(as_text=True)
    assert "confirme a quantidade" in html
    assert not (_linha(casa, aid)["selo_arquivamento"] or "").strip()


# ------------------------------------------------------------ os selos à mão
#
# Decisão do oficial, 15/10/2026: com o selo do ato digitado à mão o ato
# continua SUSPENSO_SELO até o 13.30; e o 13.30 tirado fora do sistema também
# se anota à mão, no mesmo molde.


def _lancada_sem_selo(casa, tipo="PROCURACAO") -> int:
    aid = _ato(casa, tipo)
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute("UPDATE nt_atos SET situacao='SUSPENSO_SELO', livro='3', "
                    "folha='10', lancado_em='2026-10-15T10:05:00' WHERE id=?",
                    (aid,))
    con.close()
    return aid


def test_selo_do_ato_a_mao_nao_dispensa_o_arquivamento(casa):
    casa["db"].set_settings({"ri_cns": "000000"})
    aid = _lancada_sem_selo(casa)
    html = _postar(casa, aid, acao="selo", selo="PROCUR000000ZZZZZZZZZZZZZZ12")
    r = _linha(casa, aid)
    assert r["selo"] == "PROCUR000000ZZZZZZZZZZZZZZ12"
    assert r["situacao"] == "SUSPENSO_SELO"
    assert "falta o selo de arquivamento" in html


def test_selo_de_arquivamento_a_mao_conclui_e_entra_no_razao(casa):
    casa["db"].set_settings({"ri_cns": "000000"})
    aid = _lancada_sem_selo(casa)
    _postar(casa, aid, acao="selo", selo="PROCUR000000ZZZZZZZZZZZZZZ12")
    # sem anexo e sem confirmação, recusa
    html = _postar(casa, aid, acao="selo_arquivamento",
                   selo_arquivamento="ARQUIV000000ZZZZZZZZZZZZZZ34")
    assert "anexe o documento arquivado" in html
    assert not (_linha(casa, aid)["selo_arquivamento"] or "").strip()
    _anexar(casa, aid, "rg.pdf", _pdf(2))
    _postar(casa, aid, acao="confirmar_arquivamento", folhas_arquivamento="2")
    # selo que não é de arquivamento, recusa
    html = _postar(casa, aid, acao="selo_arquivamento",
                   selo_arquivamento="ESCRIT000000ZZZZZZZZZZZZZZ56")
    assert "não é de arquivamento" in html
    _postar(casa, aid, acao="selo_arquivamento",
            selo_arquivamento="ARQUIV000000ZZZZZZZZZZZZZZ34")
    r = _linha(casa, aid)
    assert r["selo"] == "PROCUR000000ZZZZZZZZZZZZZZ12", "o do ato não sai do lugar"
    assert r["selo_arquivamento"] == "ARQUIV000000ZZZZZZZZZZZZZZ34"
    assert r["folhas_arquivamento"] == 2
    assert r["situacao"] == "LAVRADO"
    con = sqlite3.connect(casa["banco"])
    numeros = {x[0] for x in con.execute(
        "SELECT numero FROM sd_selos WHERE tabela='nt_atos' AND ato_id=?",
        (aid,))}
    con.close()
    assert numeros == {"PROCUR000000ZZZZZZZZZZZZZZ12",
                       "ARQUIV000000ZZZZZZZZZZZZZZ34"}


def test_a_tela_avisa_que_a_gratuidade_do_arquivamento_e_a_mao(casa):
    aid = _lancada_sem_selo(casa)
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute("UPDATE nt_atos SET selo='PROCUR000000ZZZZZZZZZZZZZZ12' "
                    "WHERE id=?", (aid,))
    con.close()
    html = _tela(casa, aid)
    assert "Atenção à gratuidade" in html
    assert "sem marcar, o arquivamento sai" in html


# ------------------------------------------------------------ as custas
#
# Decisão do oficial, 15/10/2026: ao confirmar, o 13.30 × N entra no
# protocolo do ato, sem duplicar, e a reconfirmação ajusta a quantidade.


def _tabela_com_o_13_30(casa) -> None:
    con = sqlite3.connect(casa["banco"])
    with con:
        vig = con.execute(
            "SELECT codigo FROM cx_vigencias WHERE vigente=1").fetchone()
        if vig is None:
            con.execute("INSERT INTO cx_vigencias (codigo, descricao, vigente) "
                        "VALUES (10022, 'tabela de ensaio', 1)")
            vig = (10022,)
        tem = con.execute(
            """SELECT 1 FROM cx_servicos s JOIN cx_servico_valores v
                   ON v.servico=s.codigo AND v.vigencia=?
                WHERE s.codigo_tj='13.30'""", (vig[0],)).fetchone()
        if not tem:
            con.execute("INSERT OR IGNORE INTO cx_servicos (codigo, codigo_tj, "
                        "descricao, grupo) VALUES (99698, '13.30', "
                        "'Arquivamento, por folha do documento', 21)")
            con.execute("INSERT INTO cx_servico_valores (servico, vigencia, "
                        "emolumentos, ferc, femp, fadep, ferrfis, total) "
                        "VALUES (99698, ?, '6,72', '0,20', '0,00', '0,00', "
                        "'0,00', '6,92')", (vig[0],))
    con.close()


def _protocolo(casa, aid) -> int:
    con = sqlite3.connect(casa["banco"])
    with con:
        pid = con.execute(
            "INSERT INTO cx_protocolos (numero, data_abertura, atribuicao, "
            "criado_em) VALUES ('2026.10.77', '2026-10-15', 'NOTAS', "
            "'2026-10-15T10:00:00')").lastrowid
        con.execute("UPDATE nt_atos SET protocolo_id=? WHERE id=?", (pid, aid))
    con.close()
    return pid


def _itens_13_30(casa, pid):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    linhas = [dict(r) for r in con.execute(
        "SELECT * FROM cx_protocolo_atos WHERE protocolo_id=? AND "
        "codigo_ato='13.30'", (pid,))]
    total = con.execute("SELECT valor_total FROM cx_protocolos WHERE id=?",
                        (pid,)).fetchone()[0]
    con.close()
    return linhas, total


def test_confirmar_lanca_o_13_30_no_protocolo_e_reconfirmar_ajusta(casa):
    _tabela_com_o_13_30(casa)
    aid = _ato(casa, "PROCURACAO")
    pid = _protocolo(casa, aid)
    _anexar(casa, aid, "rg.pdf", _pdf(3))
    html = _postar(casa, aid, acao="confirmar_arquivamento",
                   folhas_arquivamento="3")
    assert "Item 13.30 × 3 lançado no protocolo" in html
    itens, total = _itens_13_30(casa, pid)
    assert len(itens) == 1 and itens[0]["quantidade"] == 3
    assert itens[0]["valor_total"] == "20,76"         # 3 × R$ 6,92
    assert total == "20,76"
    _postar(casa, aid, acao="confirmar_arquivamento", folhas_arquivamento="5")
    itens, total = _itens_13_30(casa, pid)
    assert len(itens) == 1, "reconfirmar não duplica"
    assert itens[0]["quantidade"] == 5 and total == "34,60"


def test_o_13_30_posto_a_mao_e_adotado_e_nao_somado(casa):
    _tabela_com_o_13_30(casa)
    aid = _ato(casa, "SUBSTABELECIMENTO")
    pid = _protocolo(casa, aid)
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute("INSERT INTO cx_protocolo_atos (protocolo_id, descricao, "
                    "codigo_ato, quantidade, valor_total) VALUES (?, "
                    "'Arquivamento', '13.30', 1, '6,92')", (pid,))
    con.close()
    _anexar(casa, aid, "rg.pdf", _pdf(2))
    _postar(casa, aid, acao="confirmar_arquivamento", folhas_arquivamento="2")
    itens, _ = _itens_13_30(casa, pid)
    assert len(itens) == 1 and itens[0]["quantidade"] == 2
    assert itens[0]["origem"] == NARQ.ORIGEM_DO_ITEM


def test_item_ja_quitado_com_outra_quantidade_recusa_a_confirmacao(casa):
    _tabela_com_o_13_30(casa)
    aid = _ato(casa, "REVOGACAO")
    pid = _protocolo(casa, aid)
    _anexar(casa, aid, "rg.pdf", _pdf(2))
    _postar(casa, aid, acao="confirmar_arquivamento", folhas_arquivamento="2")
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute("UPDATE cx_protocolo_atos SET quitado=1 WHERE "
                    "protocolo_id=? AND codigo_ato='13.30'", (pid,))
    con.close()
    html = _postar(casa, aid, acao="confirmar_arquivamento",
                   folhas_arquivamento="4")
    assert "estorne no caixa" in html
    assert _linha(casa, aid)["folhas_arquivamento"] == 2, \
        "a confirmação não podia mudar sem o item acompanhar"


def test_sem_protocolo_a_confirmacao_vale_e_a_tela_avisa(casa):
    aid = _ato(casa, "PROCURACAO")
    _anexar(casa, aid, "rg.pdf", _pdf(1))
    html = _postar(casa, aid, acao="confirmar_arquivamento",
                   folhas_arquivamento="1")
    assert "O 13.30 NÃO entrou nas custas" in html
    assert "não está ligado a um protocolo" in html
    assert _linha(casa, aid)["folhas_arquivamento"] == 1


# ------------------------------------------------------------ os cinco selam
#
# Decisão do oficial, 15/10/2026: a previdenciária e a renúncia selam pelo
# mesmo caminho da procuração, como o substabelecimento e a revogação.
# Lançadas com o arquivamento confirmado, as cinco saem SELADAS — os dois
# selos —, e não suspensas.


@pytest.mark.parametrize("tipo", TIPOS)
def test_lancados_os_cinco_selam_o_ato_e_o_arquivamento(casa, tipo):
    from selador_de_bancada import ligar_o_selador
    aid = _ato(casa, tipo)
    _anexar(casa, aid, "rg.pdf", _pdf(2))
    _postar(casa, aid, acao="confirmar_arquivamento", folhas_arquivamento="2")
    with ligar_o_selador(casa):
        html = _postar(casa, aid, acao="lancar", paginas="2",
                       codigo_tj="13.9.3", especie_procuracao="SIMPLES")
    r = _linha(casa, aid)
    assert (r["livro"] or "").strip(), html[:0]
    assert (r["selo"] or "").strip(), f"{tipo} ficou sem o selo do ato"
    assert (r["selo_arquivamento"] or "").strip(), f"{tipo} sem o 13.30"
    assert r["situacao"] == "LAVRADO", f"{tipo} ficou {r['situacao']}"
    assert _selos(casa, aid) == ["/selo/notas/procuracao/simples",
                                 "/selo/notas/atos-em-geral"]
