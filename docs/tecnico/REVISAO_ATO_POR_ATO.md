# Revisão ato por ato das seis atribuições — começada em 25/08/2026

É o passo 6 da ordem combinada com o oficial: depois de a estrutura das seis
atribuições estar construída e testada, passar em cada uma perguntando **o que
o balcão não consegue fazer**.

A pergunta não é "o código está certo?" — o suíte de testes já responde isso. É
**"quem está no guichê consegue terminar o atendimento?"**. Tudo o que foi
achado no primeiro dia passava em todos os testes: eram funções de domínio
prontas, testadas, e que nenhuma tela chamava.

---

## 1. O Protesto não sabia quem é o devedor

### O que estava errado

A carga do acervo trazia os 1.366 títulos e **nenhum devedor**. A tabela
`pt_devedores` ficava vazia, e a ficha do título dizia, em texto:

> Sem devedor cadastrado. No acervo antigo isso acontece: o E-Ofício guardava
> o devedor noutra tabela, e a carga traz só o que veio junto.

Guardava mesmo — em **`tbPessoa`**, apontada por `tbAvisoProtesto.
intCodigoPessoa`. A carga passava ao lado dela.

### Por que isso é grave

**A certidão de protesto se pede pelo nome e pelo CPF de quem foi protestado.**
É a pergunta do guichê: "fulano tem protesto?". Com `pt_devedores` vazia:

- a busca da lista não achava ninguém por nome nem por documento;
- uma certidão gerada dali diria que a pessoa está limpa quando não está.

É o mesmo raciocínio que fez os sete títulos sem número **entrarem** marcados
em vez de serem rejeitados: certidão que mente é pior que carga que rejeita.

### O que se mediu antes de escrever

| | |
|---|---|
| Títulos com `intCodigoPessoa` | 1.366 de 1.370 |
| Resolvem em `tbPessoa` | **1.366 — 100%** |
| Pessoa física (`strTipoPessoa='F'`) | 980, com 11 dígitos em `strCIC` |
| Pessoa jurídica (`'J'`) | 386, com 14 dígitos em `strCGC` |
| Sem documento nenhum | **0** |
| Sem nome | **0** |
| Sem endereço | 16 |
| Cedente (`intCodigoCedente`) que resolve | 908 de 1.366 |

**O tipo diz onde está o documento**, e não o tamanho do que está escrito:
`'F'` traz o CPF em `strCIC` e `'J'` traz o CNPJ em `strCGC`, sem uma única
exceção nas 1.366 linhas. Onde o tipo não vier, vale a coluna em que o
documento está — que é leitura, e não dedução pelo comprimento.

### O que foi feito

- `acervo_carga.carregar_protesto` lê `tbPessoa` por `LEFT JOIN` — duas vezes,
  uma para o devedor e uma para o cedente. `LEFT` e não `INNER`: título sem
  cedente ainda é título, e não pode sumir da carga por uma ligação quebrada.
- O devedor entra por uma **passada à parte**, e não pelo `depois` da linha.
  `_executar` só chama o `depois` de quem **entrou agora**; quem já tinha
  rodado a carga antes desta data teria os títulos gravados como `repetidos`
  e o devedor nunca chegaria neles. A passada olha o que **falta**, serve aos
  dois casos com um caminho só, e pode rodar quantas vezes precisar.
- A lista do Protesto passou a **procurar pelo devedor** — nome e documento —
  e a mostrar quem ele é. Antes procurava só nas colunas de `pt_titulos`.

### O que a carga agora informa, além de rejeitados e avisados

`Carga.contar()` guarda fatos medidos que valem para a carga inteira, e não
para uma linha. Transformar cada um deles num aviso de linha afogaria os 7
avisos que são de linha de verdade. No acervo real:

| Fato | Quantos |
|---|---|
| devedores trazidos do acervo | 1.366 |
| títulos sem cedente em `tbPessoa` no acervo | 458 |
| títulos em que o acervo traz o mesmo cedente e devedor | 28 |
| devedores sem endereço no acervo | 16 |

Os 28 em que cedente e devedor são a mesma pessoa são o acervo dizendo que
quem apresentou é quem foi protestado — o que não acontece na vida real, e
provavelmente é digitação do começo do E-Ofício. **A carga copia o que está
lá e conta**; corrigir por conta própria seria inventar.

> **CORREÇÃO DE 29/10/2026 — o cedente desta seção estava errado.**
> `intCodigoCedente` é chave de **`tbCedente`**, e não de `tbPessoa`: os dois
> são espaços de id diferentes, e no mesmo número `tbPessoa` traz outra pessoa.
> Os «908 que resolvem», os «458 sem cedente» e os «28 com o mesmo cedente e
> devedor» mediam esse engano. Medido na produção: dos 1.409 títulos do acervo,
> nenhum tinha o credor certo — 488 vazios e 921 com o nome de outra pessoa.
> A carga passou a ler o cedente em `tbCedente`, com o **nome do registro da
> CRA** (`tbSDT.Campo04`), que é o que o E-Ofício imprimia no aviso (1.673 de
> 1.675) e na certidão (25 de 25). Ver `acervo_carga._cedente_do_titulo`.

---

## 2. O apontamento não existia na tela

### O que estava errado

`protesto.lancar_apontamento` existe desde o levantamento do Protesto e tem
teste. **Nenhuma tela o chamava.** A ficha do título oferecia intimação,
protesto, desistência, pagamento e cancelamento — e a rota `/protesto/<id>/
lancar` conhecia esses cinco.

O apontamento é o **primeiro ato da vida do título** — Lei 9.492/1997, art. 3º.

### Por que ninguém tinha visto

Porque sobre o acervo o buraco não aparece: **os 1.366 títulos do acervo já
vieram apontados** do E-Ofício. Medido:

| Situação no acervo | Quantos |
|---|---|
| PROTESTADO | 1.104 |
| PAGO | 189 |
| CANCELADO | 56 |
| APONTADO | 21 |
| **RECEBIDO** | **0** |

Nenhum título do acervo está em `RECEBIDO`, que é a única situação em que o
apontamento cabe. O defeito só se manifesta no **título novo** — e abrir
título novo também não existia. Os dois buracos se escondiam um ao outro.

### O que foi feito

`APONTAMENTO` entrou na rota e na lista do que cabe, quando a situação é
`RECEBIDO`. A regra de quem pode apontar continua no domínio: quem recusa
apontar de novo é `protesto.lancar_apontamento`, e há teste que manda o pedido
duas vezes para ver a recusa.

---

## 3. Abrir registro NOVO, nas quatro atribuições

Era o primeiro item do ajuste fino combinado com o oficial. Até aqui as quatro
telas só lançavam ato em registro **que já existia**: título, assento e
registro novos só entravam pela carga do acervo.

| Tela | O que faz | O que ela recusa, e quem recusa |
|---|---|---|
| `/protesto/novo` | cadastra título apresentado no balcão | o contrato da CRA (`conferir_titulo`): espécie, número, datas, valor, saldo, praça e ao menos um devedor com documento **e endereço** |
| `/rcpn/novo` | lavra assento de nascimento, casamento, óbito | `rc_assento`: espécie fora do catálogo, assento sem nome |
| `/rcpj-rtd/novo` | abre registro de PJ ou de título e documento | `rg_registro`: série que não é de RCPJ nem de RTD |
| `/livro3/novo` | registra título do art. 178 | `ra_registro`: natureza fora do catálogo do Livro 3 |

**As três últimas selam e cobram na hora**, com as mesmas peças do lançamento
de ato: `_selar_se_pedido`, `_cobrar_se_pedido` e a macro `quadro()` de
`_cobrar.html`. O ato de `REGISTRO` nasce junto com o registro e é selável e
cobrável como qualquer outro; deixar a cobrança para depois faria o operador
voltar à ficha, e ato lavrado e não cobrado é receita que some.

