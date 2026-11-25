"""O SEMÁFORO DA CONFORMIDADE — uma cor por área, para o oficial ver em segundos.

    «Quer que eu comece o painel de conformidade (semáforo por área)?»
    «Sim, comece» — o oficial, 18/11/2026, no plano do gestor de compliance

O QUE ELE RESPONDE
    Para cada uma das sete áreas da casa — RI, Notas, Protesto, Registro Civil,
    RTD/PJ, Financeiro e selo, Administração — uma cor: VERDE, AMARELO ou
    VERMELHO. E, quando o gestor não mediu a casa, nenhuma das três: a área
    fica SEM_MEDICAO. Verde com cara de medição, no dia em que a medição não
    rodou, seria o carimbo que mente (a lição da conferência de 02/10/2026).

DE ONDE VEM — UMA FONTE SÓ, E NÃO UMA SEGUNDA GAVETA
    Dos achados ABERTOS do gestor (`ge_achados`, `resolvido_em IS NULL`). Esta
    tela não guarda nada: mede na hora, e o achado que a conferência seguinte
    fecha sai da cor sozinho. Ninguém «pinta de verde» uma área à mão.

O CRITÉRIO, E ELE É O DO PLANO DO GESTOR
    | cor      | quando                                                         |
    |----------|----------------------------------------------------------------|
    | VERMELHO | achado VENCIDO (prazo legal passou), ou CRITICO aberto há mais |
    |          | de 1 dia útil                                                  |
    | AMARELO  | CRITICO recente; PRAZO que vence em até 2 dias úteis (ou cujo  |
    |          | prazo não se lê); regra que NAO_MEDIU; gravidade desconhecida  |
    | VERDE    | nada disso                                                     |

    O ATENCAO não muda a cor: é controle interno (o caixa esperando o visto,
    por exemplo) e, se mudasse, nenhuma área seria verde. Ele é contado e
    aparece no número da área, sem esconder.

A ÁREA SAI DO SETOR DO ACHADO
    O setor é o que a conferência já grava (`gestor_rotina.SETORES`, mais o
    FISCAL do agente financeiro). O caixa e o fechamento do mês caem no
    Financeiro pela REGRA, porque o setor deles é o de quem contou o dinheiro
    — e o dinheiro da casa é uma área só. O setor que esta régua não conhece
    vai para OUTROS, contado à parte e não escondido.

O QUE ELE AINDA NÃO MEDE (declarado, e a tela o diz)
    `NAO_MEDE`: os achados do agente de compliance (tabelas `cp_*`), que medem
    os outros robôs; e as obrigações que não têm robô (Justiça Aberta, INCRA,
    afixações, trabalhista) — elas entram quando a matriz de obrigações
    existir. Fiscal que não diz onde não olhou deixa supor que olhou em tudo.

SÓ LÊ, E SÓ DEVOLVE CÓDIGOS E CONTAGENS
    O mesmo dicionário vai à primeira tela e ao painel do celular — e, por ele,
    ao retrato que sai da casa (`painel_retrato`). Por isso nada aqui lê o
    título nem o detalhe do achado (eles trazem número de ato e nome de parte):
    só regra, gravidade, setor e datas.
"""
from __future__ import annotations

from datetime import date

from bd_nativo import banco
from ri_schema import dias_uteis_entre

#: As áreas, na ordem em que a tela as mostra, com o nome da tela.
AREAS: tuple[tuple[str, str], ...] = (
    ("RI", "Registro de Imóveis"),
    ("NOTAS", "Notas"),
    ("PROTESTO", "Protesto"),
    ("RCPN", "Registro Civil"),
    ("RTD_PJ", "RTD/PJ"),
    ("FINANCEIRO", "Financeiro e selo"),
    ("ADMINISTRACAO", "Administração"),
)
OUTROS = "OUTROS"
ROTULO_DA_AREA = {**dict(AREAS), OUTROS: "Outros setores"}

