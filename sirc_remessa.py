"""A remessa do SIRC — o prazo mais apertado do sistema inteiro.

    «o cartório está precisando do sistema pronto e amadurecido para o quanto
     antes» — o oficial, 29/08/2026

A OBRIGAÇÃO, NA LETRA DO ART. 225 DO CÓDIGO DE NORMAS DO TJMA

    «O oficial de registro civil remeterá, **no prazo de até 1 (um) dia útil**,
     ao INSS, por meio do Sistema Nacional de Informações de Registro Civil
     (SIRC), (…) a relação dos **nascimentos, dos natimortos, dos casamentos,
     dos óbitos, das averbações, das anotações e das retificações** registradas
     na serventia.

     § 1º Para os Municípios que não dispõem de provedor de conexão à internet
     (…) fica autorizada a remessa em até **05 (cinco) dias úteis**.

     § 3º No caso de **não haver sido registrado nenhum** nascimento,
     natimorto, casamento ou óbito, deverá o titular **comunicar este fato ao
     INSS, até o 5º (quinto) dia útil do mês subsequente**.

     § 4º O descumprimento (…) e o fornecimento de **informação inexata**
     sujeitarão o titular (…) à penalidade prevista no **art. 92 da Lei nº
     8.212/1991** (…) e à **ação regressiva proposta pelo INSS**, em razão dos
     danos sofridos.»

É O PRAZO MAIS CURTO DA CASA, E O QUE ALCANÇA MAIS COISA
    Um dia útil, e cobre **tudo** — inclusive averbação, anotação e retificação,
    que os outros destinos não pedem. É por isso que ele vem depois da CRC na
    ordem de construção, mas antes de tudo na ordem do dia.

O QUE O MANUAL TÉCNICO ACRESCENTA
    Do *SIRC – Recomendações Técnicas*, 121 páginas, da Dataprev, guardado em
    `FONTES_EXTERNAS/SIRC_manual_recomendacoes_tecnicas.pdf`:

    | | |
    |---|---|
    | formato | XML válido contra o XSD da Dataprev |
    | codificação | **UTF-8** |
    | tamanho | no máximo **1024 KB** |
    | registros | no máximo **250 por arquivo** |
    | compactação | **GZIP** |
    | intervalo | no mínimo **1 minuto** entre envios |

    **O teto de 250 decide a forma do módulo**: uma remessa grande se parte em
    lotes, e não é detalhe de transporte — é regra do arquivo, e ignorá-la
    produz remessa que a Dataprev recusa inteira.

A DIFERENÇA QUE SEPARA ESTE ENVELOPE DO DA CRC
    Na CRC, tag em branco **já quer dizer** «nulo ou Ignorado(a)». No SIRC:

    «Quando um campo não estiver informado, o **marcador de campo ignorado deve
     ser informado**. Analogamente, o marcador **não pode estar informado**
     quando houver preenchimento do campo.»

    **Os dois envelopes não são o mesmo**, e é por isso que há dois
    formatadores, e não uma montagem que sirva aos dois. Uma montagem única
    acertaria um e erraria o outro exatamente onde o dado falta — que é onde
    eles discordam.

O QUE ESTE MÓDULO NÃO FAZ
    **Não envia — mas o caminho por senha não exige A3, e isso corrige o que
    este arquivo dizia até 14/09/2026.**

    O manual descreve **dois** Web Services, não um:

    | | endereço | autenticação |
    |---|---|---|
    | `/SircWs/Movimento` | `sirc.dataprev.gov.br/SircWs/Movimento` | **usuário e senha**, SOAP/HTTPS simples |
    | `/SircWs/MovimentoCertificadoDigital` | …/MovimentoCertificadoDigital` | certificado **A3** + WS-Security + XML Signature |

    Só o segundo exige o token físico. O WSDL do primeiro é público
    (`.../Movimento?wsdl`) e foi lido em 14/09/2026: **9 operações**, uma
    por espécie e por ação — `enviarMovimentoNascimento`,
    `enviarMovimentoCasamento`, `enviarMovimentoObito`,
    `enviarMovimentoCancelamento`, `declararInexistenciaMovimento`, e os
    quatro `validar*` irmãos — cada uma recebendo `{cns, usuario, senha,
    conteudo}`, com `conteudo` sendo exatamente o XML que este módulo monta.
    **A separação por espécie que este módulo já faz em `montar()` não é só
    do arquivo — é da própria API**: não existe uma operação genérica que
    aceite as duas juntas.

    Isto continua **só montando, sem chamar a rede**: a chamada em si (o
    cliente SOAP, a guarda da credencial fora do banco, o histórico de
    envio) é a próxima peça, e seria o mesmo padrão de `centrais_cred.py`
    que a CRA e a CENPROT já usam — só que aqui o caminho mais simples não
    depende de hardware nenhum.
"""
from __future__ import annotations

import gzip
import hashlib
import re
import sqlite3
from datetime import date
from typing import Any
from xml.sax.saxutils import escape

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import ibge_geracao as IBG
import rc_assento as RCA
import rc_matricula as RCM
from ri_schema import valida_cpf_cnpj as _cpf_valido


class SircError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


# ------------------------------------------------------- os limites do arquivo
#
# MEDIDOS NO MANUAL, e nao escolhidos. Cada um recusa a remessa inteira quando
# estourado — nao ha aceitacao parcial.
MAXIMO_DE_REGISTROS = 250
MAXIMO_DE_BYTES = 1024 * 1024
INTERVALO_MINIMO_SEGUNDOS = 60
CODIFICACAO = "utf-8"

# **O QUE VEIO DO ACERVO NAO SE REMETE.** O registro daqueles assentos aconteceu
# ha decadas, antes de o SIRC existir; o que aconteceu agora foi a DIGITACAO — e
# a remessa e do que se REGISTROU. Ver `pendentes_de_remessa`.
#
# **E A REGRA QUASE VOLTOU A VALER SO PARA UMA ORIGEM** — achado em
# 13/09/2026, quando o lote de 6.757 assentos do acervo em .docx (importado
# com `origem='IMPORTACAO'`) apareceu inteiro na lista de pendentes, com o
# mais antigo de 1900 — o MESMO defeito que `EOFICIO` ja tinha resolvido,
# so que pela origem nova que ainda nao existia quando esta linha foi
# escrita. `ARQUIVO` (33 assentos, ate 1967) e a terceira: `rc_certidao.
# origens_importadas_sem_selo_de_registro()` ja trata as duas — EOFICIO e
# ARQUIVO — como "veio de fora"; aqui faltava so estender para as tres.
ORIGENS_QUE_NAO_SE_REMETEM = ("EOFICIO", "ARQUIVO", "IMPORTACAO")

# **O SIRC NUNCA RECEBEU O ACERVO EM .DOCX, E O OFICIAL QUER FECHAR ESSA
# LACUNA** — decisão dele em 14/09/2026, ao relatar "segue sem aparecer
# todos os registros importados para enviar pra sirc": o E-Ofício nunca
# enviou esses 6.757 assentos (papel antigo, digitado agora), e por isso
# eles precisam subir — só que **não pela remessa do dia**, que conta um
# prazo de 1 dia útil que não faz sentido para um nascimento de 1900.
#
# **É A MESMA SEPARAÇÃO QUE A CRC JÁ TEM** entre `ACAO_CARGA` (o histórico)
# e a remessa do dia a dia — só que o SIRC não tem uma `ACAO` distinta no
# XSD: o envelope é o mesmo `registroNascimentoInclusao`, para carga ou para
# o dia a dia. O que muda aqui é só QUAIS assentos entram, e a tela que não
# fala em atraso.
#
# **`EOFICIO` FICA DE FORA DESTA CARGA, DE PROPÓSITO** — o E-Ofício foi
# sistema **em uso** por anos, e presume-se que cumpriu a própria obrigação
# do SIRC enquanto rodava; misturá-lo à carga sem essa confirmação seria
# reenviar o que talvez já tenha ido. `ARQUIVO` (33 assentos) também fica de
# fora até se confirmar a mesma dúvida. Só `IMPORTACAO` — o lote em .docx,
# que não veio de nenhum sistema — está confirmado como nunca enviado.
ORIGENS_DA_CARGA_DO_ACERVO = ("IMPORTACAO",)

PRAZO_DIAS_UTEIS = 1
PRAZO_SEM_INTERNET_DIAS_UTEIS = 5
PRAZO_DA_INEXISTENCIA_DIAS_UTEIS = 5
ARTIGO = "art. 225 do Código de Normas do TJMA"

SANCAO = (
    "O descumprimento e o fornecimento de informação inexata sujeitam o titular "
    "à penalidade do art. 92 da Lei nº 8.212/1991 e à ação regressiva proposta "
    "pelo INSS, em razão dos danos sofridos (art. 225, § 4º).")

# O que o SIRC recebe — e sao SETE coisas, contra tres da CRC.
O_QUE_VAI: tuple[dict, ...] = (
    {"chave": "NASCIMENTO", "nome": "Nascimento"},
    {"chave": "NATIMORTO", "nome": "Natimorto"},
    {"chave": "CASAMENTO", "nome": "Casamento"},
    {"chave": "OBITO", "nome": "Óbito"},
    {"chave": "AVERBACAO", "nome": "Averbação"},
    {"chave": "ANOTACAO", "nome": "Anotação"},
    {"chave": "RETIFICACAO", "nome": "Retificação"},
)

ESPECIES = tuple(x["chave"] for x in O_QUE_VAI)

# **"5.0" É A ÚNICA VERSÃO QUE O XSD ACEITA** (`versaoLayoutNascimento`, um
# enum de um valor só) — o exemplo real do manual (seção 7.1) declara isso
# no topo do envelope, antes de qualquer registro.
VERSAO_LAYOUT_NASCIMENTO = "5.0"

# **"5.0" TAMBÉM É A ÚNICA VERSÃO DO CASAMENTO** — `versaoLayoutCasamento`,
# mesmo enum de valor único, medido no mesmo XSD (`SIRC_manual.txt`, seção
# 8.3).
VERSAO_LAYOUT_CASAMENTO = "5.0"

# **"5.0" TAMBÉM É A ÚNICA VERSÃO DO ÓBITO** — `versaoLayoutObito`, o mesmo
# enum de valor único, medido na seção do XSD do óbito.
VERSAO_LAYOUT_OBITO = "5.0"

# O regime de casamento, que o SIRC ENUMERA — e o enum NÃO é o mesmo da CRC.
#
# **MEDIDO CONTRA O XSD (`regimeCasamento`, seção 8.3): sete valores.** A CRC
# tem um oitavo (`SEPARACAO_LEGAL_BENS`, separação obrigatória por lei — ex:
# casamento de pessoa maior de 70 anos) que o SIRC **não enumera**. Por isso
# este de-para não reaproveita o da CRC (`crc_carga.REGIME_CASAMENTO`): os
# dois textos de entrada são os mesmos, mas os alvos não — reaproveitar
# produziria um valor que o XSD do SIRC recusa. Onde o texto do assento só
# resolve para «separação legal», o campo sai OMITIDO, e não forçado para
# `SEPARACAO_BENS` — são regimes juridicamente distintos, e escolher por
# semelhança seria assinar pelo delegatário.
REGIME_CASAMENTO_SIRC: dict[str, str] = {
    "COMUNHAO_PARCIAL": "COMUNHAO_PARCIAL",
    "COMUNHAO PARCIAL DE BENS": "COMUNHAO_PARCIAL",
    "COMUNHAO PARCIAL": "COMUNHAO_PARCIAL",
    "COMUNHAO_UNIVERSAL": "COMUNHAO_UNIVERSAL",
    "COMUNHAO UNIVERSAL DE BENS": "COMUNHAO_UNIVERSAL",
    "COMUNHAO UNIVERSAL": "COMUNHAO_UNIVERSAL",
    "SEPARACAO_TOTAL": "SEPARACAO_BENS",
    "SEPARACAO TOTAL DE BENS": "SEPARACAO_BENS",
    "SEPARACAO DE BENS": "SEPARACAO_BENS",
    "PARTICIPACAO_FINAL": "PARTICIPACAO_FINAL_AQUESTOS",
    "PARTICIPACAO FINAL NOS AQUESTOS": "PARTICIPACAO_FINAL_AQUESTOS",
    "OUTROS": "OUTROS", "OUTRO": "OUTROS",
}

# **"COMUNHÃO DE BENS", SEM QUALIFICAÇÃO, É A MESMA AMBIGUIDADE QUE A CRC JÁ
# RESOLVEU** — 292 dos 700 casamentos desta casa estão assim. Antes de
# 26/12/1977 (Lei do Divórcio) o regime legal supletivo era a comunhão
# UNIVERSAL; depois, a comunhão PARCIAL — é a mesma regra de
# `crc_carga._regime_resolvido`, aplicada aqui porque o ano decide sem
# adivinhar.
ANO_DA_LEI_DO_DIVORCIO_SIRC = 1977
_COMUNHAO_SEM_QUALIFICACAO_SIRC = "COMUNHAO DE BENS"


def _chave_regime(v: Any) -> str:
    import unicodedata
    t = " ".join(str(v or "").strip().upper().split())
    return "".join(c for c in unicodedata.normalize("NFD", t)
                   if unicodedata.category(c) != "Mn")


def regime_casamento_sirc(regime_bruto: Any, data_do_casamento: Any) -> str:
    """O `regimeCasamento` do SIRC para este texto — `""` quando não dá para
    saber. Só calcula.

    **Só resolve o que já bate com o dicionário, mais o caso de 1977** — a
    mesma régua de `crc_carga._regime_resolvido`, com o alvo do SIRC. Um
    texto que não é nenhum dos dois continua indefinido de propósito: o
    campo tem `minOccurs="0"` e nenhum marcador de ignorado — sai omitido, e
    não com um valor chutado.
    """
    chave = _chave_regime(regime_bruto)
    resolvido = REGIME_CASAMENTO_SIRC.get(chave)
    if resolvido:
        return resolvido
    if chave == _COMUNHAO_SEM_QUALIFICACAO_SIRC:
        ano = _texto(data_do_casamento)[:4]
        if ano.isdigit() and int(ano) >= ANO_DA_LEI_DO_DIVORCIO_SIRC:
            return "COMUNHAO_PARCIAL"
    return ""

# As tres coisas que o art. 225 manda mandar alem dos registros, com as regras
# de data do manual (secao 4.8).
ATOS_COM_DATA: dict[str, dict] = {
    "ANOTACAO": {
        "regra": "a data da anotação deve ser maior ou igual à do registro "
                 "civil e menor ou igual à data atual",
        "texto_minimo": 10, "texto_maximo": 1000},
    "AVERBACAO": {
        "regra": "a data da averbação deve ser maior ou igual à do registro e "
                 "menor ou igual à data atual; a data do motivo e a da sentença "
                 "devem ser menores ou iguais à da averbação",
        "texto_minimo": 10, "texto_maximo": 1000},
    "RETIFICACAO": {
        "regra": "a data da retificação deve ser maior ou igual à do registro "
                 "civil",
        "texto_minimo": 10, "texto_maximo": 1000},
}


# ------------------------------------------------ o vocabulario, que NAO e o da CRC
#
# MEDIDO NO MANUAL, e a diferenca importa: a CRC escreve `M`, `F` e `I`; o SIRC
# escreve a palavra inteira, e tem tres valores que a CRC nao tem. Usar um pelo
# outro produz arquivo bem formado que a Dataprev recusa.
SEXO = {
    "M": "MASCULINO", "F": "FEMININO",
    "MASCULINO": "MASCULINO", "FEMININO": "FEMININO",
    "NAO_BINARIO": "NAO_BINARIO", "OUTROS": "OUTROS",
    "NAO_DECLARADO": "NAO_DECLARADO", "IGNORADO": "IGNORADO",
}

# A DATA VAI EM dd/mm/aaaa, e nao no ISO do banco. Outra diferenca da CRC.
FORMATO_DA_DATA = "dd/mm/aaaa"

# ------------------------------------------- os vocabulários PRÓPRIOS do óbito
#
# **`corPele` NÃO TEM «IGNORADA»** — ao contrário do `COR_PELE` da própria CRC
# (`crc_carga.py`), que tem. Reaproveitar o de-para da CRC produziria um valor
# que este enum não conhece; por isso há um de-para SIRC próprio, e sem
# fallback de ignorado — quem não resolve aqui usa o marcador `corPeleIgnorada`.
#
# **AS DUAS GRAFIAS CORROMPIDAS DO ACERVO ENTRAM DE PROPÓSITO** — medidas em
# produção (14/09/2026): `cor_raca` tem `'IND�GENA'` e `'INDIG�NA'`,
# mojibake de «INDÍGENA»/«INDÍGENA» com um byte perdido na importação antiga.
# É a mesma correção que a CRC já aplica à grafia acentuada; aqui ela se
# estende às duas variantes corrompidas, porque `�` só pode ter vindo de
# um caractere acentuado que se perdeu — não é chute, é a única leitura que
# faz sentido do byte que sobrou.
COR_PELE_SIRC: dict[str, str] = {
    "BRANCA": "BRANCA", "PRETA": "PRETA", "AMARELA": "AMARELA",
    "PARDA": "PARDA", "INDIGENA": "INDIGENA", "INDÍGENA": "INDIGENA",
    "IND�GENA": "INDIGENA", "INDIG�NA": "INDIGENA",
}


