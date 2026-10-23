# ROTEIRO 3.6.131 — a ajuda que lê as regras da casa, e o pacote que leva os documentos

**Data:** 15/09/2026 · **Versão:** 3.6.131 (projeto) · **Servidor:** 3.6.130 — medido
agora em `C:\Program Files\CartorioGestao\VERSAO.txt`, não suposto.

> **ESTE ROTEIRO TEM DUAS METADES, E A SEGUNDA NÃO É MINHA.** A primeira é a ajuda: ela
> passou a **ler as regras da casa**, a **achar o trecho dentro dos documentos** e a
> **custar um terço do que custava** em cada pergunta. A segunda é o pacote: ele **levava
> 36 cópias de arquivo de programa** para o servidor e **não levava os documentos nem o
> `CLAUDE.md`** — sem eles, a ajuda nova não funciona lá. Digo isto no alto porque o item
> 9 diz, com os números, **de quem é cada arquivo** que esta atualização troca.

---

## 1. O PEDIDO, nas palavras dele

1. A lembrança dele de 14/09, ao aprovar o agente: *«depois lembrar de revisarmos o ajuda
   do claude para atualizar automatico e ganhar mais funcoes»*.
2. A escolha de hoje, entre as que eu levei medidas: **baixar o custo do contexto** — o
   índice dos 162 documentos era **70 %** de tudo o que a ajuda mandava em cada pergunta.
3. E depois: **levar a ajuda nova ao servidor**.

---

## 2. O QUE MUDOU NA AJUDA

### 2.1 Ela lê as regras da casa — `ajuda_regras.py`

O `CLAUDE.md` é o arquivo onde esta casa escreveu **como se decide aqui** — 42 seções,
todas com data e com a razão ao lado. Ele **não estava ao alcance da ajuda**: ela respondia
pela regra geral, que é o que a internet sabe, e não pela decisão desta serventia.

Agora há `ler_regras`, com três jeitos: **sem argumento** devolve o índice das seções;
**por número ou pedaço do título** devolve o texto dela; **por termo** devolve as linhas em
que o assunto aparece. E há teste que percorre as 42.

**E ela não inventa carimbo.** A ajuda lê a versão e o tamanho da suíte que o `CLAUDE.md`
declara e **compara com o que está rodando** — e quando não dá para conferir, ela diz
**o que não conseguiu conferir**, em vez de dar veredito. É a regra do «carimbo que mente»
aplicada à própria ajuda: melhor «não sei» do que um número com cara de conferido.

### 2.2 Ela acha o trecho dentro dos documentos — `procurar_nos_documentos`

**A peça que troca «ler os 163» por «achar o trecho».** O índice diz o nome e o título de
cada documento; encontrar o parágrafo que fala de um assunto, no meio de cem mil
caracteres, é aqui — com **o arquivo e o número da linha**, que são o endereço para pedir o
documento inteiro depois.

Medido agora, procurando «impressora»:

> 14 linha(s), em 3 arquivo(s). Os documentos com mais linhas: `ROTEIRO_3.6.65.md` (7),
> `ETIQUETA_DE_FIRMA.md` (6), `LEVANTAMENTO_QUATRO_ATRIBUICOES.md` (1)

**Ela diz sempre quantas linhas achou**, e não só as que cabem: busca que devolve quarenta
achados sem dizer que há duzentos faz quem lê concluir que o assunto acaba ali. E quando
**não acha nada**, diz que não achou — silêncio, aqui, viraria «a casa nunca escreveu sobre
isso». A procura **ignora acento e caixa** (`matricula de 32 digitos` acha «matrícula de 32
dígitos»).

> **E o que ela NÃO varre fica dito, e não em silêncio.** A pasta `DOCUMENTACAO` tem **170**
> arquivos `.md`: **163 na raiz** — que são os que a ajuda indexa e procura — e **7 em
> subpasta**, os modelos do RTDPJ e o LEIA-ME deles. Esses sete **não entram no índice nem
> na procura**, e quem procurasse por eles receberia «nenhuma linha», que é a conclusão
> errada com cara de medição. Está escrito no próprio módulo, para quem mexer depois saber
> que o recorte é escolha e não esquecimento.

