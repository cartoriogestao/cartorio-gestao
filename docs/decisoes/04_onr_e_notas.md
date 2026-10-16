# Centrais do RI (ONR) e Tabelionato de Notas

Decisões sobre a integração do Registro de Imóveis com o ONR (API, Indicador Real, endereço lido do teor, Next Cloud SAS) e sobre o Tabelionato de Notas (escrituração do livro, cadastro de partes, selo do ato de livro, modelo da escritura e CCN/e-Notariado).

## ONR — o contrato da API

### O tipo de imóvel do arquivo e o da API são vocabulários diferentes, e nunca se misturam
**Regra.** O arquivo de indicadores usa uma tabela de códigos (0 a 9); a API usa outra (64 = Casa, 65 = Apartamento, 15 = Loja, 71 = Terreno/Fração…). Há teste que exige que as duas não tenham código em comum.
**Por quê.** Usar uma pela outra poria «Loja» onde é «Casa» no índice nacional, sem erro em lugar nenhum.
**No código.** `ri_onr.py` (arquivos) · `onr_api.py` (API).

### O `openapi.json` do ONR não é JSON válido; guardam-se duas cópias e o teste compara objetos
**Regra.** Fica a cópia original (que prova o defeito: vírgulas antes de fecho) e uma limpa, lida pelos testes. A comparação tira a vírgula do original e compara o conteúdo parseado, não bytes nem tamanho.
**Por quê.** Reserializar muda tamanho e indentação sem mudar o conteúdo; comparar a forma mede a coisa errada.

### A autenticação é um par, e o token vive só na memória
**Regra.** `POST /v1/auth/token`, corpo `x-www-form-urlencoded` (não JSON), `grant_type=client_credentials`. O token fica em memória conforme `expires_in`; sem `expires_in` não se guarda; trocar a credencial descarta o token. O segredo fica fora do banco. Os ambientes (`api.` e `testes-api.`) saem de `servers` do contrato, e a configuração nasce em testes.
**Por quê.** Token guardado para sempre vence sem aviso; sem descartar na troca, a correção do segredo parece não ter pegado.
**No código.** `onr_api.py` · `centrais_cred.py`.

### A mesma API tem dois mecanismos de autenticação
**Regra.** A maioria das operações usa `Authorization: Bearer <token da serventia>`. Detalhes e validação do protocolo usam o cabeçalho `token: <token daquele protocolo>`, obtido em `POST /v1/protocolo/{n}/token`.
**Por quê.** O Bearer da serventia nos detalhes do protocolo devolve 401 sem explicação.

### Omissão no contrato é omissão, e não caminho aberto
**Regra.** Operações de edital/cobrança sem segurança declarada usam a mesma credencial; o `tokenUrl` do `oauth2` declarado aponta para endereço inexistente e é ignorado. Testes ficam vermelhos quando o contrato for corrigido.

### O `enum` deste contrato é documentação, não valor
**Regra.** Campos `integer` trazem `enum: ["64 = Casa", …]`; o gerador parte as entradas e **transcreve** os vocabulários (logradouro, ato, imóvel) para o código, conferidos por teste contra o contrato. Nome repetido no catálogo resolve para o menor código, com a duplicata declarada. `tipoLogradouro` é código no indicador real e texto no edital. Localização é `1 = Urbano`, `3 = Rural` — não existe 2. Literais com espaço não se quebram por largura no gerador.
**Por quê.** Mandar a string põe texto onde a Central espera número; o contrato não viaja no pacote de atualização, por isso é transcrito; catálogo oficial pula número.
**No código.** `tools/gerar_logradouros.py`.

### Enviar não é ser aceito, e corrigir mantém o identificador
**Regra.** `ENVIADO` e `ACEITO` são situações distintas; o ONR processa em fila própria e a situação só muda quando a palavra devolvida é conhecida. Correção reenvia pelo caminho de atualização, sem excluir e reenviar.
**Por quê.** Palavra desconhecida tratada como aceite dá por publicado o que foi recusado; excluir gera identificador novo e deixa órfão o número que alguém já consultou.

