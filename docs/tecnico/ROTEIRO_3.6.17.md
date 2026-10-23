# Roteiro para aplicar a versão 3.6.17

A 3.6.15 você aplicou em 27/08/2026 às 08h41. A 3.6.16 e esta são do mesmo dia,
e **esta traz as duas**. Os roteiros anteriores ficam como registro.

---

## O que esta versão traz

### 1. Cada atribuição no seu próprio lugar (vinha da 3.6.16)

Acabou o item «Demais atribuições» — o Registro Civil desta casa aparecia como
*demais*. Agora há **Protesto**, **Registro Civil** e **RCPJ e RTD** como grupos
próprios; o **Livro 3 foi para o Registro de Imóveis**, que é de onde ele é; e o
núcleo ganhou o grupo **Livros e acervo**.

O **RCPJ** e o **RTD** passaram a ter cada um a sua lista.

### 2. O selo sai quando o ato é praticado (vinha da 3.6.16)

Como você pediu. Se o aparelho não responder, o ato é lavrado **sem selo** e a
tela diz isso na mesma frase — balcão parado é pior que selo atrasado.

### 3. O caminho do selo do civil, medido e fechado

Medi os **1.413 selos do civil** do acervo. Três coisas saíram dali:

**A receita de custas do RCPN existe** — e este projeto dizia que não. Estava
escrito que a casa mandara o código do ato *vazio* nos 1.238 selos; **está
preenchido em 1.228 deles**. Quem mediu antes olhou a coluna errada. São 918
usos de `14.5.1` (certidão de uma folha), 237 de `14.5.6` (inteiro teor) e 60 de
`14.5.7`.

**O caminho do selo agora se compõe da espécie e do ato** — `/selo/civil/
nascimento`, `/nascimento/averbacao`, `/nascimento/segunda-via` — e **se confere
contra o contrato do selador** antes de sair. Caminho que não existe não é
usado: o ato sai sem selo, dizendo por quê.

**As três espécies que faltavam, como você decidiu**: casamento religioso sela
pelo caminho do casamento (muda o livro, não o ato), proclamas pela habilitação,
e o **Livro E se partiu em seis** — ausência, interdição, tutela, emancipação,
união estável e opção de nacionalidade, cada uma com nome próprio na tela.

### 4. O razão dos selos deixa de começar vazio

A carga passou a trazer os **26.130 selos** que esta casa emitiu em seis anos.

Isso conserta uma coisa que ninguém veria: a trava que recusa **selo repetido**
comparava contra uma tabela vazia. Um selo de 2023 podia ser digitado hoje como
novo, e nada recusava. Agora ela tem memória.

O ensaio contra o acervo devolveu **1.304 selos obtidos e não usados** — os
órfãos que o E-Ofício deixou, 5% de tudo o que foi selado. Eles entram como
órfãos, e é assim que aparecem na tela de selo obtido e não usado.

### 5. O estoque de folhas de segurança

Nova tela: **Registro Civil → Folhas de segurança**.

A certidão do civil é impressa em folha numerada da ARPEN, e **o selo leva o
número dela** — foi medindo isso que descobri que o sistema não controlava o
papel. O E-Ofício controlava 510 folhas; este agora também.

| | |
|---|---|
| **Dar entrada numa caixa** | você e o gerente, com a faixa impressa na caixa |
| **Inutilizar uma folha** | qualquer um do balcão, com o motivo escrito |
| **A próxima folha** | é a menor em branco — a ordem é a da gaveta, não a da escolha |

E a carga traz o estoque do E-Ofício: **510 folhas, 161 usadas e 349 em branco**.

### 6. Um selo para cada item da tabela de emolumentos

Como você decidiu: *"todos os selos são automáticos, escolhendo pelo item da
tabela de emolumentos"*.

**O selo sai no ato**, e o **protocolo é a fonte dos itens** — foi a sua
correção, e ela é o desenho todo. Quando o ato nasce de um protocolo, os itens
que abriram o protocolo são os que selam; quando o balcão lavra direto, valem os
itens marcados para cobrar.

**Um selo por item, e a conta é por unidade.** Medido em 120 protocolos de 2026:
**101 têm exatamente os selos dos itens que os abriram**. O protocolo
`2026.08.103` abriu um item `13.18` com quantidade 10, e saíram **10 selos**.

Cada item leva a **sua própria referência** — `pt_atos:12:17.4`. É dela que sai o
número que faz o aparelho devolver o selo que já existe em vez de vender outro;
uma referência só para três itens traria **o mesmo selo três vezes**.

### 7. O selo do Protesto e o das Notas, medidos

