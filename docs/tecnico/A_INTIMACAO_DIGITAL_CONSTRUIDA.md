# A Intimação Digital — a segunda API da CENPROT

> «a api da cenprot tbm cobre intimacoes pela resolve?»
> «veja aqui: https://docs.resolve.cenprot.org.br/v1110/resolve»
> «se conseguir a api com tudo integrado e funcionando, pode empacotar»
>                                             — o oficial, 03/09/2026

## A pergunta dele separou duas APIs que eu tratava como uma

**Não, a API que já estava integrada não cobre intimação.** Medido no
`swagger.yaml` v2.1.0 da «API Cenprot Cartório»: **zero ocorrências** de
«intima», «14.711», «negocial» ou «notifica». Os oito assuntos dela são
autenticação, anuência, cancelamento, certidão, renegociação, endereço, pedidos
de protesto e custas.

A intimação eletrônica é **outro produto, com contrato próprio**:

| | |
|---|---|
| nome | **Resolve — API para gerenciar intimações e apontamentos** |
| versão | **1.11.0**, OpenAPI **3.1.1** |
| caminhos | **16** |
| ambientes | **três** — testes, homologação e produção |
| autenticação | **`x-api-key`** no cabeçalho |

Guardado em `FONTES_EXTERNAS/cra21/resolve_intimacao_openapi_v1.11.0.json`, e
os testes o abrem.

**O comunicado de 2024 previa isto, e por isso quase se perdeu.** Ele dizia que
«outros serviços serão disponibilizados nessa API futuramente, conforme os
serviços da Lei 14.711 forem sendo implementados (intimação eletrônica...)».
Quem lesse só aquele parágrafo concluiria que não existe. **Existe, em outro
endereço — e quem o trouxe foi o oficial.**

## O que isto vale para esta casa

Medido no acervo:

| | |
|---|---|
| títulos intimados **por edital** | **1.115** |
| intimados **em mãos** | **61** |
| não-entregas que dizem «Ausente» | 1.068 de 1.139 |

**O edital aqui é a rotina, não a exceção** — e é exatamente o caso que a
intimação eletrônica ataca. No material da própria CENPROT, a intimação física
custa R$ 20 por unidade e a digital R$ 1,89 por entrega.

## Os três ambientes respondem — medido, e não suposto

```
TESTES       https://api-testes.resolve.cenprot.org.br/intimacao    200 OK
HOMOLOGACAO  https://api-homolog.resolve.cenprot.org.br/intimacao   200 OK
PRODUCAO     https://api.resolve.cenprot.org.br/intimacao           200 OK
```

Certificado válido nos três, cadeia validando sozinha. O `/api/status` é o
**único caminho sem chave**, e é por isso que ele responde «a internet e o
endereço estão bons» antes de haver credencial nenhuma.

**Esta é a primeira Central da casa com ambiente de testes declarado**, e
`centrais_cred.TESTES` nasceu por causa dela — encaixá-la nos dois de sempre
faria perder o ambiente onde se experimenta, ou usar homologação achando que é
teste. **E o padrão da tela é TESTES**, que é o contrário de começar na produção
por omissão.

## O que ficou construído

| | |
|---|---|
| `resolve_api.py` | o transporte — 16 caminhos, a chave, os limites do contrato |
| `rs_schema.py` | `rs_intimacoes` — **uma linha por intimação, e não por título** |
| `resolve_intimacao.py` | a ponte do título, quem pode ir, o envio e o acompanhamento |
| `resolve_web.py` | 9 rotas: a lista, o envio, a ficha, o histórico, o PDF e os avisos |
| menu | **Protesto → Intimação Digital** |
| testes | **58**, e os que mais valem abrem o contrato |

## O que a casa NÃO faz aqui, e está escrito na tela

**Isto não lavra a intimação no livro.** O que a plataforma chama de `INTIMADO`
é a ciência do devedor; a intimação que faz o protesto poder sair continua sendo
o ato lavrado na ficha do título, com selo, custas e lugar no livro.