### O lote de protocolo recebe um link, não o arquivo
**Regra.** Em `POST /v1/protocolo/lote`, `arquivos` é `{nome, url}`. As imagens do Livro 2 não sobem pela API: têm canal próprio (web service da serventia ou Bucket do Next Cloud SAS).

## ONR — o que o Indicador Real manda, e o que recusa mandar

### Campo obrigatório sem dado vai com o valor menos afirmativo, e a tela diz
**Regra.** `situacaoConstrucao` é obrigatória e o cadastro não a guarda: vai «Não se aplica», com aviso e caixa para trocar. O código 0 («Construção Averbada») é resposta válida e não pode cair em filtro de vazios.
**Por quê.** Em branco o contrato recusa; exigir escolha em toda matrícula produz tela que ninguém usa.

### Só o proprietário atual vai ao índice
**Regra.** Envia-se quem é dono hoje (`proprietario_ativo`), não quem já foi.
**Por quê.** Mandar os dois publicaria como proprietário quem vendeu.

### O que não casa com o vocabulário da Central aparece; não some nem se adivinha
**Regra.** Natureza do título que não casa com os códigos de ato do ONR aparece na tela com o número do ato. Tipo de imóvel não casa por semelhança; a conferência impede e lista os aceitos. Registro anterior guardado como texto não é repartido em número/tipo/CNS por conta própria.
**Por quê.** Sumir com o ato mostra cadeia com buraco; repartir por palpite troca o número de um livro pelo de outro.

### Acervo já informado não vira atraso; recusado volta à fila
**Regra.** Fichas que o sistema anterior já mandava ao ONR não entram no «falta subir»; indicador `RECUSADO` volta à lista.
**Por quê.** Reenviar o acervo enche a fila da Central; recusado é trabalho a refazer.

### Edital do usucapião: tipos vêm da Central, intimado precisa de documento, prazo tem dois saltos
**Regra.** Os tipos de edital são lidos de `/v1/edital/tipo`. O edital é recusado enquanto algum intimado não tiver documento (obrigatório no contrato). `POST /v1/edital` é a disponibilização; a publicação é o primeiro dia útil depois dela, e os prazos correm do primeiro dia útil depois da publicação.
**Por quê.** Lista escrita à mão envelhece; contar da disponibilização erra um dia, e errar um dia é recomeçar o edital.
**Fundamento.** Código de Normas, art. 755, § 1º (norma estadual — TJMA; confira o Código de Normas do seu estado).

## ONR — o endereço lido do teor da matrícula

### A máquina propõe; quem grava na ficha é quem conferiu, e quem publica é o oficial
**Regra.** O extrator lê o endereço escrito em prosa no teor e grava uma proposta em tabela própria (`UNIQUE(matricula_id)`), com o que a ficha tinha antes. A matrícula só muda em «confirmar», na mesma transação da marca. Campo digitado por pessoa entre proposta e confirmação vale mais; linha já decidida não é regravada por nova leitura; descartar exige motivo escrito e nenhuma linha se apaga. Publicar no ONR é outra tela, do oficial.
**Por quê.** Gravar direto em centenas de fichas com expressão regular seria a máquina lavrando ato registral.
**No código.** `onr_endereco_do_teor.py` · `onr_endereco_schema.py` · `onr_endereco_web.py`.

### Cada campo diz de onde saiu, citando o que o livro escreve
**Regra.** Toda célula preenchida traz a proveniência: a frase do teor entre «», o trecho cru do teor, a coluna da ficha, «já estava na ficha» ou o padrão da serventia. A citação longa não se corta. Invariante testada: campo preenchido sempre tem citação; os sem citação são os que faltam.
**Por quê.** É o que separa conferir a leitura de confiar na máquina; célula vazia de origem se lê como «não se sabe».

