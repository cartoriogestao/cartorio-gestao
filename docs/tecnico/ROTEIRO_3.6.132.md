# ROTEIRO 3.6.132 — o ato do RI de ponta a ponta, e o carimbo do selo

**Data:** 15/09/2026 · **Versão:** 3.6.132 (projeto) · **Servidor:** 3.6.129

> **ESTE ROTEIRO EXISTE PORQUE O TRABALHO FOI INTERROMPIDO NO MEIO**, por ordem
> do oficial: *«pare, salve o que avancamos, faca um relatorio para continuar
> depois»*. Ele diz o que está **feito e medido**, o que está **na produção**, o
> que **parou** e o que **fazer a seguir** — nessa ordem, porque é a ordem em
> que quem retoma precisa das coisas.

---

## 1. O PEDIDO, nas palavras dele

Em sequência, no mesmo dia:

1. *«tres atos devem ficar em pe, quero revisar no sistema e poder lavrar
   efeitivamente (selando) depois»*
2. *«faca o reabir matricula»*
3. *«nao foi construido o selar este ato no ri? se nao foi, fazer.»*
4. *«aquela av 4, 5 e 6 nao podem ficar como atos prontos, precisam ficar como
   atos para serem revistos e lavrados. Crie um mecanismo para compatibilizar
   isso e arrume a 3110»*
5. *«nao esqueca de construir o selar ato depois. deixe tudo pronto para
   comecar, revisar e encerrar qualquer ato no ri»*
6. *«atualizei, resolva todos problemas para alcancar o resultado que eu
   preciso, tens autorizacao»*

---

## 2. O QUE ESTÁ FEITO, E O QUE CADA PEÇA É

### 2.1 A minuta — `ri_minuta.py` + tabela `ri_minutas`

O ato **escrito e ainda não lavrado**: sem número tomado, fora da corrente de
hash, sem selo e sem custas.

**Ela não é `ri_rascunhos`**, e a razão é medida: aquela tem
`UNIQUE(matricula_id)` — um rascunho por ficha, que é o certo para «o ato que
estou escrevendo agora»; aqui são **três de uma vez**, cada uma com
`numero_pretendido` e vindas de um arquivo.

Situações: `A_REVISAR | LAVRADA | DESCARTADA`. Origens: `IMPORTACAO`,
`DESFEITO_DE_ATO`, `MANUAL`.

**O módulo não lavra, não numera, não sela e não cobra** — há teste que varre os
nomes públicos, a mesma régua das fraudes, do CNIB e do usucapião.

### 2.2 As rotas

| rota | quem pode | o que faz |
|---|---|---|
| `POST /registro-imoveis/<id>/atos` | ADMIN · MANAGER · USER | lavra (a de sempre). Aceita `minuta_id` e a marca `encerra` |
| `POST /registro-imoveis/minuta/<id>/guardar` | ADMIN · MANAGER · USER | guarda a revisão **sem lavrar** |
| `POST /registro-imoveis/minuta/<id>/descartar` | ADMIN · MANAGER | tira da fila, **com motivo escrito** |
| `POST /registro-imoveis/ato/<id>/selar` | ADMIN · MANAGER · USER | sela ato **já lavrado**, inclusive em ficha encerrada |
| `POST /registro-imoveis/<id>/reabrir` | ADMIN · MANAGER | desfaz o encerramento sem apagar o ato que fechou |

### 2.3 O ciclo na ficha da matrícula

| | onde |
|---|---|
| **começar** | «Lavrar novo ato», «Lavrar a partir de modelo», rascunho |
| **revisar** | painel «Minutas a revisar e lavrar» → «Revisar e lavrar» abre o formulário de sempre **preenchido** |
| **guardar a revisão** | botão «Guardar a revisão sem lavrar», no mesmo formulário |
| **lavrar** | «Lavrar ato» — a minuta sai da fila **na mesma transação** |
| **encerrar** | caixa «Este ato encerra a matrícula» (só do oficial) |
| **selar** | «Selar este ato», em cada ato sem selo |

