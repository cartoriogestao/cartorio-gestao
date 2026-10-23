# A FILA DO LIVRO 3 — as ferramentas que o Livro 2 tem e ele não

    «deixe o livro 3 com as mesmas ferramentas do livro 2»
    «Coloque todos esses itens do livro 3 na fila para fazer imediatamente
     depois de resolver a cnib»
                                        — o oficial, 20/09/2026

**ESTA FILA É ORDEM DELE, E TEM PRECEDÊNCIA**: assim que o CNIB estiver
resolvido, é por aqui que se segue — antes de qualquer outra frente.

---

## O tamanho do buraco, medido

Contado em 20/09/2026, nas duas fichas, pelos `url_for` de cada modelo de tela:

| | ações na ficha |
|---|---|
| Livro 2 (`ri_ficha.html`) | **29** |
| Livro 3 (`atrib_livro3_ficha.html`) | **19**, mais 5 telas próprias — eram **2** em 20/09/2026 |

---

## O que já saiu

**3.6.153/3.6.154 — o selo do ato**, que foi o que o relato pegou. Duas
portas, como no Livro 2: o selo automático ao lavrar e o botão «selar este
ato» para o que nasceu sem. Ver `ra_selo.py` — o caminho e o envelope são
**medidos no acervo**, nos 17 envelopes que nomeiam o Livro 3-AUX.

**3.6.155 — a minuta** (item 1 da fila). `ra_minutas` + `ra_minuta.py`, com as
três situações, o número **pretendido** e não reservado, o descarte com motivo
escrito, a marca de lavrada **na mesma transação do ato** e uma fila própria
no menu. Mais a **ponte com o que já existia**: as minutas de cancelamento dos
registros 1.198 e 1.243 moravam em `rascunhos_de_tela` — a do 1.243 virou a
AV-01 e continuou lá, como se ainda esperasse alguém —, e há um **botão** que
as traz (não migração calada: quem decide é quem escreveu o texto).

**3.6.156 — as PARTES do registro, que não estavam na fila e apareceram pelo
balcão.** Relato do oficial em 21/09: *«fui tentar selar o ato do 1243 e deu:
Os nomes das partes devem ser informados. não tem campo para partes»*. A
tabela `ra_partes` existia **desde que o Livro 3 nasceu e nenhuma tela escrevia
nela** — vazia nos 14 registros. É o defeito de costume desta casa pelo avesso:
não é função sem tela, é **tabela sem tela**. Junto veio o **devolver o ato à
minuta**, que era o item 6 da fila (expurgar com rastro) na forma que ele
pediu.

**3.6.157 — os itens 2, 4, 5 e 7, por ordem dele:** *«termine o
desenvolvimento do livro 3, falta várias coisas que temos no livro 2»*.

  * **notas de revisão** (`ra_revisoes` + `ra_revisao.py` + fila no menu). A
    nota **não trava nada**; baixar exige escrever o que se decidiu; e ela
    alcança **a minuta**, o que a do Livro 2 não faz — é lá que ela se lê,
    antes de o ato existir. Os pisos e as palavras são **lidos de
    `ri_revisao`**, e há teste que compara os dois: duas cópias divergiriam no
    primeiro conserto, e a casa passaria a exigir coisas diferentes em dois
    livros;
  * **corrigir o registro**, com lista declarada de campos e o **antes e o
    depois na auditoria**. O número, o livro, a situação e a origem **não se
    editam** — eles dizem onde o ato está no livro;
  * **descancelar**, com motivo escrito, **sem apagar a averbação** que
    cancelou;
  * **renumerar** na ordem de lavratura, **recusando ato que já tem selo** —
    o selo carrega o número do ato dentro dele, e não se reescreve.