### Área tem uma definição só, e ambiguidade devolve nada
**Regra.** A conversão para m² é uma função única, usada pelo extrator e pelo indicador. Hectare gravado como inteiro sem separador é hectare inteiro; ponto em área de m² é decimal; números de 4–5 dígitos sem separador (hectare ou metro?) devolvem `None` e a proposta declara a lacuna. Zero nunca substitui área desconhecida; alqueire não é convertido.
**Por quê.** A leitura ingênua mandava ao índice área dez mil vezes menor — concluída sobre três exemplos e aplicada à população inteira. Zero afirma que o imóvel não tem área.
**No código.** `onr_api.area_em_metros`.

### O endereço que vale é o do bloco do imóvel, lido sem as armadilhas do OCR
**Regra.** Duas âncoras: o endereço do imóvel vem do bloco do imóvel; o «residente e domiciliado» das partes é outro bloco. «Av.» é canonizada para «Avenida» do catálogo antes de partir o nome. O teor é lido como parágrafo único (sem a marcação HTML do editor) e o valor termina no próximo rótulo da ficha; rótulo terminado em dois-pontos com valor na linha seguinte é tratado. O lugar rural (vila, povoado) entra como bairro, sempre lido do teor.
**Por quê.** A última rua do texto costuma ser a do proprietário; a abreviatura não existe no catálogo e apagava o tipo; a quebra do OCR ora cortava, ora protegia o nome do imóvel.

### Divergência não sai pronta, e outra comarca é aviso
**Regra.** Onde teor e ficha discordam (urbano × rural, por exemplo), a proposta vai à conferência com as duas versões. Ficha que menciona outro município sai com aviso, não com correção.

### O botão só aparece onde pode agir, e cria por POST
**Regra.** O extrator é alcançável de várias telas, mas só onde há teor e falta logradouro; o botão é POST porque cria proposta. Telas de listas diferentes não exibem o número da outra.
**Por quê.** Botão que só recebe recusa ensina a não clicar; GET não escreve; número de outra fila faz crer que as listas são a mesma.

## ONR — Next Cloud SAS (Indicador Pessoal e imagens)

### São três coisas, e o Next Cloud SAS leva duas
**Regra.** Indicador Pessoal Simplificado (Livro 5) vai ao Firestore pelo programa IPS; imagens do Livro 2 vão ao Bucket pelo programa CSL2; o **Indicador Real vai pela API**. A tela diz que aderir ao Next Cloud SAS não desliga o Indicador Real.
**Por quê.** «Next Cloud SAS ligado» faria concluir que o RI inteiro está integrado, e o índice real pararia sem ninguém ver.

### O sistema não escreve no Bucket nem no Firestore
**Regra.** Quem sobe são os programas do ONR instalados no servidor da serventia; o sistema gera a carga completa do Indicador Pessoal e confere as imagens. Nada se instala sem decisão do oficial. Depois da carga completa, a incremental diária é dos programas do ONR, e o monitoramento também.
**Por quê.** Caminho paralelo daria dois programas gravando o mesmo fato, divergindo no dia em que o ONR mudar o formato.
**No código.** `onr_carga.py`.

### A modalidade segue a infraestrutura da serventia
**Regra.** A modalidade (a), web service próprio, exige data center no território nacional, link dedicado, VPN, RAID, backup diário e operação 24×7×365; a (b), Next Cloud SAS, é para quem não tem essa infraestrutura.
**Por quê.** Web service 24×7 a partir da máquina do balcão exporia o banco da serventia num link comum.

### As imagens do Livro 2 seguem o padrão do ONR, e o sistema só confere
**Regra.** TIFF 200 × 200 dpi, sem compressão ou sem perdas (CCITT G3, G4/T.6, LZW); pastas de 8 dígitos agrupando de mil em mil matrículas; um arquivo por página, `99999999.9999`. A conferência mede nome, pasta, resolução e compressão e lista matrícula sem imagem e arquivo de matrícula inexistente.

