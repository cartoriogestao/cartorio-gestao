"""Os termos de encerramento diário do mês, num PDF só, assinado — 23/10/2026.

    «junta tudo para assinar no final do mês, ainda que tenha encerramento
     diário; assinatura num PDF único assinado digitalmente» — o oficial

O QUE ESTES TESTES GUARDAM
      - o mês só se junta **terminado e inteiro**: dia útil sem termo, ou dia
        com protocolo sem termo, impede, e a recusa diz quais;
      - os dias que faltam se encerram de uma vez, cada um com o MESMO termo
        da tela do dia;
      - juntar põe o mês na fila de assinatura da casa (`as_documentos`);
      - **assinatura que embrulha outro papel não entra**;
      - termo novo entre juntar e assinar obriga a juntar de novo;
      - **mês assinado fecha**: nenhum dia dele recebe termo depois;
      - o dia de protocolo sem termo aparece no painel do que ficou pelo
        caminho, e sai de lá quando é encerrado.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import cades  # noqa: E402
import encerramento_mensal as EM  # noqa: E402
import escrituracao as ESC  # noqa: E402
import inacabados as IN  # noqa: E402
import livro_nucleo as LN  # noqa: E402

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from test_nucleo_web import _abrir, _con, _post, s  # noqa: E402,F401

MES = "2026-08"
HOJE = "2026-10-23"
SERIES = EM.SERIES_PADRAO
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
      "endereco_completo": "Av. Exemplo, 1"}
PDF = b"%PDF-1.4\n% termos do mes de ensaio\n1 0 obj<<>>endobj\n%%EOF\n"


def _util(d: date) -> bool:
    return d.weekday() < 5


def _uteis_do_mes() -> list[str]:
    return [d.isoformat() for d in EM.dias_do_mes(MES) if _util(d)]


def _encerrar(con, serie: str, dia: str) -> None:
    ESC.encerrar_o_dia(con, serie, dia, sv=SV, agora=f"{HOJE}T09:00:00",
                       dia_extenso=dia, usuario="MARIO EXEMPLO DOS SANTOS")


def _mes_completo(s) -> None:
    """Cada dia útil do mês encerrado, um por um — a rotina diária."""
    con = _con(s)
    with con:
        for serie in SERIES:
            for dia in _uteis_do_mes():
                _encerrar(con, serie, dia)
    con.close()


def _gerar(con) -> dict:
    return EM.gerar(con, MES, series_do_mes=SERIES, e_dia_util=_util,
                    hoje=HOJE, sv=SV, agora=f"{HOJE}T10:00:00",
                    usuario="MARIO EXEMPLO DOS SANTOS")


@pytest.fixture(scope="module")
def chave_e_cert():
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,
                                         "MARIO EXEMPLO:00000000191")])
    agora = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome)
            .public_key(chave.public_key()).serial_number(616161)
            .not_valid_before(agora - timedelta(days=1))
            .not_valid_after(agora + timedelta(days=30))
            .sign(chave, hashes.SHA256()))
    return chave, cert.public_bytes(serialization.Encoding.DER)


def _assinar(chave_e_cert, conteudo: bytes) -> bytes:
    chave, cert = chave_e_cert
    return cades.assinar(
        conteudo, cert,
        lambda dados: chave.sign(dados, padding.PKCS1v15(), hashes.SHA256()))


# ------------------------------------------------------------ o mês inteiro


def test_mes_que_nao_terminou_nao_se_junta(s):
    con = _con(s)
    with pytest.raises(EM.EncerramentoMensalError, match="ainda não terminou"):
        EM.gerar(con, "2026-10", series_do_mes=SERIES, e_dia_util=_util,
                 hoje=HOJE, sv=SV, agora=f"{HOJE}T10:00:00")


def test_dia_util_sem_termo_impede_juntar_e_a_recusa_diz_quais(s):
    con = _con(s)
    with pytest.raises(EM.EncerramentoMensalError) as erro:
        _gerar(con)
    texto = str(erro.value)
    # dois livros, cada dia útil do mês
    assert f"Faltam {2 * len(_uteis_do_mes())}" in texto
    assert _uteis_do_mes()[0] in texto
    assert "Livro de Protocolo do RCPJ" in texto


def test_protocolo_num_sabado_tambem_tem_de_estar_encerrado(s):
    # 01/08/2026 é sábado: não é dia útil, mas houve protocolo.
    _abrir(s, "PJ_PROTOCOLO", dia="2026-08-01")
    falta = EM.pendencias(_con(s), MES, series_do_mes=SERIES,
                          e_dia_util=_util, hoje=HOJE)
    sabado = [p for p in falta if p["dia"] == "2026-08-01"]
    assert len(sabado) == 1
    assert sabado[0]["serie"] == "PJ_PROTOCOLO"
    assert "protocolo" in sabado[0]["motivo"]


def test_com_cada_dia_encerrado_nao_falta_nada(s):
    _mes_completo(s)
    assert not EM.pendencias(_con(s), MES, series_do_mes=SERIES,
                             e_dia_util=_util, hoje=HOJE)


def test_nao_ha_encerramento_em_lote(s):
    # Decisão do oficial, 23/10/2026: o encerramento é manual, todo dia. O
    # módulo do mês só junta; não tem função nem rota que encerre dias.
    import ast
    arvore = ast.parse((RAIZ / "encerramento_mensal.py").read_text(encoding="utf-8"))
    chamadas = {n.func.attr for n in ast.walk(arvore)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "encerrar_o_dia" not in chamadas
    rotas = {r.rule for r in s["app"].url_map.iter_rules()}
    assert not [r for r in rotas if "encerramento-mensal" in r and "encerrar" in r]


def test_juntar_poe_o_mes_na_fila_de_assinatura(s):
    _mes_completo(s)
    con = _con(s)
    with con:
        r = _gerar(con)
    assert r["quantidade"] == 2 * len(_uteis_do_mes())
    m = EM.mensal(con, MES)
    assert m["assinado_em"] is None
    assert "TERMOS DE ENCERRAMENTO DIÁRIO — AGOSTO DE 2026" in m["html"]
    assert "Livro de Protocolo do RTD" in m["html"]
    doc = con.execute("SELECT * FROM as_documentos WHERE entidade=? "
                      "AND entidade_id=?", (EM.ENTIDADE, r["id"])).fetchone()
    assert doc["sha256_documento"] == r["sha256"]
    assert "agosto de 2026" in doc["titulo"]


def test_juntar_de_novo_refaz_o_mes_que_espera_assinatura(s):
    _mes_completo(s)
    con = _con(s)
    with con:
        primeiro = _gerar(con)
        segundo = _gerar(con)
    assert segundo["id"] == primeiro["id"]
    assert segundo["refeito"] is True
    assert con.execute("SELECT COUNT(*) FROM as_documentos WHERE entidade=?",
                       (EM.ENTIDADE,)).fetchone()[0] == 1


# ------------------------------------------------------------- a assinatura


def test_assinado_se_guarda_e_o_mes_fecha(s, chave_e_cert, tmp_path):
    _mes_completo(s)
    con = _con(s)
    with con:
        r = _gerar(con)
        g = EM.guardar_assinatura(
            con, r["id"], pdf=PDF, p7s=_assinar(chave_e_cert, PDF),
            pasta_de_arquivos=tmp_path, agora=f"{HOJE}T11:00:00",
            usuario="MARIO EXEMPLO DOS SANTOS")
    assert "MARIO EXEMPLO" in (g["assinado_por"] or "")
    pasta = tmp_path / "Livros" / "Encerramentos mensais"
    assert (pasta / f"encerramentos-diarios-{MES}.pdf").read_bytes() == PDF
    assert EM.mensal(con, MES)["assinado_em"] == f"{HOJE}T11:00:00"
    # MÊS ASSINADO FECHA: um sábado do mês não recebe termo depois.
    with pytest.raises(LN.LivroError, match="juntados e assinados"):
        _encerrar(con, "PJ_PROTOCOLO", "2026-08-02")
    # e não se junta de novo
    with pytest.raises(EM.EncerramentoMensalError, match="já foi assinado"):
        _gerar(con)


def test_assinatura_de_outro_papel_nao_entra(s, chave_e_cert, tmp_path):
    _mes_completo(s)
    con = _con(s)
    with con:
        r = _gerar(con)
    outro = PDF.replace(b"ensaio", b"OUTRO ")
    with pytest.raises(EM.EncerramentoMensalError, match="não confere"):
        EM.guardar_assinatura(
            con, r["id"], pdf=PDF, p7s=_assinar(chave_e_cert, outro),
            pasta_de_arquivos=tmp_path, agora=f"{HOJE}T11:00:00")
    assert not (tmp_path / "Livros").exists()
    assert EM.mensal(con, MES)["assinado_em"] is None


def test_termo_novo_depois_de_juntar_obriga_a_juntar_de_novo(s):
    _mes_completo(s)
    con = _con(s)
    with con:
        r = _gerar(con)
        _encerrar(con, "TD_PROTOCOLO", "2026-08-08")   # um sábado
    with pytest.raises(EM.EncerramentoMensalError, match="mudaram"):
        EM.conferir_antes_de_assinar(con, r["id"])


# ------------------------------------------------------------ a configuração


def test_por_padrao_sao_os_protocolos_do_rcpj_e_do_rtd():
    assert EM.series(lambda chave, padrao: "") == ("PJ_PROTOCOLO", "TD_PROTOCOLO")
    assert EM.series(lambda chave, padrao: "pt_protocolo") == ("PT_PROTOCOLO",)


def test_livro_que_nao_e_diario_na_configuracao_e_recusado():
    with pytest.raises(EM.EncerramentoMensalError, match="não é livro diário"):
        EM.series(lambda chave, padrao: "PJ_PROTOCOLO,RC_A")
    with pytest.raises(EM.EncerramentoMensalError, match="não existe"):
        EM.series(lambda chave, padrao: "PJ_PROTOCOLOS")


# ------------------------------------------------------------- o painel


def test_o_dia_de_protocolo_sem_termo_aparece_no_painel_e_sai_ao_encerrar(s):
    _abrir(s, "PJ_PROTOCOLO", dia="2026-10-20")
    itens = [x for x in IN.lista(_con(s), hoje=HOJE)
             if x["chave"] == "NUCLEO_DIA_SEM_ENCERRAR"]
    assert len(itens) == 1
    assert itens[0]["parado"] is True
    assert itens[0]["rotulo"] == "PJ_PROTOCOLO — 2026-10-20"
    con = _con(s)
    with con:
        _encerrar(con, "PJ_PROTOCOLO", "2026-10-20")
    assert not [x for x in IN.lista(_con(s), hoje=HOJE)
                if x["chave"] == "NUCLEO_DIA_SEM_ENCERRAR"]


# --------------------------------------------------------------- a tela


def test_a_tela_mostra_o_mes_e_os_dias_que_faltam(s):
    html = s["c"].get(f"/nucleo/encerramento-diario?mes={MES}").get_data(as_text=True)
    assert "Termos do mês, para assinar" in html
    assert "dia(s) de agosto de 2026 sem termo" in html
    assert "um por um" in html
    assert "Juntar os termos" not in html      # mês com buraco não se junta


def test_pela_tela_junta_o_mes_encerrado(s):
    _mes_completo(s)
    origem = f"/nucleo/encerramento-diario?mes={MES}"
    html = _post(s, "/nucleo/encerramento-mensal/juntar", origem=origem, mes=MES)
    assert "juntados" in html
    assert "Assinar com o certificado A3" in html
    assert _con(s).execute(
        "SELECT COUNT(*) FROM nu_encerramentos_mensais").fetchone()[0] == 1


def test_auditoria_nao_junta_o_mes(cg_casa):
    from test_nucleo_web import _sessao
    sessao = _sessao(cg_casa, papel="AUDITOR")
    resposta = sessao["c"].post("/nucleo/encerramento-mensal/juntar",
                                data={"mes": MES})
    assert resposta.status_code in (302, 400, 403)
    assert _con(sessao).execute(
        "SELECT COUNT(*) FROM nu_encerramentos_mensais").fetchone()[0] == 0