### 2.3 O contexto caiu de 34.719 para 23.766 caracteres

**O que se pagava era a PRIMEIRA FRASE de cada documento** — 11.099 caracteres em **toda**
pergunta, para dar o começo, e não o meio. O índice perdeu a frase e ficou com o nome e o
título, que é o que diz o assunto.

Medido contra o banco da produção, o contexto inteiro, na última vez às 17h05 de 15/09/2026:

| a parte | caracteres |
|---|---|
| o cabeçalho (versão e o que a ajuda sabe) | 44 |
| **os documentos do projeto (163)** | **13.131** |
| os relatos da casa (28 abertos de 62) | 6.477 |
| as regras desta casa (o índice das 42 seções) | 2.140 |
| o que mudou nesta instalação | 1.245 |
| o que só o oficial pode informar (12) | 709 |
| **total** | **23.766** |

**São quatro números no mesmo dia, e eles não são iguais — cada um com o seu instante:** o
**34.719** é a consulta **antes** (com a primeira frase no índice); o **23.731** é ela já sem
a frase, medido com **162** documentos; o **23.625** é o das 16h45; o **23.766** é o de
agora. **A diferença entre os três últimos não é desvio de medição: é o dia andando** — um
documento a mais (este roteiro), um relato a mais, e as regras medidas de novo —, e é por
isso que o número vai com a hora ao lado. **A medição sozinha não envelhece; o que envelhece
é o sistema que ela mediu**, e este mudou de conteúdo entre uma conta e a outra.

**E o peso mudou de lugar, e isso fica dito:** o índice dos documentos continua sendo o
maior pedaço, e **a lista dos relatos passou a ser o segundo** — ela vai inteira em toda
pergunta, com a frase de cada um. É a próxima economia, e **não foi feita nesta passada**.

### 2.4 Ela conta o que o desenvolvimento escreveu em cada relato

O «o que mudou nesta instalação» levava só a mudança estrutural (tabela nova, coluna nova).
Agora leva também **as notas que o desenvolvimento escreveu dentro dos relatos** — o porquê
do conserto, que é justamente o que a ajuda precisa para responder «por que é assim?».
Antes de sair, cada nota é resumida à primeira frase, para não virar contexto pagode duas
vezes.

---

## 3. O PACOTE: O QUE ELE LEVAVA E NÃO DEVIA, E O QUE NÃO LEVAVA E DEVIA

### 3.1 Trinta e seis cópias do próprio programa — 5,1 MB

Medido antes de empacotar: o `.cgu` levaria **854 arquivos**, e **36** eram cópia de
arquivo de programa com outro nome — `atribuicoes_web.py.bak_pre_folha_obrig` (331 KB),
`atribuicoes_web.py.new` (299 KB), `=ro` (0 byte, de um comando digitado errado).

**Nada disso é importado, lido ou aberto** — é a família do `.pytest_cache` que este
projeto já tirou do pacote: **arquivo inerte com cara de resposta** dentro da pasta do
programa. Com uma diferença que pesa: estes têm nomes que *quase* são os verdadeiros, e
quem abrir a pasta do balcão para conferir o que está rodando encontra trinta e seis
cópias — e «qual destes é o que está no ar?» não se responde olhando.

Agora ficam de fora, e há teste que guarda isso (`tests/test_pacote_nao_leva_lixo.py`), com
o **piso** de arquivos varridos: varredor que deixa de achar passa calado.

**Medido depois, dentro do pacote fechado: 818 arquivos** — e nenhuma das 36 cópias. A
conta fecha com o resto do que mudou hoje: saíram as 36, saíram **1 `.original`** e **1 PDF
solto na raiz**, entrou o **`CLAUDE.md`** (que viaja de fora da pasta) e entrou **este
roteiro**. **854 − 36 − 1 − 1 + 1 + 1 = 818.**

