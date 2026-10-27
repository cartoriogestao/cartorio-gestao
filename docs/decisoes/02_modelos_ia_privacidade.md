# Papéis e modelos, telas e processos, IA, privacidade e fraude

Decisões sobre os textos que a serventia emite, a organização das telas e das pendências, a importação de acervo de outro sistema, a ajuda e os agentes de IA dentro do sistema, o tratamento de dados pessoais (LGPD) e a lista de atenção para fraudes.

## Modelos e papéis

### O código é o piso; a tabela é o ajuste; o catálogo guarda onde o texto mora
**Regra.** Todo papel tem texto de fábrica no programa; a serventia só grava linha quando ajusta, e «voltar ao padrão» é apagar a linha. O catálogo guarda onde o padrão mora (módulo e constante), não o texto, e há teste que busca cada constante onde o catálogo diz e exige que toda chave seja lida por alguma tela. Todos os papéis ficam num só armazém; telas por atribuição são portas dele; tabela antiga é lida como legado, com o ajuste novo prevalecendo.
**Por quê.** Nada se perde e a instalação nova nasce funcionando. Duas cópias do texto, ou duas telas gravando em tabelas diferentes, divergem: o operador edita e o papel não muda.
**No código.** `modelos_da_casa.py` (`CATALOGO`, `corpo_de`), `mo_modelos`, `mo_elementos`, `tools/inventario_modelos.py`.

### O formato do marcador é declarado, e a conferência usa a régua da impressão
**Regra.** Cada modelo declara `JINJA` (`{{ a.campo }}`, com condição e repetição) ou `CHAVES` (`{campo}`, frases prontas montadas pelo módulo). A tela confere com a mesma função que imprime, no mesmo ambiente restrito (`SandboxedEnvironment`), antes de gravar, e recusa; corpo vazio volta ao padrão. Com dado real disponível, confere-se também contra um registro de verdade — e «conferi» (`""`) não é «não havia com que conferir» (`None`).
**Por quê.** `str.format` não estoura com `{{ a.nome }}`: imprime `{ a.nome }` no papel assinado. Gravar e avisar depois faz o escrevente descobrir o erro com o cliente na frente; folha em branco assinada é pior que modelo feio.
**No código.** `rc_modelos_do_livro.conferir_corpo`.

### Modelos se compõem por elementos com herança, e «nada muda» se prova byte a byte
**Regra.** Encerramento e rodapé podem ser comuns à atribuição e trocados por ato (ato > legado do papel > atribuição > código); o corpo nunca é comum; o cabeçalho/timbre fica fora do texto livre, montado em código na ordem normativa. Elementos novos nascem vazios e não entram na junção; a função de composição mantém nome e assinatura; a uniformidade do formato dentro da atribuição é medida, não suposta. Quem edita vê só o elemento editado. Antes de subir, cada papel é comparado byte a byte com o padrão.
**Por quê.** Corpo comum apagaria todos os papéis da atribuição. Um `strip()` na junção tirou a quebra final de vários papéis, um deles XML de molde ODT — isso não se vê lendo. Mostrar o documento composto faria o fecho ser gravado dentro do corpo e sair duas vezes.
**No código.** `modelos_elementos.py`, `rc_cabecalho.py`.

### Minuta, papel e molde são coisas diferentes
**Regra.** Papel assinado: catálogo. Molde ODT de layout fixo: armazém de moldes. Minuta de ato: fluxo da atribuição. Textos montados por campo (certidão no modelo nacional, termos e certidões de protesto) não viram modelo livre. Marcadores `[CAMPO]`, `{ESCOLHA}` ou `{{` não resolvidos não chegam ao papel assinado. Constante chamada «modelo» que não é papel (ex.: URL do QR do selo) fica fora.
**Por quê.** Campo fora do lugar é certidão errada, não questão de gosto; passar uma URL de `str.format` pela conferência Jinja aprovaria o que o QR não sabe montar.
**No código.** `modelos_moldes.py`, `nt_modelos`, `ri_minutas`.

### Parágrafo vazio escrito pelo próprio sistema é linha em branco no papel
**Regra.** Na conversão HTML→ODT, `<p></p>` sem atributo vira parágrafo vazio sem estilo, decidido no fecho de `</p>`; parágrafos vazios com estilo vindos de editor externo continuam descartados.
**Por quê.** Descartar todo vazio comia o espaço de assinatura de todos os papéis; reter todos esticaria teores importados e mudaria certidões sem decisão de quem assina. Teste que mede espaço não pode normalizar espaço ao ler.
**No código.** `ri_odt.html_para_odf`.

