# O endereço que estava escrito no teor

**O que este documento conta, e para quem.** O ONR recusa a matrícula cuja ficha
não tem endereço, e **o endereço de 1.442 fichas desta casa está escrito dentro do
teor** — o texto que a digitalização trouxe, em prosa, no meio da descrição do
imóvel. Este documento é o registro do extrator que lê esse texto
(`onr_endereco_do_teor.py`), da tela que confere o que ele leu, e das quatro portas
por onde se chega nele dentro do sistema. Quem lê é quem for mexer no assunto
depois — e quem precisar saber **por onde se anda** sem decorar caminho.

Medido em 16/09/2026, contra cópia do banco da produção (`VACUUM INTO`, leitura
pura).

---

## 1. O problema não era falta de dado

O painel do ONR (`/ri/onr`) lista as matrículas desta casa que ainda não subiram ao
Índice Real. Medido na cópia de 16/09/2026:

| | |
|---|---|
| matrículas desta casa sem indicador publicado | **434** |
| delas, **na fila do endereço** (teor e sem logradouro) | **367** |

**Oitenta e quatro por cento do que falta publicar trava no endereço.** Não é um
campo acessório: é o que decide se a matrícula vai ou não vai. E não é campo em
branco por esquecimento — as colunas de endereço nasceram com este sistema,
**depois** da digitalização, enquanto o teor já vinha escrito desde o E-Ofício.

O que existe na ficha é uma frase — esta é a da **matrícula 1904**, transcrita como
está no teor:

> «Uma gleba de terras denominada "Fazenda Serrinha" situada na zona rural deste
> município de Cidade Exemplo-MA, com a área de 30,77,70ha»

(O `30,77,70ha` está assim no teor: a vírgula a mais é da ficha, e o extrator não a
conserta — a área que ele propõe sai do número, e a tela mostra de onde veio. E o
texto chega com a marcação do editor — `<span style="font-weight:bold">` e
companhia —, que quem for ler o teor precisa descartar antes de procurar a frase.)

O contrato do ONR quer sete campos. Entre a frase e os sete campos havia um trabalho
que ninguém tinha feito — e era ele que segurava o índice.

---

## 2. As portas: por onde se chega ao extrator

**São quatro, e cada uma existe porque a pergunta nasce num lugar diferente.** Não
é redundância: é a mesma sala com quatro entradas, e nenhuma delas é a «oficial» —
quem procura por onde entrar acha a que estiver perto do problema dele.

| porta | onde | para quê |
|---|---|---|
| **O menu** | Registro de Imóveis → *ONR — endereços a conferir* | quem já sabe que o trabalho é este: despachar a fila inteira |
| **O painel do ONR** — `/ri/onr` | no alto da lista *O que falta publicar* | quem está lendo **o que** falta para publicar e descobre, na linha, que o que falta é o endereço. A pergunta seguinte («de onde eu tiro isso?») tem resposta na mesma tela |
| **A ficha do indicador** — `/ri/onr/indicador/<matrícula>` | botão *«o que o teor diz»* | quem está olhando **esta** matrícula e quer resolver a dela, agora |
| **A ficha da matrícula** — `/registro-imoveis/<id>` | botão *«o que o teor diz»*, ao lado do CNM | quem está no meio do registro de imóveis, que é onde a ficha se lê. **É aqui que o acervo é conferido no dia a dia** |

**O botão só aparece onde ele pode fazer algo** — a ficha com teor e **sem** o
logradouro preenchido. Sem teor não há o que ler; com o endereço já digitado a
proposta não tem o que acrescentar (o extrator não propõe sobre endereço
preenchido, e é a mesma régua do `gerar`). Botão que clica e recebe recusa ensina a
não clicar.

