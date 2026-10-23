# Roteiro da 3.6.79 — o selo gratuito e a filiação da CRC

> Empacotada em 10/09/2026, por ordem do oficial («empacote»), depois de dois
> relatos dele no mesmo dia.

**Ela é pequena e resolve duas coisas que já estavam custando.** Nenhuma
depende de decisão sua para funcionar; as duas mudam telas que você usa hoje.

---

## O que aplicar

**O pacote:**

| | |
|---|---|
| arquivo | `C:\Users\<usuario>\Downloads\CartorioGestao_Update_3.6.79.cgu` |
| exige no mínimo | **3.3.0** — logo ele sobe por cima de qualquer versão que esteja aí, e **basta este**, sem aplicar 3.6.76, .77 e .78 antes |
| arquivos | **700**, e **zero** de `tests/`, `output/`, `tmp/` ou cache de ferramenta |

**O SHA-256 vai na entrega, e não escrito aqui** — este roteiro **viaja dentro
do pacote**, e um arquivo não pode conter o próprio hash: escrevê-lo obrigaria
a reempacotar, o hash mudaria, e a cópia que chega ao servidor afirmaria um
número que não é o do pacote que a levou. **Carimbo que mente**, na forma mais
boba, a da referência circular.

Para conferir na sua máquina:

```bash
certutil -hashfile "C:\Users\<usuario>\Downloads\CartorioGestao_Update_3.6.79.cgu" SHA256
```

**E o pacote foi lido de volta antes de ser entregue**, e não só criado: a
leitura provou, byte a byte, que os arquivos que mudaram estão dentro e iguais
à árvore, que **o conserto do selo gratuito foi**, que a explicação do
cabeçalho voltou à tela, que `VERSAO.txt` diz 3.6.79, e que **nenhum** arquivo
de `tests/`, `output/`, `tmp/` ou cache de ferramenta entrou — o defeito da
3.6.49, quando 15 arquivos e 347 KB de `.pytest_cache` viajaram até o balcão.

Ou, pelo caminho da cópia direta:

```bash
"C:\Users\<usuario>\Downloads\CartorioGestao\SERVIDOR\ATUALIZAR_SISTEMA.cmd"
```

Pede Administrador, para o servidor, copia e sobe de novo. Depois, **Ctrl+F5**
no navegador — senão o `app.css` velho fica no cache.

---

## 1. O selo gratuito da certidão — «na última o selo que era pra ser gratuito foi pago»

**Eram duas coisas, as duas eram defeito, e as duas saem neste pacote.**

**O DEFEITO DO ENVELOPE SAI AGORA — e eu havia escrito aqui que ele já estava
instalado. Estava errado, e a correção é minha.** Abri os sete pacotes um a um
antes de fechar este: `ato_selado.envelope_do_civil` manda **só**
`isentoGratuito` em **todos**, inclusive na 3.6.78 de hoje às 10h42. O campo
`isento` entrou na árvore **depois** dela, e é a **3.6.79 que o leva**.

**Carimbo que mente sobre um conserto é pior que o defeito**, porque quem lê
para de procurar: você leria «já instalado», tentaria emitir a certidão
gratuita numa versão que não tem o conserto, e concluiria que o conserto não
funciona.

**O que era:** marcar «Selo gratuito» mandava ao selador `isentoGratuito:
"GRATUITO"` e **sem o campo `isento`**, que é o que o contrato dele declara.
O aparelho não reconhecia, o selo não vinha, e a certidão ficava lavrada **sem
selo** — as certidões 16, 17 e 23 do assento 1233, três tentativas, duas
canceladas, e **nenhuma folha de segurança consumida**, porque a folha só se
gasta se o selo sair.

**E ele está medido em três fontes**, não deduzido: o contrato do selador não
tem `isentoGratuito` em schema nenhum (o campo é `isento`); o acervo registra
`DadosSeloCertidaoRI.isento` com **667 usos** reais desta casa; e a palavra
`GRATUITO` aparece em **zero dos 26.177 selos** que a serventia emitiu. Mais a
prova contra o próprio aparelho: em 08/09 a averbação do CPF passou com
`isento = true` (HTTP 200, «Selo Isento»), e a forma que falhou foi a do
`isentoGratuito` sozinho — **a correção de 08/09 foi aplicada à averbação e não
à certidão**.