### Documento avulso não lavra, e o claro vazio aparece antes de imprimir
**Regra.** Modelo avulso é nome, espécie, texto e ativo, com chave `(espécie, nome)`; a espécie não muda depois de gravada; desativar não apaga; não numera nem sela. A montagem devolve o texto e a lista dos claros vazios, numa faixa fora da impressão. Cada claro declara de onde sai: coluna própria primeiro, dado bruto do sistema anterior só quando ela está vazia.
**Por quê.** Trocar a espécie troca o vocabulário debaixo do texto; o modelo que já imprimiu explica o papel na mão do cidadão; claro vazio descoberto depois de assinado não se conserta. Ler só a coluna deixaria o acervo em branco; ler o legado primeiro faria a correção feita na tela nunca chegar ao papel.
**No código.** `rc_modelos_livres.py`.

### Ao trazer modelos de outro sistema, copia-se o que é usado, e a conversão não adivinha nem apaga
**Regra.** Coluna vazia em todas as linhas não vira campo. O de-para de marcadores tem os dois lados medidos, compara sem caixa e tem camada por espécie (o mesmo marcador nomeia pessoas diferentes em nascimento e casamento); marcador desconhecido fica no texto e volta listado na tela. A contagem de marcadores se confere no texto real: palavra de controle RTF se corta por fronteira, e marcador não começa logo após letra ou dígito. A prova é converter todos os modelos reais de ponta a ponta.
**Por quê.** Apagar faz descobrir o buraco no papel impresso; adivinhar põe dado errado sob o rótulo certo; a cauda de um e-mail seria lida como marcador; medição errada devolve número plausível e não avisa.
**No código.** `rc_modelos_livres.py`.

## Telas, menu e alcance

### A cor do módulo é identidade, calculada e sempre com o nome
**Regra.** A cor aparece numa faixa, numa etiqueta com o nome do módulo e na marca do grupo no menu, nunca no fundo. Declara-se o matiz, longe dos vizinhos e dos matizes reservados a erro, atenção e feito; a cor é calculada até sustentar texto branco a 5:1; submódulos derivam por cálculo.
**Por quê.** Cor sem nome é adivinhação; fundo colorido cansa; paleta a olho caiu sobre a cor de «atenção» e abaixo do contraste mínimo.
**No código.** `modulos.py`.

### Uma régua para «qual módulo é esta tela», e o menu na ordem do dia
**Regra.** A mesma função decide grupo do menu, cor, rótulo e guarda de alcance, testada contra todas as rotas. Ordem: o que o balcão faz o dia todo, depois consulta e acervo, por último o que é do titular; mais de seis itens exige seções; processos que duram meses ficam em seção própria. Seção vazia e dois itens para o mesmo endereço são recusados; a mesma tela em módulos diferentes abre filtrada e diz que está filtrada.
**Por quê.** Regras duplicadas divergem; item novo entra onde é cômodo escrever, não onde é cômodo achar; lista filtrada que parece inteira engana.
**No código.** `modulos.py`.

### O alcance de módulos e da IA mora em configuração; o administrador nunca sai e só ele configura
**Regra.** Quem alcança módulos, funções sensíveis e a consulta à IA é configuração editável na tela (só o titular / todos / ninguém), com as mudanças registradas. O administrador não pode ser removido, só ele configura, e quem configura não é alcançado pela própria regra. Desligar módulo governa a vista e nunca apaga ato nem pendência; a marca da versão anterior é migrada com o sentido que tinha.
**Por quê.** Regra num decorador faria abrir para o balcão depender de programador; quem muda a regra não pode se trancar fora nem ser alcançado por ela.
**No código.** `modulos.py`, `modulos_ligados.py`, `ajuda.py` (`aj_config`).

## Processos e pendências

