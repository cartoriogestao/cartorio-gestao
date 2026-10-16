"""A mesa do oficial — o que é dele, pessoalmente, e em que ordem.

    «gerir as pendencias pessoais no cartorio gestao» — o oficial, 09/10/2026

O QUE JÁ EXISTIA, E O QUE ISTO ACRESCENTA
    O despacho diário do gestor (`gestor_rotina.despacho_do_oficial`) lista as
    tarefas que estão com ele. Medido na produção em 09/10/2026: **26 tarefas**
    com ele, numa lista corrida por prioridade — a vencida desde 30/09 ao lado da
    que vence em fevereiro. A mesa separa por QUANDO, e soma o que a lista não
    mostrava:

      1. o que VENCEU e o que vence nesta semana (o resto vem depois, contado);
      2. onde ele é SUBSTITUTO e o titular deixou vencer — a responsabilidade
         chega a ele (Lei 8.935, art. 22: o delegatário responde pelos prepostos);
      3. o malote PARA CUMPRIMENTO que ninguém pegou — sem tarefa, sem prazo,
         parado em «recebido». Medido em 09/10/2026: mandado de averbação,
         circular de óbito e pedido de certidão nessa situação;
      4. o que chega com cheiro de FRAUDE, qualquer que seja o setor;
      5. as credenciais das Centrais que só ele pode digitar;
      6. os certificados digitais da casa e quando vencem.

O QUE ELA NÃO FAZ
    Não fecha, não passa e não reprioriza tarefa de ninguém. Ela lê.
"""
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from datetime import date, datetime, timedelta

ABERTA = ("CONCLUIDA", "CANCELADA")          # situações que NÃO são abertas

#: O despacho do gestor é a lista do dia; contá-lo como tarefa dele seria a
#: tarefa que descreve as tarefas.
FORA_DA_MESA = ("DESPACHO",)

_FRAUDE = re.compile(r"fraud|falsifica|suspei", re.IGNORECASE)


def _dt(texto: str | None) -> date | None:
    try:
        return date.fromisoformat((texto or "")[:10])
    except ValueError:
        return None


def dono_da_mesa(con: sqlite3.Connection) -> int | None:
    """Quem é o oficial: o titular da Gestão (ordem dele, 06/10), senão o 1º ADMIN."""
    try:
        linha = con.execute("SELECT user_id FROM ge_responsaveis WHERE setor='GESTAO'"
                            ).fetchone()
        if linha:
            return int(linha[0])
    except sqlite3.Error:
        pass
    linha = con.execute("SELECT id FROM users WHERE role='ADMIN' AND active=1 "
                        "ORDER BY id LIMIT 1").fetchone()
    return int(linha[0]) if linha else None


def _nomes(con) -> dict[int, str]:
    return {int(r[0]): (r[1] or r[2]) for r in
            con.execute("SELECT id, full_name, username FROM users")}


def tarefas(con: sqlite3.Connection, hoje: date, dono: int) -> dict[str, list[dict]]:
    """As tarefas do oficial por quando: vencidas, hoje, 7 dias, depois, sem prazo."""
    marcas = ",".join("?" * len(ABERTA))
    fora_marcas = ",".join("?" * len(FORA_DA_MESA))
    # A SUSPENSA SAI DA PAUTA (relato #132): ela não vence nem pede o oficial
    # enquanto espera a data ou a condição.
    import tarefa_suspensao as TS
    nao_suspensa, params_suspensao = TS.condicao_nao_suspensa(None, hoje, con=con)
    linhas = con.execute(
        f"""SELECT id, title, priority, due_date, source_type, sector, linked_expediente_id
              FROM tasks WHERE assigned_user_id = ? AND status NOT IN ({marcas})
               AND source_type NOT IN ({fora_marcas}) AND {nao_suspensa}""",
        (dono, *ABERTA, *FORA_DA_MESA, *params_suspensao)).fetchall()
    grupos: dict[str, list[dict]] = {"VENCIDAS": [], "HOJE": [], "SEMANA": [],
                                     "DEPOIS": [], "SEM_PRAZO": []}
    semana = hoje + timedelta(days=7)
    ordem = {"CRITICA": 0, "ALTA": 1, "MEDIA": 2, "BAIXA": 3}
    for r in linhas:
        prazo = _dt(r[3])
        item = {"id": r[0], "titulo": r[1], "prioridade": r[2], "prazo": r[3],
                "origem": r[4], "setor": r[5], "expediente_id": r[6],
                "dias": (prazo - hoje).days if prazo else None}
        if prazo is None:
            grupos["SEM_PRAZO"].append(item)
        elif prazo < hoje:
            grupos["VENCIDAS"].append(item)
        elif prazo == hoje:
            grupos["HOJE"].append(item)
        elif prazo <= semana:
            grupos["SEMANA"].append(item)
        else:
            grupos["DEPOIS"].append(item)
    for lista in grupos.values():
        lista.sort(key=lambda t: (t["prazo"] or "9999", ordem.get(t["prioridade"], 9)))
    return grupos


