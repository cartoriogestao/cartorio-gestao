# Problema #75 — a certidão da matrícula, e o molde que faltava

**Relato do oficial, 16/09/2026 às 20h18, versão 3.6.137, na tela da matrícula
(`ri_ficha`, `/registro-imoveis/5377`):**

> «não faz sentido ter opção de emitir certidão negativa de matrícula dentro da
> tela da matrícula»
>
> «tirar a opção de certidão negativa de matrícula e estruturar um modelo base,
> considerando os modelos de outras certidões do cartório, para os demais
> modelos de certidão»

São dois pedidos, e o segundo é o que dá trabalho. O primeiro é uma opção que
sai; o segundo é a **forma** das certidões do Registro de Imóveis, que até aqui
era um texto só com quatro `{% if %}` dentro.

---

## 1. Por que ele tem razão, e não é só gosto

O texto da «certidão negativa de matrícula» dizia, com todas as letras:

> «**NADA CONSTA** em nome do requerente nos livros de Registro de Imóveis desta
> Serventia, até a presente data.»

**Isso não certifica esta matrícula.** Certifica uma busca pelo **nome da
pessoa** em **todos** os livros — que é outra pergunta, de outra tela (e que
esta casa não emite por aqui). A prova de que as duas coisas são diferentes
está no lugar onde ela mora: um campo `NEGATIVA` num seletor cujo rótulo é o
**tipo de certidão daquela matrícula**, ao lado de «inteiro teor» e «ônus».
Quem escolhesse a terceira opção receberia um papel sobre o nome do requerente
e não sobre o imóvel que estava lendo na tela.

**E o E-Ofício concorda com ele, medido no acervo.** O catálogo de modelos de
certidão do sistema antigo (`tbCertidoes`) tem **11** entradas — **8** do
Registro de Imóveis (`intAtribuicao = 5`), **2** do Registro Civil das Pessoas
Naturais (1ª e 2ª via) e **1** do RCPJ, uma certidão de ATA —, e as oito do RI
são:

| id | modelo | texto |
|---|---|---|
| 1 | Certidão de Inteiro Teor | **821.289 caracteres** |
| 2 | Certidão de Inteiro Teor com ônus | **zero** |
| 6 | Certidão Dominial Vintenária | zero |
| 7 | Certidão de Penhor Bovino | zero |
| 8 | Certidão de Ônus Completa | zero |
| 9 | Certidão Dominial Trintenária | zero |
| 10 | Certidão Dominial Quinzenária | zero |
| 11 | Certidão Trintenária | zero |

**Nenhuma das onze tem «negativa» no nome** — medido: `strDescricao LIKE
'%negativ%'` devolve **zero**. As duas do civil são «1ª via» e «2ª via» de
nascimento/óbito/casamento, e a do RCPJ é uma certidão de **ata**: nenhuma é
negativa. As negativas que esta casa emite são as do **Protesto**, e moram em
outra tabela (`tbProtesto_Certidao`, com o texto em `protesto_certidao.py`). O RI
nunca teve uma.

**E não é a `tbRI_Modelo_RA` que diz isso.** Quem for conferir a tabela de
modelos *do RI* encontra **duas linhas** — «Modelo Registro» e «Modelo
Averbação» —, cada uma com 820 bytes de cabeçalho RTF e **texto nenhum**. É o
registro que a documentação do projeto já trazia. O catálogo de **certidões** é
o `tbCertidoes`; o de **atos** é o `tbRI_Modelo_RA`. Duas tabelas, dois
assuntos, e este parágrafo existe para quem for verificar não procurar no lugar
errado.

**E o que a casa emitiu, medido na produção em 18/09/2026:**

| | |
|---|---|
| certidões do RI em `ri_certidoes` | **375**, e **375 são de inteiro teor** |
| selos no caminho `/selo/imovel/certidao` | **670** |
| matrículas | **1.985** |

A opção saiu **sem custo nenhum de história**: nenhuma certidão negativa de
matrícula foi emitida, e não há papel no acervo para converter. **Os 670 selos
não entram nessa conta, e é honesto dizer por quê**: o razão guarda o caminho e
o texto do selo, e **não guarda qual tipo de certidão cada um serviu** — é o
mesmo motivo que faz a procedência do código do item ser `TABELA`, e não
`MEDIDO`, em `ato_selado.py`. Quem tivesse dúvida sobre este ponto não a
resolve por ali.

