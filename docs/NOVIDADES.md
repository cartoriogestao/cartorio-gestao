# Novidades por versão

O que cada versão publicada trouxe, do mais novo para o mais velho. O detalhe
técnico de cada mudança — o que foi medido, o que se decidiu e por quê — está em
[`tecnico/`](tecnico/README.md).

Uma instalação em uso recebe as versões como pacote `.cgu` (tela
**Atualizações**). Cada pacote leva tudo o que as versões anteriores trouxeram:
não é preciso aplicar uma por uma.

## 3.7.15 — Parcela no caixa bancário, avisos falsos do Protesto, dispositivo lembrado e a suíte verde

Desde a 3.7.14.

> **Para a instalação que está na 3.7.10:** a 3.7.14 não chegou a ser publicada como pacote, e
> esta versão leva tudo o que veio desde a 3.7.10 (as novidades da 3.7.11 à 3.7.14, abaixo). O
> pacote para ela se gera com `--desde v3.7.10`:
> `python tools/publicar_versao.py --versao 3.7.15 --desde v3.7.10 --chave <chave do oficial>`.

**Protesto**
- A verificação da CRA não cobra mais a remessa em feriado (nacional ou da lista de feriados locais): em 02/11 ela avisou duas vezes que «ninguém baixou a remessa».
- A lista vazia da CENPROT (o 404 de «nada pendente») fica no log das Centrais como informação, e não como aviso. Os 32 avisos de 27/10 a 09/11 eram todos isso.
- Na ficha do título, o botão «Lançar …» fica no fim do formulário, depois do quadro de cobrança (protocolo, itens a selar, pagador).
- A escolha da faixa do item da tabela de emolumentos (17.1, 17.4) ocupa a largura da tabela, e a descrição do item sai inteira.
- O apontamento feito pela ficha do título da CRA já gera o arquivo de andamento do apresentante, sem enviar: quem sobe na Central continua sendo o envio, até as 11:30.

**Caixa e Parcela**
- A conciliação da Parcela usa a listagem autenticada do estabelecimento: o link pago ou expirado não fica mais aberto. O recebimento confirmado entra sozinho, uma vez só, no caixa bancário da serventia (separado das gavetas), com a data do pagamento.
- Recebimento manual já lançado na mesma data, forma e protocolo bloqueia a entrada automática; conciliar com o que já existe pede a confirmação do oficial ou do gerente, com justificativa.
- Pix e débito na maquininha deixam de ser recusados («instalments must not be less than 1»), e a recusa da maquininha aparece na tela com o motivo.
- Antes de enviar uma despesa ao Inter, o ordenador confere o destinatário um a um.

**Acesso**
- «Lembrar este dispositivo por 30 dias» depois da senha e do código de duas etapas. A senha continua obrigatória. Funciona só com o sistema em HTTPS; no acesso por HTTP da rede local a opção não se aplica. Orientações em `docs/DISPOSITIVOS_LEMBRADOS.md`.

**Servidor reserva**
- O código da verificação em duas etapas entra no servidor reserva, que é só de leitura.
- Fora do Windows, o perfil do LibreOffice fica na pasta de dados, e não numa pasta chamada «C:\ProgramData» dentro da pasta atual.

**Testes**
- A suíte inteira passa numa máquina com LibreOffice, Chrome e PostgreSQL instalados, como o servidor: 18.507 testes, nenhuma falha.

## 3.7.14 — protesto só depois do caixa, Parcela Express na maquininha e revisão no registro civil

Desde a 3.7.13.

