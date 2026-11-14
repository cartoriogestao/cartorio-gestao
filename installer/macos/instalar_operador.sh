#!/bin/bash
# INSTALA O SUPERUSUÁRIO NO SERVIDOR RESERVA (docs/SUPERUSUARIO.md).
# Rode da pasta do código instalado: bash installer/macos/instalar_operador.sh
#
# O que faz (e pode rodar de novo: o que já existe fica como está):
#   1. confere que o servidor reserva está instalado e que o Claude Code existe;
#   2. cria <dados>/operador/operador.cred a partir do exemplo (chmod 600);
#   3. monta o POSTO (<dados>/operador/posto): a pasta de onde o superusuário trabalha;
#   4. com o operador.cred dizendo como ele fala com a Anthropic, instala o LaunchAgent
#      <prefixo>.operador (a ponte: Telegram e tela do sistema);
#   5. com OPERADOR_APP=1, instala o <prefixo>.operador-app (o Remote Control, para o app
#      do Claude).
# NÃO baixa nem instala o Claude Code, e não escreve chave nenhuma: isso é do oficial.
set -euo pipefail
PASTA="$HOME/Library/Application Support/CartorioGestao"
AGENTES="$HOME/Library/LaunchAgents"
PREFIXO="${CG_LAUNCHD_PREFIXO:-br.com.cartoriogestao}"
OPERADOR="$PASTA/operador"
CRED="$OPERADOR/operador.cred"
PY="$PASTA/venv/bin/python"

falha() { echo "PAROU: $*" >&2; exit 1; }
[ "$(uname)" = "Darwin" ] || falha "este instalador é do macOS"
[ -f "$PASTA/reserva.env" ] || falha "falta o servidor reserva: rode antes o instalar_reserva.sh"
[ -f "$PASTA/sistema/operador/posto.py" ] || falha "o código instalado em $PASTA/sistema ainda não tem o superusuário desta versão (atualize o sistema)"
[ -x "$PY" ] || falha "falta o venv em $PASTA/venv"

mkdir -p "$OPERADOR" "$AGENTES" "$PASTA/logs"
chmod 700 "$OPERADOR"
if [ ! -f "$CRED" ]; then
  cp "$PASTA/sistema/operador/operador_cred.exemplo" "$CRED"
  echo "Criei $CRED"
fi
chmod 600 "$CRED"

CLAUDE="$(PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH" command -v claude || true)"
valor() { grep -E "^$1=" "$CRED" | tail -1 | cut -d= -f2- | tr -d "\"'" ; }

# O posto: a pasta de onde o superusuário trabalha, por qualquer porta.
POSTO="$(set -a; source "$PASTA/reserva.env"; set +a
         OPERADOR_AMBIENTE="$PASTA/reserva.env" OPERADOR_NOME=reserva "$PY" "$PASTA/sistema/operador/posto.py" onde)"
echo "Posto do superusuário: $POSTO"

paga=""
for chave in CLAUDE_CODE_OAUTH_TOKEN OPERADOR_ASSINATURA ANTHROPIC_API_KEY OPERADOR_CHAVE_DA_CASA; do
  [ -z "$(valor "$chave")" ] || paga="$chave"
done
if [ -z "$paga" ] || [ -z "$CLAUDE" ]; then
  echo
  echo "Ainda não liguei a ponte. Falta:"
  [ -n "$CLAUDE" ] || echo "  - instalar o Claude Code neste Mac (https://code.claude.com/docs/en/setup)"
  [ -n "$paga" ] || echo "  - dizer em $CRED como ele fala com a Anthropic (a parte 1 do arquivo):"
  [ -n "$paga" ] || echo "    pela assinatura (claude setup-token), ou pela API (uma chave)"
  echo "Depois rode este instalador de novo."
  exit 0
fi

plist() {  # plist <nome> <argumento do iniciar_operador.sh ou vazio>
  local arquivo="$AGENTES/$PREFIXO.$1.plist"
  {
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
    echo '<plist version="1.0"><dict>'
    echo "  <key>Label</key><string>$PREFIXO.$1</string>"
    echo '  <key>ProgramArguments</key><array>'
    echo '    <string>/bin/bash</string>'
    echo "    <string>$PASTA/sistema/installer/macos/iniciar_operador.sh</string>"
    [ -z "$2" ] || echo "    <string>$2</string>"
    echo '  </array>'
    echo "  <key>EnvironmentVariables</key><dict><key>PGPASSFILE</key><string>$HOME/.pgpass</string></dict>"
    echo '  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>'
    echo '  <key>ThrottleInterval</key><integer>30</integer>'
    echo '  <key>ProcessType</key><string>Background</string>'
    echo "  <key>StandardOutPath</key><string>$PASTA/logs/$1.log</string>"
    echo "  <key>StandardErrorPath</key><string>$PASTA/logs/$1.log</string>"
    echo '</dict></plist>'
  } > "$arquivo"
  launchctl bootout "gui/$(id -u)/$PREFIXO.$1" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$arquivo"
}

plist operador ""
echo "A ponte do superusuário está no ar ($PREFIXO.operador): atende a tela do sistema"
if [ -n "$(valor TELEGRAM_TOKEN)" ]; then
  echo "e o Telegram."
  if [ -z "$(valor OPERADOR_TELEGRAM_USUARIO)" ]; then
    echo "Agora escreva qualquer coisa para o bot no Telegram: ele responde o seu número de usuário."
    echo "Ponha esse número em OPERADOR_TELEGRAM_USUARIO, em $CRED, e rode este instalador de novo."
  fi
else
  echo "(sem TELEGRAM_TOKEN: o Telegram fica desligado)."
fi

if [ "$(valor OPERADOR_APP)" = "1" ]; then
  plist operador-app app
  echo "A porta do app do Claude está no ar ($PREFIXO.operador-app). Se o registro"
  echo "($PASTA/logs/operador-app.log) pedir login, rode nesta conta: claude auth login"
else
  launchctl bootout "gui/$(id -u)/$PREFIXO.operador-app" 2>/dev/null || true
fi

echo
echo "Para provar neste Mac que a guarda e o relatório funcionam com o Claude Code instalado"
echo "(não gasta a API e não toca no banco):"
echo "  \"$PY\" \"$PASTA/sistema/operador/ensaio.py\""
echo "Registros: $PASTA/logs/operador.log e $OPERADOR/ponte.log"
