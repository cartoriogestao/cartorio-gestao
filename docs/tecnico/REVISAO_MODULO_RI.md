# Amadurecimento do módulo de Registro de Imóveis

**Revisão feita em 13/08/2026.** Serventia Extrajudicial do Ofício Único de Cidade Exemplo/MA — CNS 000000.

Este documento não é um plano de obra. É uma lista de achados: o que está errado no que já existe,
o que falta, e o que a norma exige e o sistema ainda não faz. A ordem de execução está na seção 8.

---

## Como conferi

| Fonte | Uso |
|---|---|
| Lei 6.015/1973, na redação da Lei 14.382/2022 | texto oficial do Planalto; itens novos do art. 167 |
| Código de Normas CGJ/TJMA (o PDF que está no Downloads) | Capítulo III do RI, arts. 424 a 773 — é a fonte que mais pesou |
| Provimento CNJ 149/2023 | pelos dispositivos reproduzidos no Código do TJMA |
| Provimentos CNJ 228 e 229, de 16/06/2026 | notícia e resumo; **não li o texto oficial** |
| IN RFB 2.275/2025 (CIB/SINTER) | notícia e resumo; **não li o texto oficial** |
| Os 25 modelos do sistema | executados um a um, com todos os campos preenchidos |

---

## 1. Defeitos no que já existe

Estes vêm antes de qualquer coisa nova. Um ato lavrado com defeito não se apaga.

### 1.1 Colchete dentro de colchete — 13 dos 25 modelos

Usei o colchete para três coisas diferentes: campo a preencher, escolha entre alternativas
e cláusula condicional. Quando uma engole a outra, o resultado sai quebrado.

Rodei o `R-USUCAPIAO` com **todos** os campos preenchidos. Saiu assim:

> Por força de XXX, da XXX, transitada em julgado em XXX / ata notarial e procedimento
> extrajudicial concluído nos termos do art. 216-A da Lei 6.015/73**]**, fica reconhecida...

Duas coisas erradas de uma vez: o colchete de fechamento órfão, e **as duas alternativas
impressas juntas** — sentença judicial e ata notarial no mesmo ato. Isso passaria por um
conferente apressado.

Afetados: `R-PERMUTA`, `R-USUFRUTO`, `R-USUCAPIAO`, `R-ADJUDICACAO`, `R-PARTILHA` (duas vezes),
`R-INTEGRALIZACAO`, `AV-ESTADO-CIVIL`, `AV-CLAUSULAS` (duas vezes), `AV-EXTINCAO-USUFRUTO`,
`AV-CANCELAMENTO`, `AV-ALTERACAO-LOGRADOURO`.

**Correção proposta — três notações distintas:**

| Notação | Significa | Como aparece na tela |
|---|---|---|
| `[CAMPO]` | preencher | caixa de texto |
| `{opção A \| opção B}` | escolher uma | lista suspensa; a não escolhida some do texto |
| `«SE ...: ...»` | cláusula que pode não existir | caixa de marcar; desmarcada, o trecho some |

Hoje, cláusula não usada fica visível como `[SE HOUVER: ...]` e alguém tem de apagar à mão.
Com a caixa de marcar, some inteira ou entra inteira — sem sobra.

### 1.2 Rótulos que ainda saem como frase

Consequência direta do item anterior: mais de 25 campos com rótulo do tipo
*"Se houver torna: houve torna de [valor da torna"*. Some junto com a correção do 1.1.

### 1.3 Fundamentação citada errada

- **`AV-PENHORA`** citava `art. 167, II, 5`, que é alteração de nome e estado civil. **Corrigido.**
  A penhora **é averbada** — o Código do TJMA é expresso no **art. 502** e repete a penhora na
  lista de averbações do **art. 532, "k"**. A Lei 6.015 arrola penhora, arresto e sequestro no
  inciso I do art. 167, que é o inciso de registro, e o CPC (art. 844) fala em averbação: a
  divergência é antiga. O modelo continua **AV** e agora cita as três fontes, para que a nota
  devolutiva e a certidão tenham onde se apoiar. Foram acrescentados dois requisitos do art. 502:
  basta requerimento com cópia do auto ou termo, independentemente de mandado; e havendo causa de
  impenhorabilidade no assento, informar o juízo antes de averbar (§ 3º).
