"""Marco (c) da base comum das Centrais — o SIRC no transporte comum.

**NENHUM TESTE AQUI FALA COM A INTERNET, E MUITO MENOS COM A DATAPREV.** O SIRC
só tem ambiente de PRODUÇÃO; por isso a rede é trocada em
`centrais_http._abrir_conexao` (a mesma porta dos marcos a e b), e a credencial
é fictícia, gravada numa pasta temporária. Nada de CNS, CNPJ, nome de gente ou
IP de verdade — o CNS daqui é `123456`, inventado.

O QUE ELES GUARDAM
  - `sirc_cliente._bater` passa por `centrais_http.requisitar(...)`, com POST,
    o mesmo endereço https, o mesmo envelope SOAP 1.2 e as MESMAS frases de
    balcão;
  - envio ao INSS NÃO se repete sozinho (uma abertura de conexão só, mesmo
    com falha de rede);
  - o `User-Agent` não leva mais o CNS da serventia;
  - o certificado continua conferido (só as cifras antigas liberadas);
  - cada chamada vira uma linha em `centrais_log` — sem a senha (que viaja
    DENTRO do corpo), sem o CNS, sem o lote;
  - o SIRC NÃO entra na fila de homologação (não tem homologação).
"""
from __future__ import annotations

import sqlite3
import ssl
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import centrais_cred as CRED  # noqa: E402
import centrais_fila as FILA  # noqa: E402
import centrais_http as HTTP  # noqa: E402
import centrais_log as LOG  # noqa: E402
import centrais_schema as SCH  # noqa: E402
import protesto_centrais_fila as PFILA  # noqa: E402
import sirc_cliente as SC  # noqa: E402

CNS_FICTICIO = "123456"
USUARIO = "usuario-ficticio-sirc"
SENHA = "Senha-Ficticia-SIRC-9"

SUCESSO = (
    '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">'
    '<soap:Body><enviarMovimentoObitoResponse xmlns="http://dataprev.gov.br/sirc">'
    '<resultado>Recebido com sucesso</resultado>'
    '</enviarMovimentoObitoResponse></soap:Body></soap:Envelope>').encode()

FALHA_SOAP = (
    '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">'
    '<soap:Body><soap:Fault><soap:Code><soap:Value>soap:Sender</soap:Value>'
    '</soap:Code><soap:Reason><soap:Text xml:lang="pt">Lote fora do layout'
    '</soap:Text></soap:Reason></soap:Fault></soap:Body></soap:Envelope>'
).encode()


# ------------------------------------------------------------- a rede falsa


class _RespostaFalsa:
    def __init__(self, status=200, corpo=b""):
        self.status = status
        self._corpo = corpo

    def read(self):
        return self._corpo

    def getheaders(self):
        return [("Content-Type", "application/soap+xml")]


class _ConexaoFalsa:
    def __init__(self, rede, esquema, host, porta, contexto):
        self.rede = rede
        rede["aberturas"].append({"esquema": esquema, "host": host,
                                  "porta": porta, "contexto": contexto})

    def request(self, metodo, caminho, body=None, headers=None):
        self.rede["pedidos"].append({"metodo": metodo, "caminho": caminho,
                                     "corpo": body,
                                     "cabecalhos": dict(headers or {})})
        passo = (self.rede["roteiro"].pop(0) if self.rede["roteiro"]
                 else _RespostaFalsa(200, SUCESSO))
        if isinstance(passo, BaseException):
            raise passo
        self._resposta = passo

    def getresponse(self):
        return self._resposta

    def close(self):
        pass


@pytest.fixture()
def rede(monkeypatch):
    r = {"roteiro": [], "pedidos": [], "aberturas": []}

    def abrir(esquema, host, porta, prazo, contexto):
        return _ConexaoFalsa(r, esquema, host, porta, contexto)

    monkeypatch.setattr(HTTP, "_abrir_conexao", abrir)
    monkeypatch.setattr(HTTP, "_dormir", lambda s: None)
    return r


class _BancoFalso:
    """O mínimo de `database.Database`: `connect()` e `transaction()`."""

    def __init__(self, caminho):
        self.caminho = str(caminho)
        c = self.connect()
        SCH.init_centrais_schema(c)
        c.commit()
        c.close()

    def connect(self):
        c = sqlite3.connect(self.caminho, timeout=5)
        c.row_factory = sqlite3.Row
        return c

    @contextmanager
    def transaction(self):
        c = self.connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()


