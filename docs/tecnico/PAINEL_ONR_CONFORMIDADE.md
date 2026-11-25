# Painel de conformidade do ONR (RI010)

Tela: **Registro de Imóveis → Centrais e obrigações → ONR: painel de conformidade** (`/ri/onr/conformidade`).
Ver e imprimir: oficial, gerente e auditor. Lançar: oficial e gerente. **A tela não envia nada ao ONR, não entra
no portal e não chama a API.**

## Para que serve

O Painel ADPF 743 do ONR não aparece no login da serventia, e o número dele para o Provimento 143 é o que a própria
serventia declarou no «Cronograma de Dados – CNJ», não o que o ONR recebeu. O painel mostra, lado a lado, para cada
número: **declarado ao ONR** (digitado, com data de leitura, origem e quem lançou), **existe no sistema**,
**entregue com prova** e **falta**.

## O que conta como «entregue com prova»

| Número | Fontes |
|---|---|
| Livro 4 | `ri_onr_envios` (INDICADOR, PRODUCAO, só ACEITO) · importação informada «Importado» |
| Livro 5 | `ge_onr_cargas` (carga completa do IPS em PROCESSADO) · importação informada «Importado» |
| Livro 2 digitalizadas | marca `digi_onr_pendente = 0` **com** `onr_csl2_desde` informado · importação informada «Importado» |
| ITN 003 e polígonos | só importação informada: o sistema não tem canal próprio |

Vale o **maior** entre as fontes, nunca a soma (podem contar as mesmas matrículas). Enviado, em fila, em homologação,
«processando», «não importado» e lançamento anulado **não** contam.

## Divergências (declarado sem lastro)

`SOMA_ACIMA_DO_TOTAL`, `DECLARADO_ACIMA_DO_SISTEMA`, `SEM_ENTREGA`, `DECLARADO_ACIMA_DA_ENTREGA`,
`LIVRO2_DISPONIVEL_SEM_CSL2`, `DISPONIVEL_SEM_PROVA`. Obrigação com divergência nunca fica «em dia».
Os **ajustes** (declarado abaixo da entrega, total diferente do sistema, leitura com mais de 7 dias) só aparecem na tela.

## Semáforo e checklist

O painel entrega achados ao gestor (`gestor_cargas_ri.conferir` → `onr_conformidade.achados_para_o_gestor`, setor RI);
`conformidade.py` não mudou. Sem número lançado, não acusa. Divergência é ATENCAO (conta, não pinta). Obrigação em falta
**sem pendência aberta** é PRAZO sem data (amarelo). Pendência aberta é PRAZO com a data dela, e VENCIDO (vermelho) depois
dela. As três regras são do oficial: não viram tarefa de escrevente. A checklist de gestão ganhou a linha «Painel de
conformidade do ONR».

## Tabelas

`onr_declaracoes`, `onr_provas_informadas`, `onr_pendencias` (+ anexo `ONR_PENDENCIA` em `attachments`).
Só se acrescenta; corrigir é lançar de novo ou anular, com motivo.

## Quadro para a Corregedoria

`/ri/onr/conformidade/quadro` (impressão) e `/quadro/papel` (PDF): cada número com data e origem, as divergências e
as pendências com protocolo e comprovante (nome e sha-256). As regras do painel do ONR citadas são as **observadas** no anexo
da Circular, e não norma.
