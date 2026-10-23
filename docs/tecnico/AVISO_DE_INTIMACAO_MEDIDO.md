# O aviso de intimação desta casa, medido

Medido em **25/08/2026**, no `acervo_eoficio.sqlite3`, antes de escrever
qualquer linha do módulo. Este arquivo é o que se sabe hoje — e o que **não**
se sabe, que é a parte que decide o que dá para construir.

O passo do roteiro do oficial que ele serve:

```
- EMITIR AVISO INTIMAÇÃO
- gerar aviso, verificar "emitir aviso" para coobrigados sem boleto, depois
  ativa boleto e clica em registrar boletos e emitir aviso
  (sempre verificar se aparecem erros)
- gera intimação, edital, arquivo edital no cenprot e impresso na parede.
```

---

## 1. O aviso é o boleto, e o boleto é da própria serventia

A tabela é **`tbBoletoApto`**: 1.618 linhas, todas preenchidas.

| | |
|---|---|
| Títulos no acervo | 1.370 |
| Títulos com aviso | **1.361** — praticamente todos |
| Avisos emitidos | 1.618 |
| Títulos com **mais de um** aviso | **255** |

Reemitir aviso é rotina, e não exceção — 255 títulos em 1.361. Endereço que
muda, entrega que não deu certo, aviso que se refaz. **Quem construir o módulo
não pode tratar o aviso como um por título.**

**Não há banco.** Em todas as 1.618 linhas: `strBanco = '000'`,
`strCarteira = '0'`, `strAgenciaCodCedente = '0 / 0-0'` e
`strCedente = 'SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO'`. Não existe convênio
bancário a imitar nem layout de remessa CNAB a medir: **o boleto é da casa**, e
o dinheiro entra no caixa dela.

---

## 2. O código de barras é FEBRABAN de 44, e está inteiro medido

`strCB_Boleto` tem **44 dígitos em 1.618 de 1.618**.

| Posições | O que é | Medido |
|---|---|---|
| 1–3 | banco | `000` em 1.618 |
| 4 | moeda | `9` em 1.618 |
| 5 | dígito verificador geral | varia |
| 6–9 | fator de vencimento | varia — **ver a ressalva abaixo** |
| 10–19 | valor em centavos | **bate com `curValorBoleto` em 1.618 de 1.618** |
| 20–44 | campo livre (25) | 20 posições constantes; variam só as 8ª a 12ª |

**O campo livre é `0000000` + nosso número de 4 dígitos + 1 verificador +
`0000000000000`**, e isso está **provado em 1.618 de 1.618**: o trecho que
varia, lido como número, é sempre exatamente `nosso_numero × 10 + verificador`.
As outras 20 posições são zero em todas.

**O verificador NÃO foi explicado, e a busca foi exaustiva.** Fica registrado
para quem tentar depois não refazer o mesmo caminho:

- Não é módulo 10 nem módulo 11 com nenhum vetor fixo de quatro pesos. Foram
  testadas as 9⁴ combinações de pesos de 1 a 9, nos dois módulos e nas duas
  convenções (`dv = resto` e `dv = módulo − resto`): **o melhor acerto foi 465
  de 1.618, 29%** — nível de acaso.
- As posições constantes do campo livre são todas zero, então nenhum peso
  aplicado a elas muda a soma: a família "soma ponderada" está **esgotada**.
- O verificador cai de 2 em 2 (módulo 10) quando o nosso número sobe de 1, com
  saltos de 3 de tempos em tempos. É a assinatura de um resultado de módulo 11
  dobrado para caber num dígito — mas nenhuma regra de dobra testada o
  reproduz.

A conclusão é que ele depende de algo **além do nosso número**. Sem descobrir o
quê, o código de barras não se reproduz — e código de barras errado é boleto que
o leitor aceita e o dinheiro cai no lugar errado.

**A `strLinhaDigitavel_Boleto` é a linha digitável correspondente**, no formato
de cinco campos com os pontos e espaços — 1.618 distintas, todas bem formadas.

> **A ressalva do fator de vencimento, e ela importa.** O fator só bate com
> `dtmVenc` em **776 dos 1.618**. E `dtmVenc − dtmBoleto` está espalhado, com
> valores **negativos** — 185 avisos com vencimento cinco dias ANTES da
> emissão. Ou o E-Ofício gravava as duas datas em momentos diferentes, ou o
> fator vinha de outra data. **Não se reproduz o fator sem entender isso**, e
> chutar produziria boleto que o leitor ótico aceita e o valor cai errado.

---

## 3. As custas do protesto estão aqui, discriminadas — e é a fonte mais rica

`tbBoletoApto` tem **56 colunas `cur*`**. As que têm valor de verdade:

| Coluna | Faixa | O que aparenta ser |
|---|---|---|
| `curValorPrincipal` | 56,70 a 1.607.177,07 | o valor do título |
| `curValorBoleto` | 125,09 a 1.608.217,06 | o total a pagar |
| `curTaxaApto` | 7,57 a 860,81 — **87 valores** | o emolumento do apontamento, por faixa |
| `curTaxaSDT` | 8,88 a 10,67 | a taxa da Central |
| `curTaxaIntimacao` | 0 a 19,06 | a intimação |
| `curV_Diligencia` | 0 a 46,88 | a diligência da entrega |
| `curArquivamento_Valor` | 11,58 a 36,18 | o arquivamento |

