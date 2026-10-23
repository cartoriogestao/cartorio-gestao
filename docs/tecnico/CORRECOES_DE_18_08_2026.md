# As correções de 18/08/2026 — versão 3.3.9

Levantamento e conserto do primeiro dia de operação real do módulo de Registro de Imóveis.

## O que aconteceu na terça

Cinco atos, seis selos, um só negócio: o Título de Domínio MA05000000003 do INCRA em favor
de PESSOA EXEMPLO, Lote 32 do P.A. Vale do Jordão, prenotação 11.534. Tudo
lavrado por `beatriz`, em nome da Tabeliã Registradora Substituta.

| Hora | Ato | Selo | Emolumentos |
|---|---|---|---|
| 11:56 | AV-28/582 — destaque de área e abertura de matrícula | `AVESVD0000001KD2C8V6G26JSK43` | R$ 134,43 |
| 13:46 | R-01 da matrícula nova — título de domínio | `REGAVD000000OD1Q8BV5TOOZE492` | R$ 5.590,81 |
| 14:12 | AV-02 — condições resolutivas e inalienabilidade | `AVESVD000000NARRKWVNJCRSVO21` | R$ 134,43 |
| 14:50 | AV-03 — Floresta Pública Tipo B | `AVESVD000000FGG3MHVL8PU1JW52` | R$ 134,43 |
| 15:41 | Certidão 6/2026 — inteiro teor da 582 | `CERINT…` e `CERELE…` | R$ 172,86 |

## Os três defeitos, e o que cada um era de verdade

### 1. A matrícula nasceu com número já usado — e não foi digitação

O sistema contava o próximo número **por livro**. Mas o número da matrícula é único **na
serventia**: os livros 2, 2-A … 2-S são **volumes** do mesmo Livro 2 de Registro Geral, e a
letra é o volume, não uma série própria.

O volume "2" estava em 4010. O volume "2-S" já tinha a 4013. O sistema olhou só o "2" e deu
**4011** — número que a serventia já havia usado. Os três atos, no teor, dizem **4014**: a
escrevente escreveu certo, a máquina contou errado.

> Se tivesse ficado sem conserto, **toda matrícula nova aberta no volume 2 nasceria com
> número repetido.** O defeito não era daquele atendimento; era da próxima matrícula também.

**Corrigido em `ri_correcoes.py`:** o número passa a vir da **série**, olhando as duas fontes
(as matrículas de verdade e a tabela de numeração) e nunca andando para trás. O Livro 3
(Registro Auxiliar) continua contando separado, porque é série distinta.

### 2. O R-01 deixou a matrícula sem proprietário

O INCRA foi gravado com o papel **"adquirente"** — e o INCRA é quem transmite. A adquirente
ficou **sem papel nenhum**. Como o sistema só marca proprietário quem tem papel começando por
"propriet", a matrícula ficou **sem titular ativo**: certidão de propriedade em branco,
ausência no Indicador Pessoal, e recusa na CTP e na DOI por falta de transmitente e de
adquirente.

E não havia tela para corrigir parte — nem nome, nem documento, nem papel.

**Corrigido:** existe agora *corrigir* em cada linha da tabela de Partes, na ficha, com
motivo obrigatório e de-para na auditoria. Não toca em teor.

### 3. A certidão saía com marcação de ODT dentro do texto certificado

`contexto_ficha(para_odt=False)` — o caminho da certidão — desligava o **embrulho** do
fragmento, mas a **conversão para ODF já tinha acontecido**. O corpo da certidão, que é
gravado em HTML no banco para congelar o teor da emissão, recebia
`<text:p text:style-name="P-just">` no meio do texto.

**Corrigido:** a conversão passou a depender do destino, não só o embrulho. Novos
`texto_para_html` e `bloco_selo_html` em `ri_odt.py`.

## O AV-03, e por que expurgo em vez de cancelamento

O AV-03 averbou obrigação relativa a Floresta Pública Tipo B, mas o próprio teor traz a
ressalva de que **o título não individualiza existência, localização, extensão nem percentual
de sobreposição**. O ato não tinha base no título, foi lavrado em teste, e o selo foi
cancelado no Tribunal.

Cancelar por averbação escreveria na ficha, para sempre, que houve ato onde não houve — e
sairia riscado em toda certidão de inteiro teor da 4014 pelos próximos cinquenta anos.

