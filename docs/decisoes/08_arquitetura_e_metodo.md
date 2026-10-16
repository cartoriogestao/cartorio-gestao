# Arquitetura e método

Regras de desenho comuns às seis atribuições e o método que as produziu: medir antes de decidir e revisar ato por ato. A base comum de transporte das integrações (TLS, reenvio, fila, ambiente, credencial) está em `07_centrais_rcpn_rtdpj.md`.

## Transação, banco e migração

### Um escritor por vez, com índices únicos como rede de baixo
**Regra.** `db.transaction()` abre `BEGIN IMMEDIATE` sobre SQLite em WAL com `busy_timeout`; balcões simultâneos serializam e o segundo lê o contador já incrementado. Telas de leitura não escrevem. Auditoria em tela de leitura espera pouco pelo lock e, falhando, vai ao log do servidor em nível de erro.
**Por quê.** O escritor único é o que torna seguras as travas de numeração. Leitura que toma o lock derruba outras telas; entre entregar o documento sem a linha de auditoria e não entregar nada, a serventia precisa do documento.

### A chamada de rede não segura a trava de escrita, e a assinatura da função impede o engano
**Regra.** Toda função que fala com serviço externo (selador, Central, provedor de IA) recebe `db`, e não `con`, e abre transações curtas antes e depois da rede. Lote que exigiria uma chamada de rede por item não sela nem cobra dentro do lote: os itens vão para as listas de "atos sem selo" e "sem cobrança". Cada item de um lote roda na sua própria transação; o ruim não derruba os bons, e o motivo da recusa fica gravado.
**Por quê.** `BEGIN IMMEDIATE` com uma chamada de 20 a 30 s dentro põe os outros balcões no `busy_timeout`. Com `db` na assinatura não há como chamar de dentro de uma transação sem reparar.
**No código.** `ato_selado.obter_selo`, `ajuda.consultar`.

### Não trocar de SGBD sem gatilho medido, e não aumentar a dívida enquanto isso
**Regra.** O sistema permanece em SQLite. Toda transação que morre com `database is locked` vira uma linha num log da pasta de dados, fora do banco; o total aparece ao administrador, com alerta a partir de cinco em trinta dias. Outros gatilhos: segunda serventia na mesma base, exigência normativa de SGBD, réplica quente. Teste de portabilidade limita, por módulo, o acoplamento gratuito (data e recorte de texto em SQL, `PRAGMA` fora do esquema), procurando por `ast` só em literais, e acusa teto maior que o uso real; módulo novo entra com zero. Dinheiro em centavos inteiros, data em ISO.
**Por quê.** A migração custaria meses para fazer o mesmo, e o ponto de risco é a numeração, que sob MVCC exigiria `SELECT ... FOR UPDATE` ou sequência. Registrar a disputa no banco travado disputaria a mesma trava. Procurar a palavra no arquivo contava `datetime.strftime` como SQL; teto folgado nunca fica vermelho. Backup em arquivo é simples de restaurar em serventia sem TI.
**Fundamento.** Provimento CN-CNJ 213/2026 (backup).
**No código.** `tests/test_portabilidade.py`.

### A guarda dos esquemas é teste estático, não comentário
**Regra.** Um teste lê os esquemas e recusa: índice do `SCHEMA` sobre coluna que só nasce em migração; migração com `NOT NULL` sem `DEFAULT`, `UNIQUE` ou `PRIMARY KEY`; coluna presente no `SCHEMA` e ausente da migração (ou o contrário); entrada declarada duas vezes. E exige que o banco suba íntegro duas vezes seguidas (`init_*` idempotente).
**Por quê.** Teste sobre banco novo não vê defeito de banco velho.
**No código.** `tests/test_esquemas.py`.

### Normalização de texto é uma função da casa, registrada também no SQLite
**Regra.** Busca por nome usa coluna normalizada preenchida por uma única função; em tabelas sem essa coluna, a mesma função é registrada na conexão (`con.create_function`). Nunca `UPPER`/`LOWER` do SQLite, nunca cópia da função noutro módulo.
**Por quê.** `LOWER('JOSÉ')` no SQLite dá `josÉ`, e uma cópia da função divergiu na caixa: nos dois casos a busca não achava ninguém, em silêncio.
**No código.** `pt_schema.normalizar_nome`, `fraude.nome_da_casa`.

