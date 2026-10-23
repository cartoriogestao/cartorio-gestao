# Plano operacional — digitalização e integração com a ONR

**Serventia:** Serventia Extrajudicial do Ofício Único de Cidade Exemplo/MA  
**CNS:** 000000  
**Sistema:** Cartório Gestão  
**Versão observada na abertura deste plano:** 3.6.85  
**Início do acompanhamento:** 11/09/2026  

## 1. Finalidade

Este documento acompanha, passo por passo, a preparação, o saneamento, a
homologação e a entrada em produção das informações do reRegistro de Imóveis na
ONR. Ele deve registrar não apenas o que foi feito, mas também quem decidiu,
qual evidência foi conferida e qual foi a resposta recebida da ONR.

Nenhuma declaração de completude deve ser assinada antes de a medição da base
ser atualizada e as pendências serem classificadas pelo oficial.

## 2. Arquitetura escolhida

| Informação | Canal | Função do Cartório Gestão |
|---|---|---|
| Imagens das matrículas — Livro 2 | CSL2 para o Bucket do Next Cloud SAS | conferir padrão, localizar faltas e acompanhar o acervo |
| Indicador Pessoal — Livro 5 | IPS para o Firestore do Next Cloud SAS | gerar e conferir a carga inicial |
| Indicador Real — Livro 4 | API da ONR — `POST /v1/indicador/real` | montar, transmitir e acompanhar a fila |
| Atualizações posteriores | cargas incrementais do IPS/CSL2 e API | impedir a criação de novo passivo |

O Cartório Gestão não escreverá diretamente no Bucket nem no Firestore. Essa
transmissão pertence aos programas IPS e CSL2, instalados e mantidos pela ONR.

## 3. Ponto de partida conhecido

A última medição documentada foi realizada em 04/09/2026. Ela não substitui a
medição atual que abre este plano.

| Item | Medição anterior | Situação inicial |
|---|---:|---|
| Matrículas no sistema | 1.701 | **confirmado em 11/09/2026** |
| Última matrícula | 4.013 | **4.014 em 11/09/2026** |
| Matrículas com ao menos uma imagem | 1.627 | **confirmado em 11/09/2026** |
| Matrículas sem imagem | 74 | **confirmado em 11/09/2026 — pendência** |
| Arquivos de imagem | 10.227 | **confirmado em 11/09/2026** |
| Imagens no diretório e padrão de nome do ONR | 10.223 de 10.227 | **4 arquivos de matrícula zero estão na raiz** |
| Números de matrícula alcançados pelo varredor | 1.626 | **confirmado em 11/09/2026; inclui o número zero e requer conciliação com o banco** |
| Resolução 200 × 200 dpi | 300 de 300 | **amostra conforme em 11/09/2026** |
| Compressão sem perdas | 300 de 300 | **amostra conforme em 11/09/2026** |
| Indicadores pessoais/vínculos | 3.992 | **confirmado em 11/09/2026** |
| Pessoas com CPF/CNPJ | 1.173 | **confirmado em 11/09/2026** |
| Pessoas sem CPF/CNPJ | 2.819 | **confirmado em 11/09/2026 — pendência** |
| Alcance temporal | desde antes de 1976 | **confirmado em 11/09/2026: matrícula mais antiga de 1951-04-14 e ato mais antigo de 1948-09-17** |

## 4. Regras de segurança e decisão

1. Não inventar CPF ou CNPJ e não completar documento por semelhança.
2. Não declarar base completa enquanto houver pendência sem classificação.
3. Não converter ou redigitalizar imagens que já estejam conformes.
4. Não transmitir em produção antes da homologação e da conferência por
   amostragem.
5. Tratar `ENVIADO` e `ACEITO` como estados diferentes.
6. Guardar toda resposta relevante da ONR e da Corregedoria com data, remetente
   e assunto.
7. Validar o técnico da ONR pelo código exibido no Ofício Eletrônico antes de
   permitir acesso ao servidor.
8. Credenciais e senhas não devem ser copiadas para este documento.

## 5. Etapas do trabalho

### Etapa 1 — Atualizar a medição

**Objetivo:** obter a fotografia atual da base sem transmitir ou alterar dados.

