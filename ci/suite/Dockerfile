# A IMAGEM DA SUÍTE — o lugar onde o código de um PR roda (10/11/2026).
#
# O executor da CI é o servidor reserva (macOS), que guarda a réplica da produção,
# as chaves da reserva e o acesso ao servidor principal. O código de um PR nunca
# roda nele: roda AQUI, num contêiner Linux descartável, SEM REDE (`--network
# none`), sem nenhuma pasta do Mac além da cópia do código e da pasta de saída.
#
# A imagem só se monta a partir do `main` (este arquivo e os `requirements*.txt`
# de lá): a montagem é o único momento com rede, e `pip install` executa código
# dos pacotes. PR que muda dependência não entra pela fila automática — ver
# `ci/suite/rodar.sh`.
#
# Tudo o que a suíte precisa e a CI do GitHub não tinha: PostgreSQL 18, LibreOffice
# e Chromium (Playwright). O fuso é o da serventia.
FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    TZ=America/Fortaleza \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg tzdata git \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      postgresql-18 \
      libreoffice-writer-nogui libreoffice-calc-nogui \
      fonts-liberation fonts-liberation2 fonts-dejavu-core fonts-crosextra-carlito fonts-crosextra-caladea \
      swig build-essential libpcsclite-dev rsync unzip fontconfig \
 && rm -rf /var/lib/apt/lists/*

# A LETRA DOS BALCÕES. O CSS pede «Segoe UI» (Windows); sem ela, o Chromium do Linux
# caía numa fonte mais alta e TODA tela sobrava 6 px no ensaio do layout. A Selawik é a
# fonte livre (OFL) da Microsoft com as medidas da Segoe UI — conferida pelo SHA-256.
RUN curl -fsSL -o /tmp/selawik.zip https://github.com/microsoft/Selawik/releases/download/1.01/Selawik_Release.zip \
 && echo "3f62c51e05e3b5a1e6241cf92a371f0be2ea1183aa87b30718bbd40832a8d423  /tmp/selawik.zip" | sha256sum -c - \
 && mkdir -p /usr/share/fonts/truetype/selawik \
 && unzip -j -o /tmp/selawik.zip '*.ttf' -d /usr/share/fonts/truetype/selawik \
 && rm /tmp/selawik.zip
COPY fontes-segoe.conf /etc/fonts/conf.d/40-segoe-selawik.conf
RUN fc-cache -f >/dev/null

COPY requirements.txt requirements-test.txt /tmp/req/
RUN pip install -r /tmp/req/requirements.txt -r /tmp/req/requirements-test.txt \
 && python -m playwright install --with-deps chromium \
 && rm -rf /tmp/req /var/lib/apt/lists/*

# Quem roda a suíte não é root.
RUN useradd --create-home --uid 1000 --shell /bin/bash suite
COPY dentro_do_conteiner.sh /usr/local/bin/dentro_do_conteiner.sh
RUN chmod 0755 /usr/local/bin/dentro_do_conteiner.sh
ENV PATH="/usr/lib/postgresql/18/bin:${PATH}"
USER suite
WORKDIR /home/suite
ENTRYPOINT ["/usr/local/bin/dentro_do_conteiner.sh"]
