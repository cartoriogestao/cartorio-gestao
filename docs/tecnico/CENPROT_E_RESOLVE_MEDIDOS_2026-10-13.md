# CENPROT e Resolve — o que a produção e a homologação mostraram (13/10/2026)

Pedido do oficial: «antes de atualizar, vamos desenvolver resolve e cenprot». Tudo
abaixo foi medido contra as Centrais de verdade; as correções estão no SANDBOX, com
teste, e vão no próximo pacote.

## CENPROT — API do cartório (anuências, certidões, cancelamentos)

**Produção.** A credencial do oficial autentica. A leitura (só consulta, rodada por
ele com `tmp\cenprot_leitura_producao\RODAR_LEITURA_CENPROT.cmd`) achou **3 anuências
pendentes**, aprovadas pelo credor, as três casando com títulos PROTESTADOS da casa;
certidões, cancelamentos, renegociações, decisões judiciais e pedidos de protesto:
vazios. As respostas cruas ficam em
`%PROGRAMDATA%\CartorioGestao\arquivos\cenprot_producao_20261013` (têm dado de devedor).

| anuência | situação | protocolo | cotação (custa de cancelamento, tabela vigente) |
|---|---|---|---|
| 28961230 | código 2 | 2501070004 | R$ 407,67 |
| 28956854 | código 8 — «Aguardando Solicitação de Cotação» | 2312050001 | R$ 633,69 |
| 28655422 | código 2 | 2607290002 | R$ 319,54 |

O **código 2 não está no contrato** (ele só descreve 1 e 8). A CONFERIR no portal.
Ordem do oficial: as três entram no banco e são respondidas pela tabela quando a nova
versão estiver em funcionamento na produção.

**Os defeitos que a produção mostrou, e o conserto:**

1. **O token vem em `token`, e não em `access_token`** (o nome do contrato). A
   autenticação certa virava falha — e a mensagem de falha imprimia o token.
   `cenprot_api._pedir_token` lê os dois e não ecoa mais a resposta.
2. **Nas listas, 404 quer dizer «nenhum encontrado»** (o contrato diz isso em cada
   uma). O sistema o tratava como recusa; o balcão veria erro onde não há nada a
   fazer. `LISTAS_QUE_RESPONDEM_404_QUANDO_VAZIAS` — pedido de UM item continua 404.
3. **As anuências exigem `data_inicio` e `data_fim`** (422 na produção), embora o
   contrato as chame de opcionais. A recusa passou para o balcão, como no cancelamento.
4. **A resposta da anuência lia o teor só no primeiro nível**, e a Central manda tudo
   dentro de `dados_anuencia`: o corpo sairia sem os onze campos exigidos de volta, e
   nenhuma anuência se responderia pela tela. Agora `_procurar`, em qualquer nível.
5. **A anuência vem cotada pela custa de cancelamento da casa** — antes o campo vinha
   em branco. É sugestão, e a tela diz de onde veio.
6. A linha da CENPROT na tabela de credenciais deixou de se chamar «API Resolve»
   (pedido do oficial: «Resolve» é a Intimação Digital).

**Homologação:** a credencial de homologação é recusada (o oficial trocou só a de
produção).

## Resolve — Intimação Digital (homologação)

A chave autentica. **Um lote de teste foi aceito** («Lote de intimações criado»,
lote `6ace66220f142649b027e34b`, intimação `6ace66220f142649b027e358`), com a própria
serventia como credor e devedor e o telefone e o e-mail que o oficial deu. Às 14h17 a
intimação estava **ENRIQUECIDO**, sem mensagem disparada; prazo da esteira 16/10.
O que foi mandado e o que voltou: `tmp\resolve_teste_homologacao\`.

**O que a Central recusou antes de aceitar, e o conserto:**

1. **`tipoDocumento` só existe no devedor** — no credor a Central recusa o lote
   inteiro (`whitelistValidation`). `resolve_intimacao._pessoa(com_tipo=…)`.
2. **O apresentante exige nome E documento**, e a casa não tem o documento dele (a
   remessa da CRA traz código e nome). Ele é opcional no lote: agora vai inteiro, ou
   não vai. A conferência local passou a recusar pessoa sem documento.
3. **A recusa da Central diz o campo em `errors`**, e o sistema mostrava só «Body
   inválido». Agora a frase leva o item e o campo.

**O que fica declarado:** o sistema **não manda contato** (telefone, e-mail) do
devedor — a casa não os tem, e a Central marca contatos de origem «RESOLVE»: ela
enriquece pela base dela. Se o enriquecimento acha o devedor real na produção, só a
produção dirá.

## O caminho do contrato, no sistema (ordem do oficial: «vamos seguir o caminho do contrato»)

**Quem anui é o credor; quem pede o cancelamento é o interessado, e é quem paga**
(Lei 9.492/1997, art. 26). Nas 3 anuências reais, quem pediu não é o devedor nem o
credor — é um terceiro (dois CNPJ, um CPF). **Responder à anuência não baixa o
protesto**: diz só «aprovo» e «quanto custa cancelar».

| passo | onde | o que o sistema faz |
|---|---|---|
| 1. a anuência chega | Protesto → pendências da CENPROT | baixa (datas obrigatórias) e casa com o título |
| 2. a casa cota | a ficha da pendência | o valor vem sugerido pela **custa de cancelamento** da tabela; o oficial confere e envia |
| 3. o pedido de cancelamento chega | a mesma lista | mostra a anuência, o status e os **emolumentos que vieram no pedido**, ao lado da cotação da tabela, e um botão para a ficha do título **já preparada** (hipótese «Anuência do credor» e o fundamento com os números do pedido) |
| 4. a casa lavra | a ficha do título | o cancelamento se lavra ali, com os emolumentos pagos — a tela da CENPROT não lavra nada |
| 5. a casa informa a Central | a ficha da pendência | **o sistema recusa informar antes de o título estar CANCELADO no livro** |

**O que o contrato não diz, e fica A CONFERIR com a CENPROT/IEPTB-MA:** onde o
interessado paga (na plataforma ou no balcão) e o que é o código de situação 2 da
anuência.
