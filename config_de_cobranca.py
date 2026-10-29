# -*- coding: utf-8 -*-
"""AS CONFIGURAÇÕES QUE COBRAM A EQUIPE — e quem pode afrouxá-las.

    «trabalhamos com mão de obra muito propensa a erros [...] não deixar a
     escrevente cometer erros. Se insistir em algo que é erro, precisa afirmar
     expressamente e deixar log» — o oficial, 29/10/2026

O CASO QUE FEZ ESTE MÓDULO NASCER (produção, só leitura, 29/10/2026)
    `settings.caixa_fim_do_expediente` diz a hora em que o caixa aberto vira
    aviso vermelho e insistente (`caixa_aviso`). O oficial disse 14h em 06/10.
    Na auditoria: 27/10 de nada para 18:00, «a pedido» da escrevente; 28/10 de
    18:00 para 19:00, de 19:00 para 20:00 e de 20:00 para 21:00, gravadas por
    um robô «a mando de» quem o aviso cobrava. **Nenhuma das quatro passou por
    rota do sistema**: as linhas não têm usuário, nem IP, nem `agente`, e a
    hora está escrita com espaço (`2026-10-28 17:43:04`), e não com o `T` que o
    servidor grava. Foi script direto no banco — `UPDATE settings` mais um
    `INSERT INTO audit_logs` escrito à mão. Uma guarda só nas rotas não teria
    parado nenhuma delas.

    E NO DIA EM QUE ESTE MÓDULO FOI ESCRITO, de novo: em 29/10 às 16h18 o
    oficial mandou voltar a 14:00; às 16h42 a conta «suporte», agente robô, a
    pôs em 19:00 «a mando de» quem o aviso cobra, com o motivo «o oficial está
    de acordo, conforme» a mesma pessoa. É exatamente o caso: quem é cobrado
    afirma pelo oficial, e o robô executa. Aqui, quem afirma é o oficial.

A REGRA, NUM LUGAR SÓ (`alterar`)
    - **Robô nunca altera**, nem a pedido de ninguém. A tentativa fica na
      auditoria (`CONFIG_DE_COBRANCA_RECUSADA`) e vira tarefa do oficial.
    - **Só o ADMIN humano altera**, e com a afirmação expressa no contrato
      comum da casa: a caixa `afirmo` marcada e o texto `afirmacao` com pelo
      menos 30 letras além da frase (`protesto_prova.afirmacao_valida`). Vai à
      auditoria como `AFIRMACAO_EXPRESSA`, regra `CONFIG_DE_COBRANCA`.
    - **MANAGER, USER, AUDITOR: recusa, «peça ao oficial»** — também gravada.
    - **O turno de um operador nunca é alterado por ele mesmo**, ainda que
      seja ADMIN.
    - **Toda alteração vira tarefa do oficial** (painel e lista de tarefas).
      Sem e-mail por evento: a casa manda o resumo do dia.

E A REGRA VALE NO BANCO (`instalar_gatilho`)
    O gatilho `settings_cobranca` recusa, dentro do PostgreSQL, toda mudança
    numa chave daqui que não tenha, ANTES, a linha `CONFIG_DE_COBRANCA_ALTERADA`
    de um ADMIN humano com aquele mesmo valor — a que `alterar` grava na mesma
    transação. Script, ferramenta ou robô que faça `UPDATE settings` direto
    recebe o erro com a frase «peça ao oficial». O gatilho é armado de novo a
    cada abertura do banco (e religado, se alguém o desligou).

    O QUE ELE NÃO FAZ, E FICA DITO: (1) a recusa do gatilho NÃO fica em
    `audit_logs` — o PostgreSQL desfaz a transação inteira, e a linha da
    tentativa iria junto; ela fica no log do PostgreSQL. (2) Quem é dono do
    banco pode desligar o gatilho ou forjar a linha de aprovação no nome do
    oficial: isso é fraude deliberada, e fica na corrente de hash da
    auditoria. O que fecha a porta de vez é o robô não ter a senha do banco.

A LISTA É FECHADA (`CHAVES`), e cada uma diz o que cobra
    Entram as chaves cujo afrouxamento cala um aviso ou abre uma trava sobre a
    equipe, e que NENHUM outro código grava — o gatilho as tranca sem quebrar
    tela nem teste. Ficaram de fora, com a razão, as que já têm caminho
    próprio (ver `FORA_DESTA_LEVA`).

ESTE MÓDULO ESCREVE SÓ EM `alterar` E EM `registrar_recusa`, sempre na
transação de quem chama. O resto lê.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from bd_nativo import banco
import caixa_aviso as CA
import identidade_do_robo as IDR

REGRA = "CONFIG_DE_COBRANCA"
ACAO_AFIRMACAO = "AFIRMACAO_EXPRESSA"
ACAO_ALTERADA = "CONFIG_DE_COBRANCA_ALTERADA"
ACAO_RECUSADA = "CONFIG_DE_COBRANCA_RECUSADA"

#: O papel que altera. Um só, de propósito: é o oficial quem responde.
PAPEL_QUE_ALTERA = "ADMIN"

#: Os motivos da recusa — o que a auditoria e a tela mostram.
MOTIVO_ROBO = "ROBO"
MOTIVO_PAPEL = "PAPEL"
MOTIVO_PROPRIO_TURNO = "PROPRIO_TURNO"
MOTIVO_SEM_AFIRMACAO = "SEM_AFIRMACAO"
MOTIVO_SEM_LOGIN = "SEM_LOGIN"
#: As recusas que viram tarefa do oficial: quem é cobrado tentando afrouxar.
#: O oficial que esqueceu de marcar «afirmo» não ganha tarefa de si mesmo.
MOTIVOS_QUE_AVISAM = (MOTIVO_ROBO, MOTIVO_PAPEL, MOTIVO_PROPRIO_TURNO, MOTIVO_SEM_LOGIN)

MENSAGEM_DO_ROBO = (
    "Robô não altera configuração que cobra a equipe — nem a pedido de "
    "ninguém. Quem altera é o oficial, na tela «Configurações que cobram a "
    "equipe», com afirmação expressa. A tentativa ficou registrada.")
MENSAGEM_DO_PAPEL = (
    "Esta configuração cobra a equipe, e só o oficial a altera. Peça ao "
    "oficial. A tentativa ficou registrada.")
MENSAGEM_DO_PROPRIO_TURNO = (
    "O seu próprio turno quem define é o oficial, e não você — o turno decide "
    "quando o aviso do SEU caixa começa. Peça ao oficial.")

#: O tipo de cada chave — decide como o valor se lê, se grava e se compara.
HORA = "HORA"
DIAS = "DIAS"
DATA = "DATA"
LIGA = "LIGA"
LISTA = "LISTA"
TURNO = "TURNO"

#: A tarefa do oficial (`tasks.source_type`).
ORIGEM_DA_TAREFA = "CONFIG_COBRANCA"

#: Quantos dias o histórico abre, e o teto de linhas da tela.
DIAS_DO_HISTORICO = 90
LIMITE_DO_HISTORICO = 500

NOME_DA_FUNCAO = "cg_settings_cobranca"
NOME_DO_GATILHO = "settings_cobranca"


class ConfigDeCobrancaError(ValueError):
    """Erro de regra, com a frase pronta para a tela."""


class ValorInvalido(ConfigDeCobrancaError):
    """O valor não é do tipo da chave — nada se grava, e não é tentativa."""


class Recusa(ConfigDeCobrancaError):
    """A pessoa (ou o robô) não pode alterar — e isso se registra."""

    def __init__(self, motivo: str, mensagem: str):
        super().__init__(mensagem)
        self.motivo = motivo


@dataclass(frozen=True)
class Chave:
    chave: str
    nome: str
    tipo: str
    padrao: str
    #: O aviso ou a trava que a chave governa.
    cobra: str
    #: O que é afrouxar — para quem lê a tela e a auditoria.
    afrouxar: str
    #: Para LIGA: (valor que trava, valor que solta). Para LISTA: "json" ou
    #: "virgula" — a forma em que o leitor de hoje já a lê.
    opcoes: tuple = ()
    formato: str = ""
    #: LISTA de EXCEÇÕES (acrescentar afrouxa) ou de INCLUSÕES (tirar afrouxa).
    lista_de_excecoes: bool = True


#: A LISTA FECHADA. Cada uma foi conferida no código: quem a lê, e que nenhum
#: outro código a grava (os testes que a gravam montam `settings` à mão, sem
#: o gatilho — ver o PR).
CHAVES: tuple[Chave, ...] = (
    Chave(CA.CHAVE_FIM, "Fim do expediente (aviso do caixa)", HORA, CA.FIM_PADRAO,
          "a partir desta hora o caixa de hoje aberto vira faixa vermelha e janela "
          "insistente (caixa_aviso), e a conferência das 14h abre tarefa crítica",
          "empurrar a hora para depois cala o aviso que obriga a fechar o caixa"),
    Chave("produtividade_aviso_expediente", "Cronômetro esquecido — hora do aviso",
          HORA, "14:15",
          "a esta hora a tela pergunta a quem tem cronômetro aberto se ainda está "
          "trabalhando (produtividade)",
          "empurrar a hora deixa o cronômetro correr sem pergunta"),
    Chave("produtividade_encerramento_automatico",
          "Cronômetro esquecido — hora do encerramento", HORA, "14:30",
          "sem resposta, o cronômetro fecha sozinho a esta hora (produtividade)",
          "empurrar a hora soma ao painel trabalho que ninguém confirmou"),
    Chave("produtividade_hora_retroativa",
          "Cronômetro esquecido — hora gravada no encerramento", HORA, "14:15",
          "o cronômetro fechado sem resposta termina nesta hora (produtividade)",
          "empurrar a hora soma minutos que ninguém trabalhou"),
    Chave("gratuidade_comprovante_dias_alerta",
          "Comprovante da gratuidade — dias até ficar vermelho", DIAS, "3",
          "passados estes dias, a barra do comprovante que falta fica vermelha e o "
          "selo entra na lista do gestor (gratuidade_comprovante)",
          "aumentar os dias adia a cobrança do comprovante"),
    Chave("gratuidade_comprovante_desde",
          "Comprovante da gratuidade — cobrado desde", DATA, "2026-10-13",
          "o selo isento obtido a partir deste dia sem comprovante vira aviso "
          "(gratuidade_comprovante)",
          "adiar a data tira da cobrança os selos de antes dela"),
    Chave("gratuidade_comprovante_incluir",
          "Comprovante da gratuidade — selos antigos incluídos", LISTA, "",
          "os selos (id) de antes da data que o oficial mandou cobrar um a um "
          "(gratuidade_comprovante)",
          "tirar um selo da lista some com a cobrança dele",
          formato="virgula", lista_de_excecoes=False),
    Chave("cib_dispensado_matriculas", "CIB dispensado nestas matrículas (RI)",
          LISTA, "",
          "a matrícula de imóvel rural sem CIB é recusada, salvo as desta lista "
          "(ri_web)",
          "acrescentar matrícula abre a trava do CIB para ela",
          formato="json", lista_de_excecoes=True),
    Chave("ri_dias_para_digitalizar", "Ficha nova sem digitalização — dias de prazo",
          DIAS, "30",
          "passados estes dias, a ficha nova sem imagem entra na lista das "
          "atrasadas (ri_web, fichas do disco)",
          "aumentar os dias tira fichas da lista das atrasadas"),
    Chave("rcpn_termo_lavrado_trancado", "Termo lavrado e selado trancado (RCPN)",
          LIGA, "LIGADO",
          "o termo lavrado e selado nesta casa não se corrige à mão: termo, "
          "número, folha e data são o livro (rc_assento)",
          "desligar deixa corrigir o termo do livro já selado",
          opcoes=("LIGADO", "DESLIGADO")),
    Chave("ri_cnib_exigir_protocolo_na_lavratura",
          "Protocolo da CNIB exigido na lavratura (RI)", LIGA, "0",
          "com «1», a alienação ou oneração só se lavra com o protocolo da "
          "consulta na Central (ri_cnib)",
          "desligar deixa lavrar sem o protocolo da consulta",
          opcoes=("1", "0")),
)

#: O turno por operador (acréscimo do oficial, 29/10/2026). A chave é
#: `caixa_turno:<login>`; o prefixo mora em `caixa_aviso`, que é quem lê.
PREFIXO_DO_TURNO = CA.PREFIXO_DO_TURNO
ITEM_DO_TURNO = Chave(
    PREFIXO_DO_TURNO, "Turno do operador (aviso do caixa)", TURNO, "",
    "para quem tem turno próprio, o aviso do caixa começa no fim do turno DELE, "
    "e não no fim do expediente; o caixa aberto antes do começo do turno atual "
    "bloqueia as outras telas (caixa_aviso)",
    "um turno que termina mais tarde cala o aviso daquele operador até lá")

#: O que tem o mesmo papel e NÃO entrou nesta leva — com a razão. Sai no PR e
#: na tela, para o oficial decidir a próxima.
FORA_DESTA_LEVA: tuple[tuple[str, str], ...] = (
    ("selo_trava_caixa",
     "já é só do ADMIN, com justificativa, e desligada põe barra vermelha para "
     "todos; 14 arquivos de teste a desligam direto — entrar no gatilho pede "
     "mudar todos eles"),
    ("onr_certidoes_selo_pago_no_onr",
     "já é só do ADMIN, com justificativa; testes a gravam direto"),
    ("selo_conferencia_desde",
     "já tem rota própria só do ADMIN (/selo/conferencia)"),
    ("rc_digitalizacao_obrigatoria_desde",
     "o esquema a semeia na primeira abertura do banco, e o teste a regrava"),
    ("ri_feriados_locais",
     "feriado a mais empurra o tríduo, o repasse e o roteiro; muitas leituras e "
     "testes, e um script de migração a gravam"),
    ("alert_days / require_backup_assignee",
     "moram no formulário geral de Configurações, que é só do ADMIN"),
    ("dois_fatores_papeis_exigidos",
     "segurança da conta, com tela própria só do ADMIN"),
    ("horários do roteiro das Centrais",
     "não são configuração: são constantes do código (protesto_roteiro."
     "HORARIOS_DA_CRA) — só mudam por versão nova"),
    ("travas do Protesto",
     "não são configuração: vivem no código, e quem insiste afirma (PR #104)"),
    ("conferência diária",
     "é tarefa do Agendador e processo da Automação (au_*), com tela própria "
     "do ADMIN — não é chave de settings"),
)

_POR_NOME = {c.chave: c for c in CHAVES}
_LOGIN = re.compile(r"^[a-z0-9._@-]{1,60}$")
_IDENTIFICADOR = re.compile(r"^[A-Za-z0-9_:]+$")


# --------------------------------------------------------------- as chaves

def e_chave_de_cobranca(chave: Any) -> bool:
    """A chave é das que cobram a equipe? Só calcula."""
    texto = str(chave or "")
    return texto in _POR_NOME or (texto.startswith(PREFIXO_DO_TURNO)
                                  and len(texto) > len(PREFIXO_DO_TURNO))


def item(chave: Any) -> Chave:
    """A descrição da chave. Fora da lista, `ValorInvalido`."""
    texto = str(chave or "").strip()
    if texto in _POR_NOME:
        return _POR_NOME[texto]
    if texto.startswith(PREFIXO_DO_TURNO) and len(texto) > len(PREFIXO_DO_TURNO):
        return ITEM_DO_TURNO
    raise ValorInvalido(f"«{texto[:80]}» não é uma das configurações que cobram "
                        f"a equipe; esta tela não a altera.")


def chave_do_turno(login: Any) -> str:
    return CA.chave_do_turno(login)


def normalizar_chave(chave: Any) -> str:
    """A chave como se grava: o login do turno vai em minúsculas (o login da
    casa não distingue caixa), para «o próprio turno» não escapar por uma letra."""
    texto = str(chave or "").strip()
    if texto.startswith(PREFIXO_DO_TURNO):
        return chave_do_turno(texto[len(PREFIXO_DO_TURNO):])
    return texto


# --------------------------------------------------------------- os valores

def _hhmm(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def _hora(texto: Any) -> str | None:
    # Aparado e cortado antes; sem repetição aberta (CodeQL: expressão
    # polinomial em dado vindo da tela).
    m = re.fullmatch(r"(\d{1,2}) ?[:h] ?(\d{2})?", str(texto or "").strip()[:20])
    if not m or int(m.group(1)) > 23 or int(m.group(2) or 0) > 59:
        return None
    return f"{int(m.group(1)):02d}:{int(m.group(2) or 0):02d}"


def normalizar(it: Chave, valor: Any) -> str:
    """O valor como se grava. Só calcula. Torto, `ValorInvalido`."""
    texto = str(valor if valor is not None else "").strip()
    if it.tipo == HORA:
        hora = _hora(texto)
        if hora is None:
            raise ValorInvalido(f"«{texto[:20]}» não é hora: escreva como 14:00.")
        return hora
    if it.tipo == DIAS:
        if not texto.isdigit() or not 1 <= int(texto) <= 365:
            raise ValorInvalido("Escreva o número de dias, de 1 a 365.")
        return str(int(texto))
    if it.tipo == DATA:
        m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", texto)
        iso = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else texto[:10]
        try:
            return date.fromisoformat(iso).isoformat()
        except ValueError:
            raise ValorInvalido("Escreva a data como 13/10/2026.") from None
    if it.tipo == LIGA:
        if texto.upper() not in {o.upper() for o in it.opcoes}:
            raise ValorInvalido(f"Escolha {' ou '.join(it.opcoes)}.")
        return next(o for o in it.opcoes if o.upper() == texto.upper())
    if it.tipo == LISTA:
        numeros = list(dict.fromkeys(re.findall(r"\d+", texto)))
        if texto and not numeros:
            raise ValorInvalido("Escreva os números separados por vírgula.")
        if it.formato == "json":
            return json.dumps(numeros, ensure_ascii=False) if numeros else ""
        return ",".join(numeros)
    if it.tipo == TURNO:
        if not texto:
            return ""          # sem turno: vale o fim do expediente
        t = CA.turno(texto)
        if t is None:
            raise ValorInvalido("Escreva o turno como 18:00-23:30 (começo e fim). "
                                "Vazio tira o turno, e vale o fim do expediente.")
        return f"{_hhmm(t[0])}-{_hhmm(t[1])}"
    raise ValorInvalido(f"Tipo desconhecido: {it.tipo}.")


def afrouxa(it: Chave, de: Any, para: Any) -> bool | None:
    """A mudança afrouxa a cobrança? Só calcula. `None` quando não se sabe
    dizer (o turno, que depende da hora de cada um)."""
    antes = str(de if de not in (None, "") else it.padrao)
    depois = str(para if para is not None else "")
    if it.tipo in (HORA, DATA):
        return depois > antes
    if it.tipo == DIAS:
        try:
            return int(depois) > int(antes)
        except ValueError:
            return None
    if it.tipo == LIGA:
        return depois.upper() == it.opcoes[1].upper()
    if it.tipo == LISTA:
        a, d = set(re.findall(r"\d+", antes)), set(re.findall(r"\d+", depois))
        return bool(d - a) if it.lista_de_excecoes else bool(a - d)
    return None


def _valor_atual(bd, chave: str) -> str | None:
    linha = bd.um("SELECT value FROM settings WHERE key = %s", (chave,))
    return None if linha is None else str(linha["value"])


def _afirmacao(afirmo: Any, texto: Any) -> str | None:
    """O texto da afirmação, já com a frase — ou None. Régua da casa."""
    from protesto_prova import afirmacao_valida
    if not afirmo:
        return None
    return afirmacao_valida(texto)


def regra_da_afirmacao() -> str:
    from protesto_prova import FRASE_DA_AFIRMACAO, PISO_DA_AFIRMACAO
    return (f"Marque «Afirmo» e escreva «{FRASE_DA_AFIRMACAO} …» com pelo menos "
            f"{PISO_DA_AFIRMACAO} letras: por que muda, e por que não é erro. Fica "
            f"na auditoria com o seu nome, e o oficial recebe tarefa.")


# --------------------------------------------------------------- quem

def _quem(bd, usuario_id: Any) -> dict | None:
    if not str(usuario_id if usuario_id is not None else "").isdigit():
        return None
    robo = "COALESCE(eh_robo, 0)" if bd.tem_coluna("users", "eh_robo") else "0"
    return bd.um(f"""SELECT id, username, full_name, role, active, {robo} AS eh_robo
                       FROM users WHERE id = %s""", (int(usuario_id),))


def conferir_quem(quem: Any, chave: Any) -> None:
    """Pode alterar? Robô, papel e o próprio turno. Só calcula; recusa com `Recusa`."""
    import selo_robo as SR
    if not quem or not int(quem.get("active") or 0):
        raise Recusa(MOTIVO_SEM_LOGIN, MENSAGEM_DO_PAPEL)
    if SR.usuario_e_robo(quem):
        raise Recusa(MOTIVO_ROBO, MENSAGEM_DO_ROBO)
    if str(quem.get("role") or "").upper() != PAPEL_QUE_ALTERA:
        raise Recusa(MOTIVO_PAPEL, MENSAGEM_DO_PAPEL)
    texto = str(chave or "")
    if (texto.startswith(PREFIXO_DO_TURNO)
            and texto == chave_do_turno(quem.get("username"))):
        raise Recusa(MOTIVO_PROPRIO_TURNO, MENSAGEM_DO_PROPRIO_TURNO)


def _login_do_turno(bd, chave: str) -> dict:
    """O operador do turno: pessoa com cadastro ativo, e não robô."""
    login = chave[len(PREFIXO_DO_TURNO):]
    if not _LOGIN.match(login):
        raise ValorInvalido("Escolha o operador na lista.")
    robo = "COALESCE(eh_robo, 0)" if bd.tem_coluna("users", "eh_robo") else "0"
    linha = bd.um(f"""SELECT id, username, full_name, {robo} AS eh_robo FROM users
                       WHERE lower(username) = %s AND active = 1""", (login,))
    if not linha or int(linha["eh_robo"] or 0):
        raise ValorInvalido("O turno é de uma pessoa com cadastro ativo — robô não "
                            "opera caixa.")
    return linha


# --------------------------------------------------------------- o aviso

def _avisar_o_oficial(bd, *, ref: str, titulo: str, descricao: str,
                      agora: str) -> int | None:
    """A tarefa do oficial. ESCREVE, na transação de quem chama.

    Uma por `ref`: se ainda está aberta, ganha a linha nova na descrição em
    vez de virar outra — o robô que insiste não enche a lista.
    """
    import oficial_pauta as OP
    if not bd.tem_tabela("tasks"):
        return None
    aberta = bd.um("""SELECT id, description FROM tasks
                       WHERE source_type = %s AND source_ref = %s
                         AND status NOT IN ('CONCLUIDA', 'CANCELADA')
                       ORDER BY id DESC LIMIT 1""", (ORIGEM_DA_TAREFA, ref))
    if aberta:
        bd.escrever("UPDATE tasks SET description = %s, updated_at = %s WHERE id = %s",
                    ((str(aberta["description"] or "") + "\n\n" + descricao)[-8000:],
                     agora, aberta["id"]))
        return int(aberta["id"])
    dono = OP.dono_da_mesa(bd)
    linhas = bd.escrever(
        """INSERT INTO tasks (source_type, source_ref, title, description, sector,
               system_name, priority, status, start_date, due_date, assigned_user_id,
               evidence_required, created_at, updated_at)
           VALUES (%s, %s, %s, %s, 'Gestão', 'Configurações que cobram a equipe',
                   'ALTA', 'ABERTA', %s, %s, %s, 0, %s, %s)
           RETURNING id""",
        (ORIGEM_DA_TAREFA, ref, titulo[:200], descricao, agora[:10], agora[:10],
         dono, agora, agora))
    novo = int(linhas[0]["id"])
    if bd.tem_tabela("task_history"):
        bd.escrever("""INSERT INTO task_history (task_id, ts, user_id, action, note)
                       VALUES (%s, %s, NULL, 'CRIADA', %s)""",
                    (novo, agora, "Aberta pela guarda das configurações que cobram a equipe."))
    return novo


def _mostrar(valor: Any, it: Chave) -> str:
    if valor is None:
        return f"o padrão ({it.padrao or 'vazio'})"
    return f"«{valor}»" if str(valor) else "vazio"


# --------------------------------------------------------------- a escrita

def alterar(con, *, chave: Any, valor: Any, usuario_id: Any, afirmo: Any,
            afirmacao: Any, agora: str, ip: Any = None) -> dict:
    """Altera uma configuração que cobra a equipe. ESCREVE, na transação de
    quem chama. É O ÚNICO CAMINHO que o gatilho do banco aceita.

    A ordem é a da regra: quem é (robô, papel, o próprio turno), o que é (a
    chave e o valor), e a afirmação. A auditoria vem ANTES da escrita em
    `settings`, porque é a linha `CONFIG_DE_COBRANCA_ALTERADA` que o gatilho
    procura para deixar passar.
    """
    bd = banco(con)
    chave = normalizar_chave(chave)
    quem = _quem(bd, usuario_id)
    conferir_quem(quem, chave)
    it = item(chave)
    if it.tipo == TURNO:
        _login_do_turno(bd, chave)
    para = normalizar(it, valor)
    de = _valor_atual(bd, chave)
    if de == para:
        return {"mudou": False, "chave": chave, "de": de, "para": para}
    texto = _afirmacao(afirmo, afirmacao)
    if texto is None:
        raise Recusa(MOTIVO_SEM_AFIRMACAO,
                     "Esta configuração cobra a equipe: para mudá-la é preciso a "
                     "afirmação expressa. " + regra_da_afirmacao())
    solta = afrouxa(it, de, para)
    o_que_faltava = (f"«{it.nome}» cobra a equipe: {it.cobra}. Mudou de "
                     f"{_mostrar(de, it)} para {_mostrar(para, it)}"
                     + (f" — {it.afrouxar}." if solta else "."))
    IDR.registrar(bd, ts=agora, user_id=quem["id"], username=quem["username"],
                  action=ACAO_AFIRMACAO, entity_type="settings", entity_id=None,
                  details={"regra": REGRA, "afirmacao": texto,
                           "o_que_faltava": o_que_faltava, "chave": chave,
                           "de": de, "para": para},
                  ip_address=ip)
    IDR.registrar(bd, ts=agora, user_id=quem["id"], username=quem["username"],
                  action=ACAO_ALTERADA, entity_type="settings", entity_id=None,
                  details={"chave": chave, "nome": it.nome, "de": de, "para": para,
                           "afrouxa": solta, "afirmacao": texto},
                  ip_address=ip)
    bd.escrever("""INSERT INTO settings (key, value) VALUES (%s, %s)
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                (chave, para))
    quem_nome = str(quem.get("full_name") or quem["username"])
    tarefa = _avisar_o_oficial(
        bd, ref=f"{ACAO_ALTERADA}:{chave}:{agora[:19]}",
        titulo=f"Configuração que cobra a equipe alterada: {it.nome}",
        descricao=(f"{agora[:16].replace('T', ' ')} — {quem_nome} mudou «{it.nome}» "
                   f"({chave}) de {_mostrar(de, it)} para {_mostrar(para, it)}"
                   + (" — AFROUXA a cobrança" if solta else "") + ".\n"
                   f"O que ela cobra: {it.cobra}.\nAfirmação: {texto}\n\n"
                   "Confira em Configurações → Configurações que cobram a equipe."),
        agora=agora)
    return {"mudou": True, "chave": chave, "de": de, "para": para,
            "afrouxa": solta, "tarefa_id": tarefa}


