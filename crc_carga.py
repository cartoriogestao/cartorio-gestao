"""A carga da CRC Nacional — o XML dos registros civis.

    «o cartório está precisando do sistema pronto e amadurecido para o quanto
     antes» — o oficial, 29/08/2026

A FONTE É O MANUAL OFICIAL
    *Manual de Carga da Central de Informações do Registro Civil Nacional*,
    versão **2.6**, 79 páginas, da ARPEN-SP, guardado em
    `FONTES_EXTERNAS/CRC_manual_carga_webservice_v2.6.pdf`. **Nada aqui é
    suposto**: as tags, os obrigatórios, os anexos e as regras de validação
    saíram dele.

POR QUE A CRC VEM ANTES DO SIRC
    Não é escolha minha: é da norma. O art. 243 do Código de Normas do TJMA
    manda que as comunicações entre serventias sejam feitas **preferencialmente
    pela CRC**; o art. 226, § 1º, I, manda que a comunicação de óbito para
    anotação vá **primeiramente pelo sistema CRC**; e o art. 348, § 2º exige
    **consulta obrigatória** a ela antes de decidir restauração ou suprimento.

O QUE DECIDE QUEM PODE IR: A MATRÍCULA
    `<MATRICULA>` é obrigatória e são «somente 32 dígitos». **E o verificador
    dela não se gera** — o Anexo IV do manual é uma imagem, e o portal do SIRC
    diz que o dígito sai de um **programa que o CNJ distribui**. Testado em 244
    amostras contra tudo o que é padrão: nível de acaso.

    Medido no acervo: **243 de 244** já têm a matrícula. O que não tem **fica
    retido, com o motivo escrito** — porque declaração aceita com dado inventado
    é pior que declaração recusada: a recusada volta.

O QUE ESTE MÓDULO NÃO FAZ
    **Não envia, e não assina.** O modelo por web service exige o XML
    **assinado com e-CPF e em Base64**, e o certificado é do oficial. Ele monta
    o arquivo e diz o que falta; assinar e mandar é passo de quem tem o
    certificado — e o modelo por upload, que o manual também prevê, **não exige
    assinatura**.
"""
from __future__ import annotations

import sqlite3
from typing import Any
from xml.sax.saxutils import escape

# **A CHAVE DO VOCABULARIO SE NORMALIZA COM A FUNCAO DA CASA, E ELA SE IMPORTA.**
#
#   O defeito mais caro deste projeto foi COPIAR `normalizar_nome` com um
#   comentario dizendo que era «a mesma» — nao era, e a busca por nome deixou
#   de achar. Aqui a operacao e identica (NFKD, tira o que combina, sem caixa)
#   e por isso o import e a resposta, e nao uma quarta copia.
#
#   E a escolhida e a do lado do Registro Civil: `ibge_schema` e quem serve a
#   remessa do IBGE, que le as mesmas colunas que esta carga.
from ibge_schema import normalizar_nome as _sem_acento
from ibge_geracao import lugar as _lugar_ibge
from ri_schema import valida_cpf_cnpj as _cpf_valido
import rc_matricula as _RCM

VERSAO = "2.6"
ACAO_CARGA = "CARGA"


class CrcError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


# ------------------------------------------------------------ os movimentos

MOVIMENTO_DA_ESPECIE: dict[str, tuple[str, str, str]] = {
    # especie -> (bloco do movimento, bloco de inclusao, bloco de alteracao)
    "NASCIMENTO": ("MOVIMENTONASCIMENTOTN", "REGISTRONASCIMENTOINCLUSAO",
                   "REGISTRONASCIMENTOALTERACAO"),
    "NATIMORTO": ("MOVIMENTONASCIMENTOTN", "REGISTRONASCIMENTOINCLUSAO",
                  "REGISTRONASCIMENTOALTERACAO"),
    "CASAMENTO": ("MOVIMENTOCASAMENTOTC", "REGISTROCASAMENTOINCLUSAO",
                  "REGISTROCASAMENTOALTERACAO"),
    "CASAMENTO_RELIGIOSO": ("MOVIMENTOCASAMENTOTC",
                            "REGISTROCASAMENTOINCLUSAO",
                            "REGISTROCASAMENTOALTERACAO"),
    "OBITO": ("MOVIMENTOOBITOTO", "REGISTROOBITOINCLUSAO",
              "REGISTROOBITOALTERACAO"),
}

# A ORDEM DOS TRES BLOCOS NO ARQUIVO, E ELA E' DO XSD — nao da ordem em que os
# assentos aparecem na tela.
#
# **ACHADO EM 22/09/2026, NUMA CARGA DE VERDADE.** O oficial gerou o arquivo
# com 28 registros e a Central acusou:
#
#     Element 'MOVIMENTONASCIMENTOTN': This element is not expected.
#     Expected is one of ( MOVIMENTOCASAMENTOTC, MOVIMENTOOBITOTO ).
#
# `CARGAREGISTROS` e' uma `<xs:sequence>`: VERSAO, ACAO, CNS e entao os tres
# movimentos **nesta ordem**. O arquitetura de `montar` juntava os registros num
# dicionario por bloco e o escrevia na ordem de INSERCAO — ou seja, na ordem em
# que os assentos vinham. Naquela carga o primeiro era um casamento, e o arquivo
# saiu CASAMENTO, NASCIMENTO, OBITO: **bem formado e invalido**.
#
# **E ISSO SO APARECE COM MAIS DE UMA ESPECIE NO MESMO ARQUIVO.** Com uma
# especie ha um bloco so, e ordem de um elemento sempre esta certa — que e' por
# que os quatro testes contra o XSD passavam: cada um monta uma especie.
ORDEM_DOS_MOVIMENTOS: tuple[str, ...] = (
    "MOVIMENTONASCIMENTOTN",
    "MOVIMENTOCASAMENTOTC",
    "MOVIMENTOOBITOTO",
)

# Os OBRIGATORIOS, marcados com `*` no manual. Sem um deles o registro nao vai.
OBRIGATORIOS: dict[str, tuple[str, ...]] = {
    "NASCIMENTO": ("NOMEREGISTRADO", "MATRICULA", "DATAREGISTRO", "SEXO"),
    "CASAMENTO": ("NOMECONJUGE1", "NOMECONJUGE2", "MATRICULA", "DATAREGISTRO",
                  "DATACASAMENTO"),
    "OBITO": ("FLAGDESCONHECIDO", "NOMEFALECIDO", "MATRICULA", "DATAREGISTRO",
              "SEXO", "CORPELE"),
}

# ------------------------------------------------------- os valores fechados
#
# O QUE O MANUAL DA NA LETRA, e so isso. Onde ele manda «vide XSD» — e o XSD
# nao veio —, o campo sai VAZIO e o ato entra na lista do que falta. Escolher
# por semelhanca seria assinar por quem preencheu.

SEXO = {"M": "M", "F": "F", "MASCULINO": "M", "FEMININO": "F",
        "I": "I", "IGNORADO": "I"}

COR_PELE = {"BRANCA": "BRANCA", "PRETA": "PRETA", "PARDA": "PARDA",
            "AMARELA": "AMARELA", "INDIGENA": "INDIGENA",
            "INDÍGENA": "INDIGENA", "IGNORADA": "IGNORADA"}

# ============================================================================
# **O XSD VEIO, E ESTAVA NA CASA O TEMPO TODO — correção de 10/09/2026.**
#
#   Este bloco dizia, em cinco campos, «o manual manda ver o XSD, e o XSD não
#   veio». Ele veio: `FONTES_EXTERNAS/CRC_manual_carga_webservice_v2.6.pdf`,
#   com o texto extraído ao lado, e tem **344 enumerações `xs:enumeration`**
#   dentro. As cinco estão todas lá.
#
#   É «não achar onde eu procurei não prova que não existe» outra vez — e desta
#   vez o documento era um que esta casa já tinha baixado, como o manual do
#   Next Cloud do ONR em 07/09. **Ler um documento para uma pergunta não é
#   tê-lo lido.**
#
# **E O DEFEITO DE FUNDO ERA MAIOR QUE OS CINCO: a coluna guarda NÚMERO e o
# vocabulário é de PALAVRA.**
#
#   Medido na produção, coluna por coluna: `ibge_local_nascimento` traz 1, 2, 3
#   e 5; `ibge_natureza_obito` traz 1 e 2; `ibge_local_obito` traz 1, 3, 4 e 5.
#   São os códigos do IBGE. Um `dict` indexado por «NATURAL» nunca acha `"1"`,
#   e o `.get` devolve `None` **calado** — a tag simplesmente não saía.
#
#   **O gêmeo não calava: ele mentia.** `if assento.get("ibge_gemeo")` é
#   verdadeiro para o código **1**, que quer dizer «NÃO é gêmeo» — e por isso
#   **210 dos 212** nascimentos subiam à Central afirmando `POSSUIGEMEOS S`,
#   sem que um único deles tenha irmão gêmeo (`gemeo_ordem` e `gemeo_irmao_id`
#   estão vazios em todos).
#
#   Achado porque o oficial mandou verificar **um** registro: «verifique o json
#   do nilton» — assento 1240, nascimento nº 5172 de 1974, cujo teor diz com
#   todas as letras «O registrado não é gêmeo».
# ============================================================================

# **O TIPO DA MORTE: O XSD DIZ «VIOLENTA», COM ESSA PALAVRA.**
#
#   O que estava escrito aqui: «a CRC só enumera Natural ou Acidental, e esta
#   casa registrou Violenta; não são sinônimos, e por isso as violentas ficam
#   retidas». **A primeira metade era falsa.**
#
#   A frase «(Natural ou Acidental)» existe, e vem de uma página de
#   RECOMENDAÇÕES do manual (pág. 76), junto de uma que manda buscar o estado
#   civil numa tabela externa. **O XSD, que é contra o que o arquivo se valida,
#   enumera `'', NATURAL, VIOLENTA, IGNORADA`** — e o `VIOLENTA` está lá com
#   essa letra.
#
#   **Prosa de recomendação não é schema**, e onde os dois divergem quem manda é
#   o que valida o arquivo. Os **4 óbitos violentos** desta casa deixam de ser
#   retidos.
#
# A chave é o código do IBGE, que é o que a coluna guarda (1 e 2 medidos), e as
# palavras do acervo entram também porque o blob do E-Ofício as traz.
TIPO_MORTE = {
    "1": "NATURAL", "NATURAL": "NATURAL",
    "2": "VIOLENTA", "VIOLENTA": "VIOLENTA",
    "9": "IGNORADA", "IGNORADA": "IGNORADA", "IGNORADO": "IGNORADA",
}

# **O LOCAL DO NASCIMENTO É PALAVRA, E O DE-PARA ESTAVA NO ACERVO.**
#
#   `tbRCPN_LocalNascimento` tem as duas colunas lado a lado — `intCodigoIBGE`
#   e **`strWScrc`** —, e é o E-Ofício dizendo o que mandava à Central:
#
#     IBGE 1 Hospital                                  -> UNIDADE_SAUDE
#     IBGE 2 Outros estabelecimentos sem internação    -> UNIDADE_SAUDE
#     IBGE 3 Domicílio                                 -> FORA_UNIDADE_SAUDE
#     IBGE 5 Outros                                    -> FORA_UNIDADE_SAUDE
#     IBGE 9 Ignorado                                  -> IGNORADO
#
#   **Antes de deduzir de-para, procure a coluna que já o tem** — regra desta
#   casa, e ela nasceu deste mesmo campo: em 29/08 o `intCodigoIBGE` desmentiu
#   uma dedução minha sobre o código 4.
#
#   O XSD confirma os três valores, sem mais nenhum. Saía o **número**, que não
#   está na enumeração — em 212 de 212 nascimentos. E o campo é **obrigatório
#   para registro lavrado de 13/10/2015 em diante** (`**` no manual): um
#   nascimento novo seria recusado pela Central.
LOCAL_NASCIMENTO = {
    "1": "UNIDADE_SAUDE", "2": "UNIDADE_SAUDE",
    "3": "FORA_UNIDADE_SAUDE", "5": "FORA_UNIDADE_SAUDE",
    "9": "IGNORADO",
}