- [ ] Abrir `Registro de Imóveis → Carga do Next Cloud SAS`.
- [x] Anotar a quantidade total de matrículas — **1.701 em 11/09/2026**.
- [x] Anotar a última matrícula — **4.014 em 11/09/2026**.
- [x] Anotar a quantidade de matrículas sem imagem — **74 em 11/09/2026**.
- [x] Anotar o total de vínculos do Indicador Pessoal — **3.992 em 11/09/2026**.
- [x] Anotar quantos vínculos têm e não têm CPF/CNPJ — **1.173 com documento e 2.819 sem documento em 11/09/2026**.
- [x] Executar a conferência da pasta de imagens — **11/09/2026**.
- [x] Guardar ou copiar o resultado da conferência — **registrado neste plano**.
- [x] Comparar os números com a medição de 04/09/2026 — **a última matrícula passou de 4.013 para 4.014; demais totais principais mantidos na medição informada**.

**Conclusão provisória sobre completude em 11/09/2026:** a base alcança o
marco temporal exigido pelo ONR, pois vai além de 01/01/1976. Porém, ainda
não deve ser declarada como completa para fins de carga, porque existem 74
matrículas sem qualquer imagem no disco e 2.819 vínculos do Indicador Pessoal
sem CPF/CNPJ. Essas pendências precisam ser classificadas antes da assinatura
de qualquer declaração de completude.

**Critério de conclusão:** todos os números acima foram registrados com a data
da medição.

**Anomalia conciliada em 11/09/2026:** a conta por registros indica 1.627
matrículas com alguma imagem (`1.701 - 74`), mas o varredor encontrou 1.626
números nos nomes dos arquivos. A leitura direta do banco e do disco explicou
a diferença: há 1.701 registros de matrícula, mas só 1.699 números distintos
no banco, porque as matrículas 8 e 67 aparecem duplicadas. No disco existe
um número que não pertence ao banco, o número 0, vindo dos quatro arquivos
soltos `00000000.0001` a `00000000.0004`. Os quatro arquivos de matrícula
zero não devem ser enviados ao ONR nem apagados antes de se confirmar sua
origem.

### Etapa 2 — Classificar as matrículas sem imagem

Para cada matrícula listada, marcar uma categoria:

- ficha física localizada e pronta para digitalizar;
- ficha recente ainda não escaneada;
- ficha não localizada;
- matrícula cancelada, inexistente ou cadastrada indevidamente;
- necessita decisão do oficial.

**Critério de conclusão:** nenhuma matrícula permanece apenas como “sem
imagem”; todas possuem categoria, responsável e próxima ação.

**Lista completa apurada no banco em 11/09/2026 — 74 matrículas sem imagem:**

| Grupo | Quantidade | Matrículas |
|---|---:|---|
| Livro 2-A, acervo histórico de 1977-1978 | 55 | 82, 83, 84, 86, 87, 88, 92, 93, 94, 96, 97, 98, 102, 109, 110, 111, 112, 115, 116, 117, 118, 121, 122, 123, 124, 125, 126, 128, 129, 130, 131, 132, 133, 135, 136, 137, 139, 140, 141, 143, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 163, 212 |
| Livro 2-A, acervo com data de 2026 | 1 | 168 |
| Outros acervos sem imagem | 8 | 1555, 1783, 2195, 2728, 2779, 3202, 3247, 3403 |
| Fichas estruturadas sem imagem | 10 | 2693, 2782, 3201, 3214, 3244, 4009, 4010, 4011, 4012, 4013 |

Resumo por tipo: 64 fichas `ACERVO` e 10 fichas `ESTRUTURADA`.

Resumo por período de abertura: 55 dos anos 1970, 1 dos anos 1980, 1 dos anos
1990, 4 dos anos 2000, 5 dos anos 2010 e 8 dos anos 2020. As matrículas
abertas em 2026 sem imagem são 168, 2195, 4009, 4010, 4011, 4012 e 4013.

Leitura complementar em 11/09/2026: as sete matrículas abertas em 2026 não
possuem anexo na tabela `attachments`. Portanto, a pendência não parece ser
apenas arquivo anexado fora do padrão ONR dentro do Cartório Gestão; para a
carga, elas devem ser tratadas como sem imagem digital vinculada.

Nova localização informada em 11/09/2026:
`C:\Users\<usuario>\Proton Drive\<conta>\Shared with me\Cidade Exemplo\7. DIGITALIZAÇAO DE MATRICULAS`.
O cruzamento dessa pasta com as 74 pendências encontrou PDFs para 9 matrículas:
3201, 3202, 3214, 3244, 3247, 3403, 4009, 4010 e 4011.

Classificação provisória:

- Livro 2-A de 1977-1978: `ficha física a localizar no acervo`.
- Matrículas estruturadas e abertas em 2026: `ficha recente ainda não escaneada`
  ou `imagem não gravada no diretório ONR`, a confirmar no balcão/acervo.
- Demais ocorrências antigas fora do bloco 2-A: `ficha física a localizar no
  acervo` ou `necessita decisão do oficial`.

