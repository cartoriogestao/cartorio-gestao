# O padrão de importação da casa

**Relato #31 do oficial, 30/08/2026:**

> «criar manual e padrão de importação de acervo antigo e preenchimento de atos
> novos, possivelmente por json ou XML (…) para importar atos de outros sistemas
> ou preenchimento de formulários de cadastramento de partes ou objeto, seja no
> RI (matrículas), seja no RCPN (nascimentos, etc) ou outras atribuições.»

Este documento é o que se entrega a **quem vai gerar o arquivo** — o técnico do
outro sistema, a serventia de origem, quem converteu a planilha. A tela
*Livros e acervo → Importar de outro sistema* mostra o mesmo, montado do banco
de hoje.

---

## O que já existia, e por que não servia como padrão

Esta casa tem **três** importadores que leem JSONL — `ri_import`,
`notas_import` e `caixa_import` —, e eles funcionaram: foi por eles que entraram
as 1.701 matrículas, os 4.061 cartões de autógrafo e os 18.396 lançamentos de
caixa.

**Mas nenhum dos três é um padrão**, por três motivos medidos:

1. **Os nomes dos campos são os do E-Ofício.** Quem exporta de outro sistema não
   tem como adivinhar `strNomeConjuge1` nem `intCodigoLocalNascimento`.
2. **Cada um tem o seu conjunto de arquivos** — `matriculas.jsonl`,
   `firma_cartao.jsonl`, `protocolo_custas.jsonl` —, e nenhuma lista diz quais
   são nem o que vai dentro.
3. **Dois dos três não têm tela.** `caixa_import` tem; os outros dois são função
   pronta que nenhuma tela chama — o defeito que mais se repetiu neste projeto.

Eles **ficam**, porque leem o que já foi exportado do E-Ofício e essa exportação
existe. O que este padrão acrescenta é o caminho para **os outros sistemas**.

---

## As decisões de forma, e por quê

**JSON, e não XML.** O oficial ofereceu os dois. Os três importadores desta casa
já usam JSON, e o precedente da casa desempata — mais: um JSON se abre no Bloco
de Notas e se confere a olho, e um XML de registro civil vem com espaços de nome
que quem o produz erra na primeira tentativa. **A carga da CRC continua em
XML**, porque lá quem manda no formato é a Central.

**Um arquivo só, e não um por tabela.** Sete arquivos JSONL são sete chances de
mandar seis.

**Os campos são os nomes das colunas do banco**, sem camada de tradução. Nesta
casa as colunas já se chamam `nome`, `data_ato`, `cor_raca`,
`naturalidade_declarada`. Traduzir de novo criaria duas listas para divergirem
no primeiro conserto.

**E a lista dos campos é medida do esquema, não escrita.** Lista de campo escrita
à mão noutro arquivo envelhece na tarde em que se escreve — foi assim com o menu,
com as cargas, e com o teste que devia guardar as duas. Coluna nova aparece na
tela e neste manual sozinha, no dia em que nasce. **Por isso a lista de campos
não está transcrita aqui**: ela está na tela, sempre atual.

---

## A forma do arquivo

```json
{
  "formato": "CARTORIO_GESTAO_IMPORTACAO",
  "versao": 1,
  "especie": "RCPN_ASSENTO",
  "de_onde_veio": "Serventia de Fulano — sistema Beltrano, exportação de 30/08/2026",
  "registros": [
    {
      "chave": "1955-A-12",
      "serie": "RC_A",
      "especie": "NASCIMENTO",
      "numero": "12",
      "nome": "PESSOA EXEMPLO",
      "data_ato": "1955-10-12"
    }
  ]
}
```

| campo do cabeçalho | o que é |
|---|---|
| `formato` | sempre `CARTORIO_GESTAO_IMPORTACAO`. Sem ele o arquivo é recusado — importar às cegas é como o dado de outro sistema entra errado sem ninguém ver |
| `versao` | hoje, `1` |
| `especie` | o que se está importando — as seis abaixo |

### As seis espécies

**Quatro delas entraram em 07/09/2026, por pedido do oficial** — relato #40:
*«ampliar o importação de outro sistema para demais atribuições — fornecer
documentação para importação também do RTD, RCPJ, notas e protesto»*.

