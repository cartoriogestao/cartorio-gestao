# O superusuário — o operador de IA que só o oficial aciona

Ordem do oficial, 12/11/2026: um operador com poder total no servidor
principal e no reserva, acionado só por ele, de onde estiver, para resolver na
hora informática, código, banco, prática notarial e registral e financeiro —
«muito prudente», leve na máquina, e deixando relatório do que mudou para a
revisão e para o PR. Decidido com ele no mesmo dia:

- **é exceção total**: a conta dele é de robô **com perfil ADMIN**, a única
  (`database.ROBO_QUE_ADMINISTRA`);
- **os dados reais vão para a API** da Anthropic quando o pedido precisa
  deles — decisão do oficial, como controlador;
- **o pedido chega pelo Telegram**, sem ninguém entrar no servidor.

## Como funciona

```
oficial (Telegram) ──► bot do servidor ──► ponte.py ──► Claude Code sem tela (API)
                                              │               │
                                              │          guarda.py antes de cada ferramenta
                                              ▼               ▼
                                     resposta no Telegram   intervencao.py: original guardado,
                                                            cópia do banco, RELATORIO.md, patch
                                                                      │
                                              repositório privado ◄───┘ (mascarado)
                                                      │
                                     agente local: revisa, aplica o patch, abre o PR
```

| peça | o que é |
|---|---|
| `operador/ponte.py` | Espera o Telegram (consulta longa, só saída), confere que é o oficial, baixa os anexos, roda o operador e devolve a resposta. Um pedido por vez. |
| `operador/INSTRUCOES.md` | O que o operador é e como age: a prudência, o banco, o reserva, o relatório. |
| `operador/guarda.py` | Roda antes de cada ferramenta: guarda o original, cobra o «CONFIRMO» do que não tem volta, não deixa ler segredo. |
| `operador/intervencao.py` | O registro: `abrir`, `guardar`, `nota`, `sql`, `fechar`, `exportar`, `criar-conta`. |
| `<dados>/operador/` | A configuração (`operador.cred`), os anexos (`entrada/`), as intervenções e o registro da ponte. Fora do sistema e fora do git. |

**Leve:** parada, a ponte é um processo Python esperando uma resposta de rede.
O operador só existe enquanto atende um pedido. No Windows a tarefa roda com
prioridade abaixo da do servidor.

**Só saída:** a ponte liga para `api.telegram.org` e o operador para a API da
Anthropic. Nenhuma porta do cartório se abre.

## No Telegram

Mande o pedido em texto, com PDF ou foto (até 20 MB cada). Há um bot por
servidor: fale com o do **principal** para o que é do dia a dia, e com o do
**reserva** para o que é dele (ou quando o principal estiver fora).

| comando | o que faz |
|---|---|
| `/novo` | esquece a conversa e começa outra |
| `/estado` | o que está rodando, a fila e os relatórios por exportar |
| `/parar` | interrompe o pedido em andamento |
| `CONFIRMO` | libera por 10 minutos o que não tem volta |

O que **não tem volta** (`DROP`, `TRUNCATE`, `DELETE`/`UPDATE` sem `WHERE`,
sequência, restauração de banco, apagar pasta, `assumir.sh`, desligar) a guarda
barra até o oficial responder `CONFIRMO`. O operador explica antes o que vai
fazer e o que se perde.

## O que a prudência garante por programa, e o que é só instrução

| | garantido por programa | só instrução |
|---|---|---|
| Só o oficial aciona | sim (`ponte.py`) | |
| Original guardado antes de Edit/Write | sim (`guarda.py`) | edição pelo shell (`sed`) — o relatório acusa o arquivo, sem o diff |
| Cópia das tabelas antes de gravar | sim, pelo `intervencao.py sql` | gravar por `psql` direto, que a instrução proíbe |
| «CONFIRMO» para o que não tem volta | sim, pelos padrões conhecidos | o que os padrões não pegam |
| Não ler segredo (`*.key`, `*.cred`, `.pgpass`) | sim, pelo nome do arquivo | |
| Não gravar no banco do reserva | sim: `cg_leitor` só lê, e o `sql` recusa | |
| Não enviar nada para fora por iniciativa própria | | sim |

