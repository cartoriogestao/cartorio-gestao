# Relato escrevente — permissões e anexos em usucapião/georreferenciamento

Data: 14/09/2026.

## O relato

A usuária escrevente, com perfil `USER`, informou que não conseguia alterar itens
e não conseguia anexar documentos nos submódulos de processos de usucapião e de
retificação/georreferenciamento.

## O que foi encontrado

1. a escrevente está ativa no sistema com perfil `USER`.
2. Em usucapião, o perfil `USER` já podia juntar peça e marcar conferência, mas
   a tela só recebia nome/caminho/texto. Não havia campo de upload real.
3. Em retificação/georreferenciamento, a abertura de novo processo aceitava
   `ADMIN`, `MANAGER`, `REGISTRADOR` e `ESCREVENTE`, mas não aceitava `USER`.
   Como o cadastro real da casa usa `USER`, a escrevente ficava barrada na rotina.
4. Em retificação/georreferenciamento também não havia seção de peças/documentos
   na ficha do processo, apesar de existir tabela `rt_pecas`.

## O que foi corrigido

1. Usucapião:
   - a ficha agora tem campo de arquivo (`multipart/form-data`);
   - o arquivo enviado é salvo no `archive_root` do Cartório Gestão, em pasta
     própria dos autos;
   - a peça grava nome, caminho, SHA-256 e tamanho;
   - o anexo fica vinculado na tabela geral `attachments`;
   - a ficha mostra links para ver/baixar o arquivo anexado.

2. Retificação/georreferenciamento:
   - o perfil `USER` passou a poder autuar novo processo;
   - foi criada a função de domínio `juntar_peca`;
   - a ficha ganhou seção “Peças e documentos”;
   - o arquivo enviado é salvo no `archive_root` do Cartório Gestão;
   - a peça grava caminho e SHA-256 em `rt_pecas`;
   - o anexo fica vinculado na tabela geral `attachments`;
   - se o tipo da peça for igual a um item da conferência do art. 592, o item é
     marcado como `ATENDIDO` automaticamente.

## Regra aprendida

Quando o sistema fala em “juntar peça” ou “anexar documento”, não basta guardar
um texto com nome de arquivo. O fluxo precisa:

1. aceitar upload real na tela;
2. copiar o arquivo para o repositório do Cartório Gestão;
3. calcular SHA-256;
4. vincular o anexo ao ato/processo/peça;
5. mostrar o anexo depois, com opção de ver e baixar;
6. aproveitar a peça para cumprir automaticamente o item de checklist que ela
   comprova, quando houver correspondência direta.

## Validação feita

- Sintaxe dos arquivos alterados validada com `py_compile`.
- Regra de domínio da retificação validada em SQLite em memória: ao juntar peça
  com tipo igual ao item de conferência, o item mudou para `ATENDIDO`.
- A suíte de tela não pôde concluir neste ambiente porque a `.venv` local está
  incompatível com o Python disponível: a importação de `lxml.etree` falha em
  `crc_soap.py` antes de chegar nestas telas.
