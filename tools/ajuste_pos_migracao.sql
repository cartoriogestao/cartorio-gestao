-- =============================================================================
-- ajuste_pos_migracao.sql — Cartório Gestão, virada para o PostgreSQL
-- Escrito e testado em 18/10/2026 (UTC-3) no SERVIDOR, numa CÓPIA do cluster da
-- entrega (porta 5435). Roda DEPOIS de `migrar_para_postgres.py` e ANTES de
-- subir o código da branch `migracao-pg` (testado com as cabeças 4a4dddf e 0514063).
--
-- COMO RODAR (uma transação; se qualquer verificação falhar, nada muda):
--   psql -h 127.0.0.1 -p 5434 -U cg -d cartorio -X -f ajuste_pos_migracao.sql
--   variáveis opcionais:
--     -v schema=producao          schema alvo (padrão: producao). Vira o search_path.
--     -v nao_numericos=abortar    padrão. Se uma coluna que o código quer inteira
--                                 tiver texto que não é número, ABORTA e diz
--                                 quantos valores, em que coluna. Nada muda.
--     -v nao_numericos=guardar    DECISÃO DO OFICIAL: guarda cada valor que não
--                                 converte em `cg_ajuste_guardados` (tabela,
--                                 coluna, id da linha, valor original), põe NULL
--                                 na coluna e segue. Nada se perde; o valor fica
--                                 consultável e restaurável.
--     O MESMO MODO vale para as linhas repetidas na chave de um UNIQUE do
--     código (bloco 3b): abortar para e diz quantas; guardar fica com a de
--     MENOR id de cada grupo e guarda as outras INTEIRAS (coluna '*', a linha
--     em JSON) antes de apagá-las.
--   Idempotente: rodar de novo não muda nada e não dá erro.
--
-- DE ONDE VEM CADA TIPO: do CÓDIGO da branch. O código foi aberto num schema
-- VAZIO desta mesma instalação e criou o seu esquema nativo; o esperado abaixo
-- é a diferença entre esse esquema e o migrado (ri_schema.py, notas_schema.py,
-- caixa_schema.py, rg_schema.py ...). Onde o código declara INTEGER, o banco
-- migrado usa `bigint` em TODAS as colunas (padrão da migração); mantemos
-- bigint: guarda tudo o que o integer do código guarda, e o Python não vê
-- diferença. Idem `double precision` no lugar de `real` (sd_selos), que não
-- perde precisão. Essas diferenças de largura NÃO são tratadas aqui de propósito.
--
-- O QUE ESTE AJUSTE MUDA (13 colunas + 1 collation + 2 FKs + sequências):
--   texto -> bigint (o código declara INTEGER; audit_logs.entity_id por pedido
--   da equipe do Mac de 19/10/2026):
--     nt_ato_partes.conjuge_tipo   (notas_schema.py: ADD COLUMN ... INTEGER; código CENSEC)
--     nt_atos.filhos_maiores       (notas_schema.py: filhos_maiores INTEGER)
--     ri_atos.lavrado_por          (ri_schema.py: INTEGER + FOREIGN KEY users(id))
--     ri_matriculas.criado_por     (ri_schema.py: INTEGER + FOREIGN KEY users(id))
--     audit_logs.entity_id         (pedido de 19/10/2026: bigint, mesmo modo
--                                  guardar aprovado pelo oficial; sem nova decisão)
--   bigint -> text (o código declara TEXT; todas as 8 estão VAZIAS no banco de 16/10):
--     cx_depositos.criado_por, cx_recibos.cancelado_por, nt_autenticacoes.criado_por,
--     nt_cartoes.criado_por, nt_reconhecimentos.criado_por,
--     rg_encaminhamentos.criado_por, ri_ctp_itens.atualizado_por,
--     ri_matriculas.conferido_por
--   ATENÇÃO audit_logs.entity_id (conferido na cabeça 3b95885 de 19/10/2026):
--     o código ainda DECLARA TEXT (database.py:379) e ainda GRAVA chave de texto
--     em 9 pontos (livro3_modelos_web.py:79,95; modelos_elementos_web.py:96,106,
--     189; modelos_web.py:138,162,274,294). Com bigint esses INSERTs falham e
--     database.log engole o erro (DataError -> OperationalError): a linha de
--     auditoria NÃO entra (só vai para o log do servidor). O código precisa
--     parar de passar texto ali (ex.: entity_id=None e a chave em details).
--   Das 17 colunas que a migração deixou em TEXT, 12 já são TEXT no código
--   (nt_atos/pt_atos/pt_titulos/ra_atos/ra_registros/rc_assentos/rc_atos/
--   rg_atos/rg_qualificacoes/rg_registros/rg_titulos.criado_por e
--   ri_matriculas.atualizado_por) e ficam; 5 viram bigint (acima).
--   Das 32 colunas *_por que estão bigint, o código quer TEXT em 8 (acima) e
--   INTEGER nas outras 24 (cx_caixas.aberto/conferido/fechado_por,
--   cx_importacoes.executada_por, cx_lancamentos.criado_por, cx_protocolos.criado_por,
--   cx_recibos.emitido_por, pr_especie_do_processo.definida_por, pr_vinculos.criado_por,
--   rd_relatos.lido_por, ri_certidoes.emitida_por, ri_cnib_leituras.pedida_por,
--   ri_ctp_remessas.fechado/gerado_por, ri_delegatarios.criado_por,
--   ri_doi_remessas.entregue/gerado_por, ri_modelos.atualizado_por,
--   ri_notas_devolutivas.emitida_por, ri_numeracao.fixado_por,
--   ri_protocolos.criado_por, ri_qualificacoes.criado_por,
--   ri_revisoes.anotada/baixada_por) — essas ficam bigint.
--
-- VALORES QUE NÃO CONVERTEM no banco de 16/10/2026 21:18 (contagem, sem o valor):
--   ri_matriculas.criado_por   2.014 linhas, 1 valor distinto (texto de 18
--                              caracteres; nome de exibição gravado por uma
--                              importação antiga — o código só aceita id de users)
--   ri_atos.lavrado_por            1 linha (texto de 7 caracteres; é o LOGIN do
--                                  usuário id 3 -> no modo guardar vira lavrado_por=3,
--                                  bloco 1b, e o original fica guardado)
--   nt_ato_partes.conjuge_tipo     2 linhas (texto de 8 caracteres)
--   nt_atos.filhos_maiores         1 linha (texto de 174 caracteres)
--   audit_logs.entity_id           6 linhas (medido 19/10/2026): 4 chaves
--                                  "atribuição/ato/parte" de mo_elementos
--                                  (ELEMENTO_AJUSTADO, 30 caracteres), 1 de
--                                  RI_MATRICULA (14 car.) e 1 de SETTINGS (22 car.)
--   TOTAL esperado no modo guardar: 2.018 + 6 = 2.024 (banco de 16/10).
--   -> com o padrão (abortar) este ajuste PARA. Seguir pede a decisão do oficial
--      (`-v nao_numericos=guardar`). Vazio ('') vira NULL (não há nenhum hoje).
--
-- ÓRFÃS (FKs NOT VALID da migração; este ajuste só as LISTA, não apaga nada):
--   medido no ensaio, em TODAS as FKs de uma coluna do schema:
--     ri_revisoes.matricula_id -> ri_matriculas: 1 linha (a já conhecida)
--   nenhuma outra. As 2 FKs recriadas aqui (ri_atos.lavrado_por e
--   ri_matriculas.criado_por -> users) ficam sem órfãs depois da conversão e
--   são VALIDADAS. As outras 188 FKs da migração continuam NOT VALID (padrão da
--   migração; validar fica para depois, fora da janela da virada).
--
-- INFORMATIVO, SEM AÇÃO: aj_consultas id 52 tinha um caractere NUL (0x00) no
-- SQLite; a migração o trocou por U+FFFD. Texto do PostgreSQL não guarda NUL,
-- então não há como restaurar — e não é preciso.
--
-- O índice ix_ri_mat_imovel_norm NÃO é criado aqui: é do CÓDIGO. A versão
-- anunciada em 18/10 o recria como índice de trigramas (pg_trgm), e a extensão
-- pg_trgm 1.6 foi conferida como disponível no PostgreSQL 18 portátil do servidor.
--
-- Revisão 18/10/2026 (DECISAO_OFICIAL_20261018.md): bloco 1b, ri_atos.lavrado_por
-- com login de exatamente um usuário recebe o id desse usuário.
-- Revisão 19/10/2026 (pedido da equipe do Mac): audit_logs.entity_id deixa de
-- ser exceção e vira bigint como as outras 4; conferência final passa a exigir
-- 13 de 13 tipos OK e mostra o total guardado (esperado 2.024 no banco de 16/10).
-- Revisão 21/10/2026 (lote LH10; o arquivo entra na branch, em tools/): bloco 3b,
-- o UNIQUE de ri_cnib_decisoes com o NOME que o código dá. O ensaio de 21/10 com
-- o banco real comparou o esquema por nome de índice e achou faltando
-- `ri_cnib_decisoes_matricula_id_protocolo_cnib_pessoa_documen_key`. A chave
-- estava lá: o migrar_para_postgres.py encurta nome com mais de 63 bytes com um
-- hash (`nome_curto`: 54 bytes + 8 do sha1), e o PostgreSQL, que é quem nomeia o
-- UNIQUE do código, corta as colunas e põe `_key`. No schema.sql de 18/10 ela se
-- chama `..._pessoa_do_3bbea59d`. O bloco 3b RENOMEIA o que já é único nessas
-- colunas; cria o UNIQUE só se não houver nenhum (tabela de antes do UNIQUE, ou
-- a carga caiu no índice comum por repetição), e aí as repetidas seguem o modo.
-- =============================================================================

