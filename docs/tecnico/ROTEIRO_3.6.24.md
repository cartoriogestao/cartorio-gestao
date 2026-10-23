# Roteiro da 3.6.24 — o Registro Civil e a remessa do IBGE

*Serventia Extrajudicial de Cidade Exemplo/MA, CNS 000000 — 28/08/2026*

**2.416 testes, todos passando.** O pacote é `CartorioGestao_3.6.24.cgu`,
SHA-256 `f15862493796fe2d9529138d706c1ab496924d8d9971a365497f285da5321a6b`.

> **Esta versão inclui tudo o que estava na 3.6.23**, que você ainda não
> aplicou. Aplique só esta.

---

## O que ela traz

### 1. O assento passou a guardar a pessoa de quem ele é

Até agora o sistema guardava **pai, mãe e avós** — trazidos porque a certidão de
nascimento os cobrou — e **não guardava o registrado, os nubentes nem o
falecido**. O assento tinha o **nome** deles e mais nada.

Isso deixava duas coisas incompletas ao mesmo tempo: a **certidão de casamento e
a de óbito**, que descrevem essas pessoas, e a **remessa do IBGE**, que pede
sexo, data de nascimento, naturalidade, residência e estado civil.

A carga traz do acervo **264 pessoas**: 193 registrados, 20 + 20 nubentes, 31
falecidos. E a tela de lavrar passou a perguntar isso — inclusive o **nome
depois do casamento**, que muda em 17 dos 20 casamentos desta casa.

> **Vinte e uma dessas pessoas «nascem» depois do próprio ato**, no acervo — o
> campo em branco pegando a data da digitação. Essas datas **não entram**: o
> assento fica sem data de nascimento e a carga avisa com o número, para quem
> for à estante saber a quais ir. Certidão com data falsa é pior que campo
> vazio, porque campo vazio não afirma nada.

### 2. A remessa do IBGE se gera — e foi conferida contra a que você mandou

Em **Registro Civil → Remessa do IBGE**. Você escolhe ano e trimestre, vê o que
sairia, e baixa o `CARTINF.ZIP`.

**A conferência vem antes do botão de baixar, e isso é de propósito.** O IBGE
tem código próprio para «não sei» — o `9` — e **aceita** uma remessa inteira de
noves. Ela cumpre a obrigação e não informa nada, e do lado de fora as duas
coisas parecem iguais. A tela mostra quantas posições saíram como «ignorado» e
de quais campos, **antes** de você mandar.

Peguei os arquivos que o E-Ofício exportou de verdade e comparei posição por
posição:

| arquivo | linhas | idênticas ao real |
|---|---|---|
| casamento | 2 | **2 — byte a byte** |
| óbito | 13 | **8** |
| nascimento | 28 | batem em tudo menos dois campos |

---

## Três coisas que a comparação achou, e que você precisa saber

Elas **não são defeitos do sistema novo**. São do arquivo que a casa vinha
mandando — e nenhuma apareceria de outro jeito.

### 1. A idade dos falecidos ia um ano a mais

Quem morreu antes de fazer aniversário. Nascido em **12/07/1928**, morto em
**06/04/2026**, tinha 97 anos — o arquivo diz **98**. A conta era ano menos ano,
sem descontar o aniversário que não tinha chegado.

Medido: **3 dos 11** óbitos comparáveis, cerca de 27%.

### 2. A residência da mãe era o município do parto — e este é o mais sério

Em **27 das 28** linhas de nascimento, o município onde a mãe mora é **igual** ao
município onde a criança nasceu.

Mãe que mora em Cidade Exemplo e teve o filho no hospital de Imperatriz ia para o
IBGE como **moradora de Imperatriz**. E é por município de residência que o IBGE
distribui a estatística de natalidade — o número que dimensiona saúde, creche e
escola.

O sistema novo tira a residência da **mãe**, e há teste que recusa se a fonte
voltar a ser o parto.

### 3. Duas das treze linhas de óbito estão truncadas

102 posições em vez de 103. Falta um caractere **no meio**, e tudo depois anda
uma casa: a UF de nascimento sai `10` e o país `763`, que não existem em tabela
nenhuma. O IBGE aceitou assim.

---

## Os passos

**1. Feche o sistema.** Ninguém usando.

**2. Faça o backup**, e confira que ele terminou.

**3. Aplique** `CartorioGestao_3.6.24.cgu` pelo `ATUALIZAR_SISTEMA.cmd`.

**4. Confira o carimbo.** `VERSAO.txt` e `install.json` têm de dizer **3.6.24**.
Se disserem outra coisa, pare e me avise.

**5. Rode a carga do acervo** — *Livros e acervo → Trazer o acervo do E-Ofício*.
Marque **tudo**, inclusive a caixinha **IBGE**.

Ao terminar, confira estes números:

| | |
|---|---|
| assentos do RCPN | **244** |
| registrados / nubentes / falecidos | **193 / 20 + 20 / 31** |
| municípios do IBGE | **5.570** inseridos, **68** rejeitados |
| cabeçalho do IBGE | **4** configurações |
| avisos de data impossível | **21** |

Se algum número for outro, me avise antes de seguir.

**6. Abra *Registro Civil → Remessa do IBGE*** e peça o 2º trimestre de 2026.
Devem sair **28 nascimentos, 2 casamentos e 13 óbitos** — os mesmos números do
arquivo que a casa exportou. Não precisa mandar nada agora; é só para você ver
que fecha.

---

## O que continua esperando você

**Os quatro cliques da configuração do selador.** São seus: a senha do aparelho
não passa por mim nem entra no banco.

**A senha do selador está em texto puro no acervo, e é fraca.** Peça a troca a
quem mantém o aparelho.

**O certificado do selador venceu em 10/11/2025** — não impede de selar, e você
pediu para ser lembrado quando tudo estivesse rodando.

---

## O que fica para a próxima passada

**A natureza do óbito no ato novo.** A carga a traz do acervo (a coluna
`strTipoMorte`, «Natural» em 27 e «Violenta» em 4); no ato novo, ela é uma
escolha sua na tela de lavrar, que já tem o campo. Sem ela a linha sai com `9`.

**As outras remessas externas do Registro Civil**: SIRC, CRC e DNV. O IBGE era a
mais fechada das quatro — o layout estava medido desde ontem — e por isso foi a
primeira.
