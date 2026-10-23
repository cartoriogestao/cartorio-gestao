# Protesto — o que o acervo diz, antes de escrever uma linha

**21 de agosto de 2026.** Levantado em `acervo_eoficio.sqlite3`, 229 tabelas, das
quais 30 tocam o protesto. Nada aqui foi suposto: onde eu não sei, está escrito que
não sei.

## O tamanho real

| | |
|---|---|
| Títulos no acervo | **1.370** |
| Protestados | **1.164** |
| Cancelamentos de protesto | **56** |
| Títulos com pagamento | **192** |
| Linhas no Livro de Apontamento | 1.765 (em 10.400 pré-criadas) |
| Encerramentos diários gravados | **426** |
| Período | 17/03/2020 a 13/08/2026 |

## A descoberta que muda o desenho: 93% dos títulos não chegam pelo balcão

| Canal de entrada | Títulos |
|---|---|
| **CRA** (Central de Remessa de Arquivos) | **1.268** |
| **CENPROT** | 91 |
| Manual | **7** |

E **1.359 dos 1.370 são `NATO_DIGITAL`** — nasceram digitais. Só 7 são físicos.

Isto reordena o módulo. Eu ia começar pela tela de apontamento manual, que é como se
aprende protesto no livro. **Sete títulos em seis anos entraram por ali.** O que o
Protesto desta serventia realmente faz é receber remessa eletrônica, apontar em lote,
intimar, protestar ou dar baixa, e devolver o retorno ao CRA. A tela manual continua
existindo — para os sete —, mas não é o eixo.

**1.194 títulos têm chave única do CENPROT.** A integração com a Central não é
opcional: é por onde o dado entra e por onde o retorno sai.

## A geometria dos livros, medida e corrigida

Eu tinha estimado três destes números. Dois estavam errados.

| Livro | Antes (estimado) | **Agora (medido)** | De onde saiu |
|---|---|---|---|
| Apontamento | 10 por folha | **52 por folha, sem verso** | `tbPropProtesto.NAF = 52`; e o E-Ofício pré-criou **10.400** linhas por livro, que é 200 × 52; das 34 folhas escrituradas, 33 têm exatamente 52 |
| Registro de Protestos | 1 por folha, folha nova | **1 por FACE, sem folha nova** | os livros 7 e 8 fecharam com **207 e 219** registros em 200 folhas — impossível com um por folha; de 1.131 folhas, 1.099 têm um registro e 32 têm dois |
| Registro de Pagamentos | 120 por folha, com verso | **120 por folha, sem verso** | Livro 1, ordens 826 a 2145 em 11 folhas = 1.320 registros = exatamente 120 × 11 |
| Protocolo | 50 por face | 50 por face — **continua A CONFERIR** | a origem não declara |

E uma correção de semântica no próprio núcleo: o campo se chamava `por_folha` e o
código que acha o próximo lugar contava por **face**. Num livro que escritura o verso,
os dois diferem pelo dobro. Passou a chamar-se `por_face`, e a contradição agora é
recusada na construção da série.

## O protocolo do protesto reinicia todo dia

`tbProtocoloProtesto` guarda um `intProtocolo_Ultimo` **por data**, com valores de 1 a
6. Não é numeração contínua: o protocolo do protesto é numerado **por dia**.

Isso não é detalhe. Numeração contínua num livro de numeração diária faria o
protocolo de hoje sair como 2.157 em vez de 3. O núcleo passou a ter a marca
`numeracao_diaria`, e a série que a tem **não tem contador para corrigir à mão** — ela
se zera sozinha, e tentar fixá-la é recusado com essa frase.

## O encerramento diário já existe, e tem forma própria

Os 426 encerramentos estão gravados **como linha do próprio Livro de Apontamento**,
com `bitEncerrado = 1` e o texto no campo de observação:

> ENCERRADO NO NUMERO 2155 AS 17:30h. CIDADE EXEMPLO-MA, 12/08/2026. DOU FÉ. OFICIAL
> TITULAR ANTERIOR-TABELIÃO

É essa a redação da casa, e é ela que o sistema novo vai usar — não uma que eu
inventasse. O núcleo já grava o termo em tabela própria (`nu_encerramentos_diarios`),
com a faixa de números do dia, e **encerra também o dia sem movimento**, porque o
silêncio precisa estar escrito.

## Dois livros de apontamento abertos ao mesmo tempo

