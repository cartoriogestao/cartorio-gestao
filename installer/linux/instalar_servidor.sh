#!/bin/bash
# O SERVIDOR DO CARTÓRIO GESTÃO NO LINUX (Debian 12+ / Ubuntu 24.04+, com systemd).
# Rode da pasta do código, como root:   sudo bash installer/linux/instalar_servidor.sh
#
# O que faz (pode rodar de novo: é também como se ATUALIZA — o que já existe fica como está):
#   1. instala pelo apt o Python, o PostgreSQL, o LibreOffice e as fontes (os mesmos pacotes da
#      imagem da CI, `ci/suite/Dockerfile`, onde a suíte inteira roda em Debian 12);
#   2. cria a conta de sistema `cartorio` (sem login), dona da pasta de dados;
#   3. copia o código para /opt/cartorio-gestao/sistema e monta o venv com o requirements.txt;
#   4. cria no PostgreSQL local o papel `cg` (senha sorteada, SCRAM, sem superusuário) e o banco
#      `cartorio`; a senha vai só para o .pgpass da conta `cartorio` (chmod 600) — nunca para a
#      tela, para o log ou para o CG_PG_DSN;
#   5. grava /etc/cartorio-gestao/servidor.env e o serviço `cartorio-gestao` do systemd, e o sobe.
# O banco escuta só em localhost (o padrão do Debian). Firewall: o script só DIZ o que liberar.
# Detalhes, o que ainda é só do Windows e como atualizar: docs/SERVIDOR_LINUX.md.
set -euo pipefail

CONTA="${CG_LINUX_CONTA:-cartorio}"
RAIZ="${CG_LINUX_RAIZ:-/opt/cartorio-gestao}"
DADOS="${CG_LINUX_DADOS:-/var/lib/cartorio-gestao}"
ETC=/etc/cartorio-gestao
ENV="$ETC/servidor.env"
UNIDADE=/etc/systemd/system/cartorio-gestao.service
ORIGEM="$(cd "$(dirname "$0")/../.." && pwd)"

falha() { echo "PAROU: $*" >&2; exit 1; }
cd /   # o runuser do postgres não consegue entrar na pasta de quem chamou
passo() { echo; echo "== $*"; }

[ "$(uname -s)" = "Linux" ] || falha "este instalador é do Linux (no macOS: installer/macos; no Windows: INSTALAR_SERVIDOR.cmd)"
[ "$(id -u)" -eq 0 ] || falha "rode como root: sudo bash $0"
command -v systemctl >/dev/null || falha "falta o systemd"
command -v apt-get >/dev/null || falha "este instalador usa o apt (Debian/Ubuntu); em outra distribuição, siga docs/SERVIDOR_LINUX.md à mão"
[ -f "$ORIGEM/app.py" ] && [ -f "$ORIGEM/requirements.txt" ] || falha "rode de dentro da pasta do código (não achei app.py em $ORIGEM)"

passo "1. pacotes do sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q --no-install-recommends \
  python3 python3-venv python3-dev build-essential swig libpcsclite-dev \
  postgresql postgresql-contrib \
  libreoffice-writer-nogui libreoffice-calc-nogui \
  fonts-liberation fonts-liberation2 fonts-dejavu-core fonts-crosextra-carlito fonts-crosextra-caladea \
  rsync curl ca-certificates openssl fontconfig
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || falha "o sistema pede Python 3.11 ou mais novo; este Linux tem $(python3 -V 2>&1). Use Debian 12+ ou Ubuntu 24.04+"
PG_BIN="$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)"
[ -x "$PG_BIN/pg_dump" ] || falha "não achei os binários do PostgreSQL em /usr/lib/postgresql/*/bin"
systemctl enable --now postgresql >/dev/null
PG_PORTA="$(runuser -u postgres -- psql -XAtc 'show port')"

passo "2. a conta $CONTA e as pastas"
id "$CONTA" >/dev/null 2>&1 || useradd --system --home-dir "$DADOS" --shell /usr/sbin/nologin "$CONTA"
install -d -m 750 -o "$CONTA" -g "$CONTA" "$DADOS"
install -d -m 755 "$RAIZ"
install -d -m 750 -o root -g "$CONTA" "$ETC"

