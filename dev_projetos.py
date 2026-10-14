"""Projetos de desenvolvimento — andamento técnico de integrações (ADMIN)."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

STATUS_EM_ANDAMENTO = "EM_ANDAMENTO"
STATUS_PAUSADO = "PAUSADO"
STATUS_CONCLUIDO = "CONCLUIDO"

STATUS_ROTULO = {
    STATUS_EM_ANDAMENTO: "Em andamento",
    STATUS_PAUSADO: "Pausado",
    STATUS_CONCLUIDO: "Concluído",
}

STATUS_VALIDOS = frozenset(STATUS_ROTULO)


def init_dev_projetos_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS dev_projetos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL UNIQUE,
            status_geral TEXT NOT NULL DEFAULT 'EM_ANDAMENTO',
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dev_projetos_andamento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            projeto_id INTEGER NOT NULL,
            texto TEXT NOT NULL,
            criado_em TEXT NOT NULL,
            autor TEXT,
            FOREIGN KEY(projeto_id) REFERENCES dev_projetos(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_dev_projetos_andamento_projeto
            ON dev_projetos_andamento(projeto_id, criado_em DESC);
        """
    )
    try:
        con.execute("ALTER TABLE dev_projetos ADD COLUMN proximo_passo TEXT")
    except sqlite3.OperationalError:
        pass


def _agora_iso(agora: datetime | str | None) -> str:
    if agora is None:
        return datetime.now().isoformat(timespec="seconds")
    if isinstance(agora, datetime):
        return agora.isoformat(timespec="seconds")
    return str(agora).strip()



def formatar_atualizado_em_local(valor: str | None) -> str:
    """Exibe timestamp ISO do banco como DD/MM/AA - HH:MM (fuso local do PC)."""
    if valor is None:
        return "—"
    bruto = str(valor).strip()
    if not bruto:
        return "—"
    try:
        normalizado = bruto
        if " " in normalizado and "T" not in normalizado:
            normalizado = normalizado.replace(" ", "T", 1)
        dt = datetime.fromisoformat(normalizado)
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime("%d/%m/%y - %H:%M")
    except ValueError:
        legivel = bruto.replace("T", " ")
        return legivel[:16] if legivel else "—"


def listar_projetos(con: sqlite3.Connection) -> list[dict[str, Any]]:
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, titulo, status_geral, proximo_passo, criado_em, atualizado_em "
        "FROM dev_projetos ORDER BY titulo COLLATE NOCASE"
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["atualizado_em_exibicao"] = formatar_atualizado_em_local(
            item.get("atualizado_em")
        )
        out.append(item)
    return out


def obter_projeto(con: sqlite3.Connection, projeto_id: int) -> sqlite3.Row | None:
    con.row_factory = sqlite3.Row
    return con.execute(
        "SELECT id, titulo, status_geral, proximo_passo, criado_em, atualizado_em "
        "FROM dev_projetos WHERE id=?",
        (int(projeto_id),),
    ).fetchone()


def listar_andamento(con: sqlite3.Connection, projeto_id: int) -> list[sqlite3.Row]:
    con.row_factory = sqlite3.Row
    return list(
        con.execute(
            "SELECT id, projeto_id, texto, criado_em, autor "
            "FROM dev_projetos_andamento WHERE projeto_id=? "
            "ORDER BY criado_em DESC, id DESC",
            (int(projeto_id),),
        ).fetchall()
    )


def alterar_status(
    con: sqlite3.Connection,
    projeto_id: int,
    status_geral: str,
    agora: datetime | str | None = None,
) -> None:
    status = (status_geral or "").strip().upper()
    if status not in STATUS_VALIDOS:
        raise ValueError(f"status invalido: {status_geral}")
    ts = _agora_iso(agora)
    cur = con.execute(
        "UPDATE dev_projetos SET status_geral=?, atualizado_em=? WHERE id=?",
        (status, ts, int(projeto_id)),
    )
    if cur.rowcount == 0:
        raise LookupError("projeto nao encontrado")