**3.6.158 — A FILA FECHOU.** Os itens 3 e 6, mais as duas coisas que
faltavam fora dela e a que ele mandou acrescentar:

  * **a pré-visualização «como ficará»** — o registro com a minuta no fim, com
    o número que o ato *teria* (a numeração contínua, e não o
    `numero_pretendido`) e a marca `RASCUNHO — ATO NÃO LAVRADO` **em três
    lugares, nenhum deles um botão**: ela continua na impressão, porque quem
    imprime pode entregar;
  * **a ata de ocorrência** do ato desfeito, em `.odt`. Ela nasce **na mesma
    transação** do «devolver à minuta» e guarda o **teor inteiro** — a
    auditoria responde «quem e quando»; a correição pergunta «o que estava
    escrito naquele ato», e essa resposta só existe aqui;
  * **a ficha do registro em `.odt`**, com o modelo no catálogo da casa
    (`RI_LIVRO3_FICHA`, formato de chaves) — editável pelo oficial, como a
    certidão do Livro 3. **E ela não se parece com certidão**: sem fecho, sem
    «confere com o original» e sem assinatura de oficial, com o rodapé dizendo
    que é a ficha impressa e não certifica nada;
  * **conferir a ficha** contra a digitalização, com a marca guardando **quem
    e quando** — e desmarcar não apaga o carimbo de quem conferiu antes;
  * **a digitalização**, por ordem dele no mesmo dia: *«digitalizacao de
    imagens deve ter igual ao livro 2»*. Subir, ver na tela, baixar, miniatura
    e o **histórico** da varredura anterior. As regras de arquivo são **lidas**
    do módulo do Livro 2; o que muda é a tabela — e **uma coisa a menos, o
    ONR**, porque o índice que o país consulta é de imóvel e este livro
    registra título de crédito. Pasta própria (`livro3/registro-1243`), porque
    os números dos dois livros se cruzam.

**3.6.159 — A CERTIDÃO, E O DEFEITO QUE ELA ESCONDIA.** Ordem dele:
*«mesmas balizas para emissão de certidão, teor do registro principal, falta
coisa»*.

  * **A certidão do Livro 3 OMITIA AS AVERBAÇÕES.** O teor trazia o registro e
    mais nada — e a tela **oferecia escolhê-las**: o operador marcava, e elas
    eram ignoradas em silêncio. Uma certidão do registro 1.243 sairia
    reproduzindo a cédula **sem dizer que ela foi integralmente cancelada**
    pela AV-01. Agora entram, com rótulo e data; as marcadas, e **todas**
    quando não se marca nenhuma. O claro `{atos}` é **aditivo**: modelo já
    ajustado no catálogo continua valendo;
  * **as balizas que faltavam**: `validade_ate` (30 dias, art. 53 do Código de
    Normas — a certidão daqui saía **sem prazo nenhum**), o **documento** do
    requerente (nome sozinho tem homônimo) e **quem assinou por extenso**
    (`emitida_por` guarda o login, e «mario» não responde «quem assinou
    isto?»). O número dos 30 dias é **lido** de `ri_schema`, e não repetido;
  * **a digitalização do TERMO** — *«precisa ter digitalização do termo»*. Não
    é a varredura da ficha: é o papel daquele ato (o instrumento de baixa, a
    procuração, o aditivo). Duas colunas e duas pastas, porque guardar as duas
    no mesmo lugar faria a segunda apagar a primeira.

---

## A fila, na ordem em que eu faria

A ordem é por **quanto custa não ter**, e não por tamanho.

### ~~1. A MINUTA~~ — FEITA na 3.6.155

*(o que segue é o que estava escrito antes de ela sair, e fica porque é a
medição que a justificou)*

### 1. A MINUTA — o ato em pé para revisar antes de lavrar

No Livro 2 é `ri_minutas`, com `A_REVISAR | LAVRADA | DESCARTADA`, criada em
15/09/2026 porque uma importação lavrou três atos que deviam estar esperando
revisão. **O Livro 3 tem meia peça**: a ficha já mostra um bloco «Minuta a
revisar e selar» que sai de `rascunhos_de_tela`, com a chave
`livro3_minuta_av` — é um rascunho de tela usado como minuta, sem situação,
sem número pretendido e sem descarte com motivo escrito.

**Por que é o primeiro:** é o que impede o ato nascer errado, e o Livro 3 já
tem o caso real (a averbação que voltou a minuta por ter sido lavrada sem
selo).

### ~~2. AS NOTAS DE REVISÃO~~ — FEITA na 3.6.157

*(a decisão de esquema foi **tabela própria**: em `ri_revisoes` as duas chaves
estrangeiras apontam para `ri_matriculas` e `ri_atos`, e chave estrangeira que
só vale às vezes não vale)*