**O Protesto é a exceção, e é de propósito**: `cadastrar_titulo` não lavra ato
nenhum. O título entra `RECEBIDO`, e o apontamento — que tem lugar no livro,
número de ordem, selo e custas próprios — é o ato seguinte, na ficha. Juntar
os dois numa tela só faria o balcão apontar sem querer, e apontamento não se
desfaz.

### As decisões que a medição resolveu

**A espécie do título vem ordenada pelo uso desta casa**, e não em ordem
alfabética. Medido nos 1.366 títulos:

| | | | |
|---|---|---|---|
| DMI 911 | CDA 353 | CBI 62 | DSI 16 |
| DM 6 | ATC 6 | NP 4 | CTI 4 |
| SJ 3 | FPS 1 | | |

Dois terços são DMI. As 64 espécies do contrato continuam todas disponíveis —
isto ordena a lista, não a restringe. `ATC` e `CTI` **não estão no esquema
oficial da CRA**, e continuam aceitas com observação, como
`protesto_cra.ESPECIES_FORA_DO_ESQUEMA` já dizia.

**A praça vem preenchida com a cidade da serventia** — 1.360 dos 1.366 títulos
do acervo dizem CIDADE EXEMPLO. **O motivo vem em "falta de pagamento"** —
1.155 dos que trazem motivo. É a regra do oficial de 24/08: na dúvida, faça
como já foi feito antes.

**O saldo NÃO é copiado do valor.** Nos 102 títulos que não vieram da CRA, 31
têm saldo diferente do valor de face, porque o saldo traz juros e encargos.
O saldo é o que a certidão diz e o que o devedor paga: preenchê-lo sozinho
poria o protesto no valor errado. Os dois campos são obrigatórios e separados.

**A espécie manda na série no RCPN, e a série é escolhida no RCPJ/RTD.** Não é
incoerência: no Registro Civil o fato decide o livro (nascimento no A, óbito
no C), e deixar escolher seria deixar lançar óbito em livro de nascimento; no
RCPJ/RTD é a natureza jurídica do que se registra que decide, e quem a conhece
é quem está atendendo. A **atribuição**, essa, nunca se pergunta: vem da série,
em `livro_nucleo.SERIES`.

---

## 4. O passo 5 do roteiro não tinha onde acontecer

### O que estava errado

`ROTEIRO_3.6.0.md`, passo 5, e `ENSAIO_25_08_2026.md` dizem a mesma coisa:

> Antes de lavrar o primeiro protesto e o primeiro pagamento, informe o
> próximo número de cada um **pela tela de numeração**.

**Essa tela não existia.** O núcleo inteiro — `escrituracao.py`, 41 KB, os 24
livros — não tinha uma única rota. Abrir livro, encerrar livro, inutilizar
folha, encerrar o dia e **corrigir o contador** eram funções de domínio
testadas que nenhuma tela chamava.

`escrituracao.fixar_numeracao` existe desde o núcleo, recusa baixar o contador
abaixo do maior número já usado, e ninguém tinha por onde chamá-la.

### Como apareceu

Perguntando, para cada módulo de domínio, **quais funções públicas nenhuma
tela chama**. É a mesma pergunta que achou o apontamento, feita de uma vez
para o projeto inteiro em vez de módulo a módulo.

### E havia mais um pedaço solto

A tela da carga (`/atribuicoes/importar`) percorria `resultado.items()` para
montar a tabela — e `numeracao` vem no mesmo dicionário **com outra forma**
(`semeadas` e `pendentes`, e não `lidos`/`inseridos`). Ela caía na tabela como
uma linha chamada "numeracao" com todas as células **vazias**, e o quadro da
numeração — que o roteiro chama de "o passo seguinte" — não aparecia em lugar
nenhum.

### O que foi feito

- **`/atribuicoes/numeracao`**, em *Demais atribuições → Numeração dos livros*,
  só ADMIN e gerente: os 24 livros do núcleo agrupados por atribuição, com o
  maior número em uso, o próximo, de onde o contador veio, quem o informou e
  por quê. As duas séries que o acervo não sabe informar aparecem em vermelho,
  no alto, com o motivo.
- **O GET não consome número.** `proximo_numero(..., consumir=False)` não
  escreve nada; tela de conferência que consome contador fica presa no
  `busy_timeout` enquanto outro balcão lavra, e devolve 500 na cara do
  escrevente. Há teste que abre a tela e confere que `nu_numeracao` continua
  vazia.
- **A tela da carga passou a mostrar o quadro da numeração** — semeadas de um
  lado, pendentes de outro, com o botão que leva à tela de numeração — e
  parou de renderizar `numeracao` como se fosse uma carga.
- A tela da carga também mostra o que a rodada **contou** (`Carga.contagens`),
  além de rejeitados e avisados.

**Séries de numeração diária não têm contador a corrigir**, e a tela diz isso
em vez de oferecer um campo que não faz nada: o Livro de Protocolo do Protesto
reinicia sozinho a cada dia, e o número sai do livro do dia.

---

## 5. O resto do núcleo — livros, termos e o encerramento do dia

O passo 4 tapou o buraco mais urgente do núcleo, e deixou o resto à vista:
`escrituracao.py` continuava com **uma** rota, e as outras seis funções de
escrituração seguiam sem tela.

### O que faltava, e o que cada coisa custa

| Função de domínio | O que ela é | O que custava não ter tela |
|---|---|---|
| `abrir_livro` | livro novo, com termo de abertura | livro cheio e nenhum jeito de abrir o seguinte — o balcão para |
| `encerrar_livro` | termo com a faixa de números, a última folha usada e as inutilizadas | é o papel que prova que nada sumiu entre um livro e o próximo |
| `inutilizar` | face em branco, com motivo e termo | folha em branco no meio do livro, que a correição lê como ato arrancado |
| `encerrar_o_dia` | termo diário do livro de protocolo | a inspeção de 12/08/2026 cobrou isso de Protesto e de RCPJ |
| `dias_sem_encerrar` | os dias com movimento e sem termo | não basta encerrar hoje: tem de provar que não ficou dia aberto atrás |
| `conferir_livro` | o que a inspeção acharia, em frases de balcão | a conferência existia e ninguém podia rodá-la |
| `panorama` | as seis atribuições numa tela só | não havia onde ver qual série tem livro aberto |

### O que foi feito — `nucleo_web.py`

**Módulo próprio, e não dentro de `atribuicoes_web`.** Aquele é o das quatro
atribuições novas — título, assento, registro. Este é o do **livro**, que serve
as seis. São assuntos diferentes, e o livro não é de ninguém em particular: é
por isso que o núcleo existe. A tela de numeração, que tinha nascido junto com
a carga, **mudou de casa junto** — ela é tela de livro.

Três telas, em *Demais atribuições*:

- **Livros e termos** (`/nucleo/livros`) — as 24 séries agrupadas por
  atribuição: qual tem livro aberto, em que folha ele está, o próximo número de
  ordem, quantos livros e quantos atos. Abre livro onde não há, e lista os
  encerrados com os dois termos para baixar.
- **A ficha do livro** (`/nucleo/livros/<id>`) — o termo de abertura por
  extenso, a **conferência** no alto, o que está escriturado, as faces
  inutilizadas, e os botões de inutilizar e encerrar.
- **Encerramento diário** (`/nucleo/encerramento-diario`) — os três livros de
  protocolo, os dias em atraso de cada um e o histórico do que já foi encerrado.

### As decisões, e por quê

**O número do livro não se digita.** Sai de `numero_do_proximo_livro`, que é o
maior já usado mais um. Digitar abriria a porta para dois Livros 3 na mesma
série — a mesma família do defeito de 18/08.

**A conferência vem na ficha, e não numa tela à parte.** `conferir_livro` diz o
que a inspeção acharia: folha em branco no meio sem termo de inutilização,
verso pulado entre folhas escrituradas, número de ordem repetido, dia sem
encerramento. Pôr isso noutro lugar é pôr para depois.