Próxima ação: começar pelas sete ocorrências abertas em 2026, porque são as
mais prováveis de saneamento imediato e impedem a criação de novo passivo.
Depois disso, trabalhar o lote histórico 2-A em sequência física.

### Etapa 3 — Digitalizar somente o que falta

- [ ] Digitalizar todas as páginas da ficha localizada.
- [ ] Usar TIFF, 200 × 200 dpi e compressão sem perdas Group 4.
- [ ] Gravar no diretório e com o nome esperado pelo ONR.
- [ ] Abrir as páginas no Cartório Gestão para conferir legibilidade e ordem.
- [ ] Reexecutar a conferência.

**Critério de conclusão:** zero ficha localizada sem imagem e todas as exceções
restantes formalmente justificadas.

**Procedimento operacional para cada matrícula sem imagem:**

1. Abrir a ficha no Cartório Gestão e confirmar número, livro, folha e data.
2. Localizar a ficha física ou o documento original que representa a matrícula.
3. Digitalizar todas as páginas úteis da matrícula, em ordem, sem pular verso
   com ato, averbação, encerramento, transporte ou observação.
4. Configurar o scanner para imagem em preto e branco, TIFF, 200 × 200 dpi,
   compressão CCITT Group 4 ou equivalente sem perdas.
5. Salvar na pasta ONR conforme o agrupamento de mil em mil. Para matrículas
   de 1 a 999, a pasta é `00000000`; de 1000 a 1999, `00000001`; de 4000 a
   4999, `00000004`.
6. Nomear cada página como `00000000.0000`, com oito dígitos para a matrícula
   e quatro dígitos para a página. Exemplo: primeira página da matrícula 4009
   fica `00004009.0001`.
7. Abrir o arquivo salvo para conferir legibilidade, orientação, corte da folha
   e ordem das páginas.
8. Reabrir `Registro de Imóveis → Carga do Next Cloud SAS` e executar a
   conferência da pasta.
9. Registrar no diário a matrícula saneada, a quantidade de páginas e quem
   conferiu.

**Regra local de acervo do Cartório Gestão:**

O banco e o acervo documental do Cartório Gestão não devem depender da base
nem das pastas da ARPNET/E-Ofício. A pasta ONR continua sendo a origem que o
CSL2 lê para transmitir imagens ao Bucket do Next Cloud SAS, mas o acervo
próprio da serventia deve morar em
`C:\ProgramData\CartorioGestao\arquivos\ri\fichas`, registrado em
`ri_imagens.caminho_interno`, com SHA-256 e tamanho gravados no banco do
Cartório Gestão.

**Primeiro lote recomendado — matrículas abertas em 2026:**

| Matrícula | Pasta ONR | Primeiro arquivo esperado | Observação |
|---:|---|---|---|
| 168 | `C:\ARPNET\C11\ONR\IMAGENS\00000000` | `00000168.0001` | Acervo, sem anexo no banco |
| 2195 | `C:\ARPNET\C11\ONR\IMAGENS\00000002` | `00002195.0001` | Acervo, sem anexo no banco |
| 4009 | `C:\ARPNET\C11\ONR\IMAGENS\00000004` | `00004009.0001` | Estruturada, sem anexo no banco |
| 4010 | `C:\ARPNET\C11\ONR\IMAGENS\00000004` | `00004010.0001` | Estruturada, sem anexo no banco |
| 4011 | `C:\ARPNET\C11\ONR\IMAGENS\00000004` | `00004011.0001` | Estruturada, sem anexo no banco |
| 4012 | `C:\ARPNET\C11\ONR\IMAGENS\00000004` | `00004012.0001` | Estruturada, sem anexo no banco |
| 4013 | `C:\ARPNET\C11\ONR\IMAGENS\00000004` | `00004013.0001` | Estruturada, sem anexo no banco |

**Saneamento executado em 11/09/2026 a partir dos PDFs já digitalizados:**

Foi criado o utilitário
`C:\Users\<usuario>\Downloads\CartorioGestao\FERRAMENTAS\converter_matriculas_pdf_para_onr.py`
para converter PDFs de matrículas para TIFF 200 dpi, bitonal, compressão Group
4, no padrão de pasta e nome exigido pelo ONR. O script simula por padrão e
só grava com `--executar`; ele também bloqueia sobrescrita.

Foram convertidas e gravadas 45 páginas referentes às matrículas 3201, 3202,
3214, 3244, 3247, 3403, 4009, 4010 e 4011. A conferência posterior da pasta
ONR retornou:

- matrículas sem imagem: 65;
- arquivos na pasta: 10.272;
- arquivos no padrão ONR: 10.268;
- matrículas alcançadas no disco: 1.635;
- amostra de resolução: 300 de 300;
- amostra de compressão sem perdas: 300 de 300;
- arquivos fora da pasta correta: 4, os mesmos arquivos de matrícula zero.

Validação direta dos 45 TIFFs gerados: 45 de 45 com resolução 200 × 200 dpi,
unidade polegada e compressão 4, que corresponde a CCITT Group 4.

Após esse saneamento, as matrículas abertas em 2026 que ainda seguem sem
imagem são 168, 2195, 4012 e 4013.

Em 12/09/2026, foram internalizadas no acervo próprio do Cartório Gestão as
páginas que ainda existiam apenas na pasta ONR/ARPNET e não estavam registradas
em `ri_imagens`: 6.553 páginas copiadas, sem falhas. A conferência posterior
mostrou 10.220 páginas no banco próprio e 10.220 com cópia interna em
`arquivos\ri\fichas`. Restam 4 arquivos sem matrícula correspondente e 48
arquivos ambíguos, que não devem ser casados automaticamente.

### Etapa 4 — Classificar ausências de CPF/CNPJ

Para cada ocorrência, usar uma das seguintes classes:

- documento existe na ficha e precisa ser digitado;
- documento não consta do título ou da matrícula histórica;
- pessoa ou vínculo duplicado;
- cadastro importado com erro;
- vínculo não representa titular atual;
- necessita qualificação pelo oficial.

**Critério de conclusão:** toda ausência tem origem conhecida. Somente os
documentos efetivamente presentes no acervo serão digitados.

### Etapa 4-A — Importar lote de matrículas digitalizadas com OCR

**Objetivo:** trazer o lote digitalizado para dentro do Cartório Gestão e usar
o OCR para completar o texto das matrículas e preparar os indicadores, sem
depender do banco nem das pastas da ARPNET.

O lote de OCR deve ser tratado em duas camadas:

1. **Documento/imagem da matrícula:** o PDF ou as páginas TIFF ficam no acervo
   próprio do Cartório Gestão, dentro de
   `C:\ProgramData\CartorioGestao\arquivos\ri`, com cópia incluída no backup.
   Para a ONR, as páginas também precisam existir no padrão do CSL2 em
   `C:\ARPNET\C11\ONR\IMAGENS`, porque é essa pasta que o programa da ONR lê.
2. **Texto OCR:** o texto extraído do PDF não substitui automaticamente a fé
   do livro. Ele entra como teor a conferir, marcado como `conferido = 0`,
   para revisão pelo registrador contra a imagem/livro.

Fluxo recomendado para cada lote:

1. Fazer inventário dos arquivos: quantidade, extensão, tamanho, matrícula
   extraída do nome, duplicidades e arquivos sem número reconhecível.
2. Copiar os PDFs originais para o acervo próprio do Cartório Gestão, mantendo
   SHA-256, origem e data de importação em manifesto.
3. Converter cada PDF para TIFF 200 × 200 dpi, bitonal, compressão CCITT Group
   4, com nome ONR `00000000.0000`, sem sobrescrever arquivo existente.
4. Extrair o texto OCR de cada PDF e gerar uma lista de trabalho com:
   matrícula, arquivo, quantidade de páginas, tamanho, hash, texto extraído e
   situação de confronto contra o sistema.
5. Comparar o OCR com o que já existe em `ri_matriculas`:
   `NOVA`, `SO_NO_DOC`, `AMPLIADA`, `IGUAL`, `DIVERGENTE`, `AMBIGUA` ou
   `VAZIA`.
6. Importar automaticamente apenas `NOVA`, `SO_NO_DOC` e `AMPLIADA`, sempre
   como não conferidas. `DIVERGENTE`, `AMBIGUA` e `VAZIA` ficam para decisão
   manual.
7. Reexecutar:
   - conferência das imagens do Livro 2 para CSL2;
   - conferência do Indicador Pessoal para IPS;
   - conferência do Indicador Real para envio pela API.

**Estruturação dos indicadores a partir do OCR:**

O OCR deve alimentar uma fila de conferência estruturada, não uma carga cega.
Para cada matrícula digitalizada, extrair e revisar:

- dados do imóvel para `ri_matriculas`: tipo de imóvel, rural/urbano, endereço
  ou denominação, área, unidade, confrontações/perímetro, CAR/NIRF/INCRA/SIGEF/
  CCIR/IPTU quando constarem;
- dados de atos para `ri_atos`: R/AV, número, data, natureza do título,
  protocolo/prenotação e teor;
- pessoas e vínculos para `ri_partes`: nome, CPF/CNPJ quando constar, papel,
  qualificação, participação, se foi proprietário e se ainda é proprietário
  ativo.

