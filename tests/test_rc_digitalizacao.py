"""O termo assinado do RCPN, digitalizado — problema #121, 07/10/2026.

    «acrescentar a obrigatoriedade de digitalizar o termo no sistema depois da
     lavratura de registro, com visualização do termo assinado» — «nos moldes
     que temos no RI [...] fica pronto pra emitir certidão reprográfica»
                                                     — o oficial, 07/10/2026

O QUE ESTES TESTES PROVAM
    - a migração: as seis colunas `digi_*` no assento, o sha na certidão e o
      corte semeado UMA vez (e nunca regravado);
    - o envio pela ficha: o arquivo vai para `rc/digitalizacoes/<id>/`, o
      anterior para `historico/`, com auditoria — e a ficha mostra o termo;
    - a pendência só do registro LAVRADO AQUI depois do corte: o acervo
      (IMPORTACAO, EOFICIO, ARQUIVO), o cancelado, o proclama e o lavrado antes
      do corte não viram pendência; o prazo de 7 dias vence;
    - a certidão reprográfica: uma página do termo por folha, com o selo, e a
      emissão pela ficha que congela o arquivo pelo sha256;
    - a carga por programa (`anexar_digitalizacao`): não passa por cima do que
      o balcão enviou, não cria nem baixa pendência, e é idempotente; e o teor
      transcrito só entra onde o teor está vazio.
"""
from __future__ import annotations

import io
import re
import sqlite3
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import rc_digitalizacao as RCDIGI

SELO_REGISTRO = "REGNAS000000PROBLEMA121X"
CORTE = "2026-10-01T00:00:00"


# ------------------------------------------------------------------ ajudantes

def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _con(casa) -> sqlite3.Connection:
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _png(cor="white", tamanho=(60, 80)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", tamanho, cor).save(buf, format="PNG")
    return buf.getvalue()


def _pdf_de_duas_paginas(caminho: Path) -> Path:
    from PIL import Image
    a = Image.new("RGB", (620, 877), "white")
    b = Image.new("RGB", (620, 877), "lightgray")
    a.save(caminho, format="PDF", save_all=True, append_images=[b])
    return caminho


def _corte(casa, valor=CORTE):
    con = _con(casa)
    with con:
        con.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (RCDIGI.CHAVE_DO_CORTE, valor))
    con.close()


