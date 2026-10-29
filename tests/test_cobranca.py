"""A COBRANÇA POR BOLETO — Inter e Unicred, do protocolo ao depósito prévio.

Os dois bancos são FALSOS, na memória, e nunca abrem rede. Os corpos que eles
conferem são os da documentação lida em 27/10/2026: a OpenAPI «Boleto com Pix»
do Inter (`/cobranca/v3`) e os sete PDFs do portal da Unicred. Cada banco
falso RECUSA o pedido que a documentação recusaria — campo obrigatório que
falta, opcional vazio na Unicred, ambiente errado —, para o teste não aprovar
o que o banco de verdade não aceitaria.
"""
from __future__ import annotations

import base64
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import cobranca as CB
import cobranca_automacao as AUT
import cobranca_banco as CBB
import cobranca_inter as CINTER
import cobranca_unicred as CUNI
import despesas_inter as INTER
from bd_nativo import banco

AGORA = datetime(2026, 10, 27, 10, 0, tzinfo=timezone(timedelta(hours=-3)))
VENCIMENTO = "2026-11-03"
CPF = "00000000191"          # 000.000.001-91, o fictício da casa (documentos_ficticios.txt)
PAGADOR = {"nome": "FULANA DE TAL", "documento": "000.000.001-91", "email": "",
           "logradouro": "Rua Um", "numero": "10", "complemento": "", "bairro": "Centro",
           "cidade": "Cidade Exemplo", "uf": "MA", "cep": "65000-000"}
PDF = b"%PDF-1.4 boleto falso"
BENEFICIARIO = "B7CEE6BDC9E04C49A7437EC3E750140A"   # o do exemplo do documento


# ----------------------------------------------------------- os bancos falsos

class InterFalso:
    """A API Cobrança v3 do Inter, na memória."""

    def __init__(self):
        self.chamadas: list[tuple[str, str, dict]] = []
        self.cobrancas: dict[str, dict] = {}
        self.situacao = "A_RECEBER"
        self.perder_resposta = False

    def __call__(self, metodo, url, *, json_corpo=None, form=None, cabecalhos=None):
        self.chamadas.append((metodo, url, {"json": json_corpo, "form": form}))
        assert url.startswith(INTER.ENDERECOS["sandbox"]), "o teste fala só com o sandbox"
        caminho = url.split(".co", 1)[1]
        if caminho == "/oauth/v2/token":
            assert form["scope"] == "boleto-cobranca.read boleto-cobranca.write"
            return INTER.Resposta(200, {"access_token": "tok", "expires_in": 3600})
        assert (cabecalhos or {}).get("Authorization") == "Bearer tok"
        assert caminho.startswith("/cobranca/v3/cobrancas")
        resto = caminho[len("/cobranca/v3/cobrancas"):]
        if metodo == "POST" and resto == "":
            obrigatorios = {"seuNumero", "valorNominal", "dataVencimento", "numDiasAgenda", "pagador"}
            assert obrigatorios <= set(json_corpo), obrigatorios - set(json_corpo)
            assert isinstance(json_corpo["valorNominal"], float)
            assert {"cpfCnpj", "nome", "tipoPessoa", "cep", "endereco", "cidade", "uf"} \
                <= set(json_corpo["pagador"])
            codigo = f"183e982a-34e5-4bc0-9643-{len(self.cobrancas):012d}"
            self.cobrancas[codigo] = json_corpo
            if self.perder_resposta:
                self.perder_resposta = False
                raise TimeoutError("timed out")
            return INTER.Resposta(200, {"codigoSolicitacao": codigo})
        if metodo == "GET" and resto.startswith("?"):
            seu = re.search(r"seuNumero=([^&]+)", resto).group(1)
            assert "dataInicial=" in resto and "dataFinal=" in resto
            achadas = [{"cobranca": {"codigoSolicitacao": k, "seuNumero": v["seuNumero"]}}
                       for k, v in self.cobrancas.items() if v["seuNumero"] == seu]
            return INTER.Resposta(200, {"cobrancas": achadas, "totalPaginas": 1})
        codigo = resto.strip("/").split("/")[0]
        if codigo not in self.cobrancas:
            return INTER.Resposta(404, {"title": "Não encontrada"})
        if metodo == "GET" and resto.endswith("/pdf"):
            return INTER.Resposta(200, {"pdf": base64.b64encode(PDF).decode()})
        if metodo == "POST" and resto.endswith("/cancelar"):
            assert len(json_corpo["motivoCancelamento"]) <= 50
            self.situacao = "CANCELADO"
            return INTER.Resposta(202, b"")
        if metodo == "GET":
            corpo = {"cobranca": {"codigoSolicitacao": codigo, "situacao": self.situacao,
                                  "valorNominal": self.cobrancas[codigo]["valorNominal"],
                                  "dataSituacao": "2026-10-28"},
                     "boleto": {"nossoNumero": "12345678",
                                "linhaDigitavel": "0" * 47, "codigoBarras": "0" * 44},
                     "pix": {"txid": "a" * 30, "pixCopiaECola": "000201...6304ABCD"}}
            if self.situacao == "RECEBIDO":
                corpo["cobranca"].update({"valorTotalRecebido": "123.45",
                                          "origemRecebimento": "PIX"})
            return INTER.Resposta(200, corpo)
        return INTER.Resposta(404, {"title": "Não encontrado", "detail": caminho})

    def posts(self, trecho: str) -> list[dict]:
        return [c for m, u, c in self.chamadas if m == "POST" and trecho in u]


