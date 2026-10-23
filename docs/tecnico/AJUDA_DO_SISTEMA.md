# A ajuda do sistema

Pedida pelo oficial em **26/08/2026**:

> *"Conseguimos incorporar um módulo de API do Claude dentro do sistema para
> consulta e solução de problemas durante o uso do sistema?"*

Sim. E o alcance foi decisão dele.

---

## As duas decisões que ele tomou, e por que foram perguntas

### O que o módulo pode ver

Perguntei se ele podia ver **só o uso do sistema** — "como lanço uma
averbação?", "o que quer dizer este erro?" — ou **também o ato**: interpretar
recusa da CRA, conferir se uma qualificação está completa, ajudar com minuta.

Na primeira, nada de ato sai da serventia. Na segunda, sai.

**Ele escolheu também o ato.** Levantei o ponto do sigilo antes de perguntar, e
ele decidiu — é decisão de delegatário, não de programador. O que cabe ao
módulo é cumprir a decisão **com o menor risco possível**, e é o que está
abaixo.

### Quem pode usar

> *"Por enquanto habilitar esse módulo apenas para o administrador."*
>
> *"Com opção de expandir."*

**A segunda frase é que mudou o desenho.** "Só o administrador" sozinho seria
um `@roles_required("ADMIN")` na rota — e aí o dia de abrir para o balcão
dependeria de alguém mexer no código.

Como ele pediu a opção de expandir, a regra foi para o **banco**: quando
decidir, ele marca na tela, sozinho, num sábado, sem programador no meio.

Duas travas nisso:

- **O ADMIN nunca sai da lista**, mesmo que seja desmarcado. Senão a única
  pessoa que pode desfazer a mudança se tranca do lado de fora, e o conserto
  vira mexer no banco à mão com o balcão parado.
- **Configurar continua só do ADMIN**, mesmo depois de a consulta ser aberta
  para todos. Quem muda a regra não pode ser quem a regra alcança.

Cada mudança fica escrita: quem abriu, quando, e por quê.

---

## As peças

| Arquivo | O que é |
|---|---|
| `agente_provedores.py` | o transporte — só leva e traz. **É o mesmo do Agente do sistema**: a Ajuda tinha um cliente só da Anthropic, aposentado em 14/09/2026 |
| `ajuda.py` | a regra — quem pode, o que é mascarado, os tetos, o rastro |
| `ajuda_ferramentas` | as leituras que a Ajuda pode fazer desta instalação, por perfil (as mesmas ferramentas do agente, sem nenhuma de escrita) |
| `ajuda_mapa.py` | o que a ajuda sabe desta instalação, **medido** |
| `ajuda_problemas.py` | o que quebrou, a conferência da casa e o relatório |
| `ajuda_web.py` | as telas, e a **janela que existe em toda tela** |
| `templates/_ajuda.html` · `static/ajuda.js` | a janela |

### Sem dependência nova

`http.client` e `ssl`, da biblioteca padrão. Nem `requests`, nem o pacote
oficial `anthropic`.

É a mesma decisão do selador, e pelo mesmo motivo: **o sistema roda em máquina
de serventia, instalado por `.cmd`, e uma dependência a mais é um jeito a mais
de a instalação falhar num sábado.**

---

## O que protege o sigilo, já que o alcance foi aberto

### Mascara por padrão

CPF sai `***.456.789-**`; telefone e e-mail, escondidos. É a mesma
`serventia.mascarar_texto` que já protege todo papel que deixa esta casa — e
**um texto que vai para uma ferramenta de fora é papel que deixa a casa**,
mesmo que o destino seja uma máquina.

A máscara vale para a **pergunta** e para o **contexto**. Mascarar só o que se
cola deixaria a porta aberta pelo lado de dentro: o escrevente escreve "o CPF
123… não passa" na própria pergunta.

Mandar inteiro é uma caixa a marcar, e a consulta fica **registrada como
enviada sem máscara**, numa lista própria para conferir. Escolha deliberada é a
que merece ficar à vista.

### A tela mostra o que sairia, antes de sair

Quem manda dado para fora tem direito de ver o que está mandando. O botão *"Ver
o que sairia"* monta o texto e **não envia nada**.

A prévia usa **a mesma função** da consulta — não uma cópia parecida, que
divergiria no primeiro conserto e faria a tela mostrar uma coisa e mandar
outra.

