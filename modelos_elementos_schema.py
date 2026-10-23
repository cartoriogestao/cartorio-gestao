"""Onde moram os elementos dos modelos — um submódulo por atribuição.

    «preciso que haja um submodulo de modelos para cada atribuicao e nesse
     submodulo quero poder editar cada parte dos modelos, especialmente
     gerenciando cada elemento do modelo» — o oficial, 07/09/2026.

    «cabecalho compartilhado por atribuicao, podendo mudar para atos
     especificos, como certidoes do rcpn com cabecalho diferente do termo.
     todas atribuicoes de uma vez. viram modelos editaveis.» — ele, no mesmo
     dia, respondendo às três perguntas do plano.

O CABEÇALHO FICOU DE FORA, E A DECISÃO É DELE
    «cabecalho dos atos vamos deixar num ajuste separado para manter a forma e
     diminuir o risco de ir errado».

    O cabeçalho do Registro Civil sai de `rc_cabecalho.py` — **sete linhas
    montadas em código**, na ordem que a norma exige —, e o do Registro de
    Imóveis é o papel `RI_CABECALHO` do catálogo. Torná-los texto livre agora
    poria a forma do timbre nas mãos de quem edita depressa. **Eles continuam
    onde estão**, e este módulo trata das outras três partes.

    Isto **não** desfaz o que ele pediu: a herança por atribuição, com troca
    por ato, vale para o corpo, o encerramento e o rodapé — e é onde o texto
    de fato muda de ato para ato.

AS TRÊS PARTES SÃO AS DELE, do relato #28: «corpo, encerramento, eventual
notas de rodapé».

OS TRÊS DEGRAUS, E É ISSO QUE ELE PEDIU
    ```
    1. o elemento do ATO           a certidão do RCPN tem encerramento próprio
    2. o elemento da ATRIBUIÇÃO    o resto do RCPN usa o comum
    3. o padrão do CÓDIGO          instalação nova já nasce funcionando
    ```

    O terceiro degrau é a regra que `modelos_da_casa` já paga: **o código é o
    piso, a tabela é o ajuste.** Sem linha na tabela, o papel sai de fábrica —
    e por isso «voltar ao padrão» é apagar a linha, e não recadastrar um texto
    que ninguém tem mais.

**E O ENCERRAMENTO E O RODAPÉ NASCEM VAZIOS.** Os 14 papéis de hoje já trazem
o fecho dentro do próprio texto; partir esse texto automaticamente seria
adivinhar onde o corpo acaba, em documento que a serventia assina. Vazio quer
dizer **não acrescenta nada** — e é o que faz o papel sair, no dia da subida,
exatamente como saía na véspera.
"""
from __future__ import annotations

import re

from bd_nativo import banco

# ------------------------------------------------------------ as atribuições
#
# **SEIS SUBMÓDULOS, e as chaves são as do menu da casa** (`modulos.MODULOS`),
# porque é por elas que o oficial navega. Duas observações medidas em
# 07/09/2026, e nenhuma é arbitrária:
#
#   · **RCPJ e RTD não têm um único papel no catálogo.** Eles emitem certidão
#     por outro caminho (`atrib_certidao`, que serve três atribuições). O
#     submódulo deles nasce só com o nível da atribuição — tela com um elemento
#     é honesta; tela vazia faria concluir que quebrou.
#
#   · **«Caixa e protocolo» não é atribuição**, e entra assim mesmo: tem três
#     papéis reais (recibo, orçamento e recepção), e deixá-lo de fora obrigaria
#     a procurar o recibo noutro lugar — que é o relato #28 de volta.
RI = "RI"
NOTAS = "NOTAS"
RCPN = "RCPN"
RCPJ_RTD = "RCPJ_RTD"
PROTESTO = "PROTESTO"
CAIXA = "CAIXA"

ATRIBUICOES: tuple[str, ...] = (RI, NOTAS, RCPN, RCPJ_RTD, PROTESTO, CAIXA)

NOME_DA_ATRIBUICAO: dict[str, str] = {
    RI: "Registro de Imóveis",
    NOTAS: "Tabelionato de Notas",
    RCPN: "Registro Civil das Pessoas Naturais",
    RCPJ_RTD: "RCPJ e RTD",
    PROTESTO: "Protesto",
    CAIXA: "Caixa e protocolo",
}

# O de-para do rótulo que o catálogo já usa para a chave daqui. Ele existe
# porque `modelos_da_casa.CATALOGO` guarda a atribuição **por extenso**, e
# comparar texto por extenso quebraria no dia em que alguém corrigisse um
# acento.
CHAVE_DO_ROTULO: dict[str, str] = {
    "Registro de Imóveis": RI,
    "Tabelionato de Notas": NOTAS,
    "Registro Civil das Pessoas Naturais": RCPN,
    "RCPJ e RTD": RCPJ_RTD,
    "Protesto": PROTESTO,
    "Caixa e protocolo": CAIXA,
}

