# Roteiro — aplicar a 3.3.9 e consertar o dia 18

Seis passos, na ordem. A ordem importa: renumerar **antes** de expurgar faz a ata de
ocorrência nascer dizendo 4014, que é o número que os teores sempre disseram.

Tempo estimado: quinze minutos, mais o cancelamento do selo no Tribunal.

---

## Passo 0 — Backup, antes de tudo

Duplo clique em `FERRAMENTAS\BACKUP_AGORA.cmd`.

Não precisa de Administrador, não para o servidor, e ele confere o pacote depois de gravar.
Espere a mensagem de fim e confirme que apareceu um `backup_completo_...zip` novo na pasta de
backups.

> Não pule este passo. O expurgo e a renumeração não têm desfazer.

## Passo 1 — Aplicar a versão 3.3.9

**Menu → Administrativo → Atualizações.** Só ADMIN.

1. Arquivo: `CartorioGestao_3.3.9.cgu`
2. **SHA-256** (cole exatamente):

   ```
   12482cebea7d905085248e01fb83a39d74e7b543a0e36b883c16a180e5e0fbbe
   ```

3. Confirmar. O sistema fica fora do ar por alguns instantes.

Ele faz sozinho: confere a assinatura de cada arquivo, tira um backup completo de
pré-atualização, aplica, sobe e testa. **Se a versão nova não responder em 45 segundos, ele
restaura a anterior sem você fazer nada.**

Confirme no fim: **Configurações** deve mostrar **3.3.9**.

> Se preferir o caminho antigo, `SERVIDOR\ATUALIZAR_SISTEMA.cmd` também funciona — a pasta do
> projeto em Downloads já está com os arquivos novos. Mas o `.cgu` é melhor aqui, porque faz
> backup e volta atrás sozinho.

## Passo 2 — Renumerar a 4011 para 4014

**Registro de Imóveis → Matrículas →** busque `4011` **→** abra a ficha.

No painel **Identificação**, clique em **corrigir o número**.

- **Número novo:** `4014`
- **Motivo:**

  > Número 4011 já utilizado pela serventia no volume 2-S; a matrícula seguinte é a 4014, como já constava do teor dos três atos.

- **Renumerar.**

Deve aparecer: *"Matrícula 4011 passou a ser a 4014. A cadeia de integridade dos 3 ato(s) foi
refeita com o número novo, e os dois hashes de cada ato ficaram na auditoria."*

> O hash de cada ato inclui o número da matrícula, então renumerar invalida a cadeia por
> construção. O sistema recalcula e guarda os dois hashes na auditoria. Depois disso a
> conferência volta a fechar — e passa a fechar contra a verdade.

## Passo 3 — Expurgar o AV-03

Na mesma ficha, role até o cartão do **AV-03** e clique em
**Expurgar este ato (lavrado em teste)**.

A tela mostra tudo o que vai sair. Confira o selo e o teor.

- **Fundamento:**

  > Ato lavrado em 18/08/2026 durante a implantação do sistema, antes da sua entrada em operação. A averbação não tem base no título apresentado, que não individualiza existência, localização, extensão ou percentual de sobreposição a Floresta Pública Tipo B. Selo de fiscalização cancelado junto ao Tribunal de Justiça do Maranhão.

- **Selo cancelado:** `AVESVD000000FGG3MHVL8PU1JW52`
- **Confirmação:** escreva `EXPURGAR`

Deve aparecer: *"AV-03/4014 expurgado. A ata de ocorrência nº 1 guarda o teor íntegro, o selo
e o fundamento. Imprima-a e arquive."*

Em seguida, em **Atas de ocorrência**, clique em **baixar a ata (.odt)**. **Imprima e
arquive** — é o documento que, junto com o cancelamento do selo, prova o que houve.

## Passo 4 — Corrigir as partes do R-01

Na ficha da 4014, painel **Partes**. Três linhas, e a coluna **Ato** diz a qual pertence cada
uma.

**Linha do INCRA (ato R-1)** → *corrigir*:

- **Papel:** `transmitente`
- **Titular atual:** `não`
- **Motivo:** `O INCRA é o outorgante do título de domínio; não é adquirente.`

