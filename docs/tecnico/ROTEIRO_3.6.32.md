# Roteiro da 3.6.32 — o controle geral sobre os modelos

**Arquivo:** `CartorioGestao_3.6.32.cgu`
**SHA-256:** `0bff90e1feeed0d91a4bff3c75feb051a068ee4bb7e92e11054019465d42257b`
**Testes:** 2.641 passaram, 8 puladas.

Esta versão responde ao **relato #28**, que era o maior aberto na lista:

> «preciso de mais controle sobre os modelos de todos os atos, de todas
> atribuições. preciso ter controle geral sobre os modelos, em especial os
> cabeçalhos padrão de cada atribuição e ato, corpo, encerramento, eventual
> notas de rodapé»

---

## O que muda no seu dia

Havia **dois lugares** para editar modelo, os dois dentro do Registro de
Imóveis, e **cinco papéis que a casa emite sem que houvesse onde mexer neles**:
o recibo, o orçamento e o comprovante de recepção do caixa, o traslado das notas
e o comprovante de prenotação. Para mudar uma vírgula em qualquer um desses
cinco era preciso mexer no programa.

Agora é **uma tela só**, com os nove papéis:

**Administrativo → Configuração → Modelos dos documentos**

*(a entrada «Modelos de documento» do Registro de Imóveis leva para a mesma
tela — os quatro papéis do RI estão lá dentro, junto dos outros cinco)*

| Atribuição | Papéis |
|---|---|
| Registro de Imóveis | cabeçalho, ficha da matrícula, certidão, nota devolutiva, comprovante de prenotação |
| Caixa e protocolo | recibo, orçamento, comprovante de recepção |
| Tabelionato de Notas | traslado |

---

## O que você precisa saber antes de editar

**O padrão não se perde.** O modelo de fábrica mora no programa, e não no banco.
O que você grava é um *ajuste* por cima dele — e por isso o botão **«Voltar ao
padrão do sistema»** funciona sempre, mesmo daqui a três anos, sem depender de
alguém ter guardado o texto antigo em algum lugar.

**A tela diz de onde cada papel sai hoje.** «padrão do sistema» ou «ajustado por
esta casa». Os dois parecem a mesma coisa enquanto o texto for igual — e deixam
de ser no dia em que uma versão nova melhorar o padrão: **o ajustado não
acompanha**, de propósito, porque o ajuste é seu.

**O que está entre `{{` e `}}` é preenchido pelo sistema** na hora de emitir — o
nome, a data, o número do ato. Apagar um desses tira aquela informação do papel.

**O sistema recusa gravar modelo quebrado.** Ao clicar em gravar, ele monta o
modelo e, se não montar, avisa e **não grava** — porque o lugar de descobrir
isso é aqui, e não no balcão com o cliente na frente.

Nos quatro papéis do Registro de Imóveis a conferência é **contra uma matrícula
de verdade** do seu acervo, o que é mais rigoroso: pega campo que só aparece em
ficha com ato, com ônus, com parte.

---

## Os passos

1. **Faça o backup**, como sempre, antes de atualizar.
2. Rode `ATUALIZAR_SISTEMA.cmd`.
3. Confira em *Administrativo → Atualizações* que diz **3.6.32**.
4. Abra *Administrativo → Modelos dos documentos*. Ela deve listar **nove
   papéis**, todos dizendo «padrão do sistema» — nenhum ajuste foi feito ainda,
   e é assim que deve estar.
5. **Não é preciso fazer mais nada.** Nada muda na aparência dos papéis: sem
   ajuste gravado, cada um continua saindo exatamente como saía antes. A tela
   está lá para quando você quiser mexer.

---

## Três coisas que a construção achou, e você deve saber

**A etiqueta do selo não entrou na lista, e é de propósito.** Havia no código
uma coisa chamada `MODELO_PADRAO` nas notas — mas ela não é modelo de papel: é
o **endereço que vai dentro do QR do selo**, escrito noutra linguagem. Se
entrasse ali, a conferência aprovaria um texto que o QR não sabe montar. Ela
continua onde estava, em *Ajustar etiqueta*.

**A tela antiga do RI foi removida, e não desligada.** Ela editava uma tabela
que agora é só histórico: com um ajuste gravado na tela nova, **o que você
editasse lá não teria efeito nenhum e não haveria como descobrir por quê**. Ela
leva para a tela geral, com um aviso. Se você já tivesse algum modelo gravado
por ela, ele **continua valendo** — nada se perdeu.

**O que ela tinha de melhor ficou.** A conferência contra matrícula real era
dela, e passou para a tela geral.

---

## O que continua pendente, e não é trabalho meu

Sem mudança nesta versão, mas repetido aqui para não se perder:

- **A carga do acervo ainda não rodou** — *Livros e acervo → Trazer o acervo do
  E-Ofício*. Enquanto ela não rodar, Protesto, RCPN, RCPJ/RTD e Livro 3 estão
  de pé e vazios, e **nenhum contador foi semeado**.
- **Os quatro cliques da configuração do selador**, que são seus.
- **A senha do selador**, com a FPFTech ou o TJMA.
- **Perguntar à FPFTech** se o selador devolve o token dos selos novos — é o que
  falta para o QR apontar para o próprio selo (relato #16).
- **O certificado do selador venceu em 10/11/2025.** Não impede de selar; você
  pediu para ser lembrado quando tudo estivesse rodando.