def alterar_proximo_passo(
    con: sqlite3.Connection,
    projeto_id: int,
    proximo_passo: str | None,
    agora: datetime | str | None = None,
) -> None:
    texto = (proximo_passo or "").strip() or None
    ts = _agora_iso(agora)
    cur = con.execute(
        "UPDATE dev_projetos SET proximo_passo=?, atualizado_em=? WHERE id=?",
        (texto, ts, int(projeto_id)),
    )
    if cur.rowcount == 0:
        raise LookupError("projeto nao encontrado")


def registrar_andamento(
    con: sqlite3.Connection,
    projeto_id: int,
    texto: str,
    autor: str | None = None,
    agora: datetime | str | None = None,
) -> int:
    corpo = (texto or "").strip()
    if not corpo:
        raise ValueError("texto vazio")
    ts = _agora_iso(agora)
    cur = con.execute(
        "INSERT INTO dev_projetos_andamento (projeto_id, texto, criado_em, autor) "
        "VALUES (?, ?, ?, ?)",
        (int(projeto_id), corpo, ts, (autor or "").strip() or None),
    )
    con.execute(
        "UPDATE dev_projetos SET atualizado_em=? WHERE id=?",
        (ts, int(projeto_id)),
    )
    return int(cur.lastrowid)


def _ensure_projeto_seed(
    con: sqlite3.Connection,
    spec: dict[str, Any],
    agora: datetime | str | None = None,
) -> int:
    titulo = (spec.get("titulo") or "").strip()
    if not titulo:
        raise ValueError("titulo vazio")
    status = (spec.get("status_geral") or STATUS_EM_ANDAMENTO).strip().upper()
    if status not in STATUS_VALIDOS:
        status = STATUS_EM_ANDAMENTO
    ts = _agora_iso(agora)
    row = con.execute(
        "SELECT id FROM dev_projetos WHERE titulo=?", (titulo,)
    ).fetchone()
    if row:
        pid = int(row[0])
    else:
        cur = con.execute(
            "INSERT INTO dev_projetos (titulo, status_geral, criado_em, atualizado_em) "
            "VALUES (?, ?, ?, ?)",
            (titulo, status, ts, ts),
        )
        pid = int(cur.lastrowid)
    for item in spec.get("andamento") or []:
        texto = (item.get("texto") or "").strip()
        if not texto:
            continue
        criado = (item.get("criado_em") or ts).strip()
        dup = con.execute(
            "SELECT 1 FROM dev_projetos_andamento WHERE projeto_id=? AND texto=?",
            (pid, texto),
        ).fetchone()
        if dup:
            continue
        con.execute(
            "INSERT INTO dev_projetos_andamento (projeto_id, texto, criado_em, autor) "
            "VALUES (?, ?, ?, ?)",
            (pid, texto, criado, item.get("autor")),
        )
    proximo = spec.get("proximo_passo")
    if proximo is not None:
        con.execute(
            "UPDATE dev_projetos SET proximo_passo=?, atualizado_em=? WHERE id=?",
            ((proximo or "").strip() or None, ts, pid),
        )
    return pid


