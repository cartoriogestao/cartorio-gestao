#!/bin/bash
# INSTALA O SERVIDOR RESERVA NUM macOS (docs/SERVIDOR_RESERVA_MACOS.md, parte B).
# Rode da pasta do código: bash installer/macos/instalar_reserva.sh
#
# O que faz (e pode rodar de novo: o que já existe fica como está):
#   1. confere o Homebrew, o PostgreSQL 18 e o Python 3.12;
#   2. copia o código para ~/Library/Application Support/CartorioGestao/sistema e monta o venv;
#   3. cria o banco da reserva (um PostgreSQL só dela, porta 5434, com senha), os usuários cg e
#      cg_leitor, e as senhas no ~/.pgpass (chmod 600);
#   4. instala três LaunchAgents: o PostgreSQL, o servidor e a sincronia de 5 em 5 minutos.
# NÃO liga a réplica: isso é o `reserva.py montar`, depois do lado do Windows pronto (parte A).
set -euo pipefail
CODIGO_ORIGEM="$(cd "$(dirname "$0")/../.." && pwd)"
PASTA="$HOME/Library/Application Support/CartorioGestao"
AGENTES="$HOME/Library/LaunchAgents"
# Os três podem vir do ambiente (Postgres.app, outra porta, um ensaio ao lado da instalação real).
PREFIXO="${CG_LAUNCHD_PREFIXO:-br.com.cartoriogestao}"
PORTA_PG="${CG_RESERVA_PG_PORTA:-5434}"

falha() { echo "PAROU: $*" >&2; exit 1; }
[ "$(uname)" = "Darwin" ] || falha "este instalador é do macOS"
command -v brew >/dev/null || falha "instale o Homebrew (https://brew.sh) e rode de novo"
PG_BIN="${CG_PG_BIN:-$(brew --prefix postgresql@18 2>/dev/null)/bin}"
[ -x "$PG_BIN/postgres" ] || falha "falta o PostgreSQL 18: brew install postgresql@18"
PY="$(brew --prefix python@3.12 2>/dev/null)/bin/python3.12"
[ -x "$PY" ] || falha "falta o Python 3.12: brew install python@3.12"

mkdir -p "$PASTA" "$AGENTES" "$PASTA/logs"
chmod 700 "$PASTA"

echo "1/4 código e Python"
rsync -a --delete --exclude .git --exclude venv --exclude '__pycache__' "$CODIGO_ORIGEM/" "$PASTA/sistema/"
[ -x "$PASTA/venv/bin/python" ] || "$PY" -m venv "$PASTA/venv"
"$PASTA/venv/bin/pip" install -q --upgrade pip
"$PASTA/venv/bin/pip" install -q -r "$PASTA/sistema/requirements.txt"

echo "2/4 configuração"
if [ ! -f "$PASTA/reserva.env" ]; then
  sed -e "s#^CG_PG_BIN=.*#CG_PG_BIN=$PG_BIN#" -e "s#host=127.0.0.1 port=5434#host=127.0.0.1 port=$PORTA_PG#" \
      -e "s#^CG_LAUNCHD_PREFIXO=.*#CG_LAUNCHD_PREFIXO=$PREFIXO#" \
      -e "s#\$HOME/Library/Application Support/CartorioGestao#$PASTA#" \
      "$PASTA/sistema/installer/macos/reserva.env.exemplo" > "$PASTA/reserva.env"
  echo "   criado $PASTA/reserva.env — ponha nele o IP do servidor Windows"
fi
chmod 600 "$PASTA/reserva.env"

