# Revisão do Tabelionato de Notas

**17/08/2026.** Escrituras, procurações e o que as cerca. Leitura completa de `notas_web.py`
(2.200 linhas), `notas_schema.py`, `notas_livro.py`, `notas_censec.py`, `notas_import.py`,
`notas_teor.py`, `notas_modelos.py` e das nove telas, mais duas revisões adversariais do que foi
escrito nesta rodada.

---

## Nota sobre as citações deste documento

Distingo três coisas, e a distinção importa num sistema de cartório:

**Conferido em fonte primária.** Lei 8.935/1994 (Planalto, texto compilado); a existência e a
estrutura do **Provimento COGEX/TJMA nº 28, de 23/04/2026** — o Código de Normas do Foro
Extrajudicial do Maranhão, publicado em 27/04/2026 —, incluindo o sumário do Capítulo IV
(Tabelionato de Notas, arts. 774 a 880) e a divisão em seções; e, do CNN/CNJ (Provimento
149/2023), os arts. 268, 273 e 284, conferidos pelos provimentos que os alteraram.

**Conferido indiretamente.** O art. 795, §§ 2º e 4º do Código de Normas do MA, cujo teor já
estava transcrito em `notas_modelos.py` por quem construiu a biblioteca de modelos, e que cai
dentro da Seção III (arts. 788 a 797) confirmada no sumário. As duas fontes batem.

**Não conferido.** O corpo dos demais artigos do intervalo 788–797, e a doutrina notarial. O
PDF do Provimento 28/2026 tem mais de mil artigos e a ferramenta de leitura trunca muito antes
do Capítulo IV; o mesmo vale para o CNN. **Onde não confirmei, cito a seção e não o número do
artigo.** Número de artigo inventado em comentário de código é pior do que comentário nenhum.

> **Se você baixar os dois PDFs para a pasta do projeto, eu completo as remissões com o texto
> exato:**
> — CNN: `https://atos.cnj.jus.br/files/compilado182530202608036a70dd1a1a03f.pdf`
> — MA: `https://novogerenciador.tjma.jus.br/storage/arquivos/arquivos/provimento_n_28_de_23_de_abril_de_2026_cogex_28_04_2026_17_12_51.pdf`

**Achado que vale por si:** o `notas_modelos.py` cita "Provimento TJMA n. 28, de 23/04/2026" —
está certo e atual. Mas vale conferir se algum outro ponto do sistema ainda remete ao código de
normas **anterior**, substituído em abril de 2026. Numeração de artigo não sobrevive a troca de
código.

---

## 1. O que esta rodada corrigiu

| # | O defeito | Consequência |
|---|---|---|
| 1 | Guardar o teor reescrevia `folha`, `folha_final` e `folhas` do formulário | corrigir uma vírgula com o campo em branco **apagava a folha do ato**, sem aviso |
| 2 | `ix_nt_atos_livro` não era único | dois atos na mesma folha do mesmo livro, e nada reclamava |
| 3 | `nt_livros.folhas` era gravado e nunca comparado | nada impedia lavrar na folha 350 de um livro de 200 |
| 4 | `folha_atual` nascia em 1 e nunca era atualizado | a tela dizia "1 de 200" num livro com 139 folhas escritas |
| 5 | `numero_ordem` era `MAX()+1` filtrado pelo ano de **hoje**, não pela data do ato | ato retroativo colidia com a série do ano anterior |
| 6 | `livro_id` do formulário não era validado | POST direto vinculava ato a livro inexistente ou encerrado |
| 7 | `INSERT` de livro não tratava `IntegrityError` | corrida entre dois balcões dava HTTP 500 |
| 8 | `termo_abertura` era opcional e nunca lido | livro nascia sem identidade, e o termo digitado sumia |
| 9 | `livro_complemento` e `folha_complemento` nunca eram escritos | a CENSEC **recusa por duplicidade** os pares de atos na mesma folha do livro 27 |
| 10 | `nt_atos.folhas` era write-only | ninguém lia o que o operador digitava |

Detalhe do desenho em `docs/tecnico/NUMERACAO_DE_LIVRO.md`.

### E o que a revisão adversarial pegou dentro da própria correção

Vale registrar, porque é o tipo de coisa que passa em teste verde. A primeira versão desta
rodada tinha doze defeitos; os três piores:

- a guarda "já está lançado" perguntava pelas colunas **novas**, que o acervo não tem. Os 258
  atos do E-Ofício passavam direto: um clique em *Lançar no livro* numa escritura de 2011 mudava
  a folha de 139 para 141 — **e a tela oferecia o botão**, porque também decidia "é rascunho?"
  pela coluna nova;
