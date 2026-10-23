# Projeto — Registro de Imóveis: digitalização de acervo no E-Ofício

**Documento de retomada.** Leia por inteiro antes de começar. Contém o que já foi descoberto, decidido e
construído, para que o projeto seja retomado sem repetir investigação.

Escopo: **inclusão de matrículas do acervo do Livro 2 (Registro Geral)**. Nascimento, casamento e óbito
ficam em projetos separados.

---

## 1. O contexto

| | |
|---|---|
| Serventia | Serventia Extrajudicial do Ofício Único de Cidade Exemplo/MA |
| CNS | 000000 |
| CNPJ | 00.000.001/0000-55 |
| Sistema | E-OFÍCIO — Automação Cartorária / MA, Versão 1.0 (Build 0.785) |
| Acesso | máquina Windows operada por AnyDesk a partir de um macOS |

O acervo do Livro 2 está em **fichas físicas digitalizadas**. O trabalho é levar essas matrículas para o
sistema, com fidelidade e sem retrabalho de digitação.

---

## 2. O que já está pronto

Um lote de **429 matrículas** (faixa 3.440 a 4.011) foi extraído de **1.659 páginas** digitalizadas e
convertido para o layout JSON do fornecedor.

| | |
|---|---|
| Matrículas processadas | 429 |
| **Prontas para importar** | **375** |
| Pendentes de conferência | 54 |
| Atos (registros e averbações) | 769 |
| Partes qualificadas | 672, das quais 506 com CPF/CNPJ validado por dígito verificador |
| Teor | 3,6 MB de texto, íntegro |

Distribuição: 111 imóveis rurais (área em hectares) e 286 lotes urbanos (m²), boa parte de REURB-S.

Entregáveis: `entrega/prontas/`, `entrega/pendentes/`, `lote_prontas.json`, `indice.csv`,
`OFICIO_ENCAMINHAMENTO.md`, `RELATORIO_QUALIDADE.md`, `CONFERENCIA.csv`.

**O fornecedor confirmou** que a importação aceita número de matrícula já existente e inclusão de registro
de acervo. O ofício com as perguntas restantes está pronto para envio.

---

## 3. Os dois caminhos

### Caminho A — importação por JSON (preferencial)

O fornecedor forneceu o layout `modelo_json_registro_imovel`, schema_version 1.0. O conversor já produz
arquivos conformes: conferimos chave por chave contra o modelo, sem chave a mais nem a menos.

O modelo é uma gramática de **âncora + lista de atos**: `dados_imovel` (a matrícula) e
`dados_registro_averbacao` (os R- e AV- vinculados). `partes_envolvidas` é polimórfico, com `papel` livre.

**Pendente:** o fornecedor ainda não informou *como* se importa — o documento define formato, não
transporte. As perguntas estão no ofício.

### Caminho B — digitação assistida na tela "Matrícula (Em Acervo)"

`Registro de Imóvel → Matrícula em Acervo`

Mapa completo em `mapa_campos/ri_matricula_acervo.json`.

**Descoberta que muda o desenho:** esta tela é muito mais enxuta do que o layout JSON sugere. Ela tem
apenas duas abas — *Partes do Ato* e *Localização* — e **não tem campo de teor nem lista de atos R-/AV-**.
Provavelmente esses ficam em outra tela, alcançada depois de salvar. Isso precisa ser confirmado antes de
concluir que a importação por JSON substitui o preenchimento manual.

**As partes não são digitadas.** O botão *Adicionar Partes* abre uma busca no cadastro de pessoas do
sistema: escolhe-se a Qualificação (ex.: ADQUIRENTE), busca-se por Nome/Razão Social e vincula-se a pessoa
encontrada. Quem não existe precisa ser criado por *Nova Parte*. Consequência: a automação pode preencher a
busca, mas **escolher a pessoa na lista é decisão humana** — vincular homônimo em registro de imóveis é
erro grave.

---

## 4. O pipeline de extração