class UnicredFalsa:
    """A cobrança v2 da Unicred, na memória."""

    def __init__(self):
        self.chamadas: list[tuple[str, str, dict]] = []
        self.titulos: dict[str, dict] = {}
        self.status = "ABERTO"
        self.processando = False

    def __call__(self, metodo, url, *, json_corpo=None, cabecalhos=None):
        self.chamadas.append((metodo, url, {"json": json_corpo, "cab": cabecalhos or {}}))
        assert url.startswith(CUNI.ENDERECOS["sandbox"] + "/"), "o teste fala só com a homologação"
        caminho = url[len(CUNI.ENDERECOS["sandbox"]):]
        cab = cabecalhos or {}
        if caminho == CUNI.CAMINHO_DO_TOKEN:
            assert cab.get("apiKey") == "chave"
            assert json_corpo == {"nomeUsuario": "usuario", "senha": "senha"}
            # A forma do curl que a Unicred mandou ao oficial (28/10/2026).
            return INTER.Resposta(200, {"accessToken": "tok-u", "tokenExpirationTime": 28800,
                                        "refreshToken": "r", "refreshTokenExpirationTime": 36000})
        assert cab.get("Authorization") == "Bearer tok-u"
        assert cab.get("cooperativa") == "0001" and cab.get("apiKey") == "chave"
        m = re.fullmatch(rf"/cobranca/(v1|v2)/beneficiarios/{BENEFICIARIO}/titulos(.*)", caminho)
        assert m, caminho
        versao, resto = m.groups()
        if metodo == "POST" and resto == "":
            assert {"beneficiarioVariacaoCarteira", "seuNumero", "valor", "vencimento",
                    "pagador"} <= set(json_corpo)
            # «Não informar conteúdo igual a null ou brancos nos campos não obrigatórios.»
            def vazios(d):
                for k, v in d.items():
                    if isinstance(v, dict):
                        yield from vazios(v)
                    elif v in (None, ""):
                        yield k
            assert not list(vazios(json_corpo)), list(vazios(json_corpo))
            assert len(json_corpo["pagador"]["nomeRazaoSocial"]) <= 40
            ident = f"{len(self.titulos):032x}"
            self.titulos[ident] = json_corpo
            return INTER.Resposta(200, {"message": "OK", "httpStatus": 200, "id_titulo": ident})
        ident = resto.strip("/").split("/")[0]
        if ident not in self.titulos:
            return INTER.Resposta(404, {"message": "Título não encontrado", "errorCode": "COB005BCORE"})
        acao = resto.strip("/").split("/")[1] if "/" in resto.strip("/") else ""
        if metodo == "GET" and acao == "status":
            if self.processando:
                return INTER.Resposta(202, b"")
            corpo = {"codBarras": "1" * 44, "linhaDigitavel": "1" * 46, "nossoNumero": "00000231444",
                     "dataDeVencimento": VENCIMENTO, "valor": 100.0, "status": self.status,
                     "motivo": None, "qrCodePix": None}
            if self.status == "LIQUIDADO":
                corpo["pagamentos"] = {"data": "2026-10-29", "valor": 100.0}
            return INTER.Resposta(200, corpo)
        if metodo == "GET" and acao == "":
            return INTER.Resposta(200, PDF, "application/pdf")
        if metodo == "POST" and acao == "baixa":
            assert versao == "v2" and json_corpo["tipo"] == "SOLICITACAO_CEDENTE"
            self.status = "BAIXADO"
            return INTER.Resposta(201, {"codigoInstrucao": "00000000000067835258"})
        if metodo == "POST" and acao == "concessao-abatimento":
            assert versao == "v2" and json_corpo["justificativa"]
            assert json_corpo["valorAbatimento"] < self.titulos[ident]["valor"]
            return INTER.Resposta(201, {"codigoInstrucao": "1"})
        if metodo == "POST" and acao == "cancelamento-concessao-abatimento":
            assert versao == "v1", "o documento escreve v1 neste caminho"
            return INTER.Resposta(201, {"codigoInstrucao": "2"})
        if metodo == "POST" and acao == "protesto-automatico":
            assert set(json_corpo) == {"enviaProtestoAposVencimento", "quantidadeDiasProtesto",
                                       "protestoDiasUteis"}
            return INTER.Resposta(201, {"codigoInstrucao": "3"})
        return INTER.Resposta(404, {"message": caminho})


