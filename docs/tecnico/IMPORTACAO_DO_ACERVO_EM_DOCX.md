# Importar acervo em Word — onde mora cada coisa

Duas importações diferentes, e elas não se misturam: as **matrículas** do
Registro de Imóveis e os **assentos** do Registro Civil. Este documento é
índice: **ele diz onde a escrita mora, e não repete o que já está escrito.**
Copiar o texto para cá faria duas versões do mesmo assunto, e elas divergiriam
no primeiro conserto — é a regra que o catálogo de modelos desta casa já
segue.

---

## Matrículas do RI, digitadas em Word

**É módulo do sistema, com botão** — menu *Matrículas em Word*.

| onde | o que está escrito lá |
|---|---|
| `ri_doc_extrair.py` | lê a pasta e produz `matriculas_doc.jsonl` |
| `ri_doc.py` | compara com o acervo e classifica cada caso — `NOVA`, `SO_NO_DOC`, `AMBIGUA`, `AMPLIADA`, `IGUAL`, `DIVERGENTE`, `VAZIA` |
| `ri_web.py` | a tela |
| `docs/tecnico/MATRICULAS_EM_WORD.md` | os números conferidos, como rodar, e o que o sistema decide sozinho — e o que ele **não** decide |

---

## Assentos do RCPN, em certidões e termos `.docx`

**São ferramentas de desenvolvimento**, em `tools/`, e **não viajam no
`.cgu`** — como o `gerar_logradouros.py`. O que o balcão usa é o
`importar_padrao`, que já existe e já tem tela; as ferramentas só produzem o
arquivo que ele lê. Um leitor de `.docx` dentro do sistema seria peça que
ninguém chama.

```
.docx → extrair_rcpn_docx → conferir_para_a_crc → gerar_arquivo_de_importacao
      → o botão «importar» do sistema
```

| onde | o que está escrito lá |
|---|---|
| `tools/esteira_rcpn_docx.py` | **o orquestrador, e o como rodar.** Encadeia os três passos e termina provando o resultado contra o conferidor do próprio sistema |
| `tools/extrair_rcpn_docx.py` | a medição dos `.docx`, os três destinos do teor, as duas fontes do lugar no livro, e as duas coisas que ele se recusa a adivinhar |
| `tools/conferir_para_a_crc.py` | por que a régua da Central roda na **entrada**, a diferença entre `o_que_falta` (retém) e `o_que_arrumar` (vai), e a deduplicação por matrícula |
| `tools/gerar_arquivo_de_importacao.py` | as pessoas indo **dentro** do registro, a quarentena, e o que fica de fora porque o próprio documento desmente |

Nenhuma delas grava. Quem grava é o botão, e lá continuam sendo **dois**:
conferir e importar.

---

## O estado, em 12/09/2026

A esteira rodou **cinco vezes sobre o acervo inteiro** no mesmo dia, e o que
mudou entre elas foi a leitura — não o acervo:

| | assentos | pessoas | **em quarentena** | de fora | recusados pelo sistema |
|---|---|---|---|---|---|
| 1ª passada | 2.545 | | **1.838** | 129 | 0 |
| 2ª — o separador do município | 2.545 | | **1.107** | | 0 |
| 3ª — a prosa do termo + o IBGE | 2.554 | 12.439 | **287** | 120 | 0 |
| 4ª — a caixa alta e o irmão que completa | 2.574 | 14.021 | **247** | 100 | 0 |
| 5ª — os tracinhos e o «X E Y» | **2.574** | **14.058** | **247** | **100** | **0** |

Os 3.666 documentos aproveitados são os mesmos nas cinco.

**A quarentena não é marca: é derivada.** Ela é o que a régua da Central
(`crc_carga.o_que_falta`) retém — o registro entra no livro e **não sobe** até
ser completado. Das 1.838 primeiras, 1.551 saíram por consertos de leitura, e
**nenhum deles inventou dado**:

* **o travessão no lugar do hífen** (731 assentos). `IMPERATRIZ – MA` e
  `IMPERATRIZ - MA` fazem o mesmo papel no papel, e a busca do município só
  conhecia o hífen. **E a hipótese que eu tinha era outra**: achei que era o
  `//` de `IMPERATRIZ//MA`; medido, era **1 caso**;
* **a prosa do termo.** O termo antigo não tem célula: ele escreve tudo numa
  frase só. O sexo, o município e o nome do registrado saem de âncoras
  **medidas em 812 documentos** — `do sexo MASCULINO|FEMININO`, e o
  `Cidade-UF` que vem **imediatamente antes** dela;
