from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

from database import Database


def data_dir() -> Path:
    override = os.environ.get("CARTORIO_GESTAO_DATA")
    if override:
        return Path(override)
    base = os.environ.get("PROGRAMDATA") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "CartorioGestao"


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: admin_cli.py network-config | force-network | migrate-data-paths OLD NEW")
        return 2
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True)
    db = Database(root / "cartorio_gestao.sqlite3")
    cmd = sys.argv[1]
    if cmd == "network-config":
        print(json.dumps({
            "host": db.get_setting("network_host", "0.0.0.0"),
            "port": int(db.get_setting("network_port", "8765")),
            "discovery_enabled": db.get_setting("discovery_enabled", "1"),
            "discovery_port": int(db.get_setting("discovery_port", "8766")),
        }))
        return 0
    if cmd == "force-network":
        db.set_settings({"network_host": "0.0.0.0", "discovery_enabled": "1", "discovery_port": "8766"})
        print("ok")
        return 0
    if cmd == "migrate-data-paths":
        if len(sys.argv) != 4:
            return 2
        old = str(Path(sys.argv[2]).resolve())
        new = str(Path(sys.argv[3]).resolve())
        with db.transaction() as con:
            rows = list(con.execute("SELECT id, stored_path FROM attachments"))
            for row in rows:
                path = row["stored_path"] or ""
                if path.lower().startswith(old.lower()):
                    replacement = new + path[len(old):]
                    con.execute("UPDATE attachments SET stored_path=? WHERE id=?", (replacement, row["id"]))
            for key in ("archive_root", "backup_dir"):
                row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
                if row and (row["value"] or "").lower().startswith(old.lower()):
                    replacement = new + row["value"][len(old):]
                    con.execute("UPDATE settings SET value=? WHERE key=?", (replacement, key))
        print("ok")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
