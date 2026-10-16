"""O transporte do ONR, conferido CONTRA O CONTRATO GUARDADO.

**ESTES TESTES ABREM O `openapi.json` E COMPARAM** — inclusive para provar que
o arquivo **como o ONR o publica nao e JSON valido**, que e a razao de haver
duas copias.

E a licao da CENPROT (seis defeitos meus so apareceram quando o teste abriu o
contrato), da ONRTDPJ, do e-Proclamas e da Certidao Eletronica.

O contrato mora em `FONTES_EXTERNAS/onr_ri/`, **fora** da pasta que viaja no
`.cgu`. Quando ele nao esta na maquina, estes testes **pulam**.

NENHUM TESTE DAQUI FALA COM O ONR.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import centrais_cred as CRED
import onr_api as API

PROJETO = RAIZ.parent.parent
CONTRATO = PROJETO / API.CONTRATO_NO_PROJETO
COMO_ELES_PUBLICAM = PROJETO / API.CONTRATO_COMO_ELES_PUBLICAM


def _abrir(caminho: Path):
    if not caminho.is_file():
        pytest.skip(f"o contrato nao esta nesta maquina: {caminho}")
    return json.loads(caminho.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def contrato():
    return _abrir(CONTRATO)


def _operacoes(doc):
    """(metodo, caminho) -> operacao, para as 53."""
    saida = {}
    for c, ops in doc["paths"].items():
        for m, op in ops.items():
            if m in ("get", "post", "put", "patch", "delete"):
                saida[(m.upper(), c)] = op
    return saida


# ------------------------------------------------------- as duas copias


def test_o_arquivo_que_eles_publicam_NAO_e_json_valido():
    """**E por isso que ha duas copias.** Duas virgulas antes de fecho, e
    qualquer parser recusa o arquivo inteiro.

    Este teste fica **vermelho quando corrigirem** — e nesse dia a copia limpa
    deixa de ser necessaria. E a decisao do `http://` no WSDL da CRA.
    """
    if not COMO_ELES_PUBLICAM.is_file():
        pytest.skip("o contrato original nao esta nesta maquina")
    with pytest.raises(ValueError):
        json.loads(COMO_ELES_PUBLICAM.read_text(encoding="utf-8"))


def test_a_copia_limpa_e_json_valido(contrato):
    assert contrato["openapi"] == "3.0.3"
    assert "Registro de Im" in contrato["info"]["title"]


def test_as_duas_copias_sao_o_MESMO_contrato(contrato):
    """A limpa nao pode ter perdido nada: a diferenca sao duas virgulas.

    > **E O PRIMEIRO TESTE QUE EU ESCREVI AQUI COMPARAVA BYTES**, e passaria
    > por acaso ou falharia por acaso: a copia limpa foi **reserializada**,
    > com outra indentacao, de modo que o tamanho difere em 86.507 bytes sem
    > que o CONTEUDO mude. **Comparar a forma onde o que importa e o conteudo
    > mede a coisa errada** — a licao do teste de espaco que colapsava espaco,
    > pelo outro lado.

    O que se compara e o **objeto**: tira-se a virgula antes de fecho do
    original e o resultado tem de ser identico ao da copia limpa.
    """
    import re
    if not COMO_ELES_PUBLICAM.is_file():
        pytest.skip("o contrato original nao esta nesta maquina")
    bruto = COMO_ELES_PUBLICAM.read_text(encoding="utf-8")
    remendado = re.sub(r",(\s*[}\]])", r"\g<1>", bruto)
    assert json.loads(remendado) == contrato, (
        "a copia limpa deixou de ser o mesmo contrato que o ONR publica")


# ------------------------------------------------------------- os endereços


def test_os_DOIS_ambientes_vem_do_contrato(contrato):
    """**E o oposto do ON-RCPN, na FORMA e não no fundo.** Aqui os dois
    endereços saem do `servers` do contrato. Lá o contrato publicado traz só o
    de homologação — e o de produção **existe**, medido em 18/09/2026, e não é
    citado em contrato nenhum: é por medição, e não por declaração, que se sabe
    dele. O que isso muda aqui é a régua, e ela continua a mesma: **endereço que
    não se mediu, não se escreve**."""
    declarados = [s["url"] for s in contrato["servers"]]
    assert set(declarados) == set(API.BASE_POR_AMBIENTE.values())
    assert API.BASE_POR_AMBIENTE[CRED.PRODUCAO] in declarados
    assert API.BASE_POR_AMBIENTE[CRED.HOMOLOGACAO] in declarados


def test_a_casa_fala_com_a_producao_e_os_testes_seguem_pelo_nome():
    # Até 15/10/2026 a casa começava na homologação. Ordem do oficial: só a
    # produção, com ela já configurada; o endereço de testes fica no código.
    assert API.ambiente_da_casa() == CRED.PRODUCAO
    assert not API.base_do_ambiente().startswith("https://testes-api.")
    assert API.base_do_ambiente(CRED.HOMOLOGACAO).startswith("https://testes-api.")


def test_o_https_e_forcado():
    with pytest.raises(API.OnrError):
        API.partes("http://api.registrodeimoveis.org.br")
    assert API.partes(API.BASE_POR_AMBIENTE[CRED.PRODUCAO])[0] == \
        "api.registrodeimoveis.org.br"


# ------------------------------------------------------------- os caminhos


def test_as_53_operacoes_existem_no_contrato(contrato):
    ops = _operacoes(contrato)
    for qual, caminho in API.CAMINHO.items():
        chave = (API.METODO_DO_CAMINHO[qual],
                 caminho.replace(":hash", "{hash}"))
        # os nomes dos pedacos variam no contrato; compara-se por forma
        achou = any(
            m == chave[0] and _mesma_forma(c, caminho)
            for (m, c) in ops)
        assert achou, f"{qual}: {API.METODO_DO_CAMINHO[qual]} {caminho}"


def _mesma_forma(do_contrato: str, nosso: str) -> bool:
    """`/v1/edital/{numeroEdital}` e `/v1/edital/:numero` sao o mesmo caminho."""
    import re
    a = re.sub(r"\{[^}]+\}", "{}", do_contrato)
    b = re.sub(r":\w+", "{}", nosso)
    return a == b


def test_nao_sobra_nem_falta_operacao(contrato):
    assert len(API.CAMINHO) == len(_operacoes(contrato)) == 53
    assert len(contrato["paths"]) == 39
    assert set(API.CAMINHO) == set(API.METODO_DO_CAMINHO)


def test_os_ligados_sao_um_subconjunto_declarado():
    """**25 das 53** (marco B: +SAEC/protocolo/cobranca) — a decisao da ONRTDPJ (10 de 81) pela segunda vez. Os
    outros ficam declarados para ninguem os reinventar.

    > **Comecaram 20, e o varredor de funcao orfa cortou quatro funcoes.** Eu
    > havia escrito `atos_do_indicador`, `excluir_indicador`,
    > `retificar_edital` e `detalhes_do_protocolo` «para o caso de», e nenhuma
    > tela as chamava. **Foram apagadas, e nao desligadas** — o caminho fica
    > declarado em `CAMINHO`.
    """
    assert set(API.CAMINHOS_LIGADOS) <= set(API.CAMINHO)
    assert len(API.CAMINHOS_LIGADOS) == 25
    # E os apagados continuam DECLARADOS, para ninguem os reinventar:
    assert set(API.CAMINHOS_APAGADOS_MAS_DECLARADOS) <= set(API.CAMINHO)
    assert not (set(API.CAMINHOS_APAGADOS_MAS_DECLARADOS)
                & set(API.CAMINHOS_LIGADOS))


def test_caminho_declarado_e_nao_ligado_recusa_ser_chamado():
    with pytest.raises(API.OnrError) as erro:
        API._bater("cobranca_devolver_pix", hash="x")
    assert "nao esta ligado" in str(erro.value).replace("ã", "a") \
        or "não está ligado" in str(erro.value)


# ------------------------------------------------------------ a seguranca


def test_sao_DOIS_mecanismos_de_autenticacao(contrato):
    """48 operacoes com `Bearer` e **4 com um cabecalho `token`** — e o token
    daquelas e o DAQUELE protocolo, e nao o da casa."""
    import collections
    usados = collections.Counter()
    for op in _operacoes(contrato).values():
        for bloco in (op.get("security") or []):
            # `bloco` e `{"bearerAuth": []}` — o Counter tem de contar as
            # CHAVES, e nao somar as listas de escopo.
            usados.update(bloco.keys())
    assert usados["bearerAuth"] == 48
    assert usados["headerAuth"] == 4
    assert contrato["components"]["securitySchemes"]["headerAuth"] == {
        "type": "apiKey", "in": "header", "name": "token"}
    assert API.CABECALHO_DO_TOKEN_DO_PROTOCOLO == "token"


def test_as_quatro_do_headerAuth_sao_as_de_detalhe_do_protocolo(contrato):
    do_contrato = {
        c for (m, c), op in _operacoes(contrato).items()
        if any("headerAuth" in b for b in (op.get("security") or []))}
    nossos = {API.CAMINHO[q].replace(":numero", "{numeroProtocolo}")
              for q in API.CAMINHOS_COM_TOKEN_DO_PROTOCOLO}
    assert do_contrato == nossos


def test_os_dois_caminhos_de_cobranca_do_edital_nao_declaram_seguranca(contrato):
    """**Omissao do contrato, e nao caminho aberto** — mesma Central, mesma
    credencial. Fica vermelho quando corrigirem."""
    sem = {(m, c) for (m, c), op in _operacoes(contrato).items()
           if not op.get("security")}
    assert sem == {
        ("POST", "/v1/auth/token"),
        ("POST", "/v1/edital/cobranca"),
        ("PATCH", "/v1/edital/cobranca/{numeroDocumento}")}
    assert API.CAMINHOS_SEM_SEGURANCA_DECLARADA == frozenset(
        {"edital_cobranca", "edital_cobranca_atualizar"})


def test_o_oauth2_declarado_aponta_para_lugar_nenhum(contrato):
    """Sobra de configuracao deles. Vale o `/v1/auth/token`."""
    fluxo = contrato["components"]["securitySchemes"]["oauth2"]["flows"]
    assert fluxo["clientCredentials"]["tokenUrl"] == \
        "https://teste/oauth2/token"


# ------------------------------------------------------------ o token


def test_o_corpo_da_autenticacao_e_FORMULARIO_e_nao_json(contrato):
    """`application/x-www-form-urlencoded`. Mandar JSON ali devolve 422."""
    rb = contrato["paths"]["/v1/auth/token"]["post"]["requestBody"]
    assert list(rb["content"]) == [API.TIPO_DO_FORMULARIO]


def test_os_tres_obrigatorios_da_autenticacao(contrato):
    esquema = contrato["components"]["schemas"]["AutenticacaoRequest"]
    assert set(esquema["required"]) == {
        "client_id", "client_secret", "grant_type"}
    assert API.GRANT_DA_CASA in \
        esquema["properties"]["grant_type"]["enum"]


def test_a_resposta_da_autenticacao_traz_expires_in(contrato):
    esquema = contrato["components"]["schemas"]["AutenticacaoDataResponse"]
    assert set(esquema["required"]) == {
        "access_token", "expires_in", "token_type"}
    assert esquema["properties"]["token_type"]["enum"] == ["Bearer"]
    assert API.PREFIXO_DO_TOKEN == "Bearer "


def test_o_token_se_guarda_ate_perto_de_vencer(monkeypatch):
    """Pedir token a cada chamada seria uma viagem a mais em cada clique."""
    API.esquecer_o_token()
    pedidos = []

    def falso(metodo, caminho, **k):
        pedidos.append(caminho)
        return {"status": 200, "texto": "", "bytes": b"",
                "json": {"access_token": "abc", "expires_in": 600,
                         "token_type": "Bearer"}}
    monkeypatch.setattr(API, "_bater_cru", falso)
    monkeypatch.setattr(API, "credencial", lambda *a, **k: ("id", "seg"))

    assert API.token(CRED.HOMOLOGACAO, agora=1000.0) == "abc"
    assert API.token(CRED.HOMOLOGACAO, agora=1100.0) == "abc"
    assert len(pedidos) == 1, "pediu token de novo com o antigo valendo"
    # Perto de vencer (600 - 60 de margem), pede outro:
    assert API.token(CRED.HOMOLOGACAO, agora=1000.0 + 600 - 30) == "abc"
    assert len(pedidos) == 2
    API.esquecer_o_token()


def test_sem_expires_in_o_token_NAO_se_guarda(monkeypatch):
    """Guardar «para sempre» faria a casa mandar token vencido sem saber."""
    API.esquecer_o_token()
    pedidos = []

    def falso(metodo, caminho, **k):
        pedidos.append(caminho)
        return {"status": 200, "texto": "", "bytes": b"",
                "json": {"access_token": "abc", "token_type": "Bearer"}}
    monkeypatch.setattr(API, "_bater_cru", falso)
    monkeypatch.setattr(API, "credencial", lambda *a, **k: ("id", "seg"))
    API.token(CRED.HOMOLOGACAO, agora=1000.0)
    API.token(CRED.HOMOLOGACAO, agora=1001.0)
    assert len(pedidos) == 2
    API.esquecer_o_token()


def test_a_credencial_recusada_diz_onde_conferir(monkeypatch):
    API.esquecer_o_token()
    monkeypatch.setattr(API, "credencial", lambda *a, **k: ("id", "seg"))
    monkeypatch.setattr(API, "_bater_cru", lambda *a, **k: {
        "status": 401, "json": {"descricao": "credencial invalida"},
        "texto": "", "bytes": b""})
    with pytest.raises(API.OnrError) as erro:
        API.token(CRED.HOMOLOGACAO, agora=1.0)
    assert "client_id" in str(erro.value)
    API.esquecer_o_token()


def test_o_ONR_e_a_quinta_central_e_guarda_um_PAR():
    """**O contrato declara o que fazer com o par**, e por isso ele e `PAR` —
    ao contrario da ON-RCPN, cujo token e o do USUARIO, de cinco minutos, e sai
    de um `authorization_code` (manual do IdRC, medido em 18/09/2026). `PAR` faz
    o sistema MINAR o token sozinho, e la o caminho medido nao permite isso —
    ver `centrais_cred.FORMA_DA_CENTRAL`."""
    assert CRED.FORMA_DA_CENTRAL[CRED.ONR] == CRED.PAR
    assert CRED.ARQUIVO_DA_CENTRAL[CRED.ONR] == "onr.cred"
    assert CRED.rotulos_do_par(CRED.ONR) == ("client_id", "client secret")
    assert CRED.rotulos_do_par(CRED.CRA) == CRED.PAR_PADRAO
    # O contrato declara os DOIS ambientes, e os dois seguem no transporte;
    # a tela, desde 15/10/2026, oferece só a produção (ordem do oficial).
    assert CRED.ambientes_de(CRED.ONR) == (CRED.PRODUCAO,)
    assert set(API.BASE_POR_AMBIENTE) >= {CRED.HOMOLOGACAO, CRED.PRODUCAO}


# ------------------------------------------------------- os vocabularios


def test_o_enum_deste_contrato_e_DOCUMENTACAO_e_nao_valor(contrato):
    """`type: integer` com `enum: ["64 = Casa"]`. Quem mandar a string manda
    texto onde a Central espera numero."""
    ir = contrato["components"]["schemas"]["indicadorRealRequest"]["properties"]
    assert ir["tipoImovel"]["type"] == "integer"
    assert ir["tipoImovel"]["enum"][0].startswith("64 = ")


def test_codigos_do_enum_parte_a_lista():
    assert API.codigos_do_enum(["64 = Casa", "65 = Apto"]) == {
        64: "Casa", 65: "Apto"}
    # Linha fora da forma **e ignorada**, e nao vira codigo inventado:
    assert API.codigos_do_enum(["lixo", "7 = Sete"]) == {7: "Sete"}
    assert API.codigos_do_enum(None) == {}


@pytest.mark.parametrize("campo,nosso", [
    ("tipoRegistro", "TIPOS_DE_REGISTRO"),
    ("situacaoConstrucao", "SITUACOES_DE_CONSTRUCAO"),
    ("localizacao", "LOCALIZACOES"),
])
def test_os_vocabularios_transcritos_batem(contrato, campo, nosso):
    ir = contrato["components"]["schemas"]["indicadorRealRequest"]["properties"]
    assert API.codigos_do_enum(ir[campo]["enum"]) == getattr(API, nosso)


def test_a_localizacao_pula_o_dois(contrato):
    """Catalogo oficial pula numero — a licao dos catalogos do IBGE. Quem
    preencher a sequencia obvia acerta o tipo e erra o conteudo."""
    assert set(API.LOCALIZACOES) == {1, 3}
    assert 2 not in API.LOCALIZACOES
    assert API.LOCALIZACAO_PULA_O_DOIS is True


def test_os_129_tipos_de_logradouro_batem_com_o_contrato(contrato):
    """Os 129 estao transcritos, e `tools/gerar_logradouros.py` os gera.

    > **E EU TINHA ESCRITO O CONTRARIO AQUI, e a mudanca fica visivel.** O
    > primeiro teste deste arquivo afirmava que os 129 **nao** seriam
    > transcritos, «porque a casa guarda o logradouro como texto e nao tem de
    > onde tirar o codigo». **A segunda metade era falsa**: o texto que a casa
    > guarda comeca justamente pelo tipo — «Rua das Flores» —, e os NOMES do
    > enum sao o de-para. A tabela serve aos dois lados do contrato: o codigo
    > no indicador real e o nome no edital.
    """
    ir = contrato["components"]["schemas"]["indicadorRealRequest"]["properties"]
    assert len(ir["tipoLogradouro"]["enum"]) == 129
    assert API.codigos_do_enum(ir["tipoLogradouro"]["enum"]) == \
        API.TIPOS_DE_LOGRADOURO


def test_o_unico_nome_repetido_do_catalogo_esta_declarado():
    """«Alameda» e 4 **e** 645 no catalogo deles. Medido, e nao suposto — e
    para o caminho contrario fica o menor, que e o da sequencia."""
    assert API.NOMES_REPETIDOS_NO_CATALOGO == {"Alameda": (4, 645)}
    assert API.TIPOS_DE_LOGRADOURO[4] == API.TIPOS_DE_LOGRADOURO[645] == \
        "Alameda"
    assert API.CODIGO_DO_LOGRADOURO["alameda"] == 4
    # E nao ha outro nome repetido que tenha escapado:
    import collections
    contagem = collections.Counter(API.TIPOS_DE_LOGRADOURO.values())
    assert {n for n, q in contagem.items() if q > 1} == \
        set(API.NOMES_REPETIDOS_NO_CATALOGO)


def test_o_glyph_corrompido_do_catalogo_esta_declarado():
    """**O contrato deles escreve «Ýrea» onde quer dizer «Área»**, e o glifo
    U+00DD (Ý) **nao existe em portugues** — o que faz dele, sozinho, prova de
    corrupcao, sem precisar acreditar em mim.

    Medido em 15/09/2026: dos 129 nomes, **exatamente dois** o carregam, o 472
    e o 654, e sao a MESMA palavra corrompida. E a prosa do proprio contrato
    fecha a leitura — o campo `area` esta descrito como «Ýrea em metros
    quadrados do imovel rural…», onde `Ýrea` so pode ser «Area».

    Ate aqui este codigo **existia e a regua nao o alcancava**: `sem_acento`
    levava «Ýrea» a `yrea`, a casa escrevia «Area», e os dois nunca se
    encontravam. Como o `tipoLogradouro` e OBRIGATORIO no indicador real, o ato
    inteiro era recusado **por um caractere**.
    """
    assert API.APELIDOS_DO_LOGRADOURO == {"area": 472, "area especial": 654}
    # A tabela continua FIEL ao contrato: quem for conferir acha igual, e o
    # edital manda o nome exatamente como o outro lado o escreveu.
    assert API.TIPOS_DE_LOGRADOURO[472] == "Ýrea"
    assert API.TIPOS_DE_LOGRADOURO[654] == "Ýrea Especial"
    # E a casa alcanca o codigo escrevendo o que ela escreve.
    assert API.CODIGO_DO_LOGRADOURO[API.sem_acento("Área")] == 472
    assert API.CODIGO_DO_LOGRADOURO[API.sem_acento("ÁREA ESPECIAL")] == 654
    # O caminho pelo nome corrompido continua de pe, e nao foi substituido.
    assert API.CODIGO_DO_LOGRADOURO["yrea"] == 472


def test_nenhum_nome_com_glifo_estranho_fica_sem_declarar():
    """O guarda: se o ONR acrescentar outro nome com letra que nao existe em
    portugues, isto fica vermelho — em vez de o codigo nascer inalcancavel,
    que foi como o 472 viveu ate 15/09/2026.

    O `Ü` entra no conjunto de proposito: ele **é** letra do portugues, da
    grafia anterior ao acordo de 2009 («qüinqüênio»), e nao é corrupcao.
    """
    do_portugues = set("ABCDEFGHIJKLMNOPQRSTUVWXYZÜÀÁÂÃÉÊÍÓÔÕÚÇ")
    corrompidos = {
        nome for nome in API.TIPOS_DE_LOGRADOURO.values()
        if {c for c in nome.upper() if c.isalpha()} - do_portugues
    }
    assert corrompidos == {"Ýrea", "Ýrea Especial"}


def test_o_de_para_do_logradouro_ignora_acento_e_caixa():
    """O logradouro chega escrito de todo jeito no balcao."""
    assert API.CODIGO_DO_LOGRADOURO[API.sem_acento("PRAÇA")] == \
        API.CODIGO_DO_LOGRADOURO["praca"]
    assert API.sem_acento("Avenida") == "avenida"


# ------------------------------------------------- o que ele recusa sem rede


def test_o_caminho_com_pedaco_vazio_e_recusado():
    with pytest.raises(API.OnrError):
        API._endereco("edital", numero="")
    assert API._endereco("edital", numero="123") == "/v1/edital/123"


def test_os_detalhes_do_protocolo_exigem_o_token_DAQUELE_protocolo():
    """Mandar o `Bearer` da casa ali devolve 401 sem dizer por que."""
    with pytest.raises(API.OnrError) as erro:
        API._bater("protocolo_detalhes_v2", numero="1", token_do_protocolo="")
    assert "protocolo" in str(erro.value)


def test_o_indicador_real_declara_doze_obrigatorios(contrato):
    """**Quem os confere e o dominio**, com a ficha do imovel a vista — aqui so
    se registra quantos sao, para o teste avisar se mudarem."""
    esquema = contrato["components"]["schemas"]["indicadorRealRequest"]
    assert set(esquema["required"]) == {
        "cns", "numeroRegistro", "tipoImovel", "cep", "tipoLogradouro",
        "logradouro", "numero", "bairro", "cidade", "uf",
        "situacaoConstrucao", "localizacao"}


def test_o_edital_declara_tres_obrigatorios(contrato):
    esquema = contrato["components"]["schemas"]["editalRequest"]
    assert set(esquema["required"]) == {
        "tipoEdital", "intimados", "dadosServentia"}


# ------------------------------------------------ a leitura da resposta


def _resposta(status, corpo):
    return {"status": status, "json": corpo, "texto": json.dumps(corpo),
            "bytes": b""}


def test_o_422_traz_o_campo_que_o_onr_apontou():
    """`ErroModel` declara `campos`, e e ele que diz QUAL campo esta errado."""
    with pytest.raises(API.OnrRecusou) as erro:
        API._resposta_ou_erro(_resposta(422, {
            "codigo": 10, "descricao": "dados invalidos",
            "campos": {"cep": "obrigatorio"}}), "enviar")
    assert "dados invalidos" in str(erro.value)
    assert "cep" in str(erro.value)


def test_o_401_manda_conferir_a_credencial():
    with pytest.raises(API.OnrError) as erro:
        API._resposta_ou_erro(_resposta(401, {"descricao": "x"}), "enviar")
    assert "Configura" in str(erro.value)


def test_o_204_passa_por_sucesso():
    """O `DELETE` do edital e do indicador responde sem corpo."""
    assert API._resposta_ou_erro(
        {"status": 204, "json": None, "texto": "", "bytes": b""},
        "cancelar") == ""


def test_o_data_de_dentro_se_desembrulha_sem_inventar():
    assert API._dados({"data": [1, 2]}) == [1, 2]
    assert API._dados({"outro": 1}) == {"outro": 1}
    assert API._dados([1]) == [1]
