# Centrais nacionais do Registro Civil e do RTD/PJ, e lições para migrar o acervo

Decisões de desenho das integrações com SIRC, CRC Nacional, ON-RCPN (e-Proclamas e Certidão Eletrônica) e ONRTDPJ, da base comum que todas herdam, do título no RCPJ e no RTD, e regras gerais para quem migra o acervo de um sistema anterior.

## Base comum das integrações

### Toda integração segue o mesmo padrão
**Regra.** Contrato oficial baixado e guardado fora do pacote; transporte que recebe `db` e nunca `con`, de modo que a rede nunca é chamada dentro de transação (o processador da fila chama a Central e anota depois, em transação nova); credencial no cofre (`.cred`), fora do banco e do código; testes que abrem o contrato guardado e comparam caminho, método e campo; tela que diz quando a Central falhou em vez de mostrar lista vazia; e o módulo de integração nunca lavra ato.
**Por quê.** Defeito de contrato só aparece quando o teste abre o documento oficial. Chamada lenta dentro de `BEGIN IMMEDIATE` tranca o banco para o balcão. O banco viaja no backup. Lista vazia sem aviso parece «não chegou nada».
**Fundamento.** LGPD — o delegatário responde pelo tratamento.
**No código.** `centrais_cred.py`, `centrais_http.py`, `*_api.py`.

### HTTPS e TLS verificado, sem opção de desligar
**Regra.** `http://` só para `localhost` (simuladores); não há parâmetro que desligue a validação do certificado. Endpoint `http://` declarado em WSDL é recusado e trocado por `https://`. Contra servidor de Central antigo, amplia-se só a lista de cifras (`DEFAULT@SECLEVEL=1`), mantendo a verificação.
**Por quê.** Há Centrais que levam usuário e senha dentro do corpo SOAP; em texto puro a senha viajaria no envelope.
**No código.** `centrais_http.requisitar`, `centrais_http.contexto_tls`.

### Só se retenta o que não chegou
**Regra.** `GET/HEAD/OPTIONS` se retentam em falha de transporte e em 502/503/504; escrita só com `retentar_escrita=True`. 4xx/5xx volta como resposta com `status`; só falha de transporte levanta exceção. Na fila, 4xx de regra é falha definitiva; o resto espera 1, 2, 4, 8… minutos, com teto.
**Por quê.** Retentar um POST que a Central recebeu pode publicar ou cobrar duas vezes.
**No código.** `centrais_fila.py` (`FalhaDefinitiva`, `espera_da_tentativa`).

### Recebido não é aceito, e HTTP 200 não é sucesso
**Regra.** A fila distingue `ENVIADO` de `CONFIRMADO`. Quando o corpo declara `success`, ele precisa ser verdadeiro; quando declara listas de aceitos e recusados, cada item é conferido na sua lista.
**Por quê.** Lote volta com 200 e metade recusada; tratá-lo como sucesso grava como publicado o que a Central recusou.

### Produção só com permissão explícita, e o ambiente entra nas chaves únicas
**Regra.** O processador deixa `PRODUCAO` de fora salvo `permitir_producao=True`. Tabela que guarda identificador vindo de Central inclui o ambiente na chave única, por exemplo `(ambiente, modulo, numero_pedido)`.
**Por quê.** Homologação e produção numeram no mesmo intervalo; sem o ambiente, o pedido de teste ocupa o lugar do real, e o real deixa de entrar sem erro.

### A fila guarda referência, e o log não guarda segredo nem documento
**Regra.** A fila guarda `payload_ref` (`tabela:id`), nunca o corpo com dado de pessoa. O log mascara `senha`, `token`, `authorization`, `x-api-key`, `client_secret` e deixa CPF/CNPJ com os dois últimos dígitos. Nada da serventia (CNS, CNPJ, nomes, IPs) fica no código; a identificação vem da configuração.
**Por quê.** Fila e log viajam no backup e aparecem em painel.
**No código.** `centrais_fila.py`, `centrais_log.py`.

