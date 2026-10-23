# Roteiro da 3.6.52 — o Protesto maduro, e a linha em branco que sumia

Empacotada em **31/08/2026**, a pedido do oficial: *"depois de terminar com o
protesto maduro e pronto para uso, empacotar."*

Ela exige a **3.3.0**, como as anteriores. Se você tem pacotes antigos parados,
**basta este**.

---

## O que aplicar

```bat
rem Na máquina do servidor, com o sistema parado.
ATUALIZAR_SISTEMA.cmd
```

O banco migra sozinho ao subir. **Não há coluna nova nesta versão** — o que
muda é código, tela e documentação.

---

## O que mudou, em ordem de utilidade para o balcão

### 1. O Protesto passou a operar todos os arquivos que têm formato medido

**«A protestar» — o passo da tarde, que não tinha tela.** Do seu roteiro:
*"gerar protesto, sem movimentação, calcular, listar, gerar."* Era o único
passo do dia sem tela nenhuma; o título intimado ficava esperando alguém
lembrar dele na lista geral.

- a lista traz os intimados **em que nada aconteceu depois** — nem pagamento,
  nem desistência, nem cancelamento;
- **o prazo não é calculado**, como você decidiu em 24/08: a coluna conta os
  dias desde a intimação e não julga o tríduo;
- **lavra só os marcados**, um a um, cada um na sua transação — um que falha
  não derruba os outros;
- sai **sem selo e sem cobrança**, de propósito: vinte selos são vinte chamadas
  ao aparelho. Eles aparecem em *Atos sem selo* e *Atos sem cobrança*.

**As imagens dos títulos.** A CRA entrega o título em duas partes — o arquivo
de 600 posições, que o sistema já lia, e a **imagem do papel**, que vem num
`.zip` à parte. A tela da Central lista as duas pendências lado a lado e o
sistema fazia só a primeira. Agora recebe o pacote e prende cada imagem ao seu
título.

> Ela só se prende quando o **nosso número E o documento do devedor** apontam
> para o mesmo título. O nosso número se repete entre apresentantes — 53 grupos
> e 111 títulos no acervo —, e prender pela metade da chave mostraria ao
> devedor, no balcão, a dívida de um terceiro.

**Um defeito no arquivo de andamento.** O sistema montava o andamento com o
mesmo código de ocorrência do retorno (o do ato: `C`, `1`, `3`, `A`); medido
nos arquivos de 2026, o andamento desta casa **sempre mandou `0`** — em 103 de
103 linhas. Corrigido.

**A ordem do menu.** *Desistências* passou à frente de *A protestar*, que é a
ordem do seu roteiro nos dois turnos, e a tela avisa antes de lavrar:
protestar título de que o credor desistiu é o erro que não se desfaz.

### 2. O relato #27 — a ficha de assinatura

Você me corrigiu: *"o oficial não assina a ficha de assinatura, só o
cliente"*. Tirei a assinatura do oficial que eu tinha posto por engano, e a do
escrevente junto.

**E a outra metade do seu relato eu não tinha visto**: *"precisa de mais espaço
livre para desenvolver a assinatura"*. Fui aumentar o espaço de três linhas
para cinco, escrevi o teste — e ele disse **zero**.

Não era o teste. **As três nunca chegavam ao papel.** O gerador de `.odt`
jogava fora toda linha em branco, e a linha de assinar saía colada no rótulo,
que é exatamente a sua queixa.

> **Eram 80 linhas em branco perdidas assim**, em sete módulos: notas (30),
> atribuições (17), habilitação (13), o próprio gerador (11), caixa (4), núcleo
> (3) e RI (2). Ficha, termos de livro, certidões, recibos, comprovante de
> prenotação, traslado.

---

### 3. O Protesto ganhou o que a lei e o acervo cobravam — 01/09/2026

**A sustação judicial e o efeito suspensivo.** São dois institutos, e o
E-Ofício os nomeia numa tabela: `1 = Suspensivo`, `2 = Sustado`. Sustar impede
o protesto (a ordem chega antes); suspender tira os efeitos de um protesto já
lavrado (a ordem chega depois).

