"""A API DA CENPROT — o transporte, conferido contra o contrato dela.

Ordem do oficial em 02/09/2026: *«vamos integrar a api da cra21»*, e no mesmo
dia a errata com a API da CENPROT.

**OS TESTES QUE MAIS VALEM AQUI SÃO OS QUE ABREM O `swagger.yaml`.** Eu escrevi
este módulo e, nas duas releituras, ele me pareceu certo. Foram eles que
acharam os quatro defeitos:

    · **inventei os nomes dos parâmetros** — `pagina`, `dt_inicio`, `nm_chave` —
      e a mesma API usa **três convenções de data e duas de paginação**;
    · `/v2/certidao/processar` declara **três** campos obrigatórios e eu
      conferia **um** — e o que faltava era `vl_orcamento`, que é dinheiro;
    · `/v2/anuencia/processar` exige os «dados do protocolo e devedor», doze
      campos no gêmeo legado, e eu conferia **dois**;
    · `/renegociacoes` filtra por período como as anuências, e eu mandava só a
      página.

Os quatro falhariam **calados**: parâmetro que a Central não conhece ela
ignora, e campo que falta ela devolve num 500 que não diz qual. A tela pediria
«só as de setembro» e receberia o período inteiro, sem erro em lugar nenhum.

**Por isso o guarda não é uma lista escrita à mão: ele abre o contrato e
compara.** Lista escrita à mão noutro arquivo envelhece na tarde em que se
escreve — e aqui o arquivo seria o do teste que deveria guardar a regra.
"""
from __future__ import annotations

import inspect
import re
import sys
import urllib.parse
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import cenprot_api as API
import centrais_cred as CRED

# O CONTRATO SALVO. Ele mora em `FONTES_EXTERNAS/`, que **não viaja no pacote**
# — é material de desenvolvimento, como a doutrina. Na máquina do balcão estes
# testes pulam, e é o certo: lá não há contrato para conferir.
CONTRATO = (RAIZ.parent.parent / "FONTES_EXTERNAS" / "cra21"
            / "cenprot_swagger_v2.1.0.yaml")
tem_contrato = pytest.mark.skipif(
    not CONTRATO.is_file(),
    reason="o swagger.yaml só existe na máquina de desenvolvimento")


def _spec() -> str:
    return CONTRATO.read_text(encoding="utf-8", errors="replace")


def _trecho_da_rota(rota: str) -> str:
    """O pedaço do contrato que descreve aquela rota, e só ele."""
    y = _spec()
    corpo = y[re.search(r"^paths:$", y, re.MULTILINE).end():]
    rotas = [(m.group(1), m.start())
             for m in re.finditer(r"^  (/\S+):\s*$", corpo, re.MULTILINE)]
    for i, (nome, pos) in enumerate(rotas):
        if nome == rota:
            fim = rotas[i + 1][1] if i + 1 < len(rotas) else len(corpo)
            return corpo[pos:fim]
    raise AssertionError(f"a rota {rota} não está no contrato")


# **`in:` VEM SEMPRE NA LINHA SEGUINTE AO `- name:`** — conferido, 37 de 37.
# Por isso o padrão é apertado: um padrão frouxo (`(?:\s+.*\n)*?`) atravessaria
# um parâmetro `in: path` e o contaria como de query.
def _query_do_contrato(rota: str) -> set[str]:
    return set(re.findall(r"- name: (\S+)\n\s+in: query",
                          _trecho_da_rota(rota)))


def _query_obrigatoria(rota: str) -> set[str]:
    return set(re.findall(r"- name: (\S+)\n\s+in: query\n\s+required: true",
                          _trecho_da_rota(rota)))


def _corpo_obrigatorio(rota: str) -> set[str]:
    """Os campos que o schema do corpo declara em `required:`.

    Cuidado com o `required: true` do `requestBody`, que é outra coisa: aquele
    diz «o corpo é obrigatório», e não «este campo é». Por isso o padrão exige
    a LISTA, e não o valor.
    """
    t = _trecho_da_rota(rota)
    m = re.search(r"\n(\s+)required:\s*\n((?:\1\s*- \S+\n)+)", t)
    return set(re.findall(r"- (\S+)", m.group(2))) if m else set()


# ------------------------------------------- o contrato manda, e não eu


