# A base pré-carregada da ajuda

**18/09/2026.** O pedido: *«preciso que o módulo de ajuda tenha uma base de
conhecimento pré-carregada, não dá pra buscar as respostas de tudo para cada
problema»*.

Ele está dizendo duas coisas, e a segunda é a que manda no desenho: **a ajuda
sabia procurar, e procurava do jeito caro.** Cada pergunta em que ela precisava
de um documento relia **a `docs/tecnico/` inteira do disco** — **171 arquivos
então, 172 hoje** —, e as regras da casa eram lidas **outra vez, à parte**: a
mesma busca custava **1.148 ms** lendo os arquivos e **42 ms** sobre a base
carregada, medidos em 15/09/2026. Três rodadas numa pergunta só davam mais de três segundos, e o
contexto da consulta ainda levava o índice dos documentos **inteiro, com a
primeira frase de cada um**, em toda pergunta.

O que esta passada entrega é uma camada só, em memória, com as três fontes
juntas: **os documentos do projeto, as regras da casa e o que o oficial
escreve**.

---

## 1. O que ficou: uma base, três fontes, uma carga

`ajuda_base.py` é o módulo. Ele lê as fontes **uma vez por processo** e guarda,
de cada linha, o texto e a forma normalizada — sem acento e sem caixa. Depois
disso, toda busca é varredura em memória.

| a fonte | o que é | onde mora |
|---|---|---|
| `DOCUMENTO` | a documentação do projeto | `docs/tecnico/*.md` — **172 arquivos** |
| `REGRA` | as regras da casa | `CLAUDE.md` — as seções que o índice conta |
| `MANUAL` | o que o oficial escreveu | a tabela `aj_verbetes`, que nasceu aqui |

**Medido em 18/09/2026, 17h1x, com a máquina ociosa** — e este documento é um
dos arquivos contados, porque ele mora na pasta que a base lê:

| | |
|---|---|
| a carga, uma vez por processo | **3,02 s** |
| o que ela indexa | **48.248 linhas** · **2.426.575 caracteres** · **173 origens** |
| a conferência da assinatura (o cache vencido) | **88,0 ms** |
| a chamada dentro do intervalo (não confere nada) | **0,3 ms** |
| uma busca, média de cinco | **159,8 ms** |
| o contexto que a IA recebe em toda pergunta | **323 caracteres** |
| só **ler** os 172 arquivos do disco | **208,7 ms**, sem procurar nada |

**Por que a carga é lenta e por que isso não importa**: indexar 2,4 milhões de
caracteres custa 3,02 s, e ela acontece **uma vez**, na primeira pergunta depois
de o processo subir. O que se paga por pergunta é a busca — e é aí que o número
desce.

> **E AS DUAS MEDIÇÕES DO MESMO DIA NÃO BATEM, e as duas estão certas.** A
> primeira foi feita **com a suíte de outra passada rodando nesta árvore**: carga
> **3,38 s**, busca **204,5 ms**. A segunda, com a máquina ociosa: **3,02 s** e
> **159,8 ms**. Trinta por cento de diferença, e nenhuma linha de código mudou
> entre uma e outra — **o que mudou foi quem mais estava usando a máquina**.
> É por isso que todo número aqui vai com data, hora e condição: **a medição
> sozinha não envelhece; o que ela mediu é que muda embaixo dela.**

> **E O NÚMERO DE 15/09 CONTINUA VALENDO PARA O QUE ELE MEDIU.** Naquele dia a
> busca sobre a base saiu **42 ms** e a função antiga, **1.148 ms** — medidos
> antes de o volume de documentos crescer para onde está hoje. **Os três números
> convivem porque cada um diz o que mediu, quando e em que máquina**; o que
> mente é usar um deles como se fosse o outro.

> **E UMA TERCEIRA MEDIÇÃO, FEITA ENQUANTO ESTE DOCUMENTO ERA ESCRITO**, dá
> **1,86 s** de carga, **48.321 linhas** e **173 origens** — e ela é mais rápida
> que a das 17h1x com a máquina ociosa, o que não faz sentido até se olhar o que
> mudou: as duas rodaram com a **suíte desta passada** em andamento, e o que
> separa 3,02 s de 1,86 s não é o código nem o volume — é **quem mais estava
> usando o disco no minuto da medição**. Quem for comparar daqui a um mês comece
> medindo de novo, e não conferindo esta linha.