`ri_revisoes`, de 15/09/2026. Hoje as duas chaves estrangeiras apontam para
`ri_matriculas` e `ri_atos`, então **não dá para reusar sem mexer no esquema**:
ou a tabela ganha um par livro/registro, ou nasce a irmã do Livro 3. A decisão
de qual é parte do trabalho, e ela se toma medindo, não escolhendo por gosto.

### ~~3. O «COMO FICARÁ»~~ — FEITA na 3.6.158

**O rascunho em si deixou de fazer falta**, e isso é medição e não opinião: a
**minuta** do Livro 3 já é «o ato escrito e ainda não lavrado», com situação,
descarte com motivo e os campos do selo dentro — construir `ra_rascunhos` ao
lado seria uma segunda gaveta para a mesma coisa.

**O que continua faltando é a outra metade**: a pré-visualização da ficha
**com o ato novo dentro**, com a marca `RASCUNHO — ATO NÃO LAVRADO` em três
lugares, nenhum deles um botão — ela continua na impressão, porque quem
imprime pode entregar.

### ~~4. EDITAR O REGISTRO~~ — FEITA na 3.6.157

No Livro 2, `ri_editar_matricula`. No Livro 3 o que a carga trouxe do acervo
**não tem por onde ser corrigido** — e a ficha do 1.243 traz, dentro do próprio
campo de condições, uma divergência de data que o importador declarou e mandou
conferir contra o livro de papel. Hoje não há tela que deixe resolver isso.

### ~~5. RENUMERAR~~ — FEITA na 3.6.157

`ri_renumerar_matricula`. O Livro 3 numera contínuo com o registro (depois do
R-1 vem o AV-2) e **não tem conserto de numeração** — o que, num livro com 14
registros vindos do acervo, é questão de tempo.

### ~~6. A ATA DE OCORRÊNCIA DO EXPURGO~~ — FEITA na 3.6.158

**Desfazer com rastro já existe** desde a 3.6.156: `livro3_ato_para_minuta`
devolve o ato à minuta com as três recusas (ato com selo, ato do meio, ato com
dinheiro no caixa) e deixa a linha na auditoria.

**O que falta é a ATA**: no Livro 2, `ri_expurgos` guarda a ocorrência e a
imprime em `.odt`, que é o papel que a correição lê. Aqui o rastro existe e o
papel não.

### ~~7. REABRIR~~ (descancelar) — FEITA na 3.6.157

`ri_reabrir_matricula`. O Livro 3 tem `situacao` (`ATIVO`/`CANCELADO`) e o
cancelamento é uma averbação — **reabrir não existe**, e o caso de cancelar por
engano existe em qualquer livro.

---

## O que ficou de fora, e por quê

**Nada da fila.** O que o Livro 2 tem e este não tem, depois da 3.6.158:

  * **organizar as páginas soltas** (`ri_organizar_imagens`, `ri_imagem`) — no
    Livro 2 elas são as 11.251 páginas que o E-Ofício varreu ficha a ficha, e
    aqui **não existe nenhuma**: a digitalização do Livro 3 nasce com o
    arquivo oficial único, que é o desenho novo. Construir a gaveta das
    páginas soltas seria construir para um acervo que não existe;
  * **o ONR** — indicador real, indicador pessoal, Next Cloud SAS e o CNM. São
    do **imóvel**, e o Livro 3 registra título de crédito. `ra_registros.cnm`
    existe e está vazio nos 14; se ele deve ou não ser preenchido é **pergunta
    ao oficial**, e não trabalho a fazer.

---

## O que NÃO entra nesta fila, e por quê

- **Certidão** — o Livro 3 já emite, por `atrib_certidao`, com os textos
  medidos nas 6 certidões de `LivroAuxiliarCertidao`.
- **Cobrança** — já existe na ficha, pelo mesmo quadro do resto da casa.
- **Alerta de fraude** — já está no alto da ficha.
- **ONR, indicador real, indicador pessoal, CNM** — são do
  **Livro 2**: o índice que o país consulta é de imóvel, e o Livro 3 registra
  título de crédito. `ra_registros.cnm` existe e está vazio nos 14; se ele deve
  ou não ser preenchido é pergunta ao oficial, e não trabalho a fazer.