### 2.4 As decisões de desenho, e por que não são arbitrárias

- **Quem lavra é `ri_lavrar_ato`, e só ela.** Duas portas para lavrar seriam
  duas versões da regra que numera e sela, e divergiriam no primeiro conserto.
- **A marca de LAVRADA vai na mesma transação do ato** — ato que não entra
  deixa a minuta onde estava. Há teste que lavra por cima de um número já
  ocupado para provar isso.
- **A minuta não se apaga ao virar ato**: ela é a prova de que aquele texto
  existia antes e de onde veio.
- **Minuta lavrada não se revisa nem se descarta**: ela é a procedência do que
  está no livro.
- **`None` no formulário quer dizer «não mexi», e não «esvazie»** — uma revisão
  que mandasse só o teor apagaria a natureza do título, que é justamente o que o
  selo exige.
- **O rastro grava o NOME, e não o login** — «mario» não responde «quem revisou
  este texto?». É a convenção de `reaberta_por`, que aparece na mesma tela.
- **«Este ato encerra a matrícula» não lavra uma segunda averbação.** Sem isso,
  a AV-06 (que *é* o encerramento) deixava a ficha aberta, e o botão «Encerrar»
  lavraria uma AV-07: dois encerramentos na mesma ficha, e ninguém sabendo qual
  vale.
- **A guarda do encerrar é por AÇÃO, e não por rota** (`usuario_papel`): a rota
  aceita USER porque lavrar é do balcão. **E a recusa derruba o ato inteiro** —
  lavrar metade do que foi pedido deixaria uma averbação de encerramento no
  livro com a ficha aberta.
- **As quatro colunas do encerramento moram num lugar só**
  (`_marcar_a_ficha_encerrada`). Ficha que diz `encerrada=0` com um ato de
  encerramento no livro **aceita registro novo sobre imóvel já transportado**.
- **O aviso da minuta lembra, mas não marca.** Quando o teor traz
  «ENCERRAMENTO», a tela pede para marcar a caixa — e a caixa continua
  desmarcada: fechar uma ficha por causa de uma palavra no texto seria a máquina
  decidindo o ato.

### 2.5 O painel dos inacabados ganhou duas fontes

| chave | o que mostra | quantas hoje |
|---|---|---|
| `RI_MINUTA` | minuta `A_REVISAR`, rotulada `AV-4`, `AV-5`… | **3** |
| `RI_FICHA_SEM_ATO` | ficha **ESTRUTURADA** aberta sem nenhum ato | **4** |

**O número é o que torna a segunda possível:** **1.549** fichas abertas não têm
ato em `ri_atos`, e listá-las seria o alarme que soa sempre — quase todas são
ACERVO, onde o ato mora dentro do teor. Só nas ESTRUTURADAS o sistema numera, e
ali ficha sem ato é ficha que ninguém escriturou: são **4** (matrículas 8,
4.010, 4.016 e 4.018).

**O filtro é `tipo_ficha`, e não `origem`** — das quatro, uma é `EOFICIO`, uma é
`PDF_OCR` e duas são `MANUAL`. `origem` diz de onde a LINHA veio; o que decide
aqui é **como a ficha se escritura**.

### 2.6 A ferramenta — `tools/atos_para_minutas_do_ri.py`

Devolve ato lavrado por engano à condição de minuta. **Só mede por padrão**;
`--confirmar` age, e antes de agir tira cópia do banco (`VACUUM INTO`).

**As quatro recusas, e o que cada uma protege:**

1. ato **com selo** — selo pago amarrado a ato que deixa de existir é selo órfão;
2. ato **com dinheiro no caixa** — dinheiro sai por estorno, que deixa rastro;
3. ato **amarrado a prenotação** — a prenotação garante a prioridade do título;
4. ato que **não é a cauda da corrente de hash** — apagar do meio deixaria o
   seguinte apontando para um hash que não existe mais.

E ele **limpa o encerramento** quando o ato que fechou a ficha sai — deixá-lo
apontando para uma AV que não existe é carimbo que mente. **A titularidade ativa
não volta sozinha**, e o script diz isso em vez de adivinhar.

