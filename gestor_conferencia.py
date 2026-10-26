"""A conferência diária da casa — as regras que o gestor roda toda manhã.

    «preciso que faça tudo, eu fiscalizo e reviso depois» — o oficial, 06/10/2026

DE ONDE VIERAM AS REGRAS
    Do panorama de conformidade de 02/10/2026, feito à mão contra a produção.
    Cada coisa que ele achou virou uma regra aqui, para não depender de alguém
    lembrar de olhar de novo: os quinze do SIRC fora do prazo, a FUNAI, a CRC, a
    comunicação mensal de óbitos, o IBGE, a CENSEC, a DOI, os atos sem selo, os
    selos cancelados só no sistema, as prenotações vencidas, os registros sem
    consulta ao CNIB, a cópia do CNIB parada e o backup fora do servidor.

AS REGRAS SÃO CÓDIGO, E NÃO JULGAMENTO DE MODELO
    Prazo, selo e numeração têm resposta certa. Quem decide se um achado existe
    é a consulta, que responde igual todo dia; o modelo de linguagem fica para o
    que é texto (minuta, cobrança, explicação).

NENHUMA REGRA DEVOLVE ZERO POR ENGANO
    No panorama de 02/10 o painel do Registro Civil dizia «zero» comunicações de
    óbito com dois óbitos no mês, e o atualizador do CNIB dizia «não há ordens»
    com a cópia parada havia sete semanas. **Regra que quebra vira achado
    `NAO_MEDIU`, com o erro à vista** — nunca lista vazia.

O QUE ESTE MÓDULO NÃO FAZ
    Não escreve nada. Só lê e devolve achados; quem grava é `gestor_rotina`.
"""
from __future__ import annotations

import calendar
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from bd_nativo import banco
from ri_schema import eh_dia_util, soma_dias_uteis

#: O CORTE É ORDEM DO OFICIAL, 06/10/2026: «não crie tarefas para atos
#: praticados antes de 10 de setembro de 2026. sistema não estava plenamente
#: implementado». Era 01/09 (a casa lavra no sistema desde 09/09), e a DOI
#: começava em agosto por causa do arquivo do Livro 30 — os dois saíram.
#: Ato anterior ao corte não vira achado; competência que termina antes dele
#: não é cobrada; e a que atravessa o corte conta só o que veio depois.
IMPLANTACAO = "2026-09-10"
#: Um prazo entra na fila quando faltam até tantos dias corridos.
JANELA_DE_AVISO = 10
#: A cópia local do CNIB é tida como parada quando a ordem mais nova é mais
#: velha que isto. O CNIB nacional recebe dezenas de milhares de ordens por mês.
CNIB_DIAS_TOLERADOS = 3
#: O pacote do dia (o diário do banco, ou um completo): o Provimento pede cópia
#: diária. Um dia de folga porque a conferência roda de manhã (07h30) e o
#: backup no horário sai às 18h: de manhã, o «do dia» é o da noite anterior.
BACKUP_DIAS_TOLERADOS = 1
#: O completo (banco + digitalizações + acervo): UMA VEZ POR SEMANA — decisão
#: do oficial em 26/10/2026 («completo uma vez por semana»). Antes a regra
#: cobrava o completo com a folga do diário, e acusava seis dias em sete.
BACKUP_COMPLETO_DIAS_TOLERADOS = 7

GRAVIDADES = ("CRITICO", "VENCIDO", "NAO_MEDIU", "PRAZO", "ATENCAO")

ORIGENS_DO_ACERVO = ("EOFICIO", "ARQUIVO", "IMPORTACAO")

DESTINOS_DO_OBITO = (
    ("OBITO_TRE", "ao juiz eleitoral"),
    ("OBITO_ME", "ao Ministério da Economia"),
    ("OBITO_RFB", "à Receita Federal"),
    ("OBITO_IIMA", "ao Instituto de Identificação do MA"),
    ("JUNTA_MILITAR", "à Junta de Serviço Militar"),
)


# ----------------------------------------------------------------- datas

def _dia(texto) -> date | None:
    bruto = str(texto or "")[:10]
    try:
        return date(int(bruto[:4]), int(bruto[5:7]), int(bruto[8:10]))
    except (ValueError, IndexError):
        return None


def _quinto_dia_util(ano: int, mes: int) -> date:
    dia, contados = date(ano, mes, 1), 0
    while True:
        if eh_dia_util(dia):
            contados += 1
            if contados == 5:
                return dia
        dia += timedelta(days=1)


