# Novidades por versão

O que cada versão publicada trouxe, do mais novo para o mais velho. O detalhe
técnico de cada mudança — o que foi medido, o que se decidiu e por quê — está em
[`tecnico/`](tecnico/README.md).

Uma instalação em uso recebe as versões como pacote `.cgu` (tela
**Atualizações**). Cada pacote leva tudo o que as versões anteriores trouxeram:
não é preciso aplicar uma por uma.

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
