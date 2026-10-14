"""O transporte do e-Proclamas, conferido CONTRA O CONTRATO GUARDADO.

**ESTES TESTES ABREM O `swagger` E COMPARAM.** E a licao da CENPROT, em que
seis defeitos meus so apareceram quando o teste abriu o `swagger.yaml` — e a
da ONRTDPJ depois dela. Caminho escrito a mao que a Central nao conhece
devolve 404, e 404 numa integracao nova parece «nao ha nada hoje».

O contrato mora em `FONTES_EXTERNAS/onrcpn/`, **fora** da pasta que viaja no
`.cgu`. Quando ele nao esta na maquina, estes testes **pulam** — nunca passam
calados, que seria pior: um teste verde sem ter conferido nada.

NENHUM TESTE DAQUI FALA COM A CENTRAL. O que se confere e a forma; a ligacao
se confere no balcao, com credencial, e nao numa suite.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import onrcpn_api as API

# `FONTES_EXTERNAS` fica ao lado de `SERVIDOR/`, e nao dentro dele.
PROJETO = RAIZ.parent.parent
CONTRATO = PROJETO / API.CONTRATO_NO_PROJETO
CONTRATO_CERTIDAO = PROJETO / API.CONTRATO_DA_CERTIDAO


def _abrir(caminho: Path):
    if not caminho.is_file():
        pytest.skip(f"o contrato nao esta nesta maquina: {caminho}")
    return json.loads(caminho.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def contrato():
    return _abrir(CONTRATO)


@pytest.fixture(scope="module")
def contrato_da_certidao():
    return _abrir(CONTRATO_CERTIDAO)


# ---------------------------------------------------------- o endereco


def test_a_base_e_a_que_o_contrato_declara(contrato):
    """`host` + `basePath` + `schemes`, e nao um endereco escrito de memoria."""
    assert contrato["swagger"] == "2.0"
    assert contrato["host"] == "servicosh.registrocivil.org.br"
    assert contrato["schemes"] == ["https"]
    base = f"https://{contrato['host']}" + contrato.get("basePath", "").rstrip("/")
    assert API.BASE == base


def test_o_https_nao_e_opcional():
    """O token viaja nesta conexao, e com ele alguem publica edital."""
    with pytest.raises(API.OnrcpnError, match="https"):
        API.partes("http://servicosh.registrocivil.org.br")


def test_o_host_do_contrato_e_o_de_HOMOLOGACAO_e_isso_fica_dito(contrato):
    """O «h» no nome nao e detalhe: e o ambiente.

    Tirar o «h» para chegar a producao **e palpite**, e palpite de endereco e
    o pior tipo — quem o usasse acharia que testa enquanto fala com a Central
    de verdade. Se um dia o contrato publicado passar a ser o de producao,
    este teste fica vermelho e obriga a reparar.
    """
    assert contrato["host"].split(".")[0].endswith("h")
    import centrais_cred as CRED
    assert CRED.ambientes_de(CRED.ONRCPN) == (CRED.HOMOLOGACAO,)


# ---------------------------------------------------------- os caminhos


def test_os_tres_caminhos_existem_no_contrato_com_o_metodo_certo(contrato):
    for chave, caminho in API.CAMINHO.items():
        assert caminho in contrato["paths"], (
            f"«{chave}» aponta para {caminho}, que nao esta no contrato")
        metodo = API.METODO_DO_CAMINHO[chave].lower()
        assert metodo in contrato["paths"][caminho], (
            f"{caminho} nao tem {metodo.upper()} no contrato")


def test_o_contrato_tem_TRES_caminhos_e_o_modulo_usa_os_tres(contrato):
    """Aqui nao ha caminho declarado e sem funcao — sao tres, e os tres servem."""
    assert len(contrato["paths"]) == 3
    assert set(API.CAMINHO.values()) == set(contrato["paths"])


def test_o_recibo_usa_dois_pontos_e_nao_chaveta(contrato):
    """O contrato foi escrito no estilo do Express, e a marca importa.

    Trocar `:matricula` por `{matricula}` faria este teste deixar de achar o
    caminho no contrato — e o modulo passaria a montar uma URL que a Central
    nao conhece.
    """
    assert ":matricula" in API.CAMINHO["recibo"]
    assert API.CAMINHO["recibo"] in contrato["paths"]


# ---------------------------------------------------------- o corpo


def _corpo_do_enviar(contrato) -> dict:
    for p in contrato["paths"]["/api/proclama/enviar"]["post"]["parameters"]:
        if p.get("in") == "body":
            return p["schema"]
    raise AssertionError("o `enviar` nao declara corpo")


def test_os_campos_do_lote_sao_os_do_contrato(contrato):
    esquema = _corpo_do_enviar(contrato)
    assert set(esquema["properties"]) == set(API.CAMPOS_DO_LOTE)


def test_os_campos_do_proclama_sao_os_do_contrato(contrato):
    """JSON e sensivel a caixa e a Central ignora o que nao conhece.

    Mandar `Matricula` em vez de `matricula` faria o proclama subir **sem
    matricula**, com HTTP 200 e nada acontecendo do lado de la.
    """
    item = _corpo_do_enviar(contrato)["properties"]["proclamas"]["items"]
    assert set(item["properties"]) == set(API.CAMPOS_DO_PROCLAMA)


def test_os_campos_do_conjuge_sao_os_do_contrato(contrato):
    item = _corpo_do_enviar(contrato)["properties"]["proclamas"]["items"]
    for qual in ("conjuge_1", "conjuge_2"):
        c = item["properties"][qual]
        assert set(c["properties"]) == set(API.CAMPOS_DO_CONJUGE), qual


def test_os_campos_do_endereco_e_da_filiacao_sao_os_do_contrato(contrato):
    item = _corpo_do_enviar(contrato)["properties"]["proclamas"]["items"]
    c = item["properties"]["conjuge_1"]["properties"]
    assert set(c["endereco_residencia"]["properties"]) == set(
        API.CAMPOS_DO_ENDERECO)
    assert set(c["filiacao"]["items"]["properties"]) == set(
        API.CAMPOS_DA_FILIACAO)


def test_o_modulo_nao_manda_campo_que_o_contrato_nao_declara(contrato):
    """Campo nosso que vaze para o corpo nao estoura nada e nao faz nada.

    Por isso a montagem e por lista fechada, e nao por `dict(p)` — e este
    teste prova que a lista fechada e a do contrato.
    """
    montado = API.conferir_proclama({"matricula": "1" * 32, "publicacao": True})
    item = _corpo_do_enviar(contrato)["properties"]["proclamas"]["items"]
    assert set(montado) == set(item["properties"])
    assert set(montado["conjuge_1"]) == set(
        item["properties"]["conjuge_1"]["properties"])


# ---------------------------------------------------------- o vocabulario


def test_o_vocabulario_sai_da_nota_do_contrato(contrato):
    """Sexo, estado civil e tipo de casamento estao ESCRITOS na nota.

    Conferir o valor nao e inventar obrigacao: e ler o que esta la. Mandar
    `SOLTEIRO(A)` onde a Central espera `SOLTEIRO` e o defeito calado — ela
    aceita o lote e o proclama sai errado.
    """
    nota = contrato["info"]["description"]
    for palavra in API.ESTADOS_CIVIS:
        assert palavra in nota, f"«{palavra}» nao esta na nota do contrato"
    for palavra in API.TIPOS_DE_CASAMENTO:
        assert palavra in nota
    for palavra in API.SEXOS:
        assert palavra in nota


def test_as_convencoes_de_formato_sao_as_da_nota(contrato):
    """**CPF sem pontuacao e CEP COM hifen, na mesma mensagem.**

    E o tipo de detalhe que, escrito de memoria, sai errado num dos dois — e o
    errado nao estoura: chega torto do lado de la. Os dois exemplos estao na
    nota, e sao estes.
    """
    nota = contrato["info"]["description"]
    # O exemplo de CPF da nota é um número de 11 dígitos com DV válido, e não
    # se copia para cá (sanitização B3): basta provar que a nota o escreve CRU.
    import re as _re
    assert _re.search(r"(?<![\d.])\d{11}(?![\d.\-])", nota)  # CPF, so digitos
    assert "01227-200" in nota            # CEP, com hifen
    assert API.cpf_para_a_central("000.000.046-93") == "00000004693"
    assert API.cep_para_a_central("01227200") == "01227-200"
    assert "28/03/2025" in nota           # data dd/mm/aaaa
    assert API.data_para_a_central("2025-03-28") == "28/03/2025"


def test_o_brasil_e_076_na_lista_da_ONU(contrato):
    """A nota manda usar a lista M49; `76` seria outro pais."""
    assert API.BRASIL_M49 == "076"
    assert "m49" in contrato["info"]["description"].lower()


def test_a_conversao_de_estado_civil_tira_o_genero_entre_parenteses():
    """`SOLTEIRO(A)` e justamente o que o balcao digita."""
    assert API.estado_civil_para_a_central("Solteiro(a)") == "SOLTEIRO"
    assert API.estado_civil_para_a_central("Viúva") == "VIUVO"
    assert API.estado_civil_para_a_central("") == ""
    with pytest.raises(API.OnrcpnError):
        API.estado_civil_para_a_central("AMIGADO")


# ------------------------------------------------- o que o contrato NAO diz


def test_o_contrato_nao_declara_campo_obrigatorio_e_isso_fica_registrado(
        contrato):
    """Terceira vez: os `/v2` da CENPROT, a ONRTDPJ, e agora esta.

    **Nao se inventa obrigacao que o contrato nao declara.** No dia em que
    passarem a declarar, este teste fica vermelho e a conferencia da casa pode
    passar a segui-los em vez de decidir sozinha.
    """
    corpo = _corpo_do_enviar(contrato)
    assert "required" not in corpo
    item = corpo["properties"]["proclamas"]["items"]
    assert "required" not in item
    for p in contrato["paths"]["/api/proclama/enviar"]["post"]["parameters"]:
        assert not p.get("required"), (
            f"o parametro «{p.get('name')}» passou a ser obrigatorio no "
            f"contrato — a casa pode parar de decidir sozinha")


def test_o_200_traz_DUAS_LISTAS_e_nao_e_sinal_de_sucesso(contrato):
    """**O defeito mais grave desta integracao, e foi este teste que o achou.**

    Eu medi o contrato imprimindo so a `description` de cada resposta, li «OK»,
    e **conclui que o corpo nao era declarado**. Escrevi isso em tres lugares e
    fiz o codigo tratar todo 200 como sucesso.

    O esquema esta declarado, e diz o contrario: `proclamas.success` e
    `proclamas.error` sao **duas listas, por matricula**. O lote pode voltar
    aceito pela metade — com 200 —, e tratar isso como sucesso faria a casa
    dizer ao casal que o edital foi publicado quando ele nao foi.

    **Ausencia de esquema nao se conclui de uma leitura que so imprimiu a
    descricao** — e a licao e a mesma que este projeto ja tinha: procurei pelo
    nome errado e concluí que o dado nao existia.
    """
    r200 = contrato["paths"]["/api/proclama/enviar"]["post"]["responses"]["200"]
    dentro = r200["schema"]["properties"][API.CAMPO_DO_LOTE]["properties"]
    assert API.CAMPO_DOS_ACEITOS in dentro
    assert API.CAMPO_DOS_RECUSADOS in dentro
    assert API.CAMPO_DO_NUMERO_DO_LOTE in dentro
    # E cada item das duas listas e identificado pela MATRICULA.
    for lista in (API.CAMPO_DOS_ACEITOS, API.CAMPO_DOS_RECUSADOS):
        assert "matricula" in dentro[lista]["items"]["properties"]


def test_nao_ha_campo_protocolo_na_resposta_e_o_que_ha_e_o_batchId(contrato):
    """Chamar o `batchId` de protocolo seria batizar o que nao se mediu.

    O que a Central devolve para identificar o envio e o numero do LOTE, e nao
    um protocolo por proclama. A casa guarda esse numero e a tela diz que e
    isso — se um dia aparecer um campo `protocolo`, este teste fica vermelho.
    """
    r200 = contrato["paths"]["/api/proclama/enviar"]["post"]["responses"]["200"]
    dentro = r200["schema"]["properties"][API.CAMPO_DO_LOTE]["properties"]
    assert "protocolo" not in dentro
    assert API.CAMPO_DO_NUMERO_DO_LOTE == "batchId"


def test_o_recusado_diz_QUAL_CAMPO_esta_errado(contrato):
    """E o que serve ao balcao: a frase de fora e generica.

    O proprio exemplo do contrato mostra a especie de erro — «O campo sexo do
    genitor conjuge 2 se encontra invalido. Informar masculino ou feminino.
    Foi informado M» —, que e exatamente o que `sexo_para_a_central` converte.
    """
    r200 = contrato["paths"]["/api/proclama/enviar"]["post"]["responses"]["200"]
    erro = (r200["schema"]["properties"][API.CAMPO_DO_LOTE]
            ["properties"][API.CAMPO_DOS_RECUSADOS]["items"]["properties"])
    assert set(erro["errors"]["items"]["properties"]) == {"field", "message"}
    assert API.sexo_para_a_central("M") == "masculino"


def test_ler_o_lote_separa_o_aceito_do_recusado():
    lido = API.ler_o_lote({"proclamas": {
        "batchId": 7,
        "success": [{"matricula": "1" * 32, "status": "success"}],
        "error": [{"matricula": "2" * 32, "message": "the request failed",
                   "details": "Foi encontrado um ou mais erros",
                   "errors": [{"field": "sexo_genitor",
                               "message": "Informar masculino ou feminino"}]}]}})
    assert lido["entendi"] is True
    assert lido["lote"] == "7"
    assert lido["aceitos"] == ["1" * 32]
    assert lido["recusados"][0]["matricula"] == "2" * 32
    frase = API.motivo_da_recusa(lido["recusados"][0])
    assert "sexo_genitor" in frase and "masculino" in frase


def test_resposta_com_outra_forma_nao_vira_sucesso_nem_recusa():
    """«A Central recusou» e «eu nao sei ler o que ela mandou» sao coisas
    diferentes, e trata-las como a mesma e o zero com cara de medicao."""
    for estranha in ({"status": "success"}, {"proclamas": []}, "texto", None):
        lido = API.ler_o_lote(estranha)
        assert lido["entendi"] is False
        assert lido["aceitos"] == [] and lido["recusados"] == []


def test_o_recibo_tem_o_formato_declarado_de_duas_formas(contrato):
    """O contrato se contradiz, e isso fica dito em vez de resolvido a gosto.

    A descricao do caminho diz «pdf base64»; o esquema da resposta declara
    `recibo` como string com o exemplo `<<html string>>`. Escrever `.pdf` na fe
    da descricao faria a casa guardar um `.pdf` que e HTML.
    """
    item = contrato["paths"]["/api/proclama/recibo/:matricula"]["get"]
    assert "base64" in item["description"].lower()
    exemplo = item["responses"]["200"]["schema"]["properties"][
        API.CAMPO_DO_RECIBO]["example"]
    assert "html" in exemplo.lower()


def test_o_health_nao_declara_cabecalho_de_autenticacao(contrato):
    """E por isso `esta_no_ar()` nao pede token.

    **Medido, e nao deduzido**: em 03/09/2026 ele respondeu HTTP 200 com
    «Conexao com Oracle realizada com sucesso» a uma chamada sem cabecalho
    nenhum. O contrato concorda: o `health` nao tem parametro de authorization,
    e os outros dois tem.
    """
    health = contrato["paths"]["/api/proclama/health"]["get"]
    assert not health.get("parameters")
    for caminho in ("/api/proclama/enviar", "/api/proclama/recibo/:matricula"):
        item = contrato["paths"][caminho]
        operacao = item.get("post") or item.get("get")
        nomes = {p.get("name") for p in operacao.get("parameters", [])}
        assert "authorization" in nomes


# ------------------------------------------------- a autenticacao derivada


def test_o_Bearer_vem_do_contrato_das_CERTIDOES_e_isso_fica_dito(
        contrato, contrato_da_certidao):
    """O prefixo e DERIVADO, e nao medido — e a diferenca esta declarada.

    A nota do e-Proclamas manda usar «o mesmo modelo de autenticacao adotado no
    projeto das certidoes», e o contrato das certidoes declara `bearer`. Sao
    duas fontes que se apontam; nao ha uma chamada real desta serventia para
    conferir.

    Se a Central recusar com 401 tendo token valido, e `PREFIXO_DO_TOKEN` que
    se olha primeiro.
    """
    nota = contrato["info"]["description"]
    assert "certid" in nota.lower() and "autentica" in nota.lower()
    seguranca = contrato_da_certidao["components"]["securitySchemes"]
    assert seguranca["BearerAuth"]["scheme"] == "bearer"
    assert API.PREFIXO_DO_TOKEN == "Bearer "


def test_o_prefixo_E_O_MESMO_da_ONRTDPJ_por_motivos_diferentes():
    """Duas Centrais, mesmo cabeçalho `Authorization`, mesmo prefixo — e por
    RAZÕES DIFERENTES, o que é o que importa aqui.

    Aqui (ON-RCPN) o contrato **declara** `scheme: bearer`, e o prefixo é o
    que o próprio documento manda. Na ONRTDPJ o contrato declara `apiKey`
    puro — e eu escrevi, ao ler só isso, que o prefixo não entrava. **Estava
    errado**: testado contra a Central de verdade em 12/09/2026 com token
    real, sem `Bearer ` ela recusa (401) e com `Bearer ` aceita (200). As
    duas Centrais concordam no formato; só uma delas admite isso no
    contrato."""
    import onrtdpj_api as ONR
    assert ONR.CABECALHO_DO_TOKEN == API.CABECALHO_DO_TOKEN == "Authorization"
    assert ONR.PREFIXO_DO_TOKEN == API.PREFIXO_DO_TOKEN == "Bearer "


# ------------------------------------------------- as recusas da casa


def test_nao_se_manda_lote_vazio():
    """O contrato aceitaria, e a Central responderia 200 sem publicar nada."""
    with pytest.raises(API.OnrcpnError, match="proclama nenhum"):
        API.enviar("000000", [])


def test_nao_se_manda_sem_cns():
    with pytest.raises(API.OnrcpnError, match="CNS"):
        API.enviar("", [{"matricula": "1" * 32, "publicacao": True}])


def test_nao_se_manda_proclama_sem_matricula():
    """Sem ela o envio sobe e o recibo nunca mais e achado."""
    with pytest.raises(API.OnrcpnError, match="matrícula"):
        API.conferir_proclama({"publicacao": True})


def test_nao_se_manda_proclama_que_nao_faz_nada():
    """Dois booleanos falsos: a Central aceita e o escrevente acha que publicou."""
    with pytest.raises(API.OnrcpnError, match="ao menos uma"):
        API.conferir_proclama({"matricula": "1" * 32})


def test_pedir_recibo_sem_matricula_nao_sai_da_casa():
    with pytest.raises(API.OnrcpnError, match="matrícula"):
        API.recibo("")


def test_o_modulo_nao_lavra_ato():
    """Pela quinta vez — e aqui vale para o TRANSPORTE.

    Ele comunica o que a serventia ja decidiu e lavrou. Quem publica o edital e
    quem lanca no Livro D e o RCPN.
    """
    proibidos = ("lavrar", "publicar_edital", "numerar", "selar", "cobrar",
                 "assinar")
    for nome in dir(API):
        if nome.startswith("_"):
            continue
        for palavra in proibidos:
            assert palavra not in nome.lower(), (
                f"«{nome}» tem cara de ato — este modulo e transporte")