def registrar_recusa(con, *, chave: Any, valor: Any, usuario_id: Any,
                     motivo: str, mensagem: str, agora: str, ip: Any = None,
                     via: str = "tela") -> None:
    """A TENTATIVA recusada vai à auditoria — e, se é de quem é cobrado, à
    tarefa do oficial. ESCREVE, na transação de quem chama (que NÃO é a da
    tentativa: aquela foi desfeita)."""
    bd = banco(con)
    texto = normalizar_chave(chave)[:120]
    quem = _quem(bd, usuario_id)
    it = None
    try:
        it = item(texto)
    except ValorInvalido:
        pass
    de = _valor_atual(bd, texto) if it else None
    IDR.registrar(bd, ts=agora, user_id=quem["id"] if quem else None,
                  username=quem["username"] if quem else None,
                  action=ACAO_RECUSADA, entity_type="settings", entity_id=None,
                  details={"chave": texto, "de": de,
                           "para": str(valor if valor is not None else "")[:200],
                           "motivo": motivo, "mensagem": mensagem, "via": via},
                  ip_address=ip,
                  agente=None if quem else "tela das configurações que cobram a equipe",
                  a_mando_de=None if quem else IDR.PELO_RESPONSAVEL)
    if motivo not in MOTIVOS_QUE_AVISAM:
        return
    nome = (it.nome if it else texto) or "(sem chave)"
    pessoa = (str(quem.get("full_name") or quem.get("username")) if quem
              else "alguém sem login")
    _avisar_o_oficial(
        bd, ref=f"{ACAO_RECUSADA}:{texto}:{agora[:10]}",
        titulo=f"Tentativa recusada de mudar configuração que cobra a equipe: {nome}",
        descricao=(f"{agora[:16].replace('T', ' ')} — {pessoa} tentou mudar «{nome}» "
                   f"({texto}) de {_mostrar(de, it) if it else '—'} para "
                   f"«{str(valor if valor is not None else '')[:60]}». "
                   f"Recusado ({motivo}): {mensagem}"),
        agora=agora)


