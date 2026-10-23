# O e-PROCLAMAS CONSTRUÍDO — o primeiro item do cronograma

**03/09/2026.** Ordem do oficial: *«temos tempo. vamos seguir o cronograma
recomendado»* — e o primeiro item dele era este, pela razão que estava escrita:
é a menor das quatro APIs por construir (**3 caminhos**) e fecha um buraco que
o próprio sistema declarava.

> **`hc_schema`, 28/08/2026:** *«O envio à Central é integração que este
> sistema ainda não tem. Até tê-la, o escrevente publica no e-Proclamas e anota
> aqui o protocolo.»*

Era verdade, e a API existe desde **10/04/2025**.

---

## 1. O QUE PASSOU A EXISTIR

| arquivo | o que é |
|---|---|
| `onrcpn_api.py` | o **transporte** — 3 caminhos, medidos no contrato guardado |
| `proclamas.py` | o **domínio** — monta o proclama do que a casa lavrou, e manda |
| `proclamas_web.py` | a **fila**, a **conferência** e o **envio** |
| `hc_eproclamas` | o que foi mandado e o que voltou, com o teor **congelado** |
| `templates/rcpn_proclamas.html` · `rcpn_proclama.html` | as duas telas |

No menu: **Registro Civil → Casamento → `2b · Enviar ao e-Proclamas`**, colado
na etapa 2 — porque é a metade dela que acontece fora da casa.

**E o caminho manual continua de pé.** `habilitacao.registrar_publicacao` é
quem grava `eproclamas_protocolo` desde 28/08, e continua sendo: é por onde o
escrevente anota o número quando a Central está fora do ar e ele publica pelo
portal. **Dois caminhos escrevendo o mesmo fato divergiriam no primeiro
conserto** — por isso o envio automático chama aquela função em vez de escrever
por conta própria.

---

## 2. A CORRENTE, E POR QUE CADA ELO EXISTE

```
1. o edital publicado aqui        →  dele saem a DATA e o prazo
2. o assento de proclamas (Livro D) →  dele sai a MATRÍCULA de 32 dígitos
3. o envio                        →  grava o que foi e o que voltou
```

**A ordem não se inverte, e a recusa diz em que elo se parou** — porque o
conserto de cada um é num lugar diferente da casa. A da matrícula, por exemplo,
termina com *«Lavre em Registro Civil → Novo assento, espécie «Proclamas», e
amarre-o aqui»*: recusa que não diz onde se conserta manda o escrevente
procurar.

---

## 3. O ACHADO MAIS GRAVE, E FOI O TESTE DO CONTRATO QUE O ACHOU

**Eu escrevi o módulo inteiro tratando HTTP 200 como sucesso.**

Ao medir o contrato, imprimi só a `description` de cada resposta, li **«OK»**, e
concluí que **o corpo não era declarado**. Escrevi isso em três lugares e montei
uma função que procurava um campo `protocolo` «por vários nomes prováveis,
porque o contrato não diz o nome».

**Ele diz.** O esquema da resposta 200 do `enviar` é:

```
{status, message, proclamas: {batchId, success: [...], error: [...]}}
```

**São DUAS LISTAS, por matrícula.** O lote pode voltar **aceito pela metade** —
com 200 —, e cada recusado traz `message`, `details` e uma lista `errors` com
`field` e a frase da Central.

Com a primeira versão, **um proclama recusado seria gravado como publicado**, e
o balcão diria ao casal que o edital saiu quando ele não saiu. É o defeito
calado na sua forma mais cara.

**E não há campo `protocolo` nenhum.** O que a Central devolve é o **`batchId`**
— o número do LOTE, não um protocolo por proclama. Chamá-lo de protocolo seria
batizar o que não se mediu; a casa guarda esse número e a tela diz que é isso.

> **A lição é a que este projeto já tinha, na forma nova: ausência não se
> conclui de uma leitura que só olhou metade do documento.** As sete vezes
> anteriores foram *procurei pelo nome errado*; esta foi *li só um campo do que
> abri*.
>
> **E o que a desfez foi o teste, e não a releitura** — a mesma coisa que
> aconteceu na CENPROT, onde seis defeitos meus só apareceram quando o teste
> abriu o `swagger.yaml`.

O exemplo do próprio contrato mostra que espécie de erro a Central devolve:
*«O campo sexo do genitor cônjuge 2 se encontra inválido. Informar masculino ou
feminino. **Foi informado M**»* — exatamente o que `sexo_para_a_central`
converte.

---

## 4. A MATRÍCULA DO LIVRO D, E A PROCEDÊNCIA QUE FICA À VISTA

`rc_matricula` compunha **seis** tipos de livro — 1 A, 2 B, 3 B-Auxiliar,
4 C, 5 C-Auxiliar, 7 E — e **o `6` era um buraco**. O `LIVRO_DA_ESPECIE` não
tinha `PROCLAMAS`: um assento de proclamas não conseguia ter matrícula.

