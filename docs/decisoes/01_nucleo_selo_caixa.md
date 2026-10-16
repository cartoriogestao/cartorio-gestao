# Núcleo: livros, numeração, custas, selo, caixa e assinatura

Decisões do núcleo comum às seis atribuições: escrituração e numeração dos livros, custas e gratuidades, selo eletrônico e cliente do selador, carimbo, QR e etiqueta, protocolo geral com caixa e assinatura digital A3. As regras de transação e banco que as sustentam estão em `08_arquitetura_e_metodo.md`.

## Livros e escrituração

### A regra do livro mora no núcleo, uma vez só; cada série apenas declara a sua geometria
**Regra.** Termos de abertura e encerramento, inutilização, assinatura ao final do ato, rubrica, encerramento diário do protocolo e continuidade da numeração são implementados uma vez no núcleo. Cada série declara só o que varia: folhas por livro, registros por folha, uso do verso, registro em folha nova, páginas pares, transbordo do fim do livro, termo contínuo, livro diário. Combinações contraditórias (páginas pares sem verso; vários por folha com "folha nova") são recusadas na declaração. As exigências da correição de cada série ficam gravadas como dado, com teste que confere que nenhuma se perdeu.
**Por quê.** A correição cobra as mesmas coisas de todas as atribuições; quatro implementações viram quatro versões divergentes do código mais difícil do sistema.
**No código.** `livro_nucleo.py`, `nucleo_schema.py`, `escrituracao.py`, `atribuicoes.py`.

### O ato só recebe livro, folha e número no lançamento, e lançado não se relança
**Regra.** O ato nasce "em lavratura", sem livro, folha nem número, e não vai a nenhuma Central. No lançamento recebe tudo de uma vez, dentro da transação, com a contagem de páginas confirmada por quem imprimiu. Depois de lançado a folha está gasta, mesmo que o ato seja cancelado: erro se anota à margem, não se renumera. Gravar o teor nunca toca na folha.
**Por quê.** Folha reservada para ato que não se lavrou é buraco no livro. Um `UPDATE` que gravava teor e folha juntos apagava a folha quando o campo vinha vazio.
**No código.** `escrituracao.py`; nas Notas, `notas_livro.py`.

### Ato não se divide entre livros; livro cheio encerra e o seguinte abre com termo
**Regra.** Se o ato não cabe no que resta, o livro é encerrado declarando as folhas restantes como inutilizadas e o ato inteiro vai para o livro seguinte, aberto automaticamente. Os termos são obrigatórios e, em branco, o sistema os redige: número do livro, folhas por extenso e em algarismos, serventia e responsável; o de encerramento diz até que folha se usou, quais números se lavraram e quais folhas ficam inutilizadas. O painel avisa quando o livro chega às últimas folhas.
**Fundamento.** Art. 795, § 4º, do Código de Normas (norma estadual — TJMA; confira o Código de Normas do seu estado).

### Inutilizar não é cancelar, e a sobra é apontada, não inutilizada pelo sistema
**Regra.** Só face em branco se inutiliza; folha escriturada não — o ato nela é que se cancela — e o sistema recusa confundir. A inutilização exige motivo escrito (mínimo de dez letras), porque sai impresso no termo. O verso que sobra é apontado e o sistema oferece imprimir a face já inutilizada (traço, dizer com fundamento, linha de assinatura), mas não inutiliza sozinho. Para fechar paridade, no máximo sugere entrelinha dentro de banda autorizada; não altera fonte nem aplica ajuste automático.
**Por quê.** Espaço em branco é por onde se acrescenta o que ninguém declarou. Encolher a letra só muda o branco de lugar, e a contagem de páginas é estimada (quem decide a quebra é o editor ao imprimir).
**Fundamento.** Art. 795, § 2º, do Código de Normas — escrituração sem claros (norma estadual — TJMA; confira o Código de Normas do seu estado).
**No código.** `escrituracao.py`, `notas_inutilizacao.sugerir_entrelinha`.

