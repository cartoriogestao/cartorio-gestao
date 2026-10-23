# CRA-MA — o teste na homologação, medido (11 e 13/10/2026)

Pedido do oficial em 11/10/2026: *«faça o teste combinado com a cra na homologação»*;
em 13/10: *«pode baixar e me diga o que falta»*. Tudo em **HOMOLOGACAO**; a produção
não foi tocada. O banco usado foi um rascunho no scratchpad da sessão. Os
scripts do ensaio (`cra_homolog_1..6`) ficaram no scratchpad e não fazem parte do sistema.

## RESULTADO FINAL (13/10/2026, 12h40) — OS TRÊS ARQUIVOS ENTRAM PELA API

| arquivo | operação | nome | resposta da homologação |
|---|---|---|---|
| confirmação | `Confirmacao`, XML `<confirmacao>` | `C2371609.263` | **0000 — 10 títulos** |
| retorno | `Retorno`, XML `<retorno>` | `R2371310.261` | **0000** (era **9999** com o cabeçalho 68–100 e o rodapé 58–60 em branco) |
| andamento | **`TituloComplemento`**, XML `<complementos>` | `M2371310.261` | **2322 «Andamento inserido» nos 7 títulos** |

**O andamento NÃO é o arquivo de 600 posições**: o caminho veio do manual da P21 que o
oficial trouxe (*andamento em XML*). Por título vão protocolo, documento do devedor, data
do protocolo (`dd/mm/aaaa`), número do título, nosso número, valor e saldo com ponto, e o
andamento `AA` com data e hora (`dd/mm/aaaa HH:MM:SS`). A Central aceitou **sem** o bloco
de emolumentos — e o sistema não o manda, porque custa que não foi calculada não se
inventa. A resposta vem **por título**, dentro de `<mensagens>`; 2322 e 2318 querem dizer
«entrou».

**No sistema (SANDBOX)**: ao receber a remessa, o envio automático manda a confirmação de
cada lote e, **depois dela**, o andamento de cada apresentante; se a confirmação não
entrou, o andamento espera (ele fala de protocolos que só a confirmação apresenta). O
andamento que sai **em par com um retorno** (pagamento, protesto, desistência) **não**
vai pela API: o código desses andamentos não foi medido, e o sistema recusa dizendo
isso. O aviso «suba o andamento pelo portal» saiu da tela.

O que vem abaixo é o registro do dia na ordem em que aconteceu — inclusive o que se
concluiu cedo e depois se desfez.

## RESULTADO (13/10/2026, 11h31) — A CONFIRMAÇÃO PELA API ESTÁ FECHADA

`C2371609.263` (confirmação do lote 000023 do Bradesco, remessa `B2371609.263` de
16/09) foi enviada em XML no padrão do E-Ofício e a CRA respondeu **código 0000 —
10 títulos**. No portal de homologação a pendência «remessa não confirmada» sumiu.

- **O nome é o do arquivo da REMESSA com C no lugar de B** (data da remessa, 16/09, e
  a mesma sequência .263) — e não a data do download. O 2117 dos lotes 000001 e 000012
  era verdadeiro: eles já estavam confirmados.
- **O andamento NÃO sobe pela API.** O WSDL não tem operação de andamento; pela
  `Retorno`, com raiz `<andamento>` e com `<retorno>`, no layout oficial
  (`Layout_Andamento.pdf` da P21: t38 = código AA/AB/…, t51 = data e hora), a resposta
  vem **vazia** e o portal («Cancelar andamento») mostra **0 andamentos recebidos**.
  No portal ele entra por **Andamento → Upload andamento** (limite 11h12). Perguntar à
  CRA-MA se há caminho por webservice. **[Desfeito ao meio-dia: há — `TituloComplemento`,
  ver o resultado final no alto.]**
- Ficaram no portal: 2 arquivos de desistência a baixar (20 títulos) e títulos do
  Bradesco de 16/09 com retorno em atraso — material para o teste do retorno.

