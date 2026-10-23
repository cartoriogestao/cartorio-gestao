# Migrar para PostgreSQL ou SQL Server — o mapa, o custo e o gatilho

Em **25/08/2026** o oficial perguntou se fazia sentido trocar o SQLite por
PostgreSQL ou SQL Server. A resposta saiu de medição, e está aqui inteira —
com o inventário do que teria de mudar, para que uma decisão futura comece de
fatos e não de um levantamento novo.

**A resposta de hoje é não.** A decisão tomada foi: *não pagar a migração
agora, e parar de aumentar a dívida.*

---

## O que se mediu, em 25/08/2026

### A casa

| | |
|---|---|
| Banco vivo | **111 MB**, 67 tabelas |
| Usuários cadastrados | **6** |
| Lançamentos de caixa | 18.396 |
| Atos do RI | 1.245 · Notas 259 |
| `database is locked` nos logs, em um ano | **nenhum** |

### O código

| | |
|---|---|
| Módulos | **73**, 40.234 linhas |
| Testes | 50 arquivos, 17.160 linhas |
| Comandos SQL escritos à mão | **686** em 47 arquivos |
| `SELECT` 580 · `UPDATE` 154 · `INSERT` 142 · `DELETE` 20 | |
| `CREATE TABLE` 99 · `CREATE INDEX` 121 | |
| `import sqlite3` | **78 arquivos** |

### O que é do SQLite, e muda de forma

| Construção | Quantos | Vira o quê |
|---|---|---|
| `sqlite3.Row` | 165 | cursor de dicionário do driver |
| `AUTOINCREMENT` | 81 | `SERIAL` / `IDENTITY` |
| `lastrowid` | 71 | `RETURNING id` (PG) · `OUTPUT` (SQL Server) |
| `INSERT OR IGNORE` / `OR REPLACE` | 33 | `ON CONFLICT DO NOTHING` · `MERGE` |
| `strftime` / `julianday` | 35 | `to_char` e aritmética de data |
| `PRAGMA` | 23 | **não existe** — vira consulta ao catálogo |
| `busy_timeout` + `BEGIN IMMEDIATE` | 24 | MVCC e trava de linha |
| índice parcial (`CREATE INDEX ... WHERE`) | 15 | existe em PG; com restrições no SQL Server |
| `ON CONFLICT ... DO UPDATE` | 10 | `ON CONFLICT` (PG) · `MERGE` (SQL Server) |
| `substr(` e `||` | 12 | `SUBSTRING` e `CONCAT` |
| Testes com banco em memória | 22, em 19 arquivos | **não existe** Postgres em memória |

---

## A complexidade — as quatro frentes

**1. A camada de acesso.** A maioria dos 580 `SELECT` passa trocando `?` por
`%s`. O que não passa está na tabela acima — e o pior item é o `PRAGMA`: é ele
que faz `init_*` decidir se a coluna já existe (`PRAGMA table_info`) e é ele
que faz `integrity_check` e `foreign_key_check`. Essa máquina se reescreve
inteira.

**2. A concorrência — e é aqui que mora o risco.** Hoje `db.transaction()` é
`BEGIN IMMEDIATE`: **um escritor por vez**, e é isso que faz as outras travas
valerem. Em PostgreSQL ou SQL Server isso vira MVCC com trava de linha, que é
melhor — mas cada lugar que se apoiava no escritor único precisa ser
repensado.

> **A numeração é exatamente esse lugar.** `nu_numeracao` e `ri_numeracao`
> hoje estão seguros porque só um grava por vez, mais o `UNIQUE` no banco.
> É a regra que já custou o incidente de 18/08/2026 na produção e o defeito
> que o ensaio de 25/08 achou. Sob MVCC ela precisa de `SELECT ... FOR UPDATE`
> ou de uma sequência do próprio banco — conhecido, mas é mexer no lugar mais
> caro do sistema.

**3. Os testes.** Não existe Postgres em memória. Os 22 testes que hoje montam
um banco instantâneo passariam a precisar de um servidor: ou um por teste
(lento) ou um esquema por teste (mais maquinaria). A suíte, que hoje leva 12
minutos, ficaria bem mais lenta — e suíte lenta é suíte que se roda menos.