def _estado_civil_sirc(bruto: Any) -> str:
    """O estado civil do falecido, no vocabulário do SIRC — que não é o da
    CRC: `estadoCivil` aqui só tem SOLTEIRO/CASADO/VIUVO/DIVORCIADO/SEPARADO,
    sem OUTROS nem IGNORADO. Só calcula.

    **MEDIDO CONTRA OS 21 VALORES DISTINTOS QUE O ACERVO TEM** em
    `rc_pessoas.estado_civil` do papel FALECIDO — inclusive variação de
    gênero (`CASADA`, `SOLTEIRA`), mojibake (`Vi�vo`) e frases inteiras
    (`"SOLTEIRO COM 67 ANOS 9 MESES E 20 DIAS"`). Por isso a regra é por
    RAIZ, procurada dentro do texto, e não por igualdade exata — igualdade
    exata perderia as frases longas do acervo antigo.

    Valor que não bate com raiz nenhuma volta vazio, e vira o marcador
    `estadoCivilIgnorado` — não se adivinha estado civil.
    """
    t = _texto(bruto).upper()
    if not t:
        return ""
    if "DIVORCIAD" in t:
        return "DIVORCIADO"
    if "SEPARAD" in t:
        return "SEPARADO"
    if "CASAD" in t:
        return "CASADO"
    if "SOLTEIR" in t:
        return "SOLTEIRO"
    # «viúvo/viúva» sobrevive à corrupção de acento («vi?vo») porque o «u» é
    # que se perde, não a posição do caractere — o padrão aceita qualquer
    # caractere no lugar do acento.
    if re.search(r"VI.?V[OA]", t):
        return "VIUVO"
    return ""


# `ibge_local_obito` e `ibge_natureza_obito` já são medidos e documentados no
# CLAUDE.md do projeto — o mesmo catálogo do IBGE/COPRE-GESIP que a remessa
# trimestral usa. O SIRC tem os SEUS PRÓPRIOS nomes para os mesmos códigos.
TIPO_LOCAL_OBITO_SIRC: dict[int, str] = {
    1: "HOSPITAL", 2: "OUTROS_SERVICOS_SAUDE", 3: "DOMICILIO",
    4: "VIA_PUBLICA", 5: "OUTROS",
}
TIPO_MORTE_SIRC: dict[int, str] = {1: "NATURAL", 2: "VIOLENTA"}

# **O NATIMORTO NÃO TEM ENVELOPE PRÓPRIO NO SIRC** — o manual diz, na seção
# 5.4: «para os casos em que o falecido seja um natimorto, o tipo do livro
# deve possuir o valor "5"». É o MESMO `registroObitoAbstrato`; só o
# `tipoLivro` muda, e ele já vem pronto da matrícula. O que diverge é só o
# nome do papel NESTA casa: `rc_assento.PAPEIS_DA_ESPECIE` chama o principal
# de `FALECIDO` no óbito e de `REGISTRADO` no natimorto.
PAPEL_PRINCIPAL_DO_OBITO: dict[str, str] = {
    "OBITO": "FALECIDO", "NATIMORTO": "REGISTRADO"}


def data_do_sirc(iso: Any) -> str:
    """A data como o SIRC a quer — `dd/mm/aaaa`. So calcula.

    O BANCO GUARDA `aaaa-mm-dd` E O SIRC QUER O CONTRARIO. Mandar o ISO produz
    um arquivo bem formado que a Dataprev recusa — e recusa o arquivo inteiro,
    e nao a linha.

    Data que nao esta na forma do banco volta **vazia**, e vazia vira marcador de
    ignorado la na frente: inventar um dia para uma data ilegivel seria afirmar
    ao INSS uma coisa que ninguem sabe.
    """
    bruto = _texto(iso)
    if len(bruto) < 10 or bruto[4] != "-" or bruto[7] != "-":
        return ""
    ano, mes, dia = bruto[:4], bruto[5:7], bruto[8:10]
    if not (ano + mes + dia).isdigit():
        return ""
    return f"{dia}/{mes}/{ano}"


# **`dataRegistro` NÃO É `dd/mm/aaaa` — É `xs:dateTime`, COM FUSO.** Achado
# em 13/09/2026, no exemplo real do manual (seção 7.1):
# `2023-11-30T00:00:00.000-03:00`. É `dataNascimento` que é `dd/mm/aaaa` (o
# tipo `data`, um `xs:string` com padrão próprio) — a confusão entre os dois
# tipos foi o que fez este módulo tratar `dataRegistro` como se fosse
# `dataNascimento`. O Maranhão não tem horário de verão desde 2019: o fuso é
# sempre `-03:00`, e não precisa de tabela.
FUSO_DO_MARANHAO = "-03:00"

# **O PADRÃO DE `horaNascimento` NO XSD** — só 00:00 a 23:59 existem.
# Achado na carga do acervo (14/09/2026): o texto digitado do .docx traz
# "24:00", "24:40", "19:68" — hora que não existe, e o XSD recusa o
# arquivo inteiro por causa disso. Ver `_registro`.
HORA_VALIDA = re.compile(r"([0-1][0-9]|2[0-3]):[0-5][0-9]")


def data_hora_sirc(iso: Any) -> str:
    """`dataRegistro` (e qualquer outro campo `xs:dateTime` do SIRC) — ISO
    completo, com hora e fuso. Só calcula.

    Sem hora no banco (`aaaa-mm-dd` puro), a meia-noite é a mesma convenção
    do exemplo do manual (`T00:00:00.000-03:00`) — não é hora inventada, é o
    que fazer quando só se sabe o dia.
    """
    bruto = _texto(iso)
    if len(bruto) < 10 or bruto[4] != "-" or bruto[7] != "-":
        return ""
    data = bruto[:10]
    if not data.replace("-", "").isdigit():
        return ""
    hora = "00:00:00"
    if len(bruto) >= 19 and bruto[10] == "T":
        candidata = bruto[11:19]
        if len(candidata) == 8 and candidata[2] == ":" and candidata[5] == ":":
            hora = candidata
    return f"{data}T{hora}.000{FUSO_DO_MARANHAO}"


# ------------------------------------------------ os marcadores de ignorado
#
# **MEDIDOS NO XSD DO MANUAL — 52 deles — E NAO CALCULADOS.** O nome do marcador
# concorda em genero com o SUBSTANTIVO do campo: `nomeIgnorado` mas
# `dataNascimentoIgnorada`, `sexoIgnorado` mas `horaNascimentoIgnorada`. Uma
# funcao que colasse «Ignorado» no fim do nome acertaria uns e erraria os outros
# — e erraria calada, porque o XML continua bem formado.
# **`"idade"` NÃO ENTRA AQUI, E ISSO CUSTOU 50 DE 398 ÓBITOS REAIS NA
# VALIDAÇÃO CONTRA O XSD** (14/09/2026). Uma entrada `"idade":
# "idadeIgnorada"` ficou aqui desde antes de o XSD do óbito ser lido — a
# mesma família de palpite que a nota de `"dataFalecimento"`, acima, já
# registra. `idade` (tipo `idadeFalecido`) é `minOccurs="0"` **sem par de
# ignorado nenhum** no `registroObitoAbstrato`: sozinho, sem marcador, como
# `eleitor`. `campo()` emitia `idadeIgnorada` sempre que a idade faltava, e a
# Central recusaria por elemento inesperado — `_registro_obito` usa `_tag()`
# direto, e só quando há valor.
MARCADOR_IGNORADO: dict[str, str] = {
    "nome": "nomeIgnorado",
    "sexo": "sexoIgnorado",
    "cpf": "cpfIgnorado",
    "corPele": "corPeleIgnorada",
    "estadoCivil": "estadoCivilIgnorado",
    "nacionalidade": "nacionalidadeIgnorada",
    "paisNascimento": "paisNascimentoIgnorado",
    "dataNascimento": "dataNascimentoIgnorada",
    "horaNascimento": "horaNascimentoIgnorada",
    "dataObito": "dataObitoIgnorada",
    "horaObito": "horaObitoIgnorada",
    "dataFalecimento": "dataFalecimentoIgnorada",
    # **`dataNascimentoFalecido` — o marcador certo veio só ao ler o XSD do
    # óbito (14/09/2026).** `dataFalecimentoIgnorada`, acima, foi um palpite
    # de sessão anterior que não corresponde a NENHUM campo real do
    # `registroObitoAbstrato` — o XSD chama o campo `dataNascimentoFalecido`
    # (é a data de NASCIMENTO do falecido, não a do óbito), e o marcador dele
    # é `dataNascimentoFalecidoIgnorada`. A entrada velha fica — não
    # atrapalha, porque nenhum campo se chama literalmente "dataFalecimento"
    # — mas o certo é este.
    "dataNascimentoFalecido": "dataNascimentoFalecidoIgnorada",
    "dataCelebracaoCasamento": "dataCelebracaoCasamentoIgnorada",
    "declaracaoObito": "declaracaoObitoIgnorada",
    "tipoMorte": "tipoMorteIgnorado",
    "tipoLocalObito": "tipoLocalObitoIgnorado",
    "nomeLocalObito": "nomeLocalObitoIgnorado",
    "nomeDeclarante": "nomeDeclaranteIgnorado",
    "nomeConjugePosCasamento": "nomeConjugePosCasamentoIgnorado",
    "causaMorteConhecida": "causaMorteConhecidaIgnorada",
    "logradouro": "logradouroIgnorado",
    "logradouroObito": "logradouroObitoIgnorado",
    "numeroLogradouro": "numeroLogradouroIgnorado",
    "codigoIBGEMunicipio": "codigoIBGEMunicipioIgnorado",
    "codigoIBGEUF": "codigoIBGEUFIgnorado",
    "codigoIBGEUFNaturalidade": "codigoIBGEUFNaturalidadeIgnorado",
    "codigoOcupacaoSDC": "codigoOcupacaoSDCIgnorado",
    "documentos": "documentosIgnorado",
    "lugarSepultamentoCemiterio": "lugarSepultamentoCemiterioIgnorado",
    "beneficiosPrevidenciarios": "beneficiosPrevidenciariosIgnorado",
    # **OS NOVE DE 09/10/2026, lidos no XSD do manual** (`registroNascimento-
    # Abstrato` e `registroObitoAbstrato`) depois que o SIRC-Web de produção
    # recusou o lote real pedindo «informado ou ignorado» para o endereço da
    # filiação, o do falecido e o do lugar do óbito.
    "codigoIBGEMunicipioFiliacao": "codigoIBGEMunicipioFiliacaoIgnorado",
    "codigoIBGEUFFiliacao": "codigoIBGEUFFiliacaoIgnorado",
    "logradouroFiliacao": "logradouroFiliacaoIgnorado",
    "numeroLogradouroFiliacao": "numeroLogradouroFiliacaoIgnorado",
    "codigoIBGEMunicipioLogradouro": "codigoIBGEMunicipioLogradouroIgnorado",
    "codigoIBGEMunicipioLogradouroObito":
        "codigoIBGEMunicipioLogradouroObitoIgnorado",
    "codigoIBGEUFLogradouro": "codigoIBGEUFLogradouroIgnorado",
    "codigoIBGEUFLogradouroObito": "codigoIBGEUFLogradouroObitoIgnorado",
    "numeroLogradouroObito": "numeroLogradouroObitoIgnorado",
}


def _texto(v: Any) -> str:
    """O valor como texto, e vazio quando não há.

    USAR SEMPRE, E NUNCA O PADRÃO DO `get` — ele só vale quando a chave falta, e
    numa linha de banco ela existe sempre. `crc_carga` estourou em quatro
    lugares por isso, no primeiro ensaio contra dado real.

    **E NÃO SE ESCREVE `str(v or "")`, que é o reflexo.** Ele come o `0` junto
    com o `None`, porque zero é falso em Python — e aqui isso não é detalhe de
    estilo: o SIRC exige que campo sem valor leve o **marcador de ignorado**, de
    modo que uma quantidade zero, um número zero ou uma folha zero sairiam
    declarados ao INSS como «não sei», que é uma afirmação diferente de «zero».
    Peguei isso montando a declaração de inexistência, que é justamente o
    arquivo em que a quantidade é zero.
    """
    if v is None:
        return ""
    return str(v).strip()


def _tag(nome: str, valor: Any = "") -> str:
    return f"<{nome}>{escape(_texto(valor))}</{nome}>"


def em_lotes(registros: list, tamanho: int = MAXIMO_DE_REGISTROS) -> list[list]:
    """Parte a remessa em lotes de no máximo 250. Só calcula.

    **NÃO É DETALHE DE TRANSPORTE.** «O arquivo deve conter no máximo 250
    Registros», e estourar não faz a Dataprev aceitar 250 e recusar o resto:
    ela recusa **o arquivo inteiro**.

    E entre um envio e outro há **um minuto** de intervalo mínimo — por isso o
    módulo devolve os lotes, e não os manda num laço apertado.
    """
    if tamanho < 1:
        raise SircError("O lote tem de ter ao menos um registro.")
    return [registros[i:i + tamanho]
            for i in range(0, len(registros), tamanho)] or [[]]


def cabe_no_arquivo(xml: str) -> dict:
    """Se o XML cabe no limite de tamanho. Só calcula.

    O LIMITE É EM BYTES, E NÃO EM CARACTERES — e a diferença aparece justamente
    aqui, onde quase todo nome tem acento: «JOSÉ» ocupa 5 bytes em UTF-8 e 4
    caracteres. Medir por caractere deixaria passar arquivo que a Dataprev
    recusa.
    """
    tamanho = len(xml.encode(CODIFICACAO))
    return {"bytes": tamanho, "cabe": tamanho <= MAXIMO_DE_BYTES,
            "limite": MAXIMO_DE_BYTES}


# ------------------------------------------- o arquivo para o SIRC-Web (.mrc)
#
# **O CAMINHO POR SENHA (`sirc_cliente.py`) NÃO PRECISA DISTO** — o Web
# Service recebe `conteudo` como texto XML puro, dentro do envelope SOAP
# (seção 2.3 do manual). Isto aqui é só para quem sobe o arquivo pelo
# **SIRC-Web, no navegador** (seção 2.2) — um caminho independente, que
# continua existindo para quando o Web Service não responder, ou enquanto
# a credencial dele não estiver liberada.
#
# **SEM ISTO, O ARQUIVO BAIXADO EM `.xml` SERIA RECUSADO NO UPLOAD** — a
# seção 3 do manual exige, nesta ordem: comprimir em GZIP (DEFLATE), cifrar
# com AES-128-ECB (PKCS#5, sem salt, chave = hash MD5 do CNS **sem zeros à
# esquerda**), e trocar a extensão para `.mrc`. Até 14/09/2026 o botão de
# baixar só entregava o XML cru — bem formado, mas num formato que o
# SIRC-Web nunca aceitaria.
#
# **VALIDADO BYTE A BYTE CONTRA O PRÓPRIO COMANDO QUE O MANUAL DÁ COMO
# EXEMPLO** (`openssl aes-128-ecb -k <cns sem zeros> -e -nosalt -md md5`):
# o OpenSSL 3.x mudou o KDF padrão de `-k` para SHA-256 sem o `-md md5`
# explícito — sem forçar o dígest, o comando do MANUAL (escrito numa época
# de OpenSSL mais antigo) já não bate mais com o OpenSSL de hoje. O `-md
# md5` é o que faz o exemplo do manual voltar a valer, e é o que este
# módulo reproduz.
def _chave_do_arquivo(cns: Any) -> bytes:
    """O hash MD5 do CNS **sem zeros à esquerda** — é o que a seção 3.3 do
    manual manda, e é literalmente o que o comando de exemplo do manual
    faz («o openssl já converte o CNS informado por default em um hash
    MD5»): o `-k <valor>` recebe o CNS como SENHA, não como chave pronta.
    """
    sem_zeros = _texto(cns).lstrip("0") or "0"
    return hashlib.md5(sem_zeros.encode("ascii")).digest()