**O termo sai em `.odt`, para colar no livro de papel.** Termo que só existe
dentro do banco não serve: o livro físico é que precisa dele na primeira e na
última folha. A forma é **exatamente** a de `/notas/livros/<id>/termo/<qual>`,
que já roda nesta casa há versões — cabeçalho da serventia, o teor, a linha de
assinatura. É a regra do oficial de 24/08 aplicada à tela: na dúvida, faça como
já foi aceito antes.

**O campo do dia já vem com o dia mais antigo em aberto.** Encerrar fora de
ordem deixa buraco atrás, e é o buraco que a correição procura.

**Dia sem movimento também se encerra**, e o termo diz "não houve movimento".
É o que distingue dia parado de dia não escriturado.

**Perfil de auditoria vê tudo e não escreve nada.** Abre os livros, lê os
termos, baixa o `.odt` — e recebe recusa ao tentar abrir livro ou encerrar o
dia. Há teste que manda o pedido **com** o csrf da própria tela, porque sem ele
o 400 chegaria antes do 403 e o teste diria "recusou" sem ter provado por quê.

---

## 6. A certidão de protesto — e o que ela cobrou da carga

É o papel que o balcão de protesto mais entrega, e o que faltava para o
Protesto servir a quem entra pela porta: *"fulano tem protesto?"*.

### Os textos são os da casa, e não redação nova

Medidos nas **65 certidões** de `tbProtesto_Certidao`:

| Tipo | Quantas | O texto |
|---|---|---|
| `N` — negativa | 46 | "…a partir do mês de X de AAAA, neles **NÃO ENCONTREI** protesto contra FULANO CPF: … Período de Busca: 5 Anos." |
| `C` — cancelamento | 12 | a positiva **mais** "CERTIFICO ainda que no referido livro e folha consta a BAIXA e o CANCELAMENTO do mesmo de acordo com o art. 26 da lei 9492/97." |
| `P` — positiva | 7 | "…a partir do ano de dois mil e vinte até a presente data, neles encontrei protesto contra FULANO e inscrito no CNPJ: …" |

E as **colunas de cada protesto listado** vieram de
`tbProtesto_Certidao_Itens`, conferidas uma a uma contra `tbAvisoProtesto` —
os **19 itens casaram todos**: livro, folha, número do título, valor, emissão,
vencimento, e as datas do protesto e da baixa.

Duas coisas foram **escolhidas**, e ficam ditas no módulo:

1. "a requerimento **verbal** de parte interessada" é o que as 44 negativas
   dizem, e é o que sai quando ninguém informa o requerente. Informado, sai "a
   requerimento de FULANO" — dizer "verbal" sobre pedido escrito e assinado
   seria certificar o que não houve.
2. O fecho do cancelamento existe no acervo em duas formas, singular e plural.
   Sai a que couber na quantidade; a grafia é a da forma mais nova.

### As regras que o módulo carrega

**Não se emite negativa sobre quem tem protesto.** É a regra que mais importa
deste módulo: negativa errada é a certidão que faz o banco emprestar para quem
não devia, e ela não se desfaz depois. O tipo **sai do que se achou**, não de
quem pede.

**Apontamento não é protesto.** Só entra título com ato de PROTESTO lavrado.
Título apontado e pago no tríduo nunca foi protestado, e certidão que o
mostrasse mentiria contra a pessoa. Medido: dos 189 títulos pagos do acervo, só
4 chegaram a protesto.

**A busca roda de novo na emissão.** Entre o GET e o POST alguém pode ter
lavrado protesto; a rota não confia no que veio da tela.

**O teor congela.** Protesto lavrado amanhã não muda a certidão de hoje — mudar
seria reescrever o que a serventia já afirmou, e a via do cliente ficaria
diferente da do banco. Numeração por exercício, teor congelado e sha256: a
mesma forma do recibo do caixa, que já roda nesta casa.

**A certidão não mora em `pt_atos`.** `pt_atos.titulo_id` é `NOT NULL`, e a
negativa — 46 das 65 do acervo — não tem título nenhum. Certidão é ato da
**serventia sobre uma pessoa**, e por isso ganhou tabela própria,
`pt_certidoes`, com selo e custas pelo caminho `/selo/protesto/certidao` (que a
casa usou 57 vezes).

**Cancelar não apaga.** O teor fica gravado como saiu: apagá-lo deixaria a via
que o cliente levou sem par no banco — e é justamente essa via que alguém vai
conferir.

### O que a certidão cobrou da carga

Escrever a positiva mostrou que a carga não trazia o que ela precisa dizer.

**O ato de PROTESTO não existia.** A carga trazia só o apontamento — e a
certidão positiva diz "protestado no **Livro X, fl. Y**, em tal data". O livro
(4 a 9) e a folha (1 a 200) estavam no acervo o tempo todo, em
`intProtestoLivro` e `intProtestoFolha`. Agora entram: **1.160 atos de
protesto**, 1.159 com livro e folha.

**O ato de CANCELAMENTO também não.** Os 56 do acervo têm data e selo — os dois
em 100%. Entram com os dois; a **hipótese do catálogo não vem**, porque o
acervo tinha um cadastro só e metade dos 56 não diz por quê. Inventar a
hipótese seria assinar por quem cancelou.

**O protesto entra sem número de ordem**, e isso é o fato: o acervo guarda
livro e folha, e nenhuma coluna com o número. É a mesma falta que deixa
`PT_PROTESTO` sem contador semeado.

### A ocorrência `C`, que estava em aberto desde o levantamento

`CLAUDE.md` listava, nas pendências do Protesto: *"ocorrência `C` do E-Ofício,
usada 1.027 vezes: significado ainda desconhecido"*. Medida em 25/08/2026:

| | |
|---|---|
| Títulos com ocorrência `C` | **1.107** |
| Deles, com `snProtestado` | **1.106** (99,9%) |
| Deles, com livro **e** folha do protesto | **1.106** (99,9%) |
| Com `dtmOcorrencia` preenchida | 1.107 (100%) |

E o cruzamento com a situação fecha o quadro: `C` → 1.056 protestados;
`1` e `3` → só pagos; `2` (que **é** "Protestado" no contrato da CRA) → 48
protestados.

**`C` é o código que o E-Ofício escrevia quando o protesto era lavrado aqui
dentro**, enquanto o `2` vinha do arquivo da CRA. E `dtmOcorrencia` é a data em
que ele o escreveu: nos 1.164 protestados ela é **sempre posterior** à entrada
no cartório — 1.160 posteriores, nenhuma igual, nenhuma anterior. É essa a data
que o ato de PROTESTO recebe.

Isto é medição, não documentação oficial: `C` **não** entrou em
`protesto_cra.OCORRENCIAS`, que é gerada dos XSDs. Fica onde já estão os outros
códigos internos observados.

### E um defeito de busca que só a certidão faria aparecer

O primeiro teste a rodar reprovou: procurar por `josé da silva` não achava
`JOSÉ DA SILVA`. **`UPPER()` do SQLite é ASCII** — ele passa `jose` para `JOSE`
e deixa `josé` como `JOSé`.

Uma certidão que não acha por causa de grafia é uma certidão que mente. O
conserto é o que esta casa já usa em `nt_pessoas.nome_norm`: a **coluna
normalizada mora no banco**, preenchida por uma função só —
`pt_schema.normalizar_nome`, igual à de `notas_import`. Duas formas de
normalizar nome fariam a busca do Protesto achar coisa diferente da busca das
Notas para o mesmo nome.

### E um defeito que só um banco ANTIGO faria aparecer

O índice novo sobre `nome_norm` foi escrito junto dos outros dois, dentro do
`SCHEMA`. Em banco **novo** funciona: o `CREATE TABLE` ali em cima já cria a
coluna. Em banco que **já existia**, o `CREATE TABLE IF NOT EXISTS` não faz
nada, a coluna só aparece no `ALTER TABLE` mais abaixo — e o `CREATE INDEX`
estourava com *"no such column: nome_norm"* **na hora de abrir o banco**.

Quem pegou foi `tests/test_menu.py`, que reaproveita a mesma pasta de dados
entre execuções e por isso tinha um banco da versão anterior. Nenhum outro
teste viu, porque todos montam banco do zero — é o parente do que o ensaio de
25/08 já tinha mostrado: **teste sobre banco novo não vê defeito de banco
velho.**

