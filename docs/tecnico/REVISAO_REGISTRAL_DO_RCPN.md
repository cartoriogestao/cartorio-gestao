# Revisão registral do RCPN — o assento e a certidão

Primeira passada do **revisor registral** (`.claude/agents/revisor-registral.md`),
em **31/08/2026**. Cinco achados, **todos conferidos linha por linha** antes de
irem ao oficial — resultado de agente não se repassa por confiança.

**Decisão do oficial no mesmo dia: *«entra na próxima».*** A 3.6.52 foi
empacotada sem eles; este documento é para que não se percam.

Doutrina consultada: **PEDROSO, Alberto Gentil de Almeida (coord.). *Registros
Públicos*. São Paulo: Método, 2023** — capítulo 3, p. 335-771.

---

## 1. A certidão sai com «ND» exatamente no que o balcão acabou de digitar

**Hoje.** A tela de lavrar assento promete, escrito nela — *«vão no termo e na
certidão»* (`templates/atrib_rcpn_novo.html:99`) — sobre a hora do fato, o
nome e o endereço do local, a cor/raça e a naturalidade declarada.

Vão no termo. **Na certidão, não:**

| linha | lê de | onde isso mora |
|---|---|---|
| `rc_certidao.py:309` | `strHoraNascimento` | pacote do E-Ofício |
| `rc_certidao.py:317` | `_local_do_nascimento(dados)` | pacote do E-Ofício |
| `rc_certidao.py:402` | `strHoraObito` | pacote do E-Ofício |
| `rc_certidao.py:424` | `strNomeLocalObito` | pacote do E-Ofício |
| `rc_certidao.py:288` | `strCPF` | pacote do E-Ofício |

Num assento lavrado por esta casa o pacote está **vazio**, e a certidão sai
com `HORA DE NASCIMENTO: ND`, `LOCAL DE NASCIMENTO: ND`, `CPF: SEM
INFORMAÇÃO`.

**A norma.** Art. 54, itens 1º e 11, da Lei 6.015/1973 — Gentil **[p. 429]**.
E o precedente da casa: **103 das 126 certidões de nascimento reais** do acervo
trazem esses rótulos preenchidos.

**Quem se machuca.** O cliente, que leva papel incompleto — e **a certidão
congela ao ser emitida**: refazer é emitir outra e cobrar de novo.

**Tamanho.** Zero hoje (244 assentos, todos do acervo, nenhuma certidão
emitida). **100% do que a casa lavrar daqui para a frente.**

> **É o defeito de 28/08 pela segunda vez.** Naquela data a certidão de
> casamento e a de óbito saíam em branco pelo mesmo motivo — liam do blob — e o
> conserto foi feito **para as pessoas**. As colunas do assento nasceram
> depois, entre 29 e 31/08, e a certidão nunca soube delas.

**Proposta.** Ler primeiro a coluna do assento e cair no blob depois — o
desenho que `rc_certidao._de` já usa para as pessoas. Cinco linhas. E um teste
que emita certidão **a partir de um assento lavrado pela tela**, que é o que os
31 testes existentes não fazem.

E a certidão **não imprime cor/raça** em lugar nenhum, embora o campo seja
perguntado e a única certidão de óbito real da casa traga o rótulo `COR`
(art. 80, item 3º — Gentil **[p. 632]**).

---

## 2. A causa da morte, o sepultamento e o testamento não têm onde ser informados

**Hoje.** As três colunas existem, com o inciso ao lado:

```python
("rc_assentos", "causa_morte", "TEXT"),         # art. 255, IX
("rc_assentos", "local_sepultamento", "TEXT"),  # art. 255, X
("rc_assentos", "testamento", "TEXT"),          # art. 255, VII
```
`rc_schema.py:373-375`

O termo do livro sabe escrevê-las (`rc_modelos_do_livro.py:1152-1166`,
`rc_termo.py:110-112`). **Ninguém as preenche.** Conferido: `causa_morte`
aparece em três lugares — o esquema que a define e dois que a **leem**. Nenhum
grava.

E a tela não pergunta, nem poderia: `rc_assento.CAMPOS_DO_TERMO_POR_ESPECIE`
(linhas 253-262) lista para `OBITO` apenas `cor_raca`, `hora_fato`,
`local_fato_nome`, `local_fato_endereco` e `naturalidade_declarada`. Mandar as
três seria **recusado**.

**O efeito é calado.** O termo só escreve a frase se o campo tiver valor — e
isso é de propósito, para não deixar linha vazia no papel. Então o termo de
óbito sai sem as três **sem erro em lugar nenhum**.

**A norma.** Art. 80 da Lei 6.015/1973, itens 6º (testamento conhecido), 8º
(natureza e causa da morte, **com o nome dos atestantes**) e 9º (lugar do
sepultamento) — Gentil **[p. 632]**.