- **`R-TITULO-DOMINIO`** cita `art. 167, I, 26`, que é arrematação e adjudicação em hasta pública.
  Título de domínio é outra coisa: Lei 11.952/2009, Lei 6.383/1976 e Código TJMA, arts. 742 a 746.

Confiro por amostragem os demais e não achei outro erro — mas foi amostragem, não um a um.
Os que confirmei certos: compra e venda (I, 29), permuta (I, 30), doação (I, 33), hipoteca (I, 2),
alienação fiduciária (I, 35), usufruto (I, 7), usucapião (I, 28), arrematação e adjudicação (I, 26),
partilha (I, 25), integralização (I, 32), cláusulas restritivas (II, 11), reserva legal (II, 22),
extinção de ônus (II, 2), logradouro (II, 13).

### 1.4 Requisitos de aquisição derivada aplicados a aquisição originária

`R-USUCAPIAO` e `R-TITULO-DOMINIO` herdam a lista `COMUNS`, que exige **continuidade**
("o transmitente deve ser o titular constante da matrícula") e **disponibilidade**
("a área transmitida não pode exceder a registrada").

Nenhuma das duas cabe. Usucapião é aquisição originária — não há transmitente, e o próprio Código
TJMA (art. 761) prevê o caso de a área usucapida ser **maior** que a matriculada. Título de domínio
é destaque do patrimônio público. Precisa de uma lista própria para os originários.

### 1.5 Texto que não pertence ao ato

- **`R-ALIENACAO-FIDUCIARIA`** traz um parágrafo *"CONSOLIDAÇÃO: a propriedade consolida-se em nome
  do fiduciário na forma do art. 26, após intimação e não purgação da mora"*. É evento futuro e ato
  autônomo. Não se anuncia no registro da garantia. Sai do modelo e vira `AV-CONSOLIDACAO-FIDUCIARIA`.
- **`R-TITULO-DOMINIO`** tem `{{ ' SOB CONDICOES RESOLUTIVAS' }}` no título. Não é condicional coisa
  nenhuma: imprime sempre, mesmo quando o título não tem cláusula resolutiva.

---

## 2. Atos que faltam

Base: art. 167 da Lei 6.015/73 (inclusive os itens acrescidos pela Lei 14.382/2022) e as listas
próprias do Código TJMA — **art. 496** (registros além do art. 167) e **art. 532** (averbações além
do art. 167). Essas duas listas estaduais são o que mais falta no sistema hoje.

### Grupo A — rotina de uma serventia rural do Maranhão

| Ato | Base |
|---|---|
| Promessa de compra e venda, cessão e rescisão | LRP 167, I, 9 e 20; II, 16 |
| Servidão | LRP 167, I, 6 |
| Cessão de direitos hereditários e de direitos aquisitivos | CC 1.793; TJMA 803-805 |
| Dação em pagamento | CC 356 |
| Bem de família | TJMA 497 |
| Locação com cláusula de vigência + averbação de preferência + caução locatícia | TJMA 499; Lei 8.245 art. 38 § 1º |
| Consolidação da propriedade fiduciária e leilão | Lei 9.514, 26-27; TJMA 716-728-A |
| Cancelamento de indisponibilidade e de penhora | TJMA 503 e ss. |
| União estável | TJMA 532, "i" |
| Ação real ou reipersecutória; averbação premonitória | TJMA 496, "c"; CPC 828 |
| Demolição e reconstrução | LRP 167, II, 4 |
| Decreto de utilidade pública e desapropriação | TJMA 532, "m"; 533, II |
| Retificação (registro do resultado) | LRP 212 e 213 |
| Legitimação fundiária e legitimação de posse | LRP 167, I, 41 e 44; Lei 13.465/2017 |
| Concessão de direito real de uso e CUEM | LRP 167, I, 37 e 40 |
| Arrendamento rural por estrangeiro | TJMA 625-629; Lei 5.709 |
| Comodato | TJMA 532, "n"; 533, III |
| Tombamento definitivo e processo de tombamento | LRP 167, I, 46 e II, 36 — **novos** |
| Pagamento por serviços ambientais | LRP 167, I, 45 — **novo** |

### Grupo B — previstos, aparecem de vez em quando

