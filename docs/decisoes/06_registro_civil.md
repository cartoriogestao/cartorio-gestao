# Registro Civil das Pessoas Naturais

Decisões do módulo de RCPN aplicáveis a qualquer serventia: assento, termo e certidão; selo do civil; habilitação de casamento, gêmeos, registro tardio e retificação; anotações e comunicações obrigatórias (SIRC, CRC, IBGE, FUNAI, órgãos do óbito); e o que o sistema deliberadamente não faz.

«Código de Normas» refere-se ao do TJMA; numeração e prazos devem ser conferidos no Código de Normas de cada estado.

## Assento e termo

### O termo do livro congela; mudança posterior é averbação
**Regra.** O termo (texto do livro, assinado pelo oficial e pelo declarante) é montado uma vez na lavratura, gravado no assento e nunca remontado. Assentos migrados sem teor não ganham termo retroativo: o caminho para eles é a certidão, e a tela diz isso.
**Por quê.** Remontar faria o livro do sistema divergir do papel assinado, que é o que vale; montar hoje o termo de um assento antigo produziria texto que não é o do livro.
**No código.** `rc_termo.py`, `rc_schema.py`.

### Livro e folha moram no ato, não no assento
**Regra.** Quem ocupa face do livro é o ato (registro, averbação, anotação). Certidão, ofícios e comunicações localizam o assento por uma única função, a partir do ato de REGISTRO; a migração precisa lavrar esse ato para cada assento carregado.
**Por quê.** Sem ele a certidão sai com «LIVRO ND / FOLHA ND»; duas consultas para a mesma pergunta divergem no primeiro conserto.
**No código.** `rc_certidao.lugar_do_assento`.

### Nascimento tem três municípios, cada um em coluna própria
**Regra.** Guardam-se separados o município do parto, o de residência da mãe e a naturalidade declarada; o termo cita o art. 54, § 4º, ao registrar a naturalidade.
**Por quê.** A naturalidade pode ser, por opção, a residência da mãe. Confundir parto com residência da mãe desloca a estatística de natalidade do IBGE para o município do hospital.
**Fundamento.** Lei 6.015/1973, art. 54, § 4º.

### O termo não afirma o que não sabe
**Regra.** A idade da mãe no parto é a declarada, não calculada. Qualificação sem valor é omitida, não impressa em branco. Data de nascimento posterior ao ato é recusada no balcão; na migração entra vazia, com aviso.
**Por quê.** Cálculo sobre dado faltante põe idade errada em papel assinado; «portador do RG n.º ,» afirma um documento sem dizer qual.

### Quem responde pela serventia sai da configuração viva
**Regra.** Cabeçalho e assinatura de termos, certidões e ofícios vêm da regra atual (substituto em exercício, senão o titular). Modelos importados entram sem cabeçalho, e um teste varre os módulos procurando nome, telefone ou endereço vazados.
**Por quê.** Modelos antigos trazem oficial e endereço de outra gestão — o carimbo que mente.

### O que o termo lê, a tela pergunta
**Regra.** A lista de campos permitidos por espécie inclui toda coluna que o termo usa; o teste confere isso medindo, não por lista escrita à mão. No óbito, a tela pergunta natureza e causa da morte com o médico atestante, lugar do sepultamento e testamento conhecido; cor/raça é campo do assento em todas as espécies.
**Por quê.** O termo omite frase sem valor; sem campo na tela, o termo de óbito sai incompleto sem erro algum, e o termo congela.
**Fundamento.** Lei 6.015/1973, art. 80, itens 3º, 6º, 8º e 9º.

## Certidão

