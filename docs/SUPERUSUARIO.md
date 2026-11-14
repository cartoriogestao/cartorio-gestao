# O superusuário — o operador de IA que só o oficial aciona

Ordem do oficial, 12/11/2026: um operador com poder total no servidor
principal e no reserva, acionado só por ele, de onde estiver, para resolver na
hora informática, código, banco, prática notarial e registral e financeiro —
«muito prudente», leve na máquina, e deixando relatório do que mudou para a
revisão e para o PR. Decidido com ele:

- **é exceção total**: a conta dele é de robô **com perfil ADMIN**, a única
  (`database.ROBO_QUE_ADMINISTRA`);
- **os dados reais vão para a Anthropic** quando o pedido precisa deles —
  decisão do oficial, como controlador;
- **três portas, um superusuário só** (13/11/2026): o Telegram, a tela do
  sistema e o app do Claude — este pela assinatura dele, sem gastar a API;
- **conhecimento que se acumula**: «nada avulso»; ele sabe o que já foi feito
  de importante, por qualquer porta e nos dois servidores;
- **no lugar do agente antigo** (`/agente`, fora da tela desde 06/10/2026):
  «pode substituir, é um projeto abandonado»;
- **ele gerencia os outros robôs** (14/11/2026): «com um pedido simples, ele
  configura o acesso de toda a automação e deixa tudo funcionando — a de hoje
  e as futuras».

## Como funciona

O superusuário não é um programa da casa: é o **Claude Code** rodando numa
pasta do servidor, o **posto**, que carrega as instruções, a guarda e a
memória. Qualquer Claude Code aberto no posto é o superusuário — por isso as
três portas dão no mesmo lugar.

```
Telegram ─────────┐
tela do sistema ──┼─► ponte ──► Claude Code sem tela ───────────────┐
app do Claude ─────────────────► Claude Code aberto pelo app ───────┼─► O POSTO
                                                                    │   <dados>/operador/posto
                 a guarda antes de cada ferramenta ◄────────────────┤
                 o relatório do que mudou (código, banco, comandos) ◄┤
                 a memória e o diário, de todas as portas ◄─────────┘
                                     │
              repositório privado ◄──┘ (mascarado) ──► o outro servidor fica sabendo
                      │
          agente local: revisa, aplica o patch, abre o PR
```

| peça | o que é |
|---|---|
| `operador/posto.py` | Monta o posto (`CLAUDE.md`, `.claude/settings.json`, o atalho `op`) e traz os ganchos: o que entra na conversa sozinho, abrir e fechar a intervenção, anotar no diário. |
| `operador/INSTRUCOES.md` | O que o operador é e como age. Vira o `CLAUDE.md` do posto. |
| `operador/guarda.py` | Roda antes de cada ferramenta: guarda o original, anota o comando, cobra o «CONFIRMO», barra `psql` direto e segredo. |
| `operador/intervencao.py` | O registro do que mudou: `guardar`, `nota`, `consulta`, `sql`, `fechar`, `exportar`, `criar-conta`. |
| `operador/conhecimento.py` | A memória (`MEMORIA.md`) e o diário (uma linha por pedido), e a troca com o outro servidor. |
| `operador/ponte.py` | Recebe o Telegram e a bandeja da tela, roda o operador e devolve a resposta. Um pedido por vez. |
| `operador/bandeja.py` | Os arquivos por onde a tela do sistema fala com a ponte. |
| `operador_web.py` | A tela «Superusuário», dentro do sistema. |
| `operador/op.py` | O atalho das ferramentas do operador (`./op consulta`, `./op sql`, `./op lembrar`…). |
| `operador/robos.py` | Os outros robôs e a automação: o quadro de tudo, a conta de robô com a senha que ninguém vê, ligar e rodar as rotinas. |
| `operador/ouvir.py` | Transcreve o áudio do Telegram, pelo caminho dos áudios do WhatsApp. |
| `operador/ensaio.py` | Prova, no servidor, que a guarda e o relatório funcionam com o Claude Code instalado. |
| `<dados>/operador/` | Tudo o que é dele neste servidor: a configuração (`operador.cred`), o posto, o conhecimento, os anexos, as intervenções. Fora do sistema e fora do git. |