| `especie` | traz | para a tabela |
|---|---|---|
| `RCPN_ASSENTO` | assento do Registro Civil — nascimento, casamento, óbito | `rc_assentos` |
| `RI_MATRICULA` | matrícula do Registro de Imóveis | `ri_matriculas` |
| `RCPJ_RTD_REGISTRO` | registro do RCPJ ou do RTD | `rg_registros` |
| `NOTAS_ATO` | ato do Tabelionato — escritura, procuração, ata | `nt_atos` |
| `PROTESTO_TITULO` | título de protesto | `pt_titulos` |
| `LIVRO3_REGISTRO` | registro do Livro 3 — Registro Auxiliar | `ra_registros` |

**OS CAMPOS DE CADA UMA NÃO ESTÃO ESCRITOS AQUI, E É DE PROPÓSITO.** Eles são
**medidos do esquema** na hora, e a tela de importação mostra a lista de cada
espécie com o que é obrigatório e o que é data. Escrevê-los neste documento
daria duas listas — e a deste arquivo envelheceria na tarde em que uma coluna
fosse acrescentada, mandando a serventia de fora preparar um arquivo com um
campo que o sistema não lê mais.

**Peça o modelo em branco na própria tela**: ele sai com todos os campos
daquela espécie, já com a marca do formato e a versão.

> **E O CADASTRO APONTAVA PARA DUAS TELAS QUE NÃO EXISTIAM.** Ao acrescentar as
> quatro, medi as duas que já havia: `tela` valia `atrib_rcpn_ficha` e
> `ri_matricula`, e **nenhum dos dois é rota deste sistema** — os reais são
> `rcpn_assento` e `ri_ficha`. Não estourava porque **ninguém lia o campo**, e
> é isso que o tornava perigoso: valor errado num cadastro com cara de
> autoridade, esperando quem fosse ligar «depois de importar, abra a ficha».
> É o defeito que o `inacabados` teve em duas das nove fontes, e agora tem a
> mesma guarda — `tests/test_importar_padrao_modelos.py` confere endpoint,
> template e tabela das seis.
| `de_onde_veio` | texto livre, para ficar registrado na auditoria |
| `registros` | a lista |

### O `chave` de cada registro

**Todo registro precisa de um `chave`**: é o número dele no sistema de origem.

É ele que impede o mesmo registro entrar duas vezes se o arquivo for mandado de
novo — e mandar de novo é justamente o que se faz depois de corrigir o que foi
recusado. Registro sem `chave` é recusado.

`chave` **não é coluna de nenhuma tabela importável**, e há teste que confere
isso: no dia em que fosse, o campo do arquivo teria dois donos.

---

## O que o sistema recusa, e por quê

Cada recusa vem **com o número da linha e o motivo**, e **o recusado não derruba
o que passou** — é a regra da carga do acervo e da remessa da CRA: registro ruim
não impede os bons de entrar.

| recusa | por quê |
|---|---|
| **campo que a espécie não conhece** | errar o nome de um campo é o erro mais fácil de cometer e o mais difícil de perceber: quem preparou o arquivo acha que mandou o dado, e ele não entrou em lugar nenhum |
| **falta campo obrigatório** | a tela diz quais são; o arquivo diz `OBRIGATÓRIO` neles |
| **data fora de `AAAA-MM-DD`** | `12/10/1955` e `1955-10-12` ordenam diferente, e a data errada num assento vira certidão errada |
| **sem `chave`** | sem ela não há como impedir a duplicação |
| **`chave` repetida no próprio arquivo** | duas linhas disputando o mesmo registro |
| **campo que a máquina controla** (`id`, `criado_em`, `origem`, `*_norm`) | `id` deixaria o arquivo passar por cima de registro alheio; `criado_em` deixaria o acervo dizer que entrou ontem; um `nome_norm` que não corresponda ao `nome` faria a busca deixar de achar a pessoa, calada |

Chave que **já está no banco** não é recusa: é `repetido`, e é a chave de origem
fazendo o que existe para fazer.

---

## O que este padrão NÃO faz

**Não lavra ato, não numera, não sela e não cobra.** Ele traz **acervo**: o
registro que chega já tem número, livro e folha, vindos do livro de papel de onde
veio. Mandar o núcleo achar lugar reescreveria a história — é a mesma regra de
`acervo_carga`, e há teste que varre o módulo procurando `obter_selo`,
`proximo_numero` e `cobrar`.

