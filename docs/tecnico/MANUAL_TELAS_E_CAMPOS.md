# Manual das telas, campos e comandos do Cartório Gestão

Versão de referência: 3.6.173. Este volume é extraído do menu `templates/base.html` e das telas HTML da mesma versão. O nome de um campo ou botão abaixo é uma transcrição da interface; sua obrigatoriedade pode depender do tipo de ato e da etapa. Confirme a regra e a mensagem exibida na própria tela antes de gravar.

## Como ler este volume

Cada entrada informa o caminho do menu, o arquivo de tela, os campos nomeados e os comandos identificados no HTML. `{item}` representa o identificador dinâmico de uma linha ou pessoa; ele muda conforme o registro aberto. Campos dinâmicos de listas e componentes compartilhados podem aparecer apenas quando houver registro ou permissão. Campos indicados como obrigatórios têm atributo `required` no HTML; o servidor também pode exigir outros campos conforme a operação. Os comandos apresentados não autorizam seu uso sem conferência do ato.

O inventário cobre 162 entradas do menu e 102 telas complementares identificadas nesta versão. Componentes compartilhados iniciados por sublinhado aparecem dentro das telas que os incluem. Este volume descreve o que está no código, sem substituir a conferência do registro concreto.

## Geral

### Visão geral

Caminho: Geral > Visão geral.
Tela-fonte: `templates/dashboard.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ver o que ficou pelo caminho; ver todas; ver todos.

## Tabelionato de Notas

### Painel do tabelionato

Caminho: Tabelionato de Notas > Painel do tabelionato.
Tela-fonte: `templates/notas_painel.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: Reconhecer firma; Autenticar cópia; Cartões de autógrafo; Reconhecimentos; Escrituras; Atas notariais; Atos de livro; Livros; Anotações pendentes; Remessa às centrais; Pendências das escrituras; Assinaturas digitalizadas; e mais 4 links.

### Reconhecer firma

Caminho: Tabelionato de Notas > O balcão > Reconhecer firma.
Tela-fonte: `templates/notas_reconhecimento.html`.
Campos da tela: Busca [busca]; Cartao id [cartao_id]; Espécie [especie]; Tipo do documento [documento_tipo]; Descrição do documento [documento_descricao]; Veiculo [veiculo]; Financeiro [financeiro]; Placa [veiculo_placa]; Sinal publico [sinal_publico]; Confirmar bloqueio [confirmar_bloqueio].
Comandos: Procurar cartão; Reconhecer.
Acessos relacionados: ← Tabelionato; Reconhecer firma; Reconhecimentos feitos; Cartões de autógrafo; Abrir cartão novo.

### Autenticar cópia

Caminho: Tabelionato de Notas > O balcão > Autenticar cópia.
Tela-fonte: `templates/notas_autenticacao.html`.
Campos da tela: Folhas [folhas] (obrigatório na tela); Tipo [tipo]; Tipo do documento [documento_tipo]; Apresentante [apresentante]; CPF do apresentante [apresentante_documento]; Descrição [documento_descricao]; Selo [selo].
Comandos: Autenticar; Anotar.
Acessos relacionados: ← Tabelionato; Reimprimir Imprimir.

### Escrituras públicas

Caminho: Tabelionato de Notas > Instrumentos > Escrituras públicas.
Tela-fonte: `templates/notas_familia.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Tabelionato; Lavrar; Ver todos; Livro de; Remessas às centrais; Pendências específicas; Abrir a lista; Usar modelo; termo rascunho.

### Atas notariais

Caminho: Tabelionato de Notas > Instrumentos > Atas notariais.
Tela-fonte: `templates/notas_familia.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Tabelionato; Lavrar; Ver todos; Livro de; Remessas às centrais; Pendências específicas; Abrir a lista; Usar modelo; termo rascunho.

### Atos de livro

Caminho: Tabelionato de Notas > Instrumentos > Atos de livro.
Tela-fonte: `templates/notas_atos.html`.
Campos da tela: Busca [busca]; Tipo [tipo].
Comandos: Filtrar; apagar.
Acessos relacionados: ← Painel Tabelionato; Lavrar ato; Livros; rascunho; ← anterior; próxima →.

### Cartões de autógrafo

Caminho: Tabelionato de Notas > Consulta > Cartões de autógrafo.
Tela-fonte: `templates/notas_cartoes.html`.
Campos da tela: Busca [busca]; Nome [nome] (obrigatório na tela); Pessoa [tipo_pessoa]; CPF/CNPJ [documento]; RG [rg]; Órgão emissor [rg_orgao]; Nascimento [nascimento]; Nacionalidade [nacionalidade]; Estado civil [estado_civil]; Profissão [profissao]; Pai [pai]; Mãe [mae]; Endereço [endereco]; Número [endereco_numero]; Bairro [bairro]; Cidade [cidade]; UF [uf]; CEP [cep]; Celular [celular]; E-mail [email]; Como assina [como_assina]; Pessoa exposta [pessoa_exposta]; Confirmar duplicata [confirmar_duplicata].
Comandos: Procurar; Abrir cartão.
Acessos relacionados: ← Tabelionato; Reconhecer firma; Reconhecimentos feitos; Cartões de autógrafo; Trazer autógrafos do E-Ofício; abrir.

### Sinais públicos

Caminho: Tabelionato de Notas > Consulta > Sinais públicos.
Tela-fonte: `templates/notas_sinais.html`.
Campos da tela: Busca [busca]; Titular [titular] (obrigatório na tela); Documento (CPF/CNPJ) [documento]; Data da abertura [data_abertura]; Origem [origem]; Chave na central [origem_chave]; PDF baixado da central [pdf]; Observação [observacao]; Metadados (texto/JSON livre) [metadados].
Comandos: Procurar; Abrir sinal.
Acessos relacionados: ← Tabelionato; Sinais públicos; Reconhecer sinal; Cartões de autógrafo; ver PDF; abrir.

### Reconhecer sinal

Caminho: Tabelionato de Notas > Consulta > Reconhecer sinal.
Tela-fonte: `templates/notas_sinal_reconhecimento.html`.
Campos da tela: Busca [busca]; Sinal id [sinal_id] (obrigatório na tela); Documento apresentado [documento_descricao].
Comandos: Procurar; Reconhecer sinal.
Acessos relacionados: ← Sinais públicos; Reconhecer sinal; Reconhecer firma; Cadastrar; ver.

### Pendências das escrituras

Caminho: Tabelionato de Notas > Consulta > Pendências das escrituras.
Tela-fonte: `templates/notas_escrituras_pendentes.html`.
Campos da tela: Ato [ato]; Lançar na escritura [ato_id]; Parte [parte]; Valor [valor].
Comandos: Gravar as classificações marcadas; Lançar as partes marcadas; Gravar.
Acessos relacionados: ← Tabelionato; Remessa às centrais.

### Livros do tabelionato

Caminho: Tabelionato de Notas > Livros e remessas > Livros do tabelionato.
Tela-fonte: `templates/notas_livros.html`.
Campos da tela: Motivo [motivo]; Termo encerramento [termo_encerramento]; Série [serie] (obrigatório na tela); Próximo termo [proximo] (obrigatório na tela); Motivo [observacao]; Tipo [tipo] (obrigatório na tela); Número [numero]; Complemento [complemento]; Folhas [folhas]; Abertura [abertura]; Termo de abertura [termo_abertura].
Comandos: Encerrar; Fixar; Abrir livro.
Acessos relacionados: ← Tabelionato; conferir; termo de abertura; termo de encerramento; imprimir as folhas inutilizadas.

### Remessa às centrais

Caminho: Tabelionato de Notas > Livros e remessas > Remessa às centrais.
Tela-fonte: `templates/notas_remessas.html`.
Campos da tela: Ano [ano]; Mês [mes]; Quinzena [quinzena]; Situacao [situacao]; Protocolo [protocolo].
Comandos: Ver a quinzena; Gerar o arquivo dos atos; Gravar.
Acessos relacionados: ← Tabelionato; Ver ato por ato.

### Ajustar etiqueta

Caminho: Tabelionato de Notas > Configuração > Ajustar etiqueta.
Tela-fonte: `templates/notas_etiqueta_ajuste.html`.
Campos da tela: Largura (mm) [etiqueta_largura_mm] (obrigatório na tela); Altura (mm) [etiqueta_altura_mm] (obrigatório na tela); Margem interna (mm) [etiqueta_margem_mm] (obrigatório na tela); Corpo da letra (pt) [etiqueta_corpo_pt] (obrigatório na tela); Deslocar na horizontal (mm) [etiqueta_deslocamento_x_mm] (obrigatório na tela); Deslocar na vertical (mm) [etiqueta_deslocamento_y_mm] (obrigatório na tela); Entrelinha [etiqueta_entrelinha] (obrigatório na tela); Tamanho do QR (mm) [etiqueta_qr_mm] (obrigatório na tela); O que o QR carrega [{item}].
Comandos: Guardar medidas; Imprimir página de teste.
Acessos relacionados: ← Reconhecimentos.

### Trazer notas do E-Ofício

Caminho: Tabelionato de Notas > Configuração > Trazer notas do E-Ofício.
Tela-fonte: `templates/notas_importar.html`.
Campos da tela: Pasta [pasta].
Comandos: Trazer agora.
Acessos relacionados: ← Tabelionato.

### Modelos dos documentos

Caminho: Tabelionato de Notas > Modelos > Modelos dos documentos.
Tela-fonte: `templates/modelos_atribuicao.html`.
Campos da tela: Corpo [corpo].
Comandos: Negrito; Itálico; Sublinhado; Tachado vermelho; Destaque amarelo; Destaque vermelho; Parágrafo; Centralizar; Quebra de linha; Inserir marcador; Salvar; Voltar ao herdado; Salvar para todos; Remover ajuste comum.
Acessos relacionados: Abrir modelos dos atos; Abrir modelos avulsos; · ajuste(s); Modelos dos documentos.

## Registro de Imóveis

### Protocolo / prenotação

Caminho: Registro de Imóveis > O dia > Protocolo / prenotação.
Tela-fonte: `templates/ri_protocolo.html`.
Campos da tela: Livro de destino [livro_destino] (obrigatório na tela); Data [data_prenotacao]; Matrícula [matricula_numero]; Apresentante [apresentante] (obrigatório na tela); CPF/CNPJ [apresentante_documento]; Natureza do título [natureza_titulo]; Telefone [telefone]; E-mail [email]; Documento apresentado [documento_descricao]; Objeto [objeto] (obrigatório na tela); Anotação [anotacao]; Reurb [reurb]; Busca [busca]; Situacao [situacao].
Comandos: Prenotar; Filtrar.
Acessos relacionados: ← Registro de Imóveis; Consultar CNIB; abrir; nota devolutiva; comprovante.

### Matrículas

Caminho: Registro de Imóveis > O dia > Matrículas.
Tela-fonte: `templates/ri_matriculas.html`.
Campos da tela: Busca [busca]; Tipo [tipo]; Livro [livro]; Ordem [ordem].
Comandos: Buscar.
Acessos relacionados: Abrir matrícula; Numeração; Importações; Anterior; Próxima.

### Certidões

Caminho: Registro de Imóveis > O dia > Certidões.
Tela-fonte: `templates/ri_certidoes.html`.
Campos da tela: Busca [busca].
Comandos: Buscar.
Acessos relacionados: ← Registro de Imóveis; PDF; .odt.

### Rascunhos de ato

Caminho: Registro de Imóveis > O dia > Rascunhos de ato.
Tela-fonte: `templates/ri_rascunhos.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Matrículas; Ver como fica.

### O que revisar antes de selar

Caminho: Registro de Imóveis > O dia > O que revisar antes de selar.
Tela-fonte: `templates/ri_revisoes.html`.
Campos da tela: O que você conferiu e decidiu [decisao] (obrigatório na tela).
Comandos: Baixar a nota.
Acessos relacionados: ← Matrículas.

### Numeração dentro do teor

Caminho: Registro de Imóveis > O dia > Numeração dentro do teor.
Tela-fonte: `templates/ri_numeracao_no_teor.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Matrículas.

### Usucapião extrajudicial

Caminho: Registro de Imóveis > Processos que levam meses > Usucapião extrajudicial.
Tela-fonte: `templates/usucapiao_lista.html`.
Campos da tela: Termo [q]; Etapa [etapa]; Situação [situacao]; Número dos autos [numero] (obrigatório na tela); Modalidade [modalidade] (obrigatório na tela); Requerente [requerente_nome]; CPF/CNPJ [requerente_documento]; Imóvel [imovel_descricao]; Área [imovel_area]; Município [imovel_municipio]; Prenotação [prenotacao]; Posse desde [posse_inicio].
Comandos: Procurar; Autuar.
Acessos relacionados: Limpar.

### Retificação de área

Caminho: Registro de Imóveis > Processos que levam meses > Retificação de área.
Tela-fonte: `templates/ri_retificacoes.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: abrir; Novo processo; O que o Código de Normas exige.

### Registros do Livro 3

Caminho: Registro de Imóveis > Livro 3 — Registro Auxiliar > Registros do Livro 3.
Tela-fonte: `templates/atrib_lista.html`.
Campos da tela: Termo [q]; Situação [situacao].
Comandos: Procurar.
Acessos relacionados: Importar arquivo Acervo do E-Ofício (ZIP, SQLite ou pasta). Prévia antes de; Digitar as informações Um assento por vez — nascimento, casamento ou óbito ; Importar do acervo O acervo do E-Ofício (com o campo do caminho). Traz o re; Digitar as informações Um registro por vez — para quando a cédula já tem nú; Importações do RI O que já foi importado, o que ficou em quarentena e por q; o roteiro inteiro das Centrais; Certidão de protesto; + Nascimento; + Casamento; + Óbito; Importar arquivo; Averbações; e mais 7 links.

### Livro 3 — minutas a revisar

Caminho: Registro de Imóveis > Livro 3 — Registro Auxiliar > Livro 3 — minutas a revisar.
Tela-fonte: `templates/livro3_minutas.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Livro 3; abrir a ficha.

### Livro 3 — o que revisar antes de selar

Caminho: Registro de Imóveis > Livro 3 — Registro Auxiliar > Livro 3 — o que revisar antes de selar.
Tela-fonte: `templates/livro3_revisoes.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Livro 3; Minutas a revisar; abrir a ficha.

### Livro 3 — o que falta conferir

Caminho: Registro de Imóveis > Livro 3 — Registro Auxiliar > Livro 3 — o que falta conferir.
Tela-fonte: `templates/livro3_por_conferir.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Livro 3; conferir.

### Certidões do Livro 3

Caminho: Registro de Imóveis > Livro 3 — Registro Auxiliar > Certidões do Livro 3.
Tela-fonte: `templates/atrib_certidoes.html`.
Campos da tela: Atribuição [atribuicao]; Termo [q].
Comandos: Procurar.
Acessos relacionados: RCPJ e RTD; Livro 3; Limpar.

### Usucapião — o que o Código de Normas exige

Caminho: Registro de Imóveis > Consulta e acervo > Usucapião — o que o Código de Normas exige.
Tela-fonte: `templates/usucapiao_codigo_de_normas.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Os processos; CNIB — o que espera seu okay.

### Indicador Real

Caminho: Registro de Imóveis > Consulta e acervo > Indicador Real.
Tela-fonte: `templates/ri_indicador_real.html`.
Campos da tela: Busca [busca]; Bairro [bairro]; Tipo [tipo].
Comandos: Buscar.
Acessos relacionados: ← Registro de Imóveis; Indicador Pessoal; … matrícula — sem descrição; Anterior; Próxima.

### Indicador Pessoal

Caminho: Registro de Imóveis > Consulta e acervo > Indicador Pessoal.
Tela-fonte: `templates/ri_indicador_pessoal.html`.
Campos da tela: Busca [busca]; Proprietarios [proprietarios].
Comandos: Buscar.
Acessos relacionados: ← Registro de Imóveis; Indicador Real.

### CNIB — indisponibilidade

Caminho: Registro de Imóveis > Consulta e acervo > CNIB — indisponibilidade.
Tela-fonte: `templates/ri_cnib.html`.
Campos da tela: Busca [busca].
Comandos: Consultar.
Acessos relacionados: ← Registro de Imóveis; Livro de Protocolo.

### ONR — índice real e editais

Caminho: Registro de Imóveis > Consulta e acervo > ONR — índice real e editais.
Tela-fonte: `templates/ri_onr_central.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Testar a credencial; Conferir a fila do ONR; O que o ONR tem; Por quê?; Corrigir no ONR.
Acessos relacionados: Administrativo → Configurações; Conferir; Conferir os endereços.

