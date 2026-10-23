# Caixa, recibo e depósito prévio — como usar

**14/08/2026.** Vale a partir do próximo `ATUALIZAR_SISTEMA.cmd`.

---

## Emitir um recibo — o caminho curto

O recibo nasce de um **lançamento no caixa**. Não existe recibo solto: se há recibo, houve
dinheiro entrando, e ele aparece no fechamento do dia.

1. **Menu → Caixa.** Se for o primeiro acesso do dia, ele pede para abrir. Informe o dinheiro
   que já está na gaveta e clique em **Abrir o caixa de hoje**.
2. No quadro **Lançar**, preencha:
   - **Natureza** — em geral *Recebimento de ato*
   - **Forma de pagamento** — dinheiro, PIX, cartão…
   - **Valor**
   - **Pagador** e **CPF/CNPJ** — é o nome que sai no recibo
   - **Protocolo** — opcional; se informar, o recibo cita o número
   - **Descrição** — o que o cliente está pagando
3. Clique em **Lançar**. O sistema devolve *"Lançamento nº 12/2026 — R$ 250,00"*.
   Esse número é a ordem do lançamento no ano, e é por ele que se cita depois.
4. Na linha do lançamento, clique em **emitir recibo**. O arquivo `.odt` baixa na hora, pronto
   para imprimir ou enviar.

**Emitir recibo** só aparece uma vez. Depois, o botão vira **recibo** e reabre a mesma via —
idêntica, porque o teor fica congelado na emissão. Segunda via não é recibo novo.

### O que sai no recibo

Nome e documento do pagador, o valor em algarismos **e por extenso**, o protocolo (se houver),
o número do lançamento, a forma de pagamento, a data e a assinatura. No rodapé, um resumo
criptográfico — é o que permite provar que a via reimpressa é a mesma.

**A linha de composição — emolumentos, FERC, FADEP, FEMP, FERRFIS — só aparece se você
preencher esses campos.** Eles ficam em *Detalhar emolumentos e fundos (opcional)*, recolhidos.
O protocolo do caixa é de controle e recibo: não gera selo. Preencha só quando o ato foi
efetivamente selado e você quiser a composição no documento.

---

## Depósito prévio

**Menu → Depósito prévio.**

**Receber:** informe depositante, valor e forma de pagamento. O depósito entra como **entrada no
caixa do dia** — é dinheiro que chegou à gaveta.

**Usar:** na linha do depósito, informe o valor a consumir e, se quiser, o protocolo. O saldo
cai. Quando chega a zero, o depósito se encerra sozinho.

**Devolver:** informe o motivo. O saldo sai como **saída de caixa**, porque agora o dinheiro
está saindo mesmo.

> **Consumir depósito não é entrada nova.** O valor entrou quando foi depositado; o uso é
> lançado só para deixar rastro do que foi consumido e em qual protocolo. Se contasse duas
> vezes, o caixa fecharia com dinheiro que não existe.

O saldo é sempre recalculado a partir do que entrou menos o que foi usado. Não é um número
guardado que alguém edita.

---

## Alterar e excluir lançamento

Enquanto **o caixa estiver aberto**:

- **alterar** — abre o formulário na própria linha. O valor anterior fica guardado no histórico
  do lançamento, e a linha passa a exibir a marca *editado*.
- **excluir** — pede o motivo. O lançamento **sai das contas e do saldo**, a linha fica marcada
  como *excluída* com o motivo à vista.

**O registro não é apagado do banco, e isso é de propósito.** Um caixa em que a linha some sem
deixar rastro não se explica em correição — a pergunta "o que havia aqui?" não tem resposta.
Excluído sai da conta; apagado sai da história. Se você precisar mesmo do apagamento físico,
me diga e eu mudo.

**Com o caixa já fechado**, alterar e excluir ficam bloqueados. A correção passa a ser por
**estorno**: outro lançamento que anula o primeiro, com motivo. Os dois continuam visíveis.

Lançamento com **recibo emitido** não se exclui: o cliente tem uma via na mão. Cancele o recibo
primeiro.

---

## Fechar o caixa

No fim do expediente, conte o dinheiro e informe em **Contado**.

O sistema mostra o **esperado em espécie** — saldo inicial + entradas em dinheiro − saídas.
PIX e cartão entram no saldo do dia, mas **não** no esperado da gaveta: não se confere cartão
contando cédula.

Havendo diferença, a justificativa passa a ser obrigatória. O sistema guarda **o contado ao
lado do esperado**; não ajusta um para bater com o outro.

---

## Protocolo geral

**Menu → Protocolo geral.** É o número que acompanha o serviço do balcão até a entrega, em todas
as atribuições. Não confundir com a **prenotação** do Registro de Imóveis, que é o Livro 1 e tem
prazo e efeito próprios.

**Abrir:** o formulário no topo pede interessado, CPF/CNPJ, **telefone**, **e-mail**, atribuição,
previsão de entrega e assunto. O número segue o padrão do E-Ofício — `2026.08.147`.

Telefone e e-mail aparecem na lista e na ficha do protocolo, e podem ser corrigidos a qualquer
tempo em **Corrigir contato** — dado de contato não é ato, muda mesmo.

---

## Antes de tudo: trazer o movimento do E-Ofício

**Ainda não foi feito.** O banco tem as tabelas do caixa, mas está sem os protocolos: por isso
você não encontrou os registros.

**Menu → Trazer caixa do E-Ofício → Importar.** A carga leva poucos segundos e traz:

| | |
|---|---|
| Protocolos | 21.342, de 19/03/2020 a 14/08/2026 |
| Custas lançadas | 32.393 |
| Movimentos de caixa | 18.385, em 2.755 caixas |
| Entradas | R$ 1.661.724,25 |
| Saídas | R$ 25.070,97 |
| Em quarentena | 192, com o motivo |

Dos protocolos, **640 continuam em aberto** — 250 do RI, 226 do RCPN, 101 de firmas. São esses
os títulos a dar continuidade.

A carga roda em transação única e faz cópia de segurança do banco antes de começar.