def arquivo_mrc(xml: str, *, cns: Any) -> bytes:
    """O XML comprimido e cifrado, pronto para o upload manual no
    SIRC-Web. Só calcula — não grava nada, não fala com rede nenhuma.

    A ORDEM É COMPRIMIR, DEPOIS CIFRAR — inverter destruiria a
    compressão, porque texto cifrado não tem a repetição que o DEFLATE
    precisa para comprimir.

    **`mtime=0`** — sem isso, o cabeçalho do GZIP leva o instante da
    compressão, e o mesmo XML gera um `.mrc` diferente a cada chamada
    (só no primeiro bloco cifrado, por causa do ECB). A Central não liga
    para essa data, mas um arquivo que sai igual sempre que o conteúdo é
    igual é o que permite conferir/testar sem inventar tolerância.
    """
    comprimido = gzip.compress(xml.encode(CODIFICACAO), mtime=0)
    chave = _chave_do_arquivo(cns)
    enchedor = padding.PKCS7(128).padder()
    preenchido = enchedor.update(comprimido) + enchedor.finalize()
    cifrador = Cipher(algorithms.AES(chave), modes.ECB()).encryptor()
    return cifrador.update(preenchido) + cifrador.finalize()


def nome_do_arquivo_mrc(prefixo: str, numero: int) -> str:
    """O nome do arquivo pronto para upload — a extensão `.mrc` é
    obrigatória (seção 3.4): «quaisquer outras extensões serão ignoradas
    pelo SIRC». Só calcula."""
    return f"{prefixo}-{numero:03d}.mrc"


def pendentes_de_remessa(con: sqlite3.Connection,
                         limite: int = 20_000) -> list[dict]:
    """O que o SIRC ainda não recebeu, do mais antigo para o mais novo. Só lê.

    **O TETO ERA 500, E MENTIA CALADO** — o mesmo defeito da carga da CRC,
    achado no mesmo dia (13/09/2026): com o acervo em 280 assentos ele nunca
    mordia, e virou um corte disfarçado de total assim que o lote de 6.757
    chegou. Não é limite de desempenho — é número nunca revisto.

    DO MAIS ANTIGO PARA O MAIS NOVO, como as anotações e as comunicações — e
    aqui com mais razão que em qualquer outro lugar: **o prazo é de um dia
    útil**, e o que está esperando há mais tempo já estourou.

    LEVA AS SETE COISAS, e não só os registros. O art. 225 manda a relação «dos
    nascimentos, dos natimortos, dos casamentos, dos óbitos, **das averbações,
    das anotações e das retificações**» — e as três últimas moram em `rc_atos`,
    não em `rc_assentos`.

    **E O QUE VEIO DO ACERVO NÃO ENTRA.** Achado no ensaio contra a produção em
    30/08/2026: sem este filtro a lista devolvia **243 registros, o mais antigo
    de 12/10/1955** — numa tela que diz «o prazo é de 1 dia útil». Aquele
    nascimento apareceria como vinte e cinco mil dias em atraso, numa lista que o
    balcão não teria como zerar.

    O registro deles aconteceu há décadas, antes de o SIRC existir; o que
    aconteceu foi a **digitação**. A remessa é do que se **registrou**.

    > É a mesma precaução que `ibge_geracao.a_prestar` já tinha — e que eu não
    > pus aqui. Escrevi a regra num módulo e esqueci no irmão dele, no mesmo dia;
    > quem achou foi o ensaio contra o dado real, e não os 35 testes de mesa.
    >
    > **E a carga da CRC NÃO leva este filtro**, de propósito: lá os 243 estão
    > certos — a carga é *justamente* a do acervo histórico na Central.
    """
    con.row_factory = sqlite3.Row
    achados: list[dict] = []
    marcadores = ",".join("?" * len(ORIGENS_QUE_NAO_SE_REMETEM))

    # `regime_bens` NAS DUAS CONSULTAS desde 08/10/2026: `_registro_casamento`
    # lê `r["regime_bens"]`, e as consultas não o traziam — nenhum casamento
    # levava o regime ao SIRC (medido no 8366, comunhão parcial). Os testes
    # não pegavam porque montam o registro com uma consulta própria.

    for r in con.execute(
            f"""SELECT id, id AS assento_id, especie AS tipo, numero, nome,
                      data_ato, data_fato, matricula, hora_fato, dnv,
                      cpf_registrado, regime_bens
                 FROM rc_assentos
                WHERE especie IN ('NASCIMENTO','NATIMORTO','CASAMENTO',
                                  'CASAMENTO_RELIGIOSO','OBITO')
                  AND COALESCE(situacao,'ATIVO') = 'ATIVO'
                  AND COALESCE(origem,'') NOT IN ({marcadores})
             ORDER BY data_ato, id LIMIT ?""",
            (*ORIGENS_QUE_NAO_SE_REMETEM, limite)):
        achados.append({**dict(r), "onde": "rc_assentos"})

    # **OS TRES ATOS DA DIVISAO TRIPARTITE VIRAM UMA «ALTERAÇÃO» DO PRÓPRIO
    # REGISTRO — e não um envelope à parte.** Achado em 14/09/2026, lendo o
    # manual: «Alteração de Registro de Nascimento... Devem ser enviados
    # TODOS OS DADOS DO REGISTRO. Os campos que não forem enviados terão
    # seus valores considerados NULL» (seção 6.1, e o mesmo vale para
    # casamento e óbito). Não existe `registroAverbacaoInclusao` nenhum: o
    # que existe é `averbacoesNascimento`/`anotacoesNascimento`/
    # `retificacoesNascimento` (e os equivalentes) **dentro** do mesmo
    # `registroXAlteracao` que carrega o registro inteiro de novo.
    #
    # **POR ISSO OS ATOS DE UM MESMO ASSENTO SE AGRUPAM NUMA LINHA SÓ** — se
    # duas averbações pendessem sobre o mesmo nascimento e cada uma virasse
    # um envio separado, a segunda «Alteração» reenviaria o registro com
    # `dadosComplementares=NULL`, apagando a primeira: o manual diz que
    # campo ausente é NULL, e não «mantém o que já tinha».
    #
    # **E O ASSENTO CANCELADO NÃO VIRA ALTERAÇÃO** — achado em 02/10/2026,
    # no levantamento contra a produção. A busca dos assentos já exigia
    # `situacao='ATIVO'`; a dos atos não, e o assento 1231 (o termo
    # lavrado no livro físico errado) aparecia na remessa do dia como
    # «NASCIMENTO + AVERBACAO» — a averbação que ele tem é justamente a do
    # cancelamento. Mandar um `registroNascimentoAlteracao` de um termo
    # que nunca valeu afirmaria ao INSS um registro que não existe, e o
    # § 4º do art. 225 pune a informação inexata. O caminho de um termo
    # cancelado é `pendentes_de_cancelamento`, e só ele.
    try:
        linhas = list(con.execute(
                f"""SELECT s.*, a.id AS ato_id, a.tipo AS ato_tipo,
                          a.data_ato AS ato_data, a.fundamento AS ato_fundamento
                     FROM rc_atos a
                     JOIN rc_assentos s ON s.id = a.assento_id
                    WHERE a.tipo IN ('AVERBACAO','ANOTACAO','RETIFICACAO')
                      AND COALESCE(s.situacao,'ATIVO') = 'ATIVO'
                      AND COALESCE(s.origem,'') NOT IN ({marcadores})
                 ORDER BY s.id, a.data_ato, a.id""",
                (*ORIGENS_QUE_NAO_SE_REMETEM,)))
        agrupados: dict[int, dict] = {}
        for r in linhas:
            d = dict(r)
            aid = d["id"]
            candidato = agrupados.get(aid)
            if candidato is None:
                # **`tipo` PASSA A SER A ESPÉCIE DO ASSENTO** (NASCIMENTO,
                # CASAMENTO, OBITO...), e não mais «AVERBACAO» — é o que
                # deixa `montar()` escolher o envelope certo, e `o_que_falta`
                # aplicar as MESMAS conferências (matrícula, nome do
                # falecido/cônjuge) que já valem para a Inclusão.
                candidato = {**d, "tipo": d.get("especie"),
                            "assento_id": aid, "onde": "rc_atos", "atos": []}
                agrupados[aid] = candidato
            candidato["atos"].append({
                "tipo": d["ato_tipo"], "data_ato": d["ato_data"],
                "fundamento": d["ato_fundamento"]})
        achados.extend(agrupados.values())
    except sqlite3.OperationalError:
        # Instalacao sem a coluna ainda. Nao derruba a lista dos assentos —
        # meia remessa e melhor que remessa nenhuma, e a falta fica visivel.
        pass

    # **A ORDENAÇÃO É PELA DATA DO ATO MAIS ANTIGO PENDENTE DE CADA GRUPO,
    # e não pela `data_ato` do registro** — que continua sendo a do
    # REGISTRO original (ela vai em `dataRegistro`, e sobrescrevê-la
    # confundiria a data do nascimento/casamento/óbito com a da averbação).
    def _chave_de_ordenacao(x: dict) -> tuple[str, int]:
        atos = x.get("atos")
        if atos:
            data = min(_texto(a.get("data_ato")) for a in atos)
        else:
            data = _texto(x.get("data_ato"))
        return (data, x.get("id") or 0)

    achados.sort(key=_chave_de_ordenacao)
    return achados[:limite]


def pendentes_de_carga_do_acervo(con: sqlite3.Connection,
                                 limite: int = 20_000) -> list[dict]:
    """O acervo em .docx que o SIRC nunca recebeu — não é a remessa do dia.

    **DECISÃO DO OFICIAL EM 14/09/2026**: o lote de 6.757 assentos
    importados em .docx precisa subir ao SIRC, porque o E-Ofício nunca o
    enviou (papel antigo, digitado agora). Mesma forma de registro que
    `pendentes_de_remessa`, mas **sem o prazo de 1 dia útil** — aqui não há
    atraso a contar, porque não é isso que esta lista mede.

    Ver `ORIGENS_DA_CARGA_DO_ACERVO`: por enquanto só `IMPORTACAO` — o
    E-Ofício e o `ARQUIVO` ficam de fora até se confirmar se já cumpriram a
    obrigação sozinhos.
    """
    con.row_factory = sqlite3.Row
    achados: list[dict] = []
    marcadores = ",".join("?" * len(ORIGENS_DA_CARGA_DO_ACERVO))

    for r in con.execute(
            f"""SELECT id, id AS assento_id, especie AS tipo, numero, nome,
                      data_ato, data_fato, matricula, hora_fato, dnv,
                      cpf_registrado, regime_bens
                 FROM rc_assentos
                WHERE especie IN ('NASCIMENTO','NATIMORTO','CASAMENTO',
                                  'CASAMENTO_RELIGIOSO','OBITO')
                  AND COALESCE(situacao,'ATIVO') = 'ATIVO'
                  AND COALESCE(origem,'') IN ({marcadores})
             ORDER BY data_ato, id LIMIT ?""",
            (*ORIGENS_DA_CARGA_DO_ACERVO, limite)):
        achados.append({**dict(r), "onde": "rc_assentos"})

    achados.sort(key=lambda x: (_texto(x.get("data_ato")), x.get("id") or 0))
    return achados[:limite]


def quantos_ficam_de_fora_pelo_acervo(con: sqlite3.Connection) -> int:
    """Quantos assentos do acervo (EOFICIO/ARQUIVO/IMPORTACAO) NÃO entram na
    lista de pendentes — só para a tela dizer o número, e não deixar um
    filtro forte parecer sistema perdendo registro.

    **RELATO DO OFICIAL EM 13/09/2026: "remessa sirc não aparece todos
    registros do sistema para envio".** A lista caiu de milhares para 3
    depois do conserto do vazamento do acervo — certo, porque o SIRC conta
    o prazo do REGISTRO, e o acervo foi registrado há décadas —, mas a tela
    não dizia isso: um número pequeno sem explicação lê como defeito.
    """
    con.row_factory = sqlite3.Row
    marcadores = ",".join("?" * len(ORIGENS_QUE_NAO_SE_REMETEM))
    return con.execute(
        f"""SELECT COUNT(*) FROM rc_assentos
             WHERE especie IN ('NASCIMENTO','NATIMORTO','CASAMENTO',
                               'CASAMENTO_RELIGIOSO','OBITO')
               AND COALESCE(situacao,'ATIVO') = 'ATIVO'
               AND COALESCE(origem,'') IN ({marcadores})""",
        ORIGENS_QUE_NAO_SE_REMETEM).fetchone()[0]


# **NENHUMA ESPÉCIE ESTÁ PRONTA PARA SAIR AINDA — e isso só se soube
# validando contra o XSD de verdade, não lendo por cima.** Achado em
# 13/09/2026, pedido do oficial: "arrumar os que pudermos e não enviar os
# que não puderem ser arrumados".
#
# A primeira passada corrigiu os NOVE campos da base comum (`registroCivil`
# — `acervo`, `anoRegistro`, `codServentia`, `dvMatricula`, `folha`,
# `numeroLivro`, `termo`, `tipoLivro`, `tipoServico`, todos derivados da
# matrícula) e as duas `filiacoesNascimento` (`minOccurs="2"`, e o módulo não
# montava nenhuma) — e pareceu pronta. **A VALIDAÇÃO CONTRA O XSD DE VERDADE
# (extraído do próprio manual) DESMENTIU:**
#
#   1. **O ENVELOPE INTEIRO ESTAVA ERRADO.** O manual mostra o exemplo real
#      (seção 7.1): a raiz é `<movimentoNascimentoTO><versaoLayoutNascimento>
#      5.0</versaoLayoutNascimento><registroNascimentoInclusao>…`, e este
#      módulo produzia `<movimento><cns>…</cns>…<registros><registro>` — um
#      formato inventado, sem apoio no manual. **Reconstruído** — `montar()`
#      monta `movimentoNascimentoTO` de verdade, e o registro individual é
#      `registroNascimentoInclusao`, não mais o `<registro><tipo>` genérico.
#
#   2. **`dataRegistro` NÃO É `dd/mm/aaaa` — é `xs:dateTime` com fuso.** O
#      exemplo do manual traz `2023-11-30T00:00:00.000-03:00`; a `data` de
#      `dataNascimento` (outro tipo do XSD, só essa é `dd/mm/aaaa`) é que
#      confundiu a leitura anterior. É a mesma família do erro que o
#      `crc_carga.py` já documentou («dois envelopes, dois formatos», ali
#      entre a CRC e o SIRC — aqui é DENTRO do próprio SIRC, entre dois tipos
#      de data diferentes). **Corrigido** — `data_hora_sirc()`.
#
#   3. A ORDEM DOS CAMPOS DENTRO DE CADA `<xs:sequence>` IMPORTA — e nem
#      todos os campos que este módulo monta estavam na ordem certa.
#      **Corrigida** em `_registro()`, na ordem em que `registroCivil` e
#      `registroNascimentoAbstrato` declaram cada campo.
#
# **CONFERIDO CONTRA O XSD EXTRAÍDO DO PRÓPRIO MANUAL** (não só lido por
# cima): um registro de nascimento montado por este módulo, com dado real
# da produção, valida contra `registroNascimento` sem erro nenhum.
#
# **CASAMENTO ENTROU EM 14/09/2026** — medido contra o XSD extraído do
# manual (`registroCasamento`, seção 8.3), com a mesma disciplina do
# nascimento: base `registroCivil` idêntica, `filiacoesConjuge` com
# `minOccurs="2"` (duas ocorrências sempre, um genitor pode vir marcado
# ignorado), `sexoConjuge` com o MESMO enum de `SEXO` já medido aqui, e
# `regimeCasamento` com enum PRÓPRIO — ver `REGIME_CASAMENTO_SIRC`.
#
# **ÓBITO ENTROU EM 14/09/2026** — medido contra o XSD extraído do manual
# (`registroObitoAbstrato`, seção do óbito), com a mesma disciplina do
# casamento: base `registroCivil` idêntica, `filiacoesObito` com
# `minOccurs="2"` (mesma regra de `filiacoesNascimento`), `sexo`/`estadoCivil`
# do falecido em vocabulário PRÓPRIO (`estadoCivil` do SIRC não tem
# OUTROS/IGNORADO, ao contrário do da CRC), e `corPele` também com
# vocabulário próprio (sem «IGNORADA»). **NÃO INVENTA O QUE NÃO MEDIU**: os
# campos de endereço do falecido/local do óbito, ocupação e país estrangeiro
# não têm coluna nesta casa e saem OMITIDOS — não por semelhança.
#
# **NATIMORTO ENTROU EM 14/09/2026, e não com envelope próprio** — o manual
# diz na seção 5.4: «para os casos em que o falecido seja um natimorto, o
# tipo do livro deve possuir o valor "5"». Não há `registroNatimorto` no
# XSD: é o MESMO `registroObitoAbstrato`, e `_registro_obito()` já monta o
# `tipoLivro` certo (vem da matrícula, e `LIVRO_DA_ESPECIE["NATIMORTO"]` já
# é `"5"`). O que muda é só o papel da casa que guarda o nome — ver
# `PAPEL_PRINCIPAL_DO_OBITO`. **Sem registro real para validar em escala**
# (zero natimortos em produção nesta serventia), a garantia aqui é a letra
# do manual, não a medição contra dado real — diferente do óbito e do
# casamento, que validaram centenas.
#
# **OS TRÊS ATOS DA DIVISÃO TRIPARTITE (averbação/anotação/retificação)
# ENTRARAM EM 14/09/2026 — como ALTERAÇÃO do próprio registro, e não como
# envelope à parte.** O manual (seção 6.1) diz que uma averbação/anotação/
# retificação se manda reenviando TODO o registro dentro de
# `registroXAlteracao`, com o bloco (`averbacoesNascimento`, etc.)
# embutido — ver `pendentes_de_remessa` e `_bloco_dos_atos`. Por isso a
# lista abaixo continua sendo a de ESPÉCIE (nascimento/casamento/óbito), e
# não a de tipo de ato: um ato sobre uma espécie ainda sem envelope (hoje,
# nenhuma) continuaria retido pelo motivo de baixo.
ESPECIES_PRONTAS_PARA_O_SIRC: tuple[str, ...] = ("NASCIMENTO", "CASAMENTO",
                                                 "CASAMENTO_RELIGIOSO",
                                                 "OBITO", "NATIMORTO")