### ONR — endereços a conferir

Caminho: Registro de Imóveis > Consulta e acervo > ONR — endereços a conferir.
Tela-fonte: `templates/onr_enderecos.html`.
Campos da tela: So do ocr [so_do_ocr].
Comandos: Ler o teor e propor.
Acessos relacionados: ver; só as prontas; só as que divergem; todas; conferir.

### CNIB — o que espera seu okay

Caminho: Registro de Imóveis > Consulta e acervo > CNIB — o que espera seu okay.
Tela-fonte: `templates/ri_cnib_pendentes.html`.
Campos da tela: Motivo [motivo].
Comandos: Não é a mesma pessoa.
Acessos relacionados: ← Consultar a CNIB; Abrir a matrícula para averbar.

### CNIB — a cópia local e a Central

Caminho: Registro de Imóveis > Consulta e acervo > CNIB — a cópia local e a Central.
Tela-fonte: `templates/cnib_central.html`.
Campos da tela: De [de] (obrigatório na tela); Até [ate] (obrigatório na tela); CPF de quem consulta [cpf]; Rotina [rotina].
Comandos: Trazer o par do CNIB do acervo do E-Ofício; Buscar agora; Ler; Guardar.
Acessos relacionados: Ordens esperando okay →.

### Atas de ocorrência

Caminho: Registro de Imóveis > Consulta e acervo > Atas de ocorrência.
Tela-fonte: `templates/ri_expurgos.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Matrículas; baixar a ata (.odt).

### Fichas digitalizadas

Caminho: Registro de Imóveis > Consulta e acervo > Fichas digitalizadas.
Tela-fonte: `templates/ri_imagens.html`.
Campos da tela: Pasta raiz das digitalizações [raiz] (obrigatório na tela).
Comandos: 1. Localizar arquivos; 2. Copiar para o nosso acervo.
Acessos relacionados: ← Registro de Imóveis; páginas que faltam.

### Matrículas em Word

Caminho: Registro de Imóveis > Consulta e acervo > Matrículas em Word.
Tela-fonte: `templates/ri_matriculas_doc.html`.
Campos da tela: Pasta [pasta]; Mostrar [situacao]; Numero [numero].
Comandos: Ler a pasta agora; Filtrar; Trazer as marcadas para o sistema.
Acessos relacionados: ← Registro de Imóveis; ver ficha; ← anterior; próxima →.

### Modelos de atos

Caminho: Registro de Imóveis > Modelos > Modelos de atos.
Tela-fonte: `templates/ri_modelos_atos.html`.
Campos da tela: Busca [busca]; Tipo [tipo].
Comandos: Filtrar.
Acessos relacionados: ← Registro de Imóveis; Usar este modelo na matrícula.

### Modelos de documento do RI

Caminho: Registro de Imóveis > Modelos > Modelos de documento do RI.
Tela-fonte: `templates/modelos.html`.
Campos da tela: Enviar o papel ajustado [arquivo] (obrigatório na tela); Corpo [corpo].
Comandos: Enviar; Voltar ao papel do pacote; Gravar o ajuste; Voltar ao padrão do sistema.
Acessos relacionados: todas as atribuições; Documentos avulsos (modelos do E-Ofício); ver e editar; baixar o que vale hoje; Fechar.

### Selos e emolumentos

Caminho: Registro de Imóveis > Remessas e obrigações > Selos e emolumentos.
Tela-fonte: `templates/ri_selos.html`.
Campos da tela: De [inicio]; Até [fim].
Comandos: Filtrar período.
Acessos relacionados: ← Registro de Imóveis; abrir a matrícula; abrir o protocolo.

### Exportação ONR

Caminho: Registro de Imóveis > Remessas e obrigações > Exportação ONR.
Tela-fonte: `templates/ri_onr.html`.
Campos da tela: De [inicio]; Até [fim].
Comandos: Conferir período; Indicador Pessoal (.XML); Indicador Real (.json).
Acessos relacionados: ← Registro de Imóveis.

### Carga do Next Cloud SAS

Caminho: Registro de Imóveis > Remessas e obrigações > Carga do Next Cloud SAS.
Tela-fonte: `templates/ri_onr_next_cloud.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Gerar o XML da carga completa ( vínculos).
Acessos relacionados: ← Arquivos do ONR; Páginas que faltam nas fichas; Central do ONR; outra tela.

### CTP — prefeituras

Caminho: Registro de Imóveis > Remessas e obrigações > CTP — prefeituras.
Tela-fonte: `templates/ri_ctp.html`.
Campos da tela: Competência [competencia]; Observação [observacao]; Operação imobiliária [i{item}_operacao]; Data do negócio jurídico [i{item}_data_negocio]; Valor da operação [i{item}_valor_operacao]; I{item} valor operacao nao consta [i{item}_valor_operacao_nao_consta]; Base de cálculo do ITBI/ITCMD [i{item}_valor_base_itbi]; I{item} valor base itbi nao consta [i{item}_valor_base_itbi_nao_consta]; Forma de pagamento [i{item}_forma_pagamento]; Parte transacionada [i{item}_tipo_parte]; Quanto foi transacionado [i{item}_valor_parte]; Tipo do imóvel [i{item}_tipo_imovel]; Área construída (m²) [i{item}_area_construida]; Localização (distrito, povoado, gleba…) [i{item}_localizacao]; Motivo, se faltar CPF/CNPJ de alguma parte [i{item}_motivo_sem_ni]; Incluir {item} [incluir_{item}].
Comandos: Abrir competência; Fechar como «sem transações no mês»; Guardar o que foi digitado; Gerar arquivo ( registro(s)); Gerar e fechar a competência.
Acessos relacionados: ← Registro de Imóveis; Exportação ONR; Baixar o arquivo como foi gerado.

### DOI — Receita Federal

Caminho: Registro de Imóveis > Remessas e obrigações > DOI — Receita Federal.
Tela-fonte: `templates/ri_doi.html`.
Campos da tela: Competência [competencia]; Observacao [observacao]; Recibo [recibo]; Protocolo [protocolo].
Comandos: Registrar como mês sem ato; Ver a competência; Gerar o arquivo das declarações; Registrar como mês sem ato imobiliário; Registrar a entrega.
Acessos relacionados: ← Registro de Imóveis; CTP — prefeituras; baixar de novo; tela da CTP.

### Delegatários

Caminho: Registro de Imóveis > Configuração > Delegatários.
Tela-fonte: `templates/ri_delegatarios.html`.
Campos da tela: D{item} nome [d{item}_nome]; D{item} cargo [d{item}_cargo]; D{item} tratamento [d{item}_tratamento]; D{item} titulo [d{item}_titulo]; D{item} observacao [d{item}_observacao]; Nome [nome] (obrigatório na tela); Cargo [cargo]; Tratamento [tratamento]; Como assina [titulo]; Observação [observacao].
Comandos: Criar o cadastro inicial; remover; Guardar; Cadastrar.
Acessos relacionados: ← Registro de Imóveis.

### Numeração das matrículas

Caminho: Registro de Imóveis > Configuração > Numeração das matrículas.
Tela-fonte: `templates/ri_numeracao.html`.
Campos da tela: Livro [livro] (obrigatório na tela); Próximo número [proximo_numero] (obrigatório na tela); Motivo [observacao].
Comandos: Fixar.
Acessos relacionados: ← Registro de Imóveis.

### Modelos dos documentos

Caminho: Registro de Imóveis > Modelos > Modelos dos documentos.
Tela-fonte: `templates/modelos_atribuicao.html`.
Campos da tela: Corpo [corpo].
Comandos: Negrito; Itálico; Sublinhado; Tachado vermelho; Destaque amarelo; Destaque vermelho; Parágrafo; Centralizar; Quebra de linha; Inserir marcador; Salvar; Voltar ao herdado; Salvar para todos; Remover ajuste comum.
Acessos relacionados: Abrir modelos dos atos; Abrir modelos avulsos; · ajuste(s); Modelos dos documentos.

## Protesto

### O roteiro das Centrais

Caminho: Protesto > O balcão > O roteiro das Centrais.
Tela-fonte: `templates/protesto_painel.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: Títulos; Remessa da CRA; A protestar; Retorno à CRA; Abrir a tela.

### Títulos

Caminho: Protesto > O balcão > Títulos.
Tela-fonte: `templates/atrib_lista.html`.
Campos da tela: Termo [q]; Situação [situacao].
Comandos: Procurar.
Acessos relacionados: Importar arquivo Acervo do E-Ofício (ZIP, SQLite ou pasta). Prévia antes de; Digitar as informações Um assento por vez — nascimento, casamento ou óbito ; Importar do acervo O acervo do E-Ofício (com o campo do caminho). Traz o re; Digitar as informações Um registro por vez — para quando a cédula já tem nú; Importações do RI O que já foi importado, o que ficou em quarentena e por q; o roteiro inteiro das Centrais; Certidão de protesto; + Nascimento; + Casamento; + Óbito; Importar arquivo; Averbações; e mais 7 links.

### Certidões

Caminho: Protesto > O balcão > Certidões.
Tela-fonte: `templates/protesto_certidoes.html`.
Campos da tela: Nome [nome]; CPF ou CNPJ [documento]; Período de busca [anos]; Tipo [tipo]; Requerente (opcional) [requerente]; Finalidade (opcional) [finalidade]; Selo (opcional) [selo]; Procurar nas emitidas [q].
Comandos: Procurar; Emitir certidão.
Acessos relacionados: ← Títulos; Limpar.

### Instrumentos

Caminho: Protesto > O balcão > Instrumentos.
Tela-fonte: `templates/protesto_instrumentos.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Emitir.
Acessos relacionados: ← TÃ­tulos; A protestar.

### Remessa da CRA

Caminho: Protesto > O dia da CRA > Remessa da CRA.
Tela-fonte: `templates/protesto_remessas.html`.
Campos da tela: Arquivo [arquivo] (obrigatório na tela).
Comandos: Conferir.
Acessos relacionados: ← Títulos; Retorno à CRA; baixar; abrir.

### Imagens dos títulos

Caminho: Protesto > O dia da CRA > Imagens dos títulos.
Tela-fonte: `templates/protesto_imagens.html`.
Campos da tela: O pacote de imagens [arquivo] (obrigatório na tela).
Comandos: Anexar as imagens aos títulos.
Acessos relacionados: Remessas da CRA; Títulos; Abrir.

### Avisos e editais

Caminho: Protesto > O dia da CRA > Avisos e editais.
Tela-fonte: `templates/protesto_avisos.html`.
Campos da tela: Desfecho [entregue]; Se não foi, por quê [motivo]; Quem recebeu (se foi entregue) [recebido_por]; Quem entregou [entregador]; Observação [observacao].
Comandos: Publicar edital; Registrar.
Acessos relacionados: ← Títulos; Remessa da CRA; .odt; A folha do dia, para afixar.

### Desistências

Caminho: Protesto > O dia da CRA > Desistências.
Tela-fonte: `templates/protesto_desistencias.html`.
Campos da tela: Arquivo [arquivo] (obrigatório na tela).
Comandos: Conferir.
Acessos relacionados: ← Títulos; Remessa da CRA; abrir.

### A protestar

Caminho: Protesto > O dia da CRA > A protestar.
Tela-fonte: `templates/protesto_a_protestar.html`.
Campos da tela: Titulo id [titulo_id].
Comandos: Lavrar o protesto dos marcados.
Acessos relacionados: Avisos e editais; Retorno à CRA; Ver desistências; Abrir e protestar.

### Retorno à CRA

Caminho: Protesto > O dia da CRA > Retorno à CRA.
Tela-fonte: `templates/protesto_retornos.html`.
Campos da tela: Dia [dia]; Remessa nº [numero_da_remessa]; Letra da 566 [marca].
Comandos: Gerar retorno + andamento.
Acessos relacionados: ← Títulos.

### CRA — falar pela API

Caminho: Protesto > O dia da CRA > CRA — falar pela API.
Tela-fonte: `templates/protesto_cra_api.html`.
Campos da tela: Ambiente [ambiente]; O que trazer [o_que]; Nome do arquivo [nome]; Com imagem [com_imagem]; O que consultar [consulta]; Protocolo [protocolo]; Data do protocolo [data_protocolo]; Nome do arquivo (só na autorização) [nome]; Marcar baixado [marcar_baixado]; Nosso número [nosso_numero]; Número do título [numero_titulo]; Documento do devedor [documento_devedor]; Saldo [saldo]; Vencimento [vencimento]; Remessa [remessa]; Solicitação — de [solicitacao_de]; Solicitação — até [solicitacao_ate]; Remessa — de [remessa_de]; Remessa — até [remessa_ate].
Comandos: Testar a ligação; Trazer da CRA; Consultar na CRA.
Acessos relacionados: O roteiro do dia; Remessa da CRA; Pendências da CENPROT; Administrativo → Configurações → Centrais de Protesto.

### Pendências da CENPROT

Caminho: Protesto > O dia da CENPROT > Pendências da CENPROT.
Tela-fonte: `templates/protesto_pendencias.html`.
Campos da tela: Espécie [especie]; Ambiente [ambiente]; De [inicio]; Até [fim].
Comandos: Baixar da CENPROT; Testar; Enviar as à CENPROT ( ).
Acessos relacionados: O roteiro do dia; Chave do CENPROT; Remessas da CRA; Títulos; Administrativo → Configurações → Centrais de Protesto.

### Intimação Digital

Caminho: Protesto > O dia da CENPROT > Intimação Digital.
Tela-fonte: `templates/protesto_resolve.html`.
Campos da tela: Ambiente [ambiente]; Titulo id [titulo_id].
Comandos: Trocar; Mandar os marcados; Perguntar o estado à Central; Testar a ligação; comprovantes.
Acessos relacionados: Administrativo → Configurações; carregue o XML diário; Chave do CENPROT.

### Chave do CENPROT

Caminho: Protesto > O dia da CENPROT > Chave do CENPROT.
Tela-fonte: `templates/protesto_cenprot.html`.
Campos da tela: O arquivo do CENPROT [arquivo] (obrigatório na tela); Ambiente [ambiente]; Dia dos editais [dia].
Comandos: Guardar as chaves; Baixar o arquivo de emolumentos; Enviar à CENPROT pela API; Gerar o edital eletrônico.
Acessos relacionados: Remessas da CRA; Imagens dos títulos; Títulos; Livros e acervo — Trazer o acervo do E-Ofício; Avisos e editais.

### Trazer protesto do E-Ofício

Caminho: Protesto > O dia da CENPROT > Trazer protesto do E-Ofício.
Tela-fonte: `templates/protesto_importar_eoficio.html`.
Campos da tela: Quais [quais].
Comandos: Trazer agora do E-Ofício ao vivo.
Acessos relacionados: ← O roteiro; Chave do CENPROT; Carga de todas as atribuições; Trazer o acervo do E-Ofício; XML do CENPROT; Remessa da CRA; Desistências; Imagens dos títulos.

### Modelos dos documentos

Caminho: Protesto > Modelos > Modelos dos documentos.
Tela-fonte: `templates/modelos_atribuicao.html`.
Campos da tela: Corpo [corpo].
Comandos: Negrito; Itálico; Sublinhado; Tachado vermelho; Destaque amarelo; Destaque vermelho; Parágrafo; Centralizar; Quebra de linha; Inserir marcador; Salvar; Voltar ao herdado; Salvar para todos; Remover ajuste comum.
Acessos relacionados: Abrir modelos dos atos; Abrir modelos avulsos; · ajuste(s); Modelos dos documentos.

## Registro Civil das Pessoas Naturais

### Assentos

