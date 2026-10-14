"""O TRANSPORTE DA CENTRAL ONRTDPJ, conferido CONTRA O CONTRATO.

POR QUE ESTES TESTES ABREM O `swagger_v1.json`
    Na integração da CENPROT, **seis defeitos meus só apareceram quando o teste
    abriu o contrato** — três convenções de data escritas iguais, doze campos
    obrigatórios conferidos como dois, o corpo embrulhado num caminho e cru nos
    outros. Nenhum deles apareceu na releitura, e **os seis falhariam calados**.

    Então aqui a régua é a mesma: o teste lê o contrato guardado em
    `FONTES_EXTERNAS/onrtdpj/swagger_v1.json` e compara caminho por caminho,
    método por método, campo por campo.

O QUE ELES GUARDAM
      - os dez caminhos que o módulo usa **existem no contrato**, com o método
        certo — caminho inventado devolve 404, e 404 numa integração nova
        parece «não há nada hoje»;
      - os campos vão na **grafia do contrato** (maiúscula inicial) — JSON é
        sensível a caixa e a Central **ignora o que não conhece**, de modo que
        um registro subiria vazio com HTTP 200;
      - o token vai no cabeçalho `Authorization`, **com o prefixo `Bearer `**
        — e isto **não é o que o contrato diz**: ele declara `apiKey`, sem
        `bearer`, e a suposição de que por isso o prefixo não entrava foi
        testada contra a Central de verdade em 12/09/2026 e desmentida (401
        sem o prefixo, 200 com ele, mesmo token). O contrato descreve o TIPO
        do campo, não o FORMATO do valor que a Central espera dentro dele;
      - **o `https` se força**, porque o token viaja nele;
      - o módulo **não lavra ato nenhum** — pela quinta vez neste projeto;
      - e o que o contrato **não** declara fica declarado como não declarado:
        `required` vem vazio nas cem definições, e não se inventa obrigação.

SE O CONTRATO NÃO ESTIVER NA MÁQUINA
    Os testes que precisam dele **pulam**, e dizem onde buscá-lo. `FONTES_
    EXTERNAS` não viaja no `.cgu`: numa máquina que só tem o pacote, o arquivo
    não existe — e teste vermelho por falta de material de desenvolvimento é
    alarme que ninguém sabe apagar.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import centrais_cred as CRED
import onrtdpj_api as API

# O projeto é o avô da pasta do servidor: .../CartorioGestao/SERVIDOR/INSTALAR…
CONTRATO = RAIZ.parent.parent / API.CONTRATO_NO_PROJETO

precisa_do_contrato = pytest.mark.skipif(
    not CONTRATO.is_file(),
    reason=f"o contrato da ONRTDPJ não está em {CONTRATO} — ele mora em "
           f"FONTES_EXTERNAS, que não viaja no pacote. Baixe de "
           f"https://centralinside.rtdbrasil.org.br/swagger/docs/v1")


@pytest.fixture(scope="module")
def contrato() -> dict:
    return json.loads(CONTRATO.read_text(encoding="utf-8"))


# ------------------------------------------- o endereço e a autenticação


@precisa_do_contrato
def test_a_base_e_a_do_contrato(contrato):
    """**O endereço não se escolhe: sai do `host` e do `schemes`.**"""
    assert contrato["host"] in API.BASE
    assert contrato["schemes"] == ["https"]
    assert API.BASE.startswith("https://")


@precisa_do_contrato
def test_o_contrato_declara_UM_host_so(contrato):
    """**Não há homologação, e não se inventa uma.** Um endereço de teste
    inventado é o pior tipo de número inventado: quem o usasse acharia que está
    testando enquanto fala com a Central de verdade."""
    assert isinstance(contrato["host"], str)
    assert CRED.ambientes_de(CRED.ONRTDPJ) == (CRED.PRODUCAO,)


@precisa_do_contrato
def test_o_token_vai_no_cabecalho_que_o_contrato_declara(contrato):
    esquema = contrato["securityDefinitions"]["Token"]
    assert esquema["type"] == "apiKey"
    assert esquema["in"] == "header"
    assert esquema["name"] == API.CABECALHO_DO_TOKEN


def test_o_token_vai_COM_a_palavra_Bearer():
    """**Testado contra a Central de verdade em 12/09/2026, com token real do
    oficial**: sem `Bearer ` ela devolve 401 «Não foi possível validar seu
    acesso»; com `Bearer ` devolve 200 com os dados da serventia (CNS 000000).
    O contrato declara `apiKey` e não `bearer` — isso descreve o tipo do
    campo, não o formato do valor que a Central espera dentro dele, e a
    suposição de que «apiKey» quer dizer «sem prefixo» estava errada."""
    fonte = (RAIZ / "onrtdpj_api.py").read_text(encoding="utf-8")
    assert 'PREFIXO_DO_TOKEN = "Bearer "' in fonte
    linha = [x for x in fonte.splitlines()
             if "CABECALHO_DO_TOKEN:" in x and "token(" in x]
    assert linha, "não achei onde o token entra no cabeçalho"
    assert "PREFIXO_DO_TOKEN" in "".join(linha)


@precisa_do_contrato
def test_o_contrato_declara_o_esquema_e_NAO_o_aplica(contrato):
    """**O que o contrato NÃO diz, dito.** Não há `security` no documento nem
    em nenhuma das operações — logo **quais chamadas exigem o token não está no
    contrato**, está na prosa da página. Se um dia passarem a declarar, este
    teste fica vermelho e alguém relê a decisão de mandar o cabeçalho em todas.
    """
    assert "security" not in contrato
    com_security = [f"{m.upper()} {c}"
                    for c, item in contrato["paths"].items()
                    for m, op in item.items() if "security" in op]
    assert not com_security, (
        f"o contrato passou a declarar `security` em {com_security} — releia "
        f"se ainda vale mandar o cabeçalho em todas as chamadas")


# ------------------------------------------------- os caminhos existem


@precisa_do_contrato
def test_os_dez_caminhos_existem_no_contrato(contrato):
    """**Caminho escrito à mão que a Central não conhece devolve 404** — e 404
    numa integração nova parece «não há nada hoje»."""
    faltando = [f"{API.METODO_DO_CAMINHO[chave]} {caminho}"
                for chave, caminho in API.CAMINHO.items()
                if caminho not in contrato["paths"]
                or API.METODO_DO_CAMINHO[chave].lower()
                not in contrato["paths"][caminho]]
    assert not faltando, f"não existem no contrato: {faltando}"


@precisa_do_contrato
def test_o_modulo_declara_o_metodo_de_cada_caminho(contrato):
    assert set(API.CAMINHO) == set(API.METODO_DO_CAMINHO)


@precisa_do_contrato
def test_o_modulo_usa_uma_FATIA_do_contrato_e_diz_quantos_sao(contrato):
    """São 10 de 81. Declarar os 81 daria oitenta e uma funções sem chamador —
    o defeito mais repetido deste projeto. Se o contrato encolher a ponto de os
    números se aproximarem, o comentário do módulo deixa de ser verdade."""
    assert len(API.CAMINHO) == 10
    assert len(contrato["paths"]) >= 60


# ---------------------------------------- os campos, na grafia do contrato


@precisa_do_contrato
def test_os_campos_do_registro_sao_os_do_contrato(contrato):
    """**JSON é sensível a caixa, e a Central ignora o que não conhece**:
    `protocolo` em vez de `Protocolo` subiria um registro **vazio**, com HTTP
    200 e nada acontecendo do lado de lá."""
    esquema = contrato["definitions"]["RegistrarPedido"]["properties"]
    assert set(API.CAMPOS_DO_REGISTRO) == set(esquema)


@precisa_do_contrato
def test_os_campos_da_nota_devolutiva_sao_os_do_contrato(contrato):
    esquema = contrato["definitions"]["CadastroExigencia"]["properties"]
    assert set(API.CAMPOS_DA_NOTA) == set(esquema)


@precisa_do_contrato
def test_o_orcamento_e_o_cancelamento_usam_os_nomes_do_contrato(contrato):
    orcamento = contrato["definitions"]["CadastroOrcamento"]["properties"]
    assert {"Protocolo", "ValorOrcamento"} == set(orcamento)
    cancelar = contrato["definitions"]["CancelarProtocoloModel"]["properties"]
    assert {"Protocolo", "MotivoCancelamento"} == set(cancelar)


@precisa_do_contrato
def test_NENHUM_corpo_declara_campo_obrigatorio(contrato):
    """**O que o contrato não declara, o módulo não inventa.**

    Medido: `required` vem vazio nas cem definições. É a mesma situação dos
    `/v2` da CENPROT. As recusas deste módulo — protocolo, descrição da nota,
    motivo do cancelamento — são **regra da casa**, e o código diz isso.

    Se um dia a Central passar a declarar obrigatórios, este teste fica
    vermelho e a conferência passa a poder sair do contrato, que é melhor.
    """
    com_obrigatorio = {nome: e["required"]
                       for nome, e in contrato["definitions"].items()
                       if e.get("required")}
    assert not com_obrigatorio, (
        f"o contrato passou a declarar obrigatórios: {com_obrigatorio}. "
        f"Confira-os em vez de manter as recusas só como regra da casa.")


@precisa_do_contrato
def test_o_upload_e_o_catalogo_ficam_DECLARADOS_e_sem_funcao(contrato):
    """**Caminho declarado, e função apagada — de propósito.**

    `/api/arquivo` sobe um arquivo e devolve o id que o `RegistrarPedido`
    aceita em `ArquivoId`. **Este sistema não tem o que subir**: não há molde
    `.odt` do registro do RCPJ/RTD, e portanto não há documento registrado para
    mandar de volta. Escrever a função seria a peça pronta que ninguém chama, e
    é o defeito mais repetido deste projeto.

    `/api/pedido/tiposregistro` é o catálogo de tipos da Central; nenhuma tela
    o pede hoje, e copiá-lo para dentro do código seria pior — ele muda lá.

    **O caminho fica escrito para ninguém o reinventar achando que sumiu**: é o
    precedente de `cenprot_api.renegociacoes`, apagada em 02/09/2026 com o
    caminho mantido em `CAMINHO`.

    E o contrato declara os dois, então o teto continua valendo.
    """
    for chave in ("arquivo", "tipos_de_registro"):
        assert API.CAMINHO[chave] in contrato["paths"]
        assert not hasattr(API, "enviar_arquivo")
        assert not hasattr(API, "tipos_de_registro")


@precisa_do_contrato
def test_o_erro_de_digitacao_do_upload_fica_REGISTRADO(contrato):
    """**O contrato declara `consumes: ["application/form-data"]`, e esse tipo
    não existe.** O parâmetro é `in: formData, type: file`, e arquivo em
    formulário viaja em `multipart/form-data`.

    Nada nesta casa manda arquivo hoje — mas quando alguém for mandar, o
    engano está aqui esperando. **Quando a Central corrigir, este teste fica
    vermelho**, e é assim que a correção não passa despercebida: é a mesma
    decisão do `http://` no WSDL da CRA.
    """
    op = contrato["paths"]["/api/arquivo"]["post"]
    assert op["consumes"] == ["application/form-data"], (
        "a Central corrigiu o `consumes` do upload — quem for escrever o envio "
        "de arquivo já pode confiar no que o contrato diz")
    param = op["parameters"][0]
    assert param["name"] == "file" and param["in"] == "formData"
    assert param["type"] == "file"


@precisa_do_contrato
def test_a_lista_de_pendentes_aceita_os_dois_filtros_do_contrato(contrato):
    op = contrato["paths"]["/api/pedido/pendentes"]["get"]
    assert {p["name"] for p in op["parameters"]} == {"servicoId", "situacaoId"}
    assert all(p["in"] == "query" for p in op["parameters"])


@precisa_do_contrato
def test_a_nota_devolutiva_lida_e_a_v2_que_traz_o_LINK(contrato):
    """Sem o link, a nota que a Central guarda não se lê daqui."""
    assert API.CAMINHO["notas_do_protocolo"].startswith("/api/v2/")
    resumo = contrato["paths"]["/api/v2/notadevolutiva/{protocolo}"]["get"]
    assert "link" in (resumo.get("summary") or "").lower()


# --------------------------------------- o que o módulo recusa, sem rede


def test_o_https_se_forca():
    """O token viaja nesta conexão; em texto puro, quem estiver na rede o lê —
    e com ele fala pela serventia."""
    with pytest.raises(API.OnrtdpjError, match="https"):
        API._partes("http://centralinside.rtdbrasil.org.br")


def test_pedido_sem_protocolo_nao_sai_da_casa():
    """A viagem até a Central custa mais que a recusa aqui — e um pedido sem
    protocolo agiria **sobre nada**, com a Central respondendo 200."""
    for chamar in (lambda: API.pedido(""),
                   lambda: API.informar_orcamento("", "10,00"),
                   lambda: API.cadastrar_nota_devolutiva("", "faltam papéis"),
                   lambda: API.registrar_pedido(""),
                   lambda: API.cancelar_pedido("", "motivo bem escrito")):
        with pytest.raises(API.OnrtdpjError, match="protocolo"):
            chamar()


def test_nota_devolutiva_sem_exigencia_nao_sai():
    with pytest.raises(API.OnrtdpjError, match="exigências"):
        API.cadastrar_nota_devolutiva("2026.0001", "   ")


def test_cancelamento_sem_motivo_escrito_nao_sai():
    with pytest.raises(API.OnrtdpjError, match="dez letras"):
        API.cancelar_pedido("2026.0001", "ok")


def test_orcamento_com_texto_no_lugar_do_valor_e_recusado():
    with pytest.raises(API.OnrtdpjError, match="orçamento"):
        API.informar_orcamento("2026.0001", "dez reais")


def test_diagnostico_sem_cns_e_recusado():
    with pytest.raises(API.OnrtdpjError, match="CNS"):
        API.diagnostico("")


def test_campo_fora_do_contrato_nao_sobe():
    """**A Central ignora o que não conhece**, e ignorar em silêncio é como um
    erro de digitação vira um registro incompleto que ninguém percebe."""
    fonte = (RAIZ / "onrtdpj_api.py").read_text(encoding="utf-8")
    assert "sobrando = sorted(set(corpo) - set(CAMPOS_DO_REGISTRO))" in fonte


# ------------------------------------------ este módulo não lavra ato


def test_o_modulo_nao_lavra_numera_sela_nem_cobra():
    """**Pela quinta vez neste projeto**, depois do usucapião, das fraudes, do
    CNIB e da CENPROT. Ele fala com a Central; quem registra é `rg_titulo`, com
    o livro, a folha e a numeração da casa."""
    proibidas = ("lavrar", "numerar", "selar", "cobrar", "averbar",
                 "protocolar_no_livro")
    achados = [nome for nome in dir(API)
               if not nome.startswith("_") and callable(getattr(API, nome))
               and any(p in nome.lower() for p in proibidas)]
    assert not achados, f"função com nome de quem lavra: {achados}"


def test_o_modulo_nao_toca_no_banco():
    """Ele nem recebe `db`. Uma chamada de rede de trinta segundos segurando o
    `BEGIN IMMEDIATE` poria a casa inteira no `busy_timeout`."""
    fonte = (RAIZ / "onrtdpj_api.py").read_text(encoding="utf-8")
    for proibido in ("import sqlite3", "db.transaction", "INSERT ", "UPDATE ",
                     "DELETE "):
        assert proibido not in fonte, (
            f"«{proibido}» apareceu no transporte — quem grava é a rota")


def test_o_token_so_sai_por_UM_caminho():
    """Quem chama `token()` está prestes a falar com a Central; qualquer outro
    uso é vazamento. É a mesma regra de `credencial` e de `agente_provedores`."""
    fonte = (RAIZ / "onrtdpj_api.py").read_text(encoding="utf-8")
    assert fonte.count("CRED.token_guardado(") == 1


def test_o_modulo_aponta_para_onde_o_contrato_mora():
    """Sem isto, quem chegar daqui a um ano não sabe contra o quê conferir."""
    assert API.CONTRATO_NO_PROJETO.endswith("swagger_v1.json")
    assert "FONTES_EXTERNAS" in API.CONTRATO_NO_PROJETO


# ------------------------------------------------ a credencial é um token


def test_a_onrtdpj_guarda_TOKEN_e_nao_par(tmp_path):
    """**A terceira Central mudou a premissa do módulo de credenciais**: as
    duas de Protesto guardam usuário e senha; esta guarda um segredo só."""
    assert CRED.FORMA_DA_CENTRAL[CRED.ONRTDPJ] == CRED.TOKEN
    with pytest.raises(CRED.CredencialError, match="token"):
        CRED.gravar(CRED.ONRTDPJ, usuario="x", senha="Senha#123",
                    pasta=tmp_path)


def test_gravar_e_ler_o_token(tmp_path):
    CRED.gravar_token(CRED.ONRTDPJ, token="abc123", pasta=tmp_path)
    assert CRED.token_guardado(CRED.ONRTDPJ, pasta=tmp_path) == "abc123"
    assert CRED.tem(CRED.ONRTDPJ, CRED.PRODUCAO, tmp_path) is True


def test_sem_token_a_recusa_DIZ_onde_pegar(tmp_path):
    """Recusa que não diz o que fazer manda o oficial procurar — e o token não
    está num lugar óbvio: é o do SINTER, em Serviços."""
    with pytest.raises(CRED.CredencialError) as erro:
        CRED.token_guardado(CRED.ONRTDPJ, pasta=tmp_path)
    assert "SINTER" in str(erro.value)
    assert "rtdbrasil.org.br" in str(erro.value)


def test_o_token_nao_entra_no_banco():
    """O banco viaja no backup, e **o backup desta serventia já saiu daqui**.

    **E ESTE TESTE JÁ NASCEU ERRADO UMA VEZ, DO JEITO DE SEMPRE.** A primeira
    versão procurava a palavra `onrtdpj` nos módulos de esquema — e
    `rg_schema.py` a tem **num comentário**, citando o pedido do oficial. Ele
    acusava prosa, que é a **oitava** vez que um varredor deste projeto bate no
    texto em vez de bater no código; as sete anteriores estão no `CLAUDE.md`, e
    desta vez o varredor era meu.

    A régua certa é o que o esquema DECLARA: nenhuma coluna guarda token, e o
    único lugar que o lê é o arquivo fora do banco.
    """
    fonte = (RAIZ / "centrais_cred.py").read_text(encoding="utf-8")
    assert "PROGRAMDATA" in fonte
    assert "onrtdpj.cred" in fonte

    # Nenhuma COLUNA de esquema guarda token da Central. Procura o nome de
    # coluna, e não a palavra solta.
    import re
    for modulo in ("database.py", "rg_schema.py", "cn_schema.py"):
        texto = (RAIZ / modulo).read_text(encoding="utf-8")
        colunas = re.findall(r"^\s{4}(\w+)\s+(?:TEXT|INTEGER|REAL|BLOB)",
                             texto, re.MULTILINE)
        suspeitas = [c for c in colunas
                     if "token" in c.lower() or "onrtdpj" in c.lower()]
        assert not suspeitas, f"{modulo} declara coluna de token: {suspeitas}"

    # E só `centrais_cred` devolve o token — nenhum módulo de banco o lê.
    for modulo in ("database.py", "rg_schema.py"):
        assert "token_guardado" not in (RAIZ / modulo).read_text(encoding="utf-8")


def test_a_tela_pergunta_se_TEM_sem_pedir_o_token(tmp_path):
    """A tela precisa saber se já foi informado, e não qual é. Devolver o
    segredo para desenhar um «✓» seria pô-lo no HTML."""
    assert API.tem_credencial(pasta=tmp_path) is False
    CRED.gravar_token(CRED.ONRTDPJ, token="abc123", pasta=tmp_path)
    assert API.tem_credencial(pasta=tmp_path) is True
