-- =============================================================================
-- banco_pg_funcoes.sql — as funções do SQLite que o código usa dentro do SQL,
-- EMULADAS no PostgreSQL 18, com o MESMO resultado (texto no mesmo formato).
--
-- Desenho: PLANO.md, seção «Funções do SQLite emuladas no PostgreSQL».
-- Instalação: UMA VEZ por banco, com `SET search_path TO public` antes. Nada
-- aqui é qualificado com schema; tudo é CREATE OR REPLACE ou guardado por
-- teste de existência — rodar duas vezes não dá erro nem muda nada.
--
-- A RÉGUA É O SQLITE QUE O SISTEMA USA HOJE: 3.45.1, o do Python 3.11.9 da
-- migração (sqlite3.sqlite_version). O código de data foi reproduzido a partir
-- do date.c dessa versão — o mesmo estado (Y/M/D válidos, H/M/S válidos, dia
-- juliano em milissegundos, fuso) e as mesmas contas em ponto flutuante —, e
-- não por aproximação com os tipos de data do PostgreSQL. É por isso que
-- `datetime('2024-01-01 24:00')` continua dando '2024-01-01 24:00:00' e
-- `date('2023-02-31','start of month')` continua dando '2023-02-01', como lá.
-- O teste tests/test_banco_pg_funcoes.py compara as duas, entrada por entrada.
--
-- Formatos de strftime: os da 3.45.1, medidos um a um contra ela —
-- %d %e %f %F %H %I %j %J %k %l %m %M %p %P %R %s %S %T %u %w %W %Y %%.
-- Qualquer outro (%G %g %U %V, que nasceram na 3.46) devolve NULL, como lá.
--
-- DUAS ARMADILHAS DO POSTGRESQL QUE ESTE ARQUIVO NÃO RESOLVE SOZINHO:
--  1. `date('2026-01-01')` e `time('10:00')` com UM argumento LITERAL (ou
--     parâmetro ligado no cliente, que vira literal) NÃO chamam a função: o
--     PostgreSQL lê como conversão para o tipo date/time («function-style
--     cast»), e devolve tipo date/time, no fuso da sessão para 'now'. Com
--     coluna texto, ou com dois argumentos ou mais, a função é chamada.
--     Saída: o tradutor troca `date(`/`time(` por `cg_date(`/`cg_time(`, que
--     são idênticas e não têm nome de tipo.
--  2. `char(10)` não pode existir como função (CHAR é palavra reservada da
--     gramática); o tradutor troca por `chr(10)`.
-- =============================================================================


-- ---------------------------------------------------------------- extensão
-- Pedida pelo desenho. A normalização de nome NÃO a usa (ver nome_da_casa):
-- unaccent troca ß por ss, æ por ae e ø por o, e a função do Python não.
DO $do$
BEGIN
  CREATE EXTENSION IF NOT EXISTS unaccent SCHEMA public;
EXCEPTION WHEN OTHERS THEN
  RAISE WARNING 'unaccent não instalada (%): nada deste arquivo depende dela', SQLERRM;
END
$do$;


-- ------------------------------------------------- o estado do date.c (DateTime)
DO $do$
BEGIN
  IF to_regtype('cg_sqlite_dt') IS NULL THEN
    CREATE TYPE cg_sqlite_dt AS (
      ijd        bigint,            -- dia juliano × 86.400.000 (milissegundos)
      valid_jd   boolean,
      y          integer,
      mo         integer,
      d          integer,
      valid_ymd  boolean,
      h          integer,
      mi         integer,
      s          double precision,  -- segundos com fração
      valid_hms  boolean,
      tz         integer,           -- minutos
      raw_s      boolean,           -- `s` guarda um número cru ainda não interpretado
      is_utc     boolean,           -- o «tzSet» da 3.45: fuso já resolvido ('utc' vira nada)
      is_local   boolean,           -- (reservado; a 3.45 não o tem)
      use_subsec boolean
    );
  END IF;
END
$do$;


CREATE OR REPLACE FUNCTION _cg_dt_vazio() RETURNS cg_sqlite_dt
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT ROW(0::bigint, false, 0, 0, 0, false, 0, 0, 0::float8, false, 0,
             false, false, false, false)::cg_sqlite_dt
$$;


-- computeJD()
CREATE OR REPLACE FUNCTION _cg_dt_jd(p cg_sqlite_dt) RETURNS cg_sqlite_dt
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
  yy bigint; mm bigint; dd bigint; a bigint; b bigint; x1 bigint; x2 bigint;
BEGIN
  IF p IS NULL THEN RETURN NULL; END IF;
  IF p.valid_jd THEN RETURN p; END IF;
  IF p.valid_ymd THEN yy := p.y; mm := p.mo; dd := p.d;
  ELSE yy := 2000; mm := 1; dd := 1;
  END IF;
  IF yy < -4713 OR yy > 9999 OR p.raw_s THEN RETURN NULL; END IF;  -- datetimeError
  IF mm <= 2 THEN yy := yy - 1; mm := mm + 12; END IF;
  a := yy / 100;
  b := 2 - a + (a / 4);
  x1 := 36525 * (yy + 4716) / 100;
  x2 := 306001 * (mm + 1) / 10000;
  p.ijd := trunc(((x1 + x2 + dd + b)::float8 - 1524.5::float8) * 86400000::float8)::bigint;
  p.valid_jd := true;
  IF p.valid_hms THEN
    p.ijd := p.ijd + p.h::bigint * 3600000 + p.mi::bigint * 60000
             + trunc(p.s * 1000::float8 + 0.5::float8)::bigint;
    IF p.tz <> 0 THEN
      p.ijd := p.ijd - p.tz::bigint * 60000;
      p.valid_ymd := false; p.valid_hms := false; p.tz := 0;
    END IF;
  END IF;
  RETURN p;
END
$$;


-- computeYMD()
CREATE OR REPLACE FUNCTION _cg_dt_ymd(p cg_sqlite_dt) RETURNS cg_sqlite_dt
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
  z bigint; a bigint; b bigint; c bigint; dd bigint; e bigint; x1 bigint;
BEGIN
  IF p IS NULL THEN RETURN NULL; END IF;
  IF p.valid_ymd THEN RETURN p; END IF;
  IF NOT p.valid_jd THEN
    p.y := 2000; p.mo := 1; p.d := 1;
  ELSIF NOT (p.ijd >= 0 AND p.ijd <= 464269060799999) THEN
    RETURN NULL;
  ELSE
    z := (p.ijd + 43200000) / 86400000;
    a := trunc((z::float8 - 1867216.25::float8) / 36524.25::float8)::bigint;
    a := z + 1 + a - (a / 4);
    b := a + 1524;
    c := trunc((b::float8 - 122.1::float8) / 365.25::float8)::bigint;
    dd := (36525 * (c & 32767)) / 100;
    e := trunc((b - dd)::float8 / 30.6001::float8)::bigint;
    x1 := trunc(30.6001::float8 * e::float8)::bigint;
    p.d := b - dd - x1;
    p.mo := CASE WHEN e < 14 THEN e - 1 ELSE e - 13 END;
    p.y := CASE WHEN p.mo > 2 THEN c - 4716 ELSE c - 4715 END;
  END IF;
  p.valid_ymd := true;
  RETURN p;
END
$$;


-- computeHMS()
CREATE OR REPLACE FUNCTION _cg_dt_hms(p cg_sqlite_dt) RETURNS cg_sqlite_dt
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
  day_ms bigint; day_min bigint;
BEGIN
  IF p IS NULL THEN RETURN NULL; END IF;
  IF p.valid_hms THEN RETURN p; END IF;
  p := _cg_dt_jd(p);
  IF p IS NULL THEN RETURN NULL; END IF;
  day_ms := (p.ijd + 43200000) % 86400000;
  p.s := (day_ms % 60000)::float8 / 1000.0::float8;
  day_min := day_ms / 60000;
  p.mi := day_min % 60;
  p.h := day_min / 60;
  p.raw_s := false;
  p.valid_hms := true;
  RETURN p;
END
$$;


CREATE OR REPLACE FUNCTION _cg_dt_ymdhms(p cg_sqlite_dt) RETURNS cg_sqlite_dt
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT _cg_dt_hms(_cg_dt_ymd(p))
$$;


-- parseHhMmSs() — `p` é o estado em que se escreve; NULL = não é hora.
CREATE OR REPLACE FUNCTION _cg_dt_hora(p cg_sqlite_dt, z text) RETURNS cg_sqlite_dt
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
  m text[]; hh int; mn int; ss int; ms float8 := 0; escala float8 := 1;
  i int; tzh int; tzm int;
BEGIN
  m := regexp_match(z,
    '^([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:\.([0-9]+))?)?'
    '[\u0009-\u000d ]*(?:([Zz])|([+-])([0-9]{2}):([0-9]{2}))?[\u0009-\u000d ]*$');
  IF m IS NULL THEN RETURN NULL; END IF;
  hh := m[1]::int; mn := m[2]::int; ss := coalesce(m[3]::int, 0);
  IF hh > 24 OR mn > 59 OR ss > 59 THEN RETURN NULL; END IF;
  IF m[4] IS NOT NULL THEN
    BEGIN
      FOR i IN 1..length(m[4]) LOOP
        ms := ms * 10.0::float8 + (ascii(substr(m[4], i, 1)) - 48)::float8;
        escala := escala * 10.0::float8;
      END LOOP;
      ms := ms / escala;
    EXCEPTION WHEN numeric_value_out_of_range THEN
      RETURN NULL;   -- centenas de casas decimais: o SQLite faria inf/inf
    END;
  END IF;
  p.valid_jd := false;
  p.raw_s := false;
  p.valid_hms := true;
  p.h := hh; p.mi := mn; p.s := ss::float8 + ms;
  p.tz := 0;
  -- 'Z' e '+HH:MM' (até '+00:00') marcam o fuso como resolvido: depois
  -- deles o modificador 'utc' não faz nada (tzSet, na 3.45).
  IF m[5] IS NOT NULL THEN
    p.is_utc := true;
  ELSIF m[6] IS NOT NULL THEN
    tzh := m[7]::int; tzm := m[8]::int;
    IF tzh > 14 OR tzm > 59 THEN RETURN NULL; END IF;
    p.tz := (CASE WHEN m[6] = '-' THEN -1 ELSE 1 END) * (tzm + tzh * 60);
    p.is_utc := true;
  END IF;
  RETURN p;
END
$$;


-- o número que sqlite3AtoF aceita inteiro (com espaço ASCII em volta)
CREATE OR REPLACE FUNCTION _cg_e_numero(z text) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT z ~ '^[\u0009-\u000d ]*[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?[\u0009-\u000d ]*$'
$$;

CREATE OR REPLACE FUNCTION _cg_numero(z text) RETURNS double precision
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
BEGIN
  RETURN btrim(z, E' \t\n\r\f\x0b')::float8;
EXCEPTION WHEN numeric_value_out_of_range OR invalid_text_representation THEN
  RETURN NULL;
END
$$;


-- setRawDateNumber()
CREATE OR REPLACE FUNCTION _cg_dt_cru(r double precision) RETURNS cg_sqlite_dt
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE p cg_sqlite_dt := _cg_dt_vazio();
BEGIN
  IF r IS NULL OR r = 'NaN'::float8 THEN RETURN NULL; END IF;
  p.s := r; p.raw_s := true;
  IF r >= 0.0::float8 AND r < 5373484.5::float8 THEN
    p.ijd := trunc(r * 86400000.0::float8 + 0.5::float8)::bigint;
    p.valid_jd := true;
  END IF;
  RETURN p;