Caminho: Registro Civil das Pessoas Naturais > O balcão > Assentos.
Tela-fonte: `templates/atrib_lista.html`.
Campos da tela: Termo [q]; Situação [situacao].
Comandos: Procurar.
Acessos relacionados: Importar arquivo Acervo do E-Ofício (ZIP, SQLite ou pasta). Prévia antes de; Digitar as informações Um assento por vez — nascimento, casamento ou óbito ; Importar do acervo O acervo do E-Ofício (com o campo do caminho). Traz o re; Digitar as informações Um registro por vez — para quando a cédula já tem nú; Importações do RI O que já foi importado, o que ficou em quarentena e por q; o roteiro inteiro das Centrais; Certidão de protesto; + Nascimento; + Casamento; + Óbito; Importar arquivo; Averbações; e mais 7 links.

### Averbações

Caminho: Registro Civil das Pessoas Naturais > O balcão > Averbações.
Tela-fonte: `templates/atrib_rcpn_averbacoes.html`.
Campos da tela: Nome ou matrícula [q]; Situação [situacao].
Comandos: Procurar.
Acessos relacionados: ← Assentos; Novo registro; Limpar; Averbar; ← anterior; próxima →.

### Certidões

Caminho: Registro Civil das Pessoas Naturais > O balcão > Certidões.
Tela-fonte: `templates/rc_certidoes.html`.
Campos da tela: Nome ou matrícula [q].
Comandos: Procurar.
Acessos relacionados: ← Assentos; Abrir; Carga do acervo; Ver.

### Folhas de segurança

Caminho: Registro Civil das Pessoas Naturais > O balcão > Folhas de segurança.
Tela-fonte: `templates/rcpn_papel.html`.
Campos da tela: O número da folha [codigo] (obrigatório na tela); O que aconteceu [motivo] (obrigatório na tela); Fornecedor [fornecedor] (obrigatório na tela); Série (a letra da caixa) [serie]; Do número [codigo_de] (obrigatório na tela); Ao número [codigo_ate] (obrigatório na tela); Nota fiscal (opcional) [nota_fiscal]; Tipo do papel (opcional) [tipo]; Observação (opcional) [observacao]; Por quê [motivo] (obrigatório na tela).
Comandos: Inutilizar a folha; Dar entrada na caixa; Inutilizar as em branco desta remessa.

### Pedidos da Central

Caminho: Registro Civil das Pessoas Naturais > O balcão > Pedidos da Central.
Tela-fonte: `templates/rcpn_pedidos.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Baixar.
Acessos relacionados: Administrativo → Configurações; Ver; todos os módulos; Abrir.

### Documentos avulsos (modelos do E-Ofício)

Caminho: Registro Civil das Pessoas Naturais > O balcão > Documentos avulsos (modelos do E-Ofício).
Tela-fonte: `templates/rcpn_modelos.html`.
Campos da tela: Espécie [especie] (obrigatório na tela); Nome do modelo [nome] (obrigatório na tela); Texto [corpo] (obrigatório na tela).
Comandos: Cadastrar.
Acessos relacionados: Administrativo → Modelos dos documentos; todas as espécies; Cadastrar um modelo; Montar.

### Novo registro de nascimento

Caminho: Registro Civil das Pessoas Naturais > Nascimento > Novo registro de nascimento.
Tela-fonte: `templates/atrib_rcpn_escolher.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Consultar assentos; Importar arquivo; Averbações; Digitar informações deste tipo Abrir a tela deste registro.

### Teores do nascimento

Caminho: Registro Civil das Pessoas Naturais > Nascimento > Teores do nascimento.
Tela-fonte: `templates/rcpn_formulario.html`.
Campos da tela: {item} [{item}]; * — masculino feminino [{item}]; Número do assento de nascimento [assento].
Comandos: Ver como fica; Preencher com este.
Acessos relacionados: Voltar; abrir.

### Registro tardio

Caminho: Registro Civil das Pessoas Naturais > Nascimento > Registro tardio.
Tela-fonte: `templates/rcpn_registro_tardio.html`.
Campos da tela: Idade do registrando [idade]; Tem dnv [tem_dnv]; Testemunhas já colhidas [testemunhas].
Comandos: Conferir.

### Gêmeos

Caminho: Registro Civil das Pessoas Naturais > Nascimento > Gêmeos.
Tela-fonte: `templates/rcpn_gemeos.html`.
Campos da tela: é o [ordem] (obrigatório na tela); irmão de [irmao_id] (obrigatório na tela).
Comandos: Gravar.

### CPF do registrado

Caminho: Registro Civil das Pessoas Naturais > Nascimento > CPF do registrado.
Tela-fonte: `templates/rcpn_cpf.html`.
Campos da tela: CPF que a Receita gerou [cpf].
Comandos: copiar; Copiar todos; Gravar.
Acessos relacionados: ⤵ Preencher CPF na CRC; Abrir a inscrição na CRC.

### Registro do casamento

Caminho: Registro Civil das Pessoas Naturais > Casamento > Registro do casamento.
Tela-fonte: `templates/atrib_rcpn_escolher.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Consultar assentos; Importar arquivo; Averbações; Digitar informações deste tipo Abrir a tela deste registro.

### 1 · Habilitação

Caminho: Registro Civil das Pessoas Naturais > Casamento > 1 · Habilitação.
Tela-fonte: `templates/rcpn_habilitacoes.html`.
Campos da tela: Busca [busca]; Situacao [situacao].
Comandos: Procurar.
Acessos relacionados: Abrir habilitação; Assentos do Registro Civil; Limpar.

### 2 · Edital de proclamas

Caminho: Registro Civil das Pessoas Naturais > Casamento > 2 · Edital de proclamas.
Tela-fonte: `templates/rcpn_habilitacoes.html`.
Campos da tela: Busca [busca]; Situacao [situacao].
Comandos: Procurar.
Acessos relacionados: Abrir habilitação; Assentos do Registro Civil; Limpar.

### 2b · Enviar ao e-Proclamas

Caminho: Registro Civil das Pessoas Naturais > Casamento > 2b · Enviar ao e-Proclamas.
Tela-fonte: `templates/rcpn_proclamas.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Testar a ligação com a Central.
Acessos relacionados: Editais publicados; Administrativo → Configurações; Habilitação; Conferir.

### 3 · Prontas para casar

Caminho: Registro Civil das Pessoas Naturais > Casamento > 3 · Prontas para casar.
Tela-fonte: `templates/rcpn_habilitacoes.html`.
Campos da tela: Busca [busca]; Situacao [situacao].
Comandos: Procurar.
Acessos relacionados: Abrir habilitação; Assentos do Registro Civil; Limpar.

### Teores do casamento

Caminho: Registro Civil das Pessoas Naturais > Casamento > Teores do casamento.
Tela-fonte: `templates/rcpn_formulario.html`.
Campos da tela: {item} [{item}]; * — masculino feminino [{item}]; Número do assento de nascimento [assento].
Comandos: Ver como fica; Preencher com este.
Acessos relacionados: Voltar; abrir.

### Novo registro de óbito

Caminho: Registro Civil das Pessoas Naturais > Óbito > Novo registro de óbito.
Tela-fonte: `templates/atrib_rcpn_escolher.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Consultar assentos; Importar arquivo; Averbações; Digitar informações deste tipo Abrir a tela deste registro.

### Teores do óbito

Caminho: Registro Civil das Pessoas Naturais > Óbito > Teores do óbito.
Tela-fonte: `templates/rcpn_formulario.html`.
Campos da tela: {item} [{item}]; * — masculino feminino [{item}]; Número do assento de nascimento [assento].
Comandos: Ver como fica; Preencher com este.
Acessos relacionados: Voltar; abrir.

### Comunicações mensais

Caminho: Registro Civil das Pessoas Naturais > Óbito > Comunicações mensais.
Tela-fonte: `templates/rcpn_comunicacoes.html`.
Campos da tela: Competência [competencia] (obrigatório na tela).
Comandos: abrir as cinco; Abrir as cinco.
Acessos relacionados: ver o texto.

### O que falta perguntar

Caminho: Registro Civil das Pessoas Naturais > Óbito > O que falta perguntar.
Tela-fonte: `templates/rcpn_marcas_do_obito.html`.
Campos da tela: {item} [{item}].
Comandos: Gravar as respostas deste óbito; desfazer « ».

### Retificação e suprimento

Caminho: Registro Civil das Pessoas Naturais > Assento já lavrado > Retificação e suprimento.
Tela-fonte: `templates/rcpn_retificacoes.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: Abrir processo; abrir.

### Atos sem checklist

Caminho: Registro Civil das Pessoas Naturais > Assento já lavrado > Atos sem checklist.
Tela-fonte: `templates/rcpn_checklist_pendente.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: Conferir.

### Termos a escrever

Caminho: Registro Civil das Pessoas Naturais > Assento já lavrado > Termos a escrever.
Tela-fonte: `templates/rcpn_termos.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ver o termo.

### Informações importadas

Caminho: Registro Civil das Pessoas Naturais > Assento já lavrado > Informações importadas.
Tela-fonte: `templates/rcpn_informacoes_importadas.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: Importar arquivo; Digitar as informações; Lista de assentos; nº.

### Importar arquivo (acervo)

Caminho: Registro Civil das Pessoas Naturais > Assento já lavrado > Importar arquivo (acervo).
Tela-fonte: `templates/rcpn_importar_acervo.html`.
Campos da tela: Arquivo (.zip da exportação ou .sqlite3) [arquivo]; Ou caminho da pasta / do SQLite nesta máquina [pasta].
Comandos: Carregar acervo no disco; Atualizar prévia; Importar os que faltam; Nada novo para importar; Montar a prévia.
Acessos relacionados: Digitar as informações → Novo assento; Lista de assentos; Nascimento; Casamento; Óbito; Ver informações importadas; Abrir «Importar de outro sistema» (assento RCPN).

### Digitar informações (assento)

Caminho: Registro Civil das Pessoas Naturais > Assento já lavrado > Digitar informações (assento).
Tela-fonte: `templates/atrib_rcpn_escolher.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Consultar assentos; Importar arquivo; Averbações; Digitar informações deste tipo Abrir a tela deste registro.

### CPF nos assentos antigos

Caminho: Registro Civil das Pessoas Naturais > Assento já lavrado > CPF nos assentos antigos.
Tela-fonte: `templates/rcpn_dados_cadastrais.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: abrir.

### Matrículas

Caminho: Registro Civil das Pessoas Naturais > Assento já lavrado > Matrículas.
Tela-fonte: `templates/rcpn_matriculas.html`.
Campos da tela: Matricula [matricula].
Comandos: Conferir.

### Conferência da filiação

Caminho: Registro Civil das Pessoas Naturais > Assento já lavrado > Conferência da filiação.
Tela-fonte: `templates/rcpn_filiacao.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: nº.

### O que comunicar hoje

Caminho: Registro Civil das Pessoas Naturais > Comunicações e remessas > O que comunicar hoje.
Tela-fonte: `templates/rcpn_painel.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: abrir.

### Remessa do SIRC

Caminho: Registro Civil das Pessoas Naturais > Comunicações e remessas > Remessa do SIRC.
Tela-fonte: `templates/rcpn_sirc.html`.
Campos da tela: Competência [competencia]; De que mês [competencia].
Comandos: Baixar o lote — ( registros, bytes); Baixar o lote para upload manual (.mrc); Validar o lote na API; Enviar o lote pela API; Gerar a declaração; Enviar agora pela API; Baixar o lote ( registros, bytes).
Acessos relacionados: abrir e corrigir; Administrativo → Configurações.

### Comunicação à FUNAI

Caminho: Registro Civil das Pessoas Naturais > Comunicações e remessas > Comunicação à FUNAI.
Tela-fonte: `templates/rcpn_funai.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: o ofício.

### Carga da CRC

Caminho: Registro Civil das Pessoas Naturais > Comunicações e remessas > Carga da CRC.
Tela-fonte: `templates/rcpn_crc.html`.
Campos da tela: Nota [nota]; Ambiente [ambiente]; Driver [driver] (obrigatório na tela); Pin [pin] (obrigatório na tela); Assento [assento].
Comandos: Baixar o XML; Marcar como já enviado; Enviar à CRC agora; Montar o arquivo; Desmarcar todos; Já enviei estes, no site da CRC.
Acessos relacionados: ver o histórico de envios; ver os já enviados; esconder os já enviados de novo; abrir e corrigir; remessa do SIRC; n..

### Anotações devidas

Caminho: Registro Civil das Pessoas Naturais > Comunicações e remessas > Anotações devidas.
Tela-fonte: `templates/rcpn_anotacoes.html`.
Campos da tela: Nº do assento anotado (id) [assento_alvo_id] (obrigatório na tela); Por onde [canal]; Serventia de destino [serventia] (obrigatório na tela); Protocolo ou comprovante de recebimento [protocolo] (obrigatório na tela); Motivo [motivo] (obrigatório na tela).
Comandos: Registrar que anotei; Registrar a comunicação; Dispensar com motivo.
Acessos relacionados: Ver o texto da comunicação.

### Anotação da CRC

Caminho: Registro Civil das Pessoas Naturais > Comunicações e remessas > Anotação da CRC.
Tela-fonte: `templates/rcpn_anotacao_crc.html`.
Campos da tela: Arquivo HTML da CRC (.html / .htm) [arquivo] (obrigatório na tela); Modelo [modelo]; Filtrar por espécie [especie]; Cidade (fechamento) [cidade_destino]; Assinatura (placeholder) [assinatura].
Comandos: Montar prévia; Selecionar e copiar todos.
Acessos relacionados: ← Voltar às Anotações devidas.

### Remessa do IBGE

Caminho: Registro Civil das Pessoas Naturais > Comunicações e remessas > Remessa do IBGE.
Tela-fonte: `templates/rcpn_ibge.html`.
Campos da tela: Ano [ano]; Trimestre [trimestre]; Por onde [canal]; Protocolo [protocolo].
Comandos: Ver o que sairia; Baixar CARTINF.ZIP; Já entreguei este trimestre.

### Modelos dos documentos (papéis da casa)

Caminho: Registro Civil das Pessoas Naturais > Modelos > Modelos dos documentos (papéis da casa).
Tela-fonte: `templates/modelos_atribuicao.html`.
Campos da tela: Corpo [corpo].
Comandos: Negrito; Itálico; Sublinhado; Tachado vermelho; Destaque amarelo; Destaque vermelho; Parágrafo; Centralizar; Quebra de linha; Inserir marcador; Salvar; Voltar ao herdado; Salvar para todos; Remover ajuste comum.
Acessos relacionados: Abrir modelos dos atos; Abrir modelos avulsos; · ajuste(s); Modelos dos documentos.

## RCPJ e RTD — pessoas jurídicas e títulos

### RTD — títulos apresentados

Caminho: RCPJ e RTD — pessoas jurídicas e títulos > O balcão > RTD — títulos apresentados.
Tela-fonte: `templates/rcpj_rtd_titulos.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: + Receber título; Registros já lavrados; ver todos.

### RCPJ — títulos apresentados

Caminho: RCPJ e RTD — pessoas jurídicas e títulos > O balcão > RCPJ — títulos apresentados.
Tela-fonte: `templates/rcpj_rtd_titulos.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: + Receber título; Registros já lavrados; ver todos.

### Etiquetas de selos externos

Caminho: RCPJ e RTD — pessoas jurídicas e títulos > O balcão > Etiquetas de selos externos.
Tela-fonte: `templates/rcpj_rtd_etiquetas_selos_externos.html`.
Campos da tela: Número do selo [selo_manual] (obrigatório na tela); Texto do registro ou da averbação [texto_registro] (obrigatório na tela); De [inicio]; Até [fim]; Parte, ato ou número do selo [busca]; Selo [selo].
Comandos: Montar etiqueta para imprimir; Procurar; Imprimir etiquetas marcadas; Marcar todos.
Acessos relacionados: Limpar.

### Central ONRTDPJ — a fila de lá

