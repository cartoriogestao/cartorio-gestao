# O layout da CRA, medido — versão 3.5.0

> **Complemento de 23/09/2026:** esta medição é do arquivo legado de linhas
> de 600 posições. A API CRA21 em homologação devolveu uma remessa **XML**
> com os atributos FEBRABAN `h01`…`h17` e `t01`…`t52`; não se deve passar
> o XML cru a este leitor. Ver
> [CRA_HOMOLOGACAO_REMESSA_2026-09-23.md](CRA_HOMOLOGACAO_REMESSA_2026-09-23.md).

**21 de agosto de 2026.** O uso do sistema segue suspenso; nada disto foi aplicado.

## Não havia manual. Havia 99 arquivos.

O layout de 600 posições da CRA **não está documentado em lugar nenhum da sua
máquina**. O que há é o `LAYOUT 600 PROTESTO - Novo.PDF`, da SERASA — outro arquivo,
do mesmo tamanho, que serve para reportar protestos à SERASA e não para receber
títulos da Central. Conferi: no layout da SERASA as posições 2 a 44 são brancas; nos
arquivos da CRA elas trazem o nome do apresentante. São coisas diferentes.

Então o layout foi **medido**. Em `C:\ARPNET\CRA` há **99 arquivos** de 600 bytes, com
**1.058 registros de título**. Cada campo foi conferido contra o que o E-Ofício gravou
para **o mesmo título** em `tbAvisoProtesto`.

**Os 1.058 registros casaram por número do título — 100%.** É esse casamento que
transforma suposição em medida: a partir dele, cada outro campo tem contra o que ser
conferido.

## O que cada campo acertou

| Campo | Posições | Conferiu |
|---|---|---|
| Número do título | 217–227 | **100%** — foi por ele que os 1.058 casaram |
| Espécie | 214–216 | **100%** |
| Documento do devedor (CPF/CNPJ) | 346–359 | **100%** |
| Tipo do documento (001=CNPJ, 002=CPF) | 343–345 | **100%** |
| Cidade do devedor | 424–443 | **100%** |
| CEP e UF do cedente | 169–176, 197–198 | **100%** |
| Documento do cedente | 110–123 | **100%** |
| UF do devedor | 444–445 | 99,7% — a única falha é `ma` minúsculo |
| Data de emissão | 228–235 | 99,7% |
| Saldo a protestar | 261–274 | **99,1%** |
| CEP do devedor | 416–423 | 96,5% |
| Nome do devedor | 298–342 | 92,7% |
| Endereço do devedor | 371–415 | 87,2% |
| Data de vencimento | 236–243 | 87,2% — as falhas são `99999999` |
| Nome do cedente | 20–64 | 86,6% |
| Cidade do cedente | 177–196 | 82,5% — diferença de acento |
| Endereço do cedente | 124–168 | 49,1% |

As diferenças que sobram **não são de layout**: são acento (`SAO LUIS` no arquivo,
`São Luís` no acervo), abreviação (`PESSOA EXEMPLO` × `PESSOA EXEMPLO`) e endereço
corrigido depois pelo escrevente. O caso do endereço do cedente, com 49%, é esse em
grau maior — o E-Ofício guarda o endereço **corrigido**, não o recebido. Fica anotado
como coisa a decidir: qual das duas versões o sistema novo guarda.

## Três coisas que só apareceram medindo

### 1. Cedente na frente, devedor atrás — e eu tinha invertido

Na primeira leitura chamei o primeiro bloco de nomes de "sacado". Está errado: o
primeiro bloco é o **cedente** e o segundo é o **devedor**.

O que denunciou foi o endereço. O devedor é de Cidade Exemplo — é por isso que o título
se protesta aqui — e o cedente é de fora. O endereço local estava no *segundo* bloco.
A conferência contra o acervo confirmou: com os campos trocados, 0% batia; corrigidos,
92,7% e 100%.

### 2. As pastas do E-Ofício não dizem o que o arquivo é

Há arquivo de **remessa** dentro da pasta `Retorno`. Quem se guiar pela pasta lê com o
layout errado — e o layout do retorno é outro, com espécie, datas e valor em posições
diferentes (medi: 0% de acerto se lido como remessa).

O que diz o que o arquivo é são as **posições 53 a 61 do cabeçalho**, com
ORIGEM(3) + DESTINO(3) + TIPO(3):

| Marca | O que é | Sentido |
|---|---|---|
| `BFOSDTTPR` | remessa de títulos para protesto | chega ao cartório |
| `SDTBFORTP` | retorno dos títulos protestados | sai do cartório |
| `SDTBFOCRT` | confirmação do recebimento | sai do cartório |
| `SDTBFOAND` | andamento | sai do cartório |

