"""Expediente do malote de que o oficial JÁ TEM CIÊNCIA não vira tarefa — ordem dele
em 20/10/2026: «coloque de toda forma esses expedientes no sistema para cadastro, só
não cria tarefa pq já estou ciente deles».

A triagem diária (`gestor_expedientes.candidatos`) pega todo expediente em RECEBIDO
sem tarefa aberta ligada. Por isso, com --confirmar:
  --arquivar ID[,ID]   etapa ARQUIVADO, com completed_at/by e a nota de ciência;
  --ligar EXP:TAREFA   liga a tarefa que ele mandou criar ao expediente dela.
Sem --confirmar só mede. Cópia do banco antes (pasta_das_copias) e auditoria.

NO POSTGRESQL (LH03, 21/10/2026; a ferramenta nasceu no sandbox, no SQLite):
  - a medição abre o banco SÓ PARA LER (o `mode=ro` no caminho, pela porta
    `banco_pg.conectar`, que liga o `default_transaction_read_only`): medir não
    grava nem por engano;
  - a cópia de antes de gravar é a da casa no PostgreSQL
    (`banco_pg.copiar_para_arquivo`, um pg_dump), no lugar do `VACUUM INTO`;
  - a conferência (o expediente em RECEBIDO, a tarefa sem outro expediente) se
    REFAZ dentro da transação que grava, com a linha presa (`FOR UPDATE`): entre
    a medição e a escrita há a cópia, e o expediente que outra mesa arquivou
    nesse meio não se arquiva de novo por cima.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import banco_pg  # noqa: E402
from bd_nativo import banco as abrir_banco  # noqa: E402


def _quem(bd) -> dict:
    """O login em nome de quem se grava (`settings.malote_cadastra_em_nome_de`)."""
    login = bd.valor("SELECT value FROM settings WHERE key='malote_cadastra_em_nome_de'") or ""
    quem = bd.um("SELECT id, username FROM users WHERE username=%s", (login,))
    if not quem:
        raise SystemExit("Sem settings.malote_cadastra_em_nome_de válido.")
    return quem


def _conferir(bd, arquivar: list[int], ligar: list[tuple[int, int]], *,
              prender: bool = False) -> list[str]:
    """O que se vai fazer, linha a linha — ou a recusa. Com `prender`, cada linha
    lida fica presa até o fim da transação (é a conferência de dentro da escrita)."""
    preso = " FOR UPDATE" if prender else ""
    if prender:
        bd._escrita()
    plano = []
    for eid in arquivar:
        e = bd.um("SELECT internal_protocol, stage FROM expedientes WHERE id=%s" + preso, (eid,))
        if not e or e["stage"] != "RECEBIDO":
            raise SystemExit(f"Expediente {eid} não existe ou não está em RECEBIDO ({e and e['stage']}).")
        plano.append(f"arquivar (ciência): {e['internal_protocol']}")
    for eid, tid in ligar:
        t = bd.um("SELECT title, linked_expediente_id FROM tasks WHERE id=%s" + preso, (tid,))
        if not t or t["linked_expediente_id"] not in (None, eid):
            raise SystemExit(f"Tarefa {tid} não existe ou já está ligada a outro expediente.")
        plano.append(f"ligar tarefa {tid} ao expediente {eid}: {t['title']}")
    return plano


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", required=True)
    ap.add_argument("--arquivar", default="")
    ap.add_argument("--ligar", default="")
    ap.add_argument("--confirmar", action="store_true")
    a = ap.parse_args(argv)
    banco = Path(a.banco)
    arquivar = [int(x) for x in a.arquivar.split(",") if x.strip()]
    ligar = [tuple(int(y) for y in x.split(":")) for x in a.ligar.split(",") if x.strip()]
    ro = banco_pg.conectar(f"file:{banco.as_posix()}?mode=ro", uri=True)
    try:
        bd = abrir_banco(ro)
        _quem(bd)
        for linha in _conferir(bd, arquivar, ligar):
            print(linha)
    finally:
        ro.close()
    if not a.confirmar:
        print("Só medi. Nada foi gravado.")
        return 0
    from pasta_das_copias import destino_da_copia
    copia = destino_da_copia(Path(f"antes_malote_ciencia_{datetime.now():%Y%m%d_%H%M%S}.sqlite3"), banco)
    banco_pg.copiar_para_arquivo(banco, copia)
    if not copia.is_file() or copia.stat().st_size == 0:
        raise SystemExit(f"A cópia do banco não saiu ({copia}); nada foi gravado.")
    print("cópia do banco:", copia)
    agora = datetime.now().isoformat(timespec="seconds")
    nota = f"Ciência do oficial em {datetime.now():%d/%m/%Y} — arquivado sem tarefa, por ordem dele."
    con = banco_pg.conectar(banco, timeout=60)
    try:
        bd = abrir_banco(con)
        quem = _quem(bd)
        _conferir(bd, arquivar, ligar, prender=True)      # de novo, com as linhas presas
        for eid in arquivar:
            bd.escrever("""UPDATE expedientes SET stage='ARQUIVADO', completed_at=%s, completed_by=%s, updated_at=%s,
                           notes=TRIM(COALESCE(notes,'') || ' ' || %s) WHERE id=%s""",
                        (agora, quem["id"], agora, nota, eid))
            bd.escrever("INSERT INTO audit_logs(ts,user_id,username_snapshot,action,entity_type,entity_id,details) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (agora, quem["id"], quem["username"], "EXPEDIENTE_STAGE", "EXPEDIENTE", eid,
                         json.dumps({"stage": "ARQUIVADO", "origem": "AGENTE MALOTE", "motivo": nota}, ensure_ascii=False)))
        for eid, tid in ligar:
            bd.escrever("UPDATE tasks SET linked_expediente_id=%s, updated_at=%s WHERE id=%s", (eid, agora, tid))
            bd.escrever("INSERT INTO task_history(task_id,ts,user_id,action,new_value,note) VALUES (%s,%s,%s,%s,%s,%s)",
                        (tid, agora, quem["id"], "NOTA", None, f"Ligada ao expediente {eid} (malote)."))
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()
    print("feito.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
