#!/bin/bash
# Monta o app da chave (ChaveDaSuite.app) em ~/Applications e o abre a cada login.
# Roda como o usuário (sem sudo): o app não tem privilégio nenhum.
#
#   bash ci/chave/montar_app.sh
set -euo pipefail
trap 'echo "PAROU na linha $LINENO: $BASH_COMMAND" >&2' ERR
[ "$(id -u)" -ne 0 ] || { echo "Rode como o seu usuário, sem sudo."; exit 1; }

AQUI="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/Applications/ChaveDaSuite.app"
ROTULO="br.com.cartoriogestao.chave-da-suite"
AGENTE="$HOME/Library/LaunchAgents/$ROTULO.plist"

command -v swiftc >/dev/null || { echo "Falta o swiftc: xcode-select --install"; exit 1; }

echo "== compilando"
TMP="$(mktemp -d)"
swiftc -parse-as-library -swift-version 5 -O -target arm64-apple-macos14 \
  "$AQUI/ChaveDaSuite.swift" -o "$TMP/ChaveDaSuite"

echo "== montando $APP"
pkill -x ChaveDaSuite 2>/dev/null || true
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$HOME/Library/LaunchAgents"
mv "$TMP/ChaveDaSuite" "$APP/Contents/MacOS/ChaveDaSuite"
rmdir "$TMP"
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>$ROTULO</string>
  <key>CFBundleName</key><string>Chave da Suíte</string>
  <key>CFBundleDisplayName</key><string>Chave da Suíte</string>
  <key>CFBundleExecutable</key><string>ChaveDaSuite</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSUIElement</key><true/>
</dict></plist>
EOF
codesign --force --sign - "$APP" >/dev/null 2>&1 || true

echo "== abrir a cada login"
cat > "$AGENTE" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$ROTULO</string>
  <key>ProgramArguments</key><array><string>$APP/Contents/MacOS/ChaveDaSuite</string></array>
  <key>RunAtLoad</key><true/>
  <key>LimitLoadToSessionType</key><string>Aqua</string>
</dict></plist>
EOF
launchctl bootout "gui/$(id -u)/$ROTULO" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$AGENTE"
echo "Pronto: a chave aparece na barra de menus (ícone de tubo de ensaio ou de cérebro)."