- pior: `lancar_ato` fazia `situacao='LAVRADO'` sem perguntar. Uma **procuração revogada**
  voltava a valer, e voltava a ser elegível para a remessa à CENSEC, que filtra por lavrado;
- livro com `nt_livros.folhas` nulo — que a importação produz, porque copia o `intNFL` do
  E-Ofício sem conferir — era **encerrado sozinho** no primeiro lançamento, com um termo dizendo
  que ele tinha "0 (zero) folhas".

Os três estão corrigidos e cada um tem teste próprio. A lição: guarda de integridade tem de
perguntar pelo estado do **negócio** (a situação do ato), não pela coluna que o código acabou de
inventar.

---

## 2. O que continua faltando, na ordem que eu atacaria

### 2.1 ~~Anotação à margem~~ — RESOLVIDO em 17/08/2026

`nt_ato_anotacoes` está ligada. Revogação, renúncia e substabelecimento lançados no livro anotam
sozinhos a margem do ato anterior, a anotação sai transcrita no traslado, e o que não pôde ser
identificado com segurança fica na tela **Anotações pendentes**. Detalhe em
`docs/tecnico/NUMERACAO_DE_LIVRO.md`.

Uma revisão adversarial pegou, dentro desta correção, um defeito que teria sido pior do que a
lacuna: a busca do ato anterior casava só por *(livro, folha)*, e o livro 27 existe em toda série —
uma revogação de procuração marcou como **revogada** uma escritura de compra e venda de R$ 150.000
e escreveu na margem dela. Corrigido com quatro travas (serventia, tipo, série do livro, unicidade),
cada uma com teste próprio.

### 2.2 O traslado não traz a epígrafe que o próprio módulo promete

A docstring de `notas_teor.py` descreve cinco blocos, e o primeiro é **"epígrafe — LIVRO, FOLHA,
natureza do ato"**. A função `montar()` não gera epígrafe nenhuma: começa direto no
comparecimento.

Até esta rodada isso era inevitável — no momento em que o teor era montado, ninguém sabia o
livro nem a folha. **Agora sabe**, e a epígrafe pode ser inserida no lançamento, junto com a
atribuição. O traslado já traz livro/folha/termo no cabeçalho; o corpo do ato, não.

### 2.3 A CENSEC trunca a folha em silêncio

`notas_censec.py` corta `folha` em **4 caracteres** e `notas_doi.py` em **6**. A conferência
prévia verifica se o campo está **presente**, nunca se ele **cabe**. Um livro que passe da folha
9.999 produz remessa com a folha errada, sem impedimento e sem aviso — e o mesmo ato sai
truncado na CENSEC e inteiro na DOI.

O art. 273, § 1º do CNN/CNJ (conferido) diz que a informação que o CNB/CF fornece se compõe do
nome da serventia, **da data da lavratura, do número do livro e das folhas**. É literalmente o
campo que está sendo truncado. Recomendo transformar o truncamento em **impedimento**: recusar o
ato na conferência prévia em vez de mandar errado.

Hoje o risco é remoto — os livros têm 200 folhas. Vira real no dia em que alguém cadastrar um
livro grande, e aí não haverá aviso.

### 2.4 Matrícula Notarial Eletrônica (MNE) — coluna lida, nunca escrita

`nt_atos.mne` é lida por `notas_censec.py` (três vezes) e por `notas_doi.py`, e **nada a
escreve**. Nos atos em papel ela vai nula, e isso é correto. Mas o art. 284, parágrafo único do
CNN/CNJ (conferido, na redação do Prov. 181/2024) determina que **todos** os tabeliães de notas
prestem o serviço do e-Notariado. No dia em que a serventia lavrar o primeiro ato eletrônico ou
híbrido, a MNE é obrigatória e não há por onde informá-la.

Cuidado com a fonte: a MNE nasceu no **Provimento CNJ 100/2020, que está REVOGADO** pelo
149/2023. A matéria foi consolidada no Livro III do CNN. Se for implementar, o layout a seguir é
o do CNN, não o do 100/2020.

### 2.5 Ato de livro sem selo não avisa

O painel conta e alerta os **reconhecimentos** sem selo — "sem ele a prestação de contas ao
tribunal não fecha". Escrituras e procurações sem selo não têm alerta nenhum, e o selo é
igualmente obrigatório. Um contador, no mesmo painel, ao lado dos dois que acabei de acrescentar.