@tem_contrato
def test_todo_caminho_do_modulo_existe_no_contrato():
    """Caminho escrito à mão envelhece na tarde em que se escreve."""
    y = _spec()
    for chave, caminho in API.CAMINHO.items():
        procurar = caminho.split("{")[0].rstrip("/")   # o de decisão tem `{}`
        assert f"\n  {procurar}" in y, (
            f"«{chave}» aponta para {caminho}, que não está no swagger.yaml")


@tem_contrato
@pytest.mark.parametrize("rota,esperados", [
    ("/v2/anuencias", {"data_inicio", "data_fim", "pagina"}),
    ("/v2/certidoes", {"data_inicio", "data_fim", "pagina"}),
    # `/renegociacoes` fica na CONFERENCIA do contrato mesmo sem funcao no
    # modulo: ela foi APAGADA porque nenhuma tela a chamava, e saber que o
    # caminho existe — e com que nomes — e o que impede alguem de o reinventar.
    ("/renegociacoes", {"data_inicio", "data_fim", "pagina"}),
    ("/cancelamento/pedidos", {"dt_inicio", "dt_fim"}),
    ("/anuencia/arquivos", {"cd_anuencia"}),
    ("/decisao-judicial/pendentes",
     {"nm_chave", "dt_ocorrencia_de", "dt_ocorrencia_ate", "page", "per_page"}),
])
def test_as_tres_convencoes_de_nome_sao_as_do_contrato(rota, esperados):
    """**A MESMA API USA TRÊS CONVENÇÕES DE DATA E DUAS DE PAGINAÇÃO**, e eu
    escrevi as três iguais na primeira versão. Este é o teste que me pegou."""
    assert _query_do_contrato(rota) == esperados


def test_lista_vazia_volta_404_e_isso_nao_e_erro(monkeypatch):
    """Medido na produção em 13/10/2026: certidões, cancelamentos e
    renegociações sem nada pendente voltam 404 — o contrato chama esse 404 de
    «Nenhuma … encontrada». O balcão deve ver lista vazia, e não recusa."""
    monkeypatch.setattr(API, "_bater", lambda *a, **k: {
        "status": 404, "json": None, "texto": ""})
    assert API.certidoes(pagina=1) == []
    assert API.renegociacoes(pagina=1) == []
    assert API.pedidos_de_cancelamento(inicio="2026-09-01", fim="2026-09-30") == []
    assert API.anuencias(inicio="2026-09-01", fim="2026-09-30") == []
    assert API.decisoes_judiciais(pagina=1) == []
    assert API.pedidos_de_protesto(data="2026-10-13") == []
    # Pedir UM item que não existe continua sendo «não encontrado».
    with pytest.raises(API.CenprotRecusou):
        API.arquivos_da_anuencia(1234)


def test_as_anuencias_exigem_as_duas_datas_antes_da_rede(monkeypatch):
    """A produção responde 422 sem `data_inicio` e `data_fim` (13/10/2026),
    embora o contrato as chame de opcionais."""
    monkeypatch.setattr(API, "_bater", lambda *a, **k: pytest.fail("foi à rede"))
    for inicio, fim in (("", ""), ("2026-09-01", ""), ("", "2026-09-30")):
        with pytest.raises(API.CenprotError, match="duas datas"):
            API.anuencias(inicio=inicio, fim=fim)


@tem_contrato
def test_o_modulo_manda_exatamente_os_nomes_do_contrato(monkeypatch):
    """Não basta o contrato dizer: o módulo tem de mandar aqueles nomes.

    Aqui não há rede — a batida é trocada por uma que anota o caminho pedido.
    """
    pedidos: list[str] = []

    def espiar(ambiente, metodo, caminho, **kw):
        pedidos.append(caminho)
        return {"status": 200, "json": [], "texto": "[]"}

    monkeypatch.setattr(API, "_bater", espiar)
    API.anuencias(pagina=2, inicio="2026-09-01", fim="2026-09-30")
    API.certidoes(pagina=1, inicio="2026-09-01", fim="2026-09-30")
    API.pedidos_de_cancelamento(inicio="2026-09-01", fim="2026-09-30")
    API.decisoes_judiciais(pagina=1, por_pagina=50, de="2026-09-01")
    API.arquivos_da_anuencia(1234)

    juntos = " ".join(pedidos)
    for esperado in ("data_inicio=2026-09-01", "data_fim=2026-09-30",
                     "pagina=2",
                     "dt_inicio=2026-09-01", "dt_fim=2026-09-30",
                     "page=1", "per_page=50", "dt_ocorrencia_de=2026-09-01",
                     "cd_anuencia=1234"):
        assert esperado in juntos, f"o módulo não mandou «{esperado}»"

    # E O QUE NÃO PODE APARECER: os nomes que eu tinha inventado, cada um na
    # rota errada. Sem estas quatro linhas o teste de cima passaria com o
    # defeito de pé, porque ele só olha o que ESTÁ na lista.
    de_cancelamento = next(c for c in pedidos if "cancelamento" in c)
    assert "pagina" not in de_cancelamento
    de_anuencia = next(c for c in pedidos if c.startswith("/v2/anuencias"))
    assert "dt_inicio" not in de_anuencia
    de_decisao = next(c for c in pedidos if "decisao" in c)
    assert "pagina=" not in de_decisao
    de_arquivos = next(c for c in pedidos if "arquivos" in c)
    assert "nm_chave" not in de_arquivos