**Leve:** parada, a ponte é um processo Python esperando a rede e olhando uma
pasta. O operador só existe enquanto atende um pedido. O que carrega os
módulos da casa (fechar o relatório, transcrever) roda em processo que nasce e
morre. No Windows a tarefa roda com prioridade abaixo da do servidor.

**Só saída:** a ponte liga para `api.telegram.org` e o operador para a
Anthropic. Nenhuma porta do cartório se abre.

## As três portas

### O Telegram

Mande o pedido em texto ou **áudio**, com PDF ou foto (até 20 MB cada). Várias
fotos ou mensagens seguidas viram **um pedido só**. Enquanto ele trabalha, o
Telegram mostra «digitando» e, a cada dois minutos, o que está fazendo. Ele
pode devolver arquivo (PDF, planilha). Há um bot por servidor.

| comando | o que faz |
|---|---|
| `/novo` | esquece a conversa e começa outra (a memória e o diário ficam) |
| `/estado` | o que está rodando, a fila, como ele paga e os relatórios por exportar |
| `/parar` | interrompe o pedido em andamento |
| `/diario` | os últimos pedidos, de todas as portas |
| `/lembrar <fato>` | guarda um fato na memória dele |
| `/abrir <frase>` · `/trancar` | só se houver frase (`OPERADOR_FRASE`) |
| `CONFIRMO` | libera por 10 minutos o que não tem volta |

O áudio é transcrito pelo caminho que a casa já usa para o WhatsApp
(`docs/TRANSCRICAO_NO_SERVIDOR.md`): neste servidor, se o modelo estiver
instalado; senão pela OpenAI — e aí **o áudio sai do cartório**.
`OPERADOR_AUDIO=local` ou `nao` muda isso.

### A tela do sistema

**Superusuário**, no menu (Gestão → Agente e leituras), só para o oficial que
responde pela conta. A caixa do pedido aceita anexos e leva junto **a tela de
onde ele veio** — «estou nesta tela» é metade do pedido. A mesma página mostra
o que ele está fazendo agora, o **diário de todas as portas**, os relatórios e
a memória, e tem os botões Conversa nova, Parar e CONFIRMO.

A tela não roda nada: deixa o pedido na bandeja, e a ponte o colhe — é a mesma
fila do Telegram. Como não grava no banco, **vale também no servidor reserva**.

### O app do Claude — pela assinatura, sem gastar a API

Duas formas, e as duas usam o login da sua assinatura do Claude:

- **Remote Control** (`OPERADOR_APP=1`): o servidor aparece no app do Claude
  (celular e claude.ai/code) como «Cartório Principal» / «Cartório Reserva».
  Exige `claude auth login` feito uma vez na conta que roda o serviço.
- **No próprio Mac do reserva**: no app do Claude, abra uma sessão de código
  na pasta do posto (`~/Library/Application Support/CartorioGestao/operador/posto`).

Nos dois casos a sessão nasce com as instruções, a guarda e a memória, e cada
pedido abre e fecha a intervenção sozinho e vai para o diário (os ganchos do
posto). O `CONFIRMO` se escreve na própria conversa.

## Assinatura ou API

A parte 1 do `operador.cred` diz como a ponte (Telegram e tela) fala com a
Anthropic. **A assinatura ganha da API** quando as duas estão preenchidas, e a
chave sai do ambiente do operador — senão o Claude Code cobraria por ela sem
avisar. O `/estado` e a tela dizem qual está valendo.