def _mes_seguinte(ano: int, mes: int) -> tuple[int, int]:
    return (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def _meses(de: str, ate: date) -> list[tuple[int, int]]:
    """Os meses de `de` (AAAA-MM) até o mês de `ate`, inclusive."""
    ano, mes = int(de[:4]), int(de[5:7])
    saida = []
    while (ano, mes) <= (ate.year, ate.month):
        saida.append((ano, mes))
        ano, mes = _mes_seguinte(ano, mes)
    return saida


def antes_do_corte(dia) -> bool:
    """O ato é anterior ao corte de 10/09/2026? Data que não se lê não é."""
    d = dia if isinstance(dia, date) else _dia(dia)
    return d is not None and d.isoformat() < IMPLANTACAO


def _situacao_do_prazo(prazo: date, hoje: date) -> str | None:
    """VENCIDO, PRAZO (dentro da janela) ou None (ainda longe)."""
    if hoje > prazo:
        return "VENCIDO"
    if (prazo - hoje).days <= JANELA_DE_AVISO:
        return "PRAZO"
    return None


def _achado(chave, regra, gravidade, setor, titulo, detalhe="", prazo=None,
            fundamento="") -> dict:
    return {"chave": chave, "regra": regra, "gravidade": gravidade,
            "setor": setor, "titulo": titulo, "detalhe": detalhe,
            "prazo": prazo.isoformat() if isinstance(prazo, date) else prazo,
            "fundamento": fundamento}


def _envios(con: sqlite3.Connection, central: str) -> list[dict]:
    return banco(con).ler(
        "SELECT * FROM ge_envios WHERE central = %s AND situacao <> 'REJEITADO' "
        "ORDER BY id", (central,))


def _referencias_enviadas(con, central) -> set[str]:
    return {r["referencia"] for r in _envios(con, central) if r["referencia"]}


def _competencias_enviadas(con, central) -> set[str]:
    return {r["competencia"] for r in _envios(con, central) if r["competencia"]}


# ---------------------------------------------------------- Registro Civil

def regra_sirc(con, hoje: date) -> list[dict]:
    import sirc_remessa
    enviados = _referencias_enviadas(con, "SIRC")
    saida = []
    for p in sirc_remessa.pendentes_de_remessa(con):
        datas = [_dia(a.get("data_ato")) for a in p.get("atos") or []]
        ultima = max([d for d in datas if d] or [_dia(p.get("data_ato"))]
                     or [None], default=None)
        onde = p.get("onde", "rc_assentos")
        ref = f"{onde}:{p['assento_id']}:{ultima}"
        # O registro se identifica pelo assento; a ALTERAÇÃO, também pela data
        # do ato mais novo — averbação nova depois do envio é envio novo.
        if (ultima is None or antes_do_corte(ultima) or ref in enviados
                or (onde == "rc_assentos" and f"{onde}:{p['assento_id']}" in enviados)):
            continue
        prazo = soma_dias_uteis(ultima, 1)
        gravidade = _situacao_do_prazo(prazo, hoje) or "PRAZO"
        oque = "alteração" if p.get("onde") == "rc_atos" else "registro"
        saida.append(_achado(
            f"SIRC:{ref}", "SIRC", gravidade, "RCPN",
            f"SIRC: {oque} de {str(p.get('tipo') or '').lower()} "
            f"nº {p.get('numero')} ({p.get('nome')}) não enviado",
            f"Lavrado em {ultima:%d/%m/%Y}.", prazo,
            "art. 225 do Código de Normas do TJMA; art. 68 da Lei 8.212/1991"))
    return saida


def regra_sirc_cancelamentos(con, hoje: date) -> list[dict]:
    import sirc_remessa
    enviados = _referencias_enviadas(con, "SIRC_CANCELAMENTO")
    saida = []
    for p in sirc_remessa.pendentes_de_cancelamento(con):
        ref = f"rc_assentos:{p['id']}"
        if ref in enviados or antes_do_corte(p.get("data_ato")):
            continue
        vivo = p.get("matricula_em_uso_por")
        if "matricula_em_uso_por" not in p and p.get("matricula"):
            # A VERSÃO INSTALADA PODE NÃO TER A TRAVA DE 02/10/2026, e o gestor
            # roda com ela (FERRAMENTAS\GESTOR). Medido no ensaio de 06/10: o
            # cancelamento do óbito 1981 saía «a enviar» — e o SIRC cancelaria,
            # pela matrícula, o 8315, que é o que vale. A trava mora aqui também.
            linha = banco(con).um(
                """SELECT id FROM rc_assentos WHERE matricula = %s AND id <> %s
                      AND COALESCE(situacao,'ATIVO') = 'ATIVO' ORDER BY id LIMIT 1""",
                (p["matricula"], p["id"]))
            vivo = linha["id"] if linha else None
        if p.get("numero") is None:
            # SEM NÚMERO NÃO HOUVE TERMO. Medido em 06/10/2026: três assentos
            # cancelados sem número e sem averbação de cancelamento — cópias
            # refeitas no balcão. Cancelar no SIRC o que nunca foi lavrado
            # seria informação inexata (§ 4º do art. 225).
            saida.append(_achado(
                f"SIRC_CANC:{ref}", "SIRC_CANCELAMENTO", "ATENCAO", "RCPN",
                f"Assento cancelado sem número de termo ({p.get('nome')}, "
                f"id {p['id']})",
                "Conferir se chegou a ser lavrado. Se não, não há o que cancelar "
                "no SIRC; se sim, faltam o número e a averbação do cancelamento.",
                None, "art. 225 do Código de Normas do TJMA"))
            continue
        saida.append(_achado(
            f"SIRC_CANC:{ref}", "SIRC_CANCELAMENTO",
            "ATENCAO" if vivo else "PRAZO", "RCPN",
            f"SIRC: cancelamento do termo nº {p.get('numero')} "
            f"({p.get('nome')}) não comunicado",
            (f"RETIDO: a mesma matrícula está no assento ativo {vivo} — mandar "
             "este cancelamento cancelaria, no SIRC, o registro que vale. "
             "Conferir no SIRC-Web o que de fato foi enviado." if vivo else
             f"Motivo: {p.get('motivo') or '(sem averbação de cancelamento)'}."),
            None, "art. 225 do Código de Normas do TJMA"))
    return saida


def regra_funai(con, hoje: date) -> list[dict]:
    import rc_funai
    enviados = _referencias_enviadas(con, "FUNAI")
    saida = []
    for p in rc_funai.pendentes(con, hoje=hoje.isoformat()):
        ref = f"rc_assentos:{p['id']}"
        if ref in enviados or antes_do_corte(p.get("data_ato")):
            continue
        saida.append(_achado(
            f"FUNAI:{ref}", "FUNAI", "VENCIDO", "RCPN",
            f"FUNAI: nascimento indígena nº {p.get('numero')} "
            f"({p.get('nome')}) não comunicado",
            f"Lavrado há {p.get('dias')} dias; o prazo é «imediatamente».",
            _dia(p.get("data_ato")), "art. 253, § 2º, do Código de Normas"))
    return saida


def regra_crc(con, hoje: date) -> list[dict]:
    import crc_carga
    # O ACERVO NÃO VIRA TAREFA: até 06/10 ele entrava como um achado só («N
    # assentos do acervo fora da carga»), e o corte do oficial o tirou — sobe
    # por lote, quando ele mandar, e não por cobrança.
    saida = []
    for p in crc_carga.pendentes_de_carga(con):
        lavrado = _dia(p.get("data_ato"))
        if lavrado is None or antes_do_corte(lavrado):
            continue
        prazo = lavrado + timedelta(days=5)
        gravidade = _situacao_do_prazo(prazo, hoje) or "PRAZO"
        saida.append(_achado(
            f"CRC:rc_assentos:{p['id']}", "CRC", gravidade, "RCPN",
            f"CRC: {str(p.get('especie') or '').lower()} nº {p.get('numero')} "
            f"({p.get('nome')}) fora da carga",
            f"Lavrado em {lavrado:%d/%m/%Y}.", prazo, "arts. 243 e 367"))
    return saida


def regra_obitos_do_mes(con, hoje: date) -> list[dict]:
    """A comunicação mensal de óbitos, destino por destino.

    **SÓ OS ÓBITOS ATIVOS.** Em 02/10/2026 a lista do mês contava o termo 1981
    duas vezes — o lavrado e cancelado por engano, e o que vale —, e a
    comunicação sairia em duplicidade. Aqui o cancelado não entra.

    **O MÊS SEM ÓBITO TAMBÉM COBRA.** O painel do Registro Civil já dizia que a
    comunicação de mês sem movimento é a que se esquece; ela entra como
    comunicação negativa.
    """
    saida = []
    for ano, mes in _meses(IMPLANTACAO[:7], hoje):
        if (ano, mes) >= (hoje.year, hoje.month):
            continue
        comp = f"{ano:04d}-{mes:02d}"
        prazo = _quinto_dia_util(*_mes_seguinte(ano, mes))
        gravidade = _situacao_do_prazo(prazo, hoje)
        if gravidade is None:
            continue
        obitos = banco(con).ler(
            f"""SELECT numero, nome FROM rc_assentos
                 WHERE especie = 'OBITO' AND data_ato ILIKE %s
                   AND data_ato >= %s
                   AND COALESCE(situacao,'ATIVO') = 'ATIVO'
                   AND COALESCE(origem,'') NOT IN
                       ({','.join(['%s'] * len(ORIGENS_DO_ACERVO))})
              ORDER BY numero, id""",
            (comp + "%", IMPLANTACAO, *ORIGENS_DO_ACERVO))
        lista = ", ".join(f"nº {o['numero']} ({o['nome']})" for o in obitos)
        for central, nome in DESTINOS_DO_OBITO:
            # O QUE A TELA DAS COMUNICAÇÕES REGISTROU TAMBÉM CONTA (09/10/2026):
            # até aqui só `ge_envios` era lido, e a comunicação registrada como
            # enviada ou dispensada em `rc_comunicacoes` continuava cobrada.
            import gestor_cargas_rcpn
            if (comp in _competencias_enviadas(con, central)
                    or comp in gestor_cargas_rcpn.competencias_comunicadas(con, central)):
                continue
            saida.append(_achado(
                f"{central}:{comp}", "OBITO_MENSAL", gravidade, "RCPN",
                f"Óbitos de {mes:02d}/{ano}: comunicação {nome} não registrada",
                (f"{len(obitos)} óbito(s): {lista}." if obitos else
                 "Mês sem óbito — vai comunicação negativa."),
                prazo, "Lei 4.375/1964" if central == "JUNTA_MILITAR"
                else "art. 226 do Código de Normas do TJMA"))
    return saida


def regra_ibge(con, hoje: date) -> list[dict]:
    entregues = {(r["ano"], r["trimestre"]) for r in banco(con).ler(
        "SELECT ano, trimestre FROM ib_entregas WHERE enviada_em IS NOT NULL "
        "ORDER BY ano, trimestre")}
    entregues |= {(int(c[:4]), int(c[-1])) for c in
                  _competencias_enviadas(con, "IBGE") if "-T" in c}
    inicio = _dia(IMPLANTACAO)
    saida = []
    for ano in (hoje.year - 1, hoje.year):
        for tri in (1, 2, 3, 4):
            fim_tri = date(ano, tri * 3, calendar.monthrange(ano, tri * 3)[1])
            if fim_tri < inicio or (ano, tri) in entregues:
                continue
            venc_ano, venc_mes = _mes_seguinte(ano, tri * 3)
            prazo = date(venc_ano, venc_mes, 8)
            gravidade = _situacao_do_prazo(prazo, hoje)
            if gravidade is None:
                continue
            saida.append(_achado(
                f"IBGE:{ano}-T{tri}", "IBGE", gravidade, "RCPN",
                f"IBGE: mapa do {tri}º trimestre de {ano} não entregue",
                "Multa de 1 a 5 salários mínimos, sem prejuízo da ação penal.",
                prazo, "art. 224 do Código de Normas; art. 49 da Lei 6.015/1973"))
    return saida


# ------------------------------------------------------------------- Notas

TIPOS_CENSEC = ("ESCRITURA", "PROCURACAO", "SUBSTABELECIMENTO", "ATA",
                "TESTAMENTO", "REVOGACAO", "RENUNCIA")


def regra_censec(con, hoje: date) -> list[dict]:
    import notas_censec
    enviadas = {(r["ano_referencia"], r["mes_referencia"], r["quinzena"])
                for r in banco(con).ler(
                    """SELECT ano_referencia, mes_referencia, quinzena
                         FROM nt_remessas WHERE enviada_em IS NOT NULL
                        ORDER BY ano_referencia, mes_referencia, quinzena""")}
    enviadas |= {(int(c[:4]), int(c[5:7]), int(c[-1]))
                 for c in _competencias_enviadas(con, "CENSEC") if "-Q" in c}
    saida = []
    for ano, mes in _meses(IMPLANTACAO[:7], hoje):
        for quinzena in (1, 2):
            if (ano, mes, quinzena) in enviadas:
                continue
            ini, fim = notas_censec.periodo_da_quinzena(ano, mes, quinzena)
            if fim >= hoje.isoformat() or fim < IMPLANTACAO:
                continue
            ini = max(ini, IMPLANTACAO)
            prazo = _dia(notas_censec.prazo_de_fechamento(ano, mes, quinzena))
            gravidade = _situacao_do_prazo(prazo, hoje)
            if gravidade is None:
                continue
            atos = banco(con).ler(
                f"""SELECT tipo, livro, folha FROM nt_atos
                     WHERE situacao = 'LAVRADO' AND data >= %s AND data <= %s
                       AND tipo IN ({','.join(['%s'] * len(TIPOS_CENSEC))})
                     ORDER BY id""",
                (ini, fim + "z", *TIPOS_CENSEC))
            if not atos:
                continue
            saida.append(_achado(
                f"CENSEC:{ano:04d}-{mes:02d}-Q{quinzena}", "CENSEC", gravidade,
                "NOTAS",
                f"CENSEC: {quinzena}ª quinzena de {mes:02d}/{ano} não enviada",
                f"{len(atos)} ato(s) na quinzena: " + ", ".join(
                    f"{a['tipo'].lower()} L{a['livro']} fl. {a['folha']}"
                    for a in atos[:8]),
                prazo, "Provimento CNJ 18/2012"))
    return saida


def regra_censec_automatico(con, hoje: date) -> list[dict]:
    """O envio automático à CENSEC (09/10/2026): impedidos, prazo, fechamento.

    A regra mora em `censec_automatico.py`, junto do envio que ela vigia.
    """
    import censec_automatico
    return censec_automatico.regra(con, hoje)


def regra_doi(con, hoje: date) -> list[dict]:
    """Todo mês deve uma resposta à Receita — a DOI ou a declaração negativa.

    A inspeção cobra «comprovações de DOI ou declarações negativas dos meses
    sem atos imobiliários» (`notas_doi.competencias_em_aberto`): o mês vazio é
    justamente o que não aparece em lista nenhuma, e por isso a lista sai do
    calendário.
    """
    import notas_doi
    entregues = {r["competencia"] for r in banco(con).ler(
        "SELECT competencia FROM ri_doi_remessas WHERE entregue_em IS NOT NULL "
        "ORDER BY competencia")}
    entregues |= _competencias_enviadas(con, "DOI")
    saida = []
    for ano, mes in _meses(IMPLANTACAO[:7], hoje):
        comp = f"{ano:04d}-{mes:02d}"
        if comp in entregues or (ano, mes) == (hoje.year, hoje.month):
            continue
        prazo = _dia(notas_doi.prazo_de_entrega(f"{comp}-01"))
        gravidade = _situacao_do_prazo(prazo, hoje)
        if gravidade is None:
            continue
        atos = int(banco(con).valor(
            """SELECT count(*) FROM nt_atos
                WHERE situacao = 'LAVRADO' AND data ILIKE %s
                  AND data >= %s
                  AND (doi_transacao IS NOT NULL OR COALESCE(com_imovel,0) = 1)""",
            (comp + "%", IMPLANTACAO)))
        # **A DOI É DA SERVENTIA, E O REGISTRO DE IMÓVEIS TAMBÉM DECLARA** —
        # achado em 21/10/2026: setembro tinha compra e venda (R-01/[n.]) e
        # duas doações (R-02/[n.] e [n.]) registradas, e este achado dizia
        # «sem ato com imóvel no sistema: conferir se cabe declaração
        # negativa», porque só contava as escrituras. Conta-se o REGISTRO
        # (`tipo = 'R'`) não cancelado; a averbação não transmite.
        registros = int(banco(con).valor(
            """SELECT count(*) FROM ri_atos
                WHERE tipo = 'R' AND COALESCE(cancelado,0) = 0
                  AND data_ato ILIKE %s AND data_ato >= %s""",
            (comp + "%", IMPLANTACAO)))
        # A escritura com imóvel que ficou «em lavratura» pode ter sido
        # assinada no papel — e então ela é deste mês e da DOI. Não se conta
        # como ato; avisa-se, para alguém fechar ou explicar.
        em_lavratura = int(banco(con).valor(
            """SELECT count(*) FROM nt_atos
                WHERE situacao = 'EM_LAVRATURA' AND data ILIKE %s
                  AND data >= %s AND COALESCE(com_imovel,0) = 1""",
            (comp + "%", IMPLANTACAO)))
        partes_do_detalhe = []
        if registros:
            partes_do_detalhe.append(
                f"{registros} registro(s) no Registro de Imóveis no mês")
        if atos:
            partes_do_detalhe.append(
                f"{atos} escritura(s) com imóvel lavrada(s) nas Notas")
        detalhe = ("; ".join(partes_do_detalhe) + " — não cabe negativa."
                   if partes_do_detalhe
                   else "Sem registro no RI nem escritura com imóvel no "
                        "sistema: conferir se cabe declaração negativa ou se o "
                        "ato foi lavrado fora do sistema.")
        if em_lavratura:
            detalhe += (f" Há {em_lavratura} escritura(s) com imóvel ainda «em "
                        f"lavratura» com data do mês: se foi assinada, entra.")
        saida.append(_achado(
            f"DOI:{comp}", "DOI", gravidade,
            "RI" if registros and not atos else "NOTAS",
            f"DOI de {mes:02d}/{ano} sem recibo registrado",
            detalhe,
            prazo, "DOI — Receita Federal (último dia útil do mês seguinte)"))
    return saida


# ------------------------------------------------------------------- selos

#: Quem responde pelo selo é quem responde pelo ato que ele sela. A divisão é a
#: do oficial em 06/10/2026: o operacional (certidão, carga, papelada) de um
#: lado; o título, o ato final e a qualificação do outro.
_SETOR_DO_SELO = {
    "rc_atos": "RCPN", "rc_certidoes": "RCPN",
    "ri_certidoes": "RI", "ri_matriculas": "RI",
    "ri_atos": "RI_QUALIFICACAO", "ra_atos": "RI_QUALIFICACAO",
    "ri_protocolos": "RI_QUALIFICACAO",
    "nt_atos": "NOTAS_QUALIFICACAO", "nt_reconhecimentos": "NOTAS",
    "nt_autenticacoes": "NOTAS", "nt_cartoes": "NOTAS",
    "rg_atos": "RCPJ_RTD_QUALIFICACAO", "at_certidoes": "RCPJ_RTD",
    "pt_atos": "PROTESTO",
}


def _d(valor) -> str:
    """A data do dia, recortada em Python: recorte de texto no SQL muda de nome fora
    do SQLite, e o teto de módulo novo em `test_portabilidade` é zero."""
    return str(valor or "")[:10]


def _junto(a, sep: str, b) -> str:
    return f"{a}{sep}{b}" if b not in (None, "") else str(a)


def setor_da_tabela(tabela: str | None) -> str:
    return _SETOR_DO_SELO.get(tabela or "", "GESTAO")


def regra_atos_sem_selo(con, hoje: date) -> list[dict]:
    consultas = (
        ("RCPN", "rc_atos", """
            SELECT a.id, a.tipo, NULL AS tipo2, s.numero, NULL AS numero2, a.criado_em AS dia
              FROM rc_atos a LEFT JOIN rc_assentos s ON s.id = a.assento_id
             WHERE a.criado_em >= %s AND COALESCE(a.selo,'') = ''
               AND COALESCE(s.situacao,'ATIVO') = 'ATIVO'
             ORDER BY a.id"""),
        ("RI_QUALIFICACAO", "ri_atos", """
            SELECT id, tipo, numero AS tipo2, matricula_id AS numero,
                   NULL AS numero2, lavrado_em AS dia
              FROM ri_atos
             WHERE lavrado_em >= %s AND COALESCE(acervo,0) = 0
               AND COALESCE(cancelado,0) = 0 AND COALESCE(selo_texto,'') = ''
               AND NOT (COALESCE(isento,0) = 1
                        AND COALESCE(motivo_isencao,'') <> '')
             ORDER BY id"""),
        ("RCPJ_RTD_QUALIFICACAO", "rg_atos", """
            SELECT id, tipo, NULL AS tipo2, registro_id AS numero, NULL AS numero2, criado_em AS dia
              FROM rg_atos
             WHERE criado_em >= %s AND COALESCE(selo,'') = ''
               AND COALESCE(motivo_cancelamento,'') = ''
             ORDER BY id"""),
        ("NOTAS_QUALIFICACAO", "nt_atos", """
            SELECT id, tipo, NULL AS tipo2, livro AS numero, folha AS numero2,
                   data AS dia
              FROM nt_atos
             WHERE data >= %s AND situacao = 'LAVRADO'
               AND COALESCE(selo,'') = ''
             ORDER BY id"""),
    )
    saida = []
    for setor, tabela, sql in consultas:
        for r in banco(con).ler(sql, (IMPLANTACAO,)):
            saida.append(_achado(
                f"SEM_SELO:{tabela}:{r['id']}", "ATO_SEM_SELO", "ATENCAO", setor,
                f"Ato sem selo: {tabela} {r['id']} ({_junto(r['tipo'], '-', r['tipo2'])}, "
                f"{_junto(r['numero'], '/', r['numero2'])})",
                f"Lançado em {_d(r['dia'])}. Selar, ou marcar a isenção com o motivo.",
                None, "Código de Normas do TJMA — selo de fiscalização"))
    return saida


def regra_selo_cancelado_so_no_sistema(con, hoje: date) -> list[dict]:
    """O selo cancelado no sistema e não no Portal do Selo continua usado no TJ.

    A palavra que prova o cancelamento lá é dita por quem cancelou; o que a
    regra pega é o cancelamento cujo motivo **não** fala do TJ/portal.
    """
    saida = []
    for r in banco(con).ler(
            """SELECT numero, tabela, ato_id, cancelado_em, cancelado_por,
                      motivo_cancelamento FROM sd_selos
                WHERE cancelado_em IS NOT NULL
                  AND COALESCE(usado_em, obtido_em) >= %s ORDER BY id""", (IMPLANTACAO,)):
        motivo = (r["motivo_cancelamento"] or "").upper()
        if any(p in motivo for p in ("TJ", "PORTAL")) and "LOCAL" not in motivo:
            continue
        saida.append(_achado(
            f"SELO_LOCAL:{r['numero']}", "SELO_CANCELADO_LOCAL", "ATENCAO",
            setor_da_tabela(r["tabela"]),
            f"Selo {r['numero']} cancelado no sistema: confirmar no Portal do Selo",
            f"Cancelado em {str(r['cancelado_em'])[:10]} por {r['cancelado_por']}: "
            f"{r['motivo_cancelamento']}", None, "Portal do Selo — TJMA"))
    return saida


# ------------------------------------------------------- Registro de Imóveis

def regra_prenotacao_vencida(con, hoje: date) -> list[dict]:
    saida = []
    for r in banco(con).ler(
            """SELECT numero, data_prenotacao, data_limite, natureza_titulo,
                      apresentante FROM ri_protocolos
                WHERE situacao = 'ABERTO' AND data_limite < %s
                  AND data_prenotacao >= %s
                  AND prazo_suspenso_desde IS NULL ORDER BY id""", (hoje.isoformat(), IMPLANTACAO)):
        teste = (r["natureza_titulo"] or "").strip().upper() == "TESTE"
        saida.append(_achado(
            f"PRENOTACAO:{r['numero']}", "PRENOTACAO_VENCIDA",
            "ATENCAO" if teste else "VENCIDO", "RI_QUALIFICACAO",
            (f"Protocolo nº {r['numero']} de TESTE aberto na produção" if teste
             else f"Prenotação nº {r['numero']} vencida e ainda aberta"),
            f"Prenotada em {r['data_prenotacao']}, prazo até {r['data_limite']}. "
            "Registrar, suspender o prazo com motivo, ou cancelar.",
            _dia(r["data_limite"]), "art. 205 da Lei 6.015/1973"))
    return saida


#: Quantos dias úteis antes do vencimento a prenotação começa a ser cobrada.
PRENOTACAO_AVISO_DIAS_UTEIS = 5


def regra_prenotacao_a_vencer(con, hoje: date) -> list[dict]:
    """A prenotação cobrada ANTES de vencer — o trabalho do oficial é não deixar
    vencer, e a regra antiga só acusava depois (06/10/2026: 14 abertas, as
    primeiras vencendo em 14/10). Vencida, a prioridade do título se perde."""
    limite = soma_dias_uteis(hoje, PRENOTACAO_AVISO_DIAS_UTEIS).isoformat()
    saida = []
    for r in banco(con).ler(
            """SELECT numero, data_prenotacao, data_limite, natureza_titulo,
                      apresentante FROM ri_protocolos
                WHERE situacao = 'ABERTO' AND data_limite >= %s AND data_limite <= %s
                  AND data_prenotacao >= %s AND prazo_suspenso_desde IS NULL
                ORDER BY id""",
            (hoje.isoformat(), limite, IMPLANTACAO)):
        saida.append(_achado(
            f"PRENOT_VENCE:{r['numero']}", "PRENOTACAO_A_VENCER", "PRAZO",
            "RI_QUALIFICACAO",
            f"Prenotação nº {r['numero']} vence em {_dia(r['data_limite']):%d/%m} "
            f"({r['apresentante'] or 'sem apresentante'})",
            f"{r['natureza_titulo'] or 'Título'}, prenotado em {r['data_prenotacao']}. "
            "Qualificar: registrar, ou emitir a nota devolutiva antes do prazo.",
            _dia(r["data_limite"]), "art. 205 da Lei 6.015/1973"))
    return saida


def regra_digitalizacao_da_ficha(con, hoje: date) -> list[dict]:
    """R ou AV lavrado e a ficha sem imagem nova em 7 dias corridos.

    Ordem do oficial em 06/10/2026: tarefa para quem digitaliza; vencido o
    prazo, a tarefa fica CRÍTICA (e aparece na janela de avisos da casa) e o
    administrador é notificado com uma tarefa crítica própria. A data que vale
    é a da IMAGEM — ver `ri_digi_prazo`.
    """
    import ri_digi_prazo as DP
    saida = []
    for p in DP.pendentes(con, hoje):
        quando = f"{p['prazo']:%d/%m}"
        saida.append(_achado(
            f"DIGI:{p['matricula_id']}", "DIGITALIZACAO_DA_FICHA",
            "CRITICO" if p["vencida"] else "PRAZO", "RI",
            f"Matrícula {p['numero']}: digitalizar a ficha "
            + (f"— prazo VENCIDO em {quando}" if p["vencida"] else f"até {quando}"),
            f"Ato(s) fora da imagem: {p['atos']}. Última imagem: "
            f"{(p['imagem'] or 'nenhuma')[:16].replace('T', ' ')}.", p["prazo"],
            "ordem do oficial de 06/10/2026 — 7 dias corridos"))
        if p["vencida"]:
            saida.append(_achado(
                f"DIGI_ADM:{p['matricula_id']}", "DIGITALIZACAO_ATRASADA", "CRITICO",
                "GESTAO", f"Matrícula {p['numero']} sem digitalização há {p['dias']} dias "
                f"depois do ato ({p['atos']})",
                "A tarefa de quem digitaliza já está crítica; esta é a notificação "
                "do administrador.", p["prazo"], ""))
    return saida


def regra_revisao_do_agente(con, hoje: date) -> list[dict]:
    """O que a revisão em lote dos atos passados apontou e ninguém conferiu.

    Vem de `tools/revisao_em_lote.py importar` (origem AGENTE). O ato já foi
    lavrado: o apontamento é para quem qualifica decidir se cabe averbação de
    retificação. Some quando alguém marca «conferi» na tela das leituras.
    """
    import json as _json
    if not banco(con).tem_tabela("rv_revisoes"):
        return []
    saida = []
    for rv in banco(con).ler(
            """SELECT id, atribuicao, rotulo, resultado_json, graves FROM rv_revisoes
                WHERE origem = 'AGENTE' AND situacao = 'PRONTA'
                  AND justificado_em IS NULL ORDER BY id"""):
        rid, atribuicao, rotulo, resultado, graves = (
            rv["id"], rv["atribuicao"], rv["rotulo"], rv["resultado_json"], rv["graves"])
        achados = (_json.loads(resultado or "{}").get("achados") or [])
        if not achados:
            continue
        primeiro = achados[0]
        saida.append(_achado(
            f"REV_AGENTE:{rid}", "REVISAO_DO_AGENTE", "CRITICO" if graves else "ATENCAO",
            "NOTAS_QUALIFICACAO" if atribuicao == "NOTAS" else "RI_QUALIFICACAO",
            f"{rotulo}: {primeiro.get('o_que')}"[:240],
            "; ".join(str(a.get("o_que")) for a in achados[1:4]) or
            "Conferir no texto do ato; se couber, averbação de retificação.", None, ""))
    return saida


def regra_registro_sem_cnib(con, hoje: date) -> list[dict]:
    """Registro lavrado com ORDEM DE INDISPONIBILIDADE ativa contra uma das partes.

    ORDEM DO OFICIAL, 06/10/2026: «coisa da cnib já temos a base atualizada, só
    verificar se tem ordem». Até aqui a regra cobrava a CONSULTA ANOTADA no ato
    (`ri_atos_cnib`) — papelada; o que gera responsabilidade é registrar sobre bem
    indisponível. Agora ela pergunta à base local (`ri_schema.consultar_cnib`, a
    mesma da ficha da matrícula) e só aponta quando HÁ ordem.

    Pelo documento é CRITICO; só pelo nome é ATENCAO e diz que pode ser homônimo —
    homônimo é a regra, e quem decide é quem lê o documento.
    """
    from ri_schema import consultar_cnib
    saida = []
    bd = banco(con)
    for r in bd.ler(
            """SELECT a.id, a.numero, a.matricula_id, a.natureza_titulo,
                      a.lavrado_em AS dia, m.numero AS matricula
                 FROM ri_atos a LEFT JOIN ri_matriculas m ON m.id = a.matricula_id
                WHERE a.lavrado_em >= %s AND COALESCE(a.acervo,0) = 0
                  AND COALESCE(a.cancelado,0) = 0 AND a.tipo = 'R' ORDER BY a.id""",
            (IMPLANTACAO,)):
        partes = bd.ler("SELECT nome, documento_numero FROM ri_partes WHERE ato_id = %s "
                        "ORDER BY id", (r["id"],))
        if not partes:
            partes = bd.ler(
                """SELECT nome, documento_numero FROM ri_partes
                    WHERE matricula_id = %s AND COALESCE(proprietario_ativo,0) = 1
                    ORDER BY id""",
                (r["matricula_id"],))
        ordens = consultar_cnib(con, [p["documento_numero"] for p in partes
                                      if p["documento_numero"]],
                                [p["nome"] for p in partes if p["nome"]])
        if not ordens:
            continue
        por_doc = [o for o in ordens if o["criterio"] == "documento"]
        o = (por_doc or ordens)[0]
        saida.append(_achado(
            f"CNIB_ATO:{r['id']}", "REGISTRO_SEM_CNIB", "CRITICO" if por_doc else "ATENCAO",
            "RI_QUALIFICACAO",
            f"R-{r['numero']} da matrícula {r['matricula'] or r['matricula_id']}: ordem de "
            f"indisponibilidade no CNIB contra {o['nome']}",
            f"{len(ordens)} ordem(ns) ativa(s). A primeira: protocolo {o['protocolo_cnib']}, "
            f"{o['instituicao'] or ''} {o['processo'] or ''}, pedida em {_d(o['data_pedido'])}. "
            f"Bateu pelo {o['criterio']}"
            + ("." if por_doc else " — pode ser homônimo: conferir o documento da parte."),
            None, "Provimento CNJ 39/2014"))
    return saida


def regra_cnib_parado(con, hoje: date) -> list[dict]:
    """A base local do CNIB deixou de ser atualizada.

    Corrigido em 06/10/2026 («já temos a base atualizada»): media a data do PEDIDO
    da ordem mais nova, que não diz se a base foi atualizada — diz quando a última
    ordem foi pedida. O que diz é a última LEITURA que a Central respondeu
    (`ri_cnib_leituras`, situação OK ou VAZIA).
    """
    bd = banco(con)
    if not bd.tem_tabela("ri_cnib_leituras"):
        return []
    ultima = bd.valor(
        """SELECT max(terminada_em) FROM ri_cnib_leituras
            WHERE situacao IN ('OK', 'VAZIA')""")
    dia = _dia(ultima)
    if dia and (hoje - dia).days <= CNIB_DIAS_TOLERADOS:
        return []
    return [_achado(
        "CNIB:copia_parada", "CNIB_PARADO", "CRITICO", "TI",
        f"Base local do CNIB sem atualização desde {dia:%d/%m/%Y}" if dia
        else "Base local do CNIB nunca foi atualizada",
        "A conferência de ordem nos registros responde sobre uma base velha.",
        None, "Provimento CNJ 39/2014")]


# ------------------------------------------------------------- a casa

def regra_backup(con, hoje: date, pasta_dados: Path | None = None) -> list[dict]:
    if pasta_dados is None:
        return []
    # A PASTA DO BACKUP SAIU DE PERTO DO BANCO em 11/10/2026 (ordem do
    # oficial): procurar só em `<dados>/backups` acusaria «nenhum backup» na
    # manhã seguinte. Procura onde o sistema grava — `settings.backup_dir` — e,
    # por garantia, também na pasta antiga.
    import pasta_das_copias
    try:
        configurada = (banco(con).um("SELECT value FROM settings WHERE key='backup_dir'")
                       or {"value": ""})["value"] or ""
    except sqlite3.Error:
        configurada = ""
    pastas = {pasta_das_copias.pasta_de_backups(Path(pasta_dados), configurada),
              Path(pasta_dados) / "backups"}

    def dia_do_mais_novo(*padroes: str):
        achados = [p for pasta in pastas if pasta.is_dir()
                   for padrao in padroes for p in pasta.glob(padrao)]
        return (datetime.fromtimestamp(max(p.stat().st_mtime for p in achados)).date()
                if achados else None)

    # O FUNDAMENTO MUDOU DE NORMA, NÃO DE REGRA: o 213/2026 revogou o 74/2018
    # (art. 26). A cópia completa em periodicidade da classe é o art. 12,
    # § 3º, I; o alerta ao responsável quando o backup falha, o § 10.
    fundamento = "Provimento CN/CNJ 213/2026, art. 12, § 3º, I, e § 10"
    remedio = "Rodar FERRAMENTAS/BACKUP_AGORA.cmd, que também espelha fora do servidor."
    # AS DUAS COBRANÇAS (decisão do oficial em 26/10/2026, «completo uma vez
    # por semana»): o completo na SEMANA e o pacote do DIA. Até aqui a regra
    # cobrava só o completo, com a folga de um dia — e o sistema gera o
    # completo uma vez por semana, então acusava seis dias em sete. O pacote do
    # dia é o diário do banco ou um completo (que também leva o banco).
    completo = dia_do_mais_novo("backup_completo_*.zip")
    do_dia = dia_do_mais_novo("backup_banco_*.zip", "backup_completo_*.zip")
    if do_dia is None:
        return [_achado("BACKUP:completo", "BACKUP", "CRITICO", "TI",
                        "Nenhum backup encontrado", remedio, None, fundamento)]
    saida = []
    if completo is None or (hoje - completo).days > BACKUP_COMPLETO_DIAS_TOLERADOS:
        saida.append(_achado(
            "BACKUP:completo", "BACKUP", "CRITICO", "TI",
            f"Último backup completo é de {completo:%d/%m/%Y}" if completo
            else "Nenhum backup completo encontrado",
            f"O completo (banco, digitalizações e acervo) sai uma vez por semana; o "
            f"limite é {BACKUP_COMPLETO_DIAS_TOLERADOS} dias. " + remedio, None, fundamento))
    if (hoje - do_dia).days > BACKUP_DIAS_TOLERADOS:
        saida.append(_achado(
            "BACKUP:diario", "BACKUP", "CRITICO", "TI",
            f"Último backup do banco é de {do_dia:%d/%m/%Y}",
            "O pacote do banco sai todo dia (o processo BACKUP_DIARIO, às 18h). " + remedio,
            None, fundamento))
    return saida


#: abaixo disto o disco do servidor vira achado (em GB)
DISCO_CRITICO_GB = 5
DISCO_ATENCAO_GB = 20


def regra_disco(con, hoje: date, pasta_dados: Path | None = None) -> list[dict]:
    """O espaço livre no disco onde moram o banco e os backups.

    NASCEU DE UM DISCO CHEIO, em 06/10/2026 às 13h07: sobraram 24 MB livres
    num disco de 500 GB, e uma gravação do próprio gestor falhou com «no space
    left on device». Com o disco cheio o banco não grava ato e o backup não sai
    — e a regra do backup só acusaria a idade dele dias depois. O que ocupa a
    pasta de dados aparece no detalhe, do maior para o menor, para quem for
    liberar saber por onde começar; **a regra não apaga nada**.
    """
    import shutil
    if pasta_dados is None or not Path(pasta_dados).exists():
        return []
    livre_gb = shutil.disk_usage(str(pasta_dados)).free / 1024 ** 3
    if livre_gb >= DISCO_ATENCAO_GB:
        return []
    gravidade = "CRITICO" if livre_gb < DISCO_CRITICO_GB else "ATENCAO"
    copias = sorted(((q.stat().st_size, q.name) for q in Path(pasta_dados).iterdir()
                     if q.is_file() and (".bak" in q.name or "backup" in q.name.lower())),
                    reverse=True)[:6]
    detalhe = "; ".join(f"{nome} ({tam / 1024 ** 2:,.0f} MB)" for tam, nome in copias)
    # Espaço livre em disco não tem dispositivo próprio no 213/2026, que
    # revogou o 74/2018: cita-se a norma inteira, sem inventar artigo.
    return [_achado(
        "DISCO:dados", "DISCO", gravidade, "TI",
        f"Disco do servidor com {livre_gb:,.1f} GB livres".replace(",", "X").replace(".", ",").replace("X", "."),
        ("Cópias soltas na pasta de dados: " + detalhe + ". " if detalhe else "")
        + "Mover para fora do servidor o que já está no espelho de backup; "
          "com o disco cheio o banco não grava e o backup não sai.",
        None, "Provimento CN 213/2026 (que revogou o 74/2018)")]


def regra_pasta_do_banco(con, hoje: date, pasta_dados: Path | None = None) -> list[dict]:
    """Cópia, rascunho ou sobra ao lado do banco.

    NASCEU DO BANCO APAGADO, em 11/10/2026: a pasta tinha ~450 arquivos, 69
    deles cópias com o nome quase igual ao do banco, e na limpeza o verdadeiro
    foi junto. A ordem do oficial foi «backup e coisas nao importantes nao
    devem ficar na mesma pasta do banco de dados». O que pode ficar está em
    `pasta_das_copias.FICA_NA_PASTA_DO_BANCO`; **a regra não move nem apaga**.
    """
    import pasta_das_copias
    if pasta_dados is None:
        return []
    estranhos = pasta_das_copias.estranhos_na_pasta_do_banco(Path(pasta_dados))
    if not estranhos:
        return []
    nomes = ", ".join(p.name + ("\\" if p.is_dir() else "") for p in estranhos[:8])
    return [_achado(
        "PASTA_DO_BANCO:dados", "PASTA_DO_BANCO", "ATENCAO", "TI",
        f"{len(estranhos)} item(ns) que não são do sistema na pasta do banco",
        f"{nomes}{' …' if len(estranhos) > 8 else ''}. Mover para "
        f"{pasta_das_copias.raiz_das_copias(Path(pasta_dados))} — ali ficam as cópias e os "
        "rascunhos. Ao lado do banco, uma limpeza leva o banco junto.",
        None, "ordem do oficial, 11/10/2026")]


#: Usuários de teste que o oficial MANDOU MANTER — «deixa o usuario de teste»,
#: 06/10/2026. Ficam fora da cobrança; um usuário de teste novo continua sendo
#: cobrado, porque a decisão foi sobre este, e não sobre a regra.
TESTES_MANTIDOS_PELO_OFICIAL = frozenset({"teste"})


def regra_dado_de_teste(con, hoje: date) -> list[dict]:
    saida = []
    for r in banco(con).ler(
            """SELECT id, username FROM users
                WHERE active = 1 AND lower(username) IN ('teste','test') ORDER BY id"""):
        if r["username"].lower() in TESTES_MANTIDOS_PELO_OFICIAL:
            continue
        saida.append(_achado(
            f"TESTE:users:{r['id']}", "DADO_DE_TESTE", "ATENCAO", "TI",
            f"Usuário de teste «{r['username']}» ativo na produção",
            "Desativar: conta sem dono é acesso sem responsável.", None, "LGPD"))
    return saida


# ================================================================ CAMADA 2
# Cada ato lavrado desde o corte, um por um. Medido em 06/10/2026 contra a
# produção antes de virar regra: numeração e corrente de hash vieram LIMPAS
# (zero repetido, zero salto, zero quebra) — e por isso as regras ficam: zero
# medido hoje é o que torna visível o primeiro defeito amanhã.

def regra_numeracao_rcpn(con, hoje: date) -> list[dict]:
    """Número repetido entre assentos vivos, e salto na série desde o corte.

    O cancelado OCUPA o número (o termo existiu no livro) e por isso conta para
    o salto, mas não para a repetição — o 1981 de 06/10 é exatamente isso.
    """
    saida = []
    bd = banco(con)
    for r in bd.ler(
            """SELECT especie, numero, count(*) AS n FROM rc_assentos
                WHERE data_ato >= %s AND numero IS NOT NULL
                  AND COALESCE(situacao,'ATIVO') = 'ATIVO'
             GROUP BY especie, numero HAVING count(*) > 1
             ORDER BY especie, numero""", (IMPLANTACAO,)):
        saida.append(_achado(
            f"NUM_RCPN:rep:{r['especie']}:{r['numero']}", "NUMERACAO", "CRITICO",
            "RCPN", f"Termo nº {r['numero']} de {r['especie'].lower()} repetido "
            f"em {r['n']} assentos vivos", "Dois assentos vivos não podem ter o "
            "mesmo termo: conferir no livro qual vale e cancelar o outro.", None,
            "Lei 6.015/1973"))
    for linha_especie in bd.ler(
            "SELECT DISTINCT especie FROM rc_assentos WHERE data_ato >= %s ORDER BY especie",
            (IMPLANTACAO,)):
        especie = linha_especie["especie"]
        nums = sorted({r["numero"] for r in bd.ler(
            """SELECT numero FROM rc_assentos WHERE especie = %s AND numero IS NOT NULL
                  AND data_ato >= %s ORDER BY numero""", (especie, IMPLANTACAO))})
        faltam = sorted(set(range(nums[0], nums[-1] + 1)) - set(nums)) if nums else []
        if faltam:
            saida.append(_achado(
                f"NUM_RCPN:salto:{especie}:{faltam[0]}", "NUMERACAO", "ATENCAO",
                "RCPN", f"Salto na numeração de {especie.lower()}: "
                f"{', '.join(map(str, faltam[:10]))}",
                "Termo pulado tem de constar no livro como inutilizado.", None,
                "Lei 6.015/1973"))
    return saida


def regra_numeracao_ri(con, hoje: date) -> list[dict]:
    """Número de ato repetido na mesma matrícula, e a corrente de hash.

    A corrente existe para provar que nenhum ato foi inventado ou apagado: o
    `hash_anterior` de cada ato tem de ser o `hash_ato` do anterior.
    """
    saida = []
    bd = banco(con)
    tocadas = [r["matricula_id"] for r in bd.ler(
        """SELECT DISTINCT matricula_id FROM ri_atos
            WHERE lavrado_em >= %s AND COALESCE(acervo,0) = 0
            ORDER BY matricula_id""", (IMPLANTACAO,))]
    for mid in tocadas:
        atos = bd.ler(
            """SELECT id, tipo, numero, hash_ato, hash_anterior, lavrado_em,
                      COALESCE(acervo,0) AS acervo, COALESCE(cancelado,0) AS cancelado
                 FROM ri_atos WHERE matricula_id = %s ORDER BY numero, id""",
            (mid,))
        vistos: dict = {}
        for a in atos:
            if not a["cancelado"] and a["numero"] is not None:
                vistos.setdefault(a["numero"], []).append(f"{a['tipo']}-{a['numero']}")
        for numero, quem in vistos.items():
            if len(quem) > 1:
                saida.append(_achado(
                    f"NUM_RI:{mid}:{numero}", "NUMERACAO", "CRITICO", "RI_QUALIFICACAO",
                    f"Matrícula id {mid}: número {numero} usado por {', '.join(quem)}",
                    "R e AV correm na mesma sequência da matrícula.", None,
                    "Lei 6.015/1973, art. 232"))
        for ant, at in zip(atos, atos[1:]):
            if (str(at["lavrado_em"] or "")[:10] >= IMPLANTACAO and not at["acervo"]
                    and at["hash_anterior"] and ant["hash_ato"]
                    and at["hash_anterior"] != ant["hash_ato"]):
                saida.append(_achado(
                    f"CORRENTE_RI:{at['id']}", "CORRENTE_RI", "CRITICO", "TI",
                    f"Corrente de hash quebrada na matrícula id {mid}, "
                    f"{at['tipo']}-{at['numero']}",
                    "O ato não aponta para o hash do anterior: algum ato foi "
                    "alterado ou apagado por fora do sistema.", None, ""))
    return saida


def regra_ato_por_fora(con, hoje: date) -> list[dict]:
    """Ato do RI sem a auditoria de quem o lavrou — entrou por fora do sistema.

    É o defeito de 15/09/2026 (a importação inseria direto em `ri_atos`): ato
    sem `RI_ATO_LAVRADO` nunca passou pela rota que sela, cobra e audita.
    """
    saida = []
    for r in banco(con).ler(
            """SELECT a.id, a.tipo, a.numero, a.matricula_id, a.origem,
                      a.lavrado_em AS dia
                 FROM ri_atos a
                WHERE a.lavrado_em >= %s AND COALESCE(a.acervo,0) = 0
                  AND NOT EXISTS (SELECT 1 FROM audit_logs l
                                   WHERE l.action = 'RI_ATO_LAVRADO'
                                     AND l.entity_id = a.id)
                ORDER BY a.id""", (IMPLANTACAO,)):
        saida.append(_achado(
            f"POR_FORA:ri_atos:{r['id']}", "ATO_POR_FORA", "ATENCAO", "RI_QUALIFICACAO",
            f"{r['tipo']}-{r['numero']} (matrícula id {r['matricula_id']}) sem "
            "registro de quem lavrou", f"Lançado em {_d(r['dia'])}, origem "
            f"{r['origem']}. Conferir selo, custas e se é acervo marcado errado.",
            None, ""))
    return saida


def regra_registro_sem_prenotacao(con, hoje: date) -> list[dict]:
    """Registro (R) sem a prenotação amarrada — a prioridade não se prova."""
    saida = []
    for r in banco(con).ler(
            """SELECT a.id, a.numero, a.matricula_id, a.prenotacao,
                      a.lavrado_em AS dia FROM ri_atos a
                WHERE a.lavrado_em >= %s AND COALESCE(a.acervo,0) = 0
                  AND COALESCE(a.cancelado,0) = 0 AND a.tipo = 'R'
                  AND NOT EXISTS (SELECT 1 FROM ri_protocolos p WHERE p.ato_id = a.id)
                ORDER BY a.id""",
            (IMPLANTACAO,)):
        saida.append(_achado(
            f"SEM_PRENOT:{r['id']}", "REGISTRO_SEM_PRENOTACAO", "ATENCAO",
            "RI_QUALIFICACAO", f"R-{r['numero']} (matrícula id {r['matricula_id']}) "
            "sem prenotação amarrada", f"Lavrado em {_d(r['dia'])}; o campo diz "
            f"«{r['prenotacao'] or '—'}». Amarrar o protocolo ao ato.", None,
            "Lei 6.015/1973, art. 186"))
    return saida


#: (tabela do ato, coluna do selo, coluna da data)
_ATOS_COM_SELO = (
    ("rc_atos", "selo", "data_ato"), ("rc_certidoes", "selo", "emitida_em"),
    ("ri_atos", "selo_texto", "lavrado_em"), ("ri_certidoes", "selo_texto", "emitida_em"),
    ("rg_atos", "selo", "data_ato"), ("nt_atos", "selo", "data"),
    ("pt_atos", "selo", "data_ato"),
)


def regra_selo_orfao(con, hoje: date) -> list[dict]:
    """Selo no ato que o razão não conhece, e selo do razão sem o seu ato."""
    import re
    # A COLUNA PODE GUARDAR A ETIQUETA INTEIRA, e não só o código: medido em
    # 06/10/2026, a escritura 780 traz o texto de DOIS selos na mesma célula.
    # O que se confere são os códigos de 28 caracteres que estão lá dentro.
    codigo = re.compile(r"\b[A-Z]{6}\d{6}[A-Z0-9]{16}\b")
    saida = []
    bd = banco(con)
    for tabela, col, data in _ATOS_COM_SELO:
        for r in bd.ler(
                f"""SELECT a.id, a.{col} AS selo FROM {tabela} a
                     WHERE COALESCE(a.{col},'') <> '' AND a.{data} >= %s
                     ORDER BY a.id""",
                (IMPLANTACAO,)):
            achados = codigo.findall(str(r["selo"]).upper()) or [str(r["selo"]).strip()]
            fora = [c for c in achados if not bd.um(
                "SELECT 1 AS um FROM sd_selos WHERE numero = %s LIMIT 1", (c,))]
            if not fora:
                continue
            saida.append(_achado(
                f"SELO_ORFAO:ato:{tabela}:{r['id']}", "SELO_ORFAO", "ATENCAO",
                setor_da_tabela(tabela), f"{tabela} {r['id']}: selo "
                f"{', '.join(c[:40] for c in fora)} fora do razão dos selos",
                "Selo digitado à mão sem passar pela conferência: o sistema não "
                "sabe se é desta serventia nem se já foi usado.", None, ""))
    tabelas = [r["tabela"] for r in bd.ler(
        "SELECT DISTINCT tabela FROM sd_selos WHERE usado_em >= %s AND tabela IS NOT NULL "
        "ORDER BY tabela", (IMPLANTACAO,))]
    for tabela in tabelas:
        if not bd.tem_tabela(tabela):
            continue
        for r in bd.ler(
                f"""SELECT s.numero, s.ato_id FROM sd_selos s
                     WHERE s.tabela = %s AND s.usado_em >= %s AND s.cancelado_em IS NULL
                       AND NOT EXISTS (SELECT 1 FROM {tabela} a WHERE a.id = s.ato_id)
                     ORDER BY s.id""",
                (tabela, IMPLANTACAO)):
            saida.append(_achado(
                f"SELO_ORFAO:razao:{r['numero']}", "SELO_ORFAO", "ATENCAO",
                setor_da_tabela(tabela), f"Selo {r['numero']} aponta para "
                f"{tabela} {r['ato_id']}, que não existe", "Selo pago para ato "
                "que sumiu: cancelar no Portal do Selo ou religar ao ato.", None, ""))
    return saida


def _documento_invalido(doc, tipo: str = "") -> str | None:
    """'CPF'/'CNPJ' se o documento for desse tipo e o dígito não fechar."""
    from cpf_cnpj import cnpj_valido, cpf_valido
    so = "".join(ch for ch in str(doc or "") if ch.isdigit())
    tipo = (tipo or "").upper()
    if (tipo in ("", "CPF") and len(so) == 11) and not cpf_valido(so):
        return "CPF"
    if (tipo in ("", "CNPJ") and len(so) == 14) and not cnpj_valido(so):
        return "CNPJ"
    return None


def regra_documento_invalido(con, hoje: date) -> list[dict]:
    """CPF/CNPJ de parte de ato desde o corte cujo dígito não fecha."""
    fontes = (
        ("RI_QUALIFICACAO", """SELECT p.id, p.nome, p.documento_numero AS doc,
                 p.documento_tipo AS tipo FROM ri_partes p JOIN ri_atos a ON a.id = p.ato_id
                 WHERE a.lavrado_em >= %s AND COALESCE(a.acervo,0) = 0
                 ORDER BY p.id""", "ri_partes"),
        ("NOTAS_QUALIFICACAO", """SELECT p.id, p.nome, p.documento AS doc, '' AS tipo
                 FROM nt_ato_partes p JOIN nt_atos a ON a.id = p.ato_id
                 WHERE a.data >= %s ORDER BY p.id""", "nt_ato_partes"),
        ("RCPN", """SELECT p.id, p.nome, p.documento_numero AS doc,
                 p.documento_tipo AS tipo FROM rc_pessoas p
                 JOIN rc_assentos s ON s.id = p.assento_id
                 WHERE s.data_ato >= %s AND COALESCE(s.situacao,'ATIVO') = 'ATIVO'
                 ORDER BY p.id""",
         "rc_pessoas"),
    )
    saida = []
    for setor, sql, tabela in fontes:
        for r in banco(con).ler(sql, (IMPLANTACAO,)):
            qual = _documento_invalido(r["doc"], r["tipo"])
            if qual:
                saida.append(_achado(
                    f"DOC:{tabela}:{r['id']}", "DOCUMENTO_INVALIDO", "ATENCAO", setor,
                    f"{qual} inválido de {r['nome']}",
                    f"«{r['doc']}» não fecha o dígito verificador. Conferir no "
                    "documento original e corrigir antes de ir a Central.", None, ""))
    return saida


# ================================================================ CAMADA 4a
# O TEXTO DO ATO CONTRA O CADASTRO, POR REGRA — e não pela IA. Medido em
# 06/10/2026: a máscara que protege os dados antes de irem à IA troca nome por
# marca, e «JOSE» e «JOSÉ» viram marcas diferentes; ela não separaria acento de
# divergência. Nome, documento e número da matrícula se conferem AQUI, sem sair
# da serventia.
#
# SÓ NO REGISTRO (R), NA MINUTA DE R E NA ESCRITURA/PROCURAÇÃO. A medição
# mostrou que a averbação raramente repete os proprietários: em 40 atos, 23
# «documento ausente» — quase todos AV, e nenhum R. Regra que acusa toda
# averbação é alarme que ninguém ouve.

def _sem_marcas(t) -> str:
    import html as _h
    import re
    import unicodedata
    t = _h.unescape(re.sub(r"<[^>]+>", " ", str(t or "")))
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", t)).strip()


def _so_digitos_do_texto(t) -> str:
    import html as _h
    import re
    return re.sub(r"\D", "", _h.unescape(re.sub(r"<[^>]+>", " ", str(t or ""))))


def _conferir_texto(teor, partes, matricula=None) -> list[str]:
    import re
    texto, digitos = _sem_marcas(teor), _so_digitos_do_texto(teor)
    faltas = []
    for nome, doc in partes:
        if nome and _sem_marcas(nome) and _sem_marcas(nome) not in texto:
            faltas.append(f"o nome «{nome}» não aparece no texto")
        d = re.sub(r"\D", "", str(doc or ""))
        if len(d) in (11, 14) and d.strip("0") and d not in digitos:
            faltas.append(f"o documento de {nome or '?'} não aparece no texto")
    if matricula:
        m = re.sub(r"\D", "", str(matricula))
        if m and m not in digitos:
            faltas.append(f"o número da matrícula ({matricula}) não aparece no texto")
    return faltas


def regra_texto_contra_cadastro(con, hoje: date) -> list[dict]:
    casos = []
    bd = banco(con)
    for a in bd.ler(
            """SELECT a.id, a.numero, a.teor, m.numero AS mat FROM ri_atos a
                 JOIN ri_matriculas m ON m.id = a.matricula_id
                WHERE a.lavrado_em >= %s AND COALESCE(a.acervo,0) = 0 AND a.tipo = 'R'
                  AND COALESCE(a.cancelado,0) = 0 ORDER BY a.id""", (IMPLANTACAO,)):
        partes = [(q["nome"], q["documento_numero"]) for q in bd.ler(
            "SELECT nome, documento_numero FROM ri_partes WHERE ato_id = %s ORDER BY id",
            (a["id"],))]
        casos.append(("ri_atos", a["id"], f"R-{a['numero']}", a["teor"], partes, a["mat"],
                      "RI_QUALIFICACAO"))
    for a in bd.ler(
            """SELECT n.id, n.numero_pretendido, n.teor, m.numero AS mat FROM ri_minutas n
                 LEFT JOIN ri_matriculas m ON m.id = n.matricula_id
                WHERE n.situacao = 'A_REVISAR' AND n.tipo = 'R' ORDER BY n.id"""):
        partes = [(q["nome"], q["documento_numero"]) for q in bd.ler(
            "SELECT nome, documento_numero FROM ri_minuta_partes WHERE minuta_id = %s "
            "ORDER BY id", (a["id"],))]
        casos.append(("ri_minutas", a["id"], f"minuta R-{a['numero_pretendido'] or '?'}",
                      a["teor"], partes, a["mat"], "RI_QUALIFICACAO"))
    for a in bd.ler(
            """SELECT id, tipo, livro, folha, teor FROM nt_atos
                WHERE (data >= %s OR situacao = 'EM_LAVRATURA')
                  AND tipo IN ('ESCRITURA','PROCURACAO') ORDER BY id""", (IMPLANTACAO,)):
        partes = [(q["nome"], q["documento"]) for q in bd.ler(
            """SELECT nome, documento FROM nt_ato_partes
                WHERE ato_id = %s AND COALESCE(testemunha,0) = 0 ORDER BY id""", (a["id"],))]
        casos.append(("nt_atos", a["id"], f"{a['tipo'].lower()} {a['id']}", a["teor"],
                      partes, None, "NOTAS_QUALIFICACAO"))
    saida = []
    for tabela, i, rotulo, teor, partes, mat, setor in casos:
        if not _sem_marcas(teor):
            continue                      # sem texto ainda: nada a conferir
        faltas = _conferir_texto(teor, partes, mat)
        if faltas:
            saida.append(_achado(
                f"TEXTO:{tabela}:{i}", "TEXTO_CONTRA_CADASTRO", "ATENCAO", setor,
                f"{rotulo} ({tabela} {i}): o texto não bate com o cadastro",
                "; ".join(faltas[:6]) + ". Conferir no título: a divergência pode "
                "estar no texto ou no cadastro.", None, ""))
    return saida


def regra_minuta_em_ficha_encerrada(con, hoje: date) -> list[dict]:
    """Minuta esperando revisão numa ficha que já foi encerrada.

    Medido em 06/10/2026: as minutas 14 a 17 estão nas fichas 904020 e 904021,
    provisórias da importação assistida de 16/09, ENCERRADAS — os atos de
    verdade foram lavrados nas fichas 4020 e 4021. Lavrar a minuta ali seria
    lavrar em ficha fechada; o caminho é descartá-la com motivo (ou movê-la).
    """
    saida = []
    for r in banco(con).ler(
            """SELECT n.id, n.tipo, n.numero_pretendido, m.numero, m.origem
                 FROM ri_minutas n JOIN ri_matriculas m ON m.id = n.matricula_id
                WHERE n.situacao = 'A_REVISAR'
                  AND (COALESCE(m.encerrada,0) = 1 OR m.situacao = 'ENCERRADA')
                ORDER BY n.id"""):
        saida.append(_achado(
            f"MINUTA_FECHADA:{r['id']}", "MINUTA_EM_FICHA_ENCERRADA", "ATENCAO",
            "RI_QUALIFICACAO", f"Minuta {r['tipo']}-{r['numero_pretendido'] or '?'} "
            f"(ri_minutas {r['id']}) na ficha encerrada {r['numero']}",
            f"Ficha de origem {r['origem']}. Se o ato já foi lavrado noutra ficha, "
            "descartar a minuta com o motivo; se não, mover para a ficha certa.", None, ""))
    return saida


def regra_modelo_nao_preenchido(con, hoje: date) -> list[dict]:
    """Texto com marcador de modelo que não foi trocado pelo dado.

    NASCEU DE UMA MEDIÇÃO DE 06/10/2026: a IA achou numa minuta de averbação de
    indisponibilidade «{{ rotulo }} … {{ protocolo_frase }}» — e, relida minutos
    depois sem o texto ter mudado, NÃO achou mais. O grave e objetivo não pode
    depender da sorte da leitura: vira regra, que acha sempre.
    """
    import re
    # «[INSERIR …]» ENTROU EM 06/10/2026, achado pela revisão em lote: a
    # matrícula 4019 foi aberta com «[INSERIR APÓS APRESENTAÇÃO DO DOCUMENTO]»
    # no CCIR, no CIB e no CAR, e esta regra só conhecia {{ }}, {% %} e @campo.
    marcador = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|(?<![\w.])@[a-z][a-z0-9_]{3,}"
                          r"|\[\s*(?:INSERIR|PREENCHER|COMPLETAR)[^\]]*\]", re.I)
    fontes = (
        ("ri_minutas", "RI_QUALIFICACAO", "SELECT id, teor FROM ri_minutas WHERE situacao = 'A_REVISAR' ORDER BY id", ()),
        ("nt_atos", "NOTAS_QUALIFICACAO",
         "SELECT id, teor FROM nt_atos WHERE data >= %s OR situacao = 'EM_LAVRATURA' ORDER BY id", (IMPLANTACAO,)),
        ("ri_atos", "RI_QUALIFICACAO",
         "SELECT id, teor FROM ri_atos WHERE lavrado_em >= %s AND COALESCE(acervo,0) = 0 ORDER BY id", (IMPLANTACAO,)),
        ("rg_atos", "RCPJ_RTD_QUALIFICACAO", "SELECT id, teor FROM rg_atos WHERE data_ato >= %s ORDER BY id", (IMPLANTACAO,)),
        ("rc_atos", "RCPN", "SELECT id, teor FROM rc_atos WHERE data_ato >= %s ORDER BY id", (IMPLANTACAO,)),
        # O TEOR DA FICHA TAMBÉM: a abertura da matrícula escreve nele, e não em
        # `ri_atos` — foi onde o marcador da 4019 morava.
        ("ri_matriculas", "RI_QUALIFICACAO",
         """SELECT id, teor FROM ri_matriculas
             WHERE COALESCE(data_abertura, criado_em, '') >= %s ORDER BY id""", (IMPLANTACAO,)),
    )
    saida = []
    for tabela, setor, sql, args in fontes:
        for r in banco(con).ler(sql, args):
            achados = marcador.findall(str(r["teor"] or ""))
            if achados:
                saida.append(_achado(
                    f"MARCADOR:{tabela}:{r['id']}", "MODELO_NAO_PREENCHIDO", "CRITICO", setor,
                    f"{tabela} {r['id']}: texto com campo de modelo não preenchido",
                    "Marcadores no texto: " + ", ".join(sorted(set(achados))[:6])
                    + ". Lavrar assim põe o marcador no livro.", None, ""))
    return saida


