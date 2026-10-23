# Encaminhamento de lote para inclusão em acervo — Registro de Imóveis

**De:** Serventia Extrajudicial do Ofício Único de Cidade Exemplo/MA — CNS 000000
**Para:** Suporte técnico E-Ofício — Automação Cartorária/MA
**Assunto:** Inclusão em acervo de 429 matrículas do Livro 2 — Registro Geral, em JSON

---

Prezados,

Conforme confirmado por essa equipe de que a importação aceita **número de matrícula já existente** e a
**inclusão de registro de acervo**, encaminhamos o primeiro lote de matrículas digitalizadas desta
serventia, no layout `modelo_json_registro_imovel`, schema_version 1.0.

## Resumo do lote

| | |
|---|---|
| Matrículas processadas | 429 |
| Faixa | 3.440 a 4.011 (Livro 2 — Registro Geral) |
| Páginas digitalizadas de origem | 1.659 |
| **Prontas para importar** | **375** |
| Pendentes de conferência | 54 |
| Atos (registros e averbações) | 769 |
| Partes qualificadas | 672, das quais 506 com CPF ou CNPJ conferido pelo dígito verificador |
| Teor | 3,6 MB de texto, íntegro, sem corte |

Distribuição: 111 imóveis rurais com área em hectares e 286 lotes urbanos com área em metros quadrados,
boa parte oriunda de procedimento de REURB-S.

## Como o lote está organizado

O envio vem **separado em dois conjuntos**, para que a carga possa começar de imediato pelo que já está
íntegro:

- **`prontas/` — 375 arquivos.** Todos os campos aplicáveis do modelo preenchidos, nenhum vazio.
- **`pendentes/` — 54 arquivos.** Mesma estrutura, com ao menos um campo que a digitalização não permitiu
  ler com segurança. Cada um está identificado no arquivo de conferência.

Além disso:

- `lote_prontas.json` — os 375 assentos íntegros em um único array, caso a importação aceite lote;
- `indice.csv` — índice completo, com a situação de cada matrícula e os campos faltantes;
- `CONFERENCIA.csv` — fila de trabalho da serventia, com o trecho do teor onde cada pendência se resolve.

## Verificações feitas

**Todas as 429 matrículas passaram no dígito verificador do CNM** (ISO 7064 MOD 97-10). Nenhuma divergiu,
nenhuma está duplicada, nenhuma ficou fora da faixa do acervo.

**Os 506 CPF e CNPJ informados passaram no respectivo dígito verificador.** Documento que não passou foi
descartado, e não enviado como leitura provável.

**As datas foram lidas da linha de abertura da ficha**, e não da primeira data do texto — que costuma ser
a do título de origem. Como conferência adicional, comparamos cada data com a das matrículas
numericamente vizinhas: 9 destoam mais de dez anos da vizinhança e estão marcadas para conferência.

**Conferimos arquivo por arquivo**: o conjunto de chaves de cada JSON é idêntico ao do modelo enviado por
vocês, sem chave a mais nem a menos, com `tipo_ato` restrito a REGISTRO/AVERBACAO, data em ISO,
documento sem máscara e `matricula_numero` do ato igual ao do imóvel.

## Sobre o campo `folha`

Vai **vazio nas 429, por não se aplicar**. O Livro 2 desta serventia é mantido em sistema de fichas, no
qual o assento é identificado pelo número da matrícula. Folha é coordenada de livro encadernado e não
tem correspondente aqui. Não é falha de leitura nem pendência a resolver.

## Ressalvas

**Refizemos o reconhecimento óptico de 71 matrículas.** A camada de texto que veio dentro do PDF havia sido
produzida por um OCR que imprime o cabeçalho da ficha por cima da qualificação das partes, o que impedia a
leitura. Rasterizamos as 223 páginas dessas matrículas a partir da imagem, recortamos a faixa do cabeçalho
e reconhecemos de novo. Resultado: 39 delas passaram a ter partes identificadas, 65 ganharam área e 52
ganharam os atos. Nessas 71, o `teor` entregue é o do reconhecimento refeito, de qualidade superior.

**Nas 54 pendentes, o que falta é:** partes não reconhecidas em 12, área não localizada em 32 e descrição
do imóvel não localizada em 22 — com sobreposição entre elas. Em todos os casos o **teor está completo**,
o que permite o preenchimento por conferência humana sem recorrer ao livro físico.

**As partes extraídas não substituem conferência.** São leitura automática de documento digitalizado, não
conferência de escrevente. Sugerimos importá-las como dado sujeito a revisão. A grafia dos nomes foi
uniformizada dentro do lote quando o mesmo CPF aparecia com leituras diferentes — 30 ocorrências, todas
registradas no arquivo de conferência.

**Não incluímos como partes** quem assina o memorial descritivo (responsável técnico do georreferenciamento)
nem quem lavra o ato, embora apareçam qualificados no texto da ficha.

**Em 7 matrículas a parte foi reconstruída pelo documento.** Nelas o carimbo da serventia caiu sobre o
nome e a leitura saiu partida, mas o CNPJ ou CPF permaneceu legível e íntegro. Como esse número passa no
dígito verificador e já aparece, lido com clareza, em outras matrículas deste mesmo lote, adotamos o nome
canônico correspondente em vez de deixar a parte vazia. Estão marcadas na fila de conferência.

## Perguntas

1. Confirmam a preferência por arquivos individuais ou por lote único?
2. Há ambiente de homologação para rodarmos as 375 antes da carga em produção?
3. A importação devolve retorno por matrícula, indicando quais entraram e quais falharam?
4. A inclusão em acervo consome selo? Em caso positivo, como informar o selo já lançado na ficha —
   os selos originais estão preservados no `teor`.

Ficamos no aguardo para prosseguir com os lotes seguintes do acervo.

Atenciosamente,

Serventia Extrajudicial do Ofício Único de Cidade Exemplo/MA
