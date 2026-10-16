"""A folha do livro do Registro Civil — três colunas, frente e verso.

    «Na impressão o termo deve ter três colunas, frente e verso, como prevê a
     lei.» — o oficial, 30/08/2026

    **01/09/2026, manhã:** o papel da folha do livro é **RETRATO**, não
    paisagem. O #38 tinha mandado carta deitada (279 × 215 mm) e o layout da
    impressão saiu errado. Mesma folha que a casa já usava **em pé**:
    215 × 279 mm (carta em retrato — não A4 paisagem).

    | | |
    |---|---|
    | folha | **retrato**, 215 × 279 mm (carta em pé) |
    | coluna 1 — «Número» | **estreita** (~6%): só o número de ordem |
    | coluna 2 — o termo | **~64%** |
    | coluna 3 — «Notas, Averbações e Retificações» | **~30%**; **um só recanto pautado** |

    **Cada coluna tem função:**

    A primeira leva **só o número de ordem** — o nome do registrado NÃO entra
    aí (oficial, 01/09/2026). Fica apertada para sobrar miolo e margem. A
    segunda é o termo. A terceira é **um só campo**: o título «Notas,
    Averbações e Retificações» fica **em cima, fora da pauta**; abaixo, um
    recanto pautado contínuo (passo uniforme). Oficial 01/09/2026, 10:25:
    notas, averbações e retificações juntas em cima e as linhas seguidas
    abaixo. 1ª e 2ª colunas saem **sem** linhas. O verso, quando é essa mesma
    coluna de notas, leva o mesmo recanto pautado.

E A EXIGÊNCIA TEM ENDEREÇO — foi o oficial que o apontou
    **Relatório de Inspeção Ordinária de Cidade Exemplo, 12/08/2026** — o mesmo
    que mora em `inspection_seed.py`:

    | livro | página | prazo | o que exige |
    |---|---|---|---|
    | **A-24 e B-04** | 49 | 30 dias | «campo próprio para notas, averbações e retificações, **inclusive no verso das folhas**» |
    | **C-05** | 49 | 30 dias | «campos próprios para notas, averbações e retificações» |
    | **D-03** | 50 | 30 dias | idem |
"""
from __future__ import annotations

from typing import Any


class FolhaError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


# ------------------------------------------------------------------ a folha
#
# CARTA EM PE — 215 x 279 mm. O #38 tinha invertido (paisagem 279 x 215) e
# a impressao da folha do livro saiu deitada. Oficial, 01/09/2026: retrato.
LARGURA_MM = 215.0
ALTURA_MM = 279.0
ORIENTACAO = "retrato"

DE_ONDE_SAI = (
    "folha do livro desta casa em retrato (carta 215 × 279 mm); as três "
    "colunas e o verso pautado vêm da inspeção COGEX de 12/08/2026 e do "
    "termo de nascimento nº 8.369 — o #38 tinha mandado paisagem, e isso "
    "era o defeito da impressão")

# DE ONDE VEM A EXIGENCIA — e ela tem endereco, prazo e livro nomeado.
EXIGENCIA = {
    "fonte": "Relatório de Inspeção Ordinária de Cidade Exemplo, 12/08/2026 "
             "(COGEX)",
    "texto": "assegurar campo próprio para notas, averbações e retificações, "
             "**inclusive no verso das folhas**",
    "prazo_dias": 30,
    "prioridade": "ALTA",
}

# OS QUATRO LIVROS QUE A INSPECAO NOMEOU, com a pagina de cada um. **Sao quatro,
# e nao um** — e quem consertasse so o A-24 deixaria tres exigencias abertas.
LIVROS_COBRADOS: tuple[dict, ...] = (
    {"livro": "A-24", "pagina": 49, "no_verso": True},
    {"livro": "B-04", "pagina": 49, "no_verso": True},
    {"livro": "C-05", "pagina": 49, "no_verso": False},
    {"livro": "D-03", "pagina": 50, "no_verso": False},
)

