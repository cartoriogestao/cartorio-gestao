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
| `.github/workflows/fila.yml` + `ci/fila.py` | executores do GitHub (grátis em repositório público) | a fila: mescla o verde cujo teste ainda vale e pede a suíte do próximo; um por vez |
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
  `tests/conftest.py`, `banco_pg.py`, `bd_nativo.py`, `app.py`, `ci/suite/`), a fila
  pede a suíte de novo, sem mexer na branch (a suíte junta o PR com o `main` da hora). Com o `strict` ligado a fila também funciona, só que
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

## A chave da suíte (suíte × IA local)

O servidor reserva também roda a IA local (Ollama), e as duas disputam a memória: a VM da
suíte segura o que já usou enquanto estiver ligada. A **chave da suíte** reparte o Mac por
horário:

- **Suíte**: a VM e o executor ligados, como sempre foi;
- **IA**: a suíte em andamento **termina** (nunca é derrubada), o executor sai do ar e a VM
  desliga — a memória volta toda para o Mac. As suítes pedidas nesse meio-tempo **esperam na
  fila do GitHub** e rodam quando a chave volta (o GitHub desiste de uma rodada parada há
  24 h; nenhuma janela da IA deve passar disso).

O **app da barra de menus** (Chave da Suíte) mostra a posição, a memória da VM e quantas
suítes esperam, e muda a chave: **Automático** (segue a agenda), **Suíte sempre**, **IA
sempre**, **IA agora por 1–8 h**, **Suíte agora por 1–8 h** e **Agenda da IA…** (as
janelas, por dia e hora). Padrão: IA de segunda a sexta, 8h–18h; suíte no resto.
Com a suíte em andamento, **Interromper a suíte agora…** cancela a rodada no GitHub e a põe
de volta na fila assim que o executor sai do ar; ela roda do começo quando a chave voltar.

**IA tem prioridade quando estiver em uso** (campo `prioridade_ia` do pedido): com um modelo
carregado no Ollama (`GET 127.0.0.1:11434/api/ps` com `models` não vazio), a posição é IA —
por cima da agenda e do «Suíte sempre»; só «Suíte agora, por…» (modo com prazo) fica valendo.
O Ollama descarrega o modelo após 30 min parado, e a chave volta sozinha.

Com a prioridade ligada, o **app interrompe sozinho** a suíte em andamento (cancela no GitHub e a
devolve à fila depois que o executor sai do ar), com uma carência: uma suíte que roda no executor
há **25 a 45 min** está para terminar e é poupada; antes de 25 min, ou depois de 45 (travada no
swap), é interrompida. O app consulta o GitHub no máximo uma vez por minuto e registra o que fez
em `~/Library/Logs/ChaveDaSuite.log`. Isso só acontece **com o app aberto** (ele tem o `gh` do
proprietário; o controlador root não tem credencial do GitHub, de propósito) — com o app
fechado, a chave espera a suíte terminar.

Enquanto a suíte em andamento termina, a VM roda em segundo plano (`taskpolicy -b` e `renice 10`): cede CPU e
disco, mas não memória — essa só volta quando a VM desliga. Motivo (medido em 27/11/2026): com
a VM ligada e o Qwen 8B carregado, o Mac de 36 GB foi para o swap e o Qwen caiu de 39 para
~1 token/s.

| Peça | Onde | O que faz |
|---|---|---|
| `ci/chave/controlador.py` | LaunchDaemon `br.cartoriogestao.ci-chave` (root) | a cada 5 s lê o pedido, decide a posição e liga/desliga os dois serviços (`launchctl enable/disable` + `bootstrap/bootout`: o desligado não volta nem depois de reiniciar o Mac); publica o estado |
| `/Users/Shared/CartorioGestao/chave-da-suite/pedido.json` | pasta do proprietário | o que o app pede: `modo` (`auto`/`suite`/`ia`), `ate` (prazo) e `agenda` |
| `/Library/Application Support/CartorioGestao/chave-da-suite/estado.json` | pasta do root | o que o controlador vê e fez; o app lê daqui |
| `ci/chave/ChaveDaSuite.swift` | `~/Applications/ChaveDaSuite.app`, abre no login | o app; sem privilégio nenhum, só grava o pedido e usa o `gh` do proprietário |

Segurança: o controlador roda como root e **não executa nada do pedido** — lê três campos,
confere cada um (modo de uma lista, horas `HH:MM`, dias 0–6) e ignora o resto; só aceita o
arquivo se for do dono da pasta, numa pasta que ninguém mais grava, sem seguir link. O
próprio controlador fica numa pasta do root, não na do repositório.

O teto da VM é **18 GB** (o contêiner, 16 GB). **Não o baixe**: em 27/11/2026 ele foi a 12/10 GB
e o PostgreSQL do contêiner morreu no meio de três suítes seguidas («the database system is not
yet accepting connections», «in recovery mode», milhares de erros), em PRs diferentes, todas
depois da troca. O «uns 9 GB» medido no Mac era só o que a VM tinha residente, não o pico do
contêiner. A memória para a IA vem da chave, que desliga a VM.

Instalar (uma vez):

```bash
sudo bash ci/chave/instalar_chave.sh
```

```bash
bash ci/chave/montar_app.sh
```

Ver a decisão sem mexer em nada: `/usr/bin/python3 ci/chave/controlador.py --simular`.
O registro das trocas fica em `/Library/Logs/CartorioGestao/chave-da-suite.log`.

Desfazer: `sudo launchctl bootout system/br.cartoriogestao.ci-chave`, apagar o plist dele, e
religar os dois serviços (`sudo launchctl enable system/br.cartoriogestao.ci-colima`, idem
`ci-executor`, e `bootstrap` de cada um). O app: apagar `~/Applications/ChaveDaSuite.app` e
`~/Library/LaunchAgents/br.com.cartoriogestao.chave-da-suite.plist`.

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
- 11/11/2026: um PR verde ficava travado para sempre quando uma rodada da suíte era cancelada.
  O job também se chamava `suite`: a verificação cancelada ficava no commit do PR, a rodada nova da
  fila (por `workflow_dispatch`) ia para o commit do main, e a regra do main via a cancelada. O job
  passou a se chamar «suíte no contêiner»; a exigência `suite` fica só com o status (PR #408).
- 11/11/2026: a fila refazia a suíte de todo PR verde a cada merge (a regra exigia a branch em
  dia): um PR ficou verde três vezes sem entrar. A suíte passou a gravar o `main` testado
  (`suite-main`), e a fila só refaz quando o `main` mexeu no que o PR toca. Também deixou de
  pedir suíte por cima da que esperava o executor (a nova cancelava a antiga): as rodadas
  se chamam `suite #N`, e a fila espera por elas.
- 12/11/2026: o PR que a fila atualizava ficava verde e travado. O commit de junção sai em nome
  do github-actions[bot], e o GitHub deixa o anti-leak de `pull_request` nele esperando aprovação
  manual; a regra do `main` olha essa rodada parada (#408, #424). Com o teste vencido, a fila
  agora só pede a suíte de novo: ela já junta o PR com o `main` atual, e a branch não muda.
- 27/11/2026: a chave da suíte. A VM (18 GB, ligada o dia todo) tirava a memória da IA local;
  agora ela desliga nas janelas da IA, com a suíte em andamento terminando antes. Um app na
  barra de menus muda a chave e a agenda. O teto chegou a cair para 12 GB (contêiner 10 GB) no
  mesmo dia e o PostgreSQL do contêiner morreu em três suítes seguidas: voltou a 18/16.
