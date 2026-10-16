# Registro de Imóveis: matrícula, atos, prenotação, CNIB, usucapião, retificação, DOI e certidões

Decisões do módulo de Registro de Imóveis que valem para qualquer serventia: numeração e modelos de atos, prenotação, CNIB, usucapião e retificação como processos, certidões, busca, orçamento de garantias, DOI/CTP e importação de acervo.

## Matrícula e numeração dos atos

### O próximo número do ato considera também os atos escritos dentro do teor da ficha
**Regra.** Em fichas migradas, os atos costumam morar no texto da matrícula (`AV-5/1.234`) e não na tabela de atos. Na ficha que o sistema numera sozinho, o próximo número é o maior entre a tabela e o texto; na ficha de acervo, o campo vem preenchido com o que o texto indica, com aviso citando a frase, e quem confere o livro físico pode trocar. A recusa de número ocupado também olha o texto.
**Por quê.** `MAX(numero)+1` sobre a tabela não enxerga o texto e faz o ato nascer com número já usado no papel, sem ninguém digitar nada.
**No código.** `ri_numeros_do_teor.py`.

### O leitor do teor só aceita rótulo com a barra e o número da própria matrícula, e nunca cria ato
**Regra.** Conta-se `AV-5/1.234` só se o número depois da barra for o desta ficha; `AV-3` solto e ato de outra matrícula citado no teor não contam. O módulo só lê e mostra a frase de onde tirou; há teste que o varre procurando `INSERT`, `UPDATE` e `DELETE`.
**Por quê.** O teor antigo cita atos de outros imóveis o tempo todo, e o número devolvido vira número de registro: é melhor deixar de achar do que achar errado. Criar ato a partir do texto seria fabricar data, natureza e conteúdo adivinhados e pô-los na corrente de hash, que existe para provar que nenhum ato foi inventado.
**No código.** `ri_numeros_do_teor.py`.

### O CNM é gerado e validado pelo módulo 97-10, e não sobrescreve o emitido
**Regra.** Formato `CCCCCC.L.NNNNNNN-DD`: CNS (6), livro (1: o número 2 ou 3, nunca a letra do volume), número de ordem (7) e DV = `98 − (base × 100 mod 97)`. O sistema calcula e mostra como «calculado, ainda não gravado»; gravar é ação humana. Se o emitido divergir, vale o emitido e a divergência vai ao oficial. Na digitalização, o DV lido por OCR é descartado e recalculado.
**Por quê.** O código é derivado, mas quem assina o registro é o oficial. O hífen e os dígitos finais são o que o OCR mais corrompe.
**Fundamento.** Provimento CNJ 143/2023; ISO 7064 MOD 97-10.

## Modelos de atos

### Os modelos usam três notações distintas: campo, escolha e cláusula condicional
**Regra.** `[CAMPO]` é caixa de texto; `{opção A | opção B}` é lista em que a não escolhida some; `«SE ...: ...»` é caixa de marcar, e desmarcada a cláusula some inteira.
**Por quê.** O colchete usado para as três coisas produziu colchete órfão e alternativas impressas juntas (sentença judicial e ata notarial no mesmo ato de usucapião). Ato lavrado com defeito não se apaga.

### Aquisição originária não herda os requisitos da derivada, e evento futuro não se anuncia no registro
**Regra.** Usucapião e título de domínio têm lista própria, sem continuidade nem disponibilidade. O registro da alienação fiduciária não anuncia a consolidação, que é ato autônomo com modelo próprio. Texto condicional do modelo só sai quando a condição existe no título.
**Por quê.** Usucapião não tem transmitente e a área pode ser maior que a matriculada; título de domínio é destaque do patrimônio público.
**Fundamento.** Lei 11.952/2009; Lei 6.383/1976; Lei 9.514/1997, art. 26; Código de Normas TJMA, art. 761 (norma estadual — TJMA; confira o Código de Normas do seu estado).

### A penhora é averbada, e o modelo cita as fontes da divergência
**Regra.** O modelo é de averbação e cita as três fontes. Basta requerimento com cópia do auto ou termo, sem mandado; havendo impenhorabilidade no assento, informa-se o juízo antes de averbar. Indisponibilidade gera uma averbação por proprietário atingido.
**Por quê.** A Lei 6.015 arrola a penhora no inciso de registro e o CPC fala em averbação; a nota devolutiva e a certidão precisam de onde se apoiar.
**Fundamento.** Lei 6.015/1973, art. 167, I; CPC, art. 844; Código de Normas TJMA, arts. 502, 504 p.ú. e 532, «k» (norma estadual — TJMA; confira o Código de Normas do seu estado).