# **O LOCAL DO ÓBITO TAMBÉM, e as nove palavras estão no acervo** —
# `tbRCTO_TipoLocalObito.strDescricaoCRC`, e o XSD as confirma uma a uma.
#
#   **A ARMADILHA É QUE AS DUAS TABELAS NUMERAM DIFERENTE.** O `id` daquela
#   tabela do acervo é `1 = Ignorado` e `4 = Hospital`; o código do IBGE, que é
#   o que `rc_assentos.ibge_local_obito` guarda, é `1 = hospital` e
#   `9 = ignorado`. **Usar o id como chave poria «Ignorado» onde é hospital** —
#   é a mesma armadilha das duas tabelas de tipo de imóvel do ONR. A chave aqui
#   é o **código do IBGE**, e a palavra vem por descrição:
#
#     IBGE 1 hospital       -> HOSPITAL          (17 óbitos)
#     IBGE 3 domicílio      -> DOMICILIO         (3)
#     IBGE 4 via pública    -> VIA_PUBLICA       (5)
#     IBGE 5 outros         -> OUTRO             (6)
#     IBGE 9 ignorado       -> IGNORADO
#
#   O **2** («outro estabelecimento de saúde sem internação») vai em
#   `OUTROS_SERVICOS_SAUDE`, e fica dito que **esta casa não tem nenhum**: os
#   31 óbitos usam 1, 3, 4 e 5. É leitura por descrição, e não medição.
TIPO_LOCAL_OBITO = {
    "1": "HOSPITAL", "2": "OUTROS_SERVICOS_SAUDE", "3": "DOMICILIO",
    "4": "VIA_PUBLICA", "5": "OUTRO", "9": "IGNORADO",
}

# **O ESTADO CIVIL É CAMPO LIVRE NESTA CASA, e o XSD tem oito valores.**
#
#   Medido em `rc_pessoas.estado_civil`: **doze grafias** em 1.568 nulos e 100
#   preenchidos — «solteira», «solteiro», «Solteiro», «Solteiro(a)», «Casado»,
#   «casado», «casada», «Viúvo», «SOLTEIRO», «falecido», «falecida».
#
#   A régua é `_chave`: sem caixa **e sem acento**, e isso não é detalhe —
#   «Viúvo» com acento não achava nada, e 2 dos 31 falecidos subiam sem estado
#   civil. O feminino conta: «solteira» é `SOLTEIRO` para a Central, que
#   enumera o masculino.
#
#   **«falecido» não é estado civil** e não entra — alguém digitou a coisa
#   errada no campo, e adivinhar poria estado civil inventado numa certidão.
#   Ele vira **aviso**, em `o_que_arrumar`, com o nome de quem é.
ESTADO_CIVIL = {
    "SOLTEIRO": "SOLTEIRO", "SOLTEIRA": "SOLTEIRO", "SOLTEIRO(A)": "SOLTEIRO",
    "CASADO": "CASADO", "CASADA": "CASADO", "CASADO(A)": "CASADO",
    "VIUVO": "VIUVO", "VIUVA": "VIUVO", "VIUVO(A)": "VIUVO",
    "DIVORCIADO": "DIVORCIADO", "DIVORCIADA": "DIVORCIADO",
    "DIVORCIADO(A)": "DIVORCIADO",
    "SEPARADO": "SEPARADO", "SEPARADA": "SEPARADO",
    "SEPARADO(A)": "SEPARADO",
    "OUTROS": "OUTROS", "OUTRO": "OUTROS",
    "IGNORADO": "IGNORADO", "IGNORADA": "IGNORADO",
}

# **O REGIME DE BENS: a casa e a Central usam palavras diferentes para três
# dos cinco regimes.** `hc_schema.REGIMES` à esquerda, o XSD à direita:
#
#     COMUNHAO_PARCIAL       -> COMUNHAO_PARCIAL              (igual)
#     COMUNHAO_UNIVERSAL     -> COMUNHAO_UNIVERSAL            (igual)
#     SEPARACAO_TOTAL        -> SEPARACAO_BENS
#     SEPARACAO_OBRIGATORIA  -> SEPARACAO_LEGAL_BENS
#     PARTICIPACAO_FINAL     -> PARTICIPACAO_FINAL_AQUESTOS
#
#   **A separação obrigatória é a do art. 1.641 do Código Civil**, e a Central
#   a chama de LEGAL — a mesma coisa com dois nomes. Trocá-la pela voluntária
#   afirmaria que o casal escolheu o que a lei impôs.
#
#   E `rc_assentos.regime_bens` é **texto livre**: a produção tem «Comunhão
#   Parcial de Bens» em 2 casamentos. A régua aceita a chave da casa e a frase
#   por extenso, sem caixa e sem acento.
REGIME_CASAMENTO = {
    "COMUNHAO_PARCIAL": "COMUNHAO_PARCIAL",
    "COMUNHAO PARCIAL DE BENS": "COMUNHAO_PARCIAL",
    "COMUNHAO PARCIAL": "COMUNHAO_PARCIAL",
    "COMUNHAO_UNIVERSAL": "COMUNHAO_UNIVERSAL",
    "COMUNHAO UNIVERSAL DE BENS": "COMUNHAO_UNIVERSAL",
    "COMUNHAO UNIVERSAL": "COMUNHAO_UNIVERSAL",
    "SEPARACAO_TOTAL": "SEPARACAO_BENS",
    "SEPARACAO TOTAL DE BENS": "SEPARACAO_BENS",
    "SEPARACAO DE BENS": "SEPARACAO_BENS",
    "SEPARACAO_OBRIGATORIA": "SEPARACAO_LEGAL_BENS",
    "SEPARACAO OBRIGATORIA DE BENS": "SEPARACAO_LEGAL_BENS",
    "SEPARACAO LEGAL DE BENS": "SEPARACAO_LEGAL_BENS",
    "PARTICIPACAO_FINAL": "PARTICIPACAO_FINAL_AQUESTOS",
    "PARTICIPACAO FINAL NOS AQUESTOS": "PARTICIPACAO_FINAL_AQUESTOS",
    "OUTROS": "OUTROS", "OUTRO": "OUTROS",
    "IGNORADO": "IGNORADO", "IGNORADA": "IGNORADO",
}

# **"COMUNHÃO DE BENS" SEM QUALIFICAÇÃO VIRA PARCIAL A PARTIR DE 1977** —
# decisão do oficial em 13/09/2026, sobre o achado de 292 casamentos do
# acervo em que o papel só diz «Comunhão de Bens», sem dizer parcial ou
# universal. A Lei do Divórcio (Lei 6.515/1977, vigente desde 26/12/1977)
# tornou a comunhão PARCIAL o regime supletivo do casamento; antes dela, sob
# o Código Civil de 1916, era a universal — e por isso a régua só resolve
# «a partir de 1977», como o oficial decidiu: **para casamentos anteriores
# a essa data, o texto bruto continua sem se afirmar**, porque não houve
# decisão para eles.
ANO_DA_LEI_DO_DIVORCIO = 1977
_COMUNHAO_SEM_QUALIFICACAO = "COMUNHAO DE BENS"


def _regime_resolvido(regime_bruto: Any, data_do_casamento: Any) -> str:
    """O regime da CRC para este texto — `""` quando não dá para saber.

    **Só resolve o que já bate com o dicionário, mais o caso de 1977.** Um
    texto que não é nenhum dos dois continua indefinido de propósito — não
    se inventa regime por semelhança.
    """
    chave = _chave(regime_bruto)
    resolvido = REGIME_CASAMENTO.get(chave)
    if resolvido:
        return resolvido
    if chave == _COMUNHAO_SEM_QUALIFICACAO:
        ano = _texto(data_do_casamento)[:4]
        if ano.isdigit() and int(ano) >= ANO_DA_LEI_DO_DIVORCIO:
            return "COMUNHAO_PARCIAL"
    return ""


# **AS DUAS MARCAS DO ÓBITO TÊM TRÊS ESTADOS NOS DOIS LADOS, e isso é sorte
# medida.** `rc_marcas_do_obito` guarda `SIM`, `NAO` e `""` («não
# perguntado»); o XSD enumera `S`, `N`, `I` e `''`.
#
#   **O «não perguntado» não vira `I`.** `I` é «ignorado» — uma afirmação sobre
#   o falecido, dita à Central. Ninguém apurou e não achou: **ninguém
#   perguntou**, e a tag não sai. Medido: as duas colunas estão nulas em 31 de
#   31 óbitos, logo hoje isto não alcança ninguém — e alcançará o primeiro
#   óbito que o balcão lavrar.
MARCA_SIM_NAO = {"SIM": "S", "S": "S", "1": "S", "TRUE": "S",
                 "NAO": "N", "NÃO": "N", "N": "N", "0": "N", "FALSE": "N",
                 "IGNORADO": "I", "I": "I"}

# Os campos que o manual manda buscar no XSD e que **continuam sem resposta**.
#
# **A LISTA ESVAZIOU, E ELA FICA.** Os cinco que estavam aqui têm vocabulário
# agora, medido no XSD que já estava na casa. Apagar a constante faria o
# próximo campo sem vocabulário não ter onde ser declarado — e é ela que
# impede o pior desfecho, que é escolher valor por semelhança e a Central
# aceitar. **Lista vazia é resposta**: hoje não há campo nesta situação.
SEM_VOCABULARIO: tuple[dict, ...] = ()


def _chave(v: Any) -> str:
    """A chave para procurar num vocabulário fechado: sem caixa e sem acento.

    **`.upper()` SOZINHO NÃO BASTA, e isto foi medido na produção.** «Viúvo»
    virava a chave `VIÚVO`, que não está em `ESTADO_CIVIL` — e **2 dos 31
    falecidos subiam sem estado civil**, calados. «Comunhão Parcial de Bens»
    não achava o regime, e os dois únicos casamentos com regime preenchido o
    têm assim.

    É o `UPPER` que é ASCII pela quarta vez neste projeto, depois da busca de
    fraudes, do CNIB e do Protesto — e aqui o valor não vem do balcão: vem do
    acervo, onde ninguém padronizou nada.
    """
    return _sem_acento(v).upper()


def _texto(v: Any) -> str:
    """O valor como texto, e vazio quando não há.

    USAR SEMPRE, E NUNCA O PADRÃO DO `get`. O segundo argumento do `get` só vale
    quando a **chave falta** — e numa linha de banco a chave existe sempre; o
    que vem é `None`. Pedir o texto vazio como padrão e depois chamar `.upper()`
    estoura com `NoneType`, e este módulo estourou assim em **quatro lugares**
    na primeira execução contra dado real.

    O ensaio pegou porque o caso tinha a coluna vazia. **Teste de domínio
    escrito à mão preenche tudo, e por isso passaria** — é a mesma lição do
    ensaio contra o acervo que achou quatro defeitos na certidão do RCPN depois
    de 31 testes passarem.

    **E NORMALIZA O ACENTO SOLTO QUE VIROU LETRA ERRADA** — "NOMEREGISTRADO
    está inválido", relato da CRC em 11/09/2026, em LUCIANA HYH´TYHC KRIKATI.
    Medido: dos 15+ nomes Krikati no acervo, todos os outros escrevem a marca
    fonética com o apóstrofo comum (`'`, em "A'CAHUC", "CRY'CRY", "HYC'CRY") —
    só este tem um acento agudo solto (U+00B4), sozinho, sem letra para
    acentuar. **Não é um caractere novo do idioma: é o mesmo apóstrofo, digitado
    errado uma vez** — e por isso a troca não inventa nome, corrige a
    grafia para a convenção que a própria casa já usa em todos os outros.
    """
    s = str(v or "").strip()
    for errado in ("´", "’", "′", "`"):
        s = s.replace(errado, "'")
    return s


# Palavras que NÃO são município. O acervo às vezes grava «não consta»;
# a tela da CRC, quando o campo falta no XML, interpola a palavra JS
# «undefined». Nenhuma das duas pode ir como nome de cidade.
_AUSENCIA_DE_MUNICIPIO = frozenset({
    "undefined", "null", "none", "nan",
    "nada consta", "nao consta", "n/c", "nc",
})


def _e_ausencia_de_municipio(v: Any) -> bool:
    """Se o valor não nomeia um município de verdade."""
    s = _texto(v)
    if not s:
        return True
    chave = (s.lower().replace("ã", "a").replace("á", "a")
             .replace("â", "a").replace("ç", "c"))
    return chave in _AUSENCIA_DE_MUNICIPIO


