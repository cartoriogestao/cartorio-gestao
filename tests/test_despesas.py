"""AS DESPESAS — cadastro, autorização, pagamento pelo Inter e conferência no extrato.

O banco é um INTER FALSO, na memória, que guarda cada pedido e nunca abre rede.
O dígito verificador do boleto e o CRC do Pix são calculados AQUI DE NOVO, por
outro caminho (o CRC pelo `binascii.crc_hqx` da biblioteca padrão): um teste
que confere com o mesmo código que calcula não prova nada. Os códigos reais
vêm da especificação da API Banking do Inter (exemplos do sandbox).
"""
from __future__ import annotations

import binascii
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import despesas as DP  # noqa: E402
import despesas_automacao as AUT  # noqa: E402
import despesas_inter as INTER  # noqa: E402
from bd_nativo import banco  # noqa: E402

FAVORECIDO = "00000010000127"     # 00.000.010/0001-27, fictício
AGORA = datetime(2026, 10, 26, 10, 0, tzinfo=timezone(timedelta(hours=-3)))
HOJE = AGORA.date().isoformat()
VENCIMENTO = "2026-11-10"


# --------------------------------------------- os códigos, montados aqui de novo

def _mod11(numero: str) -> int:
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(d) * pesos[i % 8] for i, d in enumerate(reversed(numero)))
    dv = 11 - soma % 11
    return 1 if dv in (0, 10, 11) else dv


def boleto(valor_centavos: int, vencimento: str = VENCIMENTO) -> str:
    """Um código de barras de boleto (44) válido, com fator do calendário novo."""
    fator = (date.fromisoformat(vencimento) - date(2025, 2, 22)).days + 1000
    sem_dv = f"0779{fator:04d}{valor_centavos:010d}7777011657373795603057629"
    return sem_dv[:4] + str(_mod11(sem_dv)) + sem_dv[4:]


def pix(valor: str | None, chave: str = "fornecedor@example.com") -> str:
    def campo(tag, v):
        return f"{tag}{len(v):02d}{v}"
    conta = campo("00", "br.gov.bcb.pix") + campo("01", chave)
    corpo = (campo("00", "01") + campo("26", conta) + campo("52", "0000") + campo("53", "986")
             + (campo("54", valor) if valor else "") + campo("58", "BR")
             + campo("59", "FORNECEDOR FICTICIO") + campo("60", "CIDADE") + "6304")
    return corpo + f"{binascii.crc_hqx(corpo.encode(), 0xFFFF):04X}"


@pytest.mark.parametrize("codigo, tipo, valor", [
    ("03395988500000666539201493990000372830030102", "BOLETO", 66653),
    ("07795904400000500007777011657373795603057629", "BOLETO", 50000),
    ("10491916300000013453395782000100040000022263", "BOLETO", 1345),
    ("07797777051167847115990071126347192950000003010", "BOLETO", 3010),
    ("82670000000653301602023123106000000002830894", "ARRECADACAO", 6533),
    ("846600000026266702962017910100130004000625169925", "ARRECADACAO", 22667),
    ("81670000001283647972020063000000000294909999", "ARRECADACAO", 12836),
])
def test_os_codigos_do_sandbox_do_inter_sao_lidos_com_o_valor_certo(codigo, tipo, valor):
    lido = DP.ler_codigo_de_barras(codigo)
    assert (lido["tipo"], lido["valor_centavos"]) == (tipo, valor)


def test_um_digito_trocado_na_linha_digitavel_e_recusado():
    linha = "07797777051167847115990071126347192950000003010"
    trocado = linha[:12] + ("1" if linha[12] != "1" else "2") + linha[13:]
    with pytest.raises(DP.DespesaError, match="dígito"):
        DP.ler_codigo_de_barras(trocado)


def test_o_fator_de_vencimento_do_calendario_novo_da_a_data_certa():
    assert VENCIMENTO in DP.ler_codigo_de_barras(boleto(12345))["vencimentos"]


