#!/bin/bash
# Roda a suíte de um PR no contêiner sem rede. Executado pelo executor da CI (o
# usuário `ci-runner` do servidor reserva), SEMPRE na versão do `main`.
#
#   ci/suite/rodar.sh <pasta do main> <pasta do código do PR> <pasta de saída>
#
# O código do PR é só DADO aqui: vai para o contêiner em somente leitura e é lá,
# sem rede e sem nenhuma pasta do Mac, que ele executa. Este roteiro, o
# Dockerfile e o que roda dentro do contêiner vêm do `main`.
#
# Saída: 0 suíte verde; 1 suíte vermelha; 3 o PR muda dependência ou a própria
# CI (a imagem não se monta a partir de PR: exige revisão humana); outro, falha
# da infraestrutura.
set -euo pipefail
MAIN="$(cd "$1" && pwd)"
PR="$(cd "$2" && pwd)"
SAIDA="$3"
mkdir -p "$SAIDA"
SAIDA="$(cd "$SAIDA" && pwd)"
CONTEXTO_DOCKER="${CG_DOCKER_CONTEXTO:-colima-ci}"
PROCESSOS="${CG_SUITE_PROCESSOS:-12}"
docker_() { docker --context "$CONTEXTO_DOCKER" "$@"; }

# 1. O PR muda dependência ou a própria CI? Então ele não roda aqui sozinho.
#    Depois que o proprietário revisa e põe o rótulo `ci-revisado`, a imagem se
#    monta com as dependências DO PR (o workflow passa CG_SUITE_REVISADO=true).
SENSIVEIS="requirements.txt requirements-test.txt requirements-build.txt ci/suite .github"
ORIGEM_DA_IMAGEM="$MAIN"
for item in $SENSIVEIS; do
  if ! diff -rq "$MAIN/$item" "$PR/$item" >/dev/null 2>&1; then
    if [ -e "$MAIN/$item" ] || [ -e "$PR/$item" ]; then
      if [ "${CG_SUITE_REVISADO:-false}" = "true" ]; then
        echo "O PR muda «$item» e tem o rótulo ci-revisado: a imagem se monta com o que o PR traz."
        ORIGEM_DA_IMAGEM="$PR"
      else
        echo "O PR muda «$item»: a imagem da suíte só se monta a partir do main, e mudança"
        echo "de dependência ou da CI exige revisão humana (rótulo «ci-revisado») antes do merge."
        echo "codigo=3 o PR muda $item: falta o rotulo ci-revisado" >"$SAIDA/situacao.txt"
        exit 3
      fi
    fi
  fi
done

# 2. A imagem, pelo conteúdo: o mesmo conteúdo, a mesma imagem.
CONTEXTO="$(mktemp -d)"
trap 'rm -rf "$CONTEXTO"' EXIT
cp "$ORIGEM_DA_IMAGEM/ci/suite/Dockerfile" "$ORIGEM_DA_IMAGEM/ci/suite/dentro_do_conteiner.sh" \
   "$ORIGEM_DA_IMAGEM/ci/suite/fontes-segoe.conf" \
   "$ORIGEM_DA_IMAGEM/requirements.txt" "$ORIGEM_DA_IMAGEM/requirements-test.txt" "$CONTEXTO/"
ETIQUETA="cartorio-suite:$(cat "$CONTEXTO"/* | shasum -a 256 | cut -c1-16)"
if ! docker_ image inspect "$ETIQUETA" >/dev/null 2>&1; then
  echo "Montando a imagem $ETIQUETA (única etapa com rede)…"
  docker_ build --pull -t "$ETIQUETA" "$CONTEXTO"
fi

# 3. A suíte, sem rede, sem privilégio, com o código em somente leitura.
set +e
docker_ run --rm --network none --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 8192 --shm-size 2g --memory "${CG_SUITE_MEMORIA:-16g}" \
  -e CG_SUITE_PROCESSOS="$PROCESSOS" \
  -v "$PR:/codigo:ro" -v "$SAIDA:/saida" "$ETIQUETA"
rc=$?
set -e
[ "$rc" -le 1 ] || echo "A suíte não chegou ao fim (código $rc): falha da infraestrutura, e não do PR."
exit "$rc"