### Não se inventa endereço, obrigação nem vocabulário que o contrato não declara
**Regra.** Se o contrato publica só homologação, ou um host só, usa-se o publicado e a tela diz isso; o outro endereço não se deriva (tirar o «h» do host é palpite). `required` vazio não quer dizer «nada é obrigatório», mas não autoriza inventar obrigação: a casa recusa só a chamada que não pode funcionar, e o código diz que a regra é dela. Valor visto só em exemplo fica marcado como derivado.
**Por quê.** Com endereço adivinhado, quem acha que testa pode estar falando com a Central real.

### Erro do contrato publicado se contorna à vista
**Regra.** Diante de erro no contrato oficial (tipo de mídia inexistente, JSON inválido, `tokenUrl` fictício, operação sem `security`), o sistema faz o que funciona, guarda o original que prova o erro e mantém teste que fica vermelho quando a Central corrigir.
**Por quê.** Mandar o que está escrito falha calado; corrigir sem registro esconde a correção da Central.

### O que se manda e o que se recebe congela
**Regra.** O teor recebido fica como veio, em JSON; o enviado fica com `sha256`. Arquivo que é da Central (PDF da certidão) não vai para o banco: busca-se nela e serve-se em linha com cabeçalhos de segurança. Correção usa `PUT` e preserva o id, em vez de cancelar e recriar.
**Por quê.** A Central pode mudar o dado depois. Recriar dá id novo e deixa órfão quem já recebeu o antigo como verificador.

## SIRC

### A remessa leva assentos e atos, e o incompleto fica retido
**Regra.** A lista de pendentes lê registros (nascimento, natimorto, casamento, óbito) e atos (averbação, anotação, retificação), do mais antigo para o mais novo. Só se remetem atos lavrados no próprio sistema, não os importados. Ato sem dado obrigatório fica retido com o nome do que falta; data ilegível vira campo ignorado, nunca um dia inventado.
**Por quê.** Olhar só os assentos deixa as averbações de fora sem ninguém ver. A sanção alcança também a informação inexata: declaração recusada volta, aceita com dado inventado fica no mundo.
**Fundamento.** Remessa ao INSS pelo SIRC em até 1 dia útil, com sanção do art. 92 da Lei 8.212/1991 e ação regressiva do INSS (norma estadual — TJMA, art. 225 do Código de Normas; confira o Código de Normas do seu estado).
**No código.** `sirc_remessa.pendentes_de_remessa`.

### Mês sem movimento também se declara
**Regra.** A declaração de inexistência tem a competência em `M/AAAA`, sem zero à esquerda, e quatro booleanos independentes (casamento, nascimento, óbito, natimorto).
**Por quê.** É a obrigação que mais se esquece, porque nenhum trabalho a lembra.
**Fundamento.** Comunicação até o 5º dia útil do mês seguinte (norma estadual — TJMA, art. 225, § 3º; confira o Código de Normas do seu estado).
**No código.** `sirc_remessa.declaracao_de_inexistencia`.

### Os limites do arquivo decidem a forma do módulo
**Regra.** XML válido contra o XSD, UTF-8, até 250 registros e 1024 KB por arquivo (medidos em bytes), GZIP, e no mínimo 1 minuto entre envios, imposto no código antes de cada chamada. Cada lote e cada operação levam uma espécie só; casamento religioso usa o envelope do civil e natimorto usa o do óbito, com tipo de livro `5`.
**Por quê.** Estourar o teto faz a Dataprev recusar o arquivo inteiro; nome com acento ocupa mais bytes que caracteres; clique duplo furaria o minuto. A API tem uma operação por espécie.
**No código.** `sirc_remessa.montar`, `sirc_cliente._bater`.

