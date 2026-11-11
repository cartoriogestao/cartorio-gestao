-- Travas da produção. O oficial roda isto no PostgreSQL do Windows, com um
-- superusuário, DEPOIS de aprovar o plano. Este arquivo não é aplicado pelo
-- sistema nem por este repositório sozinho.
--
--   psql -h 127.0.0.1 -p 5434 -d cartorio -f installer/sql/travas_da_producao.sql
--
-- Idempotente. Se uma tentativa anterior parou no erro
-- «filter value TRUNCATE not recognized», rode de novo: o que faltou entra agora.
--
-- Antes: confira que producao.nu_ferj_ferc_aviso_dispensa não existe.
-- nu_avisos_gestao.py ainda faz DROP TABLE IF EXISTS nela ao preparar o banco.
-- Se a tabela existir, a trava recusa e a preparação para. Apague-a antes.
--
-- O PostgreSQL não tem gatilho de evento para TRUNCATE. Esvaziar a tabela da
-- casa é recusado por um gatilho comum, em cada tabela do schema, e também
-- nas tabelas criadas depois. A publicação, à parte, não leva esvaziamento.

\set ON_ERROR_STOP on

-- 1. O log passa a guardar DDL e conexões. Vale para conexões novas, sem
--    reiniciar o serviço. Não guarda o texto de cada SELECT.
ALTER SYSTEM SET log_statement = 'ddl';
ALTER SYSTEM SET log_connections = on;
ALTER SYSTEM SET log_disconnections = on;
SELECT pg_reload_conf();

-- 2. A marca de somente leitura da contingência. Fica em public, fora da
--    publicação do schema da casa, para não viajar até a reserva.
CREATE TABLE IF NOT EXISTS public.cg_contingencia (
    chave text PRIMARY KEY,
    valor text NOT NULL,
    desde timestamptz NOT NULL DEFAULT now()
);

-- 3. cg sem DDL destrutivo. O papel continua podendo criar coluna quando uma
--    versão nova sobe (senão a atualização para). O que ele não pode é apagar
--    o schema da casa, apagar tabela dela ou esvaziá-la. O gatilho vale também
--    para o dono: REVOKE não tira o direito de quem é dono.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cg') THEN
    ALTER ROLE cg NOSUPERUSER NOCREATEDB NOCREATEROLE;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cg_sistema') THEN
    ALTER ROLE cg_sistema NOSUPERUSER NOCREATEDB NOCREATEROLE;
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cg') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON public.cg_contingencia TO cg;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cg_sistema') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON public.cg_contingencia TO cg_sistema;
  END IF;
END $$;

CREATE OR REPLACE FUNCTION public.cg_recusar_ddl_destrutivo()
RETURNS event_trigger
LANGUAGE plpgsql
AS $$
DECLARE
  obj record;
BEGIN
  IF tg_event = 'sql_drop' THEN
    FOR obj IN SELECT * FROM pg_event_trigger_dropped_objects()
    LOOP
      IF obj.object_type = 'schema' AND obj.object_name IN ('producao', 'public') THEN
        RAISE EXCEPTION 'recusado: apagar o schema %', obj.object_name;
      END IF;
      IF obj.object_type = 'table' AND obj.schema_name IN ('producao', 'public') THEN
        RAISE EXCEPTION 'recusado: apagar a tabela %.%', obj.schema_name, obj.object_name;
      END IF;
    END LOOP;
  END IF;
END $$;

-- O nome antigo era um gatilho de evento em TRUNCATE, que o PostgreSQL recusa.
DROP EVENT TRIGGER IF EXISTS cg_recusar_truncate;

DROP EVENT TRIGGER IF EXISTS cg_recusar_drop;
CREATE EVENT TRIGGER cg_recusar_drop
  ON sql_drop
  EXECUTE FUNCTION public.cg_recusar_ddl_destrutivo();

CREATE OR REPLACE FUNCTION public.cg_recusar_esvaziar()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'recusado: esvaziar tabela no banco da produção';
END $$;

CREATE OR REPLACE FUNCTION public.cg_ligar_trava_de_esvaziar()
RETURNS event_trigger
LANGUAGE plpgsql
AS $$
DECLARE
  cmd record;
BEGIN
  FOR cmd IN
    SELECT schema_name, object_type, objid
      FROM pg_event_trigger_ddl_commands()
     WHERE object_type = 'table' AND schema_name = 'producao'
  LOOP
    IF NOT EXISTS (
      SELECT 1 FROM pg_trigger
       WHERE tgrelid = cmd.objid AND tgname = 'cg_recusar_esvaziar'
    ) THEN
      EXECUTE format(
        'CREATE TRIGGER cg_recusar_esvaziar BEFORE TRUNCATE ON %s '
        'FOR EACH STATEMENT EXECUTE FUNCTION public.cg_recusar_esvaziar()',
        cmd.objid::regclass);
    END IF;
  END LOOP;
END $$;

DROP EVENT TRIGGER IF EXISTS cg_ligar_trava_de_esvaziar;
CREATE EVENT TRIGGER cg_ligar_trava_de_esvaziar
  ON ddl_command_end
  WHEN TAG IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
  EXECUTE FUNCTION public.cg_ligar_trava_de_esvaziar();

-- Tabelas que já existem quando o oficial roda o arquivo.
DO $$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT n.nspname, c.relname
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'producao' AND c.relkind IN ('r', 'p')
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS cg_recusar_esvaziar ON %I.%I', r.nspname, r.relname);
    EXECUTE format(
      'CREATE TRIGGER cg_recusar_esvaziar BEFORE TRUNCATE ON %I.%I '
      'FOR EACH STATEMENT EXECUTE FUNCTION public.cg_recusar_esvaziar()',
      r.nspname, r.relname);
  END LOOP;
END $$;

-- 4. A publicação deixa de levar o esvaziamento de tabela. Se a publicação
--    ainda não existe, o sql-do-principal de tools/reserva.py a cria já assim.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'cg_reserva') THEN
    ALTER PUBLICATION cg_reserva SET (publish = 'insert, update, delete');
  END IF;
END $$;