### Tipo e vazio se tratam na consulta
**Regra.** Antes de comparar duas colunas confere-se o tipo das duas (afinidade `INTEGER` × `TEXT`). `SUM`, `MIN`/`MAX` de tabela vazia e divisão por contagem zero se tratam com `COALESCE` na consulta, não no template. Data guardada em dois formatos (`AAAA-MM-DD HH:MM` e `AAAA-MM-DDTHH:MM`) se filtra como texto: «até o dia D» compara com `'D' + 'z'`.
**Por quê.** Agregação vazia passa na produção cheia e derruba tela na instalação nova; consertar na consulta vale para todo leitor dela. `BETWEEN` com a data nua exclui o último dia.

## Domínio, rotas e telas

### A tela oferece por educação; o domínio recusa por dever; a guarda está no servidor
**Regra.** A tela só mostra os atos que cabem, mas a recusa mora no domínio, e há teste que manda o pedido proibido direto à rota. Módulo restrito é recusado na rota, não só escondido do menu. Permissão é por ação quando a mesma rota faz coisas de pesos diferentes (lavrar é do balcão; encerrar a ficha é do titular), e a recusa de uma parte derruba o pedido inteiro.
**Por quê.** Regra repetida em dois lugares diverge; link removido com rota de pé esconde a porta sem trancá-la; lavrar metade do pedido deixa no livro algo que só outro ato conserta.

### GET não escreve, e o POST refaz o que decide
**Regra.** Toda função de contador tem `consumir=False` para telas de leitura. O rastro de que o operador viu um alerta é gravado quando ele reconhece, nunca ao abrir a ficha. A busca que decide o conteúdo de um papel roda de novo no POST de emissão. Rota alcançada por GET, POST e redirecionamento lê `request.values`. Falta de credencial e erro de Central são apanhados como erro de regra; recusa do domínio não descarta, num redirecionamento, a lista do que não casou e por quê.
**Por quê.** Tela de leitura que grava prende o banco.

### O operador não perde o que digitou
**Regra.** Formulário de lavratura repõe os valores quando a gravação falha; revisão de várias sentadas se guarda sem lavrar pelo mesmo formulário (`formaction`), nunca por um segundo formulário com os mesmos campos; em atualização parcial, `None` quer dizer "não mexi", e só campo presente e inválido é erro, nomeado.
**Por quê.** Dois formulários divergem no dia em que a tela ganha um campo; `None` tratado como "esvazie" apagaria campo que o selo exige.

## Fonte única

### Cada decisão mora num lugar só, e tela e papel pedem o conteúdo à mesma função
**Regra.** O que o carimbo do selo escreve, a régua de qual módulo é cada tela, o bloco de alerta, o quadro de cobrança, as marcas de encerramento de uma ficha, a montagem de arquivo para Central: uma função ou macro só; tela e papel apenas desenham. Há teste que exige o uso dessa função e conta os lugares que escrevem marcas críticas.
**Por quê.** Cópia "parecida" diverge no primeiro conserto: a tela mostra uma coisa e o papel imprime outra, ou uma ficha encerrada aceita registro novo.
**No código.** `selo_no_papel.py`, `modulos.py`, `templates/_fraude.html`, `templates/_cobrar.html`.

### Lista que pode ser medida não se escreve à mão
**Regra.** Opções de filtro saem de `SELECT DISTINCT`; o mapa de telas, do `url_map`; os campos de um importador, do esquema; os campos que uma tela pergunta, do modelo da tela; regras de teste medem ("todo módulo com mais de seis itens tem seção") em vez de nomear módulos.
**Por quê.** Lista escrita à mão envelhece na tarde em que se escreve, inclusive a do teste que deveria guardar a regra; quando quem a lê é uma IA, ela responde errado com convicção.

### Função pronta sem chamador se apaga, e argumento sem quem o passe se procura
**Regra.** Peça que nenhuma tela chama é ligada a uma tela ou apagada, e o caminho externo correspondente fica declarado. Função que compra selo ou desfaz em massa só existe dentro da guarda que a justifica, com teste que exige a chamada ali dentro. Há teste que exige que todas as telas passem os argumentos de que a função precisa.
**Por quê.** Peça sem uso é a arma que alguém religa sem saber por que existia. Uma função aceitava o parâmetro e nenhum chamador o passava: o campo saía vazio em todas as linhas de uma carga, invisível a qualquer varredor de função órfã.

