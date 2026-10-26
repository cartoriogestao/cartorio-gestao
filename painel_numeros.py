"""OS NÚMEROS DA CASA, SÓ AGREGADOS — o painel do gestor no celular (26/10/2026).

    «painel do gestor no celular, só com números agregados» — pedido de 26/10/2026

O QUE ELE DEVOLVE
    Um dicionário de CONTAGENS e SOMAS — nada mais. Atos por atribuição (pelos
    selos usados), emolumentos líquidos do FERJ, selos usados e cancelados, protocolos em
    andamento e atrasados, prenotações vencidas e a vencer, tarefas, fila do
    atendimento e os alertas da casa. Para três janelas: o DIA, a SEMANA (de
    segunda até hoje) e o MÊS (do dia 1º até hoje).

O QUE ELE NUNCA DEVOLVE, E POR QUE ISSO É REGRA E NÃO CUIDADO
    Nome de cliente, CPF, número de protocolo, matrícula, teor, descrição de
    lançamento, nome de escrevente. O mesmo dicionário vira a tela do celular
    E o retrato que sai da casa (`painel_retrato`): o que entrar aqui pode sair
    para a internet. Por isso as consultas pedem só `COUNT`, datas, valores e
    códigos fechados (atribuição, gravidade) — a coluna com nome nem chega ao
    Python. Há teste que semeia nome e CPF e procura os dois no JSON.

A MESMA RÉGUA DAS OUTRAS TELAS
    Cada número vem da regra que já existe, para o celular não discordar do
    balcão: o selo usado é `selos_emitidos.USADO`; a atribuição do selo é a do
    relatório financeiro (`gestor_financeiro._ATRIB_DO_SELO`); a prenotação
    vencida ou a vencer é a da conferência diária do gestor; as tarefas são as
    de `db.dashboard_stats`; o protocolo sem item é `caixa_protocolo`.

    A RECEITA É «EMOLUMENTOS LÍQUIDOS DO FERJ» — decisão do oficial em
    26/10/2026: «apenas emolumentos abatidos do FERJ». Não sai do caixa: sai
    do SELO, que é onde o emolumento de cada ato está declarado (o lançamento
    manual quase nunca separa emolumento de fundo — `gestor_financeiro`, na
    docstring). Por ato pago (selo usado, de produção, sem marca de isento
    nem de diferido): o emolumento que o selo declara MENOS o FERJ que sai de
    dentro dele, com a régua de `custas` (`percentual_ferj_da_casa` e
    `ferj_do_emolumento`, a mesma do Livro Diário e da NFS-e). Fica de fora
    tudo o que não é da serventia: FERC, FADEP, FEMP, FERRFIS — cobrados por
    cima do emolumento — e o ISS. O FERJ NÃO é o FERC: o FERC são os 3% que o
    selo declara por cima; o FERJ são os 12% que saem de dentro.

BLOCO QUE QUEBRA NÃO VIRA ZERO
    Cada bloco é medido numa conexão própria. O que falhar (tabela que ainda
    não existe num banco antigo, coluna faltando) sai como `None` e com o nome
    em `nao_mediu` — «zero» seria o carimbo que mente, a lição da conferência
    diária de 02/10/2026.

SÓ LÊ. Não grava nada, nem auditoria: quem anota o acesso é a rota.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable

from bd_nativo import banco

FORMATO = "cg-painel-1"

#: As três janelas, na ordem em que a tela as oferece.
PERIODOS = ("dia", "semana", "mes")
ROTULO_DO_PERIODO = {"dia": "Hoje", "semana": "Semana", "mes": "Mês"}

#: As atribuições como o painel as mostra — os mesmos nomes do relatório
#: financeiro, na ordem do menu. «Outras» junta a grafia que não se reconhece,
#: sem esconder: ela aparece com o próprio número.
ATRIBUICOES = ("RI", "RCPN", "Notas", "Protesto", "RTD/PJ")
OUTRAS = "Outras"

#: Gravidades dos achados do gestor — a régua é a da conferência diária
#: (`gestor_conferencia.GRAVIDADES`), importada e não copiada. A palavra que
#: ela não conhece vai para «OUTRA», contada à parte e não escondida.
OUTRA_GRAVIDADE = "OUTRA"

# ------------------------------------------------------------------ janelas


def janelas(hoje: date) -> dict[str, tuple[date, date]]:
    """Início e fim (inclusive) de cada janela. Só calcula.

    A SEMANA COMEÇA NA SEGUNDA, e pode começar no mês anterior — dia 1º de
    outubro de 2026 é uma quinta. Por isso a consulta vai do menor início.
    """
    return {
        "dia": (hoje, hoje),
        "semana": (hoje - timedelta(days=hoje.weekday()), hoje),
        "mes": (hoje.replace(day=1), hoje),
    }


def _janelas_do_dia(dia: str, jan: dict[str, tuple[date, date]]) -> list[str]:
    """Em quais janelas cai uma data ISO («AAAA-MM-DD...»). Só calcula."""
    d = str(dia or "")[:10]
    if len(d) != 10:
        return []
    return [nome for nome, (ini, fim) in jan.items()
            if ini.isoformat() <= d <= fim.isoformat()]


# ------------------------------------------------------------------ blocos


def _atos_e_selos(con, jan, desde: str) -> dict:
    """Selos usados por atribuição (= atos praticados) e selos cancelados."""
    import selos_emitidos as SE
    from gestor_financeiro import _ATRIB_DO_SELO
    bd = banco(con)
    quando = "COALESCE(NULLIF(TRIM(COALESCE(usado_em,'')),''), obtido_em)"
    por = {p: {a: 0 for a in (*ATRIBUICOES, OUTRAS)} for p in PERIODOS}
    for linha in bd.ler(
            f"""SELECT atribuicao, {quando} AS quando FROM sd_selos
                 WHERE {SE.USADO} AND {quando} >= %s ORDER BY id""", (desde,)):
        grupo = _ATRIB_DO_SELO.get(str(linha["atribuicao"] or "").upper())
        grupo = grupo if grupo in ATRIBUICOES else OUTRAS
        for p in _janelas_do_dia(linha["quando"], jan):
            por[p][grupo] += 1
    cancelados = {p: 0 for p in PERIODOS}
    for linha in bd.ler(
            f"""SELECT cancelado_em FROM sd_selos
                 WHERE {SE.CANCELADO} AND cancelado_em >= %s ORDER BY id""", (desde,)):
        for p in _janelas_do_dia(linha["cancelado_em"], jan):
            cancelados[p] += 1
    return {p: {"atos_por_atribuicao": por[p],
                "selos_usados": sum(por[p].values()),
                "selos_cancelados": cancelados[p]} for p in PERIODOS}


def _receita(con, jan, desde: str, pct_ferj: int) -> dict:
    """Emolumentos líquidos do FERJ, em centavos, por janela. Só lê.

    Um selo usado por linha — a mesma seleção dos «atos praticados» deste
    painel, mais o filtro do ambiente: selo de homologação não é ato
    praticado e não é receita (a régua do Livro Diário, PR #15). O selo
    ISENTO e o DIFERIDO não somam: o isento não se cobrou, e o diferido entra
    como receita no pagamento, que o selo não diz quando foi. Selo sem
    emolumento legível também não soma — e é contado à parte, para o «zero»
    não esconder o que não deu para ler.
    """
    import selo as SL
    import selos_emitidos as SE
    # A RÉGUA DO FERJ É A DE `custas` — a mesma do Livro Diário e da NFS-e.
    # Ela entrou no `custas.py` deste ramo como CÓPIA BYTE A BYTE do bloco do
    # PR #15 (`livro-diario-ferj-e-ferc`), na mesma posição, para o merge dos
    # dois sair limpo; a máquina do merge confere que ficou uma definição só.
    from custas import ferj_do_emolumento
    bd = banco(con)
    quando = "COALESCE(NULLIF(TRIM(COALESCE(usado_em,'')),''), obtido_em)"
    vazio = {"receita_centavos": 0, "atos_cobrados": 0, "isentos": 0,
             "diferidos": 0, "sem_valor": 0}
    por = {p: dict(vazio) for p in PERIODOS}
    for linha in bd.ler(
            f"""SELECT texto, {quando} AS quando FROM sd_selos
                 WHERE {SE.USADO} AND {quando} >= %s
                   AND COALESCE(ambiente, 'PRODUCAO') = 'PRODUCAO'
                 ORDER BY id""", (desde,)):
        dentro = _janelas_do_dia(linha["quando"], jan)
        if not dentro:
            continue
        lido = SL.ler_texto(linha["texto"] or "")
        marcas = " ".join(lido.get("marcas") or []).upper()
        emol = lido.get("emolumentos")
        if "ISENT" in marcas:
            chave, liquido = "isentos", 0
        elif "DIFERID" in marcas:
            chave, liquido = "diferidos", 0
        elif emol is None:
            chave, liquido = "sem_valor", 0
        else:
            centavos = int(round(float(emol) * 100))
            chave = "atos_cobrados"
            liquido = centavos - ferj_do_emolumento(centavos, pct_ferj)
        for p in dentro:
            por[p][chave] += 1
            por[p]["receita_centavos"] += liquido
    return por


def _atendimento_periodos(con, jan, desde: str, ate: str) -> dict:
    """Senhas emitidas e espera média, por janela. A hora se calcula em
    Python (regra da casa: data e hora não se calculam no SQL)."""
    from database import _segundos
    bd = banco(con)
    total = {p: 0 for p in PERIODOS}
    prioridade = {p: 0 for p in PERIODOS}
    esperas: dict[str, list[float]] = {p: [] for p in PERIODOS}
    for t in bd.ler(
            """SELECT ticket_date, priority, created_at, started_at
                 FROM service_tickets WHERE ticket_date >= %s AND ticket_date <= %s
                ORDER BY id""", (desde, ate)):
        dentro = _janelas_do_dia(t["ticket_date"], jan)
        s = _segundos(t["created_at"], t["started_at"]) if t["started_at"] else None
        for p in dentro:
            total[p] += 1
            prioridade[p] += 1 if int(t["priority"] or 0) else 0
            if s is not None and s >= 0:
                esperas[p].append(s)
    return {p: {"senhas": total[p], "senhas_prioritarias": prioridade[p],
                "espera_media_min": (round(sum(esperas[p]) / len(esperas[p]) / 60, 1)
                                     if esperas[p] else None)}
            for p in PERIODOS}


def _atendimento_agora(con, hoje: date) -> dict:
    bd = banco(con)
    linha = bd.um(
        """SELECT
             SUM(CASE WHEN status = 'AGUARDANDO' THEN 1 ELSE 0 END) AS aguardando,
             SUM(CASE WHEN status IN ('CHAMADO', 'EM_ATENDIMENTO') THEN 1 ELSE 0 END) AS em_atendimento,
             SUM(CASE WHEN status = 'FINALIZADO' THEN 1 ELSE 0 END) AS finalizados
           FROM service_tickets WHERE ticket_date = %s""", (hoje.isoformat(),))
    return {k: int((linha[k] if linha else 0) or 0)
            for k in ("aguardando", "em_atendimento", "finalizados")}


def _protocolos(con, jan, hoje: date, desde: str) -> dict:
    """O protocolo geral do balcão: em andamento, atrasado, sem item."""
    import caixa_protocolo as CXP
    bd = banco(con)
    encerra = tuple(CXP.ENCERRAMENTOS)
    vivo = (f"COALESCE(finalizado, 0) = 0 AND situacao NOT IN "
            f"({', '.join(['%s'] * len(encerra))}) "
            "AND COALESCE(tipo, 'SERVICO') <> 'ORCAMENTO'")
    linha = bd.um(
        f"""SELECT COUNT(*) AS andamento,
                   SUM(CASE WHEN TRIM(COALESCE(previsao_entrega, '')) <> ''
                             AND previsao_entrega < %s THEN 1 ELSE 0 END) AS atrasados
              FROM cx_protocolos WHERE {vivo}""", (hoje.isoformat(), *encerra))
    abertos = {p: 0 for p in PERIODOS}
    for r in bd.ler("SELECT data_abertura FROM cx_protocolos "
                    "WHERE data_abertura >= %s ORDER BY id", (desde,)):
        for p in _janelas_do_dia(r["data_abertura"], jan):
            abertos[p] += 1
    return {
        "em_andamento": int(linha["andamento"] or 0),
        "atrasados": int(linha["atrasados"] or 0),
        # Os abertos que nunca ganharam item — candidatos a encerrar. Ficam à
        # vista para o «em andamento» não parecer maior do que o serviço é.
        "sem_item": int(CXP.quantos_abertos_sem_item(con)),
        "abertos_no_periodo": abertos,
    }


def _prenotacoes(con, hoje: date) -> dict:
    """A régua da conferência diária: só a contagem, nunca o achado (ele traz
    o nome do apresentante)."""
    import gestor_conferencia as GC
    bd = banco(con)
    abertas = bd.valor(
        "SELECT COUNT(*) AS n FROM ri_protocolos WHERE situacao = 'ABERTO'")
    suspensas = bd.valor(
        "SELECT COUNT(*) AS n FROM ri_protocolos WHERE situacao = 'ABERTO' "
        "AND prazo_suspenso_desde IS NOT NULL")
    return {
        "abertas": int(abertas or 0),
        "vencidas": len(GC.regra_prenotacao_vencida(con, hoje)),
        "a_vencer": len(GC.regra_prenotacao_a_vencer(con, hoje)),
        "a_vencer_dias_uteis": GC.PRENOTACAO_AVISO_DIAS_UTEIS,
        "prazo_suspenso": int(suspensas or 0),
    }


def _tarefas(db) -> dict:
    """As de `db.dashboard_stats` — o mesmo número da primeira tela."""
    try:
        dias = int(db.get_setting("alert_days", "5") or 5)
    except (TypeError, ValueError):
        dias = 5
    st = db.dashboard_stats(dias)
    return {
        "abertas": st["open_tasks"],
        "atrasadas": st["overdue"],
        "vencendo": st["soon"],
        "aguardando_terceiro": st["waiting"],
        "suspensas": st["tarefas_suspensas"],
        "expedientes_ativos": st["open_expedientes"],
        "_disputas": st["disputas_de_escrita"],
        "_implantacao": st["implantacao_abertas"],
    }


def _alertas(con, db) -> dict:
    """Os achados abertos do gestor, por gravidade — sem o título (ele traz
    número de ato e nome de parte)."""
    import gestor_conferencia as GC
    bd = banco(con)
    por = {g: 0 for g in (*GC.GRAVIDADES, OUTRA_GRAVIDADE)}
    for r in bd.ler(
            """SELECT gravidade, COUNT(*) AS n FROM ge_achados
                WHERE resolvido_em IS NULL GROUP BY gravidade ORDER BY gravidade"""):
        g = str(r["gravidade"] or "").upper()
        g = g if g in por else OUTRA_GRAVIDADE
        por[g] += int(r["n"])
    ultima = bd.um(
        """SELECT iniciada_em, terminada_em, erro FROM ge_execucoes
            ORDER BY id DESC LIMIT 1""")
    return {
        "achados_abertos": sum(por.values()),
        "achados_por_gravidade": por,
        "gestor_ultima_rodada": (str(ultima["iniciada_em"])[:16] if ultima else None),
        "gestor_ultima_rodada_com_erro": bool(ultima and str(ultima["erro"] or "").strip()),
        "manutencao_diaria_com_erro": bool(
            str(db.get_setting("manutencao_diaria_erro", "") or "").strip()),
    }


# ------------------------------------------------------------------ montar


def montar(db, hoje: date | None = None, agora: datetime | None = None) -> dict:
    """Os números da casa. SÓ LÊ.

    `db` é o `Database` do sistema: cada bloco abre a sua conexão, para que a
    falha de um (no PostgreSQL, uma consulta que quebra aborta a transação
    inteira) não leve os outros junto.
    """
    agora = agora or datetime.now()
    hoje = hoje or agora.date()
    jan = janelas(hoje)
    desde = min(ini for ini, _ in jan.values()).isoformat()
    ate = hoje.isoformat()
    nao_mediu: list[str] = []

    def medir(nome: str, fn: Callable[..., Any], com_conexao: bool = True):
        try:
            if not com_conexao:
                return fn()
            with db.connect() as con:
                return fn(con)
        except Exception:                                  # noqa: BLE001
            nao_mediu.append(nome)
            return None

    selos = medir("selos", lambda con: _atos_e_selos(con, jan, desde))
    # O percentual do FERJ é configuração (`custas.CHAVE_PERCENTUAL_FERJ`);
    # ilegível é recusa, e a receita sai como «—», nunca calculada com zero.
    from custas import percentual_ferj_da_casa
    pct_ferj = medir("ferj", lambda con: percentual_ferj_da_casa(con))
    receita = (medir("receita", lambda con: _receita(con, jan, desde, pct_ferj))
               if pct_ferj is not None else None)
    senhas = medir("atendimento", lambda con: _atendimento_periodos(con, jan, desde, ate))
    periodos: dict[str, dict] = {}
    for p in PERIODOS:
        ini, fim = jan[p]
        periodos[p] = {
            "rotulo": ROTULO_DO_PERIODO[p],
            "inicio": ini.isoformat(),
            "fim": fim.isoformat(),
            **((selos or {}).get(p) or {"atos_por_atribuicao": None,
                                         "selos_usados": None,
                                         "selos_cancelados": None}),
            **((receita or {}).get(p) or {"receita_centavos": None,
                                           "atos_cobrados": None,
                                           "isentos": None,
                                           "diferidos": None,
                                           "sem_valor": None}),
            **((senhas or {}).get(p) or {"senhas": None,
                                          "senhas_prioritarias": None,
                                          "espera_media_min": None}),
        }
    protocolos = medir("protocolos", lambda con: _protocolos(con, jan, hoje, desde))
    if protocolos:
        for p in PERIODOS:
            periodos[p]["protocolos_abertos"] = protocolos["abertos_no_periodo"][p]
        protocolos = {k: v for k, v in protocolos.items() if k != "abertos_no_periodo"}
    else:
        for p in PERIODOS:
            periodos[p]["protocolos_abertos"] = None
    tarefas = medir("tarefas", lambda: _tarefas(db), com_conexao=False)
    alertas = medir("alertas", lambda con: _alertas(con, db))
    if alertas is not None and tarefas is not None:
        alertas["disputas_de_escrita"] = tarefas["_disputas"]
        alertas["implantacao_abertas"] = tarefas["_implantacao"]
    if tarefas is not None:
        tarefas = {k: v for k, v in tarefas.items() if not k.startswith("_")}
    return {
        "formato": FORMATO,
        "gerado_em": agora.isoformat(timespec="seconds"),
        "hoje": hoje.isoformat(),
        # Com que percentual o FERJ foi abatido (centésimos de ponto: 1200 =
        # 12,00%) — a tela o mostra ao lado do número, como o Livro Diário.
        "ferj_percentual_centesimos": pct_ferj,
        "periodos": periodos,
        "agora": {
            "protocolos": protocolos,
            "prenotacoes": medir("prenotacoes", lambda con: _prenotacoes(con, hoje)),
            "tarefas": tarefas,
            "atendimento": medir("atendimento_agora",
                                 lambda con: _atendimento_agora(con, hoje)),
            "alertas": alertas,
        },
        "nao_mediu": nao_mediu,
    }


def reais(centavos: Any) -> str:
    """12345 -> «R$ 123,45». Para a tela; o retrato leva os centavos."""
    if centavos is None:
        return "—"
    v = int(centavos) / 100
    return "R$ " + f"{v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
