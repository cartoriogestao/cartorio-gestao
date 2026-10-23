# ROTEIRO DA 3.6.62 — o que aplicar, e o que decidir

Serventia Extrajudicial do Ofício Único de Cidade Exemplo/MA, CNS 000000.
Versão **3.6.62**, empacotada em 02/09/2026.

| | |
|---|---|
| arquivo | `CartorioGestao_3.6.62.cgu` |
| SHA-256 | `54515bdf7ff536ff4e342920cff2b2617f46202cd4ce625d3665b240682c8a29` |
| tamanho | 2.825.404 bytes · 523 arquivos |
| exige | 3.3.0 |
| suíte | **4.139 passaram**, 6 pulados, **zero falhas** (27m08s, `-n 4 --dist loadfile`) |
| conferência | **521 de 522** arquivos do pacote batem **byte a byte** com a árvore em que a suíte rodou. O que difere é **este roteiro**, editado depois de empacotar para registrar o SHA acima — **um arquivo não pode conter o próprio hash**. Nenhum arquivo de programa difere. |
| cache de ferramenta | **zero** — nem `.pytest_cache`, nem `.ruff_cache`, nem `__pycache__` |

Ela responde às quatro coisas que o oficial pediu de uma vez em 01/09/2026:

> *«a ferramenta de impressao esta baixando um arquivo, preciso que gere o pdf
> para impressao nesse botao. aplique essas correcoes nas outras certidoes de
> registro civil tambem. reabilite o protesto para o administrador, permitindo
> um botao em configuracoes habilitar para todos usuarios. aplique a correcao
> do selo (com emolumentos e demais informacoes) tambem para todos demais atos
> do cartorio, inclusive etiqueta de reconhecimento de firma e autenticacao de
> copia.»*

---

## 1. O Protesto voltou, e para você

Deixou de ser interruptor e virou **alcance**, com três posições em
**Administrativo → Configurações → Módulo de Protesto — quem pode abrir**:

| | |
|---|---|
| **Somente o oficial (administrador)** | o padrão de fábrica, e o estado de hoje |
| **Todos os usuários** | o botão que libera para o balcão |
| Ninguém — módulo fechado | fecha para todos |

**A guarda é no servidor, e não no menu.** O grupo some para quem não pode
entrar, e a rota recusa — quem tiver o endereço nos favoritos não entra. E a
frase muda com o alcance: o escrevente lê que o módulo é do oficial **e a quem
pedir**, em vez de ler que está desligado.

**Você nunca se tranca do lado de fora.** Só «ninguém» alcança o ADMIN, e é
justamente na tela de configurações que ele se desfaz.

**Se você já tinha aplicado a 3.6.61 e marcado a caixa**, aquela marcação vira
«todos os usuários» — a atualização não desfaz o que você decidiu.

**Desligar módulo nunca apaga ato.** Os 1.366 títulos, os 1.160 protestos e os
56 cancelamentos continuam onde estão: o que o alcance governa é a vista.

---

## 2. O botão de imprimir entrega PDF

Sete papéis passaram a abrir no visualizador do navegador, **com o botão de
imprimir do lado**:

- a certidão do Registro Civil (as três espécies);
- a certidão de protesto;
- a certidão do RCPJ, do RTD e do Livro 3;
- a certidão de inteiro teor do Registro de Imóveis;
- a ficha da matrícula;
- a nota devolutiva.

**O `.odt` continua a um clique**, no botão ao lado — há papel que você abre
para ajustar antes de imprimir.

**Quem converte é o LibreOffice**, que já está na máquina. Um gerador próprio
redesenharia o papel, e o molde da certidão é o que **você** desenhou.

### O que não fechou, e você precisa saber

O tempo da conversão **não se explicou**. Medido no mesmo dia, com o mesmo
molde e o mesmo PDF de 132.469 bytes saindo:

| | |
|---|---|
| de manhã, três rodadas seguidas | **1332 · 1101 · 1069 ms** |
| à tarde, todas as variantes | **~51 s, constante** |
| com um perfil recém-criado | **mais de 10 minutos** |

Cinquenta e um segundos constantes têm cara de espera, e não de trabalho.
Foram testadas as quatro suspeitas — perfil próprio do sistema, perfil do
usuário, uma instância do LibreOffice já de pé, e os canos do subprocesso — e
**as quatro deram igual**. O papel sai certo nos três casos; o que varia é o
tempo.

**Por isso o formato padrão é configuração, e não constante.** Em
**Administrativo → Configurações → Botão de imprimir — o que ele entrega** você
escolhe entre PDF e `.odt`. Se ficar lento no balcão, você volta numa tarde,
sem esperar versão nova.

**E o PDF que não sai volta para a tela com a frase.** Servir o `.odt` calado
depois de alguém clicar em «Imprimir» entregaria um arquivo diferente do
pedido sem dizer.

---

## 3. O selo imprime o que declara, em todos os papéis

A etiqueta de **reconhecimento de firma** e a de **autenticação de cópia**
saíam com o número do selo e o QR, e **nenhum valor**. Agora saem com a linha
do próprio selo:

```
Total R$ 18,11 Emol R$ 16,31 FERC R$ 0,50 FEMP R$ 0,65 FADEP R$ 0,65
```

**O precedente é medido, e não escolhido**: nos **25.634** selos que esta casa
imprimiu, o texto do selo traz os valores em **25.634** — sem exceção. Quem os
escreve é o **aparelho**: o valor já vem dentro do selo. O que faltava era o
papel imprimir o que o selo declara.

