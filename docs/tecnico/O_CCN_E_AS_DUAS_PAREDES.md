# O CCN do e-Notariado — o item 4, e por que ele não foi construído

> «siga no desenvolvimento das integrações até terminar de todas, sem minha
> intervenção» — o oficial, 03/09/2026.

**Este é o item que termina com «não dá», e as duas razões estão medidas.**
Terminar uma integração é medir até o fim; construir um transporte que não pode
funcionar seria pior que não construir, porque a tela diria que dá.

---

## 1. O que o CCN é

O **Cadastro Único de Clientes do Notariado** — a base nacional de pessoas do
Provimento CNJ 149/2023, com dados biográficos, biométricos e documentos.
**Não é lavratura de ato**: é o cadastro que o Tabelionato alimenta e consulta.

| | |
|---|---|
| contrato | OpenAPI **3.0.1** · «Pessoas **2.91.0 RTM**» |
| tamanho | **10 caminhos**, **11 operações**, 32 esquemas |
| `servers` | **nulo** |
| homologação | `pessoas-hml.e-notariado.org.br` |
| produção | `pessoas.e-notariado.org.br` |
| autenticação | `X-Api-Key` **ou** `Authorization: AppToken <chave>`, mais o `X-Subscription` da documentação |

**Nove das onze operações não declaram segurança nenhuma** — o quarto contrato
de Central seguido assim, depois da ONRTDPJ, da CENPROT e do ONR. A leitura é a
mesma: **omissão do contrato, e não caminho aberto.**

---

## 2. A primeira parede: o host inteiro está atrás da Cloudflare

Medido em 04/09/2026, **na rota da API** — e não só no swagger:

```
GET https://pessoas-hml.e-notariado.org.br/api/imports
GET https://pessoas.e-notariado.org.br/api/imports

    HTTP 403
    Server: cloudflare
    Cf-Mitigated: challenge
    corpo: «Just a moment...»
```

| como | resposta |
|---|---|
| cliente do sistema (`http.client`) | **403 · challenge** |
| o mesmo com **cabeçalho de navegador completo** — UA do Chrome, `Sec-Fetch-*`, `Accept-Language`, `Upgrade-Insecure-Requests` | **403 · challenge** |
| **de dentro de um navegador** | **200** |

**Não é questão de cabeçalho.** O desafio da Cloudflare exige executar
JavaScript, e um cliente servidor-a-servidor — que é o que uma integração de
cartório é — bate nela **antes de qualquer credencial**.

> A medição anterior (03/09) já tinha visto isso **no swagger**, e declarou que
> a pergunta a responder era se as **rotas da API** se comportavam igual.
> **Comportam.** Foi essa pergunta declarada que fez a medição de hoje ser
> curta.

---

## 3. A segunda parede: o `X-Signature` é uma assinatura CAdES por requisição

As duas operações de **exportação** — as que buscam a pessoa pelo CPF — exigem
o cabeçalho `X-Signature`, e o contrato diz o que ele é:

> «The Base64 **CAdES Signature** of
> `{"Timestamp":"2026-09-04T04:58:42Z","RequestPath":"/api/exports/record-sets/{cpf}"}`»

Assinar em CAdES **exige a chave privada**, e a desta serventia é o **A3 do
delegatário**. E `assinatura_digital.py` já traz a medição que fecha o assunto:

> os dois drivers PKCS#11 desta máquina — `eTPKCS11.dll` e
> `IDPrimePKCS1164.dll` — dão **segmentation fault** ao carregar, **código de
> saída 139**, antes de qualquer saída. **Segfault não se trata com
> `try/except`**: mata o processo. Um Flask que os carregue derruba **o balcão
> inteiro** — não uma tela: o sistema.

**Logo a metade de exportação do CCN é impossível aqui por construção**, e não
por falta de credencial.

---

## 4. O que isso deixa de pé

| | |
|---|---|
| **exportação** — 2 operações | **impossível**: CAdES por requisição, e o A3 não entra no processo |
| **importação e upload** — 9 operações | **seria construível** (não pedem `X-Signature`) **se a Cloudflare deixasse** |

Nove das onze são a metade que interessa ao balcão — subir o cadastro das
pessoas que a casa atende. **Elas dependem de uma coisa só, e ela não está nas
nossas mãos.**

---

## 5. O que pedir ao e-Notariado

1. **Liberar o acesso servidor-a-servidor** ao host da API para esta serventia
   — por IP fixo, por chave, ou por um host de API sem o desafio da Cloudflare.
   **Sem isso nenhuma integração de cartório funciona**, e é pedido normal de
   quem consome uma API.
2. **O XSD** do arquivo de importação, que a documentação cita e o contrato não
   publica.
3. **Como assinar o `X-Signature`** quando a serventia usa **A3** — ou se há
   caminho que dispense a assinatura por requisição.

---

## 6. Por que não se construiu um transporte «pronto para quando liberarem»

Porque ele teria de ter uma tela, e a tela diria ao escrevente que existe um
caminho que **não existe**. Este projeto tem uma regra para isso, paga mais de
dez vezes: **função pronta que nenhuma tela chama é a arma que alguém religa
depois**; e a versão pior dela é a tela que promete o que o sistema não faz.

O que fica, e é o que serve, é a **medição**: os dez caminhos, as duas formas de
autenticação, os dois ambientes, o `X-Signature` e as duas paredes — tudo em
`FONTES_EXTERNAS/enotariado/LEIA-ME.md`. **No dia em que a primeira cair, o
trabalho começa do contrato lido, e não do zero.**

---

## 7. E o resto do e-Notariado

O CCN é uma parte. Há também o **CENSEC** — que este sistema já trata em
`notas_censec.py`, pelo formato de arquivo — e o **CNB-CF**. **Não se mediu
contrato de nenhum dos dois**, e nada se afirma sobre eles.
