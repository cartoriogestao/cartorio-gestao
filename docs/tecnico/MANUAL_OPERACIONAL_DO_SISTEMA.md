# Manual completo de operação do Cartório Gestão

Versão de referência: 3.6.173. Data: 22/09/2026. Público: balcão, escreventes, conferentes, administradores e oficial. Este arquivo é a fonte textual do PDF e entra diretamente na base pesquisável dos módulos Ajuda e Agente como documento do projeto. O segundo volume, `MANUAL_TELAS_E_CAMPOS.md`, cobre as 162 entradas do menu e mais 102 telas de ficha, etapa ou documento identificadas no código desta versão.

## Como usar este manual

Os nomes entre aspas são os nomes apresentados no menu. Comece pela atribuição, abra a ficha do registro ou processo e confira as ações disponíveis para seu perfil. Os papéis ADMIN, MANAGER, USER e AUDITOR têm acessos diferentes; uma opção ausente pode decorrer do perfil ou de um módulo desabilitado. Antes de praticar ato, confira os dados, o documento original, o teor, o valor e o selo. O sistema auxilia a operação e mantém rastros; a qualificação e a decisão jurídica pertencem à pessoa competente.

Para uma dúvida durante o trabalho, use a janela Ajuda no canto da tela, sem abandonar o formulário. Informe o que tentou fazer, a tela, o número do registro ou protocolo e a mensagem de erro. Evite colar dados pessoais desnecessários. A Ajuda permite ver o contexto antes de enviá-lo ao provedor de IA; a consulta externa pode mascarar dados pessoais. Respostas da Ajuda e do Agente são orientação e devem ser conferidas na ficha e nas normas aplicáveis.

## Mapa de navegação

O menu principal reúne: Visão geral; Tabelionato de Notas; Registro de Imóveis; Protesto; Registro Civil das Pessoas Naturais; RCPJ e RTD; Livros e acervo; Malote; Administrativo. Dentro de cada grupo, as seções seguem o trabalho do dia. A Visão geral mostra indicadores e pendências. O grupo Administrativo reúne caixa, atendimento, obrigações, ajuda e configuração. Alguns grupos e ações dependem do papel do usuário.

### Primeiro acesso e rotina diária

1. Entre com usuário e senha próprios. Não compartilhe credenciais; cada ação relevante é associada a quem a executou.
2. Abra Visão geral e examine avisos, tarefas vencidas, protocolos parados, atos sem conclusão e comunicações pendentes.
3. Consulte as filas da atribuição em que trabalhará: prenotações no RI, habilitações no RCPN, remessas no Protesto, pendências de escrituras em Notas.
4. Abra o caixa do dia antes de receber valores. Identifique pagador, forma de pagamento, serviço e protocolo.
5. Ao terminar cada ato, confira o documento final, o selo, o recibo e o destino de eventual comunicação. Ao fim do dia, faça o encerramento dos livros e o fechamento do caixa conforme as telas próprias.

### Pesquisa e fichas

As listas levam às fichas. Pesquise pelo identificador próprio da atribuição: matrícula no RI, número do assento ou matrícula nacional no RCPN, registro no Livro 3, título ou protocolo no Protesto. Confirme o resultado antes de editar: pessoas com nomes semelhantes e importações antigas podem gerar duplicidade aparente. Nas fichas, consulte histórico, anexos, imagens, averbações, certidões e auditoria. Não use uma certidão antiga para inferir o estado atual do registro.

## Regras comuns a todos os atos

### Minuta, conferência, lavratura e selo

Separe o rascunho do ato lavrado. A minuta permite revisar texto, partes e documentos antes de reservar posição definitiva no livro. Use a prévia para conferir exatamente o que sairá; marcadores como `[CAMPO]`, `{ESCOLHA}` ou `{{ ... }}` indicam informação ainda pendente e não devem aparecer no papel assinado. Revise natureza, nomes, CPF/CNPJ, livro, folha, termo, matrícula, custas e fundamento.

O selo é tratado como etapa verificável. Se a emissão falhar, leia o motivo mostrado na tela e confira configuração, item de custas, dados obrigatórios, comunicação com o selador e situação do ato. Não repita o pedido às cegas: o mesmo identificador de solicitação permite recuperar um selo já obtido, e selos obtidos mas não vinculados aparecem no razão. O bloqueio ou a exceção para seguir sem selo depende da regra da tela e de decisão de quem lavra; registre o motivo quando a tela permitir. Nunca copie um número de selo de outro ato. O módulo Administrativo > Selos emitidos permite localizar selos disponíveis, vinculados ou cancelados.

Se a falha for de rede ou do serviço de selagem, anote a mensagem exata e consulte Administrativo > Selador - configuração. Corrija a causa e retome pela ficha do mesmo ato. Para selação posterior ou selo externo, use a ação própria da atribuição, com conferência de duplicidade e motivo quando exigido.

### Certidões e documentos

Escolha a atribuição, localize o registro e selecione a espécie de certidão. Confira nome, número, teor principal, averbações e anotações que devem constar, além do emissor e do espaço de assinatura quando o modelo exigir. Use a prévia e o documento gerado antes de entregar. Uma segunda via é uma nova emissão sobre o registro existente; ela não cria outro registro. Caso a geração informe sucesso mas o papel não apareça, retorne à ficha e procure o link do documento no histórico ou andamento. Se faltar o link, registre problema na Ajuda com a tela e o identificador.

### Acervo importado e ato novo