### Tudo fica guardado

`aj_consultas` grava a pergunta, **o que saiu inteiro**, o que voltou, quem
perguntou, quanto custou, e se foi mascarado.

Guardar só a pergunta esconderia o contexto que o sistema juntou sozinho — e é
ele que explica por que a resposta veio como veio.

> Se um dia alguém perguntar **"o sistema sugeriu isso?"**, a resposta não pode
> ser opinião.

---

## A chave não entra no banco

Ela mora em `%PROGRAMDATA%\CartorioGestao\agente.cred`, ao lado de
`selador.cred` e do `secret.key`. **É o mesmo arquivo do Agente do sistema**,
e há uma chave por provedor (DeepSeek, Claude, GPT ou Grok).

A chave da Anthropic que já estava em `claude.cred` continua valendo: é lida
como compatibilidade, e só depois do arquivo do agente. Quem já tinha
configurado a Ajuda não digita nada de novo — e a ordem é declarada, para não
haver duas verdades.

**O banco viaja**: vai no backup, e o backup já saiu da serventia. Chave de API
dentro dele é chave publicada. Há teste que varre o banco inteiro procurando a
chave depois de gravá-la.

---

## Nada trava se a API cair

Prazo curto, mensagem de balcão, e o atendimento segue — a mesma regra do
selador. **Ajuda que derruba o atendimento é pior que ajuda nenhuma**: o
cliente está na frente do escrevente, e a dúvida dele é menor que a fila.

E a chamada **nunca acontece dentro de `db.transaction()`**. Por isso
`consultar` recebe `db` e não `con`: assim não há como alguém chamá-la de
dentro de uma transação sem reparar no que está fazendo. Uma chamada de rede de
trinta segundos segurando o `BEGIN IMMEDIATE` poria a casa inteira no
`busy_timeout`.

**A falha também se grava.** Um dia em que a internet caiu não pode parecer um
dia em que ninguém perguntou.

---

## O teto de gasto é do módulo

A API cobra por uso. Um laço que engasgue, ou um dia de curiosidade, gastam
dinheiro da serventia sem ninguém perceber.

**120 consultas por dia**, contadas no banco, e a recusa vem com a conta na
mão. Seis usuários fazendo cinco perguntas por dia dão trinta — o teto é
generoso e ainda assim segura um erro que se repita sozinho.

---

## A IA auxilia; não decide

É a regra que já vinha do usucapião, e aqui ela está **no código**, não só no
texto: há teste que varre os nomes públicos do módulo procurando `lavrar`,
`numerar`, `selar`, `cobrar`, `cancelar`, `averbar`, `decidir`. Se alguém
acrescentar uma, fica vermelho.

A instrução que vai junto de toda pergunta diz isso ao modelo com todas as
letras — e mais uma coisa:

> Você **não inventa** número, código, selo, matrícula nem prazo. Se não
> souber, diga que não sabe e diga onde se confere.

Número chutado num cartório vira documento errado na mão de alguém, e isso não
se desfaz.

---

## O que a instrução conta sobre esta casa

Uma resposta genérica sobre "cartório" não serve ao balcão: fala do cartório em
tese, de prazos de outro estado e de livros que esta casa não tem.

A instrução diz qual é a serventia (Cidade Exemplo, CNS 000000, ofício único),
quais normas valem (TJMA, mais a 6.015/1973, a 8.935/1994 e a 9.492/1997), o
que é este sistema, e **de qual tela a pergunta nasceu**.

Cada linha dela é fato medido, e não adjetivo.

---

## Um defeito que o teste da casa pegou

A primeira versão contava as consultas do dia recortando os dez primeiros
caracteres da data **dentro do SQL**. O teto de acoplamento ao SQLite
(`tests/test_portabilidade.py`) recusou: módulo novo entra com **zero**.

A correção — comparar por faixa de data — deixou a consulta **melhor**: função
aplicada sobre a coluna não usa o índice; comparar por faixa usa.

E teve um segundo round: ao explicar o conserto no comentário, eu **citei a
chamada antiga literalmente** — e o varredor, que lê o arquivo inteiro,
contou-a como se ela ainda existisse. A lição ficou; a citação saiu.

> Regra que se aplica ao arquivo inteiro alcança também o comentário que fala
> dela.

---

# A segunda parte, de 26/08/2026

O pedido seguinte do oficial, no mesmo dia:

> *"Continue o desenvolvimento da API para que seja uma janela de ajuda em
> todas as telas e módulos do sistema. A API deve acessar, verificar e ser
> notificada sobre problemas e gerar relatório para que seja corrigido pelo
> Claude Code posteriormente. Deve ter conhecimento amplo do sistema para
> consulta."*

São quatro coisas, e cada uma mudou uma parte do desenho.

---

## 1. A janela em todas as telas

A ajuda tinha **uma** tela, no menu Administrativo. Quem estava com dúvida no
meio de um ato precisava sair do que estava fazendo para chegar até ela — e
perder o que tinha digitado.

**Ajuda que cobra o abandono da tarefa é ajuda que ninguém usa na hora em que
precisa dela.** O escrevente desiste, chuta, e o chute vira ato.

Agora a janela fica presa no canto de **qualquer** tela: um botão, e uma gaveta
que abre por cima sem recarregar a página nem apagar o que estava preenchido.

### Ela mora no `base.html`, e isso é a decisão

É a mesma da lupa das assinaturas, com a razão escrita lá:

> *"Ligada tela a tela, a primeira que alguém criasse amanhã nasceria sem lupa
> — e sem aviso nenhum de que nasceu."*

E o teste é do mesmo tipo do teste do menu: ele **varre as telas uma por uma** e
exige a janela em cada uma. "Em todas as telas" não se prova olhando uma função.

### Sem JavaScript ela continua funcionando

O botão é um **link** para a tela inteira, já com a tela de origem no endereço,
e os dois formulários apontam para rotas que respondem página. O script só troca
a navegação por abrir e fechar.

É a regra do menu deste sistema: *o sistema roda em rede local, às vezes sem
internet, e o que precisa de script é o que some.*

### A tela de origem não se digita

Ela sai do `request.endpoint`, e o nome dela sai do mapa medido. **Campo que o
operador tem de preencher para a resposta ficar boa é campo que fica vazio.**

---

## 2. O conhecimento amplo do sistema — `ajuda_mapa.py`

A instrução dizia qual era a serventia e quais normas valiam. Isso basta para
dúvida jurídica e **não basta** para a pergunta mais comum do balcão, que é de
uso: *"onde é que eu lanço isto?"*.

Sem o mapa, a resposta a essas é chute educado — e chute educado num cartório é
pior que "não sei", porque parece certo.

### O mapa não se escreve: mede-se

Escrever à mão a lista das telas é o defeito que o **menu deste sistema já
cometeu e pagou**, e está escrito em `base.html`:

> *"A primeira versão listava as rotas de cada módulo à mão. Envelheceu na mesma
> tarde em que foi escrita: nove nomes que eu supus e não existiam, e vinte e
> três rotas reais de fora."*

Aqui seria pior: quem lê a lista velha não é um operador que estranha — é uma
máquina que responde com convicção. Então tudo vem de medição:

| O que | De onde |
|---|---|
| as telas e os endereços | `app.url_map` |
| o **nome** de cada tela | do próprio menu, em `templates/base.html` |
| o arquivo onde a tela mora | `view_functions[...].__module__` |
| as tabelas e as colunas | do catálogo do banco desta máquina |
| o que cada módulo é | da primeira linha da docstring dele |

O nome vir do menu não é economia: é **o nome que a casa usa**. Qualquer outro
seria um segundo vocabulário para as mesmas telas, e quem perguntasse "onde fica
X" ouviria de volta uma palavra que não está escrita em tela nenhuma.

O arquivo vir do Python, e não do prefixo do nome, também tem motivo medido:
`protesto_*` e `rcpn_*` moram os **dois** em `atribuicoes_web.py`. Supor pelo
prefixo mandaria quem conserta para um arquivo que não tem a tela dentro.

### Vai uma fatia, e não o mapa inteiro

São 218 telas e 105 tabelas nesta instalação. Mandar tudo em toda pergunta
custaria em toda pergunta, e afogaria a dúvida no meio do inventário.

Vai o menu — que é o que responde "onde fica" — e a **fatia** da tela de onde a
pergunta nasceu: o arquivo dela, as telas irmãs e as tabelas daquele módulo.
Cerca de 6 mil caracteres. E quando corta, **o corte fica dito**: mapa que some
em silêncio faz o modelo responder como se aquilo não existisse.

### O mapa não carrega dado de cliente, e isso se prova

