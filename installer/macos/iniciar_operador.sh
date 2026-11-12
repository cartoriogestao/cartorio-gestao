#!/bin/bash
# A ponte do superusuário no macOS — o que o LaunchAgent roda (KeepAlive: se cair, volta).
# Parada, é um processo Python esperando o Telegram; o operador só existe durante um pedido.
# Lê o banco do reserva.env, como o servidor (docs/SUPERUSUARIO.md).
set -euo pipefail
# A pasta da instalação: este script mora em <pasta>/sistema/installer/macos.
PASTA="$(cd "$(dirname "$0")/../../.." && pwd)"
CODIGO="$PASTA/sistema"
set -a; source "$PASTA/reserva.env"; set +a
export PGPASSFILE="${PGPASSFILE:-$HOME/.pgpass}"
# O `claude` instalado pelo instalador oficial mora em ~/.local/bin; o psql, no CG_PG_BIN.
export PATH="$HOME/.local/bin:${CG_PG_BIN:-/opt/homebrew/bin}:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
cd "$CODIGO"
exec "$PASTA/venv/bin/python" operador/ponte.py
