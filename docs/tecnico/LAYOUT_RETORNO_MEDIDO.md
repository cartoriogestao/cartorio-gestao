# O layout do retorno (SDTBFORTP), medido — versão 3.5.2

**24 de agosto de 2026.** O uso do sistema segue suspenso; nada disto foi aplicado.

## O que é este arquivo, e por que a casa o tem

`SDTBFORTP` é `cartório → apresentante`: é a casa que EMITE este arquivo, contando
o que aconteceu com cada título — apontado, protestado, pago, cancelado. O
sistema antigo gerou 383 registros desses entre 2020 e 2026, guardados como
histórico em `C:\ARPNET\CRA\Retorno` (e um extraviado em `Cancelamentos`, e
outro em `Remessa` — as pastas continuam mentindo, como já sabíamos).

Escrever o retorno de verdade é o item 8 do roteiro do Protesto — "o que fecha
o ciclo". Antes de escrever, medi os 383 que já existem, do mesmo jeito que o
layout da remessa foi medido: casando cada registro com o título dele em
`tbAvisoProtesto`, por `strNossoNumero` — **100% dos 383 casaram**.

## O que veio de graça: metade do registro é igual à remessa

Não é um layout novo do zero. O cabeçalho, o rodapé, e boa parte do registro
de título são a MESMA estrutura de `TITULO_NA_REMESSA` — só que com blocos
inteiros em branco porque o retorno não precisa repetir o que já foi enviado:

| Campo | Posição | Igual à remessa? |
|---|---|---|
| `codigo_do_apresentante`, `identificacao_do_apresentante` | 2–19 | sim |
| `nosso_numero` | 199–213 | sim — é a chave que casou os 383 |
| `valor_do_titulo` | 247–260 | sim — **99,7%** contra `curValorRealTitulo` |
| `saldo_a_protestar` | 261–274 | sim — **99,7%** contra `curValor` |
| espécie, número do título, datas de emissão/vencimento, cedente, devedor | 214–246, 275–445 | **sempre em branco** no retorno |

## O que é novo, e só existe no retorno: o bloco 446–485

