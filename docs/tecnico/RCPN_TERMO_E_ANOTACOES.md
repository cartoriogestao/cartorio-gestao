# O RCPN amadurece: o termo do livro e as anotações devidas

*29/08/2026 — «vamos seguir no desenvolvimento do nosso módulo maduro e completo
de RCPN», o oficial.*

Dois buracos grandes, e os dois eram **obrigações da casa que nada acompanhava**.

---

# PARTE 1 — O TERMO

## O que faltava, e por que ninguém tinha visto

Este sistema construiu a **certidão** do RCPN — montada dos campos, no modelo
nacional do CNJ — e **nunca construiu o termo**, que é o texto escrito no livro.

A explicação registrada era esta, e ela era **verdadeira e enganosa ao mesmo
tempo**:

> «Os 244 assentos do acervo não têm teor nenhum: as três colunas de texto estão
> vazias nas três tabelas de origem.»

Verdadeira: estão mesmo vazias. Enganosa: dela eu concluí que o E-Ofício não
tinha termo. **Ele tinha.** Em 29/08/2026, ao procurar o código do E-Ofício a
pedido do oficial, apareceu o motivo:

**O E-Ofício não guardava o teor — ele o montava do modelo na hora de
imprimir.** Os treze modelos estão em `tbModelosRCPN`, no acervo, em RTF, com o
texto inteiro.

> **Sétima vez neste projeto que «a coluna está vazia» não queria dizer «a coisa
> não acontecia».** As anteriores: o `codigoAto` dentro do `memJson`, os
> contadores em `tbPropriedadeRCPN`, o `intCodigoIBGE` do local do nascimento, o
> `strTipoMorte`, os caminhos de selo em `strURL_Selador`, e a DNV/CRC de ontem
> de manhã.

## O termo e a certidão são papéis diferentes

| | o termo | a certidão |
|---|---|---|
| onde vive | **no livro**, escrito uma vez | fora, quantas vezes se pedir |
| quando | na lavratura | a qualquer tempo |
| quem assina | o oficial **e o declarante** | só o oficial |
| se muda | **nunca** — averba-se ao lado | a próxima sai já corrigida |

**Por isso o termo congela.** `rc_assentos.teor` guarda o texto montado e ele
não se remonta: um sistema que o remontasse faria o livro de hoje discordar do
papel assinado ontem — e é o papel assinado que vale.

## As oito colunas que entraram, e cada uma está no termo E numa remessa

| coluna | por que |
|---|---|
| `hora_fato` | o termo escreve «às ...»; a CRC pede `<HORANASCIMENTO>` |
| `cor_raca` | o termo escreve «cor ...»; o IBGE exige; a CRC exige `<CORPELE>` com valores fechados. **Medida: preenchida em 15 dos 193 nascimentos do acervo** — pouco, e é por isso que o balcão precisa de campo para passar a perguntar |
| `local_fato_nome` e `local_fato_endereco` | onde o fato aconteceu — hospital, casa, via pública |
| `naturalidade_declarada` | **e ela não é o município do parto** — ver abaixo |
| `registro_tardio` | tem forma própria (art. 46 da LRP), e o E-Ofício tem modelo só dele |
| `idade_no_fato` (na pessoa) | «tendo a mãe, na ocasião do parto, X anos» — **e a remessa do IBGE a cobra** |
| `documento_orgao` (na pessoa) | o órgão do RG; a CRC pede `<CODIGOORGAOEMISSOR>` |

### São TRÊS municípios num nascimento, e confundi-los já custou caro

O termo desta casa diz, com o endereço da lei:

> «A naturalidade declarada é de …, **na forma do art. 54, § 4º, da Lei Federal
> n.º 6.015/1973**.»

É a faculdade de declarar como naturalidade o município de **residência da mãe**,
e não o do hospital. Num nascimento há três municípios diferentes:

1. onde a criança **nasceu** (o hospital);
2. onde a **mãe mora**;
3. o que se **declarou** como naturalidade.

**E este projeto já pagou por confundi-los, do outro lado**: o E-Ofício mandava
ao IBGE o município do **parto** como residência da mãe em **27 das 28** linhas —
o defeito mais caro que a comparação com o arquivo real achou.

