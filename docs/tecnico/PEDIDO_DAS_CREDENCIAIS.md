# O pedido das credenciais — o que falta, a quem, e o nome exato de cada campo

**Medido em 18/09/2026, por causa do problema #54.** O que este documento responde
é a pergunta que sobrou dele: *quais credenciais faltam, de quem se pede, e com que
nome se pede cada campo.*

**Nada no código foi tocado para escrevê-lo.** O que se fez foi ler
`centrais_cred.py` (o quadro das credenciais), `templates/settings.html` (os rótulos
que a tela escreve), os quatro módulos de transporte que nomeiam os campos
(`onr_api.py`, `onrcpn_api.py`, `resolve_api.py`, `cra21_api.py`), e a documentação
que já estava na casa.

---

## O quadro de agora

`centrais_cred.situacao()` devolve **12 linhas** — cada Central com cada ambiente
que ela declara. **Quatro estão informadas; oito estão em branco:**

| Central | Ambiente | Estado |
|---|---|---|
| CRA | HOMOLOGACAO | **informada** |
| CRA | PRODUCAO | — |
| CENPROT | HOMOLOGACAO | **informada** |
| CENPROT | PRODUCAO | — |
| ONRTDPJ | PRODUCAO | **informada** |
| ONR | HOMOLOGACAO | — |
| ONR | PRODUCAO | — |
| ON-RCPN | HOMOLOGACAO | — |
| RESOLVE | TESTES | — |
| RESOLVE | HOMOLOGACAO | — |
| RESOLVE | PRODUCAO | — |
| SIRC | PRODUCAO | **informada** |

**São cinco pedidos, e não oito** — três deles são a mesma credencial em mais de um
ambiente, e um se pede junto com outro na mesma mensagem.

> **Os nomes das credenciais já existentes não se escrevem aqui de propósito.** O
> quadro acima é o que se mede sem abrir arquivo nenhum; repetir usuário e senha num
> documento que circula é a única forma de este papel virar risco.

### E a medição corrigiu uma linha do roteiro

O `AS_APIS_DAS_SEIS_ATRIBUICOES.md` diz que o **ONRTDPJ** está «medido e por
construir, falta só informar a credencial». **A credencial já está informada** —
medido agora. O que falta ali é outra coisa (usar a Central para os títulos
eletrônicos), e essa é decisão dele, não credencial.

**Lista de pendência que envelhece faz planejar trabalho já feito** — é a regra que
este projeto já pagou cinco vezes, e desta vez quem a pagou foi o próprio roteiro.

---

## 1. ONR — o par (`client_id` + `client secret`)

**O que pedir** — as duas metades do par, com os nomes que a própria Central usa.
Não é usuário e senha, e pedir «usuário» faz quem atende procurar um campo que não
existe lá.

| o campo, como a tela o chama | o que é |
|---|---|
| `client_id` | a identificação da serventia na Central |
| `client secret` | o segredo, que só ela devolve |

**A quem** — ao **ONR**, no mesmo processo de adesão (o Next Cloud SAS). A
correspondência é a do formulário:

- **formulário**: `FONTES_EXTERNAS/onr_nextcloud/formulario_solicitacao_backup.pdf`
  — 7 páginas, versão 2.0, **assinado com ICP-Brasil**;
- **para**: `integrar-onr@onr.org.br`;
- **assunto**: «Opção 2 – Cartório de Registro de Imóveis de Cidade Exemplo/MA».

**Ambientes** — os **dois**, e os endereços são do contrato dele:

| | |
|---|---|
| produção | `https://api.registrodeimoveis.org.br` |
| testes | `https://testes-api.registrodeimoveis.org.br` |

**O que o sistema faz com ele** — `POST /v1/auth/token`, corpo
`application/x-www-form-urlencoded`, com `client_id`, `client_secret` e
`grant_type=client_credentials`. A Central devolve `access_token` com `expires_in`,
e o sistema renova sozinho.

> **É por isso que aqui se guarda o PAR, e não o token** — e é a diferença que
> separa o ONR do ON-RCPN: lá o cadastro também devolve um par, e o endereço que o
> troca por token **não está medido** (os dois contratos citam um `/api/auth` que
> responde 404 nos dois hosts da API). Enquanto for assim, o ON-RCPN guarda o token
> que alguém colou; o ONR guarda o par e mina o token sozinho.

**O que só o oficial tem, e o formulário cobra** — técnico de informática a quem o
ONR liga na carga inicial e no erro de atualização, nome e IP do servidor, IP
externo, velocidade e tipo do link, e a **liberação da rota de backup no firewall**
(que é providência, e não papel). Mais a conta do Google —
`conta.google@exemplo.invalid` — que **não é o e-mail de contato da serventia**.

### A pergunta que vem ANTES de assinar

O formulário de adesão é uma **declaração assinada**, e não um cadastro: na página
5 ele afirma, sob assinatura ICP-Brasil, que o Indicador Pessoal está com a base
completa desde 1º/01/1976 e que a serventia possui **todas** as matrículas
digitalizadas do Livro 2.

