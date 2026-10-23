# Aprendizado — OCR, fatiamento e importação assistida de matrículas para ONR

Data-base: 12/09/2026.

Este documento registra o processo adotado para transformar dois PDFs grandes de
matrículas digitalizadas com OCR em uma base operacional que possa alimentar o
Cartório Gestão e, depois da conferência, a carga exigida pela ONR.

O objetivo não é apenas resolver este lote, mas formar um procedimento repetível
para os próximos lotes.

## 1. Princípio adotado

A base da ONR não deve receber dado parcial como se fosse completo. Por isso, o
fluxo correto é:

1. preservar o PDF original;
2. fatiar o lote por matrícula;
3. gerar relatório de conferência;
4. revisar amostra e exceções;
5. importar para o Cartório Gestão como matrícula/ficha não conferida;
6. estruturar Indicador Real e Indicador Pessoal a partir da matrícula;
7. só exportar/enviar depois de validado.

CPF/CNPJ, titularidade, imóvel, área, CAR, CCIR, INCRA, atos e proprietários não
devem ser inventados pelo OCR. O OCR pode sugerir campos, mas o dado estruturado
precisa ficar em fila de revisão antes de servir para ONR.

## 2. Entradas usadas

Foram usados dois PDFs em `C:\Users\<usuario>\Downloads`:

- `matriculas 1.pdf`
- `matriculas cont OCR.pdf`

Os dois PDFs já tinham OCR textual embutido. O primeiro estava mais regular. O
segundo exigiu tratamento especial porque o OCR confundiu vários cabeçalhos.

Também foram preservadas cópias dos PDFs originais no acervo próprio do Cartório
Gestão:

- `C:\ProgramData\CartorioGestao\arquivos\ri\lotes_ocr\2026-09-12\matriculas 1.pdf`
- `C:\ProgramData\CartorioGestao\arquivos\ri\lotes_ocr\2026-09-12\matriculas cont OCR.pdf`

Hashes SHA-256 registrados no processamento:

| Arquivo | SHA-256 |
|---|---|
| `matriculas 1.pdf` | `25378C810AC726664296F126F8968F3A828CEC7AF6C16568AC10AF4FAC2FFAF4` |
| `matriculas cont OCR.pdf` | `00B3CCE490AC89727EA111FB67DDC854A0A6637B2C500603A89255C4A52CE7B2` |

## 3. Resultado final do fatiamento

Pasta final:

`C:\Users\<usuario>\Downloads\matriculas_fatiadas_por_matricula_final_corrigida`

Arquivo de controle:

`C:\Users\<usuario>\Downloads\matriculas_fatiadas_por_matricula_final_corrigida\_conferencia_fatiamento.csv`

Resultado:

| Indicador | Resultado |
|---|---:|
| PDFs por matrícula gerados | 485 |
| Páginas totais fatiadas | 1.657 |
| Menor matrícula detectada | 344 |
| Maior matrícula detectada | 4011 |
| Matrículas com alguma correção de OCR no cabeçalho | 267 |
| Matrículas fatiadas que ainda não existem no banco | 239 |

As matrículas abaixo de 1000 encontradas no lote final foram cruzadas com o
banco e existem na base:

| Matrícula | Arquivo | Páginas | Origem no PDF | Observação |
|---:|---|---:|---|---|
| 344 | `Mat 344.pdf` | 1 | `matriculas cont OCR.pdf:542-542` | existe no banco |
| 434 | `Mat 434.pdf` | 2 | `matriculas cont OCR.pdf:489-490` | existe no banco |
| 444 | `Mat 444.pdf` | 2 | `matriculas cont OCR.pdf:525-526` | existe no banco |

## 4. Erros de OCR encontrados e regra aprendida

O segundo PDF apresentou falsos números de matrícula porque o OCR confundiu:

- `LIVRO 02` com matrícula `2`;
- número de ficha/página com parte da matrícula;
- matrícula de quatro dígitos espaçada, por exemplo `3 2 7 6`;
- cabeçalho quebrado, por exemplo `CNM - 11 3 u 59 3`;
- páginas em branco ou verso sem cabeçalho.

Exemplos corrigidos:

| Caso | Leitura ruim | Correção aplicada |
|---|---:|---:|
| `3 2 7 6` | 327 ou sem número | 3276 |
| `1 3 2 7 7` com ficha antes | 277 | 3277 |
| `3 5 3 6` | 353 | 3536 |
| `3 4 6 3` | 346 | 3463 |
| `CNM - 11 3 u 59 3` | 1135 | 3593 |

