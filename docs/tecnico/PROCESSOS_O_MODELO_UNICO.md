# Processos — o modelo único da serventia (desenho, 12/10/2026)

> Pedido do oficial, 12/10/2026: *«abri uma tarefa da daniela, de averbacao de um
> divorcio, ainda que bem explicada a tarefa eh insuficiente. nao tem os docs
> necessarios e nao tem onde procurar. precisamos unir o modulo de tarefas e de
> expedientes para ser um unico modulo de Processos, em que reuniremos todos
> processos, protocolos e pedidos da serventia, adotando um modelo unico
> autosuficiente e completo para organizar, gerenciar e documentar todos processos
> internos do cartorio, desde malote, atos das atribuicoes e tarefas
> administrativas»*

## 1. O caso que motivou: tarefa #318 (escrevente), medido na produção

| o que a tarefa tinha | o que existia e ela não mostrava |
|---|---|
| texto da triagem do agente | **o mandado em PDF**, guardado no expediente EXP-2026-000012 (anexo 16) |
| «Matrícula nº 0000000155» | a matrícula inteira é `000000 01 55 2022 2 00003 154 0000929 90` — **Livro B-3, fl. 154, termo 929**, casamento de 2022, e o assento **existe no sistema (id 1689)** |
| pesquisa nos índices **do RI** por CPF | o assunto é do **Registro Civil**; a pesquisa foi feita na atribuição errada |
| expediente classificado como «Circulares», «para conhecimento» | é um **mandado para cumprimento**, com prazo de 48 h para comunicar (art. 100, § 4º, LRP — citado pelo próprio mandado) |
| — | **falta documento**: o mandado manda averbar «a sentença, que por cópia segue em anexo», e o PDF tem só o mandado (3 páginas). Sem a sentença não se averba: é preciso pedir ao juízo |
| — | **suspeita de assento duplicado**: há dois casamentos nº 929 de 2022, um na fl. 153 (id 1403) e outro na fl. 154 (id 1689) — conferir no livro antes de averbar |

Nada disso exige inteligência nova: **cada peça já estava no banco.** O que faltou foi um
lugar que as juntasse e um roteiro que dissesse o que precisa estar ali.

## 2. O que existe hoje (medido em 12/10/2026)

| | |
|---|---|
| tarefas (`tasks`) abertas | 145 — 72 da inspeção, 51 manuais, 12 do gestor, 9 do malote, 1 despacho |
| expedientes (`expedientes`) | 33 — 30 parados em RECEBIDO; categoria do malote, e não do assunto |
| ligação tarefa→expediente | 19 tarefas |
| documentos (`attachments`) | 205, guardados por entidade: EXPEDIENTE 44, TASK 46, RI_PROTOCOLO 61, NT_ATO 36… — **cada tela só vê os seus** |
| protocolo geral do balcão desde 18/08 | 109 (44 ABERTO, 45 A_PAGAR, 19 PAGO, 1 ENTREGUE) |
| prenotações do RI abertas | 31 (só 1 com protocolo geral — medido pelo agente do RI) |
| «o que ficou pelo caminho» (`inacabados`) | já lê 13 fontes na hora — é a semente do painel único |

Tarefa e expediente são **a mesma coisa vista por dois lados**: uma obrigação com
responsável, prazo, andamento e documentos. O expediente não tem histórico; a tarefa não
vê os documentos do expediente. Por isso a escrevente ficou sem o mandado.

## 3. O desenho

**Um processo é a unidade de trabalho da casa.** Tudo o que alguém precisa cumprir —
mandado do malote, pedido do balcão, prenotação, certidão pedida pela Central, item da
inspeção, tarefa administrativa — é um processo, com a mesma ficha.

### 3.1 A ficha do processo (autossuficiente)

1. **Número único** — `PROC-2026-000123`, um só para a casa.
2. **Origem** — malote, balcão, Central (CRC/ONR/CENPROT/ON-RCPN), inspeção, gestor, interno.
3. **Espécie, com roteiro** — por exemplo «Averbação por mandado judicial (RCPN)». O roteiro
   diz, com o artigo da norma ao lado: **os documentos exigidos**, os passos, quem decide, o
   prazo legal e o que encerra o processo. É ele que resolve o «não tem os docs necessários».