As duas outras — ônus e propriedade — continuam na tela e **nunca foram usadas**
(zero das 375); elas ficam porque a tabela de emolumentos as nomeia (o item
`16.24.4` é «certidões de inteiro teor, **ônus** e de ações reais e pessoais
reipersecutórias e de cadeia dominial»).

---

## 2. O que o segundo pedido queria dizer, e como ficou

Até 18/09/2026 a certidão do RI era **um texto só**, com quatro tipos dentro:

```
{% if tipo_certidao == "INTEIRO_TEOR" %} ...
{% elif tipo_certidao == "ONUS" %} ...
{% elif tipo_certidao == "PROPRIEDADE" %} ...
{% elif tipo_certidao == "NEGATIVA" %} ... {% endif %}
```

Quem abria Administrativo → Modelos via o papel dos quatro **misturado**. Mexer
no que é comum a todos — a abertura («neles encontrei a MATRÍCULA Nº …»), a
finalidade, a validade de 30 dias do art. 53, quem assina — exigia mexer
também no que é de um tipo só, e um erro ali estragava as outras três.

Agora são **um molde e um miolo por tipo**:

| papel do catálogo | o que é |
|---|---|
| `RI_CERTIDAO` | **o molde**: o que TODA certidão tem, nos dois desenhos que a casa já usa (o do inteiro teor, que traz o cabeçalho da ficha, e o dos outros, que abre com o timbre). Carrega `{{ miolo_do_tipo }}` |
| `RI_CERTIDAO_INTEIRO_TEOR` | o teor da ficha e os atos que não estão escritos nela, fechados por «Era o que nela continha.» |
| `RI_CERTIDAO_ONUS` | os atos restritivos, ou o «NADA CONSTA» |
| `RI_CERTIDAO_PROPRIEDADE` | quem é o dono hoje |

**Os quatro são editáveis na mesma tela** — o molde e os três miolos são papéis
do catálogo da casa, como já eram a ficha, o cabeçalho e a nota devolutiva.

### A emenda é uma só, e ela é declarada

