"""As obrigações que são do DELEGATÁRIO, e não de um setor.

    «lidar com toda complexidade de atos e responsabilidades que este oficial
     de cartório carrega» — o oficial, 09/10/2026

O QUE ENTRA AQUI, E O QUE NÃO ENTRA
    As cargas de cada atribuição (SIRC, CRC, IBGE, DOI, ONR, CENSEC…) têm robô
    próprio e responsável próprio; repeti-las aqui seria a segunda gaveta do
    mesmo fato. Entra o que recai sobre a pessoa do oficial e não tem setor: a
    declaração anual ao COAF, as cotas dos fundos de compensação, o que a
    Corregedoria manda recolher.

CADA OBRIGAÇÃO DIZ DE ONDE SAIU, E SE FOI CONFERIDA
    `fonte` é o papel desta casa em que a regra foi lida; `confirmada` diz se a
    regra está medida num documento daqui. **Obrigação que não está medida não
    ganha prazo inventado**: ela vira pergunta na fila do oficial, que é a
    regra «sem precedente, recuse e pergunte» aplicada à agenda dele. Um prazo
    escrito de memória — ainda que certo na maioria das casas — seria o carimbo
    que mente na agenda de quem responde pessoalmente por ela.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

#: As obrigações conferidas num documento desta casa.
OBRIGACOES: tuple[dict, ...] = (
    {
        "codigo": "COAF_NAO_OCORRENCIA",
        "titulo": "Declaração anual de não ocorrência ao COAF (Siscoaf)",
        "periodicidade": "ANUAL",
        "dia": 31, "mes": 1,
        "fundamento": "Provimento CNJ 149/2023, art. 153 (redação do Prov. 161/2024)",
        "fonte": "provimento 149 cnj.pdf, na pasta do oficial — lido em 08/10/2026",
        "confirmada": True,
        "antecedencia_dias": 45,
        "nota": "Vale para o ano anterior inteiro. Exige a serventia habilitada no "
                "Siscoaf, e em 06/10/2026 ela ainda não estava.",
    },
    {
        "codigo": "FIC_COTAS",
        "titulo": "Recolhimento das cotas do FIC-SREI, FIC-RCPN e FIC-RTDPJ",
        "periodicidade": "MENSAL",
        "dia": "ULTIMO",
        "fundamento": "CIRC-CSERVCOGEX 222/2026 (malote, EXP-2026-000029)",
        "fonte": "um caso visto: referência 09/2026 com prazo 31/10/2026 — o mês "
                 "seguinte, até o último dia",
        "confirmada": True,
        "antecedencia_dias": 10,
        "nota": "Apurar o percebido no mês de referência por especialidade e recolher. "
                "Guardar o comprovante — é o que a correição pede.",
    },
    # O LIVRO DIÁRIO AUXILIAR saiu de A_CONFIRMAR no LG08 (19/10/2026): o
    # Código de Normas do MA dá os dois prazos, e o livro passou a existir
    # (Administrativo → Livro Diário Auxiliar). O prazo é em DIA ÚTIL, contado
    # com os feriados nacionais (`ri_schema`); feriado local a agenda não sabe.
    {
        "codigo": "LIVRO_DIARIO_MENSAL",
        "titulo": "Gerar, assinar e rubricar o Livro Diário Auxiliar do mês anterior",
        "periodicidade": "MENSAL",
        "dia_util": 5,
        "fundamento": "Código de Normas do MA (Prov. COGEX 28/2026), art. 205",
        "fonte": "referencia/codigo_de_normas_extrajudicial_ma.txt (malote de "
                 "27/05/2026) — lido em 19/10/2026",
        "confirmada": True,
        "antecedencia_dias": 7,
        "nota": "Até o 5º dia útil do mês seguinte. Gerar de novo só para "
                "retificação circunstanciada (art. 206).",
    },
    {
        "codigo": "LIVRO_DIARIO_ANUAL",
        "titulo": "Encaminhar o Livro Diário Auxiliar do exercício anterior à "
                  "Coordenadoria de Análise de Contas e ao juiz corregedor permanente",
        "periodicidade": "ANUAL",
        "mes": 5, "dia_util": 1,
        "fundamento": "Código de Normas do MA (Prov. COGEX 28/2026), art. 207",
        "fonte": "referencia/codigo_de_normas_extrajudicial_ma.txt (malote de "
                 "27/05/2026) — lido em 19/10/2026",
        "confirmada": True,
        "antecedencia_dias": 30,
        "nota": "Até o primeiro dia útil de maio. O não encaminhamento no prazo "
                "enseja processo administrativo disciplinar (art. 207, § 8º).",
    },
)

#: O que provavelmente cabe ao delegatário mas NÃO está medido em documento
#: desta casa. Vira UMA pergunta, e não prazos.
A_CONFIRMAR: tuple[dict, ...] = (
    {"codigo": "FERJ_FERC", "titulo": "Pagamento do FERJ e do FERC",
     "indicio": "havia um aviso semanal (segunda, 08h) criado no sistema e hoje desligado"},
    {"codigo": "JUSTICA_ABERTA", "titulo": "Justiça Aberta (CNJ) — produtividade e arrecadação",
     "indicio": "nenhum documento desta casa trata dela"},
    # O Livro Diário Auxiliar virou obrigação medida (LG08). Fica o imposto de
    # renda: o Código de Normas só dá ao livro o espaço do IR (art. 190, VII,
    # e § 10, facultativo); o prazo do carnê-leão é da Receita Federal.
    # DESDE 26/10/2026 o oficial pode cadastrar a regra do prazo, com a fonte,
    # em Administrativo → Carnê-leão (`carne_leao.obrigacao_da_agenda`): então
    # ela entra na agenda por `agenda(extras=...)` e sai desta pergunta.
    {"codigo": "CARNE_LEAO", "titulo": "Carnê-leão (imposto de renda mensal do delegatário)",
     "indicio": "o Código de Normas do MA só reserva espaço para o IR no Livro Diário "
                "(art. 190, VII); o prazo não está em documento desta casa"},
)


def _ultimo_dia(ano: int, mes: int) -> date:
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def _dia_util(ano: int, mes: int, n: int) -> date:
    """O n-ésimo dia útil do mês, com os feriados nacionais de `ri_schema`."""
    from ri_schema import soma_dias_uteis
    return soma_dias_uteis(date(ano, mes, 1) - timedelta(days=1), n)


def _ultimo_dia_util(ano: int, mes: int) -> date:
    """O último dia útil do mês, com os feriados nacionais de `ri_schema`."""
    from ri_schema import eh_dia_util
    dia = _ultimo_dia(ano, mes)
    while not eh_dia_util(dia):
        dia -= timedelta(days=1)
    return dia


def _mensal(hoje: date, prazo_do_mes) -> tuple[date, str]:
    """O prazo deste mês é o da referência do mês passado; passado o prazo, o
    próximo é o do mês que vem, que se refere a este."""
    ano, mes = hoje.year, hoje.month
    prazo = prazo_do_mes(ano, mes)
    if prazo < hoje:
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
        prazo = prazo_do_mes(ano, mes)
    ref_ano, ref_mes = (ano, mes - 1) if mes > 1 else (ano - 1, 12)
    return prazo, f"referência {ref_mes:02d}/{ref_ano}"


def proximo_vencimento(ob: dict, hoje: date) -> tuple[date, str]:
    """O próximo prazo da obrigação a partir de hoje, e a que período se refere."""
    # O CARNÊ-LEÃO (26/10/2026) trouxe as duas formas que faltavam: o último
    # dia útil e o dia fixo do mês. Elas só chegam aqui quando o oficial as
    # cadastrou com a fonte (`carne_leao.obrigacao_da_agenda`).
    if ob.get("ultimo_dia_util") and ob["periodicidade"] == "MENSAL":
        return _mensal(hoje, _ultimo_dia_util)
    if isinstance(ob.get("dia"), int) and ob["periodicidade"] == "MENSAL":
        return _mensal(hoje, lambda a, m: date(a, m, min(ob["dia"], _ultimo_dia(a, m).day)))
    if ob.get("dia_util") and ob["periodicidade"] == "ANUAL":
        prazo = _dia_util(hoje.year, ob["mes"], ob["dia_util"])
        if prazo < hoje:
            prazo = _dia_util(hoje.year + 1, ob["mes"], ob["dia_util"])
        return prazo, f"ano de {prazo.year - 1}"
    if ob.get("dia_util") and ob["periodicidade"] == "MENSAL":
        # O prazo deste mês é o da referência do mês passado; passado o
        # prazo, o próximo é o do mês que vem, que se refere a este.
        ano, mes = hoje.year, hoje.month
        prazo = _dia_util(ano, mes, ob["dia_util"])
        if prazo < hoje:
            ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
            prazo = _dia_util(ano, mes, ob["dia_util"])
        ref_ano, ref_mes = (ano, mes - 1) if mes > 1 else (ano - 1, 12)
        return prazo, f"referência {ref_mes:02d}/{ref_ano}"
    if ob["periodicidade"] == "ANUAL":
        prazo = date(hoje.year, ob["mes"], ob["dia"])
        if prazo < hoje:
            prazo = date(hoje.year + 1, ob["mes"], ob["dia"])
        return prazo, f"ano de {prazo.year - 1}"
    if ob["periodicidade"] == "MENSAL":
        # O prazo deste mês é o da referência do mês passado.
        prazo = _ultimo_dia(hoje.year, hoje.month)
        ref_ano, ref_mes = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)
        return prazo, f"referência {ref_mes:02d}/{ref_ano}"
    raise ValueError(f"Periodicidade desconhecida: {ob['periodicidade']!r}")


def agenda(hoje: date, horizonte_dias: int = 60, extras: tuple[dict, ...] = ()) -> list[dict]:
    """As obrigações do oficial com prazo dentro do horizonte, a mais próxima primeiro.

    `extras` são as obrigações que o oficial cadastrou com a fonte (hoje, o
    carnê-leão), no mesmo formato de `OBRIGACOES`.
    """
    fora = []
    for ob in (*OBRIGACOES, *extras):
        prazo, referencia = proximo_vencimento(ob, hoje)
        faltam = (prazo - hoje).days
        if faltam > horizonte_dias:
            continue
        fora.append({**ob, "prazo": prazo.isoformat(), "referencia": referencia,
                     "faltam_dias": faltam,
                     "alerta": faltam <= ob.get("antecedencia_dias", 10)})
    fora.sort(key=lambda o: o["prazo"])
    return fora


PERGUNTA_DAS_OBRIGACOES = "OBRIGACOES_DO_DELEGATARIO_A_CONFIRMAR"


def pergunta_das_nao_medidas(medidas: tuple[str, ...] = ()) -> dict:
    """A pergunta única sobre o que não está medido — vai à fila de decisões.

    `medidas` são os códigos que o oficial já cadastrou com a fonte (o
    carnê-leão): saem da pergunta, porque já estão na agenda.
    """
    linhas = "\n".join(f"- {o['titulo']} ({o['indicio']})" for o in A_CONFIRMAR
                       if o["codigo"] not in medidas)
    return {
        "chave": PERGUNTA_DAS_OBRIGACOES,
        "origem": "OFICIAL",
        "pergunta": "Quais destas obrigações pessoais o robô deve acompanhar, e com que prazo?",
        "contexto": "Não achei documento desta casa que dê a regra e o prazo delas, e "
                    "prazo escrito de memória não entra na sua agenda:\n" + linhas,
        "opcoes": ["Responder com o prazo de cada uma", "Nenhuma — já controlo por fora",
                   "Mandar o documento que trata dela"],
        "recomendacao": "Mandar o documento (circular, provimento ou o aviso do contador): "
                        "com ele o prazo entra medido, como o do COAF, o do FIC e o do Livro "
                        "Diário.",
        "o_que_espera": "Sem resposta, só as obrigações medidas (COAF, FIC e Livro "
                        "Diário) entram na agenda.",
        "gravidade": "INFO",
    }