@pytest.fixture()
def banco(tmp_path, monkeypatch):
    db = _BancoFalso(tmp_path / "centrais.sqlite3")
    monkeypatch.setattr(LOG, "_BANCO", db)
    return db


@pytest.fixture()
def cofre(tmp_path, monkeypatch):
    """Credencial FICTÍCIA do SIRC (o único ambiente dele é PRODUCAO, e por
    isso mesmo ela mora numa pasta temporária e a rede é falsa)."""
    pasta = tmp_path / "cofre"
    pasta.mkdir()
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: pasta)
    CRED.gravar(CRED.SIRC, usuario=USUARIO, senha=SENHA,
                ambiente=CRED.PRODUCAO, pasta=pasta)
    return pasta


@pytest.fixture(autouse=True)
def _sem_relogio_entre_testes():
    SC._ULTIMO_ENVIO = None
    yield
    SC._ULTIMO_ENVIO = None


def _linhas_do_log(db) -> list[dict]:
    c = db.connect()
    try:
        return [dict(x) for x in c.execute(
            "SELECT * FROM centrais_log ORDER BY id")]
    finally:
        c.close()


# ------------------------------------------------- o transporte é o comum


def test_enviar_passa_pelo_transporte_comum(rede, cofre, banco):
    resultado = SC.enviar("OBITO", "<lote/>", cns=CNS_FICTICIO, pasta=cofre)
    assert resultado == "Recebido com sucesso"
    assert len(rede["aberturas"]) == 1
    abertura = rede["aberturas"][0]
    assert abertura["esquema"] == "https"
    assert abertura["host"] == "sirc.dataprev.gov.br"
    assert abertura["porta"] == 443
    pedido = rede["pedidos"][0]
    assert pedido["metodo"] == "POST"
    assert pedido["caminho"] == "/SircWs/Movimento"
    corpo = pedido["corpo"].decode()
    assert "<enviarMovimentoObito" in corpo
    assert f"<cns>{CNS_FICTICIO}</cns>" in corpo
    assert "<conteudo>&lt;lote/&gt;</conteudo>" in corpo
    assert pedido["cabecalhos"]["Content-Type"] == (
        'application/soap+xml; charset=utf-8; action=""')


def test_user_agent_nao_leva_o_cns(rede, cofre, banco):
    SC.validar("NASCIMENTO", "<lote/>", cns=CNS_FICTICIO, pasta=cofre)
    ua = rede["pedidos"][0]["cabecalhos"]["User-Agent"]
    assert ua == HTTP.USER_AGENT_PADRAO
    assert not any(ch.isdigit() for ch in ua)
    fonte = (RAIZ / "sirc_cliente.py").read_text(encoding="utf-8")
    assert "CNS0" not in fonte and "000000" not in fonte


def test_o_certificado_continua_conferido_so_as_cifras_abrem(rede, cofre,
                                                            banco):
    SC.validar_cancelamento("<x/>", cns=CNS_FICTICIO, pasta=cofre)
    contexto = rede["aberturas"][0]["contexto"]
    assert isinstance(contexto, ssl.SSLContext)
    assert contexto.verify_mode == ssl.CERT_REQUIRED
    assert contexto.check_hostname is True
    assert contexto.minimum_version >= ssl.TLSVersion.TLSv1_2


def test_falha_de_rede_nao_se_repete_e_mantem_a_frase(rede, cofre, banco):
    rede["roteiro"].extend([OSError("rede indisponível"),
                            _RespostaFalsa(200, SUCESSO)])
    with pytest.raises(SC.SircClienteError) as erro:
        SC.enviar("NASCIMENTO", "<lote/>", cns=CNS_FICTICIO, pasta=cofre)
    texto = str(erro.value)
    assert len(rede["aberturas"]) == 1, "envio ao INSS não se repete sozinho"
    assert "Não consegui falar com o SIRC em sirc.dataprev.gov.br" in texto
    assert "rede indisponível" in texto
    assert "nada foi considerado enviado" in texto
    assert SENHA not in texto and USUARIO not in texto


def test_o_minuto_continua_valendo_depois_de_falha(rede, cofre, banco):
    rede["roteiro"].append(OSError("caiu"))
    with pytest.raises(SC.SircClienteError):
        SC.enviar("OBITO", "<lote/>", cns=CNS_FICTICIO, pasta=cofre)
    with pytest.raises(SC.SircClienteError, match="segundos"):
        SC.enviar("OBITO", "<lote/>", cns=CNS_FICTICIO, pasta=cofre)
    assert len(rede["aberturas"]) == 1


