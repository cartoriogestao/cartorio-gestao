"""O texto didático das tarefas do gestor (06/10/2026).

Pedido do oficial: «precisa ficar bem claro o que foi errado, como resolver e
onde acessar o ato com erro». Guarda-se: as três partes existem, o número interno
da linha não aparece, a data sai como se lê, e a tela transforma o endereço em
link — só os do sistema.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import gestor_conferencia as GC                                  # noqa: E402
import gestor_didatica as D                                      # noqa: E402
from gestor_schema import init_gestor_schema                     # noqa: E402

AGORA = "2026-10-06T08:00:00"


def test_limpar_tira_o_que_so_o_programa_entende():
    assert D.limpar("ri_minutas 14: texto com campo") == "Texto com campo"
    assert D.limpar("R-1 (matrícula id 5385) sem consulta") == "R-1 sem consulta"
    assert D.limpar("lavrado em 2026-09-23.") == "Lavrado em 23/09/2026."


def test_a_tarefa_diz_por_que_como_e_onde(cg_casa):
    con = sqlite3.connect(cg_casa["banco"])
    con.row_factory = sqlite3.Row
    init_gestor_schema(con)
    mid = con.execute("INSERT INTO ri_matriculas (numero, teor, criado_em) VALUES "
                      "('4019', 'CCIR: [INSERIR APÓS]', ?)", (AGORA,)).lastrowid
    a = {"chave": f"MARCADOR:ri_matriculas:{mid}", "regra": "MODELO_NAO_PREENCHIDO",
         "gravidade": "CRITICO", "setor": "RI_QUALIFICACAO", "prazo": None,
         "titulo": f"ri_matriculas {mid}: texto com campo de modelo não preenchido",
         "detalhe": "Marcadores no texto: [INSERIR APÓS].", "fundamento": ""}
    t = D.descricao(con, "MODELO_NAO_PREENCHIDO", [a], list(GC.GRAVIDADES))
    con.close()
    assert "POR QUE ESTA TAREFA EXISTE" in t and "COMO RESOLVER" in t
    assert "1. [CRÍTICO] Matrícula 4019" in t
    assert f"Onde abrir: Registro de Imóveis → Matrícula 4019 — /registro-imoveis/{mid}" in t
    assert "ri_matriculas" not in t


def test_a_tela_da_tarefa_poe_link_so_no_endereco_do_sistema(cg_casa_logada):
    con = sqlite3.connect(cg_casa_logada["banco"])
    tid = con.execute(
        """INSERT INTO tasks (source_type, source_ref, title, description, status,
               priority, created_at, updated_at)
           VALUES ('GESTOR', 'GESTOR:X:RI', 'T',
                   'Onde abrir: x — /registro-imoveis/12 e <b>http://fora/caixa</b>',
                   'ABERTA', 'MEDIA', ?, ?)""", (AGORA, AGORA)).lastrowid
    con.commit()
    con.close()
    html = cg_casa_logada["c"].get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "O que fazer" in html
    assert '<a href="/registro-imoveis/12">/registro-imoveis/12</a>' in html
    assert "<b>http" not in html                      # o texto é escapado