### Protocolo diário encerra todo dia, inclusive sem movimento
**Regra.** Livros de protocolo diários (Protesto, RCPJ, RTD) encerram por dia, com a faixa de números do dia; dia parado gera termo de "não houve movimento". Há consulta de dias sem encerramento.
**Por quê.** Sem termo, dia parado não se distingue de dia não escriturado; a correição pede prova de que não ficou dia aberto.
**No código.** `escrituracao.py` (`dias_sem_encerrar`).

### Acervo migrado não é tocado; ato novo entra após a última folha ocupada
**Regra.** Atos trazidos de outro sistema mantêm livro, folha e número, não são renumerados nem lançados. Atos novos entram depois da última folha ocupada daquele livro. Os índices únicos são parciais (`IS NOT NULL`), deixando o acervo de fora. Folhas repetidas no acervo recebem complemento (A, B, C…) por série, de forma idempotente, ficando o primeiro sem complemento.
**Por quê.** Índice total não se criaria sobre acervo com repetições, e há Central que identifica o ato por livro, folha e seus complementos e recusa dois iguais sem desempate.
**No código.** `notas_censec.py`.

### Ato sem base sai por expurgo com ata, sob cinco travas, e não por cancelamento
**Regra.** O ato vai para uma ata de ocorrência com teor íntegro, selos, fundamento e quem ordenou. Só se expurga ato lançado no sistema (não de acervo), o último da ficha, não cancelado nem cancelador, não citado por certidão viva nem contido em declaração já entregue a órgão externo.
**Por quê.** Cancelar por averbação registraria para sempre um ato que não houve. Os atos são encadeados por hash: tirar um do meio quebra a conferência dos seguintes.
**No código.** `ri_expurgo.py`.

## Numeração

### A numeração é contínua por série e por serventia, e a regra está no banco
**Regra.** O número de ordem é contínuo por série, não por volume: livro novo volta a folha a 1, não o número. Volumes de um mesmo livro (Livro 2, 2-A, 2-B…) compartilham a série; série distinta (Livro 3) conta à parte. O banco impõe `UNIQUE(livro_id, folha, verso, ordem)` e índice único parcial de um lugar de início por ato.
**Por quê.** Contar por volume fez nascer número já usado em outro volume; nenhuma revisão de código pegou, o banco pegaria. O teste de corrida usa conexões reais distintas.
**No código.** `nucleo_schema.py`, `escrituracao.py`, `ri_correcoes.py`.

### O contador é explícito, com autor e motivo — nunca `MAX()+1`
**Regra.** O próximo número vem de contador por série, gravado com quem fixou, quando e por quê. Pode ser corrigido com motivo, mas o sistema recusa fixar número igual ou menor que o maior já usado. A numeração consulta os atos gravados e o contador e nunca anda para trás. Consultar o próximo número não abre transação de escrita.
**Por quê.** `MAX()+1` filtrado pelo ano corrente repetia número ao lavrar ato datado de outro ano. GET com transação de escrita fica preso no `busy_timeout` enquanto outro balcão lavra.
**No código.** `nu_numeracao`, `ri_numeracao`, `nt_termos`.

### A carga do acervo termina semeando os contadores, sem nunca baixar e sem `max()` calado
**Regra.** A carga não pede lugar ao núcleo (o ato antigo já tem lugar), mas termina obrigatoriamente semeando cada contador à frente do maior número trazido, sem nunca baixar um contador mais adiantado. A série de cada ato importado sai da chave estruturada (matrícula), e divergência com a letra do livro vira aviso. Divergência entre duas fontes do mesmo contador vira pendência com os dois números. Séries sem fonte no acervo ficam pendentes, com motivo, e o oficial informa o próximo número antes do primeiro ato.
**Por quê.** Contador vazio sobre acervo faz o primeiro ato novo sair com número 1 — certo em banco vazio, e por isso só o ensaio sobre dado real pega o defeito. Uma letra errada semearia o contador de um livro com número de outro; um `max()` calado pode abrir um salto de centenas de números num livro.
**No código.** `acervo_carga.semear_numeracao()`, no fim de `carregar_tudo`.

## Custas e gratuidade

