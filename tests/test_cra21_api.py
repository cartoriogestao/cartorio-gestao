"""A API DA CRA — o transporte SOAP, conferido contra o WSDL dela.

**O JUIZ AQUI É O PRÓPRIO WSDL**, e não a minha lembrança. Ele está em
`FONTES_EXTERNAS/cra21/`, nos dois ambientes, e foi baixado em 02/09/2026 —
os dois estão públicos e responderam HTTP 200 sem credencial nenhuma.

O QUE ESTES TESTES GUARDAM
      - **as 21 operações e os parâmetros de cada uma**, na ORDEM do contrato:
        em `rpc/encoded` eles são posicionais, e trocá-los manda a data no
        lugar do protocolo **sem erro nenhum**;
      - **o `https` se força**, e o guarda existe porque o WSDL de homologação
        declara `http://` sem o S — com HTTP Basic, a senha do cartório
        viajaria legível;
      - **o namespace muda com o ambiente**, e com o errado a Central não
        reconhece a operação;
      - **o que escreve não se repete sozinho** quando a rede cai;
      - **consultar autorização não marca como baixada** por padrão — uma
        consulta que muda o estado do lado de lá não pode ser o comportamento
        silencioso de um botão de olhar;
      - e **não há função nomeada para o que não tem sentido medido**: oito das
        21 dependem de `userDados`, que o manual não descreve (Confirmação e
        Retorno foram medidos em homologação).
"""
from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import centrais_cred as CRED
import cra21_api as API

PASTA = RAIZ.parent.parent / "FONTES_EXTERNAS" / "cra21"
WSDL = {CRED.PRODUCAO: PASTA / "cra_ma_prod.wsdl",
        CRED.HOMOLOGACAO: PASTA / "cra_ma_homolog.wsdl"}
tem_wsdl = pytest.mark.skipif(
    not all(a.is_file() for a in WSDL.values()),
    reason="os WSDL só existem na máquina de desenvolvimento")


def _wsdl(ambiente) -> str:
    return WSDL[ambiente].read_text(encoding="utf-8", errors="replace")


def _operacoes_do_wsdl(texto: str) -> dict[str, tuple[str, ...]]:
    fora = {}
    for m in re.finditer(r'<message name="(\w+)Request">(.*?)</message>',
                         texto, re.DOTALL):
        fora[m.group(1)] = tuple(
            re.findall(r'<part name="(\w+)"', m.group(2)))
    return fora


# ------------------------------------------- o contrato manda, e não eu


@tem_wsdl
def test_as_21_operacoes_e_os_parametros_sao_os_do_wsdl():
    """**A ORDEM IMPORTA.** Em `rpc/encoded` os parâmetros são posicionais
    dentro do elemento da operação — trocar `protocolo` com `dataProtocolo`
    faria a Central responder sobre outra coisa, sem erro nenhum."""
    assert API.OPERACOES == _operacoes_do_wsdl(_wsdl(CRED.PRODUCAO))
    assert len(API.OPERACOES) == 21


@tem_wsdl
def test_os_dois_wsdl_declaram_as_MESMAS_operacoes():
    """Se a homologação divergir da produção, testar lá deixa de provar aqui."""
    assert (_operacoes_do_wsdl(_wsdl(CRED.PRODUCAO))
            == _operacoes_do_wsdl(_wsdl(CRED.HOMOLOGACAO)))


@tem_wsdl
def test_o_namespace_de_cada_ambiente_e_o_do_wsdl_dele():
    """**Com o namespace errado a Central não reconhece a operação**, e a
    recusa não diz por quê. Eles são diferentes: `crabr` e `cra21`."""
    for ambiente, arquivo in WSDL.items():
        texto = arquivo.read_text(encoding="utf-8", errors="replace")
        alvo = re.search(r'targetNamespace="([^"]+)"', texto).group(1)
        assert API.NAMESPACE_DO_AMBIENTE[ambiente] == f"urn:{alvo}"
    assert (API.NAMESPACE_DO_AMBIENTE[CRED.PRODUCAO]
            != API.NAMESPACE_DO_AMBIENTE[CRED.HOMOLOGACAO])