# --------------------------------------------------------------- a leitura

def quadro(con) -> dict:
    """O que a tela mostra: cada chave com o valor de agora, e os turnos. Só LÊ."""
    bd = banco(con)
    atuais = {}
    if bd.tem_tabela("settings"):
        for linha in bd.ler("SELECT key, value FROM settings WHERE key = ANY(%s) "
                            "OR key LIKE %s",
                            ([c.chave for c in CHAVES], PREFIXO_DO_TURNO + "%")):
            atuais[str(linha["key"])] = str(linha["value"])
    chaves = []
    for c in CHAVES:
        valor = atuais.get(c.chave)
        chaves.append({"chave": c.chave, "nome": c.nome, "tipo": c.tipo,
                       "valor": valor, "padrao": c.padrao,
                       "vale": valor if valor not in (None, "") else c.padrao,
                       "cobra": c.cobra, "afrouxar": c.afrouxar,
                       "opcoes": list(c.opcoes)})
    robo = "COALESCE(eh_robo, 0)" if bd.tem_coluna("users", "eh_robo") else "0"
    turnos = []
    for u in bd.ler(f"""SELECT id, username, full_name, role FROM users
                         WHERE active = 1 AND {robo} = 0 ORDER BY full_name, id"""):
        chave = chave_do_turno(u["username"])
        turnos.append({"id": int(u["id"]), "login": str(u["username"]).casefold(),
                       "nome": u["full_name"] or u["username"], "papel": u["role"],
                       "chave": chave, "turno": atuais.get(chave) or ""})
    return {"chaves": chaves, "turnos": turnos, "fora": list(FORA_DESTA_LEVA),
            "fim_do_expediente": atuais.get(CA.CHAVE_FIM) or CA.FIM_PADRAO,
            "regra_da_afirmacao": regra_da_afirmacao()}


