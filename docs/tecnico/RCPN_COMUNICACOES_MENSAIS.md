# As cinco comunicações mensais de óbito

*29/08/2026 — achado ao preparar a relação da Junta Militar, e é maior do que
ela.*

---

## O que a norma manda, e é mais do que eu tinha visto

Eu tinha achado **uma** obrigação mensal — a relação da Junta Militar, da Lei
4.375/1964. Ao procurá-la no Código de Normas do TJMA, apareceu o **art. 226**,
que traz **quatro outras**, com prazo e com sanção:

> **Art. 226.** O oficial de registro civil deverá comunicar, **até o 5º
> (quinto) dia útil do mês subsequente**, os registros de óbitos lavrados no mês
> anterior, aos seguintes órgãos:
>
> **I** — juiz(íza) eleitoral, em relação aos **maiores de 16 anos**, para
> cancelamento das inscrições de alistamento eleitoral, **sob as penas do art.
> 293 do Código Eleitoral**;
> **II** — Ministério da Economia, nos termos do art. 52, § 3º, da Lei
> 6.015/1973;
> **III** — Receita Federal, nos termos do art. 80, parágrafo único;
> **IV** — Instituto de Identificação do Maranhão, nos mesmos termos.

E o **§ 2º**: «A omissão ao cumprimento do disposto no § 1º **sujeita o(a)
delegatário(a) à responsabilização** prevista nos termos da Lei.»

**Com a Junta Militar, são cinco destinos, todo mês.**

---

## Cada destino tem um filtro próprio, e os filtros são da norma

| destino | quem entra | de onde |
|---|---|---|
| **Juiz eleitoral** | **maiores de 16 anos** | art. 226, I |
| Ministério da Economia | todos | art. 226, II |
| Receita Federal | todos | art. 226, III |
| Instituto de Identificação do MA | todos | art. 226, IV |
| **Junta de Serviço Militar** | **homens de 17 a 45 anos** | Lei 4.375/1964 |

**Medido nos 31 óbitos do acervo:**

| destino | alcança |
|---|---|
| eleitoral | **29** de 31 |
| Economia, Receita, Identificação | **31** de 31 |
| Junta Militar | **4** de 31 |

**Mandar a lista inteira ao juiz eleitoral seria mandar nome de criança para
cancelar alistamento que nunca existiu.** Mandar só os maiores de 16 à Receita
seria esconder dela metade dos óbitos. Por isso o filtro mora junto do destino, e
não numa consulta escrita à mão em cada lugar.

### E quem não tem idade ENTRA

Deixar de fora quem não tem idade seria esconder um óbito do órgão por falta de
um campo — e o § 2º responsabiliza quem omite. Ele entra, e a lista o marca.

---

## O prazo é em DIAS ÚTEIS, e desta vez o artigo qualifica

«até o **5º (quinto) dia útil** do mês subsequente». É diferente dos outros dois
prazos que este projeto já mediu:

| obrigação | prazo | dias |
|---|---|---|
| anotações (art. 367) | 5 | **corridos** — o artigo não qualifica |
| SIGEF (art. 620, § 2º) | 30 | **corridos** — idem |
| **comunicações mensais (art. 226)** | **5** | **úteis — o artigo diz** |

**Não se conta aqui**: quem conta dia útil é `ri_schema.soma_dias_uteis`, que
conhece os feriados desta comarca e já serve a prenotação, o edital do usucapião
e a retificação. Uma segunda contagem divergiria — e num prazo, divergir por um
dia é perder o prazo.

---

## O arquivo de dois anos, que não é detalhe

> **§ 1º, III** — «A comunicação de óbito deverá ser **arquivada** em meio
> físico ou virtual na serventia, **organizada por períodos mensais**, pelo
> **prazo mínimo de dois anos**.»
>
> **§ 1º, IV** — «Após o decurso do prazo legal, as comunicações somente poderão
> ser incineradas ou descartadas **após comunicação ao(à) juiz(íza) da vara de
> registros públicos**.»

É o que se mostra numa correição. Por isso o que sai fica guardado — o texto
inteiro, e não só o nome do arquivo —, organizado por mês, como o artigo manda.

---

## O tamanho do que está pendente

Medido nos óbitos do acervo, por mês de lavratura:

| mês | óbitos |
|---|---|
| 2026-04 | 7 |
| 2026-05 | 2 |
| 2026-06 | 4 |
| 2026-07 | **13** |
| 2026-08 | 2 |

**Cinco meses de 2026, 28 óbitos, cinco destinos cada** — até **25 remessas**
que podem estar em aberto. E nada no sistema as acompanhava.

---

## O que o módulo NÃO faz, e por quê

**Não envia.** Cada órgão recebe por um caminho próprio — ofício, sistema,
malote — e **nenhum deles está medido**. O eleitoral tem o INFODIP, e o cadastro
dele é passo do oficial no TRE; os outros três não têm caminho conhecido nesta
casa.

Ele **monta a relação, guarda o que saiu e cobra o prazo**; quem manda é a
pessoa, e registra o protocolo. É a mesma decisão do edital do usucapião: até
haver integração medida, o sistema faz o que se pode fazer com verdade.

---

## Um conserto que veio de brinde

A idade no óbito passa a **descontar o aniversário**. É correção de um defeito
**do E-Ofício**, medido em 28/08 ao conferir a remessa do IBGE: ele fazia `ano do
óbito − ano do nascimento` e mandava a idade **um ano a mais** para quem morreu
antes do aniversário — em **3 dos 11** óbitos comparáveis.