| forma | no `operador.cred` |
|---|---|
| assinatura, por token | `CLAUDE_CODE_OAUTH_TOKEN=` (gerado por `claude setup-token`) |
| assinatura, pelo login da conta | `OPERADOR_ASSINATURA=1` |
| API, chave só do operador | `ANTHROPIC_API_KEY=` (com limite de gasto no console) |
| API, chave do agente da casa | `OPERADOR_CHAVE_DA_CASA=1` |

Pela API, a resposta traz o custo do pedido, e `OPERADOR_TETO_USD` limita o
gasto de um pedido. `OPERADOR_ESFORCO` é o esforço de raciocínio, e
`OPERADOR_MODELO_RESERVA` o modelo que assume quando o principal está cheio.

## O que ele sabe: a memória e o diário

Tudo em `<dados>/operador/conhecimento/`, um só para as três portas:

- **`MEMORIA.md`** — o que vale daqui para a frente (como a casa está montada,
  uma decisão sua, uma armadilha). Entra inteira no começo de cada conversa.
  Quem escreve: ele (`./op lembrar`), ou você (`/lembrar`, ou a tela).
- **o diário** — uma linha por pedido atendido: o pedido, a resposta, o
  relatório, o custo. Quem escreve é o programa, e não o modelo: nada fica de
  fora. Os últimos entram no começo de cada conversa; o resto ele procura
  (`./op procurar <termo>`).
- **os comandos de shell** de cada pedido, só neste servidor.

Com `OPERADOR_REPOSITORIO`, a memória e o diário vão **mascarados** para o
repositório privado, e o outro servidor os traz: o reserva sabe o que o
principal fez, e o contrário. A conversa parada há mais de 12 horas recomeça
sozinha — o que importa dela já está aqui.

## Ele gerencia os outros robôs

O pedido é simples — «arrume a automação», «ligue o robô do protesto» — e ele
sai com tudo funcionando, ou com a lista curta do que só você pode fazer. A
casa já tinha as peças (as rotinas e o despachante em `automacao.py`, o cofre
em `automacao_cofre.py`, o quadro em `oficial_robos.py`, as contas de robô com
responsável); `operador/robos.py` só as lê e chama, pelas mesmas funções das
telas.

| comando do operador | o que faz |
|---|---|
| `op robos quadro` | Tudo numa tela: o despachante, o cofre, cada rotina por robô (ligada? rodou? rodou bem? tem a credencial?), o quadro dos robôs, as contas — e **o que falta**, separado em o que ele resolve e o que só o oficial pode fazer. |
| `op robos conta <login> --cofre <item>` | Cria a conta de robô (ou troca a senha da que existe) e guarda a senha **sorteada** direto no cofre — ou num `.cred`, com `--arquivo`. |
| `op robos responsavel <login>` | Define quem responde pelo robô, sem mexer na senha. Sem nome dito, é o oficial. |
| `op robos ligar` / `desligar` / `rodar <código>` | Liga, desliga ou pede a rodada de uma rotina. |
| `op robos semear` | Cadastra as rotinas de fábrica que uma versão nova trouxe (nascem desligadas). É assim que as **futuras** entram. |

O que continua sendo só seu, e o quadro diz exatamente o quê:

- **abrir o cofre** — a senha-mestra é sua. Com o cofre trancado, ele não mexe
  em conta nenhuma (a senha nova não teria onde ficar);
- **digitar a senha de fora** (Central, banco, portal), em Automação → Cofre.
  Ele diz qual item e quais campos faltam. **O segredo nunca vai ao modelo**:
  ele grava e lista o cofre, e nunca o lê — há teste que varre o código dele;
- **«pode agir sozinho»** numa rotina: só com o seu «pode» para aquela rotina.

As regras da casa valem para ele como gerente: robô tem conta própria, de
robô, com responsável, e só USER ou AUDITOR (`docs/IDENTIDADE_DOS_ROBOS.md`);
conta de pessoa ele não toca; e liberar rota nova para um robô
(`rotas_do_robo.py`) é mudança de código, que segue o caminho do relatório e
do PR. No reserva ele só olha o quadro: as rotinas rodam no principal.

