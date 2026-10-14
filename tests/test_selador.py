"""
O contrato do Selador API do TJMA.

DE ONDE VEM A FORCA DESTES TESTES
    Duas fontes independentes, e o valor esta em elas concordarem:

      1. a documentacao OFICIAL do Selador, achada na maquina do E-Oficio —
         181 endpoints e 115 schemas, datada de 08/10/2017;
      2. os 26.123 pedidos REAIS que esta serventia enviou entre 2020 e 2026.

    `tests/selador_reais.json` guarda os schemas oficiais e um pedido real de
    cada endpoint usado, com nome e documento mascarados. Cada pedido real e
    conferido contra o schema oficial: nenhum deles pode ter campo fora do
    schema nem deixar de enviar campo obrigatorio.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import selador as SD    # noqa: E402

DADOS = json.loads((Path(__file__).parent / "selador_reais.json").read_text(encoding="utf-8"))
SCHEMAS: dict[str, dict] = DADOS["schemas_oficiais"]
PEDIDOS: dict[str, dict] = DADOS["pedidos"]
FORA_DO_DOC = {x["onde"] for x in SD.ALEM_DA_DOCUMENTACAO}


# ================================================== os endpoints oficiais


def test_a_base_do_selador_e_configurada_e_nao_assumida():
    """Esta serventia sela num appliance da REDE LOCAL, nao na nuvem do TJMA.

    `tbSeladorConfiguracao.strUrlSelador` = https://192.168.0.200:443. Os
    enderecos do e-oficio-ma.exe sao padrao de fabrica. Apontar para a nuvem
    uma casa que sela local e 401 no meio do atendimento — ou selo em
    duplicidade.
    """
    assert SD.BASE_OBSERVADA_NA_SERVENTIA.startswith("https://192.168.")
    assert SD.BASE_OBSERVADA_NA_SERVENTIA != SD.BASE_PRODUCAO
    # E quem chama manda a base; o padrao de fabrica so entra se ninguem disser.
    dados = {"quantidade": 1}
    local = SD.montar_pedido("/selo/notas/autenticacao", dados,
                             base=SD.BASE_OBSERVADA_NA_SERVENTIA)
    assert local["url"] == (SD.BASE_OBSERVADA_NA_SERVENTIA
                            + "/selo/notas/autenticacao")
    padrao = SD.montar_pedido("/selo/notas/autenticacao", dados)
    assert padrao["url"].startswith(SD.BASE_PRODUCAO)


def test_a_homologacao_continua_sem_endereco_de_proposito():
    # Chutar endereco de homologacao e pedir para selar de verdade achando que
    # era teste. Fica None ate alguem ler a tela do E-Oficio.
    assert SD.BASE_HOMOLOGACAO is None


def test_os_cento_e_oitenta_e_um_endpoints_da_documentacao():
    assert len(SD.ENDPOINTS) == 181
    por_espaco = {}
    for v in SD.ENDPOINTS.values():
        por_espaco[v["atribuicao"]] = por_espaco.get(v["atribuicao"], 0) + 1
    assert por_espaco == {"civil": 100, "rtdpj": 24, "notas": 18,
                          "imovel": 15, "maritimo": 14, "protesto": 10}


def test_o_protesto_deixou_de_ser_lacuna():
    """Ontem eu não sabia o caminho do selo de protesto. Agora sei os dez."""
    protesto = SD.endpoints_de("protesto")
    assert "/selo/protesto/titulo" in protesto
    assert "/selo/protesto/intimacao" in protesto
    assert "/selo/protesto/pagamento" in protesto
    assert "/selo/protesto/baixa-cancelamento" in protesto
    assert len(protesto) == 10


def test_todo_endpoint_diz_o_embrulho_e_o_schema_do_corpo():
    for caminho, v in SD.ENDPOINTS.items():
        assert v["campo"], caminho
        assert v["schema"], caminho
        assert v["descricao"], caminho
        assert caminho.startswith("/selo/")


def test_caminho_inventado_e_recusado_com_mensagem_util():
    with pytest.raises(SD.SeladorError, match="181"):
        SD.endpoint("/selo/notas/nao-existe")
    with pytest.raises(SD.SeladorError, match="espaço"):
        SD.endpoints_de("cartorio-inventado")


# ============================== os pedidos reais contra os schemas oficiais


def test_a_amostra_cobre_os_endpoints_que_a_serventia_usou():
    assert len(PEDIDOS) == 34


@pytest.mark.parametrize("caminho", sorted(PEDIDOS))
def test_endpoint_realmente_usado_consta_da_documentacao(caminho):
    if caminho in FORA_DO_DOC:
        pytest.skip("endpoint posterior à documentação de 2017, já registrado")
    assert caminho in SD.ENDPOINTS


@pytest.mark.parametrize("caminho", sorted(PEDIDOS))
def test_nenhum_pedido_real_deixou_de_enviar_campo_obrigatorio(caminho):
    """Em 26.123 pedidos, nenhum obrigatório faltou. É o que dá confiança."""
    if caminho not in SD.ENDPOINTS:
        pytest.skip("endpoint posterior à documentação")
    campos = SCHEMAS.get(SD.ENDPOINTS[caminho]["schema"], {})
    obrigatorios = {c for c, v in campos.items() if v == "required"}
    enviados = set(PEDIDOS[caminho])
    assert not (obrigatorios - enviados), (
        f"{caminho}: faltaram {sorted(obrigatorios - enviados)}")


@pytest.mark.parametrize("caminho", sorted(PEDIDOS))
def test_campo_fora_do_schema_ou_consta_do_schema_ou_esta_registrado(caminho):
    if caminho not in SD.ENDPOINTS:
        pytest.skip("endpoint posterior à documentação")
    nome = SD.ENDPOINTS[caminho]["schema"]
    previstos = set(SCHEMAS.get(nome, {}))
    for campo in set(PEDIDOS[caminho]) - previstos:
        assert f"{nome}.{campo}" in FORA_DO_DOC, (
            f"{caminho} enviou «{campo}», que não está no schema {nome} nem "
            f"registrado em ALEM_DA_DOCUMENTACAO")


def test_o_que_a_api_ganhou_depois_de_2017_esta_registrado():
    assert len(SD.ALEM_DA_DOCUMENTACAO) == 5
    for x in SD.ALEM_DA_DOCUMENTACAO:
        assert x["onde"] and x["observacao"] and x["usos_no_acervo"] > 0
        assert x["tipo"] in ("endpoint", "campo")


# =============================================== os enderecos e a autenticacao


def test_os_enderecos_achados_no_binario_do_e_oficio():
    assert SD.BASE_PRODUCAO == "https://selador.ma.portalselo.com.br:9443"
    assert SD.AUTH_PRODUCAO == "https://ma.portalselo.com.br:9443/auth"


def test_a_homologacao_fica_vazia_em_vez_de_chutada():
    """Chutar endereço de homologação é selar de verdade achando que é teste."""
    assert SD.BASE_HOMOLOGACAO is None


def test_a_autenticacao_segue_o_password_grant_documentado():
    p = SD.montar_autenticacao("cartorio1", "seg" + "redo")
    assert p["metodo"] == "POST"
    assert p["url"] == SD.AUTH_PRODUCAO
    assert p["cabecalhos"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert p["formulario"]["client_id"] == "selador"
    assert p["formulario"]["grant_type"] == "password"
    assert set(p["formulario"]) == {"username", "password", "client_id", "grant_type"}


@pytest.mark.parametrize("usuario,senha", [("", "x"), ("  ", "x"), ("u", "")])
def test_autenticacao_sem_credencial_e_recusada(usuario, senha):
    with pytest.raises(SD.SeladorError):
        SD.montar_autenticacao(usuario, senha)


# ================================================================== o SID


def test_o_sid_e_deterministico_para_o_mesmo_ato():
    """É o que faz a repetição devolver o mesmo selo em vez de gerar outro."""
    a = SD.sid("000000", "PROTESTO", "ato:3727")
    b = SD.sid("000000", "PROTESTO", "ato:3727")
    assert a == b


def test_o_sid_muda_de_ato_para_ato():
    a = SD.sid("000000", "PROTESTO", "ato:3727")
    b = SD.sid("000000", "PROTESTO", "ato:3728")
    assert a != b


def test_o_sid_muda_de_atribuicao_para_atribuicao():
    assert SD.sid("000000", "NOTAS", "ato:1") != SD.sid("000000", "RCPN", "ato:1")


def test_o_sid_muda_de_serventia_para_serventia():
    """A documentação pede SID único no universo de cartórios."""
    assert SD.sid("000000", "NOTAS", "ato:1") != SD.sid("111111", "NOTAS", "ato:1")


def test_o_sid_carrega_o_cns_no_comeco():
    assert SD.sid("000000", "NOTAS", "ato:1").startswith("000000")


def test_a_tentativa_permite_pedir_selo_novo_de_proposito():
    a = SD.sid("000000", "NOTAS", "ato:1", tentativa=1)
    b = SD.sid("000000", "NOTAS", "ato:1", tentativa=2)
    assert a != b


@pytest.mark.parametrize("cns,ref", [("", "ato:1"), ("abc", "ato:1"),
                                     ("000000", ""), ("000000", "   ")])
def test_sid_sem_cns_ou_sem_referencia_e_recusado(cns, ref):
    with pytest.raises(SD.SeladorError):
        SD.sid(cns, "NOTAS", ref)


# ============================================================== o pedido


def test_o_corpo_e_o_proprio_objeto_e_nao_um_embrulho():
    """O corpo NAO se embrulha — e a correcao mais cara deste projeto.

    Ate 27/08/2026 o modulo mandava `{"dadosSelo": {...}}`, porque a
    documentacao lista o parametro de corpo com `Name: dadosSelo`. Em Swagger,
    parametro `in: body` nao tem nome dentro do JSON: **o corpo E o schema**.

    Com o embrulho, NENHUM selo automatico sairia, em atribuicao nenhuma — e
    foi o balcao que descobriu, selando um reconhecimento de firma e recebendo
    «O campo "nomesReconhecido" e obrigatorio; O campo "escrevente" e
    obrigatorio»: os dois campos que mandavamos, um nivel abaixo de onde o
    aparelho os procurava.

    Quem desempatou foi o acervo: dos **26.123** envelopes que esta casa
    mandou, **ZERO** vao embrulhados.
    """
    dados = {"escrevente": "X", "ato": {"codigo": "13.17.4",
                                        "codigoTabelaCusta": "0520260101"}}
    p = SD.montar_pedido("/selo/notas/reconhecimento-firma", dados)
    assert p["corpo"] == dados
    assert p["schema"] == "ReconhecimentoFirma"
    assert p["url"].endswith("/selo/notas/reconhecimento-firma")
    assert p["url"].startswith(SD.BASE_PRODUCAO)


def test_dadosSelo_quando_existe_e_campo_de_dentro_do_esquema():
    """E foi essa coincidencia de nome que sustentou o erro por dias.

    No civil e no imovel `dadosSelo` EXISTE mesmo — como campo DE DENTRO do
    objeto, ao lado de `protocolo`, `codigoAto`, `nomesPartes`. Eu via
    `dadosSelo` no envelope real e achava que era o meu embrulho aparecendo.
    """
    dados = {"protocolo": "1", "dadosSelo": {"escrevente": "X"}}
    a = SD.montar_pedido("/selo/imovel/prenotacao", dados)
    assert a["corpo"] == dados
    assert list(a["corpo"]) == ["protocolo", "dadosSelo"]
    b = SD.montar_pedido("/selo/notas/cartao-assinatura", {"x": 1})
    assert b["corpo"] == {"x": 1}


def test_o_sid_vai_na_query_quando_informado():
    s = SD.sid("000000", "NOTAS", "ato:9")
    p = SD.montar_pedido("/selo/notas/autenticacao", {"x": 1}, sid_do_ato=s)
    assert p["query"] == {"sid": s}
    sem = SD.montar_pedido("/selo/notas/autenticacao", {"x": 1})
    assert sem["query"] == {}


def test_pedido_sem_dados_e_recusado():
    with pytest.raises(SD.SeladorError, match="sem dados"):
        SD.montar_pedido("/selo/notas/autenticacao", {})


def test_o_desconto_do_amazonas_e_barrado():
    """Provimento 279/2016 é da CGJ do AMAZONAS, não do Maranhão."""
    with pytest.raises(SD.SeladorError, match="AMAZONAS"):
        SD.montar_pedido("/selo/notas/autenticacao",
                         {"x": 1, "descontoProvimento279": True})
    # falso passa: é o valor que o acervo enviava
    ok = SD.montar_pedido("/selo/notas/autenticacao",
                          {"x": 1, "descontoProvimento279": False})
    assert ok["corpo"]["descontoProvimento279"] is False


@pytest.mark.parametrize("caminho", sorted(PEDIDOS))
def test_todo_pedido_real_do_acervo_se_remonta_pelo_modulo(caminho):
    if caminho not in SD.ENDPOINTS:
        pytest.skip("endpoint posterior à documentação")
    p = SD.montar_pedido(caminho, PEDIDOS[caminho],
                         sid_do_ato=SD.sid("000000", "X", caminho))
    assert p["url"] == SD.BASE_PRODUCAO + caminho
    # O CORPO TEM DE SER O ENVELOPE REAL, BYTE POR BYTE.
    #
    #   Ate 27/08/2026 estas duas linhas diziam outra coisa: que o corpo era o
    #   envelope real EMBRULHADO. Elas pareciam validar contra o acervo, e
    #   validavam contra a minha propria ideia do pedido — o mesmo embrulho
    #   dos dois lados da igualdade. Por isso os 37 casos passavam com o
    #   defeito que impedia todo selo automatico de sair.
    #
    #   Teste que aplica a suposicao aos dois lados nao testa a suposicao.
    assert p["corpo"] == PEDIDOS[caminho]


# ============================================================= a resposta


def test_a_resposta_e_uma_lista_de_selos_e_nao_um_selo():
    """Com `quantidade`, o selador devolve um selo por unidade."""
    selos = SD.ler_resposta({"resumos": [
        {"numeroSelo": "AUTENT000000AAAAAAAAAAAAAAAA", "textoSelo": "t1",
         "dataGeracao": "2026-08-20", "saldoRemanescente": 1250.0},
        {"numeroSelo": "AUTENT000000BBBBBBBBBBBBBBBB", "textoSelo": "t2"},
    ]})
    assert len(selos) == 2
    assert selos[0].numero.startswith("AUTENT000000")
    assert selos[0].saldo_remanescente == 1250.0
    assert selos[1].saldo_remanescente is None


def test_resposta_sem_resumos_manda_ler_como_erro():
    with pytest.raises(SD.SeladorError, match="ler_erro"):
        SD.ler_resposta({"status": 400, "message": "x"})


@pytest.mark.parametrize("corpo", [{"resumos": []}, {"resumos": None}, "texto", None])
def test_resposta_vazia_ou_torta_e_recusada(corpo):
    with pytest.raises(SD.SeladorError):
        SD.ler_resposta(corpo)


def test_resumo_sem_numero_de_selo_e_recusado():
    with pytest.raises(SD.SeladorError, match="numeroSelo"):
        SD.ler_resposta({"resumos": [{"textoSelo": "sem número"}]})


# =============================================================== o erro


def test_o_erro_traz_os_detalhes_campo_a_campo_do_tribunal():
    e = SD.ler_erro({"status": 400, "error": "Bad Request",
                     "message": "Informe todos os dados obrigatórios.",
                     "details": ["Termo, não pode ser nulo",
                                 "VersaoTabelaDeCustas, não pode ser nulo"]})
    assert e.status == 400
    assert "Termo, não pode ser nulo" in str(e)
    assert "VersaoTabelaDeCustas" in str(e)
    assert str(e).startswith("Informe todos os dados obrigatórios.")


def test_erro_sem_detalhes_ainda_diz_algo_util():
    assert str(SD.ler_erro({"message": "Erro no servidor"})) == "Erro no servidor"
    assert str(SD.ler_erro({"error": "Unauthorized"})) == "Unauthorized"
    assert str(SD.ler_erro({})) == "O selador recusou o pedido."


def test_erro_que_nao_e_json_nao_estoura():
    e = SD.ler_erro("<html>502 Bad Gateway</html>")
    assert "502" in e.mensagem


def test_detalhe_em_string_unica_e_aceito():
    e = SD.ler_erro({"message": "x", "details": "um detalhe só"})
    assert e.detalhes == ("um detalhe só",)
