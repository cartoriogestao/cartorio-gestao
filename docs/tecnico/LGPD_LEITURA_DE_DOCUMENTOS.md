# A leitura de documentos por IA — o que a LGPD pede, e o que esta casa fez

Serventia Extrajudicial do Ofício Único de Cidade Exemplo/MA — CNS 000000.
Redigido em 12/10/2026, por ordem do oficial: incluir este tratamento no
inventário de dados e no relatório de impacto, *«justificar a não utilização de
máscara para não afetar o serviço e justificar que a política de retenção é
apenas de 30 dias, não ficando indefinidamente salvo nos servidores de
terceiros»*. **Não haverá aviso ao cliente no balcão**, por decisão
dele, no mesmo dia.

Este documento tem duas partes, e cada uma é para ser revista e assinada pelo
oficial. **Não é parecer jurídico**: é a descrição do tratamento, medida no
sistema, e as escolhas feitas.

---

## 1. Item novo do Inventário de Dados Pessoais

| Campo | Conteúdo |
|---|---|
| **Processo** | Registro Civil das Pessoas Naturais — lavratura de nascimento e de óbito, e abertura da habilitação de casamento (desde 12/10/2026) |
| **Operação** | Leitura, por inteligência artificial, dos documentos apresentados pelo declarante, para preencher o rascunho do assento |
| **Onde, no sistema** | Registro Civil → «Ler documentos (DNV, DO)» (`rc_leitura_documentos.py`, tabela `rc_leituras`) |
| **Titulares** | Registrado ou falecido; mãe, pai e avós; declarante; os dois nubentes, os pais deles, o cônjuge anterior (na certidão de casamento com divórcio averbado) e as testemunhas da habilitação; outras pessoas que constem dos documentos (ex.: quem assina declaração de residência) |
| **Dados pessoais** | nome, filiação, data e local de nascimento, naturalidade, estado civil, profissão, endereço, CPF, RG, CNH, título de eleitor, Cartão SUS, assinatura e foto (constam da imagem do documento) |
| **Dados sensíveis** | cor/raça (DNV, DO), dados de saúde (causa da morte, Apgar, gestação), biometria (impressão digital impressa no RG) |
| **Finalidade** | Adiantar a digitação do assento; conferência cruzada dos documentos (nomes, datas, dígitos verificadores) |
| **Base legal** | LGPD art. 7º, II e III, e art. 23, § 4º (exercício da atribuição legal do registro civil); dados sensíveis: art. 11, II, «a» e «b» |
| **Operador** | Anthropic (provedora do modelo Claude), por API |
| **Transferência internacional** | Sim — os servidores da Anthropic ficam fora do Brasil (LGPD art. 33) |
| **O que sai da serventia** | as imagens das páginas anexadas: todas na triagem (reduzidas) e todas na leitura (inteiras), **sem máscara** (decisão do oficial em 12/10/2026). Nada mais do banco |
| **Registro do que saiu** | cada leitura guarda: arquivo, página, modelo e tokens (`rc_leituras.envios_json`); e há linha na auditoria (`RC_LEITURA_DE_DOCUMENTOS`) |
| **Guarda na serventia** | os documentos ficam como anexos da leitura (`attachments`, entidade `RC_LEITURA`), na pasta de arquivos do sistema, que vai no backup; o resultado da leitura fica em `rc_leituras` |
| **Guarda pela Anthropic** | **até 30 dias** — a retenção padrão da API, apagada automaticamente; exceções declaradas pela própria Anthropic: conteúdo marcado por violação da política de uso (até 2 anos) e obrigação legal. |
| **Quem acessa** | usuários logados do sistema (balcão do Registro Civil) |
| **Decisão automatizada** | **não há**: a leitura vira rascunho; quem confere com os originais e lavra é o escrevente (LGPD art. 20 não se aplica) |

---

## 2. Adendo ao Relatório de Impacto à Proteção de Dados (RIPD)

O RIPD da serventia é de 2023 (arquivo `19. ARQUIVO MORTO DIGITALIZADO/LGPD
2023`). Este adendo acrescenta o tratamento acima.

**2.1 Necessidade.** O assento de nascimento e o de óbito exigem os dados que
estão na DNV, na DO e nos documentos de identidade (Lei 6.015/1973, arts. 54 e
80). A leitura não cria dado novo: transcreve o que o declarante apresentou para
o registro.

**2.2 Por que sem máscara.** A finalidade é transcrever nome, CPF, filiação e
datas; mascará-los tornaria a leitura inútil. A escolha foi do oficial em
12/10/2026: mascarar não protege um serviço cujo produto é
exatamente o dado mascarado — a leitura deixaria de existir, e o balcão
voltaria a digitar à mão, com mais erro de transcrição no livro.

