"""AS AVERBAÇÕES DE CANCELAMENTO QUE NÃO MARCARAM O ATO CANCELADO — a lista para o oficial conferir. SÓ LÊ.

O PEDIDO (o oficial, 03/11/2026, respondendo ao ensaio de atos do RI, defeito 1, «a1»): os modelos de
cancelamento e de extinção passam a pedir «qual ato se cancela» e a gravar a mesma marca do botão
«Cancelar este ato» (`ri_atos.cancelado`, `cancelado_por_ato_id`). «Para as matrículas antigas, faça a
lista das averbações lavradas por esses modelos, para conferir.»

O QUE A LISTA TRAZ
    Cada averbação lavrada por um desses modelos — ou com a natureza de cancelamento ou de extinção — que
    não é o `cancelado_por_ato_id` de ato nenhum. Ao lado, os rótulos que o texto dela cita (R-02, AV-03…)
    e se cada um ainda está de pé: é o candidato a marcar. Quem marca é o oficial, pelo botão «Cancelar
    este ato» da ficha ou por correção de ofício; esta lista não escreve nada.

USO, no servidor, com o ambiente do serviço:

    python ri_cancelamentos_sem_marca.py
"""
from __future__ import annotations

import re
import sys
import unicodedata

from bd_nativo import banco

#: Os mesmos modelos de `ri_web.MODELOS_QUE_CANCELAM` (lá ficam dentro do registro das rotas).
MODELOS_QUE_CANCELAM = ("AV-CANCELAMENTO-HIPOTECA", "AV-EXTINCAO-USUFRUTO", "AV-CANCELAMENTO")

_ROTULO = re.compile(r"\b(R|AV)-?\s*0*(\d{1,4})\b")


def _sem_acento(texto) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(texto or ""))
                   if unicodedata.category(c) != "Mn").lower()


def _e_de_cancelamento(ato: dict) -> bool:
    if str(ato.get("modelo_codigo") or "").upper() in MODELOS_QUE_CANCELAM:
        return True
    natureza = _sem_acento(ato.get("natureza_titulo"))
    return "cancelamento" in natureza or "extincao" in natureza


def listar(con) -> list[dict]:
    """As averbações de cancelamento ou extinção sem ato marcado, com os candidatos citados no texto."""
    bd = banco(con)
    marcadas = {int(r["cancelado_por_ato_id"]) for r in bd.ler(
        "SELECT cancelado_por_ato_id FROM ri_atos WHERE cancelado_por_ato_id IS NOT NULL", ())}
    saida = []
    for av in bd.ler(
            """SELECT a.*, m.numero AS matricula_numero FROM ri_atos a
                 JOIN ri_matriculas m ON m.id = a.matricula_id
                WHERE a.tipo = 'AV' AND COALESCE(a.cancelado, 0) = 0
                ORDER BY m.numero, a.numero""", ()):
        av = dict(av)
        if int(av["id"]) in marcadas or not _e_de_cancelamento(av):
            continue
        citados = []
        for tipo, numero in _ROTULO.findall(str(av.get("teor") or "")):
            if (tipo, int(numero)) == ("AV", int(av["numero"] or 0)):
                continue
            alvo = bd.um("""SELECT id, tipo, numero, natureza_titulo, cancelado FROM ri_atos
                             WHERE matricula_id = %s AND tipo = %s AND numero = %s""",
                         (av["matricula_id"], tipo, int(numero)))
            if alvo and all(c["id"] != alvo["id"] for c in citados):
                citados.append(dict(alvo))
        saida.append({"matricula": av["matricula_numero"], "averbacao_id": av["id"],
                      "rotulo": f"AV-{int(av['numero'] or 0):02d}", "data": av.get("data_ato"),
                      "natureza": av.get("natureza_titulo"), "modelo": av.get("modelo_codigo"),
                      "citados": citados})
    return saida


def em_texto(linhas: list[dict]) -> str:
    if not linhas:
        return "Nenhuma averbação de cancelamento ou extinção sem o ato marcado."
    partes = [f"{len(linhas)} averbação(ões) de cancelamento ou extinção sem o ato marcado:"]
    for x in linhas:
        cit = "; ".join(
            f"{c['tipo']}-{int(c['numero']):02d} ({c['natureza_titulo'] or 'sem natureza'}, "
            f"{'JÁ CANCELADO' if c['cancelado'] else 'de pé — candidato'})" for c in x["citados"]
        ) or "o texto não cita rótulo desta matrícula"
        partes.append(f"- Matrícula {x['matricula']}, {x['rotulo']} de {x['data'] or 's/d'} — "
                      f"{x['natureza'] or 'sem natureza'}"
                      f"{(' [' + x['modelo'] + ']') if x['modelo'] else ''}: {cit}")
    return "\n".join(partes)


def main() -> int:
    from admin_cli import data_dir
    from database import Database
    db = Database(data_dir() / "cartorio_gestao.sqlite3")
    with db.connect() as con:
        print(em_texto(listar(con)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
