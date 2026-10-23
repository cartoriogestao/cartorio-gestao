# O SIRC medido no manual oficial

*29/08/2026 — preparado antes de escrever o módulo.*

**A fonte** é o manual *SIRC – Recomendações Técnicas*, 121 páginas, da Dataprev,
guardado em `FONTES_EXTERNAS/SIRC_manual_recomendacoes_tecnicas.pdf`. Nada aqui é
suposto.

---

## O envio automático existe, e são três caminhos

| caminho | endereço | o que exige |
|---|---|---|
| SIRC Web | `https://sirc.dataprev.gov.br` | navegador; o operador sobe o arquivo |
| **Web Service com senha** | `https://sirc.dataprev.gov.br/SircWs/Movimento` | usuário e senha (WSDL em `?wsdl`) |
| **Web Service com certificado** | `.../SircWs/MovimentoCertificadoDigital` | **certificado A3 da ICP-Brasil** |

No caminho por web service **não há geração de arquivo**: o sistema monta o XML e
chama o serviço, e ele **devolve a crítica registro a registro** em XML.

**O certificado A3 é o ponto que exige decisão do oficial**: A3 quer dizer cartão
ou token físico, e um serviço que rode sozinho no servidor precisaria dele
espetado na máquina.

---

## As restrições do arquivo, e elas mudam o desenho

| | |
|---|---|
| formato | **XML**, válido contra o XSD da Dataprev |
| codificação | **UTF-8** |
| tamanho | no máximo **1024 KB** |
| registros | no máximo **250 por arquivo** |
| compactação | **GZIP** |
| intervalo entre envios | no mínimo **1 minuto** |

**O teto de 250 registros e o intervalo de um minuto decidem a forma do módulo:**
uma remessa grande **se parte em lotes**, e o envio não pode ser um laço apertado.
Não é detalhe de transporte — é regra do arquivo, e um módulo que a ignore
produz remessa que a Dataprev recusa inteira.

---

## A diferença que separa o SIRC da CRC, e ela é grande

| | campo não informado |
|---|---|
| **CRC** | tag em branco **já significa** «nulo ou Ignorado(a)» |
| **SIRC** | é preciso **marcar explicitamente** «ignorado» — e o marcador **não pode** estar presente quando o campo está preenchido |

> «Campo Ignorado: Quando um campo não estiver informado, o **marcador de campo
> ignorado deve ser informado**. Analogamente, o marcador de campo ignorado **não
> pode estar informado quando houver preenchimento do campo**.»

**Os dois envelopes não são o mesmo**, e é por isso que o desenho é **uma
montagem só do fato e dois formatadores** — e não uma montagem que sirva aos
dois. Uma montagem única acertaria um e erraria o outro exatamente onde o dado
falta, que é onde eles discordam.

---

## O SIRC tem anotação, averbação e retificação — com data e texto

E isso liga direto no módulo de anotações que esta casa acabou de construir:

| ato | regra de data | texto |
|---|---|---|
| **anotação** | ≥ data do registro civil, ≤ hoje | `dadosComplementares`, **10 a 1.000 caracteres** |
| **averbação** | ≥ data do registro, ≤ hoje; data do motivo ≤ data da averbação; data da sentença ≤ data da averbação | idem |
| **retificação** | ≥ data do registro | idem |

É a **divisão tripartite** que `rc_assento` já modela desde o começo, e que a
inspeção de 12/08/2026 cobrava — o SIRC a espera do mesmo jeito.

---

## O cancelamento de termo, e a estrutura da matrícula outra vez

> «Motivo: **no mínimo 15 e no máximo 350 caracteres**. Tipo de Registro Civil:
> NASCIMENTO, CASAMENTO ou OBITO. **Identificador da Serventia: 5 Dígitos + 1 DV
> calculado com algoritmo módulo 10** (conforme disponibilizado pelo CNJ).
> Acervo: 2 Dígitos. Tipo de Serviço: 2 Dígitos, **constante 55**. Número Termo:
> 7 Dígitos. Tipo Livro: 1. Ano do Registro: 4. Número Folha: 3. Número Livro:
> 5.»

**Isso confirma, campo por campo, a estrutura da matrícula de 32 dígitos que
este projeto já tinha medido** — e acrescenta uma peça nova.

### O dígito verificador do CNS é módulo 10, e ele fecha

O manual diz que o identificador da serventia é **5 dígitos mais um verificador
por módulo 10**. O CNS desta casa é **000000**: base `00000`, dígito `7`.

**O módulo 10 devolve 7.**

Duas fontes independentes concordando — o manual afirma a regra, o CNS da casa a
confirma. É o mesmo padrão que fechou o cabeçalho do IBGE (o código de Cidade Exemplo ser `2198765` = `21` + `07001`).

> **E isto não resolve a matrícula inteira.** O verificador dos **dois últimos**
> dígitos continua sem explicação — testado em 244 amostras contra tudo o que é
> padrão, com resultado de acaso, e o CNJ distribui um programa em vez de
> publicar o algoritmo. O que se ganhou foi **conferir o CNS**, que é um pedaço.

---

## As regras de negócio que viram recusa no balcão

| regra | na letra |
|---|---|
| **endereço** | «Deve ser preenchido **somente um** dos endereços»: o nacional **ou** o estrangeiro |
| **filiação** | quando não ignorada, **no mínimo o nome e o sexo**. Idade, data de nascimento, profissão, naturalidade e documentos **não podem ser informados sem nome e sexo** |
| **casamento** | proclamas < registro; celebração ≤ registro; registro ≤ hoje |
| **regime** | enumeração: **Comunhão Parcial; Comunhão Universal; Participação Final nos Aquestos**… |

> **A regra da filiação é a mesma invariante que este projeto já descobriu
> sozinho**, medindo o acervo: os 42 assentos com a mãe no lugar do pai foram
> achados porque *um assento tem um pai e uma mãe*, e o par decide. O SIRC exige
> nome **e** sexo pelo mesmo motivo — sem os dois, a filiação não identifica
> ninguém.

E **o regime de casamento o SIRC enumera**, enquanto a CRC manda ver no XSD que
não veio. **Onde uma central cala e a outra fala, vale a que fala** — mas com
cuidado: são vocabulários de sistemas diferentes, e só se pode usar um pelo outro
depois de conferir. Fica como pergunta, e não como de-para.

---

## O que ainda falta, e não impede começar

| o quê | por quê |
|---|---|
| o **XSD** da Dataprev | o manual o cita e não o traz; é ele que fecha os enumerados |
| a tabela **CBO-CNIS** (profissões) | citada como anexo |
| a tabela **TB0400 – Pequenas Tabelas** | onde mora o estado civil |
| o **usuário e a senha** do SIRC | são da serventia, e o oficial os tem |
| o **certificado A3** | decisão do oficial — token físico na máquina |

**Nada disso impede montar o arquivo**: o módulo monta o que sabe, marca como
ignorado o que não sabe — que é justamente o que este manual manda fazer —, e
lista o ato como incompleto com o nome do que falta.