### A régua do «antes» e do «agora», lado a lado

O script `tmp/_medir_antes_e_agora.py` roda a mesma busca dos dois jeitos, no
mesmo instante, com os mesmos cinco termos:

```
=== o caminho de antes: ler e procurar, arquivo por arquivo ===
«carimbo que mente»: 32 linhas, 1210 ms  (só os documentos; as regras seriam lidas à parte)
«matricula de 32 digitos»: 43 linhas, 1354 ms
«selo do casamento»: 26 linhas, 1585 ms
«teto de portabilidade»: 5 linhas, 1405 ms
«etiqueta de reconhecimento de firma»: 6 linhas, 1462 ms
                                                    média: 1403 ms

=== o de agora, o mesmo termo ===
«carimbo que mente»: 51 linhas, 219 ms  (as 172 fontes juntas, com seção, linha e pontuação)
«matricula de 32 digitos»: 52 linhas, 145 ms
«selo do casamento»: 32 linhas, 145 ms
«teto de portabilidade»: 8 linhas, 163 ms
«etiqueta de reconhecimento de firma»: 7 linhas, 139 ms
                                                    média: 162 ms
```

**A segunda metade também conta**: o «agora» acha **mais** — 51 contra 32,
porque ele varre as três fontes numa chamada, e a de antes só olhava os
documentos (as regras custariam outra varredura inteira, e é por isso que a
ajuda fazia três rodadas).

> **E ESTE DOCUMENTO ESTÁ DENTRO DA CONTA, e isso se vê no número.** Ele cita os
> cinco termos de propósito, porque é assim que ele explica o que eles acham —
> e por isso a mesma medição, feita uma hora antes de ele existir, deu **27, 41,
> 24, 2 e 4** linhas onde agora dá **32, 43, 26, 5 e 6**. **Documento novo muda
> a resposta da busca**, e é bom que mude: é o que faz a ajuda saber o que foi
> feito ontem.

> **O que o script de antes mede não é a função antiga, e a honestidade disso
> está no próprio script.** Ele refaz o caminho (abrir, ler, normalizar linha a
> linha, procurar) para poder medir os dois na mesma máquina e no mesmo minuto;
> a função antiga de verdade era mais rápida que esta imitação, porque usava uma
> expressão compilada — **1.148 ms**, o número que ficou registrado quando ela
> foi medida. **A imitação serve para comparar antes e agora no mesmo instante;
> o número oficial do «antes» é o 1.148.**

---

## 2. O que a busca conta, e o que ela avisa

`buscar()` devolve o achado estruturado — fonte, origem, seção, linha, trecho e
pontuação — e quem formata é `procurar()`, porque **o formato de cada fonte é
contrato com quem já o lia**: o de `procurar_nos_documentos` existe desde
15/09/2026 e a tela e o teste leem o endereço nele.

A régua de pontuação:

| pontos | quando |
|---|---|
| **1000** | a linha tem o **termo inteiro**, como quem procurou escreveu |
| 400 | a linha tem **todas as palavras** do termo, separadas |
| menos | a linha tem parte delas |

**E a régua abre quando precisa:** um termo de duas palavras que só aparece
separado contaria zero, e é justamente aí que a busca precisa dos dois. Então
ela conta as linhas que têm todas as palavras — e **avisa que contou assim**:

> «A base tem 53 linha(s) com «carimbo que mente» **(45 com a frase exata)**»

Isso é o `_ressalva`, e ele existe porque **o número mentiria para mais**: quem
lê «53 linhas» conclui que a casa escreveu 53 vezes o termo que ele pediu. O
aviso só aparece quando os dois números diferem — no caso comum, ele é vazio.

**A ordem é a pertinência**, e o empate não se inventa: o `sorted` do Python é
estável, e o que empata fica na ordem de leitura.

**E a lista se espalha em vez de encher de um só.** `_espalhar` dá a vez às
origens diferentes antes de repetir uma — com uma cota de 4 por origem e uma
segunda volta que preenche o que sobrar. Sem a segunda volta, pedir cinco
achados num assunto que só tem um documento devolveria um, e «pedi cinco, vieram
um» é o carimbo que mente sobre o próprio filtro.

### Quando não acha nada, ela diz — e diz o que isso não prova

```
Nenhuma linha dos 172 documentos do projeto fala de «tal coisa». Isso quer dizer
que ninguém escreveu sobre isso — e não que a coisa não exista: o sistema pode
fazê-lo sem documento nenhum. Procure outro termo, ou veja o código.
```