Superfície; laje; enfiteuse e anticrese; uso e habitação; condomínio de lotes; condomínio urbano
simples; multipropriedade; transformação, fusão, cisão e incorporação de sociedade (TJMA 496, "d");
pacto antenupcial (TJMA 534); alteração de regime de bens; cessão de crédito com garantia real e
sub-rogação de dívida (LRP 167, II, 21 e 30 — **novos**); caução e cessão fiduciária de direitos
reais (LRP 167, II, 8 — **novo**); descaracterização de imóvel rural, que ainda obriga a comunicar
ao INCRA (TJMA 561, parágrafo único); arrecadação de bens vagos; cédulas de crédito à exportação e
comercial (TJMA 496, I e III — vão para o Livro 3).

### Grupo C — raros aqui, mas normados

Incorporação imobiliária, instituição de condomínio, convenção de condomínio, habite-se parcial,
subcondomínio, loteamento e desmembramento urbanos (Lei 6.766/79; TJMA 560-586 e 630-702).

---

## 3. Procedimentos que faltam

Estes não se resolvem com um modelo de texto. São fluxos com prazo, notificação e decisão.

| Procedimento | Base | O que o sistema teria de controlar |
|---|---|---|
| Retificação administrativa | LRP 212-213; TJMA 587-605 | requerimento, planta e ART, notificação de confrontantes, prazo de impugnação, decisão |
| Usucapião extrajudicial | LRP 216-A; TJMA 747-761 | ata notarial, anuências, notificações, edital, prazos, decisão do oficial |
| Adjudicação compulsória extrajudicial | LRP 216-B; TJMA 703-715 | **decisão fundamentada do oficial** — hoje o sistema não tem esse tipo de peça |
| Consolidação da propriedade fiduciária | Lei 9.514, 26-27; TJMA 716-728-A | intimação (inclusive pela Central de Intimações do ONR), prazo de purgação, dois leilões |
| Dúvida | LRP 198-204; TJMA 46-54 | ver observação abaixo |
| Extremação | TJMA 729-736 | localização e estremação de parcela |
| Regularização fundiária rural | TJMA 737-746 e 138-A | além do registro, **inserir os dados no SAEC do ONR** |

**Observação sobre a dúvida — é um defeito de contagem, não só um modelo faltando.**
O Código TJMA, art. 48, IV, diz que *a prenotação fica suspensa durante a tramitação da dúvida*.
O sistema hoje conta 20 dias úteis corridos desde a prenotação, sem saber suspender. Numa dúvida
que demore, ele vai declarar vencida uma prenotação que está viva. Vale corrigir mesmo antes de
existir tela de dúvida.

---

## 4. Livros que faltam

O art. 424 do Código TJMA lista seis livros. O sistema tem quatro.

- **Livro 3 — Registro Auxiliar.** É onde entram as cédulas de crédito (TJMA 762-773), o penhor,
  a convenção de condomínio e o tombamento. Cédula de crédito rural em Cidade Exemplo é rotina, não
  exceção. Sem o Livro 3 não há onde registrar — e a certidão do Livro 3 é expressamente prevista
  no art. 547. O CNM já reserva o dígito 3 para ele.
- **Livro de Cadastro de Aquisições de Imóveis Rurais por Estrangeiros** (TJMA 424, VI; Lei 5.709,
  art. 10). Sem ele não há como montar o relatório trimestral da seção 6.

---

## 4-A. CTP — Comunicação de Transações às Prefeituras *(construída em 13/08/2026)*

Faltava na lista da seção 6 e é a obrigação mais concreta do conjunto: comunicar ao Município
as transações imobiliárias (Lei 8.935/1994, art. 30, XI), pelo módulo **CTP da CENSEC**, por
força do **Provimento CNJ 174/2024**. Carga mensal.

Foi construída uma aba própria no módulo de RI, com:

- competência mensal, com a lista de **todos** os atos do mês — inclusive os que não entram,
  com o motivo ao lado, porque ato que some da tela é ato que ninguém confere;
- operação imobiliária sugerida pelo modelo usado na lavratura; quando o ato não tem modelo,
  deduzida do texto da natureza, e a tela **avisa que foi dedução**;
- os campos que a matrícula não tem — valor do negócio, base do ITBI/ITCMD, forma de pagamento,
  data do negócio, percentual transacionado — digitados ali e guardados fora do teor do ato;
- conferência por ato, em português: *"imóvel rural sem código do INCRA"*, não *"campo nulo"*;
- geração do JSON, com fechamento da competência guardando o **SHA-256** do arquivo transmitido;
- **fechamento negativo** — «sem transações no mês». É exatamente o que a correição cobrou no
  caso do DOI: mês sem ato também precisa de comprovante.