## O que se mediu

| passo | resultado |
|---|---|
| ligação (`BuscarApresentante`) | **ok** — credencial de homologação vale |
| remessa de 23/09 (`B2372309.261`, Bradesco 237, 3 lotes, 30 títulos) recebida pelo caminho da tela num banco de rascunho | 30 apontados, 3 confirmações e 1 andamento gerados |
| confirmação **como o sistema gera** (texto de 600 posições em `userDados`) | **recusada — 10000 «1.5 ARQUIVO XML CORROMPIDO»** |
| confirmação em **XML** no padrão do E-Ofício (`<confirmacao>`, hd/tr/tl) | **lida inteira**; recusa de negócio **2117 «já foi enviada remessa com o mesmo sequencial (000001/000012)»** — esses lotes já tinham confirmação na Central |
| `RemessaPendente` (13/10) | **0003** — não há remessa nova pendente |
| andamento em XML pela operação `Retorno` (`<retorno>`, `M2371310.261`) | **resposta vazia** |

**A nota de 30/09 estava errada.** `cra21_api.enviar_confirmacao` dizia «medido em
homologação: `userDados` é o arquivo inteiro», e o mesmo documento listava o envio
real como não feito. **O envio real é este, e a CRA quer XML.**

## O formato da confirmação — do exemplo oficial

Fonte: `EXEMPLO_CONFIRMACAO_RETORNO (6).zip` do repositório público da P21
(github.com/p21sistemas/manual-cra-21), que mantém a CRA21. Raiz `<confirmacao>` (e
`<retorno>` para o retorno), `hd` h01..h17, `tr` t01..t52, `tl` t01..t08 — as mesmas
larguras de `protesto_cra_xml.LARGURAS` —, **valores sem o preenchimento de espaços**,
numéricos com os zeros.

## O conteúdo — o precedente do E-Ofício (medido em C9010510, C1LV0610, CTAB1109)

- **Cabeçalho e rodapé copiam os da remessa**: só h05/h06 trocam (BFO↔SDT) e h07 vira
  `CRT`. Data (h04), sequencial (h08), contagens (h09–h12), h13, h14, h15 e o rodapé
  (t04, t05, t06) são **os mesmos da remessa**.
- **Título**: t16 `001`; t31 `01`; t32 protocolo; t33 vazio; t34 **data do protocolo
  DDMMAAAA**; t35 `0000000000`; t37 `00000000`; t43 `00000`; t44 15 zeros; t45 `000`;
  t50 `0000000000`. t36 traz uma letra (`G`, `D`, `I`) — **o que ela é não foi medido**.
- **Nome**: `C` + apresentante + **dia/mês da remessa** + `.AA` + sequência; **um
  arquivo por lote** (43 de 43 confirmações reais).

## CONSERTADO NO SANDBOX EM 13/10/2026 (tarde)

- `protesto_cra_xml.escrever_xml` — o arquivo de 600 posições no XML da CRA21
  (`<confirmacao>`/`<retorno>`); o andamento recusa, dizendo que sobe pelo portal.
- `protesto_retorno.nome_do_arquivo` — nome FEBRABAN (`C`/`R`/`M` + apresentante +
  DDMM + `.AA` + sequência contada no banco).
- `protesto_remessa._confirmar` — a confirmação é o LOTE DA REMESSA devolvido, com
  t31/t32/t34 e os zeros; nome com a data da remessa. `_para_registro` apagado.
- `protesto_retorno.montar` — o nome do apresentante no cabeçalho do andamento e do
  retorno vem do cabeçalho da remessa (saía o código do cedente).
- `protesto_cra_envio` — XML em `userDados`; nome conferido antes da rede; andamento
  não vai à API (volta em `pelo_portal`); e **a rede saiu da transação**: ler e
  gravar em duas transações curtas, a CRA no meio. `atribuicoes_web` passa quem
  abre a transação e avisa que o andamento sobe pelo portal.
