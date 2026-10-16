# Tabelionato de Protesto

Decisões do módulo de Protesto que valem para qualquer serventia: modelo do título e dos atos, ciclo apontamento–intimação–protesto–certidão, os arquivos da CRA (layouts medidos) e as APIs da CENPROT e da Resolve, com as armadilhas de contrato que foram medidas.

## Modelo de dados e livros

### O título é uma linha e cada ato é outra linha, com selo e custas próprios
**Regra.** `pt_titulos` guarda o título; `pt_atos` guarda apontamento, intimação, protesto, pagamento, desistência, cancelamento e arquivamento, cada um com o seu selo e as suas custas vindas do núcleo. A certidão tem tabela própria (`pt_certidoes`), porque a negativa não tem título.
**Por quê.** Uma tabela larga com uma coluna de selo e de fundo por etapa (o desenho do sistema anterior) fica com metade das colunas vazias e não se consulta. Duas tabelas e uma consulta respondem «que atos este título teve».
**No código.** `pt_schema.py`, `protesto.py`, `protesto_certidao.py`.

### A geometria do livro se conta por face, e o protocolo do protesto reinicia todo dia
**Regra.** A capacidade do livro se declara em `por_face` (nunca `por_folha`), e a contradição é recusada ao montar a série. O Livro de Protocolo do protesto tem numeração diária (`numeracao_diaria`): o contador zera sozinho e o sistema recusa fixá-lo à mão. O protocolo do título é `AAMMDD` + sequencial do dia e não se renumera.
**Por quê.** Num livro que escritura o verso, folha e face diferem pelo dobro, e foi essa ambiguidade que levou a lugar errado. Numeração contínua num livro diário faria o protocolo de hoje sair com um número de milhares.
**No código.** `livro_nucleo.py`, `escrituracao.py`.

### O encerramento diário se lavra também no dia sem movimento
**Regra.** O termo de encerramento é gravado com a faixa de números do dia, e o dia sem nenhum apontamento também recebe termo.
**Por quê.** O silêncio precisa estar escrito; dia sem termo não se distingue de dia esquecido.
**No código.** `nucleo_schema.py` (`nu_encerramentos_diarios`), `escrituracao.py`.

### Dois livros abertos na mesma série são recusados
**Regra.** O núcleo recusa abrir um segundo livro enquanto houver outro aberto na mesma série.
**Por quê.** Dois livros abertos ao mesmo tempo são a receita para o mesmo número de ordem sair em dois lugares.

### Onde o acervo não traz o número, a série vira pendência declarada
**Regra.** A carga semeia o contador pelo maior número que trouxe (nunca baixando). Para as séries cujo número o acervo não guarda (Registro de Protestos, Registro de Pagamentos), o próximo número é pendência que só o oficial informa, antes do primeiro ato.
**Por quê.** Sem semear, o primeiro ato novo nasce com o número 1 sobre um livro que já passou dele. Teste em banco vazio nunca vê esse defeito.
**No código.** `acervo_carga.semear_numeracao`, `implantacao.py`.

### Gratuidade e cancelamento exigem motivo do catálogo mais fundamento escrito
**Regra.** O cancelamento exige uma das hipóteses do catálogo (pagamento, ordem judicial, anuência do credor, erro do apresentante) **e** o fundamento do caso. A gratuidade exige motivo escrito; «título apresentado em duplicidade» é irregularidade do contrato da CRA, e não isenção, e se registra como tal.
**Por quê.** Um cadastro único («erro material») ou texto livre faz o livro não explicar o que aconteceu; duplicidade e permuta não são isenção legal.
**Fundamento.** Lei 9.492/1997 (hipóteses de cancelamento). A hipótese de isenção por mandado judicial a favor de beneficiário de assistência judiciária vem da tabela de emolumentos (norma estadual — TJMA; confira a tabela do seu estado).
**No código.** `protesto.CATALOGO_CANCELAMENTO`.

## O ciclo do título

### O apontamento é o primeiro ato e não se faz junto com o cadastro
**Regra.** Cadastrar o título não lavra nada (fica `RECEBIDO`); o apontamento, com lugar no livro, número de ordem, selo e custas, é o ato seguinte, na ficha.
**Por quê.** Juntar os dois numa tela faria o balcão apontar sem querer, e apontamento não se desfaz.
**Fundamento.** Lei 9.492/1997, art. 3º.
**No código.** `protesto.py`.