### A lista do que não terminou é uma lente, não uma gaveta, e cada item leva à tela certa
**Regra.** Pendências são medidas na hora das tabelas onde os atos moram; ato concluído sai sozinho. O único dado novo é a anotação (quem cuida, até quando, o que falta), e apagá-la não tira o item. A fonte (tabela, início, término) mora no código; ligar, desligar e os dias até «parado» moram no banco, com padrão quando não há ajuste. Ajustar é do gestor; ver é de todos; a lista não conclui nem lavra. Testes executam a consulta de cada fonte contra o esquema real e conferem que a tela de destino existe e recebe o `id` que espera; fonte que falha volta com o motivo, nunca como lista vazia.
**Por quê.** Registro paralelo de expediente diverge: ato concluído com expediente aberto é o defeito a evitar. Testar «desligado» com `or` religaria a fonte (zero é falso) — usa-se `is None`. Coluna errada vira lista vazia que ninguém nota; `id` da tabela errada abre a ficha de outro registro, e ninguém desconfia de ficha que abre.
**Fundamento.** Código Civil, art. 1.532 (prazo da habilitação, usado como padrão da fonte).
**No código.** `inacabados.py`, `ex_fontes`, `ex_anotacoes`.

### O acervo não vira atraso
**Regra.** Listas com prazo contam só o que o sistema lavrou: a régua é a data do ato, não a origem da linha. Toda fonte que lê tabela com coluna de origem declara o que faz com o acervo; lista que o conta de propósito declara o motivo (carga histórica para a Central; inclusão de CPF em assentos antigos; comunicação de nascimento indígena; ordem de gêmeos). Um varredor semeia acervo em miniatura e exige que toda função de pendência nova se declare.
**Por quê.** O registro antigo foi digitado agora, mas aconteceu há décadas; mostrado como atraso de hoje, ensina o balcão a ignorar o aviso. O mesmo número pode ser defeito numa tela e o esperado em outra.
**Fundamento.** (norma estadual — TJMA, Código de Normas, arts. 233, 253 e 347; confira o Código de Normas do seu estado).
**No código.** `tests/test_o_acervo_nao_vira_atraso.py`.

### Processo é a pasta; o ato é a peça
**Regra.** O que não se resolve na hora (mandado, pedido com prazo, prenotação, item de inspeção, tarefa) é processo com número único, origem, tipo, responsável, prazo, andamento e encerramento com prova; firma, autenticação e certidão de balcão não viram processo. O processo aponta para assento, matrícula, ato e prenotação sem copiá-los e reúne os documentos de todos os vínculos. Unifica-se tarefa e expediente sem migrar nem apagar: mesma tabela e número, entrada do malote aguardando «abrir processo» ou «só ciência», endereços antigos válidos, robôs abrindo processo com guarda contra repetição pela mesma régua de «aberto».
**Por quê.** Documento guardado por entidade só aparece na tela daquela entidade, e o responsável ficou sem o mandado; migração é risco evitável; régua diferente da lista engoliu tarefa nova.
**No código.** `processos.py`, `processo_pasta.py`, `pr_vinculos`.

## Importação de acervo de outro sistema

### JSON com campos iguais às colunas, chave de origem e recusa por linha
**Regra.** Cabeçalho `formato`, `versao`, `especie`, `de_onde_veio` e a lista `registros`; campos são os nomes das colunas, com a lista gerada do esquema (a tela entrega o modelo em branco). Cada registro tem `chave` de origem, que não é coluna; chave já gravada é «repetida», não erro. Recusa-se com linha e motivo: campo desconhecido, obrigatório ausente, data fora de `AAAA-MM-DD`, chave ausente ou duplicada, campos da máquina (`id`, `criado_em`, `origem`, `*_norm`). O recusado não derruba o resto; conferir e importar são dois botões.
**Por quê.** Lista de campos escrita à mão envelhece; nome de campo errado é o erro mais invisível; `id` no arquivo sobrescreveria registro alheio; acervo importado vira o livro e não se desfaz.
**No código.** `importar_padrao.py`.

### Importar traz acervo; preencher o formulário leva a um ato novo
**Regra.** Importar não lavra, não numera, não sela, não cobra e não conserta. Preencher leva um único registro à tela de lavrar, com as mesmas recusas; o que a tela não pergunta é listado num aviso (lista medida do template); o dado é consumido uma vez e nunca vai pela query string.
**Por quê.** Confundir os dois faria ato novo com número de outra casa ou acervo gastando folha de segurança; preenchimento guardado abriria o formulário do próximo cliente com dados do anterior; dado pessoal em URL fica em histórico e log.

## Ajuda e agentes de IA