### A conferência não diz «pronto»: põe os números ao lado do que o ONR exige
**Regra.** O ONR não aceita base parcial e exige base desde 1º/01/1976 (ou do início das atividades). A tela mostra o que falta e não emite veredito; completar antes ou declarar base incompleta é decisão do delegatário. Quando o modelo da Central contraria o precedente da casa (documento zerado no IPS, por exemplo) e a casa segue o precedente, a divergência aparece com os dois números.
**Por quê.** Verde ou vermelho seria o sistema decidindo pelo oficial; quem assina precisa saber que manda o que o modelo desaconselha.

### O formulário de adesão é declaração assinada, e a decisão sobre a base vem antes
**Regra.** O formulário declara, sob assinatura ICP-Brasil, base completa desde 1976 e todas as matrículas digitalizadas. Decide-se primeiro o que fazer com a base. A declaração de inexistência é outro papel, para outro e-mail do ONR (os dois diferem por poucas letras); base existente porém incompleta é um terceiro caso, a perguntar ao ONR antes de assinar.
**Por quê.** Recomendar assinar papel não lido é afirmar conferência que não houve.

### A conta Google do projeto é a chave do acervo
**Regra.** O formulário pede uma conta Gmail para o Console do Google Cloud, pela qual se concede e revoga acesso, inclusive o do ONR (só leitura, por API). Deve ser conta da serventia, não pessoal; a senha não entra no sistema. Não é o e-mail de contato da serventia, que é outro campo (destino, entre outros, do e-mail diário de ocorrências).
**Por quê.** Conta pessoal leva o controle dos dados com quem sai; duas colunas com o mesmo valor não provam o que o valor significa.
**Fundamento.** LGPD (Lei 13.709/2018), art. 5º, VI — o oficial é o controlador.

### Instalação: código de validação e homologação antes da produção
**Regra.** Antes de um analista mexer no servidor, confere-se o código de «Validação Atendimento» do Ofício Eletrônico — o analista tem de dizer o mesmo. GoLive só depois da homologação, com a equipe familiarizada.

## Notas — escrituração do livro

### A folha do ato não se reescreve ao guardar o teor
**Regra.** Salvar o texto do ato não toca `folha`, `folha_final` e `folhas`.
**Por quê.** Corrigir uma vírgula com o campo de folha vazio apagava a folha do ato.

### Numeração e lugar no livro são travados no banco
**Regra.** Índice único de livro e folha; quantidade de folhas do livro comparada ao lançar; folha atual atualizada; número de ordem pelo ano da **data do ato**; livro informado validado (existente e aberto); inserção concorrente vira recusa, não HTTP 500; termo de abertura obrigatório, com folhas, CNS e titular. Pares de atos na mesma folha levam `livro_complemento`/`folha_complemento`.
**Por quê.** Sem isso: dois atos na mesma folha, ato além da última folha, retroativo colidindo com o ano anterior; a CENSEC recusa por duplicidade o par sem complemento.

### A guarda pergunta pelo estado do negócio, não pela coluna recém-criada
**Regra.** «Já lançado?» e «é rascunho?» olham a situação do ato. Lançar não muda situação de ato revogado. Livro com folhas desconhecidas (nulas na importação) não se encerra sozinho.
**Por quê.** Perguntar pela coluna nova deixava ato importado ser relançado, ressuscitava procuração revogada (e a remetia à Central) e encerrava livro com termo de «zero folhas».

### Escrituração sem claros, números por extenso, ato que não se divide
**Regra.** Teor corrido, sem espaços em branco; o verso que sobra entre atos é apontado para inutilização. Termos com números por extenso e repetição em algarismos. Ato não se divide entre livros; folha usada não volta à fila; ato lançado não se relança; erro se corrige por anotação à margem. Há conferência de folha pulada, repetida e termo faltante.
**Fundamento.** Código de Normas, art. 795, §§ 2º e 4º (norma estadual — TJMA; confira o Código de Normas do seu estado).

