"""Cancela a duplicata do nascimento fichada no Livro E — 13/10/2026.

Ordem do oficial: «sim» (corrigir na produção o registro de nascimento de 1994
que ficou fichado no Livro E) e, depois de a trava de permissão barrar a
primeira tentativa, «pode rodar».

O QUE FOI MEDIDO (produção, só leitura, 13/10/2026):
  - assento 116: série RC_E, espécie OUTRO, nº 8686, origem EOFICIO, sem
    pessoas, sem certidão, sem anotação; a matrícula dele diz tipo de livro 1
    — Livro A.
  - o MESMO registro já está no Livro A: assento 6189, RC_A, NASCIMENTO,
    nº 8686. Mover o 116 faria dois.
  - o contador do Livro E (`nu_numeracao` RC_E, próximo 8687) foi semeado SÓ
    por este registro; a pendência «numeracao:RC_E» está ABERTA; não há Livro
    E aberto em `nu_livros`.

O QUE FAZ, com --confirmar:
  1. cópia do banco (VACUUM INTO) na pasta das cópias
     (`pasta_das_copias.destino_da_copia`), medindo o disco antes — o banco
     fica sozinho na pasta dele;
  2. `rc_assentos` 116 → situacao CANCELADO (a linha fica);
  3. apaga a linha RC_E de `nu_numeracao` — o número fica EM ABERTO, como o
     oficial mandou; a pendência continua aberta e é onde ele o informa;
  4. auditoria RCPN_ASSENTO_CANCELADO (a forma do 8375) e
     NUMERACAO_SEMENTE_DESFEITA.

O QUE NÃO FAZ: não toca no assento 6189.

Só mede por padrão. Recusa se qualquer medida divergir da descrita acima.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BANCO_PADRAO = r"C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3"
QUEM = "agente do RCPN (ordem do oficial em 13/10/2026)"
MOTIVO = ("Duplicata fichada no Livro E pela carga do acervo: é o nascimento "
          "nº 8686 que está no Livro A (assento 6189). A matrícula do "
          "E-Ofício diz tipo de livro 1. Cancelado por ordem do oficial em "
          "13/10/2026; o contador do Livro E, semeado só por este registro, "
          "foi desfeito e o próximo número fica em aberto.")


class Recusa(SystemExit):
    pass


def medir(con: sqlite3.Connection) -> dict:
    con.row_factory = sqlite3.Row
    a = con.execute("SELECT * FROM rc_assentos WHERE id=116").fetchone()
    b = con.execute("SELECT * FROM rc_assentos WHERE id=6189").fetchone()
    if not a or not b:
        raise Recusa("RECUSO: o 116 ou o 6189 não existe.")
    a, b = dict(a), dict(b)
    esperado = {"serie": "RC_E", "especie": "OUTRO", "numero": 8686,
                "situacao": "ATIVO", "origem": "EOFICIO"}
    for k, v in esperado.items():
        if a.get(k) != v:
            raise Recusa(f"RECUSO: o 116 mudou ({k}={a.get(k)!r}, esperado {v!r}).")
    if (b["serie"], b["numero"], b["situacao"]) != ("RC_A", 8686, "ATIVO"):
        raise Recusa("RECUSO: o 6189 não é mais o nascimento ativo do Livro A.")
    # O NOME SE CONFERE ENTRE OS DOIS, E NÃO CONTRA UM LITERAL — nome de
    # pessoa não mora no código (portão anti-vazamento, 14/10/2026).
    if not (a["nome"] or "").strip() or a["nome"] != b["nome"]:
        raise Recusa("RECUSO: o 116 e o 6189 não têm o mesmo nome.")
    presos = {t: con.execute(f"SELECT count(*) FROM {t} WHERE assento_id=116"
                             ).fetchone()[0]
              for t in ("rc_pessoas", "rc_certidoes", "rc_anotacoes")}
    if any(presos.values()):
        raise Recusa(f"RECUSO: há coisa amarrada ao 116: {presos}.")
    if con.execute("SELECT 1 FROM rc_atos WHERE assento_id=116 "
                   "AND IFNULL(selo,'')!=''").fetchone():
        raise Recusa("RECUSO: o ato do 116 tem selo.")
    outros = con.execute("SELECT count(*) FROM rc_assentos WHERE serie='RC_E' "
                         "AND id!=116").fetchone()[0]
    if outros:
        raise Recusa(f"RECUSO: há {outros} outro(s) assento(s) no Livro E — o "
                     "contador não foi semeado só pelo 116.")
    if con.execute("SELECT count(*) FROM nu_livros WHERE serie='RC_E'").fetchone()[0]:
        raise Recusa("RECUSO: já existe Livro E aberto — tirar o contador agora "
                     "deixaria o próximo ato nascer com o número 1.")
    num = con.execute("SELECT * FROM nu_numeracao WHERE serie='RC_E'").fetchone()
    return {"assento_116": {k: a[k] for k in ("serie", "especie", "numero",
                                               "livro_volume", "matricula",
                                               "situacao")},
            "assento_6189": {k: b[k] for k in ("serie", "especie", "numero",
                                                "livro_volume", "matricula")},
            "contador_RC_E": dict(num) if num else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default=BANCO_PADRAO)
    ap.add_argument("--confirmar", action="store_true")
    args = ap.parse_args()
    banco = Path(args.banco)

    ro = sqlite3.connect(f"file:{banco.as_posix()}?mode=ro", uri=True)
    medida = medir(ro)
    ro.close()
    print(json.dumps(medida, ensure_ascii=False, indent=1))
    if not args.confirmar:
        print("\nSÓ MEDIU. Para gravar: --confirmar")
        return 0

    # FORA DA PASTA DO BANCO — a regra de 11/10/2026 (`pasta_das_copias`),
    # a mesma dos outros scripts de `tools/`. Até 14/10/2026 esta ferramenta
    # gravava em `<pasta do banco>\backups`, ao lado do banco.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import pasta_das_copias as _PC
    carimbo = datetime.now().strftime("%Y%m%dT%H%M%S")
    copia = _PC.destino_da_copia(
        banco.parent / f"cartorio_gestao_pre_CANCELA_116_LIVRO_E_{carimbo}.sqlite3",
        banco)
    livre = shutil.disk_usage(copia.parent).free
    tamanho = banco.stat().st_size
    if livre < tamanho * 2:
        raise Recusa(f"RECUSO: {livre / 2**20:.0f} MB livres e banco de "
                     f"{tamanho / 2**20:.0f} MB — a cópia não cabe com folga.")
    con = sqlite3.connect(banco, timeout=30)
    con.execute(f"VACUUM INTO '{copia.as_posix()}'")
    print("CÓPIA", copia, f"{copia.stat().st_size / 2**20:.0f} MB")
    con.row_factory = sqlite3.Row
    agora = datetime.now().isoformat(timespec="seconds")
    try:
        con.execute("BEGIN IMMEDIATE")
        medir(con)                                   # de novo, dentro da trava
        n = con.execute("UPDATE rc_assentos SET situacao='CANCELADO' "
                        "WHERE id=116 AND situacao='ATIVO'").rowcount
        if n != 1:
            raise Recusa(f"RECUSO: o UPDATE mudou {n} linhas.")
        antes = dict(con.execute("SELECT * FROM nu_numeracao WHERE serie='RC_E'"
                                 ).fetchone() or {})
        con.execute("DELETE FROM nu_numeracao WHERE serie='RC_E'")
        for acao, tipo, eid, det in (
                ("RCPN_ASSENTO_CANCELADO", "rc_assentos", 116,
                 {"motivo": MOTIVO, "mantido": 6189, "por": QUEM,
                  "backup_db": str(copia)}),
                ("NUMERACAO_SEMENTE_DESFEITA", "nu_numeracao", None,
                 {"serie": "RC_E", "antes": antes, "por": QUEM,
                  "backup_db": str(copia),
                  "motivo": "a semente vinha só do assento 116, cancelado; o "
                            "próximo número fica em aberto (pendência "
                            "numeracao:RC_E), por ordem do oficial"})):
            con.execute(
                "INSERT INTO audit_logs(ts, user_id, username_snapshot, action, "
                "entity_type, entity_id, details, ip_address) "
                "VALUES (?, NULL, ?, ?, ?, ?, ?, NULL)",
                (agora, "agente-rcpn", acao, tipo, eid,
                 json.dumps(det, ensure_ascii=False)))
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    print("GRAVADO: 116 CANCELADO; contador RC_E desfeito; auditoria escrita.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