## Atos e papéis assinados

### O que a serventia assina congela; reemissão é outra linha
**Regra.** Certidão, termo, edital, instrumento e recibo guardam o teor como saiu, com número do exercício e sha256; ato posterior não altera papel emitido; segunda via é nova linha; cancelar não apaga o teor; o papel registra quantos atos o registro tinha ao sair. Inteiro teor não se digita; sem teor no banco, recusa-se e indica-se o livro físico.
**Por quê.** Remontar o teor faria a via do cliente discordar do banco e invalidaria a assinatura digital, que é sobre bytes determinados.

### Papel que afirma o falso é pior que campo vazio
**Regra.** Campo sem dado sai vazio ou declarado, nunca preenchido com dado de outro contexto (data da emissão como data do registro, pais de um cônjuge sob o rótulo do outro). Data impossível não entra: no balcão a recusa é imediata; na carga, a pessoa entra sem a data e a carga diz quantas e quais. Dado corrompido na origem é declarado irrecuperável e recolhido de novo, nunca «consertado» por substituição. Modelo não afirma em texto fixo o que a norma condiciona. Rótulo sem valor não se imprime; marca que desmente o número (isento, diferido) se imprime. Prévia leva marca de "não lavrado" na própria impressão.
**Por quê.** Campo vazio não afirma nada; valor errado afirma, num documento que não se desfaz. Conserto por palpite é chute com cara de recuperação.

### Rascunho e minuta vivem fora da tabela de atos e não reservam número
**Regra.** Onde todo ato entra definitivo, toma número e entra na corrente de hash, rascunho e minuta têm tabela própria; o número é pretendido, não reservado; quem lavra é a rota de sempre; a marca de "lavrada" vai na mesma transação do ato; minuta lavrada não se revisa nem se apaga; descartar exige motivo escrito.
**Por quê.** Rascunho dentro da tabela de atos ocupa número alheio ou quebra a corrente ao ser apagado; duas portas de lavratura dariam duas versões da regra que numera e sela.
**No código.** `ri_rascunho.py`, `ri_minuta.py`.

### Leitura por máquina propõe, com a frase de onde tirou cada campo; quem confere grava
**Regra.** Leitura automática de teor ou arquivo grava só propostas, cada campo com a citação de onde saiu; campo sem citação vai para a lista do que falta. Só a confirmação humana grava na ficha, e nova leitura não desfaz a decisão de quem conferiu. Prefere-se perder casos a achar errado; valor ambíguo devolve `None`; conversão de unidade mora numa função só; palavra no texto lembra, não marca caixa de decisão.
**Por quê.** Escrever direto seria a máquina lavrando ato com conteúdo adivinhado, dentro da corrente de hash que existe para provar que nenhum ato foi inventado. Hectare lido como metro quadrado mandou a um índice nacional área dez mil vezes menor.
**No código.** `ri_numeros_do_teor.py` (teste varre `INSERT/UPDATE/DELETE`), `onr_endereco_do_teor.py`.

### O sistema prepara; quem decide é quem assina — e isso se prova por varredura de nomes
**Regra.** Módulos de apoio (fraudes, indisponibilidade, usucapião, habilitação, minutas, IA) não têm função pública que lavre, numere, sele, cobre, cancele, averbe, julgue ou recuse; há teste que varre os nomes públicos procurando esses verbos. Alerta não é trava. Onde o erro custa dinheiro do cliente, responde a pessoa numa pergunta explícita da tela, nunca uma dedução do sistema.
**Por quê.** Decisão é ato do delegatário; o sistema avisa e prepara.

### Conserto de dado em produção é script que só mede por padrão
**Regra.** O script só grava com `--confirmar`; tira cópia do banco (`VACUUM INTO`) antes; recusa ato com selo, com dinheiro, amarrado a outro registro ou fora da cauda da corrente de hash; usa a chave completa (tabela + id); recusa valor que não é exatamente o esperado; grava a auditoria à mão; é ensaiado contra cópia da produção. Depois de importação que insere direto na tabela de atos, comparam-se atos de origem manual com eventos de lavratura: o que sobra entrou por fora de selo, custas e auditoria.
**Por quê.** Apagar do meio da corrente deixa o seguinte apontando para hash inexistente; `ato_id` sozinho repete entre tabelas e apagaria registro de outra atribuição.
**No código.** `tools/atos_para_minutas_do_ri.py`.