## Prenotação e livros

### A prenotação fica suspensa enquanto a dúvida tramita
**Regra.** A contagem do prazo da prenotação para durante a suscitação de dúvida.
**Por quê.** Contar dias úteis corridos sem suspensão declara vencida uma prenotação viva e faz a prioridade se perder.
**Fundamento.** Lei 6.015/1973, arts. 198 a 204; Código de Normas TJMA, art. 48, IV (norma estadual — TJMA; confira o Código de Normas do seu estado).

### O sistema precisa do Livro 3 e do cadastro de aquisições rurais por estrangeiros
**Regra.** Cédulas de crédito, penhor, convenção de condomínio e tombamento vão ao Livro 3, com numeração e certidão próprias. Aquisição de imóvel rural por estrangeiro tem cadastro próprio, base das remessas periódicas.
**Por quê.** Sem o livro não há onde registrar; mexer no esquema é melhor antes de o acervo crescer.
**Fundamento.** Lei 5.709/1971, art. 10; Código de Normas TJMA, art. 424 (norma estadual — TJMA; confira o Código de Normas do seu estado).

## CNIB — indisponibilidade de bens

### O sistema avisa e prepara a averbação; quem decide é o oficial
**Regra.** Ao achar parte de matrícula com ordem do CNIB, a tela mostra a averbação já redigida e dois caminhos: abrir a matrícula para averbar pela tela de atos, ou «não é a mesma pessoa» com motivo escrito. A decisão fica gravada e a linha sai da lista. O módulo não tem função que averbe.
**Por quê.** Homônimo é a regra. Averbar no imóvel do homônimo tira de um inocente o direito de dispor, e só se desfaz por ordem de cancelamento. Quem lavra é a tela do RI, com corrente de hash, selo e emolumentos.
**No código.** `ri_cnib.py`.

### Documento antes de nome, e nome comparado normalizado dos dois lados
**Regra.** O achado por documento aparece primeiro. Nome se compara por coluna normalizada (sem acento, sem caixa), preenchida pela mesma função dos dois lados. A exclusão de «já achado por documento» olha a lista procurada, não a tabela inteira.
**Por quê.** `UPPER` do SQLite é só ASCII, e a exclusão contra a tabela inteira deixava a busca por nome sempre vazia: o alerta nunca aparecia, sem erro em lugar nenhum.
**No código.** `ri_cnib.py`.

### A Central não entrega base: a cópia local se mantém varrendo páginas, sem nunca consumir a fila
**Regra.** A atualização lê `/api/v2/ordem/visualizar` numa janela de datas, sempre com `ordens_visualizadas=True` e sem parâmetro para mudar isso; grava por UPSERT na chave do protocolo; nunca apaga o que não veio; volta sete dias atrás. Resposta em forma estranha é leitura recusada e a janela não anda. No UPSERT, `COALESCE` nos campos de cancelamento impede que a ordem chegando depois do próprio cancelamento seja reativada.
**Por quê.** Com `False` a leitura consome a fila, e uma rotina diária a esvaziaria sem ninguém ver. As páginas não são disjuntas, e resposta vazia não prova ausência.
**No código.** `cnib_api.py`, `cnib_atualizador.py`.

### Rede fora da transação, validade da cópia pelo registro das leituras
**Regra.** Ler na Central e gravar no banco são funções separadas. Cada ida à Central, inclusive as que falharam, vira linha numa tabela de leituras, e é ela que diz até quando a cópia vale — não o `MAX(data_pedido)`. A posta em dia anda mês a mês a partir de ponto fixo (o fim do acervo migrado), um botão por pedaço, e o pedaço que bate no teto de páginas fica marcado. A rotina diária roda em linha de fundo com conexão própria, disparada quando alguém abre o sistema, e não faz a posta em dia.
**Por quê.** A janela filtra pela data da atividade: o cancelamento recente de ordem antiga moveria o `MAX`, e uma única ordem de hoje faria anos de atraso «sumirem». Rede de até 60 s por página no início da requisição deixaria a primeira tela girando.
**No código.** `cnib_atualizador.py`, `cnib_web.py`.