O leitor se guia pelo cabeçalho, sempre.

### 3. O CNPJ perde o primeiro dígito se a leitura for ingênua

O campo tem 14 posições e vem com zeros à esquerda, então o CPF chega como
`00012345678901`. Cortar zero por zero erra nos dois sentidos: **todo CNPJ que começa
com zero perde o primeiro dígito**, e o CPF só fica com onze dígitos por sorte. Quem
diz quantos dígitos são é o campo do lado — 001 para CNPJ, 002 para CPF. Bate exato:
os 119 títulos com `001` são precisamente os 119 que têm CNPJ no acervo.

## O que não identifiquei, e não batizei

Quatro blocos ficaram sem nome — 360–370, 446–485, 508–545 e 546–596. São zeros e
brancos em todos os 343 registros de remessa (as custas, que só o retorno preenche),
com uma exceção: **uma letra D, C ou I na posição 477**, que não descobri o que é.

Eles se chamam `reservado_360`, `reservado_446` e assim por diante. Nome bonito em
campo desconhecido finge conhecimento que não existe — e há um teste que impede
alguém de batizá-los sem medir.

Um campo ficou **A CONFERIR**: o bairro do devedor, em 486–507. Traz "CENTRO" em 176
dos 343 e nomes de bairro nos demais, mas a máquina caiu no meio da conferência contra
o acervo e não voltei a rodá-la.

## O circuito, fechado

```
arquivo real da CRA
  → protesto_arquivo.ler()        estrutura, com o que o rodapé não confere
  → para_apontamento()            vocabulário do Protesto
  → protesto_cra.conferir_titulo() contra o esquema XML oficial
  → apontamento                    (o próximo passo)
```

O arquivo real de 12/09/2022 percorre esse caminho inteiro e sai **sem um único
achado**. Está na fixture de teste, com os nomes trocados por «mascarado» e todo o
resto — posições, valores, datas, documentos das empresas, CEP — como veio.

**28 testes**, e dois deles guardam o essencial: que o arquivo com um título torto
**não derruba os outros mil** (recusar o arquivo inteiro devolveria ao banco mil
títulos bons junto com o ruim), e que o rodapé é conferido contra o que foi lido —
porque arquivo estraga truncando, não com dado inválido no meio.

---

## E o selador, que você mandou fazer tudo

Li tudo. `tbSeladorConfiguracao` tem três colunas e a senha está **em texto claro**:
usuário no formato `nome.sobrenome`, senha de 8 caracteres. Não transcrevi nenhuma das
duas — nem aqui, nem em arquivo do projeto, nem na auditoria.

O que construí é melhor do que transcrever:

- **tela do selador** (`/selador`, menu Administrativo), com endereço, ambiente,
  usuário e senha;
- **botão "importar do E-Ofício"**, que lê aquela tabela e preenche tudo sozinho,
  rodando na sua máquina;
- e a decisão que importa: **a senha não entra no banco de dados**.

O banco viaja. Vai no backup, e uma cópia dele já saiu da serventia para eu ensaiar a
correção de 18/08 — se a senha estivesse lá, teria ido junto. Ela fica num arquivo
próprio da pasta de dados, ao lado do `secret.key`, que o backup não alcança.

Não chamo isso de criptografia e não vou chamar: o servidor precisa recuperar a senha
em claro para autenticar, então qualquer esquema que ele desfaça, quem tiver o disco
também desfaz. O ganho é concreto e vale a pena — **a senha deixa de sair de casa
dentro de backup e de cópia de banco**.

Há **46 testes** entre o módulo e a tela, e dois deles varrem o banco inteiro
procurando a senha, tabela por tabela, coluna por coluna.

### Por que eu não consegui selar de verdade

Não é falta de permissão sua. O selador está em `https://192.0.2.23:443`, na rede
local, e nenhum dos caminhos que tenho alcança essa rede: o ambiente na nuvem não tem
rota, o shell que roda na sua máquina fica numa VM sem placa de rede (testei: "rede
inalcançável"), e a extensão do Chrome não está conectada.

Quando o sistema voltar a rodar na sua máquina — que tem a rede —, ele sela.

## O que fica pendente

1. **O Livro 6 de Apontamento**, aberto em 05/03/2024 e nunca usado, ao lado do Livro
   1 que segue em uso. Você pediu para deixar como está; ficou registrado na
   conferência.
2. **O bairro do devedor**, em 486–507, A CONFERIR.
3. **A letra D/C/I na posição 477.**
4. **O layout do retorno** (`SDTBFORTP`), que é outro e ainda não foi medido — 383
   registros reais esperando.
5. **A URL de homologação**, que só existe na tela do E-Ofício.