O conserto: índice sobre coluna de migração vai numa lista própria, aplicada
**depois** dos `ALTER TABLE`. Conferido que a mesma armadilha não existe em
nenhum outro esquema do sistema.

---

## 7. A certidão de inteiro teor do RCPJ, do RTD e do Livro 3

Um módulo para as duas atribuições — `atrib_certidao.py` —, porque a forma é a
mesma: achar o registro, reproduzir o teor que está no livro, numerar por
exercício, congelar e assinar. O que muda é a **frase de abertura**, e é a
única coisa que `PAINEIS` guarda.

### Os textos, medidos

| Origem | Quantas | A frase |
|---|---|---|
| `tbTD_Certidao` | 38 com teor (25 RCPJ, 14 RTD) | "CERTIFICO E DOU FÉ, que revendo os livros próprios desta Serventia no Livro "A-5" de Registro de Pessoas Jurídicas, fls. …, ATO n. … datada de …, encontrei o seguinte registro, … Para conhecimento de terceiros e sua conservação: COM O SEGUINTE TEOR: -" |
| `LivroAuxiliarCertidao` | 6 com teor | "CERTIFICO E DOU FÉ, que revendo os livros próprios desta Serventia Imobiliária, a pedido de parte interessada encontrei no Livro 3 Auxiliar de Registro Geral de Imóveis, no registro n.NNNN o seguinte:-" |

34 das 38 começam com "CERTIFICO E DOU FÉ"; as 38 têm "COM O SEGUINTE TEOR" e
"Para conhecimento de terceiros e sua conservação".

### As regras

**Sem teor não há certidão de inteiro teor.** 24 dos 72 registros do RCPJ/RTD e
2 dos 14 do Livro 3 vieram do acervo sem o texto. O módulo recusa dizendo que o
registro **existe no livro** e que a cópia se tira do **livro físico** — é a
mesma resposta que o Registro de Imóveis já dá nas certidões importadas sem
corpo. Sobre o acervo real: **60 certidões saem, 26 são recusadas**, e os dois
números batem com a medição.

**O teor não se digita.** A certidão reproduz o livro; papel que a serventia
assina não se redige no balcão. Por isso `emitir()` não aceita texto de fora.

**Registro cancelado também se certifica**, e a certidão diz que ele está
cancelado. Recusar seria esconder o que existe; calar seria mentir.

**A certidão diz quantos atos o registro tinha quando saiu.** O teor congela, e
averbação lavrada amanhã não a muda — quem confere depois sabe se o registro
andou.

**Emitir é na FICHA do registro**, e não numa tela à parte: é ali que o
escrevente está quando o cliente pede, e é ali que ele acabou de ver o que o
livro diz. A tela de certidões consulta e reimprime.

### O que a certidão cobrou da carga, outra vez

Como no Protesto, escrever a certidão mostrou o que faltava:

- **O ato de REGISTRO do RCPJ/RTD não existia.** A carga trazia o registro sem
  ato nenhum — logo sem folha e sem data, que é o que o cabeçalho da certidão
  precisa dizer. Medido: `dtmData` e `strFolha_DE` estão preenchidos nos **72**.
  `strFolha_DE` é só dígitos nos 72, e `strFolha_ATE` está vazia nos 72 — a
  faixa que as certidões antigas mostram ("fls. 030V A 034") foi **digitada na
  certidão**, e não guardada. Sai a folha inicial, que é o que existe.
- **O volume do livro se perdia.** `rg_registros` ganhou a coluna `volume`: o
  E-Ofício não guarda a letra do livro, só o número do volume, e sem ele a
  certidão não sabe dizer `Livro "A-5"`.

### Dois enganos meus, e o que os desfez

**O nome do livro saía duplicado**: `no Livro "A-4" de Livro A do Registro
Civil das Pessoas Jurídicas`. Eu tinha usado `livro_nucleo.SERIES[...].nome`,
que é o nome do **livro**; a certidão nomeia o **registro**, e o livro ela já
disse entre aspas. Desfez olhando a certidão do acervo ao lado da minha.

**O cabeçalho da serventia saía duas vezes.** O E-Ofício guardava a **página
inteira** em `memInteiroTeorSemFormatacao` — com brasão, comarca e endereço no
alto —, e o meu `.odt` punha outro por cima. Em 13 das 60 certidões reais isso
acontece. O conserto **não corta nada do teor**: o `.odt` deixa de pôr o
cabeçalho dele quando o teor já traz um. Texto de certidão não se edita; só se
decide onde ele entra na folha.

### O RCPN não entrou, e é decisão do oficial

Medido: os **244 assentos do acervo não têm teor nenhum** — `memTexto`,
`memTextoInteiroTeor` e `memInteiroTeorFormatado` estão vazias nas três tabelas
de origem, todas. O E-Ofício montava a certidão dos **campos**, no modelo
nacional do CNJ, e guardava só o resultado: 103 das 126 de nascimento seguem o
mesmo desenho, com o bloco "ANOTAÇÕES DE CADASTRO".

Os campos existem no sistema (20 no nascimento, 47 no casamento, 40 no óbito),
e o desenho é medível. Mas certidão de nascimento é o documento mais
consequente que esta casa emite, e o oficial decidiu em 25/08/2026 fechar
primeiro estas duas e deixar o RCPN para uma passada própria.

---

## 8. O retorno à CRA — e o roteiro que o oficial trouxe

`protesto_arquivo` já lia **e escrevia** o arquivo de 600 posições, e a prova
disso é o ida e volta: dos 572 reais, 558 voltam idênticos byte a byte. O que
faltava era a ponte — ligar o `montar_retorno()` ao que foi **lavrado**, em vez
de a um arquivo que se acabou de ler. 93% dos títulos entram pela CRA; sem o
retorno eles entram e nunca voltam.

### O que o retorno leva, e onde cada coisa foi medida

| Campo | De onde | Medição |
|---|---|---|
| `ocorrencia` (458) | do ato lavrado | `C` para o protesto — **287 dos 383** registros de retorno reais, e 1.106 dos 1.107 `C` do acervo estão com `snProtestado` |
| `protocolo` (448) | de `pt_titulos.protocolo` | no acervo é `intProtocolo`, **igual a `strCB` nos 1.365 (100%)** |
| `data_entrada` (459) | do apontamento | |
| `data_ocorrencia` (478) | do ato | |
| nosso número, valores | do título | |
| o resto | **em branco** | medido: nos 383 reais, espécie, cedente e devedor sempre vazios |

**A ocorrência do pagamento e a da retirada são códigos diferentes**, e o
acervo mostra a separação: `strTipoPG` '12' e '0' saíram com ocorrência `1`
(Pago, 133 títulos); '2' e '4' saíram com `3` (Retirado, 46). No sistema novo os
dois atos já são distintos — PAGAMENTO e DESISTENCIA —, e cada um leva o seu.

**O `C` não está no contrato oficial da CRA, e sai assim mesmo**: é o que esta
casa mandou e a Central aceitou, 287 vezes em 383. É a regra do oficial de
24/08 aplicada ao arquivo que sai.

### O protocolo, que ninguém guardava

O retorno precisa do número de protocolo, e `pt_titulos` não tinha coluna para
ele. Medido: desde **2024** o protocolo é **`AAMMDD` mais o sequencial do dia**
— 928 dos 931 títulos. Antes de 2024 havia outro esquema (`7797140001` para
14/02/2022), que **não se reproduz**: o que vale é o que a casa faz agora.

O número nasce com o **apontamento**, que é quando o título entra. Título que já
tem protocolo — vindo do acervo — fica com o que tinha: renumerar apagaria o
que a Central já conhece.

**O protocolo não ocupa lugar no Livro de Protocolo**, e isso é deliberado: a
geometria daquele livro (quantos por face) é pendência em aberto, e escrever
nele antes de conferir seria inventar.

### E o apresentante, que também não se guardava

