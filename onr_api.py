"""
O TRANSPORTE DO ONR — a Central do Registro de Imóveis.

    «siga no desenvolvimento das integrações até terminar de todas, sem minha
     intervenção» — o oficial, 03/09/2026

É o **item 3 do cronograma**, e o maior contrato das quatro: **39 caminhos, 53
operações, 73 esquemas**.

O CONTRATO, MEDIDO EM 03/09/2026
    OpenAPI **3.0.3** · «API - Registro de Imóveis do Brasil 1.0.0».
    Guardado em `FONTES_EXTERNAS/onr_ri/`, fora da pasta que viaja no `.cgu`.
    Os testes **abrem o arquivo e comparam**.

**HÁ DUAS CÓPIAS DO CONTRATO, E A RAZÃO É UM DEFEITO DELES.** O
`openapi.json` que o ONR publica **não é JSON válido**: tem duas vírgulas antes
de fecho (`,}`), e qualquer parser recusa o arquivo inteiro. A original fica
porque é ela que prova o defeito; `openapi_limpo.json` existe para os testes
lerem. No dia em que corrigirem, o teste que compara as duas avisa — a decisão
do `http://` no WSDL da CRA.

**OS DOIS AMBIENTES ESTÃO DECLARADOS NO PRÓPRIO CONTRATO**, e isso é o oposto
do ON-RCPN:

    produção     https://api.registrodeimoveis.org.br
    testes       https://testes-api.registrodeimoveis.org.br

Aqui não se adivinha endereço nenhum — `servers` traz os dois, na ordem
produção-primeiro. **Este módulo começa na de testes**, que é a regra da casa
para Central nova.

A AUTENTICAÇÃO É UM PAR, E ELA ESTÁ MEDIDA
    `POST /v1/auth/token`, corpo **`application/x-www-form-urlencoded`** (e não
    JSON), com `client_id`, `client_secret` e `grant_type=client_credentials` —
    os três declarados obrigatórios. Volta `{access_token, expires_in,
    token_type: "Bearer"}`.

    **É o contrário do ON-RCPN pelo lado da certeza**: lá o cadastro devolve um
    par e o endereço que o troca por token **não está medido**; aqui o contrato
    declara o endereço, o corpo e a resposta. Por isso a credencial do ONR é
    `PAR` em `centrais_cred`, e a da ON-RCPN continua `TOKEN`.

**O TOKEN SE GUARDA NA MEMÓRIA, E O SEGREDO NÃO.** `expires_in` vem na
resposta, e pedir token novo a cada chamada seria uma viagem a mais em cada
clique. O que **nunca** entra em memória nem em banco é o `client_secret`: ele
é lido do disco a cada renovação, pela mesma razão de sempre — o banco viaja no
backup, e o backup já saiu da serventia.

**SÃO DOIS MECANISMOS DE AUTENTICAÇÃO NA MESMA API, E ISSO É ARMADILHA.**
Medido nas 53 operações:

    bearerAuth   48 operações   `Authorization: Bearer <token da serventia>`
    headerAuth    4 operações   cabeçalho `token: <token DAQUELE protocolo>`

    As quatro do `headerAuth` são os **detalhes do protocolo** (v1 e v2) e a
    validação delas. O token delas **não é o da casa**: sai de
    `POST /v1/protocolo/{n}/token`, e vale para aquele protocolo. Mandar o
    `Bearer` ali devolve 401 sem dizer por quê.

**E TRÊS CAMINHOS NÃO DECLARAM SEGURANÇA.** Um é o `/v1/auth/token`, e está
certo. Os outros dois são `POST /v1/edital/cobranca` e
`PATCH /v1/edital/cobranca/{numeroDocumento}` — mesma Central, mesma
credencial. **É omissão do contrato**, e há teste que fica vermelho quando
corrigirem.

**O `oauth2` DECLARADO APONTA PARA LUGAR NENHUM.** O contrato traz três
esquemas de segurança, e o do `oauth2` tem
`"tokenUrl": "https://teste/oauth2/token"` — endereço que não existe. É sobra
de configuração deles; vale o `/v1/auth/token`, que é o que a documentação
descreve e o que as operações usam.

**O ENUM DESTE CONTRATO É DOCUMENTAÇÃO, E NÃO VALOR.** Os campos de código são
`type: integer` e trazem `enum: ["64 = Casa", "65 = Apto", …]` — **strings com
o número, o sinal de igual e o nome**. Quem mandar `"64 = Casa"` manda texto
onde a Central espera número. `codigos_do_enum` parte a lista e devolve
`{64: "Casa"}`; é dela que saem os vocabulários deste módulo, e há teste que a
roda contra o contrato.

O QUE ESTE MÓDULO LIGA, E O QUE ELE SÓ DECLARA
    **25 das 53 operações** (marco B, 05/10/2026). Além do indicador,
    do edital e da fila, passam a estar ligadas: **SAEC** (atendimento
    eletrônico — listar/consultar/interagir), **protocolo** (lista,
    base, token v2, detalhes v2 e validação do token) e **cobrança**
    (lista, detalhe, tipos de pagamento e gerar). O resto fica só
    declarado — leilão, extração, devolução PIX, lote, download —
    para ninguém reinventar caminho que some da lista.

    **Os 28 ficam em `CAMINHO`**, com método e nome.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.parse
from typing import Any

import centrais_cred as CRED
import centrais_http as HTTP

# OS DOIS AMBIENTES, **do próprio contrato** (`servers`). A ordem ali é
# produção-primeiro; aqui a casa começa na de testes.
BASE_POR_AMBIENTE: dict[str, str] = {
    CRED.PRODUCAO: "https://api.registrodeimoveis.org.br",
    CRED.HOMOLOGACAO: "https://testes-api.registrodeimoveis.org.br",
}

CONTRATO_NO_PROJETO = "FONTES_EXTERNAS/onr_ri/openapi_limpo.json"
CONTRATO_COMO_ELES_PUBLICAM = "FONTES_EXTERNAS/onr_ri/openapi.json"

PRAZO_PADRAO = 60
TENTATIVAS_DE_REDE = 2

# QUANTO ANTES DE VENCER SE PEDE TOKEN NOVO. Sessenta segundos: a chamada
# seguinte não pode sair com um token que vence no caminho.
MARGEM_DO_TOKEN = 60

CABECALHO_DO_TOKEN = "Authorization"
PREFIXO_DO_TOKEN = "Bearer "
# O SEGUNDO MECANISMO — ver o cabeçalho. Quatro operações, e o token é DAQUELE
# protocolo.
CABECALHO_DO_TOKEN_DO_PROTOCOLO = "token"

TIPO_DO_FORMULARIO = "application/x-www-form-urlencoded"
GRANT_DA_CASA = "client_credentials"


# ------------------------------------------------------------- os caminhos
#
# `:x` marca o pedaço que se substitui. **Os 39 estão aqui** — inclusive os que
# este módulo não liga, porque caminho que some da lista é caminho que alguém
# reinventa.

CAMINHO: dict[str, str] = {
    # --- autenticação
    "token": "/v1/auth/token",
    "validar_token": "/v1/auth/validacao",
    # --- indicador real (o índice real que o ONR reúne nacionalmente)
    "indicadores": "/v1/indicador/real",
    "indicador_enviar": "/v1/indicador/real",
    "indicador": "/v1/indicador/real/:hash",
    "indicador_atualizar": "/v1/indicador/real/:hash",
    "indicador_excluir": "/v1/indicador/real/:hash",
    "indicador_atos": "/v1/indicador/real/:hash/atos",
    "indicador_ato_atualizar": "/v1/indicador/real/ato/:hash",
    "indicador_ato_excluir": "/v1/indicador/real/ato/:hash",
    "indicador_upload": "/v1/indicador/real/upload",
    # --- protocolo (o título que chega eletrônico)
    "protocolos": "/v1/protocolo",
    "protocolo_enviar": "/v1/protocolo",
    "protocolo": "/v1/protocolo/:numero",
    "protocolo_excluir": "/v1/protocolo/:numero",
    "protocolo_detalhes": "/v1/protocolo/:numero/detalhes",
    "protocolo_detalhes_v2": "/v2/protocolo/:numero/detalhes",
    "protocolo_lote": "/v1/protocolo/lote",
    "protocolo_token": "/v1/protocolo/:numero/token",
    "protocolo_token_v2": "/v2/protocolo/:numero/token",
    "protocolo_token_validar": "/v1/protocolo/:numero/token/validacao",
    "protocolo_token_validar_v2": "/v2/protocolo/:numero/token/validacao",
    "protocolo_download": "/v1/protocolo/:numero/download/:hash",
    # --- edital (o do usucapião, e o de leilão)
    "editais": "/v1/edital",
    "edital_gerar": "/v1/edital",
    "edital": "/v1/edital/:numero",
    "edital_retificar": "/v1/edital/:numero",
    "edital_cancelar": "/v1/edital/:numero",
    "edital_tipos": "/v1/edital/tipo",
    "edital_cobranca": "/v1/edital/cobranca",
    "edital_cobranca_atualizar": "/v1/edital/cobranca/:documento",
    "edital_leilao_gerar": "/v1/edital/leilao",
    "edital_leilao": "/v1/edital/leilao/:numero",
    "edital_leilao_retificar": "/v1/edital/leilao/:numero",
    "edital_leilao_cancelar": "/v1/edital/leilao/:numero",
    "edital_extracao_pedir": "/v1/edital/extracao",
    "edital_extracoes": "/v1/edital/extracao",
    "edital_extracao": "/v1/edital/extracao/:hash",
    "edital_extracao_dados": "/v1/edital/extracao/dados/:hash",
    "edital_extracao_baixar": "/v1/edital/extracao/download/:hash",
    # --- fila de processamento (o que aconteceu com o que subiu)
    "fila": "/v1/fila/processamento/protocolo",
    "fila_detalhes": "/v1/fila/processamento/protocolo/:hash",
    # --- atendimento eletrônico
    "atendimentos": "/v1/atendimento/eletronico",
    "atendimento": "/v1/atendimento/eletronico/:id",
    "atendimento_interagir": "/v1/atendimento/eletronico/interacao/:id",
    # --- cobrança
    "cobranca_gerar": "/v1/cobranca",
    "cobrancas": "/v1/cobranca",
    "cobranca_cadastrar": "/v1/cobranca/cadastrar",
    "cobranca_tipos_de_pagamento": "/v1/cobranca/tipo/pagamento",
    "cobranca": "/v1/cobranca/:hash",
    "cobranca_cancelar": "/v1/cobranca/:hash",
    "cobranca_devolver_pix": "/v1/cobranca/:hash/pix/devolucao",
    "cobranca_protocolo": "/v1/cobranca/:hash/protocolo",
}

METODO_DO_CAMINHO: dict[str, str] = {
    "token": "POST", "validar_token": "GET",
    "indicadores": "GET", "indicador_enviar": "POST", "indicador": "GET",
    "indicador_atualizar": "PATCH", "indicador_excluir": "DELETE",
    "indicador_atos": "GET", "indicador_ato_atualizar": "PATCH",
    "indicador_ato_excluir": "DELETE", "indicador_upload": "POST",
    "protocolos": "GET", "protocolo_enviar": "POST", "protocolo": "GET",
    "protocolo_excluir": "DELETE", "protocolo_detalhes": "GET",
    "protocolo_detalhes_v2": "GET", "protocolo_lote": "POST",
    "protocolo_token": "POST", "protocolo_token_v2": "POST",
    "protocolo_token_validar": "GET", "protocolo_token_validar_v2": "GET",
    "protocolo_download": "GET",
    "editais": "GET", "edital_gerar": "POST", "edital": "GET",
    "edital_retificar": "PUT", "edital_cancelar": "DELETE",
    "edital_tipos": "GET", "edital_cobranca": "POST",
    "edital_cobranca_atualizar": "PATCH", "edital_leilao_gerar": "POST",
    "edital_leilao": "GET", "edital_leilao_retificar": "PUT",
    "edital_leilao_cancelar": "DELETE", "edital_extracao_pedir": "POST",
    "edital_extracoes": "GET", "edital_extracao": "GET",
    "edital_extracao_dados": "GET", "edital_extracao_baixar": "GET",
    "fila": "GET", "fila_detalhes": "GET",
    "atendimentos": "GET", "atendimento": "GET",
    "atendimento_interagir": "POST",
    "cobranca_gerar": "POST", "cobrancas": "GET",
    "cobranca_cadastrar": "POST", "cobranca_tipos_de_pagamento": "GET",
    "cobranca": "GET", "cobranca_cancelar": "PATCH",
    "cobranca_devolver_pix": "PUT", "cobranca_protocolo": "PATCH",
}

# OS QUE ESTE MÓDULO LIGA. Ver o cabeçalho: os outros servem coisas que esta
# casa não faz pelo ONR.
CAMINHOS_LIGADOS: tuple[str, ...] = (
    "token", "validar_token",
    "indicadores", "indicador_enviar", "indicador", "indicador_atualizar",
    "editais", "edital_gerar", "edital", "edital_cancelar", "edital_tipos",
    "fila", "fila_detalhes",
    # --- SAEC / protocolo / cobranca (marco B)
    "atendimentos", "atendimento", "atendimento_interagir",
    "protocolos", "protocolo", "protocolo_token_v2",
    "protocolo_detalhes_v2", "protocolo_token_validar_v2",
    "cobrancas", "cobranca", "cobranca_tipos_de_pagamento", "cobranca_gerar",
)

# **QUATRO FUNCOES FORAM APAGADAS, E NAO DESLIGADAS** — 03/09/2026, depois de o
# varredor de funcao orfa as apontar. Sao `atos_do_indicador`,
# `excluir_indicador`, `retificar_edital` e `detalhes_do_protocolo`: eu as
# escrevi «para o caso de», e neste projeto funcao pronta sem chamador e a arma
# que alguem religa depois sem saber por que ela existia — ja aconteceu mais de
# dez vezes.
#
#   **Os caminhos delas continuam declarados em `CAMINHO`**, com o metodo, para
#   ninguem os reinventar achando que sumiram. E a decisao do `renegociacoes()`
#   da CENPROT.
#
#   O `protocolo_detalhes_v2` merece nota: ele e a prova viva do **segundo
#   mecanismo de autenticacao** deste contrato, e o teste continua guardando
#   isso — as quatro operacoes do `headerAuth` estao conferidas contra o
#   contrato, e `_bater` recusa chama-las sem o token daquele protocolo.
CAMINHOS_APAGADOS_MAS_DECLARADOS: tuple[str, ...] = (
    # Funcoes apagadas de proposito (sem chamador). Detalhes v1 fica de fora:
    # o fluxo ligado e o v2 + token do protocolo.
    "indicador_atos", "indicador_excluir", "edital_retificar",
    "protocolo_detalhes",
)

# AS QUATRO QUE USAM O OUTRO CABEÇALHO — e o token delas é DAQUELE protocolo.

# MARCO B (05/10/2026): `protocolos`, `protocolo`, `protocolo_token_v2`
# e `protocolo_detalhes_v2` voltaram a `CAMINHOS_LIGADOS` — o pedido do
# cartorio e testar SAEC/protocolo/cobranca com mock, sem rede real.
# `protocolo_detalhes` (v1) continua so declarado.
CAMINHOS_COM_TOKEN_DO_PROTOCOLO: frozenset[str] = frozenset({
    "protocolo_detalhes", "protocolo_detalhes_v2",
    "protocolo_token_validar", "protocolo_token_validar_v2"})

# OS DOIS QUE O CONTRATO ESQUECEU DE DECLARAR (fora o `/auth/token`, que está
# certo). Ver o cabeçalho — há teste que fica vermelho quando corrigirem.
CAMINHOS_SEM_SEGURANCA_DECLARADA: frozenset[str] = frozenset({
    "edital_cobranca", "edital_cobranca_atualizar"})


class OnrError(RuntimeError):
    """Não deu para falar com o ONR, ou ele recusou a credencial."""


class OnrRecusou(OnrError):
    """O ONR respondeu, e disse não. A frase dele vai junto."""


# ------------------------------------------------------- os vocabulários


def codigos_do_enum(valores: Any) -> dict[int, str]:
    """`["64 = Casa", "65 = Apto"]` → `{64: "Casa"}`.

    **O ENUM DESTE CONTRATO É DOCUMENTAÇÃO, E NÃO VALOR.** O campo é
    `type: integer` e o `enum` traz strings com o número, o igual e o nome.
    Quem mandar a string manda texto onde a Central espera número.

    Linha que não estiver nessa forma **é ignorada**, e não vira código
    inventado.
    """
    saida: dict[int, str] = {}
    for bruto in (valores or []):
        achado = re.match(r"\s*(\d+)\s*=\s*(.+?)\s*$", str(bruto))
        if achado:
            saida[int(achado.group(1))] = achado.group(2)
    return saida


# Transcritos do contrato, e conferidos por teste contra ele. Só os que este
# módulo usa: os 129 tipos de logradouro ficam de fora de propósito — a casa
# guarda o logradouro como texto e não tem de onde tirar o código.
TIPOS_DE_REGISTRO: dict[int, str] = {
    1: "Matrícula", 2: "Transcrição", 3: "Torrens", 4: "Título definitivo"}
SITUACOES_DE_CONSTRUCAO: dict[int, str] = {
    0: "Construção Averbada", 1: "Em construção", 2: "Não se aplica"}
LOCALIZACOES: dict[int, str] = {1: "Urbano", 3: "Rural"}

# **A LOCALIZAÇÃO PULA O 2**, e isso não é engano de transcrição: é o catálogo
# deles. Quem preencher a sequência óbvia acerta o tipo e erra o conteúdo — a
# lição dos catálogos do IBGE.
LOCALIZACAO_PULA_O_DOIS = True




# <<< vocabularios do ONR — gerado por tools/gerar_logradouros.py
#
# **UMA ENTRADA POR LINHA, e nao embrulhado.** A primeira versao deste gerador
# usou `textwrap.wrap` e **partiu nomes no meio** — «Praça de\nEsportes» —,
# produzindo um arquivo que nem compilava. Quem pegou foi o `ruff`, com vinte e
# cinco erros de sintaxe; a licao e que texto que contem espaco nao se quebra
# por largura.
#
# Eles entram aqui em vez de serem lidos em tempo de execucao porque o contrato
# mora em `FONTES_EXTERNAS`, que **nao viaja no `.cgu`**. Ha teste que compara
# os tres com o contrato.


def sem_acento(texto: Any) -> str:
    """Sem acento e sem caixa. **O que a casa guarda chega escrito de todo
    jeito**, e o de-para casa pelo NOME."""
    cru = "" if texto is None else str(texto)
    return "".join(
        c for c in unicodedata.normalize("NFD", cru)
        if unicodedata.category(c) != "Mn").casefold()


# A CONVERSÃO DE ÁREA MUDOU DE CASA EM 15/09/2026, e o motivo é medido: o
# `montar_indicador` montava o campo `area` do indicador real com o **número
# cru** da ficha. Medido nas 1.387 linhas com unidade de hectare: a matrícula
# 2580 tem `63 ha` e ia ao índice nacional como **63 m²**. Dez mil vezes menos,
# num campo que diz de quem é o imóvel e de que tamanho ele é.
#
# **ELA MORA AQUI E NÃO EM `onr_endereco_do_teor`, E A RAZÃO É O CICLO.** Aquele
# módulo importa `partir_logradouro` de `ri_onr_central`, e `ri_onr_central`
# precisa desta conversão — deixá-la lá poria os dois a dependerem um do outro.
# Aqui é a casa da **forma do contrato** (é onde `sem_acento` e os vocabulários
# moram), e os dois módulos já importam este, cada um do seu lado. **Uma
# definição só**, e é a mesma que a proposta do endereço usa.
# **UMA PALAVRA QUE FALTAVA NA LISTA VALEU DEZ FICHAS — 16/09/2026.** Enquanto a
# unidade vinha da COLUNA, a lista bastava (`"m2"`); quando a régua passou a ler
# a unidade **ESCRITA no teor** — que é o certo, e é o conserto do `_inteiro` —,
# dez fichas desta casa caíram no ramo do hectare, e cada uma por dez mil vezes:
# `13.200 metros quadrados` virou **132.000 m²**.
#
# São dez lotes urbanos de poucas centenas de metros — 2902, 924, 1459, 1007,
# 817, 815, 816, 1616, 1609 e 1615 —, e **nenhum deles é hectare**: a maior é
# `3.089,61 metros quadrados`. O `metros quadrado` (sem o plural) está aqui
# porque é como a 1616 escreve, e quem o manda ao índice sem traduzir está
# mandando o número certo com o sentido errado.
_UNIDADE_EM_METROS = ("m", "m2", "m²", "metro", "metros", "mts", "mt",
                      "metro quadrado", "metros quadrados", "metros quadrado")


def unidade_canonica(unidade: Any) -> str:
    """`"m2"`, `"ha"` ou `""` — a grafia da casa traduzida para a do contrato.

    **A MESMA UNIDADE SE ESCREVE DE MUITAS FORMAS AQUI**: a coluna escreve `ha`
    ou `m2`, a ficha escreve `há`, `hectares`, `metros`, `metros quadrados` — e
    quem decide se converte precisa da resposta em duas palavras, não de uma
    lista de sinônimos repetida em cada módulo.

    **E `""` NÃO É `"ha"`**: o vazio quer dizer «a casa não escreveu», e quem
    chama mantém o ramo do hectare por padrão, que é a regra medida das 1.298
    linhas sem separador. Medido em 16/09/2026: `area_unidade` só tem `ha`
    (1.387), `m2` (318) e vazio (277).
    """
    u = re.sub(r"\s+", " ", sem_acento(unidade)).strip()
    if not u:
        return ""
    return "m2" if u in _UNIDADE_EM_METROS else "ha"


def area_em_metros(valor: Any, unidade: Any = None) -> int | None:
    """A área **em metros quadrados**, inteira, que é a forma do contrato.

    **AS TRÊS FORMAS DA CASA PARA HECTARE, e o número que perdeu a parte
    decimal não cabe na mesma conta:**

        231,00,00 ha = 231 ha 00 a 00 ca =  2.310.000 m²
        231,0233  ha  = 231,0233 ha       =  2.310.233 m²
        347.0168  ha  = 347,0168 ha       =  3.470.168 m²   (o ponto é a vírgula)
        09,00,00  ha  = 9 ha              =     90.000 m²

    > **E EU ESCREVI AQUI QUE A CONTA ANTIGA ACERTAVA — ESTAVA ERRADO.** A
    > primeira versão dizia que `_inteiro(area_valor)` «acerta os três casos por
    > construção», e que eu não devia mexer no que estava certo. **Medido em
    > 15/09/2026 nas 1.387 linhas de `ri_matriculas` com unidade de hectare:**
    >
    > | | |
    > |---|---|
    > | **1.298** | sem separador, de 1 a 3 dígitos — `63`, `131`, `1`, `9` |
    > | 64 | com separador — a régua de cima vale |
    > | 7 | 6 ou mais dígitos, já em metros |
    > | **18** | 4 ou 5 dígitos — ambíguas, e são `None` |
    >
    > **O erro não era da função: era de eu ter medido três exemplos, e os três
    > com vírgula.** As 1.298 nunca foram olhadas, e são a maioria — é assim que
    > a casa escreve hectare quando ele é redondo. Ler `63` como metros quadrados
    > dá **63 m²** onde são **630.000 m²**: dez mil vezes menos, num número que
    > vai para o índice que o país consulta para saber de quem é o imóvel.
    > **O `×10.000` só vale quando a fração está escrita.**

    A régua depende de o número ter fração escrita:

    * **com vírgula ou ponto** → converte-se de verdade, e os dígitos finais são
      a fração (as quatro formas acima, mais `48.8` e `53.816`);
    * **só dígitos, 1 a 3** → hectares inteiros, ×10.000 (`63` → 630.000 m²);
    * **só dígitos, 6 ou mais** → já estão em metros (`27368100`, `2310233`);
    * **só dígitos, 4 ou 5** → **indefinido, e devolve `None`**: `3808` tanto
      pode ser 38,08 ha quanto 3.808 m², e chutar num lado erra por cem vezes.
      São **18 linhas**, e a proposta as declara em vez de as inventar.

    A unidade em metro tem régua própria, e `_metros_quadrados` a explica:
    `8.435,26 m²` são 8.435 metros e não 843.526, e **ali o ponto é decimal
    quando tem um ou dois dígitos depois dele** — o que só se soube medindo.

    **E A UNIDADE PODE CHEGAR ESCRITA EM PALAVRA** — `metros quadrados`,
    `metros quadrado`, `metro quadrado` —, que é como a ficha a escreve quando
    a escreve. Elas estão em `_UNIDADE_EM_METROS` desde 16/09/2026, e não desde
    sempre: **a lista nasceu para a coluna, onde a casa escreve `m2`**, e a
    régua que lê a unidade escrita no teor (o conserto do `_inteiro`) passou a
    mandar palavras para ela. Sem as três, dez fichas desta casa foram lidas
    como hectares — a 2902 diz `13.200 metros quadrados` e ia ao índice como
    **132.000 m²**.

    **QUEM A CHAMA, em 15/09/2026**: `ri_onr_central.montar_indicador` (o campo
    `area` do indicador real) e `onr_endereco_do_teor` (a proposta do endereço,
    que a compara com o que a coluna diz). **Eram dois lugares e um deles não a
    chamava** — era exatamente o defeito que a docstring acima narra.
    """
    cru = "" if valor is None else str(valor).strip()
    if not cru:
        return None
    # **SÓ O PRIMEIRO NÚMERO** — achado em 11/10/2026 na matrícula 4011, cuja
    # coluna guarda «19,3419 ha (dezenove hectares, trinta e quatro ares e
    # dezenove centiares)». Os dígitos do texto inteiro davam 1.934.190.000 m²
    # (dez mil vezes a área), e o número por extenso não tem dígito nenhum a
    # acrescentar: o primeiro número escrito é a área.
    primeiro = re.search(r"\d(?:[\d.,]*\d)?", cru)
    if primeiro and re.search(r"[A-Za-zÀ-ÿ(]", cru[primeiro.end():]):
        cru = cru[:primeiro.end()].strip()
    # **O ESPAÇO É NORMALIZADO PORQUE O TEOR O ESCREVE DE TODO JEITO**: o padrão
    # que lê a unidade aceita `metros\s+quadrados`, e o que chega aqui pode vir
    # com dois espaços. Sem isto a forma palavra passaria ao lado da lista e
    # cairia no hectare — o defeito das dez fichas de 16/09/2026.
    u = unidade_canonica(unidade)
    so_digitos = re.sub(r"\D", "", cru)
    if not so_digitos:
        return None
    if u == "m2":
        return _metros_quadrados(cru, so_digitos)
    return _hectares_em_metros(cru, so_digitos)


def _metros_quadrados(cru: str, so_digitos: str) -> int | None:
    """A forma escrita em metro, que é a mais fácil e a que mais se erra.

    **O PONTO AQUI É DECIMAL QUANDO TEM UM OU DOIS DÍGITOS DEPOIS DELE** — e
    isso não se deduz, mede-se. Nas **11** matrículas desta casa com unidade
    `m2` e separador, o ponto é decimal em todas: `9.7`, `31.47`, `181.9`,
    `4.25`, `0.1`. A primeira versão desta função lia **todas** como milhar
    (`9.7` → 9, `31.47` → 31) porque a regra do milhar estava escrita para o
    hectare, onde o separador de milhar é ponto de verdade (`1.154,00`).

    E o pior delas não é a perda de menos de um metro: **`0.1` virava `0`**, e
    zero num campo de área não é «quase nada» — é a afirmação de que o imóvel
    não tem área. **Zero devolve `None`**, aqui e na vírgula.

    Com **três** dígitos depois do ponto ele é milhar, que é a forma
    `8.435,26` — mas essa já chega com vírgula, e quem a separa é o ramo de
    cima. Nenhuma das 11 reais tem três dígitos depois do ponto.

    > **E ESTA ÚLTIMA FRASE FICOU FALSA EM 16/09/2026 — ela media a COLUNA, e
    > quem passou a escrever aqui foi o TEOR.** A régua que lê a unidade escrita
    > na ficha (`_a_unidade_escrita`) manda a este ramo números que a coluna
    > nunca teve: medido contra a cópia da produção, **1 das 1.551 matrículas
    > com teor** escreve a área assim — a **2902**, «O terreno tem uma área de
    > 13.200 metros quadrados», num lote que a mesma ficha descreve com 300 m de
    > frente e 49 m de fundo. **`13.200` virava `13`**: mil vezes menos, no
    > campo que diz de quem é o imóvel e de que tamanho ele é. A medição das 11
    > linhas estava certa e respondia por outra coisa — **a coluna escreve o
    > decimal com um ou dois dígitos; o teor escreve o milhar inteiro.**
    """
    numero = cru.replace(" ", "")
    if "," in numero:
        # `8.435,26`: a vírgula é o decimal, e o ponto é o milhar.
        inteiro = numero.split(",")[0]
        return int(re.sub(r"\D", "", inteiro) or so_digitos) or None
    if "." in numero:
        partes = numero.split(".")
        antes, _, depois = numero.rpartition(".")
        digitos_depois = re.sub(r"\D", "", depois)
        if digitos_depois and len(digitos_depois) <= 2:
            antes_digitos = re.sub(r"\D", "", antes) or "0"
            try:
                return int(round(float(antes_digitos + "." + digitos_depois))) or None
            except ValueError:  # pragma: no cover - os dígitos já foram conferidos
                return None
        # **A FORMA DO MILHAR INTEIRO, SEM VÍRGULA**: grupos de exatamente três
        # dígitos depois do primeiro — `13.200`. É a 2902, e a única do teor.
        # **A VÍRGULA CONTINUA MANDANDO** quando existe (o ramo de cima), e o
        # ponto com um ou dois dígitos continua decimal (as 11 da coluna): o que
        # esta guarda pega é só o número que nenhuma das duas alcançava.
        if len(partes) > 1 and len(re.sub(r"\D", "", partes[0])) <= 3 \
                and all(len(re.sub(r"\D", "", p)) == 3 for p in partes[1:]):
            return int(re.sub(r"\D", "", numero)) or None
        return int(re.sub(r"\D", "", antes) or so_digitos) or None
    return int(so_digitos) or None


def _hectares_em_metros(cru: str, so_digitos: str) -> int | None:
    """A forma escrita em hectare, convertida — ou `None` quando não se sabe.

    O `None` é resposta, e não falha: as de 4 e 5 dígitos sem separador são
    ambíguas, e quem chama prefere não saber a saber errado por cem vezes.
    """
    partes = re.split(r"[.,]", cru)
    # A FORMA DA CASA: hectares, ares e centiares — `231,00,00`. Os dois grupos
    # de trás têm dois dígitos cada; em `1.154,00` o grupo do meio tem três, e
    # ali ele é MILHAR, e não ares.
    #
    # **E A FORMA DA CASA TAMBÉM TEM MILHAR NOS HECTARES** — `3.108,08,06 ha`,
    # `2.166.13.37 ha`, achadas em 11/10/2026 ao gerar o XML do Indicador Real:
    # quatro grupos caíam na régua do milhar e saíam MIL VEZES maiores (a 2556
    # com 3.108.008 ha, mais que o município). Os dois grupos de trás com até
    # dois dígitos são ares e centiares; os do meio, com três, são milhar.
    digs = [re.sub(r"\D", "", p) for p in partes]
    if len(partes) >= 3 and len(digs[-1]) <= 2 and len(digs[-2]) <= 2 \
            and all(len(d) == 3 for d in digs[1:-2]):
        h = int("".join(digs[:-2]) or 0)
        return h * 10_000 + int(digs[-2] or 0) * 100 + int(digs[-1] or 0)
    if len(partes) >= 2:
        inteiro = re.sub(r"\D", "", partes[0]) or "0"
        # Os grupos do meio são milhar: `1.154,00` → 1154.
        if len(partes) > 2:
            inteiro += "".join(
                re.sub(r"\D", "", p).zfill(3) for p in partes[1:-1])
        decimal = re.sub(r"\D", "", partes[-1])
        if not decimal:
            return int(inteiro) * 10_000
        try:
            return int(round(float(f"{inteiro}.{decimal}") * 10_000))
        except ValueError:  # pragma: no cover - o dígito já foi conferido acima
            return None
    if len(so_digitos) <= 3:
        return int(so_digitos) * 10_000
    if len(so_digitos) >= 6:
        return int(so_digitos)
    return None


# **OS TIPOS DE LOGRADOURO SERVEM AOS DOIS LADOS DO MESMO CONTRATO**, que e a
# razao de a tabela existir: no `indicadorRealRequest` o `tipoLogradouro` e um
# **integer** (o codigo), e no `editalRequest` e um **string max=16** (o nome).
# Mesmo nome de campo, dois tipos, no mesmo documento.
TIPOS_DE_LOGRADOURO: dict[int, str] = {
    1: 'Acesso',
    2: 'Adro',
    4: 'Alameda',
    5: 'Alto',
    7: 'Atalho',
    8: 'Avenida',
    9: 'Balneário',
    10: 'Belvedere',
    11: 'Beco',
    12: 'Bloco',
    13: 'Bosque',
    14: 'Boulevard',
    15: 'Baixa',
    16: 'Cais',
    17: 'Caminho',
    19: 'Chapadão',
    20: 'Conjunto',
    21: 'Colônia',
    22: 'Corredor',
    23: 'Campo',
    24: 'Córrego',
    27: 'Desvio',
    28: 'Distrito',
    30: 'Escada',
    31: 'Estrada',
    32: 'Estação',
    33: 'Estádio',
    36: 'Favela',
    37: 'Fazenda',
    38: 'Ferrovia',
    39: 'Fonte',
    40: 'Feira',
    43: 'Forte',
    45: 'Galeria',
    46: 'Granja',
    50: 'Ilha',
    52: 'Jardim',
    53: 'Ladeira',
    54: 'Largo',
    55: 'Lagoa',
    56: 'Loteamento',
    59: 'Morro',
    60: 'Monte',
    62: 'Paralela',
    63: 'Passeio',
    64: 'Pátio',
    65: 'Praça',
    67: 'Parada',
    70: 'Praia',
    71: 'Prolongamento',
    72: 'Parque',
    73: 'Passarela',
    74: 'Passagem',
    76: 'Ponte',
    77: 'Quadra',
    79: 'Quinta',
    81: 'Rua',
    82: 'Ramal',
    87: 'Recanto',
    88: 'Retiro',
    89: 'Reta',
    90: 'Rodovia',
    91: 'Retorno',
    92: 'Sítio',
    94: 'Servidão',
    95: 'Setor',
    96: 'Subida',
    97: 'Trincheira',
    98: 'Terminal',
    99: 'Trevo',
    100: 'Travessa',
    101: 'Via',
    103: 'Viaduto',
    104: 'Vila',
    105: 'Viela',
    106: 'Vale',
    108: 'Zigue-Zague',
    452: 'Trecho',
    453: 'Vereda',
    465: 'Artéria',
    468: 'Elevada',
    469: 'Porto',
    470: 'Balão',
    471: 'Paradouro',
    472: 'Ýrea',
    473: 'Jardinete',
    474: 'Esplanada',
    475: 'Quintas',
    476: 'Rótula',
    477: 'Marina',
    478: 'Descida',
    479: 'Circular',
    480: 'Unidade',
    481: 'Chácara',
    482: 'Rampa',
    483: 'Ponta',
    484: 'Via de Pedestre',
    485: 'Condomínio',
    486: 'Habitacional',
    487: 'Residencial',
    495: 'Canal',
    496: 'Buraco',
    497: 'Módulo',
    498: 'Estância',
    499: 'Lago',
    500: 'Núcleo',
    501: 'Aeroporto',
    502: 'Passagem Subterrânea',
    503: 'Complexo Viário',
    504: 'Praça de Esportes',
    505: 'Via Elevado',
    506: 'Rotatória',
    564: 'Estacionamento',
    565: 'Vala',
    566: 'Rua de Pedestre',
    567: 'Túnel',
    568: 'Variante',
    569: 'Rodo Anel',
    570: 'Travessa Particular',
    571: 'Calçada',
    572: 'Via de Acesso',
    573: 'Entrada Particular',
    645: 'Alameda',
    646: 'Via Expressa',
    650: 'Estrada Municipal',
    651: 'Avenida Contorno',
    652: 'Entre Quadra',
    653: 'Rua de Ligação',
    654: 'Ýrea Especial',
}

# **UM NOME APARECE DUAS VEZES NO CATALOGO DELES**: «Alameda» e 4 e 645.
# Medido, e nao suposto. Para o caminho contrario — do nome para o codigo — o
# sistema fica com o **menor**, que e o da sequencia; a duplicata fica
# declarada para quem for conferir nao achar que a leitura se perdeu.
NOMES_REPETIDOS_NO_CATALOGO: dict[str, tuple[int, ...]] = {
    "Alameda": (4, 645),
}

# **O CONTRATO DELES ESCREVE «Ýrea» ONDE QUER DIZER «Área»**, e o glifo
# U+00DD (Ý) **nao existe em portugues** — o que faz dele, sozinho, prova de
# corrupcao. Medido em 15/09/2026: dos 129 nomes, **exatamente dois** o
# carregam, o 472 («Ýrea») e o 654 («Ýrea Especial»), e sao a MESMA palavra.
# A prosa do proprio contrato fecha a leitura: o campo `area` esta descrito
# como «Ýrea em metros quadrados do imovel rural…», onde `Ýrea` so pode ser
# «Area».
#
# **A TABELA ACIMA FICA COMO O CONTRATO A ESCREVEU**, e nao se emenda: o nome
# e o que o EDITAL manda (ali `tipoLogradouro` e `string max=16`), e inventar
# o que o outro lado escreveu seria pior que transcrever o defeito dele. Ha
# teste que compara os 129 com o contrato, e ele nao sabe deste mapa.
#
# O que entra aqui e so o caminho do NOME PARA O CODIGO — que e o que o
# indicador real usa: ele manda `472`, um integer, onde o glifo nem aparece.
# Sem isto a casa escrevia «Area», `sem_acento` levava o catalogo a `yrea`, e
# os dois nunca se encontravam: **o 472 existia e a regua nao o alcancava** —
# e o `tipoLogradouro` e OBRIGATORIO no indicador real, de modo que o ato
# inteiro era recusado por um caractere.
APELIDOS_DO_LOGRADOURO: dict[str, int] = {
    "area": 472,
    "area especial": 654,
}

TIPOS_DE_IMOVEL: dict[int, str] = {
    15: 'Loja',
    17: 'Sala',
    31: 'Galpão',
    33: 'Prédio Comercial',
    35: 'Prédio Residencial',
    64: 'Casa',
    65: 'Apto',
    69: 'Fazenda/Sítio/Chácara',
    71: 'Terreno/Fração',
    89: 'Outros',
}

TIPOS_DE_ATO: dict[int, str] = {
    11: 'Compra e Venda',
    13: 'Permuta',
    15: 'Adjudicação',
    19: 'Dação em Pagamento',
    21: 'Distrato de Negócio',
    25: 'Desapropriação',
    27: 'Herança, Legado ou Meação (adjudicação)',
    31: 'Procuração em Causa Própria',
    33: 'Promessa de Compra e Venda',
    35: 'Promessa de Cessão de Direitos',
    37: 'Cessão de Direitos',
    39: 'Outros',
    41: 'Arrematação em Hasta Pública',
    43: 'Dissolução de Sociedade',
    45: 'Incorporação e loteamento',
    47: 'Integralização/Subscrição de capital',
    49: 'Partilha amigável ou litigiosa',
    51: 'Retorno de Capital próprio',
    53: 'Doação',
    55: 'Doação em adiantamento da legítima',
    101: 'Usucapião',
    102: 'Alienação Fiduciária',
    103: 'Consolidação da Propriedade',
}


def _de_para(pares: dict[int, str]) -> dict[str, int]:
    """Do nome escrito para o codigo. **Menor codigo ganha** — ver acima."""
    saida: dict[str, int] = {}
    for codigo, nome in sorted(pares.items()):
        saida.setdefault(sem_acento(nome), codigo)
    return saida


CODIGO_DO_LOGRADOURO: dict[str, int] = _de_para(TIPOS_DE_LOGRADOURO)
# **Os apelidos entram DEPOIS do de-para, e nao dentro dele**: o `setdefault`
# do menor codigo so age em nome que ainda nao esta la, e o nome corrompido já
# está — `yrea`. Somar isto ao `_de_para` faria o apelido nao entrar, calado.
CODIGO_DO_LOGRADOURO.update(APELIDOS_DO_LOGRADOURO)
CODIGO_DO_IMOVEL: dict[str, int] = _de_para(TIPOS_DE_IMOVEL)
CODIGO_DO_ATO: dict[str, int] = _de_para(TIPOS_DE_ATO)
# >>> fim dos vocabularios do ONR

def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def base_do_ambiente(ambiente: Any = None) -> str:
    """O endereço daquele ambiente. **Os dois vêm do contrato.**"""
    onde = CRED._ambiente(ambiente) if ambiente else ambiente_da_casa()
    if onde not in BASE_POR_AMBIENTE:
        raise OnrError(f"O ONR não tem ambiente «{ambiente}».")
    return BASE_POR_AMBIENTE[onde]


def ambiente_da_casa() -> str:
    """Em que ambiente esta casa fala com o ONR.

    **Produção desde 15/10/2026** (ordem do oficial, com a produção já
    configurada): `centrais_cred` declara só ela para o ONR. Até então a casa
    começava na homologação, o primeiro da tabela.
    """
    return CRED.ambientes_de(CRED.ONR)[0]


# ------------------------------------------------------------ a credencial


def tem_credencial(ambiente: Any = None, *, pasta=None) -> bool:
    """A tela pergunta isto antes de oferecer botão. **Não devolve o segredo.**"""
    return CRED.tem(CRED.ONR, ambiente or ambiente_da_casa(), pasta)


def credencial(ambiente: Any = None, *, pasta=None) -> tuple[str, str]:
    """`(client_id, client_secret)`. **Lida do disco a cada renovação.**

    O `client_secret` **nunca** entra em memória guardada nem no banco: o banco
    viaja no backup, e o backup já saiu da serventia. O que se guarda é o
    **token**, que é derivado e vence sozinho.
    """
    return CRED.credencial(CRED.ONR, ambiente or ambiente_da_casa(), pasta)


# O TOKEN VIVE NA MEMÓRIA DO PROCESSO, por ambiente. Reiniciar o servidor o
# perde, e isso é certo: ele se pede de novo em milissegundos.
_TOKENS: dict[str, dict] = {}


def esquecer_o_token(ambiente: Any = None) -> None:
    """Joga fora o token guardado. A tela chama isto ao trocar a credencial."""
    if ambiente is None:
        _TOKENS.clear()
    else:
        _TOKENS.pop(CRED._ambiente(ambiente), None)


def token(ambiente: Any = None, *, pasta=None, agora: float | None = None) -> str:
    """O token de acesso, pedido ao ONR e guardado até perto de vencer.

    **`expires_in` vem na resposta**, e é ele que manda: pedir token novo a cada
    chamada seria uma viagem a mais em cada clique, e guardá-lo para sempre
    faria a casa mandar token vencido depois do primeiro dia.
    """
    onde = CRED._ambiente(ambiente or ambiente_da_casa())
    quando = time.time() if agora is None else agora
    guardado = _TOKENS.get(onde)
    if guardado and guardado["vence_em"] - MARGEM_DO_TOKEN > quando:
        return guardado["token"]

    ident, segredo = credencial(onde, pasta=pasta)
    corpo = urllib.parse.urlencode({
        "client_id": ident, "client_secret": segredo,
        "grant_type": GRANT_DA_CASA}).encode("utf-8")
    r = _bater_cru("POST", CAMINHO["token"], base=base_do_ambiente(onde),
                   corpo=corpo, tipo=TIPO_DO_FORMULARIO, cabecas={})
    if r["status"] not in (200, 201):
        raise OnrError(
            f"O ONR recusou a credencial da serventia (HTTP {r['status']}): "
            f"{_detalhe(r) or 'sem explicação'}. Confira o client_id e o "
            f"client secret em Administrativo → Configurações.")
    dados = r["json"] if isinstance(r["json"], dict) else {}
    # A resposta pode vir embrulhada em `data` — o contrato declara o schema
    # solto, e por isso se aceita as duas formas sem inventar nenhuma.
    if "access_token" not in dados and isinstance(dados.get("data"), dict):
        dados = dados["data"]
    novo = _texto(dados.get("access_token"))
    if not novo:
        raise OnrError(
            "O ONR respondeu à autenticação sem `access_token`. O corpo veio: "
            f"{_texto(r.get('texto'))[:200]}")
    try:
        dura = int(dados.get("expires_in") or 0)
    except (TypeError, ValueError):
        dura = 0
    # **SEM `expires_in` NÃO SE GUARDA.** Guardar «para sempre» faria a casa
    # mandar token vencido sem saber; pedir de novo custa uma viagem.
    if dura > 0:
        _TOKENS[onde] = {"token": novo, "vence_em": quando + dura}
    else:
        _TOKENS.pop(onde, None)
    return novo


# ------------------------------------------------------------ o transporte


def partes(base: str) -> tuple[str, int, str]:
    """Parte o endereço, **forçando https**.

    O `client_secret` e o token viajam nesta conexão, e com eles alguém envia
    indicador real e publica edital em nome desta serventia.
    """
    p = urllib.parse.urlsplit(base)
    if p.scheme != "https":
        raise OnrError(f"A base do ONR tem de ser https, e veio «{base}».")
    return p.hostname or "", p.port or 443, (p.path or "").rstrip("/")


def _bater_cru(metodo: str, caminho: str, *, base: str,
               corpo: bytes | None = None, tipo: str = "application/json",
               cabecas: dict | None = None, prazo: int = PRAZO_PADRAO) -> dict:
    """Uma requisição. Devolve `{status, json, texto}` — nunca estoura por 4xx.

    Transporte via `centrais_http` (marco a da base comum). Retentativa só em
    leitura (`GET`/`HEAD`/`OPTIONS`), com `tentativas=TENTATIVAS_DE_REDE` (2
    além da primeira) e `retentar_escrita=False`; POST/PUT/etc. não se repetem
    sozinhos. User-Agent = `USER_AGENT_PADRAO` (sem CNS no código).
    """
    hospedeiro, porta, prefixo = partes(base)
    autoridade = hospedeiro if porta == 443 else f"{hospedeiro}:{porta}"
    url = f"https://{autoridade}{prefixo}{caminho}"
    cabecalhos = dict(cabecas or {})
    if corpo is not None:
        cabecalhos["Content-Type"] = tipo
    verbo = str(metodo or "GET").strip().upper()
    # Alinhado a centrais_http: só leitura retenta.
    e_leitura = verbo in HTTP.METODOS_QUE_SO_LEEM
    try:
        return HTTP.requisitar(
            verbo, url, corpo=corpo, cabecalhos=cabecalhos,
            prazo=prazo,
            tentativas=TENTATIVAS_DE_REDE if e_leitura else 0,
            retentar_escrita=False,
            user_agent=HTTP.USER_AGENT_PADRAO,
        ).como_dict()
    except HTTP.CentralHttpError as erro:
        raise OnrError(
            f"Não consegui falar com o ONR em {hospedeiro}: "
            f"{erro.causa or erro}. Confira a internet da serventia e tente "
            f"de novo; nada foi enviado."
        ) from None


def _endereco(qual: str, **pedacos) -> str:
    caminho = CAMINHO[qual]
    for nome, valor in pedacos.items():
        marca = ":" + nome
        if marca in caminho:
            texto = urllib.parse.quote(_texto(valor), safe="")
            if not texto:
                raise OnrError(
                    f"O caminho «{qual}» precisa de «{nome}», e ele veio vazio.")
            caminho = caminho.replace(marca, texto)
    if ":" in caminho.split("?")[0].replace("://", ""):
        faltando = re.findall(r":(\w+)", caminho)
        raise OnrError(
            f"O caminho «{qual}» ficou com pedaço não preenchido: "
            + ", ".join(faltando))
    return caminho


def _consulta(parametros: dict | None) -> str:
    limpos = {k: v for k, v in (parametros or {}).items()
              if v not in (None, "", [])}
    return ("?" + urllib.parse.urlencode(limpos)) if limpos else ""


def _bater(qual: str, *, corpo: dict | None = None,
           parametros: dict | None = None,
           token_do_protocolo: str = "", ambiente: Any = None,
           prazo: int = PRAZO_PADRAO, pasta=None, **pedacos) -> dict:
    """Uma requisição autenticada. Escolhe **qual** dos dois cabeçalhos usar."""
    if qual not in CAMINHOS_LIGADOS:
        raise OnrError(
            f"O caminho «{qual}» está medido e não está ligado — ver o "
            f"cabeçalho de `onr_api`.")
    onde = CRED._ambiente(ambiente or ambiente_da_casa())
    cabecas: dict[str, str] = {}
    if qual in CAMINHOS_COM_TOKEN_DO_PROTOCOLO:
        # **O TOKEN DAQUELE PROTOCOLO, e não o da casa.** Ver o cabeçalho.
        if not _texto(token_do_protocolo):
            raise OnrError(
                f"O caminho «{qual}» usa o token DAQUELE protocolo, e não o da "
                f"serventia. Peça-o em «protocolo_token_v2» antes.")
        cabecas[CABECALHO_DO_TOKEN_DO_PROTOCOLO] = _texto(token_do_protocolo)
    else:
        cabecas[CABECALHO_DO_TOKEN] = PREFIXO_DO_TOKEN + token(
            onde, pasta=pasta)
    bruto = (json.dumps(corpo, ensure_ascii=False).encode("utf-8")
             if corpo is not None else None)
    return _bater_cru(METODO_DO_CAMINHO[qual],
                      _endereco(qual, **pedacos) + _consulta(parametros),
                      base=base_do_ambiente(onde), corpo=bruto, prazo=prazo,
                      cabecas=cabecas)


def _detalhe(r: dict) -> str:
    """A frase do ONR, se ele mandou uma.

    `ErroModel` declara `{codigo, descricao, campos}`, e é o `campos` que diz
    **qual campo** está errado — o que o escrevente precisa ler inteiro.
    """
    corpo = r.get("json")
    if isinstance(corpo, dict):
        partes_ = []
        for chave in ("descricao", "message", "mensagem", "error"):
            if corpo.get(chave):
                partes_.append(_texto(corpo[chave]))
                break
        campos = corpo.get("campos")
        if isinstance(campos, dict) and campos:
            partes_.append(" · ".join(
                f"{k}: {v}" for k, v in campos.items()))
        elif campos:
            partes_.append(_texto(campos))
        if partes_:
            return " — ".join(partes_)[:600]
    return _texto(r.get("texto"))[:400]


def _resposta_ou_erro(r: dict, o_que: str) -> Any:
    """Traduz o código do ONR numa resposta ou numa frase de balcão."""
    if r["status"] in (200, 201, 202, 204):
        return r["json"] if r["json"] is not None else r["texto"]
    if r["status"] in (401, 403):
        raise OnrError(
            f"O ONR recusou a credencial ao {o_que}. O token pode ter vencido "
            f"ou a credencial ter mudado: confira em Administrativo → "
            f"Configurações, na seção «Centrais — credenciais das APIs».")
    if r["status"] == 422:
        # **422 É A RECUSA QUE DIZ O QUE ESTÁ ERRADO**, e é a que mais aparece
        # numa integração nova. Vai inteira para a tela.
        raise OnrRecusou(f"O ONR recusou os dados ao {o_que}: {_detalhe(r)}")
    if r["status"] == 404:
        raise OnrRecusou(f"O ONR não encontrou o que se pediu ao {o_que}.")
    raise OnrRecusou(
        f"O ONR respondeu {r['status']} ao {o_que}: {_detalhe(r)}")


def _dados(resposta: Any) -> Any:
    """O `data` de dentro, quando a resposta vem embrulhada.

    Os esquemas `*ListarResponse` deste contrato declaram `{data: [...]}`; os
    de detalhe declaram `{data: {...}}`. **Aceitar as duas formas sem inventar
    nenhuma**: o que não vier embrulhado volta como veio.
    """
    if isinstance(resposta, dict) and "data" in resposta:
        return resposta["data"]
    return resposta


# ------------------------------------------------------------ a ligação


def esta_no_ar(*, ambiente: Any = None, pasta=None) -> dict:
    """Pergunta ao ONR se a credencial vale. **Usa `/v1/auth/validacao`.**

    Ela é a única operação que **prova o token sem afirmar nada** sobre
    indicador, protocolo ou edital — a mesma decisão do `BuscarApresentante` da
    CRA, que é a única sem parâmetro nenhum.
    """
    r = _bater("validar_token", ambiente=ambiente, prazo=25, pasta=pasta)
    return {"no_ar": r["status"] in (200, 201, 204), "status": r["status"],
            "resposta": _detalhe(r) or _texto(r.get("texto"))[:200]}


# ------------------------------------------------------- o indicador real


def indicadores(*, pagina: int = 1, por_pagina: int = 50,
                ambiente: Any = None, pasta=None) -> Any:
    """A lista dos indicadores reais já enviados. Só LÊ."""
    r = _bater("indicadores",
               parametros={"pagina": pagina, "limite": por_pagina},
               ambiente=ambiente, pasta=pasta)
    return _dados(_resposta_ou_erro(r, "buscar os indicadores reais"))


def enviar_indicador(corpo: dict, *, ambiente: Any = None, pasta=None) -> dict:
    """Envia um indicador real. **É o que alimenta o índice real nacional.**

    **Não confere campo obrigatório aqui**: o contrato declara doze, e quem os
    confere é o domínio — com a ficha do imóvel à vista e a recusa dizendo qual
    falta e onde se preenche.
    """
    r = _bater("indicador_enviar", corpo=dict(corpo or {}),
               ambiente=ambiente, pasta=pasta)
    resposta = _resposta_ou_erro(r, "enviar o indicador real")
    dados = _dados(resposta) or {}
    return {"hash": _texto(dados.get("hash") or dados.get("hashIndicador")),
             "corpo": corpo, "bruto": resposta}


def indicador(hash_indicador: Any, *, ambiente: Any = None, pasta=None) -> Any:
    """Um indicador real, como o ONR o tem. Só LÊ."""
    r = _bater("indicador", hash=hash_indicador, ambiente=ambiente, pasta=pasta)
    return _dados(_resposta_ou_erro(r, "buscar o indicador real"))




def atualizar_indicador(hash_indicador: Any, corpo: dict, *,
                        ambiente: Any = None, pasta=None) -> Any:
    """Corrige um indicador já enviado. **Não queima o hash.**"""
    r = _bater("indicador_atualizar", hash=hash_indicador,
               corpo=dict(corpo or {}), ambiente=ambiente, pasta=pasta)
    return _dados(_resposta_ou_erro(r, "atualizar o indicador real"))




# --------------------------------------------------------------- protocolo


def protocolos(*, pagina: int = 1, por_pagina: int = 50,
               ambiente: Any = None, pasta=None) -> Any:
    """A lista dos protocolos. Só LÊ."""
    r = _bater("protocolos", parametros={"pagina": pagina,
                                         "limite": por_pagina},
               ambiente=ambiente, pasta=pasta)
    return _dados(_resposta_ou_erro(r, "buscar os protocolos"))


def protocolo(numero: Any, *, ambiente: Any = None, pasta=None) -> Any:
    """Os dados básicos de um protocolo. Só LÊ."""
    r = _bater("protocolo", numero=numero, ambiente=ambiente, pasta=pasta)
    return _dados(_resposta_ou_erro(r, "buscar o protocolo"))


def token_do_protocolo(numero: Any, corpo: dict | None = None, *,
                       ambiente: Any = None, pasta=None) -> str:
    """O token **daquele** protocolo — o segundo mecanismo de autenticação.

    Sem ele os detalhes não abrem: aquelas quatro operações não aceitam o
    `Bearer` da serventia. Ver o cabeçalho.
    """
    r = _bater("protocolo_token_v2", numero=numero, corpo=dict(corpo or {}),
               ambiente=ambiente, pasta=pasta)
    dados = _dados(_resposta_ou_erro(r, "pedir o token do protocolo")) or {}
    achado = _texto(dados.get("token") or dados.get("access_token"))
    if not achado:
        raise OnrRecusou(
            "O ONR respondeu ao pedido do token do protocolo sem token dentro.")
    return achado




# ------------------------------------------------------------------ edital


def tipos_de_edital(*, ambiente: Any = None, pasta=None) -> Any:
    """Os tipos de edital que o ONR aceita. Só LÊ.

    **A casa não escreve esta lista**: ela vem da Central, e escrevê-la aqui
    seria a lista à mão que envelhece na tarde em que se escreve.
    """
    r = _bater("edital_tipos", ambiente=ambiente, pasta=pasta)
    return _dados(_resposta_ou_erro(r, "buscar os tipos de edital"))


def editais(*, pagina: int = 1, por_pagina: int = 50, ambiente: Any = None,
            pasta=None) -> Any:
    """A lista dos editais desta serventia. Só LÊ."""
    r = _bater("editais", parametros={"pagina": pagina, "limite": por_pagina},
               ambiente=ambiente, pasta=pasta)
    return _dados(_resposta_ou_erro(r, "buscar os editais"))


def gerar_edital(corpo: dict, *, ambiente: Any = None, pasta=None) -> dict:
    """Publica o edital na Central. **É a chamada que faz o prazo correr.**

    O art. 755, § 1º do Código de Normas do TJMA conta a publicação a partir
    do **primeiro dia útil depois da disponibilização na Central** — e é esta
    chamada a disponibilização. Até 03/09/2026 o sistema calculava esse prazo e
    não tinha como disponibilizar nada.
    """
    r = _bater("edital_gerar", corpo=dict(corpo or {}), ambiente=ambiente,
               pasta=pasta)
    resposta = _resposta_ou_erro(r, "gerar o edital")
    dados = _dados(resposta) or {}
    return {"numero": _texto(dados.get("numeroEdital") or dados.get("numero")),
            "corpo": corpo, "bruto": resposta}


def edital(numero: Any, *, ambiente: Any = None, pasta=None) -> Any:
    """Os detalhes de um edital. Só LÊ."""
    r = _bater("edital", numero=numero, ambiente=ambiente, pasta=pasta)
    return _dados(_resposta_ou_erro(r, "buscar o edital"))




def cancelar_edital(numero: Any, *, ambiente: Any = None, pasta=None) -> Any:
    """Cancela o edital na Central.

    **Não desfaz ato nenhum desta casa** — o processo de usucapião continua
    onde está, e a decisão sobre ele é do oficial.
    """
    r = _bater("edital_cancelar", numero=numero, ambiente=ambiente, pasta=pasta)
    return _resposta_ou_erro(r, "cancelar o edital")


# --------------------------------------------------- a fila de processamento


def fila(*, pagina: int = 1, por_pagina: int = 50, ambiente: Any = None,
         pasta=None) -> Any:
    """O que aconteceu com o que subiu. Só LÊ.

    O envio de protocolo e de indicador é **assíncrono** do lado do ONR: ele
    aceita e processa depois. Sem esta lista, «enviado» seria confundido com
    «aceito» — que é o defeito do e-Proclamas noutra forma.
    """
    r = _bater("fila", parametros={"pagina": pagina, "limite": por_pagina},
               ambiente=ambiente, pasta=pasta)
    return _dados(_resposta_ou_erro(r, "buscar a fila de processamento"))


def detalhes_da_fila(hash_fila: Any, *, ambiente: Any = None,
                     pasta=None) -> Any:
    """O detalhe de uma linha da fila — inclusive o que ele recusou. Só LÊ."""
    r = _bater("fila_detalhes", hash=hash_fila, ambiente=ambiente, pasta=pasta)
    return _dados(_resposta_ou_erro(r, "buscar os detalhes da fila"))

# ------------------------------------------------------- SAEC (atendimento)


def atendimentos(*, pagina: int = 1, por_pagina: int = 50,
                 tipo_atendimento: Any = None, status: Any = None,
                 protocolo: Any = None, documento: Any = None,
                 ambiente: Any = None, pasta=None) -> Any:
    """A lista do SAEC — pedidos eletrônicos desta serventia. SÓ LÊ.

    É por aqui que chega o pedido de certidão/pesquisa do RI (TJMA 437:
    conferir a plataforma). Sem rede real nos testes: mock de `_bater`.
    """
    r = _bater(
        "atendimentos",
        parametros={
            "numeroPagina": pagina,
            "registrosPorPagina": por_pagina,
            "tipoAtendimento": tipo_atendimento,
            "status": status,
            "protocolo": protocolo,
            "documento": documento,
        },
        ambiente=ambiente, pasta=pasta)
    return _dados(_resposta_ou_erro(r, "buscar os atendimentos do SAEC"))


def atendimento(id_atendimento: Any, *, ambiente: Any = None,
                pasta=None) -> Any:
    """O detalhe de um atendimento eletrônico. SÓ LÊ."""
    r = _bater("atendimento", id=id_atendimento, ambiente=ambiente,
               pasta=pasta)
    return _dados(_resposta_ou_erro(r, "buscar o atendimento do SAEC"))


def interagir_no_atendimento(id_atendimento: Any, corpo: dict, *,
                             ambiente: Any = None, pasta=None) -> Any:
    """Registra uma interação no SAEC (`acao` + `mensagem` obrigatórios).

    **Não emite certidão**: só devolve o que a Central aceitou. A emissão
    continua nas telas desta casa.
    """
    r = _bater("atendimento_interagir", id=id_atendimento,
               corpo=dict(corpo or {}), ambiente=ambiente, pasta=pasta)
    return _dados(_resposta_ou_erro(r, "interagir no atendimento do SAEC"))


# ------------------------------------------ protocolo (detalhes + validação)


def detalhes_do_protocolo(numero: Any, token_do_protocolo: str, *,
                          ambiente: Any = None, pasta=None) -> Any:
    """Os detalhes **v2** — exigem o token DAQUELE protocolo (headerAuth).

    Peça o token em `token_do_protocolo` antes. Mandar só o Bearer da
    serventia aqui costuma devolver 401 sem explicar o motivo.
    """
    r = _bater("protocolo_detalhes_v2", numero=numero,
               token_do_protocolo=token_do_protocolo,
               ambiente=ambiente, pasta=pasta)
    return _dados(_resposta_ou_erro(r, "buscar os detalhes do protocolo"))


def validar_token_do_protocolo(numero: Any, token_do_protocolo: str, *,
                              ambiente: Any = None, pasta=None) -> Any:
    """Confere se o token daquele protocolo ainda vale. SÓ LÊ (headerAuth)."""
    r = _bater("protocolo_token_validar_v2", numero=numero,
               token_do_protocolo=token_do_protocolo,
               ambiente=ambiente, pasta=pasta)
    return _dados(_resposta_ou_erro(r, "validar o token do protocolo"))


# ---------------------------------------------------------------- cobrança


def cobrancas(*, pagina: int = 1, por_pagina: int = 50,
              status: Any = None, tipo_cobranca: Any = None,
              ambiente: Any = None, pasta=None) -> Any:
    """A lista das cobranças ONR desta serventia. SÓ LÊ."""
    r = _bater(
        "cobrancas",
        parametros={
            "numeroPagina": pagina,
            "registrosPorPagina": por_pagina,
            "status": status,
            "tipoCobranca": tipo_cobranca,
        },
        ambiente=ambiente, pasta=pasta)
    return _dados(_resposta_ou_erro(r, "buscar as cobranças"))


def cobranca(hash_cobranca: Any, *, ambiente: Any = None, pasta=None) -> Any:
    """O detalhe de uma cobrança. SÓ LÊ."""
    r = _bater("cobranca", hash=hash_cobranca, ambiente=ambiente, pasta=pasta)
    return _dados(_resposta_ou_erro(r, "buscar a cobrança"))


def tipos_de_pagamento(*, ambiente: Any = None, pasta=None) -> Any:
    """Os tipos de pagamento que o ONR aceita na cobrança. SÓ LÊ."""
    r = _bater("cobranca_tipos_de_pagamento", ambiente=ambiente, pasta=pasta)
    return _dados(_resposta_ou_erro(r, "buscar os tipos de pagamento"))


def gerar_cobranca(corpo: dict, *, ambiente: Any = None, pasta=None) -> dict:
    """Pede a geração de uma cobrança no ONR.

    Em teste, mockar `_bater` — **não** chamar produção. Devolve o hash e o
    bruto; a casa decide se vincula ao caixa.
    """
    r = _bater("cobranca_gerar", corpo=dict(corpo or {}),
               ambiente=ambiente, pasta=pasta)
    resposta = _resposta_ou_erro(r, "gerar a cobrança")
    dados = _dados(resposta) or {}
    return {
        "hash": _texto(dados.get("hash")),
        "url": _texto(dados.get("url")),
        "status": dados.get("status"),
        "valor_total": dados.get("valorTotal"),
        "corpo": corpo,
        "bruto": resposta,
    }