def test_pix_copia_e_cola_confere_crc_e_valor():
    lido = DP.ler_pix_copia_e_cola(pix("123.45"))
    assert lido["valor_centavos"] == 12345 and lido["chave"] == "fornecedor@example.com"
    estragado = pix("123.45")[:-1] + ("0" if pix("123.45")[-1] != "0" else "1")
    with pytest.raises(DP.DespesaError, match="CRC"):
        DP.ler_pix_copia_e_cola(estragado)


# ----------------------------------------------------------------- a casa

class InterFalso:
    """O Banking v2 do Inter, na memória."""

    def __init__(self):
        self.chamadas: list[tuple[str, str, dict]] = []
        self.status_boleto = "AGENDADO"
        self.pix_por_chave: dict[str, str] = {}
        self.extrato: list[dict] = []
        self.perder_resposta = False
        self.recusar = False

    def __call__(self, metodo, url, *, json_corpo=None, form=None, cabecalhos=None):
        self.chamadas.append((metodo, url, {"json": json_corpo, "form": form,
                                            "cab": cabecalhos or {}}))
        assert url.startswith(INTER.ENDERECOS["sandbox"]), "o teste fala só com o sandbox"
        caminho = url.split(".co", 1)[1]
        if caminho == "/oauth/v2/token":
            assert form["grant_type"] == "client_credentials"
            return INTER.Resposta(200, {"access_token": "tok", "expires_in": 3600})
        assert (cabecalhos or {}).get("Authorization") == "Bearer tok"
        if self.recusar:
            return INTER.Resposta(400, {"title": "Pagamento recusado", "detail": "saldo"})
        if metodo == "POST" and caminho == "/banking/v2/pagamento":
            assert set(json_corpo) >= {"codBarraLinhaDigitavel", "valorPagar", "dataVencimento"}
            if self.perder_resposta:
                self.perder_resposta = False
                raise TimeoutError("timed out")
            return INTER.Resposta(200, {"statusPagamento": self.status_boleto,
                                        "codigoTransacao": f"T{len(self.chamadas)}",
                                        "dataAgendamento": json_corpo["dataPagamento"]})
        if metodo == "POST" and caminho == "/banking/v2/pix":
            chave = cabecalhos["x-id-idempotente"]
            codigo = self.pix_por_chave.setdefault(chave, f"00000000-0000-4000-8000-{len(self.pix_por_chave):012d}")
            if self.perder_resposta:
                self.perder_resposta = False
                raise TimeoutError("timed out")
            return INTER.Resposta(200, {"tipoRetorno": "PROCESSADO", "codigoSolicitacao": codigo})
        if metodo == "GET" and caminho.startswith("/banking/v2/pix/"):
            return INTER.Resposta(200, {"transacaoPix": {"status": "PAGO", "endToEnd": "E1"}})
        if metodo == "GET" and caminho.startswith("/banking/v2/pagamento?"):
            return INTER.Resposta(200, [])
        if metodo == "GET" and caminho.startswith("/banking/v2/extrato/completo?"):
            return INTER.Resposta(200, {"transacoes": self.extrato, "ultimaPagina": True})
        return INTER.Resposta(404, {"title": "Não encontrado", "detail": caminho})

    def posts(self, trecho: str) -> list[dict]:
        return [c for m, u, c in self.chamadas if m == "POST" and u.endswith(trecho)]


CAMPOS = {"client_id": "id-ficticio", "client_secret": "segredo-ficticio",
          "crt_pem": "x", "key_pem": "x"}


@pytest.fixture
def casa(cg_casa_logada):
    db = cg_casa_logada["db"]
    with db.transaction() as con:
        DP.gravar_configuracao(con, {**DP.PADRAO, "despesas_pagamento_ligado": "1",
                                     "despesas_ambiente": "sandbox",
                                     "despesas_teto_por_pagamento": "1.000,00",
                                     "despesas_teto_por_dia": "1.500,00",
                                     "despesas_teto_guia": "800,00",
                                     "despesas_regra_guias_ligada": "1"})
    falso = InterFalso()
    return {**cg_casa_logada, "inter": falso,
            "cliente": INTER.ClienteInter("sandbox", falso, CAMPOS)}


