# CartorioGestão — diário do projeto

**Serventia Extrajudicial do Ofício Único de Cidade Exemplo/MA — CNS 000000**
Período coberto: 13 a 17 de agosto de 2026.
Estado atual: versão 3.3.1 — 36 módulos, 117 rotas, 76 telas, 21.159 linhas de código,
210 testes. Números contados, não estimados.

---

## 1. O que existe hoje

### Registro de Imóveis

Acervo de **1.700 matrículas** importado do E-Ofício, com atos, partes, protocolos e certidões.
Ficha impressa no layout do modelo em papel da serventia, com cabeçalho em caixas, numeração de
folha que incrementa sozinha (art. 428, III do Código de Normas) e o delegatário de cada época
preservado no fecho de cada ato.

Protocolo e prenotação com prazo de 20 dias úteis, 40 em REURB-S. Certidões, nota devolutiva,
indicador real e pessoal, livro de selos, exportação ONR e aba de CTP para as prefeituras.
Biblioteca de 25 modelos de ato com preenchimento guiado.

**3.667 fichas digitalizadas** localizadas e copiadas para o acervo do sistema, agora visíveis
como miniaturas na própria matrícula.

**Pendente de carga**: 1.097 matrículas novas, 367 ampliadas e 191 sem teor.

### Caixa e protocolo geral

**21.343 protocolos** e **18.388 lançamentos** importados, de março de 2020 a agosto de 2026.
Tabela de emolumentos do TJMA conferida contra a Resolução-GP 143/2025: **270 de 270 faixas** e
**430 de 430 valores fixos** batem, teto de R$ 21.380,93 confirmado.

### Tabelionato de Notas

**4.060 cartões de autógrafo**, 3.637 imagens de assinatura, **13.209 reconhecimentos de firma**,
1.836 termos de presença, 3.539 autenticações, 213 procurações, 45 escrituras, 301 modelos.

**Atenção: estes números são da exportação, medidos rodando o importador contra ela. No banco de
produção a carga ainda não entrou** — em 17/08 o `nt_cartoes` tinha zero linhas. Foi o que fez a
tela de assinaturas parecer quebrada por três respostas seguidas. Enquanto a carga não rodar,
todo número desta seção descreve o que vai entrar, e não o que está lá.

O balcão, a lavratura e o cadastro de parte com dois caminhos seguem como antes.

### Remessa às centrais — novo

**CEP, CESDI e RCTO** montam a carga em JSON, no formato que o CNB-CF recomenda. A tela é
organizada por **quinzena**, e não por mês, porque é assim que a CENSEC fecha (Provimento CNJ
149/2023, art. 267). Mostra o prazo, destaca o vencido, lista o que está pronto e agrupa o que
falta por motivo. Item confirmado pela central não volta na quinzena seguinte; rejeitado volta.

Da fila da CEP: **188 atos prontos, 65 parados**.

### DOI — Declaração sobre Operações Imobiliárias — novo

Para a Receita Federal, pela DOI-Web. Reusa o que o operador já digita na CTP: é a mesma
informação para dois destinatários, e digitar duas vezes só faria as duas divergirem.

A tela lista os **meses que ainda devem satisfação**, tirando a lista do calendário e não dos
atos — porque a inspeção cobra comprovação de DOI **ou declaração negativa dos meses sem ato**, e
mês vazio não aparece em lista nenhuma justamente por estar vazio.

### Biblioteca de modelos notariais — novo

**33 modelos** em texto corrido: 24 da CEP, 8 da CESDI, 1 do RCTO. Escrituras de compra e venda
urbana e rural, doação, permuta, cessão de direitos hereditários, inventário e partilha,
sobrepartilha, partilha e adjudicação, nomeação de inventariante, divórcio, separação, conversão,
restabelecimento, união estável e sua dissolução, hipoteca, alienação fiduciária, confissão de
dívida com dação, quitação, distrato, emancipação, pacto antenupcial, usufruto, diretivas
antecipadas de vontade; procuração, procuração em causa própria, substabelecimento, revogação e
renúncia de mandato; três atas notariais; e o testamento público.