**Protesto**
- Desistência e cancelamento só se efetivam depois que o emolumento entra no caixa. O clique da CRA guarda o pedido e não lavra; o item quitado no protocolo geral vale como pagamento.
- No título diferido, a desistência depois do apontamento deixa o emolumento 17.4 devido, sem cobrar sozinha e sem selar.
- A intimação lavrada sem selo aparece no alto de Avisos e na ficha: o clique sela e deixa o emolumento devido. Os lavrados sem selo se selam até 10 por clique.
- Página nova com os desistidos e cancelados sem selo, separando o que a casa lavrou do que veio do E-Ofício.
- O título emitido no Brasil em moeda estrangeira tem a marca «Emitido no Brasil — sem tradução (art. 10, § 3º)» e não exige tradução; a tela avisa para conferir a estipulação pelo art. 13 da Lei 14.286/2021.
- Gerar o XML P ou D da CENPROT já baixa o arquivo; a credencial da CENPROT vem da pasta das credenciais.

**Caixa**
- Parcela Express: Pix e cartão vão para a maquininha (código da maquininha na configuração); o boleto continua no link. O pagamento confirmado entra sozinho no caixa geral, e quitar por fora pede confirmação. O menu passa a se chamar «Pix, boleto e cartão».

**Registro civil**
- Revisão com IA antes de lavrar, no mesmo lugar do RI e das Notas, aproveitando a primeira leitura sem reler a imagem.
- O lugar do nascimento escrito (hospital, posto, domicílio, aldeia, fazenda) vira o código do SIRC.
- Os assentos importados do E-Ofício ganham as colunas que estavam vazias (hora, local, causa, CPF e outras), e a certidão e a CRC saem completas. O nascimento cujo município já está escrito sai da quarentena da CRC.

**Registro de Imóveis**
- A qualificação cita as fontes normativas e prepara o rascunho da nota devolutiva no modelo da casa.

**Atendimento e treinamento**
- Atendimentos reorganizados e treinamento do escrevente, da recepção até a entrega.

**Servidor e sistema**
- Servidor reserva no macOS, só de leitura, com cópia do banco e dos arquivos do principal; assume se o principal cair. Roteiro em `docs/SERVIDOR_RESERVA_MACOS.md`.
- A IA gasta menos: reaproveita o OCR já feito e não reenvia pedido incerto.
- Sai a faixa que mandava migrar o banco: a casa já está no PostgreSQL.
- O reinício recusa deixar um servidor antigo vivo na mesma porta.

## 3.7.13 — a atualização grava só o backup do banco

Desde a 3.7.12.

**Atualização**
- Antes de aplicar a versão nova, a cópia é a do banco, a mesma do backup do dia. As digitalizações não são copiadas de novo: ficam na pasta de dados e no backup completo da semana. A cópia do programa anterior, para voltar se a versão nova não responder, continua.

## 3.7.12 — o boleto sem a janela do expediente por cima, e a Parcela Express no protocolo

Desde a 3.7.11.

**Caixa**
- Depois do fim do expediente a faixa vermelha continua pedindo para fechar o caixa, mas a janela não cobre mais as telas do boleto. O «Emitir no banco» e a resposta do banco ficam visíveis. O caixa de um dia anterior ainda aberto continua trancando as telas.
- A Parcela Express emite Pix, boleto e cartão no protocolo. O login de produção usa o host do portal.

**RTD**
- O registro com valor declarado pode selar pelo caminho com valor. A chave nasce desligada.

**Protesto**
- O título em moeda estrangeira exige a tradução por tradutor público, e o registro a cita.
- O termo e o instrumento do cheque dizem o banco sacado, o motivo e a data da devolução.
- Não há gratuidade, só o diferimento. A exceção é o mandado de gratuidade da justiça, com o mandado anexado.

**Robô**
- A conta de robô abre a retificação cadastral da matrícula e a ficha da tarefa.

**Base normativa**
- A minuta, a revisão prévia e o ônus do RI recebem os artigos do ato. O texto da lei chega inteiro ao modelo.

## 3.7.11 — o ensaio de atos nas Notas, no RI, no Protesto e no RTD/RCPJ, a receita no selo, a Ajuda que volta a ler o sistema e a base normativa