def _cadastrar(db, *, valor=12345, forma=DP.BOLETO, codigo=None, categoria="CONCESSIONARIAS",
               origem="MANUAL", chave_origem=None, esperado=None, vencimento=VENCIMENTO):
    if codigo is None:
        codigo = boleto(valor, vencimento) if forma == DP.BOLETO else pix(f"{valor / 100:.2f}")
    with db.transaction() as con:
        return DP.cadastrar(
            con, agora=AGORA, por="beatriz", origem=origem, chave_origem=chave_origem,
            beneficiario_nome="FORNECEDOR FICTICIO", beneficiario_documento=FAVORECIDO,
            valor_centavos=valor, vencimento=vencimento, forma=forma, codigo=codigo,
            descricao="Energia elétrica de outubro", categoria=categoria,
            documento_especie="Fatura", documento_numero="123",
            valor_esperado_centavos=esperado)


def _autorizar(db, i, **kw):
    with db.transaction() as con:
        return DP.autorizar(con, i, agora=AGORA, por="mario", papel="ADMIN", **kw)


def _d(db, i):
    with db.connect() as con:
        return DP.despesa(con, i)


# ------------------------------------------------------------ cadastro e regra

def test_boleto_com_valor_diferente_do_digitado_e_recusado(casa):
    with pytest.raises(DP.DespesaError, match="R\\$ 123,45"):
        _cadastrar(casa["db"], valor=99999, codigo=boleto(12345))


def test_cadastro_nasce_esperando_o_oficial_e_so_o_admin_autoriza(casa):
    db = casa["db"]
    i = _cadastrar(db)
    assert _d(db, i)["situacao"] == DP.AGUARDANDO
    with db.transaction() as con, pytest.raises(DP.DespesaError, match="Só o oficial"):
        DP.autorizar(con, i, agora=AGORA, por="carla", papel="MANAGER")
    assert _autorizar(db, i)["situacao"] == DP.AUTORIZADA


def test_acima_do_teto_so_com_a_marca_do_oficial(casa):
    db = casa["db"]
    i = _cadastrar(db, valor=120000)
    with pytest.raises(DP.DespesaError, match="teto"):
        _autorizar(db, i)
    assert _autorizar(db, i, acima_do_teto=True)["acima_do_teto"] == 1


def test_a_mesma_guia_nao_entra_duas_vezes(casa):
    db = casa["db"]
    a = _cadastrar(db, origem=DP.ORIGEM_PORTAL_SELO, chave_origem="FERJ:2026-10-26",
                   categoria="FUNDO_FERJ", esperado=12345)
    b = _cadastrar(db, origem=DP.ORIGEM_PORTAL_SELO, chave_origem="FERJ:2026-10-26",
                   categoria="FUNDO_FERJ", esperado=12345)
    assert a == b


def test_regra_das_guias_conferida_e_no_teto_nasce_autorizada(casa):
    db = casa["db"]
    ok = _cadastrar(db, origem=DP.ORIGEM_PORTAL_SELO, chave_origem="FERJ:a",
                    categoria="FUNDO_FERJ", esperado=12345)
    assert _d(db, ok)["situacao"] == DP.AUTORIZADA
    assert _d(db, ok)["natureza"] == DP.REPASSE
    divergente = _cadastrar(db, origem=DP.ORIGEM_PORTAL_SELO, chave_origem="FERJ:b",
                            categoria="FUNDO_FERJ", esperado=12000)
    assert _d(db, divergente)["situacao"] == DP.AGUARDANDO and _d(db, divergente)["divergencia"]
    acima = _cadastrar(db, valor=90000, origem=DP.ORIGEM_PORTAL_SELO, chave_origem="FERJ:c",
                       categoria="FUNDO_FERJ", esperado=90000)
    assert _d(db, acima)["situacao"] == DP.AGUARDANDO
    despesa_do_robo = _cadastrar(db, origem=DP.ORIGEM_PORTAL_SELO, chave_origem="x",
                                 esperado=12345)
    assert _d(db, despesa_do_robo)["situacao"] == DP.AGUARDANDO   # só guia de fundo


