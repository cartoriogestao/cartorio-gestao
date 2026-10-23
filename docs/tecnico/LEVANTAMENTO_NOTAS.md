# Tabelionato de Notas — o que existe no E-Ofício

**14/08/2026.** Levantamento concluído. Duas exportações, 411 tabelas inventariadas, nada
alterado no E-Ofício.

---

## O movimento, de março de 2020 a hoje

| O que | Quantos | Observação |
|---|---:|---|
| Cartões de autógrafo | **4.061** | 4.043 ativos, 2 bloqueados, 462 com biometria |
| Imagens de assinatura | **3.637** | em disco, não no banco |
| Reconhecimentos de firma | **13.209** | 11.407 por semelhança, 1.802 por autenticidade |
| Termos de presença | **1.836** | autenticidade |
| Autenticações de cópia | **3.539** | todas com selo, um único serviço (código 415) |
| Procurações | **213** | 303 modelos de texto cadastrados |
| Escrituras | **45** | 40 comuns, 5 de CESDI |
| Substabelecimentos | **0** | tabela existe, nunca usada |

O reconhecimento de firma é o balcão: **13,2 mil atos**, contra 45 escrituras. Cinco pessoas
respondem por quase tudo — escrevente (6.754), escrevente (4.371), escrevente (1.047), escrevente (602) e
escrevente (414).

---

## Onde as coisas moram

**Cartão de autógrafo** — `tbFirma`, 62 colunas. Traz nome, CPF, RG com órgão emissor, filiação,
estado civil, profissão, endereço residencial e profissional, e-mail, telefone, cônjuge, CNH,
título de eleitor. Tem também o que a legislação de prevenção à lavagem exige: `bitPPE` para
pessoa politicamente exposta e `biTerrorista`. A biometria fica em `memDigital`, num molde
proprietário — 462 cartões a têm.

**Imagens da assinatura** — `tbFirmaIMG` guarda só o nome do arquivo e o caminho
`\\servidor\C11\Firmas\`. Nenhuma imagem está dentro do banco. Conferi contra o disco: dos
3.637 arquivos citados, **3.635 existem**; faltam dois e há cinco em disco sem registro. Vou
nominar os sete quando montar a carga.

**Reconhecimento** — `tbRFirma_Registro`, com selo, código de segurança e o texto que sai
impresso. Tem campos para transferência de veículo (`strPlaca`, comprador, vendedor, DUT) que
esta serventia nunca usou.

**Escrituras** — `tbRegistroESC`. Foi o achado que justificou puxar o inventário completo: o
nome não tem "escritura" nem "notas", e eu não o encontraria adivinhando. São 84 colunas, com os
campos das centrais já embutidos — regime de bens, ato anterior, natureza do litígio, valor da
transação, base de cálculo do ITBI, endereço do imóvel para a DOI.

---

## As centrais estão mapeadas no próprio E-Ofício

Isto poupa a parte mais arriscada do trabalho: os domínios já vieram prontos, não preciso
transcrever de manual.

**CENSEC** — três centrais, com os códigos oficiais:

- **CEP**: 10 tipos de ato (escritura, procuração, procuração previdenciária, renúncia,
  revogação, substabelecimento, ata notarial, ata de usucapião, procuração privada) e
  **38 naturezas** de escritura, de compra e venda a contrato de namoro.
- **CESDI**: 11 tipos — separação, reconciliação, conversão em divórcio, divórcio direto,
  inventário, sobrepartilha, retificação, nomeação de inventariante, partilha, inventário com
  menor ou incapaz, retificação de ato não notarial.
- **RCTO**: 6 tipos de testamento.
- **22 qualificações** de parte, separadas por central: outorgado, outorgante, interveniente,
  usufrutuário, conciliador, mediador no CEP; herdeiro, inventariante, divorciando, falecido,
  cedente no CESDI; testador no RCTO.

**DOI** — 39 tipos de transação com o código da Receita, 14 tipos de imóvel, 5 naturezas de
título, e 225 declarantes já cadastrados.

---

## Três correções ao que eu disse antes

**`tbLivroApontamento` não é de notas.** Suas 20.800 linhas são livro de **protesto** — trazem
sacado, credor, espécie do título e vencimento. Eu havia listado como candidata a livro
notarial.

**`tbSDT` também não é.** É arquivo de remessa de protesto.

**`tbCN_Generica` quase não é.** Das 1.482 linhas, 1.231 são certidões de RCPN e 221 são do RI.
Só 3 são de notas.

---

## Um achado que interessa ao Registro de Imóveis

Apareceu uma **`tbQualificacaoCENSEC`** com 22 linhas. Pode ser o dicionário do `intQualifica`
que ficou sem resposta quando minha hipótese do `tbTabelas` falhou — vale testar os códigos
contra os valores que estão nas partes do RI antes de dar por resolvido.

---

## O que isso significa para a construção

A ordem que você escolheu se confirma pelos números: **firmas e autenticações primeiro**. São
18,6 mil atos contra 258 do livro de notas, e é o que trava o balcão se faltar.

O trabalho tem três frentes de tamanho bem diferente:

1. **Cartão de autógrafo e reconhecimento** — o grosso. Precisa de busca rápida por nome e CPF,
   exibição da assinatura digitalizada lado a lado, e o cuidado com dado pessoal que já
   resolvemos no caixa: são 4.061 fichas com filiação, RG e endereço.
2. **Autenticação** — pequena e direta.
3. **Livro de notas** — 258 atos e 303 modelos de texto para aproveitar como biblioteca guiada.

As remessas às centrais ficam por último, mas o esquema de dados já pode nascer com os campos
que elas exigem — que é justamente o que o E-Ofício faz, e a razão de `tbRegistroESC` ter 84
colunas.
