"""
O TRANSPORTE DA CERTIDÃO ELETRÔNICA — a segunda API do ON-RCPN.

    «siga no desenvolvimento das integrações até terminar de todas, sem minha
     intervenção» — o oficial, 03/09/2026

É o **item 2 do cronograma**, depois do e-Proclamas. E é a maior entrega para o
balcão das duas: além de emitir a certidão eletrônica, ela traz a **fila de
pedidos** de sete módulos — dois deles **pedidos de REGISTRO**, e não de
certidão.

O CONTRATO, MEDIDO EM 03/09/2026
    OpenAPI **3.0.0** · «API da Certidão Eletrônica 1.0.5» · **10 caminhos** ·
    5 esquemas. Guardado em `FONTES_EXTERNAS/onrcpn/certidao_swagger.json`,
    que fica fora de `SERVIDOR/INSTALAR_CARTORIO_GESTAO` e **não viaja no
    `.cgu`**. Os testes **abrem esse arquivo e comparam**.

**O CONTRATO NÃO DECLARA ENDEREÇO NENHUM** — `servers` vem nulo. O que existe é
o endereço da documentação, `certidaoh.registrocivil.org.br/api/docs/`, e ele
tem o «h» de homologação. **A produção continua sem endereço publicado**, como
no e-Proclamas, e pela mesma razão não se tira o «h» por conta própria.

ESTA API E O e-PROCLAMAS SÃO A MESMA CENTRAL E **NÃO SÃO O MESMO FORMATO**
    Quatro divergências medidas, comparando os exemplos dos dois contratos.
    Copiar um conversor do outro por hábito produz recusa que não diz por quê:

    | | e-Proclamas | Certidão Eletrônica |
    |---|---|---|
    | CPF | `00000004693` — **cru** | `000.000.049-36` — **com máscara** |
    | data | `28/03/2025` | `18/07/2024` — igual |
    | matrícula | 32 dígitos | 32 dígitos — igual |
    | o que volta | duas listas, sem `success` | `{success, data, message}` |

    O CPF é o que morde: **cinco exemplos deste contrato o trazem pontuado**,
    e nenhum exemplo daquele. `cpf_para_a_central` aqui **põe a máscara**, e
    a daquele módulo tira — as duas funções têm o mesmo nome em módulos
    diferentes de propósito, porque respondem à mesma pergunta com respostas
    diferentes, e o teste compara as duas para a diferença não sumir num
    conserto distraído.

    > **Isto é medido nos EXEMPLOS do contrato, e não numa chamada real.** Não
    > há um pedido desta serventia para conferir. Se a Central recusar o CPF
    > com 422, é aqui que se olha primeiro, e é uma linha.

**E O DINHEIRO TEM DOIS FORMATOS DENTRO DESTA MESMA API.** `cota_emolumentos`
vai `"R$ 10,00"` — com o símbolo e com vírgula — e `valor_emolumentos` vai
`"1.00"`, nu e com ponto. O `deposito_previo` que a Central **devolve** vem
`"43,76"`, com vírgula. Quem subtrair um do outro sem converter acha que 43,76
é 43.

**HTTP 201 NÃO QUER DIZER QUE DEU CERTO, e aqui há como saber.** Toda resposta
declara `success` (booleano). É a lição do e-Proclamas — onde eu tratei 200
como sucesso e a Central mandava duas listas — aplicada antes de custar:
`_resposta_ou_erro` **exige `success` verdadeiro**, e não só o código HTTP.

**MENOS UMA EXCEÇÃO, E ELA ESTÁ DECLARADA**: o `410 Certidão cancelada` da
assinatura devolve `{data: {status}, message}` — **sem `success`**. Tratá-lo
pela régua geral daria «a Central respondeu sem dizer se deu certo» a quem
precisa ler «esta certidão está cancelada».

**O ARQUIVO NÃO VEM EM BASE64: VEM COMO ARRAY DE INTEIROS.** O contrato declara
`arquivo: {type: string, data: array[integer]}`, que é um `Buffer` do Node
serializado em JSON — `{"type":"Buffer","data":[37,80,68,70,...]}`. Quem tentar
`base64.b64decode` recebe erro; quem tentar `.encode()` grava um PDF corrompido
que só se descobre ao abrir. `arquivo_para_bytes` faz a conversão, e aceita
base64 também **caso a Central mude** — dizendo qual das duas leu.

**O `certificate-file` É O ÚNICO DOS DEZ SEM `security` DECLARADA.** Os outros
nove trazem `BearerAuth`; ele não traz nada — e é o mesmo cadastro, o mesmo
token e a mesma Central. **É omissão do contrato, e não caminho aberto**: há
teste que fica vermelho no dia em que corrigirem, para a correção não passar
despercebida. É a decisão do `http://` no WSDL da CRA.

**NENHUM DOS CINCO ESQUEMAS DECLARA CAMPO OBRIGATÓRIO** — `required` vem vazio
em `Certidao`, `Nascimento`, `Casamento`, `Obito` e `InteiroTeor`. É o terceiro
contrato de Central seguido assim, depois dos `/v2` da CENPROT e da ONRTDPJ, e
a regra da casa é a mesma: **não se inventa obrigação que o contrato não
declara.** O que este módulo recusa é a chamada que **não pode funcionar** —
sem `id`, sem módulo conhecido, sem CNS.

    Os três caminhos de pedido são a exceção, e ali a obrigação **é** declarada:
    `obter-pedidos` exige dois campos, `enviar-pedidos` **oito** e
    `rejeitar-pedidos` três.

A AUTENTICAÇÃO É A MESMA DO e-PROCLAMAS, E O TOKEN TAMBÉM
    `BearerAuth: {type: http, scheme: bearer, bearerFormat: JWT}` — e a nota do
    contrato do e-Proclamas diz que **um token serve às duas**. Por isso este
    módulo **não tem `token()` próprio**: ele usa o de `onrcpn_api`. Duas
    leituras do mesmo arquivo divergiriam no dia em que uma passasse a renovar
    e a outra não.

O QUE ESTE MÓDULO **NÃO** FAZ, E POR QUÊ
    **Os dois caminhos de arquivo PDF** (`POST` e `PUT /certificate-file`)
    estão medidos e **não estão ligados**. Não é esquecimento:

      * o `POST` declara as três partes como `string` solto, e o `PUT` as
        declara com os `$ref` dos esquemas — **o mesmo conceito, duas formas**,
        no mesmo contrato;
      * o PDF que esta casa sabe montar é o da certidão **de papel**, do molde
        que o oficial desenhou. Mandá-lo como a certidão **eletrônica** é
        decisão de quem assina, e não dedução deste módulo.

    Ficam declarados em `CAMINHO`, com o método e as partes, **para ninguém os
    reinventar achando que sumiram** — a lição do `renegociacoes()` da CENPROT.
"""
from __future__ import annotations