**E as duas portas novas — painel e ficha do indicador — não levam número.** O
painel diz onde se resolve o endereço; o número da fila (**1.442**) é da outra tela,
onde ele é o número daquela fila. Trazer 1.442 para o lado de 434 faria quem lê
concluir que a lista do painel é a fila do endereço — e elas não são: **a fila soma
o acervo (1.076 das 1.442)**, que o painel deixa de fora de propósito, porque o
E-Ofício já respondia ao ONR e mandar setenta anos de livro como novidade encheria
a fila deles com o que já está lá.

**Os três botões são POST, e não link.** Eles criam proposta, e nesta casa um `GET`
não abre transação de escrita — a mesma forma do botão que grava o CNM, dois
parágrafos ao lado na ficha da matrícula.

**Quem alcança:** `ADMIN`, `MANAGER` e `USER` — conferir aqui **escreve na ficha**,
e escrever endereço na ficha é operação de balcão, como corrigir o bairro à mão.
Publicar no ONR continua sendo do oficial, e **não tem botão neste módulo**.

---

## 3. A fila: o que as três situações querem dizer

A tela da fila (`/ri/onr/enderecos`) mostra o que o extrator leu, e o botão *Gerar*
(ou *Gerar de novo*) roda o extrator sobre todas as fichas que ainda não conseguem
ir ao índice. Cada linha tem três estados, e os nomes são do balcão:

| | |
|---|---|
| **Esperando conferência** | o extrator leu e propôs; ninguém olhou ainda |
| **Conferida e gravada na ficha** | alguém conferiu, e os campos entraram na matrícula |
| **Descartada** | alguém olhou e disse que não serve — com motivo escrito |

**A proposta não é a gravação.** O extrator escreve numa tabela própria
(`ri_onr_enderecos`), e a matrícula continua exatamente como estava. Quem grava é
`confirmar`, na tela da conferência, **na mesma transação da marca** — ato que não
entra deixa a proposta onde estava.

**E ele não sobrescreve o que já está lá.** Se alguém digitou o bairro na ficha
entre a proposta e a confirmação, quem digitou vale mais; o campo que ficou de fora
volta na resposta e a tela diz qual foi. É a regra do CNM — *o que se calcula pode
ser mostrado sem ser gravado* —, e ela existe porque a proposta é de uma máquina e o
que está na ficha é de uma pessoa.

**A decisão de quem conferiu não é refeita por uma segunda leitura.** Se a linha já
está decidida e alguém clica no botão outra vez, a tela avisa que a decisão vale
mais e **não grava nada**. Sem essa guarda, a leitura velha apareceria como se fosse
a leitura recém-pedida — o carimbo que mente na sua forma mais direta.

**Não se apaga linha da fila.** Descartar exige **motivo escrito** (a régua da
reabertura e da dispensa do usucapião), e o que se registrou fica: a pergunta
«por que não se aproveitou?» tem resposta meses depois.

---

## 4. O que o extrator achou de errado — e isto é a parte que mais vale

O módulo não lê só o endereço: ao ler 1.442 fichas de verdade, ele foi bater em
defeitos que já estavam de pé, em outros lugares.

**1. A ÁREA IA AO ÍNDICE NACIONAL DIZENDO 63 m² ONDE HAVIA 630.000.** A conversão
lia `area_valor` como número inteiro. Medido nas **1.387** matrículas com unidade
`ha`: **1.298** trazem o hectare inteiro e sem separador (`63`, `131`, `1`, `9`),
porque a coluna não guardou os ares e os centiares — e `_inteiro('63')` devolvia
**63**, dez mil vezes menos. Quem achou foi o ensaio contra a produção, depois de a
função estar escrita e comentada como certa.

> **O erro não foi da função: foi de ter medido três exemplos e concluído sobre
> 1.387.** Os três exemplos eram reais e todos tinham vírgula. É a forma mais
> convincente do carimbo que mente — e a correção passou a morar em
> `onr_api.area_em_metros`, **uma definição só na casa**, usada pelo extrator e pelo
> `montar_indicador`. As **18** fichas de 4 e 5 dígitos sem separador (`3808`,
> `1154`) devolvem `None`: ali não dá para saber se é hectares ou metros, e chutar
> erra por cem vezes. **A proposta as declara em vez de as inventar.**