# ------------------------------------------------------------------ pagar

def test_boleto_autorizado_vai_ao_inter_com_o_corpo_da_especificacao(casa):
    db, inter = casa["db"], casa["inter"]
    i = _cadastrar(db)
    _autorizar(db, i)
    r = INTER.pagar(db, i, cliente=casa["cliente"], por="teste", agora=AGORA)
    assert r["situacao"] == DP.ENVIADA
    corpo = inter.posts("/banking/v2/pagamento")[0]["json"]
    assert corpo == {"codBarraLinhaDigitavel": boleto(12345), "valorPagar": "123.45",
                     "dataVencimento": VENCIMENTO, "dataPagamento": VENCIMENTO,
                     "cpfCnpjBeneficiario": FAVORECIDO}
    assert _d(db, i)["banco_status"] == "AGENDADO"


def test_pagamento_desligado_ou_nao_autorizado_nao_chama_o_banco(casa):
    db, inter = casa["db"], casa["inter"]
    i = _cadastrar(db)
    assert INTER.pagar(db, i, cliente=casa["cliente"], por="t", agora=AGORA)["situacao"] \
        == DP.AGUARDANDO
    _autorizar(db, i)
    with db.transaction() as con:
        DP.gravar_configuracao(con, {**DP.configuracao(con), "despesas_pagamento_ligado": ""})
    r = INTER.pagar(db, i, cliente=casa["cliente"], por="t", agora=AGORA)
    assert r["situacao"] == DP.AUTORIZADA and "desligado" in r["mensagem"]
    assert not inter.posts("/pagamento")


def test_teto_do_dia_segura_o_resto_para_amanha(casa):
    db = casa["db"]
    ids = [_cadastrar(db, valor=90000) for _ in range(2)]
    for i in ids:
        _autorizar(db, i)
    r = INTER.pagar_autorizadas(db, cliente=casa["cliente"], por="t", agora=AGORA)
    assert len(r["pagas"]) == 1 and len(r["esperam"]) == 1


def test_recusa_do_banco_vira_falhou_com_o_motivo(casa):
    db = casa["db"]
    i = _cadastrar(db)
    _autorizar(db, i)
    casa["inter"].recusar = True
    INTER.pagar(db, i, cliente=casa["cliente"], por="t", agora=AGORA)
    assert _d(db, i)["situacao"] == DP.FALHOU and "saldo" in _d(db, i)["mensagem"]


def test_pix_com_resposta_perdida_reenvia_com_a_mesma_chave_e_nao_paga_duas_vezes(casa):
    db, inter = casa["db"], casa["inter"]
    i = _cadastrar(db, forma=DP.PIX_COPIA_E_COLA)
    _autorizar(db, i)
    inter.perder_resposta = True
    INTER.pagar(db, i, cliente=casa["cliente"], por="t", agora=AGORA)
    assert _d(db, i)["banco_status"] == "SEM_RESPOSTA"
    INTER.atualizar(db, i, cliente=casa["cliente"], por="t", agora=AGORA)
    chaves = {c["cab"]["x-id-idempotente"] for c in inter.posts("/banking/v2/pix")}
    assert len(inter.posts("/banking/v2/pix")) == 2 and len(chaves) == 1
    assert len(inter.pix_por_chave) == 1 and _d(db, i)["banco_codigo"]


# ----------------------------------------------------- o extrato e o livro

def _debito(d, *, dia=HOJE, ident="X1"):
    return {"idTransacao": ident, "dataTransacao": dia, "tipoOperacao": "D",
            "valor": f"{int(d['valor']) / 100:.2f}", "descricao": "PAGAMENTO",
            "detalhes": {"codBarras": d["codigo_barras"]}}


