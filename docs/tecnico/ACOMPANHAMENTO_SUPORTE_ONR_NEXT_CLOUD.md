# Acompanhamento do suporte ONR - Next Cloud SAS, IPS e CSL2

Atualizado em 13/09/2026.

## 1. Situação atual

O cartório informou que já solicitou por e-mail ao ONR o suporte/acesso para
integração.

Finalidade da solicitação:

- ativação/integração da serventia ao ONR pela infraestrutura Next Cloud SAS;
- instalação/configuração do IPS para Indicador Pessoal Simplificado;
- instalação/configuração do CSL2 para imagens do Livro 2;
- orientação de homologação/teste antes de produção.

## 2. Base local já preparada

### Imagens

- As imagens já tratadas ficam em `C:\ARPNET\C11\ONR\IMAGENS`.
- O Cartório Gestão também mantém cópia própria em
  `C:\ProgramData\CartorioGestao\arquivos\ri\fichas`.
- O lote OCR já foi fatiado, importado e convertido para TIFF 200 dpi / CCITT
  Group 4 quando aplicável.

### Matrículas OCR

- Total do lote OCR trabalhado: 485 matrículas.
- Matrículas OCR com Indicador Real pronto pela validação do Cartório Gestão:
  52.
- Matrículas OCR com bloqueios de estrutura: 433.

Arquivos relacionados:

- `LOTE_TESTE_ONR_52_PRONTAS.csv`
- `PACOTE_TESTE_ONR_52_PRONTAS`
- `PRONTIDAO_ONR_MATRICULAS_OCR.csv`
- `FILA_INDICADORES_OCR\indicador_real_revisao.csv`
- `FILA_INDICADORES_OCR\indicador_pessoal_revisao.csv`
- `FILA_INDICADORES_OCR\atos_revisao.csv`

## 3. Manual local conferido

Manual analisado:

`C:\Users\<usuario>\Documents\Manualintegracaocartorios.pdf`

Pontos relevantes do manual:

- o acesso humano ao Portal Ofício Eletrônico/ONR é feito com certificado
  digital ICP-Brasil A3;
- prepostos devem se cadastrar no Portal Ofício Eletrônico e serem ativados
  pelo oficial/designado;
- para infraestrutura Next Cloud SAS, o Indicador Pessoal Simplificado é
  enviado pela aplicação IPS;
- as imagens das matrículas do Livro 2 são enviadas pela aplicação CSL2;
- a solicitação de ativação/integração deve ser feita ao ONR;
- o ambiente de homologação deve ser usado antes da produção;
- bases parciais/incompletas não devem ser tratadas como carga completa.

## 4. Próximos passos quando o ONR responder

1. Confirmar se o atendimento é realmente do ONR.
   - Usar o módulo de validação de atendimento no Ofício Eletrônico quando o
     suporte informar código de segurança.

2. Confirmar qual modalidade será ativada.
   - Next Cloud SAS / IPS / CSL2.
   - Ou Web Service próprio, se o ONR orientar outro caminho.

3. Instalar/configurar os aplicativos indicados.
   - IPS para Indicador Pessoal Simplificado.
   - CSL2 para imagens do Livro 2.

4. Informar ao suporte o caminho local das imagens.
   - `C:\ARPNET\C11\ONR\IMAGENS`

5. Executar teste/homologação.
   - Primeiro com lote controlado.
   - Usar as 52 matrículas prontas como referência de teste técnico.

6. Conferir ocorrências.
   - Guardar e-mails/relatórios do ONR.
   - Registrar rejeições e motivo.
   - Atualizar o plano de saneamento.

7. Somente depois, solicitar/autorizar produção.

## 5. Pendências internas antes de carga completa

Mesmo com suporte ONR solicitado, a carga completa ainda depende de:

- concluir as 63 matrículas que ainda estão sem imagem;
- revisar Indicador Pessoal com CPF/CNPJ;
- sanear as 433 matrículas OCR que ainda não passam na validação de Indicador
  Real;
- decidir a regra das fichas estruturadas antigas sem imagem;
- registrar evidências de homologação antes do GoLive.

## 6. Registro de eventos

| Data | Evento | Evidência | Próxima ação |
|---|---|---|---|
| 13/09/2026 | Cartório informou que solicitou suporte/acesso ONR por e-mail | Informação prestada nesta conversa | Aguardar retorno do ONR e validar atendimento pelo Ofício Eletrônico |
