#!/bin/bash
# A ponte do superusuário no macOS — o que o LaunchAgent roda (KeepAlive: se cair, volta).
# Parada, é um processo Python esperando o Telegram e olhando a bandeja da tela do sistema;
# o operador só existe durante um pedido. Lê o banco do reserva.env, como o servidor
# (docs/SUPERUSUARIO.md).
#
# Com «app» por argumento, sobe a outra porta: o Remote Control do Claude Code, de dentro do
# posto, para o oficial usar o superusuário pelo app do Claude (celular ou claude.ai/code),
# com a assinatura dele. Exige `claude auth login` feito nesta conta.
set -euo pipefail
# A pasta da instalação: este script mora em <pasta>/sistema/installer/macos.
PASTA="$(cd "$(dirname "$0")/../../.." && pwd)"
CODIGO="$PASTA/sistema"
set -a; source "$PASTA/reserva.env"; set +a
export PGPASSFILE="${PGPASSFILE:-$HOME/.pgpass}"
# O reserva.env muda quando o reserva assume (emergencia.sh). A ponte e o posto o releem a cada
# pedido por este caminho: sem isto, ficariam com o ambiente de réplica justamente na emergência.
export OPERADOR_AMBIENTE="$PASTA/reserva.env"
# Este Mac é o reserva mesmo depois de assumir: o nome não muda, a situação sim.
export OPERADOR_NOME="${OPERADOR_NOME:-reserva}"
# O `claude` instalado pelo instalador oficial mora em ~/.local/bin; o psql, no CG_PG_BIN.
export PATH="$HOME/.local/bin:${CG_PG_BIN:-/opt/homebrew/bin}:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
PY="$PASTA/venv/bin/python"
if [ "${1:-}" = "app" ]; then
  POSTO="$("$PY" "$CODIGO/operador/posto.py" onde)"
  cd "$POSTO"
  # A assinatura, e nunca a API: com a chave no ambiente o Remote Control nem sobe.
  unset ANTHROPIC_API_KEY
  exec claude remote-control --name "Cartório Reserva" --capacity 2
fi
cd "$CODIGO"
exec "$PY" operador/ponte.py
