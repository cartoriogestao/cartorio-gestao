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
      - **a assinatura em lote é uma janela do token por instrumento** (o
        serviço assina um PDF por chamada) e **para na primeira falha do
        token** — PIN errado em sequência bloqueia o A3;
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


def test_o_lote_de_assinatura_segue_quando_a_falha_e_do_papel():
    def assinar_um(iid):
        if iid == 2:
            raise PI.InstrumentoError("A assinatura não confere com o instrumento")
        return {"instrumento_id": iid}
    r = PI.assinar_lote([1, 2, 3], assinar_um)
    assert [f["instrumento_id"] for f in r["feitos"]] == [1, 3]
    assert r["falharam"][0]["instrumento_id"] == 2
    assert r["parou"] is False and r["nao_tentados"] == []


def test_o_lote_de_assinatura_para_na_primeira_falha_do_token():
    """PIN errado em sequência bloqueia o A3: depois da recusa, nada mais vai
    ao token."""
    chamados = []

    def assinar_um(iid):
        chamados.append(iid)
        if iid == 2:
            raise PI.AssinaturaInterrompida("o PIN não foi aceito pelo token.")
        return {"instrumento_id": iid}
    r = PI.assinar_lote([1, 2, 3, 4], assinar_um)
    assert chamados == [1, 2]
    assert r["parou"] is True
    assert r["nao_tentados"] == [3, 4]
    assert "PIN" in r["falharam"][0]["motivo"]


def test_o_lote_de_assinatura_tem_teto_e_recusa_vazio():
    with pytest.raises(PI.InstrumentoError, match="Marque"):
        PI.assinar_lote([], lambda iid: {})
    demais = list(range(1, PI.LIMITE_DO_LOTE_DE_ASSINATURA + 2))
    with pytest.raises(PI.InstrumentoError, match="janela do token"):
        PI.assinar_lote(demais, lambda iid: pytest.fail("não devia assinar"))


def test_a_regra_do_pin_esta_escrita_onde_o_lote_mora():
    """O que se mediu no código do serviço fica dito na função, e não só no
    PR: uma chamada por PDF, o PIN na janela do token."""
    doc = PI.assinar_lote.__doc__ or ""
    assert "PIN É PEDIDO A CADA INSTRUMENTO" in doc
    assert "/assinar/pdf-windows" in doc


def test_o_servico_assina_um_pdf_por_chamada():
    """A medição que sustenta «uma janela por instrumento»: o assinador do
    Windows recebe UM pdf e abre UM PowerShell para ele."""
    import inspect

    import a3_windows as A3W
    assinatura = inspect.signature(A3W.assinar_pdf)
    assert list(assinatura.parameters)[:1] == ["pdf"]
    assert "subprocess.run" in inspect.getsource(A3W.assinar_pdf)


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
    assert "uma vez para cada instrumento" in html
    assert 'name="pin"' not in html


def test_assinar_os_marcados_chama_o_servico_uma_vez_por_instrumento(
        s, chave_e_cert, monkeypatch):
    import assinar_com_a3 as A3
    import impressao_pdf as IMPPDF
    monkeypatch.setattr(IMPPDF, "pdf_de_odt", lambda odt, **k: PDF)
    vistos = []

    def servico(pdf, *, thumbprint=None):
        vistos.append(pdf)
        return {"ok": True, "cms_b64": base64.b64encode(
            _assinar(chave_e_cert, pdf)).decode("ascii")}

    monkeypatch.setattr(A3, "assinar_pdf_pelo_windows", servico)
    a, b = _instrumento(s, 1), _instrumento(s, 2)
    html = s["c"].get("/protesto/instrumentos").get_data(as_text=True)
    r = s["c"].post("/protesto/instrumentos/assinar-lote",
                    data={"csrf_token": _token(html),
                          "instrumento_id": [str(a), str(b)]},
                    follow_redirects=True)
    assert r.status_code == 200
    assert len(vistos) == 2
    assert "2 instrumento(s) assinado(s)" in r.get_data(as_text=True)
    # assinados, saem da lista do que falta assinar — e um segundo lote não
    # vai ao token de novo
    r2 = s["c"].post("/protesto/instrumentos/assinar-lote",
                     data={"csrf_token": _token(html),
                           "instrumento_id": [str(a)]},
                     follow_redirects=True)
    assert len(vistos) == 2
    assert "já foi assinado" in r2.get_data(as_text=True)


def test_o_token_que_recusa_para_o_lote_pela_tela(s, monkeypatch):
    import assinar_com_a3 as A3
    import impressao_pdf as IMPPDF
    monkeypatch.setattr(IMPPDF, "pdf_de_odt", lambda odt, **k: PDF)
    chamadas = []

    def recusa(pdf, *, thumbprint=None):
        chamadas.append(pdf)
        raise A3.AssinarComA3Error("o PIN não foi aceito pelo token.")

    monkeypatch.setattr(A3, "assinar_pdf_pelo_windows", recusa)
    a, b = _instrumento(s, 1), _instrumento(s, 2)
    html = s["c"].get("/protesto/instrumentos").get_data(as_text=True)
    r = s["c"].post("/protesto/instrumentos/assinar-lote",
                    data={"csrf_token": _token(html),
                          "instrumento_id": [str(a), str(b)]},
                    follow_redirects=True)
    texto = r.get_data(as_text=True)
    assert r.status_code == 200
    assert len(chamadas) == 1
    assert "PIN não foi aceito" in texto
    assert "não foram tentados" in texto