### A credencial do CNIB fica fora do banco, e o token é esquecido quando ela muda
**Regra.** O par mora em arquivo fora do banco; vindo do sistema anterior, é lido e gravado no servidor no mesmo passo, e a auditoria registra que se trouxe, nunca o quê. Trocar a credencial descarta o token em memória. O CPF de quem consulta fica nas configurações.
**Por quê.** O banco viaja no backup. Token velho sobrevivendo à troca faz a correção «não pegar».
**Fundamento.** Consulta do transmitente e do adquirente, com registro eletrônico: Código de Normas TJMA, art. 506 (norma estadual — TJMA; confira o Código de Normas do seu estado).

## Usucapião extrajudicial

### Usucapião é processo, não se pula etapa, e decidir não é registrar
**Regra.** Capa, peças, andamento, prazos, conferência e decisão, com «o que fazer agora» calculado do estado. Voltar é permitido; pular não. Dispensar item exige motivo escrito, e não se decide procedente com item pendente. A decisão procedente deixa o processo aberto até o ato sair na matrícula, e a amarração confere que o ato existe. A decisão serve de título.
**Por quê.** Cada fase protege alguém — confrontante, entes públicos, terceiro do edital — e registro com fase pulada nasce nulo.
**Fundamento.** Lei 6.015/1973, art. 216-A; Código de Normas TJMA, arts. 747 a 761, em especial 757 (norma estadual — TJMA; confira o Código de Normas do seu estado).
**No código.** `usucapiao.py`, `us_tjma.py`.

### O prazo do edital tem dois saltos de dia útil
**Regra.** A publicação é o primeiro dia útil depois da disponibilização na Central (data devolvida por ela, não «hoje»); os prazos começam no primeiro dia útil depois da publicação. Feriados vêm de configuração. Sem origem registrária, o edital consigna isso.
**Por quê.** Contar da disponibilização erra por um dia, e errar edital é recomeçá-lo.
**Fundamento.** Código de Normas TJMA, art. 755, §§ 1º e 2º (norma estadual — TJMA; confira o Código de Normas do seu estado).
**No código.** `us_tjma.inicio_do_prazo`.

### Notificação, ofício aos três entes e edital têm modelo, e nada se grava sem o papel
**Regra.** A notificação registra endereço, forma e tentativa, com recibo no mesmo papel; formas e endereços são os mesmos objetos da retificação, não cópia. Os ofícios a União, Estado e Município saem juntos. O teor de cada papel congela. Sem endereço ou com forma não prevista, nada é gravado.
**Por quê.** Edital só cabe frustradas as anteriores, e sem a tentativa ninguém prova que houve. Esquecer um ente é vício que aparece depois do registro.
**Fundamento.** Lei 6.015/1973, art. 216-A, §§ 2º a 4º; Código de Normas TJMA, arts. 754 e 755 (norma estadual — TJMA; confira o Código de Normas do seu estado).

### Prazo «citado» é mostrado e não imposto
**Regra.** Cada prazo leva a procedência: «lido» (conferido no texto da norma) é imposto; «citado» (texto oficial não lido) aparece e quem confirma é o oficial.
**Por quê.** Prazo errado numa notificação vira impugnação perdida meses depois, e o silêncio do titular tabular vale concordância.

### O checklist traz o que o Código manda perguntar, e o sistema não julga
**Regra.** Inclui a justificação do óbice com o alerta de que declaração falsa é crime (hipóteses «entre outras»); a vedação de exigência tributária sobre os negócios que provam a posse; o conteúdo da planta (UTM SIRGAS 2000, cada confrontante identificado); as situações de área contra matrícula; o que não impede (imóvel sem registro, área abaixo da fração mínima, ônus com titulares notificados, indisponibilidade posterior ao início da posse); a vedação absoluta (garantia no SFH); os deveres diante de indisponibilidade; e o imóvel edificado. Não decide se a impugnação procede, se a posse está provada ou se o óbice se justifica.
**Por quê.** A lista do que não impede evita que um balcão inseguro trave pedido bom. Há teste que exige cada artigo da faixa.
**Fundamento.** Código de Normas TJMA, arts. 738, 739, 748, 749, 753, 756, 758, 759, 760 e 761 (norma estadual — TJMA; confira o Código de Normas do seu estado); Lei 6.015/1973, art. 247-A.