### A IA auxilia e não decide, e o que ela diz entra «a conferir»
**Regra.** A instrução dada ao modelo proíbe inventar número, selo, matrícula ou prazo; análise de IA entra «a conferir». Os módulos de IA estão entre os de apoio sem função pública que lavre, numere, sele, cobre, cancele ou decida (a varredura de nomes está em `08_arquitetura_e_metodo.md`).
**Por quê.** Decisão é ato do delegatário; número chutado vira documento errado na mão de alguém.
**No código.** `ajuda.py`.

### Chave fora do banco, consulta fora da transação, teto de gasto e falha registrada
**Regra.** Chaves de API ficam em arquivo `.cred` na pasta de dados (teste varre o banco); a forma é conferida por provedor. A consulta recebe o objeto de banco (`db`), não a conexão, abre a própria transação curta, tem prazo curto e não trava o atendimento. Há teto diário de consultas, tokens e turnos, em limite duro. Registram-se também as consultas que falharam. Um único transporte atende todos os provedores, com biblioteca padrão.
**Por quê.** O banco viaja no backup; rede dentro de `BEGIN IMMEDIATE` põe a casa no `busy_timeout`; cobrança por token deixa um laço gastar sem ninguém ver; dia sem internet não pode parecer dia sem perguntas; clientes duplicados divergem.
**No código.** `agente_provedores.py`, `ajuda.consultar`.

### Mascarar por padrão, inclusive na pergunta; mostrar antes pela mesma função; guardar o que saiu
**Regra.** CPF, telefone e e-mail são mascarados no texto colado, na pergunta e no contexto; enviar sem máscara é escolha explícita, registrada e listada. A prévia do que sairia é montada pela mesma função do envio e não gasta consulta. Guarda-se o texto enviado inteiro, a resposta, usuário, custo e máscara; a falha também.
**Por quê.** Texto para ferramenta externa é papel que deixa a casa; mascarar só o colado deixa a porta aberta pela pergunta; prévia «parecida» mostraria uma coisa e mandaria outra; «o sistema sugeriu isso?» não admite opinião como resposta.
**No código.** `ajuda_privacidade.py`, `serventia.mascarar_texto`.

### A ajuda está em toda tela e sabe do sistema por medição, sem dado de cliente
**Regra.** A janela mora no template-base (teste varre as telas), funciona sem JavaScript e pega a tela de origem do `request.endpoint`. O mapa é medido em execução: telas do `url_map`, nomes do menu, arquivos do módulo da view, tabelas do catálogo do banco. Vai em fatia (a da tela de origem), com o corte declarado, e leva nomes de tabela e coluna, nunca valores — teste monta banco com CPF, nome e endereço e confere que nenhum chega ao mapa. A documentação viaja no pacote e vai por índice; nome de documento passa por `Path(nome).name`.
**Por quê.** Ajuda ligada tela a tela falta na próxima tela; lista escrita à mão é lida por uma máquina que responde com convicção; a máscara protege o que se digita, não o que o sistema junta sozinho; nome vindo da tela não pode virar caminho.
**No código.** `ajuda_mapa.py`, `ajuda_projeto.py`, `templates/_ajuda.html`.

### A tela que estoura vira problema anotado sozinho, e o relatório sai mascarado
**Regra.** Exceção vira linha com tela, usuário e ponto do programa; impressão digital com números trocados por `#`, única no banco, com contador; reaparecer depois de relatado reabre e fica em destaque. Anotar nunca estoura; disputa de escrita vai para arquivo, não para o banco. O balcão vê mensagem sem jargão e pode avisar problema sem perfil de consulta. A conferência da casa é pedida, mede e não conserta, e casa em ordem não gera achado. O relatório passa pela máscara, fica em disco com SHA-256 e marca como relatado só o que coube.
**Por quê.** Lembrança de balcão se perde; um defeito não pode virar dois; gravar no banco que travou disputa a mesma trava; traceback carrega o que estava sendo gravado; marcar o que não coube tiraria da lista o que ninguém recebeu.
**No código.** `ajuda_problemas.py`.

### As notas do desenvolvimento viajam no pacote e entram como migração de dado
**Regra.** O que foi feito em cada relato é empacotado e aplicado ao abrir o banco, casando pela impressão digital, não pelo número. Nota editada por pessoa nunca é sobrescrita, e nota nenhuma fecha problema. A prova citada tem de ser arquivo que existe, e um varredor confere.
**Por quê.** Quem desenvolve só lê o banco do servidor; `id` muda entre bancos; «atendido» é opinião sobre o conserto; nome plausível de teste é o que mais se parece com prova sem ser.
**No código.** `notas_do_desenvolvimento.py`.