### A certidão se monta dos campos, no modelo que a serventia já entregava
**Regra.** A certidão de breve relato (modelo do CNJ) usa rótulos e ordem de blocos medidos nas certidões já emitidas; lê primeiro as colunas do assento e só depois os dados herdados da migração. Data do registro vem do ato de registro, nunca da emissão, e «por extenso» escreve dia e ano em palavras (dia 1 = «PRIMEIRO»). O dado histórico é reproduzido sem acréscimos (ex.: não somar a UF a um município que já a contém).
**Por quê.** Usar a data da emissão fez certidão de assento antigo afirmar que o registro era do dia; ler só dos dados migrados deixa «ND» exatamente no que o balcão acabou de digitar.
**No código.** `rc_certidao.py`, `livro_nucleo.por_extenso`.

### Sem filiação não há certidão de nascimento
**Regra.** O módulo recusa a emissão dizendo que o assento existe e falta a filiação. Pais e avós (paternos e maternos) são pessoas próprias, e seus nomes entram na conferência de fraude.
**Por quê.** A filiação é o corpo da certidão; registro de nascimento falso se faz com a filiação de outra pessoa.

### Certidão emitida congela, numera por exercício e não se apaga
**Regra.** Teor congelado com sha256; `UNIQUE(numero, ano)` no banco; guarda quantos atos o assento tinha; cancelar exige motivo e mantém o teor. Tabela própria, porque certidão não ocupa folha.
**Por quê.** Averbação de amanhã não muda a certidão de hoje, que já está na mão de alguém.

### Toda averbação entra na certidão, salvo as de publicidade restrita
**Regra.** O bloco de averbações traz todos os atos à margem. Ato marcado como de publicidade restrita (alteração de prenome e gênero, adoção) é omitido da certidão de breve relato sem nenhuma observação, nem a de que algo foi omitido; a marca é escolhida por quem lavra, de lista fundamentada, e o livro continua completo. Em assento migrado sem as averbações de margem, não se afirma «nada consta» sem conferência no livro.
**Por quê.** Certidão que esconde averbação engana; certidão que expõe a origem da alteração causa dano irreversível; negativa não conferida é afirmação com responsabilidade.
**Fundamento.** Lei 6.015/1973, art. 21; STF, ADI 4.275; Provimento CNJ 73/2018, art. 5º.

### Inteiro teor é forma distinta, e quem escolhe é quem pede
**Regra.** Para assento lavrado no sistema, é o termo gravado mais o fecho, mesmo regime de numeração e hash, item de selo próprio; para assento migrado sem termo, recusa explicada (a cópia vem do livro físico).
**Fundamento.** Lei 6.015/1973, art. 19; Provimento CNJ 63/2017.

### Nomes se comparam sem acento; marca de dúvida tem três estados
**Regra.** Busca e comparação de nomes e de cor/raça usam normalização registrada no SQLite ou feita em Python. Dado herdado duvidoso (ex.: livro a confirmar) leva aviso na ficha e antes de emitir certidão, com botão para registrar a conferência em coluna própria (data e responsável).
**Por quê.** `LOWER`/`UPPER` do SQLite são ASCII (`LOWER('JOSÉ')` = `josÉ`). Com NULL significando «nunca teve dúvida» e «já resolvida», recarregar ressuscita a dúvida e ensina o balcão a ignorar o aviso.

### O sistema não gera a matrícula de 32 dígitos
**Regra.** A matrícula — CNS(6) + acervo(2) + serviço(2) + ano(4) + tipo de livro(1) + livro(5) + folha(3) + termo(7) + DV(2) — é recebida e reproduzida; há teste que falha se alguém criar função que a gere.
**Por quê.** O algoritmo do dígito não é publicado (o CNJ distribui um programa; o anexo do manual da CRC é imagem), e módulo 11, módulo 97 e Luhn deram nível de acaso contra matrículas reais. Dígito chutado volta como erro em outro estado.

## Selo do civil

(Particularidade do selador do TJMA — caminhos, campos e itens são desse contrato; confira o selador e a tabela de emolumentos do seu estado. As regras de desenho valem para qualquer selador.)