\set ON_ERROR_STOP on
\encoding UTF8
\if :{?schema}
\else
  \set schema producao
\endif
\if :{?nao_numericos}
\else
  \set nao_numericos abortar
\endif

BEGIN;
SET LOCAL search_path = :"schema", public;
SET LOCAL lock_timeout = '15s';
SELECT set_config('cg.nao_numericos', :'nao_numericos', true) AS modo_nao_numericos,
       current_schema() AS schema_alvo;

CREATE TEMP TABLE cg_ajuste_alvo (tabela text, coluna text, esperado text, fonte text) ON COMMIT DROP;
INSERT INTO cg_ajuste_alvo VALUES
  ('nt_ato_partes',      'conjuge_tipo',   'bigint', 'notas_schema.py: ("nt_ato_partes","conjuge_tipo","INTEGER")'),
  ('nt_atos',            'filhos_maiores', 'bigint', 'notas_schema.py: filhos_maiores INTEGER'),
  ('ri_atos',            'lavrado_por',    'bigint', 'ri_schema.py: lavrado_por INTEGER, FK users(id)'),
  ('ri_matriculas',      'criado_por',     'bigint', 'ri_schema.py: criado_por INTEGER, FK users(id)'),
  ('cx_depositos',       'criado_por',     'text',   'caixa_schema.py: criado_por TEXT'),
  ('cx_recibos',         'cancelado_por',  'text',   'caixa_schema.py: cancelado_por TEXT'),
  ('nt_autenticacoes',   'criado_por',     'text',   'notas_schema.py: criado_por TEXT'),
  ('nt_cartoes',         'criado_por',     'text',   'notas_schema.py: criado_por TEXT'),
  ('nt_reconhecimentos', 'criado_por',     'text',   'notas_schema.py: criado_por TEXT'),
  ('rg_encaminhamentos', 'criado_por',     'text',   'rg_schema.py: criado_por TEXT'),
  ('ri_ctp_itens',       'atualizado_por', 'text',   'ri_schema.py: atualizado_por TEXT'),
  ('ri_matriculas',      'conferido_por',  'text',   'ri_schema.py: conferido_por TEXT'),
  ('audit_logs',         'entity_id',      'bigint', 'pedido 19/10/2026: bigint no modo guardar (o código 3b95885 ainda declara TEXT)');

