"""O tríduo do protesto: quando o protesto pode ser lavrado, e até quando.

Tarefa 56 — «Controlar automaticamente datas críticas para impedir lavratura
fora do termo final». Até aqui nenhuma função do Protesto calculava prazo, por
decisão do oficial de 24/08/2026; a tarefa é a decisão nova, e a conta é a do
Código de Normas da CGJ/TJMA, lido no PDF da casa:

    art. 913, I    — o protesto se lavra dentro de três dias úteis contados da
                     protocolização;
    art. 913, § 2º — exclui-se o dia do apontamento e inclui-se o do vencimento;
    art. 913, § 3º — dia sem expediente bancário normal não é útil (é a lista
                     de feriados da casa, `ri_feriados_locais`);
    art. 925, § 4º — «o prazo-limite para pagamento é o dia previsto para a
                     lavratura do protesto»: é o dia que o aviso imprime
                     (`protesto_aviso.prazo_limite`), e protestar antes dele
                     tiraria do devedor o prazo que o papel lhe deu;
    art. 922, § 1º — por edital, o protesto se lavra «do final do primeiro dia
                     útil subsequente da publicação»;
    art. 913, II e III, e art. 924 — intimação feita no último dia do prazo ou
                     depois dele (ou comprovante devolvido depois): o protesto
                     «somente» no primeiro dia útil subsequente;
    art. 913, IV   — sustação revogada: no primeiro dia útil subsequente ao
                     término da suspensão (Lei 9.492/1997, art. 17, § 2º);
    art. 913, § 1º — ultrapassado o tríduo, o instrumento menciona o atraso e o
                     motivo que o justificou.

AS DUAS PONTAS NÃO PESAM IGUAL, e é a norma que diz isso. Antes do termo
inicial o protesto não se lavra — não há motivo que o torne lícito: o devedor
ainda está no prazo que o aviso lhe deu. Depois do termo final ele se lavra,
**com o motivo escrito**, porque o § 1º prevê o atraso e manda declará-lo.

O DIA DE CADA FATO É O DO ATO. A protocolização é o `data_ato` do apontamento
(e, sem ele, o AAMMDD do protocolo, a mesma leitura do aviso); a intimação é o
da última intimação lavrada — a pessoal se lavra quando o comprovante volta, e
a por edital no dia da publicação (`protesto_aviso.publicar_edital`). O horário
não entra: «do final do dia» é regra de expediente, e a tela o diz.

Este módulo só LÊ e calcula. Quem recusa é `protesto.lancar_protesto`, pela
`conferir_lavratura` daqui, e quem grava a conta no ato também é ele.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from bd_nativo import banco
from protesto import ProtestoError
from ri_schema import ler_feriados_locais, soma_dias_uteis

#: O mesmo piso de motivo escrito das recusas de certidão do RCPN e do RI.
PISO_DO_MOTIVO = 10

ANTES = "ANTES"
NO_PRAZO = "NO_PRAZO"
ATRASADO = "ATRASADO"
SEM_CONTA = "SEM_CONTA"


class TriduoError(ProtestoError):
    """Lavratura fora do tríduo sem o que a norma exige."""


def feriados_da_casa(con) -> set[date]:
    """A lista de feriados que o RI, o aviso e o gestor já usam. Só LÊ."""
    bd = banco(con)
    if not bd.tem_tabela("settings"):
        return set()
    linha = bd.um("SELECT value FROM settings WHERE key=%s",
                  ("ri_feriados_locais",))
    return ler_feriados_locais(((linha or {}).get("value")) or "")


def _dia(valor: Any) -> date | None:
    try:
        return date.fromisoformat(str(valor or "")[:10])
    except ValueError:
        return None


def _dia_do_protocolo(protocolo: Any) -> date | None:
    """O AAMMDD do protocolo — a leitura de `protesto_aviso.prazo_limite`."""
    s = "".join(c for c in str(protocolo or "") if c.isdigit())
    if len(s) < 6:
        return None
    try:
        return date(2000 + int(s[:2]), int(s[2:4]), int(s[4:6]))
    except ValueError:
        return None


def br(iso: Any) -> str:
    s = str(iso or "")[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) == 10 and s[4] == "-" else s


def contar(con, titulo_id: int, *, feriados: set[date] | None = None) -> dict:
    """As datas críticas do título. Só LÊ.

    Devolve `termo_inicial` e `termo_final` (AAAA-MM-DD), os fatos de onde
    saíram e a `regra`, com os artigos. Quando falta um fato, `sem_conta` diz
    qual — e as duas pontas ficam `None`: prazo inventado é pior que prazo
    nenhum.
    """
    bd = banco(con)
    if feriados is None:
        feriados = feriados_da_casa(bd)
    tit = bd.um("SELECT protocolo FROM pt_titulos WHERE id=%s", (int(titulo_id),))
    apont = bd.um(
        """SELECT data_ato FROM pt_atos WHERE titulo_id=%s AND tipo='APONTAMENTO'
              AND cancelado=0 ORDER BY id LIMIT 1""", (int(titulo_id),))
    intim = bd.um(
        """SELECT data_ato, detalhe_json FROM pt_atos
            WHERE titulo_id=%s AND tipo='INTIMACAO' AND cancelado=0
            ORDER BY id DESC LIMIT 1""", (int(titulo_id),))
    revog = bd.um(
        """SELECT data_ato FROM pt_atos
            WHERE titulo_id=%s AND tipo='REVOGACAO_SUSTACAO' AND cancelado=0
            ORDER BY id DESC LIMIT 1""", (int(titulo_id),))

    conta: dict[str, Any] = {
        "protocolizado_em": None, "de_onde": None, "termo_legal": None,
        "intimado_em": None, "modo": None, "revogada_em": None,
        "termo_inicial": None, "termo_final": None, "regra": "",
        "sem_conta": None}

    protocolizado = _dia(apont["data_ato"]) if apont else None
    conta["de_onde"] = "apontamento" if protocolizado else None
    if protocolizado is None and tit:
        protocolizado = _dia_do_protocolo(tit["protocolo"])
        conta["de_onde"] = "protocolo" if protocolizado else None
    if protocolizado is None:
        conta["sem_conta"] = ("o título não tem a data da protocolização — nem "
                              "o ato de apontamento, nem o protocolo na forma "
                              "AAMMDD")
        return conta
    legal = soma_dias_uteis(protocolizado, 3, feriados)
    conta["protocolizado_em"] = protocolizado.isoformat()
    conta["termo_legal"] = legal.isoformat()

    intimado = _dia(intim["data_ato"]) if intim else None
    if intimado is None:
        conta["sem_conta"] = "o título não tem intimação lavrada com data"
        return conta
    try:
        modo = (json.loads(intim["detalhe_json"] or "{}").get("modo") or "")
    except (TypeError, ValueError):
        modo = ""
    modo = str(modo).upper() or "PESSOAL"
    conta["intimado_em"] = intimado.isoformat()
    conta["modo"] = modo

    if modo == "EDITAL":
        depois_do_edital = soma_dias_uteis(intimado, 1, feriados)
        inicial = max(legal, depois_do_edital)
        regra = ("CN-MA art. 922, § 1º (edital: do final do primeiro dia útil "
                 "depois da publicação) e art. 925, § 4º")
        if depois_do_edital > legal:
            regra += "; publicado no último dia do tríduo ou depois: art. 913, II"
    elif intimado >= legal:
        inicial = soma_dias_uteis(intimado, 1, feriados)
        regra = ("CN-MA art. 913, II e III, e art. 924 (intimação no último dia "
                 "do tríduo ou depois: só no primeiro dia útil seguinte)")
    else:
        inicial = legal
        regra = ("CN-MA art. 913, I e § 2º (três dias úteis da protocolização) "
                 "e art. 925, § 4º (o prazo-limite do aviso é o dia da lavratura)")
    final = max(legal, inicial)

    revogada = _dia(revog["data_ato"]) if revog else None
    if revogada is not None:
        conta["revogada_em"] = revogada.isoformat()
        depois_da_revogacao = soma_dias_uteis(revogada, 1, feriados)
        if depois_da_revogacao > final:
            final = depois_da_revogacao
            regra += ("; sustação revogada: até o primeiro dia útil seguinte "
                      "(art. 913, IV; Lei 9.492/1997, art. 17, § 2º)")

    conta["termo_inicial"] = inicial.isoformat()
    conta["termo_final"] = final.isoformat()
    conta["regra"] = regra
    return conta


def situacao(conta: dict, hoje: Any) -> str:
    """Onde `hoje` cai em relação às duas pontas. Só calcula."""
    dia = str(hoje or "")[:10]
    if conta.get("sem_conta") or not conta.get("termo_final"):
        return SEM_CONTA
    if dia < conta["termo_inicial"]:
        return ANTES
    if dia > conta["termo_final"]:
        return ATRASADO
    return NO_PRAZO


def conferir_lavratura(con, titulo_id: int, *, hoje: Any,
                       motivo_atraso: str | None = None,
                       feriados: set[date] | None = None) -> dict:
    """A conta do tríduo para lavrar HOJE. Só LÊ; recusa com `TriduoError`.

    Antes do termo inicial, recusa sempre. Depois do termo final — ou quando a
    conta não fecha por falta de um fato —, exige o motivo escrito, que volta
    na conta para o ato gravar e o instrumento declarar (art. 913, § 1º).
    """
    conta = contar(con, titulo_id, feriados=feriados)
    onde = situacao(conta, hoje)
    conta["situacao"] = onde
    conta["conferido_em"] = str(hoje or "")[:10]
    if onde == ANTES:
        raise TriduoError(
            f"Ainda não é dia de protestar: o devedor tem até "
            f"{br(conta['termo_inicial'])} para pagar, e o protesto se lavra "
            f"desse dia em diante ({conta['regra']}). Intimado em "
            f"{br(conta['intimado_em'])}; protocolizado em "
            f"{br(conta['protocolizado_em'])}.")
    if onde in (ATRASADO, SEM_CONTA):
        motivo = " ".join(str(motivo_atraso or "").split())
        if len(motivo) < PISO_DO_MOTIVO:
            if onde == ATRASADO:
                raise TriduoError(
                    f"O tríduo deste título terminou em "
                    f"{br(conta['termo_final'])} ({conta['regra']}). O protesto "
                    f"ainda pode ser lavrado, mas o instrumento tem de dizer o "
                    f"atraso e o motivo (CN-MA art. 913, § 1º): escreva o "
                    f"motivo do atraso, com pelo menos {PISO_DO_MOTIVO} letras.")
            raise TriduoError(
                f"O sistema não conseguiu contar o tríduo: {conta['sem_conta']}. "
                f"Para lavrar assim mesmo, escreva o motivo, com pelo menos "
                f"{PISO_DO_MOTIVO} letras — ele fica gravado no ato.")
        conta["motivo"] = motivo
    return conta


def mencao_no_instrumento(detalhe_json: Any) -> dict | None:
    """O atraso que o ato de protesto gravou, se houve. Só calcula."""
    try:
        detalhe = json.loads(detalhe_json or "{}")
    except (TypeError, ValueError):
        return None
    t = (detalhe or {}).get("triduo") or {}
    if t.get("situacao") != ATRASADO or not t.get("motivo"):
        return None
    return {"termo_final": t.get("termo_final"), "motivo": t["motivo"],
            "lavrado_em": t.get("conferido_em")}


def para_a_lista(con, linhas: list[dict], *, hoje: Any) -> list[dict]:
    """Acrescenta a conta a cada linha da tela «A protestar». Só LÊ."""
    feriados = feriados_da_casa(con)
    for linha in linhas:
        conta = contar(con, int(linha["id"]), feriados=feriados)
        conta["termo_inicial_br"] = br(conta["termo_inicial"])
        conta["termo_final_br"] = br(conta["termo_final"])
        linha["triduo"] = conta
        linha["triduo_situacao"] = situacao(conta, hoje)
    return linhas
