"""A remessa do IBGE — os cinco arquivos dos Cartórios Informatizados.

DE ONDE SAI ESTE LAYOUT
    Da especificação oficial do IBGE — *Novas instruções para a geração dos
    arquivos dos cartórios informatizados para o sistema Registro Civil*,
    Diretoria de Informática, COPRE/GESIP, atualizada em 08/01/2015. O oficial
    indicou o caminho em 28/08/2026.

    **E ela foi conferida contra os arquivos que ESTA CASA exportou**, em
    `C:\\ARPNET\\C11\\IBGE_EXP`: a soma dos campos bate com a largura das linhas
    nos três modelos que têm dado — 112 no nascimento, 105 no casamento, 103 no
    óbito — e o resumo RC-10 bate em 68.

    Antes de achar a especificação, este layout tinha sido medido a partir dos
    arquivos: dia e mês do registro, data de nascimento, sexo, municípios e o
    número da DN saíram do cruzamento de 28 linhas com 28 assentos do acervo. A
    especificação confirmou os oito campos medidos e explicou os seis que a
    medição não tinha alcançado — local do nascimento, gêmeo, os países e a
    idade da genitora. Ver `LAYOUT_IBGE_MEDIDO.md`.

A REGRA DE ALINHAMENTO, e ela não é a mesma para os dois tipos
    `CHAR` alinha à ESQUERDA e completa com espaço; `NUM` alinha à DIREITA e
    completa com zero. É o que os arquivos reais mostram — `NUM-LIVRO` é
    `'A24         '` e `NUM-REGLIV` é `'0019506'` no RC-10 e `'19506  '` no
    modelo de nascimento, que declara o campo como NUM mas grava alinhado à
    esquerda.

    > **O modelo de nascimento contraria a própria especificação nesse campo**,
    > e o que vale é o arquivo que o IBGE aceitou desta casa. Está registrado em
    > `ALINHAMENTO_A_ESQUERDA`, com o motivo — não é engano, é observação.
"""
from __future__ import annotations

from typing import Any

# ------------------------------------------------------------ os layouts
#
# Cada campo: (nome, tipo, tamanho). A ordem É o layout.

NASCIMENTO: tuple[tuple[str, str, int], ...] = (
    ("UF-PESQUISA", "CHAR", 2), ("MUN-PESQUISA", "CHAR", 5),
    ("DIST-PESQUISA", "CHAR", 2), ("COD_CARTORIO", "CHAR", 2),
    ("TRIM-PESQUISA", "CHAR", 1), ("ANO-PESQUISA", "CHAR", 2),
    ("NUM-LIVRO", "CHAR", 12), ("NUM-REGLIV", "NUM", 7),
    ("DATAREGDIA", "NUM", 2), ("DATAREGMES", "NUM", 2),
    ("DATA-NASC", "CHAR", 8), ("LOCAL-NASC", "NUM", 1),
    ("COD-UF-NASC", "CHAR", 2), ("COD-MUNIC-NASC", "CHAR", 5),
    ("GEMEO", "NUM", 1), ("SEXO", "NUM", 1),
    ("COD-UF-NASC-PAI", "CHAR", 2), ("COD-PAIS-NASC-PAI", "CHAR", 3),
    ("COD-UF-NASC-MAE", "CHAR", 2), ("COD-PAIS-NASC-MAE", "CHAR", 3),
    ("COD-UF-RES-MAE", "CHAR", 2), ("COD-MUNIC-RES-MAE", "CHAR", 5),
    ("COD-PAIS-RES-MAE", "CHAR", 3), ("IDADE-GENI", "NUM", 2),
    ("DN", "CHAR", 35),
)

