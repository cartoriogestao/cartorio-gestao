# O arquivo de desistência da CRA — o quinto layout, medido

Achado em **25/08/2026**, construindo o aviso de intimação. Fechado em
**26/08/2026**, quando o oficial apontou a pasta de rede da serventia.

O roteiro do oficial põe a desistência nos **três turnos do dia** — é a única
coisa que aparece nos três —, e o sistema não conseguia nem abrir o arquivo
dela.

```
*** MANHÃ:    1) Arquivo banese e desistências
*** MEIO DIA: 2) verificação de desistências
*** TARDE:    1) verificar desistências
```

> **Por que ela se confere três vezes**: título de que o apresentante desistiu
> e a casa protestou é protesto que se cancela depois, com carta. É o erro mais
> caro do dia, e por isso o oficial olha três vezes.

---

## O que se sabia, e estava errado

`protesto_arquivo.py` conhece **quatro** tipos, todos de **600 posições**:
remessa, retorno, confirmação e andamento. Foi assim que se mediu, em 572
arquivos reais.

A desistência **não é nenhum deles**. Ela tem:

- **127 posições por linha**, e não 600;
- **cinco tipos de registro** (`0`, `1`, `2`, `8`, `9`), e não três;
- **sequencial nas últimas 5 posições** de cada linha, e não no começo.

`ler()` recusa o arquivo dizendo que ele não tem 600 caracteres — o que está
certo, e é a mensagem que fez o achado aparecer.

---

## A prova: 388 arquivos, dois estados, sete anos

O layout foi **medido** em quatro arquivos desta casa e depois **provado**
contra 384 de outra: em 26/08/2026 o oficial trouxe o acervo da CRA da
serventia em que trabalhou, em Sergipe, com 385 arquivos de desistência.

| | |
|---|---|
| Arquivos de desistência de Sergipe | 385 |
| **Lidos pelo layout, sem um único achado** | **384** |
| Títulos lidos | **502** |
| Arquivos em que a soma do rodapé fecha | **384 de 384** |
| Recusados | 1 — e com razão: é um **retorno de 600 posições** guardado na pasta de desistência |

> **As pastas mentem, e aqui mentiram de novo.** O único arquivo recusado é um
> `SDTBFORTP` dentro de `DESISTÊNCIA/`. O leitor o recusou dizendo o tamanho
> que achou e onde ele se abre — que é exatamente o que essa mensagem existe
> para fazer.

**Um layout medido em quatro arquivos de uma casa leu 384 de outra casa, de
outro estado, sem erro.** Isso é a prova independente que nenhuma releitura de
código dá.

E ele fechou a última coisa que faltava: a contagem do registro `8`, que com
quatro exemplares era "compatível com o dobro dos títulos" e agora é **o dobro
em 388 de 388**.

**O que a amostra grande também mostrou:** 384 de 384 arquivos têm **uma praça
só**, e 317 têm **um título só**. O maior tem nove. O multi-praça que o layout
comporta não acontece na prática — o que não é motivo para deixar de lê-lo, é
motivo para não desenhar a tela em torno dele.

---

## A amostra original: quatro arquivos, quatro anos

| Arquivo | Apresentante | Data | Títulos |
|---|---|---|---|
| `DP0002608.221` | `1LV` — Equatorial Maranhão | 26/08/2022 | 2 |
| `DP0011004.232` | `001` — Banco do Brasil | 10/04/2023 | 1 |
| `DP0011503.233` | `001` — Banco do Brasil | 15/03/2023 | 1 |
| `DP0010508.261` | `001` — Banco do Brasil | **05/08/2026** | 1 |

Os três primeiros estavam em `C:\ARPNET\CRA\DESISTENCIA`; o de 2026 veio da
pasta de rede da serventia (a subpasta das desistências da CRA), que o oficial indicou.

**Cinco títulos, dois apresentantes, quatro anos** — e o layout é o mesmo nos
quatro. Foi o de 2026 que fechou a medição: o número do título dele,
`NF-74654-/1`, tem forma inconfundível e prende a fronteira do campo, coisa que
`92000001907` e `1  00053603` sozinhos não faziam.

> É a mesma lição do retorno, outra vez: **o que fecha uma lacuna de layout é
> mais amostra, e não engenhosidade.**

---

## O layout, campo a campo

Conferido nos quatro arquivos. Onde não deu para medir, o campo se chama
`reservado_NNN` e **se lê como texto** — campo sem nome não se interpreta.

### `0` — cabeçalho