import base64
import json
import re
from typing import Any

import onrcpn_api as PROC

# O ENDEREÇO. **Não sai do contrato** — ele não declara `servers`. Sai da
# página de documentação, `certidaoh.registrocivil.org.br/api/docs/index.html`,
# e traz o «h» de homologação.
BASE = "https://certidaoh.registrocivil.org.br"

# ONDE O CONTRATO MORA, para o teste o abrir. Caminho a partir da RAIZ do
# projeto, e não desta pasta: `FONTES_EXTERNAS` fica fora do que viaja.
CONTRATO_NO_PROJETO = "FONTES_EXTERNAS/onrcpn/certidao_swagger.json"

PRAZO_PADRAO = 60

# ------------------------------------------------------------- os caminhos
#
# `:id` marca o pedaço que se substitui. Os dez estão aqui — inclusive os dois
# que este módulo não liga, porque caminho que some da lista é caminho que
# alguém reinventa.

CAMINHO: dict[str, str] = {
    "criar": "/api/v1.0/certificate-json",
    "criar_arquivo": "/api/v1.0/certificate-file",
    "buscar": "/api/v1.0/get-certificate-json/:id",
    "atualizar": "/api/v1.0/certificate-json/:id",
    "atualizar_arquivo": "/api/v1.0/certificate-file/:id",
    "assinar": "/api/v1.0/sign-certificate-json/:id",
    "cancelar": "/api/v1.0/cancel-certificate/:id",
    "obter_pedidos": "/api/v1.0/obter-pedidos",
    "enviar_pedidos": "/api/v1.0/enviar-pedidos",
    "rejeitar_pedidos": "/api/v1.0/rejeitar-pedidos",
}

METODO_DO_CAMINHO: dict[str, str] = {
    "criar": "POST", "criar_arquivo": "POST", "buscar": "GET",
    "atualizar": "PUT", "atualizar_arquivo": "PUT", "assinar": "POST",
    "cancelar": "POST", "obter_pedidos": "POST", "enviar_pedidos": "POST",
    "rejeitar_pedidos": "POST",
}

# OS DOIS QUE NÃO SE LIGAM, e a razão está no cabeçalho. Declarado aqui para o
# teste conferir que ninguém os chamou por engano.
CAMINHOS_NAO_LIGADOS: tuple[str, ...] = ("criar_arquivo", "atualizar_arquivo")

# O ÚNICO SEM `security` NO CONTRATO. Ver o cabeçalho: é omissão, e o token vai
# assim mesmo se um dia ele for ligado.
CAMINHO_SEM_SEGURANCA_DECLARADA = "criar_arquivo"


# ---------------------------------------------------------- os vocabulários

# OS SETE MÓDULOS DA FILA. **Estão na PROSA da descrição de `obter-pedidos`, e
# não numa lista fechada do contrato** — o campo `modulo` é um `string` com o
# exemplo `"CRC"` e mais nada. Transcritos um a um.
CRC, REG, JUD, EPR, P13, RSE, EOB = (
    "CRC", "REG", "JUD", "EPR", "P13", "RSE", "EOB")

MODULOS: tuple[str, ...] = (CRC, REG, JUD, EPR, P13, RSE, EOB)

NOME_DO_MODULO: dict[str, str] = {
    CRC: "Pedidos de certidões no módulo do Provimento n. 149",
    REG: "Pedidos de certidões do site do registrocivil.org.br",
    JUD: "Pedidos de certidões nos módulos CRC-Jud ou Serp-Jud",
    EPR: "Pedidos efetuados na plataforma do e-Protocolo",
    P13: "Solicitações de registro de nascimento nas Unidades Interligadas",
    RSE: "Solicitações de certidões pelo módulo do «Registre-se»",
    EOB: "Solicitações de registro de óbito feitas pelo módulo «e-Óbito»",
}

