"""Efeitos comuns do cancelamento de uma certidao emitida.

O PORTAL DO SELO CONTINUA SENDO EXTERNO. Este modulo nao cancela selo no
Tribunal e nao finge que o fez: ele exige a declaracao expressa de quem esta
operando e, depois dela, espelha no razao local os selos proprios daquela
certidao. A declaracao, o motivo e o usuario ficam gravados na certidao e na
auditoria da rota.

A FOLHA VOLTA NO MESMO CANCELAMENTO. O papel de seguranca e identificado pela
mesma chave usada pelo razao dos selos (tabela + ato_id), de modo que nenhuma
busca por numero, nome ou data e necessaria.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from bd_nativo import banco
import papel_seguranca as PAPEL


DECLARACAO_SELO_TJMA = (
    "Declaro que eventual selo próprio emitido para esta certidão já foi "
    "cancelado no Portal do Selo do TJMA."
)
MENSAGEM_DECLARACAO_OBRIGATORIA = (
    "Confirme a declaração de que eventual selo próprio emitido para esta "
    "certidão já foi cancelado no Portal do Selo do TJMA."
)

# O TAMANHO MÍNIMO DO MOTIVO MORA AQUI, e não em cada rota — relato #81,
# 17/09/2026.
#
#   O RCPN sempre exigiu motivo escrito (`rc_certidao.cancelar` recusa abaixo
#   de dez letras, com uma frase que explica por quê), e o Registro de Imóveis
#   recusava pelo MESMO número escrito de novo, dentro da rota. Dois números
#   iguais em dois arquivos são dois números que divergem no primeiro conserto
#   — e aqui o que diverge é o campo que explica, anos depois, por que um
#   papel que está na mão de alguém foi cancelado.
#
#   A MENSAGEM DO RCPN É MELHOR QUE A MINHA e ficou sendo a da casa: ela não
#   diz só «informe o motivo», diz para que ele serve. O RCPN continua com a
#   dele, palavra por palavra, porque quem a lê é o balcão e ela já está no
#   ar; o que não pode divergir é o NÚMERO, e é ele que há teste medindo nos
#   dois — rodando as duas funções na fronteira, e não lendo os dois arquivos.
MOTIVO_MINIMO = 10
MOTIVO_CURTO = (
    "Escreva por que a certidão foi cancelada. Ela está na mão de alguém, e o "
    "motivo é o que explica a segunda via."
)


def motivo_curto(texto: Any) -> bool:
    """Só calcula: o motivo não explica nada a quem for ler depois?"""
    return len(str(texto or "").strip()) < MOTIVO_MINIMO



def declaracao_confirmada(valor: Any) -> bool:
    """Aceita os valores usuais de checkbox e booleano. So calcula."""
    if valor is True or valor == 1:
        return True
    return str(valor or "").strip().lower() in {"1", "on", "sim", "true"}


def _sem_tabela(erro: sqlite3.OperationalError) -> bool:
    return "no such table" in str(erro).lower()


def concluir(con: Any, *, tabela: str, ato_id: int,
             motivo: str, agora: str, usuario: str | None = None) -> dict:
    """Espelha selos cancelados e recupera folhas. ESCREVE, sem rede.

    Bancos unitarios de alguns testes criam apenas a tabela da certidao. A
    ausencia do razao ou do estoque significa que nao ha suporte a recuperar;
    qualquer outro erro de banco continua subindo e desfaz a transacao.
    """
    selos: list[str] = []
    bd = banco(con)
    try:
        selos = [str(r["numero"]) for r in bd.ler(
            """SELECT numero FROM sd_selos
                 WHERE tabela=%s AND ato_id=%s AND cancelado_em IS NULL
                 ORDER BY id""",
            (str(tabela), int(ato_id)))]
        if selos:
            bd.escrever(
                """UPDATE sd_selos
                      SET cancelado_em=%s, cancelado_por=%s,
                          motivo_cancelamento=%s
                    WHERE tabela=%s AND ato_id=%s AND cancelado_em IS NULL""",
                (agora, str(usuario or "").strip() or None,
                 (motivo or "").strip(), str(tabela), int(ato_id)))
    except sqlite3.OperationalError as erro:
        if not _sem_tabela(erro):
            raise

    folhas: list[str] = []
    try:
        recuperadas = PAPEL.recuperar_do_ato(
            con, tabela=tabela, ato_id=ato_id, agora=agora,
            usuario=usuario, motivo=(motivo or "").strip())
        folhas = recuperadas["codigos"]
    except sqlite3.OperationalError as erro:
        if not _sem_tabela(erro):
            raise

    return {
        "selos_cancelados_localmente": selos,
        "folhas_recuperadas": folhas,
    }