O Indicador Real da ONR nasce dos campos estruturados da matrícula e dos
proprietários ativos. O Indicador Pessoal nasce dos vínculos em `ri_partes`.
Por isso, a revisão mínima antes de exportar deve confirmar, matrícula por
matrícula, pelo menos: número, imóvel, proprietários ativos, atos principais e
documentos das partes quando o documento constar no título ou na matrícula.

CPF/CNPJ ausente no acervo histórico não deve ser inventado nem preenchido por
semelhança. Deve ser classificado como ausência documental histórica ou ficar
pendente de qualificação pelo oficial.

Critério de conclusão: todos os arquivos do lote estão copiados no acervo
próprio, as páginas necessárias estão no padrão ONR, o texto OCR foi
classificado, e nenhuma matrícula importada permanece sem revisão pendente
identificada.

**Lote OCR localizado em 12/09/2026:**

Arquivos originais em `C:\Users\<usuario>\Downloads`:

- `matriculas 1.pdf`: 795 páginas, OCRmyPDF/Tesseract, 199.016.163 bytes.
- `matriculas cont OCR.pdf`: 862 páginas, OCRmyPDF/Tesseract, 261.005.274
  bytes.

Os dois PDFs foram copiados para o acervo próprio do Cartório Gestão em
`C:\ProgramData\CartorioGestao\arquivos\ri\lotes_ocr\2026-09-12`.

Hashes SHA-256 das cópias internas:

- `matriculas 1.pdf`:
  `25378C810AC726664296F126F8968F3A828CEC7AF6C16568AC10AF4FAC2FFAF4`
- `matriculas cont OCR.pdf`:
  `00B3CCE490AC89727EA111FB67DDC854A0A6637B2C500603A89255C4A52CE7B2`

Foi criado índice OCR por página em
`C:\Users\<usuario>\Downloads\CartorioGestao\tmp\onr_ocr`. O resumo conservador
detectou:

- 1.657 páginas no total;
- 394 matrículas distintas plausíveis, entre 1 e 4.011;
- 280 grupos/páginas sem número confiável no cabeçalho;
- nenhuma das 65 matrículas ainda sem imagem ONR foi coberta por esse lote;
- 223 números detectados não constam hoje em `ri_matriculas`, o que indica que
  o lote pode conter matrículas ainda não importadas para o banco, mas exige
  conferência antes de criar registros.

Decisão operacional: este lote deve alimentar a importação de matrículas e a
estruturação de indicadores, mas não deve ser usado em carga cega. O primeiro
PDF parece mais regular; o segundo tem OCR mais ruidoso e precisa de segmentação
mais cuidadosa antes de gerar páginas ONR ou criar matrículas.

### Etapa 5 — Obter orientação escrita da ONR

Pergunta a encaminhar antes da assinatura do formulário:

> A serventia possui Indicador Pessoal Simplificado e matrículas digitalizadas,
> mas as bases apresentam pendências históricas identificadas e em saneamento.
> O formulário de adesão declara base completa, enquanto a declaração
> alternativa trata de serventia que não possui a base. Qual procedimento e
> documento devem ser adotados para uma base existente, porém parcialmente
> incompleta, inclusive quanto aos registros históricos sem CPF/CNPJ?

- [ ] Enviar a consulta pelo canal oficial.
- [ ] Registrar data, assunto e protocolo, se houver.
- [ ] Arquivar a resposta.
- [ ] Atualizar este plano com a orientação recebida.

### Etapa 6 — Preparar a adesão ao Next Cloud SAS

Somente após as etapas anteriores:

- [ ] Confirmar o nome e o e-mail institucional de contato da serventia.
- [ ] Confirmar a conta Google institucional que controlará o projeto.
- [ ] Definir o técnico responsável, telefone e e-mail.
- [ ] Levantar nome e IP do servidor, IP externo, tipo e velocidade do link.
- [ ] Planejar a liberação estritamente necessária no firewall.
- [ ] Preencher o formulário conforme a resposta da ONR.
- [ ] Conferir todas as declarações antes da assinatura com e-CPF.

### Etapa 7 — Homologar IPS e CSL2

- [ ] Agendar a instalação com a ONR.
- [ ] Validar o código do atendimento no Ofício Eletrônico.
- [ ] Instalar primeiro no ambiente de homologação.
- [ ] Gerar a carga completa do Indicador Pessoal no Cartório Gestão.
- [ ] Executar a carga das imagens pelo CSL2.
- [ ] Conferir erros, rejeições e amostra de registros.
- [ ] Documentar os ajustes realizados.

