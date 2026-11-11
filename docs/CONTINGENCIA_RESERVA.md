# Contingência da reserva

O botão para o dia em que o servidor Windows cai, e a volta para quando ele
voltar. Nada disto roda sozinho: o oficial aprova e só então liga.

## Antes de ligar (uma vez, no Windows, com superusuário)

1. Ler `installer/sql/travas_da_producao.sql`.
2. Rodar esse arquivo no PostgreSQL da casa. Ele liga o log de DDL e de
   conexões, cria a marca de somente leitura, impede apagar o schema
   `producao` e tira o esvaziamento de tabela da publicação.
3. No Mac, o `reserva.env` continua com `CG_MODO_RESERVA=1`. Sem isso, o
   `montar` recusa a porta 5434 — no Windows essa porta é a produção; no Mac,
   com o modo reserva, é a cópia.

## Quando o principal cair

No Mac:

```bash
installer/macos/emergencia.sh ASSUMIR
```

O que acontece, nesta ordem:

1. Se o Windows ainda responde, o aplicativo e as automações de lá ficam
   somente leitura. A marca fica em `public`, fora da réplica.
2. A assinatura `cg_reserva` é desligada (`DISABLE SUBSCRIPTION`).
3. Um `pg_dump` da reserva é gravado em `contingencia/reserva.dump`, dentro
   da pasta de dados do Mac.
4. As sequências sobem ao maior id, as pastas apontam para as cópias do Mac,
   o `reserva.env` passa a modo principal e o serviço reinicia.

`assumir.sh ASSUMIR` faz o mesmo: ele chama o botão.

Não ligue o Windows para gravar enquanto o Mac estiver lançando.

## A volta

Com os dois bancos no ar e o Windows ainda somente leitura, no Mac, com as
variáveis do `reserva.env`:

```bash
python tools/reserva.py voltar --confirmo VOLTAR --remontar
```

O comando copia as linhas novas (id maior do que o do Windows), confere
contagem, maior id e hash, acerta as sequências no Windows e só então solta
a somente leitura. `--remontar` recria a assinatura `cg_reserva` sem copiar
de novo o que já foi conferido. É o caminho de quando as tabelas do principal
foram recriadas e a assinatura antiga não serve mais.

Se a conferência não fecha, a assinatura não religa e o Windows continua
somente leitura. O comando diz quais tabelas divergiram.

Se a publicação não existir mais no Windows, rode antes, no Windows, o SQL
que `reserva.py sql-do-principal` imprime.

## Ensaio mensal

Fora do horário de balcão, numa máquina que **não** tenha
`CG_PG_SCHEMA=producao` nem a conexão local na porta 5434 da produção:

```bash
python tools/ensaio_contingencia.py
```

Não abre banco. Prova a ordem do botão e a recusa do `montar` contra a
produção. Se o ambiente apontar para a casa, sai sem fazer nada.

## O que a suíte não faz mais

Pytest com `CG_PG_SCHEMA=producao` recusa a partida, antes de conectar.
Apagar ou recriar schema que não seja `cg_…` também. `montar` e a migração
com `--recriar` recusam o schema `producao` e a porta 5434 do principal.
A reserva no Mac, com `CG_MODO_RESERVA=1` e destino no loopback, continua
podendo ser montada.