**A linha só traz o que aquele selo declara.** Medido em 4.000 selos: FERC em
4.000, FEMP e FADP em 3.998, e **FERRFIS em 396** — um em cada dez. Com os
rótulos escritos no papel, nove em cada dez etiquetas sairiam com «FERRFIS R$»
e nada depois. Rótulo sem valor é ruído num papel assinado, e zero seria pior,
porque afirma.

**Selo digitado à mão sai sem a linha**, e isso está certo: o sistema não tem o
texto daquele selo. Ver a pendência nº 2, no fim.

---

## 4. Casamento e óbito ganharam molde

Até esta versão havia **um molde só**, e as outras duas espécies **não
imprimiam nada** — a guarda as recusava, e com razão: o título do molde é texto
fixo, e uma certidão de óbito sairia com o cabeçalho de nascimento, com caixa
de DNV e de gêmeos. A recusa protegia; ela também deixava o balcão sem papel
para as duas.

**A geometria é a do molde que você desenhou.** Cabeçalho, estilos, cor preta,
larguras de coluna, o fecho e as duas caixas de selo vêm todos do
`certidao_nascimento_modelo.odt`, clonados.

**O que está em cada campo é medido; ONDE cada campo está é derivado.** Os
Anexos V e VI do Provimento CNJ 182/2024 não estão na casa, e não há certidão
real de casamento nem de óbito no modelo nacional para medir a posição dos
campos — foi assim que a cor da letra se decidiu no de nascimento, medindo um
PDF real. **Abra os dois `.odt` no LibreOffice e ajuste**: o script que os gera
(`tools/moldes_do_civil.py`) **nunca sobrescreve** um molde que já exista.

**O natimorto e o Livro E continuam recusados**, e não por esquecimento: a
certidão de natimorto não afirma nascimento com vida, e o Livro E registra seis
coisas diferentes entre si.

### E o ensaio contra a produção achou o pior defeito desta passada

**A certidão de casamento saía dizendo que o casal é irmão.** O quadro recorria
aos pais genéricos quando faltava a filiação própria do nubente, e fazia isso
para os **dois** cônjuges: as duas colunas saíam com o mesmo pai e a mesma mãe.

Medido na produção: **não há uma única** pessoa com papel `PAI_NUBENTE1` ou
`MAE_NUBENTE2` — só `PAI` e `MAE` genéricos, 12 de cada em 20 casamentos, de
modo que o recurso valia **sempre**. De quem são eles, decidido pelos
sobrenomes: **NUBENTE 1 em 10, NUBENTE 2 em ZERO** (8 não têm pais e não
decidem).

Agora o recurso alcança só o primeiro, e o segundo fica em branco: **campo
vazio não afirma nada, e a filiação errada afirma.**

---

## Como aplicar

1. Feche o sistema no servidor.
2. Rode o `ATUALIZAR_SISTEMA.cmd`, ou aplique o `.cgu` pela tela de
   atualização.
3. Suba o sistema. O banco migra sozinho.

## Como conferir que subiu certo

| onde olhar | o que tem de aparecer |
|---|---|
| **Rodapé de qualquer tela** | `3.6.62` |
| **Menu, entrando como oficial** | o grupo **Protesto** aparece |
| **Menu, entrando como escrevente** | o grupo **Protesto** NÃO aparece |
| **Administrativo → Configurações** | «Módulo de Protesto — quem pode abrir», com três opções |
| **Administrativo → Configurações** | «Botão de imprimir — o que ele entrega» |
| **Ficha de uma certidão do RCPN** | o botão diz **Imprimir (PDF)**, e há **Baixar em .odt** ao lado |
| **Etiqueta de um reconhecimento com selo automático** | a linha `Total R$ … Emol R$ …` embaixo do número |

**Se o grupo Protesto não aparecer nem para você, a atualização não subiu** — o
padrão de fábrica é «somente o oficial», e você é o oficial.

---

## O que espera decisão sua

**1. A arrumação dos campos nas duas certidões novas.** Os PDFs de ensaio
foram gerados com assentos reais da produção (194 e 214). O que estiver fora do
lugar, ajuste no `.odt` — ou, se você tiver os Anexos V e VI do provimento, ou
uma certidão real de casamento ou de óbito no modelo nacional, mande: com fonte
medida eu refaço a geometria em vez de derivá-la.

**2. O selo digitado à mão não entra no razão `sd_selos`.** A ação «selo» da
tela do reconhecimento grava só no ato — `ato_selado.registrar_selo_obtido_a_
mao()`, que confere o CNS e recusa selo repetido dizendo em que ato ele já
está, **não é chamado**. É defeito anterior a esta passada, e está declarado e
não consertado: mexer nele durante esta entrega misturaria duas coisas.

**3. O tempo do PDF.** Se no seu balcão ele sair lento, me diga o número — e
troque o padrão para `.odt` na tela de configurações enquanto isso.

**4. O gerente entra no Protesto?** Você escreveu «para o administrador», e o
sistema está exatamente assim: o MANAGER **não** entra. Se quiser o gerente
junto, é uma palavra em `modulos_ligados.PAPEIS_DO_ALCANCE`.

---

## E as pendências antigas continuam de pé

As nove de numeração, em *O que falta informar*; os cinco achados do revisor
registral no RCPN; e os relatos #33 a #36. Nenhuma delas foi tocada por esta
versão.
