# O que a ajuda sabe do projeto

*29/08/2026 — resposta ao relato **#26** do oficial.*

> «melhorar as capacidades da resolução de problemas. Precisa poder permitir,
> caso preciso, acesso a mais informações, inclusive acesso ao projeto do
> sistema para saber o que já foi feito, o que falta.»
>
> «Ajuda precisa ganhar mais ferramentas e autonomia. Precisa se aproximar mais
> do que sabe o claude code que estamos desenvolvendo o projeto.»

---

## O que faltava, exatamente

`ajuda_mapa.py` já media as **telas**, os **arquivos** e as **tabelas** desta
instalação. Ele responde *«como o sistema é feito»* — e não responde nenhuma das
duas perguntas do oficial: **o que já foi feito** e **o que falta**.

Essas duas moram em três lugares, e os três são mensuráveis:

1. os **documentos do projeto**, que contam o que cada versão trouxe e o que se
   mediu antes de construir;
2. os **relatos** (`aj_problemas`), que dizem o que foi apontado e em que pé
   está;
3. as **pendências declaradas** (`implantacao`), que dizem o que só o oficial
   pode informar.

---

## A medição que decidiu tudo: o servidor não tinha um único documento

A ajuda roda **no servidor**. Documento que não viaja é documento que ela não
pode ler — e nenhum viajava.

Havia **duas pastas de documentação**, e elas não eram cópia uma da outra: eram
**duas metades**.

| | onde | quantos |
|---|---|---|
| os antigos | raiz do projeto | 67 |
| os recentes (`ROTEIRO_3.6.23` a `3.6.30`, `DOI_DA_SERVENTIA`, `CNIB_E_USUCAPIAO`, `ATO_DENTRO_DO_TEOR`, `REMESSA_IBGE_CONFERIDA`, `SELO_DO_CASAMENTO_MEDIDO`) | dentro da pasta empacotada | 13 |

E o índice do `CLAUDE.md` cita as duas metades como se fossem uma pasta só: quem
seguisse o índice não acharia metade dos arquivos.

Só a pasta **de dentro** viaja — o `.cgu` leva tudo o que está sob
`INSTALAR_CARTORIO_GESTAO`, e o instalador grava cada arquivo do manifesto.
(O `ATUALIZAR_SISTEMA.cmd`, que é o outro caminho, copia apenas `*.py`,
`templates/*.html`, `static/`, `VERSAO.txt` e `requirements.txt` — nenhum `.md`.)

Consolidadas: **80 documentos** na pasta que viaja, nenhum sobrescrito, e os que
existiam nos dois lugares eram idênticos byte a byte. Há teste que exige a pasta
lá dentro, com piso de 70.

> **Documentação em dois lugares diverge no primeiro conserto.** Aqui ainda não
> custou nada porque as metades não se sobrepunham — o que é sorte, e não
> desenho.

---

## O defeito que este módulo já teve, e ele é o mais instrutivo

`pendencias_declaradas` chamava `implantacao.pendentes`. **Essa função não
existe** — ela se chama `abertas`. E eu havia escrito:

```python
try:
    return [dict(x) for x in implantacao.pendentes(con)]
except Exception:
    return []          # «instalação sem a tabela ainda»
```

O `except` largo transformava um `AttributeError` — nome de função errado — em
**«zero pendências»**, com cara de medição. A tela mostraria zero, e quem lesse
concluiria que a casa não deve nada a ninguém.

São **nove**, e são justamente as nove coisas que esperam decisão do oficial: a
letra da posição 566, o Livro 6 de Apontamento, os três contadores do Protesto,
os casamentos do Livro B-Auxiliar, e os contadores do B-Auxiliar e do
C-Auxiliar.

> **Zero medido e zero por engano são a mesma tela e coisas diferentes.**

O erro agora **volta no lugar da lista**, e quem monta o contexto o mostra:
*«não deu para medir: AttributeError…»*. Silêncio ali seria lido como «não há
pendência nenhuma», que é o engano de origem. Há dois testes: um declara uma
pendência e exige que ela apareça; o outro derruba a tabela e exige que o texto
**diga** que não deu.

---

## O que vai junto da pergunta, e o que não vai

São **80 documentos e mais de 1,1 milhão de caracteres**. Mandá-los em toda
pergunta custaria em toda pergunta, e a API cobra por uso.

| vai sempre | vai quando pedido |
|---|---|
| a versão | o **texto** de um documento, pelo nome do arquivo |
| os relatos, com o `#` de cada um | |
| as pendências declaradas | |
| o **índice** dos documentos — nome, título e a primeira frase | |

O contexto inteiro dá **cerca de 15 mil caracteres**, contra 1.128.671 da
biblioteca. É a regra da fatia, que o mapa já segue com as telas.

O índice leva a primeira frase de cada documento porque um nome de arquivo
sozinho — `ROTEIRO_3.6.29.md` — não diz nada a quem escolhe o que ler.

**E o nome do documento não vira caminho.** `Path(nome).name` descarta qualquer
`..` ou barra: sem isso, um nome vindo da tela leria arquivo de fora da pasta —
e esta função existe justamente para alimentar uma consulta que **sai da casa**.
Há teste que tenta `../CLAUDE.md`, `/etc/passwd` e `app.py`.

---

## A frase que impede a máquina de errar com convicção

O sistema diz **«28 relatos, 28 abertos»**. E vinte e quatro deles estão
consertados.

Os dois estão certos: **`situacao` é o que o oficial marcou na tela**, e nada se
fecha sozinho — é decisão dele, e por isso o conserto entregue continua ABERTO
até ele clicar. Mas uma máquina que receba «28 abertos» sem essa explicação
responde *«você tem 28 problemas em aberto»* com toda a convicção.

Seria o **relato #23 outra vez** — duas vistas do mesmo fato sem o mesmo texto.
Por isso o contexto leva, junto do número:

> «ABERTO» quer dizer que ninguém marcou como resolvido na tela — e não que nada
> foi feito. Nada se fecha sozinho: quem fecha é o oficial.

---

## Onde isso aparece

**Administrativo → Ajuda → O que a ajuda sabe do projeto** (`/ajuda/projeto`).

Ela **só lê, e não gasta consulta**: ver o que a ajuda sabe não pode custar uma
pergunta à API. É a mesma regra da pré-visualização — quem manda dado para fora
tem direito de ver o que está mandando, de graça. E o texto que ela mostra é o
**mesmo** que vai na consulta, pela mesma função: montar aqui uma versão
«parecida» faria a tela mostrar uma coisa e a consulta mandar outra.

E o estado do projeto vai **sempre** quando se pede à ajuda para ler um problema
(`/ajuda/problemas`) — que é a tela onde o oficial relatou isto, e é a pergunta
que mais precisa: ler um defeito sem saber em que versão a casa está, o que já
foi consertado e o que espera decisão é ler no escuro.

---

## O que continua valendo

**A IA auxilia; não decide.** O módulo não tem função que lavre, numere, sele,
cobre, cancele, decida, feche ou julgue — e há teste que varre os nomes
públicos. É a quarta vez que esta regra aparece: usucapião, fraudes, habilitação,
e agora.

**Ele só lê.** Há teste que procura `INSERT`, `UPDATE` e `DELETE` no arquivo. E
esse teste já pegou uma coisa: eu citara a mensagem de erro do SQLite ao pé da
letra num comentário, e ela tem dentro a palavra `update`. **É a lição do
`substr(` outra vez — o varredor lê o texto do arquivo, comentário incluído.**
Descreva em prosa; não cite.
