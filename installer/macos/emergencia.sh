#!/bin/bash
# O BOTÃO DE EMERGÊNCIA — o servidor Windows caiu (ou vai cair) e a reserva assume.
# Uso: emergencia.sh ASSUMIR
#
# Ordem, para nunca haver dois gravando:
#   1. se o Windows ainda responde, o aplicativo e as automações de lá ficam somente leitura;
#   2. a assinatura para (DISABLE SUBSCRIPTION) — a reserva não recebe mais nada;
#   3. um pg_dump da reserva, antes de ela passar a gravar;
#   4. as sequências sobem ao maior id;
#   5. as pastas e o reserva.env passam ao modo principal, e o serviço reinicia.
#
# A volta é `reserva.py voltar --confirmo VOLTAR` (docs/CONTINGENCIA_RESERVA.md).
# Este script não religa a réplica.
set -euo pipefail
if [ "${1:-}" != "ASSUMIR" ]; then
  echo "Uso: $0 ASSUMIR"
  echo "Antes: confira que o Windows não vai continuar lançando."
  exit 2
fi
PASTA="$(cd "$(dirname "$0")/../../.." && pwd)"
ENV="$PASTA/reserva.env"
set -a; source "$ENV"; set +a
export PGPASSFILE="${PGPASSFILE:-$HOME/.pgpass}"
PY="$PASTA/venv/bin/python"

"$PY" "$PASTA/sistema/tools/reserva.py" emergencia --confirmo EMERGENCIA

"$CG_PG_BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$CG_RESERVA_LOCAL_DSN" \
  -v pasta="$CG_RESERVA_ARQUIVOS" -v schema="$CG_PG_SCHEMA" <<'SQL'
SET search_path TO :"schema";
UPDATE settings SET value = :'pasta' WHERE key = 'archive_root';
SQL
"$PY" "$PASTA/sistema/tools/reserva.py" pastas --apontar

cp "$ENV" "$ENV.antes-de-assumir"
sed -i '' -e 's/^CG_MODO_RESERVA=.*/CG_MODO_RESERVA=0/' \
          -e 's/user=cg_leitor/user=cg/' "$ENV"

launchctl kickstart -k "gui/$(id -u)/${CG_LAUNCHD_PREFIXO:-br.com.cartoriogestao}.servidor"
echo "Pronto: este Mac grava. O Windows, se respondeu, está somente leitura."
echo "Não ligue os dois para gravar. A volta está em docs/CONTINGENCIA_RESERVA.md."
