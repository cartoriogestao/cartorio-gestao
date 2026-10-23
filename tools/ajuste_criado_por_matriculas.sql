-- =============================================================================
-- ajuste_criado_por_matriculas.sql — Cartório Gestão, depois da virada.
-- Lote LX09 (19/10/2026). Devolve a `ri_matriculas.criado_por` o id de quem
-- carregou a matrícula, nas linhas que o `ajuste_pos_migracao.sql` deixou NULL.
--
-- DE ONDE VEM O DEFEITO: a carga do acervo do E-Ofício (`/registro-imoveis/
-- importar`) passava o NOME DE EXIBIÇÃO de quem carregava (`usuario_nome()`:
-- o `full_name`, ou o login se o nome estiver vazio) onde o `Importador` grava
-- o id de `users`. O código foi consertado no lote LX04 (`ri_web.py`, rota
-- `ri_importar`). No banco de 16/10/2026 havia 2.014 matrículas com o mesmo
-- texto de 18 caracteres em `criado_por`. O ajuste, no modo guardar, copiou
-- cada valor para `cg_ajuste_guardados` (tabela, coluna, linha_id,
-- valor_original, guardado_em) e pôs NULL na coluna, que virou bigint com FK
-- para users(id). O valor não se perdeu, mas a coluna ficou sem dono.
--
-- O QUE FAZ: para cada linha guardada de ri_matriculas.criado_por cuja
-- matrícula ainda existe e está com criado_por NULL, procura o usuário cujo
-- nome de exibição é o valor guardado e grava o id dele. Compara sem os
-- espaços das pontas e sem diferenciar maiúsculas de minúsculas
-- (public.cg_nocase, a do login; acento continua contando): a grafia do nome
-- pode ter sido corrigida no cadastro depois da carga, e a pessoa é a mesma.
--
-- RECUSA (e nada muda) se algum valor casar com NENHUM usuário ou com MAIS DE
-- UM, e o oficial não tiver dito de quem ele é (o de-para, abaixo). Gravar o
-- id de outra pessoa como autora da matrícula é pior que o NULL de hoje, e um
-- caso duvidoso não pode passar escondido no meio dos 2.014.
--
-- O DE-PARA DO OFICIAL (lote LH10, 21/10/2026). O ensaio com o banco real de
-- 21/10 deu, no seco: «com aplicar=1 este script RECUSARIA: 2 valor(es) não
-- casam com nenhum usuário e 0 casam com mais de um». Nome de quem já saiu da
-- casa, ou grafado de outro jeito, não casa com o cadastro — e só o oficial
-- sabe de quem é. Ele diz numa tabela do schema, `cg_ajuste_de_para`
-- (valor_original, user_id), uma linha por valor:
--   - user_id = o id do usuário: as matrículas daquele valor recebem esse id;
--   - user_id NULL: a matrícula fica SEM DONO (NULL), com o original guardado
--     em cg_ajuste_guardados — é uma decisão, e o valor deixa de segurar os
--     outros.
-- O de-para vale MAIS que o nome: se o oficial anotou um valor que também
-- casa pelo nome, vale o que ele anotou. O valor é comparado exatamente como
-- está guardado; por isso a linha de anotar copia o valor de
-- cg_ajuste_guardados pela CHAVE (os 12 primeiros do md5), e ninguém digita
-- nome de pessoa — no console do Windows o acento digitado não chega igual.
--
-- O valor original FICA em cg_ajuste_guardados (rastreio): este script não
-- apaga nem altera nada ali. Idempotente: só preenche criado_por que está
-- NULL; rodar de novo não muda nada e não dá erro.
--
-- SEM DADO PESSOAL NA SAÍDA, POR PADRÃO: o valor guardado é nome de pessoa, e
-- a saída deste script volta para a equipe do Mac. Ela mostra só contagens, o
-- tamanho do texto e o id do usuário — nunca o nome. O nome só aparece com
-- `-v mostrar_valores=1`, que é para a TELA de quem roda no servidor: não se
-- copia, não se salva em arquivo e não se manda para fora (LGPD). Esse modo
-- não grava matrícula nenhuma (recusa junto com aplicar=1); ele deixa pronta,
-- vazia, a tabela cg_ajuste_de_para, e é a única coisa que ele confirma.
--
-- COMO RODAR (o mesmo psql do ajuste; uma transação):
--   SECO, o padrão — só conta, e termina em ROLLBACK:
--     psql -h 127.0.0.1 -p 5434 -U cg -d cartorio -X -f ajuste_criado_por_matriculas.sql
--   VER OS VALORES SEM DONO — só no servidor, na tela, para o oficial decidir:
--     psql ... -X -v mostrar_valores=1 -f ajuste_criado_por_matriculas.sql
--     e, para cada valor, a linha «para_anotar» que ele imprime, trocando <id>
--     pelo id do usuário (ou por NULL: fica sem dono). Depois, o SECO de novo.
--   GRAVAR — só com a autorização do oficial, depois de ver o número do seco:
--     psql ... -X -v aplicar=1 -f ajuste_criado_por_matriculas.sql
--     (ou, dentro do psql: \set aplicar 1  e depois  \i ajuste_criado_por_matriculas.sql)
--   variáveis opcionais:
--     -v schema=producao     schema alvo (padrão: producao). Vira o search_path.
--     -v aplicar=0|1         0 (padrão) só conta; 1 grava.
--     -v mostrar_valores=0|1 0 (padrão) sem nome; 1 mostra os valores sem dono
--                            certo (NOME DE PESSOA: só na tela do servidor).
-- =============================================================================