-- Os UNIQUE que o código declara e que o banco migrado tem de ter com o MESMO
-- nome (o que o PostgreSQL dá ao UNIQUE do CREATE TABLE do código) e as mesmas
-- colunas, na mesma ordem.
CREATE TEMP TABLE cg_ajuste_unico (tabela text, nome text, colunas text[], fonte text) ON COMMIT DROP;
INSERT INTO cg_ajuste_unico VALUES
  ('ri_cnib_decisoes', 'ri_cnib_decisoes_matricula_id_protocolo_cnib_pessoa_documen_key',
   ARRAY['matricula_id', 'protocolo_cnib', 'pessoa_documento', 'pessoa_nome'],
   'ri_schema.py: UNIQUE(matricula_id, protocolo_cnib, pessoa_documento, pessoa_nome)');

-- ------------------------------------------------------------- 0. pré-checagem
-- Tudo o que pode impedir o ajuste é medido ANTES de mudar qualquer coisa.
DO $pre$
DECLARE
  r record; atual text; ruins bigint; zeros bigint; problemas text := ''; modo text := current_setting('cg.nao_numericos');
  u record; chave int2[]; lista text; naonulo text; grupos bigint; sobra bigint;
BEGIN
  IF modo NOT IN ('abortar', 'guardar') THEN
    RAISE EXCEPTION 'nao_numericos deve ser abortar ou guardar (veio: %)', modo;
  END IF;
  IF to_regclass('users') IS NULL THEN
    RAISE EXCEPTION 'schema % não tem a tabela users: é o schema certo?', current_schema();
  END IF;
  FOR r IN SELECT * FROM cg_ajuste_alvo LOOP
    SELECT format_type(a.atttypid, a.atttypmod) INTO atual
      FROM pg_attribute a WHERE a.attrelid = to_regclass(r.tabela) AND a.attname = r.coluna AND NOT a.attisdropped;
    IF atual IS NULL THEN
      RAISE EXCEPTION 'coluna %.% não existe no schema %', r.tabela, r.coluna, current_schema();
    END IF;
    IF r.esperado = 'bigint' AND atual = 'text' THEN
      EXECUTE format($q$SELECT count(*) FILTER (WHERE %1$I IS NOT NULL AND btrim(%1$I) <> ''
                                  AND (%1$I !~ '^\s*-?\d{1,18}\s*$')),
                              count(*) FILTER (WHERE %1$I ~ '^\s*-?0\d' OR %1$I ~ '^\s|\s$')
                        FROM %2$I$q$, r.coluna, r.tabela) INTO ruins, zeros;
      IF ruins > 0 THEN
        problemas := problemas || format(E'\n  %s.%s: %s valor(es) que não são número inteiro', r.tabela, r.coluna, ruins);
      END IF;
      IF zeros > 0 THEN
        RAISE NOTICE '%.%: % valor(es) numéricos com zero à esquerda ou espaço (convertem, mas o texto muda)', r.tabela, r.coluna, zeros;
      END IF;
    END IF;
  END LOOP;
  -- UNIQUE do código ainda sem índice único nas colunas dele: as linhas
  -- repetidas impediriam criá-lo. Conta como o índice do PostgreSQL conta:
  -- linha com NULL numa das colunas não repete nada. Tabela que não existe, o
  -- código a cria já com o UNIQUE.
  -- As colunas de um índice (`indkey`, int2vector) se comparam pelo TEXTO: o
  -- `indkey::int2[]` começa no 0, e array com outro limite nunca é igual.
  FOR u IN SELECT * FROM cg_ajuste_unico LOOP
    CONTINUE WHEN to_regclass(u.tabela) IS NULL;
    SELECT array_agg(a.attnum ORDER BY k.ord) INTO chave
      FROM unnest(u.colunas) WITH ORDINALITY k(nome, ord)
      JOIN pg_attribute a ON a.attrelid = to_regclass(u.tabela) AND a.attname = k.nome AND NOT a.attisdropped;
    IF coalesce(cardinality(chave), 0) <> cardinality(u.colunas) THEN
      RAISE EXCEPTION 'a tabela % não tem as colunas % do UNIQUE do código', u.tabela, u.colunas;
    END IF;
    CONTINUE WHEN EXISTS (SELECT 1 FROM pg_index i
                           WHERE i.indrelid = to_regclass(u.tabela) AND i.indisunique
                             AND i.indpred IS NULL AND i.indexprs IS NULL AND string_to_array(i.indkey::text, ' ')::int2[] = chave);
    SELECT string_agg(format('%I', c), ', ' ORDER BY o),
           string_agg(format('%I IS NOT NULL', c), ' AND ' ORDER BY o)
      INTO lista, naonulo FROM unnest(u.colunas) WITH ORDINALITY x(c, o);
    EXECUTE format('SELECT count(*), coalesce(sum(n - 1), 0) FROM (SELECT count(*) AS n FROM %I WHERE %s GROUP BY %s HAVING count(*) > 1) d',
                   u.tabela, naonulo, lista) INTO grupos, sobra;
    IF grupos > 0 THEN
      problemas := problemas || format(E'\n  %s: %s linha(s) repetida(s) na chave do UNIQUE (%s), em %s grupo(s)', u.tabela, sobra, lista, grupos);
    END IF;
  END LOOP;
  IF problemas <> '' AND modo = 'abortar' THEN
    RAISE EXCEPTION E'AJUSTE ABORTADO, NADA FOI ALTERADO. Valores que não convertem para o tipo do código, e linhas repetidas na chave de um UNIQUE do código:%\nDecisão do oficial: rodar de novo com -v nao_numericos=guardar (guarda os valores em cg_ajuste_guardados e põe NULL; das repetidas fica a de menor id, e as outras vão inteiras para cg_ajuste_guardados).', problemas;
  ELSIF problemas <> '' THEN
    RAISE NOTICE E'Modo guardar: estes valores vão para cg_ajuste_guardados e a coluna fica NULL (das linhas repetidas fica a de menor id; as outras vão inteiras para cg_ajuste_guardados):%', problemas;
  END IF;

  -- login: nomes que só diferem por maiúsculas/minúsculas impedem o índice único NOCASE
  IF to_regcollation('public.cg_nocase') IS NULL THEN
    CREATE COLLATION IF NOT EXISTS public.cg_nocase (provider = icu, locale = 'und-u-ks-level2', deterministic = false);
    RAISE NOTICE 'collation public.cg_nocase criada (não existia)';
  END IF;
  SELECT count(*) INTO ruins FROM (
    SELECT 1 FROM users GROUP BY username COLLATE public.cg_nocase HAVING count(*) > 1) d;
  IF ruins > 0 THEN
    RAISE EXCEPTION 'AJUSTE ABORTADO, NADA FOI ALTERADO: % nome(s) de usuário que só se diferenciam por maiúsculas/minúsculas. Resolva na tela de usuários antes.', ruins;
  END IF;
