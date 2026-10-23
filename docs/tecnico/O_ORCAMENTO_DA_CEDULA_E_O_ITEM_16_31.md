# O orçamento da cédula, o item 16.31 e a quantidade que nunca multiplicou

21/09/2026. Começou com um pedido simples do oficial — *«faça o orçamento no
sistema desse pedido de registro (…) aproveite e já veja os problemas de
acrescentar manualmente»* — e terminou em quatro consertos, um deles em dinheiro
de 5.388 protocolos.

O pedido é o protocolo **2026.09.46**: cédula de crédito bancário nº
030-26/5178-0, do Pessoa Exemplo, **R$ 695.404,50**, emitida por PESSOA EXEMPLO, com duas garantias — **penhor cedular** de 206 garrotes e
**alienação fiduciária** da Fazenda Vale do Eden II, matrícula 3.247.

---

## 1. O orçamento, e de onde saiu cada linha

Não foi redigido: foi **imitado dos precedentes desta casa**. Medidos em
`cx_protocolo_atos` os protocolos de 2026 cujo assunto cita cédula, o desenho é
sempre o mesmo — e os de origem `EOFICIO` provam que é o que o E-Ofício fazia:

| item | o que é | no protocolo 2026.09.46 |
|---|---|---|
| **16.1** | prenotação | 1 × R$ 43,37 |
| **16.45.23** | registro da garantia, pela faixa do valor | 2 × R$ 12.976,81 |
| **16.24.4** | certidão de inteiro teor/ônus, 1ª folha | 1 × R$ 101,88 |
| **16.39** | arquivamento, **por folha** | 44 × R$ 6,92 |
| **16.42** | conferência de documento público pela internet | 2 × R$ 6,92 |
| | **total** | **R$ 26.417,19** |

As 44 folhas são as dos PDFs apresentados (22 da cédula + 17 do relatório de
assinaturas + 1 CND + 3 da declaração do ITR + 1 do recibo). **Não entrou
reconhecimento de firma** (`13.17.4`), que aparece em vários precedentes: esta
cédula veio assinada digitalmente.

**Dois registros, e não um** — é o que a anotação da própria prenotação diz
(«CEDULA DE CREDITO BANCARIO LIVRO-2 LIVRO 3 AUXILIAR») e o que o protocolo
2026.03.279 fez, com dois `16.45.21` na mesma linha do tempo.

---

## 2. A pergunta do oficial, e por que a resposta é «não»

> «não seria caso de dividir o valor total do contrato pelo número de
>  garantias?»

**Não: pelo número de IMÓVEIS, e dentro de cada garantia.** É o que o item
**16.31** diz — «quando dois ou mais imóveis forem dados em garantia; ou no caso
de penhor, quando a garantia esteja estipulada em mais de um imóvel» — lido com
o **16.29**, que manda cobrar separadamente cada registro do mesmo título.

O grupo de registradores do Maranhão fixou isso em 27/08/2026, e o exemplo é a
mesma forma desta cédula com outros números:

> «Mútuo de 200 mil com hipoteca de 1 imóvel e penhor em 2 imóveis.
>  HIPOTECA: base de cálculo 200 mil.
>  PENHOR: base de cálculo 100 mil para cada imóvel de localização.»

**Cada tipo de garantia guarda o valor cheio; o que se divide é cada garantia
pelos imóveis em que ELA está.** Na cédula do Pessoa Exemplo, a alienação
fiduciária está num imóvel (mat. 3.247) e o penhor está **no mesmo** («assentado
no terreno: Fazenda Vale do Eden II, 3.247»). Um imóvel para cada: **não há o
que dividir**, e o orçamento fica como está.

### E dividir nem sempre é desconto

Vale registrar porque contraria a intuição: duas faixas menores podem somar mais
que uma grande. Os mesmos R$ 695.404,50 em **dois** imóveis dariam dois
`16.45.20` de R$ 6.644,36 — **R$ 13.288,72**, que é mais que os R$ 12.976,81 de
um `16.45.23` sozinho. Por isso a divisão não é escolha do balcão: é o que o
item manda quando a garantia está em mais de um imóvel.

---