def _specs_sandbox() -> list[dict[str, Any]]:
    return [
        {
            "titulo": "Homologação CRA21 (API)",
            "status_geral": STATUS_EM_ANDAMENTO,
            "proximo_passo": (
                "Homolog H4 pausado: nome do arquivo de remessa válido — já solicitado aos responsáveis (IEPTB); "
                "aguardando retorno. Depois: trazer remessa + confirmar/retorno."
            ),
            "andamento": [
                {
                    "criado_em": "2026-10-01T17:00:00",
                    "autor": "atualizacao-20261001",
                    "texto": (
                        "Versão 3.6.283: módulo Projetos com pendência explícita; CRA API/simulador no sandbox; "
                        "homolog slices 1–4 e ligação ~17k chars OK."
                    ),
                },
                {
                    "criado_em": "2026-09-20 10:00:00",
                    "texto": "Slices 1–4 da homolog CRA21; teste de ligação homolog com resposta ~17k caracteres.",
                },
                {
                    "criado_em": "2026-09-25 14:00:00",
                    "texto": "Slice H4 (remessa XML) pausado aguardando IEPTB; epic Ajuda #118 mantido em paralelo.",
                },
                {
                    "criado_em": "2026-10-01 12:00:00",
                    "texto": "Sandbox 3.6.281: telas CRA API + simulador; credencial de ensaio no sandbox (não produção).",
                },
            ],
        },
        {
            "titulo": "Integração CENPROT",
            "status_geral": STATUS_EM_ANDAMENTO,
            "proximo_passo": (
                "Credencial homolog IEPTB real + roteiro homolog (tipo CRA); "
                "conferir cancelamento nr_pedido e protocolar/custas."
            ),
            "andamento": [
                {
                    "criado_em": "2026-10-01T17:00:00",
                    "autor": "atualizacao-20261001",
                    "texto": (
                        "Sandbox 3.6.283: 129 pytest CENPROT OK; telas pendências/web e simulador :8911 ativos."
                    ),
                },
                {
                    "criado_em": "2026-09-02 10:00:00",
                    "texto": "Ordem do oficial (02/09): integrar API Resolve CENPROT (OpenAPI 2.1.0). Início: cenprot_api + cenprot_pendencias + fila cn_pendencias (6 espécies).",
                },
                {
                    "criado_em": "2026-09-03 18:00:00",
                    "texto": "Telas cenprot_web (/protesto/cenprot/pendencias), renegociações, emolumentos via API; roteiro Centrais 11/16 passos; suíte pytest CENPROT em expansão.",
                },
                {
                    "criado_em": "2026-10-01 15:30:00",
                    "texto": "Auditoria concluída: sandbox 3.6.281, 129 pytest CENPROT OK, simulador :8911 + sandbox_liga; cred cenprot.cred de ensaio no sandbox (não IEPTB).",
                },
                {
                    "criado_em": "2026-10-01 15:45:00",
                    "texto": "Parado antes da homolog real: credencial IEPTB homolog, slice documentado (paridade CRA #118), conferir nr_pedido cancelamento e protocolar/custas ponta a ponta.",
                },
                {
                    "criado_em": "2026-10-01 15:45:00",
                    "texto": "Doc Context: cenprot-integracao-status-20261001.md. Produção :8765 ainda sem pacote alinhado. Resolve (intimação) = projeto separado.",
                },
            ],
        },
        {
            "titulo": "Resolve (Protesto)",
            "status_geral": STATUS_EM_ANDAMENTO,
            "proximo_passo": (
                "Credencial/homolog Resolve (PAR IEPTB); E2E intimação digital ponta a ponta."
            ),
            "andamento": [
                {
                    "criado_em": "2026-10-01T17:00:00",
                    "autor": "atualizacao-20261001",
                    "texto": (
                        "Rotas Resolve e fila de intimação digital no sandbox; pytest web cobre telas principais."
                    ),
                },
                {
                    "criado_em": "2026-09-10 11:00:00",
                    "texto": "PT-13: rotas /protesto/resolve e credencial centrais_cred; fila de intimação digital ligada ao protesto.",
                },
                {
                    "criado_em": "2026-09-28 16:00:00",
                    "texto": "Saída de protesto parcial documentada; pytest de web cobre telas principais.",
                },
            ],
        },
        {
            "titulo": "ONR — envio de matrículas",
            "status_geral": STATUS_EM_ANDAMENTO,
            "proximo_passo": (
                "Credencial ONR + simulador 8914 ativo; fila ~1443 fichas sem endereço conferido."
            ),
            "andamento": [
                {
                    "criado_em": "2026-10-01T17:00:00",
                    "autor": "atualizacao-20261001",
                    "texto": (
                        "Export Next Cloud + simulador :8914; ~130 pytest ONR validados no sandbox."
                    ),
                },
                {
                    "criado_em": "2026-08-15 09:00:00",
                    "texto": "ri_onr_* + onr_api + export Next Cloud; simulador ONR na porta 8914.",
                },
                {
                    "criado_em": "2026-09-30 10:00:00",
                    "texto": "Suíte pytest ONR ~130 casos; pacotes JSON de exemplo validados no sandbox.",
                },
            ],
        },
        {
            "titulo": "ONR — indicador pessoal",
            "status_geral": STATUS_PAUSADO,
            "proximo_passo": (
                "Pausado: corrigir pytest web pós-export; auditar API antes de homolog."
            ),
            "andamento": [
                {
                    "criado_em": "2026-10-01T17:00:00",
                    "autor": "atualizacao-20261001",
                    "texto": (
                        "UI ri_indicador_pessoal entregue; status pausado registrado no módulo Projetos."
                    ),
                },
                {
                    "criado_em": "2026-09-05 14:00:00",
                    "texto": "UI ri_indicador_pessoal entregue; export pós-ajuste falhou em pytest web — auditar API antes de retomar.",
                },
            ],
        },
        {
            "titulo": "ONR — indicador real",
            "status_geral": STATUS_EM_ANDAMENTO,
            "proximo_passo": (
                "Endereços conferidos na fila; cred + E2E painel→central."
            ),
            "andamento": [
                {
                    "criado_em": "2026-10-01T17:00:00",
                    "autor": "atualizacao-20261001",
                    "texto": (
                        "Painel /ri/indicador-real e pacotes JSON no sandbox; exige endereço conferido."
                    ),
                },
                {
                    "criado_em": "2026-09-12 11:30:00",
                    "texto": "/ri/indicador-real + painel central ONR; pacote 52 JSON; exige endereço conferido (onr_endereco).",
                },
            ],
        },
        {
            "titulo": "ONRTDPJ",
            "status_geral": STATUS_EM_ANDAMENTO,
            "proximo_passo": (
                "Credencial PAR; homolog certidão inteiro teor adiada."
            ),
            "andamento": [
                {
                    "criado_em": "2026-10-01T17:00:00",
                    "autor": "atualizacao-20261001",
                    "texto": "Central ONRTDPJ e fila de certidões no sandbox; E2E local OK.",
                },
                {
                    "criado_em": "2026-09-18 09:00:00",
                    "texto": "Central /rcpj-rtd/onrtdpj revisada na 3.6.208; fila de certidões eletrônicas.",
                },
                {
                    "criado_em": "2026-09-25 17:00:00",
                    "texto": "Certidão inteiro teor adiada para slice posterior; E2E local OK no sandbox.",
                },
            ],
        },
        {
            "titulo": "ONRCPN (CRC)",
            "status_geral": STATUS_PAUSADO,
            "proximo_passo": (
                "Pausado: credencial CRC + lote batch; fluxos locais OK."
            ),
            "andamento": [
                {
                    "criado_em": "2026-10-01T17:00:00",
                    "autor": "atualizacao-20261001",
                    "texto": "onrcpn_api + pedidos web; fluxos locais E2E OK no sandbox.",
                },
                {
                    "criado_em": "2026-09-08 10:00:00",
                    "texto": "onrcpn_api + pedidos web; fluxos locais E2E OK.",
                },
                {
                    "criado_em": "2026-09-22 15:00:00",
                    "texto": "Carga batch CRC adiada; aguarda credencial e roteiro de homologação.",
                },
            ],
        },
    ]