## O que a prudência garante por programa, e o que é só instrução

| | garantido por programa | só instrução |
|---|---|---|
| Só o oficial aciona | sim: o Telegram confere o usuário, a tela confere o responsável da conta, o app é a sua assinatura | |
| Original guardado antes de Edit/Write | sim (`guarda.py`), também para arquivo de fora do sistema | edição pelo shell (`sed`) — o relatório acusa o arquivo, sem o diff |
| Comando de shell registrado | sim, todos | |
| Cópia das tabelas antes de gravar | sim, pelo `sql`; `psql` direto com escrita é barrado | gravar por script Python, que a instrução manda fazer pela função da casa |
| «CONFIRMO» para o que não tem volta | sim, pelos padrões conhecidos; a confirmação só a porta grava | o que os padrões não pegam |
| Não ler segredo (`*.key`, `*.cred`, `.pgpass`) | sim, pelo nome do arquivo (guarda e regra do Claude Code) | |
| Não gravar no banco do reserva | sim: `cg_leitor` só lê, e o `sql` recusa | |
| Não ver a senha de robô nem ler o cofre | sim: a senha é sorteada e guardada pela ferramenta, que nunca chama `cofre.ler` | não pedir senha pela conversa |
| Não enviar nada para fora por iniciativa própria | | sim |
| Não obedecer a texto de documento | | sim |

**A guarda não é cofre.** Ela reconhece padrões; um operador com shell e ADMIN
pode o que o oficial pode. Por isso: só o oficial o aciona; a sua conta do
Telegram deve ter **verificação em duas etapas**; `OPERADOR_FRASE` põe uma
frase-senha no Telegram e na tela (cinco erros trancam as duas por 15
minutos); e tudo fica registrado. O Telegram guarda as mensagens e os
documentos nos servidores dele: é mais um lugar por onde o dado passa.

## O servidor reserva

O banco do reserva é réplica: o operador lê tudo e conserta código, serviço,
sincronia e disco, mas **não grava no banco**. Assumir continua manual, do
oficial, com `CONFIRMO` e com o serviço do Windows parado
(`docs/SERVIDOR_RESERVA_MACOS.md`).

**Depois de assumir, o reserva grava.** O `emergencia.sh` troca o
`reserva.env`; a ponte e o posto releem esse arquivo a cada pedido
(`OPERADOR_AMBIENTE`), e a situação no começo da conversa passa a dizer
«reserva que ASSUMIU».

Correção de código num servidor não chega ao outro sozinha; o operador avisa
quando o outro precisa da mesma. E no reserva ela dura menos: quando o
principal muda de versão, a sincronia troca a pasta do programa do Mac
(`reserva_versao`), e a correção direta feita lá se vai com a pasta antiga.

A ponte fica meses no ar, e o programa muda debaixo dela (o pacote no
principal, a troca de versão no reserva). Parada, ela percebe e sai sozinha —
o `launchd` e a tarefa do Windows a trazem de volta com o código novo.

## O relatório e o PR

Cada pedido que muda alguma coisa fecha uma intervenção em
`<dados>/operador/intervencoes/<data>-<nº>/`:

- `RELATORIO.md` — o pedido, o que ficou feito, as notas, os arquivos, o SQL,
  os comandos de shell e os arquivos de fora do sistema que mudaram;
- `codigo.patch` — o diff do código (aplica com `git apply`);
- `antes/` — os originais; `banco/` — o SQL, a saída e o `pg_dump` de antes;
- `fora_do_sistema.diff` — o que mudou em configuração e serviço. Só fica no
  servidor.

O pedido que só perguntou, consultou ou rodou comando não gera relatório: fica
no diário, com os comandos.

Com `OPERADOR_REPOSITORIO`, vão para `intervencoes/<servidor>-<id>/` no
repositório privado o relatório e o SQL **mascarados** (`ajuda_privacidade`) e
o patch; nunca o `pg_dump`. No desenvolvimento, o comando
`/revisar-intervencoes` do Claude Code lê as pendentes, aplica o patch num
ramo, roda os testes e abre o PR.