---

## 3. O QUE JÁ ESTÁ NA PRODUÇÃO

**A matrícula 3.110 está arrumada.** Rodado em 15/09 às 10h13, com a ordem
expressa do oficial:

| | |
|---|---|
| atos da 3.110 | **0** (eram 3) |
| minutas `A_REVISAR` | **3** — AV-04, AV-05, AV-06, com o teor inteiro |
| a ficha | **ATIVO**, encerramento limpo |
| selos de firma de 2022 | **3, intactos** |
| cópia do banco | `C:\ProgramData\CartorioGestao\cartorio_gestao.antes-das-minutas-20260915-101345.sqlite3` (154 MB) |

**O código NÃO está no servidor.** O servidor está na **3.6.129** (aplicada por
ele às 10h11) — tem o reabrir, o selar e o painel das minutas, mas **não tem** a
marca «este ato encerra a matrícula», as duas fontes novas do painel nem o
«guardar a revisão».

---

## 4. O QUE PAROU, E POR QUÊ

### 4.1 Seis atos em três fichas, esperando a ordem dele

**O script de importação rodou de novo em 15/09 às 08h03:47** e lavrou seis
atos, todos sem selo:

| ficha | atos | o que são |
|---|---|---|
| **3.201** (Livro 2R, id 4894) | AV-04 | destaque de área e abertura de matrícula — protocolo 11.548 |
| **1.197** (Livro 2-F, id 4967) | AV-07, AV-08, AV-09 | retificação de área, certificação SIGEF/INCRA e **o encerramento** — protocolo 11.539 |
| **4.017** (Livro 2, id 5379) | R-01, AV-02 | título de domínio sob condições resolutivas e as cláusulas — protocolo 11.548 |

**A 1.197 é a 3.110 outra vez, inteira**: a última AV encerrou o livro, a ficha
ficou `encerrada=1` e os três atos do dia sem selo.

**Ensaiados os três: passam nas quatro recusas** e são o caso idêntico. A
execução foi **bloqueada pelo classificador** («Irreversible Deletion»), e não
se contornou: o oficial não nomeou estas fichas, e elas nasceram naquela manhã.
**Os comandos estão no item 5.2.**

### 4.2 As três fichas vazias se explicam

A **4.016** é o destino do transporte da 3.110, a **4.017** é o destaque da
3.201, e a **4.018** é o destino da 1.197. As três estão com **zero atos** — e
agora aparecem no painel, em vez de ficarem escondidas.

**O que se lavra nelas é decisão registral do oficial.** O sistema passou a não
esconder que estão em branco; inventar parte ou ato ali seria fabricar registro.

### 4.3 O script continua lavrando por fora — e não é meu para consertar

Medido na auditoria da produção:

| | |
|---|---|
| atos do RI com `origem='MANUAL'` | **10** |
| deles com `RI_ATO_LAVRADO` na auditoria | **4** — todos de 18/08, pela ESCREVENTE |
| os seis de 15/09 às 08:03:47 | **zero** auditoria, **zero** selo |

**O script insere direto em `ri_atos`.** Isso explica as duas coisas de uma vez:
por que os atos nasceram sem selo e sem custas (**não foi o selador nem a tela:
o caminho que lavra não foi usado**) e por que o defeito se repete.

**O mecanismo das minutas não impede isso**, e é honesto dizer: quem não passa
pela rota não é alcançado por guarda nenhuma da rota. **O script não está nesta
árvore** — é de outra passada, e a regra da casa é «quem não está construindo o
módulo não mexe nele». O conserto dele é **chamar `RIMIN.criar`** em vez de
`INSERT INTO ri_atos`.

---

## 5. O QUE FAZER A SEGUIR, na ordem

### 5.1 Aplicar a 3.6.130 (precisa de UAC, é dele)

```bat
SERVIDOR\ATUALIZAR_SISTEMA.cmd
```