> **E A DIGITALIZAÇÃO SAIU DESTA LISTA EM 21/09/2026, POR ORDEM DELE** —
> *«digitalizacao de imagens deve ter igual ao livro 2»*. Ela estava escrita
> aqui como coisa do Livro 2, e deixou de ser: `ra_digitalizacao.py` nasceu na
> **3.6.158**, lendo do Livro 2 as regras de arquivo (extensões, hash, nome
> seguro, histórico). **O que continua de fora é só o ONR**, e por isso as duas
> colunas dele não vieram junto — ver `ra_schema.MIGRACOES`.
>
> **E ELA FICOU MEIA TELA ATÉ 21/09 À NOITE**, quando ele relatou: *«na 1243
> não tem digitalização da ficha»*. O envio existia e morava **só na tela de
> conferir** — um clique adiante, atrás de um botão que diz outra coisa —, e a
> **miniatura não tinha chamador nenhum**, que é «função pronta que nenhuma
> tela chama», o defeito mais repetido desta casa. No Livro 2 as duas estão na
> própria ficha, e foi lá que ele foi procurar. Agora estão aqui também.
>
> **E o que ele viu na 1.243 tinha uma segunda razão, maior**: o servidor está
> na **3.6.156**, e a digitalização do Livro 3 nasceu na 3.6.158. Naquela
> máquina não havia o que aparecer — em registro nenhum dos 16.

---

## A régua que vale para todos eles

O Livro 3 **não é o Livro 2 com outro nome**, e três coisas medidas mostram
onde eles divergem — quem copiar tela por tela vai errar nas três:

1. **a numeração é contínua com o registro** (R-1, AV-2, AV-3), e não duas
   séries;
2. **o cancelamento é uma averbação** — o registro fica na ficha, com a
   averbação dizendo que foi cancelado e por quê;
3. **o selo leva `livro: 3` e `registroAverbacao: 0`**, e o campo chamado
   «matrícula» carrega a frase `AV - 1 do Registro 1243`. Medido.

---

## A CERTIDÃO POR REPRODUÇÃO DA DIGITALIZAÇÃO — 21/09/2026

Ordem dele, no mesmo dia: *«siga desenvolvimento»*, depois de a digitalização
da ficha aparecer onde ela devia estar.

**O LIVRO 2 EMITE DE DOIS MODOS, E ESTE SÓ TINHA UM.** Lá a certidão de inteiro
teor sai pelo **texto** do teor ou por **reprodução** da varredura da ficha;
aqui só havia o texto. E a diferença não é de conforto: há registro cujo teor
veio do acervo **sem teor nenhum** — medido em 21/09/2026: os registros
**1.315 e 1.560**, cédulas de crédito rural, com zero caractere no registro e
no R-1. Para esses a certidão por texto é **recusada** (a cópia se tira do
livro físico), e a reprodução da varredura é o caminho que eles passam a ter.

**O QUE FICA GRAVADO NÃO É O TEXTO DO REGISTRO.** O teor da certidão por
reprodução é o resumo — quantas folhas, e o sha256 do arquivo reproduzido.
Gravar o texto faria o banco afirmar um teor que a via impressa não traz, e é
o banco que alguém vai ler daqui a dez anos para saber o que se certificou.

**A CÓPIA CONGELA, E A PASTA É DO LIVRO 3.** A certidão guarda uma cópia do
arquivo como ele estava: varrer a ficha de novo amanhã não muda a via que saiu
hoje. E a pasta é `livro3/certidoes/<id>`, e não a do Livro 2 —
`ri_digitalizacao.pasta_snapshot_certidao` chaveia por `certidao_id` sozinho, e
`ri_certidoes` e `at_certidoes` são **tabelas com sequências de id
independentes**: a certidão 7 do Registro de Imóveis e a 7 daqui cairiam na
mesma pasta, e a segunda apagaria a varredura que a primeira congelou. É a
régua do selo — **a chave é a tabela mais o id** —, pela terceira vez neste
projeto.

**O QUE O MÓDULO RECUSA, E ONDE:**