# **O LOCAL DO NASCIMENTO É OBRIGATÓRIO PARA O SIRC — medido em 06/10/2026 no
# próprio SIRC-Web.** O XSD o declara `minOccurs="0"` (`local`, enum
# UNIDADE_SAUDE / FORA_UNIDADE_SAUDE) e por isso este módulo o omitia; o
# «Relatório de Movimentos com Erro» da casa mostra os termos 19572 a 19575
# recusados em 22/09 e de novo em 30/09 com «Dados Obrigatórios não
# informados: local» — e as cargas do acervo de 13/09 com o mesmo erro. O
# XSD diz o que cabe; quem diz o que é obrigatório é a Central.
#
# O de-para sai do catálogo do IBGE que a casa já guarda
# (`ibge_local_nascimento`, `ibge_remessa.LOCAL_DO_NASCIMENTO`): hospital e
# outro estabelecimento de saúde são unidade de saúde; domicílio e «outros»
# são fora dela. «Ignorado» (9) e vazio NÃO viram nenhum dos dois — o XSD não
# traz marcador de local ignorado, e escolher um lado seria afirmar o que
# ninguém informou. Ficam retidos, dizendo onde se informa.
LOCAL_NASCIMENTO_SIRC: dict[int, str] = {
    1: "UNIDADE_SAUDE",
    2: "UNIDADE_SAUDE",
    3: "FORA_UNIDADE_SAUDE",
    5: "FORA_UNIDADE_SAUDE",
}


def _codigo_local_nascimento(con: sqlite3.Connection | None,
                             r: dict) -> int | None:
    if "ibge_local_nascimento" in r:
        bruto = r.get("ibge_local_nascimento")
    elif con is not None and r.get("assento_id") is not None:
        try:
            linha = con.execute(
                "SELECT ibge_local_nascimento FROM rc_assentos WHERE id = ?",
                (r.get("assento_id"),)).fetchone()
        except sqlite3.OperationalError:
            linha = None
        bruto = linha[0] if linha else None
    else:
        return None
    try:
        return int(bruto)
    except (TypeError, ValueError):
        return None


# ------------------------------------------ o que o SIRC-Web de produção cobra
#
# **O VALIDADOR DE PRODUÇÃO COBRA MAIS QUE OS «CAMPOS MÍNIMOS» DO MANUAL** —
# medido em 09/10/2026, subindo o lote real pelo SIRC-Web: 5 nascimentos e 1
# óbito recusados inteiros, todos por campo «que deve ser informado ou
# ignorado» — o município do nascimento, a data/idade, a profissão e o CPF de
# cada genitor, o endereço da filiação; no óbito, o endereço do falecido e o
# número/município/UF do lugar do óbito, a nacionalidade e os benefícios. O
# manual avisa («de acordo com as regras de negócio do sistema, outros campos
# podem se tornar obrigatórios»), e esta é a lista medida.
#
# **E O DADO ESTAVA NO SISTEMA**: endereço, CPF, data de nascimento e
# naturalidade dos genitores em `rc_pessoas`; a cidade do parto em
# `rc_assentos.local_fato_endereco`. O montador é que não os levava.

def _coluna_do_assento(con: sqlite3.Connection | None, r: dict,
                       coluna: str) -> Any:
    """Uma coluna de `rc_assentos` — da linha que veio, ou do banco.

    **A CONSULTA DOS PENDENTES TRAZ SÓ PARTE DAS COLUNAS** (é a mesma família
    do `regime_bens` de 08/10/2026): o óbito saía com o lugar, a causa, a
    natureza e o número da DO «ignorados» embora preenchidos no assento.
    Ler daqui vale para a consulta que veio curta e para o teste que monta o
    registro à mão — a forma de `_codigo_local_nascimento`."""
    if coluna in r:
        return r.get(coluna)
    if con is None or r.get("assento_id") is None:
        return None
    try:
        linha = con.execute(f"SELECT {coluna} FROM rc_assentos WHERE id = ?",
                            (r.get("assento_id"),)).fetchone()
    except sqlite3.OperationalError:
        return None
    return linha[0] if linha else None


_NUMERO_DO_ENDERECO = re.compile(
    r"^(?:n[ºo°]?\.?\s*º?|n[uú]mero)?\s*(\d+[A-Za-z]?|s\s*/\s*n)\.?$", re.I)


def _endereco_em_partes(texto: Any) -> dict:
    """Um endereço escrito numa linha só, partido nas vírgulas. Só calcula.

    Medido nos assentos de 2026: «Rua 10, n.º 12, Vila Angical»,
    «Rua Sebastião, 12», «Povoado Corcovado, s/n» e, no lugar do fato,
    «Avenida Bernardo Sayão, nº 2640, Nova Imperatriz, Imperatriz/MA». A
    primeira parte é o logradouro; a que é só número (ou «s/n») é o número; a
    última com barra é «Cidade/UF»; o que sobra no meio é o bairro. **Não
    adivinha**: o que não se acha volta vazio, e vira «ignorado» no XML."""
    partes = [p.strip() for p in _texto(texto).split(",") if p.strip()]
    saida = {"logradouro": "", "numero": "", "bairro": "",
             "cidade": "", "uf": ""}
    if not partes:
        return saida
    saida["logradouro"] = partes[0]
    resto = partes[1:]
    if resto and re.fullmatch(r"[^/]+/\s*[A-Za-z]{2}\.?", resto[-1]):
        cidade, uf = resto.pop().split("/", 1)
        saida["cidade"], saida["uf"] = cidade.strip(), uf.strip(" .").upper()
    meio = []
    for p in resto:
        m = _NUMERO_DO_ENDERECO.match(p)
        if m and not saida["numero"]:
            saida["numero"] = "S/N" if "/" in m.group(1) else m.group(1)
        else:
            meio.append(p)
    saida["bairro"] = ", ".join(meio)
    return saida


def _municipio_sirc(con: sqlite3.Connection | None, cidade: Any,
                    uf: Any) -> tuple[str, str]:
    """(código do município NO SIRC, código da UF) — ou ("", "") se não achou.

    A MESMA BUSCA da remessa do IBGE e da carga da CRC (`ibge_geracao.lugar`,
    contra `ib_municipios`), e não uma cópia: a regra de ambiguidade («sem
    UF, só vale se o nome for único no Brasil») mora lá.

    **NO SIRC O CÓDIGO TEM SEIS DÍGITOS — o do IBGE SEM o verificador.**
    Medido em 09/10/2026: o validador recusou `2105302` (Imperatriz) e
    `2198765` (Cidade Exemplo) como «Código IBGE … inválido», e todos os
    exemplos do manual têm seis (`314230`, `251540`, `120001`). É o mesmo
    município da CRC e do e-Proclamas, noutra forma — os sete menos o último."""
    nome = _texto(cidade).split("/")[0].strip(" .")
    if con is None or not nome:
        return "", ""
    achado = IBG.lugar(con, nome, _texto(uf).strip(" .").upper())
    if not achado.get("achou"):
        return "", ""
    return achado["codigo_ibge"][:6], achado["uf"]


# A NACIONALIDADE É CÓDIGO DO SDC (TB0085), e o único medido é o do Brasil:
# `76`, nos exemplos do próprio manual (seção 8, «nacionalidade 76» ao lado de
# «paisNascimento 76»). Outra nacionalidade sai ignorada — não se escolhe
# código de país por semelhança de nome.
NACIONALIDADE_BRASIL_SIRC = 76


def _nacionalidade_sirc(texto: Any) -> str:
    t = _texto(texto).lower()
    return str(NACIONALIDADE_BRASIL_SIRC) if t.startswith("brasileir") else ""


def _cpf_da_pessoa(pessoa: dict) -> str:
    """O CPF de 11 dígitos que passa no módulo 11, ou vazio. O SIRC confere o
    dígito (seção 4, «CPF: verificado de acordo com algoritmo módulo 11»), e
    um CPF que não passa derrubaria o registro inteiro."""
    if _texto(pessoa.get("documento_tipo")).upper() not in ("", "CPF"):
        return ""
    n = "".join(c for c in _texto(pessoa.get("documento_numero"))
                if c.isdigit())
    return n if len(n) == 11 and _cpf_valido(n) else ""


def o_que_falta(con: sqlite3.Connection | None, registro: dict) -> list[str]:
    """O que impede este registro de ir ao SIRC. Só calcula.

    A CONFERENCIA VEM ANTES DO ARQUIVO, e aqui ela vale mais que em qualquer
    outro lugar: o § 4º pune **o fornecimento de informação inexata** com a
    penalidade do art. 92 da Lei 8.212 **e ação regressiva do INSS**. Mandar
    errado é pior que não mandar.
    """
    faltas: list[str] = []
    if not _texto(registro.get("data_ato")):
        faltas.append("a data do ato")
    if not _texto(registro.get("nome")):
        faltas.append("o nome")
    tipo = _texto(registro.get("tipo")).upper()

    # **A REGRA DE DATA DOS TRÊS ATOS (seção 4.8 do manual) SE APLICA A CADA
    # UM DENTRO DE `atos`** — desde 14/09/2026 `tipo` é a ESPÉCIE do
    # registro (NASCIMENTO/CASAMENTO/OBITO), e não mais «AVERBACAO» — ver
    # `pendentes_de_remessa`. Um registro pode carregar várias averbações
    # pendentes juntas, e cada uma tem a própria data para conferir.
    for ato in registro.get("atos", []) or []:
        tipo_ato = _texto(ato.get("tipo")).upper()
        if tipo_ato in ATOS_COM_DATA and not _texto(ato.get("data_ato")):
            faltas.append(ATOS_COM_DATA[tipo_ato]["regra"])

    if tipo and tipo not in ESPECIES_PRONTAS_PARA_O_SIRC:
        faltas.append(
            f"o envelope de {tipo.lower()} para o SIRC ainda não foi "
            f"construído contra o XSD do manual — fica retido para não "
            f"sair incompleto")
        return faltas

    matricula = _texto(registro.get("matricula"))
    if not matricula:
        faltas.append("a matrícula de 32 dígitos")
    else:
        try:
            RCM.partes(matricula)
        except RCM.MatriculaError as erro:
            faltas.append(f"a matrícula não bate com o formato: {erro}")

    # **O FATO NÃO VEM DEPOIS DO REGISTRO** — a mesma régua de
    #   `crc_carga.o_que_falta`, que já retinha. Medido em 08/10/2026 no
    #   casamento 8366: celebração 08/10 e registro 07/10 — a CRC retinha e o
    #   SIRC mandava. Duas réguas para o mesmo dado divergem; e aqui o § 4º
    #   pune informação inexata.
    if tipo in ("NASCIMENTO", "NATIMORTO", "CASAMENTO", "CASAMENTO_RELIGIOSO"):
        fato = _data_iso(registro.get("data_fato"))
        ato = _data_iso(registro.get("data_ato"))
        if fato and ato and fato > ato:
            rotulo = ("do nascimento" if tipo in ("NASCIMENTO", "NATIMORTO")
                      else "da celebração")
            faltas.append(
                f"a data {rotulo} ({fato[8:10]}/{fato[5:7]}/{fato[:4]}) é "
                f"depois da data do registro ({ato[8:10]}/{ato[5:7]}/{ato[:4]}) "
                "— isso não é possível, e é sinal de que uma das duas datas "
                "está errada no assento. Confira contra o livro de papel "
                "antes de mandar")

    if tipo == "NASCIMENTO" and con is not None and (
            _codigo_local_nascimento(con, registro)
            not in LOCAL_NASCIMENTO_SIRC):
        faltas.append(
            "o local do nascimento (estabelecimento de saúde ou fora dele) — "
            "o SIRC recusa o registro sem ele; informe «Onde nasceu» em "
            "«Editar informações» na ficha do assento")

    # **O CASAMENTO EXIGE OS DOIS NOMES, medido no XSD e nos OBRIGATORIOS do
    # manual técnico** (`NOMECONJUGE1`, `NOMECONJUGE2`) — o SIRC não tem
    # marcador de ignorado para o nome do próprio cônjuge (só para o dos
    # genitores, dentro de `filiacoesConjuge`): um casamento sem um dos dois
    # nomes não é um casamento, e não há «cônjuge ignorado» no manual.
    if tipo in ("CASAMENTO", "CASAMENTO_RELIGIOSO") and con is not None:
        assento_id = registro.get("assento_id")
        pessoas = ({p["papel"]: dict(p) for p in
                   RCA.pessoas_do_assento(con, assento_id,
                                          ("NUBENTE1", "NUBENTE2"))}
                  if assento_id is not None else {})
        for papel, rotulo in (("NUBENTE1", "primeiro"),
                              ("NUBENTE2", "segundo")):
            if not _texto(pessoas.get(papel, {}).get("nome")):
                faltas.append(f"o nome do {rotulo} cônjuge")

    # **ÓBITO E NATIMORTO EXIGEM O NOME DO PRINCIPAL** — sem marcador de
    # ignorado possível para o registro inteiro (é a própria identidade do
    # ato), na mesma lógica do nome do cônjuge no casamento. O papel que
    # guarda esse nome muda com a espécie (`FALECIDO` no óbito,
    # `REGISTRADO` no natimorto — ver `PAPEL_PRINCIPAL_DO_OBITO`).
    if tipo in PAPEL_PRINCIPAL_DO_OBITO and con is not None:
        assento_id = registro.get("assento_id")
        papel = PAPEL_PRINCIPAL_DO_OBITO[tipo]
        achados = ([] if assento_id is None else
                   RCA.pessoas_do_assento(con, assento_id, (papel,)))
        principal = dict(achados[0]) if achados else {}
        rotulo = "falecido" if tipo == "OBITO" else "natimorto"
        if not _texto(principal.get("nome")):
            faltas.append(f"o nome do {rotulo}")

    return faltas


def campo(nome: str, valor: Any = "") -> str:
    """Um campo do SIRC — o valor, OU o marcador de ignorado. Nunca os dois.

    **É AQUI QUE ESTE ENVELOPE SE SEPARA DO DA CRC**, e é a razão de haver dois
    montadores e não uma montagem que sirva aos dois:

        «Quando um campo não estiver informado, o marcador de campo ignorado
         **deve** ser informado. Analogamente, o marcador **não pode** estar
         informado quando houver preenchimento do campo.»

    Na CRC, tag em branco já quer dizer «nulo ou Ignorado(a)» e basta deixá-la
    vazia. Aqui, tag vazia é campo **mal preenchido**. Uma montagem única
    acertaria um envelope e erraria o outro exatamente onde o dado falta — que é
    onde os dois discordam.

    **O MARCADOR NÃO SE CALCULA**: ele vem da tabela medida, porque concorda em
    gênero com o substantivo do campo. Campo sem marcador conhecido sai só com o
    valor, e sai **vazio** quando não há — deixar de sair produziria um XML sem o
    elemento, que é uma terceira coisa que o manual não prevê.
    """
    texto = _texto(valor)
    if texto:
        return _tag(nome, texto)
    marcador = MARCADOR_IGNORADO.get(nome)
    if marcador:
        return _tag(marcador, "true")
    return _tag(nome)