### A idade da mãe no parto NÃO se calcula

O termo afirma a idade **no dia do parto**, e a data de nascimento da mãe falta
em boa parte dos assentos. Calcular onde falta daria idade errada num papel
assinado. **Guarda-se o que o declarante informou** — que é o que o E-Ofício
fazia, e é o mesmo campo que a remessa do IBGE cobra.

## O cabeçalho do E-Ofício não veio junto

Dois dos treze modelos trazem a **oficial anterior**, com endereço, telefone e
até um CEP diferente (65.289-000 contra 65.936-000). Copiar o cabeçalho traria o
oficial de ontem para dentro do sistema de hoje — o «carimbo que mente» outra
vez.

Quem responde pela serventia sai da **regra viva** — a substituta se houver,
senão o titular —, a mesma do cartão de autógrafo e da certidão do RI. **Há
teste que varre o módulo procurando o cabeçalho vazado.**

## E a qualificação pula o que falta

O termo do E-Ofício escrevia a frase inteira com os campos vazios no meio:
«portador do RG n.º , inscrito no CPF n.º ,». **Papel assinado com buraco no meio
é pior que papel sem a informação: ele afirma que há um RG e não diz qual.**

## Os 244 do acervo continuam sem termo, de propósito

Montá-lo agora seria escrever hoje um texto que foi lido e assinado há anos, com
os dados que sobreviveram à carga — e o que sairia não é o que está no livro de
papel. Para eles o caminho é a **certidão**, que diz o que o assento contém **sem
fingir ser a cópia do que foi escrito**. A tela diz isso, para ninguém achar que
é falha.

---

# PARTE 2 — AS ANOTAÇÕES DEVIDAS

## O terceiro prazo da casa que ninguém de fora cobra

Quando esta casa lavra um **casamento** ou um **óbito**, os assentos anteriores
daquela pessoa **têm de ser anotados**. Se o assento anterior é daqui, anota-se
aqui; se é de outra serventia, **manda-se comunicação**. E há **cinco dias**.

> **Art. 367** — «Sempre que o oficial de registro ou preposto autorizado fizer
> algum registro ou averbação, deverá, **no prazo de cinco dias**, anotá-lo nos
> atos anteriores, com remissões recíprocas, se lançados na serventia, ou fará
> comunicação, com resumo do assento, à serventia onde estiverem os registros
> primitivos.»

**É o terceiro prazo desta casa que ninguém de fora cobra**, e os três têm a
mesma forma — obrigação da serventia, que nasce **depois** do ato, com o cliente
já fora do balcão:

| | prazo | de onde |
|---|---|---|
| SIGEF, na retificação georreferenciada | 30 dias | art. 620, § 2º |
| relação da Junta Militar | **mensal** | Lei 4.375/1964 |
| **anotações** | **5 dias** | art. 367 |

O das anotações é **o mais curto e o mais frequente**: nasce em todo casamento e
em todo óbito.

## O que se anota onde — art. 372, na letra

> «O óbito deverá ser anotado, com as remissões recíprocas, nos assentos de
> casamento e nascimento. **Parágrafo único.** O casamento será anotado no
> registro de nascimento e nos registros anteriores de casamento.»

Note a assimetria, que é da norma: o óbito vai para dois assentos; o casamento
vai para o nascimento e para os casamentos **anteriores** — não para óbito
nenhum, porque quem casa está vivo.

### E as três do Livro E também anotam — e eu as tinha deixado de fora

**Foi a minha própria saída de conferência que mostrou.** Ao listar as espécies,
`INTERDICAO` aparecia como «nenhuma — é o registro primitivo», o que é falso: ela
não é primitiva coisa nenhuma, é uma sentença que muda a capacidade de quem já
tem nascimento lavrado.

> **Art. 328, § 2º** — «Compete ao registrador civil que proceder ao registro da
> sentença no Livro "E" comunicar tal fato ao registrador civil do nascimento
> e/ou casamento do emancipado, interditado ou ausente, que anotará tais
> circunstâncias nos assentos primitivos.»