def substituicoes_vencidas(con: sqlite3.Connection, hoje: date, dono: int) -> list[dict]:
    """Onde o oficial é o substituto e o titular deixou vencer."""
    marcas = ",".join("?" * len(ABERTA))
    nomes = _nomes(con)
    import tarefa_suspensao as TS
    nao_suspensa, params_suspensao = TS.condicao_nao_suspensa(None, hoje, con=con)
    linhas = con.execute(
        f"""SELECT id, title, priority, due_date, assigned_user_id FROM tasks
             WHERE backup_user_id = ? AND assigned_user_id IS NOT NULL
               AND assigned_user_id <> ? AND status NOT IN ({marcas})
               AND due_date IS NOT NULL AND due_date < ? AND {nao_suspensa}
             ORDER BY due_date""",
        (dono, dono, *ABERTA, hoje.isoformat(), *params_suspensao)).fetchall()
    return [{"id": r[0], "titulo": r[1], "prioridade": r[2], "prazo": r[3],
             "titular": nomes.get(r[4], f"#{r[4]}"),
             "dias_vencida": (hoje - _dt(r[3])).days} for r in linhas]


def malote_sem_providencia(con: sqlite3.Connection, hoje: date) -> list[dict]:
    """Expediente «para cumprimento» parado em RECEBIDO e sem tarefa aberta ligada.

    É da casa inteira, e não só do oficial: ordem judicial que ninguém pegou é
    responsabilidade dele qualquer que seja o setor.
    """
    marcas = ",".join("?" * len(ABERTA))
    nomes = _nomes(con)
    linhas = con.execute(
        f"""SELECT e.id, e.internal_protocol, e.subject, e.sender, e.received_at,
                   e.deadline_date, e.assigned_user_id, e.category
              FROM expedientes e
             WHERE e.completed_at IS NULL AND e.stage = 'RECEBIDO'
               AND e.category = 'Para Cumprimento'
               AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.linked_expediente_id = e.id
                                  AND t.status NOT IN ({marcas}))
             ORDER BY e.received_at""", ABERTA).fetchall()
    fora = []
    for r in linhas:
        recebido = _dt(r[4])
        fora.append({"id": r[0], "protocolo": r[1], "assunto": " ".join((r[2] or "").split()),
                     "remetente": (r[3] or "").strip(), "recebido_em": r[4],
                     "prazo": r[5], "responsavel": nomes.get(r[6], "—"),
                     "dias_parado": (hoje - recebido).days if recebido else None})
    return fora


def suspeitas_de_fraude(con: sqlite3.Connection) -> list[dict]:
    """Expediente aberto que fala em fraude ou suspeita — qualquer categoria."""
    nomes = _nomes(con)
    fora = []
    for r in con.execute(
            """SELECT id, internal_protocol, subject, sender, received_at, assigned_user_id,
                      stage FROM expedientes WHERE completed_at IS NULL ORDER BY received_at"""):
        assunto = " ".join((r[2] or "").split())
        if _FRAUDE.search(assunto):
            fora.append({"id": r[0], "protocolo": r[1], "assunto": assunto,
                         "remetente": (r[3] or "").strip(), "recebido_em": r[4],
                         "responsavel": nomes.get(r[5], "—"), "etapa": r[6]})
    return fora


