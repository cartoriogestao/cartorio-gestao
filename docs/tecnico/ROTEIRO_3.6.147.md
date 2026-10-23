# ROTEIRO 3.6.147 — o Livro 3 que entrou sem gente e sem averbação

**Data:** 18/09/2026 · **Versão:** 3.6.147 (projeto) · **Pacote anterior:** 3.6.141

> **Este roteiro existe por causa de um pedido do oficial** — *«preciso que tenha
> campo para importar do acervo registro do livro 3 do RI, igual temos no livro
> 2»* —, e o que ele traz além da tela é a medição que decidiu o desenho: **o
> Livro 3 estava no balcão com 16 registros e ZERO pessoas**, e as 5 averbações
> dos títulos ficaram todas no acervo.

---

## 1. O PEDIDO, nas palavras dele

**18/09/2026:**

> «preciso que tenha campo para importar do acervo registro do livro 3 do RI,
> igual temos no livro 2»

A lista das matrículas do Registro de Imóveis (`/registro-imoveis/importacoes`)
tem a porta do acervo desde sempre. A lista do **Livro 3** só oferecia o
**registro manual**, um de cada vez — e o acervo do E-Ofício tem os 14 registros,
as 25 partes e as 5 averbações guardados.

---

## 2. O QUE ESTAVA ACONTECENDO, medido na base do balcão

| | antes desta versão |
|---|---|
| `ra_registros` | **16** — 14 do acervo (`EOFICIO`) e 2 desta casa (`IMPORTACAO`) |
| `ra_atos` | **16** — um ato de registro por ficha |
| `ra_partes` | **0** |

**Zero pessoas em dezesseis registros.** A carga anterior trouxe o registro e o
ato de abertura, e **parou ali**: quem emitiu a cédula, quem é o credor, quem
avalizou — nada disso entrou. E as **5 averbações** que o acervo guarda (uma
cédula cancelada, uma carta autorizativa, um primeiro aditamento, uma
transferência de propriedade) também ficaram lá.

---

## 3. AS DUAS MEDIÇÕES QUE DECIDIRAM O DESENHO

### 3.1 A parte se resolve pelo `tbOrtoga`, e não pelo `tbPessoa`

O acervo tem as duas tabelas, e **elas discordam no mesmo id**: no
`id = 10018` o `tbPessoa` diz **«PESSOA EXEMPLO»** e o `tbOrtoga` diz
**«PESSOA EXEMPLO»** — e o credor daquele registro é o banco.

Conferido nas 25: **o `tbOrtoga` resolve as 25**. A leitura é a dele, com o
`tbPessoa` atrás para o que ele não alcançar, e há teste que guarda a ordem.

### 3.2 O corpo da averbação NÃO está dentro do teor do registro

Era a pergunta que decidia tudo: se o texto da averbação já estivesse no teor da
ficha, bastava importar a ficha; se não estivesse, a averbação tinha de entrar
como **ato próprio**.

Medido: **não está**. As 5 averbações entram em `ra_atos` com o texto inteiro —
**4.395**, **4.036**, **1.230**, **1.158** e **799** caracteres —, cada uma com
o seu número (`AV-1` do registro) e a sua data. Nada de texto foi inventado: é o
que o acervo guarda.

---

## 4. O QUE O SISTEMA FAZ AGORA

**Tela nova:** *Demais atribuições → Livro 3 → **Importar do acervo***
(`/livro3/importar-do-acervo`). Chega-se a ela por **três portas**, porque a
pergunta nasce em três lugares: o card no alto da lista do Livro 3, o botão na
lista vazia (quem abre uma lista vazia precisa saber onde buscar) e
*Registro de Imóveis → Importações*, ao lado da carga das matrículas.

**Conferir e importar são dois botões.** O primeiro só lê o acervo e o banco e
diz o que entraria — `14 registro(s), 5 averbação(ões) e 25 parte(s)` —; o
segundo grava. Aqui não há como desfazer: acervo importado vira o livro.

**A passada olha o que FALTA, e por isso alcança quem já estava.** Os 14
registros já estão gravados nesta casa; se a passada só olhasse as fichas novas,
as partes e as averbações **nunca chegariam neles** — foi exatamente o que
aconteceu até hoje. A chave é `LivroAuxiliar:<id>` / `LivroAuxiliarPartes:<id>`
por linha, e por isso rodar de novo não duplica nada (medido: a segunda rodada
insere zero e conta as 25 partes e as 5 averbações como já importadas).

**Parte de averbação que já era parte do registro não se repete** (medido: 10
delas nas 5 averbações). O mesmo banco que é credor do registro não é reinserido
como parte da averbação do mesmo registro.

