"""O transporte da Certidao Eletronica, conferido CONTRA O CONTRATO GUARDADO.

**ESTES TESTES ABREM O `swagger.json` E COMPARAM.** E a licao da CENPROT (seis
defeitos meus so apareceram quando o teste abriu o contrato), a da ONRTDPJ, e a
do e-Proclamas — onde eu tratei HTTP 200 como sucesso porque tinha lido so a
`description` de cada resposta.

O contrato mora em `FONTES_EXTERNAS/onrcpn/`, **fora** da pasta que viaja no
`.cgu`. Quando ele nao esta na maquina, estes testes **pulam** — nunca passam
calados, que seria pior: um teste verde sem ter conferido nada.

NENHUM TESTE DAQUI FALA COM A CENTRAL.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import onrcpn_api as PROC
import onrcpn_certidao_api as API

PROJETO = RAIZ.parent.parent
CONTRATO = PROJETO / API.CONTRATO_NO_PROJETO


def _abrir(caminho: Path):
    if not caminho.is_file():
        pytest.skip(f"o contrato nao esta nesta maquina: {caminho}")
    return json.loads(caminho.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def contrato():
    return _abrir(CONTRATO)


# ------------------------------------------------------------- os caminhos


def test_os_dez_caminhos_existem_no_contrato(contrato):
    """Caminho escrito a mao que a Central nao conhece devolve 404 — e 404
    numa integracao nova se le como «nao ha nada hoje»."""
    declarados = set(contrato["paths"])
    for qual, caminho in API.CAMINHO.items():
        assert caminho.replace(":id", "{id}") in declarados, \
            f"o caminho «{qual}» nao esta no contrato"


def test_nao_sobra_nem_falta_caminho(contrato):
    assert len(API.CAMINHO) == len(contrato["paths"]) == 10


def test_o_metodo_de_cada_caminho_bate(contrato):
    """Em OpenAPI o metodo faz parte da identidade do caminho: `PUT` onde a
    Central espera `POST` responde 405, e 405 nao diz o que esta errado."""
    for qual, caminho in API.CAMINHO.items():
        ops = contrato["paths"][caminho.replace(":id", "{id}")]
        metodos = {m.upper() for m in ops if m in
                   ("get", "post", "put", "patch", "delete")}
        assert API.METODO_DO_CAMINHO[qual] in metodos, qual


def test_o_contrato_nao_declara_servidor_nenhum(contrato):
    """A BASE **nao sai do contrato** — ele nao tem `servers`. Sai da pagina de
    documentacao, e tem o «h» de homologacao.

    Se um dia declararem, este teste fica vermelho e a BASE passa a ter fonte
    melhor que a pagina de documentacao.
    """
    assert not contrato.get("servers"), (
        "o contrato passou a declarar `servers` — confira a BASE contra ele")
    assert API.BASE.startswith("https://certidaoh.")


def test_a_seguranca_e_bearer(contrato):
    esquema = contrato["components"]["securitySchemes"]["BearerAuth"]
    assert esquema == {"type": "http", "scheme": "bearer",
                       "bearerFormat": "JWT"}


def test_so_um_caminho_nao_declara_seguranca(contrato):
    """**O `certificate-file` e o unico dos dez sem `security`.**

    E omissao do contrato, e nao caminho aberto: mesmo cadastro, mesmo token,
    mesma Central. **Este teste fica vermelho quando corrigirem** — para a
    correcao nao passar despercebida, que e a decisao do `http://` no WSDL da
    CRA.
    """
    sem = []
    for caminho, ops in contrato["paths"].items():
        for metodo, op in ops.items():
            if metodo not in ("get", "post", "put", "patch", "delete"):
                continue
            if not op.get("security"):
                sem.append((metodo, caminho))
    assert sem == [("post", API.CAMINHO["criar_arquivo"])], sem
    assert API.CAMINHO_SEM_SEGURANCA_DECLARADA == "criar_arquivo"


def test_os_dois_caminhos_de_arquivo_recusam_ser_chamados():
    """Medidos e nao ligados — e a recusa diz onde esta a razao."""
    for qual in API.CAMINHOS_NAO_LIGADOS:
        with pytest.raises(API.CertidaoError) as erro:
            API._bater(qual)
        assert "nao esta ligado" in str(erro.value).replace("ã", "a") \
            or "não está ligado" in str(erro.value)


# ------------------------------------------------------------- os esquemas


def test_os_cinco_esquemas_existem(contrato):
    assert set(contrato["components"]["schemas"]) == {
        "Certidao", "Nascimento", "Casamento", "Obito", "InteiroTeor"}


@pytest.mark.parametrize("esquema,campos", [
    ("Certidao", "CAMPOS_DA_CERTIDAO"),
    ("Nascimento", "CAMPOS_DO_NASCIMENTO"),
    ("Casamento", "CAMPOS_DO_CASAMENTO"),
    ("Obito", "CAMPOS_DO_OBITO"),
    ("InteiroTeor", "CAMPOS_DO_INTEIRO_TEOR"),
])
def test_os_campos_de_cada_esquema_batem(contrato, esquema, campos):
    """Campo a mais o servidor ignora **calado**; campo a menos sai em branco
    numa certidao assinada."""
    do_contrato = list(contrato["components"]["schemas"][esquema]["properties"])
    assert list(getattr(API, campos)) == do_contrato


def test_nenhum_esquema_declara_obrigatorio(contrato):
    """**Nao se inventa obrigacao que o contrato nao declara** — o terceiro
    contrato de Central seguido assim, depois dos `/v2` da CENPROT e da
    ONRTDPJ. Se um dia declararem, este teste fica vermelho e a conferencia
    do dominio passa a ter fonte."""
    for nome, esquema in contrato["components"]["schemas"].items():
        assert not esquema.get("required"), nome


def test_os_campos_do_conjuge_batem(contrato):
    do_contrato = list(contrato["components"]["schemas"]["Casamento"]
                       ["properties"]["conjuges"]["items"]["properties"])
    assert list(API.CAMPOS_DO_CONJUGE) == do_contrato


def test_os_campos_da_anotacao_de_cadastro_batem(contrato):
    do_contrato = list(contrato["components"]["schemas"]["Nascimento"]
                       ["properties"]["anotacoes_cadastro"]["items"]
                       ["properties"])
    assert list(API.CAMPOS_DA_ANOTACAO_DE_CADASTRO) == do_contrato


def test_os_vocabularios_fechados_batem(contrato):
    props = contrato["components"]["schemas"]
    assert list(props["Certidao"]["properties"]["tipo_registro"]["enum"]) == \
        list(API.TIPOS_DE_REGISTRO)
    assert list(props["Certidao"]["properties"]["modalidade"]["enum"]) == \
        list(API.MODALIDADES)
    assert list(props["Nascimento"]["properties"]["sexo"]["enum"]) == \
        list(API.SEXOS)
    assert list(props["Obito"]["properties"]["existencia_bens"]["enum"]) == \
        list(API.EXISTENCIA_BENS)
    assert list(props["Obito"]["properties"]["existencia_filhos_opcao"]
                ["enum"]) == list(API.EXISTENCIA_FILHOS)
    assert list(props["Nascimento"]["properties"]["anotacoes_cadastro"]
                ["items"]["properties"]["tipo"]["enum"]) == \
        list(API.TIPOS_DE_DOCUMENTO)


# --------------------------------------------------------- a fila de pedidos


def test_os_sete_modulos_estao_na_prosa_do_contrato(contrato):
    """**Eles nao estao numa lista fechada**: o campo `modulo` e um `string`
    com o exemplo «CRC». Os sete estao na descricao, e e de la que sairam."""
    desc = contrato["paths"][API.CAMINHO["obter_pedidos"]]["post"]["description"]
    for modulo in API.MODULOS:
        assert f"<b>{modulo}</b>" in desc, modulo
    assert len(API.MODULOS) == 7


def test_os_dois_modulos_de_registro_dizem_REGISTRO_na_descricao(contrato):
    """P13 e EOB pedem que se **lavre**, e nao que se emita — e e a descricao
    do contrato que diz isso, com a palavra «registro»."""
    desc = contrato["paths"][API.CAMINHO["obter_pedidos"]]["post"]["description"]
    for modulo in API.MODULOS_DE_REGISTRO:
        pedaco = desc.split(f"<b>{modulo}</b>")[1][:120].lower()
        assert "registro" in pedaco, modulo
    assert set(API.MODULOS_DE_REGISTRO) == {"P13", "EOB"}
    assert set(API.MODULOS_DE_CERTIDAO) | set(API.MODULOS_DE_REGISTRO) == \
        set(API.MODULOS)


def test_as_colunas_do_pedido_batem(contrato):
    linha = (contrato["paths"][API.CAMINHO["obter_pedidos"]]["post"]
             ["responses"]["200"]["content"]["application/json"]["schema"]
             ["properties"]["rows"]["items"]["properties"])
    assert list(API.CAMPOS_DO_PEDIDO) == list(linha)


def test_os_oito_obrigatorios_do_envio_batem(contrato):
    esquema = (contrato["paths"][API.CAMINHO["enviar_pedidos"]]["post"]
               ["requestBody"]["content"]["application/json"]["schema"])
    assert list(API.CAMPOS_DO_ENVIO) == list(esquema["required"])


def test_os_tres_obrigatorios_da_rejeicao_batem(contrato):
    esquema = (contrato["paths"][API.CAMINHO["rejeitar_pedidos"]]["post"]
               ["requestBody"]["content"]["application/json"]["schema"])
    assert list(API.CAMPOS_DA_REJEICAO) == list(esquema["required"])


def test_o_numero_do_pedido_tem_tipos_DIFERENTES_nos_dois_caminhos(contrato):
    """**A MESMA CHAVE, DOIS TIPOS, NO MESMO CONTRATO** — e um terceiro nome na
    resposta. E a armadilha do `cd_pedido` da CENPROT outra vez."""
    enviar = (contrato["paths"][API.CAMINHO["enviar_pedidos"]]["post"]
              ["requestBody"]["content"]["application/json"]["schema"]
              ["properties"]["numero_pedido"]["type"])
    rejeitar = (contrato["paths"][API.CAMINHO["rejeitar_pedidos"]]["post"]
                ["requestBody"]["content"]["application/json"]["schema"]
                ["properties"]["numero_pedido"]["type"])
    assert enviar == "string"
    assert rejeitar == "number"
    assert API.TIPO_DO_NUMERO_DO_PEDIDO["enviar_pedidos"] is str
    assert API.TIPO_DO_NUMERO_DO_PEDIDO["rejeitar_pedidos"] is int
    # E o terceiro nome, na resposta:
    assert "pedido_certidao_id" in API.CAMPOS_DO_PEDIDO
    assert "numero_pedido" not in API.CAMPOS_DO_PEDIDO


def test_a_regra_do_quantidade_averbacao_esta_na_descricao(contrato):
    """«Quando a solicitacao for de outro estado, envie o valor NULL.»"""
    desc = contrato["paths"][API.CAMINHO["enviar_pedidos"]]["post"]["description"]
    assert "quantidade_averbacao" in desc
    assert "NULL" in desc
    assert "S&atilde;o Paulo" in desc or "São Paulo" in desc
    assert API.UF_QUE_CONTA_AVERBACAO == "SP"


# -------------------------------------------------------------- o que volta


def test_a_resposta_declara_success(contrato):
    """E a licao do e-Proclamas: la eu li so a `description` e concluí que o
    corpo nao era declarado. Aqui ele **e**, e tem um campo que responde."""
    esquema = (contrato["paths"][API.CAMINHO["criar"]]["post"]["responses"]
               ["201"]["content"]["application/json"]["schema"]["properties"])
    assert API.CAMPO_DO_SUCESSO in esquema
    assert esquema[API.CAMPO_DO_SUCESSO]["type"] == "boolean"
    assert API.CAMPO_DO_ID in esquema[API.CAMPO_DOS_DADOS]["properties"]


def test_o_arquivo_e_lista_de_bytes_e_nao_base64(contrato):
    """`{type, data: array[integer]}` e um `Buffer` do Node em JSON. Quem
    tratar como base64 grava um PDF corrompido que so aparece ao abrir."""
    arquivo = (contrato["paths"][API.CAMINHO["criar"]]["post"]["responses"]
               ["201"]["content"]["application/json"]["schema"]["properties"]
               ["data"]["properties"]["arquivo"])
    assert arquivo["properties"]["data"]["type"] == "array"
    assert arquivo["properties"]["data"]["items"]["type"] == "integer"


def test_o_410_da_assinatura_nao_tem_success(contrato):
    """A excecao declarada — e por isso ela tem tratamento proprio."""
    resposta = (contrato["paths"][API.CAMINHO["assinar"].replace(":id", "{id}")]
                ["post"]["responses"]["410"]["content"]["application/json"]
                ["schema"]["properties"])
    assert API.CAMPO_DO_SUCESSO not in resposta
    assert 410 in API.STATUS_SEM_SUCESSO


def test_a_assinatura_devolve_link_e_id(contrato):
    dados = (contrato["paths"][API.CAMINHO["assinar"].replace(":id", "{id}")]
             ["post"]["responses"]["200"]["content"]["application/json"]
             ["schema"]["properties"]["data"]["properties"])
    assert API.CAMPO_DO_LINK_DE_ASSINATURA in dados
    assert API.CAMPO_DO_ID_DA_ASSINATURA in dados


def test_o_message_do_envio_e_um_INTEIRO(contrato):
    """O unico caminho assim. Tratar como frase daria «1» na tela onde deveria
    ir o numero que a Central devolveu."""
    esquema = (contrato["paths"][API.CAMINHO["enviar_pedidos"]]["post"]
               ["responses"]["200"]["content"]["application/json"]["schema"]
               ["properties"])
    assert esquema[API.CAMPO_DA_MENSAGEM]["type"] == "integer"


# ------------------------------------------------------- o que ela entende


def test_o_cpf_vai_COM_mascara_ao_contrario_do_eproclamas():
    """**A MESMA CENTRAL, DOIS FORMATOS.** Este teste existe para um conserto
    distraido nao igualar as duas."""
    assert API.cpf_para_a_central("00000004693") == "000.000.046-93"
    assert PROC.cpf_para_a_central("000.000.046-93") == "00000004693"
    assert API.cpf_para_a_central(" ") == ""


def test_os_exemplos_de_cpf_do_contrato_estao_todos_mascarados(contrato):
    """A medicao que decidiu a funcao acima: cinco exemplos, todos pontuados."""
    achados = []

    def caminhar(no):
        if isinstance(no, dict):
            for k, v in no.items():
                if k in ("cpf", "cpf_secundario") and isinstance(v, dict) \
                        and "example" in v:
                    achados.append(v["example"])
                caminhar(v)
        elif isinstance(no, list):
            for v in no:
                caminhar(v)

    caminhar(contrato)
    assert achados, "o contrato deixou de trazer exemplo de CPF"
    for ex in achados:
        assert "." in ex and "-" in ex, ex


def test_a_data_e_a_mesma_das_duas_apis():
    assert API.data_para_a_central("2026-09-03") == "03/09/2026"
    assert API.data_para_a_central("2026-09-03") == \
        PROC.data_para_a_central("2026-09-03")


def test_os_dois_formatos_de_dinheiro():
    """`cota_emolumentos` vai «R$ 10,00»; `valor_emolumentos` vai «10.00»."""
    assert API.cota_para_a_central("10") == "R$ 10,00"
    assert API.valor_para_a_central("10") == "10.00"
    # E o `deposito_previo` VOLTA com virgula:
    assert API.ler_valor_da_central("43,76") == 43.76
    assert API.ler_valor_da_central("1.234,56") == 1234.56
    assert API.ler_valor_da_central("R$ 43,76") == 43.76
    assert API.ler_valor_da_central("") == 0.0


def test_o_arquivo_vira_bytes():
    assert API.arquivo_para_bytes(
        {"type": "Buffer", "data": [37, 80, 68, 70]}) == b"%PDF"
    assert API.arquivo_para_bytes("JVBERg==") == b"%PDF"
    with pytest.raises(API.CertidaoError):
        API.arquivo_para_bytes(12345)


def test_o_modulo_desconhecido_e_recusado():
    assert API.modulo_da_central("crc") == "CRC"
    with pytest.raises(API.CertidaoError) as erro:
        API.modulo_da_central("XPTO")
    assert "CRC" in str(erro.value)


def test_so_o_N_esta_medido_e_a_letra_desconhecida_devolve_None():
    """**Um caso que separa vale mais que cinco que concordam** — e aqui nao ha
    caso nenhum alem do `N`. Devolver palpite faria a fila dizer «casamento»
    sobre um pedido que ninguem conferiu."""
    assert API.especie_do_pedido("N") == "nascimento"
    assert API.especie_do_pedido("X") is None
    assert API.LETRAS_MEDIDAS == frozenset({"N"})


def test_o_token_e_o_MESMO_do_eproclamas():
    """Um cadastro serve as duas — esta na nota do contrato do e-Proclamas."""
    assert API.token.__module__ == "onrcpn_certidao_api"
    assert API.tem_credencial() == PROC.tem_credencial()


def test_o_https_e_forcado_e_e_a_MESMA_funcao_das_duas_apis():
    """O https e o «so GET se repete» sao as duas regras que nao podem
    divergir entre as duas APIs da mesma Central."""
    with pytest.raises(PROC.OnrcpnError):
        PROC.partes("http://certidaoh.registrocivil.org.br")
    assert PROC.partes(API.BASE)[0] == "certidaoh.registrocivil.org.br"


# ---------------------------------------------- o que ele recusa sem rede


def test_obter_pedidos_recusa_sem_cns():
    with pytest.raises(API.CertidaoError) as erro:
        API.obter_pedidos("CRC", "")
    assert "CNS" in str(erro.value)


def test_enviar_pedido_recusa_sem_id_verificador():
    with pytest.raises(API.CertidaoError) as erro:
        API.enviar_pedido(numero_pedido="1", modulo="CRC",
                          valor_emolumentos="1", id_externo="1",
                          id_verificador="")
    assert "id_verificador" in str(erro.value)


def test_rejeitar_pedido_exige_motivo_escrito():
    with pytest.raises(API.CertidaoError) as erro:
        API.rejeitar_pedido(numero_pedido="21038065", modulo="CRC", motivo="")
    assert "motivo" in str(erro.value).lower()


def test_o_caminho_com_id_recusa_id_vazio():
    with pytest.raises(API.CertidaoError):
        API._endereco("assinar", "")
    assert API._endereco("assinar", "abc") == "/api/v1.0/sign-certificate-json/abc"


# ------------------------------------------------ a leitura da resposta


def _resposta(status, corpo):
    return {"status": status, "json": corpo, "texto": json.dumps(corpo)}


def test_HTTP_bom_com_success_falso_NAO_passa_por_sucesso():
    """**E a licao do e-Proclamas antes de ela custar.**"""
    with pytest.raises(API.CertidaoRecusou) as erro:
        API._resposta_ou_erro(
            _resposta(201, {"success": False, "message": "faltou coisa"}),
            "criar")
    assert "faltou coisa" in str(erro.value)


def test_HTTP_bom_com_success_verdadeiro_passa():
    corpo = API._resposta_ou_erro(
        _resposta(201, {"success": True, "data": {"certidao_id": "abc"}}),
        "criar")
    assert corpo["data"]["certidao_id"] == "abc"


def test_o_422_traz_o_campo_que_a_central_apontou():
    """O `message` do 422 e um objeto POR CAMPO, e nao uma frase — e e ele que
    o escrevente precisa ler inteiro."""
    with pytest.raises(API.CertidaoRecusou) as erro:
        API._resposta_ou_erro(_resposta(422, {
            "success": False,
            "message": {"registro.matricula": ["campo obrigatorio"]}}),
            "criar")
    assert "registro.matricula" in str(erro.value)
    assert "campo obrigatorio" in str(erro.value)


def test_o_410_vira_certidao_cancelada():
    with pytest.raises(API.CertidaoCancelada) as erro:
        API._resposta_ou_erro(
            _resposta(410, {"data": {"status": "cancelada"},
                            "message": "Certidao cancelada."}), "assinar")
    assert "cancelada" in str(erro.value).lower()


def test_o_401_manda_conferir_a_credencial_e_diz_que_e_a_MESMA():
    with pytest.raises(API.CertidaoError) as erro:
        API._resposta_ou_erro(_resposta(401, {"message": "token"}), "criar")
    assert "e-Proclamas" in str(erro.value)


def test_corpo_que_nao_e_objeto_nao_passa_por_sucesso():
    with pytest.raises(API.CertidaoRecusou):
        API._resposta_ou_erro({"status": 200, "json": None, "texto": "ok"},
                              "buscar")