END $pre$;

-- ------------------------------------------------- 1. valores que não convertem
-- Só no modo guardar. Idempotente: a chave impede guardar duas vezes, e depois
-- da conversão a coluna já é bigint e não entra mais aqui.
DO $guarda$
DECLARE r record; atual text; n bigint;
BEGIN
  IF current_setting('cg.nao_numericos') <> 'guardar' THEN RETURN; END IF;
  CREATE TABLE IF NOT EXISTS cg_ajuste_guardados (
    tabela text NOT NULL, coluna text NOT NULL, linha_id bigint NOT NULL,
    valor_original text, guardado_em timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tabela, coluna, linha_id));
  FOR r IN SELECT * FROM cg_ajuste_alvo WHERE esperado = 'bigint' LOOP
    SELECT format_type(a.atttypid, a.atttypmod) INTO atual
      FROM pg_attribute a WHERE a.attrelid = to_regclass(r.tabela) AND a.attname = r.coluna AND NOT a.attisdropped;
    CONTINUE WHEN atual <> 'text';
    EXECUTE format($q$INSERT INTO cg_ajuste_guardados (tabela, coluna, linha_id, valor_original)
                      SELECT %1$L, %2$L, id, %2$I FROM %1$I
                       WHERE %2$I IS NOT NULL AND btrim(%2$I) <> '' AND %2$I !~ '^\s*-?\d{1,18}\s*$'
                      ON CONFLICT DO NOTHING$q$, r.tabela, r.coluna);
    EXECUTE format($q$UPDATE %1$I SET %2$I = NULL
                       WHERE %2$I IS NOT NULL AND btrim(%2$I) <> '' AND %2$I !~ '^\s*-?\d{1,18}\s*$'$q$, r.tabela, r.coluna);
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n > 0 THEN RAISE NOTICE '%.%: % valor(es) guardado(s) em cg_ajuste_guardados e anulado(s)', r.tabela, r.coluna, n; END IF;
  END LOOP;
END $guarda$;