CAMPOS_INTER = {"client_id": "id-ficticio", "client_secret": "segredo-ficticio",
                "crt_pem": "x", "key_pem": "x"}
CAMPOS_UNICRED = {"api_key": "chave", "usuario": "usuario",
                  "senha": "senha", "cooperativa": "0001",
                  "beneficiario": BENEFICIARIO, "variacao_carteira": "43"}


# ------------------------------------------------------------------ a casa

@pytest.fixture
def casa(cg_casa_logada):
    db = cg_casa_logada["db"]
    with db.transaction() as con:
        CB.gravar_configuracao(con, {**CB.PADRAO, "cobranca_ligada": "1",
                                     "cobranca_ambiente": "sandbox"})
        bd = banco(con)
        p = bd.escrever(
            """INSERT INTO cx_protocolos (numero, data_abertura, interessado,
                   interessado_documento, criado_em)
               VALUES ('2026.10.900', '2026-10-27', 'FULANA DE TAL', %s, '2026-10-27T09:00:00')
               RETURNING id""", (CPF,))
        protocolo_id = int(p[0]["id"])
        for valor in ("80,00", "43,45"):
            bd.escrever("INSERT INTO cx_protocolo_atos (protocolo_id, descricao, valor_total) "
                        "VALUES (%s, 'Certidão', %s)", (protocolo_id, valor))
    inter, uni = InterFalso(), UnicredFalsa()
    return {**cg_casa_logada, "protocolo_id": protocolo_id, "inter": inter, "unicred": uni,
            "c_inter": CINTER.ClienteCobrancaInter("sandbox", inter, CAMPOS_INTER),
            "c_uni": CUNI.ClienteCobrancaUnicred("sandbox", uni, CAMPOS_UNICRED)}


def _cadastrar(casa, *, banco_codigo=CB.INTER, valor=12345, protocolo=True):
    with casa["db"].transaction() as con:
        return CB.cadastrar(con, agora=AGORA, por="beatriz", banco_codigo=banco_codigo,
                            ambiente="sandbox",
                            protocolo_id=casa["protocolo_id"] if protocolo else None,
                            valor_centavos=valor, vencimento=VENCIMENTO, pagador=PAGADOR,
                            mensagem="Emolumentos do protocolo 2026.10.900.",
                            dias_apos_vencimento=30)


def _c(casa, i):
    with casa["db"].connect() as con:
        return CB.cobranca(con, i)


# ------------------------------------------------------ o que se cobra

def test_o_valor_sugerido_e_o_que_falta_pagar_do_protocolo(casa):
    with casa["db"].connect() as con:
        r = CB.a_pagar_do_protocolo(con, casa["protocolo_id"])
    assert (r["itens"], r["devido"], r["sugerido"]) == (2, 12345, 12345)


