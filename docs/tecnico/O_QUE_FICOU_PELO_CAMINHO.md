# O que começou e não terminou — construído em 30/08/2026

> «Sobre os expedientes, eles seriam de **abastecimento automático**, pegariam
> todos atos que começaram e não terminaram no sistema (…) Criar módulo para
> gerenciar a melhor aplicação disso, para **moldar o que fica, o que sai, como
> melhora**.» — o oficial, relato #24

É a construção do que foi desenhado em `DESENHO_INACABADOS_E_RETIFICACAO.md`,
com o desenho mantido: **a lista é uma lente, e não uma segunda gaveta.**

## A decisão de fundo, e por que ela é a mais importante

A tentação era criar uma linha de expediente para cada ato inacabado. **Não.**

O ato já é o registro. Uma linha ao lado dele seriam **dois lugares guardando o
mesmo fato** — e este projeto já sabe como isso termina: a `normalizar_nome`
copiada, o `VERSAO.txt` que dizia 3.2.1, a documentação em duas pastas, os
modelos em duas telas. **A cópia diverge no primeiro conserto**, e aqui
divergiria de um jeito caro: o ato seria concluído e o expediente continuaria
aberto — que é *exatamente* o relato #24.

Então a lista sai das tabelas onde os atos já moram, **medida na hora**. **Ato
concluído sai dela sozinho**, porque a lista é a pergunta e não a resposta
guardada. Há teste que conclui uma tarefa e confere que ela sumiu.

## As nove fontes

Cada uma diz quatro coisas, e nenhuma é invenção — as colunas foram lidas do
esquema, uma a uma:

| fonte | atribuição | sai da lista | parado depois de |
|---|---|---|---|
| Escritura em lavratura | Notas | quando é lavrada | 7 dias |
| Prenotação sem ato | RI | quando o ato se amarra a ela | 10 dias |
| Rascunho de ato do RI | RI | quando o ato é lavrado | 7 dias |
| Atendimento do balcão em aberto | Administrativo | ENTREGUE ou CANCELADO | 30 dias |
| Usucapião em andamento | RI | quando é registrado | 30 dias |
| Retificação de área | RI | quando é averbada | 30 dias |
| Habilitação de casamento | RCPN | quando o casamento é celebrado | 30 dias |
| Expediente sem encerrar | Administrativo | RESPONDIDO ou ARQUIVADO | 15 dias |
| Tarefa em aberto | Administrativo | quando é concluída | 15 dias |

**Nenhuma delas é nova.** Todas já existiam como tabela e como tela; o que não
existia era **o lugar onde elas aparecem juntas**. Antes, para saber o que a casa
devia, eram nove telas.

### Os prazos padrão não são todos iguais, e cada um tem razão

- **A prenotação tem 10 dias** porque o prazo dela é de 20 dias úteis (40 no
  REURB-S): quem olha a lista precisa ver o título **antes** de o prazo vencer.
- **O balcão tem 30** porque os **640 abertos** são todos do E-Ofício e nenhum
  tem um único item. Com 7 dias esta fonte gritaria 640 vezes no primeiro dia — e
  alarme que soa sempre é alarme que ninguém ouve.
- **A habilitação tem 30** porque ela vale 90 dias (CC art. 1.532), e celebrar
  com ela vencida é celebrar sem habilitação.
- **Usucapião e retificação têm 30** porque são ritos de meses.

## A tela que molda — «o que fica, o que sai»

Liga, desliga e muda os dias, por fonte. **Isso mora no banco** (`ex_fontes`),
para o oficial ajustar num sábado sem programador.

**Mas a fonte em si mora no código**, e é deliberado: saber onde o ato mora e o
que o termina não se digita numa tela. A tela liga e desliga o que existe; ela
não inventa fonte. É a mesma divisão de `aj_config` — *quem pode usar a ajuda*
mora no banco, *como a ajuda funciona* mora no código.

**Nada se perde:** sem linha em `ex_fontes` a fonte funciona com o padrão do
código, e «voltar ao padrão» é apagar a linha. Instalação nova nasce funcionando
— a regra de `mo_modelos`.

## Os dois guardas que valem mais que os outros testes

