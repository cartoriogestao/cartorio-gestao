# A carga da CRC: o de-para medido, tag por tag

*29/08/2026 — preparado antes de escrever o módulo, a pedido do oficial:*

> «o cartório está precisando do sistema pronto e amadurecido para o quanto
> antes»

**A fonte é o manual oficial** — *Manual de Carga da Central de Informações do
Registro Civil Nacional — CRC Nacional*, versão 2.6, 79 páginas, da ARPEN-SP,
guardado em `FONTES_EXTERNAS/CRC_manual_carga_webservice_v2.6.pdf`. Nada aqui é
suposto.

---

## O tamanho do que se vai montar

| movimento | tags |
|---|---|
| `<MOVIMENTONASCIMENTOTN>` | **49** |
| `<MOVIMENTOCASAMENTOTC>` | **55** |
| `<MOVIMENTOOBITOTO>` | **78** |

Raiz `<CARGAREGISTROS>`, com `<VERSAO>`, `<ACAO>` e `<CNS>`; dentro, o movimento
da espécie; dentro dele, `<REGISTRO…INCLUSAO>` ou `<REGISTRO…ALTERACAO>`.

**A ordem importa e é imposta pelo manual:** *«deve-se formatar o XML primeiro
com as INCLUSÕES e depois com as ALTERAÇÕES em cada tipo de registro»*.

**Tag em branco não é tag ausente:** *«As tags que não forem enviadas, ou forem
em branco, serão incluídas como nulo ou "Ignorado(a)"»*. Quem omite um campo
está **afirmando que é ignorado**, e não deixando de afirmar — o que muda o que
significa deixar um campo vazio.

---

## O que decide quem pode ir: a MATRÍCULA

`<MATRICULA>` é **obrigatória** (`*` no manual) e são «somente 32 dígitos», com
o dígito verificador do Anexo IV.

**E esse verificador não se gera.** O Anexo IV do manual é uma imagem, e o portal
do SIRC diz que o dígito «é formado automaticamente por meio do **programa que
pode ser baixado gratuitamente**» no site do CNJ. Testado em 244 amostras contra
módulo 11 (quatro conjuntos de pesos, sequencial e paralelo, duas convenções) e
contra o ISO 7064 MOD 97-10 do CNM: **7 acertos em 244** e **0 em 244**. Nível
de acaso.

**Medido no acervo — quem já tem a matrícula de 32 dígitos:**

| espécie | com matrícula | total |
|---|---|---|
| nascimento | **192** | 193 |
| casamento | **20** | 20 |
| óbito | **31** | 31 |

**243 de 244.** O único sem matrícula fica retido, com o motivo escrito, em vez
de sair com um número inventado — porque **declaração aceita com dado inventado
é pior que declaração recusada: a recusada volta**.

---

## Os obrigatórios do nascimento

`VERSAO`, `ACAO`, `CNS`, `INDICEREGISTRO`, `NOMEREGISTRADO`, `MATRICULA`,
`DATAREGISTRO`, `SEXO`.

Os três primeiros são da casa e do arquivo; `INDICEREGISTRO` é o número de ordem
dentro do arquivo — o manual avisa que **pode repetir em outros arquivos**, então
não serve de chave global.

---

## Os vocabulários fechados — e os que eu NÃO tenho

| tag | o manual diz | temos? |
|---|---|---|
| `<SEXO>` | **M=Masculino, F=Feminino, I=Ignorado** | **sim, na letra** |
| `<CORPELE>` | **BRANCA, PRETA, PARDA, AMARELA, INDIGENA, IGNORADA** | **sim, na letra** |
| `<TIPOMORTE>` | «enumeração de tipo de morte (**Natural ou Acidental**)» | **sim — mas ver abaixo** |
| `<ESTADOCIVIL>` | tabela **SDC TB0400 / 34**, «exceto União Estável» | **não** — a tabela não veio |
| `<TIPOLOCALOBITO>` | «Vide valores possíveis no XSD» | **não** |
| `<ELEITOR>` | «Vide valores possíveis no XSD» | **não** |
| `<POSSUIBENS>` | «Vide valores possíveis no XSD» | **não** |
| `<REGIMECASAMENTO>` | «Vide XSD» | **não** |