### Base de conhecimento única, carregada uma vez, e erro nunca vira zero
**Regra.** Documentos, regras e verbetes são indexados em memória uma vez por processo, sem acento calculado na carga, com cache conferido pela assinatura dos arquivos em intervalo curto. A busca pontua frase exata acima de palavras soltas e avisa, espalha achados entre origens e, sem achado, diz que ausência de texto não prova ausência da coisa; todas as portas usam a mesma função; o trecho não colapsa espaços. Falha de leitura aparece como falha, nunca como lista vazia. Verbetes só o gestor escreve, com auditoria.
**Por quê.** Reler o disco a cada pergunta era ordens de grandeza mais caro; um `except` largo já transformou função inexistente em «zero pendências»; o que a ajuda lê é respondido com convicção.
**No código.** `ajuda_base.py`, `aj_verbetes`.

### Diagnóstico lê código e anexos, mas não executa nada
**Regra.** Leitura de código só de arquivos conhecidos dentro da pasta do sistema, nunca testes ou instaladores. Anexo é processado em memória, com limites de tamanho e páginas; banco, executável e compactado são recusados; sai só o texto extraído, sem o nome do arquivo, pela mesma barreira; instrução dentro do anexo é dado não confiável.
**Por quê.** Diagnóstico não pode virar canal de alteração, vazamento ou instrução injetada.

### O revisor por IA só lê e só cita o que é citável
**Regra.** O revisor registral lê código, norma e acervo e devolve achados com fonte, sem escrever nada; os achados são conferidos linha a linha antes de chegar ao titular, e ele declara o que não conferiu. Cita só doutrina em texto digital com paginação marcada; digitalização com OCR serve para ler, não para citar.
**Por quê.** Citação entre aspas de texto deturpado pelo OCR afirma palavras que o autor não escreveu.

### Agente com escrita nasce desligado; robôs agem com humano no loop
**Regra.** O agente administrativo é separado da ajuda; ferramentas de escrita só aparecem quando o titular liga, cada mudança guarda antes e depois e se desfaz; não toca em ato, selo, cobrança ou caixa nem lê credenciais. Robôs de atendimento só preparam rascunho, nunca gravam no livro nem enviam sozinhos, agem com o usuário humano vinculado (não há usuário com nome de robô, e o selo recusa esse rótulo), só na rede local, com chaves fora do código e fora dos logs.
**Por quê.** «Conserta sozinho» sem volta é «quebra sozinho»; ato e selo exigem responsável humano identificado.
**No código.** `agente.py`, `agente_ferramentas.py`, `robo_web.py`.

## Privacidade (LGPD)

### Tratamento por IA entra no inventário e no RIPD antes de valer
**Regra.** Cada uso de IA sobre documentos é descrito: titulares, dados pessoais e sensíveis, finalidade, base legal, operador, transferência internacional, o que sai, o que se registra, guarda na serventia e no operador, quem acessa e se há decisão automatizada. Cada envio guarda arquivo, página, modelo, tokens, data e usuário, com auditoria; a leitura vira rascunho conferido com o original e lavrado por pessoa.
**Por quê.** Envio a provedor é transferência a operador; sem registro não se responde ao titular nem à correição; sem decisão automatizada, não incide o regime do art. 20.
**Fundamento.** LGPD, arts. 7º, II e III; 11, II, «a» e «b»; 20; 23, § 4º; 33.
**No código.** `rc_leitura_documentos.py`, `rc_leituras`; desde 26/10/2026 também as Notas — `leitura_ia.py` (o motor comum), `nt_leitura_documentos.py`, `nt_leituras` (com `retencao_dias = 30` e `sem_mascara = 1` em cada linha).

### Anonimizar onde a finalidade permite; exceção delimitada e justificada
**Regra.** A regra é mascarar o que sai. Quando a finalidade é transcrever o próprio dado (leitura de DNV, DO e documentos para o rascunho do assento; e, desde 26/10/2026, de RG, CIN, CNH, CRLV, CRV e ATPV para o rascunho do cartão de autógrafo e do veículo nas Notas — «autorizo ia sem mascara. trabalharemos com o prazo de retencao de 30 dias da api», o oficial), o envio sem máscara é exceção restrita a esse uso, justificada por escrito, só com as páginas daquele registro, sem deixar arquivos guardados no provedor, e com a retenção do operador conferida na fonte oficial, citada com data e revista a cada revisão do relatório.
**Por quê.** Mascarar inutilizaria o serviço e devolveria a digitação manual com mais erro; exceção sem limites viraria regra.
**Fundamento.** LGPD, art. 11, II; Lei 6.015/1973, arts. 16 a 21, 54 e 80.