def regra_leitura_do_texto(con, hoje: date) -> list[dict]:
    """O que a IA apontou na leitura do texto (camada 4b). Não fala com a rede:
    a leitura é feita antes, por `gestor_leitura.ler_pendentes`."""
    import gestor_leitura as GL
    return [_achado(
        a["chave"], "LEITURA_DO_TEXTO", "CRITICO" if a["grave"] else "ATENCAO",
        a["setor"], f"{a['rotulo']}: {a['o_que']}",
        (f"Trecho: «{a['trecho']}». " if a["trecho"] else "")
        + f"Apontado pela leitura automática ({a['provedor']}); conferir no título "
        "— a IA aponta, não decide.", None, "")
        for a in GL.achados_vigentes(con)]


# ================================================================ CAMADA 3
# O dinheiro. MEDIDO EM 06/10/2026: a cobrança ato por ato não serve de régua
# — a casa cobra por lançamento manual, e ~250 atos desde o corte não têm
# lançamento amarrado e estão cobrados. Também a comparação DIÁRIA selo × caixa
# não serve: o RI recebe por depósito em dia diferente do ato (um dia com R$ 12
# mil em selos e R$ 660 no caixa, outro com R$ 48 mil no caixa). O que se
# sustenta é o MÊS, e mesmo ele hoje não fecha — por isso ele vira achado.