Daí o **expurgo com ata de ocorrência** (`ri_expurgo.py`): o ato sai da ficha e passa a
existir na ata, que guarda o teor íntegro, o selo do sistema, o selo cancelado no Tribunal, o
fundamento e quem ordenou.

### As travas do expurgo, e por que cada uma

1. **Só ato de origem MANUAL** — ato do acervo não se expurga.
2. **Só o último ato da matrícula** — o hash encadeia no anterior; tirar um do meio quebraria
   a conferência dos seguintes em silêncio.
3. **Ato não cancelado, e que não cancelou outro.**
4. **Nenhuma certidão viva pode citar o ato** — foi essa trava que protegeu o AV-28/582, que
   a certidão 6/2026 transcreve.
5. **Nenhuma CTP fechada nem DOI entregue pode conter o ato.**

## A renumeração e o hash

O hash de cada ato inclui o número da matrícula. Renumerar 4011 → 4014 invalida a cadeia
**por construção** — e isso é o mecanismo funcionando, não efeito colateral. A cadeia é
recalculada com o número novo, e **os dois hashes de cada ato ficam na auditoria**, para que a
troca seja auditável e não um apagamento silencioso. Depois disso a cadeia volta a conferir —
e passa a conferir contra a verdade, porque os teores sempre disseram 4014.

## O que ficou como está, e por quê

- **AV-28/582, R-01 e AV-02 permanecem.** Só o AV-03 saiu.
- **A certidão 6/2026 continua válida:** ela transcreve o AV-28, que fica, e nada tem do
  AV-03, que é de outra matrícula. O defeito dela era de formatação, e foi corrigido no
  código — as próximas saem limpas.
- **O depósito prévio DP2026.08.3**, R$ 6.499,31 de PESSOA EXEMPLO, fica intacto,
  com saldo integral, à disposição do registro.
- **O protocolo 11.534 continua aberto**, com data-limite vencida em 06/08 e sem vínculo com
  os atos. Fica para a rodada seguinte.

## Ensaio contra o banco real

Antes de subir, a sequência inteira foi ensaiada sobre uma **cópia do banco de produção**:

```
próximo número do livro 2 ....... 4014   (antes: 4011)
livro 3, Registro Auxiliar ...... 1651   (conta separado, como deve)
expurgo do AV-03 ................ nenhum impedimento
expurgo do AV-02 ................ recusado: não é o último ato
expurgo do AV-28/582 ............ recusado: a certidão 6/2026 o transcreve
estado final .................... matrícula 4014, atos R-01 e AV-02, cadeia CONFERE
partes .......................... INCRA transmitente; PESSOA EXEMPLO proprietária, titular
próximo número depois ........... 4015
AV-28 da 582 .................... intacto
certidão 6/2026 ................. válida
depósito DP2026.08.3 ............ R$ 6.499,31
```

## Testes

443 → **508**. Sessenta e cinco novos, e todos nasceram de um fato do dia 18:

- `tests/test_ri_correcoes.py` — a série do livro, a numeração por serventia, a renumeração
  com recálculo de cadeia, os papéis das partes.
- `tests/test_ri_expurgo.py` — as cinco travas, uma por uma, e a ata.
- `tests/test_ri_correcoes_web.py` — os caminhos pelas telas, incluindo
  `test_a_certidao_nao_leva_marcacao_de_odt_no_corpo`, que falha se o defeito voltar.

## Ainda em aberto, documentado

- O protocolo 11.534 continua ABERTO e sem vínculo com os atos; prenotação não se amarra
  sozinha ao ato lavrado.
- A marca REURB-S não é gravada.
- O comprovante de prenotação de REURB-S imprime "20 dias úteis" com data-limite de 40.
- `conferido_por` nunca é gravado.
- CNM não é gerado nem validado.
- Cancelar certidão e encerrar protocolo existem na rota e não têm botão em tela.
- O recibo da DOI diz "registrado" mesmo quando não há remessa gerada.
- `manutencao_diaria_erro` é gravado e nenhuma tela o exibe.
- Selo colado como imagem (Ctrl+V / arrastar) não entra no ato — nenhum dos atos de 18/08 tem
  o QR gravado.