> ## CORREÇÃO DE 10/09/2026 — O XSD VEIO, E ESTAVA NA CASA
>
> **Tudo o que este documento diz sobre «o XSD não veio» está errado**, e a
> correção fica aqui em cima porque quem lê o resto precisa saber antes.
>
> O manual está em `FONTES_EXTERNAS/CRC_manual_carga_webservice_v2.6.pdf`, com
> o texto extraído ao lado, e ele tem **344 `xs:enumeration`** dentro. Os
> cinco campos que este documento marca como «não temos o valor» estão todos
> lá:
>
> | tag | o que o XSD enumera |
> |---|---|
> | `LOCALNASCIMENTO` | `IGNORADO`, `UNIDADE_SAUDE`, `FORA_UNIDADE_SAUDE` |
> | `POSSUIGEMEOS` | `S`, `N` |
> | `NUMEROGEMEOS` | vazio, e de `1` a `10` |
> | `ESTADOCIVIL` | vazio, `IGNORADO`, `SOLTEIRO`, `CASADO`, `VIUVO`, `DIVORCIADO`, `SEPARADO`, `OUTROS` |
> | `TIPOLOCALOBITO` | vazio, `IGNORADO`, `AMBULANCIA`, `DOMICILIO`, `HOSPITAL`, `OUTRO`, `OUTROS_SERVICOS_SAUDE`, `POSTO_SAUDE`, `SAMU`, `VIA_PUBLICA` |
> | `TIPOMORTE` | vazio, **`NATURAL`, `VIOLENTA`, `IGNORADA`** |
> | `ELEITOR` · `POSSUIBENS` | vazio, `I`, `S`, `N` |
> | `REGIMECASAMENTO` | `COMUNHAO_PARCIAL`, `COMUNHAO_UNIVERSAL`, `PARTICIPACAO_FINAL_AQUESTOS`, `SEPARACAO_BENS`, `SEPARACAO_LEGAL_BENS`, `OUTROS`, `IGNORADO` |
>
> **E A ARMADILHA DO «VIOLENTA» NÃO EXISTIA.** Este documento diz, mais
> abaixo, que «a CRC quer Natural ou Acidental» e que por isso os 4 óbitos
> violentos ficam retidos. **O XSD enumera `VIOLENTA`, com essa palavra.** A
> frase «(Natural ou Acidental)» é real e vem de uma **página de
> recomendações** (pág. 76) — a mesma que manda buscar o estado civil numa
> tabela externa que o XSD tem em casa. **Prosa de recomendação não é schema**,
> e onde os dois divergem quem manda é o que valida o arquivo.
>
> **O DEFEITO DE FUNDO ERA MAIOR QUE OS CINCO: a coluna guarda NÚMERO e o
> vocabulário é de PALAVRA.** A tabela de de-para deste documento aponta
> `LOCALNASCIMENTO` para `ibge_local_nascimento` e `POSSUIGEMEOS` para
> `ibge_gemeo` — e aquelas colunas guardam o **código do IBGE**. Medido na
> produção em 10/09/2026:
>
> | | o que saía | o que sai |
> |---|---|---|
> | `LOCALNASCIMENTO` | o **número** (1, 2, 3, 5) em **212 de 212** — fora da enumeração | `UNIDADE_SAUDE` ×147, `FORA_UNIDADE_SAUDE` ×65 |
> | `POSSUIGEMEOS` | **`S` em 210** — e o código 1 quer dizer «NÃO é gêmeo» | `N` ×210 |
> | `TIPOMORTE` | **nada**, em 31 de 31 | `NATURAL` ×27, `VIOLENTA` ×4 |
> | `TIPOLOCALOBITO` | **nada** | `HOSPITAL` ×17, `OUTRO` ×6, `VIA_PUBLICA` ×5, `DOMICILIO` ×3 |
> | `ESTADOCIVIL` | **nada** | `SOLTEIRO` ×15, `CASADO` ×13, `VIUVO` ×3 |
> | `REGIMECASAMENTO` | **nada** | `COMUNHAO_PARCIAL` ×2 |
>
> **Zero valores fora da enumeração**, conferido registro por registro contra
> o XSD.
>
> **E O DE-PARA DO LOCAL DO NASCIMENTO ESTAVA NO ACERVO**, com esse nome:
> `tbRCPN_LocalNascimento.strWScrc`. É o E-Ofício dizendo o que mandava à
> Central. **Antes de deduzir de-para, procure a coluna que já o tem** — e
> esta regra desta casa nasceu deste mesmo campo.
>
> **A ARMADILHA QUE SOBRA É A DAS DUAS NUMERAÇÕES.** As nove palavras do local
> do óbito estão em `tbRCTO_TipoLocalObito.strDescricaoCRC`, e o **`id`**
> daquela tabela é `1 = Ignorado` e `4 = Hospital`, enquanto o código do IBGE
> — que é o que a coluna guarda — é `1 = hospital` e `4 = via pública`. Usar
> o id como chave poria **«Ignorado» onde é hospital**.
>
> **Quem achou tudo isto foi o oficial mandando verificar UM registro:**
> «verifique o json do Pessoa Exemplo» — assento 1240, nascimento nº 5172 de 1974,
> cujo teor diz com todas as letras «O registrado não é gêmeo».
>
> É «não achar onde eu procurei não prova que não existe» outra vez, e desta
> vez com um documento que esta casa já tinha baixado. **Ler um documento para
> uma pergunta não é tê-lo lido.**