**A tela mostra o que NÃO entra, com o motivo.** Parte que o `tbOrtoga` não
resolve aparece na conferência com o número, em vez de sumir calada — hoje são
**zero** nas 25.

---

## 5. ENSAIO CONTRA A PRODUÇÃO, NUMA CÓPIA DO BANCO

`tmp/_livro3_ensaio.py` tira cópia por `VACUUM INTO`, roda a carga duas vezes e
confere que a produção não foi tocada. Medido em 18/09/2026:

| | antes | depois da 1ª rodada | 2ª rodada |
|---|---|---|---|
| `ra_registros` | 16 | 16 | 16 |
| `ra_atos` | 16 | **21** | 21 |
| `ra_partes` | **0** | **25** | 25 |

E a produção, conferida no fim: **16 · 16 · 0** — a cópia mudou, o banco do
balcão não.

**Os dois registros `CANCELADO` (nº 1.198 e 1.243, de 14/09/2026) são desta
casa**, não do acervo, e a passada não os alcança: eles já têm o seu ato, e o
que falta neles não é parte do acervo.

---

## 6. COMO CONFERIR QUE SUBIU

1. **Demais atribuições → Livro 3.** O card *Importar do acervo* tem de estar no
   alto. Se não estiver, a atualização não subiu.
2. Apertar **Importar do acervo** → **Conferir**. A tela tem de dizer:
   **14 registro(s) — 0 novo(s)**, **5 averbação(ões)** e **25 parte(s)**.
3. Apertar **Importar**. Depois, abrir a lista do Livro 3: as fichas mostram as
   partes (emitente, credor) e a averbação no lugar dos atos.
4. No banco: `ra_partes` deixa de estar vazia (**0 → 25**) e `ra_atos` vai de
   **16 para 21**.

---

## 7. O QUE ESTE PACOTE LEVA ALÉM DESTA PASSADA

**A árvore tinha outra passada escrevendo nela no mesmo dia**, e o pacote leva a
árvore inteira — não o meu recorte. Para que nada chegue sem saber de onde veio,
o que **não é desta passada**, por família:

| família | arquivos |
|---|---|
| **tarefas e avisos** | `tarefa_processo.py`, `templates/_aviso.html`, `static/avisos.js`, `templates/tasks.html`, `templates/task_detail.html`, `tools/normalizar_situacao_das_tarefas.py` |
| **depósitos do caixa** | `caixa_depositos.py`, `caixa_schema.py`, `caixa_web.py`, `templates/caixa_depositos.html`, `docs/tecnico/O_TIPO_DE_SERVICO_DO_DEPOSITO.md` |
| **indicador do RI** | `ri_indicador_lancamentos.py`, `templates/ri_indicador_pessoal.html`, `templates/ri_indicador_real.html` |
| **endereço do ONR** | `onr_endereco_do_teor.py`, `onr_endereco_schema.py` |
| **folha e verso do livro** | `notas_livro.py`, `ri_odt.py`, `tests/test_folha_livro_verso.py` |
| **credenciais das Centrais** | `centrais_cred.py`, `docs/tecnico/PEDIDO_DAS_CREDENCIAIS.md` |
| **agente** | `static/agente.js`, `templates/_agente*.html` |

**E esta versão nasceu da 3.6.146, que outra passada carimbou e nunca
empacotou** — o último pacote aplicável era o **3.6.141**. Este roteiro é o da
**3.6.147** e é o que se aplica.

### 7.1 Ficam declaradas cinco vermelhas que NÃO são desta passada

Medidas em 18/09/2026, e nenhuma delas foi consertada aqui — **quem não está
construindo o módulo não mexe nele**:

| onde | o que é |
|---|---|
| `test_atribuicoes_web.py`, `test_habilitacao_web.py`, `test_desfazer_averbacoes_rcpj.py` (4 nesta árvore) | **a mesma família**: o registro, o assento, a certidão e a averbação que **não conseguem selo são CANCELADOS**, e «não ter item de cobrança marcado» conta como não conseguir selo. É a segunda metade do item 1 que falta nesses módulos: no RI, o que **só o selo diz** suspende, e o que **falta preencher** não. Uma delas chama-se `test_a_habilitacao_continua_expedida_sem_o_selador` |
| `test_funcao_sem_tela.py` (1) | `notas_livro.rotulo_folha_da_pagina` — `test_nenhuma_funcao_nova_fica_sem_tela` acusa a função sem caminho até tela. No papel quem faz a conta é `ri_odt.campo_folha_do_livro_odf`, que a cita na prosa e escreve a mesma fórmula dentro do ODF. É trabalho da passada do verso do livro, de hoje |