## Avisos

### Alarme que soa sempre ninguém ouve: aviso nasce medido e tem saída
**Regra.** Pendência é declarada por quem a descobriu, com o fato medido, não listada por regra genérica; a frequência de um aviso novo é medida antes de ele existir. Todo aviso de conferência tem botão que registra quem conferiu e quando; dispensar exige motivo escrito, que fica mesmo se reaberto. Quando `NULL` significaria "nunca teve" e "resolvido", o terceiro estado tem coluna própria. Marca que explica uma consequência (prazo dobrado, regime especial) fica gravada, não só usada no cálculo.
**Por quê.** Avisos numa instalação limpa ensinam o balcão a ignorar o aviso; marca que volta depois de resolvida é pior que nenhuma; na correição a pergunta é "por que este prazo é diferente do vizinho".
**No código.** `implantacao.py`.

### Zero medido e zero por engano não podem ter a mesma cara
**Regra.** `except` largo não devolve lista vazia nem zero: só se perdoa a ausência esperada (tabela inexistente), devolvendo `None` com motivo. Valor desconhecido mostra traço, nunca zero. Palavra fora do vocabulário é exibida como é, com aviso, e não cai em vista nenhuma pelo `else`. `rowcount` zero onde se esperava gravação é recusa. Código de saída de processo externo não é prova: a prova é o arquivo produzido. Totais sob um filtro são os do filtro; lista vazia diz por quê.
**Por quê.** Zero com cara de medição faz o leitor parar de procurar; "registrado" sobre `UPDATE` de zero linhas deixa obrigação legal por cumprir.

## Varredores e testes

### As perguntas estruturais viram varredores com piso, que leem código e não palavra
**Regra.** Há varredores para: função pública de domínio sem tela que a chame; rota que grava sem tela (exceção estreita para webhook externo); formulário que grava sem `csrf_token`, no HTML renderizado; toda tela GET sem parâmetro abrindo num banco vazio; `url_for` para rota inexistente; versão da tabela de custas montada com a data de hoje. Cada um tem piso mínimo de itens varridos. Leem com `ast` (chamadas, imports inclusive `as`, literais que não são docstring, excluída pelo nó); em template, só expressões Jinja; regex de SQL distingue `UPDATE tabela` de `DO UPDATE SET`. Exceção vai em lista própria e datada.
**Por quê.** Testes de tela montam o POST com o token na mão e provam a rota, não a tela; função pronta sem tela foi o defeito mais repetido; tela vazia passa na produção e falha na casa recém-instalada. Varredor que deixa de achar passa calado.
**No código.** `tests/test_csrf_nas_telas.py`, `tests/test_debitos_do_balcao.py`, `tests/test_toda_tela_abre_em_instalacao_nova.py`.

### Teste compara com o artefato real; ensaio contra cópia da produção prova o dado
**Regra.** Teste de contrato compara a saída com o artefato real (envelope aceito, arquivo da Central, contrato guardado), por conteúdo e não por forma; ida e volta (ler arquivo real e reescrevê-lo idêntico) é o guarda mais forte de leitores e escritores; diferença nova exige explicação. Toda função que opera sobre acervo, e toda entrega, é ensaiada contra cópia da produção (`VACUUM INTO`), conferindo tabela a tabela, com `integrity_check` e `foreign_key_check`, e que a produção não mudou. Testes rodam com chave estrangeira ligada, inclusive carga rodada duas vezes e banco de versão anterior. O app de teste se monta uma vez por módulo, restaurando um seed por teste; os pesados levam a marca `lento`.
**Por quê.** Testes "contra o acervo" passavam com o defeito de pé porque remontavam o envelope com a mesma ideia errada do código. Banco vazio não vê defeito de continuidade; teste escrito à mão preenche tudo e passa onde o dado real tem `None`.
**No código.** `tests/conftest.py`, `pytest.ini`.

## Medir antes de decidir