Caminho: RCPJ e RTD — pessoas jurídicas e títulos > O balcão > Central ONRTDPJ — a fila de lá.
Tela-fonte: `templates/rcpj_rtd_onrtdpj.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Testar a ligação; Trazer.
Acessos relacionados: ← Títulos apresentados; Administrativo → Configurações; Trazer para; o arquivo, na Central.

### RCPJ — registros lavrados

Caminho: RCPJ e RTD — pessoas jurídicas e títulos > Registro já lavrado > RCPJ — registros lavrados.
Tela-fonte: `templates/atrib_lista.html`.
Campos da tela: Termo [q]; Situação [situacao].
Comandos: Procurar.
Acessos relacionados: Importar arquivo Acervo do E-Ofício (ZIP, SQLite ou pasta). Prévia antes de; Digitar as informações Um assento por vez — nascimento, casamento ou óbito ; Importar do acervo O acervo do E-Ofício (com o campo do caminho). Traz o re; Digitar as informações Um registro por vez — para quando a cédula já tem nú; Importações do RI O que já foi importado, o que ficou em quarentena e por q; o roteiro inteiro das Centrais; Certidão de protesto; + Nascimento; + Casamento; + Óbito; Importar arquivo; Averbações; e mais 7 links.

### RTD — registros lavrados

Caminho: RCPJ e RTD — pessoas jurídicas e títulos > Registro já lavrado > RTD — registros lavrados.
Tela-fonte: `templates/atrib_lista.html`.
Campos da tela: Termo [q]; Situação [situacao].
Comandos: Procurar.
Acessos relacionados: Importar arquivo Acervo do E-Ofício (ZIP, SQLite ou pasta). Prévia antes de; Digitar as informações Um assento por vez — nascimento, casamento ou óbito ; Importar do acervo O acervo do E-Ofício (com o campo do caminho). Traz o re; Digitar as informações Um registro por vez — para quando a cédula já tem nú; Importações do RI O que já foi importado, o que ficou em quarentena e por q; o roteiro inteiro das Centrais; Certidão de protesto; + Nascimento; + Casamento; + Óbito; Importar arquivo; Averbações; e mais 7 links.

### Últimos atos praticados

Caminho: RCPJ e RTD — pessoas jurídicas e títulos > Registro já lavrado > Últimos atos praticados.
Tela-fonte: `templates/atrib_rcpj_rtd_ultimos_atos.html`.
Campos da tela: Atribuição [atribuicao]; Tipo de ato [tipo].
Comandos: Filtrar.
Acessos relacionados: Limpar; nº; ← anterior; próxima →.

### Certidões de inteiro teor

Caminho: RCPJ e RTD — pessoas jurídicas e títulos > Registro já lavrado > Certidões de inteiro teor.
Tela-fonte: `templates/atrib_certidoes.html`.
Campos da tela: Atribuição [atribuicao]; Termo [q].
Comandos: Procurar.
Acessos relacionados: RCPJ e RTD; Livro 3; Limpar.

### Ajustar a etiqueta de registro

Caminho: RCPJ e RTD — pessoas jurídicas e títulos > Configuração > Ajustar a etiqueta de registro.
Tela-fonte: `templates/rcpj_rtd_etiqueta_ajuste.html`.
Campos da tela: Largura (mm) [etiqueta_largura_mm] (obrigatório na tela); Altura (mm) [etiqueta_altura_mm] (obrigatório na tela); Margem interna (mm) [etiqueta_margem_mm] (obrigatório na tela); Corpo da letra (pt) [etiqueta_corpo_pt] (obrigatório na tela); Deslocar na horizontal (mm) [etiqueta_deslocamento_x_mm] (obrigatório na tela); Deslocar na vertical (mm) [etiqueta_deslocamento_y_mm] (obrigatório na tela); Entrelinha [etiqueta_entrelinha] (obrigatório na tela); Tamanho do QR (mm) [etiqueta_qr_mm] (obrigatório na tela).
Comandos: Guardar as medidas.
Acessos relacionados: ← Títulos apresentados.

### Modelos dos documentos

Caminho: RCPJ e RTD — pessoas jurídicas e títulos > Modelos > Modelos dos documentos.
Tela-fonte: `templates/modelos_atribuicao.html`.
Campos da tela: Corpo [corpo].
Comandos: Negrito; Itálico; Sublinhado; Tachado vermelho; Destaque amarelo; Destaque vermelho; Parágrafo; Centralizar; Quebra de linha; Inserir marcador; Salvar; Voltar ao herdado; Salvar para todos; Remover ajuste comum.
Acessos relacionados: Abrir modelos dos atos; Abrir modelos avulsos; · ajuste(s); Modelos dos documentos.

## Livros e acervo

### Livros e termos

Caminho: Livros e acervo > Livros e termos.
Tela-fonte: `templates/nucleo_livros.html`.
Campos da tela: Dia [dia] (obrigatório na tela); Folhas [folhas].
Comandos: Abrir livro.
Acessos relacionados: Encerrar os dias; n.; abertura; encerramento.

### Encerramento diário

Caminho: Livros e acervo > Encerramento diário.
Tela-fonte: `templates/nucleo_encerramento_diario.html`.
Campos da tela: Dia [dia].
Comandos: Encerrar o dia.
Acessos relacionados: ← Livros.

### Numeração dos livros

Caminho: Livros e acervo > Numeração dos livros.
Tela-fonte: `templates/nucleo_numeracao.html`.
Campos da tela: Próximo número [proximo] (obrigatório na tela); Por quê [motivo].
Comandos: Informar.
Acessos relacionados: carga do acervo.

### O que falta informar

Caminho: Livros e acervo > O que falta informar.
Tela-fonte: `templates/implantacao.html`.
Campos da tela: Próximo número [proximo] (obrigatório na tela); De onde saiu esse número [observacao]; O que foi decidido [observacao] (obrigatório na tela); Por que não se aplica [motivo] (obrigatório na tela).
Comandos: Informar; Registrar a decisão; Dispensar; reabrir.
Acessos relacionados: Livros e termos; Numeração dos livros.

### Trazer o acervo do E-Ofício

Caminho: Livros e acervo > Trazer o acervo do E-Ofício.
Tela-fonte: `templates/atrib_importar.html`.
Campos da tela: Quais [quais].
Comandos: Trazer do E-Ofício.
Acessos relacionados: Numeração dos livros; Abrir a numeração dos livros.

### Importar de outro sistema

Caminho: Livros e acervo > Importar de outro sistema.
Tela-fonte: `templates/importar_padrao.html`.
Campos da tela: O que você vai importar [especie]; Envie o arquivo .json [arquivo]; Texto [texto].
Comandos: escolher; Conferir; Preencher o formulário do ato novo; Importar os que passaram.

### Importar matrícula do RI

Caminho: Livros e acervo > Importar matrícula do RI.
Tela-fonte: `templates/importar_padrao.html`.
Campos da tela: O que você vai importar [especie]; Envie o arquivo .json [arquivo]; Texto [texto].
Comandos: escolher; Conferir; Preencher o formulário do ato novo; Importar os que passaram.

## Malote

### Expedientes / Malote

Caminho: Malote > Expedientes / Malote.
Tela-fonte: `templates/expedientes.html`.
Campos da tela: Via de entrada [source]; Referência externa [external_reference]; Assunto [subject] (obrigatório na tela); Remetente [sender]; Classificação [category]; Setor [sector]; Data de recebimento [received_at] (obrigatório na tela); Data-base do prazo [deadline_start]; Prazo em dias [deadline_days]; Prioridade [priority]; Responsável [assigned_user_id]; Substituto [backup_user_id]; Arquivos recebidos [files]; Observações [notes].
Comandos: Cadastrar recebimento.

### Expedientes prontos para encerrar

Caminho: Malote > Expedientes prontos para encerrar.
Tela-fonte: `templates/expedientes_prontos.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Expedientes; Encerrar.

### Tarefas e pendências

Caminho: Malote > Tarefas e pendências.
Tela-fonte: `templates/tasks.html`.
Campos da tela: Título [title] (obrigatório na tela); Setor [sector]; Sistema/tema [system_name]; Prioridade [priority]; Data-base [start_date]; Prazo em dias [due_days]; Vencimento direto [due_date]; Responsável [assigned_user_id]; Substituto [backup_user_id]; Evidence required [evidence_required]; Referência normativa [legal_ref]; Descrição [description]; Status [status]; Sector [sector].
Comandos: Criar tarefa; Filtrar.

### Inspeções

Caminho: Malote > Inspeções.
Tela-fonte: `templates/inspections.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.

## Administrativo

### Caixa

Caminho: Administrativo > Dinheiro > Caixa.
Tela-fonte: `templates/caixa.html`.
Campos da tela: Saldo inicial (dinheiro em caixa) [saldo_inicial]; Natureza [natureza]; Forma de pagamento [forma_pagamento]; Valor [valor] (obrigatório na tela); Protocolo [protocolo]; Pagador [pagador]; CPF/CNPJ [pagador_documento]; Descrição [descricao]; Emolumentos [emolumentos]; Selo [selo]; FERC [ferc]; FADEP [fadep]; FEMP [femp]; FERRFIS [ferrfis]; Forma [forma_pagamento]; Motivo [motivo] (obrigatório na tela); Contado [valor_contado] (obrigatório na tela); Justificativa (obrigatória se houver diferença) [justificativa].
Comandos: Abrir o caixa de hoje; Lançar; emitir recibo; salvar alteração; estornar; excluir; Fechar o caixa; Conferi.
Acessos relacionados: Protocolo geral; Recibos; Tabela de emolumentos; recibo.

### Protocolo geral

Caminho: Administrativo > Dinheiro > Protocolo geral.
Tela-fonte: `templates/caixa_protocolos.html`.
Campos da tela: Interessado [interessado] (obrigatório na tela); CPF/CNPJ [interessado_documento]; Telefone [telefone]; E-mail [email]; Para que serve [tipo]; Atribuição [atribuicao]; Previsão de entrega [previsao_entrega]; Documento apresentado [documento_tipo]; Nº do documento [documento_numero]; Descrição do documento [documento_descricao]; Assunto [assunto]; Observação [observacao]; Prenotação do RI (Livro 1) [ri_protocolo_id]; Situação [situacao]; Buscar [busca].
Comandos: Abrir protocolo; Filtrar.
Acessos relacionados: ← Caixa; ← anterior; próxima →.

### Protocolos parados

Caminho: Administrativo > Dinheiro > Protocolos parados.
Tela-fonte: `templates/caixa_protocolos_parados.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Todos os protocolos; Abrir.

### Depósito prévio

Caminho: Administrativo > Dinheiro > Depósito prévio.
Tela-fonte: `templates/caixa_depositos.html`.
Campos da tela: Depositante [depositante] (obrigatório na tela); CPF/CNPJ [depositante_documento]; Data do depósito [data]; Valor [valor] (obrigatório na tela); Forma de pagamento [forma_pagamento]; Observação [observacao]; Atribuição [atribuicao]; Serviço do catálogo [servico_codigo]; Mostrar [mostrar]; Buscar [busca]; Procurar o serviço no catálogo [servico_termo]; Valor usar [valor_usar] (obrigatório na tela); Protocolo [protocolo]; Motivo [motivo] (obrigatório na tela).
Comandos: Preencher o tipo dos depósitos que têm vínculo; Registrar depósito; Filtrar; Procurar; usar; devolver.
Acessos relacionados: ← Caixa; escolher.

### Recibos

Caminho: Administrativo > Dinheiro > Recibos.
Tela-fonte: `templates/caixa_recibos.html`.
Campos da tela: Buscar [busca].
Comandos: Procurar.
Acessos relacionados: ← Caixa; 2ª via.

### Emolumentos

Caminho: Administrativo > Dinheiro > Emolumentos.
Tela-fonte: `templates/caixa_emolumentos.html`.
Campos da tela: Código do TJ ou palavra da descrição [busca]; Valor do negócio [valor]; Tabela [tabela].
Comandos: Importar do E-Ofício; Procurar; Calcular.
Acessos relacionados: ← Caixa.

### Selos emitidos

Caminho: Administrativo > Dinheiro > Selos emitidos.
Tela-fonte: `templates/selos_emitidos.html`.
Campos da tela: De (data) [inicio]; Até [fim]; Especialidade [atribuicao]; Usuário [quem]; Tipo do ato (pelo selo) [tipo]; Ato (caminho do selador) [caminho]; Situação [situacao]; Número do selo [numero]; Agrupar [agrupar].
Comandos: Procurar.
Acessos relacionados: tela de selos do Registro de Imóveis; Limpar; ← anterior; próxima →.

### Atendimento / senhas

Caminho: Administrativo > Atendimento > Atendimento / senhas.
Tela-fonte: `templates/service_queue.html`.
Campos da tela: Service type [service_type]; Priority [priority].
Comandos: Gerar senha; Chamar; Iniciar; Finalizar.

### WhatsApp

Caminho: Administrativo > Atendimento > WhatsApp.
Tela-fonte: `templates/whatsapp_lista.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: puxar caixa-postal.
Acessos relacionados: Configuração Meta.

### Robôs

Caminho: Administrativo > Atendimento > Robôs.
Tela-fonte: `templates/robos_lista.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: novo robô; configuração de API.

### O que ficou pelo caminho

Caminho: Administrativo > Atendimento > O que ficou pelo caminho.
Tela-fonte: `templates/inacabados.html`.
Campos da tela: Ligada {item} [ligada_{item}]; Dias {item} [dias_{item}]; Atribuição [atribuicao]; So parados [so_parados].
Comandos: Guardar o ajuste; filtrar.
Acessos relacionados: ver; abrir; anotar.

### Rascunhos

Caminho: Administrativo > Atendimento > Rascunhos.
Tela-fonte: `templates/rascunhos.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: apagar.
Acessos relacionados: abrir.

### Consultar fraudes

Caminho: Administrativo > Atendimento > Consultar fraudes.
Tela-fonte: `templates/fraude_consultar.html`.
Campos da tela: Nome [nome]; CPF ou CNPJ [documento]; O que você decidiu [decisao]; Referência (protocolo, título…) [referencia]; O que você conferiu [observacao].
Comandos: Consultar; Registrar a conferência.

### Relatórios

Caminho: Administrativo > Atendimento > Relatórios.
Tela-fonte: `templates/reports.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: Exportar tarefas CSV; Exportar expedientes CSV.

### Atenção para fraudes

Caminho: Administrativo > A casa > Atenção para fraudes.
Tela-fonte: `templates/fraudes.html`.
Campos da tela: Papel na fraude [papel] (obrigatório na tela); Nome [nome]; CPF ou CNPJ [documento]; De onde veio a comunicação [origem] (obrigatório na tela); Quem comunicou [origem_orgao]; Data da comunicação [origem_data]; O que a comunicação diz, em resumo [observacao]; Procurar [q]; Mostrar [situacao]; Por quê [motivo] (obrigatório na tela).
Comandos: Incluir; Procurar; Tirar; devolver à lista.
Acessos relacionados: Consultar um nome.

### Checklists

Caminho: Administrativo > A casa > Checklists.
Tela-fonte: `templates/checklists.html`.
Campos da tela: Nome [name] (obrigatório na tela); Setor [sector]; Itens, um por linha [items] (obrigatório na tela); Reference [reference].
Comandos: Criar modelo; Iniciar checklist.

### Obrigações recorrentes

Caminho: Administrativo > A casa > Obrigações recorrentes.
Tela-fonte: `templates/recurrences.html`.
Campos da tela: Título [title] (obrigatório na tela); Setor [sector]; Sistema [system_name]; Frequência [frequency]; Próximo vencimento [next_due_date] (obrigatório na tela); Dia preferencial [due_day]; Mês anual [due_month]; Gerar com antecedência de [lead_days]; Responsável [assigned_user_id]; Substituto [backup_user_id]; Evidence required [evidence_required]; Notas [notes].
Comandos: Cadastrar.

### LGPD e governança

Caminho: Administrativo > A casa > LGPD e governança.
Tela-fonte: `templates/lgpd.html`.
Campos da tela: Tipo [item_type]; Título [title] (obrigatório na tela); Responsável [owner_user_id]; Status [status]; Próxima revisão [review_date]; Notas [notes].
Comandos: Cadastrar.

### TI e infraestrutura