**2. O PONTO DECIMAL DAS `m2`** — nas **11** matrículas com unidade `m2` e separador,
o ponto é decimal em todas (`9.7`, `31.47`, `0.1`). Lidas como milhar davam 9, 31 e
**0** — e zero num campo de área afirma que o imóvel não tem área.

**3. ELE LEU O ENDEREÇO DA PESSOA COMO SE FOSSE O DO IMÓVEL.** A ficha termina com
«Proprietário: JOSE DA SILVA, … residente e domiciliado na Av. Venerando F.
Borges», e é essa a última rua do texto. Duas fichas (**971** e **979**) tiveram o
endereço de quem vende posto na coluna do imóvel. Hoje há **duas âncoras**: o
endereço que vale é o que está dentro do bloco do imóvel, e o das pessoas é de
outro bloco. Há teste com as duas ruas no mesmo teor, exigindo que a da pessoa
**não** apareça na proposta.

**4. «Av.» NÃO EXISTE NO CATÁLOGO DO ONR.** O contrato tem `Avenida` (código 8) e
não tem a abreviatura — e a leitura literal de uma via abreviada fazia o tipo
**desaparecer** da proposta, com o nome indo inteiro para o campo errado. Medido:
**10 matrículas** da fila traziam `Av.` literal como logradouro. `_tipo_da_via`
canoniza contra o catálogo antes de partir o nome.

**5. O NOME DO IMÓVEL RURAL ERA CORTADO PELA QUEBRA DE LINHA DO OCR.** Medido nas
duas direções, e as duas metades se explicam:

| | |
|---|---|
| `FAZENDA\nTRES PORTEIRAS` (5131) | o `\n` **cortava o nome no meio**, e sobrava `FAZENDA` |
| `FAZENDA LEÔNCIO.\nLOCALIZAÇÃO :` (3399) | o `\n` **protegia o nome**, e o resto era rótulo |

**Vinte e três fichas dependem de qual das duas coisas o `\n` faz, e em vinte e uma
ele protege.** A saída não foi tirar a quebra: foi **trocar uma fronteira por
outra** — ler tudo como um parágrafo só (a quebra é do OCR, não do nome) e fechar o
valor onde a ficha escreve o rótulo seguinte (`LOCALIZAÇÃO :`, `ORIGEM :`,
`TÍTULO :`).

**6. O LUGAR VIRA BAIRRO, E O NOME SAI DO TEXTO.** O lugar da ficha rural — *Vila*,
*Povoado*, *Distrito*, *Loteamento*, *Centro* — não tem coluna própria na ficha e é
onde o morador diz que mora; ele entra como bairro, sempre lido do teor e **nunca
inventado**. Medido depois da mudança: **um** registro mudou de resultado, e o
bairro saiu correto — é o tamanho do que se mexeu, e é por isso que a mudança foi
segura.

**7. «RÓTULO TERMINA EM DOIS-PONTOS, O VALOR ESTÁ NA LINHA DE BAIXO».** Na matrícula
3975 o teor traz `DENOMINAÇÃO DO IMÓVEL RURAL:` e, na linha seguinte, `Fazenda Três
Porteiras; área total (ha): 46,0000`. Sem tratar isso, o nome do imóvel saía como
**«do imóvel rural:»** — o rótulo — e iria assim para o índice nacional.

---

## 5. O que o extrator hoje entrega — medido

Contra cópia da produção de 16/09/2026:

| | |
|---|---|
| fichas elegíveis (com teor e sem endereço) | **1.442** |
| **prontas para enviar** | **1.283** |
| com buraco (falta campo) | **112** |
| divergentes do que a ficha já diz | **82** |

