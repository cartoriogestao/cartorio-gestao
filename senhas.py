# -*- coding: utf-8 -*-
"""O PAINEL DE SENHAS e a medição do tempo de espera (26/10/2026).

O QUE JÁ EXISTIA
    A tabela `service_tickets` (chegada, chamada, início, fim, atendente,
    prioridade), a tela `/atendimento` e as métricas do dia no bloco
    «Atendimento de hoje» de `/relatorios`. Faltava o que faz a fila funcionar
    na recepção — a TV, o papel da senha, o guichê — e a régua do período para
    o gestor.

O QUE ESTE MÓDULO ACRESCENTA
    - o GUICHÊ de quem chama, guardado por usuário (`senha_guiches`) e
      gravado na senha no momento da chamada (`service_tickets.guiche`);
    - o RECHAMAR (a chamada repetida conta, e a TV volta a anunciar) e a
      DESISTÊNCIA (chamada sem resposta, ou quem foi embora da fila);
    - a LIGAÇÃO OPCIONAL da senha ao protocolo geral (`cx_protocolos`),
      quando o atendimento vira protocolo;
    - o ESTADO DA TV, que só leva senha e guichê — nunca nome, tipo de
      serviço nem atendente;
    - as MÉTRICAS DO PERÍODO, por atendente, por tipo e por prioridade. São a
      MESMA régua das de hoje (`Database.service_metrics_today` chama esta):
      duas réguas para a mesma pergunta divergem no primeiro conserto.

A RÉGUA DO TEMPO
    espera       = chegada → PRIMEIRA chamada (`called_at`). A senha que foi
                   atendida sem chamada registrada (linha de antes de
                   26/10/2026, quando «Iniciar» podia vir direto) usa o início.
                   Até 26/10/2026 a espera de `/relatorios` ia até o INÍCIO do
                   atendimento, e somava o caminho da cadeira ao guichê; a
                   pergunta do gestor é quanto tempo a pessoa ficou esperando
                   ser chamada.
    atendimento  = início → fim.
    Data e hora se calculam em Python, e não no SQL (regra da casa — ver
    `database._segundos`).

A CHAVE DA TV
    A TV da recepção não entra com login: a sessão da casa tem prazo absoluto
    (`prazo_absoluto_horas`) e cai por inatividade, e uma TV não digita senha.
    Ela abre um endereço com uma chave longa e aleatória, que o ADMIN gera e
    troca na tela «Painel da TV». A chave é segredo e mora no COFRE
    (`senhas.cred`), e não no banco — regra da casa. O que a chave abre é só
    senha e guichê: quem a tiver não vê nome, documento, tipo de serviço nem
    quem atende.
"""
from __future__ import annotations

import re
import secrets
from datetime import date, datetime
from typing import Any

from bd_nativo import banco

# ------------------------------------------------------------------ o esquema

SCHEMA = """
CREATE TABLE IF NOT EXISTS senha_guiches (
    -- O GUICHÊ (ou a mesa) DE CADA ATENDENTE. Um por usuário: quem troca de
    -- mesa troca aqui, e a próxima chamada já sai com o número novo.
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    guiche TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
"""