# **DOIS DOS SETE NÃO PEDEM CERTIDÃO: PEDEM REGISTRO.** A descrição do contrato
# diz «Solicitações de REGISTRO de nascimento» e «de REGISTRO de óbito». São
# atos diferentes — um se emite, o outro se lavra —, e tratá-los pela mesma
# régua faria o balcão responder «certidão emitida» a quem pediu um registro
# que ninguém lavrou.
MODULOS_DE_REGISTRO: tuple[str, ...] = (P13, EOB)
MODULOS_DE_CERTIDAO: tuple[str, ...] = tuple(
    m for m in MODULOS if m not in MODULOS_DE_REGISTRO)

# O QUE CADA MÓDULO DE REGISTRO PEDE QUE SE LAVRE.
ESPECIE_DO_MODULO_DE_REGISTRO: dict[str, str] = {
    P13: "NASCIMENTO",
    EOB: "OBITO",
}

TIPOS_DE_REGISTRO: tuple[str, ...] = (
    "nascimento", "casamento", "obito", "inteiro_teor")
MODALIDADES: tuple[str, ...] = ("eletronica", "fisica")
SEXOS: tuple[str, ...] = ("masculino", "feminino", "ignorado", "outros")
TIPOS_DE_DOCUMENTO: tuple[str, ...] = (
    "RG", "CTPS", "RNE", "CNH", "passaporte", "titulo_eleitor")
EXISTENCIA_BENS: tuple[str, ...] = ("sim", "nao", "ignorada")
EXISTENCIA_FILHOS: tuple[str, ...] = ("sim", "nao", "ignorado", "texto")

# A LETRA DO `tipo_registro` **DE DENTRO DO PEDIDO** — e ela NÃO é o vocabulário
# do esquema `Certidao`. Ali o campo se chama igual e vale `"nascimento"`; aqui
# o exemplo é `"N"`.
#
#   **Só o `N` está medido**, e é o único exemplo do contrato. O `C` e o `O`
#   são derivados da inicial, que é a leitura óbvia — e leitura óbvia não é
#   medição. Por isso `especie_do_pedido` devolve `None` para letra
#   desconhecida em vez de chutar, e a tela mostra a letra crua.
LETRA_DO_TIPO_DE_REGISTRO: dict[str, str] = {
    "N": "nascimento",   # MEDIDO — exemplo do contrato
    "C": "casamento",    # DERIVADO da inicial — A CONFERIR
    "O": "obito",        # DERIVADO da inicial — A CONFERIR
}
LETRAS_MEDIDAS: frozenset[str] = frozenset({"N"})


# ------------------------------------------------------------- os campos
#
# Transcritos do contrato, na ordem em que ele os declara. Servem para o teste
# comparar contra o `certidao_swagger.json` e para as telas montarem a ficha
# sem repetir a lista.

CAMPOS_DA_CERTIDAO: tuple[str, ...] = (
    "plataformaId", "tipo_registro", "tipo_certidao", "transcricao",
    "cartorio_cns", "selo", "cod_selo", "modalidade", "cota_emolumentos",
    "cota_emolumentos_isento")

CAMPOS_DO_NASCIMENTO: tuple[str, ...] = (
    "nome_completo", "cpf_sem_inscricao", "cpf", "matricula", "data_registro",
    "data_nascimento_ignorada", "data_nascimento", "hora_nascimento",
    "municipio_naturalidade", "uf_naturalidade", "local_nascimento",
    "municipio_nascimento", "uf_nascimento", "sexo", "sexo_outros", "gemeos",
    "filiacao", "numero_dnv", "averbacao_anotacao", "anotacoes_cadastro")

CAMPOS_DO_CASAMENTO: tuple[str, ...] = (
    "conjuges", "matricula", "data_celebracao", "regime_bens",
    "data_registro", "averbacao_anotacao", "anotacoes_cadastro")

CAMPOS_DO_CONJUGE: tuple[str, ...] = (
    "nome_atual_habilitacao", "cpf_sem_inscricao", "cpf", "novo_nome",
    "nome_apos_casamento", "data_nascimento", "nacionalidade", "estado_civil",
    "municipio_naturalidade", "uf_naturalidade", "genitores")

CAMPOS_DO_OBITO: tuple[str, ...] = (
    "nome_completo", "cpf_sem_inscricao", "cpf", "matricula",
    "data_falecimento_ignorada", "data_falecimento", "hora_falecimento",
    "local_falecimento", "municipio_falecimento", "uf_falecimento", "sexo",
    "sexo_outros", "estado_civil", "nome_ultimo_conjuge_convivente", "idade",
    "data_nascimento", "municipio_naturalidade", "uf_naturalidade",
    "filiacao", "causa_morte", "nome_medico", "crm_medico",
    "local_sepultamento_cremacao", "municipio_sepultamento_cremacao",
    "uf_sepultamento_cremacao", "data_registro", "nome_declarante",
    "existencia_bens", "existencia_filhos_ignorada",
    "existencia_filhos_opcao", "existencia_filhos", "averbacao_anotacao",
    "anotacoes_cadastro")

CAMPOS_DO_INTEIRO_TEOR: tuple[str, ...] = (
    "nome_completo", "cpf_sem_inscricao", "cpf", "matricula",
    "nome_secundario_completo", "cpf_secundario_sem_inscricao",
    "cpf_secundario", "texto_certidao")