### A anotação à margem é automática, com quatro travas
**Regra.** Revogação, renúncia e substabelecimento lançados anotam a margem do ato anterior, que precisa casar por serventia, tipo do ato, série do livro e unicidade; o que não se identifica com segurança fica em «anotações pendentes». A anotação sai no traslado e deve sair na certidão.
**Por quê.** Casar só por livro e folha marcou como revogada uma escritura de compra e venda: o mesmo número de livro existe em toda série.

### Campo que não cabe no layout da Central deve ser recusado, não truncado
**Regra.** A remessa da CENSEC corta a folha em 4 caracteres e a DOI em 6, e a conferência só verifica presença. A recomendação registrada é transformar o corte em impedimento.
**Por quê.** A folha sairia errada numa Central e certa na outra, sem aviso — e é o dado que a Central fornece.
**Fundamento.** CNN/CNJ (Provimento 149/2023), art. 273, § 1º.
**No código.** `notas_censec.py` · `notas_doi.py`.

### Pendências com base legal nominada
**Regra.** (a) A MNE é obrigatória no ato eletrônico ou híbrido e nula no de papel; o layout a seguir é o do Livro III do CNN, não o do Provimento CNJ 100/2020, revogado. (b) Trava contra testamento lançado por substituto. (c) Alerta de escritura e procuração sem selo, como já existe para o reconhecimento. (d) O RCDUV (Diretiva Antecipada de Vontade) fica fora das centrais com remessa — botão que gera arquivo vazio esconde a obrigação —, e a comunicação, obrigatória, gratuita e sigilosa, fica lembrada na tela.
**Fundamento.** CNN/CNJ, art. 284, parágrafo único (Prov. 181/2024); Lei 8.935/1994, art. 20, § 4º.

## Notas — carga do acervo e cadastro de partes

### A chave de importação é o identificador do ato, não o protocolo
**Regra.** A carga usa o identificador do ato de origem; conta pelo `rowcount` de cada comando; é idempotente e preserva o que foi digitado entre cargas; o que não entra vai para quarentena com motivo e conteúdo original. Na migração, as tabelas do sistema anterior se identificam pelo conteúdo, não pelo nome.
**Por quê.** Um protocolo gera várias escrituras, e o `INSERT OR IGNORE` as descartava em silêncio; contador cumulativo relatava importações que não houve.
**No código.** `notas_import.py`.

### A ficha de firma é o cadastro de partes, e o sistema avisa sem impedir
**Regra.** Ao qualificar parte, busca-se a ficha por nome (início de palavra, mínimo três letras) ou CPF (com ou sem pontuação) e traz-se o cadastro com a assinatura ao lado; cadastrar do zero avisa duplicidade de CPF ou nome. Ao trazer a ficha, avisa cartão bloqueado, PPE, restrição por terrorismo, cartão só por autenticidade, dígito verificador inválido e o que falta para qualificar. Quem decide é o tabelião.
**Por quê.** Redigitar gera grafias divergentes e o indicador pessoal perde a pessoa; ficha duplicada divide os atos.
**Fundamento.** Provimento CNJ 88/2019, art. 20; Lei 13.810/2019; Código Civil, art. 215, § 1º.

## Notas — o selo do ato de livro

### O caminho do selo do ato de livro é medido nos envelopes reais
**Regra.** Envelopes de ato de livro levam `selo{escrevente, livro, folha}` e casam com o ato por livro e folha. Procuração usa os caminhos de procuração (poderes específicos, simples, venda); escritura, ato declarado com e sem valor — sem cruzamento. O caminho «atos em geral» não é ato de livro: nunca leva livro e folha, e serve ao arquivamento por folha do balcão.
**Por quê.** O nome do caminho sugere o contrário do que ele é; só o envelope real desempata.
**Fundamento.** Particularidade do selador do estado (TJMA); confira o contrato do selador do seu estado.
**No código.** `ato_selado.py`.