def _brl(v: float) -> str:
    """1234.5 -> '1.234,50' — o dinheiro como o balcão o lê."""
    return f"{v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _reais(v) -> float:
    if v in (None, ""):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).replace(".", "").replace(",", "."))


def _pessoa_do_operador(con, nome: str | None) -> str:
    """O caixa é de uma pessoa, e a cobrança do caixa aberto vai para ELA.

    `cx_caixas` guarda o nome (o `operador_id` vem vazio); casa com o cadastro
    pelo nome inteiro ou pelo começo dele — «Carla» e «Carla Exemplo
    Jardim» são a mesma pessoa. Sem casamento único, vai para a Gestão.
    """
    import unicodedata

    def forma(t):
        t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode()
        return " ".join(t.upper().split())
    # A COMPARAÇÃO É EM PYTHON: o `upper()` do SQLite é ASCII e deixa o «ú» de
    # «Araújo» minúsculo — a primeira versão mandou o caixa da Beatriz para a
    # Gestão (medido em 06/10/2026, 14h10).
    n = forma(nome)
    if not n:
        return "GESTAO"
    achados = [r["id"] for r in banco(con).ler(
        "SELECT id, full_name FROM users WHERE active = 1 ORDER BY id")
               if forma(r["full_name"]).startswith(n)]
    return f"PESSOA:{achados[0]}" if len(achados) == 1 else "GESTAO"