@tem_wsdl
def test_O_WSDL_DE_HOMOLOGACAO_DECLARA_HTTP_SEM_O_S():
    """**O achado de segurança, guardado como teste.**

    O manual diz que HTTPS é obrigatório; o WSDL de homologação declara
    `http://`. Quem montar o cliente lendo o WSDL — que é o normal — falaria em
    texto puro, e a autenticação é HTTP Basic: **a senha do cartório viajaria
    legível na rede**.

    Se algum dia eles consertarem o arquivo, este teste fica vermelho e conta
    a história — em vez de a correção passar despercebida.
    """
    endereco = re.search(r'soap:address location="([^"]+)"',
                         _wsdl(CRED.HOMOLOGACAO)).group(1)
    assert endereco.startswith("http://"), (
        "o WSDL de homologação passou a declarar https — confira o arquivo e "
        "atualize esta nota; o guarda do módulo continua valendo")
    # E o do módulo NÃO segue o arquivo: ele força.
    assert API.ENDERECO_DO_AMBIENTE[CRED.HOMOLOGACAO].startswith("https://")
    assert (re.search(r"//([^/:]+)", endereco).group(1)
            in API.ENDERECO_DO_AMBIENTE[CRED.HOMOLOGACAO]), (
        "o endereço forçado tem de apontar para o MESMO servidor do WSDL — "
        "forçar https é mudar o transporte, e não o destino")


def test_o_https_se_forca_e_a_recusa_diz_por_que():
    with pytest.raises(API.CraError) as e:
        API._partes("http://crama.cra21.com.br/crama/xml/x.php")
    assert "https" in str(e.value)
    assert "legível" in str(e.value)


# ------------------------------------------- o envelope


def test_o_envelope_poe_os_parametros_na_ordem_do_contrato():
    """Mesmo com o dicionário fora de ordem — porque em `rpc/encoded` quem
    manda é a posição, e não o nome."""
    e = API.envelope("ConsultaSlip",
                     {"dataProtocolo": "2026-09-02", "protocolo": "123"},
                     "urn:x").decode()
    assert e.index("<protocolo>") < e.index("<dataProtocolo>")


def test_o_envelope_manda_TODOS_os_parametros_ainda_que_vazios():
    """Em `rpc/encoded` o que falta desloca o que vem depois."""
    e = API.envelope("ConsultaImagem", {"nossoNumero": "1"}, "urn:x").decode()
    for nome in API.OPERACOES["ConsultaImagem"]:
        assert f"<{nome}>" in e


def test_o_envelope_escapa_o_valor():
    """Nome de arquivo com `&` não é comum; **conteúdo de arquivo é** — e um
    `&` solto quebra o XML do lado de lá."""
    e = API.envelope("Desistencia", {"userArq": "a&b<c>"}, "urn:x").decode()
    assert "a&amp;b&lt;c&gt;" in e
    assert "<userArq>a&b" not in e


def test_o_envelope_recusa_operacao_e_parametro_que_o_contrato_nao_tem():
    with pytest.raises(API.CraError) as e:
        API.envelope("NaoExiste", {}, "urn:x")
    assert "engano de programação" in str(e.value)
    with pytest.raises(API.CraError) as e:
        API.envelope("Desistencia", {"userDados": "x"}, "urn:x")
    assert "userArq" in str(e.value)


def test_o_envelope_leva_o_namespace_do_ambiente():
    p = API.envelope("BuscarApresentante", {},
                     API.namespace_do_ambiente(CRED.PRODUCAO)).decode()
    h = API.envelope("BuscarApresentante", {},
                     API.namespace_do_ambiente(CRED.HOMOLOGACAO)).decode()
    assert "crabr.com.br" in p and "cra21.com.br" in h
    assert p != h


# ------------------------------------------- ler a resposta