### Quem escolhe: o valor declarado, quem atende e o item da tabela
**Regra.** O valor declarado escolhe entre com e sem valor. Entre as procurações escolhe quem atende — a natureza gravada não separa. O item da tabela é perguntado, com os usados no caminho em ordem de frequência; sem item, não há selo e a tela diz. Ata notarial não sela automaticamente: sem caminho medido, a tela diz em vez de oferecer botão que sempre recusa.
**Por quê.** Correlação forte parece regra até contar as exceções; não se sela por caminho que a casa nunca usou.

### O envelope reproduz a forma medida, campo a campo
**Regra.** Com valor: sem `quantidade`, com `valorDeclarado{valorAvaliado, valorDeclarado}`. Sem valor: `natureza{descricao:"Outros", tipo:41}` e `quantidade:1`. Procuração: `quantidade:1`. `termo` vai quando existe; parte sem documento vai só com o nome, sem `documento: ""`; isenção exige motivo escrito.
**Fundamento.** Isenção da procuração previdenciária: Lei 8.212/1991, art. 68-A.

### No livro de notas, o selo sai depois do lançamento e não suspende o ato
**Regra.** O pedido leva livro e folha, que só existem após o lançamento. Se o selo falhar, o ato fica lançado sem selo, dizendo por quê, e o botão de selar permanece.
**Por quê.** Folha e termo já foram escritos no papel; suspender seria desfazer no banco o que está no livro.

### O selo digitado à mão passa pelo razão
**Regra.** É lido, tem o CNS conferido, é recusado se já usado em qualquer ato e entra no razão de selos.
**Por quê.** Gravar o número direto na coluna do ato desligava a trava contra selo repetido.
**No código.** `ato_selado.registrar_selo_obtido_a_mao`.

### A anotação antes da lavratura não é a anotação à margem
**Regra.** Nota de trabalho com autor e data, mostrada antes do teor e congelada depois da lavratura; a ação chama-se `anotacao_de_lavratura`. A anotação à margem é ato: entra no livro e tem selo. Gravação feita por script antes de haver tela só mede por padrão, copia o banco antes, tem recusas explícitas e grava auditoria.
**Por quê.** Nota sem dono não se sabe se vale; aviso depois do botão ninguém lê.

## Notas — o modelo da escritura pública

### O corpo da escritura segue a minuta em títulos, dentro do texto corrido
**Regra.** O texto do ato mora na biblioteca de modelos de Notas (não nos papéis administrativos). Os modelos seguem títulos numerados (imóvel, matrícula, preço, ITBI, CCIR/CAR, modalidade, georreferenciamento, declarações, certidões, DOI/LGPD/lavagem, base legal, emolumentos), com marcadores onde falta dado, como marca dentro do parágrafo; teste recusa quebra de linha.
**Fundamento.** Código de Normas, art. 795, § 2º (norma estadual — TJMA; confira o Código de Normas do seu estado).
**No código.** `notas_modelos.py`.

### O modelo é renderizado antes dos marcadores, e lado sem parte aparece marcado
**Regra.** O Jinja (serventia, quem lavra, outorgantes, outorgados) é renderizado antes dos marcadores do escrevente. As partes vão para cada lado pela qualificação digitada (outorgado, comprador, donatário, procurador de um lado; o resto do outro; testemunha em nenhum). Lado sem parte vira marcador visível, que a conferência acusa.
**Por quê.** Sem isso a escritura sairia com `{{ outorgantes }}` literal no papel assinado; lacuna em branco ninguém nota antes de assinar.
**No código.** `notas_teor.partes_por_lado` · `notas_web.notas_ato_preencher`.

## Notas — CCN do e-Notariado