def _relogio() -> datetime:
    """A hora de agora — num lugar só, para o teste poder trocá-la."""
    return datetime.now()


def regra_caixa_do_dia(con, hoje: date) -> list[dict]:
    """O caixa DE HOJE ainda aberto depois do fim do expediente.

    «expediente termina 14h, funcionarios vao embora 14h15. avisas 14h pra
    fechar o caixa» — o oficial, 06/10/2026. Por isso a conferência roda
    também às 14h: a tarefa crítica vai para quem está com o caixa, e aparece
    na janela de avisos da casa. **Só vale para hoje** — conferência de outro
    dia não sabe que horas eram.
    """
    import caixa_aviso as CA
    if hoje != date.today():
        return []
    linha = banco(con).um("SELECT value FROM settings WHERE key = %s",
                          (CA.CHAVE_FIM,))
    hora, minuto = CA.fim_do_expediente(linha["value"] if linha else None)
    agora = _relogio()
    if (agora.hour, agora.minute) < (hora, minuto):
        return []
    saida = []
    for r in banco(con).ler(
            """SELECT id, operador_nome FROM cx_caixas
                WHERE data = %s AND situacao = 'ABERTO' AND fechado_em IS NULL
                ORDER BY id""",
            (hoje.isoformat(),)):
        saida.append(_achado(
            f"CAIXA_HOJE:{r['id']}", "CAIXA_DO_DIA_ABERTO", "CRITICO",
            _pessoa_do_operador(con, r["operador_nome"]),
            f"O expediente acabou às {hora:02d}:{minuto:02d} e o caixa de hoje "
            f"({r['operador_nome']}) está aberto",
            "Conte o dinheiro e feche o caixa antes de sair. Caixa que fica aberto "
            "de um dia para o outro mistura o dinheiro de dois dias.", hoje, ""))
    return saida


