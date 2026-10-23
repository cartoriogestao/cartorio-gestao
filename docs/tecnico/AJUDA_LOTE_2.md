# Ajuda do sistema — Lote 2: diagnóstico controlado

O Lote 2 dá à Ajuda capacidade de investigar sem lhe dar capacidade de
alterar o CartorioGestao. Ele tem duas ferramentas: leitura limitada do código
relacionado a um problema e extração local de texto de arquivos entregues pelo
operador.

## O que passa a ser possível

1. Um problema registrado pode ser relacionado à tela e ao arquivo que a
   implementa. A Ajuda recebe um trecho numerado em torno da função ou da
   linha indicada no rastro do erro.
2. O operador pode anexar texto, log, Markdown, CSV, JSON, XML, código-fonte ou
   PDF com texto a uma pergunta. A resposta volta na mesma tela.
3. A consulta registra qual arquivo local foi analisado, seu tamanho e a sua
   impressão SHA-256. O diagnóstico estrutural registra arquivo, linhas e
   SHA-256 do código efetivamente lido.

## Limites de segurança

- O arquivo recebido é processado em memória e não é executado.
- Arquivos de banco, programas, pacotes compactados e formatos não previstos
  são recusados.
- O limite por arquivo é 4 MB; o texto extraído é limitado a 30 mil
  caracteres e o PDF a 80 páginas.
- O nome original e o binário ficam na serventia. Para a consulta externa vai
  somente texto extraído, sem o nome do arquivo.
- Esse texto ainda atravessa integralmente a barreira obrigatória do Lote 1.
  Dados pessoais, sensíveis, registrais e segredos são substituídos antes da
  rede.
- O conteúdo anexado é tratado como dado não confiável. Instruções escritas
  dentro dele não concedem permissão nem são executadas.
- A leitura de código só alcança arquivos conhecidos, dentro da pasta do
  CartorioGestao, e nunca testes, ferramentas ou instaladores.

## O que continua proibido

O Lote 2 não grava código, não executa arquivo recebido, não instala pacote,
não atualiza o programa, não fecha problema e não pratica ato de cartório. A
resposta é diagnóstico assistido: deve separar evidência de hipótese e continua
sujeita à conferência humana.

Qualquer capacidade de propor alteração aplicável, testar uma cópia ou instalar
atualização pertence ao lote seguinte e exige aprovação, isolamento, reversão e
auditoria próprios.