-- 1b. ri_atos.lavrado_por: login -> id (pedido junto da decisão do oficial, 18/10/2026)
-- Só no modo guardar. Quando o valor guardado de ri_atos.lavrado_por é o LOGIN
-- de exatamente UM usuário (comparando como o login: sem diferenciar
-- maiúsculas/minúsculas, collation public.cg_nocase, e sem espaços nas pontas),
-- a coluna recebe o id desse usuário em vez de ficar NULL. O valor original
-- continua em cg_ajuste_guardados (rastreio). Medido em 16/10: 1 linha, usuário id 3.
-- Roda depois do bloco 1 e antes da conversão de tipo; a coluna ainda é texto,
-- então o id entra como texto e o bloco 2 o converte para bigint. Idempotente:
-- depois da conversão a coluna já é bigint e o bloco não faz nada; e só
-- preenche linhas que estão NULL.
DO $lavrado$
DECLARE n bigint;
BEGIN
  IF current_setting('cg.nao_numericos') <> 'guardar' THEN RETURN; END IF;
  IF (SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a
       WHERE a.attrelid = to_regclass('ri_atos') AND a.attname = 'lavrado_por' AND NOT a.attisdropped) <> 'text' THEN
    RETURN;
  END IF;
  UPDATE ri_atos t SET lavrado_por = u.id::text
    FROM cg_ajuste_guardados g
    JOIN LATERAL (SELECT min(x.id) AS id, count(*) AS qtd FROM users x
                   WHERE btrim(x.username) COLLATE public.cg_nocase = btrim(g.valor_original) COLLATE public.cg_nocase) u
      ON u.qtd = 1
   WHERE g.tabela = 'ri_atos' AND g.coluna = 'lavrado_por' AND g.linha_id = t.id
     AND t.lavrado_por IS NULL;
  GET DIAGNOSTICS n = ROW_COUNT;
  RAISE NOTICE 'ri_atos.lavrado_por: % linha(s) com login de usuário receberam o id (valor original segue em cg_ajuste_guardados)', n;
END $lavrado$;