END
$$;


-- setDateTimeToCurrent(): o «agora» do comando, em milissegundos, UTC.
CREATE OR REPLACE FUNCTION _cg_dt_agora() RETURNS cg_sqlite_dt
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE p cg_sqlite_dt := _cg_dt_vazio();
BEGIN
  p.ijd := floor(extract(epoch FROM statement_timestamp()) * 1000)::bigint + 210866760000000;
  p.valid_jd := true;
  RETURN p;
END
$$;


-- parseDateOrTime()
CREATE OR REPLACE FUNCTION _cg_dt_analisar(z text, puro boolean) RETURNS cg_sqlite_dt
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
  p cg_sqlite_dt := _cg_dt_vazio(); m text[]; resto text; q cg_sqlite_dt;
  yy int; mm int; dd int; r float8;
BEGIN
  IF z IS NULL THEN RETURN NULL; END IF;
  -- parseYyyyMmDd
  m := regexp_match(z, '^(-?)([0-9]{4})-([0-9]{2})-([0-9]{2})(.*)$');
  IF m IS NOT NULL THEN
    yy := m[2]::int; mm := m[3]::int; dd := m[4]::int;
    IF mm BETWEEN 1 AND 12 AND dd BETWEEN 1 AND 31 THEN
      resto := regexp_replace(m[5], '^[\u0009-\u000d T]*', '');
      q := p;
      IF resto <> '' THEN
        q := _cg_dt_hora(p, resto);
      ELSE
        q.valid_hms := false;
      END IF;
      IF q IS NOT NULL THEN
        q.valid_jd := false;
        q.valid_ymd := true;
        q.y := CASE WHEN m[1] = '-' THEN -yy ELSE yy END;
        q.mo := mm; q.d := dd;
        IF q.tz <> 0 THEN q := _cg_dt_jd(q); END IF;
        RETURN q;
      END IF;
    END IF;
  END IF;
  -- parseHhMmSs
  q := _cg_dt_hora(p, z);
  IF q IS NOT NULL THEN RETURN q; END IF;
  -- 'now'
  IF lower(z COLLATE "C") = 'now' THEN
    IF puro THEN
      RAISE EXCEPTION 'uso não determinístico de função de data (''now'') em contexto imutável';
    END IF;
    RETURN _cg_dt_agora();
  END IF;
  -- número
  IF _cg_e_numero(z) THEN
    r := _cg_numero(z);
    IF r IS NULL THEN RETURN NULL; END IF;
    RETURN _cg_dt_cru(r);
  END IF;
  IF lower(z COLLATE "C") IN ('subsec', 'subsecond') THEN
    IF puro THEN
      RAISE EXCEPTION 'uso não determinístico de função de data (''subsec'') em contexto imutável';
    END IF;
    q := _cg_dt_agora(); q.use_subsec := true;
    RETURN q;
  END IF;
  RETURN NULL;
END
$$;


-- toLocaltime(): para o fuso da SESSÃO (SET TIME ZONE), com o mesmo truque de
-- ano do SQLite fora de 1970..2038.
CREATE OR REPLACE FUNCTION _cg_dt_local(p cg_sqlite_dt) RETURNS cg_sqlite_dt
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
  x cg_sqlite_dt; dif int; t bigint; ts timestamp;
BEGIN
  p := _cg_dt_jd(p);
  IF p IS NULL THEN RETURN NULL; END IF;
  IF p.ijd < 210866760000000 OR p.ijd > 213014145600000 THEN
    x := _cg_dt_ymdhms(p);
    IF x IS NULL THEN RETURN NULL; END IF;
    dif := (2000 + x.y % 4) - x.y;
    x.y := x.y + dif;
    x.valid_jd := false;
    x := _cg_dt_jd(x);
    IF x IS NULL THEN RETURN NULL; END IF;
    t := x.ijd / 1000 - 210866760000;
  ELSE
    dif := 0;
    t := p.ijd / 1000 - 210866760000;
  END IF;
  ts := to_timestamp(t::float8) AT TIME ZONE current_setting('TimeZone');
  p.y := extract(year FROM ts)::int - dif;
  p.mo := extract(month FROM ts)::int;
  p.d := extract(day FROM ts)::int;
  p.h := extract(hour FROM ts)::int;
  p.mi := extract(minute FROM ts)::int;
  p.s := floor(extract(second FROM ts))::float8 + (p.ijd % 1000)::float8 * 0.001::float8;
  p.valid_ymd := true; p.valid_hms := true; p.valid_jd := false;
  p.raw_s := false; p.tz := 0;
  RETURN p;
END
$$;


-- parseModifier() — NULL quando o modificador não vale (o SQLite devolve NULL).
CREATE OR REPLACE FUNCTION _cg_dt_modificar(p cg_sqlite_dt, z text, idx int, puro boolean)
RETURNS cg_sqlite_dt
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
  zl text := lower(z COLLATE "C");
  c0 text := left(zl, 1);
  r float8; nn int; z7 bigint; n int; len int; ch text; pref text; z0 text;
  zz text; mm text[]; yv int; mv int; dv int; x int; z2 text; n2 int;
  tx cg_sqlite_dt; dia bigint; u text; nu int; nome text; rr float8;
  lim float8; xf float8; achou boolean := false;
  orig bigint; palpite bigint; erro bigint; cnt int; novo cg_sqlite_dt;