# **O VERSO TAMBEM LEVA A COLUNA DE NOTAS**, e isso esta na letra da exigencia do
# A-24 e do B-04. Uma folha cujo verso nao tem a margem e uma folha em que a
# averbacao nao cabe — e a averbacao vem depois, quando a folha ja esta escrita.
A_COLUNA_DE_NOTAS_VAI_NOS_DOIS_LADOS = True


# ------------------------------------------------------------- as tres colunas
#
# A primeira e ESTREITA de proposito: so o numero de ordem. 10% comia miolo
# e margem. Oficial 01/09/2026: apertar a 1a para sobrar termo e notas.
COLUNAS: tuple[dict, ...] = (
    {"chave": "NUMERO",
     "titulo": "Número",
     "largura": 0.06,
     "o_que_leva": "o número de ordem do termo — só o número, sem o nome "
                   "do registrado",
     "por_que": "coluna estreita: sobra espaço para o termo e para as notas"},
    {"chave": "TERMO",
     "titulo": "Termo",
     "largura": 0.64,
     "o_que_leva": "o texto do termo, com as frases impressas e os claros "
                   "preenchidos",
     "por_que": "é o ato"},
    {"chave": "NOTAS",
     "titulo": "Notas, Averbações e Retificações",
     "largura": 0.30,
     "o_que_leva": "notas, averbações e retificações no mesmo recanto; "
                   "título único em cima, pauta contínua abaixo",
     "por_que": "é o campo próprio da margem — um só, não três caixas"},
)

CHAVES = tuple(c["chave"] for c in COLUNAS)

# A FAIXA DE CIMA, onde as testemunhas assinam atravessando as colunas. No termo
# 8.369 sao duas assinaturas manuscritas, acima do cabecalho das colunas.
FAIXA_DE_ASSINATURAS_NO_TOPO = True

# QUEM ASSINA EMBAIXO DO TERMO, POR ESPÉCIE — relato #124 do oficial
# («adequar todos os termos do RCPN para constar campo de assinatura para quem
# assina o ato»), 15/10/2026. Até aqui só nascimento, óbito e casamento tinham
# as linhas (hotfix de 09/10/2026, termo 19579); o natimorto e as sete espécies
# do Livro E saíam sem linha nenhuma, embora o termo diga «dou fé e assino».
#
#   **A LISTA É A DO PRÓPRIO TEXTO DO TERMO**, e não uma escolha daqui: o de
#   nascimento (que o natimorto usa) diz «o(a) declarante assina»; o de óbito,
#   «assina comigo» o declarante; o de casamento, os nubentes; o do Livro E só
#   «Eu, …, dou fé e assino» — lá não há declarante nem testemunha, porque o
#   registro se faz pelo traslado do título (Lei 6.015/1973, art. 90, caput).
#   Quem lavrou fecha todas as listas, e é acrescentado por quem monta a folha.
#
#   **E A RESPOSTA DO OFICIAL VEIO NO MESMO DIA, 15/10/2026, e ampliou a
#   lista** — a primeira versão deixava de fora as testemunhas do casamento
#   (no termo 8.369 elas assinam na faixa de cima) e as partes do Livro E, e
#   perguntou. Ele decidiu:
#     • CASAMENTO — as TESTEMUNHAS e o JUIZ DE PAZ (presidente do ato, Lei
#       6.015/1973, art. 70) ganham linha com o nome embaixo; sem nome, a linha
#       sai com o rótulo da função. As testemunhas são todas as do assento, e
#       no mínimo duas (Código Civil, art. 1.534).
#     • LIVRO E — as partes também assinam: os companheiros na união estável,
#       o optante na opção de nacionalidade e, nas demais, quem o texto do termo
#       nomeia como requerente ou declarante (a interdição diz «a requerimento
#       de», a ausência «promovido por»). Emancipação, tutela e «outro» não
#       nomeiam requerente nem declarante no termo, e ficam só com quem lavrou.
#   Quem assina pela serventia continua vindo da regra viva (relato #65).
#
#   Cada linha é `(papel, rótulo)`: o papel é o de `rc_pessoas`, e o rótulo é
#   o que sai embaixo do nome (vazio = o rótulo do papel em `rc_assento`).
#   `JUIZ_DE_PAZ` não é papel de `rc_pessoas`: não há campo para ele no
#   assento lavrado aqui — quem o lê é a folha, do que o acervo trouxe.
TESTEMUNHAS_DO_CASAMENTO_NO_MINIMO = 2
JUIZ_DE_PAZ = "JUIZ_DE_PAZ"
ASSINAM_ALEM_DE_QUEM_LAVROU: dict[str, tuple[tuple[str, str], ...]] = {
    "NASCIMENTO": (("DECLARANTE", ""),),
    "NATIMORTO": (("DECLARANTE", ""),),
    "OBITO": (("DECLARANTE", ""),),
    "CASAMENTO": (("NUBENTE1", ""), ("NUBENTE2", ""), ("TESTEMUNHA", ""),
                  (JUIZ_DE_PAZ, "Juiz(a) de Paz")),
    # O religioso é o mesmo termo, e as testemunhas assinam; quem presidiu
    # foi o celebrante religioso, e não juiz de paz desta casa.
    "CASAMENTO_RELIGIOSO": (("NUBENTE1", ""), ("NUBENTE2", ""),
                            ("TESTEMUNHA", "")),
    "AUSENCIA": (("REQUERENTE", "Requerente"),),
    "INTERDICAO": (("REQUERENTE", "Requerente"),),
    "TUTELA": (),
    "EMANCIPACAO": (),
    "UNIAO_ESTAVEL": (("COMPANHEIRO1", ""), ("COMPANHEIRO2", "")),
    "OPCAO_NACIONALIDADE": (("REGISTRADO", "Optante"),),
    "OUTRO": (),
}

