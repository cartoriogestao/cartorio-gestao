# Índice de minutas de ato (`MINUTA_ATO`)

> Fase 1 do plano de modelos. **Não são papéis** do `CATALOGO` — são corpos de ato (escritura, procuração, ato de RI, etc.). Não misturar com ajuste de papel em `mo_elementos`.

Medido em 2026-09-19 10:47 (America/Fortaleza).

## Notas — `nt_modelos` (seed: `notas_modelos.py`)

| tipo | quantidade |
|---|---|
| `ATA_NOTARIAL` | 2 |
| `ATA_USUCAPIAO` | 1 |
| `ESCRITURA` | 25 |
| `PROCURACAO` | 301 |
| `RENUNCIA_PROCURACAO` | 1 |
| `REVOGACAO_PROCURACAO` | 1 |
| `SUBSTABELECIMENTO` | 1 |
| `TESTAMENTO` | 1 |

Total: **333** linhas. Seed de fábrica: `notas_modelos.MODELOS` / `instalar()` (não reescrever conteúdo maduro).

## RI — modelos de atos

- Tela: `/registro-imoveis/modelos-atos` (`ri_modelos_atos.py`).
- Tipo: `MINUTA_ATO` (índice de teores de ato imobiliário, não papel do catálogo).

## Tabelas `*modelo*` no SQLite desta casa

`ri_modelos`, `nt_modelos`, `mo_modelos`, `rc_modelos_livres`

## Regra

Alterar texto de minuta = edição no módulo Notas/RI ou seed, **não** via `modelos_da_casa.CATALOGO`. O catálogo é só papel emitido pela casa.