### O valor sai da tabela vigente na data do ato, e o desvio é declarado
**Regra.** Cada vigência tem início e fim; o cálculo usa a que contém a data do ato. Sem correspondência, usa a corrente e avisa. O total é emolumento mais os fundos de repasse; o ISS é fundo conhecido com `no_total=False`. Divergência de fundo é relatada, nunca corrigida; arredondamentos da própria tabela ficam numa lista declarada. Siglas variantes do mesmo fundo são aceitas como sinônimos.
**Por quê.** Relavrar ou reimprimir pela tabela de outro ano é cobrança indevida. O ISS é imposto municipal do delegatário, não repasse cobrado da parte. Corrigir fundo por conta própria seria inventar preço.
**No código.** `custas.py` (`DIVERGENCIAS_CONHECIDAS`).

### Gratuidade vem da tabela ou de quem pede, exige motivo, e guarda o valor que teria
**Regra.** Isenções por ato são as que a tabela declara no texto (nascimento e óbito com primeira certidão, Reurb-S, ato refeito por erro da serventia, entre outras). Isenções por pessoa (hipossuficiência, assistência judiciária) exigem motivo escrito e indicam o que arquivar; sem isso o lançamento é recusado. Ato gratuito devolve total zero e o valor que teria, e o selo é emitido igualmente.
**Por quê.** O valor compensável vai em coluna própria; somar junto leva a pedir compensação de ato pago. Ato refeito por erro do serviço não se cobra de novo.
**Fundamento.** Lei 9.534/1997; Lei 13.465/2017; vedação de cobrança por ato refeito por erro do serviço, item 14.10.1 da tabela (norma estadual — TJMA; confira a tabela do seu estado).
**No código.** `custas.py`.

## Selo eletrônico e cliente do selador

### O sistema guarda o que o selador devolve, e o papel imprime só o que o selo declara
**Regra.** A resposta do selador traz código, total, repartição por fundo, texto pronto e valor do QR; o sistema grava e imprime isso, sem recompor. Gratuidade (com motivo) e papel de segurança usado (código e fornecedor) vão no próprio pedido. O carimbo traz número do selo, ato, data e hora da emissão, requerente, valores, QR e link; campo não declarado não sai, e sem valores no razão sai só o número. Marcas do selo ("Selo Isento", "Diferido") andam na mesma linha dos valores. Todo papel selado leva carimbo. Moldes com marcador por linha pedem cada linha pelo nome, nunca por índice; o leitor do texto aceita as formas antigas do link.
**Por quê.** O texto devolvido é a declaração oficial: remontar a conta imprime valor que o selo não declara, e selo isento vem com emolumentos escritos — sem a marca, o papel afirma que se cobrou. Selo comprado que não sai no papel faz a certidão dizer menos que o selo. Depender da ordem de lista de outro módulo troca campos em silêncio.
**No código.** `selo.py`, `selador.py`, `selo.ler_texto`, `selo_no_papel.py`, `ri_odt.carimbo_da_certidao_odf`.

### A ordem é custas → selo → vínculo, e toda tabela que sela está no cadastro de tabelas de ato
**Regra.** Primeiro a conta local (barata, falha por regra), depois a compra do selo, por último o vínculo ao ato já existente. O vínculo consulta o mapa medido da coluna onde cada tabela guarda o selo. Um varredor lê o código das telas, junta toda tabela em que alguma manda selar ou cobrar e exige que esteja no cadastro, com piso mínimo de achados.
**Por quê.** Selo comprado não se devolve, e defeito no vínculo acontece depois do pagamento: produz selo órfão ou devolve HTTP 500 a quem já pagou. Tabela fora do cadastro não dá erro de programação, dá ato perdido: a rota trata o selo como recusado, desfaz a transação, e o documento recém-emitido some.
**No código.** `ato_selado.COLUNA_DO_SELO`, `ato_selado.TABELAS_DE_ATO`.

