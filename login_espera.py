"""A ESPERA DEPOIS DE ERRAR A SENHA — lote LX11 (achado A4 do LS01), 19/10/2026.

O QUE ISTO FECHA
    Qualquer máquina da rede, sem login, tentava senhas à vontade contra
    qualquer usuário: doze threads do waitress, nenhum freio. O PBKDF2 só
    encarecia cada tentativa.

POR QUE ESPERA, E NÃO TRANCA
    Trancar de vez depois de N erros dá ao atacante o poder de trancar o ADMIN
    de propósito — e o balcão fica sem quem destranque. Aqui, depois de 5 erros
    em 15 minutos, cada tentativa nova espera mais: 30 s, 1, 2, 5 e 15 minutos
    (`ESCADA`). Nunca passa de 15 minutos, e a espera é por USUÁRIO + IP: quem
    erra da máquina do balcão não segura o oficial no servidor. Por isso o
    último ADMIN nunca fica trancado de vez — e o ADMIN pode destravar qualquer
    um na tela de usuários.

ONDE MORA A CONTAGEM
    Em `audit_logs`, sem tabela nova: cada erro já era uma linha
    `LOGIN_FAILURE`. A linha guarda a `chave` — HMAC do usuário DIGITADO com a
    chave da sessão — e não o que foi digitado: quem digita a senha no campo do
    usuário não a deixa escrita na auditoria (B5), e o usuário inexistente tem
    a mesma régua que o existente, sem cada nome inventado revelar se existe.
    Zeram a contagem a entrada certa (por usuário + IP) e o «destravar» do ADMIN.

A TENTATIVA EM ESPERA NÃO CONTA COMO ERRO
    Ela nem chega a conferir a senha. Se contasse, quem martela o formulário
    empurraria a espera do dono da conta para sempre.

UMA TENTATIVA POR VEZ (`na_vez`)
    Ler a contagem, conferir a senha e gravar o erro são três passos; sem
    trava, doze tentativas simultâneas liam todas «zero erros» e passavam
    juntas. A tentativa segura a vez da sua chave + IP do começo ao fim.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from contextlib import contextmanager
from datetime import datetime, timedelta

from bd_nativo import banco

LIMIAR = 5
JANELA = timedelta(minutes=15)
ESCADA = (30, 60, 120, 300, 900)            # segundos, do 5º erro em diante
INEXISTENTE = "(inexistente)"

FALHA = "LOGIN_FAILURE"
EM_ESPERA = "LOGIN_EM_ESPERA"
DESTRAVADO = "LOGIN_DESTRAVADO"
ENTROU = "LOGIN_SUCCESS"
ASSUNTO = "login_espera."                   # o começo da chave da trava

# Quanto da auditoria se lê para saber a espera. A cadeia mais longa que a
# régua admite cabe folgada: cada erro novo precisa vir até 30 minutos depois
# do anterior (15 de espera + 15 de janela), e passou disso ela zera.
_HORIZONTE = timedelta(hours=24)
_ISO = "%Y-%m-%dT%H:%M:%S"                   # o de `database.ISO_DT`


def agora() -> datetime:
    """O relógio da régua — os testes o adiantam, como o `DF.relogio`."""
    return datetime.now().replace(microsecond=0)


def chave(segredo: str, usuario: str) -> str:
    """Quem está sendo tentado, sem guardar o que foi digitado."""
    nome = (usuario or "").strip().casefold()
    return hmac.new(str(segredo).encode("utf-8"), nome.encode("utf-8"),
                    hashlib.sha256).hexdigest()[:32]


def detalhes(chave_: str, **extra) -> dict:
    """A `chave` vem PRIMEIRO: é por esse começo do texto que a régua acha a
    linha (`_prefixo`), e o `json.dumps` do `db.log` respeita a ordem."""
    return {"chave": chave_, **extra}


def _prefixo(chave_: str) -> str:
    return json.dumps({"chave": chave_}, ensure_ascii=False)[:-1] + "%"


def espera_do_degrau(n_erros: int) -> timedelta:
    if n_erros < LIMIAR:
        return timedelta(0)
    return timedelta(seconds=ESCADA[min(n_erros - LIMIAR, len(ESCADA) - 1)])


def cadeia(falhas: list[datetime]) -> list[datetime]:
    """Os erros que ainda pesam, do mais velho ao mais novo.

    Abaixo do limiar a janela é deslizante (5 em 15 minutos). Passado o
    limiar, a cadeia segue enquanto cada erro vier até 15 minutos depois de
    acabar a espera do anterior — senão bastaria esperar a janela vencer para
    ganhar mais cinco tentativas livres.
    """
    atual: list[datetime] = []
    for t in sorted(falhas):
        if len(atual) >= LIMIAR and t - atual[-1] > espera_do_degrau(len(atual)) + JANELA:
            atual = []
        if len(atual) < LIMIAR:
            atual = [x for x in atual if t - x <= JANELA]
        atual.append(t)
    return atual


def liberado_em(falhas: list[datetime], quando: datetime) -> datetime | None:
    """Até quando a próxima tentativa espera — ou None, se pode tentar já."""
    erros = cadeia(falhas)
    if len(erros) < LIMIAR:
        return None
    espera = espera_do_degrau(len(erros))
    fim = erros[-1] + espera
    if quando - erros[-1] > espera + JANELA or quando >= fim:
        return None
    return fim


def _falhas(bd, chave_: str, ip: str | None, user_id: int | None,
            quando: datetime) -> list[datetime]:
    desde = (quando - _HORIZONTE).strftime(_ISO)
    marco = bd.valor(
        "SELECT coalesce(max(id), 0) AS n FROM audit_logs "
        "WHERE ts >= %s AND ((action = %s AND details LIKE %s) "
        "OR (action = %s AND user_id = %s AND ip_address IS NOT DISTINCT FROM %s))",
        (desde, DESTRAVADO, _prefixo(chave_), ENTROU, user_id, ip))
    linhas = bd.ler(
        "SELECT ts FROM audit_logs WHERE ts >= %s AND id > %s AND action = %s "
        "AND details LIKE %s AND ip_address IS NOT DISTINCT FROM %s ORDER BY id",
        (desde, marco, FALHA, _prefixo(chave_), ip))
    return [_data(l["ts"]) for l in linhas if _data(l["ts"])]


def _data(texto) -> datetime | None:
    try:
        return datetime.fromisoformat(str(texto))
    except ValueError:
        return None


def espera(con, chave_: str, ip: str | None, user_id: int | None,
           quando: datetime | None = None) -> datetime | None:
    """A espera de quem tenta `chave_` deste `ip`. Só LÊ."""
    quando = quando or agora()
    return liberado_em(_falhas(banco(con), chave_, ip, user_id, quando), quando)


@contextmanager
def na_vez(con, chave_: str, ip: str | None):
    """A vez de tentar a `chave_` deste `ip`: da leitura da espera até o erro
    gravado, uma tentativa só.

    A RAJADA PASSAVA INTEIRA (revisão do LX11). Sem a vez, as doze threads do
    waitress liam ao mesmo tempo «nenhum erro», conferiam a senha e só então
    gravavam: cada rajada ganhava uma dúzia de tentativas além das cinco.
    Com ela, a sexta tentativa só lê a contagem depois que a quinta gravou
    a sua falha — e encontra a espera.

    POR QUE NÃO `bd.travar`. Ela abre a escrita da ponte, que pega a trava
    ÚNICA do banco; segurada durante o PBKDF2 (310 mil voltas), toda gravação
    da casa esperaria cada login, e quem martelasse o formulário pararia o
    balcão. Aqui a transação abre sem a trava única — o BEGIN simples da
    ponte, que é o adiado — e a trava é só desta chave + IP: espera quem
    tenta a mesma conta da mesma máquina, e mais ninguém. Nesta conexão nada
    se grava: o erro vai pelo `db.log`, que confirma na conexão dele ANTES
    desta soltar a vez, e a leitura seguinte (READ COMMITTED) já o vê.
    """
    bd = banco(con)
    con.execute("BEGIN")
    try:
        bd.ler("SELECT pg_advisory_xact_lock(hashtext(%s)) AS vez",
               (f"{ASSUNTO}{chave_}|{ip or ''}",))
        yield bd
    finally:
        con.rollback()


def em_espera_na_casa(con, usuarios: list[dict], segredo: str,
                      quando: datetime | None = None) -> dict[int, list[dict]]:
    """Para a tela de usuários: quem está esperando agora, e de que IP. Só LÊ.

    Uma leitura só da auditoria do dia, e a conta em Python — a tela lista
    todos os usuários, e uma consulta por usuário e por IP seria o dobro do
    serviço para dizer, quase sempre, «ninguém».
    """
    quando = quando or agora()
    bd = banco(con)
    desde = (quando - _HORIZONTE).strftime(_ISO)
    linhas = bd.ler(
        "SELECT id, ts, action, user_id, details, ip_address FROM audit_logs "
        "WHERE ts >= %s AND action IN (%s, %s, %s) ORDER BY id",
        (desde, FALHA, DESTRAVADO, ENTROU))
    por_chave = {chave(segredo, u["username"]): u for u in usuarios}
    falhas: dict[tuple[str, str | None], list[tuple[int, datetime]]] = {}
    marcos: dict[tuple, int] = {}
    for l in linhas:
        try:
            ch = (json.loads(l["details"] or "null") or {}).get("chave")
        except (ValueError, AttributeError):
            ch = None
        if l["action"] == FALHA and ch in por_chave and _data(l["ts"]):
            falhas.setdefault((ch, l["ip_address"]), []).append((l["id"], _data(l["ts"])))
        elif l["action"] == DESTRAVADO and ch:
            marcos[("chave", ch)] = l["id"]
        elif l["action"] == ENTROU and l["user_id"] is not None:
            marcos[("uid", int(l["user_id"]), l["ip_address"])] = l["id"]
    resultado: dict[int, list[dict]] = {}
    for (ch, ip), lista in falhas.items():
        u = por_chave[ch]
        marco = max(marcos.get(("chave", ch), 0),
                    marcos.get(("uid", int(u["id"]), ip), 0))
        fim = liberado_em([t for i, t in lista if i > marco], quando)
        if fim:
            resultado.setdefault(int(u["id"]), []).append({"ip": ip or "?", "ate": fim})
    for lista in resultado.values():
        lista.sort(key=lambda x: (x["ate"], x["ip"]))
    return resultado


def tempo_por_extenso(falta: timedelta) -> str:
    """«30 segundos», «1 minuto», «15 minutos» — arredondando para cima."""
    s = max(1, int(-(-falta.total_seconds() // 1)))
    if s < 60:
        return f"{s} segundo" + ("s" if s != 1 else "")
    m = -(-s // 60)
    return f"{m} minuto" + ("s" if m != 1 else "")


def recado(fim: datetime, quando: datetime | None = None) -> str:
    quando = quando or agora()
    return (f"Muitas tentativas erradas para este usuário neste computador. "
            f"Por segurança, tente de novo em {tempo_por_extenso(fim - quando)} "
            f"(às {fim:%H:%M:%S}). Se você esqueceu a senha, peça ao "
            f"administrador para redefini-la.")
