# O acervo não vira atraso — o ensaio de 30/08/2026

> **A carga do acervo já rodou no servidor**, e este documento nasceu de medir
> isso: os módulos novos, rodados contra a produção, mostraram setenta anos de
> livro como trabalho atrasado de hoje.

## Primeiro: a carga rodou, e o `CLAUDE.md` dizia que não

Medido no banco do servidor em 30/08/2026, **só leitura**:

| | |
|---|---|
| `rc_assentos` · `rc_pessoas` · `rc_atos` | **244** · **1.084** · **244** |
| `pt_titulos` | **1.366** |
| `rg_registros` · `ra_registros` | **72** · **14** |
| `sd_selos` | **26.134** |
| `nu_implantacao` | **9** pendências declaradas |

Até esta data o `CLAUDE.md` dizia *«A CARGA DO ACERVO AINDA NÃO RODOU»*, com os
números de 27/08 — todos em zero. **Lista de pendência que envelhece faz planejar
trabalho já feito**, e é o «carimbo que mente» aplicado ao roteiro.

Quem desmentiu foi o **ensaio**, e não a releitura.

## O defeito que ele achou, e eram três módulos

`sirc_remessa.pendentes_de_remessa` devolveu **243 registros, o mais antigo de
12/10/1955** — numa tela que diz **«o prazo é de 1 dia útil»**. Aquele nascimento
apareceria com vinte e cinco mil dias de atraso, numa lista que o balcão não teria
como zerar.

E não era um módulo:

| lista | mostrava | e é |
|---|---|---|
| **SIRC** | 243, desde **12/10/1955** | tela de um dia útil |
| **Comunicações mensais** | 8 meses × 5 destinos = **40** desde **março de 2009** | a comunicação era devida em 2009 |
| **Termos a escrever** | **244** | e nenhum é trabalho |

**O registro daqueles assentos aconteceu há décadas. O que aconteceu agora foi a
DIGITAÇÃO** — e digitar hoje não faz nascer obrigação de hoje.

## E eu tinha escrito a precaução, no mesmo dia, no módulo irmão

`ibge_geracao.a_prestar` já dizia: *«só conta o que este sistema lavrou — os
assentos que vieram do acervo o E-Ofício já entregou, e dizer o contrário seria
acusar setenta anos de livro»*.

Escrevi isso pela manhã e **não pus no SIRC nem nas comunicações**. Os 35 testes
de mesa do SIRC passavam — porque no teste o assento entra do jeito certo, e a
produção não é assim. É a lição do ensaio contra o acervo pela quinta vez.

## Por isso não consertei três módulos: escrevi o varredor

`tests/test_o_acervo_nao_vira_atraso.py` semeia um banco com **o acervo em
miniatura** — um nascimento de 1955, um óbito de 2009, um nascimento indígena de
2022 e um parto múltiplo de 1990, todos `origem = EOFICIO` — e mais nada. Depois
pergunta a cada lista de pendência quantas ela vê.

**Quem contar o acervo como atraso fica vermelho.**

E ele exige que **toda lista nova se declare**: varre `rc_*.py` procurando a
**forma** — função pública chamada `pendentes…`, `a_prestar` ou `meses_sem_…` — e
recusa qualquer uma que não esteja na tabela, com o motivo escrito.

> **Ele se provou na primeira vez que rodou**: achou **cinco listas** que eu não
> tinha visto olhando módulo a módulo.

### O seed tem de alcançar a lista

Sem o nascimento indígena, `rc_funai` devolveria zero **por não ter o que ver**, e
o teste passaria dizendo o contrário do que quer dizer. **Seed que não alcança a
lista não prova nada sobre ela** — foi preciso alargá-lo para os quatro casos.

## As listas que contam o acervo de propósito, e por quê

| lista | por que conta |
|---|---|
| **carga da CRC** | ela é *justamente* a subida do acervo histórico à Central (`ACAO_CARGA = "CARGA"`) — excluí-lo apagaria a razão de existir |
| **mutirão do art. 347** | o artigo alcança **exatamente** os assentos anteriores a 14/11/2017; excluí-los deixaria a lista sempre vazia |
| **termos a escrever** | eles ficam sem termo de propósito, e a tela explica — mas a **conta** passou a separar |
| **FUNAI** | o RANI é **o documento da pessoa**, e não uma remessa estatística: se não foi feito, a criança segue sem ele, e o tempo não apaga isso |
| **gêmeos** | a ordem de nascimento é **requisito do assento** (art. 233, III), e a falta é real mesmo em 1990 — mas ali o caminho é a **retificação** (art. 352, I), e não editar o campo |

E duas ficam de fora **por construção, e não por filtro**: as **anotações** e as
**comunicações declaradas** nascem quando o oficial ou o ato as declara, e a carga
não declara nada.

> **Exceção sem motivo escrito é exceção que alguém copia** para o módulo
> seguinte sem saber por quê — e aí o defeito volta pela porta que a exceção
> abriu.

## Mesmo número, duas telas, sentidos opostos

O SIRC e a CRC devolviam **os mesmos 243**. Num era defeito; no outro é o
esperado. **Consertar os dois do mesmo jeito seria o reflexo certo pelo motivo
errado.**

O que a tela da CRC ganhou foi a frase que diz isso, para o número grande não
parecer atraso — e ela aponta para a do SIRC, explicando a diferença.

## E a conta dos termos passou a dizer o que a tela já dizia

`quantos_termos_faltam` separa: **244 sem termo, 244 do acervo, 0 a escrever de
verdade**. A tela explicava em palavras desde 29/08; **número que parece trabalho
e não é faz planejar o que não existe** — é o «carimbo que mente» aplicado a um
contador.

## Como ficou, na produção

| | antes | depois |
|---|---|---|
| SIRC a remeter | 243 | **0** |
| meses com óbito a comunicar | 8 | **0** |
| termos a escrever | 244 | **0** (de 244 sem termo) |
| CRC a carregar | 243 | **243** — e está certo |

## Os números

| | |
|---|---|
| `tests/test_o_acervo_nao_vira_atraso.py` | **13** testes, e onze listas declaradas |
| módulos corrigidos | `sirc_remessa`, `rc_comunicacoes`, `rc_termo` |
| telas corrigidas | remessa do SIRC · carga da CRC · termos a escrever |