def test_a_falha_SOAP_vira_frase_e_nao_erro_de_rede():
    """**A falha SOAP vem com HTTP 500**, e quem olhar só o código chamaria de
    erro de rede o que é recusa da Central, com motivo escrito dentro."""
    with pytest.raises(API.CraRecusou) as e:
        API.ler_resposta(
            "<SOAP-ENV:Fault><faultstring>Login inv&#225;lido</faultstring>"
            "</SOAP-ENV:Fault>", "baixar a remessa")
    assert "Login" in str(e.value)


def test_o_return_volta_desescapado_e_nao_interpretado():
    """**Nada aqui interpreta arquivo** — o que volta vai para
    `protesto_arquivo`, que já lê os cinco layouts."""
    r = API.ler_resposta(
        '<return xsi:type="xsd:string">&lt;xml&gt;a&amp;b&lt;/xml&gt;</return>',
        "baixar")
    assert r == "<xml>a&b</xml>"


def test_o_return_desfaz_aspas_escapadas_na_remessa_xml():
    """Medido na homologação: delimitadores do XML dentro do ``<return>``."""
    r = API.ler_resposta(
        '<return>&lt;?xml version=&amp;quot;1.0&amp;quot; encoding=&amp;quot;'
        'UTF-8&amp;quot;?&gt;</return>',
        "baixar a remessa")
    assert r.startswith('<?xml version="1.0" encoding="UTF-8"?>')


def test_resposta_sem_return_nao_passa_calada():
    with pytest.raises(API.CraRecusou) as e:
        API.ler_resposta("<html>manutenção</html>", "baixar a remessa")
    assert "sem o conteúdo esperado" in str(e.value)


def test_erro_xml_dentro_do_return_vira_recusa_no_diagnostico():
    """Medido 01/10/2026: homolog real devolve auth fail no ``<return>`` (~135 chars)."""
    xml = (
        '<?xml version="1.0" encoding="ISO-8859-1" standalone="no"?>\n'
        "<erro><mensagem>Falha na autenticação.</mensagem>"
        "<codigo>1</codigo></erro>\n")
    assert len(xml) == 135
    assert API.recusa_no_return(xml) == "Falha na autenticação. (código 1)"


def test_relatorio_0002_no_return():
    xml = (
        '<?xml version="1.0" encoding="ISO-8859-1" standalone="no"?>\n'
        "<relatorio><codigo>0002</codigo>"
        "<ocorrencia>NOME DO ARQUIVO INVÁLIDO.</ocorrencia></relatorio>\n"
    )
    msg = API.recusa_no_return(xml)
    assert msg is not None
    assert "0002" in msg
    assert "Nome do arquivo inválido" in msg


def test_relatorio_0003_no_return():
    xml = (
        '<?xml version="1.0" encoding="ISO-8859-1" standalone="no"?>\n'
        "<relatorio><nome_arquivo>B0013110.221</nome_arquivo>"
        "<datahora>202610091732</datahora><codigo>0003</codigo>"
        "<ocorrencia>NÃO EXISTE REMESSA NA DATA INFORMADA.</ocorrencia>"
        "</relatorio>\n"
    )
    msg = API.recusa_no_return(xml)
    assert msg is not None
    assert "0003" in msg
    assert "Não existe remessa na data informada" in msg


# ------------------------------------------- a rede


def _finge_a_rede(monkeypatch, tmp_path, *, resposta="", estoura=False):
    import http.client as hc

    tentativas: dict[str, int] = {}

    class Resposta:
        status = 200

        def read(self):
            return resposta.encode("utf-8")

        def getheaders(self):
            # O transporte comum (marco b) le os cabecalhos, como o
            # `http.client` de verdade sempre oferece.
            return []

    class Conexao:
        def __init__(self, *a, **kw):
            pass

        def request(self, metodo, caminho, body=None, headers=None):
            operacao = re.search(rb"<ns1:(\w+)", body).group(1).decode()
            tentativas[operacao] = tentativas.get(operacao, 0) + 1
            Conexao.ultimo_cabecalho = headers
            Conexao.ultimo_corpo = body
            if estoura:
                raise OSError("rede caiu")

        def getresponse(self):
            return Resposta()

        def close(self):
            pass

    monkeypatch.setattr(hc, "HTTPSConnection", Conexao)
    CRED.gravar(CRED.CRA, usuario="cartorio", senha="segredo",
                pasta=tmp_path)
    return tentativas, Conexao