Regra operacional aprendida: quando o cabeçalho é antigo ou está degradado, a
detecção deve priorizar, nesta ordem:

1. CNM completo `000000.2.000NNNN`;
2. matrícula explícita no cabeçalho;
3. ato `R.xx/NNNN` ou `AV.xx/NNNN`;
4. quatro dígitos espaçados no cabeçalho;
5. sequência com número de ficha antes da matrícula;
6. anexação de página sem cabeçalho à matrícula anterior.

Regra de segurança: não usar automaticamente números de 1 a 99 em lote de
matrículas modernas quando vierem de `LIVRO 02`, `FICHA`, `RUBRICA` ou selo; isso
quase sempre é ruído.

## 5. Scripts criados

### `indexar_pdf_matriculas_ocr.py`

Primeiro indexador simples. Serviu para provar que o OCR textual existia e para
mapear páginas iniciais por matrícula. Ficou útil para PDFs com cabeçalho limpo,
mas foi permissivo demais para o segundo PDF.

### `indexar_pdf_matriculas_ocr_forte.py`

Indexador mais rígido, criado após os falsos positivos. Reconhece CNM, atos,
matrículas pontuadas e matrículas de quatro dígitos espaçadas no cabeçalho.

Arquivo:

`C:\Users\<usuario>\Downloads\CartorioGestao\FERRAMENTAS\indexar_pdf_matriculas_ocr_forte.py`

### `fatiar_pdfs_ocr_por_matricula.py`

Gera um PDF por matrícula, no padrão de nome:

`Mat <numero>.pdf`

Também gera `_conferencia_fatiamento.csv` com:

- número da matrícula;
- nome do PDF criado;
- total de páginas;
- origem exata no PDF original;
- quantidade de correções de OCR aplicadas.

Arquivo:

`C:\Users\<usuario>\Downloads\CartorioGestao\FERRAMENTAS\fatiar_pdfs_ocr_por_matricula.py`

### `auditar_fatiamento_matriculas_ocr.py`

Cruza o CSV final com o banco do Cartório Gestão em modo somente leitura e mede:

- total de PDFs;
- total de páginas;
- menor e maior matrícula;
- matrículas abaixo de 1000;
- matrículas com correção de OCR;
- matrículas fatiadas que ainda não existem no banco.

Arquivo:

`C:\Users\<usuario>\Downloads\CartorioGestao\FERRAMENTAS\auditar_fatiamento_matriculas_ocr.py`

## 6. Por que a importação direta foi suspensa

Uma importação inicial direta foi iniciada, mas foi interrompida porque renderizar
centenas de páginas de uma vez para TIFF ONR ficou demorado demais e sem
progresso visível. A decisão correta foi parar, fatiar os PDFs por matrícula e
criar uma base revisável.

Aprendizado: para lote grande, nunca iniciar importação cega de PDF inteiro.
Primeiro fatiar, auditar e só depois importar em blocos pequenos.

## 7. Próximo fluxo de importação recomendado

Para cada PDF fatiado aprovado:

1. localizar matrícula existente no banco;
2. se existir, anexar o PDF/fichas como imagem/documento da matrícula, sem marcar
   como conferido;
3. se não existir, criar matrícula `ACERVO`, `ATIVA`, `conferido=0`, com origem
   `PDF_OCR`;
4. converter páginas para TIFF 200 dpi, preto e branco, compressão Group 4, se o
   destino for a pasta ONR/CSL2;
5. manter o PDF original fatiado como documento de auditoria;
6. gerar fila de revisão para Indicador Real e Indicador Pessoal.

## 8. Estruturação dos indicadores

### Indicador Real

Deve nascer da matrícula revisada, principalmente de:

- tipo do imóvel: rural ou urbano;
- denominação/endereço;
- área e unidade;
- perímetro/confrontações;
- CAR, CCIR, INCRA, NIRF/SIGEF quando constarem;
- proprietários ativos;
- atos relevantes `R` e `AV`.

### Indicador Pessoal

Deve nascer das partes extraídas da matrícula, principalmente:

- nome;
- CPF/CNPJ quando constar;
- RG/outros documentos quando constarem;
- qualificação;
- papel no ato;
- relação com matrícula e ato;
- proprietário ativo ou histórico.

Ausência de CPF/CNPJ em matrícula antiga deve ser classificada como ausência
documental do acervo, não preenchida por suposição.

## 9. Pendências abertas

- Revisar amostra dos PDFs fatiados finais.
- Tratar as 239 matrículas fatiadas que ainda não existem no banco.
- Decidir regra operacional: importar primeiro as 27 matrículas existentes que
  precisam de complemento de imagem ou já criar também as 239 ausentes como
  `ACERVO` não conferidas.