> **E O FILTRO DO PDF É SÓ DA RAIZ, e isso é medido, não estético.** Havia na raiz um
> `previa_inteiro_teor_pessoa_exemplo.pdf` (71 KB) — a prévia de uma certidão de cliente, salva ali
> para conferência e esquecida, **com o nome de uma pessoa da casa dentro**. A tentação é
> filtrar `.pdf` no pacote inteiro — e isso tiraria os **três modelos do RTDPJ** (3,9 MB,
> dentro da `DOCUMENTACAO`) que a ajuda lê. **Filtro que tira o que devia ficar é pior que
> filtro nenhum**, e há teste para as duas direções: uma que exige zero PDF na raiz, outra
> que exige os três do RTDPJ presentes.

> **E EMPACOTAR ACHOU UM DEFEITO MEU, no mesmo minuto.** O `criar_atualizacao.py` morreu com
> `'str' object has no attribute 'open'`: eu havia escrito `todos_os_arquivos` devolvendo o
> par **`(destino, arquivo)`** enquanto o `iter_files` devolve **`(arquivo, destino)`** — e o
> `main` desempacota na ordem do segundo. **Duas funções com o par de nome igual e ordem
> oposta são duas réguas para a mesma medida**, e nada no erro dizia qual das duas estava
> torta. Consertado na função, e agora há um terceiro teste que confere **o tipo de cada
> posição** nas duas — a ordem não se afirma em comentário, confere-se.

### 3.2 Os documentos e as regras nunca chegaram ao servidor — e a causa não era o pacote

**Esta é a metade que decide se a ajuda nova funciona.** Medido agora no servidor:

| | no servidor | na árvore |
|---|---|---|
| documentos do projeto | **3** | **163** |
| `CLAUDE.md` | **não existe** | existe (raiz do projeto) |

Os três que existem chegaram **à mão**, um a um, em 13 e 14/09 — são os que A ESCREVENTE
precisou naqueles dias. **A ajuda subiria inteira e responderia sobre uma biblioteca de três
arquivos** — e, pior, **sem saber que faltavam 160**: ausência com cara de medição, que é a
mesma família do «zero pendências» que já apareceu aqui.

> **EU PRIMEIRO ESCREVI QUE O PACOTE NÃO OS LEVAVA, E A MEDIÇÃO ME DESMENTIU.** Abri o
> `.cgu` da **3.6.98** e o da **3.6.99**, e os dois trazem os documentos no corpo: **162
> entradas `payload/docs/tecnico/*.md`** em cada um. O empacotador fazia a parte dele desde
> 11/09. Quem não levava era o **outro** caminho — e ele é o que está em uso.

**São dois caminhos de atualização, e até 15/09 só um funcionava nesta instalação:**

| | o que aconteceu, medido |
|---|---|
| **`.cgu`** (pela tela do sistema) | `%PROGRAMDATA%\CartorioGestao\updates\update.log` registra **uma** tentativa, em **09/09/2026 às 18:33 — «Aplicando atualizacao para 3.6.76» … «ERRO: Acesso negado.»** O `aplicar_atualizacao.ps1` que estava no servidor era o de **13/08** (4.348 bytes), porque o `.cmd` **excluía a pasta `installer`** — **o conserto do atualizador viajava dentro da atualização que o atualizador não conseguia aplicar**. Corrigido e aplicado em **15/09 às 17:41**: hoje o servidor tem o `ps1` de **9.600 bytes**, conferido por hash contra a árvore. |
| **`ATUALIZAR_SISTEMA.cmd`** (com UAC) | é o que o senhor usa desde então, e é por ele que o servidor está na **3.6.131**. Ele copiava `*.py`, as telas, o `static`, os `modelos` e o `VERSAO.txt` — **e mais nada**. É daqui que vêm os três documentos. |

