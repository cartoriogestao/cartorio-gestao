"""Avisos gerenciÃ¡veis (ADMIN) com dispensa diÃ¡ria por usuÃ¡rio.
Regra de pendÃªncia (N na barra e modal): avisos **ativos** e **vigentes**
(hoje entre vigencia_inicio e vigencia_fim, se informadas) que o usuÃ¡rio **nÃ£o
dispensou hoje** (`nu_aviso_dispensa.data_local` = YYYY-MM-DD local).
MÃ³dulo Ãºnico de avisos overlay/barra â sem aviso fixo FERJ/FERC (removido 3.6.247).
"""
from __future__ import annotations
import os
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any
SCHEMA = """
CREATE TABLE IF NOT EXISTS nu_avisos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    corpo TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1,
    prioridade INTEGER NOT NULL DEFAULT 0,
    vigencia_inicio TEXT,
    vigencia_fim TEXT,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    criado_por TEXT
);
CREATE TABLE IF NOT EXISTS nu_aviso_dispensa (
    user_id INTEGER NOT NULL,
    aviso_id INTEGER NOT NULL,
    data_local TEXT NOT NULL,
    dispensado_em TEXT NOT NULL,
    PRIMARY KEY (user_id, aviso_id, data_local),
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(aviso_id) REFERENCES nu_avisos(id)
);
CREATE INDEX IF NOT EXISTS idx_nu_avisos_ativo ON nu_avisos(ativo, prioridade DESC);
"""
_COLUNAS_RECORRENCIA = (
    ("recorrente", "INTEGER NOT NULL DEFAULT 0"),
    ("recorrencia_dia_semana", "INTEGER"),
    ("recorrencia_dias", "INTEGER"),
    ("recorrencia_hora", "TEXT"),
    ("recorrencia_ultima_reativacao_em", "TEXT"),
)
DIAS_SEMANA_ABREV = ("Seg", "Ter", "Qua", "Qui", "Sex", "S\u00e1b", "Dom")
class AvisoGestaoError(Exception):
    pass
def init_nu_avisos_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)
    for nome, tipo in _COLUNAS_RECORRENCIA:
        try:
            con.execute(f"ALTER TABLE nu_avisos ADD COLUMN {nome} {tipo}")
        except sqlite3.OperationalError:
            pass
    con.execute("""UPDATE nu_avisos SET recorrencia_dias = (1 << recorrencia_dia_semana)
           WHERE recorrencia_dias IS NULL AND recorrencia_dia_semana IS NOT NULL""")
    con.execute("DROP TABLE IF EXISTS nu_ferj_ferc_aviso_dispensa")
    con.execute(
        "DELETE FROM settings WHERE key=?", ("ferj_ferc_aviso_dispensado_mes",)
    )
    if banco_e_sandbox(con):
        configurar_demo_recorrencia_sandbox(con)
def banco_e_sandbox(con: sqlite3.Connection) -> bool:
    try:
        from ajuda_problemas import caminho_do_banco
        path_db = caminho_do_banco(con)
    except sqlite3.Error:
        path_db = ""
    if not path_db:
        path_db = os.environ.get("CARTORIO_GESTAO_DATA", "")
    path_db = path_db.replace("\\", "/").upper()
    return "/SANDBOX/" in path_db and ("/DADOS/" in path_db or path_db.rstrip("/").endswith("/DADOS"))
def modal_modo_teste(con: sqlite3.Connection | None = None) -> bool:
    flag = (os.environ.get("NU_AVISOS_MODAL_SEMPRE") or "").strip()
    if flag == "1":
        return True
    if flag == "0":
        return False
    if con is not None and banco_e_sandbox(con):
        return True
    return False
def data_local(agora: datetime | str | None = None) -> str:
    if agora is None:
        return date.today().isoformat()
    if isinstance(agora, datetime):
        return agora.date().isoformat()
    texto = (agora or "").strip()
    if len(texto) >= 10:
        return texto[:10]
    return date.today().isoformat()