\set ON_ERROR_STOP on
\encoding UTF8
\if :{?schema}
\else
  \set schema producao
\endif
\if :{?aplicar}
\else
  \set aplicar 0
\endif
\if :{?mostrar_valores}
\else
  \set mostrar_valores 0
\endif

BEGIN;
SET LOCAL search_path = :"schema", public;
SET LOCAL lock_timeout = '15s';
SELECT set_config('cg.aplicar', :'aplicar', true) AS aplicar,
       set_config('cg.mostrar_valores', :'mostrar_valores', true) AS mostrar_valores,
       set_config('cg.schema', :'schema', true) AS schema_pedido,
       current_schema() AS schema_alvo;

-- ------------------------------------------------------------- 0. pré-checagem
-- O terreno é conferido antes de qualquer leitura: sem a tabela dos guardados,
-- ou com a coluna ainda em texto, o ajuste de 18/10 não rodou aqui e não há o
-- que devolver.
DO $pre$
DECLARE tipo text;
BEGIN
  IF current_setting('cg.aplicar') NOT IN ('0', '1') THEN
    RAISE EXCEPTION 'aplicar deve ser 0 (seco) ou 1 (gravar) (veio: %)', current_setting('cg.aplicar');
  END IF;
  IF current_setting('cg.mostrar_valores') NOT IN ('0', '1') THEN
    RAISE EXCEPTION 'mostrar_valores deve ser 0 (sem nome) ou 1 (mostra os valores) (veio: %)', current_setting('cg.mostrar_valores');
  END IF;
  -- a saída com nome de pessoa não acompanha uma gravação: ela é para decidir
  IF current_setting('cg.aplicar') = '1' AND current_setting('cg.mostrar_valores') = '1' THEN
    RAISE EXCEPTION 'mostrar_valores=1 só roda no seco: a saída dele tem nome de pessoa e não pode acompanhar a gravação. Grave com aplicar=1 sem mostrar_valores.';
  END IF;
  -- schema que não existe some do search_path calado, e o alvo vira o public
  IF current_schema() IS DISTINCT FROM current_setting('cg.schema') THEN
    RAISE EXCEPTION 'o schema % não existe neste banco', current_setting('cg.schema');
  END IF;
  IF to_regclass('users') IS NULL OR to_regclass('ri_matriculas') IS NULL THEN
    RAISE EXCEPTION 'schema % não tem as tabelas users e ri_matriculas: é o schema certo?', current_schema();
  END IF;
  IF to_regclass('cg_ajuste_guardados') IS NULL THEN
    RAISE EXCEPTION 'schema % não tem cg_ajuste_guardados: o ajuste_pos_migracao.sql não rodou no modo guardar aqui, e não há o que devolver', current_schema();
  END IF;
  SELECT format_type(a.atttypid, a.atttypmod) INTO tipo
    FROM pg_attribute a
   WHERE a.attrelid = to_regclass('ri_matriculas') AND a.attname = 'criado_por' AND NOT a.attisdropped;
  IF tipo IS DISTINCT FROM 'bigint' AND tipo IS DISTINCT FROM 'integer' THEN
    RAISE EXCEPTION 'ri_matriculas.criado_por é % (esperado bigint): rode o ajuste_pos_migracao.sql antes', coalesce(tipo, 'inexistente');
  END IF;
  IF to_regcollation('public.cg_nocase') IS NULL THEN
    RAISE EXCEPTION 'falta a collation public.cg_nocase (o ajuste_pos_migracao.sql a cria)';
  END IF;
END $pre$;

-- ------------------------------------------------------ 1. o de-para do oficial
-- Nasce vazia, aqui, para a conta poder ler sempre a mesma tabela. No seco ela
-- some com o ROLLBACK; com mostrar_valores=1 ela fica (é para ser preenchida);
-- com aplicar=1 também. O user_id aponta para users: id que não existe não
-- entra.
DO $de_para$
BEGIN
  IF to_regclass('cg_ajuste_de_para') IS NULL THEN
    CREATE TABLE cg_ajuste_de_para (
      valor_original text PRIMARY KEY,
      user_id bigint REFERENCES users(id));
  END IF;