def _uf_crc(v: Any) -> str:
    """UF de 2 letras, ou vazio — nunca a palavra JS «undefined»."""
    if _e_ausencia_de_municipio(v):
        return ""
    s = _texto(v)
    return s.upper() if len(s) == 2 else s


def _digitos(v: Any) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


def _cpf(pessoa: dict) -> str:
    """O CPF de uma pessoa, só quando passa no dígito verificador.

    **RELATO DA CRC EM 11/09/2026: "CPFPAI é invalido" / "CPFMAE é invalido" /
    "O CPF da filiação invalido".** Medido na produção: `documento_numero`
    guarda `"004,944,233"` — uma vírgula de separador de milhar, do jeito que
    uma planilha formata um número, e não um CPF (`_digitos` some com a
    vírgula e sobram 9 dígitos, não 11). E há CPF de 11 dígitos que é apenas
    ERRADO — `64596923206` não bate no módulo 11 — que é dado ruim do
    acervo, não um problema de formatação.

    **NÃO SE ADIVINHA O DÍGITO QUE SE PERDEU.** Completar com zero à esquerda
    ou inventar o que sobra seria montar um CPF que não é de ninguém, num
    documento que vai à Central em nome da pessoa. A tag sai vazia — CPF não
    é obrigatório em nenhum bloco desta carga — e o que sobrar de errado no
    acervo continua sendo trabalho de conferência no balcão, e não do XML.
    """
    if _texto(pessoa.get("documento_tipo")).upper() != "CPF":
        return ""
    n = _digitos(pessoa.get("documento_numero"))
    return n if _cpf_valido(n) else ""


def _cidade_para_busca(cidade: Any) -> str:
    """O nome do município, sem a UF colada nem pontuação sobrando.

    **Medido em 11/09/2026: `naturalidade_cidade` guarda `"IMPERATRIZ/MA."`**
    — cidade, barra, UF e ponto final, tudo no mesmo campo —, e a busca por
    município nunca acha isso em `ib_municipios`, que guarda só o nome.
    Cortar depois da barra não inventa cidade nenhuma: é o mesmo texto, sem o
    que outro campo (`naturalidade_uf`) já diz.
    """
    s = _texto(cidade)
    s = s.split("/")[0]
    s = s.strip(" .")
    return "" if _e_ausencia_de_municipio(s) else s


def _codigo_ibge_municipio(con: sqlite3.Connection, cidade: Any,
                           uf: Any) -> str:
    """O código IBGE de 7 dígitos de um município. Vazio quando não achou.

    **"CODIGOIBGEMUNNASCIMENTO obrigatorio" — relato da CRC em 11/09/2026,**
    em dezenas de nascimentos. O campo sempre saiu vazio, com o comentário
    dizendo que esta casa "não tem coluna nesta casa" — e tinha: é a mesma
    busca que `ibge_geracao.lugar()` já faz para a remessa do IBGE, contra
    `ib_municipios` (5.570 municípios), a partir da naturalidade da própria
    pessoa (`naturalidade_cidade`/`naturalidade_uf`). Reaproveitada, e não
    reescrita — a lição da `normalizar_nome` copiada.
    """
    if _e_ausencia_de_municipio(_cidade_para_busca(cidade)):
        return ""
    achado = _lugar_ibge(con, _cidade_para_busca(cidade), _uf_crc(uf))
    return achado["codigo_ibge"] if achado.get("achou") else ""


def _texto_livre_municipio_nat(pessoa: dict) -> str:
    """O `TEXTOLIVREMUNICIPIONAT` de óbito/casamento: `CIDADE/UF`, ou vazio.

    **Não inventa município.** «não consta» e «undefined» saem vazios aqui;
    quem precisa de um sentinela não-nulo (a filiação, que a CRC recusa com
    os dois campos nulos) preenche depois.
    """
    cidade = _cidade_para_busca(pessoa.get("naturalidade_cidade"))
    if not cidade:
        return ""
    uf = _uf_crc(pessoa.get("naturalidade_uf"))
    return f"{cidade}/{uf}" if uf else cidade


# **O XSD LIMITA CADA LINHA DA CAUSA DA MORTE A 170 CARACTERES** — achado
# em 13/09/2026 rodando o XSD contra o lote real do `.docx` (o teste que o
# oficial pediu, "além do XSD"): `CAUSAMORTEANTECEDENTES_A` recebia a
# prosa inteira da certidão, sem quebra nenhuma, e 17 óbitos do lote real
# excedem os 170 — o maior tem 375. Até aqui `causa_morte` sempre estava
# vazia em produção (comentário abaixo, de antes desta correção), e por
# isso o defeito nunca tinha aparecido.
CAUSA_MORTE_MAXLEN = 170


def _causa_morte_em_quatro_linhas(causa_morte: Any) -> tuple[str, str, str,
                                                             str, bool]:
    """A causa da morte partida nas quatro linhas do manual (`_A` a `_D`),
    sem cortar palavra ao meio. Devolve as quatro partes e se ainda sobrou
    texto depois delas.

    **ENCHER AS QUATRO EM VEZ DE TRUNCAR SÓ A PRIMEIRA** — o manual já prevê
    quatro linhas para a cadeia de causas (a mesma forma da Declaração de
    Óbito, com causa imediata e antecedentes); usá-las é aproveitar o espaço
    que a Central aceita, e não perder na primeira linha o que caberia na
    segunda.
    """
    resto = _texto(causa_morte)
    partes: list[str] = []
    for _ in range(4):
        if not resto:
            partes.append("")
            continue
        if len(resto) <= CAUSA_MORTE_MAXLEN:
            partes.append(resto)
            resto = ""
            continue
        corte = resto.rfind(" ", 0, CAUSA_MORTE_MAXLEN + 1)
        if corte <= 0:
            corte = CAUSA_MORTE_MAXLEN
        partes.append(resto[:corte].strip())
        resto = resto[corte:].strip()
    a, b, c, d = partes
    return a, b, c, d, bool(resto)



# **O XSD LIMITA O CRM DO ATESTANTE A 13 CARACTERES** - achado em 30/09/2026
# validando a selecao do dia (33 assentos / 27 no XML) contra
# `schemas/cargaRegistrosCompleto.xsd`: `CRMATESTANTEPRIMARIO` recebia a
# prosa livre de `atestante_documento` (ex. "CRM-MA 4603 (IML Imperatriz)",
# 28 chars; "CRM-MA 11290 (assistente)", 25) e o facet `maxLength=13`
# derrubava o arquivo inteiro. O nome do medico ja vai em
# `NOMEATESTANTEPRIMARIO` (max 100); o CRM e so o identificador curto.
CRM_ATESTANTE_MAXLEN = 13


def _crm_atestante(v: Any) -> str:
    """O CRM do atestante cabendo no `maxLength=13` do XSD.

    Esta casa grava em `atestante_documento` texto livre com anotacao entre
    parenteses (local/funcao). Tira o que esta entre `()`, comprime espacos,
    e se ainda passar do limite corta - o excesso nao e o numero do CRM, e a
    anotacao que o balcao acrescentou ao lado.
    """
    s = _texto(v)
    if not s:
        return ""
    while True:
        a = s.find("(")
        b = s.find(")", a + 1) if a >= 0 else -1
        if a < 0 or b < 0:
            break
        s = (s[:a] + " " + s[b + 1:]).strip()
    s = " ".join(s.split())
    if len(s) > CRM_ATESTANTE_MAXLEN:
        s = s[:CRM_ATESTANTE_MAXLEN].rstrip()
    return s


def _ibge_carregado(con: sqlite3.Connection) -> bool:
    """Se `ib_municipios` tem alguma linha — só a carga do acervo a popula.

    **DECIDE ENTRE RETER E AVISAR.** Sem esta tabela, "não achou o município"
    não distingue naturalidade mal grafada de infraestrutura que nunca
    carregou — e reter por uma tabela vazia travaria todo nascimento numa
    instalação nova, mesmo com a naturalidade certa na ficha. Só quando a
    tabela existe de verdade é que "não achou" vira sinal de grafia errada,
    e passa a reter.
    """
    return con.execute("SELECT 1 FROM ib_municipios LIMIT 1").fetchone() is not None



# **A HORA VAI EM HH:MM, SEMPRE COM DOIS DIGITOS NA HORA** - achado em
# 30/09/2026 na carga CRC do obito de TOMAS MACEDO CORREIRO: a ficha
# gravou `hora_fato=2:18` e o gerador mandava cru em `HORAOBITO`. O XSD
# so limita `maxLength=5` (cabe `2:18`), mas a Central recusa com
# "HORAOBITO invalida" - o formato de negocio e HH:MM (`02:18`). O mesmo
# campo alimenta `HORANASCIMENTO`. Nao se inventa hora: o que nao se
# reconhece sai vazio.
def _hora(v: Any) -> str:
    """Normaliza `hora_fato` para HH:MM (5 chars), ou vazio se invalido.

    Aceita `H:MM`, `HH:MM`, `HH:MM:SS` e grafias com `h` (`14h30`). Hora
    fora de 0..23 ou minuto fora de 0..59 devolve vazio - melhor tag
    vazia do que inventar (ex. `19:68`, `24:00` do acervo).
    """
    s = _texto(v).strip()
    if not s:
        return ""
    s = s.replace(".", ":").replace("H", ":").replace("h", ":")
    partes = [p for p in s.replace(" ", ":").split(":") if p != ""]
    if len(partes) < 2:
        return ""
    try:
        hh = int(partes[0])
        mm = int(partes[1])
    except ValueError:
        return ""
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        return ""
    return f"{hh:02d}:{mm:02d}"


def _data(v: Any) -> str:
    """`AAAA-MM-DD` vira `DD/MM/AAAA`, que e o formato do manual.

    DEVOLVE VAZIO PARA O QUE NAO RECONHECE, em vez de tentar adivinhar: data
    mal formada num arquivo que a Central valida derruba o registro inteiro, e
    a mensagem de recusa nao diz qual campo era.
    """
    s = _texto(v)
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    return ""


def _tag(nome: str, valor: Any = "") -> str:
    """Uma tag, com o texto escapado.

    O ESCAPE E O DO XML, E NAO O DO MANUAL. A tabela de caracteres especiais do
    manual, como ela sai do PDF, esta **invertida** — diz que `>` vira `&lt;` e
    `<` vira `&gt;`. Copiar o erro produziria arquivo bem formado com o texto
    trocado, que e o pior dos dois mundos.
    """
    return f"<{nome}>{escape(_texto(valor))}</{nome}>"


# O RÓTULO DE CADA GENITOR, na convenção que o oficial escolheu em 30/08/2026
# — «filiação 1 e 2, indicando a 1 para mãe entre parênteses». As chaves
# gravadas continuam `PAI`/`MAE`, que são as do acervo.
ROTULO_DO_GENITOR: dict[str, str] = {
    "MAE": "filiação 1 (mãe)",
    "PAI": "filiação 2 (pai)",
}