VERMELHO, AMARELO, VERDE, SEM_MEDICAO = "VERMELHO", "AMARELO", "VERDE", "SEM_MEDICAO"
CORES = (VERMELHO, AMARELO, VERDE, SEM_MEDICAO)
ROTULO_DA_COR = {VERMELHO: "Vermelho", AMARELO: "Amarelo", VERDE: "Verde",
                 SEM_MEDICAO: "Sem medição"}

#: Por que a casa está sem medição — códigos, para poderem sair no retrato.
SEM_RODADA, RODADA_COM_ERRO, RODADA_ANTIGA = "SEM_RODADA", "RODADA_COM_ERRO", "RODADA_ANTIGA"
ROTULO_DO_MOTIVO = {
    SEM_RODADA: "o gestor nunca terminou uma rodada neste banco",
    RODADA_COM_ERRO: "a última rodada do gestor terminou com erro",
    RODADA_ANTIGA: "a última rodada do gestor tem mais de 1 dia útil",
}

#: CRITICO aberto há mais que isto (em dias úteis) deixa a área vermelha.
CRITICO_TOLERADO_DIAS_UTEIS = 1
#: PRAZO que vence em até isto (em dias úteis) deixa a área amarela.
PRAZO_PROXIMO_DIAS_UTEIS = 2
#: A rodada do gestor mais velha que isto (em dias úteis) não vale como medição.
RODADA_TOLERADA_DIAS_UTEIS = 1

#: O setor do achado → a área. Os de qualificação caem na mesma atribuição.
AREA_DO_SETOR = {
    "RI": "RI",
    "RI_QUALIFICACAO": "RI",
    "NOTAS": "NOTAS",
    "NOTAS_QUALIFICACAO": "NOTAS",
    "PROTESTO": "PROTESTO",
    "RCPN": "RCPN",
    "RCPJ_RTD": "RTD_PJ",
    "RCPJ_RTD_QUALIFICACAO": "RTD_PJ",
    "FISCAL": "FINANCEIRO",
    "GESTAO": "ADMINISTRACAO",
    "TI": "ADMINISTRACAO",
}

#: As regras que são do Financeiro qualquer que seja o setor gravado.
REGRAS_DO_FINANCEIRO = frozenset({"FECHAMENTO_DO_MES", "REPASSE_DE_TERCEIRO"})
PREFIXOS_DO_FINANCEIRO = ("CAIXA", "FISCAL")

GRAVIDADES_CONHECIDAS = frozenset({"CRITICO", "VENCIDO", "NAO_MEDIU", "PRAZO", "ATENCAO"})

#: O que este semáforo ainda não olha. A tela o mostra embaixo das cores.
NAO_MEDE = (
    "os achados do agente de compliance, que fiscaliza os outros robôs",
    "as obrigações sem robô: Justiça Aberta, INCRA, afixações e trabalhista",
)

CONTADORES = ("abertos", "vencidos", "criticos", "criticos_antigos",
              "prazo_proximo", "nao_mediu", "atencao", "outra_gravidade")


def area_do_achado(setor: str | None, regra: str | None) -> str:
    """A área de um achado. Só calcula."""
    r = str(regra or "").upper()
    if r in REGRAS_DO_FINANCEIRO or r.startswith(PREFIXOS_DO_FINANCEIRO):
        return "FINANCEIRO"
    return AREA_DO_SETOR.get(str(setor or "").upper(), OUTROS)


def _dia(texto) -> date | None:
    bruto = str(texto or "")[:10]
    try:
        return date(int(bruto[:4]), int(bruto[5:7]), int(bruto[8:10]))
    except (ValueError, IndexError):
        return None


def cor_da_area(c: dict) -> str:
    """A cor de uma área pelas contagens dela. Só calcula."""
    if c["vencidos"] or c["criticos_antigos"]:
        return VERMELHO
    if c["criticos"] or c["prazo_proximo"] or c["nao_mediu"] or c["outra_gravidade"]:
        return AMARELO
    return VERDE