# ---------------------------------- o que a Central exige, medido no contrato


@tem_contrato
def test_a_lista_de_campos_da_anuencia_e_a_do_contrato():
    """**Eu conferia dois de doze**, e a lista agora está amarrada ao contrato.

    A prova vem de duas fontes do mesmo arquivo, porque o schema do `v2` traz
    as propriedades e **não** declara quais são obrigatórias: a descrição dele
    nomeia «cd_anuencia, ic_aprovado e os dados do protocolo e devedor», e o
    gêmeo legado `/anuencia/processar` marca `required: true` em doze.
    """
    do_modulo = {c for c, _ in API.CAMPOS_OBRIGATORIOS_DA_ANUENCIA}
    # `ic_aprovado` é conferido à parte, porque `False` é resposta e não falta.
    assert do_modulo | {"ic_aprovado"} == _query_obrigatoria("/anuencia/processar")


@tem_contrato
def test_a_certidao_exige_o_que_o_contrato_declara_menos_o_que_ele_contradiz():
    """São **três** no `required`, e o módulo cobra **dois** — de propósito.

    `arquivo_certidao` está na lista formal E a descrição, duas linhas acima,
    o condiciona ao status «aguardando certidão». Exigi-lo sempre travaria o
    ORÇAMENTO, que é o primeiro passo e no qual a certidão ainda não existe.
    **Item declarado é diferente de item esquecido**, e este está declarado.
    """
    assert _corpo_obrigatorio("/v2/certidao/processar") == {
        "cd_pedido", "vl_orcamento", "arquivo_certidao"}
    fonte = inspect.getsource(API.processar_certidao)
    assert "cd_pedido" in fonte and "vl_orcamento" in fonte
    assert "aguardando certidão" in fonte, (
        "a razão de não exigir o arquivo tem de estar escrita onde ela vale")


@tem_contrato
def test_o_cancelamento_so_exige_o_codigo_do_pedido():
    """E a certidão dele é opcional — conferido, para não exigir a mais."""
    assert _corpo_obrigatorio("/cancelamento/cancelar-protesto") == {"cd_pedido"}


# ------------------------------------------- o que escreve na Central


def test_todo_caminho_que_escreve_esta_declarado():
    """A lista existe para o teste de baixo poder varrer."""
    for chave in API.CAMINHOS_QUE_ESCREVEM:
        assert chave in API.CAMINHO, f"«{chave}» não é um caminho conhecido"


def test_escrever_recusa_caminho_nao_declarado():
    """Engano de programação, e a frase diz isso — não é erro do balcão."""
    with pytest.raises(API.CenprotError) as e:
        API._escrever(CRED.HOMOLOGACAO, "anuencias", [], "testar")
    assert "engano de programação" in str(e.value)


def test_o_post_nao_se_repete_sozinho(monkeypatch):
    """**Aprovar a mesma anuência duas vezes é um ato a mais na Central que
    ninguém pediu.** O GET pode repetir; o POST, não."""
    import http.client as hc

    tentativas = {"GET": 0, "POST": 0}

    class Conexao:
        def __init__(self, *a, **kw):
            pass

        def request(self, metodo, caminho, body=None, headers=None):
            tentativas[metodo] += 1
            raise OSError("rede caiu")

        def close(self):
            pass

    monkeypatch.setattr(hc, "HTTPSConnection", Conexao)
    monkeypatch.setattr(API, "token", lambda *a, **kw: "fingido")
    monkeypatch.setattr(API.time, "sleep", lambda s: None)
    with pytest.raises(API.CenprotError):
        API._bater(CRED.HOMOLOGACAO, "GET", "/x")
    with pytest.raises(API.CenprotError):
        API._bater(CRED.HOMOLOGACAO, "POST", "/y", corpo=b"{}")
    assert tentativas["GET"] > 1, "o GET pode tentar de novo"
    assert tentativas["POST"] == 1, "o POST NÃO pode tentar de novo"


