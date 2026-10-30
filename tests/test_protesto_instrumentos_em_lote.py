"""OS INSTRUMENTOS EM LOTE — pedido do oficial, 29/10/2026.

    «não quero ter que clicar um por um, tem que ter a opção de selecionar
     todos instrumentos pendentes»

Havia 18 protestos de 28/10 esperando, e a tela pedia «Emitir» em cada um e
depois «Assinar» em cada instrumento. Medido na produção nesse dia (só
leitura): 1.207 protestos sem instrumento, 1.186 do acervo do E-Ofício e 21
lavrados neste sistema.

O QUE ESTES TESTES GUARDAM
      - **o que se junta é o clique, e não o ato**: cada instrumento sai com
        o seu número, e cada título vai na sua própria transação — um que
        falha não derruba os outros, e a falha volta com o motivo;
      - **título que já tem instrumento não ganha segunda via no lote**;
      - **a fila separa o acervo do E-Ofício dos lavrados neste sistema**, e
        os atalhos de data recortam sem esconder o número de cada pedaço;
      - **a assinatura em lote manda todos os PDFs de uma vez** (o PowerShell
        único está em `test_a3_windows_lote.py`), grava item a item e **para na
        primeira falha do token** — PIN errado em sequência bloqueia o A3 —,
        guardando o que já foi assinado;
      - a falha do PAPEL não para os outros, e o papel que não saiu nem vai ao
        token;
      - **o serviço local antigo cai no um por um**, com aviso;
      - o já assinado não vai ao token de novo;
      - a tela manda o `csrf_token`, tem «marcar todos» e diz como o PIN
        funciona; e continua sem campo de PIN.

Dados fictícios (LGPD): a lista de `tests/fixtures/anti_vazamento`.
"""
from __future__ import annotations

import base64
import re
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prova_de_intimacao import juntar_prova  # noqa: E402

import protesto_instrumento as PI  # noqa: E402

from test_protesto_instrumento import (  # noqa: E402
    AGORA, SERVENTIA, banco, protestado)
from test_protesto_instrumento_assinado import (  # noqa: E402,F401
    PDF, SV, _assinar, chave_e_cert)
from test_protesto_aviso_web import _con, _token, s  # noqa: E402,F401


def _transacao_de(con):
    """O `db.transaction` do teste: a mesma conexão, com o `with` dela."""
    @contextmanager
    def transacao():
        with con:
            yield con
    return transacao


# ------------------------------------------------------ emitir em lote


def test_o_lote_emite_cada_um_com_o_seu_numero():
    con = banco()
    a = protestado(con)
    b = protestado(con, numero_titulo="00124", protocolo="2606090002")
    r = PI.emitir_lote(_transacao_de(con), [a, b], serventia=SERVENTIA,
                       agora=AGORA)
    assert [f["titulo_id"] for f in r["feitos"]] == [a, b]
    assert sorted(f["numero"] for f in r["feitos"]) == [1, 2]
    assert r["falharam"] == []
    # cada um entrou na fila de assinatura da casa, como o de um só
    n = con.execute("SELECT COUNT(*) FROM as_documentos WHERE entidade=?",
                    (PI.ENTIDADE_DA_ASSINATURA,)).fetchone()[0]
    assert n == 2
    assert PI.a_entregar(con) == []


def test_um_que_falha_nao_derruba_os_outros_e_diz_o_motivo():
    con = banco()
    a = protestado(con)
    sem_motivo = protestado(con, numero_titulo="00124",
                            protocolo="2606090002", motivo_protesto="")
    c = protestado(con, numero_titulo="00125", protocolo="2606090003")
    r = PI.emitir_lote(_transacao_de(con), [a, sem_motivo, c],
                       serventia=SERVENTIA, agora=AGORA)
    assert [f["titulo_id"] for f in r["feitos"]] == [a, c]
    assert len(r["falharam"]) == 1
    assert r["falharam"][0]["titulo_id"] == sem_motivo
    assert "motivo do protesto" in r["falharam"][0]["motivo"]


