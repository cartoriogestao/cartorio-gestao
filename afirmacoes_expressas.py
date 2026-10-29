"""AS AFIRMAÇÕES EXPRESSAS — quando a escrevente insiste no que a regra diz que é erro.

ORDEM DO OFICIAL, 29/10/2026: *«trabalhamos com mao de obra muito propensa a
erros e precisamos revisar os processos para nao permitir que a mao de obra
erre. [...] se insistir em algo que eh erro, precisa afirmar expressamente e
deixar log.»*

O CONTRATO É UM SÓ, e quem trava escreve por ele — a rota, logo depois da
transação, porque `audit` abre a sua própria:

    audit("AFIRMACAO_EXPRESSA", entity_type, entity_id,
          {"regra": "...", "afirmacao": "...", "o_que_faltava": "..."})

`regra` é o nome curto da trava (o que se filtra na tela); `afirmacao` é o que
a pessoa escreveu ao insistir; `o_que_faltava` é o que a regra cobrava e não
estava lá. Uma linha só em `audit_logs`, e não tabela própria: a auditoria já
guarda quem, quando e de onde, e uma segunda tabela seria a segunda versão do
mesmo fato.

ESTE MÓDULO SÓ LÊ. Ele não decide o que é erro (quem decide é a trava de cada
módulo) nem apaga afirmação nenhuma: o que se afirmou fica, e é isso que o
oficial confere.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from typing import Any

from bd_nativo import banco

ACAO = "AFIRMACAO_EXPRESSA"

#: O contador do painel do roteiro conta a última semana.
DIAS_DO_CONTADOR = 7
#: A tela abre nos últimos trinta dias, e o filtro muda isso.
DIAS_DA_TELA = 30
#: O teto da tela. Passou dele, a tela diz — e não esconde que cortou.
LIMITE = 1000

SEM_REGRA = "(sem regra declarada)"

#: O PISO DA AFIRMACAO: LETRAS, e nao caracteres — «.......» nao e afirmacao
#: de ninguem. O mesmo das outras travas da reestruturacao de 29/10/2026.
MINIMO_DE_LETRAS = 30
MODELO = "Afirmo, sob minha responsabilidade, que"


class AfirmacaoError(ValueError):
    """A afirmacao nao cumpre o contrato — a frase diz o que falta."""


def letras(texto: Any) -> int:
    """Quantas letras o texto tem. Espaco, pontuacao e numero nao contam."""
    return sum(1 for ch in str(texto or "") if ch.isalpha())


def validar(afirmo: Any, afirmacao: Any, *, por_que: str = "") -> str:
    """O contrato comum: a caixa «Afirmo» marcada E pelo menos 30 letras.

    Devolve o texto limpo, ou recusa dizendo o que falta. Quem grava a
    auditoria e a rota, depois da transacao (`audit` abre a sua).
    """
    texto = " ".join(str(afirmacao or "").split())
    if afirmo and letras(texto) >= MINIMO_DE_LETRAS:
        return texto
    falta = []
    if not afirmo:
        falta.append("marque a caixa «Afirmo»")
    if letras(texto) < MINIMO_DE_LETRAS:
        falta.append(f"escreva a afirmação com pelo menos {MINIMO_DE_LETRAS} "
                     f"letras (vieram {letras(texto)})")
    raise AfirmacaoError(
        (por_que + " " if por_que else "") + "Para seguir, "
        + " e ".join(falta) + f", começando por «{MODELO}…». Ela fica gravada "
        f"com o seu nome.")


def _detalhes(texto: Any) -> dict:
    """Os detalhes gravados. Linha fora do contrato não some: vira afirmação."""
    try:
        lido = json.loads(texto or "{}")
    except (TypeError, ValueError):
        return {"afirmacao": str(texto or "")}
    return lido if isinstance(lido, dict) else {"afirmacao": str(lido)}


def periodo_padrao(hoje: str) -> tuple[str, str]:
    """De trinta dias atrás até hoje, em AAAA-MM-DD."""
    fim = date.fromisoformat(str(hoje)[:10])
    return (fim - timedelta(days=DIAS_DA_TELA)).isoformat(), fim.isoformat()


def _data(texto: Any, padrao: str) -> str:
    """O dia do filtro, ou o padrão quando o que veio não é data."""
    try:
        return date.fromisoformat(str(texto or "").strip()[:10]).isoformat()
    except ValueError:
        return padrao


def listar(con: sqlite3.Connection, *, hoje: str, de: Any = None,
           ate: Any = None, regra: Any = None) -> dict:
    """As afirmações do período, da mais nova para a mais antiga. Só LÊ.

    O período é por TEXTO, como no resto da casa: `ts` guarda
    `2026-10-29T11:00:00`, e `ate + '~'` apanha o dia inteiro (`~` vem depois
    de todo dígito e do `T`). A regra se filtra depois de ler, em Python — ela
    mora dentro do JSON, e operador de JSON no SQL seria acoplamento ao banco.
    """
    padrao_de, padrao_ate = periodo_padrao(hoje)
    de, ate = _data(de, padrao_de), _data(ate, padrao_ate)
    if de > ate:
        de, ate = ate, de
    regra = str(regra or "").strip()
    saida = {"de": de, "ate": ate, "regra": regra, "linhas": [],
             "regras": [], "cortado": False, "total": 0}
    if not banco(con).tem_tabela("audit_logs"):
        saida["total"] = None
        return saida
    lidas = banco(con).ler(
        """SELECT id, ts, username_snapshot, entity_type, entity_id, details
             FROM audit_logs
            WHERE action = %s AND ts >= %s AND ts < %s
            ORDER BY id DESC LIMIT %s""", (ACAO, de, ate + "~", LIMITE + 1))
    saida["cortado"] = len(lidas) > LIMITE
    regras = set()
    for linha in lidas[:LIMITE]:
        d = _detalhes(linha["details"])
        nome = str(d.get("regra") or "").strip() or SEM_REGRA
        regras.add(nome)
        if regra and nome != regra:
            continue
        saida["linhas"].append({
            "id": linha["id"], "ts": str(linha["ts"] or ""),
            "quem": linha["username_snapshot"] or "sistema",
            "regra": nome,
            "entidade": linha["entity_type"] or "",
            "entidade_id": (linha["entity_id"]
                            if linha["entity_id"] is not None
                            else d.get("entidade", "")),
            "afirmacao": str(d.get("afirmacao") or ""),
            "o_que_faltava": str(d.get("o_que_faltava") or "")})
    saida["regras"] = sorted(regras)
    saida["total"] = len(saida["linhas"])
    return saida


def contar(con: sqlite3.Connection, *, hoje: str) -> int | None:
    """Quantas afirmações nos últimos sete dias. `None` sem a tabela."""
    if not banco(con).tem_tabela("audit_logs"):
        return None
    desde = (date.fromisoformat(str(hoje)[:10])
             - timedelta(days=DIAS_DO_CONTADOR)).isoformat()
    return int(banco(con).valor(
        "SELECT COUNT(*) FROM audit_logs WHERE action = %s AND ts >= %s",
        (ACAO, desde)) or 0)
