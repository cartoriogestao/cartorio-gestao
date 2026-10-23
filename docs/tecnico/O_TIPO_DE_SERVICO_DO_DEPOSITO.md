# O tipo de serviço do depósito prévio — relato #50

**Data:** 17/09/2026 · **Relato:** #50, do oficial
**Onde:** `caixa_depositos.py`, `caixa_web.py`, `caixa_schema.py`,
`templates/caixa_depositos.html`

O relato tinha duas metades, e elas foram feitas em dias diferentes: **a data do
depósito** e as **informações do tipo de serviço**. Este documento é sobre a
segunda — a primeira está em `tests/test_relato_50_data_do_deposito.py`.

---

## 1. O que estava lá, medido

A tela do depósito prévio tinha **dois** campos de texto: o depositante e a
observação. O tipo do serviço não existia como campo.

E a casa resolveu isso **à mão, na observação** — dos 14 depósitos da produção,
em 17/09/2026:

| id | o que a observação diz | vínculo |
|---|---|---|
| 2 | «ESCRITURA PÚBLICA DE COMPRA E VENDA DA MATRICULA 4…» | protocolo 21.343 (NOTAS) |
| 4 | «DEPOÓSITO PRÉVIO DE 2 ESCRITURAS, UMA DE INVENTÁRI…» | — |
| 6 | «GEORREFERENCIAMNETO AGUARDANDO CUMPRIMENTO DE NOTA» | — |
| 9 | «REGISTRO ESCRITURA DE COMPRA E VENDA LAVRADA NESTA…» | — |
| 11 | «AVERBAÇÕES CADASTROS RURAIS» | — |
| 3, 12, 13, 14 | «Depósito prévio do título 11.568/1A» | prenotação do RI |

**Texto livre não soma, não filtra e não se conta.** Quem quisesse saber quanto
se depositou por averbação teria de ler os catorze.

E o vínculo — que é quem carrega o tipo — estava vazio em **oito** dos catorze.

## 2. As três decisões do oficial

| | |
|---|---|
| **granularidade** | o **serviço do catálogo** (`cx_servicos`, 1.317 linhas, 1.305 com código do TJ) **mais a atribuição**, que sai sozinha do vínculo e do grupo do serviço |
| **obrigatoriedade** | **opcional** — 8 dos 14 não têm vínculo, e o depósito solto é legítimo; a lista declara quantos estão sem tipo |
| **dados antigos** | preencher **só os 6 que têm vínculo** — a atribuição deles é fato lido do protocolo/prenotação, não palpite |

## 3. O que foi construído

### No depósito novo

Dois campos a mais no formulário: a **atribuição** (as oito da casa, as mesmas
de `cx_protocolos.atribuicao`) e o **serviço** — que aceita o **código do TJ**
ou uma **palavra**.

**A busca é resolvida no servidor.** A busca instantânea do protocolo (relato
#53) vive num formulário que não recarrega; o do depósito **é** o cadastro, e
Enter manda registrar. Sequestrar o Enter para buscar faria o balcão gravar sem
querer. Então a tela aceita a palavra e resolve no envio, e **funciona sem
JavaScript**.

**Quando a palavra acha mais de um serviço, a tela recusa listando os
códigos.** Recusar sem dizer quais é fazer a pessoa digitar de novo e receber o
mesmo silêncio. A mensagem mostra até oito e o resto vira «e mais N».

### O vínculo responde sozinho

Quando o depósito está amarrado, o tipo é **fato lido**, e não palpite:

| vínculo | o que ele declara | por quê |
|---|---|---|
| `protocolo_id` | a atribuição daquele protocolo | a tela que abriu o protocolo já a gravou |
| `ri_protocolo_id` | **RI** | `ri_protocolos` é a tabela de protocolo do Registro de Imóveis |
| `nt_ato_id` | **NOTAS** | `nt_atos` é o ato de **livro** do Tabelionato |

E o **serviço** sai do protocolo **quando ele tem um item só**: com vários itens
o depósito cobre o conjunto, e escolher um deles seria escolher por quem atende.

**Se o vínculo e o serviço escolhido discordarem, o vínculo ganha e a
divergência aparece.** É a mesma ordem do selo, onde o código do ato precede o
texto: o vínculo é fato, o grupo do serviço diz por quais tabelas ele passa — e
discordarem não é empate a desempatar por ordem, é uma das duas coisas que está
errada. Quem sabe qual é quem atende.

### O botão dos antigos

Alcança **6 dos 14** — só os que têm vínculo. Os outros 8 ficam sem tipo, e a
lista declara quantos são.

**Ele grava pela mesma régua do cadastro** (`sugerir_tipo`), e não por uma
segunda leitura do vínculo: o que o botão grava tem de ser o que a tela gravaria
se aquele depósito fosse registrado hoje. Duas versões do mesmo `WHERE`
divergiriam no primeiro conserto.

O botão é **do oficial e do gerente** — a guarda está **dentro da ação**, e não
só na rota: `/caixa/depositos` é de todos, e o `gravar_tipos` recusa quem não
seja `ADMIN` ou `MANAGER`, dizendo a quem pedir. A tela não mostra o botão a
quem não pode usá-lo; a rota recusa porque é ela que faz — a mesma divisão da
conferência do caixa, e pela mesma razão: mexer na classificação de dinheiro que
já entrou não é gesto de balcão.

### O grupo do catálogo estreita o campo

Medido no próprio acervo, em `tbGrupoTJ`:

| grupo | atribuição |
|---|---|
| 22 | RCPN |
| 23 | RCPJ **e** RTD |
| 24 | RI |
| 25 | PROTESTO |
| **21** | **FIRMAS e NOTAS** — o acervo o chama de «atos dos tabelionatos de notas», e ali o balcão registra os dois: 10.310 firmas e 1.576 atos de livro, dois preços e dois caminhos de selo |

Escolher um serviço de Notas não deve fazer ninguém procurar Protesto na lista.
Mas **o grupo 21 não escolhe** — quem sabe qual dos dois é quem atende. E grupo
que não decide (o `0` do acervo, caso do prefixo 18) oferece **as oito** em vez
de esconder as que a casa usa: instalação sem o grupo semeado continua
funcionando.

## 4. O que ficou de fora, e por quê

- **O depósito solto continua sem tipo até alguém abrir e escolher.** Não se
  deduz do texto da observação: «REGISTRO ESCRITURA DE COMPRA E VENDA LAVRADA»
  casaria com dezenas de itens do catálogo, e escolher um seria inventar.
- **O filtro da lista é por atribuição e por termo do serviço**, não por faixa
  de valor nem por data — o relato não pediu, e cada filtro a mais é uma coluna
  a mais numa tabela que o balcão lê de pé.

## 5. As provas

- `tests/test_relato_50_tipo_de_servico.py` — a tela, o domínio, o vínculo, o
  botão dos antigos, o grupo e a busca sem JavaScript.
- `tests/test_relato_50_data_do_deposito.py` — a primeira metade.
- `tests/test_relato_53_busca_dos_atos.py` — a busca do item, que é a peça que
  o campo reusa.