**Falta**: e-Notariado, RCDUV e a confirmação do envelope da DOI.

---

## 2. Decisões que moldaram o sistema

As de antes continuam valendo: dinheiro em centavos inteiros; nada entra em silêncio; carga
repetível por construção; o que sai do cartório sai mascarado e o banco guarda inteiro; o sistema
separa, mede e mostra; congelar o que foi impresso; papel administrativo mascara, cópia de ato
não; não montar por template o que tem forma vinculada.

As novas:

**Texto corrido, sem claro nem espaço em branco.** Art. 795, § 2º, do Código de Normas. Espaço em
branco em ato notarial não é questão de estética: é o lugar por onde se acrescenta o que ninguém
declarou. Por isso `texto_corrido()` roda DEPOIS do preenchimento — quando uma cláusula
condicional não entra, o buraco que ela deixaria é fechado, inclusive a vírgula órfã.

**Procuração vai com valor 0,00; escritura sem valor fica parada.** A CEP marca `valor` como
obrigatório, mas o layout diz o que ele é: "o valor discriminado no ato, e não o valor pago pela
lavratura". Procuração não discrimina valor — ali o zero é a informação correta. Escritura é o
oposto: o valor é o conteúdo econômico do ato, e mandar zero seria declaração falsa a uma central
nacional.

**Uma DOI para cada imóvel, e os lados vêm do imóvel.** Não uma por ato. Na permuta, quem aliena
um imóvel adquire o outro: montando do ato para baixo, os lados sairiam trocados na segunda
declaração e ninguém perceberia.

**Rótulo que não está no de-para não passa.** A serventia não grava "outorgante": grava o papel do
ato — VENDEDOR(A), CEDENTE(S), PROPRIETÁRIO(A). São 22 rótulos, e todos mapeiam. O que não estiver
mapeado vira impedimento com o nome exato, para aparecer na tela em vez de virar Outorgante
calado.

**O testamento passou a ser modelo completo, invertendo o que este diário dizia.** A decisão
anterior era devolver só a qualificação. Por determinação do delegatário, o modelo agora monta o
ato inteiro — com os três requisitos essenciais do art. 1.864 escritos no corpo, as cláusulas do
cego lido duas vezes, do surdo, de quem não assina, o aviso da legítima e a justa causa do art.
1.848. A ressalva do diário continua verdadeira: isso aproxima o defeito de forma do balcão, e a
conferência do tabelião é o que resta entre o modelo e a nulidade.

---

## 3. Os erros, que são o que mais ensinou

### Três respostas sobre a pasta, e a tabela estava vazia

Passei três respostas consertando o caminho das assinaturas: a pasta UNC que o serviço não
enxerga, a cópia para dentro do acervo, a medição que olhava uma pasta só. Cada correção era
real e nenhuma resolvia, porque **o `nt_cartao_imagens` tinha zero linhas.**

Não havia o que localizar. A carga do E-Ofício nunca entrou neste banco.

O sintoma — "nenhuma assinatura localizada" — descreve com igual fidelidade um arquivo que não
se acha e um banco sem nada a achar. **Eu escolhi a leitura que já tinha uma teoria pronta.** A
tela dizia "de 0", e eu li "0 de 3.637".

O diagnóstico que finalmente perguntou "quantas linhas há?" custou menos que qualquer uma das
três deduções. Agora ele responde também à pergunta seguinte, quando a tabela está vazia: se a
carga já foi tentada, o que o `nt_importacoes` registrou, e onde está a exportação no disco.

Medido depois, contra a exportação real: o importador traz 4.060 cartões, 3.637 imagens, 13.209
reconhecimentos, 258 atos. Ele sempre funcionou. Ninguém o havia rodado.

### Medir uma pasta e responder sobre todas

As 3.644 assinaturas vieram para `arquivos\eoficio\Firmas` — caminho local, que o serviço
enxerga. A tela continuou dizendo **"nenhuma assinatura localizada"**.

Não era a cópia. Era a medição. A tela indexava só a pasta gravada em `nt_pasta_firmas`, que
seguia sendo o `\\servidor\C11\Firmas` morto, e apresentava aquele resultado como se fosse sobre
o sistema inteiro. O sistema procurava em quatro pastas e media uma.

