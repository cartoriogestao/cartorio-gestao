# Roteiro de digitalização das matrículas pendentes para ONR

Atualizado em 13/09/2026.

## 0. Decisão operacional atual

Em 13/09/2026 o cartório decidiu trabalhar primeiro com o acervo que já está
digitalizado/OCR e deixar as matrículas ainda sem imagem para etapa posterior.

Também foi informado que o suporte/acesso ONR já foi solicitado por e-mail.

Enquanto o ONR não retorna:

- manter as 63 pendências sem imagem em fila separada;
- não bloquear o saneamento das matrículas OCR já disponíveis;
- usar o lote das 52 matrículas prontas como referência de teste/homologação;
- continuar preparando Indicador Real e Indicador Pessoal das demais matrículas
  OCR em fila de revisão.

## 1. Regra de ouro

Não importar como imagem ONR apenas porque existe um arquivo com o número da
matrícula. Antes de importar, confirmar pelo menos um destes elementos:

- cabeçalho da ficha com o número da matrícula;
- CNM correspondente;
- livro/folha/data compatíveis com o banco;
- conferência visual da primeira página.

Certidões de inteiro teor, arquivos Word e transcrições digitadas servem para
revisar Indicador Real, Indicador Pessoal e atos. Elas não devem substituir a
imagem/ficha da matrícula sem decisão expressa do cartório.

## 2. Ordem de ataque

### Prioridade 1 — recentes ainda sem imagem

1. Matrícula 168 — Livro 2-A — abertura 16/07/2026.
   - Há texto em `IMOVEIS\LIVRO- 2\168.doc`.
   - Usar o texto para revisar indicadores.
   - Ainda precisa localizar ficha/imagem oficial ou redigitalizar.

2. Matrícula 2195 — Livro 2M — abertura 21/07/2026.
   - Há certidão/inteiro teor em DOCX.
   - Usar a certidão para revisar indicadores.
   - Ainda precisa localizar ficha/imagem oficial ou redigitalizar.

### Prioridade 2 — estruturadas antigas sem imagem

1. Matrícula 2693 — Livro 2-O — folha 124 — abertura 06/05/2004.
   - Há DOCX textual/conferido.
   - Banco possui estrutura com partes e atos.
   - Falta definir se será renderizada ficha estruturada ou redigitalizada a ficha física.

2. Matrícula 2782 — Livro 2-P — folha 19 — abertura 15/09/2005.
   - Há PDF de certidão de inteiro teor e documentos textuais.
   - Banco possui estrutura com partes e atos.
   - Falta definir se será renderizada ficha estruturada ou redigitalizada a ficha física.

### Prioridade 3 — mutirão Livro 2-A

Digitalizar em sequência as 55 matrículas do Livro 2-A indicadas em
`MATRICULAS_SEM_IMAGEM_PRIORIZADAS.csv`.

Fluxo recomendado:

1. Separar o livro/ficha física por faixa.
2. Digitalizar em PDF por matrícula, não por lote gigante.
3. Nomear como `Mat <numero>.pdf`.
4. Conferir primeira página antes da importação.
5. Importar para o Cartório Gestão e gerar TIFF ONR.
6. Regenerar `MATRICULAS_SEM_IMAGEM_ATUAL.csv`.

### Prioridade 4 — isoladas de acervo

Resolver após o mutirão sequencial, pois exigem busca individual por livro,
folha ou origem.

## 3. Padrão técnico de imagem ONR

- TIFF.
- 200 x 200 dpi.
- Compressão CCITT Group 4.
- Pasta por milhar no padrão já usado pelo importador.
- Nome no formato `00000000.0001`, onde os oito primeiros dígitos são o número
  da matrícula com zeros à esquerda.

## 4. Conferência pós-importação

Após cada lote:

1. Validar no banco se a matrícula ficou com imagem.
2. Confirmar que os arquivos apareceram na pasta ONR correta.
3. Conferir amostra de DPI e compressão.
4. Atualizar o diário do `PLANO_ONR_PASSO_A_PASSO.md`.
5. Regenerar a lista de pendências.

## 5. Arquivos de apoio

- `MATRICULAS_SEM_IMAGEM_ATUAL.csv`
- `MATRICULAS_SEM_IMAGEM_PRIORIZADAS.csv`
- `REVISAO_URGENTES_168_2195_INDICADORES.csv`
- `REVISAO_ESTRUTURADAS_2693_2782_INDICADORES.csv`
- `APRENDIZADO_ONR_OCR_MATRICULAS.md`