def _detalhes(texto: Any) -> dict:
    try:
        lido = json.loads(texto or "{}")
    except (TypeError, ValueError):
        return {}
    return lido if isinstance(lido, dict) else {}


def _o_que(acao: str) -> str:
    if acao == ACAO_ALTERADA:
        return "ALTERADA"
    if acao == ACAO_RECUSADA:
        return "RECUSADA"
    return "POR_FORA"


def historico(con, *, hoje: str, dias: Any = None) -> dict:
    """Quem mudou cada chave de cobrança, quando, de quê para quê e a mando
    de quem — da mais nova para a mais antiga. Só LÊ.

    Entram as linhas desta guarda (alterada, recusada) e as de ANTES dela, que
    scripts e robôs gravaram à mão com nomes diversos (`SETTING_ALTERADO`,
    `RI_CIB_DISPENSADO`…): o que as une é a chave no JSON — `chave` ou `key`,
    `de`/`antes`, `para`/`depois`. A afirmação expressa não entra como linha à
    parte: o texto dela já vai na linha da alteração.
    """
    bd = banco(con)
    try:
        dias = max(1, min(3650, int(dias)))
    except (TypeError, ValueError):
        dias = DIAS_DO_HISTORICO
    desde = (date.fromisoformat(str(hoje)[:10]) - timedelta(days=dias)).isoformat()
    saida = {"desde": desde, "dias": dias, "linhas": [], "cortado": False,
             "medido": False}
    if not bd.tem_tabela("audit_logs"):
        return saida
    saida["medido"] = True
    padroes = [f'%"{c.chave}"%' for c in CHAVES] + [f'%"{PREFIXO_DO_TURNO}%']
    filtro = " OR ".join(["details LIKE %s"] * len(padroes))
    extra = ", agente, a_mando_de" if bd.tem_coluna("audit_logs", "a_mando_de") else ""
    lidas = bd.ler(
        f"""SELECT id, ts, user_id, username_snapshot, action, details{extra}
              FROM audit_logs
             WHERE ts >= %s AND action <> %s AND ({filtro})
             ORDER BY id DESC LIMIT %s""",
        (desde, ACAO_AFIRMACAO, *padroes, LIMITE_DO_HISTORICO + 1))
    saida["cortado"] = len(lidas) > LIMITE_DO_HISTORICO
    for linha in lidas[:LIMITE_DO_HISTORICO]:
        d = _detalhes(linha["details"])
        chave = d.get("chave", d.get("key"))
        if e_chave_de_cobranca(chave):
            pares = [(chave, d.get("de", d.get("antes")), d.get("para", d.get("depois")))]
        else:
            # O formulário geral grava o dicionário inteiro {chave: valor}.
            pares = [(k, None, v) for k, v in d.items() if e_chave_de_cobranca(k)]
        for k, de, para in pares:
            it = item(k)
            saida["linhas"].append({
                "id": linha["id"], "ts": str(linha["ts"] or ""),
                "quem": linha["username_snapshot"] or "—",
                "agente": (linha.get("agente") if extra else None) or "",
                "a_mando_de": (linha.get("a_mando_de") if extra else None) or "",
                "chave": k, "nome": it.nome,
                "de": "" if de is None else str(de),
                "para": "" if para is None else str(para),
                "o_que": _o_que(str(linha["action"])),
                "acao": str(linha["action"]),
                "afrouxa": d.get("afrouxa") if "afrouxa" in d else afrouxa(it, de, para),
                "motivo": str(d.get("motivo") or d.get("mensagem") or ""),
                "afirmacao": str(d.get("afirmacao") or "")})
    return saida