### O aviso é o instrumento; a intimação é o ato
**Regra.** O aviso se emite quantas vezes for preciso (vários por título), com o endereço congelado no aviso. A intimação pessoal só se lavra quando a entrega é confirmada; tentativa frustrada não lavra nada. O motivo de não-entrega sai de catálogo com duas marcas que valem regra: «vai direto a edital» e «conta tentativa e pede outra».
**Por quê.** Lavrar na tentativa deixaria o título intimado sem ninguém intimado, e o protesto sairia em cima disso. O endereço congela porque a tentativa de hoje foi para aquele lugar.
**No código.** `protesto_aviso.py`.

### O edital é tratado como rotina, e é registro numerado com teor congelado
**Regra.** O edital recebe número do exercício, teor congelado e hash, e lavra a intimação por edital. A tela põe a fila do edital primeiro.
**Por quê.** Medido no acervo, o caminho comum é a tentativa sem ninguém em casa seguida de edital. Edital que só existe como texto digitado num campo não se confere depois.
**No código.** `protesto_aviso.py`.

### O sistema não calcula o tríduo nem decide se o prazo venceu
**Regra.** As telas mostram a data da intimação e quantos dias correram — contagem, e não juízo. Sem data, a contagem é `None` (traço), nunca zero. Há teste que recusa nomes como `venceu_o_prazo` ou `pode_protestar`.
**Por quê.** Contar o prazo é decisão jurídica do oficial; zero afirmaria «intimado hoje».

### «A protestar» lista os intimados sem ato posterior e lavra só os marcados
**Regra.** A fila é de títulos intimados sem nenhum ato depois da intimação (pela ordem dos atos, e não só pela situação). Lavra apenas os marcados, cada um na sua própria transação; o lote (como o recebimento de remessa) não sela nem cobra, e os atos aparecem em `atos_sem_selo` e `atos_sem_cobranca`.
**Por quê.** Protesto não se desfaz: um clique não pode valer vinte atos. Selar em lote seriam dezenas de chamadas de rede dentro de `BEGIN IMMEDIATE`, travando a casa.

### A sustação bloqueia três atos, e o revogado volta ao alto da fila
**Regra.** Título sustado não pode ser pago, protestado nem retirado; a recusa diz juízo, processo e data. Juízo e processo são obrigatórios ao registrar. Revogada a sustação, o título aparece no alto do «A protestar», porque deve ser protestado até o primeiro dia útil seguinte ao **recebimento** da revogação, sem nova intimação. O sustado tem tela própria.
**Por quê.** Sem a sustação registrada, a lavratura em lote ofereceria um título que o juiz mandou parar. O revogado tem dois atos após a intimação e sumiria da fila comum, justo o que tem um dia de prazo.
**Fundamento.** Lei 9.492/1997, art. 17, §§ 1º e 2º.
**No código.** `protesto.ATOS_QUE_A_SUSTACAO_BLOQUEIA`.

### Sustação e efeito suspensivo são institutos diferentes
**Regra.** Sustação chega antes do protesto e impede o ato; efeito suspensivo chega depois e suspende a publicidade. O protesto suspenso continua na certidão positiva, com a nota de que os efeitos estão suspensos (juízo e processo).
**Por quê.** Tirar o protesto da certidão seria mentir do outro lado: ele existe no livro.

### O termo do protesto se compõe de frases inteiras e congela no ato
**Regra.** O texto que vai ao Livro de Registro de Protestos é modelo editável no catálogo (formato `CHAVES`), com a frase do edital montada dos fatos — uma vez, terminada em ponto — e só quando a intimação foi por edital. O termo congela no ato; corrigir é averbar.
**Por quê.** O livro saía sem o texto do ato. A frase de edital em intimação pessoal afirmaria publicação que não houve. Afirmação jurídica fixa no texto padrão (ex.: a certificação da dívida ativa) é decisão de quem assina, não do código.
**Fundamento.** Lei 9.430/1996, art. 9º-A (protesto de CDA).
**No código.** `protesto_termo.py`.