### O selo automático vem depois do lançamento, e a recusa dele não desfaz o ato
**Regra.** O envelope leva livro, folha e número, que só existem depois do lançamento. A função de selar nunca estoura: devolve `{"selado": False, "motivo": ...}`, a tela diz que o ato foi lavrado sem selo, e ele entra na lista de atos sem selo, com botão de selar depois (também em ficha encerrada, pois o selo não entra no hash do ato). A qualificação digitada para o selo é gravada antes da rede. O que falta preencher deixa o ato lavrado, com aviso. O selo digitado à mão é conferido dentro da transação do ato, passa pelo razão e, recusado, derruba o lançamento inteiro.
**Por quê.** Balcão parado é pior que selo atrasado, e ato com selo inventado é pior que os dois. Ato válido não se cancela por pendência de cadastro, e mensagem de tela nunca diz "suspenso" sobre ato apagado.
**No código.** `ato_selado.py` (`selar_o_ato_lavrado`, `registrar_selo_obtido_a_mao`, `obter_selo`).

### Pedido com SID determinístico e razão gravado na chegada: repetir não compra outro selo
**Regra.** O SID é SHA-256 do CNS, da atribuição e da referência do ato — nunca da hora —, e o mesmo ato devolve o mesmo selo; se o razão local já o tem, o pedido nem sai. Ato com unidades (cada firma, cada folha autenticada) pede um selo por unidade, cada uma com referência própria. Todo selo entra no razão ao chegar, antes de o ato terminar. Falha de rede repete; recusa do selador não. Cancelar selo exige motivo escrito.
**Por quê.** Repetir após erro de rede sem identificador gera selo novo, cobrado, e deixa o anterior órfão — padrão medido em acervo antigo, com selos órfãos sem tela onde olhar e cancelamentos sem motivo. Uma referência para três unidades traria o mesmo selo três vezes.
**No código.** `selador.py`, tabela `sd_selos`.

### O razão é a fonte do selo: chave tabela + ato, pesquisável, com o obtido e não usado à vista
**Regra.** O selo de um ato se busca pela tabela de origem mais o id do ato; quando a carga deixou a tabela nula, vale o número do selo gravado no ato. O razão se pesquisa por período, atribuição/caminho e quem obteve, com totais que acompanham o filtro, e tem a vista dos selos sem ato (dinheiro pago sem ato).
**Por quê.** Por `ato_id` sozinho vêm selos de outra atribuição. Total geral embaixo de um filtro induz conclusão errada; selo órfão sem tela não é conferido por ninguém.
**No código.** `ato_selado.etiqueta_do_ato`.

### O contrato vem da documentação oficial, e a procedência de cada código fica marcada
**Regra.** Endpoints e schemas, campo a campo, saem da documentação oficial; caminhos e campos usados na prática e ausentes dela ficam numa lista separada. Pedido por tipo de ato em `/selo/{atribuição}/{ato}`, com a versão da tabela de custas no formato `TTAAAAMMDD`. O código do ato no envelope é medido (a serventia já mandou assim e foi aceito) ou lido da tabela de emolumentos; sem nenhum dos dois, o ato sai sem selo e a tela diz por quê. Correlação forte entre espécie e item de custa não vira dedução: o item é marcado por quem atende. O tipo de selo é resolvido pelo cadastro intermediário, com teste que exige que todo ato resolva; código com dois donos é conflito a perguntar à Corregedoria. Campo de provimento de outro estado presente no schema é recusado com valor verdadeiro.
**Por quê.** Misturar medição e documentação apaga a procedência das duas. Correlação parece regra até se contarem as exceções. Ler código de cadastro como tipo devolve "não encontrado" sem erro, e o ato sai sem tipo de selo. Enviar o campo alheio seria conceder desconto sem base legal.
**Fundamento.** Provimento 279 da CGJ do Amazonas, não aplicável no TJMA (particularidade do selador do fornecedor usado no TJMA; confira o do seu estado).
**No código.** `selador.ENDPOINTS`, `selador.ALEM_DA_DOCUMENTACAO`, `atribuicoes.py` (`CONFLITOS_NO_ACERVO`).