### Parecer externo entra «por conferir», e a decisão recusa parecer não lido
**Regra.** O processo exporta relatório (CPF/CNPJ mascarados por padrão, sha256 na auditoria) e importa parecer de qualquer origem — advogado, assessoria ou IA. O parecer não tem campo de sentido; a decisão não fecha apoiada em parecer não conferido, e o hash amarra o parecer à versão dos autos. Chave de tipo já gravada no banco não se renomeia: muda-se a etiqueta.
**Por quê.** A decisão é ato do delegatário e não se delega. Renomear a chave faria movimentos lançados sumirem.
**No código.** `usucapiao.py`.

## Retificação administrativa e georreferenciamento

### A retificação é processo em dias úteis, e o prazo do SIGEF é contado pela serventia
**Regra.** O módulo controla instrução, notificação, impugnação e decisão em dias úteis pelo calendário da casa. Averbada a poligonal certificada, abre-se o prazo de 30 dias corridos para requerer o registro no SIGEF com as certidões da matrícula nova e da encerrada.
**Por quê.** A obrigação do SIGEF nasce depois do ato, quando o cliente já foi embora.
**Fundamento.** Lei 6.015/1973, arts. 212 e 213; Código de Normas TJMA, arts. 587 a 620, em especial 597 a 600 e 620, § 2º (norma estadual — TJMA; confira o Código de Normas do seu estado).
**No código.** `rt_tjma.py`, `retificacao.py`.

### Prazo vencido presume anuência, mas a porta só fecha com a averbação
**Regra.** O sistema diz que a anuência se presume e continua aceitando impugnação até a averbação. O prazo conta individualmente para cada notificado. Só contam confrontantes de divisas afetadas; credor real e senhorio direto só são notificados. A notificação segue a ordem: pessoal, RTD, correio com AR, e edital só frustradas as anteriores. A instrução pede duas plantas (área retificada e área como está na matrícula). Não há limite de aumento ou redução de área que reflita as divisas reais.
**Por quê.** Tratar «prazo vencido» como «acabou» erraria em favor de quem não foi ouvido.
**Fundamento.** Código de Normas TJMA, arts. 589, 592, 593, 596, 598 e 599, §§ 1º e 3º (norma estadual — TJMA; confira o Código de Normas do seu estado); Lei 6.015/1973, art. 213, § 2º.

### Retificação e georreferenciamento terminam em matrícula nova; o módulo prepara e a tela do RI lavra
**Regra.** Procedente: averba-se a retificação (e a certificação), encerra-se a matrícula anterior, abre-se a nova (com o memorial do SIGEF e o número da certificação do INCRA) e transportam-se os ônus não cancelados. O módulo não lavra e não julga a impugnação; improcedente, abre-se prazo para pedir suscitação de dúvida.
**Fundamento.** Código de Normas TJMA, arts. 604 e 610 a 620 (norma estadual — TJMA; confira o Código de Normas do seu estado); Lei 6.015/1973, art. 176, §§ 3º a 7º; Decreto 4.449/2002.

## Certidões do RI

### Não existe «certidão negativa» na tela da matrícula
**Regra.** A ficha oferece só certidões sobre aquele imóvel (inteiro teor, ônus, propriedade).
**Por quê.** «Nada consta em nome do requerente» certifica busca por pessoa em todos os livros, que é outra pergunta. Ao lado do inteiro teor, entregaria um papel sobre o nome e não sobre o imóvel.

### A certidão é um molde comum mais um miolo por tipo, e a emenda é conferida duas vezes
**Regra.** O molde guarda abertura, finalidade, validade e assinatura, e carrega um marcador obrigatório do miolo. A falta do marcador é recusada ao gravar o modelo e de novo ao emitir, pela mesma função. Tipos, miolos e códigos de selo são o mesmo conjunto, por teste. O miolo é renderizado antes de entrar no molde. Tipo sem texto conhecido não é inventado: acrescentá-lo é acrescentar um miolo.
**Por quê.** Com um texto só e vários `if`, mexer no comum estragava os outros tipos. Sem o miolo, a certidão afirmaria «cujo inteiro teor segue:» sem reproduzir nada. Teor de acervo traz `{{ }}`, que renderizado junto seria lido como modelo.
**No código.** `ri_odt.py` (`MARCADOR_DO_MIOLO`, `MIOLO_DA_CERTIDAO`), `modelos_da_casa.conferir_marcadores`, `ri_schema.TIPOS_CERTIDAO`.

