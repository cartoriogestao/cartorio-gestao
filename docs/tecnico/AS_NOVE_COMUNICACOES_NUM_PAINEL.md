# As nove comunicações num painel — e a FUNAI, que não tinha nenhum

*29/08/2026*

> **Seis linhas, nove destinos, cinco prazos.** De um dia útil a trimestral.

## Por que um painel, e não seis telas

Elas já têm as suas telas — e é justamente esse o problema. Quem chega de manhã
não vai abrir seis telas para saber se alguma venceu. Abriria **a que
lembrasse** — e a que se esquece é justamente **a que não tem trabalho para
lembrá-la**: a declaração de mês sem movimento do SIRC, a relação da Junta
Militar num mês em que não morreu ninguém.

O painel (`/rcpn/comunicacoes-painel`, *O que comunicar hoje*) **não faz
comunicação nenhuma**. Ele pergunta a cada módulo quantas estão esperando e
mostra as seis lado a lado, na ordem do **aperto** — e não na ordem em que os
módulos foram escritos. Onde há trabalho, a linha leva à tela que o faz.

## O nove é somado, e não escrito

| linha | destinos | prazo |
|---|---|---|
| SIRC / INSS (art. 225) | 1 | **1 dia útil** |
| FUNAI (art. 253, § 2º) | 1 | **imediatamente** |
| CRC Nacional (arts. 243 e 367) | 1 | 5 dias |
| art. 226 — juiz eleitoral, Economia, Receita, Identificação MA | **4** | 5º dia útil |
| Junta de Serviço Militar (Lei 4.375/1964) | 1 | mensal |
| IBGE (art. 224) | 1 | dia 8 de jan/abr/jul/out |
| | **9** | |

`quantos_destinos()` soma. **O número nove não está escrito em lugar nenhum do
módulo** — escrevê-lo à mão faria o painel dizer «nove» no dia em que virassem
dez. É o defeito do menu, e o do carimbo de versão que mentia.

**E a soma me corrigiu na hora de escrevê-la**: o cabeçalho que eu tinha
redigido dizia «sete linhas», e são **seis**. Foi a função que respondeu, e não
a minha contagem — pela terceira vez neste projeto: *dado cru não é resposta; a
resposta é o que a função devolve*.

## A carga e a anotação são uma linha só

O art. 367 manda anotar «preferencialmente pela CRC» e o art. 243 manda que toda
comunicação entre serventias vá por ela. **Duas linhas dariam a impressão de dois
destinos, e é um só.** A linha da CRC leva aos dois lugares — a carga e as
anotações devidas.

## O IBGE não se mede por contagem, e isso é buraco declarado

As outras cinco contam o que espera porque **cada ato pendente é uma linha**. A
do IBGE é um mapa **trimestral**, e saber se ele já foi mandado exige guardar o
que saiu — coisa que este sistema **não guarda**.

Dali poderia sair uma contagem dos atos do trimestre, que teria cara de medição e
responderia **outra pergunta**. Em vez disso a linha mostra o **prazo**, e diz,
com todas as letras, que o envio não é acompanhado. **Número que responde à
pergunta errada é pior que número nenhum**, e buraco calado vira «o sistema já
cuida disso».

### E o trimestre que vence não é o trimestre que se reporta

O dia 8 de **outubro** entrega **julho, agosto e setembro**; o de janeiro entrega
outubro a dezembro **do ano anterior**. Rotular o vencimento com o trimestre em
que ele cai poria o arquivo com o período errado — numa obrigação que tem **multa
de 1 a 5 salários mínimos, «sem prejuízo da ação penal»**. A primeira versão da
função fazia exatamente isso; está consertada, com teste para os quatro
trimestres.

## Zero medido e zero por engano — e o painel já se provou

Quando um módulo não sabe responder, a linha diz **«não deu para medir»** e
mostra o motivo. Nunca zero. É a lição de `ajuda_projeto`, onde um
`except Exception: return []` transformou uma função inexistente em «zero
pendências» quando eram nove.

**E ele se provou no primeiro dia.** Minha consulta da FUNAI pedia `a.folha` de
`rc_assentos` — coluna que não existe, porque **livro e folha moram no ATO**, e
não no assento. O painel não disse «nenhum nascimento esperando»: disse
*«rc_funai.quantas_pendentes não respondeu: no such column: a.folha»*. Um
`except` largo teria escondido isso atrás de um zero tranquilo.

---

# A FUNAI — art. 253, § 2º

> «O oficial deverá comunicar **imediatamente** à FUNAI o assento de nascimento
> do indígena, para as providências necessárias ao **registro administrativo**.»

## É o único prazo da casa sem número

Os outros oito têm número — um dia útil, cinco dias, dia 8. Este diz
«imediatamente», e **prazo sem número é prazo que ninguém sente vencer**.