CAMPOS_DA_ANOTACAO_DE_CADASTRO: tuple[str, ...] = (
    "tipo", "documento", "orgao_emissor", "uf_emissao", "data_emissao")

CAMPOS_DA_FILIACAO_DO_NASCIMENTO: tuple[str, ...] = (
    "nome", "municipio_nascimento", "uf_nascimento", "avos")

CAMPOS_POR_TIPO: dict[str, tuple[str, ...]] = {
    "nascimento": CAMPOS_DO_NASCIMENTO,
    "casamento": CAMPOS_DO_CASAMENTO,
    "obito": CAMPOS_DO_OBITO,
    "inteiro_teor": CAMPOS_DO_INTEIRO_TEOR,
}

# O QUE VOLTA EM CADA LINHA DA FILA (`rows` de `obter-pedidos`).
CAMPOS_DO_PEDIDO: tuple[str, ...] = (
    "pedido_certidao_id", "numero_cnj_solicitante", "numero_cnj_recebedor",
    "nome_requerente", "documento_requerente", "data_pedido", "tipo_registro",
    "nome_registrado", "data_ato_fato", "data_registro", "num_livro",
    "num_folha", "num_registro", "matricula", "obs_pedido", "deposito_previo")

# OS OITO QUE `enviar-pedidos` EXIGE — e ali o contrato **declara** os
# obrigatórios, ao contrário dos cinco esquemas.
CAMPOS_DO_ENVIO: tuple[str, ...] = (
    "numero_pedido", "modulo", "quantidade_averbacao", "valor_adicional",
    "valor_emolumentos", "observacoes_emissao", "id_externo", "id_verificador")

CAMPOS_DA_REJEICAO: tuple[str, ...] = (
    "numero_pedido", "modulo", "descricao_motivo")

# ------------------------------------------------------------ o que volta

CAMPO_DO_SUCESSO = "success"
CAMPO_DA_MENSAGEM = "message"
CAMPO_DOS_DADOS = "data"
CAMPO_DO_ID = "certidao_id"
CAMPO_DO_ARQUIVO = "arquivo"
CAMPO_DO_ESTADO = "status"
CAMPO_DAS_LINHAS = "rows"
CAMPO_DA_CONTAGEM = "count"
CAMPO_DO_LINK_DE_ASSINATURA = "link_assinatura"
CAMPO_DO_ID_DA_ASSINATURA = "id_assinatura"

# **O `numero_pedido` TEM TRÊS NOMES E DOIS TIPOS NESTA MESMA API**, e é a
# armadilha do `cd_pedido` da CENPROT outra vez:
#
#   `obter-pedidos`    devolve  `pedido_certidao_id`  integer
#   `enviar-pedidos`   exige    `numero_pedido`       **string**
#   `rejeitar-pedidos` exige    `numero_pedido`       **number**
#
# Mandar o número como texto onde ela quer número — ou o contrário — é o tipo
# de recusa que volta como 500 sem dizer qual campo.
TIPO_DO_NUMERO_DO_PEDIDO: dict[str, type] = {
    "enviar_pedidos": str,
    "rejeitar_pedidos": int,
}

# **FORA DE SÃO PAULO, `quantidade_averbacao` VAI NULO.** Está na descrição de
# `enviar-pedidos`: «Quando a solicitação for de outro estado, envie o valor
# NULL». O Maranhão é outro estado — e o campo é **obrigatório**, de modo que
# ele vai presente e nulo, e não ausente.
UF_QUE_CONTA_AVERBACAO = "SP"

# O `410` DA ASSINATURA NÃO TEM `success` — ver o cabeçalho.
STATUS_SEM_SUCESSO: frozenset[int] = frozenset({410})


class CertidaoError(RuntimeError):
    """Não deu para falar com a Central, ou ela recusou o token."""


class CertidaoRecusou(CertidaoError):
    """A Central respondeu, e disse não. A frase dela vai junto."""


class CertidaoCancelada(CertidaoRecusou):
    """A certidão que se tentou assinar está cancelada (410)."""


# ------------------------------------------------------ o que ela entende


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def cpf_para_a_central(valor: Any) -> str:
    """`000.000.049-36` — **COM máscara**, ao contrário do e-Proclamas.

    Medido nos **cinco** exemplos de CPF deste contrato; nenhum vem cru. A
    função irmã de `onrcpn_api` faz o oposto, e a diferença é deliberada — há
    teste que compara as duas, para um conserto distraído não igualar as duas
    Centrais que não são iguais.

    Devolve `""` quando não há CPF: **campo vazio não afirma nada**, e o
    contrato tem `cpf_sem_inscricao` para dizer que a pessoa não tem.
    """
    digitos = re.sub(r"\D", "", _texto(valor))
    if not digitos:
        return ""
    if len(digitos) != PROC.DIGITOS_DO_CPF:
        raise CertidaoError(
            f"O CPF «{valor}» não tem {PROC.DIGITOS_DO_CPF} dígitos.")
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def data_para_a_central(valor: Any) -> str:
    """`dd/mm/aaaa`. **Igual à do e-Proclamas** — e por isso é a dele.

    Reaproveitar em vez de copiar é o que impede as duas divergirem no dia em
    que uma das Centrais mudar.
    """
    return PROC.data_para_a_central(valor)


