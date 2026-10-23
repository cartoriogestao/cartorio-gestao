# Virada para o PostgreSQL: as 20 tabelas que a subida não criava, e o acervo do E-Ofício

Lote LH09, 21/10/2026. Medição só de estrutura, sem dado:
`relatorios/COMPARACAO_SQLITE_REAL.md` e `relatorios/ESTRUTURA_TABELAS_FALTANDO.md`
(da pasta da migração). O banco real da produção não foi aberto aqui.

## 1. O que estava errado

O banco SQLite da produção tem 20 tabelas, quase todas com dados, que o esquema
criado por `create_app` num PostgreSQL vazio não tinha. Cada módulo dono criava a
sua tabela **preguiçoso**: na primeira vez que a função dele rodava (o compliance
na rodada, o gestor ao registrar um envio, a leitura da IA ao ler, e assim por
diante). Por isso a tabela existia no SQLite da produção, onde as funções já
tinham rodado, e não existia no banco recém-subido.

Duas consequências:

- a carga da virada não tinha onde pôr as linhas com o tipo que o código grava;
- a conferência da carga (`python banco_pg.py conferir-carga`) acusava as 20 como
  «não vieram».

## 2. O que mudou

- **A subida cria as 19 tabelas do sistema.** `Database.init_schema`
  (`database.py`) chama o `init` de cada módulo dono, que é o mesmo DDL que o
  módulo já rodava sozinho. Ele usa `IF NOT EXISTS` e é idempotente; nenhuma das
  19 tem chave estrangeira. A criação preguiçosa continua nos módulos, para o
  banco que ainda não passou pela subida.
- **`_ping` não é do sistema.** Nenhum código a cria: ela não aparece no código,
  nas ferramentas nem na história do repositório. É uma coluna `x` sem tipo, com
  0 linhas, sobra de um teste de escrita feito à mão no servidor. A subida não a
  cria. A conferência da carga a lista em `tabelas_ignoradas` (o aviso, também
  impresso na saída de erro da linha de comando) e não dá a carga por incompleta
  por causa dela (`banco_pg.TABELAS_FORA_DA_CARGA`).
- A tela GET das leituras do gestor continua sem escrever. Com `ge_leituras` de
  pé desde a subida, `gestor_leitura.achados_vigentes` só roda o esquema quando a
  tabela falta.

## 3. Tabela → quem cria → como a carga a leva

«Linhas» é a contagem medida na produção (sem dado). «Quem cria» é o `init` do
módulo dono. Desde o LH09, ele é chamado também pela subida
(`database.Database.init_schema`).

| tabela | linhas | quem cria | quem grava e lê |
|---|---:|---|---|
| `cp_achados` | 21 | `compliance.init_schema` | `compliance.gravar` / `rodar` (o fiscal dos agentes) |
| `cp_execucoes` | 16 | `compliance.init_schema` | `compliance.rodar` |
| `cp_fotografias` | 104 | `compliance.init_schema` | `compliance.regra_config_sem_rastro` |
| `cp_mudancas` | 12 | `compliance.init_schema` | `compliance.regra_config_sem_rastro` |
| `ge_achados` | 344 | `gestor_schema.init_gestor_schema` | `gestor_rotina`/`gestor_conferencia`, `gestor_envios.pendentes`, `gestor_rcpn`, `compliance` |
| `ge_envios` | 25 | `gestor_schema.init_gestor_schema` | `gestor_envios.registrar`/`recentes`, `gestor_cargas_rcpn`, `compliance` |
| `ge_execucoes` | 70 | `gestor_schema.init_gestor_schema` | `gestor_rotina`, `oficial_robos`, `compliance` |
| `ge_leituras` | 90 | `gestor_leitura.init_leitura_schema` | `gestor_leitura.ler_pendentes`/`achados_vigentes`, `gestor_web`, `oficial_robos` |
| `ge_onr_cargas` | 115 | `gestor_schema.init_gestor_schema` | `gestor_cargas_ri` |
| `ge_responsaveis` | 10 | `gestor_schema.init_gestor_schema` | `gestor_rotina` (distribuição), `compliance`, `oficial_*` |
| `ge_triagens` | 39 | `gestor_expedientes.init_schema` | `gestor_expedientes.triar_pendentes`/`para_ciencia`, `compliance` |
| `mt_alertas_propostos` | 42 | `malote_fraudes.init_schema` / `init_schema_ia` | `malote_fraudes.carregar`/`revisar`/`aplicar`/`tratar_grupo` |
| `mt_arquivos` | 27 | `malote_agente.init_schema` | `malote_agente.cadastrar`, `malote_fraudes.tratar_grupo`, `compliance` |
| `mt_execucoes` | 5 | `malote_agente.init_schema` | `malote_agente.rodada` |
| `mt_fraude_leituras` | 1 | `malote_fraudes.init_schema_ia` | `malote_fraudes._registrar_leitura` |
| `rc_leituras` | 11 | `rc_leitura_documentos.init_schema` | `rc_leitura_documentos` (abrir/concluir/uma/lista), `rc_leitura_web` |
| `ri_onus_sugestoes` | 2 | `ri_onus_ia.init_schema` | `ri_onus_ia.pedir`/`executar`/`ultima`, `ri_onus_ia_web` |
| `rv_anexos_lidos` | 21 | `revisao_anexos.init_schema` | `revisao_anexos.ler` |
| `rv_revisoes` | 69 | `revisao_previa.init_schema` | `revisao_previa.pedir`/`mostrar`/`exigir_para_lavrar`, `gestor_conferencia`, `gestor_web`, `tools/revisao_em_lote.py` |
| `_ping` | 0 | **ninguém** (não é do sistema) | ninguém. A carga a ignora; a conferência avisa |