def o_que_arrumar(con: sqlite3.Connection, assento: dict,
                  pessoas: dict) -> list[str]:
    """O que impede a filiação de subir — **relato do oficial em 10/09/2026**.

        «preciso que resolva o problema do json das certidoes da crc, estao
         saindo sem preencher os pais»

    **O DEFEITO ERA O SILÊNCIO, e não a montagem.** `_filiacao` exige nome
    **e** sexo — é a regra da CRC, e ela está certa: «no mínimo o nome e o sexo
    devem ser preenchidos». O que estava errado é que, faltando o sexo, ela
    devolvia string vazia e **o bloco inteiro se perdia sem ninguém saber** —
    com o nome do genitor gravado no sistema.

    Medido na produção em 10/09/2026, nos 210 nascimentos:

    | | |
    |---|---|
    | filiações esperadas | **420** (210 × 2) |
    | subiam | **396** |
    | **não subiam** | **24**, caladas |

    E as 24 são **duas coisas diferentes**, que pedem providências diferentes:

      · **14 sem a pessoa** — a carga do acervo não trouxe a mãe. Não há o que
        mandar; o nome está no livro de papel;
      · **10 com nome e sem sexo** — e aqui **o nome está no sistema e não
        sobe**. É esta a que a lista resolve.

    **Uma delas não é falta: é declaração.** No assento 70 o pai **chama-se
    «IGNORADO»** — é como o acervo escreve «pai não declarado». Cobrar o sexo
    dele mandaria o balcão procurar na estante o que o livro diz que não existe,
    e por isso ele sai da lista pela palavra, e não pelo campo vazio. A régua é
    `rc_assento.e_declarado_ausente`, a mesma que a lavratura usa.

    **E ISTO AVISA, E NÃO TRAVA — correção minha, no mesmo dia, e quem me
    corrigiu foram os testes que já existiam.** A primeira versão punha a
    filiação entre as `faltas`, que retêm o registro. **O manual não põe a
    filiação entre os obrigatórios do nascimento** — são `NOMEREGISTRADO`,
    `MATRICULA`, `DATAREGISTRO` e `SEXO`, e só. Bloquear seria mais severo que
    a norma, e deixaria **20 registros válidos** sem nunca chegar à Central por
    causa de um campo que ela não exige.

    E o pedido do oficial era justamente avisar: «precisa avisar quais
    informações precisam ser arrumadas para adequar a crc json». **Avisar é o
    que ele pediu; travar é o que eu quase fiz.**

    São duas listas, e a diferença é a consequência:

      · `o_que_falta` — **retém** o registro. É o obrigatório do manual;
      · `o_que_arrumar` — **o registro vai**, e a tela diz o que consertar.

    **E O SEXO NÃO SE PREENCHE SOZINHO — decisão do oficial em 10/09/2026:**

        «deixa sexo em aberto para quem estiver lavrando arrume»

    A CRC aceita «ignorado», e eu perguntei se a tela devia oferecer marcá-lo
    para o nome subir. **Ele disse que não.** O campo fica em aberto e quem
    lavra arruma — e a diferença não é de comodidade: «ignorado» é uma
    **declaração** de que ninguém sabe, e quem pode fazê-la é quem tem o livro
    na mão, não um programa que quer completar o arquivo.

    Por isso este módulo **não tem, e não deve ganhar**, um caminho que
    escreva sexo em `rc_pessoas`. Ele mede e avisa; quem corrige é
    `/rcpn/<id>/editar`, com motivo e auditoria.
    """
    from rc_assento import e_declarado_ausente

    especie = _texto(assento.get("especie")).upper()

    # ---------------------------------------------------------- o ÓBITO
    #
    # **O ESTADO CIVIL DO FALECIDO É CAMPO LIVRE, e dois têm coisa que não é
    # estado civil.** Medido em 10/09/2026: dos 31 falecidos, 15 «Solteiro»,
    # 13 «Casado», 3 «Viúvo/Viuvo» — e o campo tem doze grafias em
    # `rc_pessoas`, entre elas «falecido» e «falecida». A tag não sai, e
    # ninguém sabia.
    #
    # A CRC não o põe entre os obrigatórios do óbito (`FLAGDESCONHECIDO`,
    # `NOMEFALECIDO`, `MATRICULA`, `DATAREGISTRO`, `SEXO`, `CORPELE`), logo
    # isto **avisa** — a mesma decisão da filiação, tomada horas antes.
    if especie == "OBITO":
        avisos: list[str] = []
        fal = pessoas.get("FALECIDO") or {}
        civil = _texto(fal.get("estado_civil"))
        if civil and not ESTADO_CIVIL.get(_chave(civil)):
            avisos.append(
                f"o estado civil do falecido está gravado como «{civil}», "
                "que não é um estado civil — a CRC aceita solteiro, casado, "
                "viúvo, divorciado, separado, outros e ignorado. Sem ele o "
                "registro sobe, e a Central não recebe essa informação")
        # **A NATURALIDADE DO FALECIDO ESTAVA MEDIDA E NÃO CONFERIDA —
        # 13/09/2026, pedido do oficial.** O nascimento tem esta mesma
        # checagem em `o_que_falta` (RETÉM), porque a CRC recusou de verdade
        # quando ela faltava (relato de 11/09/2026). **Para o óbito não há
        # relato assim**, e o manual não põe naturalidade entre os
        # obrigatórios (`FLAGDESCONHECIDO`, `NOMEFALECIDO`, `MATRICULA`,
        # `DATAREGISTRO`, `SEXO`, `CORPELE`) — só o estado civil, acima, está
        # nessa mesma situação. **Bloquear seria mais severo que a norma**, e
        # por isso ela AVISA aqui, e não retém. Se a Central um dia recusar
        # por falta dela, a checagem sobe para `o_que_falta`, como
        # `POSSUIBENS` subiu.
        #
        # Medido em 13/09/2026, nos 309 óbitos do acervo local: **8 sem
        # naturalidade na ficha** e **4 com a naturalidade lida e a grafia
        # fora do cadastro do IBGE** desta casa.
        if _ibge_carregado(con):
            cidade_obito = _texto(fal.get("naturalidade_cidade"))
            if not cidade_obito:
                avisos.append(
                    "a naturalidade do falecido não está na ficha — a CRC "
                    "recebe o código do município "
                    "(CODIGOIBGEMUNNATURALIDADE), e sem ele a tag sai "
                    "vazia. O registro sobe assim mesmo")
            elif not _codigo_ibge_municipio(
                    con, cidade_obito, fal.get("naturalidade_uf")):
                avisos.append(
                    f"a naturalidade do falecido «{cidade_obito}» não foi "
                    "encontrada no cadastro do IBGE desta casa — confira a "
                    "grafia na ficha. O registro sobe, e a tag do município "
                    "sai vazia")
        # **A CAUSA DA MORTE SÓ TEM QUATRO LINHAS DE 170 CARACTERES** — achado
        # em 13/09/2026 pelo XSD, e não pela releitura. Quando a prosa da
        # certidão não cabe nem nas quatro, o excesso é cortado para o XML
        # não estourar o limite — e é isso que se avisa aqui, para alguém
        # decidir se resume o texto no papel antes de mandar à Central.
        _a, _b, _c, _d, sobrou_causa = _causa_morte_em_quatro_linhas(
            assento.get("causa_morte"))
        if sobrou_causa:
            avisos.append(
                "a causa da morte é mais longa do que as quatro linhas que "
                "a CRC aceita (170 caracteres cada) — o texto foi cortado "
                "para caber, e uma parte não sobe. Resuma o texto na ficha "
                "se quiser que ele suba inteiro")
        # **"POSSUIBENS" passou a `o_que_falta` em 11/09/2026** — a CRC
        # recusa o registro **sempre** que ele sobe sem essa resposta (o
        # relato voltou idêntico depois de mandar mesmo assim), e mandar de
        # novo só repete a viagem para o mesmo "não". Reter é a resposta
        # honesta: nenhum caminho fazia esse envio ter sucesso.
        return avisos

    # ------------------------------------------------------ o CASAMENTO
    #
    # **O REGIME DE BENS É OBRIGATÓRIO DA CERTIDÃO** (Lei 6.015/1973, art. 70,
    # item 6) e está **vazio em 20 dos 22** casamentos — os 20 do acervo. Ele
    # não retém o registro na CRC, e é informação que a Central quer e a
    # certidão precisa.
    if especie in ("CASAMENTO", "CASAMENTO_RELIGIOSO"):
        avisos = []
        regime = _texto(assento.get("regime_bens"))
        if not regime:
            avisos.append(
                "o regime de bens não está no assento — ele é campo "
                "obrigatório da certidão de casamento (art. 70, item 6, da "
                "Lei 6.015/1973), e a CRC o recebe. O registro sobe sem ele; "
                "o regime está no livro de papel")
        elif not _regime_resolvido(regime, assento.get("data_fato")):
            avisos.append(
                f"o regime de bens está gravado como «{regime}», que não "
                "casa com nenhum dos sete que a CRC aceita — comunhão "
                "parcial, comunhão universal, participação final nos "
                "aquestos, separação de bens, separação legal de bens, "
                "outros e ignorado")
        return avisos

    if especie not in ("NASCIMENTO", "NATIMORTO"):
        return []

    # **PAI AUSENTE NÃO É IRREGULARIDADE — decisão do oficial em 13/09/2026:
    # "não é irregularidade não ter pai, é comum. Mãe todos devem ter."**
    # Paternidade não reconhecida é comum nesta casa (e na vida), e avisar
    # sobre isso em cada assento sem pai produziria um aviso que ninguém
    # nunca resolve, porque não há o que resolver — é o alarme que soa
    # sempre, e que ninguém mais ouve. A mãe continua obrigatória: **todo**
    # nascimento tem mãe, e a falta dela é falha da carga, não do mundo.
    ROTULOS_QUE_AVISAM_SE_FALTAM = ("MAE",)

    faltas: list[str] = []
    for papel in ("MAE", "PAI"):
        quem = pessoas.get(papel) or {}
        nome = _texto(quem.get("nome"))
        rotulo = ROTULO_DO_GENITOR[papel]
        if not nome:
            if papel in ROTULOS_QUE_AVISAM_SE_FALTAM:
                faltas.append(
                    f"a {rotulo} não está no sistema — a carga do acervo não "
                    "a trouxe. O registro sobe sem ela; o nome está no livro "
                    "de papel")
            continue
        if e_declarado_ausente(nome):
            # «IGNORADO» é declaração, e não campo em branco: a filiação não
            # sobe, e isso está certo. Não se cobra o sexo de quem o livro diz
            # que não foi declarado.
            continue
        if not SEXO.get(_texto(quem.get("sexo")).upper()):
            faltas.append(
                f"o sexo da {rotulo} («{nome}») — **sem ele esta filiação não "
                "sobe**, e o nome já está no sistema. A CRC aceita masculino, "
                "feminino e ignorado")

    return faltas