def test_o_que_ja_tem_instrumento_nao_ganha_segunda_via_no_lote():
    con = banco()
    a = protestado(con)
    PI.emitir(con, a, serventia=SERVENTIA, agora=AGORA)
    # O título que falha tem a transação desfeita; nesta conexão única do
    # teste, sem gravar antes, o desfazer levava junto as tabelas criadas
    # acima (no PostgreSQL a criação de tabela entra na transação).
    con.commit()
    r = PI.emitir_lote(_transacao_de(con), [a], serventia=SERVENTIA,
                       agora=AGORA)
    assert r["feitos"] == []
    assert "Segunda via" in r["falharam"][0]["motivo"]
    n = con.execute("SELECT COUNT(*) FROM pt_instrumentos WHERE titulo_id=?",
                    (a,)).fetchone()[0]
    assert n == 1


def test_o_mesmo_titulo_marcado_duas_vezes_sai_uma_vez():
    con = banco()
    a = protestado(con)
    r = PI.emitir_lote(_transacao_de(con), [a, a, str(a)],
                       serventia=SERVENTIA, agora=AGORA)
    assert len(r["feitos"]) == 1
    assert r["falharam"] == []


def test_nada_marcado_recusa_com_frase_e_o_teto_se_diz():
    con = banco()
    with pytest.raises(PI.InstrumentoError, match="Marque"):
        PI.emitir_lote(_transacao_de(con), [], serventia=SERVENTIA,
                       agora=AGORA)
    demais = list(range(1, PI.LIMITE_DO_LOTE_DE_EMISSAO + 2))
    with pytest.raises(PI.InstrumentoError, match="de cada vez"):
        PI.emitir_lote(_transacao_de(con), demais, serventia=SERVENTIA,
                       agora=AGORA)


def test_o_modelo_da_casa_e_lido_dentro_da_transacao_de_cada_um():
    con = banco()
    a = protestado(con)
    vistos = []

    def modelo_de(c):
        vistos.append(c)
        return None
    PI.emitir_lote(_transacao_de(con), [a], serventia=SERVENTIA, agora=AGORA,
                   modelo_de=modelo_de)
    assert vistos == [con]


# ------------------------------------------------------ a fila recortada


def _do_acervo(con, titulo_id):
    con.execute("UPDATE pt_atos SET origem='EOFICIO' WHERE titulo_id=?",
                (titulo_id,))


def test_a_fila_separa_o_acervo_dos_lavrados_neste_sistema():
    con = banco()
    novo = protestado(con)
    velho = protestado(con, numero_titulo="00124", protocolo="2606090002")
    _do_acervo(con, velho)
    assert [r["titulo_id"] for r in PI.a_entregar(con, quais="sistema")] == [novo]
    assert [r["titulo_id"] for r in PI.a_entregar(con, quais="acervo")] == [velho]
    assert len(PI.a_entregar(con)) == 2
    q = PI.quadro_da_fila(con, hoje="2026-06-13")
    assert (q["todos"], q["sistema"], q["acervo"]) == (2, 1, 1)


