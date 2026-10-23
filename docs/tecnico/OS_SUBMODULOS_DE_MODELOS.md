# Os submódulos de modelos — um por atribuição, com as partes editáveis

> **Estado em 19/09/2026 (Fase 0):** **34 papéis** no `CATALOGO` (não 10 nem 15). RCPJ/RTD **têm** várias chaves (certidão congelada, teores, capa/faixa PDF) — a linha «RCPJ e RTD = 0» abaixo é do desenho inicial de *elementos* por atribuição, não do catálogo. Ver [MATRIZ_DE_PAPEIS.md](MATRIZ_DE_PAPEIS.md).

> «preciso que haja um submodulo de modelos para cada atribuicao e nesse
> submodulo quero poder editar cada parte dos modelos, especialmente
> gerenciando cada elemento do modelo» — o oficial, 07/09/2026.

---

## 1. As três decisões, e são dele

Antes de escrever linha, três perguntas foram ao oficial. As respostas:

| pergunta | a resposta dele |
|---|---|
| o elemento é do modelo ou da casa? | **«cabecalho compartilhado por atribuicao, podendo mudar para atos especificos, como certidoes do rcpn com cabecalho diferente do termo»** |
| as seis de uma vez, ou uma primeiro? | **«todas atribuicoes de uma vez»** |
| e os papéis fixos de hoje? | **«viram modelos editaveis»** |

E, ao ver o desenho, uma quarta que mudou o tamanho da obra:

> **«cabecalho dos atos vamos deixar num ajuste separado para manter a forma e
> diminuir o risco de ir errado»**

**O cabeçalho ficou de fora.** Ele continua no `RI_CABECALHO` do catálogo, para
o Registro de Imóveis, e em `rc_cabecalho.py` — sete linhas montadas em código,
na ordem que a norma exige — para o Registro Civil. Torná-lo texto livre poria
a forma do timbre nas mãos de quem edita depressa.

Isso **não** desfaz o pedido: a herança por atribuição, com troca por ato, vale
para o corpo, o encerramento e o rodapé — que é onde o texto de fato muda de
ato para ato.

---

## 2. O que se mediu antes, e o que cada medição decidiu

**Eram 15 na mediçao de 07/09; hoje são 34 no CATALOGO.** O catálogo cresceu desde 29/08 — entraram os dois
do protesto e o termo de óbito. Contados.

**`mo_modelos` e `ri_modelos` estão com ZERO linhas na produção.** Os 14 saem
todos do código hoje. Foi isso que permitiu à tabela nova ser o **lar único** do
corpo sem migração nenhuma — e as duas velhas ficam como legado, para uma
instalação que já tivesse ajustado alguma coisa.

**O formato do claro é uniforme dentro de cada atribuição** — e é isso que
*permite* um elemento compartilhado:

| atribuição | papéis | marcador |
|---|---|---|
| Registro de Imóveis | 5 | Jinja `{{ a.numero }}` |
| Tabelionato de Notas | 2 | Jinja |
| Caixa e protocolo | 3 | Jinja |
| Registro Civil | 3 | chaves `{numero}` |
| Protesto | 2 | chaves |
| **RCPJ e RTD** | **0** | — |

Um encerramento em Jinja herdado por um termo do Registro Civil seria texto
**aprovado numa conferência e recusado pela outra**, e o escrevente descobriria
com o cliente na frente. `formato_da_atribuicao` **mede** a uniformidade em vez
de a supor, e recusa se um dia ela deixar de valer.

**RCPJ e RTD não têm um único papel no catálogo.** Eles emitem certidão por
outro caminho (`atrib_certidao`, que serve três atribuições). O submódulo deles
nasce só com o nível da atribuição, e **a tela diz isso** — tela vazia se lê
como quebrada.

**«Caixa e protocolo» não é atribuição**, e entra como o sexto assim mesmo: tem
três papéis reais, e deixá-lo de fora obrigaria a procurar o recibo noutro
lugar — que é o relato #28 de volta. O menu dele é o Administrativo.

---

## 3. Os três degraus

```
1. o elemento do ATO           a certidão do RI tem encerramento próprio
2. o elemento da ATRIBUIÇÃO    o resto do RI usa o comum
3. o padrão do CÓDIGO          instalação nova já nasce funcionando
```

Entre o 1 e o 2 há um degrau a mais, o **legado**: quem já tinha ajustado
aquele papel em `mo_modelos` ou `ri_modelos` ajustou o **papel**, que é mais
específico que a atribuição. Perder esse ajuste ao subir de versão seria apagar
trabalho de alguém sem avisar.