**O buraco não era esquecimento.** A tabela veio do **guia do SIRC**, e o SIRC
não recebe proclamas — ele recebe nascimento, casamento e óbito. Procurado nos
dois manuais que esta casa guarda (`SIRC_manual.txt`, `CRC_manual.txt`), o
Livro D não aparece em nenhum.

**O que existe é o exemplo do contrato do e-Proclamas.** A matrícula de exemplo
dele — `11111101552025600001102000001541` — traz `6` exatamente na posição do
tipo de livro. É a Central do Registro Civil dizendo, num contrato de
proclamas, com que dígito um proclama se identifica.

**E o exemplo é fabricado, o que precisa ser dito:** o CNS dele é `111111`, que
não existe, e o dígito verificador **não confere** com a regra do Anexo IV (dá
20, e está escrito 41). **Ele não prova a conta; mostra a posição.**

Por isso o `6` entrou **com a procedência marcada** — a decisão do envelope do
selo do civil (`MEDIDO` / `TABELA`) aplicada aqui:

| tipo | livro | de onde veio |
|---|---|---|
| 1, 4 | A, C | **medido nos assentos desta casa** |
| 2, 3, 5, 7 | B, B-Aux, C-Aux, E | guia do SIRC para cartórios |
| **6** | **D** | **exemplo do contrato da API e-Proclamas** |

**A tela mostra isso ao lado da matrícula**, para quem assina ver de onde veio
o dígito antes de assinar. E há teste que fica vermelho se alguém medir o
dígito numa fonte melhor e esquecer de trocar a procedência junto.

> **E a procedência segue o NÚMERO, e não o caminho — correção do mesmo dia.**
> A primeira versão só a mostrava quando a matrícula era *calculada aqui*, e
> devolvia vazio quando ela vinha **gravada no assento**. Só que
> `rc_assento.lavrar_assento` **compõe e grava a matrícula ao lavrar** — logo o
> caso normal é justamente o gravado, e a procedência **nunca apareceria**.
> Lendo o dígito de dentro da matrícula, a resposta é a mesma pelos dois
> caminhos.

---

## 5. O QUE A CENTRAL PEDE E A CASA NÃO TEM — declarado, e não preenchido

### O ENDEREÇO NÃO VAI

A Central quer **seis campos** — `cep`, `logradouro`, `numero`, `complemento`,
`bairro`, `ibge_municipio`. A habilitação guarda **um campo de texto livre**,
`nubente1_endereco`.

Partir esse texto por vírgulas poria «Centro» em `logradouro` numa boa parte
das vezes, e ninguém veria: a Central aceita e o edital sai com o endereço
trocado de casa. **Campo vazio não afirma nada; campo errado afirma** — a regra
que este projeto já aplicou na filiação do segundo cônjuge.

Então ele **não vai**, e a conferência diz isso com todas as letras. **Quando o
oficial quiser que vá, o conserto é na tela da habilitação**, que passa a
perguntar os seis campos.

### A NATURALIDADE VAI QUANDO SE RESOLVE

`hc_habilitacoes.naturalidade` é texto («Cidade Exemplo/MA»); a Central quer os
**7 dígitos do IBGE**. A busca é a de **`ibge_geracao.lugar`** — e não uma
parecida —, com a régua de ambiguidade que ela já tem: **sem UF, só vale se o
nome for único no Brasil**. Há dezenas de «Bom Jesus», e escolher o primeiro
poria o casal no estado errado.

> **E aqui o código antigo ganhou uma linha em vez de uma cópia.** A remessa do
> IBGE quer o município **partido** (`21` e `07001`, em posições diferentes do
> arquivo); o e-Proclamas quer os **sete juntos** (`2198765`). É o mesmo
> município achado pela mesma busca — `lugar()` passou a devolver também o
> `codigo_ibge`, e não há uma segunda função com a mesma consulta dentro.

**Não achar o município NÃO faz o nubente de estrangeiro.** A Central tem
`naturalidade_estrangeiro`, e marcá-la por ausência diria a ela uma coisa que
ninguém apurou — erro de digitação na cidade viraria «nasceu fora do Brasil».

---

## 6. OS DOIS CÔNJUGES SAEM DA HABILITAÇÃO, E NÃO DO ASSENTO

Medido em 03/09/2026: **`rc_assento.PAPEIS_DA_ESPECIE` não tem entrada para
`PROCLAMAS`** — um assento de proclamas não aceita pessoa nenhuma.

**E isso não é defeito a consertar: é o desenho certo.** Os dois nubentes já
moram em `hc_habilitacoes`, em colunas próprias, e é de lá que o edital os
descreve. Repeti-los no assento seriam **dois lugares guardando o mesmo fato**,
que divergem no primeiro conserto.

---

## 7. AS RECUSAS DA CASA, E O QUE ELAS PROTEGEM