**A guarda não é cofre.** Ela reconhece padrões; um operador com shell e
ADMIN pode o que o oficial pode. É por isso que o canal só atende o oficial, a
chave da API é só deste uso e tem limite de gasto, e tudo fica no relatório.

## O servidor reserva

O banco do reserva é réplica: o operador lê tudo e conserta código, serviço,
sincronia e disco, mas **não grava no banco**. Assumir continua manual, do
oficial, com `CONFIRMO` e com o serviço do Windows parado
(`docs/SERVIDOR_RESERVA_MACOS.md`). Correção de código num servidor não chega
ao outro sozinha; o operador avisa quando o outro precisa da mesma.

## O relatório e o PR

Cada pedido que muda alguma coisa fecha uma intervenção em
`<dados>/operador/intervencoes/<data>-<nº>/`:

- `RELATORIO.md` — o pedido, o que ficou feito, as notas, os arquivos, o SQL;
- `codigo.patch` — o diff do código (aplica com `git apply`);
- `antes/` — os originais; `banco/` — o SQL, a saída e o `pg_dump` de antes.

Com `OPERADOR_REPOSITORIO` configurado, a ponte exporta para
`intervencoes/<servidor>-<id>/` no repositório privado: relatório e SQL
**mascarados** (`ajuda_privacidade`), o patch, e nunca o `pg_dump`. No
desenvolvimento, o comando `/revisar-intervencoes` do Claude Code
(`.claude/commands/revisar-intervencoes.md`) lê as pendentes, aplica o patch
num ramo, roda os testes e abre o PR.

**A correção direta vale até o próximo pacote `.cgu`**, que a apaga se o PR
não tiver entrado. Antes de aplicar um pacote, confira `/estado`: relatório
por exportar ou PR aberto é correção que o pacote vai desfazer.

## Instalar

O oficial faz, uma vez por servidor:

1. No Telegram, no `@BotFather`: `/newbot`, um bot para cada servidor (por
   exemplo «Cartório Principal» e «Cartório Reserva»). Guarde os dois tokens.
2. Em console.anthropic.com: uma chave de API só para o operador, com limite
   de gasto mensal.
3. Instalar o Claude Code no servidor (https://code.claude.com/docs/en/setup),
   na conta que vai rodar a ponte.
4. Rodar o instalador, que cria o `operador.cred`; preencher
   `TELEGRAM_TOKEN` e `ANTHROPIC_API_KEY`; rodar de novo:
   - reserva (macOS): `bash installer/macos/instalar_operador.sh`
   - principal (Windows, como Administrador):
     `powershell -ExecutionPolicy Bypass -File installer\instalar_operador.ps1`
5. Escrever qualquer coisa para o bot: ele responde o seu número de usuário.
   Pôr o número em `OPERADOR_TELEGRAM_USUARIO` e rodar o instalador de novo.
   **Até aí o bot não atende ninguém.**
6. No principal, criar a conta do operador:
   `python operador\intervencao.py criar-conta --responsavel <seu login>`

Para desligar: macOS, `launchctl bootout gui/$(id -u)/br.com.cartoriogestao.operador`;
Windows, `Disable-ScheduledTask CartorioGestaoOperador`. Para cortar o acesso
de vez, revogue o token no `@BotFather` e a chave no console.

## O que ainda não foi provado

- A execução do Claude Code por tarefa agendada no Windows, sem ninguém
  logado, não está documentada por ele: o instalador roda a tarefa na conta de
  quem instala (com senha) em vez de SYSTEM, e isso precisa ser ensaiado no
  servidor principal.
- Sem o Git for Windows, o operador usa PowerShell no lugar do Bash; a guarda
  cobre os dois, mas os padrões foram escritos pensando primeiro no Bash.