Importar é trazer informação preexistente. A importação deve preservar o teor e a origem e não deve inventar dado que o documento não comprova. Uma informação de acervo pode não ter selo ou responsável pela lavratura no sistema atual, porque foi praticada antes da carga. No RI, matrículas abaixo de 4015 são tratadas como acervo nesta instalação; observe a origem indicada na ficha. Para atos novos, a validação de selo e identificação de quem lavrou seguem o fluxo atual. Antes de importar lote, use a conferência sem gravação, examine rejeições e duplicidades e só então confirme. Depois, verifique amostras na ficha e na certidão.

### Correção, cancelamento e auditoria

Use a ação específica de retificação, cancelamento, expurgo ou estorno. Não apague a história do ato para fazê-lo desaparecer. As telas de correção registram antes, depois, autor e motivo quando necessário. Uma averbação duplicada ou equivocada deve ser analisada na ficha e cancelada pela função própria, preservando a averbação correta e seu selo. O cancelamento de selo exige motivo escrito. Se a correção mudar documento já entregue ou comunicado a uma central, confira também a necessidade de retificação e nova comunicação.

## Tabelionato de Notas

### Reconhecimento de firma e autenticação

Abra Tabelionato de Notas > Reconhecer firma. Localize o cartão de autógrafo, confirme a pessoa, a modalidade e a assinatura que será reconhecida. Preencha os nomes e os itens exigidos pela tela; confira emolumentos e o selo antes de imprimir a etiqueta. A lista dos reconhecimentos praticados fica na própria área do reconhecimento. Para cópias, use Autenticar cópia e informe a quantidade correta. Se o selo não sair, observe a mensagem e consulte o razão antes de tentar novamente. O ato e sua etiqueta devem apontar para o mesmo selo.

Em Cartões de autógrafo ficam cadastro e assinatura digitalizada; a carga antiga de assinaturas abastece esses cartões. Sinais públicos usam cadastro separado. O reconhecimento de sinal é ato próprio, acessível em Reconhecer sinal.

### Escrituras públicas, procurações e atas notariais

Em Escrituras públicas, abra ou localize a minuta. Escolha o modelo adequado, informe partes e qualificações, bens, valores e documentos de suporte. Confira pendências indicadas pela tela e o texto de cada cláusula. A prévia mostra como ficará o documento. Antes de lavrar, confirme livro, termo, folha, número de páginas e responsáveis. Cada ato começa em folha nova; frente e verso são controlados pelo sistema. Se sobrar uma face, imprima a inutilização gerada na ficha. O livro cheio é encerrado e o próximo segue a numeração da série.

Procurações e demais atos de livro seguem a mesma lógica de livro, folha, termo, partes, teor e selo; escolha a natureza correta. Em Atas notariais, descreva fatos observados, anexos e evidências, sem transformar a ata em decisão jurídica. Revise o teor antes da lavratura e confira o selo e o traslado. Em Pendências das escrituras estão os trabalhos iniciados que ainda exigem ação. Modelos dos documentos trata os papéis da atribuição; o corpo dos modelos de escritura também é controlado pelo catálogo de modelos de atos.

### Livros e remessas de Notas

Livros do tabelionato mostra capacidade, folha atual, termos e material para inutilização. Remessa às centrais reúne obrigações externas. Não deduza que uma remessa ocorreu porque o ato foi lavrado: confira protocolo, arquivo ou confirmação de envio na tela da central.

## Registro de Imóveis - Livro 2

### Protocolo, prenotação e matrícula

O título chega em Protocolo / prenotação. Identifique apresentante, título e dados necessários, gere o número e acompanhe exigências e prazo. Protocolo geral do caixa não substitui a prenotação do Livro 1. Depois da qualificação, localize a matrícula e prepare o ato em Rascunhos de ato. Revise a matrícula certa, titularidade, imóvel, partes, título e natureza do registro ou averbação. A lista O que revisar antes de selar mostra pendências registradas; Numeração dentro do teor ajuda a conferir referências no próprio texto.

Na ficha da matrícula, confira imagem digitalizada, teor, atos, selos e histórico. Imagem ausente na miniatura inicial pode exigir conferência em Fichas digitalizadas, que mostra arquivos e vínculos. Em Matrículas em Word, a comparação classifica entradas como novas, iguais, ampliadas, divergentes, ambíguas ou vazias; não confirme uma divergência sem revisar o documento. Indicador Real e Indicador Pessoal são índices de pesquisa e precisam concordar com a ficha.

### Certidão do RI e Livro 3

Em Certidões, selecione a matrícula e o tipo de certidão, confira atos e averbações relevantes, dados de quem emite e local de assinatura. A certidão deve refletir o estado atual da matrícula, inclusive cancelamentos. Para o Registro Auxiliar, use Livro 3 > Certidões do Livro 3: o teor principal e as averbações pertencem ao mesmo documento e precisam ser conferidos juntos.

Livro 3 oferece Registros, Minutas a revisar, O que revisar antes de selar e O que falta conferir. Na ficha, revise partes, número, texto, averbações, imagem e selo. É possível pré-visualizar a minuta com marca de rascunho, corrigir dados permitidos com auditoria, produzir ficha em ODT e conferir a digitalização. A renumeração de ato selado é recusada porque o número integra o selo. Para desfazer um ato e devolvê-lo à minuta, use a ação específica e consulte a ata de ocorrência, sem apagar a história.

### CNIB, ONR e obrigações