### O instrumento de protesto confere os dez itens da lei e declara os que faltam
**Regra.** O instrumento se monta dos requisitos legais e vai ao catálogo de modelos. `conferir()` diz item a item o que o título preenche; item sem fonte (ex.: endereço do apresentante, que a remessa da CRA não traz) aparece como faltante, e os itens só aplicáveis à letra de câmbio aparecem como «não se aplica». A dispensa do parágrafo único só se afirma se a cópia do título estiver de fato arquivada (pergunta-se ao banco). O teor congela porque vai ser assinado; segunda via é outra linha.
**Por quê.** Papel assinado que omite item da lei só mostra o defeito quando contestado. Teor remontado faz a assinatura deixar de conferir.
**Fundamento.** Lei 9.492/1997, arts. 20 e 22 (e parágrafo único); LUG, arts. 56 a 58.
**No código.** `protesto_instrumento.py`.

### A certidão tira o tipo do que a busca achou, e só protesto lavrado conta
**Regra.** Negativa nunca sai sobre quem tem protesto; o tipo vem do resultado, nunca do pedido. Apontamento não é protesto. A busca roda de novo na emissão, o teor congela, numeração por exercício com sha256. A busca por nome usa coluna normalizada (`nome_norm`) por função Python única.
**Por quê.** Negativa errada faz o banco emprestar e não se desfaz. `UPPER`/`LOWER` do SQLite são ASCII e não acham nome acentuado.
**No código.** `protesto_certidao.py`, `pt_schema.normalizar_nome`.

## Arquivos da CRA (layout de 600 posições)

### O tipo do arquivo se lê do cabeçalho, nunca da pasta
**Regra.** As posições 53–61 do cabeçalho (origem + destino + tipo) dizem se é remessa, retorno, confirmação ou andamento. A desistência tem layout próprio e é recusada pelo leitor de 600 com a mensagem do tamanho achado.
**Por quê.** Medido: há remessa guardada em pasta de retorno e retorno em pasta de desistência; lido com o layout errado, nada bate.
**No código.** `protesto_arquivo.py`.

### O layout foi medido contra o acervo, e campo não identificado fica `reservado_NNN`, lido como texto
**Regra.** No registro de título o primeiro bloco de nomes é o cedente e o segundo o devedor. O documento tem 14 posições com zeros à esquerda e quem diz se é CPF ou CNPJ é o campo de tipo ao lado (001 = CNPJ, 002 = CPF). `99999999` é «sem vencimento»: lê-se como vazio e reescreve-se como `99999999`. Campo cujo sentido não foi medido chama-se `reservado_NNN` e é lido como texto; há teste que impede batizá-lo sem medir.
**Por quê.** Cortar zeros faz CNPJ iniciado por zero perder um dígito. Ler reservado como número destrói a estrutura na reescrita. Nome bonito em campo desconhecido finge conhecimento.

### A prova do layout é o ida e volta byte a byte
**Regra.** Ler um arquivo real e reescrevê-lo tem de sair idêntico, inclusive nos campos reservados. Arquivo com mais de um lote emendado é recusado pelo escritor, que manda separar os lotes. O arquivo sai em ISO-8859-1.
**Por quê.** O ida e volta achou defeitos que nenhuma conferência campo a campo pegou (fronteira do bairro do devedor, rodapé, a marca de sem vencimento). Escrever a partir de multi-lote perderia os lotes de trás em silêncio; acento em dois bytes empurra a linha.

### O rodapé da remessa conta registros; o do retorno conta títulos
**Regra.** Remessa e confirmação: o rodapé conta registros (cabeçalho, títulos e rodapé). Retorno e andamento: conta títulos, em 4 dígitos a partir da posição 54. São dois campos com nomes diferentes.
**Por quê.** Lido com a largura e o sentido errados, o rodapé dava sempre o mesmo número e a conferência acusava «arquivo truncado» em arquivos bons — alarme que soa sempre ninguém ouve.

### Confirmação e andamento são compostos, e não transcritos
**Regra.** Confirmação e andamento são o layout da remessa com o bloco 446–485 do retorno (protocolo, ocorrência, data de entrada, data da ocorrência). A composição recusa faixa que não cubra exatamente o bloco.
**Por quê.** Transcrever criaria outro lugar para a mesma medida divergir; composto, a correção chega sozinha.
**No código.** `protesto_arquivo.TITULO_NA_CONFIRMACAO`, `RODAPE_RETORNO`.