Ele leva **nome** de tabela e de coluna, e nunca o conteúdo delas. Um mapa que
levasse valores mandaria dado do balcão para fora em toda pergunta, sem ninguém
pedir — e a máscara não pegaria, porque ela protege o que o escrevente digita,
não o que o sistema junta sozinho.

O teste monta um banco com **CPF, nome e endereço dentro** e procura os três no
mapa.

### O que saiu passou a ficar guardado inteiro

Enquanto a instrução era uma só, guardar a pergunta bastava para reconstituir a
consulta. Desde que ela carrega o mapa da tela, duas perguntas iguais saídas de
telas diferentes **mandam coisas diferentes** — e `aj_consultas.enviado` passou a
guardar as duas partes, que é o que a coluna sempre prometeu.

---

## 3. Ser notificada sobre problemas — `ajuda_problemas.py`

Até aqui, quando uma tela estourava, o que sobrava era a lembrança de quem
estava no balcão. **Lembrança de balcão em dia de movimento é o que se perde
primeiro**: o escrevente fecha a janela, atende o próximo, e o defeito volta na
semana seguinte com outra pessoa, que também não anota.

### O sistema avisa; ninguém precisa lembrar

Toda tela que estoura vira uma linha, sozinha, com a hora, a tela, o usuário e o
**ponto exato do programa** onde parou. Quem topou com o defeito não precisa
fazer nada — e é bom que não precise, porque ele está com o cliente na frente.

