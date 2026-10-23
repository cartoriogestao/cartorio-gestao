-- =============================================================================
-- conferir_dados_ls02.sql — Cartório Gestão, depois da virada.
-- Lote LX12 (19/10/2026). As duas conferências de «Dado que pode estar errado
-- na produção» da auditoria de segurança LS02 (relatorios/LS02.md).
--
-- SÓ LEITURA. Abre a transação em READ ONLY e termina em ROLLBACK: o
-- PostgreSQL recusa qualquer escrita lá dentro, e este arquivo não tem
-- nenhuma. Pode rodar no horário do balcão.
--
-- SEM DADO PESSOAL NA SAÍDA: o teor é a qualificação das partes e o nome do
-- arquivo da ficha leva o número da matrícula. A saída volta para a equipe do
-- Mac, e por isso mostra só CONTAGENS e IDS — nunca o texto.
--
-- O QUE CONFERE
--   1. `ri_imagens.nome_arquivo` com `/`, `\` ou `:`, ou igual a `.`/`..`:
--      gravado pelo «renomear» antes do conserto C9 do LS02, ou vindo de
--      carga. A cópia para o acervo agora o recusa e diz qual; os ids daqui
--      são as fichas a renomear à mão na tela do RI.
--   2. Teor com `<script`, `<iframe`/`<object`/`<embed`/`<svg`, atributo
--      `on...=` dentro de etiqueta, ou `javascript:` — em `nt_atos`,
--      `nt_certidoes`, `ri_rascunhos` e `rc_assentos`. Desde o LS02 ele não
--      roda mais na tela (`sem_script`), mas o texto continua no banco: os ids
--      daqui são os teores a olhar com o oficial. Tabela que ainda não existe
--      neste banco (ex.: `nt_certidoes`, que nasce na primeira certidão das
--      notas) sai como «tabela ausente», e não como erro.
--
-- COMO RODAR:
--     psql -h 127.0.0.1 -p 5434 -U cg -d cartorio -X -f conferir_dados_ls02.sql
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

-- ------------------------------------------- 1. a ficha do RI com pasta no nome
SELECT 'ri_imagens.nome_arquivo com / \ : . ..' AS conferencia,
       count(*) AS quantos,
       coalesce(string_agg(id::text, ',' ORDER BY id), '') AS ids
  FROM ri_imagens
 WHERE nome_arquivo ~ '[/\\:]' OR nome_arquivo IN ('.', '..');

-- --------------------------------------------- 2. o teor que levava script
-- A consulta de cada tabela se monta com `format` e roda por `query_to_xml`:
-- assim a tabela que não existe é pulada (`to_regclass`), em vez de derrubar
-- o arquivo inteiro.
WITH alvo(tabela) AS (
    VALUES ('nt_atos'), ('nt_certidoes'), ('ri_rascunhos'), ('rc_assentos')
), lido AS (
    SELECT tabela,
           to_regclass(tabela) IS NOT NULL AS existe,
           CASE WHEN to_regclass(tabela) IS NOT NULL THEN
               query_to_xml(format(
                   $q$SELECT count(*) AS n,
                             coalesce(string_agg(id::text, ',' ORDER BY id), '') AS ids
                        FROM %I
                       WHERE teor ~* %L$q$,
                   tabela,
                   '<\s*/?\s*(script|iframe|object|embed|svg)\M'
                   || '|<[^>]*[\s/"'']on[a-z]+\s*='
                   || '|javascript\s*:'),
                 false, true, '')
           END AS x
      FROM alvo
)
SELECT tabela || '.teor com script' AS conferencia,
       CASE WHEN existe THEN (xpath('/row/n/text()', x))[1]::text::bigint END AS quantos,
       CASE WHEN existe THEN coalesce((xpath('/row/ids/text()', x))[1]::text, '')
            ELSE 'tabela ausente' END AS ids
  FROM lido
 ORDER BY tabela;

ROLLBACK;