- Revisar a fila estruturada de Indicador Real/Pessoal antes de gravar qualquer
  CPF/CNPJ, proprietário, área ou ato no banco.
- Depois da conferência, converter para imagem ONR e validar via CSL2.

## 10. Pacote de revisão e importação criado

Foi criado o pacote:

`C:\Users\<usuario>\Downloads\CartorioGestao\SERVIDOR\INSTALAR_CARTORIO_GESTAO\DOCUMENTACAO\PACOTE_IMPORTACAO_OCR`

Ele contém:

- matrículas existentes para importação;
- matrículas ausentes para criação;
- amostras de conferência;
- filas separadas de Indicador Real;
- filas separadas de Indicador Pessoal;
- atos extraídos do OCR;
- simulação detalhada de importação.

Resultado da simulação segura:

| Ação | Matrículas | Imagens/páginas |
|---|---:|---:|
| Pular porque já tem imagens suficientes | 219 | - |
| Importar complemento em matrícula existente | 27 | 226 |
| Criar matrícula acervo e importar imagens | 239 | 768 |
| Total de imagens novas previstas | - | 994 |

O importador preparado é:

`C:\Users\<usuario>\Downloads\CartorioGestao\FERRAMENTAS\importar_fichas_pdf_ocr.py`

Por padrão ele executa somente simulação. A gravação real exige `--executar`.

## 11. Importação controlada das matrículas já existentes

Depois da auditoria automática dos cabeçalhos, foi executada apenas a importação
das matrículas que já existiam no banco:

`01_matriculas_existentes_para_importar.csv`

Resultado da execução:

| Indicador | Resultado |
|---|---:|
| Matrículas avaliadas | 246 |
| Matrículas novas criadas nesta etapa | 0 |
| Matrículas existentes usadas | 246 |
| Matrículas puladas por já terem imagens suficientes | 219 |
| PDFs fatiados copiados para acervo de auditoria | 27 |
| Novas imagens registradas pelo importador | 85 |
| Erros | 0 |

Validação pós-importação:

| Validação | Resultado |
|---|---:|
| Matrículas existentes do CSV cobertas no banco | 246 |
| Matrículas existentes incompletas | 0 |
| Matrículas do CSV que sumiram do banco | 0 |
| Total de imagens em `ri_imagens` | 10.465 |
| Matrículas com imagem no banco | 1.672 |

Prontidão ONR recalculada depois da importação:

| Indicador | Resultado |
|---|---:|
| Matrículas no banco | 1.739 |
| Matrículas sem imagem | 65 |
| Arquivos na pasta ONR | 10.517 |
| Arquivos no padrão ONR | 10.513 |
| Matrículas alcançadas no disco | 1.673 |
| Resolução 200 dpi na amostra | 300/300 |
| Compressão sem perdas na amostra | 300/300 |

Observação: o total de matrículas do banco inclui 39 registros `PDF_OCR` criados
na tentativa anterior interrompida. Nesta etapa controlada não foi criada
matrícula nova.

## 12. Importação controlada das matrículas ausentes

Depois da nova simulação do lote ausente, foi executada a criação das matrículas
que não existiam no banco:

`02_matriculas_ausentes_para_criar.csv`

Resultado da execução:

| Indicador | Resultado |
|---|---:|
| Matrículas avaliadas | 239 |
| Matrículas criadas | 239 |
| Imagens importadas | 768 |
| PDFs fatiados copiados para acervo de auditoria | 239 |
| Erros | 0 |

Todas foram criadas com origem `PDF_OCR_FATIADO`, separada da origem `PDF_OCR`
usada na tentativa anterior.

Validação pós-importação:

| Validação | Resultado |
|---|---:|
| Matrículas ausentes do CSV agora cobertas no banco | 239 |
| Matrículas ausentes incompletas | 0 |
| Matrículas do CSV que não existem no banco | 0 |
| Total final de imagens em `ri_imagens` | 11.233 |
| Total final de matrículas com imagem no banco | 1.911 |

Prontidão ONR recalculada depois dos dois lotes:

| Indicador | Resultado |
|---|---:|
| Matrículas no banco | 1.978 |
| Matrículas sem imagem | 65 |
| Arquivos na pasta ONR | 11.285 |
| Arquivos no padrão ONR | 11.281 |
| Matrículas alcançadas no disco | 1.912 |
| Resolução 200 dpi na amostra | 300/300 |
| Compressão sem perdas na amostra | 300/300 |

Distribuição final de origem das matrículas:

| Origem | Quantidade |
|---|---:|
| `EOFICIO` | 1.699 |
| `PDF_OCR_FATIADO` | 239 |
| `PDF_OCR` | 39 |
| `MANUAL` | 1 |

Conclusão operacional: o lote OCR foi incorporado ao Cartório Gestão e à pasta
ONR local, mas não eliminou as 65 pendências históricas sem imagem, porque essas
matrículas não estavam cobertas por este lote.

## 13. Lista atual das matrículas sem imagem

Foi exportada a lista atual:

`C:\Users\<usuario>\Downloads\CartorioGestao\SERVIDOR\INSTALAR_CARTORIO_GESTAO\DOCUMENTACAO\MATRICULAS_SEM_IMAGEM_ATUAL.csv`

Resultado:

| Tipo | Quantidade |
|---|---:|
| `ACERVO` | 61 |
| `ESTRUTURADA` | 4 |
| Total | 65 |

As últimas pendências da lista incluem:

| Matrícula | Livro | Folha | Tipo | Abertura |
|---:|---|---|---|---|
| 168 | 2-A | - | ACERVO | 2026-07-16 |
| 2195 | 2M | - | ACERVO | 2026-07-21 |
| 2693 | 2-O | 124 | ESTRUTURADA | 2004-05-06 |
| 2782 | 2-P | 19 | ESTRUTURADA | 2005-09-15 |
| 4012 | 2R | fichas | ESTRUTURADA | 2026-07-31 |
| 4013 | 2S | fichas | ESTRUTURADA | 2026-07-31 |

Conclusão: para a ONR, a pendência de completude não é mais o lote OCR já
tratado. A frente crítica passa a ser a localização/digitalização dessas 65
matrículas sem nenhuma página no disco.

Depois da importação da matrícula 4012, a lista foi atualizada para 64
pendências. A 4012 saiu da lista.

Arquivos gerados:

- `MATRICULAS_SEM_IMAGEM_ATUAL.csv`
- `MATRICULAS_SEM_IMAGEM_ARQUIVOS_ENCONTRADOS.csv`
- `MATRICULAS_SEM_IMAGEM_CANDIDATOS_AUDITADOS.csv`
- `MATRICULAS_SEM_IMAGEM_PRIORIZADAS.csv`

Resultado da busca por arquivos candidatos:

| Classe | Resultado |
|---|---:|
| Candidatos encontrados por nome | 89 |
| Candidatos fortes por OCR | 1 |
| Candidatos divergentes | 6 |
| PDFs sem texto OCR | 43 |
| Imagens sem OCR | 11 |
| Candidatos fracos | 28 |

O candidato forte era `C:\Users\<usuario>\Downloads\EXEMPLO_ficha_4012.pdf`, que
foi importado para a matrícula 4012.

Resultado da importação da 4012:

| Indicador | Resultado |
|---|---:|
| Matrículas importadas | 1 |
| Imagens importadas | 6 |
| PDFs copiados para acervo de auditoria | 1 |
| Erros | 0 |

Prontidão ONR após a 4012:

| Indicador | Resultado |
|---|---:|
| Matrículas sem imagem | 64 |
| Arquivos na pasta ONR | 11.291 |
| Arquivos no padrão ONR | 11.287 |
| Matrículas alcançadas no disco | 1.913 |
| Resolução 200 dpi na amostra | 300/300 |
| Compressão sem perdas na amostra | 300/300 |

Lista priorizada das 64 pendências:

| Classe | Quantidade | Ação |
|---|---:|---|
| `URGENTE_RECENTE` | 3 | localizar/redigitalizar primeiro |
| `ESTRUTURADA` | 2 | gerar imagem da ficha estruturada |
| `MUTIRAO_LIVRO_2A` | 55 | digitalizar em sequência pelo Livro 2-A |
| `ISOLADA_ACERVO` | 4 | buscar pelo livro físico/digital indicado |

Urgentes recentes:

| Matrícula | Livro | Tipo | Abertura |
|---:|---|---|---|
| 168 | 2-A | ACERVO | 2026-07-16 |
| 2195 | 2M | ACERVO | 2026-07-21 |
| 4013 | 2S | ESTRUTURADA | 2026-07-31 |

## 14. Matrícula 4013 e regra de conferência por cabeçalho

Em 13/09/2026 foi localizado no Proton Drive o arquivo
`1. RI\LIVRO- 2\FICHAS MATRICULAS\4013\FICHA 4013-assinado.pdf`.

Validação antes da importação:

| Checagem | Resultado |
|---|---|
| Páginas | 12 |
| Cabeçalho textual | Matrícula 4013 |
| CNM textual | 000000.2.0004013-90 |
| Situação no banco antes | matrícula existente, 0 imagens |
| Simulação | 12 imagens a importar, 0 erros |

Resultado da importação:

| Indicador | Resultado |
|---|---:|
| Matrículas criadas | 0 |
| Matrículas existentes usadas | 1 |
| Imagens importadas | 12 |
| PDFs copiados para acervo de auditoria | 1 |
| Erros | 0 |
| Validação posterior | 1/1 matrícula coberta |

Os arquivos ONR foram gravados em `C:\ARPNET\C11\ONR\IMAGENS\00000004`
como `00004013.0001` a `00004013.0012`. Amostra da própria matrícula:
200 dpi e tag TIFF 259 = 4 (CCITT Group 4).

Após a importação, a fila de matrículas sem imagem caiu para 63.

Aprendizado importante: havia arquivos TIFF em
`C:\ProgramData\CartorioGestao\arquivos\ri\fichas\4013`, mas a conferência
visual mostrou que eram da matrícula/CNM 3582 (`00003582.0001` a
`00003582.0010`). A pasta, sozinha, não deve ser usada como prova; a matrícula
deve ser confirmada por cabeçalho, CNM, OCR ou amostra visual antes de qualquer
vínculo no banco ou envio à ONR.

## 15. Pendências urgentes remanescentes após 4013

Depois da 4013, restam duas pendências recentes:

| Matrícula | Livro | Tipo | Abertura | Situação encontrada |
|---:|---|---|---|---|
| 168 | 2-A | ACERVO | 2026-07-16 | Há arquivo Word antigo `IMOVEIS\LIVRO- 2\168.doc`, útil para conferência e indicadores, mas não validado como imagem/ficha ONR. |
| 2195 | 2M | ACERVO | 2026-07-21 | Há DOCX de certidão/inteiro teor em `MATRICULAS ANTIGAS EM DOC\CERTIDÕES\_INTEIRO TEOR\2195.docx`, útil para estruturação, mas não substitui ficha/imagem sem decisão do cartório. |

Regra operacional: certidão e documento textual podem alimentar Indicador Real,
Indicador Pessoal e conferência manual, mas não devem ser importados como
imagem da matrícula para ONR sem validação expressa de que representam a ficha
oficial que será mantida no acervo.

Foram criados os arquivos de apoio:

- `REVISAO_URGENTES_168_2195_INDICADORES.csv`
- `REVISAO_ESTRUTURADAS_2693_2782_INDICADORES.csv`

As matrículas 2693 e 2782 têm estrutura rica no banco, mas continuam sem
imagem vinculada. A 2693 possui DOCX textual/conferido; a 2782 possui PDF de
certidão de inteiro teor. Ambos ajudam a conferir Indicador Real, Indicador
Pessoal e atos, mas não foram usados como imagem ONR.

Decisão pendente do cartório para fichas estruturadas antigas: definir se a
imagem que será enviada à ONR pode ser uma ficha estruturada renderizada a
partir do Cartório Gestão/teor conferido, ou se a regra local será digitalizar
o livro/ficha física. Até essa decisão, manter essas ocorrências na fila de
pendência de imagem.

## 16. Comandos de referência

Reindexar um PDF com regra forte:

```powershell
& 'C:\Users\<usuario>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  'C:\Users\<usuario>\Downloads\CartorioGestao\FERRAMENTAS\indexar_pdf_matriculas_ocr_forte.py' `
  'C:\Users\<usuario>\Downloads\matriculas cont OCR.pdf' `
  'C:\Users\<usuario>\Downloads\CartorioGestao\tmp\onr_ocr\matriculas_cont_ocr.forte4.paginas.jsonl'
```

Fatiar PDFs por matrícula:

```powershell
& 'C:\Users\<usuario>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  'C:\Users\<usuario>\Downloads\CartorioGestao\FERRAMENTAS\fatiar_pdfs_ocr_por_matricula.py' `
  --destino 'C:\Users\<usuario>\Downloads\matriculas_fatiadas_por_matricula_final_corrigida' `
  'C:\Users\<usuario>\Downloads\CartorioGestao\tmp\onr_ocr\matriculas_1.forte2.paginas.jsonl' `
  'C:\Users\<usuario>\Downloads\CartorioGestao\tmp\onr_ocr\matriculas_cont_ocr.forte4.paginas.jsonl'
```

Auditar resultado:

```powershell
& 'C:\Users\<usuario>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  'C:\Users\<usuario>\Downloads\CartorioGestao\FERRAMENTAS\auditar_fatiamento_matriculas_ocr.py'
```