**Silêncio, aqui, viraria «a casa nunca escreveu sobre isso»** — e a resposta
sairia com a mesma cara de uma resposta certa. É a regra do zero medido e zero
por engano, aplicada à busca.

---

## 3. O acento, a caixa e o cabeçalho

**`sem_acento` é a diferença entre achar e não achar.** Quem procura escreve
«matricula» com a maior naturalidade, e o documento diz «matrícula»; o mesmo
vale para «sessao»/«sessão» e «nao»/«não». A normalização é feita **uma vez, na
carga**, e não a cada busca — é a parte que torna a varredura em memória barata.

**É a mesma função da casa, e não uma parecida.** Havia uma `normalizar_nome` no
`pt_schema` que devolvia minúsculas e outra copiada dentro do módulo de fraudes
que devolvia maiúsculas — **o alerta por nome não achava ninguém**, e nenhuma
releitura pegou. Aqui a normalização é uma só, `ajuda_base.sem_acento`, e há
teste que procura pelo termo **com** acento e pelo termo **sem** ele.

**O título da seção é procurado junto com o texto**, e isso responde a um
pedido direto: quem procura «teto de portabilidade» e o documento tem esse texto
**no título** precisa achá-lo. Como o título é uma linha do arquivo, procurá-lo
não é um caso especial: ele entra na varredura como as outras linhas.

**E é por isso que a linha que ele devolve conta o título** — detalhe que vale
uma nota, porque já custou caro neste projeto. O cabeçalho **não** está dentro
de `linhas` (é campo próprio do bloco), e numerar o achado pela linha do
cabeçalho faria **todo endereço depois do primeiro apontar uma linha antes** do
que achou. O endereço é o que permite abrir o arquivo e conferir; apontar uma
linha errada é pior que não apontar.

---

## 4. O cache não pode mentir

A base se **recarrega sozinha** quando um documento muda, e a conferência é a
impressão digital das fontes: o tamanho e a data de modificação de cada arquivo.

**As duas metades são medidas, e é o que decide o desenho:** conferir a
assinatura custa **88 ms** (173 `stat`, medidos hoje com a máquina ociosa) e
construir a base custa **3,02 s**. Conferir a cada busca devolveria 88 ms em
cima de cada pergunta; não conferir nunca faria a ajuda responder com o
documento de ontem. A saída é o `INTERVALO_DA_CONFERENCIA`: **2 segundos** — o
cache não mente em escala de gente, e a conta por pergunta fica em milissegundos
(medido: **0,3 ms** dentro do intervalo). Quem quiser o outro extremo,
`carregar(forcar=True)` reconstrói na hora.

**Falhar não é silencioso.** Se a construção inteira estourar — o que não deveria
acontecer, porque arquivo ilegível já é tolerado um a um —, o motivo fica
guardado e `resumo()` o mostra na tela. É o mesmo cuidado do `except` largo que
transformava «não achei a tabela» em «zero pendências»: **zero medido e zero por
engano são a mesma tela e coisas diferentes.**

**A carga é por processo.** O servidor é um processo só; subir de novo recarrega.
Não há cópia em disco e não há arquivo de índice — o que existe é a leitura dos
arquivos na memória de quem responde.

**O que fica de fora da assinatura**: os verbetes. Eles moram no banco e são
lidos **a cada busca** por quem tem a conexão na mão — é a tabela do oficial, e
cachear o que ele acabou de escrever faria ele digitar, salvar e não ver.

---

## 5. O contexto que vai em toda pergunta

`para_o_contexto()` devolve **323 caracteres**. São três linhas e uma lista:

- quantas origens, quantas linhas e quantos caracteres a base tem;
- **o endereço de cada fonte** (a pasta, o caminho das regras, a tabela);
- os **títulos** dos verbetes do oficial — no máximo 40, e só os títulos;
- a frase que diz o que fazer: **uma chamada de `buscar_na_base` procura nas
  três de uma vez.**

> **O TEXTO DA BASE NÃO VAI, E ISSO É A REGRA DA FATIA.** Ele já foi medido do
> outro lado: o índice dos documentos **com a primeira frase de cada um** custava
> **24.356 caracteres** e era **70 % do contexto** de toda pergunta — e uma
> primeira frase nunca resumiu um documento de cem mil caracteres. A frase saiu
> em 15/09/2026 e o contexto inteiro caiu de **34.719** para **23.731**. Aqui a
> mesma régua: **o título diz o assunto, e o texto custa só quando é chamado.**

