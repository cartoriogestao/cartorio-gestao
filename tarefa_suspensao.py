"""SUSPENDER A TAREFA (E O PROCESSO) — relato #132 do oficial, 14/10/2026.

    «criar opção de suspensão de tarefas e expedientes por prazo ou por
     condição — permitir suspender a exigência da tarefa ou expediente por
     tempo, ou condicionar ao retorno de algo, como no caso de emissao de nota
     devolutiva e espera do retorno do cliente»     — na tela `/processos`

O QUE A SUSPENSÃO É, E O QUE ELA NÃO É
    Ela suspende a EXIGÊNCIA, e não a tarefa. A tarefa continua na lista, com a
    situação que tinha (ABERTA, EM_ANDAMENTO, AGUARDANDO_TERCEIRO), e ganha um
    selo «SUSPENSA» com o motivo e o fim. O que para é a COBRANÇA: o painel, o
    sino de avisos, o escalonamento ao substituto, a cobrança diária do gestor,
    a pauta do oficial e a carga da equipe deixam de contá-la como pendente e
    como vencida.

    Por isso ela NÃO É uma situação nova em `tarefa_processo.SITUACOES`. Uma
    palavra a mais ali faria a tarefa perder a situação que tinha (quem estava
    EM_ANDAMENTO voltaria como o quê?), e cada um dos módulos que leem
    `status NOT IN ('CONCLUIDA','CANCELADA')` passaria a vê-la como serviço
    conhecido ou desconhecido conforme a lista que cada um escreveu à mão. A
    suspensão mora em colunas próprias, e quem cobra pergunta a ESTA régua.

OS DOIS MODOS — e são exclusivos
    - POR PRAZO: até uma data. No dia da data a tarefa volta a ser cobrada
      sozinha — a conta é feita na leitura (`suspensa_ate > hoje`), e não
      depende de rotina nenhuma ter rodado. A manutenção diária só deixa o
      rastro («retomada automática») e limpa as colunas.
    - POR CONDIÇÃO: sem data, até alguém marcar que a condição se cumpriu
      («o cliente voltou com o documento»). Não volta sozinha: o sistema não
      sabe quando o cliente voltou.

O PRAZO PARA DE CORRER (confirmado pelo oficial em 15/10/2026: dias corridos)
    Suspender pausa o relógio: ao retomar, o vencimento anda para a frente os
    dias que a tarefa ficou suspensa — dias CORRIDOS, contados da data em que
    se suspendeu até a data em que se retomou. Na suspensão por prazo os dias
    já se sabem, e o vencimento anda NA HORA de suspender; se ela for retomada
    antes, o vencimento é refeito a partir do que era antes. Assim a volta
    automática não depende de rotina gravar nada para o prazo estar certo.

O RASTRO
    Suspender e retomar são linhas da linha do tempo da tarefa
    (`task_history`, ações SUSPENSA e RETOMADA), com quem, quando, o motivo e
    o vencimento antes e depois; a rota grava também a auditoria. O vencimento
    de antes fica guardado na própria tarefa enquanto ela está suspensa
    (`suspensa_prazo_original`), porque é dele que a retomada antecipada
    recalcula.

O EXPEDIENTE
    A obrigação do expediente é o processo dele (a tarefa ligada, desde
    12/10/2026). Suspende-se o processo; a entrada do malote que ainda espera
    «abrir processo» ou «só ciência» não tem prazo correndo contra a casa, e
    não ganha suspensão própria — DECIDIDO pelo oficial em 15/10/2026: ela se
    suspende pelo processo ligado.

AS DECISÕES DO OFICIAL DE 15/10/2026
    O prazo para em DIAS CORRIDOS (como está acima). O AUDITOR não suspende nem
    retoma: só vê — a guarda é na rota da ficha (`app.task_detail`). E o boletim
    do RCPN (`gestor_rcpn`) e a crítica da produtividade (`produtividade_agente`)
    também deixaram de cobrar a suspensa.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import tarefa_processo as TP
from bd_nativo import banco

# --------------------------------------------------------------------------
# O esquema — colunas novas em `tasks`, só acrescentadas
# --------------------------------------------------------------------------

#: Só `ADD COLUMN`, e nenhuma NOT NULL: a produção migra ao atualizar, e a
#: tabela de tarefas dela tem linhas.
MIGRACOES = (
    ("tasks", "suspensa_em", "TEXT"),              # o instante em que se suspendeu
    ("tasks", "suspensa_desde", "TEXT"),           # a data (AAAA-MM-DD) — é dela que se contam os dias
    ("tasks", "suspensa_ate", "TEXT"),             # por prazo: a data em que volta; por condição: NULL
    ("tasks", "suspensa_condicao", "TEXT"),        # por condição: o que se espera
    ("tasks", "suspensa_motivo", "TEXT"),
    ("tasks", "suspensa_por", "INTEGER"),
    ("tasks", "suspensa_prazo_original", "TEXT"),  # o vencimento de antes da suspensão
)

COLUNAS = tuple(coluna for _tabela, coluna, _tipo in MIGRACOES)


def init_suspensao_schema(con: Any) -> None:
    """Acrescenta as colunas da suspensão em `tasks`. Idempotente."""
    bd = banco(con)
    if not bd.tem_tabela("tasks"):
        return
    for tabela, coluna, tipo in MIGRACOES:
        if not bd.tem_coluna(tabela, coluna):
            bd.escrever(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")


def tem_as_colunas(con: Any | None) -> bool:
    """True quando o banco já tem as colunas. Sem conexão, supõe que sim.

    Existe para quem cobra não estourar numa tabela montada à mão (os testes de
    domínio do gestor e da carga montam `tasks` com meia dúzia de colunas): ali
    não há suspensão nenhuma, e a régua devolve «nada suspenso».
    """
    if con is None:
        return True
    return banco(con).tem_coluna("tasks", "suspensa_desde")


# --------------------------------------------------------------------------
# O vocabulário
# --------------------------------------------------------------------------

MODO_PRAZO = "PRAZO"
MODO_CONDICAO = "CONDICAO"
MODOS = {
    MODO_PRAZO: "Por prazo — até uma data; volta a ser cobrada sozinha nesse dia",
    MODO_CONDICAO: "Por condição — até o retorno de algo; alguém marca quando voltar",
}

#: As ações da linha do tempo, com a frase que o balcão lê.
ACAO_SUSPENSA = "SUSPENSA"
ACAO_RETOMADA = "RETOMADA"
ACOES = {
    ACAO_SUSPENSA: "Suspensa — a cobrança parou",
    ACAO_RETOMADA: "Suspensão encerrada — voltou a ser cobrada",
}

#: O filtro das listas (`tarefa_ordem`). Vazio = mostra, com o selo.
FILTRO = {"OCULTAR": "esconder as suspensas", "SO": "só as suspensas"}


class SuspensaoError(TP.ProcessoError):
    """Erro de regra com mensagem pronta para o balcão."""


# --------------------------------------------------------------------------
# A régua — uma só, para a lista, o painel, o sino e quem cobra
# --------------------------------------------------------------------------


def _hoje_iso(hoje: date | str | None = None) -> str:
    if hoje is None:
        return date.today().isoformat()
    if isinstance(hoje, date):
        return hoje.isoformat()
    return str(hoje)[:10]


def _prefixo(alias: str | None) -> str:
    return f"{alias}." if alias else ""


#: O marcador do pedaço de WHERE que este módulo ENTREGA. Quem o consome ainda
#: pela ponte (`database`, `tarefa_ordem`, `carga_da_equipe`,
#: `gestor_financeiro`) espera `?`, e quem já é nativo o troca no ponto de uso
#: (`tarefa_processo._pg`, `oficial_pauta`, `gestor_rcpn`, `gestor_rotina`).
#: Sai quando esses consumidores forem convertidos — junto com aquelas trocas.
_Q = "?"


def condicao_suspensa(alias: str | None = "t", hoje: date | str | None = None,
                      con: Any | None = None) -> tuple[str, list[Any]]:
    """O SQL de «está suspensa HOJE», e os parâmetros dele.

    Por prazo, ela está suspensa até a véspera da data: no dia da data volta a
    ser cobrada — sem rotina nenhuma ter de rodar antes.
    """
    if not tem_as_colunas(con):
        return "0=1", []
    p = _prefixo(alias)
    return (f"({p}suspensa_desde IS NOT NULL AND "
            f"({p}suspensa_ate IS NULL OR {p}suspensa_ate > {_Q}))", [_hoje_iso(hoje)])


def condicao_nao_suspensa(alias: str | None = "t", hoje: date | str | None = None,
                          con: Any | None = None) -> tuple[str, list[Any]]:
    """O contrário — o que entra na cobrança. Ver `condicao_suspensa`."""
    if not tem_as_colunas(con):
        return "1=1", []
    sql, params = condicao_suspensa(alias, hoje)
    return f"NOT {sql}", params


def _campo(linha: Any, nome: str) -> Any:
    """Lê a coluna da linha da ponte ou de `dict` — e None quando ela não vem."""
    try:
        return linha[nome]
    except (KeyError, IndexError, TypeError):
        return None


def esta_suspensa(linha: Any, hoje: date | str | None = None) -> bool:
    """A mesma régua de `condicao_suspensa`, em Python, sobre uma linha lida."""
    if not _campo(linha, "suspensa_desde"):
        return False
    ate = _campo(linha, "suspensa_ate")
    return not ate or str(ate)[:10] > _hoje_iso(hoje)


def _br(iso: str | None) -> str:
    d = str(iso or "")[:10]
    return f"{d[8:10]}/{d[5:7]}/{d[:4]}" if len(d) == 10 else (d or "—")


def situacao(linha: Any, hoje: date | str | None = None) -> dict | None:
    """O que o selo mostra, ou None quando a tarefa não está suspensa hoje.

    Tarefa concluída ou cancelada não mostra selo: não há cobrança a suspender.
    """
    if not esta_suspensa(linha, hoje):
        return None
    status = _campo(linha, "status")
    if status is not None and not TP.tem_servico_em_andamento(status):
        return None
    ate = _campo(linha, "suspensa_ate")
    condicao = _campo(linha, "suspensa_condicao")
    if ate:
        rotulo = f"SUSPENSA até {_br(ate)}"
    else:
        rotulo = f"SUSPENSA até: {condicao or 'condição não descrita'}"
    return {
        "modo": MODO_PRAZO if ate else MODO_CONDICAO,
        "ate": ate, "condicao": condicao,
        "desde": _campo(linha, "suspensa_desde"),
        "motivo": _campo(linha, "suspensa_motivo"),
        "por": _campo(linha, "suspensa_por"),
        "prazo_original": _campo(linha, "suspensa_prazo_original"),
        "rotulo": rotulo,
    }


# --------------------------------------------------------------------------
# A conta do prazo
# --------------------------------------------------------------------------


def _data(iso: Any) -> date | None:
    try:
        return date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return None


def _vencimento_somado(vencimento: Any, dias: int) -> str | None:
    """O vencimento andado `dias` para a frente. Sem vencimento, continua sem."""
    d = _data(vencimento)
    if d is None:
        return vencimento or None
    return (d + timedelta(days=max(0, int(dias)))).isoformat()


def dias_entre(desde: Any, ate: Any) -> int:
    """Dias corridos entre as duas datas — nunca negativo."""
    a, b = _data(desde), _data(ate)
    if a is None or b is None:
        return 0
    return max(0, (b - a).days)


# --------------------------------------------------------------------------
# Suspender e retomar
# --------------------------------------------------------------------------


def _linha(bd: Any, task_id: int) -> dict:
    """A tarefa, presa até o fim da transação: quem a lê aqui grava nela.

    FOR UPDATE: o vencimento e o «já está suspensa» saem desta leitura, e dois
    balcões ao mesmo tempo calculariam sobre o estado de antes do outro.
    """
    bd = banco(bd)
    bd._escrita()
    linha = bd.um("SELECT * FROM tasks WHERE id=%s FOR UPDATE", (int(task_id),))
    if not linha:
        raise SuspensaoError("Tarefa não encontrada.")
    return linha


def _texto(valor: str | None, falta: str) -> str:
    texto = (valor or "").strip()
    if not texto:
        raise SuspensaoError(falta)
    if len(texto) < TP.MOTIVO_MINIMO:
        raise SuspensaoError(
            f"Escreva com pelo menos {TP.MOTIVO_MINIMO} letras — é este texto "
            "que responde, meses depois, por que a cobrança parou ou voltou.")
    return texto


def _limpar(bd: Any, task_id: int, agora: str,
            vencimento: Any = None, mexe_no_vencimento: bool = False) -> None:
    sets = ", ".join(f"{c}=NULL" for c in COLUNAS)
    if mexe_no_vencimento:
        banco(bd).escrever(f"UPDATE tasks SET {sets}, due_date=%s, updated_at=%s WHERE id=%s",
                           (vencimento, agora, int(task_id)))
    else:
        banco(bd).escrever(f"UPDATE tasks SET {sets}, updated_at=%s WHERE id=%s",
                           (agora, int(task_id)))


def suspender(con: Any, task_id: int, *, modo: str, motivo: str,
              usuario_id: int | None, agora: str, ate: str | None = None,
              condicao: str | None = None, hoje: date | str | None = None) -> dict[str, Any]:
    """Suspende a cobrança da tarefa — por prazo ou por condição.

    `agora` vem de fora (o relógio da casa é `database.now()`), e `hoje`
    também pode vir, para o teste mexer no calendário.
    """
    bd = banco(con)
    hoje_iso = _hoje_iso(hoje)
    modo = (modo or "").strip().upper()
    if modo not in MODOS:
        raise SuspensaoError("Escolha como suspender: por prazo (até uma data) "
                             "ou por condição (até o retorno de algo).")
    texto_motivo = _texto(motivo, "Escreva o motivo da suspensão.")
    linha = _linha(bd, task_id)
    if linha["status"] not in TP.SITUACOES_ABERTAS:
        raise SuspensaoError(
            f"A tarefa #{task_id} está «{linha['status']}» — só se suspende o que "
            "ainda está andando.")
    # A suspensão por prazo que já passou da data não conta: ela acabou
    # sozinha, e o rastro dela se fecha antes de a nova começar.
    if _campo(linha, "suspensa_desde"):
        if esta_suspensa(linha, hoje_iso):
            raise SuspensaoError(
                f"A tarefa #{task_id} já está suspensa ({situacao(linha, hoje_iso)['rotulo']}). "
                "Retome-a primeiro, se a suspensão precisa mudar.")
        _fechar_a_que_venceu(bd, linha, agora)
        linha = _linha(bd, task_id)
    vencimento_antes = linha["due_date"]
    vencimento_depois = vencimento_antes
    data_ate = None
    texto_condicao = None
    if modo == MODO_PRAZO:
        d = _data(ate)
        if d is None:
            raise SuspensaoError("Informe até que data a tarefa fica suspensa.")
        if d.isoformat() <= hoje_iso:
            raise SuspensaoError("A data do fim da suspensão tem de ser depois de hoje.")
        data_ate = d.isoformat()
        # Os dias já se sabem: o vencimento anda agora, e a volta automática
        # não depende de rotina nenhuma gravar o prazo depois.
        vencimento_depois = _vencimento_somado(vencimento_antes, dias_entre(hoje_iso, data_ate))
        resumo = f"Por prazo, até {_br(data_ate)}."
    else:
        texto_condicao = _texto(condicao, "Descreva a condição — o que se espera para "
                                          "a tarefa voltar a andar.")
        resumo = f"Por condição: {texto_condicao}."
    bd.escrever(
        "UPDATE tasks SET suspensa_em=%s, suspensa_desde=%s, suspensa_ate=%s, suspensa_condicao=%s, "
        "suspensa_motivo=%s, suspensa_por=%s, suspensa_prazo_original=%s, due_date=%s, updated_at=%s "
        "WHERE id=%s",
        (agora, hoje_iso, data_ate, texto_condicao, texto_motivo, usuario_id,
         vencimento_antes, vencimento_depois, agora, int(task_id)))
    nota = f"{resumo} Motivo: {texto_motivo}"
    if vencimento_depois != vencimento_antes:
        nota += (f" O vencimento passou de {_br(vencimento_antes)} para "
                 f"{_br(vencimento_depois)} — o prazo não corre enquanto suspensa.")
    TP._registrar(bd, int(task_id), ACAO_SUSPENSA, usuario_id, agora,
                  antigo=vencimento_antes, novo=vencimento_depois, nota=nota)
    return {"task_id": int(task_id), "modo": modo, "ate": data_ate, "condicao": texto_condicao,
            "motivo": texto_motivo, "vencimento_antes": vencimento_antes,
            "vencimento_depois": vencimento_depois}


def retomar(con: Any, task_id: int, *, motivo: str,
            usuario_id: int | None, agora: str,
            hoje: date | str | None = None) -> dict[str, Any]:
    """Encerra a suspensão à mão — a qualquer momento — e o prazo volta a correr.

    O vencimento é o de antes da suspensão mais os dias que ela durou de fato.
    Na suspensão por prazo retomada antes da data, isso DEVOLVE os dias que
    tinham sido somados a mais ao suspender.
    """
    bd = banco(con)
    hoje_iso = _hoje_iso(hoje)
    texto = _texto(motivo, "Escreva o que aconteceu — por que a cobrança volta.")
    linha = _linha(bd, task_id)
    if not _campo(linha, "suspensa_desde"):
        raise SuspensaoError(f"A tarefa #{task_id} não está suspensa.")
    if not esta_suspensa(linha, hoje_iso):
        # Já tinha voltado sozinha: fecha o rastro como automático e diz isso —
        # sem recusar, porque recusar desfaria (rollback) o rastro que se fechou.
        _fechar_a_que_venceu(bd, linha, agora)
        return {"task_id": int(task_id), "dias": dias_entre(linha["suspensa_desde"],
                                                            linha["suspensa_ate"]),
                "vencimento_antes": linha["due_date"], "vencimento_depois": linha["due_date"],
                "motivo": texto, "ja_tinha_voltado": True}
    dias = dias_entre(linha["suspensa_desde"], hoje_iso)
    original = linha["suspensa_prazo_original"]
    novo = _vencimento_somado(original, dias)
    _limpar(bd, task_id, agora, novo, mexe_no_vencimento=True)
    nota = (f"Retomada depois de {dias} dia(s) suspensa. {texto}")
    if novo != linha["due_date"]:
        nota += f" Vencimento: {_br(original)} + {dias} dia(s) = {_br(novo)}."
    TP._registrar(bd, int(task_id), ACAO_RETOMADA, usuario_id, agora,
                  antigo=linha["due_date"], novo=novo, nota=nota)
    return {"task_id": int(task_id), "dias": dias, "vencimento_antes": linha["due_date"],
            "vencimento_depois": novo, "motivo": texto, "ja_tinha_voltado": False}


def _fechar_a_que_venceu(bd: Any, linha: Any, agora: str) -> None:
    """Fecha o rastro da suspensão por prazo que acabou sozinha.

    O vencimento já andou quando ela começou; aqui só se limpa e se anota.
    """
    _limpar(bd, linha["id"], agora)
    TP._registrar(bd, int(linha["id"]), ACAO_RETOMADA, None, agora,
                  antigo=linha["due_date"], novo=linha["due_date"],
                  nota=(f"Retomada automática: a suspensão ia até "
                        f"{_br(linha['suspensa_ate'])}, e a data chegou."))


def encerrar_as_vencidas(con: Any, *, agora: str,
                         hoje: date | str | None = None) -> int:
    """A manutenção diária: fecha o rastro das suspensões por prazo que chegaram
    à data. A cobrança já tinha voltado na leitura; isto só escreve a linha do
    tempo e limpa as colunas. Idempotente — a que fechou não volta à lista."""
    bd = banco(con)
    if not tem_as_colunas(bd):
        return 0
    # FOR UPDATE: duas passadas ao mesmo tempo fechariam o mesmo rastro duas vezes.
    bd._escrita()
    linhas = bd.ler(
        "SELECT * FROM tasks WHERE suspensa_desde IS NOT NULL AND suspensa_ate IS NOT NULL "
        "AND suspensa_ate <= %s ORDER BY id FOR UPDATE", (_hoje_iso(hoje),))
    for linha in linhas:
        _fechar_a_que_venceu(bd, linha, agora)
    return len(linhas)


def vencimento_editado(con: Any, task_id: int, antes: Any, depois: Any) -> None:
    """Quem muda o vencimento à mão durante a suspensão muda também o de antes.

    A retomada recalcula a partir de `suspensa_prazo_original`; sem isto, ela
    desfaria em silêncio a correção de quem editou. O de antes anda os mesmos
    dias que o vencimento andou; apagado o vencimento, apaga-se o de antes.
    """
    bd = banco(con)
    if not tem_as_colunas(bd):
        return
    linha = _linha(bd, task_id)
    if not _campo(linha, "suspensa_desde"):
        return
    a, d, original = _data(antes), _data(depois), _data(linha["suspensa_prazo_original"])
    if d is None or original is None or a is None:
        novo_original = depois or None
    else:
        novo_original = (original + (d - a)).isoformat()
    bd.escrever("UPDATE tasks SET suspensa_prazo_original=%s WHERE id=%s",
                (novo_original, int(task_id)))


def encerrar_pelo_fim_da_tarefa(con: Any, task_id: int, novo_status: str,
                                usuario_id: int | None, agora: str) -> bool:
    """Concluir ou cancelar a tarefa suspensa encerra a suspensão junto.

    Sem isto, a tarefa reaberta meses depois voltaria «suspensa» por uma
    condição de que ninguém se lembra mais. O vencimento não se mexe: o
    serviço terminou.
    """
    bd = banco(con)
    if not tem_as_colunas(bd):
        return False
    linha = _linha(bd, task_id)
    if not _campo(linha, "suspensa_desde"):
        return False
    _limpar(bd, task_id, agora)
    TP._registrar(bd, int(task_id), ACAO_RETOMADA, usuario_id, agora,
                  nota=(f"A suspensão foi encerrada junto com a mudança da tarefa "
                        f"para «{novo_status}»."))
    return True