**Como conferir que subiu:** abra a ficha de uma matrícula e o formulário de
lavrar tem de trazer, para o oficial, a caixa **«Este ato encerra a
matrícula?»**. Se não trouxer, a atualização não subiu.

### 5.2 Arrumar as três fichas restantes (uma por vez, ordem dele)

Sem `--confirmar` ele só mostra:

```bat
"%PROGRAMDATA%\CartorioGestao\runtime\Scripts\python.exe" tools\atos_para_minutas_do_ri.py "%PROGRAMDATA%\CartorioGestao\cartorio_gestao.sqlite3" --matricula 3201 --atos 4 --confirmar
```

```bat
"%PROGRAMDATA%\CartorioGestao\runtime\Scripts\python.exe" tools\atos_para_minutas_do_ri.py "%PROGRAMDATA%\CartorioGestao\cartorio_gestao.sqlite3" --matricula 1197 --atos 7,8,9 --confirmar
```

```bat
"%PROGRAMDATA%\CartorioGestao\runtime\Scripts\python.exe" tools\atos_para_minutas_do_ri.py "%PROGRAMDATA%\CartorioGestao\cartorio_gestao.sqlite3" --matricula 4017 --atos 1,2 --confirmar
```

Depois disso são **9 minutas** em 4 fichas, e a 1.197 volta a aceitar atos.

### 5.3 Revisar e lavrar, na ordem do protocolo

**Os protocolos amarram os atos entre si** — lavrar fora de ordem deixaria a
cadeia sem sentido:

- **protocolo 11.539** → 1.197: AV-07 (retificação) → AV-08 (SIGEF) → AV-09
  (encerramento, **com a caixa marcada**), abrindo a 4.018;
- **protocolo 11.548** → 3.201: AV-04 (destaque), abrindo a 4.017; e na 4.017:
  R-01 (título de domínio) → AV-02 (condições resolutivas);
- **protocolo 11.559** → 3.110: AV-04 → AV-05 → AV-06 (encerramento, **com a
  caixa marcada**), com destino 4.016.

Ao lavrar, o selo sai do selador; se ele não responder, o ato fica lavrado e
aparece em «atos sem selo», com o botão «Selar este ato» ao lado.

### 5.4 Falar com quem construiu o importador

Ele tem de **criar minuta**, e não lavrar ato. Enquanto isso não mudar, a
próxima importação repete tudo.

### 5.5 Depois do expediente — a suíte inteira e o `.cgu`

**Não há pacote desde a 3.6.99**: as versões **3.6.100 a 3.6.130** (31) não têm
`.cgu`, logo **não há ponto de retorno** para elas. O `.cgu` é o desfazer deste
projeto, que não tem git.

---

## 6. O QUE FOI CONSERTADO DE PASSAGEM, e o que cada um ensina

### 6.1 `ato_selado` escrevia numa coluna que não existe

`registrar_selo_obtido_a_mao` fazia `UPDATE {tabela} SET selo=?`, e `ri_atos`
guarda em **`selo_texto`** → `sqlite3.OperationalError: no such column: selo`.

**`COLUNA_DO_SELO`, no mesmo arquivo, existe exatamente para isso**, e
`vincular_ao_ato` já a consultava desde 27/08 — era a outra metade do ciclo que
não a usava. **O defeito estava escondido porque a função não tinha chamador**
(o CLAUDE.md registra isso em 01/09), e o botão novo de selar foi o primeiro.

**E o estrago seria caro:** o selo entra em `sd_selos` na linha de cima, e a
exceção derrubaria a transação inteira — o escrevente digitaria a etiqueta do
selo **já pago** e levaria um HTTP 500.

> **Peça pronta que ninguém usa também esconde defeito**, e não só serve de arma
> para alguém religar depois.

### 6.2 A chave do selo é `tabela` **mais** `ato_id`

Ao medir o que estava amarrado aos atos 3728-3730,
`sd_selos WHERE ato_id IN (...)` devolveu **três selos de reconhecimento de
firma de 2022**, de `nt_reconhecimentos`: **`ato_id` é chave dentro de cada
tabela, e não número global.** Um script pela metade da chave apagaria selos
reais de outra atribuição.