def test_os_atalhos_de_data_recortam_e_o_mais_novo_vem_primeiro():
    con = banco()
    hoje = protestado(con)  # protesto de 13/06
    ontem = protestado(con, numero_titulo="00124", protocolo="2606090002")
    con.execute("UPDATE pt_atos SET data_ato='2026-06-12 09:30:00' "
                "WHERE titulo_id=? AND tipo='PROTESTO'", (ontem,))
    antigo = protestado(con, numero_titulo="00125", protocolo="2606090003")
    con.execute("UPDATE pt_atos SET data_ato='2025-01-02' "
                "WHERE titulo_id=? AND tipo='PROTESTO'", (antigo,))
    dia = "2026-06-13"
    assert PI.desde_do_atalho("hoje", dia) == "2026-06-13"
    assert PI.desde_do_atalho("ontem", dia) == "2026-06-12"
    assert PI.desde_do_atalho("semana", dia) == "2026-06-07"
    assert PI.desde_do_atalho("qualquer", dia) is None
    so_hoje = PI.a_entregar(con, desde=PI.desde_do_atalho("hoje", dia))
    assert [r["titulo_id"] for r in so_hoje] == [hoje]
    # a data com hora junto (como 21 da produção) entra no recorte
    dois = PI.a_entregar(con, desde=PI.desde_do_atalho("ontem", dia))
    assert [r["titulo_id"] for r in dois] == [hoje, ontem]
    assert [r["titulo_id"] for r in PI.a_entregar(con)] == [hoje, ontem, antigo]
    q = PI.quadro_da_fila(con, hoje=dia)
    assert q["por_atalho"]["todos"] == {"hoje": 1, "ontem": 2, "semana": 2}


# ------------------------------------------------------ assinar em lote


def _lote(ids, *, preparar=None, varios=None, guardar=None, um=None):
    """`PI.assinar_lote` com as peças simuladas. Sem `um`, cair nele é defeito."""
    return PI.assinar_lote(
        ids,
        preparar=preparar or (lambda iid: b"PDF:%d" % iid),
        assinar_varios=varios or (lambda pdfs: {
            "assinados": {i: b"P7S:" + x for i, x in enumerate(pdfs)},
            "falha": None}),
        guardar=guardar or (lambda iid, pdf, p7s: {"instrumento_id": iid,
                                                   "pdf": pdf, "p7s": p7s}),
        assinar_um=um or (lambda iid: pytest.fail("não devia cair no um por um")))


def test_o_lote_manda_todos_de_uma_vez_e_grava_cada_um():
    chamadas = []

    def varios(pdfs):
        chamadas.append(list(pdfs))
        return {"assinados": {i: b"P7S:" + x for i, x in enumerate(pdfs)},
                "falha": None}
    r = _lote([1, 2, 3], varios=varios)
    assert chamadas == [[b"PDF:1", b"PDF:2", b"PDF:3"]]
    assert [f["instrumento_id"] for f in r["feitos"]] == [1, 2, 3]
    assert r["feitos"][1]["pdf"] == b"PDF:2"
    assert r["feitos"][1]["p7s"] == b"P7S:PDF:2"
    assert r["falharam"] == [] and r["nao_tentados"] == []
    assert r["parou"] is False and r["aviso"] is None


def test_o_papel_que_nao_sai_nao_vai_ao_token_e_nao_para_os_outros():
    vistos = []

    def preparar(iid):
        if iid == 2:
            raise PI.InstrumentoError("o PDF não saiu")
        return b"PDF:%d" % iid

    def varios(pdfs):
        vistos.extend(pdfs)
        return {"assinados": {i: b"P7S" for i in range(len(pdfs))}, "falha": None}
    r = _lote([1, 2, 3], preparar=preparar, varios=varios)
    assert vistos == [b"PDF:1", b"PDF:3"]
    assert [f["instrumento_id"] for f in r["feitos"]] == [1, 3]
    assert r["falharam"] == [{"instrumento_id": 2, "motivo": "o PDF não saiu"}]
    assert r["parou"] is False


def test_sem_nenhum_papel_pronto_o_token_nem_e_chamado():
    def preparar(iid):
        raise PI.JaAssinado("já foi assinado")
    r = _lote([1], preparar=preparar,
              varios=lambda pdfs: pytest.fail("não devia ir ao token"))
    assert r["feitos"] == [] and r["parou"] is False
    assert "já foi assinado" in r["falharam"][0]["motivo"]


