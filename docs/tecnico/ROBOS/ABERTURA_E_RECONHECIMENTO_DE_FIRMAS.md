# Guia operacional — Abertura e reconhecimento de firmas

**Sistema:** Cartório Gestão (módulo Notas) · referência v3.6.68  
**Serventia:** Ofício Único de Cidade Exemplo/MA — CNS 000000  
**Robô deste ato:** Robô Abertura de Firmas  
**Biometria/foto (#39):** coordenar com Robô Firmas  
**Base jurídica resumida:** Lei 8.935/1994 art. 52; doutrina em *Registros Públicos* (coord. Alberto Gentil) — Caps. Notas e RI  
**Público:** qualquer operador do balcão + robôs

---

## 1. O que é o quê

| Conceito | No balcão | No sistema |
|---|---|---|
| Abertura de firma | Abrir ficha / cartão de assinatura (depósito do padrão) | `/notas/cartoes` · tabela `nt_cartoes` · selo de abertura |
| Cartão / ficha | Papel assinado pelo **cliente** + imagem digitalizada | Ficha `.odt` + `nt_cartao_imagens` |
| Reconhecimento por semelhança | Confrontar traço com o cartão (pode sem a pessoa) | `/notas/reconhecimento` espécie `SEMELHANCA` |
| Reconhecimento por autenticidade | Pessoa assina o documento **na frente** do tabelião/escrevente | espécie `AUTENTICIDADE` |
| Livro / termo de presença | Prova de que compareceu (Gentil) | Tabela `nt_presencas` existe; **fluxo atual não cria sozinho** — usar livro/papel da casa |
| Etiqueta | Tira térmica colada no documento | 100×30 mm · `/notas/reconhecimento/<id>/etiqueta` |

**Competência (Gentil / Lei 8.935):** reconhecimento de firma por Tabelião de Notas ou RCPN (art. 52). Nesta casa: Tabelionato de Notas.

---

## 2. Telas e atalhos

| O quê | Caminho |
|---|---|
| Buscar / abrir cartão | `/notas/cartoes` |
| Ficha do cartão | `/notas/cartoes/<id>` |
| Imprimir ficha para assinar | `/notas/cartoes/<id>/ficha` |
| Enviar digitalização da ficha | POST na ficha do cartão (`/fichas`) |
| Foto do cadastro (#39) | `/notas/cartoes/<id>/foto` |
| Digitais (#39) | `/notas/cartoes/<id>/digital` |
| Balcão reconhecer | `/notas/reconhecimento` |
| Ato já lavrado | `/notas/reconhecimento/<id>` |
| Lista de reconhecimentos | `/notas/reconhecimentos` |
| Ajustar etiqueta | `/notas/etiqueta/ajuste` |
| Mutirão autógrafos E-Ofício | `/notas/assinaturas` (ADMIN/MANAGER) |

**Selagem (rede do selador, LAN):**  
- Abertura: `/selo/notas/cartao-assinatura` → `nt_cartoes.selo_abertura`  
- Reconhecimento: `/selo/notas/reconhecimento-firma` → **1 selo por firma** (`nt_reconhecimento_partes.selo`)

**Emolumentos (tabela TJMA nesta casa):**  
- Cartão / abertura: serviço **412** (13.17.1)  
- Reconhecimento comum: **413** (13.17.2) — semelhança e autenticidade  
- Veículo: **414** (13.17.3)  
- Conteúdo financeiro: **416** (13.17.4)

---

## 3. Checklist — Abrir firma (cartão novo)

1. Documento de identidade **original** da pessoa (Gentil: identificar no primeiro ato).
2. `/notas/cartoes` → cadastrar cartão novo.
3. Nome obrigatório. Se o sistema avisar **duplicata** (mesmo CPF ou nome), conferir se é outra pessoa; só então confirmar.
4. Preencher o que a casa usa no balcão (CPF, RG, filiação, endereço, etc.). Cidade padrão da casa: Cidade Exemplo / MA.
5. Marcar **PPE** se for o caso (diligência reforçada — Prov. CNJ 88/2019).
6. Gravar: o sistema tenta o **selo de abertura**. Se falhar, o cartão **já nasceu** — mensagem SEM SELO; anotar selo depois.
7. Imprimir a ficha (`.odt`). **Só o cliente assina** (oficial não assina a ficha).
8. Digitalizar e **enviar a ficha na tela do cartão** (o formulário de abertura não tem anexo de arquivo).
9. Foto e digitais (#39): **não são obrigatórias** para abrir nem para selar. Avisar o que falta; pode ficar para a próxima visita.
10. Sem imagem de autógrafo no cartão, reconhecimento por semelhança fica frágil — priorizar a digitalização.

**Permissões:** ADMIN, MANAGER, USER, AUDITOR (conforme rota).

---

## 4. Checklist — Reconhecer por semelhança

1. `/notas/reconhecimento` · busca com pelo menos **3 letras** ou CPF.
2. Abrir a assinatura na **lupa** (clique / gestos: zoom, girar, comparar vias).
3. Confrontar o traço com o cartão (inclinação, levantamento da caneta, laço do sobrenome).
4. Ler os **avisos** do cartão: bloqueado, inativo, só-autenticidade, PPE, terrorismo, sem CPF, CPF inválido.
5. Cartão **bloqueado**: só reconhecer com confirmação consciente.
6. Flag **somente autenticidade**: **proibido** reconhecer por semelhança — mudar a espécie.
7. Preencher descrição do documento; marcar veículo/financeiro se couber (muda o item de emolumento).
8. Confirmar → lavra o ato → selagem (1 selo por firma).
9. Imprimir etiqueta térmica **100×30 mm**. Na impressora: escala **100%** (não “ajustar à página”).
10. Sem selo: a tela e a etiqueta avisam — não tratar como conferível.

**Permissão no balcão (POST):** ADMIN, MANAGER, USER (AUDITOR não reconhece).

---

## 5. Checklist — Reconhecer por autenticidade

1. Mesma tela · espécie **AUTENTICIDADE**.
2. Pessoa presente · identificar · ela assina o **documento** na frente.
3. **Gentil:** também assina o **Livro de Reconhecimento de firma** (prova de presença).  
   No Cartório Gestão: `nt_presencas` está modelada, mas o fluxo atual **não cria o termo automaticamente** — usar o livro/papel da casa até o sistema passar a gerar.
4. Se o ato em si exige autenticidade (ex.: transferência de veículo), a **procuração** para esse ato também deve ser por autenticidade — semelhança aí gera insegurança de identificação (Gentil).
5. Selar · imprimir etiqueta · mesmas regras de selo/escala.

---

## 6. Depois do ato / manutenção do cartão

- Reimprimir etiqueta pela lista se a térmica falhar (o sistema conta impressões).
- Cancelar reconhecimento só com **motivo**; etiqueta de ato cancelado **não** imprime.
- Corrigir cadastro, bloquear/desbloquear: na ficha `/notas/cartoes/<id>`.
- Ajustar medidas da etiqueta: `/notas/etiqueta/ajuste` (teste em folha comum antes de gastar o rolo).
- QR do selo: portal TJMA (`selo.tjma.jus.br`); número do selo continua impresso ao lado.

---

## 7. Biometria e foto (#39) — borda com Robô Firmas

- Ficam no **cadastro** (`nt_cadastro_imagens`), **não mudam** a ficha de papel impressa.
- Disco: `%PROGRAMDATA%\CartorioGestao\arquivos\notas\firmas\<id>\` (`foto.jpg`, `digital_N.png`).
- Dedos da casa (CCN): 1, 2, 6, 7 (polegares e indicadores).
- Leitor: DigitalPersona U.are.U 4500/4000b (homologado CNB) — coleta no balcão; CCN fora do ar não trava abertura.
- **Robô Abertura de Firmas** cobre abertura/reconhecimento notarial; **Robô Firmas** cobre o pipeline biométrico/CCN.

**Atenção de tela:** em `notas_cartao.html` pode aparecer painel de digitais do #39 e um stub antigo ao mesmo tempo — seguir o bloco do #39; avisar o oficial se o stub confundir o balcão.

---

## 8. Lacunas conhecidas (v3.6.68)

1. Formulário de cartão novo sem upload — anexo só na ficha depois.
2. `somente_autenticidade` no banco/regras, sem interruptor claro na UI de edição.
3. `nt_presencas` sem lavratura automática na autenticidade.
4. Se o selador falhar, cartão/ato nasce sem selo (aviso SEM SELO).
5. Sem regra automática de menor/estrangeiro no domínio de firmas — critério humano.

---

## 9. Arquivos técnicos (para robô / suporte)

- `notas_web.py`, `notas_schema.py`, `notas_partes.py`, `cadastro_biometria.py`, `notas_selo.py`, `etiqueta.py`
- Templates: `notas_cartoes`, `notas_cartao`, `notas_reconhecimento`, `notas_reconhecimento_ver`, `notas_reconhecimentos`, `notas_etiqueta*`
- Docs irmãs: `ETIQUETA_DE_FIRMA.md`, `LUPA_DAS_ASSINATURAS.md`, `PROJETO_39_CADASTRO_CCN.md`, `LEVANTAMENTO_NOTAS.md`
- Livro de referência (Downloads): *Registros Públicos* (Alberto Gentil) — PDF/EPUB

---

## Histórico

| Data | O quê |
|---|---|
| 2026-09-07 | Criação do guia (código v3.6.68 + Gentil + decisão #39). |

*Manter este histórico curto. Toda mudança de regra ou tela ganha uma linha aqui.*