**Resposta que parece medição é pior que nenhuma, porque encerra a investigação.** Foi o que ela
fez comigo duas vezes seguidas: eu li "nenhuma localizada", acreditei que era sobre o acervo, e
deduzi em vez de conferir. `indexar_varias()` passou a medir todas; `diagnostico()` aceita lista.

E, no lugar da terceira dedução, o `DIAGNOSTICAR_FIRMAS.cmd` — que mostra os dois lados, o nome
que o banco procura e o arquivo que o disco tem, e ainda confere se o código instalado é o
corrigido. Mesmo remédio que resolveu as fichas do Registro de Imóveis.

### Uma pasta de rede que caiu derrubou a cópia inteira

**O `COPIAR_ARQUIVOS_EOFICIO` copiou seis pastas, inclusive as 3.644 assinaturas, e então morreu
na sétima** com `OSError: [WinError 64] O nome da rede especificado não está mais disponível`. As
duas últimas da lista — o malote do SISDFERJ e as fichas do ONR — não chegaram a ser tentadas.

O detalhe que não sabia: **`Path.is_dir()` não é seguro para caminho de rede.** Ele engole
`WinError 21`, `123` e `1921` e devolve `False`; o `64` escapa e vira exceção. Quer dizer: é
seguro para caminho que não existe, e não é seguro para caminho que existiu e caiu.

Que é exatamente o cenário do trabalho. Desligar o servidor antigo é o objetivo — depois disso,
todo `\\servidor\...` gravado no banco vira caminho que cai. E um deles estava no caminho da tela
de assinaturas, que teria virado erro 500 em vez de tela vazia.

Corrigido em três lugares (`copiar_arquivos_eoficio`, `notas_web`, `ri_imagens`) com um
`e_pasta()`/`_e_arquivo()` que devolve `False` em vez de levantar, e com cada pasta da cópia
tentada dentro do seu próprio `try`: **pasta que não responde é informação a relatar, nunca motivo
para parar.** O manifesto passou a ser gravado a cada pasta, para que o interrompido conte.

### Reimplementar o que já existia — de novo, e pior

**Escrevi um módulo de DOI inteiro por cima do `ri_ctp`, que já fazia aquilo.** A CTP usa o mesmo
formato de arquivo da DOI-Web — quem diz é o CNB, com todas as letras. E o meu saiu com três
defeitos que o `ri_ctp` não tinha:

- **copiei um erro do E-Ofício**: a operação 19 está gravada lá como "Doação em Pagamento". A
  Receita chama de **dação** em pagamento, art. 356 do Código Civil, outro instituto;
- **inventei os códigos de forma de pagamento**, simbólicos, quando os oficiais são numéricos;
- **batizei os campos do arquivo com os nomes das fichas da tela** do manual, e não com os do
  layout.

O `ri_ctp` não tem nenhum desses porque foi escrito a partir da especificação publicada. Apaguei o
montador duplicado e passei a delegar. Um teste garante que o domínio é o mesmo objeto: se alguém
recriar a tabela, ele cai.

A lição do traslado sem teor era **"eu tinha a ferramenta e improvisei outra"**. Repeti, num
módulo maior, três meses depois de escrevê-la.

### O mesmo defeito voltando por não ter sido resolvido na raiz

**Na remessa à CEP o arquivo saía com `"identidade": null` em toda parte sem RG.** Corrigi
filtrando os vazios. Na DOI, o mesmo: `null` vazando dos dicionários aninhados, porque o filtro
olhava só o nível de cima.

Da segunda vez tornei a função **recursiva**. Quem escreve o dicionário à mão lembra de limpar o
que está vendo, não o que está dentro; recursivo, o descuido não tem por onde entrar.

### Passar a chave errada, e a falha ser aceita

**As partes da DOI saíam sem CPF.** Passei `documento` onde o `ri_ctp` lê `documento_numero`, e o
registro ia com `identificadorNiIdentificado: false`. Uma declaração sem quem alienou é **pior do
que uma recusada, porque a Receita aceita** — e o erro só apareceria numa fiscalização.