def test_a_falha_do_token_para_o_lote_e_guarda_o_que_ja_foi_assinado():
    """PIN errado em sequência bloqueia o A3: depois da falha, nada mais vai ao
    token, e o que saiu antes dela fica valendo."""
    gravados = []

    def guardar(iid, pdf, p7s):
        gravados.append(iid)
        return {"instrumento_id": iid}

    def varios(pdfs):
        return {"assinados": {0: b"P7S"},
                "falha": "o PIN não foi aceito pelo token."}
    r = _lote([1, 2, 3, 4], varios=varios, guardar=guardar)
    assert gravados == [1]
    assert [f["instrumento_id"] for f in r["feitos"]] == [1]
    assert r["parou"] is True
    assert r["nao_tentados"] == [3, 4]
    assert r["falharam"] == [{"instrumento_id": 2,
                              "motivo": "o PIN não foi aceito pelo token."}]


def test_o_servico_fora_do_ar_para_o_lote_sem_nada_assinado():
    def varios(pdfs):
        raise PI.AssinaturaInterrompida("o serviço não está no ar")
    r = _lote([1, 2, 3], varios=varios)
    assert r["feitos"] == []
    assert r["parou"] is True and r["nao_tentados"] == [2, 3]
    assert r["falharam"][0]["instrumento_id"] == 1


def test_a_assinatura_que_nao_confere_e_daquele_instrumento_so():
    def guardar(iid, pdf, p7s):
        if iid == 2:
            raise PI.InstrumentoError("A assinatura não confere com o instrumento")
        return {"instrumento_id": iid}
    r = _lote([1, 2, 3], guardar=guardar)
    assert [f["instrumento_id"] for f in r["feitos"]] == [1, 3]
    assert r["falharam"][0]["instrumento_id"] == 2
    assert r["parou"] is False and r["nao_tentados"] == []


def test_o_erro_inesperado_ao_gravar_nao_perde_os_outros_ja_assinados():
    def guardar(iid, pdf, p7s):
        if iid == 1:
            raise RuntimeError("banco fora")
        return {"instrumento_id": iid}
    r = _lote([1, 2], guardar=guardar)
    assert [f["instrumento_id"] for f in r["feitos"]] == [2]
    assert "erro inesperado" in r["falharam"][0]["motivo"]


def test_o_servico_antigo_cai_no_um_por_um_com_aviso():
    um = []

    def varios(pdfs):
        raise PI.LoteIndisponivel("o serviço é de uma versão anterior")

    def preparar(iid):
        if iid == 2:
            raise PI.InstrumentoError("o PDF não saiu")
        return b"PDF"

    def assinar_um(iid):
        um.append(iid)
        return {"instrumento_id": iid}
    r = _lote([1, 2, 3], preparar=preparar, varios=varios, um=assinar_um)
    assert um == [1, 3]
    assert [f["instrumento_id"] for f in r["feitos"]] == [1, 3]
    assert r["falharam"][0]["instrumento_id"] == 2
    assert "versão anterior" in r["aviso"]


def test_na_queda_o_um_por_um_tambem_para_na_falha_do_token():
    chamados = []

    def assinar_um(iid):
        chamados.append(iid)
        if iid == 2:
            raise PI.AssinaturaInterrompida("o PIN não foi aceito pelo token.")
        return {"instrumento_id": iid}

    def varios(pdfs):
        raise PI.LoteIndisponivel("versão anterior")
    r = _lote([1, 2, 3, 4], varios=varios, um=assinar_um)
    assert chamados == [1, 2]
    assert r["parou"] is True
    assert r["nao_tentados"] == [3, 4]
    assert "PIN" in r["falharam"][0]["motivo"]


def test_o_um_por_um_segue_quando_a_falha_e_do_papel():
    def assinar_um(iid):
        if iid == 2:
            raise PI.InstrumentoError("A assinatura não confere com o instrumento")
        return {"instrumento_id": iid}
    r = PI.assinar_um_por_um([1, 2, 3], assinar_um)
    assert [f["instrumento_id"] for f in r["feitos"]] == [1, 3]
    assert r["falharam"][0]["instrumento_id"] == 2
    assert r["parou"] is False and r["nao_tentados"] == []