### O caminho se compõe de espécie + tipo de ato e se confere contra o contrato
**Regra.** Cada espécie (inclusive transcrições e as seis do Livro E) tem registro, averbação, anotação, retificação, segunda via e certidão negativa. O sistema compõe o caminho e o confere contra os endpoints do contrato; inexistente não sela. Casamento religioso sela como casamento (muda o livro, não o ato); proclamas, pela habilitação.
**Por quê.** Compor sem conferir gera caminhos que não existem.
**No código.** `ato_selado.caminho_do_civil`, `ato_selado.caminho_do_ato`.

### O envelope leva o ato já lavrado, com o campo de código certo e a isenção escrita
**Regra.** O selo é pedido depois da lavratura, porque livro, folha e termo vão dentro do envelope. O campo do código é `codigoTipoAtoRegistro` no registro e `codigoTipoAtoCertidao` na certidão. Itens que a tabela declara isentos (registro de nascimento, óbito, natimorto) vão com a marca de isenção e o motivo. A primeira certidão já está compreendida no selo do registro; certidões seguintes, e a certidão emitida com averbação, têm selo próprio.
**Por quê.** Nome de campo errado é recusa do aparelho.

### A versão da tabela de custas tem prefixo por atribuição; só a vigência é configuração
**Regra.** Os dois primeiros dígitos (seção da atribuição) moram no código; a data de vigência é configuração. O item de custa usado vem marcado como medido ou lido da tabela; sem nenhum, o ato sai sem selo e a tela diz por quê. A busca de receita do civil passa a espécie, sem a qual não há sugestão de cobrança.
**Por quê.** Versão única para a casa diria ao aparelho que o ato foi cobrado por outra tabela; ato selado e não cobrado é receita que some.

### A folha de segurança só se gasta quando o envelope a leva
**Regra.** O papel de segurança vai só nos caminhos que imprimem certidão (registros com primeira certidão e segundas vias), lista conferida por teste contra a documentação do selador. A folha é reservada antes do pedido e baixada só após a resposta do aparelho.
**Por quê.** Gastar folha em averbação desperdiça papel e, com estoque vazio, travava o selo de atos que não usam folha.
**No código.** `papel_seguranca.py`.

### Toda tabela que sela está registrada, e um teste do conjunto garante
**Regra.** Um teste lê as telas, junta as tabelas que mandam selar ou cobrar e confere que todas constam do registro de tabelas de ato, exigindo um piso mínimo de achados. A atribuição tem grafia única no razão de selos.
**Por quê.** Tabela não registrada faz o selo digitado ser recusado e, como selo recusado desfaz a transação, o ato emitido some. Varredor sem piso passa calado quando deixa de achar.

## Habilitação de casamento

### A habilitação é processo com etapas, e as recusas são da lei
**Regra.** Abrir → documentos → edital → [oposição] → habilitar → celebrar. O domínio recusa habilitar sem edital ou dentro do prazo do edital, e celebrar com habilitação vencida (90 dias). O próximo passo é calculado do estado.
**Por quê.** Habilitar sem edital tira de terceiros o direito de opor impedimento; celebrar com habilitação vencida é celebrar sem habilitação.
**Fundamento.** Código Civil, arts. 1.525, 1.527, 1.529, 1.531 e 1.532; Lei 6.015/1973, art. 67, § 1º (o prazo do edital configurado deve ser revisado juridicamente pela serventia).
**No código.** `habilitacao.py`.

### Checklist por nubente, dispensa com motivo, impedimento decidido pelo oficial
**Regra.** Os incisos do art. 1.525 viram itens para cada nubente na abertura; prova de dissolução só para quem precisa. Dispensa exige motivo escrito. O sistema registra oposição e decisão fundamentada do oficial, sem julgar impedimento (teste varre funções de julgar). O edital congela com hash, e a reimpressão usa o teor publicado.
**Por quê.** Item que alguém tem de lembrar fica de fora; item impossível faz o checklist inteiro ser ignorado; reimprimir pelo modelo diverge do papel afixado.
**Fundamento.** Código Civil, arts. 1.525 e 1.529.