* **o endereço grudado no nome da cidade**, provado contra os 5.570 municípios
  do IBGE. «Centro De Imperatriz» resolve em «Imperatriz»; **«Amarante Do
  Maranhão» não vira «Maranhão»**, que é o que a regra óbvia — cortar no
  último «de» — faria.

> **A âncora do «do sexo» existe porque o termo descreve DUAS pessoas.** Ele
> diz «natural de X» do registrado **e** do declarante, e quem pegar o
> primeiro «natural de» da frase grava, em boa parte dos casos, a
> naturalidade de quem foi ao balcão. **Dado errado debaixo do rótulo certo é
> o pior lugar para um erro num assento.**

> **E a medição me impediu de cometer o engano maior.** Eu ia acrescentar
> «LOCAL DE NASCIMENTO» à busca do município — é o rótulo mais comum da
> quarentena, 202 de 250. Medido, ali vai a **casa ou o hospital**, e a
> primeira célula daquele bloco é o município **de registro**.

O que sobra:

* **nada foi gravado na produção** — nenhum destes assentos entrou no banco do
  servidor, e a esteira abre o banco em `mode=ro`. Importar pelo botão do
  sistema continua sendo decisão do oficial;
* os **287 em quarentena** e os **120 que ficaram de fora** estão nos arquivos
  `_em_quarentena.json` e `_ficaram_de_fora.json`, cada um com o motivo
  escrito e o nome do `.docx` — quem for à estante sabe a quais ir;
* **21 entraram com a data do nascimento no lugar da do registro**, porque a
  do registro não se leu no papel. Estão em `_conferir_a_data_no_livro.json`,
  e pedem o livro;
* o acervo local hidratado do Registro Civil está em
  `.../CARTÓRIO EXEMPLO Dropbox/.../CARTORIO/PESSOAS NATURAIS`, com 7.300
  `.docx` — 2.156 em `LIVRO A- NASCIMENTOS` e 1.820 em `CERTIDÕES`. **Hidrate
  antes de medir**: na pasta sincronizada da nuvem cada leitura força um download, e a
  passada não termina;
* **o óbito e o casamento entraram no mesmo dia** — ver as seções no fim
  deste documento.

---

## Dois defeitos que a quarentena fez aparecer — 12/09/2026

A quarentena de 287 foi medida um a um, e ler os documentos que ela retinha
achou **dois defeitos da leitura, e nenhum deles estava na lista de faltas**.

### 1. «MA e ROSANA» — a mãe entrando com sujeira na frente do nome

**735 das 2.554 mães (29 %) iam para o assento com «e » ou «UF e » colado no
começo do nome.** O termo escreve

> «FILIAÇÃO: PESSOA EXEMPLO, brasileiro, (...) residente na Rua São
> Francisco nº 31, Vila João Alberto – Cidade Exemplo**-MA e PESSOA EXEMPLO**, brasileira, lavradeira, (...)»

e o padrão que separa as pessoas — `NOME em caixa alta, qualificação` —
**levava `re.I`**. Com ele `[A-ZÀ-Ü]` casa minúscula também: o `e` minúsculo
passou a caber dentro do nome, e a leitura começou no `MA` da cidade.

**O `re.I` apagava exatamente a caixa alta que o padrão existe para exigir** —
e o comentário em cima dele já dizia «o nome em CAIXA ALTA». A qualificação
continua indiferente à caixa, cercada por `(?i:…)`; o nome, não.

Medido nos 2.135 documentos da pasta do Livro A, os dois padrões lado a lado:
**1.497 mudam**, e em todos o que sai é o «e » de fora do nome. **18 perdem um
genitor** — e nos 18 o que se perde já estava errado («PESSOA EXEMPLO brasileiro», com a qualificação dentro do nome, porque o papel não pôs
a vírgula). **Campo vazio não afirma nada; nome com «brasileiro» colado
afirma** — e a falta passa a aparecer na quarentena, com o nome do documento.

> **Este não foi achado lendo o código: foi achado contando o arquivo que sai.**
> A conferência da CRC não tem como reclamar — o nome está preenchido, e a
> Central aceita qualquer texto ali.

### 2. O mesmo ato em dois papéis, e o mais forte jogando fora o que tinha

`juntar_o_mesmo_ato` prometia, no próprio docstring, «com o que cada fonte tem
de melhor» — e escolhia **o DOCUMENTO INTEIRO**, pela força do tipo. Medido:
`PESSOA EXEMPLO` está no acervo duas vezes, e o **inteiro teor**
(mais forte) não traz a naturalidade que a **certidão em resumo** traz. O
assento ficava retido por falta de um dado que o acervo tinha.