## 3. O teto do art. 37, que quase pegou

A Resolução-GP 143/2025, art. 2º, põe o limite geral de emolumentos em
**R$ 21.380,93**. Os dois registros desta cédula somam **R$ 23.172,88** de
emolumento: cada um passa longe do teto, e juntos estouram.

**Como o teto se conta está em disputa aberta**, e as duas leituras estão no
grupo, no mesmo fio:

- **por tipo de garantia** (Pessoa Exemplo: *«limite é por garantia e
  circunscrição»*; Pessoa Exemplo: *«o teto é por circunscrição e por tipo de
  garantia»*) — e aí uma cédula com duas garantias tem **dois tetos**;
- **pela soma dos registros do mesmo título** (Pessoa Exemplo: *«é a soma de todos os
  imóveis no mesmo contrato»*), e Pessoa Exemplo aponta que o texto do 16.31 não é
  claro: *«se a norma quis se referir que o teto é a cada um dos registros,
  acabou dizendo o óbvio»*. **Há ofício na corregedoria.**

**O sistema mede e avisa; não corta.** É a régua do CNIB e do usucapião: cortar
por uma das duas leituras seria o sistema decidindo tese jurídica no lugar de
quem assina. A tela do protocolo passa a mostrar os dois números — o que a
tabela deu e o que o teto daria — e o oficial decide. Nesta cédula ele decidiu,
em 21/09/2026, ficar com **os dois tetos**.

### O teto não é número escrito no código

Ele muda por Resolução a cada exercício. `emolumentos.teto_geral()` o lê da
**última faixa da tabela 16.3** — conferido, não deduzido: o `16.3.36` da
vigência 10022 traz exatamente R$ 21.380,93 de emolumento e R$ 23.946,65 de
total, que é o número que a colega citou no grupo. É a mesma decisão da
constante de custas do Protesto: *deixou de ser um número escrito e passou a ser
lido da tabela*.

---

## 4. Os problemas de acrescentar manualmente

### 4.1 O ato pedido não aparecia na busca

Medido no banco da casa: dos 1.317 serviços, **273 códigos do TJ aparecem mais
de uma vez** — o `16.45.23` está nos serviços **732, 1064 e 1506** — e **só um
de cada tem preço na vigência**. Dois efeitos, e o segundo trava:

1. duas das três linhas não funcionam: clicar devolve «Não encontrei esse ato na
   tabela vigente. Confira o código ou o valor do negócio» — frase que manda
   conferir o código justamente quando ele está certo;
2. **o triplo de linhas estourava o limite antes do ato pedido.** A tela lista
   30; procurando `16.45`, a lista parava no `16.45.18`. **O `16.45.23` não
   aparecia de jeito nenhum**, e quem estivesse no balcão concluiria que a
   tabela não tem o ato.

`EMOL.buscar` passou a devolver **uma linha por código do TJ**, ficando com a
que tem preço. Isso não esconde ato nenhum, e o número que autoriza é medido:
**nenhum** código do TJ tem dois preços na mesma vigência — a escolha nunca
decide entre dois valores.

> **Subir o limite seria o conserto errado**: deixaria as duas linhas mortas na
> tela, e a de cima, sem preço, é a que o olho pega primeiro.

### 4.2 Quatro rótulos iguais na caixa das faixas

As tabelas 6, 7, 8 e 9 de `TABELAS_FAIXA` diziam todas «Registro de Imóveis».
Quem precisa da faixa do crédito rural não tinha como distinguir da dos
registros torrens — escolheria pelo número do item, que é justamente o que ainda
não se sabe quando se está procurando. Os quatro nomes agora são os da
**descrição do próprio item** em `cx_servicos`, lidos no banco.

### 4.3 Não havia onde dizer em quantos imóveis a garantia está

No portal do selo isso se faz pelo `16.13.1`, que remete ao `16.45` e abre a
opção de dividir. Aqui não existia o campo: o balcão teria de dividir na mão e
digitar o resultado — e **valor digitado é justamente o que esta tela existe para
não ter**. O formulário «acrescentar pela faixa» ganhou *Imóveis em que esta
garantia está*, e o item entra com a base dividida, a quantidade igual ao número
de imóveis (um registro, um selo por imóvel) e a conta escrita na frase da tela.