def test_falha_soap_com_http_500_vira_recusa_com_o_motivo(rede, cofre, banco):
    rede["roteiro"].append(_RespostaFalsa(500, FALHA_SOAP))
    with pytest.raises(SC.SircRecusou, match="Lote fora do layout"):
        SC.enviar("CASAMENTO", "<lote/>", cns=CNS_FICTICIO, pasta=cofre)


def test_resposta_sem_resultado_nao_passa_calada(rede, cofre, banco):
    rede["roteiro"].append(_RespostaFalsa(503, b"<html>indisponivel</html>"))
    with pytest.raises(SC.SircRecusou, match="sem o «resultado»"):
        SC.declarar_inexistencia("<x/>", cns=CNS_FICTICIO, pasta=cofre)


def test_sem_credencial_nao_abre_conexao(rede, tmp_path, banco):
    with pytest.raises(CRED.CredencialError):
        SC.enviar("OBITO", "<lote/>", cns=CNS_FICTICIO, pasta=tmp_path)
    assert rede["aberturas"] == []
    assert _linhas_do_log(banco) == []


def test_http_puro_continua_recusado_antes_da_rede(rede, cofre, banco,
                                                  monkeypatch):
    monkeypatch.setattr(SC, "ENDERECO",
                        "http://sirc.dataprev.gov.br/SircWs/Movimento")
    with pytest.raises(SC.SircClienteError, match="https"):
        SC.enviar("OBITO", "<lote/>", cns=CNS_FICTICIO, pasta=cofre)
    assert rede["aberturas"] == []


# ------------------------------------------------- o log das Centrais


def test_cada_chamada_vira_linha_no_log_sem_segredo(rede, cofre, banco):
    SC.enviar("OBITO", "<lote>dado</lote>", cns=CNS_FICTICIO, pasta=cofre)
    linhas = _linhas_do_log(banco)
    assert len(linhas) == 1
    ln = linhas[0]
    assert ln["central"] == "SIRC"
    assert ln["operacao"] == "enviarMovimentoObito"
    assert ln["ambiente"] == "PRODUCAO"
    assert ln["status_http"] == 200
    assert ln["evento"] == "REQUISICAO"
    tudo = " ".join(str(v) for v in ln.values())
    for proibido in (SENHA, USUARIO, CNS_FICTICIO, "dado", "<lote"):
        assert proibido not in tudo, proibido


def test_falha_de_transporte_tambem_vai_para_o_log(rede, cofre, banco):
    rede["roteiro"].append(OSError("sem rota"))
    with pytest.raises(SC.SircClienteError):
        SC.validar("OBITO", "<lote/>", cns=CNS_FICTICIO, pasta=cofre)
    linhas = _linhas_do_log(banco)
    assert [x["evento"] for x in linhas] == ["FALHA_DE_TRANSPORTE"]
    assert linhas[0]["nivel"] == SCH.ERRO
    assert linhas[0]["operacao"] == "validarMovimentoObito"
    assert SENHA not in " ".join(str(v) for v in linhas[0].values())


def test_sem_banco_ligado_o_envio_segue(rede, cofre, monkeypatch):
    monkeypatch.setattr(LOG, "_BANCO", None)
    assert SC.enviar("OBITO", "<lote/>", cns=CNS_FICTICIO,
                     pasta=cofre) == "Recebido com sucesso"


def test_resposta_grande_chega_inteira(rede, cofre, banco):
    enchimento = "x" * (HTTP.LIMITE_DO_CORPO_NO_TEXTO + 10)
    corpo = SUCESSO.replace(b"<soap:Body>",
                            f"<soap:Header>{enchimento}</soap:Header>"
                            "<soap:Body>".encode())
    rede["roteiro"].append(_RespostaFalsa(200, corpo))
    assert SC.enviar("OBITO", "<lote/>", cns=CNS_FICTICIO,
                     pasta=cofre) == "Recebido com sucesso"


# ------------------------------------------------- sem homologação, sem fila


def test_o_sirc_so_tem_producao_e_fica_fora_da_fila(banco):
    assert CRED.ambientes_de(CRED.SIRC) == (CRED.PRODUCAO,)
    with pytest.raises(FILA.FilaError):
        PFILA.testar_pela_fila(banco, CRED.SIRC, FILA.HOMOLOGACAO)
    with pytest.raises(FILA.FilaError):
        PFILA.testar_pela_fila(banco, CRED.SIRC, CRED.PRODUCAO)
    c = banco.connect()
    try:
        assert c.execute("SELECT COUNT(*) FROM centrais_fila").fetchone()[0] == 0
    finally:
        c.close()