CNIB - indisponibilidade mostra as restrições; CNIB - o que espera seu okay destaca decisões pendentes. Consulte a cópia local e a Central e observe a data da última atualização antes de concluir que não há restrição. ONR - endereços a conferir prepara os dados do indicador real; ONR - índice real e editais acompanha a publicação. Exportação ONR e Carga do Next Cloud SAS são caminhos de envio distintos. A DOI é acessível em DOI - Receita Federal; confira arquivo, competência, recibo e situação de transmissão. CTP - prefeituras, Selos e emolumentos e Delegatários ficam no mesmo grupo de obrigação ou configuração, conforme o perfil.

### Usucapião extrajudicial e retificação de área

Usucapião extrajudicial é processo, com capa, peças, checklist, movimentações, notificações, ciência dos entes, edital, análise, decisão e registro. Cadastre requerentes, imóvel, titulares, confrontantes e endereços. Junte provas na ficha e confira o checklist antes de avançar. Gere as notificações dos titulares e confrontantes pela etapa própria, registre forma de entrega, tentativas e resposta. O botão de ciência aos entes gera três ofícios: União, Estado e Município. Depois de gerar, vá ao Andamento e use Abrir para imprimir em cada linha; a geração não exige recriar o processo. Registre a prova de entrega e os prazos.

O edital para terceiros e a contagem de prazo dependem da data de disponibilização e das regras do procedimento; confira a data informada pela Central. A análise organiza elementos do processo, mas a decisão é de quem tem atribuição para decidir. Em Retificação de área, siga a ficha do processo, os documentos técnicos, notificações e decisões registrados; não trate a retificação como simples edição do texto da matrícula.

## Registro Civil das Pessoas Naturais

### Nascimento, casamento e óbito

Em Nascimento, abra o novo assento, preencha dados do registrado, pais, declarante, local e demais campos exigidos. Confira o CPF do registrado, eventual condição de gêmeo, ordem de nascimento e o teor antes de lavrar. O cadastro de gêmeos e o CPF têm filas próprias. A primeira certidão e as segundas vias têm tratamentos distintos de selo; verifique a indicação da tela para a espécie concreta.

O casamento começa na Habilitação: cadastre os nubentes e confira documentos de cada um. Siga o edital de proclamas, registre a publicação pelo e-Proclamas ou o protocolo manual quando necessário, observe oposição e situação da habilitação e só então chegue às Prontas para casar. O registro do casamento e o teor ficam nas telas de Casamento. Não interprete a lista de uma fase como ato concluído; abra a ficha do processo e confira o próximo passo.

Em Óbito, registre a declaração e confira dados da pessoa, falecimento e declarante. A tela O que falta perguntar reúne situações que acionam comunicações, como eleitor, filhos, bens e pessoa não identificada. Confira o termo e a certidão antes de entregar.

### Assento já lavrado, CPF e segunda via

Retificação e suprimento é o caminho para corrigir, restaurar ou suprir assento, com fundamento e histórico. Use Atos sem checklist, Termos a escrever e Conferência da filiação para pendências do acervo. Informações importadas não devem ser confundidas com assentos novos. CPF nos assentos antigos trata a averbação em registros anteriores; examine se já existe averbação antes de criar outra, confira qual fica válida e use cancelamento na indevida. A matrícula nacional do assento deve aparecer completa no teor e na certidão; consulte a tela Matrículas se faltar ou estiver inconsistente.

Para segunda via, localize o assento existente, selecione a espécie e confira os dados atuais e as averbações antes de emitir. Caso uma importação tenha teor ou vínculo incompleto, registre o identificador e a mensagem na Ajuda; não duplique o assento para liberar a certidão. Confira o selo específico da segunda via ou a justificativa apresentada pelo sistema.

### Comunicações e remessas do RCPN

O que comunicar hoje é o painel de obrigações. As telas específicas incluem Remessa do SIRC, Comunicação à FUNAI, Carga da CRC, Anotações devidas, Anotação da CRC e Remessa do IBGE. Uma obrigação mostrada no painel não é prova de envio: valide o arquivo, destino, competência e recibo na tela correspondente. Comunicações mensais de óbito ficam junto da área de Óbito. Quando um retorno da CRC exige anotação, confira o texto sugerido e o assento de destino antes de gravar.

## Protesto de títulos

O roteiro das Centrais apresenta o ciclo diário. Pela manhã, confira arquivos bancários e desistências; ao receber remessa da CRA, confira os lotes antes de importar, confirme o recebimento e emita aviso de intimação. Verifique desistências novamente antes de protestar. Use Títulos para acompanhar cada apontamento, coobrigados, aviso, entrega, edital, pagamento e cancelamento. Em A protestar, confira o conjunto antes de gerar os instrumentos. O retorno final e o arquivo de andamento são produzidos como par; confira ambos em Retorno à CRA. A CENPROT tem etapas próprias de assinatura e transmissão.

Imagens dos títulos, Avisos e editais, Instrumentos, Certidões e Remessas ficam nas respectivas telas. Se um arquivo da Central tiver rejeições, leia o motivo por título; não conclua o lote inteiro como recebido ou enviado sem conferir o retorno. A desistência é especialmente sensível: faça a conferência nos momentos do dia indicados pelo roteiro da serventia.

## RCPJ e RTD

Um título apresentado entra em RTD - títulos apresentados ou RCPJ - títulos apresentados. Escolha a atribuição correta antes de protocolar. A ficha reúne apresentação, qualificação, exigências, registro, atos posteriores, documentos e selo. RCPJ - registros lavrados e RTD - registros lavrados são listas distintas; Últimos atos praticados facilita a conferência recente. Certidões de inteiro teor devem reproduzir o registro principal e os atos posteriores selecionados. Etiquetas de selos externos e Central ONRTDPJ têm filas próprias; confirme número, origem e protocolo externo antes de associá-los ao registro.

