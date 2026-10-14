"""A TAREFA COMO PROCESSO — o relato #59 do oficial, e o que ele pede.

    «quando atualizar o andamento nas tarefas, insetir botao para informar que o
     responsavel deu andamento e informar quem criou ou o substituto para novo
     andamento»
    «permitir um sistema de processamento e transito de responsabilidades durante
     a tarefa. A obrigacao como processo para ao final chegar na pratica do ato.
     Podemos revisar o geral das tarefas e expedientes para todos funcionarem
     coomo processos.»
    — Mario Exemplo dos Santos, na tela `task_detail`, `/tarefas/85`, 14/09/2026

A PRIMEIRA METADE JÁ ESTAVA FEITA quando isto foi escrito. O botão de andamento
existe desde 27/08 e chama-se «Histórico e andamento» — «Registrar andamento,
contato, dependência, providência…» —, grava com data e com o nome de quem
registrou, e aparece na linha do tempo junto com as outras ações. O que ESTE
módulo faz é a segunda metade: o trânsito.

MEDIDO NA PRODUÇÃO EM 17/09/2026, antes de escrever qualquer linha — 95 tarefas:

| | |
|---|---|
| `ABERTA` · `CONCLUIDA` | **89** · **5** |
| `PENDENTE` | **1** — a tarefa **#85**, e ela é o próprio relato: concluída em 08/09 11:40, com o carimbo gravado, e com uma palavra que não pertence ao vocabulário do sistema |
| histórico | **56** linhas, **7** ações distintas, **todas** em jargão na tela (`ALTEROU_STATUS`, `ESCALONAMENTO_AUTOMATICO`, `NOTA`, `CRIADA`…) |
| `ALTEROU_*USER*` | **zero** — o histórico gravaria o NÚMERO da pessoa no lugar do nome; é defeito latente, e ninguém o alcançou ainda |
| escalonamento automático | **13** linhas dizendo «Responsável substituto **#2** deve acompanhar» — este, sim, **está na tela** |
| sem responsável · sem quem criou | **79** de 95 · **78** de 95 |
| histórico do expediente | **não existe**: são 13 expedientes, todos com responsável, e nenhuma tabela de rastro |

O ÚLTIMO NÚMERO GOVERNA O DESENHO DA PASSAGEM. Com 79 tarefas sem responsável,
uma regra do tipo «só quem responde passa» deixaria a maior parte do serviço sem
ninguém que possa movê-lo — e o balcão não é lugar de pedir ao ADMIN o que ele
pode fazer sozinho. **Quem passa é quem tem login, e o que protege a casa é o
rastro**: o nome de quem passou fica na linha do tempo, com o motivo escrito.

AS DUAS METADES DO DIREITO DE IR E VIR, e cada uma protege alguém:

- **Reabrir** é o caminho de volta da conclusão — sem ele, tarefa fechada por
  engano ficava fechada. Exige motivo escrito e apaga o carimbo de conclusão,
  porque carimbo que fica depois de a tarefa voltar a andar **mente sobre o dia
  em que o serviço terminou**.
- **Passar** é o caminho lateral: a tarefa sai da mão de um e entra na de outro,
  com o motivo escrito. Não muda a situação — quem recebe decide se começa,
  aguarda terceiro ou conclui.

O EXPEDIENTE FICA DECLARADO — e não esquecido. Ele tem responsável e substituto
gravados, e não tem tabela de histórico nenhuma; dar a ele o mesmo trânsito é
revisão de outro módulo, e o oficial pediu para revisar. Fica escrito aqui para
não se procurar o que não existe, em vez de aparecer como se já funcionasse.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date
from typing import Any

#: `@login` no texto do andamento — relato #110 (notificar sem passar a tarefa).
_MENCAO_LOGIN = re.compile(r"@([A-Za-z0-9_]+)")

# --------------------------------------------------------------------------
# O que se recusa, e por quê
# --------------------------------------------------------------------------

#: O piso de letras do motivo escrito, o mesmo da recusa de certidão do RCPN e
#: do RI, e o mesmo da linha do problema resolvido (relato #82). «ok» não
#: responde à pergunta que a correição faz, e a pergunta aqui é
#: «por que esta tarefa voltou / por que ela mudou de mão?».
MOTIVO_MINIMO = 10

MOTIVO_CURTO = (
    f"Escreva o motivo, com pelo menos {MOTIVO_MINIMO} letras — é ele que "
    "responde, meses depois, por que a tarefa voltou ou mudou de mão."
)

MOTIVO_AUSENTE = "Escreva o motivo. Sem ele a passagem não se registra."


class ProcessoError(ValueError):
    """Erro de regra com mensagem pronta para o balcão."""


# --------------------------------------------------------------------------
# O vocabulário da situação — e ele é o mesmo de `TASK_STATUSES`
# --------------------------------------------------------------------------

#: AS SITUAÇÕES QUE O SISTEMA CONHECE — e a lista mora AQUI, e não em `app.py`.
#:
#: Ela estava escrita lá (`TASK_STATUSES`), e daqui de baixo era inalcançável
#: sem carregar o Flask inteiro: quem precisa dela fora da tela — o script que
#: conserta palavra torta no banco da produção — teria de reescrevê-la à mão,
#: que é como duas listas divergem. `app.TASK_STATUSES` passou a ser um apelido
#: para isto, e há teste que exige que os dois sejam a mesma coisa.
SITUACOES = ("ABERTA", "EM_ANDAMENTO", "AGUARDANDO_TERCEIRO", "CONCLUIDA", "CANCELADA")

#: Reabrir devolve a tarefa a ABERTA, e **não** a uma palavra nova. Até
#: 17/09/2026 a rota escrevia `PENDENTE`, que não está em `SITUACOES`: a tarefa
#: saía do filtro «Abertas» e não voltava a nenhum, com o carimbo de conclusão
#: ainda dentro dela. Medido: uma linha assim, a #85 — o próprio relato.
STATUS_DE_REABERTURA = "ABERTA"

#: Só a conclusão carimba. Qualquer outra situação **não tem** carimbo: o
#: carimbo diz «este serviço terminou em tal dia», e serviço que voltou a andar
#: não terminou.
STATUS_QUE_CARIMBAM = ("CONCLUIDA",)

#: As situações em que não há serviço para passar adiante.
STATUS_SEM_SERVICO = ("CONCLUIDA", "CANCELADA")

#: As situações que ainda pedem trabalho — **a lista POSITIVA das conhecidas**.
#:
#: Isto era um `NOT IN ('CONCLUIDA','CANCELADA')`, e a diferença não é de
#: estilo: com o filtro negativo, **qualquer palavra desconhecida entrava na
#: vista dos abertos**. `PENDENTE` é o caso vivo — ela quer dizer «a tarefa
#: voltou a andar» e também «a tarefa parou», e o sistema não sabe qual. Chutar
#: «aberto» mostraria ao balcão serviço que talvez esteja terminado; chutar
#: «concluído» esconderia o que talvez esteja esperando. É a régua do problema
#: #77 («a palavra desconhecida não entra em vista nenhuma, de propósito»),
#: aplicada aqui: a vista «Em aberto» lista só o que o sistema reconhece, e a
#: vista «Todas» mostra a palavra **como ela é**, com o aviso.
#:
#: Quem derrubou o filtro negativo foi o teste da tarefa fora do vocabulário —
#: escrito por mim, e ele acusou a minha própria régua, não o teste.
SITUACOES_ABERTAS = tuple(s for s in SITUACOES if s not in STATUS_SEM_SERVICO)


def condicao_aberta(coluna: str = "status") -> tuple[str, list[str]]:
    """O `IN (...)` das situações conhecidas, e os parâmetros dele.

    Existe para o **número** não mentir: o painel conta «tarefas abertas» e
    «vencidas», e com o filtro negativo qualquer palavra desconhecida inflava os
    dois — a tarefa que o sistema não sabe ler aparecia como serviço de hoje, e
    como atraso se tivesse prazo. O contador tem de usar a mesma régua da lista;
    escrito duas vezes, ele divergiria no primeiro conserto.

    **Onde esta régua NÃO entra, de propósito:** o recálculo de prazo da inspeção,
    a atribuição em lote e o escalonamento por vencimento continuam alcançando a
    tarefa de palavra desconhecida. São caminhos de *ação*, e a tarefa que o
    sistema não entende é justamente a que precisa de alguém — filtrá-la ali a
    deixaria invisível em vez de declarada. O que se recusa é **contá-la** como
    serviço conhecido; o que se preserva é ela continuar **alcançável**.
    """
    marcadores = ",".join("?" * len(SITUACOES_ABERTAS))
    return f"{coluna} IN ({marcadores})", list(SITUACOES_ABERTAS)


def carimba_o_status(status: str | None) -> bool:
    """True quando esta situação guarda (ou passa a guardar) o carimbo."""
    return (status or "") in STATUS_QUE_CARIMBAM


def tem_servico_em_andamento(status: str | None) -> bool:
    """True quando há trabalho para passar de uma mão para outra."""
    return (status or "") not in STATUS_SEM_SERVICO


# --------------------------------------------------------------------------
# As vistas da lista — «o que está comigo» e «o que passou por mim»
# --------------------------------------------------------------------------

#: «Em aberto» é a vista de sempre, e a que abre a tela.
VISTA_ABERTAS = "ABERTAS"
#: O que está na minha mão agora.
VISTA_COMIGO = "COMIGO"
#: O que eu passei adiante e **ainda está andando** — as concluídas saem daqui,
#: como saem de tudo: o que terminou não pede acompanhamento.
VISTA_PASSOU_POR_MIM = "PASSOU_POR_MIM"
#: Quem foi chamado no andamento e ainda não respondeu com uma NOTA sua.
VISTA_PEDIRAM_RESPOSTA = "PEDIRAM_RESPOSTA"

VISTAS_ESPECIAIS = (
    VISTA_ABERTAS,
    VISTA_COMIGO,
    VISTA_PEDIRAM_RESPOSTA,
    VISTA_PASSOU_POR_MIM,
)

ROTULO_DA_VISTA = {
    VISTA_ABERTAS: "Em aberto",
    VISTA_COMIGO: "Comigo",
    VISTA_PEDIRAM_RESPOSTA: "Pediram minha resposta",
    VISTA_PASSOU_POR_MIM: "Passou por mim",
}

#: O que a tela diz de cada vista, embaixo do filtro. Vista que não se explica
#: sozinha faz a pessoa procurar o que não está ali — a mesma régua da marca
#: da ajuda («2 relatos», e não «2»).
AJUDA_DA_VISTA = {
    # «Tudo» era mentira depois do conserto: a palavra fora do vocabulário saiu
    # desta vista de propósito, e a frase precisa dizer o que a vista faz — a
    # linha que promete tudo e esconde uma não deixa ninguém procurar.
    VISTA_ABERTAS: (
        "O que ainda não foi concluído nem cancelado, entre as situações que "
        "o sistema conhece."
    ),
    VISTA_COMIGO: "O que está na sua mão — só o que ainda está andando.",
    VISTA_PEDIRAM_RESPOSTA: (
        "Tarefas em que alguém pediu o seu andamento ou resposta, sem passar "
        "a responsabilidade para você. Some daqui quando você registrar uma NOTA."
    ),
    VISTA_PASSOU_POR_MIM: (
        "O que você passou para outra pessoa e continua andando. "
        "O que já foi concluído sai daqui."
    ),
}


def filtro_da_vista(vista: str | None, usuario_id: int | None) -> tuple[list[str], list[Any]]:
    """As condições de SQL de cada vista, e os parâmetros delas.

    Mora aqui, e não em `database.py`, por uma razão só: **é a mesma régua da
    tela e da lista**. Duas versões do pedaço que decide «o que está comigo»
    divergiriam no primeiro conserto, e a que ficasse velha mostraria ao
    escrevente o serviço de outra pessoa como se fosse dele.

    Devolve listas vazias quando não há filtro nenhum — que é o caso de «Todas».
    """
    if vista in (None, ""):
        return [], []
    if vista == VISTA_ABERTAS:
        # Lista POSITIVA das situações conhecidas: palavra fora do vocabulário
        # não entra aqui — ver `SITUACOES_ABERTAS`. A vista «Todas» é a que a
        # mostra, com a palavra como ela é.
        condicao, params = condicao_aberta("t.status")
        return [condicao], params
    if vista in (VISTA_COMIGO, VISTA_PASSOU_POR_MIM):
        if usuario_id is None:
            # Zero por engano é o defeito que a casa mais paga: sem saber de
            # quem é a lista, uma lista vazia se leria como «você não tem
            # nada». Aqui isso é erro de chamada, e não medição.
            raise ProcessoError(
                f"A vista «{ROTULO_DA_VISTA.get(vista, vista)}» precisa de "
                "saber de quem é a lista."
            )
        abertas, params_abertas = condicao_aberta("t.status")
        if vista == VISTA_COMIGO:
            return (
                ["t.assigned_user_id=?", abertas],
                [usuario_id, *params_abertas],
            )
        # O que eu passei e não voltou para a minha mão. `IS NULL` entra porque
        # tarefa sem responsável está com ninguém, e não comigo.
        return (
            [
                abertas,
                "(t.assigned_user_id IS NULL OR t.assigned_user_id<>?)",
                (
                    "EXISTS (SELECT 1 FROM task_history h WHERE h.task_id=t.id"
                    " AND h.action='PASSAGEM' AND h.user_id=?)"
                ),
            ],
            [*params_abertas, usuario_id, usuario_id],
        )
    if vista == VISTA_PEDIRAM_RESPOSTA:
        abertas, params_abertas = condicao_aberta("t.status")
        uid = str(usuario_id)
        return (
            [
                abertas,
                (
                    "EXISTS (SELECT 1 FROM task_history n WHERE n.task_id=t.id"
                    " AND n.action='NOTIFICACAO' AND n.new_value=?"
                    " AND n.id > COALESCE((SELECT MAX(r.id) FROM task_history r"
                    " WHERE r.task_id=t.id AND r.user_id=? AND r.action='NOTA'), 0))"
                ),
            ],
            [*params_abertas, uid, usuario_id],
        )
    # Uma situação qualquer, escolhida na lista (CONCLUIDA, CANCELADA…).
    return ["t.status=?"], [vista]


def contagem_por_vista(
    con: sqlite3.Connection, usuario_id: int | None, sector: str | None = None
) -> dict[str, int]:
    """Quantos em cada vista — pela MESMA régua que monta a lista.

    O número ao lado do botão vem daqui, e não de uma segunda consulta escrita à
    mão: contagem que não acompanha o próprio filtro é o carimbo que mente sobre
    ele — foi o achado do relato #82, na lista de problemas. **E o setor entra
    junto**: esta lista tem dois filtros além da vista, e com um setor escolhido
    o número diz «quantos NESTE setor», que é o que a lista mostra.
    """
    fora: dict[str, int] = {}
    for vista in VISTAS_ESPECIAIS:
        filtros, params = filtro_da_vista(vista, usuario_id)
        if sector:
            filtros.append("t.sector=?")
            params.append(sector)
        where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
        fora[vista] = int(
            con.execute(f"SELECT COUNT(*) FROM tasks t {where}", params).fetchone()[0]
        )
    return fora




_VISTAS_NOTIFICACAO = (VISTA_COMIGO, VISTA_PEDIRAM_RESPOSTA)


def _contagem_notificacao(
    con: sqlite3.Connection,
    usuario_id: int,
    filtros_extra: list[str],
    params_extra: tuple[Any, ...] = (),
) -> int:
    """Tarefas em Comigo + Pediram resposta, com filtros SQL adicionais."""
    total = 0
    for vista in _VISTAS_NOTIFICACAO:
        filtros, params = filtro_da_vista(vista, usuario_id)
        filtros.extend(filtros_extra)
        where = "WHERE " + " AND ".join(filtros)
        total += int(
            con.execute(f"SELECT COUNT(*) FROM tasks t {where}", (*params, *params_extra)).fetchone()[0]
        )
    return total


def _hoje_iso(hoje: date | str | None = None) -> str:
    if hoje is None:
        return date.today().isoformat()
    if isinstance(hoje, date):
        return hoje.isoformat()
    return str(hoje)[:10]


def contagem_tier_critico_tarefas(
    con: sqlite3.Connection, usuario_id: int, hoje: date | str | None = None
) -> int:
    """CRÍTICA ou prazo vencido (qualquer prioridade) — tier Crítico."""
    h = _hoje_iso(hoje)
    return _contagem_notificacao(
        con,
        usuario_id,
        [
            "(t.priority='CRITICA' OR (t.due_date IS NOT NULL AND t.due_date < ?))",
        ],
        (h,),
    )


def contagem_tier_alta_tarefas(
    con: sqlite3.Connection, usuario_id: int, hoje: date | str | None = None
) -> int:
    """Prioridade ALTA ainda no prazo — tier Importante."""
    h = _hoje_iso(hoje)
    return _contagem_notificacao(
        con,
        usuario_id,
        [
            "t.priority='ALTA'",
            "NOT (t.due_date IS NOT NULL AND t.due_date < ?)",
        ],
        (h,),
    )


def contagem_media_baixa_notificacao(
    con: sqlite3.Connection, usuario_id: int, hoje: date | str | None = None
) -> tuple[int, int]:
    """MÉDIA e BAIXA em aberto, no prazo — faixa «Tarefas pendentes»."""
    h = _hoje_iso(hoje)
    fora_vencida = [
        "NOT (t.due_date IS NOT NULL AND t.due_date < ?)",
    ]
    media = _contagem_notificacao(
        con, usuario_id, ["t.priority='MEDIA'", *fora_vencida], (h,)
    )
    baixa = _contagem_notificacao(
        con, usuario_id, ["t.priority='BAIXA'", *fora_vencida], (h,)
    )
    return media, baixa


def contagem_criticas_notificacao(con: sqlite3.Connection, usuario_id: int) -> int:
    """Compatível com chamadas antigas — equivale ao tier Crítico completo."""
    return contagem_tier_critico_tarefas(con, usuario_id)


def contagem_pendentes_nao_criticas(con: sqlite3.Connection, usuario_id: int) -> int:
    """Soma MÉDIA+BAIXA (no prazo) — compatibilidade."""
    m, b = contagem_media_baixa_notificacao(con, usuario_id)
    return m + b


def texto_tarefas_criticas(quantidade: int) -> str:
    if quantidade == 1:
        return "Você possui 1 tarefa crítica ou com prazo vencido em aberto"
    return f"Você possui {quantidade} tarefas críticas ou com prazo vencido em aberto"


def texto_tarefas_alta(quantidade: int) -> str:
    if quantidade == 1:
        return "Você possui 1 tarefa de prioridade ALTA em aberto"
    return f"Você possui {quantidade} tarefas de prioridade ALTA em aberto"


def texto_tarefas_media_baixa_intro(media: int, baixa: int) -> str:
    total = int(media or 0) + int(baixa or 0)
    if total == 1:
        return "Você possui 1 tarefa:"
    return f"Você possui {total} tarefa(s):"


def contagem_pendentes_notificacao(
    con: sqlite3.Connection, usuario_id: int
) -> int:
    """Comigo + Pediram minha resposta — mesma régua que `contagem_por_vista`."""
    c = contagem_por_vista(con, usuario_id, sector=None)
    return int(c[VISTA_COMIGO] + c[VISTA_PEDIRAM_RESPOSTA])


def contagem_sem_responsavel_abertas(con: sqlite3.Connection) -> int:
    """Tarefas abertas (vocabulário conhecido) sem responsável — só ADMIN no modal/faixa."""
    abertas, params = condicao_aberta("t.status")
    sql = (
        f"SELECT COUNT(*) FROM tasks t WHERE t.assigned_user_id IS NULL AND ({abertas})"
    )
    return int(con.execute(sql, params).fetchone()[0])


def texto_tarefas_pendentes(quantidade: int) -> str:
    if quantidade == 1:
        return "Você possui 1 tarefa pendente"
    return f"Você possui {quantidade} tarefas pendentes"


def texto_sem_responsavel(quantidade: int) -> str:
    if quantidade == 1:
        return "Há 1 tarefa em aberto sem responsável"
    return f"Há {quantidade} tarefas em aberto sem responsável"


def tarefas_fora_do_vocabulario(
    con: sqlite3.Connection, sector: str | None = None
) -> int:
    """Quantas tarefas têm situação que o sistema não conhece.

    Existe para o número **não sumir**: a palavra desconhecida sai de todas as
    vistas de propósito (ver `SITUACOES_ABERTAS`) e ficaria só em «Todas», que
    ninguém abre por acaso. É a régua do problema #77 — a palavra fora do
    vocabulário não se chuta em vista nenhuma, **e também não se esconde**: ela
    aparece contada, com a palavra como ela é, e quem sabe o que ela quer dizer
    a corrige.

    Conta pela régua do módulo (`SITUACOES`), e não por uma lista escrita aqui.
    """
    marcadores = ",".join("?" * len(SITUACOES))
    filtros = [f"COALESCE(t.status,'') NOT IN ({marcadores})"]
    params: list[Any] = list(SITUACOES)
    if sector:
        filtros.append("t.sector=?")
        params.append(sector)
    return int(
        con.execute(
            f"SELECT COUNT(*) FROM tasks t WHERE {' AND '.join(filtros)}", params
        ).fetchone()[0]
    )



#: Tipos de andamento na linha do tempo da tarefa (pedido Beatriz / cart3,
#: tarefa #80 Usucapiao — observação tipada, não só texto livre).
#:
#: O código fica em `task_history.new_value` nas linhas `NOTA`. Linhas antigas
#: sem tipo leem-se como «Observação». `NOTIFICACAO` continua usando new_value
#: para o id de quem foi chamado — o tipo vai só na NOTA irmã.
TIPOS_ANDAMENTO = (
    ("OBSERVACAO", "Observação"),
    ("EMITIDA_NOTA_EXIGENCIA", "Emitida nota de exigência"),
    ("AGUARDANDO_CLIENTE", "Aguardando o cliente"),
    ("CUMPRIR_EXIGENCIAS", "Cumprir exigências"),
    ("CUMPRIDO", "Cumprido"),
    ("EM_ANALISE", "Em análise"),
    ("DOCUMENTO_PENDENTE", "Documento pendente"),
    ("CONTATO_REALIZADO", "Contato realizado"),
    ("PROVIDENCIA", "Providência"),
    ("DEPENDENCIA_EXTERNA", "Dependência externa"),
)

TIPOS_ANDAMENTO_MAP = dict(TIPOS_ANDAMENTO)
TIPO_ANDAMENTO_PADRAO = "OBSERVACAO"


def normalizar_tipo_andamento(tipo: str | None) -> str:
    """Devolve o código conhecido, ou OBSERVACAO quando a palavra não existe."""
    chave = (tipo or "").strip().upper()
    if chave in TIPOS_ANDAMENTO_MAP:
        return chave
    return TIPO_ANDAMENTO_PADRAO


def rotulo_do_tipo_andamento(tipo: str | None) -> str:
    """Frase do balcão para o tipo — tipo vazio = Observação (legado)."""
    if not (tipo or "").strip():
        return TIPOS_ANDAMENTO_MAP[TIPO_ANDAMENTO_PADRAO]
    return TIPOS_ANDAMENTO_MAP.get(
        normalizar_tipo_andamento(tipo),
        TIPOS_ANDAMENTO_MAP[TIPO_ANDAMENTO_PADRAO],
    )


def texto_andamento_com_tipo(tipo: str | None, nota: str) -> str:
    """Prefixa o rótulo do tipo quando não é só observação — útil na passagem."""
    texto = (nota or "").strip()
    codigo = normalizar_tipo_andamento(tipo)
    if codigo == TIPO_ANDAMENTO_PADRAO:
        return texto
    rotulo = TIPOS_ANDAMENTO_MAP[codigo]
    if texto.startswith(f"[{rotulo}]"):
        return texto
    return f"[{rotulo}] {texto}" if texto else f"[{rotulo}]"

# --------------------------------------------------------------------------
# O histórico sai em português — «a linha do tempo não é para programador»
# --------------------------------------------------------------------------

#: A palavra que o histórico grava, e a frase que o balcão lê. O relato #59 é de
#: um escrevente que abriu a ficha e viu `ALTEROU_STATUS` e
#: `ESCALONAMENTO_AUTOMATICO` na própria linha do tempo.
ACOES = {
    "CRIADA": "Tarefa criada",
    "NOTA": "Andamento registrado",
    "NOTIFICACAO": "Pediu andamento ou resposta de",
    "PASSAGEM": "Passou para outro responsável",
    "REABERTA": "Tarefa reaberta",
    "NORMALIZADA": "Situação corrigida no banco",
    "PRAZO_CALCULADO": "Vencimento calculado",
    "ATRIBUICAO_EM_LOTE": "Responsável definido em lote",
    "ESCALONAMENTO_AUTOMATICO": "Venceu — o substituto foi avisado",
}

#: O rótulo de cada coluna da tarefa, para as linhas `ALTEROU_<COLUNA>`.
COLUNAS = {
    "TITLE": "Mudou o título",
    "DESCRIPTION": "Mudou a descrição",
    "SECTOR": "Mudou o setor",
    "SYSTEM_NAME": "Mudou o sistema/tema",
    "PRIORITY": "Mudou a prioridade",
    "STATUS": "Mudou a situação",
    "START_DATE": "Mudou a data-base",
    "DUE_DAYS": "Mudou o prazo em dias",
    "DUE_DATE": "Mudou o vencimento",
    "ASSIGNED_USER_ID": "Mudou o responsável",
    "BACKUP_USER_ID": "Mudou o substituto",
    "EVIDENCE_REQUIRED": "Mudou a exigência de evidência",
    "LEGAL_REF": "Mudou a referência normativa",
}

#: As colunas cujo valor é uma PESSOA. O histórico gravava o número dela; daqui
#: para a frente grava o nome, porque quem lê a ficha pergunta «passou para
#: quem?», e «passou para 5» não responde.
COLUNAS_DE_PESSOA = ("ASSIGNED_USER_ID", "BACKUP_USER_ID", "COMPLETED_BY")


def rotulo_da_acao(acao: str | None) -> str:
    """A frase que o balcão lê no lugar da palavra do histórico.

    Ação desconhecida **não some**: ela volta como está, para não se perder o
    que aconteceu por falta de um rótulo. É melhor uma palavra técnica na tela
    do que um fato escondido.
    """
    texto = (acao or "").strip()
    if not texto:
        return "—"
    if texto in ACOES:
        return ACOES[texto]
    if texto.startswith("ALTEROU_"):
        coluna = texto[len("ALTEROU_"):]
        return COLUNAS.get(coluna, f"Mudou {coluna.replace('_', ' ').lower()}")
    return texto


def nome_do_usuario(con: sqlite3.Connection, usuario_id: int | None) -> str | None:
    """O nome de quem fez, ou None. Nome não se inventa, e a ficha mostra '—'."""
    if usuario_id is None:
        return None
    linha = con.execute(
        "SELECT full_name FROM users WHERE id=?", (usuario_id,)
    ).fetchone()
    return linha[0] if linha else None


# --------------------------------------------------------------------------
# A tarefa, e as duas operações
# --------------------------------------------------------------------------


def _linha_da_tarefa(con: sqlite3.Connection, task_id: int) -> sqlite3.Row:
    linha = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not linha:
        raise ProcessoError("Tarefa não encontrada.")
    return linha


def _motivo_limpo(motivo: str | None) -> str:
    texto = (motivo or "").strip()
    if not texto:
        raise ProcessoError(MOTIVO_AUSENTE)
    if len(texto) < MOTIVO_MINIMO:
        raise ProcessoError(MOTIVO_CURTO)
    return texto


def _registrar(
    con: sqlite3.Connection,
    task_id: int,
    acao: str,
    usuario_id: int,
    agora: str,
    *,
    antigo: str | None = None,
    novo: str | None = None,
    nota: str | None = None,
) -> None:
    con.execute(
        "INSERT INTO task_history(task_id,ts,user_id,action,old_value,new_value,note)"
        " VALUES (?,?,?,?,?,?,?)",
        (task_id, agora, usuario_id, acao, antigo, novo, nota),
    )


def reabrir(
    con: sqlite3.Connection,
    task_id: int,
    motivo: str,
    usuario_id: int,
    agora: str,
) -> dict[str, Any]:
    """Devolve a tarefa concluída ao andamento, com motivo escrito e sem carimbo.

    O que ela desfaz, e por que as três coisas andam juntas:

    1. a situação volta para **ABERTA** — palavra que o sistema conhece, e que
       faz a tarefa reaparecer no filtro «Abertas»;
    2. o **carimbo de conclusão sai** (`completed_at` e `completed_by`), porque
       ele afirma o dia em que o serviço terminou, e o serviço voltou a andar;
    3. o **motivo fica na linha do tempo**, com quem reabriu e quando.

    Sem a terceira, a tarefa volta ao andamento e ninguém sabe por quê — e é a
    terceira que responde à correição meses depois.

    `agora` VEM DE FORA, E É OBRIGATÓRIO. O relógio desta casa é um só
    (`database.now()`), e um segundo relógio aqui dentro faria a linha do tempo
    e o `updated_at` discordarem por um segundo. Quem chama passa a hora.
    """
    texto = _motivo_limpo(motivo)
    linha = _linha_da_tarefa(con, task_id)
    if tem_servico_em_andamento(linha["status"]):
        raise ProcessoError(
            f"A tarefa #{task_id} não está concluída — a situação dela é "
            f"«{linha['status']}». Só o que foi concluído precisa ser reaberto."
        )
    instante = agora
    con.execute(
        "UPDATE tasks SET status=?, completed_at=NULL, completed_by=NULL, "
        "updated_at=? WHERE id=?",
        (STATUS_DE_REABERTURA, instante, task_id),
    )
    _registrar(
        con, task_id, "REABERTA", usuario_id, instante,
        antigo=linha["status"], novo=STATUS_DE_REABERTURA, nota=texto,
    )
    return {
        "task_id": task_id,
        "status": STATUS_DE_REABERTURA,
        "carimbo_apagado": bool(linha["completed_at"]),
        "motivo": texto,
    }


def passar_para(
    con: sqlite3.Connection,
    task_id: int,
    para_user_id: int,
    motivo: str,
    usuario_id: int,
    agora: str,
) -> dict[str, Any]:
    """Passa a tarefa para outra pessoa, com motivo escrito e nome no rastro.

    **Não muda a situação.** Quem recebe é que decide se começa, se aguarda
    terceiro ou se conclui — passar a tarefa não é começar a fazê-la, e marcar
    «em andamento» por conta própria faria o sistema afirmar que alguém já
    trabalha nela.

    **O substituto não se move.** Ele é o segundo de quem responde; trocar os
    dois de uma vez deixaria a tarefa sem ninguém atrás — e é justamente o
    substituto que o escalonamento automático avisa quando o vencimento passa.
    """
    texto = _motivo_limpo(motivo)
    linha = _linha_da_tarefa(con, task_id)
    if not tem_servico_em_andamento(linha["status"]):
        raise ProcessoError(
            f"A tarefa #{task_id} está «{linha['status']}» — não há serviço em "
            "andamento para passar adiante. Se ela precisa voltar a andar, "
            "reabra-a primeiro."
        )
    de_quem = linha["assigned_user_id"]
    if de_quem is None:
        raise ProcessoError(
            "Esta tarefa não tem responsável definido, e por isso não há de "
            "quem tirá-la. Defina o responsável no formulário e salve — a "
            "mudança fica registrada no histórico."
        )
    if para_user_id == de_quem:
        raise ProcessoError(
            f"A tarefa já está com {nome_do_usuario(con, de_quem) or 'esta pessoa'}"
            " — escolha outra pessoa para receber."
        )
    destino = con.execute(
        "SELECT id, full_name, active FROM users WHERE id=?", (para_user_id,)
    ).fetchone()
    if not destino:
        raise ProcessoError("Escolha a pessoa que vai receber a tarefa.")
    if not destino["active"]:
        # Passar para quem está desligado é entregar ao vazio: a tarefa sai da
        # mão de quem responde e não entra na de ninguém.
        raise ProcessoError(
            f"{destino['full_name']} não está ativo no sistema. Escolha quem "
            "está trabalhando hoje."
        )
    instante = agora
    con.execute(
        "UPDATE tasks SET assigned_user_id=?, updated_at=? WHERE id=?",
        (para_user_id, instante, task_id),
    )
    _registrar(
        con, task_id, "PASSAGEM", usuario_id, instante,
        antigo=nome_do_usuario(con, de_quem), novo=destino["full_name"], nota=texto,
    )
    return {
        "task_id": task_id,
        "de": nome_do_usuario(con, de_quem),
        "para": destino["full_name"],
        "para_user_id": para_user_id,
        "status": linha["status"],
        "motivo": texto,
    }


def usuarios_mencionados_no_texto(
    con: sqlite3.Connection, texto: str
) -> list[int]:
    """Resolve `@login` no andamento para ids de usuário ativos (#110)."""
    vistos: set[str] = set()
    ids: list[int] = []
    for login in _MENCAO_LOGIN.findall(texto or ""):
        chave = login.lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        linha = con.execute(
            "SELECT id FROM users WHERE lower(username)=? AND active=1",
            (chave,),
        ).fetchone()
        if linha:
            ids.append(int(linha[0]))
    return ids


def notificar_para(
    con: sqlite3.Connection,
    task_id: int,
    para_user_id: int,
    texto: str,
    usuario_id: int,
    agora: str,
    tipo: str | None = None,
) -> dict[str, Any]:
    """Registra andamento e chama alguém para responder, sem mudar o responsável.

    Relato #110 — «notificar alguém dentro de uma tarefa para dar andamento ou
    resposta», distinto da passagem (#107): quem registra continua em «Comigo».
    """
    mensagem = _motivo_limpo(texto)
    linha = _linha_da_tarefa(con, task_id)
    if not tem_servico_em_andamento(linha["status"]):
        raise ProcessoError(
            f"A tarefa #{task_id} está «{linha['status']}» — não há serviço em "
            "andamento para pedir resposta."
        )
    if para_user_id == usuario_id:
        raise ProcessoError(
            "Para pedir resposta a outra pessoa, escolha alguém que não seja "
            "você — ou use só «Registrar»."
        )
    destino = con.execute(
        "SELECT id, full_name, active FROM users WHERE id=?", (para_user_id,)
    ).fetchone()
    if not destino:
        raise ProcessoError("Escolha quem deve responder.")
    if not destino["active"]:
        raise ProcessoError(
            f"{destino['full_name']} não está ativo no sistema. Escolha quem "
            "está trabalhando hoje."
        )
    instante = agora
    _registrar(con, task_id, "NOTA", usuario_id, instante,
               novo=normalizar_tipo_andamento(tipo), nota=mensagem)
    _registrar(
        con,
        task_id,
        "NOTIFICACAO",
        usuario_id,
        instante,
        antigo=destino["full_name"],
        novo=str(para_user_id),
        nota=mensagem,
    )
    return {
        "task_id": task_id,
        "para": destino["full_name"],
        "para_user_id": para_user_id,
        "texto": mensagem,
    }