def test_a_falha_de_rede_diz_que_nada_foi_enviado(monkeypatch):
    """Quem está no balcão precisa saber se o ato saiu ou não."""
    import http.client as hc

    class Conexao:
        def __init__(self, *a, **kw):
            pass

        def request(self, *a, **kw):
            raise OSError("sem rede")

        def close(self):
            pass

    monkeypatch.setattr(hc, "HTTPSConnection", Conexao)
    monkeypatch.setattr(API, "token", lambda *a, **kw: "fingido")
    with pytest.raises(API.CenprotError) as e:
        API._bater(CRED.HOMOLOGACAO, "POST", "/y", corpo=b"{}")
    assert "nada foi enviado" in str(e.value)


# ------------------------------------------- a recusa no balcão, e não lá


def _anuencia(**mudar) -> dict:
    """Uma anuência completa, como a Central a devolve. Os testes mexem numa
    coisa de cada vez — assim a recusa que aparece é a que se está provando.

    Passar `campo=...` (as reticências) TIRA o campo; passar `None` o deixa
    presente e vazio, que é coisa diferente.
    """
    d = {
        "cd_anuencia": 1,
        "nm_chave": "21987650141243301260417",
        "nm_nr_protocolo": "2604170001",
        "dt_protocolo": "2026-04-17",
        "nm_nr_titulo": "00123",
        "dt_emissao": "2026-03-01",
        "vl_protesto": 200.95,
        "nm_devedor": "FULANO DA SILVA",
        "nm_nr_documento_devedor": "00000000000",
        "nm_nr_documento_credor": "00000010000127",
        "dt_solicitacao_anuencia": "2026-04-20",
        "ic_aprovado": True,
        "vl_custas": 82.64,
    }
    d.update(mudar)
    return {k: v for k, v in d.items() if v is not ...}


def test_a_anuencia_completa_passa_pela_conferencia(monkeypatch):
    """**O guarda tem de deixar passar o caso bom**, senão ele só atrapalha."""
    monkeypatch.setattr(API, "_bater", lambda *a, **kw: {
        "status": 200, "json": {"message": "ok"}, "texto": ""})
    assert API.processar_anuencia([_anuencia()]) == {"message": "ok"}


@pytest.mark.parametrize("campo", [c for c, _ in
                                   API.CAMPOS_OBRIGATORIOS_DA_ANUENCIA])
def test_falta_de_qualquer_campo_obrigatorio_para_no_balcao(campo):
    """A Central responde 500 sem dizer qual item faltou; esta recusa diz —
    **com o nome do campo E com o rótulo em português**, porque quem lê está
    no balcão."""
    with pytest.raises(API.CenprotError) as e:
        API.processar_anuencia([_anuencia(**{campo: ...})])
    assert campo in str(e.value)
    assert "anuência 1" in str(e.value)


def test_a_anuencia_aprovada_exige_o_valor():
    """Aprovar sem dizer quanto custou é o orçamento que ninguém deu."""
    with pytest.raises(API.CenprotError) as e:
        API.processar_anuencia([_anuencia(vl_custas=...)])
    assert "custas" in str(e.value)


def test_a_anuencia_recusada_exige_o_motivo():
    """Quem lê o motivo é quem pediu a anuência."""
    with pytest.raises(API.CenprotError) as e:
        API.processar_anuencia([_anuencia(ic_aprovado=False, vl_custas=...)])
    assert "motivo" in str(e.value)


def test_a_anuencia_sem_decisao_nao_e_a_mesma_coisa_que_recusada():
    """`None` é «ninguém decidiu» e `False` é «o oficial recusou». Tratá-los
    como a mesma coisa mandaria à Central uma recusa que ninguém assinou."""
    with pytest.raises(API.CenprotError) as e:
        API.processar_anuencia([_anuencia(ic_aprovado=None)])
    assert "aprovada ou recusada" in str(e.value)


