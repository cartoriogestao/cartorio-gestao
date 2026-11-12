#!/bin/bash
# INSTALA A PONTE DO SUPERUSUÁRIO NO SERVIDOR RESERVA (docs/SUPERUSUARIO.md).
# Rode da pasta do código instalado: bash installer/macos/instalar_operador.sh
#
# O que faz (e pode rodar de novo: o que já existe fica como está):
#   1. confere que o servidor reserva está instalado e que o Claude Code existe;
#   2. cria <dados>/operador/operador.cred a partir do exemplo (chmod 600);
#   3. com o operador.cred preenchido, instala o LaunchAgent <prefixo>.operador.
# NÃO baixa nem instala o Claude Code, e não escreve chave nenhuma: isso é do oficial.
set -euo pipefail
PASTA="$HOME/Library/Application Support/CartorioGestao"
AGENTES="$HOME/Library/LaunchAgents"
PREFIXO="${CG_LAUNCHD_PREFIXO:-br.com.cartoriogestao}"
OPERADOR="$PASTA/operador"
CRED="$OPERADOR/operador.cred"

falha() { echo "PAROU: $*" >&2; exit 1; }
[ "$(uname)" = "Darwin" ] || falha "este instalador é do macOS"
[ -f "$PASTA/reserva.env" ] || falha "falta o servidor reserva: rode antes o instalar_reserva.sh"
[ -f "$PASTA/sistema/operador/ponte.py" ] || falha "o código instalado em $PASTA/sistema ainda não tem a pasta operador/ (atualize o sistema)"
[ -x "$PASTA/venv/bin/python" ] || falha "falta o venv em $PASTA/venv"

mkdir -p "$OPERADOR" "$AGENTES" "$PASTA/logs"
chmod 700 "$OPERADOR"
if [ ! -f "$CRED" ]; then
  cp "$PASTA/sistema/operador/operador_cred.exemplo" "$CRED"
  echo "Criei $CRED"
fi
chmod 600 "$CRED"

CLAUDE="$(PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH" command -v claude || true)"
if [ -z "$CLAUDE" ]; then
  echo "FALTA o Claude Code neste Mac. Instale (https://code.claude.com/docs/en/setup) e rode de novo."
fi

valor() { grep -E "^$1=" "$CRED" | tail -1 | cut -d= -f2- | tr -d "\"'" ; }
faltam=""
for chave in TELEGRAM_TOKEN ANTHROPIC_API_KEY; do
  [ -n "$(valor "$chave")" ] || faltam="$faltam $chave"
done
if [ -n "$faltam" ] || [ -z "$CLAUDE" ]; then
  echo
  echo "Ainda não liguei a ponte. Falta:"
  [ -z "$faltam" ] || echo "  - preencher em $CRED:$faltam"
  [ -n "$CLAUDE" ] || echo "  - instalar o Claude Code"
  echo "Depois rode este instalador de novo."
  exit 0
fi

PLIST="$AGENTES/$PREFIXO.operador.plist"
{
  echo '<?xml version="1.0" encoding="UTF-8"?>'
  echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
  echo '<plist version="1.0"><dict>'
  echo "  <key>Label</key><string>$PREFIXO.operador</string>"
  echo '  <key>ProgramArguments</key><array>'
  echo '    <string>/bin/bash</string>'
  echo "    <string>$PASTA/sistema/installer/macos/iniciar_operador.sh</string>"
  echo '  </array>'
  echo "  <key>EnvironmentVariables</key><dict><key>PGPASSFILE</key><string>$HOME/.pgpass</string></dict>"
  echo '  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>'
  echo '  <key>ThrottleInterval</key><integer>30</integer>'
  echo '  <key>ProcessType</key><string>Background</string>'
  echo "  <key>StandardOutPath</key><string>$PASTA/logs/operador.log</string>"
  echo "  <key>StandardErrorPath</key><string>$PASTA/logs/operador.log</string>"
  echo '</dict></plist>'
} > "$PLIST"
launchctl bootout "gui/$(id -u)/$PREFIXO.operador" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "A ponte do superusuário está no ar ($PREFIXO.operador)."
if [ -z "$(valor OPERADOR_TELEGRAM_USUARIO)" ]; then
  echo "Agora escreva qualquer coisa para o bot no Telegram: ele responde o seu número de usuário."
  echo "Ponha esse número em OPERADOR_TELEGRAM_USUARIO, em $CRED, e rode este instalador de novo."
fi
echo "Registro: $PASTA/logs/operador.log e $OPERADOR/ponte.log"
