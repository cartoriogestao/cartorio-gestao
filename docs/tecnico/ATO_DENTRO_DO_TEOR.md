# O «AV-28» que não era layout

**28/08/2026.** O relato do oficial, no backlog do balcão, era uma linha:

> «AV-28 aparecendo no teor de ficha do acervo»

Parecia coisa de tela. Fui medir antes de mexer, e o que está por trás é a numeração.

---

## O que se mediu

Nas fichas que vieram do E-Ofício, **os atos moram dentro do texto da matrícula** —
`AV-28/1.490:-`, `R-33/314:-`, `R-01/3.236.` — e não como linhas em `ri_atos`.

- **1.052 das 1.508** matrículas com teor trazem rótulo de ato dentro do texto;
- em **756** o texto passa à frente da tabela de atos — é o número que o próprio
  módulo devolve, e não o da minha primeira contagem à mão, que deu 752;
- a maior distância é de **32 atos** (matrícula 920: a ficha traz até R-32, a tabela
  está vazia).

E o sistema calcula o próximo número com `MAX(numero) + 1` sobre `ri_atos`.

---

## E aqui eu quase exagerei o tamanho do problema

Cheguei a dizer ao oficial que eram **752 matrículas** em que o ato novo nasceria com um
número já usado. Fui medir o `tipo_ficha` antes de deixar a frase de pé:

| Tipo de ficha | Em risco | O que o sistema faz |
|---|---:|---|
| **ACERVO** | 743 | **já exigia o número à mão**, e recusava lavrar sem ele |
| **ESTRUTURADA** | 13 | **numera sozinho** — e aqui o erro sai calado |

**Treze, e não setecentos.** Nas 743 de acervo o código já se protegia: há um `if` que
diz *«nesta ficha de acervo o número do ato precisa ser informado, conforme o livro
físico»*. O problema ali é outro e menor — **a tela não dizia qual era o número certo**, e
quem digitava tinha de ir ao papel para descobrir.

> **Dado cru não é resposta; a resposta é o que a função devolve.** Contei as fichas com
> divergência e concluí o risco; a função já tratava 98% delas. É a segunda vez que este
> projeto aprende isso — a primeira foi a numeração por volume, quando li `ri_numeracao`
> crua e disse ao oficial que a matrícula sairia 714.

Mas as treze são treze registros que sairiam com número repetido **sem ninguém digitar
nada**:

| Matrícula | A ficha traz | O sistema numeraria | Devia ser |
|---|---:|---:|---:|
| 314 | R-35 | 15 | **36** |
| 3199 | R-13 | 3 | **14** |
| 302 | R-12 | 6 | **13** |
| 315 | R-11 | 8 | **12** |
| 313 | R-10 | 5 | **11** |
| 2 | R-8 | 7 | **9** |
| 322 | R-8 | 4 | **9** |
| 3090 | R-7 | 4 | **8** |
| 1125 | R-6 | 2 | **7** |
| 899 | R-6 | 6 | **7** |
| 8 | R-4 | 1 | **5** |
| 615 | R-4 | 4 | **5** |
| 3236 | R-2 | 2 | **3** |

É o defeito de 18/08/2026 outra vez — a numeração que anda para trás sobre acervo —, agora
na ficha de imóvel.

---

## O que **não** se fez, e é o ponto

**Não se cria ato a partir do texto.** A tentação é óbvia: ler o teor, achar os rótulos,
inserir as linhas que faltam em `ri_atos`. Seria fabricar atos com **data, natureza e
conteúdo adivinhados por um programa** — e ainda pô-los na **corrente de hash**, que existe
justamente para provar que nenhum ato foi inventado.

Um parser errando ali produz registro falso. Há teste que varre `ri_numeros_do_teor.py`
procurando `INSERT`, `UPDATE` e `DELETE`, e nomes públicos com `criar`, `importar` ou
`gravar`.

O módulo faz duas coisas, e só:

1. **lê o que está escrito** e diz qual o maior número que a ficha já usou;
2. **mostra a frase de onde tirou**, para uma pessoa poder discordar.

---

## A precisão que faz isto valer

O teor das fichas antigas cita atos de **outras** matrículas o tempo todo:

> «Transcrita neste Registro no Lº 2-C, fls. 16 sob nº **R-1/503** em 22-05-80.»

Contar aquele `R-1` como ato desta ficha inflaria a numeração com o passado de outro
imóvel. Por isso o padrão **exige a barra e o número da matrícula depois dela**, e compara
com a desta ficha. Conferido contra o acervo real: a matrícula 1904, que traz essa frase,
devolve **nenhum** ato próprio.

E `AV-3` solto **não conta**. Isso perde alguns casos de propósito: **é melhor deixar de
achar do que achar errado**, porque o número que este módulo devolve vira o número de um
registro.

---

## O que mudou na prática

**Na ficha estruturada**, o próximo número passa a ser o maior dos dois — a tabela e o
texto. A matrícula 314 agora numera **36**, e não 15 — a ficha dela traz R-35.

**Na ficha de acervo**, o campo do número **vem preenchido** com o que a ficha manda, e um
aviso vermelho diz de onde saiu, com as frases citadas. O padrão passou a ser o certo, e
quem discordar troca — porque quem confere o livro físico é a pessoa.

**E a recusa passou a olhar o texto.** A que existia dizia *«o número 3 já está ocupado
pelo ato AV-03»* olhando só `ri_atos`. Agora, se o número escolhido estiver escrito na
própria ficha, ela recusa citando o rótulo **e a frase**:

> O número 28 já está usado nesta matrícula: a própria ficha traz «AV-28». Está escrito
> assim no teor — “…sob nº AV-28/1.490:- Cidade Exemplo…”. Informe outro número, conforme o
> livro físico.

**E há uma tela com as 756**, em *Registro de Imóveis → Numeração dentro do teor*, com as
**estruturadas no topo** — e não as de maior distância. São as únicas em que o sistema
numera sozinho, e por isso as únicas em que o erro sairia sem ninguém digitar nada.
