# O Protesto e os arquivos que ele opera — medido em 31/08/2026

Pedido do oficial: *"vamos arrumar o módulo de protesto para que ele opere
todos os arquivos que precisamos… depois de terminar com o protesto maduro e
pronto para uso, empacotar."* Junto veio a pergunta que orientou a passada:
*"Verifique o que vem pela remessa, o que volta pelo andamento, o que vai pelo
retorno. Os últimos atos devem responder tudo que temos de importante."*

Isto é o que se mediu, o que se consertou e o que **não se construiu, e por
quê**.

---

## O que se mediu: os 125 arquivos de 2026

A pasta `8. CRA` do Proton Drive, hidratada antes de medir — os arquivos
chegam como marcador de nuvem e cada leitura força um download.

| Tipo | Sigla | Arquivos | Títulos | Ocorrência |
|---|---|---|---|---|
| remessa (chega) | `BFOSDTTPR` | 26 | 46 | — não tem o campo |
| confirmação (sai) | `SDTBFOCRT` | 29 | 44 | vazia |
| **andamento (sai)** | `SDTBFOAND` | 25 | **103** | **`0` em 103 de 103** |
| **retorno (sai)** | `SDTBFORTP` | 43 | 64 | `C` 45 · `1` 11 · `3` 4 · `A` 2 · `2` 2 |

Um arquivo foi recusado, e corretamente: `DP0010508.261` é desistência, que
tem **127 posições** e mora noutro leitor.

---

## O DEFEITO QUE ISSO ACHOU: o andamento repetia a ocorrência do retorno

`protesto_retorno.py` montava os dois arquivos com **o mesmo código de
ocorrência** — o do ato: `C` no protesto, `1` no pagamento, `3` na desistência,
`A` no cancelamento. A medição diz que o andamento desta casa **sempre mandou
`0`**, nas 103 linhas que temos.

```python
OCORRENCIA_DO_ANDAMENTO = "0"     # medido: 0 em 103 de 103

"ocorrencia": (OCORRENCIA_DO_ANDAMENTO if tipo == "SDTBFOAND"
               else OCORRENCIA_DO_ATO[a["tipo"]]),
```

### E o que torna isto um defeito, e não uma diferença

Dois arquivos com códigos diferentes só é defeito se eles **falarem dos mesmos
títulos**. Se o andamento fosse de outro conjunto, comparar os dois seria
comparar coisas diferentes — e o «conserto» estaria estragando o arquivo.

Medido pelos nossos números:

| | |
|---|---|
| no andamento | 45 |
| no retorno | 47 |
| **nos dois** | **42** |

Os conjuntos são praticamente o mesmo. **A pergunta que separa o defeito da
diferença foi "eles falam das mesmas coisas?", e ela precisou ser feita antes
de mexer numa linha.**

> **A regra do oficial de 24/08/2026 decide aqui**: na dúvida, faça como o
> E-Ofício fazia, ou como um padrão que já foi aceito antes. O `0` do andamento
> é padrão aceito 103 vezes; o código copiado do ato nunca saiu desta casa.

---

## O QUE FALTAVA E FOI CONSTRUÍDO

### 1. As imagens dos títulos — `protesto_imagens.py`

A CRA entrega o título em **duas partes**: o registro de 600 posições, que o
sistema lia desde o começo, e a **imagem do papel**, que vem num `.zip` à
parte. A tela da Central lista as duas pendências lado a lado — *Download
remessa* e *Download imagens* — e o sistema fazia só a primeira.

A imagem não é anexo: **é o título**. O que se protesta é o documento.

O nome do arquivo decodifica em três partes, medido num pacote real:

```
49000005243_00000000191_01.pdf
└ nosso número ┘└ documento ┘└ sequência ┘
```

**A DUPLA CHAVE é o coração do módulo.** A imagem só se prende ao título
quando o **nosso número E o documento do devedor** apontam para o mesmo — e a
razão é medida: o nosso número se repete entre apresentantes (53 grupos e 111
títulos no acervo). Prender pela metade da chave mostraria ao devedor, no
balcão, a dívida de um terceiro.

E a recusa **diz qual das duas partes falhou**, porque o conserto é diferente:
nosso número que não acha é título que não entrou; documento que não bate é
imagem de outra pessoa.

### 2. «A protestar» — o passo da tarde que não tinha tela

Do roteiro dele: *"gerar protesto, sem movimentação, calcular, listar,
gerar."* Era o único passo do dia sem tela nenhuma — o título intimado ficava
esperando alguém lembrar dele, um a um, na lista geral.

**«Sem movimentação» quer dizer sem ato posterior**, e não apenas situação
`INTIMADO`: a consulta olha o `id` do ato, que é a ordem em que foram lavrados.
Perguntar só pela situação deixaria passar o título cujo ato posterior não
mudou o estado.

**O PRAZO NÃO SE CALCULA**, e a decisão é dele, de 24/08/2026. A tela mostra a
data da intimação e quantos dias correram: é **contagem, e não juízo sobre o
tríduo**. Há teste que fica vermelho se alguém escrever `venceu_o_prazo` ou
`pode_protestar` no módulo.