**Quem se machuca.** A família que procura o cemitério anos depois; o herdeiro,
porque o testamento muda quem herda; o IBGE, para quem a causa é o dado
principal do óbito. E **o termo congela**: corrigir depois é averbar ao lado.

**Tamanho.** Vazias em **244 de 244**. Atinge todo óbito que a casa lavrar — e
ela ainda não lavrou nenhum, então dá para consertar antes do primeiro.

**Proposta.** Três campos no bloco do óbito, as três colunas na lista de
campos permitidos, e a frase da causa citando também o **médico atestante**,
que o inciso pede junto e que a certidão real da casa imprime em bloco próprio.

> **E o guarda que devia pegar isto olhou o lugar errado.** O teste
> «o que o termo pede, a tela pergunta» confere a **lista de campos
> permitidos** — que é justamente onde as três faltam. E o outro teste monta o
> óbito **à mão**, com a causa preenchida, e passa verde. Ampliar o guarda para
> conferir **toda coluna que o termo lê** é parte do conserto, senão o próximo
> campo cai no mesmo buraco.

---

## 3. O Registro Civil não emite certidão de inteiro teor

**Hoje.** A ficha do assento tem um botão só, *«Emitir certidão»*, e a rota
chama sempre a mesma função, que monta sempre o **breve relato** no modelo do
CNJ. O módulo de inteiro teor (`atrib_certidao.py`) atende **RCPJ/RTD e o
Livro 3** — o próprio arquivo diz que `PAINEIS` tem *«duas entradas e não
três»*. O civil não está lá.

E o pedido de selo **já sabe** da diferença: há código próprio para o inteiro
teor (`ato_selado.py:351`, item `14.5.6`), e nenhuma tela do civil o aciona.

**A norma.** Art. 19 da Lei 6.015/1973 — as certidões *serão lavradas em
inteiro teor, em resumo, ou em relatório, conforme quesitos* —, com os modelos
do Provimento CNJ 63/2017. Gentil **[p. 380]**. **Quem escolhe a forma é quem
pede.** E há caso em que só ela serve: na adoção simples anterior ao Código
Civil de 2002 é *o meio mais seguro para demonstrar o parentesco* — Gentil
**[p. 451]**.

**Tamanho.** **23 das 145 certidões reais** desta casa são de inteiro teor —
uma em seis, 18% das de nascimento. Bate com o selo: 237 usos do `14.5.6`
contra 918 do `14.5.1`.

**Quem se machuca.** O cliente, que sai sem o papel; e a serventia, que perde a
diferença de preço.

**Proposta.** Para o que **esta casa lavrar**, o caminho é curto: o termo já é
o texto integral e fica gravado no assento — a certidão de inteiro teor é o
termo mais o fecho, com o mesmo número de exercício, congelamento e hash. Para
os **244 do acervo**, que não têm termo por decisão do oficial em 29/08, a
resposta certa é a recusa que o RCPJ/RTD já dá: *o registro existe no livro, e
a cópia se tira do livro físico*.

---

## 4. O quadro de cobrança nunca aparece no civil — e a tela afirma o que a medição desmente

São **dois defeitos independentes**, e o segundo é carimbo que mente.

**a) A busca de receita não passa a espécie.** `atribuicoes_web._receitas_de`
(linhas 294-301) chama `AS.caminho_do_ato(tabela, tipo)` — sem a espécie. E a
docstring da função chamada diz, com todas as letras:

> *«A ESPECIE SO IMPORTA NO CIVIL, e por isso ela e opcional (...) No RCPN, sem
> especie nao ha caminho — e devolver None e o certo.»*
> `ato_selado.py:983-986`

Devolve `None`, a tela lê como «não há nada a cobrar», e **o quadro não
aparece**. Sem mensagem, sem aviso. Atinge as quatro telas de ato do civil
(lavrar, averbar, anotar, retificar).

**b) A ficha da certidão afirma que não há receita medida.** Escrito na tela
(`templates/atrib_rcpn_ficha.html:219-222`):

> *«O E-Ofício selou 1.238 atos desta atribuição sem guardar qual item cobrava,
> e por isso não há receita medida para sugerir aqui.»*

**A correção de 27/08/2026 desmente isso**, e está no `CLAUDE.md`: o
`codigoAto` está preenchido em **1.228 dos 1.238** — 918 em `14.5.1`, 237 em
`14.5.6`, 60 em `14.5.7`. Quem mediu antes olhou a **coluna** `intCodigoAto`, e
não o campo de dentro do `memJson`.

**Quem se machuca.** A serventia: o ato sai selado, o cliente leva o papel, e o
lançamento no caixa depende de alguém lembrar de ir a outra tela e escolher o
item de memória. **Ato lavrado e não cobrado é receita que some sem ninguém
ver** — e numa correição, ato selado sem lançamento é pergunta.