**Nenhuma das duas se marca com verdade hoje:** são **74 de 1.701** matrículas sem
uma única imagem e **2.819 de 3.992** pessoas sem CPF/CNPJ. E a outra via — a
declaração de inexistência — também não serve: ela diz «não possui», e a casa
**tem** as duas bases, incompletas.

**A situação desta casa não é nenhuma das duas, e escolher o papel mais parecido
seria afirmar o que não é verdade.** A pergunta ao ONR vem primeiro; a assinatura,
depois da resposta. A regra é a do CNIB: a máquina prepara, e quem responde é quem
assina.

**Onde se digita** — Administrativo → Configurações → «Centrais — credenciais das
APIs», linha do **ONR**, nas duas caixas `client_id` e `client secret`.

**Onde fica** — `%PROGRAMDATA%\CartorioGestao\onr.cred`, **fora do banco** — o banco
viaja no backup, e o backup já saiu da serventia.

---

## 2. ON-RCPN — o token do IdRC

**O que pedir** — **um** token, o **IdRC**, que serve **as duas APIs** do ON-RCPN: o
e-Proclamas (o edital) e a Certidão Eletrônica. É um pedido, e não dois — está
escrito na nota do próprio contrato.

**O campo na tela** é um só, e se chama **«token da Central»** (a forma desta
Central é `TOKEN`, e não par).

**A quem, e como** — o cadastro se abre em:

```
home.registrocivil.org.br/solicitacao-novo-client
```

Dois cuidados, e os dois são da Central:

1. **No campo «Ambiente de criação», a opção de HOMOLOGAÇÃO.** A Central **não
   deixa começar pela produção**, e o formulário tem um campo obrigatório que se
   responde com o protocolo do *client* de homologação já existente para o mesmo
   projeto. É por isso que este é o pedido de agora, e o de produção é **outro**,
   depois.
2. **Pedir junto, na mesma mensagem**, duas coisas que a casa não tem:
   - o **manual de autenticação do `/api/auth`** — ele é citado e não é declarado
     em contrato nenhum, e é um documento à parte;
   - o **endereço de produção**, que não está publicado. O que está medido é o da
     homologação: `https://servicosh.registrocivil.org.br` (do contrato do
     e-Proclamas).

**O que o sistema faz com ele** — `Authorization: Bearer <token>`.

> **Isto é DERIVADO, e não medido, e a diferença fica dita.** Não há uma chamada
> real desta serventia para conferir: o que há são duas fontes que se apontam — a
> nota do contrato manda usar o modelo das certidões, e o contrato das certidões
> declara `bearer`. Se a Central recusar com **401** tendo o token bom, é a linha
> `PREFIXO_DO_TOKEN` que se olha primeiro.

**Onde se digita** — a mesma tela, linha do **ON-RCPN**, na caixa «token da
Central». **Onde fica** — `%PROGRAMDATA%\CartorioGestao\onrcpn.cred`.

---

## 3. Resolve — a `x-api-key` (a Intimação Digital)

**O que pedir** — uma chave só, que no contrato se chama **`x-api-key`**. Não se
pede usuário: o contrato declara **três** esquemas de autenticação e **as operações
usam um só** (`apiKeyAuth`, em cabeçalho, no nome `x-api-key`). Guardar um par aqui
faria a tela pedir um usuário que a Central não dá.

**Na tela** o campo é «token da Central», como o do ON-RCPN.

**A quem** — à **CENPROT**, **depois** de aderir à Intimação Digital. A Resolve é a
segunda API da CENPROT, com contrato e cadastro próprios, e a chave sai do cadastro
dela.

**Ambientes** — ela é a única das Centrais com **três**, e os três respondem
`200 OK` no `/api/status`:

| | |
|---|---|
| TESTES | `https://api-testes.resolve.cenprot.org.br/intimacao` |
| HOMOLOGACAO | `https://api-homolog.resolve.cenprot.org.br/intimacao` |
| PRODUCAO | `https://api.resolve.cenprot.org.br/intimacao` |

**O sistema começa em TESTES**, e isso é deliberado: é onde se experimenta sem
combinar nada com ninguém.

**Por que este pedido vale, com o número** — **1.115** dos 1.176 títulos desta casa
foram intimados por **edital**, contra **61** em mãos. O edital é a rotina, e não a
exceção: a intimação digital é o caminho moderno dela.

### O que este pedido NÃO resolve, e fica dito antes

**Com a chave em mãos, nenhum título pode ser intimado hoje.** O contrato exige um
`nrChave` de 23 caracteres, e `pt_titulos.chave_cenprot` está **vazia em 1.366 de
1.366** — quem a preenche é a tela «Chave do CENPROT», do XML diário.

**São duas coisas independentes, e a chave da API não substitui a outra.** A tela da
intimação já diz isso com todas as letras, para a lista vazia não parecer defeito.

**Onde se digita** — a mesma tela, linha da **Resolve**. **Onde fica** —
`%PROGRAMDATA%\CartorioGestao\resolve.cred`.

---