### A remessa se separa em lotes, entra uma vez só e um título ruim não derruba os outros
**Regra.** Um arquivo pode trazer vários lotes de apresentantes diferentes: separa-se por lote antes de tudo, cada lote vira uma remessa com sua confirmação. `UNIQUE(hash_arquivo)` sobre o conteúdo normalizado (CRLF/LF) impede receber duas vezes. Conferir e receber são dois passos, e conferir não grava. A chave de origem é a posição no lote, não o nosso número. A confirmação confirma só o que entrou.
**Por quê.** Ler só o primeiro cabeçalho atribuiria os títulos dos outros lotes ao primeiro apresentante, e o erro só apareceria no retorno. O nosso número se repete entre apresentantes. Receber duas vezes apontaria tudo de novo.
**No código.** `protesto_remessa.py` (`pt_remessas`).

### Título sem vencimento e espécie fora do esquema entram com aviso
**Regra.** Data de vencimento não é obrigatória na conferência (certidão de dívida ativa chega sem ela; o próprio contrato tem irregularidade para o caso). Espécie usada no acervo e ausente do XSD é aceita com aviso; código interno do sistema anterior não entra no vocabulário oficial.
**Por quê.** Recusar faria o balcão digitar à mão títulos que a Central mandou; aceitar em silêncio mandaria dado inválido de volta.
**No código.** `protesto_cra.py` (espécies, irregularidades e ocorrências dos XSDs oficiais).

### O retorno sai do que foi lavrado, sempre em par com o andamento
**Regra.** A ocorrência do retorno vem do ato (protesto, pagamento, desistência, cancelamento); ato informado ganha `retorno_id` e o arquivo inteiro fica gravado. Retorno e andamento saem juntos. Na dúvida sobre um campo, imita-se o que já foi aceito pela Central (ex.: o andamento desta casa sempre levou ocorrência `0`; o campo de valor de evento sai zero). A letra da posição 566 é convenção de cada casa (A, P ou branco são aceitos): o sistema usa a do histórico do apresentante e, sem histórico, recusa e pede a letra.
**Por quê.** Nada sai duas vezes, e quando a Central reclamar é o teor gravado que se lê. Antes de «consertar» uma diferença entre dois arquivos, confirma-se que falam dos mesmos títulos.
**No código.** `protesto_retorno.py` (`MARCA_POR_APRESENTANTE`, `OCORRENCIA_DO_ANDAMENTO`).

### A desistência tem layout próprio de 127 posições e não se aplica sozinha
**Regra.** Cinco tipos de registro (0, 1, 2, 8, 9), sequencial nas últimas 5 posições, soma de valores conferida no rodapé; a contagem do registro 8 (o dobro dos títulos, medido) gera aviso e não recusa. O protocolo do arquivo acha o título; cada título é marcado pelo oficial. Arquivo repetido não é recusado (aplicar duas vezes não faz nada), mas é gravado uma vez. O sistema não escreve este arquivo: ele só chega.
**Por quê.** Desistência não aplicada é protesto contra quem o credor desistiu de protestar; aplicada por engano é protesto que deixa de sair. O layout foi provado em acervo de outro estado: layout é nacional, convenção não.
**No código.** `protesto_desistencia.py`.

### A imagem do título só se prende pela dupla chave
**Regra.** O pacote de imagens se casa ao título por nosso número **e** documento do devedor; a recusa diz qual das duas falhou. Conferir não grava; o mesmo pacote não entra duas vezes (sha256).
**Por quê.** O nosso número se repete entre apresentantes; prender pela metade mostraria ao devedor a dívida de outro.
**No código.** `protesto_imagens.py`.

## CENPROT: chave única e arquivos

### A serventia não gera a chave de 23 dígitos; guarda a que a Central devolve
**Regra.** A chave é IBGE da comarca (7) + bloco da Central (8) + código do cartório (2) + data do protocolo `AAMMDD` (6). Ela não vem por nenhum arquivo da CRA; vem do XML diário do CENPROT, ao lado do nosso protocolo. O importador grava em `pt_titulos.chave_cenprot` com três guardas: o arquivo é desta serventia (comarca e cartório do cabeçalho), o casamento é por protocolo **e** nosso número (ou valor), e chave já gravada não se sobrescreve.
**Por quê.** Nem protocolo nem nosso número são nacionais: sem as guardas, o arquivo da serventia vizinha escreveria chaves alheias nos nossos títulos. Regularidade de uma casa (o bloco do meio) não se generaliza sem olhar outra.
**No código.** `protesto_cenprot.py`.