Agora a força do tipo escolhe o **documento base**, e o irmão **completa campo
a campo o que está vazio nele** — cada campo dizendo de onde veio. O que os
dois têm e discordam continua decidido pelo tipo, **e vira aviso**, como já era
com o nome. **O teor não se completa**: ele é do documento, e «resumo entra sem
teor» é decisão do oficial.

### E as duas réguas de «qual documento é este ato» viraram uma

`gerar_arquivo_de_importacao.montar` recebia a extração **crua** e reindexava
por matrícula com um dicionário — onde **o último da lista ganha** —, enquanto
a régua da CRC tinha conferido **o mais forte**. Duas réguas para a mesma
pergunta: o arquivo podia sair de um papel e a conferência ter falado de outro.
Hoje ele recebe os atos já juntados, e **recusa** dois documentos com a mesma
matrícula em vez de escolher calado.

### 3. Os tracinhos do papel entrando no nome

O termo completa o resto da linha com traços, e eles vinham junto: **23
assentos** com nomes como `---------------------PESSOA EXEMPLO------`.
`_limpar_nome` passou a apará-los **só nas pontas** — no meio o hífen fica,
porque há nome hifenizado (`PESSOA EXEMPLO`).

### 4. «X E Y» num campo só — e a fronteira é medida

Em **31 assentos** — medidos na passada inteira; eram 16 na amostra em que a
fronteira foi levantada — o campo do pai levava **os dois genitores** e o da
mãe ficava vazio. O que separa o « E » conjunção do « E » sobrenome foi medido nos
nomes do arquivo gerado:

| palavras depois do « E » | o que é | quantos |
|---|---|---|
| **1** | sobrenome — `PESSOA EXEMPLO` | 11 de 11 |
| **2** | sobrenome — `SOUSA E SILVA LIMA` | 3 de 3 |
| **3 ou mais** | **duas pessoas** — `PESSOA EXEMPLO E PESSOA EXEMPLO` | 16 de 16 |

**E os avós corroboram**: `AVO_PATERNO/PATERNA` casam com o primeiro e
`AVO_MATERNO/MATERNA` com o segundo, que é o segundo sinal de
`decidir_quem_e_pai`. **A separação vira dúvida** e vai escrita em
`_a_conferir.json`, com o nome do documento — trinta nomes são poucos para
fazer lei, e quem confere é quem tem o livro. São **31**, e o irmão que
completa outro documento deixou nota em **748**.

---

## O que a quarentena ainda retém — 247, medidos

| | |
|---|---|
| o município de nascimento **não está na ficha** | **209** |
| a **data do registro** não foi lida | **133** |
| o ano da matrícula não bate com o ano do registro | 22 |
| o município **está na ficha** e a grafia não está no cadastro do IBGE | **15** |
| o sexo do registrado | 5 |

(um assento pode faltar em mais de uma coisa)

**As 15 grafias são onze, e oito delas diferem do IBGE por uma letra**:
`Governador Edson Lobão` contra **Edison** Lobão, `Senador La Roque` contra
La Ro**cq**ue, `Lageado Novo` contra La**j**eado Novo, `Governador Acher`
contra Ar**ch**er, `Loureto` contra Loreto, `Imperatiz` contra Imperat**r**iz.
**Nenhuma foi corrigida**: trocar letra em nome de município por parecença é
adivinhar — e `São João` (que tem cinco municípios no Maranhão e o papel diz
`/PI`) e `Araguaia/PA` (que não é município: o papel diz «HOSPITAL DE SÃO
GERALDO, ARAGUAIA/PA») mostram por quê. Elas ficam na quarentena, com o nome
do documento, para quem tem o livro decidir.

**E o que sobra não se conserta lendo melhor**: 209 documentos simplesmente
não escrevem a naturalidade, e 133 não escrevem a data do registro. Isso é
pergunta ao livro de papel, não à ferramenta.

---

## O ÓBITO ENTROU — 12/09/2026

A leitura era só a do nascimento; o oficial mandou seguir, e o óbito é a
segunda espécie. **A porta se abre uma de cada vez, e ela DECLARA quais lê** —
`extrair_rcpn_docx.ESPECIES_QUE_ESTA_FERRAMENTA_LE`. Entrar com os campos do
nascimento num assento de óbito poria o dado errado debaixo do rótulo certo.

| a passada inteira | assentos | em quarentena | recusados pelo sistema |
|---|---|---|---|
| nascimento | 2.575 | | 0 |
| **óbito** | **309** | | **0** |
| **total** | **2.884** | **308** | **0** |

O que o óbito traz, medido nos 309:

| | |
|---|---|
| nome do falecido | **100 %** |
| data do falecimento · causa da morte · sepultamento | **99,7 %** |
| hora | 89,3 % |
| «deixou bens?» | 88,0 % |
| cor / raça | 83,5 % |
| **data do REGISTRO** | **98,7 %** — ver a decisão do oficial abaixo |