Das 1.283 prontas, **1.129 são de confiança alta** e 154 média — a confiança é da
frase de onde o campo saiu, e vai à vista na tela.

**Os buracos, campo a campo** (o que trava o índice nacional):

| campo | quantas | por quê |
|---|---|---|
| **Bairro** | **93** | o teor não diz o lugar — a ficha urbana antiga escreve a rua e o número e mais nada |
| **Logradouro** | **26** | o teor nomeia o imóvel («Fazenda X») mas não uma via |
| **Urbano ou rural** | **2** | a coluna está vazia e o teor não diz |

**Os avisos que vão junto da proposta** — o extrator declara o que fez, e não só o
resultado. Medidos por categoria, na cópia de 16/09/2026 (20h05): **693 avisos**,
e a soma das linhas abaixo é exatamente o total.

| quantas | o que o extrator avisa |
|---|---|
| **346** | a área da **coluna** não bate com a da **ficha** — a da ficha é a que vai |
| **161** | o nome do imóvel saiu da **frase mais fraca** das quatro formas |
| **48** | a ficha diz um município que não é desta serventia (Imperatriz, Ribamar Fiquene, Amarante, Lageado Novo) |
| **42 + 40** | **o teor diz URBANO e a ficha está marcada como RURAL** (e o inverso) — a proposta **não sai pronta** |
| **30 + 9** | o tipo do imóvel vai como «Fazenda/Sítio/Chácara» ou «Terreno/fração» porque a ficha não o tem |
| **13** | o teor não diz o nome do imóvel — o único campo que o ONR **não** aceita vazio |
| **3** | a via não existe na ficha, e o nome vai como «Área» |
| **1** | a ficha mede em **alqueire** — o sistema não faz essa conta, e diz por quê |

**Os contadores da rodada** (`gerar`) são outros, e é por isso que eles não se
somam com os avisos: **1.442 lidas · 1.283 prontas · 112 com buraco · 82
divergentes · 13 sem nome · 42 sem a marca `IMÓVEL:`** — nesta última o bloco do
imóvel foi lido inteiro mesmo assim, e a tela diz.

> **AS DUAS RÉGUAS DE «DIVERGENTE», E ELAS NÃO SÃO A MESMA CONTA.** `gerar`
> devolve **82** divergentes (campo a campo, contra o que a ficha já diz), e a tela
> mostra **94** de confiança baixa — **89** por discordarem da ficha e **13** por
> não haver nome do imóvel, com sobreposição entre as duas causas. Quem comparar os
> dois números e concluir que um está errado vai consertar o que não quebrou: são
> perguntas diferentes («o teor discorda da coluna?» e «esta proposta pode ser
> enviada?»), e a segunda inclui a primeira.


> **NÚMERO DE FILA ENVELHECE, E ESTE AQUI ENVELHECEU EM UM DIA.** A primeira medição
> desta passada deu **1.443** e a de horas depois deu **1.442** — não por erro de
> conta: a cópia é tirada do banco vivo, e o banco vivo é o da serventia. Uma ficha
> ganhou endereço no meio do caminho. Por isso todo número deste documento vem com
> a data e com a origem (cópia da produção), e quem escrever aqui depois **mede de
> novo** — a medição custa segundos, e o número torto é o que faz planejar trabalho
> já feito.

---

## 6. A citação da proveniência — o que cada campo diz de onde veio

**A tela da conferência tem uma coluna chamada «de onde saiu»**, e ela é o que
separa *conferir a leitura* de *confiar na máquina*. Cada campo preenchido traz ali
uma frase dizendo de onde ele veio — e **o que ela cita é o que o livro escreve**,
entre `«»`, para quem confere ir procurar exatamente aquilo na ficha de papel.

Medido campo a campo na cópia de 16/09/2026:

