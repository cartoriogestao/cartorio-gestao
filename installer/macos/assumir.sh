#!/bin/bash
# O assumir passou a ser o botão de emergência: trava o principal se ele
# responder, desliga a réplica, despeja a reserva e só então promove.
# Uso: assumir.sh ASSUMIR
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/emergencia.sh" "$@"
