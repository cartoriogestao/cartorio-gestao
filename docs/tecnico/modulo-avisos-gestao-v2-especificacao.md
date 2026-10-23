# Avisos gestão v2 — recorrência e vigência (3.6.257)

## Recorrência

- Admin form: chips **Seg … Dom** (`recorrencia_dias` multi-select → bitmask em `nu_avisos.recorrencia_dias`).
- Hora: `recorrencia_hora` (HH:MM).
- Legado: `recorrencia_dia_semana` (0–6) migrado para bitmask na init do schema.
- Scheduler: `processar_recorrencias` reativa `ativo=1` no **primeiro slot** (dia marcado + hora) após encerramento; limpa `nu_aviso_dispensa` do aviso.

## Vigência

- Campos opcionais `vigencia_inicio` / `vigencia_fim` (`<input type="date">` no form admin).
- `vigente()` exclui avisos fora do período (fim inclusive).

## ADMIN — encerrar importantes

Mesmo backend: `dispensar(..., papel=ADMIN)` → `desativar` + regras de recorrência.

| Superfície | Comportamento |
|------------|----------------|
| `/avisos` (tabela ADMIN) | Botão **Encerrar** em avisos importantes ativos |
| Faixa vermelha | **Dispensar importantes** (POST `/avisos/dispensar-importantes-faixa`) |
| Modal 1º login | **Dispensar** por item (importante); × só fecha overlay |
| Detalhe | **Encerrar (ADMIN)** |

Non-ADMIN: sem encerrar importantes; normais inalterados (faixa verde / lista).

## Modal

- Sem link «Ver todos os avisos» no rodapé; títulos linkam para detalhe.