### O campo ausente se marca como ignorado, e o marcador vem de tabela
**Regra.** Todo campo não informado leva o marcador de ignorado, que não pode existir com o campo cheio: valor ou marcador, nunca os dois, nunca nenhum. Os nomes vêm de tabela medida no XSD (concordam em gênero: `nomeIgnorado`, `dataNascimentoIgnorada`); campo sem marcador (`idade`, `eleitor`) se omite. Uma conferência recursiva roda antes de oferecer o arquivo. A conversão para texto distingue `0` de `None`.
**Por quê.** É aqui que SIRC e CRC divergem, por isso há um formatador para cada um sobre a mesma montagem do fato. Colar «Ignorado» no nome erra calado. `str(v or "")` come o zero e declararia «não sei» onde é zero.
**No código.** `sirc_remessa.campo`, `MARCADOR_IGNORADO`, `conferir_marcadores`.

### Formatos e ordem do SIRC não se herdam da CRC
**Regra.** Data `dd/mm/aaaa`; sexo por extenso, seis valores (`MASCULINO`, `FEMININO`, `NAO_BINARIO`, `OUTROS`, `NAO_DECLARADO`, `IGNORADO`); regime, cor e estado civil com de-para próprio; CPF dentro do bloco de documentos (`tipo=CPF`, `dono=...`). Os elementos saem na ordem do `xs:sequence` (no cônjuge, documentos e filiações antes de nome e sexo), com sempre duas filiações. Cada envelope é validado contra o XSD com registros reais antes de ser dado por pronto.
**Por quê.** Data ISO, vocabulário da CRC ou ordem errada geram XML bem formado que é recusado. Só a validação real revelou os erros de ordem e um marcador inventado.
**No código.** `sirc_remessa.regime_casamento_sirc`.

### Averbação, anotação e retificação são Alteração do registro inteiro
**Regra.** Os três atos vão como blocos dentro da Alteração, que reenvia todos os dados do registro; atos pendentes do mesmo assento se agrupam numa Alteração só. Motivo não classificado vai como `OUTROS` com complemento; o texto complementar tem de 10 a 1.000 caracteres.
**Por quê.** Campo não enviado vira NULL; duas Alterações separadas fariam a segunda apagar a primeira.
**No código.** `sirc_remessa._bloco_dos_atos`.

### Cancelamento de termo não é Alteração
**Regra.** Termo cancelado no livro tem envelope, operação e versão de layout próprios; motivo obrigatório de 15 a 350 caracteres; tipo de registro só nascimento, casamento ou óbito. Sem motivo, ou sendo natimorto, fica retido.
**Por quê.** Dizer que o termo nunca valeu é o oposto de dizer que o registro mudou.
**No código.** `sirc_remessa.montar_cancelamento`.

### Regras de negócio do SIRC viram recusa no balcão
**Regra.** Só um endereço (nacional ou estrangeiro); filiação não ignorada exige nome e sexo, e nenhum outro dado do genitor sem os dois; no casamento, proclamas antes do registro, celebração até o registro, registro até hoje.
**Por quê.** A recusa no balcão acontece com o cliente na frente; a da Central chega dias depois.