| campo | a citação, e quantas são de cada forma |
|---|---|
| **Logradouro** | **1.416** citam o **trecho do teor** copiado como está (`denominada Fazenda "Leôncio", com área de 231,0233ha…`) · 26 sem citação (é o buraco) |
| **Número** | **1.310** são a **regra da casa** — imóvel rural não tem número predial, e vai `«0»` · **119** citam o teor (`n.º 137`, `nº198`) |
| **Bairro** | **1.201** são a regra do rural (`«Zona Rural»`) · **148** citam a frase do teor (`teor: «, Centro»`) |
| **Cidade** | **680** citam a frase (`teor: «município de Cidade Exemplo»`) · 675 são o padrão da casa · 87 já estavam na ficha |
| **UF** | **1.355** são o padrão da casa (`(MA) — o teor não escreve a UF`) · 87 já estavam na ficha |
| **CEP** | **1.370** são o padrão da casa (por cidade) · 72 já estavam na ficha |
| **Urbano ou rural** | **1.427** citam as **palavras que decidiram** (`teor: «gleba de terras», «fazenda», «hectare»`) · 13 vêm da coluna |
| **Área** | **1.086** citam a frase com a unidade **como o livro a escreve** (`teor: «231,0233 ha» = 2310233 m²`) · 349 vêm da coluna |
| **Unidade da área** | **1.059** dizem que a ficha escreve hectare e que vai convertida · **376** que a unidade é a da coluna |
| **Tipo do imóvel** | **39** explicam de onde saiu o palpite (a ficha não tem tipo) |

**Quatro campos não citavam o livro, e o conserto é de 16/09/2026** — os três
defeitos foram achados medindo a própria coluna, e não lendo o código:

| | antes | agora |
|---|---|---|
| **Cidade** (680) | `teor: Cidade Exemplo` — dizia de onde veio e **não mostrava o que o livro escreve** | `teor: «município de Cidade Exemplo»` — a mesma frase que o aviso da tela já usava |
| **Urbano ou rural** (1.427) | as palavras soltas, separadas por vírgula (`teor: gleba de terras, fazenda, hectare`) — lia-se como rótulo do sistema, não como palavra da ficha | `teor: «gleba de terras», «fazenda», «hectare»` |
| **UF** (1.442) | **nada**: a célula saía em branco | `padrão da serventia (MA) — o teor não escreve a UF`, ou `já estava na ficha` |
| **Unidade da área** (1.435) | **nada**: a célula saía em branco | `a ficha escreve «ha» → convertida para m², que é o que o ONR espera` |

> **CÉLULA VAZIA NUMA COLUNA QUE EXISTE PARA DIZER A ORIGEM SE LÊ COMO «NÃO SE
> SABE».** Não era o caso da UF e da unidade: as duas tinham origem certa e
> simples — o padrão da casa —, e o silêncio as fazia parecer desconhecidas. É o
> «carimbo que mente» ao contrário: o carimbo que **cala** e deixa quem lê tirar a
> conclusão errada sozinho.

**As cinco formas da citação, e o que cada uma quer dizer:**

| forma | o que significa |
|---|---|
| `teor: «…»` | a **frase do teor** que decidiu, copiada entre `«»` — quem confere procura isso na ficha |
| o trecho cru do teor | o **pedaço do livro** de onde o valor sai, copiado como está. Não é uma frase escolhida: é o trecho que contém o dado (é o caso do logradouro e do número) |
| `coluna: …` | o dado **já estava na coluna** da ficha |
| `já estava na ficha` | o extrator **não mexeu** — havia valor, e ele vale mais |
| `padrão da serventia` / regra da casa | **não vem do livro** — é decisão da casa, e está dito qual |

**A citação longa não se corta, e isso é deliberado.** Medido: das 1.535 citações
de logradouro e número, **814 têm até 40 caracteres**, 68 vão até 120 e **653
passam de 120** — são trechos de teor rural, que descrevem o imóvel numa frase só.
Cortar deixaria a citação bonita e a conferência pior: quem confere precisa do
trecho inteiro para achar a passagem na ficha.

---

## 7. O que ele NÃO faz