### Endereço do selador é configuração da serventia, e o certificado é fixado
**Regra.** Base e autenticação são configuradas por serventia; homologação fica nula até ser informada, nunca adivinhada. Na primeira conexão o sistema exibe a impressão digital do certificado; confirmada, só ele é aceito, e sem ela o sistema recusa conectar. O token fica só em memória, com folga de validade e reautenticação automática. Prazo curto por chamada (20 s), com mensagem de balcão; botão "testar a conexão" confere rede, certificado e credencial sem selar. O transporte é testado contra selador falso local com TLS real, que devolve o mesmo selo para o mesmo SID, recusa com 400 e devolve 401 uma vez.
**Por quê.** Há serventias que selam por aparelho na rede local e outras pela nuvem: apontar errado manda a senha para fora, trava ou sela em duplicidade; homologação chutada pode gerar selo real. Desligar a validação do certificado do aparelho deixa qualquer máquina da rede receber a senha. Token em disco é senha em disco. Mock não exercita TLS, impressão digital, token vencido nem prazo esgotado.
**Fundamento.** Arranjo do selador do TJMA, aparelho local ou serviço do fornecedor (confira o do seu estado).
**No código.** `selador.py`, `tests/selador_falso.py`.

## Carimbo, etiqueta e QR

### Um só gerador de QR; o QR é um link para a consulta do selo, provado decodificando
**Regra.** Todos os papéis geram o QR pelo mesmo módulo, a partir de modelo de endereço configurável com `{selo}`, apontando para a consulta daquele selo — nunca token cru. A configuração gravada ganha do padrão; a ferramenta que a atualiza só troca o valor se ele for exatamente a forma antiga. O teste desenha o QR no tamanho físico e o decodifica a 203 e 300 DPI, exigindo o endereço esperado. O número do selo sai sempre legível ao lado; sem selo, não há QR; sem a biblioteca de QR, sai só o número.
**Por quê.** O conteúdo do QR de papel assinado não pode ter várias versões; token cru é lido pela câmera e não abre nada. QR que câmera não lê é pior que nenhum; QR para consulta vazia parece conferível e não é.
**Fundamento.** No portal do TJMA a consulta abre em `#/resumo/<selo>`; `?selo=` fora do hash é descartado (particularidade do portal do TJMA; confira o do seu estado).
**No código.** `notas_selo.MODELO_PADRAO`, `notas_selo.marca_do_selo`, `ri_odt.png_do_qr_do_selo`, `tests/test_qr_do_selo.py`.

### Etiqueta térmica é HTML com tamanho de página, e não corta, não mente, não repete
**Regra.** A etiqueta é página com `@page` no tamanho exato, QR em SVG, medidas e deslocamento ajustáveis por tela, página de teste com régua, escala de impressão em 100%. Teor completo com fecho, sem duplicar o de atos importados. Recusa ato cancelado, avisa quando falta selo e, se o teor não couber, diz quanto falta e não abre a impressão. Cada impressão é contada e auditada.
**Por quê.** ESC/POS ou ZPL exigem programa por máquina e variam por fabricante. Cortar teor de ato notarial em silêncio é o pior defeito; etiqueta de ato cancelado colada é o ato valendo no mundo.
**No código.** `notas_selo.py`, `notas_web.py`.

## Protocolo, caixa e depósito prévio

### Protocolo geral e caixa são um trilho só; o protocolo do RI fica separado e atrelado
**Regra.** Serviços entram no protocolo geral com valor da tabela vigente; quitar o item gera um lançamento por item, com fundos e selo, e o valor não é recalculado na quitação. Cobrar pela ficha do ato é exceção para ato sem protocolo. O protocolo do RI fica separado, com os atributos da prenotação, ligado ao geral.
**Por quê.** Dois caminhos para o mesmo dinheiro divergem. Lançamento único impede a conferência dos fundos; recalcular cobra preço diferente do informado se a tabela mudar no meio.
**No código.** `cx_lancamentos` com `UNIQUE(origem, origem_chave)`; `cx_protocolos.ri_protocolo_id`.

### Dinheiro sai por estorno, o recibo cobre só o que entrou, e quem fecha o caixa não o confere
**Regra.** Desquitar não apaga lançamento: a tela indica qual estornar. O recibo cobre o atendimento inteiro, só itens quitados, marca os lançamentos que somou e usa a forma única da casa (numeração por exercício, teor congelado e hash). Quem atende fecha o próprio caixa; a conferência é outro ato, gravado com quem conferiu, e o sistema recusa conferir o próprio caixa.
**Por quê.** Apagar fecha a conferência sem rastro; sem a marca, o mesmo dinheiro sai em dois recibos. Conferência feita por quem fechou não vale nada.