CASAMENTO: tuple[tuple[str, str, int], ...] = (
    ("UF-PESQUISA", "CHAR", 2), ("MUN-PESQUISA", "CHAR", 5),
    ("DIST-PESQUISA", "CHAR", 2), ("COD_CARTORIO", "CHAR", 2),
    ("TRIM-PESQUISA", "CHAR", 1), ("ANO-PESQUISA", "CHAR", 2),
    ("NUM-LIVRO", "CHAR", 12), ("NUM-REGLIV", "NUM", 7),
    ("DATAREGDIA", "NUM", 2), ("DATAREGMES", "NUM", 2),
    ("DATA-CASAM", "CHAR", 8),
    ("SEXO-CONJ1", "NUM", 1), ("SEXO-CONJ2", "NUM", 1),
    ("ESTCIV-CONJ1", "NUM", 1), ("ESTCIV-CONJ2", "NUM", 1),
    ("DT-NASC-CONJ1", "CHAR", 8), ("DT-NASC-CONJ2", "CHAR", 8),
    ("COD-UF-NASC-CONJ1", "CHAR", 2), ("COD-MUNIC-NASC-CONJ1", "CHAR", 5),
    ("COD-PAIS-NASC-CONJ1", "CHAR", 3),
    ("COD-UF-NASC-CONJ2", "CHAR", 2), ("COD-MUNIC-NASC-CONJ2", "CHAR", 5),
    ("COD-PAIS-NASC-CONJ2", "CHAR", 3),
    ("COD-UF-RES-CONJ1", "CHAR", 2), ("COD-MUNIC-RES-CONJ1", "CHAR", 5),
    ("COD-PAIS-RES-CONJ1", "CHAR", 3),
    ("COD-UF-RES-CONJ2", "CHAR", 2), ("COD-MUNIC-RES-CONJ2", "CHAR", 5),
    ("COD-PAIS-RES-CONJ2", "CHAR", 3),
)

OBITO: tuple[tuple[str, str, int], ...] = (
    ("UF-PESQUISA", "CHAR", 2), ("MUN-PESQUISA", "CHAR", 5),
    ("DIST-PESQUISA", "CHAR", 2), ("COD_CARTORIO", "CHAR", 2),
    ("TRIM-PESQUISA", "CHAR", 1), ("ANO-PESQUISA", "CHAR", 2),
    ("NUM-LIVRO", "CHAR", 12), ("NUM-REGLIV", "NUM", 7),
    ("DATAREGDIA", "NUM", 2), ("DATAREGMES", "NUM", 2),
    ("DATA-OBITO", "CHAR", 8), ("NATUREZA", "NUM", 1), ("LOCAL", "NUM", 1),
    ("COD-UF-RES", "CHAR", 2), ("COD-MUNIC-RES", "CHAR", 5),
    ("COD-PAIS-RES", "CHAR", 3), ("SEXO", "NUM", 1), ("IDADE", "NUM", 3),
    ("TIPO-TEMPO", "NUM", 1), ("EST-CIV", "NUM", 1),
    ("COD-UF-NASC", "CHAR", 2), ("COD-PAIS-NASC", "CHAR", 3),
    ("DO", "CHAR", 35),
)

RC10: tuple[tuple[str, str, int], ...] = (
    ("UF-PESQUISA", "CHAR", 2), ("MUN-PESQUISA", "CHAR", 5),
    ("DIST-PESQUISA", "CHAR", 2), ("COD_CARTORIO", "CHAR", 2),
    ("TRIM-PESQUISA", "CHAR", 1), ("ANO-PESQUISA", "CHAR", 2),
    ("NUM-LIVRO", "CHAR", 12), ("PRI-TRIMES", "NUM", 7),
    ("ULT-TRIMES", "NUM", 7), ("TNASCIDOS", "NUM", 5),
    ("TCASAMENTO", "NUM", 5), ("TOBITOS", "NUM", 5), ("TOBITOS-FE", "NUM", 5),
    ("ANULADOS", "NUM", 4), ("REPETIDOS", "NUM", 4),
)

ARQUIVOS: dict[str, tuple[tuple[str, str, int], ...]] = {
    "CARTINF01.TXT": NASCIMENTO,
    "CARTINF02.TXT": CASAMENTO,
    "CARTINF03.TXT": OBITO,
    "CARTINF10.TXT": RC10,
}

# OS CAMPOS QUE O ARQUIVO REAL ALINHA À ESQUERDA APESAR DE SEREM `NUM`.
#
#   `NUM-REGLIV` é declarado NUM na especificação, e nos arquivos que esta casa
#   mandou ele aparece `'19506  '` nos modelos de registro — alinhado à
#   esquerda, com espaços — e `'0019506'` no RC-10, com zeros à esquerda.
#
#   Os dois foram aceitos pelo IBGE. Escrever de um jeito só faria o arquivo
#   deixar de ser idêntico ao que a casa já mandou, e a prova de ida e volta é
#   o que garante que o escritor está certo.
ALINHAMENTO_A_ESQUERDA: dict[int, frozenset[str]] = {
    id(NASCIMENTO): frozenset({"NUM-REGLIV"}),
    id(CASAMENTO): frozenset({"NUM-REGLIV"}),
    id(OBITO): frozenset({"NUM-REGLIV"}),
    id(RC10): frozenset(),
}