### Etapa 8 — Homologar o Indicador Real

- [ ] Obter `client_id` e `client_secret` de homologação.
- [ ] Cadastrar as credenciais sem registrá-las neste documento.
- [ ] Testar a conexão.
- [ ] Enviar pequena amostra representativa.
- [ ] Consultar a fila até obter estado final.
- [ ] Corrigir recusas mantendo o identificador do envio.
- [ ] Ampliar a carga somente depois da amostra aceita.

### Etapa 9 — Entrada em produção

- [ ] Obter aprovação do oficial para o GoLive.
- [ ] Confirmar responsáveis pelo acompanhamento diário.
- [ ] Executar a carga inicial em produção.
- [ ] Conferir o resultado da fila e os e-mails de ocorrência.
- [ ] Registrar data e evidências da conclusão.

### Etapa 10 — Rotina permanente

- [ ] Toda matrícula nova deve ter imagem conferida antes do encerramento.
- [ ] Indicador Real deve ser enviado e ter o resultado acompanhado.
- [ ] Ocorrências do IPS e CSL2 devem ser verificadas diariamente.
- [ ] Pendências e rejeições devem ter responsável e prazo.
- [ ] Realizar conferência geral mensal do acervo.
- [ ] Atualizar o Cartório Gestão conforme as novas ITNs da ONR.

## 6. Indicadores de acompanhamento

| Indicador | Meta |
|---|---:|
| Matrículas localizadas com imagem | 100% |
| Imagens fora do padrão | 0 |
| Ausências de CPF/CNPJ sem classificação | 0 |
| Envios do Indicador Real parados sem responsável | 0 |
| Rejeições sem tratamento | 0 |
| Dias sem conferir ocorrências do IPS/CSL2 | 0 |

## 7. Diário de execução