**E os títulos dos verbetes vão por inteiro de propósito**: o título é o que
permite pedir «o que o oficial escreveu sobre a etiqueta», e o texto dele é o
que custa.

---

## 6. O que o oficial escreve

A terceira fonte é dele, e é a única que se escreve **de dentro do sistema**.

| | |
|---|---|
| a tabela | `aj_verbetes` — título, texto, assunto, onde, quem escreveu e quando |
| o piso | **dez letras**, o mesmo da recusa de certidão do RCPN e do RI |
| quem entra | `ADMIN` e `MANAGER` — **a porta é do oficial, e é deliberado** |
| o rastro | `AJUDA_BASE_VERBETE_GRAVADO` e `AJUDA_BASE_VERBETE_APAGADO` na auditoria |

**Por que a porta é dele, e não do balcão.** O que ele escrever aqui a ajuda lê
**como lê os documentos**: com a mesma convicção. Um verbete errado não fica no
caderno de quem o escreveu — fica na resposta que o balcão vai receber como «a
casa decidiu assim». É a mesma separação do alcance da ajuda e do agente:
**consultar abre; configurar, não.**

**Editar não cria outro**: a rota leva o `id` quando existe e recusa quando não
existe, em vez de criar mais um. Criar em silêncio é como se perde a conta de
quantos «o mesmo» verbete existem.

**Apagar não é ato de cartório.** Nada do que a serventia lavrou passa por esta
tabela; o que se apaga é o caderno da ajuda — e deixar a linha velha seria pior,
porque a ajuda a leria com a mesma convicção das outras.

**E o verbete entra na busca como uma fonte a mais** — a quarta origem, com o
endereço dele em vez de arquivo e linha: `escrito por FULANO em 18/09/2026 —
«o título»`.

---

## 7. As quatro portas de entrada

A base é **uma só** e tem quatro caminhos até ela. Nenhum tem cópia da régua de
busca:

| a porta | o que ela é |
|---|---|
| **a ferramenta do modelo** — `buscar_na_base` | o caminho da ajuda; **uma chamada para as três fontes**, e é o que ele pediu |
| `ajuda_projeto.procurar_nos_documentos` | **a assinatura não mudou** e o corpo mudou de lugar: ela delega |
| `ajuda_regras.procurar` | idem, com o escopo das regras |
| **a tela** — `/ajuda/base` | o que está indexado, e o que o oficial escreve |

**O corpo mudou de lugar e a assinatura não, e isso é deliberado.** As duas
funções antigas têm chamador no modelo, na tela e nos testes, e reescrevê-las
onde estavam seria **a segunda régua de busca da casa** — que é como duas
divergem no primeiro conserto.

**E a tela procura com a mesma função da ajuda**, não com uma parecida: quem
abre `/ajuda/base` e procura «carimbo que mente» vê exatamente o que a ajuda
veria. **Tela que mostra uma coisa e sistema que manda outra** é o defeito que
este projeto persegue desde a `normalizar_nome`.

**A ferramenta do modelo se chama `buscar_na_base`, e não `procurar_nos_documentos`**,
porque o nome diz o que ela faz: procura na base inteira. E a instrução fixa diz
isso ao modelo — sem essa linha ele não sabe que a base existe e volta a
procurar de um em um, que é o custo que o pedido manda tirar.

**A tela diz a verdade quando a base não tem o que se espera.** Se os documentos
não chegaram nesta instalação, o número aparece **abaixo do piso** e a tela diz
que é isso. O `PISO_DE_DOCUMENTOS = 50` não é alvo: é diagnóstico — o
`ATUALIZAR_SISTEMA.cmd` copiava `*.py`, telas, `static`, `modelos`, `VERSAO.txt`
e `requirements.txt`, e **os `.md` não estavam em nenhuma das linhas dele**. A
ajuda respondia olhando uma biblioteca de três arquivos **sem nada que dissesse
que a biblioteca não tinha chegado**.

---

## 8. O que se mediu, e o que não se mediu

**Medido nesta passada:** a carga, o cache, a busca, o contexto, o tamanho das
fontes — os números do § 1 e do § 5, todos com data e condição.

**O que eu não medi, e fica declarado:**