Só vi porque abri o arquivo e li. Terceira vez neste projeto que ler o arquivo pega o que o teste
não pegou.

### O mesmo ato indo para duas centrais

Corrigida a leitura da natureza, as 5 escrituras da CESDI passaram a aparecer **também** na fila
da CEP. O layout é explícito: a CEP recebe todas as escrituras *exceto* as que se enquadram na
CESDI e no RCTO. Defeito meu, exposto por uma correção minha.

### Deduzir três vezes antes de medir uma

**As fichas digitalizadas não abriam.** Deduzi da exportação que o problema era a extensão: o
banco guarda `00003967.0001`, o disco guardaria `00003967.0001.TIF`, e o casamento exato falharia
em todas. Fazia sentido, e estava errado — **nesta instalação os arquivos não têm extensão
nenhuma**.

Foram três respostas minhas antes de eu escrever um diagnóstico que lesse a instalação de verdade.
Ele respondeu em dois segundos: as 3.667 fichas localizadas, copiadas, presentes no disco. Faltava
o **Pillow**, sem o qual não há como converter TIFF Grupo 4 para o que o navegador exibe.

A correção da extensão continua no código como robustez. Mas a lição não é sobre extensão: é que
eu tinha acesso à máquina desde o começo e preferi deduzir. **Medir custa dois segundos; deduzir
custou três rodadas e a sua paciência.**

### Um defeito escondendo outro

Mesmo achando o Pillow, a ficha continuaria "sem abrir" por um segundo motivo independente: **na
tela da matrícula as fichas eram só texto**. Seis nomes de arquivo num `<li>`, sem link, sem
miniatura. A digitalização só aparecia numa segunda tela que ninguém adivinha que existe.

### O atualizador que não atualizava tudo

**O `ATUALIZAR_SISTEMA.cmd` copiava código e telas, mas nunca instalou dependência.** Foi por isso
que "atualizei e segue igual" era, ao mesmo tempo, verdade e frustração. Agora ele confere Flask,
waitress e Pillow a cada atualização.

---

## 4. Correções que vieram de você

As anteriores continuam registradas: penhora é averbada; o protocolo no caixa não tem selo; não
cadastrar delegatários por período; o e-mail novo é `contato@exemplo.invalid`.

**"Procuração vai com 0,00."** Destravou 213 atos de uma vez.

**"Modelos em texto corrido, sem espaço."** Foi o que me levou ao art. 795 e aos seus parágrafos,
que agora governam a biblioteca inteira.

**"Testamento: modelo completo, com as cautelas."** Inverteu a decisão que este diário registrava.

**"Segue como antes."** Duas palavras que valeram mais que as minhas três deduções: eram o
servidor rodando código antigo, e depois a biblioteca faltando.

---

## 5. Achados no acervo que pedem sua atenção

Os de antes seguem: matrícula 8 duplicada em dois livros; dois CPFs inexistentes entre os 4.061
cartões; 135 matrículas divergentes entre o Word e o sistema; sete imagens de assinatura
descasadas.

**Os domínios do E-Ofício estão velhos.** Faltam 17 naturezas de escritura das 54 que a CENSEC
aceita — quatro delas de 2025 e 2026. O sistema passou a carregar a tabela oficial.

**As partes das escrituras nunca tinham sido exportadas.** Moravam em `tbESC_Partes`, e nenhum
script as trazia. Trazidas em 15/08, 36 das 45 escrituras ganharam partes.

**`intCodigoParte` aponta o cartão de autógrafo**, não uma tabela de pessoas: resolve 72 de 72.
Contra `tbOrtoga` resolvia 2. Conferido antes de construir.

**`intQualificacao` não é o domínio da CENSEC.** Os códigos 20, 21 e 22 ali são COMPRADORA,
VENDEDORA e DECLARANTE; na `tbQualificacaoCENSEC` os mesmos números são ANUENTE, Outorgado e
Outorgante. Isso enfraquece a hipótese, registrada aqui antes, de que aquela tabela de 22 linhas
fosse a chave do `intQualifica` do RI.