# COLUNAS NOVAS EM `service_tickets` — a tabela nasce em `database.init` e já
# existe na produção; `CREATE TABLE IF NOT EXISTS` não acrescenta coluna, e é
# `ALTER TABLE ADD COLUMN` que resolve. Aditivo, no padrão da casa.
MIGRACOES: tuple[tuple[str, str, str], ...] = (
    # O guichê em que a senha foi chamada — gravado na chamada, e não lido do
    # cadastro depois: quem muda de mesa amanhã não reescreve o histórico.
    ("service_tickets", "guiche", "TEXT"),
    # Quantas vezes foi chamada, e a última: o RECHAMAR volta a anunciar na
    # TV, e a ordem das «últimas chamadas» é a da última chamada.
    ("service_tickets", "chamadas", "INTEGER NOT NULL DEFAULT 0"),
    ("service_tickets", "ultima_chamada_em", "TEXT"),
    # A DESISTÊNCIA — chamada sem resposta, ou a pessoa foi embora.
    ("service_tickets", "desistiu_em", "TEXT"),
    # A LIGAÇÃO OPCIONAL AO PROTOCOLO GERAL. Sem chave estrangeira de
    # propósito: `service_tickets` nasce antes de `cx_protocolos` na abertura
    # do banco, e a ligação é conferida por quem grava (`ligar_protocolo`).
    ("service_tickets", "protocolo_id", "INTEGER"),
    ("service_tickets", "protocolo_ligado_em", "TEXT"),
    ("service_tickets", "protocolo_ligado_por", "INTEGER"),
)

# ÍNDICE SOBRE COLUNA DE MIGRAÇÃO VAI AQUI, e não no `SCHEMA` — num banco que
# já existe a coluna só aparece no `ALTER TABLE`, e o `CREATE INDEX` estoura ao
# abrir. É o defeito que o oficial cometeu duas vezes em 25/08/2026.
INDICES_DEPOIS_DA_MIGRACAO: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_ticket_ultima_chamada "
    "ON service_tickets(ticket_date, ultima_chamada_em)",
    "CREATE INDEX IF NOT EXISTS idx_ticket_protocolo "
    "ON service_tickets(protocolo_id)",
)