### Toda limpeza do teor acontece antes do hash, e mudança de forma se prova byte a byte
**Regra.** Transformações no teor são feitas antes de calcular a impressão da certidão. Reorganizar modelos exige renderizar os tipos contra fichas de ensaio na versão anterior e na nova, com resultado idêntico.
**Por quê.** Limpar depois do hash faz a conferência do teor falhar em toda certidão nova, calada. O risco de reestruturar modelos é mudar o papel sem ninguém ver.

## Busca de matrículas

### Número, CNM e documento por igualdade; nome e endereço por trecho normalizado
**Regra.** Uma regra serve a lista de matrículas e os indicadores real e pessoal. CNM e documento comparados só pelos dígitos, com ou sem máscara; documento por igualdade quando o digitado tem dígitos suficientes. A parte cadastrada grava a coluna normalizada no mesmo `INSERT`, e uma passada idempotente preenche as colunas derivadas na subida do sistema, sem inventar valor onde não há fonte.
**Por quê.** «Contém» sobre CPF trazia matrícula de outra pessoa, e um dígito solto trazia mais de mil fichas. Nome comparado cru não achava quem digitasse em minúsculas, e para muitas partes o nome é o único caminho.
**No código.** `ri_web.py` (`_condicao_de_busca_da_matricula`), `preencher_colunas_derivadas`.

## Emolumentos e orçamento

### Garantia em vários imóveis: cada garantia guarda o valor cheio, dividido pelos imóveis em que ela está
**Regra.** Não se divide pelo número de garantias. Cada garantia usa o valor total, dividido pelos imóveis daquela garantia, com quantidade igual ao número de imóveis. Divisão em centavos inteiros, sobra declarada. Dividir nem sempre é desconto: duas faixas menores podem somar mais que uma grande.
**Por quê.** Ponto flutuante pode pôr a base do lado errado da fronteira de uma faixa.
**Fundamento.** Tabela de emolumentos do TJMA, itens 16.29 e 16.31 (norma estadual — TJMA; confira a tabela do seu estado).

### O teto de emolumentos é lido da tabela, e o sistema avisa sem cortar
**Regra.** O limite geral vem da última faixa da tabela vigente. A tela mostra o valor da tabela e o do teto, e o oficial decide; há teste que recusa função que corte sozinha.
**Por quê.** O teto muda a cada exercício, e há disputa aberta sobre se conta por tipo de garantia ou pela soma do título; cortar seria o sistema decidindo tese jurídica.
**Fundamento.** Resolução-GP 143/2025 do TJMA, art. 2º (norma estadual — TJMA; confira a norma do seu estado).
**No código.** `emolumentos.teto_geral()`.

### A busca de ato devolve uma linha por código do TJ, a que tem preço
**Regra.** Código repetido no cadastro de serviços aparece uma vez, a linha com preço na vigência; as faixas são rotuladas pela descrição do item.
**Por quê.** Linhas sem preço davam «não encontrei esse ato» com o código certo e esgotavam o limite da lista antes do ato procurado. Nenhum código tem dois preços na mesma vigência.

### Na migração de itens de protocolo, valor total é quantidade × unitário
**Regra.** A carga multiplica emolumento e fundos pela quantidade (ausente ou zero vale 1). A correção do já carregado só mede por padrão, copia o banco antes, é idempotente e recusa item quitado ou com lançamento no caixa, item sem origem e item editado à mão.
**Por quê.** O sistema anterior guardava o unitário com a quantidade sem efeito. O acervo provou que a coluna é unitária; o caixa provou que a casa cobrou multiplicando. Dinheiro que entrou sai por estorno.
**No código.** `caixa_import.py`.

## DOI e CTP