def test_custas_ZERO_e_anuencia_gratuita_e_nao_campo_em_branco(monkeypatch):
    """**`str(v or "")` COME O ZERO**, e este projeto já pagou duas vezes por
    isso — o `or` que religou a fonte desligada, e o zero da declaração de mês
    vazio do SIRC. Aqui custaria caro: **esta casa lavra ato gratuito**, e o
    valor que ele teria é o que a serventia compensa junto ao fundo."""
    monkeypatch.setattr(API, "_bater", lambda *a, **kw: {
        "status": 200, "json": {"message": "ok"}, "texto": ""})
    API.processar_anuencia([_anuencia(vl_custas=0)])      # não pode estourar
    assert API._falta({"vl_custas": 0}, "vl_custas") is False
    assert API._falta({"vl_custas": None}, "vl_custas") is True
    assert API._falta({}, "vl_custas") is True
    assert API._falta({"motivo_recusa": "   "}, "motivo_recusa") is True


def test_o_pedido_de_certidao_exige_o_numero_e_o_ORCAMENTO():
    """O segundo é dinheiro, e eu não o conferia."""
    with pytest.raises(API.CenprotError) as e:
        API.processar_certidao([{"vl_orcamento": 150.75}])
    assert "cd_pedido" in str(e.value)
    with pytest.raises(API.CenprotError) as e:
        API.processar_certidao([{"cd_pedido": 123}])
    assert "vl_orcamento" in str(e.value)


def test_a_certidao_completa_passa(monkeypatch):
    """E com orçamento ZERO também — certidão gratuita existe."""
    monkeypatch.setattr(API, "_bater", lambda *a, **kw: {
        "status": 200, "json": {"message": "ok"}, "texto": ""})
    assert API.processar_certidao(
        [{"cd_pedido": 123, "vl_orcamento": 0}]) == {"message": "ok"}


def test_nao_se_envia_lista_vazia():
    """Mandar nada e receber 200 faria a tela dizer que enviou."""
    for chamar in (API.processar_anuencia, API.processar_certidao):
        with pytest.raises(API.CenprotError) as e:
            chamar([])
        assert "marcad" in str(e.value)


def test_o_cancelamento_pede_o_codigo_do_pedido():
    """E ele vem do próprio GET — a frase diz de onde."""
    with pytest.raises(API.CenprotError) as e:
        API.cancelar_protesto("nao e numero")
    assert "cancelamento/pedidos" in str(e.value)


def test_as_custas_exigem_o_nome_do_arquivo():
    """**O NOME FAZ PARTE DO CONTRATO**, e tem forma: sem ele, a Central
    recebe um arquivo que não sabe de quem é."""
    with pytest.raises(API.CenprotError) as e:
        API.enviar_custas("", "SGVsbG8=")
    assert "AAAAMMDD" in str(e.value)
    with pytest.raises(API.CenprotError):
        API.enviar_custas("MA-2198765-01-E-20260902-01.txt", "")


def test_o_periodo_do_cancelamento_e_obrigatorio():
    """O contrato marca as duas datas como obrigatórias."""
    with pytest.raises(API.CenprotError) as e:
        API.pedidos_de_cancelamento(inicio="", fim="")
    assert "período" in str(e.value)


# ------------------------------------------- as regras da casa


def test_a_base_tem_de_ser_https():
    """A credencial e o token viajam nesta conexão."""
    with pytest.raises(API.CenprotError) as e:
        API._partes("http://wspub.cenprotnacional.org.br/x")
    assert "https" in str(e.value)


def test_a_homologacao_e_o_padrao():
    """Onde se começa — e o engano cai para o lado seguro."""
    assert API.base_do_ambiente(None) == API.BASE_DO_AMBIENTE[CRED.HOMOLOGACAO]
    assert API.base_do_ambiente("sei la") == API.BASE_DO_AMBIENTE[CRED.HOMOLOGACAO]
    assert "homolog" in API.base_do_ambiente(CRED.HOMOLOGACAO)
    assert "homolog" not in API.base_do_ambiente(CRED.PRODUCAO)


def test_a_barra_do_fim_da_homologacao_nao_dobra():
    """O contrato traz `.../cartorio-homolog/`; juntar com `/token` daria
    `//token`, que devolve 404 sem dizer por quê."""
    _, _, prefixo = API._partes(API.base_do_ambiente(CRED.HOMOLOGACAO))
    assert not prefixo.endswith("/")
    assert (prefixo + API.CAMINHO["token"]).count("//") == 0


def test_nenhuma_funcao_recebe_con():
    """**CHAMADA DE REDE NÃO ENTRA EM TRANSAÇÃO.** É a regra desde o selador:
    um `BEGIN IMMEDIATE` segurado por trinta segundos põe todo outro balcão no
    `busy_timeout`. Aqui a regra se varre, e não se lembra."""
    for nome, obj in vars(API).items():
        if not inspect.isfunction(obj) or obj.__module__ != API.__name__:
            continue
        assert "con" not in set(inspect.signature(obj).parameters), (
            f"`{nome}` recebe `con` — chamada de rede não pode entrar numa "
            f"transação de escrita")