def regra_caixa(con, hoje: date) -> list[dict]:
    """Caixa fechado sem conferência, diferença sem explicação, caixa esquecido.

    Conferir é ato do oficial (a casa recusa quem confere o próprio caixa), e
    por isso vai para a Gestão.
    """
    import gestor_caixa
    saida = []
    for r in banco(con).ler(
            """SELECT id, data, operador_nome, diferenca, justificativa, fechado_em,
                      conferido_por, situacao, saldo_inicial, valor_esperado,
                      valor_contado FROM cx_caixas
                WHERE aberto_em >= %s ORDER BY id""", (IMPLANTACAO,)):
        dia = _dia(r["data"])
        if r["fechado_em"] and not r["conferido_por"] and dia and (hoje - dia).days >= 1:
            # O AGENTE REFAZ A CONTA (06/10/2026): o caixa que fecha vai para o
            # visto do oficial; o que tem ponto diz qual — e a pergunta vai a
            # quem contou, com o oficial vendo.
            pontos = gestor_caixa.parecer(con, r)
            if pontos:
                saida.append(_achado(
                    f"CAIXA_CONF:{r['id']}", "CAIXA_COM_PONTOS", "ATENCAO", "GESTAO",
                    f"Caixa de {dia:%d/%m} ({r['operador_nome']}): "
                    + "; ".join(pontos), "Perguntar a quem contou e conferir.", None, ""))
            else:
                saida.append(_achado(
                    f"CAIXA_CONF:{r['id']}", "CAIXA_PRONTO_PARA_VISTO", "ATENCAO", "GESTAO",
                    f"Caixa de {dia:%d/%m} ({r['operador_nome']}) fecha — falta o seu visto",
                    "O agente refez a conta: esperado, contado e lançamentos batem.",
                    None, ""))
        if abs(_reais(r["diferenca"])) >= 0.01 and not (r["justificativa"] or "").strip():
            saida.append(_achado(
                f"CAIXA_DIF:{r['id']}", "CAIXA_DIFERENCA", "VENCIDO", "GESTAO",
                f"Caixa de {r['data']} ({r['operador_nome']}): diferença de "
                f"R$ {r['diferenca']} sem justificativa", "", dia, ""))
        if not r["fechado_em"] and (r["situacao"] or "").upper() == "ABERTO" \
                and dia and dia < hoje:
            # O CAIXA ESQUECIDO É COBRADO DE QUEM O ABRIU (06/10/2026): até
            # aqui ia para a Gestão, e quem tinha de contar o dinheiro não via.
            saida.append(_achado(
                f"CAIXA_ABERTO:{r['id']}", "CAIXA_ABERTO", "CRITICO",
                _pessoa_do_operador(con, r["operador_nome"]),
                f"Caixa de {dia:%d/%m} ({r['operador_nome']}) ainda aberto",
                "Caixa aberto de um dia para o outro mistura o dinheiro de dois "
                "dias no fechamento.", dia, ""))
    return saida