# --------------------------------------------------------------- o gatilho

def _literal(texto: str) -> str:
    if not _IDENTIFICADOR.match(texto):
        raise ValueError(f"chave fora do formato de identificador: {texto!r}")
    return f"'{texto}'"


def corpo_do_gatilho() -> str:
    """O corpo PL/pgSQL do gatilho. Só calcula — e é a lista de `CHAVES`
    escrita dentro dele, para a regra do banco e a do Python serem a mesma.

    `TG_TABLE_SCHEMA` e não nome fixo: a função mora no schema da casa
    (produção, sandbox, o de cada teste), e cada um tem a sua.
    """
    lista = ", ".join(_literal(c.chave) for c in CHAVES)
    prefixo = _literal(PREFIXO_DO_TURNO)
    acao = _literal(ACAO_ALTERADA)
    return f"""
DECLARE
  k text;
  novo text;
  velho text;
  existe boolean;
  aprovada jsonb;
  quem bigint;
  agente text;
  pessoa boolean;
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.key IS DISTINCT FROM OLD.key
     AND (OLD.key = ANY (ARRAY[{lista}]::text[]) OR starts_with(OLD.key, {prefixo})
          OR NEW.key = ANY (ARRAY[{lista}]::text[]) OR starts_with(NEW.key, {prefixo})) THEN
    RAISE EXCEPTION 'Chave de cobrança «%» não se renomeia.', OLD.key;
  END IF;
  IF TG_OP = 'DELETE' THEN
    k := OLD.key; novo := NULL; velho := OLD.value; existe := true;
  ELSE
    k := NEW.key; novo := NEW.value;
  END IF;
  IF NOT (k = ANY (ARRAY[{lista}]::text[]) OR starts_with(k, {prefixo})) THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'UPDATE' THEN
    velho := OLD.value; existe := true;
  ELSIF TG_OP = 'INSERT' THEN
    EXECUTE format('SELECT value, true FROM %I.settings WHERE key = $1', TG_TABLE_SCHEMA)
       INTO velho, existe USING k;
    existe := coalesce(existe, false);
  END IF;
  IF TG_OP <> 'DELETE' AND existe AND velho IS NOT DISTINCT FROM novo THEN
    RETURN NEW;
  END IF;
  EXECUTE format($q$SELECT a.user_id, a.details::jsonb, to_jsonb(a) ->> 'agente'
                      FROM %I.audit_logs a
                     WHERE a.action = {acao}
                       AND (CASE WHEN a.action = {acao}
                                 THEN a.details::jsonb ->> 'chave' END) = $1
                     ORDER BY a.id DESC LIMIT 1$q$, TG_TABLE_SCHEMA)
     INTO quem, aprovada, agente USING k;
  pessoa := false;
  IF quem IS NOT NULL AND agente IS NULL
     AND (aprovada ->> 'para') IS NOT DISTINCT FROM novo THEN
    EXECUTE format($q$SELECT EXISTS (SELECT 1 FROM %I.users u
                       WHERE u.id = $1 AND u.role = 'ADMIN' AND u.active = 1
                         AND coalesce(to_jsonb(u) ->> 'eh_robo', '0') = '0')$q$,
                   TG_TABLE_SCHEMA)
       INTO pessoa USING quem;
  END IF;
  IF NOT coalesce(pessoa, false) THEN
    RAISE EXCEPTION 'Chave de cobrança «%»: só o oficial (ADMIN) a altera, na tela Configurações que cobram a equipe, com afirmação expressa. Robô nunca altera, nem a pedido de alguém. Peça ao oficial.', k
      USING HINT = 'Mudança gravada direto no banco (script, ferramenta ou robô) é recusada pelo gatilho settings_cobranca.';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END
"""


