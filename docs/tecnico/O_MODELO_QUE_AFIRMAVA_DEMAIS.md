# O modelo que afirmava demais — o registro tardio, e o mutirão do art. 347

*30/08/2026*

---

# PARTE 1 — O registro de nascimento tardio

## O achado

O modelo `m04_Registro_Tardio` desta casa — extraído do E-Ofício, dos treze
modelos que ele guardava em `tbModelosRCPN` — traz impresso, **em toda folha**:

> «Dispensada a presença de testemunhas nos termos do Artigo 3º do Provimento
> 28/2018 – CGJ-MA.»

**O art. 249, II do Código de Normas diz outra coisa:**

> «II - o requerimento **será assinado por duas testemunhas**, sob as penas da
> lei. **Caso o registrando for de menor de 12 anos e for apresentado a DNV**
> (Declaração de Nascido Vivo) ou documento equivalente expedido por
> estabelecimento de saúde, **será dispensada a presença das testemunhas e a
> entrevista do registrando**.»

A regra é **colher duas**. A dispensa existe **num caso só**, e as duas condições
são **cumulativas**: menor de 12 anos **e** com DNV apresentada.

## Por que isso importa

Um papel que afirma a dispensa em toda folha faz o balcão deixar de colher
testemunha **justamente onde ela é obrigatória** — e é o declarante quem assina
esse papel «sob as penas da lei». O defeito não aparece no dia: aparece se alguém
contestar o registro, anos depois.

Por isso `rc_registro_tardio.py` **calcula** a dispensa, e **diz por quê**, em
vez de imprimi-la.

## O que este documento NÃO afirma

**Não afirma que o Provimento 28/2018 não exista** — ele não foi lido. Afirma que
o **Código de Normas vigente condiciona**, e que afirmar sem condição num papel
assinado é o que não se pode fazer.

Se o oficial souber de norma posterior que amplie a dispensa, a régua muda em
`rc_registro_tardio.dispensa_testemunhas` — num lugar só, e com o artigo ao lado.

> É a mesma disciplina do «comentário que afirma medição sem ter medido é pior
> que comentário nenhum»: aqui, **dizer o que não se leu seria o mesmo erro pelo
> outro lado**.

## Três regras do art. 249 que o sistema não tinha

**1. Registra-se no lugar de RESIDÊNCIA do interessado** (caput), e não no do
nascimento. É competência, e não preferência — registrar pelo local do parto
seria lavrar em serventia incompetente.

**2. O arquivo é de vinte anos** (§ 1º), e findo o prazo quem autoriza a
incineração é **o juiz da vara de registros públicos** — não a serventia. E o
requerimento fica em arquivo obrigatório **com os documentos que o instruem**
(art. 211, II, na forma do Provimento nº 149/2023 do CNJ).

**3. Os documentos do § 2º são «sempre que possível»** — DNV (ou declaração com
firma reconhecida, em caso de extravio), certidão negativa do local de nascimento
e certidões dos irmãos. São **desejáveis, e não condição**: tratá-los como
obrigatórios travaria o registro de quem não os tem, que é exatamente quem
precisa do tardio.

E o módulo **não recusa nada**: o registro de nascimento é imperativo legal (art.
250), e travar o requerimento por documento faltante seria negar registro a quem
mais precisa dele. Ele diz o que falta; decidir é do oficial.

## E a DNV é dispensada justamente aqui

O art. 236 torna a DNV obrigatória no registro de nascimento — **ressalvada a
hipótese de registro tardio**. Faz sentido: quem nunca foi registrado costuma não
ter DNV, e é por isso que o tardio existe.

## Não saber a idade não dispensa

`dispensa_testemunhas` devolve «colha as duas» quando a idade não se lê. **Não
saber não é o mesmo que saber que é menor**, e o erro para o lado da dispensa
produz requerimento sem as testemunhas que a lei exige.

---

# PARTE 2 — O mutirão do art. 347

> «Nos assentos de nascimento, casamento e óbito lavrados em data anterior à
> vigência do Provimento nº 63, de 14 de novembro de 2017 (…) serão
> **averbados**, quando possível, de forma gratuita e mediante conferência, o
> número do CPF, e **anotados** os números do DNI ou do RG, do título de eleitor
> e de outro dado cadastral público.»

## O artigo usa dois verbos, e são dois atos

**O CPF se AVERBA; o RG, o título de eleitor e os demais se ANOTAM.** Não é
descuido de redação: são exatamente os dois atos que a inspeção de 12/08/2026
cobra separados, e que `rc_assento` já modela como espécies distintas.

Pôr o CPF numa anotação — ou o RG numa averbação — seria lavrar o ato errado num
assento, **e ninguém percebe**, porque os dois aparecem à margem.

## Ele alcança as três espécies

Nascimento, casamento **e óbito**. Medido no acervo:

| espécie | anteriores a 14/11/2017 |
|---|---|
| nascimento | **135** de 193 |
| casamento | **17** de 20 |
| óbito | **2** de 31 |
| | **154** |

**E o acervo é 1% do livro desta casa** — 193 nascimentos de 19.552 registrados.
O mutirão de verdade só aparece à medida que os assentos entrarem no sistema, e a
tela diz isso quando a lista está vazia.

## As três condições, e nenhuma é enfeite

**«quando possível»** — não é obrigação de resultado: onde o dado não existe ou
não se confere, não se averba, e isso não vira pendência eterna.

**«de forma gratuita»** — e ato gratuito **lança com zero, e não deixa de
lançar**: o valor que teria é o que a serventia compensa junto ao fundo, e ato
gratuito fora do caixa é compensação que ninguém pede.

**«mediante conferência»** — o número **não se copia** do que o interessado diz:
confere-se. É por isso que **este sistema não busca CPF em lugar nenhum**, e há
teste que varre o módulo procurando `requests`, `urllib`, `receita` e `serpro`.
Um programa que buscasse o número numa base e o averbasse estaria dispensando
exatamente a conferência que a norma manda fazer.

## «DNI ou RG», e não os dois

O artigo escreve «do Documento Nacional de Identificação Digital (DNI) **ou** do
Registro Geral (RG)». Ter um dos dois basta — exigir ambos poria em pendência
quem já está em ordem.

## A lista é medida, e não guardada

Sem tabela nova. Quem sai dela é o assento que **recebeu o ato** — e a busca olha
`rc_atos` além de `rc_pessoas`, porque o CPF pode ter sido averbado sem estar na
linha da pessoa. É a mesma disciplina de `inacabados.py`: a lista é a pergunta, e
não a resposta guardada.

---

## Os números

| | |
|---|---|
| `rc_registro_tardio.py` | a régua do art. 249, com 12 artigos citados |
| `rc_dados_cadastrais.py` | o mutirão do art. 347 |
| `tests/test_rc_registro_tardio.py` | **33** testes |
| `tests/test_rc_dados_cadastrais.py` | **32** testes |
| telas | `/rcpn/registro-tardio` e `/rcpn/dados-cadastrais` |

## O que fica pendente do oficial

- **O Provimento 28/2018 da CGJ-MA** amplia mesmo a dispensa das testemunhas, ou
  o modelo do E-Ofício generalizou? Se ampliar, a régua muda num lugar só.
- **O termo de gêmeos** (`m08`) ainda não foi construído — e o modelo dele traz o
  cabeçalho da **oficial anterior**, que não se copia.