_GRUPO_DO_SELO = {"IMOVEL": "RI", "RI": "RI", "LIVRO3": "RI", "RCPN": "RCPN",
                  "CIVIL": "RCPN", "NOTAS": "Notas", "RCPJ": "RTD/PJ",
                  "RCPJ_RTD": "RTD/PJ", "RTDPJ": "RTD/PJ", "PROTESTO": "Protesto"}


def regra_protesto(con, hoje: date) -> list[dict]:
    """O Protesto — regularidade dos atos, prazos, intimações, protestos devidos
    e indevidos. As regras moram com o agente do Protesto (`gestor_protesto`,
    09/10/2026), que lê o banco E os arquivos da CRA: o protesto desta casa
    ainda é praticado no E-Ofício, e o rastro do dia está na pasta da CRA."""
    import gestor_protesto
    return gestor_protesto.conferir(con, hoje)


def regra_onr_cargas(con, hoje: date) -> list[dict]:
    """As três cargas do RI ao ONR — imagens, Indicador Pessoal e Indicador Real.
    As regras moram com o agente que faz as cargas (`gestor_cargas_ri`): quem
    entrega é quem sabe o que ficou por entregar."""
    import gestor_cargas_ri
    return gestor_cargas_ri.conferir(con, hoje)


def regra_rcpn_cargas(con, hoje: date) -> list[dict]:
    """As cinco cargas do RCPN — SIRC, CRC, FUNAI, óbitos do mês e IBGE — no
    que o agente de cargas preparou e ainda não subiu. As regras moram com ele
    (`gestor_cargas_rcpn`), como as do RI moram com o agente do ONR."""
    import gestor_cargas_rcpn
    return gestor_cargas_rcpn.conferir(con, hoje)


def regra_rcpn(con, hoje: date) -> list[dict]:
    """O ato e o balcão do RCPN — duplicidade, assento sem número ou sem termo,
    dado obrigatório, anotações do art. 367, habilitações, retificações,
    pedidos da Central e folha de segurança. As regras moram com o agente do
    RCPN (`gestor_rcpn`, 09/10/2026); as Centrais ficam com o de cargas."""
    import gestor_rcpn
    return gestor_rcpn.conferir(con, hoje)


def regra_agente_notas(con, hoje: date) -> list[dict]:
    """O Tabelionato de Notas — livro, CENSEC por ato, anotação à margem,
    escritura de imóvel, minutas e rascunhos. As regras moram com o agente das
    Notas (`agente_notas`, 09/10/2026), cada uma com o artigo ao lado."""
    import agente_notas
    return agente_notas.conferir(con, hoje)


def regra_rtdpj(con, hoje: date) -> list[dict]:
    """O RTD e o RCPJ — títulos parados ou atendidos sem conclusão, o selo da
    etiqueta, a Central ONRTDPJ, os livros e o protocolo sem pagamento. As
    regras moram com o agente do RTD/PJ (`gestor_rtdpj`, 09/10/2026)."""
    import gestor_rtdpj
    return gestor_rtdpj.conferir(con, hoje)


def regra_fiscal(con, hoje: date) -> list[dict]:
    """O agente financeiro e das gratuidades — os selos do sistema contra o
    Portal do Selo do TJMA e contra o saldo do selador. As regras moram com ele
    (`gestor_fiscal`, 09/10/2026); a consulta ao portal roda antes, na rodada."""
    import gestor_fiscal
    return gestor_fiscal.conferir(con, hoje)


def regra_pld(con, hoje: date) -> list[dict]:
    """PLD/COAF — o caso selecionado que espera análise ou comunicação (23/10/2026).

    A seleção roda logo antes, na rodada (`pld_coaf.selecionar`); aqui só se lê.
    O prazo é o do art. 151 do CNN: 30 dias da operação para a comunicação que
    independe de análise, 60 para a análise. Vencido ou dentro da janela, vira
    achado; longe, não — alarme que soa sempre é alarme que ninguém ouve.

    SIGILO (CNN, art. 154): o achado vai ao setor do oficial e diz o NÚMERO do
    caso e a hipótese, nunca o nome de quem está no ato. Quem quiser saber mais
    abre a tela do PLD, que é só do ADMIN.
    """
    import pld_coaf as PLD
    bd = banco(con)
    if not bd.tem_tabela("pld_casos"):
        return []
    saida = []
    for c in bd.ler(
            """SELECT id, atribuicao, hipotese, especie, fundamento, data_operacao,
                      situacao FROM pld_casos
                WHERE situacao IN ('A_ANALISAR', 'A_COMUNICAR') ORDER BY id"""):
        dia = _dia(c["data_operacao"])
        if dia is None or antes_do_corte(dia):
            continue
        dias = (PLD.DIAS_PARA_SELECIONAR if c["especie"] == PLD.AUTOMATICA
                else PLD.DIAS_PARA_ANALISAR)
        prazo = dia + timedelta(days=dias)
        gravidade = _situacao_do_prazo(prazo, hoje)
        if gravidade is None:
            continue
        o_que = ("comunicar ao COAF" if c["situacao"] == "A_COMUNICAR"
                 else "analisar e decidir")
        saida.append(_achado(
            f"PLD:{c['id']}", "PLD_COAF", gravidade, "GESTAO",
            f"PLD/COAF: caso nº {c['id']} ({c['atribuicao']}) para {o_que}",
            f"Hipótese {c['hipotese']}, operação de {dia:%d/%m/%Y}. Abra "
            "Administrativo → PLD/COAF: a análise se registra com fundamentação, "
            "comunique-se ou não (CNN, art. 141, § 3º).",
            prazo, c["fundamento"]))
    return saida


def regra_fechamento_do_mes(con, hoje: date) -> list[dict]:
    """Selos usados no mês × entradas do caixa no mês, por atribuição.

    O selo declara o valor do ato (Total R$); o isento e o diferido saem da
    conta pela marca. Não é acusação: é a pergunta que a correição faz, com os
    números ao lado. Abaixo de R$ 50 e de 5% não se levanta.
    """
    import selo as SL
    saida = []
    for ano, mes in _meses(IMPLANTACAO[:7], hoje):
        comp = f"{ano:04d}-{mes:02d}"
        selos: dict[str, float] = {}
        for sel in banco(con).ler(
                """SELECT texto, atribuicao FROM sd_selos
                    WHERE usado_em ILIKE %s AND usado_em >= %s
                      AND cancelado_em IS NULL ORDER BY id""", (comp + "%", IMPLANTACAO)):
            texto, atr = sel["texto"], sel["atribuicao"]
            lido = SL.ler_texto(texto or "")
            marcas = " ".join(lido.get("marcas") or []).upper()
            if "ISENT" in marcas or "DIFERID" in marcas or lido.get("total") is None:
                continue
            g = _GRUPO_DO_SELO.get(atr or "", atr or "?")
            selos[g] = selos.get(g, 0.0) + lido["total"]
        caixa = 0.0
        sem_protocolo = 0
        for lanc in banco(con).ler(
                """SELECT valor, sentido, protocolo_id FROM cx_lancamentos
                    WHERE data ILIKE %s AND data >= %s
                      AND COALESCE(estornado,0) = 0 AND COALESCE(excluido,0) = 0
                    ORDER BY id""",
                (comp + "%", IMPLANTACAO)):
            v, sentido, prot = lanc["valor"], lanc["sentido"], lanc["protocolo_id"]
            caixa += _reais(v) * (1 if (sentido or "ENTRADA") == "ENTRADA" else -1)
            sem_protocolo += prot is None
        total_selos = sum(selos.values())
        dif = caixa - total_selos
        if abs(dif) < 50 or abs(dif) < 0.05 * max(total_selos, caixa, 1):
            continue
        fechado = (ano, mes) < (hoje.year, hoje.month)
        abertura = ", ".join(f"{g} R$ {_brl(v)}" for g, v in sorted(selos.items()))
        saida.append(_achado(
            f"FECHAMENTO:{comp}", "FECHAMENTO_DO_MES",
            "ATENCAO", "GESTAO",
            f"{mes:02d}/{ano}{'' if fechado else ' (parcial)'}: selos declaram "
            f"R$ {_brl(total_selos)} e o caixa registra R$ {_brl(caixa)}",
            f"Diferença R$ {_brl(dif)}. Selos por atribuição: {abertura}. "
            f"{sem_protocolo} lançamento(s) do caixa sem protocolo, que não dizem "
            "de que atribuição são. Pode ser gratuidade sem a marca no selo, ou "
            "dinheiro recebido por outro caminho — conferir.", None, ""))
    return saida


