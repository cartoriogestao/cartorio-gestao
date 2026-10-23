# Roteiro para aplicar a versão 3.6.22

> **Esta traz tudo desde a 3.6.18.** Você está na 3.6.20; aplique só esta.

Trabalho da noite de 27 para 28/08/2026, sem interação: resolver as pendências
apontadas dentro do sistema e desenvolver o Registro Civil.

---

## O Registro Civil ganhou a peça que faltava

### A habilitação de casamento

O sistema sabia lavrar o **assento** de casamento. Não sabia nada das semanas
que vêm antes dele — e é ali que o casamento se decide.

Nova tela: **Registro Civil → Habilitação de casamento**.

```
abrir  →  documentos  →  edital  →  [oposição]  →  habilitar  →  celebrar
```

| etapa | fundamento | quem protege |
|---|---|---|
| documentos | CC art. 1.525, I a V | a lei exige, e é você que atesta terem sido cumpridos |
| edital | CC art. 1.527 | chama qualquer pessoa a opor impedimento |
| prazo de 15 dias | CC art. 1.527 | é o tempo desse direito |
| oposição | CC art. 1.529 | terceiro que sabe de impedimento |
| habilitar | CC art. 1.531 | você atesta que nada obsta |
| celebrar em 90 dias | CC art. 1.532 | vencido, o processo se refaz |

**O sistema recusa três coisas, e cada uma protege alguém:** habilitar sem
edital publicado, habilitar antes de vencido o prazo, e celebrar com a
habilitação vencida.

O **edital** e a **certidão de habilitação** saem em `.odt`, prontos para
afixar e para entregar. O modelo do edital já vem com os nomes dos nubentes —
campo em branco num edital é o que produz edital genérico.

E a ficha diz **o que fazer agora**, calculado do estado: num rito de semanas,
«e agora?» é a pergunta que mais se repete.

> **Não havia precedente a imitar, e isso foi medido.** O E-Ofício não tem
> tabela de habilitação nem de proclamas — guardava três datas dentro do assento
> final e o contador do Livro D, que marca **1.358 proclamas registrados**. Mil
> trezentas e cinquenta e oito habilitações aconteceram nesta casa sem deixar
> rastro. Sem precedente de forma, o que se imita é a lei.

---

## Duas das suas pendências foram resolvidas pelo próprio acervo

| série | próximo número | onde estava |
|---|---|---|
| **Proclamas — Livro D** | **1.359** | na configuração do E-Ofício |
| **Natimortos — Livro C-Auxiliar** | **13** | idem |

Eu havia declarado as duas como coisa que só você poderia informar, com o motivo
«o acervo não tem tabela de proclamas nem de natimortos». A conclusão sobre as
**tabelas** estava certa; sobre os **números**, errada — eles estavam guardados
noutro lugar, e ninguém tinha aberto.

**Continuam abertas duas**, e agora com a prova de por quê: o E-Ofício guarda o
**livro** do B-Auxiliar (casamento religioso) e do Livro E, e **não guarda o
número do registro** — esse campo não existe lá. Esses dois só saem do livro
físico.

---

## Um defeito que teria estragado o Livro E

Um assento entrava como Livro E por causa de **uma letra digitada errada** no
E-Ofício — e semeava o contador daquele livro em **8687**, com um número que é
de nascimento. O primeiro ato de Livro E desta casa nasceria com o 8688: o
defeito de 18/08 num livro que ainda nem foi usado.

O registro é o nascimento de PESSOA EXEMPLO, Livro 9, folha 102, número
8686, de 1994 — e **a matrícula dele diz Livro A**. A matrícula é o número
nacional impresso na certidão, e agora é ela que decide. A divergência vira
**aviso**, e não silêncio.

---

## O declarante entrou na carga

O declarante é **campo obrigatório** do assento de nascimento e de óbito (Lei
6.015/1973, arts. 54 e 80), e a certidão de óbito o nomeia. Ele não entrava.