def test_o_lote_de_assinatura_tem_teto_e_recusa_vazio():
    with pytest.raises(PI.InstrumentoError, match="Marque"):
        _lote([])
    demais = list(range(1, PI.LIMITE_DO_LOTE_DE_ASSINATURA + 2))
    with pytest.raises(PI.InstrumentoError, match="de cada vez"):
        _lote(demais, preparar=lambda iid: pytest.fail("não devia preparar"))


def test_a_regra_do_pin_esta_escrita_onde_o_lote_mora():
    """O que não se mediu fica dito na função, e não só no PR: a janela única
    é hipótese, e o caminho é a rota de lote."""
    doc = PI.assinar_lote.__doc__ or ""
    assert "HIPÓTESE" in doc
    assert "/assinar/pdfs-windows" in doc


# ------------------------------------------------------ as telas


def _emitidos(s):
    con = _con(s)
    try:
        return con.execute("SELECT COUNT(*) FROM pt_instrumentos").fetchone()[0]
    finally:
        con.close()


def _protestado_pela_casa(s, n: int = 1) -> int:
    """Um título protestado pelo domínio. `n` muda a chave de origem: a mesma
    chave devolveria o MESMO título (a carga é repetível por construção)."""
    import sqlite3

    import protesto as PT
    from database import Database
    db = Database(s["banco"])
    agora = db.now()
    with db.transaction() as con:
        con.row_factory = sqlite3.Row
        tid = PT.cadastrar_titulo(con, {
            "apresentante_codigo": "001", "apresentante_nome": "BANCO EXEMPLO",
            "especie": "DMI", "numero_titulo": f"99{n:02d}/1",
            "nosso_numero": f"NNL{n:03d}", "data_emissao": "2026-01-05",
            "data_vencimento": "2026-02-05", "valor": "1200.00",
            "saldo": "1310.45", "praca_protesto": "CIDADE EXEMPLO",
            "cedente": {"nome": "EMPRESA DE EXEMPLO LTDA",
                        "documento": "00000001000055"},
            "devedores": [{"nome": "MARIO EXEMPLO DOS SANTOS", "CPF": "00000000191",
                           "enderecos": [{"endereco": "RUA GRANDE, 10",
                                          "bairro": "CENTRO",
                                          "cidade": "Cidade Exemplo",
                                          "uf": "MA"}]}],
        }, origem="CRA", origem_chave=f"lote-em-lote:{n}", agora=agora)
        PT.lancar_apontamento(con, tid, sv=SV, agora=agora,
                              data_extenso="vinte e cinco de agosto")
    con = _con(s)
    with con:
        PT.lancar_intimacao(con, tid, modo="PESSOAL",
                            agora="2026-10-10T10:00:00")
        con.execute("UPDATE pt_titulos SET motivo_protesto='1' WHERE id=?",
                    (tid,))
        juntar_prova(con, tid)   # a prova da intimação (29/10/2026)
        PT.lancar_protesto(con, tid, sv=SV, agora="2026-10-14T10:00:00",
                           data_extenso="x")
    con.close()
    return tid


def _instrumento(s, n: int = 1) -> int:
    tid = _protestado_pela_casa(s, n)
    con = _con(s)
    with con:
        r = PI.emitir(con, tid, serventia=SV["unit_name"],
                      agora="2026-10-14T11:00:00")
    con.close()
    return r["id"]


def test_a_tela_oferece_marcar_todos_e_os_dois_lotes(s):
    _protestado_pela_casa(s)
    html = s["c"].get("/protesto/instrumentos").get_data(as_text=True)
    assert "Emitir os marcados" in html
    assert 'name="titulo_id"' in html
    assert "data-marcar=\"titulo_id\"" in html
    assert "lavrados neste sistema" in html
    assert "do acervo do E-Ofício" in html
    for form in re.findall(r"<form[^>]*method=\"post\".*?</form>", html,
                           flags=re.S | re.I):
        assert 'name="csrf_token"' in form


