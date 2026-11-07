# Atendimento e aprendizagem

O módulo **Trabalho** reúne os atendimentos e o treinamento.
**Entrada de caixa e protocolo geral** identifica a entrada financeira e o cadastro
do protocolo geral no balcão. O atendimento conserva
o número do protocolo geral; a apresentação ao RI conserva o número do Livro 1.
A ficha mostra separadamente a etapa do trabalho, a prenotação e o financeiro.
Pagamento não conclui o serviço nem concede prioridade registral.

## Usar no balcão

1. Abra **Trabalho → Atendimentos** e pesquise antes de cadastrar outro pedido.
2. Confira o vínculo à prenotação e os documentos. A ficha tem Resumo, Documentos,
   Análise e exigências, Atos e entrega, Financeiro e Histórico.
3. Assuma o pedido ou solicite a distribuição à gestão. **Meu trabalho** reúne
   os pedidos designados à sua conta. As anotações de acompanhamento já existentes
   continuam visíveis; nomes digitados anteriormente não viram vínculos automáticos.
4. Siga a próxima ação. Os atos, prazos, decisões, reingressos, selagem e movimentos
   financeiros usam as rotinas e validações próprias da atribuição.
5. No cumprimento de exigências, registre o item apresentado ou conferido e sua
   evidência. Essa conferência não emite decisão nem modifica a nota ou seu prazo.
   Documento retirado ou pertencente a outro pedido não serve como evidência.

## Ensinar um escrevente

Comece por **Treinamento → Primeiro dia**, depois pela trilha da atribuição.
O catálogo oferece roteiros, funções da interface, modelos de atos e documentos.
Cada aula explica a preparação, execução, conferência e encaminhamento; apresenta
os campos e comandos inventariados quando disponíveis. Aulas dos modelos de atos
também exibem a estrutura didática do texto de fábrica, com marcadores a preencher.

As situações fictícias registram somente aprendizagem e auditoria. Não criam
clientes, protocolos, atos, selos ou lançamentos. A conclusão exige todas as
respostas corretas e guarda pessoa, data e versão do conteúdo. Uma revisão da
aula exige nova prática. A gestão consulta **Aprendizagem da equipe**; somente
ADMIN publica orientações da serventia, com fontes, motivo e autoria.

A base normativa instalada pode ser pesquisada na área de treinamento. As aulas,
exercícios e pesquisas locais não fazem chamadas à API. A Ajuda continua disponível
pelo mecanismo próprio do sistema. O conteúdo operacional e os modelos exigem a
conferência das fontes e supervisão adequada ao caso; a conclusão da aprendizagem
não concede permissões para praticar atos.

## Atualizar a cobertura

`python tools/inventariar_treinamento.py` recompõe o inventário da versão do código.
O gerador lê menus, rotas, campos, comandos, catálogo de documentos e modelos de
fábrica. Não consulta o banco nem exporta atos ou documentos de clientes. Para uma
instalação diferente, use `--fonte` e `--saida`; `--sobrepor` permite conferir as
alterações dirigidas antes da implantação. Revise o inventário junto com a mudança
da rotina, especialmente a classificação de acesso e a família pedagógica.

As tabelas novas são inicializadas pelo próprio servidor: `at_responsaveis`,
`at_exigencia_itens`, `tr_tentativas` e `tr_orientacoes`. GETs consultam; gravações
exigem usuário autorizado e CSRF. O histórico anterior permanece nas rotinas de
origem. O sistema não cria vínculos de pedidos por semelhança de nome.

## Entregar o serviço concluído

Na aba **Atos e entrega**, identifique quem recebeu, descreva o que foi entregue e
confirme as conferências de documentos, assinaturas, selos e arquivamento. A ação
exige quitação (ou gratuidade já registrada), ausência de exigência aberta e saldo
de depósito resolvido. No RI, exige ato válido e selado e selo de arquivamento.
A entrega e sua auditoria são gravadas na mesma transação; repetir a confirmação
não troca o recebedor, a data nem cria outra ocorrência. Pagamentos, recibos,
documentos e selos são preservados.

O encerramento de um atendimento que não virou serviço continua na rotina
anterior. Não se estorna um pagamento para entregar o serviço concluído.

O Financeiro deriva total e quitação dos itens. Um depósito aplicado não é nova
entrada: o recibo do depósito comprova seu recebimento e o recibo do pagamento
direto comprova o saldo recebido depois. A ficha oferece os dois comprovantes.
A trilha do primeiro dia e as trilhas das atribuições incluem a aula de entrega.

A jornada de integração usa um escrevente USER, cliente fictício, tabela de ensaio,
matrícula histórica fictícia e selador HTTPS local de teste. Percorre os dois
layouts pelos formulários autenticados, até a entrega, sem API ou selagem reais.