### O acervo e os arquivos reais decidem, e a procedência fica marcada
**Regra.** Antes de decidir uma regra, mede-se no acervo e nos arquivos que a serventia enviou e recebeu. Cada valor guarda a procedência (`MEDIDO` = o que a casa mandou e foi aceito; `TABELA` = o que a norma ou tabela oficial diz). Na dúvida imita-se o precedente aceito; sem precedente, recusa-se e pergunta-se. O não medido é `A CONFERIR`, e campo de layout não decifrado chama-se `reservado_NNN` (teste impede batizá-lo). Ao corrigir, o comentário diz o que estava escrito e por que estava errado. Pedido que não bate com o dado não se cumpre ao pé da letra nem se recusa: mede-se e entrega-se o que se quis dizer.
**Por quê.** Nome plausível é o que mais se parece com medição sem ser; vários defeitos só foram achados porque o erro anterior estava documentado.

### Ausência onde se procurou não prova ausência, e nome não é significado
**Regra.** Coluna vazia prova que aquela coluna não é onde o dado mora; antes de deduzir um de-para, procura-se a coluna que já o tem e lê-se inteira a documentação que já está na casa. Nome de tabela ou coluna é afirmação de quem o criou: desempata o schema ou o estado do registro; `origem` diz de onde a linha veio, a data diz quando o ato aconteceu. Antes de afirmar o efeito de um caso, chama-se a função que o sistema usa e conta-se como o programa compara.
**Por quê.** Cada uma dessas conclusões apressadas já declarou pendente o que existia, escondeu casos reais ou levou a afirmar ao titular um número que o sistema nunca abriria.

### Regularidade de uma casa não é lei; um caso que separa vale mais que muitos que concordam
**Regra.** Padrão forte de uma serventia é convenção local até ser conferido em outra: layout nacional se prova com acervo de outra casa. Lacuna de layout se fecha com mais amostra, não com engenhosidade; busca exaustiva de combinações sempre "fecha" e não prova nada; o texto da norma prevalece sobre o deduzido; frequência medida em lote antigo pode estar medindo o passado. O contrato técnico diz como se manda; a tabela de emolumentos diz o que se cobra.

## Integração com as Centrais

### Formatos variam entre APIs e dentro da mesma API; a regra de transporte mora num lugar só
**Regra.** Cada API tem conversor próprio (ex.: CPF cru numa, mascarado na outra da mesma Central), e um teste compara os dois para ninguém igualá-los. Dinheiro, identificador e tipo de campo podem variar dentro da mesma API; obrigatório pode ir presente e nulo; binário pode vir como array de inteiros e não mora no banco. HTTPS forçado e «só GET se repete» ficam numa função comum.
**Por quê.** Quem subtrai valor sem converter lê outro número; regra de reenvio escrita duas vezes dá duas versões da linha que decide se um pedido sobe em duplicata.
**No código.** `onrcpn_api.py`, `onrcpn_certidao_api.py`.

### Catálogo oficial se transcreve e se confere; nunca se completa nem se mistura
**Regra.** `enum: ["64 = Casa", ...]` em campo inteiro é partido e transcrito para o código por gerador; repetições ficam declaradas; nunca se preenche a sequência «óbvia». Quando arquivo e API da mesma Central usam catálogos diferentes para o mesmo conceito, cada um mora no seu módulo e um teste exige que não compartilhem código. De-para já existente no acervo é procurado antes de deduzido; códigos se conferem por duas fontes. O dado se guarda como o papel o escreve; a forma do arquivo é conversão do gerador da remessa.
**Por quê.** Quem preenche a sequência acerta o tipo e erra o conteúdo; usar um catálogo pelo outro publica no índice nacional um valor errado sem erro em lugar nenhum.
**No código.** `tools/gerar_logradouros.py`, `onr_api.py`.

### A carga para Central mostra números, não veredito, e o formato mora num lugar só
**Regra.** A conferência mostra quanto falta ao lado do que a Central exige, sem dizer «pronto»; enviar base incompleta é decisão do delegatário. Onde o precedente aceito diverge do modelo, segue-se o precedente e a divergência aparece com os dois números; sujeira do acervo vai inteira e declarada. A carga completa chama o mesmo gerador da exportação periódica (teste recusa a marca do formato noutro módulo), e é comparada posição a posição com arquivos já aceitos — o que também revela defeitos do sistema anterior, que não se reproduzem. Onde a Central instala programa próprio de envio, o sistema prepara e confere, mas não transmite.
**Por quê.** Quem assina precisa saber o que manda; «limpar» pode estragar uma razão social. Duas montagens, ou dois caminhos gravando o mesmo fato, divergem no primeiro conserto.
**No código.** `onr_carga.py`, `ri_onr.py`.