### Um item de custa, um selo: o selo da habilitação aparece no assento
**Regra.** Com habilitação da própria serventia, o selo é comprado na habilitação e espelhado no assento, que não compra nada; o espelhamento funciona em qualquer ordem e não sobrescreve selo já digitado. Com habilitação de outra serventia, o assento compra selo próprio citando o selo e a serventia de origem — e o que separa os casos é um campo respondido pelo escrevente, não dedução.
**Por quê.** O item da tabela compreende habilitação e registro: o contrato ter dois endpoints diz como se manda, não quanto se cobra. Deduzir pela ausência de vínculo cobraria em dobro no dia em que o vínculo ainda não existisse.
**No código.** `habilitacao.espelhar_o_selo_no_assento`.

### Conversão de união estável e proclamas têm envelopes próprios
**Regra.** A conversão sela pelo caminho de conversão, que exige o número do processo da união estável convertida; o sistema guarda esse número e recusa no balcão sem ele. O proclama do Livro D é item distinto e vai pelo envelope da habilitação, que exige o tipo de casamento.
**Por quê.** Pelo caminho ou envelope comum, o aparelho recusaria.
**Fundamento.** Código Civil, art. 1.726.

## Espécies com forma própria

### Gêmeos: ordem em cada assento, ligação recíproca, aviso de prenome igual
**Regra.** Um assento e um termo por criança, com ordem de nascimento e ligação ao irmão, recíproca por construção. Prenomes iguais geram aviso antes de lavrar, não recusa. O campo estatístico «é gêmeo» do IBGE não substitui a ordem.
**Por quê.** «Se é gêmeo» cumpre a remessa e descumpre a norma; registro de nascimento é imperativo legal, então o sistema avisa e o oficial decide.
**Fundamento.** Código de Normas, arts. 234 e 250 (norma estadual — TJMA; confira o Código de Normas do seu estado).
**No código.** `rc_gemeos.py`.

### Registro tardio: a dispensa de testemunhas se calcula
**Regra.** Regra: duas testemunhas. Dispensa só para menor de 12 anos com DNV ou equivalente (cumulativo); idade desconhecida não dispensa. Competência da serventia da residência do interessado. Documentos complementares são «sempre que possível» e não travam o registro; DNV é dispensada. Requerimento e documentos ficam em arquivo de vinte anos, descarte com autorização judicial.
**Por quê.** Modelo que imprime a dispensa em toda folha leva o balcão a não colher testemunha onde ela é obrigatória.
**Fundamento.** Lei 6.015/1973, art. 46; Código de Normas, arts. 236, 249 e 250 (norma estadual — TJMA; confira o seu estado); Provimento CNJ 149/2023.
**No código.** `rc_registro_tardio.dispensa_testemunhas`.

### Assentos anteriores ao Provimento 63/2017: CPF se averba, demais documentos se anotam
**Regra.** O sistema lista assentos anteriores a 14/11/2017 sem CPF. CPF entra por averbação; DNI ou RG (um basta), título de eleitor e outros dados por anotação; gratuito, lança com valor zero. Não busca CPF em base externa (teste impede chamadas de rede no módulo).
**Por quê.** Os dois verbos da norma são dois atos; «mediante conferência» proíbe copiar o número de uma base; ato gratuito fora do caixa é compensação que ninguém pede.
**Fundamento.** Provimento CNJ 63/2017; Código de Normas, art. 347 (norma estadual — TJMA).
**No código.** `rc_dados_cadastrais.py`.

## Anotações entre assentos

### Casamento, óbito e sentenças do Livro E geram anotações em 5 dias
**Regra.** O óbito anota-se no casamento e no nascimento; o casamento, no nascimento e nos casamentos anteriores; emancipação, interdição e ausência comunicam ao registro primitivo e ao juiz que as determinou. Na serventia, anota-se com remissões recíprocas; fora, comunica-se. A lista vai do mais antigo ao mais novo; assento sem data não conta como vencido.
**Fundamento.** Lei 6.015/1973, art. 106; Código de Normas, arts. 328, §§ 2º e 3º, e 367 a 372 (norma estadual — TJMA).
**No código.** `rc_anotacao.py`.