echo "3/4 o banco da reserva (porta $PORTA_PG)"
touch "$HOME/.pgpass"; chmod 600 "$HOME/.pgpass"
senha_de() {   # a senha do usuário $1 no ~/.pgpass deste Mac; sorteia e anota se não houver
  local linha; linha=$(grep "^127.0.0.1:$PORTA_PG:\*:$1:" "$HOME/.pgpass" || true)
  if [ -z "$linha" ]; then
    local s; s=$(openssl rand -base64 24 | tr -d '/+=:' | cut -c1-24)
    echo "127.0.0.1:$PORTA_PG:*:$1:$s" >> "$HOME/.pgpass"; echo "$s"
  else echo "${linha##*:}"; fi
}
SENHA_CG=$(senha_de cg); SENHA_LEITOR=$(senha_de cg_leitor)
if [ ! -d "$PASTA/pg" ]; then
  PW=$(mktemp); echo "$SENHA_CG" > "$PW"
  "$PG_BIN/initdb" -D "$PASTA/pg" -U cg --pwfile="$PW" --auth=scram-sha-256 \
    --encoding=UTF8 --locale-provider=icu --icu-locale=pt-BR --locale=C > "$PASTA/logs/initdb.log"
  rm -f "$PW"
  printf "port = %s\nlisten_addresses = '127.0.0.1'\n" "$PORTA_PG" >> "$PASTA/pg/postgresql.conf"
fi

plist() {   # nome, programa e argumentos..., com KeepAlive/RunAtLoad ou StartInterval (SEGUNDOS=)
  local nome="$1"; shift
  {
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
    echo '<plist version="1.0"><dict>'
    echo "  <key>Label</key><string>$PREFIXO.$nome</string>"
    echo '  <key>ProgramArguments</key><array>'
    for a in "$@"; do echo "    <string>$a</string>"; done
    echo '  </array>'
    echo "  <key>EnvironmentVariables</key><dict><key>PGPASSFILE</key><string>$HOME/.pgpass</string></dict>"
    if [ -n "${SEGUNDOS:-}" ]; then echo "  <key>StartInterval</key><integer>$SEGUNDOS</integer>"
    else echo '  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>'; fi
    echo "  <key>StandardOutPath</key><string>$PASTA/logs/$nome.log</string>"
    echo "  <key>StandardErrorPath</key><string>$PASTA/logs/$nome.log</string>"
    echo '</dict></plist>'
  } > "$AGENTES/$PREFIXO.$nome.plist"
  launchctl bootout "gui/$(id -u)/$PREFIXO.$nome" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$AGENTES/$PREFIXO.$nome.plist"
}

echo "4/4 serviços do launchd"
# O PostgreSQL da reserva roda com PGPASSFILE: é dele a senha do principal que a réplica usa.
# CG_SEM_AGENTE_PG=1: o PostgreSQL já é gerido de outro jeito (Postgres.app, brew services) e está
# no ar nesta porta — então ele precisa ter o PGPASSFILE no ambiente dele (roteiro, B2).
[ -n "${CG_SEM_AGENTE_PG:-}" ] || plist postgres "$PG_BIN/postgres" -D "$PASTA/pg"
for i in $(seq 1 30); do "$PG_BIN/pg_isready" -q -h 127.0.0.1 -p "$PORTA_PG" && break; sleep 1; done
export PGPASSFILE="$HOME/.pgpass"
PSQL=("$PG_BIN/psql" -X -q -h 127.0.0.1 -p "$PORTA_PG" -U cg)
"${PSQL[@]}" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='cartorio'" | grep -q 1 \
  || "${PSQL[@]}" -d postgres -c "CREATE DATABASE cartorio"
"${PSQL[@]}" -d cartorio -v senha="$SENHA_LEITOR" <<'SQL'
SELECT 'CREATE ROLE cg_leitor LOGIN' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='cg_leitor') \gexec
ALTER ROLE cg_leitor WITH LOGIN PASSWORD :'senha';
SQL
chmod +x "$PASTA/sistema/installer/macos/"*.sh
plist servidor /bin/bash "$PASTA/sistema/installer/macos/iniciar_reserva.sh"
SEGUNDOS=300 plist sincronia /bin/bash "$PASTA/sistema/installer/macos/sincronizar.sh"

echo
echo "Instalado. Falta (roteiro, parte B):"
echo "  - pôr o IP do Windows em $PASTA/reserva.env"
echo "  - anotar a senha do cg_replica no ~/.pgpass: IP_DO_WINDOWS:5434:cartorio:cg_replica:<senha>"
echo "  - montar a réplica: $PASTA/venv/bin/python $PASTA/sistema/tools/reserva.py montar"