### A data do registro do óbito — decisão do oficial em 13/09/2026

> «o óbito, salvo se por decisão judicial, precisa ser feito no prazo de 24
> horas. Vamos colocar o registro do óbito, por padrão, no dia do óbito quando
> não tivermos data»

**A certidão de óbito em resumo não traz a data do registro** — o que está no
rodapé é a data em que ela foi expedida, que é outra coisa. O termo do Livro C
traz, na abertura. Com a decisão dele:

| | antes | depois |
|---|---|---|
| óbitos com data do registro | 27 de 309 | **305 de 309** |
| a quarentena inteira | 529 | **308** |

**A REGRA E A DECISÃO MORAM NA MESMA FUNÇÃO.** É a mesma de 12/09 para o
nascimento, agora com a espécie dita — escrever a segunda ao lado daria duas
versões da decisão dele. E **cada assento derivado leva a marca em
`dados_json`**, com as palavras da decisão e a data: quem abrir daqui a cinco
anos precisa saber que aquela data **não foi transcrita do livro**.

**E A FRASE DELE TEM UMA EXCEÇÃO DENTRO, que virou código.** A regra se apoia
no prazo de 24 horas — «salvo se por decisão judicial». **Onde o próprio papel
diz que o registro foi tardio, a premissa não vale**: `1.851 PESSOA EXEMPLO` morreu em 07/05/2022 e foi registrado em 08/12/2023, «após o prazo
legal pelo Processo nº 0800896-73.2022.8.10.0102» — **um ano e meio**. Derivar
ali poria no assento uma data que o documento desmente.

Medido nos 388 óbitos que entram: **12 declaram o atraso**, e **10 já trazem a
data do registro** (nem chegariam à derivação). **Três** são recusados pela
exceção, com a frase do papel escrita ao lado — `PESSOA EXEMPLO`,
`PESSOA EXEMPLO` e `PESSOA EXEMPLO`.

**«Processo nº» sozinho não entra na régua.** Ele aparece nos 12 e é sinal
fraco — número de processo cabe em qualquer averbação. O que decide é a frase
que diz o atraso: «após o prazo legal», «registro tardio», «fora do prazo»,
«ordem judicial». Os dois casos medidos a trazem: «Ordem Judicial, processo nº
27-56.2016.8.10.0102» e «POR ORDEM JUDICIAL SOB processo nº 535-70.2014…».

> **E o artigo da lei não está citado aqui de propósito.** O prazo de 24 horas
> é o que o oficial enunciou, e é dele que a regra vive; **o que não se leu,
> não se afirma** — o número do artigo fica para quem tem a lei na frente.


### A naturalidade do falecido — checagem estendida em 13/09/2026

O óbito não tinha checagem de município nenhuma em `crc_carga`, ao contrário
do nascimento. Pedido do oficial: estender a mesma checagem.

**A régua não é a mesma do nascimento — é `o_que_arrumar` (avisa), e não
`o_que_falta` (retém).** O manual não põe naturalidade entre os obrigatórios
do óbito (`FLAGDESCONHECIDO`, `NOMEFALECIDO`, `MATRICULA`, `DATAREGISTRO`,
`SEXO`, `CORPELE`) — a diferença para o nascimento é que ali a Central
**recusou de verdade** quando ela faltava (relato de 11/09/2026), e para o
óbito não há relato assim. **Bloquear seria mais severo que a norma.** Se a
Central um dia recusar por falta dela, a checagem sobe para `o_que_falta`,
como `POSSUIBENS` subiu em 11/09.

Medido no acervo local, nos 309 óbitos: **8 sem naturalidade na ficha** e **4
com a naturalidade lida e a grafia fora do cadastro do IBGE** — `Franco/MA`,
`Tome Açu/PA`, `Almerim/PA`, `São Francisco Ma/MA`.

### Quatro coisas que a construção do óbito achou

**1. O título se lê NO ALTO DO PAPEL — e lê-lo no documento inteiro custava
243 óbitos.** A certidão de óbito CITA as outras certidões da pessoa:
«CERTIDÃO CASAMENTO COM AVERBAÇÃO DIVORCIO LV. B-02» e «certidão de nascimento
foi lavrada nesta Serventia». Com a busca no texto todo, **176 óbitos se
diziam de casamento e 67 de nascimento**, e a conferência das duas fontes da
espécie os recusava por uma citação. **Título é o que está escrito em cima.**