def _assento(casa, *, origem="MANUAL", criado_em="2026-10-05T10:00:00",
             especie="NASCIMENTO", situacao="ATIVO", numero=19600,
             com_registro=True, teor=None) -> int:
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos(serie, especie, numero, nome, data_ato,
                   data_fato, dados_json, teor, situacao, origem, origem_chave,
                   criado_em)
               VALUES ('RC_A', ?, ?, 'REGISTRADO DO TERMO', ?, '2026-09-30',
                       '{}', ?, ?, ?, ?, ?)""",
            (especie, numero, criado_em[:10], teor, situacao, origem,
             None if origem == "MANUAL" else f"t121:{numero}:{criado_em}",
             criado_em))
        aid = int(cur.lastrowid)
        if com_registro:
            con.execute(
                """INSERT INTO rc_atos(assento_id, tipo, folha, numero_ordem,
                       rotulo, data_ato, selo, origem, criado_em)
                   VALUES (?, 'REGISTRO', 12, ?, '12', ?, ?, 'MANUAL', ?)""",
                (aid, numero, criado_em[:10], SELO_REGISTRO, criado_em))
        for papel, quem, ordem in (("PAI", "JOSÉ DO TERMO", 1),
                                   ("MAE", "MARIA DO TERMO", 2)):
            con.execute(
                """INSERT INTO rc_pessoas(assento_id, papel, nome, ordem,
                       origem, criado_em) VALUES (?,?,?,?,'MANUAL',?)""",
                (aid, papel, quem, ordem, criado_em))
    con.close()
    return aid


def _enviar(casa, aid: int, conteudo: bytes, nome: str):
    c = casa["c"]
    ficha = c.get(f"/rcpn/{aid}").get_data(as_text=True)
    return c.post(f"/rcpn/{aid}/digitalizacao",
                  data={"csrf_token": _token(ficha),
                        "arquivo": (io.BytesIO(conteudo), nome)},
                  content_type="multipart/form-data", follow_redirects=True)


def _pendentes(casa, hoje=date(2026, 10, 8)) -> list[int]:
    con = _con(casa)
    try:
        return [p["id"] for p in RCDIGI.pendentes(con, hoje)]
    finally:
        con.close()


# ------------------------------------------------------------------ migração

def test_a_migracao_cria_as_colunas_e_semeia_o_corte_uma_vez(cg_casa):
    con = _con(cg_casa)
    colunas = {r[1] for r in con.execute("PRAGMA table_info(rc_assentos)")}
    assert {"digi_path", "digi_nome", "digi_sha256", "digi_em", "digi_por",
            "digi_origem"} <= colunas
    cert = {r[1] for r in con.execute("PRAGMA table_info(rc_certidoes)")}
    assert "digitalizacao_sha256" in cert
    semeado = con.execute("SELECT value FROM settings WHERE key=?",
                          (RCDIGI.CHAVE_DO_CORTE,)).fetchone()
    assert semeado and re.match(r"\d{4}-\d{2}-\d{2}T", semeado[0])

    # «A PARTIR DA INSTALAÇÃO»: abrir o banco de novo não regrava o corte.
    from rc_schema import init_rc_schema
    with con:
        con.execute("UPDATE settings SET value=? WHERE key=?",
                    (CORTE, RCDIGI.CHAVE_DO_CORTE))
        init_rc_schema(con)
    assert con.execute("SELECT value FROM settings WHERE key=?",
                       (RCDIGI.CHAVE_DO_CORTE,)).fetchone()[0] == CORTE
    con.close()


def test_banco_sem_settings_nao_estoura_e_nao_obriga():
    import nucleo_schema
    from rc_schema import init_rc_schema
    con = conexao_de_teste()
    nucleo_schema.init_nucleo_schema(con)
    init_rc_schema(con)
    assert RCDIGI.obrigatoria_desde(con) is None
    assert RCDIGI.pendentes(con) == []
    con.close()


# ------------------------------------------------------------------ envio

def test_o_envio_pela_ficha_guarda_audita_e_a_ficha_mostra(cg_casa_logada):
    casa = cg_casa_logada
    _corte(casa)
    aid = _assento(casa)
    r = _enviar(casa, aid, _png(), "termo-19600.png")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Termo digitalizado guardado" in html

    con = _con(casa)
    row = con.execute("SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone()
    assert row["digi_nome"] == "termo-19600.png"
    assert row["digi_origem"] == "BALCAO"
    assert row["digi_sha256"] and row["digi_por"]
    caminho = Path(row["digi_path"])
    assert caminho.is_file()
    assert caminho.parent.name == str(aid)
    assert caminho.parent.parent.name == "digitalizacoes"
    assert con.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action='RCPN_DIGITALIZACAO_ATUALIZADA'"
        " AND entity_id=?", (aid,)).fetchone()[0] == 1
    con.close()

    # A ficha mostra o termo: miniatura e o arquivo que abre na tela.
    assert f"/rcpn/{aid}/digitalizacao/miniatura" in html
    assert f"/rcpn/{aid}/digitalizacao/arquivo?visualizar=1" in html
    assert "Emitir reprográfica da digitalização" in html
    mini = casa["c"].get(f"/rcpn/{aid}/digitalizacao/miniatura")
    assert mini.status_code == 200 and mini.data[:4] == b"\x89PNG"
    ver = casa["c"].get(f"/rcpn/{aid}/digitalizacao/arquivo?visualizar=1")
    assert ver.status_code == 200
    assert ver.headers["Content-Disposition"].startswith("inline")


def test_o_segundo_envio_guarda_o_primeiro_no_historico(cg_casa_logada):
    casa = cg_casa_logada
    _corte(casa)
    aid = _assento(casa)
    _enviar(casa, aid, _png("white"), "primeiro.png")
    _enviar(casa, aid, _png("black"), "segundo.png")
    con = _con(casa)
    row = con.execute("SELECT digi_nome, digi_path FROM rc_assentos WHERE id=?",
                      (aid,)).fetchone()
    con.close()
    assert row["digi_nome"] == "segundo.png"
    historico = Path(row["digi_path"]).parent / "historico"
    nomes = [p.name for p in historico.iterdir()]
    assert len(nomes) == 1 and nomes[0].endswith("primeiro.png")


def test_formato_errado_e_recusado_com_frase(cg_casa_logada):
    casa = cg_casa_logada
    aid = _assento(casa)
    r = _enviar(casa, aid, b"nao sou pdf", "termo.docx")
    assert "Formato não aceito" in r.get_data(as_text=True)
    con = _con(casa)
    assert con.execute("SELECT digi_path FROM rc_assentos WHERE id=?",
                       (aid,)).fetchone()[0] is None
    con.close()


# ------------------------------------------------------------------ pendência

def test_a_pendencia_e_so_do_registro_lavrado_aqui_depois_do_corte(cg_casa):
    casa = cg_casa
    _corte(casa)
    novo = _assento(casa, numero=1)
    antes = _assento(casa, numero=2, criado_em="2026-09-20T10:00:00")
    importado = _assento(casa, numero=3, origem="IMPORTACAO")
    eoficio = _assento(casa, numero=4, origem="EOFICIO")
    digitado = _assento(casa, numero=5, origem="ARQUIVO")
    cancelado = _assento(casa, numero=6, situacao="CANCELADO")
    proclama = _assento(casa, numero=7, especie="PROCLAMAS")
    # «2026-10-01 09:00:00» com ESPAÇO é depois do corte: a comparação
    # normaliza, e não compara o espaço (32) com o `T` (84).
    com_espaco = _assento(casa, numero=8, criado_em="2026-10-01 09:00:00")
    assert sorted(_pendentes(casa)) == sorted([novo, com_espaco])
    for fora in (antes, importado, eoficio, digitado, cancelado, proclama):
        assert fora not in _pendentes(casa)


def test_o_prazo_e_de_sete_dias_corridos(cg_casa):
    casa = cg_casa
    _corte(casa)
    aid = _assento(casa, criado_em="2026-10-02T15:00:00")
    con = _con(casa)
    dentro = RCDIGI.situacao(con, aid, hoje=date(2026, 10, 9))
    fora = RCDIGI.situacao(con, aid, hoje=date(2026, 10, 10))
    con.close()
    assert dentro["pendente"] and not dentro["vencida"]
    assert dentro["prazo"] == date(2026, 10, 9)
    assert fora["vencida"] and fora["dias"] == 8


def test_o_envio_do_balcao_baixa_a_pendencia(cg_casa_logada):
    casa = cg_casa_logada
    _corte(casa)
    aid = _assento(casa)
    assert aid in _pendentes(casa)
    _enviar(casa, aid, _png(), "termo.png")
    assert aid not in _pendentes(casa)


def test_a_lista_e_o_aviso_vermelho_aparecem_e_nao_travam(cg_casa_logada):
    casa = cg_casa_logada
    # Lavrado bem antes de hoje, para o prazo de 7 dias já ter vencido
    # qualquer que seja o dia em que o teste roda.
    _corte(casa, "2026-01-01T00:00:00")
    vencido = _assento(casa, criado_em="2026-01-05T08:00:00", numero=777)
    lista = casa["c"].get("/rcpn/termos-a-digitalizar")
    assert lista.status_code == 200
    texto = lista.get_data(as_text=True)
    assert f"/rcpn/{vencido}#termo-digitalizado" in texto
    assert "VENCIDO" in texto
    # O aviso vermelho sobe nas telas do Registro Civil (hoje > 08/10).
    ficha = casa["c"].get(f"/rcpn/{vencido}").get_data(as_text=True)
    assert "sem o termo assinado" in ficha
    assert "PRAZO VENCIDO" in ficha
    # E não trava a certidão: o formulário de emitir continua na ficha.
    assert f"/rcpn/{vencido}/certidao" in ficha


# ------------------------------------------------------------------ certidão

def test_o_odt_reprografico_traz_uma_pagina_por_folha_e_o_selo(tmp_path):
    pdf = _pdf_de_duas_paginas(tmp_path / "termo.pdf")
    certidao = {
        "numero": 9, "ano": 2026, "modalidade": "INTEIRO_REPRO",
        "imagem_caminho": str(pdf), "digitalizacao_sha256": "abc",
        "teor": "CERTIDÃO DE INTEIRO TEOR DE NASCIMENTO\n\nCERTIFICO E DOU FÉ "
                "que [...] na imagem abaixo.\n\n[Cópia reprográfica do assento "
                "anexa a esta certidão.]",
        "selo": "CERTID000000ABCDEFGHIJKLMNO1", "emitida_por": "ESCREVENTE TESTE",
    }
    sv = {"unit_name": "Serventia", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
    odt = RCDIGI.odt_da_certidao(certidao, sv, hoje_extenso="8 de outubro de 2026")
    assert odt[:4] == b"PK\x03\x04"
    with zipfile.ZipFile(io.BytesIO(odt)) as z:
        xml = z.read("content.xml").decode("utf-8")
        nomes = z.namelist()
    assert "Pictures/rcdigi1.png" in nomes and "Pictures/rcdigi2.png" in nomes
    assert xml.count('text:style-name="P-rcdigi-pagina"') == 2
    assert "Era o que cabia certificar." in xml
    assert "ESCREVENTE TESTE" in xml
    assert "##IMG_REPRO##" not in xml and "@@SELO@@" not in xml
    for w, h in re.findall(r'draw:name="rcdigi\d\.png"[^>]*svg:width="([0-9.]+)cm"'
                           r'[^>]*svg:height="([0-9.]+)cm"', xml):
        assert float(w) <= RCDIGI.AREA_W_CM and float(h) <= RCDIGI.AREA_H_CM


def test_a_ficha_emite_a_reprografica_da_digitalizacao(cg_casa_logada, tmp_path):
    casa = cg_casa_logada
    _corte(casa)
    aid = _assento(casa)
    pdf = _pdf_de_duas_paginas(tmp_path / "termo.pdf").read_bytes()
    _enviar(casa, aid, pdf, "termo-assinado.pdf")

    import papel_seguranca as PP
    con = _con(casa)
    with con:
        PP.receber_remessa(con, fornecedor="TESTE", codigo_de="7000001",
                           codigo_ate="7000003", agora="2026-10-08T09:00:00")
    con.close()

    ficha = casa["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
    r = casa["c"].post(f"/rcpn/{aid}/certidao", data={
        "csrf_token": _token(ficha), "tipo_certidao": "resumo",
        "usar_digitalizacao": "1", "folha_seguranca": "7000001",
        "requerente": "O PRÓPRIO"}, follow_redirects=True)
    assert r.status_code == 200
    assert "emitida" in r.get_data(as_text=True).lower()

    con = _con(casa)
    row = con.execute(
        """SELECT id, modalidade, imagem_caminho, digitalizacao_sha256,
                  cancelada_em FROM rc_certidoes WHERE assento_id=?""",
        (aid,)).fetchone()
    digi = con.execute("SELECT digi_sha256 FROM rc_assentos WHERE id=?",
                       (aid,)).fetchone()[0]
    auditado = con.execute(
        "SELECT details FROM audit_logs WHERE action='RCPN_CERTIDAO' "
        "AND entity_id=?", (row["id"],)).fetchone()[0]
    con.close()
    assert row["modalidade"] == "INTEIRO_REPRO"
    assert row["cancelada_em"] is None
    assert row["digitalizacao_sha256"] == digi
    assert digi in auditado
    congelada = Path(row["imagem_caminho"])
    assert congelada.is_file() and congelada.parent.name == "certidoes"

    odt = casa["c"].get(f"/rcpn/certidoes/{row['id']}/odt?formato=odt")
    assert odt.status_code == 200
    with zipfile.ZipFile(io.BytesIO(odt.data)) as z:
        assert "Pictures/rcdigi2.png" in z.namelist()


def test_sem_termo_digitalizado_a_reprografica_e_recusada(cg_casa_logada):
    casa = cg_casa_logada
    aid = _assento(casa)
    ficha = casa["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
    assert "Emitir reprográfica da digitalização" not in ficha
    r = casa["c"].post(f"/rcpn/{aid}/certidao", data={
        "csrf_token": _token(ficha), "usar_digitalizacao": "1",
        "folha_seguranca": "1"}, follow_redirects=True)
    assert "não tem o termo digitalizado" in r.get_data(as_text=True)
    con = _con(casa)
    assert con.execute("SELECT COUNT(*) FROM rc_certidoes WHERE assento_id=?",
                       (aid,)).fetchone()[0] == 0
    con.close()


# ------------------------------------------------------------------ carga

def test_anexar_por_programa_vira_oficial_e_nao_cria_pendencia(cg_casa, tmp_path):
    casa = cg_casa
    _corte(casa)
    importado = _assento(casa, origem="IMPORTACAO", numero=11)
    arq = tmp_path / "acervo-11.png"
    arq.write_bytes(_png())
    r = RCDIGI.anexar_digitalizacao(casa["db"], importado, arq, "CARGA ACERVO")
    assert r["acao"] == "OFICIAL"
    con = _con(casa)
    row = con.execute("SELECT * FROM rc_assentos WHERE id=?",
                      (importado,)).fetchone()
    assert row["digi_origem"] == "ACERVO_TRANSCRITO"
    assert Path(row["digi_path"]).is_file()
    assert con.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action='RCPN_DIGITALIZACAO_ANEXADA'"
        " AND entity_id=?", (importado,)).fetchone()[0] == 1
    con.close()
    assert importado not in _pendentes(casa)
    # Idempotente: o mesmo arquivo de novo não muda nada.
    assert RCDIGI.anexar_digitalizacao(
        casa["db"], importado, arq, "CARGA ACERVO")["acao"] == "IGUAL"


def test_anexar_nao_passa_por_cima_do_que_o_balcao_enviou(cg_casa_logada, tmp_path):
    casa = cg_casa_logada
    _corte(casa)
    aid = _assento(casa)
    _enviar(casa, aid, _png("white"), "do-balcao.png")
    arq = tmp_path / "da-carga.png"
    arq.write_bytes(_png("black"))
    r = RCDIGI.anexar_digitalizacao(casa["db"], aid, arq, "CARGA ACERVO")
    assert r["acao"] == "REFERENCIA"
    assert Path(r["path"]).parent.name == "referencia"
    con = _con(casa)
    row = con.execute("SELECT digi_nome, digi_origem FROM rc_assentos WHERE id=?",
                      (aid,)).fetchone()
    con.close()
    assert row["digi_nome"] == "do-balcao.png"
    assert row["digi_origem"] == "BALCAO"


def test_anexar_nao_baixa_a_pendencia_do_registro_novo(cg_casa, tmp_path):
    """O termo assinado é o papel que o balcão tem na mão: só o envio de
    pessoa baixa a pendência do registro lavrado aqui."""
    casa = cg_casa
    _corte(casa)
    aid = _assento(casa)
    arq = tmp_path / "x.png"
    arq.write_bytes(_png())
    RCDIGI.anexar_digitalizacao(casa["db"], aid, arq, "CARGA ACERVO")
    assert aid in _pendentes(casa)


def test_anexar_com_conexao_crua_escreve_na_transacao_de_quem_chama(cg_casa, tmp_path):
    casa = cg_casa
    aid = _assento(casa, origem="EOFICIO", numero=12)
    arq = tmp_path / "y.png"
    arq.write_bytes(_png())
    con = _con(casa)
    configurada = (con.execute(
        "SELECT value FROM settings WHERE key='archive_root'").fetchone() or [""])[0]
    if not (configurada or "").strip():
        # Sem `archive_root` e sem `raiz_arquivos=`, a conexão crua não sabe
        # onde fica a pasta — e diz isso, em vez de gravar num lugar chutado.
        with pytest.raises(RCDIGI.DigitalizacaoError, match="raiz_arquivos"):
            RCDIGI.anexar_digitalizacao(con, aid, arq, "CARGA")
    r = RCDIGI.anexar_digitalizacao(con, aid, arq, "CARGA",
                                    raiz_arquivos=tmp_path / "arquivos")
    assert r["acao"] == "OFICIAL"
    con.rollback()
    assert con.execute("SELECT digi_path FROM rc_assentos WHERE id=?",
                       (aid,)).fetchone()[0] is None, (
        "com conexão crua, quem decide o commit é quem chamou")
    con.close()


def test_o_teor_transcrito_so_entra_onde_esta_vazio(cg_casa):
    casa = cg_casa
    vazio = _assento(casa, origem="IMPORTACAO", numero=21)
    cheio = _assento(casa, origem="IMPORTACAO", numero=22,
                     teor="Teor que já estava lá.")
    assert RCDIGI.gravar_teor_transcrito(
        casa["db"], vazio, "Aos oito dias...", "CARGA ACERVO") is True
    assert RCDIGI.gravar_teor_transcrito(
        casa["db"], cheio, "Outro texto", "CARGA ACERVO") is False
    con = _con(casa)
    assert con.execute("SELECT teor FROM rc_assentos WHERE id=?",
                       (vazio,)).fetchone()[0] == "Aos oito dias..."
    assert con.execute("SELECT teor FROM rc_assentos WHERE id=?",
                       (cheio,)).fetchone()[0] == "Teor que já estava lá."
    assert con.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action='RCPN_TEOR_TRANSCRITO'"
        ).fetchone()[0] == 1
    con.close()
    with pytest.raises(RCDIGI.DigitalizacaoError):
        RCDIGI.gravar_teor_transcrito(casa["db"], vazio, "   ", "CARGA")


def test_a_origem_de_pessoa_nao_se_usa_por_programa(cg_casa, tmp_path):
    casa = cg_casa
    aid = _assento(casa, origem="IMPORTACAO", numero=31)
    arq = tmp_path / "z.png"
    arq.write_bytes(_png())
    with pytest.raises(RCDIGI.DigitalizacaoError):
        RCDIGI.anexar_digitalizacao(casa["db"], aid, arq, "CARGA", origem="BALCAO")