def _conferir_um_pedaco(xml: str) -> list[str]:
    achados: list[str] = []
    for nome, marcador in MARCADOR_IGNORADO.items():
        tem_marcador = f"<{marcador}>true</{marcador}>" in xml
        # `<nome>` nao casa com `<nomeIgnorado>`: o `>` vem colado ao nome.
        cheio = re.search(rf"<{nome}>[^<]+</{nome}>", xml)
        if tem_marcador and cheio:
            achados.append(
                f"«{nome}» saiu preenchido e marcado como ignorado ao mesmo "
                f"tempo — o manual diz que o marcador não pode estar informado "
                f"quando houver preenchimento")
    return achados


# **OS FILHOS DE CADA NÍVEL — generalizado em 14/09/2026, ao entrar o
# casamento.** O nascimento tinha um nível de aninhamento (`registro` →
# `filiacoesNascimento`); o casamento tem dois (`registro` → `conjuge1`/
# `conjuge2` → `filiacoesConjuge`), e a MESMA confusão de tag ocorre em cada
# nível: `sexo`/`sexoIgnorado` aparece no cônjuge E dentro de cada filiação
# dele. `_conferir_um_pedaco` continua olhando só o nível de fora; quem
# desce nos filhos é `_conferir_recursivo`.
FILHOS_DE: dict[str, tuple[str, ...]] = {
    None: ("filiacoesNascimento", "conjuge1", "conjuge2", "filiacoesObito"),
    "conjuge1": ("filiacoesConjuge",), "conjuge2": ("filiacoesConjuge",),
}


def _conferir_recursivo(xml: str, tag_do_pai: str | None = None) -> list[str]:
    """Confere um pedaço, descendo nos filhos que aquele nível pode ter.

    **CADA NÍVEL SE CONFERE À PARTE**, porque a mesma tag (`nome`, `sexo`,
    `dataNascimento`...) se repete em níveis diferentes com sentidos
    diferentes — o nome do cônjuge e o nome do pai dele não são a mesma
    pessoa, e uma conferência que lesse tudo junto confundiria os dois.
    """
    filhas = FILHOS_DE.get(tag_do_pai, ())
    resto = xml
    blocos_por_tag: list[tuple[str, list[str]]] = []
    for tag in filhas:
        blocos = re.findall(rf"<{tag}>.*?</{tag}>", xml, re.DOTALL)
        for bloco in blocos:
            resto = resto.replace(bloco, "", 1)
        if blocos:
            blocos_por_tag.append((tag, blocos))
    achados: list[str] = list(_conferir_um_pedaco(resto))
    for tag, blocos in blocos_por_tag:
        for bloco in blocos:
            achados.extend(_conferir_recursivo(bloco, tag))
    return achados


def _conferir_um_registro(xml_do_registro: str) -> list[str]:
    """Confere UM registro (nascimento OU casamento), descendo nos filhos que
    ele tiver — filiações do nascimento, ou os dois cônjuges do casamento."""
    return _conferir_recursivo(xml_do_registro, None)


def conferir_marcadores(xml: str) -> list[str]:
    """Os campos que saíram com valor **e** com marcador de ignorado. Só lê.

    A REGRA TEM DOIS LADOS E O SEGUNDO É O QUE ESCAPA. Faltar o marcador quem
    monta percebe; sobrar o marcador ao lado de um campo cheio ninguém percebe,
    porque o XML continua bem formado e a linha continua completa. Esta função
    existe para o segundo lado, e a tela a chama antes de oferecer o arquivo.

    **CADA `registro*Inclusao`/`registro*Alteracao` SE CONFERE À PARTE, E
    CADA NÍVEL DENTRO DELE TAMBÉM — achado em 13/09/2026, em dois tempos, e
    generalizado em 14/09/2026 ao entrar o casamento.** Primeiro, ao ligar
    as filiações: `nome`/`nomeIgnorado` são os MESMOS nomes de tag no
    registro e dentro de cada filiação, e uma conferência que lesse o XML
    inteiro de um registro confundia o nome do REGISTRADO com o do PAI.
    **Corrigido — e não bastou**: um lote real de 250 registros (a carga do
    acervo, 14/09/2026) acusou o mesmo falso positivo de novo, agora entre
    PESSOAS DIFERENTES — o sexo preenchido do registrado Fulano ao lado do
    sexo ignorado do registrado Beltrano, no mesmo lote, pareciam «o mesmo
    campo cheio e ignorado ao mesmo tempo». A conferência agora separa por
    registro primeiro, e só depois recursivamente por nível — a mesma lição
    («a mesma palavra em dois lugares não quer dizer a mesma coisa»), pela
    enésima vez.

    **E `\\1\\2` É O QUE IMPEDE `Alteracao` DE FECHAR COM `Inclusao`** — os
    três atos (14/09/2026) fizeram este módulo passar a montar
    `registroXAlteracao` também; sem a referência ao mesmo grupo capturado,
    um lote misto (uma inclusão e uma alteração) casaria a abertura de uma
    com o fecho da outra.
    """
    # `finditer` + `.group(0)`, e não `findall` — com dois grupos de
    # captura, `findall` devolveria tuplas (`("Nascimento", "Alteracao")`),
    # e não o texto inteiro que `_conferir_um_registro` espera.
    registros = [m.group(0) for m in re.finditer(
        r"<registro(\w+?)(Inclusao|Alteracao)>.*?</registro\1\2>",
        xml, re.DOTALL)]
    if not registros:
        # Compatibilidade com quem confere um pedaço solto (testes, ou um
        # bloco de filiação isolado) — sem `registro*Inclusao`/`*Alteracao`
        # nenhum para separar, confere o texto inteiro como um pedaço só.
        return _conferir_um_registro(xml)
    achados: list[str] = []
    for registro in registros:
        achados.extend(_conferir_um_registro(registro))
    return achados


# ------------------------------------------ o que já saiu para o SIRC
#
# **MEDIDO EM 06/10/2026: O ENVIO PELA API NÃO DEIXAVA RASTRO.** O botão
# «Enviar» chamava a Central, mostrava a resposta numa faixa verde e
# esquecia. No dia seguinte o mesmo registro voltava à lista — e a
# conferência do gestor o cobrava como atrasado para sempre. O registro do
# envio mora em `ge_envios` (do gestor), e a CHAVE é a mesma que
# `gestor_conferencia.regra_sirc` procura: «onde:assento_id:data do ato mais
# novo». Uma chave diferente gravaria o envio e a cobrança continuaria.

def _data_iso(valor: Any) -> str:
    bruto = str(valor or "")[:10]
    try:
        return date.fromisoformat(bruto).isoformat()
    except ValueError:
        return ""


def referencia_do_envio(r: dict) -> str:
    """A chave do registro em `ge_envios` — a da regra do gestor.

    A ALTERAÇÃO leva a data do ato mais novo: averbação feita depois do
    envio é envio novo, e não pode sumir por causa do envio antigo."""
    datas = [d for d in (_data_iso(a.get("data_ato"))
                         for a in r.get("atos") or []) if d]
    ultima = max(datas) if datas else _data_iso(r.get("data_ato"))
    base = f"{r.get('onde') or 'rc_assentos'}:{r.get('assento_id')}"
    return f"{base}:{ultima}" if ultima else base


def ja_enviados(con: sqlite3.Connection, central: str = "SIRC") -> set[str]:
    """As referências com envio registrado. Só lê; sem a tabela, nenhuma."""
    try:
        linhas = con.execute(
            "SELECT referencia FROM ge_envios WHERE central = ? "
            "AND situacao <> 'REJEITADO' AND referencia IS NOT NULL",
            (central,)).fetchall()
    except sqlite3.OperationalError:
        return set()
    return {linha[0] for linha in linhas}


def sem_os_ja_enviados(con: sqlite3.Connection, registros: list[dict]) -> list[dict]:
    """A remessa sem o que já tem envio registrado — o mesmo critério da
    regra do gestor, para a tela e a cobrança dizerem a mesma coisa."""
    enviados = ja_enviados(con)
    saida = []
    for r in registros:
        base = f"{r.get('onde') or 'rc_assentos'}:{r.get('assento_id')}"
        if referencia_do_envio(r) in enviados or (
                base.startswith("rc_assentos:") and base in enviados):
            continue
        saida.append(r)
    return saida


def quantas_pendentes(con: sqlite3.Connection) -> int:
    """O número do painel das comunicações (`rc_obrigacoes._quantas`, que
    procura esta função antes de `pendentes_de_remessa`). Sem ela o painel
    contava também o que já tem envio registrado — o mesmo aviso eterno que
    a tela do SIRC tinha até 06/10/2026."""
    return len(sem_os_ja_enviados(con, pendentes_de_remessa(con)))


def cancelamentos_sem_os_ja_enviados(con: sqlite3.Connection,
                                     registros: list[dict]) -> list[dict]:
    enviados = ja_enviados(con, "SIRC_CANCELAMENTO")
    return [r for r in registros if f"rc_assentos:{r.get('id')}" not in enviados]


def montar(con: sqlite3.Connection | None, registros: list[dict], *,
           cns: str, competencia: str = "") -> dict:
    """A remessa em lotes de até 250, e o que ficou retido. Só lê.

    **O QUE NÃO PODE IR NÃO SOME**: volta em `retidos`, com o motivo. E aqui isso
    pesa mais do que na CRC — o § 4º pune **o fornecimento de informação
    inexata** com a penalidade do art. 92 da Lei 8.212/1991 e com **ação
    regressiva do INSS**. Mandar errado é pior que não mandar.
    """
    prontos, retidos = [], []
    for r in registros:
        faltas = o_que_falta(con, r)
        if faltas:
            # O `assento_id` VAI JUNTO — relato #13: «opcao facilitada de
            # corrigir». Motivo sem caminho e diagnostico sem tratamento:
            # aparece toda vez que se gera a remessa e ninguem conserta.
            #
            #   **E ele NAO E o `id`.** Nos atos da divisao tripartite o `id` e
            #   do ATO, e o link montado com ele abriria a ficha de OUTRO
            #   assento — e ninguem desconfia de uma ficha que abre.
            retidos.append({"nome": r.get("nome"), "tipo": r.get("tipo"),
                            "onde": r.get("onde"), "faltas": faltas,
                            "assento_id": r.get("assento_id")})
            continue
        prontos.append(r)

    # **CADA ESPÉCIE VAI NUM ARQUIVO PRÓPRIO, E NUNCA MISTURADA** — medido
    # nos três exemplos do manual (seção 7): `movimentoNascimentoTO`,
    # `movimentoCasamentoTO` e `movimentoObitoTO` são sempre mostrados
    # sozinhos, um elemento-raiz por arquivo, nunca dois juntos. E a própria
    # API confirma: o WSDL público (`SircWs/Movimento?wsdl`) declara
    # operações SEPARADAS por espécie —`enviarMovimentoNascimento`,
    # `enviarMovimentoCasamento`, `enviarMovimentoObito` — e não uma única
    # operação genérica. Misturar nascimento e casamento no mesmo lote
    # produziria um XML que nenhuma das duas operações aceita.
    #
    # `CASAMENTO_RELIGIOSO` **entra no MESMO arquivo do civil**, e não um
    # terceiro: é o mesmo `movimentoCasamentoTO`/`registroCasamentoInclusao`
    # — muda o livro (`tipoLivro`), e o livro já vem da matrícula.
    ENVELOPE_DA_ESPECIE: dict[str, tuple[str, str, str, Any]] = {
        "NASCIMENTO": ("movimentoNascimentoTO", "versaoLayoutNascimento",
                       VERSAO_LAYOUT_NASCIMENTO, _registro),
        "CASAMENTO": ("movimentoCasamentoTO", "versaoLayoutCasamento",
                      VERSAO_LAYOUT_CASAMENTO, _registro_casamento),
        "CASAMENTO_RELIGIOSO": ("movimentoCasamentoTO", "versaoLayoutCasamento",
                                VERSAO_LAYOUT_CASAMENTO, _registro_casamento),
        "OBITO": ("movimentoObitoTO", "versaoLayoutObito",
                  VERSAO_LAYOUT_OBITO, _registro_obito),
        # **NATIMORTO USA O MESMO ENVELOPE DO ÓBITO** — o manual (seção
        # 5.4) não lhe dá `movimentoNatimortoTO` nenhum: o que muda é só o
        # `tipoLivro` (já vem da matrícula, ver `PAPEL_PRINCIPAL_DO_OBITO`).
        "NATIMORTO": ("movimentoObitoTO", "versaoLayoutObito",
                      VERSAO_LAYOUT_OBITO, _registro_obito),
    }

    # `especie` VAZIA CAI NO NASCIMENTO — é a forma dos testes que só
    # exercitam a matrícula/base comum, sem espécie nenhuma («tipo=""», o
    # generico que já existia antes de casamento entrar). Um registro assim
    # nunca chega até aqui vindo do banco de verdade — `pendentes_de_
    # remessa()` sempre grava `especie` — e `o_que_falta` já teria retido
    # qualquer espécie de verdade que não esteja pronta.
    por_especie: dict[str, list[dict]] = {}
    for r in prontos:
        por_especie.setdefault(_texto(r.get("tipo")).upper(), []).append(r)

    lotes = []
    numero = 0
    for especie, registros_da_especie in por_especie.items():
        raiz, tag_versao, versao, montador = ENVELOPE_DA_ESPECIE.get(
            especie, ENVELOPE_DA_ESPECIE["NASCIMENTO"])
        for lote in em_lotes(registros_da_especie):
            numero += 1
            corpo = "".join(montador(con, r) for r in lote)
            xml = ('<?xml version="1.0" encoding="utf-8"?>'
                   f"<{raiz}>"
                   f"<{tag_versao}>{versao}</{tag_versao}>"
                   f"{corpo}"
                   f"</{raiz}>")
            cabe = cabe_no_arquivo(xml)
            lotes.append({"numero": numero, "especie": especie,
                          "quantos": len(lote), "xml": xml,
                          "referencias": [referencia_do_envio(r) for r in lote],
                          "bytes": cabe["bytes"], "cabe": cabe["cabe"],
                          "avisos": conferir_marcadores(xml)})
    return {"lotes": lotes, "quantos": len(prontos), "retidos": retidos}


# ------------------------------------- os TRÊS ATOS, embutidos na Alteração
#
# **NÃO HÁ ENVELOPE PRÓPRIO PARA AVERBAÇÃO/ANOTAÇÃO/RETIFICAÇÃO** — medido no
# manual (seção 6.1): eles são blocos (`averbacoesNascimento`, etc.) dentro
# do MESMO `registroXAlteracao` que carrega o registro inteiro de novo. As
# tags mudam por espécie, mas a estrutura interna é idêntica nas três.
_TAG_DOS_ATOS: dict[str, tuple[str, str, str]] = {
    "NASCIMENTO": ("averbacoesNascimento", "anotacoesNascimento",
                  "retificacoesNascimento"),
    "CASAMENTO": ("averbacoesCasamento", "anotacoesCasamento",
                 "retificacoesCasamento"),
    "CASAMENTO_RELIGIOSO": ("averbacoesCasamento", "anotacoesCasamento",
                           "retificacoesCasamento"),
    "OBITO": ("averbacoesObito", "anotacoesObito", "retificacoesObito"),
    "NATIMORTO": ("averbacoesObito", "anotacoesObito", "retificacoesObito"),
}

# **`motivoAverbacao` É MEDIDO CONTRA A PRODUÇÃO** — das 37 averbações reais
# desta casa (33 de nascimento, 4 de casamento), **36 são o mutirão do art.
# 347** (CPF/RG averbados em massa), que bate exatamente com o valor
# `ANOTACAO_CPF` do enum — presente nas TRÊS espécies
# (`motivoAverbacaoNascimento`/`Casamento`/`Obito`). A única exceção
# («Determinação do oficial…», uma correção de livro físico) não bate com
# nenhum motivo estruturado, e cai em `OUTROS` — que o próprio manual
# reserva para isso, exigindo o complemento junto.
_MOTIVO_AVERBACAO_POR_PALAVRA: tuple[tuple[str, str], ...] = (
    ("ART. 347", "ANOTACAO_CPF"),
)


def _motivo_averbacao(fundamento: Any) -> str:
    """O `motivoAverbacao` medido, ou `OUTROS` — nunca inventado. Só calcula."""
    bruto = _texto(fundamento).upper()
    for pedaco, motivo in _MOTIVO_AVERBACAO_POR_PALAVRA:
        if pedaco in bruto:
            return motivo
    return "OUTROS"