**Oito escrituras estão na quarentena com as partes em disputa.** Três protocolos rendem mais de
um ato — o 2020.08.219 rendeu quatro — e as partes não dizem qual é de qual. Em dois deles o livro
e a folha também se repetem, que é o caso em que a CENSEC recusa por duplicidade.

**40 escrituras seguem sem valor declarado.** `curValorTransacao` veio nulo em todas as 45. É o
maior bloqueio da fila da CEP.

**O RCDUV é um quarto módulo da CENSEC, e não estava no sistema.** O art. 880 manda comunicar a
Diretiva Antecipada de Vontade de forma obrigatória, gratuita e sigilosa ao Registro Central de
Disposições de Última Vontade.

---

## 6. O que fazer agora

1. **Rodar a carga do E-Ofício** em Notas → Importar, com a pasta
   `Downloads\CartorioGestao\MIGRACAO\EXPORT_NOTAS_EOFICIO`. O banco de Notas está vazio; é
   isto, e não as imagens, que faz a tela de assinaturas não mostrar nada.
2. **Rodar de novo o `COPIAR_ARQUIVOS_EOFICIO.cmd`** — a primeira rodada trouxe 6 das 8 pastas
   (408 MB, com as 3.644 assinaturas) e parou no erro de rede. A segunda pula o que já veio e
   tenta as duas que faltam: o malote do SISDFERJ e as fichas do ONR. **O E-Ofício não pode ser
   desligado antes de o script terminar sem pasta pendente.**
2. **Lançar o valor declarado nas 40 escrituras**, na tela de Pendências das escrituras.
3. **Distribuir as partes das 8 escrituras** de protocolo repetido, na mesma tela, e informar o
   complemento de livro ou folha nas duas que se repetem.
4. **Classificar a natureza das 45 escrituras** contra a tabela de 54 — hoje caem todas em
   "ACORDO EXTRAJUDICIAL", que é marcação de fábrica do E-Ofício.
5. **Confirmar os nomes das listas do envelope da CENSEC**, baixando a coleção do Postman.
6. **Baixar o esquema JSON da DOI** e confirmar o envelope. O registro já está conferido.
7. **Cadastrar a função de cada usuário**, abrir os livros do tabelionato, carregar as matrículas
   em Word e cadastrar os delegatários.
8. **RCDUV, e-Notariado**, e depois **CIB e SINTER**, obrigatórios a partir de janeiro de 2027.

---

## 6b. O que a 3.3.1 mudou

Versão pequena, feita quase toda de correções que vieram de uma coisa só não funcionar.

- **Assinaturas**: a busca passou a incluir `arquivos\eoficio\Firmas` — caminho local — antes das
  UNC, e a medir TODAS as pastas em vez de uma. `indexar_varias()` em `ri_imagens`.
- **Caminho de rede morto** deixou de derrubar tela e script: `e_pasta()` / `_e_arquivo()` em
  `ri_imagens`, `notas_web` e `copiar_arquivos_eoficio`.
- **`COPIAR_ARQUIVOS_EOFICIO`**: cada pasta tentada no seu próprio `try`, manifesto gravado a
  cada pasta. Trouxe 6 das 8 na primeira rodada — 408 MB, 3.644 assinaturas.
- **Arquivo já dentro do acervo é adotado, não copiado** — senão o acervo dobraria de tamanho e
  todo backup carregaria as duas cópias.
- **`DIAGNOSTICAR_FIRMAS.cmd`**: mede os dois lados, e quando a tabela está vazia responde à
  pergunta seguinte — se a carga já foi tentada, o que ficou registrado, onde está a exportação.
- Testes: 198 → 210.

---

## 7. Como trabalhamos

Os dois limites continuam: **UAC não se automatiza**, então tudo que pede administrador volta para
você; e eu não escrevo em `C:\Program Files` nem apago na pasta de backups.

O padrão que se firmou: construir, testar contra cópia da produção com chave estrangeira ligada, e
relatar o que deu errado junto com o que deu certo. São 130 testes.

**Imprimir e olhar** segue pagando. Nesta semana pegou três defeitos que passaram por todos os
testes automáticos: o `identidade: null` na carga da CEP, o `null` aninhado na DOI, e as partes
sem CPF.

