"""A ficha redigitalizada depois de cada ato — prazo de 7 dias corridos.

    «criar uma trava que cria tarefa, aviso chamativo e notificação de
     administrador no caso de lavratura de registro ou averbação no RI sem nova
     digitalização da ficha no prazo de 7 dias corridos» — o oficial, 06/10/2026

A DATA QUE VALE É A DA IMAGEM, E NÃO A DO CADASTRO
    Medido em 06/10/2026: a «Importação pasta 7» de 03/10 regravou
    `ri_matriculas.digi_em` em dezenas de fichas, e em duas delas (3247 e 4004)
    o arquivo importado é de 27/09 — ANTERIOR ao ato de 28/09. Pela coluna, as
    duas estariam em dia; pela imagem, o ato não está nela. Por isso a régua é
    a data do arquivo (`digi_path`), e a coluna só vale quando o arquivo falta.

O QUE ESTE MÓDULO FAZ: só mede. Quem cobra é o gestor (tarefa, prioridade,
notificação ao administrador) e quem avisa é a tela. Ele não impede lavrar:
balcão parado por falta de escâner é pior que ficha atrasada — e a cobrança
cresce todo dia até a imagem entrar.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any

from bd_nativo import banco

PRAZO_DIAS = 7
#: Os atos que este sistema lavrou depois que ele entrou em uso (o corte do oficial).
DESDE = "2026-09-10"


def data_da_imagem(caminho: str | None, digi_em: str | None) -> str | None:
    """Quando a imagem foi feita: a do arquivo; sem arquivo, a do cadastro."""
    if caminho and os.path.exists(caminho):
        return datetime.fromtimestamp(os.path.getmtime(caminho)).isoformat(timespec="seconds")
    return digi_em or None


def pendentes(con: Any, hoje: date | None = None) -> list[dict]:
    """Fichas com R ou AV lavrado depois da última imagem. Só LÊ."""
    hoje = hoje or date.today()
    fichas: dict[int, dict] = {}
    for r in banco(con).ler(
            """SELECT m.id, m.numero, m.digi_em, m.digi_path, a.tipo, a.numero AS num,
                      a.lavrado_em
                 FROM ri_atos a JOIN ri_matriculas m ON m.id = a.matricula_id
                WHERE a.lavrado_em >= %s AND COALESCE(a.acervo,0) = 0
                  AND COALESCE(a.cancelado,0) = 0 AND a.tipo IN ('R','AV')
                ORDER BY a.lavrado_em, a.id""", (DESDE,)):
        mid, numero, digi_em, caminho = r["id"], r["numero"], r["digi_em"], r["digi_path"]
        tipo, num, lavrado = r["tipo"], r["num"], r["lavrado_em"]
        f = fichas.setdefault(mid, {"numero": numero, "digi_em": digi_em,
                                    "caminho": caminho, "atos": []})
        f["atos"].append((f"{tipo}-{num}", lavrado))
    saida = []
    for mid, f in fichas.items():
        numero, digi_em, caminho = f["numero"], f["digi_em"], f["caminho"]
        imagem = data_da_imagem(caminho, digi_em)
        ultimo = f["atos"][-1][1]
        # SÓ OS ATOS QUE A IMAGEM NÃO TEM — os de antes dela estão nela.
        fora = [(r, quando) for r, quando in f["atos"] if not imagem or quando > imagem]
        if imagem and imagem >= ultimo:
            continue
        quais = ", ".join(r for r, _ in fora)
        # O PRAZO CONTA DO PRIMEIRO ATO QUE FICOU FORA DA IMAGEM: contar do
        # último faria cada ato novo empurrar o prazo para a frente.
        lavrado = date.fromisoformat(fora[0][1][:10])
        prazo = lavrado + timedelta(days=PRAZO_DIAS)
        saida.append({"matricula_id": mid, "numero": numero, "atos": quais,
                      "ultimo_ato": ultimo, "imagem": imagem, "prazo": prazo,
                      "vencida": hoje > prazo, "dias": (hoje - lavrado).days})
    return sorted(saida, key=lambda p: p["prazo"])

