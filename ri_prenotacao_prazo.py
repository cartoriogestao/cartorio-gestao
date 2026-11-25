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

from bd_nativo import banco
from ri_schema import dias_uteis_entre, soma_dias_uteis

#: A PRENOTACAO DO REQUERIMENTO DE INTIMACAO FIDUCIARIA NAO VENCE (RI013-I1, 24/11/2026).
#:   «Os efeitos da prenotacao cessarao somente com a conclusao do procedimento de notificacao, o
#:   que ocorrera com a emissao da certidao de purgacao ou nao da mora» (TJMA 723). Quem suspende
#:   e o procedimento (`ri_intimacao_fiduciaria.autuar`), e quem encerra e a certidao dele; a mao
#:   nao suspende nem retoma por este motivo enquanto o procedimento estiver aberto. Suspensa, a
#:   prenotacao continua ABERTA, e por isso continua nas certidoes da matricula (723, § 3º).
INTIMACAO_FIDUCIARIA = "INTIMACAO_FIDUCIARIA"

# TJMA 452, § 3º — hipoteses em que o prazo da prenotacao nao corre; e o TJMA 723, acima.
MOTIVOS: dict[str, str] = {
    "DUVIDA": "Suscitação de dúvida / remessa ao juízo",
    "USUCAPIAO": "Usucapião extrajudicial em processamento",
    "RETIFICACAO": "Retificação de área em processamento",
    "ADJUDICACAO": "Adjudicação compulsória extrajudicial",
    "EDITAIS": "Editais e notificações em curso",
    "SALDO_EMOLUMENTOS": "Saldo de emolumentos (Lei 6.015, art. 206-A)",
    "NOVA_EXIGENCIA": "Nova nota de exigências",
    "REINGRESSO": "Reingresso do título",
    INTIMACAO_FIDUCIARIA: "Intimação do devedor fiduciante em curso (TJMA 723)",
}

#: O que a ficha da prenotacao oferece para suspender a mao: todos, menos o do procedimento.
MOTIVOS_MANUAIS: dict[str, str] = {k: v for k, v in MOTIVOS.items() if k != INTIMACAO_FIDUCIARIA}


#: As situações em que o prazo corre. A nota devolutiva não o suspende: «a prenotação continua correndo».
CORRENDO = ("ABERTO", "DEVOLVIDO")


class PrazoError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


def suspensa(p) -> bool:
    try:
        return bool(p["prazo_suspenso_desde"])
    except (KeyError, IndexError):
        return False


def _intimacao_aberta(bd, protocolo_id: int) -> bool:
    if not bd.tem_tabela("ri_intimacoes"):
        return False
    import ri_intimacao_fiduciaria as INTIM
    return INTIM.aberta_no_protocolo(bd, protocolo_id)


def suspender(con, protocolo_id: int, *, motivo: str, quem: str | None,
              hoje: date, pelo_procedimento: bool = False) -> None:
    bd = banco(con)
    p = bd.um("SELECT * FROM ri_protocolos WHERE id=%s",
              (int(protocolo_id),))
    if not p:
        raise PrazoError("Protocolo não encontrado.")
    if p["situacao"] != "ABERTO":
        raise PrazoError("Só se suspende o prazo de prenotação ABERTA.")
    if suspensa(p):
        raise PrazoError("O prazo desta prenotação já está suspenso.")
    if motivo not in MOTIVOS:
        raise PrazoError("Escolha uma das hipóteses do TJMA 452, § 3º.")
    if motivo == INTIMACAO_FIDUCIARIA and not pelo_procedimento:
        raise PrazoError("Este prazo se suspende abrindo o procedimento de intimação "
                         "fiduciária da prenotação (TJMA 723).")
    bd.escrever(
        """UPDATE ri_protocolos
              SET prazo_suspenso_desde=%s, prazo_suspenso_motivo=%s,
                  prazo_suspenso_por=%s,
                  suscitacao_duvida=CASE WHEN %s
                                         THEN COALESCE(suscitacao_duvida, %s)
                                         ELSE suscitacao_duvida END
            WHERE id=%s""",
        (hoje.isoformat(), motivo, quem, motivo == "DUVIDA", hoje.isoformat(),
         int(protocolo_id)))


def retomar(con, protocolo_id: int, *, quem: str | None, hoje: date,
            feriados: set | None = None) -> dict:
    """Volta a contar. Devolve `{"dias", "data_limite"}` (nova)."""
    bd = banco(con)
    p = bd.um("SELECT * FROM ri_protocolos WHERE id=%s",
              (int(protocolo_id),))
    if not p:
        raise PrazoError("Protocolo não encontrado.")
    if not suspensa(p):
        raise PrazoError("O prazo desta prenotação não está suspenso.")
    if (p["prazo_suspenso_motivo"] == INTIMACAO_FIDUCIARIA
            and _intimacao_aberta(bd, int(protocolo_id))):
        raise PrazoError("A prenotação do requerimento de intimação só cessa com a "
                         "certidão de purgação ou de não purgação (TJMA 723).")
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
    bd.escrever(
        """UPDATE ri_protocolos
              SET data_limite=%s, prazo_suspenso_desde=NULL,
                  prazo_suspenso_motivo=NULL, prazo_suspenso_por=NULL,
                  anotacao=COALESCE(anotacao || chr(10), '') || %s
            WHERE id=%s""",
        (novo, nota, int(protocolo_id)))
    return {"dias": dias, "data_limite": novo}