| Data | Etapa | Ação ou decisão | Responsável | Evidência/resultado | Próximo passo |
|---|---|---|---|---|---|
| 11/09/2026 | Preparação | Plano operacional aberto sobre a versão 3.6.85 | Cartório/Codex | Este documento | Executar a Etapa 1 |
| 11/09/2026 | Etapa 1 | Conferidos os totais de imagens e do Indicador Pessoal | Cartório/Codex | 74 de 1.701 matrículas sem página; 1.173 de 3.992 vínculos com documento e 2.819 sem documento | Conferir pasta e padrão das imagens |
| 11/09/2026 | Etapa 1 | Conferida a pasta `C:\ARPNET\C11\ONR\IMAGENS` | Cartório/Codex | 10.227 arquivos; 10.223 no diretório/padrão; 1.626 números alcançados; resolução e compressão conformes em amostra de 300; quatro arquivos de matrícula zero na raiz | Confirmar última matrícula e alcance temporal; depois conciliar a diferença de contagem |
| 11/09/2026 | Etapa 1 | Confirmada a última matrícula e o alcance temporal da base | Cartório/Codex | Última matrícula 4.014; matrícula mais antiga de 1951-04-14; ato mais antigo de 1948-09-17 | Classificar as 74 matrículas sem imagem |
| 11/09/2026 | Etapa 2 | Registrada a lista completa das matrículas sem imagem por leitura direta do banco | Cartório/Codex | 74 ocorrências: 64 acervo, 10 estruturadas; 7 abertas em 2026 | Começar saneamento pelas sete ocorrências de 2026 |
| 11/09/2026 | Etapa 1 | Conciliada a divergência entre registros com imagem e números no disco | Cartório/Codex | Banco tem 1.701 registros e 1.699 números distintos; matrículas 8 e 67 duplicadas; disco tem número 0 fora do banco | Confirmar origem dos quatro arquivos de matrícula zero |
| 11/09/2026 | Etapa 2 | Conferidos anexos das sete matrículas abertas em 2026 sem imagem ONR | Cartório/Codex | Matrículas 168, 2195, 4009, 4010, 4011, 4012 e 4013 com `attachments = 0` | Localizar ficha física/digital original e digitalizar para a pasta ONR |
| 11/09/2026 | Etapa 3 | Convertidos PDFs já digitalizados para o padrão ONR | Cartório/Codex | 45 TIFFs gravados para as matrículas 3201, 3202, 3214, 3244, 3247, 3403, 4009, 4010 e 4011; 45 de 45 validados em 200 dpi e Group 4; pendência caiu de 74 para 65 | Procurar PDFs/imagens das matrículas 168, 2195, 4012 e 4013; depois atacar lote histórico 2-A |
| 12/09/2026 | Etapa 3 | Internalizadas as imagens ONR/ARPNET no acervo próprio do Cartório Gestão | Cartório/Codex | 6.553 páginas copiadas sem falha; banco passou a ter 10.220 páginas em `ri_imagens`, todas com cópia interna | Resolver 48 imagens ambíguas e 4 arquivos sem matrícula; manter busca das 65 matrículas sem imagem |
| 12/09/2026 | Etapa 4-A | Localizado e copiado lote OCR de matrículas em PDF | Cartório/Codex | 2 PDFs copiados para `arquivos\ri\lotes_ocr\2026-09-12`; 1.657 páginas; 394 matrículas plausíveis detectadas; nenhuma cobre as 65 sem imagem ONR | Construir importação assistida do OCR para teor, imagens ONR e indicadores |
| 12/09/2026 | Etapa 4-A | Suspensa a importação direta e fatiado o lote OCR por matrícula | Cartório/Codex | 485 PDFs gerados em `C:\Users\<usuario>\Downloads\matriculas_fatiadas_por_matricula_final_corrigida`; um arquivo por matrícula detectada, com CSV de conferência; casos 3276/3277 corrigidos após falso OCR | Revisar amostra dos PDFs fatiados e depois importar lote aprovado para o Cartório Gestão |
| 12/09/2026 | Etapa 4-A | Documentada a base de aprendizado do lote OCR | Cartório/Codex | Criado `APRENDIZADO_ONR_OCR_MATRICULAS.md`; auditoria: 485 PDFs, 1.657 páginas, matrículas 344 a 4011, 267 com correção de OCR e 239 ainda sem cadastro no banco | Definir regra de importação das 239 matrículas ausentes e gerar fila de Indicador Real/Pessoal |
| 12/09/2026 | Etapa 4-A | Gerado pacote de revisão e simulação de importação | Cartório/Codex | Criado `PACOTE_IMPORTACAO_OCR`; simulação: 219 matrículas seriam puladas por já terem imagens, 27 existentes receberiam 226 páginas e 239 ausentes seriam criadas com 768 páginas; total previsto de 994 imagens novas | Conferir amostras e, após validação, executar importação em lote controlado |
| 12/09/2026 | Etapa 4-A | Auditados os cabeçalhos dos PDFs fatiados | Cartório/Codex | Auditoria automática: 40/40 amostras OK e 485/485 PDFs OK; nenhuma divergência entre `Mat <número>.pdf` e cabeçalho OCR da primeira página | Executar importação controlada das fichas ou revisar amostra visual antes |
| 12/09/2026 | Etapa 4-A | Importadas fichas OCR apenas de matrículas já existentes | Cartório/Codex | 246 matrículas avaliadas; 219 puladas por já terem imagens; 27 PDFs copiados para acervo de auditoria; 85 novas imagens registradas; validação: 246/246 cobertas e 0 erros | Decidir criação das 239 matrículas ausentes como `ACERVO` não conferido |
| 12/09/2026 | Etapa 4-A | Criadas e importadas as matrículas ausentes do lote OCR fatiado | Cartório/Codex | 239 matrículas criadas como `PDF_OCR_FATIADO`; 768 imagens importadas; validação: 239/239 cobertas e 0 erros; prontidão ONR agora mede 1.978 matrículas, 11.285 arquivos e 65 sem imagem | Gerar lista atual das 65 sem imagem e seguir para revisão/estruturação dos indicadores |
| 12/09/2026 | Etapa 2 | Exportada a lista atual de matrículas sem imagem | Cartório/Codex | Criado `MATRICULAS_SEM_IMAGEM_ATUAL.csv`; 65 pendências: 61 `ACERVO` e 4 `ESTRUTURADA`; permanecem 4012 e 4013 sem ficha | Digitalizar/localizar as 65 pendências, priorizando estruturadas e matrículas recentes |
| 12/09/2026 | Etapa 2 | Localizada e importada a ficha da matrícula 4012 | Cartório/Codex | Candidato forte `EXEMPLO_ficha_4012.pdf`; 6 imagens importadas; pendências caíram de 65 para 64; ONR agora com 11.291 arquivos e amostra 300/300 OK | Localizar/redigitalizar 168, 2195 e 4013; depois mutirão Livro 2-A |
| 12/09/2026 | Etapa 2 | Priorizada a lista remanescente de matrículas sem imagem | Cartório/Codex | Criado `MATRICULAS_SEM_IMAGEM_PRIORIZADAS.csv`: 3 urgentes recentes, 2 estruturadas antigas, 55 Livro 2-A e 4 isoladas de acervo | Executar digitalização física dos 64 casos restantes |
| 13/09/2026 | Etapa 2 | Localizada e importada a ficha da matrícula 4013 | Cartório/Codex | Candidato forte `FICHA 4013-assinado.pdf` no Proton Drive; primeira página validada por texto com matrícula 4013 e CNM 000000.2.0004013-90; 12 imagens importadas; validação: 1/1 coberta, 0 erros; pendências caíram para 63 | Localizar/redigitalizar 168 e 2195; depois priorizar 2693 e 2782 |
| 13/09/2026 | Etapa 2 | Detectada pasta interna incorreta em `ri\fichas\4013` | Cartório/Codex | Os arquivos `00003582.0001` a `00003582.0010` dentro da pasta 4013 são visualmente da matrícula/CNM 3582; a matrícula 3582 já possui 10 imagens registradas no banco; nada foi movido ou excluído | Tratar como inconsistência de acervo separado, sem usar esses arquivos para cumprir a 4013 |
| 13/09/2026 | Etapa 2/5 | Criada fila de revisão para 168 e 2195 | Cartório/Codex | Criado `REVISAO_URGENTES_168_2195_INDICADORES.csv`; banco não tem anexos para ambas; documentos textuais encontrados servem para Indicador Real/Pessoal, mas não foram classificados como imagem ONR | Localizar ficha física/digitalizada de 168 e 2195 ou obter decisão expressa do cartório sobre a origem oficial |
| 13/09/2026 | Etapa 2/5 | Criada fila de revisão para 2693 e 2782 | Cartório/Codex | Criado `REVISAO_ESTRUTURADAS_2693_2782_INDICADORES.csv`; 2693 tem DOCX textual conferido; 2782 tem certidão PDF; ambos servem para revisar estrutura, mas seguem sem imagem/ficha ONR | Definir se fichas estruturadas antigas serão impressas/renderizadas como imagem de acervo ou se serão redigitalizadas do livro físico |
| 13/09/2026 | Etapa 5 | Medida a prontidão ONR das 485 matrículas OCR | Cartório/Codex | Criado `PRONTIDAO_ONR_MATRICULAS_OCR.csv`; 52 matrículas já passam na montagem do Indicador Real; 433 ainda têm bloqueios de campos obrigatórios, sobretudo logradouro, número, bairro, cidade, UF, CEP, tipo de imóvel e rural/urbano | Trabalhar saneamento por lote antes de envio amplo; enviar apenas lote pronto se for decisão de homologação/amostra |
| 13/09/2026 | Etapa 8 | Preparado lote de teste ONR com as 52 matrículas OCR prontas | Cartório/Codex | Criado `LOTE_TESTE_ONR_52_PRONTAS.csv` e `PACOTE_TESTE_ONR_52_PRONTAS` com 52 JSONs de Indicador Real; envio pela API não executado porque a credencial ONR local ainda não está configurada (`tem_credencial=False`, ambiente HOMOLOGACAO) | Cadastrar `client_id` e `client_secret` de homologação da ONR no Cartório Gestão e executar o envio do lote |
| 13/09/2026 | Etapa 7/8 | Conferido o manual local de integração ONR | Cartório/Codex | Manual em `C:\Users\<usuario>\Documents\Manualintegracaocartorios.pdf`: para Next Cloud SAS, IPS e CSL2 são instalados no servidor/estação; solicitação/ativação deve ser feita pelo e-mail `integrar-onr@onr.org.br`; prepostos são cadastrados pelo Portal Ofício Eletrônico e ativados pelo Oficial/designado | Solicitar ativação ao ONR e agendar suporte Next Cloud SAS; manter lote de 52 como pacote de teste técnico |
| 13/09/2026 | Etapa 7/8 | Solicitado suporte/acesso ONR por e-mail | Cartório | O cartório informou que já solicitou suporte e acesso por e-mail para ativação/integração ONR | Aguardar retorno do ONR; validar atendimento pelo Ofício Eletrônico; instalar/configurar IPS e CSL2; executar primeiro teste com lote controlado |

## 8. Documentos relacionados

- `O_NEXT_CLOUD_SAS_DO_ONR.md` — decisão técnica e diagnóstico.
- `COMO_USAR_O_NEXT_CLOUD_SAS.md` — roteiro de adesão e operação.
- `O_ONR_CONSTRUIDO.md` — integração da API e Indicador Real.
- `APRENDIZADO_ONR_OCR_MATRICULAS.md` — base de aprendizado do fatiamento,
  auditoria e importação assistida dos PDFs OCR de matrículas.
- `FONTES_EXTERNAS/onr_ri/manual_integracao_cartorios.pdf` — manual oficial
  usado na implementação.
- `FONTES_EXTERNAS/onr_nextcloud/` — formulários e instruções oficiais.