**Isto não prova que o aparelho aceita a certidão**, e nada aqui poderia
provar: pedir selo de verdade gasta selo, e isso é do balcão. **A confirmação é
uma certidão gratuita emitida por você depois de aplicar** — e é a primeira
coisa da lista de conferência.

**O selo pago não foi defeito: foi a regra que você deu em 09/09.** O assento
do Pessoa Exemplo veio do **ARQUIVO** e o registro de 1996 nunca foi selado aqui;
`eh_primeira_certidao_do_registro` devolve `False`, e o caminho passa a ser
`/selo/civil/nascimento/segunda-via`, que é pago.

**O que esta versão traz: a tela deixa de cobrar calada.** Antes de emitir, ela
diz se o selo vai ser cobrado e por quê — e no assento importado sem selo de
registro ela avisa, em faixa amarela, que será tratado como **segunda via** e
que **sem marcar «Selo gratuito / isento» o selo sai pago**.

**A presunção de segunda via fica** — decisão sua de 09/09, mantida em 10/09
(«resolva»): o sistema não tem como saber se a pessoa já tirou a primeira via
em 1996. Das duas hipóteses, cobrar por engano se desfaz; deixar de cobrar o
que era devido, não.

---

## 2. A filiação da CRC — «estão saindo sem preencher os pais»

**Estavam. Medido na produção: 24 filiações de 420 não subiam, e nada dizia.**

`_filiacao` exige nome **e** sexo — a regra é da CRC e está certa —, mas
faltando o sexo ela devolvia vazio e **o bloco inteiro se perdia**, com o nome
do genitor gravado no sistema. O arquivo saía bem formado e incompleto, e **a
Central o aceitaria**.

São duas coisas, com providências diferentes:

| | |
|---|---|
| **14** | a carga do acervo **não trouxe a mãe**. O nome está no livro de papel |
| **10** | a pessoa existe e **o sexo está vazio** — era esta que doía |

E uma **não é falta**: no assento 70 o pai **chama-se «IGNORADO»**, que é como
o acervo escreve «não declarado». Esse sai da lista pela palavra, com a mesma
régua da lavratura (`rc_assento.e_declarado_ausente`).

**Agora nada se perde calado:**

```
entram no XML: 210     retidos: 0     a arrumar: 20
filiações: 189 registros com 2, 18 com 1, 3 com 0
```

A tela da carga ganhou uma segunda lista — **«sobem incompletos»** — com o nome
de quem falta e um botão que leva **direto** à tela que tem os campos
(`/rcpn/<id>/editar`). Antes ele levava à ficha, que só mostra.

> **E EU QUASE TRAVEI 20 REGISTROS VÁLIDOS.** A primeira versão punha a
> filiação entre as faltas que **retêm** o registro. Seis testes que já
> existiam ficaram vermelhos, e a medição explicou: **o manual não põe a
> filiação entre os obrigatórios do nascimento** — são `NOMEREGISTRADO`,
> `MATRICULA`, `DATAREGISTRO` e `SEXO`. Travar seria mais severo que a norma, e
> deixaria vinte registros válidos sem nunca chegar à Central.
>
> São duas listas com consequências diferentes: `o_que_falta` **retém**;
> `o_que_arrumar` **deixa subir e avisa** — que é o que você pediu.

**O sexo não se preenche sozinho** — sua decisão de 10/09: *«deixa sexo em
aberto para quem estiver lavrando arrume»*. A CRC aceita «ignorado», e eu
perguntei se a tela devia oferecer marcá-lo; você disse que não. «Ignorado» é
uma **declaração** de que ninguém sabe, e quem a faz é quem tem o livro na mão.
Há varredor que guarda isso: `crc_carga.py` **mede e avisa, e não escreve**.

---

## Como conferir que subiu certo

| onde | o que tem de aparecer |
|---|---|
| qualquer tela, no pé | **3.6.79** |
| Registro Civil → um assento importado → certidão | faixa **amarela** dizendo «Este selo será COBRADO — segunda via», com a razão |
| Registro Civil → um assento lavrado aqui → certidão | «Este selo é gratuito — primeira via», com o número do `REGNAS…` |
| **emita uma certidão marcando «Selo gratuito / isento»** | **o selo SAI, e a folha de segurança é consumida** — é a prova de que o envelope novo passou pelo aparelho |
| Registro Civil → CRC → marcar assentos → conferir | a segunda lista, **«20 registro(s) sobem incompletos»**, com nomes |
| a lista dos incompletos → «corrigir o assento» | abre `/rcpn/<id>/editar`, e **não** a ficha |