## 4. CENPROT — a de PRODUÇÃO

A de homologação já está informada, e é ela que sustenta os **11 dos 16 passos** do
roteiro das Centrais que o sistema cobre.

**O que pedir** — usuário e senha **de produção**, com a exigência que a própria
Central impõe à senha: **8 caracteres ao menos, com maiúscula, minúscula, número e
caractere especial**. Pedir já nessa forma evita o segundo e-mail.

**A quem** — à CENPROT, em **Cadastro → Cadastro do Cartório → «Informações de
Autenticação da API»**. É onde o cadastro da API mora; só o oficial pode fazê-lo.

**O que separa os dois ambientes** é o endereço — produção
`https://wspub.cenprotnacional.org.br/ieptb-cenprot-api-cartorio`, homologação o
mesmo com `-homolog` no fim. **Já há tela para as duas**, e ela pinta o ambiente de
produção em vermelho.

**Onde se digita** — a mesma tela. **Onde fica** —
`%PROGRAMDATA%\CartorioGestao\cenprot.cred`.

---

## 5. CRA — a de produção, e a metade que não é credencial

A de homologação já está informada. Da produção, o caminho é a **P21**, que se
ofereceu em **02/09/2026**, por mensagem (Pessoa Exemplo, P21 Sistemas):

> *«tendo feito a criação da integração com a CRA, basta liberar para eles o usuário
> e senha de homologação. Caso eles queiram títulos de exemplo, podemos enviar
> conforme for solicitado. Podemos liberar um ambiente de teste.»*

**E o pedido tem duas metades, que se pedem juntas.** A credencial sozinha mede o
que a API devolve; **só um título mede o que vai na Confirmação e no Retorno** —
os dois passos **com hora marcada** (11h30 e 14h10) e os dois que dependem do
`userDados`, cujo conteúdo **não está medido**: o manual não o descreve, e o exemplo
em PHP passa um argumento só.

**A ressalva que vale, e é a razão de a frase existir** — se o «ambiente de teste»
oferecido for o sistema **da P21**, e não a homologação **da Central**, ele **não
serve**: o código fala **direto com a Central**, e não passa pela P21.

**Onde se digita** — a mesma tela, linha da **CRA**. **Onde fica** —
`%PROGRAMDATA%\CartorioGestao\cra.cred`.

---

## O que NÃO se pede, e por quê

**O e-Notariado (CCN).** Não é credencial que falta — é transporte que ainda não
pode funcionar, por duas paredes medidas: a **Cloudflare** devolve `403` com
`Cf-Mitigated: challenge` na rota da API (também com cabeçalho de navegador
completo), e o **`X-Signature`** exige uma assinatura **CAdES por requisição**, cuja
chave é o A3 que dá *segfault* no processo do Flask. As duas são anteriores a
qualquer credencial. Ver `O_CCN_E_AS_DUAS_PAREDES.md`.

**A produção do ON-RCPN.** Não é pedido de agora: a Central **não deixa começar por
lá**, e o caminho é o mesmo formulário, num segundo momento.

---

## O que fica A CONFERIR — declarado, e não escondido

1. **Se o par do ONR é um só para os dois ambientes ou um por ambiente.** O contrato
   declara os dois endereços e não diz isso; o sistema guarda **por ambiente**, e
   uma linha em branco aparece no quadro para cada um.
2. **O prefixo do token do ON-RCPN** (`Bearer `) — derivado de duas fontes que se
   apontam, e não medido.
3. **O endereço de produção do ON-RCPN** — não publicado.
4. **O manual do `/api/auth`** do ON-RCPN — citado nos contratos, e os dois hosts
   respondem `404` nele.
5. **Se a Resolve dá uma chave por ambiente ou uma só.** O contrato declara três
   `servers` e não diz; o sistema guarda por ambiente, como as outras.
6. **Qual declaração do ONR assinar** — a casa não é nem «base completa» nem «não
   possui»: é um terceiro caso, e a pergunta é para o ONR.

---

## O silêncio da tela, e ele é meu (achado deste dia)

Na tela das credenciais, **cinco** linhas explicam de onde a credencial vem e o que
ela é. **Duas não** — a do **ON-RCPN** e a da **Resolve** —, e são justamente as
duas de que este documento trata.

Quem tiver a tela aberta com o e-mail da Central na frente vai ter de adivinhar. São
**dois parágrafos**, no mesmo lugar e na mesma forma dos outros cinco.

---

## Depois que chegar, como se confere

**O quadro é 12 linhas, e ele se lê na hora**: na tela, ao lado de cada linha;
ou pela função que o monta, `centrais_cred.situacao()`. Quando as linhas do **ONR**,
do **ON-RCPN** e da **Resolve** deixarem de estar em branco, o pedido chegou.

**Mas a prova não é a linha do quadro** — é a primeira chamada de verdade. Os
painéis que já têm botão de ligação (a CRA, a CENPROT, a ONRTDPJ) existem para
isso, e o da Resolve é o `/api/status`, que respondeu `200` nos três ambientes
medidos.