### 6.3 A contagem do catálogo de modelos, vermelha desde 11/09

Apurado nos `.cgu`: a **3.6.90** tem 22 entradas e a **3.6.98** tem **30** — os
oito que entraram são os quatro **teores** do RCPJ/RTD e as quatro peças da
**certidão em PDF**. O teste afirmava **26**, que não corresponde a nenhum dos
dois. Corrigido o **número**; **o porquê é de quem os pôs**, e
`modelos_da_casa.py` não foi tocado.

### 6.4 Três enganos meus, que ficam escritos

- **Inventei a coluna `destino_encerramento`** no `UPDATE` do script. Ela não
  existe: o destino vai **dentro** de `motivo_encerramento`. Teria estourado no
  `--confirmar`, **depois** da cópia e com o ato já apagado.
- **Juntei texto no SQL** (`tipo || '-' || numero`) e o varredor de
  portabilidade me pegou — o teto de `inacabados.py` é **zero**. A regra escrita
  é «recorte e junte em Python, depois de ler», e subir o teto era o caminho
  preguiçoso.
- **Editei arquivo com a suíte rodando**, e isso produziu uma vermelha que não
  existia — um teste meu falhou na fatia larga e passou sozinho duas vezes.
  **Não se mexe na árvore que está sendo medida.**

E um quarto, no ensaio: o `print` com `→` estourou em `UnicodeEncodeError`
**depois** de o banco já estar certo. **Banco gravado e tela com erro é a pior
ordem possível**, porque quem lê conclui que nada foi feito.

---

## 7. ARQUIVOS DESTA PASSADA

**Novos**

| | |
|---|---|
| `ri_minuta.py` | o domínio da minuta |
| `tools/atos_para_minutas_do_ri.py` | devolve ato à condição de minuta |
| `tests/test_ri_minuta.py` | 19 testes |
| `tests/test_ri_minuta_revisao.py` | 13 testes |
| `tests/test_ri_encerrar_pelo_ato.py` | 11 testes |
| `tests/test_ri_selar_ato.py` | 17 testes |
| `tests/test_ri_reabrir_matricula.py` | 8 testes |

**Mexidos**

`ri_web.py` (import, ficha, lavrar, selar, guardar, descartar,
`_marcar_a_ficha_encerrada`, `_quem_mexeu_na_minuta`) · `ri_schema.py`
(tabela + índice) · `templates/ri_ficha.html` (painel, prefill, caixa de
encerrar, botão de guardar) · `inacabados.py` (duas fontes + `rotulo_2`) ·
`ato_selado.py` (a coluna do selo) · `tests/test_modelos_da_casa.py` (a
contagem) · `app.py` e `VERSAO.txt` (3.6.130) · `CLAUDE.md`

**Testes:** os 68 dos cinco arquivos do RI passam; a fatia larga (566) fechou
com **565 verdes e uma vermelha**, que era a contagem do catálogo — corrigida, o
arquivo dela passa inteiro (28). Lint limpo em tudo o que se escreveu.

**A suíte inteira não rodou**, por ordem de 31/08: ela roda quando ele pedir.

---

## 8. MEMÓRIA GRAVADA (para quem retomar)

- `minutas-ri-ficam-de-pe-e-selam-depois` — a decisão e o mecanismo
- `reabrir-matricula-do-ri` — o que o reabrir faz e o que não faz
- `chave-do-selo-e-tabela-mais-ato-id` — a armadilha da meia chave
- `importacao-ri-lavra-por-fora-do-sistema` — o script, e como medi-lo


---

## 9. O CARIMBO DO SELO — a segunda metade do dia (3.6.131 → 3.6.132)

Depois de o oficial lavrar a **AV-04/3.110** a partir da minuta, ele relatou:
*«o teor foi com espacamento no meio, nao foi o carimbo do selo e o relatorio
de emolumentos deve ir junto com o carimbo do selo e qr code»*. **Eram três
defeitos, e ele os viu como um papel torto.**

