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
from datetime import date

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
)

#: O que provavelmente cabe ao delegatário mas NÃO está medido em documento
#: desta casa. Vira UMA pergunta, e não prazos.
A_CONFIRMAR: tuple[dict, ...] = (
    {"codigo": "FERJ_FERC", "titulo": "Pagamento do FERJ e do FERC",
     "indicio": "havia um aviso semanal (segunda, 08h) criado no sistema e hoje desligado"},
    {"codigo": "JUSTICA_ABERTA", "titulo": "Justiça Aberta (CNJ) — produtividade e arrecadação",
     "indicio": "nenhum documento desta casa trata dela"},
    {"codigo": "LIVRO_CAIXA_IR", "titulo": "Livro Diário da receita e despesa / carnê-leão",
     "indicio": "nenhum documento desta casa trata dele"},
)


def _ultimo_dia(ano: int, mes: int) -> date:
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def proximo_vencimento(ob: dict, hoje: date) -> tuple[date, str]:
    """O próximo prazo da obrigação a partir de hoje, e a que período se refere."""
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


def agenda(hoje: date, horizonte_dias: int = 60) -> list[dict]:
    """As obrigações do oficial com prazo dentro do horizonte, a mais próxima primeiro."""
    fora = []
    for ob in OBRIGACOES:
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


def pergunta_das_nao_medidas() -> dict:
    """A pergunta única sobre o que não está medido — vai à fila de decisões."""
    linhas = "\n".join(f"- {o['titulo']} ({o['indicio']})" for o in A_CONFIRMAR)
    return {
        "chave": PERGUNTA_DAS_OBRIGACOES,
        "origem": "OFICIAL",
        "pergunta": "Quais destas obrigações pessoais o robô deve acompanhar, e com que prazo?",
        "contexto": "Não achei documento desta casa que dê a regra e o prazo delas, e "
                    "prazo escrito de memória não entra na sua agenda:\n" + linhas,
        "opcoes": ["Responder com o prazo de cada uma", "Nenhuma — já controlo por fora",
                   "Mandar o documento que trata dela"],
        "recomendacao": "Mandar o documento (circular, provimento ou o aviso do contador): "
                        "com ele o prazo entra medido, como o do COAF e o do FIC.",
        "o_que_espera": "Sem resposta, só o COAF e o FIC entram na agenda.",
        "gravidade": "INFO",
    }