| Posições | Tam. | Campo | Medido |
|---|---|---|---|
| 1 | 1 | tipo do registro | `0` |
| 2–4 | 3 | **código do apresentante** | `001`, `1LV` — a **mesma largura** do arquivo de 600 |
| 5–49 | 45 | nome do apresentante | |
| 50–57 | 8 | data do movimento | `ddMMyyyy` |
| 58–62 | 5 | **quantidade de títulos** | bate com as linhas `2` nos quatro |
| 63–67 | 5 | `reservado_63` | igual ao anterior nos quatro — A CONFERIR |
| 68–122 | 55 | brancos | |
| 123–127 | 5 | sequencial da linha | `00001` |

### `1` — a praça

| Posições | Tam. | Campo | Medido |
|---|---|---|---|
| 1 | 1 | tipo | `1` |
| 2–3 | 2 | número da praça | `01`, `03` — casa com o `8` |
| 4–8 | 5 | quantidade de títulos da praça | |
| 9–15 | 7 | **código IBGE da cidade** | `2198765` (Cidade Exemplo/MA), `2905500` |

`2905500` é de outro município, e **não se sabe qual** — não se inventa nome de
cidade a partir de código.

### `2` — o título de que se desiste

O registro que interessa, e está inteiro:

| Posições | Tam. | Campo | Medido |
|---|---|---|---|
| 1 | 1 | tipo | `2` |
| 2–11 | 10 | **protocolo** | `7791240003`, `2608030003` |
| 12–19 | 8 | data | `ddMMyyyy` |
| 20–30 | 11 | **número do título** | `NF-74654-/1`, `92000001907`, `1  00053603` |
| 31–75 | 45 | **nome do devedor** | |
| 76–89 | 14 | **valor em centavos** | e a soma **fecha com o rodapé nos quatro** |
| 90 | 1 | `reservado_90` | `S` nos cinco títulos |
| 91–102 | 12 | `reservado_91` | zeros nos cinco |
| 103–114 | 12 | `reservado_103` | zeros no BB, brancos na Equatorial |
| 115–116 | 2 | `reservado_115` | brancos nos cinco |
| 117–122 | 6 | `reservado_117` | `000000` no BB, `     I` na Equatorial |
| 123–127 | 5 | sequencial | |

**Os cinco campos reservados não carregam nada que identifique o título** —
são constantes, zeros ou brancos. Por isso a leitura é segura sem eles.

### `8` — total da praça

| Posições | Tam. | Campo |
|---|---|---|
| 1 | 1 | tipo (`8`) |
| 2–3 | 2 | número da praça |
| 4–8 | 5 | uma contagem |

**A contagem é o DOBRO do número de títulos — em 388 arquivos de 388.** Era a
única coisa do layout que não fechava com quatro exemplares; fechou com 384.

**O que ela conta de fato continua sem explicação** — não é o número de
títulos, nem o de linhas do bloco, nem o de registros. Mas a *relação* está
estabelecida além de dúvida: 388 arquivos, dois estados, sete anos, nenhuma
exceção. A conferência compara com o dobro e **avisa** em vez de recusar,
porque avisar sobre uma relação medida é honesto e recusar por uma hipótese
não é.

### `9` — rodapé

| Posições | Tam. | Campo | Medido |
|---|---|---|---|
| 1 | 1 | tipo (`9`) | |
| 2–4 | 3 | apresentante | |
| 5–49 | 45 | nome | |
| 50–57 | 8 | data do movimento | |
| 58–62 | 5 | a mesma contagem do `8` | dobro dos títulos nos quatro |
| 63–76 | 14 | **soma dos valores** | **fecha nos quatro** |
| 123–127 | 5 | sequencial | |

A soma é a conferência que vale: R$ 1.066,22 = 530,77 + 535,45 no primeiro, e
os outros três fecham com o título único de cada um.

---

## O que se faz com isso, e o que não

**Lê-se, confere-se e aplica-se título a título** — `protesto_desistencia.py`.
O protocolo do arquivo procura o título na base; o que a casa tem, mostra; o
que não tem, diz que não tem.

**Não se aplica sozinho — e isso NÃO mudou com a amostra grande.** O layout
está provado em 388 arquivos, e mesmo assim cada título é uma marcação do
oficial. A razão não é desconfiança do leitor: é a **consequência**.
Desistência aplicada por engano é protesto que deixa de sair; desistência não
aplicada é protesto lavrado contra quem o credor desistiu de protestar — e esse
se desfaz com carta. Confiança no código não é a mesma coisa que autoridade
para decidir.

**Não se escreve este arquivo**, e nem se deve tentar: a desistência chega, não
sai.