def _bloco_dos_atos(especie: str, atos: list[dict]) -> str:
    """Os blocos `averbacoes{Especie}`/`anotacoes{Especie}`/
    `retificacoes{Especie}`, na ordem em que `atos` chegou (que já é a da
    data, mais antigo primeiro — ver `pendentes_de_remessa`).

    **`motivoAnotacao` E O CAMPO ALTERADO DA RETIFICAÇÃO NÃO SÃO
    MEDIDOS** — esta casa tem **zero** anotações e retificações em
    produção (só averbação, e só a do art. 347). Por isso as duas usam
    `OUTROS`/o texto livre de `fundamento`, que o manual aceita como
    alternativa sempre que a classificação não é conhecida (\"ao menos um
    dos campos é obrigatório\" — nunca os dois em branco).
    """
    tag_averbacao, tag_anotacao, tag_retificacao = _TAG_DOS_ATOS.get(
        especie, _TAG_DOS_ATOS["NASCIMENTO"])
    partes = []
    for ato in atos:
        tipo_ato = _texto(ato.get("tipo")).upper()
        data = data_hora_sirc(ato.get("data_ato"))
        fundamento = _texto(ato.get("fundamento"))
        if tipo_ato == "AVERBACAO":
            motivo = _motivo_averbacao(fundamento)
            complementares = (_tag("dadosComplementares", fundamento)
                             if motivo == "OUTROS" else "")
            partes.append(
                f"<{tag_averbacao}>"
                f"{_tag('dataAverbacao', data)}"
                f"{_tag('motivoAverbacao', motivo)}"
                f"{complementares}"
                f"</{tag_averbacao}>")
        elif tipo_ato == "ANOTACAO":
            partes.append(
                f"<{tag_anotacao}>"
                f"{_tag('dataAnotacao', data)}"
                f"{_tag('motivoAnotacao', 'OUTROS')}"
                f"{_tag('dadosComplementares', fundamento or 'Anotação')}"
                f"</{tag_anotacao}>")
        elif tipo_ato == "RETIFICACAO":
            partes.append(
                f"<{tag_retificacao}>"
                f"{_tag('dataRetificacao', data)}"
                f"{_tag('dadosComplementares', fundamento or 'Retificação')}"
                f"</{tag_retificacao}>")
    return "".join(partes)


def _filiacoes_nascimento(con: sqlite3.Connection | None,
                          assento_id: Any) -> str:
    """As `filiacoesNascimento`, com `minOccurs="2"` no XSD — e o módulo não
    montava nenhuma.

    **DUAS OCORRÊNCIAS, SEMPRE**, mesmo quando um dos genitores é
    desconhecido: o XSD conta ELEMENTOS, e um `<filiacoesNascimento>` com
    `nomeIgnorado` continua sendo um elemento. Marcar como ignorado é
    honesto; omitir o segundo bloco quebraria a estrutura que a Central
    exige, e não é a mesma coisa que "não temos o pai".
    """
    if con is None or assento_id is None:
        pessoas = {}
    else:
        pessoas = {p["papel"]: p for p in
                   RCA.pessoas_do_assento(con, assento_id, ("PAI", "MAE"))}
    partes = []
    for papel in ("PAI", "MAE"):
        pessoa = dict(pessoas.get(papel) or {})
        nome = _texto(pessoa.get("nome"))
        sexo_bruto = _texto(pessoa.get("sexo")).upper()
        # **NA ORDEM DO `xs:sequence` DE `filiacaoNascimento`** — e cada um
        # destes o SIRC-Web de produção cobrou em 09/10/2026, por genitor.
        nat_mun, nat_uf = _municipio_sirc(con, pessoa.get("naturalidade_cidade"),
                                          pessoa.get("naturalidade_uf"))
        cpf = _cpf_da_pessoa(pessoa)
        data_nasc = data_hora_sirc(pessoa.get("data_nascimento")) \
            if _texto(pessoa.get("data_nascimento")) else ""
        idade = _texto(pessoa.get("idade_no_fato"))
        idade = idade if idade.isdigit() and len(idade) <= 3 else ""
        blocos = [
            (_tag("codigoIBGEMunicipioNaturalidade", int(nat_mun))
             if nat_mun else ""),
            # A naturalidade NÃO foi cobrada em 09/10: sai quando se acha o
            # município, e fica de fora (como sempre ficou) quando não.
            (_tag("codigoIBGEUFNaturalidade", int(nat_uf)) if nat_uf else ""),
            # A profissão é CÓDIGO da CBO-CNIS, e essa tabela não veio para
            # esta casa — o texto («lavrador») está no assento, o código não.
            # Ignorada é a verdade; «-2 = outras» seria afirmar uma escolha.
            _tag("codigoOcupacaoSDCIgnorado", "true"),
            # Data OU idade: com a data, a idade fica de fora (a mesma regra
            # que o validador aplica ao falecido — «a idade não deve ser
            # informada quando a data de nascimento estiver preenchida»).
            (_tag("dataNascimento", data_nasc) if data_nasc
             else _tag("dataNascimentoIgnorada", "true") if not idade else ""),
            (f"<documentos><dono>FILIACAO_NASCIMENTO</dono>"
             f"{_tag('numero', cpf)}<tipo>CPF</tipo></documentos>"
             if cpf else ""),
            _tag("cpfIgnorado", "false" if cpf else "true"),
            _tag("documentosIgnorado", "false" if cpf else "true"),
            ("" if data_nasc else _tag("idade", int(idade)) if idade
             else _tag("idadeIgnorada", "true")),
            campo("nacionalidade", _nacionalidade_sirc(
                pessoa.get("nacionalidade"))),
            campo("nome", nome),
            # **COM A NATURALIDADE BRASILEIRA VAI O PAÍS** — o validador
            # recusou (09/10/2026) a naturalidade sem ele: «se o país de
            # nascimento não é Brasil, o município de naturalidade não pode
            # ser preenchido». Município achado em `ib_municipios` é Brasil.
            (_tag("paisNascimento", NACIONALIDADE_BRASIL_SIRC)
             if nat_mun else ""),
            campo("sexo", SEXO.get(sexo_bruto, "")),
        ]
        partes.append("<filiacoesNascimento>" + "".join(blocos)
                      + "</filiacoesNascimento>")
    return "".join(partes)


def _endereco_da_filiacao(con: sqlite3.Connection | None,
                          assento_id: Any) -> dict:
    """O domicílio dos genitores — da MÃE, e do PAI quando ela não o tem.

    O XSD tem UM endereço de filiação por registro (`logradouroFiliacao`,
    `numeroLogradouroFiliacao`, `bairroFiliacao`, `codigoIBGEMunicipioFiliacao`
    e a UF), e não um por genitor. A mãe vem primeiro pela mesma razão da
    remessa do IBGE: é dela a residência que a estatística de natalidade usa."""
    if con is None or assento_id is None:
        return {}
    pessoas = {p["papel"]: dict(p) for p in
               RCA.pessoas_do_assento(con, assento_id, ("PAI", "MAE"))}
    for papel in ("MAE", "PAI"):
        p = pessoas.get(papel) or {}
        if _texto(p.get("endereco")) or _texto(p.get("cidade")):
            partes = _endereco_em_partes(p.get("endereco"))
            mun, uf = _municipio_sirc(con, p.get("cidade"), p.get("uf"))
            return {"logradouro": partes["logradouro"],
                    "numero": partes["numero"],
                    "bairro": _texto(p.get("bairro")) or partes["bairro"],
                    "municipio": mun, "uf": uf}
    return {}


def _registro(con: sqlite3.Connection | None, r: dict) -> str:
    """Um registro do movimento. Só monta o que `montar()` já filtrou como
    pronto — `o_que_falta` retém o que ainda não tem envelope próprio.

    NÃO INVENTA O QUE NÃO MEDIU. Os campos do XSD que dependem de tabela que não
    veio junto (ocupação CBO-CNIS, países SDC, município do IBGE dentro do
    registro) **não saem preenchidos por semelhança** — saem OMITIDOS, porque
    o manual não lhes dá marcador de ignorado (são `minOccurs="0"` puros).
    Escolher por semelhança seria assinar por quem preencheu.
    """
    assento_id = r.get("assento_id")
    reg = {}
    if con is not None and assento_id is not None:
        pessoas = RCA.pessoas_do_assento(con, assento_id, ("REGISTRADO",))
        if pessoas:
            reg = dict(pessoas[0])
    sexo_bruto = _texto(reg.get("sexo")).upper()
    cpf = _texto(reg.get("cpf")) or _texto(r.get("cpf_registrado"))
    # **`dnv` É `string11` NO XSD — 11 CARACTERES, NO MÁXIMO.** Achado
    # conferindo o primeiro lote real: o valor guardado vem com hífens
    # (`30-94275444-3`, 13 caracteres) e estourava o limite. É a mesma
    # regra que a CRC já aplica à DNV, só que lá ela exige exatamente 11
    # DÍGITOS; aqui o XSD só limita o TAMANHO do texto — não são a mesma
    # conta, e por isso não se reaproveita a função da CRC direto.
    dnv_bruto = _texto(r.get("dnv"))
    dnv = dnv_bruto if len(dnv_bruto) <= 11 else ""
    # **`horaNascimento` TEM PADRÃO PRÓPRIO NO XSD** —
    # `([0-1][0-9]|2[0-3]):[0-5][0-9]`, ou seja, só existem 00:00 a 23:59.
    # Achado na carga do acervo em 14/09/2026: o `hora_fato` digitado do
    # .docx traz **"24:00", "24:40", "19:68"** — hora e minuto que não
    # existem, provavelmente erro de digitação ou de leitura do papel
    # antigo. Mandar assim quebraria o arquivo inteiro contra o XSD; a
    # hora inválida sai como ignorada, e não se adivinha o valor certo.
    hora_bruta = _texto(r.get("hora_fato"))
    hora = hora_bruta if HORA_VALIDA.fullmatch(hora_bruta) else ""
    cod_local = _codigo_local_nascimento(con, r)
    p = RCM.partes(_texto(r.get("matricula")))
    # **O MUNICÍPIO DO NASCIMENTO É O DO PARTO** (manual, quadro 2: «Município
    # de Nascimento – Código IBGE»), e a naturalidade tem campo próprio —
    # desde a Lei 13.484/2017 ela pode ser a da residência da mãe, e nos
    # assentos de 06/10/2026 é: nascidos em Imperatriz, naturais de Montes
    # Altos. A cidade do parto vem no fim do endereço do local do fato
    # («Rua Coriolano Milhomem, Centro, Imperatriz/MA»); sem ela, a
    # naturalidade, que é o que a carga da CRC usa para o mesmo campo.
    lugar_do_fato = _endereco_em_partes(
        _coluna_do_assento(con, r, "local_fato_endereco"))
    nasc_mun, nasc_uf = _municipio_sirc(con, lugar_do_fato["cidade"],
                                        lugar_do_fato["uf"])
    if not nasc_mun:
        nasc_mun, nasc_uf = _municipio_sirc(
            con, reg.get("naturalidade_cidade"), reg.get("naturalidade_uf"))
    nat_mun, nat_uf = _municipio_sirc(con, reg.get("naturalidade_cidade"),
                                      reg.get("naturalidade_uf"))
    domicilio = _endereco_da_filiacao(con, assento_id)

    # **A ORDEM AQUI É A DO `xs:sequence` DO XSD, E NÃO A DE QUEM ESCREVE O
    # CÓDIGO — 13/09/2026.** `registroNascimentoAbstrato` estende
    # `registroCivil`; os campos da BASE vêm primeiro (na ordem em que o
    # XSD os declara), e só depois os da extensão. Uma primeira versão
    # deste módulo pôs `nome` logo no início e `observacoes` no fim — os
    # dois errados — e a Central recusaria por estrutura, não por
    # conteúdo: é a mesma lição que `crc_carga.registro_de_nascimento` já
    # tinha aprendido, só que na CRC o CPF é que saía fora de ordem.
    partes = [
        # --- base (`registroCivil`) ---
        _tag("acervo", int(p["acervo"])),
        _tag("anoRegistro", int(p["ano"])),
        _tag("codServentia", int(p["cns"])),
        _tag("dataRegistro", data_hora_sirc(r.get("data_ato"))),
        _tag("dvMatricula", p["dv"]),
        _tag("folha", int(p["folha"])),
        _tag("numeroLivro", int(p["livro"])),
        _tag("observacoes", ""),
        _tag("termo", int(p["termo"])),
        _tag("tipoLivro", int(p["livro_tipo"])),
        # `tipoServico` é o mesmo campo «serviço» da matrícula — sempre 55,
        # RCPN — e por isso não é uma segunda fonte: é a mesma.
        _tag("tipoServico", int(p["servico"])),
        # --- extensão (`registroNascimentoAbstrato`) ---
        (_tag("bairroFiliacao", domicilio["bairro"][:100])
         if domicilio.get("bairro") else ""),
        campo("codigoIBGEMunicipio", nasc_mun and int(nasc_mun)),
        campo("codigoIBGEMunicipioFiliacao",
              domicilio.get("municipio") and int(domicilio["municipio"])),
        campo("codigoIBGEUF", nasc_uf and int(nasc_uf)),
        campo("codigoIBGEUFFiliacao",
              domicilio.get("uf") and int(domicilio["uf"])),
        (_tag("codigoIBGEMunicipioNaturalidade", int(nat_mun))
         if nat_mun else ""),
        (_tag("codigoIBGEUFNaturalidade", int(nat_uf)) if nat_uf else ""),
        campo("cpf", cpf),
        campo("dataNascimento", data_do_sirc(r.get("data_fato"))),
        # **DNV: UM DOS DOIS É OBRIGATÓRIO, E NÃO HÁ TERCEIRA RESPOSTA** no
        # XSD (`dnv` ou `dnvInexistente`, nunca os dois). Este sistema não
        # distingue "não perguntei" de "perguntei e não existe" — a mesma
        # ambiguidade que as quatro marcas do óbito já documentam —, e
        # enquanto essa terceira resposta não existir aqui, ausência de
        # `dnv` sai como `dnvInexistente`.
        _tag("dnv", dnv) if dnv else _tag("dnvInexistente", "true"),
        _filiacoes_nascimento(con, assento_id),
        campo("horaNascimento", hora),
        # `local` vem depois de `horaNascimento`/`impressosSeguranca` no
        # `xs:sequence` — ver `LOCAL_NASCIMENTO_SIRC`.
        (_tag("local", LOCAL_NASCIMENTO_SIRC[cod_local])
         if cod_local in LOCAL_NASCIMENTO_SIRC else ""),
        campo("logradouroFiliacao", domicilio.get("logradouro", "")[:255]),
        campo("nome", r.get("nome")),
        campo("numeroLogradouroFiliacao", domicilio.get("numero", "")[:20]),
        campo("sexo", SEXO.get(sexo_bruto, "")),
        # **AVERBAÇÃO/ANOTAÇÃO/RETIFICAÇÃO, SE HOUVER** — ver
        # `pendentes_de_remessa`: um registro só carrega `atos` quando é
        # uma Alteração (o registro já existia e ganhou um ato novo).
        _bloco_dos_atos("NASCIMENTO", r.get("atos") or []),
        _tag("filiacaoNomesIguais", "false"),
    ]
    # **INCLUSÃO OU ALTERAÇÃO — A MESMA FUNÇÃO, TAG DIFERENTE.** O manual
    # (seção 6.1) manda reenviar TODOS os dados do registro numa Alteração;
    # como este módulo já monta o registro inteiro para a Inclusão, a
    # Alteração é a MESMA montagem, só com os blocos de ato embutidos e a
    # tag trocada — nunca uma segunda função que pudesse divergir da
    # primeira.
    raiz = ("registroNascimentoAlteracao" if r.get("atos")
           else "registroNascimentoInclusao")
    return f"<{raiz}>" + "".join(partes) + f"</{raiz}>"


# ---------------------------------------------------------------- o CASAMENTO
#
# MEDIDO CONTRA O XSD EXTRAÍDO DO MANUAL (`registroCasamento`, seção 8.3), com
# a mesma disciplina do nascimento — e não por semelhança:
#
#   `registroCasamentoAbstrato` ESTENDE `registroCivil` — a MESMA base do
#   nascimento (acervo, anoRegistro, codServentia, dataRegistro, dvMatricula,
#   folha, numeroLivro, termo, tipoLivro, tipoServico), na MESMA ordem. Só
#   depois vêm os campos próprios do casamento, e só depois os dois cônjuges.
#
#   `filiacoesConjuge` TEM `minOccurs="2"`, como `filiacoesNascimento` — duas
#   ocorrências sempre, mesmo quando um genitor é desconhecido.
#
#   `sexoConjuge` é o MESMO enum que `SEXO` já mede para o nascimento
#   (MASCULINO, FEMININO, NAO_BINARIO, OUTROS, NAO_DECLARADO, IGNORADO) —
#   reaproveitado, e não copiado.
#
#   **O NOME DO CÔNJUGE NÃO TEM MARCADOR DE IGNORADO** — `conjugeAbstrato`
#   declara `nomeEspecial`, mas nenhum `nomeIgnorado`. Por isso ele sai com
#   `_tag()` direto, e não com `campo()`: `o_que_falta` já recusa o registro
#   antes de chegar aqui se um dos nomes faltar, e usar `campo()` inventaria
#   uma tag (`nomeIgnorado`) que o XSD deste tipo não tem.