---

**O XSD não veio no manual.** Onde não houver valor medido, o campo sai vazio e
o ato aparece na lista do que falta — em vez de eu escolher por semelhança.
Escolher por semelhança seria assinar por quem preencheu.

### O tipo da morte é uma armadilha, e ela é do vocabulário

A CRC quer **«Natural ou Acidental»**. Esta casa guarda, em `strTipoMorte`:

| valor | quantos |
|---|---|
| Natural | **27** |
| Violenta | **4** |

**«Violenta» não é «Acidental».** Um homicídio é violento e não é acidental; um
suicídio também. Mapear um no outro seria afirmar à Central uma coisa que a casa
não registrou — e a Central aceitaria.

As 27 naturais vão; as 4 violentas ficam retidas com a pergunta, até alguém dizer
qual valor a CRC espera para elas.

> **É o mesmo tipo de erro que o catálogo do óbito do IBGE já ensinou**: lá o
> código `4` é «via pública» no óbito e não existe no nascimento, e usar um pelo
> outro mandaria «outros» onde o IBGE espera a informação que ele mais quer.
> **Vocabulário parecido não é vocabulário igual.**

---

## As validações que passam a ser recusa no balcão

O manual lista as regras que a CRC aplica **depois** de receber. Aplicá-las
**antes** transforma uma rejeição na rede — que chega dias depois, sem o cliente
por perto — numa recusa no balcão, com ele ainda na frente. É o que este projeto
já fez com a participação das partes na DOI.

| regra | na letra do manual |
|---|---|
| **datas do óbito** | nascimento ≤ óbito ≤ lavratura ≤ hoje |
| **pessoa desconhecida** | `FLAGDESCONHECIDO` = S ou N; quando S, os nomes (registrado, pai, mãe) **devem conter o valor "DESCONHECIDO"** |
| **ocupação** | `-1` para «sem profissão remunerada», `-2` para «outras» |
| **benefício do INSS** | dez dígitos, o último um verificador de módulo 11 |
| **caracteres especiais** | `<`, `>`, `&`, `"` e `'` vão escapados |
| **documentos** | só se gravam se `DONO` **e** `TIPO_DOC` estiverem preenchidas |

### Uma correção que o próprio manual precisa

A tabela de caracteres especiais do manual, como ela sai do PDF, está
**invertida**:

> `> (sinal de maior) > = &lt;`   ·   `< (sinal de menor) < = &gt;`

O certo é o contrário — `<` é `&lt;` e `>` é `&gt;`. **Vou usar o escape correto
do XML, e não copiar o erro do manual**: um arquivo com as entidades trocadas
sairia bem formado e com o texto errado, que é o pior dos dois mundos.

---

## O de-para, campo a campo

### Nascimento

