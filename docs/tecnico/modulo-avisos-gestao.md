## Avisos v2 (3.6.258) — sandbox :8899

- Faixas compactas: implantação, disputa, avisos vermelho/verde (`templates/_faixas_compactas.html`).
- Vermelho: importantes — USER não dispensa; **ADMIN** dispensa pela faixa ou modal/lista/detalhe.
- Verde: normais — dispensar resto do dia (faixa + lista `/avisos`).
- Recorrência: chips Seg–Dom + hora; coluna `recorrencia_dias` (bitmask); `processar_recorrencias` no contexto web.
- Vigência opcional: de/até no form admin (`vigencia_inicio`, `vigencia_fim`).
- Modal login: lista de títulos (link detalhe), × fechar; **sem** «Ver todos os avisos».
- Especificação: `docs/tecnico/modulo-avisos-gestao-v2-especificacao.md`.