> **E a comparação do legado é com o padrão, e não com `esta_ajustado`.**
> Aquela função olha só `mo_modelos`, e o legado do Registro de Imóveis mora
> numa segunda tabela. Perguntar «o que sai é diferente do que o programa
> traz?» alcança as duas.

O terceiro degrau é a regra que `modelos_da_casa` já paga: **o código é o piso,
a tabela é o ajuste** — e por isso «voltar ao herdado» é apagar a linha, e não
recadastrar um texto que ninguém tem mais.

---

## 4. A promessa, e como ela quase se quebrou por um caractere

A condição do oficial ao tirar o cabeçalho foi **«manter a forma»**. Em código
isso quer dizer uma coisa medível: **os 15 papéis saem, no dia da subida,
exatamente como saíam na véspera.**

O encerramento e o rodapé nascem **vazios**, e vazio não entra na junção — de
modo que o que sai é o corpo literal.

> **A PRIMEIRA VERSÃO DA JUNÇÃO QUEBROU ISSO POR UM CARACTERE.** Ela juntava as
> três partes com `strip()` em cada uma, e **nove dos catorze** papéis perderam
> a quebra de linha do fim: 743 caracteres viraram 742, e assim nos nove de
> Jinja. Um deles é o molde da ficha da matrícula, que é **XML de ODT**.
>
> Quem pegou foi o ensaio que compara papel por papel contra o padrão do
> código. **«Um caractere a menos» não se vê lendo** — e é por isso que a
> promessa de que nada muda **se mede, e não se afirma**. Há teste que a
> guarda.

Quando o oficial escreve um encerramento, aí sim o corpo perde o espaço em
branco do fim — senão sairiam três linhas vazias entre uma parte e outra. E
isso já é uma mudança que ele pediu.

---

## 5. O que não quebrou, e por quê

**Há 13 sítios chamando `modelos_da_casa.corpo_de`** — no RI, no caixa, nas
notas, no termo do civil e no protesto. Nenhum foi editado.

`corpo_de` **mudou de conteúdo e não mudou de nome nem de assinatura**: ela
passou a compor o documento pelos elementos. Assim os treze ganharam o
encerramento e o rodapé de uma vez — e **edição em treze lugares é treze
chances de errar um**.

O que era o corpo de `corpo_de` virou `corpo_gravado_ou_padrao`, e a razão é de
recursão: o módulo dos elementos precisa desse piso para montar o degrau de
baixo. Se ele chamasse `corpo_de`, os dois se chamariam para sempre.

**Quem edita não chama `corpo_de`**, e sim `modelos_elementos.corpo_do_ato`:
mostrar o documento composto na caixa de edição faria o escrevente gravar o
fecho **dentro** do corpo, e ele sairia duas vezes no papel seguinte.

**E a tela geral continua existindo**, em Administrativo → Modelos. As duas
gravam **no mesmo lugar**: duas telas editando o mesmo texto em tabelas
diferentes é o defeito das «duas fontes para a mesma coisa», que este projeto
já pagou duas vezes. A geral responde «onde eu mudo isto?» quando não se sabe
de qual atribuição é o papel; o submódulo responde quando se sabe.

---

## 6. Onde isso mora

| arquivo | o que é |
|---|---|
| `modelos_elementos_schema.py` | a tabela `mo_elementos`, as seis atribuições e as três partes |
| `modelos_elementos.py` | os três degraus, a composição e a conferência por formato |
| `modelos_elementos_web.py` | **seis endpoints, uma função só** — seis cópias divergiriam no primeiro conserto |
| `templates/modelos_atribuicao.html` | a tela, a mesma para as seis |
| `tests/test_modelos_elementos.py` | **27** testes de domínio |
| `tests/test_modelos_elementos_web.py` | **15** testes das seis telas |

**No menu:** cada atribuição → **Modelos** → *Modelos dos documentos*; e o
caixa em Administrativo → *Modelos do caixa*.

---

## 7. O que não se fez, e é decisão declarada

**O cabeçalho** — decisão do oficial, ver a secção 1.

**Não há corpo compartilhado pela atribuição.** O corpo de uma certidão não é o
corpo de uma nota devolutiva; oferecê-lo daria um campo que, preenchido,
apagaria o texto de todos os papéis da atribuição de uma vez. Só o encerramento
e o rodapé têm o nível comum.

**Não se partiu o texto dos 15 papéis em corpo + fecho.** Eles já trazem o
fecho dentro do próprio texto, e partir isso automaticamente seria adivinhar
onde o corpo acaba, em documento que a serventia assina. Quem quiser separar,
separa à mão — e aí o fecho passa a poder ser herdado.