BEGIN
  IF p IS NULL OR z IS NULL OR z = '' THEN RETURN NULL; END IF;

  IF c0 = 'a' THEN                                   -- auto
    IF zl <> 'auto' OR idx > 1 THEN RETURN NULL; END IF;
    IF NOT p.raw_s OR p.valid_jd THEN
      p.raw_s := false;
    ELSIF p.s >= -210866760000::float8 AND p.s <= 253402300799::float8 THEN
      r := p.s * 1000.0::float8 + 210866760000000.0::float8;
      p.valid_ymd := false; p.valid_hms := false; p.tz := 0;
      p.ijd := trunc(r + 0.5::float8)::bigint;
      p.valid_jd := true; p.raw_s := false;
    END IF;
    RETURN p;

  ELSIF c0 = 'j' THEN                                -- julianday
    IF zl <> 'julianday' OR idx > 1 THEN RETURN NULL; END IF;
    IF p.valid_jd AND p.raw_s THEN p.raw_s := false; RETURN p; END IF;
    RETURN NULL;

  ELSIF c0 = 'l' THEN                                -- localtime
    IF zl <> 'localtime' THEN RETURN NULL; END IF;
    IF puro THEN
      RAISE EXCEPTION 'uso não determinístico de função de data (''localtime'') em contexto imutável';
    END IF;
    -- Na 3.45 'localtime' converte SEMPRE — duas vezes desloca duas vezes
    -- (só a 3.46 passou a ignorar a segunda). Medido no teste.
    p := _cg_dt_local(p);
    RETURN p;

  ELSIF c0 = 'u' THEN                                -- unixepoch | utc
    IF zl = 'unixepoch' AND p.raw_s THEN
      IF idx > 1 THEN RETURN NULL; END IF;
      r := p.s * 1000.0::float8 + 210866760000000.0::float8;
      IF r >= 0.0::float8 AND r < 464269060800000.0::float8 THEN
        p.valid_ymd := false; p.valid_hms := false; p.tz := 0;
        p.ijd := trunc(r + 0.5::float8)::bigint;
        p.valid_jd := true; p.raw_s := false;
        RETURN p;
      END IF;
      RETURN NULL;
    ELSIF zl = 'utc' THEN
      IF puro THEN
        RAISE EXCEPTION 'uso não determinístico de função de data (''utc'') em contexto imutável';
      END IF;
      IF NOT p.is_utc THEN
        p := _cg_dt_jd(p);
        IF p IS NULL THEN RETURN NULL; END IF;
        orig := p.ijd; palpite := orig; erro := 0; cnt := 0;
        LOOP
          palpite := palpite - erro;
          novo := _cg_dt_vazio(); novo.ijd := palpite; novo.valid_jd := true;
          novo := _cg_dt_jd(_cg_dt_local(novo));
          IF novo IS NULL THEN RETURN NULL; END IF;
          erro := novo.ijd - orig;
          EXIT WHEN erro = 0 OR cnt >= 3;
          cnt := cnt + 1;
        END LOOP;
        p := _cg_dt_vazio();
        p.ijd := palpite; p.valid_jd := true; p.is_utc := true;
      END IF;
      RETURN p;
    END IF;
    RETURN NULL;

  ELSIF c0 = 'w' THEN                                -- weekday N
    IF left(zl, 8) <> 'weekday ' OR NOT _cg_e_numero(substr(z, 9)) THEN RETURN NULL; END IF;
    r := _cg_numero(substr(z, 9));
    IF r IS NULL OR NOT (r >= 0.0::float8 AND r < 7.0::float8) OR trunc(r) <> r THEN RETURN NULL; END IF;
    nn := r::int;
    p := _cg_dt_ymdhms(p);
    IF p IS NULL THEN RETURN NULL; END IF;
    p.tz := 0; p.valid_jd := false;
    p := _cg_dt_jd(p);
    IF p IS NULL THEN RETURN NULL; END IF;
    z7 := ((p.ijd + 129600000) / 86400000) % 7;
    IF z7 > nn THEN z7 := z7 - 7; END IF;
    p.ijd := p.ijd + (nn - z7) * 86400000;
    p.valid_ymd := false; p.valid_hms := false; p.tz := 0;
    RETURN p;

  ELSIF c0 = 's' THEN                                -- start of ... | subsec
    IF left(zl, 9) <> 'start of ' THEN
      IF zl IN ('subsec', 'subsecond') THEN p.use_subsec := true; RETURN p; END IF;
      RETURN NULL;
    END IF;
    IF NOT p.valid_jd AND NOT p.valid_ymd AND NOT p.valid_hms THEN RETURN NULL; END IF;
    p := _cg_dt_ymd(p);
    IF p IS NULL THEN RETURN NULL; END IF;
    p.valid_hms := true; p.h := 0; p.mi := 0; p.s := 0; p.raw_s := false;
    p.tz := 0; p.valid_jd := false;
    u := substr(zl, 10);
    IF u = 'month' THEN p.d := 1;
    ELSIF u = 'year' THEN p.mo := 1; p.d := 1;
    ELSIF u = 'day' THEN NULL;
    ELSE RETURN NULL;
    END IF;
    RETURN p;

  ELSIF c0 IN ('+','-','0','1','2','3','4','5','6','7','8','9') THEN
    len := length(z);
    n := 1;
    WHILE n < len LOOP
      ch := substr(z, n + 1, 1);
      EXIT WHEN ch = ':' OR ch ~ '[\u0009-\u000d ]';
      IF ch = '-' THEN
        EXIT WHEN n = 5 AND substr(z, 2, 4) ~ '^[0-9]{4}$';
        EXIT WHEN n = 6 AND CASE WHEN substr(z, 2, 5) ~ '^[0-9]{5}$'
                                 THEN substr(z, 2, 5)::int <= 14712 ELSE false END;
      END IF;
      n := n + 1;
    END LOOP;
    pref := substr(z, 1, n);
    IF NOT _cg_e_numero(pref) THEN RETURN NULL; END IF;
    r := _cg_numero(pref);
    IF r IS NULL THEN RETURN NULL; END IF;
    z0 := left(z, 1);
    z2 := z; n2 := n;

    IF substr(z, n + 1, 1) = '-' THEN
      -- (+|-)YYYY-MM-DD [HH:MM[:SS.FFF]]
      IF z0 NOT IN ('+', '-') THEN RETURN NULL; END IF;
      IF n = 5 THEN
        zz := z;
        mm := regexp_match(substr(z, 2), '^([0-9]{4})-([0-9]{2})-([0-9]{2})');
      ELSE
        zz := substr(z, 2);
        mm := regexp_match(substr(z, 2), '^([0-9]{5})-([0-9]{2})-([0-9]{2})');
      END IF;
      IF mm IS NULL THEN RETURN NULL; END IF;
      yv := mm[1]::int; mv := mm[2]::int; dv := mm[3]::int;
      IF yv > 14712 OR mv > 12 OR dv > 31 THEN RETURN NULL; END IF;   -- getDigits
      IF mv >= 12 OR dv >= 31 THEN RETURN NULL; END IF;
      p := _cg_dt_ymdhms(p);
      IF p IS NULL THEN RETURN NULL; END IF;
      p.valid_jd := false;
      IF z0 = '-' THEN
        p.y := p.y - yv; p.mo := p.mo - mv; dv := -dv;
      ELSE
        p.y := p.y + yv; p.mo := p.mo + mv;
      END IF;
      x := CASE WHEN p.mo > 0 THEN (p.mo - 1) / 12 ELSE (p.mo - 12) / 12 END;
      p.y := p.y + x;
      p.mo := p.mo - x * 12;
      p := _cg_dt_jd(p);
      IF p IS NULL THEN RETURN NULL; END IF;
      p.valid_hms := false; p.valid_ymd := false;
      p.ijd := p.ijd + dv::bigint * 86400000;
      IF substr(zz, 12, 1) = '' THEN RETURN p; END IF;
      IF substr(zz, 12, 1) ~ '[\u0009-\u000d ]' AND substr(zz, 13) ~ '^[0-9]{2}:[0-9]{2}' THEN
        IF substr(zz, 13, 2)::int > 24 OR substr(zz, 16, 2)::int > 59 THEN RETURN NULL; END IF;
        z2 := substr(zz, 13); n2 := 2;
      ELSE
        RETURN NULL;
      END IF;
    END IF;

    IF substr(z2, n2 + 1, 1) = ':' THEN
      -- (+|-)HH:MM[:SS[.FFF]]
      IF left(z2, 1) !~ '[0-9]' THEN z2 := substr(z2, 2); END IF;
      tx := _cg_dt_hora(_cg_dt_vazio(), z2);
      IF tx IS NULL THEN RETURN NULL; END IF;
      tx := _cg_dt_jd(tx);
      IF tx IS NULL THEN RETURN NULL; END IF;
      tx.ijd := tx.ijd - 43200000;
      dia := tx.ijd / 86400000;
      tx.ijd := tx.ijd - dia * 86400000;
      IF z0 = '-' THEN tx.ijd := -tx.ijd; END IF;
      p := _cg_dt_jd(p);
      IF p IS NULL THEN RETURN NULL; END IF;
      p.valid_ymd := false; p.valid_hms := false; p.tz := 0;
      p.ijd := p.ijd + tx.ijd;
      RETURN p;
    END IF;

    -- "+NNN days" e companhia
    u := regexp_replace(substr(z, n + 1), '^[\u0009-\u000d ]*', '');
    nu := length(u);
    IF nu < 3 OR nu > 10 THEN RETURN NULL; END IF;
    IF lower(right(u, 1) COLLATE "C") = 's' THEN nu := nu - 1; END IF;
    p := _cg_dt_jd(p);
    IF p IS NULL THEN RETURN NULL; END IF;
    rr := CASE WHEN r < 0 THEN -0.5::float8 ELSE 0.5::float8 END;
    nome := lower(left(u, nu) COLLATE "C");
    -- aXformType: os limites são float de 32 bits no C, e aqui vão como ficam
    -- em double depois da conversão.
    IF nome = 'second' THEN lim := 464269992787968; xf := 1;
    ELSIF nome = 'minute' THEN lim := 7737900007424; xf := 60;
    ELSIF nome = 'hour' THEN lim := 128969998336; xf := 3600;
    ELSIF nome = 'day' THEN lim := 5373485; xf := 86400;
    ELSIF nome = 'month' THEN lim := 176546; xf := 2592000;
    ELSIF nome = 'year' THEN lim := 14713; xf := 31536000;
    END IF;
    IF lim IS NOT NULL AND r > -lim AND r < lim THEN
      IF nome = 'month' THEN
        p := _cg_dt_ymdhms(p);
        IF p IS NULL THEN RETURN NULL; END IF;
        p.mo := p.mo + trunc(r)::int;
        x := CASE WHEN p.mo > 0 THEN (p.mo - 1) / 12 ELSE (p.mo - 12) / 12 END;
        p.y := p.y + x;
        p.mo := p.mo - x * 12;
        p.valid_jd := false;
        r := r - trunc(r);
      ELSIF nome = 'year' THEN
        p := _cg_dt_ymdhms(p);
        IF p IS NULL THEN RETURN NULL; END IF;
        p.y := p.y + trunc(r)::int;
        p.valid_jd := false;
        r := r - trunc(r);
      END IF;
      p := _cg_dt_jd(p);
      IF p IS NULL THEN RETURN NULL; END IF;
      p.ijd := p.ijd + trunc(r * 1000.0::float8 * xf + rr)::bigint;
      achou := true;
    END IF;
    p.valid_ymd := false; p.valid_hms := false; p.tz := 0;
    IF achou THEN RETURN p; END IF;
    RETURN NULL;
  END IF;
  RETURN NULL;
END
$$;


-- isDate(): valor (texto ou número) + modificadores → o estado final, ou NULL.
CREATE OR REPLACE FUNCTION _cg_dt(p_txt text, p_num double precision, p_eh_num boolean,
                                  p_mods text[], p_puro boolean DEFAULT false)
RETURNS cg_sqlite_dt
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
  p cg_sqlite_dt; i int; nmods int := coalesce(array_length(p_mods, 1), 0);
BEGIN
  IF p_eh_num THEN
    IF p_num IS NULL THEN RETURN NULL; END IF;
    p := _cg_dt_cru(p_num);
  ELSE
    IF p_txt IS NULL THEN RETURN NULL; END IF;
    p := _cg_dt_analisar(p_txt, p_puro);
  END IF;
  IF p IS NULL THEN RETURN NULL; END IF;
  FOR i IN 1..nmods LOOP
    p := _cg_dt_modificar(p, p_mods[i], i, p_puro);
    IF p IS NULL THEN RETURN NULL; END IF;
  END LOOP;
  p := _cg_dt_jd(p);
  IF p IS NULL OR NOT (p.ijd >= 0 AND p.ijd <= 464269060799999) THEN RETURN NULL; END IF;
  IF nmods = 0 AND p.valid_ymd AND p.d > 28 THEN
    p.valid_ymd := false;    -- 2023-02-31 -> 2023-03-03
  END IF;
  RETURN p;
END
$$;


-- ---------------------------------------------------------- formatação

-- "%0Nd" do C (o sinal conta na largura)
CREATE OR REPLACE FUNCTION _cg_pad(v bigint, w int) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN v < 0 THEN '-' ELSE '' END
         || lpad(abs(v)::text, greatest(length(abs(v)::text), w - CASE WHEN v < 0 THEN 1 ELSE 0 END), '0')
$$;


-- A expansão decimal EXATA de um double (todo double é um racional finito
-- em base 10). O cast float8 -> numeric do PostgreSQL arredonda para 15
-- dígitos, e o printf do SQLite olha mais longe que isso.
CREATE OR REPLACE FUNCTION _cg_decimal_exato(x double precision) RETURNS numeric
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
DECLARE
  ax float8 := abs(x); e int; m bigint; k int; nmr numeric; s text; i int;
BEGIN
  IF ax = 0 THEN RETURN 0; END IF;
  IF ax = 'Infinity'::float8 OR x = 'NaN'::float8 THEN RETURN NULL; END IF;
  e := floor(ln(ax) / ln(2::float8))::int;
  -- acerta e para que 2^e <= ax < 2^(e+1)
  WHILE e > -1074 AND power(2::float8, e) > ax LOOP e := e - 1; END LOOP;
  WHILE e < 1023 AND power(2::float8, e + 1) <= ax LOOP e := e + 1; END LOOP;
  IF e < -1022 THEN e := -1022; END IF;                      -- subnormal
  -- m = ax * 2^(52-e), inteiro exato (multiplicar por potência de 2 é exato)
  IF 52 - e > 1000 THEN
    m := (ax * power(2::float8, 1000) * power(2::float8, 52 - e - 1000))::bigint;
  ELSE
    m := (ax * power(2::float8, 52 - e))::bigint;
  END IF;
  k := 52 - e;
  IF k <= 0 THEN
    nmr := m::numeric;
    FOR i IN 1..(-k) LOOP nmr := nmr * 2; END LOOP;
  ELSE
    nmr := m::numeric;
    FOR i IN 1..k LOOP nmr := nmr * 5; END LOOP;     -- m*2^-k = m*5^k / 10^k
    s := nmr::text;
    IF length(s) <= k THEN s := repeat('0', k - length(s) + 1) || s; END IF;
    nmr := (left(s, length(s) - k) || '.' || right(s, k))::numeric;
  END IF;
  RETURN CASE WHEN x < 0 THEN -nmr ELSE nmr END;
END
$$;


-- O printf do SQLite para real (sqlite3FpDecode + etFLOAT/etGENERIC):
-- arredonda «meio para cima» sobre a expansão decimal, com no máximo 16
-- dígitos significativos (26 com a marca '!').
--   tipo 'f' = %.Nf ; tipo 'g' = %.Ng ; alt2 = a marca '!'
CREATE OR REPLACE FUNCTION _cg_fmt_real(x double precision, tipo text, prec int,
                                        alt2 boolean DEFAULT false)
RETURNS text
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
  ex numeric; s text; dig text; idp int; n int; iround int; mx int;
  j int; ch int; sinal text := ''; e int; pr int; ip text; fp text; res text;
  i int; flag_dp boolean;