def test_emitir_os_marcados_pela_tela(s):
    a = _protestado_pela_casa(s)
    html = s["c"].get("/protesto/instrumentos").get_data(as_text=True)
    r = s["c"].post("/protesto/instrumentos/emitir-lote",
                    data={"csrf_token": _token(html), "titulo_id": [str(a), "abc"]},
                    follow_redirects=True)
    assert r.status_code == 200
    assert "1 instrumento(s) emitido(s)" in r.get_data(as_text=True)
    assert _emitidos(s) == 1


def test_lote_sem_nada_marcado_volta_com_frase(s):
    _protestado_pela_casa(s)
    html = s["c"].get("/protesto/instrumentos").get_data(as_text=True)
    r = s["c"].post("/protesto/instrumentos/emitir-lote",
                    data={"csrf_token": _token(html)}, follow_redirects=True)
    assert r.status_code == 200
    assert "Marque os protestos" in r.get_data(as_text=True)


def test_a_tela_diz_como_o_pin_funciona_e_nao_pede_pin(s):
    _instrumento(s)
    html = s["c"].get("/protesto/instrumentos").get_data(as_text=True)
    assert "Instrumentos a assinar" in html
    assert "Assinar os marcados com o A3" in html
    assert "aparece no começo do lote" in html
    assert "uma vez para cada instrumento" not in html
    assert 'name="pin"' not in html


def _servico_de_lote(chave_e_cert, vistos, *, falha_em=None, outro_em=None):
    """O `assinar_pdfs_pelo_windows` simulado. `falha_em`: a posição em que o
    token falha. `outro_em`: a posição cuja assinatura embrulha outro papel."""
    def servico(pdfs, *, thumbprint=None):
        vistos.append(list(pdfs))
        itens = []
        for i, pdf in enumerate(pdfs):
            if i == falha_em:
                return {"ok": True, "itens": itens,
                        "falha": "o PIN não foi aceito pelo token."}
            conteudo = b"%PDF-1.4 OUTRO" if i == outro_em else pdf
            itens.append({"indice": i, "thumbprint": "ABC",
                          "cms_b64": base64.b64encode(
                              _assinar(chave_e_cert, conteudo)).decode("ascii")})
        return {"ok": True, "itens": itens, "falha": None}
    return servico


def _a_assinar(s):
    con = _con(s)
    try:
        return [r["id"] for r in PI.a_assinar(con)]
    finally:
        con.close()


def _postar_lote(s, ids):
    html = s["c"].get("/protesto/instrumentos").get_data(as_text=True)
    return s["c"].post("/protesto/instrumentos/assinar-lote",
                       data={"csrf_token": _token(html),
                             "instrumento_id": [str(x) for x in ids]},
                       follow_redirects=True)


def test_assinar_os_marcados_manda_os_pdfs_de_uma_vez(
        s, chave_e_cert, monkeypatch):
    import assinar_com_a3 as A3
    import impressao_pdf as IMPPDF
    monkeypatch.setattr(IMPPDF, "pdf_de_odt", lambda odt, **k: PDF)
    vistos = []
    monkeypatch.setattr(A3, "assinar_pdfs_pelo_windows",
                        _servico_de_lote(chave_e_cert, vistos))
    monkeypatch.setattr(A3, "assinar_pdf_pelo_windows",
                        lambda *a, **k: pytest.fail("não devia ir um por um"))
    a, b = _instrumento(s, 1), _instrumento(s, 2)
    r = _postar_lote(s, [a, b])
    assert r.status_code == 200
    assert vistos == [[PDF, PDF]]
    assert "2 instrumento(s) assinado(s)" in r.get_data(as_text=True)
    assert _a_assinar(s) == []
    # assinados, saem da lista do que falta assinar — e um segundo lote não
    # vai ao token de novo
    r2 = _postar_lote(s, [a])
    assert len(vistos) == 1
    assert "já foi assinado" in r2.get_data(as_text=True)