def _filiacoes_casamento(con: sqlite3.Connection | None, assento_id: Any,
                         indice: int) -> str:
    """As duas `filiacoesConjuge` do cônjuge `indice` (1 ou 2).

    Papéis medidos em `rc_assento.PAPEIS_DA_ESPECIE["CASAMENTO"]`:
    `MAE_NUBENTE{indice}` e `PAI_NUBENTE{indice}` — a mesma forma de
    `_filiacoes_nascimento`, só que amarrada ao cônjuge certo.
    """
    if con is None or assento_id is None:
        pessoas = {}
    else:
        papeis = (f"MAE_NUBENTE{indice}", f"PAI_NUBENTE{indice}")
        pessoas = {p["papel"]: p for p in
                   RCA.pessoas_do_assento(con, assento_id, papeis)}
    partes = []
    for papel in (f"MAE_NUBENTE{indice}", f"PAI_NUBENTE{indice}"):
        pessoa = pessoas.get(papel, {})
        nome = pessoa["nome"] if pessoa else ""
        sexo_bruto = _texto(pessoa["sexo"]).upper() if pessoa else ""
        partes.append(
            "<filiacoesConjuge>"
            f"{campo('nome', nome)}"
            f"{campo('sexo', SEXO.get(sexo_bruto, ''))}"
            "</filiacoesConjuge>")
    return "".join(partes)


def _conjuge(con: sqlite3.Connection | None, assento_id: Any,
            indice: int) -> str:
    """Um `<conjuge1>` ou `<conjuge2>` inteiro — nome, sexo, CPF e as duas
    filiações.

    **O CPF VAI DENTRO DE `documentosConjuge`, e não como campo direto** —
    medido no XSD: `conjugeAbstrato` só tem `cpfConjugeIgnorado` (booleano);
    o número mora em `documentosConjuge` com `tipo=CPF` e `dono=CONJUGEn`,
    que é a MESMA forma do documento do falecido/do registrado — ao
    contrário da CRC, cujo `TIPO_DOC` não enumera CPF (`crc_carga.py`, "o
    CPF vai cru no e-Proclamas e com máscara na Certidão" — outra família de
    diferenças entre Centrais). Sem CPF, sai só o marcador.
    """
    if con is None or assento_id is None:
        pessoa = {}
    else:
        achados = RCA.pessoas_do_assento(con, assento_id,
                                         (f"NUBENTE{indice}",))
        pessoa = dict(achados[0]) if achados else {}
    nome = pessoa.get("nome", "")
    sexo_bruto = _texto(pessoa.get("sexo")).upper()
    cpf = "".join(c for c in _texto(pessoa.get("documento_numero"))
                  if c.isdigit())
    documento = (
        f"<documentosConjuge><dono>CONJUGE{indice}</dono>"
        f"{_tag('numero', cpf)}<tipo>CPF</tipo></documentosConjuge>"
        if len(cpf) == 11 else "")
    # **A ORDEM É A DO `xs:sequence` DE `conjugeAbstrato`, e não a ordem
    # "natural" de escrever (nome, sexo, documento)** — achado só ao validar
    # contra o XSD de verdade: `documentosConjuge`/`cpfConjugeIgnorado` e
    # `filiacoesConjuge` vêm ANTES de `nome`, que vem antes de `sexo`. A
    # primeira versão pôs nome e sexo primeiro — bem formado, e a Central
    # recusaria por estrutura, não por conteúdo. É a mesma lição que
    # `_registro()` (nascimento) já tinha aprendido, agora num nível mais
    # fundo.
    partes = [
        documento,
        _tag("cpfConjugeIgnorado", "false" if documento else "true"),
        _filiacoes_casamento(con, assento_id, indice),
        _tag("nome", nome),
        campo("sexo", SEXO.get(sexo_bruto, "")),
    ]
    return f"<conjuge{indice}>" + "".join(partes) + f"</conjuge{indice}>"


def _registro_casamento(con: sqlite3.Connection | None, r: dict) -> str:
    """Um `registroCasamentoInclusao`. Só monta o que `montar()` já filtrou
    como pronto — `o_que_falta` retém quem não tem os dois nomes.

    NÃO INVENTA O QUE NÃO MEDIU: campos do XSD que dependem de dado que este
    sistema ainda não guarda por casamento (celebrante religioso, escritura
    antenupcial, proclamas, endereço e ocupação dos cônjuges) saem OMITIDOS
    — são todos `minOccurs="0"` sem marcador de ignorado, e escolher por
    semelhança seria assinar por quem preencheu.
    """
    assento_id = r.get("assento_id")
    p = RCM.partes(_texto(r.get("matricula")))
    regime = regime_casamento_sirc(r.get("regime_bens"), r.get("data_fato"))

    partes = [
        # --- base (`registroCivil`) — MESMA ORDEM do nascimento ---
        _tag("acervo", int(p["acervo"])),
        _tag("anoRegistro", int(p["ano"])),
        _tag("codServentia", int(p["cns"])),
        _tag("dataRegistro", data_hora_sirc(r.get("data_ato"))),
        _tag("dvMatricula", p["dv"]),
        _tag("folha", int(p["folha"])),
        _tag("numeroLivro", int(p["livro"])),
        _tag("observacoes", ""),
        _tag("termo", int(p["termo"])),
        _tag("tipoLivro", int(p["livro_tipo"])),
        _tag("tipoServico", int(p["servico"])),
        # --- extensão (`registroCasamentoAbstrato`) ---
        campo("dataCelebracaoCasamento", data_hora_sirc(r.get("data_fato"))),
    ]
    # `regimeCasamento` NÃO TEM MARCADOR DE IGNORADO no XSD — sai só quando
    # resolvido, e omitido quando não (nunca uma tag vazia: ver o cabeçalho
    # de `REGIME_CASAMENTO_SIRC`).
    if regime:
        partes.append(_tag("regimeCasamento", regime))
    # **AVERBAÇÃO/ANOTAÇÃO/RETIFICAÇÃO VÊM AQUI** — depois de
    # `regimeCasamento` e antes dos cônjuges, na ordem do
    # `registroCasamentoAbstrato`; `conjuge1`/`conjuge2` só entram na
    # extensão de fora (`registroCasamento`), por isso ficam por último.
    partes.append(_bloco_dos_atos("CASAMENTO", r.get("atos") or []))
    partes.append(_conjuge(con, assento_id, 1))
    partes.append(_conjuge(con, assento_id, 2))
    raiz = ("registroCasamentoAlteracao" if r.get("atos")
           else "registroCasamentoInclusao")
    return f"<{raiz}>" + "".join(partes) + f"</{raiz}>"


# ------------------------------------------------------------------ o ÓBITO
#
# MEDIDO CONTRA O XSD EXTRAÍDO DO MANUAL (`registroObitoAbstrato`) e contra o
# exemplo real da seção 7.2, com a mesma disciplina do casamento:
#
#   `registroObitoAbstrato` ESTENDE `registroCivil` — a MESMA base do
#   nascimento e do casamento, na MESMA ordem.
#
#   `filiacoesObito` TEM `minOccurs="2"`, como `filiacoesNascimento` — duas
#   ocorrências sempre, mesmo quando um genitor é desconhecido.
#
#   **O NOME DO FALECIDO TEM MARCADOR, MAS NÃO ADJACENTE** — achado só ao ler
#   o exemplo real: `nome`/`nomeEspecial` do falecido aparecem logo depois de
#   `nacionalidadeIgnorada`, e `nomeIgnorado` só aparece bem mais adiante na
#   sequência, perto de `nomeLocalObito`. É a mesma família do defeito de
#   ordem do `_conjuge()` — a diferença é que aqui o par nome/marcador não
#   fica junto nem quando os dois existem: são dois pontos fixos e distantes
#   do `xs:sequence`, e por isso este módulo não usa `campo()` para o nome do
#   falecido (que assumiria os dois adjacentes) — usa `_tag()` no lugar do
#   nome e, no lugar do marcador, só emite `nomeIgnorado` se o nome faltar
#   (caso que `o_que_falta` já recusa antes de chegar aqui).
#
#   **`corPele` E `estadoCivil` TÊM VOCABULÁRIO PRÓPRIO DO SIRC** — sem
#   «IGNORADA»/«OUTROS», ao contrário dos da CRC. Ver `COR_PELE_SIRC` e
#   `_estado_civil_sirc()`.
#
#   **`documentosDeclarante`/`documentosFalecido` SÃO O MESMO `documento` do
#   casamento** (`tipo=CPF`, `dono=DECLARANTE`/`FALECIDO`) — reaproveitado,
#   e não copiado.
#
#   NÃO INVENTA O QUE NÃO MEDIU: os campos de endereço do falecido e do local
#   do óbito (logradouro, número, complemento, bairro, município/UF em
#   código IBGE), a ocupação (CBO-CNIS), o país estrangeiro e os benefícios
#   previdenciários não têm coluna nesta casa — saem OMITIDOS, e não
#   preenchidos por semelhança.


def _filiacoes_obito(con: sqlite3.Connection | None, assento_id: Any) -> str:
    """As `filiacoesObito` (PAI e MAE do falecido), `minOccurs="2"` no XSD —
    a mesma forma de `_filiacoes_nascimento`, com o mesmo papel PAI/MAE
    (`rc_assento.PAPEIS_DA_ESPECIE["OBITO"]`)."""
    if con is None or assento_id is None:
        pessoas = {}
    else:
        pessoas = {p["papel"]: p for p in
                   RCA.pessoas_do_assento(con, assento_id, ("PAI", "MAE"))}
    partes = []
    for papel in ("PAI", "MAE"):
        pessoa = pessoas.get(papel, {})
        nome = pessoa["nome"] if pessoa else ""
        sexo_bruto = _texto(pessoa["sexo"]).upper() if pessoa else ""
        partes.append(
            "<filiacoesObito>"
            f"{campo('nome', nome)}"
            f"{campo('sexo', SEXO.get(sexo_bruto, ''))}"
            "</filiacoesObito>")
    return "".join(partes)


def _documento_obito(dono: str, numero_bruto: Any, tag: str) -> str:
    """Um `<documentosDeclarante>`/`<documentosFalecido>` com CPF, ou nada —
    a mesma forma de `documento` já usada em `_conjuge` (casamento): só sai
    quando há 11 dígitos, porque um documento parcial afirmaria um CPF que
    ninguém conferiu."""
    numero = "".join(c for c in _texto(numero_bruto) if c.isdigit())
    if len(numero) != 11:
        return ""
    return (f"<{tag}><dono>{dono}</dono>"
            f"{_tag('numero', numero)}<tipo>CPF</tipo></{tag}>")


def _registro_obito(con: sqlite3.Connection | None, r: dict) -> str:
    """Um `registroObitoInclusao`. Só monta o que `montar()` já filtrou como
    pronto — `o_que_falta` retém quem não tem o nome do falecido.

    **SERVE TAMBÉM AO NATIMORTO** — o manual diz, com todas as letras
    («5.4», medido em 14/09/2026): «para os casos em que o falecido seja um
    natimorto, o tipo do livro (…) deve possuir o valor "5"». Não há
    `registroNatimorto` no XSD: é o MESMO `registroObitoAbstrato`, e o que
    muda é só o `tipoLivro` — que já vem pronto da matrícula
    (`rc_matricula.LIVRO_DA_ESPECIE["NATIMORTO"] == "5"`). **O que muda
    aqui dentro** é o papel da casa: `rc_assento.PAPEIS_DA_ESPECIE`
    chama o principal de `FALECIDO` no óbito e de `REGISTRADO` no
    natimorto — a mesma pessoa, dois nomes de papel — mas o `dono` que vai
    no XML continua sendo `FALECIDO`, porque é o único valor que o enum
    `donoDocumento` conhece para essa posição."""
    assento_id = r.get("assento_id")
    papel_do_principal = PAPEL_PRINCIPAL_DO_OBITO.get(
        _texto(r.get("tipo")).upper(), "FALECIDO")
    falecido, declarante = {}, {}
    if con is not None and assento_id is not None:
        achados_f = RCA.pessoas_do_assento(con, assento_id,
                                           (papel_do_principal,))
        if achados_f:
            falecido = dict(achados_f[0])
        achados_d = RCA.pessoas_do_assento(con, assento_id, ("DECLARANTE",))
        if achados_d:
            declarante = dict(achados_d[0])

    p = RCM.partes(_texto(r.get("matricula")))
    nome_falecido = _texto(falecido.get("nome"))
    sexo_bruto = _texto(falecido.get("sexo")).upper()
    estado_civil = _estado_civil_sirc(falecido.get("estado_civil"))
    idade = falecido.get("idade_no_fato")
    # **AS COLUNAS DO ASSENTO VÊM DO ASSENTO** (ver `_coluna_do_assento`): até
    # 09/10/2026 estas cinco saíam «ignoradas» no óbito 1984 com o assento
    # preenchido — a consulta dos pendentes não as trazia.
    def _int_ou_nada(v: Any) -> int | None:
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    cor_bruta = _texto(_coluna_do_assento(con, r, "cor_raca")).upper()
    tipo_local = TIPO_LOCAL_OBITO_SIRC.get(
        _int_ou_nada(_coluna_do_assento(con, r, "ibge_local_obito")), "")
    tipo_morte = TIPO_MORTE_SIRC.get(
        _int_ou_nada(_coluna_do_assento(con, r, "ibge_natureza_obito")), "")
    causa_morte = _texto(_coluna_do_assento(con, r, "causa_morte"))[:1024]
    sepultamento = _texto(_coluna_do_assento(con, r, "local_sepultamento"))
    nome_local = _texto(_coluna_do_assento(con, r, "local_fato_nome"))
    # A DO é `string9` no XSD — os nove dígitos (oito e o verificador); o
    # banco a guarda com hífen («12345678-9»). Outra forma sai ignorada.
    numero_do = "".join(c for c in _texto(
        _coluna_do_assento(con, r, "numero_do")) if c.isdigit())
    numero_do = numero_do if len(numero_do) == 9 else ""
    # O ENDEREÇO DO FALECIDO E O DO LUGAR DO ÓBITO — cobrados pelo SIRC-Web
    # de produção em 09/10/2026 («informado ou ignorado», os dois).
    end_falecido = _endereco_em_partes(falecido.get("endereco"))
    fal_mun, fal_uf = _municipio_sirc(con, falecido.get("cidade"),
                                      falecido.get("uf"))
    end_obito = _endereco_em_partes(
        _coluna_do_assento(con, r, "local_fato_endereco"))
    ob_mun, ob_uf = _municipio_sirc(con, end_obito["cidade"], end_obito["uf"])
    data_nasc_falecido = data_hora_sirc(falecido.get("data_nascimento")) \
        if _texto(falecido.get("data_nascimento")) else ""
    hora_bruta = _texto(r.get("hora_fato"))
    hora = hora_bruta if HORA_VALIDA.fullmatch(hora_bruta) else ""

    doc_declarante = _documento_obito(
        "DECLARANTE", declarante.get("documento_numero"),
        "documentosDeclarante")
    doc_falecido = _documento_obito(
        "FALECIDO", falecido.get("documento_numero"), "documentosFalecido")

    partes = [
        # --- base (`registroCivil`) — MESMA ORDEM do nascimento/casamento ---
        _tag("acervo", int(p["acervo"])),
        _tag("anoRegistro", int(p["ano"])),
        _tag("codServentia", int(p["cns"])),
        _tag("dataRegistro", data_hora_sirc(r.get("data_ato"))),
        _tag("dvMatricula", p["dv"]),
        _tag("folha", int(p["folha"])),
        _tag("numeroLivro", int(p["livro"])),
        _tag("observacoes", ""),
        _tag("termo", int(p["termo"])),
        _tag("tipoLivro", int(p["livro_tipo"])),
        _tag("tipoServico", int(p["servico"])),
        # --- extensão (`registroObitoAbstrato`), na ordem do `xs:sequence` ---
        # O endereço do falecido e o do lugar do óbito, os benefícios e a
        # nacionalidade entraram em 09/10/2026: o SIRC-Web de produção recusou
        # o óbito 1984 por eles (ver `_endereco_em_partes`).
        (_tag("bairro", (_texto(falecido.get("bairro"))
                         or end_falecido["bairro"])[:100])
         if (_texto(falecido.get("bairro")) or end_falecido["bairro"]) else ""),
        (_tag("bairroObito", end_obito["bairro"][:100])
         if end_obito["bairro"] else ""),
        # Benefício PREVIDENCIÁRIO é o número do INSS (NB), e esta casa não o
        # guarda — `beneficio_social` é outra coisa. Ignorado é a verdade.
        _tag("beneficiosPrevidenciariosIgnorado", "true"),
        campo("causaMorteConhecida", causa_morte),
        # A causa preenchida vai COM o marcador em `false` — é a forma do
        # exemplo do manual, e o validador recusou a causa sozinha em
        # 09/10/2026 («ignorado preenchido ou não ignorado vazio»).
        (_tag("causaMorteConhecidaIgnorada", "false") if causa_morte else ""),
        campo("codigoIBGEMunicipioLogradouro", fal_mun and int(fal_mun)),
        campo("codigoIBGEMunicipioLogradouroObito", ob_mun and int(ob_mun)),
        campo("codigoIBGEUFLogradouro", fal_uf and int(fal_uf)),
        campo("codigoIBGEUFLogradouroObito", ob_uf and int(ob_uf)),
        campo("corPele", COR_PELE_SIRC.get(cor_bruta, "")),
        campo("dataNascimentoFalecido", data_nasc_falecido),
        campo("dataObito", data_do_sirc(r.get("data_fato"))),
        # O número da DO mora em `rc_assentos.numero_do` (este comentário
        # dizia, até 09/10/2026, que «não há coluna» — havia, e o óbito saía
        # com a DO ignorada).
        campo("declaracaoObito", numero_do),
        doc_declarante,
        doc_falecido,
        _tag("cpfFalecidoIgnorado", "false" if doc_falecido else "true"),
        _tag("documentosFalecidoIgnorado", "false" if doc_falecido else "true"),
        campo("estadoCivil", estado_civil),
        _filiacoes_obito(con, assento_id),
        campo("horaObito", hora),
        # `idade` NÃO TEM MARCADOR DE IGNORADO NO XSD — `campo()` inventaria
        # `idadeIgnorada`, que a Central recusa (medido: 50 de 398 óbitos
        # reais falhavam por isso antes deste ajuste). Omitida quando não há
        # valor, como `eleitor` — **e omitida também quando há a data de
        # nascimento**: «a idade do falecido não deve ser informada quando a
        # data de nascimento estiver preenchida» (SIRC-Web, 09/10/2026).
        (_tag("idade", int(idade))
         if idade not in (None, "") and not data_nasc_falecido else ""),
        campo("logradouro", end_falecido["logradouro"][:255]),
        campo("logradouroObito", end_obito["logradouro"][:100]),
        campo("lugarSepultamentoCemiterio", sepultamento[:255]),
        campo("nacionalidade",
              _nacionalidade_sirc(falecido.get("nacionalidade"))),
        # `nome`/`nomeEspecial` do FALECIDO — ver a nota acima sobre a
        # posição não adjacente de `nomeIgnorado` no XSD. `o_que_falta` já
        # recusa o registro antes de chegar aqui se o nome faltar; o `if`
        # continua aqui porque esta função também é chamada direto em teste.
        (_tag("nome", nome_falecido) if nome_falecido else ""),
        (_tag("nomeEspecial", "false") if nome_falecido else ""),
        campo("nomeDeclarante", declarante.get("nome")),
        ("" if nome_falecido else _tag("nomeIgnorado", "true")),
        campo("nomeLocalObito", nome_local[:255]),
        campo("numeroLogradouro", end_falecido["numero"][:20]),
        campo("numeroLogradouroObito", end_obito["numero"][:20]),
        campo("sexo", SEXO.get(sexo_bruto, "")),
        campo("tipoLocalObito", tipo_local),
        campo("tipoMorte", tipo_morte),
        # **AVERBAÇÃO/ANOTAÇÃO/RETIFICAÇÃO ENTRAM AQUI**, entre `tipoMorte`
        # e `filiacaoNomesIguais` — a mesma posição para NATIMORTO, que
        # reusa este envelope inteiro (ver `_TAG_DOS_ATOS`).
        _bloco_dos_atos(_texto(r.get("tipo")).upper(), r.get("atos") or []),
        _tag("filiacaoNomesIguais", "false"),
    ]
    raiz_base = "registroObitoAlteracao" if r.get("atos") else "registroObitoInclusao"
    return f"<{raiz_base}>" + "".join(partes) + f"</{raiz_base}>"