E cada uma tem **os fundos ao lado**: `_FEC`, `_MP`, `_DP`, `_ferrfis`. É a
mesma estrutura de quatro fundos que `custas.py` já conhece — aqui aplicada
título a título, com o valor que foi de fato cobrado.

**São zero em todas as 1.618**: `curTaxaEntrega`, `curTaxaAR`,
`curTaxaBancaria`, `curTaxaEdital`, `curCertidao`, `curOutras_Custas`,
`curValorPago`, `curValor_ISS`, e as quatro de `Averbacao173`. Zero medido é
fato: esta casa não cobrava por entrega, por AR, nem taxa bancária.

---

## 4. A entrega, e o edital como o que vem depois dela

| | |
|---|---|
| Avisos entregues (`bitEntregue=1`) | **1.152** |
| Não entregues | 466 |
| Com data de entrega confirmada | 1.145 |
| **Publicados em edital** (`bitPublicadoEdital=1`) | **1.092** |

O aviso guarda `intCodigoEntregador` e `dtmEntregaConfirmada`: **a entrega é
feita por alguém, e o sistema registra quem e quando.**

**Quem entrega é o próprio cartório.** `tbEntregador` tem **duas** linhas:

| Código | Nome | ECT | Ativo | Usos |
|---|---|---|---|---|
| 2 | `CARTORIO` | não | **sim** | **1.618 de 1.618** |
| 3 | `CORREIROS` | sim | não | zero |

Os Correios estão cadastrados e **desligados**. Todo aviso desta casa saiu pela
mão de quem trabalha nela — o que explica por que `curTaxaEntrega` e `curTaxaAR`
são zero nas 1.618.

### O catálogo de motivos de não-entrega, e ele decide o edital

`tbMotivoNEntrega` tem **13 motivos**, e duas marcas que valem regra:

| # | Motivo | Vai a edital | Conta tentativa |
|---|---|---|---|
| 1 | Mudou-se | **sim** | |
| 2 | Endereço não encontrado | | |
| 3 | Recusou-se a receber | | |
| 4 | Falecido | | |
| 5 | Não é o número indicado | **sim** | |
| 8 | Destinatário desconhecido | | |
| 9 | Endereço incompleto | | |
| 10 | Informação fornecida pelo porteiro/síndico | | |
| 11 | Ausente | | **sim** |
| 12 | Fechado | | **sim** |
| 13 | Não procurado | | |
| 14 | Fora do perímetro | | |
| 7 | Não existe o número indicado | | *(inativo)* |

**O que acontece na prática, medido em `tbBoletoControleNEntrega` (1.139):**

| Motivo | Vezes |
|---|---|
| **Ausente** | **1.068** — 94% |
| Endereço não encontrado | 13 |
| Recusou-se a receber | 6 |
| Fechado | 4 |
| Falecido | 4 |
| Destinatário desconhecido | 1 |
| sem motivo gravado | 43 |

E **1.070 dos 1.139 controles terminam não entregues**. Junte com os 1.092
publicados em edital e o quadro fecha: nesta casa, **o caminho comum da
intimação é a tentativa que não acha ninguém em casa e o edital em seguida** —
e não a entrega em mão. Quem construir o módulo tem de tratar o edital como
rotina, e não como exceção.

**`tbEdital`**: 1.086 linhas.

| Coluna | O que traz |
|---|---|
| `strcb_ap` | o título |
| `dtmpublicacao` | a data |
| `strUSERID_Publicado` | quem publicou |
| `strCodigoCidadeIBGE` | `2198765` (Cidade Exemplo/MA) nas 1.086 |
| `curValor` | **0,00 nas 1.086** |
| `strNControleDev` | número de controle do devedor |
| `bitativo` | **0 nas 1.086** |

**O edital não é cobrado nesta casa** — `curValor` é zero em todas, e
`curTaxaEdital` do aviso também.

---

## 5. O que NÃO se sabe, e por isso não se constrói ainda

1. **O verificador do nosso número** no campo livre — busca exaustiva feita,
   nada explica. Depende de algo além do nosso número.
2. **De onde vem o fator de vencimento** — bate com `dtmVenc` em menos da
   metade. É o buraco que impede reproduzir o código de barras.
3. **O texto do aviso.** Nenhuma das duas tabelas guarda o teor. Como no RCPN,
   o E-Ofício montava o papel dos campos; que papel era esse, o acervo não diz.
4. **O arquivo do edital para o CENPROT** — o roteiro o cita
   (*"arquivo edital no cenprot"*) e não há vestígio dele no acervo.
5. ~~Quem são os entregadores~~ — **achado**: `tbEntregador`, e é o próprio
   cartório nas 1.618.

**Nenhum dos quatro que sobram se resolve inventando.** Os dois primeiros travam
o boleto; os dois seguintes travam o texto do aviso e o arquivo do edital. O que dá para construir sem eles é o
**registro** do aviso e da entrega — que já é o que falta ao sistema hoje, e é
o que a inspeção cobra: saber se o devedor foi intimado, quando, por quem, e se
foi por edital.