**4. O que não é banco.** `backup.py` tem 17 pontos que tratam o banco como
**arquivo**; `update_manager.py`, 9. Hoje o backup é `BACKUP_AGORA.cmd` e sai
um zip que se leva embora — é assim que a serventia cumpre o Provimento
CN-CNJ 213/2026. Com um servidor, o backup vira `pg_dump` ou um plano de
manutenção: um serviço a configurar, monitorar e saber restaurar.

**E o acervo continua SQLite.** `acervo_eoficio.sqlite3` tem 382 MB e é lido em
`ro`. Ele não migra — o sistema passaria a falar dois bancos.

---

## Os riscos, o pior primeiro

1. **A numeração**, pelo motivo acima.
2. **A tipagem frouxa.** O SQLite aceita número em coluna de texto; os outros
   não. Migrar 111 MB faria aparecer toda inconsistência de uma vez — o que é
   bom, mas várias são decisões sobre dado de anos atrás, e só o oficial pode
   tomá-las.
3. **A busca muda de sentido.** O `LIKE` do SQLite ignora maiúscula por
   padrão; o do PostgreSQL não. Toda busca teria de ser reconferida —
   inclusive a da certidão de protesto. (A busca por nome já está preparada:
   ela usa a coluna `nome_norm`, sem acento e sem caixa.)
4. **O restore.** O risco não é o backup falhar: é descobrir na hora de
   restaurar que ninguém sabia como.
5. **Mais uma peça que pode estar fora do ar**, numa serventia sem TI.

---

## O tempo

**Três a cinco meses de trabalho dedicado** até ter os testes verdes de novo,
mais um período rodando em paralelo com o SQLite antes de confiar. Ao fim
disso, o sistema faz **exatamente o que já fazia**.

---

## Os benefícios — e por que nenhum é de hoje

| Benefício | Vale para esta casa? |
|---|---|
| Escrita concorrente de verdade | **Não hoje**: 6 usuários, nenhuma trava em um ano |
| Tipos fortes (data é data, dinheiro é `numeric`) | Real — mas o sistema já guarda dinheiro em centavos inteiros e data em ISO, com teste |
| Réplica quente / standby | **Real** — é o único que o backup em arquivo não dá |
| Acesso de outra máquina, ou de outra serventia | Real **se um dia houver** |
| Ferramentas de administração | Marginal num banco de 111 MB |

Os benefícios são condicionais a coisas que não são o caso; o custo é certo.

---

## O gatilho — e ele agora se mede sozinho

Desde a **3.6.6** o sistema conta as disputas de escrita. Quando uma transação
morre com `database is locked` ou `database is busy`, uma linha é anotada em:

```
%PROGRAMDATA%\CartorioGestao\disputas_de_escrita.log
```

**O registro vai para arquivo, e não para o banco** — gravar a disputa dentro
do banco que acabou de travar seria disputar a mesma trava, e no pior caso
perder justamente o registro que interessa.

O número aparece **em qualquer tela**, para ADMIN e gerente, porque aviso raro
que mora num canto é aviso que ninguém vê. A partir de **cinco em trinta
dias** o texto muda de "uma vez ou outra é normal" para "já é rotina, vale
conversar".

Além desse, mudariam a resposta:

- uma **segunda serventia** passando a usar a mesma base;
- exigência do **TJMA ou do CNJ** por um SGBD específico;
- necessidade de **réplica quente**.

---

## O que se fez em vez de migrar

**Parou-se de aumentar a dívida.** `tests/test_portabilidade.py` guarda o
acoplamento **gratuito** — data calculada no SQL, recorte de texto no SQL,
`PRAGMA` fora dos módulos de esquema — com o número de hoje como teto, módulo
a módulo. Módulo novo entra com zero; módulo antigo pode diminuir, nunca
aumentar.

Ele **não** tenta impedir os 686 comandos, os 71 `lastrowid` nem os 43
`INSERT OR IGNORE`: para esses não há alternativa barata, e trocá-los agora
seria pagar a migração sem migrar.

**E a arquitetura já ajuda.** Os módulos de domínio recebem `con` de fora e não
abrem conexão sozinhos — é essa decisão, tomada lá atrás, que faz a conta
acima ser "700 comandos" e não "reescrever o sistema". Se um dia for preciso,
o caminho existe e este documento é o mapa.