### O sistema não anota sozinho no assento alheio
**Regra.** O oficial confere a compatibilidade dos atos; o sistema grava que ele conferiu e anotou. Teste exige que o assento alvo fique inalterado.
**Por quê.** Anotar automaticamente é decidir que dois assentos são da mesma pessoa.
**Fundamento.** Código de Normas, art. 370 (norma estadual — TJMA).

### A comunicação leva resumo e exige protocolo
**Regra.** Vai o ato, a data e a localização (serventia, livro, folha, número), não o teor. Canais na ordem: CRC, malote digital, e só em falha carta ou meio com confirmação — por isso o protocolo é obrigatório. A parte pode pedir a anotação com certidão de até 90 dias, sem esperar o ofício.
**Por quê.** O teor espalha dados pessoais desnecessários; comunicação sem confirmação ninguém prova ter mandado.
**Fundamento.** Provimento CNJ 46/2015; Código de Normas, arts. 243, 369 e 371 (norma estadual — TJMA).

## Retificação, restauração, suprimento e duplicidade

### Três institutos, um rito com recusas
**Regra.** Retificação corrige o errado; restauração reconstitui o extraviado; suprimento lança o que falta e não exige assento existente. O oficial retifica sozinho só erro sem indagação ou de transposição. Pedido escrito, eletrônico ou verbal (só abre com o termo de redução), inclusive por procurador. Os 10 dias úteis contam do pedido instruído, registrado como passo próprio. O deferido vai ao livro corrente com remissões ao original.
**Por quê.** Contar da chegada atrasa o oficial por documento não trazido; sem remissão, dois assentos da mesma pessoa ficam sem ligação.
**Fundamento.** Código de Normas, arts. 348 a 354 (norma estadual — TJMA; confira o seu estado).
**No código.** `retificacao_rcpn.py`, `rr_tjma.py`, `rr_schema.py`.

### A consulta à CRC é condição da decisão, registrada com busca e resultado
**Regra.** A decisão é recusada sem consulta à CRC registrada com data, o que se procurou e o que se achou. O sistema não consulta nem marca «consultado» por conta própria. O ato deferido é lavrado pela tela do assento, e o processo confere que ele existe antes de amarrar.
**Por quê.** A consulta verifica duplicidade ou lavratura anterior; campo livre seria preenchido com «ok».
**Fundamento.** Código de Normas, art. 348, § 2º (norma estadual — TJMA).

### Erro da serventia é decisão fundamentada do oficial, com gratuidade e comunicação aos fundos
**Regra.** O sistema não decide se o erro é da serventia. Marcado pelo oficial com fundamento próprio, o ato é gratuito e abrem-se de uma vez as comunicações aos fundos indicados; registrar a comunicação confere que alguma linha mudou.
**Por quê.** A marcação gera cobrança contra o delegatário da época, pessoa nomeada; comunicar a um só fundo deixa o ressarcimento pela metade.
**Fundamento.** Código de Normas, art. 353 (norma estadual — TJMA; os fundos variam por estado).

### Duplicidade: vale o mais antigo, comunica-se de imediato e bloqueia-se o mais recente
**Regra.** Comunicação imediata ao juiz corregedor e bloqueio cautelar do mais recente; cancelamento efetivado gera, em 5 dias, anotações e comunicação pela CRC, inclusive a órgãos de identificação.
**Fundamento.** Código de Normas, arts. 365 e 366 (norma estadual — TJMA).

## Comunicações obrigatórias

### Um painel lê todas as obrigações, na ordem do aperto, sem comunicar nada
**Regra.** O painel pergunta a cada módulo o que está pendente e ordena pela urgência do prazo; o total de destinos é somado pelo código. Módulo que falha aparece como «não deu para medir», com o erro, nunca como zero.
**Por quê.** A obrigação esquecida é a sem trabalho para lembrá-la (mês sem movimento, relação vazia); `except` largo transforma erro em «nenhuma pendência».
**No código.** `rc_obrigacoes.py`.