**Logo: o motivo de o servidor ter três documentos não é o pacote — é o script que se usa.**
E isso muda o que se deve fazer depois de aplicar, que está no § 4.

**Corrigido, e com conferência, e não com suposição:** o `ATUALIZAR_SISTEMA.cmd` passou a
copiar a pasta `DOCUMENTACAO` inteira, a pasta **`installer`** (que é o conserto de que
trata o bloco abaixo) e o `CLAUDE.md` (que mora **fora** da pasta do programa, na raiz do
projeto, e por isso vem por caminho próprio) — **e a conferir que chegou**, imprimindo
`ATENCAO: as regras da casa nao chegaram...` quando não chegou. Cópia que falha em
silêncio é o mesmo defeito de novo, só que mais tarde e mais difícil de achar.

**O `CLAUDE.md` passou a viajar nos dois caminhos**, e isso importa justamente pelo dia em
que o `.cgu` fosse consertado: o pacote leva a árvore inteira mais o arquivo das regras, que
está fora dela.

> **A PERGUNTA ACIMA FOI RESPONDIDA, E O CONSERTO ESTÁ APLICADO — 15/09/2026, 17h41.**
> O senhor escolheu **consertar**, e mandou aplicar na mesma hora pelo
> `ATUALIZAR_SISTEMA.cmd`. O que segue é a medição que fechou a causa e o que foi feito.

**A CAUSA NÃO ERA FALTA DE ELEVAÇÃO, e foram três medições que a fecharam:**

| | medido |
|---|---|
| a tentativa de 09/09 | rodou das 18:33:44 às 18:33:51 — **sete segundos** —, e o log acaba em «ERRO: Acesso negado.» |
| a cópia de rollback | `...\updates\20260909_183344_v3.6.76` **existe no disco**, e o `ps1` do servidor continuou com 4.348 bytes: ele parou **na primeira cópia grande**, e o payload nunca chegou |
| o `ps1` do servidor | era o de **13/08** — e **idêntico ao que vinha dentro do `.cgu`**. O pacote estava certo; o programa que o aplicava é que não. |

> **E uma coisa eu NÃO consegui medir, e digo isso em vez de afirmar:** com que conta
> o serviço rodava em **09/09**. Hoje ele roda em **sessão 0, como serviço**, e nessa
> conta `C:\Program Files` é gravável — foi daí que o conserto saiu. Se em 09/09 rodava
> como usuário comum, o acesso negado é exatamente o que se vê. O que se sabe, e é o
> que importa, é que **o defeito de fundo era outro e era maior**.

**O DEFEITO DE FUNDO, e é a lição que fica:** o `ATUALIZAR_SISTEMA.cmd` **não copiava a
pasta `installer`** — e é dentro dela que mora o `aplicar_atualizacao.ps1`, que é
**justamente o arquivo que o caminho do `.cgu` usa**. O conserto do atualizador viajava
dentro da atualização que o atualizador não conseguia aplicar: **saída impossível por
dentro**, e é por isso que o `.cmd` era a única saída — e ele precisava ser consertado
primeiro.

**O CONSERTO SÃO QUATRO PEÇAS, e nenhuma delas é «pedir elevação»:**

1. **A pergunta vem antes de oferecer o botão** — `update_manager.pode_aplicar_sozinho`
   grava um arquivo de teste na pasta da instalação e o apaga, em Python, antes de a tela
   oferecer a aplicação. Sem permissão, **o botão não aparece e a frase diz o motivo e o
   caminho**: pelo `ATUALIZAR_SISTEMA.cmd`.
2. **O `.ps1` mede antes de parar o serviço** — a primeira coisa que ele faz é gravar
   `.teste_de_escrita_*.tmp` na instalação. Se não der, **ele recusa com o serviço no ar** e
   diz «NADA FOI ALTERADO». Antes, o serviço era parado **primeiro** e a recusa vinha
   depois: a pior ordem possível, porque quem lê precisa saber que o sistema está de pé.