def test_o_post_do_token_manda_usuario_e_senha_no_formulario(tmp_path, monkeypatch):
    """Medido no OpenAPI: `POST /token` exige form `usuario` e `senha`."""
    CRED.gravar(CRED.CENPROT, usuario="01234567", senha="Cenprot@2024",
                pasta=tmp_path)
    visto: dict = {}

    def fake_bater(ambiente, metodo, caminho, *, corpo=None, cabecalhos=None,
                   prazo=60, com_token=True, pasta=None):
        visto.update(metodo=metodo, caminho=caminho, corpo=corpo,
                     cabecalhos=dict(cabecalhos or {}), com_token=com_token)
        return {"status": 200, "json": {"access_token": "jwt-teste"}, "texto": "{}"}

    monkeypatch.setattr(API, "_bater", fake_bater)
    assert API._pedir_token(CRED.HOMOLOGACAO, pasta=tmp_path) == "jwt-teste"
    assert visto["metodo"] == "POST"
    assert visto["caminho"] == API.CAMINHO["token"]
    assert visto["com_token"] is False
    assert visto["cabecalhos"]["Content-Type"] == API.TIPO_DO_FORMULARIO
    campos = urllib.parse.parse_qs(visto["corpo"].decode("utf-8"))
    assert campos["usuario"] == ["01234567"]
    assert campos["senha"] == ["Cenprot@2024"]


def test_a_producao_devolve_token_e_nao_access_token(tmp_path, monkeypatch):
    """Medido na produção em 13/10/2026: `{"token": …, "message": "Sucesso"}`.
    O contrato diz `access_token`; lendo só ele, a autenticação certa virava
    falha — e a mensagem de falha imprimia o token na tela."""
    CRED.gravar(CRED.CENPROT, usuario="01234567", senha="Cenprot@2024",
                pasta=tmp_path)
    monkeypatch.setattr(API, "_bater", lambda *a, **k: {
        "status": 200, "json": {"token": "abc123", "message": "Sucesso"},
        "texto": '{"token":"abc123"}'})
    assert API._pedir_token(CRED.HOMOLOGACAO, pasta=tmp_path) == "abc123"
    monkeypatch.setattr(API, "_bater", lambda *a, **k: {
        "status": 200, "json": {"segredo": "nao-mostre"},
        "texto": '{"segredo":"nao-mostre"}'})
    with pytest.raises(API.CenprotError) as erro:
        API._pedir_token(CRED.HOMOLOGACAO, pasta=tmp_path)
    assert "nao-mostre" not in str(erro.value)


def test_o_token_fica_na_memoria_e_nao_em_disco(tmp_path, monkeypatch):
    """Guardá-lo em disco seria criar um segundo segredo para vazar."""
    CRED.gravar(CRED.CENPROT, usuario="0000000", senha="Cenprot@2024",
                pasta=tmp_path)
    monkeypatch.setattr(API, "_pedir_token", lambda a, pasta=None: "jwt-fingido")
    API.esquecer_token()
    try:
        assert API.token(CRED.HOMOLOGACAO, pasta=tmp_path) == "jwt-fingido"

        def nao_pode(a, pasta=None):
            raise AssertionError("pediu token de novo sem precisar")

        monkeypatch.setattr(API, "_pedir_token", nao_pode)
        assert API.token(CRED.HOMOLOGACAO, pasta=tmp_path) == "jwt-fingido"

        for arq in tmp_path.rglob("*"):
            if arq.is_file():
                assert b"jwt-fingido" not in arq.read_bytes()
    finally:
        API.esquecer_token()


def test_o_401_renova_o_token_uma_vez_e_nao_em_laco(monkeypatch):
    """**Credencial errada devolve 401 sempre**, e um laço faria o sistema
    martelar a Central até ela barrar a serventia."""
    chamadas = {"n": 0}

    def sempre_401():
        chamadas["n"] += 1
        return {"status": 401, "json": None, "texto": ""}

    monkeypatch.setattr(API, "esquecer_token", lambda *a, **kw: None)
    r = API._com_renovacao(CRED.HOMOLOGACAO, sempre_401)
    assert r["status"] == 401
    assert chamadas["n"] == 2, "tentou uma vez, renovou, tentou outra — e parou"