def o_que_falta(con: sqlite3.Connection, assento: dict,
                pessoas: dict) -> list[str]:
    """O que impede este assento de ir para a CRC. Só calcula.

    **A LISTA VEM ANTES DO ARQUIVO.** A Central valida e recusa depois — e a
    recusa chega dias depois, sem ninguém por perto. Conferir aqui transforma
    isso em recusa no balcão, que é o que este projeto já faz com a participação
    das partes na DOI.
    """
    faltas: list[str] = []
    especie = _texto(assento.get("especie")).upper()

    matricula = _digitos(assento.get("matricula"))
    if len(matricula) != 32:
        faltas.append(
            # **ESTE TEXTO DIZIA QUE A MATRÍCULA NÃO SE GERA, E ELA SE
            # GERA DESDE 03/09/2026** — `rc_matricula.py`, pelo Anexo IV do
            # manual da própria CRC, e acerta **255 de 255**. O que ele dizia
            # era verdade quando foi escrito, e deixou de ser: carimbo que
            # mente manda o balcão procurar quem informe o que o sistema
            # calcula.
            "a matrícula de 32 dígitos, que é obrigatória na CRC — e ela **se "
            "calcula** pelo Anexo IV do manual (`rc_matricula`): a ficha do "
            "assento mostra a calculada, com um botão para gravá-la")
    else:
        # **"MATRICULA ja existe na nossa base" NÃO ENTRA AQUI** — é a CRC
        # dizendo que aquele registro já chegou lá antes (provavelmente
        # pelo E-Ofício, que integrava com a Central), e não um defeito
        # desta carga: mandar de novo é o esperado ao subir o acervo
        # histórico, e a Central decide o que fazer com a duplicata.
        #
        # **"A MATRICULA é invalida" e "O ano do registro (...) deve ser o
        # mesmo ano da data do registro" — relatos da CRC em 11/09/2026,**
        # e os dois são o mesmo defeito por dois lados: o dígito
        # verificador ou o ano dentro da matrícula não batem com o que o
        # Anexo IV exige. `rc_matricula.confere` já sabe calcular os dois —
        # é a mesma conta que valida a matrícula nova; aqui ela audita a
        # que já está gravada.
        conferida = _RCM.confere(matricula)
        if not conferida["ok"]:
            faltas.append(
                f"a matrícula está com o dígito verificador errado — devia "
                f"ser **{conferida['esperado']}** e está "
                f"**{conferida['achado']}**. A ficha do assento recalcula e "
                f"grava o certo")
        else:
            ano_ato = _texto(assento.get("data_ato"))[:4]
            ano_matricula = conferida["partes"].get("ano", "")
            if ano_ato and ano_matricula and ano_ato != ano_matricula:
                faltas.append(
                    f"o ano dentro da matrícula é **{ano_matricula}**, e a "
                    f"data do registro é de **{ano_ato}** — a CRC exige que "
                    "os dois sejam o mesmo ano. A matrícula foi gravada com "
                    "o ano errado; recalcule e grave a certa na ficha do "
                    "assento")

    if not _data(assento.get("data_ato")):
        faltas.append("a data do registro")

    # **"DATANASCIMENTO não pode ser maior que a data do registro" —
    # relato da CRC em 11/09/2026, em vários nascimentos do acervo.**
    # Nascer depois de ser registrado é impossível; é dado corrompido na
    # importação, e não algo que este módulo deveria calar mandando assim
    # mesmo — a CRC recusaria o registro inteiro por um campo que ninguém
    # olhou antes de mandar.
    if especie in ("NASCIMENTO", "NATIMORTO", "CASAMENTO", "CASAMENTO_RELIGIOSO"):
        fato = _data(assento.get("data_fato"))
        ato = _data(assento.get("data_ato"))
        if fato and ato:
            data_fato_iso = f"{fato[6:10]}-{fato[3:5]}-{fato[0:2]}"
            data_ato_iso = f"{ato[6:10]}-{ato[3:5]}-{ato[0:2]}"
            if data_fato_iso > data_ato_iso:
                rotulo = ("do nascimento" if especie in
                          ("NASCIMENTO", "NATIMORTO") else "da celebração")
                faltas.append(
                    f"a data {rotulo} ({fato}) é depois da data do registro "
                    f"({ato}) — isso não é possível, e é sinal de que uma "
                    "das duas datas está errada no assento. Confira contra "
                    "o livro de papel antes de mandar")

    if especie in ("NASCIMENTO", "NATIMORTO"):
        if not _texto(assento.get("nome")):
            faltas.append("o nome do registrado")
        if not SEXO.get(_texto(
                pessoas.get("REGISTRADO", {}).get("sexo")).upper()):
            faltas.append("o sexo do registrado")
        # **"CODIGOIBGEMUNNASCIMENTO obrigatorio" — relato da CRC em
        # 11/09/2026, e volta a apontar depois de a maioria já resolver
        # sozinha (a busca por município ficou boa em 11/09).** O que sobra
        # agora é sempre grafia — "Governador Edson Lobão" contra "Edison
        # Lobão" no cadastro — e mandar de novo não muda o resultado.
        #
        # **SÓ RETÉM QUANDO `ib_municipios` TEM DADO**, porque ela só se
        # popula pela carga do acervo: sem ela, "não achou" seria a tabela
        # vazia, e não a grafia — e reter travaria todo nascimento numa
        # instalação sem carga nenhuma, mesmo com a naturalidade certa.
        if _ibge_carregado(con):
            registrado = pessoas.get("REGISTRADO") or {}
            cidade_nasc = _texto(registrado.get("naturalidade_cidade"))
            if not cidade_nasc:
                faltas.append(
                    "o município de nascimento do registrado não está na "
                    "ficha — a CRC exige o código do município (obrigatório "
                    "desde 13/10/2015), e a Central recusa o registro sem "
                    "ele")
            elif not _codigo_ibge_municipio(
                    con, cidade_nasc, registrado.get("naturalidade_uf")):
                faltas.append(
                    f"o município de nascimento «{cidade_nasc}» não foi "
                    "encontrado no cadastro do IBGE desta casa — confira a "
                    "grafia na ficha do registrado. Sem achar, a Central "
                    "recusa o registro")
    elif especie in ("CASAMENTO", "CASAMENTO_RELIGIOSO"):
        for papel, rotulo in (("NUBENTE1", "primeiro"), ("NUBENTE2", "segundo")):
            if not _texto(pessoas.get(papel, {}).get("nome")):
                faltas.append(f"o nome do {rotulo} cônjuge")
        if not _data(assento.get("data_fato")):
            faltas.append("a data da celebração do casamento")
    elif especie == "OBITO":
        if not _texto(pessoas.get("FALECIDO", {}).get("nome")
                      or assento.get("nome")):
            faltas.append("o nome do falecido")
        cor = _texto(assento.get("cor_raca")).upper()
        if cor and cor not in COR_PELE:
            faltas.append(
                f"a cor «{assento.get('cor_raca')}» não está entre as que a "
                "CRC aceita (branca, preta, parda, amarela, indígena, "
                "ignorada)")
        # **"O campo POSSUIBENS deve ser preenchido com S OU N" — relato da
        # CRC em 11/09/2026, repetido depois de subir mesmo assim.** Primeira
        # versão só avisava, porque o manual não o põe entre os obrigatórios
        # do óbito — e a Central recusa o registro **sempre** que falta,
        # sem exceção observada. Mandar de novo sem resposta só repete a
        # mesma viagem para o mesmo "não"; reter é a resposta honesta.
        if not MARCA_SIM_NAO.get(_chave(assento.get("obito_possui_bens"))):
            faltas.append(
                "se o falecido possuía bens — a CRC exige S ou N nesse "
                "campo, sem opção de ignorado, e a ficha não tem essa "
                "resposta. Sem ela a Central recusa o registro inteiro")
        # **A RETENÇÃO DO ÓBITO VIOLENTO SAIU — 10/09/2026.** Aqui os 4 óbitos
        # violentos desta casa eram retidos, porque estava escrito que «a CRC
        # só enumera Natural ou Acidental». **O XSD enumera `VIOLENTA`**, com
        # essa palavra; a frase do «Natural ou Acidental» é de uma página de
        # recomendações do manual, e prosa de recomendação não é schema.

    return faltas


# ------------------------------------------------------------- a montagem


def _possui_gemeos(assento: dict) -> str:
    """`S`, `N`, ou vazio quando ninguém respondeu.

    **O CÓDIGO 1 DO IBGE QUER DIZER «NÃO É GÊMEO», E ISSO CUSTOU 210
    REGISTROS.** Aqui havia `if assento.get("ibge_gemeo"): "S"` — e um é
    verdadeiro em Python. Medido na produção: **210 dos 212** nascimentos têm
    o código 1, e **todos** subiam afirmando `POSSUIGEMEOS S`, sem que um
    único tenha irmão gêmeo.

    Achado porque o oficial mandou verificar um registro — o do Nilton, cujo
    teor diz «O registrado não é gêmeo» —, e não pela releitura.

    **A INVARIANTE MAIS FORTE VEM PRIMEIRO.** `gemeo_irmao_id` e `gemeo_ordem`
    são o art. 234 do Código de Normas: eles dizem que ESTE assento está
    amarrado ao do irmão, e isso vale mais que um código de remessa
    estatística — que é para o que `ibge_gemeo` existe. Foi a distinção
    registrada em 30/08/2026, quando as duas colunas nasceram: «`ibge_gemeo`
    diz se é gêmeo; o art. 234 exige qual é a ordem».

    **E O «IGNORADO» NÃO VIRA NEM `S` NEM `N`.** O XSD só tem os dois, e
    escolher um afirmaria à Central o que ninguém apurou. A tag não sai — o
    manual não a põe entre as obrigatórias.
    """
    if assento.get("gemeo_irmao_id") or assento.get("gemeo_ordem"):
        return "S"
    codigo = _texto(assento.get("ibge_gemeo"))
    if codigo in ("2", "3"):
        return "S"
    if codigo == "1":
        return "N"
    return ""


def _quantos_gemeos(assento: dict) -> str:
    """Quantos IRMÃOS gêmeos — e não quantos nasceram.

    «Total de irmãos gêmeos do registrado. **Se nasceram tri-gêmeos = 2**» —
    o manual, na letra. Logo o gêmeo simples é `1`.

    **E O CÓDIGO 3 DO IBGE NÃO DÁ O NÚMERO**: ele é «trigêmeo **ou mais**».
    Escrever 2 ali seria inventar um número num arquivo que vai à Central —
    e o XSD aceita a tag vazia. Fica de fora, e quem souber o número o informa
    pela ordem dos gêmeos do art. 234.
    """
    if _texto(assento.get("ibge_gemeo")) == "2":
        return "1"
    return ""


def _pessoas_do_assento(con: sqlite3.Connection,
                        assento_id: int) -> dict[str, dict]:
    con.row_factory = sqlite3.Row
    achadas: dict[str, dict] = {}
    for r in con.execute(
            """SELECT * FROM rc_pessoas WHERE assento_id = ?
                ORDER BY ordem, id""", (assento_id,)):
        achadas.setdefault(_texto(r["papel"]).upper(), dict(r))
    return achadas


# **O DOCUMENTOS É SÓ PARA "O OUTRO DOCUMENTO", NUNCA PARA O CPF** — o manual
# diz «a preferência de envio é sempre pelo CPF; somente deverá ser enviado
# outro documento se não existir o CPF», e o XSD confirma: `TIPO_DOC` **não
# tem `CPF` na enumeração** (`RG, NIT, RIC, RNE, TITULO_DE_ELEITOR,
# PASSAPORTE, CNH, CTPS, CARTEIRA_DE_MARITIMO, DOC_ESTRANGEIRO,
# CERT_DE_NASCIMENTO, CERT_DE_RESERVISTA, NAO_IDENTIFICADO`). O CPF vai pela
# tag própria (`CPFREGISTRADO`, `CPFCONJUGE{n}`, `CPFFALECIDO`, ou `CPF`
# dentro de `FILIACAONASCIMENTO`) — mandar `<TIPO_DOC>CPF</TIPO_DOC>` aqui
# seria um valor fora da enumeração, e derrubaria o registro.
TIPO_DOC = {"RG": "RG"}


def _documentos(pessoa: dict, dono: str, indice: int,
                indice_filiacao: int | None = None) -> str:
    """O bloco `<DOCUMENTOS>` de uma pessoa — só quando NÃO é CPF.

    **`INDICEFILIACAO` SÓ EXISTE NO NASCIMENTO** — medido nos seis exemplos do
    manual e confirmado no XSD: o bloco de casamento e o de óbito não têm essa
    tag. `indice_filiacao=None` a omite; um número a inclui, para o
    documento do genitor (dono=FILIACAO_NASCIMENTO).
    """
    tipo = TIPO_DOC.get(_texto(pessoa.get("documento_tipo")).upper())
    numero = _texto(pessoa.get("documento_numero"))
    if not numero or not tipo:
        return ""
    partes = [_tag("INDICEREGISTRO", indice)]
    if indice_filiacao is not None:
        partes.append(_tag("INDICEFILIACAO", indice_filiacao))
    partes.extend([_tag("DONO", dono), _tag("TIPO_DOC", tipo),
                   _tag("NUMERO", numero)])
    # **`CODIGOORGAOEMISSOR` É CÓDIGO, E NÃO O NOME DO ÓRGÃO — achado em
    # 22/09/2026, quando a carga passou a levar os 45 registros.** O XSD o
    # limita a **2 caracteres**, e esta casa guarda `documento_orgao` como
    # «SSP/MA» (6) e «RFB» (3): a Central recusava o arquivo inteiro dizendo
    # «has a length of 6; this exceeds the allowed maximum length of 2».
    #
    # **NÃO SE MANDA MAIS NADA AQUI, e não é omissão: é o que se sabe.** O XSD
    # não enumera os valores e esta casa não tem a tabela de códigos de órgão
    # da CRC — inventar um código de duas letras a partir de «SSP/MA» seria
    # afirmar à Central um órgão que ninguém conferiu, e a tag é
    # `minOccurs="0"`. Quando a tabela aparecer, o de-para entra aqui.
    #
    # **O DEFEITO SÓ APARECEU AGORA porque os dois RG desta casa estavam
    # retidos por outro motivo** (a naturalidade que faltava na pessoa): eles
    # nunca tinham chegado ao XSD. Conserto que destrava dado destrava também
    # o defeito seguinte.
    if pessoa.get("uf"):
        partes.append(_tag("UF_EMISSAO", pessoa["uf"]))
    return "<DOCUMENTOS>" + "".join(partes) + "</DOCUMENTOS>"