### O Web Service por senha não exige A3; o upload manual exige `.mrc`
**Regra.** Há um Web Service por usuário e senha (SOAP 1.2, document/literal, `{cns, usuario, senha, conteudo}` no corpo; falha em `soap:Reason`; `<resultado>` devolvido cru) e outro por A3 com WS-Security. Para subir pelo portal, o XML vai em GZIP, cifrado em AES-128-ECB (PKCS#5, sem salt, chave por MD5 do CNS sem zeros à esquerda), com extensão `.mrc`; no OpenSSL 3.x o comando do manual só reproduz com `-md md5`. O módulo que monta não fala com rede, e há teste que varre os imports.
**Por quê.** Só o segundo Web Service exige token físico. Outras extensões são ignoradas pelo portal, e o OpenSSL 3 mudou o KDF padrão de `-k`.
**No código.** `sirc_cliente.py`, `sirc_remessa.arquivo_mrc`.

## Matrícula do Registro Civil

### A matrícula de 32 dígitos decide quem vai à Central, e não se inventa
**Regra.** Estrutura: CNS (5 dígitos + verificador módulo 10), acervo (2), serviço (2, constante `55`), ano (4), tipo de livro (1), livro (5), folha (3), termo (7) e dois verificadores. Tipos de livro: 1 A, 2 B, 3 B-Auxiliar, 4 C, 5 C-Auxiliar, 6 D (proclamas), 7 E. O verificador final não se gera por palpite; ato sem matrícula fica retido. Cada tipo de livro carrega a procedência (medido, guia do SIRC, exemplo de contrato), mostrada ao lado da matrícula e lida do próprio número.
**Por quê.** O CNJ distribui o verificador como programa, não como algoritmo publicado. O tipo `6` vem só do exemplo do contrato do e-Proclamas, e quem assina precisa saber disso.
**Fundamento.** Anexo IV do manual da CRC; manual do SIRC.
**No código.** `rc_matricula.py` (`LIVRO_DA_ESPECIE`).

## CRC Nacional

### Na CRC, tag em branco já afirma «ignorado»
**Regra.** Tag omitida ou vazia é gravada como nulo ou ignorado. Inclusões vêm antes das alterações em cada tipo de registro. `INDICEREGISTRO` é ordem dentro do arquivo, não chave global.
**Por quê.** Quem omite um campo afirma que é ignorado.
**Fundamento.** Manual de Carga da CRC Nacional.
**No código.** `crc_soap.py`.

### O vocabulário vem do XSD, e a coluna numérica passa por de-para
**Regra.** Os enumerados são os do XSD embutido no manual (`TIPOMORTE` = `NATURAL`, `VIOLENTA`, `IGNORADA`; `LOCALNASCIMENTO` = `IGNORADO`, `UNIDADE_SAUDE`, `FORA_UNIDADE_SAUDE`); onde a prosa de recomendação diverge, vale o schema. Coluna que guarda código numérico (local do nascimento, gêmeo, local do óbito pelo IBGE) passa por de-para explícito para a palavra, usando como chave a numeração que a coluna realmente guarda. Sem valor medido, o campo sai vazio e o ato aparece como incompleto.
**Por quê.** A prosa dizia «Natural ou Acidental», e «violenta» não é «acidental». Mandar o número sai fora da enumeração; usar o id da tabela em vez do código IBGE poria «Ignorado» onde é hospital.

### Validações da CRC aplicadas antes do envio
**Regra.** Nascimento ≤ óbito ≤ lavratura ≤ hoje; pessoa desconhecida com os nomes como `DESCONHECIDO`; ocupação `-1` (sem profissão remunerada) e `-2` (outras); benefício do INSS com dez dígitos e verificador módulo 11; documento só com `DONO` e `TIPO_DOC`; escape XML correto (`<` é `&lt;`, ao contrário da tabela invertida do manual). Causa da morte guardada num campo só vai inteira no primeiro (`_A`), sem repartir por palpite.
**Por quê.** A Central recusaria depois, longe do cliente. Escape trocado sai bem formado e com texto errado.

### O transporte se testa primeiro em homologação
**Regra.** O envio assinado com A3 começa em homologação, onde a Central não valida a assinatura como usuário cadastrado; montar e enviar não alteram assento nem consomem número.
**Por quê.** Envelope medido por analogia só se confirma com a resposta real da Central.

## ON-RCPN — e-Proclamas

### As duas APIs do ON-RCPN usam um único token IdRC
**Regra.** e-Proclamas e Certidão Eletrônica usam o mesmo token IdRC (OAuth 2.0/OpenID Connect) como `Bearer`. O cadastro gera `clientID`/`client secret`; o prefixo `Bearer`, derivado do contrato das certidões, fica numa constante.
**Por quê.** A ONRTDPJ usa token cru no mesmo cabeçalho; copiar um formato para o outro dá 401 sem explicação.
**No código.** `onrcpn_api.PREFIXO_DO_TOKEN`.

### Publicação e Livro D eletrônico são dois booleanos do mesmo envio
**Regra.** Exige-se pelo menos um de `publicacao` e `livro_eletronico` verdadeiro; lote vazio é recusado; publicar duas vezes no mesmo ambiente é recusado (teste em homologação não trava a produção). A resposta traz `success` e `error` por matrícula; o número devolvido é `batchId`, do lote, e é guardado com esse nome.
**Por quê.** Dois falsos são aceitos sem efeito; publicação custa e sai no mundo; chamar o número do lote de protocolo seria batizar o que não se mediu.
**No código.** `proclamas.py`.

### Convenções do contrato do e-Proclamas
**Regra.** Datas `dd/mm/aaaa`; CPF só dígitos; CEP com hífen; sexo `masculino`/`feminino`; estado civil `IGNORADO`, `SOLTEIRO`, `VIUVO`, `DIVORCIADO`, `SEPARADO`, `OUTROS`; tipo `civil`, `religioso`, `conversao`, `afixacao`; país pela M49 da ONU; município IBGE de 7 dígitos. O vocabulário se confere só quando o campo vem preenchido.
**Por quê.** CPF sem pontuação e CEP com hífen na mesma mensagem sai errado em um dos dois quando escrito de memória.

### A corrente edital → assento do Livro D → envio não se inverte
**Regra.** Sem edital publicado, ou sem assento de proclamas com matrícula, não há envio, e a recusa diz onde se conserta. Os nubentes saem da habilitação, não do assento de proclamas. O registro manual do protocolo continua, e o envio automático grava pela mesma função.
**Por quê.** Sem matrícula o recibo não é mais achado; dois lugares guardando o mesmo fato divergem no primeiro conserto.
**No código.** `proclamas.py`, `habilitacao.registrar_publicacao`.

### Texto livre não se parte para caber no campo da Central
**Regra.** Endereço em texto livre não vai nos campos estruturados, e a conferência diz isso. A naturalidade só vai quando o município se resolve pelo IBGE com régua de ambiguidade (sem UF, só se o nome for único no país); não achar não marca estrangeiro.
**Por quê.** Campo vazio não afirma nada; campo errado afirma. Erro de digitação viraria «nasceu fora do Brasil».

## ON-RCPN — Certidão Eletrônica

### Dois dos sete módulos pedem registro, e o sistema não os lavra
**Regra.** `CRC`, `REG`, `JUD`, `EPR` e `RSE` pedem certidão; `P13` (nascimento em Unidade Interligada) e `EOB` (óbito pelo e-Óbito) pedem lavratura. Esses dois não se cumprem pelo caminho da certidão: a ficha manda lavrar na tela do Registro Civil, e a situação `REGISTRADO` tira o pedido da fila sem criar assento.
**Por quê.** Lavrar toma número, folha e selo e entra na cadeia de hash: é ato da casa.
**Fundamento.** Provimento CNJ 149 (módulo `CRC`).
**No código.** `rc_pedidos.py`.

### Armadilhas medidas no contrato da certidão
**Regra.** Sem `servers` declarado; CPF com máscara (o oposto do e-Proclamas, com teste que compara as duas funções); dinheiro em três formatos (`"R$ 10,00"`, `"1.00"`, `"43,76"`), convertido antes de qualquer conta; número do pedido com três nomes e dois tipos; fora de São Paulo `quantidade_averbacao` vai presente e nula; arquivo como `Buffer` do Node, não base64; `410` sem `success`; `422` com mensagem por campo, mostrada inteira; do `tipo_registro` do pedido só `N` foi conferido.
**Por quê.** Pela régua geral, cada uma vira valor lido errado, PDF corrompido ou campo escondido.
**No código.** `onrcpn_certidao_api.py`.

### O pedido casa com o assento só pela matrícula
**Regra.** Livro, folha e número não servem; com a matrícula igual, o nome se compara e a divergência é aviso. Sem casamento, amarra-se à mão com motivo escrito.
**Por quê.** A numeração pode reiniciar por volume, e um casamento errado mostra o registro de outra pessoa. O nome muda legitimamente com o casamento.

### O que a casa não sabe não vai como resposta
**Regra.** Sexo em branco não vira «ignorado»; natimorto não vai como nascimento; bens em texto não reconhecido ficam vazios com aviso; inteiro teor só sai de assento com teor; selo não se escolhe por semelhança. Rejeitar (sobe o motivo à Central) e dispensar (só tira da fila local) são ações distintas, ambas com motivo escrito.
**Por quê.** «Ignorado» é resposta que alguém deu; vazio é campo que ninguém preencheu. Natimorto como nascimento afirma nascimento com vida.

### A assinatura acontece na Central, e o sistema não atesta a firma
**Regra.** A certidão é assinada pelo endpoint da Central; o sistema não afirma que a firma é válida.
**Por quê.** Driver PKCS#11 do A3 carregado no servidor web pode derrubar o balcão; conferir a cadeia ICP-Brasil exige âncoras e lista de revogação.

## RCPJ, RTD e ONRTDPJ

### O título recebe o protocolo geral e o número próprio da atribuição
**Regra.** Cada título fica ligado ao protocolo geral do balcão (comum às seis atribuições) e recebe o número do protocolo do RTD ou do RCPJ, com contador próprio para cada, escrito no Livro de Protocolo diário. É esse segundo número que vai na etiqueta e na certidão. Toda situação declarada do título tem um caminho que a produz, conferido por teste.
**Por quê.** Contador único faria o RCPJ pular pelo movimento do RTD. Situação que nenhum caminho alcança é trava; protocolo que só abre é diário.
**No código.** `rg_titulo.receber`, `caixa_protocolo.py`.

### O título apresentado é arquivado e aberto na tela com lista curta
**Regra.** O documento vai para o armazenamento único de anexos, que o backup alcança. Abrem na tela só pdf, png, jpg, jpeg, gif, webp e bmp; `svg` e `tif` baixam. A resposta leva `X-Content-Type-Options: nosniff` e política que proíbe script e moldura. Etiquetas de registro e de firma são configurações nomeadas, cada uma com suas medidas.
**Por quê.** Sem o título na tela não há o que qualificar. Arquivo em linha roda na origem do sistema: `.html` ou `.svg` de terceiro levaria script à sessão do balcão.
**No código.** `arquivo_visivel.py`, `etiqueta.py`.

### Um núcleo de livro comum, e cada atribuição declara as suas séries
**Regra.** Livro, volume, folha, verso, termo contínuo, abertura, encerramento, livro cheio, inutilização de folha em branco e encerramento diário do protocolo moram num núcleo só. RCPJ: Livro A (atos constitutivos de sociedades civis, associações, fundações, partidos) e Livro B (oficinas impressoras, jornais, radiodifusão, agências de notícias). RTD: Livro B (trasladação integral), C (extração) e F (conservação). A natureza do título é texto livre quando não há vocabulário oficial.
**Por quê.** Cópias da numeração por atribuição divergem; numeração contada por volume em vez de por serventia já mostrou o custo.
**Fundamento.** Art. 127, VII e art. 127-A da Lei 6.015/1973 (Livro F do RTD).
**No código.** `livro_nucleo`, `rg_schema.py`.

### O sistema comunica à ONRTDPJ o que já lavrou
**Regra.** O registro é o do livro da serventia; a Central só é informada do ato lavrado, e a nota devolutiva enviada é o texto lavrado na casa. A atribuição é escolhida por quem traz o pedido enquanto `Servico.Especialidade` não for medida em pedido real. Só se implementam os caminhos que a serventia usa.
**Por quê.** Informar sem ato lavrado poria no mundo um registro que o livro não tem; livro errado só aparece na certidão; caminho declarado sem uso vira função sem chamador.
**No código.** `onrtdpj_api.py`.

### Armadilhas do contrato da ONRTDPJ
**Regra.** Token cru em `Authorization` (apiKey, sem `Bearer`), o mesmo gerado na Central para o extrato SINTER; segurança declarada e não aplicada, então o cabeçalho vai em todas as chamadas; `required` vazio em todas as definições; `application/form-data` (inexistente) substituído por `multipart/form-data`; host único, sem homologação, dito na tela.
**Por quê.** Seguindo à letra, o servidor não acharia a parte do arquivo; homologação inventada faria testar contra a produção.

## Migração do acervo de um sistema anterior

### Antes de deduzir um de-para, procure a coluna que já o tem
**Regra.** O sistema anterior costuma guardar, ao lado do código interno, o valor que mandava a cada Central; ele é usado antes de qualquer dedução, conferindo qual numeração a coluna guarda.
**Por quê.** Não achar onde se procurou não prova que não existe; valor usado de fato vale mais que dedução por semelhança.

### O que migrou se mede contando as duas pontas
**Regra.** Compara-se a contagem no acervo com a do banco novo, tabela por tabela; procurar o nome da tabela antiga no código não responde.
**Por quê.** Importadores leem exportações intermediárias; procurar o nome mede o código, não o dado.

### A carga não cria ato, não fabrica trâmite e não consome número
**Regra.** Registros históricos entram como acervo, sem título com situações que nunca viveram e sem passar pela reserva de número do livro de hoje. Os números de partida dos livros continuados vêm do controlador do sistema anterior, não de estimativa.
**Por quê.** Criar ato a partir do que se leu inventa história; passar pela numeração reescreve o Livro de Protocolo. A continuidade da numeração na migração é cobrada em correição.

### O razão de selos históricos precisa entrar
**Regra.** Os selos já usados são carregados no razão de selos, e não só gravados dentro de cada ato.
**Por quê.** A trava de selo repetido compara contra o razão; vazio, um selo antigo passa como novo.

### Divergência do acervo fica visível, não corrigida em silêncio
**Regra.** Grafias diferentes da mesma coisa (volume `05` e `5`, acentos corrompidos, estado civil com anotações) entram como vieram; o casamento com o vocabulário novo é por regra explícita, como raiz textual.
**Por quê.** Correção silenciosa apaga a prova; contar por valor exato conta dois livros onde há um.

### Situação, configuração e rastro herdados não se presumem verdadeiros
**Regra.** Antes de importar situação ou trâmite, mede-se se o sistema anterior os exercitava; modelos e configurações herdados são revistos. Log de auditoria e acessos do sistema anterior ficam no acervo consultável, sem se misturar ao rastro novo; a leitura ao vivo do banco anterior usa permissão só de leitura. Arquivos referenciados por caminho de máquina são copiados para o armazenamento de anexos.
**Por quê.** Máquina de estado pode existir inteira e nunca ter sido usada; dado que não se revê envelhece calado; dois rastros misturados não provam nada; só a pasta de anexos entra no backup.

### Um teor por ato, imutável
**Regra.** O sistema novo guarda um teor por ato, com cadeia de hash, e o ato não se edita depois de lavrado. Assento migrado sem teor não ganha texto inventado: certidão de inteiro teor dele se tira do livro.
**Por quê.** Texto espalhado em vários campos com preenchimento desigual é a maior fonte de erro na migração; edição sem trilha não deixa prova.

### Auditar o sistema anterior antes de migrar
**Regra.** Lêem-se as cadeias de texto do executável anterior para levantar destinos de rede, nomes de campo das Centrais e credenciais embutidas, sem extrair lógica para copiar. O sistema novo não embute senha de banco e não depende de servidor de licença de terceiro para funcionar.
**Por quê.** Senha fixa igual em toda instalação tira do delegatário o controle do banco; licença remota pode travar a serventia de fora. Nome de campo e de Central é referência factual; código é outra coisa.
**Fundamento.** LGPD — o delegatário responde pelo tratamento dos dados da serventia.