## Livros e acervo

Livros e termos mostra séries, livros, folhas, termos e situações. Encerramento diário fecha o movimento do dia e gera os documentos de escrituração pertinentes. Numeração dos livros é configuração restrita; não altere contador para corrigir um ato isolado. Em O que falta informar estão decisões que não podem ser deduzidas do acervo. Trazer o acervo do E-Ofício executa a carga própria daquela fonte. Importar de outro sistema aceita formato padronizado: primeiro confira o arquivo, leia conflitos e omissões e depois importe. Guarde identificação da origem e confira amostras de cada espécie depois da carga.

## Malote, tarefas e inspeções

Expedientes / Malote acompanha entradas, distribuição, prazo, resposta e arquivamento. Associe evidências e responsáveis. Tarefas e pendências é a lista operacional; concluir uma tarefa não deve ser tomado como encerramento automático do expediente, que tem etapa própria. Expedientes prontos para encerrar identifica os casos com trabalho terminado. Em Inspeções, registre achados, ações, responsáveis e prova de saneamento. O painel mostra atrasos e ajuda a priorizar.

## Administrativo e atendimento

### Caixa, protocolo, depósito e recibo

Em Caixa, abra o dia com o valor inicial em espécie. Para cada recebimento, informe natureza, forma de pagamento, valor, pagador, documento, descrição e protocolo quando houver. O recibo nasce do lançamento; emiti-lo congela o teor, e reabrir a via não cria recibo novo. Depósito prévio entra como recebimento; consumir o saldo não é nova receita; devolver o saldo gera saída. Com o caixa aberto, alterações e exclusões lógicas deixam histórico. Após o fechamento, corrija por estorno, com motivo. No fechamento, informe o valor contado e justifique divergência; PIX e cartão não entram no esperado de dinheiro físico.

Protocolo geral acompanha serviços do balcão até a entrega e permite corrigir contato. Protocolos parados mostra serviços sem andamento. Emolumentos e Selos emitidos permitem conferir composição e razão; não confundem o protocolo geral com a prenotação do RI.

### Atendimento, filas e governança

Atendimento / senhas organiza o balcão. WhatsApp e Robôs têm filas próprias. O que ficou pelo caminho reúne atos iniciados que pedem conclusão; Rascunhos guarda textos ainda não convertidos em ato. Consultar fraudes e Atenção para fraudes são instrumentos de consulta e alerta, não decisão automática de impedimento. Checklists e Obrigações recorrentes ajudam a cumprir tarefas periódicas. LGPD e governança, TI e infraestrutura, Auditoria e Integridade mostram controles administrativos e técnicos.

### Modelos, usuários e configuração

Modelos dos documentos e Modelos do caixa centralizam papéis editáveis. Antes de alterar um modelo, faça prévia de um exemplo e confira marcadores, cabeçalho, encerramento e rodapé. Selador - configuração guarda parâmetros de integração; alteração exige conferência. Rede / acesso mostra a situação de acesso local. Usuários e permissões são administrados pelo perfil autorizado. Corrigir dado do acervo tem fluxo próprio e não equivale a retificar ato já praticado.

## Ajuda e Agente

Ajuda do sistema responde dúvidas a partir do contexto da tela. Problemas do sistema recebe relatos de falha; informe o efeito real, o caminho para repetir e o identificador necessário. O que a ajuda sabe do projeto mostra documentos e regras. Base de conhecimento da ajuda combina documentos do projeto, regras da casa e verbetes escritos pelo oficial. Este manual está na fonte DOCUMENTO. Agente do sistema pode pesquisar essa mesma base pela ferramenta de busca geral e abrir documentos da pasta `DOCUMENTACAO`.

Para uma resposta verificável, peça o caminho de menu, a condição exigida e a fonte. Se a resposta citar versão antiga, confirme a versão atual em /saude ou no rodapé do sistema. Uma ausência na busca não prova ausência da função: abra a tela ou peça conferência do código. O Agente deve distinguir fato medido, texto de documentação, inferência e decisão pendente de pessoa responsável.

## Atualização, segurança e recuperação

Em Correções e atualizações, o administrador prepara um pacote `.cgu`, confere seu SHA-256 e o impacto, faz backup e aprova. A atualização reinicia o servidor; a tela de saúde precisa responder com a versão instalada. Se o sistema continuar na versão anterior, consulte o resultado e os logs antes de repetir. Backup deve incluir banco e arquivos do acervo. Não copie o SQLite aberto manualmente como forma de backup. A tela Integridade ajuda a identificar inconsistências; Auditoria mostra quem fez cada operação registrada.

Na rede local, o servidor convencional usa a porta configurada na instalação; outros computadores entram pelo cliente ou endereço informado em Rede / acesso. Se uma tela falhar, anote horário, URL, versão e mensagem. Se for erro de selo, inclua o SID ou identificador de tentativa quando exibido. Não envie senha, chave de API ou documento sigiloso em relato desnecessário.

## Problemas frequentes e primeira verificação

### O selo não foi emitido

Abra o ato e leia o motivo exibido. Confira item de custas, campos obrigatórios, serviço do selador e Selos emitidos para saber se um selo já foi obtido. Se houver selo solto, recupere o vínculo pela ação prevista; se não houver, corrija a causa e tente pelo mesmo ato. Não crie ato duplicado para pedir novo selo.

### A certidão de segunda via não sai

