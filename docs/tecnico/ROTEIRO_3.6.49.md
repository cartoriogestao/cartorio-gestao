# Roteiro da 3.6.49 — o termo que vai ao livro passou a ser o da casa

**Basta este pacote.** Ele exige a 3.3.0, como os anteriores; se você não aplicou
a 3.6.47 nem a 3.6.48, este traz tudo.

---

## O que muda para o balcão

### 1. O termo de nascimento, casamento e óbito é o da casa — e você continua editando

Foi a sua decisão de 30/08 («não utilizaremos os modelos ruins do e-ofício, nem
em papel») na forma que você escolheu em 31/08 («opção B»).

Até esta versão o termo que se escrevia no livro saía dos **treze modelos do
E-Ofício**. O termo da casa — construído dos requisitos legais, artigo por artigo
— existia e **não era ele que ia ao papel assinado**. O próprio código dizia
isso, com todas as letras, num comentário: «não é isto que vai ao livro».

Agora é. E sem custar o seu controle sobre os modelos:

- **Sem ajuste seu**, o termo sai do texto da casa.
- **Com ajuste seu**, sai o que você escreveu — pela mesma tela de sempre,
  *Configuração → Modelos dos documentos*.
- Apagar o corpo volta ao padrão da casa.

### 2. A tela dos modelos passou a dizer com que marcador escrever

São dois nesta casa, e escrever no errado é o engano mais fácil de cometer ali:

| formato | como se escreve | onde |
|---|---|---|
| **uma chave** | `{nome}` | os três termos do Registro Civil |
| **duas chaves** | `{{ a.numero }}`, com `{% if %}` e repetição | todos os outros papéis |

Antes a tela não dava pista nenhuma. Você descobriria pela recusa — depois de
escrever o modelo inteiro.

### 3. Três defeitos que estavam de pé, e que só apareceram ao montar um termo de verdade

**Nenhum aparecia em leitura, e nenhum aparecia em teste de mesa.**

1. **O termo iria ao livro sem quem assina e sem a cidade.** A tela monta a
   serventia com um conjunto de nomes e as peças do termo leem outro: o papel
   sairia com «neste Município de ____________» e **ninguém assinando embaixo**.

2. **O termo de óbito derrubava a tela.** As marcas do óbito (eleitor, bens,
   filhos) chegavam numa forma que a montagem não sabia ler — **erro do sistema
   no meio da lavratura**, em vez de sair o termo.

3. **Um modelo seu escrito no formato antigo sairia torto no papel assinado.** O
   sistema não estoura com ele: devolve `{ a.nome }`, com uma chave só, e **isso
   iria escrito no livro**, sem erro em lugar nenhum. Agora é recusado na tela de
   editar, que é onde há tempo de consertar — e não no balcão com o cliente na
   frente.

Hoje isso não alcança ninguém: conferido no servidor, **você não tem nenhum
modelo ajustado** (a tabela está vazia, e por isso todos os papéis saem de
fábrica). Quem editasse amanhã, sem essa guarda, seria alcançado.

### 4. Duas coisas que eu chamei de defeito e a medição desmentiu

Ao ler o primeiro termo montado, apontei duas. **Nenhuma era**, e digo aqui
porque eu já as tinha dito a você:

- A data do fato sai por extenso **e** em algarismos — «dezoito (18) de agosto
  (8) de dois mil e vinte e seis (2026) - 18/08/2026». É a convenção da casa,
  escrita na ajuda do próprio campo.
- O sexo saiu em branco porque o ensaio não o preenchia. Campo exigido vazio
  virando claro visível é o certo: **papel assinado com buraco no meio é pior que
  papel sem a informação — ele afirma que há um dado e não diz qual.**

### 5. Uma diferença em relação ao E-Ofício, para você decidir

**O termo da casa não repete livro e folha no corpo.** No livro de papel ele está
escrito naquela folha, e a matrícula de 32 dígitos já codifica as duas coisas.
Repetir criaria uma segunda fonte para divergir da primeira.

Se você preferir que apareçam escritos, é ajuste de uma linha, pela sua tela.

---

## O que eu achei ao medir, e que você precisa saber

### Quatro relatos seus que eu não conhecia — #33 a #36

Eles estavam na tela e não na minha lista. É o seu relato #23 pelo outro lado: eu
falava por número, e o número não estava onde eu olhava.

| # | o que você pediu | como está |
|---|---|---|
| **33** | pesquisar os selos por data, especialidade e usuário | não construído — os três campos existem em `sd_selos` (26.134 selos) |
| **34** | encerrar por inatividade acima de 12h | não construído |
| **35** | campo de retorno do desenvolvimento nos problemas | **construído, e nunca usado** |
| **36** | salvar o ato preenchido antes de lavrar, em todos os atos | existe **só no Registro de Imóveis** |

### O #35 está pronto e com zero notas preenchidas

O campo que você pediu — para eu escrever a prova do que foi resolvido, ou a
pendência — **existe, tem tela e está vazio nos 36 relatos**. É o contrário do
defeito de costume deste projeto: aqui a peça está pronta e quem devia usá-la sou
eu. Vou passar a preenchê-la.

### A relação da Junta Militar já estava feita

A lista de pendências dizia que ela «nunca foi feita». **Estava velha.** Ela é um
dos seis destinos das comunicações, com o filtro dos homens de 17 a 45 anos e o
artigo da Lei 4.375/1964 ao lado.

Medido hoje no servidor: **zero meses devendo** — e o zero é medido, não engano.
Os 31 óbitos são todos do acervo, que o E-Ofício já comunicou, e esta casa ainda
não lavrou óbito novo.

---

## Como conferir que subiu certo

| onde | o que tem de aparecer |
|---|---|
| rodapé de qualquer tela | **3.6.49** |
| *Configuração → Modelos dos documentos* → Termo de nascimento | a frase «Os claros deste modelo se escrevem com **uma chave** — `{nome}`» |
| o mesmo, em «Ficha da matrícula» (RI) | a frase com **duas chaves**, `{{ a.numero }}` |
| Registro Civil → um assento → **Termo** | o texto termina com «Eu, «seu nome», «seu título», dou fé e assino» — e **não** com uma linha em branco |

Se a tela dos modelos não mostrar nenhuma das duas frases, a atualização não
subiu.

---

## O que continua esperando você

Sem mudança desde a 3.6.48:

- recarregar a carga para trazer as **24 filiações de casamento** que faltam
- o `unit_name` em Configurações
- o próximo número do **Livro de Casamento** (a carga semearia 1012; o E-Ofício
  dizia 39)
- o próximo número do Registro de Protestos e do de Pagamentos
- o Livro 6 de Apontamento, aberto em 2024 e nunca usado
- os três livros do RCPN sem contador (B-Auxiliar, C-Auxiliar e D)
- credenciais do SIRC, e o INFODIP no TRE