# Com mais de três linhas (o casamento), as assinaturas saem DUAS POR LINHA:
# uma embaixo da outra elas empurrariam a frente para outra página.
ASSINATURAS_EM_PAR_A_PARTIR_DE = 4

# Oficial 01/09/2026, 10:25: um só título no topo da 3ª coluna; abaixo,
# linhas seguidas no mesmo passo. 1ª e 2ª colunas lisas.
PAUTA_ATRAVESSA_AS_COLUNAS = False
A_TERCEIRA_COLUNA_E_PAUTADA = True
SO_AVERBACOES_SAO_PAUTADAS = False  # nao fatiar a 3a em tres caixas
PAUTA_PASSO_MM = 5.0

# MARGEM DE CIMA — o oficial pediu para tirar o espaço não usado acima das
# três colunas. Laterais e rodapé continuam na margem da casa; o topo aperta.
MARGEM_MM = 12.0
MARGEM_TOPO_MM = 5.0
# A margem que a IMPRESSORA recebe nos outros três lados (`@page` da folha).
# A folha se compõe com a margem da casa (12 mm) e, na impressão, é ampliada
# até esta — o `zoom` do modelo de tela. Um número só para os dois lugares.
MARGEM_DA_IMPRESSAO_MM = 5.0

# A ALTURA DA PAUTA SAI DA CONTA DA FOLHA, E NÃO DE UM NÚMERO ESCRITO — relato
# #124 do oficial, 15/10/2026: «expandir a parte de baixo para alcançar mais a
# margem de baixo, folha deixa muito espaço em branco. Só aumentar a linha das
# colunas e seguir com as linhas das averbações até mais embaixo».
#
#   Até aqui eram 155 mm fixos (31 linhas). Medido no PDF que o Chrome imprime
#   (a rota `/rcpn/<id>/folha/papel`, casamento com carimbo e três
#   assinaturas): a última linha da pauta caía a 226,9 mm do topo de uma folha
#   de 279 — **52 mm de papel em branco embaixo**.
#
#   A conta: a altura útil do papel (menos o topo e o rodapé da impressora),
#   devolvida à escala em que a folha se compõe (o `zoom` da impressão), menos
#   o que fica fora da pauta. Esse «fora» foi MEDIDO no mesmo PDF — cabeçalho
#   com o brasão, faixa das testemunhas, títulos das colunas e a marca
#   «Frente/Verso» somam 55 mm na bancada; a produção tem uma linha a mais no
#   cabeçalho (o contato), ~4 mm — e leva 9 mm de folga, porque a pauta que
#   passa da folha empurra a frente para uma segunda página e o verso para a
#   terceira, que é pior que papel em branco.
RESERVA_FORA_DA_PAUTA_MM = 68.0