def test_pagador_sem_documento_valido_ou_sem_endereco_e_recusado(casa):
    with pytest.raises(CB.CobrancaError, match="CPF ou CNPJ"):
        CB.conferir_pagador({**PAGADOR, "documento": "111.111.111-12"})
    with pytest.raises(CB.CobrancaError, match="endereço"):
        CB.conferir_pagador({**PAGADOR, "logradouro": ""})
    with pytest.raises(CB.CobrancaError, match="CEP"):
        CB.conferir_pagador({**PAGADOR, "cep": "650"})


def test_abaixo_do_minimo_do_inter_e_vencimento_passado_sao_recusados(casa):
    with pytest.raises(CB.CobrancaError, match="2,50"):
        _cadastrar(casa, valor=249)
    with casa["db"].transaction() as con, pytest.raises(CB.CobrancaError, match="anterior"):
        CB.cadastrar(con, agora=AGORA, por="b", banco_codigo=CB.INTER, ambiente="sandbox",
                     protocolo_id=None, valor_centavos=1000, vencimento="2026-10-26",
                     pagador=PAGADOR)


def test_o_seu_numero_e_o_da_linha_e_nao_se_repete(casa):
    a, b = _cadastrar(casa), _cadastrar(casa)
    assert (_c(casa, a)["seu_numero"], _c(casa, b)["seu_numero"]) == (f"CG{a}", f"CG{b}")
    # A recusa vem do índice único: a transação inteira cai, e por isso o
    # `raises` fica POR FORA dela (no PostgreSQL a transação abortada não comita).
    # A ponte devolve a frase do SQLite («UNIQUE constraint failed: ...seu_numero»),
    # e o PostgreSQL puro, o nome do índice: os dois trazem `seu_numero`.
    with pytest.raises(Exception, match="seu_numero"):
        with casa["db"].transaction() as con:
            banco(con).escrever("UPDATE cb_cobrancas SET seu_numero = %s WHERE id = %s",
                                (f"CG{a}", b))


def test_os_valores_do_banco_se_leem_com_ponto_decimal():
    assert CB.centavos_do_banco("1234.56") == 123456
    assert CB.centavos_do_banco(1234.56) == 123456
    assert CB.centavos_do_banco("1.234") == 123      # ponto é decimal, e não milhar
    assert CB.centavos_do_banco(None) is None


# --------------------------------------------------------------- o Inter

def test_inter_emite_com_o_corpo_do_contrato_e_fica_aberta(casa):
    i = _cadastrar(casa)
    nova = CBB.emitir(casa["db"], i, cliente=casa["c_inter"], por="beatriz", agora=AGORA)
    c = _c(casa, i)
    assert nova == CB.ABERTA and c["linha_digitavel"] == "0" * 47 and c["pix_copia_e_cola"]
    corpo = casa["inter"].posts("/cobranca/v3/cobrancas")[0]["json"]
    assert corpo["valorNominal"] == 123.45 and corpo["numDiasAgenda"] == 30
    assert corpo["pagador"]["tipoPessoa"] == "FISICA" and corpo["pagador"]["cep"] == "65000000"
    assert corpo["mensagem"]["linha1"].startswith("Emolumentos")


def test_inter_pago_vira_recebida_com_o_valor_e_a_forma(casa):
    i = _cadastrar(casa)
    CBB.emitir(casa["db"], i, cliente=casa["c_inter"], por="b", agora=AGORA)
    casa["inter"].situacao = "RECEBIDO"
    assert CBB.atualizar(casa["db"], i, cliente=casa["c_inter"], por="b", agora=AGORA) == CB.RECEBIDA
    c = _c(casa, i)
    assert (c["valor_recebido"], c["forma_recebida"], c["data_pagamento"]) == (12345, "PIX", "2026-10-28")


def test_marcado_como_recebido_no_banco_nao_e_dinheiro_na_conta(casa):
    i = _cadastrar(casa)
    CBB.emitir(casa["db"], i, cliente=casa["c_inter"], por="b", agora=AGORA)
    casa["inter"].situacao = "MARCADO_RECEBIDO"
    assert CBB.atualizar(casa["db"], i, cliente=casa["c_inter"], por="b", agora=AGORA) == CB.BAIXADA
    assert "NÃO passou" in _c(casa, i)["banco_motivo"]


