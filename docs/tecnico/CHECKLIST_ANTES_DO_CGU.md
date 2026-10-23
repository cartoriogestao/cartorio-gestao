# Checklist antes de empacotar `.cgu`

Use na árvore `INSTALAR_CARTORIO_GESTAO` (Downloads), **antes** de `tools\criar_atualizacao.py`.

1. **Versão** — [x] `VERSAO.txt` e `VERSION` em `app.py` iguais (**3.6.193**); sandbox `/saude` **3.6.193** (`:8899`); produção **3.6.193** (`:8765`) após apply 2026-09-24.
2. **Conferência** — [x] `python tools\conferir_antes_de_atualizar.py` (366 módulos, 261 telas, versão consistente).
3. **Pytest** — [x] suite mínima do release (**94 passed**, 1 spy corrigido em `test_traslado_carimbo_e_assinaturas.py`):
   - `tests\test_pacote_nao_leva_lixo.py`
   - `tests\test_titulo_aba.py`
   - `tests\test_traslado_carimbo_e_assinaturas.py`, `tests\test_doi_da_serventia.py`, `tests\test_ra_livro3_completo.py`
4. **Sandbox** — [ ] não rerun neste pacote (sem mudança de faixa/integração além do já validado em `:8899`).
5. **Modelos** — [ ] não alterou catálogo neste fechamento.
6. **Amostra** — [ ] amostra ODT manual (revisão humana pendente).
7. **Pacote limpo** — [x] `backups_patch\` excluído do `.cgu` (`PASTAS_IGNORADAS_NA_COPIA`); BOM removido de arquivos de programa; docs UTF-8.

Produção: [x] aplicado pelo fluxo ADMIN (`validate_and_stage` → inspeção → `aplicar_atualizacao.ps1`) em **2026-09-24**. Sandbox continua em **8899** com `CARTORIO_GESTAO_DATA` próprio.