def altura_util_impressa_mm() -> float:
    """A altura da folha na escala em que ela se compõe, em mm. Só calcula.

    O papel tem `ALTURA_MM` menos o topo e o rodapé da impressão; a folha é
    composta com a margem da casa e ampliada pelo `zoom` até a margem da
    impressora — então cada milímetro composto ocupa `zoom` milímetros de papel.
    """
    zoom = ((LARGURA_MM - 2 * MARGEM_DA_IMPRESSAO_MM)
            / (LARGURA_MM - 2 * MARGEM_MM))
    return (ALTURA_MM - MARGEM_TOPO_MM - MARGEM_DA_IMPRESSAO_MM) / zoom


def _pauta_que_cabe() -> float:
    """A maior pauta, em passos inteiros, que cabe na folha. Só calcula."""
    livre = altura_util_impressa_mm() - RESERVA_FORA_DA_PAUTA_MM
    return float(int(livre // PAUTA_PASSO_MM) * PAUTA_PASSO_MM)


# Altura do recanto pautado e quantas linhas cabem: 180 mm e 36 linhas na
# carta 215 × 279 (eram 155 e 31).
PAUTA_ALTURA_MM = _pauta_que_cabe()
PAUTA_LINHAS = int(PAUTA_ALTURA_MM // PAUTA_PASSO_MM)


def somam_um() -> bool:
    """As três larguras fecham em 1. Só calcula.

    **UMA LARGURA QUE NÃO FECHA É UMA COLUNA QUE INVADE A OUTRA** — e no papel
    isso é o texto do termo entrando na margem das averbações, que é onde se
    escreve por cima depois.
    """
    return abs(sum(c["largura"] for c in COLUNAS) - 1.0) < 1e-9


def coluna(chave: str) -> dict:
    for c in COLUNAS:
        if c["chave"] == chave:
            return c
    raise FolhaError(f"«{chave}» não é uma das três colunas da folha.")


def larguras_em_mm(margem_mm: float | None = None) -> dict[str, float]:
    """A largura de cada coluna, em milímetros. Só calcula."""
    if margem_mm is None:
        margem_mm = MARGEM_MM
    util = LARGURA_MM - 2 * margem_mm
    if util <= 0:
        raise FolhaError("A margem não cabe na folha.")
    return {c["chave"]: round(util * c["largura"], 2) for c in COLUNAS}


# ------------------------------------------------------------ frente e verso
#
# **A FOLHA TEM DUAS FACES, E O NUCLEO JA SABE DISSO.** `livro_nucleo` conta por
# FACE — `por_face`, e nao `por_folha` —, e a ambiguidade entre as duas ja custou
# caro a este projeto. Aqui a impressao segue o mesmo vocabulario.
FACES = ("FRENTE", "VERSO")


def face_da(ordem: Any) -> str:
    """Se aquele lugar cai na frente ou no verso. Só calcula.

    O NÚMERO DE ORDEM DA FACE É ÍMPAR NA FRENTE E PAR NO VERSO — a folha 1 tem a
    face 1 (frente) e a face 2 (verso). É a convenção do `livro_nucleo`, e
    inverter faria o termo sair no lado errado do papel: quem imprime frente e
    verso não descobre o engano até a folha estar no livro.
    """
    try:
        n = int(ordem)
    except (TypeError, ValueError) as erro:
        raise FolhaError("Diga o número da face.") from erro
    if n < 1:
        raise FolhaError("A face começa em 1.")
    return FACES[0] if n % 2 == 1 else FACES[1]


def folha_da(ordem: Any) -> int:
    """Em que folha aquela face está. Só calcula — faces 1 e 2 são a folha 1."""
    try:
        n = int(ordem)
    except (TypeError, ValueError) as erro:
        raise FolhaError("Diga o número da face.") from erro
    if n < 1:
        raise FolhaError("A face começa em 1.")
    return (n + 1) // 2


def _texto(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()