Layout conforme a especificação do CNB-CF, versão 1.3 de 24/10/2025, que segue o Manual da DOI
v1.1 de 30/04/2025.

**Duas ressalvas, e são importantes.** Primeira: a tabela de domínio publicada traz um único
tipo de serviço — *Notarial* — e dois tipos de ato — *Escritura* e *Procuração*. O documento
fala em "três tipos de serviço" e tem campos claramente registrais (CNM, transcrição, data de
lavratura/registro/averbação), mas **os códigos registrais não estão publicados**. O arquivo sai
com o padrão notarial, configurável, e isso precisa ser conferido com a CENSEC antes da primeira
remessa. Segunda: o sistema gera o arquivo, **não transmite** — envio por API exigiria credencial.

**O acervo não entra retroativamente.** Os 1.241 atos herdados do E-Ofício vieram sem natureza do
título (1.241 de 1.241), com todas as 3.986 partes gravadas como "proprietário" — sem separar quem
transmitiu de quem adquiriu — e sem valor de negócio. A CTP vale dos atos lavrados daqui em diante;
para incluir um ato antigo é preciso completar os dados à mão. A tela diz isso quando o ato é do
acervo, para a pendência não parecer defeito do sistema.

---

## 5. CNM — o campo existe, mas ninguém o gera

`ri_matriculas.cnm` está no banco e recebeu o que veio do E-Ofício. O sistema **não gera e não
valida** — e o art. 428, IV, do Código TJMA exige o CNM na ficha.

Formato (Provimento CNJ 143/2023): **`CCCCCC.L.NNNNNNN-DD`**, 16 dígitos — CNS com 6, livro com 1
(2 ou 3), número de ordem com 7, e 2 dígitos verificadores por módulo 97 base 10.

Com CNS `000000` e Livro 2, dá para gerar as 1.699 matrículas de uma vez e, de quebra, conferir as
que já vieram preenchidas. É das poucas coisas desta lista que é trabalho de uma tarde.

---

## 6. Centrais e obrigações periódicas

| Obrigação | Quando | Base | Hoje |
|---|---|---|---|
| Consulta à CNIB **do transmitente e do adquirente**, com registro eletrônico da consulta | antes de cada alienação ou oneração | TJMA 506 | cópia local congelada em 19/03/2023, e a consulta não fica registrada |
| Indisponibilidade: **uma averbação por proprietário atingido** | a cada ordem | TJMA 504, p.ú. | o modelo não separa |
| Dados de regularização fundiária no SAEC/ONR | a cada procedimento | TJMA 138-A | não faz |
| Coordenadas no SIG-RI; análise do mosaico **antes** do ato | retificação, loteamento, desmembramento, desdobro, destaque, unificação | TJMA 441 | não faz |
| IERI-e — inventário estatístico | conforme ONR | TJMA 427-A | não faz |
| Modificações em imóveis rurais → INCRA | **mensal** | TJMA 434 § 4, "a" | não faz |
| Aquisição por estrangeiro → INCRA, Corregedoria (NOTARIUM) e MAPA, **mesmo sem transmissão** | **trimestral** | TJMA 621 e 624 | não faz |
| Arrendamento rural a estrangeiro → Corregedoria e INCRA | **trimestral** | TJMA 629 | não faz |
| DOI → Receita Federal | mensal | TJMA 434 § 4, "c" | não faz |
| DOITU → SPU | mensal | TJMA 434 § 4, "d" | não faz |
| SISCOAF | conforme o caso | TJMA 434 § 4, "h" | não faz |
| Relação atualizada de ações reais e reipersecutórias | permanente | TJMA 434 § 4, "g" | não faz |
| **CTP → CENSEC → municípios** | **mensal** | Lei 8.935/94, art. 30, XI; Prov. CNJ 174/2024 | **feito — aba própria, ver seção 4-A** |
| Certificação diária do horário de encerramento do protocolo | diária | TJMA 425 § 2 | não faz |
| Certidão de inteiro teor digital em **2 horas** | por pedido | TJMA 547 | emite, mas não controla o prazo |
| Cópia de segurança fora da serventia + **teste de restauração semestral com relatório** | semestral | TJMA 161 | o backup existe; o relatório de teste, não |