def _filiacao(con: sqlite3.Connection, pessoa: dict, indice: int,
             ordem: int) -> str:
    """O bloco `<FILIACAONASCIMENTO>` de um genitor.

    «Quando os dados de qualquer filiação não forem ignorados, as informações
    inseridas devem estar coerentes: **no mínimo o nome e o sexo** devem ser
    preenchidos.» — é a regra do SIRC, e a CRC pede os mesmos dois.

    **É a mesma invariante que este projeto descobriu sozinho**, medindo o
    acervo: os 42 assentos com a mãe no lugar do pai apareceram porque um
    assento tem um pai e uma mãe, e o par decide. Sem nome e sexo, a filiação
    não identifica ninguém.
    """
    nome = _texto(pessoa.get("nome"))
    sexo = SEXO.get(_texto(pessoa.get("sexo")).upper(), "")
    if not nome or not sexo:
        return ""
    # **CPF E DATANASCIMENTO SÃO OBRIGATÓRIOS AQUI, MESMO SEM DADO** — o XSD
    # não os marca `minOccurs="0"` como marca SEXO logo acima; a tag tem de
    # existir na sequência, vazia se não houver o quê. Emitir só quando há
    # CPF (como antes) derrubaria por «elemento não esperado» todo genitor
    # sem CPF cadastrado — que é a maioria, medido no acervo.
    partes = [_tag("INDICEREGISTRO", indice), _tag("INDICEFILIACAO", ordem),
              _tag("NOME", nome), _tag("SEXO", sexo),
              _tag("CPF", _cpf(pessoa)),
              _tag("DATANASCIMENTO", _data(pessoa.get("data_nascimento")))]
    if pessoa.get("idade_no_fato"):
        # **A ENUMERAÇÃO É A LETRA, E NÃO A PALAVRA** — `'', 'D', 'M', 'A'`.
        # Isto dizia `"ANOS"`, que não está no XSD e derrubaria o registro
        # inteiro por causa de um genitor com idade informada. Só se guarda
        # a idade em ANOS nesta casa; por isso a letra é sempre `A`.
        partes.append(_tag("IDADE", pessoa["idade_no_fato"]))
        partes.append(_tag("IDADE_DIAS_MESES_ANOS", "A"))
    for coluna, tag in (("endereco", "LOGRADOURO"), ("bairro", "BAIRRO")):
        if pessoa.get(coluna):
            partes.append(_tag(tag, pessoa[coluna]))
    # **"O CODIGOIBGEMUNNATURALIDADE filiação não pode ser nulo e se o
    # campo TEXTOLIVREMUNICIPIONAT também for nulo" — relato da CRC em
    # 11/09/2026.** O XSD marca os dois `minOccurs="0"`, mas a Central exige
    # que ao menos um saia preenchido. O código vem da mesma busca de
    # `_codigo_ibge_municipio`; o texto livre é o que já se monta para o
    # óbito — cidade mais UF.
    #
    # **E SEM CIDADE TAMBÉM NÃO SE OMITEM OS DOIS** — medido em Edimar de
    # Sousa Pimentel / Hilda da Silva Lima (assento 1239): os dois
    # genitores têm `naturalidade_cidade`/`uf` nulos, a carga não emitia
    # tag nenhuma, e a CRC mostrava «Município: undefined / UF: undefined»,
    # a interpolação JS do campo ausente. Óbito e casamento já emitem a
    # tag mesmo vazia. A filiação precisa de conteúdo (a Central recusa
    # os dois nulos); «não consta» é texto livre, cabe no `maxLength` 100,
    # e não finge código IBGE.
    codigo = _codigo_ibge_municipio(con, pessoa.get("naturalidade_cidade"),
                                    pessoa.get("naturalidade_uf"))
    if codigo:
        partes.append(_tag("CODIGOIBGEMUNNATURALIDADE", codigo))
    else:
        texto_livre = (_texto_livre_municipio_nat(pessoa) or "não consta")
        partes.append(_tag("TEXTOLIVREMUNICIPIONAT", texto_livre))
    return "<FILIACAONASCIMENTO>" + "".join(partes) + "</FILIACAONASCIMENTO>"


def registro_de_nascimento(con: sqlite3.Connection, assento: dict,
                           pessoas: dict, indice: int) -> str:
    """O bloco de inclusão de um nascimento. Só calcula.

    **A ORDEM É A DO XSD, E NÃO A DE QUEM ESCREVEU O CÓDIGO — 10/09/2026.**
    Até esta correção, `CPFREGISTRADO` só entrava quando havia CPF, e o
    XSD o exige **na sequência, sempre presente** (`minOccurs` não
    declarado é `1`, e não `0`): sem ele, a Central recusa o registro
    inteiro dizendo que `MATRICULA` «não era esperado ali» — porque, do
    ponto de vista da validação estrutural, faltou o elemento anterior.
    Confirmado validando contra o próprio XSD desta casa: **todo assento
    sem CPF do registrado quebrava**, e é a maioria do acervo.

    **`CODIGOIBGEMUNNASCIMENTO` deixou de ser «sem coluna nesta casa» em
    11/09/2026** — era a naturalidade do próprio REGISTRADO, achada pela
    mesma busca que a remessa do IBGE já faz. Os campos que continuam
    mesmo sem coluna (`PAISNASCIMENTO`, `NACIONALIDADE`,
    `TEXTONACIONALIDADEESTRANGEIRO`) saem vazios — a tag existe, o conteúdo
    não se inventa. É o que o próprio manual descreve para tag em branco:
    vira nulo/ignorado do lado da Central.
    """
    reg = pessoas.get("REGISTRADO", {})
    partes = [
        _tag("INDICEREGISTRO", indice),
        _tag("NOMEREGISTRADO", assento.get("nome")),
        _tag("CPFREGISTRADO", _cpf(reg)),
        _tag("MATRICULA", _digitos(assento.get("matricula"))),
        _tag("DATAREGISTRO", _data(assento.get("data_ato"))),
        # **A DNV TEM 11 DÍGITOS, SEMPRE** — "Número da DNV inválido" na CRC,
        # relato de 11/09/2026, em registros cuja `dnv` tem só **10**
        # dígitos. É a mesma família do CPF com vírgula de milhar: um zero à
        # esquerda que se perdeu na importação. **Não se repõe o zero
        # adivinhando** — a tag sai vazia quando a contagem não é 11, porque
        # DNV não é obrigatória nesta carga, e mandar 10 dígitos por 11 é
        # mandar um número que não é o da declaração de ninguém.
        _tag("DNV", _digitos(assento.get("dnv"))
             if len(_digitos(assento.get("dnv"))) == 11 else ""),
        _tag("DATANASCIMENTO", _data(assento.get("data_fato"))),
        _tag("HORANASCIMENTO", _hora(assento.get("hora_fato"))),
        # **O LOCAL VAI POR PALAVRA, E A ENUMERAÇÃO NÃO TEM VAZIO** — só
        # `IGNORADO`, `UNIDADE_SAUDE` e `FORA_UNIDADE_SAUDE`. O número saía
        # cru, fora da enumeração, em 212 de 212.
        _tag("LOCALNASCIMENTO", LOCAL_NASCIMENTO.get(
            _texto(assento.get("ibge_local_nascimento")), "IGNORADO")),
        # **SEXO TAMBÉM NÃO TEM VAZIO NO ENUM** (`M`, `F`, `I`) — `I` é
        # Ignorado, e é a resposta honesta quando a coluna não bate com
        # nenhuma das duas.
        _tag("SEXO", SEXO.get(_texto(reg.get("sexo")).upper(), "I")),
        # **POSSUIGEMEOS SÓ TEM `S`/`N`, SEM «IGNORADO»** — quando nada indica
        # gêmeo, `N` é o padrão seguro: é o que vale para a esmagadora maioria
        # (210 de 212 medidos), e a norma manda cada gêmeo se identificar por
        # nome quando existir (art. 234) — não há como um assento sozinho
        # "esquecer de dizer" que tem irmão gêmeo sem essa amarração.
        _tag("POSSUIGEMEOS", _possui_gemeos(assento) or "N"),
        _tag("NUMEROGEMEOS", _quantos_gemeos(assento)),
        # **"CODIGOIBGEMUNNASCIMENTO obrigatorio" — relato da CRC em
        # 11/09/2026**, em dezenas de nascimentos. Saía vazio dizendo que
        # "esta casa não tem coluna" — tem, é a naturalidade do próprio
        # REGISTRADO, a mesma busca que a remessa do IBGE já faz contra
        # `ib_municipios`.
        _tag("CODIGOIBGEMUNNASCIMENTO", _codigo_ibge_municipio(
            con, reg.get("naturalidade_cidade"), reg.get("naturalidade_uf"))),
        _tag("PAISNASCIMENTO", ""),
        _tag("NACIONALIDADE", ""),
        _tag("TEXTONACIONALIDADEESTRANGEIRO", ""),
    ]
    # **`DOCUMENTOS` NÃO TEM `DONO=REGISTRADO` NO NASCIMENTO** — o XSD só
    # enumera `'', FILIACAO_NASCIMENTO`: é o documento (não-CPF) DO GENITOR, e
    # não do registrado. Um recém-nascido não tem CPF nem RG próprio a
    # declarar aqui.
    #
    # **AS DUAS PASSADAS SÃO SEPARADAS DE PROPÓSITO** — a sequência do XSD é
    # `(FILIACAONASCIMENTO)* (DOCUMENTOS)*`, os dois grupos inteiros um
    # depois do outro, e não intercalados. Uma primeira versão gerava
    # filiação-do-pai, documento-do-pai, filiação-da-mãe, documento-da-mãe —
    # e a Central recusaria a segunda filiação, porque a validação já tinha
    # "saído" do grupo de filiações ao ver o primeiro documento.
    documentos_dos_genitores: list[str] = []
    for i, papel in enumerate(("PAI", "MAE"), 1):
        pessoa_papel = pessoas.get(papel, {})
        bloco = _filiacao(con, pessoa_papel, indice, i)
        if bloco:
            partes.append(bloco)
            doc = _documentos(pessoa_papel, "FILIACAO_NASCIMENTO", indice,
                              indice_filiacao=i)
            if doc:
                documentos_dos_genitores.append(doc)
    partes.extend(documentos_dos_genitores)
    # OBSERVACOES é obrigatória na sequência, e este projeto não tem de
    # onde tirar o texto — sai vazia, como todo campo sem fonte.
    partes.append(_tag("OBSERVACOES", ""))
    return "".join(partes)


# **"O MESMO" NÃO É UM NOME — é a forma como esta casa escreve, no
# `nome_pos`, que o cônjuge não passou a assinar diferente.** `rc_termo.py`
# lê isso certo («passou a assinar: O MESMO.»); a CRC não: `NOVONOMECONJUGE`
# é o nome que a pessoa usa, e mandar a frase «O MESMO» manda um nome que
# não existe. Quando não houve troca, o nome que se usa é o mesmo de sempre.
_SEM_TROCA = {"O MESMO", "A MESMA", "MESMO", "MESMA", "O MESMO."}


def _novo_nome(pessoa: dict) -> str:
    """O nome que o cônjuge passa a usar, para `NOVONOMECONJUGE{n}`.

    **"O campo NOVONOMECONJUGE2 está inválido" — relato da CRC em
    11/09/2026.** Duas causas, as duas na mesma coluna: a frase «O mesmo»
    (não é nome) e um ponto final sobrando de uma frase copiada
    («XISTO FALCAO NEIVA.», medido em 1 dos 22 casamentos) — os dois
    passam pelo `maxLength=100` do XSD, e por isso só a Central acusa.
    """
    nome_pos = _texto(pessoa.get("nome_pos")).strip(" .")
    if not nome_pos or _chave(nome_pos) in {_chave(v) for v in _SEM_TROCA}:
        return _texto(pessoa.get("nome"))
    return nome_pos