E há uma **segunda comunicação** que só existe nas três: o **§ 3º** manda cada
oficial comunicar ao **juiz** que a determinou, em cinco dias, «sob pena de
responsabilidade administrativa».

## A CRC é o primeiro canal, e a ordem é da norma

| ordem | canal | de onde |
|---|---|---|
| 1 | **CRC Nacional** | art. 226, § 1º, I; art. 366, parágrafo único — Provimento 46/2015 do CNJ |
| 2 | malote digital (Sistema HERMES) | art. 226, § 1º, I — Provimento 25/2012 |
| 3 | carta em protocolo, ou outro meio eletrônico seguro | art. 371 — e só «em caso de falha desse sistema, **desde que haja confirmação de recebimento**» |

**Por isso o protocolo é obrigatório** ao registrar a comunicação: sem ele não há
confirmação, e comunicação sem confirmação é a que ninguém prova ter mandado.

> Isto amarra diretamente na pesquisa das centrais: a **CRC é o caminho de
> primeira escolha da própria norma**, e o envio automático dela existe — XML
> assinado com e-CPF em Base64. Ver `RCPN_PESQUISA_DAS_CENTRAIS.md`.

## O módulo NÃO anota sozinho no assento alheio

> **Art. 370** — «Antes de proceder à anotação, incumbe ao oficial observar a
> **compatibilidade dos atos registrários**. Sendo necessário, solicitará
> informações às serventias envolvidas.»

Um programa que anotasse sozinho estaria **decidindo que dois assentos são da
mesma pessoa**, que é justamente o que o oficial tem de conferir. O que se grava
é **que ele conferiu e anotou**, com a data e com qual assento — o rastro que a
correição procura. Há teste que compara o assento alvo antes e depois e exige que
nada tenha mudado.

## O resumo é resumo, e não o teor

O art. 367 manda ir «comunicação, **com resumo do assento**». A diferença
importa: o teor traz a qualificação de todo mundo, e mandá-lo a outra serventia é
espalhar dado pessoal que ela não precisa para anotar à margem.

O que vai é o que o art. 369 exige do outro lado: que ato foi, quando, e onde ele
está — serventia, livro, folha e número.

## Duas coisas que o balcão precisa saber, e estão na tela

**A parte pode pedir a anotação sem esperar o ofício** (art. 371, parágrafo
único): à vista de certidão atualizada — **prazo de 90 dias** —, «ainda que a
comunicação não tenha sido recebida». A pessoa chega com a certidão na mão, e o
escrevente pode achar que tem de esperar o ofício.

**A comunicação tem de ser certificada nos autos de habilitação** (art. 285,
parágrafo único), quando se trata de casamento.

## A lista vem do mais antigo para o mais novo

É o contrário de todas as outras listas deste sistema, e é deliberado: **aqui o
que importa é o prazo**, e quem está há mais tempo esperando é quem está mais
perto de estourar os cinco dias.

E **assento sem data não entra nas vencidas**: sem data não dá para dizer que o
prazo passou, e afirmar que passou seria pior que não afirmar nada.

---

## Os enganos desta construção, para não se repetirem

**A afinidade INTEGER mordeu pela quarta vez.** O teste gravava
`numero="11"` e `rc_assentos.numero` é INTEGER: o SQLite guarda `11`, e a
comparação com `"11"` falha. Os testes passaram a comparar **pelo id**, que é a
chave e não um texto que o banco reescreve.

**A comparação de texto do modelo tem de normalizar o espaço.** O Jinja quebra
linha onde a linha do modelo terminou, e «na ocasião do parto» sai com uma quebra
no meio. Em HTML isso é um espaço; numa comparação de teste é uma falha. **A
lição já estava registrada neste projeto**, do teste do cartão de autógrafo, e eu
a esqueci em três testes seguidos.

**O varredor de modelos olhava três arquivos escritos à mão.** Ao entrarem os
três termos do Registro Civil — consumidos por `rc_termo` — ele acusou falta onde
não havia. Passou a varrer o sistema inteiro. **Varredor com lista escrita à mão
envelhece na tarde em que se escreve**, e é a lição do menu pela terceira vez.
