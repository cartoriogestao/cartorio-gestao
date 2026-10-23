# Roteiro da virada para o PostgreSQL: os passos do banco, na ordem

Lote LH10, 21/10/2026. Este roteiro sai do ensaio feito no Mac em 21/10, das 18h06
às 18h10, com o banco real da produção daquele dia: 222 tabelas e 3.214.960 linhas.
Do ensaio vieram só contagens, sem dado.

Ele não substitui o `ROTEIRO_VIRADA.md` da entrega (18 e 19/10). Lá estão a parte A
(preparação: serviço do PostgreSQL, psycopg), os tempos medidos no servidor, a
janela B5–B6 e o caminho de volta. Aqui fica fixada a ORDEM dos passos que mexem
no banco, agora que as ferramentas estão na branch.

## As ferramentas

| arquivo | passo | de onde veio |
|---|---|---|
| `tools/migrar_para_postgres.py` | B3, a carga, com a conferência dela | É a versão da entrega de 17/10 (`entrega/migrar_para_postgres.py` do `CartorioGestao_PostgreSQL_20261017.zip`), a mesma do ensaio de 21/10. Entrou na branch sem mudar nenhum byte: sha256 `f383b39df2383f4cf0ed13925d2413819ef002a2b226dedd226f0baebd7f884d` |
| `tools/ajuste_pos_migracao.sql` | B4, o ajuste | Pacote do servidor de 19/10, mais o bloco 3b do LH10 (o UNIQUE de `ri_cnib_decisoes`) |
| `python banco_pg.py conferir-carga` | conferência da carga | Veio do LH07. O LH10 acrescentou o desconto do que o ajuste guardou |
| `tools/ajuste_criado_por_matriculas.sql` | LX09 | Veio do LX09. O LH10 acrescentou o de-para do oficial e o `mostrar_valores` |

O código novo ainda não está instalado nos passos B3, B4 e conferir-carga. Por isso
esses passos rodam **da pasta do código novo**: o pacote do ciclo extraído numa
pasta de trabalho, como no ensaio. O Python é o da produção, que tem o psycopg desde
o passo A4. As linhas abaixo usam o psql da entrega
(`-h 127.0.0.1 -p 5434 -U cg -d cartorio`). Troque pelo do dia, se for outro.

## A ordem

### 1. B3 — a carga

```
python tools/migrar_para_postgres.py --sqlite <cópia B2 .sqlite3> --dsn "host=127.0.0.1 port=5434 user=cg dbname=cartorio" --schema producao --recriar --relatorio <pasta>\relatorio_carga.md
```

- **Exigido:** saída 0. O relatório tem de dizer «Tabelas divergentes: 0» e
  «Corrente de hash do RI: confere dos dois lados».
- **No ensaio de 21/10:** 222 de 222 tabelas conferidas por contagem e sha256. A
  corrente do RI conferiu (1.283 atos).
- `--recriar` apaga o schema antes. Use só na janela, contra a cópia B2. A
  ferramenta recusa o `public`, e recusa schema com tabelas se faltar
  `--recriar`.
- O relatório e a saída mostram contagens, nomes de tabela e coluna e ids. Valor
  fora do tipo aparece como «texto de N caracteres». Só o vazio, números e datas
  aparecem por extenso. Antes de mandar para fora, confira se nenhum desses números
  é documento de pessoa.

### 2. B4 — o ajuste

```
psql -h 127.0.0.1 -p 5434 -U cg -d cartorio -X -v schema=producao -v nao_numericos=guardar -f tools/ajuste_pos_migracao.sql
```

O modo `guardar` foi a decisão do oficial de 18/10. O mesmo modo vale para as linhas
repetidas na chave de um UNIQUE do código.

- **Exigido:**
  - «CONCLUÍDO» e «tipos: 13 de 13 OK»;
  - as 2 FKs para `users` validadas;
  - 0 sequências atrás;
  - «UNIQUE OK: ri_cnib_decisoes.ri_cnib_decisoes_matricula_id_protocolo_cnib_pessoa_documen_key».
- **No ensaio de 21/10**, o que foi para `cg_ajuste_guardados`:

  | coluna | valores guardados |
  |---|---:|
  | `ri_matriculas.criado_por` | 2.015 |
  | `audit_logs.entity_id` | 6 |
  | `nt_ato_partes.conjuge_tipo` | 2 |
  | `nt_atos.filhos_maiores` | 1 |

  Além disso, em `ri_atos.lavrado_por` 1 login foi trocado pelo id.
- **O UNIQUE de `ri_cnib_decisoes`.** A comparação de esquema do ensaio (feita por
  nome de índice) achou faltando
  `ri_cnib_decisoes_matricula_id_protocolo_cnib_pessoa_documen_key`. Só o nome
  estava diferente. A carga encurta nome com mais de 63 bytes com um hash
  (`nome_curto`), e no schema de 18/10 ele é `..._pessoa_do_3bbea59d`. O PostgreSQL,
  que nomeia o UNIQUE do código, corta e põe `_key`.
  - O esperado no B4 é a linha «... `_pessoa_do_3bbea59d` renomeado para
    `..._pessoa_documen_key`», sem tocar em linha nenhuma.
  - Se em vez disso aparecer «linha(s) repetida(s) na chave do UNIQUE», a carga
    não conseguiu o único. No modo `guardar`, fica a decisão de menor id de cada
    grupo, que é a que o código lê primeiro. As outras vão inteiras para
    `cg_ajuste_guardados` (coluna `*`, a linha em JSON, restaurável com
    `json_populate_record`).