**A divisão é em centavos inteiros**, pela mesma razão de `faixa_por_valor`
comparar inteiros: em ponto flutuante, uma divisão por três põe a base do lado
errado da fronteira de uma faixa. **A sobra é declarada** — quem confere precisa
saber que a soma das bases não fecha com o contrato por aqueles centavos.

---

## 5. A quantidade que nunca multiplicou (e é dinheiro)

`cx_protocolo_atos.valor_total` queria dizer **duas coisas conforme a origem da
linha**:

| | |
|---|---|
| o balcão, acrescentando à mão | quantidade × unitário |
| a carga do E-Ofício | o unitário, com a quantidade ao lado sem efeito |

O caso mais claro é o `16.39` — «arquivamento, **por folha** do documento»: um
protocolo com 128 folhas somava R$ 5,92.

| | |
|---|---|
| itens vindos do E-Ofício | **32.393** |
| deles com quantidade maior que 1 | **7.483** |
| o que a soma do protocolo deixa de contar | **R$ 643.694,38** |
| desses itens já quitados | **2** |

### Duas medições independentes, e a segunda é a que decide

**No acervo**: em **185** pares (código do TJ, ano) com mais de uma quantidade o
`curv_Emolumento` é **constante**, e em **zero** ele escala — o `13.17.2` sai
5,92 tanto na quantidade 1 quanto na 90, e os fundos acompanham o unitário (4%
de 5,92 = 0,23 em todas). Os 11 pares que não ficaram constantes **não
escalam**: são troca de tabela no meio do ano e itens de faixa, cujo valor
depende da base.

Isso prova que a coluna é unitária. **Não prova que a casa cobrou
multiplicando** — e essa é a pergunta que importa antes de mexer em dinheiro.

**No caixa desta casa**, que é o dinheiro que de fato entrou: em **3.799**
protocolos pagos o lançamento bate com **quantidade × unitário**, e em **1** com
o unitário. A casa cobrou multiplicando; era o nosso registro que estava a
menos — a ficha do protocolo mostrava menos do que a serventia recebeu.

> **Teste de mesa prova a regra; só o dado real prova o dado.** O acervo dizia
> «a coluna é unitária»; quem respondeu «e a casa cobrou assim» foi o caixa,
> que é outra fonte.

### O que foi feito, e o que espera ordem

- **`caixa_import` passou a multiplicar** o emolumento e os quatro fundos pela
  quantidade. Carga futura entra certa.
- **`tools/quantidade_nas_custas_do_eoficio.py`** acerta o que já entrou. Ele
  **só mede por padrão**; com `--confirmar` tira cópia do banco (`VACUUM INTO`)
  antes de tocar em nada e grava a auditoria à mão, porque a rota não foi usada.
  **É idempotente**: lê o unitário do acervo por `origem_chave` e grava o
  produto, de modo que rodar duas vezes dá o mesmo resultado.

  Ele **recusa**, declarando cada caso: item já quitado ou com lançamento no
  caixa (esse dinheiro entrou, e sai por estorno, que é decisão de quem assina);
  chave de origem que não está no acervo; e item cujo valor gravado não bate nem
  com o unitário nem com o produto — alguém o editou, e o script não adivinha.

  Medido em 21/09/2026: **7.468 a corrigir, 13 já certos, 2 recusados, 5.388
  protocolos, R$ 643.470,82 de diferença.**

**A execução espera ordem do oficial** — não foi rodada.

---

## 6. Os testes

| arquivo | o que guarda |
|---|---|
| `tests/test_busca_do_ato_repetido.py` | uma linha por código do TJ, a que tem preço, e o limite contando atos e não repetidas |
| `tests/test_garantia_em_varios_imoveis.py` | a divisão do 16.31, a sobra declarada, o teto lido da tabela, o aviso na tela — e o varredor que recusa função que corte o valor sozinho |
| `tests/test_carga_do_caixa_multiplica_a_quantidade.py` | a carga multiplicando emolumento e os quatro fundos, com quantidade ausente e zerada valendo 1 |