Caminho: Administrativo > A casa > TI e infraestrutura.
Tela-fonte: `templates/assets.html`.
Campos da tela: Tipo [kind]; Nome [name] (obrigatório na tela); Identificador [identifier]; Local [location]; Responsável [responsible_user_id]; Status [status]; Validade [expiry_date]; Última verificação [last_check_date]; Notas [notes].
Comandos: Cadastrar.

### Auditoria

Caminho: Administrativo > A casa > Auditoria.
Tela-fonte: `templates/audit.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.

### Integridade

Caminho: Administrativo > A casa > Integridade.
Tela-fonte: `templates/integrity.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.

### Ajuda do sistema

Caminho: Administrativo > Ajuda > Ajuda do sistema.
Tela-fonte: `templates/ajuda.html`.
Campos da tela: Sua pergunta [pergunta] (obrigatório na tela); Assunto [assunto]; Quem responde [modelo]; O que o sistema mostra agora (opcional — cole a mensagem de erro, o... [contexto]; De onde vem a dúvida (opcional) [onde]; Referência (opcional) [referencia].
Comandos: Ver o que sairia; Perguntar.
Acessos relacionados: Configurar; Ver o que foi enviado; Ver problemas diagnosticados; Revisar correções e atualizações; Ver.

### Problemas do sistema

Caminho: Administrativo > Ajuda > Problemas do sistema.
Tela-fonte: `templates/ajuda_problemas.html`.
Campos da tela: Documento [documento]; Texto [texto]; Estado [estado]; Nota dev [nota_dev]; Prova [prova]; Nota [nota] (obrigatório na tela).
Comandos: Conferir a casa; Gerar o relatório para conserto; Importar; Gravar o retorno; Pedir a leitura da ajuda; Reabrir; Resolvido.
Acessos relacionados: Revisar pacote de correção; os resolvidos.

### O que a ajuda sabe do projeto

Caminho: Administrativo > Ajuda > O que a ajuda sabe do projeto.
Tela-fonte: `templates/ajuda_projeto.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: Problemas do sistema; ler; Fechar.

### Base de conhecimento da ajuda

Caminho: Administrativo > Ajuda > Base de conhecimento da ajuda.
Tela-fonte: `templates/ajuda_base.html`.
Campos da tela: Procurar [procurar]; Titulo [titulo] (obrigatório na tela); Assunto [assunto]; Onde [onde]; Texto [texto] (obrigatório na tela).
Comandos: Procurar na base; apagar; Salvar a alteração Gravar na base.
Acessos relacionados: editar; Cancelar.

### Agente do sistema

Caminho: Administrativo > Ajuda > Agente do sistema.
Tela-fonte: `templates/agente.html`.
Campos da tela: O que você quer que ele apure [pedido] (obrigatório na tela); Provedor [provedor]; Modelo (vazio = o padrão do provedor) [modelo].
Comandos: Pedir; desfazer.
Acessos relacionados: Configuração do agente; Problemas do sistema.

### Modelos dos documentos

Caminho: Administrativo > Configuração > Modelos dos documentos.
Tela-fonte: `templates/modelos.html`.
Campos da tela: Enviar o papel ajustado [arquivo] (obrigatório na tela); Corpo [corpo].
Comandos: Enviar; Voltar ao papel do pacote; Gravar o ajuste; Voltar ao padrão do sistema.
Acessos relacionados: todas as atribuições; Documentos avulsos (modelos do E-Ofício); ver e editar; baixar o que vale hoje; Fechar.

### Modelos do caixa

Caminho: Administrativo > Configuração > Modelos do caixa.
Tela-fonte: `templates/modelos_atribuicao.html`.
Campos da tela: Corpo [corpo].
Comandos: Negrito; Itálico; Sublinhado; Tachado vermelho; Destaque amarelo; Destaque vermelho; Parágrafo; Centralizar; Quebra de linha; Inserir marcador; Salvar; Voltar ao herdado; Salvar para todos; Remover ajuste comum.
Acessos relacionados: Abrir modelos dos atos; Abrir modelos avulsos; · ajuste(s); Modelos dos documentos.

### Selador — configuração

Caminho: Administrativo > Configuração > Selador — configuração.
Tela-fonte: `templates/selador_config.html`.
Campos da tela: Impressão digital (SHA-256) apresentada pelo selador [sha256]; Endereço do selador [base_url]; Endereço de homologação [base_homologacao]; Endereço de autenticação [auth_url]; Ambiente [ambiente]; Usuário [usuario]; Senha [senha].
Comandos: Importar do E-Ofício; Ver a impressão digital; Conferi — pode fixar; Testar a conexão; Gravar; Apagar credencial.

### Rede / acesso

Caminho: Administrativo > Configuração > Rede / acesso.
Tela-fonte: `templates/network.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Copiar.
Acessos relacionados: Baixar instalador do acesso cliente.

### Usuários

Caminho: Administrativo > Configuração > Usuários.
Tela-fonte: `templates/users.html`.
Campos da tela: Nome [full_name] (obrigatório na tela); Usuário [username] (obrigatório na tela); Perfil [role]; Senha [password] (obrigatório na tela); Um cargo por linha — é o que sai impresso embaixo da assinatura, e o... [funcoes_cargos]; Full name [full_name] (obrigatório na tela); Username [username] (obrigatório na tela); Role [role]; Funcao [funcao]; New password [new_password] (obrigatório na tela).
Comandos: Criar usuário; Salvar cargos; Salvar; Guardar; Redefinir.

### Corrigir dado do acervo

Caminho: Administrativo > Configuração > Corrigir dado do acervo.
Tela-fonte: `templates/acervo_corrigir.html`.
Campos da tela: Tabela [tabela]; Buscar por [termo]; Campo {item} [campo_{item}]; Motivo da correção — obrigatório [motivo] (obrigatório na tela).
Comandos: Buscar; Salvar correção.
Acessos relacionados: Corrigir.

### Agente — configurar

Caminho: Administrativo > Configuração > Agente — configurar.
Tela-fonte: `templates/agente_configurar.html`.
Campos da tela: Provedor [provedor_padrao]; Modelo (vazio = o padrão do provedor) [modelo_padrao]; Teto de turnos por rodada [teto_de_turnos]; Teto de sessões por dia [teto_de_sessoes]; Escrita ligada [escrita_ligada]; Api key [api_key].
Comandos: Guardar; Gravar a chave; apagar a chave deste provedor.
Acessos relacionados: ← Agente do sistema; Ajuda do sistema — configurar; painel do provedor.

### Ajuda — configurar

Caminho: Administrativo > Configuração > Ajuda — configurar.
Tela-fonte: `templates/ajuda_configurar.html`.
Campos da tela: Provedor [provedor]; Modelo [modelo]; Api key [api_key]; Perfis [perfis]; Por que está mudando (opcional, mas fica registrado) [motivo].
Comandos: Passar a responder por este provedor; Gravar a chave; Apagar a chave; Salvar quem pode consultar.
Acessos relacionados: ← Ajuda do sistema; painel do provedor; Ver.

### Trazer caixa do E-Ofício

Caminho: Administrativo > Configuração > Trazer caixa do E-Ofício.
Tela-fonte: `templates/caixa_importar.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Importar.
Acessos relacionados: ← Protocolo geral.

### Correções e atualizações

Caminho: Administrativo > Configuração > Correções e atualizações.
Tela-fonte: `templates/updates.html`.
Campos da tela: Arquivo oficial de atualização (.cgu) [update_file] (obrigatório na tela); SHA-256 recebido por canal separado [expected_sha256] (obrigatório na tela); Repita o SHA-256 exibido acima [approval_sha256] (obrigatório na tela); Digite exatamente APLICAR [confirmation] (obrigatório na tela); Senha atual do administrador [admin_password] (obrigatório na tela); Review ack [review_ack] (obrigatório na tela).
Comandos: Validar e preparar — sem aplicar; Criar backup, aprovar e aplicar.

### Configurações

Caminho: Administrativo > Configuração > Configurações.
Tela-fonte: `templates/settings.html`.
Campos da tela: Nome da unidade [unit_name]; Registrador (RI) [ri_registrador]; Substituto(a) (RI) [ri_substituta]; Cidade (RI) [ri_cidade]; UF (RI) [ri_uf]; Pasta principal de arquivos [archive_root]; Pasta de backups [backup_dir]; Dias de antecedência dos alertas [alert_days]; Tempo de inatividade da sessão [session_timeout_minutes]; Host do servidor [network_host]; Porta HTTP [network_port]; Discovery enabled [discovery_enabled]; Porta de descoberta [discovery_port]; Retenção de backups automáticos [backup_retention]; Auto backup [auto_backup]; Require backup assignee [require_backup_assignee]; Botão de imprimir — o que ele entrega [impressao_formato_padrao]; Módulo de Protesto — quem pode abrir [modulo_protesto_alcance]; Quantidade mínima de caracteres [password_min_length]; Password require upper [password_require_upper]; Password require lower [password_require_lower]; Password require digit [password_require_digit]; Classificações [categories]; Vias de entrada [sources]; Setores [sectors]; Token [token]; Usuario [usuario]; Senha [senha].
Comandos: Salvar configurações; Guardar; Retirar; Criar e baixar backup completo.
Acessos relacionados: Verificar integridade dos anexos.

## Telas de ficha, etapa e documento

Estas telas não têm entrada própria no menu principal. Abrem a partir de listas, fichas, etapas ou links de outra tela. O nome abaixo vem do título HTML quando há um título estático; caso contrário, do arquivo. Para voltar ao processo ou registro, use o link de retorno da própria tela.

### Sessão do agente #

Tela-fonte: `templates/agente_sessao.html`.
Campos da tela: O que você quer acrescentar [pedido] (obrigatório na tela).
Comandos: Continuar.
Acessos relacionados: ← Agente do sistema; Problemas do sistema.

### Consulta

Tela-fonte: `templates/ajuda_consulta.html`.
Campos da tela: O que faltou, ou o que prestou (opcional) [observacao].
Comandos: Ajudou; Não ajudou.
Acessos relacionados: ← Ajuda do sistema.

### TI/Infra #

Tela-fonte: `templates/asset_detail.html`.
Campos da tela: Tipo [kind]; Nome [name] (obrigatório na tela); Identificador [identifier]; Local [location]; Responsável [responsible_user_id]; Status [status]; Validade [expiry_date]; Última verificação [last_check_date]; Notas [notes].
Comandos: Salvar.

### Certidão n. / —

Tela-fonte: `templates/atrib_certidao.html`.
Campos da tela: Por que está sendo cancelada [motivo] (obrigatório na tela); Selo cancelado tjma [selo_cancelado_tjma] (obrigatório na tela).
Comandos: Cancelar a certidão.
Acessos relacionados: ← Certidões; Imprimir (PDF); Baixar em .odt; Abrir o registro.

### Livro 3 — registro nº

Tela-fonte: `templates/atrib_livro3_ficha.html`.
Campos da tela: Natureza do título (sai dentro do selo) [natureza_titulo]; Item da tabela de custas [codigo_tj]; Valor declarado (vazio = sem valor) [base_calculo]; Arquivo [arquivo] (obrigatório na tela); Nome [nome] (obrigatório na tela); CPF ou CNPJ (opcional) [documento]; Papel [papel] (obrigatório na tela); Decisao [decisao]; Assunto [assunto]; Na minuta (opcional) [minuta_id]; Nota [nota]; Teor [teor]; Número pretendido (sugestão, não reserva) [numero_pretendido]; Motivo [motivo]; Teor [teor] (obrigatório na tela); Natureza (opcional) [natureza]; Selo já obtido (só se o aparelho estiver fora do ar) [selo]; Motivo [motivo] (obrigatório na tela); Selo já obtido (digitado à mão) [selo]; Arquivo [arquivo]; Tipo do título [titulo_tipo]; Número do título [titulo_numero]; Data do título [data_titulo]; Valor (em reais) [valor_centavos]; Primeiro vencimento [vencimento_inicial]; Vencimento final [vencimento_final]; Parcelas [parcelas]; Juros [juros]; Prenotação [prenotacao]; Folha [folha]; Garantia [garantia]; Condições [condicoes].
Comandos: Enviar digitalização; retirar; Acrescentar parte; Baixar a nota; Anotar; Guardar a revisão (não lavra); Lavrar esta averbação; Descartar; Trazer para as minutas; Lançar averbação; Guardar como minuta (não lavra); Cancelar o registro; Selar; Devolver à minuta; Guardar; Guardar a correção; Renumerar na ordem em que foram lavrados; Descancelar o registro.
Acessos relacionados: ← Livro 3; Conferir com a digitalização ✓; Ficha em .odt; clique na miniatura para conferir; baixar o arquivo; abrir para conferir; Como a ficha vai ficar; ata em .odt.

### Livro 3 — importar do acervo

Tela-fonte: `templates/atrib_livro3_importar.html`.
Campos da tela: Caminho do acervo (o arquivo ou a pasta que o contém) [caminho].
Comandos: Conferir o que falta; Importar os que faltam; Nada novo para importar Importar.
Acessos relacionados: ← Registros do Livro 3; Importações do RI; RCPN → Importar arquivo; Ver os registros do Livro 3; Importar registro do Livro 3 (manual); Lista do Livro 3.

### Registro novo — Livro 3

Tela-fonte: `templates/atrib_livro3_novo.html`.
Campos da tela: Natureza [natureza] (obrigatório na tela); Tipo do título [titulo_tipo]; Número do título [titulo_numero]; Data do título [data_titulo]; Valor [valor]; Parcelas [parcelas]; Juros [juros]; Primeiro vencimento [vencimento_inicial]; Último vencimento [vencimento_final]; Garantia [garantia]; Condições [condicoes]; Teor (opcional agora) [teor]; Nome [parte_nome]; Documento [parte_documento_tipo]; Número [parte_documento]; Papel [parte_papel]; Selo (opcional) [selo].
Comandos: Registrar no Livro 3.
Acessos relacionados: ← Livro 3; Cancelar.

### Título

Tela-fonte: `templates/atrib_protesto_ficha.html`.
Campos da tela: Outro endereço (opcional) [endereco]; Bairro [bairro]; CEP [cep]; Cidade [cidade]; UF [uf]; Como foi intimado [modo]; Código do edital (só na intimação por edital) [codigo_edital]; Comprovante / o que aconteceu [comprovante]; Digital [digital]; Motivo da desistência [motivo] (obrigatório na tela); Valor pago [valor_pago]; Juízo (de onde veio a ordem) [juizo] (obrigatório na tela); Processo (o número dos autos) [processo] (obrigatório na tela); Recebida em (quando o mandado chegou aqui) [recebido_em]; Observação [observacao]; Processo [processo] (obrigatório na tela); Recebida em [recebido_em]; Recebida em (quando a revogação chegou aqui) [recebido_em]; Hipótese (Lei 9.492/1997) [hipotese] (obrigatório na tela); Fundamento deste caso [fundamento] (obrigatório na tela); Selo (opcional) [selo].
Comandos: Emitir aviso; Lançar.
Acessos relacionados: ← Títulos; Trazer das atribuições; Registrar entrega e publicar edital; Abrir; Imagens dos títulos.

### Título novo — apresentado no balcão

Tela-fonte: `templates/atrib_protesto_novo.html`.
Campos da tela: Espécie [especie] (obrigatório na tela); Número do título [numero_titulo] (obrigatório na tela); Nosso número (opcional) [nosso_numero]; Emissão [data_emissao] (obrigatório na tela); Vencimento [data_vencimento] (obrigatório na tela); Valor do título [valor] (obrigatório na tela); Saldo a protestar [saldo] (obrigatório na tela); Praça de protesto [praca_protesto] (obrigatório na tela); Moeda [tipo_moeda]; Motivo do protesto [motivo_protesto]; Tipo de protesto [tipo_protesto]; Endosso [tipo_endosso]; Aceite (opcional) [aceite]; Nome [devedor_nome] (obrigatório na tela); Documento [devedor_documento_tipo]; Número [devedor_documento] (obrigatório na tela); Endereço [devedor_endereco] (obrigatório na tela); Bairro [devedor_bairro]; CEP [devedor_cep]; Cidade [devedor_cidade]; UF [devedor_uf]; Nome [cedente_nome]; Documento [cedente_documento]; CEP [cedente_cep]; Endereço [cedente_endereco]; Cidade [cedente_cidade]; UF [cedente_uf].
Comandos: Cadastrar título.
Acessos relacionados: ← Títulos; Cancelar.

### Editar informações — de

Tela-fonte: `templates/atrib_rcpn_editar.html`.
Campos da tela: Por que está corrigindo? [motivo] (obrigatório na tela); Nome [nome] (obrigatório na tela); Sexo (dados da espécie) [sexo]; Data do assento [data_ato]; Data do fato [data_fato]; Matrícula (32 dígitos, se houver) [matricula]; Livro (volume, como na capa) editável [livro_volume]; Número do termo editável [numero]; Folha (ato de registro) editável [folha]; Cor ou raça [cor_raca]; Hora do fato [hora_fato]; Local do fato (nome) [local_fato_nome]; Local do fato (endereço) [local_fato_endereco]; Naturalidade declarada [naturalidade_declarada]; Causa da morte [causa_morte]; Atestante [atestante]; Documento do atestante [atestante_documento]; Local do sepultamento [local_sepultamento]; Testamento [testamento]; Teor [teor].
Comandos: Salvar correções.
Acessos relacionados: ← Voltar à ficha; Cancelar.

### de

Tela-fonte: `templates/atrib_rcpn_ficha.html`.
Campos da tela: CPF — ( ) CPF do registrado [cpf] (obrigatório na tela); Motivo da gratuidade (opcional — padrão art. 347) [motivo_gratuidade]; O livro, como está escrito na capa [livro_volume] (obrigatório na tela); Tipo da certidão [tipo_certidao]; Modo [modo_inteiro]; Teor completo do registro (cole do livro — não se inventa) [teor_colado]; Imagem do assento (foto/scan) [imagem_assento]; Ou use um anexo já digitalizado [anexo_imagem_id]; Largura (cm) [imagem_largura_cm]; Altura (cm) opcional [imagem_altura_cm]; Margem esquerda (cm) [imagem_margem_esq_cm]; Margem superior (cm) [imagem_margem_sup_cm]; Requerente (opcional) [requerente]; Finalidade (opcional) [finalidade]; Selo (opcional) [selo]; Folha de segurança [folha_seguranca]; Ato gratuito [ato_gratuito] (obrigatório na tela); Tipo de gratuidade [gratuidade_codigo]; Motivo obrigatório se gratuito — sem ele o selo não sai [motivo_gratuidade].
Comandos: Averbar CPF — (gratuito); Confirmei no livro de papel; Ver prévia; Emitir certidão.
Acessos relacionados: ← Assentos; Alterar livro / termo / folha; Averbação Alterar ou complementar o conteúdo.; Anotação Fazer remissão a outro assento.; Retificação Corrigir erro com fundamento.; Ajustar etiqueta de averbação (mm); ODT; carga do acervo; Ver o termo; Folha (HTML); Folha PDF; Folha ODT; e mais 3 links.

### —

Tela-fonte: `templates/atrib_rcpn_lancamento_novo.html`.
Campos da tela: Teor [teor] (obrigatório na tela); Fundamento (obrigatório) (opcional) [fundamento] (obrigatório na tela); Natureza da averbação [natureza_averbacao]; Selo (opcional) [selo]; Ato gratuito [ato_gratuito]; Tipo de gratuidade [gratuidade_codigo]; Motivo (obrigatório se gratuito) [motivo_gratuidade].
Comandos: Lançar.
Acessos relacionados: ← Ficha do assento; Localizar outro assento; Cancelar.

### Novo registro —

Tela-fonte: `templates/atrib_rcpn_novo.html`.
Campos da tela: Nome ou identificação do registro [nome] (obrigatório na tela); Data do nascimento Data da celebração Data do óbito Data do fato ou ato [data_fato] (obrigatório na tela); Matrícula de 32 dígitos (opcional) [matricula]; Teor do registro (opcional agora) [teor]; Cor ou raça [cor_raca]; Hora do fato [hora_fato]; Nome do local [local_fato_nome]; Nao tem local fato [nao_tem_local_fato]; Endereço do local [local_fato_endereco]; Naturalidade declarada [naturalidade_declarada]; Natureza e causa da morte [causa_morte]; Nome de quem atestou o óbito [atestante]; CRM ou documento do atestante (se houver) [atestante_documento]; Local do sepultamento ou cremação [local_sepultamento]; Testamento conhecido (se houver) [testamento]; Onde nasceu [ibge_local]; Tipo de parto [ibge_gemeo]; DNV Declaração de Nascido Vivo [dnv]; DO Declaração de Óbito [numero_do]; Natureza do óbito [natureza_obito]; Onde ocorreu o óbito [local_obito]; Regime de bens [regime_bens]; Serventia da habilitação (só quando veio de fora) [habilitacao_serventia]; Selo da habilitação externa (opcional) [habilitacao_selo]; Selo já tirado no portal (só quando o aparelho está fora do ar) [selo].
Comandos: Conferir.
Acessos relacionados: ← Escolher outro tipo; Consultar assentos; Importar arquivo; Cancelar.

### nº

Tela-fonte: `templates/atrib_registro_ficha.html`.
Campos da tela: Requerente [requerente_nome]; Documento [requerente_documento]; Motivo da correção [motivo] (obrigatório na tela); Tipo do ato averbado [natureza_ato] (obrigatório na tela); Data da assinatura do ato [data_assinatura]; {item} [{item}] (obrigatório na tela); Anexar arquivo(s) do documento a averbar (PDF ou imagem — sobe agora e... [novo_arquivo]; Anexo id [anexo_id]; Selo digitado à mão (só se você já tem o número — sem marcar nada, o... [selo]; Tipo do ato averbado [natureza_ato]; Anexar arquivo do livro [arquivo]; Descrição [descricao].
Comandos: Gravar correção; Lançar; Prévia do teor (PDF); Anexar.
Acessos relacionados: ← Registros; Ver teor (PDF); Etiqueta; Ver; Baixar.

### Registro novo — RCPJ / RTD

Tela-fonte: `templates/atrib_registro_novo.html`.
Campos da tela: Livro [serie] (obrigatório na tela); Natureza [natureza]; Requerente [requerente_nome]; Documento do requerente [requerente_documento]; Teor (opcional agora) [teor]; Selo (opcional) [selo].
Comandos: Abrir registro.
Acessos relacionados: ← Registros; Cancelar.

### Protocolo

Tela-fonte: `templates/caixa_protocolo.html`.
Campos da tela: Prenotação [ri_protocolo_id]; Forma de pagamento do lote [forma_pagamento]; Procurar o ato [busca_ato]; Tabela [tabela]; Valor do negócio [base_calculo]; Imóveis em que esta garantia está [imoveis]; Quantidade [quantidade]; Telefone [telefone]; E-mail [email]; CPF/CNPJ [interessado_documento]; Previsão de entrega [previsao_entrega]; Documento apresentado [documento_tipo]; Nº do documento [documento_numero]; Descrição do documento [documento_descricao]; Motivo [motivo]; Como encerrar [encerramento]; Por quê [motivo].
Comandos: Recibo do atendimento; Vincular; Desvincular; Quitar os que faltam —; reabrir; quitar; remover; Procurar; Acrescentar pela faixa; Guardar; Reabrir; Encerrar.
Acessos relacionados: ← Protocolo geral; Emitir cálculo de emolumentos Emitir orçamento; acrescente os serviços; Protocolo de recepção; nº /.

### Checklist run

Tela-fonte: `templates/checklist_run.html`.
Campos da tela: Checked [checked]; Note {item} [note_{item}].
Comandos: Salvar; Concluir checklist.

### Dossiê de cumprimento - Tarefa #

Tela-fonte: `templates/dossier.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.

### Erro

Tela-fonte: `templates/error.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: Voltar ao painel.

### Expediente detail

Tela-fonte: `templates/expediente_detail.html`.
Campos da tela: Stage [stage]; Response reference [response_reference]; File [file] (obrigatório na tela); Description [description].
Comandos: Atualizar etapa; Encerrar expediente; Anexar.

### Anotar

Tela-fonte: `templates/inacabados_anotar.html`.
Campos da tela: O que falta [texto]; Quem está cuidando [responsavel]; Até quando [ate].
Comandos: Guardar a anotação; Apagar.
Acessos relacionados: abrir a tela deste ato; voltar à lista.

### Plano de ação da inspeção

Tela-fonte: `templates/inspection_detail.html`.
Campos da tela: Start date [start_date] (obrigatório na tela); Sector [sector] (obrigatório na tela); Assigned user id [assigned_user_id]; Backup user id [backup_user_id].
Comandos: Definir/recalcular data-base; Atribuir tarefas abertas do setor.

### LGPD/Governança #

Tela-fonte: `templates/lgpd_detail.html`.
Campos da tela: Tipo [item_type]; Título [title] (obrigatório na tela); Responsável [owner_user_id]; Status [status]; Próxima revisão [review_date]; Notas [notes].
Comandos: Salvar.

### Livro 3 — registro nº , como vai ficar

Tela-fonte: `templates/livro3_como_ficara.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← voltar à ficha.

### Conferir o registro nº

Tela-fonte: `templates/livro3_conferir.html`.
Campos da tela: Enviar/atualizar a varredura [arquivo]; Nota (opcional — o que você achou) [nota].
Comandos: Enviar; Tirar a marca de conferido; Marcar como conferido.
Acessos relacionados: ← voltar à ficha; o que falta conferir; baixar o arquivo.

### Login

Tela-fonte: `templates/login.html`.
Campos da tela: Usuário [username] (obrigatório na tela); Senha [password] (obrigatório na tela).
Comandos: Entrar.

### Anotações à margem pendentes

Tela-fonte: `templates/notas_anotacoes_pendentes.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Tabelionato; Atos de livro.

### Assinaturas digitalizadas

Tela-fonte: `templates/notas_assinaturas.html`.
Campos da tela: Pasta local das assinaturas [raiz] (obrigatório na tela).
Comandos: 1. Localizar as assinaturas; 2. Copiar para o nosso acervo.
Acessos relacionados: ← Tabelionato; Cartões de autógrafo.

### — termo nº nº (acervo) em lavratura (nº interno ) nº interno

Tela-fonte: `templates/notas_ato.html`.
Campos da tela: Qual procuração é esta? [especie_procuracao]; Item da tabela de emolumentos [codigo_tj]; Selo isento? [selo_isento]; Motivo da isenção [motivo_isencao]; Observacao [observacao]; Arquivos [arquivo]; Descrição (obrigatória) [descricao] (obrigatório na tela); Busca parte [busca_parte]; Qualificacao [qualificacao]; Testemunha [testemunha]; Nome [nome] (obrigatório na tela); Pessoa [tipo_pessoa]; CPF/CNPJ [documento]; Nacionalidade [nacionalidade]; Estado civil [estado_civil]; Profissão [profissao]; Qualificação no ato [qualificacao]; Endereço [endereco]; Cidade [cidade]; UF [uf]; Abrir cartao [abrir_cartao]; {item} [{item}]; Teor [teor]; Arquivo [arquivo] (obrigatório na tela); Com imovel [com_imovel]; Operação [doi_transacao]; Tipo do imóvel [doi_tipo_imovel]; Matrícula do imóvel [doi_matricula]; Área [doi_area]; Endereço ou denominação [doi_endereco]; Participacao {item} [participacao_{item}]; Páginas escritas (frente e verso contam separado) [paginas] (obrigatório na tela); Tipo [tipo] (obrigatório na tela); Data do ato que gerou [data]; Selo [selo_anotacao]; Externa [externa]; Serventia [serventia_externa]; CNS [cns_externa]; Texto [texto]; Busca anterior [busca_anterior]; e mais 9 campos.
Comandos: Guardar a anotação; Guardar arquivo; remover; Procurar ficha; Incluir; Incluir parte; Preencher o teor; Montar com as partes; Guardar o teor; Substituir o teor; Guardar; Anotar; Lançar no livro; Anotar à margem; Procurar o ato anterior; Vincular; Registrar depósito; Pedir o selo ao aparelho; Anotar o selo à mão.
Acessos relacionados: ← Atos; Termo do livro (.odt); Traslado (.odt); ver; baixar; Exportar para editar (.odt); Imprimir a face já inutilizada (.odt); livro , folha; Depósito prévio.

### Lavrar ato

Tela-fonte: `templates/notas_ato_novo.html`.
Campos da tela: Tipo do ato [tipo] (obrigatório na tela); Data [data]; Modelo de texto [modelo_codigo]; Interessado [interessado]; Natureza (quando não usar modelo) [natureza].
Comandos: Abrir o ato.
Acessos relacionados: ← Atos; Livros.

### Cartão nº —

Tela-fonte: `templates/notas_cartao.html`.
Campos da tela: firma colhida em [data_coleta]; Ficha [ficha]; Firma colhida em [data_coleta]; Favorita [favorita]; ou um JPEG [foto]; Digital [digital] (obrigatório na tela); Nome [nome] (obrigatório na tela); CPF/CNPJ [documento]; RG [rg]; Órgão [rg_orgao]; Nascimento [nascimento]; Nacionalidade [nacionalidade]; Estado civil [estado_civil]; Profissão [profissao]; Cônjuge [conjuge]; Pai [pai]; Mãe [mae]; Endereço [endereco]; Número [endereco_numero]; Bairro [bairro]; Cidade [cidade]; UF [uf]; Celular [celular]; E-mail [email]; Observação [observacao]; Motivo [motivo] (obrigatório na tela).
Comandos: Usar esta no balcão; Anotar; Retirar do cartão; Girar 90°; Desfazer corte; Recomeçar; Guardar no cartão; Colher; Recolher Colher; Guardar; Desbloquear; Bloquear.
Acessos relacionados: ← Cartões; Reconhecer firma desta pessoa; Imprimir ficha para assinar.

### Notas etiqueta

Tela-fonte: `templates/notas_etiqueta.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Imprimir.
Acessos relacionados: ← Voltar ao ato; Ajustar etiqueta; " + "Ajustar etiqueta.

### Modelos dos atos

Tela-fonte: `templates/notas_modelos_de_atos.html`.
Campos da tela: Localizar modelo [busca]; Nome [nome] (obrigatório na tela); Texto [corpo] (obrigatório na tela); Fundamento [fundamento].
Comandos: Salvar modelo do ato.
Acessos relacionados: Cabeçalhos, traslados e fichas.

### Reconhecimento nº

Tela-fonte: `templates/notas_reconhecimento_ver.html`.
Campos da tela: Número do selo colado [selo]; Motivo [motivo] (obrigatório na tela).
Comandos: Anotar selo; Cancelar o ato.
Acessos relacionados: ← Reconhecer outra; Lista; Reimprimir etiqueta Imprimir etiqueta.

### Reconhecimentos

Tela-fonte: `templates/notas_reconhecimentos.html`.
Campos da tela: Busca [busca]; Espécie [especie].
Comandos: Filtrar.
Acessos relacionados: ← Tabelionato; Reconhecer firma; Reconhecimentos feitos; Cartões de autógrafo; reimprimir imprimir etiqueta; ← anterior; próxima →.

### — o que falta, ato por ato

Tela-fonte: `templates/notas_remessa_pendencias.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Remessas.

### Sinal público nº

Tela-fonte: `templates/notas_sinal.html`.
Campos da tela: Titular [titular] (obrigatório na tela); Documento [documento]; Data da abertura [data_abertura]; Origem [origem]; Chave na central [origem_chave]; Observação [observacao]; Metadados [metadados]; Inativo [inativo]; Substituir / anexar PDF [pdf] (obrigatório na tela).
Comandos: Salvar; Guardar PDF.
Acessos relacionados: ← Sinais; Reconhecer este sinal; Abrir PDF; ver.

### Reconhecimento de sinal nº

Tela-fonte: `templates/notas_sinal_reconhecimento_ver.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Reconhecimentos; Sinal nº; PDF do sinal.

### — Livro n.

Tela-fonte: `templates/nucleo_livro.html`.
Campos da tela: Folha [rotulo] (obrigatório na tela); Motivo [motivo] (obrigatório na tela); Motivo (opcional — sai no termo) [motivo].
Comandos: Inutilizar, com termo; Encerrar o livro.
Acessos relacionados: ← Livros; Termo de abertura (.odt); Termo de encerramento (.odt).

### Conferir o endereço — matrícula

Tela-fonte: `templates/onr_endereco.html`.
Campos da tela: Logradouro [logradouro]; Número [numero_predial]; Bairro [bairro]; Cidade [cidade]; UF [uf]; CEP [cep]; Urbano ou rural [rural_urbano]; Área [area_valor]; Unidade da área [area_unidade]; Tipo do imóvel [tipo_imovel]; Motivo [motivo] (obrigatório na tela).
Comandos: Gravar na ficha; Descartar.
Acessos relacionados: Voltar à fila; A ficha do imóvel.

### Certidão n. /

Tela-fonte: `templates/protesto_certidao.html`.
Campos da tela: Por que está sendo cancelada [motivo] (obrigatório na tela); Selo cancelado tjma [selo_cancelado_tjma] (obrigatório na tela).
Comandos: Cancelar a certidão.
Acessos relacionados: ← Certidões; Imprimir (PDF); Baixar em .odt.

### Desistência recebida

Tela-fonte: `templates/protesto_desistencia.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Desistências; Títulos; baixar como chegou; Desistências; abrir.

### Conferir a desistência

Tela-fonte: `templates/protesto_desistencia_conferir.html`.
Campos da tela: Protocolo [protocolo].
Comandos: Aplicar a desistência nos marcados.
Acessos relacionados: ← Desistências; Cancelar.

### —

Tela-fonte: `templates/protesto_pendencia.html`.
Campos da tela: O que fazer [decisao]; Valor das custas (se aprovada; zero é gratuita) [vl_custas]; Motivo da recusa (se recusada — quem lê é quem pediu) [motivo_recusa]; Valor do orçamento (a CENPROT exige; é o que o solicitante vê) [vl_orcamento]; Certidão em base64 (só quando ela já estiver pronta) [arquivo_certidao]; Certidão de cancelamento em base64 (opcional, só PDF) [certidao_cancelamento_b64]; Valor da custa de cancelamento [vl_custa]; Chave única (23 dígitos) [cd_chave_unica]; Número do protocolo desta casa [nm_nr_protocolo]; Data do protocolo [dt_protocolo]; Valor da retirada [vl_retirada]; Por que esta pendência sai da lista [motivo].
Comandos: Gravar a decisão; Dispensar.
Acessos relacionados: Voltar à fila; Ficha do título; Baixar os arquivos assinados.

### Remessa recebida

Tela-fonte: `templates/protesto_remessa.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Remessas; Títulos; baixar como chegou; baixar; abrir.

### Conferir a remessa

Tela-fonte: `templates/protesto_remessa_conferir.html`.
Campos da tela: Apontar [apontar]; Marca [marca].
Comandos: Receber título(s) e gerar a confirmação.
Acessos relacionados: ← Remessas; Cancelar.

### Intimação Digital —

Tela-fonte: `templates/protesto_resolve_ficha.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Trazer o histórico; Link do comprovante (PDF); Avisar.
Acessos relacionados: ← voltar à lista.

### Certidão n. /

Tela-fonte: `templates/rc_certidao.html`.
Campos da tela: Por que está sendo cancelada [motivo] (obrigatório na tela); Selo cancelado tjma [selo_cancelado_tjma] (obrigatório na tela).
Comandos: Cancelar a certidão.
Acessos relacionados: ← Certidões; O assento; Imprimir (PDF); Baixar em .odt.

### Prévia da certidão — assento

Tela-fonte: `templates/rc_certidao_previa.html`.
Campos da tela: Teor colado [teor_colado]; Folha de segurança [folha_seguranca]; Ato gratuito [ato_gratuito]; Tipo de gratuidade [gratuidade_codigo]; Motivo (obrigatório se gratuito) [motivo_gratuidade].
Comandos: Emitir certidão.
Acessos relacionados: ← Voltar ao assento.

### Rcpj rtd etiqueta

Tela-fonte: `templates/rcpj_rtd_etiqueta.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Imprimir.
Acessos relacionados: ← Voltar ao título; Ajustar a etiqueta de registro; Ajustar a etiqueta " + "de registro.

### Rcpj rtd etiquetas selos externos imprimir

Tela-fonte: `templates/rcpj_rtd_etiquetas_selos_externos_imprimir.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Imprimir etiqueta(s).
Acessos relacionados: ← Voltar à seleção.

### Nota devolutiva

Tela-fonte: `templates/rcpj_rtd_nota.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Imprimir.
Acessos relacionados: ← Voltar ao título.

### Título n. —

Tela-fonte: `templates/rcpj_rtd_titulo.html`.
Campos da tela: Apresentante [apresentante]; CPF ou CNPJ [apresentante_documento]; Telefone [telefone]; E-mail [email]; Natureza [natureza]; Livro pretendido [serie]; Forma [forma]; Vias [vias]; Valor declarado [valor_declarado]; Observação [observacao]; Anexar arquivo do título [arquivo] (obrigatório na tela); Descrição [descricao]; Resultado [resultado] (obrigatório na tela); Exigências — obrigatórias na negativa [exigencias]; Fundamento [fundamentacao]; Prazo para cumprir [prazo_ate]; Livro [serie] (obrigatório na tela); Teor do registro [teor]; Selo (opcional) [selo]; Orçamento (R$) [valor] (obrigatório na tela); Motivo do cancelamento na Central — pelo menos dez letras [motivo] (obrigatório na tela); Sentido [sentido] (obrigatório na tela); Data [data_encaminhamento]; Protocolo da Central [protocolo_central]; Como [situacao] (obrigatório na tela); Motivo — pelo menos dez letras [motivo] (obrigatório na tela).
Comandos: Salvar os dados; Anexar; Registrar a qualificação; Prévia do teor (PDF); Lavrar o registro; Enviar a nota devolutiva à Central; Informar o registro à Central; Informar à Central; Cancelar o pedido na Central; Registrar a passagem; Encerrar.
Acessos relacionados: ← Voltar à fila; Ver o registro lavrado; Abrir em outra aba; Baixar; Ver; Imprimir a nota devolutiva; Etiqueta; Central ONRTDPJ.

### Receber título —

Tela-fonte: `templates/rcpj_rtd_titulo_novo.html`.
Campos da tela: Data (obrigatória) [data_apresentacao] (obrigatório na tela); Hora [hora]; Como veio [forma]; Vias [vias]; Nome [apresentante]; CPF ou CNPJ [apresentante_documento]; Telefone [telefone]; E-mail [email]; Natureza — o que é o documento [natureza]; Livro pretendido [serie]; Valor declarado [valor_declarado]; Observação [observacao].
Comandos: Receber e protocolar.
Acessos relacionados: Cancelar.

### Comunicação para anotação

Tela-fonte: `templates/rcpn_anotacao_oficio.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← voltar às anotações devidas.

### Certidão eletrônica na CRC

Tela-fonte: `templates/rcpn_certidao_eletronica_nova.html`.
Campos da tela: Tipo de registro [tipo_registro]; Selo [selo]; Código do selo [cod_selo]; Cota de emolumentos [cota_emolumentos]; Cota isento [cota_isento].
Comandos: Refazer a conferência; Emitir JSON (CRC); Criar na Central; Assinar na Central.
Acessos relacionados: voltar à ficha; link da assinatura; Baixar JSON; Ver o PDF.

### Rcpn certidao impressa

Tela-fonte: `templates/rcpn_certidao_impressa.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Imprimir.
Acessos relacionados: ← Voltar.

### Checklist antes de concluir

Tela-fonte: `templates/rcpn_checklist.html`.
Campos da tela: Item [item].
Comandos: Gravar o que foi conferido.
Acessos relacionados: voltar ao assento.

### Rcpn comunicacao

Tela-fonte: `templates/rcpn_comunicacao.html`.
Campos da tela: Por onde [canal]; Data [quando]; Protocolo ou comprovante [protocolo] (obrigatório na tela); Motivo [motivo] (obrigatório na tela).
Comandos: Registrar o envio; Dispensar com motivo.
Acessos relacionados: ← voltar.

### Conferência —

Tela-fonte: `templates/rcpn_conferencia.html`.
Campos da tela: Folha de segurança * [folha_seguranca] (obrigatório na tela); CPF gerado pela Receita (grava ao lavrar) [cpf_registrado].
Comandos: Voltar e editar; Imprimir rascunho; copiar; Copiar todos; Lavrar.
Acessos relacionados: Consultar assentos; Papel de segurança; Abrir a inscrição na CRC; CPF do registrado.

### Histórico de envios à CRC

Tela-fonte: `templates/rcpn_crc_historico.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← voltar para a carga da CRC.

### Rcpn etiqueta averbacao ajuste

Tela-fonte: `templates/rcpn_etiqueta_averbacao_ajuste.html`.
Campos da tela: Largura (mm) [etiqueta_largura_mm] (obrigatório na tela); Altura (mm) [etiqueta_altura_mm] (obrigatório na tela); Margem / área útil (mm) [etiqueta_margem_mm] (obrigatório na tela); Corpo da letra (pt) [etiqueta_corpo_pt] (obrigatório na tela); Deslocar na horizontal (mm) [etiqueta_deslocamento_x_mm] (obrigatório na tela); Deslocar na vertical (mm) [etiqueta_deslocamento_y_mm] (obrigatório na tela); Entrelinha [etiqueta_entrelinha] (obrigatório na tela); Tamanho do QR (mm) [etiqueta_qr_mm] (obrigatório na tela).
Comandos: Guardar as medidas.
Acessos relacionados: ← Assentos RCPN.

### Rcpn folha impressa

Tela-fonte: `templates/rcpn_folha_impressa.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.

### Ofício à FUNAI —

Tela-fonte: `templates/rcpn_funai_oficio.html`.
Campos da tela: {item} [{item}]; Por onde saiu [canal]; Protocolo [protocolo]; Motivo [motivo].
Comandos: Refazer o ofício; Já comuniquei; Dispensar, com este motivo.
Acessos relacionados: voltar à lista.

### Habilitação /

Tela-fonte: `templates/rcpn_habilitacao.html`.
Campos da tela: Qual [documento_id]; Motivo [motivo] (obrigatório na tela); Teor [teor]; Protocolo [protocolo] (obrigatório na tela); Processo [processo] (obrigatório na tela); Decisão [decisao]; Fundamento [fundamento] (obrigatório na tela); Quem opõe [quem] (obrigatório na tela); O que foi oposto [teor] (obrigatório na tela); Assento id [assento_id] (obrigatório na tela).
Comandos: Dispensar; Publicar edital; Anotar; Decidir; Registrar; Habilitar; Pedir o selo ao aparelho; Registrar a celebração; Arquivar.
Acessos relacionados: ← Habilitações; Edital de proclamas; Certidão de habilitação.

### Abrir habilitação de casamento

Tela-fonte: `templates/rcpn_habilitacao_nova.html`.
Campos da tela: Data de entrada [data_entrada]; Tipo [tipo]; Regime de bens [regime]; Nome [{item}_nome] (obrigatório na tela); Como passa a assinar [{item}_nome_pos]; Sexo [{item}_sexo]; Nascimento [{item}_nascimento]; CPF [{item}_documento]; Estado civil [{item}_estado_civil]; Profissão [{item}_profissao]; Nacionalidade [{item}_nacionalidade]; Naturalidade [{item}_naturalidade]; Endereço [{item}_endereco]; Pai [{item}_pai]; Mãe [{item}_mae]; Observação [observacao].
Comandos: Abrir habilitação.
Acessos relacionados: ← Habilitações.

### Rcpn modelo

Tela-fonte: `templates/rcpn_modelo.html`.
Campos da tela: Nome [nome] (obrigatório na tela); Corpo [corpo]; Do eoficio [do_eoficio].
Comandos: Gravar; Desativar; Ativar; Converter — não grava.
Acessos relacionados: ← Voltar aos modelos.

### Rcpn modelo documento

Tela-fonte: `templates/rcpn_modelo_documento.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Imprimir.
Acessos relacionados: ← Outros modelos; Editar o modelo.

### Pedido ·

Tela-fonte: `templates/rcpn_pedido.html`.
Campos da tela: Número do assento [assento_id]; Como se achou [motivo]; Número do assento lavrado [assento_id]; Tipo de registro [tipo_registro]; Selo [selo]; Código do selo [cod_selo]; Cota de emolumentos [cota_emolumentos]; Cota isento [cota_isento]; Qual certidão entregar [eletronica_id]; Valor dos emolumentos [valor_emolumentos]; Valor adicional [valor_adicional]; Observações da emissão [observacoes]; Quantidade de averbações/anotações [quantidade_averbacao]; Motivo [motivo].
Comandos: Amarrar este assento; Marcar como registrado; Refazer a conferência; Emitir JSON (CRC); Criar na Central; Assinar; Corrigir na Central; Cancelar; Cumprir o pedido na Central; Rejeitar na Central; Dispensar.
Acessos relacionados: Voltar à fila; O assento; link da assinatura; Baixar JSON; Ver o PDF.

### e-Proclamas — e

Tela-fonte: `templates/rcpn_proclama.html`.
Campos da tela: Publicacao [publicacao]; Livro eletronico [livro_eletronico]; CPF [cpf_fatura]; Nome [nome_fatura].
Comandos: Refazer a conferência; Enviar ao e-Proclamas.
Acessos relacionados: Voltar à fila; A habilitação; Administrativo → Configurações; e-Proclamas — a fila.

### /

Tela-fonte: `templates/rcpn_retificacao.html`.
Campos da tela: O que foi procurado [o_que_se_procurou]; O que a CRC devolveu [resultado]; Achou duplicidade [achou_duplicidade]; Achou outra [achou_outra]; Protocolo [protocolo]; Decisão [decisao]; Fundamento [fundamento]; Erro da serventia [erro_da_serventia]; Fundamento dessa marca [erro_fundamento]; Teor [teor]; Por onde [canal]; Número do ato no sistema [ato_id] (obrigatório na tela).
Comandos: O pedido está devidamente instruído; Registrar a consulta; Decidir; Já comuniquei; Amarrar.
Acessos relacionados: voltar à lista.

### Abrir processo

Tela-fonte: `templates/rcpn_retificacao_nova.html`.
Campos da tela: Instituto [instituto]; Forma [forma]; Se foi verbal, o termo — com a assinatura do declarante [termo_verbal]; Nome do requerente [requerente_nome] (obrigatório na tela); Documento [requerente_documento]; Quem assinou a petição [assinado_por]; O que se pede [o_que_se_pede] (obrigatório na tela); De que assento se trata [assento_descricao].
Comandos: Abrir o processo.

### Termo do assento nº

Tela-fonte: `templates/rcpn_termo.html`.
Campos da tela: Arquivo [arquivo] (obrigatório na tela); Descricao [descricao]; Livro [livro]; Folha [folha].
Comandos: Anexar o termo do livro; Escrever o termo no assento.
Acessos relacionados: Baixar em .odt para o livro; Voltar à ficha; Baixar em .odt sem escrever.

### Obrigação recorrente #

Tela-fonte: `templates/recurrence_detail.html`.
Campos da tela: Título [title] (obrigatório na tela); Setor [sector]; Sistema [system_name]; Frequência [frequency]; Próximo vencimento [next_due_date]; Dia preferencial [due_day]; Mês anual [due_month]; Antecedência [lead_days]; Responsável [assigned_user_id]; Substituto [backup_user_id]; Active [active]; Evidence required [evidence_required]; Notas [notes].
Comandos: Salvar.

### Matrícula — como ela vai ficar

Tela-fonte: `templates/ri_como_ficara.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Jogar o rascunho fora.
Acessos relacionados: ← A ficha; Voltar à ficha para lavrar.

### Conferir matrícula

Tela-fonte: `templates/ri_conferir.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Ficha; Próxima não conferida ( ) →; baixar; Baixe o arquivo.; Baixe para conferir.; Fichas digitalizadas; abrir sozinha.

### Editar cadastro — matrícula

Tela-fonte: `templates/ri_editar.html`.
Campos da tela: CNM [cnm]; Folha [folha]; Quem abriu esta matrícula [aberta_nome]; Logradouro / denominação [logradouro]; Número [numero_predial]; Complemento [complemento_endereco]; Bairro [bairro]; Cidade [cidade]; UF [uf]; CEP [cep]; Localização [rural_urbano]; Área [area_valor]; Unidade [area_unidade]; Descrição do perímetro [descricao_perimetro]; Confrontações [confrontacoes]; Registro anterior [registro_anterior]; CAR [car]; NIRF [nirf]; INCRA [incra]; SIGEF [sigef]; CCIR [ccir]; CMC [cmc]; Inscrição municipal [inscricao_municipal]; IPTU [iptu]; Observação [observacao]; Motivo da alteração [motivo] (obrigatório na tela).
Comandos: Salvar alterações.
Acessos relacionados: ← Ficha.

### Expurgar

Tela-fonte: `templates/ri_expurgo.html`.
Campos da tela: Fundamento (mínimo quinze letras — é a única explicação que vai restar... [motivo] (obrigatório na tela); Selo cancelado no Tribunal [selo_cancelado]; Escreva EXPURGAR para confirmar [confirmacao] (obrigatório na tela).
Comandos: Expurgar e lavrar a ata.
Acessos relacionados: ← Voltar à ficha; Atas de ocorrência.

### Matrícula -

Tela-fonte: `templates/ri_ficha.html`.
Campos da tela: O que você conferiu e decidiu [decisao] (obrigatório na tela); Assunto [assunto] (obrigatório na tela); O que precisa ser conferido [nota] (obrigatório na tela); De qual ato (deixe em branco se for da matrícula inteira) [ato_id]; Por que não vai virar ato [motivo] (obrigatório na tela); Tipo de ato [tipo] (obrigatório na tela); Número pretendido [numero]; Data [data_ato]; Natureza [natureza_titulo]; Protocolo [protocolo]; Teor [teor] (obrigatório na tela); Prenotação (Livro 1 — prioridade) [prenotacao_id_ui]; Número da prenotação no ato [protocolo]; Observação / data da prenotação (campo do ato) [prenotacao]; Protocolo de caixa (override — se a prenotação já trouxe um ligado,... [protocolo_id]; Número do ato [numero] (obrigatório na tela); Data do ato [data_ato]; Natureza do título — o selo exige [natureza_titulo]; Protocolo item id [protocolo_item_id]; Codigo tj item [codigo_tj_item]; Outro código (fora da lista) [codigo_tj]; Valor declarado (base de cálculo) [base_calculo]; Emolumentos [emolumentos]; Isento [isento]; Motivo da gratuidade [motivo_isencao]; Encerra [encerra]; Motivo do encerramento [encerra_motivo]; Matrícula(s) de destino [encerra_destino]; Por que está sendo reaberta [motivo] (obrigatório na tela); Motivo do encerramento [motivo] (obrigatório na tela); Data [data_encerramento]; Matrícula(s) de destino [destino]; Arquivo da varredura [arquivo] (obrigatório na tela); Tipo [tipo] (obrigatório na tela); Corpo da certidão de inteiro teor [fonte_corpo]; Folhas da certidão [folhas]; Requerente [requerente] (obrigatório na tela); CPF/CNPJ do requerente [requerente_documento]; Finalidade [finalidade]; Número novo [novo_numero] (obrigatório na tela); e mais 18 campos.
Comandos: Baixar a nota; Anotar; Marcar como conferida; Descartar minuta; Guardar na fila de revisão; Acrescentar parte; Lavrar ato; Guardar a revisão sem lavrar; Reabrir; Voltar a encerrar; Encerrar matrícula; Enviar digitalização; Emitir certidão; Renumerar; gravar; o que o teor diz; Pedir o selo ao aparelho; Corrigir; Guardar rascunho; Jogar fora; Cancelar o ato por averbação; Selar -; uma página acima; uma página abaixo; ir; renomear; tirar da ficha.
Acessos relacionados: Selar agora; Informar quem abriu; ← Todas as matrículas; + Lavrar registro ou averbação; Lavrar a partir de modelo; Imprimir ficha (PDF); .odt; Conferir com a digitalização; Editar cadastro; Revisar e lavrar; baixar; Ver como a matrícula fica; e mais 8 links.

### Páginas que faltam nas fichas

Tela-fonte: `templates/ri_fichas_do_disco.html`.
Campos da tela: Matricula id [matricula_id]; Quantas de uma vez (vazio ou 0 traz todas) [limite].
Comandos: Ligar a esta; Trazer página(s).
Acessos relacionados: ← Fichas digitalizadas.

### Importação manual —

Tela-fonte: `templates/ri_importacao_manual.html`.
Campos da tela: Campo {item} [campo_{item}]; valor (R$) — formato brasileiro, ex.: 23.999,99 [campo_valor_reais].
Comandos: Conferir; Importar.
Acessos relacionados: ← Importações do RI; Matrícula; Registro do Livro 3.

### Importações do acervo

Tela-fonte: `templates/ri_importacoes.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Completar o tipo do imóvel.
Acessos relacionados: ← Registro de Imóveis; Carregar acervo; Livro 3 — importar do acervo; Matrículas em Word; Importar matrícula (manual); Importar registro do Livro 3 (manual).

### Carregar acervo do E-Ofício

Tela-fonte: `templates/ri_importar.html`.
Campos da tela: Pasta com os arquivos exportados [pasta] (obrigatório na tela); Substituir [substituir] (obrigatório na tela).
Comandos: usar esta; Carregar acervo.
Acessos relacionados: ← Importações.

### Nota devolutiva — protocolo

Tela-fonte: `templates/ri_nota.html`.
Campos da tela: Data do reingresso [data_reingresso]; Observação [observacao]; Data [data_nota]; Exigências — uma por linha [exigencias] (obrigatório na tela); Fundamentação [fundamentacao].
Comandos: Registrar reingresso do título; Emitir nota devolutiva.
Acessos relacionados: ← Livro de Protocolo; Imprimir nota (PDF); .odt.

### Abrir matrícula

Tela-fonte: `templates/ri_nova.html`.
Campos da tela: Folha (só para ficha do acervo) [folha]; Data de abertura [data_abertura]; Localização [rural_urbano]; Logradouro / denominação [logradouro]; Número [numero_predial]; Bairro [bairro]; Cidade [cidade]; UF [uf]; CEP [cep]; Área [area_valor]; Unidade [area_unidade]; Descrição do perímetro [descricao_perimetro]; Registro anterior [registro_anterior]; Teor de abertura [teor].
Comandos: Abrir matrícula.
Acessos relacionados: ← Registro de Imóveis.

### Edital na Central — usucapião /

Tela-fonte: `templates/ri_onr_edital.html`.
Campos da tela: Tipo de edital (código do ONR) [tipo_edital]; Texto do edital [texto]; Motivo [motivo].
Comandos: Refazer a conferência; Trazer os tipos da Central; Disponibilizar na Central; Cancelar na Central.
Acessos relacionados: Voltar ao ONR; O processo.

### Indicador real — matrícula

Tela-fonte: `templates/ri_onr_indicador.html`.
Campos da tela: Situação da construção [situacao_construcao]; Tipo do imóvel [tipo_imovel].
Comandos: o que o teor diz; Refazer a conferência; Enviar o indicador real.
Acessos relacionados: Voltar ao ONR; A ficha do imóvel.

### — matrícula

Tela-fonte: `templates/ri_preencher.html`.
Campos da tela: C {item} [c_{item}]; (escolha) [c_{item}]; (só se a cláusula entrar) [c_{item}]; Confirmar pendencias [confirmar_pendencias]; Teor [teor].
Comandos: Preencher em abas; Preencher no documento; Atualizar prévia; Enviar para a lavratura; Lavrar -.
Acessos relacionados: ← Ficha.

### Título Livro — Protocolo

Tela-fonte: `templates/ri_protocolo_ver.html`.
Campos da tela: Arquivos [documento]; O que é [descricao]; Por que está reabrindo [motivo] (obrigatório na tela); Valor (R$) [valor] (obrigatório na tela); Forma de pagamento [forma_pagamento]; Depositante [depositante]; CPF/CNPJ do depositante [depositante_documento]; Observação [observacao]; {item} [{item}].
Comandos: Anexar; Reabrir o protocolo; Registrar depósito; Guardar correção.
Acessos relacionados: ← Protocolo; Comprovante de prenotação; Abrir a matrícula; Abrir; Depósito prévio.

### Retificação nº

Tela-fonte: `templates/ri_retificacao.html`.
Campos da tela: Data do requerimento [quando]; Protocolo que o SIGEF devolveu [protocolo] (obrigatório na tela); Tipo [tipo]; Arquivo digitalizado [documento]; Caminho já existente, se não houver upload [arquivo]; Descrição [descricao]; Entregue em [entregue_em]; Situacao [situacao]; Nota [nota]; Forma [forma]; Quando [quando] (obrigatório na tela); Prazo ate [prazo_ate] (obrigatório na tela); Resposta [resposta]; Impugnacao [impugnacao]; Nome [nome] (obrigatório na tela); Papel [papel]; Documento [documento]; Endereço [endereco]; Matrícula contígua [matricula_contigua]; Serventia [serventia_contigua]; Divisa afetada [divisa_afetada]; Assinou planta [assinou_planta]; Carta anuencia [carta_anuencia]; Nº do ato (id) [ato_id] (obrigatório na tela); Nº da matrícula nova (id) [matricula_nova_id]; Sentido [sentido]; Fundamento [fundamento] (obrigatório na tela).
Comandos: Registrar; Juntar documento; marcar; notificar; responder; Anotar; Amarrar ao processo; Decidir.
Acessos relacionados: ver; baixar; imprimir em PDF; .odt; ← voltar; o que o Código de Normas exige.

### O que o Código de Normas do TJMA exige

Tela-fonte: `templates/ri_retificacao_normas.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← voltar.

### Novo processo de retificação de área

Tela-fonte: `templates/ri_retificacao_nova.html`.
Campos da tela: Número do processo [numero] (obrigatório na tela); Matrícula a retificar [matricula_id] (obrigatório na tela); Espécie [especie] (obrigatório na tela); Fundamento [fundamento] (obrigatório na tela); Rural [rural]; Nome [requerente_nome]; CPF ou CNPJ [requerente_documento]; Nome [profissional_nome]; Conselho [profissional_conselho]; Registro [profissional_registro]; ART, RRT ou TRT [art_numero]; Como está na matrícula [area_na_matricula]; Como fica [area_pretendida]; Nº da certificação do INCRA [certificacao_incra]; Código no SIGEF [sigef_codigo].
Comandos: Autuar o processo.
Acessos relacionados: Cancelar.

### Configuração de API dos robôs

Tela-fonte: `templates/robos_config.html`.
Campos da tela: provedor padrão [provedor_padrao]; api_key_grok (xAI) [api_key_grok]; api_key_gpt (OpenAI) [api_key_gpt]; api_key_claude (Anthropic) [api_key_claude]; api_key_deepseek [api_key_deepseek].
Comandos: guardar.
Acessos relacionados: ← robôs.

### Novo robô

Tela-fonte: `templates/robos_form.html`.
Campos da tela: nome [nome] (obrigatório na tela); ato (texto curto) [ato] (obrigatório na tela); provedor [provedor]; prompt [prompt]; Ativo [ativo]; entrada [entrada] (obrigatório na tela); saída esperada [saida_esperada] (obrigatório na tela); peso [peso]; pedido [pedido] (obrigatório na tela).
Comandos: guardar; apagar; adicionar exemplo; testar.
Acessos relacionados: ← robôs.

### Configuração inicial

Tela-fonte: `templates/setup.html`.
Campos da tela: Nome completo [full_name] (obrigatório na tela); Usuário [username] (obrigatório na tela); Senha [password] (obrigatório na tela); Confirmar senha [confirm] (obrigatório na tela).
Comandos: Criar administrador e iniciar.

### Tarefa #

Tela-fonte: `templates/task_detail.html`.
Campos da tela: Motivo [motivo] (obrigatório na tela); Passar para [para_user_id]; Título [title] (obrigatório na tela); Setor [sector]; Sistema/tema [system_name]; Prioridade [priority]; Status [status]; Data-base [start_date]; Prazo em dias [due_days]; Vencimento [due_date]; Responsável [assigned_user_id]; Substituto [backup_user_id]; Referência normativa [legal_ref]; Descrição [description]; Evidence required [evidence_required]; File [file] (obrigatório na tela); Description [description]; Note [note] (obrigatório na tela).
Comandos: Concluir tarefa; Reabrir tarefa; Passar; Para o substituto ( ); Devolver a quem criou ( ); Salvar alterações; Anexar evidência; Registrar.
Acessos relacionados: Gerar dossiê.

### Relatório para qualificação — usucapião

Tela-fonte: `templates/usucapiao_dossie.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.
Acessos relacionados: ← Os autos; Baixar (.md); Gerar sem mascarar; Gerar mascarado.

### Usucapião

Tela-fonte: `templates/usucapiao_ficha.html`.
Campos da tela: Mudar para [etapa]; Estado [estado]; Motivo [motivo]; Tipo [tipo]; Descrição [descricao]; Arquivo digitalizado (PDF, imagem ou documento que ficará no arquivo do... [documento]; Nome avulso (se não houver upload) [nome_arquivo]; Caminho já existente (se o arquivo já estiver em disco) [caminho]; Teor em texto (é o que vai no relatório — o PDF se lê pior) [teor]; Resposta [resposta]; Resposta teor [resposta_teor]; Sem origem [sem_origem]; Disponibilizado na Central em [disponibilizado_em]; Quem se notifica [destinatario] (obrigatório na tela); Na qualidade de [destinatario_papel] (obrigatório na tela); Endereço para onde o papel vai [endereco] (obrigatório na tela); Por qual forma [forma]; Prazo de quem [prazo_chave]; Que tentativa é esta [tentativa]; Movimento [tipo]; Destinatário [destinatario]; Papel [destinatario_papel]; Prazo em dias [prazo_dias]; Prazo começa [prazo_inicio]; Prazo vence [prazo_fim]; Descrição [descricao] (obrigatório na tela); De quem veio [ferramenta]; SHA-256 do dossiê [dossie_sha256]; Parecer recebido [parecer] (obrigatório na tela); Achados em JSON (opcional) [achados_json]; Sentido [sentido]; Apoiada na análise (opcional) [analise_id]; Fundamento [fundamento] (obrigatório na tela); Teor [teor] (obrigatório na tela); Ato do RI [ato_id] (obrigatório na tela); Selo [selo].
Comandos: Mudar etapa; Gravar; Juntar; Montar o edital; Montar os três ofícios; Expedir e montar o papel; Lançar movimento; Conferi esta análise; Juntar a análise; Lavrar decisão; Registrar e encerrar.
Acessos relacionados: ← Processos; Relatório para qualificação; ver; baixar; Imprimir em PDF; ver na tela; como efetuar.

### Como efetuar a notificação

Tela-fonte: `templates/usucapiao_manual.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: nenhum botão local nomeado.

### Notificação expedida

Tela-fonte: `templates/usucapiao_notificacao.html`.
Campos da tela: nenhum campo de formulário nomeado nesta tela.
Comandos: Imprimir pela tela.
Acessos relacionados: ← voltar ao processo; como efetuar; Imprimir em PDF; Baixar em .odt.

### Configuração Meta

Tela-fonte: `templates/whatsapp_config.html`.
Campos da tela: verify_token [verify_token]; phone_number_id [phone_number_id]; access_token [access_token]; app_secret (opcional — HMAC do webhook) [app_secret]; caixa_url [caixa_url]; caixa_segredo [caixa_segredo].
Comandos: guardar.
Acessos relacionados: ← fila do WhatsApp.

### Whatsapp conversa

Tela-fonte: `templates/whatsapp_conversa.html`.
Campos da tela: Rascunho [rascunho].
Comandos: guardar rascunho; Enviar no WhatsApp; marcar resolvida.
Acessos relacionados: ← fila do WhatsApp; configuração.
