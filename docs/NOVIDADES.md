# Novidades por versão

O que cada versão publicada trouxe, do mais novo para o mais velho. O detalhe
técnico de cada mudança — o que foi medido, o que se decidiu e por quê — está em
[`tecnico/`](tecnico/README.md).

Uma instalação em uso recebe as versões como pacote `.cgu` (tela
**Atualizações**). Cada pacote leva tudo o que as versões anteriores trouxeram:
não é preciso aplicar uma por uma.

## 3.7.7 — WhatsApp em tempo real, selo gratuito e cancelado, segurança

São 8 mudanças juntadas desde a 3.7.6. A suíte roda na máquina da
integração, e não na do desenvolvimento.

**Atenção ao instalar**
- **O WhatsApp passa a buscar mensagens de 20 em 20 segundos, 24 horas por
  dia**, dentro do servidor, sempre que a caixa-postal estiver configurada. O
  atendente com IA e o aviso de fora do horário continuam dependendo de cada
  um estar ligado na tela; nada disso nasce ligado.
- **Colunas novas no WhatsApp** (arquivos do cliente e entrega da mensagem),
  todas acrescentadas sem mexer no que existe.
- **Selo cancelado no Portal**: na AV-9 da matrícula 2, o botão «O selo … foi
  cancelado no Portal do Selo?» termina o que o script de 28/10 deixou, e em
  seguida «Selar este ato» marcado **isento**, com o motivo.

**WhatsApp**
- A mensagem do cliente chega à tela em segundos, com a hora em que ele a
  mandou (e não a hora em que o sistema a buscou).
- Aviso do Windows, som, título piscando e cartão no canto quando chega
  mensagem nova. Nos balcões que abrem o sistema por `http://<ip>:8765` o
  aviso do Windows depende de política do Chrome ou de `https`; o som, o
  título e o cartão funcionam.
- Foto, PDF, documento, áudio e vídeo do cliente ficam guardados e abrem na
  conversa; a casa também manda arquivo com legenda.
- A entrega aparece em cada mensagem: enviada, entregue, lida ou não chegou.
- A IA passa a conversa para uma pessoa quando o cliente manda arquivo ou
  insiste depois de quatro respostas automáticas; o aviso de passagem não
  conta mais como resposta.
- Horário de atendimento, aviso de fora do horário, respostas prontas e
  conversa parada resolvida depois de alguns dias, na tela do atendente.

**Selo**
- **Item gratuito não paga selo pago**, e ato isento não sela com item
  cobrado ligado a ele. A tela diz qual item é e o que fazer.
- **O selo cancelado no Portal não volta**: a nova tentativa pede outro selo,
  e não o mesmo. Botão na ficha do RI para registrar o cancelamento feito no
  Portal.

**Despesas e cobrança**
- **Todos os usuários cadastram despesa**; o escrevente vê só as que
  cadastrou. Toda despesa continua esperando a autorização do oficial.
- **Unicred**: autenticação confirmada com o modelo da própria Unicred, e o
  token vale 8 horas.

**Segurança**
- A prévia do teor das Notas não roda script vindo do texto gravado.
- Expressões que travavam com textos grandes (a barreira de privacidade da
  ajuda, o editor de modelos, o título da comunicação da CRC) passam a
  responder em milissegundos.
- O «volte para» das telas continua aceitando só caminho do próprio sistema.

## 3.7.6 — protesto em dia com a CRA e a CENPROT, cobrança por boleto, WhatsApp

São 38 mudanças juntadas desde a 3.7.5. A suíte roda na máquina da
integração, e não na do desenvolvimento.

**Atenção ao instalar**
- **Seis retornos à CRA passam de «enviado» para «recusado»** sozinhos, quando
  o esquema abre: são os de 28/10/2026 que a CRA recusou (código 2161) e a tela
  mostrava como enviados. Os atos deles não contam como informados, e não voltam
  à fila sem alguém mandar.
- **O protesto passa a ser no dia útil seguinte ao prazo-limite do devedor**
  (por edital ou pessoal). Antes desta versão o sistema aceitava protestar no
  próprio prazo-limite.
- **Títulos da CENPROT (código TAB)** ganham o apresentante próprio. Um botão
  na tela do XML traz nome, documento e tipo do cadastro do E-Ofício, e o
  clique troca o nome gravado onde ele não era o que foi à Central.

**Protesto**
- **Tríduo**: o protesto se lavra no dia útil seguinte ao prazo-limite (CN-MA
  art. 922, § 1º, e art. 925, § 4º).
