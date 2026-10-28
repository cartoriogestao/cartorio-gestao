-- =============================================================================
-- conferir_referencias_de_selo.sql — Cartório Gestão, antes e depois da virada.
-- Lote LX25 (20/10/2026). A medida que a revisão do LX24 pediu: quantas
-- referências de selo da produção estão FORA da forma canônica.
--
-- POR QUE IMPORTA
--   O LX24 passou a gravar e procurar a referência do selo numa grafia só
--   (`ato_selado.referencia_do_selo`: tabela em minúscula, número sem zero à
--   esquerda, cada pedaço sem espaço em volta). O que foi gravado ANTES está
--   no texto cru: `cx_selo_coberturas.referencia` (a chave da cobertura) e
--   `sd_selos.referencia` (o texto de que saiu o SID). O LX25 procura pela
--   canônica E pela grafia crua recebida; o que esta conferência mede é se há
--   ato gravado numa grafia que nenhuma das duas acha — por exemplo, gravado
--   «PT_ATOS:01» e pedido hoje como `pt_atos:1`. Se tudo der zero, não há
--   de-para a fazer.
--
-- SÓ LEITURA, SÓ CONTAGENS. Abre a transação em READ ONLY e termina em
-- ROLLBACK: o PostgreSQL recusa qualquer escrita lá dentro, e este arquivo
-- não tem nenhuma. Não mostra referência nem número de selo, só quantos.
-- Pode rodar no horário do balcão.
--
-- O QUE SAI, POR TABELA
--   com_referencia                linhas com referência preenchida
--   fora_da_forma_canonica        referência diferente da canônica
--   de_ato_fora_da_forma          dessas, as que são de ato (`tabela:número`):
--                                 as que a troca de grafia pode desencontrar
--   atos_com_mais_de_uma_grafia   formas canônicas gravadas com 2+ textos
--                                 diferentes (o mesmo ato pago duas vezes?)
--   Tabela que não existe neste banco (`cx_selo_coberturas` nasce na subida
--   do sistema novo) sai como «tabela ausente», e não como erro.
--
-- A RÉGUA É A DO PYTHON: a lista de tabelas de ato é `ato_selado.TABELAS_DE_ATO`
-- (o teste `test_selo_e_caixa` confere que as duas são iguais e que as
-- contagens batem com `referencia_do_selo`).
--
-- COMO RODAR:
--     psql -h 127.0.0.1 -p 5434 -U cg -d cartorio -X -f conferir_referencias_de_selo.sql
--   variável opcional:
--     -v schema=producao   schema alvo (padrão: producao). Vira o search_path.
-- =============================================================================

\set ON_ERROR_STOP on
\encoding UTF8
\if :{?schema}
\else
  \set schema producao
\endif

BEGIN READ ONLY;
SET LOCAL search_path = :"schema", public;
SET LOCAL statement_timeout = '120s';

-- A consulta de cada tabela se monta com `format` e roda por `query_to_xml`:
-- assim a tabela que não existe é pulada (`to_regclass`), em vez de derrubar
-- o arquivo inteiro.
WITH tabelas_de_ato(nome) AS (
    -- `ato_selado.TABELAS_DE_ATO`, na mesma ordem
    VALUES
           ('pt_atos'),
           ('pt_certidoes'),
           ('at_certidoes'),
           ('rc_certidoes'),
           ('rc_materializacoes'),
           ('rc_atos'),
           ('rg_atos'),
           ('ra_atos'),
           ('ri_atos'),
           ('nt_atos'),
           ('nt_certidoes'),
           ('nt_reconhecimentos'),
           ('nt_autenticacoes'),
           ('nt_cartoes'),
           ('nt_sinais_reconhecimentos'),
           ('ri_protocolos'),
           ('hc_habilitacoes'),
           ('ri_certidoes'),
           ('ri_matriculas'),
           ('rg_notificacao_diligencias'),
           ('rg_notificacao_certidoes'),
           ('rg_livros_contabeis'),
           ('nt_publicas_formas'),
           ('nt_comunicacoes_veiculo'),
           ('ri_conferencias')
), alvo(tabela) AS (
    VALUES ('cx_selo_coberturas'), ('sd_selos')
), lido AS (
    SELECT tabela,
           to_regclass(tabela) IS NOT NULL AS existe,
           CASE WHEN to_regclass(tabela) IS NOT NULL THEN
               query_to_xml(format(
                   $q$WITH partes AS (
                          SELECT referencia,
                                 ARRAY(SELECT regexp_replace(u.p, '^\s+|\s+$', '', 'g')
                                         FROM unnest(string_to_array(referencia, ':'))
                                              WITH ORDINALITY AS u(p, n)
                                        ORDER BY u.n) AS p
                            FROM %I
                           WHERE referencia IS NOT NULL
                      ), regua AS (
                          SELECT referencia,
                                 (cardinality(p) >= 2
                                  AND lower(p[1]) = ANY (%L::text[])
                                  AND p[2] ~ '^[0-9]+$') AS de_ato,
                                 p
                            FROM partes
                      ), canon AS (
                          SELECT referencia, de_ato,
                                 CASE WHEN de_ato
                                      THEN array_to_string(
                                               ARRAY[lower(p[1]), (p[2]::numeric)::text]
                                               || p[3:], ':')
                                      ELSE regexp_replace(referencia, '^\s+|\s+$', '', 'g')
                                 END AS canonica
                            FROM regua
                      )
                      SELECT count(*) AS com_referencia,
                             count(*) FILTER (WHERE referencia <> canonica)
                                 AS fora_da_forma_canonica,
                             count(*) FILTER (WHERE referencia <> canonica AND de_ato)
                                 AS de_ato_fora_da_forma,
                             (SELECT count(*) FROM (
                                  SELECT canonica FROM canon
                                   GROUP BY canonica
                                  HAVING count(DISTINCT referencia) > 1) g)
                                 AS atos_com_mais_de_uma_grafia
                        FROM canon$q$,
                   tabela,
                   (SELECT array_agg(nome ORDER BY nome) FROM tabelas_de_ato)::text),
                 false, true, '')
           END AS x
      FROM alvo
)
SELECT tabela,
       CASE WHEN existe THEN 'medida' ELSE 'tabela ausente' END AS situacao,
       CASE WHEN existe THEN (xpath('/row/com_referencia/text()', x))[1]::text::bigint
       END AS com_referencia,
       CASE WHEN existe THEN (xpath('/row/fora_da_forma_canonica/text()', x))[1]::text::bigint
       END AS fora_da_forma_canonica,
       CASE WHEN existe THEN (xpath('/row/de_ato_fora_da_forma/text()', x))[1]::text::bigint
       END AS de_ato_fora_da_forma,
       CASE WHEN existe THEN (xpath('/row/atos_com_mais_de_uma_grafia/text()', x))[1]::text::bigint
       END AS atos_com_mais_de_uma_grafia
  FROM lido
 ORDER BY tabela;

ROLLBACK;