**2. O nome do falecido tem TRÊS moradas, e a régua é sempre o rótulo que o
papel imprime** — nunca «o primeiro que parece nome». Medido: `CERTIDÃO DE
ÓBITO / NOME: / PESSOA EXEMPLO`; `PESSOA EXEMPLO / MATRÍCULA: / …`;
e a terceira, em que o nome está no texto e a tabela começa em `MATRÍCULA:`.
Com uma só, 110 dos 159 óbitos da primeira amostra ficavam sem nome — **fora
até da quarentena, porque o banco o exige**. E a régua não pode ser «parece
nome»: `_e_nome_de_pessoa('CERTIDÃO DE ÓBITO')` responde **True**, e o falecido
entraria chamado «Certidão de Óbito».

**3. A hora saía do texto inteiro, e a primeira hora do papel é a do selo.**
`PESSOA EXEMPLO` saía com **14:40** e o documento diz «ás dezessete horas e vinte
minutos (17:20hrs)». Agora ela sai do bloco que a rotula, nas duas espécies —
**e o fecho da régua deixou de ser `\b`**: entre o `0` e o `h` de «(17:20hrs)»
não há fronteira de palavra, e a hora não era lida.

**4. «Deixa bens?» é frase, e não campo.** A CRC retém o óbito sem S ou N, e
sem opção de ignorado. Medido nos 528 documentos: **330 dizem que não, 151 que
sim, 40 não falam** e 7 falam sem responder. A negativa se pergunta primeiro
(a mesma frase traz as duas metades — «deixa bens a inventariar, e não deixa
testamento conhecido»), o verbo tem de vir colado em «bens» («era casado sob o
regime da comunhão de bens» não responde nada), **e a frase lida vai escrita na
dúvida**: isto decide se há inventário.

### O que ainda não se lê

**Casamento — 772 documentos**, mais 42 de casamento religioso. O papel traz o
que a Central pede (filiação em 99,5 %, regime de bens em 99,1 %, os dois
nubentes em 99 %), e são quatro filiações, o regime e o nome que cada cônjuge
passou a usar. Proclamas (4) e Livro E (5) continuam recusados, dizendo por quê.

## O CASAMENTO ENTROU — 13/09/2026

Ordem do oficial («siga»), depois do óbito. É a maior das três espécies: **881
documentos distintos**. Passada completa (nascimento + óbito + casamento):
**3.399 assentos, zero recusados pelo conferidor do próprio sistema.**

| espécie | assentos |
|---|---|
| nascimento | 2.575 |
| óbito | 309 |
| **casamento** | **515** |

### O papel tem TRÊS moldes, e um deles ainda não se lê

| a forma da filiação | quantos documentos |
|---|---|
| dois parágrafos, um por nubente | — |
| um parágrafo com `;` («N1 e N2, ELE...; ELA...» ou sem cabeçalho) | a maioria |
| **o termo do Livro B** (`O CÔNJUGE:`/`A CÔNJUGE:`, sem tabela) | **~126 recusados** |

**O termo do Livro B fica recusado, de propósito.** Ele não tem a célula
rotulada da filiação que a certidão em resumo tem — é prosa corrida, do
início ao fim do documento. Construí uma primeira versão que lia os dois
nubentes no **documento inteiro**, e ela tinha um defeito grave: **no termo,
os GENITORES também têm «nascido em ...»** — «filho de PESSOA EXEMPLO
ALVES, **nascido em** dezenove de março de 1946 (...) e de dona PESSOA EXEMPLO, **nascida em** 1954». Uma âncora que caça «nome, nascid[oa]»
em texto corrido pega o PAI como se fosse o segundo cônjuge — nome trocado
por papel errado, o pior lugar para um erro num assento.

**A saída é a mesma do nascimento: ler dentro do bloco rotulado.**
`bloco_com_rotulo(blocos, "FILIACAO")` já existe e separa o que é filiação do
que não é; o termo do Livro B não tem essa célula (é prosa sem tabela), e por
isso fica recusado — «melhor deixar de achar do que achar errado».

### Quatro consertos, medidos contra o acervo real

1. **A aspa curva das KRIKATI (`’`, U+2019) não estava no alfabeto de nomes.**
   `PESSOA EXEMPLO` perdia a filiação inteira porque o caractere
   parava a leitura no meio do nome. A mesma aspa já estava tratada em
   `NOME_QUALIFICADO`, do nascimento — só não tinha chegado ao casamento.
2. **A vírgula antes de `ELE`/`ELA` não é sempre escrita.** «...NOGUEIRA ELE
   nascido...» (sem vírgula) fazia o cabeçalho «N1 e N2» não ser reconhecido,
   e o nome de N2 saía como a palavra **«ELA»**.
