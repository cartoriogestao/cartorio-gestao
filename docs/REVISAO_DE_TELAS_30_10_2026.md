# Revisão de telas e funções, 30/10/2026

Pedido do oficial, antes de mexer no layout: confirmar que nenhuma tela antiga se
perdeu e que não há função utilizável sem tela. Medido no `main` da 3.7.8, só por
leitura do código, sem banco e sem subir o sistema.

## O tamanho

| | |
|---|---|
| Rotas | 1.060 |
| Rotas de tela (GET que desenha página) | 399 |
| Rotas só de gravação (POST) | 536 |
| Arquivos de tela | 455 |
| Itens no menu antes desta revisão | 216, para 198 destinos |

## Telas perdidas: nenhuma

Dos 455 arquivos de tela, 454 são desenhados por uma rota ou incluídos por outra
tela. O que sobra é `rcpn_certidao_impressa.html`: o papel da certidão passou para o
molde, e `docs/MODELOS_INVENTARIO.md` já o registra como morto. Não é tela perdida.

## Portas que faltavam, corrigidas nesta revisão

Partindo do menu e clicando, 71 rotas não eram alcançadas. Destas, 25 eram defeito:

| O quê | Rotas | O problema | A porta nova |
|---|---|---|---|
| Certidão diária em relação | 8 | Nenhum clique chegava nela | Protesto › Livros e repasses |
| Repasses ao apresentante | 11 | Só se achava pelo roteiro | Protesto › Livros e repasses |
| Livro de Pagamentos e de Protocolo | 1 | Só em «Livros obrigatórios», que o escrevente não vê. É o livro que as inspeções de 2021 e 2026 marcaram como inexistente | Protesto › Livros e repasses |
| Edital do usucapião pela Central do ONR | 4 | Nenhum clique chegava nele | Ficha do usucapião, junto do edital |
| Mapa do ONR (.csv) | 1 | O manual mandava digitar o endereço | Exportação para o ONR, só para quem baixa |

## Sem porta de propósito: 34 rotas

`tests/test_toda_pagina_tem_porta.py` guarda a lista, com o motivo de cada uma, e
cobra as duas direções: rota nova sem porta reprova, e nome que ganhou porta tem de
sair da lista.

| Por quê | Rotas |
|---|---|
| Importação do E-Ofício terminada: o oficial mandou tirar o botão | 10 |
| Endereço antigo que continua respondendo | 8 |
| Etiquetas e ações do WhatsApp que saíram na segunda revisão do #73 | 4 |
| Entrada no sistema: login em duas etapas e primeira instalação | 3 |
| Chamadas por script, com o endereço montado na tela | 4 |
| Chamadas por máquina: ponte do A3, Meta, sonda de saúde | 5 |

As outras 12 das 71 são chamadas pelos editores de modelos, com o endereço escrito no
`.js`. O varredor as reconhece sozinho, e por isso não entram na lista.

## Funções prontas sem tela

`tests/test_funcao_sem_tela.py` lista 155 funções sem caminho até uma tela, todas já
declaradas lá. A maior parte não é para ter tela: infraestrutura do banco de teste,
fila das Centrais, leitores internos, auxiliares de papel e ensaios.

As que uma pessoa usaria, e onde cada uma foi parar. `tests/test_funcoes_com_tela.py`
guarda as ligações:

| Função | O que faz | Situação |
|---|---|---|
| `cnib_api.consultar_por_documento` | «O que pesa sobre este CPF, agora», direto na Central | Sem tela: fala com a Central, espera o oficial |
| `onr_api.atendimentos` | Lista de pedidos eletrônicos do SAEC | Sem tela: fala com a Central, espera o oficial |
| `onr_api.interagir_no_atendimento`, `gerar_cobranca` | Responder no SAEC e gerar cobrança | Sem tela: escrevem na Central, só com ordem do oficial |
| `ato_selado.atos_sem_cobranca` | Atos com selo que ninguém cobrou | Sem tela: espera o oficial (abaixo) |
| `ato_selado.pagamentos_pendentes` | O que cada pessoa selou liberado e não foi pago | Selo e caixa, a cobrança de quem abriu a tela |
| `papel_seguranca.movimentos_da_folha` | O caminho de uma folha de segurança | Folhas de segurança, busca pelo número |
| `protesto_cenprot.titulos_sem_chave` | A lista por trás da contagem da CENPROT | Chave do CENPROT, recolhida junto da contagem |
| `protesto_retorno.atos_do_retorno` | Que atos entraram naquele retorno | Retorno à CRA, na linha de cada arquivo |
| `protesto_arquivo.conferir_remessa` | Conferir o arquivo contra o contrato da CRA | Não precisa: o fluxo já confere (abaixo) |
| `ri_digitalizacao.pendentes_onr` | Matrículas com imagem nova não enviada ao ONR | Exportação para o ONR, recolhida |
| `onr_indicador_xml.arquivo_xml` | O indicador real em XML | Exportação para o ONR, botão próprio (abaixo) |
| `rc_assento.blocos_do` | Os atos do assento pela divisão tripartite | Não precisa: a ficha já separa (abaixo) |
| `livro_nucleo.exigencias_da_inspecao` | O que a inspeção cobra, série por série | Livros e termos, recolhida |

**`atos_sem_cobranca` espera uma decisão: o que conta como cobrado.** Ela pergunta por
`lancamento_id`. As tabelas do Registro de Imóveis não têm essa coluna, e por isso a tela
de selos do RI, onde está o par `atos_sem_selo`, cairia ao chamá-la. Nas outras tabelas a
coluna só se preenche por `ato_selado.cobrar`: as Notas nunca o chamam, e desde a 3.7.0 o
dinheiro entra pelo protocolo, de modo que o ato pago apareceria como «ninguém cobrou».
O que a casa já mede pela régua nova é `selos_pagos_sem_cobertura`, em «Selos × caixa —
conferência».

**`conferir_remessa` e `blocos_do` não precisam de tela.** A conferência da remessa já passa
cada título por `protesto_cra.conferir_titulo`, a mesma conta, e mostra a falta de cada um.
A ficha do assento já tem um quadro para averbações, outro para anotações e outro para
retificações, e cada ato ali leva quem lavrou e a folha, que `blocos_do` não traz.

**O botão do XML manda o que a ficha diz.** Ele cobre as matrículas do período, com o mesmo
conteúdo da API, e a tela lista a que fica de fora e o motivo. O arquivo inteiro do acervo,
com a regra da casa de 10/10/2026 (`completar_ficha`, `donos_presumidos`), é outra coisa: foi
gerado pelo script `FERRAMENTAS/gerar_indicador_real_xml.py`, que ainda lê o banco antigo.
Levá-lo para a tela depende do oficial, porque o script traz decisões dele escritas à mão.

## Como repetir

```bash
python -c "import tests.test_toda_pagina_tem_porta as t; print(sorted(t.fora_de_alcance()))"
```
