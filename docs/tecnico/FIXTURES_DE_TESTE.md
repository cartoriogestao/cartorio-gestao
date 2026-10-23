# Fixtures compartilhadas de teste (DB/app)

## Objetivo

Reduzir o tempo da suite: create_app + schema SQLite custam ~1 s e ~2 MB
por chamada. As fixtures em `tests/conftest.py` montam o app **uma vez por
modulo** e isolam cada teste com restore barato a partir de um seed.

## API

| Fixture | Escopo | Uso |
|---------|--------|-----|
| cg_data_dir | module | pasta DATA_DIR do modulo |
| cg_app | module | Flask ja montado |
| cg_db_path | module | path do .sqlite3 |
| cg_db | function | Database com seed restaurado |
| cg_client | function | test_client + reset |
| cg_casa | function | dict legado {app,c,cliente,banco,db,dados,acervo} |
| cg_casa_logada | function | cg_casa + admin `mario`/`Senha#12345` logado (nao usar em testes de auth) |
| cg_login(client, user, senha) | helper | login com CSRF |

O reset por teste limpa o SQLite (DELETE+INSERT do seed) **e** remove
arquivos/sidecars gerados sob DATA_DIR (pasta `arquivos/`, `agente.cred`,
etc.), mantendo so o DB e o seed.

## Progresso da migracao create_app frio -> cg_*

Atualizado em 15/09/2026 (America/Sao_Paulo, UTC-3):

| Situacao | Qtd (aprox.) |
|----------|--------------|
| Arquivos com `def casa(cg_casa)` | **63** |
| Arquivos **sem** create_app e com cg_* | **~120** |
| Migrados nesta fatia (create_app eliminado) | **57 arquivos / ~1150 testes** |
| Arquivos que ainda chamam create_app | **~35** (~30 frios + ~5 mistos) |
| Testes ainda em arquivos com create_app | **~610** |
| Suite total coletada | **5851** |

Nesta fatia: migracao mecanica de fixtures `s` / `_sessao` / `serventia` /
`con` / `logado` / `auditor` para `cg_casa` / `cg_db`, pytest por lotes.
Revertidos os incompativeis com **scope=module** + `tmp_path_factory`.

### Ainda com create_app (nao migrar sem cuidado)

- Schema parcial / `:memory:` / DROP TABLE: `test_ibge_geracao`,
  `test_pessoas_do_assento`, `test_rascunho_abrir`, `test_selador_cliente`,
  `test_ajuda_projeto`, `test_inacabados`, `test_sirc_remessa`, `test_agente`
- Producao / acervo especial: `test_ri_selo_do_ato`, `test_acervo_eo_vivo`
- **scope=module** + `tmp_path_factory` (amortizado de proposito):
  `test_cores_na_tela`, `test_firmas_organizadas`, `test_painel_dos_atos`,
  `test_preencher_formulario`, `test_manual_de_importacao`,
  `test_importar_padrao_tela`, `test_usucapiao_notificacao_tela`,
  `test_menu_sem_duas_portas`
- DADOS/tempfile de modulo: `test_menu`, `test_modulo_alcance`,
  `test_selador_web`, `test_importar_padrao_modelos`
- Pasta por papel / mutacao de url_map: `test_papel_web`, `test_agente_web`,
  `test_ajuda_janela`
- Auth frio pontual (1 teste no arquivo): `test_robos`, `test_wa_balcao`

### Amostra de tempos (pytest --durations)

- Setup de modulo (1o teste do arquivo cg_*): ~1,7–2,5 s (create_app + seed)
- Setup dos demais no mesmo arquivo: ~0,3–0,5 s (restore ATTACH + limpeza)
- Ex.: `test_selos_emitidos` (16) + `test_desfazer_averbacoes_rcpj` (4):
  **20 passed em ~14 s** (antes ~2 s de create_app **por** teste)
- `cg_casa_logada`: ganho pequeno (~tempo do POST /login); use por
  boilerplate, nao por velocidade de schema

## Gate rapido (`lento`)

Marker registrado em `pytest.ini`:

```text
markers =
    lento: testes pesados (prod/acervo/EOF/notoriamente lentos)
```

Comando do gate (exclui **762** testes marcados; sobram **5089**):

```bat
pytest -m "not lento" --durations=20
```

Suite completa:

```bat
pytest --durations=20
```

Atalho no fonte: `RODAR_SUITE_RAPIDA.cmd` (Python do runtime
`C:\ProgramData\CartorioGestao\runtime\Scripts\python.exe`).

**27** arquivos com `pytestmark = pytest.mark.lento` (producao,
acervo_eoficio, DROP TABLE pesado, suites web longas como
`atribuicoes_web`, `rg_web`, `sirc_remessa`, etc.).

## Quando NAO usar cg_*

- Teste com schema proprio em `:memory:` (ex.: so `init_rc_schema`).
- Qualquer caminho que aponte ao SQLite de producao
  (`C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3`).
- Teste que exige estado inicial diferente do seed de fabrica do `init_schema`.
- Teste que faz `DROP TABLE` / altera schema no meio — o restore so
  DELETE+INSERT a partir do seed; nao recria tabela dropada.
- Fixture **module-scoped** que ja amortiza um unico `create_app` via
  `tmp_path_factory` — migrar para `cg_casa` (function) pode piorar.
- Testes de auth/login anonimo: use `cg_casa` / `cg_client`, **nao**
  `cg_casa_logada`.

## Como migrar um arquivo

1. Troque a fixture local que chama `create_app` por `cg_casa` / `cg_db`.
2. Mantenha so o setup de dominio (usuario, login, INSERTs).
3. Meça: `pytest --durations=10 tests/test_X.py`.
4. Se o fixture era `scope="module"` + `tmp_path_factory`, **nao** migrar
   mecanicamente — meça antes.
5. Migre aos poucos; rode o lote, nao a suite completa (~5800).

## Isolamento

Entre testes do mesmo modulo: DELETE em todas as tabelas de dados +
INSERT ... SELECT a partir do seed (ATTACH). Nao se dropa o schema.
Arquivos sob DATA_DIR (incluindo fora de `arquivos/`) sao limpos a cada reset.