### Depósito prévio é amarrado ao título, entra no caixa e é gravado mesmo sem caixa aberto
**Regra.** O depósito é lançado na tela do título, amarrado a ele com saldo somado, entra no caixa do operador e, sem caixa aberto, é gravado com aviso. Sua criação existe numa só função, com teste que impede `INSERT` por fora. Pode indicar atribuição e serviço do catálogo (código do Tribunal ou palavra resolvida no servidor; palavra ambígua é recusada listando os códigos); havendo vínculo, ele ganha da escolha e a divergência é exibida; sem vínculo, nada se deduz do texto livre.
**Por quê.** Depósito longe do título perde referência; recusar porque a gaveta está fechada perde o fato; regra copiada diverge. Texto livre não soma nem filtra, e deduzir dele é inventar.
**No código.** `caixa_depositos.py` (`sugerir_tipo`, `gravar_tipos`).

### A prioridade do título protocolado não se estica nem se perde
**Regra.** Corrigir partes ou dados de título protocolado exige motivo e grava na auditoria valor anterior e novo, campo a campo, sem tocar no teor; número de ordem, livro e data da prenotação não se corrigem por aí. Reabrir protocolo encerrado por engano exige motivo, registra situação anterior, quem e quando, e não reinicia o prazo. A prenotação sela, mas selo que falha não a derruba. Ao lavrar, a tela oferece as prenotações abertas e amarrar a encerra; prenotação já amarrada continua no primeiro ato; cancelada não reabre.
**Por quê.** "Registro editado" não responde à correição. Protocolo novo jogaria o título para o fim da fila; reabrir com prazo novo esticaria a prioridade sobre terceiros. A prioridade conta da hora da entrada e não se transfere.
**Fundamento.** Lei 6.015/1973, art. 186.
**No código.** `ri_web.py`, `ri_correcoes.py`.

## Assinatura digital A3

### O sistema nunca assina, nunca guarda chave ou PIN, nunca carrega driver de token no seu processo
**Regra.** O sistema monta o documento, guarda o assinado, confere e lê quem assinou. Assina-se na própria tela do ato, mas a assinatura ocorre fora do servidor web: no assinador do delegatário (que devolve o `.p7s`) ou num serviço local na estação de quem assina, chamado pelo navegador em `localhost`. Esse serviço escuta só em `127.0.0.1` (recusa `0.0.0.0`); carrega PKCS#11 só em processo filho; aceita driver explícito por parâmetro, variável de ambiente ou arquivo; recebe o PIN só no ato, sem gravá-lo em banco, log, arquivo ou linha de comando; e não registra corpo de requisição.
**Por quê.** Driver PKCS#11 pode derrubar o processo com falha de segmentação, que `try/except` não trata — cairia o sistema inteiro. No A3 a chave não sai do token; o servidor não alcança tokens de outras máquinas e o navegador não fala PKCS#11.
**No código.** `assinar_com_a3.py`, `a3_servico_local.py`.

### A conferência que mais protege é a do conteúdo embrulhado, byte a byte
**Regra.** Ao receber o `.p7s`: é PKCS#7 `signedData`; o documento anexado é byte a byte o emitido; quem assinou (nome e CPF do e-CPF); cadeia até a raiz ICP-Brasil. Nada disso exige segredo.
**Por quê.** Pega assinatura de arquivo errado ou alterado. A assinatura é anexada: guardar só o PDF é guardar papel sem firma.

### A fila de assinatura é do núcleo e serve todos os papéis
**Regra.** Todo papel (certidões, termos, recibos, traslados, comprovantes, editais, instrumentos) segue monta → espera assinatura → volta assinado → arquivado; o módulo informa só de que ato é. Papel não assinado sai dizendo que está sem assinatura. Os certificados autorizados (delegatário e substitutos, cada um com seu CPF) são cadastro explícito.
**Por quê.** Várias implementações dariam várias respostas para "este papel está assinado?"; papel que se diz assinado sem estar é pior que papel sem assinatura; sem o cadastro, o papel legítimo do substituto seria recusado.
