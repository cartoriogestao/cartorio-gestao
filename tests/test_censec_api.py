"""A CENSEC por API: a tradução para o contrato, a conferência, o envio e o registro.

O QUE ESTES TESTES GUARDAM
    **Que o corpo sai no formato do contrato** (`CENSEC API` 2.71.0, lido em
    09/10/2026): listas `atosCep`/`atosCesdi`/`testamentos`, vocabulário por
    nome (`Cpf`, `Usufrutuario`, `Marco` sem cedilha) e `valor` numérico.

    **Que HTTP 200 não é «entrou»** — cada central volta com o seu resultado, e
    o ato recusado (por livro e folha) volta para a fila.

    **Que homologação não marca nada** e **que POST não se repete sozinho**.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import censec_api as CA                                          # noqa: E402
import centrais_cred as CRED                                     # noqa: E402
import centrais_trava_sandbox as TRAVA                           # noqa: E402
import notas_censec as NC                                        # noqa: E402

AGORA = "2026-10-09T08:00:00"
CPF_A, CPF_B = "52998224725", "11144477735"


# ------------------------------------------------------------ a tradução

def test_procuracao_sai_no_vocabulario_do_contrato():
    ato = {"tipo": "PROCURACAO", "data": "2026-10-08", "livro": "28", "folha": "46",
           "valor_transacao": None}
    partes = [{"nome": "MARIA", "documento": CPF_A, "qualificacao": "OUTORGANTE"},
              {"nome": "JOSE", "documento": CPF_B, "qualificacao": "OUTORGADO"}]
    assert NC.conferir_ato_cep(ato, partes) == []
    linha = CA.ato_cep(NC.montar_cep(ato, partes))
    assert linha["tipoAtoCep"] == "Procuracao"
    assert linha["valor"] == 0.0 and isinstance(linha["valor"], float)
    assert {p["tipoDocumento"] for p in linha["partes"]} == {"Cpf"}
    assert [p["qualidade"] for p in linha["partes"]] == ["Outorgante", "Outorgado"]
    assert linha["partes"][0]["estrangeiro"] is False


def test_acento_e_caixa_do_gerador_viram_o_nome_do_contrato():
    assert CA._do_vocabulario("Usufrutuário", CA.QUALIDADE_CEP) == "Usufrutuario"
    assert CA._do_vocabulario("CPF", CA.TIPO_DOCUMENTO_CEP) == "Cpf"
    assert CA._do_vocabulario("OAB", CA.TIPO_DOCUMENTO_CESDI) == "Oab"
    assert CA.cabecalho("999999", 2026, 3, 1)["quinzena"]["mesReferencia"] == "Marco"
    assert CA.cabecalho("999999", 2026, 3, 1)["cns"] == 999999


def test_as_tabelas_numericas_casam_com_os_nomes_do_contrato():
    assert set(CA.NATUREZA_DO_CODIGO) == set(NC.NATUREZA_ESCRITURA)
    assert len(CA.NATUREZA_ESCRITURA) == len(NC.NATUREZA_ESCRITURA) == 54
    assert CA.NATUREZA_DO_CODIGO[6] == "CompraEVenda"
    assert CA.NATUREZA_DO_CODIGO[35] == "Rerratificacao"
    assert CA.NATUREZA_DO_CODIGO[80] == "PromessaDeCompraEVenda"
    assert CA.TIPO_ATO_CESDI_DO_CODIGO[4] == "DivorcioDireto"
    assert set(NC.TIPO_ATO_CEP.values()) <= set(CA.TIPO_ATO_CEP)
    assert set(NC.TIPO_TESTAMENTO.values()) == set(CA.TIPO_TESTAMENTO)


def test_o_envelope_do_gerador_e_o_do_contrato():
    assert NC.ENVELOPE_CONFERIDO is True
    assert {c: CA.TRADUTOR[c][0] for c in CA.TRADUTOR} == NC.ENVELOPE_CHAVES


def test_responsavel_que_nao_se_reconhece_nao_vira_palpite():
    assert CA._responsavel("Ambos os cônjuges") == "AmbosConjuges"
    assert CA._responsavel("a avó materna") is None


# ------------------------------------------------------------ a conferência

def test_conferencia_diz_o_que_a_api_recusaria_com_livro_e_folha():
    corpo = CA.cabecalho("999999", 2026, 10, 1)
    corpo["atosCep"] = [{"tipoAtoCep": "Procuracao", "data": "2026-10-08",
                         "livro": "28", "folha": "46",
                         "partes": [{"nome": "X", "qualidade": None,
                                     "tipoDocumento": "Cpf"}]}]
    problemas = CA.conferir_corpo(corpo)
    assert any("livro 28, fl. 46" in p and "qualidade" in p for p in problemas)
    corpo["atosCep"][0]["partes"][0]["qualidade"] = "Outorgante"
    assert CA.conferir_corpo(corpo) == []
    corpo["atosCep"][0]["tipoAtoCep"] = 2
    assert any("fora do vocabulário" in p for p in CA.conferir_corpo(corpo))


def test_quinzena_sem_ato_nao_vai():
    assert any("nada a enviar" in p for p in
               CA.conferir_corpo(CA.cabecalho("999999", 2026, 10, 1)))


# ------------------------------------------------------------ a resposta

RESPOSTA = {
    "cepResult": {
        "success": True, "exception": {"occurred": False},
        "carga": {"id": "11111111-2222-3333-4444-555555555555",
                  "status": "AguardandoValidacao"},
        "validationResults": [
            {"livro": "28", "folha": "47", "hasError": True, "hasWarning": False,
             "Errors": [{"level": "Error", "message": "Qualidade inválida"}]}]},
    "cesdiResult": {"success": False, "exception": {"occurred": True,
                                                    "message": "CNS sem permissão"}},
}


def test_resumo_le_cada_central_e_cada_recusa():
    r = CA.resumir_resposta(RESPOSTA)
    assert r["CEP"]["sucesso"] is True
    assert r["CEP"]["situacao"] == "AguardandoValidacao"
    assert r["CEP"]["recusas"] == [{"livro": "28", "folha": "47", "livroComplemento": None,
                                    "folhaComplemento": None,
                                    "mensagens": ["Qualidade inválida"]}]
    assert r["CESDI"]["sucesso"] is False and "permissão" in r["CESDI"]["erro"]


# ------------------------------------------------------------ envio e registro

@pytest.fixture()
def casa(cg_casa):
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    for folha, (a, b) in (("46", (CPF_A, CPF_B)), ("47", (CPF_B, CPF_A))):
        ato = c.execute(
            """INSERT INTO nt_atos (tipo, data, situacao, livro, folha, origem, criado_em)
               VALUES ('PROCURACAO','2026-10-08','LAVRADO','28',?,'MANUAL',?)""",
            (folha, AGORA)).lastrowid
        for nome, doc, q in (("MARIA", a, "OUTORGANTE"), ("JOSE", b, "OUTORGADO")):
            c.execute("""INSERT INTO nt_ato_partes (ato_id, nome, documento, qualificacao,
                             criado_em) VALUES (?,?,?,?,?)""", (ato, nome, doc, q, AGORA))
    c.commit()
    yield cg_casa["db"], c
    c.close()


def _falsa_central(monkeypatch, resposta=RESPOSTA, status=200):
    chamadas = []

    def bater(ambiente, metodo, caminho, *, corpo=None, prazo=60, pasta=None):
        chamadas.append({"ambiente": ambiente, "metodo": metodo, "caminho": caminho,
                         "corpo": corpo})
        return {"status": status, "json": resposta, "texto": ""}
    monkeypatch.setattr(CA, "_bater", bater)
    return chamadas


def test_homologacao_envia_e_nao_marca_nada(casa, monkeypatch):
    db, con = casa
    chamadas = _falsa_central(monkeypatch)
    r = CA.enviar_quinzena(db, 2026, 10, 1, cns="999999", ambiente="HOMOLOGACAO")
    assert len(chamadas) == 1 and chamadas[0]["caminho"] == "/api/cargas/upload-json"
    corpo = __import__("json").loads(chamadas[0]["corpo"].decode("utf-8"))
    assert len(corpo["atosCep"]) == 2 and corpo["quinzena"]["mesReferencia"] == "Outubro"
    assert r["remessas"] == []
    assert con.execute("SELECT count(*) FROM nt_remessas").fetchone()[0] == 0


def test_producao_registra_e_o_recusado_volta_para_a_fila(casa, monkeypatch):
    db, con = casa
    _falsa_central(monkeypatch)
    r = CA.enviar_quinzena(db, 2026, 10, 1, cns="999999", ambiente="PRODUCAO", por="X")
    assert [x["situacao"] for x in r["remessas"]] == ["ENVIADA"]
    rem = con.execute("SELECT * FROM nt_remessas").fetchone()
    assert rem["protocolo_central"] == "11111111-2222-3333-4444-555555555555"
    assert rem["enviada_em"] and rem["quantidade"] == 2
    itens = {r2["folha"]: r2["situacao"] for r2 in con.execute(
        """SELECT a.folha, i.situacao FROM nt_remessa_itens i
             JOIN nt_atos a ON a.id = i.ato_id""")}
    assert itens == {"46": "ENVIADA", "47": "REJEITADA"}
    # o enviado sai da fila; o recusado volta
    aptos = NC.separar(con, "CEP", 2026, 10, 1)["aptos"]
    assert [x["ato"]["folha"] for x in aptos] == ["47"]


def test_recusa_http_vira_erro_e_nada_se_grava(casa, monkeypatch):
    db, con = casa
    chamadas = _falsa_central(monkeypatch, resposta={"title": "Unauthorized"}, status=401)
    with pytest.raises(CA.CensecRecusou, match="chave de integração"):
        CA.enviar_quinzena(db, 2026, 10, 1, cns="999999", ambiente="PRODUCAO")
    assert len(chamadas) == 1                    # POST não se repete
    assert con.execute("SELECT count(*) FROM nt_remessas").fetchone()[0] == 0


def test_sem_chave_a_recusa_diz_onde_gerar(tmp_path):
    with pytest.raises(CA.CensecError, match="chave de integração da CENSEC"):
        CA.chave("PRODUCAO", pasta=tmp_path)
    CRED.gravar_token(CRED.CENSEC, token="abc123", ambiente="PRODUCAO", pasta=tmp_path)
    assert CA.chave("PRODUCAO", pasta=tmp_path) == "abc123"
    assert not CRED.tem(CRED.CENSEC, "HOMOLOGACAO", tmp_path)


def test_a_credencial_e_token_fora_do_banco():
    assert CRED.FORMA_DA_CENTRAL[CRED.CENSEC] == CRED.TOKEN
    assert CRED.ARQUIVO_DA_CENTRAL[CRED.CENSEC] == "censec.cred"
    assert CRED.ambientes_de(CRED.CENSEC) == (CRED.HOMOLOGACAO, CRED.PRODUCAO)


def test_no_sandbox_a_producao_da_censec_nao_sai(monkeypatch):
    monkeypatch.setenv(TRAVA.MARCA, "1")
    with pytest.raises(TRAVA.SandboxTravaRecusou):
        TRAVA.destino_seguro("censec.org.br", 443)
    assert TRAVA.destino_seguro("hml.censec.org.br", 443) == ("hml.censec.org.br", 443)


def test_a_tela_mostra_o_envio_e_o_botao_respeita_homologacao(cg_casa_logada, monkeypatch):
    c = cg_casa_logada["c"]
    html = c.get("/notas/remessas?ano=2026&mes=10&quinzena=1").get_data(as_text=True)
    assert "Enviar pela API da CENSEC" in html
    recebido = {}

    def enviar(db, ano, mes, quinzena, *, cns, ambiente, por="", pasta=None):
        recebido.update(ambiente=ambiente, quinzena=quinzena)
        return {"por_central": {}, "atos": {}, "remessas": [], "ambiente": ambiente}
    monkeypatch.setattr(CA, "enviar_quinzena", enviar)
    import re
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    r = c.post("/notas/remessas/enviar-api",
               data={"ano": "2026", "mes": "10", "quinzena": "1",
                     "ambiente": "HOMOLOGACAO", "csrf_token": token})
    assert r.status_code in (302, 303)
    assert recebido == {"ambiente": "HOMOLOGACAO", "quinzena": 1}