- Testes: `tests/test_cra_homologacao_13_10.py` (8) e os quatro que cobravam o nome
  antigo / `userDados` em texto, atualizados com a razão escrita. 100 passaram na
  bateria do protesto; os guardas (portabilidade, função sem tela) e as telas, 17.

**Duas vermelhas que NÃO são desta passada**: `test_protesto_cra_envio::
test_enviar_confirmacao_monta_envelope` e `test_protesto_cra_e2e_txt::
test_txt_conferir_receber_apontar_dispara_envio_cra_homolog` — o objeto falso de
resposta HTTP desses testes (de 30/09) não tem `getheaders`, que `centrais_http.py`
(05/10) passou a chamar. O primeiro chama `cra21_api` direto, que não foi tocado.

**Não feito no andamento**: o código do andamento em t38 (AA, AB…), t35 (custas)
e t51 (data e hora) do layout da P21 — ele não sai pela API, e o arquivo do portal
segue como estava até a P21 responder sobre o caminho.

**Ao meio-dia, o andamento pela `TituloComplemento`** (manual da P21): `protesto_cra_envio.
montar_complemento` monta o `<complementos>` dos títulos do andamento (`pt_atos.
retorno_id`), `interpretar_resposta_complemento` lê a resposta título a título,
`enviar_pos_remessa` manda confirmação e andamento (`pelo_portal` saiu), e a rota deixou
de mandar subir pelo portal. Testes novos em `tests/test_cra_homologacao_13_10.py`: o XML
do manual, a leitura da resposta, confirmação e andamento fora da transação, e o
andamento que espera a confirmação recusada.

**Correção deste documento**: o «defeito 5» abaixo NÃO existe —
`interpretar_resposta_envio` já recusa resposta vazia; o «ok» que vi saiu do meu
script de ensaio, que transformava o erro em texto antes de interpretar.

## Os defeitos que o teste achou no sistema

1. `protesto_cra_envio` manda o **texto de 600 posições** em `userDados` — tem de ser XML.
2. Manda como `userArq` o **nome interno** (`SDTBFOCRT-237-20261011-001.txt`); a CRA
   recusa nome fora do padrão FEBRABAN (código 0002, medido em 12/09).
3. A confirmação gerada **não copia o cabeçalho da remessa**: h04 é a data de hoje,
   h09–h15 vão vazios, o rodapé tem t05 `00000` e a soma com 15 dígitos em vez de 18.
4. No título: t16 `000` (o E-Ofício manda `001`), **t34 (data do protocolo) zerado**,
   t43/t44/t45/t50 vazios.
5. `interpretar_resposta_envio` devolve **`ok: True` para resposta vazia** — o envio
   automático daria por enviado o que a CRA não aceitou.
6. O envio automático roda a chamada de rede **dentro de `db.transaction()`**
   (`atribuicoes_web`, recebimento da remessa) — contra a regra da casa.

## O que falta para fechar

Riscados ao meio-dia de 13/10: ~~remessa nova~~ (confirmação 0000), ~~o andamento~~
(`TituloComplemento`, 2322), ~~o retorno~~ (0000), ~~os seis defeitos~~ (consertados no
SANDBOX, com teste). O que resta:

1. **Credencial de produção** da CRA — é o oficial quem pede e digita.
2. **Empacotar e instalar** — quando ele pedir.
3. **O andamento que acompanha o retorno** (códigos de pagamento, protesto,
   desistência no `<complementos>`) — não medido; até lá vai pelo portal, e o sistema
   recusa mandá-lo pela API.
4. **As custas no andamento** (retirada/cancelamento) — a Central não exigiu; se a P21
   disser que precisa, saem da tabela (`protesto_cenprot.precos_do_titulo`), e não de
   número escrito.