### Dias úteis só onde a norma qualifica, por um único contador
**Regra.** «Úteis» só quando o artigo diz; corridos nos demais. Dia útil sai de um contador único, que conhece os feriados locais. «Imediatamente» mostra dias corridos desde o assento, avisando que o limiar visual é da casa, não da norma.
**Por quê.** Duas contagens divergem, e num prazo um dia é perder o prazo.
**No código.** `ri_schema.soma_dias_uteis`.

### SIRC: tudo vai, inclusive averbação, anotação, retificação e mês sem movimento
**Regra.** Nascimentos, natimortos, casamentos, óbitos, averbações, anotações e retificações vão ao INSS pelo SIRC; mês sem registro gera declaração de inexistência de movimento. Caminhos: upload no SIRC Web, web service com usuário e senha, ou web service com certificado A3 ICP-Brasil (WS-Security, XML Signature, timestamp). Lote XML UTF-8 com limites de tamanho e registros, GZIP, intervalo mínimo entre envios, XSD por espécie e de cancelamento, crítica devolvida por registro.
**Por quê.** Omissão ou dado inexato sujeita a penalidade e a ação regressiva do INSS; A3 é token físico, e envio autônomo depende do oficial.
**Fundamento.** Lei 8.212/1991, art. 92 (como citado na norma); Código de Normas, art. 225 (norma estadual — TJMA: 1 dia útil; confira o seu estado).

### CRC: inclusões antes de alterações, e tag vazia afirma «ignorado»
**Regra.** Carga por upload (XML sem assinatura) ou web service (XML assinado com e-CPF, em Base64), raiz `<CARGAREGISTROS>`, blocos de inclusão e alteração por espécie, inclusões primeiro. Tag omitida ou vazia é gravada como nulo/«Ignorado». CPF é o documento preferencial. Catálogos: DTB do IBGE, M49 da ONU, CBO, cor/pele fechada e anexos do manual. Como a CRC incorporou os campos do SIRC, o fato se monta uma vez, com um formatador por central; gera-se primeiro o arquivo conferível na tela, e o que o manual não define fica «A CONFERIR».
**Por quê.** Montagens paralelas divergem no primeiro conserto; layout inventado é recusa futura.
**Fundamento.** Provimento CNJ 46/2015.

### Óbitos do mês: filtro por destino, sem envio automático
**Regra.** Juiz eleitoral recebe óbitos de maiores de 16 anos; órgãos fazendários e de identificação, todos; Junta de Serviço Militar, homens de 17 a 45 anos do mês anterior, com relação vazia quando não houver. O filtro mora junto do destino; óbito sem idade entra marcado; a idade desconta o aniversário. O sistema monta, guarda o texto por mês e cobra o prazo; quem envia registra o protocolo. Cadastro no INFODIP (eleitoral) é passo do oficial.
**Por quê.** Lista inteira ao eleitoral manda crianças; filtro demais esconde óbito; idade por diferença de anos muda quem entra nas relações.
**Fundamento.** Lei 4.375/1964; Código Eleitoral, art. 293; Resolução Conjunta CNJ/TSE 6/2020; Código de Normas, art. 226 (norma estadual — TJMA: 5º dia útil, quatro destinos, arquivo de dois anos; confira o seu estado).
**No código.** `rc_comunicacoes.py`.