| a recusa | onde ela acontece |
|---|---|
| reprodução sem varredura na ficha | **antes de qualquer escrita** — com o cliente ainda na frente, e não uma certidão numerada que depois não se imprime |
| reprodução no RCPJ/RTD | no domínio: **só o Livro 3 tem varredura de ficha**; lá o que se guarda é o documento *apresentado*, que é o papel do cliente e não a folha do livro desta casa |
| reimprimir reprodução **cancelada** | na impressão: a certidão por texto sai com «CERTIDÃO CANCELADA» no alto, e esta é composta das folhas do livro — não há onde carimbar sem escrever por cima. Na mão de quem recebe, ela seria indistinguível de uma válida |

**E A OPÇÃO SÓ APARECE QUANDO HÁ ARQUIVO.** Medido em 21/09/2026: **0 dos 16**
registros deste livro têm varredura, logo hoje o padrão é o texto em todos eles
— e passa a ser a reprodução ficha a ficha, à medida que o balcão varre. Opção
que se pode escolher e que recusa depois faz o balcão descobrir o buraco com o
cliente na frente; é a lição que o Livro 2 pagou em 16/09/2026, quando
`DIGITALIZACAO` fixo no código recusou **toda** certidão de inteiro teor da
casa.

**O PAPEL É O MESMO DO LIVRO 2** — `ri_digitalizacao.odt_da_digitalizacao`, e
não um segundo montador: duas versões do papel que reproduz o livro
divergiriam no primeiro conserto. Ele leva as folhas, o carimbo do selo (quando
há selo) e **a linha de quem expediu** — sem ela o papel terminaria na última
folha do livro, sem ninguém assinando embaixo.

---

## O SELO DA CERTIDÃO DO LIVRO 3 — 21/09/2026

**ELA NUNCA SELOU SOZINHA, E HAVIA CAMINHO MEDIDO.** O comentário da própria
rota dizia que *«só o RCPJ/RTD tem o caminho genérico medido; o Livro 3
continua como estava — sem regressão, porque nunca selou automático também»*.
A medição do acervo desmentiu.

| medido em 21/09/2026 | |
|---|---|
| certidões do Livro 3 no acervo (`LivroAuxiliarCertidao`) | **9** |
| delas com selo de `/selo/imovel/certidao` no protocolo geral | **9** — prefixo `CERIMV` |
| delas com a coluna `Selado` preenchida | **0** — a amarração é pelo **protocolo**, e não pela linha da certidão |
| protocolos em que **não há outro caminho nenhum** | **2** (`2020.06.48` e `2020.07.35`) |

São esses dois que fecham a leitura: nos outros o protocolo carrega também
prenotação e ato declarado, e um `CERIMV` ali poderia ser de uma certidão de
matrícula emitida no mesmo atendimento. **Naqueles dois não há segunda certidão
possível a que aquele selo pertencesse.**

**E O ESTRAGO MAIOR NÃO ERA O SELO: ERA O DINHEIRO.** `at_certidoes` serve
**duas** atribuições — RCPJ/RTD e Livro 3 — e os dois atos se chamam
`CERTIDAO`: o par (tabela, tipo) não os separa. Até hoje o mapa devolvia o
caminho do RTD/PJ para os dois, **e o comentário ao lado dele já dizia que o
Livro 3 é do Registro de Imóveis** — a regra estava escrita e não valia. Como a
receita de custas sai do **caminho**, a ficha do Livro 3 oferecia ao balcão os
itens do grupo **15** (RTD/PJ) onde esta casa cobrou os do **16.24**:

| o que a ficha oferecia | o que a casa cobrou |
|---|---|
| `15.10.1` · `15.10.2` · `15.7.1` · `15.5.2` · `15.22` | `16.24.1` · `16.24.4` · `16.24.4.1` · `16.24.2` · as buscas `16.25.x` |

**A espécie separa o que a tabela não separa** — no civil ela é a espécie do
assento; aqui é a atribuição. Sem ela não há como saber de que livro é a
certidão, e devolver o caminho errado é pior que devolver nada.

**O ENVELOPE É O DO RI, e não um parecido** — `envelope_da_certidao_do_ri`,
medido em 667. O código do item sai da **tabela** (`16.24.4`, «certidões de
inteiro teor, ônus e de ações reais»), e a procedência fica marcada:
`PROCEDENCIA_DO_CAMINHO_DA_CERTIDAO = "MEDIDO"` e
`PROCEDENCIA_DO_CODIGO_DA_CERTIDAO = "TABELA"`. MEDIDO é o que a casa mandou;
TABELA é o que a norma diz, e confundir os dois apaga a procedência dos dois.