def test_operacao_que_muda_estado_remoto_nao_se_repete_sozinha(monkeypatch, tmp_path):
    """Envio e download podem ter sido aceitos mesmo após falha de rede."""
    tentativas, _ = _finge_a_rede(monkeypatch, tmp_path, estoura=True)
    with pytest.raises(API.CraError):
        API.chamar("Desistencia", CRED.HOMOLOGACAO, pasta=tmp_path,
                   userArq="DP001.txt")
    with pytest.raises(API.CraError):
        API.chamar("Confirmacao", CRED.HOMOLOGACAO, pasta=tmp_path,
                   userArq="C001.141", userDados="")
    with pytest.raises(API.CraError, match="marcou o arquivo como baixado"):
        API.chamar("RemessaPendente", CRED.HOMOLOGACAO, pasta=tmp_path,
                   userArq="", downloadImagem="2")
    assert tentativas["Desistencia"] == 1
    assert tentativas["Confirmacao"] == 1
    assert tentativas["RemessaPendente"] == 1


def test_a_credencial_vai_em_HTTP_Basic_e_nenhuma_operacao_a_recebe(
        monkeypatch, tmp_path):
    """**Nenhuma das 21 tem parâmetro de usuário** — quem identifica a
    serventia é a credencial HTTP. Conferido no WSDL e aqui no envelope."""
    _, conexao = _finge_a_rede(
        monkeypatch, tmp_path,
        resposta="<return>ok</return>")
    API.apresentantes(CRED.HOMOLOGACAO, pasta=tmp_path)
    cabecas = conexao.ultimo_cabecalho
    assert cabecas["Authorization"].startswith("Basic ")
    import base64
    assert base64.b64decode(
        cabecas["Authorization"].split()[1]).decode() == "cartorio:segredo"
    # e o SOAPAction leva o namespace do ambiente
    assert "cra21.com.br#BuscarApresentante" in cabecas["SOAPAction"]
    for parametros in API.OPERACOES.values():
        for nome in parametros:
            assert nome not in ("login", "senha", "usuario", "cartorio")


def test_sem_credencial_a_chamada_nem_sai(tmp_path):
    """A recusa é no balcão, e não na rede."""
    with pytest.raises(CRED.CredencialError) as e:
        API.apresentantes(CRED.HOMOLOGACAO, pasta=tmp_path)
    assert "não foi informada" in str(e.value)


# ------------------------------------------- o que o módulo recusa


def test_userArq_e_NOME_de_arquivo_e_nao_conteudo():
    """**Medido no manual**: «Nome do arquivo no formato FEBRABAN». Mandar o
    conteúdo seria mandar megabytes onde a Central espera onze caracteres."""
    with pytest.raises(API.CraError) as e:
        API.remessa("")
    assert "NOME do arquivo" in str(e.value)
    with pytest.raises(API.CraError) as e:
        API.remessa("0" * 600 + "\nlinha de arquivo")
    assert "e não o conteúdo" in str(e.value)


def test_consultar_autorizacao_NAO_marca_como_baixada_por_padrao(
        monkeypatch, tmp_path):
    """**Consultar marca como baixada salvo se se disser que não** — medido no
    manual. Uma consulta que muda o estado do lado de lá não pode ser o
    comportamento silencioso de um botão de olhar."""
    _, conexao = _finge_a_rede(monkeypatch, tmp_path,
                               resposta="<return>ok</return>")
    # **NAO BASTA O PADRAO DA ASSINATURA SER `False`** — o que a Central
    # recebe e o `marcarBaixado` do envelope, e e ele que este teste le.
    API.consultar_autorizacao("A.txt", "123", "2026-09-02", CRED.HOMOLOGACAO,
                              pasta=tmp_path)
    assert "<marcarBaixado>0</marcarBaixado>" in conexao.ultimo_corpo.decode()
    API.consultar_autorizacao("A.txt", "123", "2026-09-02", CRED.HOMOLOGACAO,
                              marcar_baixado=True, pasta=tmp_path)
    assert "<marcarBaixado>1</marcarBaixado>" in conexao.ultimo_corpo.decode()