### 2.6 Testamento lavrado por substituto

A Lei 8.935/1994, art. 20, § 4º (conferido) diz que os substitutos podem praticar simultaneamente
todos os atos do titular **exceto, nos tabelionatos de notas, lavrar testamentos**. O sistema já
cadastra a função de cada usuário e já a imprime nos documentos — mas não impede que um usuário
com função de Substituto lance um testamento no livro.

É uma trava de três linhas no lançamento, com base legal explícita e nominada.

### 2.7 RCDUV — comunicação obrigatória sem caminho

`CENTRAIS` conhece o RCDUV e `CENTRAIS_COM_REMESSA` deliberadamente o exclui, com um comentário
que explica por quê: a lista separada evita a tela oferecer um botão que geraria arquivo em
branco. A decisão está certa. Fica o registro de que a comunicação da Diretiva Antecipada de
Vontade é **obrigatória, gratuita e sigilosa**, e hoje só existe se alguém fizer à mão, fora do
sistema. Vale um lembrete na tela de remessas, para não sumir da vista.

---

## 3. ~~Um achado fora do módulo de notas~~ — RESOLVIDO em 17/08/2026

O `before_request` do `app.py` abria transação de **escrita** em toda requisição. Medido: onze
telas de leitura devolviam HTTP 500 depois de dez segundos, com outro balcão escrevendo. Agora a
manutenção roda uma vez por dia, com recuperação de atraso, reserva atômica e falha registrada.

Junto foi o **traslado**, a última tela de leitura que ainda morria sob lock — não pela manutenção,
mas pelo `audit()`. A auditoria passou a esperar 800 ms em vez de 10 segundos e, falhando, registra
a linha no log do servidor.

Detalhe e as três armadilhas que a revisão obrigou a cobrir: `docs/tecnico/NUMERACAO_DE_LIVRO.md`.

## 4. Boas práticas de escrituração que o sistema agora sustenta

O que se consegue afirmar, com o código na mão, sobre a escrituração das notas:

- **numeração seguida, sem furo e sem repetição**, garantida em três camadas: contador explícito,
  transação `BEGIN IMMEDIATE`, e índice único no banco;
- **sem claros nem espaços em branco** (art. 795, § 2º): o `texto_corrido()` já fechava os
  buracos dentro do ato; agora o verso que sobra entre um ato e outro é apontado para
  inutilização, que era o único claro que restava;
- **números por extenso com repetição em algarismos** (art. 795, § 4º) nos termos de abertura e
  encerramento;
- **livro que se identifica**: termo de abertura obrigatório, com folhas, CNS e titular; termo de
  encerramento que diz até onde foi usado e o que ficou inutilizado;
- **unidade do ato**: nenhum ato se divide entre dois livros;
- **irreversibilidade do que foi ao papel**: folha usada não volta para a fila, nem por
  cancelamento; ato lançado não se relança; ato errado se anota à margem — quando 2.1 estiver
  feito;
- **rastro**: quem lançou e quando, em `lancado_por`/`lancado_em` e na auditoria, com livro,
  folha e termo nos detalhes;
- **conferência antes da correição**: folha pulada, folha repetida, termo faltando, num link.

---

## 5. Ordem sugerida para a próxima rodada

Dos seis itens da lista original, **três já saíram** (2.1, 3 e a inutilização impressa da face em
branco). O que resta, na ordem que eu atacaria:

1. **Epígrafe no teor** (2.2) — `notas_teor.montar()` promete "LIVRO, FOLHA, natureza do ato" na
   docstring e não gera. Antes era impossível; agora o livro e a folha existem no lançamento.
2. **Truncamento vira impedimento** na CENSEC (4 caracteres) e na DOI (6) — 2.3.
3. **Medição real de página** — fecha o ajuste de entrelinha, que hoje só sugere. `soffice
   --headless --convert-to pdf` + `pypdfium2`, os dois já quase montados na casa. Descrito em
   `notas_inutilizacao.sugerir_entrelinha`.
4. **Contador de ato sem selo** (2.5) e **trava do testamento por substituto** (2.6) — baratos,
   com base legal nominada.
5. **MNE / e-Notariado** (2.4) — maior, e só urge quando o primeiro ato eletrônico aparecer.

E uma dívida que esta rodada criou: a **anotação à margem não sai na certidão**, porque o módulo de
notas ainda não tem rota de certidão — só de traslado. Quando a certidão existir, ela tem de puxar
`notas_anotacoes.do_ato` como o traslado já puxa.