**Se a faixa do selo não aparecer, a atualização não subiu.**

---

## O que esta versão NÃO faz

**Não marca sexo sozinho** — sua decisão, ver acima.

**Não retém registro por falta de filiação** — o manual não a exige.

**Não muda o caminho do selo.** A certidão de assento importado continua indo
por `segunda-via`; o que mudou é que a tela **diz** antes.

**Não mexe no cabeçalho dos atos** — decisão sua de 07/09, «para manter a forma
e diminuir o risco de ir errado».

---

## AS NOVE FALHAS DO PORTÃO, APURADAS UMA A UMA

**Eu não empacoto sobre falha que não sei de onde veio.** A fatia larga que
rodei antes de fechar este pacote — **300 testes, 30m07s** — voltou com **9
vermelhas**, e o pacote ficou parado até cada uma ter nome, dono e data.
**E depois apareceram mais três**, no submódulo de modelos, que aquela fatia não
cobria — as três estão na seção seguinte, e as três estão consertadas.

**Uma era minha, e está consertada. As outras oito são de uma segunda passada
que trabalha nesta mesma árvore, e cada uma foi datada dentro do pacote em que
a mudança nasceu** — não pelo que eu me lembro, e não pela data do arquivo em
disco, que hoje está toda misturada.

| teste | de quem | provado em |
|---|---|---|
| `test_aviso_do_selo_da_certidao::test_o_veredito_concorda_com_quem_sela` | **minha** | **consertada** — o meu ajudante repetia a `origem_chave` no laço, e `rc_assentos` tem `UNIQUE(origem, origem_chave)`. Um contador resolveu; **as 9 passam** |
| `test_rc_termo_tela::test_quem_assina_sai_da_regra_viva` | outra passada | **3.6.76** (09/09, 18h17) — e a mudança é **pedido seu de 09/09**: o termo passou a sair com o nome de **quem está lavrando**, e não com a substituta. O teste é de 31/08 e ainda cobra a regra antiga |
| `test_rc_termo_tela::test_espécie_sem_modelo_avisa_na_tela_em_vez_de_estourar` | outra passada | **3.6.72** (08/09, 11h01) — o **termo do Livro E** foi construído. O teste afirma que a interdição não tem modelo, e ela passou a ter |
| `test_atribuicoes_web::test_assento_novo_vai_para_o_livro_da_especie_e_nao_para_o_escolhido` | outra passada | **3.6.76** — lavrar passou a **exigir que se escolha a folha de segurança** («ela não se escolhe sozinha»). O teste lavra sem escolher |
| `test_atribuicoes_web::test_abrir_registro_novo_com_selo_de_outra_serventia_nao_deixa_registro` | outra passada | **3.6.76** — a mesma exigência da folha: o assento para antes de chegar ao selo, e o aviso que o teste espera não sai |
| `test_atribuicoes_web::test_a_carga_roda_de_verdade_e_mostra_os_numeros` | outra passada | `acervo_carga.py:636`, `no such column: a.intCodigoPessoa` |
| `test_ato_selado::test_toda_tabela_que_as_telas_selam_esta_registrada` | outra passada | `rg_web.py` sela numa tabela de `ato_id` que não está em `TABELAS_DE_ATO` — é o módulo do **título do RCPJ/RTD**, que ela está construindo hoje |
| `test_funcao_sem_tela::test_nenhuma_funcao_nova_fica_sem_tela` | outra passada | quatro órfãs, todas em arquivos dela: `escapar_xml` (`rc_certidao_inteiro_teor.py`) e três em `papel_seguranca.py` |
| `test_funcao_sem_tela::test_a_lista_de_conhecidas_nao_vira_deposito` | outra passada | `a_entregar`, `carregar` e `esquema_por_tabela` já ganharam tela e continuam em `JA_SABIDAS` |

**E EU NÃO CONSERTEI AS OITO, DE PROPÓSITO.** A regra desta casa, escrita em
02/09 depois de duas passadas se atropelarem nos arquivos do WhatsApp: **quem
não está construindo o módulo não mexe nele** — mede, relata, e deixa quem tem
o contexto na mão. Naquele dia eu consertei por cima e fui sobrescrito cinco
minutos depois, e **um teste meu ficou afirmando um contrato que já não
existia**.