- **A sustação bloqueia TRÊS atos**, e não um: o art. 17, § 1º diz que o título
  sustado *"só poderá ser pago, protestado ou retirado com autorização
  judicial"*. A recusa diz o juízo, o processo e o artigo.
- **Revogada, o prazo é de UM DIA ÚTIL** e **sem nova intimação** (§ 2º) — e
  esses títulos aparecem **no alto** da tela «A protestar», porque a fila
  comum os esconderia.
- **O efeito suspensivo pesa na certidão**: um protesto cujos efeitos o juiz
  suspendeu sairia nela como protesto vivo. Ele **não some** da certidão — o
  protesto existe e está no livro —, mas ela passa a dizer que os efeitos
  estão suspensos, com o juízo e o processo.

**O texto que vai no Livro de Registro de Protestos.** O sistema gravava livro,
folha e número de ordem, e mais nada; o E-Ofício escrevia um texto em **1.132
de 1.164** protestos. Ele agora se monta das frases medidas e **congela** no
ato — e a ficha do título o mostra.

> O texto-base afirma *«PROTESTO LAVRADO PARA FINS E EFEITOS DO ART. 9º-A DA
> LEI Nº 9.430/1996»* — o artigo da dívida ativa da Fazenda — em 1.126 de 1.132
> protestos desta casa, **inclusive nos que não são de dívida ativa**. Por
> isso ele foi para o **catálogo de modelos que você edita**: afirmação
> jurídica em papel que a serventia assina é de quem assina.

---

## E ISTO PRECISA DE UM PASSO SEU DEPOIS DE APLICAR

**Rode a carga do Protesto de novo.** Em *Demais atribuições → Trazer do
E-Ofício*, marque **Protesto** e mande.

**Por quê.** O ensaio contra a produção achou que **o retorno à CRA não podia
ser gerado para nenhum dos 1.366 títulos do acervo**: eles estão sem
`protocolo` (que volta na posição 448), sem `apresentante` (sem o qual não há
cabeçalho nem a letra da 566) e sem ato de **intimação**. São 1.211 atos que a
Central não sabe, e nenhum saía.

A carga passou a trazer os três. Ela **olha o que falta**, então rodá-la de
novo não duplica nada — e o que já está lá fica como está.

**O que você deve ver ao terminar:**

| | |
|---|---|
| protocolos trazidos | **1.365** |
| apresentantes trazidos | **1.357** |
| intimações trazidas | **1.176** — 1.115 por edital, 61 em mãos |
| títulos sem intimação no acervo | 190 — quase todos pagos ou desistidos antes |

E depois, em **Protesto → Retorno à CRA**, a tela deve mostrar **58
apresentantes** com pendência, em vez de um só com o código em branco. Se
continuar aparecendo um grupo vazio, a carga não rodou.

---

## Uma coisa que espera decisão sua

**A certidão de inteiro teor deve reproduzir as linhas em branco do
E-Ofício?**

Medi antes de mexer. Se todo parágrafo vazio virasse linha em branco:

| | |
|---|---|
| matrículas com teor | 1.508 |
| **ganhariam linha em branco** | **1.057** |
| linhas novas, ao todo | 1.757 (pior caso: 15 numa ficha) |
| crescimento médio | 11,8% dos parágrafos |
| atos das Notas afetados | 0 |

E as do RI não são iguais às do código: elas vêm com `lang` e `style`, na forma
que o **editor do E-Ofício** exportava.

- Se o E-Ofício as desenhava como linha em branco, repô-las é **reproduzir o
  livro** — que é o que uma certidão de inteiro teor faz.
- Se eram sobra do editor, é **esticar 1.057 certidões** sem motivo.

**Não dá para medir**: das 369 certidões do acervo, uma só guarda o corpo.

Por isso o conserto ficou no que é inequívoco — a linha em branco que o código
da casa escreve — e **a produção não ganhou uma linha sequer**. Trocar é uma
linha de código, no dia em que você disser.

---

## Duas coisas que não dá para construir hoje, e por quê

Do seu roteiro da tarde:

```
3) enviar e aprovar arquivos CENPROT (xml);
4) enviar arquivo de emolumentos.
```