def test_so_o_debito_no_extrato_leva_a_despesa_ao_livro_diario(casa):
    db, inter = casa["db"], casa["inter"]
    despesa = _cadastrar(db)
    guia = _cadastrar(db, origem=DP.ORIGEM_PORTAL_SELO, chave_origem="FERJ:z",
                      categoria="FUNDO_FERJ", esperado=12345, valor=12345,
                      codigo=boleto(12345, "2026-11-11"), vencimento="2026-11-11")
    _autorizar(db, despesa)
    INTER.pagar_autorizadas(db, cliente=casa["cliente"], por="t", agora=AGORA)
    r = INTER.conciliar(db, cliente=casa["cliente"], por="t", agora=AGORA)
    assert r["conciliadas"] == []                       # extrato vazio: nada conferido
    inter.extrato = [_debito(_d(db, despesa), ident="A"), _debito(_d(db, guia), ident="B"),
                     {"idTransacao": "C", "dataTransacao": HOJE, "valor": "9.99",
                      "descricao": "TARIFA", "detalhes": {}}]
    r = INTER.conciliar(db, cliente=casa["cliente"], por="t", agora=AGORA)
    assert sorted(r["conciliadas"]) == sorted([despesa, guia])
    assert [s["valor"] for s in r["sem_despesa"]] == [999]
    assert _d(db, despesa)["ld_despesa_id"] and not _d(db, guia)["ld_despesa_id"]
    with db.connect() as con:
        livro = banco(con).ler("SELECT data, valor FROM ld_despesas")
        rel = DP.relatorio_do_mes(con, HOJE[:7])
    assert livro == [{"data": HOJE, "valor": 12345}]
    assert rel["total"] == {DP.DESPESA: 12345, DP.REPASSE: 12345}
    assert len(DP.lancamentos_para_o_siaferj(rel)) == 1


# ------------------------------------------------- a automação e o cofre

class _Contexto:
    def __init__(self, db, pode_agir=True):
        self.db, self.agora, self.pasta_dados = db, AGORA, None
        self.processo = {"pode_agir": pode_agir}


def test_cofre_trancado_e_aviso_e_a_despesa_nao_muda(casa, monkeypatch):
    db = casa["db"]
    i = _cadastrar(db)
    _autorizar(db, i)

    def trancado(pasta=None):
        raise INTER.CredencialTrancada("O cofre está trancado.")
    monkeypatch.setattr(INTER, "credencial", trancado)
    r = AUT.pagar(_Contexto(db))
    assert r["situacao"] == "AVISO" and "trancado" in r["relato"]
    assert _d(db, i)["situacao"] == DP.AUTORIZADA and _d(db, i)["tentativas"] == 0


def test_sem_pode_agir_o_processo_so_conta(casa):
    db = casa["db"]
    i = _cadastrar(db)
    _autorizar(db, i)
    r = AUT.pagar(_Contexto(db, pode_agir=False))
    assert r["situacao"] == "AVISO" and r["acoes"] == [] and not casa["inter"].chamadas


# ------------------------------------------------------------------ telas

def _token(c, url):
    import re
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                     c.get(url).get_data(as_text=True)).group(1)


def test_as_telas_abrem_e_o_cadastro_pela_tela_funciona(casa):
    c, db = casa["c"], casa["db"]
    for url in ("/administrativo/despesas", "/administrativo/despesas/nova",
                "/administrativo/despesas/relatorio", "/administrativo/despesas/configuracao"):
        assert c.get(url).status_code == 200, url
    r = c.post("/administrativo/despesas/nova", data={
        "csrf_token": _token(c, "/administrativo/despesas/nova"), "categoria": "MATERIAIS",
        "descricao": "Papel A4 para o balcão", "beneficiario_nome": "PAPELARIA FICTICIA",
        "beneficiario_documento": FAVORECIDO, "valor": "123,45", "vencimento": VENCIMENTO,
        "forma": DP.BOLETO, "codigo": boleto(12345), "documento_especie": "Nota fiscal"},
        follow_redirects=True)
    assert r.status_code == 200 and "Aguardando a autorização do oficial" in r.get_data(as_text=True)
    with db.connect() as con:
        assert DP.listar(con)[0]["valor"] == 12345