# ----------------------------------------------------------------- as partes
CORPO = "CORPO"
ENCERRAMENTO = "ENCERRAMENTO"
RODAPE = "RODAPE"

PARTES: tuple[str, ...] = (CORPO, ENCERRAMENTO, RODAPE)

NOME_DA_PARTE: dict[str, str] = {
    CORPO: "Corpo",
    ENCERRAMENTO: "Encerramento",
    RODAPE: "Nota de rodapé",
}

EXPLICA_A_PARTE: dict[str, str] = {
    CORPO: "O texto do documento. É o que existe hoje, e sem ajuste ele sai "
           "do padrão escrito no programa.",
    ENCERRAMENTO: "O que vem depois do corpo — o fecho, o «dou fé», a "
                  "assinatura. **Nasce vazio**, e vazio não acrescenta nada.",
    RODAPE: "A observação de pé de página. **Nasce vazia.**",
}

# **O CABEÇALHO NÃO ESTÁ AQUI, E A AUSÊNCIA É DECISÃO DO OFICIAL** — ver o
# cabeçalho do módulo. Declaro a chave para que quem procurar por ela ache a
# razão, em vez de achar que faltou.
CABECALHO_FICOU_DE_FORA = (
    "O cabeçalho continua onde está: no `RI_CABECALHO` do catálogo, para o "
    "Registro de Imóveis, e em `rc_cabecalho.py`, montado em código, para o "
    "Registro Civil. Decisão do oficial em 07/09/2026 — «manter a forma e "
    "diminuir o risco de ir errado»."
)

# **O NÍVEL DA ATRIBUIÇÃO É `ato = ''`, E NÃO `NULL`.** No SQLite dois NULL
# são distintos num índice único: com `NULL` a casa poderia gravar dois
# encerramentos do Registro de Imóveis inteiro, e o segundo venceria o
# primeiro sem que ninguém visse.
TODA_A_ATRIBUICAO = ""

SCHEMA = """
CREATE TABLE IF NOT EXISTS mo_elementos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

    -- RI | NOTAS | RCPN | RCPJ_RTD | PROTESTO | CAIXA
    atribuicao TEXT NOT NULL,

    -- '' = vale para a atribuição inteira; senão a chave do ato no catálogo
    -- (`RC_TERMO_OBITO`, `RI_CERTIDAO`…), que é o degrau que sobrepõe.
    ato TEXT NOT NULL DEFAULT '',

    -- CORPO | ENCERRAMENTO | RODAPE
    parte TEXT NOT NULL,

    corpo TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1,

    atualizado_em TEXT NOT NULL,
    atualizado_por TEXT,

    -- sha256 do padrão sobre o qual o CORPO foi ajustado (LF06A); a tabela
    -- que já existia ganha a coluna pela MIGRACOES, nula nos ajustes antigos
    base_impressao TEXT,

    UNIQUE(atribuicao, ato, parte)
);

CREATE INDEX IF NOT EXISTS idx_mo_elementos_atrib
    ON mo_elementos(atribuicao, ato, parte);
"""

# Colunas acrescentadas depois. Aditivo, no padrão do sistema — e índice sobre
# coluna de migração **não vai aqui**: vai em `INDICES_DEPOIS_DA_MIGRACAO`.
MIGRACOES: tuple[tuple[str, str, str], ...] = (
    # SOBRE QUAL PADRÃO O CORPO FOI AJUSTADO — LF06A, 19/10/2026. É AQUI que a
    #   tela de Modelos grava o ajuste desde 07/09 (o `mo_modelos` virou
    #   legado), e por isso a marca tem de morar aqui também: posta só em
    #   `mo_modelos`, o aviso «o padrão mudou depois do seu ajuste» nunca
    #   acenderia para o ajuste que a casa de fato faz. Só o CORPO de um ato tem
    #   padrão; encerramento e rodapé ficam nulos. Nula nos ajustes antigos.
    ("mo_elementos", "base_impressao", "TEXT"),
)

INDICES_DEPOIS_DA_MIGRACAO: tuple[str, ...] = ()


def init_modelos_elementos_schema(con) -> None:
    """Cria a tabela dos elementos dos modelos. Idempotente."""
    bd = banco(con)
    for comando in re.split(r";[ \t]*\n", SCHEMA):
        if re.sub(r"--[^\n]*", "", comando).strip():
            bd.escrever(comando)
    for tabela, coluna, tipo in MIGRACOES:
        if not bd.tem_coluna(tabela, coluna):
            bd.escrever(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    for comando in INDICES_DEPOIS_DA_MIGRACAO:
        bd.escrever(comando)