-- ------------------------------------------------------------------ 2. tipos
DO $tipos$
DECLARE r record; atual text;
BEGIN
  FOR r IN SELECT * FROM cg_ajuste_alvo LOOP
    SELECT format_type(a.atttypid, a.atttypmod) INTO atual
      FROM pg_attribute a WHERE a.attrelid = to_regclass(r.tabela) AND a.attname = r.coluna AND NOT a.attisdropped;
    CONTINUE WHEN atual = r.esperado;
    IF r.esperado = 'bigint' THEN
      EXECUTE format('ALTER TABLE %I ALTER COLUMN %I TYPE bigint USING nullif(btrim(%I), '''')::bigint',
                     r.tabela, r.coluna, r.coluna);
    ELSIF r.esperado = 'text' THEN
      EXECUTE format('ALTER TABLE %I ALTER COLUMN %I TYPE text USING %I::text', r.tabela, r.coluna, r.coluna);
    END IF;
    RAISE NOTICE 'tipo: %.%  % -> %', r.tabela, r.coluna, atual, r.esperado;
  END LOOP;
END $tipos$;

-- ---------------------------------------------- 3. as 2 FKs que o código declara
DO $fks$
DECLARE r record; orfas bigint;
BEGIN
  FOR r IN SELECT * FROM (VALUES ('ri_atos', 'lavrado_por', 'ri_atos_lavrado_por_fkey'),
                                 ('ri_matriculas', 'criado_por', 'ri_matriculas_criado_por_fkey')) v(tabela, coluna, nome) LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_constraint k
                    WHERE k.conrelid = to_regclass(r.tabela) AND k.contype = 'f'
                      AND k.confrelid = to_regclass('users')
                      AND k.conkey = ARRAY[(SELECT attnum FROM pg_attribute
                                             WHERE attrelid = to_regclass(r.tabela) AND attname = r.coluna)]) THEN
      EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES users(id) NOT VALID',
                     r.tabela, r.nome, r.coluna);
      RAISE NOTICE 'FK criada (NOT VALID): %.% -> users(id)', r.tabela, r.coluna;
    END IF;
    EXECUTE format('SELECT count(*) FROM %I t WHERE t.%I IS NOT NULL AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = t.%I)',
                   r.tabela, r.coluna, r.coluna) INTO orfas;
    IF orfas = 0 THEN
      IF EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = to_regclass(r.tabela) AND conname = r.nome AND NOT convalidated) THEN
        EXECUTE format('ALTER TABLE %I VALIDATE CONSTRAINT %I', r.tabela, r.nome);
        RAISE NOTICE 'FK validada: %', r.nome;
      END IF;
    ELSE
      RAISE NOTICE 'FK % fica NOT VALID: % linha(s) órfã(s)', r.nome, orfas;
    END IF;
  END LOOP;
END $fks$;

-- ------------------------------------------ 3b. os UNIQUE que o código declara
-- Com o NOME do código, porque é por nome que se confere o esquema (e é o nome
-- que aparece no erro de quem gravar a repetida). Na ordem:
--   1) já tem o nome do código: nada a fazer (é a segunda rodada);
--   2) a mesma chave já é UNIQUE com outro nome (a carga encurta com hash):
--      renomeia — não lê nem muda linha nenhuma;
--   3) há índice único nessas colunas sem restrição: vira a restrição;
--   4) não há nada único: no modo guardar, fica a linha de MENOR id de cada
--      grupo repetido (é a que o código lê primeiro: `ORDER BY id LIMIT 1` do
--      ri_cnib.resolver_ocorrencia) e as outras vão INTEIRAS para
--      cg_ajuste_guardados (coluna '*', a linha em JSON, restaurável com
--      json_populate_record) antes de saírem; no abortar a pré-checagem já
--      parou se havia repetida. Cria o UNIQUE, e apaga o índice comum das
--      mesmas colunas que a carga põe no lugar do único que não entrou.
DO $unicos$
DECLARE u record; chave int2[]; lista text; naonulo text; existente text; n bigint; idx record;
BEGIN
  FOR u IN SELECT * FROM cg_ajuste_unico LOOP
    CONTINUE WHEN to_regclass(u.tabela) IS NULL;
    CONTINUE WHEN EXISTS (SELECT 1 FROM pg_constraint
                           WHERE conrelid = to_regclass(u.tabela) AND conname = u.nome AND contype = 'u');
    SELECT array_agg(a.attnum ORDER BY k.ord) INTO chave
      FROM unnest(u.colunas) WITH ORDINALITY k(nome, ord)
      JOIN pg_attribute a ON a.attrelid = to_regclass(u.tabela) AND a.attname = k.nome AND NOT a.attisdropped;
    SELECT string_agg(format('%I', c), ', ' ORDER BY o),
           string_agg(format('%I IS NOT NULL', c), ' AND ' ORDER BY o)
      INTO lista, naonulo FROM unnest(u.colunas) WITH ORDINALITY x(c, o);

    SELECT k.conname INTO existente FROM pg_constraint k
     WHERE k.conrelid = to_regclass(u.tabela) AND k.contype = 'u' AND k.conkey = chave
     ORDER BY k.conname LIMIT 1;
    IF existente IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %I RENAME CONSTRAINT %I TO %I', u.tabela, existente, u.nome);
      RAISE NOTICE 'UNIQUE de % (%): % renomeado para %', u.tabela, lista, existente, u.nome;
      CONTINUE;
    END IF;

    SELECT c.relname INTO existente FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
     WHERE i.indrelid = to_regclass(u.tabela) AND i.indisunique
       AND i.indpred IS NULL AND i.indexprs IS NULL AND string_to_array(i.indkey::text, ' ')::int2[] = chave
       AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid = i.indexrelid)
     ORDER BY c.relname LIMIT 1;
    IF existente IS NOT NULL THEN
      EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I UNIQUE USING INDEX %I', u.tabela, u.nome, existente);
      RAISE NOTICE 'UNIQUE de % (%): o índice único % virou a restrição %', u.tabela, lista, existente, u.nome;
      CONTINUE;
    END IF;

    IF current_setting('cg.nao_numericos') = 'guardar' THEN
      EXECUTE format($q$WITH r AS (SELECT id, row_number() OVER (PARTITION BY %2$s ORDER BY id) AS ordem
                                     FROM %1$I WHERE %3$s)
                        INSERT INTO cg_ajuste_guardados (tabela, coluna, linha_id, valor_original)
                        SELECT %1$L, '*', t.id, row_to_json(t)::text FROM %1$I t JOIN r ON r.id = t.id
                         WHERE r.ordem > 1
                        ON CONFLICT DO NOTHING$q$, u.tabela, lista, naonulo);
      EXECUTE format($q$WITH r AS (SELECT id, row_number() OVER (PARTITION BY %2$s ORDER BY id) AS ordem
                                     FROM %1$I WHERE %3$s)
                        DELETE FROM %1$I t USING r WHERE r.id = t.id AND r.ordem > 1$q$, u.tabela, lista, naonulo);
      GET DIAGNOSTICS n = ROW_COUNT;
      IF n > 0 THEN
        RAISE NOTICE '%: % linha(s) repetida(s) na chave (%) guardada(s) inteira(s) em cg_ajuste_guardados e apagada(s); ficou a de menor id de cada grupo',
                     u.tabela, n, lista;
      END IF;
    END IF;
    EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I UNIQUE (%s)', u.tabela, u.nome, lista);
    RAISE NOTICE 'UNIQUE de % (%) criado: %', u.tabela, lista, u.nome;
    FOR idx IN SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
                WHERE i.indrelid = to_regclass(u.tabela) AND NOT i.indisunique
                  AND i.indpred IS NULL AND i.indexprs IS NULL AND string_to_array(i.indkey::text, ' ')::int2[] = chave
                  AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid = i.indexrelid)
                ORDER BY c.relname LOOP
      EXECUTE format('DROP INDEX %I', idx.relname);
      RAISE NOTICE 'índice comum % (as mesmas colunas, posto pela carga no lugar do único) apagado', idx.relname;
    END LOOP;
  END LOOP;
END $unicos$;

-- ------------------------------------------------------- 4. collation do login
DO $login$
BEGIN
  IF (SELECT attcollation FROM pg_attribute WHERE attrelid = to_regclass('users') AND attname = 'username')
       <> to_regcollation('public.cg_nocase') THEN
    -- recria sozinho o índice único users_username_key, agora sem distinguir maiúsculas
    ALTER TABLE users ALTER COLUMN username TYPE text COLLATE public.cg_nocase;
    RAISE NOTICE 'users.username agora COLLATE public.cg_nocase (índice único recriado)';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
                  WHERE i.indrelid = to_regclass('users') AND i.indisunique
                    AND i.indkey[0] = (SELECT attnum FROM pg_attribute WHERE attrelid = to_regclass('users') AND attname = 'username')
                    AND i.indcollation[0] = to_regcollation('public.cg_nocase')) THEN
    ALTER TABLE users ADD CONSTRAINT users_username_key UNIQUE (username);
    RAISE NOTICE 'índice único de users.username criado';
  END IF;
END $login$;

-- ------------------------------------------------------------- 5. sequências
-- Toda coluna identity/serial do schema: o próximo id passa do maior que existe.
-- Tabela vazia: setval(seq, 1, false) -> o próximo é 1. NUNCA abaixa uma
-- sequência que já está à frente (como o AUTOINCREMENT do SQLite, id apagado
-- não volta a ser usado).
DO $seq$
DECLARE r record; maior bigint; ultimo bigint; chamado boolean; n int := 0;
BEGIN
  FOR r IN SELECT c.relname tabela, a.attname coluna, pg_get_serial_sequence(format('%I.%I', current_schema(), c.relname), a.attname) seq
             FROM pg_class c JOIN pg_attribute a ON a.attrelid = c.oid
            WHERE c.relnamespace = current_schema()::regnamespace AND c.relkind = 'r'
              AND a.attnum > 0 AND NOT a.attisdropped
              AND pg_get_serial_sequence(format('%I.%I', current_schema(), c.relname), a.attname) IS NOT NULL LOOP
    EXECUTE format('SELECT max(%I) FROM %I', r.coluna, r.tabela) INTO maior;
    EXECUTE format('SELECT last_value, is_called FROM %s', r.seq) INTO ultimo, chamado;
    IF maior IS NULL THEN
      IF chamado THEN CONTINUE; END IF;            -- já usada e tabela esvaziada: não volta
      PERFORM setval(r.seq, 1, false);
    ELSIF NOT chamado OR ultimo < maior THEN
      PERFORM setval(r.seq, greatest(maior, 1), true);
      n := n + 1;
    END IF;
  END LOOP;
  RAISE NOTICE 'sequências ajustadas: %', n;
END $seq$;

-- ------------------------------------------------------------- 6. conferência
\echo '== conferência: tipos esperados x atuais'
SELECT t.tabela || '.' || t.coluna AS coluna, t.esperado,
       format_type(a.atttypid, a.atttypmod) AS atual,
       CASE WHEN format_type(a.atttypid, a.atttypmod) = t.esperado THEN 'OK' ELSE 'DIFERENTE' END AS situacao
  FROM cg_ajuste_alvo t JOIN pg_attribute a ON a.attrelid = to_regclass(t.tabela) AND a.attname = t.coluna
 ORDER BY 1;
DO $conf_tipos$
DECLARE ok int; total int;
BEGIN
  SELECT count(*) FILTER (WHERE format_type(a.atttypid, a.atttypmod) = t.esperado), count(*) INTO ok, total
    FROM cg_ajuste_alvo t JOIN pg_attribute a ON a.attrelid = to_regclass(t.tabela) AND a.attname = t.coluna AND NOT a.attisdropped;
  RAISE NOTICE 'tipos: % de % OK', ok, total;
  IF ok <> total OR total <> (SELECT count(*) FROM cg_ajuste_alvo) THEN
    RAISE EXCEPTION 'há coluna com tipo diferente do esperado: ajuste não confirmado';
  END IF;
END $conf_tipos$;

\echo '== conferência: collation e índice único do login'
SELECT a.attcollation::regcollation AS collation_username,
       (SELECT string_agg(c.relname || CASE WHEN i.indisunique THEN ' (único, ' ELSE ' (' END
                          || i.indcollation[0]::regcollation::text || ')', ', ')
          FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
         WHERE i.indrelid = to_regclass('users')
           AND i.indkey[0] = a.attnum) AS indices
  FROM pg_attribute a WHERE a.attrelid = to_regclass('users') AND a.attname = 'username';

\echo '== conferência: FKs para users recriadas'
SELECT conrelid::regclass AS tabela, conname, convalidated AS validada
  FROM pg_constraint WHERE conname IN ('ri_atos_lavrado_por_fkey', 'ri_matriculas_criado_por_fkey')
   AND connamespace = current_schema()::regnamespace ORDER BY 1;

\echo '== conferência: UNIQUE que o código declara (nome e colunas)'
SELECT u.tabela, u.nome,
       (SELECT pg_get_constraintdef(k.oid) FROM pg_constraint k
         WHERE k.conrelid = to_regclass(u.tabela) AND k.conname = u.nome AND k.contype = 'u') AS definicao
  FROM cg_ajuste_unico u ORDER BY 1, 2;
DO $conf_unicos$
DECLARE u record; feito text; esperado text;
BEGIN
  FOR u IN SELECT * FROM cg_ajuste_unico LOOP
    CONTINUE WHEN to_regclass(u.tabela) IS NULL;
    SELECT pg_get_constraintdef(k.oid) INTO feito FROM pg_constraint k
     WHERE k.conrelid = to_regclass(u.tabela) AND k.conname = u.nome AND k.contype = 'u';
    SELECT format('UNIQUE (%s)', string_agg(format('%I', c), ', ' ORDER BY o)) INTO esperado
      FROM unnest(u.colunas) WITH ORDINALITY x(c, o);
    IF feito IS DISTINCT FROM esperado THEN
      RAISE EXCEPTION 'UNIQUE % de %: esperado %, achado %: ajuste não confirmado', u.nome, u.tabela, esperado, coalesce(feito, 'nenhum');
    END IF;
    RAISE NOTICE 'UNIQUE OK: %.% = %', u.tabela, u.nome, feito;
  END LOOP;
END $conf_unicos$;

\echo '== conferência: órfãs em TODAS as FKs do schema (só as que têm)'
DO $orf$
DECLARE r record; n bigint; total int := 0;
BEGIN
  FOR r IN SELECT k.conrelid::regclass rel, k.confrelid::regclass ref, k.conname,
                  (SELECT attname FROM pg_attribute WHERE attrelid = k.conrelid AND attnum = k.conkey[1]) col,
                  (SELECT attname FROM pg_attribute WHERE attrelid = k.confrelid AND attnum = k.confkey[1]) refcol
             FROM pg_constraint k
            WHERE k.contype = 'f' AND k.connamespace = current_schema()::regnamespace AND array_length(k.conkey, 1) = 1 LOOP
    EXECUTE format('SELECT count(*) FROM %s t WHERE t.%I IS NOT NULL AND NOT EXISTS (SELECT 1 FROM %s r WHERE r.%I = t.%I)',
                   r.rel, r.col, r.ref, r.refcol, r.col) INTO n;
    total := total + 1;
    IF n > 0 THEN RAISE NOTICE 'órfãs: %.% -> % : % linha(s)', r.rel, r.col, r.ref, n; END IF;
  END LOOP;
  RAISE NOTICE 'FKs conferidas: %', total;
END $orf$;

\echo '== conferência: sequências (todas devem estar >= MAX(id))'
DO $conf_seq$
DECLARE r record; maior bigint; ultimo bigint; chamado boolean; ok int := 0; ruim int := 0;
BEGIN
  FOR r IN SELECT c.relname tabela, a.attname coluna, pg_get_serial_sequence(format('%I.%I', current_schema(), c.relname), a.attname) seq
             FROM pg_class c JOIN pg_attribute a ON a.attrelid = c.oid
            WHERE c.relnamespace = current_schema()::regnamespace AND c.relkind = 'r' AND a.attnum > 0
              AND pg_get_serial_sequence(format('%I.%I', current_schema(), c.relname), a.attname) IS NOT NULL LOOP
    EXECUTE format('SELECT max(%I) FROM %I', r.coluna, r.tabela) INTO maior;
    EXECUTE format('SELECT last_value, is_called FROM %s', r.seq) INTO ultimo, chamado;
    IF maior IS NULL OR (chamado AND ultimo >= maior) THEN ok := ok + 1;
    ELSE ruim := ruim + 1; RAISE NOTICE 'sequência atrás: %.% (max %, seq %)', r.tabela, r.coluna, maior, ultimo; END IF;
  END LOOP;
  RAISE NOTICE 'sequências: % à frente do MAX(id) (ou tabela vazia), % atrás', ok, ruim;
  IF ruim > 0 THEN RAISE EXCEPTION 'há sequência atrás do MAX(id): ajuste não confirmado'; END IF;
END $conf_seq$;

\echo '== conferência: valores guardados (modo guardar)'
DO $guard$
DECLARE r record;
BEGIN
  IF to_regclass('cg_ajuste_guardados') IS NULL THEN
    RAISE NOTICE 'cg_ajuste_guardados não existe: nenhum valor foi guardado';
    RETURN;
  END IF;
  FOR r IN EXECUTE 'SELECT tabela, coluna, count(*) n FROM cg_ajuste_guardados GROUP BY 1, 2 ORDER BY 1, 2' LOOP
    RAISE NOTICE 'guardados: %.% = % linha(s)%', r.tabela, r.coluna, r.n,
                 CASE WHEN r.coluna = '*' THEN ' (linhas inteiras, repetidas na chave de um UNIQUE do código)' ELSE '' END;
  END LOOP;
  FOR r IN EXECUTE 'SELECT count(*) n FROM cg_ajuste_guardados' LOOP
    RAISE NOTICE 'guardados: TOTAL = % linha(s) (esperado no banco de 16/10/2026: 2.024 = 2.018 + 6 de audit_logs.entity_id; no dia da virada pode ser um pouco maior)', r.n;
  END LOOP;
  FOR r IN EXECUTE $q$SELECT t.lavrado_por AS id, count(*) n FROM cg_ajuste_guardados g
                       JOIN ri_atos t ON t.id = g.linha_id
                      WHERE g.tabela = 'ri_atos' AND g.coluna = 'lavrado_por' AND t.lavrado_por IS NOT NULL
                      GROUP BY 1 ORDER BY 1$q$ LOOP
    RAISE NOTICE 'ri_atos.lavrado_por guardado e preenchido pelo login: usuário id % = % linha(s)', r.id, r.n;
  END LOOP;
END $guard$;

COMMIT;
\echo '== ajuste_pos_migracao.sql: CONCLUÍDO'