def test_emissao_sem_resposta_e_achada_pelo_seu_numero_e_nao_reemitida(casa):
    i = _cadastrar(casa)
    casa["inter"].perder_resposta = True
    assert CBB.emitir(casa["db"], i, cliente=casa["c_inter"], por="b", agora=AGORA) == CB.EMITINDO
    assert not _c(casa, i)["banco_id"]
    assert CBB.atualizar(casa["db"], i, cliente=casa["c_inter"], por="b", agora=AGORA) == CB.ABERTA
    assert len(casa["inter"].posts("/cobranca/v3/cobrancas")) == 1, "não emite de novo"


def test_sem_resposta_e_sem_rastro_vira_falhou_depois_da_espera(casa):
    i = _cadastrar(casa)
    with casa["db"].transaction() as con:
        CB.marcar_emitindo(con, i, por="b", agora=AGORA)
    assert CBB.atualizar(casa["db"], i, cliente=casa["c_inter"], por="b", agora=AGORA) == CB.EMITINDO
    depois = AGORA + CB.PRAZO_DE_ESPERA + timedelta(minutes=1)
    assert CBB.atualizar(casa["db"], i, cliente=casa["c_inter"], por="b", agora=depois) == CB.FALHOU
    assert "Confira no internet banking" in _c(casa, i)["erro"]


def test_cobranca_de_teste_nunca_vai_ao_banco_de_producao(casa):
    i = _cadastrar(casa)
    producao = CINTER.ClienteCobrancaInter("producao", lambda *a, **k: pytest.fail("rede"),
                                           CAMPOS_INTER)
    with pytest.raises(CBB.BancoError, match="não vai a outro ambiente"):
        CBB.emitir(casa["db"], i, cliente=producao, por="b", agora=AGORA)
    assert _c(casa, i)["situacao"] == CB.A_EMITIR


def test_inter_cancela_no_banco_antes_de_cancelar_aqui(casa):
    i = _cadastrar(casa)
    CBB.emitir(casa["db"], i, cliente=casa["c_inter"], por="b", agora=AGORA)
    with casa["db"].transaction() as con:
        CB.pedir(con, i, "CANCELAR", {"motivo": "Cliente pagou no balcão"}, por="mario", agora=AGORA)
    assert _c(casa, i)["situacao"] == CB.ABERTA, "só depois do banco"
    CBB.executar_pedido(casa["db"], i, cliente=casa["c_inter"], por="mario", agora=AGORA)
    c = _c(casa, i)
    assert c["situacao"] == CB.CANCELADA and c["pedido"] == ""
    assert casa["inter"].posts("/cancelar")


def test_o_inter_nao_tem_abatimento_e_o_pedido_e_recusado_antes_da_rede(casa):
    i = _cadastrar(casa)
    CBB.emitir(casa["db"], i, cliente=casa["c_inter"], por="b", agora=AGORA)
    with casa["db"].transaction() as con, pytest.raises(CB.CobrancaError, match="não oferece"):
        CB.pedir(con, i, "ABATIMENTO", {"valor": 100, "justificativa": "acordo"}, por="m", agora=AGORA)


# --------------------------------------------------------------- a Unicred

def test_unicred_emite_sem_campo_vazio_e_com_o_id_do_titulo(casa):
    i = _cadastrar(casa, banco_codigo=CB.UNICRED, valor=10000)
    nova = CBB.emitir(casa["db"], i, cliente=casa["c_uni"], por="b", agora=AGORA)
    c = _c(casa, i)
    assert nova == CB.ABERTA and c["banco_id"] == f"{0:032x}" and c["nosso_numero"] == "00000231444"
    corpo = casa["unicred"].chamadas[1][2]["json"]
    assert corpo["beneficiarioVariacaoCarteira"] == 43 and corpo["pagador"]["tipoPessoa"] == "F"
    assert "complemento" not in corpo["pagador"]["endereco"]


def test_unicred_ainda_processando_fica_emitindo(casa):
    casa["unicred"].processando = True
    i = _cadastrar(casa, banco_codigo=CB.UNICRED, valor=10000)
    assert CBB.emitir(casa["db"], i, cliente=casa["c_uni"], por="b", agora=AGORA) == CB.EMITINDO