**Proposta.** Passar a espécie à busca de receita — é parâmetro que a função já
aceita e que ninguém preenche —, chamar a receita da certidão na ficha, e
**apagar o texto velho**. Se o oficial preferir que o civil continue sem
sugestão, o texto tem de dizer *«a casa decidiu lançar o civil à mão»*, e não
*«não há receita medida»*, que é afirmação que a medição já desmentiu.

---

## 5. A certidão imprime toda averbação, e há averbação que a lei manda não aparecer

**Hoje.** No fim de toda certidão o sistema abre `OBSERVAÇÕES/AVERBAÇÕES A
ACRESCER:` e despeja **todas** as averbações, anotações e retificações, com o
teor inteiro (`rc_certidao.py:443-451`). Sem filtro, sem espécie reservada, sem
perguntar quem pede.

Procurado: **a palavra «sigilo» não existe em nenhum módulo do civil.**

O bloco em si está **certo** — é o art. 21 da Lei 6.015/1973, e certidão que
esconde averbação é certidão que engana. O que falta é a exceção.

**A norma.** A publicidade da Pessoa Exemplo e gênero é **sigilosa e de
acesso restrito** (STF, ADI 4.275): as certidões *serão fornecidas sem nenhuma
observação sobre a origem do ato*, vedado o uso da expressão «transgênero» —
art. 5º do Provimento CNJ 73/2018, Gentil **[p. 498]**. Na adoção, igualmente,
a certidão *não fará nenhuma observação sobre a ordem judicial de adoção* —
**[p. 451]**.

**Quem se machuca.** A pessoa cujo registro foi alterado, e o dano é da espécie
que não se desfaz: a certidão de nascimento é pública, qualquer um a pede, e o
papel sai da casa.

**Tamanho.** Zero hoje — os 244 assentos têm **244 atos, todos de REGISTRO**, e
nenhuma averbação foi lançada. **É o de menor frequência e maior gravidade
desta lista, e por isso o mais barato de resolver antes que aconteça.**

**Proposta.** Uma marca no ato de averbação dizendo que ele é de publicidade
restrita, escolhida por quem lavra a partir de lista curta e fundamentada, e a
certidão de breve relato omitindo o teor desses — **sem nenhuma observação, nem
sequer a de que existe algo omitido**, como a norma manda.

> **Isto é uma trava, e ela precisa dizer quem protege e quem barra por
> engano.** Protege o registrado. Barra por engano o próprio titular que peça
> sem se identificar — e ali a saída é a da casa em tudo o mais: **o sistema
> recusa e pergunta**. Nada disso impede a averbação de ser lavrada nem de
> constar do livro: o livro continua completo; muda o que sai impresso.

---

## O que o revisor NÃO conseguiu conferir

Ele declarou, e a declaração vale tanto quanto os achados:

1. **O Código de Normas do TJMA** não foi aberto nesta passada. Onde o parecer
   cita o art. 255 estadual, está repetindo o que os comentários do próprio
   código afirmam. **A citação lida e conferida é a da Lei 6.015/1973, no
   Gentil.**
2. **O Provimento CNJ 63/2017** não está na casa — só o que o Gentil diz dele.
   Logo, **não se afirma** que a certidão desta casa cumpre ou descumpre o
   modelo-padrão campo a campo.
3. **Se o livro de papel tem averbação à margem dos 244 assentos carregados** —
   e isto é pergunta para o oficial. A certidão imprime **«NADA CONSTA.»**
   quando não há averbação registrada, e nenhuma foi carregada, porque o acervo
   não guarda tabela delas. Se a margem do livro físico tiver um divórcio ou um
   reconhecimento, **a certidão afirma uma negativa que ninguém conferiu** — e
   o art. 21 põe a responsabilidade nessa afirmação. Achou **uma** certidão
   real, entre 147, em que a escrevente digitou à mão *«Consta Averbações a
   Margem do Registro»*: o caso existe nesta casa.
4. **Quantas vezes por ano a casa averba Pessoa Exemplo e gênero** — não
   há como medir, porque o acervo não trouxe averbação nenhuma. O tamanho do
   achado 5 é **desconhecido**, e «zero medido» ali seria zero por falta de
   dado, e não por ausência do fato.

---

## O que ficou de fora do recorte

Habilitação de casamento, retificação/restauração/suprimento, as remessas
(SIRC, CRC, IBGE, FUNAI, Junta Militar), as anotações do art. 372, o mutirão do
CPF, os gêmeos, o registro tardio, a folha do livro, a matrícula de 32 dígitos,
o Livro E, os proclamas e o natimorto. **Cada um merece passada própria** — e
esta é a primeira de sete atribuições.