O retorno volta **para quem mandou**, e `pt_titulos` não sabia quem era. O
código e o nome estavam no registro do arquivo, nas posições 2 a 19, e
`para_apontamento()` não os trazia. Agora traz — e sem eles `montar_retorno`
não sabe nem a letra da posição 566.

### Nada sai duas vezes

Ato informado ganha `retorno_id` e some da lista de pendentes. Mandar o mesmo
protesto duas vezes faz a Central registrar dois, e desfazer isso é trabalho de
carta. O arquivo inteiro fica gravado — não só o nome —, porque quando a
Central reclamar de um título é esse teor que se lê.

### O que o oficial trouxe, e que a medição não daria

Em 25/08/2026 o oficial pôs na pasta **o roteiro do protesto da serventia em
que trabalhou**. Ele diz, em maiúscula:

> **SEMPRE QUE GERAR RETORNO (FINAL), GERAR ANDAMENTO**

Isso **não está no acervo**. O acervo guarda o que foi lavrado, não a ordem em
que se lavra — nenhuma medição contaria que os dois arquivos andam em par.
`gerar()` passou a produzir os dois numa operação só, com os mesmos títulos, e
os dois se apontam por `par_id`.

O roteiro trouxe mais: a **confirmação** é do meio-dia, junto com o recebimento
da remessa; a **desistência** se confere três vezes por dia; e o dia tem uma
ordem — recebe, confirma, avisa, verifica, protesta, devolve. Está transcrito
inteiro em `ROTEIRO_DIARIO_DO_PROTESTO.md`, com o que já existe e o que ainda
falta de cada passo.

**A lição, e ela é a mesma de 24/08**: quem operou o sistema sabe coisas que a
tabela não guarda. Da primeira vez foi o oficial corrigindo que o E-Ofício
selava em todas as atribuições, contra o que uma coluna vazia sugeria. Desta
vez foi um roteiro de meia página que reorganizou o módulo inteiro.

---

## 9. O mesmo erro, duas vezes no mesmo dia — e o que o desfez

De manhã, o índice sobre `nome_norm` dentro do `SCHEMA` quebrava qualquer banco
de versão anterior. Consertei, movi para `INDICES_DEPOIS_DA_MIGRACAO`, e
escrevi o comentário explicando por quê.

À tarde, escrevendo o retorno, pus `ix_pt_atos_retorno` sobre `retorno_id` —
outra coluna de migração — **dentro do `SCHEMA` outra vez**. O mesmo teste de
menu pegou, com a mesma mensagem: *"no such column"*.

**Comentário não impede; teste impede.** `tests/test_esquemas.py` passou a
guardar os esquemas do banco:

| Guarda | O que ele impede |
|---|---|
| índice do `SCHEMA` sobre coluna de migração | o defeito que estourou duas vezes |
| `MIGRACOES` só acrescenta coluna | `NOT NULL` sem `DEFAULT`, `UNIQUE`, `PRIMARY KEY` — o `ALTER TABLE` falha sobre tabela com linhas, e produção tem 116 MB delas |
| a coluna existe no `SCHEMA` **e** na migração | banco novo e banco velho andando diferente |
| nenhuma entrada declarada duas vezes | achou uma de verdade: `cx_depositos.atualizado_em`, em `caixa_schema` |
| o banco inteiro sobe e fica íntegro, duas vezes seguidas | `init_*` é idempotente por contrato |

**O guarda é estático, e isso foi escolha.** O caminho dinâmico — montar o
banco, arrancar as colunas de migração e subir a atualização por cima — esbarra
num limite do SQLite: `DROP COLUMN` reescreve o DDL da tabela e não lida com o
comentário que vem antes da coluna, e este projeto comenta os esquemas de
propósito. O guarda estático pega o mesmo defeito sem essa fragilidade. Teste
frágil que cobre mais é pior que teste firme que cobre o que interessa.

---

## 10. Um teste que ficava vermelho pela faxina

`test_duas_conexoes_nao_pegam_a_mesma_folha` deixava as duas conexões abertas
até o fim. No Windows, arquivo aberto não se apaga: a limpeza da pasta
temporária estourava **depois** de todas as verificações terem passado, e o
suite ficava vermelho por causa da faxina e não da regra. Fechado em `finally`.

---

## 11. A pergunta do oficial sobre trocar de banco — e o que ela deixou pronto

Ele perguntou, no meio da revisão: *"faz algum sentido migrar para o SQL
Server ou Postgres?"* — e depois o que interessava mesmo: **complexidade,
risco, tempo e benefício**.

A resposta saiu de medição, e não de preferência:

| O que se mediu | Quanto |
|---|---|
| Tamanho do banco vivo | **111 MB** |
| Usuários simultâneos | **6** |
| `database is locked` em um ano de uso | **zero** |
| Comandos SQL escritos à mão | **686** |
| Arquivos que importam `sqlite3` | **78** |

Os motivos que fazem uma casa trocar de banco — muitos escritores ao mesmo
tempo, dezenas de gigabytes, réplica, acesso de fora — **nenhum é o caso
desta**. O custo, esse é certo: **três a cinco meses**, com o banco vivo em
produção durante a troca. O mapa inteiro, com os riscos em ordem do pior para
o menos pior, ficou em `MIGRAR_DE_BANCO.md`.

**Mas "não agora" não é "nunca", e foi isso que o oficial pediu para tratar.**
A instrução dele foi de três partes, e cada uma virou código:

### O aviso, quando o banco travar

`db.transaction()` é `BEGIN IMMEDIATE`: um escritor por vez. Quando dois
balcões gravam ao mesmo tempo e a espera estoura os dez segundos, o SQLite
devolve `database is locked`. **Nada se perde** — o ato volta atrás inteiro —,
mas quem estava atendendo leva o erro na cara.

Agora cada uma dessas vira **uma linha** em
`ProgramData\CartorioGestao\disputas_de_escrita.log`, e o número aparece
**em qualquer tela**, para o oficial e para o gerente. A partir de **cinco em
trinta dias** o aviso muda de tom: de "uma vez ou outra é normal" para "já é
rotina, vale conversar sobre trocar de banco".

**O registro vai para ARQUIVO, e não para o banco.** Gravar a disputa dentro
do banco que acabou de travar seria disputar a mesma trava — e perder
justamente o registro que interessa, que é o da hora ruim. Foi a única decisão
de desenho que essa parte exigiu, e ela tem teste próprio.

**A prova é com trava de verdade.** `tests/test_disputa_de_escrita.py` abre
duas conexões, uma segura a trava e a outra tenta gravar; não há erro
fabricado em lugar nenhum. Nove testes, e três deles existem para o aviso não
mentir: erro que **não** é trava não entra na conta (senão o gatilho dispara
por engano), disputa antiga conta no total e **não** nas recentes, e registro
ilegível não derruba a tela — aviso que quebra a tela é pior que aviso nenhum.

### A facilitação, para se um dia a migração vier

O pedido era construir "com facilitação para uma eventual migração futura".
A tentação aqui é começar a reescrever os 686 comandos — e isso seria **pagar
a migração sem migrar**: todo o custo, nenhum benefício, e mais superfície
para errar num sistema que está suspenso esperando conserto.

O que se fez é mais barato e vale mais: **um teto que impede a dívida de
crescer.** `tests/test_portabilidade.py` mede, por módulo, três coisas que têm
alternativa em Python e não deveriam estar no SQL — data calculada no banco
(`strftime`, `julianday`), recorte de texto no banco, e `PRAGMA` fora dos
módulos de esquema — e congela o número de hoje. **Módulo novo entra com zero.
Módulo antigo pode diminuir; aumentar, não.**

É a diferença entre uma dívida que cresce e uma que fica parada. Se a migração
vier daqui a dois anos, ela vai encontrar o mesmo tamanho de problema que
encontraria hoje, e não o dobro.

### O que NÃO se mexeu, de propósito

