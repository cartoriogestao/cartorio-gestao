#!/bin/bash
# INSTALA A CHAVE DA SUÍTE no servidor reserva (macOS) — roda uma vez, com sudo.
#
#   sudo bash ci/chave/instalar_chave.sh
#   bash ci/chave/montar_app.sh          # o app da barra de menus (sem sudo)
#
# O que faz (e só isto):
#   1. copia o controlador para uma pasta do root (o root não roda código de pasta
#      que o usuário pode trocar);
#   2. cria a pasta do pedido, do usuário que chamou o sudo (é nela que o app grava);
#   3. baixa o teto da VM da suíte de 18 para 12 GB, e o do contêiner de 16 para 10 GB
#      (a suíte usa uns 9 GB; vale a partir da próxima vez que a VM ligar);
#   4. instala o controlador como LaunchDaemon (br.cartoriogestao.ci-chave).
#
# Desfazer: ver docs/CI_EXECUTOR.md, «A chave da suíte».
set -euo pipefail
trap 'echo "PAROU na linha $LINENO: $BASH_COMMAND" >&2' ERR

[ "$(id -u)" -eq 0 ] || { echo "Rode com sudo."; exit 1; }
QUEM="${SUDO_USER:?rode com sudo a partir do seu usuário}"
AQUI="$(cd "$(dirname "$0")" && pwd)"
cd /

ROTULO="br.cartoriogestao.ci-chave"
PROGRAMA="/Library/Application Support/CartorioGestao/chave-da-suite"
PEDIDOS="/Users/Shared/CartorioGestao/chave-da-suite"
LOGS="/Library/Logs/CartorioGestao"
VM_PLIST="/Library/LaunchDaemons/br.cartoriogestao.ci-colima.plist"
EXEC_PLIST="/Library/LaunchDaemons/br.cartoriogestao.ci-executor.plist"
MEMORIA_VM="${CG_CI_MEMORIA_GB:-12}"
MEMORIA_CONTEINER="${CG_SUITE_MEMORIA:-$((MEMORIA_VM - 2))g}"

[ -f "$VM_PLIST" ] && [ -f "$EXEC_PLIST" ] || { echo "O executor da suíte não está instalado (ci/suite/instalar_executor.sh)."; exit 1; }

echo "== 1. o controlador, numa pasta do root"
install -d -o root -g wheel -m 755 "$PROGRAMA" "$LOGS"
install -o root -g wheel -m 755 "$AQUI/controlador.py" "$PROGRAMA/controlador.py"

echo "== 2. a pasta do pedido, de $QUEM"
install -d -o root -g wheel -m 755 /Users/Shared/CartorioGestao
install -d -o "$QUEM" -g staff -m 755 "$PEDIDOS"
if [ ! -f "$PEDIDOS/pedido.json" ]; then
  sudo -u "$QUEM" /bin/sh -c "umask 022; cat > '$PEDIDOS/pedido.json'" <<'EOF'
{
  "agenda" : [ { "dias" : [ 0, 1, 2, 3, 4 ], "fim" : "18:00", "inicio" : "08:00" } ],
  "modo" : "auto"
}
EOF
fi

echo "== 3. o teto da VM: ${MEMORIA_VM} GB; o do contêiner: ${MEMORIA_CONTEINER}"
/usr/bin/python3 - "$VM_PLIST" "$EXEC_PLIST" "$MEMORIA_VM" "$MEMORIA_CONTEINER" <<'EOF'
import plistlib, sys
vm, exe, memoria, conteiner = sys.argv[1:]
with open(vm, "rb") as f:
    p = plistlib.load(f)
args = p["ProgramArguments"]
args[args.index("--memory") + 1] = memoria
p["ExitTimeOut"] = 180          # o colima precisa de tempo para parar a VM com calma
with open(vm, "wb") as f:
    plistlib.dump(p, f)
with open(exe, "rb") as f:
    p = plistlib.load(f)
p["EnvironmentVariables"]["CG_SUITE_MEMORIA"] = conteiner
with open(exe, "wb") as f:
    plistlib.dump(p, f)
EOF
chmod 644 "$VM_PLIST" "$EXEC_PLIST"

echo "== 4. o serviço da chave"
cat > "/Library/LaunchDaemons/$ROTULO.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$ROTULO</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/python3</string><string>-I</string><string>$PROGRAMA/controlador.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOGS/chave-da-suite.log</string>
  <key>StandardErrorPath</key><string>$LOGS/chave-da-suite.log</string>
</dict></plist>
EOF
chmod 644 "/Library/LaunchDaemons/$ROTULO.plist"
launchctl bootout "system/$ROTULO" 2>/dev/null || true
launchctl enable "system/$ROTULO"
launchctl bootstrap system "/Library/LaunchDaemons/$ROTULO.plist"

echo
echo "Pronto. A chave já vale (padrão: IA de seg a sex, 8h–18h; suíte no resto)."
echo "O teto novo da VM vale na próxima vez que ela ligar."
echo "Agora o app, sem sudo:  bash ci/chave/montar_app.sh"