### 9.1 O teor guardava o marcador do selo

`ri_lavrar_teor.versao_final_para_lavrar` compunha, na lavratura, «teor +
relação de emolumentos + espaço reservado para o selo». O espaço reservado é um
desenho tipográfico:

```
--- Espaco reservado para o selo digital do TJMA ---
[ selo / verificacao ]                    [ QR / autenticacao ]
```

Aqueles **vinte espaços** foram o que ele viu. O desenho previa que o carimbo de
verdade entraria depois, «quando o aparelho responde» — mas **o teor congela na
corrente de hash**: o marcador entrou e não sai mais.

**Medido:** o teor gravado do ato 3737 tem **dez linhas**, e nove não são do
ato; a minuta de onde ele saiu e o ato original têm **uma**. O defeito alcança
**1 ato** em todo o banco.

**O conserto é no CHAMADOR**, com os dois parâmetros que a própria API daquele
módulo oferece (`com_emolumentos=False, com_espaco_selo=False`) — não se
reescreveu o módulo de outra passada. **E `sem_fecho_antigo` fica**, que é o que
interessa dele aqui: é ele que tira o fecho manual da minuta («Emolumentos:
R$ ______ … Selo de Fiscalização Digital nº ______»), que não pode conviver com
o selo que o aparelho emite.

### 9.2 O carimbo lia a coluna do ato, que guarda o NÚMERO

**Este é o achado que explica o pedido 3.** `ri_atos.selo_texto` recebe
`str(numero)` de `ato_selado.vincular_ao_ato` — 28 caracteres:

| | |
|---|---|
| `ri_atos.selo_texto` | `AVESVD000000IFWIQRMJW7CGUA95` |
| `sd_selos.texto` | a etiqueta inteira, com data, ato, partes e **todos os fundos** |
| `valores_para_o_carimbo(selo_texto)` | **vazio** |
| `valores_para_o_carimbo(texto do razão)` | `Total R$ 134,43 … FERRFIS R$ 1,20` |

**A coluna se chama `selo_texto` e recebe o número** — «a mesma palavra em dois
lugares» outra vez. Enquanto o carimbo lesse a coluna do ato, ele **nunca**
mostraria os emolumentos — e isso valia para **todo ato do RI selado
automaticamente**, e não só para este.

**Não se mexeu em `vincular_ao_ato`:** ela grava o número em cinco tabelas de
cinco atribuições, e mudar o que ela escreve mexeria no cartão de autógrafo e na
prenotação junto. **Quem tem de ler a fonte certa é quem desenha o carimbo** — e
a fonte é o razão. A chave é `tabela` **mais** `ato_id`.

### 9.3 O QR não saía

O campo de colar QR saiu da tela em 14/09 (medido então: em 1.245 atos, **zero**
tinham QR colado), e nada passou a preencher `selo_qr`. Agora ele é **gerado na
hora** do `qr_token` do razão — e, sem token, do modelo padrão, que ao menos
abre o portal certo. Sem o `segno` instalado devolve vazio e o carimbo sai só
com o número e a linha de valores: **QR é conveniência, nunca motivo para o
papel não sair**.

### 9.4 E o conserto dos dois primeiros criou um quarto — que fica DECLARADO

Com a etiqueta inteira chegando ao carimbo, a conta passou a sair **três
vezes**: uma dentro da etiqueta, uma no **resumo curto do ato**
(`ri_atos.emolumentos`, colado no fim da linha) e uma na **relação rotulada**
«Emolumentos do carimbo».

**Some a do meio, e só ela.** O resumo curto é literalmente os mesmos dois
valores que a etiqueta já traz, sem rótulo e sem os fundos — e quem o passava
era o meu próprio chamador. A guarda ficou em `emolumentos_do_carimbo`, no
`contexto_ficha`.