**O Protesto sela por natureza do ato**, e essa foi a parte que mais me fez
errar: a mesma palavra quer dizer coisas diferentes em lugares diferentes. Na
certidão, `0` é «por nome»; no título, `0` é «intimação por carta protocolada». E
`CANCELAMENTO` é natureza `9` quando é baixa do protesto e `0` quando é certidão
de cancelamento. Quem desempata é a **tabela**, nunca a palavra — e são duas
correções que os números do acervo pegaram.

**As Notas estão medidas e ainda não ligadas.** O caminho, a natureza da firma e
o envelope saíram de mais de vinte mil selos e estão prontos em `ato_selado`. O
que falta é a passada pelo módulo de Notas, que é o mais antigo da casa e o de
maior movimento — metade do que esta serventia sela é reconhecimento de firma. É
o próximo trabalho, e ele merece a passada inteira, não um remendo.

### 8. O protocolo geral e o caixa viraram a mesma coisa

Como você pediu: *"juntemos protocolo geral com o caixa; no caixa/protocolo geral
colocamos os serviços prestados"*.

**Quitar um item do protocolo agora lança no caixa**, com os quatro fundos
separados. Antes, quitar só marcava uma bandeira, e o dinheiro entrava por outro
caminho — o botão «cobrar» da ficha do ato. Dois trilhos para o mesmo dinheiro é
como eles divergem: o protocolo dizia que o cliente pagou, o caixa não tinha o
lançamento, e a conferência do dia fechava com uma diferença sem origem.

**O tamanho disso, medido no banco do servidor**: `cx_protocolo_atos` tem 32.416
serviços, e **nenhum deles jamais virou lançamento de caixa**.

**Um recibo do atendimento inteiro** — quem pede três cópias autenticadas e uma
certidão na mesma ida ao balcão leva **um papel**, e não quatro. Ele é do que já
entrou no caixa, e não do que foi orçado.

**Desquitar não apaga lançamento**: dinheiro que entrou sai por estorno, que
deixa rastro. A tela recusa e diz qual lançamento estornar.

**O protocolo do RI fica separado**, com os atributos da prenotação, atrelado ao
geral — foi o único pedaço desta mudança que não precisou de nada, porque já era
assim.

### 9. A certidão do Livro 3 ficou dentro do Registro de Imóveis

Correção sua, de hoje. O Livro 3 já tinha ido para o RI, mas a **certidão** dele
abria o grupo de RCPJ e RTD — quem estava no Livro 3 e pedia a certidão via o
menu pular para outro módulo. A tela é a mesma das três atribuições; o que mudou
é ela abrir o grupo **daquela que está mostrando**.

---

## Os passos

> **Correção de hoje**: os roteiros anteriores começavam com
> `net stop CartorioGestao`. **Não existe serviço com esse nome** — conferi. O
> servidor desta casa roda como **tarefa agendada** (`CartorioGestaoServidor`),
> e quem a para e a sobe de volta é o próprio `ATUALIZAR_SISTEMA.cmd`. O comando
> antigo não parava nada; só respondia que o nome não vale.

### 1. Ninguém lavrando

O balcão fecha por uns dois minutos. O servidor vai parar e voltar.

### 2. Guardar o banco — pelo próprio sistema

Duplo clique em `FERRAMENTAS\BACKUP_AGORA.cmd`, **ou** na tela
*Administrativo → Configurações*, botão **Criar e baixar backup completo**.

**Não copie o arquivo do banco com o servidor no ar.** O banco trabalha em modo
WAL: parte do que foi gravado está num arquivo ao lado, e a cópia crua pega o
banco pela metade — um backup com cara de bom que não abre quando você precisar.
O backup do sistema fecha, confere o zip e o SHA-256, e só então dá o arquivo
por pronto.

### 3. Aplicar

Duplo clique em `SERVIDOR\ATUALIZAR_SISTEMA.cmd`. O Windows vai pedir permissão
de Administrador — confirme **Sim**.

Ele faz quatro coisas e diz cada uma: para o servidor, copia código e telas,
confere as dependências e sobe o servidor de novo. No fim tem de aparecer
**«Servidor respondendo.»** e **«Versao carimbada: 3.6.17»**.

> O carimbo é novidade desta versão. Até hoje o `install.json` e o `VERSAO.txt`
> diziam **3.2.1** com a 3.6.15 rodando — conferi agora, ainda dizem. Depois
> desta atualização os dois passam a dizer a verdade.

Feito isso, no navegador: **Ctrl+F5**.

### 4. Conferir que subiu

Abra `http://127.0.0.1:8765/saude` no navegador do servidor. Tem de dizer
`"version": "3.6.17"`.

