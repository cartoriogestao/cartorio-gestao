#!/bin/bash
# INSTALA O EXECUTOR DA CI NO SERVIDOR RESERVA (macOS) — roda UMA vez, com sudo.
#
#   sudo bash ci/suite/instalar_executor.sh
#
# O que faz (e só isto):
#   1. fecha a pasta pessoal de quem roda (700): o usuário novo não a lê;
#   2. cria o usuário `ci-runner`, padrão (não administrador), sem senha de login;
#   3. sobe a máquina virtual Linux dele (Colima, perfil `ci`), que só monta a área
#      de trabalho do executor — nenhuma outra pasta do Mac;
#   4. baixa o executor do GitHub Actions (versão conferida pelo SHA-256 publicado),
#      registra-o SÓ neste repositório, com o rótulo `cartorio-suite`;
#   5. instala os dois serviços (máquina virtual e executor) como LaunchDaemons do
#      `ci-runner`, que sobem com o Mac e se reiniciam sozinhos.
#
# O token de registro é pedido ao GitHub pelo `gh` de quem chamou o sudo e vale uma
# hora; ele não fica gravado em lugar nenhum.
#
# Desfazer: ver docs/CI_EXECUTOR.md, «Remover o executor».
set -euo pipefail
cd /   # nada de rodar a partir de uma pasta que o ci-runner não pode ler

REPO="cartoriogestao/cartorio-gestao"
USUARIO="ci-runner"
CASA="/Users/$USUARIO"
EXECUTOR="$CASA/actions-runner"
TRABALHO="$EXECUTOR/_work"
BREW="/opt/homebrew/bin"
CPUS="${CG_CI_CPUS:-14}"
MEMORIA="${CG_CI_MEMORIA_GB:-18}"

[ "$(id -u)" -eq 0 ] || { echo "Rode com sudo."; exit 1; }
QUEM="${SUDO_USER:?rode com sudo a partir do seu usuário}"
[ -x "$BREW/colima" ] && [ -x "$BREW/docker" ] || { echo "Falta o Colima/Docker: brew install colima docker"; exit 1; }

echo "== 1. a pasta pessoal de $QUEM fica só dele"
chmod 700 "/Users/$QUEM"

echo "== 2. o usuário $USUARIO"
if ! id "$USUARIO" >/dev/null 2>&1; then
  SENHA="$(openssl rand -base64 32)"   # ninguém a usa: o usuário não entra pela tela
  sysadminctl -addUser "$USUARIO" -fullName "Executor da CI" -password "$SENHA" -home "$CASA" >/dev/null 2>&1
  unset SENHA
  createhomedir -c -u "$USUARIO" >/dev/null
  dscl . -create "/Users/$USUARIO" IsHidden 1
fi
chmod 700 "$CASA"
sudo -u "$USUARIO" mkdir -p "$TRABALHO"

echo "== 3. o executor do GitHub Actions"
if [ ! -x "$EXECUTOR/run.sh" ]; then
  INFO="$(sudo -u "$QUEM" "$BREW/gh" api repos/actions/runner/releases/latest)"
  VERSAO="$(printf '%s' "$INFO" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"].lstrip("v"))')"
  ARQUIVO="actions-runner-osx-arm64-$VERSAO.tar.gz"
  # O SHA-256 por DUAS fontes que precisam concordar: o campo `digest` do arquivo na API
  # e a marcação «BEGIN SHA osx-arm64» da página da versão. (A primeira versão deste
  # roteiro pegava o primeiro número depois do nome do arquivo — que era o do Windows.)
  ESPERADO="$(printf '%s' "$INFO" | /usr/bin/python3 -c "