BEGIN
  IF x IS NULL THEN RETURN NULL; END IF;
  IF x = 'NaN'::float8 THEN RETURN 'NaN'; END IF;
  IF x = 'Infinity'::float8 THEN RETURN 'Inf'; END IF;
  IF x = '-Infinity'::float8 THEN RETURN '-Inf'; END IF;
  mx := CASE WHEN alt2 THEN 26 ELSE 16 END;
  IF x < 0 THEN sinal := '-'; END IF;
  IF x = 0 THEN
    dig := '0'; idp := 1;
  ELSE
    ex := abs(_cg_decimal_exato(x));
    s := ex::text;
    IF position('.' IN s) > 0 THEN
      ip := split_part(s, '.', 1); fp := split_part(s, '.', 2);
    ELSE
      ip := s; fp := '';
    END IF;
    IF ip = '0' THEN
      dig := ltrim(fp, '0');
      idp := -(length(fp) - length(dig));
    ELSE
      dig := ip || fp;
      idp := length(ip);
    END IF;
    dig := rtrim(dig, '0');
    IF dig = '' THEN dig := '0'; idp := 1; END IF;
  END IF;
  n := length(dig);

  pr := prec;
  IF tipo = 'f' AND pr = 0 THEN
    iround := 0;                -- sem arredondar: a 3.45 trunca em %.0f
  ELSIF tipo = 'f' THEN
    iround := idp + pr;
  ELSE
    IF pr = 0 THEN pr := 1; END IF;
    iround := pr;
  END IF;
  IF tipo = 'f' AND pr > 0 AND iround = 0 AND left(dig, 1) >= '5' THEN
    dig := '0' || dig; n := n + 1; idp := idp + 1; iround := 1;
  END IF;
  IF iround > 0 AND (iround < n OR n > mx) THEN
    IF iround > mx THEN iround := mx; END IF;
    IF substr(dig, iround + 1, 1) >= '5' THEN
      j := iround;
      LOOP
        ch := ascii(substr(dig, j, 1)) + 1;
        IF ch <= 57 THEN
          dig := overlay(dig PLACING chr(ch) FROM j FOR 1);
          EXIT;
        END IF;
        dig := overlay(dig PLACING '0' FROM j FOR 1);
        IF j = 1 THEN
          dig := '1' || dig; idp := idp + 1; iround := iround + 1;
          EXIT;
        END IF;
        j := j - 1;
      END LOOP;
    END IF;
    dig := left(dig, iround);
    n := iround;
  ELSIF iround <= 0 AND tipo = 'f' AND pr > 0 THEN
    dig := '0'; n := 1;   -- nada sobra dentro da precisão
    idp := 1;
    -- (o C imprime zeros; o resultado é o mesmo)
  END IF;

  IF tipo = 'g' THEN
    e := idp - 1;
    pr := pr - 1;
    IF dig = '0' THEN e := 0; END IF;
    flag_dp := (pr > 0) OR alt2;
    IF e < -4 OR e > pr THEN
      -- etEXP: um dígito, ponto, pr dígitos
      fp := rpad(substr(dig, 2), pr, '0');
      res := left(dig, 1);
      IF flag_dp THEN res := res || '.' || fp; END IF;
      res := rtrim(res, '0');
      IF right(res, 1) = '.' THEN
        res := CASE WHEN alt2 THEN res || '0' ELSE left(res, length(res) - 1) END;
      END IF;
      res := res || 'e' || CASE WHEN e < 0 THEN '-' ELSE '+' END
             || CASE WHEN abs(e) >= 100 THEN abs(e)::text ELSE lpad(abs(e)::text, 2, '0') END;
      RETURN sinal || res;
    END IF;
    pr := pr - e;
    tipo := 'f';
    -- etFLOAT com remoção de zeros à direita
    IF idp <= 0 THEN ip := '0';
    ELSE ip := rpad(left(dig, idp), idp, '0');
    END IF;
    fp := '';
    FOR i IN 1..pr LOOP
      j := idp + i;
      fp := fp || CASE WHEN j >= 1 AND j <= n THEN substr(dig, j, 1) ELSE '0' END;
    END LOOP;
    res := ip;
    IF flag_dp THEN res := res || '.' || fp; END IF;
    IF flag_dp THEN
      res := rtrim(res, '0');
      IF right(res, 1) = '.' THEN
        res := CASE WHEN alt2 THEN res || '0' ELSE left(res, length(res) - 1) END;
      END IF;
    END IF;
    RETURN sinal || res;
  END IF;

  -- etFLOAT
  IF idp <= 0 THEN ip := '0';
  ELSE ip := rpad(left(dig, idp), idp, '0');
  END IF;
  fp := '';
  FOR i IN 1..pr LOOP
    j := idp + i;
    fp := fp || CASE WHEN j >= 1 AND j <= n THEN substr(dig, j, 1) ELSE '0' END;
  END LOOP;
  IF pr > 0 THEN RETURN sinal || ip || '.' || fp; END IF;
  RETURN sinal || ip;
END
$$;


-- REAL -> TEXT como o SQLite 3.45 (sqlite3VdbeMemStringify: "%!.15g")
CREATE OR REPLACE FUNCTION _cg_real_texto(x double precision) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT _cg_fmt_real(x, 'g', 15, true)
$$;


CREATE OR REPLACE FUNCTION _cg_dt_strftime(fmt text, p cg_sqlite_dt) RETURNS text
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
  res text := ''; i int := 1; n int; c text; y cg_sqlite_dt; nday bigint; wd bigint;
  sv float8; t text; hh12 int;
BEGIN
  IF fmt IS NULL OR p IS NULL THEN RETURN NULL; END IF;
  p := _cg_dt_ymdhms(_cg_dt_jd(p));
  IF p IS NULL THEN RETURN NULL; END IF;
  n := length(fmt);
  WHILE i <= n LOOP
    c := substr(fmt, i, 1);
    IF c <> '%' THEN
      res := res || c; i := i + 1; CONTINUE;
    END IF;
    c := substr(fmt, i + 1, 1);
    i := i + 2;
    IF c = 'd' THEN res := res || _cg_pad(p.d, 2);
    ELSIF c = 'e' THEN res := res || lpad(p.d::text, greatest(2, length(p.d::text)), ' ');
    ELSIF c = 'F' THEN res := res || _cg_pad(p.y, 4) || '-' || _cg_pad(p.mo, 2) || '-' || _cg_pad(p.d, 2);
    ELSIF c = 'k' THEN res := res || lpad(p.h::text, greatest(2, length(p.h::text)), ' ');
    ELSIF c IN ('I', 'l') THEN
      hh12 := CASE WHEN p.h > 12 THEN p.h - 12 WHEN p.h = 0 THEN 12 ELSE p.h END;
      res := res || CASE WHEN c = 'I' THEN _cg_pad(hh12, 2)
                         ELSE lpad(hh12::text, greatest(2, length(hh12::text)), ' ') END;
    ELSIF c = 'p' THEN res := res || CASE WHEN p.h >= 12 THEN 'PM' ELSE 'AM' END;
    ELSIF c = 'P' THEN res := res || CASE WHEN p.h >= 12 THEN 'pm' ELSE 'am' END;
    ELSIF c = 'R' THEN res := res || _cg_pad(p.h, 2) || ':' || _cg_pad(p.mi, 2);
    ELSIF c = 'T' THEN res := res || _cg_pad(p.h, 2) || ':' || _cg_pad(p.mi, 2) || ':' || _cg_pad(trunc(p.s)::bigint, 2);
    ELSIF c = 'u' THEN
      wd := ((p.ijd + 129600000) / 86400000) % 7;
      res := res || CASE WHEN wd = 0 THEN '7' ELSE wd::text END;
    ELSIF c = 'f' THEN
      sv := p.s;
      IF sv > 59.999::float8 THEN sv := 59.999::float8; END IF;
      t := _cg_fmt_real(sv, 'f', 3);
      res := res || lpad(t, greatest(6, length(t)), '0');
    ELSIF c = 'H' THEN res := res || _cg_pad(p.h, 2);
    ELSIF c IN ('W', 'j') THEN
      y := p; y.valid_jd := false; y.mo := 1; y.d := 1;
      y := _cg_dt_jd(y);
      IF y IS NULL THEN RETURN NULL; END IF;
      nday := (p.ijd - y.ijd + 43200000) / 86400000;
      IF c = 'W' THEN
        wd := ((p.ijd + 43200000) / 86400000) % 7;
        res := res || _cg_pad((nday + 7 - wd) / 7, 2);
      ELSE
        res := res || _cg_pad(nday + 1, 3);
      END IF;
    ELSIF c = 'J' THEN res := res || _cg_fmt_real(p.ijd::float8 / 86400000.0::float8, 'g', 16);
    ELSIF c = 'm' THEN res := res || _cg_pad(p.mo, 2);
    ELSIF c = 'M' THEN res := res || _cg_pad(p.mi, 2);
    ELSIF c = 's' THEN
      IF p.use_subsec THEN
        res := res || _cg_fmt_real((p.ijd - 210866760000000)::float8 / 1000.0::float8, 'f', 3);
      ELSE
        res := res || (p.ijd / 1000 - 210866760000)::text;
      END IF;
    ELSIF c = 'S' THEN res := res || _cg_pad(trunc(p.s)::bigint, 2);
    ELSIF c = 'w' THEN res := res || (((p.ijd + 129600000) / 86400000) % 7)::text;
    ELSIF c = 'Y' THEN res := res || _cg_pad(p.y, 4);
    ELSIF c = '%' THEN res := res || '%';
    ELSE RETURN NULL;          -- formato desconhecido, ou '%' no fim
    END IF;
  END LOOP;
  RETURN res;
END
$$;


-- dateFunc / timeFunc / datetimeFunc (buffer montado à mão, como na 3.45)
CREATE OR REPLACE FUNCTION _cg_dt_data(p cg_sqlite_dt) RETURNS text
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
BEGIN
  p := _cg_dt_ymd(p);
  IF p IS NULL THEN RETURN NULL; END IF;
  RETURN CASE WHEN p.y < 0 THEN '-' ELSE '' END
         || lpad((abs(p.y) % 10000)::text, 4, '0') || '-'
         || lpad((p.mo % 100)::text, 2, '0') || '-'
         || lpad((p.d % 100)::text, 2, '0');
END
$$;

CREATE OR REPLACE FUNCTION _cg_dt_horario(p cg_sqlite_dt) RETURNS text
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE s bigint;
BEGIN
  p := _cg_dt_hms(p);
  IF p IS NULL THEN RETURN NULL; END IF;
  IF p.use_subsec THEN
    s := trunc(1000.0::float8 * p.s + 0.5::float8)::bigint;
    RETURN lpad((p.h % 100)::text, 2, '0') || ':' || lpad((p.mi % 100)::text, 2, '0') || ':'
           || ((s / 10000) % 10)::text || ((s / 1000) % 10)::text || '.'
           || ((s / 100) % 10)::text || ((s / 10) % 10)::text || (s % 10)::text;
  END IF;
  s := trunc(p.s)::bigint;
  RETURN lpad((p.h % 100)::text, 2, '0') || ':' || lpad((p.mi % 100)::text, 2, '0') || ':'
         || lpad((s % 100)::text, 2, '0');
END
$$;

CREATE OR REPLACE FUNCTION _cg_dt_datahora(p cg_sqlite_dt) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT _cg_dt_data(_cg_dt_ymd(p)) || ' ' || _cg_dt_horario(_cg_dt_ymd(p))
$$;

CREATE OR REPLACE FUNCTION _cg_dt_juliano(p cg_sqlite_dt) RETURNS double precision
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT (p).ijd::float8 / 86400000.0::float8
$$;