**2.2.1 A recomendação da inspeção 0000524, e a decisão.** A inspeção recomenda
*«implantar rotina de anonimização de dados sensíveis… em textos e
transferências de documentos a terceiros»*, e enviar o documento à Anthropic é
transferência a terceiro. **Decisão do oficial em 12/10/2026: manter o envio
sem máscara, justificado aqui**, com a retenção limitada descrita em 2.2.2.

A justificativa:

- **a anonimização frustraria a finalidade** — o que se transcreve é
  exatamente o dado pessoal (nome, CPF, filiação, datas), e o registro civil é
  obrigação legal (Lei 6.015/1973), não escolha;
- **a anonimização continua valendo onde a finalidade permite** — certidões,
  relatórios e comunicações seguem as regras próprias; esta é uma exceção
  delimitada à leitura para lavratura;
- **o terceiro é operador, e não destinatário**: trata o dado por conta da
  serventia, sem finalidade própria, não o usa para treinar modelos (termos
  comerciais da API) e o apaga em até 30 dias (2.2.2);
- **cada envio fica registrado** (arquivo, página, modelo, data e usuário), o
  que permite responder a titular e à Corregedoria o que saiu e quando;
- **nenhuma decisão é automatizada**: a leitura vira rascunho conferido e
  lavrado por pessoa.

**2.2.2 A retenção pela Anthropic.** Vale a retenção padrão da API comercial,
conferida em 12/10/2026 na página oficial (Privacy Center, «How long do
you store my organization's data?»,
<https://privacy.claude.com/en/articles/7996866>):

- **regra:** as entradas e saídas da API — aqui, as imagens dos documentos e a
  transcrição devolvida — são **apagadas automaticamente dos servidores da
  Anthropic em até 30 dias** do envio. **Não ficam guardadas indefinidamente**
  em servidor de terceiro;
- **exceções que a própria Anthropic declara, e que este relatório não
  omite:** (a) conteúdo marcado pelos sistemas automáticos dela como violação
  da política de uso pode ser guardado por até 2 anos; (b) guarda exigida por
  lei; (c) serviços de armazenamento que o cliente controla (ex.: Files API) —
  **que este sistema não usa**: as imagens vão dentro da própria requisição e
  nada é deixado guardado lá de propósito;
- **a hipótese (a) é remota neste tratamento:** os documentos são DNV, DO,
  certidões, identidades e requerimentos de habilitação, enviados com
  instrução de transcrição — nada que se aproxime do que a política de uso
  proíbe;
- **o prazo de 30 dias é curto diante do que está em jogo:** os mesmos dados
  ficam guardados para sempre no livro e no sistema da serventia, por
  obrigação legal; o que a Anthropic guarda é uma cópia transitória, apagada
  em semanas, de dado que já é público por natureza no registro (Lei
  6.015/1973, arts. 16 a 21), ressalvados os dados sensíveis, que seguem o
  art. 11 da LGPD;
- **a serventia guarda a prova**: cada envio fica registrado (arquivo, página,
  modelo, data e usuário), e o prazo de 30 dias conta a partir de cada um.

**A página da Anthropic pode mudar.** Este relatório cita a regra como estava
em 12/10/2026; ao revisá-lo, confira o endereço acima de novo — se o prazo
mudar, este item muda junto.

**2.3 Riscos e medidas.**

| Risco | Medida já existente | Medida a tomar |
|---|---|---|
| Vazamento ou uso indevido pelo operador | API comercial, sem uso para treino; apagado em até 30 dias (2.2.2); registro de cada envio | conferir o acordo de tratamento de dados (DPA) da Anthropic; reconferir a página de retenção a cada revisão deste relatório |
| Erro de leitura que vire erro no registro | rascunho, nunca ato; conferência cruzada; dúvida marcada «(?)»; o escrevente confere com o original | treinar o balcão a ler a lista «o que conferir» antes de lavrar |
| Envio de mais do que o necessário | só as páginas anexadas para aquele registro | — (decisão de 12/10/2026: sem máscara, justificado em 2.2 e 2.2.1) |
| Transferência internacional | operador com contrato | registrar a cláusula do DPA que trata de transferência |
| Acesso indevido na serventia | login; auditoria | — |

**2.4 Conclusão.** O tratamento é necessário e tem base legal. Mascarar os
documentos inviabilizaria o serviço, e por isso eles seguem sem máscara
(2.2 e 2.2.1). O risco residual fica limitado pela retenção padrão do
operador — **apagamento em até
30 dias**, sem uso para treino, com as exceções declaradas em 2.2.2 —, pelo
registro de cada envio e pela conferência humana antes de todo ato.

Cidade Exemplo/MA, ____ de __________ de 2026.

______________________________________
Oficial / Encarregado de dados
