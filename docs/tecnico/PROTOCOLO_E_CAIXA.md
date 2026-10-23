# O protocolo geral e o caixa, juntos

Decisão do oficial em **27/08/2026**:

> *"Juntemos protocolo geral com o caixa. No caixa/protocolo geral colocamos os
> serviços prestados. Deixemos separado apenas o protocolo de RI, atrelado ao
> protocolo geral/caixa, mas com os atributos da prenotação."*

---

## O defeito que isso conserta, e o tamanho dele

O protocolo guardava os serviços com os valores da tabela do tribunal, e quitar
um item **só marcava uma bandeira**. O dinheiro entrava no caixa por **outro
caminho** — o botão «cobrar» da ficha do ato.

**Dois trilhos para o mesmo dinheiro é como eles divergem**: o protocolo dizia
que o cliente pagou, o caixa não tinha o lançamento, e a conferência do dia
fechava com uma diferença que ninguém sabia de onde vinha.

O tamanho, medido em 27/08/2026:

| | |
|---|---|
| `cx_protocolo_atos` | 32.416 serviços |
| deles, com `lancamento_id` | **0** |

**Nenhum item de protocolo jamais virou dinheiro nesta casa.**

---

## O desenho que ficou

| | |
|---|---|
| **Onde entram os serviços** | no protocolo geral, com o valor da tabela vigente |
| **Quando vira dinheiro** | ao quitar o item — um lançamento por item |
| **A ficha do ato** | continua podendo cobrar, como **exceção**, para o ato que nasce sem protocolo |
| **A trava contra cobrança dupla** | `UNIQUE(origem, origem_chave)` em `cx_lancamentos`, que já existia |
| **O recibo** | um só, do atendimento inteiro |
| **O protocolo do RI** | separado, com os atributos da prenotação, atrelado por `cx_protocolos.ri_protocolo_id` |

### Um lançamento por item, e não um pelo protocolo

É o item que tem o valor da tabela, os quatro fundos separados e o selo. Somar
tudo num lançamento só faria a **conferência dos fundos deixar de fechar** — e é
ela que a inspeção pede.

### O valor não se recalcula na quitação

Ele foi calculado quando o item entrou no protocolo, pela tabela vigente
naquela data. Recalcular faria o cliente pagar um preço diferente do que lhe foi
dito no balcão — e **tabela nova entre uma coisa e outra** é exatamente o caso
em que isso aconteceria.

### Desquitar não apaga lançamento

Dinheiro que entrou no caixa sai por **estorno**, que deixa rastro. Apagar a
linha faria a conferência do dia fechar sem que ninguém soubesse por quê. A tela
recusa e diz qual lançamento estornar.

---

## O recibo do atendimento

Quem pede três cópias autenticadas e uma certidão na mesma ida ao balcão espera
**um papel**, e não quatro.

**Ele é do que já entrou no caixa**, e não do que foi orçado: item ainda não
quitado não entra. Recibo é prova de pagamento, e dizer que se recebeu o que não
se recebeu é o tipo de papel que volta.

**Ele marca todos os lançamentos que somou.** Sem isso, o mesmo dinheiro sairia
num segundo recibo — e dois recibos do mesmo pagamento é o que ninguém consegue
conferir depois.

**A forma é a do recibo que já existia** — numeração por exercício, teor
congelado e hash. Duas formas de recibo na mesma casa seria uma a mais para
conferir.

---

## O protocolo do RI não precisou de nada

Foi o único pedaço desta mudança que já estava pronto: `ri_protocolos` guarda
número, livro, data da prenotação, apresentante, natureza do título, objeto,
data-limite, suscitação de dúvida e o selo da prenotação — e
`cx_protocolos.ri_protocolo_id` já era o elo com o geral.

**Separado, com os atributos da prenotação, atrelado ao geral** — exatamente o
que foi pedido, e que já existia.
