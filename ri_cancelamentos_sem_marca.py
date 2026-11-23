"""AS AVERBAÇÕES DE CANCELAMENTO QUE NÃO MARCARAM O ATO CANCELADO — a lista para o oficial conferir. SÓ LÊ.

O PEDIDO (o oficial, 03/11/2026, respondendo ao ensaio de atos do RI, defeito 1, «a1»): os modelos de
cancelamento e de extinção passam a pedir «qual ato se cancela» e a gravar a mesma marca do botão
«Cancelar este ato» (`ri_atos.cancelado`, `cancelado_por_ato_id`). «Para as matrículas antigas, faça a
lista das averbações lavradas por esses modelos, para conferir.»

O QUE A LISTA TRAZ
    Cada averbação lavrada por um desses modelos — ou com a natureza de cancelamento, extinção ou
    baixa — que não é o `cancelado_por_ato_id` de ato nenhum. Ao lado, os rótulos que o texto dela
    cita (R-02, AV-03…) e se cada um ainda está de pé: é o candidato a marcar. Quem marca é o
    oficial, pelo botão «Cancelar este ato» da ficha ou por correção de ofício; esta lista não
    escreve nada.

USO, no servidor, com o ambiente do serviço:

    python ri_cancelamentos_sem_marca.py
    python ri_cancelamentos_sem_marca.py --acervo
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata

from bd_nativo import banco
from ri_schema import matricula_de_acervo

#: Os mesmos modelos de `ri_web.MODELOS_QUE_CANCELAM` (lá ficam dentro do registro das rotas).
MODELOS_QUE_CANCELAM = ("AV-CANCELAMENTO-HIPOTECA", "AV-EXTINCAO-USUFRUTO", "AV-CANCELAMENTO")

_ROTULO = re.compile(r"\b(R|AV)-?\s*0*(\d{1,4})\b", re.I)

# Palavras que, na natureza ou no começo do teor, apontam cancelamento/baixa/extinção.
_MARCAS_DE_CANCELAMENTO = (
    "cancelamento", "cancelado", "cancela o", "cancela a", "cancela os", "cancela as",
    "extincao", "extinto", "baixa", "baixado", "baixad",
    "quitacao", "quitado", "totalmente liberado",
)


def _sem_acento(texto) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(texto or ""))
                   if unicodedata.category(c) != "Mn").lower()


def e_de_cancelamento(ato: dict | None = None, *, natureza=None, teor=None,
                      modelo=None) -> bool:
    """Modelo de cancelamento/extinção, natureza de baixa/cancelamento, ou teor que baixa."""
    if ato is not None:
        natureza = ato.get("natureza_titulo") if natureza is None else natureza
        teor = ato.get("teor") if teor is None else teor
        modelo = ato.get("modelo_codigo") if modelo is None else modelo
    if str(modelo or "").upper() in MODELOS_QUE_CANCELAM:
        return True
    # Natureza curta decide sozinha; no teor só a janela inicial — o resto da ficha
    # de acervo cita cancelamentos históricos sem ser a averbação que cancela.
    blob = _sem_acento(natureza or "")
    if any(p in blob for p in ("cancelamento", "extincao", "baixa", "quitacao")):
        return True
    inicio = _sem_acento((teor or "")[:800])
    return any(p in inicio for p in _MARCAS_DE_CANCELAMENTO)


def _e_de_cancelamento(ato: dict) -> bool:
    """Compatível com o nome antigo usado pelos testes."""
    return e_de_cancelamento(ato)


def citados_do_teor(bd, matricula_id: int, teor, *, av_numero=None) -> list[dict]:
    """Os R/AV desta matrícula que o teor cita, na ordem em que aparecem (sem repetir)."""
    citados: list[dict] = []
    for tipo, numero in _ROTULO.findall(str(teor or "")):
        tipo = tipo.upper()
        n = int(numero)
        if av_numero is not None and (tipo, n) == ("AV", int(av_numero or 0)):
            continue
        alvo = bd.um("""SELECT id, tipo, numero, natureza_titulo, cancelado FROM ri_atos
                         WHERE matricula_id = %s AND tipo = %s AND numero = %s""",
                     (matricula_id, tipo, n))
        if alvo and all(c["id"] != alvo["id"] for c in citados):
            citados.append(dict(alvo))
    return citados


def ids_do_formulario(form) -> list[int]:
    """Um ou vários `cancela_ato_id` do formulário (select múltiplo ou checkboxes)."""
    vistos: list[int] = []
    brutos = []
    if hasattr(form, "getlist"):
        brutos = list(form.getlist("cancela_ato_id") or [])
    if not brutos:
        um = form.get("cancela_ato_id") if hasattr(form, "get") else None
        if um:
            brutos = [um]
    for raw in brutos:
        digitos = "".join(c for c in str(raw or "") if c.isdigit())
        if not digitos:
            continue
        n = int(digitos)
        if n not in vistos:
            vistos.append(n)
    return vistos


def listar(con, *, so_acervo: bool = False) -> list[dict]:
    """As averbações de cancelamento, extinção ou baixa sem ato marcado, com os candidatos citados."""
    bd = banco(con)
    marcadas = {int(r["cancelado_por_ato_id"]) for r in bd.ler(
        "SELECT cancelado_por_ato_id FROM ri_atos WHERE cancelado_por_ato_id IS NOT NULL", ())}
    saida = []
    for av in bd.ler(
            """SELECT a.*, m.numero AS matricula_numero, m.tipo_ficha
                 FROM ri_atos a
                 JOIN ri_matriculas m ON m.id = a.matricula_id
                WHERE a.tipo = 'AV' AND COALESCE(a.cancelado, 0) = 0
                ORDER BY m.numero, a.numero""", ()):
        av = dict(av)
        if int(av["id"]) in marcadas or not e_de_cancelamento(av):
            continue
        if so_acervo:
            tipo_ficha = (av.get("tipo_ficha") or "").upper()
            if tipo_ficha != "ACERVO" and not matricula_de_acervo(av.get("matricula_numero")):
                continue
        citados = citados_do_teor(bd, av["matricula_id"], av.get("teor"),
                                   av_numero=av.get("numero"))
        saida.append({"matricula": av["matricula_numero"], "averbacao_id": av["id"],
                      "rotulo": f"AV-{int(av['numero'] or 0):02d}", "data": av.get("data_ato"),
                      "natureza": av.get("natureza_titulo"), "modelo": av.get("modelo_codigo"),
                      "tipo_ficha": av.get("tipo_ficha"), "citados": citados})
    return saida


def em_texto(linhas: list[dict]) -> str:
    if not linhas:
        return "Nenhuma averbação de cancelamento, extinção ou baixa sem o ato marcado."
    partes = [f"{len(linhas)} averbação(ões) de cancelamento, extinção ou baixa sem o ato marcado:"]
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
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--acervo", action="store_true",
                    help="só matrículas de acervo (tipo_ficha ACERVO ou número de acervo)")
    args = ap.parse_args()
    from admin_cli import data_dir
    from database import Database
    db = Database(data_dir() / "cartorio_gestao.sqlite3")
    with db.connect() as con:
        print(em_texto(listar(con, so_acervo=args.acervo)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