### Terminar uma integração é medir e ler até o fim, e não se constrói transporte que não pode funcionar
**Regra.** Se a rota exige desafio de navegador ou assinatura por requisição com A3 que não pode ser carregado no servidor, a integração fica medida e documentada, com o que pedir à Central. Manual é relido inteiro antes de concluir; formulário de adesão é lido antes de recomendado, porque pode conter declarações sob assinatura digital. Conta que controla dados da serventia em nuvem é institucional.
**Por quê.** Tela que diz que dá, quando não dá, é pior que nenhuma; a chave do acervo não pode sair com quem sai da casa.

## Dado herdado do sistema anterior

### A carga copia e conta; não corrige nem inventa — e a certidão cobra o que faltou
**Regra.** Rejeitado, avisado e contado são contadores distintos, e `lidos = inseridos + rejeitados`; conta-se inserção efetiva (`lastrowid`). A chave de origem é da unidade representada (pessoa, posição no lote), não do contêiner. Registro com dado faltante que afeta terceiros entra marcado em vez de rejeitado. Inconsistência do acervo é copiada e contada; ligação quebrada usa `LEFT JOIN`. Escrever a certidão de cada atribuição testa a carga: o que ela precisa dizer tem de estar no banco, e o que falta entra por uma passada à parte, repetível, que alcança quem já rodou a carga.
**Por quê.** Com a chave da linha, o `INSERT OR IGNORE` engolia a segunda pessoa e a carga dizia «entraram vinte» com a tabela vazia; acervo importado vira o livro e não se desfaz.
**No código.** `acervo_carga.py`, `importar_padrao.py`.

## Atualização segura e método

### Atualização: a IA propõe, o desenvolvimento testa, o administrador aprova
**Regra.** Só o administrador recebe pacote; SHA-256 por canal separado; conferência de manifesto, caminhos, tamanhos e hashes; montagem em cópia isolada com inspeção estática sem importar código; aprovação repetindo o hash, digitando a confirmação e reinformando a senha. Aplicar exige backup, guarda cópia para rollback, testa a saúde e volta se falhar. O pacote não leva dado do acervo, cache, testes nem rascunhos; `VERSION` em `app.py` e `VERSAO.txt` mudam juntos.
**Por quê.** O servidor não pode executar código não aprovado; assinatura com chave pública fixada é a evolução recomendada. Cache de teste copiado ao servidor afirma falhas que não aconteceram ali.
**No código.** `update_manager.py`, `installer/aplicar_atualizacao.ps1`, `tools/criar_atualizacao.py`.

### A origem de uma falha se apura no pacote anterior, e falha alheia se declara
**Regra.** Os pacotes antigos são a linha do tempo do código: extrai-se o anterior numa cópia e rodam-se ali os testes vermelhos. Teste cuja mudança de contrato já está num pacote anterior é teste velho, a corrigir. Falha que não é da passada é declarada, não consertada por cima; antes de empacotar, compara-se a árvore com o pacote anterior por hash. A suíte não roda com a árvore sendo editada; conexões e arquivos se fecham em `finally`.
**Por quê.** Com mais de um trabalho na mesma árvore, a data de modificação mistura trabalhos; conserto por cima é sobrescrito.
**No código.** `tools/pytest_guard.py`.

### A pergunta da revisão é "quem está no guichê consegue terminar o atendimento?"
**Regra.** Construída a estrutura de cada atribuição, revisa-se ato por ato o que o balcão não consegue fazer. Duas perguntas acham classes inteiras: quais funções de domínio nenhuma tela chama; e o que acontece se ninguém rodou a carga e o primeiro cliente entra pela porta. Cadastrar um registro e praticar o ato irreversível ficam em passos separados.
**Por quê.** Os buracos mais graves passavam em todos os testes; acervo completo esconde buraco de fluxo, porque todo registro migrado já vem num estado posterior ao que falta.
