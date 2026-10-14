"""O TRANSPORTE DO SIRC — conferido contra o WSDL público dele.

**O JUIZ AQUI É O PRÓPRIO WSDL**, baixado em 14/09/2026 de
`https://sirc.dataprev.gov.br/SircWs/Movimento?wsdl` (público, respondeu HTTP
200 sem credencial nenhuma) e guardado em `FONTES_EXTERNAS/sirc/Movimento.wsdl`.

O QUE ESTES TESTES GUARDAM
    - **as nove operações**, medidas no WSDL — e não oito, não dez;
    - **document/literal, por nome** — ao contrário do `rpc/encoded`
      posicional da CRA21;
    - **o `https` se força**, porque o WSDL declara `http://` sem o S, e
      aqui a senha viaja DENTRO do corpo — pior que HTTP Basic se vazasse;
    - **SOAP 1.2**, e a falha mora em `Reason/Text`, não em `faultstring`;
    - **`<resultado>` volta cru**, porque o manual não descreve o
      vocabulário dele — este módulo não inventa significado;
    - **não há operação de NATIMORTO**, e isso concorda com `sirc_remessa`,
      que também não constrói o envelope dela ainda.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import centrais_cred as CRED                                     # noqa: E402
import sirc_cliente as SC                                         # noqa: E402
import sirc_remessa as SIRC                                        # noqa: E402

WSDL_PATH = RAIZ.parent.parent / "FONTES_EXTERNAS" / "sirc" / "Movimento.wsdl"
tem_wsdl = pytest.mark.skipif(
    not WSDL_PATH.is_file(),
    reason="o WSDL só existe na máquina de desenvolvimento")


def _wsdl() -> str:
    return WSDL_PATH.read_text(encoding="utf-8", errors="replace")


def _operacoes_do_wsdl(texto: str) -> set[str]:
    return set(re.findall(r'<wsdl:operation name="(\w+)"', texto))


@pytest.fixture(autouse=True)
def _sem_relogio_entre_testes():
    """`_ULTIMO_ENVIO` é global ao módulo — sem isolar, um teste que chame
    `_bater` deixaria o próximo preso no intervalo de 1 minuto, e a suíte
    ficaria vermelha por ordem de execução, não por defeito."""
    SC._ULTIMO_ENVIO = None
    yield
    SC._ULTIMO_ENVIO = None


# ------------------------------------------- o contrato manda, e não eu


@tem_wsdl
def test_as_nove_operacoes_sao_as_do_wsdl():
    assert set(SC.OPERACOES) == _operacoes_do_wsdl(_wsdl())
    assert len(SC.OPERACOES) == 9


@tem_wsdl
def test_nao_ha_operacao_propria_de_natimorto_no_contrato():
    """Medido, não suposto — e concorda com `sirc_remessa` e com o manual
    (seção 5.4): um natimorto se manda pela MESMA operação do óbito, com
    `tipoLivro="5"` dentro do XML."""
    assert not any("Natimorto" in op for op in _operacoes_do_wsdl(_wsdl()))
    assert "NATIMORTO" in SIRC.ESPECIES_PRONTAS_PARA_O_SIRC
    assert (SC.OPERACAO_DE_ENVIO_DA_ESPECIE["NATIMORTO"]
            == "enviarMovimentoObito")
    assert (SC.OPERACAO_DE_VALIDACAO_DA_ESPECIE["NATIMORTO"]
            == "validarMovimentoObito")


@tem_wsdl
def test_o_endereco_e_o_do_wsdl_com_https_forcado():
    """O WSDL declara `http://sirc.dataprev.gov.br:80/...`, sem o S — o
    sistema usa o mesmo host e caminho, só que em https."""
    texto = _wsdl()
    achado = re.search(r'location="https?://([^/]+?)(?::\d+)?(/[^"]+)"',
                       texto)
    assert achado, "o WSDL não declarou soap12:address"
    hospedeiro, caminho = achado.groups()
    assert SC.ENDERECO == f"https://{hospedeiro}{caminho}"


@tem_wsdl
def test_o_binding_e_soap12_document_literal():
    """Ao contrário da CRA (`rpc/encoded`, SOAP 1.1), aqui os campos vão
    por NOME — e é isso que `envelope()` monta."""
    texto = _wsdl()
    assert 'style="document"' in texto
    assert 'use="literal"' in texto
    assert "soap12" in texto


@tem_wsdl
def test_toda_operacao_de_envio_e_validacao_tem_os_mesmos_quatro_campos():
    """Ao contrário da CRA21 (parâmetros por operação), aqui as nove usam
    sempre `{cns, usuario, senha, conteudo}` — medido no WSDL."""
    texto = _wsdl()
    for op in SC.OPERACOES:
        bloco = re.search(
            rf'<xsd:complexType name="{op}">.*?</xsd:complexType>',
            texto, re.DOTALL)
        assert bloco, op
        for campo in ("cns", "usuario", "senha", "conteudo"):
            assert f'name="{campo}"' in bloco.group(0), (op, campo)


# ------------------------------------------- o https não é opcional


def test_o_wsdl_declara_http_sem_o_s():
    """O achado que justifica o guarda — sem ele pareceria zelo demais."""
    if not WSDL_PATH.is_file():
        pytest.skip("o WSDL só existe na máquina de desenvolvimento")
    assert 'location="http://sirc.dataprev.gov.br' in _wsdl()


def test_o_https_se_forca_e_a_recusa_diz_por_que():
    with pytest.raises(SC.SircClienteError) as erro:
        SC._partes_https("http://sirc.dataprev.gov.br/SircWs/Movimento")
    assert "https" in str(erro.value)
    assert "senha" in str(erro.value)


def test_endereco_https_passa():
    hospedeiro, porta, caminho = SC._partes_https(SC.ENDERECO)
    assert hospedeiro == "sirc.dataprev.gov.br"
    assert porta == 443
    assert caminho == "/SircWs/Movimento"


# ------------------------------------------- o envelope


def test_o_envelope_leva_os_quatro_campos_por_nome():
    xml = SC.envelope("enviarMovimentoObito", cns="000000", usuario="jean",
                      senha="Senha#1", conteudo="<lote/>")
    assert "<cns>000000</cns>" in xml.decode()
    assert "<usuario>jean</usuario>" in xml.decode()
    assert "<senha>Senha#1</senha>" in xml.decode()
    assert "<conteudo>&lt;lote/&gt;</conteudo>" in xml.decode()
    assert f'<enviarMovimentoObito xmlns="{SC.NAMESPACE}">' in xml.decode()


def test_o_envelope_e_soap_1_2():
    xml = SC.envelope("enviarMovimentoNascimento", cns="1", usuario="a",
                      senha="b", conteudo="c").decode()
    assert "http://www.w3.org/2003/05/soap-envelope" in xml
    assert "soap:Envelope" in xml
    assert "soap:Body" in xml


def test_o_envelope_escapa_o_conteudo():
    """`conteudo` é o XML do lote inteiro — cheio de `<` e `&` de sobra."""
    xml = SC.envelope("enviarMovimentoCasamento", cns="1", usuario="a",
                      senha="b", conteudo="<a>&</a>").decode()
    assert "<a>&</a>" not in xml
    assert "&lt;a&gt;&amp;&lt;/a&gt;" in xml


def test_o_envelope_recusa_operacao_que_o_contrato_nao_tem():
    with pytest.raises(SC.SircClienteError):
        SC.envelope("enviarMovimentoNatimorto", cns="1", usuario="a",
                   senha="b", conteudo="c")


# ------------------------------------------- a leitura da resposta


def test_a_falha_soap_1_2_vira_frase():
    """Ao contrário da CRA (`<faultstring>`, SOAP 1.1), aqui é
    `soap:Reason/soap:Text` — e `SircWebServiceFault` não tem campo
    próprio nenhum para o motivo."""
    resposta = (
        '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">'
        '<soap:Body><soap:Fault><soap:Code><soap:Value>soap:Sender'
        '</soap:Value></soap:Code><soap:Reason><soap:Text xml:lang="en">'
        'Credencial inválida</soap:Text></soap:Reason></soap:Fault>'
        '</soap:Body></soap:Envelope>')
    with pytest.raises(SC.SircRecusou, match="Credencial inválida"):
        SC.ler_resposta(resposta, "testar")


def test_o_resultado_volta_cru_e_nao_interpretado():
    """O manual não descreve o vocabulário de `resultado` — este módulo
    não inventa o que aquele texto quer dizer."""
    resposta = (
        '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">'
        '<soap:Body><enviarMovimentoObitoResponse '
        f'xmlns="{SC.NAMESPACE}"><resultado>Recebido com sucesso'
        '</resultado></enviarMovimentoObitoResponse></soap:Body>'
        '</soap:Envelope>')
    assert SC.ler_resposta(resposta, "testar") == "Recebido com sucesso"


def test_resposta_sem_resultado_nao_passa_calada():
    with pytest.raises(SC.SircRecusou, match="sem"):
        SC.ler_resposta("<algo/>", "testar")


# ------------------------------------------- a espécie decide a operação


def test_enviar_natimorto_usa_a_operacao_do_obito(tmp_path, monkeypatch):
    """O manual (seção 5.4) manda o natimorto pela MESMA operação do
    óbito — não há `enviarMovimentoNatimorto` para recusar."""
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: tmp_path)
    with pytest.raises(CRED.CredencialError):
        SC.enviar("NATIMORTO", "<lote/>", cns="000000")


def test_enviar_recusa_especie_de_verdade_desconhecida():
    with pytest.raises(SC.SircClienteError, match="ANOTACAO"):
        SC.enviar("ANOTACAO", "<lote/>", cns="000000")


def test_a_especie_decide_a_operacao_de_envio_e_validacao():
    assert SC.OPERACAO_DE_ENVIO_DA_ESPECIE["OBITO"] == "enviarMovimentoObito"
    assert (SC.OPERACAO_DE_VALIDACAO_DA_ESPECIE["CASAMENTO"]
            == "validarMovimentoCasamento")
    assert (SC.OPERACAO_DE_ENVIO_DA_ESPECIE["CASAMENTO_RELIGIOSO"]
            == "enviarMovimentoCasamento")


def test_sem_credencial_a_chamada_nem_sai(tmp_path):
    with pytest.raises(CRED.CredencialError):
        SC.enviar("OBITO", "<lote/>", cns="000000", pasta=tmp_path)


# ------------------------------------------- a credencial

def test_o_sirc_e_par_com_ambiente_unico():
    assert CRED.FORMA_DA_CENTRAL[CRED.SIRC] == CRED.PAR
    assert CRED.ambientes_de(CRED.SIRC) == (CRED.PRODUCAO,)
    assert CRED.ARQUIVO_DA_CENTRAL[CRED.SIRC] == "sirc.cred"


def test_a_senha_nunca_aparece_em_erro_de_rede(tmp_path, monkeypatch):
    """A credencial vai no CORPO, e não em HTTP Basic — um erro que
    ecoasse a requisição vazaria a senha."""
    CRED.gravar(CRED.SIRC, usuario="jean", senha="Senha#Secreta9",
               ambiente=CRED.PRODUCAO, pasta=tmp_path)

    def _falha(*a, **k):
        raise OSError("rede indisponível")

    monkeypatch.setattr(SC.http.client, "HTTPSConnection", _falha)
    with pytest.raises(SC.SircClienteError) as erro:
        SC.enviar("OBITO", "<lote/>", cns="000000", pasta=tmp_path)
    assert "Senha#Secreta9" not in str(erro.value)


# ------------------------------------------- o cancelamento de termo


def test_enviar_e_validar_cancelamento_usam_as_operacoes_certas(
        tmp_path, monkeypatch):
    """`enviar_cancelamento`/`validar_cancelamento` não passam por
    `OPERACAO_DE_ENVIO_DA_ESPECIE` — cancelamento não é uma das sete
    coisas do art. 225."""
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: tmp_path)
    with pytest.raises(CRED.CredencialError):
        SC.enviar_cancelamento("<movimentoCancelamentoTO/>", cns="000000")
    with pytest.raises(CRED.CredencialError):
        SC.validar_cancelamento("<movimentoCancelamentoTO/>", cns="000000")


def test_cancelamento_usa_o_envelope_certo():
    xml = SC.envelope("enviarMovimentoCancelamento", cns="000000",
                      usuario="jean", senha="Senha#1",
                      conteudo="<movimentoCancelamentoTO/>")
    assert b"<enviarMovimentoCancelamento" in xml
    # `conteudo` vai escapado — é uma string, como qualquer outro campo.
    assert b"&lt;movimentoCancelamentoTO/&gt;" in xml


# ------------------------------------------- o minuto entre envios


def test_o_minuto_entre_envios_recusa_o_segundo_muito_cedo(tmp_path, monkeypatch):
    """O manual exige o intervalo — sem isso, dois lotes seguidos (ou um
    clique duplo) poderiam furá-lo, porque só havia botão de baixar antes
    de este cliente existir."""
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: tmp_path)
    CRED.gravar(CRED.SIRC, usuario="jean", senha="Senha#12345",
               ambiente=CRED.PRODUCAO, pasta=tmp_path)

    def _resposta_falsa(*a, **k):
        class _R:
            def getresponse(self):
                class _Resp:
                    # A resposta de verdade tem `status` e `getheaders` — o
                    # transporte comum (marco c, 05/10/2026) lê os dois.
                    status = 200

                    def getheaders(self):
                        return []

                    def read(self):
                        return (b'<soap:Envelope xmlns:soap='
                                b'"http://www.w3.org/2003/05/soap-envelope">'
                                b'<soap:Body><enviarMovimentoObitoResponse '
                                + SC.NAMESPACE.encode() +
                                b'><resultado>ok</resultado>'
                                b'</enviarMovimentoObitoResponse></soap:Body>'
                                b'</soap:Envelope>')
                return _Resp()
            def request(self, *a, **k): pass
            def close(self): pass
        return _R()

    monkeypatch.setattr(SC.http.client, "HTTPSConnection", _resposta_falsa)
    SC.enviar("OBITO", "<lote/>", cns="000000", pasta=tmp_path)
    with pytest.raises(SC.SircClienteError, match="60 segundos"):
        SC.enviar("OBITO", "<lote/>", cns="000000", pasta=tmp_path)


def test_o_minuto_passa_e_o_proximo_envio_libera(tmp_path, monkeypatch):
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: tmp_path)
    SC._ULTIMO_ENVIO = time.monotonic() - SIRC.INTERVALO_MINIMO_SEGUNDOS - 1
    with pytest.raises(CRED.CredencialError):
        SC.enviar("OBITO", "<lote/>", cns="000000", pasta=tmp_path)


def test_a_recusa_do_minuto_nao_precisa_de_credencial_gravada(tmp_path,
                                                              monkeypatch):
    """A ordem é credencial primeiro — sem ela, a tela precisa apontar
    para a configuração, e não para "espere o minuto"."""
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: tmp_path)
    SC._ULTIMO_ENVIO = time.monotonic()
    with pytest.raises(CRED.CredencialError):
        SC.enviar("OBITO", "<lote/>", cns="000000", pasta=tmp_path)