def test_o_404_e_caso_normal_e_a_frase_diz_isso():
    """Pendência já tratada por outra pessoa é rotina numa Central que trabalha
    o dia inteiro — a frase não pode assustar quem está no balcão."""
    with pytest.raises(API.CenprotRecusou) as e:
        API._resposta_ou_erro({"status": 404, "json": None, "texto": ""},
                              "baixar as anuências")
    assert "normal" in str(e.value)


def test_o_diagnostico_nao_baixa_nem_envia_nada(tmp_path):
    """É o botão «testar a conexão»: sem credencial ele diz isso, e pronto."""
    d = API.diagnostico(CRED.HOMOLOGACAO, pasta=tmp_path)
    assert d["ok"] is False
    assert "não foi informada" in d["motivo"]


def test_o_modulo_nao_tem_funcao_que_lavre_ato():
    """**A CENTRAL NÃO LAVRA ATO NESTA CASA.** Quem aponta, protesta, cancela e
    certifica é o módulo de domínio, com as recusas que ele já tem — a regra do
    CNIB pela terceira vez."""
    for nome in vars(API):
        if nome.startswith("_"):
            continue
        for palavra in ("lavrar", "protestar", "apontar", "numerar", "selar",
                        "averbar", "cobrar"):
            assert palavra not in nome.lower(), (
                f"`{nome}` tem cara de quem lavra ato — este módulo é "
                f"transporte")


@tem_contrato
def test_a_versao_do_contrato_esta_registrada():
    """**O PDF é da versão 1.0 e o contrato vivo é 2.1.0.** Se alguém trocar o
    arquivo por um mais novo, este teste conta a história de novo."""
    m = re.search(r"^  version: (\S+)", _spec(), re.MULTILINE)
    assert m, "o contrato não declara versão"
    assert m.group(1) == "2.1.0", (
        f"o contrato salvo agora é {m.group(1)} — releia o que mudou antes de "
        f"confiar no módulo, e atualize este teste com a versão nova")


# ============================================================================
# A REMESSA DA CENPROT — `/pedidos/consulta` e `/pedidos/protocolar`.
#
# É o **passo 1 do roteiro das Centrais**, que não tinha tela nenhuma.
# ============================================================================


def _tipo_do_corpo(rota: str) -> str:
    """`array` ou `object` — o que o schema do corpo daquele POST declara."""
    m = re.search(r"requestBody:(?:.|\n)*?schema:\n\s+type: (\w+)",
                  _trecho_da_rota(rota))
    assert m, f"{rota} não declara o tipo do corpo"
    return m.group(1)


@tem_contrato
def test_o_corpo_vai_EMBRULHADO_no_protocolar_e_CRU_nos_processar(monkeypatch):
    """**A CORREÇÃO MAIS CARA DESTE PROJETO FOI ESTA, PELO OUTRO LADO.**

    Eu embrulhava o pedido de selo em `{"dadosSelo": …}` porque a documentação
    nomeava o parâmetro de corpo — e com o embrulho **nenhum selo automático
    sairia, em atribuição nenhuma**. A lição não é «nunca embrulhe»: é **leia o
    schema de cada caminho**, porque nesta mesma API os três POST não são
    iguais.

    O contrato declara, e o módulo obedece:

        /v2/anuencia/processar   type: array   → o corpo É a lista
        /v2/certidao/processar   type: array   → o corpo É a lista
        /pedidos/protocolar      type: object  → `{"pedidos": [...]}`
    """
    assert _tipo_do_corpo("/v2/anuencia/processar") == "array"
    assert _tipo_do_corpo("/v2/certidao/processar") == "array"
    assert _tipo_do_corpo("/pedidos/protocolar") == "object"

    enviados: list = []
    monkeypatch.setattr(API, "_escrever",
                        lambda amb, ch, corpo, oq, **kw: enviados.append(corpo))

    API.processar_anuencia([_anuencia()])
    API.processar_certidao([{"cd_pedido": 1, "vl_orcamento": 10}])
    API.protocolar_pedidos([{
        "cd_pedido_protesto": 100001,
        "cd_chave_unica": "21987650141243301260417",
        "nm_nr_protocolo": "2604170001",
        "dt_protocolo": "2026-04-17",
        "vl_retirada": 82.64}])

    assert isinstance(enviados[0], list), "a anuência vai CRUA"
    assert isinstance(enviados[1], list), "a certidão vai CRUA"
    assert isinstance(enviados[2], dict), "o protocolar vai EMBRULHADO"
    assert list(enviados[2]) == ["pedidos"]