4. **Documentos exigidos × recebidos** — a lista do roteiro com o que já chegou e o que
   **falta**. Falta documento → o processo mostra «falta: sentença» e oferece o ofício de
   pedido ao remetente.
5. **Vínculos** — assento, matrícula, ato, protocolo geral, prenotação, expediente de
   entrada. O processo **aponta** para eles; não os copia (o ato continua no seu livro, com
   a sua numeração e o seu selo).
6. **A pasta do processo** — **todos os documentos de todos os vínculos numa lista só**:
   o PDF do malote, o título da prenotação, a evidência anexada, a certidão emitida.
7. **Partes e interessados.**
8. **Prazo** — o legal (do roteiro) e o combinado; o mais curto manda.
9. **Responsável, substituto e trâmite** — o «passar para» e o «reabrir» que a tarefa já
   tem (relato #59), agora também para o que vinha do malote.
10. **Andamento e decisão do oficial** — a linha do tempo que a tarefa já tem.
11. **Encerramento com prova** — o ato praticado, a resposta enviada ou o motivo escrito.

### 3.2 O que NÃO muda

- **Ato registral não vira processo nem sai do seu módulo.** A prenotação continua no Livro 1,
  o assento no seu livro, o selo no seu razão. O processo é a pasta; o ato é a peça.
- **Nada se apaga.** As 145 tarefas abertas e os 33 expedientes passam a ser processos com o
  mesmo número de antes guardado ao lado (os endereços antigos continuam abrindo).
- **Os robôs continuam funcionando.** Gestor, inspeção, malote e cobrança passam a abrir
  processo pelo mesmo caminho que hoje abre tarefa — com a guarda contra repetida de 12/10.

### 3.3 Como se constrói sem parar o balcão

| fase | o que entrega | risco |
|---|---|---|
| **0 — feita hoje** | a tela da tarefa mostra os documentos do expediente (SANDBOX, testado) | nenhum |
| **1** | a **pasta do processo**: na ficha, os documentos de todos os vínculos; vínculo com assento/matrícula/ato/prenotação | baixo |
| **2** | **espécies com roteiro** e a lista «exigido × recebido» — começando pelas mais frequentes: averbação por mandado (RCPN), pedido de certidão, prenotação/registro (RI), ofício de resposta, item de inspeção, tarefa administrativa | baixo — o texto do roteiro vem da norma e passa por você |
| **3** | **um módulo só**: expediente vira processo de origem «malote» (com remetente, nº externo e data de entrada), tela única «Processos», tarefas e expedientes viram vistas dela | médio — migração com cópia do banco e ensaio contra cópia da produção |
| **4** | o **balcão e as Centrais** entram: protocolo geral, prenotação (a etapa calculada pelo agente do RI), pedidos da CRC/ONR/CENPROT | médio |

## 4. O que só o oficial decide

1. **Todo protocolo do balcão vira processo?** Recomendação: **não** — só o que não se
   resolve no mesmo dia ou tem prazo (RI, RCPJ/RTD, retificação, habilitação, certidão que
   depende de busca). Firma e autenticação saem na hora; virar processo seria ruído.
2. **Quem aprova os roteiros.** Recomendação: o agente redige cada roteiro a partir do
   Código de Normas, com o artigo ao lado, e você (ou quem indicar por atribuição) aprova
   antes de valer.
3. **A ordem das fases** acima — em especial se a fase 3 (o módulo único) vem antes ou depois
   da 2 (os roteiros). Recomendação: 1 → 2 → 3 → 4, porque a 1 e a 2 resolvem já o caso da
   escrevente e não exigem migração.


## 5. O que o oficial decidiu, e o que já foi feito (12/10/2026)

**Decisões dele:** vira processo só o que **não se resolve na hora** — firma, autenticação de
cópia, registro de nascimento, certidão do balcão não viram; o rascunho de ato que fica para
outro dia **pode** virar processo; a lista de documentos é **exemplificativa** («cada caso seria
avaliado pelo escrevente e subiria o que é importante e existe»); seguir a ordem 1 → 2 → 3 → 4.

| fase | feito no SANDBOX | arquivos |
|---|---|---|
| 0 | a tarefa mostra os documentos do expediente | `app.py`, `task_detail.html` |
| 1 | **pasta do processo** (vínculos com expediente, assento, matrícula, prenotação, protocolo, ato das Notas, registro do RTD/RCPJ, rascunho; documentos de todos numa lista) e **rascunho → processo** | `processo_pasta.py`, `processo_pasta_web.py`, `_rascunho.html`, `rascunhos.html` |
| 2 | **roteiros** de 6 espécies, cada item com o artigo do Prov. 28/2026 e a página do PDF; marcação recebido/pedido/não se aplica; aprovação do oficial por espécie; nada trava | `processo_especies.py` |
| 3 | **a tela «Processos»**: lista única (comigo, abertos, vencidos, encerrados, todos; filtro por origem e busca), número `PROC-AAAA-NNNNNN`, e no alto **o que chegou pelo malote e espera decisão** — abrir processo (com o tipo sugerido) ou «só ciência» | `processos.py`, `processos_web.py`, `processos.html`, menu |

**Na fase 3 não houve migração de dado:** o processo é a tarefa (mesma tabela, mesmo número),
e o expediente sem processo aparece no alto da lista até alguém decidir. Por isso nada precisa
ser convertido no banco da produção — o pacote leva as telas e as tabelas novas
(`pr_vinculos`, `pr_especie_do_processo`, `pr_itens_marcados`, `pr_especies_aprovadas`), que
nascem vazias.

**Fase 4 (feita no SANDBOX):** a lista de Processos ganhou o bloco «Balcão, atribuições e Centrais —
esperando», que reaproveita a régua do painel dos inacabados (`inacabados.lista`, a mesma das 13
fontes): o atendimento do balcão **só entra depois do dia** em que foi aberto; prenotação, minuta,
rascunho e ficha sem ato do RI, escritura em lavratura e título do RTD/RCPJ ganham «Abrir processo»
(com a peça na pasta); usucapião, retificação e habilitação aparecem com o link, porque já são processo
no próprio módulo; e as filas das Centrais (Certidão Eletrônica do ON-RCPN, certidões do ONR,
pendências da CENPROT) aparecem com a contagem e o caminho. Na pasta, a prenotação mostra a **etapa
calculada pelo agente do RI** (`ri_pedidos.etapa`, uma régua só). O processo do rascunho conclui pela
pasta («o ato foi lavrado»), porque as telas de ato não carregam o número do rascunho até a lavratura
— o sistema não tem como saber sozinho.

**Fase 5 (feita no SANDBOX, 12/10/2026) — Processos substitui Tarefas e Expedientes no que o balcão vê:**
o menu perdeu «Expedientes / Malote», «Expedientes prontos para encerrar» e «Tarefas e pendências»; a
tela de Processos ganhou «Abrir processo interno» (era criar tarefa) e «Registrar entrada do malote»
(o cadastro de expediente, que volta para Processos), o filtro de setor e as vistas «Passou por mim» e
«Pediram minha resposta» (a mesma régua de `tarefa_processo.filtro_da_vista`); a ficha diz «Concluir
processo» e volta para Processos; o painel inicial aponta para Processos. As telas antigas continuam
abrindo, com aviso no alto. **E a guarda contra tarefa repetida passou a usar a régua de «aberta» da
lista** — a primeira versão engolia tarefa nova quando havia outra com palavra fora do vocabulário.

**O ROTEIRO SAIU (12/10/2026, à noite).** O oficial: «simplifique a parte do roteiro, deixe apenas
tarefa administrativa, ordem judicial, processos da corregedoria e ato do cartório pendente» e, em
seguida, «não precisa de roteiro». A fase 2 ficou só com o **tipo**: quatro opções
(`TAREFA_ADMINISTRATIVA`, `ORDEM_JUDICIAL`, `CORREGEDORIA`, `ATO_PENDENTE`), sugerido pela origem e
pelo texto, gravado na ficha («Tipo do processo») ou ao abrir, e usado nos filtros, no quadro de
fiscalização e na planilha. Saíram a lista de documentos, os passos, a marcação e a aprovação — e o
filtro e a coluna «documento pedido». As tabelas `pr_itens_marcados` e `pr_especies_aprovadas`
**não nascem mais**; quem já as tinha no SANDBOX fica com elas vazias e sem uso. O que falta num
processo se diz no andamento. Tipo gravado com um código antigo aparece como «sem tipo».