### Comunicação por assento não cabe em tabela mensal
**Regra.** Comunicações mensais têm `UNIQUE(destino, competência)`; as por assento (FUNAI) têm tabela própria, teor congelado com sha256, baixa com canal e protocolo, dispensa com motivo. O nascimento indígena é identificado pela cor/raça declarada; etnia e aldeia são perguntadas, nunca deduzidas do sobrenome, e vazias saem marcadas para completar.
**Por quê.** Na tabela mensal, a segunda criança do mês sumiria no `UNIQUE`. Deduzir etnia do nome erra nos dois sentidos, num papel enviado a órgão federal.
**Fundamento.** Código de Normas, art. 253, §§ 1º e 2º (norma estadual — TJMA: comunicação imediata à FUNAI).
**No código.** `rc_funai.py`.

## Remessa do IBGE

### O mapa trimestral tem prazo e multa, e o vencimento entrega o trimestre anterior
**Regra.** Prazo no dia 8 de janeiro, abril, julho e outubro; o arquivo é rotulado com o trimestre reportado (o de janeiro entrega outubro a dezembro do ano anterior) e inclui o número da DNV. Enquanto o envio não for acompanhado, o painel mostra o prazo e declara isso, sem contagem que responda a outra pergunta.
**Fundamento.** Lei 6.015/1973, art. 49; Código de Normas, art. 224 (norma estadual — TJMA).

### Layout de posições fixas, ISO-8859-1, prova por ida e volta
**Regra.** `CARTINF01` (nascidos vivos), `02` (casamentos), `03` (óbitos), `04` (óbitos fetais) e `10` (resumo RC-10), zipados, larguras fixas, chave UF + município + distrito + cartório no início de toda linha. ISO-8859-1 com CRLF; texto à esquerda com espaço, número à direita com zero; livro como letra + dois dígitos, sem hífen. Teste de largura em todas as espécies; o leitor/escritor se prova reescrevendo arquivos reais byte a byte iguais.
**Por quê.** Acento em dois bytes ou um caractere a menos desloca a linha, e o IBGE pode recusar o trimestre sem dizer qual linha.
**No código.** `ibge_geracao.py`.

### Catálogos oficiais pulam números, e o do óbito não é o do nascimento
**Regra.** Local do nascimento sem o 4; local do óbito com 4 = via pública; estado civil sem o 5; idade da genitora 99 se ignorada. Campos de catálogo são caixa de seleção; de-para de sistema anterior se procura no próprio dado antes de deduzir.
**Por quê.** A sequência «óbvia» acerta o tipo e erra o conteúdo; o catálogo do nascimento no óbito apaga a via pública.

### Residência da mãe vem da mãe, e a conferência conta os «ignorados»
**Regra.** O município de residência da mãe sai da pessoa da mãe, com teste que recusa o local do parto como fonte. Municípios por tabela DTB completa, sobras como rejeição escrita. Antes do envio, a conferência conta quantas posições saíram como «ignorado» e de quais campos.
**Por quê.** Remessa cheia de «9» é aceita e inútil.

## Migração e leitura de documentos

### Coluna vazia não prova que o dado não existe
**Regra.** Na migração, procurar o dado em JSONs internos, tabelas de propriedades, colunas de de-para e modelos guardados antes de concluir que não existe; executável de terceiro não se decompila. Toda pessoa do assento (registrado, nubentes, falecido) migra com chave própria, e a carga conta inserções efetivas. Certidão e remessas se ensaiam contra registros reais, além dos testes de domínio.
**Por quê.** Concluir «não há» pela coluna errada levou afirmações falsas à tela; com a chave do assento, o segundo nubente sumia por `INSERT OR IGNORE`.

### Leitura assistida de documentos não presume nem salva
**Regra.** Cada campo lido leva valor, fonte e confiança; o que não se leu com segurança fica vazio, com o trecho recortado para conferência. Divergência entre documentos é registrada e decidida pelo escrevente. Hierarquia: qualificação pelo documento de identidade, parto pela DNV, ato pelo termo. A automação nunca salva/registra nem preenche numeração, matrícula, papel de segurança ou juízo de registro tardio. Número com dígito verificador pode chegar com pontuação variável, pois só entra se o dígito fechar.
**Por quê.** Registro público com erro exige averbação; o trabalho humano passa de procurar para conferir.