-- ------------------------------------------------- as funções com o nome do SQLite
-- Geradas para cada tipo de valor (texto, double, bigint, integer, numeric),
-- com e sem modificadores. As de NÚMERO são lidas como dia juliano (ou
-- segundos com 'unixepoch'), como o SQLite faz com REAL e INTEGER.
-- Todas STABLE: dependem de 'now' e do fuso da sessão ('localtime').
DO $do$
DECLARE
  nomes   text[] := ARRAY['date', 'time', 'datetime', 'julianday',
                          'cg_date', 'cg_time', 'cg_datetime', 'cg_julianday'];
  saidas  text[] := ARRAY['_cg_dt_data', '_cg_dt_horario', '_cg_dt_datahora', '_cg_dt_juliano',
                          '_cg_dt_data', '_cg_dt_horario', '_cg_dt_datahora', '_cg_dt_juliano'];
  tipos   text[] := ARRAY['text', 'double precision', 'bigint', 'integer', 'numeric'];
  i int; t text; ret text; chamada_txt text; chamada_num text;
BEGIN
  FOR i IN 1..array_length(nomes, 1) LOOP
    ret := CASE WHEN saidas[i] = '_cg_dt_juliano' THEN 'double precision' ELSE 'text' END;
    -- sem argumento: 'now'
    EXECUTE format($f$CREATE OR REPLACE FUNCTION %I() RETURNS %s
      LANGUAGE sql STABLE PARALLEL SAFE AS $b$ SELECT %s(_cg_dt('now', NULL, false, NULL)) $b$$f$,
      nomes[i], ret, saidas[i]);
    FOREACH t IN ARRAY tipos LOOP
      IF t = 'text' THEN
        chamada_txt := '_cg_dt(valor, NULL, false, %s)';
      ELSE
        chamada_txt := '_cg_dt(NULL, valor::float8, true, %s)';
      END IF;
      EXECUTE format($f$CREATE OR REPLACE FUNCTION %I(valor %s) RETURNS %s
        LANGUAGE sql STABLE PARALLEL SAFE AS $b$ SELECT %s(%s) $b$$f$,
        nomes[i], t, ret, saidas[i], format(chamada_txt, 'NULL'));
      EXECUTE format($f$CREATE OR REPLACE FUNCTION %I(valor %s, VARIADIC modificadores text[]) RETURNS %s
        LANGUAGE sql STABLE PARALLEL SAFE AS $b$ SELECT %s(%s) $b$$f$,
        nomes[i], t, ret, saidas[i], format(chamada_txt, 'modificadores'));
    END LOOP;
  END LOOP;

  -- strftime(fmt), strftime(fmt, valor), strftime(fmt, valor, VARIADIC mods)
  EXECUTE $f$CREATE OR REPLACE FUNCTION strftime(fmt text) RETURNS text
    LANGUAGE sql STABLE PARALLEL SAFE AS $b$ SELECT _cg_dt_strftime(fmt, _cg_dt('now', NULL, false, NULL)) $b$$f$;
  FOREACH t IN ARRAY tipos LOOP
    IF t = 'text' THEN
      chamada_txt := '_cg_dt(valor, NULL, false, %s)';
    ELSE
      chamada_txt := '_cg_dt(NULL, valor::float8, true, %s)';
    END IF;
    EXECUTE format($f$CREATE OR REPLACE FUNCTION strftime(fmt text, valor %s) RETURNS text
      LANGUAGE sql STABLE PARALLEL SAFE AS $b$ SELECT _cg_dt_strftime(fmt, %s) $b$$f$,
      t, format(chamada_txt, 'NULL'));
    EXECUTE format($f$CREATE OR REPLACE FUNCTION strftime(fmt text, valor %s, VARIADIC modificadores text[]) RETURNS text
      LANGUAGE sql STABLE PARALLEL SAFE AS $b$ SELECT _cg_dt_strftime(fmt, %s) $b$$f$,
      t, format(chamada_txt, 'modificadores'));
  END LOOP;
END
$do$;


-- O CAMINHO CURTO de date(texto) e datetime(texto), sem modificador: a forma
-- canônica que o próprio sistema grava ('AAAA-MM-DD', com ' ' ou 'T' e
-- HH:MM[:SS[.fff]]) sai por recorte de texto, sem passar pela máquina de
-- estado em PL/pgSQL (medido: ~180 µs por chamada pela máquina; o recorte é
-- SQL puro, que o planejador embute na consulta). Só entra o que dá o MESMO
-- resultado com certeza: a data tem de EXISTIR (29, 30 e 31 só nos meses que
-- os têm, e 29/02 só no bissexto — o SQLite normaliza 2023-02-31 para
-- 03-03 pelo dia juliano) e a hora vai de 00 a 23 (24:00 é aceito lá e
-- vira outro dia). O resto — e toda chamada com modificador — vai pela
-- máquina.
CREATE OR REPLACE FUNCTION _cg_canonico(valor text) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE
    WHEN valor IS NULL THEN false
    WHEN valor !~ '^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])([ T]([01][0-9]|2[0-3]):[0-5][0-9](:[0-5][0-9](\.[0-9]+)?)?)?$'
      THEN false
    WHEN substr(valor, 9, 2)::int <= 28 THEN true
    WHEN substr(valor, 6, 2)::int = 2 THEN
      substr(valor, 9, 2)::int = 29
      AND (substr(valor, 1, 4)::int % 4 = 0
           AND (substr(valor, 1, 4)::int % 100 <> 0 OR substr(valor, 1, 4)::int % 400 = 0))
    WHEN substr(valor, 9, 2)::int = 31 THEN substr(valor, 6, 2)::int IN (1, 3, 5, 7, 8, 10, 12)
    ELSE true
  END
$$;

CREATE OR REPLACE FUNCTION date(valor text) RETURNS text
LANGUAGE sql STABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN _cg_canonico(valor) THEN left(valor, 10)
              ELSE _cg_dt_data(_cg_dt(valor, NULL, false, NULL)) END
$$;
CREATE OR REPLACE FUNCTION cg_date(valor text) RETURNS text
LANGUAGE sql STABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN _cg_canonico(valor) THEN left(valor, 10)
              ELSE _cg_dt_data(_cg_dt(valor, NULL, false, NULL)) END
$$;
CREATE OR REPLACE FUNCTION datetime(valor text) RETURNS text
LANGUAGE sql STABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN _cg_canonico(valor)
              THEN left(valor, 10) || ' '
                   || CASE WHEN length(valor) >= 16 THEN substr(valor, 12, 5) ELSE '00:00' END
                   || ':' || CASE WHEN length(valor) >= 19 THEN substr(valor, 18, 2) ELSE '00' END
              ELSE _cg_dt_datahora(_cg_dt(valor, NULL, false, NULL)) END
$$;
CREATE OR REPLACE FUNCTION cg_datetime(valor text) RETURNS text
LANGUAGE sql STABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN _cg_canonico(valor)
              THEN left(valor, 10) || ' '
                   || CASE WHEN length(valor) >= 16 THEN substr(valor, 12, 5) ELSE '00:00' END
                   || ':' || CASE WHEN length(valor) >= 19 THEN substr(valor, 18, 2) ELSE '00' END
              ELSE _cg_dt_datahora(_cg_dt(valor, NULL, false, NULL)) END
$$;


-- Versões IMUTÁVEIS, para índice e coluna gerada: só aceitam data fixa.
-- Levam o search_path de quando foram criadas: o PostgreSQL 17+ roda a
-- manutenção de índice (CREATE INDEX, REINDEX, VACUUM) com search_path
-- restrito a pg_catalog, e sem isto as auxiliares _cg_dt* não seriam achadas
-- (medido: «function _cg_dt(...) does not exist» no CREATE INDEX).
-- 'now', 'subsec', 'localtime' e 'utc' viram ERRO (como o SQLite faz num
-- índice: «non-deterministic use of date()»), e não NULL calado.
CREATE OR REPLACE FUNCTION cg_date_imutavel(valor text, VARIADIC modificadores text[] DEFAULT '{}')
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE
  SET search_path FROM CURRENT AS $$
  SELECT _cg_dt_data(_cg_dt(valor, NULL, false, modificadores, true))
$$;
CREATE OR REPLACE FUNCTION cg_time_imutavel(valor text, VARIADIC modificadores text[] DEFAULT '{}')
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE
  SET search_path FROM CURRENT AS $$
  SELECT _cg_dt_horario(_cg_dt(valor, NULL, false, modificadores, true))
$$;
CREATE OR REPLACE FUNCTION cg_datetime_imutavel(valor text, VARIADIC modificadores text[] DEFAULT '{}')
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE
  SET search_path FROM CURRENT AS $$
  SELECT _cg_dt_datahora(_cg_dt(valor, NULL, false, modificadores, true))
$$;
CREATE OR REPLACE FUNCTION cg_julianday_imutavel(valor text, VARIADIC modificadores text[] DEFAULT '{}')
RETURNS double precision LANGUAGE sql IMMUTABLE PARALLEL SAFE
  SET search_path FROM CURRENT AS $$
  SELECT _cg_dt_juliano(_cg_dt(valor, NULL, false, modificadores, true))
$$;
CREATE OR REPLACE FUNCTION cg_strftime_imutavel(fmt text, valor text, VARIADIC modificadores text[] DEFAULT '{}')
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE
  SET search_path FROM CURRENT AS $$
  SELECT _cg_dt_strftime(fmt, _cg_dt(valor, NULL, false, modificadores, true))
$$;


