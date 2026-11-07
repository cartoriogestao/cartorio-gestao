#!/bin/bash
# A RESERVA ASSUME — o servidor Windows caiu e não volta hoje. Uso: assumir.sh ASSUMIR
#
# ANTES: o servidor Windows tem de estar DESLIGADO (ou o serviço do Cartório Gestão parado lá).
# Dois servidores lançando dariam o mesmo número de protocolo, selo ou ato duas vezes.
#
# O que faz, nesta ordem:
#   1. desliga a réplica e acerta o próximo número de cada tabela (tools/reserva.py assumir);
#   2. a pasta de arquivos do sistema, e as outras pastas configuradas, passam a ser as cópias
#      deste Mac;
#   3. troca reserva.env para o modo principal (CG_MODO_RESERVA=0, usuário cg do banco);
#   4. reinicia o servidor: ele sobe na porta do principal (8765) e responde à descoberta, e os
#      balcões o acham sozinhos.
set -euo pipefail
if [ "${1:-}" != "ASSUMIR" ]; then
  echo "Uso: $0 ASSUMIR"
  echo "Antes, confira que o servidor Windows está DESLIGADO."
  exit 2
fi
# A pasta da instalação: este script mora em <pasta>/sistema/installer/macos.
PASTA="$(cd "$(dirname "$0")/../../.." && pwd)"
ENV="$PASTA/reserva.env"
set -a; source "$ENV"; set +a
export PGPASSFILE="${PGPASSFILE:-$HOME/.pgpass}"
PY="$PASTA/venv/bin/python"

"$PY" "$PASTA/sistema/tools/reserva.py" assumir --confirmo ASSUMIR

# 2. a pasta dos arquivos (a do banco é a do Windows, C:\...)
"$CG_PG_BIN/psql" -X -q -v ON_ERROR_STOP=1 -d "$CG_RESERVA_LOCAL_DSN" \
  -v pasta="$CG_RESERVA_ARQUIVOS" -v schema="$CG_PG_SCHEMA" <<'SQL'
SET search_path TO :"schema";
UPDATE settings SET value = :'pasta' WHERE key = 'archive_root';
SQL
# e as pastas configuradas fora dela, que têm cópia aqui
"$PY" "$PASTA/sistema/tools/reserva.py" pastas --apontar

# 3. o modo principal (cópia do arquivo antigo ao lado)
cp "$ENV" "$ENV.antes-de-assumir"
sed -i '' -e 's/^CG_MODO_RESERVA=.*/CG_MODO_RESERVA=0/' \
          -e 's/user=cg_leitor/user=cg/' "$ENV"

# 4. reiniciar
launchctl kickstart -k "gui/$(id -u)/${CG_LAUNCHD_PREFIXO:-br.com.cartoriogestao}.servidor"
echo "Pronto: este Mac é o servidor principal. Avise os balcões; o endereço novo aparece na tela de"
echo "descoberta. NÃO ligue o servidor Windows de novo sem seguir «a volta do principal» no roteiro."
