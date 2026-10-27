# Novidades por versão

O que cada versão publicada trouxe, do mais novo para o mais velho. O detalhe
técnico de cada mudança — o que foi medido, o que se decidiu e por quê — está em
[`tecnico/`](tecnico/README.md).

Uma instalação em uso recebe as versões como pacote `.cgu` (tela
**Atualizações**). Cada pacote leva tudo o que as versões anteriores trouxeram:
não é preciso aplicar uma por uma.

## 3.7.5 — automação, despesas, NFS-e, WhatsApp, painéis e as travas novas do balcão

São 44 mudanças juntadas desde a 3.7.4. As principais, por assunto:

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