3. **Erro de programa de fora virou código de saída** — `Rodar()` cerca `robocopy` e `pip`,
   e o log passa a dizer **qual** comando falhou e com que código, em vez da palavra
   genérica que não dizia onde parar de procurar.
4. **O `.cmd` leva a pasta `installer` e confere que chegou** — e compara o `ps1` com o da
   origem (`fc /b`), porque **um `ps1` velho na pasta é exatamente o que fez a tela mentir
   desde 09/09**.

**E a tela agora diz a verdade.** Quando não puder aplicar sozinha, ela diz **por quê** —
«o sistema roda de uma pasta que não é a instalada», «não há `install.json` para saber qual
é a pasta», «a conta X não pode gravar em C:\Program Files» — e aponta o `.cmd`. Era o
relato que o senhor fez sem saber: **a tela dizia que atualizava e o log dizia acesso
negado.**

**APLICADO E CONFERIDO — 15/09/2026, 17h41:**

| | antes | depois |
|---|---|---|
| `VERSAO.txt` no servidor | 3.6.130 | **3.6.131** |
| `installer\aplicar_atualizacao.ps1` | 4.348 bytes (13/08) | **9.600 bytes (15/09 17:24) — hash igual ao da árvore** |
| documentos na pasta | 3 | **263** |
| `CLAUDE.md` | ausente | **411.348 bytes** |
| arquivos na instalação | 811 | **1.078** |
| o servidor | — | **HTTP 200, versão 3.6.131** |

> **E fica uma conferência para o senhor, que é a que prova o conserto:** na próxima
> atualização, use **a tela de atualizações** com o `.cgu`. Se ela recusar, **leia o motivo
> na tela** — ele agora aparece. Se ela aplicar, o log tem de terminar em «Atualizacao
> concluida». O `.cmd` continua de pé como caminho de emergência, e não como o único.

---

## 4. COMO CONFERIR QUE SUBIU

**O pacote desta versão, medido por dentro do arquivo fechado — e não pelo que o
empacotador disse:**

| | |
|---|---|
| arquivo | `C:\Users\<usuario>\Downloads\CartorioGestao_3.6.131.cgu` |
| tamanho | **9.000.612 bytes** (9,0 MB), medido por dentro do arquivo |
| arquivos | **818** no manifesto **e 818** dentro do zip |
| documentos | **170** `.md` sob a `DOCUMENTACAO` — **163 na raiz**, que são os que a ajuda indexa e procura, e 7 em subpasta (os modelos do RTDPJ) · **263** arquivos no total, com os anexos |
| as regras | **`CLAUDE.md` presente** |
| o lixo de quem edita | **zero** — nenhum `.bak`, `.new`, `=ro`, `.original` nem PDF solto |
| os modelos do RTDPJ | **os três intactos** (o filtro do PDF é só da raiz, e não os tirou) |
| **SHA-256** | **vai na mensagem que acompanha o pacote** |

> **POR QUE O SHA NÃO ESTÁ AQUI DENTRO, e isso não é descuido.** Este roteiro viaja
> **dentro** do `.cgu`; escrever o hash do pacote no documento que o pacote carrega é o
> ovo e a galinha — assim que eu corrijo uma linha daqui, o arquivo muda e o número
> impresso passa a mentir. **E o pacote não é reproduzível byte a byte**: o zip guarda a
> data de modificação de cada arquivo, de modo que dois empacotamentos do mesmo conteúdo
> dão hashes diferentes. O número que vale é o do arquivo que o senhor tem na mão, e é
> por isso que ele vai na mensagem — **carimbo que mente é pior que carimbo nenhum**, e um
> hash desatualizado é o carimbo que mente na forma mais convincente: um número de verdade,
> só que de outro arquivo.

> **Perguntar ao empacotador o que ele levou mediria a intenção, e não o pacote**: a
> contagem acima foi feita abrindo o `.cgu` e lendo o zip. É a diferença entre «o
> `iter_files` devolve isto» e «isto está dentro do arquivo que o senhor vai aplicar».