### O arquivo de emolumentos tem formato medido e valores somados da tabela
**Regra.** Texto separado por `|`, com cabeçalho `nm_chave|vl_retirada|vl_cancelamento|cd_ibge|nr_cartorio|dt_movimento`, data `AAAAMMDD`, CRLF e sem BOM. Retirada = parte fixa + faixa do item de liquidação/desistência pelo valor do título; cancelamento = parte fixa + faixa do item de protesto pelo valor. A parte fixa é somada da tabela vigente (não é número escrito), e um teste amarra a soma ao valor medido em arquivo real (norma estadual — TJMA; os itens e faixas são da tabela do seu estado).
**Por quê.** Número inventado em arquivo que vai à Central é pior que arquivo nenhum. Somar itens até «fechar» um número sempre fecha: a composição só valeu quando um arquivo real nomeou os itens.

### O edital eletrônico tem convenções próprias dentro do mesmo arquivo
**Regra.** O documento do devedor vai **com máscara**; o valor aparece em duas formas no mesmo registro (vírgula e ponto); o nome leva data `DDMMAAAA` (o de emolumentos usa `AAAAMMDD`); `finalidade` é o motivo da não-entrega e fica vazio sem motivo; `numerotitulo` é o número do título, não o nosso número. A fonte são os editais já publicados; gerar o arquivo não publica edital.
**Por quê.** Cada convenção foi medida em exemplar real; usar a regra de um arquivo no outro quebra sem aviso. Motivo inventado afirma sobre a pessoa o que ninguém apurou.

## APIs das Centrais

### Credencial fora do banco e chamada de rede fora da transação
**Regra.** Senha, token e chave de cada Central ficam em arquivo próprio na pasta de dados (fora do backup), com o ambiente fazendo parte da chave. Nenhuma chamada de rede acontece dentro de `db.transaction()`. Falta de credencial é recusa com frase para o balcão, não HTTP 500.
**Por quê.** O banco viaja no backup. Trinta segundos de rede segurando `BEGIN IMMEDIATE` põem a casa no `busy_timeout`.
**No código.** `centrais_cred.py`.

### As APIs não lavram ato: trazem, levam e informam
**Regra.** Cancelamento, protesto, intimação e certidão continuam sendo lavrados no módulo de domínio, com suas recusas. A tela da Central só informa o que já foi lavrado; decidir e enviar são dois botões, e enviar não é do balcão. A decisão judicial da CENPROT só se baixa; quem registra a ordem (com a data do recebimento) é o oficial.
**Por quê.** Avisar e preparar; quem assina decide. Um clique que decidisse e mandasse faria respostas saírem sem ninguém olhar.

### CRA21 (SOAP): HTTPS forçado, namespace por ambiente, parâmetros posicionais
**Regra.** O endereço é forçado para HTTPS e não lido do WSDL (o de homologação declara `http://` e a autenticação é HTTP Basic); há teste que avisa se o WSDL for corrigido. O namespace muda entre produção e homologação. Em `rpc/encoded` a ordem dos parâmetros é posicional e é conferida contra o WSDL. `userArq` é o nome do arquivo FEBRABAN, não o conteúdo. O teste de ligação usa `BuscarApresentante` (única operação sem parâmetro), porque pedir remessa a marcaria como baixada. `ConsultaAutorizacao` vai com `marcarBaixado` desligado por padrão. As operações que dependem de `userDados` (inclusive Confirmação e Retorno) não têm botão enquanto o conteúdo não for medido em homologação. A remessa devolvida pela API vem em XML com atributos FEBRABAN e precisa de adaptador; não se passa o XML cru ao leitor de 600 posições.
**Por quê.** Senha não viaja em texto puro. Namespace ou ordem errados fazem a Central responder sobre outra coisa, sem erro. Apontar o que se leu errado aponta títulos que ninguém apresentou.
**No código.** `cra21_api.py`, `cra21_web.py`.