END $de_para$;

-- ------------------------------------------------------------------- 2. trava
-- Só ao gravar. Ninguém cria, renomeia ou apaga usuário entre a contagem e a
-- gravação: senão um nome que casava com um só usuário na conta podia casar
-- com dois no UPDATE. SHARE não impede ler, e a transação dura milissegundos.
-- O de-para também: o que o oficial anotou é o que a conta leu.
\if :aplicar
LOCK TABLE users IN SHARE MODE;
LOCK TABLE cg_ajuste_de_para IN SHARE MODE;
\endif

-- ------------------------------------------------------------------ 3. a conta
-- Uma linha por matrícula guardada, com o usuário que o nome aponta e o que o
-- oficial anotou. Feita uma vez só: a recusa e a gravação leem a MESMA conta.
CREATE TEMP TABLE cg_criado_por_alvo ON COMMIT DROP AS
SELECT g.linha_id AS matricula_id,
       g.valor_original,
       (m.id IS NOT NULL) AS matricula_existe,
       m.criado_por AS criado_por_hoje,
       u.qtd AS usuarios,
       (d.valor_original IS NOT NULL) AS no_de_para,
       CASE WHEN d.valor_original IS NOT NULL THEN d.user_id   -- o oficial disse (NULL: sem dono)
            WHEN u.qtd = 1 THEN u.id END AS usuario_id
  FROM cg_ajuste_guardados g
  LEFT JOIN ri_matriculas m ON m.id = g.linha_id
  LEFT JOIN cg_ajuste_de_para d ON d.valor_original = g.valor_original
  CROSS JOIN LATERAL (
       -- o nome de exibição, como `usuario_nome()` o monta
       SELECT count(*) AS qtd, min(x.id) AS id
         FROM users x
        WHERE coalesce(nullif(btrim(x.full_name), ''), btrim(x.username)) COLLATE public.cg_nocase
              = btrim(g.valor_original) COLLATE public.cg_nocase) u
 WHERE g.tabela = 'ri_matriculas' AND g.coluna = 'criado_por';

\echo '== matrículas com criado_por guardado pelo ajuste (o valor não aparece: é nome de pessoa)'
SELECT count(*) AS guardadas,
       count(*) FILTER (WHERE NOT matricula_existe) AS matricula_apagada,
       count(*) FILTER (WHERE criado_por_hoje IS NOT NULL) AS ja_preenchidas,
       count(*) FILTER (WHERE matricula_existe AND criado_por_hoje IS NULL) AS a_preencher,
       count(*) FILTER (WHERE matricula_existe AND criado_por_hoje IS NULL AND no_de_para) AS pelo_de_para,
       count(*) FILTER (WHERE matricula_existe AND criado_por_hoje IS NULL AND no_de_para
                          AND usuario_id IS NULL) AS sem_dono_pelo_de_para,
       count(DISTINCT valor_original) AS valores_distintos
  FROM cg_criado_por_alvo;

\echo '== por valor guardado: com quantos usuários o nome de exibição casa (esperado: 1, ou o de-para)'
SELECT length(btrim(valor_original)) AS caracteres,
       usuarios AS usuarios_que_casam,
       no_de_para AS de_para,
       usuario_id,
       count(*) FILTER (WHERE matricula_existe AND criado_por_hoje IS NULL) AS a_preencher,
       count(*) AS guardadas
  FROM cg_criado_por_alvo
 GROUP BY valor_original, usuarios, no_de_para, usuario_id
 ORDER BY guardadas DESC, min(matricula_id);

-- ------------------------------------------------------------------ 4. recusa
-- Tudo ou nada: um valor duvidoso, sem a palavra do oficial, segura a gravação
-- de todos.
DO $recusa$
DECLARE nenhum bigint; varios bigint;
BEGIN
  SELECT count(DISTINCT valor_original) FILTER (WHERE usuarios = 0),
         count(DISTINCT valor_original) FILTER (WHERE usuarios > 1)
    INTO nenhum, varios
    FROM cg_criado_por_alvo
   WHERE matricula_existe AND criado_por_hoje IS NULL AND NOT no_de_para;
  IF nenhum + varios = 0 THEN
    RAISE NOTICE 'todo valor a preencher tem dono certo: casa com exatamente um usuário, ou o oficial anotou o dono (ou que fica sem dono) em cg_ajuste_de_para';
  ELSIF current_setting('cg.aplicar') = '1' THEN
    RAISE EXCEPTION E'RECUSADO, NADA FOI ALTERADO: % valor(es) guardado(s) não casam com nenhum usuário e % casam com mais de um, sem dono anotado em cg_ajuste_de_para.\nConfira o nome no cadastro de usuários (tela de usuários), ou rode no servidor com -v mostrar_valores=1 e anote o dono de cada valor; depois rode o seco de novo.', nenhum, varios;
  ELSE
    RAISE NOTICE 'SECO: com aplicar=1 este script RECUSARIA: % valor(es) não casam com nenhum usuário e % casam com mais de um (sem dono anotado em cg_ajuste_de_para)', nenhum, varios;
  END IF;
