# O que editar onde   minuta, papel e molde ODT

Referência de **1 página** para a serventia (M8 do roteiro revisor).

| O quê | Onde editar | Quando usar |
|-------|-------------|-------------|
| **Papel assinado** (texto do ato/certidão no sistema) | `/modelos`   catálogo `modelos_da_casa` + overrides em `mo_elementos` | Teor que sai na impressão/PDF após lavratura |
| **Molde ODT** (layout de certidão RCPN etc.) | Arquivos `modelos/*.odt` + registro `mo_moldes` | Certidões com formatação cartorial fixa |
| **Minuta de escritura (Notas)** | Fluxo Notas ’! `nt_modelos` | Rascunho antes da lavratura; **não** é o catálogo `/modelos` |
| **Minuta RI** | Ficha da matrícula ’! `ri_minutas` (`?minuta=`) | Texto em elaboração até revisão/lavratura |
| **Índice de modelos de ato RI** | `ri_modelos_atos` redireciona para `/modelos` | Evitar duplicar editor |

**Regra:** marcadores `[CAMPO]`, `{ESCOLHA}` ou `{{` não resolvido não podem ir para o papel assinado.

**Inventário técnico:** `python tools\inventario_modelos.py`   ver também `docs/tecnico/MATRIZ_DE_PAPEIS.md` e `INDEX_MINUTAS_ATO.md`.