-- CURRENT_TIMESTAMP / CURRENT_DATE / CURRENT_TIME do SQLite: UTC, texto, e o
-- mesmo instante para o comando inteiro (statement_timestamp, e não now(),
-- que é o início da TRANSAÇÃO — o SQLite congela por comando).
CREATE OR REPLACE FUNCTION cg_agora_texto() RETURNS text
LANGUAGE sql STABLE PARALLEL SAFE AS $$
  SELECT to_char(statement_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
$$;
CREATE OR REPLACE FUNCTION cg_hoje_texto() RETURNS text
LANGUAGE sql STABLE PARALLEL SAFE AS $$
  SELECT to_char(statement_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD')
$$;
CREATE OR REPLACE FUNCTION cg_hora_texto() RETURNS text
LANGUAGE sql STABLE PARALLEL SAFE AS $$
  SELECT to_char(statement_timestamp() AT TIME ZONE 'UTC', 'HH24:MI:SS')
$$;


-- ------------------------------------------------------------------ ifnull
-- Pares concretos primeiro (resolvem `ifnull(texto,'')`, `ifnull(int,0)` e
-- `ifnull(int,'')` sem ambiguidade); o polimórfico cobre o resto.
CREATE OR REPLACE FUNCTION ifnull(a text, b text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT coalesce(a, b) $$;
CREATE OR REPLACE FUNCTION ifnull(a integer, b integer) RETURNS integer
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT coalesce(a, b) $$;
CREATE OR REPLACE FUNCTION ifnull(a bigint, b bigint) RETURNS bigint
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT coalesce(a, b) $$;
CREATE OR REPLACE FUNCTION ifnull(a double precision, b double precision) RETURNS double precision
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT coalesce(a, b) $$;
CREATE OR REPLACE FUNCTION ifnull(a numeric, b numeric) RETURNS numeric
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT coalesce(a, b) $$;
CREATE OR REPLACE FUNCTION ifnull(a bytea, b bytea) RETURNS bytea
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT coalesce(a, b) $$;
-- número com texto: o SQLite devolve o que vier, com o tipo de quem veio;
-- aqui o resultado é texto, com o número escrito como o SQLite o escreveria.
CREATE OR REPLACE FUNCTION ifnull(a bigint, b text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT coalesce(a::text, b) $$;
CREATE OR REPLACE FUNCTION ifnull(a text, b bigint) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT coalesce(a, b::text) $$;
CREATE OR REPLACE FUNCTION ifnull(a double precision, b text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT coalesce(_cg_real_texto(a), b) $$;
CREATE OR REPLACE FUNCTION ifnull(a text, b double precision) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT coalesce(a, _cg_real_texto(b)) $$;
CREATE OR REPLACE FUNCTION ifnull(a anycompatible, b anycompatible) RETURNS anycompatible
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT coalesce(a, b) $$;


-- ------------------------------------------------------------ group_concat
-- Agregado. NULL é pulado; o separador de cada linha vai ANTES do valor dela
-- (como string_agg e como o SQLite); separador NULL = nada; nenhum valor =
-- NULL; um valor vazio sozinho = ''. Número vira texto como o SQLite escreve.
CREATE OR REPLACE FUNCTION _cg_gc_passo(estado text, valor text, sep text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN valor IS NULL THEN estado
              WHEN estado IS NULL THEN valor
              ELSE estado || coalesce(sep, '') || valor END
$$;
CREATE OR REPLACE FUNCTION _cg_gc_passo1(estado text, valor text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT _cg_gc_passo(estado, valor, ',') $$;
CREATE OR REPLACE FUNCTION _cg_gc_passo_i(estado text, valor bigint, sep text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT _cg_gc_passo(estado, valor::text, sep) $$;
CREATE OR REPLACE FUNCTION _cg_gc_passo_i1(estado text, valor bigint) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT _cg_gc_passo(estado, valor::text, ',') $$;
CREATE OR REPLACE FUNCTION _cg_gc_passo_r(estado text, valor double precision, sep text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT _cg_gc_passo(estado, _cg_real_texto(valor), sep) $$;
CREATE OR REPLACE FUNCTION _cg_gc_passo_r1(estado text, valor double precision) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT _cg_gc_passo(estado, _cg_real_texto(valor), ',') $$;

CREATE OR REPLACE AGGREGATE group_concat(text) (SFUNC = _cg_gc_passo1, STYPE = text);
CREATE OR REPLACE AGGREGATE group_concat(text, text) (SFUNC = _cg_gc_passo, STYPE = text);
CREATE OR REPLACE AGGREGATE group_concat(bigint) (SFUNC = _cg_gc_passo_i1, STYPE = text);
CREATE OR REPLACE AGGREGATE group_concat(bigint, text) (SFUNC = _cg_gc_passo_i, STYPE = text);
CREATE OR REPLACE FUNCTION _cg_numeric_texto(x numeric) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN x = trunc(x) AND x BETWEEN -9223372036854775808 AND 9223372036854775807
              THEN trunc(x)::text ELSE _cg_real_texto(x::float8) END $$;
CREATE OR REPLACE FUNCTION _cg_gc_passo_n(estado text, valor numeric, sep text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT _cg_gc_passo(estado, _cg_numeric_texto(valor), sep) $$;
CREATE OR REPLACE FUNCTION _cg_gc_passo_n1(estado text, valor numeric) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT _cg_gc_passo(estado, _cg_numeric_texto(valor), ',') $$;
CREATE OR REPLACE FUNCTION _cg_gc_passo_i4(estado text, valor integer, sep text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT _cg_gc_passo(estado, valor::text, sep) $$;
CREATE OR REPLACE FUNCTION _cg_gc_passo_i41(estado text, valor integer) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT _cg_gc_passo(estado, valor::text, ',') $$;
CREATE OR REPLACE AGGREGATE group_concat(double precision) (SFUNC = _cg_gc_passo_r1, STYPE = text);
CREATE OR REPLACE AGGREGATE group_concat(numeric) (SFUNC = _cg_gc_passo_n1, STYPE = text);
CREATE OR REPLACE AGGREGATE group_concat(numeric, text) (SFUNC = _cg_gc_passo_n, STYPE = text);
CREATE OR REPLACE AGGREGATE group_concat(integer) (SFUNC = _cg_gc_passo_i41, STYPE = text);
CREATE OR REPLACE AGGREGATE group_concat(integer, text) (SFUNC = _cg_gc_passo_i4, STYPE = text);
CREATE OR REPLACE AGGREGATE group_concat(double precision, text) (SFUNC = _cg_gc_passo_r, STYPE = text);


-- ------------------------------------------------------------------- instr
CREATE OR REPLACE FUNCTION instr(texto text, sub text) RETURNS integer
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT strpos(texto, sub) $$;


-- ------------------------------------------------------- max/min escalares
-- O SQLite: max(a,b,...) devolve NULL se QUALQUER argumento for NULL
-- (greatest() do PostgreSQL ignora o NULL — por isso não é tradução direta).
-- 2 a 5 argumentos; o agregado de 1 argumento continua o do PostgreSQL.
CREATE OR REPLACE FUNCTION max(a anycompatible, b anycompatible) RETURNS anycompatible
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN a IS NULL OR b IS NULL THEN NULL ELSE greatest(a, b) END $$;
CREATE OR REPLACE FUNCTION max(a anycompatible, b anycompatible, c anycompatible) RETURNS anycompatible
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN a IS NULL OR b IS NULL OR c IS NULL THEN NULL ELSE greatest(a, b, c) END $$;
CREATE OR REPLACE FUNCTION max(a anycompatible, b anycompatible, c anycompatible, d anycompatible) RETURNS anycompatible
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN a IS NULL OR b IS NULL OR c IS NULL OR d IS NULL THEN NULL ELSE greatest(a, b, c, d) END $$;
CREATE OR REPLACE FUNCTION max(a anycompatible, b anycompatible, c anycompatible, d anycompatible, e anycompatible) RETURNS anycompatible
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN a IS NULL OR b IS NULL OR c IS NULL OR d IS NULL OR e IS NULL THEN NULL ELSE greatest(a, b, c, d, e) END $$;
CREATE OR REPLACE FUNCTION min(a anycompatible, b anycompatible) RETURNS anycompatible
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN a IS NULL OR b IS NULL THEN NULL ELSE least(a, b) END $$;
CREATE OR REPLACE FUNCTION min(a anycompatible, b anycompatible, c anycompatible) RETURNS anycompatible
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN a IS NULL OR b IS NULL OR c IS NULL THEN NULL ELSE least(a, b, c) END $$;
CREATE OR REPLACE FUNCTION min(a anycompatible, b anycompatible, c anycompatible, d anycompatible) RETURNS anycompatible
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN a IS NULL OR b IS NULL OR c IS NULL OR d IS NULL THEN NULL ELSE least(a, b, c, d) END $$;
CREATE OR REPLACE FUNCTION min(a anycompatible, b anycompatible, c anycompatible, d anycompatible, e anycompatible) RETURNS anycompatible
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN a IS NULL OR b IS NULL OR c IS NULL OR d IS NULL OR e IS NULL THEN NULL ELSE least(a, b, c, d, e) END $$;


-- ----------------------------------------------------------- sum(boolean)
-- No SQLite a comparação vale 0 ou 1, e `sum(x = 'S')` conta as linhas que
-- casam; no PostgreSQL ela é boolean e o sum não existia (P04: cnib,
-- gestor_financeiro). Como o sum do SQLite: inteiro, e NULL se não houver
-- nenhum valor que não seja NULL.
CREATE OR REPLACE FUNCTION _cg_soma_bool(s bigint, b boolean) RETURNS bigint
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN b IS NULL THEN s ELSE coalesce(s, 0) + b::int END $$;
CREATE OR REPLACE AGGREGATE sum(boolean) (SFUNC = _cg_soma_bool, STYPE = bigint);


-- ------------------------------------------------------------------ typeof
-- Aproximado: o tipo da COLUNA no PostgreSQL, e não o do valor guardado
-- (no SQLite uma coluna TEXT pode guardar um inteiro; aqui não).
CREATE OR REPLACE FUNCTION typeof(x text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT CASE WHEN x IS NULL THEN 'null' ELSE 'text' END $$;
CREATE OR REPLACE FUNCTION typeof(x bigint) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT CASE WHEN x IS NULL THEN 'null' ELSE 'integer' END $$;
CREATE OR REPLACE FUNCTION typeof(x integer) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT CASE WHEN x IS NULL THEN 'null' ELSE 'integer' END $$;
CREATE OR REPLACE FUNCTION typeof(x smallint) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT CASE WHEN x IS NULL THEN 'null' ELSE 'integer' END $$;
CREATE OR REPLACE FUNCTION typeof(x boolean) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT CASE WHEN x IS NULL THEN 'null' ELSE 'integer' END $$;
CREATE OR REPLACE FUNCTION typeof(x double precision) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT CASE WHEN x IS NULL THEN 'null' ELSE 'real' END $$;
CREATE OR REPLACE FUNCTION typeof(x real) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT CASE WHEN x IS NULL THEN 'null' ELSE 'real' END $$;
-- NUMERIC: a afinidade numérica do SQLite guarda 5.0 como inteiro 5
CREATE OR REPLACE FUNCTION typeof(x numeric) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN x IS NULL THEN 'null'
              WHEN x = trunc(x) AND x BETWEEN -9223372036854775808 AND 9223372036854775807 THEN 'integer'
              ELSE 'real' END $$;
CREATE OR REPLACE FUNCTION typeof(x bytea) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT CASE WHEN x IS NULL THEN 'null' ELSE 'blob' END $$;


-- ------------------------------------------------------------------ printf
-- Só o que o sistema pode precisar: %s %d %i %f %c %% com bandeiras '-' e
-- '0', largura e precisão (%05d, %.2f, %-10s). Os argumentos chegam como
-- TEXTO; com UM argumento numérico há sobrecargas tipadas. Hoje nenhum SQL
-- do sistema chama printf( nem format( (medido em 15/10/2026).
CREATE OR REPLACE FUNCTION printf(fmt text, VARIADIC args text[]) RETURNS text
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
  res text := ''; i int := 1; n int; m text[]; flags text; larg int; prec int;
  conv text; a text; k int := 0; v text; num float8; inteiro bigint; neg boolean;
BEGIN
  IF fmt IS NULL THEN RETURN NULL; END IF;
  n := length(fmt);
  WHILE i <= n LOOP
    IF substr(fmt, i, 1) <> '%' THEN
      res := res || substr(fmt, i, 1); i := i + 1; CONTINUE;
    END IF;
    m := regexp_match(substr(fmt, i), '^%([-0+ #!,]*)([0-9]*)(?:\.([0-9]*))?([a-zA-Z%])');
    IF m IS NULL THEN RETURN res; END IF;           -- o SQLite para no formato inválido
    i := i + length(substring(substr(fmt, i) FROM '^%[-0+ #!,]*[0-9]*(?:\.[0-9]*)?[a-zA-Z%]'));
    flags := m[1]; larg := nullif(m[2], '')::int; prec := CASE WHEN m[3] IS NULL THEN NULL ELSE coalesce(nullif(m[3], ''), '0')::int END;
    conv := m[4];
    IF conv = '%' THEN res := res || '%'; CONTINUE; END IF;
    k := k + 1;
    a := CASE WHEN args IS NOT NULL AND k <= coalesce(array_length(args, 1), 0) THEN args[k] END;
    IF conv IN ('d', 'i') THEN
      inteiro := coalesce(trunc(_cg_numero(substring(coalesce(a, '') FROM '^[\u0009-\u000d ]*[+-]?[0-9]*\.?[0-9]*(?:[eE][+-]?[0-9]+)?'))), 0)::bigint;
      neg := inteiro < 0;
      v := abs(inteiro)::text;
      IF prec IS NOT NULL AND length(v) < prec THEN v := lpad(v, prec, '0'); END IF;
      IF neg THEN v := '-' || v; ELSIF position('+' IN flags) > 0 THEN v := '+' || v; END IF;
      IF larg IS NOT NULL AND length(v) < larg THEN
        IF position('-' IN flags) > 0 THEN v := rpad(v, larg, ' ');
        ELSIF position('0' IN flags) > 0 THEN
          v := CASE WHEN left(v, 1) IN ('-', '+') THEN left(v, 1) || lpad(substr(v, 2), larg - 1, '0') ELSE lpad(v, larg, '0') END;
        ELSE v := lpad(v, larg, ' ');
        END IF;
      END IF;
    ELSIF conv IN ('f', 'g') THEN
      num := coalesce(_cg_numero(substring(coalesce(a, '') FROM '^[\u0009-\u000d ]*[+-]?[0-9]*\.?[0-9]*(?:[eE][+-]?[0-9]+)?')), 0);
      v := _cg_fmt_real(num, conv, coalesce(prec, 6), position('!' IN flags) > 0);
      IF larg IS NOT NULL AND length(v) < larg THEN
        IF position('-' IN flags) > 0 THEN v := rpad(v, larg, ' ');
        ELSIF position('0' IN flags) > 0 THEN
          v := CASE WHEN left(v, 1) = '-' THEN '-' || lpad(substr(v, 2), larg - 1, '0') ELSE lpad(v, larg, '0') END;
        ELSE v := lpad(v, larg, ' ');
        END IF;
      END IF;
    ELSIF conv IN ('s', 'z', 'c') THEN
      v := coalesce(a, '');
      IF conv = 'c' THEN v := left(v, 1); END IF;
      IF prec IS NOT NULL THEN v := left(v, prec); END IF;
      IF larg IS NOT NULL AND length(v) < larg THEN
        v := CASE WHEN position('-' IN flags) > 0 THEN rpad(v, larg, ' ') ELSE lpad(v, larg, ' ') END;
      END IF;
    ELSE
      RETURN res;        -- conversão que este emulador não conhece
    END IF;
    res := res || v;
  END LOOP;
  RETURN res;
END
$$;
CREATE OR REPLACE FUNCTION printf(fmt text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT printf(fmt, VARIADIC ARRAY[]::text[]) $$;
CREATE OR REPLACE FUNCTION printf(fmt text, a bigint) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT printf(fmt, VARIADIC ARRAY[a::text]) $$;
CREATE OR REPLACE FUNCTION printf(fmt text, a numeric) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT printf(fmt, VARIADIC ARRAY[a::text]) $$;
CREATE OR REPLACE FUNCTION printf(fmt text, a double precision) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT printf(fmt, VARIADIC ARRAY[_cg_real_texto(a)]) $$;


-- ------------------------------------------------------------- nome_da_casa
-- pt_schema.normalizar_nome, que fraude.py e rc_certidao.py registram por
-- con.create_function("nome_da_casa", 1, lambda v: normalizar_nome(v) or ""):
--     s = str(texto or "").strip()
--     t = NFD(s.lower()); tira as marcas da categoria Mn
--     re.sub(r"\s+", " ", t).strip()   -> e None vira ''
-- Reproduzida passo a passo, e NÃO com unaccent: a categoria Mn e o espaço
-- do Python (\s Unicode) são as classes geradas do unicodedata do Python
-- 3.11 (Unicode 14.0); minúscula Unicode completa pelo provedor embutido
-- (o LOWER da collation C só conhece ASCII — o mesmo defeito do SQLite).
-- ACRESCENTADO NA MIGRAÇÃO (16/10/2026): a minúscula Unicode completa vem do
-- `pg_unicode_fast` no PostgreSQL 18; no 16/17 (o Mac do teste), da ICU
-- (`und-x-icu`), que dá o mesmo resultado para o texto da casa.
-- O teste de existência olha o schema CORRENTE (o da instalação): a mesma
-- collation noutro schema não serve, porque não está no search_path.
DO $cg$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_collation WHERE collname = 'cg_minuscula'
                   AND collnamespace = current_schema()::regnamespace) THEN
    IF EXISTS (SELECT 1 FROM pg_collation WHERE collname = 'pg_unicode_fast') THEN
      CREATE COLLATION cg_minuscula FROM pg_unicode_fast;
    ELSE
      CREATE COLLATION cg_minuscula FROM "und-x-icu";
    END IF;
  END IF;
END $cg$;
-- CORRIGIDO 19/10/2026 (achado no PostgreSQL 18 do servidor): do 17 em diante,
-- CREATE INDEX, REINDEX, ANALYZE de indice de expressao e pg_restore avaliam a
-- expressao com search_path = pg_catalog. A collation sem schema nao era achada
-- no inlining. Por isso a funcao nasce com o schema escrito (o corrente: `public`
-- na instalacao, o do teste no teste) -- e continua SQL inlinavel, sem SET.
DO $cg_nome$ BEGIN EXECUTE format($fn$
CREATE OR REPLACE FUNCTION nome_da_casa(texto text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $f$
  SELECT CASE WHEN texto IS NULL THEN '' ELSE
    btrim(regexp_replace(
      regexp_replace(normalize(lower(texto COLLATE %I.cg_minuscula), NFD),
                     '[\u0300-\u036f\u0483-\u0487\u0591-\u05bd\u05bf\u05c1-\u05c2\u05c4-\u05c5\u05c7\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06dc\u06df-\u06e4\u06e7-\u06e8\u06ea-\u06ed\u0711\u0730-\u074a\u07a6-\u07b0\u07eb-\u07f3\u07fd\u0816-\u0819\u081b-\u0823\u0825-\u0827\u0829-\u082d\u0859-\u085b\u0898-\u089f\u08ca-\u08e1\u08e3-\u0902\u093a\u093c\u0941-\u0948\u094d\u0951-\u0957\u0962-\u0963\u0981\u09bc\u09c1-\u09c4\u09cd\u09e2-\u09e3\u09fe\u0a01-\u0a02\u0a3c\u0a41-\u0a42\u0a47-\u0a48\u0a4b-\u0a4d\u0a51\u0a70-\u0a71\u0a75\u0a81-\u0a82\u0abc\u0ac1-\u0ac5\u0ac7-\u0ac8\u0acd\u0ae2-\u0ae3\u0afa-\u0aff\u0b01\u0b3c\u0b3f\u0b41-\u0b44\u0b4d\u0b55-\u0b56\u0b62-\u0b63\u0b82\u0bc0\u0bcd\u0c00\u0c04\u0c3c\u0c3e-\u0c40\u0c46-\u0c48\u0c4a-\u0c4d\u0c55-\u0c56\u0c62-\u0c63\u0c81\u0cbc\u0cbf\u0cc6\u0ccc-\u0ccd\u0ce2-\u0ce3\u0d00-\u0d01\u0d3b-\u0d3c\u0d41-\u0d44\u0d4d\u0d62-\u0d63\u0d81\u0dca\u0dd2-\u0dd4\u0dd6\u0e31\u0e34-\u0e3a\u0e47-\u0e4e\u0eb1\u0eb4-\u0ebc\u0ec8-\u0ecd\u0f18-\u0f19\u0f35\u0f37\u0f39\u0f71-\u0f7e\u0f80-\u0f84\u0f86-\u0f87\u0f8d-\u0f97\u0f99-\u0fbc\u0fc6\u102d-\u1030\u1032-\u1037\u1039-\u103a\u103d-\u103e\u1058-\u1059\u105e-\u1060\u1071-\u1074\u1082\u1085-\u1086\u108d\u109d\u135d-\u135f\u1712-\u1714\u1732-\u1733\u1752-\u1753\u1772-\u1773\u17b4-\u17b5\u17b7-\u17bd\u17c6\u17c9-\u17d3\u17dd\u180b-\u180d\u180f\u1885-\u1886\u18a9\u1920-\u1922\u1927-\u1928\u1932\u1939-\u193b\u1a17-\u1a18\u1a1b\u1a56\u1a58-\u1a5e\u1a60\u1a62\u1a65-\u1a6c\u1a73-\u1a7c\u1a7f\u1ab0-\u1abd\u1abf-\u1ace\u1b00-\u1b03\u1b34\u1b36-\u1b3a\u1b3c\u1b42\u1b6b-\u1b73\u1b80-\u1b81\u1ba2-\u1ba5\u1ba8-\u1ba9\u1bab-\u1bad\u1be6\u1be8-\u1be9\u1bed\u1bef-\u1bf1\u1c2c-\u1c33\u1c36-\u1c37\u1cd0-\u1cd2\u1cd4-\u1ce0\u1ce2-\u1ce8\u1ced\u1cf4\u1cf8-\u1cf9\u1dc0-\u1dff\u20d0-\u20dc\u20e1\u20e5-\u20f0\u2cef-\u2cf1\u2d7f\u2de0-\u2dff\u302a-\u302d\u3099-\u309a\ua66f\ua674-\ua67d\ua69e-\ua69f\ua6f0-\ua6f1\ua802\ua806\ua80b\ua825-\ua826\ua82c\ua8c4-\ua8c5\ua8e0-\ua8f1\ua8ff\ua926-\ua92d\ua947-\ua951\ua980-\ua982\ua9b3\ua9b6-\ua9b9\ua9bc-\ua9bd\ua9e5\uaa29-\uaa2e\uaa31-\uaa32\uaa35-\uaa36\uaa43\uaa4c\uaa7c\uaab0\uaab2-\uaab4\uaab7-\uaab8\uaabe-\uaabf\uaac1\uaaec-\uaaed\uaaf6\uabe5\uabe8\uabed\ufb1e\ufe00-\ufe0f\ufe20-\ufe2f\U000101fd\U000102e0\U00010376-\U0001037a\U00010a01-\U00010a03\U00010a05-\U00010a06\U00010a0c-\U00010a0f\U00010a38-\U00010a3a\U00010a3f\U00010ae5-\U00010ae6\U00010d24-\U00010d27\U00010eab-\U00010eac\U00010f46-\U00010f50\U00010f82-\U00010f85\U00011001\U00011038-\U00011046\U00011070\U00011073-\U00011074\U0001107f-\U00011081\U000110b3-\U000110b6\U000110b9-\U000110ba\U000110c2\U00011100-\U00011102\U00011127-\U0001112b\U0001112d-\U00011134\U00011173\U00011180-\U00011181\U000111b6-\U000111be\U000111c9-\U000111cc\U000111cf\U0001122f-\U00011231\U00011234\U00011236-\U00011237\U0001123e\U000112df\U000112e3-\U000112ea\U00011300-\U00011301\U0001133b-\U0001133c\U00011340\U00011366-\U0001136c\U00011370-\U00011374\U00011438-\U0001143f\U00011442-\U00011444\U00011446\U0001145e\U000114b3-\U000114b8\U000114ba\U000114bf-\U000114c0\U000114c2-\U000114c3\U000115b2-\U000115b5\U000115bc-\U000115bd\U000115bf-\U000115c0\U000115dc-\U000115dd\U00011633-\U0001163a\U0001163d\U0001163f-\U00011640\U000116ab\U000116ad\U000116b0-\U000116b5\U000116b7\U0001171d-\U0001171f\U00011722-\U00011725\U00011727-\U0001172b\U0001182f-\U00011837\U00011839-\U0001183a\U0001193b-\U0001193c\U0001193e\U00011943\U000119d4-\U000119d7\U000119da-\U000119db\U000119e0\U00011a01-\U00011a0a\U00011a33-\U00011a38\U00011a3b-\U00011a3e\U00011a47\U00011a51-\U00011a56\U00011a59-\U00011a5b\U00011a8a-\U00011a96\U00011a98-\U00011a99\U00011c30-\U00011c36\U00011c38-\U00011c3d\U00011c3f\U00011c92-\U00011ca7\U00011caa-\U00011cb0\U00011cb2-\U00011cb3\U00011cb5-\U00011cb6\U00011d31-\U00011d36\U00011d3a\U00011d3c-\U00011d3d\U00011d3f-\U00011d45\U00011d47\U00011d90-\U00011d91\U00011d95\U00011d97\U00011ef3-\U00011ef4\U00016af0-\U00016af4\U00016b30-\U00016b36\U00016f4f\U00016f8f-\U00016f92\U00016fe4\U0001bc9d-\U0001bc9e\U0001cf00-\U0001cf2d\U0001cf30-\U0001cf46\U0001d167-\U0001d169\U0001d17b-\U0001d182\U0001d185-\U0001d18b\U0001d1aa-\U0001d1ad\U0001d242-\U0001d244\U0001da00-\U0001da36\U0001da3b-\U0001da6c\U0001da75\U0001da84\U0001da9b-\U0001da9f\U0001daa1-\U0001daaf\U0001e000-\U0001e006\U0001e008-\U0001e018\U0001e01b-\U0001e021\U0001e023-\U0001e024\U0001e026-\U0001e02a\U0001e130-\U0001e136\U0001e2ae\U0001e2ec-\U0001e2ef\U0001e8d0-\U0001e8d6\U0001e944-\U0001e94a\U000e0100-\U000e01ef]', '', 'g'),
      '[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028-\u2029\u202f\u205f\u3000]+', ' ', 'g'), ' ')
  END
$f$$fn$, current_schema());
END $cg_nome$;
CREATE OR REPLACE FUNCTION nome_da_casa(texto bigint) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN texto IS NULL OR texto = 0 THEN '' ELSE texto::text END $$;


-- ------------------------------------------------------------------ digitos
-- protesto_cenprot.so_digitos: re.sub(r"\D+", "", str(valor or "")) — o \d
-- do Python é Unicode (categoria Nd), e a classe abaixo é a dele.
-- (protesto_imagens registra o MESMO nome com c.isdigit(), que também aceita
-- sobrescritos como «²»: as duas versões do Python já divergem entre si.)
CREATE OR REPLACE FUNCTION digitos(valor text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $f$
  SELECT CASE WHEN valor IS NULL THEN '' ELSE regexp_replace(valor, '[^\u0030-\u0039\u0660-\u0669\u06f0-\u06f9\u07c0-\u07c9\u0966-\u096f\u09e6-\u09ef\u0a66-\u0a6f\u0ae6-\u0aef\u0b66-\u0b6f\u0be6-\u0bef\u0c66-\u0c6f\u0ce6-\u0cef\u0d66-\u0d6f\u0de6-\u0def\u0e50-\u0e59\u0ed0-\u0ed9\u0f20-\u0f29\u1040-\u1049\u1090-\u1099\u17e0-\u17e9\u1810-\u1819\u1946-\u194f\u19d0-\u19d9\u1a80-\u1a89\u1a90-\u1a99\u1b50-\u1b59\u1bb0-\u1bb9\u1c40-\u1c49\u1c50-\u1c59\ua620-\ua629\ua8d0-\ua8d9\ua900-\ua909\ua9d0-\ua9d9\ua9f0-\ua9f9\uaa50-\uaa59\uabf0-\uabf9\uff10-\uff19\U000104a0-\U000104a9\U00010d30-\U00010d39\U00011066-\U0001106f\U000110f0-\U000110f9\U00011136-\U0001113f\U000111d0-\U000111d9\U000112f0-\U000112f9\U00011450-\U00011459\U000114d0-\U000114d9\U00011650-\U00011659\U000116c0-\U000116c9\U00011730-\U00011739\U000118e0-\U000118e9\U00011950-\U00011959\U00011c50-\U00011c59\U00011d50-\U00011d59\U00011da0-\U00011da9\U00016a60-\U00016a69\U00016ac0-\U00016ac9\U00016b50-\U00016b59\U0001d7ce-\U0001d7ff\U0001e140-\U0001e149\U0001e2f0-\U0001e2f9\U0001e950-\U0001e959\U0001fbf0-\U0001fbf9]+', '', 'g') END
$f$;
CREATE OR REPLACE FUNCTION digitos(valor bigint) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN valor IS NULL OR valor = 0 THEN '' ELSE abs(valor)::text END $$;
CREATE OR REPLACE FUNCTION digitos(valor integer) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN valor IS NULL OR valor = 0 THEN '' ELSE abs(valor::bigint)::text END $$;
CREATE OR REPLACE FUNCTION digitos(valor numeric) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN valor IS NULL OR valor = 0 THEN '' ELSE regexp_replace(valor::text, '[^0-9]+', '', 'g') END $$;
-- str(float) do Python: 5.0 -> '5.0' (o zero da fração conta como dígito)
CREATE OR REPLACE FUNCTION digitos(valor double precision) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN valor IS NULL OR valor = 0 THEN ''
              WHEN valor = trunc(valor) AND abs(valor) < 1e16 THEN abs(valor)::bigint::text || '0'
              ELSE regexp_replace(valor::text, '[^0-9]+', '', 'g') END $$;

-- cg_inteiro: o CAST(x AS INTEGER) do SQLite (15/10/2026, pedido do lote L2).
-- O SQLite não estoura com texto: lê os brancos do começo, o sinal e os
-- dígitos iniciais ('12A' -> 12, '  -5x' -> -5, '1.9' -> 1) e devolve 0 quando
-- não há dígito ('' e 'abc' -> 0). O CAST do PostgreSQL estouraria. NULL -> NULL.
CREATE OR REPLACE FUNCTION cg_inteiro(t text) RETURNS bigint
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN t IS NULL THEN NULL
              ELSE COALESCE(substring(ltrim(t, E' \t\n\r') from '^[+-]?[0-9]+')::bigint, 0) END $$;
CREATE OR REPLACE FUNCTION cg_inteiro(n integer) RETURNS bigint
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT n::bigint $$;
CREATE OR REPLACE FUNCTION cg_inteiro(n bigint) RETURNS bigint
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT n $$;
CREATE OR REPLACE FUNCTION cg_inteiro(n numeric) RETURNS bigint
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT trunc(n)::bigint $$;
CREATE OR REPLACE FUNCTION cg_inteiro(n double precision) RETURNS bigint
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT trunc(n)::bigint $$;

-- cg_glob_regex: o padrão do GLOB do SQLite (sensível a caixa, casa o texto
-- INTEIRO) como expressão regular: * -> .*, ? -> ., [..] fica, o resto escapa.
-- Usado quando o padrão chega como parâmetro; o literal a camada converte antes.
CREATE OR REPLACE FUNCTION cg_glob_regex(p text) RETURNS text
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
  saida text := '^';
  i int := 1;
  n int := length(p);
  c text;
  fim int;
BEGIN
  IF p IS NULL THEN RETURN NULL; END IF;
  WHILE i <= n LOOP
    c := substr(p, i, 1);
    IF c = '*' THEN saida := saida || '.*';
    ELSIF c = '?' THEN saida := saida || '.';
    ELSIF c = '[' THEN
      fim := strpos(substr(p, i + 2), ']');
      IF fim = 0 THEN saida := saida || '\['; ELSE
        saida := saida || replace(substr(p, i, fim + 2), '\', '\\');
        i := i + fim + 1;
      END IF;
    ELSE saida := saida || regexp_replace(c, '([.^$+(){}|\\])', '\\\1', 'g');
    END IF;
    i := i + 1;
  END LOOP;
  RETURN saida || '$';
END $$;


-- ACRESCENTADO NA MIGRAÇÃO (16/10/2026): `1 << coluna`. No SQLite tudo é
-- inteiro de 64 bits; no PostgreSQL o deslocamento só aceita integer à direita.
CREATE OR REPLACE FUNCTION cg__shl(a bigint, b bigint) RETURNS bigint LANGUAGE sql IMMUTABLE AS $$ SELECT a << b::int $$;
CREATE OR REPLACE FUNCTION cg__shr(a bigint, b bigint) RETURNS bigint LANGUAGE sql IMMUTABLE AS $$ SELECT a >> b::int $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_operator WHERE oprname = '<<' AND oprleft = 'bigint'::regtype AND oprright = 'bigint'::regtype
                   AND oprnamespace = current_schema()::regnamespace) THEN
    CREATE OPERATOR << (LEFTARG = bigint, RIGHTARG = bigint, FUNCTION = cg__shl);
    CREATE OPERATOR >> (LEFTARG = bigint, RIGHTARG = bigint, FUNCTION = cg__shr);
  END IF;
END $$;


-- A CORRENTE DE HASH DA AUDITORIA (revisão de segurança de 22/10/2026).
-- Cada linha de `audit_logs` aponta o hash da anterior e leva o seu; quem
-- apagar ou mexer numa linha quebra a corrente, e a conferência da casa
-- acusa. É um gatilho, e não código Python, porque TRINTA E UM arquivos
-- escrevem na tabela por INSERT direto (ferramentas, agentes, scripts): a
-- régua tem de valer para todos, e vale no banco. A trava consultiva
-- serializa só as escritas da auditoria, o bastante para a corrente não
-- bifurcar com dois balcões gravando ao mesmo tempo. O texto do hash é o
-- de `auditoria_cadeia.hash_da_linha`, campo a campo, com `|` entre eles e
-- vazio onde é NULL — os dois lados têm de bater byte a byte.
CREATE OR REPLACE FUNCTION cg_auditoria_encadear() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  anterior text;
  bruto text;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext(TG_TABLE_SCHEMA || '.audit_logs.cadeia'));
  EXECUTE format('SELECT hash_linha FROM %I.audit_logs WHERE hash_linha IS NOT NULL ORDER BY id DESC LIMIT 1',
                 TG_TABLE_SCHEMA) INTO anterior;
  NEW.hash_anterior := anterior;
  bruto := coalesce(NEW.ts, '') || '|' || coalesce(NEW.user_id::text, '') || '|'
        || coalesce(NEW.username_snapshot, '') || '|' || coalesce(NEW.action, '') || '|'
        || coalesce(NEW.entity_type, '') || '|' || coalesce(NEW.entity_id::text, '') || '|'
        || coalesce(NEW.details, '') || '|' || coalesce(NEW.ip_address, '') || '|'
        || coalesce(anterior, '');
  NEW.hash_linha := encode(sha256(convert_to(bruto, 'UTF8')), 'hex');
  RETURN NEW;
END $$;