def registro_de_casamento(con: sqlite3.Connection, assento: dict,
                          pessoas: dict, indice: int) -> str:
    """O bloco de inclusão de um casamento. Só calcula.

    **O BLOCO É PLANO**: cada campo existe duas vezes, com sufixo 1 e 2. Não há
    sub-bloco de cônjuge, e a filiação deles é só nome e sexo — o que confirma,
    do lado da CRC, a decisão deste projeto de guardar as quatro filiações do
    casamento como pessoas.

    **A ORDEM É A DO XSD, E TODO CAMPO SEM `minOccurs="0"` SAI SEMPRE** —
    correção de 10/09/2026, a mesma do nascimento. `CPFCONJUGE1` e
    `SEXOCONJUGE1` só saíam quando havia o dado; o XSD os exige na sequência
    mesmo vazios, e `SEXOCONJUGE1` ausente derrubava o registro dizendo que
    `NOMEPAICONJUGE1` «não era esperado» ali — a mensagem aponta para o
    elemento seguinte, não para o que falta.
    """
    partes = [_tag("INDICEREGISTRO", indice)]
    for n, papel in ((1, "NUBENTE1"), (2, "NUBENTE2")):
        p = pessoas.get(papel, {})
        pai = pessoas.get(f"PAI{n}", {}) or (pessoas.get("PAI", {}) if n == 1
                                             else {})
        mae = pessoas.get(f"MAE{n}", {}) or (pessoas.get("MAE", {}) if n == 1
                                             else {})
        # **`NOVONOMECONJUGE{n}` TAMBÉM É OBRIGATÓRIO NA SEQUÊNCIA** — só
        # `SEXOPAICONJUGE`/`SEXOMAECONJUGE` são `minOccurs="0"` de verdade.
        # A primeira versão tratava este como opcional também, e um casal sem
        # nome de casada preenchido travava exatamente no próximo campo
        # (`CPFCONJUGE1`), com a mensagem apontando para o campo ANTERIOR —
        # o mesmo padrão do `CPFREGISTRADO` que motivou toda esta correção.
        partes.append(_tag(f"NOMECONJUGE{n}", p.get("nome")))
        # O NOME QUE CADA UM PASSOU A USAR — e o motivo pelo qual a
        # certidão de casamento existe. Medido: o segundo cônjuge muda em
        # 17 dos 20.
        partes.append(_tag(f"NOVONOMECONJUGE{n}", _novo_nome(p)))
        partes.append(_tag(f"CPFCONJUGE{n}", _cpf(p)))
        # SEXOCONJUGE também não tem vazio no enum (`M`/`F`/`I`) — `I` de
        # Ignorado é a resposta honesta, como no SEXO do nascimento.
        partes.append(_tag(f"SEXOCONJUGE{n}",
                           SEXO.get(_texto(p.get("sexo")).upper(), "I")))
        partes.append(_tag(f"DATANASCIMENTOCONJUGE{n}",
                           _data(p.get("data_nascimento"))))
        partes.append(_tag(f"NOMEPAICONJUGE{n}", pai.get("nome")))
        if pai.get("nome"):
            partes.append(_tag(f"SEXOPAICONJUGE{n}", "M"))
        partes.append(_tag(f"NOMEMAECONJUGE{n}", mae.get("nome")))
        if mae.get("nome"):
            partes.append(_tag(f"SEXOMAECONJUGE{n}", "F"))
        # Sem coluna nesta casa — a tag existe, vazia, pela mesma razão do
        # nascimento: presença estrutural sem conteúdo inventado.
        partes.append(_tag(f"CODIGOOCUPACAOSDCCONJUGE{n}", ""))
        partes.append(_tag(f"PAISNASCIMENTOCONJUGE{n}", ""))
        # **NÃO É TEXTO LIVRE — é código de até 3 caracteres**, e
        # `rc_pessoas.nacionalidade` guarda a palavra («Brasileira»), que
        # estoura o `maxLength`. O de-para código↔palavra não está medido
        # nesta casa; sai vazio em vez de truncar a palavra até caber.
        partes.append(_tag(f"NACIONALIDADECONJUGE{n}", ""))
        partes.append(_tag(f"CODIGOIBGEMUNNATCONJUGE{n}", _codigo_ibge_municipio(
            con, p.get("naturalidade_cidade"), p.get("naturalidade_uf"))))
        partes.append(_tag(f"TEXTOLIVREMUNNATCONJUGE{n}",
                           _texto_livre_municipio_nat(p)))
        partes.append(_tag(f"CODIGOIBGEMUNLOGRADOURO{n}", ""))
        partes.append(_tag(f"DOMICILIOESTRANGEIRO{n}", ""))
    partes.append(_tag("MATRICULA", _digitos(assento.get("matricula"))))
    partes.append(_tag("DATAREGISTRO", _data(assento.get("data_ato"))))
    partes.append(_tag("DATACASAMENTO", _data(assento.get("data_fato"))))
    # **O REGIME DE BENS É OBRIGATÓRIO NA SEQUÊNCIA, E A ENUMERAÇÃO NÃO ACEITA
    # VAZIO** — ao contrário de SEXO e de outros campos fechados, o XSD não
    # lista `''` entre os valores de `REGIMECASAMENTO`. Onde a casa não
    # informou ou não bate com o de-para, `IGNORADO` é a resposta honesta: é
    # um valor real da enumeração, e não um regime inventado (Lei 6.015/1973,
    # art. 70, item 6). A separação obrigatória do art. 1.641 do Código Civil
    # é a que a Central chama de LEGAL.
    partes.append(_tag("REGIMECASAMENTO",
                       _regime_resolvido(assento.get("regime_bens"),
                                         assento.get("data_fato"))
                       or "IGNORADO"))
    partes.append(_tag("OBSERVACOES", ""))
    return "".join(partes)


def _idade_do_falecido(nascimento: Any, obito: Any) -> tuple[str, str]:
    """A idade do falecido em anos, e a letra `A` do XSD. Só calcula.

    **NÃO É `ano do óbito − ano do nascimento` SEM DESCONTO** — esse é
    exatamente o defeito medido no E-Ofício (`REMESSA_IBGE_CONFERIDA.md`): ele
    errava a idade por um ano em quem morria antes do aniversário, em 3 dos 11
    óbitos comparáveis. Aqui o desconto entra pela comparação de texto
    `MM-DD`, que ordena igual a data porque tem largura fixa.

    Devolve `("", "")` quando falta uma das duas datas — o XSD aceita os dois
    campos vazios (nem `IDADE` nem `IDADE_DIAS_MESES_ANOS` têm enumeração sem
    `''`), e idade calculada de data que falta seria inventar.
    """
    n, o = _texto(nascimento)[:10], _texto(obito)[:10]
    if len(n) != 10 or len(o) != 10:
        return "", ""
    anos = int(o[:4]) - int(n[:4]) - (o[5:10] < n[5:10])
    if anos < 0:
        return "", ""
    return str(min(anos, 999)), "A"


def registro_de_obito(con: sqlite3.Connection, assento: dict, pessoas: dict,
                      indice: int) -> str:
    """O bloco de inclusão de um óbito. Só calcula — 78 tags no manual."""
    fal = pessoas.get("FALECIDO", {})
    nome = _texto(fal.get("nome") or assento.get("nome"))
    idade, idade_unidade = _idade_do_falecido(
        fal.get("data_nascimento"), assento.get("data_fato"))
    dec = pessoas.get("DECLARANTE", {})

    partes = [
        _tag("INDICEREGISTRO", indice),
        _tag("FLAGDESCONHECIDO", "N"),
        _tag("NOMEFALECIDO", nome),
        _tag("CPFFALECIDO", _cpf(fal)),
        _tag("MATRICULA", _digitos(assento.get("matricula"))),
        _tag("DATAREGISTRO", _data(assento.get("data_ato"))),
    ]
    for papel, tag, sexo in (("PAI", "NOMEPAI", "M"), ("MAE", "NOMEMAE", "F")):
        p = pessoas.get(papel, {})
        partes.append(_tag(tag, p.get("nome")))
        partes.append(_tag(f"CPF{papel}", _cpf(p)))
        if p.get("nome"):
            partes.append(_tag(f"SEXO{papel}", sexo))
    partes.extend([
        _tag("DATAOBITO", _data(assento.get("data_fato"))),
        _tag("HORAOBITO", _hora(assento.get("hora_fato"))),
        _tag("SEXO", SEXO.get(_texto(fal.get("sexo")).upper(), "I")),
        _tag("CORPELE", COR_PELE.get(_texto(assento.get("cor_raca")).upper(),
                                     "IGNORADA")),
        _tag("ESTADOCIVIL", ESTADO_CIVIL.get(_chave(fal.get("estado_civil")), "")),
        _tag("DATANASCIMENTOFALECIDO", _data(fal.get("data_nascimento"))),
        _tag("IDADE", idade),
        _tag("IDADE_DIAS_MESES_ANOS", idade_unidade),
    ])
    # **"Campo ELEITOR deve ser preenchido com S, N ou I" — relato da CRC em
    # 11/09/2026, em praticamente todo óbito.** O XSD enumera `''` também, e
    # por isso isto nunca quebrava contra o schema local — mas a Central
    # exige um dos três na validação de negócio. `I` (Ignorado) é a resposta
    # honesta de quem não perguntou, e é a mesma resposta que este módulo já
    # dá para SEXO e para LOCALNASCIMENTO quando a coluna não bate.
    # POSSUIBENS não foi apontado pela CRC, e continua podendo sair vazio.
    partes.append(_tag("ELEITOR", MARCA_SIM_NAO.get(
        _chave(assento.get("obito_eleitor")), "I")))
    partes.append(_tag("POSSUIBENS", MARCA_SIM_NAO.get(
        _chave(assento.get("obito_possui_bens")), "")))
    # Sem coluna nesta casa — presença estrutural, sem conteúdo inventado.
    partes.append(_tag("CODIGOOCUPACAOSDC", ""))
    partes.append(_tag("PAISNASCIMENTO", ""))
    partes.append(_tag("NACIONALIDADE", ""))
    partes.append(_tag("CODIGOIBGEMUNNATURALIDADE", _codigo_ibge_municipio(
        con, fal.get("naturalidade_cidade"), fal.get("naturalidade_uf"))))
    partes.append(_tag("TEXTOLIVREMUNICIPIONAT",
                       _texto_livre_municipio_nat(fal)))
    partes.append(_tag("CODIGOIBGEMUNLOGRADOURO", ""))
    partes.append(_tag("DOMICILIOESTRANGEIROFALECIDO", ""))
    partes.append(_tag("LOGRADOURO", fal.get("endereco")))
    partes.append(_tag("NUMEROLOGRADOURO", ""))
    partes.append(_tag("COMPLEMENTOLOGRADOURO", ""))
    partes.append(_tag("BAIRRO", fal.get("bairro")))
    doc = _documentos(fal, "FALECIDO", indice)
    if doc:
        partes.append(doc)
    # **A CHAVE É O CÓDIGO, e a palavra é a do XSD.** Aqui a chave era
    # «NATURAL» e a coluna guarda `1` — o `.get` devolvia None e a tag **nunca
    # saía**, em 31 de 31 óbitos, sem erro em lugar nenhum.
    partes.append(_tag("TIPOLOCALOBITO", TIPO_LOCAL_OBITO.get(
        _texto(assento.get("ibge_local_obito")), "")))
    partes.append(_tag("TIPOMORTE", TIPO_MORTE.get(
        _chave(assento.get("ibge_natureza_obito")), "")))
    if assento.get("numero_do"):
        partes.append(_tag("NUMDECLARACAOOBITO",
                           _digitos(assento["numero_do"])))
    partes.append(_tag("CODIGOIBGEMUNLOGRADOUROOBITO", ""))
    partes.append(_tag("ENDERECOLOCALOBITOESTRANGEIRO", ""))
    partes.append(_tag("LOGRADOUROOBITO", assento.get("local_fato_endereco")))
    partes.append(_tag("NUMEROLOGRADOUROOBITO", ""))
    partes.append(_tag("COMPLEMENTOLOGRADOUROOBITO", ""))
    partes.append(_tag("BAIRROOBITO", ""))
    # **CAUSA DA MORTE, ATESTANTE E SEPULTAMENTO TÊM COLUNA NESTA CASA**
    # (`causa_morte`, `atestante`, `atestante_documento`,
    # `local_sepultamento` — art. 80, itens 6º, 8º e 9º da Lei 6.015/1973), e
    # **nenhuma tela ainda as grava** — estão vazias em toda a produção
    # medida. A tag existe, honestamente vazia, até que a tela exista.
    causa_a, causa_b, causa_c, causa_d, _sobrou_causa = (
        _causa_morte_em_quatro_linhas(assento.get("causa_morte")))
    partes.append(_tag("CAUSAMORTEANTECEDENTES_A", causa_a))
    partes.append(_tag("CAUSAMORTEANTECEDENTES_B", causa_b))
    partes.append(_tag("CAUSAMORTEANTECEDENTES_C", causa_c))
    partes.append(_tag("CAUSAMORTEANTECEDENTES_D", causa_d))
    partes.append(_tag("CAUSAMORTEOUTRASCOND_A", ""))
    partes.append(_tag("CAUSAMORTEOUTRASCOND_B", ""))
    partes.append(_tag("LUGARFALECIMENTO", assento.get("local_fato_nome")))
    partes.append(_tag("LUGARSEPULTAMENTOCEMITERIO",
                       assento.get("local_sepultamento")))
    partes.append(_tag("NOMEATESTANTEPRIMARIO", assento.get("atestante")))
    partes.append(_tag("CRMATESTANTEPRIMARIO",
                           _crm_atestante(assento.get("atestante_documento"))))
    partes.append(_tag("NOMEATESTANTESECUNDARIO", ""))
    partes.append(_tag("CRMATESTANTESECUNDARIO", ""))
    partes.append(_tag("NOMEDECLARANTE", dec.get("nome")))
    partes.append(_tag("CPFDECLARANTE", _cpf(dec)))
    partes.append(_tag("OBSERVACOES", ""))
    return "".join(partes)


