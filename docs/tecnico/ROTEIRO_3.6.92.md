# Roteiro 3.6.92 — Teor RTDPJ editável (modelo da casa)

**11/09/2026** — forma aprovada nos PDFs ouro Santa Isabel.

## O que entrou

- Módulo `rg_teor_rtdpj.py` (piso do texto + PDF). `rg_teor_averbacao.py` vira reexport.
- Quatro chaves no catálogo `modelos_da_casa`:
  - `RCPJ_TEOR_AVERBACAO` / `RCPJ_TEOR_REGISTRO`
  - `RTD_TEOR_AVERBACAO` / `RTD_TEOR_REGISTRO`
- Código = piso; `mo_modelos` = ajuste; voltar ao padrão = apagar a linha.
- Prévia na ficha do registro (`tipo=AVERBACAO`) e no título lavrado (`tipo=REGISTRO`).
- PDFs ouro em `docs/tecnico/modelos_teor_rtdpj/`.

## Como editar

Administrativo → **Modelos** → filtrar «RCPJ e RTD» → editar a chave desejada.
URL direta: `/modelos?editar=RCPJ_TEOR_AVERBACAO`

## O que NÃO foi feito nesta versão

- **Não** rodou ATUALIZAR no live.
- **Não** selou nem lançou averbação na ficha 361.