def valor_para_a_central(valor: Any) -> str:
    """`"1.00"` — nu, com **ponto**, duas casas. É o formato de `valor_*`.

    **Não é o de `cota_emolumentos`**, que vai `"R$ 10,00"`. Duas formas de
    dinheiro na mesma API, e o contrato mostra as duas nos exemplos.
    """
    texto = _texto(valor)
    if not texto:
        return "0.00"
    return f"{ler_valor_da_central(texto):.2f}"


def ler_valor_da_central(valor: Any) -> float:
    """`"43,76"` → `43.76`. É como o `deposito_previo` VOLTA.

    **A Central devolve com vírgula e recebe com ponto**, e quem não converter
    lê quarenta e três reais e setenta e seis centavos como quarenta e três.
    Aceita as duas formas porque as duas aparecem no contrato.
    """
    texto = _texto(valor).replace("R$", "").strip()
    if not texto:
        return 0.0
    # Milhar com ponto e centavo com vírgula — `1.234,56` — é a forma
    # brasileira; sem vírgula, o ponto já é o decimal.
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError as erro:
        raise CertidaoError(
            f"Não entendi o valor «{valor}» que a Central mandou.") from erro


def cota_para_a_central(valor: Any) -> str:
    """`"R$ 10,00"` — com símbolo e **vírgula**. É o formato de `cota_emolumentos`."""
    return f"R$ {ler_valor_da_central(valor):.2f}".replace(".", ",")


def _do_vocabulario(valor: Any, aceitos: tuple[str, ...], onde: str) -> str:
    texto = _texto(valor).lower()
    if not texto:
        return ""
    if texto not in aceitos:
        raise CertidaoError(
            f"A Central não aceita «{valor}» {onde}. Ela aceita: "
            + ", ".join(aceitos) + ".")
    return texto


def tipo_de_registro_para_a_central(valor: Any) -> str:
    return _do_vocabulario(valor, TIPOS_DE_REGISTRO, "no tipo de registro")


def modalidade_para_a_central(valor: Any) -> str:
    return _do_vocabulario(valor, MODALIDADES, "na modalidade")


def sexo_para_a_central(valor: Any) -> str:
    """O vocabulário aqui tem **quatro** palavras, e o do e-Proclamas tem duas.

    Lá são `masculino` e `feminino`; aqui há `ignorado` e `outros` — e `outros`
    vem com `sexo_outros`, um texto livre. Mandar `ignorado` ao e-Proclamas
    seria recusa; não oferecê-lo aqui seria esconder uma resposta legítima.
    """
    return _do_vocabulario(valor, SEXOS, "no sexo")


def modulo_da_central(valor: Any) -> str:
    """O código do módulo, em MAIÚSCULAS. **Recusa o que não está nos sete.**

    O contrato não fecha a lista — os sete estão na prosa —, e é justamente
    por isso que a recusa é aqui: um módulo escrito errado voltaria como lista
    vazia, e lista vazia se lê como «não há pedido nenhum».
    """
    texto = _texto(valor).upper()
    if texto not in MODULOS:
        raise CertidaoError(
            f"«{valor}» não é um dos módulos da Central. Os sete são: "
            + ", ".join(MODULOS) + ".")
    return texto


def especie_do_pedido(letra: Any) -> str | None:
    """A letra do `tipo_registro` do pedido → a espécie. `None` se não se sabe.

    **Só o `N` está medido.** Devolver um palpite para as outras faria a fila
    dizer «casamento» sobre um pedido que ninguém conferiu.
    """
    texto = _texto(letra).upper()
    return LETRA_DO_TIPO_DE_REGISTRO.get(texto)


def arquivo_para_bytes(arquivo: Any) -> bytes:
    """O PDF que a Central devolve. **Array de inteiros, e não base64.**

    O contrato declara `{type: string, data: array[integer]}` — um `Buffer` do
    Node serializado. Aceita base64 também, para o caso de mudarem, e recusa o
    que não é nem uma coisa nem outra em vez de gravar um PDF corrompido que
    só se descobre ao abrir.
    """
    if isinstance(arquivo, (bytes, bytearray)):
        return bytes(arquivo)
    if isinstance(arquivo, dict):
        dados = arquivo.get("data")
        if isinstance(dados, list):
            try:
                return bytes(int(b) & 0xFF for b in dados)
            except (TypeError, ValueError) as erro:
                raise CertidaoError(
                    "A Central mandou o arquivo como lista, e há algo que não "
                    "é um byte dentro dela.") from erro
        if isinstance(dados, str):
            arquivo = dados
    if isinstance(arquivo, str):
        try:
            return base64.b64decode(arquivo, validate=True)
        except (ValueError, TypeError) as erro:
            raise CertidaoError(
                "A Central mandou o arquivo como texto, e ele não é base64.",
            ) from erro
    raise CertidaoError(
        "Não reconheci a forma do arquivo que a Central devolveu. O contrato "
        "declara «{type, data}» com `data` sendo uma lista de bytes.")


# ------------------------------------------------------------ a credencial


def token(*, pasta=None) -> str:
    """**O token é o do e-Proclamas**, e por isso esta função só delega.

    A nota do contrato do e-Proclamas: «o token de acesso (IdRC) já utilizado
    para integração com o sistema de certidões **também poderá ser
    reutilizado**». Um `token()` próprio aqui seria uma segunda leitura do
    mesmo arquivo, para divergir no primeiro conserto.
    """
    return PROC.token(pasta=pasta)