ATUALIZACAO_20261001_AUTOR = "atualizacao-20261001"
ATUALIZACAO_20261001_TS = "2026-10-01T17:00:00"

PENDENCIAS_20261001: dict[str, dict[str, str]] = {
    "Homologação CRA21 (API)": {
        "andamento": (
            "Versão 3.6.283: módulo Projetos com pendência explícita; CRA API/simulador no sandbox; "
            "homolog slices 1–4 e ligação ~17k chars OK."
        ),
        "proximo_passo": (
            "Homolog H4 pausado: nome do arquivo de remessa válido — já solicitado aos responsáveis (IEPTB); "
            "aguardando retorno. Depois: trazer remessa + confirmar/retorno."
        ),
    },
    "Integração CENPROT": {
        "andamento": (
            "Sandbox 3.6.283: 129 pytest CENPROT OK; telas pendências/web e simulador :8911 ativos."
        ),
        "proximo_passo": (
            "Credencial homolog IEPTB real + roteiro homolog (tipo CRA); "
            "conferir cancelamento nr_pedido e protocolar/custas."
        ),
    },
    "Resolve (Protesto)": {
        "andamento": (
            "Rotas Resolve e fila de intimação digital no sandbox; pytest web cobre telas principais."
        ),
        "proximo_passo": (
            "Credencial/homolog Resolve (PAR IEPTB); E2E intimação digital ponta a ponta."
        ),
    },
    "ONR — envio de matrículas": {
        "andamento": (
            "Export Next Cloud + simulador :8914; ~130 pytest ONR validados no sandbox."
        ),
        "proximo_passo": (
            "Credencial ONR + simulador 8914 ativo; fila ~1443 fichas sem endereço conferido."
        ),
    },
    "ONR — indicador pessoal": {
        "andamento": (
            "UI ri_indicador_pessoal entregue; status pausado registrado no módulo Projetos."
        ),
        "proximo_passo": (
            "Pausado: corrigir pytest web pós-export; auditar API antes de homolog."
        ),
    },
    "ONR — indicador real": {
        "andamento": (
            "Painel /ri/indicador-real e pacotes JSON no sandbox; exige endereço conferido."
        ),
        "proximo_passo": (
            "Endereços conferidos na fila; cred + E2E painel→central."
        ),
    },
    "ONRTDPJ": {
        "andamento": (
            "Central ONRTDPJ e fila de certidões no sandbox; E2E local OK."
        ),
        "proximo_passo": (
            "Credencial PAR; homolog certidão inteiro teor adiada."
        ),
    },
    "ONRCPN (CRC)": {
        "andamento": (
            "onrcpn_api + pedidos web; fluxos locais E2E OK no sandbox."
        ),
        "proximo_passo": (
            "Pausado: credencial CRC + lote batch; fluxos locais OK."
        ),
    },
}