1. **O ganho de ponta a ponta numa pergunta de verdade.** O que se mediu é a
   busca e a leitura; o que a pergunta custa inclui a chamada ao provedor de IA,
   que não se mede aqui. **O que se pode afirmar é o que mudou**: a ajuda deixou
   de precisar de **até três rodadas** para procurar, e cada rodada custava uma
   varredura do disco.
2. **A base é construída por processo, e o servidor não foi medido com ela em
   uso no balcão.** O primeiro a perguntar depois de uma atualização paga os
   3,02 s.
3. **Não há índice invertido — e ele é o próximo passo, se algum dia doer.**
   Cada busca varre as 48.248 linhas em memória: **159,8 ms hoje**. Uma tabela
   de palavra → linhas traria isso para a casa dos milissegundos, e custaria
   memória (centenas de milhares de posições) e um caminho novo para manter em
   sincronia com o cache. **Não foi feito porque 160 ms não atrapalha quem
   espera segundos por uma resposta de IA** — e a régua para voltar a esta
   decisão é este número, medido de novo, e não a impressão de que está lento.
4. **Subpasta nenhuma entra.** A varredura é `docs/tecnico/*.md`, de primeiro
   nível — é onde a documentação da casa mora, por decisão de 29/08/2026.

---

## 9. Os enganos do caminho

Ficam escritos porque foi assim que eles apareceram, e nenhum foi achado por
releitura:

1. **O `csrf_token` da tela.** O molde chamava `csrf_token()` como função; no
   contexto do Flask ele é **valor**. Quem pegou foi o teste da tela, na
   primeira vez que ela foi aberta — e é o argumento de sempre: **teste de tela
   mede o que o navegador recebe, e não o que o código parece querer dizer.**
2. **Um teste meu media a página inteira onde o que importa é a linha.** Ele
   exigia que o título do verbete apagado não aparecesse no HTML — e a mensagem
   de sucesso da própria exclusão carrega o título (««tal» saiu da base»).
   **Procurar uma palavra na página inteira é a régua que já bateu na própria
   prosa sete vezes neste projeto**; a asserção passou a olhar a **linha** do
   verbete e a mensagem.
3. **Dois scripts de medição meus caíram por chute de nome de chave** —
   `origens` onde é `total_de_origens`, e `titulo` onde é `secao`. **Nome
   plausível é o que mais se parece com medição sem ser**, e quem desempatou foi
   rodar contra a base de verdade, não reler o script.