def tem_credencial(*, pasta=None) -> bool:
    """A tela pergunta isto antes de oferecer botão. **Não devolve o token.**"""
    return PROC.tem_credencial(pasta=pasta)


# ------------------------------------------------------------ o transporte


def _endereco(qual: str, ident: Any = None) -> str:
    caminho = CAMINHO[qual]
    if ":id" in caminho:
        chave = _texto(ident)
        if not chave:
            raise CertidaoError(
                f"O caminho «{qual}» precisa do identificador da certidão.")
        caminho = caminho.replace(":id", chave)
    return caminho


def _bater(qual: str, *, ident: Any = None, corpo: dict | None = None,
           prazo: int = PRAZO_PADRAO, pasta=None) -> dict:
    """Uma requisição a esta API. **O transporte é o de `onrcpn_api`.**

    Ver o cabeçalho de `onrcpn_api.bater`: o https forçado e o «só GET se
    repete» são as duas regras que não podem divergir entre as duas APIs.
    """
    if qual in CAMINHOS_NAO_LIGADOS:
        raise CertidaoError(
            f"O caminho «{qual}» está medido e não está ligado — ver o "
            f"cabeçalho de `onrcpn_certidao_api`.")
    bruto = (json.dumps(corpo, ensure_ascii=False).encode("utf-8")
             if corpo is not None else None)
    return PROC.bater(METODO_DO_CAMINHO[qual], _endereco(qual, ident),
                      corpo=bruto, base=BASE, prazo=prazo, pasta=pasta)


def _detalhe(r: dict) -> str:
    """A frase da Central, se ela mandou uma.

    O `422` traz o `message` como **um objeto por campo**
    (`{"registro.matricula": ["..."]}`), e não como frase — e é justamente ele
    que o escrevente precisa ler inteiro para saber qual campo corrigir.
    """
    corpo = r.get("json")
    if isinstance(corpo, dict):
        valor = corpo.get(CAMPO_DA_MENSAGEM)
        if isinstance(valor, dict):
            partes = []
            for campo, avisos in valor.items():
                if isinstance(avisos, list):
                    partes.append(f"{campo}: " + "; ".join(str(a) for a in avisos))
                else:
                    partes.append(f"{campo}: {avisos}")
            return " · ".join(partes)[:600]
        if valor:
            return _texto(valor)[:600]
    return _texto(r.get("texto"))[:400]


def _resposta_ou_erro(r: dict, o_que: str) -> dict:
    """Traduz a resposta da Central. **Exige `success`, e não só o HTTP.**

    É a lição do e-Proclamas antes de ela custar: lá eu tratei 200 como
    sucesso e a Central mandava duas listas. Aqui há um campo que responde, e
    ignorá-lo seria repetir o erro tendo a resposta na mão.
    """
    corpo = r.get("json")
    status = r["status"]

    if status == 410:
        # **A EXCEÇÃO DECLARADA.** Este corpo não tem `success`, e a frase que
        # importa é «esta certidão está cancelada».
        estado = ""
        if isinstance(corpo, dict):
            estado = _texto((corpo.get(CAMPO_DOS_DADOS) or {}).get(
                CAMPO_DO_ESTADO))
        raise CertidaoCancelada(
            f"A Central recusou {o_que}: a certidão está cancelada"
            + (f" (situação «{estado}»)" if estado else "") + ".")

    if status in (401, 403):
        raise CertidaoError(
            f"A Certidão Eletrônica recusou o token ao {o_que}. O token IdRC "
            f"pode ter expirado ou sido trocado: informe-o de novo em "
            f"Administrativo → Configurações, na seção «Centrais — "
            f"credenciais das APIs». **É o mesmo token do e-Proclamas.**")

    if status == 422:
        raise CertidaoRecusou(
            f"A Central recusou os dados ao {o_que}: {_detalhe(r)}")

    if status == 404:
        raise CertidaoRecusou(
            f"A Central não encontrou o que se pediu ao {o_que}.")

    if status not in (200, 201):
        raise CertidaoRecusou(
            f"A Central respondeu {status} ao {o_que}: {_detalhe(r)}")

    if not isinstance(corpo, dict):
        raise CertidaoRecusou(
            f"A Central respondeu {status} ao {o_que} com um corpo que não é "
            f"um objeto JSON: {_texto(r.get('texto'))[:200]}")

    # **AQUI ESTÁ A LIÇÃO DO e-PROCLAMAS.** HTTP bom e `success: false` é a
    # resposta que passaria por sucesso se ninguém olhasse.
    if corpo.get(CAMPO_DO_SUCESSO) is not True:
        raise CertidaoRecusou(
            f"A Central respondeu {status} ao {o_que}, e disse que **não** deu "
            f"certo: {_detalhe(r) or 'sem explicação'}.")
    return corpo


# --------------------------------------------------------- a fila de pedidos