> **E EU FUI LONGE DEMAIS ANTES DE RECUAR.** Suprimi também a relação rotulada,
> invocando «sem repetições» — a regra da certidão do RCPN, de 01/09 — e
> **derrubei o teste de quem a construiu** (`test_carimbo_inclui_relacao_de_
> emolumentos`). Ela existe de propósito: na etiqueta os valores vêm no meio de
> uma frase corrida, e ali vêm legíveis, que é o «relatório de emolumentos» que
> o oficial pediu. **Recuei e devolvi `ri_odt.py` ao desenho deles.**
>
> No meio disso escrevi a guarda errada duas vezes: comparei as frases
> inteiras, e elas **nunca casam** — a etiqueta escreve `FERC FADEP FEMP` e a
> relação devolve `FERC FEMP FADEP`. **A ordem dos fundos difere.**

**O QUE ESPERA DECISÃO DELE.** O carimbo sai hoje com a conta **duas vezes** —
a etiqueta crua, que o sistema reproduz sem reformatar porque é o que foi
selado, e a relação rotulada logo abaixo:

```
Poder Judiciário – TJMA. Selo: AVESVD000000IFWIQRMJW7CGUA95, 15/09/2026
17:34:08, Ato: 16.22.2, Parte(s): PESSOA EXEMPLO, PESSOA EXEMPLO
PESSOA EXEMPLO, Total R$ 134,43 Emol R$ 120,03 FERC R$ 3,60 FADEP R$ 4,80
FEMP R$ 4,80 FERRFIS R$ 1,20 Consulte em https://selo.tjma.jus.br
Emolumentos do carimbo: Total R$ 134,43 Emol R$ 120,03 FERC R$ 3,60
FEMP R$ 4,80 FADEP R$ 4,80 FERRFIS R$ 1,20
```

**São duas leituras defensáveis do mesmo pedido dele**, e por isso nenhuma das
duas sessões devia decidir sozinha:

| | |
|---|---|
| **fica como está** | a relação rotulada é o relatório legível que ele pediu; a etiqueta crua é a prova do que foi selado |
| **sai a relação** | «sem repetições», a régua da certidão do RCPN — e os valores já estão na etiqueta |

**Pergunta para ele, com o papel na mão.**

### 9.5 O que ficou para você fazer

**A AV-04 já está lavrada com o teor sujo**, e a decisão dele foi *«deixe o
selo, vamos arrumar o texto so»*. `tools/limpar_marcador_do_selo_no_teor.py`
tira o marcador, refaz o hash sobre o texto que de fato está escrito e grava o
rastro em `audit_logs` (`RI_ATO_TEOR_CORRIGIDO`, com o hash antes e depois).

**A única recusa:** ele **não** mexe em ato que tenha ato depois dele na mesma
ficha — o hash de um é o `hash_anterior` do seguinte, e refazer a corrente
inteira seria reescrever a história de todos. A AV-04 é o único ato da ficha, e
por isso é segura. **O selo não entra no hash**, então ele continua valendo.

Ensaiado contra cópia da produção: teor de **10 → 1 linha**, hash refeito e
conferido contra o teor gravado, selo intacto, auditoria escrita.

```bat
"%PROGRAMDATA%\CartorioGestao
untime\Scripts\python.exe" tools\limpar_marcador_do_selo_no_teor.py "%PROGRAMDATA%\CartorioGestao\cartorio_gestao.sqlite3" --ato-id 3737 --confirmar
```

**Sem `--ato-id` ele só lista.** A execução na produção foi **bloqueada pelo
classificador** desta sessão (mexe em ato lavrado), e não se contornou.

### 9.6 Duas passadas na mesma árvore, e desta vez deu certo

`ri_lavrar_teor.py` estava sendo escrito por outra sessão — mexido **22 minutos
antes** de eu medir. A regra da casa mandaria só declarar; o oficial mandou
terminar aqui. **O que se fez para não atropelar:** o conserto ficou no
**chamador** e no **desenho do carimbo**, usando a API deles; nenhuma função de
`ri_lavrar_teor.py` foi reescrita. **Conferido: os 34 testes daquele módulo
continuam verdes.**