#: A ordem é a de aperto: primeiro o que já venceu na lei, por último a casa.
REGRAS: tuple[tuple[str, Callable], ...] = (
    ("SIRC", regra_sirc),
    ("SIRC_CANCELAMENTO", regra_sirc_cancelamentos),
    ("FUNAI", regra_funai),
    ("CRC", regra_crc),
    ("OBITO_MENSAL", regra_obitos_do_mes),
    ("IBGE", regra_ibge),
    ("CENSEC", regra_censec),
    ("CENSEC_AUTOMATICO", regra_censec_automatico),
    ("DOI", regra_doi),
    ("ATO_SEM_SELO", regra_atos_sem_selo),
    ("SELO_CANCELADO_LOCAL", regra_selo_cancelado_so_no_sistema),
    ("PRENOTACAO_VENCIDA", regra_prenotacao_vencida),
    ("PRENOTACAO_A_VENCER", regra_prenotacao_a_vencer),
    ("DIGITALIZACAO_DA_FICHA", regra_digitalizacao_da_ficha),
    ("REVISAO_DO_AGENTE", regra_revisao_do_agente),
    ("REGISTRO_SEM_CNIB", regra_registro_sem_cnib),
    ("CNIB_PARADO", regra_cnib_parado),
    ("BACKUP", regra_backup),
    ("CAIXA_DO_DIA_ABERTO", regra_caixa_do_dia),
    ("DISCO", regra_disco),
    ("PASTA_DO_BANCO", regra_pasta_do_banco),
    ("DADO_DE_TESTE", regra_dado_de_teste),
    # camada 2 — cada ato
    ("NUMERACAO_RCPN", regra_numeracao_rcpn),
    ("NUMERACAO_RI", regra_numeracao_ri),
    ("ATO_POR_FORA", regra_ato_por_fora),
    ("REGISTRO_SEM_PRENOTACAO", regra_registro_sem_prenotacao),
    ("SELO_ORFAO", regra_selo_orfao),
    ("DOCUMENTO_INVALIDO", regra_documento_invalido),
    # camada 4a — o texto contra o cadastro, por regra
    ("TEXTO_CONTRA_CADASTRO", regra_texto_contra_cadastro),
    ("MODELO_NAO_PREENCHIDO", regra_modelo_nao_preenchido),
    ("MINUTA_EM_FICHA_ENCERRADA", regra_minuta_em_ficha_encerrada),
    ("LEITURA_DO_TEXTO", regra_leitura_do_texto),
    # camada 3 — o dinheiro
    ("CAIXA", regra_caixa),
    ("FECHAMENTO_DO_MES", regra_fechamento_do_mes),
    # o agente de cargas do RI (09/10/2026)
    ("ONR_CARGAS", regra_onr_cargas),
    # o agente de cargas do RCPN (09/10/2026)
    ("CARGAS_RCPN", regra_rcpn_cargas),
    # o agente do RCPN — o ato e o balcão (09/10/2026)
    ("RCPN_AGENTE", regra_rcpn),
    # o agente das Notas (09/10/2026)
    ("NOTAS_AGENTE", regra_agente_notas),
    # o agente do RTD/PJ (09/10/2026)
    ("RTDPJ", regra_rtdpj),
    # o agente do Protesto (09/10/2026)
    ("PROTESTO", regra_protesto),
    # o agente financeiro e das gratuidades (09/10/2026)
    ("FISCAL", regra_fiscal),
    # o PLD/COAF — o caso que espera análise ou comunicação (23/10/2026)
    ("PLD_COAF", regra_pld),
)


# --------------------------------------------- só o essencial nos atos já lavrados
#
# ORDEM DO OFICIAL, 06/10/2026: «reduza a quantidade de erros para corrigir.
# deixe apenas os fundamentais e atos efetivamente lavrados e selados. o que não
# for essencial e muito importante, tire e segue a vida» — e, logo depois: «isso
# para os atos já lavrados, os que estão para revisão, segue normal».
#
# O CORTE É SÓ SOBRE O ATO JÁ LAVRADO. Minuta, rascunho e escritura em
# lavratura continuam com tudo (ali o conserto é de graça: ainda não foi ao
# livro). Caixa, comunicações às Centrais, prazos e TI não são «erro em ato» e
# não passam por aqui.
#
# Medido em 06/10/2026 na produção, antes do corte: 21 apontamentos da revisão
# em lote em atos lavrados, dos quais 5 GRAVES em ato selado; 6 selos cancelados
# a confirmar no portal; 4 registros sem prenotação amarrada; 2 atos por fora;
# 2 selos fora do razão.

#: Saem de vez: dizem respeito a ato lavrado e não são defeito do ato.
RETIRADAS_DO_ATO_LAVRADO = frozenset({
    "ATO_POR_FORA",             # quem lavrou não ficou na auditoria (importação)
    "REGISTRO_SEM_PRENOTACAO",  # amarração de arquivo, não defeito do registro
    "SELO_ORFAO",               # conciliação do razão de selos
    "SELO_CANCELADO_LOCAL",     # conferência no Portal do Selo
    # «não existe ato lavrado sem selo, ato é lavrado apenas com a emissão do selo»
    # (o oficial, 06/10/2026). Medido no mesmo dia: dos 7 apontados, 5 eram acervo
    # transcrito (2000, 2002, 2011, E-Ofício, importação) e 2 lançamentos à mão.
    "ATO_SEM_SELO",
})
#: Em ato lavrado, ficam só se o ato estiver SELADO; nas duas primeiras, só o GRAVE.
SO_GRAVE_E_SELADO = frozenset({"REVISAO_DO_AGENTE", "LEITURA_DO_TEXTO"})
SO_SELADO = frozenset({"TEXTO_CONTRA_CADASTRO", "MODELO_NAO_PREENCHIDO",
                       "REGISTRO_SEM_CNIB"})
#: Onde cada tabela de ato guarda o selo, além do razão (`sd_selos`).
_COLUNA_DO_SELO = {"ri_atos": "selo_texto", "nt_atos": "selo", "rc_atos": "selo"}


def _coluna_existe(con, tabela: str, coluna: str) -> bool:
    return banco(con).tem_coluna(tabela, coluna)


def _lavrado(con, tabela: str, ato_id) -> bool:
    """Minuta e escritura em lavratura NÃO são ato lavrado; o resto das tabelas
    de ato só guarda ato lavrado."""
    if tabela in ("ri_minutas", "ri_rascunhos"):
        return False
    if tabela == "nt_atos":
        r = banco(con).um("SELECT situacao FROM nt_atos WHERE id = %s", (ato_id,))
        return bool(r) and (r["situacao"] or "").upper() == "LAVRADO"
    return tabela in ("ri_atos", "rc_atos", "ra_atos", "rg_atos", "pt_atos")


def _selado(con, tabela: str, ato_id) -> bool:
    """A chave do selo é tabela + ato_id — por ato_id sozinho vêm selos de outra
    atribuição."""
    bd = banco(con)
    if bd.tem_tabela("sd_selos"):
        if bd.um("""SELECT 1 AS um FROM sd_selos WHERE tabela = %s AND ato_id = %s
                       AND cancelado_em IS NULL LIMIT 1""", (tabela, ato_id)):
            return True
    col = _COLUNA_DO_SELO.get(tabela)
    if col and _coluna_existe(con, tabela, col):
        r = bd.um(f"SELECT {col} AS selo FROM {tabela} WHERE id = %s", (ato_id,))
        return bool(r and (r["selo"] or "").strip())
    return False


def _ato_da_revisao(con, rid) -> tuple[str, int] | None:
    """(tabela, id) do ato que a revisão em lote leu. No RI o alvo é a
    MATRÍCULA, e o ato sai do rótulo («AV-6 da matrícula 3110»)."""
    import re as _re
    bd = banco(con)
    if not bd.tem_tabela("rv_revisoes"):
        return None
    r = bd.um("SELECT atribuicao, alvo_id, rotulo FROM rv_revisoes WHERE id = %s",
              (rid,))
    if not r:
        return None
    atribuicao, alvo, rotulo = r["atribuicao"], r["alvo_id"], r["rotulo"] or ""
    if atribuicao == "NOTAS":
        return "nt_atos", alvo
    if atribuicao == "RI":
        m = _re.match(r"\s*(R|AV)-(\d+)", rotulo)
        if not m:
            return None
        a = bd.um("SELECT id FROM ri_atos WHERE matricula_id=%s AND tipo=%s AND numero=%s "
                  "ORDER BY id LIMIT 1", (alvo, m.group(1), int(m.group(2))))
        return ("ri_atos", a["id"]) if a else None
    if atribuicao == "LIVRO3":
        return "ra_atos", alvo
    return None


def _ato_do_achado(con, a: dict) -> tuple[str, int] | None:
    partes = (a["chave"] or "").split(":")
    if a["regra"] == "REVISAO_DO_AGENTE" and len(partes) >= 2 and partes[1].isdigit():
        return _ato_da_revisao(con, int(partes[1]))
    if a["regra"] == "REGISTRO_SEM_CNIB" and len(partes) >= 2 and partes[1].isdigit():
        return "ri_atos", int(partes[1])
    if len(partes) >= 3 and partes[2].isdigit():   # TEXTO:/MARCADOR:/LEITURA:tabela:id
        return partes[1], int(partes[2])
    return None


def so_o_essencial(con: sqlite3.Connection, achados: list[dict]) -> list[dict]:
    """Tira dos atos já lavrados o que não é fundamental. O que é sobre ato em
    revisão (minuta, rascunho, em lavratura) passa inteiro."""
    saida = []
    for a in achados:
        regra = a["regra"]
        if regra in RETIRADAS_DO_ATO_LAVRADO:
            continue
        if regra in SO_GRAVE_E_SELADO or regra in SO_SELADO:
            ato = _ato_do_achado(con, a)
            # Revisão em lote só existe sobre ato lavrado; nas outras, decide a tabela.
            lavrado = (regra == "REVISAO_DO_AGENTE") or (ato is not None and _lavrado(con, *ato))
            if lavrado:
                if regra in SO_GRAVE_E_SELADO and a["gravidade"] != "CRITICO":
                    continue
                if ato is None or not _selado(con, *ato):
                    continue
        saida.append(a)
    return saida


def conferir(con: sqlite3.Connection, hoje: date, *,
             pasta_dados: Path | None = None) -> list[dict]:
    """Roda todas as regras. Só lê. A regra que quebra vira achado NAO_MEDIU.

    A única escrita é estrutural: as tabelas `ge_*` nascem aqui se faltarem.
    Num banco onde o gestor nunca rodou, `ge_envios` não existe — e a regra
    tem de entender isso como «nada registrado», e não quebrar.
    """
    from gestor_schema import init_gestor_schema
    init_gestor_schema(con)
    achados: list[dict] = []
    for nome, regra in REGRAS:
        try:
            if regra in (regra_backup, regra_disco, regra_pasta_do_banco):
                achados.extend(regra(con, hoje, pasta_dados))
            else:
                achados.extend(regra(con, hoje))
        except Exception as erro:            # noqa: BLE001 — o erro vai à fila
            achados.append(_achado(
                f"NAO_MEDIU:{nome}", nome, "NAO_MEDIU", "TI",
                f"A conferência «{nome}» não conseguiu medir",
                f"{type(erro).__name__}: {erro}", None, ""))
    return so_o_essencial(con, achados)