def credenciais_faltando(pasta_dados) -> list[dict] | None:
    """As credenciais de PRODUÇÃO que ainda não foram digitadas. None = não mediu.

    Só lê se o arquivo existe — `centrais_cred.situacao` nunca devolve segredo.
    """
    try:
        import centrais_cred as CC
        linhas = CC.situacao(pasta_dados)
    except Exception:                                   # noqa: BLE001 — vira «não mediu»
        return None
    return [{"central": c["nome"], "ambiente": c["ambiente"]} for c in linhas
            if not c["informada"] and c["ambiente"] == CC.PRODUCAO]


_CPF_NO_NOME = re.compile(r":\d{11,14}")


def ler_certificados_do_windows() -> list[dict] | None:
    """Os certificados com chave privada do usuário do Windows. None = não mediu.

    Lê assunto e validade — nada que seja segredo. O número do CPF/CNPJ que a
    ICP-Brasil põe no nome sai mascarado.
    """
    comando = ("Get-ChildItem Cert:\\CurrentUser\\My | Where-Object HasPrivateKey | "
               "Select-Object Subject, @{n='Vence';e={$_.NotAfter.ToString('yyyy-MM-dd')}} | "
               "ConvertTo-Json -Compress")
    try:
        saida = subprocess.run(["powershell", "-NoProfile", "-Command", comando],
                               capture_output=True, timeout=60, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    texto = saida.decode("utf-8", errors="replace").strip()
    if not texto:
        return []
    try:
        dados = json.loads(texto)
    except ValueError:
        return None
    if isinstance(dados, dict):
        dados = [dados]
    fora = []
    for c in dados:
        assunto = c.get("Subject") or ""
        nome = re.search(r"CN=([^,]+)", assunto)
        fora.append({"nome": _CPF_NO_NOME.sub(":***", nome.group(1) if nome else assunto),
                     "vence": c.get("Vence")})
    return fora


def certificados_a_vencer(certificados: list[dict] | None, hoje: date,
                          dias: int = 60) -> list[dict] | None:
    """Os que vencem dentro de `dias` (ou já venceram). A3 vencido para tudo."""
    if certificados is None:
        return None
    fora = []
    for c in certificados:
        vence = _dt(c.get("vence"))
        if vence is None:
            continue
        faltam = (vence - hoje).days
        if faltam <= dias:
            fora.append({**c, "faltam_dias": faltam})
    fora.sort(key=lambda c: c["faltam_dias"])
    return fora


def montar(con: sqlite3.Connection, hoje: date, *, pasta_dados=None,
           ler_certificados=None) -> dict:
    """A mesa inteira do dia, numa estrutura só, para o relatório e para a tela."""
    dono = dono_da_mesa(con)
    mesa: dict = {"hoje": hoje.isoformat(), "dono": dono,
                  "dono_nome": _nomes(con).get(dono, "—") if dono else "—"}
    if dono is None:
        mesa["erro"] = "Não há oficial (titular da Gestão nem ADMIN ativo) neste banco."
        return mesa
    mesa["tarefas"] = tarefas(con, hoje, dono)
    mesa["substituicoes"] = substituicoes_vencidas(con, hoje, dono)
    mesa["malote"] = malote_sem_providencia(con, hoje)
    mesa["fraude"] = suspeitas_de_fraude(con)
    mesa["credenciais"] = credenciais_faltando(pasta_dados) if pasta_dados else None
    leitor = ler_certificados or ler_certificados_do_windows
    mesa["certificados"] = certificados_a_vencer(leitor(), hoje)
    mesa["gerada_em"] = datetime.now().isoformat(timespec="seconds")
    return mesa