**Como a carga leva as 19.** As colunas, as chaves únicas e os índices (com o
mesmo nome) do esquema do código são os do CREATE TABLE da produção. O código
tem colunas a mais só onde elas aceitam NULL: `rv_anexos_lidos.paginas_triadas`,
que veio do LX13. Os tipos guardam o que a produção tem: `INTEGER` vira `integer`
ou `bigint`, `REAL` vira `double precision` (só `rc_leituras.custo_estimado`) e
`TEXT` vira `text`. Isso vale nos dois caminhos de carga:

1. **Carga que recria o schema a partir do arquivo** (roteiro da virada, passo B3:
   `tools/migrar_para_postgres.py --schema producao --recriar`; a ordem dos passos
   está em `docs/ROTEIRO_DA_VIRADA.md`). A carga cria as 20 com
   o DDL do arquivo: `INTEGER` → `bigint`, `REAL` → `double precision`, `TEXT` →
   `text`, `id` com identidade. Depois a primeira subida do código (B6) as
   encontra: o `CREATE TABLE IF NOT EXISTS` não faz nada, o índice de mesmo nome
   também não, e só entra a coluna tardia (`rv_anexos_lidos.paginas_triadas`).
   A `_ping` pode vir junto, vazia, e não atrapalha.
2. **Carga num schema que o código já subiu** (tabela existente recebe as linhas
   pelas colunas que existem dos dois lados, como em `tests/test_banco_pg_virada.py`).
   As 19 já estão lá, com os tipos do código. A `_ping` fica de fora.

Depois da carga e do ajuste (B4), e antes de subir o código,
`python banco_pg.py conferir-carga <copia.sqlite3>` tem de sair com 0. A `_ping`
aparece só em `tabelas_ignoradas`, e o que o ajuste guardou aparece em AVISO, sem
pesar (LH10).

A prova está em `tests/test_banco_pg_tabelas_da_producao.py`. Ali há:

- a subida num banco vazio, conferida contra o CREATE TABLE da produção (colunas,
  tipos, NOT NULL, chaves únicas e índices);
- a carga de uma linha de exemplo por tabela, com a conferência fechando;
- um teste por módulo dono que grava e lê uma linha com o esquema preguiçoso
  desligado.

## 4. O acervo do E-Ofício NÃO vai para o PostgreSQL

`acervo_eoficio.sqlite3` (229 tabelas `tb*`, cópia estática do sistema antigo)
continua um arquivo SQLite ao lado do banco. O desvio do `sqlite3.connect` e o
`banco_pg.conectar` decidem pelo **nome** do arquivo: o que termina em
`cartorio_gestao.sqlite3`, ou foi registrado, vai ao PostgreSQL. Desde o LH09,
todo código que abre o acervo usa a porta `banco_pg.conectar_sqlite`, que abre o
SQLite de verdade sem passar pelo desvio e só para leitura (`mode=ro`), a menos
que quem chama monte o acervo.

| quem abre | para quê | como abre |
|---|---|---|
| `acervo_carga.abrir_acervo` | as cargas e prévias das atribuições, o XML da CENPROT, o Livro 3 (aceita caminho digitado) | porta, só leitura |
| `acervo_carga.instalar_acervo_de_sqlite` | confere o arquivo enviado antes de pô-lo no lugar do acervo | porta, só leitura |
| `acervo_eoficio.conferir` / `resumo` | a conferência e o resumo do acervo montado | porta, só leitura |
| `acervo_eoficio.carregar` | **monta** o acervo a partir da exportação JSONL (no `.parcial`) | porta, escrita |
| `acervo_eo_vivo.aplicar_jsonl_no_acervo` | **atualiza** as tabelas do Protesto puxadas ao vivo do E-Ofício | porta, escrita |
| `cnib_atualizador.retrato_do_acervo` | a data do último pedido da CNIB no acervo | porta, só leitura |
| `cnib_web.cnib_credencial_do_acervo` | traz o par da CNIB do acervo para o cofre | porta, só leitura |
| `selador_config.ler_do_eoficio` | a configuração do selador guardada no acervo | porta, só leitura |
| `tools/quantidade_nas_custas_do_eoficio.py` | mede as custas contra o acervo (linha de comando) | porta, só leitura |
| `app.py` (backup completo) | põe o arquivo no pacote (`backup.gerar_pacote`) | **não abre conexão**: copia os bytes |

O defeito que a porta fechou: `instalar_acervo_de_sqlite` conferia o arquivo pelo
`sqlite3.connect`. Um arquivo enviado (upload, pasta digitada ou zip) com o nome
do banco da casa ia ao PostgreSQL e achava as tabelas da casa, e a cópia seguinte
punha o arquivo-marca vazio do banco no lugar do acervo. O caminho digitado do
Livro 3 com esse nome abria o banco da casa no PostgreSQL. A prova, um teste por
item da tabela acima, está em `tests/test_acervo_sqlite_de_verdade.py`.