# O código do Brasil na tabela de países do IBGE — medido nos arquivos reais
# desta casa: `076` nos três campos de país dos 28 nascimentos.
BRASIL = "076"

# A codificação e o terminador dos arquivos, medidos.
CODIFICACAO = "latin-1"
FIM_DE_LINHA = "\r\n"


class IbgeError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcão."""


def largura(layout: tuple[tuple[str, str, int], ...]) -> int:
    """Quantas posições tem uma linha deste modelo. Só calcula."""
    return sum(t for _, _, t in layout)


def posicoes(layout: tuple[tuple[str, str, int], ...]) -> dict[str, tuple[int, int]]:
    """Onde cada campo começa e termina. Só calcula — serve à conferência."""
    saida, i = {}, 0
    for nome, _, tam in layout:
        saida[nome] = (i, i + tam)
        i += tam
    return saida


def montar_linha(layout: tuple[tuple[str, str, int], ...],
                 valores: dict[str, Any]) -> str:
    """Uma linha do arquivo, com cada campo no seu lugar. Só calcula.

    CAMPO MAIOR QUE O TAMANHO É ERRO, E NÃO SE CORTA. Cortar o número de um
    registro produz arquivo que o IBGE aceita e que informa outro registro — e
    estatística errada não volta atrás, porque ninguém a confere depois.

    CAMPO AUSENTE FICA VAZIO, e vazio tem forma: espaço no `CHAR`, zero no
    `NUM`. É o que os arquivos reais mostram nos campos que a casa não
    preencheu.
    """
    a_esquerda = ALINHAMENTO_A_ESQUERDA.get(id(layout), frozenset())
    partes = []
    for nome, tipo, tam in layout:
        bruto = valores.get(nome)
        texto = "" if bruto is None else str(bruto).strip()
        if len(texto) > tam:
            raise IbgeError(
                f"O campo {nome} tem {len(texto)} caracteres e cabem {tam}: "
                f"{texto!r}. Cortar produziria arquivo que informa outra coisa.")
        if tipo == "NUM" and nome not in a_esquerda:
            partes.append(texto.rjust(tam, "0") if texto else "0" * tam)
        else:
            partes.append(texto.ljust(tam))
    return "".join(partes)


def ler_linha(layout: tuple[tuple[str, str, int], ...],
              linha: str) -> dict[str, str]:
    """Os campos de uma linha, como estão. Só calcula.

    SEM INTERPRETAR: devolve o texto de cada posição, e não o significado. É o
    que a prova de ida e volta precisa — e é a regra da casa para campo lido de
    arquivo de terceiro.
    """
    saida, i = {}, 0
    for nome, _, tam in layout:
        saida[nome] = linha[i:i + tam]
        i += tam
    return saida


def escrever(layout: tuple[tuple[str, str, int], ...],
             linhas: list[dict[str, Any]]) -> bytes:
    """O arquivo inteiro, pronto para gravar. Só calcula.

    Em `latin-1` e com `CRLF`, que é o que os arquivos reais desta casa usam.
    Acento em dois bytes empurraria todos os campos da linha para a direita —
    a mesma lição do retorno da CRA.
    """
    corpo = "".join(montar_linha(layout, v) + FIM_DE_LINHA for v in linhas)
    return corpo.encode(CODIFICACAO, errors="replace")


def ler(layout: tuple[tuple[str, str, int], ...],
        conteudo: bytes) -> list[dict[str, str]]:
    """As linhas de um arquivo. Só calcula."""
    texto = conteudo.decode(CODIFICACAO, errors="replace")
    return [ler_linha(layout, x.rstrip("\r"))
            for x in texto.split("\n") if x.strip()]


# ------------------------------------------------------- as tabelas de código
#
# Todas da especificação oficial. Onde ela dá o código, ele fica aqui; onde não
# dá, não se inventa.

LOCAL_DO_NASCIMENTO: dict[int, str] = {
    1: "hospital",
    2: "outros estabelecimentos de saúde sem internação",
    3: "domicílio",
    5: "outros",
    9: "ignorado",
}

GEMEO: dict[int, str] = {
    1: "não é gêmeo",
    2: "gêmeo",
    3: "trigêmeo ou mais",
    9: "ignorado",
}

SEXO: dict[int, str] = {1: "masculino", 2: "feminino", 9: "ignorado"}


# ------------------------------------------- os catálogos do ÓBITO
#
# FECHADOS EM 28/08/2026, e por dois caminhos que se conferiram um ao outro.
#
#   MEDIDOS PRIMEIRO, nas 13 linhas de óbito que esta casa exportou, cruzadas
#   com os 31 óbitos do acervo pelo número do registro:
#
#       Hospital     -> LOCAL 1   (7 linhas)
#       Via Pública  -> LOCAL 4   (1 linha, e é a mesma que traz NATUREZA 2)
#       Outros       -> LOCAL 5   (5 linhas)
#       TIPO-TEMPO 4 nas 13; EST-CIV 1 e 2.
#
#   E CONFIRMADOS DEPOIS pela especificação oficial do IBGE (COPRE/GESIP,
#   08/01/2015), que traz as listas inteiras — inclusive os códigos que a
#   amostra desta casa não mostrou.
#
#   A coincidência importa: a linha de NATUREZA 2 é justamente a morte em via
#   pública de um homem de 26 anos. «Violenta» encaixa; nenhuma outra leitura
#   encaixaria as duas coisas ao mesmo tempo.
NATUREZA_DO_OBITO: dict[int, str] = {
    1: "natural",
    2: "violenta",
    9: "ignorado",
}

# O CATÁLOGO DO ÓBITO NÃO É O DO NASCIMENTO, e a diferença é o `4`: o óbito tem
# «via pública», que o nascimento não tem. Usar um pelo outro mandaria «outros»
# onde o IBGE espera «via pública» — e via pública é a informação que ele mais
# quer, porque é onde a morte violenta acontece.
LOCAL_DO_OBITO: dict[int, str] = {
    1: "hospital",
    2: "outros estabelecimentos de saúde sem internação",
    3: "domicílio",
    4: "via pública",
    5: "outros",
    9: "ignorado",
}

# A UNIDADE DE TEMPO DA IDADE — e ela existe porque o recém-nascido que morre
# tem idade em minutos, não em anos. Sem ela, «2» seria dois anos quando eram
# dois dias.
TIPO_DE_TEMPO: dict[int, str] = {
    0: "minutos", 1: "horas", 2: "dias", 3: "meses", 4: "anos", 9: "ignorado",
}

# O ESTADO CIVIL DO FALECIDO. Repare que **não há 5** — como não há 4 no local
# do nascimento. Catálogo oficial pula número, e quem preencher a sequência
# «óbvia» acerta o tipo do campo e erra o conteúdo.
ESTADO_CIVIL_DO_FALECIDO: dict[int, str] = {
    1: "solteiro",
    2: "casado",
    3: "viúvo",
    4: "separado judicialmente",
    6: "divorciado",
    7: "desquitado",
    9: "ignorado",
}

IDADE_DO_FALECIDO_IGNORADA = 999

# A idade da genitora tem faixa declarada: maior que 9 e até 69; 99 é ignorada.
IDADE_GENITORA_MINIMA = 10
IDADE_GENITORA_MAXIMA = 69
IDADE_IGNORADA = 99

# Os dois códigos de exceção do dia do registro, que valem para todos os
# modelos e que a casa precisa conhecer: eles não são datas.
DIA_REGISTRO_ANULADO = 98
DIA_REGISTRO_ADOCAO = 97
TEXTO_DA_ADOCAO = "ADOCAO COM SEGUNDO REGISTRO"


def trimestre_de(mes: Any) -> int:
    """O trimestre de um mês. Só calcula."""
    m = int(mes)
    if not 1 <= m <= 12:
        raise IbgeError(f"Mês inválido: {mes!r}.")
    return (m - 1) // 3 + 1


def conferir_idade_da_genitora(idade: Any) -> int:
    """A idade, ou 99. Só calcula.

    FORA DA FAIXA VIRA «IGNORADA», E NÃO ERRO. O acervo desta casa tem idade
    `01` gravada em assento de mãe de quarenta e quatro anos — dado velho e
    errado, que não pode impedir a remessa do trimestre inteiro. Mandar 99 diz
    a verdade: a casa não sabe.
    """
    try:
        n = int(str(idade).strip())
    except (TypeError, ValueError):
        return IDADE_IGNORADA
    if IDADE_GENITORA_MINIMA <= n <= IDADE_GENITORA_MAXIMA:
        return n
    return IDADE_IGNORADA