def test_chamar_recusa_operacao_que_nao_existe():
    with pytest.raises(API.CraError) as e:
        API.chamar("Inventada")
    assert "BuscarApresentante" in str(e.value)   # a frase lista as que há


def test_nao_ha_funcao_nomeada_para_o_que_nao_tem_sentido_medido():
    """**Oito das 21 dependem de `userDados` sem medição na homologação.**
    Escrever dez funções nomeadas com um conteúdo suposto seria pôr no código
    uma hipótese com cara de contrato — e este projeto já pagou caro por isso
    (o `{"dadosSelo": …}` que impedia a casa inteira de selar).

    Elas continuam alcançáveis por `chamar()`, que confere os NOMES contra o
    WSDL e manda o que lhe derem.
    """
    nomeadas = {n for n, o in vars(API).items()
                if inspect.isfunction(o) and o.__module__ == API.__name__
                and not n.startswith("_")}
    # o que cada função nomeada chama, lido da fonte
    fonte = (RAIZ / "cra21_api.py").read_text(encoding="utf-8")
    for operacao in API.OPERACOES_SEM_SENTIDO_MEDIDO:
        assert f'chamar("{operacao}"' not in fonte, (
            f"há função nomeada chamando «{operacao}», cujo `userDados` não "
            f"está medido")
    assert "apresentantes" in nomeadas       # a que não tem parâmetro nenhum
    assert "diagnostico" in nomeadas
    assert "enviar_confirmacao" in nomeadas
    assert "enviar_retorno" in nomeadas


def test_toda_operacao_sem_sentido_medido_existe_no_contrato():
    """Lista escrita à mão que cite operação inexistente é a promessa com cara
    de prova."""
    assert API.OPERACOES_SEM_SENTIDO_MEDIDO <= set(API.OPERACOES)
    assert API.OPERACOES_QUE_ESCREVEM <= set(API.OPERACOES)


# ------------------------------------------- as regras da casa


def test_nenhuma_funcao_recebe_con():
    """Chamada de rede não entra em transação — a regra desde o selador."""
    for nome, obj in vars(API).items():
        if not inspect.isfunction(obj) or obj.__module__ != API.__name__:
            continue
        assert "con" not in set(inspect.signature(obj).parameters), (
            f"`{nome}` recebe `con`")


def test_o_modulo_nao_tem_funcao_que_lavre_ato():
    """A CRA não lavra ato nesta casa — quem aponta e protesta é o domínio."""
    for nome in vars(API):
        if nome.startswith("_"):
            continue
        for palavra in ("lavrar", "protestar", "apontar", "numerar", "selar",
                        "averbar", "cobrar"):
            assert palavra not in nome.lower(), f"`{nome}` tem cara de ato"


def test_o_diagnostico_usa_a_operacao_QUE_NAO_MARCA_NADA(tmp_path):
    """**`BuscarApresentante` é a única sem parâmetro nenhum**, e por isso a
    única que testa conexão e credencial sem afirmar nada sobre arquivo. Um
    teste que pedisse uma remessa marcaria a remessa como baixada lá."""
    assert API.OPERACOES["BuscarApresentante"] == ()
    fonte = inspect.getsource(API.diagnostico)
    assert "apresentantes(" in fonte
    d = API.diagnostico(CRED.HOMOLOGACAO, pasta=tmp_path)
    assert d["ok"] is False
    assert "não foi informada" in d["motivo"]


def test_a_homologacao_e_o_padrao():
    """Onde se começa — e o engano cai para o lado seguro."""
    assert API.endereco_do_ambiente(None) == (
        API.ENDERECO_DO_AMBIENTE[CRED.HOMOLOGACAO])
    assert API.namespace_do_ambiente("sei la") == (
        API.NAMESPACE_DO_AMBIENTE[CRED.HOMOLOGACAO])