Confirme que o assento ou registro existe uma única vez, que o teor e a matrícula estão completos e que a espécie de certidão é a correta. Confira averbações, nome do emissor e mensagem de erro. Em caso de origem importada, examine campos ausentes na ficha e registre problema com o número do assento; não duplique o registro.

### O documento foi gerado mas não abre

Volte à ficha, consulte histórico ou andamento e procure Abrir para imprimir, Ver ou Baixar. No usucapião, os ofícios à União, ao Estado e ao Município ficam em linhas de Ciência no Andamento. Caso o link falte, registre tela, processo e horário na Ajuda.

### A imagem da matrícula não aparece

Confira a ficha e Fichas digitalizadas, inclusive vínculo, arquivo original, miniatura e histórico de substituição. Um arquivo no disco sem associação à matrícula não aparece automaticamente na tela inicial. Não vincule imagem apenas pela semelhança do número sem confrontar o conteúdo.

### O registro está duplicado ou a averbação está errada

Compare número, origem, teor, datas e histórico. Preserve o registro correto. Use cancelamento ou correção com motivo na ficha aplicável e examine selo e certidões já emitidas. Se o problema veio da importação, documente a origem para prevenir repetição no próximo lote.

## Procedimentos passo a passo

Os procedimentos abaixo usam os nomes dos botões e campos exibidos pela versão de referência. Quando uma etapa depender de informação que não aparece no registro, volte ao documento original e solicite a conferência de quem responde pelo ato. O volume complementar `MANUAL_TELAS_E_CAMPOS.md` relaciona cada campo e comando identificado nas telas.

### Reconhecer firma no balcão

1. Entre em Tabelionato de Notas > Reconhecer firma. Em Busca, informe pelo menos três letras do nome ou o CPF de quem assinou e clique em Procurar cartão.
2. Abra o cartão encontrado e compare a assinatura digitalizada com o documento. Use a ampliação; se não houver imagem, confira o cartão físico. Leia avisos de bloqueio. Se não houver cartão, use Abrir cartão novo e volte ao reconhecimento.
3. Marque o cartão de cada pessoa cuja firma será reconhecida. Escolha a Espécie de reconhecimento e confira se corresponde ao ato praticado: semelhança e autenticidade não são intercambiáveis.
4. Informe Tipo do documento e Descrição do documento. Marque Documento de veículo ou Conteúdo financeiro somente quando aplicável; se for veículo, confira a Placa. Se houver reconhecimento de sinal público, marque a opção própria.
5. Clique em Reconhecer. Confira a mensagem, o número do selo, o registro do ato e a etiqueta. Se o selo falhar, a tela deve indicar o motivo e o reconhecimento não deve ser apresentado como concluído. Consulte Selos emitidos antes de repetir.
6. Para reimprimir ou verificar um ato, use a aba Reconhecimentos feitos. Reimpressão da mesma etiqueta não é novo reconhecimento.

### Autenticar cópia

1. Em Tabelionato de Notas > Autenticar cópia, informe a quantidade de Folhas, o Tipo, o Tipo do documento, o Apresentante e o CPF quando conhecido.
2. Descreva o documento para que a autenticação seja identificável. Confira o original apresentado e os valores calculados.
3. Use Autenticar e confira o selo retornado. O campo Selo ou a ação Anotar serve ao fluxo previsto na tela para registro posterior; não informe selo de outro ato.
4. Na listagem, use Imprimir ou Reimprimir para a via do mesmo ato. Se houver erro, consulte a ficha e o razão dos selos.

### Abrir, preparar e lavrar ato de Notas

1. Entre em Escrituras públicas, Atas notariais ou Atos de livro e selecione Lavrar. A tela da família mostra modelos e atos recentes; escolha o tipo que corresponde ao instrumento.
2. Ao abrir o ato, confira natureza, data, livro, partes e qualificação. Preencha o teor a partir do modelo correto. Os marcadores ainda visíveis exigem resposta ou remoção fundamentada antes de assinar.
3. Junte documentos de suporte, confira pendências e abra a prévia. Verifique valores, matrícula de imóvel quando houver, qualificação das partes, cláusulas e fecho. Para ata notarial, separe fato observado de inferência ou conclusão.
4. Confira livro, termo, folha e quantidade de páginas. O sistema reserva folhas inteiras, incluindo verso, e oferece impressão de face inutilizada quando sobra espaço. Não altere contador para acomodar manualmente uma impressão.
5. Clique na ação de lavrar apenas após a conferência. Leia a resposta do selador e confirme o número do selo no documento final e em Selos emitidos. Se a tela permitir decisão excepcional de prosseguir sem selo, registre a razão e acompanhe a selação pendente.
6. Emita o traslado ou cópia pela ficha do ato. Confirme que o arquivo reaberto reproduz o teor lavrado, não uma minuta ainda editável. Acompanhe remessas às centrais pela área própria.

### Prenotar título e praticar ato no RI

1. Em Registro de Imóveis > Protocolo / prenotação, cadastre o título apresentado e o apresentante. Confirme número, data, documentos e recibo de apresentação.
2. Acompanhe qualificação, exigência, cumprimento e prazo pela ficha do protocolo. Uma exigência deve apontar o que falta; não use o protocolo geral do caixa como prenotação.
3. Localize a matrícula pelo número ou CNM. Na lista, confira tipo de ficha, livro, folha, condição de acervo e marca de conferência contra o livro físico. Abra a ficha e confronte imagem, teor e dados estruturados.
4. Inicie Rascunhos de ato ou a ação correspondente na ficha. Escolha registro ou averbação e a natureza exata. Confira titularidade, partes, imóvel, título, sequência de atos e referências dentro do teor.
5. Use a prévia e a fila O que revisar antes de selar. Corrija os itens documentados; uma nota de revisão não altera o ato sozinha. Só depois lavre e confira o selo e o ato na ficha.
6. Se a matrícula veio de acervo, preserve o texto importado e a informação de origem. Matrículas anteriores à faixa nova indicada pelo sistema não exigem reconstituir selo histórico como se fossem ato lavrado agora.

