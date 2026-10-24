# O que fazer agora, na ordem

**15/08/2026.** Tudo abaixo está construído e testado fora do ar. Nada disso está valendo no
sistema enquanto o `ATUALIZAR_SISTEMA.cmd` não rodar.

---

## 1. Atualizar o sistema — `ATUALIZAR_SISTEMA.cmd`

Pede administrador (o Windows vai perguntar; confirme **Sim**). É o único passo que não posso
fazer sozinho.

### O Tabelionato de Notas entrou

Menu novo, com quatro telas: **Tabelionato de Notas** (painel), **Reconhecer firma**,
**Autenticar cópia** e **Cartões de autógrafo**.

O caminho do balcão: procura o cartão pelo nome ou pelo CPF, a assinatura digitalizada aparece
na tela para conferência, marca quem está reconhecendo e pronto — o emolumento sai da tabela do
tribunal, sem ninguém digitar valor. Não havendo cartão, abre um ali mesmo.

O sistema recusa selo já usado em outro ato, avisa antes de reconhecer com cartão bloqueado, e
impede que cartão restrito a autenticidade saia como semelhança — dizer uma espécie pela outra
não é questão de estilo.

Antes de usar, rode a carga do acervo em **Trazer notas do E-Ofício**: 4.060 cartões de
autógrafo, 3.637 assinaturas digitalizadas, 13.209 reconhecimentos, 3.539 autenticações, 213
procurações, 45 escrituras e 301 modelos de texto. Pode rodar quantas vezes precisar.

### E o resto desta rodada:

- **Identificação da serventia num lugar só** (`serventia.py`), tirada do papel timbrado que
  você mandou. Aparece no recibo, no orçamento, no protocolo de recepção, no comprovante de
  prenotação e no topo das telas de caixa, protocolo geral, depósito prévio e prenotação.
- **Protocolo de recepção** — documento novo, imprime pelo botão na tela do protocolo.
- **Comprovante de prenotação** — documento novo, imprime pela lista do protocolo do RI.
- **Dados do documento apresentado** — tipo, número e descrição, no protocolo geral e na
  prenotação.
- **LGPD**: CPF, telefone e e-mail saem mascarados em todo papel que deixa o cartório.
- **Assinatura dupla** no orçamento, no protocolo de recepção e no comprovante de prenotação:
  funcionário (com a função que exerce) e requerente.
- **Função de cada usuário**, cadastrável na tela **Usuários**.
- Correção do risco solto no topo do recibo, do orçamento e da certidão (o cabeçalho vazio
  reservava 3,2 cm e desenhava a linha de baixo).
- E o que já estava pendente da rodada anterior: importação incremental do caixa, orçamento,
  quitação item a item, número do depósito prévio, correção da importação da tabela de
  emolumentos.

---

## 2. Cadastrar a função de quem atende — menu **Usuários**

Coluna nova **Função**. O que estiver ali é o que sai impresso embaixo da assinatura no
orçamento, no protocolo de recepção e no comprovante de prenotação. As opções seguem a Lei
8.935/94, arts. 20 e 21:

- Tabelião e Oficial de Registro
- Substituto
- Escrevente Autorizado
- Escrevente
- Auxiliar

Sem preencher, o sistema imprime "Escrevente" — que é o que menos afirma. Quem assina por
delegação tem de dizer em que qualidade assina, então vale a pena preencher os três usuários.

---

## 3. Conferir o timbre

O cabeçalho foi montado a partir da foto do papel timbrado. Onde ele divergia do `C11.INI` do
E-Ofício, ficou o timbre — o INI trazia CEP genérico 65000000, o timbre traz 00000-000.

Confira nas amostras da pasta `AMOSTRAS_DOCUMENTOS`:

| Campo | Está assim |
|---|---|
| Nome | SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO |
| Titular | Tabelião e Oficial de Registro: OFICIAL |
| CNPJ | 00.000.001/0000-55 |
| CNS | 000000 |
| Telefone | (00) 0000-0000 |
| Endereço | Av. Exemplo, 85, Centro, CEP 00000-000, Cidade Exemplo-MA |
| E-mail | conta.google@exemplo.invalid |

Havendo erro, corrige-se em **Configurações**, sem mexer em código — o padrão só entra quando
o campo está vazio.

---

## 4. Cadastrar os delegatários — **é o que destrava a impressão da ficha**

Menu **Delegatários**. A tela está vazia e oferece um começo com três nomes:

| Nome | Cargo | De onde saiu | O que falta |
|---|---|---|---|
| OFICIAL | Titular | você disse que assumiu em julho de 2026 | o dia exato |
| ESCREVENTE | Substituta | assina os atos no modelo de 31/07/2026 | desde quando |
| TITULAR ANTERIOR | Titular anterior | consta no `C11.INI` do E-Ofício | início e fim |

**Só você sabe as datas.** Enquanto o período não estiver preenchido, o ato antigo sai **sem o
fecho** — sem "Dou fé" e sem nome. É de propósito: ficha sem nome é melhor do que ficha
atribuindo a alguém ato que não praticou.

O acervo vai de **15/10/1985 a 2026**. Se houve outros delegatários nesses quarenta anos, eles
precisam entrar aqui, cada um com seu período.

---

## 5. Trazer as matrículas digitadas em Word

`EXTRAIR_MATRICULAS_DOC.cmd`, na pasta Downloads. Roda no Windows porque os arquivos estão no
serviço de nuvem e chegam como marcador de nuvem — de dentro do meu ambiente eles não abrem.

São **1.097 matrículas** que existem na pasta e não estão no acervo importado do E-Ofício.

---

## 6. Conferir a pasta das assinaturas

As imagens ficam em disco, não no banco. O sistema procura em `C:\ARPNET\C11\Firmas` e em
`\\servidor\C11\Firmas`. Se a máquina que abre a tela não enxergar nenhuma das duas, a
assinatura não aparece e o cartão avisa — nesse caso, informe o caminho certo em
**Configurações**, na chave `nt_pasta_firmas`.

Sete imagens estão descasadas: duas citadas no banco não existem em disco, cinco em disco não
têm registro.

---

## 7. O que fica para depois

- **Domínio do `intQualifica`** do E-Ofício — a hipótese de que fosse `tbTabelas` não se
  confirmou; `tbTabelas` é a tabela de emolumentos.
- **Módulo de RI** (do `REVISAO_MODULO_RI.md`): Livro 3, livro de estrangeiros, termos de
  abertura e encerramento, suspensão da prenotação pela dúvida, ~20 atos do art. 167 ainda sem
  modelo, remessas periódicas.
- **Notas — lavratura de escrituras, procurações, testamentos e atas**, com a biblioteca guiada
  a partir dos 301 modelos importados.
- **Notas — remessas às centrais**: CENSEC (CEP, CESDI, RCTO), e-Notariado e DOI. Os domínios já
  estão carregados com os códigos oficiais do próprio E-Ofício.
- **CIB e SINTER** — obrigatórios a partir de janeiro de 2027.

---

## Onde estão as amostras

Pasta `AMOSTRAS_DOCUMENTOS`, ao lado deste arquivo: os cinco documentos em `.odt` e em `.pdf`,
preenchidos com um caso fictício, para você conferir o texto e o layout antes de usar no
balcão.