E entrou um hábito novo, que devia ter entrado antes: **medir a instalação em vez de deduzir dela**.
O `DIAGNOSTICAR_FICHAS.cmd` roda sem administrador, lê o banco em modo somente leitura, e diz qual
dos cinco motivos possíveis é o da vez. Escrevê-lo levou dez minutos. Não tê-lo escrito custou três
rodadas de palpite.

---

## 8. Rodada de 17/08/2026 — a numeração dos livros de notas (3.3.8)

O pedido era "vincular livro e folha para contagem automática". O que estava embaixo era pior do
que o pedido sugeria: a folha era **digitada**, e a mesma gravação que salvava o teor
sobrescrevia a folha — corrigir uma vírgula com o campo em branco apagava a folha do ato, sem
aviso. Junto disso, nada impedia dois atos na mesma folha, nada impedia lavrar na folha 350 de um
livro de 200, e o `folha_atual` de todo livro nascia em 1 e morria em 1.

**A regra que você fixou**, e que o sistema agora aplica: cada ato começa em folha nova, conta-se
frente e verso, o ato ocupa folhas inteiras (páginas sempre pares), o termo é contínuo por série
e não reinicia, e livro cheio encerra e o seguinte abre sozinho.

**A decisão de desenho que mais mudou o fluxo**: o ato nasce `EM_LAVRATURA`, sem livro, sem folha
e sem termo, e recebe os três de uma vez no **lançamento**, quando o teor está pronto e se sabe
quantas páginas ele tem. Folha reservada para ato que não se lavrou vira buraco no livro, e
buraco não se explica em correição.

Novo módulo `notas_livro.py`, nova tabela `nt_termos` (contador de termo, no mesmo desenho do
`ri_numeracao` do Registro de Imóveis), dois índices únicos **parciais** — a condição
`IS NOT NULL` deixa o acervo de fora, senão o índice se recusaria a criar por causa das folhas
repetidas do livro 27 e a atualização morreria na largada.

### O que a revisão adversarial ensinou

Escrevi 54 testes, todos verdes, e mandei um revisor cético procurar defeito. **Achou doze.** Os
três que mais importam:

- a guarda "já está lançado" perguntava pelas colunas **novas**, que o acervo não tem. Os 258
  atos do E-Ofício passavam direto, e a tela ainda **oferecia o botão**, porque também decidia
  "é rascunho?" pela coluna nova. Um clique reescrevia a folha 139 de uma escritura de 2011;
- `lancar_ato` fazia `situacao='LAVRADO'` sem perguntar: uma **procuração revogada** voltava a
  valer, e voltava para a remessa da CENSEC, que filtra por lavrado;
- livro com `folhas` nulo — que a própria importação produz — era **encerrado sozinho** no
  primeiro lançamento, com termo dizendo que tinha "0 (zero) folhas".

A lição, e é a que quero deixar escrita: **guarda de integridade tem de perguntar pelo estado do
negócio, não pela coluna que o código acabou de inventar.** Coluna nova é nula no acervo inteiro,
e o acervo é a maior parte do banco.

O revisor também mostrou que meu teste de concorrência não testava concorrência: dava
`commit()` no primeiro antes de abrir o segundo. Trocado por quatro threads e quatro conexões de
verdade, dezesseis lançamentos simultâneos.

Testes: 210 → **384**. Ruff limpo nos arquivos tocados. Nenhuma regressão: os erros que a suíte
acusa fora deste ambiente são de templates que eu não tinha copiado, não de código.

### O que ficou registrado como pendente

Em `docs/tecnico/REVISAO_MODULO_NOTAS.md`, na ordem de ataque. O primeiro é o que mais pesa:
**`nt_ato_anotacoes` existe no esquema e ninguém a usa** — revogação, renúncia e
substabelecimento não são averbados à margem da procuração original. Certidão de procuração
revogada sai sem dizer que foi revogada.

E um achado fora do módulo: o `before_request` do `app.py` abre transação de **escrita** em toda
requisição, inclusive nos GET. Com outro balcão escrevendo, uma tela de leitura espera dez
segundos e devolve 500. É do sistema inteiro, não das notas.