- O ajuste é idempotente: rodar de novo não muda nada.

### 3. Conferir a carga — ANTES de subir o código

Rode da pasta do código novo, com `CG_PG_DSN` e `CG_PG_SCHEMA` no ambiente:

```
set "CG_PG_DSN=host=127.0.0.1 port=5434 user=cg dbname=cartorio"
set "CG_PG_SCHEMA=producao"
python banco_pg.py conferir-carga <cópia B2 .sqlite3>
```

- **Exigido:** saída 0.
- As linhas `AVISO: ... guardados pelo ajuste em cg_ajuste_guardados (não é
  perda)` repetem os números do B4. A conferência desconta exatamente o que está
  guardado e continua fora. Qualquer diferença além disso é perda, ou acréscimo, e
  dá saída 1, com a tabela e a coluna em `linhas_diferentes` e
  `valores_diferentes`.
- A `_ping` aparece só como aviso (`tabelas_ignoradas`, LH09).
- **Por que antes de subir o código:** a primeira subida insere linhas de
  configuração e cria tabelas e colunas que faltam (LH09). Depois dela a contagem não
  bate por isso, e a conferência perde o valor.

### 4. Subir o código

São os passos B4 a B7 do roteiro da entrega: as variáveis no `.cmd`, subir a
3.6.292, aplicar o `.cgu` real pela tela de Atualizações e conferir as telas.

### 5. LX09, seco — depois que o código subiu, fora da parada

```
psql -h 127.0.0.1 -p 5434 -U cg -d cartorio -X -v schema=producao -f tools/ajuste_criado_por_matriculas.sql
```

O código abre sem este passo. A decisão do oficial não precisa caber na janela.

- O seco só conta e termina em ROLLBACK. A saída não tem nome de pessoa e pode
  voltar para a equipe do Mac.
- **No ensaio de 21/10:** «com aplicar=1 este script RECUSARIA: 2 valor(es) não
  casam com nenhum usuário e 0 casam com mais de um».

### 6. LX09, aplicar — por ordem do oficial

Os valores que não casam com o cadastro (pessoa que saiu, grafia diferente) só o
oficial sabe de quem são.

1. **No servidor, só na tela**, rode o modo que mostra os valores:

   ```
   psql ... -X -v schema=producao -v mostrar_valores=1 -f tools/ajuste_criado_por_matriculas.sql
   ```

   Ele lista cada valor sem dono certo, com uma chave (os 12 primeiros do md5), a
   lista de usuários e uma linha `para_anotar` por valor. Essa saída tem **nome de
   pessoa**: não se copia, não se salva em arquivo e não se manda para fora (LGPD).
   Este modo não grava matrícula e recusa junto com `aplicar=1`. Ele só deixa pronta,
   vazia, a tabela `cg_ajuste_de_para (valor_original, user_id)`.
2. Para cada valor, o oficial roda a linha `para_anotar`, trocando `<id>` pelo id do
   usuário. Se trocar por `NULL`, a matrícula fica sem dono e o original continua
   guardado. A linha copia o valor de `cg_ajuste_guardados` pela chave: ninguém
   digita o nome, porque no console do Windows o acento digitado não chega igual.
   Rodar a linha de novo com outro id troca a anotação. O que o oficial anota vale
   mais que o nome que casa sozinho.
3. Rode o seco de novo. O esperado é «todo valor a preencher tem dono certo».
4. Grave com a autorização do oficial:

   ```
   psql ... -X -v schema=producao -v aplicar=1 -f tools/ajuste_criado_por_matriculas.sql
   ```

   - **Exigido:** «GRAVADO».
   - Em `continuam_nulas` sobram só as anotadas sem dono (`sem_dono_pelo_de_para`).
   - O original de cada valor continua em `cg_ajuste_guardados`.
   - O LX09 é idempotente.

## Onde estão as provas

Todas rodam num SQLite de fixture, sem dado real (`tests/virada_de_teste.py`), pelas
ferramentas de verdade: a carga em outro processo e o SQL pelo psql.

| assunto | arquivo de teste |
|---|---|
| carga | `tests/test_banco_pg_virada.py` (copia e confere; acusa a linha mudada; não escreve por cima; a conferência depois do ajuste) |
| ajuste | `tests/test_ajuste_pos_migracao.py` (padrão para; guardar guarda e anula; duas vezes sem mudar nada) |
| UNIQUE | `tests/test_ri_cnib_decisoes_na_virada.py` (cada caminho do bloco 3b, com e sem repetição) |
| LX09 | `tests/test_ajuste_criado_por_matriculas.py` (seco sem nome; recusa; mostrar_valores; de-para) |