- **Retorno à CRA**: o arquivo que a CRA recusa fica **recusado**, com o
  código e o motivo na tela, e com botão para devolver os atos à fila. Ato
  desfeito (selo que não saiu, protesto tornado sem efeito) não entra no
  retorno, e o que já tinha ido aparece num aviso. Ato do mesmo protocolo com
  outra ocorrência fica para o próximo arquivo.
- **XML da CENPROT**: o apresentante TAB vem do próprio título, um bloco por
  solicitante, como o E-Ofício mandava; o aviso, o instrumento e o termo deixam
  de mostrar o documento de outra pessoa.
- **Pedido de protesto da CENPROT** não cria título repetido nem grava
  protocolo fora da forma da casa.

**Dinheiro**
- **Cobrança por boleto** pelo Banco Inter e pela Unicred, do protocolo ao
  depósito prévio.
- **Despesas recorrentes**: o Pix do mês se carrega esperando a autorização do
  oficial; o resto avisa.
- **FERJ** vazio vale 12% no Livro Diário e na NFS-e; a **NFS-e** usa a data do
  recibo como competência.

**Registro de Imóveis**
- **Qualificação assistida** no protocolo, com os dois resultados (positiva ou
  negativa).
- **Selo da conferência de documento eletrônico** (16.42) a partir do
  protocolo, com etiqueta e comprovante em PDF; o subitem de faixa do caixa
  (16.45.33) vai ao TJ como o item (16.45).
- **Certidões do ONR**: a emissão que caiu depois de gravar é amarrada, sem
  gastar outro selo.

**Registro Civil**
- Terceira saída do **pai não declarado**: a mãe não compareceu, averiguação
  não iniciada.
- O que foi cancelado sai das listas de pendência; a remessa do **IBGE** sai
  com o nome certo do CARTINF.ZIP, os seis arquivos e o RC-10.

**Balcão, WhatsApp e avisos**
- **WhatsApp**: tela de conversa como num aplicativo, atalho flutuante com as
  não respondidas e envio por modelo da Meta (desligado de fábrica).
- **Automação**: um e-mail por dia em vez de um por aviso; as rotinas rodam no
  horário e sem abrir janela; o cofre trancado aparece sempre no painel.
- **Portal e avisos**: exigência de qualquer atribuição e «pronto» pela marca
  do balcão. O protocolo do caixa não abre mais com a atribuição RI marcada.
- **Problemas relatados**: exportação mascarada, retorno do desenvolvimento e
  a tarefa agendada que sincroniza a lista.

**Segurança**
- Telas que davam HTTP 500 passam a avisar; robôs se identificam.
- Pastas digitadas no RI e nas Notas só dentro da casa; XML do CENPROT sem
  entidade externa; TLS 1.2 no selador; alertas do CodeQL corrigidos.

## 3.7.5 — automação, despesas, NFS-e, WhatsApp, painéis e as travas novas do balcão

São 45 mudanças juntadas desde a 3.7.4, e a suíte de testes sai inteira
verde no PostgreSQL. As principais, por assunto:

**Rotinas, avisos e segurança**
- **Central de automação**: um despachante único roda as rotinas da casa, com
  avisos em mais de um canal (painel, tarefa, e-mail) e o cofre aberto pela
  senha-mestra. A senha do e-mail dos avisos fica num arquivo próprio, fora do
  cofre, para o aviso «cofre trancado» conseguir sair.
- **Backup no horário** pela automação, com teste de restauração e alerta de
  falha.
- **Robôs** em lista fechada e sempre identificados («a mando de quem agem»);
  exportação em CSV sem fórmula; cota de IA reservada antes de ir à rede.
- O agente de IA lê o banco com papel de leitura, sem superusuário.

**Dinheiro**
- **Despesas**: cadastro, autorização do oficial, pagamento pelo Banco Inter
  (nasce desligado) e conferência no extrato. **Carnê-leão e livro-caixa** do
  titular.
- **NFS-e** no leiaute 1.01: cancelamento aceito pelo XSD, grupo IBS/CBS,
  DANFSe montado pela casa e apuração mensal do ISS.
- **Livro Diário**: o FERJ passa a ser 12% do emolumento.