# **AS QUATRO ESPÉCIES QUE O § 3º CITA**, na ordem em que o XSD as declara —
# e é a ordem que decide o nome da tag: o manual escreve «nascimento,
# natimorto, casamento ou óbito» na letra da lei, mas o XSD (seção 11, elemento
# `declaracaoInexistenciaMovimentoTO`) declara os quatro booleanos na ordem
# Casamento → Nascimento → Óbito → ObitoNatimorto — copiar a ordem da lei
# produziria um XML com a sequência errada.
ESPECIES_DA_DECLARACAO: tuple[str, ...] = (
    "Casamento", "Nascimento", "Obito", "ObitoNatimorto")


def declaracao_de_inexistencia(*, competencia: str,
                               especies: tuple[str, ...] = ESPECIES_DA_DECLARACAO
                               ) -> str:
    """O mês sem movimento — art. 225, § 3º, até o 5º dia útil do mês seguinte.

    **MÊS VAZIO TAMBÉM SE COMUNICA**, e esta é a obrigação que mais se esquece,
    justamente porque não há trabalho que a lembre: não houve registro, não houve
    remessa, e ninguém repara na falta. O § 4º não distingue — a sanção alcança o
    descumprimento, e não haver o que mandar não é descumprir só se a declaração
    for feita.

    **O ENVELOPE NÃO ERA `<movimento><cns>...<quantidade>`, e essa forma nunca
    existiu no manual — achado em 14/09/2026, ao ler o XSD de verdade
    (`declaracaoInexistenciaMovimentoServicoTO`, seção 11).** Ele é
    `{competencia, declaracaoInexistenciaMovimentoCasamento,
    ...Nascimento, ...Obito, ...ObitoNatimorto}` — quatro booleanos
    independentes, um por espécie, e não uma única marca genérica. E a
    `competencia` é `MM/AAAA` (o XSD tem o padrão: `([0]?[1-9]|10|11|12)/
    [0-9]{4}`) — não `AAAA-MM`, que é a forma que a tela já usa por dentro.

    **`especies` deixa declarar só o que faltou**, para o dia em que um mês
    tiver nascimento mas não tiver casamento — hoje a tela só oferece «não
    houve nada», que é o caso do § 3º na letra («nenhum... nascimento,
    natimorto, casamento OU óbito»), e por isso o padrão é as quatro.
    """
    bruto = _texto(competencia)
    if len(bruto) != 7 or bruto[4] != "-":
        raise SircError("Diga de qual mês é a declaração, no formato AAAA-MM.")
    ano, mes = bruto[:4], bruto[5:7]
    if not (ano.isdigit() and mes.isdigit() and 1 <= int(mes) <= 12):
        raise SircError("Diga de qual mês é a declaração, no formato AAAA-MM.")
    competencia_sirc = f"{int(mes)}/{ano}"

    marcados = set(especies)
    booleanos = "".join(
        _tag(f"declaracaoInexistenciaMovimento{sufixo}", "true")
        for sufixo in ESPECIES_DA_DECLARACAO if sufixo in marcados)
    return ('<?xml version="1.0" encoding="utf-8"?>'
            "<declaracaoInexistenciaMovimentoServicoTO>"
            f"{_tag('competencia', competencia_sirc)}"
            f"{booleanos}"
            "</declaracaoInexistenciaMovimentoServicoTO>")


# ------------------------------------------------- o CANCELAMENTO DE TERMO
#
# **NÃO É UM DOS SETE DO ART. 225 — é uma OBRIGAÇÃO SEPARADA, seção 5.7 do
# manual.** «Esta funcionalidade deve ser utilizada apenas para termos que
# não foram utilizados para fins de registro civil e/ou que foram
# cancelados no livro pela serventia.» Não é uma Alteração de registro (que
# reenvia dados de um registro que EXISTE) — é o oposto: dizer que aquele
# termo NUNCA VALEU, e por isso tem envelope, operação e versão de layout
# PRÓPRIOS (`movimentoCancelamentoTO`, `enviarMovimentoCancelamento`,
# `versaoLayoutCancelamento` "1.1" — não "5.0").
#
# **MEDIDO CONTRA A CASA**: `rc_assentos.situacao` já tem `CANCELADO`
# (`rc_assento.SITUACOES`), e há **um caso real** desta serventia — o
# assento 1231, lavrado no livro físico errado (A-1 em vez de A-24, a
# mesma história da averbação medida em `sirc-tres-atos-sao-alteracao`) e
# cancelado depois. O `motivo` (`string350`, OBRIGATÓRIO no XSD) não tem
# coluna própria nesta casa — é lido da averbação mais recente sobre o
# mesmo assento, que na prática já é onde o oficial registrou por que
# cancelou. Sem averbação com fundamento, o candidato fica retido: campo
# obrigatório sem valor não se inventa.
VERSAO_LAYOUT_CANCELAMENTO = "1.1"

# **`tipoRegistroCivil` SÓ TEM TRÊS VALORES** — medido no XSD: NASCIMENTO,
# CASAMENTO, OBITO. NATIMORTO não está entre eles (usa o `tipoLivro="5"`
# dentro do óbito para SE REGISTRAR, mas cancelamento pergunta o tipo do
# REGISTRO CIVIL, não o livro) — e não há como saber, sem medir contra a
# Central, se um termo de natimorto cancelado se declara como NASCIMENTO ou
# como OBITO. Fica retido, e não adivinhado.
TIPO_REGISTRO_CIVIL_CANCELAMENTO: dict[str, str] = {
    "NASCIMENTO": "NASCIMENTO", "CASAMENTO": "CASAMENTO",
    "CASAMENTO_RELIGIOSO": "CASAMENTO", "OBITO": "OBITO",
}


def pendentes_de_cancelamento(con: sqlite3.Connection,
                              limite: int = 20_000) -> list[dict]:
    """Os termos cancelados nesta casa que o SIRC ainda não sabe. Só lê.

    Mesma regra do resto da remessa: o que veio do acervo (EOFICIO/
    ARQUIVO/IMPORTACAO) não se remete — o cancelamento, se houve, já
    aconteceu há décadas, antes de o SIRC existir.
    """
    con.row_factory = sqlite3.Row
    marcadores = ",".join("?" * len(ORIGENS_QUE_NAO_SE_REMETEM))
    achados = []
    for r in con.execute(
            f"""SELECT * FROM rc_assentos
                WHERE situacao = 'CANCELADO'
                  AND especie IN ('NASCIMENTO','CASAMENTO',
                                  'CASAMENTO_RELIGIOSO','OBITO','NATIMORTO')
                  AND COALESCE(origem,'') NOT IN ({marcadores})
             ORDER BY data_ato, id LIMIT ?""",
            (*ORIGENS_QUE_NAO_SE_REMETEM, limite)):
        d = dict(r)
        # **O MOTIVO NÃO TEM COLUNA PRÓPRIA** — lido da averbação mais
        # recente sobre este assento, que na prática é onde o oficial já
        # registra por que cancelou (o caso real: "Determinação do
        # oficial à lavratura no livro físico errado").
        motivo = con.execute(
            """SELECT fundamento FROM rc_atos
                WHERE assento_id=? AND tipo='AVERBACAO'
                  AND COALESCE(fundamento,'')<>''
             ORDER BY data_ato DESC, id DESC LIMIT 1""",
            (d["id"],)).fetchone()
        d["motivo"] = motivo[0] if motivo else ""
        # **A MATRÍCULA DO TERMO CANCELADO PODE ESTAR EM USO POR OUTRO
        # ASSENTO VIVO** — achado em 02/10/2026 contra a produção: o óbito
        # 8311 (cancelado) e o 8315 (ativo) têm a MESMA matrícula de 32
        # dígitos, e o nascimento 8300 (cancelado) a mesma do 8298 (ativo).
        # O termo foi refeito no mesmo lugar do livro. O SIRC identifica o
        # termo pela matrícula (`registroTermoCancelado` não leva nome nem
        # id desta casa) — mandar este cancelamento cancelaria, lá, o
        # registro que VALE. Fica retido, com o número do assento vivo,
        # para quem decide conferir no SIRC-Web o que de fato foi enviado.
        if _texto(d.get("matricula")):
            vivo = con.execute(
                """SELECT id FROM rc_assentos
                    WHERE matricula = ? AND id <> ?
                      AND COALESCE(situacao,'ATIVO') = 'ATIVO'
                 ORDER BY id LIMIT 1""",
                (d["matricula"], d["id"])).fetchone()
            d["matricula_em_uso_por"] = vivo[0] if vivo else None
        else:
            d["matricula_em_uso_por"] = None
        achados.append(d)
    return achados


def o_que_falta_cancelamento(registro: dict) -> list[str]:
    """O que impede este termo cancelado de ir ao SIRC. Só calcula."""
    faltas: list[str] = []
    matricula = _texto(registro.get("matricula"))
    if not matricula:
        faltas.append("a matrícula de 32 dígitos")
    else:
        try:
            RCM.partes(matricula)
        except RCM.MatriculaError as erro:
            faltas.append(f"a matrícula não bate com o formato: {erro}")
    if not _texto(registro.get("motivo")):
        faltas.append(
            "o motivo do cancelamento — sem coluna própria nesta casa, "
            "ele vem da averbação mais recente sobre o assento; sem uma "
            "averbação com o fundamento preenchido, o campo obrigatório "
            "do SIRC fica sem valor")
    especie = _texto(registro.get("especie")).upper()
    if especie not in TIPO_REGISTRO_CIVIL_CANCELAMENTO:
        faltas.append(
            f"o tipo de registro civil do cancelamento para «{especie}» — "
            f"o enum do SIRC só conhece NASCIMENTO, CASAMENTO e OBITO")
    vivo = registro.get("matricula_em_uso_por")
    if vivo:
        faltas.append(
            f"a matrícula deste termo é a mesma do assento {vivo}, que está "
            f"ATIVO — o SIRC identifica o termo pela matrícula, e este "
            f"cancelamento cancelaria lá o registro que vale. Confira no "
            f"SIRC-Web se este termo chegou a ser enviado antes de decidir")
    return faltas


def _registro_termo_cancelado(registro: dict) -> str:
    """Um `registroTermoCancelado`. Só monta o que `montar_cancelamento()`
    já filtrou como pronto."""
    p = RCM.partes(_texto(registro.get("matricula")))
    especie = _texto(registro.get("especie")).upper()
    partes = [
        _tag("motivo", registro.get("motivo")),
        _tag("tipoRegistroCivil", TIPO_REGISTRO_CIVIL_CANCELAMENTO[especie]),
        _tag("codServentia", int(p["cns"])),
        _tag("acervo", int(p["acervo"])),
        _tag("tipoServico", int(p["servico"])),
        _tag("termo", int(p["termo"])),
        _tag("tipoLivro", int(p["livro_tipo"])),
        _tag("anoRegistro", int(p["ano"])),
        _tag("dvMatricula", p["dv"]),
        _tag("folha", int(p["folha"])),
        _tag("numeroLivro", int(p["livro"])),
    ]
    return "<registroTermoCancelado>" + "".join(partes) \
        + "</registroTermoCancelado>"


def montar_cancelamento(registros: list[dict]) -> dict:
    """A remessa dos termos cancelados, em lotes de até 250 — mesmo teto
    do resto da casa (seção 3 do manual, genérica para todo arquivo).

    **NÃO PASSA POR `ENVELOPE_DA_ESPECIE`**: cancelamento não é uma das
    sete coisas do art. 225, tem envelope e versão de layout PRÓPRIOS
    (`movimentoCancelamentoTO`, "1.1"), e por isso é montado à parte —
    juntá-lo à máquina de `montar()` faria um lote de cancelamento parecer
    mais uma espécie do art. 225, que ele não é.
    """
    prontos, retidos = [], []
    for r in registros:
        faltas = o_que_falta_cancelamento(r)
        if faltas:
            retidos.append({"nome": r.get("nome"), "especie": r.get("especie"),
                            "faltas": faltas, "assento_id": r.get("id")})
            continue
        prontos.append(r)

    lotes = []
    for numero, lote in enumerate(em_lotes(prontos), start=1):
        corpo = "".join(_registro_termo_cancelado(r) for r in lote)
        xml = ('<?xml version="1.0" encoding="utf-8"?>'
               "<movimentoCancelamentoTO>"
               f"{_tag('versaoLayoutCancelamento', VERSAO_LAYOUT_CANCELAMENTO)}"
               f"{corpo}"
               "</movimentoCancelamentoTO>")
        cabe = cabe_no_arquivo(xml)
        lotes.append({"numero": numero, "quantos": len(lote), "xml": xml,
                      "referencias": [f"rc_assentos:{r.get('id')}" for r in lote],
                      "bytes": cabe["bytes"], "cabe": cabe["cabe"]})
    return {"lotes": lotes, "quantos": len(prontos), "retidos": retidos}
