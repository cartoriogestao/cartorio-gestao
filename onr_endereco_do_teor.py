# -*- coding: utf-8 -*-
"""O endereço que o ONR exige, lido do TEOR das fichas que vieram do OCR.

Medido em 15/09/2026, no banco da produção, porque a pergunta era «quantas
matrículas ainda não conseguem ir ao índice real, e por quê»:

    278 fichas têm teor e não têm endereço — 67 rurais e 211 urbanas.

**O DADO NÃO FALTA: ELE ESTÁ ESCRITO EM PROSA.** A ficha do E-Ofício descreve
o imóvel em texto corrido — «uma AREA DE TERRAS denominada "Barra do Arraias
II", situada na Fazenda Angical, neste Município de Cidade Exemplo» —, e as
colunas de endereço nasceram com o nosso módulo, depois do OCR. O que existe
é uma frase; o que o contrato pede são sete campos.

O QUE SE MEDIU PARA ESCREVER ISTO, E NÃO SE SUPÔS
    - **1.400 das 1.443** fichas sem endereço trazem a marca `IMÓVEL:` (o
      `denominada` sozinho acha menos, e a marca é o começo do bloco).
    - Das 162 cuja coluna `rural_urbano` diz «R», **158 dizem o mesmo no
      teor** — e as 4 que discordam são o caso em que a coluna está errada,
      como se viu nas de 2026, cujas fichas foram escritas por este sistema.
    - O nome do imóvel vem em **quatro formas**, e as quatro estão nos dados:
      `DENOMINAÇÃO:` rotulado (as ESTRUTURADAS), `denominada "X"` (a mais
      comum), `NO LUGAR "X"` (a antiga), e `na FAZENDA X` sem aspas (a de
      matrícula 2).
    - **As 1.701 matrículas rurais do acervo são «Área»**: `rural_urbano='R'`
      em 1.652 e `tipo_imovel=NULL` em 1.224. Não é dedução — é a forma do
      dado desta casa.
    - `CODIGO_DO_IMOVEL['fazenda/sitio/chacara'] = 69`, e o texto do acervo
      diz **exatamente** «Fazenda/Sítio/Chácara». O que falta ali não é valor,
      é quem o escreva.

**ELE NÃO GRAVA NA FICHA.** Propõe, e a proposta fica ao lado do que já está
lá, com a frase de onde saiu. Quem confirma é uma pessoa na tela — é a regra do
CNIB pela oitava vez: o sistema prepara, o oficial decide. Escrever direto em
1.443 fichas com uma expressão regular seria a máquina lavrando ato registral.

**O QUE NÃO SE ACHOU FICA DITO.** `faltam` sai na proposta e na tela; campo
vazio que ninguém sabe que está vazio é o defeito que este módulo existe para
acabar. E **onde o teor discorda da coluna `rural_urbano`, a proposta NÃO sai
pronta** — ela vai para a conferência com as duas versões à vista.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from bd_nativo import banco
import onr_api as API

# A CONVERSÃO DE ÁREA VEM DE `onr_api`, e **não** é uma cópia: ela subiu para lá
# em 15/09/2026 porque o `montar_indicador` também precisa dela, e este módulo
# importa `partir_logradouro` de `ri_onr_central` — deixá-la aqui poria os dois
# módulos a depender um do outro. O nome continua valendo neste arquivo.
from onr_api import area_em_metros  # noqa: F401  (usado por `area_do_texto`)

# A PARTIÇÃO DO LOGRADOURO É A MESMA DE `ri_onr_central`, e não uma parecida:
# o que este módulo escreve é o que `montar_indicador` vai partir de novo. Duas
# réguas de partir logradouro divergiriam no primeiro conserto, e o defeito só
# apareceria meses depois, na ficha que o ONR recusou.
from ri_onr_central import partir_logradouro


class EnderecoError(ValueError):
    """Recusa de regra, com a frase pronta para o balcão."""


# ═══════════════════════════════════════════════════════════════════════
# 1. A LIMPEZA — o mesmo cuidado de `onr_baldes2.py`, e pelo mesmo motivo
# ═══════════════════════════════════════════════════════════════════════

# AS ENTIDADES SÃO AS QUE APARECEM NESTE ACERVO, e não a lista inteira do
# HTML: as que não estão aqui não aparecem em 1.700 fichas medidas.
_ENTIDADES: tuple[tuple[str, str], ...] = (
    ("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'), ("&#39;", "'"),
    ("&lt;", "<"), ("&gt;", ">"), ("&ordm;", "º"), ("&ordf;", "ª"),
    ("&aacute;", "á"), ("&eacute;", "é"), ("&iacute;", "í"),
    ("&oacute;", "ó"), ("&uacute;", "ú"), ("&ecirc;", "ê"),
    ("&atilde;", "ã"), ("&otilde;", "õ"), ("&ccedil;", "ç"),
    ("&Aacute;", "Á"), ("&Oacute;", "Ó"), ("&Ccedil;", "Ç"),
)


def texto_do_teor(teor: Any) -> str:
    """O HTML da ficha vira texto, **com as quebras de linha no lugar**.

    A quebra não é enfeite: ela é o fim de um campo e o começo do outro na
    ficha do E-Ofício — «…Área: 231,00,00 Há\\nLocalização: ZONA RURAL» —, e
    trocá-la por espaço faria os dois campos virarem um só.
    """
    t = "" if teor is None else str(teor)
    if not t:
        return ""
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
    t = re.sub(r"(?i)</p>|<br\s*/?>|</div>|</tr>|</h[1-6]>", "\n", t)
    # **A TAG INLINE SAI SEM DEIXAR ESPAÇO — e ela deixava, no meio da
    # palavra.** Medido em 16/09/2026, nas 1.982 fichas: **166 tags em 43
    # fichas** caem entre duas letras, e **todas as 166 são `<span>`** — o
    # editor do E-Ofício marcava uma letra em negrito e a embrulhava sozinha.
    # A matrícula 3976 (`id` 5131) traz
    # `Fazenda Três <span style="font-weight:bold;">P</span>orteiras`, e a
    # limpeza antiga lia **`Fazenda Três orteiras`** — um nome que parece
    # medido e está errado, indo para o índice que o país consulta para saber
    # de quem é o imóvel. É a família do «nome plausível»: o `P` que sumiu não
    # aparece em log nenhum.
    #
    # **A régua é o que a tag É, e não o que ela parece**: a de bloco já virou
    # quebra de linha na linha de cima (`</p>`, `</div>`, `</tr>`, `</h1..6>`),
    # de modo que o que sobra aqui é o que não separa nada — e a de bloco que
    # sobrar (uma abertura de `<p>` solta) continua virando espaço, que é o
    # comportamento antigo e o certo para ela.
    t = re.sub(r"(?i)</?(?:span|b|i|u|font|strong|em|a|sup|sub|small|big|s|"
               r"strike|tt|code|abbr|cite|q|mark)(?:\s[^>]*)?/?>", "", t)
    t = re.sub(r"<[^>]+>", " ", t)
    for de, para in _ENTIDADES:
        t = t.replace(de, para)
    # **AS NUMÉRICAS TAMBÉM**, e isto foi medido numa ficha real: a matrícula
    # 3205 traz `Fazenda &#x0027;B o m Jesus&#x0027;`, e sem estas duas linhas
    # o nome do imóvel sairia com a entidade dentro — e o nome do imóvel é o
    # `logradouro` que o ONR publica. `&#x0027;` é o apóstrofo de `D'Anta`.
    t = re.sub(r"&#[xX]([0-9A-Fa-f]{2,6});",
               lambda m: chr(int(m.group(1), 16)), t)
    t = re.sub(r"&#(\d{2,6});", lambda m: chr(int(m.group(1))), t)
    # **RÓTULO QUE TERMINA EM DOIS-PONTOS: O VALOR ESTÁ NA LINHA DE BAIXO.**
    # Medido na matrícula 3975 — `DENOMINAÇÃO DO IMÓVEL RURAL:` e, na linha
    # seguinte, `Fazenda Três Porteiras; área total (ha): 46,0000`. Sem esta
    # linha o valor não é lido: os padrões param no fim da linha, e o nome
    # saía como «do imóvel rural:», que é o rótulo, e iria assim para o
    # índice nacional.
    t = re.sub(r":\s*\n\s*", ": ", t)
    return re.sub(r"[ \t\u00a0]+", " ", t)


# ═══════════════════════════════════════════════════════════════════════
# 2. O BLOCO — a marca `IMÓVEL:` e onde ele termina
# ═══════════════════════════════════════════════════════════════════════

# **A MARCA É O SINGULAR COM SEPARADOR.** O cabeçalho de página escreve
# «IMOVEIS» (plural, sem dois-pontos) e a prosa escreve «Imóveis de
# Imperatriz»; a única coisa que abre o bloco do imóvel é o rótulo.
MARCA_DO_IMOVEL = re.compile(r"(?i)\bIM[ÓO]VEL\s*[:\-–]\s*")

# O QUE FECHA O BLOCO, em **duas formas**, e a segunda nasceu de uma medição
# que desmentiu a primeira.
#
# > **A PRIMEIRA VERSÃO NUNCA FECHOU NADA, e o defeito estava escondido atrás
# > de um `^`.** O padrão era `^\s*(?:PROPRIET[ÁA]RIOS?|…)`, e `^` **sem o
# > sinalizador `re.M` só casa no começo do texto** — que é justamente onde o
# > bloco não está, porque ele começa logo depois da marca `IMÓVEL:`. O
# > resultado: `fim` era sempre `None`, o bloco corria até o limite de 2.000
# > caracteres e engolia o resto da ficha.
# >
# > **E o estrago apareceu no ensaio contra a produção, não na releitura.** Com
# > o bloco comprido, o município lido era o **endereço da PARTE** — «residente
# > e domiciliado na cidade de Imperatriz-MA» —, e Imperatriz não é o
# > município de nenhum imóvel desta casa: é onde mora quem vende. Medido: a
# > expressão «cidade de Imperatriz» aparece em **198 fichas**, e em **111**
# > delas a mesma ficha também diz «município de Cidade Exemplo» — ou seja, a
# > parte mora em Imperatriz e o imóvel está aqui.
#
# As duas formas, e a ordem em que são procuradas:
#
#  1. **O RÓTULO**, que a ficha escreve com dois pontos ou travessão e que pode
#     estar **no meio da linha** — «…Imperatriz/MA. TÍTULO:- Compra e venda.».
#     É a forma dos títulos, dos valores e das transcrições.
#  2. **A SEÇÃO**, que a ficha escreve começando a linha — «PROPRIETÁRIOS:-»,
#     «PÁGINA 12». Aqui o `^` vale, e vale com `re.M`.
FIM_DO_BLOCO = re.compile(
    r"(?i)\b(?:PROPRIET[ÁA]RIOS?|TITULAR(?:ES)?|ADQUIRENTES?|TRANSMITENTES?|"
    r"VENDEDORES?|COMPRADORES?|CEDENTES?|OUTORGANTES?|ENFITEUTA|"
    r"USUFRUT[ÚU][ÁA]RIO|AVERBA[ÇC][ÕO]ES?|MATR[ÍI]CULA\s+ANTERIOR|"
    r"REGISTRO\s+ANTERIOR|CANCELAMENTO|T[ÍI]TULO(?:\s+AQUISITIVO)?|"
    r"VALOR|ORIGEM)\s*[:=]"
)
SECAO_QUE_FECHA = re.compile(
    r"(?im)^\s*(?:P[ÁA]GINA\s+\d|LIVRO\s+[A-Z0-9]|IM[ÓO]VEIS?\s*:|"
    r"TRANSCRI[ÇC][ÃA]O\s+N|REGISTRO\s+N)"
)

# **ONDE FECHAR É TÃO IMPORTANTE QUANTO SE TEM O QUE LER.** Um rótulo que caia
# colado na marca — «IMÓVEL: TÍTULO:-» — deixaria o bloco vazio, e bloco vazio
# não propõe nada. Por isso o fecho só vale se sobrar descrição suficiente; se
# não sobrar, procura-se o próximo.
MINIMO_DO_BLOCO = 60


def bloco_do_imovel(teor: Any, *, limite: int = 2000) -> dict:
    """O pedaço da ficha que descreve o imóvel, e se a marca foi achada.

    Devolve `{"texto": str, "achou": bool, "comeco": int}`. Sem a marca, o
    texto volta **inteiro e cortado no limite** — o extrator tenta ainda, e
    quem lê a proposta vê de onde saiu.
    """
    t = texto_do_teor(teor)
    if not t:
        return {"texto": "", "achou": False, "comeco": 0}
    m = MARCA_DO_IMOVEL.search(t)
    if not m:
        return {"texto": t[:limite], "achou": False, "comeco": 0}
    corpo = t[m.end():m.end() + limite]
    fim = _onde_o_bloco_termina(corpo)
    if fim is not None:
        corpo = corpo[:fim]
    return {"texto": corpo, "achou": True, "comeco": m.end()}


def _onde_o_bloco_termina(corpo: str) -> int | None:
    """Em que ponto do texto a descrição do imóvel acaba.

    Devolve `None` quando nenhum fecho deixa descrição suficiente — e o
    `None` é resposta, não falha: significa «não achei onde termina», e quem
    chama fica com o texto inteiro, como antes.
    """
    if not corpo:
        return None
    # Os dois padrões, na ordem em que aparecem no texto: o rótulo primeiro
    # (porque é o mais comum), e a seção como alternativa.
    for padrao in (FIM_DO_BLOCO, SECAO_QUE_FECHA):
        for m in padrao.finditer(corpo):
            if m.start() >= MINIMO_DO_BLOCO:
                return m.start()
    return None


# ═══════════════════════════════════════════════════════════════════════
# 3. O NOME DO IMÓVEL — as quatro formas medidas
# ═══════════════════════════════════════════════════════════════════════

# ONDE O NOME ACABA. É a lista que separa o nome da frase seguinte:
# «Fazenda "Leôncio"**,** com área de…», «"Cocalinho"** situada** na Fazenda…».
#
# **O PONTO SOZINHO NÃO É FRONTEIRA**, e isto foi medido: há nomes com ponto
# dentro — `FAZENDA "SÃO JOSÉ – LT.217 – GL. DIVISA"`. Por isso a fronteira é
# **ponto seguido de espaço**, que não existe dentro de `LT.217`.
#
# > **A FRASE DESCRITIVA ENTRAVA INTEIRA NO LOGRADOURO — medido em 15/09/2026,
# > nas 1.410 propostas com logradouro.** Cinco delas iam assim (quatro já
# > `pode_enviar=1`) e seriam publicadas no índice nacional do ONR, que é a
# > lista que o país inteiro consulta para saber de quem é o imóvel:
# >
# > | o que ia | o que é |
# > |---|---|
# > | `Fazenda Santa Rosa a margem direita do Ribeirão Campo Alegre` | o nome, e a confrontação dele |
# > | `Área Riacho do Meio até a nascente do mesmo` | idem |
# > | `Área Ribeirãozinho até sua nascente` | idem |
# > | `fazenda Fortaleza dali rumo do N` | idem |
# > | `Estrada com uma linha de 67ºSE e 110 metros` | isto não é nome: é a descrição de um terreno sem rua |
# >
# > **A régua antiga cortava na vírgula, e a ficha velha não usa vírgula.** O que
# > ela usa é a **frase relativa** — `que vai`, `que liga`, `que demanda` — e a
# > **medida** — `com uma linha de`, `até a nascente`, `a margem direita`. São
# > elas que entram agora, e cada uma foi conferida contra as 1.410: **cortam 21,
# > e nenhuma delas é nome de imóvel.**
# >
# > E o que **não** entrou, porque a medição desmentiria: `até` e `margem`
# > soltos, e `rumo` sozinho. Nome de imóvel tem `Norte`, `Nascente`, `Divisa` e
# > `Estrela` dentro — `Fazenda Estrela do Norte`, `Área Sol Nascente` —, e uma
# > lista de palavras cortaria justamente os bons. **O que se procura é a frase,
# > e não a palavra.**
#
# > **E A PRIMEIRA VERSÃO MEDIU UMA STRING E O PROGRAMA CORTAVA OUTRA —
# > corrigido no mesmo dia.** A frase era procurada sempre **depois de um
# > espaço** (`\s+com`), e isso funciona no texto corrido. Só que `_corta`
# > recebe o fragmento **já sem o tipo**: quem casou «ESTRADA» foi o
# > `VIA_NO_TEXTO`, e o que sobra para cortar começa em «com uma linha de
# > 67ºSE…». **No começo da string não há espaço antes de `com`**, a fronteira
# > não achava nada, e a prosa entrava inteira.
# >
# > A medição das 21 propostas tinha rodado sobre a string **com** o tipo
# > («Estrada com uma linha…» → «Estrada»), que é a forma em que o defeito não
# > aparece: **contar de um jeito e o programa comparar de outro dá um número
# > com cara de medição que não é.** Das 21, **seis não encolheram nada** no
# > programa — `Estrada com uma linha…`, `Beco que vem…`, `Rua e fundos…`,
# > `Área no vértice…`, `Área objeto da presente` e `Área nesta descrição…` —, e
# > quatro delas iam `pode_enviar=1`.
# >
# > O conserto é a fronteira de **palavra** (`\bcom\b`), que vale nos dois
# > lugares: no meio da frase e no começo dela. `Comendador` e `Quebra-Pote`
# > continuam inteiros, porque depois de `com` e de `que` vem letra, e `\b`
# > exige fronteira. E quando a frase abre o fragmento, o corte devolve **vazio**
# > — que é a resposta certa: «com uma linha de 67ºSE» não é nome de rua, e o
# > extrator segue para as outras formas em vez de gravar lixo.
#
# > **E A REGRA DO PONTO SAIU NO MESMO DIA, DEPOIS DE MEDIDA.** Ela estava aqui
# > (`\.\s`, «o nome acaba na primeira frase») e parecia zelo. O extrator rodou
# > **duas vezes sobre as 1.551 fichas** que têm teor, com e sem ela: o
# > logradouro muda em **sete**, e **nas sete o ponto corta uma abreviatura, e
# > não uma frase**:
# >
# > | ficha | com a regra | sem ela |
# > |---|---|---|
# > | 3.503 | `Área FAZ` | `Área FAZ. BOA VISTA` |
# > | 4.095 | `Área Santa Rosa` | `Área Santa Rosa.` |
# > | 4.523 | `FAZENDA SÃO JOSÉ – LT.` | `… – LT.217 – GL. DIVISA` |
# > | 4.717 | `Chácara São Francisco` | `Chácara São Francisco.` |
# > | 4.749 | `Área Faz` | `Área Faz. Santa Terezinha` |
# > | 4.755 | `Fazenda S` | `Fazenda S. Raimundo` |
# > | 5.099 | `Área LOTE 32 – P.A` | `Área LOTE 32 – P.A. VALE DO JORDÃO` |
# >
# > **Zero casos em que ela tenha protegido o nome de prosa que viesse depois.**
# > `Faz.`, `S.`, `P.A.` e `LT.` são abreviaturas, e neste livro elas são a
# > regra: o nome do imóvel vem abreviado porque quem escriturava economizava
# > tinta. A frase que a regra queria cortar já é cortada por `com`, `situad`,
# > `medindo`, `objeto` e as outras — e a medição provou que era só isso:
# > **regra sem caso em que ganha e sete em que perde não é zelo, é dano**.
# >
# > O que sobra de aparência de resto é o ponto final solto (`Área Santa Rosa.`),
# > e esse o `_corta` tira.
# >
# > **E A FRONTEIRA `de área de` ENTROU NO MESMO DIA, MEDIDA.** Ela não veio de
# > ideia: veio de **seis** fichas em que o corte caía no meio de um número com
# > vírgula — `Fazenda Engenho Velho de área de 60` (de «…de área de 60,1394 ha»)
# > e cinco irmãs. O `_corta` fez o trabalho dele (parou na vírgula) e deixou o
# > pedaço da frase para trás; a fronteira tira o pedaço. Rodado nas 1.551:
# > **seis melhoram, nenhuma perde nada**.
# >
# > **E A FRONTEIRA DE LUGAR ENTROU EM 15/09/2026, E ELA É OUTRA COISA.** «Rua
# > São Francisco **na Vila** João Alberto» e «Avenida Principal **do povoado**
# > Lageado Novo» são **prosa** dentro do nome, e o logradouro ia ao índice com
# > ela. As duas entraram com a **preposição colada** (`no povoado`, `na vila`,
# > `do povoado`), que é o que impede o corte no meio de um nome próprio —
# > `Vila` sozinho cortaria «Rua Vila Nova», que é o nome da rua.
# >
# > **E A PRIMEIRA VERSÃO DESTA RÉGUA SÓ TINHA `no` E `na` — eu escrevi no
# > comentário uma lista maior que a do código.** Quem pegou foi a ficha **530**,
# > que continuava publicando «Avenida Principal do povoado Lageado Novo»: o
# > corte era em `do povoado`, e o `do` não estava lá. Medido nas 1.551 com as
# > duas réguas: com `do`/`da` **uma** ficha melhora (a 530), **nenhuma perde**,
# > e o `pode_enviar` não muda (1.379 nas duas). Uma terceira régua, mais larga
# > ainda (`dos`, `das`, `num`, `numa`, `deste`, `desta`, `neste`, `nesta`),
# > toca **a mesma e única ficha** — e as que sobravam já cortavam sozinhas,
# > três linhas acima. Não se adota o que não compra nada.
# >
# > **E o lugar não some: ele já estava no bairro, e isso se mediu.** Nas três
# > fichas tocadas, o `bairro_do_texto` publica `LAGEADO NOVO`, `LAGEADO II` e
# > `JOÃO ALBERTO` — tirados de «POVOADO Lageado Novo», «POVOADO Lageado II» e
# > «VILA João Alberto» —, com e sem o corte do logradouro. O que o corte tira é
# > a prosa repetida, e não a informação.
FIM_DO_NOME = re.compile(
    r"(?i)\s*(?:[,;]|\bcom\b|\be\s+com\b|\bque\b|\be\s+fundos?\b|"
    r"\bno\s+v[ée]rtice|\bdali\b|"
    r"\bat[ée]\s+(?:a|o|as|os|sua|seu)\b|\b[àa]\s+margem\b|"
    r"\bsituad|\blocalizad|\bmedindo\b|\bde\s+[áa]rea\b|"
    r"\bdeste\b|\bdesta\b|\bneste\b|\bnesta\b|\bno\s+munic|\bem\s+munic|"
    r"\b(?:no|do|em)\s+povoado|\b(?:no|do|em)\s+distrito|"
    r"\b(?:na|da|em)\s+vila|\b(?:no|do|em)\s+bairro|"
    r"\b(?:no|do|em)\s+loteamento|\b(?:na|da|em)\s+zona|"
    r"\b(?:no|do|em)\s+n[úu]cleo|"
    r"\bmatr[íi]cula|\bregistrad|\bobjeto\b|\badquirid|\bpertencente|"
    r"\bj[áa]\s+referid|\bsupracitad|\bretro\s+mencionad)"
)

# **A FICHA É LIDA SEM AS QUEBRAS DE LINHA, E POR ISSO O RÓTULO PASSA A CORTAR.**
# Medido em 15/09/2026, e as duas metades da medição se explicam uma à outra:
#
# | | |
# |---|---|
# | `FAZENDA\nTRES PORTEIRAS` (5131) | o `\n` **cortava o nome no meio** e sobrava `FAZENDA` |
# | `FAZENDA LEÔNCIO.\nLOCALIZAÇÃO :` (3399) | o `\n` **protegia o nome**, e o resto era rótulo |
#
# **Vinte e três fichas dependem de qual das duas coisas o `\n` faz**, e em
# vinte e uma ele protege: quem lê a ficha linha a linha não quer `LOCALIZAÇÃO`
# no fim do nome do imóvel. Tirar as quebras e deixar o `\n` como fronteira
# resolveria duas e estragaria vinte e uma.
#
# A saída é trocar uma fronteira por outra: **ler tudo como um parágrafo só**
# (o `\n` é do OCR, não do nome) **e fechar o valor onde a ficha escreve o
# rótulo seguinte** — `LOCALIZAÇÃO :`, `ORIGEM :`, `TÍTULO :`.
#
# **A lista é medida**: os rótulos em maiúsculas com dois-pontos das 1.551
# fichas, contados um a um — `VALOR` em 3.036, `ADQUIRENTE` em 1.602, `IMÓVEL`
# em 1.511, `TÍTULO` em 1.495, `FORMA DO TÍTULO` em 1.457. **E o dois-pontos é
# obrigatório no padrão**, porque `DATA` é rótulo em 765 fichas e é nome de
# imóvel em outras (`DATA TROIA`, `FAZENDA GRANDE DA DATA`) — sem ele, o corte
# comeria o nome de quem tem «data» dentro.
FIM_NO_ROTULO = re.compile(
    r"(?i)\b(?:VALOR|ADQUIRENTE[S]?|TRANSMITENTE[S]?|PROPRIET[ÁA]RIO[S]?|"
    r"IM[ÓO]VEL(?:\s+VENDIDO)?|T[ÍI]TULO(?:\s+AQUISITIVO)?|FORMA\s+DO\s+T[ÍI]TULO|"
    r"LOCALIZA[ÇC][ÃA]O|ORIGEM|MATR[ÍI]CULA|DESCRI[ÇC][ÃA]O|LIVRO|FOLHA|"
    r"CREDOR|DEVEDOR|CNS|CEP|CPF|CNPJ|CFT|FERC|UTM|NIRF|[ÁA]REA)\s*:")

# **«S/N» É O CAMPO `numero` DIZENDO QUE NÃO TEM NÚMERO — não é nome de rua.**
# A ficha desta casa escreve `Rua Fabrício Ferraz s/nº`, e o `s/nº` ficava
# dentro do logradouro: o ONR tem campo próprio para o número, e mandar «s/nº»
# colado no nome da rua é sujeira no índice nacional. Medido em 15/09/2026
# sobre as 1.515 propostas: **11** terminam assim — e as onze passam a terminar
# onde a rua termina (`Rua Fabrício Ferraz`), com uma delas (mat 4789) largando
# junto o «- Bairro Vila Lobão» que vinha atrás.
#
# E uma **esvazia**: a mat 3641 diz `Rua s/nº- Vila Angical- Cidade Exemplo/MA`,
# isto é, a rua sem nome nenhum. Sem o corte sairia uma rua chamada «S/Nº», que
# o índice leria como nome; com o corte sobra «Rua», que é só o tipo, e a
# proposta cai fora — que é o certo para uma rua que a ficha não nomeia.
FIM_SEM_NUMERO = re.compile(
    r"(?i)\s*s\s*/\s*n\s*[º°o.]{0,2}\b|\s+sem\s+n[úu]mero\b"
)

# **O HÍFEN NÃO É FRONTEIRA — a ÂNCORA é.** A tentação é cortar o nome no
# primeiro `–`, e a medição desmentiu: nesta ficha o travessão separa qualquer
# coisa. Dos 45 cortes que ele faria, **33 são perda** — `Área PA SÃO JOSÉ / 025
# - CHÁCARA ALTO DO CAJU` (18 fichas: o nome do lote é justamente o que vem
# depois do hífen), `FAZENDA SÃO JOSÉ – LT.217 – GL. DIVISA`, `FAZENDA SERRA DA
# QUIRIBA – PARTE 1` e `– PARTE 2` (duas matrículas do mesmo imóvel ficariam
# com o mesmo nome no índice).
#
# O que o hífen separa e **é** prova de que o nome acabou: as palavras deste
# padrão — bairro, município, microregião, distrito, zona, comarca, povoado,
# lado, situado, localizado. Elas não nomeiam imóvel nenhum, e depois delas vem
# a explicação da ficha. São **4** as que se corrigem, medidas uma a uma.
FIM_APOS_ANCORA = re.compile(
    r"(?i)\s*[–—-]\s+(?:bairro|munic[íi]pio|microregi[ãa]o|micro-regi[ãa]o|"
    r"distrito|zona|comarca|povoado|lado|situad[oa]|localizad[oa])\b"
)

# As aspas que a ficha usa — as retas e as curvas. Sem as curvas, os nomes
# entre “…” sairiam com os sinais dentro.
_ASPAS = "\"'“”‘’"

# **A aspa que DELIMITA, e não a que é do nome.** Ela encosta em espaço ou na
# ponta; o apóstrofo de `Grota D’Anta` tem letra dos dois lados e fica de fora
# por construção. Medido: das 27 aspas que sobrevivem nos nomes, **26 são
# apóstrofo legítimo** e uma é o `”` solto da ficha 3972.
_ASPA_SOLTA = re.compile(r"(?:(?<=\s)|^)[\"'“”‘’]+|[\"'“”‘’]+(?=\s|$)")

# **A FICHA DOBRA A ASPA, E O EXTRATOR SÓ CONHECIA A SIMPLES.** Medido em
# 15/09/2026 sobre as 1.551 fichas: são **239 corridas de duas ou mais aspas**, e
# nas formas que o OCR desta casa usa —
#
# | forma | fichas | exemplo |
# |---|---|---|
# | `‘‘NOME’’`   | 11 | `sita na data ‘‘Fazenda Grande’’` (3558) |
# | `‘’ NOME ‘’` | 15 | `fazenda ‘’ Guara ‘’` (3605) |
# | `NOME’’`     |  1 | `Fazenda Grande’’` (3558) |
# | `““NOME””`   |  2 | — |
#
# Sem esta passada, `_recorta_aspas` não reconhece a abertura — ela procura
# `"`, `“` ou `'` —, e **o nome que está ali dentro não é lido por ninguém**:
# é a diferença entre a 3558 entrar com «Fazenda Grande» ou ficar sem
# logradouro nenhum. Não é enfeite de leitura: é o nome do imóvel no índice
# nacional.
#
# **A RÉGUA É A VIZINHANÇA, E ELA FOI MEDIDA:** das 239 corridas, **238 têm um
# caractere que não é letra encostado de pelo menos um lado** — e é isso que
# separa a aspa que delimita do apóstrofo que é do nome. `D’Anta` tem letra dos
# dois lados e **fica**; `Grande’’` tem espaço depois e **vira aspa canônica**.
# A única corrida entre letras dos dois lados fica como está, porque o apóstrofo
# do nome vale mais que a citação de uma ficha.
#
# **E é UMA passada só, com uma aspa de cada vez** — a `‘` sozinha entra na
# mesma régua, porque as 37 dela também abrem citação (`‘Arraias”`). Duas
# substituições encadeadas sobre o mesmo texto não servem: a segunda lê a string
# já mexida com os índices da primeira, e a corrida de duas casas vira uma — o
# vizinho que a segunda consulta deixa de ser o do nome.
_ASPA_QUALQUER = re.compile(r"[\"'“”‘’]+")


def _aspas_canonicas(txt: str) -> str:
    """A aspa que **delimita** vira `"`; o apóstrofo que é do nome fica.

    É passada no texto antes de qualquer forma procurar o nome, e existe porque
    a ficha dobra a aspa: `fazenda ‘’ Guara ‘’`, `‘‘Monte Alegre’’` — e sem ela
    essas fichas não têm nome para propor. Ver [`_ASPA_QUALQUER`] para a medição
    inteira.
    """
    def troca(m: re.Match) -> str:
        antes = txt[m.start() - 1] if m.start() else " "
        depois = txt[m.end()] if m.end() < len(txt) else " "
        if antes.isalpha() and depois.isalpha():
            return m.group(0)
        return '"'

    return _ASPA_QUALQUER.sub(troca, txt)

PADROES_DO_NOME: tuple[tuple[str, re.Pattern], ...] = (
    # 1. O CAMPO ROTULADO — é a forma das fichas ESTRUTURADAS.
    #    `DENOMINAÇÃO : "PA NOVO HORIZONTE-LOTE 025" LOCALIZAÇÃO : ZONA RURAL`
    ("campo",
     re.compile(r"(?i)\bDENOMINA[ÇC][ÃA]O\s*[:\-–]\s*(.{2,140})")),
    # 2. A FRASE CLÁSSICA — a mais comum nos rurais do acervo.
    #    `denominada Fazenda "Leôncio", com área de...`
    #
    # > **E O «DENOMINAÇÃO DE» FICAVA SEM NOME, em 13 fichas.** A expressão era
    # > `denomina(?:da|do)?\s+(.…)`, que casa o «denomina» de «denominação» e
    # > entregava `ção de Grota D'Anta` ao corte — o `_corta` parava em «de» e
    # > a proposta dizia que a ficha não nomeia o imóvel, **e ela nomeia**:
    # > «com a denominação de Grota D'Anta». Agora o `ção` entra na alternativa
    # > e o `de` de ligação é opcional.
    ("denominada",
     re.compile(r"(?i)\bdenomina(?:da|do|[çc][ãa]o)?\s+(?:de\s+)?(.{2,140})")),
    # 3. O LUGAR ENTRE ASPAS — a forma antiga, sem `denominada`.
    #    `NO LUGAR "CAMPO ALEGRE"`, `NA DATA "FAZENDA GRANDE"`
    #
    #    **E AS ASPAS PODEM VIR EM VOLTA DO TIPO, e não do nome** — medido na
    #    matrícula 4003: `“FAZENDA ALTO BONITO”, DATA TROIA, situado na zona
    #    rural`. A primeira versão só entendia `FAZENDA "NOME"`, e ali as
    #    aspas estão ANTES do tipo: sem a segunda alternativa, quem pegava a
    #    frase era o `lugar_solto`, que devolvia `ALTO BONITO` — o tipo
    #    «FAZENDA» perdido e «Alto» lido como tipo (código 5 do catálogo), de
    #    modo que o logradouro publicado seria «BONITO».
    ("lugar",
     re.compile(r"(?i)\b(?:LUGAR|DATA|POVOADO|S[ÍI]TIO|FAZENDA|CH[ÁA]CARA|"
                r"GLEBA|POSSE|QUINH[ÃA]O)\s+[\"“']([^\"”']{2,90})[\"”']"
                r"|[\"“']\s*((?:LUGAR|DATA|POVOADO|S[ÍI]TIO|FAZENDA|"
                r"CH[ÁA]CARA|GLEBA|POSSE|QUINH[ÃA]O)\s+[^\"”']{2,90})[\"”']")),
    # 4. A FAZENDA SEM ASPAS — a de matrícula 2: `na Fazenda Angical`.
    ("na_fazenda",
     re.compile(r"(?i)\b(?:na|da)\s+(FAZENDA|S[ÍI]TIO|CH[ÁA]CARA|COL[ÔO]NIA|"
                r"CAMPO)\s+([A-ZÀ-Ú][^\n,;.]{2,60})")),
    # 5. O LUGAR SEM ASPAS — **medido em 48 fichas**, e é a quinta forma que
    #    faltava: `no lugar Grota D'Anta`, `na data Barra do Arraias II`,
    #    `na posse Taboca`, `nas terras de Santa Rita` e `imóvel Fazenda
    #    Vitoria III`. Sem ela, essas 48 não tinham o que propor — e o nome do
    #    imóvel é o único campo do ONR que não se deduz de mais nada.
    ("lugar_solto",
     re.compile(r"(?i)\b(?:no|do|ao)\s+LUGAR\s+([A-ZÀ-Ú][^\n,;.]{2,60})"
                r"|\b(?:na|da)\s+DATA\s+([A-ZÀ-Ú][^\n,;.]{2,60})"
                r"|\b(?:na|da)\s+POSSE\s+([A-ZÀ-Ú][^\n,;.]{2,60})"
                r"|\b(?:na|da)\s+GLEBA\s+([A-ZÀ-Ú][^\n,;.]{2,60})"
                r"|\bnas\s+TERRAS\s+DE\s+([A-ZÀ-Ú][^\n,;.]{2,60})"
                r"|\bIM[ÓO]VEL\s+([A-ZÀ-Ú][^\n,;.]{2,60})"
                r"|\b((?:FAZENDA|S[ÍI]TIO|CH[ÁA]CARA)\s+[A-ZÀ-Ú][^\n,;.]{2,60})")),
)

# **O CAMPO ROTULADO TAMBÉM RECEBE PROSA, e é preciso descartá-la.** Medido: a
# matrícula 94 traz `DENOMINAÇÃO : conforme o registro anterior, imóvel sem
# denominação`, e o valor saía inteiro para a ficha — «conforme o registro
# anterior…» iria como nome do imóvel no índice nacional. São as primeiras
# palavras com que uma frase começa, e não com que um nome de imóvel começa.
#
# > **E `uma` FALTAVA — medido em 15/09/2026, e o estrago era o pior possível:
# > o nome certo era ENGOLIDO pelo errado.** As matrículas 3.754 e 4.089 dizem,
# > na mesma frase e nesta ordem:
# >
# > `Denominação: Uma gleba de terras com a área de 45,8531 ha (…); denominada
# > “FAZENDA MIRANTE” da data “FAZENDA GRANDE” deste município`
# >
# > A primeira forma é a do campo rotulado e a segunda é a do `denominada` — e
# > **o campo rotulado vem primeiro na lista de formas, de propósito**, porque
# > em todo o resto do livro ele é o declarado pela casa. Aqui o rotulado traz
# > uma *descrição* e o nome de verdade vem depois do ponto e vírgula. Sem `uma`
# > na lista, o extrator parava na primeira forma e propunha «Uma gleba de
# > terras» — **e com `uma` ele descarta a descrição, a forma seguinte casa, e
# > saem `FAZENDA MIRANTE` e `FAZENDA BELA VISTA / PARTE 4`, que é o que está
# > escrito no livro.**
# >
# > É a regra da casa outra vez: em `PROSA_NO_CAMPO` a palavra é a **primeira**
# > do valor, e nenhum nome de imóvel começa por artigo indefinido.
PROSA_NO_CAMPO: frozenset[str] = frozenset((
    "conforme", "consta", "sem", "nao", "acima", "abaixo", "mesmo", "mesma",
    "referido", "referida", "registrado", "registrada", "descrito",
    "descrita", "mencionado", "mencionada", "supracitado", "retro", "todos",
    "todas", "todo", "toda", "este", "esta", "esse", "essa", "isso", "do",
    "da", "dos", "das", "de", "em", "no", "na", "nos", "nas", "para", "por",
    "com", "que", "qual", "quais", "quando", "onde", "cujo", "cuja", "e", "ou",
    "um", "uma", "uns", "umas",
))

# Um nome de imóvel é curto. Doze palavras já é uma frase inteira, e medido: o
# campo rotulado da matrícula 3075 devolvia 16 palavras, terminando em
# «FAZENDA PAULO (KM.)» — a sede e o quilômetro da estrada não são o nome.
MAXIMO_DE_PALAVRAS = 12

# AS PALAVRAS QUE **NÃO SÃO** O NOME, e sim o tipo dele. Elas não se descartam:
# elas vão à frente do nome, porque é assim que `partir_logradouro` sabe de que
# tipo é o logradouro.
TIPOS_DA_CASA: tuple[str, ...] = (
    "fazenda", "sitio", "chacara", "colonia", "campo", "ilha", "gleba", "posse",
    "quinhão", "quinhao", "data", "lote", "loteamento", "area", "área",
    "parte de terras", "povoado", "assentamento", "terreno", "terras",
)

# O QUE A FILA DO ONR NÃO TEM, e por isso vai como «Área» — medido no catálogo
# dele: `gleba`, `posse`, `quinhão`, `data`, `povoado` e `assentamento` **não
# existem** em `TIPOS_DE_LOGRADOURO`. Ver `TIPO_DA_GLEBA`.
TERMOS_DE_GLEBA: tuple[str, ...] = (
    "gleba", "posse", "quinhão", "quinhao", "data", "povoado",
    "assentamento", "parte de terras", "terras", "área", "area",
)

# 472 = «Área» no catálogo do ONR, e é a decisão do oficial: o que a casa chama
# de gleba, quinhão, posse ou data vai como «Área», **com o nome no logradouro**
# — «Área Barra do Arraias II». O nome não se perde, e o tipo é um dos 129.
TIPO_DA_GLEBA = 472


def nome_do_tipo(codigo: int) -> str:
    """O nome do tipo, **com o glifo do contrato consertado**.

    O contrato do ONR escreve «**Ý**rea» e «**Ý**rea Especial» — `Ý` (U+00DD,
    Y com agudo) no lugar de `Á` (U+00C1). Medido: são **2 das 129** entradas,
    e as duas são estas, que é justamente a que esta casa usa.

    Gravar «Ýrea Barra do Arraias II» na ficha da matrícula poria um caractere
    que não existe em português no lugar onde a casa lê o endereço — e o
    conserto tem de ser aqui, onde o glifo sairia para os NOSSOS dados. O
    catálogo continua sendo transcrito do contrato como está, e há teste que
    guarda as duas coisas: o glifo torto na transcrição, e o nome certo aqui.
    """
    return API.TIPOS_DE_LOGRADOURO.get(codigo, "").replace("Ý", "Á")


def _tira_aspas(txt: str) -> str:
    """Tira as aspas — e **só as que delimitam**, nunca o apóstrofo do nome.

    Medido em 15/09/2026 sobre as 1.551 fichas: **27 nomes** têm aspa dentro, e
    **26 delas são apóstrofo legítimo** — `Área Grota D’Anta` (oito fichas),
    `Área Olho D’água`, `Fazenda Ossos D’Anta`, `Chácara D’de Dá`. Tirar toda
    aspa estragaria vinte e seis nomes de lugar para consertar um.

    A régua é a vizinhança: **aspa que encosta em espaço (ou na ponta) é
    delimitador e sai; aspa entre letras é do nome e fica.** O caso que a
    obrigou: a 3972 traz `Avenida Principal” do povoado Lageado Novo` — o `”`
    fecha uma aspa que a ficha nunca abriu, e sem esta régua ele ia impresso no
    índice nacional. E a 4651, `CHÁCARA ‘LUA DE CRISTAL”`, com as duas trocadas
    (abre com `‘` e fecha com `”`), que a limpeza de ponta não pegava porque só
    olhava a primeira e a última casa da string inteira.
    """
    txt = _ASPA_SOLTA.sub("", txt)
    return txt.strip().strip(_ASPAS).strip()


def _corta(txt: str) -> str:
    """Corta o nome onde ele acaba — na primeira fronteira que aparecer.

    E **tira o ponto final solto**, que é o que sobra quando o teor fecha a
    frase logo depois do nome: «Área Santa Rosa.» vira «Área Santa Rosa». Não é
    a regra do ponto de volta — ela cortava no ponto do MEIO e levava junto
    `Faz.`, `S.` e `LT.`; esta só limpa a última casa, e o que vem antes fica.

    **E corta no RÓTULO da ficha** (`LOCALIZAÇÃO :`, `ORIGEM :`) — que é o
    segundo dos dois cortes, e existe por causa do primeiro. Ver
    `FIM_NO_ROTULO`: a partir do momento em que o texto é lido **sem as quebras
    de linha**, o `\\n` deixa de ser a fronteira que era, e é o rótulo que passa
    a fechar o valor.

    **E corta no `s/n` e na âncora do travessão** — as duas fronteiras medidas
    em 15/09/2026, com o preço de cada uma: ver `FIM_SEM_NUMERO` e
    `FIM_APOS_ANCORA`. Aqui valem para todo campo de nome (via, imóvel, bairro),
    que é onde elas foram medidas.
    """
    cortes = [m.start() for m in (FIM_DO_NOME.search(txt), FIM_NO_ROTULO.search(txt),
                                  FIM_SEM_NUMERO.search(txt), FIM_APOS_ANCORA.search(txt)) if m]
    return (txt[:min(cortes)] if cortes else txt).strip().rstrip(".,;:")


def _sem_repetir(txt: str) -> str:
    """«Fazenda FAZENDA SÃO JOSÉ» → «Fazenda SÃO JOSÉ».

    Acontece quando o tipo vem antes das aspas e o nome de dentro também o
    traz — medido na matrícula de «Fazenda “FAZENDA SÃO JOSÉ – LT.217”».
    """
    palavras = txt.split()
    if len(palavras) >= 2 and API.sem_acento(palavras[0]) == API.sem_acento(palavras[1]):
        return " ".join(palavras[1:])
    return txt


def _recorta_aspas(bruto: str) -> str | None:
    """Se o nome vem entre aspas, ele acaba na aspa que fecha.

    **E se não houver aspa que feche, ele vai até o fim** — medido em
    «denominada “LOTE 32 – P.A. VALE DO JORDÃO», que a ficha cortou no meio.
    """
    for i, c in enumerate(bruto):
        if c in "\"“'":
            abre = c
            fecha = {"\"": "\"", "“": "”", "'": "'"}[abre]
            resto = bruto[i + 1:]
            fim = resto.find(fecha)
            dentro = resto if fim < 0 else resto[:fim]
            return (bruto[:i] + " " + dentro).strip()
    return None


def _primeiro_grupo(m: re.Match) -> str:
    """O primeiro grupo que casou — a forma de `lugar_solto`, que tem oito."""
    for g in m.groups():
        if g:
            return g
    return ""


# **O RÓTULO VEM ANTES DO NOME, E NÃO É O NOME.** Medido: `denominação do
# imóvel rural: Fazenda Três Porteiras` — o valor está DEPOIS dos dois-pontos,
# e o que está antes é o rótulo do campo. Já `Fazenda Nova Jerusalém: Município:
# Montes` é o contrário: o nome veio primeiro e o OCR colou o campo seguinte.
# Quem decide de que lado está o nome é a palavra de antes, e é para isso que
# esta lista existe.
ROTULOS_ANTES_DO_NOME: tuple[str, ...] = (
    "do imovel rural", "do imovel", "da propriedade", "do terreno", "da gleba",
    "do bem", "do predio", "do lote", "da area", "do sitio", "da fazenda",
    "da chacara", "rural", "imovel", "denominacao", "denominado", "denominada",
)


def _tira_o_rotulo(nome: str) -> str:
    """O rótulo fora, e o nome do lado certo dos dois-pontos.

    Os dois casos medidos são opostos, e por isso a régua pergunta antes de
    cortar: se o que vem antes dos dois-pontos é **rótulo** («do imóvel
    rural», «denominação»), o nome é o de depois; se não é, o nome veio
    primeiro e o de depois é outro campo da ficha («Município: Montes»).
    """
    for _ in range(3):
        antes, sep, depois = nome.partition(":")
        if not sep:
            return nome.strip(" -–—·,")
        limpo = API.sem_acento(antes).strip()
        if any(limpo.endswith(r) for r in ROTULOS_ANTES_DO_NOME):
            nome = depois
        else:
            nome = antes
    return nome.strip(" -–—·,")


def _limpa_o_campo(nome: str) -> str:
    """O valor do `DENOMINAÇÃO :`, pronto — prosa fora, e o parêntese fora.

    Medido: `DENOMINAÇÃO : conforme o registro anterior, imóvel sem
    denominação` (matrícula 94) e `DENOMINAÇÃO : FAZENDA SANTA ROSA II …
    (KM.06, SENTIDO BELÉM-BRASÍLIA)` (matrícula 3075). O primeiro é frase e
    não é nome; o segundo é nome, e o que vem depois do parêntese é **onde a
    fazenda fica**, não como ela se chama.

    **E o `_corta` entra aqui, porque a forma `campo` era a única que não o
    tinha** — medido em 3.754: `DENOMINAÇÃO : Uma gleba de terras com a área de
    45,8531 ha (quarenta e cinco hectares…)` saía como nome, com a prosa do meio
    dentro, porque o parêntese era o único corte. Rodado nas 1.551: a fronteira
    muda **seis** fichas, e nas seis o que sai é prosa (`de área de 60`,
    `com a área de 45,8531 ha`). **O corte é o mesmo dos outros nomes**: o
    rótulo é uma forma de achar o valor, não uma licença para levar a frase.
    """
    if nome.split() and API.sem_acento(nome.split()[0]) in PROSA_NO_CAMPO:
        return ""
    return _corta(re.split(r"\s*[\(\[]", nome)[0]).strip(" -–—·,")


def nome_do_imovel(texto: str) -> dict | None:
    """O nome do imóvel, e de qual das cinco formas ele saiu.

    Devolve `{"nome", "forma", "de_onde", "confianca"}` ou `None`. **A forma
    fica gravada** porque a confiança depende dela: o campo rotulado é o
    declarado pela casa; o lugar sem aspas é a mais fraca das cinco.

    **E O TEXTO É LIDO COMO UM PARÁGRAFO SÓ** — as quebras de linha fora. Elas
    são do OCR, e não do nome: em **vinte e três** fichas a resposta depende de
    qual das duas coisas o `\\n` faz, e em **vinte e uma** ele corta o nome no
    meio. Medido em 15/09/2026 — as duas que ele ajuda (5131 e 5132,
    `FAZENDA\\n\\nTRES PORTEIRAS`) são o preço de acertar as vinte e uma, e
    **essas duas passam a acertar também**, porque quem fecha o valor agora é o
    rótulo seguinte ([`FIM_NO_ROTULO`]) e não o fim da linha.

    O `de_onde` sai da mesma forma: a frase de que o nome veio, com as quebras
    de linha já pastadas.
    """
    if not texto:
        return None
    texto = _aspas_canonicas(re.sub(r"\s+", " ", texto))
    for forma, padrao in PADROES_DO_NOME:
        m = padrao.search(texto)
        if not m:
            continue
        if forma == "na_fazenda":
            nome = f"{m.group(1).title()} {m.group(2)}"
        else:
            bruto = _primeiro_grupo(m)
            nome = _recorta_aspas(bruto) or _corta(bruto)
        nome = _sem_repetir(_tira_aspas(nome if forma == "campo" else _corta(nome)))
        nome = re.sub(r"\s+", " ", nome).strip(" -–—·, ")
        if forma == "campo":
            nome = _limpa_o_campo(nome)
        # **O RÓTULO SAI DEPOIS, E PARA TODAS AS FORMAS** — não só para o campo
        # rotulado. Medido na 3976: `denominação do imóvel rural: Fazenda Três`
        # entrava como nome a frase inteira, e o logradouro publicado no índice
        # nacional seria «Área do imóvel rural: Fazenda Três».
        nome = _tira_o_rotulo(nome)
        if len(nome) < 3 or not re.search(r"[A-Za-zÀ-Ú]", nome):
            continue
        if len(nome.split()) > MAXIMO_DE_PALAVRAS:
            continue
        confianca = {"campo": "alta", "denominada": "alta", "lugar": "media",
                     "na_fazenda": "baixa", "lugar_solto": "baixa"}[forma]
        return {"nome": nome, "forma": forma, "de_onde": m.group(0)[:160],
                "confianca": confianca}
    return None


def logradouro_do_nome(nome: str) -> dict:
    """O nome vira `tipoLogradouro` + `logradouro`, como o ONR os quer.

    **Não se inventa tipo.** Se o nome já começa por um dos 129 do contrato
    («Fazenda Leôncio», «Sítio Novo», «Quadra 09»), ele é o tipo. Se não
    começa, ele é uma área — e vai com «Área» à frente, que é o que a casa
    chama de gleba, quinhão, posse e data.

    **E `texto` é o que vai para a FICHA, com o tipo na frente.** O
    `logradouro` sozinho não serve para gravar: medido no ensaio contra a
    cópia da produção, **19 das 33 confirmadas foram recusadas no envio**
    porque a ficha recebeu «São Francisco» onde o nome era «Fazenda São
    Francisco» — o tipo tinha sido consumido na leitura e não voltou, e
    `partir_logradouro` não acha tipo em «São Francisco». Quem lê o teor
    precisa do tipo; quem publica o logradouro também.
    """
    cru = (nome or "").strip()
    if not cru:
        return {"tipo_codigo": None, "tipo_nome": "", "logradouro": "",
                "texto": "", "acrescentou": False}
    partido = partir_logradouro(cru)
    if partido["tipo_codigo"] is not None:
        return {**partido, "texto": cru, "acrescentou": False}
    tipo = nome_do_tipo(TIPO_DA_GLEBA)
    partido = partir_logradouro(f"{tipo} {cru}")
    if partido["tipo_codigo"] is not None:
        return {**partido, "texto": f"{tipo} {cru}", "acrescentou": True}
    return {**partido, "texto": cru, "acrescentou": False}


def so_o_tipo(txt: str) -> bool:
    """O que sobrou é **só o tipo** — «Estrada», «Área» —, e isso não é nome.

    **O CORTE DA PROSA DEIXA O TIPO SOZINHO, E TIPO SOZINHO NÃO VAI AO ÍNDICE.**
    Medido em 15/09/2026, depois de o `FIM_DO_NOME` passar a cortar a frase
    relativa: das **21** propostas que encolheram, **doze** ficaram só com o
    tipo — `Estrada` em seis, `Rua`, `Beco` e `Área` nas outras cinco —, e
    **três delas iam prontas** (`pode_enviar=1`). `Área` sozinho no índice
    nacional é linha que não diz nada e ocupa o lugar do nome que ninguém
    escreveu.

    **A RÉGUA É O CATÁLOGO, E NÃO UMA LISTA ESCRITA AQUI.** O que se pergunta é
    se o texto inteiro é o nome de um tipo do ONR — `estrada`, `rua`, `beco`,
    `avenida`, `area`, `fazenda` —, pela mesma tabela que o envio usa para achar
    o código. Lista escrita neste arquivo envelheceria no dia em que o contrato
    ganhasse um tipo.

    **O campo volta para `faltam`**, que é a verdade: este teor fala de uma
    estrada e não diz o nome dela. Quem sabe o nome é quem lê a ficha.
    """
    n = API.sem_acento((txt or "").strip())
    if not n:
        return True
    return n in API.CODIGO_DO_LOGRADOURO or n in API.APELIDOS_DO_LOGRADOURO


def tira_o_logradouro_que_nao_e_nome(campos: dict, de_onde: dict,
                                     avisos: list) -> bool:
    """Tira o logradouro que é só o tipo, e diz por quê. Devolve se tirou.

    **AS DUAS PONTAS DO `if letra` PRECISAM DA MESMA RÉGUA.** O urbano e o rural
    chegam ao logradouro por caminhos diferentes — a via, a quadra, o nome do
    imóvel —, e escrever este aviso duas vezes daria duas versões dele,
    divergindo no primeiro conserto. Aqui é uma vez só.
    """
    if "logradouro" not in campos or not so_o_tipo(campos["logradouro"]):
        return False
    avisos.append(
        f"O teor fala de «{campos['logradouro']}» e **não diz o nome** — tipo "
        f"sozinho não vai ao índice nacional, que é a lista que o país consulta "
        f"para saber de quem é o imóvel. Confira a ficha e escreva o nome, ou "
        f"descarte esta leitura.")
    campos.pop("logradouro")
    de_onde.pop("logradouro", None)
    return True


# ═══════════════════════════════════════════════════════════════════════
# 4. A ÁREA — e a unidade que a ficha escreve de três formas
# ═══════════════════════════════════════════════════════════════════════

# `Área: 231,00,00 Há` · `com área de 8.435,26 m²` · `área de 230 ha`
# O HÍFEN ENTRE O NÚMERO E A UNIDADE — «25.434,50-M²», matrícula 1926, achado em
# 11/10/2026 ao gerar o XML do Indicador Real: sem o `-?` a unidade não casava,
# o número caía no hectare, e a ficha de 2,5 ha ia ao índice com 25.434 ha.
AREA_NO_TEXTO = re.compile(
    r"(?i)\b[ÁA]REA\b[^\n\d]{0,30}?([\d][\d.,\s]{0,18}\d)"
    r"\s*-?\s*(m[²2]|metros?\s+quadrados?|ha\b|h[áa]\b|hectares?\b|ares?\b|a\b)?"
)

# A CONVERSÃO NÃO MORA MAIS AQUI — ela subiu para `onr_api.area_em_metros` em
# 15/09/2026, quando o `montar_indicador` passou a precisar dela. **Ela é a forma
# do contrato** (metros quadrados), e este módulo **importa `partir_logradouro`
# de `ri_onr_central`**: deixada aqui, os dois passariam a depender um do outro.
# O nome continua valendo neste arquivo pela linha de `import` lá no alto — **uma
# definição só**, e é a mesma que o indicador real usa.


# A UNIDADE ESCRITA NO TEOR, EM TRÊS FORMAS — e nenhuma delas é a coluna.
#
# A sigla colada no número é a forma comum; a **palavra por extenso** aparece
# entre parênteses logo depois («89,43,75 (oitenta e nove hectares…)») e o
# **rótulo antes do número** aparece nas fichas do INCRA/SNCR («área total (ha)
# do imóvel rural: 84,7438»). Medido em 16/09/2026 nas 1.982 fichas com teor.
_UNIDADE_EM_PALAVRA = re.compile(
    r"(?i)\b(hectares?|ha|h[áa]|has|metros?\s+quadrados?|alqueires?)\b")
_UNIDADE_NO_ROTULO = re.compile(r"(?i)\(\s*(ha|h[áa]|m\s*[²2]|hectares?)\s*\)")


def _a_unidade_escrita(texto: str, m: "re.Match") -> tuple[str, bool, str]:
    """`(unidade, escrita_no_teor, palavra)` — o que o TEOR diz da unidade.

    Devolve `("", False, "")` quando a ficha não escreve unidade nenhuma, que é
    o único caso em que a coluna responde. A `palavra` volta preenchida quando
    o teor escreve **alqueire**, que este módulo não converte (ver a docstring
    de [`area_do_texto`]).

    **AS TRÊS FORMAS, UMA POR FICHA REAL — 16/09/2026:**

    | a ficha | como ela escreve |
    |---|---|
    | 971 | `«35,00 há»` — a sigla colada no número |
    | 381 | `«89,43,75 (oitenta e nove hectares…)»` — a palavra, no parêntese |
    | 4010 | `«área total (ha) do imóvel rural: 84,7438»` — o rótulo, antes |

    A terceira é medida com uma ressalva que vale registrar: em 4010 o
    `(ha)` que a régua acha pertence à medida **anterior** da mesma lista do
    SNCR (`área total (ha) …; área liquida do imóvel: 84,7438`), e ali todas as
    medidas da lista estão em hectare. Foi assim que ela acertou — e é honesto
    dizer que acertou por isso, e não por ler o rótulo do próprio número. O
    caso contrário (cortar a busca no `;`) foi ensaiado e **dá 84 m² para uma
    fazenda de 84 ha**: não se aperta a régua sem uma ficha que a desminta.
    """
    direto = (m.group(2) or "").strip()
    if direto:
        # A FORMA ESCRITA VAI PARA A CITAÇÃO; CANÔNICA VAI PARA O CAMPO. A
        # ficha que escreve `metros quadrados` tem de sair com `m2` — é o que o
        # contrato conhece —, e a frase do `de_onde` continua citando o que
        # está no livro.
        return API.unidade_canonica(direto) or direto, True, ""
    # A frase do número, e só ela: parar antes do ponto-e-vírgula evita pegar a
    # unidade de outro parágrafo. **Vale o primeiro que aparece** — «quinhentos
    # metros quadrados, o que equivale a 0,05 hectares» fala de metro quadrado,
    # e procurar por hectares primeiro leria a equivalência como se fosse a
    # unidade da área.
    janela = re.split(r"[;\n]", texto[m.end():m.end() + 90])[0]
    achado = _UNIDADE_EM_PALAVRA.search(janela)
    if achado:
        letra = re.sub(r"\s+", " ", achado.group(1).lower())
        if letra.startswith("alqueire"):
            return "", True, "alqueire"
        return ("m2" if letra.startswith("metro") else "ha"), True, ""
    # O rótulo vem **antes do número**, e a busca vai de 40 caracteres antes da
    # palavra «área» até o próprio número: assim ele é achado tanto no meio da
    # frase do número («área total (ha) do imóvel rural: 84,7438») quanto no
    # começo dela. Vale o **último** da janela, que é o mais próximo — nas
    # listas do SNCR o `(ha)` do primeiro rótulo governa as medidas seguintes
    # (`área total (ha) …; área liquida do imóvel: 84,7438`), e é essa a
    # unidade que vale para a lista inteira. **O ensaio com o corte no
    # ponto-e-vírgula está registrado na docstring.**
    rotulos = _UNIDADE_NO_ROTULO.findall(
        texto[max(0, m.start() - 40):m.start(1)])
    if rotulos:
        letra = re.sub(r"\s+", "", rotulos[-1].lower())
        return ("m2" if letra in ("m2", "m²") else "ha"), True, ""
    return "", False, ""


def area_do_texto(texto: str, *, unidade_da_coluna: Any = None) -> dict | None:
    """A área como a **ficha** a escreve, com a frase de onde saiu.

    A ficha é a fonte: em `ri_matriculas.area_valor` há 14 formas diferentes de
    escrita e a unidade discorda do número em pelo menos um caso medido.

    **QUANDO A FICHA NÃO ESCREVE A UNIDADE, QUEM RESPONDE É A COLUNA** — e isto
    foi medido em 16/09/2026, depois de o conserto das tags inline (`<span>`)
    revelar a família. O bloco do loteamento Veronília diz, em **24 fichas**:

        «…com a área de 1.759,25.»

    — o número e mais nada. Sem unidade escrita, a régua antiga supunha
    hectare e o número subia multiplicado por 10.000: **17.592.500 m²** para um
    lote urbano de **1.759,25 m²**, indo para o índice que o país consulta para
    saber de quem é o imóvel. E a unidade estava escrita na casa o tempo todo:
    `ri_matriculas.area_unidade` diz **`m2`** nas 24. Não é suposição contra
    suposição: é ler o campo da casa. O número continua sendo o da ficha, que é
    o mais preciso (a coluna guarda `1759` e a ficha, `1.759,25`); o que vem da
    coluna é só a **unidade**, e o `de_onde` da proposta diz de onde cada
    metade veio.

    **MAS A UNIDADE TAMBÉM SE ESCREVE EM PALAVRA, E ISSO FOI MEDIDO DEPOIS.** A
    primeira versão desta régua só olhava a sigla colada no número, e por isso
    tratava como «sem unidade» três fichas que a escrevem por extenso — e a
    coluna delas diz outra coisa:

        mat 381:  «…com a área de 89,43,75 (oitenta e nove hectares, quarenta e
                   três ares e cinco centiares)…»      coluna: 89 **m2**
        mat 3326: «…com a área de 50,3259 (cinquenta hectares trinta e dois ares
                   e cinquenta e nove centiares)…»      coluna: 28 **m2**
        mat 4010: «…área total (ha) do imóvel rural: 84,7438…»  coluna: sem unidade

    Nelas o teor está certo e a coluna está errada — 89,43,75 é a **grafia do
    hectare** (hectares, ares e centiares, que é o que os parênteses escrevem) —,
    e seguir a coluna daria **89 m²** onde são **894.375 m²**. Por isso a ordem
    é: primeiro a unidade que o **teor** escreve — sigla, palavra ou o rótulo
    antes do número —, e só quando o teor não escreve nenhuma é que a coluna
    responde.

    **O QUE ESTA FUNÇÃO NÃO CONVERTE, E DIZ QUE NÃO:** `alqueire`. A ficha o
    escreve (a matrícula 534: «165,96,87,5 = 34,291 alqueires goiano»), e o
    alqueire **não tem uma medida só** — o goiano, o paulista e o do Norte
    diferem. Aqui ele volta com `metros=None` e `palavra="alqueire"`: a
    proposta cai na coluna da casa e ganha o aviso, em vez de sair com um
    número que ninguém pode conferir (a leitura pela régua do hectare dava
    **1,65 trilhão de m²** para esta ficha).
    """
    if not texto:
        return None
    for m in AREA_NO_TEXTO.finditer(texto):
        bruto = re.sub(r"\s+", "", m.group(1))
        unidade, escrita, palavra = _a_unidade_escrita(texto, m)
        # A FORMA EXATA que o teor escreveu, para a citação do `de_onde` não
        # trocar `metros quadrados` por `m2` no papel que o balcão lê.
        escrito = re.sub(r"\s+", " ", (m.group(2) or "")).strip()
        da_coluna = bool(not escrita and str(unidade_da_coluna or "").strip())
        if da_coluna:
            unidade = str(unidade_da_coluna).strip()
        # **O CAMPO `unidade` É CANÔNICO** (`ha` ou `m2`), e a coluna passa pela
        # mesma tradução da ficha: a casa escreve `ha`/`m2` na coluna e a ficha
        # escreve por extenso, e quem lê a proposta não deve receber duas
        # grafias da mesma unidade só por causa da origem. `or "ha"` preserva o
        # que já valia: unidade não escrita e coluna vazia leem hectare.
        unidade = API.unidade_canonica(unidade) or "ha"
        digitos = re.sub(r"\D", "", bruto)
        if not digitos or digitos == "0":
            continue
        # Um número solto sem unidade **no teor** e com menos de 4 dígitos é o
        # número de um lote ou de uma quadra, e não uma área — a ficha dos
        # urbanos diz «LOTE 231» logo depois da palavra. **A régua é a unidade
        # escrita na ficha, e não a que veio da coluna**: medido em 16/09/2026,
        # contar a da coluna aqui fazia a matrícula 513 ler «100» (que é o
        # número do lote) como 100 hectares.
        if not escrita and len(digitos) < 4:
            continue
        metros = None if palavra == "alqueire" else area_em_metros(bruto, unidade)
        if palavra != "alqueire" and not metros:
            continue
        return {"texto": bruto, "unidade": unidade or "ha", "metros": metros,
                "unidade_escrita": escrita, "unidade_como_escrita": escrito,
                "unidade_da_coluna": da_coluna,
                "palavra": palavra,
                "de_onde": m.group(0)[:160]}
    return None


# ═══════════════════════════════════════════════════════════════════════
# 5. URBANO OU RURAL — e a discordância com a coluna
# ═══════════════════════════════════════════════════════════════════════

# OS SINAIS TÊM PESO, E O PESO FOI MEDIDO — `tmp/onr_sinais_no_bloco.py`.
#
# A primeira lista foi escrita a olho, com todas as palavras valendo o mesmo, e
# o ensaio contra a produção mostrou que ela **marcava ficha urbana como
# rural** — porque a ficha rural cita o endereço PESSOAL das partes. Medido no
# texto inteiro, «rua» aparecia em 42% das rurais e «travessa» e «praça»
# empatavam; dentro do BLOCO do imóvel, «rua» é 2% contra 17% (razão 0,10) e
# «praça» empata em 1%. **O sinal se lê no bloco**, que `propor` já entrega —
# e foi o mesmo erro que fez o município sair errado antes.
#
# Cada palavra foi contada nas 1.176 fichas de coluna «R» e nas 333 de «U»,
# dentro do bloco, e a razão entre as duas decidiu o peso:
#
#     razão ≥ 4  →  forte (2)      ·      2 a 4  →  fraco (1)
#     razão ≤ 0,25 →  forte (2)    ·   0,25 a 0,5 →  fraco (1)
#     entre 0,5 e 2 → NÃO ENTRA: aparece nos dois, e contar não separa
#
# Ficaram de fora, com o número medido ao lado: `sítio` (26 R / 4 U, razão
# 1,84), `loteamento` (21/5, 1,19), `povoado` (21/7, 0,85), `travessa` (19/8,
# 0,67) e `praça` (7/3, 0,66). **`sítio` fora é o achado que mais espanta** —
# ele é nome de imóvel rural nesta casa («no lugar denominado Sítio Novo»),
# e o que a ficha chama de sítio é o NOME, não o tipo. `loteamento` aparece em
# 21 rurais porque a localidade rural tem loteamento dentro do nome («gleba
# Mucuíba/loteamento Buritirana»).
SINAIS_RURAL: tuple[tuple[int, str], ...] = (
    # ── forte: razão medida de 4 para cima ────────────────────────────
    (2, "zona rural"),          #   74 R ·   0 U  · razão 62926
    (2, "imóvel rural"),        #   22 R ·   0 U
    (2, "assentamento"),        #   10 R ·   0 U
    (2, "roça"),                #    8 R ·   0 U
    (2, "pecuária"),            #    3 R ·   0 U
    (2, "terras devolutas"),    #    1 R ·   0 U
    (2, "lavoura"),             #  139 R ·   2 U  · razão 19,68
    (2, "criação"),             #  160 R ·   3 U  · razão 15,10
    (2, "gleba de terras"),     #  414 R ·  11 U  · razão 10,66
    (2, "fazenda"),             #  926 R ·  31 U  · razão  8,46
    (2, "quinhão"),             #  246 R ·  10 U  · razão  6,97
    (2, "lugar"),               #  218 R ·   9 U  · razão  6,86
    (2, "denominação"),         #  114 R ·   5 U  · razão  6,46
    (2, "alqueire"),            #   68 R ·   3 U  · razão  6,42
    (2, "parte de terras"),     #  121 R ·   6 U  · razão  5,71
    (2, "hectare"),             #  676 R ·  37 U  · razão  5,17
    # ── fraco: razão entre 2 e 4 ──────────────────────────────────────
    (1, "madeira"),             #  241 R ·  18 U  · razão  3,79
    (1, "posse de terras"),     #   89 R ·   7 U  · razão  3,60
    (1, "mata"),                #   72 R ·   6 U  · razão  3,40
    (1, "chácara"),             #   71 R ·   6 U  · razão  3,35
    # `denominada` mede 9,56 e `denominado` 3,19 — A MESMA PALAVRA EM DOIS
    # GÊNEROS, e por isso o mesmo peso: dar a elas pesos diferentes faria o
    # gênero do imóvel decidir se ele é urbano ou rural.
    (1, "denominada"),
    (1, "denominado"),
)

SINAIS_URBANO: tuple[tuple[int, str], ...] = (
    # ── forte: razão medida de 0,25 para baixo ────────────────────────
    (2, "bairro"),              #    3 R · 197 U  · razão 0,00
    (2, "quadra"),              #    2 R · 206 U  · razão 0,00
    (2, "zona urbana"),         #    2 R ·   8 U  · razão 0,07
    (2, "esquina"),             #    1 R ·   4 U
    (2, "residencial"),         #    3 R ·  12 U  · razão 0,07
    (2, "rua "),                #   20 R ·  56 U  · razão 0,10
    (2, "lote"),                #   83 R · 192 U  · razão 0,12
    (2, "nesta cidade"),        #   33 R ·  70 U  · razão 0,13
    (2, "desta cidade"),        #   25 R ·  50 U  · razão 0,14
    (2, "avenida"),             #    3 R ·   6 U
    (2, "terreno"),             #   53 R · 105 U  · razão 0,14
    (2, "suburbana"),           #    9 R ·  11 U  · razão 0,23
    # ── fraco: razão entre 0,25 e 0,5 ─────────────────────────────────
    (1, "urbano"),              #    2 R ·   2 U
    (1, "casa"),                #   71 R ·  56 U  · razão 0,36
)


def localizacao_do_texto(texto: str) -> dict:
    """O que o teor diz sobre ser urbano ou rural, e em que ele se apoia.

    **A leitura não substitui a coluna: ela a confere.** Das 162 de coluna
    «R», 158 concordam e 4 discordam — e as 4 são as de 2026, em que a coluna
    está errada (as fichas foram escritas por este sistema). Por isso a
    discordância **não é conserto**: é proposta que espera alguém olhar.

    Soma os sinais de cada lado em vez de parar no primeiro: uma ficha rural
    diz «ZONA RURAL» e «BAIRRO ZONA RURAL» na mesma linha, e parar no primeiro
    faria a segunda palavra decidir.

    **A soma é ponderada**, e o peso de cada palavra está medido na tabela
    acima. Sem peso, `fazenda` (que aparece em 9% das urbanas, porque os lotes
    desta cidade nasceram de fazendas) valia o mesmo que `bairro` — e a ficha
    urbana saía rural.
    """
    alvo = API.sem_acento(texto or "")
    rurais = [(peso, f) for peso, f in SINAIS_RURAL
              if API.sem_acento(f) in alvo]
    urbanos = [(peso, f) for peso, f in SINAIS_URBANO
               if API.sem_acento(f) in alvo]
    pr = sum(p for p, _ in rurais)
    pu = sum(p for p, _ in urbanos)
    # O mais forte primeiro: é ele que a tela mostra como razão da leitura.
    rurais.sort(key=lambda t: -t[0])
    urbanos.sort(key=lambda t: -t[0])
    if pr == pu:
        return {"letra": None, "rurais": [f for _, f in rurais],
                "urbanos": [f for _, f in urbanos], "pontos_rural": pr,
                "pontos_urbano": pu, "empate": True}
    return {"letra": "R" if pr > pu else "U",
            "rurais": [f for _, f in rurais],
            "urbanos": [f for _, f in urbanos], "pontos_rural": pr,
            "pontos_urbano": pu, "empate": False}



# ═══════════════════════════════════════════════════════════════════════
# 6. OS PEDAÇOS DO URBANO — a via, o número, e o par quadra/lote
# ═══════════════════════════════════════════════════════════════════════

# `Rua Fabrício Ferraz, nº 9, VERONÍLIA` · `AVENIDA MA-280` · `Travessa São Pedro`
#
# > **E A ABREVIATURA FICA DE FORA, MEDIDA — não é esquecimento.** `Av. Central`
# > e `R. da Praça` **não** estão aqui, e a tentação de acrescentá-las é grande:
# > a leitura mostra **17** fichas em que a via abreviada é a do IMÓVEL
# > («localizado à Av. Central», «sito à Av. Raimundo Barros»). Só que o mesmo
# > `Av.` aparece em **125** fichas ancorado em «residentes e domiciliados na
# > Av. …», «com sede na Rod. BR-010» e «Agência … situada na Av. Getúlio
# > Vargas» — e **esse é o endereço das PESSOAS e das empresas, não do imóvel.**
# > Medido em 15/09/2026, com a âncora de cada lado contada uma a uma: 17 da
# > ficha, 125 das pessoas, 81 sem âncora nenhuma.
# >
# > Ler a abreviada sem mais nada mandaria o endereço particular do adquirente
# > para o **índice nacional de imóveis** — o campo existe para dizer onde o
# > imóvel fica, e ali ele diria onde o dono mora. O que separa os dois é a
# > âncora («sito», «localizado», «frente para» contra «residentes», «sede»), e
# > enquanto ela não estiver medida o valor fica **em branco para quem preenche**
# > — que é o caminho que o ONR tem para o caso.
#
# > **O PISO DO NOME É 2, E O REGEX PEDIA 3 — duas réguas para a mesma coisa.**
# > O grupo já exige um caractere (`[A-Za-zÀ-Ú0-9]`) e o `{2,60}` exigia mais
# > dois, de modo que «Rua **03**» — dois caracteres — **não casava**; e a
# > função logo abaixo aceita a partir de 2 (`len(nome) < 2`). Quem estava
# > errado era o regex: a ficha desta casa numera rua com dois dígitos, e
# > «Rua 03» é o endereço de **mat 4662**. Medido em 15/09/2026 nas 1.551:
# > **1 ganho** (a 4662) e **1 correção** — a 3928 publicava «Chácara Quintal
# > Verde», que a própria ficha diz ser o nome **de antes** («**antes**
# > denominada»), e passa a publicar a «Rua 02» onde o terreno está. Zero
# > perdas.
# >
# > **E A ABREVIATURA ENTROU EM 15/09/2026 — o comentário acima estava certo
# > sobre a dúvida e errado sobre o preço.** Ele terminava em «fica para quem
# > medir a âncora», e a âncora foi medida, com os dois lados:
# >
# > | o que se mediu | |
# > |---|---|
# > | `Av.` no **bloco do imóvel** | **24** menções nas 1.551 (o texto inteiro tem **254** — as outras 230 são de quem declarou) |
# > | das 24, ancoradas em **PESSOAS** | **3** — e **nenhuma vence**: duas são de fichas **rurais**, onde a via nem é usada, e a terceira já achava «Avenida Raimundo Barros» por extenso |
# > | o preço, medido pelo `propor` nas 1.551 | sem logradouro **36 → 29**, `pode_enviar` **1376 → 1379**, **zero perdas**, **onze** fichas tocadas |
# >
# > **O preço velho — 8 ganhos contra 95 perdas — era de OUTRA mutação**: ele
# > juntava `Av.` e `R.` com o piso 1 e o `\s*`, que casa no meio de palavra.
# > Esta é só o `Av.`, com o `\s+` que já estava aqui.
# >
# > **E a troca que sobrou mostra que a abreviação não é atalho de texto:** a
# > 4.329 publicava «Avenida Buenos Aires» — por extenso, tirado da **divisa**
# > («frente com a Avenida Buenos Aires») — e passou a tirá-lo da **âncora do
# > imóvel** («situado a Av. Buenos Aires»). É a mesma rua, e depois do
# > `_tipo_da_via` é o mesmo valor: o que mudou foi de onde ele vem, e a âncora
# > é melhor. O caso que separa é a 3.730, e é o oposto: ela publicava «Rua
# > Governador Eugênio Barros» — a rua **vizinha**, do bloco de confrontantes —
# > e publica «Avenida Raimundo Barros», onde o terreno **está** («sito na Av.
# > Raimundo Barros, esquina com a Rua Governador Eugênio Barros»).
# >
# > **E O TIPO SAI CANÔNICO, senão não sai.** Medido: o catálogo do ONR **não
# > tem `Av.`** — `partir_logradouro("Av. Central")` devolve `tipo_codigo=None`,
# > e os dois lados do contrato exigem o tipo. Os **sete** ganhos acima
# > chegariam ao índice **sem tipo**. Quem resolve é `_tipo_da_via`, e a régua
# > dela é o próprio catálogo. Os dez tipos desta régua já o eram — `Rua` 81,
# > `Avenida` 8, `Travessa` 100, `Alameda` 4, `Praça` 65, `Rodovia` 90,
# > `Estrada` 31, `Viela` 105, `Beco` 11, `Via` 101 — e `Av.` era o único que
# > faltava.
VIA_NO_TEXTO = re.compile(
    r"(?i)\b(AV\.|RUA|AVENIDA|TRAVESSA|ALAMEDA|PRA[ÇC]A|RODOVIA|ESTRADA|VIELA|"
    r"BECO|VIA)\s+([A-Za-zÀ-Ú0-9][^\n,;]{1,60}?)\s*(?=,|;|\.\s|\s+n[º°º.]|\s*$)"
)

# **A FICHA PÕE O NOME DA RUA ENTRE ASPAS, E AÍ O NOME NÃO COMEÇA POR LETRA.**
# Medido em 15/09/2026: em **6** fichas o tipo de via vem seguido de aspa. Cinco
# delas já saem certas por outro caminho — e **relaxar a régua acima para
# aceitar a aspa as estragaria**: as quatro rurais (`quinhão de terra na data ou
# “Fazenda Grande”`, `Fazenda “Folha Larga”`, `fazenda “Campo Maior”`, `Fazenda
# “Guará” … no lugar denominado “Tabatinga”`) trocariam o nome do imóvel por uma
# `Rua D` que a ficha menciona noutro lugar — o endereço de quem vendeu, ou uma
# divisa. **Um caso que separa vale mais que cinco que concordam, e aqui é o
# contrário**: um ganho contra quatro perdas.
#
# Por isso ela é **SOCORRO, e não substituição**: só entra quando a régua normal
# não achou via nenhuma, e só quando é a **PRIMEIRA** menção de via do texto.
# Com as duas condições, ela alcança **uma** ficha — a 3641, cuja proposta não
# tinha logradouro nenhum (o `s/n` a esvaziou) e que diz, no imóvel: `sito a rua
# ‘’01’’`. As outras cinco ficam exatamente como estavam. Socorrer não pode
# apagar o que já estava achado: é a lição do `None` que quer dizer «não mexi».
VIA_ENTRE_ASPAS = re.compile(
    r"(?i)\b(AV\.|RUA|AVENIDA|TRAVESSA|ALAMEDA|PRA[ÇC]A|RODOVIA|ESTRADA|VIELA|"
    r"BECO|VIA)\s+[\"'“”‘’]+\s*([A-Za-zÀ-Ú0-9][^\n,;]{1,60}?)\s*[\"'“”‘’]*"
    r"\s*(?=,|;|\.\s|\s+n[º°º.]|\s*$|\s*[–-])"
)
# **AS TRÊS RÉGUAS DE VIA ANDAM JUNTAS** — esta é a que mede «a PRIMEIRA menção
# de via do texto», que é a condição do socorro da aspa. Tirar `AV\.` daqui
# faria as duas discordarem sobre qual é a primeira menção, e o socorro passaria
# a recusar ficha cujo texto começa por uma avenida abreviada.
_QUALQUER_VIA = re.compile(
    r"(?i)\b(?:AV\.|RUA|AVENIDA|TRAVESSA|ALAMEDA|PRA[ÇC]A|RODOVIA|ESTRADA|VIELA|"
    r"BECO|VIA)\b"
)

# `nº 9` · `N. 9` · `número 123` · `, 231` **depois de um espaço**, e não colado.
#
# > **O `,\s*` PEGAVA A DATA.** Medido: as 12 propostas sem número predial
# > saíam com «14» e «17» — o **dia do mês** de «Imperatriz, 14 de outubro de
# > 1971», que era o trecho mais próximo depois do logradouro. A vírgula
# > sozinha não é separador de número: `, 231` é, e `,14 de outubro` não.
# > Exigir o espaço antes da vírgula resolve os dois sem perder nenhum caso
# > legítimo (a ficha escreve «Rua X, 231»).
NUMERO_NO_TEXTO = re.compile(
    r"(?i)(?:\bn\s*[º°º.]{0,3}\s*|\bn[úu]mero\s*|\s,\s*)(\d{1,6})\b"
)

# **AS PALAVRAS QUE, ANTES DO NÚMERO, PROVAM QUE ELE NÃO É NÚMERO DE PORTA.**
#
# O `nº` da ficha serve para tudo: número de porta, de CPF, de CI, de título
# eleitoral, de aforamento, de CREA, de talão. O que diz de qual deles se trata
# é a palavra que vem **antes**, e é ela que esta régua lê — em 45 letras
# anteriores ao número. Medido nas 1.551 fichas com teor: com ela saem **52**
# dos 62 números que o `propor` devolvia errado, e **nenhum número de porta
# verdadeiro sai junto** (zero trocas, zero perdas). Ver
# `numero_predial_do_texto`, onde as três guardas estão contadas uma a uma.
PALAVRA_DE_DOCUMENTO = re.compile(
    r"(?i)(aforamento|escritura|termo\b|matr[íi]cula|transcri[çc][ãa]o|registro|"
    r"averba[çc][ãa]o|contrato|t[íi]tulo|incra|ccir|processo|protocolo|"
    r"requerimento|c[óo]digo|contribuinte|receita|decreto|portaria|edital|"
    r"certid[ãa]o|cpf|cic|cnpj|identidade|\bci\b|\brg\b|nirf|eleitoral|"
    r"crea|engenharia|l[º°]\b|fls|livro|tal[ãa]o|pagamento|notas|autos)"
)

# **A JANELA É 100 CARACTERES, E É A ÚNICA MEDIDA EM QUE AS DUAS COISAS CABEM.**
#
# O número do imóvel está colado no endereço; o do documento, longe. Medido
# nas 1.551: em 100 o `nº 496` do aforamento (a 600 letras) e o `N 9` da
# coordenada do vértice ficam de fora, e nada de porta fica. **120 foi testado
# e traz lixo**: a mat 3683 tem a coordenada `47°12'48 , 5-18"W`, e o `, 5`
# dela entra na janela de 120 e vira número predial.
JANELA_DO_NUMERO = 100

# `QUADRA 09` · `Q. 12` · `QUADRA "B"`
QUADRA_NO_TEXTO = re.compile(
    r"(?i)\b(?:QUADRA|QD|Q)\.?\s*n?[º°º.]{0,2}\s*[:\-]?\s*([0-9]{1,4}[A-Za-z]?)\b"
)

# `LOTE 231` · `LOTE Nº 12` · `LOTE 32 – P.A. …`
LOTE_NO_TEXTO = re.compile(
    r"(?i)\bLOTE\s*n?[º°º.]{0,3}\s*[:\-]?\s*([0-9]{1,5}[A-Za-z]?)\b"
)

# `BAIRRO VERONÍLIA` · `BAIRRO: CENTRO` — a palavra identifica o TIPO do lugar
# e não o nome dele, então ela não vai para o campo.
BAIRRO_NO_TEXTO = re.compile(
    r"(?i)\bBAIRRO\s*[:\-–]?\s*([A-ZÀ-Ú][^\n,;.]{2,45})"
)

# **A FICHA VELHA NÃO DIZ «BAIRRO»: DIZ «VILA», «POVOADO» OU «DISTRITO» — e o
# nome do lugar é o bairro.** Decisão do oficial em 15/09/2026, depois de
# medir que **121** das 943 fichas da conferência ficavam sem `bairro` — e o
# campo é `required` do `indicadorRealRequest`. Dessas:
#
#     a coluna da ficha diz RURAL e o teor diz urbano ....... 40  (divergentes,
#                                                                bloqueadas)
#     têm um lugar escrito no teor ......................... 21  ← é este
#     só dizem «nesta cidade» / «zona suburbana» ........... 60  (o escrevente
#                                                                digita)
#
# As 21 são medidas, uma a uma: `Vila João Alberto` ×5, `Povoado Lageado Novo`
# ×3, `Povoado Lageado II` ×3, `Vila Lobão` ×2, e `Vila Angical`, `Vila Maria
# Tereza`, `Vila Vaquejada`, `Povoado Sumaúma`, `Povoado Açaizal`,
# `Povoado Lageanopólis`, `Distrito Lageado I` e `Centro`.
#
# > **O `RESIDENCIAL` FOI TESTADO E TIRADO, E É O CASO QUE ENSINA.** A primeira
# > versão da lista o trazia, porque «Residencial X» é bairro em muita cidade.
# > Nesta ficha ele não é: «uma casa **residencial** coberta de telhas…»,
# > «**residencial** e seu respectivo terreno situado à Praça Santana» — oito
# > das 26 primeiras leituras eram esse adjetivo, e o bairro sairia
# > `COBERTA DE TELHAS`. **Palavra de duas caras não entra numa régua que
# > escreve no índice nacional.**
#
# **`JARDIM`, `CONJUNTO`, `NÚCLEO`, `SETOR` E `ALDEIA` FORAM VARRIDOS E NÃO
# ENTRARAM**: zero leituras nas 943. Ficam ditos aqui para que quem achar um
# «Jardim X» nesta casa saiba que a régua não o vê **porque ele não está no
# acervo** — e não porque alguém o esqueceu.
#
# > **E O `LOTEAMENTO` SAIU DESSA LISTA EM 16/09/2026, PORQUE A AMOSTRA NÃO ERA
# > O ACERVO.** Ele dera zero nas **943** da conferência, e medido agora nas
# > **1.443** elegíveis ele aparece **duas vezes** — as matrículas 1779 e 1791,
# > do acervo: «na Quadra F da Rua 02, **no loteamento «Eunice Coelho»**». O
# > zero era verdadeiro e a conclusão era falsa: **ausência na amostra não prova
# > ausência no acervo**, e a amostra aqui eram as fichas que a conferência
# > olhava, não as que o índice vai receber. Os outros cinco continuam fora, e
# > continuam declarados.
#
# **E A FICHA ESCREVE O NOME DO LUGAR ENTRE ASPAS** — `no povoado “Sumaúma”`,
# `no loteamento “Eunice Coelho”`. A aspa antes do nome derrubava a régua, que
# exige a letra maiúscula logo depois da palavra do lugar: **três das sem bairro**
# saíram por isso (mat 345, 1615 e 1617, medidas em `tmp/onr_quanto_cada_regua.py`).
# O `[\"'“”‘’]?` as come, e a aspa de fecho é tirada na limpeza, como o resto.
#
# **O ADJETIVO DO DISTRITO SE PULA.** A mat 4782 escreve «distrito **urbano**
# de Lageado I»; sem o salto, o bairro sairia `URBANO`. O `de` que vem depois
# também sai, e o nome fica `LAGEADO I`.
LUGAR_NO_TEXTO = re.compile(
    r"(?i)\b(?:VILA|POVOADO|DISTRITO|LOTEAMENTO)\s*[:\-–]?\s*"
    r"(?:(?:urbano|rural|judici[áa]ri[oa]|sede)\s+(?:de\s+|do\s+|da\s+)?)?"
    r"[\"'“”‘’]?\s*([A-ZÀ-Ú][^\n,;.]{1,45})"
)

# ONDE O NOME DO LUGAR ACABA. A ficha emenda a localização na frase seguinte —
# «no povoado Açaizal **deste município** de Cidade Exemplo», «Vila Vaquejada
# **com a seguinte extensão**» —, e sem o corte o bairro levava a oração junto.
# A lista é a que a medição mostrou nas 21, e o corte por vírgula resolve a
# maioria (13 delas).
FIM_DO_LUGAR = re.compile(
    r"(?i)\s+(?:deste|desta|neste|nesta|termo|comarca|zona|situad|medindo|"
    r"[áa]rea|com)\s+|[,\-–]"
)

# `no CENTRO` · `do Centro` · `ao Centro` — e, desde 16/09/2026, o **`, Centro`**
# do endereço, que é como o acervo escreve: «Rua do Campo nº198, Centro»,
# «Travessa Central, s/nº, Centro».
#
# **AS DUAS GUARDAS PROTEGEM COISAS DIFERENTES, e as duas nasceram de medição:**
#
#   · a preposição adiante — «centro» solto é o meio de qualquer coisa;
#   · o `(?!\s+do|\s+da|\s+de)` depois — **e esta faltava.** A mat 1931 diz
#     «500 metros aproximadamente **do centro da cidade**», e a régua lia isso
#     como bairro `CENTRO`: a preposição estava lá, e o que vinha depois não
#     estava sendo olhado. **Medido nas 1.443: é o único caso, e ele é falso.**
#     Bairro que sai de uma medida de distância é o tipo de dado que ninguém
#     confere depois, porque `CENTRO` é um bairro de verdade em muitas cidades.
#
# > **E A PERDA DE UM CASO FOI O GANHO DESTA CORREÇÃO.** A régua remendada
# > ganha **8** e perde **1** — e a que ela perde é justamente a 1931, cujo
# > `CENTRO` nunca deveria ter existido. Tirar bairro errado do índice vale
# > mais que pôr bairro certo, porque o errado não se desconfia.
CENTRO_NO_TEXTO = re.compile(
    r"(?i)(?:\b(?:no|do|ao|deste|nesta)\s+CENTRO\b(?!\s+do\b|\s+da\b|\s+de\b)|"
    r",\s*CENTRO\b(?!\s+do\b|\s+da\b|\s+de\b))"
)

# `no Município de Cidade Exemplo` · `deste Município` · `nesta Cidade`
#
# > **`COMARCA` ESTAVA AQUI, E A MEDIÇÃO A TIROU.** Eu a havia posto como
# > sinônimo de município; ela não é. «Comarca de Imperatriz» é a **divisão
# > judiciária** de onde o título veio, e o imóvel desta casa está em Montes
# > Altos. Medido no ensaio contra a produção: das **425** fichas em que a
# > leitura achou um município, **378** foram por «comarca» — e o valor que
# > saiu foi «Imperatriz», que não é o município de **nenhum** imóvel do
# > acervo. Era o defeito a um passo de virar índice nacional.
MUNICIPIO_NO_TEXTO = re.compile(
    r"(?i)\b(?:munic[íi]pio|cidade)\s+de\s+([A-ZÀ-Ú][A-Za-zÀ-ú' ]{2,40})"
)

# ONDE O NOME DO MUNICÍPIO ACABA — e isto foi **medido nos 1.443**, não suposto.
#
# > **O NOME CORRIA ATÉ 40 LETRAS.** A ficha velha não usa vírgula: «nesta
# > cidade de Cidade Exemplo Termo Judiciário da Comarca de Imperatriz». A
# > leitura devolvia isso inteiro — 5 fichas —, o nome não casava com o mapa,
# > e o aviso «não é um dos municípios desta serventia» **soava falso** sobre
# > um imóvel que é de Cidade Exemplo. Outras 5 traziam a divisa junto: «Montes
# > Altos e Amarante do Maranhão», «Cidade Exemplo á Porto Franco», «Montes
# > Altos em campo aberto».
# >
# > O corte é por palavra **inteira** (`\s+X\s+`), e a lista é a que a medição
# > mostrou — `termo`, `comarca`, `judiciário`, `vara`, `zona`, `em`, `e`,
# > `á`, `até`, `onde`. Nenhum dos municípios deste mapa tem palavra solta
# > dessas dentro do nome.
FIM_DO_MUNICIPIO = re.compile(
    r"(?i)\s+(?:termo|comarca|judici[áa]ri|vara|zona|sede|situad|distante|"
    r"onde|em|e|at[ée]|[áa])\s+"
)


# ═══════════════════════════════════════════════════════════════════════
# A ABREVIAÇÃO DENTRO DO NOME — «Rua Dep. La Rocque»
# ═══════════════════════════════════════════════════════════════════════
#
# **O `\.\s` DO LOOKAHEAD CORTA EM FIM DE FRASE, E ELE ESTÁ CERTO** — é ele que
# impede «Rua das Flores. Adquirido por Aforamento» de virar um logradouro de
# trinta letras. Mas o ponto também separa uma **abreviação** do resto do
# nome, e aí ele não está terminando coisa nenhuma.
#
# Medido em 15/09/2026, nas **250** fichas em que a leitura achou via: acontece
# **uma vez** — a matrícula **1020**, «Rua Dep. La Rocque», que saía como «Rua
# Dep». **Um caso é pouco para afrouxar o lookahead e muito para deixar
# errado**, porque o logradouro vai ao índice nacional.
#
# **E A RÉGUA É A LISTA, E NÃO O TAMANHO DA PALAVRA.** Aceitar «token de até
# quatro letras» foi medido e toca a mesma ficha —, mas estenderia também
# «Rua Sol. Adquirido por…»: um nome curto de rua não se distingue de uma
# palavra curta de prosa contando letras. **Abreviação é vocabulário, e
# vocabulário se declara.** Quem precisar de outra a acrescenta aqui, e o
# medidor diz o efeito antes.
ABREVIACAO_NO_NOME = re.compile(
    r"(?i)\b(?:dep|cel|maj|cap|ten|sgt|gal|mal|brig|prof|dr|dra|pe|frei|dom|"
    r"sta|sto|pres|gov|min|eng|arq|cmte|alf|gen|cor|m[ée]d|visc|bar[ãa]o|"
    r"conde|duque|mons|padre|c[ôo]nego|bispo)$"
)

# O que a ficha escreve **depois do ponto da abreviação** — e ela continua com
# palavra, não com uma frase nova. As fronteiras são as mesmas do
# `VIA_NO_TEXTO`, pelo mesmo motivo: o nome não pode engolir a prosa seguinte.
CONTINUA_DEPOIS_DO_PONTO = re.compile(
    r"\.\s*([A-Za-zÀ-Ú][^\n,;]{1,40}?)\s*(?=,|;|\.\s|\s+n[º°º.]|\s*$)"
)


def _estende_a_abreviacao(nome: str, texto: str, fim: int) -> tuple[str, int]:
    """O resto do nome da via, quando a ficha o continua depois do ponto.

    Devolve `(nome, fim)` — e, quando não é o caso, devolve o que recebeu. O
    `fim` volta maior quando estende, e é ele que faz o `de_onde` mostrar o que
    de fato foi lido, em vez do pedaço que a régua parou de ler.
    """
    if not ABREVIACAO_NO_NOME.search(nome):
        return nome, fim
    if fim >= len(texto) or texto[fim] != ".":
        return nome, fim
    m = CONTINUA_DEPOIS_DO_PONTO.match(texto[fim:])
    if m is None:
        return nome, fim
    return f"{nome}. {m.group(1).strip()}", fim + m.end()


# **O TIPO SAI COMO O CATÁLOGO DO ONR O ESCREVE — e a régua é o catálogo.**
# Medido em 15/09/2026: `partir_logradouro("Av. Central")` devolvia
# `tipo_codigo=None`, porque `CODIGO_DO_LOGRADOURO` tem `avenida` e **não tem
# `av.`**. Os sete logradouros que a regex passou a achar chegariam ao índice
# nacional **sem tipo**, e o contrato o exige dos dois lados.
#
# A conferência é feita **contra o catálogo**, e não contra uma lista escrita
# aqui: os dez tipos desta régua já são palavras do contrato, e escrever uma
# segunda lista faria as duas divergirem no primeiro tipo novo. A tabela abaixo
# só tem o que o catálogo não conhece — hoje, uma entrada.
TIPO_ABREVIADO = {"av.": "Avenida"}


def _tipo_da_via(bruto: str) -> str:
    """«AV.» → «Avenida»; «RUA» → «Rua»; o que não estiver no catálogo sai como veio.

    **Não é enfeite de formatação: é o que faz o tipo existir para o ONR.** Quem
    lê o resultado é `partir_logradouro`, e ele procura a palavra no catálogo do
    contrato — «Av.» não está lá, «Avenida» está (código 8).
    """
    t = (bruto or "").strip()
    if API.sem_acento(t) in API.CODIGO_DO_LOGRADOURO:
        return t.title()
    return TIPO_ABREVIADO.get(API.sem_acento(t), t.title())


def _limpa_nome_lugar(txt: str) -> str:
    return re.sub(r"\s+", " ", _tira_aspas(_corta(txt))).strip(" -–—·")


def via_do_texto(texto: str) -> dict | None:
    """A via urbana — «Rua Fabrício Ferraz» —, com o tipo à frente.

    **E, quando a régua normal não devolve nome utilizável, o socorro da aspa**
    — que só vale se for a primeira menção de via do texto. As duas condições
    estão medidas em `VIA_ENTRE_ASPAS`: sem elas a aspa do nome trocaria o nome
    do imóvel por uma rua que a ficha cita de passagem.

    **E o socorro não é só para o «não achou»: é para o «não sobrou nome».** A
    ficha 3641 casa — na **segunda** menção, `pelo lado esquerdo com a Rua s/nº`,
    que descreve a divisa — e o `s/n` esvazia o nome depois; o `None` que sai
    daqui não era falta de via, era via sem nome. Foi isso que me fez escrever
    a condição errada na primeira versão, e o medidor devolveu **zero fichas
    tocadas** em vez de uma. Quem apontou foi o `via_do_texto` chamado direto
    sobre o bloco, com o `match` à vista na posição 487.
    """
    if not texto:
        return None
    m = VIA_NO_TEXTO.search(texto)
    nome = _limpa_nome_lugar(m.group(2)) if m else ""
    fim = m.end() if m else 0
    if m is not None:
        # «Rua Dep. La Rocque»: o ponto era da abreviação, e não o fim do nome.
        nome, fim = _estende_a_abreviacao(nome, texto, fim)
    if len(nome) < 2:
        # O socorro: só quando não sobrou nome utilizável, e só na primeira
        # menção de via do texto.
        primeira = _QUALQUER_VIA.search(texto)
        a = VIA_ENTRE_ASPAS.search(texto)
        if a is not None and primeira is not None and a.start() == primeira.start():
            nome, m = _limpa_nome_lugar(a.group(2)), a
            nome, fim = _estende_a_abreviacao(nome, texto, fim)
    if not m or len(nome) < 2:
        return None
    # «AVENIDA MA-280» é código de rodovia, e o número dele não é o predial.
    # **O tipo passa pelo catálogo** (`_tipo_da_via`): «Av.» não é palavra do
    # contrato do ONR, e o tipo é exigido dos dois lados.
    via = f"{_tipo_da_via(m.group(1))} {nome}"
    return {"logradouro": via, "de_onde": texto[m.start():fim][:160]}


def numero_predial_do_texto(texto: str, *, depois_de: int = 0) -> dict | None:
    """O número predial, **procurado depois do logradouro quando há um**.

    A ordem importa: a ficha escreve «LOTE 231, QUADRA 12, RUA X, Nº 9», e
    pegar o primeiro número do bloco pegaria o do lote.

    **E O `Nº` DA FICHA NÃO QUER DIZER NÚMERO DE PORTA — foi esta passada que
    fixou isso.** Medido nas **1.551** fichas com teor, contra o que o `propor`
    devolvia antes das guardas: em **52** delas o «número predial» era
    `Título Eleitoral nº 3046`, `CI nº 1112757-PA`, `CPF sob nº 054`,
    `Termo de Aforamento nº 496`, `Talão nº 530`, `CREA nº 1418` — **documento
    de quem declarou**, a seiscentas letras do endereço, indo para o índice
    nacional como «número do imóvel». Em outras **9** o número era de
    coordenada (`N 9` do vértice P-09) ou de divisa, e em **1** o `nº02` era de
    um lote citado na descrição. São **62 ao todo** — e as três guardas
    separam-nas dos números de porta sem perder nenhum deles: **zero trocas e
    zero perdas** medidas.

    As três, na ordem em que decidem:

    1. **A JANELA (`JANELA_DO_NUMERO`)** — o número tem de estar colado no
       endereço, e é o que a ficha faz quando o número é do imóvel. Sozinha não
       bastava: o `CPF sob nº 054` de quem declarou cai **dentro** dos cem
       primeiros.
    2. **A PALAVRA DE DOCUMENTO (`PALAVRA_DE_DOCUMENTO`)** — quarenta e cinco
       letras antes do número, e a palavra que aparece ali diz o que ele é.
    3. **O `de` DEPOIS** — número seguido de ` de ` é data ou quantidade
       (`nº 5 de junho`, `nº 10 de metros`), não porta. Pegou **1**.

    **E O QUE FICOU DE FORA, DE PROPÓSITO: o socorro do lote.** Duas fichas
    (3511 e 3512) escrevem `Lote nº07` como unidade, e a tentação era socorrê-las
    pela `LOTE_NO_TEXTO` desta casa quando a régua do número não devolvesse
    nada. Medido: ela **não recupera nenhuma das duas** — as duas nem chegam
    aqui, porque não têm via urbana — e **troca uma terceira, errada** (a mat
    3928 passaria de `02` para o `10` de outro lote citado no texto). Socorrer
    com a régua larga custa um erro para não ganhar nada; com a forma estreita
    `Lote nº N` é **no-op** medido nas 1.551. **Nenhuma das duas entrou**:
    função que não muda nada é função que ninguém confere depois, e esta já tem
    três guardas para quem for mexer nela.

    > **E o `n º 64` mostrou que a régua do número tinha um buraco — e mostrou
    > também que valor certo vindo do lugar errado passa por acerto.** A mat
    > 4709 — «Um Terreno sito a Rua Quintiliano Jose Tavares» — escreve o
    > marcador **separado da letra**: `n º 64`, com espaço entre o `n` e o `º`.
    > O padrão antigo (`\\bn[º°º.]…`) exigia o `º` colado no `n`, e **sem janela
    > isso passava despercebido**: ele achava um `n° 64` **546 letras adiante**,
    > na descrição da divisa, com o mesmo valor **por coincidência**. `de_onde`
    > agora diz `n º 64` na posição 36 — colado no nome da rua, que é onde o
    > número do imóvel é. Medido nas 1.551: o `\\s*` **não cria número nenhum
    > onde não havia** — devolve um, que é este, e é verdadeiro.
    """
    if not texto:
        return None
    m = NUMERO_NO_TEXTO.search(texto, depois_de, depois_de + JANELA_DO_NUMERO)
    if not m:
        return None
    antes = texto[max(0, m.start() - 45):m.start()]
    depois = texto[m.end(1):m.end(1) + 8]
    if PALAVRA_DE_DOCUMENTO.search(antes) or re.match(r"\s*de\s", depois, re.I):
        return None
    return {"numero": m.group(1), "de_onde": m.group(0)[:120],
            "fim": m.end(1)}


def quadra_e_lote(texto: str) -> dict:
    """O par quadra/lote — e a decisão do oficial sobre como ele vai ao ONR.

    **`tipoLogradouro = 77 «Quadra»` · `logradouro = «09»` · `numero = «12»`**:
    a quadra é o logradouro e o lote é a unidade. E «Quadra» é uma das 129
    entradas do catálogo do ONR — medido, não escolhido.
    """
    q = QUADRA_NO_TEXTO.search(texto or "")
    lote = LOTE_NO_TEXTO.search(texto or "")
    return {"quadra": q.group(1) if q else None,
            "lote": lote.group(1) if lote else None,
            "de_onde_quadra": q.group(0)[:80] if q else "",
            "de_onde_lote": lote.group(0)[:80] if lote else ""}


def bairro_do_texto(texto: str) -> dict | None:
    """O bairro — **sem a palavra «BAIRRO»**, que é o tipo do lugar.

    Decisão do oficial: «VERONÍLIA — a palavra "BAIRRO" identifica o tipo do
    lugar, não o nome dele».

    **QUANDO A FICHA NÃO DIZ «BAIRRO», O NOME DO LUGAR É O BAIRRO** — decisão
    dele em 15/09/2026, sobre as 21 que o acervo tem: a ficha velha desta casa
    escreve `Vila João Alberto`, `Povoado Lageado Novo`, `Distrito Lageado I`.
    Ver `LUGAR_NO_TEXTO`, onde as 21 estão contadas e o `RESIDENCIAL` está
    explicado — foi medido e tirado, porque nesta ficha ele é adjetivo.

    **A ORDEM É A DA FORÇA**: `BAIRRO X` primeiro, porque é a palavra que não
    tem outro sentido; o lugar depois, porque `Vila` pode nomear qualquer
    coisa; `CENTRO` por último, e **com duas guardas** — a preposição na frente
    e a palavra depois: «no centro **do terreno**» é o meio do terreno, e «do
    centro **da cidade**» é uma distância. Sem elas ele viraria bairro em
    qualquer ficha que falasse do centro de alguma coisa, e foi o que a mat
    1931 mostrou.
    """
    if not texto:
        return None
    m = BAIRRO_NO_TEXTO.search(texto)
    if m:
        nome = _limpa_nome_lugar(m.group(1))
        if len(nome) >= 3:
            return {"bairro": nome.upper(), "de_onde": f"teor: «{m.group(0)[:90]}»"}
    m = LUGAR_NO_TEXTO.search(texto)
    if m:
        bruto = m.group(1)
        corte = FIM_DO_LUGAR.search(bruto)
        if corte:
            bruto = bruto[:corte.start()]
        nome = _limpa_nome_lugar(bruto)
        if len(nome) >= 3:
            tipo = m.group(0).split()[0].upper()
            return {"bairro": nome.upper(),
                    "de_onde": f"teor: «{tipo} {nome}»"}
    m = CENTRO_NO_TEXTO.search(texto)
    if m:
        # **A PROCEDÊNCIA É O QUE O TEXTO DIZ, e não a forma que a régua espera.**
        # Aqui saía a frase fixa «no Centro» — e a mat 2754, que escreve
        # `Travessa Central, s/nº, Centro`, ganharia um bairro cuja procedência
        # ninguém consegue achar no teor. Quem confere o `de_onde` procura o
        # trecho na ficha: ele tem de estar lá.
        return {"bairro": "CENTRO", "de_onde": f"teor: «{m.group(0).strip()}»"}
    return None


def municipio_do_texto(texto: str) -> dict | None:
    """O município que a ficha declara, quando ela o declara.

    **O NOME ACABA ONDE ELE ACABA**, e não onde a regex parou de contar: ver
    `FIM_DO_MUNICIPIO`, que foi medido nas 1.443.
    """
    if not texto:
        return None
    m = MUNICIPIO_NO_TEXTO.search(texto)
    if not m:
        return None
    bruto = m.group(1)
    corte = FIM_DO_MUNICIPIO.search(bruto)
    if corte:
        bruto = bruto[:corte.start()]
    nome = _limpa_nome_lugar(bruto)
    return {"municipio": nome, "de_onde": m.group(0)[:120]} if nome else None


# ═══════════════════════════════════════════════════════════════════════
# 7. O PADRÃO DA CASA — o que vale para toda a serventia
# ═══════════════════════════════════════════════════════════════════════

# **O CEP DESTA CASA É UM SÓ PARA A CIDADE**, e o oficial confirmou em
# 15/09/2026: «CEP generico da cidade, no caso de cidade exemplo eh unico para
# toda cidade». Medido nas fichas já preenchidas: 65936000 em **173** delas.
#
# > **E O MAPA É POR MUNICÍPIO PORQUE SÃO DOIS.** Ribamar Fiquene — município
# > vizinho, com matrícula neste livro — aparece com o CEP **65938000** numa
# > ficha que a própria casa preencheu; e **29** das 1.443 fichas do ensaio têm
# > a cidade «Ribamar Fiquene» no teor. Com um número só no código, essas 29
# > iriam ao índice nacional na rua de outra cidade. O CEP vizinho é medido, e
# > não deduzido — quem o escreveu foi a casa.
#
# **O MAPA SAIU DO CÓDIGO em 09/10/2026** (sanitização para o código aberto):
# ele é desta instalação e mora em `settings.onr_ceps_por_cidade`, uma linha
# por município no formato `Cidade=00000000`, gravado pelo perfil local
# (`tools/migrar_settings_serventia_b0.py`). O CEP da própria serventia
# (`serventia_cep`) vale sempre para a cidade dela, sem precisar repetir.
CHAVE_CEPS = "onr_ceps_por_cidade"
CEP_POR_CIDADE: dict[str, str] = {}

CIDADE_PADRAO = ""
UF_PADRAO = ""


def ceps_por_cidade(s: dict) -> dict[str, str]:
    """O mapa município → CEP desta instalação, lido da configuração."""
    mapa: dict[str, str] = dict(CEP_POR_CIDADE)
    for linha in str(s.get(CHAVE_CEPS) or "").splitlines():
        cidade, _, cep = linha.partition("=")
        digitos = "".join(ch for ch in cep if ch.isdigit())
        if cidade.strip() and len(digitos) == 8:
            mapa[API.sem_acento(cidade.strip())] = digitos
    propria = s.get("ri_cidade") or s.get("serventia_cidade") or ""
    cep_proprio = "".join(ch for ch in str(s.get("serventia_cep") or "") if ch.isdigit())
    if propria and len(cep_proprio) == 8:
        mapa.setdefault(API.sem_acento(propria), cep_proprio)
    return mapa

# **O RURAL DESTA CASA MORA NA ZONA RURAL**, decisão do oficial no mesmo dia.
BAIRRO_RURAL = "Zona Rural"

# **O NÚMERO QUE NÃO EXISTE VAI COMO «0»**, e não vazio: o contrato exige o
# campo, e isto é o que a casa já faz nas fichas preenchidas.
NUMERO_SEM_NUMERO = "0"


def padrao_da_casa(settings: dict | None = None) -> dict:
    """O que se aplica a toda a serventia, e o que vem da configuração.

    A cidade e a UF saem de `ri_cidade` e `ri_uf`, que é onde esta casa já as
    guarda — **escrevê-las de novo aqui seria a segunda fonte do mesmo nome**.
    O padrão fica embaixo, para a instalação nova e para o banco sem elas.
    """
    s = {k: ("" if v is None else str(v)).strip()
         for k, v in (settings or {}).items()}
    cidade = s.get("ri_cidade") or s.get("serventia_cidade") or CIDADE_PADRAO
    uf = (s.get("ri_uf") or s.get("serventia_uf") or UF_PADRAO).upper()[:2]
    ceps = ceps_por_cidade(s)
    cep = s.get("ri_cep") or ceps.get(API.sem_acento(cidade), "")
    return {"cidade": cidade, "uf": uf, "cep": cep,
            "ceps": ceps,
            "bairro_rural": BAIRRO_RURAL, "numero": NUMERO_SEM_NUMERO}


# ═══════════════════════════════════════════════════════════════════════
# 8. A PROPOSTA
# ═══════════════════════════════════════════════════════════════════════

# Os campos desta casa que o indicador real lê.
CAMPOS: tuple[str, ...] = (
    "logradouro", "numero_predial", "bairro", "cidade", "uf", "cep",
    "rural_urbano", "area_valor", "area_unidade", "tipo_imovel",
)

ROTULO_DO_CAMPO: dict[str, str] = {
    "logradouro": "Logradouro", "numero_predial": "Número", "bairro": "Bairro",
    "cidade": "Cidade", "uf": "UF", "cep": "CEP",
    "rural_urbano": "Urbano ou rural", "area_valor": "Área",
    "area_unidade": "Unidade da área", "tipo_imovel": "Tipo do imóvel",
}


def _vazio(v: Any) -> bool:
    return v is None or not str(v).strip()


def propor(matricula: dict, *, teor: Any = None, settings: dict | None = None,
           padrao: dict | None = None) -> dict:
    """Lê o teor e diz o que iria para a ficha. **SÓ CALCULA.**

    Devolve a proposta com quatro partes que a tela mostra separadas:

        `campos`    o que se propõe gravar, campo por campo
        `de_onde`   a frase do teor de onde cada campo saiu
        `faltam`    o que o contrato exige e o teor não deu
        `avisos`    o que a pessoa precisa olhar antes de confirmar

    **`pode_enviar` é `False` quando o teor discorda da coluna.** Não é uma
    recusa: é a fila da conferência, com as duas versões à vista — foi a
    escolha do oficial para as 67 divergentes, e ela vale para estas.
    """
    m = dict(matricula or {})
    p = dict(padrao or padrao_da_casa(settings))
    bruto = texto_do_teor(teor if teor is not None else m.get("teor"))
    bloco = bloco_do_imovel(bruto)

    campos: dict[str, Any] = {}
    de_onde: dict[str, str] = {}
    faltam: list[str] = []
    avisos: list[str] = []

    # ── a leitura do teor, cada peça com a sua confiança ──────────────
    leitura = localizacao_do_texto(bloco["texto"])
    coluna = (m.get("rural_urbano") or "").strip().upper()[:1] or None
    letra = leitura["letra"] or coluna
    if letra is None:
        faltam.append("Urbano ou rural")
    elif (coluna in ("R", "U") and leitura["letra"]
          and leitura["letra"] != coluna):
        # **O AVISO MOSTRA OS SINAIS DE QUEM GANHOU, E NÃO OS DO OUTRO LADO.**
        # A primeira versão escrevia `rurais or urbanos`, e nas duas fichas em
        # que o teor é urbano *e* fala «hectare» ela dizia «O teor diz URBANO —
        # apoia-se em: hectare»: a razão apresentada contradizia a conclusão, num
        # aviso que existe justamente para a pessoa conferir. Medido em
        # 15/09/2026 sobre as 1.443: acontece em duas (matrículas 1117 e 1125).
        venceu = leitura["rurais"] if leitura["letra"] == "R" else leitura["urbanos"]
        perdeu = leitura["urbanos"] if leitura["letra"] == "R" else leitura["rurais"]
        avisos.append(
            f"**O teor diz {'RURAL' if leitura['letra'] == 'R' else 'URBANO'} "
            f"e a ficha está marcada como {'RURAL' if coluna == 'R' else 'URBANO'}.**"
            f" O teor se apoia em: {', '.join(venceu)[:120]}."
            + (f" Do outro lado aparecem: {', '.join(perdeu)[:80]}."
               if perdeu else "")
            + " Una as duas na ficha antes de mandar.")
    elif leitura["empate"] and coluna not in ("R", "U"):
        avisos.append(
            "O teor não decide se o imóvel é urbano ou rural — os sinais "
            "aparecem dos dois lados. Preencha na ficha.")

    divergente = bool(coluna in ("R", "U") and leitura["letra"]
                      and leitura["letra"] != coluna)
    if letra in ("R", "U"):
        campos["rural_urbano"] = letra
        sinais = (leitura["rurais"] if letra == "R" else leitura["urbanos"])[:3]
        # **A CITAÇÃO MOSTRA AS PALAVRAS DO LIVRO, ENTRE «» — corrigido em
        # 16/09/2026.** Antes ela escrevia os sinais soltos, separados por
        # vírgula («teor: gleba de terras, fazenda, hectare»), e assim não se
        # distinguia de um rótulo do sistema: quem confere não sabia que eram
        # palavras a procurar na ficha. Medido: **1.427 das 1.442** citações
        # deste campo saíam sem a marca, e é ela que diz «isto está escrito
        # no teor».
        de_onde["rural_urbano"] = (
            f"{'teor' if leitura['letra'] else 'coluna'}: "
            + ", ".join(f"«{s}»" for s in sinais))

    # ── o nome, a via e o par quadra/lote ─────────────────────────────
    nome = nome_do_imovel(bloco["texto"])
    ql = quadra_e_lote(bloco["texto"])
    via = via_do_texto(bloco["texto"])

    if letra == "U":
        # O URBANO TEM VIA, QUADRA E LOTE — medido nas 211.
        if ql["quadra"]:
            campos["logradouro"] = f"Quadra {ql['quadra']}"
            de_onde["logradouro"] = ql["de_onde_quadra"]
            campos["numero_predial"] = ql["lote"] or p["numero"]
            de_onde["numero_predial"] = (
                ql["de_onde_lote"] or "sem número na ficha → «0»")
        elif via:
            campos["logradouro"] = via["logradouro"]
            de_onde["logradouro"] = via["de_onde"]
        elif nome:
            logr = logradouro_do_nome(nome["nome"])
            # **O TIPO VAI JUNTO PARA A FICHA** — ver `logradouro_do_nome`.
            campos["logradouro"] = logr["texto"]
            de_onde["logradouro"] = nome["de_onde"]
            if logr["acrescentou"]:
                avisos.append(
                    f"A ficha não diz a via deste imóvel — o nome dela é "
                    f"«{nome['nome']}», e ele vai como «Área», que é o que o "
                    f"catálogo do ONR tem. Se houver rua, escreva-a na ficha.")
        # O TIPO SOZINHO NÃO É NOME — «Estrada», «Área» —, e volta para «faltam».
        tira_o_logradouro_que_nao_e_nome(campos, de_onde, avisos)
        if "logradouro" not in campos:
            faltam.append("Logradouro")
        elif "numero_predial" not in campos:
            # O NÚMERO VEM DEPOIS DO LOGRADOURO, e não antes: a ficha escreve
            # «RUA X, Nº 9», mas também «LOTE 231, RUA X» — e pegar o primeiro
            # número do bloco pegaria o do lote.
            pos = bloco["texto"].upper().find(str(campos["logradouro"]).upper())
            n = numero_predial_do_texto(
                bloco["texto"], depois_de=max(pos, 0))
            campos["numero_predial"] = n["numero"] if n else p["numero"]
            de_onde["numero_predial"] = (
                n["de_onde"] if n else "sem número na ficha → «0»")
        if ql["quadra"] and not ql["lote"]:
            avisos.append(
                "A ficha diz a quadra e não diz o lote — o número vai como "
                "«0». Confira se o lote não está escrito de outra forma.")
    else:
        # O RURAL TEM NOME, E O NOME É O LOGRADOURO.
        if nome:
            logr = logradouro_do_nome(nome["nome"])
            # **O TIPO FICA NO QUE VAI PARA A FICHA** — «Fazenda São
            # Francisco», e não «São Francisco». Medido: sem ele o envio
            # recusa, porque não acha o tipo do logradouro, e o nome do
            # imóvel é justamente o que o índice nacional publica.
            campos["logradouro"] = logr["texto"].strip()
            de_onde["logradouro"] = nome["de_onde"]
            if nome["confianca"] == "baixa":
                avisos.append(
                    f"O nome do imóvel saiu da frase mais fraca das quatro "
                    f"(«{nome['nome']}», tirado de «na Fazenda …»). Confira.")
        else:
            faltam.append("Logradouro")
            avisos.append(
                "**O teor não diz o nome deste imóvel.** É o único campo que o "
                "ONR não aceita vazio e que não se deduz — quem sabe é quem lê "
                "a ficha, e aqui não há o que propor.")
        # O TIPO SOZINHO NÃO É NOME — a mesma régua do urbano, e o mesmo aviso.
        if tira_o_logradouro_que_nao_e_nome(campos, de_onde, avisos):
            faltam.append("Logradouro")
        campos["numero_predial"] = p["numero"]
        de_onde["numero_predial"] = "imóvel rural, sem número predial → «0»"

    # ── a área ────────────────────────────────────────────────────────
    area = area_do_texto(bloco["texto"], unidade_da_coluna=m.get("area_unidade"))
    area_coluna = area_em_metros(m.get("area_valor"), m.get("area_unidade"))
    if area and area.get("metros"):
        campos["area_valor"] = str(area["metros"])
        campos["area_unidade"] = "m2"
        if area["unidade_da_coluna"]:
            de_onde["area_valor"] = (
                f"teor: «{area['texto']}» com a unidade da coluna "
                f"({m.get('area_unidade')}) = {area['metros']} m²")
            de_onde["area_unidade"] = (
                f"unidade da coluna da ficha ({m.get('area_unidade')}) → "
                f"convertida para m², que é o que o ONR espera")
        elif not area["unidade_escrita"]:
            de_onde["area_valor"] = (
                f"teor: «{area['texto']}» = {area['metros']} m² — a ficha não "
                f"escreve a unidade, e a casa lê hectare")
            de_onde["area_unidade"] = (
                "a ficha não escreve a unidade — a casa lê hectare, e vai "
                "convertida para m²")
        else:
            # A CITAÇÃO USA A FORMA ESCRITA, e o número ao lado é canônico: a
            # ficha 924 diz «344,35 metros quadrados», e é assim que ela tem de
            # aparecer entre «» — quem confere vai procurar isso no livro.
            escrito = area.get("unidade_como_escrita") or area["unidade"]
            de_onde["area_valor"] = (
                f"teor: «{area['texto']} {escrito}» = {area['metros']} m²")
            de_onde["area_unidade"] = (
                f"a ficha escreve «{escrito}» → convertida para m², que é o "
                f"que o ONR espera")
        if area_coluna and abs(area_coluna - area["metros"]) > max(
                2, area["metros"] // 100):
            avisos.append(
                f"A área da coluna ({m.get('area_valor')} "
                f"{m.get('area_unidade') or ''} = {area_coluna} m²) não bate "
                f"com a da ficha ({area['metros']} m²). **A da ficha é a que "
                f"vai** — confira antes.")
    elif area_coluna:
        campos["area_valor"] = str(area_coluna)
        campos["area_unidade"] = "m2"
        de_onde["area_valor"] = (
            f"coluna: {m.get('area_valor')} {m.get('area_unidade') or ''} "
            f"= {area_coluna} m²")
        de_onde["area_unidade"] = (
            f"unidade da coluna da ficha ({m.get('area_unidade') or 'sem unidade'})"
            f" → convertida para m²")
    if area and area.get("palavra") == "alqueire":
        avisos.append(
            "A ficha mede a área em **alqueire** («"
            f"{area['texto']}»), e o alqueire não tem uma medida só — o "
            "goiano, o paulista e o do Norte diferem. **Este sistema não faz "
            "essa conta**: a área acima veio da coluna da casa e precisa ser "
            "conferida antes de enviar.")

    # ── o bairro, a cidade, a UF e o CEP ──────────────────────────────
    b = bairro_do_texto(bloco["texto"])
    if letra == "R":
        campos["bairro"] = p["bairro_rural"]
        de_onde["bairro"] = "imóvel rural → «Zona Rural»"
    elif b:
        campos["bairro"] = b["bairro"]
        de_onde["bairro"] = b["de_onde"]
    elif not _vazio(m.get("bairro")):
        campos["bairro"] = str(m["bairro"]).strip()
        de_onde["bairro"] = "já estava na ficha"
    else:
        faltam.append("Bairro")

    mun = municipio_do_texto(bloco["texto"])
    conhecidas = {API.sem_acento(c) for c in p["ceps"]}
    if mun and API.sem_acento(mun["municipio"]) not in conhecidas:
        avisos.append(
            f"A ficha diz «{mun['de_onde']}», que não é um dos municípios "
            f"desta serventia ({', '.join(sorted(p['ceps']))}). Vai o "
            f"padrão ({p['cidade']}), e **confira**: ou o imóvel é de fora, ou "
            f"a ficha tem outro nome no lugar.")
        de_onde["cidade"] = f"padrão (a ficha diz «{mun['municipio']}»)"
    elif not _vazio(m.get("cidade")):
        de_onde["cidade"] = "já estava na ficha"
    else:
        # **AQUI DIZIA «ficha:», E A CIDADE NÃO VINHA DA FICHA — corrigido em
        # 16/09/2026.** Este ramo só roda quando a coluna está VAZIA (o de cima
        # é o `já estava na ficha`), de modo que o valor sai do **teor** ou do
        # **padrão** — nunca da ficha. E `de_onde` é o mapa que existe para a
        # pessoa conferir de onde cada campo saiu: rótulo que aponta para o
        # lugar errado manda quem confere olhar onde o dado não está. Achado
        # montando o teste da tela, com a matrícula 1.616, que tem a coluna
        # vazia e o teor dizendo «município de Cidade Exemplo»: a tela mostrava
        # «ficha: Cidade Exemplo» para um dado que a ficha não tinha.
        # **A CITAÇÃO CITA A FRASE, E NÃO SÓ O NOME JÁ LIMPO — corrigido em
        # 16/09/2026.** «teor: Cidade Exemplo» dizia de onde o dado veio sem
        # mostrar o que o livro escreve; a frase medida — a mesma que o aviso
        # logo acima já usa — é o que quem confere vai procurar na ficha.
        # Medido antes: **680 das 1.442** citações deste campo saíam sem ela.
        de_onde["cidade"] = (
            f"teor: «{mun['de_onde']}»" if mun
            else "padrão da serventia — a ficha não diz o município")

    campos["cidade"] = (str(m["cidade"]).strip() if not _vazio(m.get("cidade"))
                        else (mun["municipio"] if mun
                              and API.sem_acento(mun["municipio"]) in conhecidas
                              else p["cidade"]))
    campos["uf"] = (str(m["uf"]).strip().upper() if not _vazio(m.get("uf"))
                    else p["uf"])
    # **A UF NÃO TINHA CITAÇÃO NENHUMA, e é campo que a conferência mostra** —
    # achado em 16/09/2026 medindo a coluna «de onde saiu»: das **1.442**
    # propostas, **1.442** tinham a célula da UF em branco. Célula vazia numa
    # coluna que existe para dizer a origem se lê como «não se sabe»; o certo é
    # dizer o que é: a ficha já a tinha, ou ela é o padrão da casa, porque o
    # teor quase nunca escreve a sigla.
    de_onde["uf"] = ("já estava na ficha" if not _vazio(m.get("uf"))
                     else f"padrão da serventia ({p['uf']}) — o teor não escreve a UF")

    # **O CEP É DA CIDADE QUE VAI, E NÃO O DESTA CASA** — defeito meu, achado em
    # 15/09/2026 medindo as 1.443: **29 fichas saíam com cidade «Ribamar
    # Fiquene» e o CEP de Cidade Exemplo**, e o `de_onde` ainda dizia «padrão de
    # Ribamar Fiquene» — carimbo que mente sobre o próprio dado. Numa base
    # nacional, o CEP errado põe o imóvel na rua de outra cidade.
    #
    # A ordem: o que a ficha já tem ganha (é o que a casa escreveu); depois o
    # CEP **daquela** cidade, do mapa medido; e sem CEP para a cidade,
    # **falta** — nunca o CEP de outra.
    cep_da_ficha = re.sub(r"\D", "", str(m.get("cep") or ""))[:8]
    if len(cep_da_ficha) == 8:
        campos["cep"] = cep_da_ficha
        de_onde["cep"] = "já estava na ficha"
    else:
        da_cidade = API.sem_acento(campos["cidade"])
        if da_cidade == API.sem_acento(p["cidade"]):
            cep = p["cep"]
            de_onde_cep = f"padrão de {campos['cidade']}"
        else:
            cep = p["ceps"].get(da_cidade, "")
            de_onde_cep = (f"CEP de {campos['cidade']}, medido nas fichas "
                           f"da casa")
        if not cep:
            faltam.append("CEP")
            avisos.append(
                f"Não há CEP para «{campos['cidade']}» no padrão da casa — e o "
                f"CEP de outra cidade não serve, porque iria errado ao índice "
                f"nacional. Informe-o em Administrativo → Configurações, ou na "
                f"própria ficha.")
        else:
            campos["cep"] = re.sub(r"\D", "", cep)[:8]
            de_onde["cep"] = de_onde_cep

    for rotulo in ("Cidade", "UF"):
        if _vazio(campos.get(rotulo.lower())):
            faltam.append(rotulo)

    # ── o tipo do imóvel ──────────────────────────────────────────────
    if _vazio(m.get("tipo_imovel")):
        # NÃO É ESCOLHA NOSSA: é o que a coluna desta casa diz nas 1.701 do
        # acervo — «Fazenda/Sítio/Chácara» —, e o de-para para o código do
        # ONR já existe em `onr_api.CODIGO_DO_IMOVEL`.
        palpite = "Fazenda/Sítio/Chácara" if letra == "R" else "Terreno/fração"
        campos["tipo_imovel"] = palpite
        de_onde["tipo_imovel"] = (
            f"a ficha não tem tipo, e o do acervo rural desta casa é "
            f"«Fazenda/Sítio/Chácara»" if letra == "R" else
            "a ficha não tem tipo — «Terreno/fração», que é o menos afirmativo")
        avisos.append(
            f"O tipo do imóvel vai como «{palpite}» porque a ficha não o tem. "
            f"É o que esta casa grava nas do acervo; troque acima se souber.")

    # ── a conta final ─────────────────────────────────────────────────
    confianca = "alta"
    if nome is None and letra != "U":
        confianca = "baixa"
    elif faltam or any(nome and nome["confianca"] == "baixa" for _ in (0,)):
        confianca = "media"
    if divergente:
        confianca = "baixa"

    return {
        "matricula_id": m.get("id"),
        "numero": str(m.get("numero") or ""),
        "campos": campos,
        "de_onde": de_onde,
        "faltam": faltam,
        "avisos": avisos,
        "bloco": bloco["texto"][:1400],
        "achou_a_marca": bloco["achou"],
        "localizacao": {**leitura, "coluna": coluna, "concorda": not divergente},
        "nome": nome,
        "area": area,
        "confianca": confianca,
        "divergente": divergente,
        # **SÓ SAI PRONTA O QUE NÃO TEM DIVERGÊNCIA E NÃO TEM BURACO.** O que
        # falta não impede a pessoa de completar na mão; o que diverge impede a
        # máquina de decidir sozinha.
        "pode_enviar": not divergente and not faltam,
    }


def propor_do_banco(con: sqlite3.Connection, matricula_id: int,
                    *, settings: dict | None = None,
                    padrao: dict | None = None) -> dict:
    """A mesma proposta, lendo a matrícula do banco.

    **E ELA RECUSA A FICHA SEM TEOR — o guarda entrou em 16/09/2026, junto com a
    primeira porta desta função** (o botão «o que o teor diz», na ficha do
    imóvel). Até então ela só era chamada de script, e o que acontecia sem o
    guarda está medido: numa ficha sem texto, `propor` devolve uma proposta com
    **três campos em `faltam`** (urbano/rural, logradouro e bairro) e com o
    `numero_predial` em «0» — uma linha na fila que não diz nada sobre a ficha e
    que alguém teria de abrir para descobrir isso.

    O extrator lê o TEOR; onde não há teor, não há o que ler. **A ficha é o
    lugar onde isso se diz**, e é para lá que a tela manda a frase.
    """
    linha = banco(con).um(
        "SELECT id, numero, teor, logradouro, numero_predial, bairro, cidade, "
        "uf, cep, rural_urbano, area_valor, area_unidade, tipo_imovel "
        "FROM ri_matriculas WHERE id=%s", (int(matricula_id),))
    if not linha:
        raise EnderecoError(f"A matrícula {matricula_id} não existe.")
    if not (linha["teor"] or "").strip():
        raise EnderecoError(
            f"A matrícula {matricula_id} não tem teor — este extrator lê o "
            "texto da ficha, e nesta não há texto nenhum para ler. Se o "
            "endereço estiver no papel, ele se escreve na própria ficha.")
    return propor(dict(linha), settings=settings, padrao=padrao)


def o_que_ja_tem(m: dict) -> dict:
    """Como estão os campos hoje — é a «outra versão» da tela."""
    return {c: ("" if m.get(c) is None else str(m.get(c))) for c in CAMPOS
            if c in m}


# ═══════════════════════════════════════════════════════════════════════
# 9. A FILA DA CONFERÊNCIA
# ═══════════════════════════════════════════════════════════════════════

A_CONFERIR = "A_CONFERIR"
CONFIRMADA = "CONFIRMADA"
DESCARTADA = "DESCARTADA"

SITUACOES: tuple[str, ...] = (A_CONFERIR, CONFIRMADA, DESCARTADA)

NOME_DA_SITUACAO: dict[str, str] = {
    A_CONFERIR: "Esperando conferência",
    CONFIRMADA: "Conferida e gravada na ficha",
    DESCARTADA: "Descartada",
}


def _json(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def _de_json(v: Any, padrao: Any) -> Any:
    if not v:
        return padrao
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return padrao


def guardar(con: sqlite3.Connection, proposta: dict,
            *, agora: str) -> int:
    """Guarda a proposta. **Não toca em `ri_matriculas`.**

    Uma proposta por matrícula: rodar o extrator de novo sobre uma ficha que já
    foi conferida **não apaga a conferência** — ela só é refeita se a ficha
    ainda não foi decidida. Sem isso, uma segunda passada sobre as 1.443
    desfaria o trabalho de quem conferiu.

    **E ELA DEVOLVE O `id` DA PROPOSTA QUE JÁ EXISTE**, decidida ou não — é o
    que faz a tela poder levar à decisão em vez de mostrar uma linha nova. Quem
    chama não pode supor que o teor que acabou de ler virou o que está gravado:
    numa proposta decidida, o `UPDATE` não roda e o que fica é a leitura antiga.

    **O QUE NÃO ESTÁ CONSTRUÍDO, DECLARADO — 16/09/2026.** Não há como **reabrir
    uma proposta decidida**: `confirmar` e `descartar` exigem `A_CONFERIR`
    (medido: as duas recusam), e `motivo` foi escrito no esquema como «a régua
    da reabertura» desde 15/09 sem que ninguém a tenha construído. O caso que
    dói é a **descartada cuja ficha continua sem endereço** — ela fica sem
    caminho, porque o botão da ficha para na decisão que já existe.

    Não se constrói no palpite, e a razão é medida: **reabrir apaga o motivo
    escrito por uma pessoa** (`decidido_por`, `decidido_em` e `motivo` são
    sobrescritos pelo `UPDATE`). O lugar dessa decisão antiga é uma tabela
    própria, na forma de `ri_minutas`, que guarda o descarte como história em
    vez de o perder — e **quantas vezes isso acontece ainda não foi medido**
    (na fila de 16/09: zero descartadas de 1.443). Quem decide construir é o
    oficial, com esse número na mão.
    """
    mid = proposta.get("matricula_id")
    if not mid:
        raise EnderecoError("A proposta veio sem a matrícula de origem.")
    bd = banco(con)
    antes = bd.um(
        "SELECT logradouro, numero_predial, bairro, cidade, uf, cep, "
        "rural_urbano, area_valor, area_unidade, tipo_imovel "
        "FROM ri_matriculas WHERE id=%s", (int(mid),))
    if not antes:
        raise EnderecoError(f"A matrícula {mid} não existe.")
    bd.escrever(
        "INSERT INTO ri_onr_enderecos (matricula_id, situacao, proposta, "
        " de_onde, faltam, avisos, bloco, confianca, pode_enviar, antes, "
        " calculado_em) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT(matricula_id) DO UPDATE SET "
        "  situacao=excluded.situacao, proposta=excluded.proposta, "
        "  de_onde=excluded.de_onde, faltam=excluded.faltam, "
        "  avisos=excluded.avisos, bloco=excluded.bloco, "
        "  confianca=excluded.confianca, pode_enviar=excluded.pode_enviar, "
        "  antes=excluded.antes, calculado_em=excluded.calculado_em "
        "WHERE ri_onr_enderecos.situacao = %s",
        (int(mid), A_CONFERIR, _json(proposta.get("campos") or {}),
         _json(proposta.get("de_onde") or {}),
         _json(proposta.get("faltam") or []),
         _json(proposta.get("avisos") or []),
         proposta.get("bloco") or "", proposta.get("confianca") or "media",
         1 if proposta.get("pode_enviar") else 0,
         _json(o_que_ja_tem(dict(antes))), agora, A_CONFERIR))
    linha = bd.um(
        "SELECT id FROM ri_onr_enderecos WHERE matricula_id=%s",
        (int(mid),))
    return int(linha["id"])


def ler(con: sqlite3.Connection, proposta_id: int) -> dict | None:
    """Uma proposta, já com o JSON aberto e o número da matrícula."""
    r = banco(con).um(
        "SELECT e.*, m.numero AS matricula_numero, m.livro "
        "FROM ri_onr_enderecos e JOIN ri_matriculas m ON m.id=e.matricula_id "
        "WHERE e.id=%s", (int(proposta_id),))
    if not r:
        return None
    d = dict(r)
    d["proposta"] = _de_json(d.get("proposta"), {})
    d["de_onde"] = _de_json(d.get("de_onde"), {})
    d["antes"] = _de_json(d.get("antes"), {})
    d["faltam"] = _de_json(d.get("faltam"), [])
    d["avisos"] = _de_json(d.get("avisos"), [])
    d["pode_enviar"] = bool(d.get("pode_enviar"))
    return d


def listar(con: sqlite3.Connection, *, situacao: str | None = A_CONFERIR,
           somente_prontas: bool = False, somente_divergentes: bool = False,
           confianca: str | None = None, limite: int = 300) -> list[dict]:
    """A fila da conferência.

    **A ordem é a da confiança: primeiro o que está pronto.** Quem abre esta
    tela quer despachar o que não precisa de olho; o que precisa, espera.
    """
    onde, args = [], []
    if situacao:
        onde.append("e.situacao=%s")
        args.append(situacao)
    if somente_prontas:
        onde.append("e.pode_enviar=1")
    if somente_divergentes:
        onde.append("e.confianca='baixa'")
    if confianca:
        onde.append("e.confianca=%s")
        args.append(confianca)
    args.append(int(limite))
    sql = ("SELECT e.id, e.matricula_id, e.situacao, e.confianca, e.pode_enviar, "
           "e.calculado_em, e.decidido_em, e.decidido_por, e.motivo, "
           "e.proposta, e.antes, e.faltam, "
           "m.numero AS matricula_numero, m.livro, m.rural_urbano "
           "FROM ri_onr_enderecos e JOIN ri_matriculas m ON m.id=e.matricula_id")
    if onde:
        sql += " WHERE " + " AND ".join(onde)
    sql += (" ORDER BY CASE e.confianca WHEN 'alta' THEN 1 WHEN 'media' THEN 2 "
            "ELSE 3 END, e.id LIMIT %s")
    saida = []
    for r in banco(con).ler(sql, args):
        d = dict(r)
        d["proposta"] = _de_json(d.get("proposta"), {})
        d["antes"] = _de_json(d.get("antes"), {})
        d["faltam"] = _de_json(d.get("faltam"), [])
        d["pode_enviar"] = bool(d.get("pode_enviar"))
        saida.append(d)
    return saida


def contar(con: sqlite3.Connection) -> dict:
    """Quantas em cada situação, e quantas prontas para ir."""
    bd = banco(con)
    por_situacao = {r["situacao"]: int(r["n"]) for r in bd.ler(
        "SELECT situacao, COUNT(*) AS n FROM ri_onr_enderecos GROUP BY situacao "
        "ORDER BY situacao")}
    prontas = int(bd.valor(
        "SELECT COUNT(*) FROM ri_onr_enderecos WHERE situacao=%s AND "
        "pode_enviar=1", (A_CONFERIR,)))
    return {"por_situacao": por_situacao,
            "a_conferir": por_situacao.get(A_CONFERIR, 0),
            "prontas": prontas,
            "divergentes": int(bd.valor(
                "SELECT COUNT(*) FROM ri_onr_enderecos WHERE situacao=%s AND "
                "confianca='baixa'", (A_CONFERIR,)))}


# Os campos que a conferência pode gravar. **`rural_urbano` e `tipo_imovel`
# estão aqui**, e não só o endereço: eles são o que o teor desmente e o que
# falta para o indicador fechar, e deixá-los de fora faria a pessoa corrigir a
# rua e continuar sem poder enviar.
CAMPOS_QUE_A_CONFERENCIA_GRAVA: tuple[str, ...] = CAMPOS


def confirmar(con: sqlite3.Connection, proposta_id: int, *,
              agora: str, usuario: str = "",
              ajustes: dict | None = None) -> dict:
    """Grava na ficha o que foi conferido. **Na mesma transação da marca.**

    **Não sobrescreve o que já está lá.** Se alguém digitou o bairro na ficha
    entre a proposta e a confirmação, quem digitou vale mais — e o campo que
    ficou de fora volta na resposta, para a tela dizer qual foi. É a regra do
    CNM (`O QUE SE CALCULA PODE SER MOSTRADO SEM SER GRAVADO`), e ela existe
    porque a proposta é de uma máquina e o que está na ficha é de uma pessoa.

    **`ajustes` é o que a pessoa corrigiu na tela** — os campos vazios que ela
    preencheu à mão. O que não vier neles vai como a proposta o calculou.
    """
    p = ler(con, proposta_id)
    if not p:
        raise EnderecoError("Esta proposta de endereço não existe.")
    if p["situacao"] != A_CONFERIR:
        # **«RODAR O EXTRATOR DE NOVO CRIA OUTRA» ERA FALSO, e sai da frase que a
        # pessoa lê.** Medido, e não suposto: `guardar` garante uma proposta por
        # matrícula (`UNIQUE(matricula_id)`) e, numa decidida, o `UPDATE` não
        # roda — rodar de novo **não cria nada**. A frase mandava procurar um
        # caminho que não existe. O que há é um só: a decisão já tomada, à vista
        # na tela própria. (Reabrir é outra coisa, e não está construído — ver
        # `guardar`.)
        raise EnderecoError(
            f"Esta proposta já foi {NOME_DA_SITUACAO.get(p['situacao'], p['situacao']).lower()}"
            f" por {p.get('decidido_por') or 'alguém'}"
            f"{' em ' + str(p['decidido_em'])[:16] if p.get('decidido_em') else ''}."
            f" Uma proposta por matrícula, e a decisão de quem conferiu vale mais"
            f" que uma segunda leitura — ela está na tela da proposta.")

    bd = banco(con)
    atual = bd.um(
        "SELECT logradouro, numero_predial, bairro, cidade, uf, cep, "
        "rural_urbano, area_valor, area_unidade, tipo_imovel "
        "FROM ri_matriculas WHERE id=%s", (int(p["matricula_id"]),))
    if not atual:
        raise EnderecoError(
            f"A matrícula {p['matricula_id']} não existe mais.")
    atual = dict(atual)

    proposto = dict(p["proposta"])
    for campo, valor in (ajustes or {}).items():
        if campo in CAMPOS_QUE_A_CONFERENCIA_GRAVA:
            proposto[campo] = valor

    vao, ficaram = {}, []
    for campo in CAMPOS_QUE_A_CONFERENCIA_GRAVA:
        if not _vazio(atual.get(campo)):
            if not _vazio(proposto.get(campo)) and \
                    str(atual[campo]).strip() != str(proposto[campo]).strip():
                ficaram.append(campo)
            continue
        if _vazio(proposto.get(campo)):
            continue
        vao[campo] = str(proposto[campo]).strip()

    if vao:
        conjuntos = ", ".join(f"{c}=%s" for c in vao)
        bd.escrever(f"UPDATE ri_matriculas SET {conjuntos} WHERE id=%s",
                    [*vao.values(), int(p["matricula_id"])])
    bd.escrever(
        "UPDATE ri_onr_enderecos SET situacao=%s, decidido_em=%s, decidido_por=%s, "
        "motivo=%s, gravado=%s, preservado=%s WHERE id=%s",
        (CONFIRMADA, agora, usuario,
         ("ficaram como estavam: " + ", ".join(ficaram)) if ficaram else "",
         _json(vao), _json(ficaram), int(proposta_id)))
    return {"gravados": vao, "preservados": ficaram,
            "matricula_id": p["matricula_id"],
            "matricula_numero": p.get("matricula_numero")}


def descartar(con: sqlite3.Connection, proposta_id: int, *, motivo: str,
              agora: str, usuario: str = "") -> None:
    """Tira a proposta da fila. **Exige motivo escrito.**

    Descartar diz «esta leitura não serve», e quem for olhar depois precisa
    saber por quê — é a régua da reabertura do RI e da dispensa do usucapião.
    """
    if not (motivo or "").strip():
        raise EnderecoError(
            "Descartar uma proposta exige o motivo escrito: quem olhar esta "
            "ficha depois precisa saber por que a leitura não servia.")
    p = ler(con, proposta_id)
    if not p:
        raise EnderecoError("Esta proposta de endereço não existe.")
    if p["situacao"] == CONFIRMADA:
        raise EnderecoError(
            "Esta proposta já foi confirmada e gravada na ficha. O que está "
            "lá se corrige na própria ficha, com rastro.")
    banco(con).escrever(
        "UPDATE ri_onr_enderecos SET situacao=%s, decidido_em=%s, decidido_por=%s, "
        "motivo=%s WHERE id=%s",
        (DESCARTADA, agora, usuario, motivo.strip(), int(proposta_id)))


def gerar(con: sqlite3.Connection, *, agora: str, settings: dict | None = None,
          limite: int = 5000, so_do_ocr: bool = False) -> dict:
    """Roda o extrator sobre as fichas que não conseguem ir ao índice.

    **O critério é o do próprio indicador**, e não uma lista escrita à mão: as
    fichas cujo endereço está incompleto — o endereço que já está digitado não
    gera proposta, e isso vale nos dois modos.

    **`so_do_ocr` NASCE `False`, e isto é decisão do oficial** — 15/09/2026,
    perguntado se o extrator deveria olhar só as 39 fichas do OCR novo ou
    também o acervo: *«Mandar tudo, inclusive o acervo»*. A primeira versão
    nascia `True`, e o número que a desmentiu foi **1.443** fichas com teor e
    sem endereço contra as **39** que ele alcançava: o acervo do E-Ofício é
    **1.399** delas, e é ele que o índice nacional não vê.

    > **A opção fica, e não é sobra.** Rodar só o OCR é o que se quer depois de
    > uma importação nova, quando as 1.443 já foram conferidas — sem ela, cada
    > rodada reproporia o acervo inteiro e a proposta confirmada não seria
    > tocada (o `WHERE situacao` do `guardar` a preserva), mas a fila da
    > conferência se encheria de linha já decidida.
    """
    bd = banco(con)
    onde = ["(m.teor IS NOT NULL AND TRIM(m.teor) <> '')",
            "(m.logradouro IS NULL OR TRIM(m.logradouro) = '')"]
    if so_do_ocr:
        onde.append("(m.origem ILIKE 'PDF_OCR%%')")
    linhas = bd.ler(
        "SELECT m.id, m.numero, m.teor, m.logradouro, m.numero_predial, "
        "m.bairro, m.cidade, m.uf, m.cep, m.rural_urbano, m.area_valor, "
        "m.area_unidade, m.tipo_imovel, m.origem "
        "FROM ri_matriculas m WHERE " + " AND ".join(onde)
        + " ORDER BY m.id LIMIT %s", (int(limite),))
    padrao = padrao_da_casa(settings)
    feito = {"lidas": 0, "prontas": 0, "com_buraco": 0, "divergentes": 0,
             "sem_nome": 0, "sem_marca": 0}
    for linha in linhas:
        m = dict(linha)
        p = propor(m, padrao=padrao)
        guardar(bd, p, agora=agora)
        feito["lidas"] += 1
        if p["pode_enviar"]:
            feito["prontas"] += 1
        if p["faltam"]:
            feito["com_buraco"] += 1
        if p["divergente"]:
            feito["divergentes"] += 1
        if p["nome"] is None and p["campos"].get("rural_urbano") != "U":
            feito["sem_nome"] += 1
        if not p["achou_a_marca"]:
            feito["sem_marca"] += 1
    return feito


# ═══════════════════════════════════════════════════════════════════════
# O QUE ESTE MÓDULO ACHOU DE ERRADO — e o que foi feito com cada um
# ═══════════════════════════════════════════════════════════════════════
#
# **1. O CONVERSOR DE ÁREA NÃO ACERTAVA, E EU HAVIA ESCRITO AQUI QUE ELE
# ACERTAVA — corrigido em 15/09/2026.**
#
# Neste lugar estava escrito: «`_inteiro(area_valor)` está CERTO para hectare, e
# isso me desmentiu», com três exemplos ao lado (`231,00,00`, `231,0233`,
# `09,00,00`) — **os três com vírgula**. A conclusão era verdadeira para eles e
# falsa para a maioria: medido nas **1.387** matrículas com unidade `ha`,
# **1.298** trazem o hectare inteiro e sem separador (`63`, `131`, `1`, `9`),
# porque a coluna não guardou os ares e os centiares. `_inteiro('63')` devolvia
# **63**, e o indicador real ia ao índice nacional dizendo que a fazenda tem
# **63 m²** — dez mil vezes menos.
#
# **O erro não foi da função: foi de ter medido três exemplos e concluído sobre
# 1.387.** É a forma mais convincente do carimbo que mente, porque os três
# exemplos eram reais.
#
# A conversão passou a morar em `onr_api.area_em_metros` — **uma definição só na
# casa**, usada por `montar_indicador` e por este módulo —, e as **18** fichas de
# 4 e 5 dígitos sem separador (`3808`, `1154`) devolvem `None`: ali não dá para
# saber se é hectares ou metros, e chutar erra por cem vezes. A proposta as
# declara em vez de as inventar.
#
# **2. O PONTO DECIMAL DAS `m2`, corrigido junto — é o mesmo defeito menor.**
# Nas **11** matrículas com unidade `m2` e separador, o ponto é decimal em todas
# (`9.7`, `31.47`, `0.1`). Lidas como milhar davam 9, 31 e **0** — e zero num
# campo de área é a afirmação de que o imóvel não tem área. `_metros_quadrados`
# guarda a régua medida, e zero devolve `None`.
#
# **3. O QUE CONTINUA DECLARADO, E NÃO SE CONSERTOU:** a coluna `area_unidade`
# mente em 7 fichas — diz `ha` e guarda o número já em metros (`2310233`), que
# só vão certas porque 6+ dígitos são lidos como metros. A ficha da matrícula
# 3.236 diz `231,00,00 Há`, que é o mesmo número escrito direito. **A área vai
# lida do teor**, onde está escrita com a unidade ao lado, e é por isso que o
# extrator a lê de lá antes de olhar a coluna.