def test_unicred_liquidado_vira_recebida_com_o_pagamento(casa):
    i = _cadastrar(casa, banco_codigo=CB.UNICRED, valor=10000)
    CBB.emitir(casa["db"], i, cliente=casa["c_uni"], por="b", agora=AGORA)
    casa["unicred"].status = "LIQUIDADO"
    CBB.atualizar(casa["db"], i, cliente=casa["c_uni"], por="b", agora=AGORA)
    c = _c(casa, i)
    assert (c["situacao"], c["valor_recebido"], c["data_pagamento"]) == (CB.RECEBIDA, 10000, "2026-10-29")


def test_unicred_abatimento_protesto_e_cancelamento_pelos_caminhos_do_documento(casa, tmp_path):
    i = _cadastrar(casa, banco_codigo=CB.UNICRED, valor=10000)
    CBB.emitir(casa["db"], i, cliente=casa["c_uni"], por="b", agora=AGORA)
    passos = [("ABATIMENTO", {"valor": 2000, "justificativa": "Acordo com o cliente"}),
              ("CANCELAR_ABATIMENTO", {"justificativa": "Revisão interna"}),
              ("PROTESTO", {"ligado": True, "dias": 10, "dias_uteis": True}),
              ("CANCELAR", {"motivo": "Desistência do serviço"})]
    for acao, dados in passos:
        with casa["db"].transaction() as con:
            CB.pedir(con, i, acao, dados, por="mario", agora=AGORA)
        frase = CBB.executar_pedido(casa["db"], i, cliente=casa["c_uni"], por="mario",
                                    agora=AGORA, pasta=tmp_path)
        assert "assíncrona" in frase, (acao, frase)
    assert _c(casa, i)["situacao"] == CB.CANCELADA
    caminhos = [u for m, u, _ in casa["unicred"].chamadas if m == "POST"]
    assert any("/v1/" in u and u.endswith("cancelamento-concessao-abatimento") for u in caminhos)


def test_um_pedido_por_vez(casa):
    i = _cadastrar(casa, banco_codigo=CB.UNICRED, valor=10000)
    CBB.emitir(casa["db"], i, cliente=casa["c_uni"], por="b", agora=AGORA)
    with casa["db"].transaction() as con:
        CB.pedir(con, i, "PROTESTO", {"ligado": False, "dias": 0, "dias_uteis": False},
                 por="m", agora=AGORA)
    with casa["db"].transaction() as con, pytest.raises(CB.CobrancaError, match="Já há"):
        CB.pedir(con, i, "CANCELAR", {"motivo": "outro pedido"}, por="m", agora=AGORA)


def test_as_tres_formas_de_erro_da_unicred_viram_frase():
    assert "numero: no máximo 5" in CUNI._frase(
        {"message": "Erro ao validar atributo.",
         "body": [{"Fields": "pagador.endereco.numero", "message": "no máximo 5"}]})
    assert "C1" in CUNI._frase({"message": "A situação do título deve ser Aberto.", "errorCode": "C1"})
    assert "nulo" in CUNI._frase({"message": "Erro", "details": ["dias: não pode ser nulo"]})


def test_o_id_do_titulo_se_le_nas_duas_formas_do_documento():
    ident = "0000008d56aa461796227f0e30c7f5f2"
    assert CUNI.id_do_titulo({"id_titulo": ident}) == ident
    assert CUNI.id_do_titulo(f"Preview: id_titulo:{ident}".encode()) == ident


def test_o_token_da_unicred_vale_a_validade_que_ela_devolve(casa, monkeypatch):
    """`tokenExpirationTime` (8 h no curl da Unicred): um token só para a rodada inteira."""
    relogio = [1000.0]
    monkeypatch.setattr(CUNI.time, "monotonic", lambda: relogio[0])
    cliente = casa["c_uni"]
    cliente.token()
    relogio[0] += 4 * 3600
    cliente.token()
    tokens = [u for m, u, _ in casa["unicred"].chamadas if u.endswith(CUNI.CAMINHO_DO_TOKEN)]
    assert len(tokens) == 1, "dentro das 8 horas o token se reaproveita"
    relogio[0] += 4 * 3600
    cliente.token()
    tokens = [u for m, u, _ in casa["unicred"].chamadas if u.endswith(CUNI.CAMINHO_DO_TOKEN)]
    assert len(tokens) == 2, "vencido, pede outro"