---

## 9. Ainda 17/08/2026 — a margem, o `before_request` e a face riscada

Três coisas, na ordem em que você pediu.

**Anotação à margem.** A revogação era lavrada num livro e a procuração revogada ficava intacta no
outro. Certidão de procuração revogada saía limpa. A tabela `nt_ato_anotacoes` estava no esquema
desde o início e nenhuma linha do sistema a usava. Agora o lançamento da revogação anota sozinho a
margem do ato anterior, na mesma transação, e o traslado transcreve a margem.

**O `before_request`.** Abria transação de escrita em toda requisição. Onze telas de leitura
devolviam 500 depois de dez segundos com outro balcão escrevendo; agora abrem em centésimos.

**A face em branco.** Você perguntou se dava para mexer na fonte para fechar o ato em número par de
páginas. Dá, mas com teto — nenhum ato termina na última linha, então a tipografia muda o branco de
lugar em vez de eliminá-lo. O caminho que resolve o incômodo é o outro: a face que sobra sai
**impressa já inutilizada**, com traço, dizer e linha de assinatura. A sugestão de entrelinha ficou
na tela, dentro da banda de 10% que você autorizou, e explicitamente marcada como sugestão — para
aplicá-la sozinho seria preciso medir a página, e o sistema hoje estima.

### O que a segunda revisão adversarial ensinou

Doze achados de novo, e os três piores foram todos da mesma família: **código que confia num
identificador fraco**.

- A busca do ato anterior casava por `(livro, folha)`. Uma revogação de procuração encontrou como
  "único candidato" uma **escritura de compra e venda de R$ 150.000** no livro 27 de escrituras,
  marcou-a como REVOGADA e escreveu na margem dela. O `livro_id` estava preenchido e resolveria — a
  função simplesmente não o usava.
- `vincular_anterior` duas vezes deixava **duas** procurações revogadas: a segunda sobrescrevia o
  vínculo, mas a anotação da primeira não sai, porque anotação não se apaga. E o gesto é o mais
  natural do balcão: clicar na linha errada, voltar, clicar na certa.
- A trava de "uma vez por dia" fazia obrigação **diária** atrasar para sempre: `ensure_recurring_tasks`
  avança um vencimento por chamada, e todo fim de semana perdia dois dias. Em oito semanas, quinze
  dias de deriva. A docstring que eu tinha escrito — "rodar cem vezes produz o mesmo resultado de
  rodar uma" — era falsa, e eu não tinha medido antes de escrevê-la.

**A lição desta rodada**, diferente da anterior: quando o código passa a decidir sozinho, o
identificador que ele usa para decidir precisa ser tão forte quanto a decisão. Livro e folha
identificam um ato dentro de uma série; fora dela, identificam qualquer coisa.

Testes: 384 → **443**.

---

## 10. O manual — 17/08/2026

Você pediu um manual completo: todas as funções, todas as formas de resolver problema, e como
praticar, editar e cancelar **todos** os atos administrativos, notariais e registrais que o sistema
faz. Escolheu HTML navegável mais `.docx` para encadernar, na profundidade completa — balcão,
administração e TI.

Saiu com **39 mil palavras**, treze capítulos, **127 páginas** no formato de encadernação.

### Como foi escrito, e por que isso importa

Não foi escrito de memória. Antes de qualquer parágrafo, o sistema foi **relido por dentro**, tela
por tela, rota por rota: o que cada botão faz, que campo é obrigatório, o que o servidor aceita
apesar de a tela dizer que não, e **qual é a mensagem exata** que aparece. As mensagens estão no
manual copiadas ao pé da letra, entre aspas, porque o escrevente procura no manual a frase que viu
na tela — e frase parecida não serve.

O contrato de escrita ficou no `ESTILO.md`, dentro do `MANUAL_FONTE.zip`. Toda tela tem o mesmo
molde: **Onde fica · Quem pode · Para que serve · Como fazer · O que o sistema faz sozinho · Como
corrigir · Como cancelar ou desfazer · O que a tela diz, e o que significa.** A seção "Como cancelar
ou desfazer" é a única que **nunca** pode ser omitida — e é onde o manual mais custou a ser escrito,
porque a resposta honesta, muitas vezes, é "não há".