**Não existe um único exemplar do arquivo de edital do CENPROT nem do de
emolumentos** em lugar nenhum desta casa — procurei em `C:\ARPNET` inteiro e na
pasta `8. CRA`. Construí-los seria inventar formato, e a regra é sua: onde não
há padrão anterior, o sistema recusa e pergunta.

**Com um arquivo de cada que já tenha subido e sido aceito, os dois se medem
numa tarde** — foi assim que o quinto layout, o da desistência, ficou pronto.

E o **XML do CENPROT** está medido inteiro (903 arquivos, 17.270 títulos) e
mesmo assim não se gera para título novo: falta a **chave única de 23
dígitos**. Refiz a medição mais larga em 31/08 — os 125 arquivos de 2026, nos
quatro tipos, lidos byte a byte: **a chave não vem por arquivo nenhum da CRA**.
Ela é da plataforma do CENPROT.

---

## Como conferir que subiu certo

| onde | o que tem de aparecer |
|---|---|
| `/saude` | versão **3.6.52** |
| **Protesto → A protestar** | a tela abre, com o aviso de que o prazo não é calculado |
| **Protesto → Imagens dos títulos** | a tela abre e aceita `.zip` |
| menu do Protesto | *Desistências* **antes** de *A protestar* |
| ficha do cartão de autógrafo | espaço em branco entre cada rótulo e a linha de assinar |
| **Ajuda → Problemas**, relato #27 | nota do desenvolvimento marcada **ATENDIDO** |
| **Ajuda → Problemas**, relato #36 | nota dizendo que está pela metade, e **quais sete telas faltam** |
| **Protesto → Retorno à CRA** | **58 apresentantes**, e não um com código vazio — depois de rodar a carga |
| ficha de um título protestado | um bloco *«O texto que foi ao livro»*, com o CERTIFICO e a frase do edital |

> Se a ficha do cartão continuar com a linha de assinar colada no rótulo, a
> atualização não subiu.

---

## E nasceu um revisor registral, que não vai no pacote

Pedido seu em 31/08/2026: *"um agente de IA com amplo conhecimento da atividade
notarial e registral (...) para testar o sistema, encontrar problemas e propor
soluções e melhorias"*.

Ele mora em `.claude/agents/revisor-registral.md`, **fora da pasta que o `.cgu`
leva** — é ferramenta de desenvolvimento, e o servidor não tem o que fazer com
ela. A doutrina que ele consulta é o **Gentil** (*Registros Públicos*, Método,
2023), em `FONTES_EXTERNAS/gentil/`: sete capítulos, e seis são as suas seis
atribuições. Ele cita a **página impressa**, que vem marcada no texto, para
você conferir no livro.

**O Loureiro ficou como segunda fonte, e só para ler.** É digitalização, e o
OCR troca letras — «Notariqis», «conjunta1nente», e o romano `II` saindo `li`.
Citar aquilo entre aspas afirma palavras que o autor não escreveu.

**A primeira passada dele achou cinco coisas no Registro Civil**, e você
decidiu que **entram na próxima**. Estão em `REVISAO_REGISTRAL_DO_RCPN.md`, com
a norma e a página de cada uma. As duas que mais pesam:

- a certidão sai com **«ND»** exatamente na hora e no local que o balcão
  acabou de digitar — atinge 100% do que a casa lavrar daqui para a frente;
- **causa da morte, sepultamento e testamento** (art. 80, itens 6º, 8º e 9º)
  não têm onde ser informados: as colunas existem, o termo sabe escrevê-las, e
  nenhuma tela as pergunta.

Nenhuma das duas dói hoje — a casa ainda não lavrou assento novo nem emitiu
certidão. Dá para consertar antes do primeiro.

---

## O que continua em aberto, e é meu

| # | o que falta |
|---|---|
| **#20** | subir e baixar o `.odt` do teor da escritura |
| **#33** | a tela de pesquisa dos selos (os três filtros existem no razão) |
| **#34** | encerrar sessão por inatividade acima de 12h |
| **#36** | o rascunho nas **sete telas** que faltam — escritura, título do protesto, RCPJ/RTD, Livro 3, habilitação, retificação do civil e lançamento no assento |
| boleto | o código de barras do aviso — o verificador não se explicou |