**1. Toda fonte tem consulta que roda.** O teste executa a consulta de cada uma
contra o esquema de verdade. Sem ele, uma fonte com nome de coluna errado só
apareceria como **lista vazia** — e ninguém repara em item que deixou de
aparecer.

Não é hipótese: no dia anterior escrevi `a.folha` em `rc_funai`, pedindo de
`rc_assentos` uma coluna que mora em `rc_atos`.

**2. Toda fonte leva a uma tela que existe, com o parâmetro certo.** **Duas das
nove estavam erradas** quando as escrevi — `ri_protocolo` não recebe parâmetro
(o certo é `ri_protocolo_ver`) e `ri_matricula` não existe (é `ri_rascunho_ver`).
O link quebrado só apareceria quando alguém clicasse.

E o teste de tela vai além: **monta a página inteira com item de verdade em cada
uma das nove fontes**. Se um `url_for` não fechar, o Jinja estoura ali.

### O `id` da fonte tem de servir à tela dela

O rascunho do RI é o caso: a linha mora em `ri_rascunhos`, mas a tela para onde
ela leva é a da **matrícula**. Devolver o `id` da linha do rascunho produziria um
link que abre **a ficha de outro imóvel** — e ninguém desconfia de uma ficha que
abre.

## Três coisas que a construção achou

**O `or` teria religado o que o oficial desligou.**
`ajuste.get("ligada") or padrão` devolve o padrão quando o valor é `0` — porque
zero é falso. É o mesmo `str(v or "")` que comia o zero na remessa do SIRC, com
outro custo: lá a quantidade virava «não sei»; aqui a fonte **desligada voltaria
a gritar**. `is None` resolve, e há teste.

**O varredor bateu na minha própria prosa SQL, pela quarta vez.** O teste que
prova que o módulo só escreve nas duas tabelas dele usava
`UPDATE\s+(\w+)` — e isso casa com `DO UPDATE SET`, do `ON CONFLICT`. Ele acusou
o módulo de escrever numa tabela chamada **«SET»**. *Varredor procura a forma, e
nunca a palavra solta que também cabe noutra frase.*

**Palavra genérica não serve de marca num HTML inteiro.** Um teste procurava
«algo» para provar que a anotação tinha sido apagada — e a própria janela da
ajuda escreve «como fazer **algo** no sistema». O teste falhava com o código
certo; e teria passado com o código errado se a palavra fosse comum dos dois
lados.

## O que ele não faz

- **Não conclui nada.** Mostra e leva à tela do ato — concluir é lá, com as
  regras de lá. Há teste que varre os nomes públicos procurando `concluir`,
  `encerrar`, `finalizar`, `arquivar` e `lavrar`. *Quarta vez que esta regra
  aparece: usucapião, fraudes, habilitação, e agora.*
- **Não cria expediente.** Ver acima.
- **Não escreve fora das duas tabelas dele.** Há teste que junta toda escrita do
  módulo e exige que sejam só `ex_fontes` e `ex_anotacoes`.
- **Fonte que não responde não vira lista vazia**: ela volta com o motivo, como
  no painel das comunicações. Uma tabela renomeada faria a lista encolher em
  silêncio.

## O único dado novo

`ex_anotacoes` — quem está cuidando, até quando, o que falta. É o único que não
existe em lugar nenhum; todo o resto é medido.

Ela **não tem chave estrangeira**, de propósito: aponta para nove tabelas
diferentes, e uma FK só pode apontar para uma. Quem garante que a tabela é válida
é `anotar()`, que recusa nome fora de `FONTES`.

E **apagar a anotação não tira o item da lista** — quem o tira é a conclusão do
ato, na tela dele. Se sumisse, a lista viraria gaveta, que é exatamente o que ela
não é.

## Os números

| | |
|---|---|
| `inacabados.py` | as nove fontes, a configuração e a anotação |
| `ex_schema.py` | `ex_fontes` e `ex_anotacoes` — duas tabelas, nenhuma guarda ato |
| `tests/test_inacabados.py` | **28** testes |
| `tests/test_inacabados_tela.py` | **21** testes |
| telas | `/inacabados` (*O que ficou pelo caminho*) e `/inacabados/anotar/…` |

**Ajustar é do ADMIN e do gerente**; **ver é de todos** — quem precisa da lista é
quem trabalha, e quem muda a regra não pode ser o balcão inteiro.