```
PDFs digitalizados
   ↓ ri_preparar.py    texto por página → segmenta em matrículas
   ↓ ri_extrair.py     campos + partes + atos por matrícula
   ↓ ri_validar.py     CNM, CPF/CNPJ, datas, coerência
   ↓ ri_conferencia.py fila de pendências com o trecho recortado
   ↓ ri_exportar.py    JSON no layout do fornecedor, separado em prontas/pendentes
   ↓ ri_reocr.py       (quando necessário) refaz o OCR a partir da imagem
```

### Comandos

```bash
python scripts/ri_preparar.py "matriculas 1.pdf" "matriculas cont OCR.pdf"
python scripts/ri_extrair.py
python scripts/ri_validar.py
python scripts/ri_conferencia.py
python scripts/ri_exportar.py --saida registros/ri_lote/entrega
```

`ri_reocr.py` é retomável: cada execução processa o que couber no tempo e grava o estado.

---

## 5. Conhecimento técnico que custou caro

### O dígito verificador do CNM

A matrícula CNJ de 32 dígitos usa **ISO 7064 MOD 97-10**. Descobri testando contra os números lidos:

```python
def dv_cnm(base):  # base = CNS(6) + livro(1) + numero(7)
    return f"{98 - ((int(base) * 100) % 97):02d}"
```

Isso permite **descartar o DV lido pelo OCR e recalculá-lo** — o hífen e os dois dígitos finais são
justamente o que a digitalização mais corrompe. As 429 matrículas conferem.

Decomposição: `CNS(6) acervo(2) serviço(2) ano(4) tipo_livro(1) livro(5) folha(3) termo(7) DV(2)`.

### Dois modelos de ficha convivem no acervo

- moderno: `MATRICULA/CMN No 000000.2.0004011-96`
- antigo: `MATRÍCULA No` com número curto (3.467) e `LIVRO 02-S`

Precisam de detectores separados, e o do modelo antigo tem que ser **restrito à faixa descoberta pelos
CNM** — sem isso ele captura ano de escritura como se fosse matrícula.

### O tesseract estava 5x mais lento que o necessário

Cada página levava 7s. O paralelismo interno brigava por CPU numa máquina de 2 núcleos. Com
`OMP_THREAD_LIMIT=1` e dois processos em paralelo, caiu para **1,4s**.

### A data que aparece primeiro não é a do registro

A ficha traz `CIDADE EXEMPLO/MA, 09/08/2023. PROTOCOLO No 11.008` logo abaixo do cabeçalho. Sem ancorar aí, a
primeira data do texto costuma ser a do **título de origem** — havia matrículas datadas de 1947.

Conferência adicional: comparar a data com a das matrículas **numericamente vizinhas**. Matrícula é aberta
em ordem, então vizinha de número é vizinha de data. Nove destoam mais de dez anos e estão marcadas.

### O campo `folha` não se aplica

O Livro 2 desta serventia é mantido em **sistema de fichas**, onde o assento é identificado pelo número da
matrícula. Folha é coordenada de livro encadernado. O campo vai vazio por não se aplicar — não é falha de
leitura nem pendência. *(Correção do usuário, e ela eliminou 412 falsas pendências.)*

### Extração de partes: o que funciona

O nome vem **sempre depois de um rótulo de papel** e antes da vírgula que abre a qualificação:

```
PROPRIETÁRIOS: PESSOA EXEMPLO, brasileira, maior...
```

Ancorar no rótulo é o que separa o nome da profissão — as duas aparecem na mesma cadeia de vírgulas.

Quando o carimbo da serventia cai sobre o nome e a leitura sai partida, mas o CPF/CNPJ continua legível, a
parte é **reconstruída pelo documento**: o número passa no dígito verificador e o nome canônico já foi lido
com clareza em outra matrícula do mesmo lote. Sete casos, todos marcados na conferência.

Também é feita **uniformização global de nomes**: mesmo CPF com grafias diferentes entre fichas adota a
leitura mais frequente.

**Não entram como partes** quem assina o memorial descritivo (responsável técnico do georreferenciamento)
nem quem lavra o ato.