**Cinco das oito são exatamente isso: teste que afirma o contrato antigo depois
de você ter mandado mudar a regra.** Consertá-los de fora é escolher, no lugar
de quem construiu, o que a regra nova quer dizer.

**A segunda passada empacotou 3.6.76, 3.6.77 e 3.6.78 com essas oito
vermelhas** — logo ela sabe delas, e não está parada por causa delas.

---

## E DEPOIS APARECERAM TRÊS, NO MEU PRÓPRIO MÓDULO

A fatia larga não cobria `tests/test_modelos_elementos_web.py` — o submódulo de
modelos que você pediu em 07/09. **Rodei aquele módulo à parte antes de fechar
o pacote, e ele voltou com três vermelhas.** Elas passavam quando eu o
entreguei.

**A tela do submódulo foi REESCRITA na 3.6.75** (08/09, 18h02), pela segunda
passada: ela ganhou lista à esquerda, editor com **prévia** à direita, busca, e
o corpo de cada elemento passou a aparecer só com um documento **aberto**
(`/ri/modelos?editar=…`). Antes ela listava tudo de uma vez. Datado abrindo os
pacotes: a **3.6.72** tem a minha tela, de 133 linhas; a **3.6.75** tem a dela,
de 63.

**A tela nova é melhor que a minha** — a prévia lado a lado é justamente o que
falta a quem escreve modelo. O que ela perdeu foi informação:

| a vermelha | o que era | o que eu fiz |
|---|---|---|
| «a tela diz que o cabeçalho não está ali» | **a explicação da SUA decisão de 07/09 saiu da tela** — «cabeçalho dos atos vamos deixar num ajuste separado para manter a forma» | **reposta**, em duas linhas |
| «a tela diz de onde o texto veio» | a palavra mudou: «Herdado de Registro de Imóveis» onde dizia «herdado da atribuição» | **o teste passou a cobrar a palavra de hoje** |
| «o que se grava na tela geral aparece no submódulo» | o endereço virou índice; o corpo mora no editor | **o teste passou a abrir o documento** |

**A PRIMEIRA NÃO ERA TESTE VELHO: ERA PEÇA PRONTA QUE NINGUÉM USA, dentro do
modelo de tela.** `modelos_elementos_web.py` **nunca parou** de entregar
`cabecalho_de_fora` à tela — a rota manda a explicação em toda chamada, e a
tela reescrita deixou de mostrá-la. Sem ela, quem abrisse o submódulo procuraria
o cabeçalho, não o acharia, e concluiria que o sistema tem defeito — quando o
que existe é uma decisão sua. **Campo que some sem explicação faz procurar
defeito onde há decisão.**

**E A PROMESSA QUE MAIS IMPORTA CONTINUA DE PÉ — medida, e não suposta.**
«Duas portas, um armazém»: gravei pela tela geral (Administrativo → Modelos) e
fui conferir nos três lugares — **uma** linha em `mo_elementos`, o submódulo
mostrando, e `modelos_da_casa.corpo_de` imprimindo no papel. Se ela tivesse se
partido em duas, seria o relato #12 de volta na pior forma: **duas telas para a
mesma coisa, uma perdendo em silêncio**.

**Os 44 testes do submódulo passam.**

---

## UM ACHADO QUE ESPERA VOCÊ: A CERTIDÃO POSITIVA DE PROTESTO

**Você não alcança o texto dela na tela de editar modelos**, e a negativa sim.
Achado em 10/09/2026 pelo guarda do catálogo, ao conferir o pacote.

O catálogo de modelos passou de 16 para **22 papéis** na 3.6.75 (08/09), com as
seis certidões que faltavam — Livro 3, RCPJ, RTD e as três do Protesto. Cinco
entraram com o texto dentro. A **positiva de protesto** entrou assim:

```
MODELO_CERTIDAO_POSITIVA = "{cabeca} {corpo}"
```

**Dezesseis caracteres, e duas palavras — as duas são marcadores.** A frase que
a certidão de fato afirma —

> «CERTIFICO …, que revendo em meu Cartório, os livros de Registros de
> Protestos de Letras e Outros Títulos, a partir do ano de … até a presente
> data, neles **encontrei protesto contra** …»