Os 686 comandos escritos à mão, os 71 `lastrowid` e os 43 `INSERT OR IGNORE`
ficam onde estão. Para eles não há alternativa barata — `lastrowid` vira
`RETURNING`, `INSERT OR IGNORE` vira `ON CONFLICT DO NOTHING` —, e são
exatamente o trabalho da migração. Trocá-los agora não deixaria o sistema
melhor em nada; só gastaria os três meses antes da hora.

**A lição, e ela não é sobre banco de dados.** A pergunta era "devo migrar?", e
a resposta honesta era "não dá para saber ainda". O que se pode fazer com uma
pergunta assim não é adivinhar: é **fazer o sistema medir o próprio gatilho**,
para que a resposta, quando vier, venha de contagem e não de lembrança.

---

## 12. A remessa da CRA — o passo do meio-dia, e os três defeitos que ele achou

**93% dos títulos desta casa entram pela CRA**, e não havia por onde recebê-los.
`protesto_arquivo.ler()` sabia ler o arquivo desde o primeiro dia — os quatro
tipos, medidos em 572 arquivos reais, com o teste de ida e volta que já pegou
quatro defeitos. `cadastrar_titulo` sabia gravar. `lancar_apontamento` sabia
apontar. `montar_confirmacao` sabia montar o recibo.

O que não existia era o lugar onde uma coisa vira a outra.

É a quarta vez que a mesma pergunta acha o mesmo defeito: *quais funções
públicas de domínio nenhum `*_web.py` chama?* Antes foram o devedor, o
apontamento e a numeração; agora, o passo inteiro do meio-dia — o maior dos
quatro, porque é por onde entra quase tudo.

### O que a construção achou, medindo os 197 arquivos reais

**1. Um arquivo pode trazer mais de um lote, e de apresentantes diferentes.**

Seis dos 197 são multi-lote, e em **três** deles os lotes são de apresentantes
distintos. Um traz 237, 1LV e 033 no mesmo arquivo.

Ler só o primeiro cabeçalho — que é o que `PA.ler()` faz, e está certo para o
que ele é — poria os títulos dos outros dois apresentantes no primeiro. E aqui
está o que faz este defeito ser dos piores: **ele não aparece na entrada**. Os
títulos entram, apontam, ganham protocolo e folha. Tudo parece certo. O erro só
se descobre quando o retorno volta para quem não apresentou, meses depois, e
aí já há atos lavrados em cima.

O arquivo agora se separa em lotes antes de qualquer coisa, e cada lote é uma
remessa própria — com o seu apresentante, o seu número e a sua confirmação.

> `escrever()` já recusava arquivo multi-lote desde 24/08, porque reescrevê-lo
> perderia os lotes de trás. A informação estava lá; o que faltou foi puxar a
> consequência dela para o outro lado do fluxo.

**2. Eu recusava 11% do que a Central manda.**

Trinta e sete dos 343 títulos das remessas reais chegam com `99999999` no
vencimento — a marca de *sem vencimento*, que este módulo já conhecia desde
24/08 —, e **todos são da espécie CDA**: certidão de dívida ativa, que não tem
vencimento nenhum.

Eu havia posto `data_vencimento` na lista de campos obrigatórios de
`conferir_titulo`. Isso faria o balcão digitar à mão um título em cada nove que
vem pronto da Central.

E o contrato oficial já tinha palavra para o caso, na tabela que este mesmo
módulo carrega: **a irregularidade 33 é "Falta data de vencimento no título"**.
Título sem vencimento não é arquivo torto — é título com irregularidade
catalogada, o que é motivo para protestar, e não para devolver.

**3. A letra da posição 566 é do retorno, e só dele.**

`_montar_saida` exigia a letra dos três arquivos de saída, porque é a mesma
função para os três — e reunir os três foi acerto, o rodapé já enganou uma
medição inteira por estar escrito em três lugares.

Só que `reservado_566` existe no layout do **retorno** e em mais nenhum: na
confirmação e no andamento aquela posição cai dentro de `reservado_546`
(546–596), medido como zeros e brancos nos 343 registros.

Com a exigência, **a remessa de um apresentante novo não podia ser recebida**.
A confirmação pedia uma letra que só se aprende num retorno anterior daquele
apresentante — e apresentante novo, por definição, não tem retorno anterior. Um
campo que nem chega a ser escrito travaria o balcão no caso mais comum de todos.

A correção não fixou a regra numa lista de tipos: ela **pergunta ao layout** se
o campo existe. Assim, se um layout for medido amanhã, a regra o segue sozinha.

### As decisões, e o preço de cada alternativa

| Decisão | O que a alternativa custaria |
|---|---|
| `UNIQUE(hash_arquivo)` — o mesmo arquivo não entra duas vezes | apontar tudo de novo: protocolo dobrado, folha gasta, dois avisos ao mesmo devedor — e apontamento não se desfaz |
| Conferir e receber são dois passos; o primeiro não grava | cinquenta títulos entrando sem ninguém olhar são cinquenta atos para desfazer à mão |
| Título ruim não derruba o lote | devolver ao banco mil títulos bons junto com o ruim |
| A confirmação confirma o que ENTROU | dizer à Central que recebeu o que recusou, e depois não ter o que devolver |
| A chave de origem é a posição no lote | 53 grupos e 111 títulos do acervo repetem o nosso número: a reapresentação sumiria dentro da primeira, calada |
| O lote não sela e não cobra | cinquenta chamadas de rede de 20 s dentro de um `BEGIN IMMEDIATE`, com a casa inteira no `busy_timeout` |

**A confirmação parcial foi medida, não suposta.** Em 138 pares
remessa-confirmação um para um dos arquivos reais desta casa: **130 trazem
exatamente os títulos da remessa, 8 trazem menos, e nenhuma traz título que não
veio**. Era a pergunta que decidia o desenho — confirmar o lote inteiro ou só o
que entrou —, e ela tinha resposta nos arquivos.

**O aviso do rodapé também foi medido antes de existir.** Ele soa em 44 dos 197
arquivos reais — 22%. Alto o bastante para não ser ignorado, baixo o bastante
para não ser ruído: alarme que soa sempre é alarme que ninguém ouve, e este
projeto já pagou por isso uma vez, quando a conferência gritava falso em 191
remessas boas.

### O que ficou de fora, e por quê

O **aviso de intimação** — o terceiro item do passo do meio-dia — continua na
ficha de cada título. Ele é ato individual, com modo (pessoal, edital, hora
certa) e consequência jurídica própria; empurrá-lo para dentro do lote faria
cinquenta intimações saírem sem ninguém escolher o modo de nenhuma. O roteiro
o cita junto do recebimento porque é o que se faz em seguida, e não porque é a
mesma operação.

---

## 13. O aviso de intimação — e a diferença entre o instrumento e o ato

O passo seguinte do roteiro do oficial, no mesmo bloco do meio-dia:
*"recebimento de remessa, confirmação e **emissão do aviso**"*. Os dois
primeiros ficaram prontos na seção 12; este é o terceiro.

### O que a medição mostrou antes de qualquer linha de código

O aviso desta casa está em `tbBoletoApto`, e é maior do que o nome sugere.
Está inteiro em `AVISO_DE_INTIMACAO_MEDIDO.md`; o que decidiu o desenho:

| Medido | Consequência no desenho |
|---|---|
| 1.618 avisos para 1.361 títulos — **255 têm mais de um** | o aviso é tabela com uma linha por emissão, e não coluna do título |
| `strBanco='000'`, cedente = a própria serventia, nas 1.618 | não há convênio bancário nem CNAB a medir: o boleto era da casa |
| Quem entrega é `CARTORIO` nas 1.618; `CORREIROS` está **desligado** | por isso `curTaxaEntrega` e `curTaxaAR` são zero |
| **1.092 dos 1.618** foram a edital; **1.068 das 1.139** não-entregas dizem "Ausente" | **o edital é rotina, não exceção** — e por isso é a primeira lista da tela |
| 13 motivos catalogados, com marcas `bitEdital` e `bitContador` | o motivo sai do catálogo, e são as marcas dele que decidem o caminho |