### O que o manual documenta e o sistema ainda não conserta

Escrever a seção "Como cancelar ou desfazer" de cada tela obrigou a listar, de uma vez, tudo o que
não tem volta. O apêndice `90-desfazer.md` reúne a lista inteira. Alguns itens são **decisão**
— ato lavrado não se edita, auditoria não se apaga, encerramento não se reabre, e é assim que deve
ser. Outros são **falta**, e o manual os nomeia como falta, com todas as letras:

- **Delegatários — "remover" apaga sempre o primeiro da lista.** Todas as linhas da tabela estão
  dentro do mesmo formulário, e o servidor lê o primeiro valor. A confirmação do navegador cita o
  nome certo, o que torna o defeito pior do que se não citasse nada.
- **Delegatários — "Guardar" apaga início, fim e confirmado de todas as linhas**, porque os três
  campos não existem no formulário e o código grava o que não veio.
- **Cancelar certidão existe na rota e não tem botão em tela nenhuma.**
- **Encerrar protocolo existe na rota e não tem botão em tela nenhuma.**
- **Recibo da DOI:** o registro é aplicado à competência; não havendo remessa gerada, nada acontece
  e a mensagem de sucesso aparece do mesmo jeito.
- **Comprovante de prenotação de REURB-S** imprime "20 dias úteis" no texto, com a data-limite de 40.
- **A marca REURB-S não é gravada** — some depois da prenotação.
- **`conferido_por` nunca é gravado**; quem conferiu a matrícula só existe na auditoria.
- **CNM não é gerado nem validado** — as duas funções existem em `ri_schema.py` e ninguém as chama.
- **`manutencao_diaria_erro`** é gravado e **nenhuma tela o exibe**: a manutenção pode estar falhando
  há semanas sem ninguém saber.

Nenhum desses foi corrigido nesta rodada. Estão no manual porque **defeito documentado é defeito que
o balcão contorna; defeito calado é defeito que o balcão descobre no pior dia**.

### Duas coisas que o manual repete de propósito

**O servidor roda como SYSTEM.** Aparece no capítulo das fichas digitalizadas, no das matrículas em
Word, no do backup e no de operação — porque é a mesma armadilha aparecendo em quatro lugares
diferentes, e quem lê só um capítulo precisa dela ali.

**O backup automático não é agendado.** Roda uma vez por processo, na primeira requisição depois que
o servidor sobe. Servidor ligado três semanas sem reiniciar são três semanas sem backup novo. Está
dito no capítulo de administração e outra vez no de operação, com o contorno: agendar o
`BACKUP_AGORA.cmd` no Agendador de Tarefas.

### O que ficou de fora, e é honesto dizer

O teor dos artigos do Código de Normas do Foro Extrajudicial do Maranhão (Prov. COGEX/TJMA 28/2026)
não pôde ser lido inteiro em fonte primária. Onde havia dúvida, o manual cita a **seção**, não o
número do artigo. **Nenhum número de artigo foi inventado** — e a abertura do manual diz isso ao
leitor, para que ele não se apoie no que não sustenta.

### Os arquivos

- `docs/tecnico/MANUAL_CARTORIO_GESTAO.html` — arquivo único, sem internet, sumário lateral com
  filtro, índice de 143 mensagens do sistema.
- `docs/tecnico/MANUAL_CARTORIO_GESTAO.docx` — A4 com margem de encadernação, capítulo em folha
  nova, rodapé numerado, sumário que o Word preenche ao abrir.
- `docs/tecnico/MANUAL_FONTE.zip` — um Markdown por capítulo, o `ESTILO.md` e os três scripts que
  remontam os dois formatos. **Editar o manual é editar o `.md`**; o HTML e o `.docx` são saída.

O índice de mensagens é gerado varrendo as tabelas "O que a tela diz" dos demais capítulos. Mensagem
nova num capítulo entra no índice sozinha, na próxima geração.
