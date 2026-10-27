# O dia do Protesto, como ele se faz — trazido pelo oficial

Em **25/08/2026** o oficial pôs na pasta o roteiro do protesto da serventia em
que trabalhou antes. Ele vale mais do que parece: **isto não está no acervo**.
O `acervo_eoficio.sqlite3` guarda o que foi lavrado, e não a ordem em que se
lavra; nenhuma medição sobre ele contaria que o retorno e o andamento saem em
par, ou que a conferência de desistências acontece três vezes ao dia.

O texto está transcrito abaixo, inteiro e sem retoque, e depois dele o que já
foi feito e o que ainda falta.

---

## O que o oficial escreveu

```
(começou termina)

- DOWNLOAD REMESSA CRA
- UPLOAD REMESSA FEBRABAN EPROTESTO
- GERAR RESPOSTA E-PROTESTO E SUBIR NA CRA
- EMITIR AVISO INTIMAÇÃO
- gerar aviso, verificar "emitir aviso" para coobrigados sem boleto, depois
  ativa boleto e clica em registrar boletos e emitir aviso
  (sempre verificar se aparecem erros)
- SEMPRE QUE GERAR RETORNO (FINAL), GERAR ANDAMENTO
- gera intimação, edital, arquivo edital no cenprot e impresso na parede.
- gerar protesto, sem movimentação, calcular, listar, gerar.


PASSOS ELEMENTARES DIÁRIOS:
*** MANHÃ: 1) Arquivo banese e desistências; 2) arquivos de retorno e de
    andamento
*** MEIO DIA (das 11h às 13h): 1) recebimento de remessa, confirmação e emissão
    do aviso; 2) verificação de desistências
*** TARDE: 1) verificar desistências; 2) gerar protesto, assinar instrumento
    eletrônico do protesto na CENPROT; 3) enviar e aprovar arquivos CENPROT
    (xml); 4) enviar arquivo de emolumentos.
```

---

## O que ele ensinou, e que a medição não ensinaria

**"SEMPRE QUE GERAR RETORNO (FINAL), GERAR ANDAMENTO."** Em maiúscula, no
original. Os dois arquivos andam em par, e o sistema passou a gerá-los assim:
`protesto_retorno.gerar()` produz o retorno **e** o andamento numa operação só,
com o mesmo conjunto de títulos, e os dois se apontam por `par_id`.

Os layouts sozinhos não contavam isso. `LAYOUT_RETORNO_MEDIDO.md` já sabia que
o andamento é a remessa mais o bloco do retorno — mas não que ele é obrigatório
junto do retorno final. Quem faz protesto todo dia sabe.

**A confirmação é do meio-dia**, junto com o recebimento da remessa:
*"recebimento de remessa, confirmação e emissão do aviso"*. Ela é o recibo do
que chegou, e por isso pertence à entrada e não à saída — `montar_confirmacao`
existe pelo mesmo motivo que `montar_andamento`, e espera a tela da remessa.

**A desistência se confere três vezes por dia** — manhã, meio-dia e tarde. É a
única coisa do roteiro que aparece nos três turnos, e diz o quanto ela é
sensível: título que o apresentante desistiu e a casa protestou é protesto que
se cancela depois, com carta.

**E ela chega num arquivo que não é como os outros quatro** — achado em
25/08/2026 e medido em 26/08, quando o oficial indicou a pasta de rede da serventia:
**127 posições e cinco tipos de registro**, contra 600 e três. O sistema não
conseguia nem abri-lo. Está em `LAYOUT_DESISTENCIA_MEDIDO.md`, e a tela é
*Protesto — desistências*.

**O ciclo do dia tem uma ordem**, e ela é: recebe remessa → confirma → emite
aviso de intimação → verifica desistências → gera protesto → gera retorno **e**
andamento → sobe na CRA.

---

## O que já existe no sistema

| Passo do roteiro | Onde está |
|---|---|
| Recebimento da remessa | **feito** — *Demais atribuições → Protesto — remessa da CRA* |
| **Confirmação** | **feito** — sai junto do recebimento, com o que entrou |
| Emissão do aviso de intimação | **feito** — o aviso sai na ficha; a entrega e o edital em *Protesto — avisos e editais* |
| Verificação de desistências | **feito** — *Protesto — desistências*: o arquivo da CRA se confere e se aplica título a título |
| Gerar protesto | `protesto.lancar_protesto`, na ficha |
| **Retorno + andamento** | **feito** — *Demais atribuições → Protesto — retorno à CRA* |
| Subir na CRA | o arquivo baixa em ISO-8859-1, pronto para subir |

## O passo do meio-dia, e o que ele cobrou — 25/08/2026

A tela da remessa foi construída depois deste roteiro, e por causa dele. O
arquivo se lia no domínio desde o começo; o que faltava era o lugar onde ele
vira ato — **o mesmo achado que se repetiu a revisão inteira**: função pronta e
testada que nenhuma tela chama.

Ela ficou em **Demais atribuições → Protesto — remessa da CRA**, e faz o passo
como o roteiro o descreve: recebe o arquivo, **confere sem gravar nada**, e no
segundo passo cadastra, aponta cada título — protocolo e lugar no Livro de
Apontamento — e **gera a confirmação** para subir na Central.

### O que a construção dela achou, medindo

Três coisas apareceram, e nenhuma teria aparecido sem medir os 197 arquivos
reais desta casa:

**1. Um arquivo pode trazer mais de um lote, e de apresentantes diferentes.**
Seis dos 197 são multi-lote, e em **três** deles os lotes são de apresentantes
distintos — um traz 237, 1LV e 033 juntos. Ler só o primeiro cabeçalho poria os
títulos dos outros dois no primeiro, e o **retorno voltaria para quem não
apresentou**. Pior: o erro não apareceria na entrada. Só meses depois, quando a
Central reclamasse. O arquivo agora se separa em lotes antes de qualquer coisa,
e cada lote é uma remessa com o seu apresentante e a sua confirmação.

**2. Eu recusava 11% do que a Central manda.** Trinta e sete dos 343 títulos
chegam com `99999999` no vencimento — a marca de *sem vencimento* —, todos da
espécie CDA, que é certidão de dívida ativa e não tem vencimento nenhum. Eu
havia posto `data_vencimento` na lista de campos obrigatórios do contrato, e
isso faria o balcão digitar à mão o que vem pronto. **A própria CRA tem palavra
para o caso**: a irregularidade 33 é "Falta data de vencimento no título" —
título sem vencimento é título com irregularidade catalogada, que é motivo para
protestar e não para devolver.

**3. A letra da posição 566 é do retorno, e só dele.** `_montar_saida` a exigia
dos três arquivos de saída, porque é a mesma função para os três. Só que
`reservado_566` existe no layout do **retorno** e em mais nenhum: na confirmação
e no andamento aquela posição cai dentro de `reservado_546`, medido como zeros e
brancos nos 343 registros. Com a exigência, **a remessa de um apresentante novo
não podia ser recebida** — a confirmação pedia uma letra que só se aprende num
retorno anterior, e apresentante novo não tem retorno anterior. Um campo que nem
chega a ser escrito travaria o balcão.

### As decisões, e o motivo de cada uma

**O mesmo arquivo não entra duas vezes**, e a trava mora no banco:
`UNIQUE(hash_arquivo)`. Receber de novo apontaria todos os títulos outra vez —
protocolo dobrado, folha gasta, dois avisos para o mesmo devedor —, e
apontamento não se desfaz. O hash é do conteúdo normalizado, senão o mesmo
arquivo salvo noutro programa passaria por outro.

**Conferir e receber são dois passos**, e o primeiro não grava nada. Cinquenta
títulos que entram sem ninguém olhar são cinquenta atos para desfazer à mão.

**Título ruim não derruba o lote.** Os bons entram; os recusados ficam listados
com o motivo, guardado no próprio lote — quando o apresentante ligar
perguntando por que aquele título não voltou, é essa a resposta.

**A confirmação confirma o que ENTROU**, e isso foi medido: em 138 pares
remessa-confirmação um para um dos arquivos reais, 130 trazem exatamente os
títulos da remessa, 8 trazem menos, e **nenhuma traz título que não veio**.
Confirmação parcial existe; confirmação que inventa título, não.

**A chave de origem é a posição no lote**, e não o nosso número: no acervo, 53
grupos e 111 títulos repetem o `strNossoNumero`. Chavear por ele faria a segunda
apresentação de um título sumir dentro da primeira, calada. Título vivo com o
mesmo nosso número vira **aviso** na conferência, e não recusa — pode ser
reapresentação legítima, e quem decide é quem está no balcão.

**O lote não sela e não cobra.** Selar cinquenta títulos são cinquenta chamadas
de rede de 20 s dentro de um `BEGIN IMMEDIATE`, e a casa inteira ficaria no
`busy_timeout` esperando o lote terminar. Eles entram e aparecem em *atos sem
selo* e *atos sem cobrança*, que são as telas do outro lado e existem para isso.

---

## O que o roteiro mostra que ainda falta

- **O boleto do aviso**: o aviso, a entrega e o edital ficaram prontos em
  25/08/2026 — o que falta é o **boleto**, e o motivo está medido em
  `AVISO_DE_INTIMACAO_MEDIDO.md`: duas coisas do código de barras não se
  explicam, e código de barras errado é dinheiro no lugar errado.
- **O arquivo do edital para o CENPROT**: *"arquivo edital no cenprot"*. O
  edital agora é registro e sai em `.odt` para afixar; o arquivo que sobe na
  Central não tem vestígio no acervo.
- **O XML do CENPROT e o instrumento eletrônico** — **medidos em 26/08/2026**,
  em 903 arquivos e 17.270 títulos do acervo de Sergipe
  (`CENPROT_XML_MEDIDO.md`). E o passo **se aplica a esta casa**: 1.194 dos
  1.370 títulos daqui têm chave única do CENPROT, começando com o IBGE de
  Cidade Exemplo.

  A estrutura está inteira, e o contrato dela já existe em `protesto_cra.py`.
  **Falta uma coisa só, e é uma pergunta e não trabalho**: de onde vem a chave
  única de um título novo. O verificador dela não se explica por regra padrão
  nenhuma, testado em 3.083 chaves. Ou o CENPROT devolve a chave, ou há uma
  regra num manual do IEPTB.

  Foi para a aba **O que falta informar**.
- **O arquivo de emolumentos**, que fecha a tarde.
- ~~O arquivo do Banese, da manhã~~ — **não se aplica a esta casa**, e quem
  disse foi o oficial em 26/08/2026: o arquivo do Banese era do **TJSE**,
  porque lá os pagamentos caíam direto no banco. **No TJMA o pagamento é na
  serventia**, e por isso não há arquivo de banco a receber.

  > Fica registrado porque a pasta de Sergipe tem **881 arquivos do Banese**, e
  > quem os encontrar sem esta nota vai medi-los achando que faltam.

Nenhum desses se resolve por medição do acervo: são fluxos com prazo, arquivo
externo e decisão. Ficam aqui listados para não se perderem, e na ordem em que
o dia os pede.