3. **«ELE»/«ELA» não é nome — é rótulo do outro cônjuge quando o documento não
   repete o nome dele.** `PESSOA EXEMPLO, ELE nascido...; ELA
   nascida...` nunca diz o nome dela em lugar nenhum. A leitura agora recusa
   esse nome (fica vazio, com dúvida) em vez de gravar «ELA» como pessoa.
4. **«Filho ANTONIO...» sem o «de» é erro de digitação no próprio papel** —
   `PESSOA EXEMPLO` — e a filiação fica de fora, com dúvida, em vez de
   ser adivinhada.

### O regime de bens tem uma forma que a Central não reconhece

**«COMUNHÃO DE BENS», sem qualificação, não está no vocabulário da CRC**
(`crc_carga.REGIME_CASAMENTO` só tem «parcial», «universal», «separação total/
legal», «participação final» — nenhum bare «comunhão de bens»). Medido:
`PESSOA EXEMPLO`, casamento de 1979, escreve só isso. O Código Civil
de 1916 fazia da comunhão universal o regime supletivo — **mas isto não se
afirma aqui**: escrever «universal» por dedução seria inventar o que o papel
não escreveu. O texto sobe como o papel escreveu, e o `o_que_arrumar` (que já
existe) avisa que não bate com o vocabulário da Central.

### O que ainda falta

- **A data do registro não se deriva** — ao contrário do nascimento e do
  óbito, não há decisão do oficial sobre o que fazer quando o livro não a
  traz. A falta fica escrita, e ele decide quando quiser;
- **Proclamas e Livro E** continuam recusados, como já estavam.

## O CASAMENTO RELIGIOSO ENTROU — 13/09/2026

Pendência da seção anterior, e o número que ela escrevia estava errado: não
são 42 documentos, são **134** — o que ela media não tinha sido medido, só
suposto por semelhança com outra estimativa. Medido de verdade contra o
acervo (`rc_matricula.confere`, com o dígito verificador conferido): das 134
matrículas válidas com `livro_tipo == "3"`, **29 assentos entraram**, **7
ficaram de fora com motivo** (o mesmo motivo de sempre — o termo do Livro B
sem célula de filiação, e duas matrículas com o ano trocado) e o resto são
duplicatas do mesmo ato (2ª via, resumo e inteiro teor do mesmo casamento) —
a mesma proporção de repetição já medida no acervo inteiro.

**É O MESMO PAPEL, E A LEITURA É A MESMA — só o que muda é para onde vai.**
Uma certidão de casamento religioso com efeitos civis (CC, art. 1.516) não
tem nenhuma palavra que a distinga de uma certidão de casamento civil comum:
o título diz `CERTIDÃO DE CASAMENTO DE:` nos dois casos, a prosa da filiação
é idêntica, o "ELE nascido em..., ELA nascida em..." é o mesmo molde. **Quem
separa os dois é só a matrícula** — o dígito do tipo de livro, que aponta
para o Livro B-Auxiliar em vez do B — e por isso a leitura reaproveita
`casamento_do_documento()` inteira, sem nenhum código novo além de abrir a
porta.

**A porta já estava meio aberta, e eu quase não vi.** `rc_matricula.
TIPOS_DE_LIVRO`, `rc_assento.SERIE_DA_ESPECIE` e `rc_assento.
PAPEIS_DA_ESPECIE` já tinham `CASAMENTO_RELIGIOSO` mapeado — provavelmente
para o domínio de lavratura nova, não para esta ferramenta. Faltavam três
linhas em `extrair_rcpn_docx.py`: a espécie entrar em
`ESPECIES_QUE_ESTA_FERRAMENTA_LE`, o cruzamento com o título parar de
recusar (o título nunca diz «religioso»; comparar ao pé da letra recusaria
os 134 inteiros), e o `if especie == "CASAMENTO":` virar
`if especie in rc_assento.ESPECIES_DE_CASAMENTO:` — a mesma constante que o
domínio já usa, e não uma lista nova que divergiria dela no primeiro
conserto.

**Passada completa depois da extensão: 3.428 assentos, zero recusados pelo
conferidor do próprio sistema.**

| espécie | assentos |
|---|---|
| nascimento | 2.575 |
| casamento | 515 |
| óbito | 309 |
| **casamento religioso** | **29** |

## A DATA DERIVADA GANHOU O BOTÃO QUE JÁ EXISTIA — 13/09/2026

Pergunta do oficial: *«os novos assentos incluídos pelas importações possuem
um botão para dizer que ele precisam ou já foram conferidos?»* A resposta
medida foi **não** — e por um motivo específico, que ficava escondido.