def _parse_data(texto: str | None) -> date | None:
    if not (texto or "").strip():
        return None
    return date.fromisoformat(texto.strip()[:10])
def _row_val(row, key: str, idx: int):
    if isinstance(row, dict):
        return row.get(key)
    if isinstance(row, sqlite3.Row):
        return row[key]
    return row[idx]
def eh_critico(row) -> bool:
    p = _row_val(row, "prioridade", 4)
    return int(p or 0) >= 2


def eh_importante(row) -> bool:
    p = _row_val(row, "prioridade", 4)
    return int(p or 0) == 1


def eh_prioritario(row) -> bool:
    return eh_critico(row) or eh_importante(row)
def vigente(row: sqlite3.Row | dict, hoje: str | None = None) -> bool:
    h = hoje or date.today().isoformat()
    ini = _row_val(row, "vigencia_inicio", 5)
    fim = _row_val(row, "vigencia_fim", 6)
    d_ini = _parse_data(ini)
    d_fim = _parse_data(fim)
    d_hoje = date.fromisoformat(h)
    if d_ini and d_hoje < d_ini:
        return False
    if d_fim and d_hoje > d_fim:
        return False
    return bool(_row_val(row, "ativo", 3))
def listar_admin(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        con.execute(
            """SELECT * FROM nu_avisos
               ORDER BY ativo DESC, prioridade DESC, id DESC"""
        ).fetchall()
    )
def obter(con: sqlite3.Connection, aviso_id: int) -> sqlite3.Row | None:
    return con.execute(
        "SELECT * FROM nu_avisos WHERE id=?", (aviso_id,)
    ).fetchone()
def dias_bitmask(dias: list[int] | set[int] | int | None) -> int | None:
    if dias is None:
        return None
    if isinstance(dias, int):
        if dias >= 128:
            return dias
        if dias > 0:
            return dias
        if 0 <= dias <= 6:
            return 1 << dias
        return None
    mask = 0
    for d in dias:
        i = int(d)
        if i < 0 or i > 6:
            raise AvisoGestaoError("Dia da semana invï¿½lido (use Seg Dom).")
        mask |= 1 << i
    return mask or None
def dias_do_row(row: sqlite3.Row | dict) -> int | None:
    mask = _row_val(row, "recorrencia_dias", 11)
    if mask is not None and int(mask) > 0:
        return int(mask)
    leg = _row_val(row, "recorrencia_dia_semana", 10)
    if leg is not None:
        return 1 << int(leg)
    return None
def dias_selecionados_do_row(row: sqlite3.Row | dict) -> list[int]:
    mask = dias_do_row(row)
    if not mask:
        return []
    return [i for i in range(7) if mask & (1 << i)]
def _normalizar_recorrencia(
    recorrente: bool,
    dias: list[int] | set[int] | int | None,
    hora: str | None,
) -> tuple[int, int | None, int | None, str | None]:
    if not recorrente:
        return 0, None, None, None
    mask = dias_bitmask(dias)
    if not mask:
        raise AvisoGestaoError("Marque ao menos um dia da semana (Seg Dom).")
    hhmm = (hora or "").strip()
    if len(hhmm) != 5 or hhmm[2] != ":":
        raise AvisoGestaoError("Informe a hora no formato HH:MM.")
    try:
        h, m = (int(hhmm[:2]), int(hhmm[3:5]))
        if h < 0 or h > 23 or m < 0 or m > 59:
            raise ValueError
    except ValueError as exc:
        raise AvisoGestaoError("Hora invï¿½lida.") from exc
    legado = min(i for i in range(7) if mask & (1 << i))
    return 1, legado, mask, hhmm