O caso da certidão foi apurado até o fim, e é o mais claro dos quatro: **a
certidão é montada e o item de cobrança é marcado, e ainda assim o ato é
cancelado** — a mensagem «Lançado no caixa» não sai, porque a certidão deixou de
existir antes. O conserto é da passada do módulo, e não desta.

Três outras vermelhas de `test_atribuicoes_web.py` (a carga de verdade e a
abertura de registro com selo de outra serventia) **já estavam vermelhas na
3.6.141** — conferidas rodando os testes de hoje contra aquele pacote.

### 7.2 A SUÍTE INTEIRA NÃO FOI MEDIDA HOJE, e o motivo fica escrito

**Isto é uma declaração, e não um desculpa.** O § 7.1 lista os casos que foram
apurados um a um; **ele não é o total de vermelhas da 3.6.147**, porque o total
**não foi medido** — e quem ler este roteiro daqui a um mês precisa saber disso.

Em **18/09/2026, às 15h24**, a suíte inteira foi disparada
(`pytest tests\ -q -n 4 --dist loadfile`, **6.560 testes**). Ia tudo bem até
**41%**: 15 vermelhas, nenhum erro. Às **16h08**, em **78%** e 43 minutos de
execução, a contagem era de **652 falhas e 44 erros** — e uma dessas duas
medições não podia ser verdade.

**O corte diz o que aconteceu: os `F` explodem em 69%**, e 69% cai em
**~15h59:45**. O `tests/conftest.py` foi gravado às **15h59:47** — dois segundos
depois. A árvore estava sendo reescrita **durante a medição**:

| hora | o que foi gravado |
|---|---|
| 15:59:21 | `tools/pytest_guard.py` |
| 15:59:27 | `ri_schema.py` |
| **15:59:47** | **`tests/conftest.py`** |
| 16:06:20 | `ri_import.py` |
| 16:06:30 | `ri_web.py` |

**E não era uma suíte só: havia TRÊS rodando ao mesmo tempo nesta árvore** — a
minha e mais duas da outra passada (`test_ajuda_*` + `test_agente.py` às 15h53,
e a família da certidão do RI + `test_ato_selado.py` às 15h58). Elas disputam os
mesmos diretórios `tmp` e o mesmo banco.

**A própria outra passada chegou à mesma conclusão no mesmo minuto**, e escreveu
o guarda que diz isso melhor do que eu diria — `tools/pytest_guard.py`, primeira
linha:

> *«Uma suite mede uma versao. Se outra suite disputa os mesmos recursos, ou se
> o codigo muda no meio da medicao, o resultado deixa de pertencer a uma versao
> e uma falha pode se multiplicar por centenas.»*

**«Multiplicar por centenas» é literalmente 15 → 652.** O guarda nasceu às
15h59:21, e a minha suíte tinha começado às 15h24 — antes dele existir, e por
isso rodou sem trava.

**A suíte foi parada às 16h09, por ordem dele**, para não continuar disputando
recurso com as execuções da outra passada — **uma suíte contaminada não só mente
sobre si: ela faz a execução vizinha caçar defeito que não existe.**

**O que fica valendo, e o que não fica:**

| | |
|---|---|
| **vale** | os casos do § 7.1, apurados um a um, com o arquivo e o nome de cada um |
| **vale** | **6.560 testes coletados** — a coleta é medida e não depende de ninguém mexer na árvore |
| **NÃO vale** | **652 falhas** — pertencem a uma árvore que mudou no meio, e a nenhuma versão |
| **A CONFERIR** | **o total de vermelhas da 3.6.147** — roda-se limpo quando a outra passada parar de escrever |

**A régua que fica, e ela já estava escrita neste projeto:** *não se mexe na
árvore que está sendo medida, senão a medição não é de nada* — e agora ela tem
um guarda que a aplica em vez de confiar em quem lembra.

---

## 8. O QUE ESPERA O OFICIAL

**Nada trava o balcão.** A importação do Livro 3 é uma decisão de um clique, e o
botão *Conferir* diz exatamente o que vai entrar antes de entrar.

O que fica como pergunta, e não como pendência: **as 25 partes do Livro 3 são o
que o acervo guardou** — 14 registros de cédula rural, dez deles com o Banco do
Brasil ou o Pessoa Exemplo como credor. Se alguma ficha do livro de papel
mostrar parte que o acervo não trouxe, ela se digita na ficha; o que a carga
trouxe não se apaga, e o que falta aparece.