### Mensageiro externo não expõe o servidor nem envia dado sensível sozinho
**Regra.** Usa-se a API oficial do provedor; o servidor não recebe conexão de fora (caixa-postal externa recebe o webhook, o servidor busca por saída HTTPS). O webhook exige HMAC-SHA256 sobre o corpo cru, conferido com `hmac.compare_digest`; cabeçalho de teste não abre a porta havendo segredo; segredos fora do código. Autoenvio desligado; nunca se envia sozinho CPF, valor, protesto, certidão ou dado de livro, nem horário inventado. É a única rota que grava sem tela, declarada como exceção.
**Por quê.** Cabeçalho que vem de fora não abre porta sozinho; sem isso era possível injetar mensagem falsa na fila do balcão.
**No código.** `wa_balcao.py`, `wa_web.py`, `wa_puxar.py`.

### O atendente com IA responde sozinho em quatro casos, e o resto passa a uma pessoa (26/10/2026)
**Regra.** A regra «autoenvio desligado» acima foi revogada pelo titular em 26/10/2026 **só para quatro casos**: (1) andamento do protocolo, depois da identificação por número e código de acompanhamento impresso no recibo, com limite de tentativas por telefone e a mesma resposta quer o número exista quer não; (2) dúvidas gerais a partir de um texto-base aprovado pelo titular e editável na tela — resposta com número fora do texto-base, valor em dinheiro ou marcador de dado ocultado não sai; (3) valores pela tabela de emolumentos, sempre como estimativa, com o número calculado pelo motor de custas da casa e não pelo modelo, que só escolhe o item de uma lista aprovada; (4) transcrição do áudio do cliente. Tudo o mais — pedido do cliente, dúvida que a IA não sabe, protesto, registro civil, dado pessoal, reclamação — passa a uma pessoa com a conversa marcada para o setor. Interruptor geral desligado de fábrica (só o administrador liga, e só se responde o que chegou depois de ligado); cada resposta automática é registrada com o que a IA leu (mascarado), o que respondeu, provedor, tokens e custo. O que vai ao modelo passa pela máscara; o áudio vai inteiro ao provedor de transcrição, e a tela diz isso. Rede nunca dentro de transação.
**Por quê.** Pedido do titular («é importante»). A regra antiga continua valendo para todo o resto: o que a IA pode afirmar ao cliente fica limitado ao que a casa aprovou ou calcula, e o que é sensível continua com uma pessoa.
**No código.** `wa_atendente.py`, `wa_transcricao.py`, `wa_fila.py`, `wa_ia_registro`.

## Atenção para fraudes

### Alerta não é trava, a vítima se protege, e documento vem antes do nome
**Regra.** A lista avisa e não recusa ato (teste contra funções de bloquear ou recusar). O texto muda com o papel — vítima, envolvido, nome em documento fraudado —, e o da vítima diz que, conferida a identidade, o ato segue. Todo cadastro exige procedência (comunicação, órgão, data). Achados por documento vêm antes dos por nome, que trazem ressalva de homônimo; a consulta mostra os atos que a casa já tem daquela pessoa.
**Por quê.** Homônimo é a regra e recusar ato é decisão do titular; barrar a vítima repete o fraudador; alerta sem procedência não se avalia; documento não tem homônimo.
**No código.** `fraude.py`, `fr_schema.py`.

### Toda porta de entrada avisa, e fica o rastro de que o aviso foi visto
**Regra.** O alerta aparece no protocolo do balcão (o ato requerido) e nas fichas de protesto, assento, RCPJ/RTD, Livro 3, notas e matrícula, por uma macro única; no RI, ao lado da consulta de indisponibilidade, sem substituí-la. Consulta é de todos; cadastro, do titular e do gerente. Grava-se quem viu, quando, sobre qual ato e o que decidiu — só ao reconhecer, nunca ao mostrar. Sair da lista é inativar com motivo, nunca apagar.
**Por quê.** Aviso depois de lavrado chega tarde; «o sistema avisou?» exige resposta escrita; tela de leitura que grava prende o banco; comunicação de fraude é documento.
**No código.** `templates/_fraude.html`, `fr_conferencias`.