`MARCADOR_DO_MIOLO = "{{ miolo_do_tipo }}"`, e o molde **tem de** carregá-lo.
Sem ele a certidão sairia afirmando «cujo inteiro teor segue:» e **não
reproduzindo nada** — o carimbo que mente na sua forma mais cara, num papel que
a serventia assina (é o mesmo defeito do relato #79, do dia anterior).

Por isso a conferência acontece **duas vezes**: na tela que grava (onde há tempo
de consertar) e na emissão (onde quem lê o erro está com o cliente na frente).
É a mesma função (`modelos_da_casa.conferir_marcadores`) nos dois lados —
conferir com uma régua e emitir com outra é como a tela passa a aprovar o que o
papel não sabe montar.

### O miolo é renderizado ANTES de entrar no molde

Se ele fosse colado no molde e renderizado junto, o `{{ }}` que o **teor da
ficha** tiver — e o teor do acervo tem chave de tudo quanto é jeito — seria lido
como marcador do Jinja, e o papel sairia com o texto do livro interpretado como
modelo. Renderizado antes, o que entra no molde é **papel**, e não modelo. Há
teste com teor que traz `{{ }}` de propósito.

---

## 3. A garantia de que o papel não mudou

O risco desta passada era o de sempre: mexer na forma e **mudar o papel que sai**
sem ninguém ver. A medição compara o `ri_odt.py` do **pacote 3.6.147** — o
`.cgu` que estava nesta máquina quando a passada começou, extraído para
`tmp/_pkg147/`, e **não** reconstruído de memória — com o da árvore,
renderizando os **três tipos** em **cinco fichas de ensaio** (com ônus, sem
ônus, sem teor, sem proprietário, e sem requerente nem finalidade): **15
comparações**, e em todas elas o arquivo que vira PDF sai **byte a byte igual**.

> **A régua já foi outra, e as duas concordam.** A primeira medição usou o
> `MODELO_CERTIDAO_PADRAO` da **3.6.139**, e é o mesmo texto: conferido, **4.983
> caracteres nos dois**. O script que faz a comparação é
> `tmp/_75_o_papel_nao_mudou.py`, e ele imprime **«O PAPEL NAO MUDOU»** quando
> as 15 batem.

Na ficha cheia, os três tipos dão, nos dois lados:

| tipo | caracteres de papel |
|---|---|
| `INTEIRO_TEOR` | **1.350** |
| `ONUS` | **2.050** |
| `PROPRIEDADE` | **1.899** |

**A única diferença é sempre a mesma, é pequena, e é de HTML.** Onde o miolo
acaba e o molde continua, o texto antigo tinha `</p>\n\n\n<p>` e o novo tem
`</p>\n<p>` — **duas quebras de linha cruas, entre tags**, no `ONUS` e no
`PROPRIEDADE` (o `INTEIRO_TEOR` sai idêntico nos dois). E o que importa: **não é
`<p></p>`** — o parágrafo vazio é o que a casa sabe que vira linha em branco no
papel, e é ele que sumiria sem aviso (foi o achado do `A_LINHA_EM_BRANCO_QUE_SUMIA.md`).
Aqui não há parágrafo vazio nenhum: são só linhas em branco *entre* as tags, e a
conversão para ODF as despreza — conferido, porque o papel saiu igual nas 15.

---

## 4. Os testes

`tests/test_relato_75_a_certidao_da_matricula.py` é o arquivo desta passada, e
ele mede as três coisas que podem se perder sozinhas:

| o que ele guarda | por quê |
|---|---|
| a tela **não oferece** `NEGATIVA`, e oferece exatamente `ri_schema.TIPOS_CERTIDAO` | quem escolhe é o `<option>` do molde, e não a lista do Python: tirar de um lugar só deixaria o outro servindo |
| `ri_odt.MIOLO_DA_CERTIDAO`, `ato_selado.CODIGO_DA_CERTIDAO_DO_RI` e `ri_schema.TIPOS_CERTIDAO` são **o mesmo conjunto** | tipo sem miolo sai com a abertura e sem o teor; chave a mais no mapa do selo é caminho aberto para o próximo código pedir texto de uma certidão que a casa não emite |
| o molde carrega `MARCADOR_DO_MIOLO` e **só ele** | os outros papéis (ficha, nota, cabeçalho) não têm miolo e não podem passar a exigir um |
| cada um dos três tipos emite os pedaços da **mesma** certidão: o texto do tipo **e** a abertura, a validade e a assinatura | olhar só o miolo não distingue «acertou» de «quebrou o molde» |
| o `{{ }}` do teor **não** é interpretado | é o defeito que o desenho existe para evitar |
| gravar um molde sem o marcador é **recusado**, e emitir com ele faltando também | as duas metades da emenda |
| o conferidor do modelo funciona **mesmo sem matrícula nenhuma** | instalação nova: ele devolve `None` («não tinha com que conferir»), e não um erro que não existe |
| a palavra `NEGATIVA` não voltou a nenhum dos módulos do RI | ela é legítima em `ato_selado` (`pt_certidoes`, do Protesto) e em `rg_titulo` (qualificação do RCPJ/RTD) — e o teste declara as duas exceções em vez de varrer a árvore inteira |

**E os testes de casa que falavam dos quatro tipos foram ajustados** — não para
ficarem verdes, mas porque o contrato mudou de verdade, e um teste que afirma o
contrato antigo é pior que teste nenhum:

- `tests/test_relatos_42_43_cnpj_e_selo_da_certidao.py` — a lista dos tipos que
  selam passou a ser **comparada** com `ri_schema.TIPOS_CERTIDAO`, em vez de
  escrita à mão com o `NEGATIVA` dentro;
- `tests/test_relato_76_protocolo_da_certidao.py` — emite `ONUS` no lugar de
  `NEGATIVA` (o teste é sobre o protocolo, não sobre o tipo);
- `tests/test_relato_79_teor_na_certidao.py` — a guarda do teor mudou de
  endereço junto com o teor: agora ela mora no miolo, e o teste lê o miolo
  **pelo catálogo**, que é como a emissão o lê;
- `tests/test_modelos_da_casa.py` e `tests/test_modelos_elementos.py` — a
  contagem dos papéis: o catálogo passou de 30 para **34** e o submódulo do RI
  de 6 papéis para **9**.

---

## 5. A conferência desta passada — 18/09/2026

**A rodada que vale correu na árvore de verdade — não numa cópia —, porque a
árvore ficou quieta na janela da medição: os dez arquivos desta passada deram
151 aprovados, zero falhando, em 2m49s.**

> **E a cópia existe por uma razão medida, não por precaução.** Há mais de uma
> passada escrevendo esta árvore, e o próprio `conftest.py` recusa o resultado
> quando a árvore muda durante a medição («ARVORE ALTERADA DURANTE A SUITE»). O
> resultado de quem mede a árvore que está sendo editada não é de nada — foi o
> que invalidou a primeira tentativa desta passada.

**Antes da rodada definitiva houve uma em cópia, e ela fica declarada porque foi
ela que apurou as cinco vermelhas que a árvore não tem** — o lote da certidão
deu 82 aprovados, e o dos modelos e das telas, 141 com 5 vermelhas:

| a vermelha | o que a apuração achou |
|---|---|
| 3 em `test_ajuda_projeto.py` | **eram da cópia, e não do código.** Sem o `CLAUDE.md` no lugar, a ajuda não acha o material escrito — e é exatamente isso que os três testes cobram. Repostas na cópia **com o arquivo no lugar (ele viaja no pacote, e mora fora da pasta do programa)**: **as três passam**, e na árvore de verdade elas nunca ficaram vermelhas. É a mesma família do `conferir_biblioteca()`: ausência com cara de medição |
| 2 em `test_portabilidade.py` | **declaradas, e não são minhas.** Os seis arquivos acusados — `mats_meta.py`, `verify_fix_final.py`, `arquivar_stubs.py`, `invest_digi_fast.py`, `scan_digi_trocas.py` e `scan_imagens_troca.py` — são **byte a byte os do pacote 3.6.147**, conferido por sha256, e nenhum deles é tocado pelo #75. São rascunho de raiz da outra passada |

**E o `ruff` foi comparado com a régua do `.cgu`, e não com a memória:** **85**
achados na árvore e **85** no pacote 3.6.147, com o **mesmo conjunto de
(arquivo, regra)** — nenhuma regra nova, e nenhuma a mais. Módulo novo entra
limpo; aqui não entrou módulo novo, e o que se mexeu não piorou.

---

## 6. O que espera decisão do oficial

**As outras sete certidões do E-Ofício não foram construídas, e não por
esquecimento: elas não têm texto.** Medido acima — do catálogo de oito modelos do
RI, **sete estão com zero caractere** no `memTexto`, e o único com texto é a de
inteiro teor (821.289 caracteres de RTF).

**Mas «sem texto no modelo» NÃO quer dizer «nunca usada», e esta distinção é o
que faz a pergunta mudar de forma.** O `tbRI_Certidao.intModeloCertidao` diz por
qual modelo cada certidão saiu, e as **370** que o E-Ofício emitiu se repartem
assim:

| modelo | certidões |
|---|---|
| 1 — Certidão de Inteiro Teor | **340** |
| 8 — Certidão de Ônus Completa | **14** |
| 2 — Certidão de Inteiro Teor com ônus | **12** |
| 6, 9, 10, 11 — as quatro dominiais/trintenárias | **1 cada**, todas de 2020 |
| 7 — Certidão de Penhor Bovino | **0** |

Ou seja: **seis daquelas sete saíram sem modelo escrito** — o texto foi digitado
em cada uma, ou o modelo não veio na carga —, e **com que texto eu não sei**.
Só o **penhor bovino** nunca saiu.

Escrever a prosa delas agora seria **inventar prosa registral** — e este projeto
já tem a regra: não se inventa o que não se mediu. O que a passada fez foi abrir a
porta: **acrescentar uma delas é acrescentar um miolo e uma linha no mapa**, sem
tocar no molde, sem mexer nas outras, e com a conferência e os testes já cobrindo
o caminho.

**A pergunta é qual delas esta casa emite, e com que texto.** As candidatas
naturais são as que já saíram — a **ônus completa** (14 vezes) e a **inteiro teor
com ônus** (12) —, e as **dominiais** também têm apoio na tabela de emolumentos:
o item `16.24.4` nomeia «certidões de inteiro teor, **ônus** e de ações reais e
pessoais reipersecutórias e de **cadeia dominial**». O que não tem nem uso nem
nome na tabela é a **trintenária** (modelo 11) e o **penhor bovino** (modelo 7,
que nunca saiu). Enquanto ele não disser, todas ficam como estão: **no acervo, e
não no menu**.