### A DOI é uma por serventia por mês, com Notas e RI juntos
**Regra.** Um arquivo reúne escrituras e atos do RI. Operação e tipo de imóvel escolhidos de lista; marca «este ato não tem imóvel» para procuração, ata e declaração; a conferência vem antes do botão de gerar. Campos INTEGER são lidos como número no de-para.
**Por quê.** É o que a Receita espera; duas telas dariam dois arquivos e um seria esquecido. Código digitado é recusado sem dizer a linha.
**No código.** `notas_doi.py`.

### O lado de cada parte sai da qualificação livre, com procurador descartado antes
**Regra.** Procuradores, representantes e testemunhas saem antes de procurar alienante e adquirente. Qualificação que bate nos dois lados vira dúvida, não desempate por ordem. «Proprietário», «permutante», «herdeiro» e «declarante» não dizem o lado. Escritura com parte não classificada para e diz nome e qualificação. A régua das Notas não se unifica com o vocabulário controlado das partes do RI.
**Por quê.** «Procurador do vendedor» contém «vendedor». Declaração aceita sem o alienante é pior que recusada. No RI, «proprietário» quer dizer dono de registro; unificar faria todos virarem alienantes.
**No código.** `notas_doi.py`, `ri_ctp.py`.

### A participação de cada lado soma entre 99% e 100%, e a sugestão fica à vista
**Regra.** Sugerida em partes iguais, editável, com o resto da divisão no primeiro, conferida no balcão.
**Por quê.** A Receita recusa o arquivo inteiro fora da faixa, e o arredondamento sozinho não a garante.

### A CTP às prefeituras é carga mensal com fechamento negativo
**Regra.** A competência lista todos os atos do mês, inclusive os que não entram, com o motivo. A operação é sugerida pelo modelo da lavratura, e quando deduzida do texto a tela avisa. Valor do negócio, base do imposto, pagamento, data e percentual são digitados fora do teor. O fechamento guarda o SHA-256, e mês sem transações também se fecha. O sistema gera e não transmite; acervo sem natureza e lados não entra retroativamente.
**Por quê.** Ato que some da tela ninguém confere, e mês sem ato também precisa de comprovante. Os códigos registrais não estavam publicados, e o padrão fica configurável.
**Fundamento.** Lei 8.935/1994, art. 30, XI; Provimento CNJ 174/2024.

## Importação e digitalização de acervo

### A automação prepara; quem confere e salva é a pessoa
**Regra.** Extratores produzem arquivo e não gravam; o sistema tem dois botões, conferir e importar. Campo não lido fica vazio, com o trecho do documento. Parte é vinculada ao cadastro por escolha humana. Nunca se escreve direto no banco de outro sistema.
**Por quê.** Vincular homônimo é erro grave de registro. Selo, matrícula e auditoria são gerados pelo sistema; inserir por fora pode invalidar o ato.

### Cada dado se ancora no rótulo que o papel imprime
**Regra.** A data do registro se ancora no cabeçalho (a primeira data costuma ser a do título de origem), e datas destoantes das matrículas vizinhas em número são marcadas. O nome vem depois do rótulo de papel e antes da vírgula da qualificação. Responsável técnico do memorial e quem lavra o ato não são partes. O título se lê no alto do documento. Antes de reprocessar por OCR, diagnostica-se o código de extração.
**Por quê.** Matrícula é aberta em ordem: vizinha de número é vizinha de data. Sem âncora, dado certo cai sob rótulo errado; e boa parte das falhas atribuídas ao OCR era do extrator.

### Quarentena derivada da régua da Central, sem correção por parecença
**Regra.** O que a Central exige (retém) e o que só avisa são listas separadas. Município se confere contra o cadastro do IBGE e nunca se corrige por grafia parecida. Data derivada por decisão do oficial leva marca visível na ficha, com o botão «confirmei no livro de papel», e a regra recusa onde o documento a desmente. Lote grande se ensaia importando numa cópia do banco e validando o arquivo da Central contra o XSD.
**Por quê.** Trocar letra em nome de município é adivinhar. Marca num campo que a ficha não abre fica muda. XML bem formado não é XML válido.

### Erro dentro de string SQL só aparece quando a tela é usada
**Regra.** Toda emissão de certidão tem teste que executa o caminho completo até o banco.
**Por quê.** Texto colado dentro do SQL não falha ao importar o módulo: o sistema sobe e só quem clica em «emitir» descobre.