### Emitir certidão do RI

1. Em Registro de Imóveis > Certidões, pesquise a matrícula. Confirme número completo, CNM quando aplicável e estado atual da ficha.
2. Escolha a espécie de certidão e confira o conjunto de atos e averbações. Cancelamento e restrição posterior não podem desaparecer do teor por seleção inadvertida.
3. Confira nome e função de quem emite, local de assinatura, data e selo previsto. Abra a prévia antes de gerar PDF ou ODT.
4. Reabra o arquivo gerado e compare com a ficha, especialmente matrícula completa, qualificação do imóvel, atos recentes e assinatura. Se a impressão mostrar documento antigo, não o entregue; registre o identificador e a mensagem do sistema.

### Registrar e certificar no Livro 3

1. Em Livro 3 > Registros do Livro 3, localize o registro ou abra novo. Confira a série, número e dados do título, das partes e do interessado.
2. Se o ato ainda é minuta, revise em Livro 3 - minutas a revisar. Abra a prévia marcada como rascunho, resolva as notas de revisão e confira a numeração proposta antes de lavrar.
3. Após lavrar, confira o selo, as partes, a ficha em ODT e a imagem digitalizada. Use O que falta conferir para cotejar a ficha com a imagem do livro.
4. Para certidão, selecione o registro principal e examine todas as averbações. O cancelamento de uma cédula ou título deve aparecer na certidão correspondente.
5. Correção, descancelamento e devolução à minuta exigem ação própria e motivo. A numeração de ato selado não se altera por simples renumeração.

### Conduzir usucapião extrajudicial

1. Abra o processo em Registro de Imóveis > Usucapião extrajudicial. Cadastre requerentes, imóvel, matrícula ou origem registrária, titulares, confrontantes e endereços.
2. Junte requerimento, planta, memorial, ata notarial e demais provas na ficha. Abra cada anexo e confira se ficou vinculado ao processo correto.
3. Preencha o checklist. Se algum documento for dispensado, registre o motivo na própria etapa. A situação do processo determina os próximos passos apresentados na ficha.
4. Gere as notificações dos titulares e confrontantes, confira destinatário e endereço, imprima o papel e registre forma, tentativa, entrega, resposta e prazo. Não marque ciência apenas porque o documento foi gerado.
5. Em Ciência aos entes, gere os três ofícios. No Andamento, abra e imprima separadamente os papéis da União, do Estado e do Município. Guarde prova de envio e eventual pedido de prorrogação justificado.
6. Para edital, confira a data de disponibilização informada pela Central, a forma de publicação e a contagem do prazo. A análise e a decisão devem indicar os elementos examinados e o fundamento de quem decide.
7. Depois do registro, confira o ato resultante na matrícula e no dossiê do processo. Não reabra ou duplique processo para recuperar um papel já gerado.

### Lavrar assento e emitir segunda via no RCPN

1. Em Registro Civil > Assentos, pesquise a pessoa e o registro antes de abrir novo. Para nascimento, casamento ou óbito, escolha a porta específica e preencha os dados comprovados pelo documento apresentado.
2. Confira nomes, filiação, datas, local, declarante, livro, folha, termo e matrícula nacional completa. No nascimento, verifique CPF do registrado e gêmeos; no óbito, responda as perguntas que disparam comunicações.
3. Revise o teor e as averbações. Se o assento foi importado, compare a informação estruturada com o documento original; campo ausente no cadastro não deve ser preenchido por suposição.
4. Ao lavrar, leia a mensagem de selo e confira seu vínculo. Em averbação posterior, examine se já existe ato igual. Para CPF antigo, use CPF nos assentos antigos e a ação de averbar ou cancelar apropriada.
5. Para segunda via, abra Certidões ou a ficha do assento existente. Selecione espécie, revise o teor atualizado, a matrícula, as averbações, quem emite e o selo da segunda via. Gere, reabra e confira o documento antes de entregar.
6. Se a segunda via falhar para assento importado, anote número, espécie, tela e mensagem em Problemas do sistema. Corrija o vínculo ou dado faltante pelo fluxo próprio; criar outro assento cria duplicidade.

### Concluir habilitação de casamento

1. Em Casamento > Habilitação, abra o processo dos nubentes e complete o checklist individual de cada um. Documento dispensado exige motivo.
2. Gere e confira o edital de proclamas. Publique pelo e-Proclamas ou registre o protocolo externo pela forma manual disponível na ficha. Anote a data efetiva da publicação.
3. Registre eventual oposição e a decisão fundamentada. A tela separa registrar a oposição, decidir e habilitar; não salte uma etapa por ter preenchido as seguintes.
4. Confirme a situação da habilitação e a validade antes da celebração. Após celebrar, registre o assento de casamento e confira teor, selo e certidão.
5. Se uma etapa estiver bloqueada, leia o motivo mostrado na ficha e volte ao documento ou prazo apontado. Não altere a data da publicação apenas para liberar a ação.

### Cumprir o dia do Protesto

