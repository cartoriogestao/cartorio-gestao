# Sinais publicos — fatia 1 (07/09/2026)

## O que e

Cadastro do **sinal publico** baixado da central (CNSIP/Censec) e
**reconhecimento autonomo** desse sinal (sem firma).

## Regras do oficial

- **Abertura NAO sela.** So titular, origem, metadados e PDF anexado.
- O PDF e o da central — **nao se redesenha** o sinal.
- Reconhecimento autonomo usa o item **413** (cx_servicos: Reconhecimento
  de sinal, letra e firma), o mesmo do reconhecimento de firma.
- O checkbox «reconhecer tambem o sinal» no reconhecimento de **firma**
  permanece intacto (
t_reconhecimentos.sinal_publico).

## Tabelas (proprias — nao sobrecarrega 
t_cartoes)

- 
t_sinais_publicos — abertura / cadastro + caminho do PDF
- 
t_sinais_reconhecimentos — ato de reconhecimento autonomo

PDF em disco: rquivos/notas/sinais/<id>/sinal-<id>.pdf (caminho relativo
no banco; sem BLOB no SQLite).

## Rotas

- /notas/sinais — lista / abrir / anexar PDF
- /notas/sinais/<id> — ficha + upload
- /notas/sinais/<id>/pdf — serve o PDF
- /notas/sinais/reconhecimento — balcao do reconhecimento autonomo
- /notas/sinais/reconhecimento/<id> — consulta do ato

Menu: Tabelionato de Notas → Consulta → Sinais publicos / Reconhecer sinal.

## Fatia 1 — limites

- Sem cliente CNSIP no codigo: upload **manual** do PDF baixado na central.
- Selo do reconhecimento: mesmo caminho /selo/notas/reconhecimento-firma
  (envelope medido do item 413). Se o aparelho falhar, o ato fica lavrado
  sem selo (padrao da casa).

## Depois do ATUALIZAR

O init_notas_schema cria as tabelas na subida. No balcao:

1. Menu Notas → **Sinais publicos** → cadastrar titular/origem → anexar PDF.
2. **Reconhecer sinal** → buscar titular → lavrar (cobra 413 / sela se o
   selador estiver no ar).

Nao e necessario ATUALIZAR_SISTEMA especial alem do pacote que ja copia
*.py e 	emplates.