**Não grava na ficha.** Propõe, e a proposta fica ao lado do que já está lá, com a
frase de onde cada campo saiu. Escrever direto em 1.442 fichas com uma expressão
regular seria a máquina lavrando ato registral.

**Não publica no ONR.** Montar e enviar o indicador é outra tela e outro papel —
`/ri/onr` monta, a rota de envio sobe, e ela é do oficial.

**Não inventa.** O que não se achou fica em `faltam` e aparece na tela: campo vazio
que ninguém sabe que está vazio é o defeito que este módulo existe para acabar. E
onde o teor discorda da coluna, **a proposta não sai pronta** — vai para a
conferência com as duas versões.

**Não julga o que é de outra comarca.** As ~14 fichas que dizem «cidade de
Imperatriz» saem com o aviso; corrigi-las é decisão de quem lê, não da máquina.

**Não mexe em nada do acervo além do endereço.** Rodar o extrator de novo sobre as
1.442 não toca em proposta já confirmada (`WHERE situacao` no `guardar`), e a
opção de rodar **só as fichas do OCR novo** existe para o dia seguinte a uma
importação, quando o acervo já foi conferido. O padrão nasce olhando **tudo**, e
isso é decisão do oficial de 15/09/2026: *«Mandar tudo, inclusive o acervo»*.

---

## 8. Onde mora o código

| módulo | o que é |
|---|---|
| `onr_endereco_do_teor.py` | o extrator: limpeza do teor, o bloco do imóvel, a via, o número, o lugar, a área, o nome — e a proposta |
| `onr_endereco_schema.py` | `ri_onr_enderecos`: uma linha por matrícula (`UNIQUE(matricula_id)`), com `proposta`, `de_onde`, `faltam`, `avisos`, `antes` (o que a ficha tinha) e quem decidiu |
| `onr_endereco_web.py` | as telas: a fila, a conferência, confirmar e descartar, e o botão da ficha |
| `onr_api.area_em_metros` | a conversão de área — **uma definição só na casa** |
| `ri_onr_central.partir_logradouro` | a partição do logradouro contra o catálogo do ONR — a **mesma** régua que o indicador usa |
| `templates/onr_enderecos.html`, `onr_endereco.html` | a fila e a conferência (as duas versões lado a lado) |

Testes: `tests/test_onr_endereco_do_teor.py` (o extrator), `tests/test_onr_endereco_telas.py`
(a fila, a conferência, o botão da ficha) e — as duas portas novas — `tests/test_ri_onr_central.py`.

---

## 9. Como conferir, quando desconfiar

1. **O painel manda conferir os endereços?** Abra `/ri/onr` e procure, acima da
   lista, a frase *«Muita matrícula desta lista não sobe por falta de endereço»* e o
   botão **Conferir os endereços**, no mesmo parágrafo. Se a frase estiver lá e o
   botão não, a atualização não subiu.
2. **A ficha do indicador oferece o botão?** Abra uma matrícula **com teor e sem
   logradouro**. Se a ficha disser que o logradouro impede a publicação e **não**
   oferecer o botão *«o que o teor diz»*, é a mesma coisa.
3. **A conta bate?** Na fila, o alto diz quantas esperam conferência e quantas já
   podem ser enviadas. Se a conta não bater com o que o painel do ONR mostra como
   faltando publicar, **lembre-se de que são listas diferentes** — a fila soma o
   acervo, o painel não.
4. **A coluna «de onde saiu» está preenchida em toda linha?** Abra uma proposta e
   confira os dez campos da tabela: cada um com valor tem de trazer a sua frase.
   Célula vazia é o defeito que a medição de 16/09/2026 achou nos campos **UF** e
   **Unidade da área** — e, na **Cidade** e no **Urbano ou rural**, a frase tem de
   trazer o trecho entre `«»`, senão voltou a forma antiga (que dizia de onde veio
   sem mostrar o que o livro escreve).