### O CCN é cadastro de pessoas, e «importar» é enviar
**Regra.** O Cadastro Único de Clientes do Notariado é base nacional de pessoas, não lavratura. No vocabulário do CNB, mandar o cadastro ao CCN é **Importar**; **Exportar** é consultar por CPF.
**Fundamento.** Provimento CNJ 149/2023.

### Duas paredes medidas: Cloudflare e assinatura CAdES por requisição
**Regra.** O host da API (`pessoas-hml.e-notariado.org.br` e `pessoas.e-notariado.org.br`) responde 403 com desafio da Cloudflare a cliente servidor-a-servidor, mesmo com cabeçalhos de navegador, antes de qualquer credencial. A exportação exige `X-Signature`: CAdES de `{Timestamp, RequestPath}` por requisição, com a chave privada do certificado. A credencial (`X-Api-Key`/AppToken + `X-Subscription`) é o terceiro passo, não o único. Pede-se ao CNB: liberação servidor-a-servidor, o XSD da importação e orientação para o `X-Signature` com A3.
**Por quê.** Nove das onze operações (importação) seriam construíveis se a rede deixasse.

### Não se constrói transporte nem tela que finja funcionar, e não se contorna a proteção
**Regra.** Sem caminho de rede, não há cliente CCN no servidor nem tela «pronta para quando liberarem»; fica a medição do contrato. Não se emula navegador nem se reaproveita sessão do portal fora do navegador. Caminhos aceitos: liberação oficial; fluxo assistido, em que o usuário entra no portal e uma extensão age só na aba da homologação, pede a assinatura ao serviço local e envia na mesma origem, com a sessão ficando no navegador; ou portal com upload manual. Homologação primeiro.
**Por quê.** A tela diria ao escrevente que existe um caminho que não existe.

### O certificado A3 nunca é carregado no processo do servidor web
**Regra.** A assinatura acontece em subprocesso ou serviço local preso a `127.0.0.1`, chamado por uma camada única. O PIN é digitado na hora e descartado — nunca em banco, log, credencial ou conversa.
**Por quê.** O driver PKCS#11 pode dar falha de segmentação ao carregar; isso mata o processo e, no servidor web, derruba o sistema inteiro.
**No código.** `crc_a3.py` / `crc_a3_assinador.py` · `a3_servico_local.py` · `assinar_com_a3.py`.

### Foto e digital moram no disco, ligadas ao cartão, e não travam o balcão
**Regra.** Em Notas o cadastro da pessoa é o cartão de autógrafo. Foto e digitais entram como arquivo em disco, com caminho, sha256, espécie, dedo, autor e data no banco — sem blob. Uma foto e uma imagem por dedo, por índice parcial (UNIQUE com coluna nula não trava duplicata no SQLite). Dedos colhidos: códigos CCN 1, 2, 6, 7; foto presencial marca `fotoVerificada`. Não são obrigatórias para abrir firma nem selar; há fila do que falta. Molde biométrico proprietário do sistema anterior não é convertido nem enviado. A ficha impressa não muda de desenho. A digital exige ajudante local, com leitor homologado pelo CNB. Imagens entram na barreira de privacidade; auditoria não as leva.
**No código.** `cadastro_biometria.py` · `nt_cadastro_imagens`.

### O envio ao CCN segue o provimento e não derruba o balcão
**Regra.** Vai toda pessoa com firma aberta e as qualificadas em atos, com periodicidade máxima de 15 dias e carga desde 01/10/2019 se possível. CPF e nome são o mínimo; biometria, se enviada, leva dedo e imagem juntos. O XML é conferido contra o XSD do CNB; lote do acervo fora do horário, abaixo do limite de tamanho. Chaves em credencial fora do banco. Central fora do ar é recado e envio pendente, não HTTP 500. Produção só depois de importação bem-sucedida na homologação.
**Fundamento.** Provimento CNJ 149/2023, art. 166, § 1º.