def aplicar_atualizacao_pendencias_20261001(
    con: sqlite3.Connection,
    agora: datetime | str | None = None,
) -> int:
    """Idempotente: proximo_passo + andamento (autor atualizacao-20261001) por título."""
    ts = _agora_iso(agora or ATUALIZACAO_20261001_TS)
    aplicados = 0
    for titulo, payload in PENDENCIAS_20261001.items():
        row = con.execute(
            "SELECT id FROM dev_projetos WHERE titulo=?", (titulo,)
        ).fetchone()
        if not row:
            continue
        pid = int(row[0])
        pp = (payload.get("proximo_passo") or "").strip()
        if pp:
            con.execute(
                "UPDATE dev_projetos SET proximo_passo=?, atualizado_em=? WHERE id=?",
                (pp, ts, pid),
            )
        texto = (payload.get("andamento") or "").strip()
        if texto:
            dup = con.execute(
                "SELECT 1 FROM dev_projetos_andamento WHERE projeto_id=? AND autor=? AND texto=?",
                (pid, ATUALIZACAO_20261001_AUTOR, texto),
            ).fetchone()
            if not dup:
                registrar_andamento(
                    con,
                    pid,
                    texto,
                    autor=ATUALIZACAO_20261001_AUTOR,
                    agora=ts,
                )
        aplicados += 1
    return aplicados


def seed_sandbox_exemplo(
    con: sqlite3.Connection,
    agora: datetime | str | None = None,
) -> None:
    for spec in _specs_sandbox():
        _ensure_projeto_seed(con, spec, agora=agora)


def atualizar_andamento_cenprot(con: sqlite3.Connection) -> int | None:
    """Substitui stub antigo do projeto CENPROT pelo seed auditado."""
    specs = [s for s in _specs_sandbox() if s["titulo"] == "Integração CENPROT"]
    if not specs:
        return None
    row = con.execute(
        "SELECT id FROM dev_projetos WHERE titulo=?", ("Integração CENPROT",)
    ).fetchone()
    if row:
        pid = int(row[0])
        con.execute("DELETE FROM dev_projetos_andamento WHERE projeto_id=?", (pid,))
    else:
        pid = None
    pid = _ensure_projeto_seed(con, specs[0])
    return pid
