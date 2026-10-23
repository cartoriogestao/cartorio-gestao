# Roteiro da 3.6.80 — o arquivo da CRC ia errado, e o defeito era de família

> Empacotada em 10/09/2026, por ordem do oficial («feche o pacote»), depois de
> ele mandar verificar **um** registro: «verifique o json do Pessoa Exemplo».

**Ela leva a 3.6.79 inteira e mais os consertos da CRC.** Se você ainda não
aplicou a 3.6.79, **basta esta** — ela exige no mínimo a 3.3.0 e sobe por cima
de qualquer versão que esteja aí.

---

## O que aplicar

| | |
|---|---|
| arquivo | `C:\Users\<usuario>\Downloads\CartorioGestao_Update_3.6.80.cgu` |
| exige no mínimo | **3.3.0** |

O SHA-256 vai na entrega, e não escrito aqui: **este roteiro viaja dentro do
pacote**, e um arquivo não pode conter o próprio hash. Para conferir:

```bash
certutil -hashfile "C:\Users\<usuario>\Downloads\CartorioGestao_Update_3.6.80.cgu" SHA256
```

Depois de aplicar, **Ctrl+F5** no navegador.

---

## O QUE VOCÊ PEDIU: o registro do Pessoa Exemplo

**Assento 1240**, nascimento nº 5172 de 1974, livro A-12 fl. 154, lavrado no
balcão hoje às 11h42 pelo teor colado. Origem `ARQUIVO`.

**A filiação dele sobe completa** — o problema de ontem não o alcança:

| | |
|---|---|
| filiação 1 | Pessoa Exemplo · sexo **F** · idade no parto 33 |
| filiação 2 | Pessoa Exemplo · sexo **M** |
| mais | os quatro avós, o declarante, o CPF e a matrícula de 32 dígitos |

**O que estava errado dentro dele eram dois valores:**

| campo | ia | é |
|---|---|---|
| `POSSUIGEMEOS` | **`S`** — «tem gêmeo» | `N` |
| `LOCALNASCIMENTO` | **`5`** — um número cru | `FORA_UNIDADE_SAUDE` |

E o teor dele diz, com todas as letras: «O registrado **não é gêmeo**».

---

## 1. O gêmeo que não é gêmeo — 210 de 212

O programa fazia:

```python
if assento.get("ibge_gemeo"):
    POSSUIGEMEOS = "S"
```

**O código `1` do IBGE quer dizer «NÃO é gêmeo»** (2 é gêmeo, 3 trigêmeo ou
mais, 9 ignorado) — e **um é verdadeiro** em Python. Medido na produção:

| | |
|---|---|
| nascimentos com o código 1 («não é gêmeo») | **210** |
| sem código | 2 |
| com irmão gêmeo amarrado de verdade | **zero** |

**Duzentos e dez registros subiam à Central afirmando que a pessoa tem gêmeo.**

**E o XSD tem os dois valores** — `S` e `N` —, logo «N» é resposta, e não
silêncio. O «ignorado» **não vira nem um nem outro**: escolher afirmaria à
Central o que ninguém apurou, e o manual não põe o campo entre os
obrigatórios.

**E o número de gêmeos não se inventa.** O manual diz «total de irmãos gêmeos
do registrado; se nasceram tri-gêmeos = 2» — logo o gêmeo simples é 1. **O
código 3 do IBGE é «trigêmeo OU MAIS» e não dá o número**, e o XSD aceita a tag
vazia: ela fica de fora.

---

## 2. O local do nascimento saía como número — 212 de 212

A CRC enumera **palavra**: `IGNORADO`, `UNIDADE_SAUDE`, `FORA_UNIDADE_SAUDE`.
Saía o código do IBGE, que não está na enumeração.

**E esse campo é obrigatório para registro lavrado de 13/10/2015 em diante**
(`**` no manual): **um nascimento novo seria recusado pela Central.**

**O de-para estava no acervo, com esse nome** —
`tbRCPN_LocalNascimento.strWScrc`. É o E-Ofício dizendo o que ele mandava:

| IBGE | a palavra |
|---|---|
| 1 Hospital · 2 Outros estabelecimentos sem internação | `UNIDADE_SAUDE` |
| 3 Domicílio · 5 Outros | `FORA_UNIDADE_SAUDE` |
| 9 Ignorado | `IGNORADO` |

**Antes de deduzir de-para, procure a coluna que já o tem** — e esta regra da
casa nasceu deste mesmo campo, em 29/08.

---

## 3. Cinco campos que o sistema dizia não saber preencher, e o XSD está na casa

O módulo declarava `ESTADOCIVIL`, `TIPOLOCALOBITO`, `ELEITOR`, `POSSUIBENS` e
`REGIMECASAMENTO` como «o manual manda ver o XSD, e o XSD não veio junto».

**Ele veio.** `FONTES_EXTERNAS/CRC_manual_carga_webservice_v2.6.pdf`, que já
estava na casa, tem **344 enumerações** dentro, e os cinco estão todos lá.

**E O DEFEITO DE FUNDO ERA MAIOR QUE OS CINCO:** o vocabulário é de **palavra**
e a coluna guarda **número**. Um dicionário indexado por «NATURAL» nunca acha
`1`, e o `.get` devolve nada **calado** — a tag simplesmente não saía.