def _sql_da_funcao() -> str:
    return (f"CREATE OR REPLACE FUNCTION {NOME_DA_FUNCAO}() RETURNS trigger "
            f"LANGUAGE plpgsql AS $f${corpo_do_gatilho()}$f$")


SQL_DO_GATILHO = (f"CREATE OR REPLACE TRIGGER {NOME_DO_GATILHO} "
                  f"BEFORE INSERT OR UPDATE OR DELETE ON settings "
                  f"FOR EACH ROW EXECUTE FUNCTION {NOME_DA_FUNCAO}()")


def instalar_gatilho(con) -> list[str]:
    """Arma o gatilho no schema da casa. ESCREVE (DDL). Idempotente.

    Só recria o que mudou: a função quando o corpo difere (a lista mudou de
    versão), o gatilho quando falta, e o RELIGA quando alguém o desligou —
    o servidor que sobe rearma a guarda. Devolve os comandos que rodou.

    `_cru`, como o gatilho da corrente da auditoria (`database.init_schema`):
    o DDL vai direto, e a anotação na gravação do banco novo vai à mão —
    senão os schemas reproduzidos (a suíte em paralelo) nasceriam sem ele.
    """
    bd = banco(con)
    if not (bd.tem_tabela("settings") and bd.tem_tabela("audit_logs")
            and bd.tem_tabela("users")):
        return []
    corpo = corpo_do_gatilho()
    atual = bd.valor(
        """SELECT p.prosrc FROM pg_proc p
             JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = current_schema() AND p.proname = %s""",
        (NOME_DA_FUNCAO,))
    comandos = []
    if atual != corpo:
        comandos.append(_sql_da_funcao())
    gatilho = bd.um(
        """SELECT t.tgenabled::text AS ligado FROM pg_trigger t
             JOIN pg_class c ON c.oid = t.tgrelid
             JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema() AND c.relname = 'settings'
              AND t.tgname = %s""", (NOME_DO_GATILHO,))
    if gatilho is None:
        comandos.append(SQL_DO_GATILHO)
    elif str(gatilho["ligado"]) == "D":
        comandos.append(f"ALTER TABLE settings ENABLE TRIGGER {NOME_DO_GATILHO}")
    for sql in comandos:
        bd._cru(sql)
        if getattr(bd, "_ponte", None) is not None:
            bd._ponte._anotar(None, sql, None)
    return comandos