— é montada **dentro da função** que emite a certidão, e por isso não chega ao
catálogo. Você abre *Modelos → Certidão positiva de protesto* e vê `{cabeca}
{corpo}`.

**A ASSIMETRIA É O QUE PROVA O DEFEITO.** Na **negativa** a frase está no
modelo, e você a edita:

> «CERTIFICO, …, que revendo nesta Serventia os Livros de Registro de
> Protestos …, neles **NÃO ENCONTREI** protesto contra …»

Duas certidões da mesma família, e só uma editável — e a que não é editável é a
**positiva**, que é o papel que faz o banco negar crédito.

**É O MESMO DEFEITO QUE EU COMETI EM 01/09**, e o guarda do catálogo existe por
causa dele: eu havia posto o termo do protesto como `{base} {posteriori}
{edital}`, 28 caracteres, com a frase do art. 9º-A invisível e ineditável. O
guarda me pegou naquele dia e pegou este agora.

**E EU NÃO CONSERTEI, de propósito — e não é a regra de não mexer em módulo de
outrem.** Mover a frase da função para dentro da constante muda **como um papel
assinado se compõe**, e o texto de uma certidão positiva é afirmação sobre a
vida de crédito de uma pessoa. **Quem escreve isso é quem assina.** A decisão é
sua, e são duas:

1. **o texto da positiva vira modelo editável** — igual à negativa; ou
2. **fica como está**, e a tela passa a dizer que aquele papel se monta no
   módulo e não se edita ali.

**O guarda ficou vermelho se alguém consertar sem tirar a chave da lista** — é
a forma do teto de portabilidade: declaração que sobrevive ao defeito é o
carimbo que mente.

**Uma observação menor, no mesmo lugar:** a certidão **de cancelamento** tem a
mesma cabeça-marcador, mas dela você alcança o fecho do art. 26, que está
escrito no modelo. Eu a havia declarado junto com a positiva, e **o próprio
guarda me desmentiu** — ele exige que o declarado seja esqueleto de verdade, e
ali há dezessete palavras suas para editar.

---

## O QUE MAIS VAI NESTE PACOTE, ALÉM DO MEU

**O pacote leva a árvore inteira, e não o meu recorte** — é assim que o `.cgu`
funciona, e é por isso que ele é o desfazer do projeto. Medido contra a
**3.6.78**, arquivo por arquivo, por hash:

**Meu (9 arquivos):** `rc_certidao.py`, `atribuicoes_web.py`, `crc_carga.py`,
`app.py`, `VERSAO.txt`, e as telas `atrib_rcpn_ficha.html`,
`rc_certidao_previa.html`, `rcpn_crc.html`, `base.html`.

**Da segunda passada (16 arquivos):** `ato_selado.py`, `etiqueta.py`,
`impressao_pdf.py`, `rc_certidao_odt.py`, `rc_pedidos.py`,
`rc_pedidos_web.py`, `rg_web.py`, `selos_emitidos.py`, um molde novo de
certidão de óbito, e sete telas — entre elas as **etiquetas de selo externo do
RCPJ/RTD**, que ela escreveu **às 13h08 de hoje**, minutos antes de eu fechar
este pacote.

**Isto não é um aviso de defeito: é o que eu não medi.** O trabalho dela
compila, o sistema sobe, e as telas dela abrem — foi o que eu conferi. **O que
eu não conferi é se aquele módulo está terminado**, porque não é meu e ela
ainda estava escrevendo nele. Se a etiqueta de selo externo do RCPJ/RTD sair
torta, é dali que vem, e o conserto é a versão seguinte — não este pacote de
volta.

---

## O carimbo do CLAUDE.md continua atrasado, e é honesto dizer

A primeira linha dele diz **3.6.65** e **4.337 testes**. A versão está certa
agora no `app.py` e no `VERSAO.txt`; **o número de testes não se atualizou**,
porque atualizá-lo exige a **suíte inteira** rodada, e nesta passada rodou uma
**fatia larga: 300 testes em 30m07s** — as da CRC, as do aviso do selo, as dos
modelos e os varredores da casa. Trezentos não são quatro mil e trezentos.

**Contado, e não somado**: enquanto a suíte inteira não responder, o número
antigo fica, com esta nota ao lado. Somar de cabeça daria um número parecido e
não medido — e o carimbo diria o que ninguém conferiu.