Depois de aplicar (`SERVIDOR\ATUALIZAR_SISTEMA.cmd`, com UAC — é dele):

| # | o que conferir | se não estiver assim |
|---|---|---|
| 1 | a janela imprime **«Documentos do projeto atualizados.»** e **«Regras da casa atualizadas.»** | imprimiu `ATENCAO:` — a pasta de origem está incompleta |
| 2 | `C:\Program Files\CartorioGestao\CLAUDE.md` existe | a ajuda não vai saber como se decide aqui |
| 3 | `C:\Program Files\CartorioGestao\DOCUMENTACAO` tem **mais de 160** `.md` | tinha 3 antes; se continuar 3, a cópia não foi |
| 4 | `VERSAO.txt` do servidor diz **3.6.131** | a atualização não subiu |
| 5 | na tela de ajuda, pergunte **«o que a casa decidiu sobre o selo do casamento?»** | a resposta tem de vir **com a decisão desta casa** (um selo só, emitido na habilitação) e não com a regra geral |
| 6 | pergunte **«o que a casa escreveu sobre a impressora do molde?»** | tem de achar `ROTEIRO_3.6.65.md` — é a busca por dentro dos documentos |
| 7 | na consulta, abra **os passos**: cada ferramenta usada aparece, com o argumento e o tamanho do que voltou | é o rastro de que ela leu, e não de que ela achou |
| 8 | `installer\aplicar_atualizacao.ps1` no servidor tem **9.600 bytes** | se tiver **4.348**, o atualizador da tela continua o de 13/08 — e a tela de atualizações volta a mentir |

---

## 5. O QUE ESPERA DECISÃO DELE

1. **Abrir a ajuda ao balcão, ou não.** Hoje ela é do ADMIN, e abrir é uma caixa em
   Administrativo → Configurações (`aj_config.perfis`), sem programador no meio. As oito
   ferramentas de leitura já são as do balcão; o que muda é quem alcança a tela.
2. **O que «atualizar sozinha» quer dizer.** A pergunta está aberta desde 14/09 e **eu não
   a respondo por adivinhação**: o que já se mede sozinho é o **mapa** (telas, arquivos e
   tabelas desta instalação); o que **não** se atualiza é o texto. O que o senhor quer que
   ela saiba sem ninguém escrever: o mapa das telas, o `CLAUDE.md`, ou um resumo do que
   mudou de uma versão para a outra?
3. **A segunda economia do contexto.** A lista dos relatos são **6.336 caracteres** em toda
   pergunta. Ela pode virar índice (número, título e situação) com o texto vindo só quando
   pedido — como ficou o índice dos documentos. **Não fiz porque muda o comportamento da
   resposta**, e quem decide isso é o senhor.
4. **Os cinco testes vermelhos do Registro Civil** — o item 6. Eles são de outra passada e
   são **testes velhos**, e o senhor precisa saber que existem se um dia a suíte inteira
   rodar.

---

## 6. O QUE ESTAVA VERMELHO, E NÃO ERA DESTA PASSADA — medido

Cinco testes falham em `tests/test_rc_modelos_do_livro.py` e
`tests/test_modelos_elementos.py`: a contagem do catálogo de modelos (querendo 3 teores,
havendo 4), a espécie `LIVRO_E` que não está na lista que o teste monta à mão, e o nome do
assento que o teste espera entre aspas.

**A pergunta da casa é «esta falha é minha?», e ela se apura medindo — não na memória.** O
teste que decidi usar é mais forte que a data do arquivo: **troquei o `rc_modelos_do_livro.py`
da árvore pelo que está NO SERVIDOR** (a versão que está no ar desde 09/09) e rodei os dois
arquivos de teste:

> **os mesmos cinco falharam**, com 71 passando.