`tbLivros_Setup` mostra o Livro 1 aberto em **13/07/2020** e o Livro 6 aberto em
**05/03/2024**. O Livro 1 continua recebendo apontamentos até 13/08/2026; o Livro 6
tem **zero** registros e 10.400 linhas em branco.

Ou seja: **um livro foi aberto e nunca usado, e ficou aberto ao lado do que está em
uso.** Dois livros abertos na mesma série é a receita para o mesmo número de ordem
sair em dois lugares. O núcleo agora **recusa** abrir o segundo, com essa frase na
tela. O Livro 6 do acervo vai precisar de decisão sua: encerrar com termo dizendo que
nada foi lançado, ou reaproveitar como o próximo.

## Um selo por etapa, e é assim que tem de ser

`tbAvisoProtesto` tem uma coluna de selo para cada ato da vida do título:

| Etapa | Títulos com selo |
|---|---|
| Apontamento | 245 |
| Intimação | 245 |
| Diligência | 245 |
| Arquivamento | 191 |
| Certidão | 62 |
| Cancelamento | 56 |

E, ao lado de cada uma, o seu próprio emolumento e os seus próprios FERC, MP, DP e
ferrfis. São **190 colunas** numa tabela só.

**Não vou copiar isso.** É o mesmo defeito de `tbRegistroESC`, que tem 84 colunas
porque quem deixa para preencher depois não preenche. No sistema novo: uma linha por
**título**, e uma linha por **ato** — apontamento, intimação, protesto, pagamento,
cancelamento, arquivamento, certidão —, cada ato com o seu selo e as suas custas
vindas do núcleo. O que lá são 190 colunas, aqui são duas tabelas e uma consulta.

## Prazos e espécies

Da configuração real da serventia (`tbPropProtesto`):

| | |
|---|---|
| Prazo de intimação | **3 dias** |
| Prazo do edital | **2 dias** |
| Folhas por livro | 200 |
| Apontamentos por folha | 52 |
| Livro de Apontamento atual | 1 |
| Livro de Protestos atual | 9 |
| Código CRA / CENPROT | 01 |
| Cobra custas de | apontamento, intimação, certidão, arquivamento, diligência |

Espécies de título que realmente aparecem, por volume: **DMI** (duplicata mercantil
por indicação) 911, **CDA** (certidão de dívida ativa) 353, **CBI** 62, **DSI** 16,
**DM** 6, **ATC** 6, **NP** 4, **CTI** 4, **SJ** 3, **FPS** 1.

Duas coisas a notar. Primeiro: **DMI e CDA são 92% do movimento** — a tela tem de ser
boa nessas duas antes de ser completa nas onze. Segundo: **CDA é dívida ativa**, e o
protesto dela usa a certificação do art. 9º-A da Lei 9.430/1996, cujo texto já está
cadastrado na casa e vai vir junto.

## A gratuidade do protesto é texto livre, e isso é um problema

`tbProtestoGratuito` tem seis registros. Os motivos: **"TÍTULO APRESENTADO EM
DUPLICIDADE"** (dois), **"PERMUTA"** (um) e **três em branco**.

Metade dos casos de gratuidade não diz por quê. No sistema novo a gratuidade exige
motivo escrito — e, para o protesto, o item **17.8** da tabela do Tribunal dá a
hipótese normativa: "serão isentos de emolumentos os atos praticados em cumprimento de
mandado judicial expedido em favor da parte beneficiária de assistência judiciária".
Duplicidade e permuta não são isenção legal; são devolução ou erro de apresentação, e
o sistema vai pedir que se diga qual dos dois.

## Motivo de cancelamento: um único cadastro, "Erro Material"

`tbMotivoCancelamentoProtesto` tem **uma** linha: "Erro Material". Os 56 cancelamentos
do acervo saíram todos dela ou de campo livre. O cancelamento de protesto tem hipóteses
distintas na Lei 9.492/1997 — pagamento, ordem judicial, anuência do credor, erro do
apresentante — e tratá-las todas como "erro material" é o que faz o livro não explicar
o que aconteceu. O módulo novo vai ter o catálogo, com o fundamento de cada uma.

## O layout da CRA também estava na sua máquina

Eu tinha escrito, acima, que o formato do arquivo da CRA era a próxima coisa a
procurar. Procurei, e achei — pela terceira vez, a documentação estava no seu próprio
computador:

```
C:\ARPNET\CRA\Remessa\v1_21.xsd
C:\ARPNET\CRA\Remessa\v1_22-apontamento.xsd
C:\ARPNET\CRA\Remessa\v1_22-geral.xsd
C:\ARPNET\C11\serasa\LAYOUT 600 PROTESTO - Novo.PDF
```

Os três primeiros são os **esquemas XML oficiais da CRA/CENPROT**, nas versões 1.21 e
1.22. Deles saíram, com o texto que o próprio esquema documenta:

| Domínio | Códigos |
|---|---|
| Espécies de título | **64** (66 enumerações, duas repetidas) |
| Códigos de irregularidade | **76** |
| Ocorrências | **11** entre as duas versões |
| Tipo de protesto | 2 — Comum e Falimentar |
| Motivo do protesto | 3 — falta de pagamento, de aceite, de devolução |
| Tipo de endosso | 3 — mandato, translativo, sem endosso |
| Tipo de apresentante | 5 — banco, empresa, condomínio, governo, particular |

Estão em `protesto_cra.py`, com 24 testes. O quarto arquivo é outra coisa, também
útil: o **layout SERASA CONCENTRE de 600 posições**, que é o relatório de protestos
mandado à SERASA — não é o mesmo que o da CRA, embora ambos tenham 600 bytes. Fica
anotado para quando chegarmos nele.

Há também **571 arquivos reais** de remessa e retorno na pasta, com registros de 600
bytes e tipos `0` (header), `1` (título) e `9` (trailer), mais quatro de 127 bytes para
desistência. Servem de caso de teste quando o leitor de arquivo for escrito.

### Três divergências entre o esquema e o acervo, e nenhuma foi silenciada

1. **O esquema oficial declara duas espécies em duplicidade**: `SJ` aparece como
   "Sentença Judicial" e "Sentenca Judicial", e `TS` como "Triplicata de Prestação de
   Serviços" e "Triplicata de Prest Servico". Mesmo código, redação diferente. Ficou a
   completa, e a duplicidade está registrada.

2. **O acervo tem duas espécies que o esquema não tem**: `ATC` (6 títulos) e `CTI` (4
   títulos). Dez títulos reais, apontados e protestados. Recusá-los agora perderia o
   acervo; aceitá-los em silêncio mandaria dado inválido para a Central. O módulo
   aceita **com aviso**, e a pergunta fica para a CRA.

3. **O E-Ofício gravou `C` como ocorrência 1.027 vezes** — mais que todas as
   ocorrências oficiais somadas. `C` não existe no contrato da CRA: é código interno do
   programa. Traduzi-lo como se fosse ocorrência oficial mandaria dado inválido. O
   módulo **recusa**, dizendo o que ele é, e o significado precisa ser confirmado antes
   de qualquer migração.

E uma coisa que o cruzamento resolveu: `tbProtestoGratuito` guardava "TÍTULO
APRESENTADO EM DUPLICIDADE" como texto livre. É a **irregularidade 52** do contrato,
com esse nome exato. Deixou de ser texto livre.

## O que eu ainda não sei, e não vou supor

1. **Quantos protocolos cabem por face do Livro de Protocolo.** A origem não declara.
   Precisa de olhada no livro físico.
2. **O que fazer com o Livro 6 de Apontamento**, aberto em 2024 e nunca usado.
3. **`intPrazo = 9000`** em `tbPropProtesto`. Os outros dois prazos são 3 e 2 dias;
   este parece marca de "sem limite", não prazo. Não vou usá-lo até saber.
4. **O que significa a ocorrência `C`** do E-Ofício, usada 1.027 vezes.
5. **Se a serventia ainda envia à SERASA** pelo layout de 600 posições, ou se isso
   parou quando a CENPROT assumiu.

## A ordem em que vou construir

1. As tabelas do título e dos atos, ligadas ao núcleo (livro, folha, ordem, custas).
2. **Apontamento** — em lote pelo CRA e à mão pelos sete.
3. **Intimação** — pessoal, por edital, e a prova da entrega.
4. **Protesto** e **desistência**, com o prazo de 3 dias contado como a lei manda.
5. **Pagamento** e o Livro de Registro de Pagamentos.
6. **Cancelamento**, com o catálogo de hipóteses.
7. **Certidões** — negativa, positiva, de cancelamento — e o Livro de Protocolo com
   encerramento diário.
8. O **retorno ao CRA**, que é o que fecha o ciclo.