**Registro de Imóveis**
- **Selar a prenotação pendente** usa o apresentante já gravado — antes o
  selador recusava por «nomes das partes» (problema #145).
- **Qualificação assistida**: a IA rascunha as exigências da nota devolutiva;
  a nota tem lugar claro no protocolo.
- **Busca em texto livre** no teor do acervo, com resumo da situação jurídica.
- **ONR**: certidões no automático (o robô prepara, o escrevente aprova) e
  andamento das prenotações no Acompanhamento de Títulos.

**Registro Civil**
- **Nascimento sem o pai declarado** só se lavra com o termo de alegação de
  paternidade (a mãe indica o suposto pai) ou o termo negativo (Lei nº
  8.560/1992, art. 2º). O termo nasce com o assento, sai para imprimir na
  ficha, e a alegação não remetida ao juiz aparece no painel.
- **Selo da materialização** de certidão de outra serventia (item 14.5.1).
- **Carga da CRC**: a idade da filiação vai só com o número.

**Protesto**
- **Controle do tríduo**: antes do prazo o protesto é recusado; depois dele,
  exige o motivo do atraso, que sai no instrumento.
- **Intimação digital**: comprovante, envio do edital à CENPROT, e a entregue
  sem leitura segue para o edital. O pedido de protesto da CENPROT vira título
  pela tela de pendências.
- **Retorno à CRA** com uma linha por protocolo (título com dois devedores).

**RCPJ e RTD**
- Os **termos de encerramento diário** do mês se juntam num PDF único,
  assinado com o certificado A3 do delegatário. O encerramento continua
  manual, todo dia.

**Balcão e atendimento**
- **WhatsApp** com atendente de IA, etiquetas, setor, transferência e painel do
  prazo; **avisos de andamento** ao cliente por e-mail.
- **Ouvidoria e pesquisa de satisfação**; **portal do cliente** com código de
  acompanhamento no recibo.
- **Painel de senhas** para a TV da recepção e o papel de 80 mm.
- **Leitor de digital** ligado ao cartão de autógrafo; **leitura por IA** de
  documentos de identidade e de veículo nas Notas.
- **Caixa-postal**: autenticar, ler o envelope e confirmar os itens.
- **Nota de exigência** em todas as atribuições, e **tarefa a partir do
  protocolo**.
- **Painel do gestor no celular**, só com números agregados.

**Código público**
- A organização de pastas da serventia saiu do código e da documentação
  técnica: a pasta do malote e a dos comprovantes de gratuidade passam a vir
  só da configuração.

## 3.7.4 — o agente de minutas do RI e das Notas

- **Um quadro «Agente de minutas (IA)»** na ficha da matrícula (Registro de
  Imóveis) e no ato em lavratura (Notas: escritura, procuração, procuração
  previdenciária, substabelecimento, revogação, ata notarial e ata para
  usucapião). Ele lê os documentos que a pessoa marca — os da prenotação e do
  protocolo geral, ou os que ela junta na hora — e prepara o **primeiro texto**
  do ato.
- **Instruções iniciais e de revisão.** A revisão parte do texto como ele está,
  inclusive com o que já foi corrigido à mão, e toda versão fica guardada.
- **Ele não inventa:** o que falta ou está ilegível sai como
  `[COMPLETAR: …]` e na lista de pendências, e a versão mostra de que documento
  e página saiu cada dado importante.
- **Ele não lavra, não numera, não sela e não cobra.** No RI a minuta vai para a
  fila «Minutas a revisar e lavrar»; nas Notas, para o teor do ato em lavratura.
  Quem pratica o ato é a pessoa.
- Usa o provedor de IA configurado pela serventia, com teto diário de pedidos.
  Ver [`tecnico/O_AGENTE_DE_MINUTAS.md`](tecnico/O_AGENTE_DE_MINUTAS.md).

## 3.7.3 — máquina não assina ato, e ninguém assina por ela

- Quando quem está na tela é um **robô** (conta marcada como robô) ou **não há
  ninguém logado**, o campo de quem praticou o ato fica
  **«PENDENTE — assina quem selar»**. Antes saía o nome da substituta ou do
  oficial cadastrado, que não praticaram o ato.
- **Quem sela assina:** ao selar, o nome de quem obteve o selo entra no lugar da
  marca. O selo continua recusando sair em nome de máquina.
- O texto já lavrado não se reescreve: só troca o campo que contém exatamente a
  marca.

## 3.7.2 — revisão de segurança e correções da publicação

- A assinatura do pacote de atualização é conferida de novo na hora de aplicar.
- Estorno de caixa já fechado exige quem aprove.
- O robô não sela; os atos isentos do dia têm controle próprio.
- Os modelos editáveis não aceitam HTML com script.
- A trilha de auditoria passou a ser encadeada.
- Correções de impressão (folha do casamento, testemunhas), do selo da certidão
  eletrônica da CRC, da intimação digital sem PDF e do código de validação do
  selo.
- O repositório público passou a levar os arquivos de dados que o código lê e a
  documentação técnica sanitizada (`docs/tecnico/`).

## 3.7.0 — PostgreSQL

- O banco de dados passou a ser o **PostgreSQL** (antes, SQLite). Ver
  [`REQUISITOS.md`](REQUISITOS.md#o-banco-de-dados-postgresql).