**Havia DUAS marcas para o mesmo aviso, e só uma tinha botão.** Quando a data
do registro é derivada da data do fato (porque o livro não a traz — decisão
do oficial de 12/09 para o nascimento e de 13/09 para o óbito), esta
ferramenta já gravava a explicação em `dados_json` desde que o óbito entrou.
Mas `dados_json`, aqui, só é **lido** por `conferir_para_a_crc` e
`gerar_arquivo_de_importacao` — para tolerar o descompasso entre o ano da
matrícula e o ano do fato. **A ficha do assento nunca abre esse campo**, e o
botão «Confirmei no livro de papel» — que já existe, construído em
26/08/2026 para os três casamentos duvidosos do E-Ofício — não sabia deste
caso. A marca ficava muda no banco.

**A correção não foi inventar um segundo mecanismo: foi preencher o
primeiro.** `rc_assentos.livro_a_confirmar` já tem a coluna, o aviso na
ficha e o botão que zera a marca quando alguém vai ao livro conferir —
tudo pronto, e usado por três assentos. `_data_do_registro_que_o_livro_nao_tem`
passou a gravar o mesmo texto ali também, e ele entra pelo caminho comum:
`livro_a_confirmar` não é campo «da máquina» (`importar_padrao.DA_MAQUINA`),
então o formulário/arquivo de importação já o aceita — não foi preciso
mexer em `atribuicoes_web.py` nem na ficha, que são de outra frente
trabalhando nesta mesma árvore.

**Medido contra o acervo inteiro depois da mudança: 351 dos 3.428 assentos
saem com `livro_a_confirmar` preenchido** — e a passada continua em **zero
recusados**. `dados_json` continua tendo a marca, para a tolerância da CRC;
`livro_a_confirmar` é a mesma informação, no lugar que o balcão já enxerga.

## A PASTA "CERTIDÕES E TERMOS REUNIDOS" — 13/09/2026

O oficial organizou um acervo próprio, maior e mais limpo que o do Dropbox:
**10.858 documentos do RCPN** (nascimento, casamento, óbito), já separados
por espécie e por tipo (resumo / inteiro teor / termo). A esteira rodou
contra ela pela primeira vez em 13/09/2026, e depois pediu: *«certificar
que a importação não vai gerar erros no arquivo xml e no json. Simular os
erros e resolver antes da importação»*.

### O ensaio: importar de verdade numa cópia, e gerar o XML em cima

Nasceu daí o roteiro que passou a valer para qualquer lote grande: copiar
`cartorio_gestao.sqlite3` para um arquivo descartável, rodar
`importar_padrao.importar()` de verdade nessa cópia (não é só `conferir`),
e então `crc_carga.montar()` sobre os assentos recém-entrados — o mesmo
passo que só apareceria depois, na hora de gerar a carga pela tela. O XML
que sai é reaberto com o parser, para provar que está bem formado, e — a
parte que faltava nos ensaios anteriores — **validado contra o XSD**
(`schemas/cargaRegistrosCompleto.xsd`), que é o que efetivamente pegou o
primeiro bug real.

**`tests/test_crc_carga_campos_da_producao.py`** nasceu do mesmo pedido, na
forma de teste permanente: audita o que já está gravado nesta máquina
(pula se o banco de produção não existir) e vai além do XSD — nenhuma tag
com `None`/`null`/lixo de programação, nenhum caractere de encoding
quebrado, campos obrigatórios do manual nunca vazios, datas no formato
certo, CNS com 6 dígitos, matrícula com 32, regime de casamento nunca vazio.

### O bug que o XSD achou, e que a string bem-formada escondia

**A causa da morte estourava o limite de 170 caracteres do XSD** em 17
óbitos do lote real (o maior tinha 375) — `CAUSAMORTEANTECEDENTES_A`
recebia a prosa inteira, sem quebra. Corrigido reaproveitando as quatro
linhas que o próprio manual reserva para a cadeia de causas
(`_causa_morte_em_quatro_linhas`, em `crc_carga.py`): a prosa se reparte
sem cortar palavra ao meio, e só avisa (não bloqueia) se nem as quatro
linhas juntas (680 caracteres) bastarem.

### Quatro decisões do oficial, tomadas em sequência

1. **Pai ausente não é irregularidade** — "é comum. Mãe todos devem ter."
   `o_que_arrumar` parou de avisar sobre a falta do pai; a falta da mãe
   continua avisando.
2. **"Comunhão de bens" sem qualificação vira parcial a partir de 1977**
   (Lei do Divórcio, Lei 6.515/1977) — `_regime_resolvido()`, em
   `crc_carga.py`. Antes de 1977 continua sem se afirmar.