Isso não é hipótese. O `inspection_seed.py` do próprio sistema já carrega pendências de **DOI/AUDITUS**
e **SISCOAF** apontadas em correição, com prazo. O módulo de RI é justamente quem tem os dados para
produzir essas remessas — e hoje não produz nenhuma.

---

## 7. O que mudou em 2026 e ainda não está no sistema

**Provimento CNJ 228, de 16/06/2026 — extrato eletrônico.** Representação estruturada e padronizada
dos dados do título, recebida obrigatoriamente pelo SERP, em sistema do ONR. Implantação gradual em
até três anos, começando por financiamento imobiliário, SFH, Minha Casa Minha Vida, SFI e cédulas de
crédito e do agronegócio. O emitente responde civil e criminalmente pela fidelidade do extrato.

Vale reparar na coincidência: o extrato eletrônico é exatamente o que alimentaria o preenchimento
guiado que acabamos de construir. Em vez de digitar 9 campos, o extrato chega e preenche — e o
registrador confere em vez de datilografar. É a peça que faltava para aquilo fazer sentido pleno.

**Provimento CNJ 229, de 16/06/2026** — regulamenta o ecossistema do SERP e institui a marca
"Meu Registro". Implantação por etapas de homologação e projeto-piloto.

**IN RFB 2.275/2025 — CIB e SINTER.** Compartilhamento estruturado e eletrônico dos dados de cada
operação imobiliária, **imediatamente após a prática do ato**. Capitais e DF desde janeiro de 2026;
**demais municípios a partir de janeiro de 2027**. Descumprimento é comunicado ao CNJ.

Cidade Exemplo entra em **janeiro de 2027 — cinco meses**. É o prazo mais curto de toda esta lista.

---

## 8. Ordem sugerida

1. **Corrigir os colchetes dos 13 modelos.** É o único item onde o sistema pode produzir um ato
   defeituoso hoje. *(A citação do `AV-PENHORA` já foi corrigida; falta a do `R-TITULO-DOMINIO`.)*
2. **Gerar e validar o CNM.** Barato, obrigatório, e resolve as 1.699 de uma vez.
   *(O algoritmo já está no sistema e foi conferido: gera exatamente os 1.656 CNMs que vieram
   preenchidos do E-Ofício, 1.656 de 1.656. Falta a tela que aplica nas que estão em branco.)*
3. **Suspensão da prenotação na dúvida** e **registro eletrônico da consulta à CNIB.** Dois defeitos
   pequenos com consequência grande em correição.
4. **Atos do Grupo A.** Vinte modelos, mesma estrutura dos 25 que já existem.
5. **Livro 3 e livro de estrangeiros.** Mexe no esquema; melhor antes de o acervo crescer.
6. **Retificação administrativa e consolidação fiduciária.** Os dois procedimentos mais pedidos.
7. **Remessas periódicas** — começando por INCRA mensal e estrangeiros trimestral, que são as que
   vencem sozinhas, e pela exportação SINTER, que tem data marcada.
8. **Extrato eletrônico**, quando o ONR publicar o formato.

---

## 9. O que eu não conferi

- **Não li o texto oficial** dos Provimentos CNJ 228 e 229/2026 nem da IN RFB 2.275/2025 — só
  notícias e resumos. Antes de programar qualquer coisa com base neles, é preciso ler a íntegra.
- Não li o Provimento CNJ 149/2023 artigo por artigo; usei o Código do TJMA, que o reproduz nos
  pontos que importam aqui.
- Os números de item do art. 167 nos modelos foram conferidos **por amostragem**, não um a um.
- **Nenhuma integração real foi testada** — ONR, SERP, SINTER, CNIB, CENSEC ao vivo. Não temos
  credenciais, e tudo o que está escrito aqui sobre esses sistemas é norma e especificação
  publicada, não experiência com a interface deles. Vale em dobro para a CTP: o arquivo obedece
  ao layout publicado, mas nunca foi aceito por uma CENSEC de verdade.

---

## 10. Um achado de dados, à margem

Existe no acervo um ato com **data de 06/11/2026** — três meses no futuro. Veio assim do E-Ofício.
Não quebra nada, mas aparece na CTP de novembro como se fosse ato do mês, e vai aparecer em
qualquer relatório por período. Vale conferir contra o livro na hora da conferência daquela
matrícula.