1. Abra O roteiro das Centrais e verifique tarefas do turno. Em Remessa da CRA, envie o arquivo e clique em Conferir; leia lotes, títulos e irregularidades antes de importar.
2. Após receber a remessa, confira a confirmação e acompanhe cada título em Títulos. Abra as imagens quando necessário. Em Avisos e editais, confira destinatários, coobrigados, entrega, boleto e edital.
3. Consulte Desistências de manhã, no recebimento do meio-dia e antes de A protestar. Aplique cada desistência ao título correto e confirme a situação resultante.
4. Em A protestar, confira títulos elegíveis, valores e pendências antes da lavratura. Depois, abra Instrumentos e confira assinatura e selo de cada item cobrado.
5. Em Retorno à CRA, gere e confira retorno final e andamento como par. Verifique o arquivo de rejeições e a prova de envio. Nas etapas da CENPROT, acompanhe pendências, intimação digital e assinatura.

### Receber e registrar título em RCPJ ou RTD

1. Escolha RTD - títulos apresentados ou RCPJ - títulos apresentados. A atribuição define a fila e o livro; confira antes de protocolar.
2. Abra a ficha do título, junte o documento e confira apresentante, partes, natureza e exigências. Acompanhe o processamento da Central ONRTDPJ quando a entrada vier de lá.
3. Lavre o registro somente após a qualificação e confira número, selo e documento resultante. Acompanhe atos posteriores na ficha do registro.
4. Para certidão de inteiro teor, compare o registro principal com os atos posteriores. Use Etiquetas de selos externos apenas para selo realmente obtido em canal externo, conferindo número e origem.

### Importar acervo com conferência

1. Em Livros e acervo > Importar de outro sistema, escolha O que você vai importar. Envie o arquivo JSON ou use o campo Texto quando a tela permitir.
2. Clique em Conferir. Leia o resumo, as linhas recusadas, duplicidades e campos ausentes. Compare uma amostra com o documento original.
3. Para uma unidade que requer digitação, use Preencher o formulário do ato novo. Para lote conferido, use Importar os que passaram e guarde o relatório.
4. Abra amostras de cada tipo importado: registro, partes, teor, imagens, averbações e certidão. Se uma inconsistência aparecer, interrompa o próximo lote e registre o caso com a origem do arquivo.

### Operar caixa e protocolo geral

1. Em Caixa, informe Saldo inicial e clique em Abrir o caixa de hoje. Antes de Lançar, confira Natureza, Forma de pagamento, Valor, Pagador, CPF/CNPJ, Descrição e Protocolo.
2. Quando houver composição de emolumentos, preencha os campos de fundos e selo a partir dos valores efetivos; não invente composição para fazer o recibo parecer completo.
3. Após Lançar, use emitir recibo. Confira o valor, pagador e protocolo no arquivo. Reimprimir ou reabrir o mesmo recibo não cria nova entrada.
4. Com o caixa aberto, uma correção pode ser feita pela ação salvar alteração, estornar ou excluir, sempre com o motivo exigido. Com caixa fechado, siga a ação de estorno; não apague um recebimento que já sustentou recibo.
5. No fechamento, conte a gaveta, informe Contado e justifique diferença. O sistema compara o dinheiro físico com o esperado em espécie; PIX e cartão não entram na gaveta.
6. Em Protocolo geral, abra o serviço, identifique interessado e contato, vincule documentos e acompanhe a entrega. Use Protocolos parados para retomar pendências.

### Relatar problema e consultar o Agente

1. Abra Ajuda do sistema pela janela da tela em que ocorreu a dúvida. Escreva o objetivo, o que fez, o resultado e a mensagem literal. Use Ver o que sairia antes de enviar dados à IA quando houver informação sensível.
2. Se o comportamento do sistema estiver errado, abra Problemas do sistema e registre um relato que permita repetir: módulo, tela, versão, número do registro ou protocolo, horário e erro. Anexe documento apenas quando necessário.
3. O desenvolvimento pode registrar nota, estado e prova de correção. A marcação Resolvido é a confirmação de quem usa e confere; um retorno técnico não substitui a prova no ato real.
4. Em Base de conhecimento da ajuda, pesquise pelo assunto. Este manual aparece como DOCUMENTO, junto com o volume de telas. O Agente do sistema, disponível ao administrador, usa a mesma base; peça a fonte e confira na tela quando a resposta envolver selo, prazo ou dado de registro.

### Preparar atualização do sistema

1. Em Correções e atualizações, selecione o arquivo `.cgu` e informe o SHA-256 recebido por canal separado. Clique em Validar e preparar - sem aplicar.
2. Leia a inspeção, versão de origem e destino, arquivos alterados, alertas e plano de retorno. Faça o backup obrigatório e confirme que ele terminou.
3. Para aprovar, repita o hash, digite a frase APLICAR seguida da versão, informe a senha atual do administrador e marque que revisou o impacto. Clique em Criar backup, aprovar e aplicar.
4. Aguarde o reinício. Abra a saúde ou o rodapé e confirme que a versão em execução é a instalada. Se houver falha, consulte o resultado da atualização e o log antes de repetir o pacote.

## Catálogo completo das portas do menu

Este catálogo ajuda a localizar uma função pelo nome visto na tela. A presença de cada link depende das permissões do usuário e do alcance configurado para o módulo.

### Tabelionato de Notas - onde encontrar

Painel do tabelionato concentra o movimento. Reconhecer firma e Autenticar cópia atendem o balcão. Escrituras públicas, Atas notariais e Atos de livro cuidam dos instrumentos. Cartões de autógrafo, Sinais públicos, Reconhecer sinal e Pendências das escrituras ficam na consulta. Livros do tabelionato e Remessa às centrais reúnem a escrituração e os envios. Ajustar etiqueta, Trazer notas do E-Ofício e Modelos dos documentos são portas de configuração, importação e modelos.

