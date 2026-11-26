"""AS CADEIAS AUTOMÁTICAS — o aviso na tela quando uma delas para.

    «cuidar da questão do CNIB. [...] esse também roda automaticamente no
     sistema, baixa as ordens e gera as minutas de averbação. Se, por um
     acaso, a rotina parar, deve criar um aviso no sistema para o gestor e
     admin cuidarem disso, mas se estiver funcionando, não precisa de rotina
     manual. Portanto, retirar do checklist do dia e garantir que problemas
     sejam avisados à TI, ao gestor e ao admin.» — o oficial, 26/11/2026 (A006)

    «Conferir a carga da CENSEC da madrugada também entra na mesma lógica»
     — o oficial, no mesmo dia

    E «Conferir o Constrijud» (ROT-RI-04), na mesma lógica: a automação
    verifica e só avisa quando a rotina para (A008, no mesmo dia).

O QUE É UMA CADEIA
    Uma rotina que o sistema faz sozinho, de ponta a ponta, e que antes alguém
    conferia à mão todo dia. Cada cadeia é uma lista de ELOS; cada elo diz se
    está funcionando. Se todos estão, ninguém recebe nada. Se um para, a faixa
    do alto da tela (`templates/_cadeias_aviso.html`) diz QUAL elo parou,
    DESDE QUANDO e ONDE olhar, com um clique. Quando o elo volta a funcionar, a
    faixa some sozinha: ela é calculada a cada tela, e não gravada.

    CNIB    a leitura diária da Central (ou a rodada da fila), a base local com
            ordem nova, o processo «CNIB — ordens sem decisão» da central de
            automação, a rotina das minutas e a minuta da averbação devida.
    CENSEC  o envio da madrugada (02:00) e a conferência da situação (07:40).
            O que a API da CENSEC não faz (fechar a quinzena, ver a validação
            no portal) continua como achado do gestor (`CENSEC_AUTOMATICO`).
    CONSTRIJUD  a leitura do e-Protocolo do ONR (por onde as ordens do
            Constrijud chegam, desde 25/05/2026), a conferência do Constrijud
            (`RI_CONSTRIJUD`: leitura boa nas últimas 2 horas, CNN 320-AB) e a
            contagem da Penhora Online no WSOfício, que o ONR mantém na
            transição. Ordem de constrição esperando prenotação é TRABALHO do
            escrevente do RI (tarefa), e não rotina parada.

QUEM VÊ
    A TI, o gestor (MANAGER) e o administrador (`QUEM_VE`). O escrevente não:
    não é ele quem conserta rotina parada.

A GRAVIDADE: LARANJA NO PRIMEIRO DIA, VERMELHA DEPOIS
    A mesma régua da faixa do comprovante da gratuidade. No dia em que o elo
    parou, a faixa é laranja; a partir do dia seguinte (`DIAS_PARA_FICAR_
    VERMELHO`), vermelha. O elo sem data conhecida fica laranja.

O QUE FAZ FALTA MEDIR, E ONDE SE MEDE
    O elo que esta casa já media fica onde estava, e aqui só se lê:
    - a leitura vazia e a base parada são as réguas de `gestor_conferencia`
      (`CNIB_DIAS_TOLERADOS`, `CNIB_DIAS_DE_LEITURA_VAZIA`), usadas daqui, e
      não copiadas;
    - o processo que não rodou ou deu erro vem de `au_processos` e
      `au_execucoes`, com a agenda de `automacao`;
    - a ordem devida sem minuta vem do `estado` do processo `RI_CNIB`, que a
      grava a cada rodada (`automacao_processos.verificar_cnib`): contá-la
      aqui custaria a busca da CNIB matrícula por matrícula a cada tela.

A BASE ATRASADA COM A FILA ANDANDO NÃO É ROTINA PARADA
    Com a leitura da fila ligada, a fila entrega primeiro as ordens antigas, e
    a ordem mais nova da base só sobe quando ela chegar às novas. Enquanto a
    rodada recente da fila leu ordens, a cadeia está funcionando, e esta faixa
    não acusa. A regra do gestor (`CNIB_PARADO`) continua medindo a base e
    contando no semáforo: o «nada consta» da cópia local ainda não vale.

SÓ LÊ. Nada aqui grava, liga ou desliga processo.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable

from bd_nativo import banco

#: Quem vê a faixa.
QUEM_VE = ("ADMIN", "MANAGER", "TI")
#: A partir de quantos dias parado o elo deixa a faixa vermelha.
DIAS_PARA_FICAR_VERMELHO = 1
#: Quanto depois do horário da agenda o processo que não começou conta como
#: «não rodou». O despachante bate a cada minuto; duas horas cobrem a fila de
#: processos da manhã e a máquina que demorou a ligar.
ATRASO_TOLERADO = timedelta(hours=2)

#: As situações de rodada que querem dizer «não funcionou».
_FALHAS = ("ERRO", "TEMPO_ESGOTADO", "INTERROMPIDA")

CNIB, CENSEC, CONSTRIJUD = "CNIB", "CENSEC", "CONSTRIJUD"
ROTULO_DA_CADEIA = {CNIB: "CNIB (indisponibilidade de bens)",
                    CENSEC: "Carga da CENSEC da madrugada",
                    CONSTRIJUD: "Constrijud (ordens de constrição)"}

#: Os processos de cada cadeia: (código, nome curto, AVISO também é falha?).
#: No `RI_CNIB` o AVISO é caso novo da CNIB — trabalho, e não rotina parada. Na
#: rotina das minutas e no envio da CENSEC, o AVISO é «não terminou como
#: devia» ou «está desligado»: aí a cadeia parou. Na situação da CENSEC o
#: AVISO é ato impedido, trabalho de quem lavrou. No Constrijud, o AVISO dos
#: três é trabalho (título a prenotar, ordem a prenotar, ofício ou penhora
#: nova); a rotina parada é o ERRO — no `RI_CONSTRIJUD`, inclusive a leitura do
#: e-Protocolo desligada ou sem leitura boa nas últimas 2 horas.
PROCESSOS: dict[str, tuple[tuple[str, str, bool], ...]] = {
    CNIB: (("RI_CNIB", "a conferência das ordens da CNIB", False),
           ("RI_CNIB_MINUTAS", "a rotina das minutas da CNIB", True)),
    CENSEC: (("ROTINA_CENSEC_ENVIO", "o envio da madrugada à CENSEC", True),
             ("CASA_CENSEC", "a conferência da situação da CENSEC", False)),
    CONSTRIJUD: (("RI_ONR_EPROTOCOLO", "a leitura do e-Protocolo do ONR", False),
                 ("RI_CONSTRIJUD", "a conferência do Constrijud", False),
                 ("RI_WSOFICIO", "a contagem da Penhora Online (WSOfício)", False)),
}


def _dia(texto: Any) -> date | None:
    bruto = str(texto or "")[:10]
    try:
        return date.fromisoformat(bruto)
    except ValueError:
        return None


def _quando(texto: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(texto or "")[:19])
    except ValueError:
        return None


def _elo(cadeia: str, elo: str, titulo: str, desde: date | None, onde: tuple,
         detalhe: str = "") -> dict:
    """Um elo parado. `onde` = (endpoint, {argumentos}, rótulo do link)."""
    endpoint, args, rotulo = onde
    return {"cadeia": cadeia, "rotulo_da_cadeia": ROTULO_DA_CADEIA[cadeia], "elo": elo,
            "titulo": titulo, "desde": desde.isoformat() if desde else None,
            "endpoint": endpoint, "args": dict(args), "onde": rotulo,
            "detalhe": " ".join(str(detalhe or "").split())[:300]}


_CENTRAL_DO_CNIB = ("cnib_central", {}, "CNIB: a cópia local e a Central")


# ------------------------------------------------------------------ CNIB: a leitura


def _elos_da_leitura(con, hoje: date) -> list[dict]:
    import cnib_atualizador as ATZ
    import gestor_conferencia as GC
    bd = banco(con)
    if not (bd.tem_tabela("ri_cnib_leituras") and bd.tem_tabela("ri_cnib_ordens")):
        return []
    ultima = bd.um("SELECT pedida_em FROM ri_cnib_leituras ORDER BY id DESC LIMIT 1")
    ultima_dia = _dia((ultima or {}).get("pedida_em"))
    pronto = ATZ.esta_pronto(con)
    if ultima is None and not pronto["pronto"]:
        # Instalação que nunca leu a Central nem a configurou: não há cadeia.
        return []

    if not ATZ.rotina_ligada(con):
        return [_elo(CNIB, "ROTINA_DESLIGADA", "a leitura diária da Central está desligada",
                     ultima_dia, _CENTRAL_DO_CNIB,
                     "Sem ela a base local não recebe ordem nova. Religue em «Ajustes».")]
    if not pronto["pronto"]:
        return [_elo(CNIB, "SEM_CREDENCIAL", "a leitura diária não pode rodar",
                     ultima_dia, _CENTRAL_DO_CNIB, " ".join(pronto["falta"]))]

    saida = []
    # A ÚLTIMA LEITURA QUE TERMINOU DEU ERRO OU FOI RECUSADA: credencial,
    # certificado, rede ou resposta que não se entendeu. Desde a primeira da série.
    serie, desde, mensagem = 0, None, ""
    for r in bd.ler("""SELECT situacao, pedida_em, mensagem FROM ri_cnib_leituras
                        WHERE terminada_em IS NOT NULL ORDER BY id DESC LIMIT 60"""):
        if r["situacao"] not in (ATZ.ERRO, ATZ.RECUSADA):
            break
        serie += 1
        desde = _dia(r["pedida_em"])
        mensagem = mensagem or str(r["mensagem"] or "")
    if serie:
        saida.append(_elo(CNIB, "LEITURA_COM_ERRO",
                          "a leitura da Central está dando erro"
                          + (f" ({serie} seguidas)" if serie > 1 else ""),
                          desde, _CENTRAL_DO_CNIB, f"A Central respondeu: «{mensagem[:200]}»"))

    # A ROTINA NÃO RODA: nenhuma leitura pedida nos últimos dias.
    if ultima_dia is None or (hoje - ultima_dia).days > GC.CNIB_DIAS_TOLERADOS:
        saida.append(_elo(CNIB, "SEM_LEITURA", "a leitura diária da Central não está rodando",
                          ultima_dia, _CENTRAL_DO_CNIB,
                          "Nenhuma leitura foi pedida" + (
                              f" desde {ultima_dia:%d/%m/%Y}" if ultima_dia else " até hoje")
                          + ". A rotina sai na primeira tela do dia, no servidor principal."))

    _, dias_vazios, desde_vazia = GC._leituras_vazias_em_seguida(bd)
    if dias_vazios >= GC.CNIB_DIAS_DE_LEITURA_VAZIA:
        saida.append(_elo(CNIB, "LEITURA_VAZIA", "a leitura da Central volta vazia",
                          _dia(desde_vazia), _CENTRAL_DO_CNIB,
                          f"{dias_vazios} dias seguidos de resposta vazia. Resposta vazia "
                          "não prova que não há ordem."))

    base = _dia(bd.valor("SELECT max(data_pedido) FROM ri_cnib_ordens WHERE data_pedido < %s",
                         ((hoje + timedelta(days=1)).isoformat(),)))
    if base is None or (hoje - base).days > GC.CNIB_DIAS_TOLERADOS:
        rodada = GC._ultima_rodada_da_fila(bd) if ATZ.fila_autorizada(con) else None
        quando = _dia((rodada or {}).get("pedida_em"))
        andando = bool(rodada and int(rodada.get("lidas") or 0) > 0 and quando
                       and (hoje - quando).days <= GC.CNIB_DIAS_TOLERADOS)
        if not andando:
            saida.append(_elo(CNIB, "BASE_PARADA", "a base local não recebe ordem nova",
                              base, _CENTRAL_DO_CNIB,
                              (f"A ordem mais nova da base é de {base:%d/%m/%Y}."
                               if base else "A base local não tem nenhuma ordem.")
                              + " Enquanto isso, o «nada consta» da cópia local não vale."))
    return saida


# ------------------------------------------------------------------ os processos


def _elos_dos_processos(con, cadeia: str, agora: datetime) -> list[dict]:
    import automacao as AU
    bd = banco(con)
    if not (bd.tem_tabela("au_processos") and bd.tem_tabela("au_execucoes")):
        return []
    saida = []
    for codigo, nome, aviso_e_falha in PROCESSOS[cadeia]:
        p = AU.por_codigo(con, codigo)
        if p is None:
            # Instalação sem este processo na central: não há o que vigiar.
            continue
        onde = ("automacao_processo", {"processo_id": p["id"]}, f"Automação → {p['nome']}")
        if not p.get("ativo"):
            # Desligado e nunca rodou: esta casa não usa o processo, e não há
            # cadeia. Desligado depois de rodar: a rotina parou.
            if not bd.valor("SELECT count(*) FROM au_execucoes WHERE processo_id=%s",
                            (p["id"],)):
                continue
            saida.append(_elo(cadeia, "PROCESSO_DESLIGADO",
                              f"{nome} está desligada na central de automação",
                              _dia(p.get("alterado_em")), onde,
                              "Quem liga e desliga processo é o oficial."))
            continue
        rodando = bd.valor("SELECT count(*) FROM au_execucoes WHERE processo_id=%s AND situacao=%s",
                           (p["id"], "RODANDO"))
        ultima = bd.um("""SELECT situacao, iniciada_em, relato FROM au_execucoes
                           WHERE processo_id=%s AND situacao NOT IN ('PULADA', 'RODANDO')
                           ORDER BY id DESC LIMIT 1""", (p["id"],))
        if ultima and (ultima["situacao"] in _FALHAS
                       or (aviso_e_falha and ultima["situacao"] == "AVISO")):
            desde = _dia(p.get("alerta_desde")) or _dia(ultima["iniciada_em"])
            saida.append(_elo(cadeia, "PROCESSO_COM_ERRO", f"{nome} terminou com problema",
                              desde, onde, str(ultima["relato"] or "")))
        # O horário que venceu há mais que a folga, e não o último da agenda:
        # num processo de 15 minutos ou de 2 em 2 horas, o último horário tem
        # sempre menos de duas horas, e o processo que parasse no meio do dia
        # só acenderia à noite (A008).
        try:
            slot = AU.ultimo_slot(AU.normalizar_agenda(p.get("agenda")), agora - ATRASO_TOLERADO)
        except Exception:                               # noqa: BLE001 — agenda inválida
            slot = None
        iniciada = _quando((ultima or {}).get("iniciada_em"))
        if slot is not None and not rodando and (iniciada is None or iniciada < slot):
            saida.append(_elo(cadeia, "PROCESSO_NAO_RODOU", f"{nome} não rodou na hora",
                              slot.date(), onde,
                              f"Devia ter rodado às {slot:%H:%M} de {slot:%d/%m}"
                              + (f"; a última rodada foi em {iniciada:%d/%m %H:%M}."
                                 if iniciada else "; nunca rodou.")))
    return saida


def _elo_da_minuta(con, hoje: date) -> list[dict]:
    """A ordem devida (documento da ordem = dono de hoje) que ficou sem minuta."""
    import automacao as AU
    if not banco(con).tem_tabela("au_processos"):
        return []
    p = AU.por_codigo(con, "RI_CNIB")
    if p is None or not p.get("ativo"):
        return []
    estado = p.get("estado") if isinstance(p.get("estado"), dict) else {}
    n = int(estado.get("devidas_sem_minuta") or 0)
    desde = _dia(estado.get("sem_minuta_desde"))
    # Com «pode agir» o próprio processo prepara a minuta: sobrou, falhou. Sem
    # ele, quem prepara é a rotina das minutas, que roda depois: só conta a
    # que atravessou um dia.
    if not n or desde is None or (desde >= hoje and not p.get("pode_agir")):
        return []
    return [_elo(CNIB, "SEM_MINUTA", f"{n} averbação(ões) devida(s) sem minuta", desde,
                 ("ri_cnib_pendentes", {}, "CNIB: o que espera seu okay"),
                 "Ordem cujo documento é o do dono de hoje e que ninguém preparou. "
                 "Prepare a minuta ou registre a decisão.")]


# ------------------------------------------------------------------ o aviso


#: As partes da medição, cada uma na sua conexão: no PostgreSQL a consulta que
#: falha aborta a transação, e uma parte quebrada não pode calar as outras.
#: (cadeia, o que se mede, função(con, agora), onde olhar se ela quebrar)
PARTES = (
    (CNIB, "a leitura da Central do CNIB",
     lambda con, agora: _elos_da_leitura(con, agora.date()), _CENTRAL_DO_CNIB),
    (CNIB, "os processos do CNIB na central de automação",
     lambda con, agora: _elos_dos_processos(con, CNIB, agora),
     ("automacao_lista", {}, "Automação")),
    (CNIB, "as minutas devidas do CNIB",
     lambda con, agora: _elo_da_minuta(con, agora.date()),
     ("ri_cnib_pendentes", {}, "CNIB: o que espera seu okay")),
    (CENSEC, "os processos da CENSEC na central de automação",
     lambda con, agora: _elos_dos_processos(con, CENSEC, agora),
     ("automacao_lista", {}, "Automação")),
    (CONSTRIJUD, "os processos do Constrijud na central de automação",
     lambda con, agora: _elos_dos_processos(con, CONSTRIJUD, agora),
     ("automacao_lista", {}, "Automação")),
)


def elos_parados(abrir: Callable[[], Any], agora: datetime) -> list[dict]:
    """Os elos parados de todas as cadeias, na ordem em que se conserta. SÓ LÊ.

    `abrir()` devolve a conexão de uma parte (um gerenciador de contexto, como
    `db.connect()`). A parte que quebra vira o elo «não deu para conferir»:
    medição que falha não vira «tudo funcionando».
    """
    saida: list[dict] = []
    for cadeia, o_que, medir, onde in PARTES:
        try:
            with abrir() as con:
                saida += medir(con, agora)
        except Exception as erro:                       # noqa: BLE001 — ver acima
            saida.append(_elo(cadeia, "NAO_MEDIU", f"não deu para conferir {o_que}", None,
                              onde, str(erro) or erro.__class__.__name__))
    return saida


def aviso(abrir: Callable[[], Any], agora: datetime) -> dict:
    """O que a faixa diz. `{quantos, elos, vermelho}`; `quantos=0` não mostra nada.

    Cada elo ganha `dias` (parado há quantos dias, ou None) e `vermelho`.
    """
    hoje = agora.date()
    elos = elos_parados(abrir, agora)
    for e in elos:
        d = _dia(e["desde"])
        e["dias"] = (hoje - d).days if d else None
        e["vermelho"] = e["dias"] is not None and e["dias"] >= DIAS_PARA_FICAR_VERMELHO
    return {"quantos": len(elos), "elos": elos, "vermelho": any(e["vermelho"] for e in elos)}