MONTADOR = {
    "NASCIMENTO": registro_de_nascimento,
    "NATIMORTO": registro_de_nascimento,
    "CASAMENTO": registro_de_casamento,
    "CASAMENTO_RELIGIOSO": registro_de_casamento,
    "OBITO": registro_de_obito,
}


def montar(con: sqlite3.Connection, assentos: list[int], *, cns: str) -> dict:
    """O XML da carga, e a lista do que ficou de fora. Só lê.

    **AS INCLUSÕES VÊM ANTES DAS ALTERAÇÕES**, e a ordem é imposta pelo manual:
    «deve-se formatar o XML primeiro com as INCLUSÕES e depois com as ALTERAÇÕES
    em cada tipo de registro».

    **E o que não pode ir NÃO some**: volta em `retidos`, com o motivo. Mandar
    só o que deu certo produziria um arquivo bem formado e incompleto — e a
    Central o aceitaria, que é o pior desfecho.
    """
    con.row_factory = sqlite3.Row
    por_movimento: dict[str, list[str]] = {}
    retidos: list[dict] = []
    a_arrumar: list[dict] = []
    indice = 0

    for aid in assentos:
        a = con.execute("SELECT * FROM rc_assentos WHERE id = ?",
                        (aid,)).fetchone()
        if not a:
            retidos.append({"assento_id": aid,
                            "faltas": ["o assento não existe"]})
            continue
        a = dict(a)
        especie = _texto(a.get("especie")).upper()
        if especie not in MOVIMENTO_DA_ESPECIE:
            retidos.append({
                "assento_id": aid, "nome": a.get("nome"),
                "faltas": [
                    (f"a CRC não recebe {especie.lower() or 'esta espécie'}"
                     " — ela carrega nascimento, casamento e óbito")]})
            continue

        pessoas = _pessoas_do_assento(con, aid)
        faltas = o_que_falta(con, a, pessoas)
        if faltas:
            retidos.append({"assento_id": aid, "nome": a.get("nome"),
                            "especie": especie, "faltas": faltas})
            continue

        # **O QUE VAI E PRECISA DE CONSERTO** — relato do oficial em
        # 10/09/2026. Ele **não** retém: o manual não exige a filiação, e
        # travar por ela deixaria 20 registros válidos fora da Central.
        arrumar = o_que_arrumar(con, a, pessoas)
        if arrumar:
            a_arrumar.append({"assento_id": aid, "nome": a.get("nome"),
                              "especie": especie, "arrumar": arrumar})

        indice += 1
        bloco, inclusao, _ = MOVIMENTO_DA_ESPECIE[especie]
        corpo = MONTADOR[especie](con, a, pessoas, indice)
        por_movimento.setdefault(bloco, []).append(
            f"<{inclusao}>{corpo}</{inclusao}>")

    partes = ['<?xml version="1.0" encoding="utf-8"?>', "<CARGAREGISTROS>",
              _tag("VERSAO", VERSAO), _tag("ACAO", ACAO_CARGA),
              _tag("CNS", _digitos(cns))]
    # NA ORDEM DO XSD, e não na ordem em que os assentos chegaram — ver
    # `ORDEM_DOS_MOVIMENTOS`. Percorrer `por_movimento` direto escrevia o
    # arquivo na ordem de inserção, e a Central recusava a carga inteira.
    for bloco in ORDEM_DOS_MOVIMENTOS:
        itens = por_movimento.get(bloco)
        if itens:
            partes.append(f"<{bloco}>" + "".join(itens) + f"</{bloco}>")
    partes.append("</CARGAREGISTROS>")

    return {"xml": "".join(partes), "quantos": indice, "retidos": retidos,
            "a_arrumar": a_arrumar}


def _pessoas_do_assento(con: sqlite3.Connection, assento_id: Any) -> dict:
    """As pessoas daquele assento, por papel — como `o_que_falta` as espera."""
    con.row_factory = sqlite3.Row
    saida: dict[str, dict] = {}
    for linha in con.execute(
            "SELECT * FROM rc_pessoas WHERE assento_id=? ORDER BY ordem",
            (int(assento_id),)):
        papel = _texto(linha["papel"]).upper()
        if papel and papel not in saida:
            saida[papel] = dict(linha)
    return saida


def em_quarentena(con: sqlite3.Connection, limite: int = 20_000) -> list[dict]:
    """Os assentos que a Central recusaria, com o que falta em cada um.

        «os que foram importados sem elemento essencial para a CRC, deixar em
         quarentena pendente de complemento. não entra nas cargas de envio»
         — o oficial, 12/09/2026

    **A QUARENTENA É DERIVADA, E NÃO UMA MARCA GRAVADA.** Ela é o próprio
    `o_que_falta` medido na hora: complete o dado que falta, e o assento sai da
    quarentena **sozinho**, sem ninguém lembrar de desmarcar nada. É a lição de
    `inacabados` — uma lente, e não uma segunda gaveta, porque a cópia diverge
    do fato no primeiro conserto.

    **E ELA MOSTRA, MAS NÃO RETÉM — quem retém é `montar`.** Esta função é a
    VISTA de uma decisão que já existia: o assento incompleto nunca entrou no
    XML, e voltava em `retidos` na hora de montar. O que faltava era o balcão
    **ver isso antes de escolher**, em vez de descobrir no fim.

    Eu cheguei a fazer `pendentes_de_carga` filtrar por aqui, e foi um erro
    grande: os 244 assentos do acervo são justamente os que não têm sexo nem
    município, e **a carga existe para subir o acervo à Central**. A lista de
    candidatos continua trazendo todos.

    **E NÃO SE USOU `situacao` PARA ISSO, embora ela já filtre a carga.** Ela é
    `ATIVO | CANCELADO`, e `rc_assento` **recusa lançamento e correção** em
    assento que não está ATIVO — pôr a quarentena ali trancaria justamente o
    que precisa ser completado, e ainda daria a `CANCELADO`, que tem sentido
    jurídico, um segundo significado. A mesma palavra em dois lugares não quer
    dizer a mesma coisa.
    """
    con.row_factory = sqlite3.Row
    retidos = []
    for linha in con.execute(
            """SELECT * FROM rc_assentos
                WHERE especie IN ('NASCIMENTO','NATIMORTO','CASAMENTO',
                                  'CASAMENTO_RELIGIOSO','OBITO')
                  AND COALESCE(situacao,'ATIVO') = 'ATIVO'
             ORDER BY data_ato, id LIMIT ?""", (limite,)):
        assento = dict(linha)
        faltas = o_que_falta(con, assento,
                             _pessoas_do_assento(con, assento["id"]))
        if faltas:
            retidos.append({
                "id": assento["id"], "especie": assento["especie"],
                "numero": assento["numero"], "nome": assento["nome"],
                "data_ato": assento["data_ato"],
                "matricula": assento["matricula"],
                "o_que_falta": faltas,
            })
    return retidos


def pendentes_de_carga(con: sqlite3.Connection, limite: int = 20_000, *,
                       incluir_ja_enviados: bool = False) -> list[dict]:
    """Os assentos que a CRC ainda não recebeu. Só lê.

    **O LIMITE ERA 500, E MENTIA — achado em 13/09/2026, no dia em que o
    acervo em `.docx` fez a carga passar de 280 para mais de 7.000
    assentos.** `<h2>Assentos ({{ candidatos|length }})</h2>` mostrava
    "Assentos (500)" como se fosse o total — e a conta de "já enviados"
    (`len(todos_ativos) - len(nao_enviados)`) comparava duas listas cortadas
    no mesmo teto, um resultado sem sentido. Medido contra o lote real:
    `pendentes_de_carga(limite=20000)` devolve os 7.035 em 0,3 s — o corte
    de 500 nunca precisou existir por desempenho, só sobrou de um número
    escrito sem medir o tamanho real da carga.

    ELA SE CHAMAVA `a_enviar`, E O VARREDOR PEGOU. Ele varre os nomes públicos
    procurando «enviar», para provar que este módulo não manda nada — e aquele
    nome, que era um substantivo («os a enviar»), lia-se como verbo.

    O varredor estava certo em ser burro: **um nome que se lê como ação é um
    nome que alguém vai usar como ação.** É a mesma correção de
    `campos_para_lavrar`, que virou `campos_do_ato` pelo mesmo motivo — e ali
    também o guarda valeu mais que o nome.

    **E ELA MENTIA — relato do oficial em 11/09/2026: "os assentos não
    ficaram lá nas cargas, sem opção de dizer que já foram enviados".** Até
    esta correção a lista devolvia SEMPRE os mesmos assentos, porque nada
    guardava «este já foi». Agora ela some por padrão o que tem lote
    registrado em `rc_crc_lotes` — `incluir_ja_enviados=True` traz de volta,
    para quem quiser reenviar de propósito.
    """
    # **ESTA LISTA NÃO FILTRA PELO QUE FALTA — e eu a fiz filtrar por algumas
    # horas, em 12/09/2026, e quebrei a razão de ela existir.**
    #
    #   Quem retém o assento incompleto é `montar`, que o deixa fora do XML e
    #   o devolve em `retidos`, com o motivo — a quarentena que o oficial pediu
    #   **já estava construída ali**. Repeti-la aqui foi uma segunda régua para
    #   o mesmo fato, e ela tirou da carga **o acervo histórico inteiro**: os
    #   244 assentos do E-Ofício são justamente os que não têm sexo nem
    #   município, e a carga existe *para* subir o acervo à Central.
    #
    #   **Quem me pegou foi o teste que guarda isso**, e o texto dele diz o
    #   que eu tinha esquecido: «a carga é *justamente* a subida do acervo
    #   histórico — excluí-lo apagaria a razão de ela existir».
    con.row_factory = sqlite3.Row
    if incluir_ja_enviados:
        return [dict(r) for r in con.execute(
            """SELECT id, especie, numero, nome, data_ato, matricula
                 FROM rc_assentos
                WHERE especie IN ('NASCIMENTO','NATIMORTO','CASAMENTO',
                                  'CASAMENTO_RELIGIOSO','OBITO')
                  AND COALESCE(situacao,'ATIVO') = 'ATIVO'
             ORDER BY data_ato, id LIMIT ?""", (limite,))]
    return [dict(r) for r in con.execute(
        """SELECT id, especie, numero, nome, data_ato, matricula
             FROM rc_assentos
            WHERE especie IN ('NASCIMENTO','NATIMORTO','CASAMENTO',
                              'CASAMENTO_RELIGIOSO','OBITO')
              AND COALESCE(situacao,'ATIVO') = 'ATIVO'
              AND id NOT IN (SELECT assento_id FROM rc_crc_lote_assentos)
         ORDER BY data_ato, id LIMIT ?""", (limite,))]