E `dias_desde_a_intimacao` devolve **`None`** quando falta data, nunca zero:
zero diria «foi intimado hoje», que é afirmação, e não saber é outra coisa. A
tela mostra um traço.

**Lavra só os MARCADOS.** Entre «listar» e «gerar» está a decisão, e protesto
não se desfaz: um botão que protestasse a lista inteira faria um clique valer
por vinte atos definitivos. Cada título vai na **sua própria transação** — um
que falha não derruba os outros —, e o lote **não sela e não cobra**, pela
mesma razão da remessa: vinte selos são vinte chamadas de rede de 20 s dentro
de um `BEGIN IMMEDIATE`, com a casa inteira no `busy_timeout`.

---

## O QUE NÃO SE CONSTRUIU, E POR QUÊ

Dois passos do roteiro da tarde ficam de fora, e não por falta de trabalho:

```
*** TARDE: 3) enviar e aprovar arquivos CENPROT (xml);
           4) enviar arquivo de emolumentos.
```

### O arquivo de edital do CENPROT e o de emolumentos

**Não existe um único exemplar de nenhum dos dois em lugar nenhum desta
casa.** Procurado em `C:\ARPNET` inteiro e na pasta `8. CRA`: os arquivos que
há são os quatro da CRA, as desistências, os `.p7s` (instrumentos assinados) e
os `.zip` de imagem. De edital do CENPROT e de emolumentos, nada.

Construí-los seria **inventar formato** — e a regra da casa, que é dele, diz o
contrário: *onde não há padrão anterior, o sistema recusa e pergunta.*

> **Isto é pergunta, e não trabalho pendente.** Trabalho pendente se faz;
> pergunta pendente se pergunta. Com um exemplar de cada — um arquivo que já
> tenha subido e sido aceito —, os dois se medem numa tarde, como o quinto
> layout da desistência foi medido.

### O XML do CENPROT

Este está **medido inteiro** (`CENPROT_XML_MEDIDO.md`, 903 arquivos e 17.270
títulos) e mesmo assim não se gera para título novo: falta a **chave única de
23 dígitos**, cujo verificador não se explica.

Em 31/08 a medição foi refeita mais larga — os **125 arquivos de 2026**, nos
**quatro tipos**, lidos **byte a byte** e não só nos campos que o leitor
conhece:

| | |
|---|---|
| com a chave (`2198765` + 16 dígitos) | **0** |
| com qualquer corrida de 23 dígitos | 21 — todas `00000000000000000000000`, preenchimento |

Do outro lado, para o zero querer dizer alguma coisa: o acervo tem **1.194
chaves preenchidas e 1.163 distintas**.

**A chave não chega por arquivo nenhum da CRA.** Ela vem da plataforma do
CENPROT. O sistema guarda a coluna e nunca a inventa.

---

## O que o Protesto opera hoje, do roteiro inteiro

| Passo do roteiro | |
|---|---|
| download da remessa CRA | ✅ recebe, confere, aponta e confirma |
| **imagens dos títulos** | ✅ **novo** |
| upload da remessa no e-protesto | ✅ o arquivo recebido volta a baixar |
| emitir aviso de intimação | ✅ com a entrega e o edital |
| boleto do aviso | ⚠️ o registro sim; o **código de barras não** — o verificador não se explicou (`AVISO_DE_INTIMACAO_MEDIDO.md`) |
| desistências (manhã, meio-dia e tarde) | ✅ o quinto layout, de 127 posições |
| **gerar protesto — sem movimentação** | ✅ **novo** |
| retorno **e** andamento, em par | ✅ e o par sai por construção, numa rota só |
| arquivos CENPROT (xml) | ⚠️ estrutura medida; falta a chave, que não é desta casa |
| arquivo de edital do CENPROT | ❌ **sem exemplar para medir** — e o caminho que resolveu o de emolumentos serve aqui |
| arquivo de emolumentos | ⚠️ **formato medido em 01/09** — os VALORES é que não se reproduzem |

---

## Duas lições de método desta passada

**A primeira é sobre o zero.** O `except Exception` do meu script de medição
engoliu um `AttributeError` meu — `Arquivo` é dataclass e eu chamei `.get()` —
e **124 dos 125 arquivos apareceram como ilegíveis**. Um defeito meu virou uma
medição com cara de resposta. Trocado por `except PA.ArquivoError`, os 123 que
são de 600 posições leem, e o único recusado é a desistência, que é de outro
leitor. **`except` largo vira zero com cara de medição** — segunda vez neste
projeto.

**A segunda é sobre procurar pelo nome.** A coluna da chave do CENPROT não é
`strChaveUnica`, que foi o que eu escrevi: é **`strChaveUnicaCENPROT`**. Quem a
achou foi varrer as 229 tabelas do acervo atrás do **formato do dado** —
`2198765` mais dezesseis dígitos — em vez do nome que eu imaginava. **Sexta vez
neste projeto**: não achar a coluna que procurei não prova que o dado não
existe; prova que procurei pelo nome errado.