E o escrevente passou a ver uma página que diz **o que fazer** ("nada foi gravado
pela metade; se era um ato, refaça"), em vez do erro cru do servidor.

### Quem quiser contar, conta

Defeito que **não** estoura o programa — o botão que não faz nada, o número que
sai errado — é justamente o que máquina nenhuma percebe. Por isso a janela tem
"Avisar um problema desta tela".

**Isso não passa pela lista de perfis**, e é deliberado: consultar a API gasta e
manda dado para fora; anotar um problema não faz nem uma coisa nem outra. **Quem
topa com o defeito é o balcão**, e o balcão não pode ficar sem poder avisar por
causa de uma regra que existe para outra coisa.

### A mesma coisa duas vezes é uma linha, com um contador

Um defeito que acontece quarenta vezes num dia geraria quarenta linhas, e as
quarenta afogariam os outros três problemas da lista. Cada problema tem uma
**impressão digital** — a espécie do erro e o ponto do programa, com os números
trocados por `#`, porque `matrícula 1.234 não existe` e `matrícula 5.678 não
existe` são o mesmo defeito.

A unicidade mora no banco, num `UNIQUE`. É a regra da casa: nenhuma revisão de
código pegou o defeito de 18/08, e um `UNIQUE` teria pego.

### Duas coisas que ele **não** faz

**Não anota disputa de escrita.** Gravar no banco que acabou de travar é disputar
a mesma trava, e o balcão esperaria mais dez segundos por uma tela que já deu
errado. Essa espécie já está contada em `disputas_de_escrita.log`, que é arquivo.

**Não estoura nunca.** Um anotador que quebra enquanto anota um erro transforma
um defeito em dois e esconde o primeiro. Mesma regra de `_anotar_disputa`.

### O que voltou depois de relatado é a linha mais importante da lista

Problema que reaparece depois de mandado para conserto quer dizer uma de duas
coisas: o conserto não veio, ou não era o conserto. A nova ocorrência devolve o
problema para ABERTO **sem apagar** a data em que ele foi relatado, e a lista o
marca como `VOLTOU`.

### O jargão não chega ao balcão

O título do problema é técnico de propósito — `KeyError em ri_web.py:1234` é o
que serve a quem conserta. Mas a **janela** mostra "O sistema deu erro nesta
tela": `KeyError` na cara de quem acabou de levar um erro é jargão de programador
em cima de susto.

*(Isto foi correção: a primeira versão mostrava o título cru, e a própria página
de erro passou a exibir a espécie da exceção para quem estava atendendo. Quem
pegou foi o teste de tela — mais uma vez neste projeto.)*

---

## 4. Acessar e verificar — a conferência da casa

*"Conferir a casa"*, na tela **Problemas do sistema**, mede o que o sistema já
sabe medir em outros cantos e escreve o que encontrou:

- as **disputas de escrita** — e cinco em trinta dias é o gatilho medido da
  conversa sobre trocar de banco (`MIGRAR_DE_BANCO.md`);
- a **integridade do banco** e as chaves apontando para registro que não existe;
- **o que só o oficial pode informar** — série sem contador é o primeiro ato novo
  nascendo com o número 1 sobre acervo que já passou disso;
- a **manutenção diária** que não terminou — ela já se anotava sozinha em
  `settings`, e o que faltava era alguém olhar (era item do backlog antigo);
- as **consultas da ajuda que não voltaram** — um dia em que a internet caiu não
  pode parecer um dia normal.

Ela **mede; não conserta**, e não decide nada. E é pedida, não automática: lê o
banco inteiro e leva segundos — rodar isso ao abrir tela poria o balcão
esperando por uma coisa que ninguém pediu.

**Casa em ordem não gera achado.** Alarme que soa sempre é alarme que ninguém
ouve.

### E a leitura da ajuda sobre um problema

Cada problema tem o botão *"Pedir a leitura da ajuda"*: ela recebe o que ficou
escrito, mais o mapa da tela, e responde três coisas — o que provavelmente
aconteceu, o que o escrevente faz **agora**, e o que quem for consertar deve olhar
primeiro.

A resposta fica junto do problema e vai no relatório **marcada como conselho**.
Ela leu a mensagem; não conferiu o código.

---

## 5. O relatório para o conserto

O botão *"Gerar o relatório para conserto"* monta um arquivo `.md` com os
problemas abertos, o que a conferência mediu e o tamanho medido do sistema. Ele
**baixa e fica em disco**, em `%PROGRAMDATA%\CartorioGestao\relatorios\` — ficar
em disco é o que salva o dia em que o navegador perde o arquivo, ou em que quem
baixou não é quem vai mandar.

Cada problema traz **o arquivo onde a tela mora**, medido nesta instalação. É a
única linha do relatório que existe só para quem programa, e é a que economiza a
meia hora de procurar.

### Ele sai sempre mascarado

A consulta à API pergunta se pode ir sem máscara, porque às vezes o dado inteiro
é a dúvida. Aqui não é: **o relatório nasce para deixar a serventia**, e o que
conserta o programa é o ponto onde ele parou, e nunca de quem era o CPF que
estava sendo gravado. Um traceback carrega o que estava sendo escrito no banco —
então tudo passa pela mesma `serventia.mascarar_texto`, e a folha de rosto diz
que passou.

### Ele marca o que foi mandado — e só o que foi

Os problemas que entraram no relatório ficam `RELATADO`; o que não coube fica
`ABERTO`. *(A primeira versão marcava todos os abertos: um problema que ficasse
de fora pelo teto sairia da lista como se tivesse sido mandado, e ninguém
consertaria o que ninguém recebeu.)*

Cada relatório fica registrado com a **impressão digital SHA-256** do arquivo —
a mesma conferência que o roteiro de atualização já pede com `certutil`, e pelo
mesmo motivo: quem recebe confere que o que chegou é o que saiu.

---

## Um defeito que estava de pé, e que este trabalho achou

A rota que mostra uma consulta antiga recusava quem não tem perfil com
`redirect(url_for("index"))` — **e não existe rota chamada `index` neste
sistema**. O `url_for` estourava, e a recusa virava HTTP 500 na cara de quem ela
recusava.

Nenhum dos quinze testes daquele módulo passava por ali: todos entravam como
ADMIN, e o ADMIN nunca é recusado.

> **O caminho de recusa é o que ninguém exercita à mão** — e é justamente o que
> só aparece para quem já está com um problema.

Está consertado, e agora tem teste.

---

## O que a segunda parte NÃO fez, e por quê

**A ajuda não conserta nada.** Ela lê, explica e escreve o relatório; o conserto
é do programador, com o código na frente. Há teste que varre os nomes públicos
dos dois módulos novos procurando `corrigir`, `consertar` e `aplicar`, além dos
verbos de ato que já eram proibidos.

**A conferência não roda sozinha.** Nem ao abrir tela, nem por hora marcada. Ela
lê o banco inteiro, e o balcão não pode esperar por uma coisa que ninguém pediu.

**O relatório não se manda sozinho.** Ele baixa e fica em disco; quem decide
mandar, e para quem, é o oficial. Arquivo que sai da serventia por conta própria
é exatamente o que este projeto passou dois dias evitando.