| | saía | sai |
|---|---|---|
| `TIPOMORTE` | **nada**, em 31 de 31 óbitos | `NATURAL` ×27, `VIOLENTA` ×4 |
| `TIPOLOCALOBITO` | **nada** | `HOSPITAL` ×17, `OUTRO` ×6, `VIA_PUBLICA` ×5, `DOMICILIO` ×3 |
| `ESTADOCIVIL` | **nada** | `SOLTEIRO` ×15, `CASADO` ×13, `VIUVO` ×3 |
| `REGIMECASAMENTO` | **nada** | `COMUNHAO_PARCIAL` ×2 |
| `LOCALNASCIMENTO` | o número, em 212 | palavra: 148 + 66 |
| `POSSUIGEMEOS` | **`S` em 210** | `N` ×211 |

**Conferido registro por registro contra o XSD: zero valores fora da
enumeração.**

---

## 4. Os quatro óbitos violentos deixavam de subir por uma frase

Estava escrito no sistema que «a CRC só enumera **Natural ou Acidental**, e
esta casa registrou Violenta; não são sinônimos — um homicídio é violento e não
é acidental». **O raciocínio estava certo e a premissa era falsa.**

**O XSD enumera `VIOLENTA`**, com essa palavra. A frase do «(Natural ou
Acidental)» existe e vem de uma **página de recomendações** do manual — a mesma
que manda buscar o estado civil numa tabela externa que o XSD tem em casa.

**Prosa de recomendação não é schema**, e onde os dois divergem quem manda é o
que valida o arquivo. Os 4 óbitos violentos passam a subir.

---

## 5. O regime de bens entrou, e ele é obrigatório da certidão

`REGIMECASAMENTO` ficava de fora. Ele é **campo obrigatório da certidão de
casamento** (Lei 6.015/1973, art. 70, item 6), e a Central o recebe.

**A casa e a Central usam palavras diferentes para três dos cinco regimes:**

| a casa | a Central |
|---|---|
| `SEPARACAO_TOTAL` | `SEPARACAO_BENS` |
| `SEPARACAO_OBRIGATORIA` (art. 1.641 do CC) | **`SEPARACAO_LEGAL_BENS`** |
| `PARTICIPACAO_FINAL` | `PARTICIPACAO_FINAL_AQUESTOS` |

A obrigatória é a que a Central chama de **legal** — a mesma coisa com dois
nomes. Trocá-la pela voluntária afirmaria que o casal escolheu o que a lei
impôs.

---

## 6. Duas correções minhas, no meio disto

**Eu escrevi «a régua é sem caixa e sem acento» e implementei só maiúsculas.**
Medido na produção:

- **«Viúvo» não achava nada** — 2 dos 31 falecidos subiam sem estado civil;
- **«Comunhão Parcial de Bens» também não** — e é assim que os dois únicos
  casamentos com regime o têm escrito, de modo que **o regime que eu tinha
  acabado de acrescentar não sairia em casamento nenhum.**

É o `UPPER` que é ASCII pela quarta vez neste projeto. **A função se importa, e
não se copia** — o defeito mais caro daqui foi copiar `normalizar_nome` com um
comentário dizendo que era «a mesma». Há teste que compara as duas.

**E um carimbo velho saiu:** o sistema dizia que a matrícula de 32 dígitos «não
se gera, o CNJ distribui um programa». **Ela se gera desde 03/09** —
`rc_matricula.py`, pelo Anexo IV do manual da própria CRC, e acerta 255 de 255.

---

## O que mudou na lista de avisos: de 20 para 40

O aviso alcançava só o nascimento. Agora alcança as três espécies:

- **20 casamentos sem regime de bens** — campo obrigatório da certidão;
- **o estado civil que não é estado civil** — há falecidos com «falecido»
  escrito nesse campo.

**Nenhum dos dois retém o registro**: não estão entre os obrigatórios do
manual. Eles avisam, que é o que você pediu em 10/09.

---

## Como conferir que subiu certo

| onde | o que tem de aparecer |
|---|---|
| qualquer tela, no pé | **3.6.80** |
| Registro Civil → CRC | o quadro do fim diz **«Todos os campos de vocabulário fechado estão preenchidos»**, e não mais a lista dos cinco |
| Registro Civil → CRC → marcar tudo → conferir | **«40 registro(s) sobem incompletos»**, com os 20 casamentos sem regime |
| a mesma tela | **nenhum registro retido por morte violenta** — só 1 retido, o do Livro E, que a CRC não recebe |
| emita uma certidão marcando «Selo gratuito» | o selo **sai** e a folha de segurança é consumida (isto vem da 3.6.79) |

**Se a tela da CRC ainda listar `REGIMECASAMENTO` como «não sabemos
preencher», a atualização não subiu.**

---

## O que esta versão NÃO faz

**Não envia nada à CRC.** A carga continua gerando o arquivo para você assinar
com e-CPF e subir — este módulo não fala com a Central.

**Não escreve sexo, estado civil nem regime em lugar nenhum.** Ele mede e
avisa; quem corrige é quem lavra, em `/rcpn/<id>/editar`. É a sua decisão de
10/09: «deixa sexo em aberto para quem estiver lavrando arrume».

**Não manda `ELEITOR` nem `POSSUIBENS`** — as duas colunas estão vazias nos 31
óbitos. O vocabulário está pronto; o dado é do balcão, e «não perguntado» não
vira «ignorado»: `I` é uma afirmação sobre o falecido.

**Não mexe no que a segunda passada está construindo.** Como na 3.6.79, o
pacote leva a árvore inteira — e o trabalho dela das etiquetas de selo externo
do RCPJ/RTD vai junto. Compila, sobe e as telas abrem; **se aquele módulo está
terminado, eu não conferi**, porque não é meu.