def obter_pedidos(modulo: Any, cns: Any, *, pasta=None) -> dict:
    """Os pedidos pendentes daquele módulo. **Não grava nada.**

    Devolve `{modulo, quantos, pedidos}`. O `count` da Central vem junto e é
    conferido contra o tamanho da lista: se discordarem, a tela precisa saber —
    é o sinal de que a resposta veio pela metade.
    """
    qual = modulo_da_central(modulo)
    chave = re.sub(r"\D", "", _texto(cns))
    if not chave:
        raise CertidaoError(
            "A Central precisa do CNS da serventia para achar os pedidos. "
            "Informe-o em Administrativo → Configurações.")
    r = _bater("obter_pedidos", corpo={"modulo": qual, "cns": chave},
               pasta=pasta)
    corpo = _resposta_ou_erro(r, f"buscar os pedidos do módulo {qual}")
    linhas = corpo.get(CAMPO_DAS_LINHAS) or []
    if not isinstance(linhas, list):
        raise CertidaoRecusou(
            f"A Central devolveu «{CAMPO_DAS_LINHAS}» em forma inesperada ao "
            f"buscar os pedidos do módulo {qual}.")
    declarados = corpo.get(CAMPO_DA_CONTAGEM)
    return {
        "modulo": qual,
        "quantos": len(linhas),
        "quantos_a_central_disse": declarados,
        # **DIVERGÊNCIA NÃO SE CORRIGE EM SILÊNCIO**: ela vira aviso.
        "contagem_bate": (declarados is None or int(declarados) == len(linhas)),
        "pedidos": [_pedido(linha) for linha in linhas],
    }


def _pedido(linha: Any) -> dict:
    """Uma linha da fila, como a Central a mandou, mais o que se derivou dela.

    **O `teor` guarda a linha inteira e crua.** A Central pode acrescentar
    coluna amanhã, e o que a casa recebeu naquele dia foi isto.
    """
    if not isinstance(linha, dict):
        raise CertidaoRecusou(
            "A Central mandou um pedido que não é um objeto JSON.")
    pedido = {c: linha.get(c) for c in CAMPOS_DO_PEDIDO}
    pedido["especie"] = especie_do_pedido(linha.get("tipo_registro"))
    pedido["letra_medida"] = (
        _texto(linha.get("tipo_registro")).upper() in LETRAS_MEDIDAS)
    pedido["deposito_previo_valor"] = ler_valor_da_central(
        linha.get("deposito_previo"))
    pedido["teor"] = linha
    return pedido


def enviar_pedido(*, numero_pedido: Any, modulo: Any, valor_emolumentos: Any,
                  id_externo: Any, id_verificador: Any,
                  observacoes_emissao: Any = "", valor_adicional: Any = None,
                  quantidade_averbacao: Any = None, uf_da_serventia: str = "",
                  pasta=None) -> dict:
    """Cumpre um pedido. **É a chamada que entrega a certidão ao requerente.**

    `quantidade_averbacao` vai **nulo fora de São Paulo** — está na descrição
    do próprio caminho —, e o campo é obrigatório: vai presente e nulo, e não
    ausente. Passar um número estando fora de SP é o único jeito de mandá-lo, e
    aí a responsabilidade é de quem passou.
    """
    qual = modulo_da_central(modulo)
    numero = _texto(numero_pedido)
    if not numero:
        raise CertidaoError("Informe o número do pedido a cumprir.")
    verificador = _texto(id_verificador)
    if not verificador:
        raise CertidaoError(
            "A Central exige o «id_verificador» — o identificador da certidão "
            "que se está entregando. Ele vem do envio da certidão eletrônica.")

    uf = _texto(uf_da_serventia).upper()
    if uf != UF_QUE_CONTA_AVERBACAO:
        quantidade_averbacao = None

    corpo: dict[str, Any] = {
        # STRING AQUI, e número em `rejeitar-pedidos`. Ver TIPO_DO_NUMERO_DO_PEDIDO.
        "numero_pedido": numero,
        "modulo": qual,
        "quantidade_averbacao": (None if quantidade_averbacao is None
                                 else int(quantidade_averbacao)),
        "valor_adicional": valor_para_a_central(valor_adicional),
        "valor_emolumentos": valor_para_a_central(valor_emolumentos),
        "observacoes_emissao": _texto(observacoes_emissao),
        "id_externo": _texto(id_externo),
        "id_verificador": verificador,
    }
    faltam = [c for c in CAMPOS_DO_ENVIO if c not in corpo]
    if faltam:
        raise CertidaoError(
            "Faltam campos que a Central declara obrigatórios: "
            + ", ".join(faltam) + ".")
    r = _bater("enviar_pedidos", corpo=corpo, pasta=pasta)
    resposta = _resposta_ou_erro(r, f"cumprir o pedido {numero}")
    return {"numero_pedido": numero, "modulo": qual, "corpo": corpo,
            # **O `message` DAQUI É UM INTEIRO NO CONTRATO**, e não uma frase —
            # é o único caminho assim. Vai como veio.
            "resposta": resposta.get(CAMPO_DA_MENSAGEM), "bruto": resposta}


def rejeitar_pedido(*, numero_pedido: Any, modulo: Any, motivo: Any,
                    pasta=None) -> dict:
    """Recusa um pedido, com o motivo escrito.

    **O número vai como NÚMERO aqui**, e como texto no `enviar-pedidos` — a
    mesma chave, dois tipos, no mesmo contrato.

    **Motivo é obrigatório e não se preenche sozinho**: quem pediu a certidão
    vai ler esta frase, e «não foi possível atender» não diz o que fazer.
    """
    qual = modulo_da_central(modulo)
    digitos = re.sub(r"\D", "", _texto(numero_pedido))
    if not digitos:
        raise CertidaoError(
            "Informe o número do pedido a rejeitar. A Central o quer como "
            "número, e não como texto.")
    razao = _texto(motivo)
    if not razao:
        raise CertidaoError(
            "A Central exige o motivo da rejeição, e é ele que o requerente "
            "vai ler. Escreva o que falta ou por que não se pode atender.")
    corpo = {"numero_pedido": int(digitos), "modulo": qual,
             "descricao_motivo": razao}
    r = _bater("rejeitar_pedidos", corpo=corpo, pasta=pasta)
    resposta = _resposta_ou_erro(r, f"rejeitar o pedido {digitos}")
    return {"numero_pedido": int(digitos), "modulo": qual, "corpo": corpo,
            "resposta": _texto(resposta.get(CAMPO_DA_MENSAGEM))}