**Logo não é regressão de hoje: é o que já estava, e ninguém tinha visto porque a suíte não
roda com o que está no servidor** — os testes não viajam no pacote. Os testes desses arquivos
são de **07/09 18:08** e **11/09 13:43**, e os contratos que eles cobram mudaram depois
(`LIVRO_E` entrou na 3.6.72, de 08/09; os quatro teores do RCPJ/RTD e as peças da certidão
em PDF entraram na 3.6.98, de 11/09).

**Não os consertei**: é módulo de outra passada, e a regra de 02/09 é «quem não está
construindo o módulo não mexe nele». Ficam **declarados, com o nome de cada um**, para
serem cobrados de quem os escreveu.

---

## 7. ARQUIVOS DESTA PASSADA

**Novos**

| | |
|---|---|
| `docs/tecnico/ROTEIRO_3.6.131.md` | este roteiro |
| `ajuda_regras.py` | as regras da casa ao alcance da ajuda: seções, procura e carimbo |
| `tests/test_ajuda_regras.py` | os testes dele, incluindo o do pacote que leva o arquivo |
| `tests/test_pacote_nao_leva_lixo.py` | o pacote não leva `.bak`, `.new` nem `=ro` — e continua levando o programa. **Depois do defeito de hoje ele ganhou o terceiro teste**: o par das duas funções do empacotador sai na mesma ordem |

**Mexidos**