def test_credencial_da_unicred_com_campo_torto_e_recusada():
    with pytest.raises(CB.CobrancaError, match="hexadecimais"):
        CUNI.conferir_credencial({**CAMPOS_UNICRED, "beneficiario": "abc"})
    with pytest.raises(CB.CobrancaError, match="Faltam"):
        CUNI.conferir_credencial({**CAMPOS_UNICRED, "senha": ""})


# ------------------------------------------------------- o caixa e o PDF

def _caixa(casa, operador="MARIO EXEMPLO DOS SANTOS"):
    with casa["db"].transaction() as con:
        return int(banco(con).escrever(
            """INSERT INTO cx_caixas (data, operador_nome, aberto_em, situacao)
               VALUES ('2026-10-27', %s, '2026-10-27T08:00:00', 'ABERTO') RETURNING id""",
            (operador,))[0]["id"])


def test_paga_vira_deposito_previo_do_protocolo_no_caixa_aberto(casa):
    i = _cadastrar(casa)
    CBB.emitir(casa["db"], i, cliente=casa["c_inter"], por="b", agora=AGORA)
    casa["inter"].situacao = "RECEBIDO"
    CBB.atualizar(casa["db"], i, cliente=casa["c_inter"], por="b", agora=AGORA)
    with casa["db"].transaction() as con, pytest.raises(CB.CobrancaError, match="Abra o seu caixa"):
        CB.lancar_no_caixa(con, i, por="mario", agora=AGORA, caixa_id=None)
    caixa_id = _caixa(casa)
    with casa["db"].transaction() as con:
        feito = CB.lancar_no_caixa(con, i, por="mario", agora=AGORA, caixa_id=caixa_id)
    with casa["db"].connect() as con:
        dep = banco(con).um("SELECT * FROM cx_depositos WHERE id = %s", (feito["id"],))
        lanc = banco(con).um("SELECT * FROM cx_lancamentos WHERE id = %s", (dep["lancamento_id"],))
    assert dep["protocolo_id"] == casa["protocolo_id"] and lanc["forma_pagamento"] == "PIX"
    assert _c(casa, i)["situacao"] == CB.LANCADA
    with casa["db"].transaction() as con, pytest.raises(CB.CobrancaError):
        CB.lancar_no_caixa(con, i, por="mario", agora=AGORA, caixa_id=caixa_id)


def test_lancada_nao_volta_por_consulta(casa):
    i = _cadastrar(casa)
    CBB.emitir(casa["db"], i, cliente=casa["c_inter"], por="b", agora=AGORA)
    with casa["db"].transaction() as con:
        CB.gravar_resposta(con, i, {"situacao": CB.LANCADA}, por="x", agora=AGORA)
        assert CB.gravar_resposta(con, i, {"situacao": CB.ABERTA}, por="x", agora=AGORA) == CB.LANCADA


def test_o_pdf_se_guarda_na_pasta_e_o_abatimento_o_apaga(casa, tmp_path):
    i = _cadastrar(casa, banco_codigo=CB.UNICRED, valor=10000)
    CBB.emitir(casa["db"], i, cliente=casa["c_uni"], por="b", agora=AGORA)
    CBB.guardar_pdf(casa["db"], i, cliente=casa["c_uni"], pasta=tmp_path)
    assert CB.caminho_do_pdf(tmp_path, i).read_bytes() == PDF and _c(casa, i)["pdf_guardado"] == 1
    with casa["db"].transaction() as con:
        CB.pedir(con, i, "ABATIMENTO", {"valor": 500, "justificativa": "Acordo"}, por="m", agora=AGORA)
    CBB.executar_pedido(casa["db"], i, cliente=casa["c_uni"], por="m", agora=AGORA, pasta=tmp_path)
    assert not CB.caminho_do_pdf(tmp_path, i).exists() and _c(casa, i)["pdf_guardado"] == 0


# ------------------------------------------------------------ a automação

class _Contexto:
    def __init__(self, db, pasta, pode_agir=True):
        self.db, self.agora, self.pasta_dados = db, AGORA, pasta
        self.processo = {"pode_agir": pode_agir}


