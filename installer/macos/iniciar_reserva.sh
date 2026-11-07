#!/bin/bash
# O servidor do Cartório Gestão no macOS — o que o LaunchAgent roda (KeepAlive: se cair, volta).
# Lê a configuração de reserva.env; com CG_MODO_RESERVA=1 é o servidor reserva (só lê).
set -euo pipefail
# A pasta da instalação: este script mora em <pasta>/sistema/installer/macos.
PASTA="$(cd "$(dirname "$0")/../../.." && pwd)"
CODIGO="$PASTA/sistema"
set -a; source "$PASTA/reserva.env"; set +a
export CARTORIO_GESTAO_NO_BROWSER=1
export PGPASSFILE="${PGPASSFILE:-$HOME/.pgpass}"
cd "$CODIGO"
exec "$PASTA/venv/bin/python" app.py --service
