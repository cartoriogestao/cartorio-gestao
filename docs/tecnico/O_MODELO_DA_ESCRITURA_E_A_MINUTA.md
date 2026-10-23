# O modelo da escritura pública, ajustado ao padrão da minuta — 07/09/2026

> «criei o submodulo de modelos para poder editar os modelos dos atos no
> sistema mais facilmente. Preciso ajustar o modelo dos atos de escrituras
> publicas para que corresponda ao padrao tecnico e estetico do modelo de
> minuta que baixei mais cedo em downloads» — o oficial.

---

## 1. O que ele trouxe, e onde o modelo mora

`MINUTA_ESCRITURA_MATRICULA para modelo.docx`, uma escritura pública real
desta serventia — compra e venda de imóvel rural, com nome de partes, valores
e matrícula de verdade. O oficial pediu para o **modelo dos atos de
escrituras públicas** imitar a forma dela.

O texto da escritura (o que sai no livro quando o ato é lavrado) mora em
`notas_modelos.py`, na entrada `nt_modelos` — **não** no submódulo de
modelos por atribuição (`modelos_elementos.py`) que entrou no mesmo dia:
aquele cobre os 15 papéis administrativos da casa (recibo, traslado, ficha,
certidão…), e a escritura pública não é um deles — é o próprio ato, com
corpo próprio por natureza (compra e venda, doação…), e vive na biblioteca
de modelos do Tabelionato de Notas.

## 2. O que a minuta ensina, e o que dela se imitou

A minuta organiza o corpo em **títulos numerados** (I a XIII): o imóvel, a
matrícula, o preço, o ITBI, o CCIR/CIB/CAR, a modalidade AD CORPUS, o
georreferenciamento, as declarações de cada parte, as certidões arquivadas,
a DOI/LGPD/prevenção à lavagem, a base legal por extenso e os emolumentos.

Os dois modelos de compra e venda — `NT-ESC-COMPRA-VENDA` (urbano) e
`NT-ESC-COMPRA-VENDA-RURAL` — passaram a seguir essa mesma ordem, com
marcador (`[CAMPO]`, `{ESCOLHA}`, `«SE»`) onde o sistema não tem o dado que a
minuta trazia preenchido (nome das partes, matrícula, CNIB, CCIR).

**O que NÃO se imitou, e por quê:** a minuta é um documento impresso, com
título centralizado numa linha própria e bloco de assinatura com linha
pontilhada. O corpo deste sistema continua **corrido**, sem linha em branco
— art. 795, § 2º, do Código de Normas: *"a escrituração deve ser seguida,
sem claros ou espaços em branco"*. Os títulos (`I -`, `II -`…) entram como
marca dentro do mesmo parágrafo, não como parágrafo à parte. É a mesma forma
que os outros 15+ modelos deste arquivo já usam, e `tests/test_notas_modelos.
py::test_nenhum_modelo_tem_quebra_de_linha` continua de pé.

## 3. A lacuna que apareceu ao conferir se o modelo FUNCIONA

Os modelos de `notas_modelos.py` usam `{{ sv.ri_cidade }}`,
`{{ sv.ri_uf }}`, `{{ lavrado_nome }}`, `{{ lavrado_titulo }}`,
`{{ outorgantes }}` e `{{ outorgados }}` — sintaxe Jinja — desde que foram
escritos. **Nada no sistema os renderizava.**

A tela de lavrar um ato tem dois botões que aplicam o modelo:

| botão | rota | o que troca |
|---|---|---|
| *Montar com as partes* | `notas_ato_montar` | monta comparecimento e qualificação por fora (`notas_teor.montar`) — é o caminho dos 301 modelos importados do E-Ofício, que são só a cláusula de poderes |
| *Preencher a partir do modelo* | `notas_ato_preencher` | troca `[CAMPO]`, `{ESCOLHA}` e `«SE»` no próprio corpo do modelo — é o caminho dos modelos desta biblioteca, que já vêm com comparecimento, qualificação e fecho embutidos |

O segundo caminho — o que serve `NT-ESC-COMPRA-VENDA-RURAL` — só chamava
`ri_modelos_atos.preencher()`, que não sabe nada de Jinja. Uma escritura
montada por ele sairia com `{{ outorgantes }}` e `{{ lavrado_nome }}`
escritos **literalmente**, no documento que a serventia assina. Nenhum teste
cobria essa rota — é a primeira vez que ela é exercitada de ponta a ponta.

## 4. A correção

`notas_teor.partes_por_lado(partes)` separa as partes do ato pela
**qualificação que o próprio escrevente digitou**: quem tem "OUTORGADO",
"COMPRADOR", "DONATARIO" ou "PROCURADOR" na qualificação vai para
`outorgados`; o resto (vendedor, doador, outorgante puro, substabelecente,
renunciante, ou parte sem qualificação) vai para `outorgantes`. Testemunha
não entra em nenhum dos dois — nenhum destes modelos as cita no corpo.

`notas_ato_preencher()` agora renderiza esse Jinja **antes** de aplicar os
marcadores do escrevente:

```
sv          → serventia.dados(db.get_settings)      (cidade, UF, …)
lavrado_nome    → a["lavrado_nome"] ou o usuário logado
lavrado_titulo  → a["lavrado_titulo"] ou a função do usuário logado
outorgantes / outorgados → notas_teor.partes_por_lado(partes do ato)
```

**O que não der para classificar sai marcado, e não em branco** — a mesma
regra de `notas_teor._falta()`: lado sem parte nenhuma vira
`[OUTORGANTE(S) — QUALIFIQUE A PARTE NO ATO]`, que `pendencias_modelo()` já
acusa na tela como campo em branco. Lacuna muda é pior: ninguém a nota antes
de assinar.

## 5. O que ficou de fora, e é decisão do oficial

**`nt_modelos` só se semeia hoje como efeito colateral da carga do acervo**
(`notas_importar` chama `notas_modelos.instalar()` no fim da importação).
Uma instalação nova que nunca importasse o E-Ofício nasceria com a tela de
abrir ato **sem modelo nenhum** para oferecer — nem o de escritura, nem os
outros ~25. Não é o defeito deste ajuste, mas é o que o bloquearia numa casa
que ainda não rodou a carga; ficou registrado aqui para não se perder.

## 6. Onde conferir

| arquivo | o que traz |
|---|---|
| `notas_modelos.py` | `NT-ESC-COMPRA-VENDA` e `NT-ESC-COMPRA-VENDA-RURAL`, reescritos |
| `notas_teor.py` | `partes_por_lado()` |
| `notas_web.py` | `notas_ato_preencher()`, com o Jinja renderizado antes do `preencher_modelo` |
| `tests/test_notas_modelos.py` | as 50 regras de forma já existentes, todas verdes contra o texto novo |
| `tests/test_escritura_publica_padrao_da_minuta.py` | a ordem por títulos, o LGPD/AD CORPUS/base legal, e o caminho inteiro — abrir o ato, incluir as duas partes, preencher, e conferir que nenhuma chave dupla sobra no teor |
