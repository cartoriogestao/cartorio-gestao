"""Troca o responsável e o substituto de uma tarefa, como a tela faz — histórico
ALTEROU_ASSIGNED_USER_ID / ALTEROU_BACKUP_USER_ID com valor antigo e novo, e auditoria.

    --tarefa ID:RESPONSAVEL[:SUBSTITUTO]  (logins; pode repetir separado por vírgula)
    --motivo «texto»                       vai na nota do histórico
Sem --confirmar só mede. Com --confirmar tira cópia do banco antes (pasta_das_copias).
Quem troca é o login de settings.malote_cadastra_em_nome_de (o oficial).

NO POSTGRESQL (LH03, 21/10/2026; a ferramenta nasceu no sandbox, no SQLite):
  - a medição abre o banco SÓ PARA LER (o `mode=ro` no caminho, pela porta
    `banco_pg.conectar`), e a cópia de antes de gravar é a da casa
    (`banco_pg.copiar_para_arquivo`, um pg_dump), no lugar do `VACUUM INTO`;
  - na escrita, a tarefa é RELIDA com a linha presa (`FOR UPDATE`, como o
    `database.update_task` da tela): o «valor antigo» do histórico é o que está
    no banco na hora de gravar, e não o da medição — a tela pode ter trocado o
    responsável durante a cópia.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import banco_pg  # noqa: E402
import identidade_do_robo as IDR  # noqa: E402
from bd_nativo import banco as abrir_banco  # noqa: E402


def _quem(bd) -> dict:
    """O login em nome de quem se grava (`settings.malote_cadastra_em_nome_de`)."""
    login = bd.valor("SELECT value FROM settings WHERE key='malote_cadastra_em_nome_de'") or ""
    quem = bd.um("SELECT id, username FROM users WHERE username=%s", (login,))
    if not quem:
        raise SystemExit("Sem settings.malote_cadastra_em_nome_de válido.")
    return quem


def _tarefa(bd, tid: int, *, prender: bool = False) -> dict:
    """A tarefa como está agora. Com `prender`, a linha fica presa até o fim."""
    if prender:
        bd._escrita()
    t = bd.um("SELECT title, assigned_user_id, backup_user_id FROM tasks WHERE id=%s"
              + (" FOR UPDATE" if prender else ""), (tid,))
    if not t:
        raise SystemExit(f"Tarefa {tid} não existe.")
    return t


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", required=True)
    ap.add_argument("--tarefa", required=True)
    ap.add_argument("--motivo", default="")
    ap.add_argument("--confirmar", action="store_true")
    a = ap.parse_args(argv)
    banco = Path(a.banco)
    ro = banco_pg.conectar(f"file:{banco.as_posix()}?mode=ro", uri=True)
    try:
        bd = abrir_banco(ro)
        _quem(bd)

        def uid(lg):
            r = bd.um("SELECT id FROM users WHERE username=%s AND active=1", (lg,))
            if not r:
                raise SystemExit(f"Usuário «{lg}» não existe ou está inativo.")
            return int(r["id"])

        plano = []
        for item in a.tarefa.split(","):
            partes = item.strip().split(":")
            tid, resp = int(partes[0]), uid(partes[1])
            subst = uid(partes[2]) if len(partes) > 2 else None
            t = _tarefa(bd, tid)
            plano.append((tid, resp, subst))
            print(f"tarefa {tid} — {t['title']}: responsável {t['assigned_user_id']}→{resp}, "
                  f"substituto {t['backup_user_id']}→{subst if subst else t['backup_user_id']}")
    finally:
        ro.close()
    if not a.confirmar:
        print("Só medi. Nada foi gravado.")
        return 0
    from pasta_das_copias import destino_da_copia
    copia = destino_da_copia(Path(f"antes_trocar_responsavel_{datetime.now():%Y%m%d_%H%M%S}.sqlite3"), banco)
    banco_pg.copiar_para_arquivo(banco, copia)
    if not copia.is_file() or copia.stat().st_size == 0:
        raise SystemExit(f"A cópia do banco não saiu ({copia}); nada foi gravado.")
    print("cópia do banco:", copia)
    agora = datetime.now().isoformat(timespec="seconds")
    con = banco_pg.conectar(banco, timeout=60)
    try:
        bd = abrir_banco(con)
        quem = _quem(bd)
        for tid, resp, subst in plano:
            t = _tarefa(bd, tid, prender=True)
            novo_subst = subst if subst else t["backup_user_id"]
            bd.escrever("UPDATE tasks SET assigned_user_id=%s, backup_user_id=%s, updated_at=%s WHERE id=%s",
                        (resp, novo_subst, agora, tid))
            if t["assigned_user_id"] != resp:
                bd.escrever("INSERT INTO task_history(task_id,ts,user_id,action,old_value,new_value,note) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                            (tid, agora, quem["id"], "ALTEROU_ASSIGNED_USER_ID", str(t["assigned_user_id"]), str(resp), a.motivo))
            if t["backup_user_id"] != novo_subst:
                bd.escrever("INSERT INTO task_history(task_id,ts,user_id,action,old_value,new_value,note) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                            (tid, agora, quem["id"], "ALTEROU_BACKUP_USER_ID", str(t["backup_user_id"]), str(novo_subst), a.motivo))
            # O script age com a conta de uma pessoa: a linha diz que foi o
            # script, a mando dela (26/10/2026).
            IDR.registrar(bd, ts=agora, user_id=quem["id"], username=quem["username"],
                          action="TASK_UPDATED", entity_type="TASK", entity_id=tid,
                          details=json.dumps({"responsavel": resp, "substituto": novo_subst, "motivo": a.motivo}, ensure_ascii=False),
                          agente="tools/tarefa_trocar_responsavel.py")
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