---

## 6. Bugs que eu mesmo causei — para não repetir

1. **Guarda contra o responsável técnico olhava 200 caracteres para trás.** Na ficha, o bloco do memorial
   vem logo antes de PROPRIETÁRIO, então todo proprietário que viesse depois dele era descartado. Correção:
   quando há rótulo de papel explícito, o papel já está estabelecido e o guarda não se aplica.
2. **"FILHO" estava na lista de palavras proibidas**, para evitar capturar "filha de Fulano". Com isso
   PESSOA EXEMPLO** era descartado oito vezes. Sufixo de sobrenome não é fragmento de
   qualificação.
3. **A lista de proibidas só funcionava em maiúsculas** — comparava sem normalizar caixa, e metade dos
   filtros nunca disparava.
4. **A limpeza de cabeçalho apagava linhas inteiras.** Quando o OCR fundia cabeçalho e conteúdo na mesma
   linha, o começo do bloco IMÓVEL ia junto. Correção: remoção cirúrgica do trecho, não da linha.
5. **O regex do bloco IMÓVEL exigia terminador em até 300 caracteres.** Quando "PROPRIETÁRIO" vinha depois
   disso, não casava nada. Correção: recortar e depois cortar, em vez de exigir que o regex ache o fim.

**A lição maior:** atribuí 71 falhas à qualidade do OCR e refiz 223 páginas. Ajudou, mas boa parte era
código meu. **Diagnostique antes de reprocessar.**

---

## 7. O que ainda falta

1. **Resposta do fornecedor** sobre como se importa o JSON: arquivo individual ou lote, ambiente de
   homologação, retorno por matrícula, consumo de selo.
2. **Confirmar onde ficam o teor e os atos** na tela de acervo do RI — não há campo para eles.
3. **Levantar a lista completa de Qualificação** das partes no modal de adicionar.
4. **Observar o botão "Livro"** do cabeçalho: é botão, não caixa de texto.
5. **Ver o bloco de endereço quando "Localizado em" = Rural** (só vimos Urbano).
6. **54 pendentes**: 12 sem partes, 32 sem área, 22 sem descrição — com sobreposição. O teor está completo
   em todas; a fila de conferência traz o trecho recortado.
7. **9 matrículas com data destoante** da vizinhança, marcadas para conferência.

---

## 8. Regras que não se negociam

- **A automação nunca salva.** Ela prepara; quem confere e salva é o escrevente.
- **Nada é presumido.** Campo que não pôde ser lido fica vazio, com o trecho do documento recortado para
  conferência humana.
- **Nunca escrever direto no SQL Server.** O SSMS está instalado na máquina e tecnicamente daria, mas
  registro público tem selo, matrícula e trilha de auditoria gerados pelo sistema. Inserir por fora quebra
  isso e pode invalidar o ato. Se for por banco, tem que ser rotina homologada pelo fornecedor.
- **Parte é vinculada, não digitada.** No cadastro de pessoas do sistema, escolher o homônimo errado é erro
  de registro público.

---

## 9. Estrutura do pacote

```
PROJETO_REGISTRO_IMOVEIS.md   este documento
config/
   modelo_json_registro_imovel.json    layout do fornecedor (referência)
scripts/
   ri_preparar.py ri_extrair.py ri_validar.py ri_conferencia.py
   ri_exportar.py ri_reocr.py
mapa_campos/
   ri_matricula_acervo.json            a tela do sistema, campo a campo
registros/ri_lote/
   dados_ri.json                       fonte de verdade da extração
   OFICIO_ENCAMINHAMENTO.md            pronto para enviar ao fornecedor
   RELATORIO_QUALIDADE.md
   CONFERENCIA.csv                     fila de trabalho da serventia
   entrega/prontas/  entrega/pendentes/  lote_prontas.json  indice.csv
```

Os dois PDFs de origem (`matriculas 1.pdf`, 199 MB e `matriculas cont OCR.pdf`, 261 MB) **não vão no
pacote** por tamanho. Ficam na pasta Downloads da máquina.