END $recusa$;

-- ------------------------------------------- 5. os valores, só na tela (opcional)
\if :mostrar_valores
\echo ''
\echo '!! ATENÇÃO: daqui até o fim a saída tem NOME DE PESSOA. Ela é só para a tela do servidor:'
\echo '!! não copie, não salve em arquivo e não mande para fora do cartório (LGPD).'
\echo '== valores guardados que pedem a palavra do oficial (sem usuário, ou com mais de um) e os já anotados'
SELECT left(md5(valor_original), 12) AS chave,
       count(*) FILTER (WHERE matricula_existe AND criado_por_hoje IS NULL) AS a_preencher,
       usuarios AS usuarios_que_casam,
       CASE WHEN NOT no_de_para THEN 'sem decisão'
            WHEN usuario_id IS NULL THEN 'anotado: fica sem dono'
            ELSE 'anotado: usuário ' || usuario_id END AS situacao,
       valor_original AS valor
  FROM cg_criado_por_alvo
 WHERE no_de_para OR usuarios <> 1
 GROUP BY valor_original, usuarios, no_de_para, usuario_id
 ORDER BY a_preencher DESC, chave;

\echo '== usuários (para escolher o dono)'
SELECT id, username AS login, full_name AS nome_de_exibicao FROM users ORDER BY id;

\echo '== para anotar: troque <id> pelo id do usuário (ou por NULL: a matrícula fica sem dono e o original continua guardado)'
\echo '   e rode a linha no psql. Rodar de novo com outro id troca a anotação. Depois, o seco de novo.'
SELECT format($f$INSERT INTO %1$I.cg_ajuste_de_para (valor_original, user_id) SELECT DISTINCT valor_original, CAST(<id> AS bigint) FROM %1$I.cg_ajuste_guardados WHERE tabela = 'ri_matriculas' AND coluna = 'criado_por' AND left(md5(valor_original), 12) = %2$L ON CONFLICT (valor_original) DO UPDATE SET user_id = EXCLUDED.user_id;$f$,
              current_schema(), left(md5(valor_original), 12)) AS para_anotar
  FROM cg_criado_por_alvo
 WHERE matricula_existe AND criado_por_hoje IS NULL AND (no_de_para OR usuarios <> 1)
 GROUP BY valor_original
 ORDER BY count(*) DESC, 1;
\endif

-- ----------------------------------------------------------------- 6. gravação
\if :aplicar
UPDATE ri_matriculas m
   SET criado_por = a.usuario_id
  FROM cg_criado_por_alvo a
 WHERE a.matricula_id = m.id AND a.usuario_id IS NOT NULL AND m.criado_por IS NULL;

\echo '== conferência: matrículas guardadas que continuam sem criado_por (esperado: só as que o de-para deixou sem dono)'
SELECT count(*) AS continuam_nulas,
       count(*) FILTER (WHERE d.valor_original IS NOT NULL AND d.user_id IS NULL) AS sem_dono_pelo_de_para
  FROM cg_ajuste_guardados g
  JOIN ri_matriculas m ON m.id = g.linha_id
  LEFT JOIN cg_ajuste_de_para d ON d.valor_original = g.valor_original
 WHERE g.tabela = 'ri_matriculas' AND g.coluna = 'criado_por' AND m.criado_por IS NULL;

\echo '== conferência: matrículas guardadas com criado_por, por usuário'
SELECT m.criado_por AS usuario_id, count(*) AS matriculas
  FROM cg_ajuste_guardados g JOIN ri_matriculas m ON m.id = g.linha_id
 WHERE g.tabela = 'ri_matriculas' AND g.coluna = 'criado_por' AND m.criado_por IS NOT NULL
 GROUP BY m.criado_por
 ORDER BY m.criado_por;

COMMIT;
\echo '== ajuste_criado_por_matriculas.sql: GRAVADO'
\elif :mostrar_valores
COMMIT;
\echo '== ajuste_criado_por_matriculas.sql: VALORES MOSTRADOS, nenhuma matrícula foi gravada (a tabela cg_ajuste_de_para está pronta para as anotações)'
\else
ROLLBACK;
\echo '== ajuste_criado_por_matriculas.sql: SECO, nada foi gravado (para gravar: -v aplicar=1)'
\endif