passo "3. o código e o venv"
# A cópia nova substitui a anterior; o que é da casa mora em $DADOS, e não aqui.
rsync -a --delete --exclude '.git' --exclude '__pycache__' --exclude '.pytest_cache' \
  "$ORIGEM/" "$RAIZ/sistema/"
[ -x "$RAIZ/venv/bin/python" ] || python3 -m venv "$RAIZ/venv"
"$RAIZ/venv/bin/python" -m pip install -q --upgrade pip
"$RAIZ/venv/bin/python" -m pip install -q -r "$RAIZ/sistema/requirements.txt"
"$RAIZ/venv/bin/python" -c "import flask, waitress, psycopg" || falha "o venv ficou sem Flask/waitress/psycopg"

passo "4. o banco (PostgreSQL $(basename "$(dirname "$PG_BIN")"), porta $PG_PORTA, só localhost)"
PGPASS="$DADOS/.pgpass"
if [ ! -s "$PGPASS" ]; then
  SENHA="$(openssl rand -hex 24)"
  # A senha entra pela entrada padrão do psql, e não pela linha de comando (que `ps` mostra).
  if runuser -u postgres -- psql -XAtc "select 1 from pg_roles where rolname='cg'" | grep -q 1; then
    COMANDO="ALTER ROLE cg LOGIN NOSUPERUSER PASSWORD '$SENHA'"
  else
    COMANDO="CREATE ROLE cg LOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB PASSWORD '$SENHA'"
  fi
  printf "SET password_encryption = 'scram-sha-256';\n%s;\n" "$COMANDO" \
    | runuser -u postgres -- psql -Xq -v ON_ERROR_STOP=1 >/dev/null
  unset COMANDO
  UMASK_ANTES="$(umask)"; umask 077
  printf '127.0.0.1:%s:cartorio:cg:%s\n' "$PG_PORTA" "$SENHA" > "$PGPASS"
  unset SENHA; umask "$UMASK_ANTES"
  chown "$CONTA:$CONTA" "$PGPASS"; chmod 600 "$PGPASS"
  echo "senha do papel cg sorteada e guardada em $PGPASS (só a conta $CONTA lê)"
else
  echo "o $PGPASS já existe: a senha fica como está"
fi
runuser -u postgres -- psql -XAtc "select 1 from pg_database where datname='cartorio'" | grep -q 1 \
  || runuser -u postgres -- createdb -O cg -E UTF8 -T template0 cartorio
# pg_trgm e unaccent são extensões confiáveis: o dono do banco as cria ao subir o sistema.

passo "5. a configuração e o serviço"
if [ ! -f "$ENV" ]; then
  sed -e "s#@DADOS@#$DADOS#g" -e "s#@PORTA@#$PG_PORTA#g" -e "s#@PG_BIN@#$PG_BIN#g" \
    "$RAIZ/sistema/installer/linux/servidor.env.exemplo" > "$ENV"
  echo "criei $ENV"
else
  echo "o $ENV já existe: fica como está"
fi
chown root:"$CONTA" "$ENV"; chmod 640 "$ENV"
sed -e "s#@CONTA@#$CONTA#g" -e "s#@RAIZ@#$RAIZ#g" -e "s#@DADOS@#$DADOS#g" -e "s#@ENV@#$ENV#g" \
  "$RAIZ/sistema/installer/linux/cartorio-gestao.service" > "$UNIDADE"
systemctl daemon-reload
systemctl enable cartorio-gestao >/dev/null
systemctl restart cartorio-gestao

echo -n "esperando o sistema responder"
for _ in $(seq 1 60); do
  if curl -fsS -o /dev/null "http://127.0.0.1:8765/"; then echo; break; fi
  echo -n "."; sleep 2
done
curl -fsS -o /dev/null "http://127.0.0.1:8765/" \
  || falha "o serviço não respondeu em 2 minutos: veja  journalctl -u cartorio-gestao -n 80"

echo
echo "PRONTO. Abra http://$(hostname -I 2>/dev/null | awk '{print $1}'):8765 num navegador da rede e crie o administrador."
echo "Depois: Configurações → Serventia (os dados da casa). Log: journalctl -u cartorio-gestao -f"
if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
  echo
  echo "O ufw está ligado. Para os balcões alcançarem o servidor, libere só a rede local, por exemplo:"
  echo "  ufw allow from 192.168.0.0/16 to any port 8765 proto tcp"
  echo "  ufw allow from 192.168.0.0/16 to any port 8766 proto udp"
fi