def _contar(contagem: dict, gravidade: str, prazo, visto, hoje: date) -> None:
    contagem["abertos"] += 1
    if gravidade == "VENCIDO":
        contagem["vencidos"] += 1
    elif gravidade == "CRITICO":
        contagem["criticos"] += 1
        desde = _dia(visto)
        # Data que não se lê não absolve: conta como antigo.
        if desde is None or dias_uteis_entre(desde, hoje) > CRITICO_TOLERADO_DIAS_UTEIS:
            contagem["criticos_antigos"] += 1
    elif gravidade == "PRAZO":
        vence = _dia(prazo)
        if vence is None or dias_uteis_entre(hoje, vence) <= PRAZO_PROXIMO_DIAS_UTEIS:
            contagem["prazo_proximo"] += 1
    elif gravidade == "NAO_MEDIU":
        contagem["nao_mediu"] += 1
    elif gravidade == "ATENCAO":
        contagem["atencao"] += 1
    else:
        contagem["outra_gravidade"] += 1


def _rodada(con, hoje: date) -> dict:
    """A última rodada TERMINADA do gestor, e se ela vale como medição.

    A rodada em andamento (começou e não terminou) não conta: às 14:00 ela
    está rodando, e a da manhã continua valendo. A rodada presa é cobrada
    pelo robô oficial (`oficial_robos`), e não aqui.
    """
    ultima = banco(con).um(
        """SELECT iniciada_em, terminada_em, erro FROM ge_execucoes
            WHERE terminada_em IS NOT NULL AND TRIM(terminada_em) <> ''
            ORDER BY id DESC LIMIT 1""")
    if not ultima:
        return {"ultima_rodada": None, "medido": False, "motivo": SEM_RODADA}
    quando = str(ultima["terminada_em"])[:16]
    if str(ultima["erro"] or "").strip():
        return {"ultima_rodada": quando, "medido": False, "motivo": RODADA_COM_ERRO}
    dia = _dia(ultima["terminada_em"])
    if dia is None or dias_uteis_entre(dia, hoje) > RODADA_TOLERADA_DIAS_UTEIS:
        return {"ultima_rodada": quando, "medido": False, "motivo": RODADA_ANTIGA}
    return {"ultima_rodada": quando, "medido": True, "motivo": None}


def medir(con, hoje: date | None = None) -> dict:
    """O semáforo da casa. SÓ LÊ.

    Devolve `{"gestor": {...}, "areas": {codigo: {cor, contagens}},
    "resumo": {cor: quantas áreas}}` — só códigos, datas e números. A área
    OUTROS só aparece quando tem achado. Tabela que não existe é exceção:
    quem chama decide como mostrar o «não mediu», e nunca como zero.
    """
    hoje = hoje or date.today()
    rodada = _rodada(con, hoje)
    contagens = {codigo: dict.fromkeys(CONTADORES, 0) for codigo, _ in AREAS}
    for r in banco(con).ler(
            """SELECT regra, gravidade, setor, prazo, primeiro_visto_em
                 FROM ge_achados WHERE resolvido_em IS NULL ORDER BY id"""):
        area = area_do_achado(r["setor"], r["regra"])
        if area not in contagens:
            contagens[area] = dict.fromkeys(CONTADORES, 0)
        gravidade = str(r["gravidade"] or "").upper()
        if gravidade not in GRAVIDADES_CONHECIDAS:
            gravidade = "OUTRA"
        _contar(contagens[area], gravidade, r["prazo"], r["primeiro_visto_em"], hoje)
    areas = {}
    for area, c in contagens.items():
        cor = cor_da_area(c) if rodada["medido"] else SEM_MEDICAO
        areas[area] = {"cor": cor, **c}
    resumo = dict.fromkeys(CORES, 0)
    for a in areas.values():
        resumo[a["cor"]] += 1
    return {"hoje": hoje.isoformat(), "gestor": rodada, "areas": areas, "resumo": resumo}