# ---------------------------------------------------- a certidão eletrônica


def criar(certidao: dict, registro: dict, *, pasta=None) -> dict:
    """Cria a certidão eletrônica na Central. Devolve `{id, arquivo, ...}`.

    **Não confere campo obrigatório nenhum**, e é deliberado: o contrato não
    declara nenhum nos cinco esquemas, e inventar obrigação que ele não declara
    é o erro do outro lado. Quem confere o que a casa quer mandar é o domínio,
    antes, com a ficha à vista.
    """
    corpo = {"certidao": dict(certidao or {}), "registro": dict(registro or {})}
    r = _bater("criar", corpo=corpo, pasta=pasta)
    resposta = _resposta_ou_erro(r, "criar a certidão eletrônica")
    dados = resposta.get(CAMPO_DOS_DADOS) or {}
    return {
        "id": _texto(dados.get(CAMPO_DO_ID)),
        "arquivo": dados.get(CAMPO_DO_ARQUIVO),
        "mensagem": _texto(resposta.get(CAMPO_DA_MENSAGEM)),
        "corpo": corpo,
        "bruto": resposta,
    }


def atualizar(ident: Any, certidao: dict, registro: dict, *, pasta=None) -> dict:
    """Corrige uma certidão já criada. **O tipo de registro NÃO se altera** —
    está escrito na descrição do caminho, e a Central recusa."""
    corpo = {"certidao": dict(certidao or {}), "registro": dict(registro or {})}
    r = _bater("atualizar", ident=ident, corpo=corpo, pasta=pasta)
    resposta = _resposta_ou_erro(r, "atualizar a certidão eletrônica")
    dados = resposta.get(CAMPO_DOS_DADOS) or {}
    return {"id": _texto(ident), "arquivo": dados.get(CAMPO_DO_ARQUIVO),
            "mensagem": _texto(resposta.get(CAMPO_DA_MENSAGEM)),
            "corpo": corpo, "bruto": resposta}


def buscar(ident: Any, *, pasta=None) -> dict:
    """Busca a certidão pelo id. Devolve `{id, situacao, arquivo, pdf}`."""
    r = _bater("buscar", ident=ident, pasta=pasta)
    resposta = _resposta_ou_erro(r, "buscar a certidão eletrônica")
    dados = resposta.get(CAMPO_DOS_DADOS) or {}
    arquivo = dados.get(CAMPO_DO_ARQUIVO)
    return {
        "id": _texto(ident),
        "situacao": _texto(dados.get(CAMPO_DO_ESTADO)),
        "arquivo": arquivo,
        "pdf": arquivo_para_bytes(arquivo) if arquivo else b"",
        "bruto": resposta,
    }


def assinar(ident: Any, *, pasta=None) -> dict:
    """Assina a certidão **na Central**, e devolve o link da assinatura.

    **ISTO RESOLVE, PARA ESTE PAPEL, O QUE O A3 IMPEDE AQUI DENTRO.**
    `assinatura_digital.py` registra a medição: os dois drivers PKCS#11 desta
    máquina dão **segmentation fault** ao carregar, e um Flask que os carregue
    leva o balcão inteiro junto. Aqui a assinatura acontece do lado de lá, e o
    que volta é um `link_assinatura` e um `id_assinatura`.

    **O que este módulo NÃO afirma é que a firma é válida** — é a mesma regra
    daquele: conferir a cadeia da ICP-Brasil exige âncoras e lista de revogação
    que esta casa não tem.
    """
    r = _bater("assinar", ident=ident, pasta=pasta)
    resposta = _resposta_ou_erro(r, "assinar a certidão eletrônica")
    dados = resposta.get(CAMPO_DOS_DADOS) or {}
    arquivo = dados.get(CAMPO_DO_ARQUIVO)
    return {
        "id": _texto(ident),
        "link": _texto(dados.get(CAMPO_DO_LINK_DE_ASSINATURA)),
        "id_assinatura": _texto(dados.get(CAMPO_DO_ID_DA_ASSINATURA)),
        "arquivo": arquivo,
        "pdf": arquivo_para_bytes(arquivo) if arquivo else b"",
        "bruto": resposta,
    }


def cancelar(ident: Any, *, pasta=None) -> dict:
    """Cancela a certidão eletrônica na Central.

    **Não lavra nem desfaz ato nenhum desta casa** — cancelar a certidão de
    papel é outro ato, na ficha do assento, e este módulo não o pratica.
    """
    r = _bater("cancelar", ident=ident, pasta=pasta)
    resposta = _resposta_ou_erro(r, "cancelar a certidão eletrônica")
    return {"id": _texto(ident),
            "mensagem": _texto(resposta.get(CAMPO_DA_MENSAGEM)),
            "bruto": resposta}