`agente_ferramentas.py` (as duas ferramentas novas: `procurar_nos_documentos` e
`ler_regras`; e o tratamento de erro das ferramentas passou a apanhar **todo** erro de regra,
que é `ValueError` nesta casa) · `ajuda_projeto.py` (a busca dentro dos documentos; a
primeira frase saiu do índice; as notas do desenvolvimento entram no «o que mudou») ·
`tests/test_ajuda_projeto.py` · `tools/criar_atualizacao.py` (o filtro das cópias — e a lista
das pastas ignoradas passou a vir **do sistema**, para não haver duas) ·
`SERVIDOR/ATUALIZAR_SISTEMA.cmd` (os documentos, as regras **e a pasta `installer`**, com
conferência) · `update_manager.py` (as três perguntas antes de aplicar: é Windows, é a pasta
instalada, dá para gravar) · `installer/aplicar_atualizacao.ps1` (mede a escrita **antes** de
parar o serviço; erro de programa de fora passou a ser código de saída) ·
`templates/updates.html` (a tela diz **por que** não pode aplicar) ·
`tests/test_update_approval.py` · `tests/test_atualizacao_permissao.py` (**novo — 15 testes**,
o conserto do caminho do `.cgu`) ·
`notas_do_desenvolvimento.py` (a nota do relato #26) · `app.py` e `VERSAO.txt` (3.6.131) ·
`CLAUDE.md` (a versão, os números do contexto, **a contagem das ferramentas, que este
arquivo dizia «treze» e são quinze** — corrigida com a data e o motivo — e, já à noite, o
carimbo dos testes, que dizia 5.983 e são **6.003**, mais o bloco novo sobre o caminho do
`.cgu` e a pasta `installer`).

---

## 8. A SUÍTE DO QUE SE MEXEU

**Os doze arquivos de teste da ajuda, do agente e do pacote rodaram inteiros: 266 passaram,
zero falhou**, em 6 minutos e 10 segundos — medido depois deste roteiro existir, que é o que
fecha o vermelho do item 5 do § 5 (o teste quer que o roteiro da versão que roda esteja
escrito; era ele o único vermelho da passada).

**Rodaram de novo no fim, e o número mudou porque o trabalho não parou:** a medição anterior,
de 263, foi feita antes de eu escrever as duas seções que o § 3 ganhou depois — e o
`test_pacote_nao_leva_lixo.py` cresceu de dois testes para quatro no intervalo, um deles
nascido do defeito de hoje. **Número de suíte vale com a hora ao lado**, e por isso os dois
aparecem: 263 às 13h, 266 às 14h.

**E a fatia do atualizador rodou depois do conserto, separada:** os três arquivos que guardam
o caminho da atualização — `test_atualizacao_permissao.py`, `test_update_approval.py` e
`test_pacote_nao_leva_lixo.py` — **22 passaram, zero falhou, em 47,33 s**.

**E o carimbo foi conferido contra a coleta, que é o que o § 3 passou a exigir de mim:**
`pytest --collect-only` conta **6.003 em 8,92 s**, contra os **5.983** que o `CLAUDE.md`
dizia. **Quinze dos vinte novos são deste conserto** (`--collect-only` no
`test_atualizacao_permissao.py` dá 15); as outras cinco eu não atribuo, porque há uma segunda
passada escrevendo nesta árvore. O número foi corrigido lá, com a hora e a medição ao lado —
e é a **terceira** vez no mesmo dia que esta linha envelhece.

**A suíte inteira não rodou**, por ordem de 31/08: ela roda quando o senhor pedir. E fica
dito o que ela traria: **os cinco vermelhos do § 6**, que não são desta passada.

---

## 9. DE QUEM É CADA ARQUIVO DESTA ATUALIZAÇÃO

Medido antes de fechar, porque **duas passadas escrevem esta árvore** e quem aplica precisa
saber de onde vem cada coisa se sair torto. O pacote levaria **819 arquivos**; trocaria
**16** no servidor e criaria **289** (quase todos os documentos que nunca chegaram lá).

**Os 16 que trocam:**

| arquivo | escrito na árvore | quem |
|---|---|---|
| `agente_ferramentas.py` · `ajuda_projeto.py` · `app.py` · `VERSAO.txt` · `notas_do_desenvolvimento.py` · `tools/criar_atualizacao.py` | hoje | **esta passada** |
| `rc_modelos_do_livro.py` · `caixa_depositos.py` · `caixa_web.py` · `templates/base.html` · `templates/caixa_depositos.html` · `templates/caixa_protocolo.html` · `templates/notas_cartao.html` | hoje | **a outra passada** |
| `ATUALIZAR_DA_V3.txt` (11/09) · `installer/aplicar_atualizacao.ps1` (01/09) · `docs/tecnico/GUIA_RI_IMPORTAR_MATRICULAS.md` (14/09) | dias anteriores | já era para estar lá |

**O que isso quer dizer, sem rodeio:** esta atualização **não leva só a ajuda** — leva
também o que a outra passada escreveu hoje no caixa, no selo e no RI. Foi ela que decidiu
empacotar agora? Se o senhor preferir levar **só a ajuda**, o caminho é aplicar depois de a
outra passada parar; o `.cgu` não sabe recortar.

> **E uma coisa que o senhor precisa saber, porque ela morde na próxima vez:** **o conserto
> do atualizador não está dentro deste `.cgu`.** O pacote fechou às **16h55** e o
> `aplicar_atualizacao.ps1` novo é das **17h24** — ele viajou pelo `.cmd`, que é o caminho que
> copia a pasta `installer`. **Não é defeito: é a ordem dos fatos**, e o próximo pacote é o
> primeiro que já nasce com ele dentro.
>
> **A consequência prática:** se o senhor aplicar este `.cgu` pela tela, o payload **repõe o
> `ps1` de 01/09** por cima do novo — porque é ele que está dentro do pacote. **A conferência
> 8 do § 4 é justamente para isso**: se depois de aplicar a tela o `ps1` voltar a ter 4.348
> bytes, rode o `ATUALIZAR_SISTEMA.cmd` e ele o repõe. **Conferir depois de aplicar é o que
> substitui confiar na ordem das coisas** — e a ordem, hoje, é esta.

---

## 10. MEMÓRIA GRAVADA (para quem retomar)

- `ajuda-le-as-regras-da-casa` — o `CLAUDE.md` ao alcance da ajuda, e o carimbo conferido
- `a-primeira-frase-do-indice-saiu` — a economia, com os números antes e depois
- `o-pacote-leva-os-documentos-e-o-claude-md` — os dois caminhos de instalação