def criar(
    con: sqlite3.Connection,
    *,
    titulo: str,
    corpo: str,
    ativo: bool,
    prioridade: int,
    vigencia_inicio: str | None,
    vigencia_fim: str | None,
    agora: str,
    criado_por: str,
    recorrente: bool = False,
    recorrencia_dia_semana: int | None = None,
    recorrencia_dias: int | None = None,
    recorrencia_hora: str | None = None,
) -> int:
    titulo = (titulo or "").strip()
    corpo = (corpo or "").strip()
    if not titulo:
        raise AvisoGestaoError("Informe o tÃ­tulo do aviso.")
    if not corpo:
        raise AvisoGestaoError("Informe o texto do aviso.")
    if recorrencia_dias is not None:
        _raw_dias = recorrencia_dias
    elif recorrencia_dia_semana is not None:
        _raw_dias = 1 << int(recorrencia_dia_semana)
    else:
        _raw_dias = None
    rec, dia, dias_mask, hhmm = _normalizar_recorrencia(
        recorrente, _raw_dias, recorrencia_hora,
    )
    cur = con.execute(
        """INSERT INTO nu_avisos
           (titulo, corpo, ativo, prioridade, vigencia_inicio, vigencia_fim,
            criado_em, atualizado_em, criado_por,
            recorrente, recorrencia_dia_semana, recorrencia_dias, recorrencia_hora)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            titulo,
            corpo,
            1 if ativo else 0,
            int(prioridade),
            vigencia_inicio or None,
            vigencia_fim or None,
            agora,
            agora,
            criado_por,
            rec,
            dia,
            dias_mask,
            hhmm,
        ),
    )
    return int(cur.lastrowid)
def atualizar(
    con: sqlite3.Connection,
    aviso_id: int,
    *,
    titulo: str,
    corpo: str,
    ativo: bool,
    prioridade: int,
    vigencia_inicio: str | None,
    vigencia_fim: str | None,
    agora: str,
    recorrente: bool = False,
    recorrencia_dia_semana: int | None = None,
    recorrencia_dias: int | None = None,
    recorrencia_hora: str | None = None,
) -> None:
    if not obter(con, aviso_id):
        raise AvisoGestaoError("Aviso nÃ£o encontrado.")
    titulo = (titulo or "").strip()
    corpo = (corpo or "").strip()
    if not titulo:
        raise AvisoGestaoError("Informe o tÃ­tulo do aviso.")
    if not corpo:
        raise AvisoGestaoError("Informe o texto do aviso.")
    if recorrencia_dias is not None:
        _raw_dias = recorrencia_dias
    elif recorrencia_dia_semana is not None:
        _raw_dias = 1 << int(recorrencia_dia_semana)
    else:
        _raw_dias = None
    rec, dia, dias_mask, hhmm = _normalizar_recorrencia(
        recorrente, _raw_dias, recorrencia_hora,
    )
    con.execute(
        """UPDATE nu_avisos SET titulo=?, corpo=?, ativo=?, prioridade=?,
           vigencia_inicio=?, vigencia_fim=?, atualizado_em=?,
           recorrente=?, recorrencia_dia_semana=?, recorrencia_dias=?, recorrencia_hora=?
           WHERE id=?""",
        (
            titulo,
            corpo,
            1 if ativo else 0,
            int(prioridade),
            vigencia_inicio or None,
            vigencia_fim or None,
            agora,
            rec,
            dia,
            dias_mask,
            hhmm,
            aviso_id,
        ),
    )
def desativar(con: sqlite3.Connection, aviso_id: int, *, agora: str) -> None:
    if not obter(con, aviso_id):
        raise AvisoGestaoError("Aviso nÃ£o encontrado.")
    con.execute(
        "UPDATE nu_avisos SET ativo=0, atualizado_em=? WHERE id=?",
        (agora, aviso_id),
    )
def ativar(con: sqlite3.Connection, aviso_id: int, *, agora: str) -> None:
    if not obter(con, aviso_id):
        raise AvisoGestaoError("Aviso nÃ£o encontrado.")
    con.execute(
        "UPDATE nu_avisos SET ativo=1, atualizado_em=? WHERE id=?",
        (agora, aviso_id),
    )
def alternar_ativo(con: sqlite3.Connection, aviso_id: int, *, agora: str) -> bool:
    aviso = obter(con, aviso_id)
    if not aviso:
        raise AvisoGestaoError("Aviso nÃ£o encontrado.")
    novo = 0 if int(aviso["ativo"]) else 1
    con.execute(
        "UPDATE nu_avisos SET ativo=?, atualizado_em=? WHERE id=?",
        (novo, agora, aviso_id),
    )
    return bool(novo)
def remover(con: sqlite3.Connection, aviso_id: int) -> None:
    if not obter(con, aviso_id):
        raise AvisoGestaoError("Aviso nÃ£o encontrado.")
    con.execute("DELETE FROM nu_aviso_dispensa WHERE aviso_id=?", (aviso_id,))
    con.execute("DELETE FROM nu_avisos WHERE id=?", (aviso_id,))
def listar_ativos_vigentes(con: sqlite3.Connection, *, hoje: str | None = None) -> list[sqlite3.Row]:
    h = hoje or date.today().isoformat()
    prev = con.row_factory
    con.row_factory = sqlite3.Row
    try:
        linhas = con.execute(
            """SELECT * FROM nu_avisos WHERE ativo=1
               ORDER BY prioridade DESC, id ASC"""
        ).fetchall()
    finally:
        con.row_factory = prev
    return [r for r in linhas if vigente(r, h)]
def ids_dispensados_hoje(
    con: sqlite3.Connection, user_id: int, *, hoje: str | None = None
) -> set[int]:
    h = hoje or date.today().isoformat()
    rows = con.execute(
        """SELECT aviso_id FROM nu_aviso_dispensa
           WHERE user_id=? AND data_local=?""",
        (user_id, h),
    ).fetchall()
    return {int(r[0]) for r in rows}
def pendentes_para_usuario(
    con: sqlite3.Connection,
    user_id: int,
    *,
    hoje: str | None = None,
    dispensados: set[int] | None = None,
) -> list[dict[str, Any]]:
    h = hoje or date.today().isoformat()
    if dispensados is None:
        dispensados = ids_dispensados_hoje(con, user_id, hoje=h)
    out: list[dict[str, Any]] = []
    for row in listar_ativos_vigentes(con, hoje=h):
        if eh_prioritario(row):
            out.append(dict(row))
            continue
        if int(row["id"]) in dispensados:
            continue
        out.append(dict(row))
    return out
def contar_pendentes(
    con: sqlite3.Connection,
    user_id: int,
    *,
    hoje: str | None = None,
    dispensados: set[int] | None = None,
) -> int:
    return len(
        pendentes_para_usuario(con, user_id, hoje=hoje, dispensados=dispensados)
    )
def dispensar(
    con: sqlite3.Connection,
    *,
    user_id: int,
    aviso_id: int,
    agora: str,
    hoje: str | None = None,
    papel: str | None = None,
) -> None:
    aviso = obter(con, aviso_id)
    if not aviso:
        raise AvisoGestaoError("Aviso nÃ£o encontrado.")
    if eh_prioritario(aviso):
        if (papel or "").upper() != "ADMIN":
            raise AvisoGestaoError(
                "Aviso importante sÃ³ pode ser encerrado por ADMIN."
            )
        desativar(con, aviso_id, agora=agora)
        return
    h = hoje or data_local(agora)
    con.execute(
        """INSERT INTO nu_aviso_dispensa
           (user_id, aviso_id, data_local, dispensado_em)
           VALUES (?,?,?,?)
           ON CONFLICT(user_id, aviso_id, data_local) DO UPDATE SET
           dispensado_em=excluded.dispensado_em""",
        (user_id, aviso_id, h, agora),
    )
def dispensar_todos_pendentes(
    con: sqlite3.Connection,
    *,
    user_id: int,
    agora: str,
    hoje: str | None = None,
    apenas_normais: bool = False,
    apenas_importantes: bool = False,
    papel: str | None = None,
) -> int:
    pendentes = pendentes_para_usuario(con, user_id, hoje=hoje or data_local(agora))
    if apenas_importantes:
        if (papel or "").upper() != "ADMIN":
            raise AvisoGestaoError(
                "Aviso importante s\u00f3 pode ser encerrado por ADMIN."
            )
        pendentes = pendentes_importantes(pendentes)
    elif apenas_normais:
        pendentes = pendentes_normais(pendentes)
    for av in pendentes:
        dispensar(
            con,
            user_id=user_id,
            aviso_id=int(av["id"]),
            agora=agora,
            hoje=hoje,
            papel=papel,
        )
    return len(pendentes)
def pendentes_criticos(pendentes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in pendentes if eh_critico(a)]


def pendentes_importantes(pendentes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in pendentes if eh_importante(a)]


def pendentes_normais(pendentes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in pendentes if int(a.get("prioridade") or 0) == 0]
def _parse_agora(agora: str | datetime) -> datetime:
    if isinstance(agora, datetime):
        return agora
    texto = (agora or "").strip()
    if len(texto) >= 19:
        return datetime.fromisoformat(texto[:19])
    if len(texto) >= 10:
        return datetime.fromisoformat(texto[:10] + "T00:00:00")
    return datetime.now()
def _slot_no_dia(dia: date, hora_hhmm: str) -> datetime:
    h, m = (int(hora_hhmm[:2]), int(hora_hhmm[3:5]))
    return datetime.combine(dia, datetime.min.time()).replace(hour=h, minute=m)
def _slots_recorrencia_entre(
    mask: int, hora_hhmm: str, depois: datetime, ate: datetime
) -> list[datetime]:
    slots: list[datetime] = []
    dia = depois.date()
    fim = ate.date()
    while dia <= fim:
        if mask & (1 << dia.weekday()):
            slot = _slot_no_dia(dia, hora_hhmm)
            if depois < slot <= ate:
                slots.append(slot)
        dia += timedelta(days=1)
    return slots
def processar_recorrencias(con: sqlite3.Connection, *, agora: str | datetime) -> int:
    dt = _parse_agora(agora)
    agora_txt = dt.isoformat(timespec="seconds")
    linhas = con.execute(
        """SELECT * FROM nu_avisos
           WHERE ativo=0 AND recorrente=1
             AND recorrencia_hora IS NOT NULL"""
    ).fetchall()
    reativados = 0
    for row in linhas:
        mask = dias_do_row(row)
        if not mask:
            continue
        base = row["atualizado_em"] or row["criado_em"] or agora_txt
        depois = _parse_agora(base)
        slots = _slots_recorrencia_entre(
            mask, row["recorrencia_hora"], depois, dt
        )
        if not slots:
            continue
        slot = slots[-1]
        ultima = row["recorrencia_ultima_reativacao_em"]
        if ultima and _parse_agora(ultima) >= slot:
            continue
        con.execute(
            """UPDATE nu_avisos SET ativo=1, atualizado_em=?,
               recorrencia_ultima_reativacao_em=? WHERE id=?""",
            (agora_txt, agora_txt, int(row["id"])),
        )
        con.execute(
            "DELETE FROM nu_aviso_dispensa WHERE aviso_id=?", (int(row["id"]),)
        )
        reativados += 1
    return reativados
def configurar_demo_recorrencia_sandbox(con: sqlite3.Connection) -> int | None:
    if not banco_e_sandbox(con):
        return None
    row = con.execute(
        """SELECT id, recorrente, recorrencia_dia_semana, recorrencia_hora
           FROM nu_avisos WHERE prioridade >= 1
           ORDER BY id ASC LIMIT 1"""
    ).fetchone()
    if not row:
        return None
    aid = int(row["id"])
    if int(row["recorrente"] or 0) and row["recorrencia_hora"]:
        return aid
    con.execute(
        """UPDATE nu_avisos SET recorrente=1, recorrencia_dia_semana=0,
           recorrencia_dias=1, recorrencia_hora='08:00' WHERE id=?""",
        (aid,),
    )
    return aid