São 91 mudanças juntadas desde a 3.7.10 (#251 a #344). A suíte inteira rodou em partes no layout novo, na
máquina da integração: 18.333 verdes, nenhuma falha. O ensaio de atos pedido pelo oficial em
01/11/2026 — praticar pelas telas os atos que a lei prevê e conferir o que sai — passou pelas Notas, pelo
Registro de Imóveis, pelo Protesto e pelo RTD/RCPJ, e cada defeito que ele achou foi consertado com a
decisão do oficial. Os relatórios estão em `docs/ensaio_de_atos/`.

**Atenção ao instalar**
- **O carnê-leão reconhece a receita no SELO do ato, e não mais no pagamento** (decisão do oficial de
  03/11/2026). O item pago antes conta no dia do selo; o selado antes e pago depois conta no pagamento; o
  pago e nunca selado entra em 31/12. A diligência, o arquivamento por folha e a publicação, quando não
  vão marcados em ato nenhum, contam no primeiro selo do mesmo protocolo depois do pagamento. A tela do
  carnê-leão mostra, mês a mês, a diferença em relação ao critério de antes.
- **Colunas novas** nas partes das Notas, no caixa, no RCPJ, na retificação e na usucapião nascem
  sozinhas na primeira abertura.
- **O termo do protesto** só diz «pagamento a posteriori» no título de emolumentos diferidos; no pago no
  balcão a frase não sai. A frase virou peça própria, que se edita na tela de Modelos.
- **A qualificação assistida do RI está suspensa** até a base normativa ser validada (#310).
- **A Ajuda responde pela documentação que vem com o sistema** (`docs/`) e pelas **regras da casa**
  (`docs/REGRAS_DA_CASA.md`). A pasta `DOCUMENTACAO\` e o `CLAUDE.md` que ficaram no servidor, da
  instalação antiga, **deixam de ser lidos**. Ajuda → Configurar avisa se os documentos não chegaram.
- **A pasta nova `base_normativa/`** traz o Código de Normas do TJMA, o Código Nacional de Normas do CNJ e
  as leis da atividade (4,8 MB, um arquivo por norma). Viaja com a atualização.
- **Mais colunas novas**, que também nascem sozinhas: a fração de cada titular (RI), a moeda estrangeira
  e os dados do cheque (Protesto), e o domicílio das partes (RTD).

**Notas — o que o ensaio de atos achou e já está certo**
- Quem comparece por outro (procurador, representante da empresa, pai ou mãe do menor) sai qualificado e
  fora dos dois lados do negócio, com o instrumento; a linha das assinaturas diz quem assina por quem.
- O lado de cada parte vem da qualidade da CEP, no masculino e no feminino (doadora, donatária,
  cessionária); o anuente consente e não vende, e o casal em comunhão vende junto.
- A emancipação confere os dezesseis anos; o estado civil do testador vem da parte; «sabe | pode» é
  escolha no testamento; «nome de solteiro(a)» e «Estado do Maranhão» por extenso nas minutas.
- O advogado no inventário e no divórcio, a CENSEC, a DOI, a revogação e a certidão do testamento
  conferidos na segunda leva. Sem teor, o ato não vai ao livro.

**Registro de Imóveis**
- A indisponibilidade averbada na matrícula **barra** a venda, a doação, a hipoteca e os demais atos
  voluntários, e **avisa** na arrematação, na adjudicação e na partilha. A régua reconhece esses atos
  pelo nome do modelo da casa e pelo da tabela de naturezas.
- A prenotação **anterior** aberta sobre a matrícula se cita na lavratura, e o título posterior só se
  lavra confirmando, com o motivo (fica na auditoria).
- Os modelos de cancelamento de hipoteca, de extinção de usufruto e de cancelamento de ato perguntam
  **qual ato se cancela** e o marcam, como o botão «Cancelar este ato»: o ato cancelado sai da certidão
  de ônus. A lista `ri_cancelamentos_sem_marca.py` acha os cancelamentos antigos sem a marca.
- A matrícula aberta de imóvel gravado avisa o ônus da origem até a averbação do transporte, e a casa
  ganhou o modelo **Transporte de ônus da matrícula de origem** (LRP art. 230).
- A nota com erro se exclui pela tela; a retificação de área acha a matrícula pelo número.
- A certidão de propriedade traz a **qualificação atual** de cada titular, estado civil inclusive (a da
  AV de casamento, depois dela), e a dona que a averbação traz de novo sai uma vez só.
- O quadro de titulares guarda a **fração** de cada um («50%», «1/4»), informada em Partes → Corrigir; a
  certidão de propriedade a diz, e a ficha avisa quando falta a de alguém ou a soma não fecha 100%.

**Protesto**
- O mesmo título não se protesta duas vezes: com o outro protestado, barra; só apontado, aponta-se
  afirmando.
- Depois do vencimento, a falta de aceite ou de devolução se lavra **por falta de pagamento**, e a tela
  avisa a troca (Lei 9.492/1997, art. 21).
- O protesto para fins falimentares intimado por edital só se lavra com a afirmação de que a procura se
  esgotou.
- O título da CRA e da CENPROT (diferido) lança sem caixa; todo título apontado recebe a chave da CENPROT;
  o XML termina com CRLF; o clique da remessa baixa as pendências da Central; a tela avisa o instrumento
  que falta emitir ou assinar antes do XML; o comprovante do edital aceita o PDF da CENPROT e mostra a
  recusa dentro do quadro.
- O recado da sustação concorda com o ato; dois títulos irmãos, um pago e um protestado com o mesmo
  valor, não são mais acusados de incoerência.
- O título em **moeda estrangeira** (Lei 9.492/1997, art. 10): a ficha guarda a moeda e o valor de
  origem, e o valor em reais, convertido, é obrigatório — é o que se cobra e se intima.
- O **cheque** do balcão pede o banco sacado, o motivo da devolução e a data da apresentação ao banco,
  salvo o protesto para instruir medida contra o próprio banco (CN-MA art. 910). Os motivos 20, 25, 28,
  30 e 35 (furto, roubo, extravio, fraude) não se apontam; o cheque de mais de um ano pede o endereço do
  emitente.

**RTD e RCPJ**
- A mesma denominação não se inscreve no Livro A; a parecida, só com a fundamentação.
- O Livro A pergunta a **forma** da pessoa jurídica e avisa quando a natureza diz «empresária» (é da
  Junta Comercial).
- A releitura da ficha pergunta a denominação, e o breve relato certifica a lida e confere a leitura
  pela ordem dos atos.
- O registro cancelado não abre notificação.
- Cada parte do registro tem o **domicílio** (cidade e UF), e a ficha do RTD avisa quando ele não aponta
  para esta circunscrição (LRP art. 130).
- O título do RTD com **valor declarado** mostra o item da tabela pela faixa do valor (15.2.N).

**Registro Civil**
- O termo de óbito longo cabe na frente; a folha do livro em ODT com as três colunas e a pauta.
- O número da D.O. na certidão de óbito; a pesquisa ampla de assentos (livro e folha, pais, declarante);
  o acervo transcrito se inclui e se completa em lote pela tela, e a carga longa se retoma pelo servidor.

**A Ajuda e os agentes de IA**
- A consulta da Ajuda estava lenta e respondia pela regra geral: a base de conhecimento procurava os
  documentos numa pasta que a atualização não leva, e subia vazia. Agora lê `docs/` e as regras da casa,
  a busca entende a pergunta do balcão, e a resposta diz quando foi cortada ou não terminou.
- A Ajuda e o agente do sistema **leem a norma e citam o artigo** (o CN-MA, o CNN, a LRP, a Lei do
  Protesto, o Código Civil, o CPC e as demais), só o trecho pertinente a cada pergunta.
- O manual (`docs/MANUAL.md`) acompanha o que entrou desde a 3.7.10.

**Caixa, despesas e financeiro**
- Quitar o item com o pagamento feito em data anterior, com a aprovação de outra pessoa.
- O item revogado da tabela aparece «REVOGADO – sem valor» e não entra no protocolo.
- Os anexos de Pix e de boleto se leem, e o faturamento do Portal do Selo se confere; o fechamento por
  selo e a apuração fiscal incompleta se identificam.
- Os documentos retirados voltam à ficha do protocolo; a correção de pagamento de despesa pede nova
  autorização.

**Segurança e testes**
- Alertas do CodeQL fechados nas despesas (as recusas respondem frase fixa).
- Testes que dependiam da data e do SQLite da máquina deixaram de depender.

## 3.7.10 — o Registro Civil conferido com a lei, atualizar pelo GitHub e a tela ajustável

São 17 mudanças juntadas desde a 3.7.9 (#233 a #249). A suíte inteira rodou no layout novo, na máquina
da integração: 17.651 verdes, nenhuma falha.

**Atenção ao instalar**
- **Esta é a última atualização pelo caminho de sempre.** A 3.7.9 e as anteriores recusam o pacote
  completo (o sistema passou de 2.000 arquivos): esta versão vai como **pacote parcial**, só com o que
  mudou desde a versão instalada. Da 3.7.10 em diante, a tela **Atualizações** avisa a versão nova do
  GitHub e atualiza com a **senha do oficial**, sem escolher arquivo nem colar SHA-256.
- **Colunas novas** no Registro Civil (testamento do óbito, os sinais do óbito de pessoa não identificada,
  a natureza do ato) nascem sozinhas na primeira abertura.
- **O termo de nascimento não fala mais do casamento dos pais** (Lei 8.560/1992, art. 5º), e o de
  casamento passa a dizer **quem presidiu o ato** (decisões do oficial de 02/11/2026).

**Registro Civil — o que o ensaio de atos achou e já está certo**
- Nascimento: «sendo filha de» para a registrada; a ordem do gêmeo se pergunta na lavratura e vai ao
  termo; a lavratura avisa quando a naturalidade declarada não chega à pessoa.
- Casamento: o CPF dos cônjuges no breve relato; o termo diz quem presidiu o ato.
- Óbito: o testamento é pergunta SIM/NÃO; o óbito de pessoa não identificada não afirma o que ninguém
  sabe e traz os sinais do art. 81, também na tela de corrigir; o natimorto se lavra sem nome, com breve
  relato próprio, causa e sepultamento.
- Reconhecimento de paternidade e mudança de prenome: a certidão sai atualizada e não transcreve a
  averbação (Lei 8.560/1992, art. 6º).
- O «(a)» do termo concorda com a pessoa, e o CPF do breve relato sai com pontos.

**Atualizar pelo GitHub**
- O sino avisa a versão nova, e a tela Atualizações mostra o que ela traz e o botão **Baixar e
  atualizar**: o sistema baixa o pacote, confere o SHA-256 e a assinatura da chave da casa, faz o backup,
  aplica, reinicia e volta sozinho se falhar.
- Falha ao preparar uma atualização vira aviso na tela, e não mais erro 500.

**A tela**
- **Letra maior por pessoa** (100% a 150%), no menu de cada um.
- **As colunas da esquerda recolhem**, e a escolha fica guardada por pessoa.
- **A coluna da direita em destaque**: o cronômetro mostra que está correndo, e o WhatsApp avisa quando
  há gente chamando.
- **Gravar não volta ao topo**: depois de um botão, a tela abre com ele embaixo do mouse.

**Segurança**
- Alerta do CodeQL fechado: o pacote enviado vai ao disco com nome dado pelo servidor.

## 3.7.9 — o layout novo como padrão, despesas do titular e o ensaio de atos

São 104 mudanças juntadas desde a 3.7.8 (#128 a #231). A suíte inteira rodou no layout novo, na máquina
da integração.

**Atenção ao instalar**
- **O layout novo é o padrão da casa** (decisão do oficial de 30/10/2026). Quem ainda não escolheu
  abre nele, com o aviso para ficar ou voltar. O layout antigo continua lá, mas os testes dele não
  rodam mais (ficam no código, marcados como antigos).
- **Livro-caixa, Livro Diário, balanço do mês e backup são só do oficial titular.** Quem não é o
  titular não vê esses livros nem muda as configurações de backup. A **senha do oficial** é opcional
  (Administrativo → Senha do oficial): fecha essas telas por cima do login. Senha esquecida só se limpa
  direto no banco.
- **Chave do titular para o backup** (Despesas → Configuração): com ela, as despesas e o livro-caixa
  saem do pacote de backup fechados, e só abrem com a senha do titular. Sem a chave, o backup segue
  como antes.
- **As barras vermelhas** (FERJ/FERC e as outras que não se fecham) ficam inteiras no alto da tela,
  acima da busca, e a **janela de pendências** abre sozinha ao entrar também no layout novo.
- **Colunas e tabelas novas** (protocolo que virou serviço, despesas, RTD fiduciário, pendências do
  e-Protocolo) nascem sozinhas na primeira abertura.
- **A transcrição dos áudios do WhatsApp** ganhou a escolha de onde transcrever, desligada: até alguém
  mudar, o áudio segue para a OpenAI, como hoje.

**Layout novo**
- As fichas do RI, de Notas, do Protesto, do RCPN, do Livro 3, do RCPJ e do RTD em abas ou fases;
  formulários em passos; quadros recolhidos nas telas longas (configurações, protesto, modelos, CTP).
- Testes de todas as telas e de todos os formulários nas duas molduras, e no Chrome de verdade.

**Registro Civil — o ensaio de atos**
- Cada ato praticado pela tela e o documento conferido com a lei e com o padrão da casa
  (`docs/ensaio_de_atos/`). Já corrigidos: o casamento que o Código Civil não admite não se lavra sem
  aviso; o declarante e a testemunha podem ter nascido depois do fato; o estrangeiro sai com
  passaporte e país; a certidão de natimorto traz o sexo do termo. Os demais estão no relatório.
- A matrícula de 32 dígitos se gera desde 03/09/2026 na ficha do assento.

**Despesas e livros do titular**
- Pix por chave só sai se o favorecido confere; demonstrativo de pagamento em PDF, por e-mail e
  WhatsApp; folha como recorrente; contato e comprovante na despesa; autorizar na lista.
- Livro-caixa do mês até agora, previsão de gastos, ISS preliminar no balanço e DARF do carnê-leão
  preenchido.

**Protesto**
- Confirmação com todos os títulos e confirmação parcial com as contagens; custa na retirada; edital
  sem efeito; a chave da CENPROT pela regra do layout oficial; valor que não é número é recusado; o
  lote de instrumentos vai ao token de uma vez.

**RTD e RCPJ**
- Abas dos livros obrigatórios, partes, bens e o que conferir; processo fiduciário, sobrestamento, DOI,
  nome parecido e Livro Auxiliar; o termo de um dia passado fala daquele dia; lista de presença ou
  certidão de não apresentação exigida.

**Centrais e protocolo**
- CNIB por CPF, atendimentos do SAEC e cobranças do ONR; Serviço de Pendências do e-Protocolo
  (Unidade Interligada e e-Óbito); o cálculo que vira serviço, com a correção dos já quitados.

**Outros**
- Data digitada errada volta com aviso; listas com o mais recente em cima; ordenar pela coluna não
  volta ao topo; relatórios de produtividade por período; certidão reprográfica na largura cheia; o
  login com página desatualizada não responde mais «Bad Request».

**Segurança**
- Seis alertas do CodeQL fechados (redirecionamento, expressões regulares lentas, exceção na resposta
  do WhatsApp, a volta da senha do oficial e a leitura do HTML no ensaio).

## 3.7.8 — o Protesto que não deixa errar, sem janela do Python

São 30 mudanças juntadas desde a 3.7.7 (#97 a #126). A suíte roda na máquina
da integração, e não na do desenvolvimento.

**Atenção ao instalar**
- **As configurações que cobram a equipe** (fim do expediente do caixa,
  avisos do cronômetro e as demais da lista) passam a ser alteradas **só pelo
  oficial, na tela, com afirmação escrita**. O próprio banco recusa a mudança
  feita por script, inclusive a que o suporte rode por ordem sua. O fim do
  expediente do caixa está hoje em **19:00**; voltar a 14:00 é pela tela.
- **Doze tabelas novas e colunas novas no Protesto** nascem sozinhas na
  primeira abertura. O ensaio do esquema foi feito em banco vazio, e não numa
  cópia da produção.
- **Os robôs novos nascem desligados**: conferência CENPROT das 8h15, relação
  da guia de repasse, PIX conferido no banco, boleto de repasse no portal da
  CRA e ciência diária do malote às 8h. Cada um se liga na Automação, e os que
  entram em site pedem a senha no cofre.
- **As janelas do Python que abriam a cada 15 minutos param.**

**Protesto — o que passa a travar**
- O protesto só se lavra com a **prova da intimação** (pessoal, digital ou
  por edital); a entrega do aviso só se registra com o **comprovante** e o nome
  de quem recebeu, e o comprovante de outro título é recusado.
- O **selo se confere antes de lavrar**; falha que se sabe antes recusa
  antes, e a do aparelho vira pendência com saída.
- **Títulos irmãos** (mesmo protocolo) aparecem lado a lado; o protesto trava
  quando o irmão de vencimento posterior está pago com o mesmo valor.
- **Conferência CENPROT × sistema** antes de protestar título da Central,
  separando o pago por liquidação no portal do que veio do nosso XML.
- **PIX só conta como pago** com comprovante e crédito localizado no banco;
  dinheiro sem pagamento lançado vira pendência.
- Quem insiste numa trava **afirma por escrito**, e a afirmação fica no log.

**Protesto — o que passa a fazer**
- O clique da remessa traz também **desistências, cancelamentos e
  autorizações** da CRA; desistência alcança todos os títulos do protocolo.
- **Retorno à CRA**: ocorrência já aceita, protocolo já informado ou arquivo
  ainda sem resposta não voltam à fila.
- **Roteiro das Centrais** com condutas cobradas e **encerramento do dia**;
  só o oficial reabre o dia.
- **Guia de repasse** nasce sozinha no dia do pagamento, e o pagamento só sai
  da pendência com a guia paga; o robô pode emitir o boleto no portal da CRA,
  que vai às despesas esperando a sua autorização.
- **Instrumentos em lote**: emitir e assinar vários de uma vez.
- **Averbação de retificação de erro material**, de ofício (art. 25).
- **Selo que faltou** se emite depois, pelo item já pago no protocolo.
- O nome de **quem recebeu o aviso** no canhoto, completado depois, com
  tarefa à escrevente.
- O cedente do acervo vem do cadastro do E-Ofício, com o nome da CRA.

**Correções de ofício**
- Uma fila: o agente ou a escrevente propõe, o oficial aprova com afirmação
  expressa, e o servidor executa.

**WhatsApp**
- O script da conversa voltou a carregar.
- Erro passageiro volta à fila, e a entrega aparece ao vivo com o motivo.
- Quem é a pessoa: cartão de firma e protocolos pelo telefone.

**Malote**
- O robô pode dar a ciência diária às 8h com a senha do cofre, pedindo o
  código de dois fatores quando o malote exigir.

**Segurança**
- Os dois alertas novos do CodeQL (código da comunicação da CRC e extensão do
  documento da despesa) e a leitura do XML de desistência sem expansão de
  entidade.

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