@tem_contrato
def test_a_consulta_de_pedidos_usa_os_nomes_do_contrato():
    assert _query_do_contrato("/pedidos/consulta") == {"nr_pedido", "data_pedido"}


@tem_contrato
def test_o_protocolar_exige_os_cinco_campos_que_o_contrato_lista():
    """«Todos os campos do protocolar são obrigatórios em qualquer modo.»"""
    do_modulo = {c for c, _ in API.CAMPOS_DO_PROTOCOLAR}
    assert do_modulo == _corpo_obrigatorio("/pedidos/protocolar")


@tem_contrato
def test_o_teto_do_lote_e_o_do_contrato_e_NAO_o_dos_processar():
    """**O teto não é o mesmo em toda a API** — 1.000 nos `processar` e 50
    aqui. Escrever o mesmo número nos três é mais um engano que sai calado."""
    t = _trecho_da_rota("/pedidos/protocolar")
    assert re.search(r"maxItems: (\d+)", t).group(1) == str(
        API.LIMITE_DO_LOTE_PROTOCOLAR)


@tem_contrato
def test_a_chave_unica_tem_o_tamanho_do_contrato_e_o_da_casa():
    """O contrato declara 23, e a chave que esta casa mediu tem 23 dígitos —
    IBGE(7) + CENPROT(8) + cartório(2) + AAMMDD(6), em 175 de 175.

    **E o exemplo do próprio contrato desobedece à restrição dele**
    (`SP12345678900000000000123`, 25 caracteres): vale a restrição, que bate
    com o dado real, e não o exemplo.
    """
    t = _trecho_da_rota("/pedidos/protocolar")
    assert re.search(r"minLength: (\d+)", t).group(1) == str(
        API.DIGITOS_DA_CHAVE_UNICA)
    assert len("2198765" + "01412433" + "01" + "260417") == (
        API.DIGITOS_DA_CHAVE_UNICA)
    assert len(re.search(r"example: (SP\S+)", t).group(1)) != (
        API.DIGITOS_DA_CHAVE_UNICA), (
        "o exemplo do contrato passou a obedecer à restrição — releia o "
        "arquivo, porque este teste guardava uma contradição dele")


def test_a_consulta_de_pedidos_exige_um_dos_dois_filtros():
    """Sem nenhum, a Central responde erro; a recusa daqui diz o que informar."""
    with pytest.raises(API.CenprotError) as e:
        API.pedidos_de_protesto()
    assert "número do pedido ou a data" in str(e.value)


def test_o_protocolar_recusa_lote_maior_que_o_teto():
    um = {"cd_pedido_protesto": 1, "cd_chave_unica": "2" * 23,
          "nm_nr_protocolo": "1", "dt_protocolo": "2026-04-17",
          "vl_retirada": 1}
    with pytest.raises(API.CenprotError) as e:
        API.protocolar_pedidos([dict(um) for _ in range(51)])
    assert "50" in str(e.value)


def test_o_protocolar_nao_inventa_chave_unica():
    """**O `GET` não devolve a chave, e o `POST` a exige** — medido: o
    `/pedidos/consulta` não a traz em campo nenhum. Ela vem do XML diário, que
    `protesto_cenprot` já lê. A recusa diz onde consegui-la."""
    with pytest.raises(API.CenprotError) as e:
        API.protocolar_pedidos([{
            "cd_pedido_protesto": 1, "cd_chave_unica": "123",
            "nm_nr_protocolo": "1", "dt_protocolo": "2026-04-17",
            "vl_retirada": 1}])
    assert "Chave do CENPROT" in str(e.value)
    with pytest.raises(API.CenprotError) as e:
        API.protocolar_pedidos([{
            "cd_chave_unica": "2" * 23, "nm_nr_protocolo": "1",
            "dt_protocolo": "2026-04-17", "vl_retirada": 1}])
    assert "cd_pedido_protesto" in str(e.value)


def test_o_protocolar_aceita_valor_de_retirada_ZERO(monkeypatch):
    """Pelo mesmo motivo das custas: zero é gratuidade, e não campo em branco."""
    monkeypatch.setattr(API, "_escrever", lambda *a, **kw: {"ok": True})
    API.protocolar_pedidos([{
        "cd_pedido_protesto": 1, "cd_chave_unica": "2" * 23,
        "nm_nr_protocolo": "1", "dt_protocolo": "2026-04-17",
        "vl_retirada": 0}])