O módulo conta **os dias corridos desde o assento** e mostra o número: não para
afirmar um vencimento que a norma não deu, mas para que «imediatamente» deixe de
ser palavra. A partir de cinco dias a linha fica vermelha — e a tela diz, ali
mesmo, que **esse número é da casa e não da norma**.

**Corridos, e não úteis.** Os prazos em dias úteis desta casa são assim porque o
artigo **qualifica**; o art. 253, § 2º não qualifica nada. Contar em dias úteis
emprestaria a esta obrigação uma folga que a norma não deu.

## Não é estatística: é o papel de alguém

A comunicação existe para o **RANI** — o registro administrativo de nascimento
de indígena, o documento com que a pessoa se apresenta à FUNAI a vida inteira.

Medido no acervo: **4 nascimentos** declarados indígenas, e **três são de 2026**
(julho, julho e agosto). Todos com sobrenome Krikati.

## A etnia não se tira do sobrenome

Nos quatro casos o sobrenome é «KRIKATI», e o § 1º **até permite** que o povo
seja lançado como sobrenome — **a pedido do declarante**. Permite, não obriga.

Uma regra que lesse a etnia do nome acertaria os quatro casos desta casa e
erraria o primeiro que chegasse sem ele; ou tiraria de um sobrenome comum uma
etnia que não é. **E o acervo não tem coluna de etnia nem de aldeia.** As duas
são **perguntadas** na tela; vindo vazias, o ofício sai com o lugar marcado —
`[COMPLETAR: a etnia, que o sistema não deduz]`.

Vazio é melhor que inventado: o papel afirma a origem de uma criança a um órgão
federal.

## A lista é do que o sistema sabe

`strRacaCor` está **em branco em 178 dos 193** nascimentos do acervo. Os quatro
só aparecem porque alguém preencheu o campo — de modo que esta lista é do que o
sistema **sabe**, e não necessariamente de tudo o que aconteceu. A tela vazia diz
isso, em vez de deixar o operador achar que não houve nenhum.

## A comparação da cor é sem acento

O acervo guarda «Indigena», sem acento, e o balcão vai digitar «Indígena».
`UPPER` do SQLite é ASCII e não resolveria — é a armadilha que deixou o CNIB sem
achar ninguém por nome, e a busca do Protesto antes dela. A consulta traz os
nascimentos e quem decide é `e_indigena`, em Python.

## Aviso sem saída é aviso que fica para sempre

Há o botão *«Já comuniquei»*, com o canal e o protocolo — e é ele que tira o
nascimento da lista. **O teor congela**, com sha256: é o papel que a serventia
afirma ter mandado, e numa correição é ele que se mostra.

Dispensar exige **motivo escrito**, e o que se escreveu **fica**. Dispensar é
decisão do oficial; ignorar não é.

## Dois defeitos que os testes de tela acharam

1. **A consulta pedia `a.folha` de `rc_assentos`** — coluna que não existe.
   Livro e folha moram no **ato**. Agora o ofício usa
   `rc_certidao.lugar_do_assento`, a **mesma função** da certidão: duas consultas
   para a mesma pergunta divergem no primeiro conserto, e a que ficasse velha
   poria o ofício a citar folha errada.
2. **O formulário que refaz o ofício manda por GET, e a rota só lia
   `request.form`.** O que o operador digitasse sumiria — a tela continuaria
   dizendo «falta preencher a etnia» depois de ele a ter preenchido. O teste de
   domínio passava, porque ele chama `montar` direto com os valores na mão.
   **Décimo primeiro caso neste projeto em que a diferença entre testar o módulo
   e testar a tela importou.**

## Os números

| | |
|---|---|
| `rc_obrigacoes.py` | o painel — só lê, e não comunica nada |
| `rc_funai.py` | a comunicação, com tabela própria `rc_funai` |
| `tests/test_rc_obrigacoes.py` | **17** testes |
| `tests/test_rc_funai.py` | **29** testes |
| `tests/test_rc_funai_tela.py` | **22** testes das duas telas |
| telas | `/rcpn/comunicacoes-painel` e `/rcpn/funai` |

## Por que `rc_funai` é tabela própria

`rc_comunicacoes` tem `UNIQUE(destino, competencia)`, porque as comunicações do
art. 226 são **mensais** — uma por mês por destino. Esta é **por assento**, e o
prazo é «imediatamente». Enfiá-la lá faria duas crianças nascidas no mesmo mês
caberem numa linha só, e **a segunda sumiria calada no `UNIQUE`**.

## O que ainda falta

- **acompanhar o envio ao IBGE** — o mapa se gera e o sistema não guarda o que
  saiu. É o buraco que o painel declara.
- **o endereço da FUNAI** e por onde a comunicação sai (malote, e-mail, ofício
  em mão) — pergunta do oficial, e não trava o que foi construído.
