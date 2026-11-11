# A suíte em todo PR e a fila de merge

Desde 10/11/2026 todo PR roda a **suíte completa** (cerca de 18 mil testes, com
PostgreSQL, LibreOffice e Chromium) antes de entrar no `main`. Os PRs prontos da
conta proprietária entram **sozinhos**, um por vez, **testados exatamente como vão
entrar**.

Por que existe: a CI do GitHub só rodava o anti-leak e o CodeQL. Em um só dia, a
suíte completa achou quatro defeitos que já estavam no `main` ou a um merge dele
(testes vencidos por um PR, a semente do layout quebrada por outro, uma tela que
esticava a página, uma função sem tela) e quinze falhas que só aparecem numa
máquina com LibreOffice, como o servidor.

## As peças

| Peça | Onde roda | O que faz |
|---|---|---|
| `.github/workflows/suite.yml` | executor `servidor-reserva` (o Mac da reserva) | baixa o PR, mescla com o `main` de agora e roda a suíte no contêiner; publica o status `suite` no commit do PR; comenta o que falhou |
| `ci/suite/rodar.sh` | idem, fora do contêiner | monta a imagem (só a partir do `main`) e roda o contêiner sem rede |
| `ci/suite/Dockerfile`, `dentro_do_conteiner.sh` | dentro do contêiner | Python 3.12, PostgreSQL 18 descartável, LibreOffice, Chromium; roda o pytest |
| `ci/suite/resumir.py` | executor, fora do contêiner | o comentário de falha: as falhas agrupadas pela causa (do `junit.xml`) e o primeiro erro, sem IA |
| `.github/workflows/fila.yml` + `ci/fila.py` | executores do GitHub (grátis em repositório público) | a fila: mescla o verde cujo teste ainda vale, atualiza o próximo e pede a suíte; um por vez |
| `ci/suite/instalar_executor.sh` | uma vez, com `sudo` | cria o usuário `ci-runner`, a máquina virtual e os serviços |

## Segurança

O executor é o **servidor reserva**: ele guarda a réplica da produção, as chaves da
reserva e o acesso ao servidor principal. Por isso:

- **O código do PR nunca roda no Mac.** Roda num contêiner Linux descartável,
  **sem rede** (`--network none`), sem privilégios, com o código em somente leitura,
  dentro de uma máquina virtual que só enxerga a área de trabalho do executor.
- **Os passos vêm do `main`.** A suíte usa `pull_request_target`: um PR não consegue
  trocar o que o executor faz. O código do PR é só dado entregue ao contêiner.
- **Só a conta proprietária, só o próprio repositório, só PR pronto.** PR de fork
  nunca chega ao executor.
- **O executor é o usuário `ci-runner`**, sem privilégios, sem acesso à pasta do
  proprietário (fechada em 700) nem às credenciais do GitHub dele.
- **Dependência e CI não mudam sozinhas.** PR que mexe em `requirements*.txt`,
  `ci/suite/` ou `.github/` fica vermelho até o proprietário revisar e pôr o rótulo
  **`ci-revisado`** — só então a imagem se monta com o que o PR traz (a montagem é o
  único momento com rede, e `pip install` executa código dos pacotes).
- **O comentário de falha é feito por código, sem IA.** Ele agrupa as falhas pela
  mensagem de erro (294 quedas de uma causa só aparecem como uma linha) e mostra o
  primeiro erro como o pytest o deu. Um resumo por modelo de linguagem foi testado e
  descartado em 10/11/2026: só reescrevia o relatório, com o risco de errar. O que vem
  do PR entra só dentro de bloco de código, e o `junit.xml` com DOCTYPE/ENTITY é recusado.
- **O status `suite` só vale vindo do GitHub Actions**: a regra do `main` o exige
  dessa origem.

Risco residual conhecido: o disco externo «Banco de Dados Cart» está com «ignorar
donos» ligado, e qualquer usuário do Mac o lê — inclusive o `ci-runner`, fora do
contêiner (onde só rodam os passos do `main`). Ligar os donos (`diskutil
enableOwnership`) exige conferir antes o acesso da reserva aos próprios arquivos.

## A regra do `main`

- verificações obrigatórias: `anti-leak` e `suite` (esta, só do GitHub Actions);
- o PR **não** precisa estar em dia com o `main` (`strict` desligado, 11/11/2026). Quem
  decide se o teste ainda vale é a fila: a suíte testa o PR mesclado com o `main` daquele
  instante e grava esse `main` no status `suite-main`; se depois o `main` mexeu em arquivo
  do PR ou em arquivo de base (`ARQUIVOS_DE_BASE` em `ci/fila.py`: requirements,
  `tests/conftest.py`, `banco_pg.py`, `bd_nativo.py`, `app.py`, `ci/`, `.github/`), a fila
  atualiza a branch e testa de novo. Com o `strict` ligado a fila também funciona, só que
  refaz a suíte de todo PR a cada merge;
- nem administrador passa por cima.

## O dia a dia

- **Abrir um PR pronto** (não rascunho) basta: a suíte roda, e a fila o mescla em
  squash quando ele estiver verde e o teste dele ainda valer.
- **Tirar um PR da fila:** rótulo `nao-mesclar`.
- **Conflito:** a fila põe o rótulo `conflito` e comenta; resolvido o conflito, tire o
  rótulo.
- **Suíte vermelha:** o PR recebe um comentário com o que falhou e fica parado até um
  push novo.
- **Mudança de dependência ou da CI:** revise e ponha `ci-revisado`.
- Cada PR na fila leva o tempo de uma suíte: cerca de 20 minutos no contêiner (medido em 10/11/2026: 18.617 testes em 19 min 10 s, o mesmo resultado da rodada direta no Mac).

## Instalar o executor (uma vez)

```bash
brew install colima docker
sudo bash ci/suite/instalar_executor.sh
```

## Remover o executor

```bash
sudo launchctl bootout system /Library/LaunchDaemons/br.cartoriogestao.ci-executor.plist
sudo launchctl bootout system /Library/LaunchDaemons/br.cartoriogestao.ci-colima.plist
sudo rm /Library/LaunchDaemons/br.cartoriogestao.ci-*.plist
```

Depois, em *Settings → Actions → Runners* do repositório, remova o `servidor-reserva`
e, se quiser, apague o usuário: `sudo sysadminctl -deleteUser ci-runner`.

## Histórico

- 10/11/2026: o executor `servidor-reserva` entrou em operação; o primeiro PR a passar pela suíte
  no contêiner e pela fila foi o de ensaio que acrescentou esta linha.
- 11/11/2026: pôr um rótulo num PR (o `nao-mesclar`, por exemplo) cancelava a suíte que já corria
  nele — a concorrência estava no workflow, e todo evento entrava no grupo. Passou para o job.
- 11/11/2026: a fila refazia a suíte de todo PR verde a cada merge (a regra exigia a branch em
  dia): um PR ficou verde três vezes sem entrar. A suíte passou a gravar o `main` testado
  (`suite-main`), e a fila só refaz quando o `main` mexeu no que o PR toca. Também deixou de
  pedir suíte por cima da que esperava o executor (a nova cancelava a antiga): as rodadas
  se chamam `suite #N`, e a fila espera por elas.
