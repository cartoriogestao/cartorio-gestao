"""Suspensao e retomada do prazo da prenotacao (TJMA 452, § 3º).

O ACHADO — revisao de 13/08 e de 24/09/2026 (P1): `suscitacao_duvida` existia
em `ri_protocolos`, mas o prazo corria sem parar e a prenotacao viva de um
titulo em duvida, usucapiao ou retificacao aparecia como VENCIDA.

O DESENHO MINIMO
    `data_limite` continua sendo a unica data que as telas leem (lista,
    comprovante, reingresso). Suspender grava desde quando e por que; retomar
    empurra `data_limite` pelos dias uteis em que ficou suspensa e anota isso
    na `anotacao` do protocolo. Enquanto suspensa, nenhuma tela a conta como
    vencida.

AINDA NAO FEITO (TODO documentado no checklist): ligar automaticamente o
processo de usucapiao/retificacao ao protocolo e suspender ao abri-lo; a
contagem dos 5 dias do saldo de emolumentos (art. 206-A) fora do prazo.
"""
from __future__ import annotations

from datetime import date

from ri_schema import dias_uteis_entre, soma_dias_uteis

# TJMA 452, § 3º — hipoteses em que o prazo da prenotacao nao corre.
MOTIVOS: dict[str, str] = {
    "DUVIDA": "Suscitação de dúvida / remessa ao juízo",
    "USUCAPIAO": "Usucapião extrajudicial em processamento",
    "RETIFICACAO": "Retificação de área em processamento",
    "ADJUDICACAO": "Adjudicação compulsória extrajudicial",
    "EDITAIS": "Editais e notificações em curso",
    "SALDO_EMOLUMENTOS": "Saldo de emolumentos (Lei 6.015, art. 206-A)",
    "NOVA_EXIGENCIA": "Nova nota de exigências",
    "REINGRESSO": "Reingresso do título",
}


class PrazoError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


def suspensa(p) -> bool:
    try:
        return bool(p["prazo_suspenso_desde"])
    except (KeyError, IndexError):
        return False


def suspender(con, protocolo_id: int, *, motivo: str, quem: str | None,
              hoje: date) -> None:
    p = con.execute("SELECT * FROM ri_protocolos WHERE id=?",
                    (int(protocolo_id),)).fetchone()
    if not p:
        raise PrazoError("Protocolo não encontrado.")
    if p["situacao"] != "ABERTO":
        raise PrazoError("Só se suspende o prazo de prenotação ABERTA.")
    if suspensa(p):
        raise PrazoError("O prazo desta prenotação já está suspenso.")
    if motivo not in MOTIVOS:
        raise PrazoError("Escolha uma das hipóteses do TJMA 452, § 3º.")
    con.execute(
        """UPDATE ri_protocolos
              SET prazo_suspenso_desde=?, prazo_suspenso_motivo=?,
                  prazo_suspenso_por=?,
                  suscitacao_duvida=CASE WHEN ?='DUVIDA'
                                         THEN COALESCE(suscitacao_duvida, ?)
                                         ELSE suscitacao_duvida END
            WHERE id=?""",
        (hoje.isoformat(), motivo, quem, motivo, hoje.isoformat(),
         int(protocolo_id)))


def retomar(con, protocolo_id: int, *, quem: str | None, hoje: date,
            feriados: set | None = None) -> dict:
    """Volta a contar. Devolve `{"dias", "data_limite"}` (nova)."""
    p = con.execute("SELECT * FROM ri_protocolos WHERE id=?",
                    (int(protocolo_id),)).fetchone()
    if not p:
        raise PrazoError("Protocolo não encontrado.")
    if not suspensa(p):
        raise PrazoError("O prazo desta prenotação não está suspenso.")
    desde = date.fromisoformat(p["prazo_suspenso_desde"][:10])
    dias = max(0, dias_uteis_entre(desde, hoje, feriados))
    limite = p["data_limite"]
    novo = limite
    if limite and dias:
        novo = soma_dias_uteis(date.fromisoformat(limite[:10]), dias,
                               feriados).isoformat()
    nota = (f"Prazo suspenso de {desde.isoformat()} a {hoje.isoformat()} "
            f"({MOTIVOS.get(p['prazo_suspenso_motivo'], p['prazo_suspenso_motivo'])}"
            f"): +{dias} dia(s) útil(eis); limite {limite} → {novo}"
            f"{' — ' + quem if quem else ''}.")
    con.execute(
        """UPDATE ri_protocolos
              SET data_limite=?, prazo_suspenso_desde=NULL,
                  prazo_suspenso_motivo=NULL, prazo_suspenso_por=NULL,
                  anotacao=COALESCE(anotacao || char(10), '') || ?
            WHERE id=?""",
        (novo, nota, int(protocolo_id)))
    return {"dias": dias, "data_limite": novo}