Como a idade agora decide **quem entra em duas das cinco relações**, o erro
deixaria de ser estatístico e passaria a ser de lista: um homem de 45 anos que
morresse antes do aniversário entraria na Junta Militar com 46 e sairia dela — ou
o contrário.

---

## E não são só as mensais — o mapa inteiro

Ao procurar as outras obrigações de comunicar no Código de Normas, apareceram
mais três, e duas delas são mais graves que as mensais.

### Art. 225 — o SIRC é de UM DIA ÚTIL

> «O oficial de registro civil remeterá, **no prazo de até 1 (um) dia útil**, ao
> INSS, por meio do **Sistema Nacional de Informações de Registro Civil
> (SIRC)**, a relação dos nascimentos, dos natimortos, dos casamentos, dos
> óbitos, **das averbações, das anotações e das retificações** registradas na
> serventia.»

**É o prazo mais apertado do sistema inteiro**, e cobre tudo — não só o óbito.

- **§ 1º**: municípios sem provedor de internet têm **5 dias úteis**;
- **§ 3º**: **mês sem registro nenhum também se comunica**, até o 5º dia útil do
  mês subsequente — é a «declaração de inexistência de movimento» que o manual
  técnico do SIRC descreve, e que existe por web service desde a versão 3.3;
- **§ 4º**: descumprir ou informar dado inexato sujeita à penalidade do **art. 92
  da Lei 8.212/1991** e à **ação regressiva do INSS**.

> **A averbação, a anotação e a retificação entram no SIRC.** Isso amarra
> diretamente no módulo de anotações que esta casa acabou de construir: cada
> anotação feita gera, além da comunicação à serventia de origem, uma linha para
> o SIRC — e o manual técnico dele confirma, com data e `dadosComplementares` de
> 10 a 1.000 caracteres para cada uma das três.

### Art. 224 — o IBGE tem dia certo, e multa

> «O oficial remeterá, **até o dia oito** dos meses de **janeiro, abril, julho e
> outubro**, à Fundação IBGE, o mapa dos nascimentos, casamentos e óbitos
> ocorridos no trimestre (art. 49 da Lei 6.015/1973).»
>
> **§ 2º** — «Os oficiais que, no prazo legal, não remeterem os mapas
> incorrerão em **multa de um a cinco salários-mínimos**, a ser cobrada como
> dívida da União, **sem prejuízo da ação penal cabível**.»
>
> **§ 3º** — «No mapa deverá ser informado o **número da identificação da
> Declaração de Nascido Vivo — DNV**.»

`ibge_geracao.py` já monta o mapa e foi conferido posição por posição contra os
arquivos reais. **O que faltava era o prazo**: o sistema não sabia que o dia 8
existe, nem que o atraso tem multa.

### Art. 253, § 2º — a FUNAI, e é IMEDIATO

> «O oficial deverá comunicar **imediatamente à FUNAI** o assento de nascimento
> do indígena, para as providências necessárias ao registro administrativo.»

**E esta casa registra indígenas.** Medido nos 193 nascimentos do acervo:
**quatro**, todos do povo **Krikati** — e **três são de 2026**:

| nome | assentado em |
|---|---|
| PESSOA EXEMPLO | 12/12/2022 |
| PESSOA EXEMPLO | **10/07/2026** |
| PESSOA EXEMPLO | **14/07/2026** |
| PESSOA EXEMPLO | **05/08/2026** |

> **E eles só aparecem porque alguém preencheu a cor.** `strRacaCor` está em
> branco em **178 dos 193**. O campo `cor_raca`, que entrou com o termo, é o que
> faz esta obrigação ser vista — sem ele, um nascimento indígena passa como
> qualquer outro e a FUNAI nunca é avisada.

---

## O mapa inteiro das comunicações do RCPN

| destino | o quê | prazo | sanção |
|---|---|---|---|
| **SIRC / INSS** | tudo, inclusive averbação, anotação e retificação | **1 dia útil** | art. 92 da Lei 8.212 + ação regressiva |
| **IBGE** | mapa trimestral, com o nº da DNV | **dia 8** de jan/abr/jul/out | multa de 1 a 5 salários + ação penal |
| **FUNAI** | nascimento de indígena | **imediatamente** | — |
| juiz eleitoral | óbitos de maiores de 16 | 5º dia útil do mês seguinte | art. 293 do Código Eleitoral |
| Ministério da Economia | óbitos | 5º dia útil | responsabilização (§ 2º) |
| Receita Federal | óbitos | 5º dia útil | idem |
| Instituto de Identificação do MA | óbitos | 5º dia útil | idem |
| Junta de Serviço Militar | óbitos, homens de 17 a 45 | mensal | — |
| CRC Nacional | anotações a outras serventias | 5 dias | — |

**Nove destinos, com cinco prazos diferentes** — e nenhum deles o sistema
acompanhava.

---

## O que fica pendente, e é seu

- **o endereço de cada destino** — para onde vai o ofício de cada um;
- **o cadastro no INFODIP**, no TRE (o formulário se assina, digitaliza e envia;
  usuário e senha voltam por e-mail em até 3 dias úteis);
- **se há caminho eletrônico** para o Ministério da Economia, a Receita e o
  Instituto de Identificação do Maranhão, ou se são ofício em papel.

**Nada disso impede começar**: o módulo monta as cinco relações e as guarda; o
caminho de saída se acrescenta quando você disser qual é.