**Linha da PESSOA EXEMPLO do ato R-1** → *corrigir*:

- **Papel:** `proprietário`
- **Titular atual:** `deduzir do papel`
- **Motivo:** `Adquirente do título de domínio e titular atual do imóvel.`

A terceira linha é a PESSOA EXEMPLO do **AV-2**, e está sem papel. Ela não afeta a titularidade
— quem decide isso é a linha do R-1. Se quiser deixá-la explícita, `interveniente` serve.

> Sem esta correção, a certidão de propriedade da 4014 sai **sem proprietário**, ela não
> aparece no Indicador Pessoal em nome da Pessoa Exemplo, e a CTP e a DOI recusam o ato por
> falta de transmitente e de adquirente.

## Passo 5 — Conferir, antes de fechar

Na ficha da **4014**:

- [ ] o número no alto é **4014**
- [ ] os atos são **R-01** e **AV-02**, e o AV-03 não aparece
- [ ] **não há** nenhuma marca `Hash divergente`
- [ ] em Partes, **PESSOA EXEMPLO** aparece com **Ativo**, e o INCRA não
- [ ] nenhuma linha diz `sem papel`, exceto a Pessoa Exemplo do AV-2 se você a deixou assim

Em **Registro de Imóveis → Numeração das matrículas**:

- [ ] a coluna **Próximo da série** diz **4015**
- [ ] nenhum volume do Livro 2 aparece marcado `desalinhado`

Em **Atas de ocorrência**:

- [ ] a ata nº 1 está lá, com o selo cancelado ao lado

E, para provar que o defeito da certidão foi embora: emita uma **certidão de inteiro teor** de
qualquer matrícula e abra o `.odt`. Não deve haver `text:p` nem `text:style-name` no meio do
texto.

## Passo 6 — Cancelar o selo no Tribunal

No selador do TJMA, cancele **um selo só**:

```
AVESVD000000FGG3MHVL8PU1JW52
```

É o do AV-03, gerado em 18/08/2026 às 14:42:38, Ato 16.22.2, R$ 134,43.

**Não cancele os outros.** Ficam válidos:

| Selo | Ato |
|---|---|
| `AVESVD0000001KD2C8V6G26JSK43` | AV-28/582 |
| `REGAVD000000OD1Q8BV5TOOZE492` | R-01/4014 |
| `AVESVD000000NARRKWVNJCRSVO21` | AV-02/4014 |
| `CERINT0000001X6QAWVD87GIT007` | Certidão 6/2026 |
| `CERELE000000B8BFFW4OTASYJA15` | Certidão 6/2026 |

Guarde o comprovante do cancelamento **junto com a ata de ocorrência impressa**. As duas
coisas juntas é que fecham a história.

---

## O que este roteiro não toca, de propósito

- **A certidão 6/2026 continua válida.** Ela transcreve o AV-28, que fica, e nada tem do
  AV-03. O defeito dela era de formatação, e foi corrigido no código.
- **O depósito prévio DP2026.08.3**, R$ 6.499,31 do Pessoa Exemplo, fica intacto, com saldo integral.
- **O protocolo 11.534** continua aberto, vencido desde 06/08 e sem vínculo com os atos. Fica
  para a rodada seguinte.

## Se algo der errado

| Sintoma | O que fazer |
|---|---|
| A atualização diz que o SHA-256 não corresponde | Pare. O arquivo não é o que deveria ser — baixe de novo |
| A atualização diz "ROLLBACK" | Ela voltou sozinha para a 3.3.8. Nada foi perdido. Guarde `ProgramData\CartorioGestao\updates\last_result.json` e me mande |
| O botão "corrigir o número" não aparece | Você está como MANAGER ou a matrícula está encerrada. Entre como ADMIN |
| O botão "Expurgar este ato" não aparece no AV-03 | Só ADMIN vê, e só no **último** ato da ficha. Se o AV-03 não é o último, algo foi lavrado depois — me avise antes de continuar |
| A tela de expurgo lista impedimentos | Leia-os: cada um diz exatamente o que trava. Não force |
| Depois de renumerar aparece "Hash divergente" | Não deve acontecer. Se acontecer, **pare** e me mande a tela |
