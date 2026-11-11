-- Travas da produção. O oficial roda isto no PostgreSQL do Windows, com um
-- superusuário, DEPOIS de aprovar o plano. Este arquivo não é aplicado pelo
-- sistema nem por este repositório sozinho.
--
--   psql -h 127.0.0.1 -p 5434 -d cartorio -f installer/sql/travas_da_producao.sql
--
-- Idempotente.

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
  IF tg_tag = 'TRUNCATE' THEN
    RAISE EXCEPTION 'recusado: esvaziar tabela no banco da produção';
  END IF;
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

DROP EVENT TRIGGER IF EXISTS cg_recusar_truncate;
CREATE EVENT TRIGGER cg_recusar_truncate
  ON ddl_command_start
  WHEN TAG IN ('TRUNCATE')
  EXECUTE FUNCTION public.cg_recusar_ddl_destrutivo();

DROP EVENT TRIGGER IF EXISTS cg_recusar_drop;
CREATE EVENT TRIGGER cg_recusar_drop
  ON sql_drop
  EXECUTE FUNCTION public.cg_recusar_ddl_destrutivo();

-- 4. A publicação deixa de levar o esvaziamento de tabela. Se a publicação
--    ainda não existe, o sql-do-principal de tools/reserva.py a cria já assim.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'cg_reserva') THEN
    ALTER PUBLICATION cg_reserva SET (publish = 'insert, update, delete');
  END IF;
END $$;
