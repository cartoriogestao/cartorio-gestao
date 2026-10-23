# Fase 1 — o núcleo, primeiro bloco

Dois módulos novos, 54 testes, nenhuma tela. É de propósito: o que está aqui é a base sobre
a qual Protesto, RCPN, RCPJ e RTD vão ser construídos, e base com defeito não aparece como
defeito — aparece como quatro módulos concordando na coisa errada.

**Suíte: 508 → 562.**

---

## `atribuicoes.py` — o vocabulário comum

Não foi digitado: foi **gerado** das tabelas `tbAtribuicao`, `tbAtos`, `tbTipoSelo`,
`tbSelos`, `tbFundo`, `tbTipoPapel` e `tbServico` do acervo. São os códigos que o Tribunal
reconhece.

- **6 atribuições** com os códigos do E-Ofício: 1 Notas, 2 Protesto, 3 RCPJ, 4 RTD,
  5 RI, 6 RCPN.
- **72 tipos de ato**, cada um com atribuição, selo e se está liberado. Dois seguem
  desativados: Apostila de Haia no Protesto e Certidão Unificada de Protesto.
- **11 tipos de selo**, **5 fundos** com percentual, **12 tipos de papel de segurança**.
- Os **12 caminhos do selador** observados no acervo — todos de RTD/RCPJ.

### Três armadilhas que o acervo trazia, e que agora estão presas por teste

**1. Dois espaços de código para o selo.** `tbAtos.intCodigoSelo` **não** aponta para a
tabela de tipos de selo: aponta para o cadastro de selos, que por sua vez diz qual é o tipo.
Ler o `10` como tipo devolve "nada encontrado" **sem erro nenhum**, e o ato sairia sem tipo
de selo. É a pior espécie de armadilha: silenciosa.

**2. Os cinco atos do RCPN gravaram o tipo no lugar do código.** 67 atos gravaram `10`
(o código do cadastro); os cinco do RCPN gravaram `20` (o tipo). Sem tratamento, esses cinco
sairiam sem tipo de selo — e a inspeção apontou exatamente isso: *"regularizar selos,
emolumentos e destinações nos atos do Livro C"*. Há um teste que percorre os 72 atos e exige
que **todos** resolvam para Selo Eletrônico.

**3. O código de ato 305 tinha dois donos.** Cadastrado no RTD com selo, e no RCPJ sem selo.
Código de ato é o que o selador reconhece: dois donos é ambiguidade na hora de selar.
Prevaleceu a entrada com selo, e a outra ficou registrada em `CONFLITOS_NO_ACERVO` —
**para ser perguntada à COGEX, não para ser esquecida.** É por isso que o RCPJ tem 14 atos
e não 15.

E a divergência de sigla que eu não vou "consertar": o cadastro de fundos escreve **FADP**,
o texto do selo do Tribunal imprime **FADEP**. É o mesmo fundo, o da Defensoria. A leitura
aceita as duas formas, e também FERMOJUPI para FERC, MP para FEMP e DP para FADP.

---

## `livro_nucleo.py` — a geometria do livro, para as seis atribuições

**24 séries de livro**, com os números tirados do acervo, não escolhidos:

| Atribuição | Séries |
|---|---|
| Notas | Escrituras, Procurações, Substabelecimentos, Testamentos, Testamentos Cerrados, Atas |
| Protesto | Apontamento, Registro de Protestos, Registro de Pagamentos, Protocolo |
| RCPJ | Livro A, Livro B, Protocolo |
| RTD | Livro B, Livro C, Livro F, Protocolo |
| RCPN | A, B, B-Auxiliar, C, C-Auxiliar, D, E |

### O que varia de uma série para outra, e o que não varia

Não varia: existe livro, o livro tem folhas, a folha tem frente e verso, o registro ocupa
lugar, o livro abre com termo e fecha com termo, o que sobra em branco se inutiliza.

Varia, e por isso cada série declara: **folhas por livro · registros por folha · usa verso ·
cada registro em folha nova · páginas pares · pode transbordar · termo contínuo · é diário**.

Exemplos do que isso captura:

- **RCPN**: 300 folhas, **um registro por folha**, folha nova — de `tbPropriedadeRCPN`.
- **RTD e RCPJ**: 300 folhas, usa verso, e **transbordam** o fim do livro — de
  `bitPassarDoLimiteDoLivro`.
- **Apontamento do Protesto**: vários por folha, sem folha nova.
- **Registro de Pagamentos**: no acervo, as ordens 826 a 2145 em 11 folhas — cerca de 120
  por folha, e está marcado **A CONFERIR** no livro físico, porque o acervo não declara.
- **Notas**: 200 folhas e **páginas pares** — a única atribuição com essa regra, que é a
  desta serventia, de 17/08/2026.
- **Protocolos** de Protesto, RCPJ e RTD: **diários**, porque a inspeção cobra encerramento
  diário.

### A série recusa regras que se contradizem

Declarar páginas pares sem escriturar o verso é contradição — sem verso, toda folha é uma
página. Declarar cinco registros por folha e, ao mesmo tempo, que cada registro começa em
folha nova, também. O núcleo recusa as duas na hora da declaração, com mensagem que explica
a contradição em vez de aceitar e errar depois.

### As exigências da inspeção viraram dado

Cada série carrega as exigências que a inspeção fez a ela, em texto. `exigencias_da_inspecao()`
devolve tudo, e há um teste que confere que nenhuma se perdeu: inutilizar, assinatura, termo
de abertura, rubricar, encerramento diário, continuidade da numeração.

---

## O que vem em seguida, nesta fase

1. As tabelas do núcleo — livros, termos e inutilizações — genéricas para as seis
   atribuições, e as funções que atribuem folha e ordem dentro da transação.
2. O motor de emolumentos com os cinco fundos e as vigências, calculando a linha que hoje se
   cola à mão.
3. Encerramento diário do protocolo.
4. O restante do backlog que toca o núcleo.

## Nada disto entra em atendimento ainda

Os dois módulos não têm rota, não gravam e não aparecem em tela. Podem ir para a máquina sem
risco, e a próxima atualização os leva junto — mas o sistema continua suspenso, como você
decidiu.
