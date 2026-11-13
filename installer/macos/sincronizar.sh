#!/bin/bash
# A SINCRONIA DA RESERVA, de 5 em 5 minutos (LaunchAgent). Nesta ordem:
#   1. a pasta de arquivos do principal → a cópia local (sem apagar nada daqui), e as pastas
#      configuradas fora dela (`reserva.py pastas`);
#   2. o esquema: tabela ou coluna nova de uma versão nova do principal entra antes das linhas
#      (sem isto a réplica para na primeira linha que as usa);
#   3. o programa: a etiqueta que o principal publicou, só com o esquema já igual
#      (`reserva.py versao`);
#   4. os segredos da pasta de dados (`reserva.py chaves`: o pacote cifrado para este Mac);
#   5. a situação da réplica, anotada em sincronia.log — o `situacao` sai 1 se atrasou.
# Depois de assumir (CG_MODO_RESERVA=0), não faz mais nada: não há de onde copiar.
set -uo pipefail
# A pasta da instalação: este script mora em <pasta>/sistema/installer/macos.
PASTA="$(cd "$(dirname "$0")/../../.." && pwd)"
LOG="$PASTA/sincronia.log"
set -a; source "$PASTA/reserva.env"; set +a
export PGPASSFILE="${PGPASSFILE:-$HOME/.pgpass}"
[ "${CG_MODO_RESERVA:-0}" = "1" ] || exit 0
PY="$PASTA/venv/bin/python"; FERRAMENTA="$PASTA/sistema/tools/reserva.py"
agora() { date "+%Y-%m-%d %H:%M:%S"; }

# 1. os arquivos (a senha do compartilhamento fica nas Chaves do macOS: ver o roteiro)
if [ -n "${CG_RESERVA_SMB:-}" ]; then
  PONTO="$PASTA/principal-arquivos"
  mkdir -p "$PONTO" "$CG_RESERVA_ARQUIVOS"
  if ! mount | grep -q " on $PONTO "; then
    mount_smbfs "$CG_RESERVA_SMB" "$PONTO" 2>>"$LOG" || echo "$(agora) arquivos: não montei $CG_RESERVA_SMB" >>"$LOG"
  fi
  if mount | grep -q " on $PONTO "; then
    # -rt sem --delete: o que sumiu do principal continua aqui (a cópia é de segurança).
    rsync -rt --partial --exclude '~$*' --exclude '*.tmp' "$PONTO/" "$CG_RESERVA_ARQUIVOS/" 2>>"$LOG" \
      || echo "$(agora) arquivos: a cópia parou com erro (ver acima)" >>"$LOG"
  fi
fi

# 1b. as pastas configuradas FORA da pasta de arquivos (cada uma do seu compartilhamento)
"$PY" "$FERRAMENTA" pastas >>"$LOG" 2>&1 || echo "$(agora) pastas: falhou" >>"$LOG"

# 2. o esquema, 3. a versão do programa, 4. as chaves e 5. a situação
"$PY" "$FERRAMENTA" esquema --aplicar >>"$LOG" 2>&1 || echo "$(agora) esquema: falhou" >>"$LOG"
"$PY" "$FERRAMENTA" versao >>"$LOG" 2>&1 || echo "$(agora) versao: falhou" >>"$LOG"
"$PY" "$FERRAMENTA" chaves >>"$LOG" 2>&1 || echo "$(agora) chaves: falhou" >>"$LOG"
echo "$(agora) $("$PY" "$FERRAMENTA" situacao 2>&1 | tr '\n' ' ')" >>"$LOG"
# o log não cresce sem fim: fica com as últimas 5000 linhas
tail -n 5000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