def init_senhas_schema(con) -> None:
    """Cria a tabela dos guichês, as colunas novas da senha e os índices.
    Idempotente."""
    bd = banco(con)
    for comando in re.split(r";[ \t]*\n", SCHEMA):
        if re.sub(r"--[^\n]*", "", comando).strip():
            bd.escrever(comando)
    for tabela, coluna, tipo in MIGRACOES:
        if not bd.tem_coluna(tabela, coluna):
            bd.escrever(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    for comando in INDICES_DEPOIS_DA_MIGRACAO:
        bd.escrever(comando)


# ------------------------------------------------------------------ as palavras

AGUARDANDO = "AGUARDANDO"
CHAMADO = "CHAMADO"
EM_ATENDIMENTO = "EM_ATENDIMENTO"
FINALIZADO = "FINALIZADO"
DESISTIU = "DESISTIU"

NOME_DA_SITUACAO = {
    AGUARDANDO: "Aguardando",
    CHAMADO: "Chamada",
    EM_ATENDIMENTO: "Em atendimento",
    FINALIZADO: "Atendida",
    DESISTIU: "Desistiu",
}

#: As ações que a tela manda. Os nomes em inglês são os da rota antiga
#: (`/atendimento/<id>/call`), que fica de pé para quem a tem nos favoritos.
ACOES = ("call", "recall", "start", "finish", "giveup")

#: OS TIPOS DE ATENDIMENTO DE FÁBRICA — o oficial troca a lista na tela
#: «Painel da TV» (configuração `senhas_tipos_de_atendimento`, um por linha).
#: O tipo é o que agrupa o relatório do período; escrito à mão, «Certidão»,
#: «certidao» e «Certidões» seriam três linhas da mesma coisa.
#:
#: UMA ENTRADA POR ATRIBUIÇÃO DA CASA — decisão do oficial em 26/10/2026,
#: «tipos: todas as atribuições». Os nomes saem de `atribuicoes.ATRIBUICOES`
#: (o vocabulário gerado do acervo), e não são escritos de novo aqui: a
#: primeira versão tinha «Títulos e Documentos / Pessoa Jurídica» numa linha
#: só, e o oficial pediu RTD e RCPJ separados. `ORDEM_DAS_ATRIBUICOES` é só a
#: ordem do balcão, a que o oficial ditou; atribuição que entrar no
#: vocabulário e não estiver nela vai para o fim, e não some da lista.
#: Em volta ficam os tipos genéricos que já existiam (o geral, a certidão, a
#: retirada e o caixa).
ORDEM_DAS_ATRIBUICOES: tuple[str, ...] = ("NOTAS", "RI", "RCPN", "RTD", "RCPJ", "PROTESTO")
TIPOS_GENERICOS_ANTES: tuple[str, ...] = ("Geral",)
TIPOS_GENERICOS_DEPOIS: tuple[str, ...] = (
    "Certidão",
    "Retirada de documento",
    "Pagamento / caixa",
)


def tipos_das_atribuicoes() -> tuple[str, ...]:
    """Um tipo por atribuição, com o nome do vocabulário da casa. Só LÊ."""
    import atribuicoes as ATR
    por_sigla = {a["sigla"]: a["nome"] for a in ATR.ATRIBUICOES.values()}
    siglas = [s for s in ORDEM_DAS_ATRIBUICOES if s in por_sigla]
    siglas += [s for s in por_sigla if s not in siglas]
    return tuple(por_sigla[s] for s in siglas)


TIPOS_DE_FABRICA: tuple[str, ...] = (
    TIPOS_GENERICOS_ANTES + tipos_das_atribuicoes() + TIPOS_GENERICOS_DEPOIS)

CHAVE_DOS_TIPOS = "senhas_tipos_de_atendimento"

#: Teto do guichê digitado: é o que aparece grande na TV.
TAMANHO_DO_GUICHE = 12


class SenhaError(ValueError):
    """A ação não se faz, com a frase pronta para o balcão."""


def tipos_de_atendimento(get_setting) -> list[str]:
    """Os tipos que a tela oferece. Só LÊ."""
    bruto = str(get_setting(CHAVE_DOS_TIPOS, "") or "")
    tipos = []
    for linha in bruto.splitlines():
        t = " ".join(linha.split())[:60]
        if t and t not in tipos:
            tipos.append(t)
    return tipos or list(TIPOS_DE_FABRICA)


def rotulo(ticket: dict) -> str:
    """A senha como sai no papel e na TV: `P012` (preferencial) ou `N012`.

    A numeração é UMA só no dia — a letra diz a fila, o número diz a ordem de
    chegada. É o que se lê em voz alta e o que a pessoa confere no papel.
    O formato foi confirmado pelo oficial em 26/10/2026 («P001/N001: mantém»).
    """
    letra = "P" if int(ticket.get("priority") or 0) else "N"
    return f"{letra}{int(ticket.get('ticket_no') or 0):03d}"


def _segundos(inicio: Any, fim: Any) -> float | None:
    """`fim - inicio` em segundos, das horas ISO gravadas — a mesma conta de
    `database._segundos` (não importada de lá: `database` importa este
    módulo). Hora que não se lê não entra na média."""
    try:
        s = (datetime.fromisoformat(str(fim)) - datetime.fromisoformat(str(inicio))).total_seconds()
    except (TypeError, ValueError):
        return None
    return s if s >= 0 else None


def _espera(r: dict) -> float | None:
    """Chegada até a primeira chamada (ver «A RÉGUA DO TEMPO» acima)."""
    fim = r.get("called_at") or r.get("started_at")
    return _segundos(r.get("created_at"), fim) if fim else None


def _atendimento(r: dict) -> float | None:
    if not r.get("started_at") or not r.get("finished_at"):
        return None
    return _segundos(r.get("started_at"), r.get("finished_at"))


def _media(valores: list[float]) -> float:
    return sum(valores) / len(valores) if valores else 0.0


# ------------------------------------------------------------------ o guichê

def guiche_de(con, user_id: int | None) -> str:
    """O guichê gravado deste atendente, ou "". Só LÊ."""
    if not user_id:
        return ""
    r = banco(con).um("SELECT guiche FROM senha_guiches WHERE user_id = %s", (int(user_id),))
    return str(r["guiche"]) if r else ""


def gravar_guiche(con, user_id: int, guiche: str, *, agora: str) -> str:
    """Grava o guichê (ou a mesa) deste atendente. ESCREVE."""
    texto = " ".join(str(guiche or "").split())
    if not texto:
        raise SenhaError("Informe o número do seu guichê ou da sua mesa.")
    if len(texto) > TAMANHO_DO_GUICHE:
        raise SenhaError(f"O guichê aparece grande na TV: use até {TAMANHO_DO_GUICHE} "
                         "caracteres (por exemplo «2» ou «Mesa 3»).")
    banco(con).escrever(
        """INSERT INTO senha_guiches (user_id, guiche, atualizado_em) VALUES (%s, %s, %s)
           ON CONFLICT (user_id) DO UPDATE
              SET guiche = EXCLUDED.guiche, atualizado_em = EXCLUDED.atualizado_em""",
        (int(user_id), texto, agora))
    return texto


# ------------------------------------------------------------------ a fila

def emitir(con, *, preferencial: bool, tipo: str | None, agora: str,
           dia: str | None = None) -> dict:
    """Emite a senha seguinte do dia. ESCREVE.

    A numeração é por dia e única (`UNIQUE(ticket_date, ticket_no)`); a trava
    impede duas recepções de tirarem o mesmo número ao mesmo tempo.
    """
    d = dia or str(agora)[:10]
    bd = banco(con)
    bd.travar("service_tickets.ticket_no")
    maior = bd.valor("SELECT MAX(ticket_no) AS maior FROM service_tickets WHERE ticket_date = %s", (d,))
    numero = int(maior or 0) + 1
    t = " ".join(str(tipo or "").split())[:60] or None
    novo = bd.escrever(
        """INSERT INTO service_tickets (ticket_no, ticket_date, priority, service_type,
                                        status, created_at, chamadas)
           VALUES (%s, %s, %s, %s, 'AGUARDANDO', %s, 0) RETURNING id""",
        (numero, d, 1 if preferencial else 0, t, agora))
    return {"id": int(novo[0]["id"]), "ticket_no": numero, "priority": 1 if preferencial else 0,
            "senha": rotulo({"ticket_no": numero, "priority": 1 if preferencial else 0})}


def senha(con, ticket_id: int) -> dict | None:
    """Uma senha, com o número do protocolo ligado. Só LÊ."""
    r = banco(con).um(
        """SELECT s.*, u.full_name AS attendant_name, p.numero AS protocolo_numero
             FROM service_tickets s
             LEFT JOIN users u ON u.id = s.attendant_user_id
             LEFT JOIN cx_protocolos p ON p.id = s.protocolo_id
            WHERE s.id = %s""", (int(ticket_id),))
    if r:
        r["senha"] = rotulo(r)
    return r


def ordem_de_chamada(con, dia: str) -> list[int]:
    """Os ids das senhas AGUARDANDO na ordem em que `chamar_proxima` as
    chamaria hoje, alternando preferencial e normal. Só LÊ.

    É a mesma régua de `chamar_proxima`, simulada até o fim da fila — o
    número do papel e a ordem da tela não podem dizer outra coisa que o
    botão faz.
    """
    bd = banco(con)
    ultima = bd.um(
        """SELECT priority FROM service_tickets
            WHERE ticket_date = %s AND called_at IS NOT NULL
            ORDER BY called_at DESC, id DESC LIMIT 1""", (dia,))
    esperando = bd.ler(
        """SELECT id, priority FROM service_tickets
            WHERE ticket_date = %s AND status = 'AGUARDANDO' ORDER BY ticket_no""", (dia,))
    pref = [int(r["id"]) for r in esperando if int(r["priority"] or 0)]
    norm = [int(r["id"]) for r in esperando if not int(r["priority"] or 0)]
    a_vez = 0 if ultima and int(ultima["priority"] or 0) else 1
    ordem: list[int] = []
    while pref or norm:
        lado = pref if (a_vez == 1 and pref) or not norm else norm
        ordem.append(lado.pop(0))
        a_vez = 0 if lado is pref else 1
    return ordem


def a_frente(con, ticket: dict) -> int:
    """Quantas senhas AGUARDANDO serão chamadas antes desta, pela ordem de
    `chamar_proxima`. Só LÊ — é o número que sai no papel."""
    if ticket.get("status") != AGUARDANDO:
        return 0
    ordem = ordem_de_chamada(con, ticket["ticket_date"])
    tid = int(ticket["id"])
    return ordem.index(tid) if tid in ordem else 0


def fila_do_dia(con, dia: str) -> list[dict]:
    """As senhas do dia, na ordem do balcão: chamadas e em atendimento no
    alto, depois a fila na ordem em que serão chamadas (preferencial e normal
    alternadas, `ordem_de_chamada`), depois as encerradas. Só LÊ."""
    linhas = banco(con).ler(
        """SELECT s.*, u.full_name AS attendant_name, p.numero AS protocolo_numero
             FROM service_tickets s
             LEFT JOIN users u ON u.id = s.attendant_user_id
             LEFT JOIN cx_protocolos p ON p.id = s.protocolo_id
            WHERE s.ticket_date = %s
            ORDER BY CASE s.status WHEN 'CHAMADO' THEN 0 WHEN 'EM_ATENDIMENTO' THEN 1
                                   WHEN 'AGUARDANDO' THEN 2 ELSE 3 END,
                     s.ticket_no""", (dia,))
    posicao = {tid: i for i, tid in enumerate(ordem_de_chamada(con, dia))}
    linhas.sort(key=lambda r: (
        {"CHAMADO": 0, "EM_ATENDIMENTO": 1, "AGUARDANDO": 2}.get(r["status"], 3),
        posicao.get(int(r["id"]), 0) if r["status"] == AGUARDANDO else 0))
    for r in linhas:
        r["senha"] = rotulo(r)
        r["situacao"] = NOME_DA_SITUACAO.get(r["status"], r["status"])
        r["espera_seg"] = _espera(r)
        r["atendimento_seg"] = _atendimento(r)
    return linhas


def _chamar(bd, ticket_id: int, *, user_id: int, guiche: str, agora: str,
            de: tuple[str, ...]) -> dict | None:
    marcas = ",".join(["%s"] * len(de))
    feito = bd.escrever(
        f"""UPDATE service_tickets
               SET status = 'CHAMADO', called_at = COALESCE(called_at, %s),
                   ultima_chamada_em = %s, chamadas = COALESCE(chamadas, 0) + 1,
                   guiche = %s, attendant_user_id = %s
             WHERE id = %s AND status IN ({marcas})
         RETURNING id, ticket_no, priority""",
        (agora, agora, guiche, user_id, int(ticket_id), *de))
    return feito[0] if feito else None


def agir(con, ticket_id: int, acao: str, *, user_id: int, agora: str) -> dict:
    """Chama, rechama, inicia, finaliza ou marca a desistência. ESCREVE.

    Cada ação só vale a partir da situação certa — duas pessoas clicando na
    mesma senha ao mesmo tempo não a chamam duas vezes nem «finalizam» o que
    ninguém começou. A recusa vem com a frase do balcão.
    """
    bd = banco(con)
    atual = bd.um("SELECT * FROM service_tickets WHERE id = %s", (int(ticket_id),))
    if not atual:
        raise SenhaError("Senha não encontrada.")
    nome = rotulo(atual)
    if acao in ("call", "recall"):
        guiche = guiche_de(con, user_id)
        if not guiche:
            raise SenhaError("Informe o seu guichê (ou mesa) no alto da tela antes de chamar: "
                             "é ele que aparece na TV da recepção.")
        de = (AGUARDANDO,) if acao == "call" else (CHAMADO,)
        if not _chamar(bd, ticket_id, user_id=user_id, guiche=guiche, agora=agora, de=de):
            raise SenhaError(f"A senha {nome} não está mais aguardando — outra pessoa pode "
                             "tê-la chamado. A lista foi atualizada.")
        return {"senha": nome, "guiche": guiche}
    if acao == "start":
        feito = bd.escrever(
            """UPDATE service_tickets SET status = 'EM_ATENDIMENTO',
                      started_at = COALESCE(started_at, %s), attendant_user_id = %s
                WHERE id = %s AND status = 'CHAMADO' RETURNING id""",
            (agora, user_id, int(ticket_id)))
    elif acao == "finish":
        feito = bd.escrever(
            """UPDATE service_tickets SET status = 'FINALIZADO', finished_at = %s,
                      attendant_user_id = %s
                WHERE id = %s AND status = 'EM_ATENDIMENTO' RETURNING id""",
            (agora, user_id, int(ticket_id)))
    elif acao == "giveup":
        feito = bd.escrever(
            """UPDATE service_tickets SET status = 'DESISTIU', desistiu_em = %s,
                      attendant_user_id = %s
                WHERE id = %s AND status IN ('AGUARDANDO', 'CHAMADO') RETURNING id""",
            (agora, user_id, int(ticket_id)))
    else:
        raise SenhaError("Ação desconhecida.")
    if not feito:
        raise SenhaError(f"A senha {nome} está «{NOME_DA_SITUACAO.get(atual['status'], atual['status'])}»"
                         " e não aceita esta ação. A lista foi atualizada.")
    return {"senha": nome}


def chamar_proxima(con, *, user_id: int, agora: str, dia: str) -> dict | None:
    """Chama a próxima da fila, ALTERNANDO preferencial e normal. ESCREVE.
    None quando a fila está vazia.

    Decisão do oficial em 26/10/2026: «preferencial alternada». A régua é a
    última senha chamada no dia, em qualquer guichê: se ela foi preferencial,
    vem agora a normal mais antiga; se foi normal (ou é a primeira do dia),
    vem a preferencial mais antiga. Quando o lado da vez não tem ninguém
    esperando, chama-se o outro: a fila nunca fica parada por causa da regra.
    A tela continua deixando chamar qualquer senha pelo botão da linha.
    """
    guiche = guiche_de(con, user_id)
    if not guiche:
        raise SenhaError("Informe o seu guichê (ou mesa) no alto da tela antes de chamar: "
                         "é ele que aparece na TV da recepção.")
    bd = banco(con)
    bd.travar("service_tickets.chamada")
    for _ in range(3):
        ultima = bd.um(
            """SELECT priority FROM service_tickets
                WHERE ticket_date = %s AND called_at IS NOT NULL
                ORDER BY called_at DESC, id DESC LIMIT 1""", (dia,))
        a_vez = 0 if ultima and int(ultima["priority"] or 0) else 1
        prox = bd.um(
            """SELECT id FROM service_tickets
                WHERE ticket_date = %s AND status = 'AGUARDANDO'
                ORDER BY CASE WHEN priority = %s THEN 0 ELSE 1 END, ticket_no
                LIMIT 1""", (dia, a_vez))
        if not prox:
            return None
        feito = _chamar(bd, prox["id"], user_id=user_id, guiche=guiche, agora=agora,
                        de=(AGUARDANDO,))
        if feito:
            return {"id": int(feito["id"]), "senha": rotulo(feito), "guiche": guiche}
    return None


# ------------------------------------------------------------------ o protocolo

def ligar_protocolo(con, ticket_id: int, protocolo: Any, *, user_id: int,
                    agora: str) -> dict:
    """Liga a senha ao protocolo geral (`cx_protocolos`). ESCREVE.

    `protocolo` é o número do balcão (`2026.10.15`) ou o id. Opcional: a
    senha que não virou protocolo (uma informação, uma retirada) fica sem.
    """
    bd = banco(con)
    if not bd.um("SELECT id FROM service_tickets WHERE id = %s", (int(ticket_id),)):
        raise SenhaError("Senha não encontrada.")
    bruto = str(protocolo or "").strip()
    if not bruto:
        raise SenhaError("Digite o número do protocolo (ano.mês.número).")
    p = bd.um("SELECT id, numero FROM cx_protocolos WHERE numero = %s ORDER BY id LIMIT 1",
              (bruto,))
    if not p and bruto.isascii() and bruto.isdigit() and len(bruto) < 18:
        p = bd.um("SELECT id, numero FROM cx_protocolos WHERE id = %s", (int(bruto),))
    if not p:
        raise SenhaError(f"Não achei o protocolo «{bruto}». Confira o número no papel do "
                         "balcão (ano.mês.número).")
    bd.escrever(
        """UPDATE service_tickets SET protocolo_id = %s, protocolo_ligado_em = %s,
                  protocolo_ligado_por = %s WHERE id = %s""",
        (int(p["id"]), agora, int(user_id), int(ticket_id)))
    return {"protocolo_id": int(p["id"]), "numero": p["numero"]}


def desligar_protocolo(con, ticket_id: int) -> None:
    """Tira a ligação feita por engano. ESCREVE."""
    banco(con).escrever(
        """UPDATE service_tickets SET protocolo_id = NULL, protocolo_ligado_em = NULL,
                  protocolo_ligado_por = NULL WHERE id = %s""", (int(ticket_id),))


# ------------------------------------------------------------------ a TV

def estado_do_painel(con, dia: str, limite: int = 6) -> dict:
    """O que a TV mostra: a chamada atual e as últimas. Só LÊ.

    **SÓ SENHA E GUICHÊ.** A consulta não traz nome, tipo, atendente nem id —
    o que não sai do banco não vaza da TV. A `marca` muda a cada chamada (e a
    cada rechamada), e é por ela que a TV sabe quando tocar o aviso.
    """
    linhas = banco(con).ler(
        """SELECT ticket_no, priority, guiche, ultima_chamada_em, chamadas
             FROM service_tickets
            WHERE ticket_date = %s AND ultima_chamada_em IS NOT NULL
              AND status IN ('CHAMADO', 'EM_ATENDIMENTO', 'FINALIZADO')
            ORDER BY ultima_chamada_em DESC, ticket_no DESC
            LIMIT %s""", (dia, int(limite) + 1))
    itens = [{"senha": rotulo(r), "guiche": str(r["guiche"] or ""),
              "marca": f"{rotulo(r)}|{r['guiche'] or ''}|{r['ultima_chamada_em']}|{r['chamadas'] or 0}"}
             for r in linhas]
    return {"atual": itens[0] if itens else None, "ultimas": itens[1:limite + 1]}


def gerar_chave() -> str:
    """Uma chave nova para o endereço da TV — 256 bits, só calcula."""
    return secrets.token_urlsafe(32)


def chave_confere(guardada: str, recebida: str) -> bool:
    """Compara em tempo constante. Chave vazia nunca confere."""
    g, r = str(guardada or ""), str(recebida or "")
    return bool(g) and bool(r) and secrets.compare_digest(g, r)


# ------------------------------------------------------------------ o período

def _linhas_do_periodo(bd, inicio: str, fim: str, atendente_id: int | None = None) -> list[dict]:
    sql = ("""SELECT s.*, u.full_name AS attendant_name, p.numero AS protocolo_numero
                FROM service_tickets s
                LEFT JOIN users u ON u.id = s.attendant_user_id
                LEFT JOIN cx_protocolos p ON p.id = s.protocolo_id
               WHERE s.ticket_date BETWEEN %s AND %s""")
    params: list[Any] = [inicio, fim]
    if atendente_id:
        sql += " AND s.attendant_user_id = %s"
        params.append(int(atendente_id))
    sql += " ORDER BY s.ticket_date, s.ticket_no"
    return banco(bd).ler(sql, tuple(params))


def _resumo(linhas: list[dict], hoje: str) -> dict:
    esperas = [s for s in (_espera(r) for r in linhas) if s is not None]
    atend = [s for s in (_atendimento(r) for r in linhas) if s is not None]
    # FICOU SEM ATENDIMENTO: de dia que já passou, e não foi finalizada nem
    # marcada como desistência. A de hoje ainda está na fila.
    sem = sum(1 for r in linhas if r["ticket_date"] < hoje
              and r["status"] in (AGUARDANDO, CHAMADO, EM_ATENDIMENTO))
    return {
        "total": len(linhas),
        "preferenciais": sum(1 for r in linhas if int(r.get("priority") or 0)),
        "atendidas": sum(1 for r in linhas if r["status"] == FINALIZADO),
        "desistencias": sum(1 for r in linhas if r["status"] == DESISTIU),
        "sem_atendimento": sem,
        "na_fila": sum(1 for r in linhas if r["ticket_date"] == hoje and r["status"] == AGUARDANDO),
        "espera_media": _media(esperas),
        "espera_maior": max(esperas) if esperas else 0.0,
        "atendimento_medio": _media(atend),
        "com_protocolo": sum(1 for r in linhas if r.get("protocolo_id")),
    }


def _agrupar(linhas: list[dict], chave, hoje: str) -> list[dict]:
    grupos: dict[str, list[dict]] = {}
    for r in linhas:
        grupos.setdefault(chave(r), []).append(r)
    saida = [{"nome": nome, **_resumo(rs, hoje)} for nome, rs in grupos.items()]
    saida.sort(key=lambda g: (-g["total"], g["nome"]))
    return saida


def metricas(con, inicio: str, fim: str, *, hoje: str | None = None,
             atendente_id: int | None = None) -> dict:
    """Os números do período (datas ISO, as duas inclusive). Só LÊ.

    Por atendente é quem fez a última ação na senha — quem atendeu, quem
    marcou a desistência. A senha que ninguém chamou fica «sem atendente».
    """
    h = hoje or date.today().isoformat()
    linhas = _linhas_do_periodo(con, inicio, fim, atendente_id)
    por_hora: dict[str, int] = {}
    for r in linhas:
        hora = str(r.get("created_at") or "")[11:13]
        if hora:
            por_hora[hora] = por_hora.get(hora, 0) + 1
    return {
        "inicio": inicio, "fim": fim,
        "resumo": _resumo(linhas, h),
        "por_atendente": _agrupar(linhas, lambda r: r.get("attendant_name") or "(sem atendente)", h),
        "por_tipo": _agrupar(linhas, lambda r: r.get("service_type") or "Geral", h),
        "por_prioridade": _agrupar(
            linhas, lambda r: "Preferencial" if int(r.get("priority") or 0) else "Normal", h),
        "por_dia": sorted(_agrupar(linhas, lambda r: r["ticket_date"], h), key=lambda g: g["nome"]),
        "por_hora": [{"hour": k, "count": por_hora[k]} for k in sorted(por_hora)],
    }


def historico(con, inicio: str, fim: str, *, atendente_id: int | None = None) -> list[dict]:
    """As senhas do período, uma por linha, com os tempos. Só LÊ."""
    linhas = _linhas_do_periodo(con, inicio, fim, atendente_id)
    for r in linhas:
        r["senha"] = rotulo(r)
        r["situacao"] = NOME_DA_SITUACAO.get(r["status"], r["status"])
        r["espera_seg"] = _espera(r)
        r["atendimento_seg"] = _atendimento(r)
    return linhas


def minutos(segundos: Any) -> str:
    """`754` → `12,6 min`. Para a tela e o CSV; só calcula."""
    if segundos is None:
        return "—"
    return f"{float(segundos) / 60:.1f}".replace(".", ",") + " min"