### API da CENPROT: cada caminho tem a sua convenção, e o teste lê o contrato
**Regra.** Os testes abrem o `swagger.yaml` e comparam. A mesma API tem três convenções de data/paginação (`data_inicio`/`pagina`; `dt_inicio`/`dt_fim` obrigatórios; `dt_ocorrencia_de`/`page`/`per_page`); anuências exigem `data_inicio` e `data_fim` embora o contrato diga opcional. O corpo vai cru (array) nos `processar` e embrulhado (`{"pedidos": [...]}`) no `protocolar`; tetos de lote 1.000 e 50. Os obrigatórios se conferem antes da rede (a Central responde 500 sem dizer qual faltou), com o gêmeo legado como fonte quando o schema novo cala. O token vem em `token` (não `access_token`) e nunca se ecoa em mensagem. Nas listas, 404 significa «nenhum». O teor da anuência pode vir aninhado e é procurado em qualquer nível. O ambiente entra na chave única das pendências (homologação e produção usam o mesmo intervalo de códigos). Em caso de nome divergente no contrato (`cd_pedido` × `nr_pedido`; nome de campo com aspas e espaços na lista `required`; chave declarada com 23 e exemplificada com 25), vale a restrição e o exemplo que separa, marcado A CONFERIR em homologação.
**Por quê.** Parâmetro desconhecido a Central ignora: a tela pediria um mês e receberia tudo. Sem o ambiente na chave, a pendência real não entraria, sem erro.
**No código.** `cenprot_api.py`, `cn_schema.py`, `cenprot_pendencias.py`, `cenprot_web.py`.

### Anuência e cancelamento seguem o caminho do contrato
**Regra.** Quem anui é o credor; quem pede o cancelamento é o interessado, e é quem paga. Responder à anuência diz «aprovo» e «quanto custa cancelar», e não baixa o protesto. A cotação vem sugerida pela custa de cancelamento da tabela, com a origem dita na tela. O sistema recusa informar o cancelamento à Central antes de o título estar CANCELADO no livro. Código de situação não documentado no contrato fica A CONFERIR.
**Fundamento.** Lei 9.492/1997, art. 26.

### Renegociação responde a custa de cancelamento, não a de retirada
**Regra.** A casa não aceita nem recusa a proposta do devedor: responde `vl_custa` = custa de cancelamento. Um teste exige que a função da renegociação use o cancelamento e a do pedido de protesto use a retirada. Sugestão sem cálculo devolve `None` com motivo, nunca zero. Como a Central recusa item a item dentro de uma resposta 200, a conferência (lote vazio, acima do teto, item sem código ou sem custa) é antes da rede e diz qual item.
**Por quê.** Trocar os dois valores mandaria ao devedor um preço errado que só apareceria no balcão. Zero em campo de dinheiro afirma «não custa nada».

### A Intimação Digital (Resolve) é outra API e não lavra a intimação
**Regra.** Contrato próprio, chave `x-api-key`, três ambientes (testes, homologação, produção), com testes como padrão da tela. Uma linha por intimação, não por título. O `INTIMADO` da plataforma é ciência do devedor; a intimação que permite o protesto continua sendo o ato lavrado na ficha. Não vão títulos sustados, pagos, retirados, protestados, cancelados ou desistidos. Valor em centavos é convertido para reais com duas casas. `nrChave` (23 dígitos) é obrigatório. `tipoDocumento` só existe no devedor; o apresentante vai com nome e documento ou não vai. O sistema não manda contato que a casa não tem. A casa avisa à Central pagamento, intimação feita por outro meio e cancelamento. Histórico (com assinatura HMAC) e PDF do comprovante são a prova da tentativa antes do edital; o PDF não se guarda no banco. Cancelamento de lote inteiro não tem botão.
**Por quê.** Mensageria sobre título sustado cobraria quem o juiz mandou parar. Mandar o inteiro cobraria cem vezes o valor na casa do devedor.
**Fundamento.** Lei 14.711 (intimação eletrônica).
**No código.** `resolve_api.py`, `rs_schema.py`, `resolve_intimacao.py`, `resolve_web.py`.

## O que o sistema deliberadamente não faz

### Não gera o boleto do aviso nem a chave do CENPROT
**Regra.** O registro do aviso existe; o código de barras não, porque o dígito verificador do campo livre e o fator de vencimento não se reproduziram em busca exaustiva. A chave do CENPROT só se guarda, nunca se compõe.
**Por quê.** Código de barras errado é boleto que o leitor aceita com o dinheiro indo para o lugar errado; chave inventada fala de outro título na Central.

### Não constrói função do sistema anterior sem dado que mostre uso
**Regra.** Antes de reproduzir um item de menu do sistema legado, procura-se o dado no banco; tabela ausente ou coluna zerada indica que a casa nunca usou (ex.: monitoramento de devedor, exportação a birôs de crédito, arquivo bancário, repasse ao apresentante, autorização de cancelamento quase sem uso). Relatórios de prestação de contas ao tribunal exigem a norma lida antes de construir.
**Por quê.** Três telas não são medida de frequência; fluxo de outro estado (pagamento no banco) não se aplica onde o pagamento é na serventia.