### Registro de Imóveis - onde encontrar

O dia: Protocolo / prenotação, Matrículas, Certidões, Rascunhos de ato, O que revisar antes de selar e Numeração dentro do teor. Processos que levam meses: Usucapião extrajudicial e Retificação de área. Livro 3 - Registro Auxiliar: Registros do Livro 3, Minutas a revisar, O que revisar antes de selar, O que falta conferir e Certidões do Livro 3. Consulta e acervo: Código de Normas do usucapião, Indicador Real, Indicador Pessoal, CNIB, ONR, endereços a conferir, Atas de ocorrência, Fichas digitalizadas e Matrículas em Word. Remessas e obrigações: Selos e emolumentos, Exportação ONR, Carga do Next Cloud SAS, CTP e DOI. Configuração e modelos: Delegatários, Numeração das matrículas, Modelos de atos e Modelos dos documentos.

### Protesto - onde encontrar

O balcão: O roteiro das Centrais, Títulos, Certidões e Instrumentos. Dia da CRA: Remessa da CRA, Imagens dos títulos, Avisos e editais, Desistências, A protestar, Retorno à CRA e CRA - falar pela API. Dia da CENPROT: Pendências da CENPROT, Intimação Digital e Chave do CENPROT. Trazer protesto do E-Ofício e Modelos dos documentos completam as portas do grupo.

### Registro Civil - onde encontrar

O balcão: Assentos, Averbações, Certidões, Folhas de segurança, Pedidos da Central e Documentos avulsos. Nascimento: Novo registro de nascimento, Teores do nascimento, Registro tardio, Gêmeos e CPF do registrado. Casamento: Registro do casamento, Habilitação, Edital de proclamas, Enviar ao e-Proclamas, Prontas para casar e Teores do casamento. Óbito: Novo registro, Teores do óbito, Comunicações mensais e O que falta perguntar. Assento já lavrado: Retificação e suprimento, Atos sem checklist, Termos a escrever, Informações importadas, Importar arquivo, Digitar informações, CPF nos assentos antigos, Matrículas e Conferência da filiação. Comunicações e remessas: O que comunicar hoje, SIRC, FUNAI, CRC, Anotações devidas, Anotação da CRC e IBGE. Modelos dos documentos fecha o grupo.

### RCPJ, RTD, Livros, Malote e Administrativo - onde encontrar

RCPJ e RTD: Títulos apresentados de RTD e RCPJ, Etiquetas de selos externos, Central ONRTDPJ, Registros lavrados de cada atribuição, Últimos atos praticados, Certidões de inteiro teor, Ajustar etiqueta e Modelos dos documentos. Livros e acervo: Livros e termos, Encerramento diário, Numeração dos livros, O que falta informar, Trazer o acervo do E-Ofício e Importar de outro sistema. Malote: Expedientes, Expedientes prontos para encerrar, Tarefas e pendências e Inspeções.

### Administrativo - onde encontrar

Dinheiro: Caixa, Protocolo geral, Protocolos parados, Depósito prévio, Recibos, Emolumentos e Selos emitidos. Atendimento: Atendimento / senhas, WhatsApp, Robôs, O que ficou pelo caminho, Rascunhos, Consultar fraudes e Relatórios. A casa: Atenção para fraudes, Checklists, Obrigações recorrentes, LGPD e governança, TI e infraestrutura, Auditoria e Integridade. Ajuda: Ajuda do sistema, Problemas do sistema, O que a ajuda sabe do projeto, Base de conhecimento da ajuda e Agente do sistema. Configuração: Modelos dos documentos, Modelos do caixa, Selador - configuração, Rede / acesso, Usuários, Corrigir dado do acervo, Agente - configurar, Ajuda - configurar, Trazer caixa do E-Ofício, Correções e atualizações e Configurações.

## Glossário rápido

Assento: registro do RCPN. Averbação: ato posterior lançado à margem ou na ficha. Certidão: documento que certifica o conteúdo ou situação de um registro. Livro 2: matrículas de imóveis. Livro 3: Registro Auxiliar do RI. Minuta: texto preparatório ainda não lavrado. Prenotação: lançamento do título no protocolo do RI. Protocolo geral: controle administrativo de atendimento. Razão dos selos: histórico de selos obtidos, vinculados e cancelados. Teor: texto do ato ou registro. SID: identificador da solicitação ao selador, usado para recuperar uma tentativa sem multiplicar selos.

## Fontes internas para aprofundamento

Este manual foi consolidado a partir do menu em `templates/base.html`, das rotas atuais e dos documentos do projeto. Para detalhes técnicos e hipóteses de acervo, consulte `docs/tecnico/TUTORIAL_CAIXA.md`, `docs/tecnico/NUMERACAO_DE_LIVRO.md`, `docs/tecnico/USUCAPIAO_OS_TRES_PAPEIS.md`, `docs/tecnico/FILA_DO_LIVRO_3.md`, `docs/tecnico/HABILITACAO_DE_CASAMENTO.md`, `docs/tecnico/ROTEIRO_DIARIO_DO_PROTESTO.md`, `docs/tecnico/IMPORTACAO_DO_ACERVO_EM_DOCX.md`, `docs/tecnico/SELADOR_CLIENTE.md` e `docs/tecnico/A_BASE_DA_AJUDA_PRE_CARREGADA.md`. Quando houver diferença entre documento histórico e tela atual, a versão instalada e o registro concreto devem ser conferidos antes da operação.