Um bloco de 40 posições que a remessa não usa (lá é `reservado_446`, "zeros com
uma letra D/C/I na posição 477 — não identificada"). No retorno, ele carrega
quatro coisas:

| Campo | Posição | Conferiu contra o acervo |
|---|---|---|
| `reservado_446` | 446–447 | constante `"01"` nos 383 — código fixo, não dado |
| `protocolo` | 448–457 | **98,4%** (377/383) contra `intProtocolo` |
| `ocorrencia` | 458 | **95,8%** (367/383) contra `intCodigoOcorrencia` |
| `data_movimento` (candidata) | 459–466 | **66,8%** contra `dtmE_Cartorio` — ver abaixo |
| `valor_evento` | 467–476 | só 20 dos 383 são diferentes de zero; nenhuma soma de
custas testada bateu — **A CONFERIR** |
| (separador) | 477 | sempre branco nos 383 |
| `data_ocorrencia` | 478–485 | **95,6%** (366/383) contra `dtmOcorrencia` |

`ocorrencia` (posição 458) é o mesmo campo que já era conhecido do lado do
acervo: nos 383, **287 vezes é `C`** — a mesma marca sem significado oficial
que `LEVANTAMENTO_PROTESTO.md` já tinha achado 1.027 vezes no acervo inteiro.
As seis divergências entre a posição 458 e `intCodigoOcorrencia` são todas
casos em que o título tem cancelamento: parece que quando o cancelamento é
mais recente que a última ocorrência gravada, o arquivo leva
`strOcorrenciaCancelamento` (também uma letra, `A`) no lugar do código
numérico. Não confirmei isso contra mais casos — fica anotado como hipótese,
não como medida.

## A segunda medição, com o lote de 2026 — e o que ela fechou

**24/08/2026, mais tarde.** O oficial indicou a pasta da CRA na rede da serventia: 119
arquivos, sufixo `.261`/`.262`, de 2026 — lote **mais novo** que o de
`C:\ARPNET\CRA` (2022–23). São 40 retornos com 60 títulos, e **os 60 casaram
com o acervo**, como os 383. Pool combinado: **443 registros, cobrindo quatro
anos.**

Os arquivos chegam como marcador de nuvem e cada leitura força um download —
medir direto na pasta não termina. Hidratei a pasta inteira primeiro, e daí a
medição roda em segundos.

Com quatro anos de amostra em vez de dois, três dos cinco campos deixaram de
ser dúvida:

### `data_entrada` (459–466) — identificado, e não pela taxa

Batia 65,5% contra `dtmE_Cartorio` — taxa que não autoriza batizar campo. O que
fechou foi a **ordem**, testada cruzando os arquivos entre si: para os 362
títulos que aparecem tanto numa remessa quanto num retorno, esta data **nunca é
anterior à data da remessa** que trouxe o título.

| Diferença | Registros |
|---|---|
| mesmo dia | 253 |
| +1 dia | 40 |
| +2 a +7 dias | 61 |
| fora disso | 8 (três são títulos reapresentados) |

É o perfil exato de "entrada no cartório": a remessa chega e a casa protocola no
mesmo dia ou em poucos dias, nunca antes. Some-se a posição — colada ao
protocolo, que é o número que se dá na entrada. Os 34,5% que divergem de
`dtmE_Cartorio` são esperados: o E-Ofício deixava editar aquela data depois.

Passou a se chamar `data_entrada`, com a taxa medida ao lado.

### `reservado_566` — é campo do ARQUIVO, não do registro

O achado que reorganizou a pergunta: **é constante em todos os 194 arquivos
medidos, sem uma única exceção.** Estava sendo lido como atributo do título, e
não é — vem repetido em cada linha do mesmo arquivo.

Sobre o que ele marca, o que a medição mostra:

| Valor | Registros | Casa com |
|---|---|---|
| branco | 130 | título pago ou arquivado — 76 têm selo de arquivamento, a maioria tem `strTipoPG` |
| `A` | 173 | título protestado, sem arquivamento |
| `P` | 140 | idem |

O que separa `A` de `P` **não é atributo de título nenhum**: cruzei contra as
176 colunas de `tbAvisoProtesto`, uma por uma, e a que melhor explicou acertou
60% contra 42% de linha de base — ou seja, nada. Sendo constante por arquivo e
sem correlação com o conteúdo, o que resta é marca de geração do arquivo. Fica
`reservado_566`, agora com o motivo escrito.

### `reservado_486` e `reservado_568` — não são dúvida, são preenchimento fixo

`486` traz `"00"` em 442 dos 443. `568` traz zero nos 443. **Quatro anos, dois
lotes, duas versões do E-Ofício, e nenhuma variação.** Isso não é "campo que
esta casa nunca usou": é preenchimento fixo do layout. Deixam de ser pergunta
aberta e passam a ser fato medido — com a observação dizendo isso, para ninguém
gastar tempo "descobrindo" o que já se sabe.

### `reservado_467` — o único que continua A CONFERIR, e agora se sabe o que ele NÃO é

Zero em 416 dos 443. Nos 27 não-zero, os valores se repetem e se agrupam pela
ocorrência: R$ 230–250 na ocorrência `A`, R$ 68–134 na `3`. Tem cara de tarifa
de tabela.

Não é custa do acervo, e isto foi testado a fundo: **busca exaustiva de toda
soma de 1 a 5 das 60 colunas `cur*`** de `tbAvisoProtesto` explicou 2 dos 27, com
combinações sem sentido (`curValor + curProtesto_Valor + curV_Diligencia_MP +
curArquivamento_MP`) — coincidência aritmética, não achado.

A hipótese que sobra vem do manual de procedimentos da CRA, que diz que o
cartório informa no retorno **o valor cobrado pelo banco pela TED do repasse**.
Bate com o perfil: quase sempre zero, valor pequeno, e sem coluna equivalente no
acervo — porque o E-Ofício não guardava tarifa de banco. Não há contra o que
conferir, então fica A CONFERIR.

## Os outros dois tipos de arquivo — medidos, e não eram um layout novo

O lote de 2026 trouxe ANDAMENTO (`SDTBFOAND`) e CONFIRMAÇÃO (`SDTBFOCRT`), os
dois tipos que o catálogo conhecia pelo sentido e cujo registro de título nunca
havia sido medido. Com o lote antigo somado, deu **371 registros de confirmação
e 105 de andamento**.

**Eles não têm layout próprio.** São o layout da **remessa** — cedente, devedor,
endereço, espécie, tudo preenchido — **mais o bloco 446–485 do retorno**, que
traz protocolo, ocorrência e as datas. E faz sentido assim: eles devolvem ao
apresentante o título que ele mandou, dizendo o que a casa fez com ele.

A prova é limpa: lidos com o layout da remessa, a espécie de **todos os 476
registros** confere com o acervo, casando por número do título — 105/105 e
371/371. O protocolo, no bloco do retorno, confere em 447 dos 476 (94%).

Em `protesto_arquivo.py` o layout é **composto**, e não transcrito:
`TITULO_NA_CONFIRMACAO` é `TITULO_NA_REMESSA` com o `reservado_446` trocado pelo
bloco do retorno, e a composição recusa faixa que não cubra exatamente 446–485.
Transcrever daria um quarto lugar para a mesma medida divergir; composto,
qualquer correção futura na remessa ou no retorno chega aqui sozinha.

**Os quatro tipos do catálogo agora têm layout.** A linha crua ficou reservada
para um tipo novo que apareça amanhã — que continua não sendo lido com o layout
de outro.

## O que não identifiquei, e não batizei

> **Esta seção é a da PRIMEIRA medição, e a segunda a superou.** Deixo-a à
> vista em vez de reescrever em silêncio, porque é o registro de onde a
> investigação estava. Quatro dos cinco itens abaixo foram resolvidos na
> segunda medição, acima: `459` virou `data_entrada`, `486` e `568` são
> preenchimento fixo, e `566` é campo do arquivo. Só o `467` continua de pé.

- **`data_movimento` (459–466)**: bate com `dtmE_Cartorio` em 66,8% dos casos,
  com `dtmOcorrencia` em 11 e com `dtmUSERID_A` em 5. Não fecha o suficiente
  para eu escolher uma das três. Fica `reservado_459`.
- **`valor_evento` (467–476)**: zero em 363 dos 383. Testei contra 6 somas de
  custas (protesto, cancelamento, intimação, certidão, diligência,
  arquivamento) e contra 15 colunas de valor isoladas — nenhuma bateu nos 20
  casos não-zero. Fica `reservado_467`.
- **A letra em 566** (`A` em 160, `P` em 129, branco em 94): testei contra
  `snProtestado`/`snCanceladoProtesto` e contra ter selo de intimação pessoal
  ou por edital — nenhuma hipótese explicou a distribuição. Fica
  `reservado_566`.
- **Um bloco de dez zeros em 568–577**: zero nos 383 sem exceção. Reservado,
  nunca visto preenchido.
- **`devedor_bairro` (486–507)**: 367 trazem `"00"` e o resto é branco — não é
  bairro nenhum aqui, é outra coisa não identificada. Fica `reservado_486`.

Cinco campos sem nome bonito, porque nome bonito em campo desconhecido finge
conhecimento que não existe — a mesma regra da remessa.

**O que fez a diferença entre as duas medições** não foi mais engenhosidade: foi
mais amostra (443 em vez de 383, e quatro anos em vez de dois) e duas perguntas
melhores — "isto é constante dentro do arquivo?" e "isto é anterior ou posterior
ao outro arquivo?". Nenhuma das duas exige adivinhar.

## O rodapé também não é o da remessa

Ao testar contra os 194 arquivos reais, `quantidade_de_titulos` do rodapé —
lido na mesma posição e largura da remessa, 8 dígitos a partir de 53 — dava
**sempre `1000`**, nunca a quantidade verdadeira. Um arquivo com 1 título e
outro com 3 liam o mesmo `1000`: a resposta que parece medição e não é.

Procurando a posição certa: o campo tem **4 dígitos**, não 8, começando em
54. Medido nos 194: **188 batem (96,9%)**. `soma_dos_valores`, na mesma
posição da remessa (61, 15 dígitos), bate em **188/194** também — esse não
mudou. `RODAPE_RETORNO`, em `protesto_arquivo.py`, guarda os dois; os outros
tipos (`SDTBFOCRT`, `SDTBFOAND`) continuam com o rodapé da remessa até serem
medidos.

## Escrever — e a prova que o ida e volta deu

**24/08/2026, ainda.** Escrever é o item 8 do roteiro do Protesto, o que fecha o
ciclo: a casa recebe a remessa, aponta, protesta ou dá baixa, e devolve o
retorno ao apresentante.

A prova de que a escrita está certa não é conferir campo a campo — isso já se
fez na leitura. É o **ida e volta**: ler um arquivo real e reescrevê-lo tem de
sair **idêntico byte a byte**, inclusive nos campos que ninguém identificou,
porque eles também têm de voltar como estavam.

Contra os 572 arquivos reais de `C:\ARPNET\CRA`:

| | |
|---|---|
| voltam idênticos | **558** |
| recusados de propósito | 12 (multi-lote — ver abaixo) |
| diferentes | 2 |

Os dois que diferem trazem a string literal `ddMMyyyy` no campo de data de
emissão — lixo do programa que os gerou. A escrita põe zeros ali, e propagar a
corrupção seria pior.

### O que o ida e volta descobriu, e nenhuma outra conferência achou

Este teste pagou por si quatro vezes. Cada item abaixo é um defeito que estava
no código, passando por todas as outras conferências:

1. **O bairro do devedor começava duas posições antes do lugar.** Estava
   declarado em 486 com 22 posições, e "A CONFERIR" desde a primeira medição. O
   arquivo real trazia `000  VL JOA` e a reescrita saía `000VL JOAO `. As
   posições 486–487 são separador — dois espaços em 343 de 343 remessas — e o
   bairro é **488–507**. Com o limite certo, deixa de ser dúvida: sai `CENTRO`,
   `VL JOAO ALBERTO`, `ACUDE`, que são bairros de Cidade Exemplo. Não havia coluna
   de bairro no acervo contra a qual conferir, e foi por isso que a primeira
   medição parou ali — o próprio arquivo respondeu.

2. **O rodapé da remessa não conta títulos: conta REGISTROS.** Num arquivo de um
   título ele diz 3 — cabeçalho, título, rodapé. Lido como `quantidade_de_titulos`
   com 8 dígitos dava 3.000, e a conferência acusava "arquivo truncado" em **191
   remessas boas**. Alarme que soa sempre é alarme que ninguém ouve. Agora são
   dois campos com nomes diferentes, porque são coisas diferentes: o retorno e o
   andamento contam **títulos** (exato nos 190 medidos), a remessa e a
   confirmação contam **registros** (exato em 278 de 370).

3. **`99999999` é a marca de "sem vencimento", e a volta tem de escrevê-la.** A
   leitura a traduz para vazio, o que está certo — não há data. Mas escrever
   zeros ali seria pôr data inválida onde o arquivo dizia "não tem". Sem essa
   distinção, 22 arquivos reais voltavam diferentes.

4. **Campo reservado tem de ser lido como TEXTO, não como número.** O
   `reservado_508` estava como número; no andamento ele vem em três pedaços, com
   espaços no meio, e lido como número virava um inteiro só — a volta escrevia 38
   zeros seguidos e perdia a estrutura. Texto é o único tipo que devolve o campo
   como ele veio. Virou regra: **campo sem nome não se interpreta.**

### Os 12 que a escrita recusa, e por que recusar é o certo

Doze dos 572 arquivos têm **mais de um lote emendado** — cabeçalho, títulos e
rodapé repetidos no mesmo arquivo. A leitura já avisava (a linha que começa com
`0` ou `9` no meio vira achado), mas escrever a partir dela produziria um
arquivo com os lotes de trás **faltando, e calado**. `escrever()` recusa e diz
para separar os lotes primeiro.

## O que isto habilita, e o que ainda não

Dá para **ler** um arquivo de retorno real com confiança alta: protocolo,
ocorrência, data de entrada, data da ocorrência e valores. É o suficiente para
conferir o que a casa registrou contra o que o arquivo diz.

E dá para **escrever**: `escrever()` monta o arquivo e `montar_retorno()` monta
a estrutura de um retorno novo, com o rodapé calculado. Dos campos que sobravam
em branco por ignorância, três saíram da lista — `486` e `568` são preenchimento
fixo, e `566` é marca de arquivo. As duas incógnitas que restavam foram resolvidas pela regra que o oficial deu em
24/08/2026: **na dúvida, como o E-Ofício fazia, ou um padrão aceito antes.**

1. **`467`** sai zero — que é o que o próprio E-Ofício escreveu em 416 dos 443.

2. **A letra `A` × `P` em 566** sai do **apresentante**. Procurando o que a
   explicava, o achado: **29 de 30 apresentantes usam sempre a mesma letra.**
   Não é atributo do título, é convenção de quem apresenta.

   Conferido em dado que não foi usado para descobrir — a tabela montada só com
   o lote de 2022–23 acerta **11 de 11** no lote de 2026, e 127 de 128 no
   próprio lote de origem. Está em `MARCA_POR_APRESENTANTE`, e cada linha é uma
   letra que a Central **já aceitou** daquele apresentante.

   Há uma tendência visível, que **não** virou regra porque tem exceção: banco e
   instituição de crédito levam `P`; conselho profissional, governo e comércio
   levam `A`. O `FAA`, fundo de investimento com `A`, quebra a leitura fácil — e
   é por isso que vale a tabela medida, e não a teoria.

   **Apresentante sem histórico é recusado, não chutado.** Dos 148 arquivos
   medidos, 74 levam `A` e 74 levam `P` — empate exato. Num empate desses não
   existe "o que o E-Ofício fazia" para imitar, então `montar_retorno()` recusa
   e diz o que fazer: conferir num retorno recente aceito daquele apresentante e
   informar a letra.

O que continua valendo, e é o único jeito de saber: **só uma tentativa real de
envio** diz se a Central aceita o arquivo. A especificação oficial da CRA não
está nesta máquina, e não está nos cinco manuais do IEPTB-CE — conferidos um por
um em 24/08, são procedimento de tela, sem layout.

O que o ida e volta garante é outra coisa, e é bastante: um arquivo que esta casa
escreve é **indistinguível**, byte a byte, de um arquivo que o E-Ofício escreveu
e a Central aceitou. Se a Central recusar, não vai ser por forma.