**SEM REQUERENTE VAI O QUE SE CERTIFICA, NA PALAVRA DESTE LIVRO.** No RI a casa
mandou `MATRICULA 1116`; aqui a coisa certificada chama-se **registro**, e é
assim que este livro a escreve no envelope do próprio ato (`AV - 1 do Registro
1332`, medido nos 17). A forma é a mesma, a palavra é a deste livro — e fica
declarado que ela é **derivada**: não há envelope de certidão do Livro 3 no
acervo para medir o texto da parte.

**A QUANTIDADE É O NÚMERO DE FOLHAS**, como nos 667. Na certidão por
**reprodução** ela é contada do arquivo; na de texto vale uma, que é o que a
casa manda quando não tem como contar.

**E SELO QUE NÃO SAI SUSPENDE A CERTIDÃO** — a regra do oficial, a mesma do RI
e do RCPJ/RTD. Isto é mudança de comportamento no Livro 3: até hoje a certidão
saía sem selo e ficava valendo. O campo de digitar o selo à mão continua, e
quando ele vem preenchido o caminho automático não pede outro.

---

## O QUE FICA DECLARADO E NÃO CONSERTADO

**`ato_selado.selos_do_ato` está definida DUAS VEZES** — linhas 2118 e 2527 —,
e **a segunda é a que vale**. As duas leem a mesma coisa; o que muda é a
ordenação (`id` contra `obtido_em`), e `obtido_em` tem **dois formatos** nesta
casa (`2020-03-19 14:21:03` da carga e `2026-09-01T14:17:06` deste sistema). O
efeito prático hoje é nenhum, e a duplicata **é anterior a esta passada** —
está assim na 3.6.159. Não mexi: a correção é apagar uma definição num módulo
que outra passada também escreve.

### E A CERTIDÃO DE MAIS DE UMA FOLHA SÃO DOIS SELOS

Medido nos mesmos 667 envelopes, agrupados pelo protocolo:

| o que saiu no protocolo | protocolos |
|---|---|
| `16.24.4` **+** `16.24.4.1` (inteiro teor + folha acrescida) | **99** |
| `16.24.1` **+** `16.24.2` (certidão comum + folha acrescida) | **94** |
| `16.24.4` sozinho | **44** — e a quantidade é **1** nos 44 |
| `16.24.1` sozinho | **44** |

E a quantidade diz o resto: **o item base vai sempre com 1** (uma exceção em
99), e quem carrega o número é o item da **folha acrescida** — 1, 2, 3, até 12.
A casa não mandou «inteiro teor, quantidade 5»: mandou «inteiro teor, 1» **e**
«folha acrescida, 4». A tabela diz a mesma coisa com todas as letras — o
`16.24.4.1` chama-se «por folha acrescida além da primeira».

**São 92 dos 667 envelopes com mais de uma folha**, e o sistema mandava uma,
sempre. Agora a tela do Livro 3 pergunta quantas folhas, e o selo sai em dois
itens quando há mais de uma — **cada um com a sua própria referência**, que é
de onde sai o SID: uma referência só para dois itens faria o aparelho devolver
o mesmo selo duas vezes.

**E NA REPRODUÇÃO AS FOLHAS SÃO CONTADAS DO ARQUIVO**, e não digitadas. Na
certidão por texto quem informa é quem atende: deduzir o número de folhas do
tamanho do teor seria inventar o que só se sabe depois de imprimir.

---

## E O MESMO DEFEITO ESTAVA NO LIVRO 2 — consertado em 21/09/2026

**A certidão do RI selava sempre UMA folha, e o campo que diria outra coisa não
existia.** `ri_web.py` lia `int(request.form.get("folhas") or 1)` e **nenhum
modelo de tela desta casa mandava `folhas`** para aquela rota — os únicos
`name="folhas"` estavam nas telas das Notas. É *argumento sem quem o passe*, a
mesma família do defeito que travou o CNIB inteiro: o varredor de função órfã
não o pega, **porque a função tem chamador**.

**O tamanho está medido**: dos 667 envelopes de certidão, **92** cobraram mais
de uma folha, até doze — e, pelo par acima, a conta certa nem era a quantidade
no item base.

