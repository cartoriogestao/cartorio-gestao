# As renegociações da Resolve — o que faltava da API da CENPROT

> «se atualize sobre o projeto do sistema, veja os novos módulos de integração
>  com as APIs das centrais, e construa a integração com a api da resolve na
>  cenprot (juntei em downloads o pdf)» — o oficial, 03/09/2026

## A primeira coisa medida: ela já existia

Antes de escrever qualquer linha, o estado real:

| | |
|---|---|
| `cenprot_api.py` | 721 linhas, **20 caminhos** medidos no `swagger.yaml` v2.1.0 |
| `cenprot_pendencias.py` | a fila do balcão — baixar, decidir, dispensar, enviar |
| `cenprot_web.py` | 9 rotas |
| no menu | **Pendências da CENPROT**, no Protesto |
| testes | **192**, em seis arquivos |

**Dezessete dos vinte caminhos já tinham função.** A integração foi construída
em 02/09/2026, e o PDF que o oficial juntou agora **já estava na casa** desde
então, em `FONTES_EXTERNAS/cra21/cenprot_errata_comunicado_007_2024.pdf`.

**E ele é o comunicado, não a documentação técnica.** O PDF anuncia a API e
aponta, em três links embutidos, para o manual, o Swagger e o manual de
autenticação. O manual é a **versão 1.0, de 29/02/2024, com cinco caminhos**; o
contrato vivo é **OpenAPI 3.0, versão 2.1.0, com vinte**. Construir pelo PDF
seria construir contra um contrato de dois anos atrás — foi por isso que, em
02/09, o módulo foi escrito a partir do `swagger.yaml`.

## O que faltava, e era o coração da coisa

Dos três caminhos sem função, dois são os legados `/anuencias` e `/certidoes`,
**declarados de propósito** para ninguém os reinventar achando que sumiram.

O terceiro era **a renegociação** — e ela é justamente aquilo para que a Resolve
existe. O comunicado do IEPTB diz, com todas as letras, que a API veio para que
ela «aumente a base de títulos que podem ser cobrados junto aos devedores»: a
renegociação é a proposta que o devedor faz para quitar e cancelar o protesto.

**Os dois caminhos estavam declarados e nenhuma função os chamava.** O balcão
não via proposta nenhuma.

### E a função chegou a existir, e foi apagada — corretamente

Em 02/09 uma `renegociacoes()` foi escrita e **apagada no mesmo dia**, porque o
varredor de função órfã a pegou: peça pronta que nenhuma tela chama é, neste
projeto, a arma que alguém religa sem saber por que existia. O caminho ficou
declarado em `CAMINHO`, e a decisão está registrada no CLAUDE.md.

**Isto aqui não é a volta daquele órfão.** É a espécie inteira: baixar, entrar
na fila, aparecer na lista, ser decidida na ficha e subir à Central — com tela,
com chamador e com teste em cada elo.

## O que se construiu

**A sexta espécie de `cn_pendencias`.** A tabela já servia cinco (anuência,
certidão, cancelamento, decisão judicial, pedido de protesto) e a vida delas é a
mesma: chega, alguém decide, a resposta sobe. O que muda é o teor.

| | |
|---|---|
| **baixar** | `GET /renegociacoes` — `data_inicio`, `data_fim`, `pagina` (1.000 por página) |
| **enviar** | `POST /renegociacoes/processar` — lote de até **1.000**, array obrigatório |
| **o código** | `cd_renegociacao_divida` |

**O que a casa decide é UM número: a custa de cancelamento.** Ela não aceita nem
recusa a proposta — isso é entre o devedor e o credor. Ela responde **quanto
custa cancelar**, e é esse valor que a Resolve mostra a ele.

É a regra do CNIB outra vez, pela quinta vez neste projeto: preparar, e não
decidir pelo outro.

## O achado que mais importa: o valor já estava calculado, e era o outro

A renegociação manda `vl_custa` — a **custa de cancelamento**.

`protesto_cenprot.precos_do_titulo` devolve **os dois** valores desde 31/08:

```
retirada     = 82,64  + faixa 17.4   ← o devedor paga antes de o protesto sair
cancelamento = 224,68 + faixa 17.1   ← desfazer o protesto já lavrado
```

**A retirada era a que estava à mão** — `retirada_sugerida` já existia, para o
pedido de protesto. Usá-la aqui mandaria à Central um valor que o devedor
**paga**, com quase cento e cinquenta reais de diferença.

**E não apareceria em tela nenhuma.** Só no balcão, com o cliente reclamando do
preço — que é o pior lugar para descobrir.

`custa_de_cancelamento_sugerida` é a função nova, e o teste que a guarda lê o
código das duas e exige que uma use `cancelamento` e a outra `retirada`.

**É sugestão, e a tela diz isso** — a regra da receita de custas e da
participação das partes na DOI. E `None` não vira zero: zero afirma «não custa
nada», e o devedor viria ao balcão com essa afirmação.

## O que o envio recusa antes de tocar na rede

A Central responde **um `status_http` por item dentro de uma resposta 200** — um
lote com metade recusada volta como sucesso. Sem conferência aqui, a tela diria
que mandou o que não mandou.

- lote vazio
- lote acima de **1.000** (o `maxItems` do contrato), dizendo para mandar em partes
- item sem `cd_renegociacao_divida` ou sem `vl_custa`, **dizendo qual item do lote**

## O que os testes guardam

`tests/test_cenprot_renegociacao.py`, 16 testes. Os que mais valem:

- **os dois caminhos e o teto lidos do `swagger.yaml` real** — o contrato está na
  casa, e o teste o abre. Foi assim que seis defeitos apareceram em 02/09.
- **a custa de cancelamento não é a retirada** — lê o código das duas funções.
- **toda espécie declarada tem despacho de baixa e campo de código** — uma
  espécie nova sem entrada apareceria no seletor e estouraria ao baixar.

## O que continua faltando, e não é isto

**A credencial.** Medido nesta máquina em 03/09/2026: `cenprot.cred` **não
existe**, e as cinco Centrais estão todas com `informada: False`.

O caminho é *Administrativo → Configurações*, na tabela das Centrais. **Não me
mande a senha** — ela é digitada por você numa tela e gravada em
`%PROGRAMDATA%\CartorioGestao\`, que o backup não alcança.

Sem ela, o sistema recusa com a frase certa («A credencial da CENPROT ainda não
foi informada») e não há como saber se a Central responde como o contrato diz.