4. **A linha que sai da base colapsava o branco de dentro, e o endereço
   deixava de se conferir.** `_trecho` fazia `" ".join(linha.split())` — limpeza
   razoável para texto colado de fora, **perda silenciosa** para quem promete
   citar o que o arquivo escreve. Medido: uma linha deste próprio documento
   escreve «1210 ms **dois espaços** (só os documentos», e a base mostrava um —
   quem copiasse o que a base mostra e procurasse no arquivo **não achava**.
   Quem pegou foi `test_o_endereco_que_ela_devolve_aponta_para_a_linha_certa`,
   que abre o arquivo e compara com a linha de verdade em vez de comparar a base
   com ela mesma. **É «o teste que mede espaço não pode colapsar espaço», de
   31/08, na mesma família** — lá o `split()` do teste comia a linha em branco
   que era o conteúdo; aqui o `split()` da base comia o espaço que era o
   endereço. Agora ela **tira as pontas** (a indentação do markdown não
   identifica a linha) e **corta o tamanho** (que é a razão de a função
   existir), e não toca no que está no meio.

5. **A resposta do «não achei» saía com 173 números, um por arquivo.** A
   pergunta é «não achou?», e o que se devolve é o tamanho do que foi varrido —
   e são **três** lugares: os documentos, as regras e os verbetes. A primeira
   versão somava o que `fontes()` devolve, e `fontes()` é uma linha por
   **ORIGEM**: medido ao imprimir a resposta, **2.400 caracteres** de lista de
   arquivos para dizer «procurei em toda ela», com a mesma frase
   «nos documentos do projeto» repetida 171 vezes. Também foi correção de
   frase: a versão anterior montava `f"{n} em {rótulo}"` e o rótulo já carrega
   o artigo — saía **«32 em os documentos do projeto»**. Duas correções na
   mesma linha, e as duas só apareceram **olhando a resposta impressa**. Há
   guarda agora: `test_o_que_nao_se_achou_e_contado_por_fonte_e_nao_por_arquivo`
   conta os números da resposta e recusa nome de arquivo no que não achou nada.

> **E OS CINCO ENGANOS TÊM A MESMA FORMA.** Nenhum foi achado por releitura, e
> os cinco só apareceram **rodando**: o `csrf_token` na primeira vez que a tela
> abriu, o título do verbete contra o HTML de verdade, os dois nomes de chave
> contra a base, o espaço contra o arquivo, e a parede de números contra a
> resposta impressa. **É o que este projeto repete desde 27/08 — os defeitos
> chegam pela janela do uso, e não pela leitura.**

---

## 10. As provas

**193 testes passaram** nos seis arquivos da família da ajuda, medidos em
18/09/2026 — e a conta fecha com o número de testes de cada um:

| arquivo | testes |
|---|---|
| `tests/test_ajuda_base.py` — **novo** | **31** |
| `tests/test_ajuda_projeto.py` | 36 |
| `tests/test_ajuda_regras.py` | 23 |
| `tests/test_ajuda.py` | 37 |
| `tests/test_ajuda_janela.py` | 29 |
| `tests/test_agente.py` | 37 |

> **E O NÚMERO NÃO É SOMA DE MEDIÇÕES SOLTAS: ele é uma rodada só.** Depois do
> último conserto, os seis arquivos rodaram **de uma vez**, em **9m56s**, e
> responderam **193 passed** — o mesmo número, agora contado e não somado. A
> tabela acima foi conferida em separado com `--collect-only`, arquivo por
> arquivo, porque *número escrito em documento é número que ninguém confere*, e
> este arquivo já carimbou errado a contagem de testes de outra passada: as seis
> linhas batem uma a uma com a coleta.
>
> **A suíte inteira continua não medida nesta passada** — o portão da casa
> (`tools/pytest_guard.py`) recusou a varredura porque havia outra suíte rodando
> nesta árvore, e é para isso que ele existe. **Quem aplicar esta versão e quiser
> o número grande, meça de novo.**

Os 31 do módulo novo cobrem, um por um: a carga das fontes; a pasta ser uma
definição só; o documento de outra pasta não entrar; **o endereço apontar para a
linha certa**; o das regras levar a seção; **a linha do achado contar o
cabeçalho**; a busca não depender de acento nem de caixa; **o título da seção
ser procurado**; os dois números da ressalva; o espalhamento dos achados; termo
vazio recusado com a frase da casa; limite zero devolvendo zero com cara de
zero; as três fontes numa chamada; **o que não se acha dizer que não se achou e
por que isso não é prova**; **o «não achei» contar por fonte e não por arquivo**;
o contexto não levar o texto da base nem de um
verbeta, e levar o título dele; **o contexto dizer que não carregou em vez de
dizer zero**; o piso do verbete curto; alterar o que não existe recusar em vez
de criar outro; apagar o que não existe devolver falso; o ciclo gravar-alterar-
apagar; o verbete entrar na busca; **a base se recarregar quando o documento
muda**; o arquivo ilegível não derrubar a base; pasta vazia aparecer como zero e
não como pronto; e as cinco da tela — abrir sem gastar consulta, procurar com a
mesma função da ajuda, escrever e apagar, recusar o verbete curto com a frase
para o balcão, e não ser do balcão.

**A suíte inteira não foi medida nesta passada**, e a razão é do dia: havia mais
de uma suíte rodando nesta árvore, e o portão da casa (`tools/pytest_guard.py`)
existe justamente para não deixar duas medições se atropelarem. O número de
testes coletados da linha do `CLAUDE.md` é da passada vizinha, não desta.

---

## O que fica para quem vier depois

- **Se a busca começar a parecer lenta, o número é o § 8.3** — 159,8 ms, medido
  assim, nesta máquina. Não é impressão: é medir de novo e comparar.
- **Os verbetes são a única fonte que se escreve de dentro do sistema**, e ela
  está declarada na auditoria. Se um dia a ajuda responder algo que o oficial
  não escreveu, o caminho é a tabela `aj_verbetes` e o `AJUDA_BASE_VERBETE_GRAVADO`.
- **A instrução fixa menciona a base, e isso não é enfeite**: sem essa linha o
  modelo volta a procurar de um em um, e o custo que esta passada tirou volta
  sem ninguém notar. A prova é `test_ajuda.py`.