**O achado que mais mudou a tela foi o quarto.** A intuição diz que o normal é
entregar em mão e que o edital é o caso raro. Nesta casa é o contrário: o
caminho comum é a tentativa que não acha ninguém, seguida de edital. Uma tela
desenhada pela intuição poria o edital no fim, escondido — e o escrevente
passaria o dia procurando o botão que ele mais usa.

### A regra que este módulo carrega: o instrumento não é o ato

**O aviso é o papel; a intimação é o ato.** Eles se juntam num lugar só —
quando o papel chega na mão do devedor. Aí sim `protesto.lancar_intimacao`
lavra a intimação pessoal, o título vai a `INTIMADO`, e o protesto pode sair.

**Tentativa frustrada não lavra nada.** Se lavrasse, o título ficaria intimado
sem que ninguém tivesse sido intimado — e o protesto sairia em cima disso. É o
tipo de defeito que não aparece em tela nenhuma: o sistema mostraria tudo
certo, e o erro só existiria no mundo.

**O edital lavra a intimação por edital, com o código.** Antes desta passada o
código do edital era um campo de texto na ficha, digitado à mão — e edital que
só existe como texto num campo não se confere depois. Agora ele é registro, com
número do exercício, **teor congelado e hash**, e sai em `.odt` para afixar.

### O endereço congela no aviso

O papel foi para um lugar. Cadastro que mude amanhã não muda a tentativa de
hoje, e a segunda tentativa é **outro aviso**, com o endereço novo. É
exatamente o que os 255 títulos com mais de um aviso mostram — e é por isso que
a tela deixa corrigir o endereço no ato de emitir, valendo só para aquele
papel.

### O defeito que a medição achou depois do módulo pronto

Escrevi `registrar_entrega` guardando o desfecho **no próprio aviso** — uma
coluna `motivo`, uma `entrega_em`. Funcionava, e os testes passavam.

Aí voltei ao acervo por outro motivo e vi que `tbBoletoControleNEntrega` é uma
**tabela à parte**, com 1.139 linhas para 1.093 títulos: 1.054 com uma
tentativa, **34 com duas, 3 com três e 2 com quatro**.

São 3,6% dos casos — e são exatamente os que importam. Guardar só o desfecho
apagava a tentativa anterior quando a segunda era registrada, e é **o rastro
dela que justifica o edital**. "Tentou-se duas vezes e não havia ninguém" é o
que a inspeção lê; "não entregue" sozinho não conta essa história.

`pt_tentativas` passou a existir, com uma linha por tentativa, e o aviso
continua guardando o desfecho — a mesma divisão do acervo, `tbBoletoApto` ao
lado do controle. E as telas mostram o rastro, porque guardar sem mostrar não
serve de nada.

> **A pergunta que achou isto**: *o que o acervo guarda em tabela própria que
> eu estou guardando em coluna?* Tabela à parte quase nunca é capricho — é
> alguém que precisou de mais de uma linha.

### O que ficou de fora, e a razão está medida

**O boleto não foi construído.** O código de barras é FEBRABAN de 44 posições e
está quase todo explicado — banco, moeda, valor (bate em 1.618 de 1.618), e o
campo livre, que é `nosso número × 10 + verificador` em 1.618 de 1.618. Faltam
duas coisas:

- **o verificador**: busca exaustiva das 9⁴ combinações de pesos, em módulo 10
  e 11, nas duas convenções. Melhor acerto: **465 de 1.618**, nível de acaso.
  Ele depende de algo além do nosso número, e não se sabe do quê.
- **o fator de vencimento**: bate com `dtmVenc` em 776 de 1.618, e a diferença
  entre emissão e vencimento chega a ser **negativa** em 185 casos.

**Código de barras errado é boleto que o leitor ótico aceita e o dinheiro cai
no lugar errado.** Não se chuta — e a busca que não deu em nada ficou escrita,
para quem tentar depois não refazer o mesmo caminho.

O que se construiu é o **registro**: quem foi intimado, quando, por quem, e se
foi por edital. É o que a inspeção cobra, e é o que o sistema não tinha.

---

## 14. A desistência — e o que a pasta do oficial fechou numa manhã

Em **26/08/2026** o oficial disse onde estavam mais arquivos da CRA:
`<pasta de rede da serventia>\…\<pasta da CRA>`. **Cento e vinte e dois arquivos** — e
um deles resolveu o layout que estava travado desde a véspera.

### Um arquivo mudou o que dava para afirmar

A desistência tinha três exemplares no acervo, todos de 2022–23, e o registro
do título não fechava: os dois apresentantes preenchiam de forma diferente, e
com um título de cada não dava para separar campo de preenchimento.

O quarto arquivo é de **05/08/2026**, e o número do título dele é
**`NF-74654-/1`**.

Foi só isso. Um número com letras, hífens e barra, onde os outros três tinham
`92000001907` e `1  00053603` — dígitos e espaços que se confundem com o
preenchimento em volta. A forma inconfundível prendeu a fronteira do campo, e
com ela **todos os outros campos do registro caíram no lugar**.

> É a terceira vez que este projeto aprende a mesma coisa, e vale escrever de
> novo: **o que fecha uma lacuna de layout é mais amostra, e não
> engenhosidade.** No retorno foram duas perguntas melhores e mais arquivos.
> Aqui foi um arquivo, quatro anos depois dos outros.

O layout inteiro está em `LAYOUT_DESISTENCIA_MEDIDO.md`. Os quatro arquivos
agora leem com **zero achados**, e a soma do rodapé fecha nos quatro.

### O que se construiu, e o que deliberadamente não

`protesto_desistencia.py` lê o arquivo, procura cada título **pelo protocolo**
e mostra o que a casa tem de cada um: apontado, já protestado — e por que não
cabe —, ou nenhum título com aquele protocolo.

**Nada se aplica sozinho.** Cada título é uma marcação do oficial. Com cinco
títulos de amostra medidos, ler errado continua sendo possível, e desistência
lida errado é **protesto lavrado contra quem o credor desistiu de protestar** —
o erro que o roteiro manda conferir três vezes por dia.

**E o arquivo repetido NÃO é recusado**, ao contrário da remessa. Lá, receber
duas vezes apontaria tudo de novo. Aqui, aplicar duas vezes não faz nada — o
domínio recusa desistir de título já desistido — e o caso comum é justamente o
segundo turno: metade de manhã, o resto ao meio-dia. O arquivo fica gravado uma
vez só, achado pelo hash.

### E a pasta ainda cobrou uma conferência

Os outros 120 arquivos são de 600 posições, todos de 2026 — quatro anos depois
do lote em que o leitor foi medido. Passei o **teste de ida e volta** neles:

| | |
|---|---|
| Voltam idênticos byte a byte | **99** |
| Recusados de propósito (multi-lote) | 21 |
| **Diferentes** | **0** |

E deram um número que muda o peso de uma decisão da véspera:

| | 2022–23 | **2026** |
|---|---|---|
| Remessas multi-lote | 6 de 197 — **3%** | **3 de 25 — 12%** |
| …com apresentantes diferentes | 3 | **2** |

**O multi-lote quadruplicou.** Quando eu o tratei, em 25/08, o número que eu
tinha era 3% — raro o bastante para parecer zelo excessivo. Com 12%, o defeito
que ele evita — títulos lançados no apresentante errado, e o erro só aparecendo
quando o retorno volta para quem não apresentou — chegaria ao balcão **cerca de
uma vez por semana**.

Os três multi-lote de 2026 passaram inteiros pelo recebimento: 12 títulos, cada
um no apresentante que o apresentou, com uma confirmação por lote.

> **A lição, e ela é sobre medição e não sobre protesto**: uma frequência
> medida num lote antigo pode estar medindo o passado. Os 3% eram verdade em
> 2022; a decisão que eles quase não justificaram é a que 2026 tornou
> necessária.

---

## 15. A aba do que só o oficial sabe — e o dia em que um segundo acervo desmentiu uma crença

Em **26/08/2026** o oficial leu a lista de pendências no fim de uma conversa e
respondeu com um pedido curto:

