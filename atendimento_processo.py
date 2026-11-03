"""A prenotação e o protocolo de recepção de um processo longo.

A retificação e o usucapião já tinham as colunas (`prenotacao`, `protocolo_id`)
e nenhuma tela as preenchia. O protocolo é o do Caixa — o atendimento em que
o título entrou, no formato `2026.10.158`. A prenotação é a do Livro 1 da
matrícula.

PRENOTAÇÃO VENCIDA SEGUE VALENDO. O prazo do Livro 1 pode ter passado e o
título continua sendo aquele: tirar a vencida da lista faria o processo nascer
sem o número que o cliente já tem na mão. Cancelada é outra coisa — essa não
se liga.
"""
from __future__ import annotations

from typing import Any

from bd_nativo import banco


class AtendimentoError(ValueError):
    """O que se pediu não é prenotação desta matrícula, nem protocolo do Caixa."""


def _hoje(hoje: str | None) -> str:
    return str(hoje or "")[:10]


def vencida(linha: dict, *, hoje: str) -> bool:
    """O prazo do Livro 1 passou e a prenotação não foi encerrada. Só calcula."""
    limite = str(linha.get("data_limite") or "")[:10]
    situacao = str(linha.get("situacao") or "").upper()
    if situacao in ("ENCERRADO", "CANCELADO") or not limite or not _hoje(hoje):
        return False
    return limite < _hoje(hoje)


def rotulo_da_prenotacao(linha: dict, *, hoje: str) -> str:
    numero = linha.get("numero") or linha.get("id")
    livro = linha.get("livro") or "1"
    situacao = str(linha.get("situacao") or "").lower()
    extra = "vencida — segue valendo" if vencida(linha, hoje=hoje) else situacao
    return f"{numero}/{livro} ({extra})"


def prenotacoes_da_matricula(con, matricula_id: int, *,
                             hoje: str) -> list[dict]:
    """As prenotações desta matrícula, vencidas inclusive. Só lê.

    Cancelada fica de fora: não há o que aproveitar. As outras entram, com o
    prazo estourado ou não.
    """
    if not matricula_id:
        return []
    bd = banco(con)
    if not bd.tem_tabela("ri_protocolos"):
        return []
    linhas = bd.ler(
        """SELECT id, numero, livro, situacao, data_limite, data_prenotacao,
                  matricula_id
             FROM ri_protocolos
            WHERE matricula_id = %s
              AND COALESCE(situacao, '') <> 'CANCELADO'
            ORDER BY numero DESC, id DESC""",
        (int(matricula_id),))
    saida = []
    for linha in linhas:
        item = dict(linha)
        item["vencida"] = vencida(item, hoje=hoje)
        item["rotulo"] = rotulo_da_prenotacao(item, hoje=hoje)
        saida.append(item)
    return saida


def buscar_protocolos(con, termo: str, *, limite: int = 20
                      ) -> tuple[list[dict], bool]:
    """Protocolos do Caixa pelo número (`2026.10.158`). Só lê.

    O número é exato quando se digita ele inteiro, e o começo enquanto se
    digita. Não varre o nome de quem foi atendido: protocolo de recepção se
    acha pelo número.
    """
    texto = " ".join(str(termo or "").split())
    if len(texto) < 4:
        return [], False
    bd = banco(con)
    if not bd.tem_tabela("cx_protocolos"):
        return [], False
    teto = max(1, min(int(limite), 20))
    linhas = bd.ler(
        """SELECT id, numero, interessado, atribuicao, situacao
             FROM cx_protocolos
            WHERE numero = %s OR numero ILIKE %s
            ORDER BY CASE WHEN numero = %s THEN 0 ELSE 1 END, numero DESC, id
            LIMIT %s""",
        (texto, texto + "%", texto, teto + 1))
    ha_mais = len(linhas) > teto
    saida = []
    for linha in linhas[:teto]:
        item = dict(linha)
        quem = item.get("interessado") or ""
        item["rotulo"] = f"{item['numero']}" + (f" — {quem}" if quem else "")
        saida.append(item)
    return saida, ha_mais


def _um_protocolo(bd, protocolo_id: int) -> dict | None:
    return bd.um(
        """SELECT id, numero, interessado, atribuicao, situacao
             FROM cx_protocolos WHERE id = %s""",
        (int(protocolo_id),))


def resolver(con, *, matricula_id: int | None, prenotacao_id: Any,
             protocolo_id: Any, protocolo_busca: str, hoje: str) -> dict:
    """O par que o processo vai guardar. Só lê.

    Os dois são opcionais. Preenchido, cada um tem de existir: a prenotação
    na matrícula deste processo (vencida serve), o protocolo pelo id ou pelo
    número do Caixa.
    """
    bd = banco(con)
    prenotacao = None
    bruto_pre = str(prenotacao_id or "").strip()
    if bruto_pre:
        if not bruto_pre.isdigit():
            raise AtendimentoError("A prenotação indicada não é um número.")
        linha = bd.um("SELECT * FROM ri_protocolos WHERE id = %s", (int(bruto_pre),))
        if not linha:
            raise AtendimentoError("Não achei essa prenotação.")
        if str(linha.get("situacao") or "").upper() == "CANCELADO":
            raise AtendimentoError(
                f"A prenotação {linha.get('numero')} está cancelada e não se "
                "liga ao processo.")
        if matricula_id and int(linha.get("matricula_id") or 0) != int(matricula_id):
            raise AtendimentoError(
                f"A prenotação {linha.get('numero')} não é da matrícula deste "
                "processo. A lista só oferece as dela, vencidas inclusive.")
        prenotacao = dict(linha)
        prenotacao["rotulo"] = rotulo_da_prenotacao(prenotacao, hoje=hoje)

    protocolo = None
    bruto_id = str(protocolo_id or "").strip()
    busca = " ".join(str(protocolo_busca or "").split())
    if busca:
        achados, _ = buscar_protocolos(bd, busca, limite=20)
        exatos = [a for a in achados if str(a.get("numero") or "") == busca]
        if len(exatos) == 1:
            protocolo = exatos[0]
        elif not exatos:
            raise AtendimentoError(
                f"Não achei protocolo de recepção com o número «{busca}». "
                "O número é o do Caixa, como 2026.10.158.")
        else:
            raise AtendimentoError(
                f"Há mais de um protocolo «{busca}». Escolha na lista.")
    elif bruto_id:
        if not bruto_id.isdigit():
            raise AtendimentoError("O protocolo indicado não é um número.")
        protocolo = _um_protocolo(bd, int(bruto_id))
        if not protocolo:
            raise AtendimentoError("Não achei esse protocolo de recepção.")

    return {
        "prenotacao_id": int(prenotacao["id"]) if prenotacao else None,
        "prenotacao": str(prenotacao["numero"]) if prenotacao else None,
        "protocolo_id": int(protocolo["id"]) if protocolo else None,
        "protocolo_numero": str(protocolo["numero"]) if protocolo else None,
    }