É a regra do CNIB pela sexta vez neste projeto: **avisar e preparar; quem
assina decide.**

## O defeito mais caro que os testes guardam

**A conversão de centavos.** A casa guarda `valor_centavos` como inteiro; a
Central quer reais com duas casas (`2255.39`). Mandar o inteiro faria a
intimação **cobrar cem vezes o valor** — escrito, com o nome desta serventia em
cima, na casa do devedor.

## O segundo: o título sustado

O § 1º do art. 17 da Lei 9.492/1997 diz que o título sustado só se paga,
protesta ou retira com autorização judicial, e `protesto` já recusa os três.
**Mensageria correndo sobre ele cobraria justamente quem o juiz mandou parar** —
pelo caminho que não passa por nenhuma daquelas guardas. `SITUACOES_QUE_NAO_VAO`
o exclui, com pago, retirado, protestado, cancelado e desistido.

## O que a Central sabe e a casa precisa dizer a ela

Três avisos, e cada um existe porque o fato aconteceu **aqui**:

- **pago** — o devedor pagou no balcão; sem isto ela continua cobrando quem já
  pagou;
- **intimado** — a intimação aconteceu fora dela, em mãos ou por edital; sem
  isto ela segue mandando mensagem a quem já foi intimado;
- **cancelada** — o título foi retirado, desistido ou sustado.

Nenhum deles lava ato: são avisos a quem está mandando as mensagens.

## E a prova de que se tentou

O histórico devolve, por tentativa, o canal, o destinatário, a data e uma
**assinatura HMAC**; e há o PDF do comprovante. **É o que se lê quando alguém
perguntar por que o título foi a edital** — e é a razão de a ficha ter os dois
botões.

**O PDF não se guarda no banco**: a Central devolve uma URL, e o banco viaja no
backup.

## O que os testes acharam

**Três caminhos do contrato não declaram a chave** — `/api/status`,
`/api/reports` e `/api/simulate/message-webhook`. Do status é verdade (medido).
Dos outros dois é quase certo que não: relatório de pagamentos do cartório não é
público. É o mesmo caso da ONRTDPJ, cujo contrato «declara o esquema de
segurança e não o aplica a operação nenhuma». **O módulo manda a chave nos
dois**, que é o seguro.

**E o varredor de função órfã pegou oito de uma vez.** Seis ganharam tela (a
ficha nasceu daí); **duas foram apagadas**:

- `cancelar_lote` desfaz um lote **inteiro** — até duas mil intimações num
  clique. O que o balcão precisa é cancelar uma.
- `link_de_pagamento` só serve a quem tem link próprio habilitado na conta, e
  esta casa não tem essa configuração.

Os caminhos ficam declarados, **para ninguém os reinventar achando que
sumiram** — o mesmo que se fez com os legados da CENPROT.

## O que falta, e não é código

**1. A adesão.** É pelo site: `pesquisaprotesto.com.br` → entrar → menu lateral
**SSO – Resolve** → **Adesão – Intimação Digital** → escolher o plano.

**2. A chave.** Depois da adesão, a plataforma entrega a `x-api-key`. Ela se
cadastra em *Administrativo → Configurações*, na tabela das Centrais — há três
linhas da Resolve, uma por ambiente. **Não me mande a chave**: ela é digitada
por você e gravada em `%PROGRAMDATA%\CartorioGestao\resolve.cred`, fora do banco.

**3. A chave de 23 dígitos dos títulos.** Medido em 03/09/2026:
`pt_titulos.chave_cenprot` está **vazia em 1.366 de 1.366**, e o contrato a
exige (`nrChave`). Ela vem do XML diário do CENPROT, e a tela *Chave do CENPROT*
já sabe gravá-la.

**Enquanto o XML não for carregado, nenhum título pode ser intimado por aqui** —
e a tela diz isso com todas as letras, em vez de mostrar uma lista vazia que faz
o operador achar que quebrou.