Se você preferir aplicar pelo pacote em vez do script — é o caminho do
`.cgu`, para quando a pasta do projeto não estiver na máquina —, o arquivo é
`CartorioGestao_3.6.17.cgu` e a impressão digital SHA-256 dele é:

```
0763f1d88ac88352b11f4872d1f7dad3c4db4211987db86c0cde1ae09e604bb5
```

```bat
certutil -hashfile CartorioGestao_3.6.17.cgu SHA256
```

**Os dois caminhos instalam a mesma coisa**; não faça os dois.

Esta versão acrescenta **duas tabelas** — `pp_remessas` e `pp_folhas`, do papel
de segurança — e mais nada. As duas entram sozinhas ao abrir o banco, e nenhuma
apaga nada.

### 5. Rodar a carga do acervo — **é o passo que falta desde a 3.6.15**

Em *Livros e acervo → Trazer o acervo do E-Ofício*.

As quatro atribuições continuam **de pé e vazias**, e nenhum contador foi
semeado. Enquanto isso não for feito, o primeiro ato novo de cada série nasceria
com o número 1 sobre acervo que já passou disso.

Ao terminar, confira:

| Contagem | Tem de dar |
|---|---|
| `pessoas_de_filiacao` | 1084 |
| `atos_de_registro` | 244 |
| `assentos_com_livro_a_confirmar` | 3 |
| **papel — `em_branco`** | **349** |
| **papel — `usadas`** | **161** |
| **selos — inseridos** | **26.130** |
| **selos — obtidos e não usados** | **1.304** |

**Número diferente disso, pare e me diga.**

### 6. Os quatro cliques do selador

Em *Administrativo → Selador — configuração*, nesta ordem:

**Importar do E-Ofício** → **Ver o certificado** → **Fixar** → **Testar**.

Usuário e senha estão dentro do acervo e o botão os traz — **ninguém precisa
digitar senha**, e eu não a vejo em momento nenhum. O aparelho está ligado e o
certificado confere.

Enquanto estes quatro cliques não forem dados, o ato é lavrado e a tela diz, na
mesma frase, que ele saiu **sem selo** e por quê.

### 7. Informar a numeração que só você sabe

Em *Livros e acervo → Numeração dos livros*: o próximo número do **Registro de
Protestos** e do **Registro de Pagamentos**, e o dos três livros do RCPN que o
E-Ofício nunca teve (B-Auxiliar, C-Auxiliar e D).

O acervo não tem esses números, e sem eles o primeiro ato de cada série nasce
com o **número 1** sobre acervo que já passou disso — o defeito de 18/08 outra
vez.

---

## O selo do civil está inteiro nesta versão

O envelope ficou pronto: caminho, item da tabela de custas, isenção, livro,
folha, termo, escrevente, nome da parte e o número da folha de segurança.

**A folha só se gasta se o selo sair.** Ela é reservada antes do pedido e vai
dentro do envelope; a baixa acontece depois de o aparelho responder. Se ele não
responder, ela continua em branco — porque continua em branco na gaveta.

**Falta só a sua parte**: os quatro cliques da configuração do selador. Enquanto
ela não for feita, o ato do civil é lavrado e a tela diz, na mesma frase, que
ele saiu sem selo e por quê.

### Onde o selo automático já está ligado, nesta versão

| | |
|---|---|
| **Registro Civil** — registro, averbação, anotação, retificação e certidão | **automático** |
| **Protesto** — apontamento, protesto, pagamento, desistência, cancelamento e certidão | **automático** |
| **Notas** | envelope medido, **ainda não ligado** — é o próximo trabalho |
| **RCPJ, RTD e Livro 3** | selo digitado à mão; o envelope de cada um ainda não foi medido |

Nas duas atribuições automáticas, se o aparelho não responder o ato é lavrado e
a tela diz, na mesma frase, que ele saiu **sem selo** e por quê. Ele fica na
lista de *ato sem selo*, e não se perde.

---

## Se algo der errado

Pare o servidor e devolva o banco do backup que você fez no passo 2:

```bat
schtasks /End /TN CartorioGestaoServidor
```

O pacote do backup é um `.zip` com o banco dentro, em
`%PROGRAMDATA%\CartorioGestao\backups`. Descompacte, ponha o
`cartorio_gestao.sqlite3` de volta em `%PROGRAMDATA%\CartorioGestao` **apagando
antes os arquivos `-wal` e `-shm` que estiverem ao lado** — eles são a parte
gravada do banco velho, e deixá-los ali misturaria os dois. Depois:

```bat
schtasks /Run /TN CartorioGestaoServidor
```

e me diga o que apareceu na tela, com as palavras que estavam escritas nela.