import json,re,sys
info=json.load(sys.stdin)
api=[a.get('digest') or '' for a in info['assets'] if a['name']=='$ARQUIVO']
api=api[0].removeprefix('sha256:') if api else ''
m=re.search(r'BEGIN SHA osx-arm64 -->\s*([0-9a-f]{64})\s*<!-- END SHA osx-arm64', info['body'])
pagina=m.group(1) if m else ''
print(api if api and api==pagina else '')")"
  [ -n "$ESPERADO" ] || { echo "O SHA-256 de $ARQUIVO não confere entre a API e a página da versão."; exit 1; }
  sudo -u "$USUARIO" curl -fsSL -o "$EXECUTOR/$ARQUIVO" \
    "https://github.com/actions/runner/releases/download/v$VERSAO/$ARQUIVO"
  OBTIDO="$(shasum -a 256 "$EXECUTOR/$ARQUIVO" | cut -d' ' -f1)"
  [ "$OBTIDO" = "$ESPERADO" ] || { echo "SHA-256 não confere: $OBTIDO ≠ $ESPERADO"; exit 1; }
  sudo -u "$USUARIO" tar -xzf "$EXECUTOR/$ARQUIVO" -C "$EXECUTOR"
  rm -f "$EXECUTOR/$ARQUIVO"
fi
if [ ! -f "$EXECUTOR/.runner" ]; then
  TOKEN="$(sudo -u "$QUEM" "$BREW/gh" api -X POST "repos/$REPO/actions/runners/registration-token" --jq .token)"
  ( cd "$EXECUTOR" && sudo -u "$USUARIO" ./config.sh --unattended --replace \
      --url "https://github.com/$REPO" --token "$TOKEN" \
      --name "servidor-reserva" --labels "cartorio-suite" --work "_work" --no-default-labels )
  unset TOKEN
fi

echo "== 4. os serviços"
cat > /Library/LaunchDaemons/br.cartoriogestao.ci-colima.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>br.cartoriogestao.ci-colima</string>
  <key>UserName</key><string>$USUARIO</string>
  <key>EnvironmentVariables</key><dict>
    <key>HOME</key><string>$CASA</string>
    <key>PATH</key><string>$BREW:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>ProgramArguments</key><array>
    <string>$BREW/colima</string><string>start</string><string>--profile</string><string>ci</string>
    <string>--foreground</string><string>--vm-type</string><string>vz</string>
    <string>--cpu</string><string>$CPUS</string><string>--memory</string><string>$MEMORIA</string>
    <string>--disk</string><string>80</string><string>--mount-type</string><string>virtiofs</string>
    <string>--mount</string><string>$TRABALHO:w</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$CASA/colima.log</string>
  <key>StandardErrorPath</key><string>$CASA/colima.log</string>
</dict></plist>
EOF
cat > /Library/LaunchDaemons/br.cartoriogestao.ci-executor.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>br.cartoriogestao.ci-executor</string>
  <key>UserName</key><string>$USUARIO</string>
  <key>WorkingDirectory</key><string>$EXECUTOR</string>
  <key>EnvironmentVariables</key><dict>
    <key>HOME</key><string>$CASA</string>
    <key>PATH</key><string>$BREW:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>CG_DOCKER_CONTEXTO</key><string>colima-ci</string>
    <key>CG_SUITE_PROCESSOS</key><string>$CPUS</string>
  </dict>
  <key>ProgramArguments</key><array><string>$EXECUTOR/run.sh</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$CASA/executor.log</string>
  <key>StandardErrorPath</key><string>$CASA/executor.log</string>
</dict></plist>
EOF
chmod 644 /Library/LaunchDaemons/br.cartoriogestao.ci-*.plist
for s in ci-colima ci-executor; do
  launchctl bootout system "/Library/LaunchDaemons/br.cartoriogestao.$s.plist" 2>/dev/null || true
  launchctl bootstrap system "/Library/LaunchDaemons/br.cartoriogestao.$s.plist"
done

echo
echo "Pronto. O executor «servidor-reserva» aparece em"
echo "  https://github.com/$REPO/settings/actions/runners"
echo "A primeira suíte monta a imagem (uns 10 minutos, com rede); as seguintes não."
