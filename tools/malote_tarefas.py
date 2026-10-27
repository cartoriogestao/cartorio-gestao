"""Tarefas a partir do malote, sem expediente — ordem do oficial em 20/10/2026:
«já estou ciente de todos, apenas crie tarefas para <servidora-1> e <servidora-2> para os do
rcpn que precisa conferir».

Lê um JSON com uma lista de tarefas, cada uma com:
    titulo, descricao, setor, responsavel (login), substituto (login),
    prazo_dias, prazo (AAAA-MM-DD), prioridade, arquivos (caminhos)

Sem --confirmar só mede (banco aberto só para ler). Com --confirmar: cópia do banco
longe dele (pasta_das_copias), e numa transação só cria a tarefa, o histórico
«CRIADA», os anexos (copiados para arquivos\\Evidencias\\<setor>\\Tarefa-NNNNN, como a
tela faz) e a auditoria. A mesma tarefa ABERTA (título + responsável) não nasce duas
vezes — a regra de 12/10/2026 de `database.create_task`. Quem cria é o login de
settings.malote_cadastra_em_nome_de.

NO POSTGRESQL (LH03, 21/10/2026; a ferramenta nasceu no sandbox, no SQLite):
  - a medição abre o banco SÓ PARA LER (o `mode=ro` no caminho, pela porta
    `banco_pg.conectar`), e a cópia de antes de gravar é a da casa
    (`banco_pg.copiar_para_arquivo`, um pg_dump), no lugar do `VACUUM INTO`;
  - a transação exclusiva do SQLite virou a trava do assunto (`TRAVA`), pega ANTES de
    perguntar «já existe?»: a pergunta se refaz dentro dela, porque a tarefa
    igual pode ter nascido na tela durante a cópia, e duas rodadas desta
    ferramenta ao mesmo tempo não criam a mesma tarefa duas vezes;
  - o número da tarefa vem do `RETURNING id`, no lugar do `lastrowid`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AQUI))

import banco_pg  # noqa: E402
import identidade_do_robo as IDR  # noqa: E402
from bd_nativo import banco as abrir_banco  # noqa: E402

#: A trava de quem cria tarefa por fora da tela: «já existe a mesma ABERTA?» e o
#: INSERT são um passo só. `FOR UPDATE` não prende a linha que ainda não existe.
TRAVA = "tasks.tarefa_igual_aberta"


def _seguro(nome: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", nome).strip() or "Geral"


def _igual(bd, titulo: str, responsavel: int) -> int | None:
    """A tarefa ABERTA com o mesmo título e o mesmo responsável, se houver."""
    r = bd.um(
        "SELECT id FROM tasks WHERE title=%s AND assigned_user_id=%s AND status NOT IN ('CONCLUIDA','CANCELADA') "
        "ORDER BY id LIMIT 1",
        (titulo, responsavel))
    return int(r["id"]) if r else None


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", required=True)
    ap.add_argument("--tarefas", required=True, help="JSON com a lista de tarefas")
    ap.add_argument("--confirmar", action="store_true")
    a = ap.parse_args(argv)
    banco = Path(a.banco)
    tarefas = json.loads(Path(a.tarefas).read_text(encoding="utf-8"))

    ro = banco_pg.conectar(f"file:{banco.as_posix()}?mode=ro", uri=True)
    try:
        bd = abrir_banco(ro)
        valor = bd.valor("SELECT value FROM settings WHERE key='malote_cadastra_em_nome_de'")
        login_criador = str(valor or "").strip()
        criador = bd.um("SELECT id, username FROM users WHERE username=%s", (login_criador,))
        if not criador:
            raise SystemExit("Sem settings.malote_cadastra_em_nome_de válido: não sei em nome de quem criar.")
        valor = bd.valor("SELECT value FROM settings WHERE key='archive_root'")
        raiz = Path(str(valor).strip()) if str(valor or "").strip() else banco.parent / "arquivos"

        def uid(login):
            row = bd.um("SELECT id FROM users WHERE username=%s AND active=1", (login,))
            if not row:
                raise SystemExit(f"Usuário «{login}» não existe ou está inativo.")
            return int(row["id"])

        plano = []
        for t in tarefas:
            resp, subst = uid(t["responsavel"]), (uid(t["substituto"]) if t.get("substituto") else None)
            for f in t.get("arquivos", []):
                if not Path(f).is_file():
                    raise SystemExit(f"Arquivo não encontrado: {f}")
            igual = _igual(bd, t["titulo"], resp)
            plano.append((t, resp, subst))
            print(("JÁ EXISTE (tarefa %s): " % igual if igual else "a criar: ") + t["titulo"],
                  "→", t["responsavel"], "| prazo", t.get("prazo"), "| anexos", len(t.get("arquivos", [])))
    finally:
        ro.close()
    if not a.confirmar:
        print("Só medi. Nada foi gravado.")
        return 0

    from pasta_das_copias import destino_da_copia
    copia = destino_da_copia(Path(f"antes_malote_tarefas_{datetime.now():%Y%m%d_%H%M%S}.sqlite3"), banco)
    banco_pg.copiar_para_arquivo(banco, copia)
    if not copia.is_file() or copia.stat().st_size == 0:
        raise SystemExit(f"A cópia do banco não saiu ({copia}); nada foi gravado.")
    print("cópia do banco:", copia)

    agora = datetime.now().isoformat(timespec="seconds")
    copiados: list[Path] = []
    criadas = []
    con = banco_pg.conectar(banco, timeout=60)
    try:
        bd = abrir_banco(con)
        bd.travar(TRAVA)
        for t, resp, subst in plano:
            # de novo, dentro da trava: a da medição pode ter nascido depois
            if _igual(bd, t["titulo"], resp):
                continue
            tid = int(bd.escrever(
                """INSERT INTO tasks(source_type,source_ref,title,description,sector,system_name,priority,status,
                   due_days,start_date,due_date,assigned_user_id,backup_user_id,evidence_required,legal_ref,
                   created_by,created_at,updated_at)
                   VALUES ('MANUAL',%s,%s,%s,%s,'',%s,'ABERTA',%s,%s,%s,%s,%s,0,%s,%s,%s,%s) RETURNING id""",
                (t.get("referencia"), t["titulo"], t["descricao"], t.get("setor") or "RCPN",
                 t.get("prioridade") or "ALTA", t.get("prazo_dias"), date.today().isoformat(), t.get("prazo"),
                 resp, subst, t.get("base_legal") or "", criador["id"], agora, agora))[0]["id"])
            bd.escrever("INSERT INTO task_history(task_id,ts,user_id,action,new_value,note) VALUES (%s,%s,%s,%s,%s,%s)",
                        (tid, agora, criador["id"], "CRIADA", "ABERTA", t["descricao"]))
            pasta = raiz / "Evidencias" / _seguro(t.get("setor") or "RCPN") / f"Tarefa-{tid:05d}"
            pasta.mkdir(parents=True, exist_ok=True)
            for f in t.get("arquivos", []):
                src = Path(f)
                nome = re.sub(r"^MALOTE_\d+_", "", src.name)
                alvo = pasta / nome
                shutil.copy2(src, alvo)
                copiados.append(alvo)
                dados = alvo.read_bytes()
                bd.escrever(
                    "INSERT INTO attachments(entity_type,entity_id,original_name,stored_name,stored_path,sha256,size_bytes,description,uploaded_by,uploaded_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    ("TASK", tid, nome, nome, str(alvo), hashlib.sha256(dados).hexdigest(), len(dados),
                     "Malote Digital — " + (t.get("referencia") or ""), criador["id"], agora))
            # O agente do malote age com a conta de quem o oficial designou: a
            # linha diz isso (agente + a mando da pessoa) (26/10/2026).
            IDR.registrar(
                bd, ts=agora, user_id=criador["id"], username=criador["username"],
                action="TASK_CREATED", entity_type="TASK", entity_id=tid,
                details=json.dumps({"origem": "AGENTE MALOTE", "titulo": t["titulo"], "referencia": t.get("referencia")},
                                   ensure_ascii=False),
                agente="agente do malote (tools/malote_tarefas.py)")
            criadas.append((tid, t["titulo"], t["responsavel"]))
        con.commit()
    except BaseException:
        con.rollback()
        for p in copiados:
            p.unlink(missing_ok=True)
        raise
    finally:
        con.close()
    for tid, titulo, resp in criadas:
        print(f"criada: tarefa {tid} — {titulo} → {resp}")
    print("criadas:", len(criadas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
