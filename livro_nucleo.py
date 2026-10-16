"""
O nucleo do livro — a geometria de livro, folha, pagina e ordem, para as SEIS
atribuicoes.

POR QUE UM NUCLEO, E NAO UM MODULO POR ATRIBUICAO
    A inspecao de 12/08/2026 pede a MESMA coisa a todas as atribuicoes novas:
    inutilizar folha e verso em branco (RCPN, Protesto, RCPJ e RTD), assinatura
    ao final de cada ato (RCPN e RCPJ), termo de abertura e encerramento
    (RCPN e Protesto), rubrica de folhas (Protesto), encerramento diario do
    livro de protocolo (Protesto e RCPJ) e continuidade da numeracao ao migrar
    do livro fisico (RCPN).

    Isto ja existe, escrito e testado, em `notas_livro.py`. Escrever de novo,
    quatro vezes, seria fabricar quatro versoes divergentes do codigo mais
    dificil do sistema. E o custo da divergencia acabou de ser medido: em
    18/08/2026 a numeracao de matricula, contada por VOLUME em vez de por
    SERVENTIA, abriu a matricula 4011 depois de a 4013 ja existir.

    O E-Oficio, alias, tinha chegado a mesma conclusao onde pode: RTD e RCPJ
    compartilham as tabelas `livroTDPJ` e `tbTipoLivros_TDPJ`, e um unico
    controlador, `tbTD_Propriedade`, conta os dois.

O QUE VARIA DE UMA SERIE PARA OUTRA, E O QUE NAO VARIA
    Nao varia: existe livro, o livro tem folhas, a folha tem frente e verso, o
    registro ocupa lugar, o livro abre com termo e fecha com termo, o que sobra
    em branco se inutiliza.

    Varia, e por isso cada serie declara o seu:

      folhas          quantas folhas o livro tem
      por_face        quantos registros cabem em UMA FACE (frente ou verso)
      usa_verso       se o verso da folha e escriturado
      folha_nova      se cada registro comeca em folha nova
      paginas_pares   se o registro tem de ocupar folhas inteiras
      transborda      se o ultimo registro pode passar do fim do livro
      termo_continuo  se a numeracao segue de um livro para o outro
      numeracao_diaria se a numeracao reinicia a cada dia (e o contrario do
                      anterior; quem manda no codigo e este)

    Os numeros de cada serie abaixo NAO foram escolhidos: sairam do acervo do
    E-Oficio — `tbPropriedadeRCPN`, `tbTD_Propriedade`, `tbLivros_Setup`,
    `tbLivroApontamento` e `tbLivro_Registro_Pagamento`.

O QUE ESTE MODULO NAO FAZ
    Nao toca no banco. E geometria e regra: dada uma serie, o estado de um
    livro e o tamanho de um registro, ele diz onde o registro cai, se cabe, o
    que sobra e o que precisa ser inutilizado. Quem grava e o modulo da
    atribuicao, dentro da transacao dele.

FUNDAMENTO
    Lei 8.935/1994, art. 30, I e art. 46.
    Lei 6.015/1973, arts. 3o a 6o (escrituracao dos livros do registro civil).
    Codigo de Normas do Foro Extrajudicial do Maranhao — Provimento TJMA n. 28,
        de 23/04/2026 — Secao "Dos Livros e da sua Escrituracao".

    Como no resto do sistema: onde o artigo nao foi lido em fonte primaria,
    cita-se a SECAO. Nenhum numero foi inventado.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import atribuicoes as ATR


class LivroError(ValueError):
    """Impedimento de regra, com mensagem pronta para a tela."""


PAGINAS_POR_FOLHA = 2


# ------------------------------------------------------------- por extenso

_UNIDADES = ("", "um", "dois", "tres", "quatro", "cinco", "seis", "sete",
             "oito", "nove", "dez", "onze", "doze", "treze", "catorze",
             "quinze", "dezesseis", "dezessete", "dezoito", "dezenove")
_DEZENAS = ("", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta",
            "setenta", "oitenta", "noventa")
_CENTENAS = ("", "cento", "duzentos", "trezentos", "quatrocentos",
             "quinhentos", "seiscentos", "setecentos", "oitocentos",
             "novecentos")

# "duzentas folhas", nao "duzentos folhas". Palavra por palavra, porque
# "duzentos" nao contem "centos" e uma troca por pedaco de string erraria em
# metade das centenas — foi o primeiro jeito que tentei, e errou.
_FEMININO = {
    "um": "uma", "dois": "duas",
    "duzentos": "duzentas", "trezentos": "trezentas",
    "quatrocentos": "quatrocentas", "quinhentos": "quinhentas",
    "seiscentos": "seiscentas", "setecentos": "setecentas",
    "oitocentos": "oitocentas", "novecentos": "novecentas",
}


def _ate_999(n: int) -> str:
    if n == 100:
        return "cem"
    partes = []
    if n >= 100:
        partes.append(_CENTENAS[n // 100])
        n %= 100
    if n >= 20:
        partes.append(_DEZENAS[n // 10])
        n %= 10
        if n:
            partes.append(_UNIDADES[n])
    elif n:
        partes.append(_UNIDADES[n])
    return " e ".join(partes)


# Acima disto o modulo devolve so o algarismo, em vez de estourar.
#
# NAO E ZELO EXCESSIVO. `folhas` e `paginas` chegam de campo de formulario, e
# um 1000000 digitado por engano ia parar em `_ate_999(1000)`, que indexa
# `_CENTENAS[10]` e levanta IndexError — HTTP 500 na cara do escrevente, no
# meio de um encerramento de livro. Numero por extenso e acabamento do termo;
# nao pode derrubar o ato.
LIMITE_POR_EXTENSO = 999_999


def por_extenso(n: int, feminino: bool = False) -> str:
    """O numero em palavras, ate 999.999. Acima disso, o proprio algarismo.

    O art. 795, § 4º, do Codigo de Normas manda escrever por extenso COM
    REPETICAO EM ALGARISMOS. E por isso que `com_algarismos()` existe logo
    abaixo, e nao porque fique bonito.
    """
    n = int(n)
    if n == 0:
        return "zero"
    if n < 0:
        return f"menos {por_extenso(-n, feminino)}"
    if n > LIMITE_POR_EXTENSO:
        return str(n)
    if n >= 1000:
        milhares, resto = divmod(n, 1000)
        cabeca = "mil" if milhares == 1 else f"{_ate_999(milhares)} mil"
        if not resto:
            return cabeca
        ligacao = " e " if resto < 100 or resto % 100 == 0 else " "
        return cabeca + ligacao + por_extenso(resto, feminino)
    texto = _ate_999(n)
    if feminino:
        texto = " ".join(_FEMININO.get(p, p) for p in texto.split(" "))
    return texto


def com_algarismos(n: int, feminino: bool = False) -> str:
    """`200 (duzentas)` — a forma que o art. 795, § 4º exige."""
    return f"{int(n)} ({por_extenso(n, feminino)})"



# ------------------------------------------------------------ a serie


@dataclass(frozen=True)
class Serie:
    """Uma serie de livros: o Livro A do RCPN, o de Apontamento do Protesto...

    `codigo` e a chave interna e nunca muda, porque vai gravada em cada
    registro. `nome` e o que sai impresso no termo.
    """

    codigo: str
    atribuicao: int
    nome: str
    folhas: int = 200
    # POR FACE, e nao por folha. Este campo se chamava `por_folha` e a
    # ambiguidade era real: o texto dizia "por folha" e o codigo que acha o
    # proximo lugar contava por FACE. Num livro que escritura o verso, os dois
    # diferem pelo dobro — e errar por dois num livro de protocolo poe o
    # protocolo 51 na folha 2 quando ele e da folha 1.
    por_face: int = 1
    usa_verso: bool = True
    folha_nova: bool = True
    paginas_pares: bool = False
    transborda: bool = False
    termo_continuo: bool = True
    # Livro que se encerra todo dia, e nao quando enche: o de protocolo.
    diario: bool = False
    # Numeracao que REINICIA a cada dia, em vez de correr contínua.
    #
    # `tbProtocoloProtesto` guarda um `intProtocolo_Ultimo` POR DATA, com
    # valores de 1 a 6 — o protocolo do protesto e numerado por dia, e nao
    # continuamente. Isto nao e detalhe: numeracao contínua num livro de
    # numeracao diaria faz o protocolo do dia sair como 2.157 em vez de 3.
    numeracao_diaria: bool = False
    observacao: str = ""
    exigencias: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if self.folhas < 1:
            raise LivroError(f"A série {self.codigo} declara {self.folhas} folhas.")
        if self.por_face < 1:
            raise LivroError(
                f"A série {self.codigo} declara {self.por_face} registros por face.")
        if self.paginas_pares and not self.usa_verso:
            raise LivroError(
                f"A série {self.codigo} pede páginas pares sem escriturar o verso — "
                f"são regras que se contradizem: sem verso, toda folha é uma página.")
        if self.termo_continuo and self.numeracao_diaria:
            raise LivroError(
                f"A série {self.codigo} diz que a numeração é contínua de um "
                f"livro para o outro e, ao mesmo tempo, que reinicia a cada "
                f"dia. São regras que se contradizem.")
        if self.por_face > 1 and self.folha_nova:
            raise LivroError(
                f"A série {self.codigo} diz que cabem {self.por_face} registros por "
                f"face e, ao mesmo tempo, que cada registro começa em folha nova.")

    @property
    def paginas(self) -> int:
        """Paginas escrituraveis do livro."""
        return self.folhas * (PAGINAS_POR_FOLHA if self.usa_verso else 1)

    @property
    def capacidade(self) -> int:
        """Quantos registros o livro comporta, quando isso e calculavel.

        Serie de folha nova comporta uma folha por registro. Serie com varios
        por folha multiplica. Serie de tamanho de registro variavel — as notas —
        nao tem capacidade em registros, e devolve 0: quem manda ali e o
        tamanho do teor, nao a contagem.
        """
        if self.paginas_pares:
            return 0
        if self.folha_nova:
            # Um registro por folha: o verso, quando usado, e do mesmo
            # registro. Contar as duas faces daria o dobro da verdade.
            return self.folhas
        return self.folhas * self.por_face * (PAGINAS_POR_FOLHA if self.usa_verso else 1)


# --------------------------------------------------- as series da serventia
#
# Cada numero abaixo tem procedencia. Onde eu nao sei, esta escrito que nao sei.

SERIES: dict[str, Serie] = {}


def _registrar(s: Serie) -> Serie:
    if s.codigo in SERIES:
        raise LivroError(f"Série repetida: {s.codigo}")
    SERIES[s.codigo] = s
    return s


# ---- Tabelionato de Notas (atribuicao 1)
#
# A regra desta serventia, definida pelo delegatario em 17/08/2026: cada ato em
# folha nova, conta-se frente e verso, e o ato ocupa folhas inteiras — logo
# paginas pares. Capacidade de `tbLivros_Setup`: 200 folhas.
for _cod, _nome in (
    ("NT_ESCRITURA", "Livro de Escrituras"),
    ("NT_PROCURACAO", "Livro de Procurações"),
    ("NT_SUBSTABELECIMENTO", "Livro de Substabelecimentos"),
    ("NT_TESTAMENTO", "Livro de Testamentos"),
    ("NT_TESTAMENTO_CERRADO", "Livro de Testamentos Cerrados"),
    ("NT_ATA", "Livro de Atas Notariais"),
):
    _registrar(Serie(
        codigo=_cod, atribuicao=1, nome=_nome, folhas=200, por_face=1,
        usa_verso=True, folha_nova=True, paginas_pares=True, termo_continuo=True,
        observacao="Regra da serventia de 17/08/2026: cada ato em folha nova, "
                   "frente e verso, folhas inteiras.",
        exigencias=("inutilizar o verso que sobrar",),
    ))

# ---- Protesto (atribuicao 2)
#
# MEDIDO NO ACERVO EM 21/08/2026, e nao mais estimado.
#
# `tbPropProtesto` declara NFL = 200 folhas e NAF = 52 apontamentos por folha.
# `tbLivroApontamento` confirma: o E-Oficio PRE-CRIOU 10.400 linhas por livro
# — exatamente 200 x 52 — e das 34 folhas escrituradas do Livro 1, trinta e
# tres tem 52 apontamentos e a corrente tem 49. Nao ha coluna de verso: a
# origem conta 52 por FOLHA sem distinguir face, e e desse livro que sai o
# impresso que esta na estante. Declarar verso aqui poria 104 numa folha de 52
# e faria a nossa numeracao divergir do livro fisico na primeira virada.
#
# O que eu tinha aqui — 10 por folha, "A CONFERIR" — era estimativa. Ficou
# errado por cinco vezes.
_registrar(Serie(
    codigo="PT_APONTAMENTO", atribuicao=2, nome="Livro de Apontamento", folhas=200,
    por_face=52, usa_verso=False, folha_nova=False, termo_continuo=True,
    observacao="Do acervo: tbPropProtesto NFL=200 e NAF=52; tbLivroApontamento "
               "pré-criou 10.400 linhas (200 x 52) e as folhas escrituradas "
               "têm 52 apontamentos cada.",
    exigencias=("termo de abertura e de encerramento",
                "rubricar as folhas",
                "inutilizar versos e espaços em branco"),
))
_registrar(Serie(
    codigo="PT_PROTESTO", atribuicao=2, nome="Livro de Registro de Protestos", folhas=200,
    por_face=1, usa_verso=True, folha_nova=False, termo_continuo=True,
    observacao="UM PROTESTO POR FACE, frente e verso — decisão do oficial "
               "em 14/10/2026: «podemos fazer um protesto por face de "
               "página a partir de agora, não tem por que deixar o verso em "
               "branco». O E-Ofício fazia diferente, e foi medido em 13/10: "
               "um título por FOLHA com o verso em branco (das 34 folhas com "
               "dois registros, 33 são o mesmo protocolo com dois devedores, "
               "e `tbPropProtesto.PFA` anda uma folha por protesto). Essa "
               "medição serviu para CONTAR o número de ordem atual (Livros 1 "
               "a 8 de 200 folhas + Livro 9 até a 182 = 1.782; o próximo, "
               "1.783), e não para a regra daqui em diante.",
    exigencias=("termo de abertura e de encerramento",
                "tipo e motivo individualizados, nunca genéricos"),
))
_registrar(Serie(
    codigo="PT_PAGAMENTO", atribuicao=2, nome="Livro de Registro de Pagamentos", folhas=200,
    por_face=120, usa_verso=False, folha_nova=False, termo_continuo=True,
    observacao="Do acervo: tbLivro_Registro_Pagamento, Livro 1, ordens 826 a "
               "2145 em 11 folhas — 1.320 registros, exatamente 120 por folha. "
               "Sem coluna de verso na origem, como no Apontamento.",
    exigencias=("registrar o pagamento no campo Ocorrências do Livro de Protocolo",),
))
_registrar(Serie(
    codigo="PT_PROTOCOLO", atribuicao=2, nome="Livro de Protocolo do Protesto", folhas=200,
    por_face=50, usa_verso=True, folha_nova=False, termo_continuo=False,
    diario=True, numeracao_diaria=True,
    observacao="`tbProtocoloProtesto` guarda um intProtocolo_Ultimo POR DATA, "
               "com valores de 1 a 6 — o protocolo do protesto REINICIA a cada "
               "dia. Quantos cabem por face continua A CONFERIR no livro "
               "físico; a origem não declara.",
    exigencias=("encerramento diário", "campo de Ocorrências por protocolo"),
))

# ---- Registro Civil das Pessoas Juridicas (atribuicao 3)
#
# Livros e teor legal de `tbTipoLivros_TDPJ`. Estado de `tbTD_Propriedade`:
# livro atual 4, 300 folhas, 1 registro por pagina, usa verso, e a averbacao
# NAO consome protocolo.
_registrar(Serie(
    codigo="PJ_A", atribuicao=3, nome="Livro A do Registro Civil das Pessoas Jurídicas",
    folhas=300, por_face=1, usa_verso=True, folha_nova=True, transborda=True,
    termo_continuo=True,
    observacao="Contratos, atos constitutivos, estatutos e compromissos de "
               "sociedades civis, fundações, associações de utilidade pública e "
               "partidos políticos.",
    exigencias=("assinatura do delegatário ao final de cada ato",
                "inutilizar folhas em branco remanescentes"),
))
_registrar(Serie(
    codigo="PJ_B", atribuicao=3, nome="Livro B do Registro Civil das Pessoas Jurídicas",
    folhas=300, por_face=1, usa_verso=True, folha_nova=True, transborda=True,
    termo_continuo=True,
    observacao="Matrícula de oficinas impressoras, jornais, periódicos, "
               "empresas de radiodifusão e agências de notícias.",
    exigencias=("assinatura do delegatário ao final de cada ato",),
))
_registrar(Serie(
    codigo="PJ_PROTOCOLO", atribuicao=3, nome="Livro de Protocolo do RCPJ",
    folhas=300, por_face=50, usa_verso=True, folha_nova=False, diario=True,
    termo_continuo=True,
    observacao="`tbTD_Propriedade.intLivroAtual_PPJ` = 1, protocolo em 1.273.",
    exigencias=("encerramento diário e assinaturas",),
))

# ---- Registro de Titulos e Documentos (atribuicao 4)
#
# Mesma estrutura do RCPJ, e a averbacao AQUI consome protocolo
# (`bitIncrementoProtocoloAVTD` = verdadeiro).
_registrar(Serie(
    codigo="TD_B", atribuicao=4, nome="Livro B do Registro de Títulos e Documentos",
    folhas=300, por_face=1, usa_verso=True, folha_nova=True, transborda=True,
    termo_continuo=True,
    observacao="Trasladação integral de títulos e documentos.",
    exigencias=("inutilizar folhas em branco remanescentes",),
))
_registrar(Serie(
    codigo="TD_C", atribuicao=4, nome="Livro C do Registro de Títulos e Documentos",
    folhas=300, por_face=1, usa_verso=True, folha_nova=True, transborda=True,
    termo_continuo=True,
    observacao="Inscrição por extração, para efeitos contra terceiros e "
               "autenticação de data.",
))
_registrar(Serie(
    codigo="TD_F", atribuicao=4, nome="Livro F do Registro de Títulos e Documentos",
    folhas=300, por_face=1, usa_verso=True, folha_nova=True, transborda=True,
    termo_continuo=True,
    observacao="Registro facultativo para conservação — Lei 6.015/1973, "
               "art. 127, VII, e art. 127-A.",
))
_registrar(Serie(
    codigo="TD_PROTOCOLO", atribuicao=4, nome="Livro de Protocolo do RTD",
    folhas=300, por_face=50, usa_verso=True, folha_nova=False, diario=True,
    termo_continuo=True,
    observacao="`tbTD_Propriedade.intLivroAtual_PTD` = 1, protocolo em 1.275.",
))

# ---- Registro Civil das Pessoas Naturais (atribuicao 6)
#
# Tudo de `tbPropriedadeRCPN`, e cada linha bate com o que a inspecao apontou:
# nascimento no livro 24 (a inspecao diz "A-24"), casamento no 4 ("B-04"),
# obito no 5 ("C-05"), proclamas no 3 ("D-03"). 300 folhas, UM registro por
# folha.
_registrar(Serie(
    codigo="RC_A", atribuicao=6, nome="Livro A — Registro de Nascimento",
    folhas=300, por_face=1, usa_verso=True, folha_nova=True, termo_continuo=True,
    observacao="Acervo: livro 24, registro 19.552, folha 166.",
    exigencias=("divisão do assento em campos próprios para nota, averbação e "
                "retificação, inclusive no verso",
                "assinaturas do assento",
                "selo, emolumentos, destinações e gratuidade padronizados"),
))
_registrar(Serie(
    codigo="RC_B", atribuicao=6, nome="Livro B — Registro de Casamento",
    folhas=300, por_face=1, usa_verso=True, folha_nova=True, termo_continuo=True,
    observacao="Acervo: livro 4, registro 39, folha 39.",
    exigencias=("divisão do assento em campos próprios",),
))
_registrar(Serie(
    codigo="RC_B_AUXILIAR", atribuicao=6,
    nome="Livro B-Auxiliar — Casamento Religioso com Efeito Civil",
    folhas=300, por_face=1, usa_verso=True, folha_nova=True, termo_continuo=True,
    observacao="Acervo: livro 2. A inspeção manda ENCERRAR o físico e seguir "
               "no sistema, mantendo a continuidade da numeração.",
    exigencias=("encerrar o livro físico preservando o acervo",
                "continuidade da numeração"),
))
_registrar(Serie(
    codigo="RC_C", atribuicao=6, nome="Livro C — Registro de Óbito",
    folhas=300, por_face=1, usa_verso=True, folha_nova=True, termo_continuo=True,
    observacao="Acervo: livro 5, registro 1.976, folha 275.",
    exigencias=("divisão do assento em campos próprios",
                "um registro por folha plástica, em sequência numérica regular",
                "selos, emolumentos e destinações completos"),
))
_registrar(Serie(
    codigo="RC_C_AUXILIAR", atribuicao=6, nome="Livro C-Auxiliar — Natimortos",
    folhas=300, por_face=1, usa_verso=True, folha_nova=True, termo_continuo=True,
    observacao="Acervo: livro 2, registro 12.",
    exigencias=("encerrar o livro físico preservando o acervo",
                "continuidade da numeração"),
))
_registrar(Serie(
    codigo="RC_D", atribuicao=6, nome="Livro D — Registro de Proclamas",
    folhas=300, por_face=1, usa_verso=True, folha_nova=True, termo_continuo=True,
    observacao="Acervo: livro 3, registro 1.358, folha 126.",
    exigencias=("divisão do assento em campos próprios",),
))
_registrar(Serie(
    codigo="RC_E", atribuicao=6, nome="Livro E — Demais Atos do Registro Civil",
    folhas=150, por_face=1, usa_verso=True, folha_nova=True, termo_continuo=True,
    observacao="Acervo: livro 2, folha 39, 150 folhas.",
))


# ---------------------------------------------------------------- consultas


def serie(codigo: str) -> Serie:
    s = SERIES.get(str(codigo or "").strip().upper())
    if s is None:
        raise LivroError(f"Série de livro desconhecida: {codigo!r}")
    return s


def series_da(atribuicao: int | str) -> dict[str, Serie]:
    codigo = ATR.codigo_da_atribuicao(atribuicao)
    return {k: v for k, v in SERIES.items() if v.atribuicao == codigo}


def exigencias_da_inspecao() -> dict[str, tuple[str, ...]]:
    """O que a inspecao cobra, serie por serie. Serve de checklist."""
    return {k: v.exigencias for k, v in SERIES.items() if v.exigencias}


# -------------------------------------------------------------- geometria


def rotulo_folha(numero: Any, verso: bool = False) -> str:
    """A folha 12 tem duas paginas: "12" e "12v"."""
    return f"{int(numero)}v" if verso else str(int(numero))


def paginas_de(s: Serie, folhas: int) -> int:
    return int(folhas) * (PAGINAS_POR_FOLHA if s.usa_verso else 1)


def folhas_para(s: Serie, paginas: Any) -> int:
    """Quantas folhas um registro de N paginas ocupa nesta serie."""
    n = max(1, int(paginas or 1))
    if not s.usa_verso:
        return n
    if s.paginas_pares:
        # Folhas inteiras: 1 pagina ainda gasta a folha toda.
        return (n + 1) // 2
    return (n + PAGINAS_POR_FOLHA - 1) // PAGINAS_POR_FOLHA


def faces_de(s: Serie, folha_inicial: int, paginas: Any) -> list[str]:
    """As faces que um registro ocupa, na ordem: ["14", "14v", "15"]."""
    n = max(1, int(paginas or 1))
    faces: list[str] = []
    folha = int(folha_inicial)
    while len(faces) < n:
        faces.append(rotulo_folha(folha))
        if len(faces) < n and s.usa_verso:
            faces.append(rotulo_folha(folha, verso=True))
        folha += 1
    return faces


def sobra_de(s: Serie, folha_inicial: int, paginas: Any) -> list[str]:
    """As faces que sobram em branco e precisam ser inutilizadas.

    So faz sentido em serie de folha inteira: quem escritura varios registros
    por folha nao deixa sobra, deixa continuacao.
    """
    if not (s.folha_nova and s.usa_verso):
        return []
    n = max(1, int(paginas or 1))
    if n % PAGINAS_POR_FOLHA == 0:
        return []
    ultima = int(folha_inicial) + folhas_para(s, n) - 1
    return [rotulo_folha(ultima, verso=True)]