| a recusa | o que ela impede |
|---|---|
| sem edital publicado | comunicar um edital que não existe |
| sem assento no Livro D | subir sem matrícula — e o recibo nunca mais é achado |
| sem marcar publicação nem Livro D | **dois booleanos falsos**: a Central aceita e nada acontece |
| publicar duas vezes | **publicação custa e sai no mundo** |
| lote vazio | 200 sem publicar nada |
| CPF de 10 dígitos, data solta, `AMIGADO` no estado civil | dado torto que a Central aceita e escreve errado |

**A do «duas vezes» conta só o MESMO ambiente**: um envio de homologação não
impede a publicação de verdade — travar o balcão por causa de um teste seria o
pior dos dois lados. E o **Livro D Eletrônico continua podendo ir sozinho**
depois de a publicação já ter saído.

**E o vocabulário se confere sem inventar obrigação.** Uma coisa é exigir que um
campo venha preenchido — o contrato **não declara `required` em parâmetro
nenhum**, e inventar obrigação seria o erro do outro lado; outra é conferir que,
**vindo preenchido**, ele traga um dos valores que a nota do contrato lista.
`SOLTEIRO(A)`, que é o que o balcão digita, vira `SOLTEIRO`.

---

## 8. AS ARMADILHAS DO CONTRATO, MEDIDAS

| | |
|---|---|
| **CPF sem pontuação e CEP COM hífen** | na mesma mensagem, com exemplo de cada um na nota |
| **`Bearer` aqui, token CRU na ONRTDPJ** | dois cabeçalhos `Authorization`, dois formatos — copiar um para o outro produz um 401 que não diz por quê |
| **`:matricula`, e não `{matricula}`** | o contrato é escrito no estilo do Express |
| **o `recibo` é PDF base64 *e* HTML** | a descrição diz uma coisa, o esquema exemplifica outra — **e as duas são do mesmo documento** |
| **só há homologação publicada** | `servicos**h**`, `certidao**h**` |

**O `Bearer` é DERIVADO, e não medido, e a diferença fica dita.** O contrato
declara o parâmetro `authorization` como `string` e não diz o formato; a nota
dele manda usar «o mesmo modelo de autenticação adotado no projeto das
certidões», e o contrato das certidões declara `BearerAuth: {scheme: bearer}`.
São duas fontes que se apontam. **Se a Central recusar com 401 tendo token
válido, é `PREFIXO_DO_TOKEN` que se olha primeiro** — é uma linha.

---

## 9. O QUE FALTA, E É DO OFICIAL

1. **O cadastro em `home.registrocivil.org.br/solicitacao-novo-client`**, que
   gera o token IdRC. **Um cadastro serve às duas APIs** do ON-RCPN — o
   e-Proclamas e a Certidão Eletrônica.
2. **O endereço de produção**, que vem com o cadastro. Enquanto não vier, o
   sistema fala com a homologação e **diz isso na tela**.
3. **O `/api/auth`**, citado pelos dois contratos e declarado por nenhum. Este
   módulo **não pede token a ninguém**: usa o que o oficial gravou. Se o IdRC
   devolver um JWT de vida curta, a renovação entra aqui — e o desenho é o de
   `cenprot_api`, que já faz isso.

**E há uma pendência da casa que este trabalho torna concreta:** o Livro D
(`RC_D`) é uma das três séries **sem contador**, declarada em *O que falta
informar* desde 26/08. Sem o próximo número, o primeiro assento de proclamas
nasce no número 1.

---

## 10. O QUE FOI RODADO

| | |
|---|---|
| `test_onrcpn_api.py` | **26** — abrem o contrato guardado e comparam |
| `test_proclamas.py` | **19** — o domínio, sem rota e sem rede |
| `test_proclamas_web.py` | **14** — as telas, com o transporte trocado |
| `test_rc_matricula.py` | 23 — com os cinco novos do Livro D |
| os varredores da casa | `csrf`, `função sem tela`, `débitos do balcão`, `portabilidade`, `menu`, `esquemas` |

**E o varredor de função órfã cobrou uma dívida antiga**: `compor_do_assento`
estava em `JA_SABIDAS` desde que foi escrita, e deixou de ser órfã quando
`proclamas.matricula_do_proclama` passou a chamá-la. Saiu da lista — **nome que
deixou de ser órfão sai, senão ela só cresce e o varredor vira enfeite.**

`ruff check` limpo nos módulos novos e nos alterados.

> **Um achado de lint que se recusou:** o `SIM118` pedia trocar
> `"matricula" in a.keys()` por `"matricula" in a`. **Num `sqlite3.Row` isso
> muda o significado** — `in` itera os **valores**, e não as chaves: `"x" in
> linha` devolve `True` quando `x` é o conteúdo de alguma coluna. A troca faria
> a leitura acertar por acaso e errar quando o dado mudasse. Fica com
> `# noqa`, e o motivo escrito ao lado.