> *"Todas pendências de atualizações de livros, crie um aviso no sistema para
> atualizar e disponibilize uma aba para incluir depois quando formos colocar o
> sistema para funcionar novamente. Esse entendimento serve para todas
> atribuições."*

Ele está certo, e a frase que resume por quê é esta: **documentação não avisa
ninguém.** Aquelas pendências estavam escritas em `CLAUDE.md` e em três
roteiros; o balcão nunca as veria, e o sistema vai voltar do zero com elas em
aberto.

### O que ficou

`implantacao.py`, no **núcleo** — porque o pedido foi "para todas atribuições",
e o núcleo é o que serve as seis. Uma aba (*O que falta informar*) e um aviso
que aparece em **qualquer tela**, ao lado do aviso de travamento do banco.

Cada pendência diz três coisas: **o que é**, **por que só o oficial sabe** —
com o fato medido — e **o que acontece** se ficar sem resposta. As de número
têm o formulário ali mesmo; as de decisão pedem que se escreva o que foi
decidido, porque "resolvido" sozinho não responde a pergunta que a inspeção faz
seis meses depois.

**Dispensar exige motivo escrito**, como no rito do usucapião: dispensar é
decisão do oficial; ignorar não é.

### A decisão que faz o aviso valer alguma coisa

**Pendência é declarada, não adivinhada.** Uma pendência entra na aba porque
alguém a descobriu e a declarou, com o motivo medido — a carga do acervo
declara as séries que não soube semear.

A alternativa era listar "toda série sem contador". Ela teria gritado **quinze
avisos numa instalação limpa**, onde começar do número 1 está certo. Esta casa
já pagou por esse erro: a conferência do rodapé gritava falso em 191 remessas
boas, e alarme que soa sempre é alarme que ninguém ouve.

### E construir a aba achou três séries CALADAS

Ao perguntar "quais séries o núcleo serve, e quais a carga não sabe semear?",
apareceram três que ninguém tinha declarado:

| Série | Espécie que vai para ela |
|---|---|
| `RC_B_AUXILIAR` | casamento religioso com efeito civil |
| `RC_C_AUXILIAR` | natimortos |
| `RC_D` | proclamas |

`rc_assento.SERIE_DA_ESPECIE` manda assentos para as três, e **nenhuma tinha
contador nem aviso**: o primeiro assento de cada uma nasceria com o número 1.
Era o defeito de 18/08/2026 esperando em três lugares, **em silêncio** — que é
pior que esperando à vista.

O motivo é medido: o acervo do E-Ofício tem **três tabelas do civil** —
`tbRegistroNascimento`, `tbRegistroCasamento`, `tbRegistroObito` — e mais
nenhuma. Esses três livros nunca existiram nele.

E a pergunta virou teste: *toda série que o núcleo serve tem fonte na carga ou
motivo declarado?* Sem ele, acrescentar uma espécie nova ao RCPN amanhã traria
o mesmo silêncio de volta.

---

## O segundo acervo, e as duas coisas que ele desmentiu

No mesmo dia o oficial trouxe **17.057 arquivos da CRA** da serventia em que
trabalhou, em **Sergipe**. Ele disse "talvez seja útil". Foi mais que isso: em
uma manhã, aquele acervo **provou uma medição** e **desmentiu duas crenças**.

### 1. Provou o layout da desistência

O leitor da desistência tinha sido medido em **quatro** arquivos desta casa.
Contra os 385 de Sergipe: **384 lidos sem um único achado**, 502 títulos, e a
soma do rodapé fechando nos 384. O único recusado é um retorno de 600 posições
guardado na pasta errada — e o leitor o recusou dizendo onde ele se abre.

E fechou a última incógnita: a contagem do registro `8`, que com quatro
exemplares era "compatível com o dobro dos títulos", é **o dobro em 388 de
388**.

> **Um layout medido em quatro arquivos de uma casa leu 384 de outra casa, de
> outro estado, sem erro.** É a prova independente que releitura de código
> nenhuma dá.

### 2. Desmentiu a letra da posição 566

`CLAUDE.md` dizia, desde 24/08, que a letra da posição 566 do retorno é
**convenção do apresentante** — porque nesta casa cada apresentante recebe
sempre a mesma letra: 31 de 32, em 315 títulos. Uma regularidade forte.

Nos **2.087 retornos de Sergipe a posição 566 vem em branco**. Todos.

Então não é regra nacional do apresentante: é **convenção de cada casa**, e a
Central aceita branco também. `MARCA_POR_APRESENTANTE` continua valendo — como
tabela do que *esta casa* escreveu, e não do que o apresentante exige.

E a pendência mudou de forma: ela era "A ou P, e o empate é exato". Agora são
**três caminhos aceitos**, e o terceiro tem 2.087 provas. Ela foi para a aba
nova, com as três opções à vista de quem decide.

> **A lição de método, e ela não é sobre protesto:** uma regularidade forte
> dentro de uma casa parece lei até alguém olhar outra casa. Foi o segundo
> acervo que separou "o que o apresentante exige" de "o que o nosso programa
> fazia".

### 3. E o oficial desmentiu a terceira

A pasta de Sergipe tem **881 arquivos do Banese**, e o roteiro do protesto os
cita na rotina da manhã. Eu os tinha registrado como "um layout que ninguém
mediu ainda" — trabalho pendente.

O oficial cortou isso em uma frase: o arquivo do Banese era do **TJSE**, porque
lá os pagamentos caíam direto no banco. **No TJMA o pagamento é na serventia**,
e não há arquivo de banco a receber.

Ficou registrado no roteiro justamente porque os 881 arquivos existem: quem os
encontrar sem esta nota vai medi-los achando que faltam.

> **As três correções do dia vieram de fora do código.** Duas de um segundo
> acervo, uma de quem operou o sistema. Nenhuma teria aparecido relendo o que
> eu já tinha escrito — e as três estavam escritas com confiança.

---

## O que a revisão ensinou, e vale para as atribuições que faltam

**Buraco de tela não aparece em teste de domínio.** As três faltas mais graves
do dia — o devedor, o apontamento e a numeração — têm função de domínio pronta
e testada. O que faltava era alguém as chamar.

A pergunta que acha essa classe inteira de uma vez: **quais funções públicas
de domínio nenhum `*_web.py` chama?** Ela achou o núcleo sem nenhuma tela, e
com ele o passo 5 do roteiro — que mandava fazer algo impossível.

Foi ela que apontou `escrituracao.abrir_livro`, `encerrar_livro`,
`inutilizar`, `encerrar_o_dia`, `dias_sem_encerrar`, `conferir_livro` e
`panorama` — o núcleo inteiro sem uma rota. Todos ganharam tela no mesmo dia
(seção 5), e a pergunta continua servindo para o que vier.

**Acervo completo esconde buraco de fluxo.** O apontamento não aparecia porque
todo título do acervo já vinha apontado; abrir registro novo não aparecia
porque a carga preenchia as listas. É o parente do que o ensaio de 25/08 já
tinha mostrado do outro lado: **teste sobre banco vazio não vê defeito de
continuidade, e tela sobre acervo cheio não vê defeito de começo.**

A pergunta que achou as duas: *o que acontece se ninguém tiver rodado a carga
e o primeiro cliente entrar pela porta?*

---

## O que ainda falta nesta revisão

- **a certidão do RCPN**, no modelo nacional do CNJ — decisão do oficial de
  25/08/2026: fica para uma passada própria
- **as remessas externas** do RCPN: SIRC, CRC, IBGE e DNV
- **o boleto do aviso** — o registro do aviso, da entrega e do edital ficou
  pronto em 25/08; o código de barras não, e o motivo está medido
- **a receita de custas do RCPN** — não há: o E-Ofício mandou o `codigoAto`
  vazio nos 1.238 atos gerais do civil
- **a matrícula de 32 dígitos** do RCPN — recebida, não gerada nem validada
- passar a mesma pergunta pelas Notas e pelo Registro de Imóveis, que são as
  duas atribuições que esta revisão ainda não visitou
