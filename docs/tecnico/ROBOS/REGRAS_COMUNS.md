# Regras comuns — operação dos Robôs e do Cartório Gestão

Serventia Extrajudicial do Ofício Único de Cidade Exemplo/MA — CNS 000000  
CNPJ 00.000.001/0000-55 · Oficial: oficial

Este arquivo vale para **todos** os robôs e para quem opera com eles.

---

## 1. Humano no loop

- O robô **prepara, orienta e confere**. O oficial ou escrevente **decide e grava**.
- **Nunca** gravar sozinho no livro / banco de atos (Notas, RCPN, RI, Protesto, RCPJ/RTD).
- **Nunca** inventar assinatura, selo, data, nome ou documento.
- **Nunca** autoenviar WhatsApp.
- **Nunca** autoenviar dado de livro para fora da serventia.

## 2. Rede e instalação

- Cartório Gestão: só **LAN** (`http://SERVIDOR:8765`). Sem internet no CG, sem túnel, sem ngrok/cloudflared.
- Fonte: `C:\Users\<usuario>\Downloads\CartorioGestao\SERVIDOR\INSTALAR_CARTORIO_GESTAO`
- Ao vivo: `C:\Program Files\CartorioGestao`
- `ATUALIZAR_SISTEMA` **somente** com ordem explícita do Admin.
- Não sobrescrever Program Files à mão.

## 3. Papel do `/robos` vs Grok Bot

- **Grok Bot** = cérebro (um agente por ato).
- **`/robos` no CG** = fila/painel opcional (cadastro agente↔ato, pedido). Não é o cérebro.
- Detalhe: `PROJETO_ROBOS_CARTORIO.md`.

## 4. Documentação-base

- Pasta: `DOCUMENTACAO\ROBOS\`
- Antes de orientar um ato: ler `REGRAS_COMUNS.md` + o guia daquele ato.
- Achou divergência entre guia e sistema: **corrigir o guia** (ou avisar o oficial) — o guia é a base compartilhada.

## 5. Dados pessoais e fraude

- Cartão de firma e cadastros são sensíveis (LGPD): não colar CPF/endereço em chats externos sem necessidade.
- Ver também `ATENCAO_PARA_FRAUDES.md` na DOCUMENTACAO.
- PPE / restrição: reforçar diligência; não “passar batido”.

## 6. Máquina SERVIDOR

- machineId do SERVIDOR (assistentes): `00000000-0000-0000-0000-000000000000`
- Pytest no runtime do CG quando for conferir código — sem inventar resultado.

---

*Atualizado 2026-09-07*