Entram **117 declarantes e 20 testemunhas**. Os números são baixos porque o
acervo é assim: só 120 dos 225 declarantes e 20 das 450 testemunhas têm nome
gravado — o resto são linhas vazias que o E-Ofício criou. Linha vazia na certidão
é pior que ausência: afirma que há um declarante e não diz quem.

---

## O que mais vem junto (era a 3.6.21)

- **A prenotação do RI sela**, e o comprovante diz o prazo certo — o de REURB-S
  dizia 20 dias quando são 40
- **Ficha nova sem volume de papel** — Livro 2 e o número, e mais nada
- **As firmas num lugar só**, com abas, e os autógrafos junto dos cartões
- **A ficha do cartão para o cliente assinar**, em `.odt`
- **A etiqueta da autenticação de cópia**
- **As pendências das escrituras**: as 45 do E-Ofício saíram da lista de hoje

---

## Os passos

### 1. Guarde o banco

`FERRAMENTAS\BACKUP_AGORA.cmd`. **Não copie o arquivo do banco com o servidor no
ar.**

### 2. Aplique

`SERVIDOR\ATUALIZAR_SISTEMA.cmd`. No fim tem de aparecer **«Versao carimbada:
3.6.22»**. Depois, **Ctrl+F5**.

Esta versão acrescenta **três tabelas** ao banco — as da habilitação de casamento
— e três colunas. Entram sozinhas e não apagam nada.

Se preferir aplicar pelo pacote em vez do script, o arquivo é
`CartorioGestao_3.6.22.cgu` e a impressão digital SHA-256 dele é:

```
2d2ea69f5606ff46a8f0c4b42c777540d166d37a73e97624614e93c8f3828fc1
```

```bat
certutil -hashfile CartorioGestao_3.6.22.cgu SHA256
```

**Os dois caminhos instalam a mesma coisa**; não faça os dois.

### 3. Rode a carga do acervo de novo

*Livros e acervo → Trazer o acervo do E-Ofício*, tudo marcado.

O que já entrou volta como «já estavam» — isso é o certo. O que entra agora:

| | |
|---|---|
| **declarantes** | **117** |
| **testemunhas** | **20** |
| **proclamas — próximo número** | **1.359** |
| **natimortos — próximo número** | **13** |
| pendências restantes | só **B-Auxiliar** e **Livro E** |

### 4. Confira a data da tabela de custas

*Administrativo → Configurações*: **01/01/2026**.

---

## Três coisas para você decidir

**A senha do selador está em texto claro dentro do acervo**, é fraca, e o arquivo
vai junto no backup completo. Ela é conta do aparelho — peça a troca a quem o
instalou (FPFTech ou TJMA), e depois use o botão «Importar do E-Ofício» de novo.

**O selo da habilitação não sai ainda.** O caminho existe no contrato do selador,
mas esta casa nunca selou por ele — os 1.358 proclamas são anteriores ao selo
eletrônico, ou saíram por outro caminho. **Não se sela por caminho que a casa
nunca usou**: até medir, a habilitação sai sem selo e a tela diz por quê.

**A remessa do IBGE está medida, e não construída.** Achei os arquivos reais que
esta casa exportou e decodifiquei o essencial contra 28 assentos — data do
assento, data de nascimento, **sexo** (exato nas 28), municípios e o número da
**DNV**. Mas sobram seis posições que não se explicaram, e um gerador com elas
adivinhadas produziria arquivo que o IBGE aceita e que informa errado. O que
falta para fechar é **mais amostra**: se houver exportações antigas em backup, ou
se a próxima for guardada antes de enviada, o layout fecha. Ver
`LAYOUT_IBGE_MEDIDO.md`.

---

## Se algo der errado

```bat
schtasks /End /TN CartorioGestaoServidor
```

Devolva o banco do backup do passo 1 — descompacte o `.zip`, ponha o
`cartorio_gestao.sqlite3` de volta em `%PROGRAMDATA%\CartorioGestao` **apagando
antes os arquivos `-wal` e `-shm` que estiverem ao lado**. Depois:

```bat
schtasks /Run /TN CartorioGestaoServidor
```