def test_sem_pode_agir_a_rodada_so_conta(casa, tmp_path):
    _cadastrar(casa)
    r = AUT.acompanhar(_Contexto(casa["db"], tmp_path, pode_agir=False))
    assert r["situacao"] == "AVISO" and r["acoes"] == [] and not casa["inter"].chamadas


def test_a_rodada_emite_consulta_guarda_o_pdf_e_avisa_a_paga(casa, tmp_path, monkeypatch):
    i = _cadastrar(casa)
    monkeypatch.setattr(CBB, "cliente_da_casa", lambda cfg, **kw: casa["c_inter"])
    r = AUT.acompanhar(_Contexto(casa["db"], tmp_path))
    assert _c(casa, i)["situacao"] == CB.ABERTA and _c(casa, i)["pdf_guardado"] == 1, r
    casa["inter"].situacao = "RECEBIDO"
    r = AUT.acompanhar(_Contexto(casa["db"], tmp_path))
    assert r["situacao"] == "AVISO" and r["achados"][0]["tipo"] == "PAGA_FALTA_LANCAR"
    assert _c(casa, i)["situacao"] == CB.RECEBIDA, "o robô não lança no caixa"


def test_com_a_emissao_desligada_a_rodada_nao_emite(casa, tmp_path, monkeypatch):
    with casa["db"].transaction() as con:
        CB.gravar_configuracao(con, {**CB.PADRAO, "cobranca_ligada": "0"})
    i = _cadastrar(casa)
    monkeypatch.setattr(CBB, "cliente_da_casa", lambda cfg, **kw: casa["c_inter"])
    AUT.acompanhar(_Contexto(casa["db"], tmp_path))
    assert _c(casa, i)["situacao"] == CB.A_EMITIR and not casa["inter"].chamadas


def test_cofre_trancado_e_aviso_e_nada_muda(casa, tmp_path, monkeypatch):
    i = _cadastrar(casa)

    def trancado(pasta=None):
        raise INTER.CredencialTrancada("O cofre está trancado.")
    monkeypatch.setattr(INTER, "credencial", trancado)
    r = AUT.acompanhar(_Contexto(casa["db"], tmp_path))
    assert r["situacao"] == "AVISO" and "trancado" in r["relato"]
    assert _c(casa, i)["situacao"] == CB.A_EMITIR


def test_o_processo_entra_no_catalogo_da_automacao():
    import automacao_processos as PROC
    assert "COBRANCA_ACOMPANHAR" in {s["codigo"] for s in PROC.todas_as_sementes()}


# ------------------------------------------------------------------ telas

def _token(c, url):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                     c.get(url).get_data(as_text=True)).group(1)


def test_as_telas_abrem_e_o_cadastro_pela_tela_espera_a_emissao_ligada(casa):
    c, db = casa["c"], casa["db"]
    with db.transaction() as con:
        CB.gravar_configuracao(con, {**CB.PADRAO, "cobranca_ligada": "0"})
    for url in ("/caixa/cobranca", "/caixa/cobranca/configuracao",
                f"/caixa/cobranca/nova?protocolo_id={casa['protocolo_id']}"):
        assert c.get(url).status_code == 200, url
    pagina = c.get(f"/caixa/cobranca/nova?protocolo_id={casa['protocolo_id']}").get_data(as_text=True)
    assert "123,45" in pagina and "FULANA DE TAL" in pagina
    r = c.post("/caixa/cobranca/nova", data={
        "csrf_token": _token(c, "/caixa/cobranca/nova"), "protocolo_id": casa["protocolo_id"],
        "valor": "123,45", "vencimento": VENCIMENTO, **PAGADOR}, follow_redirects=True)
    assert r.status_code == 200 and "desligada" in r.get_data(as_text=True)
    with db.connect() as con:
        linha = CB.lista(con)[0]
    assert (linha["situacao"], linha["valor"]) == (CB.A_EMITIR, 12345)
    assert c.get(f"/caixa/cobranca/{linha['id']}").status_code == 200


def test_o_protocolo_oferece_cobrar_por_boleto(casa):
    pagina = casa["c"].get(f"/caixa/protocolos/{casa['protocolo_id']}").get_data(as_text=True)
    assert "Cobrar por boleto" in pagina