| tag da CRC | de onde vem | falta? |
|---|---|---|
| `NOMEREGISTRADO` | `rc_pessoas` papel `REGISTRADO`, ou `rc_assentos.nome` | |
| `CPFREGISTRADO` | `rc_pessoas.documento_numero` quando o tipo é CPF | |
| `MATRICULA` | `rc_assentos.matricula` | **retém quem não tem** |
| `DATAREGISTRO` | `rc_assentos.data_ato` | |
| `DNV` | `rc_assentos.dnv` | medido: 61 de 193 no acervo |
| `DATANASCIMENTO` | `rc_assentos.data_fato` | |
| `HORANASCIMENTO` | `rc_assentos.hora_fato` | **coluna nova, da 3.6.35** |
| `LOCALNASCIMENTO` | `rc_assentos.ibge_local_nascimento` | |
| `SEXO` | `rc_pessoas.sexo` do registrado | |
| `POSSUIGEMEOS` / `NUMEROGEMEOS` | `rc_assentos.ibge_gemeo` | |
| `CODIGOIBGEMUNNASCIMENTO` | `ib_municipios`, pela cidade | os 5.570 já estão carregados |
| `PAISNASCIMENTO` / `NACIONALIDADE` | padrão **M49 da ONU** | **não temos a tabela** |
| `FILIACAONASCIMENTO` (bloco) | `rc_pessoas` papéis `PAI` e `MAE` | |
| ⟶ `IDADE` / `IDADE_DIAS_MESES_ANOS` | `rc_pessoas.idade_no_fato` | **coluna nova, da 3.6.35** |
| ⟶ `CODIGOOCUPACAOSDC` | `rc_pessoas.profissao` | **é texto; a CRC quer o código da CBO** |
| `DOCUMENTOS` (bloco) | `rc_pessoas.documento_*` | `CODIGOORGAOEMISSOR` é do Anexo II, que não veio |

### Casamento

O bloco é **plano**: cada campo existe duas vezes, com sufixo `1` e `2`
(`NOMECONJUGE1`, `NOMECONJUGE2`…). Vêm de `rc_pessoas` papéis `NUBENTE1` e
`NUBENTE2`, e o **nome que cada um passou a usar** é `NOVONOMECONJUGE*`, que sai
de `rc_pessoas.nome_pos` — medido: o segundo cônjuge muda de nome em **17 dos
20** casamentos.

**A filiação dos cônjuges é só nome e sexo** (`NOMEPAICONJUGE1`,
`SEXOPAICONJUGE1`…), e não um bloco — o que confirma, do lado da CRC, a decisão
deste projeto de guardar as quatro filiações do casamento como pessoas.

### Óbito — o maior dos três, com 78 tags

Traz coisas que só ele tem, e todas existem no acervo:

| tag | de onde |
|---|---|
| `NUMDECLARACAOOBITO` | `rc_assentos.numero_do` — **31 de 31** |
| `ELEITOR` | `tbRegistroObito.bitEleitor` — **31 de 31** |
| `POSSUIBENS` | `bitPossuiBens` — **31 de 31** |
| `NUMEROBENEFICIO` | `strBeneficioSocial` — **0 de 31**, e o balcão precisa passar a perguntar |
| `NOMEATESTANTEPRIMARIO` / `CRMATESTANTEPRIMARIO` | `strAtestantePrimario` / `strCRMAtestantePrimario` |
| `CAUSAMORTEANTECEDENTES_A` a `_D` e `OUTRASCOND_A`/`_B` | `strCausaMorte` — **uma coluna só para seis campos** |
| `TIPOLOCALOBITO` | `strTipoLocalObito`, com o de-para de `tbRCTO_TipoLocalObito.strDescricaoCRC` — **e esse de-para está no acervo** |

> **`tbRCTO_TipoLocalObito.strDescricaoCRC` é ouro**: são as **9** descrições que
> a própria CRC usa, guardadas pelo E-Ofício. É o mesmo caso do `intCodigoIBGE`
> do local de nascimento — **antes de deduzir de-para, procure a coluna que já o
> tem**, e desta vez eu procurei primeiro.

**A causa da morte é seis campos na CRC e um no acervo.** Ela vem em
`strCausaMorte` como texto corrido; a CRC quer a cadeia do atestado separada em
antecedentes A, B, C, D e outras condições A e B. **Não se reparte texto corrido
em seis por palpite**: vai no primeiro (`_A`), que é a causa imediata, e os
outros ficam vazios — o que é verdade, e não invenção.

---

## O que fica pendente, e por quê

| o quê | por quê |
|---|---|
| tabela **M49 da ONU** (país e nacionalidade) | não veio no manual; é padrão público e se baixa |
| tabela **CBO** (ocupação) | idem — e o acervo guarda profissão como texto |
| tabela **SDC TB0400 / 34** (estado civil) | citada no manual, não anexada |
| **Anexos I, II e III** (tipos de documento, órgãos emissores, motivos de alteração) | estão no manual, em páginas que ainda não extraí |
| os enumerados do **XSD** | o XSD não veio |
| o valor da CRC para morte **violenta** | «Natural ou Acidental» não cobre |

**Nenhuma dessas impede começar**: o módulo monta o que sabe, deixa vazio o que
não sabe, e lista o ato como incompleto com o nome do que falta — que é o mesmo
desenho da remessa do IBGE e da DOI.