def test_a_falha_do_token_para_o_lote_e_o_assinado_fica_pela_tela(
        s, chave_e_cert, monkeypatch):
    import assinar_com_a3 as A3
    import impressao_pdf as IMPPDF
    monkeypatch.setattr(IMPPDF, "pdf_de_odt", lambda odt, **k: PDF)
    monkeypatch.setattr(A3, "assinar_pdfs_pelo_windows",
                        _servico_de_lote(chave_e_cert, [], falha_em=1))
    a, b, c = _instrumento(s, 1), _instrumento(s, 2), _instrumento(s, 3)
    texto = _postar_lote(s, [a, b, c]).get_data(as_text=True)
    assert "1 instrumento(s) assinado(s)" in texto
    assert "PIN não foi aceito" in texto
    assert "não foram tentados" in texto
    assert sorted(_a_assinar(s)) == sorted([b, c])


def test_o_servico_fora_do_ar_para_o_lote_pela_tela(s, monkeypatch):
    import assinar_com_a3 as A3
    import impressao_pdf as IMPPDF
    monkeypatch.setattr(IMPPDF, "pdf_de_odt", lambda odt, **k: PDF)

    def fora(pdfs, *, thumbprint=None):
        raise A3.AssinarComA3Error("o serviço local não está no ar")

    monkeypatch.setattr(A3, "assinar_pdfs_pelo_windows", fora)
    a, b = _instrumento(s, 1), _instrumento(s, 2)
    r = _postar_lote(s, [a, b])
    texto = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "não está no ar" in texto
    assert "não foram tentados" in texto
    assert sorted(_a_assinar(s)) == sorted([a, b])


def test_cada_p7s_se_confere_com_o_seu_pdf_e_o_que_nao_confere_nao_entra(
        s, chave_e_cert, monkeypatch):
    """A conferência é a de `assinar_um` (`guardar_assinatura`), byte a byte."""
    import assinar_com_a3 as A3
    import impressao_pdf as IMPPDF
    monkeypatch.setattr(IMPPDF, "pdf_de_odt", lambda odt, **k: PDF)
    monkeypatch.setattr(A3, "assinar_pdfs_pelo_windows",
                        _servico_de_lote(chave_e_cert, [], outro_em=0))
    a, b = _instrumento(s, 1), _instrumento(s, 2)
    texto = _postar_lote(s, [a, b]).get_data(as_text=True)
    assert "1 instrumento(s) assinado(s)" in texto
    assert "não confere" in texto
    assert "não foram tentados" not in texto
    assert _a_assinar(s) == [a]


def test_o_servico_antigo_cai_no_um_por_um_pela_tela(
        s, chave_e_cert, monkeypatch):
    import assinar_com_a3 as A3
    import impressao_pdf as IMPPDF
    monkeypatch.setattr(IMPPDF, "pdf_de_odt", lambda odt, **k: PDF)
    um = []

    def antigo(pdfs, *, thumbprint=None):
        raise A3.ServicoSemLote("O serviço é de uma versão anterior.")

    def servico(pdf, *, thumbprint=None):
        um.append(pdf)
        return {"ok": True, "cms_b64": base64.b64encode(
            _assinar(chave_e_cert, pdf)).decode("ascii")}

    monkeypatch.setattr(A3, "assinar_pdfs_pelo_windows", antigo)
    monkeypatch.setattr(A3, "assinar_pdf_pelo_windows", servico)
    a, b = _instrumento(s, 1), _instrumento(s, 2)
    texto = _postar_lote(s, [a, b]).get_data(as_text=True)
    assert len(um) == 2
    assert "2 instrumento(s) assinado(s)" in texto
    assert "versão anterior" in texto
    assert _a_assinar(s) == []
