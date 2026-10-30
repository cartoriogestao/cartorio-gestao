"""Encerramento da prenotação do Registro de Imóveis, com motivo da lista.

Pedido da Tabeliã e Registradora Substituta: na ficha da prenotação
o oficial escolhe o motivo, e a situação sai do motivo. Texto livre não encerra.

O QUE SE GRAVA
    `motivo_encerramento` é o rótulo da lista, do jeito que se lê na correição
    — não uma chave. `obs_encerramento` é a observação; em «Outro» ela é
    obrigatória, porque é a única explicação. `anotacao` continua recebendo
    a linha `[Encerrado] …`, como o caminho antigo já fazia.

QUEM AINDA PODE SER ENCERRADA
    `ABERTO` e `DEVOLVIDO`. A devolvida não está fechada: a nota devolutiva
    põe essa situação e a prenotação segue aceitando nota e reingresso
    (`ri_nota_devolutiva.SITUACOES_QUE_ACEITAM_NOTA`; `ri_pedidos._ABERTAS`).
    Encerrar a partir daí é decidir que não se espera mais — decurso, exigência
    não cumprida, recusa. `ENCERRADO`, `CANCELADO` e `RECUSADO` já estão
    fechados; o caminho é reabrir, que não apaga estas colunas.
"""
from __future__ import annotations

MOTIVO_TITULO_REGISTRADO = "TITULO_REGISTRADO"
MOTIVO_DECURSO = "DECURSO_PRAZO"
MOTIVO_DESISTENCIA = "DESISTENCIA"
MOTIVO_EXIGENCIA = "EXIGENCIA"
MOTIVO_DEVOLVIDO = "DEVOLVIDO_NOTA"
MOTIVO_RECUSA = "RECUSA"
MOTIVO_OUTRO = "OUTRO"

# O arquivamento 16.39 encerra sozinho, sem alguém escolher na lista. O motivo
# é o mesmo item «Título registrado»; a observação diz por qual caminho veio.
OBS_DO_ARQUIVAMENTO = "arquivamento 16.39"

# A ordem é a ordem do seletor.
MOTIVOS: dict[str, dict[str, str]] = {
    MOTIVO_TITULO_REGISTRADO: {
        "rotulo": "Título registrado",
        "situacao": "ENCERRADO",
    },
    MOTIVO_DECURSO: {
        "rotulo": ("Decurso do prazo da prenotação sem registro "
                   "(Lei 6.015/73, art. 205)"),
        "situacao": "CANCELADO",
    },
    MOTIVO_DESISTENCIA: {
        "rotulo": "Desistência ou requerimento do apresentante",
        "situacao": "CANCELADO",
    },
    MOTIVO_EXIGENCIA: {
        "rotulo": "Exigência não cumprida no prazo",
        "situacao": "CANCELADO",
    },
    MOTIVO_DEVOLVIDO: {
        "rotulo": "Devolvido com nota devolutiva",
        "situacao": "DEVOLVIDO",
    },
    MOTIVO_RECUSA: {
        "rotulo": "Recusa do título",
        "situacao": "RECUSADO",
    },
    MOTIVO_OUTRO: {
        "rotulo": "Outro",
        "situacao": "CANCELADO",
    },
}

SITUACOES_RESULTANTES = ("ENCERRADO", "CANCELADO", "RECUSADO", "DEVOLVIDO")
SITUACOES_QUE_SE_ENCERRAM = ("ABERTO", "DEVOLVIDO")


class EncerrarError(ValueError):
    """Regra recusada, com a frase pronta para o balcão."""


def resolver(motivo: str | None, *, observacao: str | None = None,
             situacao_escolhida: str | None = None) -> dict:
    """Traduz a escolha da tela. Não grava.

    Nos motivos da lista, a situação é a do motivo — o que a tela mandar em
    `situacao_escolhida` não vale. Em «Outro», vale a situação escolhida, e
    sem escolha fica CANCELADO; a observação é obrigatória.
    """
    chave = (motivo or "").strip()
    if chave not in MOTIVOS:
        raise EncerrarError(
            "Escolha o motivo do encerramento na lista. Texto livre não "
            "encerra prenotação.")
    item = MOTIVOS[chave]
    obs = (observacao or "").strip()
    if chave == MOTIVO_OUTRO:
        if not obs:
            raise EncerrarError(
                "No motivo «Outro», a observação é obrigatória: é ela que "
                "explica o encerramento na correição.")
        situacao = (situacao_escolhida or "").strip().upper() or item["situacao"]
        if situacao not in SITUACOES_RESULTANTES:
            raise EncerrarError(
                f"Situação «{situacao}» não encerra prenotação. "
                f"Use: {', '.join(SITUACOES_RESULTANTES)}.")
    else:
        situacao = item["situacao"]
    return {
        "chave": chave,
        "rotulo": item["rotulo"],
        "situacao": situacao,
        "observacao": obs or None,
    }


def texto_da_anotacao(resolvido: dict) -> str:
    """A linha que se anexa em `anotacao`, no mesmo formato de antes."""
    texto = f"\n[Encerrado] {resolvido['rotulo']}"
    if resolvido.get("observacao"):
        texto += f" — {resolvido['observacao']}"
    return texto


def gravar(bd, protocolo_id: int, resolvido: dict, *, quem: str | None,
           agora: str) -> list:
    """Grava o encerramento. ESCREVE. Devolve as linhas (vazio se a situação
    já não era aberta nem devolvida — outro balcão encerrou no meio)."""
    lugares = ",".join(["%s"] * len(SITUACOES_QUE_SE_ENCERRAM))
    return bd.escrever(
        f"""UPDATE ri_protocolos
               SET situacao=%s,
                   encerrado_em=%s,
                   encerrado_por=%s,
                   motivo_encerramento=%s,
                   obs_encerramento=%s,
                   anotacao=COALESCE(anotacao, '') || %s
             WHERE id=%s AND situacao IN ({lugares})
             RETURNING id""",
        (resolvido["situacao"], agora, quem or None,
         resolvido["rotulo"], resolvido["observacao"],
         texto_da_anotacao(resolvido),
         int(protocolo_id), *SITUACOES_QUE_SE_ENCERRAM),
    )