3. **Município de nascimento ausente ou não reconhecido pelo IBGE vira
   Cidade Exemplo/MA**, só neste lote (734 registrados) — não é regra
   permanente da leitura nem de `crc_carga.py`.
4. **Bens do falecido sem resposta viram "N"**, e **matrículas cujo ano não
   bate com o ano do registro são recompostas** com o ano certo
   (`rc_matricula.compor`, dígito recalculado) — aplicado a este lote via
   script, não como regra permanente.

### O bug maior: 568 nascimentos sem NENHUMA data

Achado ao aplicar a decisão nº 4: 568 nascimentos (de 6.755) não tinham
nem data de registro nem data de nascimento — nenhuma das duas. **Um** era
matrícula com o dígito de tipo de livro errado (um casamento digitado como
se fosse nascimento — erro no próprio papel antigo, sem relação com esta
ferramenta). **Os outros 568** tinham, na maioria (429+ medidos, 536
confirmados depois de tudo pronto), a data escrita na forma «declarou que
no dia sete de dezembro de mil novecentos e noventa (07/12/1990) (...)
**nasceu** FULANO» — diferente do padrão «nascid[oa] aos...» que a leitura
já reconhecia.

**A correção não confia na leitura sozinha.** `extrair_rcpn_docx.py` passou
a procurar a data entre parênteses mais próxima da palavra "nasceu" na
mesma frase (sem ponto entre as duas) — o mesmo documento às vezes cita
outra data adiante, como uma anotação de casamento posterior, e pegar a
errada seria pior que não achar nenhuma. Toda data lida assim fica marcada
(`MARCA_DATA_FATO_POR_PROXIMIDADE`), e uma nova função em
`conferir_para_a_crc.py` — `conferir_datas_por_proximidade` — só a aceita
se bater com os registros vizinhos do livro (o termo antes e depois, com
folga de dois anos para o caso comum de registro tardio); se não bater, a
data é descartada e o registro volta a ficar sem data, como se nunca
tivesse sido lida.

**E para os que mesmo assim continuam sem nenhuma data**, decisão do
oficial: *«o cartório vai olhar no livro e vai ter que inventar uma data.
Utilize a data de registro do registro seguinte ou anterior (se sabido)
(...) desde que não seja antes da data do ocorrido»*.
`preencher_data_pelo_vizinho()` estima a partir do termo vizinho mais
próximo (o que servir, respeitando o limite da data do fato quando ela é
conhecida — o caso dos registros tardios), e marca a estimativa em
`livro_a_confirmar` — a mesma coluna e o mesmo botão "Confirmei no livro de
papel" já usados para os outros avisos.

### O efeito, do início ao fim da tarde

| | retidos pela CRC | no XML |
|---|---|---|
| lote inicial (antes de qualquer correção) | 907 | 5.848 |
| **depois de tudo** | **22** | **6.735** |

### Duas colisões de matrícula, e a regra que as resolveu

Corrigir o ano da matrícula revelou 4 pares que colidiam na mesma chave —
pessoas que a extração original não tinha juntado porque cada cópia trazia
um ano (errado) diferente. **Duas eram duplicata exata** (mesmo nome, mesma
data — mantida uma cópia). **Duas divergiam de verdade**
(PESSOA EXEMPLO e PESSOA EXEMPLO, com datas de
registro diferentes entre as duas cópias de cada uma). Decisão do oficial:
*«vale a certidão mais nova»* — resolvido lendo a data de emissão no rodapé
de cada documento-fonte e ficando com a mais recente.

### O que ainda falta, depois de tudo isso

- **22 assentos retidos**: 19 por falta de sexo, 1 pelo nome do segundo
  cônjuge (termo do Livro B sem tabela), 1 pela cor "INDÍGENA" (fora do
  vocabulário da CRC — espera decisão), 1 genuinamente sem nenhuma data
  (nem no documento, nem nos vizinhos do livro);
- **228 assentos com aviso de filiação (mãe) e 196 com aviso de regime de
  bens** — entram, mas pedem revisão;
- a pasta «OUTRAS CERTIDÕES (IMÓVEIS, PJ, ETC.)» tem ao menos um documento
  do RCPN arquivado por engano ali dentro (achado ao investigar a colisão
  da Daniela) — vale conferir se há mais;
- **um detalhe técnico que custou tempo hoje**: passar o caminho da pasta
  pela linha de comando (mesmo pelo PowerShell) corrompe o "Õ" de
  "CERTIDÕES" — o nome real da pasta usa o "O" com til **decomposto**
  (U+0303), não o "Õ" pronto (U+00D5). A saída é sempre resolver o caminho
  com `glob.glob(...CERTID*ES...)` e nunca digitar o caractere direto num
  script.