Ordem dele no mesmo dia — *«siga arrumando o que precisa»* —, e por isso a
correção entrou nos dois livros:

  * o campo **Folhas da certidão** nasceu na ficha da matrícula, ao lado do
    protocolo;
  * a regra dos itens mora **num lugar só**, `ato_selado.itens_da_certidao_do_ri`
    — o Livro 3 a chama, em vez de ter a sua cópia: o caminho é o mesmo e a
    tabela é a mesma, e o que diverge aqui é a conta que o cliente paga;
  * **a referência do primeiro item não mudou** (`ri_certidoes:<id>`), e é dela
    que sai o SID: trocar a forma faria o aparelho vender selo novo onde antes
    devolvia o mesmo. O item da folha acrescida, que é novo, leva a sua.

**E folha que não é número não derruba a certidão já gravada**: vale uma, que é
o padrão da casa — um `int()` solto ali daria HTTP 500 depois de o ato existir.

---

## O QUE FICA DECLARADO, E É DA OUTRA PASSADA

**`tests/test_ato_selado.py::test_obter_selo_abre_transacao_propria_e_nao_usa_a_do_ato`
está vermelho, e não é desta passada.** Hoje, às 12h55, nasceu `nome_humano.py`
e `selar_o_ato_lavrado` passou a **recusar** selo quando o escrevente tem cara
de robô («a sessão parece robô/máquina e a substituta/oficial não está
cadastrada»). O teste é anterior e passa um usuário assim. Medido: a frase não
existe no pacote 3.6.159, e `nome_humano.py` é de hoje. **Não mexi** — é da
passada que está construindo aquilo, e ela tem o contexto na mão.

E foi a mesma passada que pôs `import nome_humano as NOMEHUM` fora de ordem no
topo de `ato_selado.py` (o `I001` que o lint acusa naquele arquivo).

## O PAPEL DA CERTIDÃO POR TEXTO, IGUAL AO DO LIVRO 2 — 23/09/2026

    «emiti uma certidao de livro 3 e saiu dois selos»
    «e falta o selo na averbacao»
    «e falta cabecalho do cartorio na certidao. deixe igual a certidao
     equivalente do livro 2»                               — o oficial

**Os dois selos da certidão 1/2026 estão certos.** Ela foi emitida com duas
folhas: `CERINT…` é o item 16.24.4 (R$ 101,88) e `CERELE…` é a folha acrescida
16.24.4.1 (R$ 10,14). O prefixo `CERELE` não é «certidão eletrônica»: medido no
acervo, **121 de 121** selos do item 16.24.4.1 saíram com ele.

**O selo da AV-1 existia e o papel não o imprimia**, e o cabeçalho da casa era
calado porque a rota procurava «REPÚBLICA FEDERATIVA» no teor — e no registro
1.243 essa frase está **no meio**, dentro da página do E-Ofício que o registro
reproduz. O papel do Livro 3 por texto passou a ser montado por
`atribuicoes_web._papel_da_certidao_do_livro3`, peça por peça como o do Livro 2:
o cabeçalho da casa no cabeçalho de cada página, **o selo de cada averbação logo
abaixo dela** (`atrib_certidao.blocos_por_ato`), o fecho «Era o que nela
continha.», a finalidade, a validade do art. 53, a data **da emissão** e quem
expediu — o nome e o título, sem o branco da caneta (ordem de 22/09 e decisão de
23/09, as mesmas do Livro 2).

**Nada disso está no teor.** O teor congelado não muda uma letra — há teste que
confere que os trechos juntos são o teor inteiro e que o hash não muda ao
imprimir —, e por isso a certidão 1/2026, que já saiu, ganha o selo e o
cabeçalho na próxima impressão. O RCPJ/RTD continua como estava.

**DECLARADO, E NÃO RESOLVIDO: o papel novo da 1/2026 tem TRÊS páginas, e ela foi
cobrada por DUAS folhas.** Medido no ensaio contra cópia da produção: o
cabeçalho, o selo da AV e o fecho empurram os dois carimbos da certidão para uma
terceira página, sozinhos. Quantas folhas cobrar é decisão do oficial — o sistema
cobra o que o balcão informa no campo «Folhas da certidão».