**Não conserta o que vem errado.** Adivinhar o que o outro sistema quis dizer é
como o dado errado entra com cara de certo.

---

## Como se usa

1. *Livros e acervo → **Importar de outro sistema*** (só ADMIN)
2. Escolha a espécie. A tela mostra **o exemplo montado do banco de hoje** e a
   lista de campos, dizendo quais são obrigatórios
3. **Envie o arquivo `.json`** — ou cole o conteúdo, se for pequeno — e clique
   em **Conferir**
4. Leia o quadro: quantos entram, quantos foram recusados e por quê
5. Só então **Importar**

**O UPLOAD FOI ACRESCENTADO EM 13/09/2026** — relato do oficial: *«não achei
ponto para importar o arquivo, só digitando ele na tela»*. A tela só tinha
`<textarea>` desde que nasceu, e um lote de acervo tem milhares de registros —
ninguém cola isso à mão. O arquivo enviado vira o mesmo texto que o textarea já
usava (`request.files.get("arquivo")`, o mesmo padrão de outras 14 rotas do
sistema); **e a resposta não ecoa o arquivo de volta no textarea** quando ele é
grande (acima de 200 KB) — devolver um upload de 11 MB dentro do HTML da
página deixaria a tela pesada só para reaparecer numa caixa que ninguém edita.

**Conferir e importar são dois botões, e não um.** Aqui não há como desfazer,
porque acervo importado vira o livro — um clique só faria alguém gravar
cinquenta registros que nunca viu. É a mesma separação da remessa da CRA.

---

## A segunda metade: preencher o formulário do ato novo

O relato #31 tem duas metades. A primeira é a de cima — **importar acervo**.

A segunda é *«preenchimento de formulários de cadastramento de partes ou
objeto»*, e o oficial escolheu como fazê-la em 30/08/2026: **o mesmo padrão,
jogando os dados na tela em vez de gravar direto**.

Na tela do padrão, ao lado de *Conferir*, há o botão **Preencher o formulário do
ato novo**. Ele leva o registro para a tela de lavrar, já preenchida.

### São dois caminhos, e a diferença não é de conveniência

| | *Importar* | *Preencher o formulário* |
|---|---|---|
| o que entra | **acervo** — o registro como ele veio | um **ato novo** |
| o número | o que ele já tinha | o próximo da serventia |
| folha, selo, custas | nada disso acontece | toma folha, sela e cobra |
| quantos por vez | quantos o arquivo trouxer | **um** |
| quem decide | o arquivo, conferido antes | **quem lavra**, que confere e assina |

Confundir os dois faria nascer ato novo com número de outra casa — ou acervo
histórico consumindo folha de segurança de hoje.

### O que ele recusa, e por quê

**Um registro de cada vez.** Um arquivo com trinta preencheria a tela com o
primeiro e calaria os vinte e nove — e quem mandou acharia que os trinta
entraram. Para vários, o caminho é a importação.

**As mesmas recusas da importação.** Campo desconhecido, falta de obrigatório,
data fora de forma: tudo o que não entraria pela importação também não preenche.

### O que ele diz, em vez de calar

**O que o arquivo trazia e a tela não pergunta fica escrito no aviso.** A tela do
assento não pergunta tudo o que a tabela guarda — a `serie`, por exemplo, vem da
espécie e não se digita. Descartar em silêncio faria o escrevente assinar achando
que aquele dado está lá.

**E a lista do que a tela pergunta é medida do próprio modelo de tela**, e não
escrita: escrita, ela envelheceria no dia em que a tela ganhasse um campo, e o
preenchimento passaria a calar justamente o campo novo.

### O que ele não faz

**Não grava.** Ele preenche a tela; lavrar continua sendo um clique de quem
assina, com todas as regras de lavratura no lugar.

**Não guarda o dado depois de usar.** O preenchimento é consumido de uma vez: se
ficasse guardado, o formulário do próximo cliente abriria com os dados do
anterior, e alguém lavraria assento com o nome de outra pessoa.

**Não manda dado de pessoa pelo endereço.** Nome, data de nascimento e endereço
numa `query string` ficariam no histórico do navegador do balcão e no registro
do servidor.