**A correção direta vale até o próximo pacote `.cgu`**, que a apaga se o PR
não tiver entrado. Antes de aplicar um pacote, confira `/estado` ou a tela:
relatório por exportar ou PR aberto é correção que o pacote vai desfazer.

## Instalar

O oficial faz, uma vez por servidor:

1. Instalar o Claude Code no servidor (https://code.claude.com/docs/en/setup),
   na conta que vai rodar a ponte.
2. Rodar o instalador, que cria o `operador.cred` e monta o posto:
   - reserva (macOS): `bash installer/macos/instalar_operador.sh`
   - principal (Windows, como Administrador):
     `powershell -ExecutionPolicy Bypass -File installer\instalar_operador.ps1`
3. Preencher a parte 1 do `operador.cred` (assinatura ou API) e rodar o
   instalador de novo: a ponte sobe, e a tela do sistema já funciona.
4. **Rodar o ensaio** — não gasta a API e não toca no banco:
   `python operador/ensaio.py`. Ele diz, conferência por conferência, se a
   guarda, o relatório e o diário funcionam com o Claude Code daquele servidor.
5. No principal, criar a conta:
   `python operador\intervencao.py criar-conta --responsavel <seu login>`.
   Quem responde pela conta é quem vê a tela.
6. Telegram (opcional): no `@BotFather`, `/newbot`, um bot para cada servidor;
   pôr o token em `TELEGRAM_TOKEN`; escrever para o bot, que responde o seu
   número; pôr o número em `OPERADOR_TELEGRAM_USUARIO`. **Até aí o bot não
   atende ninguém.**
7. App do Claude (opcional): `claude auth login` na conta do serviço,
   `OPERADOR_APP=1`, e o instalador de novo.

Para desligar: macOS, `launchctl bootout gui/$(id -u)/br.com.cartoriogestao.operador`
(e `.operador-app`); Windows, `Disable-ScheduledTask CartorioGestaoOperador`
(e `CartorioGestaoOperadorApp`). Para cortar o acesso de vez, revogue o token
no `@BotFather`, a chave no console e a sessão em claude.ai.

## O que foi provado, e o que ainda não

**Provado em 13/11/2026**, no Mac do reserva, com o Claude Code 2.1.321 de
verdade e uma «Anthropic de mentira» local (`operador/ensaio.py`): o operador
roda sem tela pela ponte; ler `operador.cred` é barrado; a edição guarda o
original e o relatório traz o patch; `rm -rf` espera o CONFIRMO; `psql` com
escrita é barrado; os comandos ficam no relatório e o pedido no diário; pela
porta do app, a memória e as instruções entram sozinhas e o pedido fecha no
diário.

**Ainda não provado:**

- um pedido com o modelo de verdade e com o Telegram de verdade (falta a
  credencial, que é do oficial);
- nada no Windows — nem a ponte como tarefa agendada, nem a guarda com o
  PowerShell. O ensaio foi feito para isso: rode-o no principal;
- o Remote Control como serviço (no ensaio ele subiu sem terminal e parou no
  login, que é o esperado sem a assinatura);
- a transcrição de áudio pela ponte;
- a gestão dos robôs contra o cofre e o despachante de verdade (os testes
  usam um cofre de mentira e o banco de teste).

## O que ficou para o oficial decidir

- **O catálogo de IA da casa** (`ia_catalogo.py`, de onde sai o relatório à
  COGEX) ainda não tem a entrada do superusuário. O texto dela é
  enquadramento na norma — dado sem máscara, por decisão do controlador — e
  por isso não foi escrito aqui. Precisa existir antes de ele entrar em uso.
- **O agente antigo** continua como estava desde 06/10: fora da tela, com as
  rotas, as tabelas e a chave no lugar. Tirar o código dele é um PR próprio.
